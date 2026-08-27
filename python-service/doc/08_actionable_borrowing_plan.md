# danbao-poc 可借鉴能力落地方案（代码级）

> 分析日期：2026-05-29  
> 范围：`graphify-7`、`GraphRAG-Example-master`、`langextract-main`、`KnowFlow-main`、`RAG-Pro`、`grain_agent_showcase`、`DataGraphX_Learn-main` 与 `danbao-poc` 当前实现对照。  
> 目标：不再停留在“可借鉴”层面，而是明确原项目的具体方法/算法、`danbao-poc` 当前代码怎么做、该怎么改、会带来什么效果。

---

## 0. 当前项目实现基线

### 0.1 解析与中间结构

当前 `danbao-poc` 的文件入口在 `src/danbao_poc/document_parser.py`：

- `parse_document()`：按后缀路由 TXT/MD、DOCX、CSV/TSV、XLSX、PDF、图片。
- `_parse_via_ocr()`：PDF/图片走 MinerU、Paddle、Qianfan VLM、GLM OCR。
- `_normalize_mineru_middle_json()`：把 MinerU `middle_json.pdf_info[].para_blocks/preproc_blocks` 归一为 `middle_document.pages[].blocks[]`。
- `_normalize_native_pages()`：生成 `plain_text`、`normalized_text`、`char_map.spans`、`pages`、`tables`。

已经具备的能力：

- 多 OCR 后端配置。
- 中间结构带 block 级 `bbox`、`page_no`、`block_id`。
- MySQL 已有 `file_char_map`、`kb_knowledge_unit_evidence`、`file_field_mentions` 等可承载字符定位的表。

主要缺口：

- `char_map` 仍以 block 为最小单位，没有 KnowFlow 那种 line-level 坐标映射。
- 文本编码回退只覆盖 `utf-8`、`utf-8-sig`、`gb18030`、`gbk`，低于 RAG-Pro。
- 缺少按 `file_hash + parser + parse_options + profile` 复用解析产物的内容寻址缓存。

### 0.2 分块

当前分块主线：

- `catalog_chunker.build_catalog_driven_chunks()`：先抽标题候选，再让 LLM 生成目录，再映射到 `merged_text` 字符区间。
- `_map_catalog()`：用候选 ID、anchor、标题匹配，得到 `start_char/end_char`、`page_start/page_end`、`block_ids/bbox`。
- `chunk_generation.build_multigranularity_chunks()`：把目录节转成 `small_chunk`、`section_chunk`、`parent_chunk`。

已经具备的能力：

- 多粒度 chunk 已经有，且 `parent_chunk`、`section_chunk` 作为 context 角色存在。
- `small_chunk` 默认保留完整逻辑章节，不是强制短切。
- `content_for_embedding` 和 `content_for_bm25` 已区分。

主要缺口：

- 父子关系是按目录路径/section 聚合，不是 KnowFlow 那种 AST 行范围包含。
- 检索命中 child 后，没有自动用 parent chunk 替换/扩展 evidence group 的主上下文。
- 表格、代码块等结构块没有 AST 级“不可拆”保护，只靠 block 和 catalog 质量。

### 0.3 抽取、图谱、索引

当前结构化抽取：

- `extractor.extract_guarantee_plan()`：担保方案字段抽取，规则 + LLM 合并。
- `knowledge_extractor.extract_knowledge_structure()`：Anchor、Knowledge Unit、Relation 联合抽取。
- `knowledge_extractor.normalize_knowledge_payload()`：做 evidence_quote 是否存在于 primary chunk 的校验。
- `graph_builder.build_business_graph()`：把方案、字段、区域、产业、机构转 Neo4j 图节点/边。
- `graph_writer.import_business_graph()`：写入 Neo4j。

已经具备的能力：

- Anchor/Unit/Relation 三层结构已经有。
- MySQL 有候选池 `kb_knowledge_candidate_pool`，可承接实体合并和人工审核。
- ES 有 chunk、field、QA、section_summary、anchor、knowledge_unit 六类索引。

主要缺口：

- Evidence 只做字符串包含，未做 LangExtract 的 token/字符级模糊对齐。
- Anchor 去重依赖 `canonical_key` 和简单归一，缺少 Graphify 的 MinHash/Jaro-Winkler/LLM 仲裁。
- `build_business_graph()` 图 Schema 偏窄，只有担保方案字段图；`knowledge_structure` 的 Relation 尚未形成强约束图检索主通道。

### 0.4 检索

当前检索主线在 `api/retrieve_service.py` 和 `query.py`：

- `retrieve()`：并行召回 `qa`、`structured`、`section_summary`、`graph`、`bm25`、`vector` 六路。
- `weighted_rrf_fuse()`：支持 `weighted_rrf` 和 `score_aware` 两种融合。
- `rerank_candidates()`：调用 rerank 模型后再结合字段/关键词优先级。
- `build_evidence_groups()`：按 `primary_chunk_id` 聚合 evidence。
- `context_chunks`：通过 `load_related_chunks()` 和可选 `graph_context_plan()` 加载关联 chunk。

已经具备的能力：

- RAG-Pro 的 RRF 思路已经部分落地。
- KnowFlow/RAG-Pro 的“多路召回 + rerank”已经有本地版本。
- 支持 product scope file filter，避免跨产品串召回。

主要缺口：

- 默认策略仍是 `score_aware`，RRF 没有作为稳定默认。
- 没有 dense+sparse 双向量，只有 ES BM25 与 dense/vector 分路。
- Parent chunk 只是 context_chunks，不会替换 child evidence，也没有 parent 独立召回策略。
- 查询改写默认可开启，但没有 RAG-Pro 的“短查询不改写”硬保护。

---

## 1. Graphify-7：实体去重、增量解析、图社区

### 1.1 可借鉴源码/算法

Graphify 关键方法：

- `graphify/detect.py:detect_incremental()`：基于 manifest、mtime、hash 做增量检测。
- `graphify/llm.py:_extract_with_adaptive_retry()`：LLM 输出失败/截断后，把 chunk 二分递归重试。
- `graphify/dedup.py:deduplicate_entities()`：五阶段实体去重。
- `graphify/cluster.py:cluster()`：Leiden/Louvain 社区检测。
- `graphify/serve.py:_score_nodes()` 和 `_filter_graph_by_context()`：关键词选种子，再按上下文过滤边类型。

实体去重的可迁移算法：

1. 标准化：lowercase、去标点、空白折叠。
2. 熵门控：低信息文本如“额度”“流程”“条件”不进入模糊合并。
3. MinHash/LSH：用字符 3-gram 生成候选对，降低两两比较成本。
4. Jaro-Winkler：高分自动合并，中间分进入 ambiguous。
5. LLM 仲裁：批量判断 ambiguous 对是否同一业务对象。

### 1.2 danbao-poc 当前怎么实现

当前 Anchor 去重在 `knowledge_extractor.normalize_knowledge_payload()` 内完成：

- `_is_generic_anchor()` 会丢弃明显泛词。
- `stable_id = anchor_{canonical_key(...)}` 根据名称和证据生成稳定 ID。
- `mysql_store.save_parse_result()` 会把 anchor/unit/relation 写进 `kb_knowledge_candidate_pool`，其中 `merge_group_key` 是 `clean_identifier(...)` 结果。

这能防止完全重复，但解决不了这些情况：

- “鲁担惠农贷”“鲁担 惠农贷”“山东农担惠农贷”无法合并。
- “服务对象”“支持对象”可能是同一节对象，但如果 evidence 不同会形成多个候选。
- 同一 KB 多文件内的同名产品、同名制度章节没有跨文件实体簇。

### 1.3 该怎么改

新增模块：`src/danbao_poc/knowledge_deduper.py`

建议接口：

```python
def dedupe_anchors(
    anchors: list[dict],
    *,
    kb_id: int,
    file_node_id: int,
    parse_generation: str,
    use_llm_arbitration: bool = False,
) -> tuple[list[dict], dict]:
    ...
```

核心步骤：

1. `normalize_anchor_name(name)`：统一全角/半角、去空白、去括号补充说明、统一“担保/农担/鲁担”等领域缩写。
2. `shannon_entropy(text)`：低于阈值 2.5 的短泛词不进入 LSH。
3. `char_ngrams(text, n=3)`：中文名少于 3 字时降级为 2-gram。
4. `minhash_signature(ngrams)`：不新增重依赖时可先用 `hashlib.blake2b(seed + gram)` 模拟 64 个 permutation。
5. `jaro_winkler(a, b)`：可本地实现，或轻依赖 `rapidfuzz`。考虑当前依赖较保守，建议先本地实现 Jaro-Winkler。
6. 自动合并阈值：`jw >= 0.92`；疑似阈值：`0.78 <= jw < 0.92`。
7. 低置信 ambiguous 放入 `kb_knowledge_candidate_pool.review_status='pending'`，不要直接合并。

调用点：

- `knowledge_extractor.extract_knowledge_structure()` 之后、`mysql_store.save_parse_result()` 之前。
- 或在 `save_parse_result()` 写 candidate pool 前做一次同文件去重，再后续做 KB 级异步合并。

表结构建议：

- 复用 `kb_knowledge_candidate_pool.merge_group_key` 存标准实体簇 key。
- 可新增 `kb_anchor_merge_group`：
  - `kb_id`
  - `merge_group_key`
  - `canonical_anchor_id`
  - `canonical_name`
  - `member_anchor_ids_json`
  - `decision_source`
  - `confidence`

### 1.4 预期效果

- Anchor 重复率下降，structured/graph 通道不会被同义节点稀释。
- 图谱中的节点度更真实，后续做 Graphify 社区检测或 DataGraphX 条件关系检索才有价值。
- 对担保方案中“产品名/方案名/制度名”多写法尤其有效。

### 1.5 不建议照搬

Graphify 面向代码库图谱，很多关系类型如 `calls/imports/inherits` 对担保方案无意义。不要把它的开放关系全搬进 Neo4j；只借鉴去重、增量、社区检测。

---

## 2. GraphRAG-Example：中文规则关系、鲁棒 JSON 解析、通道优先级

### 2.1 可借鉴源码/算法

GraphRAG-Example 关键方法：

- `src/services/parsers/txtParser.js:CN_PATTERNS`：中文关系正则。
- `src/services/parsers/txtParser.js` 的 `_isXofY`：处理“A 是 B 的 C”。
- `src/services/llmExtractor.js:parseExtractionResult()`：剥离 markdown code fence、修复常见 JSON 变体。
- `src/services/llmExtractor.js:extractJsonObject()`：按花括号深度提取嵌入散文里的 JSON。
- `src/services/graphService.js:findSeedNodes()`：图检索种子评分。
- `src/services/ragRetriever.js:formatCombinedContext()`：把原文内容标为主要依据，把图结构标为辅助参考。

最值得迁移的是 11 类中文关系模式：

- 等价：`A 是 B`
- 归属：`A 属于/隶属于 B`
- 组成：`A 包含/包括/涵盖 B`
- 创建/提出：`A 创建/提出/制定 B`
- 位置/范围：`A 位于/来自/适用于 B`
- 因果：`A 导致/影响/引发 B`
- 依赖：`A 基于/依赖/使用 B`
- 别名：`A 又称/被称为 B`
- 并列：`A 和/与/及 B`
- 所有格：`A 是 B 的 C`
- 句内共现：仅无强关系时补充。

### 2.2 danbao-poc 当前怎么实现

当前关系主要来自 LLM：

- `knowledge_extractor.extract_knowledge_structure()` 提示模型输出 `relations`。
- `normalize_knowledge_payload()` 只校验 relation endpoint 是否已知。
- `graph_builder.build_business_graph()` 只把担保字段转成 `BusinessPlan -HAS_FIELD-> BusinessField`，区域/产业/机构为固定维度边。

当前没有规则关系补召回。也就是说，如果 LLM 漏掉“适用于”“由 X 负责”“依赖于”的关系，后续 graph 通道没有补救。

当前 JSON 解析也较脆弱：

- `JsonChatClient._complete_with_http()` 直接 `json.loads(content)`。
- 虽然请求里设置了 `response_format={"type":"json_object"}`，但兼容 OpenAI-like 或代理模型时，仍可能返回 code fence、前后解释文字、尾逗号。

### 2.3 该怎么改

#### A. 新增规则关系抽取器

新增：`src/danbao_poc/rule_relation_extractor.py`

建议输出对齐现有 `knowledge_extractor` 的 relation schema：

```python
def extract_rule_relations(chunks: list[dict], anchors: list[dict], units: list[dict]) -> list[dict]:
    ...
```

实现要点：

1. 只对 `small_chunk` 主体内容跑规则。
2. 先在 chunk 内定位已知 anchor/unit 文本，形成 `known_terms`。
3. 正则命中时，只接受 `subject/object` 至少一端能落到已知 anchor/unit；避免把普通词造图。
4. `_isXofY` 规则不要直接造三元组为 `A related_to B`，应映射成：
   - `B contains A` 或 `A attribute_of B`
   - `C` 写入 `metadata.attribute`
5. 共现边只作为低置信 `related_to`，且当同一对节点已有强关系时不加。

调用点：

- `knowledge_extractor.normalize_knowledge_payload()` 得到 anchors/units 后追加。
- 或 `save_parse_result()` 写 `kb_relation` 前合并规则关系。

#### B. 增强 JSON 解析

改造 `openai_compat.JsonChatClient._complete_with_http()`：

```python
def parse_json_lenient(content: str) -> dict:
    content = strip_think_tags(content)
    content = strip_markdown_fence(content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        obj = extract_balanced_json_object(content)
        obj = normalize_fullwidth_punctuation(obj)
        obj = remove_trailing_commas(obj)
        return json.loads(obj)
```

这一层适用于 `EXTRACT`、`KNOWLEDGE`、`CATALOG`、`QUERY` 全部 LLM JSON 调用。

#### C. 在证据组里标注主/辅来源

改造 `query.build_evidence_groups()`：

- `bm25/vector/qa/structured/section_summary` 标为 `source_priority="primary"`
- `graph` 标为 `source_priority="auxiliary"`
- prompt 组装时明确：“答案必须优先来自 primary evidence；graph path 只用于补充关系解释。”

### 2.4 预期效果

- 对制度/方案类文档，“适用范围、职责分工、依赖、引用、包含”关系召回会更稳。
- JSON 调用失败率下降，尤其是代理模型或 fallback 模型输出格式不稳定时。
- Graph 通道不再和原文通道平权干扰，降低“图谱辅助信息喧宾夺主”的风险。

---

## 3. LangExtract：字符级对齐、LCS 双门控、多轮抽取

### 3.1 可借鉴源码/算法

LangExtract 关键方法：

- `langextract/chunking.py:ChunkIterator`：句子级 chunk，超限优先换行，再 token fallback。
- `langextract/prompting.py:ContextAwarePromptBuilder`：把前一 chunk 尾部作为上下文前置。
- `langextract/resolver.py:WordAligner`：整体抽取结果与源文本 token 序列对齐。
- `langextract/resolver.py:_best_lcs_spans()`：LCS DP 记录不同匹配数下的最短源跨度。
- `langextract/resolver.py` 的 coverage/density gate：
  - 覆盖率：匹配 token 数达到阈值。
  - 密度：`matches / span_len >= min_density`，防止匹配分散。

### 3.2 danbao-poc 当前怎么实现

当前证据对齐有三类：

- `knowledge_extractor._quote_in_chunks()`：`quote in content` 或去空白包含。
- `answer_prebuilder._quote_in_chunk()`：同样是字符串包含。
- `extractor._best_chunk_for_field()`：如果 LLM 给了 `source_chunk_key` 就信任，否则 `_score_chunk_for_field()` 按字段别名、section_type、value_text 命中打分。

MySQL 表已经为精细对齐预留字段：

- `file_field_mentions.char_start/char_end/alignment_status`
- `kb_knowledge_unit_evidence.char_start/char_end/alignment_status`
- `kb_section_summary_evidence.char_start/char_end/alignment_status`
- `file_char_map.global_char_start/global_char_end/page_no/block_id/bbox_json`

但当前没有真正把 evidence quote 定位到字符区间，也没有记录 `MATCH_EXACT/MATCH_FUZZY/MATCH_LESSER/FAILED`。

### 3.3 该怎么改

新增：`src/danbao_poc/evidence_aligner.py`

建议核心接口：

```python
class AlignmentStatus:
    MATCH_EXACT = "match_exact"
    MATCH_COMPACT = "match_compact"
    MATCH_FUZZY = "match_fuzzy"
    FAILED = "failed"

def align_quote_to_chunk(quote: str, chunk: dict) -> dict:
    ...

def align_quote_to_document(quote: str, char_map: dict, normalized_text: str) -> dict:
    ...
```

算法建议：

1. 精确匹配：
   - `content.find(quote)`
2. 紧凑匹配：
   - 去空白后匹配，同时维护 compact index 到原始 index 的反查。
3. Token LCS：
   - 中文可用字符 bigram 或 `jieba + 标点 token`。
   - 对 quote token 和 content token 做 DP。
   - 记录每个 match_count 的最短 span。
4. 双门控：
   - `coverage >= 0.75`
   - `density >= 1/3`
5. 输出：
   - `char_start/char_end`
   - `alignment_status`
   - `alignment_score`
   - `page_no/block_ids/bbox`：通过 `file_char_map.spans` 或 chunk `block_ids/bbox` 映射。

调用点：

- `knowledge_extractor.normalize_knowledge_payload()`：替换 `_quote_in_chunks()` 的布尔返回，返回对齐详情。
- `extractor._make_field()`：填充 mention 的 `char_start/char_end/alignment_status`。
- `answer_prebuilder.normalize_prebuilt_answers()`：不再只检查 quote 是否存在，而是记录对齐质量。
- `mysql_store.save_parse_result()`：写入 evidence 表时使用对齐详情。

### 3.4 预期效果

- 证据引用从 chunk 级提升到字符级。
- 大幅减少“LLM 摘抄时多/少一个词导致证据丢弃”的问题。
- 前端可支持点击答案引用后定位到页内具体文本区域。
- 后续评测可以统计 exact/fuzzy/failed 占比，作为解析质量指标。

---

## 4. KnowFlow：父子检索、行级坐标、AST 语义分块

### 4.1 可借鉴源码/算法

KnowFlow 关键能力：

- 父子分块：child 检索，parent 作为回答上下文。
- `know_parent_chunk`、`know_parent_child_mapping`：父块和映射独立存储。
- `coordinate_map`：`{line_idx: [page, x0, x1, y0, y1]}`。
- Smart chunk：Markdown AST 保持表格、代码块、列表、引用完整。
- `FulltextQueryer` 字段 boost：`title_tks^10`、`important_kwd^30`、`question_tks^20`。
- `insert_citations`：答案句子和 chunk 做 embedding 相似度，在答案中插入 `[ID:n]`。

### 4.2 danbao-poc 当前怎么实现

父子结构：

- `chunk_generation.build_multigranularity_chunks()` 已生成 `small_chunk`、`section_chunk`、`parent_chunk`。
- `kb_chunk` 表已有 `primary_chunk_id`、`parent_chunk_id` 字段。
- ES chunk mapping 也有 `primary_chunk_id`、`parent_chunk_id`、`retrieval_role`、`context_level`。

但检索阶段：

- `search_bm25()`、`search_vector()` 可按 `chunk_type` 过滤，但默认召回结果仍主要按候选自身内容进入 evidence group。
- `build_evidence_groups()` 以 `primary_chunk_id` 聚合，但 `primary_chunk` 仍可能是 child 内容。
- `context_chunks` 是额外字段，不会强制替换 answer prompt 的主上下文。

坐标：

- `_normalize_native_pages()` 和 `catalog_chunker.build_merged_text()` 产出 block 级 `char_map.spans`。
- `bbox` 是 block bbox 列表，无法精确到行。

### 4.3 该怎么改

#### A. 父子检索扩展先落地

无需大改存储，直接基于现有 `kb_chunk` 做：

新增：`mysql_store.load_parent_chunks_for_primary_ids(kb_id, primary_chunk_ids, index_generations)`

逻辑：

1. 对命中的 `small_chunk` 查 `parent_chunk_id`。
2. 如果没有 `parent_chunk_id`，用 `section_chunk` 或同 `chunk_group_id` 下 context chunk。
3. 返回 parent 内容、child 命中内容、映射关系。

改造 `retrieve_service.retrieve()`：

1. `results = rerank_candidates(...)` 后，取 `primary_chunk_id`。
2. 调用 `load_parent_chunks_for_primary_ids()`。
3. 在 `evidence_groups` 中新增：
   - `retrieval_hit_chunk`
   - `answer_context_chunk`
   - `context_replacement="parent"` / `"section"` / `"child_only"`
4. 生成 prompt 时优先使用 `answer_context_chunk.content`，但引用仍指向 child evidence。

配置项：

```json
{
  "parent_context": {
    "enabled": true,
    "mode": "replace",
    "max_parent_chars": 6500,
    "fallback": "section_then_child"
  }
}
```

#### B. 父 chunk 独立 ES 索引可作为 P2

当前 ES 单索引已能跑。父 chunk 独立索引适合数据量大后再做：

- 新增 `knowledge_parent_chunks_v1`
- 只写 `chunk_type=parent_chunk/section_chunk`
- 检索时 child index 召回，parent index 按 id 批量取。

短期不建议先做独立索引，因为当前项目还在 POC 阶段，多一套索引会增加运维复杂度。

#### C. 行级坐标映射

改造 `document_parser._normalize_mineru_middle_json()`：

1. 遍历 MinerU block 的 `lines[]`。
2. 每一行生成：
   - `line_id`
   - `page_no`
   - `global_char_start/global_char_end`
   - `bbox`
   - `block_id`
3. `middle_document.coordinate_map` 写成 line 级。
4. `file_char_map` 可继续存 span，但 `span_id` 从 block span 扩展为 line span。

再改 `evidence_aligner`：

- quote 对齐到 char interval 后，反查覆盖哪些 line span。
- bbox 用行 bbox 合并，而不是整个 block bbox。

#### D. AST 语义分块

新增可选分块器：`markdown_ast_chunker.py`

迁移策略：

1. 对 `middle_document.markdown` 使用 `markdown-it-py`。
2. 节点类型为 `table/code/fence/blockquote/list` 时作为 protected block。
3. 标题更新 `context_stack`。
4. 超限时只在普通段落间切，不在 protected block 内切。
5. 产出 base chunks 后仍走 `build_multigranularity_chunks()`，保持后续存储不变。

开启条件：

- `parse_options.chunking.strategy="markdown_ast"`
- 或当 `middle_document.parser in {"mineru", "qianfan_vlm", "glm_ocr"}` 且 markdown 非空时启用。

### 4.4 预期效果

- 父子检索扩展是最高收益：命中小段，回答用完整上级上下文，减少“答案只看到半条规则”的问题。
- 行级坐标会让引用定位更稳，尤其是 PDF 表格、条款列表。
- AST 分块能降低表格/代码/清单被拆烂导致 BM25 和向量语义都变差的问题。

---

## 5. RAG-Pro：RRF 默认化、稀疏向量、关键词/伪问题、短查询保护

### 5.1 可借鉴源码/算法

RAG-Pro 关键方法：

- `backend/app/core/vector_store.py:sparse_search()`：稀疏向量 overlap 点积。
- `backend/app/core/vector_store.py:hybrid_search()`：dense + sparse 的 RRF，`k=60`。
- `backend/app/core/retriever.py`：embed -> hybrid search -> rerank -> parent context -> confidence。
- `backend/app/api/v1/document.py:_extract_keywords()`：每 chunk top 5 关键词。
- `backend/app/api/v1/document.py:_generate_questions()`：每 chunk 生成 3 个伪问题。
- `backend/app/api/v1/document.py`：查询长度大于 50 才做 LLM 改写。
- `backend/app/core/confidence.py`：`confidence = 0.6 * max_score + 0.4 * avg_score`。

### 5.2 danbao-poc 当前怎么实现

已经有：

- `query.DEFAULT_RRF_K = 60`
- `query.resolve_weighted_rrf_config()` 支持 `weighted_rrf`。
- `query.weighted_rrf_fuse()` 已实现按 route 权重的 RRF/score-aware。
- ES mapping 已有 `question_tks`、`extended_questions_tks` 用于 QA。
- `answer_prebuilder.prebuild_answers()` 能生成预置 QA。

缺口：

- 默认 fusion strategy 是 `score_aware`，不是纯 RRF。
- chunk 本身没有 `keywords/questions` 字段；BM25 只能搜标题、路径、正文。
- EmbeddingClient 只取 dense embedding，不保留 BGE-M3 sparse lexical weights。
- 查询改写是否开启由配置控制，但没有“短查询不改写”的统一保护。
- 检索响应没有统一 `confidence/confidence_label`。

### 5.3 该怎么改

#### A. RRF 作为默认稳定策略

改 `query.resolve_weighted_rrf_config()`：

- 对 `business_plan/governance_rule/project_doc` 默认 `strategy="weighted_rrf"`。
- 如果线上评测显示部分场景 score-aware 更好，可在 MySQL `retrieval_config` 单独覆盖。

注意：当前 `weighted_rrf` contribution 是 `route_weight * confidence / (k + rank)`，数值很小，但排序有效。需要在 debug 中保留原始 route score，方便排查。

#### B. Chunk 关键词和伪问题

新增：`chunk_enrichment.py`

```python
def enrich_chunk_text(chunk: dict, *, keyword_count: int = 8, question_count: int = 3) -> dict:
    keywords = extract_keywords(chunk["content"], chunk["title"], chunk["section_type"])
    questions = generate_pseudo_questions(chunk)
    return {"keywords": keywords, "questions": questions}
```

字段落点：

- 不建议马上改 `kb_chunk` 表加列；先写入 `metadata_json.enrichment`。
- ES mapping 增加：
  - `keywords_tks`
  - `questions_tks`
  - `important_kwd`
- `index_rows()` 写 chunk 文档时把 `keywords/questions` 拼入 `content_for_bm25` 或单独字段。

搜索改造：

- `search_bm25()` 的 `chunk_fields` 从：
  - `doc_name_tks^5`
  - `section_path_text_tks^3`
  - `title_tks^2`
  - `content_for_bm25_tks^2`
  - `content_tks`
- 调整为：
  - `doc_name_tks^5`
  - `section_path_text_tks^3`
  - `title_tks^4`
  - `keywords_tks^6`
  - `questions_tks^4`
  - `content_for_bm25_tks^2`
  - `content_tks`

#### C. Dense + sparse 双向量

当前 ES/CSS 环境对 sparse vector 不友好，不建议直接引入新向量库。更稳的落地方式：

1. 继续使用 ES `_tks` scripted BM25 作为 sparse 通道。
2. 如果 embedding 服务返回 BGE-M3 `lexical_weights`，存入 MySQL/ES metadata 作为 P2。
3. 第一阶段通过 `weighted_rrf` 融合 `bm25 + vector`，实际已经等价于 dense + sparse 两路排名融合。

#### D. 短查询保护

改 `api/retrieve_service.retrieve()` 的 query understanding 逻辑：

```python
enable_query_assist = option_enabled and len(request.query.strip()) > 50
```

再加白名单：

- 如果 query 命中字段短问，如“额度多少”“反担保是什么”“农贸贷期限”，不改写。
- 如果 query 有明确产品名/文件名，也不改写，只做 scope anchor 提取。

#### E. 统一置信度

新增：

```python
def compute_retrieval_confidence(results: list[dict]) -> dict:
    scores = [r.normalized_score or r.rerank_normalized_score or r.score]
    confidence = 0.6 * max(scores) + 0.4 * avg(scores)
```

落入 retrieve response：

- `confidence`
- `confidence_label`
- `confidence_factors`

### 5.4 预期效果

- RRF 默认化能降低不同通道 score 标尺不一致造成的排序漂移。
- keywords/questions 会显著提升“用户问法和原文写法不一致”时的 BM25 召回。
- 短查询保护能减少“额度”“期限”“反担保”这类精准短问被 LLM 改坏。
- 置信度能给前端和评测提供统一质量信号。

---

## 6. grain_agent_showcase：SSE、引用兼容、前端展示

### 6.1 可借鉴源码/算法

grain_agent_showcase 不是 RAG 后端，它的价值在前端协议：

- `app.js:processSseBlock`：按 `\n\n` 切 SSE block，保留未完成 buffer。
- `normalizeReferenceList()`：兼容 RAGFlow 多种引用结构。
- `splitThoughtSections()`：把 `<think>` 段落和普通答案分离。
- `renderPlainBlock()`：纯文本按列表/段落结构化渲染。

### 6.2 danbao-poc 当前怎么实现

当前主要是同步检索 API：

- `/api/v1/retrieve/query` 返回完整 JSON。
- 响应里已有 `results`、`evidence_groups`、`context_chunks`。
- 没有标准 SSE answer stream。

### 6.3 该怎么改

新增接口：

- `POST /api/v1/retrieve/chat_stream`

事件建议：

```text
event: retrieval_started
data: {"query":"...","kb_ids":[...]}

event: recall_finished
data: {"route_candidate_counts": {...}}

event: evidence
data: {"evidence_groups":[...]}

event: text_delta
data: {"text":"..."}

event: message_end
data: {"answer":"...","citations":[...],"confidence":0.82}
```

引用兼容层：

新增 `reference_normalizer.py`，统一输出：

```json
{
  "doc_name": "...",
  "kb_id": 1,
  "file_node_id": 2,
  "chunk_id": 3,
  "page_no": 4,
  "position": {"char_start": 10, "char_end": 30, "bbox": [...]},
  "content": "..."
}
```

### 6.4 预期效果

- 前端能边检索边展示召回进度。
- 引用格式稳定后，未来兼容 RAGFlow/本系统/外部 Agent 更容易。
- 用户体验提升，但对检索质量本身帮助较小，因此优先级 P3。

---

## 7. DataGraphX：受约束 Schema、条件关系搜索、Neo4j 回退

### 7.1 可借鉴源码/算法

DataGraphX 关键方法：

- `config.py:GRAPH_CONFIG`：固定 `allowed_nodes`、`allowed_relationships`。
- `app.py:LLMGraphTransformer(...)`：LLM 只允许输出白名单节点和关系。
- `app.py:process_question()`：
  - jieba 关键词精确匹配。
  - Neo4j vector index 查询。
  - 问题含“关系/联系/作用/影响/如何”时才触发关系搜索。
  - Neo4j fulltext index 查询。
  - APOC fuzzyMatch 作为回退。
- `knowledge_graph_utils.py:find_relevant_subgraph()`：关键词命中节点后 BFS max_depth=2。

### 7.2 danbao-poc 当前怎么实现

当前有两套图：

1. 业务字段图：
   - `build_business_graph()` 固定 `BusinessPlan/BusinessField/Region/Industry/Organization`。
2. 知识结构：
   - `kb_anchor_registry`
   - `kb_knowledge_unit`
   - `kb_relation`

但 Neo4j 主写入还是业务字段图。`kb_relation` 更多停留在 MySQL/ES structured 检索层，没有形成 DataGraphX 那种受约束图谱检索。

### 7.3 该怎么改

#### A. 为不同 profile 定义受约束 Schema

新增：`profiles/graph_schema.py`

示例：

```python
GRAPH_SCHEMAS = {
    "business_plan": {
        "nodes": ["Plan", "Product", "ServiceObject", "Condition", "AmountRule", "TermRule", "Region", "Industry", "Organization", "Material", "ProcessStep"],
        "relationships": ["HAS_RULE", "APPLIES_TO", "IN_REGION", "SUPPORTS_INDUSTRY", "REQUIRES", "HAS_STEP", "REFERENCES", "RISK_SHARED_BY", "COUNTER_GUARANTEE"]
    },
    "governance_rule": {
        "nodes": ["RuleDocument", "Clause", "Department", "Role", "Responsibility", "Process", "Requirement", "Prohibition", "Reference"],
        "relationships": ["CONTAINS", "REQUIRES", "PROHIBITS", "RESPONSIBLE_FOR", "REFERENCES", "APPLIES_TO"]
    }
}
```

#### B. 把 Knowledge Unit 映射到图

新增：`knowledge_graph_builder.py`

输入：

- `anchors`
- `knowledge_units`
- `relations`
- `profile`

输出：

- 受约束节点/边。

映射规则：

- `unit_type=condition` -> `Condition`
- `unit_type=amount/formula` -> `AmountRule`
- `unit_type=process_step` -> `ProcessStep`
- `relation_type=references` -> `REFERENCES`
- `relation_type=applies_to` -> `APPLIES_TO`

不能映射的保留在 MySQL，不写 Neo4j，避免噪声。

#### C. 条件触发关系搜索

改 `query.graph_query()`：

- 如果 query 含“关系、联系、作用、影响、依赖、引用、依据、负责、适用、包含、流程”，执行关系路径查询。
- 否则优先查节点/字段，不扫关系。

关系查询模板：

```cypher
MATCH (n)-[r]-(m)
WHERE n.kb_id = $kb_id
  AND any(term IN $terms WHERE n.name_cn CONTAINS term OR m.name_cn CONTAINS term)
RETURN n, type(r) AS relation, m
LIMIT $limit
```

#### D. APOC 模糊匹配只做回退

如果 Neo4j 部署有 APOC，可启用：

```cypher
MATCH (n)
WHERE apoc.text.fuzzyMatch(n.name_cn, $query)
RETURN n
```

如果没有 APOC，不要强依赖；当前 ES BM25/field/anchor 检索已经能承担模糊召回。

### 7.4 预期效果

- 图谱关系更可控，避免 LLM 自由造关系类型。
- 图检索只在关系型问题触发，减少延迟和噪声。
- 多 profile 后，制度/项目文档可以有自己的图 Schema，而不是全部套担保方案字段图。

---

## 8. 优先级路线图

### P0：建议先做，收益最大且和现有架构契合

1. **父子检索扩展**
   - 改造点：`retrieve_service.retrieve()`、`query.build_evidence_groups()`、`mysql_store.load_parent_chunks_for_primary_ids()`。
   - 现状：已有 `parent_chunk`，但检索不自动替换上下文。
   - 效果：回答上下文完整性提升，尤其是担保方案条款和制度条款。

2. **Evidence LCS 双门控对齐**
   - 改造点：新增 `evidence_aligner.py`，替换 `_quote_in_chunks()`、`_make_field()` 证据定位逻辑。
   - 现状：只做字符串包含。
   - 效果：引用定位更准，减少证据丢弃。

3. **短查询不改写**
   - 改造点：`retrieve_service.retrieve()` query understanding 开关。
   - 现状：配置开启后短问也可能被改写。
   - 效果：减少精准短问召回变差。

### P1：检索与抽取质量增强

4. **Chunk keywords/questions**
   - 改造点：`chunk_generation._make_chunk()` 或索引前 enrichment；`es_store.ensure_indices()`；`search_bm25()` 字段 boost。
   - 现状：chunk 无关键词/伪问题。
   - 效果：BM25 召回增强。

5. **规则关系抽取**
   - 改造点：新增 `rule_relation_extractor.py`，接入 `knowledge_extractor`。
   - 现状：关系主要靠 LLM。
   - 效果：中文制度/方案关系召回更稳。

6. **Anchor 五阶段去重**
   - 改造点：新增 `knowledge_deduper.py`，接入 candidate pool。
   - 现状：canonical_key 简单去重。
   - 效果：图谱节点质量提升。

7. **鲁棒 JSON 解析**
   - 改造点：`openai_compat.JsonChatClient._complete_with_http()`。
   - 现状：直接 `json.loads(content)`。
   - 效果：LLM 抽取失败率下降。

### P2：结构和工程能力补强

8. **行级坐标映射**
   - 改造点：`document_parser._normalize_mineru_middle_json()`、`file_char_map` 写入逻辑、`evidence_aligner`。
   - 现状：block 级 bbox。
   - 效果：PDF 高亮定位更准。

9. **受约束 Knowledge Graph Schema**
   - 改造点：`profiles/graph_schema.py`、`knowledge_graph_builder.py`、`graph_writer.py`。
   - 现状：Neo4j 主要是 BusinessPlan 字段图。
   - 效果：图检索噪声下降，支持多文档类型。

10. **解析缓存/增量解析**
    - 改造点：`parse_service` 进入 `parse_document()` 前检查 `file_hash + profile + parser + options_hash`。
    - 现状：`kb_file_node.file_hash` 存在，但没有作为解析结果缓存 key。
    - 效果：重复解析成本下降。

### P3：体验和扩展

11. **SSE 流式问答**
    - 改造点：新增 `/api/v1/retrieve/chat_stream`。
    - 效果：前端体验提升。

12. **AST Markdown 分块**
    - 改造点：新增 `markdown_ast_chunker.py`。
    - 效果：表格、代码、列表 chunk 质量提升。

13. **Neo4j fulltext/APOC 回退**
    - 改造点：`graph_query()`。
    - 效果：graph 通道召回补充，但依赖 Neo4j 插件和索引配置。

---

## 9. 推荐第一轮改造包

第一轮不要同时动解析、抽取、索引、检索四层。建议按“能快速评测”的顺序做：

### 改造包 A：检索上下文完整性

内容：

1. 父子检索扩展。
2. 短查询不改写。
3. retrieve response 增加 `confidence/confidence_label`。

涉及文件：

- `src/danbao_poc/api/retrieve_service.py`
- `src/danbao_poc/query.py`
- `src/danbao_poc/mysql_store.py`

评测：

- 用现有 `tests/run_100query_test.py` 或 `tests/retrieval_comparison_test.py` 跑担保方案问题。
- 重点看“额度、期限、反担保、准入条件、办理流程”的答案完整性。

### 改造包 B：证据定位质量

内容：

1. 新增 `evidence_aligner.py`。
2. `knowledge_extractor`、`extractor`、`answer_prebuilder` 接入。
3. MySQL evidence 表写入 `char_start/char_end/alignment_status`。

涉及文件：

- `src/danbao_poc/evidence_aligner.py`
- `src/danbao_poc/knowledge_extractor.py`
- `src/danbao_poc/extractor.py`
- `src/danbao_poc/answer_prebuilder.py`
- `src/danbao_poc/mysql_store.py`

评测：

- 新增单测：exact、去空白、少量漏字、分散匹配拒绝。
- 统计 parse report 中 exact/fuzzy/failed 数量。

### 改造包 C：召回增强

内容：

1. chunk keywords/questions。
2. BM25 字段 boost 调整。
3. 规则关系抽取。

涉及文件：

- `src/danbao_poc/chunk_enrichment.py`
- `src/danbao_poc/chunk_generation.py`
- `src/danbao_poc/es_store.py`
- `src/danbao_poc/rule_relation_extractor.py`
- `src/danbao_poc/knowledge_extractor.py`

评测：

- 对比 BM25 命中数量、融合后 top_k 命中率、答案引用覆盖率。

---

## 10. 与 00-07 文档的差异

00-07 的结论大体正确，但有几处需要修正：

1. “danbao-poc 没有 RRF”不准确。当前已有 `weighted_rrf_fuse()` 和 `DEFAULT_RRF_K=60`，问题是默认策略和稀疏向量层还没完全按 RAG-Pro 方式落地。
2. “danbao-poc 父子分块简单”只说对了一半。当前已生成 `parent_chunk`，但检索时没有 child -> parent 自动上下文替换，这是核心缺口。
3. “danbao-poc 字符定位 chunk 级”需要细化。表结构已经有 char 字段，`file_char_map` 也存在；缺的是 LangExtract 式对齐算法和 KnowFlow 式行级坐标。
4. “DataGraphX Neo4j 向量索引值得迁移”优先级不应太高。当前 ES/CSS 已经承担向量和 BM25，短期更值得做的是受约束 Schema 和条件触发关系搜索。
5. “KnowFlow 父 chunk 独立索引”不是第一步。当前 MySQL + 单 ES 索引已能支持 parent 扩展，独立索引适合数据量上来后再做。

