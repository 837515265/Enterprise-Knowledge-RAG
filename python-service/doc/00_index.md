# danbao-poc 项目对比分析报告 — 索引

> 分析日期：2026-05-28
> 对比对象：danbao-poc vs 7 个开源/参考项目

---

## 报告目录

| # | 项目 | 文件 | 核心定位 |
|---|------|------|---------|
| 1 | Graphify-7 | `01_graphify_analysis.md` | 代码库/文档 → 知识图谱（无向量检索） |
| 2 | GraphRAG-Example (ZSTP) | `02_graphrag_example_analysis.md` | 知识图谱构建 + 可视化 + RAG 问答 |
| 3 | LangExtract | `03_langextract_analysis.md` | Google LLM 结构化提取库（字符级对齐） |
| 4 | KnowFlow | `04_knowflow_analysis.md` | RAGFlow 企业级扩展（父子分块 + 100% 坐标追溯） |
| 5 | RAG-Pro | `05_rag_pro_analysis.md` | 本地优先 RAG（10 种分块 + RRF + 稀疏向量） |
| 6 | grain_agent_showcase | `06_grain_agent_showcase_analysis.md` | RAGFlow Agent 前端包装（纯静态） |
| 7 | DataGraphX | `07_datagraphx_analysis.md` | 知识图谱 RAG（受约束 Schema + Neo4j 向量） |
| 8 | 落地方案 | `08_actionable_borrowing_plan.md` | 逐项映射到 danbao-poc 当前代码、改造点与预期效果 |
| 9 | 流程分层优化 | `09_flow_layer_optimization_plan.md` | 按 danbao-poc 解析、索引、检索、回答流程逐层说明可借鉴算法、改法与效果 |
| 10 | 准确率下一步计划 | `10_accuracy_next_step_plan.md` | 合并准确率优化建议与完整优化方案，提炼下一轮开发步骤、状态、涉及文件和验收标准 |

---

## 7 项目对比总表

| 项目 | 分块策略 | 检索通道 | 图存储 | 向量存储 | 核心亮点 |
|------|---------|---------|--------|---------|---------|
| **danbao-poc** | 1（LLM Planner） | 6 通道融合 | Neo4j | ES dense_vector | 多通道融合 + 证据组装 |
| **Graphify** | 0（符号级） | 图遍历 | NetworkX | 无 | 5 阶段实体去重 + 社区检测 |
| **GraphRAG** | 0 | 2 通道拼接 | SQLite+内存 | 无 | 中文正则 11 模式 + LLM 鲁棒解析 |
| **LangExtract** | 1（句子级） | 无（提取库） | 无 | 无 | LCS 双门控对齐 + 多轮提取 |
| **KnowFlow** | **5 种** | 混合+父子 | Neo4j | ES 8+ | **100% 坐标追溯 + 父子检索** |
| **RAG-Pro** | **10 种** | 5 步管道 | 无 | Milvus | **RRF 融合 + 稀疏向量 + 智能路由** |
| **grain_agent** | 0 | 0（纯前端） | 无 | 无 | RAGFlow API 集成参考 |
| **DataGraphX** | 1 | 5 策略 | Neo4j | Neo4j 内置 | 受约束 Schema + 条件关系搜索 |

---

## danbao-poc 最值得借鉴的 Top 10

> 注：`08_actionable_borrowing_plan.md` 已进一步核对当前源码。当前项目已具备 `weighted_rrf_fuse`、多粒度 chunk、`file_char_map` 和 evidence 表字段；真正缺口主要在“检索时 child→parent 上下文替换”“字符级对齐算法”“规则关系补召回”“Anchor 五阶段去重”等落地环节。

| 排名 | 来源项目 | 借鉴点 | 预期收益 | 工作量 |
|------|---------|--------|---------|--------|
| **1** | KnowFlow | **父子检索扩展**（child 检索 → parent 上下文替换） | 检索结果上下文完整性大幅提升 | 2 天 |
| **2** | KnowFlow | **100% 坐标追溯**（line_number → 坐标映射） | 证据定位精度从 ~97% → 100% | 1 天 |
| **3** | LangExtract | **LCS 双门控对齐**（覆盖率 + 密度双重验证） | 证据引用精确度大幅提升 | 2 天 |
| **4** | RAG-Pro | **RRF 默认化 + dense/BM25 排名融合**（当前已有实现，需调为稳定默认） | 降低多通道 score 标尺不一致导致的排序漂移 | 半天 |
| **5** | RAG-Pro | **chunk 关键词 + 问题自动生成** | BM25 召回率提升 | 1 天 |
| **6** | RAG-Pro | **条件性查询改写**（仅 >50 字符时才改写） | 避免短查询被 LLM 改写损坏 | 半天 |
| **7** | KnowFlow | **AST 语义分块**（表格/代码块保持完整） | 结构化内容 chunk 质量提升 | 2 天 |
| **8** | Graphify | **5 阶段实体去重**（熵门控 + MinHash + Jaro-Winkler + LLM 仲裁） | anchor 去重质量提升 | 2 天 |
| **9** | GraphRAG | **中文正则关系模式**（11 条 pattern） | 关系提取召回率补充 LLM | 1 天 |
| **10** | DataGraphX | **受约束图 Schema**（固定节点/关系类型） | 减少 graph 通道噪声 | 半天 |

---

## 按维度汇总

### 文件处理

| 特性 | danbao-poc | 最佳实践 |
|------|-----------|---------|
| 格式数 | 5 | KnowFlow（20+，含 Gotenberg 120+ 转换） |
| 增量检测 | 无 | Graphify（mtime + MD5） |
| 编码处理 | UTF-8 | RAG-Pro（11 种中文编码回退） |
| 文件去重 | 无 | DataGraphX（MD5 + Document 节点） |

### 文件解析

| 特性 | danbao-poc | 最佳实践 |
|------|-----------|---------|
| PDF 引擎 | MinerU + Paddle | KnowFlow（4 引擎可选） |
| 解析缓存 | Redis 查询缓存 | Graphify（SHA256 文件级缓存） |
| 失败处理 | fallback 基础提取 | Graphify（自适应二分重试） |
| 图提取 | LLM 自由定义 | DataGraphX（受约束 6 节点 + 10 关系） |

### Chunk 划分

| 特性 | danbao-poc | 最佳实践 |
|------|-----------|---------|
| 策略数 | 1 | RAG-Pro（10 种） |
| 父子分块 | 简单 primary_chunk_id | KnowFlow（行范围包含 + 独立 parent 索引） |
| AST 感知 | LLM Planner 间接 | KnowFlow（markdown-it AST 直接遍历） |
| 跨 chunk 上下文 | section_path | LangExtract（前一 chunk 尾部前置） |
| 关键词/问题生成 | 无 | RAG-Pro（5 关键词 + 3 伪问题/chunk） |

### 数据存储

| 特性 | danbao-poc | 最佳实践 |
|------|-----------|---------|
| 向量库 | ES 7.x（CSS） | RAG-Pro（Milvus，支持稀疏向量） |
| rank_feature | 无 | KnowFlow（标签特征排序） |
| parent 存储 | 同索引 | KnowFlow（独立 parent 索引） |
| 字符定位 | chunk 级 | LangExtract（字符级 + 4 级对齐状态） |

### 检索方法

| 特性 | danbao-poc | 最佳实践 |
|------|-----------|---------|
| 融合算法 | score_aware | RAG-Pro（RRF，k=60） |
| 稀疏检索 | 无 | RAG-Pro（token overlap 点积） |
| 父子扩展 | 无 | KnowFlow（child→parent 上下文替换） |
| 引用插入 | 无 | KnowFlow（自动 [ID:n] 引用） |
| 查询改写 | LLM（默认开） | RAG-Pro（仅 >50 字符） |
| 置信度评分 | 无统一评分 | RAG-Pro（0.6*max + 0.4*avg） |
| 条件关系搜索 | 无 | DataGraphX（关系关键词触发） |
