from __future__ import annotations

from typing import Any

from .common import clean_text


def build_answer_context_protocol(
    evidence_groups: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    *,
    max_items: int = 12,
) -> dict[str, Any]:
    """Build answer-ready citation context.

    Retrieval returns rich evidence groups for UI/debug. This protocol is the
    compact contract for answer generation: every factual sentence should cite
    one or more `[ref_n]` ids, and unsupported facts should be omitted.
    """
    groups_by_chunk: dict[tuple[Any, Any], dict[str, Any]] = {}
    for group in evidence_groups:
        context_chunk = group.get("answer_context_chunk") if isinstance(group.get("answer_context_chunk"), dict) else {}
        hit_chunk = group.get("retrieval_hit_chunk") if isinstance(group.get("retrieval_hit_chunk"), dict) else {}
        chunk = context_chunk or hit_chunk
        key = (group.get("file_node_id") or chunk.get("file_node_id"), group.get("chunk_id") or chunk.get("chunk_id"))
        groups_by_chunk.setdefault(key, group)

    blocks: list[dict[str, Any]] = []
    for citation in citations[:max_items]:
        key = (citation.get("file_node_id"), citation.get("chunk_id"))
        group = groups_by_chunk.get(key) or {}
        context_chunk = group.get("answer_context_chunk") if isinstance(group.get("answer_context_chunk"), dict) else {}
        context_text = context_chunk.get("content") or citation.get("content") or group.get("answer_hint") or group.get("display_text")
        quote = citation.get("content") or group.get("evidence_quote") or group.get("answer_hint") or context_text
        ref_id = citation.get("citation_id") or f"ref_{len(blocks) + 1}"
        blocks.append(
            {
                "ref_id": ref_id,
                "title": citation.get("title"),
                "quote": clean_text(quote),
                "context": clean_text(context_text),
                "source": citation.get("source"),
                "kb_id": citation.get("kb_id"),
                "file_node_id": citation.get("file_node_id"),
                "chunk_id": citation.get("chunk_id"),
                "page_start": citation.get("page_start"),
                "page_end": citation.get("page_end"),
                "score": citation.get("score"),
            }
        )
    lines = [
        "回答要求：只使用下面引用材料作答；每个关键事实后标注 [ref_n]；证据不足时直接说明未检索到可靠依据。",
    ]
    for block in blocks:
        location = f"页码 {block['page_start']}" if block.get("page_start") else ""
        lines.append(f"[{block['ref_id']}] {block.get('title') or '引用'} {location}\n{block.get('context') or block.get('quote')}")
    return {
        "protocol": "answer_with_inline_ref_ids",
        "citation_style": "[ref_n]",
        "instruction": lines[0],
        "blocks": blocks,
        "prompt_context": "\n\n".join(lines),
    }
