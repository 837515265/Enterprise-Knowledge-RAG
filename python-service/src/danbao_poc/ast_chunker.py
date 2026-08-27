from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from danbao_poc.chunker_common import doc_title, embedding_text, flatten_blocks, split_content
from danbao_poc.common import clean_text, stable_hash


MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
RULE_HEADING_RE = re.compile(r"^(第[一二三四五六七八九十百千万0-9]+[章节条款].*)$")
NUMBER_HEADING_RE = re.compile(r"^([一二三四五六七八九十]+[、.．].*|[0-9]+[、.．]\s*.*|（[一二三四五六七八九十0-9]+）.*)$")
FENCE_RE = re.compile(r"^\s*```(\w+)?")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass
class AstUnit:
    kind: str
    text: str
    level: int | None = None
    title: str | None = None
    page_no: int | None = None
    block_ids: list[str] | None = None
    protected_block: bool = False
    protected_block_type: str | None = None


def _line_lookup(middle_document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for block in flatten_blocks(middle_document):
        text = clean_text(block.get("text"))
        if not text:
            continue
        for line in text.splitlines() or [text]:
            normalized = clean_text(line)
            if normalized:
                lookup.setdefault(normalized, []).append(block)
    return lookup


def _source_text(middle_document: dict[str, Any]) -> str:
    text = clean_text(middle_document.get("markdown") or "")
    if text:
        return text
    text = clean_text(middle_document.get("normalized_text") or middle_document.get("plain_text") or "")
    if text:
        return text
    return "\n".join(clean_text(block.get("text")) for block in flatten_blocks(middle_document) if clean_text(block.get("text")))


def _take_line_meta(line: str, lookup: dict[str, list[dict[str, Any]]]) -> tuple[int | None, list[str]]:
    rows = lookup.get(clean_text(line)) or []
    if not rows:
        return None, []
    row = rows.pop(0)
    block_id = row.get("block_id")
    return row.get("page_no"), [block_id] if block_id else []


def _heading_level_and_title(line: str) -> tuple[int, str] | None:
    text = clean_text(line)
    match = MARKDOWN_HEADING_RE.match(text)
    if match:
        return len(match.group(1)), clean_text(match.group(2))
    if RULE_HEADING_RE.match(text):
        if "章" in text:
            return 1, text
        if "节" in text:
            return 2, text
        if "条" in text:
            return 3, text
        return 4, text
    if NUMBER_HEADING_RE.match(text) and len(text) <= 100:
        if re.match(r"^[一二三四五六七八九十]+[、.．]", text):
            return 2, text
        if text.startswith("（"):
            return 4, text
        return 3, text
    return None


def _is_table_start(lines: list[str], index: int) -> bool:
    line = clean_text(lines[index])
    if not line.startswith("|") or "|" not in line[1:]:
        return False
    if index + 1 >= len(lines):
        return False
    return bool(TABLE_SEPARATOR_RE.match(clean_text(lines[index + 1])))


def _parse_ast_units(middle_document: dict[str, Any]) -> list[AstUnit]:
    text = _source_text(middle_document)
    if not text:
        return []
    lookup = _line_lookup(middle_document)
    lines = [line.rstrip() for line in text.splitlines()]
    units: list[AstUnit] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = clean_text(raw_line)
        if not line:
            index += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            start = index
            index += 1
            while index < len(lines) and not FENCE_RE.match(clean_text(lines[index])):
                index += 1
            if index < len(lines):
                index += 1
            block_lines = [item.rstrip() for item in lines[start:index]]
            page_no, block_ids = _take_line_meta(block_lines[0], lookup)
            for extra in block_lines[1:]:
                extra_page, extra_ids = _take_line_meta(extra, lookup)
                page_no = page_no or extra_page
                block_ids.extend(extra_ids)
            units.append(
                AstUnit(
                    kind="code_block",
                    text=clean_text("\n".join(block_lines)),
                    page_no=page_no,
                    block_ids=block_ids,
                    protected_block=True,
                    protected_block_type="code",
                )
            )
            continue

        if _is_table_start(lines, index):
            start = index
            index += 1
            while index < len(lines) and clean_text(lines[index]).startswith("|"):
                index += 1
            block_lines = [item.rstrip() for item in lines[start:index]]
            page_no = None
            block_ids: list[str] = []
            for item in block_lines:
                item_page, item_ids = _take_line_meta(item, lookup)
                page_no = page_no or item_page
                block_ids.extend(item_ids)
            units.append(
                AstUnit(
                    kind="table_block",
                    text=clean_text("\n".join(block_lines)),
                    page_no=page_no,
                    block_ids=block_ids,
                    protected_block=True,
                    protected_block_type="table",
                )
            )
            continue

        heading = _heading_level_and_title(line)
        page_no, block_ids = _take_line_meta(line, lookup)
        if heading:
            level, title = heading
            units.append(AstUnit(kind="heading", text=line, level=level, title=title, page_no=page_no, block_ids=block_ids))
        else:
            units.append(AstUnit(kind="text", text=line, page_no=page_no, block_ids=block_ids))
        index += 1
    return units


def _append_chunk(
    chunks: list[dict[str, Any]],
    *,
    doc_title_value: str,
    middle_document: dict[str, Any],
    title_path: list[str],
    content: str,
    chunk_type: str,
    section_type: str,
    pages: list[int],
    block_ids: list[str],
    metadata: dict[str, Any],
    part_index: int = 1,
) -> None:
    content = clean_text(content)
    if not content:
        return
    title = title_path[-1] if title_path else doc_title_value
    section_path = " / ".join(title_path)
    section_hash = stable_hash(f"{section_path}\n{content[:120]}", 16)
    chunks.append(
        {
            "chunk_key": f"chunk_{len(chunks) + 1:03d}",
            "seq_no": len(chunks) + 1,
            "chunk_type": chunk_type,
            "section_type": section_type,
            "section_id": f"ast_section_{section_hash}",
            "chunk_group_id": f"section:{section_hash}",
            "title": title,
            "title_path": title_path,
            "content": content,
            "summary": content[:180],
            "content_hash": stable_hash(content, 40),
            "content_for_embedding": embedding_text(doc_title_value, title, content),
            "content_for_bm25": clean_text(f"{doc_title_value} {section_path} {content}"),
            "page_start": min(pages) if pages else None,
            "page_end": max(pages) if pages else None,
            "block_ids": block_ids,
            "bbox": [],
            "metadata": {
                "document_title": doc_title_value,
                "profile": middle_document.get("profile"),
                "section_path": section_path,
                "title_path": title_path,
                "part_index": part_index,
                "fallback_source": "markdown_ast",
                "confidence": "EXTRACTED",
                **metadata,
            },
        }
    )


def chunk_by_markdown_ast_fallback(
    middle_document: dict[str, Any],
    *,
    profile: str | None = None,
    chunk_type: str = "text_section",
) -> list[dict[str, Any]]:
    units = _parse_ast_units(middle_document)
    if not units:
        return []
    doc_title_value = doc_title(middle_document)
    title_stack: list[tuple[int, str]] = [(0, doc_title_value)]
    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    buffer_pages: list[int] = []
    buffer_block_ids: list[str] = []

    def current_title_path() -> list[str]:
        path = [title for _, title in title_stack if title]
        return path or [doc_title_value]

    def flush_buffer() -> None:
        nonlocal buffer, buffer_pages, buffer_block_ids
        content = clean_text("\n".join(buffer))
        if not content:
            buffer = []
            buffer_pages = []
            buffer_block_ids = []
            return
        for part_index, part in enumerate(split_content(content), 1):
            _append_chunk(
                chunks,
                doc_title_value=doc_title_value,
                middle_document=middle_document,
                title_path=current_title_path(),
                content=part,
                chunk_type=chunk_type,
                section_type=chunk_type,
                pages=buffer_pages,
                block_ids=buffer_block_ids,
                metadata={"protected_block": False, "profile": profile or middle_document.get("profile")},
                part_index=part_index,
            )
        buffer = []
        buffer_pages = []
        buffer_block_ids = []

    for unit in units:
        if unit.kind == "heading":
            flush_buffer()
            level = unit.level or 1
            while title_stack and title_stack[-1][0] >= level:
                title_stack.pop()
            title_stack.append((level, unit.title or unit.text))
            buffer.append(unit.text)
            if unit.page_no:
                buffer_pages.append(unit.page_no)
            buffer_block_ids.extend(unit.block_ids or [])
            continue

        if unit.protected_block:
            flush_buffer()
            title_path = current_title_path()
            protected_type = unit.protected_block_type or unit.kind
            protected_title = f"{title_path[-1]} {'表格' if protected_type == 'table' else '代码块'}"
            _append_chunk(
                chunks,
                doc_title_value=doc_title_value,
                middle_document=middle_document,
                title_path=[*title_path[:-1], protected_title],
                content=unit.text,
                chunk_type="table_region" if protected_type == "table" else "code_block",
                section_type="table_region" if protected_type == "table" else "code_block",
                pages=[unit.page_no] if unit.page_no else [],
                block_ids=unit.block_ids or [],
                metadata={
                    "protected_block": True,
                    "protected_block_type": protected_type,
                    "profile": profile or middle_document.get("profile"),
                },
            )
            continue

        buffer.append(unit.text)
        if unit.page_no:
            buffer_pages.append(unit.page_no)
        buffer_block_ids.extend(unit.block_ids or [])
    flush_buffer()
    return chunks
