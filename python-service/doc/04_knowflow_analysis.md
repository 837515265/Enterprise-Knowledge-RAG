# KnowFlow 项目分析报告

## 1. 项目概述

KnowFlow 是基于 **RAGFlow v0.20.5** 的企业级 RAG 知识库平台，**插件式微服务架构**：作为独立服务层运行在 RAGFlow 之上，共享 MySQL/MinIO/Redis 基础设施，不修改 RAGFlow 核心代码。

**核心贡献**：
- 5 种分块策略（含父子分块、AST 语义分块）
- 100% 坐标追溯（block-level line mapping）
- 父子分块检索（child 检索 → parent 上下文）
- 多引擎 OCR 适配（MinerU/DOTS/PaddleOCR/DeepDOC）
- RBAC 权限系统

---

## 2. 文件处理

**20+ 格式支持**：

**直接解析**（RAGFlow 原生）：
- PDF（DeepDOC OCR / MinerU / DOTS / PaddleOCR / PlainParser / VisionParser）
- DOCX（python-docx，含图片和表格）
- XLSX/CSV（openpyxl，QA 对提取或逐行）
- TXT/代码文件（20+ 语言）
- MD（markdown-it AST 解析，含表格）
- HTML/JSON

**Gotenberg 转换**（KnowFlow 扩展）：
`OFFICE_EXTENSIONS` 含 ~120 种文件类型（PPT/ODT/EPUB/RTF/VSD/Pages/Key/Numbers 等），通过 Gotenberg（LibreOffice）转 PDF 后再解析。

### 与 danbao-poc 对比

| 维度 | danbao-poc | KnowFlow |
|------|-----------|----------|
| PDF 引擎 | MinerU + Paddle fallback | MinerU + DOTS + PaddleOCR + DeepDOC（4 引擎可选） |
| Office 转换 | 无 | Gotenberg（120+ 格式→PDF） |
| 代码文件 | 不支持 | 20+ 语言纯文本 |

**可借鉴**：
1. **多 OCR 引擎可选**：按文档类型选择最优引擎
2. **Gotenberg Office 转换**：覆盖 120+ 格式

---

## 3. 文件解析

### 三层解析管道

**Layer 1：文件→PDF**（`ensure_pdf`）
Office/URL → Gotenberg → PDF

**Layer 2：OCR/版面识别**（4 引擎可选）：
- **MinerU**：HTTP 调用 KnowFlow Server `/api/parse/mineru`，返回语义块或行级 markdown + 坐标映射
- **DOTS**：HTTP 调用 `/api/parse/dots`，boxes + markdown + coordinate_map
- **PaddleOCR**：HTTP 调用 `/api/parse/paddleocr`，块级识别 + 自动标题层级推断（H1-H6）
- **DeepDOC**：RAGFlow 原生图像 OCR + 版面识别 + 表格 transformer + 文本合并

**Layer 3：Middle JSON → Markdown**（`SimpleMiddleJsonConverter`）

块类型处理：
- `text/title`：`merge_text_lines` 合并多行
- `table`：从 span 提取 HTML，caption 与 body 合并
- `image`：生成 `<img>` 标签 + MinIO 路径，分离 caption bbox
- LaTeX：行内 `$...$` 和显示 `$$...$$`
- **坐标映射**：`{line_number: [page_idx, x0, x1, y0, y1]}`

### 与 danbao-poc 对比

| 维度 | danbao-poc | KnowFlow |
|------|-----------|----------|
| 中间格式 | normalize_etl4lm_response | middle.json（pdf_info with blocks/lines/spans） |
| 坐标映射 | bbox_json（per block） | **line_number → [page, x0, x1, y0, y1]** |
| 表格处理 | 无专门处理 | HTML 提取 + caption 合并 |
| 公式处理 | 无 | 行内/显示 LaTeX |

**可借鉴**：
1. **行号→坐标映射**：比 per-block bbox 更精确
2. **表格 HTML 提取**：保留表格结构用于检索

---

## 4. Chunk 划分（核心亮点）

### 5 种分块策略

**A. Smart 分块**（AST 语义分块）

`markdown-it-py` 解析 Markdown → `SyntaxTreeNode` AST：
- 标题触发 chunk 边界
- 表格/代码块/引用/列表保持完整（即使超限）
- `context_stack` 跟踪标题层级（H1-H6），附加为 `heading_metadata`
- 配置：`chunk_token_num=256`, `min_chunk_tokens=10`, `enable_heading_in_content`

`_add_missing_parent_headings`：缺失的父标题自动添加到 chunk 内容。

**B. Title 分块**

严格按指定标题层级（默认 H2）切分。**智能回退**：如果切分只产生 1 个 chunk，自动回退到更高层级直到产生多个 chunk。

**C. Regex 分块**

用户定义正则模式，逐行处理，匹配行开始新 chunk。包装为 `^\s*` + 用户模式确保行边界匹配。正则失败回退到 Smart。

**D. 父子分块**（旗舰策略）

两层结构：
1. 解析 Markdown AST，创建带行范围和上下文栈的增强节点
2. **Child chunks**：按 token 限制和标题边界（H1-H3）分组
3. **Parent chunks**：按可配置 `parent_split_level`（默认 H2）分组
4. 通过**行范围包含**建立关系：child 的 `[start_line, end_line]` 必须在 parent 范围内

ID 使用 xxhash：child ID = `xxhash.xxh64(content + doc_id)`，parent ID = `{doc_id}_parent_{order}_{hash[:8]}`

Parent chunks 存入 ES 独立索引 `ragflow_{tenant_id}_parent`，映射关系存入 MySQL `parent_child_mapping` 表。

**E. Naive 分块**（RAGFlow 原生）

`naive_merge` 可配置分隔符和 token 限制。

### 与 danbao-poc 对比

| 维度 | danbao-poc | KnowFlow |
|------|-----------|----------|
| 分块策略数 | 1（LLM Planner + split_content） | **5 种** |
| AST 感知 | LLM Planner 间接感知 | markdown-it AST 直接遍历 |
| 父子分块 | primary_chunk_id/parent_chunk_id（简单） | **行范围包含**（精确） |
| 标题回退 | 无 | Title 分块自动回退到更高层级 |
| Token 计算 | 字符数 | tiktoken cl100k_base |

**可借鉴**：
1. **父子分块的行范围包含**：比 token 累积更精确
2. **AST 语义分块**：表格/代码块保持完整
3. **Title 智能回退**：自动调整切分粒度
4. **缺失父标题自动补充**：增强 chunk 上下文

---

## 5. 数据存储

### MySQL（Peewee ORM）

**RAGFlow 原生表**：
`user`, `tenant`, `knowledgebase`, `document`, `file`, `task`, `dialog`, `conversation`, `llm_factories`, `llm`, `tenant_llm`

**KnowFlow 扩展表（RBAC + 父子分块）**：
- `parent_chunk`：id(128), doc_id, kb_id, content, chunk_order, page_num, metadata(JSON), token_count, char_count
- `child_chunk`：id(128), parent_chunk_id, doc_id, kb_id, content, content_ltks, chunk_order_in_parent, chunk_order_global
- `parent_child_mapping`：child_chunk_id, parent_chunk_id, relevance_score（唯一约束）
- `parent_child_config`：kb_id PK, parent_chunk_size(1024), child_chunk_size(256), retrieval_mode(parent/child/hybrid)

### Elasticsearch 8+

**索引命名**：`ragflow_{tenant_id}`（chunks）, `ragflow_{tenant_id}_parent`（parent chunks）

**ES Mapping**（动态模板）：
- `*_tks`：自定义 `scripted_sim`（BM25-like IDF + boost）
- `*_ltks`：whitespace analyzer
- `*_kwd`：keyword type
- `*_vec`：dense_vector cosine（512/768/1024/1536 维）
- `*_fea`/`*_feas`：rank_feature/rank_features

**配置**：2 shards, 0 replicas, 1000ms refresh

### MinIO

对象存储，图片引用为 `/minio/{kb_id}/{image_name}`

### Redis

RBAC 权限缓存

### 与 danbao-poc 对比

| 维度 | danbao-poc | KnowFlow |
|------|-----------|----------|
| 关系 DB | MySQL（pymysql） | MySQL（Peewee ORM） |
| ES 版本 | 7.x（CSS） | **8+**（原生 kNN） |
| 向量字段 | `dense_vector` / CSS `vector` | `dense_vector` cosine |
| 父 chunk 存储 | 同索引 | **独立索引** `ragflow_{tenant_id}_parent` |
| rank_feature | 无 | **有**（标签特征排序） |

**可借鉴**：
1. **父 chunk 独立索引**：避免子 chunk 检索时加载父 chunk 数据
2. **rank_feature 标签排序**：自动从内容提取标签，查询时 boost

---

## 6. 检索方法

### 混合检索（Dealer 类）

**向量检索**：cosine kNN（ES dense_vector）
**BM25 检索**：ES query_string + `scripted_sim`

**融合**：`weighted_sum`（默认 0.05 text + 0.95 vector）

**重排**：
- **统计重排**：`hybrid = tkweight * token_sim + vtweight * vector_sim + rank_feature_scores`
- **模型重排**：BAAI/bge-reranker-v2-m3 cross-encoder + token_sim + rank_features

### 父子检索（核心亮点）

1. 混合检索返回 child chunks
2. 通过 `ParentChildMapping` 查 parent
3. 从 ES `ragflow_{tenant_id}_parent` 获取 parent 内容
4. **用 parent 内容替换 child**（更完整上下文）
5. 回退：parent 获取失败时用 child（`chunk_type: "child_as_parent"`）

### 全文查询构建（FulltextQueryer）

字段 boost 权重：
- `title_tks^10`, `title_sm_tks^5`
- `important_kwd^30`, `important_tks^20`
- `question_tks^20`
- `content_ltks^2`, `content_sm_ltks`

**中文查询**：term_weight 分词 → 细粒度分词 → 同义词扩展 → 近似匹配 `"..."~2`
**英文查询**：分词 → term weights → 同义词 → bigram boost

minimum_should_match：中文 30%，英文 60%

### Agentic Deep Research

`DeepResearcher` 多步定位-阅读模式：
1. LLM 生成推理
2. 提取搜索查询
3. KB 检索
4. 结果反馈回推理
5. 截断先前推理保持上下文可管理

### 引用插入（insert_citations）

LLM 答案按句子切分 → 每句 embedding → 与 chunk 向量混合相似度 → 相似度超阈值处插入 `[ID:n]`。阈值从 0.63 递减（0.8x 每轮，下限 0.3）。

### 与 danbao-poc 对比

| 维度 | danbao-poc | KnowFlow |
|------|-----------|----------|
| 融合方式 | score_aware（score_weight=0.65 + rank_weight=0.35） | weighted_sum（0.05 text + 0.95 vector） |
| 重排 | rerank 模型 | 统计重排 + 模型重排 |
| 父子检索 | 无（primary_chunk_id 存在但未用于检索扩展） | **child 检索 → parent 上下文替换** |
| 字段 boost | 硬编码 `^5/^3/^2` | `important_kwd^30` + `title_tks^10` |
| 引用 | 无 | **自动插入 [ID:n] 引用** |

**可借鉴**：
1. **父子检索扩展**：检索到 child chunk 后自动获取 parent 完整上下文
2. **important_kwd^30 高权重**：关键词字段极高 boost
3. **自动引用插入**：LLM 答案中标注来源

---

## 7. 核心算法亮点

### 7.1 100% 坐标追溯

danbao-poc 用 OCR 文本相似度匹配约 97% 精度。KnowFlow 通过 **block-level line mapping** 达到 100%：

- `middle_json_simple.py` 构建 `{line_number: [page_idx, x0, x1, y0, y1]}` 坐标映射
- `extract_text_and_coordinates` 剥离位置标签 `@@page\tx0\tx1\ty0\ty1##`
- `_attach_coordinates_to_chunks` 将 chunk 文本行映射回原始行号（精确匹配 + 部分匹配 + `used_indices` 防重复）

### 7.2 AST 语义分块

`markdown-it-py` → `SyntaxTreeNode` → 遍历节点：
- 标题：触发 chunk 终止 + 更新 context_stack
- 表格：保持 HTML 完整
- 代码块：保持完整
- 引用/列表：正确格式化渲染

### 7.3 父子 AST 行范围包含

`ASTChunkInfo` 对象含 `start_line`/`end_line` 字段（从 AST 派生）。父子关系由**行范围包含**确定，比 token 大小累积更精确。

### 7.4 自定义 BM25（scripted_sim）

```
double idf = Math.log(1+(field.docCount-term.docFreq+0.5)/(term.docFreq+0.5))/Math.log(1+((field.docCount-0.5)/1.5));
return query.boost * idf * Math.min(doc.freq, 1);
```

Okapi BM25-like IDF，用于 `*_tks` 字段，提供比标准 TF-IDF 更精确的 term 匹配。

### 7.5 Vision Enhancement

分块和坐标映射后，可选用 VLM 为含图片 chunk 添加 `[图片描述]: {desc}` 格式文本。

---

## 8. danbao-poc 可借鉴总结

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P0 | **父子检索扩展**（child 检索 → parent 上下文替换） | 检索结果上下文完整性大幅提升 |
| P0 | **100% 坐标追溯**（line_number → 坐标映射） | 证据定位精度从 ~97% 提升到 100% |
| P1 | **AST 语义分块**（表格/代码块保持完整） | 结构化内容的 chunk 质量提升 |
| P1 | **important_kwd^30 高权重 boost** | 关键词匹配准确度提升 |
| P1 | **自动引用插入**（LLM 答案标注 [ID:n]） | 可追溯性 |
| P2 | **父 chunk 独立索引** | 检索性能优化 |
| P2 | **rank_feature 标签排序** | 标签匹配信号 |
| P2 | **Title 智能回退** | 自动调整切分粒度 |
| P2 | **多 OCR 引擎可选** | 按文档类型选最优引擎 |
| P3 | **Gotenberg Office 转换** | 覆盖 120+ 格式 |
| P3 | **Agentic Deep Research** | 复杂问题的多步推理 |
