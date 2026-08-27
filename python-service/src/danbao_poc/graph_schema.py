from __future__ import annotations

from typing import Any

from danbao_poc.profiles.registry import normalize_profile


UNIVERSAL_NODE_TYPES = {
    "File", "Document", "Section", "Chunk",
    "Entity", "Concept", "Attribute", "Value", "Assertion", "GraphCommunity",
    "Requirement", "Condition", "ProcessStep",
    "Organization", "PersonRole", "Location",
    "Industry", "Time", "Metric",
}

ALLOWED_NODE_TYPES_BY_PROFILE: dict[str, set[str]] = {
    "business_plan": {"File", "BusinessPlan", "BusinessField", "Region", "Industry", "Organization", "Chunk"} | UNIVERSAL_NODE_TYPES,
    "governance_rule": {"File", "RuleDocument", "Chapter", "Clause", "Role", "Responsibility", "Decision", "Chunk"} | UNIVERSAL_NODE_TYPES,
    "project_doc": {"File", "System", "Module", "API", "DatabaseTable", "ConfigItem", "Chunk"} | UNIVERSAL_NODE_TYPES,
    "general_document": {"File", "Document", "Section", "Topic", "Chunk"} | UNIVERSAL_NODE_TYPES,
    "contract_agreement": {"File", "Contract", "Party", "Clause", "Amount", "Date", "Chunk"} | UNIVERSAL_NODE_TYPES,
    "structured_data": {"File", "Table", "Column", "Record", "Chunk"} | UNIVERSAL_NODE_TYPES,
}

ALLOWED_RELATION_TYPES_BY_PROFILE: dict[str, set[str]] = {
    "business_plan": {
        "has_unit",
        "applies_to",
        "targets_customer",
        "excludes_industry",
        "cooperates_with",
        "requires",
        "constrained_by",
        "depends_on",
        "occurs_before",
        "references",
        "contains",
        "alias_of",
        "related_to",
    },
    "governance_rule": {
        "has_unit",
        "belongs_to",
        "contains",
        "responsible_for",
        "approves",
        "prohibits",
        "requires",
        "constrained_by",
        "depends_on",
        "occurs_before",
        "references",
        "alias_of",
        "related_to",
    },
    "project_doc": {
        "has_unit",
        "belongs_to",
        "contains",
        "requires",
        "depends_on",
        "occurs_before",
        "references",
        "alias_of",
        "related_to",
    },
    "general_document": {"has_unit", "applies_to", "belongs_to", "contains", "depends_on", "occurs_before", "references", "alias_of", "related_to"},
    "contract_agreement": {"has_unit", "belongs_to", "requires", "constrained_by", "depends_on", "occurs_before", "references", "contains", "related_to"},
    "structured_data": {"has_unit", "contains", "belongs_to", "depends_on", "occurs_before", "references", "related_to"},
}

UNIVERSAL_EDGE_TYPES = {
    "PARSED_AS", "CONTAINS", "MENTIONS",
    "HAS_ATTRIBUTE", "HAS_VALUE",
    "APPLIES_TO", "EXCLUDES", "REQUIRES", "CONSTRAINS",
    "DEPENDS_ON", "REFERENCES",
    "RESPONSIBLE_FOR", "APPROVES",
    "PART_OF", "OCCURS_BEFORE",
    "SAME_AS", "RELATED_TO", "ASSERTS", "MEMBER_OF_COMMUNITY", "EVIDENCED_BY",
}

ALLOWED_GRAPH_EDGE_TYPES_BY_PROFILE: dict[str, set[str]] = {
    "business_plan": {"PARSED_AS", "HAS_FIELD", "IN_REGION", "IN_INDUSTRY", "RELATED_TO", "EVIDENCED_BY"} | UNIVERSAL_EDGE_TYPES,
    "governance_rule": {"PARSED_AS", "HAS_CHAPTER", "HAS_CLAUSE", "ASSIGNS_RESPONSIBILITY", "REQUIRES_APPROVAL", "REFERENCES_RULE", "EVIDENCED_BY"} | UNIVERSAL_EDGE_TYPES,
    "project_doc": {"PARSED_AS", "HAS_MODULE", "HAS_API", "HAS_TABLE", "HAS_CONFIG", "DEPENDS_ON", "REFERENCES", "EVIDENCED_BY"} | UNIVERSAL_EDGE_TYPES,
    "general_document": {"PARSED_AS", "HAS_SECTION", "RELATED_TO", "REFERENCES", "EVIDENCED_BY"} | UNIVERSAL_EDGE_TYPES,
    "contract_agreement": {"PARSED_AS", "HAS_PARTY", "HAS_CLAUSE", "CONSTRAINED_BY", "EVIDENCED_BY"} | UNIVERSAL_EDGE_TYPES,
    "structured_data": {"PARSED_AS", "HAS_COLUMN", "HAS_RECORD", "EVIDENCED_BY"} | UNIVERSAL_EDGE_TYPES,
}

RELATION_WEIGHT_BY_TYPE: dict[str, float] = {
    "PARSED_AS": 0.50,
    "HAS_FIELD": 1.00,
    "EVIDENCED_BY": 0.92,
    "IN_REGION": 0.78,
    "IN_INDUSTRY": 0.74,
    "RELATED_TO": 0.70,
    "HAS_CHAPTER": 0.76,
    "HAS_CLAUSE": 0.82,
    "ASSIGNS_RESPONSIBILITY": 0.86,
    "REQUIRES_APPROVAL": 0.84,
    "REFERENCES_RULE": 0.80,
    # 通用关系类型
    "CONTAINS": 0.80,
    "MENTIONS": 0.60,
    "HAS_ATTRIBUTE": 0.90,
    "HAS_VALUE": 0.85,
    "APPLIES_TO": 0.85,
    "EXCLUDES": 0.82,
    "REQUIRES": 0.84,
    "CONSTRAINS": 0.80,
    "DEPENDS_ON": 0.78,
    "REFERENCES": 0.76,
    "RESPONSIBLE_FOR": 0.86,
    "APPROVES": 0.84,
    "PART_OF": 0.72,
    "OCCURS_BEFORE": 0.74,
    "SAME_AS": 0.88,
    "ASSERTS": 0.90,
}

PROFILE_GRAPH_QUERY_INTENTS: dict[str, set[str]] = {
    "business_plan": {"HAS_FIELD", "IN_REGION", "IN_INDUSTRY", "RELATED_TO", "EVIDENCED_BY",
                       "APPLIES_TO", "EXCLUDES", "REQUIRES", "HAS_ATTRIBUTE", "RESPONSIBLE_FOR", "CONTAINS"},
    "governance_rule": {"HAS_CHAPTER", "HAS_CLAUSE", "ASSIGNS_RESPONSIBILITY", "REQUIRES_APPROVAL", "REFERENCES_RULE", "EVIDENCED_BY",
                         "RESPONSIBLE_FOR", "APPROVES", "REQUIRES", "REFERENCES", "CONTAINS", "EXCLUDES"},
    "project_doc": {"HAS_MODULE", "HAS_API", "HAS_TABLE", "HAS_CONFIG", "DEPENDS_ON", "REFERENCES", "EVIDENCED_BY",
                     "CONTAINS", "REQUIRES", "DEPENDS_ON"},
    "general_document": {"HAS_SECTION", "RELATED_TO", "REFERENCES", "EVIDENCED_BY",
                          "APPLIES_TO", "CONTAINS", "REQUIRES"},
    "contract_agreement": {"HAS_PARTY", "HAS_CLAUSE", "CONSTRAINED_BY", "EVIDENCED_BY",
                            "REQUIRES", "CONSTRAINS", "REFERENCES", "CONTAINS"},
    "structured_data": {"HAS_COLUMN", "HAS_RECORD", "EVIDENCED_BY",
                         "CONTAINS", "REFERENCES"},
}


def normalized_profile(profile: str | None) -> str:
    return normalize_profile(profile) or profile or "general_document"


def global_knowledge_relation_types() -> set[str]:
    result: set[str] = set()
    for values in ALLOWED_RELATION_TYPES_BY_PROFILE.values():
        result.update(values)
    return result


def allowed_node_types(profile: str | None) -> set[str]:
    return set(ALLOWED_NODE_TYPES_BY_PROFILE.get(normalized_profile(profile), ALLOWED_NODE_TYPES_BY_PROFILE["general_document"]))


def allowed_knowledge_relation_types(profile: str | None) -> set[str]:
    if not profile:
        return global_knowledge_relation_types()
    return set(ALLOWED_RELATION_TYPES_BY_PROFILE.get(normalized_profile(profile), ALLOWED_RELATION_TYPES_BY_PROFILE["general_document"]))


def allowed_graph_edge_types(profile: str | None) -> set[str]:
    return set(ALLOWED_GRAPH_EDGE_TYPES_BY_PROFILE.get(normalized_profile(profile), ALLOWED_GRAPH_EDGE_TYPES_BY_PROFILE["general_document"]))


def graph_query_relations(profile: str | None) -> set[str]:
    return set(PROFILE_GRAPH_QUERY_INTENTS.get(normalized_profile(profile), PROFILE_GRAPH_QUERY_INTENTS["general_document"]))


def relation_type_allowed(profile: str | None, relation_type: str) -> bool:
    return relation_type in allowed_knowledge_relation_types(profile)


def filter_graph_records(
    profile: str | None,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    node_types = allowed_node_types(profile)
    edge_types = allowed_graph_edge_types(profile)
    kept_node_keys = {
        str(node.get("node_key"))
        for node in nodes
        if str(node.get("node_type") or "") in node_types
    }
    filtered_nodes = [node for node in nodes if str(node.get("node_key")) in kept_node_keys]
    warnings: list[str] = []
    for node in nodes:
        if str(node.get("node_key")) not in kept_node_keys:
            warnings.append(f"graph_node_schema_rejected:{node.get('node_type')}:{node.get('node_key')}")

    filtered_edges: list[dict[str, Any]] = []
    for edge in edges:
        edge_type = str(edge.get("edge_type") or "")
        if edge_type not in edge_types:
            warnings.append(f"graph_edge_schema_rejected:{edge_type}")
            continue
        if str(edge.get("from_node_key")) not in kept_node_keys or str(edge.get("to_node_key")) not in kept_node_keys:
            warnings.append(f"graph_edge_endpoint_rejected:{edge_type}")
            continue
        filtered_edges.append(edge)
    return filtered_nodes, filtered_edges, warnings
