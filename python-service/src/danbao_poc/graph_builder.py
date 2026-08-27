from __future__ import annotations

import re
from typing import Any

from danbao_poc.graph_schema import filter_graph_records


INVALID_REGION_TOKENS = {"市场", "证券", "期货", "房地产", "资金", "贷款", "担保", "业务", "方案", "产业", "行业", "重点", "特色", "公司", "银行", "客户", "主体", "任何形式"}


def _safe_region(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 16:
        return ""
    if any(token in text for token in INVALID_REGION_TOKENS):
        return ""
    if not re.fullmatch(r"[\u4e00-\u9fa5]{2,16}(?:省|市|县|区|镇|乡|村|街道)", text):
        return ""
    return text


def build_business_graph(extraction: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan = extraction.get("plan") or {}
    fields = extraction.get("fields") or []
    region_evidence = "\n".join(
        str(value or "")
        for value in [
            plan.get("plan_name"),
            plan.get("product_name"),
            *[
                field.get("value_text")
                for field in fields
                if field.get("field_code") in {"region", "applicable_scope"}
            ],
        ]
    )
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    nodes.append(
        {
            "node_key": "file",
            "node_type": "File",
            "name_cn": "文件",
            "value_text": None,
            "properties": {},
        }
    )
    nodes.append(
        {
            "node_key": "plan",
            "node_type": "BusinessPlan",
            "name_cn": plan.get("plan_name") or "担保方案",
            "value_text": plan.get("document_no"),
            "properties": {"document_no": plan.get("document_no")},
        }
    )
    edges.append({"edge_type": "PARSED_AS", "from_node_key": "file", "to_node_key": "plan", "properties": {}})

    for field in fields:
        field_key = field["field_key"]
        field_node_key = f"field:{field_key}"
        nodes.append(
            {
                "node_key": field_node_key,
                "node_type": "BusinessField",
                "name_cn": field.get("field_name_cn"),
                "value_text": field.get("value_text"),
                "source_field_key": field_key,
                "source_chunk_key": field.get("source_chunk_key"),
                "properties": {"field_code": field.get("field_code")},
            }
        )
        edges.append(
            {
                "edge_type": "HAS_FIELD",
                "from_node_key": "plan",
                "to_node_key": field_node_key,
                "source_field_key": field_key,
                "source_chunk_key": field.get("source_chunk_key"),
                "properties": {"field_code": field.get("field_code")},
            }
        )

    for region in plan.get("regions") or []:
        region = _safe_region(region)
        if not region or region not in region_evidence:
            continue
        node_key = f"region:{region}"
        nodes.append({"node_key": node_key, "node_type": "Region", "name_cn": region, "value_text": None, "properties": {}})
        edges.append({"edge_type": "IN_REGION", "from_node_key": "plan", "to_node_key": node_key, "properties": {}})

    for industry in plan.get("industries") or []:
        node_key = f"industry:{industry}"
        nodes.append({"node_key": node_key, "node_type": "Industry", "name_cn": industry, "value_text": None, "properties": {}})
        edges.append({"edge_type": "IN_INDUSTRY", "from_node_key": "plan", "to_node_key": node_key, "properties": {}})

    for org in plan.get("organizations") or []:
        node_key = f"org:{org}"
        nodes.append({"node_key": node_key, "node_type": "Organization", "name_cn": org, "value_text": None, "properties": {}})
        edges.append({"edge_type": "RELATED_TO", "from_node_key": "plan", "to_node_key": node_key, "properties": {}})

    filtered_nodes, filtered_edges, warnings = filter_graph_records("business_plan", _dedupe_nodes(nodes), _dedupe_edges(edges))
    if warnings:
        extraction.setdefault("_debug", {})["graph_schema_warnings"] = warnings
    return filtered_nodes, filtered_edges


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for node in nodes:
        key = node["node_key"]
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for edge in edges:
        key = (edge["edge_type"], edge["from_node_key"], edge["to_node_key"])
        if key not in seen:
            seen.add(key)
            result.append(edge)
    return result
