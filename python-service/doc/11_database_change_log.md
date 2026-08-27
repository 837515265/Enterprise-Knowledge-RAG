# 数据库与索引变更记录

> 这里专门记录需要数据库、ES mapping、索引重建或线上数据迁移配合的事项。纯 Python 逻辑改动不放在这里。

## 1. P1-1 产品名强锚定

状态：代码已接入，线上需要重建索引后生效。

### 已在代码中使用的字段

- ES `knowledge_chunks_v1.product_names`
- ES `knowledge_fields_v1.product_names`
- ES `knowledge_qa_v1.product_names`
- ES `section_summary_v1.product_names`

字段类型：

```json
{"type": "keyword"}
```

用途：

- 保存文件、chunk、字段、QA、章节摘要对应的产品名和产品别名。
- 支撑“加工贷反担保措施”这类精确产品查询的强过滤、boost 和 debug。

### 当前是否需要 MySQL DDL

当前阶段不需要新增 MySQL 列。

原因：

- 代码优先复用已有 JSON 字段：
  - `kb_file_node.metadata_json.product_names`
  - `kb_chunk.metadata_json.product_names`
  - `kb_qa_pair.metadata_json.product_names`
  - 结构化 summary JSON 中的产品信息
- 如果这些 JSON 中没有产品名，索引阶段会从 `doc_name`、`title`、`question`、`section_path` 等文本中提取。

### 线上执行要求

1. 确认 `ensure_indices()` 已执行，让 ES mapping patch 生效。
2. 对已有文件重建 ES 索引，否则旧文档不会自动拥有 `product_names`。
3. 重建后跑 315 题，重点看：
   - `反混淆`
   - `精确产品`
   - `跨产品对比`

### 后续可选 MySQL 增强

如果产品名治理需要人工审核，可以再考虑新增结构化字段或表：

```sql
ALTER TABLE kb_file_node ADD COLUMN product_names_json JSON DEFAULT NULL;
```

当前不建议马上加，先用 metadata_json 和 ES 字段验证准确率收益。

## 2. P1-2 超短/口语查询扩展

状态：纯代码改动，不需要数据库变更。

说明：

- 新增 `query_expansion.py` 维护口语同义词表。
- 检索时扩展词作为低权重 should clause，不写库。
- 不需要 ES mapping 变更。

## 3. P0-3 多通道融合权重 preset

状态：纯代码改动，不需要数据库 DDL。

可选配置位置：

- 请求级：`options.fusion.weight_preset`
- MySQL 策略配置：`kb_retrieval_strategy_config.config_json.fusion.weight_preset`
- MySQL 策略配置：`kb_retrieval_strategy_config.config_json.fusion_weight_preset`

可选值：

- `baseline_current`
- `bm25_vector_stronger`
- `graph_structured_lower`
- `qa_boosted`

如果要把某套 preset 固化为线上策略，只需要更新策略 JSON，不需要改表结构。

## 4. P1-3 跨文档对比查询聚合

状态：纯代码改动，不需要数据库变更。

说明：

- `query.py` 输出 `comparison_query`、`comparison_anchors`、`comparison_fields`。
- `retrieve_service.py` 根据对比锚点提高召回量，并在 evidence group 阶段做产品覆盖保底。
- 不需要 MySQL DDL。
- 不需要 ES mapping 变更。

## 5. P1-4/P1-5 governance_rule 制度专项

状态：纯代码改动，不需要数据库变更。

说明：

- `governance_rule` 的 graph 路由只在职责、审批、章节、条款、引用等关系意图命中时启用。
- `search_bm25()` 和 `search_section_summary()` 按 profile 使用制度类字段权重。
- governance aliases 和 section type 判断在代码中扩展。
- 不需要 MySQL DDL。
- 不需要 ES mapping 变更。

## 6. P1-6 LCS 双门控证据对齐

状态：纯代码改动，不需要数据库变更。

说明：

- `EvidenceAlignment` 的 `to_dict()` 会多输出 `method`、`matched_units`、`source_span_units`、`false_positive_suspect`。
- 这些字段进入已有 metadata JSON，不需要新增 MySQL 列。
- parse report 多了 `lcs_alignment_rate` 和 `alignment_false_positive_suspect_count`。
- 不需要 MySQL DDL。
- 不需要 ES mapping 变更。

## 7. P1-7 citation 坐标追溯输出

状态：当前代码改动不需要数据库变更，但依赖已有数据字段的完整性。

已使用的已有字段：

- `char_start`
- `char_end`
- `page_no` / `page_start` / `page_end`
- `block_ids`
- `bbox_json`

说明：

- citation 现在输出 `char_start/end`、`block_ids`、`bbox_json`、`highlight_mode`。
- 当前没有新增 MySQL 列。
- 如果线上历史 evidence 缺少这些字段，需要通过重跑解析/抽取/索引来补齐数据，而不是改表。

后续可能需要前端改动：

- 前端引用点击优先按 `highlight_mode=bbox` 使用 `bbox_json` 高亮。
- 缺少 bbox 时降级到 `char_span`、`block` 或 `page`。

## 8. P1-8 AST 语义分块 fallback

状态：纯代码改动，不需要数据库变更。

说明：

- 新增 `ast_chunker.py`，在 LLM Planner/目录识别失败或现有标题分块过粗时，按 Markdown 标题、制度条款标题、编号标题进行 fallback 分块。
- `general_document`、`governance_rule`、`project_doc` 已接入 fallback。
- 表格和代码块作为保护块输出：
  - `metadata.protected_block=true`
  - `metadata.protected_block_type=table/code`
  - `metadata.fallback_source=markdown_ast`
- 不需要 MySQL DDL。
- 不需要 ES mapping 变更。

线上注意：

- 新逻辑只影响后续解析/重解析产生的 chunk。
- 如果希望历史文件也受益，需要对相关文件重跑解析和索引。

## 9. P2-1 多轮提取与重叠解决

状态：纯代码改动，不需要数据库变更。

说明：

- 新增 `extraction_merge.py`，用于多轮抽取结果合并：
  - exact evidence 相同去重。
  - 同字段/同 subject-predicate 的 evidence/value 重叠时，保留置信度更高、证据更长的记录。
  - 不重叠的候选保留，避免压掉第二轮新增召回。
- 字段抽取和 knowledge structure 抽取支持：
  - `parse_options.extraction.extraction_passes`
  - `parse_options.extraction.merge_overlaps`
  - 顶层兼容：`parse_options.extraction_passes`、`parse_options.merge_overlaps`
- parse report 增加多轮抽取指标：
  - `field_extraction_pass_count`
  - `field_extraction_newly_added_count`
  - `field_extraction_overlap_dropped_count`
  - `knowledge_extraction_pass_count`
  - `knowledge_extraction_newly_added_count`
  - `knowledge_extraction_overlap_dropped_count`

当前是否需要 MySQL DDL：

当前不需要。

原因：

- 新增指标写入已有解析过程产物和返回 JSON。
- 字段、anchor、unit、relation 的最终结构仍走现有表结构和 JSON metadata。
- `parse_options` 本来已经进入解析缓存 identity；开启多 pass 后会形成不同 `parse_options_hash`，不会污染单 pass 缓存。

线上注意：

- 默认仍是单 pass，避免立刻增加 LLM 调用成本。
- 如果要验证收益，可对小样本设置：

```json
{
  "extraction": {
    "extraction_passes": 2,
    "merge_overlaps": true
  }
}
```

- 开启后需要观察：
  - 新增召回是否来自第二轮。
  - `overlap_dropped_count` 是否过高。
  - 错误字段、错误 relation 是否增加。

## 10. P2-2 中文正则关系模式补全

状态：纯代码改动，不需要数据库变更。

说明：

- 扩展 `relation_rule_extractor.py` 的中文关系 pattern。
- 新增/增强的规则关系类型包括：
  - `belongs_to`：属于、隶属于、归属于、归口等。
  - `contains`：包括、包含、涵盖、由...组成、下设等。
  - `responsible_for`：负责、承担职责、履行职责、牵头、承办等。
  - `approves`：审批、批准、备案、核准、审议、授权等。
  - `prohibits`：禁止、不得、严禁、不予、限制等。
  - `applies_to`：适用、支持、覆盖、面向等。
  - `references`：依据、根据、参照、引用、按照、遵循等。
  - `alias_of`：简称、又称、也叫、以下简称等。
  - `depends_on`：依赖、前置、基于、取决于、以...为前提等。
- `knowledge_extractor.py` 的 relation schema 提示已同步允许这些类型。
- 规则关系仍然只补召回：
  - 如果 LLM 已经抽出同 from/to pair，规则不会再补一条覆盖它。

当前是否需要 MySQL DDL：

当前不需要。

原因：

- `kb_relation.relation_type` 已是字符串字段，新增枚举值不需要改表。
- Neo4j 写入层当前没有强枚举约束。
- 后续 P2-3 会统一 graph schema，到时再决定是否需要配置化白名单或迁移。

线上注意：

- 新关系类型会出现在后续解析产物和关系表中。
- 如前端或运营后台有 relation_type 白名单展示，需要同步展示文案；这不是数据库 DDL。

## 11. P2-3 受约束图 Schema 统一

状态：纯代码改动，当前不需要数据库 DDL。

说明：

- 新增 `graph_schema.py`，集中维护：
  - `ALLOWED_NODE_TYPES_BY_PROFILE`
  - `ALLOWED_RELATION_TYPES_BY_PROFILE`
  - `ALLOWED_GRAPH_EDGE_TYPES_BY_PROFILE`
  - `RELATION_WEIGHT_BY_TYPE`
  - `PROFILE_GRAPH_QUERY_INTENTS`
- `knowledge_extractor.py`：
  - 按 profile 校验 `relation_type`。
  - 不合规关系不进入最终 relations。
  - 输出 `relation_schema_rejected:*` warning。
- `graph_builder.py`：
  - 通过 `filter_graph_records()` 过滤非法 node/edge。
  - 不合规 graph edge 不会进入 Neo4j 写入列表。
- `graph_writer.py`：
  - 边权重改为引用统一 schema。
- `graph_intent.py` / `query.py`：
  - graph query intent 改为按 profile 白名单过滤。

当前是否需要 MySQL DDL：

当前不需要。

原因：

- 这是白名单和过滤逻辑收紧，不新增字段。
- `relation_type` 仍写入已有字符串列。
- 不合规关系直接不入最终关系结果，不需要迁移表结构。

线上注意：

- 如果历史数据里已有不在新 schema 内的 relation_type，它们不会被本次代码自动迁移或删除。
- 后续如果要治理历史脏关系，需要单独写数据清理脚本。
- 当前 Neo4j 查询实现仍主要围绕 `BusinessPlan` 图，制度图 query intent 已统一约束，但真实制度图写入/查询闭环还需要后续专项验证。

## 12. P2-4 Anchor 五阶段去重与审核闭环

状态：当前已完成候选生成纯代码增强；审核回写需要数据库/ES/Neo4j 专项开发。

本次已完成且不需要 DDL 的部分：

- `anchor_deduper.py` 增加 deterministic MinHash/LSH 候选生成。
- 低熵短标签继续跳过模糊匹配，降低“额度/费率/条件”这类泛词误合并。
- 高风险候选仍输出 `pending_review`，不自动改 anchor。
- 候选原因增加 `graphify_minhash_lsh_candidate`。

当前是否需要 MySQL DDL：

本次代码不需要。

原因：

- 已有 `knowledge_anchor_merge_candidate` 表可以继续承载候选。
- 本次只是候选发现算法增强，不改变候选表结构。

后续审核闭环需要的数据库/索引事项：

1. 审核状态回写：
   - 当前已有候选表，但还需要明确审核接口和状态流转。
   - 需要支持 `approved`、`rejected`、`rolled_back` 等状态的业务约定。
2. Anchor 合并回写：
   - 更新 anchor alias。
   - 更新 unit 的 `anchor_id`。
   - 更新 relation 的 `from_id` / `to_id`。
3. ES 同步：
   - 更新 anchor/unit 索引中的 anchor id、normalized name、alias。
   - 对被合并 anchor 执行删除或重定向。
4. Neo4j 同步：
   - 合并节点或建立 alias/redirect 边。
   - 更新相关边端点。
5. 回滚：
   - 需要记录 merge 前的 anchor/unit/relation 快照或操作日志。

建议：

- 下一阶段不要直接改线上表，先补一个 `anchor_merge_service.py`，把“预览影响范围、执行合并、回滚”三步做成可测试服务。
