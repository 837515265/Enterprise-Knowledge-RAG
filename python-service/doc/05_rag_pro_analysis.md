# RAG-Pro 项目分析报告

## 1. 项目概述

RAG-Pro 是**本地优先的 RAG 知识库系统**，面向中英双语企业场景。提供全生命周期管理：文档上传、解析、分块、混合检索、多轮对话 QA（SSE 流式）、智能多格式输出（文本/图表/报告/网页/数据表）。

**架构**：前后端分离 — Vue 3 前端 + FastAPI 后端。单机运行（SQLite + Milvus Lite），无外部依赖。PostgreSQL + 完整 Milvus 为生产扩展选项。

---

## 2. 文件处理

**6 种格式**：

| 格式 | 解析方法 | 库 | 关键行为 |
|------|---------|---|---------|
| PDF | PyMuPDF (`fitz`) | 逐页提取，每页 → DocumentPage |
| DOCX/DOC | python-docx | **标题感知** — Heading 样式分段 |
| CSV | csv.DictReader | 每 20 行一批，`key: value` 格式 |
| TXT | 原始字节 + 编码回退 | 双换行分组段落，~2000 字符/页 |
| MD | 按 `#`/`##` 分段 | 标题分段 |

**编码处理**：`chardet` 检测 + 11 种编码级联回退（utf-8-sig → utf-16 → gb18030 → gbk → gb2312 → big5 → cp936 → latin-1），专为中文文本设计。

### 与 danbao-poc 对比

| 维度 | danbao-poc | RAG-Pro |
|------|-----------|---------|
| PDF | MinerU OCR | PyMuPDF 纯文本 |
| DOCX | python-docx | python-docx + **标题感知** |
| 编码 | UTF-8 为主 | **11 种中文编码回退** |
| CSV | 支持 | 20 行批量 + key:value 格式 |

**可借鉴**：中文编码级联回退（gb18030/gbk/gb2312/big5）

---

## 3. 文件解析

`DocumentParser` 单例，dispatcher 模式（`PARSERS` dict 映射扩展名到方法）。

所有解析器返回 `DocumentPage` 对象：`text`, `page_number`, `section_title`, `metadata`。

**解析生命周期**：
1. Upload → `parse_status = "parsing"` → 立即调用 `_parse_document`
2. 成功 → `parse_status = "parsed"`
3. 失败 → `parse_status = "failed"`，存储错误信息
4. 分块是独立步骤（用户触发）

**DOCX 标题感知**：识别 "Heading" 样式段落为章节边界，每个章节成为独立 page。无标题时整个文档为单页。

### 与 danbao-poc 对比

| 维度 | danbao-poc | RAG-Pro |
|------|-----------|---------|
| 解析触发 | 上传后立即 + 异步 worker | 上传后立即（同步） |
| 中间格式 | normalize_etl4lm_response JSON | DocumentPage dataclass |
| 错误处理 | worker 重试 | 标记 failed，用户手动重试 |

---

## 4. Chunk 划分（10 种策略）

`get_chunker(method, chunk_size, chunk_overlap, min_chunk_size)` 工厂方法。

### 4.1 RecursiveChunker（最精密基础分块器）

- **分隔符层级**：`["\n\n", "\n", ". ", "；", "。", " ", ""]`
- 递归按最高优先级分隔符切分，超限则降级
- **Token 估算**：`中文字符 / 1.5 + 其他字符 / 4`
- **Overlap**：前一个 chunk 尾部 `overlap_chars = chunk_overlap * 3` 前置到当前 chunk

### 4.2 ParentChildChunker（旗舰策略）

- **Parent chunks**（1536 tokens）：提供完整上下文，不 overlap
- **Child chunks**（512 tokens）：embedding + 检索用，有 overlap
- 检索时：child chunk → 查 DB 获取 parent 内容 → 更丰富上下文给 LLM

### 4.3 IntelligentChunker

- 正则检测文档结构：Markdown `#` 标题、中文章节标记（`第X章节部分`）、编号段（`一、`、`1.`）
- 低于 `min_chunk_size`（默认 50 tokens）的段落合并
- 超限段落回退到 RecursiveChunker

### 4.4 QAChunker

三种模式：
- `Q:/问:` + `A:/答:` 配对
- CSV `key: value` 对
- 编号项 `1. ... 2. ...`

### 4.5 TableChunker

- CSV：每行一个 chunk，前置表头上下文
- Markdown 表格：`|...|` 模式提取整表 chunk

### 4.6 BookChunker / PaperChunker / ResumeChunker

- **Book**：中文章节标题（`第X章节部篇`）或 `Chapter N`
- **Paper**：`abstract`/`摘要`/`introduction`/`引言` 等关键词
- **Resume**：`个人信息`/`教育背景`/`工作经历`/`技能` 等关键词

### 4.7 关键词和问题生成

分块时自动丰富每个 chunk：
- `_extract_keywords(text, top_k=5)`：正则提取 2+ 字符中文词或 3+ 字符英文词，按频率排序
- `_generate_questions(text, count=3)`：从句子生成伪问题（如含 "如何/怎么" → "X的具体做法是什么？"）

### 与 danbao-poc 对比

| 维度 | danbao-poc | RAG-Pro |
|------|-----------|---------|
| 策略数 | 1（LLM Planner） | **10 种** |
| 父子分块 | primary_chunk_id（简单） | **1536 parent + 512 child** |
| 关键词生成 | 无 | **top 5 关键词/chunk** |
| 问题生成 | 无 | **3 个伪问题/chunk** |
| Token 估算 | 字符数 | **中文/1.5 + 其他/4** |

**可借鉴**：
1. **关键词 + 问题生成**：每个 chunk 自动提取关键词和生成伪问题，增强 BM25 召回
2. **10 种分块策略**：按文档类型选最优策略
3. **中文章节正则检测**：`第X章节部分` 模式

---

## 5. 数据存储

### SQLite（开发）/ PostgreSQL（生产）

**7 张表**：

| 表 | 关键字段 |
|----|---------|
| `knowledge_bases` | id(UUID), name, embedding_model, chunk_size, chunk_overlap |
| `documents` | id(UUID), kb_id, filename, parse_status, chunk_method |
| `chunks` | id(UUID), doc_id, content, **parent_chunk_id**(nullable), keywords(TEXT), questions(TEXT), milvus_id |
| `conversations` | id, kb_id, title |
| `messages` | id, conversation_id, role, content(JSON), **type**(report/chart/webpage/text) |
| `llm_configs` | id, provider, model_name, api_key_encrypted |
| `shortcuts` | id, title, query_text, answer_snapshot(JSON) |

**Parent-child**：`parent_chunk_id = NULL` → 父 chunk；非 NULL → 子 chunk。列表时只显示子 chunk。

### Milvus Lite（开发）/ Milvus（生产）

**Milvus schema**：
- `id` VARCHAR 64 PK
- `chunk_id`, `doc_id` VARCHAR 64
- `dense_vector` FLOAT_VECTOR dim=1024
- `content` VARCHAR 8192
- 索引：FLAT COSINE

**内存回退**：`InMemoryVectorStore` 持久化到 `vectors.json`，支持三种搜索：
- `search`（dense cosine）
- `sparse_search`（BM25 风格 overlap 点积）
- `hybrid_search`（**RRF 融合 dense + sparse**）

### 与 danbao-poc 对比

| 维度 | danbao-poc | RAG-Pro |
|------|-----------|---------|
| 关系 DB | MySQL | SQLite/PostgreSQL |
| 向量库 | ES dense_vector | **Milvus** |
| 稀疏向量 | 无 | **有**（token_id → weight） |
| chunk 元数据 | section_type/title | **keywords + questions** |

**可借鉴**：
1. **稀疏向量**（BM25 风格 token overlap）用于混合检索
2. **chunk keywords/questions 字段**：增强 BM25 匹配

---

## 6. 检索方法

### 5 步检索管道

**Step 1：查询 Embedding**
BGE-M3 一次性生成 dense（1024 维）+ sparse（token_id → weight）向量。

**Step 2：混合搜索**
- Dense cosine 搜索 → `top_k * 2` 候选
- Sparse overlap 搜索 → `top_k * 2` 候选
- **RRF 融合**：`score(d) = Σ 1/(k + rank)`，`k=60`

**Step 3：Cross-Encoder 重排**
BAAI/bge-reranker-v2-m3 评分，归一化 0-1，取 top_n=5。

**Step 4：Parent 上下文扩展**
每个 child chunk 查 DB 获取 parent 内容，prompt 优先用 parent。

**Step 5：置信度评分**
`confidence = 0.6 * max(scores) + 0.4 * avg(scores)`
标签：high(≥0.8), medium(≥0.5), low(≥0.3), very_low(<0.3)

### Test-chat 模式

查询 >50 字符时，LLM 改写为更适合检索的形式。

### 与 danbao-poc 对比

| 维度 | danbao-poc | RAG-Pro |
|------|-----------|---------|
| 融合算法 | score_aware（score + rank 混合） | **RRF**（纯排名融合） |
| 稀疏检索 | 无（仅 BM25 via ES） | **有**（token overlap 点积） |
| 置信度 | 无统一评分 | **0.6*max + 0.4*avg** |
| 查询改写 | LLM query enhancement（默认开） | 仅 >50 字符时改写 |
| Parent 扩展 | 无 | **自动 parent 上下文** |

**可借鉴**：
1. **RRF 融合**：简单有效的排名融合
2. **稀疏向量检索**：BM25 风格的 token overlap，补充 dense 检索
3. **置信度评分公式**：`0.6*max + 0.4*avg`
4. **条件性查询改写**：仅长查询才改写，短查询保持原样

---

## 7. 核心算法亮点

### 7.1 RRF 混合搜索

```
score(chunk_id) = Σ 1/(60 + rank_dense) + Σ 1/(60 + rank_sparse)
```

标准 RRF（`k=60`），dense 提供语义相似度，sparse 提供精确关键词匹配。

### 7.2 智能 Agent 路由

`detect_intent` 用 LLM 零样本分类决定输出类型：`text` / `chart` / `report` / `webpage` / `data_table`。

4 个专业 Agent：
- **ChartAgent**：ECharts JSON 配置
- **ReportAgent**：HTML 报告片段
- **DataAgent**：复合 JSON（summary + data_table + chart_spec + insights）
- **WebpageAgent**：HTML+CSS+JS 静态页面

失败时回退到纯文本。

### 7.3 MCP Server

JSON-RPC over SSE，暴露两个工具：`list_knowledge_bases` + `rag_chat`。外部 MCP 客户端可集成检索能力。

### 7.4 LiteLLM 多供应商网关

Provider → 模型前缀映射：OpenAI(无前缀)、Anthropic(`anthropic/`)、DeepSeek/Zhipu/Qwen(`openai/`)、Ollama(`ollama/`)。

---

## 8. danbao-poc 可借鉴总结

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P0 | **RRF 融合**（dense + sparse 排名融合） | 混合检索效果提升 |
| P0 | **条件性查询改写**（仅 >50 字符时） | 避免短查询被 LLM 改写损坏 |
| P1 | **chunk 关键词 + 问题生成** | BM25 召回率提升 |
| P1 | **稀疏向量检索**（token overlap） | 精确关键词匹配补充 |
| P1 | **Parent 上下文自动扩展** | 检索结果上下文完整性 |
| P2 | **置信度评分公式**（0.6*max + 0.4*avg） | 统一评分标准 |
| P2 | **10 种分块策略工厂** | 按文档类型选最优策略 |
| P2 | **智能 Agent 路由**（图表/报告/网页） | 多格式输出 |
| P2 | **中文 token 估算**（中文/1.5 + 其他/4） | 更准确的分块大小控制 |
| P3 | **MCP Server** | 外部集成 |
| P3 | **中文编码级联回退** | 中文文本文件兼容性 |
