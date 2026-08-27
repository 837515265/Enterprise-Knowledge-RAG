from __future__ import annotations

from typing import Any

from .common import clean_text


def _first_evidence_location(group: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    if isinstance(group.get("primary_chunk"), dict):
        sources.append(group["primary_chunk"])
    if isinstance(chunk, dict):
        sources.append(chunk)
    sources.extend(item for item in group.get("evidence_items") or [] if isinstance(item, dict))
    sources.extend(item for item in group.get("matched_fields") or [] if isinstance(item, dict))
    for item in sources:
        bbox = item.get("bbox_json") or item.get("bbox")
        block_ids = item.get("block_ids") or []
        char_start = item.get("char_start")
        char_end = item.get("char_end")
        page_start = item.get("page_start") or item.get("page_no")
        page_end = item.get("page_end")
        if any(value is not None and value != [] for value in [bbox, block_ids, char_start, char_end, page_start, page_end]):
            return {
                "char_start": char_start,
                "char_end": char_end,
                "block_ids": block_ids,
                "bbox_json": bbox,
                "page_start": page_start,
                "page_end": page_end,
                "highlight_mode": "bbox" if bbox else ("char_span" if char_start is not None and char_end is not None else ("block" if block_ids else "page")),
            }
    return {"highlight_mode": "page"}


def build_citations(evidence_groups: list[dict[str, Any]], *, max_items: int = 12) -> list[dict[str, Any]]:
    """Build frontend-friendly references from evidence groups.

    grain_agent_showcase renders a flexible `references` list with title,
    content, and metadata. This function produces that shape from danbao-poc's
    evidence groups while preserving source ids for PDF/page highlighting.
    """
    citations: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str]] = set()
    for index, group in enumerate(evidence_groups, 1):
        context_chunk = group.get("answer_context_chunk") if isinstance(group.get("answer_context_chunk"), dict) else {}
        hit_chunk = group.get("retrieval_hit_chunk") if isinstance(group.get("retrieval_hit_chunk"), dict) else {}
        chunk = context_chunk or hit_chunk
        chunk_id = group.get("chunk_id") or chunk.get("chunk_id")
        file_node_id = group.get("file_node_id") or chunk.get("file_node_id")
        quote = clean_text(group.get("evidence_quote") or group.get("answer_hint") or chunk.get("content"))
        key = (file_node_id, chunk_id, quote[:80])
        if key in seen:
            continue
        seen.add(key)

        title = clean_text(
            group.get("title")
            or chunk.get("title")
            or chunk.get("section_title")
            or group.get("field_name_cn")
            or group.get("doc_name")
            or f"引用 {index}"
        )
        page_start = group.get("page_start") or group.get("page_no") or chunk.get("page_start")
        page_end = group.get("page_end") or chunk.get("page_end")
        location = _first_evidence_location(group, chunk)
        page_start = page_start or location.get("page_start")
        page_end = page_end or location.get("page_end")
        meta_parts = [
            f"文件ID {file_node_id}" if file_node_id else "",
            f"Chunk {chunk_id}" if chunk_id else "",
            f"页码 {page_start}-{page_end}" if page_start and page_end and page_end != page_start else (f"页码 {page_start}" if page_start else ""),
            clean_text(group.get("route") or group.get("match_type")),
        ]
        citations.append(
            {
                "citation_id": f"ref_{len(citations) + 1}",
                "title": title,
                "content": quote,
                "meta": " | ".join(item for item in meta_parts if item),
                "kb_id": group.get("kb_id") or chunk.get("kb_id"),
                "file_node_id": file_node_id,
                "chunk_id": chunk_id,
                "page_start": page_start,
                "page_end": page_end,
                "char_start": location.get("char_start"),
                "char_end": location.get("char_end"),
                "block_ids": location.get("block_ids") or [],
                "bbox_json": location.get("bbox_json"),
                "highlight_mode": location.get("highlight_mode") or "page",
                "source": group.get("route") or group.get("hit_type"),
                "score": group.get("score"),
                "answer_context_chunk_id": chunk.get("chunk_id") if context_chunk else None,
                "retrieval_hit_chunk_id": hit_chunk.get("chunk_id") if hit_chunk else chunk_id,
                "graph_paths": [
                    item.get("graph_path")
                    for item in (group.get("matched_graph_paths") or [])
                    if isinstance(item, dict) and item.get("graph_path")
                ],
            }
        )
        if len(citations) >= max_items:
            break
    return citations
