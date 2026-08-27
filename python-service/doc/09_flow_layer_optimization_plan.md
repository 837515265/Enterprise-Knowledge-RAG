# danbao-poc 按流程分层优化方案

> 分析日期：2026-05-29  
> 写法说明：本篇不再按参考项目逐个分析，而是按 `danbao-poc` 自己的处理流程来写。每一层都包含：当前怎么实现、主要问题、可以借鉴哪些项目的哪些具体算法、代码怎么改、改完能达到什么效果。  
> 适合阅读方式：先看第 0 节总览，再按你当前最想优化的层往下看。

---

## 0. 总览：按你的流程看优化重点

`danbao-poc` 现在不是一个简单 RAG，它已经有完整的解析、目录分块、字段抽取、知识结构、图谱、ES 多索引和多路检索。真正需要优化的不是“再加一个向量检索”，而是让每一层之间的证据、上下文、结构化信息传得更稳。

可以把现在的流程理解成：

```text
文件接入
  -> 文档解析
  -> 目录识别与章节分块
  -> 多粒度 chunk
  -> 章节摘要
  -> 字段抽取
  -> Anchor / Unit / Relation 知识结构
  -> QA 预构建
  -> 图谱构建
  -> 质量报告与持久化
  -> ES / MySQL / Neo4j 索引
  -> 查询理解
  -> 多通道召回
  -> 融合与 rerank
  -> 证据组装
  -> 回答与引用
```

按投入产出比排序，最值得先做的是下面这些：

| 流程层 | 当前最明显短板 | 借鉴来源 | 具体借鉴点 | 优先级 | 落地状态 |
|---|---|---|---|---|---|
| 检索证据组装 | 命中的是小 chunk，回答时上下文有时不完整 | KnowFlow | child 命中后替换或扩展到 parent chunk | P0 | 已落地：`retrieve_service.py` 中 `_enrich_evidence_groups()` 加载 `parent_context/section_context`，同时保留 `retrieval_hit_chunk` 和 `answer_context_chunk` |
| 查询理解 | 短问题可能被 LLM 改写坏 | RAG-Pro | 只对长问题或口语化复杂问题改写 | P0 | 已落地：`_query_rewrite_guard()` 对短查询、字段查询默认跳过 LLM 改写 |
| 证据定位 | 主要靠字符串包含，遇到 OCR 空格、换行、错字容易失败 | LangExtract | LCS 双门控字符级对齐 | P0 | 已落地：新增 `evidence_aligner.py`，字段、知识、QA 预构建都写入 alignment 状态 |
| 解析定位 | 已有 block 坐标，但缺 line 级坐标 | KnowFlow | line_number 到 bbox 的坐标映射 | P1 | 已落地：`document_parser.py`、`paddle_normalizer.py` 输出 line span 和 position |
| 分块质量 | 表格、列表、合同条款可能被目录映射或长度切分打散 | KnowFlow、LangExtract | AST/结构块保护，窗口前缀上下文 | P1 | 已落地：`catalog_chunker.py` 增加 protected block 边界调整 |
| BM25 召回 | chunk 只靠正文，业务别名、伪问题不足 | RAG-Pro | 每个 chunk 生成关键词和可能问题 | P1 | 已落地：`chunk_generation.py` 生成 `keywords/possible_questions`，`es_store.py` 加入 BM25 字段权重 |
| 关系抽取 | 关系基本依赖 LLM，自由输出容易漏或漂 | GraphRAG、DataGraphX | 中文正则关系补召回 + 受约束 Schema | P1 | 已落地：新增 `relation_rule_extractor.py`，`knowledge_extractor.py` 做 Schema 过滤与规则补召回 |
| Anchor 去重 | `canonical_key` 只能处理简单同名，不能处理近似别名 | Graphify | MinHash + Jaro-Winkler + LLM 仲裁 | P2 | 部分落地：新增 `anchor_deduper.py`，当前先做标准化精确合并和模糊候选标注，暂未引入 LLM 仲裁 |
| 图谱检索 | 图谱已写入，但业务问答中图检索不够强 | DataGraphX | 条件关系搜索和相关子图扩展 | P2 | 已落地：新增 `graph_intent.py`，关系型问题可触发 graph 通道并返回关系证据 |
| 流式回答与引用 | 前端和引用展示还可以更稳定 | grain_agent_showcase、KnowFlow | SSE 消息协议 + 自动插入引用 | P2 | 后端已落地：新增 `citation_formatter.py` 和 `/api/v1/retrieve/query/stream`，前端展示可后续接 |

---

## 1. 文件接入层：先把“同一个文件”识别清楚

### 1.1 你现在怎么做

当前入口主要在：

- `src/danbao_poc/document_parser.py`
  - `parse_document()` 按后缀选择 TXT、MD、DOCX、CSV、TSV、XLSX、PDF、图片解析。
  - `_parse_via_ocr()` 对 PDF/图片走 MinerU、Paddle、Qianfan VLM、GLM OCR。
  - `_decode_text_bytes()` 对文本文件做编码兜底。
- `src/danbao_poc/mysql_store.py`
  - `save_parse_result()` 将解析结果、chunk、字段、知识结构写库。

当前已经能解析多种格式，但它更像“一次任务从头跑到底”。如果同一个文件反复上传、同一文件只改了 OCR 参数、或者同一产品批量重跑，缺少一个稳定的“内容寻址缓存”。

### 1.2 可以借鉴什么

**借鉴 Graphify 的增量检测**

Graphify 的思路不是只看文件名，而是维护一个 manifest，里面记录：

- 文件路径
- 文件大小
- 修改时间
- 文件 hash
- 上次解析参数
- 上次解析产物

只有 hash 或解析参数变化时才重新解析。

**借鉴 DataGraphX 的文档 MD5**

DataGraphX 会给文档生成 MD5，把同一个文档识别成同一个 Document 节点。这个思路适合你的 MySQL 和 Neo4j，因为后续可以把文件、产品、解析版本、图谱版本关联起来。

### 1.3 具体怎么改

建议新增一个文件级缓存表，不要先动现有主流程：

```sql
CREATE TABLE file_parse_cache (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  file_hash VARCHAR(128) NOT NULL,
  parser_profile VARCHAR(64) NOT NULL,
  parser_name VARCHAR(64) NOT NULL,
  parser_version VARCHAR(64) NOT NULL,
  parse_options_hash VARCHAR(128) NOT NULL,
  artifact_path VARCHAR(512) NULL,
  middle_document_json LONGTEXT NULL,
  plain_text_hash VARCHAR(128) NULL,
  status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_parse_cache (
    file_hash,
    parser_profile,
    parser_name,
    parser_version,
    parse_options_hash
  )
);
```

在 `parse_document()` 最前面加：

```python
file_hash = sha256_file(path)
options_hash = sha256_json({
    "profile": profile,
    "ocr_backend": settings.ocr_backend,
    "ocr_layout": settings.ocr_layout,
    "parser_version": PARSER_VERSION,
})

cached = mysql_store.load_parse_cache(
    file_hash=file_hash,
    parser_profile=profile,
    parser_name=parser_name,
    parser_version=PARSER_VERSION,
    parse_options_hash=options_hash,
)
if cached and cached.status == "success":
    return cached.to_parse_result()
```

解析成功后再写入缓存。注意缓存 key 里必须包含 `parser_version` 和 `parse_options_hash`，否则以后你改了解析逻辑，旧缓存会污染新结果。

### 1.4 改完效果

- 同一文件反复调试不会反复 OCR，速度会明显提升。
- 批量导入时，重复文件可以直接跳过。
- 后续做“增量更新图谱”时，可以知道哪些文件真的变了，哪些只是重新入库。

---

## 2. 文档解析层：把文本、页码、坐标同时保住

### 2.1 你现在怎么做

当前解析层已经有比较好的基础：

- `middle_document.pages[].blocks[]` 保存页、block、bbox、文本。
- `_normalize_native_pages()` 生成 `plain_text`、`normalized_text`、`char_map.spans`。
- MySQL 有 `file_char_map`，可以承载字符区间到页码、bbox 的映射。

主要问题是：定位粒度还偏粗。现在更像“这段话来自某页某个 block”，但 KnowFlow 那种能力是“这句话来自第几页第几行的哪个 bbox”。

### 2.2 可以借鉴什么

**借鉴 KnowFlow 的 coordinate_map**

KnowFlow 的核心价值不是 OCR 本身，而是它把文本拆到 line 级，维护：

- line text
- page number
- bbox
- parser block id
- 在整篇文档中的 char start/end

这样检索命中一句话时，可以准确高亮到 PDF 的行。

**借鉴 LangExtract 的字符级对齐**

LangExtract 不相信 LLM 给出的 evidence 一定原样存在。它会把抽取结果和原文做 LCS 对齐，并且用两个门槛判断是否可信：

- coverage：抽取文本有多少被原文覆盖。
- density：匹配字符是不是连续，而不是散落在很远的位置。

### 2.3 具体怎么改

第一步，不要直接重写解析器，只在归一化层增加 line spans。

在 `document_parser.py` 里新增一个统一结构：

```python
@dataclass
class TextSpan:
    text: str
    start_char: int
    end_char: int
    page_no: int | None
    block_id: str | None
    line_no: int | None
    bbox: list[float] | None
    source_type: str
```

在 `_normalize_mineru_middle_json()` 和 `_normalize_native_pages()` 中，把 block 文本继续拆成 line：

```python
for block in page.blocks:
    block_text = normalize_text(block.text)
    for line_index, line in enumerate(split_preserve_lines(block_text)):
        start = cursor
        merged_parts.append(line)
        cursor += len(line)
        spans.append({
            "start": start,
            "end": cursor,
            "page_no": page_no,
            "block_id": block_id,
            "line_no": line_index + 1,
            "bbox": estimate_line_bbox(block.bbox, line_index, line_count),
            "source_type": "ocr_line",
        })
```

如果 OCR 后端本身已经给了 line bbox，就直接使用；如果只给 block bbox，可以先按行数等分估算，后续再替换为真实 line bbox。

第二步，新增一个 evidence 对齐模块：

```text
src/danbao_poc/evidence_aligner.py
```

核心函数：

```python
def align_quote_to_document(
    quote: str,
    normalized_text: str,
    char_spans: list[TextSpan],
    min_coverage: float = 0.85,
    min_density: float = 0.65,
) -> EvidenceAlignment:
    ...
```

对齐策略按从简单到复杂：

1. 原文直接 `find()`，能找到就返回 `exact`。
2. 去空格、去换行、全角半角归一后再找，返回 `normalized_exact`。
3. LCS 对齐，计算 coverage 和 density。
4. 低于阈值返回 `failed`，不要假装有证据。

### 2.4 改完效果

- 字段抽取、知识抽取、QA 引用都能共用同一套证据定位。
- OCR 中多出来的空格、换行不会导致 evidence 失效。
- 前端后续可以做到行级高亮，而不是只跳到页。

---

## 3. 目录识别与章节分块层：目录是骨架，不能只靠 LLM 猜

### 3.1 你现在怎么做

当前核心在：

- `src/danbao_poc/catalog_chunker.py`
  - `build_catalog_driven_chunks()` 负责目录驱动分块。
  - 先抽 heading candidate，再让 LLM 规划目录，再映射回 `merged_text`。

这个方向是对的。担保文档、产品方案、制度条款通常有自然目录，用目录切比纯长度切更适合。

问题在于：LLM 目录规划如果漏标题、改标题、合并标题，后面的 chunk 边界就会受影响。表格、附件、编号条款也容易被误切。

### 3.2 可以借鉴什么

**借鉴 KnowFlow 的 AST/结构块保护**

KnowFlow 对 Markdown、表格、代码、列表会先形成结构树，再按结构树切。迁移到你的项目，不一定要完整引入 markdown-it，但要借鉴一个原则：表格、附件清单、编号条款块要先保护，再交给目录规划。

**借鉴 LangExtract 的窗口前缀上下文**

LangExtract 处理长文本时，会在当前 chunk 前面带一点前一个 chunk 的尾部上下文，避免模型在边界处丢信息。

**借鉴 Graphify 的自适应重试**

Graphify 的 LLM 输出失败后，不是直接报错，而是把输入切小再试。目录规划也可以这样：整篇规划失败，就按页或大章节窗口规划，再合并。

### 3.3 具体怎么改

第一步，给 `catalog_chunker.py` 增加结构块保护。

在构建 `merged_text` 前，先识别这些 protected block：

```python
PROTECTED_BLOCK_TYPES = {
    "table",
    "table_caption",
    "appendix_table",
    "numbered_clause_group",
    "signature_block",
}
```

识别规则可以先简单做：

- 连续多行都包含 `|`、`\t` 或多列空格，判为 table。
- 连续编号如 `1.`、`1.1`、`（一）`、`第一条`，判为 numbered clause group。
- 包含 `附件`、`附表`、`清单` 且后续多行短文本，判为 appendix block。

目录映射时加一个约束：

```python
def adjust_boundary_away_from_protected_block(start, end, protected_blocks):
    # 如果边界落在 protected block 中间，就扩到 block 边界
    ...
```

第二步，目录规划从“一次整篇”改成“整篇优先，失败后窗口化”：

```python
catalog = plan_catalog_whole_document(text)
if not is_valid_catalog(catalog):
    windows = split_by_pages_or_candidates(text)
    partial_catalogs = [
        plan_catalog_window(
            window_text=w.text,
            previous_tail=w.previous_tail,
            candidate_headings=w.candidates,
        )
        for w in windows
    ]
    catalog = merge_partial_catalogs(partial_catalogs)
```

第三步，给目录结果做硬校验：

```python
def validate_catalog_item(item, heading_candidates, merged_text):
    checks = {
        "has_title": bool(item.title),
        "can_locate_anchor": locate_anchor(item, merged_text) is not None,
        "not_inside_protected_block": not boundary_inside_protected(item),
        "range_not_too_small": item.end_char - item.start_char > min_chars,
    }
    return checks
```

### 3.4 改完效果

- 表格、附件、编号条款更不容易被切碎。
- 长文档目录识别失败率降低。
- 分块边界更稳定，后面的字段抽取和检索都会受益。

---

## 4. 章节树与多粒度 chunk 层：小 chunk 用来找，parent 用来答

### 4.1 你现在怎么做

当前核心在：

- `src/danbao_poc/chunk_generation.py`
  - `build_multigranularity_chunks()` 生成 `small_chunk`、`section_chunk`、`parent_chunk`。
- MySQL 中已经有 chunk 表和关系表：
  - `kb_chunk`
  - `file_chunk_relations`
  - `primary_chunk_id`

你的项目其实已经有“多粒度 chunk”的雏形。现在缺的不是生成 parent，而是在检索时真正把 parent 用起来。

### 4.2 可以借鉴什么

**借鉴 KnowFlow 的父子检索**

KnowFlow 的核心做法可以用一句话解释：

> 用小 chunk 找得准，用 parent chunk 答得全。

也就是：

1. ES/向量先召回 child chunk。
2. 根据 child 的行范围或 parent id 找到 parent chunk。
3. 最终给 LLM 的上下文优先使用 parent。
4. 引用仍然保留 child 命中的精确位置。

**借鉴 RAG-Pro 的 parent/child 尺寸思想**

RAG-Pro 里常见做法是 parent 比 child 大 2 到 4 倍。你的项目不一定要按 token 精确复刻，但可以保留这个比例：

- child：适合召回，短，聚焦。
- parent：适合回答，完整，带标题和上下文。

### 4.3 具体怎么改

第一步，明确 chunk 角色。

建议在 chunk metadata 里统一写入：

```json
{
  "retrieval_role": "child",
  "context_role": "parent",
  "parent_chunk_id": "...",
  "section_id": "...",
  "section_path": ["产品介绍", "准入条件"],
  "char_start": 1234,
  "char_end": 1888,
  "line_start": 30,
  "line_end": 42
}
```

第二步，生成 child-parent 关系时，不只靠目录层级，也要靠字符区间包含：

```python
def link_child_to_parent(child, parent):
    return (
        child.file_id == parent.file_id
        and parent.start_char <= child.start_char
        and child.end_char <= parent.end_char
    )
```

如果一个 child 被多个 parent 包含，选最小的那个 parent，也就是最贴近的上级上下文。

第三步，在检索组装时改 EvidenceGroup。

当前 `query.py` 的 `build_evidence_groups()` 已经按 `primary_chunk_id` 聚合。建议把一个 evidence group 拆成两个概念：

```python
EvidenceGroup(
    retrieval_hit_chunk=child_chunk,      # 命中的小块
    answer_context_chunk=parent_chunk,    # 给模型看的大块
    citation_span=child_aligned_span,     # 引用仍然指向小块或原文位置
)
```

第四步，在 `retrieve_service.py` 增加开关：

```yaml
retrieval:
  parent_context:
    enabled: true
    replace_child_context: true
    max_parent_chars: 4000
    keep_child_quote: true
```

### 4.4 改完效果

- “保证金比例是多少”这种问题仍然能靠小块精准命中。
- “这个产品准入条件有哪些”这种问题回答会更完整，因为给模型的是整段 parent。
- 引用不会变粗，仍然能指到具体命中的句子。

---

## 5. 章节摘要层：摘要不是给人看的，是给检索路由用的

### 5.1 你现在怎么做

当前章节摘要主要服务于：

- ES 的 `section_summary` 索引。
- 检索中的 `section_summary` 通道。
- 回答时补充上下文。

这层的方向是好的，但摘要如果只是“压缩正文”，价值有限。更适合做成“路由摘要”：告诉检索系统这个章节主要回答哪些类型的问题。

### 5.2 可以借鉴什么

**借鉴 RAG-Pro 的伪问题生成**

RAG-Pro 会围绕 chunk 生成可能被用户问到的问题。这对 BM25 和 query matching 很有用。

**借鉴 Graphify 的社区摘要**

Graphify 的社区摘要关注“这一组节点共同表达什么”。迁移到章节摘要层，可以把一个章节中的字段、Anchor、关系一起总结，而不是只摘要原文。

### 5.3 具体怎么改

把章节摘要拆成三部分：

```json
{
  "section_brief": "本节说明客户准入条件、区域限制和行业要求。",
  "retrieval_keywords": ["准入条件", "区域限制", "禁入行业", "客户资质"],
  "possible_questions": [
    "哪些客户可以申请该产品？",
    "该产品支持哪些区域？",
    "哪些行业不能申请？"
  ],
  "structured_hints": {
    "fields": ["适用区域", "客户准入", "禁入行业"],
    "anchors": ["山东省", "小微企业", "禁入行业"]
  }
}
```

在 ES `section_summary` 索引里，建议把不同字段分开：

- `summary_text`
- `keywords_tks`
- `questions_tks`
- `structured_hints`

检索时：

- 用户问法接近自然语言问题，优先匹配 `questions_tks`。
- 用户输入短关键词，优先匹配 `keywords_tks`。
- 用户问“有哪些、包括哪些、限制是什么”，section summary 可以给更高权重。

### 5.4 改完效果

- 章节摘要通道不再只是“另一份正文”，而是专门为召回设计的索引。
- 对“这份方案里有没有区域限制”这种抽象问题召回更稳。
- 后续 query understanding 可以直接利用 `possible_questions` 做路由。

---

## 6. 字段抽取层：确定性字段先用规则，复杂解释再交给 LLM

### 6.1 你现在怎么做

当前核心在：

- `src/danbao_poc/extractor.py`
  - `_score_chunk_for_field()`
  - `_best_chunk_for_field()`
  - `_make_field()`
  - `extract_guarantee_plan()`

整体是规则和 LLM 混合。这个方向是对的，但不同字段应该分成两类：

- 确定性字段：金额、期限、比例、利率、文件编号、日期。
- 解释性字段：准入条件、业务流程、风险控制、反担保要求。

确定性字段如果过度依赖 LLM，容易出现格式漂移。解释性字段如果只靠规则，又容易漏。

### 6.2 可以借鉴什么

**借鉴 GraphRAG-Example 的中文正则模式**

GraphRAG-Example 对中文关系和结构有一组正则模板。你的字段抽取也可以先建立担保业务字段模板，例如：

- `担保额度[：:]?(.+)`
- `担保费率[：:]?(.+)`
- `贷款期限[：:]?(.+)`
- `适用区域[：:]?(.+)`
- `合作银行[：:]?(.+)`

**借鉴 LangExtract 的 evidence alignment**

字段值最终必须能回到原文。LLM 抽出来的字段值如果不能对齐原文，要降置信度，不能直接作为高可信字段。

### 6.3 具体怎么改

第一步，给字段配置增加抽取策略：

```python
FIELD_PROFILE = {
    "guarantee_amount": {
        "type": "amount",
        "strategy": "regex_first",
        "patterns": [
            r"担保额度[：: ]*(?P<value>[^。\n；;]+)",
            r"最高(?:担保)?额度[为不超过]*(?P<value>[^。\n；;]+)",
        ],
    },
    "access_condition": {
        "type": "long_text",
        "strategy": "llm_with_regex_hints",
        "section_keywords": ["准入", "条件", "申请人", "客户"],
    },
}
```

第二步，抽取流程改成：

```text
候选 chunk 打分
  -> 正则抽取确定性字段
  -> LLM 抽取解释性字段
  -> 字段值标准化
  -> evidence 对齐
  -> 置信度重算
```

第三步，字段置信度不要只看 LLM confidence，建议组合：

```python
confidence = (
    0.35 * source_score       # 来自强规则、弱规则、LLM
    + 0.30 * evidence_score   # exact / normalized / fuzzy / failed
    + 0.20 * chunk_score      # chunk 是否是字段相关章节
    + 0.15 * consistency_score
)
```

其中 `consistency_score` 可以检查：

- 金额是否能解析成数值。
- 日期是否是合法日期。
- 比例是否在合理范围。
- 同一字段多个来源是否冲突。

### 6.4 改完效果

- 金额、期限、费率这类字段更稳定。
- LLM 输出找不到原文时会被降权，不会悄悄进入高可信结果。
- 字段抽取结果更适合后续入图和问答。

---

## 7. 知识结构层：Anchor、Unit、Relation 要从“能抽出”变成“能合并、能检索”

### 7.1 你现在怎么做

当前核心在：

- `src/danbao_poc/knowledge_extractor.py`
  - `extract_knowledge_structure()` 抽 Anchor、Knowledge Unit、Relation。
  - `normalize_knowledge_payload()` 做基础校验。
- MySQL 里已经有：
  - `kb_anchor`
  - `kb_knowledge_unit`
  - `kb_knowledge_unit_evidence`
  - `kb_relation`
  - `kb_knowledge_candidate_pool`

这说明你的系统已经具备知识图谱的中间层。主要问题是：Anchor 合并、Relation 约束、Evidence 对齐还不够强。

### 7.2 可以借鉴什么

**借鉴 Graphify 的五阶段实体去重**

Graphify 的去重适合迁移到 Anchor 层：

1. 标准化名称。
2. 低信息名称过滤。
3. MinHash 找候选近似名称。
4. Jaro-Winkler 或编辑距离打分。
5. LLM 只仲裁模糊边界样本。

**借鉴 DataGraphX 的受约束 Schema**

DataGraphX 不让 LLM 自由生成任何节点和关系，而是给固定节点类型、关系类型。你的担保领域也应该这样做。

**借鉴 GraphRAG-Example 的中文关系模板**

对一些高频关系，不要只等 LLM 抽：

- 产品适用于区域
- 产品面向客户
- 产品限制行业
- 产品合作机构
- 产品要求反担保
- 字段属于方案

这些关系可以用规则补召回。

### 7.3 具体怎么改

第一步，建立担保领域图谱 Schema。

建议新增：

```text
src/danbao_poc/profiles/guarantee_graph_schema.py
```

示例：

```python
ALLOWED_NODE_TYPES = {
    "Product",
    "GuaranteePlan",
    "Policy",
    "Region",
    "Industry",
    "CustomerType",
    "Institution",
    "Field",
    "RiskRule",
    "DocumentSection",
}

ALLOWED_RELATION_TYPES = {
    "HAS_PLAN",
    "APPLIES_TO_REGION",
    "TARGETS_CUSTOMER",
    "EXCLUDES_INDUSTRY",
    "COOPERATES_WITH",
    "HAS_FIELD",
    "REQUIRES",
    "CONSTRAINED_BY",
    "EVIDENCED_BY",
    "MENTIONED_IN",
}
```

第二步，LLM 输出后做 Schema 过滤：

```python
def normalize_relation(raw_relation):
    relation_type = map_relation_type(raw_relation.type)
    if relation_type not in ALLOWED_RELATION_TYPES:
        return None
    if not is_allowed_pair(raw_relation.source_type, relation_type, raw_relation.target_type):
        return None
    return normalized_relation
```

第三步，增加规则关系抽取：

```python
RELATION_PATTERNS = [
    {
        "relation": "APPLIES_TO_REGION",
        "pattern": r"(适用|覆盖|支持)(?P<region>[^。\n；;]{2,40})(地区|区域|范围)?",
        "target_type": "Region",
    },
    {
        "relation": "EXCLUDES_INDUSTRY",
        "pattern": r"(禁入|限制|不支持|不得准入)(?P<industry>[^。\n；;]{2,60})(行业|领域)?",
        "target_type": "Industry",
    },
]
```

第四步，Anchor 去重不要直接合并，先写候选池：

```text
raw anchor
  -> canonical_key exact merge
  -> MinHash 找近似候选
  -> Jaro-Winkler 打分
  -> 高分自动合并
  -> 中间分写 candidate_pool
  -> LLM 或人工仲裁
```

阈值建议：

- `score >= 0.94` 自动合并。
- `0.82 <= score < 0.94` 进入候选池。
- `< 0.82` 不合并。

### 7.4 改完效果

- “鲁担数科”“山东担保数科”“省担保数科”这类别名更容易合并。
- 图谱关系不会因为 LLM 发散而变脏。
- 规则关系能补上 LLM 漏掉的显式业务关系。

---

## 8. QA 预构建层：把常见问题提前挂到证据上

### 8.1 你现在怎么做

当前已经有答案预构建思路，ES 里也有 QA 索引。QA 通道对担保产品问答很有价值，因为用户经常问的是固定问题：

- 额度是多少？
- 期限多久？
- 适用哪些客户？
- 需要什么材料？
- 有哪些准入限制？

主要问题是：QA 预构建如果只生成标准问答，和用户真实问法之间仍有差距。

### 8.2 可以借鉴什么

**借鉴 RAG-Pro 的问题生成**

RAG-Pro 会给每个 chunk 生成多个 possible questions。你的 QA 预构建可以分两类：

- 字段级 QA：围绕已抽取字段生成。
- 章节级 QA：围绕章节摘要生成。

**借鉴 LangExtract 的 evidence 校验**

预构建答案必须绑定证据。没有证据的答案可以保存，但不能作为高优先级 QA 召回结果。

### 8.3 具体怎么改

字段级 QA 示例：

```json
{
  "question": "该产品最高担保额度是多少？",
  "question_aliases": [
    "最多能担保多少钱？",
    "担保上限是多少？",
    "额度最高多少？"
  ],
  "answer": "最高担保额度为 500 万元。",
  "field_code": "guarantee_amount",
  "evidence_quote": "最高担保额度为500万元",
  "evidence_alignment_status": "exact",
  "source_chunk_id": "..."
}
```

章节级 QA 示例：

```json
{
  "question": "该产品有哪些准入条件？",
  "question_aliases": [
    "什么客户可以申请？",
    "申请这个产品要满足什么条件？"
  ],
  "answer_type": "section_summary",
  "source_section_id": "...",
  "evidence_chunk_ids": ["..."]
}
```

ES 索引建议增加：

- `question_tks`
- `question_aliases_tks`
- `answer_tks`
- `field_code`
- `evidence_alignment_status`
- `source_priority`

### 8.4 改完效果

- 对常见问法可以直接命中 QA，不必每次都从正文拼。
- 用户口语化问法更容易匹配。
- QA 的答案可解释，因为每个答案都绑定证据。

---

## 9. 图谱构建层：不要只建字段图，要建“可检索业务图”

### 9.1 你现在怎么做

当前图谱核心在：

- `src/danbao_poc/graph_builder.py`
  - `build_business_graph()` 从方案、字段、区域、产业、机构构造业务图。
- `src/danbao_poc/graph_writer.py`
  - 写入 Neo4j。

现在的图谱更偏“把结构化结果可视化存起来”。但检索时，图谱应该能回答关系型问题，例如：

- 某产品适用哪些区域？
- 哪些产品限制某行业？
- 哪些字段共同约束准入？
- 某机构参与哪些产品？

### 9.2 可以借鉴什么

**借鉴 DataGraphX 的条件关系搜索**

DataGraphX 会根据问题中是否出现关系词，触发不同图查询。比如用户问“适用于哪些区域”，就应该查 `APPLIES_TO_REGION`，而不是只做向量检索。

**借鉴 Graphify 的社区/邻域扩展**

Graphify 会从种子节点出发扩展邻居，再做过滤。你的图谱检索也可以先找到产品、区域、机构等种子节点，再扩展一跳或两跳关系。

### 9.3 具体怎么改

第一步，给问题识别关系意图：

```python
GRAPH_INTENT_PATTERNS = [
    ("APPLIES_TO_REGION", ["适用区域", "覆盖区域", "哪些地区", "区域范围"]),
    ("TARGETS_CUSTOMER", ["适用客户", "客户类型", "哪些客户", "准入对象"]),
    ("EXCLUDES_INDUSTRY", ["禁入行业", "限制行业", "不支持行业"]),
    ("COOPERATES_WITH", ["合作银行", "合作机构", "经办机构"]),
    ("REQUIRES", ["需要", "要求", "材料", "条件"]),
]
```

第二步，图检索不只返回节点文本，要返回可读三元组：

```json
{
  "source": "鲁担惠农贷",
  "relation": "APPLIES_TO_REGION",
  "target": "山东省",
  "evidence_chunk_id": "...",
  "evidence_quote": "适用区域为山东省内...",
  "confidence": 0.91
}
```

第三步，图通道结果进入 EvidenceGroup：

```python
graph_hits = neo4j_store.search_relations(
    product_scope=product_scope,
    relation_types=detected_relation_types,
    anchor_terms=query_terms,
)

for hit in graph_hits:
    candidates.append(RetrievalCandidate(
        channel="graph_relation",
        chunk_id=hit.evidence_chunk_id,
        score=hit.confidence,
        structured_payload=hit.triple,
    ))
```

### 9.4 改完效果

- 图谱通道不再只是“附加上下文”，而是能直接召回关系证据。
- 对“哪些、属于、适用、限制、合作、要求”这类关系问题更准。
- 图谱结果可以反过来增强正文检索，把 evidence chunk 拉进候选池。

---

## 10. 质量报告与校验层：每层都要能说清楚“我有没有做对”

### 10.1 你现在怎么做

当前已有解析层报告和校验逻辑，这是很好的方向。现在可以继续补充更贴近业务质量的指标。

### 10.2 可以借鉴什么

**借鉴 LangExtract 的对齐状态**

对每条字段、知识单元、QA，都记录 evidence 对齐结果：

- `exact`
- `normalized_exact`
- `fuzzy_aligned`
- `failed`

**借鉴 RAG-Pro 的置信度组合**

RAG-Pro 会把多条检索结果的最高分和平均分合成 confidence。你的检索和抽取也可以用类似方式给出“整体可信度”。

**借鉴 Graphify 的解析报告**

Graphify 会区分成功、失败、跳过、增量未变化。你的批处理也应该输出这些状态。

### 10.3 具体怎么改

建议报告里增加这些指标：

| 指标 | 含义 | 用途 |
|---|---|---|
| `parse_cache_hit_rate` | 文件解析缓存命中率 | 判断是否节省 OCR |
| `line_span_coverage` | 有 line bbox 的文本占比 | 判断坐标定位能力 |
| `catalog_locate_success_rate` | 目录项成功映射比例 | 判断目录规划质量 |
| `protected_block_split_count` | 表格/附件被切断次数 | 判断分块是否破坏结构 |
| `field_evidence_exact_rate` | 字段证据精确命中比例 | 判断字段可信度 |
| `knowledge_evidence_aligned_rate` | 知识证据对齐比例 | 判断知识抽取可信度 |
| `anchor_dedup_candidate_count` | Anchor 模糊候选数量 | 判断是否需要人工审核 |
| `relation_schema_reject_count` | 被 Schema 拒绝的关系数 | 判断 LLM 是否发散 |
| `parent_context_hit_rate` | 检索命中 child 后找到 parent 的比例 | 判断父子分块是否可用 |
| `qa_evidence_failed_count` | 预构建 QA 无证据数量 | 判断 QA 是否可发布 |

### 10.4 改完效果

- 不用靠人工翻日志判断解析质量。
- 每次优化后能看到指标变化。
- 批量产品导入时，可以先拦截低质量文件。

---

## 11. 持久化与索引层：MySQL 存事实，ES 存召回线索，Neo4j 存关系

### 11.1 你现在怎么做

当前存储分工大体是：

- MySQL：文件、chunk、字段、知识单元、evidence、关系。
- ES：chunk、field、QA、section summary、anchor、knowledge unit。
- Neo4j：业务图谱。

这个分工是合理的。优化点在于每种存储都要放它最擅长的东西。

### 11.2 可以借鉴什么

**借鉴 RAG-Pro 的关键词和伪问题索引**

RAG-Pro 的优势是让 chunk 不只靠正文召回，还靠关键词和可能问题召回。

**借鉴 KnowFlow 的 rank_feature 思想**

KnowFlow 会把重要关键词、标签等作为排序特征。你的 ES 版本如果不方便用 `rank_feature`，也可以先把它实现成字段权重。

**借鉴 Graphify 的内容 hash**

每个解析产物、chunk、知识单元都可以有 hash，避免重复写入和重复索引。

### 11.3 具体怎么改

chunk 入库时增加 enrichment：

```json
{
  "keywords": ["担保额度", "准入条件", "山东省"],
  "possible_questions": [
    "该产品担保额度是多少？",
    "该产品适用哪些区域？"
  ],
  "business_terms": ["小微企业", "反担保", "合作银行"],
  "source_priority": "primary",
  "parent_chunk_id": "...",
  "content_hash": "..."
}
```

ES chunk 索引建议增加字段：

```json
{
  "keywords_tks": "担保额度 准入条件 山东省",
  "questions_tks": "该产品担保额度是多少 该产品适用哪些区域",
  "business_terms_tks": "小微企业 反担保 合作银行",
  "source_priority": "primary",
  "parent_chunk_id": "...",
  "retrieval_role": "child"
}
```

召回时分字段权重：

```python
bm25_fields = [
    ("content_for_bm25", 1.0),
    ("keywords_tks", 1.5),
    ("questions_tks", 1.3),
    ("business_terms_tks", 1.2),
    ("section_path_tks", 1.1),
]
```

### 11.4 改完效果

- 用户用短词问，关键词字段更容易命中。
- 用户用完整问题问，伪问题字段更容易命中。
- ES 召回更像“业务检索”，不只是普通全文检索。

---

## 12. 查询理解层：短问题不要乱改，长问题才整理

### 12.1 你现在怎么做

当前检索服务里有 query understanding 和 query assist 的能力，能做问题扩展、字段识别、产品范围控制。

问题是：不是所有查询都应该改写。担保业务里很多短问题非常精准：

- “费率”
- “额度”
- “鲁担惠农贷期限”
- “反担保”
- “准入条件”

这种短问题一旦被 LLM 改写，可能反而变宽、变偏。

### 12.2 可以借鉴什么

**借鉴 RAG-Pro 的条件性查询改写**

RAG-Pro 的做法是：短查询不改写，长查询或复杂查询才改写。

### 12.3 具体怎么改

建议加一个硬规则：

```python
def should_rewrite_query(query: str) -> bool:
    q = query.strip()
    if len(q) <= 50:
        return False
    if looks_like_exact_field_query(q):
        return False
    if contains_product_name_and_field(q):
        return False
    return True
```

对短问题只做轻量解析：

```json
{
  "original_query": "额度",
  "rewrite_query": null,
  "keywords": ["额度", "担保额度", "最高额度"],
  "field_intents": ["guarantee_amount"],
  "relation_intents": [],
  "rewrite_enabled": false
}
```

对长问题才改写：

```json
{
  "original_query": "我们想了解这个产品对农业企业申请时有哪些限制以及额度期限大概是什么",
  "rewrite_query": "农业企业申请该担保产品的准入限制、担保额度和期限是什么？",
  "keywords": ["农业企业", "准入限制", "担保额度", "期限"],
  "field_intents": ["access_condition", "guarantee_amount", "loan_term"],
  "rewrite_enabled": true
}
```

### 12.4 改完效果

- 短查询不会被 LLM 破坏。
- 长查询仍然可以被整理成更适合检索的形式。
- 用户输入字段名、产品名时，召回更稳定。

---

## 13. 多通道召回层：保留六通道，但让每个通道职责更清楚

### 13.1 你现在怎么做

当前 `retrieve_service.py` 已经有六路召回：

- QA
- structured field
- section summary
- graph
- BM25
- vector

这比很多参考项目已经完整。优化重点不是再加更多通道，而是明确每个通道适合解决什么问题。

### 13.2 可以借鉴什么

**借鉴 RAG-Pro 的 RRF 融合**

RAG-Pro 默认用 RRF，因为不同通道分数尺度不一样。你的项目已经有 `weighted_rrf_fuse()`，但可以把 RRF 作为稳定默认。

**借鉴 DataGraphX 的关系触发**

当问题是关系型问题时，graph 通道应该加权，而不是所有问题都平均对待。

**借鉴 GraphRAG-Example 的正则补召回**

当问题里有明确中文关系词时，可以从结构化关系和正则关系中补候选。

### 13.3 具体怎么改

给通道设置意图权重：

```python
CHANNEL_WEIGHTS_BY_INTENT = {
    "field_lookup": {
        "structured": 1.6,
        "qa": 1.3,
        "bm25": 1.0,
        "vector": 0.8,
    },
    "relation_lookup": {
        "graph": 1.7,
        "knowledge_unit": 1.2,
        "bm25": 1.0,
        "vector": 0.8,
    },
    "semantic_summary": {
        "section_summary": 1.4,
        "vector": 1.2,
        "bm25": 1.0,
    },
}
```

融合默认使用 weighted RRF：

```python
fused = weighted_rrf_fuse(
    channel_results=results_by_channel,
    weights=channel_weights,
    k=60,
)
```

分数型融合可以保留为实验参数：

```yaml
retrieval:
  fusion:
    default: weighted_rrf
    experimental_score_aware: false
```

### 13.4 改完效果

- 不同召回通道的分数不再互相污染。
- 关系问题更容易走 graph。
- 字段问题更容易走 structured 和 QA。

---

## 14. Rerank 与候选过滤层：先保召回，再做排序

### 14.1 你现在怎么做

当前已有 rerank，并且会结合字段、关键词优先级。问题是如果候选本身上下文不足，rerank 再强也只能在坏候选里排序。

### 14.2 可以借鉴什么

**借鉴 KnowFlow 的 child-to-parent rerank 前后分工**

KnowFlow 的关键点是：

- rerank 前可以用 child，保证精确。
- 送给回答前要换成 parent，保证完整。

**借鉴 RAG-Pro 的置信度公式**

不要只看 top1 分数，也要看 top 候选之间是否一致。

### 14.3 具体怎么改

建议顺序：

```text
多通道召回 child candidates
  -> RRF 融合
  -> rerank child candidates
  -> child 去重
  -> parent 扩展
  -> answer context 去重
  -> evidence group 构建
```

置信度可以这样算：

```python
confidence = 0.6 * top_score + 0.4 * average_top_scores
```

再加惩罚项：

```python
if evidence_alignment_status == "failed":
    confidence *= 0.6
if parent_context_missing:
    confidence *= 0.85
if product_scope_mismatch:
    confidence *= 0.2
```

### 14.4 改完效果

- 排序更稳定。
- 命中证据但上下文不足的问题减少。
- 可以给前端展示“高可信、一般可信、低可信”。

### 14.5 已落地改法

这层已经完成两块：

1. `query.py:resolve_weighted_rrf_config()` 默认策略改成 `weighted_rrf`，也就是 RAG-Pro 的 RRF 思路。不同通道不再直接比原始分数，而是按“各通道排名 + 通道权重”融合，BM25 的 20 分和向量的 0.8 分不会因为量纲不同互相污染。
2. 新增 `retrieval_confidence.py`，核心公式直接借鉴 `RAG-Pro/backend/app/core/confidence.py`：

```python
confidence = 0.6 * top_score + 0.4 * average_top_scores
```

然后结合本项目自己的证据质量做惩罚：

- top evidence group 没有 `answer_context_chunk`，说明 child 命中了但 parent/section 上下文没拿到，置信度乘 `0.85`。
- 没有有效 `evidence_items` 文本，说明引用展示不稳，置信度乘 `0.75`。
- 文件名和用户明确提到的产品/方案不匹配，说明可能跨产品误召回，置信度乘 `0.2`。
- 如果后续 evidence alignment 状态进入 evidence group，`failed` 会乘 `0.6`。

接口实际变化：

- `retrieve_service.py` 在 evidence group enriched 和 diversity 之后调用 `compute_retrieval_confidence()`。
- `/api/v1/retrieve/query`、`/api/v1/retrieve` 响应新增：
  - `confidence`
  - `confidence_label`
  - `confidence_factors`
- `debug.confidence` 会说明 top score、平均分、惩罚原因。

通俗地说：以前系统只告诉你“我找到了这些结果”；现在会额外告诉你“这些结果有多稳，为什么稳或为什么不稳”。

---

## 15. 证据组装层：引用要指小块，回答要看大块

### 15.1 你现在怎么做

当前 `query.py` 里有 `build_evidence_groups()`，会把候选按 `primary_chunk_id` 聚合。这个设计已经接近正确方向。

缺口是：EvidenceGroup 需要同时保存“命中的证据”和“给模型看的上下文”。现在这两个概念容易混在一起。

### 15.2 可以借鉴什么

**借鉴 KnowFlow 的引用插入**

KnowFlow 会把检索结果转成带引用 ID 的上下文，让模型回答时可以引用 `[ID:1]`。

**借鉴 LangExtract 的字符 span**

引用不应该只到 chunk，而应该尽量到原文字符区间、页码、bbox。

### 15.3 具体怎么改

EvidenceGroup 建议结构：

```json
{
  "group_id": "g1",
  "retrieval_hit": {
    "chunk_id": "child_123",
    "quote": "最高担保额度为500万元",
    "char_start": 120,
    "char_end": 132,
    "page_no": 3,
    "bbox": [100, 220, 500, 245]
  },
  "answer_context": {
    "chunk_id": "parent_45",
    "text": "二、产品要素\n本产品最高担保额度为500万元...",
    "section_path": ["产品要素"]
  },
  "source": {
    "file_id": "...",
    "file_name": "...",
    "product_name": "..."
  },
  "scores": {
    "retrieval_score": 0.83,
    "rerank_score": 0.91,
    "evidence_score": 1.0
  }
}
```

给 LLM 的上下文可以格式化成：

```text
[证据1]
来源：鲁担惠农贷产品方案 / 产品要素 / 第3页
命中句：最高担保额度为500万元
上下文：
二、产品要素
本产品面向...
最高担保额度为500万元...
```

### 15.4 改完效果

- 模型回答更完整。
- 引用仍然精确。
- 前端展示来源时更清晰。

---

## 16. 回答生成与引用层：先答业务，再给证据，不要让模型自由编引用

### 16.1 你现在怎么做

当前重点在检索服务和 evidence groups。回答层如果后续要完善，建议把引用协议固定下来。

### 16.2 可以借鉴什么

**借鉴 KnowFlow 的 insert_citations**

KnowFlow 会把引用 ID 插到回答中，引用来源来自检索结果，而不是让模型自己编。

**借鉴 grain_agent_showcase 的 SSE 消息格式**

grain_agent_showcase 作为前端示例，最值得借鉴的是消息流协议：思考、正文、引用、结束事件分开。

### 16.3 具体怎么改

回答 prompt 中明确要求：

```text
你只能使用给定证据回答。
每个关键结论后必须引用证据编号，例如 [1]。
如果证据不足，直接说明未在资料中找到。
不要编造文件名、页码、金额、期限。
```

后端不要完全相信模型引用，回答后做一次引用校验：

```python
used_citation_ids = parse_citations(answer_text)
valid_ids = {e.id for e in evidence_groups}
invalid_ids = used_citation_ids - valid_ids
if invalid_ids:
    answer_text = remove_invalid_citations(answer_text)
```

如果做流式接口，事件可以分成：

```text
event: answer_delta
event: citation
event: evidence_group
event: done
event: error
```

### 16.4 改完效果

- 引用不会乱编。
- 前端可以边生成边展示来源。
- 业务回答更像“有依据的答复”，而不是普通聊天。

---

## 17. 前端与交互层：让用户看见系统为什么这么答

### 17.1 你现在怎么做

当前主要工作集中在后端解析和检索。前端如果只展示最终答案，用户很难判断答案是否可靠。

### 17.2 可以借鉴什么

**借鉴 grain_agent_showcase 的静态前端包装**

它不是复杂系统，但提供了一个很实用的方向：把 API 响应拆成对话、引用、状态展示。

**借鉴 KnowFlow 的文档坐标追溯**

如果后端能提供 page、bbox、char span，前端就可以做到“点引用跳转到原文位置”。

### 17.3 具体怎么改

前端展示建议至少有三块：

```text
回答正文
  关键结论 + 引用编号

证据列表
  文件名 / 页码 / 章节 / 命中句 / 可信度

原文预览
  点击证据后定位到页码和高亮区域
```

后端 API 需要返回：

```json
{
  "answer": "...",
  "citations": [
    {
      "id": 1,
      "file_id": "...",
      "file_name": "...",
      "page_no": 3,
      "bbox": [100, 220, 500, 245],
      "quote": "最高担保额度为500万元",
      "confidence": 0.93
    }
  ],
  "debug": {
    "channels": ["qa", "structured", "bm25"],
    "fusion": "weighted_rrf",
    "parent_context_enabled": true
  }
}
```

### 17.4 改完效果

- 用户能看到答案依据。
- 业务人员能快速判断是否可信。
- 低质量解析、低质量 evidence 会更容易暴露出来。

---

## 18. 推荐实施顺序

### 第一批：先解决检索可用性

目标：让问答质量最快提升。

建议改动：

1. `retrieve_service.py` 增加短查询不改写规则。
2. `query.py` 的融合默认切到 `weighted_rrf`。
3. `build_evidence_groups()` 增加 child 命中、parent 上下文扩展。
4. MySQL 增加或复用 child-parent 关系查询。

预期效果：

- 短问题更稳定。
- 回答上下文更完整。
- 不需要大改解析流程，能较快上线。

落地标注：

- 已完成 `retrieve_service.py:_query_rewrite_guard()`：默认对短问题、明确字段问题不走 LLM 改写，避免“额度多少”被改坏。
- 已完成 `query.py:resolve_weighted_rrf_config()`：默认融合策略从 `score_aware` 切到 `weighted_rrf`，借鉴 RAG-Pro 的 RRF 排名融合，仍允许请求参数和 MySQL profile 覆盖。
- 已完成 `retrieve_service.py:_enrich_evidence_groups()`：child chunk 负责命中，回答前加载 parent/section context；响应里同时有 `retrieval_hit_chunk` 和 `answer_context_chunk`。
- 已完成 `mysql_store.py:load_related_chunks()` 复用现有 child-parent 关系，不额外新建一套检索结构。

### 第二批：补证据对齐和坐标

目标：让抽取和引用更可信。

建议改动：

1. 新增 `evidence_aligner.py`。
2. 字段抽取、知识抽取、QA 预构建统一调用 evidence aligner。
3. `document_parser.py` 增加 line span。
4. `file_char_map` 写入 line-level 信息。

预期效果：

- evidence 不再只靠字符串包含。
- OCR 换行、空格导致的引用失败明显减少。
- 后续前端可以行级高亮。

落地标注：

- 已完成 `evidence_aligner.py`：支持 `exact`、`normalized_exact`、`fuzzy_aligned`、`failed` 四类结果。
- 已完成 `extractor.py`、`knowledge_extractor.py`、`answer_prebuilder.py` 接入 evidence alignment；失败时会降低置信度或保留失败状态，便于报告和前端提示。
- 已完成 `document_parser.py`、`paddle_normalizer.py`：把原来的 block 坐标细化为 line span，记录 `line_no`、`global_char_start/end`、`bbox/positions`。
- 已完成 `parse_service.py` 质量报告指标：新增 evidence exact/aligned rate、line span coverage 等指标。

### 第三批：增强索引召回

目标：让 BM25、QA、section summary 更懂业务问法。

建议改动：

1. chunk 生成后补 `keywords`、`possible_questions`。
2. ES chunk 和 section summary 增加 `keywords_tks`、`questions_tks`。
3. QA 预构建增加 `question_aliases`。
4. 检索时按 query intent 调整通道权重。

预期效果：

- 用户换一种问法也能召回。
- 章节摘要通道更有用。
- 字段型问题命中更快。

落地标注：

- 已完成 `chunk_generation.py:_extract_keywords()`、`_generate_questions()`：从 chunk 正文提取业务关键词和可回答问题。
- 已完成 `es_store.py`：chunk 索引新增 `keywords`、`possible_questions`、`keywords_tks`、`questions_tks`，BM25 查询提高这些字段权重。
- 已完成 `section_builder.py`：章节摘要增加 `retrieval_keywords`、`possible_questions`、`structured_hints`，并写入 section summary ES 索引。
- 已完成 `extractor.py` 字段规则优先：对金额、期限、对象、范围等确定性字段先走正则，再和 LLM 结果合并，减少“明文字段抽错”。

### 第四批：增强知识结构和图谱

目标：让系统能回答关系型问题。

建议改动：

1. 新增担保领域图谱 Schema。
2. LLM relation 输出做 Schema 过滤。
3. 增加中文正则关系抽取。
4. Anchor 增加 MinHash + Jaro-Winkler 去重候选池。
5. 图检索增加关系意图触发。

预期效果：

- 图谱噪声降低。
- “适用哪些区域、限制哪些行业、合作哪些机构”这类问题更准。
- Anchor 别名和重复实体更容易治理。

落地标注：

- 已完成 `knowledge_extractor.py` 关系 Schema 过滤：LLM 输出不在担保领域 Schema 内的关系会被拒绝，并计入质量报告。
- 已完成 `relation_rule_extractor.py`：用中文规则补抽 `IN_REGION`、`HAS_LIMIT`、`HAS_TERM`、`REQUIRES`、`RELATED_TO` 等高频业务关系。
- 已完成 `anchor_deduper.py`：标准化名称后自动合并明显重复 Anchor；近似名称先写候选信息，不直接冒险合并。
- 已完成 `graph_intent.py` 和 `query.py:graph_query()` 增强：即使用户没问具体字段，只要问“涉及哪些区域/机构/限制”，也可以触发图谱关系检索。

### 第五批：补解析缓存和流式体验

目标：提高批量处理效率和前端体验。

建议改动：

1. 增加 `file_parse_cache`。
2. `parse_document()` 支持内容 hash 命中缓存。
3. 回答接口支持 SSE。
4. 前端展示 citation、evidence group、debug channel。

预期效果：

- 重复解析成本下降。
- 批量导入更快。
- 用户体验更接近可用产品。

落地标注：

- 已完成 `mysql_store.py` 的 `file_parse_cache` 表初始化、`load_parse_cache()`、`save_parse_cache()`。
- 已完成 `parse_service.py` 缓存命中：按文件 hash、profile、parser、parser_version、options hash 复用 `middle_document/raw_payload`，跳过重复 OCR/解析。
- 已完成 `citation_formatter.py`：优先展示 parent answer context，同时保留 child retrieval hit，引用更接近 KnowFlow 的“命中小块、引用大块”模式。
- 已完成 `retrieve_service.py` SSE 接口：`/api/v1/retrieve/query/stream` 和 `/api/v1/retrieve/stream` 输出 `stage/references/result/done/error`。
- 已完成 `retrieval_confidence.py`：借鉴 RAG-Pro `0.6 * top_score + 0.4 * avg_score`，再结合 parent context、证据文本、产品范围匹配做惩罚；响应新增 `confidence`、`confidence_label`、`confidence_factors`。

---

## 19. 最建议先落地的 5 个代码包

如果只选最少改动、最大收益，建议先做这 5 个包。

### 19.1 `evidence_aligner.py`

状态：已完成。

作用：

- 统一字段、知识单元、QA 的证据定位。
- 支持 exact、normalized exact、fuzzy LCS、failed。

被谁调用：

- `extractor.py`
- `knowledge_extractor.py`
- `answer_prebuilder.py`
- `query.py`

### 19.2 `parent_context_resolver.py`

状态：已完成核心能力，但没有单独拆文件；实际落在 `retrieve_service.py:_enrich_evidence_groups()`，这样改动更小，也更贴近当前服务入口。

作用：

- 输入 child chunk ids。
- 查询 parent chunk。
- 返回 answer context chunk。

被谁调用：

- `retrieve_service.py`
- `query.py`

核心逻辑：

```python
def resolve_parent_context(child_chunks, max_chars=4000):
    parent_ids = collect_parent_ids(child_chunks)
    parents = mysql_store.load_chunks_by_ids(parent_ids)
    return choose_best_parent_for_each_child(child_chunks, parents, max_chars)
```

### 19.3 `query_rewrite_guard.py`

状态：已完成核心能力，但没有单独拆文件；实际落在 `retrieve_service.py:_query_rewrite_guard()`。

作用：

- 判断是否允许 LLM 改写。
- 短查询、字段查询、产品名查询默认不改写。

被谁调用：

- `retrieve_service.py`

### 19.4 `chunk_enrichment.py`

状态：已完成核心能力，实际落在 `chunk_generation.py`、`section_builder.py`、`es_store.py`。

作用：

- 为 chunk 生成关键词、业务术语、可能问题。
- 写入 MySQL metadata 和 ES 索引字段。

被谁调用：

- chunk 生成后
- ES 索引前

### 19.5 `relation_rule_extractor.py`

状态：已完成。

作用：

- 用中文正则补充高频业务关系。
- 和 LLM relation 合并。
- 做 Schema 校验。

被谁调用：

- `knowledge_extractor.py`
- `graph_builder.py`

实际调用说明：当前已经由 `knowledge_extractor.py` 调用；图谱写入仍沿用现有 graph writer 链路，不额外新建 `graph_builder.py`。

### 19.6 `retrieval_confidence.py`

状态：已完成，属于这次补充。

作用：

- 借鉴 RAG-Pro 的 `compute_confidence()`，用 top score 和平均分共同判断检索质量。
- 结合本项目的 parent context、证据文本、产品范围匹配做惩罚。
- 给前端和调用方返回 `confidence/confidence_label/confidence_factors`。

被谁调用：

- `retrieve_service.py`

核心逻辑：

```python
base_confidence = 0.6 * top_score + 0.4 * average_top_scores
confidence = base_confidence * penalty_factor
```

效果：

- 可以区分“召回很多但不稳”和“top 证据很集中、上下文完整”的情况。
- 后续前端可以直接展示高/中/低/极低可信度。

---

## 20. 用一句话总结每个参考项目怎么落到你的流程里

| 参考项目 | 在你的流程里最该落的位置 | 不建议照搬的地方 |
|---|---|---|
| Graphify | Anchor 去重、增量解析、图邻域扩展 | 它不做向量 RAG，不能替代你的检索链路 |
| GraphRAG-Example | 中文关系正则、LLM JSON 解析兜底 | 它的存储和前端偏 demo，不适合直接迁移 |
| LangExtract | evidence 字符级对齐、多轮抽取校验 | 它不是完整 RAG 系统，只借鉴抽取质量控制 |
| KnowFlow | 父子检索、坐标追溯、结构块保护 | 全量 RAGFlow 架构太重，不建议整体搬 |
| RAG-Pro | RRF 默认融合、短查询保护、关键词和伪问题、检索置信度 | Milvus/稀疏向量可后置，不必第一批换库 |
| grain_agent_showcase | SSE、引用展示、前端消息协议 | 它不是检索算法来源，不要过度参考业务逻辑 |
| DataGraphX | 受约束 Schema、关系意图图检索 | 它的 Neo4j 向量方案不一定适配你当前 ES 架构 |

---

## 21. 最终建议

你的项目现在已经有很多“高级结构”，例如多通道召回、多粒度 chunk、知识单元、证据表、图谱和 ES 多索引。下一步最重要的不是继续堆功能，而是把这些结构串严密：

1. 用小 chunk 精准召回。
2. 用 parent chunk 提供完整回答上下文。
3. 用 evidence_aligner 保证每个字段、知识和答案都能回到原文。
4. 用关键词和伪问题增强 BM25 与 QA 召回。
5. 用受约束 Schema 和规则关系让图谱变成可检索资产。

这样改完以后，系统会从“能解析、能检索、能回答”提升到“回答有上下文、结论有证据、引用能定位、关系能追溯”。

---

## 22. 从可借鉴点提取出来的下一步开发清单

前面已经完成了第一轮最关键的 P0/P1：child -> parent 上下文、短查询保护、证据对齐、行级 char map、结构块保护、关键词/伪问题索引、规则关系抽取、图意图触发、SSE 引用和检索置信度。

接下来不要再从头堆一套新架构，应该沿着“已经生成的数据怎么更好用”继续做。下面按收益和风险排序。

### 22.1 下一步一：字段置信度从 HIGH/MEDIUM/LOW 改成可解释分数

状态：已完成。新增 `field_confidence.py`，按 `source/evidence/chunk/consistency` 四因子计算分数；`extractor.py` 写入 `field_confidence_score/factors/conflict`；`parse_service.py` 报告新增 `high_confidence_field_rate`、`regex_first_field_rate`、`field_conflict_count`。

借鉴来源：

- RAG-Pro：用多个分数合成一个最终 confidence。
- LangExtract：证据 alignment 状态直接影响可信度。

当前状态：

- `extractor.py` 已经有 regex-first 和 evidence alignment。
- 现在主要还是 `HIGH/MEDIUM/LOW`，alignment failed 只把 `HIGH` 降到 `MEDIUM`。
- 还没有把“规则来源、证据对齐、字段所在章节、同字段一致性”组合成一个稳定分数。

建议改法：

1. 新增 `field_confidence.py`。
2. 对每个字段计算：

```python
confidence = (
    0.35 * source_score       # regex_first > llm_with_source > llm_weak
    + 0.30 * evidence_score   # exact > normalized_exact > fuzzy_aligned > failed
    + 0.20 * chunk_score      # 字段是否来自匹配章节，如额度字段来自 credit_limit
    + 0.15 * consistency_score # 同一字段多处是否一致
)
```

3. `extractor.py:_make_field()` 写入：
   - `metadata.field_confidence_score`
   - `metadata.field_confidence_factors`
   - `confidence` 仍保留 HIGH/MEDIUM/LOW，兼容现有表结构。
4. `parse_service.py` 报告增加：
   - `high_confidence_field_rate`
   - `regex_first_field_rate`
   - `field_conflict_count`

预期效果：

- 字段审核时能知道“为什么这个字段可信/不可信”。
- 额度、期限、文号这类强规则字段会更稳。
- 后续 QA 和图谱可以优先使用高置信字段。

### 22.2 下一步二：QA 预构建结果做证据质量分层

状态：已完成。`answer_prebuilder.py` 已按 evidence alignment 输出 `exact_evidence/fuzzy_evidence/chunk_only/no_evidence`，并联动 `confidence/priority`；`es_store.py:search_qa()` 已提升 `evidence_quotes_tks`、高置信和高优先级 QA；`query.py` 会把 `evidence_quality` 带到 evidence group。

借鉴来源：

- RAG-Pro：QA 召回要有 confidence 和 extended questions。
- LangExtract：预构建答案必须能回到原文证据。

当前状态：

- `answer_prebuilder.py` 已有 `extended_questions`、`confidence`、`evidence_quotes`。
- `es_store.py` 已把 `extended_questions_tks`、`evidence_quotes_tks` 加入 QA 索引。
- 但 QA 结果还没有按证据质量明显分层：有证据、弱证据、无证据的召回优先级还可以更清楚。

建议改法：

1. 在 `answer_prebuilder.py` 里给每条 QA 增加 `evidence_quality`：
   - `exact_evidence`
   - `fuzzy_evidence`
   - `chunk_only`
   - `no_evidence`
2. 保存 QA 时按质量设置：
   - `priority`
   - `confidence`
   - `metadata_json.evidence_alignment`
3. `search_qa()` 中让 `evidence_quotes_tks`、`confidence`、`priority` 共同影响排序。
4. 在 `build_evidence_groups()` 中把 QA 的 `evidence_quality` 带到 `matched_preset_answers`。

预期效果：

- 常见问法还是快，但不会让“没证据的预生成答案”压过真实 chunk 证据。
- FAQ 类问题更适合直接回答，字段类问题仍能回到原文。

### 22.3 下一步三：Anchor 去重进入二阶段治理

状态：已完成第一版候选池。`anchor_deduper.py` 新增 `extract_anchor_merge_candidates()`，模糊候选按 `auto_accept/pending_review` 分层；`mysql_store.py` 新增 `knowledge_anchor_merge_candidate` 表并在保存解析结果时持久化候选。本轮先做候选池和自动标记，人工审核接口/LLM 仲裁可作为后续独立功能。

借鉴来源：

- Graphify：实体去重五阶段管道，尤其是 MinHash + Jaro-Winkler + LLM 仲裁。

当前状态：

- `anchor_deduper.py` 已做标准化精确合并。
- 模糊相似的 Anchor 现在只写候选标注，不自动合并，这是正确的保守策略。
- 缺的是“候选池持久化 + 人工/LLM 仲裁 + 合并回写”。

建议改法：

1. 新增 MySQL 表 `knowledge_anchor_merge_candidate`：
   - `left_anchor_id`
   - `right_anchor_id`
   - `similarity_score`
   - `similarity_reason`
   - `decision`
   - `reviewer`
2. `anchor_deduper.py` 输出候选时写入 candidate pool。
3. 增加 `anchor_merge_service.py`：
   - `auto_accept(score >= 0.94 and same_type)`
   - `pending_review(0.82 <= score < 0.94)`
   - `reject(score < 0.82)`
4. 合并时同步更新：
   - unit 的 `anchor_id`
   - relation 的 source/target
   - ES anchor/unit 索引
   - Neo4j 节点别名

预期效果：

- “鲁担惠农贷”“惠农贷”“鲁担惠农贷产品”这类重复实体能逐步收敛。
- 图谱节点度更真实，关系型检索更准。
- 不会因为激进自动合并把两个不同产品合错。

### 22.4 下一步四：解析缓存继续延伸到增量索引和增量图谱

状态：已完成轻量复用版。新增 `index_incremental.py` 计算索引快照签名；`retrieve_service.py:_run_index_file()` 在同一 parse generation 已有 synced index 时返回 `operation: reuse_previous`，跳过 ES/Neo4j 重复删写，并返回 `snapshot_hash/snapshot_row_counts/incremental_reason`。本轮先做代际级复用，chunk 级局部 upsert 可继续细化。

借鉴来源：

- Graphify：SHA256 文件级缓存、增量检测。
- DataGraphX：文件 MD5 绑定 Document 节点。

当前状态：

- `file_parse_cache` 已经能复用解析结果，跳过重复 parser/OCR。
- 但 ES 索引和 Neo4j 图谱仍偏重 rebuild 思路。
- `content_hash` 已经存在于 chunk 层，可以继续往下用。

建议改法：

1. `index_task_store` 或 `mysql_store` 中增加 chunk/index hash 对照：
   - `chunk_id`
   - `content_hash`
   - `indexed_hash`
   - `graph_hash`
2. `index_rows()` 前先 diff：
   - hash 未变：跳过 ES upsert。
   - hash 变化：只重写变更 chunk、field、QA、unit、anchor。
3. `graph_writer.py` 增加按 file/chunk 删除和局部重建：
   - 删除当前文件旧关系。
   - 只导入变更 chunk 关联的 anchors/units/relations。
4. 报告增加：
   - `index_skipped_unchanged_count`
   - `graph_skipped_unchanged_count`
   - `incremental_changed_chunk_count`

预期效果：

- 批量重复导入速度继续提升。
- 图谱不会每次全量重写，调试成本下降。
- 后续大文件、多文件知识库更容易跑得动。

### 22.5 下一步五：让 query router 真正利用 possible_questions

状态：已完成。`query.py` 新增 `possible_question_like/field_alias_exact/relation_intent_hit` 路由特征和 `route_reason`；`retrieval_plan.py` 会据此提高 QA、section_summary、structured、graph 等通道优先级；`retrieve_service.py` debug 返回 `route_reason`。

借鉴来源：

- RAG-Pro：问题改写和伪问题用于召回增强。

当前状态：

- chunk 和 section summary 已经生成 `possible_questions`。
- ES 也已经索引 `questions_tks`。
- 但查询理解层还没有显式利用“用户问题像不像某个 possible question”来调整通道。

建议改法：

1. 在 `query.py` 增加轻量路由特征：
   - `possible_question_like`
   - `field_alias_exact`
   - `relation_intent_hit`
2. `RetrievalPlanBuilder` 根据特征调权：
   - `possible_question_like=True`：提高 QA/section_summary。
   - `field_alias_exact=True`：提高 structured/bm25。
   - `relation_intent_hit=True`：提高 graph。
3. `retrieve_service.py` debug 返回 `route_reason`，例如：

```json
{
  "qa": "query matches possible question style",
  "graph": "relation intent: IN_REGION, RELATED_TO",
  "bm25": "exact field alias hit: 担保额度"
}
```

预期效果：

- 多通道召回不只是“都查一遍”，而是每条问题有明确通道职责。
- 便于后续人工调参和线上排查。

### 22.6 下一步六：引用协议从 references 扩展到答案内引用

状态：已完成。新增 `answer_context_protocol.py`，把 evidence groups 和 citations 转成 `[ref_n]` 引用块、硬规则 instruction 和 `answer_context_prompt`；`retrieve_service.py` 普通响应和 SSE `references` 事件都会返回 `answer_context`。

借鉴来源：

- KnowFlow：检索上下文插入 `[ID:n]`，回答时引用这些 ID。
- grain_agent_showcase：前端用结构化 references 展示来源。

当前状态：

- 后端已返回 `citations/references`。
- SSE 已有 `references` 事件。
- 但如果后续接回答生成，模型本身还没有被强制按 `[ref_1]`、`[ref_2]` 引用。

建议改法：

1. 新增 `answer_context_builder.py`：
   - 把 evidence groups 转成带引用 ID 的上下文。
   - 每段格式固定为 `[ref_1] 标题 / 页码 / 正文`。
2. 回答 prompt 增加硬规则：
   - 结论后必须引用 `[ref_n]`。
   - 没有证据时输出“资料中未找到明确依据”。
3. `citation_formatter.py` 支持从答案中的 `[ref_n]` 反查 citation。
4. 前端展示：
   - 高亮答案内引用。
   - 点击引用定位到 evidence group。

预期效果：

- 引用不再只是答案下面的列表，而是每个结论都能对应来源。
- 可以明显减少“答案看起来对，但不知道哪句话支持”的问题。

### 22.7 下一步七：前端调试视图展示系统为什么这么答

状态：已完成。`frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 新增检索洞察面板，展示置信度、路由标签、证据组、引用协议和 `Answer Context Prompt`；仍保留原始 JSON 方便研发排查。

借鉴来源：

- grain_agent_showcase：流式状态、references、可视化反馈。
- KnowFlow：父子 chunk 预览和编辑体验。

当前状态：

- 后端已经返回：
  - `confidence`
  - `confidence_label`
  - `confidence_factors`
  - `citations/references`
  - `evidence_groups`
  - `debug`
- 前端还没有把这些结构作为正式产品体验展示出来。

建议改法：

1. 检索结果页增加三个面板：
   - `答案依据`：展示 citations。
   - `命中证据`：展示 child retrieval hit。
   - `回答上下文`：展示 parent answer context。
2. 置信度展示：
   - high：绿色。
   - medium：黄色。
   - low/very_low：红色，并展示 penalty reasons。
3. debug 模式展示：
   - route_candidate_counts
   - fusion strategy
   - rerank_top_n
   - query_rewrite_guard
   - route_reason

预期效果：

- 业务人员能看懂系统为什么这样答。
- 研发调参不必直接看 JSON。
- 引用、置信度、父子 chunk 的价值能在界面上体现出来。

### 22.8 下一步八：图谱边权重和 BFS 子图检索

状态：已完成。`graph_writer.py` 新增 `edge_weight()` 并把 `weight` 写入 `PARSED_AS/HAS_FIELD/EVIDENCED_BY/IN_REGION/IN_INDUSTRY/RELATED_TO`；`query.py:graph_query()` 返回 `relationship_weight/graph_depth`，关系类图查询会补充 1-2 跳 BFS 子图候选并按权重、深度、scope match 排序。

借鉴来源：

- GraphRAG-Example：重复关系边权重累积、BFS depth/maxNodes 双约束。
- DataGraphX：条件触发子图搜索。

当前状态：

- 图意图和关系型 graph 查询已增强。
- 但图谱边还可以增加频率/置信度权重，子图扩展也可以更可控。

建议改法：

1. `graph_writer.py` 写关系时，如果同一边重复出现：
   - `weight += 1`
   - `evidence_count += 1`
   - `last_seen_generation = current_generation`
2. `graph_query()` 增加 BFS 参数：
   - `max_depth`
   - `max_nodes`
   - `allowed_relation_types`
3. 排序时综合：
   - relation intent match
   - edge weight
   - evidence alignment
   - file scope match

预期效果：

- 多处文档共同支持的关系排名更靠前。
- 图谱检索不会扩散得太大。
- “这个产品和哪些机构/地区/限制有关”会更稳定。

### 22.9 建议执行顺序

本轮已按下面顺序完成 1-8 项。后续如果继续扩展，建议从“Anchor 人工审核/LLM 仲裁”和“chunk 级局部 upsert”两个方向细化。

| 顺序 | 要做的事 | 借鉴来源 | 为什么先做 |
|---|---|---|---|
| 1 | 字段置信度可解释分数 | RAG-Pro + LangExtract | 字段是 QA、图谱、报告的基础，收益最大 |
| 2 | QA 证据质量分层 | RAG-Pro + LangExtract | 直接提升常见问答质量，风险小 |
| 3 | Query router 利用 possible_questions | RAG-Pro | 已经有索引字段，只差路由使用 |
| 4 | Anchor 二阶段去重候选池 | Graphify | 当前只做了第一阶段，继续做能提升图谱质量 |
| 5 | 增量索引和增量图谱 | Graphify + DataGraphX | 工程收益大，但涉及索引/图谱状态，放在质量优化后 |
| 6 | 答案内引用协议 | KnowFlow + grain_agent_showcase | 需要回答生成链路配合，适合引用结构稳定后做 |
| 7 | 前端 evidence/debug 展示 | grain_agent_showcase + KnowFlow | 后端字段已齐，属于产品化呈现 |
| 8 | 图谱边权重和 BFS 子图检索 | GraphRAG-Example + DataGraphX | 图谱质量进一步增强，适合 Anchor 治理后做 |

本轮完成后的下一批可做项：

1. Anchor 候选审核接口：把 `knowledge_anchor_merge_candidate` 做成可审核、可合并、可回滚。
2. chunk 级增量索引：从当前“代际复用”继续细化到“只 upsert 变更 chunk/field/unit/anchor”。
3. 答案生成链路：真正调用模型时强制使用 `answer_context_prompt`，并校验输出中的 `[ref_n]` 是否都存在。
