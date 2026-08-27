# GraphRAG-Example（ZSTP 知识图谱系统）分析报告

## 1. 项目概述

ZSTP 是一个**知识图谱构建与可视化平台**，集成 RAG 智能问答。全栈 JavaScript 应用：

- **前端**：Vue 3 + Vite + Pinia + D3.js 可视化
- **后端**：Express + SQL.js（内存 SQLite）
- **LLM**：OpenAI 兼容 API（实体提取 + RAG 问答）

核心特性：多图管理、导入历史撤销、聊天消息持久化。

---

## 2. 文件处理

**支持格式**：`.json`, `.csv`, `.txt`, `.md`, `.markdown`, `.pdf`

**分类**：
- **结构化**（直接解析为节点/边）：JSON, CSV
- **非结构化**（需提取）：TXT, MD, PDF

非结构化文件优先 LLM 提取，LLM 不可用时 fallback 到正则提取。

### 与 danbao-poc 对比

| 维度 | danbao-poc | ZSTP |
|------|-----------|------|
| 格式支持 | PDF, DOCX, XLSX, TXT, MD | JSON, CSV, TXT, MD, PDF |
| 结构化导入 | 无 | JSON 三种格式 + CSV 三种格式 |
| 优雅降级 | 无 | LLM 失败 → 正则 fallback |

**可借鉴**：结构化数据（JSON/CSV）直接导入图的能力，可增强 danbao-poc 的 graph 通道。

---

## 3. 文件解析

### JSON 解析器（3 种格式）

1. **节点/边结构**：`{ nodes: [...], edges: [...] }`（也接受 vertices/links/relations）
2. **三元组数组**：`[{ subject, predicate, object }]`（也接受 head/relation/tail）
3. **邻接表**：`{ "NodeA": { "rel": ["NodeB"] } }`

### CSV 解析器（PapaParse，3 种模式）

1. **三元组**：`subject/predicate/object` 列
2. **边列表**：`source/target` 列
3. **实体列表**：首列 label，其余 properties

### TXT 解析器（核心正则提取引擎）

6 步 Pipeline：

1. 注册 Markdown 标题为实体 + 层级关系
2. 引号/书名号实体提取：`[《「『【]...[》」』】]|"[^"]{2,20}"`
3. **模式关系提取**：11 条中文模式 + 3 条英文模式
   - 中文覆盖：拥有(`A是B的C`)、等价(`A是B`)、归属(`属于/隶属于`)、组成(`包含/包括/涵盖/由...组成`)、创建(`创建/发明/提出/发现`)、位置(`位于/来自/出生于`)、因果(`影响/导致/引发`)、依赖(`基于/依赖/使用`)、别名(`被称为/又称`)、并列(`和/与/及`)
   - 英文覆盖：`A is/was B`, `A created/founded B`, `A is based on/part of B`
   - 特殊 `_isXofY` 模式处理 "A是B的C" 三元分解
4. **高频词提取**：中文 2-6 字 n-gram（2/3/4-gram），英文专有名词（大写多词序列），出现 2+ 次且不在节点表中的词加入实体
5. **句子级共现**：按 `。！？.!?\n` 分句，同句实体（2-8 个）用 `共现` 边连接，**仅在无更强语义关系时**
6. 清理：移除 <2 字符或纯数字/标点节点

### PDF 解析器

pdfjs-dist 提取文本 → 按 Y 坐标分行 → 拼接 → 委托给 TXT 解析器

### 与 danbao-poc 对比

| 维度 | danbao-poc | ZSTP |
|------|-----------|------|
| PDF 解析 | MinerU OCR（版面分析 + 语义块） | pdfjs-dist（纯文本） |
| 关系提取 | LLM 知识抽取（anchor/unit/relation） | 正则 11+3 模式 + 共现 |
| 中文 NLP | jieba POS 标注 + NER | 中文 bigram 分词 + n-gram 高频词 |
| 共现分析 | 无 | 句子级共现边（冗余抑制） |

**可借鉴**：
1. **中文正则关系模式**：11 条中文 pattern 可补充 LLM 提取的召回率
2. **共现边冗余抑制**：只在无更强语义关系时才加共现边

---

## 4. Chunk 划分

**无传统分块**。

- **共现分析**：按句子分割（`。！？.!?\n`，最短 4 字符），每句是一个 "chunk"
- **LLM 提取**：硬截断 4000 字符
- **RAG 搜索**：关键词匹配扩展为 800 字符上下文窗口（前后各 400 字符），重叠检测避免重复

### 与 danbao-poc 对比

| 维度 | danbao-poc | ZSTP |
|------|-----------|------|
| 分块方式 | LLM Planner + 2000 字符切分 | 无分块 |
| 上下文窗口 | section_path + parent context | 800 字符关键词窗口 |

---

## 5. 数据存储

**SQLite（SQL.js）**：6 张表

| 表 | 用途 |
|----|------|
| `graphs` | 图元数据（id, name, nodeCount, edgeCount） |
| `nodes` | 节点（id+graphId PK, label, type, properties JSON） |
| `edges` | 边（id+graphId PK, source, target, label, weight） |
| `import_history` | 导入历史（支持撤销） |
| `messages` | 聊天消息 |
| `files` | 原始文件内容（用于 RAG 搜索） |

**去重机制**：`labelIndex`（归一化 label → nodeId），重复节点合并 properties。

**边权重累积**：相同边重复导入时 weight += 1，作为置信度/频率信号。

**持久化**：debounce 写入（100ms），SIGINT 同步写入。

**前端状态**：Pinia Store 内存图（nodes Map, edges Map, adjacency Map）。

### 与 danbao-poc 对比

| 维度 | danbao-poc | ZSTP |
|------|-----------|------|
| 数据库 | MySQL + ES + Neo4j | SQLite（单文件） |
| 图存储 | Neo4j（Cypher） | 内存 + SQLite |
| 边权重 | 无 | weight 累积（频率信号） |
| 撤销 | 无 | import_history 支持 per-import undo |

---

## 6. 检索方法

**双通道检索**：

### 通道 1：文件内容检索（主要）

关键词出现次数计分 → 800 字符上下文窗口 → Top 10 文件 → 高分文件（≥2）额外提供 6000 字符全文。

### 通道 2：图结构检索（辅助）

`findSeedNodes()` 评分（精确匹配=10, 子串=5, 属性=2）→ Top 10 种子 → `bfsSubgraph()`（depth=2, maxNodes=50）

### 上下文融合

`formatCombinedContext()` 拼接两个通道：
- 文档内容标记为 **"原始文档内容（主要参考依据）"**
- 图结构标记为 **"知识图谱结构（辅助参考）"**

LLM 提示明确指示：**优先使用原始文档，图结构仅作辅助**。

### 无复杂重排

无 cross-encoder、无 BM25、无余弦相似度。纯关键词计数排序。

### 与 danbao-poc 对比

| 维度 | danbao-poc | ZSTP |
|------|-----------|------|
| 检索通道 | 6 通道融合 | 2 通道拼接 |
| 评分方式 | RRF + rerank 模型 | 关键词计数 |
| 通道优先级 | 权重融合 | 文档优先，图辅助 |
| 延迟 | ~2.3s | 更快（无向量计算） |

**可借鉴**：
1. **明确的通道优先级标注**：LLM 提示中区分 "主要依据" 和 "辅助参考"，防止低质量图数据干扰
2. **边权重累积**：重复出现的边增加权重，可作为置信度信号

---

## 7. 核心算法亮点

### 7.1 中文正则关系模式（11 条）

覆盖中文主要句法结构：拥有、等价、归属、组成、创建、位置、因果、依赖、别名、并列。命名捕获组 `(?<s>, ?<o>, ?<v>, ?<a>)` 提取主语/宾语/动词/形容词。

**`_isXofY` 特殊模式**：处理 "A是B的C" 中文特有结构，分解为三元关系而非二元。

### 7.2 LLM 输出鲁棒解析

`parseExtractionResult()` 处理：
- Markdown 代码块（带语言标签）
- 嵌入散文中的 JSON（平衡花括号提取）
- 中文标点转换（全角→ASCII）
- 尾随逗号
- 单引号

`extractJsonObject()` 跟踪字符串转义状态和花括号深度。

### 7.3 BFS 子图（深度 + 大小限制）

`bfsSubgraph()` 双约束：`maxDepth=2` + `maxNodes=50`，防止 hub 节点导致子图爆炸。

### 7.4 D3 四种布局

Force-directed、Circular、Grid、Concentric（按度分层），`d3.easeCubicInOut` 600ms 过渡动画。

---

## 8. danbao-poc 可借鉴总结

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P1 | **中文正则关系模式**（11 条 pattern） | 补充 LLM 提取召回率，对制度文件的条款关系特别有价值 |
| P1 | **LLM 输出鲁棒解析**（平衡花括号 + 标点转换 + 尾逗号） | 减少知识提取失败率 |
| P2 | **边权重累积**（重复导入 weight += 1） | Neo4j 边可加频率置信度 |
| P2 | **明确的通道优先级标注** | 在 evidence group 中区分主要/辅助来源 |
| P2 | **BFS 双约束**（depth + maxNodes） | 图检索通道优化 |
| P3 | **共现边冗余抑制** | 减少 Neo4j 中的噪声边 |
