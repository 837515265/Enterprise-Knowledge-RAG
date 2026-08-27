from __future__ import annotations

from typing import Any

from .graph_schema import allowed_node_types, graph_query_relations


ALLOWED_GRAPH_NODES = sorted(allowed_node_types("business_plan") | allowed_node_types("governance_rule"))

GRAPH_RELATION_ALIASES: dict[str, list[str]] = {
    "HAS_FIELD": ["字段", "要素", "内容", "额度", "费率", "期限", "条件", "用途", "对象", "是什么", "多少"],
    "IN_REGION": ["地区", "区域", "地域", "省内", "市内", "适用地区", "适用区域", "覆盖"],
    "IN_INDUSTRY": ["行业", "产业", "种植", "养殖", "禁入行业", "限制行业"],
    "RELATED_TO": ["机构", "银行", "合作", "经办", "部门", "公司"],
    "EVIDENCED_BY": ["证据", "依据", "出处", "原文", "引用", "来自哪里"],
    "HAS_CHAPTER": ["章节", "第几章", "哪章", "目录", "章"],
    "HAS_CLAUSE": ["条款", "第几条", "哪条", "规定", "条"],
    "ASSIGNS_RESPONSIBILITY": ["职责", "责任", "负责", "谁管", "责任部门", "归口部门", "主管部门"],
    "REQUIRES_APPROVAL": ["审批", "批准", "授权", "决策", "谁审批", "谁有权", "权限"],
    "REFERENCES_RULE": ["引用", "依据", "参照", "根据", "哪个制度", "哪些制度"],
    # 通用关系类型
    "APPLIES_TO": ["适用", "适用于", "覆盖", "面向", "服务于", "范围", "区域", "地区", "省内", "市内", "哪些产品", "哪些方案"],
    "EXCLUDES": ["禁入", "限制", "不支持", "禁止", "不允许", "不得", "负面清单"],
    "REQUIRES": ["需要", "必须", "提供", "提交", "满足", "符合", "准入", "材料", "反担保"],
    "CONSTRAINS": ["约束", "限制", "上限", "不超过", "不得超过", "最高", "最低"],
    "RESPONSIBLE_FOR": ["负责", "承担", "职责", "牵头", "主管部门", "归口部门", "谁管"],
    "APPROVES": ["审批", "批准", "授权", "决策", "谁审批", "谁有权"],
    "REFERENCES": ["依据", "根据", "参照", "引用", "按照", "遵循"],
    "DEPENDS_ON": ["依赖", "前置", "基于", "取决于"],
    "CONTAINS": ["包括", "包含", "涵盖", "组成", "分为"],
    "HAS_ATTRIBUTE": ["属性", "特征", "特点", "参数"],
}

RELATION_QUERY_TERMS = {"关系", "关联", "联系", "涉及", "相关", "链路", "图谱", "上下游"}

# 通用关系 → 需要的节点类型
_RELATION_NODE_MAP: dict[str, list[str]] = {
    "APPLIES_TO": ["Entity", "Location", "Industry", "Condition"],
    "EXCLUDES": ["Entity", "Industry", "Requirement"],
    "REQUIRES": ["Entity", "Requirement", "Condition"],
    "CONSTRAINS": ["Entity", "Condition", "Attribute"],
    "RESPONSIBLE_FOR": ["Entity", "Organization", "Requirement"],
    "APPROVES": ["Entity", "Organization", "Requirement"],
    "REFERENCES": ["Entity", "Document"],
    "DEPENDS_ON": ["Entity", "Condition"],
    "CONTAINS": ["Entity", "Section", "ProcessStep"],
    "HAS_ATTRIBUTE": ["Entity", "Attribute"],
    "IN_REGION": ["Entity", "Location"],
    "IN_INDUSTRY": ["Entity", "Industry"],
    "RELATED_TO": ["Entity", "Organization"],
    "HAS_FIELD": ["BusinessPlan", "BusinessField"],
}


def _add_nodes_for_relation(relation: str, add_node: callable) -> None:
    """为匹配到的关系添加对应的节点类型。"""
    for node_type in _RELATION_NODE_MAP.get(relation, []):
        add_node(node_type)


def infer_graph_intent(query: str, understanding: dict[str, Any] | None = None) -> dict[str, Any]:
    """Infer a constrained graph search scope from a question.

    DataGraphX uses allowed node/relationship lists to build only the subgraph
    relevant to the question. This project keeps that idea but maps it to the
    guarantee-plan graph schema.
    """
    understanding = understanding or {}
    text = query or ""
    entities = understanding.get("entities") if isinstance(understanding.get("entities"), dict) else {}
    target_fields = [str(item) for item in understanding.get("target_field_codes") or [] if item]
    profile = str(understanding.get("profile") or "")
    schema_profile = profile or "business_plan"
    governance_profile = schema_profile == "governance_rule"
    allowed_nodes = allowed_node_types(schema_profile)
    allowed_relations = graph_query_relations(schema_profile)

    nodes: list[str] = []
    relations: list[str] = []

    def add_node(node: str) -> None:
        if node in allowed_nodes and node not in nodes:
            nodes.append(node)

    def add_relation(relation: str) -> None:
        if relation in GRAPH_RELATION_ALIASES and relation in allowed_relations and relation not in relations:
            relations.append(relation)

    if target_fields and not governance_profile:
        add_node("BusinessPlan")
        add_node("BusinessField")
        add_node("Entity")
        add_relation("HAS_FIELD")
        add_relation("HAS_ATTRIBUTE")
        add_relation("EVIDENCED_BY")

    if governance_profile:
        governance_hits = {
            "HAS_CHAPTER": ["Chapter"],
            "HAS_CLAUSE": ["Chapter", "Clause"],
            "ASSIGNS_RESPONSIBILITY": ["Role", "Responsibility"],
            "REQUIRES_APPROVAL": ["Role", "Decision"],
            "REFERENCES_RULE": ["RuleDocument"],
        }
        for relation, relation_nodes in governance_hits.items():
            if any(alias in text for alias in GRAPH_RELATION_ALIASES[relation]):
                add_node("RuleDocument")
                for node in relation_nodes:
                    add_node(node)
                add_relation(relation)
                add_relation("EVIDENCED_BY")

    if entities.get("regions") or any(alias in text for alias in GRAPH_RELATION_ALIASES["IN_REGION"]):
        add_node("Region")
        add_relation("IN_REGION")
    if entities.get("industries") or any(alias in text for alias in GRAPH_RELATION_ALIASES["IN_INDUSTRY"]):
        add_node("Industry")
        add_relation("IN_INDUSTRY")
    if entities.get("organizations") or any(alias in text for alias in GRAPH_RELATION_ALIASES["RELATED_TO"]):
        add_node("Organization")
        add_relation("RELATED_TO")
    if any(alias in text for alias in GRAPH_RELATION_ALIASES["EVIDENCED_BY"]):
        add_node("Chunk")
        add_relation("EVIDENCED_BY")

    for relation, aliases in GRAPH_RELATION_ALIASES.items():
        if any(alias in text for alias in aliases):
            add_relation(relation)
            # 为通用关系添加对应的节点类型
            _add_nodes_for_relation(relation, add_node)

    relation_query = any(term in text for term in RELATION_QUERY_TERMS)
    if relation_query and not relations:
        if governance_profile:
            for relation in ["HAS_CHAPTER", "HAS_CLAUSE", "ASSIGNS_RESPONSIBILITY", "REQUIRES_APPROVAL", "REFERENCES_RULE"]:
                add_relation(relation)
            add_node("RuleDocument")
        else:
            for relation in ["HAS_FIELD", "IN_REGION", "IN_INDUSTRY", "RELATED_TO", "APPLIES_TO", "REQUIRES", "HAS_ATTRIBUTE"]:
                add_relation(relation)
            add_node("BusinessPlan")
            add_node("Entity")

    if not nodes and relations:
        if governance_profile:
            add_node("RuleDocument")
        else:
            add_node("BusinessPlan")
            add_node("Entity")
    if "EVIDENCED_BY" in relations and "Chunk" not in nodes:
        add_node("Chunk")

    return {
        "nodes": nodes,
        "relations": relations,
        "relation_query": relation_query,
        "source": "datagraphx_allowed_schema",
    }
