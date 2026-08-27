# danbao-poc 下一步准确率优化开发计划

> 来源文档：
> - `accuracy_optimization_recommendations.md`
> - `OPTIMIZATION_PLAN.md`
>
> 目标：把两份文档里所有“还需要优化”的点合并成下一轮开发计划，并结合当前代码状态区分“已完成需回归”“部分完成需补齐”“未开始需开发”。

---

## 1. 总体判断

两份文档的核心判断一致：当前准确率瓶颈不在“再堆一个大模型能力”，而在检索链路的几个工程细节：

1. 短查询、产品名、制度条款这类高频场景需要更明确的路由和过滤。
2. BM25、向量、结构化、图谱、QA 多通道融合要降低噪声，不能让弱通道抢排序。
3. evidence alignment、坐标追溯、父子 chunk、引用协议要继续闭环，让“命中了什么”和“为什么可信”可验证。
4. 图谱和实体治理要从“能抽出来”推进到“能稳定合并、能稳定检索”。

当前代码已经完成了前一轮 09 文档中的一批基础能力，包括：

- 短查询改写保护：`retrieve_service.py:_query_rewrite_guard()`。
- 默认 `weighted_rrf` 融合：`query.py:resolve_weighted_rrf_config()`。
- 父子上下文组装：`retrieve_service.py:_enrich_evidence_groups()`。
- 字段置信度、QA evidence quality、引用协议、前端 evidence/debug、图谱边权重和 BFS。
- 关系规则补抽、Anchor 候选池、增量索引代际复用。

所以本计划不重复写“已经完成”的基础项，而是把它们转成回归验证或细化任务。

---

## 2. 执行前必须先做：分品类 baseline

### A0. 建立 315 题分品类 baseline

状态：已完成，作为后续每项优化的固定回归入口。

来源：

- `accuracy_optimization_recommendations.md` 第六部分。
- `OPTIMIZATION_PLAN.md` 1.1、1.2。

为什么先做：

- 当前只知道总命中率约 80%，但两份文档都指出最差品类不同：制度刁难、制度模糊、制度文件、反混淆、跨库混合。
- 后续每项优化必须知道改善了哪个品类、是否伤害了其他品类。

已落地：

1. 新增 `tests/run_category_accuracy_baseline.py`，默认读取 `tests/results/correctness_v2.json`。
2. 输出：
   - `tests/results/category_accuracy_baseline.json`
   - `tests/results/category_accuracy_baseline.md`
3. 当前 315 题 baseline：
   - RAGFLOW 有效命中：227/315，72.1%。
   - danbao-poc 有效命中：252/315，80.0%。
4. 当前最需要盯住的差品类：
   - 制度刁钻：错误率 66.7%。
   - 制度模糊：错误率 66.7%。
   - 制度文件：错误率 56.5%。
   - 反混淆：错误率 35.5%。
   - 跨库混合：错误率 30.0%。
5. 报告已附加 Query Rewrite Guard 模拟，用来观察开启 `query_assist.enabled=true` 时哪些题会跳过 LLM 改写。

验收标准：

- 可以一键跑出 315 题分品类报告。
- 每个优化 PR 或开发批次都能比较“改前/改后”。
- 任一单项优化导致总命中率下降超过 1%，或任一重点品类下降超过 3%，需要回退或降级开关。

---

## 3. Phase 1：立即修复与调权

### P0-1. 修复 BM25 子通道归一化问题

状态：已完成。

来源：

- `accuracy_optimization_recommendations.md` 修复 1。
- `OPTIMIZATION_PLAN.md` 2.3。

当前问题：

- `es_store.py` 里仍能看到 `span = hi - lo if hi > lo else 1.0`。
- 当 field_results 或 chunk_results 只有一条时，原始 BM25 分数信号会被压扁，导致单结果场景排序不稳定。

已落地：

1. 在 `es_store.py` 新增 `_normalize_search_scores()`：
   - 多结果：保留 min-max。
   - 单结果：用 sigmoid 按原始 BM25 分数生成可比较分数。
   - 同时保留 `raw_score`，便于后续调试和融合解释。
2. 已替换 `search_bm25()` 的 field/chunk 子通道归一化。
3. 已同步 `search_structured()` 的 unit/anchor 子通道归一化，避免同类问题重复出现。
4. 增加单元测试：
   - 单条高 BM25 分数不能被压成低质量分。
   - 单条低 BM25 分数不能和高分结果等价。
   - field/chunk 两个子通道排序稳定。

涉及文件：

- `src/danbao_poc/es_store.py`
- `src/danbao_poc/query.py`
- `tests/test_core_behaviors.py`

验收标准：

- 单结果 BM25 case 分数不再失真。
- 315 题总命中率不下降。
- 反混淆、字段查询、超短查询至少不退化。

### P0-2. LLM Query Enhancement 条件化做回归确认

状态：已完成核心能力和离线 guard 模拟。

来源：

- `accuracy_optimization_recommendations.md` 修复 2。
- `OPTIMIZATION_PLAN.md` 2.1。

当前状态：

- `retrieve_service.py:_query_rewrite_guard()` 已经存在。
- 短查询、明确字段查询默认不走 LLM 改写。

已落地：

1. `retrieve_service.py:_query_rewrite_guard()` 新增产品/范围锚点保护：
   - `scope_anchor_candidates` 命中时，默认 120 字以内不走 LLM 改写。
   - 返回 reason：`scope_anchor_detected`。
2. guard 判定顺序已调整为：
   - 明确产品/范围锚点优先。
   - 极短查询仍归为 `short_query`。
   - 明确字段查询归为 `exact_field_query`。
3. `tests/run_category_accuracy_baseline.py` 已记录 315 题 guard 模拟：
   - 走启发式的数量。
   - 走 LLM 改写的数量。
   - 每个 reason 的数量。
   - 每类问题的跳过/使用模型分布。
4. 当前模拟结果：
   - 使用模型：0/315。
   - 跳过模型：315/315。
   - `scope_anchor_detected`：176。
   - `short_query`：139。
5. 报告里写入的 guard reason：
   - `short_query`
   - `exact_field_query`
   - `scope_anchor_detected`
   - `forced`
   - `long_or_complex_query`

涉及文件：

- `src/danbao_poc/api/retrieve_service.py`
- `src/danbao_poc/query.py`
- `tests/run_category_accuracy_baseline.py`

验收标准：

- LLM 改写开启时不能低于纯启发式 baseline。
- 超短查询、口语查询、反混淆类不能因改写下降。

### P0-3. 多通道融合权重重新校准

状态：已完成可切换策略入口，仍需在线跑 315 题选最终默认值。

来源：

- `accuracy_optimization_recommendations.md` 修复 3。
- `OPTIMIZATION_PLAN.md` 2.2。

当前状态：

- `query.py` 已默认 `weighted_rrf`。
- 已在 `query.py` 新增 `FUSION_WEIGHT_PRESETS`，把文档里建议的几套权重做成可切换 preset。
- 但 business_plan、governance_rule 的最终默认 route 权重仍需要按 315 题验证后再固化。

已落地：

1. 新增可切换检索策略：
   - `baseline_current`
   - `bm25_vector_stronger`
   - `graph_structured_lower`
   - `qa_boosted`
2. `resolve_weighted_rrf_config()` 支持两种配置入口：
   - 请求级：`options.fusion.weight_preset`
   - MySQL 级：`kb_retrieval_strategy_config` 里的 `fusion.weight_preset` 或 `fusion_weight_preset`
3. 权重合并优先级：
   - 代码默认权重。
   - MySQL preset。
   - MySQL 显式 `weights`。
   - 请求级 preset。
   - 请求级显式 `weights`。
4. business_plan/guarantee_plan 的 preset 已按计划：
   - 降低 `structured`、`graph`。
   - 提高 `bm25`、`vector`、`qa`。
5. governance_rule 的 preset 已单独处理：
   - `section_summary`、`bm25`、`section_path` 相关权重更高。
   - `graph` 权重明显降低，避免制度类普通问答被关系图噪声抢排序。
6. `tests/ablation_test.py` 已加入 4 个 fusion preset 消融配置，后续可直接跑每套权重。
7. 增加单元测试，确认 `graph_structured_lower` 能降低 noisy routes，并保留 QA/BM25/vector 的相对优势。

下一步验证：

1. 每套权重跑 315 题，按品类对比。
2. 如果 `graph_structured_lower` 在反混淆、制度文件、跨库混合上更稳，再考虑设为 business_plan 或 governance_rule 的默认 preset。
3. 如果 QA 库证据质量未达标，不要默认使用 `qa_boosted`，只保留为实验开关。

涉及文件：

- `src/danbao_poc/query.py`
- `src/danbao_poc/retrieval_plan.py`
- MySQL `kb_retrieval_strategy_config`
- `tests/ablation_test.py`

验收标准：

- 总命中率提升，且最差品类不恶化。
- graph/structured 不能再出现“去掉反而更好”的明显噪声。

---

## 4. Phase 2：产品锚定、口语查询、对比查询

### P1-1. 产品名到文件的强锚定

状态：已完成第一阶段，是下一轮准确率最大单项；仍需重建索引后跑 315 题反混淆回归。

来源：

- `accuracy_optimization_recommendations.md` 核心优化 1。
- `OPTIMIZATION_PLAN.md` 2.4。

当前问题：

- `query.py` 有 `KNOWN_PRODUCT_NAMES`，但主要用于 scope anchor 识别。
- ES chunk/field/QA/section_summary 索引还没有统一的 `product_names` 字段。
- 用户问“加工贷反担保措施”时，系统容易返回其他产品的反担保内容。

已落地：

1. 新增 `product_name_extractor.py`：
   - 从文件名提取产品名。
   - 从 metadata 的 `product_names`、`product_name`、`plan_name` 提取产品名。
   - 正则识别 `X贷`、`X保`、`X方案`。
   - 维护别名：如 `加工贷` <-> `鲁担惠农贷_加工贷` / `鲁担惠农贷加工贷`。
2. 检索时已增强产品锚定：
   - `_resolve_scope_anchor_file_filter()` 不只匹配文件名，也匹配 metadata 里的 `product_names`。
   - `_apply_document_and_field_scoring()` 使用产品别名做文档 boost/penalty。
   - debug 中返回 `product_names`、`matched_product_names`、`matched_anchors`。
3. ES mapping 已增加：
   - chunk：`product_names keyword`
   - field：`product_names keyword`
   - QA：`product_names keyword`
   - section_summary：`product_names keyword`
4. ES 写入时已填充 `product_names`：
   - chunk 从 `doc_name`、`title`、chunk metadata 提取。
   - field 从 `doc_name`、`plan_name/product_name` 字段值、metadata 提取。
   - QA 从 `doc_name`、`question`、metadata 提取。
   - section_summary 从 `doc_name`、`section_title`、`section_path`、结构化 summary 提取。
5. 已增加单元测试：
   - 产品名提取能展开 `加工贷` 与 `鲁担惠农贷加工贷` 别名。
   - scope anchor filter 能通过 metadata product_names 命中文件。
   - 文档打分能用产品别名 boost 正确产品、penalty 错误产品。

还需要验证：

1. 重建 ES 索引，使新增 `product_names` 字段进入线上索引。
2. 跑 315 题，重点看 `反混淆`、`精确产品`、`跨产品对比`。
3. 如果反混淆仍不稳，再把 `product_names` 加入 ES query 的 should boost 或 filter-first 强约束。

涉及文件：

- `src/danbao_poc/query.py`
- `src/danbao_poc/es_store.py`
- `src/danbao_poc/mysql_store.py`
- `src/danbao_poc/api/retrieve_service.py`
- `tests/test_core_behaviors.py`
- 315 题反混淆测试集

验收标准：

- 反混淆类正确率明显提升。
- 问到明确产品名时，top1 文件必须优先命中对应产品文件。
- 没有产品名的问题不能被错误过滤。

### P1-2. 超短/口语查询同义词扩展

状态：已完成第一阶段，纯代码改动，不需要数据库变更。

来源：

- `OPTIMIZATION_PLAN.md` 2.6。

当前问题：

- “几个点”“能贷多少”“抵押”“还不上”“多久”这类口语词需要映射到正式字段。
- 只靠 LLM 改写风险高，容易把精确短词改泛。

已落地：

1. 新增 `query_expansion.py`：
   - `COLLOQUIAL_SYNONYMS`
   - `expand_colloquial_query()`
   - `build_expanded_query_text()`
2. 扩展输出已进入 `heuristic_query_understanding()`：
   - `expanded_terms`
   - `expanded_field_codes`
   - `expansion_reason`
   - `matched_colloquial_terms`
3. 检索时已把扩展词用于：
   - BM25 query text。
   - section_summary possible_questions。
   - QA extended_questions。
   - structured unit/anchor。
4. 保留原 query 高权重，扩展词低权重：
   - 原 query boost 默认 3.0。
   - 扩展词 boost 默认 0.75。
   - 使用 `should + minimum_should_match=1`，避免原口语词无命中时直接召回失败。
5. 已增加单元测试：
   - “强村贷几个点？”不改写原 query，但扩展出 `担保费率`。
   - BM25 的扩展词作为低权重 should clause，不覆盖原 query。

建议词表示例：

| 口语词 | 扩展词 |
|---|---|
| 利息、几个点 | 担保费率、费率、利率 |
| 抵押 | 反担保、担保物、抵押物 |
| 能贷多少 | 额度、授信额度、最高额度 |
| 多久 | 期限、授信期限、担保期限 |
| 还不上 | 追偿、风险缓释、逾期 |
| 怎么办 | 办理流程、申请流程、材料 |

涉及文件：

- `src/danbao_poc/query.py`
- `src/danbao_poc/query_expansion.py`
- `src/danbao_poc/es_store.py`
- `tests/test_core_behaviors.py`

验收标准：

- 超短/口语类命中率提升。
- 扩展词只作为召回增强，不覆盖原 query。

### P1-3. 跨文档对比查询聚合

状态：已完成第一阶段，纯代码改动，不需要数据库变更；仍需 315 题对比类回归。

来源：

- `OPTIMIZATION_PLAN.md` 2.9。

当前状态：

- `retrieve_service.py` 已有 `cross_doc_query` 和 diversity 基础逻辑。
- 但“农耕贷和农贸贷分别是什么期限”这类对比查询，还需要保证每个产品至少保留一个 evidence group。

已落地：

1. `query.py` 已增加：
   - `comparison_query=True`
   - `comparison_anchors`
   - `comparison_fields`
   - `comparison_markers`
2. 检索时已处理：
   - 多产品对比查询自动提高 `recall_top_k`。
   - 对比标记包括 `对比`、`比较`、`区别`、`分别`、`各自`、`和`、`与`。
3. evidence group 阶段已增加 `_apply_comparison_anchor_coverage()`：
   - 根据产品锚点和文件名/产品名别名匹配 evidence group。
   - 每个对比产品尽量保留 1 个 group。
   - 缺哪个产品就明确写入 debug，不混用其他产品内容。
4. debug 响应增加：
   - `comparison_groups`
   - `missing_comparison_targets`
   - `covered_anchors`
5. 已增加单元测试：
   - “农耕贷和农贸贷分别是什么期限？”能识别为 comparison query。
   - evidence group 重排能保留每个产品至少一条证据。

涉及文件：

- `src/danbao_poc/query.py`
- `src/danbao_poc/api/retrieve_service.py`
- `src/danbao_poc/query.py:build_evidence_groups()`
- 315 题对比类测试集

验收标准：

- 对比类不再只返回一个产品。
- 如果某个产品没有证据，要明确返回缺失，而不是混用其他产品内容。

---

## 5. Phase 3：制度文件 profile 专项

### P1-4. governance_rule 开启可控图检索

状态：已完成第一阶段，纯代码改动，不需要数据库变更；仍需制度类 315 题回归确认图谱是否带来收益。

来源：

- `accuracy_optimization_recommendations.md` 核心优化 2。
- `OPTIMIZATION_PLAN.md` 2.7。

当前问题：

- `retrieval_plan.py` 的 governance_rule 默认 modes 仍没有 graph。
- `query.py:_graph_enabled_profile()` 仍需要确认是否只允许 business_plan。
- 制度类查询错率高，章节/条款/职责/权限关系检索需要图谱或结构关系辅助。

已落地：

1. `_graph_enabled_profile()` 已支持：
   - `business_plan`
   - `governance_rule`
2. `PROFILE_DEFAULT_MODES["governance_rule"]` 已增加 `graph`，但 `RetrievalPlanBuilder` 会在非关系意图时移除 graph。
3. governance_rule 图谱 Schema 已限定：
   - `RuleDocument`
   - `Chapter`
   - `Clause`
   - `Role`
   - `Responsibility`
   - `Decision`
4. 关系限定已加入 `graph_intent.py`：
   - `HAS_CHAPTER`
   - `HAS_CLAUSE`
   - `ASSIGNS_RESPONSIBILITY`
   - `REQUIRES_APPROVAL`
   - `REFERENCES_RULE`
5. graph 查询不参与所有制度问题，只在以下意图参与：
   - 职责是谁
   - 哪条规定
   - 哪个章节
   - 需要谁审批
   - 引用了哪个制度
6. 已增加单元测试：
   - 普通制度内容问法不启用 graph。
   - “哪个部门负责审批”这类职责/审批关系意图启用 graph。

涉及文件：

- `src/danbao_poc/query.py`
- `src/danbao_poc/retrieval_plan.py`
- `src/danbao_poc/graph_builder.py`
- `src/danbao_poc/graph_writer.py`
- `src/danbao_poc/knowledge_extractor.py`

验收标准：

- 制度类正确率提升。
- graph 通道不能在制度类产生明显噪声。

### P1-5. governance_rule BM25 字段权重和章节别名优化

状态：已完成第一阶段，纯代码改动，不需要数据库变更；仍需制度类回归确认。

来源：

- `accuracy_optimization_recommendations.md` 核心优化 2。
- `OPTIMIZATION_PLAN.md` 2.7。

当前问题：

- 制度类最重要的是章节路径、条款标题、条号，但默认权重仍偏文档名和正文。
- 口语制度查询无法稳定映射到章节类型。

已落地：

1. 在 `search_bm25()` 根据 profile 切换字段权重：
   - `section_path_text_tks^6`
   - `title_tks^4`
   - `doc_name_tks^3`
   - `keywords_tks^3`
   - `content_for_bm25_tks^2`
2. `search_section_summary()` 对 governance_rule 也提高章节路径和章节标题权重。
3. 扩展 governance section aliases：
   - 职责、职权、权限
   - 处罚、追责、责任追究
   - 任命、聘任、选举
   - 会议、议事规则、表决
   - 财务、资金、预算、大额资金
   - 审批、授权、决策
4. 对 “第几章/第几条/第几款” 增加规则识别：
   - 直接 boost section_path/title。
   - 必要时按条号过滤。
5. 已增加单元测试：
   - governance_rule BM25 使用 `section_path_text_tks^6`、`title_tks^4`、`doc_name_tks^3`。

涉及文件：

- `src/danbao_poc/es_store.py`
- `src/danbao_poc/chunker.py`
- `src/danbao_poc/profiles/field_aliases.py`
- `src/danbao_poc/profiles/registry.py`

验收标准：

- 制度刁难、制度模糊、制度文件三类正确率提升。
- 条号类问题 top1 必须更靠近正确章节。

---

## 6. Phase 4：证据对齐、坐标追溯、分块质量

### P1-6. LCS 双门控证据对齐

状态：已完成第一阶段，纯代码改动，不需要数据库变更；仍需解析批次回归确认误对齐下降。

来源：

- `OPTIMIZATION_PLAN.md` 2.8。
- LangExtract。

当前问题：

- `evidence_aligner.py` 仍基于 `SequenceMatcher`。
- 对短句、重复词、弱相似句可能有假阳性。

已落地：

1. 新增 LCS token/char span 算法：
   - coverage gate：匹配 token 数 >= extraction token 数 * 0.75。
   - density gate：匹配 token 数 / source span 长度 >= 0.33。
2. 输出更细状态：
   - `exact`
   - `normalized_exact`
   - `lcs_aligned`
   - `fuzzy_aligned`
   - `failed`
3. `EvidenceAlignment` 已增加：
   - `method`
   - `matched_units`
   - `source_span_units`
   - `false_positive_suspect`
4. 字段、QA、知识单元继续使用同一 `align_quote_to_text()`。
5. parse report 已增加：
   - `lcs_alignment_rate`
   - `alignment_false_positive_suspect_count`
6. 已增加单元测试：
   - exact/normalized exact 不退化。
   - 可接受的非连续证据返回 `lcs_aligned`。
   - 稀疏 LCS 假阳性被拒绝并标记 `false_positive_suspect`。

涉及文件：

- `src/danbao_poc/evidence_aligner.py`
- `src/danbao_poc/extractor.py`
- `src/danbao_poc/answer_prebuilder.py`
- `src/danbao_poc/knowledge_extractor.py`
- `src/danbao_poc/api/parse_service.py`

验收标准：

- 对齐假阳性减少。
- 原有 exact/normalized exact 不退化。

### P1-7. 100% 坐标追溯补齐

状态：已完成输出层第一阶段，未改数据库结构；bbox/行级映射闭环仍需端到端验证。

来源：

- `OPTIMIZATION_PLAN.md` 2.15。
- KnowFlow。

当前状态：

- 已经有 line span、char map、bbox/positions 的基础字段。
- 但还需要确认前端引用点击、chunk、field、QA、unit 是否都能回到具体页码/行/坐标。

已落地：

1. 标准化 `file_char_map`：
   - `global_line_no`
   - `global_char_start/end`
   - `page_no`
   - `block_id`
   - `line_no`
   - `bbox`
2. evidence group 已保留：
   - `char_start/end`
   - `page_no`
   - `block_ids`
   - `bbox_json`
3. citation 输出中已增加：
   - `char_start/end`
   - `bbox_json`
   - `highlight_mode`
4. `highlight_mode` 规则：
   - 有 bbox 走坐标高亮。
   - 有 char span 走字符区间。
   - 有 block_ids 走块定位。
   - 都没有时走页码定位。
5. 已增加单元测试：
   - citation 能输出 `highlight_mode=bbox`、`char_start/end`、`bbox_json`、页码。

还需要验证：

1. 前端引用点击是否消费 `highlight_mode` 和 `bbox_json`。
2. 线上解析结果中 field/QA/unit 是否都能带出已有 `char_start/end` 和 `bbox_json`。

涉及文件：

- `src/danbao_poc/document_parser.py`
- `src/danbao_poc/paddle_normalizer.py`
- `src/danbao_poc/mysql_store.py`
- `src/danbao_poc/citation_formatter.py`
- `frontend/app.js`

验收标准：

- 每个 citation 至少有页码。
- PDF/图片解析结果尽量有 bbox。
- 前端能点击引用定位到原文区域。

### P1-8. AST 语义分块作为 LLM Planner fallback

状态：已完成第一阶段，纯代码 fallback，不需要数据库变更；仍需用解析失败样本回归确认粗块下降。

来源：

- `OPTIMIZATION_PLAN.md` 2.11。
- KnowFlow。

当前问题：

- LLM Planner 或目录识别失败时，fallback chunk 结构可能变粗。
- Markdown、制度、技术文档可以用 AST/标题规则更稳定地切。

建议改法：

1. [已完成] 新增 `ast_chunker.py`：
   - Markdown AST：使用 `markdown-it-py` 或等价解析。
   - 标题触发边界。
   - 表格、代码块、列表保持完整。
   - 当前实现未新增依赖，先用轻量 Markdown/条款 AST 规则等价落地：识别 `#` 标题、`第X章/节/条`、`一、/1.` 编号标题、代码围栏和 Markdown 表格。
   - 代码块和表格作为 `protected_block=true` 的独立 chunk 输出，避免被 `split_content()` 切碎。
2. [已完成] 在 profile chunker fallback 中接入：
   - project_doc
   - governance_rule
   - general_document
   - 只有 AST fallback 结果比现有 `chunk_by_headers()` 更细，且至少能切出 2 个 chunk 时才替换现有结果。
   - 对制度文档继续复用 `_detect_rule_section_type()`，例如“职责/负责/审批”仍能落到 `responsibility_clause` / `procedure_clause`。
   - 对项目文档继续复用原来的 API、CREATE TABLE、代码块、配置项二次识别逻辑。
3. [已完成] 输出统一字段：
   - `section_path`
   - `chunk_type`
   - `protected_block`
   - `parent_chunk_id`
   - 第一阶段已输出 `section_path`、`chunk_type`、`protected_block`、`protected_block_type`、`fallback_source=markdown_ast`。
   - `parent_chunk_id` 当前不写入，因为 fallback 阶段还没有数据库 chunk id；后续如需要父子块显式关系，应在多粒度 chunk 生成或入库后补。
4. [部分完成] 与现有 `catalog_chunker.py` 的保护块逻辑复用。
   - 已复用同类“保护块不跨边界”的思路。
   - 未直接调用 catalog planner 的边界调整函数，原因是 AST fallback 运行在无 planner 映射结果的场景，先由 AST 单元天然保持表格/代码完整。

涉及文件：

- `src/danbao_poc/ast_chunker.py`
- `src/danbao_poc/catalog_chunker.py`
- `src/danbao_poc/profiles/registry.py`
- `tests/test_core_behaviors.py`

验收标准：

- [已验证] LLM Planner 失败时不会退化成单大块：`general_document` 在单文本块 Markdown 中会切成多段。
- [已验证] 表格、代码块、条款列表不被拆碎：代码围栏和 Markdown 表格会输出保护块。
- [已验证] 制度条款 fallback 后仍保留职责类 section type。

---

## 7. Phase 5：抽取与图谱治理

### P2-1. 多轮提取与重叠解决

状态：已完成第一阶段，纯代码改动，不需要数据库变更；多轮默认仍为 1，线上需通过 `parse_options` 打开后回归成本和收益。

来源：

- `OPTIMIZATION_PLAN.md` 2.10。
- LangExtract。

建议改法：

1. [已完成] 在字段/知识抽取 options 增加：
   - `extraction_passes`
   - `merge_overlaps`
   - 支持 `parse_options.extraction.extraction_passes` 或顶层 `parse_options.extraction_passes`。
   - 支持 `parse_options.extraction.merge_overlaps` 或顶层 `parse_options.merge_overlaps`。
   - pass 上限控制为 3，避免线上成本失控。
2. [已完成] 多轮低温抽取：
   - 第一轮稳态。
   - 第二轮偏召回。
   - 第一轮 temperature=0。
   - 后续 recall pass 使用低温 0.15 起步，最多 0.35。
   - `business_plan` 字段抽取、通用 profile prompt 字段抽取、knowledge structure 抽取均已接入。
3. [已完成] 合并策略：
   - exact evidence 相同：去重。
   - span 重叠：高置信优先。
   - span 不重叠：保留为候选。
   - 已新增 `extraction_merge.py`，按 exact key 去重。
   - 对同字段/同 subject-predicate 的 evidence/value 文本做重叠判断。
   - 重叠时优先保留置信度更高、证据更长的记录。
   - 不重叠的字段或 knowledge unit 保留为候选。
4. [已完成] parse report 展示：
   - pass_count
   - newly_added_count
   - overlap_dropped_count
   - 已输出字段抽取和知识抽取两套指标：
     - `field_extraction_pass_count`
     - `field_extraction_newly_added_count`
     - `field_extraction_overlap_dropped_count`
     - `knowledge_extraction_pass_count`
     - `knowledge_extraction_newly_added_count`
     - `knowledge_extraction_overlap_dropped_count`

涉及文件：

- `src/danbao_poc/extractor.py`
- `src/danbao_poc/knowledge_extractor.py`
- `src/danbao_poc/api/parse_service.py`

验收标准：

- [待线上回归] 知识提取召回提升：需要用 `extraction_passes=2` 重跑样本集对比。
- [已加防线] 不明显增加错误字段和错误关系：exact 去重、重叠证据降噪、parse report 指标已接入，仍需人工 spot check。

### P2-2. 中文正则关系模式补全

状态：已完成第一阶段，纯代码改动，不需要数据库变更；仍需用制度/担保样本 spot check 误触发率。

来源：

- `OPTIMIZATION_PLAN.md` 2.12。
- GraphRAG-Example。

当前状态：

- 已有 `relation_rule_extractor.py`，已扩展中文 pattern。

建议补充：

- [已完成] 属于/隶属于/归属于：映射 `belongs_to`。
- [已完成] 包含/包括/涵盖/由...组成：映射 `contains`。
- [已完成] 负责/承担/履行职责：映射 `responsible_for`。
- [已完成] 审批/批准/备案：映射 `approves`。
- [已完成] 禁止/不得/限制：区分 `excludes_industry` 和 `prohibits`。
- [已完成] 支持/适用于/面向：映射 `applies_to`。
- [已完成] 引用/依据/按照：映射 `references`。
- [已完成] 简称/又称/也叫：映射 `alias_of`。
- [已完成] 依赖/基于/前置：映射 `depends_on`。

涉及文件：

- `src/danbao_poc/relation_rule_extractor.py`
- `src/danbao_poc/knowledge_extractor.py`
- `tests/test_core_behaviors.py`

验收标准：

- [已验证] 规则关系只补召回，不覆盖 LLM 高可信结果：同 from/to pair 已存在时不再补规则关系。
- [待样本回归] 不在制度/担保两类 profile 间误抽关系：已补模式单测，仍需线上制度/担保样本 spot check。

### P2-3. 受约束图 Schema 再收紧

状态：已完成第一阶段，纯代码改动，不需要数据库 DDL；Neo4j 真实写入仍需后续用线上图谱样本验证。

来源：

- `OPTIMIZATION_PLAN.md` 2.13。
- DataGraphX。

当前状态：

- `knowledge_extractor.py` 已有 profile 约束和关系校验。
- 还需要让 graph_builder、Neo4j 写入、graph_query 三者共用同一 Schema。

建议改法：

1. [已完成] 新增 `graph_schema.py`：
   - `ALLOWED_NODE_TYPES_BY_PROFILE`
   - `ALLOWED_RELATION_TYPES_BY_PROFILE`
   - `RELATION_WEIGHT_BY_TYPE`
   - `PROFILE_GRAPH_QUERY_INTENTS`
   - 同时补充了 `ALLOWED_GRAPH_EDGE_TYPES_BY_PROFILE`，用于 Neo4j 边类型过滤。
2. [已完成第一阶段] `knowledge_extractor.py`、`graph_builder.py`、`graph_writer.py`、`query.py` 统一引用。
   - `knowledge_extractor.py` 按 profile 校验 relation_type，不合规则写 warning 并跳过。
   - `graph_builder.py` 通过 `filter_graph_records()` 过滤非法 node/edge。
   - `graph_writer.py` 的权重改为引用 `RELATION_WEIGHT_BY_TYPE`。
   - `query.py` / `graph_intent.py` 改为从 `PROFILE_GRAPH_QUERY_INTENTS` 读取可用图关系。
3. [已完成第一阶段] 不在 Schema 内的关系：
   - parse 阶段作为 warning。
   - 不写 Neo4j。
   - 不进 graph query。
   - 当前知识关系会输出 `relation_schema_rejected:*` warning。
   - 当前 graph builder 会输出 `graph_node_schema_rejected:*`、`graph_edge_schema_rejected:*` warning。
   - graph query 已按 profile 过滤关系意图；当前 Neo4j 查询实现仍只支持 `BusinessPlan` 图，非业务图会直接降级为空结果。

涉及文件：

- `src/danbao_poc/graph_schema.py`
- `src/danbao_poc/knowledge_extractor.py`
- `src/danbao_poc/graph_builder.py`
- `src/danbao_poc/graph_writer.py`
- `src/danbao_poc/query.py`

验收标准：

- [待线上回归] 图通道噪声下降：需要用真实 Neo4j 图谱和制度/业务样本验证。
- [已验证] Schema 变更只改一个文件：新增 schema 单测覆盖 profile relation 白名单、graph node/edge 过滤和 graph query intent。

### P2-4. Anchor 五阶段去重与审核闭环

状态：已完成候选生成第一阶段；审核回写涉及数据库/ES/Neo4j，已单独记录，暂未直接改库。

来源：

- `OPTIMIZATION_PLAN.md` 2.14。
- Graphify。

当前状态：

- 已有 `anchor_deduper.py` 精确合并和模糊候选。
- 已有 `knowledge_anchor_merge_candidate` 候选池。
- 还没有 MinHash/LSH、熵门控、LLM 仲裁和审核回写。

建议开发：

1. [已完成] Stage 1：精确归一化合并，已完成。
2. [已完成] Stage 2：低熵标签跳过模糊匹配。
   - 当前 `_ENTROPY_THRESHOLD=1.2`，如“额度”“费率”这类低熵短标签不进入模糊候选，避免泛词互相误合并。
3. [已完成第一阶段] Stage 3：MinHash/LSH 生成候选。
   - 新增 deterministic MinHash signature，不引入外部依赖。
   - 使用 band bucket 做候选召回，再补充短后缀包含关系 block，例如“鲁担惠农贷”和“鲁担惠农贷产品”。
4. [已完成第一阶段] Stage 4：Jaro-Winkler 或当前相似度验证。
   - 当前继续使用现有 Jaccard/SequenceMatcher 综合分数。
   - 包含型高相似名称给 0.9 候选分，仍低于自动合并阈值。
5. [部分完成] Stage 5：LLM/人工仲裁 ambiguous pair。
   - 当前会输出 `pending_review` / `auto_accept` 决策字段。
   - 暂未接 LLM 仲裁接口和人工审核服务。
6. [未执行，需数据库/索引专项] 审核通过后回写：
   - anchor alias。
   - unit anchor_id。
   - relation from/to。
   - ES anchor/unit。
   - Neo4j 节点。

涉及文件：

- `src/danbao_poc/anchor_deduper.py`
- `src/danbao_poc/mysql_store.py`
- `src/danbao_poc/api/retrieve_service.py` 或新增 `anchor_merge_service.py`
- `src/danbao_poc/es_store.py`
- `src/danbao_poc/graph_writer.py`

验收标准：

- [部分满足] 候选可审核：已有 `knowledge_anchor_merge_candidate` 候选输出；合并和回滚服务未做。
- [已验证] 高风险候选不能自动合并：MinHash/LSH 召回出的 0.9 相似候选仍进入 `pending_review`。

### P2-5. chunk 级增量索引和局部图谱重建

状态：部分完成。

来源：

- `accuracy_optimization_recommendations.md` 和 `09` 的增量索引延伸。

当前状态：

- 已完成代际级 `reuse_previous`。
- 但还没做到 chunk 级 diff/upsert。

建议改法：

1. 增加 index hash 对照：
   - `chunk_id`
   - `content_hash`
   - `indexed_hash`
   - `graph_hash`
2. ES：
   - 未变 chunk 跳过。
   - 变更 chunk 局部 upsert。
   - 删除 chunk 执行 delete_by_query。
3. Neo4j：
   - 删除当前 chunk 相关旧关系。
   - 只重建变更 chunk 的 field/anchor/unit/relation。
4. 报告增加：
   - `index_skipped_unchanged_count`
   - `incremental_changed_chunk_count`
   - `graph_skipped_unchanged_count`

涉及文件：

- `src/danbao_poc/index_incremental.py`
- `src/danbao_poc/es_store.py`
- `src/danbao_poc/graph_writer.py`
- `src/danbao_poc/mysql_store.py`
- `src/danbao_poc/api/retrieve_service.py`

验收标准：

- 小改一个 chunk 不触发全文件重建。
- 索引指针和 Neo4j 数据不出现新旧混杂。

---

## 8. Phase 6：高级检索与回答可追溯

### P3-1. 稀疏向量检索

状态：未开始，建议暂缓。

来源：

- `OPTIMIZATION_PLAN.md` 2.16。
- RAG-Pro。

为什么暂缓：

- 两份文档也强调当前瓶颈主要在路由、锚定、融合和证据，不是 embedding 模型。
- 稀疏向量依赖模型和部署，工程成本高。

建议触发条件：

- 完成 P0/P1 后仍有大量精确关键词问题召回失败。
- 有可用 BGE-M3 或等价 sparse vector 能力。

涉及文件：

- `src/danbao_poc/es_store.py`
- `src/danbao_poc/openai_compat.py`
- `src/danbao_poc/query.py`

验收标准：

- 只作为新增 sparse route，不替换现有 BM25。
- 必须通过 RRF 融合，不能直接靠 sparse 分数压制其他通道。

### P3-2. 自动引用插入与答案引用校验

状态：部分完成，需要接真实回答生成链路。

来源：

- `OPTIMIZATION_PLAN.md` 2.17。
- KnowFlow。

当前状态：

- 已有 `answer_context_protocol.py`，可以生成 `[ref_n]` prompt。
- 但如果后续接 LLM 生成答案，还需要校验答案里的引用。

建议改法：

1. 回答生成时强制使用 `answer_context_prompt`。
2. 生成后解析所有 `[ref_n]`：
   - 不存在的 ref 删除或重写。
   - 没引用的事实句标记为 unsupported。
3. 如果答案没有任何引用：
   - 降低 confidence。
   - 返回 warning。
4. 前端点击答案内 `[ref_n]` 定位 evidence group。

涉及文件：

- `src/danbao_poc/answer_context_protocol.py`
- `src/danbao_poc/citation_formatter.py`
- `src/danbao_poc/api/retrieve_service.py`
- `frontend/app.js`

验收标准：

- 答案中的每个 `[ref_n]` 都能反查 citation。
- 不允许模型引用不存在的 ref。

---

## 9. 不建议本轮做的事

两份文档都提醒不要过早做高成本替换。本轮不建议：

| 暂不做 | 原因 |
|---|---|
| 更换 embedding 模型 | 当前主要瓶颈不是向量质量 |
| 引入 Milvus | ES 当前足够，迁移成本高 |
| fine-tune reranker | 需要标注集，ROI 暂时低 |
| 直接上复杂五阶段全自动实体合并 | 先做候选审核闭环，避免错合并 |
| 稀疏向量作为主检索 | 依赖模型和部署，先作为 P3 |
| 大规模前端重做 | 前端调试面板已具备基础能力，准确率优先 |

---

## 10. 建议执行顺序

### 第一批：必须先做，避免盲调

1. [已完成] A0 分品类 baseline：已新增脚本和 json/md 报告，当前 danbao-poc 有效命中 252/315，80.0%。
2. [已完成] P0-1 BM25 子通道归一化修复：已保留单结果 raw_score，并用 sigmoid 避免分数被压平。
3. [已完成] P0-2 Query Enhancement guard 阈值回归：已加入 scope anchor guard，并在 baseline 报告输出 guard reason 分布。
4. [已完成执行入口] P0-3 多通道权重校准：已新增 4 套 fusion preset 和消融配置，下一步需要在线跑 315 题决定默认权重。

### 第二批：最大准确率收益

5. [已完成第一阶段] P1-1 产品名到文件强锚定：已新增产品名提取、别名匹配、ES `product_names` 字段和文档打分增强；下一步重建索引后回归。
6. [已完成第一阶段] P1-2 超短/口语查询扩展：已新增口语同义词扩展，扩展词低权重参与 BM25/structured/section_summary/QA 召回。
7. [已完成第一阶段] P1-3 跨文档对比查询聚合：已识别 comparison anchors/fields，提高召回量，并按产品锚点做 evidence group 保底。
8. [已完成第一阶段] P1-4/P1-5 governance_rule 专项：制度图谱改成关系意图触发，BM25/section_summary 改成章节路径和标题优先。

### 第三批：证据和分块质量

9. [已完成第一阶段] P1-6 LCS 双门控证据对齐：已新增 LCS coverage/density 双门控、对齐状态和 parse report 指标。
10. [已完成输出层第一阶段] P1-7 100% 坐标追溯：citation 已输出 char/bbox/block/highlight_mode，前端点击和线上数据完整性待验证。
11. [已完成第一阶段] P1-8 AST 语义分块 fallback：已新增轻量 Markdown/条款 AST 分块，接入 general/governance/project profile，保护代码块和表格不被拆碎。

### 第四批：图谱和抽取增强

12. [已完成第一阶段] P2-1 多轮提取：已支持字段/知识抽取多 pass、exact 去重、重叠证据降噪和 parse report 指标；默认仍为单 pass，需按样本开启回归。
13. [已完成第一阶段] P2-2 中文正则关系补全：已扩展 belongs_to/contains/responsible_for/approves/prohibits/applies_to/references/alias_of/depends_on 等中文模式，并保留不覆盖已有关系的保护。
14. [已完成第一阶段] P2-3 受约束图 Schema 统一：已新增 `graph_schema.py`，集中维护节点类型、关系白名单、边权重和 graph query intent，并接入 knowledge/graph/query 主要链路。
15. [已完成候选生成第一阶段] P2-4 Anchor 五阶段去重与审核闭环：已补低熵门控、MinHash/LSH 候选生成和高风险 pending review；审核通过后的数据库/ES/Neo4j 回写需单独开发。
16. P2-5 chunk 级增量索引和局部图谱重建。

### 第五批：高级能力

17. P3-1 稀疏向量检索。
18. P3-2 自动引用插入与答案引用校验。

---

## 11. 验收总表

| 阶段 | 核心验收 |
|---|---|
| A0 | 315 题能输出分品类 baseline |
| P0 | 总命中率提升到 83% 以上，且无重点品类明显下降 |
| P1 | 反混淆、制度类、口语类、对比类都有专项提升 |
| P2 | 证据对齐更稳，图谱噪声下降，Anchor 可审核治理 |
| P3 | 仅在 P0/P1/P2 后仍有瓶颈时启用 |

保守目标：

- 第一批完成：80% -> 83%~86%。
- 第二批完成：86% -> 88%~92%。
- 第三、四批完成：向 90%+ 稳定推进。

注意：两份文档都提到收益不能简单相加。实际目标应以分品类 baseline 和每次回归报告为准。
