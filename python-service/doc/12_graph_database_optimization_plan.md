# danbao-poc 图数据库优化方案

## 1. 背景与问题

danbao-poc 当前已经具备 MySQL、Elasticsearch、Neo4j 三类存储，并在检索侧形成 `structured / section_summary / graph / bm25 / vector / qa` 多通道召回。但从准确率测试和消融结果看，graph 通道没有稳定贡献，部分场景甚至产生噪声。

根本原因不是 Neo4j 本身价值不足，而是当前图数据库的定位、建模和检索闭环还没有充分发挥图结构的优势。

当前 Neo4j 主要承载的是业务字段图：

```text
File -> BusinessPlan
BusinessPlan -> BusinessField
BusinessPlan -> Region
BusinessPlan -> Industry
BusinessPlan -> Organization
BusinessField -> Chunk
```

这类图对"字段值查询"帮助有限。比如用户问"授信期限是多少""反担保措施是什么""额度是多少"，`structured`、`BM25`、`QA` 已经可以直接召回原文或字段结果，graph 只是把同一份字段信息换成图结构存了一遍，新增信息量不足。

与此同时，真正适合图数据库的问题，例如"适用哪些区域""哪些产品限制某行业""某机构参与哪些产品""某制度哪条规定了审批职责""A 和 B 的关系是什么"，当前图谱中的节点、边和证据绑定还不够完整，因此 graph 通道没有形成稳定的独立价值。

因此，本方案的核心不是"继续加强担保方案字段图"，而是把 Neo4j 从"字段结果可视化存储"升级为"通用知识关系图 + Profile 映射 + 意图驱动检索 + 证据绑定"的关系检索层。

### 1.1 开发环境实测数据（2026-06-01）

> **以下数据来自对开发环境 Neo4j（bolt://10.10.20.45:7687）的实际查询，是方案修订的关键依据。**

#### 节点统计

| 节点类型 | 数量 | 说明 |
|---|---|---|
| File | 153 | 23 个 kb_id 下的文件 |
| BusinessPlan | 107 | 担保方案节点 |
| BusinessField | 496 | 字段节点 |
| Chunk | 416 | 证据块 |
| Region | 71 | 区域维度节点 |
| Industry | 188 | 行业维度节点 |
| Organization | 27 | 机构维度节点 |
| **总计** | **1458** | |

#### 关系统计

| 关系类型 | 数量 | 有 weight 属性 | 说明 |
|---|---|---|---|
| PARSED_AS | 107 | 20 (19%) | File -> BusinessPlan |
| HAS_FIELD | 496 | 1 (0.2%) | BusinessPlan -> BusinessField |
| EVIDENCED_BY | 489 | 0 (0%) | BusinessField -> Chunk |
| IN_REGION | 79 | 1 (1%) | BusinessPlan -> Region |
| IN_INDUSTRY | 206 | 33 (16%) | BusinessPlan -> Industry |
| RELATED_TO | 58 | 0 (0%) | BusinessPlan -> Organization |
| **总计** | **1435** | **55 (3.8%)** | |

#### 发现的关键问题

**问题 1：关系 weight 属性几乎全部缺失**

`EVIDENCED_BY`（489 条）和 `RELATED_TO`（58 条）的 weight 全部为 None，`HAS_FIELD`（496 条）只有 1 条有 weight。原因是历史数据在旧版代码（未写入 weight）下导入，而 Neo4j 的 `MERGE` 不会更新已有关系的属性，只在新建关系时写入。这导致 `_graph_relation_score()` 中的 `relationship_weight` 和 `evidence_weight` 全部回退到默认值，排序完全失效。

**问题 2：制度文件完全没有图谱化**

`kb_id=862026050615464176`（7 个制度文件）在 Neo4j 中只有 7 个 File 节点，没有 BusinessPlan、BusinessField、Chapter、Clause 等任何业务节点。制度文件的图谱 schema 虽然在 `graph_schema.py` 中定义了，但没有 graph builder 实现。

**问题 3：GraphEntity 节点不存在**

`graphrag_adapter.py` 定义了 GraphEntity 和 GraphCommunity 的导入逻辑，但开发环境中 GraphEntity 节点数量为 0，GraphRAG 数据未被导入。

**问题 4：EVIDENCED_BY 证据粒度粗糙**

`evidence_text` 存储的是 Chunk 的 `content_preview`（前 500 字符），而非精确的证据引用。例如 `document_no` 字段的 evidence_text 是整个 chunk 的开头文本，而非具体提取出的文号值。

#### 消融测试验证

消融测试（110 题，2026-05-25）数据：

| 配置 | 命中文件率 | 平均 Top-1 分 |
|---|---|---|
| baseline（全开） | 56.0% | 0.8555 |
| **no_graph（关掉图）** | **59.3%** | **0.8581** |

**关掉 graph 后命中率反而 +3.3%，Top-1 分 +0.0026。** graph 在以下品类产生明显噪声：

| 品类 | baseline 命中率 | no_graph 命中率 | graph 影响 |
|---|---|---|---|
| 超短查询 | 36.0% | **52.0%** | **-16% 伤害** |
| 多轮上下文 | 47.8% | **60.9%** | **-13% 伤害** |
| 口语同义词 | 34.9% | **41.9%** | **-7% 伤害** |
| 错别字 | 50.0% | **56.7%** | **-7% 伤害** |
| 边界场景 | 57.9% | **63.2%** | **-5% 伤害** |

graph 仅在跨文档聚合（+9%）和复杂推理（+6%）上有正向贡献。

---

## 2. 优化目标

图数据库优化后的目标如下：

1. 图谱从"担保方案专用字段图"升级为"通用知识图底座"，支持担保方案、制度文件、项目文档、合同协议、通用文档、结构化数据等多种 profile。
2. 所有图谱节点和关系必须能追溯到原文证据，graph 结果必须能够回到 `chunk_id`、`section_id`、`file_node_id`。
3. graph 通道只在关系型、流程型、责任型、依赖型、范围型、对比型问题中发挥作用，不参与普通字段查询的主排序。
4. 图谱关系类型受控，不允许 LLM 自由生成不可治理的节点和关系。
5. 图检索结果进入 evidence group 时，定位为"关系证据"，不能替代原文主证据。
6. 支持增量构建和局部重建，避免每次索引都全量删除重建 Neo4j。
7. 支持可观测调试，能够解释 graph 为什么命中、命中了什么关系、证据来自哪里、最终是否参与排序。

---

## 3. 设计原则

### 3.1 通用底座，领域映射

Neo4j 底层不应写死为 `BusinessPlan / BusinessField / CounterGuarantee` 这类单业务节点，而应采用通用知识图模型。

担保方案、制度文件、项目文档、合同协议只是不同 profile，它们通过映射规则把领域概念落到通用节点和通用关系上。

例如：

```text
担保方案中的"加工贷"         -> Entity(type="product")
担保方案中的"反担保措施"     -> Requirement(type="counter_guarantee")
制度文件中的"审批职责"       -> Requirement(type="approval")
项目文档中的"接口"           -> Entity(type="api")
合同中的"违约责任"           -> Requirement(type="breach_liability")
```

底层 schema 保持统一，profile 只负责补充 `domain_type`、`field_code`、`profile` 等语义属性。

### 3.2 图谱只解决关系问题

图数据库不应该和 BM25、QA、structured 抢普通字段查询。

适合 graph 的问题包括：

```text
适用哪些区域
限制哪些行业
需要哪些材料
由谁负责
谁审批
引用了哪个制度
依赖哪个条件
包含哪些步骤
A 和 B 有什么关系
哪些产品满足某个条件
```

不适合 graph 作为主通道的问题包括：

```text
授信期限是多少
额度是多少
利率几个点
还款方式是什么
反担保措施原文是什么
```

这些字段型问题应以 `structured / BM25 / QA / vector` 为主，graph 最多作为辅助说明。

### 3.3 证据优先，图谱辅助

graph 结果必须绑定证据。

每条边至少需要具备：

```text
source_doc_id
file_node_id
section_id
chunk_id
evidence_text
confidence
parse_generation
index_generation
extract_source
```

如果一条图关系无法落回原文 chunk，则不能进入最终 evidence group，只能作为后台分析或待审核候选。

### 3.4 Schema 受控

LLM 可以参与抽取，但不能自由决定最终图谱 schema。

所有节点类型和关系类型必须经过白名单过滤。无法映射到白名单的结果保留在 MySQL 候选池或审核池，不直接写入 Neo4j。

---

## 4. 总体架构

优化后的图数据库架构分为五层：

```text
文档解析层
  -> Document / Section / Chunk

知识抽取层
  -> Entity / Attribute / Value / Requirement / Condition / ProcessStep / Event

Profile 映射层
  -> 将领域概念映射到通用 schema，并补充 domain_type

图谱存储层
  -> Neo4j 存节点、边、证据关系、别名关系、增量状态

图检索层
  -> 按 query intent 触发关系查询、路径查询、邻域扩展
```

MySQL、ES、Neo4j 的分工如下：

| 存储 | 职责 |
|---|---|
| MySQL | 文件、chunk、字段、知识单元、关系候选、审核状态、索引代际 |
| Elasticsearch | BM25、向量、字段、QA、章节摘要、关键词、伪问题召回 |
| Neo4j | 实体关系、依赖路径、适用范围、责任主体、流程步骤、别名归并、证据链 |

Neo4j 不替代 ES，也不替代 MySQL。它只负责"关系结构"和"关系路径"。

---

## 5. 通用图 Schema

### 5.1 通用节点类型

建议 Neo4j 使用以下通用节点类型：

| 节点类型 | 说明 |
|---|---|
| `Document` | 文档节点，对应文件或资料 |
| `Section` | 章节节点 |
| `Chunk` | 原文证据块 |
| `Entity` | 通用实体，如产品、系统、接口、合同主体、制度对象 |
| `Concept` | 抽象概念，如服务对象、风险缓释、授信政策 |
| `Attribute` | 属性项，如额度、期限、费率、状态 |
| `Value` | 属性值，如 12 个月、300 万元 |
| `Requirement` | 要求、材料、义务、审批要求、反担保要求 |
| `Condition` | 条件、准入条件、触发条件、限制条件 |
| `ProcessStep` | 流程步骤 |
| `Organization` | 机构、部门、企业、银行 |
| `PersonRole` | 角色、岗位、责任人类型 |
| `Location` | 区域、地点 |
| `Industry` | 行业、产业 |
| `Time` | 时间、期限、日期 |
| `Metric` | 金额、比例、数量、指标 |

### 5.2 通用关系类型

建议使用以下通用关系：

| 关系类型 | 说明 |
|---|---|
| `CONTAINS` | 包含关系，文档包含章节、章节包含 chunk、实体包含子项 |
| `MENTIONS` | 文档或 chunk 提到实体 |
| `HAS_ATTRIBUTE` | 实体具有某个属性 |
| `HAS_VALUE` | 属性具有某个取值 |
| `APPLIES_TO` | 适用于某对象、区域、行业、场景 |
| `EXCLUDES` | 排除、限制、不适用 |
| `REQUIRES` | 需要材料、条件、动作 |
| `CONSTRAINS` | 约束某对象或行为 |
| `DEPENDS_ON` | 依赖某条件、流程、系统、制度 |
| `REFERENCES` | 引用制度、文件、条款 |
| `RESPONSIBLE_FOR` | 负责某事项 |
| `APPROVES` | 审批某事项 |
| `PART_OF` | 属于某整体 |
| `OCCURS_BEFORE` | 流程先后关系 |
| `SAME_AS` | 别名、同义实体 |
| `RELATED_TO` | 低置信泛关系，仅作弱边 |
| `EVIDENCED_BY` | 节点或关系由某 chunk 证明 |

### 5.3 节点通用属性

所有业务节点建议具备以下属性：

```text
kb_id
node_key
name_cn
node_type
profile
domain_type
normalized_name
value_text
confidence
source
parse_generation
index_generation
created_at
updated_at
```

### 5.4 关系通用属性

所有业务边建议具备以下属性：

```text
kb_id
relation_key
profile
domain_relation_type
confidence
weight
evidence_count
source
parse_generation
index_generation
created_at
updated_at
```

关系证据可以采用两种方式：

1. 边属性直接存 `evidence_chunk_id`、`evidence_text`。
2. 关系节点化，即 `(a)-[:HAS_RELATION]->(r:RelationEvidence)-[:TO]->(b)`，再由 `RelationEvidence -EVIDENCED_BY-> Chunk`。

短期建议先采用第一种，工程改造较小。中长期如果需要多证据、多来源、多版本审核，再升级为关系节点化。

---

## 6. Profile 映射设计

### 6.1 Profile 映射不是重新定义图

不同 profile 不应该各自拥有完全不同的 Neo4j 节点和边。它们应共享通用 schema，再通过映射规则补充领域语义。

映射配置示例：

```python
PROFILE_GRAPH_MAPPINGS = {
    "business_plan": {
        "entity_types": {
            "product": {"node": "Entity", "domain_type": "product"},
            "service_object": {"node": "Concept", "domain_type": "service_object"},
            "material": {"node": "Requirement", "domain_type": "material"},
            "counter_guarantee": {"node": "Requirement", "domain_type": "counter_guarantee"},
            "risk_measure": {"node": "Requirement", "domain_type": "risk_measure"},
        },
        "relations": {
            "applies_to": "APPLIES_TO",
            "requires": "REQUIRES",
            "excludes_industry": "EXCLUDES",
            "cooperates_with": "RELATED_TO",
            "depends_on": "DEPENDS_ON",
            "references": "REFERENCES",
        },
    },
    "governance_rule": {
        "entity_types": {
            "rule_document": {"node": "Document", "domain_type": "rule_document"},
            "clause": {"node": "Section", "domain_type": "clause"},
            "department": {"node": "Organization", "domain_type": "department"},
            "responsibility": {"node": "Requirement", "domain_type": "responsibility"},
            "approval": {"node": "Requirement", "domain_type": "approval"},
        },
        "relations": {
            "responsible_for": "RESPONSIBLE_FOR",
            "approves": "APPROVES",
            "requires": "REQUIRES",
            "references": "REFERENCES",
            "contains": "CONTAINS",
        },
    },
}
```

### 6.2 担保方案映射

担保方案 profile 重点关系：

| 领域对象 | 通用节点 |
|---|---|
| 产品 / 方案 | `Entity(domain_type="product")` |
| 适用客户 | `Concept(domain_type="service_object")` |
| 准入条件 | `Condition(domain_type="admission")` |
| 材料 | `Requirement(domain_type="material")` |
| 反担保措施 | `Requirement(domain_type="counter_guarantee")` |
| 风险缓释措施 | `Requirement(domain_type="risk_measure")` |
| 办理步骤 | `ProcessStep(domain_type="application_step")` |
| 区域 | `Location` |
| 行业 | `Industry` |
| 合作机构 | `Organization` |

关系示例：

```text
Product -APPLIES_TO-> Location
Product -APPLIES_TO-> Industry
Product -EXCLUDES-> Industry
Product -REQUIRES-> Requirement(material)
Product -REQUIRES-> Condition(admission)
Product -REQUIRES-> Requirement(counter_guarantee)
Product -RELATED_TO-> Organization
Product -CONTAINS-> ProcessStep
ProcessStep -OCCURS_BEFORE-> ProcessStep
```

### 6.3 制度文件映射

制度文件 profile 重点关系：

```text
Document -CONTAINS-> Section(clause)
Section -RESPONSIBLE_FOR-> Organization
Section -APPROVES-> Requirement(approval)
Section -REQUIRES-> Requirement
Section -REFERENCES-> Document / Section
Section -CONSTRAINS-> Entity / Concept
```

适合回答：

```text
哪个部门负责
谁审批
依据哪条制度
哪个章节规定了某事项
某流程需要哪些审批
```

### 6.4 项目文档映射

项目文档 profile 重点关系：

```text
System -CONTAINS-> Module
Module -CONTAINS-> Entity(api)
API -REQUIRES-> Attribute(parameter)
API -HAS_VALUE-> Value(example)
Module -DEPENDS_ON-> Module
Module -REFERENCES-> Entity(database_table)
Entity(config_item) -CONSTRAINS-> Module
```

适合回答：

```text
某接口依赖哪些模块
某配置影响哪些功能
某表被哪些接口使用
某模块有哪些外部依赖
```

### 6.5 合同协议映射

合同 profile 重点关系：

```text
Document(contract) -CONTAINS-> Section(clause)
Organization / PersonRole -RESPONSIBLE_FOR-> Requirement(obligation)
Condition -CONSTRAINS-> Requirement
Requirement -HAS_ATTRIBUTE-> Metric / Time
Section -REFERENCES-> Section
```

适合回答：

```text
甲方有哪些义务
违约条件是什么
付款节点是什么
哪个条款约束了某责任
```

---

## 7. 图构建流程

### 7.1 输入来源

图构建不应只依赖 `fields`。应同时接入以下来源：

1. `kb_chunk`：Document / Section / Chunk 结构。
2. `kb_field`：已抽取字段。
3. `kb_anchor_registry`：实体锚点。
4. `kb_knowledge_unit`：知识单元。
5. `kb_relation`：LLM 或规则抽取出的关系。
6. `file_chunk_relations`：父子 chunk、章节关系。

### 7.2 构建步骤

建议新增 `knowledge_graph_builder.py`，负责把 MySQL 中的知识结构转成通用图记录。

流程：

```text
load graph source rows
  -> normalize anchors
  -> apply profile mapping
  -> filter schema
  -> bind evidence
  -> dedupe nodes
  -> dedupe edges
  -> compute edge weight
  -> write Neo4j
```

### 7.3 证据绑定规则

节点证据：

```text
Entity / Attribute / Requirement / Condition
  -EVIDENCED_BY->
Chunk
```

边证据：

```text
边属性：
evidence_chunk_id
evidence_text
evidence_quote
confidence
```

如果一条关系没有 chunk 证据：

1. 不写入 Neo4j 主图；
2. 写入 MySQL 候选池；
3. 标记 `review_status='pending'`；
4. 不参与 graph 检索。

### 7.4 规则关系补召回

LLM 抽取可能漏掉显式关系，因此需要保留规则关系抽取。

规则关系适合处理：

```text
A 适用于 B
A 不适用于 B
A 由 B 负责
A 需提交 B
A 包括 B
A 依据 B
A 依赖 B
A 又称 B
```

规则关系不能覆盖 LLM 高置信关系。同一 from/to/relation 已存在时，只增加 `evidence_count` 和 `weight`，不重复造边。

---

## 8. 图检索设计

### 8.1 查询意图分类

检索前先识别 query intent。

通用 intent：

| intent | 说明 | 主要关系 |
|---|---|---|
| `attribute_lookup` | 查属性值 | `HAS_ATTRIBUTE`, `HAS_VALUE` |
| `scope_lookup` | 查适用范围 | `APPLIES_TO`, `EXCLUDES` |
| `requirement_lookup` | 查要求、材料、条件 | `REQUIRES`, `CONSTRAINS` |
| `responsibility_lookup` | 查责任主体 | `RESPONSIBLE_FOR`, `APPROVES` |
| `process_lookup` | 查流程 | `CONTAINS`, `OCCURS_BEFORE` |
| `dependency_lookup` | 查依赖、引用、依据 | `DEPENDS_ON`, `REFERENCES` |
| `comparison_lookup` | 查对比 | `HAS_ATTRIBUTE`, `HAS_VALUE`, `SAME_AS` |
| `evidence_lookup` | 查出处 | `EVIDENCED_BY`, `REFERENCES` |

graph 只在以下 intent 中默认启用：

```text
scope_lookup
requirement_lookup
responsibility_lookup
process_lookup
dependency_lookup
comparison_lookup
evidence_lookup
```

`attribute_lookup` 默认不启用 graph，除非字段结果不足或用户明确问"关系/依据/出处"。

### 8.2 图检索模式

#### 模式一：锚点关系查询

适用问题：

```text
加工贷适用哪些区域
某制度由哪个部门负责
```

查询逻辑：

```cypher
MATCH (a {kb_id: $kb_id})-[r]->(b)
WHERE a.normalized_name IN $anchor_names
  AND type(r) IN $relation_types
RETURN a, type(r), b, r
```

#### 模式二：反向关系查询

适用问题：

```text
哪些产品适用于山东省
哪些制度涉及审批
哪些接口依赖用户表
```

查询逻辑：

```cypher
MATCH (a)-[r]->(b {kb_id: $kb_id})
WHERE b.normalized_name IN $target_names
  AND type(r) IN $relation_types
RETURN a, type(r), b, r
```

#### 模式三：证据路径查询

适用问题：

```text
这个结论依据哪里
哪个条款证明了这个要求
```

查询逻辑：

```cypher
MATCH (a)-[r]->(b)
MATCH (a)-[:EVIDENCED_BY]->(ca:Chunk)
MATCH (b)-[:EVIDENCED_BY]->(cb:Chunk)
WHERE a.kb_id = $kb_id
RETURN a, r, b, ca, cb
```

#### 模式四：受控 BFS 邻域扩展

适用问题：

```text
这个产品涉及哪些机构、区域和条件
A 和 B 有什么关系
```

限制条件：

```text
max_depth <= 2
max_nodes <= 50
allowed_relation_types 必须由 intent 决定
禁止从泛化节点无限扩散
必须返回 evidence_chunk_id
```

### 8.3 图结果格式

graph 查询结果应统一转换成候选：

```json
{
  "route": "graph",
  "hit_type": "graph_relation",
  "kb_id": 1,
  "file_node_id": 100,
  "chunk_id": 2001,
  "source": "加工贷",
  "relation": "APPLIES_TO",
  "target": "山东省",
  "evidence_text": "本产品适用于山东省内...",
  "graph_depth": 1,
  "relationship_weight": 0.86,
  "evidence_weight": 0.92,
  "score": 0.88,
  "graph_intent": {
    "intent": "scope_lookup",
    "relations": ["APPLIES_TO"]
  }
}
```

进入 evidence group 时，`chunk_id` 必须有效。

---

## 9. 排序与融合

graph score 不应只看 Neo4j 命中，而应综合：

```text
graph_score =
relation_intent_match
* edge_weight
* evidence_weight
* anchor_match
* profile_match
* freshness
- depth_penalty
- generic_node_penalty
```

建议规则：

1. relation 与 query intent 完全匹配，加权。
2. 命中产品名、制度名、接口名等 scope anchor，加权。
3. 命中泛化节点，如"条件""流程""业务""要求"，降权。
4. BFS depth=1 优先于 depth=2。
5. 没有 evidence chunk 的结果直接过滤。
6. graph 默认权重低，只有关系型问题才提高权重。

推荐通道策略：

| 问题类型 | 主通道 | graph 角色 |
|---|---|---|
| 字段查询 | structured / BM25 / QA | 默认关闭或低权重 |
| 口语字段查询 | QA / BM25 / vector | 默认关闭 |
| 范围查询 | graph / structured / BM25 | 主召回之一 |
| 责任查询 | graph / section_summary / BM25 | 主召回之一 |
| 流程查询 | section_summary / graph / BM25 | 辅助结构化流程 |
| 依赖查询 | graph / BM25 | 主召回之一 |
| 对比查询 | BM25 / structured / graph | graph 辅助补齐关系 |

---

## 10. 增量构建与更新

### 10.1 图谱 hash

每个图谱构建单元建议计算：

```text
graph_node_hash
graph_edge_hash
graph_snapshot_hash
```

hash 输入包括：

```text
kb_id
file_node_id
chunk_id
anchor normalized_name
unit content
relation type
evidence chunk
parse_generation
```

### 10.2 局部重建

文件重建时不应全库删除。

建议粒度：

1. 文档级：删除某 `file_node_id` 下的 Document / Section / Chunk / 私有 Entity。
2. chunk 级：只删除该 chunk 产生的节点和边。
3. 共享节点：如 Organization、Location、Industry、SAME_AS 别名簇不直接删除，只有无入边时异步清理。

### 10.3 写入策略

Neo4j 写入采用 `MERGE`，边重复出现时更新：

```text
weight = max(old.weight, new.weight)
evidence_count += 1
last_seen_generation = current_generation
updated_at = datetime()
```

不要因为重复抽取而重复造多条同义边。

---

## 11. 实施计划

### Phase 1：图检索降噪与证据约束

目标：让 graph 不再拖累普通问答。

任务：

1. graph 只在关系型 intent 下默认启用。
2. graph 查询必须返回 `chunk_id`。
3. evidence group 中标记 graph 为关系证据。
4. graph 默认融合权重降低。
5. graph debug 输出 intent、relation、depth、evidence chunk。

验收：

1. 字段型查询不再默认进入 graph。
2. `no_graph` 消融不应明显优于 baseline。
3. graph 命中结果都能回到原文 chunk。

### Phase 2：通用 Schema 与 Profile 映射

目标：从担保字段图升级为通用知识图。

任务：

1. 新增 `graph_profile_mapping.py`。
2. 定义通用节点和通用关系白名单。
3. 将 business_plan、governance_rule、project_doc、contract_agreement 映射到通用 schema。
4. 无法映射的关系进入审核池，不写 Neo4j。

验收：

1. Neo4j 不再只有 `BusinessPlan / BusinessField`。
2. 不同 profile 的节点都能落入统一 schema。
3. schema reject 有日志和统计。

### Phase 3：Knowledge Relation 入图

目标：让 `kb_anchor_registry / kb_knowledge_unit / kb_relation` 成为 Neo4j 主数据来源。

任务：

1. 新增 `knowledge_graph_builder.py`。
2. 从 MySQL 读取 anchor、unit、relation、evidence。
3. 映射为通用节点和边。
4. 写入 Neo4j。
5. 为每条边绑定 evidence chunk。

验收：

1. "适用区域、限制行业、所需材料、责任部门、引用依据"等关系能通过 Neo4j 查到。
2. 每条关系都有 evidence chunk。
3. graph 查询能直接拉回 evidence group。

### Phase 4：Anchor 治理与 SAME_AS

目标：解决同义实体分裂导致图谱稀疏的问题。

任务：

1. 引入 MinHash / Jaro-Winkler / LLM 仲裁候选池。
2. 建立 `SAME_AS` 关系。
3. 审核通过后写回 MySQL、ES、Neo4j。
4. 查询时先归一到 canonical entity。

验收：

1. 产品名、制度名、机构名同义写法能合并。
2. 图谱节点度更真实。
3. 不同写法查询返回同一关系证据。

### Phase 5：增量图谱与调试视图

目标：降低重建成本，提高可观测性。

任务：

1. 增加 graph hash。
2. 支持文件级和 chunk 级局部重建。
3. debug 返回 graph path、relation score、evidence score。
4. 前端展示图谱命中路径和证据 chunk。

验收：

1. 未变化文件不重复重建 Neo4j。
2. 修改单个文件不影响其他文件图谱。
3. 能解释每个 graph 命中的来源和排序原因。

---

## 12. 验收指标

### 12.1 准确率指标

1. 字段型问题 Top-1 不因 graph 开启下降。
2. 关系型问题 Top-1 提升。
3. 对比型问题 coverage 提升。
4. `no_graph` 消融不再显著优于 baseline。

### 12.2 图谱质量指标

```text
graph_node_count
graph_edge_count
graph_schema_reject_count
graph_evidence_missing_count
graph_same_as_count
graph_relation_with_evidence_rate
graph_relation_avg_confidence
```

关键目标：

```text
graph_relation_with_evidence_rate >= 95%
graph_evidence_missing_count 趋近于 0
graph_schema_reject_count 可解释、可审计
```

### 12.3 检索可观测指标

```text
graph_trigger_rate
graph_hit_count
graph_used_in_final_evidence_count
graph_filtered_no_evidence_count
graph_depth_distribution
graph_relation_type_distribution
graph_score_distribution
```

这些指标用于判断 graph 是否被过度触发，是否仍然存在噪声。

---

## 13. 风险与控制

### 13.1 风险：通用 Schema 太抽象

如果 schema 太抽象，所有东西都变成 `Entity -RELATED_TO-> Entity`，图谱会失去语义。

控制方式：

1. 保留通用节点和通用关系。
2. 必须补充 `domain_type`。
3. `RELATED_TO` 只能作为低置信弱边。
4. 关系型查询优先使用强语义边。

### 13.2 风险：LLM 造关系

LLM 可能生成不可靠关系。

控制方式：

1. schema 白名单过滤。
2. 证据 chunk 必填。
3. 规则关系不覆盖高置信 LLM 关系。
4. 低置信关系进入审核池。

### 13.3 风险：graph 抢排序

graph 如果和正文通道平权，容易把弱关系排到前面。

控制方式：

1. graph 只在关系型 intent 下默认启用。
2. graph 默认低权重。
3. graph 结果必须 evidence-bound。
4. prompt 中标注 graph 为关系证据，不替代原文主证据。

### 13.4 风险：工程复杂度过高

一次性重构图谱链路风险较高。

控制方式：

1. 先做 graph 降噪。
2. 再做通用 schema。
3. 再做 knowledge relation 入图。
4. 最后做 anchor 治理和增量图谱。

---

## 14. 推荐落地顺序

优先级建议：

| 优先级 | 事项 | 价值 |
|---|---|---|
| P0 | graph intent gate、证据过滤、低权重 | 立即降低噪声 |
| P0 | graph debug 输出 | 方便验证问题 |
| P1 | 通用 schema + profile mapping | 解决普适性 |
| P1 | knowledge relation 入图 | 让 Neo4j 真正有新增价值 |
| P1 | 关系型 query Cypher 模板 | 提升关系问题 |
| P2 | SAME_AS / anchor 治理 | 提高图谱连通性 |
| P2 | 增量图谱 | 降低工程成本 |
| P3 | 社区检测 / 路径推荐 | 高级能力，后置 |

---

## 15. 总结

danbao-poc 当前 graph 通道价值不明显，核心原因是 Neo4j 主要存的是字段图，和 structured 检索信息重叠，缺少真正的关系型知识图和证据绑定。

优化方向不是把担保方案节点继续做细，而是建立一套通用图数据库底座：

```text
通用 Schema
+ Profile 映射
+ 证据绑定
+ 意图驱动图检索
+ Anchor 治理
+ 增量构建
```

这样 Neo4j 才能从"字段结果的可视化备份"变成"关系问题的专用检索引擎"。

最终效果应该是：

1. 字段问题仍由 structured / BM25 / QA 主导。
2. 关系问题由 graph 精准补强。
3. 所有 graph 结论都能回到原文证据。
4. 不同 profile 共用同一套底层图模型。
5. 图谱不再是噪声通道，而是可解释、可追溯、可治理的关系检索资产。

---

## 16. 附录：开发环境实测问题清单与修复建议

> 本节基于 2026-06-01 对开发环境 Neo4j 的实际数据探查，记录发现的具体问题和修复建议。

### 16.1 关系 weight 属性缺失（紧急）

**现状**：1435 条关系中，只有 55 条（3.8%）有 weight 属性。EVIDENCED_BY（489 条）和 RELATED_TO（58 条）的 weight 全部为 None。

**根因**：历史数据在旧版代码（未写入 weight）下导入，Neo4j 的 `MERGE` 不会更新已有关系的属性。

**影响**：`_graph_relation_score()` 中的 `relationship_weight` 和 `evidence_weight` 全部回退到默认值，排序公式形同虚设。

**修复建议**：
1. 写一个一次性 Cypher 脚本，为所有缺失 weight 的关系补填默认值：
   ```cypher
   MATCH ()-[r:EVIDENCED_BY]->() WHERE r.weight IS NULL SET r.weight = 0.92;
   MATCH ()-[r:HAS_FIELD]->() WHERE r.weight IS NULL SET r.weight = 1.00;
   MATCH ()-[r:RELATED_TO]->() WHERE r.weight IS NULL SET r.weight = 0.70;
   MATCH ()-[r:IN_REGION]->() WHERE r.weight IS NULL SET r.weight = 0.78;
   MATCH ()-[r:IN_INDUSTRY]->() WHERE r.weight IS NULL SET r.weight = 0.74;
   MATCH ()-[r:PARSED_AS]->() WHERE r.weight IS NULL SET r.weight = 0.50;
   ```
2. 改造 `import_business_graph()` 中的 MERGE 语句，使用 `ON CREATE SET` + `ON MATCH SET` 确保已有关系也能更新 weight：
   ```cypher
   MERGE (a)-[r:IN_REGION]->(b)
   ON CREATE SET r.weight = $weight, r.parse_generation = $pg, r.index_generation = $ig
   ON MATCH SET r.weight = CASE WHEN $weight > coalesce(r.weight, 0) THEN $weight ELSE r.weight END
   ```

### 16.2 制度文件无图谱（重要）

**现状**：`kb_id=862026050615464176`（7 个制度文件）在 Neo4j 中只有 7 个 File 节点，无任何业务节点。

**根因**：`governance_rule` profile 的 graph builder 未实现。`graph_schema.py` 中定义了 schema（RuleDocument、Chapter、Clause、Role、Responsibility、Decision），但 `profiles/registry.py` 中没有注册对应的 graph builder。

**影响**：制度类查询（315 题中占比 23%，错误率 56.5%~66.7%）完全无法利用图谱。

**修复建议**：Phase 2 优先为 `governance_rule` 实现 graph builder，至少支持 `Chapter -> Clause -> Responsibility -> Organization` 这条核心链路。

### 16.3 GraphRAG 数据未导入（低）

**现状**：GraphEntity 节点数量为 0。

**根因**：`graphrag_adapter.py` 的导入脚本（`scripts/06_import_graphrag_to_neo4j.py`）未被运行，或运行失败。

**影响**：GraphRAG 的实体关系数据无法被图检索利用。

**修复建议**：确认 GraphRAG parquet 文件是否存在，如果存在则重新运行导入脚本；如果不需要 GraphRAG 数据，则清理相关代码避免混淆。

### 16.4 Cypher 注入风险（中等）

**现状**：`graph_writer.py` 第 92 行和 170-173 行用 f-string 拼接 node label 和 edge type：
```python
f"MERGE (n:{labels} {{kb_id: $kb_id, ...}})"
f"MERGE (a)-[r:{edge['edge_type']}]->(b)"
```

**根因**：虽然有 `filter_graph_records()` 做白名单过滤，但上游如果绕过此函数就是直接的 Cypher 注入。

**修复建议**：
1. 在 `import_business_graph()` 入口处加断言，校验 label 和 edge_type 必须在白名单内
2. 或改用 APOC 的 `apoc.merge.node` 等安全函数
3. 或用参数化方式构建 Cypher（Neo4j 不支持参数化 label，但可以在 Python 侧用白名单校验后拼接）

### 16.5 连接管理（低）

**现状**：`graph_writer.py`、`query.py`、`graphrag_adapter.py` 每个函数都自己 `driver()` + `close()`。

**修复建议**：引入全局单例 driver，用 `atexit` 注册关闭。示例：
```python
_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver

import atexit
atexit.register(lambda: _driver.close() if _driver else None)
```

### 16.6 EVIDENCED_BY 证据粒度粗糙（中等）

**现状**：`evidence_text` 存储的是 Chunk 的 `content_preview`（前 500 字符），而非精确的证据引用。例如 `document_no` 字段的 evidence_text 是整个 chunk 的开头文本，而非具体提取出的文号值。

**修复建议**：
1. 在 `import_business_graph()` 中，evidence_text 改为使用 `mention_row.get("evidence_text")` 中的精确引用（当前代码已有此逻辑，但 fallback 到了 chunk preview）
2. 确保 `kb_field_mention` 表中的 `evidence_text` 字段被正确填充

### 16.7 shared 节点 delete 保护（低）

**现状**：`delete_file_graph()` 用 `{kb_id, file_node_id}` 匹配删除。Region/Industry/Organization 节点没有 `file_node_id` 属性，理论上不会被误删。但这个设计依赖隐含假设。

**修复建议**：在 `delete_file_graph()` 中加显式保护：
```cypher
MATCH (n {kb_id: $kb_id, file_node_id: $file_node_id})
WHERE NOT n:Region AND NOT n:Industry AND NOT n:Organization
DETACH DELETE n
```
