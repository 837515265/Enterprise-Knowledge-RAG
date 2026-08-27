# DataGraphX（学习版）项目分析报告

## 1. 项目概述

DataGraphX 是**基于知识图谱的 RAG 应用**，组合三大技术：
- **LangChain**：文档加载、文本分割、图转换、LLM 编排
- **Neo4j**：图数据库存储知识图谱 + 图检索
- **LLM**（DeepSeek/OpenAI）：实体/关系提取 + 问答

**Streamlit Web 应用**（`app.py` 入口），用户上传 PDF → 自动构建知识图谱 → 自然语言查询。Plotly 交互式图谱可视化。

---

## 2. 文件处理

**仅支持 PDF**。

- Streamlit 文件上传限制 `type="pdf"`
- `PyPDFLoader` 逐页加载 → `Document` 对象列表

不支持 Word/TXT/HTML/CSV 等格式。

### 与 danbao-poc 对比

| 维度 | danbao-poc | DataGraphX |
|------|-----------|------------|
| 格式 | PDF/DOCX/XLSX/TXT/MD | **仅 PDF** |
| PDF 引擎 | MinerU + Paddle | PyPDFLoader（纯文本） |
| OCR | 有 | 无 |

---

## 3. 文件解析

### 5 阶段管道

**Stage 1：PDF 加载**（`PyPDFLoader`）
逐页 → Document 对象（`page_content` + metadata）

**Stage 2：文本分割**（`RecursiveCharacterTextSplitter`）
- 按页分割（非按文档）
- `ThreadPoolExecutor` 并行

**Stage 3：文档清理**
- `doc.page_content.replace("\n", "")` 去换行
- `ThreadPoolExecutor` 并行

**Stage 4：图转换**（`LLMGraphTransformer`）
- `langchain_experimental.graph_transformers` 的 LLM 图提取
- 每个 chunk 独立提取实体/关系
- 受 `GRAPH_CONFIG` 约束节点/关系类型
- `asyncio.to_thread` 最昂贵步骤

**Stage 5：图存储和索引**
- `graph.add_graph_documents(all_graph_documents, include_source=True)`
- `Neo4jVector.from_existing_graph` 创建向量 + 全文索引
- `Document` 节点跟踪处理状态

### 与 danbao-poc 对比

| 维度 | danbao-poc | DataGraphX |
|------|-----------|------------|
| 图提取 | knowledge_extractor（LLM 多类型提取） | LLMGraphTransformer（LangChain） |
| 图 Schema | 自由定义 | **固定 6 节点类型 + 10 关系类型** |
| 提取粒度 | chunk 级 | chunk 级 |

**可借鉴**：**受约束的图 Schema**（固定节点/关系类型）防止 LLM 生成不可控图结构。

---

## 4. Chunk 划分

`config.py`：
```python
DOC_CONFIG = {
    'chunk_size': 1000,
    'chunk_overlap': 40
}
```

**RecursiveCharacterTextSplitter**：
- 分隔符优先级：`["\n\n", "\n", " ", ""]`
- 字符数单位（1000 字符上限）
- 40 字符 overlap

按页独立分割 → 扁平化为 Document 列表。

### 与 danbao-poc 对比

| 维度 | danbao-poc | DataGraphX |
|------|-----------|------------|
| 分块策略 | LLM Planner + 2000 字符 | RecursiveCharacterTextSplitter + 1000 字符 |
| 章节感知 | 有 | 无 |
| Overlap | 100 字符 | 40 字符 |

---

## 5. 数据存储

### Neo4j（主存储）

**双客户端**：
- `langchain_neo4j.Neo4jGraph`：LangChain 集成（add_graph_documents, from_existing_graph）
- `py2neo.Graph`：直接图遍历（可视化准备）

**受约束的节点类型（6 种）**：

| 标签 | 说明 |
|------|------|
| `研究内容` | Research Content |
| `研究方法` | Research Method |
| `创新点` | Innovation Point |
| `参考部分` | Reference Section |
| `预期成果` | Expected Outcome |
| `未来展望` | Future Outlook |

**受约束的关系类型（10 种）**：

`支持`, `补充`, `引用`, `反映`, `基于`, `达成`, `依赖于`, `借鉴`, `指导`, `产生`

**Neo4j 索引**：
1. `vector_index`：`研究内容` 标签上的向量索引
2. `entity_index`：全文索引

**Document 节点**：跟踪已处理文件（name, hash, processed）

### 本地缓存（JSON）

- `{file_hash}_graph_data.json`：每个 PDF 的序列化图数据
- `graph_documents_cache.pkl`：pickle 缓存（每次处理前删除）

**文件缓存逻辑**：处理前检查本地 JSON + Neo4j Document 节点（MD5 哈希）。已处理则跳过。

### 与 danbao-poc 对比

| 维度 | danbao-poc | DataGraphX |
|------|-----------|------------|
| 图 Schema | 自由（anchor/unit/relation） | **固定 6 节点 + 10 关系** |
| 向量存储 | ES | **Neo4j 内置向量索引** |
| 文件去重 | 无 | MD5 + Document 节点 |
| 缓存 | Redis | JSON + pickle |

**可借鉴**：
1. **受约束图 Schema**：防止 LLM 生成不可控结构
2. **Neo4j 内置向量索引**：图 + 向量统一存储
3. **MD5 文件去重**：避免重复处理

---

## 6. 检索方法

`process_question`（`app.py`）实现**5 策略检索管道**：

### 策略 1：中文关键词提取 + 精确匹配

`jieba.lcut(prompt)` 分词 → 过滤 ≥2 字符词 → Cypher：
```cypher
MATCH (n)
WHERE n.text IS NOT NULL
AND toLower(n.text) CONTAINS toLower($term)
RETURN n.text as content, 1.0 as score
LIMIT 3
```

### 策略 2：向量语义搜索

Embedding 查询向量 → Neo4j 向量索引：
```cypher
CALL db.index.vector.queryNodes('vector_index', 5, $embedding)
YIELD node, score
WHERE node.text IS NOT NULL AND score > 0.3
RETURN node.text as content, score
ORDER BY score DESC
```
阈值 0.3，top 5。

### 策略 3：关系搜索

问题含关系关键词（`["关系", "联系", "作用", "影响", "如何"]`）时触发：
```cypher
MATCH (n)-[r]-(m)
WHERE n.text IS NOT NULL AND m.text IS NOT NULL
AND (ANY(term IN split($terms, '|') WHERE
    toLower(n.text) CONTAINS toLower(term)
    OR toLower(m.text) CONTAINS toLower(term)))
RETURN n.text as source, type(r) as relation, m.text as target
LIMIT 5
```

### 策略 4：全文搜索

Neo4j 全文索引 `entity_index`：
```cypher
CALL db.index.fulltext.queryNodes("entity_index", $question) YIELD node, score
WHERE score > 0.5
```
返回匹配节点的 schema 信息（labels, properties, relationships）。

### 策略 5：APOC 模糊匹配

`apoc.text.fuzzyMatch` 近似字符串匹配（无特定节点/关系类型时回退）。

### 混合搜索

Neo4j 向量索引用 `search_type="hybrid"` 创建，单次查询组合向量 + 全文。

### 子图检索（可视化）

`find_relevant_subgraph`：
- jieba 分词找 `text` 含关键词的节点
- BFS 遍历（max_depth=2）
- <3 节点时扩展所有邻居

### 答案生成

去重聚合所有结果 → context 字符串 → LLM 结构化格式（Summary/Analysis/Answer）。

### 与 danbao-poc 对比

| 维度 | danbao-poc | DataGraphX |
|------|-----------|------------|
| 检索通道 | 6 通道（BM25/Vector/Structured/Graph/Summary/QA） | 5 策略（关键词/向量/关系/全文/模糊） |
| 图检索 | Neo4j Cypher 遍历 | **关系搜索**（条件触发） |
| 分词 | jieba | jieba |
| 全文搜索 | ES BM25 | **Neo4j 全文索引** |
| 模糊匹配 | 无 | **APOC fuzzyMatch** |

**可借鉴**：
1. **条件触发关系搜索**：问题含关系关键词时才搜索关系，减少不必要查询
2. **APOC 模糊匹配**：作为回退策略
3. **Neo4j 全文索引**：图数据库内完成全文搜索

---

## 7. 核心算法亮点

### 7.1 LLMGraphTransformer 知识图谱构建

LangChain 的 `LLMGraphTransformer` 将每个 chunk 发给 LLM，指示按 `allowed_nodes` + `allowed_relationships` 提取实体/关系。`node_properties=False` 保持图 Schema 精简。

### 7.2 jieba 中文分词

`jieba.lcut()` 用于检索管道和子图搜索。`jieba.analyse` 已导入但未主动调用（可用于 TF-IDF 关键词提取）。

### 7.3 APOC 模糊匹配

`apoc.text.fuzzyMatch` 作为结构化信息无法提取时的回退。

### 7.4 NetworkX + Spring Layout

`nx.spring_layout(G, k=0.5, iterations=50)` — **Fruchterman-Reingold 力导向布局**。
节点大小按邻居数缩放：`10 + len(list(G.neighbors(node)))`。
HSV 色彩空间映射节点类型颜色。

### 7.5 MD5 文档去重

`generate_file_hash(file_content)` 计算 PDF 字节 MD5 → 本地缓存检查 + Neo4j Document 节点检查。

### 7.6 双 Neo4j 客户端

`langchain_neo4j.Neo4jGraph`（高级集成）+ `py2neo.Graph`（低级遍历），提供高层和底层 Neo4j 访问。

### 7.7 Async + ThreadPool 并行

PDF 处理用 `asyncio.to_thread`（I/O 密集 Neo4j 操作）。文本分割和清理用 `ThreadPoolExecutor`。Streamlit UI 保持响应。

### 7.8 受约束 Schema 知识图谱

与开放域 KG 提取不同，DataGraphX 限制输出为 6 节点类型 + 10 关系类型。领域特定（学术/研究文档分析），防止 LLM 生成不可控图 Schema。

---

## 8. danbao-poc 可借鉴总结

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P1 | **受约束图 Schema**（固定节点/关系类型） | 防止 graph 通道产生噪声 |
| P1 | **条件触发关系搜索**（关系关键词检测） | 减少不必要的 Neo4j 查询 |
| P2 | **Neo4j 内置向量索引** | 图 + 向量统一存储，减少 ES 负载 |
| P2 | **MD5 文件去重** | 避免重复解析 |
| P2 | **APOC 模糊匹配** | 回退检索策略 |
| P3 | **jieba.analyse TF-IDF** | 关键词提取增强 |
| P3 | **Neo4j 全文索引** | 图数据库内全文搜索 |

---

## 附：7 项目对比总表

| 项目 | 分块策略数 | 检索通道 | 图存储 | 向量存储 | 核心亮点 |
|------|-----------|---------|--------|---------|---------|
| **danbao-poc** | 1 | 6 通道融合 | Neo4j | ES dense_vector | 多通道融合 + 证据组装 |
| **Graphify** | 0（符号级） | 图遍历 | NetworkX | 无 | 5 阶段实体去重 + 社区检测 |
| **GraphRAG-Example** | 0 | 2 通道拼接 | SQLite + 内存 | 无 | 中文正则 11 模式 + LLM 鲁棒解析 |
| **LangExtract** | 1（句子级） | 无（提取库） | 无 | 无 | LCS 双门控对齐 + 多轮提取 |
| **KnowFlow** | 5 | 混合 + 父子 | Neo4j | ES 8+ | 100% 坐标追溯 + 父子检索 |
| **RAG-Pro** | 10 | 5 步管道 | 无 | Milvus | RRF 融合 + 稀疏向量 + 10 策略 |
| **grain_agent** | 0 | 0（纯前端） | 无 | 无 | RAGFlow API 集成参考 |
| **DataGraphX** | 1 | 5 策略 | Neo4j | Neo4j 内置 | 受约束 Schema + 条件关系搜索 |

### danbao-poc 最值得借鉴的 Top 10

| 排名 | 来源 | 借鉴点 | 预期收益 |
|------|------|--------|---------|
| 1 | KnowFlow | **父子检索扩展**（child→parent 上下文替换） | 检索上下文完整性 |
| 2 | KnowFlow | **100% 坐标追溯**（line_number→坐标映射） | 证据定位精度 |
| 3 | RAG-Pro | **RRF 融合**（dense + sparse 排名融合） | 混合检索效果 |
| 4 | LangExtract | **LCS 双门控对齐** | 证据引用精确度 |
| 5 | RAG-Pro | **chunk 关键词 + 问题生成** | BM25 召回率 |
| 6 | RAG-Pro | **条件性查询改写**（仅 >50 字符） | 避免短查询被改写损坏 |
| 7 | KnowFlow | **AST 语义分块**（表格/代码块完整） | chunk 质量 |
| 8 | Graphify | **5 阶段实体去重** | anchor 去重质量 |
| 9 | GraphRAG | **中文正则 11 模式** | 关系提取召回率 |
| 10 | DataGraphX | **受约束图 Schema** | 减少 graph 通道噪声 |
