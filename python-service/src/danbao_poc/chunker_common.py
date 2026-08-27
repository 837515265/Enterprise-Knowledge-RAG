from __future__ import annotations

import re
from typing import Any

from .common import clean_text, stable_hash


HEADING_RE = re.compile(
    r"^\s*(#{1,6}\s+.+|第[一二三四五六七八九十百千万0-9]+[章节条款].*|"
    r"[一二三四五六七八九十]+[、.．].*|[0-9]+[、.．].*|（[一二三四五六七八九十0-9]+）.*)"
)
MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 2000
OVERLAP_CHARS = 100
EMBEDDING_PREFIX_CHARS = 160
PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:[-—–－]\s*)?\d{1,4}(?:\s*[-—–－])?\s*$|^\s*第\s*\d{1,4}\s*页\s*$"
)


def doc_title(middle_document: dict[str, Any]) -> str:
    for page in middle_document.get("pages") or []:
        for block in page.get("blocks") or []:
            if block.get("label") == "doc_title" and block.get("text"):
                return clean_text(block["text"])
    file_name = middle_document.get("file_name") or "unknown"
    return file_name.rsplit(".", 1)[0]


def flatten_blocks(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in middle_document.get("pages") or []:
        page_no = page.get("page_no")
        for block in page.get("blocks") or []:
            item = dict(block)
            item["page_no"] = page_no
            rows.append(item)
    return sorted(rows, key=lambda item: (item.get("page_no") or 0, item.get("order") or 0))


def is_page_number_text(text: Any) -> bool:
    return bool(PAGE_NUMBER_RE.match(clean_text(text)))


def is_page_number_block(block: dict[str, Any]) -> bool:
    return is_page_number_text(block.get("text"))


def embedding_text(doc_title_value: str, title: str, content: str) -> str:
    prefix = clean_text(f"{doc_title_value} {title}")[:EMBEDDING_PREFIX_CHARS]
    return clean_text(f"{prefix} {content}")


def split_content(
    content: str,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[str]:
    if len(content) <= max_chars:
        return [content]
    parts: list[str] = []
    start = 0
    min_advance = max(MIN_CHUNK_CHARS, min(max_chars // 3, max_chars - overlap_chars if max_chars > overlap_chars else max_chars))
    while start < len(content):
        end = min(len(content), start + max_chars)
        if end < len(content):
            split_at = max(content.rfind("\n", start, end), content.rfind("。", start, end), content.rfind("；", start, end))
            if split_at >= start + min_advance:
                end = split_at + 1
        part = content[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(content):
            break
        next_start = max(end - overlap_chars, start + min_advance)
        if next_start <= start:
            next_start = start + min_advance
        start = min(next_start, len(content))
    return parts


def renumber_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, chunk in enumerate(chunks, 1):
        chunk["seq_no"] = index
        chunk["chunk_key"] = f"chunk_{index:03d}"
    return chunks


def chunk_by_headers(middle_document: dict[str, Any], *, chunk_type: str = "text_section") -> list[dict[str, Any]]:
    doc_title_value = doc_title(middle_document)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for block in flatten_blocks(middle_document):
        text = clean_text(block.get("text"))
        if not text or is_page_number_text(text) or block.get("type") in {"noise", "seal"} or block.get("label") == "doc_title":
            continue
        is_heading = block.get("type") == "title" or (len(text) <= 100 and bool(HEADING_RE.match(text)))
        if current is None:
            current = {"title": text if is_heading else doc_title_value, "blocks": []}
        elif is_heading:
            sections.append(current)
            current = {"title": text, "blocks": []}
        current["blocks"].append(block)

    if current:
        sections.append(current)

    chunks: list[dict[str, Any]] = []
    seq_no = 0
    pending_short: dict[str, Any] | None = None

    def append_chunk(section: dict[str, Any], blocks: list[dict[str, Any]], content: str, section_hash: str, part_index: int = 1) -> None:
        nonlocal seq_no
        page_numbers = [item.get("page_no") for item in blocks if item.get("page_no")]
        title = clean_text(section.get("title"))
        seq_no += 1
        chunk_key = f"chunk_{seq_no:03d}"
        chunks.append(
            {
                "chunk_key": chunk_key,
                "seq_no": seq_no,
                "chunk_type": chunk_type,
                "section_type": "table_region" if any(item.get("type") == "table" for item in blocks) else chunk_type,
                "section_id": f"section_{section_hash}",
                "chunk_group_id": f"section:{section_hash}",
                "title": title,
                "title_path": [doc_title_value, title],
                "content": content,
                "summary": content[:180],
                "content_hash": stable_hash(content, 40),
                "content_for_embedding": embedding_text(doc_title_value, title, content),
                "content_for_bm25": clean_text(f"{doc_title_value} {title} {content}"),
                "page_start": min(page_numbers) if page_numbers else None,
                "page_end": max(page_numbers) if page_numbers else None,
                "block_ids": [item.get("block_id") for item in blocks if item.get("block_id")],
                "bbox": [],
                "metadata": {
                    "document_title": doc_title_value,
                    "profile": middle_document.get("profile"),
                    "part_index": part_index,
                    "min_chunk_chars": MIN_CHUNK_CHARS,
                    "max_chunk_chars": MAX_CHUNK_CHARS,
                    "confidence": "EXTRACTED",
                },
            }
        )

    for section in sections:
        blocks = section["blocks"]
        content = clean_text("\n".join(item.get("text") or "" for item in blocks))
        if not content:
            continue
        title = clean_text(section.get("title"))
        section_hash = stable_hash(title or content[:80], 16)
        if len(content) < MIN_CHUNK_CHARS and pending_short:
            pending_short["blocks"].extend(blocks)
            pending_short["content"] = clean_text(f"{pending_short['content']}\n{content}")
            pending_short["title"] = pending_short["title"] or title
            if len(pending_short["content"]) < MIN_CHUNK_CHARS:
                continue
            merged_section = {"title": pending_short["title"]}
            merged_hash = stable_hash(merged_section["title"] or pending_short["content"][:80], 16)
            for part_index, part in enumerate(split_content(pending_short["content"]), 1):
                append_chunk(merged_section, pending_short["blocks"], part, merged_hash, part_index)
            pending_short = None
            continue
        if len(content) < MIN_CHUNK_CHARS:
            pending_short = {"title": title, "blocks": list(blocks), "content": content}
            continue
        for part_index, part in enumerate(split_content(content), 1):
            append_chunk(section, blocks, part, section_hash, part_index)
    if pending_short:
        section = {"title": pending_short["title"]}
        section_hash = stable_hash(section["title"] or pending_short["content"][:80], 16)
        append_chunk(section, pending_short["blocks"], pending_short["content"], section_hash, 1)
    return renumber_chunks(chunks)
