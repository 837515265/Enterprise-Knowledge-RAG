"""通用知识图构建器。

从 MySQL 中已有的 anchors、knowledge_units、relations 数据，
映射为通用图节点和边，供 Neo4j 存储使用。

替代原有的 build_business_graph()，支持所有 profile。
"""
from __future__ import annotations

from typing import Any

from .graph_schema import filter_graph_records


# ──────────────────────────────────────────────────────────────
# anchor_type → 通用节点类型映射
# ──────────────────────────────────────────────────────────────
ANCHOR_NODE_MAP: dict[str, tuple[str, str]] = {
    # business_plan
    "plan":           ("Entity",      "product"),
    "product":        ("Entity",      "product"),
    "service_object": ("Concept",     "service_object"),
    # governance_rule
    "institution":    ("Document",    "rule_document"),
    "rule_document":  ("Document",    "rule_document"),
    "chapter":        ("Section",     "clause"),
    "department":     ("Organization", "department"),
    # project_doc
    "system":         ("Entity",      "system"),
    "module":         ("Entity",      "module"),
    "api":            ("Entity",      "api"),
    "database_table": ("Entity",      "database_table"),
    "config_item":    ("Entity",      "config_item"),
    # 通用
    "organization":   ("Organization", "organization"),
    "region":         ("Location",    "region"),
    "industry":       ("Industry",    "industry"),
    "person":         ("PersonRole",  "person"),
    "role":           ("PersonRole",  "role"),
}

# ──────────────────────────────────────────────────────────────
# unit_type → 通用节点类型映射
# ──────────────────────────────────────────────────────────────
UNIT_NODE_MAP: dict[str, tuple[str, str]] = {
    # 条件类
    "scope":              ("Condition",   "scope"),
    "condition":          ("Condition",   "condition"),
    "access_condition":   ("Condition",   "admission"),
    "admission":          ("Condition",   "admission"),
    "exclusion":          ("Condition",   "exclusion"),
    # 要求类
    "counter_guarantee":  ("Requirement", "counter_guarantee"),
    "material":           ("Requirement", "material"),
    "risk_measure":       ("Requirement", "risk_measure"),
    "obligation":         ("Requirement", "obligation"),
    "approval":           ("Requirement", "approval"),
    "prohibition":        ("Requirement", "prohibition"),
    "rule":               ("Requirement", "rule"),
    "responsibility":     ("Requirement", "responsibility"),
    # 属性类
    "credit_limit":       ("Attribute",   "credit_limit"),
    "guarantee_rate":     ("Attribute",   "guarantee_rate"),
    "credit_term":        ("Attribute",   "credit_term"),
    "credit_purpose":     ("Attribute",   "credit_purpose"),
    "risk_share_ratio":   ("Attribute",   "risk_share_ratio"),
    "service_object":     ("Attribute",   "service_object"),
    "applicable_scope":   ("Attribute",   "applicable_scope"),
    # 流程类
    "business_process":   ("ProcessStep", "application_step"),
    "approval_process":   ("ProcessStep", "approval_step"),
    "process":            ("ProcessStep", "process"),
    "process_step":       ("ProcessStep", "process_step"),
    # 度量类
    "formula":            ("Metric",      "formula"),
    "amount":             ("Metric",      "amount"),
    "rate":               ("Metric",      "rate"),
    "ratio":              ("Metric",      "ratio"),
}

# ──────────────────────────────────────────────────────────────
# relation_type → 通用边类型映射
# ──────────────────────────────────────────────────────────────
RELATION_EDGE_MAP: dict[str, str] = {
    "applies_to":        "APPLIES_TO",
    "targets_customer":  "APPLIES_TO",
    "excludes_industry": "EXCLUDES",
    "prohibits":         "EXCLUDES",
    "requires":          "REQUIRES",
    "constrained_by":    "CONSTRAINS",
    "depends_on":        "DEPENDS_ON",
    "occurs_before":     "OCCURS_BEFORE",
    "references":        "REFERENCES",
    "responsible_for":   "RESPONSIBLE_FOR",
    "approves":          "APPROVES",
    "contains":          "CONTAINS",
    "belongs_to":        "PART_OF",
    "alias_of":          "SAME_AS",
    "cooperates_with":   "RELATED_TO",
    "has_unit":          "RELATED_TO",
    "related_to":        "RELATED_TO",
}

# unit_type → anchor 之间的默认边类型
UNIT_ANCHOR_EDGE_MAP: dict[str, str] = {
    # 属性类 unit → HAS_ATTRIBUTE
    "credit_limit":      "HAS_ATTRIBUTE",
    "guarantee_rate":    "HAS_ATTRIBUTE",
    "credit_term":       "HAS_ATTRIBUTE",
    "credit_purpose":    "HAS_ATTRIBUTE",
    "risk_share_ratio":  "HAS_ATTRIBUTE",
    "service_object":    "HAS_ATTRIBUTE",
    "applicable_scope":  "HAS_ATTRIBUTE",
    "formula":           "HAS_ATTRIBUTE",
    "amount":            "HAS_ATTRIBUTE",
    "rate":              "HAS_ATTRIBUTE",
    "ratio":             "HAS_ATTRIBUTE",
    # 条件/要求类 unit → REQUIRES
    "condition":         "REQUIRES",
    "access_condition":  "REQUIRES",
    "admission":         "REQUIRES",
    "exclusion":         "REQUIRES",
    "counter_guarantee": "REQUIRES",
    "material":          "REQUIRES",
    "risk_measure":      "REQUIRES",
    "obligation":        "REQUIRES",
    "approval":          "REQUIRES",
    "prohibition":       "EXCLUDES",
    "rule":              "REQUIRES",
    "responsibility":    "REQUIRES",
    "scope":             "APPLIES_TO",
    # 流程类 unit → CONTAINS
    "business_process":  "CONTAINS",
    "approval_process":  "CONTAINS",
    "process":           "CONTAINS",
    "process_step":      "CONTAINS",
}


def _resolve_anchor_node(anchor: dict[str, Any]) -> tuple[str, str] | None:
    """将 anchor_type 映射为 (通用节点类型, domain_type)。"""
    anchor_type = str(anchor.get("anchor_type") or "").lower()
    return ANCHOR_NODE_MAP.get(anchor_type)


def _resolve_unit_node(unit: dict[str, Any]) -> tuple[str, str] | None:
    """将 unit_type 映射为 (通用节点类型, domain_type)。"""
    unit_type = str(unit.get("unit_type") or "").lower()
    return UNIT_NODE_MAP.get(unit_type, ("Requirement", unit_type))


def _resolve_relation_edge(relation_type: str) -> str:
    """将 relation_type 映射为通用边类型。"""
    return RELATION_EDGE_MAP.get(relation_type, "RELATED_TO")


def _resolve_unit_anchor_edge(unit_type: str) -> str:
    """将 unit_type 映射为 anchor → unit 之间的默认边类型。"""
    return UNIT_ANCHOR_EDGE_MAP.get(unit_type, "RELATED_TO")


def build_knowledge_graph(
    *,
    profile: str,
    anchors: list[dict[str, Any]],
    knowledge_units: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    fields: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """从知识抽取结果构建通用图节点和边。

    输入来自 MySQL 的 kb_anchor_registry、kb_knowledge_unit、kb_relation 表。
    输出格式与 build_business_graph() 一致，可直接存入 file_graph_nodes/file_graph_edges。
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    # chunk_map: chunk_key 或 id -> chunk，兼容两种数据来源
    chunk_map: dict[str, Any] = {}
    for c in chunks:
        chunk_map[str(c.get("chunk_key") or c.get("id"))] = c
        chunk_map[str(c.get("id"))] = c
    anchor_by_id: dict[str, dict[str, Any]] = {}

    # ── 1. File 节点 ──────────────────────────────────────────
    nodes.append({
        "node_key": "file",
        "node_type": "File",
        "name_cn": "文件",
        "value_text": None,
        "source_chunk_key": None,
        "properties": {},
    })

    # ── 2. Anchor → 实体节点 ──────────────────────────────────
    for anchor in anchors:
        anchor_id = anchor.get("anchor_id")
        resolved = _resolve_anchor_node(anchor)
        if not resolved:
            # 无法映射的 anchor 降级为 Concept
            node_type, domain_type = "Concept", str(anchor.get("anchor_type") or "other")
        else:
            node_type, domain_type = resolved

        normalized = str(anchor.get("normalized_name") or anchor.get("anchor_name") or "").strip()
        if not normalized:
            continue

        node_key = f"{node_type}:{normalized}"
        anchor_by_id[anchor_id] = {
            "node_key": node_key,
            "node_type": node_type,
            "name_cn": anchor.get("anchor_name") or normalized,
        }

        nodes.append({
            "node_key": node_key,
            "node_type": node_type,
            "name_cn": anchor.get("anchor_name") or normalized,
            "value_text": None,
            "domain_type": domain_type,
            "profile": profile,
            "confidence": anchor.get("confidence"),
            "source_chunk_key": anchor.get("source_chunk_key"),
            "source_anchor_id": anchor_id,
            "source_unit_id": None,
            "properties": {
                "graph_schema_version": "v2",
                "graph_role": "anchor",
                "anchor_id": anchor_id,
                "anchor_type": anchor.get("anchor_type"),
            },
        })

        # File → Entity (PARSED_AS)
        edges.append({
            "edge_type": "PARSED_AS",
            "from_node_key": "file",
            "to_node_key": node_key,
            "source_chunk_key": anchor.get("source_chunk_key"),
            "evidence_quote": None,
            "confidence": anchor.get("confidence"),
            "properties": {},
        })

        # Anchor → EVIDENCED_BY → Chunk
        chunk_key = anchor.get("source_chunk_key") or anchor.get("source_chunk_id")
        if chunk_key and str(chunk_key) in chunk_map:
            chunk_node_key = f"chunk:{chunk_key}"
            _ensure_chunk_node(nodes, chunk_map[str(chunk_key)], chunk_node_key)
            edges.append({
                "edge_type": "EVIDENCED_BY",
                "from_node_key": node_key,
                "to_node_key": chunk_node_key,
                "source_chunk_key": chunk_key,
                "evidence_quote": anchor.get("evidence_quote"),
                "confidence": anchor.get("confidence"),
                "properties": {},
            })

    # ── 3. KnowledgeUnit → 知识节点 ──────────────────────────
    unit_node_map: dict[str, str] = {}  # unit_id → node_key

    for unit in knowledge_units:
        unit_id = unit.get("unit_id")
        unit_type = str(unit.get("unit_type") or "").lower()
        resolved = _resolve_unit_node(unit)
        node_type, domain_type = resolved

        # 图节点表达“关系事实”，避免把 ES 的整段 Chunk 再复制一遍。
        predicate = str(unit.get("predicate_text") or "").strip()
        object_text = str(unit.get("object_text") or "").strip()
        name = "：".join(part for part in [predicate, object_text[:80]] if part)
        if not name:
            name = str(unit.get("subject_text") or "").strip()
        if not name:
            name = unit_type

        # 用 unit_id 做 node_key 保证唯一性
        node_key = f"{node_type}:{unit_id}"
        unit_node_map[unit_id] = node_key

        nodes.append({
            "node_key": node_key,
            "node_type": node_type,
            "name_cn": name,
            "value_text": unit.get("object_text"),
            "domain_type": domain_type,
            "profile": profile,
            "confidence": unit.get("confidence"),
            "source_chunk_key": unit.get("primary_chunk_key") or unit.get("primary_chunk_id"),
            "source_anchor_id": unit.get("anchor_id"),
            "source_unit_id": unit_id,
            "properties": {
                "unit_type": unit_type,
                "unit_subtype": unit.get("unit_subtype"),
                "subject_text": unit.get("subject_text"),
                "predicate_text": unit.get("predicate_text"),
                "object_text": unit.get("object_text"),
                "graph_schema_version": "v2",
                "graph_role": "relation_fact",
                "unit_id": unit_id,
                "anchor_id": unit.get("anchor_id"),
            },
        })

        # Unit → EVIDENCED_BY → Chunk
        chunk_key = unit.get("primary_chunk_key") or unit.get("primary_chunk_id")
        if chunk_key and str(chunk_key) in chunk_map:
            chunk_node_key = f"chunk:{chunk_key}"
            _ensure_chunk_node(nodes, chunk_map[str(chunk_key)], chunk_node_key)
            edges.append({
                "edge_type": "EVIDENCED_BY",
                "from_node_key": node_key,
                "to_node_key": chunk_node_key,
                "source_chunk_key": chunk_key,
                "evidence_quote": unit.get("evidence_quote"),
                "confidence": unit.get("confidence"),
                "properties": {
                    "graph_schema_version": "v2",
                    "unit_id": unit_id,
                    "predicate_text": unit.get("predicate_text"),
                },
            })

        # Anchor → Unit 边 (如果 unit 关联了 anchor)
        anchor_id = unit.get("anchor_id")
        if anchor_id and anchor_id in anchor_by_id:
            edge_type = _resolve_unit_anchor_edge(unit_type)
            edges.append({
                "edge_type": edge_type,
                "from_node_key": anchor_by_id[anchor_id]["node_key"],
                "to_node_key": node_key,
                "source_chunk_key": chunk_key,
                "evidence_quote": unit.get("evidence_quote"),
                "confidence": unit.get("confidence"),
                "properties": {
                    "graph_schema_version": "v2",
                    "unit_id": unit_id,
                    "anchor_id": anchor_id,
                    "unit_type": unit_type,
                    "predicate_text": unit.get("predicate_text"),
                },
            })

    # ── 4. Relation → 文件私有 Assertion ─────────────────────
    #
    # 不能把跨文档共享 Anchor 之间的事实直接 MERGE 成一条共享边：
    # 那样无法区分每个文件的证据，也无法在文件删除/重解析时安全撤销。
    # Assertion 作为文件私有的事实载体，保留 relation_id、置信度和 Chunk
    # 证据；共享实体只负责稳定身份。
    node_name_by_key = {
        str(node.get("node_key")): str(node.get("name_cn") or node.get("value_text") or node.get("node_key") or "")
        for node in nodes
        if node.get("node_key")
    }
    for rel in relations:
        from_id = rel.get("from_id")
        to_id = rel.get("to_id")
        from_type = str(rel.get("from_type") or "").lower()
        to_type = str(rel.get("to_type") or "").lower()
        relation_type = str(rel.get("relation_type") or "related_to").lower()

        # 解析 from_node_key
        from_node_key = _resolve_entity_key(from_type, from_id, anchor_by_id, unit_node_map)
        to_node_key = _resolve_entity_key(to_type, to_id, anchor_by_id, unit_node_map)

        if not from_node_key or not to_node_key:
            continue

        edge_type = _resolve_relation_edge(relation_type)
        relation_id = str(rel.get("relation_id") or "").strip()
        if not relation_id:
            continue
        assertion_key = f"Assertion:{relation_id}"
        source_name = node_name_by_key.get(from_node_key, from_node_key)
        target_name = node_name_by_key.get(to_node_key, to_node_key)
        relation_metadata = rel.get("metadata") if isinstance(rel.get("metadata"), dict) else {}
        confidence_label = str(relation_metadata.get("confidence_label") or "").strip().upper()
        if confidence_label not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
            confidence_label = "INFERRED" if relation_metadata.get("rule_source") else "EXTRACTED"

        nodes.append({
            "node_key": assertion_key,
            "node_type": "Assertion",
            "name_cn": f"{source_name} --{edge_type}--> {target_name}",
            "value_text": rel.get("evidence_quote"),
            "domain_type": relation_type,
            "profile": profile,
            "confidence": rel.get("confidence"),
            "source_chunk_key": rel.get("source_chunk_key"),
            "source_anchor_id": None,
            "source_unit_id": None,
            "properties": {
                "graph_schema_version": "v2.1",
                "graph_role": "assertion",
                "relation_id": relation_id,
                "relation_type": relation_type,
                "predicate": edge_type,
                "subject_name": source_name,
                "object_name": target_name,
                "subject_node_key": from_node_key,
                "object_node_key": to_node_key,
                "confidence_label": confidence_label,
                "extraction_source": relation_metadata.get("rule_source") or "llm",
            },
        })

        edges.append({
            "edge_type": "ASSERTS",
            "from_node_key": from_node_key,
            "to_node_key": assertion_key,
            "source_chunk_key": rel.get("source_chunk_key"),
            "evidence_quote": rel.get("evidence_quote"),
            "confidence": rel.get("confidence"),
            "properties": {
                "graph_schema_version": "v2.1",
                "relation_id": relation_id,
                "confidence_label": confidence_label,
            },
        })
        edges.append({
            "edge_type": edge_type,
            "from_node_key": assertion_key,
            "to_node_key": to_node_key,
            "source_chunk_key": rel.get("source_chunk_key"),
            "evidence_quote": rel.get("evidence_quote"),
            "confidence": rel.get("confidence"),
            "properties": {
                "graph_schema_version": "v2.1",
                "relation_id": relation_id,
                "relation_type": relation_type,
                "confidence_label": confidence_label,
            },
        })

        # Relation 的 EVIDENCED_BY
        chunk_key = rel.get("source_chunk_key") or rel.get("source_chunk_id")
        if chunk_key and str(chunk_key) in chunk_map:
            chunk_node_key = f"chunk:{chunk_key}"
            _ensure_chunk_node(nodes, chunk_map[str(chunk_key)], chunk_node_key)
            edges.append({
                "edge_type": "EVIDENCED_BY",
                "from_node_key": assertion_key,
                "to_node_key": chunk_node_key,
                "source_chunk_key": chunk_key,
                "evidence_quote": rel.get("evidence_quote"),
                "confidence": rel.get("confidence"),
                "properties": {
                    "graph_schema_version": "v2.1",
                    "relation_id": relation_id,
                    "confidence_label": confidence_label,
                },
            })

    # ── 5. Fields 补充属性值 ──────────────────────────────────
    if fields:
        _enrich_from_fields(nodes, edges, fields, profile)

    # ── 6. 去重 + schema 过滤 ─────────────────────────────────
    filtered_nodes, filtered_edges, warnings = filter_graph_records(
        profile, _dedupe_nodes(nodes), _dedupe_edges(edges)
    )
    return filtered_nodes, filtered_edges


def _resolve_entity_key(
    entity_type: str,
    entity_id: str,
    anchor_by_id: dict[str, dict[str, Any]],
    unit_node_map: dict[str, str],
) -> str | None:
    """将 (from_type, from_id) 解析为 node_key。"""
    if entity_type == "anchor":
        anchor_info = anchor_by_id.get(entity_id)
        return anchor_info["node_key"] if anchor_info else None
    if entity_type == "unit":
        return unit_node_map.get(entity_id)
    if entity_type == "section":
        return f"section:{entity_id}"
    return None


def _ensure_chunk_node(
    nodes: list[dict[str, Any]],
    chunk: dict[str, Any],
    chunk_node_key: str,
) -> None:
    """确保 Chunk 节点存在于节点列表中（幂等）。"""
    for node in nodes:
        if node["node_key"] == chunk_node_key:
            return
    nodes.append({
        "node_key": chunk_node_key,
        "node_type": "Chunk",
        "name_cn": chunk.get("title") or "",
        "value_text": (chunk.get("content") or "")[:500],
        "source_chunk_key": str(chunk.get("chunk_key") or chunk.get("id")),
        "properties": {
            "chunk_id": chunk.get("id"),
            "section_type": chunk.get("section_type"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
        },
    })


def _enrich_from_fields(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    profile: str,
) -> None:
    """从 fields 补充 Attribute 节点（如果 knowledge_unit 没覆盖到的字段）。"""
    existing_domain_types = {
        n.get("domain_type") for n in nodes if n.get("node_type") == "Attribute"
    }

    for field in fields:
        field_code = str(field.get("field_code") or "").lower()
        value_text = field.get("value_text")
        if not field_code or not value_text:
            continue

        # 映射 field_code → domain_type
        domain_type = _field_code_to_domain(field_code)
        if not domain_type or domain_type in existing_domain_types:
            continue

        node_key = f"Attribute:field:{field_code}"
        nodes.append({
            "node_key": node_key,
            "node_type": "Attribute",
            "name_cn": field.get("field_name_cn") or field_code,
            "value_text": value_text,
            "domain_type": domain_type,
            "profile": profile,
            "confidence": field.get("confidence"),
            "source_chunk_key": field.get("source_chunk_key") or field.get("source_chunk_id"),
            "source_anchor_id": None,
            "source_unit_id": None,
            "properties": {"field_code": field_code},
        })
        existing_domain_types.add(domain_type)

        # 找到主实体节点（第一个 Entity 类型），建立 HAS_ATTRIBUTE 边
        entity_key = next(
            (n["node_key"] for n in nodes if n.get("node_type") == "Entity"),
            None,
        )
        if entity_key:
            edges.append({
                "edge_type": "HAS_ATTRIBUTE",
                "from_node_key": entity_key,
                "to_node_key": node_key,
                "source_chunk_key": field.get("source_chunk_key") or field.get("source_chunk_id"),
                "evidence_quote": None,
                "confidence": field.get("confidence"),
                "properties": {"field_code": field_code},
            })


def _field_code_to_domain(field_code: str) -> str | None:
    """field_code → Attribute 的 domain_type。"""
    mapping = {
        "credit_limit":      "credit_limit",
        "guarantee_rate":    "guarantee_rate",
        "credit_term":       "credit_term",
        "credit_purpose":    "credit_purpose",
        "counter_guarantee": "counter_guarantee",
        "risk_mitigation":   "risk_measure",
        "risk_share_ratio":  "risk_share_ratio",
        "access_condition":  "admission",
        "service_object":    "service_object",
        "applicable_scope":  "applicable_scope",
        "business_process":  "application_step",
        "document_no":       "document_no",
        "plan_name":         "plan_name",
        "industry":          "industry",
        "region":            "region",
    }
    return mapping.get(field_code)


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 node_key 去重，保留最高 confidence。"""
    best: dict[str, dict[str, Any]] = {}
    for node in nodes:
        key = node["node_key"]
        existing = best.get(key)
        if not existing:
            best[key] = node
        else:
            new_conf = float(node.get("confidence") or 0)
            old_conf = float(existing.get("confidence") or 0)
            if new_conf > old_conf:
                best[key] = node
    return list(best.values())


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (edge_type, from, to) 去重，保留最高 confidence。"""
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (edge["edge_type"], edge["from_node_key"], edge["to_node_key"])
        existing = best.get(key)
        if not existing:
            best[key] = edge
        else:
            new_conf = float(edge.get("confidence") or 0)
            old_conf = float(existing.get("confidence") or 0)
            if new_conf > old_conf:
                best[key] = edge
    return list(best.values())
