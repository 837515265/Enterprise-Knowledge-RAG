# 图数据库结构化检索实施方案

> 基于消融测试结论和 DataGraphX/Graphify/GraphRAG-Example 最佳实践
> 2026-06-02

## 1. 问题诊断

### 1.1 消融测试结论

10 道关系型问题，graph 只有 1 道提供了独特有用证据，6 道完全无贡献。

根本原因：**graph 返回的是 chunk 内容，和 BM25/vector 返回的东西一模一样。**

```
当前：graph_query() → Cypher → Chunk.content_preview → 和 BM25 重叠
应该：graph_query() → Cypher → (产品名, 关系, 值) → 结构化答案
```

### 1.2 其他项目怎么做的

| 项目 | graph 返回什么 | 独特价值 |
|---|---|---|
| DataGraphX | 三元组 (source, relation, target) | "A 依赖 B" vs "A 提到 B" |
| Graphify | 子图文本 + 边类型标注 | "A calls B, B imports C" |
| GraphRAG-Example | 节点+边，标记为"辅助参考" | 关系骨架，非独立证据 |

共同点：**graph 返回的是关系结构，不是文本块。**

---

## 2. 设计方案

### 2.1 核心思路

graph 通道输出两种格式：

1. **结构化三元组**（主输出）：`(产品名, 关系类型, 目标值)` → 直接回答关系型问题
2. **证据 chunk**（辅助输出）：三元组关联的原文 chunk → 用于引用和验证

### 2.2 五种专用查询模板

#### 模板 1：反向关系查询（"哪些产品满足 X 条件"）

用途：从条件/属性反查产品

```cypher
// 查找包含关键词的所有节点，返回关联的 Entity
MATCH (e:Entity {kb_id: $kb_id})-[r]->(n)
WHERE any(term IN $terms WHERE n.name_cn CONTAINS term OR n.value_text CONTAINS term)
  AND type(r) IN $relation_types
OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c:Chunk)
RETURN e.name_cn AS source_entity,
       type(r) AS relation,
       n.name_cn AS target_name,
       n.value_text AS target_value,
       labels(n)[0] AS target_type,
       c.chunk_id AS chunk_id,
       c.title_cn AS chunk_title,
       coalesce(r.weight, 0.5) AS weight
ORDER BY coalesce(r.weight, 0.5) DESC
LIMIT $top_k
```

示例查询："哪些产品不需要提供房产抵押"

```cypher
MATCH (e:Entity {kb_id: $kb_id})-[r:EXCLUDES]->(n)
WHERE n.name_cn CONTAINS '房产' OR n.value_text CONTAINS '房产'
OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c:Chunk)
RETURN e.name_cn AS product, 'EXCLUDES' AS relation, n.name_cn AS condition
```

返回：
```json
[
  {"source": "农耕贷", "relation": "EXCLUDES", "target": "房产抵押"},
  {"source": "富农产业贷", "relation": "REQUIRES", "target": "房产抵押"}
]
```

#### 模板 2：多实体对比查询（"A 和 B 的 X 有什么区别"）

用途：拉取多个实体的同类属性做结构化对比

```cypher
// 从 query 中提取实体名，分别拉取属性
MATCH (e:Entity {kb_id: $kb_id})-[r]->(n)
WHERE e.name_cn IN $entity_names
  AND type(r) IN $relation_types
OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c:Chunk)
RETURN e.name_cn AS source_entity,
       type(r) AS relation,
       n.name_cn AS target_name,
       n.value_text AS target_value,
       n.domain_type AS domain_type,
       c.chunk_id AS chunk_id
ORDER BY e.name_cn, type(r)
```

示例查询："农耕贷和加工贷的反担保措施有什么区别"

```cypher
MATCH (e:Entity {kb_id: $kb_id})-[:REQUIRES]->(r:Requirement {domain_type: 'counter_guarantee'})
WHERE e.name_cn IN ['农耕贷', '加工贷']
RETURN e.name_cn AS product, r.name_cn AS requirement, r.value_text AS detail
```

返回：
```json
[
  {"product": "农耕贷", "requirement": "反担保", "detail": "自然人客户配偶及子女提供连带责任保证"},
  {"product": "加工贷", "requirement": "反担保", "detail": "房产抵押+自然人保证"}
]
```

#### 模板 3：范围反查查询（"X 地区有哪些产品"）

用途：从区域/行业反查产品

```cypher
MATCH (e:Entity {kb_id: $kb_id})-[r:APPLIES_TO]->(n)
WHERE n.name_cn CONTAINS $target_name OR n.value_text CONTAINS $target_name
OPTIONAL MATCH (e)-[:EVIDENCED_BY]->(c:Chunk)
RETURN e.name_cn AS product, n.name_cn AS scope, c.chunk_id AS chunk_id
LIMIT $top_k
```

示例查询："滨州市有哪些产品"

```cypher
MATCH (e:Entity {kb_id: $kb_id})-[r]->(n)
WHERE n.name_cn CONTAINS '滨州' OR n.value_text CONTAINS '滨州'
RETURN e.name_cn AS product, type(r) AS relation, n.name_cn AS target
```

#### 模板 4：全产品属性遍历（"所有产品的 X 分别是多少"）

用途：遍历所有产品的某个属性

```cypher
MATCH (e:Entity {kb_id: $kb_id})-[:HAS_ATTRIBUTE]->(a:Attribute)
WHERE a.domain_type = $attribute_type
RETURN e.name_cn AS product, a.name_cn AS attribute, a.value_text AS value
ORDER BY e.name_cn
```

示例查询："所有产品的担保费率分别是多少"

```cypher
MATCH (e:Entity {kb_id: $kb_id})-[:HAS_ATTRIBUTE]->(a:Attribute {domain_type: 'guarantee_rate'})
RETURN e.name_cn AS product, a.value_text AS rate
```

返回：
```json
[
  {"product": "农耕贷", "rate": "0.75%/年"},
  {"product": "加工贷", "rate": "0.75%/年"},
  {"product": "富农产业贷", "rate": "0.75%/年"}
]
```

#### 模板 5：BFS 子图扩展（"这个产品涉及哪些方面"）

用途：从一个实体出发，遍历其所有关系

```cypher
MATCH (e:Entity {kb_id: $kb_id, name_cn: $entity_name})-[r*1..2]-(n)
WHERE all(rel IN r WHERE type(rel) IN $allowed_relations)
  AND NOT "Entity" IN labels(n)
WITH e, n, r, length(r) AS depth
OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c:Chunk)
RETURN e.name_cn AS source,
       [rel IN r | type(rel)] AS path,
       labels(n)[0] AS target_type,
       n.name_cn AS target_name,
       n.value_text AS target_value,
       depth,
       c.chunk_id AS chunk_id
ORDER BY depth, coalesce(r[0].weight, 0.5) DESC
LIMIT 20
```

### 2.3 查询意图 → 模板映射

```python
GRAPH_QUERY_TEMPLATES = {
    # "哪些产品满足X条件" → 反向关系查询
    "reverse_relation": {
        "triggers": ["哪些", "什么产品", "哪些方案", "哪些产品"],
        "template": "reverse_lookup",
        "relation_types": ["APPLIES_TO", "EXCLUDES", "REQUIRES", "CONSTRAINS"],
    },
    # "A和B有什么区别" → 多实体对比
    "comparison": {
        "triggers": ["区别", "不同", "对比", "比较", "一样吗"],
        "template": "multi_entity_compare",
        "relation_types": ["HAS_ATTRIBUTE", "REQUIRES", "APPLIES_TO"],
    },
    # "X地区有哪些产品" → 范围反查
    "scope_reverse": {
        "triggers": ["有哪些", "有哪些产品", "哪些方案"],
        "template": "scope_reverse_lookup",
        "relation_types": ["APPLIES_TO"],
    },
    # "所有产品的X" → 全产品遍历
    "all_products": {
        "triggers": ["所有", "全部", "各个", "分别"],
        "template": "all_product_attribute",
        "relation_types": ["HAS_ATTRIBUTE"],
    },
    # "这个产品涉及什么" → BFS 扩展
    "bfs_expand": {
        "triggers": ["涉及", "包含", "包括", "有哪些方面"],
        "template": "bfs_subgraph",
        "relation_types": ["HAS_ATTRIBUTE", "REQUIRES", "APPLIES_TO", "CONTAINS"],
    },
}
```

---

## 3. 输出格式

### 3.1 结构化三元组输出

graph 通道的核心输出是结构化三元组，不是 chunk 内容：

```python
{
    "route": "graph",
    "hit_type": "graph_structured",
    "template": "reverse_relation",  # 使用的查询模板

    # 结构化答案
    "structured_results": [
        {
            "source": "农耕贷",
            "relation": "EXCLUDES",
            "target": "房产抵押",
            "target_type": "Requirement",
            "confidence": 0.85,
        },
        {
            "source": "加工贷",
            "relation": "REQUIRES",
            "target": "房产抵押",
            "target_type": "Requirement",
            "confidence": 0.90,
        },
    ],

    # 证据 chunk（用于引用验证）
    "evidence_chunks": [
        {
            "chunk_id": 123456,
            "file_node_id": 789,
            "title": "反担保措施",
            "content_preview": "...",
            "page_no": 5,
        }
    ],

    # 融合排序用
    "score": 0.88,
    "source_priority": "auxiliary",  # 标记为辅助证据
}
```

### 3.2 Evidence Group 中的表示

在 evidence_groups 中，graph 结果标记为 `source_priority="auxiliary"`：

```python
{
    "group_id": "eg_001",
    "display_text": "农耕贷：不需要房产抵押（EXCLUDES）。加工贷：需要房产抵押（REQUIRES）。",
    "hit_routes": ["graph"],
    "source_priority": "auxiliary",  # graph 是辅助证据
    "structured_answer": {
        "products": [
            {"name": "农耕贷", "relation": "EXCLUDES", "target": "房产抵押"},
            {"name": "加工贷", "relation": "REQUIRES", "target": "房产抵押"},
        ]
    },
    "evidence_chunks": [...],
}
```

### 3.3 LLM Prompt 中的区分

answer_context_prompt 中明确区分主证据和辅助证据：

```
回答要求：
1. 优先使用 [primary] 标记的原文证据回答问题
2. [auxiliary] 标记的图谱关系仅用于补充说明关系结构
3. 如果图谱显示"农耕贷 EXCLUDES 房产抵押"，应结合原文证据确认
4. 图谱结论必须有原文证据支撑，不能单独使用图谱关系回答
```

---

## 4. 实施步骤

### Step 1：新增查询模板模块

新建 `src/danbao_poc/graph_templates.py`：

```python
def reverse_relation_query(session, kb_id, terms, relation_types, top_k):
    """反向关系查询：从关键词反查 Entity。"""
    cypher = """
        MATCH (e:Entity {kb_id: $kb_id})-[r]->(n)
        WHERE any(term IN $terms WHERE n.name_cn CONTAINS term OR n.value_text CONTAINS term)
          AND type(r) IN $relation_types
        OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c:Chunk)
        RETURN e.name_cn AS source, type(r) AS relation,
               n.name_cn AS target, n.value_text AS target_value,
               labels(n)[0] AS target_type,
               c.chunk_id AS chunk_id, c.title_cn AS chunk_title,
               coalesce(r.weight, 0.5) AS weight
        ORDER BY weight DESC LIMIT $top_k
    """
    # ...

def multi_entity_compare(session, kb_id, entity_names, relation_types):
    """多实体对比：拉取多个实体的同类属性。"""
    # ...

def scope_reverse_lookup(session, kb_id, target_name, top_k):
    """范围反查：从区域/行业反查产品。"""
    # ...

def all_product_attribute(session, kb_id, attribute_type):
    """全产品属性遍历。"""
    # ...

def bfs_subgraph(session, kb_id, entity_name, allowed_relations, max_depth=2, max_nodes=20):
    """BFS 子图扩展。"""
    # ...
```

### Step 2：改造意图路由

修改 `src/danbao_poc/graph_intent.py`：

```python
def infer_graph_query_template(query, understanding):
    """推断 graph 查询模板。"""
    text = query or ""

    # 反向关系："哪些产品不需要房产抵押"
    if any(t in text for t in ["哪些", "什么产品"]):
        terms = extract_condition_terms(text)
        if terms:
            return {"template": "reverse_relation", "terms": terms}

    # 多实体对比："农耕贷和加工贷的区别"
    entities = extract_entity_names(text, understanding)
    if len(entities) >= 2 and any(t in text for t in ["区别", "不同", "对比"]):
        return {"template": "comparison", "entities": entities}

    # 范围反查："滨州有哪些产品"
    if any(t in text for t in ["有哪些", "有哪些产品"]):
        scope = extract_scope_term(text)
        if scope:
            return {"template": "scope_reverse", "scope": scope}

    # 全产品遍历："所有产品的费率"
    if any(t in text for t in ["所有", "全部", "分别"]):
        attr = extract_attribute_type(text)
        if attr:
            return {"template": "all_product_attribute", "attribute": attr}

    return None  # 不触发 graph
```

### Step 3：改造 graph_query()

修改 `src/danbao_poc/query.py` 的 `graph_query()`：

```python
def graph_query(...):
    # 1. 推断查询模板
    template = infer_graph_query_template(query, understanding)

    if template:
        # 2. 使用专用模板查询
        if template["template"] == "reverse_relation":
            results = reverse_relation_query(session, kb_id, template["terms"], ...)
        elif template["template"] == "comparison":
            results = multi_entity_compare(session, kb_id, template["entities"], ...)
        # ...

        # 3. 构造结构化输出
        return [{
            "route": "graph",
            "hit_type": "graph_structured",
            "template": template["template"],
            "structured_results": results,
            "evidence_chunks": extract_evidence_chunks(results),
            "score": compute_graph_score(results),
            "source_priority": "auxiliary",
        }]
    else:
        # 4. 不触发 graph，返回空
        return []
```

### Step 4：改造 evidence_groups 构建

修改 `build_evidence_groups()` 让 graph 结果以结构化形式进入：

```python
def build_evidence_groups(...):
    for candidate in candidates:
        if candidate.get("route") == "graph" and candidate.get("hit_type") == "graph_structured":
            # graph 结构化结果：生成结构化 display_text
            structured = candidate.get("structured_results", [])
            display = format_structured_answer(structured)  # "农耕贷: 不需要房产抵押; 加工贷: 需要房产抵押"
            group = {
                "display_text": display,
                "hit_routes": ["graph"],
                "source_priority": "auxiliary",
                "structured_answer": structured,
                "evidence_chunks": candidate.get("evidence_chunks", []),
            }
        else:
            # 其他通道：正常处理
            # ...
```

### Step 5：调整融合权重

graph 结构化结果的权重应该比 chunk 结果高，因为它们提供了独特价值：

```python
GRAPH_WEIGHT_PRESETS = {
    "default": {
        "graph": 0.10,          # 从 0.05 提升到 0.10
        "bm25": 0.32,
        "vector": 0.23,
        "qa": 0.15,
        "structured": 0.12,
        "section_summary": 0.08,
    },
    "relation_heavy": {
        "graph": 0.20,          # 关系型问题提高 graph 权重
        "bm25": 0.28,
        "vector": 0.20,
        "qa": 0.12,
        "structured": 0.12,
        "section_summary": 0.08,
    },
}
```

---

## 5. 预期效果

### 5.1 消融测试预期

| 题目 | 当前效果 | 预期效果 |
|---|---|---|
| Q01 哪些产品费率低于1% | graph 找到 chunk | graph 直接返回产品+费率列表 |
| Q02 哪些产品不需房产抵押 | graph 无贡献 | graph 返回"农耕贷: EXCLUDES 房产" |
| Q03 面向全省+3年经营 | graph 标记参与 | graph 返回全省产品列表+准入条件 |
| Q04 农耕贷vs加工贷反担保 | graph 无贡献 | graph 返回两产品的反担保对比表 |
| Q07 种植+养殖产品 | graph 找到烟台苹果 | graph 返回同时适用的产品列表 |
| Q10 无棣县养虾 | graph 标记参与 | graph 返回适用产品+水产养殖条件 |

### 5.2 独特价值

graph 提供了 BM25/vector 给不了的三种能力：

1. **结构化答案**：直接返回"产品→关系→值"的列表，不需要 LLM 从 chunk 中提取
2. **反向查询**：从条件/区域/行业反查产品，BM25 只能正向匹配
3. **多实体对比**：同时拉取多个产品的同类属性，BM25 只能逐个返回

---

## 6. 与现有代码的关系

| 现有模块 | 改动 |
|---|---|
| `graph_intent.py` | 新增 `infer_graph_query_template()` |
| `query.py` 的 `graph_query()` | 新增模板分发逻辑 |
| `graph_templates.py` | **新建**，5 种 Cypher 查询模板 |
| `build_evidence_groups()` | 支持结构化 graph 结果 |
| `graph_schema.py` | 不变 |
| `knowledge_graph_builder.py` | 不变 |
| `graph_writer.py` | 不变 |

图构建层（knowledge_graph_builder + graph_writer）已经完成，不需要改动。
只需要改查询层（intent → template → Cypher → 结构化输出）。

---

## 7. Cypher 模板之外的优化方向

Cypher 查询模板只解决了"怎么查"的问题，还有 6 个其他方面需要优化。

### 7.1 节点粒度优化 — 合并同义节点

**现状：** 同一个"反担保措施"是 5 个独立的 Requirement 节点（每个对应一条 knowledge_unit），而不是 1 个节点汇聚 5 条证据。

**影响：**
- REQUIRES 边有 5 条同义边，BFS 遍历时 node degree 虚高
- 查询"反担保措施"返回 5 条相同内容（不同 chunk 视角）
- Graph 查询排序时被权重稀释

**修复方案：** `knowledge_graph_builder.py` 增加同名合并逻辑

```python
def _merge_same_name_nodes(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """同名节点合并：同一 Entity 下相同 name_cn + node_type 的节点合并为一个。"""
    groups: dict[str, list[int]] = {}
    for i, node in enumerate(nodes):
        if node["node_type"] not in ("Entity", "File", "Chunk"):
            key = f"{node.get('source_anchor_id')}/{node['node_type']}/{node['name_cn']}"
            groups.setdefault(key, []).append(i)

    # 保留最高 confidence 的节点，合并其他节点的 evidence_chunk_key
    merged_nodes = []
    merged_edges = []
    for key, indices in groups.items():
        if len(indices) == 1:
            merged_nodes.append(nodes[indices[0]])
        else:
            best_idx = max(indices, key=lambda i: nodes[i].get("confidence", 0))
            best_node = dict(nodes[best_idx])
            # 合并所有 EVIDENCED_BY 的 chunk_key
            all_chunks = {nodes[i].get("source_chunk_key") for i in indices if nodes[i].get("source_chunk_key")}
            best_node["merged_chunk_keys"] = list(all_chunks)
            merged_nodes.append(best_node)
            # 重定向边：所有指向被合并节点的边改为指向 best_node
            for edge in edges:
                target = edge["to_node_key"]
                for i in indices:
                    if i != best_idx and target == nodes[i]["node_key"]:
                        edge["to_node_key"] = best_node["node_key"]
    return merged_nodes, merged_edges
```

### 7.2 减少 RELATED_TO 泛关系

**现状：** 768 条关系中，198 条（26%）是 RELATED_TO 泛关系。RELATED_TO 不带语义信息，BM25 也能找到"相关"的内容。

**根因：** `UNIT_ANCHOR_EDGE_MAP` 中多种 unit_type fallback 到 RELATED_TO，`RELATION_EDGE_MAP` 中 `has_unit` 和 `cooperates_with` 都映射为 RELATED_TO。

**修复方案：**

1. 细化 unit_type 映射，减少 RELATED_TO fallback：
```python
# 当前：所有未知 unit_type → RELATED_TO
# 改为：根据 unit 的 subject_text/predicate_text 推断更精确的边类型

def _infer_edge_from_unit(unit: dict) -> str:
    """从 unit 内容推断更精确的边类型。"""
    text = f"{unit.get('subject_text', '')} {unit.get('predicate_text', '')} {unit.get('object_text', '')}"
    if any(t in text for t in ["适用于", "覆盖", "范围"]):
        return "APPLIES_TO"
    if any(t in text for t in ["需要", "必须", "提供", "满足"]):
        return "REQUIRES"
    if any(t in text for t in ["禁止", "不得", "不允许"]):
        return "EXCLUDES"
    if any(t in text for t in ["负责", "承担", "职责"]):
        return "RESPONSIBLE_FOR"
    return "RELATED_TO"
```

2. 在 `knowledge_graph_builder.py` 的 `_resolve_unit_anchor_edge()` 中使用精确推断。

### 7.3 实体名称归一化 + SAME_AS 边

**现状：** Entity 节点名称来自 anchor，不同文件的同名实体没有合并。

示例：
- "无棣县农业产业化草莓产业集群担保服务方案" 
- "无棣县草莓产业集群担保服务方案"
- 应该合并为一个 Entity，但当前是两个独立节点

**修复方案：** 分两步走

第一步（简单规则）：在 `knowledge_graph_builder.py` 的节点去重阶段，用归一化名称合并：
```python
def _normalize_entity_name(name: str) -> str:
    """归一化产品名。"""
    # 去掉常见的后缀/前缀变体
    name = re.sub(r'担保服务方案|产业集群|产业链|融资担保|产品方案', '', name)
    name = re.sub(r'[\s\-\—]+', '', name)
    return name.strip()
```

第二步（LLM + 规则）：引入 MinHash/Jaro-Winkler 候选配对 + LLM 仲裁，建立 SAME_AS 边。参考 `graphrag_adapter.py` 和 `04_knowflow_analysis.md` 的 5 阶段去重方案。

### 7.4 收紧 graph intent 触发条件

**现状：** `_graph_default_for_profile()` 只要有 target_fields 就返回 True，导致大量字段查询走 graph。

消融测试中，"担保费率"这种纯字段查询 graph_hits=11，但这些结果和其他通道重叠，浪费了 Neo4j 查询开销。

**修复方案：**

```python
# 当前
def _graph_default_for_profile(profile, target_fields, graph_intent):
    if target_fields:
        return True
    return _graph_has_relation_intent(graph_intent)

# 改为：只在关系型意图时触发
GRAPH_RELATION_INTENT_TYPES = {
    "APPLIES_TO", "EXCLUDES", "REQUIRES", "CONSTRAINS",
    "RESPONSIBLE_FOR", "APPROVES", "DEPENDS_ON", "REFERENCES",
    "IN_REGION", "IN_INDUSTRY",
}

def _graph_default_for_profile(profile, target_fields, graph_intent):
    relations = set(graph_intent.get("relations", []))
    # 只有明确的强语义关系才触发
    if relations & GRAPH_RELATION_INTENT_TYPES:
        return True
    # 字段查询 + 泛关系不触发
    if target_fields and relations == {"HAS_FIELD", "EVIDENCED_BY", "HAS_ATTRIBUTE"}:
        return False
    return False
```

### 7.5 Evidence Group 中 graph 的独立展示

**现状：** graph 返回的结果被塞到和其他通道一样的 evidence_group 里，无法区分"这是 graph 给的关系证据"和"这是 BM25 给的原文证据"。

**修复方案：** 参考 DataGraphX 和 GraphRAG-Example 的做法：

1. graph 结果单独创建一个 evidence_group，类型标记为 `source_priority: "auxiliary"`
2. LLM prompt 中明确区分：
```
[关系证据] 农耕贷 REQUIRES 反担保: 配偶及子女连带保证 ← graph 提供
[原文证据] ... 反担保措施原文 chunk ... ← BM25/vector 提供
```
3. display_text 格式化为结构化描述而非 chunk 原文

### 7.6 动态融合权重

**现状：** 所有查询 graph 权重固定 0.05，不管是不是关系型问题。

**修复方案：** 根据 graph_intent 动态调整：

```python
def resolve_graph_weight(graph_intent: dict, field_codes: list[str]) -> float:
    """根据查询意图动态调整 graph 权重。"""
    relations = set(graph_intent.get("relations", []))
    
    # 强关系型：graph 主攻
    if relations & {"APPLIES_TO", "EXCLUDES", "RESPONSIBLE_FOR", "APPROVES"}:
        return 0.15
    # 条件/要求型：graph 辅助
    if relations & {"REQUIRES", "CONSTRAINS", "DEPENDS_ON"}:
        return 0.10
    # 对比型：graph 辅助
    if graph_intent.get("relation_query") and len(field_codes or []) > 0:
        return 0.08
    # 纯字段型：graph 不参与
    if field_codes and not relations & GRAPH_RELATION_INTENT_TYPES:
        return 0.0
    # 默认
    return 0.05
```

---

## 8. 所有优化项汇总

| # | 优化项 | 类型 | 模块 | 优先级 |
|---|--------|------|------|--------|
| 1 | 反向关系查询模板 | Cypher 模板 | graph_templates.py | P0 |
| 2 | 多实体对比查询模板 | Cypher 模板 | graph_templates.py | P0 |
| 3 | 范围反查查询模板 | Cypher 模板 | graph_templates.py | P0 |
| 4 | 全产品属性遍历模板 | Cypher 模板 | graph_templates.py | P0 |
| 5 | 收紧 graph intent 触发 | 意图路由 | graph_intent.py | P0 |
| 6 | 动态融合权重 | 融合排序 | query.py | P1 |
| 7 | 节点粒度合并同名节点 | 图构建 | knowledge_graph_builder.py | P1 |
| 8 | 减少 RELATED_TO 泛关系 | 图构建 | knowledge_graph_builder.py | P1 |
| 9 | Evidence Group graph 独立展示 | 证据构建 | query.py | P1 |
| 10 | 实体名称归一化 + SAME_AS | 图构建 | knowledge_graph_builder.py | P2 |
