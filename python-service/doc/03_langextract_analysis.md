# LangExtract 项目分析报告

## 1. 项目概述

LangExtract 是 **Google 开发的 LLM 结构化提取库**，从非结构化文本中提取实体/关系/事实，并将提取结果精确对齐到源文本的字符和 token 位置。

**核心价值**：
- **精确源定位**：每个提取结果映射到源文本的精确字符/token 位置
- **结构化输出**：Gemini controlled generation / OpenAI JSON mode
- **长文档优化**：分块 + 并行处理 + 多轮提取
- **交互可视化**：自包含 HTML 输出，动画高亮提取跨度

**技术栈**：Python、difflib、regex/unicode tokenizer、Gemini/OpenAI/Ollama

**顶层 API**：`lx.extract(text, prompt, examples, model_id)` + `lx.visualize(data)`

---

## 2. 文件处理

**输入格式**：
- 纯文本字符串（主要模式）
- CSV 文件（pandas，可配置分隔符）
- URL（requests.get 流式下载，多编码回退）
- Document 对象

**输出格式**：JSONL（每行一个 AnnotatedDocument）

**提示模板**：YAML / JSON

**LLM 输出**：JSON / YAML（支持 `<think>` 标签剥离）

**不支持**：PDF、DOCX、二进制格式（假设调用者提供干净文本）

### 与 danbao-poc 对比

| 维度 | danbao-poc | LangExtract |
|------|-----------|-------------|
| 格式支持 | PDF/DOCX/XLSX/TXT/MD（含 OCR） | 纯文本/CSV/URL（无 OCR） |
| 输出格式 | MySQL + ES + Neo4j | JSONL 文件 |
| 数据库 | 三库存储 | 无数据库 |

---

## 3. 文件解析

LangExtract **不解析二进制文档**。文档摄取限制为：
- 原始文本字符串
- CSV 表格数据
- Web 内容（requests.get）

`data.Document` 类：`text` + `document_id`（auto UUID `doc_<uuid8>`）+ `additional_context` + `tokenized_text`（惰性计算）

### 与 danbao-poc 对比

danbao-poc 有完整的 OCR 管道（MinerU/Paddle），LangExtract 没有。两者定位不同：danbao-poc 是全栈 RAG 系统，LangExtract 是纯文本提取库。

---

## 4. Chunk 划分（核心亮点）

LangExtract 的分块系统是整个项目最精密的部分。

### 4.1 分词器（tokenizer.py）

**RegexTokenizer**（默认）：`[^\W\d_]+|\d+|([^\w\s]|_)\1*`，跟踪换行位置和字符区间。

**UnicodeTokenizer**：`regex` 库的 `\X` 字形簇模式，处理 CJK/emoji/Hangul/Thai。按文字系统分组合并同脚本 token，CJK 和非空格文字碎片化。

### 4.2 句子边界检测（find_sentence_range）

- 标点匹配 `[.?!...]` + 闭合引号/括号
- 缩写排除（Mr., Mrs., Dr., Prof., St.）
- 换行 + 大写 = 句子断点

### 4.3 ChunkIterator（核心分块算法）

`max_char_buffer=1000`：
1. 通过 `SentenceIterator` 逐句迭代
2. 累积整句直到超过 `max_char_buffer`
3. 超限时优先在换行处断开
4. 单 token 超限 → 独立 chunk
5. 单句超限 → 先换行断开，再 token 断开

`TextChunk` 携带 `token_interval` 和 `document` 引用，惰性访问 `chunk_text`、`char_interval`、`sanitized_chunk_text`。

### 4.4 跨 chunk 上下文（ContextAwarePromptBuilder）

设置 `context_window_chars` 时，前一个 chunk 的尾部作为 `[Previous text]: ...` 前置到当前提示，实现跨 chunk 共指消解。

### 4.5 批量分组

`make_batches_of_textchunk` 将 chunk 分组为 `batch_length=10` 的批次并行推理。

### 与 danbao-poc 对比

| 维度 | danbao-poc | LangExtract |
|------|-----------|-------------|
| 分块策略 | LLM Planner + 固定 2000 字符 | 句子级 + 换行优先 + token 回退 |
| 跨 chunk 上下文 | section_path + parent context | 前一 chunk 尾部前置 |
| 分词 | jieba | RegexTokenizer / UnicodeTokenizer |
| 句子感知 | 无 | find_sentence_range（缩写排除） |

**可借鉴**：
1. **换行优先断开**：超限时先找换行，再 token 断开，保持语义完整
2. **跨 chunk 上下文前置**：前一 chunk 尾部作为上下文前置，解决共指问题

---

## 5. 数据存储

**无数据库**。纯内存 dataclass + JSONL 序列化。

**核心 Schema**：

| 类 | 关键字段 |
|----|---------|
| `Document` | text, document_id, additional_context, tokenized_text |
| `Extraction` | extraction_class, extraction_text, char_interval, token_interval, alignment_status, attributes |
| `AnnotatedDocument` | document_id, extractions[], text, tokenized_text |
| `CharInterval` | start_pos, end_pos |
| `AlignmentStatus` | MATCH_EXACT / MATCH_GREATER / MATCH_LESSER / MATCH_FUZZY |

### 与 danbao-poc 对比

| 维度 | danbao-poc | LangExtract |
|------|-----------|-------------|
| 存储 | MySQL + ES + Neo4j | 无（JSONL） |
| 字符定位 | chunk 级（page_start/end） | **字符级**（char_interval） |
| 对齐状态 | 无 | 4 级对齐状态枚举 |

**可借鉴**：**字符级定位 + 对齐状态**可大幅提升证据引用的精确度。

---

## 6. 检索方法

LangExtract **不是 RAG 系统**，无向量搜索/索引检索。但有精密的**文本-提取对齐**算法：

### 6.1 精确对齐（WordAligner.align_extractions）

`difflib.SequenceMatcher`（`autojunk=False`）匹配提取 token 和源 token。所有提取用 Unicode unit separator 拼接后作为单序列匹配。

结果：`MATCH_EXACT`（token 数精确匹配）/ `MATCH_LESSER`（提取长于匹配文本）

### 6.2 LCS 模糊对齐（核心算法）

**O(n × m²) DP** 找到每个可达匹配数的最紧源跨度。

**双门控**：
- **覆盖率门控**：matches ≥ ceil(extraction_len × 0.75)
- **密度门控**：matches / span_length ≥ 1/3

如果最大匹配跨度未通过密度门控，尝试更低匹配数的更密集替代。

### 6.3 Token 归一化

`_normalize_token`：lowercase + 轻量复数词干（>3 字符结尾 "s" 但非 "ss" 去 "s"）

### 6.4 多轮提取（annotation.py）

`extraction_passes > 1` 时，多轮独立提取后合并。重叠提取按 "首轮优先" 解决；非重叠的后续轮提取追加。

### 与 danbao-poc 对比

| 维度 | danbao-poc | LangExtract |
|------|-----------|-------------|
| 对齐方式 | 三层（精确/紧凑/模糊 SequenceMatcher 0.78） | LCS DP + 双门控 |
| 多轮提取 | 无 | 多轮独立提取 + 重叠解决 |
| 证据验证 | `_quote_in_chunks` 检查存在性 | 字符级对齐 + 4 级状态 |

**可借鉴**：
1. **LCS 双门控对齐**：覆盖率 + 密度双重验证，比纯 SequenceMatcher 更精确
2. **多轮提取 + 重叠解决**：提升召回率而不引入重复

---

## 7. 核心算法亮点

### 7.1 LCS 模糊对齐（最核心算法）

`_best_lcs_spans` 返回 dict：每个可达匹配数 k → 最紧 LcsSpan。

优先最小跨度宽度，同跨度最早起点胜出。

这比 danbao-poc 的 `SequenceMatcher.ratio() > 0.78` 更精细：
- 可以尝试更低匹配数（如果最大匹配的跨度过散）
- 密度门控防止匹配 token 分散在大量噪声中
- 覆盖率门控防止匹配太少 token

### 7.2 分隔符多提取对齐

所有提取拼接 Unicode unit separator (`␟`) 后作为单序列对齐。使 difflib 按出现顺序匹配，比独立对齐每个提取更可靠。

### 7.3 提示验证（prompt_validation.py）

提取前验证 few-shot 示例的 `extraction_text` 能否对齐回示例自身的 `text`。问题分类：
- `FAILED`：无法定位
- `NON_EXACT`：模糊或部分匹配

验证级别：OFF / WARNING（默认）/ ERROR（抛异常）。严格模式拒绝模糊匹配。

### 7.4 Provider Router

模型 ID 通过正则匹配 Provider，优先级排序。支持惰性注册（import path）和直接装饰器注册。

### 7.5 GCS 批量缓存

Vertex AI Batch API 的 SHA256 内容寻址缓存。提交前检查相同 (model, prompt, schema, config) 组合，跳过已完成。

---

## 8. danbao-poc 可借鉴总结

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P0 | **LCS 双门控对齐算法**（覆盖率 + 密度） | 证据引用精确度大幅提升 |
| P1 | **多轮提取 + 重叠解决** | 知识提取召回率提升 |
| P1 | **提示验证**（提取前验证 few-shot 示例对齐） | 减少 LLM 提取失败 |
| P1 | **跨 chunk 上下文前置** | 解决共指消解问题 |
| P2 | **字符级定位 + 4 级对齐状态** | 证据引用从 chunk 级提升到字符级 |
| P2 | **Unicode 感知分词**（CJK/emoji/Hangul） | 中文分词质量提升 |
| P2 | **分隔符多提取对齐** | 多实体提取的对齐可靠性 |
| P3 | **GCS 批量缓存** | 大规模提取时节省 API 成本 |
