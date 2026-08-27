from __future__ import annotations

from typing import Any


CONFIDENCE_VALUES = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
REQUIRED_CHUNK_FIELDS = {
    "chunk_key",
    "seq_no",
    "chunk_type",
    "section_type",
    "content",
    "content_hash",
    "content_for_embedding",
    "content_for_bm25",
}


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def validate_middle_document(middle_document: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not isinstance(middle_document.get("pages"), list):
        warnings.append("middle_document.pages must be a list")
    char_map = middle_document.get("char_map") or {}
    spans = char_map.get("spans") or []
    normalized_text = middle_document.get("normalized_text") or ""
    last_end = 0
    for index, span in enumerate(spans, 1):
        start = span.get("global_char_start")
        end = span.get("global_char_end")
        if not isinstance(start, int) or not isinstance(end, int) or start > end:
            warnings.append(f"char_map span {index} has invalid offsets")
            continue
        if start < last_end:
            warnings.append(f"char_map span {index} overlaps previous span")
        if normalized_text and end > len(normalized_text):
            warnings.append(f"char_map span {index} exceeds normalized_text length")
        last_end = max(last_end, end)
    return warnings


def validate_chunks(chunks: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    seen_keys: set[str] = set()
    for index, chunk in enumerate(chunks, 1):
        missing = sorted(field for field in REQUIRED_CHUNK_FIELDS if not chunk.get(field))
        if missing:
            warnings.append(f"chunk {index} missing fields: {','.join(missing)}")
        chunk_key = str(chunk.get("chunk_key") or "")
        if chunk_key in seen_keys:
            warnings.append(f"duplicate chunk_key: {chunk_key}")
        seen_keys.add(chunk_key)
        if chunk.get("seq_no") != index:
            warnings.append(f"chunk {chunk_key or index} seq_no is not continuous")
        confidence = _metadata(chunk).get("confidence")
        if confidence and confidence not in CONFIDENCE_VALUES:
            warnings.append(f"chunk {chunk_key or index} has invalid confidence: {confidence}")
    return warnings


def validate_graph_items(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    node_keys = {str(node.get("node_key") or "") for node in nodes if node.get("node_key")}
    for index, edge in enumerate(edges, 1):
        if not edge.get("edge_type"):
            warnings.append(f"graph edge {index} missing edge_type")
        if edge.get("from_node_key") not in node_keys:
            warnings.append(f"graph edge {index} from_node_key not found")
        if edge.get("to_node_key") not in node_keys:
            warnings.append(f"graph edge {index} to_node_key not found")
    return warnings


def validate_relation_payload(
    from_chunk: dict[str, Any],
    to_chunk: dict[str, Any],
    relation_type: str,
    weight: float,
    properties: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not from_chunk.get("id") or not to_chunk.get("id"):
        warnings.append("relation endpoint chunk id is missing")
    if from_chunk.get("id") == to_chunk.get("id"):
        warnings.append("relation endpoints must not be the same chunk")
    if not relation_type:
        warnings.append("relation_type is missing")
    if weight <= 0:
        warnings.append("relation weight must be positive")
    confidence = properties.get("confidence") if isinstance(properties, dict) else None
    if confidence and confidence not in CONFIDENCE_VALUES:
        warnings.append(f"relation confidence invalid: {confidence}")
    return warnings
