from __future__ import annotations

import hashlib
import json
from typing import Any


_ROW_FIELDS = {
    "chunks": [
        "id",
        "revision_id",
        "content_hash",
        "chunk_type",
        "section_type",
        "section_id",
        "primary_chunk_id",
        "parent_chunk_id",
        "enabled",
        "audit_status",
    ],
    "fields": ["id", "field_code", "field_name_cn", "value_text", "source_chunk_id", "del_flag"],
    "qa_rows": ["id", "file_node_id", "question", "answer", "evidence_quotes_json", "confidence", "priority", "audit_status", "del_flag"],
    "section_summaries": ["id", "section_id", "node_summary", "structured_summary_json", "covered_chunk_ids_json", "confidence"],
    "anchors": ["id", "anchor_id", "anchor_type", "anchor_name", "normalized_name", "source_chunk_id", "evidence_quote", "confidence", "status"],
    "knowledge_units": ["id", "unit_id", "unit_type", "unit_subtype", "anchor_id", "subject_text", "predicate_text", "object_text", "primary_chunk_id", "evidence_quote", "confidence", "status"],
    "graph_nodes": ["id", "node_key", "node_type", "name_cn", "value_text", "source_chunk_id", "source_field_id"],
    "graph_edges": ["id", "edge_type", "from_node_key", "to_node_key", "source_chunk_id", "source_field_id"],
}


def _stable_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_index_snapshot_signature(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic signature for the rows that feed ES and Neo4j.

    The signature is used like GraphRAG/DataGraphX checkpoints: when the active
    parse generation is already indexed, a repeated rebuild request can reuse
    the current generation instead of deleting and writing identical documents.
    """
    payload: dict[str, Any] = {
        "kb_id": (snapshot.get("file_node") or {}).get("kb_id"),
        "file_node_id": (snapshot.get("file_node") or {}).get("id"),
        "parse_generation": snapshot.get("parse_generation"),
        "row_counts": {},
        "rows": {},
    }
    for collection, fields in _ROW_FIELDS.items():
        rows = snapshot.get(collection) or []
        payload["row_counts"][collection] = len(rows)
        stable_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            stable_rows.append({field: _stable_value(row.get(field)) for field in fields if field in row})
        payload["rows"][collection] = sorted(stable_rows, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "snapshot_hash": hashlib.sha1(raw.encode("utf-8")).hexdigest(),
        "row_counts": payload["row_counts"],
    }


def plan_incremental_index(
    snapshot: dict[str, Any],
    *,
    requested_index_generation: str | None = None,
    incremental_reuse: bool = True,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    signature = build_index_snapshot_signature(snapshot)
    file_node = snapshot.get("file_node") or {}
    active_generation = file_node.get("current_index_generation")
    active_parse_generation = file_node.get("current_parse_generation")
    index_status = str(file_node.get("index_status") or "").lower()
    parse_generation = snapshot.get("parse_generation")
    can_reuse = (
        bool(incremental_reuse)
        and not force_rebuild
        and not requested_index_generation
        and bool(active_generation)
        and active_parse_generation == parse_generation
        and index_status in {"synced", "active", "success"}
    )
    reason = "active_generation_matches_parse" if can_reuse else "rebuild_required"
    if force_rebuild:
        reason = "force_rebuild"
    elif requested_index_generation:
        reason = "explicit_index_generation"
    elif not active_generation:
        reason = "no_active_index_generation"
    elif active_parse_generation != parse_generation:
        reason = "parse_generation_changed"
    elif index_status not in {"synced", "active", "success"}:
        reason = "active_index_not_synced"
    return {
        **signature,
        "reuse_previous": can_reuse,
        "reuse_index_generation": active_generation if can_reuse else None,
        "reason": reason,
    }
