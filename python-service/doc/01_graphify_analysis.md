# Graphify-7 项目分析报告

## 1. 项目概述

Graphify 是一个**知识图谱构建工具**，将代码库、文档、PDF、图片、音视频映射为可导航的 NetworkX 图。核心理念：**图结构本身就是相似度信号，无需向量检索**。

**技术栈**：Python、NetworkX、Tree-sitter（AST）、faster-whisper（音视频转录）、Claude/Kimi/Ollama（LLM 提取）、Leiden/Louvain（社区检测）。

**Pipeline 阶段**：detect → extract → build → cluster → analyze → report → export（9 种输出格式）

---

## 2. 文件处理

| 类型 | 支持格式 | 处理方式 |
|------|---------|---------|
| 代码 | 50+ 扩展名，26 种语言 | Tree-sitter AST 提取 |
| 文档 | md, txt, rst, adoc, org | LLM 语义提取 |
| 论文 | PDF（pypdf） | LLM 语义提取 |
| 图片 | png, jpg, gif, webp, svg | Claude Vision 提取 |
| 音视频 | mp4, mov, wav, m4a | faster-whisper 转录 + LLM |
| Office | docx（python-docx）, xlsx（openpyxl） | 转为 Markdown 副文件 |

**增量检测**：`detect_incremental()` 基于 mtime + MD5 哈希，只对变更文件重新提取。

**URL 摄取**：支持 tweet、arXiv、GitHub、YouTube、PDF、网页。

### 与 danbao-poc 的对比

| 维度 | danbao-poc | Graphify |
|------|-----------|----------|
| 支持格式 | PDF, DOCX, XLSX, TXT, MD | 50+ 代码语言 + 文档 + 音视频 |
| 增量处理 | 无（每次全量重解析） | mtime + MD5 增量检测 |
| Office 转换 | 无 | docx→md, xlsx→md 副文件 |

**可借鉴**：增量检测机制可避免重复解析未变更的文档，节省 LLM 调用成本。

---

## 3. 文件解析

### 三级提取（成本递增）

**Pass 1：代码结构（免费，确定性）**
- `LanguageConfig` 数据类驱动 Tree-sitter AST 提取
- 13 种 Tree-sitter 语言配置 + 7 种特殊提取器（Go, Rust, Zig 等）
- 提取类、函数、方法、导入、调用图 → 直接生成节点和边
- `_extract_python_rationale` 额外提取 docstring 和 `# NOTE:`/`# HACK:`/`# TODO:` 注释

**Pass 2：音视频（本地免费）**
- faster-whisper base 模型，CPU int8 量化
- SHA1 缓存，避免重复转录

**Pass 3：文档/论文/图片（LLM，付费）**
- `_pack_chunks_by_tokens()` 按 token 预算打包文件
- 每个文件上限 20,000 字符
- ThreadPoolExecutor 并行提取（max_concurrency=4）

### 自适应重试机制
`_extract_with_adaptive_retry()`：LLM 输出截断时，将 chunk 二分后分别重试，最多递归 3 层。

### 与 danbao-poc 的对比

| 维度 | danbao-poc | Graphify |
|------|-----------|----------|
| PDF 解析 | MinerU / PaddleOCR / PyMuPDF fallback | pypdf + LLM |
| 代码解析 | 不支持 | Tree-sitter AST（50+ 语言） |
| 解析失败处理 | fallback 到基础提取 | 二分重试（自适应） |
| 缓存 | Redis 查询缓存 | SHA256 文件级缓存（ast/ + semantic/） |

**可借鉴**：
1. **自适应重试**：LLM 输出截断时二分重试，而非简单 fallback
2. **SHA256 文件缓存**：解析结果按内容哈希缓存，重复解析直接返回缓存

---

## 4. Chunk 划分

Graphify **没有传统文本分块**。提取单元是结构性元素：

**代码**：每个类/函数/方法 → 一个节点，每个 import/call → 一条边。粒度是符号级，不是段落级。

**文档**：`_pack_chunks_by_tokens()` 按 token 预算（tiktoken cl100k_base）贪心打包同目录文件，不是分块而是文件级打包。

**Node ID 生成**：`_make_id(*parts)` = `re.sub(r"[^a-zA-Z0-9]+", "_", combined).strip("_").lower()`

### 与 danbao-poc 的对比

| 维度 | danbao-poc | Graphify |
|------|-----------|----------|
| 分块策略 | LLM Planner + split_content（2000 字符上限） | 无分块，符号级提取 |
| 章节感知 | SECTION_ALIASES + section_type 标注 | 无（代码用 AST 层级） |
| Overlap | 100 字符 overlap | 无（节点间通过边关联） |

**可借鉴**：代码类文档可考虑 AST 级别的提取，而非纯文本分块。

---

## 5. 数据存储

**主存储**：NetworkX 图 → `graphify-out/graph.json`（node-link 格式）

**无数据库**：不使用 ES、MySQL、PostgreSQL。

**节点 Schema**：`id`, `label`, `file_type`（code/document/paper/image/rationale/concept）, `source_file`, `source_location`

**边 Schema**：`source`, `target`, `relation`（calls/imports/uses/inherits 等）, `confidence`（EXTRACTED/INFERRED/AMBIGUOUS）, `confidence_score`

**全局图**：`~/.graphify/global-graph.json` 跨项目合并图，节点 ID 前缀 `repo_tag::` 隔离。

**可选 Neo4j**：`push_to_neo4j()` 使用 MERGE upsert 推送。

### 与 danbao-poc 的对比

| 维度 | danbao-poc | Graphify |
|------|-----------|----------|
| 主存储 | MySQL + ES + Neo4j 三库 | NetworkX JSON |
| 向量存储 | ES dense_vector | 无（无向量检索） |
| 图存储 | Neo4j（简单 BusinessPlan→Field） | NetworkX（丰富关系类型） |
| 增量更新 | 删除重建 | build_merge 增量合并 |

---

## 6. 检索方法

**核心策略：图遍历即检索**。无 BM25、无向量搜索。

**查询 Pipeline**（`serve.py`）：
1. 分词 → `_score_nodes(G, terms)` 评分（精确匹配 +100，部分匹配按比例）
2. 选 Top 3 种子节点
3. BFS/DFS 遍历（默认 depth=3）
4. `_filter_graph_by_context` 上下文过滤（如 "call" 查询只保留 calls/invokes 边）
5. `_subgraph_to_text` 渲染为文本（token 预算控制）

**MCP Server 工具**：`query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `shortest_path`

**社区检索**：Leiden/Louvain 社区作为预计算聚类，支持 "按主题浏览"。

**Surprise Score**：跨文件/跨社区/跨仓库的边按复合意外度评分，提供 "你可能不知道" 检索模式。

### 与 danbao-poc 的对比

| 维度 | danbao-poc | Graphify |
|------|-----------|----------|
| 检索方式 | BM25 + Vector + Graph + Structured 多通道融合 | 纯图遍历 |
| 种子选择 | 无（直接搜 ES） | 关键词匹配评分选种子节点 |
| 上下文过滤 | 无 | `_CONTEXT_HINTS` 映射关键词到边类型 |
| 重排 | Rerank 模型 | 无 |

---

## 7. 核心算法亮点

### 7.1 五阶段实体去重（dedup.py）

1. **精确归一化**：lowercase + 非字母数字折叠为 `_`，Union-Find 合并
2. **熵门控**：Shannon 熵 < 2.5 bits/char 的标签（如 `main`, `test`）跳过模糊匹配
3. **MinHash/LSH 阻塞**：字符 3-gram shingles → MinHash 签名 → LSH 候选对
4. **Jaro-Winkler 验证**：候选对评分，同社区 +5.0 加分，≥92 合并，75-92 标记为 ambiguous
5. **LLM 仲裁**：批量解决 ambiguous 对（batch_size=30）

**Union-Find**：路径压缩 + 按秩合并，`_pick_winner` 优先无 chunk 后缀的 ID。

### 7.2 社区检测（cluster.py）

- **主算法**：Leiden（graspologic）
- **回退**：Louvain（networkx）
- **超大分裂**：社区 > 图 25%（最少 10 节点）递归 Leiden 分裂
- **低内聚分裂**：内聚分 < 0.05（最少 50 节点）二次 Leiden
- **内聚分**：实际社区内边数 / 最大可能边数

### 7.3 跨文件导入解析

**两阶段**：
1. 构建全局 `name → node_id` 索引
2. 解析 `from .module import Name` 为类级 INFERRED "uses" 边

**歧义跳过**：同名多候选节点的调用直接跳过，防止虚假 god-node 膨胀。

### 7.4 SSRF 防护

`validate_url()` 阻止私有/保留/回环 IP。`_ssrf_guarded_socket()` 在 fetch 期间 patch `socket.getaddrinfo` 防止 DNS 重绑定。

---

## 8. danbao-poc 可借鉴总结

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P1 | **实体去重五阶段管道**（熵门控 + MinHash + Jaro-Winkler + LLM 仲裁） | 提升 anchor 去重质量，减少虚假重复 |
| P1 | **SHA256 文件级解析缓存** | 重复解析时直接返回缓存，节省 LLM 调用 |
| P2 | **自适应重试**（LLM 截断时二分重试） | 减少解析失败率 |
| P2 | **增量检测**（mtime + MD5） | 避免重复解析未变更文件 |
| P2 | **社区检测**（Leiden + 超大分裂 + 低内聚分裂） | 图检索通道可提供更有意义的聚类 |
| P3 | **跨文件调用解析** | 多文档间的知识关联 |
| P3 | **Surprise Score** | 发现跨文档的意外关联 |
