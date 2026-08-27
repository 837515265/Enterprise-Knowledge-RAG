from __future__ import annotations

import json
import re
from typing import Any

from .chunk_generation import representative_text_for_embedding
from .common import clean_text, normalize_html_text


TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def _truncate(text: Any, limit: int) -> str:
    value = clean_text(str(text or ""))
    if limit <= 0 or len(value) <= limit:
        return value
    return value[: max(0, limit - 12)] + "...[truncated]"


def _compact_table(match: re.Match[str]) -> str:
    table = match.group(0)
    cells = [clean_text(TAG_RE.sub(" ", cell)) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", table, flags=re.IGNORECASE | re.DOTALL)]
    cells = [cell for cell in cells if cell]
    if not cells:
        return "[表格]"
    return "[表格: " + " | ".join(cells[:40]) + (" | ..." if len(cells) > 40 else "") + "]"


def compact_llm_text(text: Any, *, max_chars: int = 1800, compact_tables: bool = True) -> str:
    """Return task-oriented text for prompts, without location/debug metadata."""
    value = str(text or "")
    if compact_tables:
        value = TABLE_RE.sub(_compact_table, value)
    value = normalize_html_text(value)
    return _truncate(value, max_chars)


def build_catalog_window_text(spans: list[dict[str, Any]], max_chars: int) -> str:
    """Compact char-map spans into stable block-id lines for catalog planning."""
    lines: list[str] = []
    total = 0
    for span in spans:
        block_id = clean_text(span.get("block_id")) or "unknown_block"
        page_no = span.get("page_no")
        block_type = clean_text(span.get("block_type") or span.get("block_label"))
        text = compact_llm_text(span.get("text"), max_chars=1200)
        if not text:
            continue
        prefix = f"[{block_id}]"
        if page_no is not None:
            prefix += f"[p{page_no}]"
        if block_type:
            prefix += f"[{block_type}]"
        line = f"{prefix} {text}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def chunk_prompt_item(chunk: dict[str, Any], *, max_text_chars: int = 4000) -> dict[str, Any]:
    content = normalize_html_text(chunk.get("content"))
    text = representative_text_for_embedding(content, max_chars=max_text_chars) if len(content) > max_text_chars else compact_llm_text(content, max_chars=max_text_chars)
    return {
        "chunk_key": chunk.get("chunk_key"),
        "chunk_type": chunk.get("chunk_type"),
        "section_type": chunk.get("section_type"),
        "section_id": chunk.get("section_id"),
        "title": clean_text(chunk.get("title")),
        "section_path": [clean_text(item) for item in (chunk.get("title_path") or []) if clean_text(item)],
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "text": text,
        "text_view": "representative_slices" if len(content) > max_text_chars else "full",
        "full_text_chars": len(content),
    }


def format_chunks_for_prompt(
    chunks: list[dict[str, Any]],
    *,
    max_chars: int,
    chunk_type: str | None = "small_chunk",
    max_text_chars: int = 4000,
) -> str:
    rows: list[str] = []
    total = 0
    for chunk in chunks:
        if chunk_type and chunk.get("chunk_type") != chunk_type:
            continue
        item = chunk_prompt_item(chunk, max_text_chars=max_text_chars)
        if not item["text"]:
            continue
        line = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if total + len(line) > max_chars:
            break
        rows.append(line)
        total += len(line) + 1
    return "\n".join(rows)


def section_prompt_item(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": section.get("section_id"),
        "section_title": clean_text(section.get("section_title") or section.get("title")),
        "section_path": [clean_text(item) for item in (section.get("section_path") or []) if clean_text(item)],
        "section_level": section.get("section_level"),
        "section_type": section.get("section_type"),
        "page_start": section.get("page_start"),
        "page_end": section.get("page_end"),
    }


def summary_prompt_item(summary: dict[str, Any], *, max_summary_chars: int = 500, max_quotes: int = 5) -> dict[str, Any]:
    structured = summary.get("structured_summary") or {}
    if not isinstance(structured, dict):
        structured = {}
    slim_structured = {
        key: structured.get(key)
        for key in ("main_objects", "key_rules", "amounts_or_rates", "conditions", "process_steps", "references")
        if structured.get(key)
    }
    return {
        "section_id": summary.get("section_id"),
        "section_title": clean_text(summary.get("section_title")),
        "section_path": [clean_text(item) for item in (summary.get("section_path") or []) if clean_text(item)],
        "node_summary": _truncate(summary.get("node_summary"), max_summary_chars),
        "structured_summary": slim_structured,
        "covered_chunk_keys": (summary.get("covered_chunk_keys") or [])[:20],
        "evidence_quotes": (summary.get("evidence_quotes") or [])[:max_quotes],
    }


def format_summaries_for_prompt(
    summaries: list[dict[str, Any]],
    *,
    max_items: int = 30,
    max_chars: int = 8000,
    max_summary_chars: int = 500,
) -> str:
    rows: list[str] = []
    total = 0
    for summary in summaries[:max_items]:
        line = json.dumps(summary_prompt_item(summary, max_summary_chars=max_summary_chars), ensure_ascii=False, separators=(",", ":"))
        if total + len(line) > max_chars:
            break
        rows.append(line)
        total += len(line) + 1
    return "\n".join(rows)


def knowledge_prompt_view(knowledge_structure: dict[str, Any], *, max_anchors: int = 40, max_units: int = 80, max_relations: int = 40) -> dict[str, Any]:
    anchors = []
    for item in (knowledge_structure.get("anchors") or [])[:max_anchors]:
        anchors.append(
            {
                "anchor_id": item.get("anchor_id"),
                "anchor_type": item.get("anchor_type"),
                "anchor_name": clean_text(item.get("anchor_name") or item.get("name")),
                "evidence_quote": clean_text(item.get("evidence_quote")),
            }
        )
    units = []
    for item in (knowledge_structure.get("knowledge_units") or [])[:max_units]:
        units.append(
            {
                "unit_id": item.get("unit_id"),
                "unit_type": item.get("unit_type"),
                "unit_subtype": item.get("unit_subtype"),
                "subject": clean_text(item.get("subject")),
                "predicate": clean_text(item.get("predicate")),
                "object_text": compact_llm_text(item.get("object_text"), max_chars=500),
                "evidence_quote": clean_text(item.get("evidence_quote")),
                "source_chunk_key": item.get("source_chunk_key"),
            }
        )
    relations = []
    for item in (knowledge_structure.get("relations") or [])[:max_relations]:
        relations.append(
            {
                "relation_type": item.get("relation_type"),
                "from_id": item.get("from_id"),
                "to_id": item.get("to_id"),
                "evidence_quote": clean_text(item.get("evidence_quote")),
            }
        )
    return {"anchors": anchors, "knowledge_units": units, "relations": relations}


def build_rerank_document(candidate: dict[str, Any], *, max_chars: int = 1200) -> str:
    section_path = candidate.get("section_path") or candidate.get("title_path") or []
    if isinstance(section_path, list):
        section_path_text = " > ".join(str(item) for item in section_path if item)
    else:
        section_path_text = clean_text(section_path)
    parts = [
        f"doc={clean_text(candidate.get('doc_name') or candidate.get('file_name'))}",
        f"section={section_path_text}",
        f"title={clean_text(candidate.get('title'))}",
        f"field={clean_text(candidate.get('field_code'))}",
        compact_llm_text(candidate.get("content"), max_chars=max_chars),
        compact_llm_text(candidate.get("value_text"), max_chars=500),
        compact_llm_text(candidate.get("evidence_text"), max_chars=500),
    ]
    return _truncate(" | ".join(part for part in parts if part and part != "="), max_chars)
