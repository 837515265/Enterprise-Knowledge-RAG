from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from .chunker_common import embedding_text, split_content
from .common import clean_text, normalize_html_text, stable_hash, visible_text_length


DEFAULT_SMALL_CHUNK_CHARS = 1200
DEFAULT_SMALL_CHUNK_OVERLAP = 120
DEFAULT_SECTION_CHUNK_CHARS = 4200
DEFAULT_PARENT_CHUNK_CHARS = 6500
DEFAULT_EMBEDDING_SOURCE_CHARS = 4000


def _extract_keywords(text: str, top_k: int = 5) -> list[str]:
    # Adapted from RAG-Pro: regex terms over the first part of the chunk, then
    # frequency ranking. Keep it deterministic so indexing does not require LLM.
    words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", text[:5000])
    freq: dict[str, int] = {}
    for word in words:
        token = word.lower()
        if token in {"的", "以及", "进行", "相关", "本产品", "本方案"}:
            continue
        freq[token] = freq.get(token, 0) + 1
    return [word for word, _ in sorted(freq.items(), key=lambda item: (-item[1], item[0]))[:top_k]]


def _generate_questions(text: str, count: int = 3) -> list[str]:
    # Adapted from RAG-Pro's sentence-to-question heuristic.
    sentences = [s.strip() for s in re.split(r"[。！？!?\.]+", text[:2000]) if len(s.strip()) > 10]
    questions: list[str] = []
    for sentence in sentences[:count]:
        preview = sentence[:30]
        if "如何" in sentence or "怎么" in sentence:
            questions.append(f"{preview} 的具体做法是什么？")
        elif "是" in sentence or "为" in sentence or "包括" in sentence:
            questions.append(f"{preview} 具体指的是什么？")
        elif "额度" in sentence:
            questions.append("这段内容说明的额度要求是什么？")
        elif "条件" in sentence or "准入" in sentence:
            questions.append("这段内容说明的准入条件是什么？")
        else:
            questions.append(f"这段内容中提到的“{preview}”是什么意思？")
    while len(questions) < count:
        questions.append("这段内容的核心观点是什么？")
    return questions[:count]


def _option(options: dict[str, Any] | None, path: str, default: Any) -> Any:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _bool_option(options: dict[str, Any] | None, path: str, default: bool) -> bool:
    value = _option(options, path, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _int_option(options: dict[str, Any] | None, path: str, default: int) -> int:
    try:
        return int(_option(options, path, default))
    except Exception:
        return default


def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return dict(metadata) if isinstance(metadata, dict) else {}


def _path(chunk: dict[str, Any], document_title: str) -> list[str]:
    metadata = _metadata(chunk)
    value = metadata.get("section_path") or chunk.get("title_path") or []
    if isinstance(value, list):
        path = [clean_text(item) for item in value if clean_text(item)]
    else:
        path = [clean_text(value)] if clean_text(value) else []
    title = clean_text(chunk.get("title"))
    if not path:
        path = [item for item in [document_title, title] if item]
    elif title and title not in path:
        path.append(title)
    return path


def _section_id(chunk: dict[str, Any], document_title: str) -> str:
    value = clean_text(chunk.get("section_id"))
    if value:
        return value
    return f"section_{stable_hash('>'.join(_path(chunk, document_title)) or chunk.get('content') or '', 16)}"


def _parent_section_id(chunk: dict[str, Any], section_id: str, document_title: str) -> str:
    metadata = _metadata(chunk)
    value = clean_text(metadata.get("parent_section_id"))
    if value:
        return value
    path = _path(chunk, document_title)
    if len(path) >= 3:
        return f"section_{stable_hash('>'.join(path[:-1]), 16)}"
    business_block_id = clean_text(metadata.get("business_block_id"))
    if business_block_id:
        return f"parent_{business_block_id}"
    return section_id


def _pages(chunks: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    starts = [item.get("page_start") for item in chunks if item.get("page_start") is not None]
    ends = [item.get("page_end") for item in chunks if item.get("page_end") is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _dedupe(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if value is None:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _normalized_content_hash(content: str) -> str:
    return stable_hash(normalize_html_text(content), 40)


def _is_low_value_part(content: str, min_visible_chars: int = 50) -> bool:
    if "<" not in content or ">" not in content:
        return False
    return visible_text_length(content) < min_visible_chars


def representative_text_for_embedding(content: str, *, max_chars: int = DEFAULT_EMBEDDING_SOURCE_CHARS) -> str:
    """Build a focused vector view while preserving full content elsewhere."""
    text = normalize_html_text(content)
    if len(text) <= max_chars:
        return text
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    selected: list[str] = []

    def add(value: str) -> None:
        value = clean_text(value)
        if value and value not in selected:
            selected.append(value)

    add(text[:900])
    key_terms = [
        "服务对象",
        "适用范围",
        "准入",
        "额度",
        "测算",
        "期限",
        "用途",
        "费率",
        "反担保",
        "风险",
        "材料",
        "流程",
        "必须",
        "不得",
        "应当",
        "不超过",
        "不低于",
        "=",
        "＝",
        "%",
        "万元",
    ]
    for line in lines:
        compact = line.replace(" ", "")
        if any(term in line for term in key_terms) or re_match_numbered_item(compact):
            add(line)
        if len("\n".join(selected)) >= max_chars * 0.75:
            break
    add(text[-600:])
    return clean_text("\n".join(selected))[:max_chars]


def re_match_numbered_item(text: str) -> bool:
    return bool(text and re.match(r"^([0-9]{1,2}[.．、]|[（(][一二三四五六七八九十0-9]+[）)])", text))


def _make_chunk(
    *,
    chunk_key: str,
    seq_no: int,
    chunk_type: str,
    section_type: str | None,
    section_id: str | None,
    chunk_group_id: str | None,
    title: str,
    title_path: list[str],
    content: str,
    document_title: str,
    page_start: int | None,
    page_end: int | None,
    block_ids: list[Any],
    metadata: dict[str, Any],
    bbox: list[Any] | None = None,
) -> dict[str, Any]:
    content = normalize_html_text(content)
    section_path_text = " ".join(title_path)
    embedding_source_text = clean_text(metadata.get("embedding_source_text")) or representative_text_for_embedding(content)
    keyword_count = int(metadata.get("keyword_count") or 5)
    question_count = int(metadata.get("question_count") or 3)
    keywords = metadata.get("keywords") if isinstance(metadata.get("keywords"), list) else _extract_keywords(content, keyword_count)
    possible_questions = metadata.get("possible_questions") if isinstance(metadata.get("possible_questions"), list) else _generate_questions(content, question_count)
    metadata = {
        **metadata,
        "keywords": keywords,
        "possible_questions": possible_questions,
        "enrichment_source": metadata.get("enrichment_source") or "rag_pro_regex_frequency",
    }
    bm25_text = clean_text(f"{section_path_text} {' '.join(keywords)} {' '.join(possible_questions)} {content}")
    return {
        "chunk_key": chunk_key,
        "seq_no": seq_no,
        "chunk_type": chunk_type,
        "section_type": section_type,
        "section_id": section_id,
        "chunk_group_id": chunk_group_id,
        "title": title,
        "title_path": title_path,
        "content": content,
        "summary": clean_text(content)[:180],
        "content_hash": stable_hash(f"{chunk_type}:{section_id}:{content}", 40),
        "normalized_content_hash": _normalized_content_hash(content),
        "content_for_embedding": embedding_text(document_title, " > ".join(title_path), embedding_source_text),
        "content_for_bm25": bm25_text,
        "page_start": page_start,
        "page_end": page_end,
        "block_ids": block_ids,
        "bbox": bbox or [],
        "metadata": metadata,
    }


def build_multigranularity_chunks(
    base_chunks: list[dict[str, Any]],
    *,
    document_title: str,
    profile: str,
    parse_options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert profile chunks into retrieval-oriented multi-granularity chunks.

    The profile chunkers decide domain boundaries. This layer standardizes what
    gets stored and indexed:
    - small_chunk is the primary evidence unit and defaults to the full logical section.
    - section_chunk is a wider same-section context unit.
    - parent_chunk is a parent-level context unit.
    """
    if not base_chunks:
        return []
    options = parse_options or {}
    enabled = _bool_option(options, "chunking.multigranularity_enabled", True)
    if not enabled:
        return [dict(chunk) for chunk in base_chunks]

    split_primary_by_chars = _bool_option(options, "chunking.split_primary_by_chars", False)
    max_small = max(300, _int_option(options, "chunking.max_small_chunk_chars", DEFAULT_SMALL_CHUNK_CHARS))
    overlap = max(0, _int_option(options, "chunking.small_chunk_overlap_chars", DEFAULT_SMALL_CHUNK_OVERLAP))
    max_section = max(max_small, _int_option(options, "chunking.max_section_chunk_chars", DEFAULT_SECTION_CHUNK_CHARS))
    max_parent = max(max_section, _int_option(options, "chunking.max_parent_chunk_chars", DEFAULT_PARENT_CHUNK_CHARS))
    # sql_analytics 不生成 section/parent 上下文 chunk；文件名以"字段-"开头的表结构
    # 文件同样不生成——字段表、术语、SQL 都是独立知识对象，父 chunk 会把多个对象
    # 拼成大块，干扰精确检索。
    is_field_table_file = bool(document_title) and str(document_title).startswith("字段-")
    no_context_chunks = (bool(profile) and str(profile) == "sql_analytics") or is_field_table_file
    create_section = _bool_option(options, "chunking.create_section_chunks", not no_context_chunks)
    create_parent = _bool_option(options, "chunking.create_parent_chunks", not no_context_chunks)

    small_chunks: list[dict[str, Any]] = []
    section_groups: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    parent_groups: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    source_index = 0

    for base in base_chunks:
        content = normalize_html_text(base.get("content"))
        if not content:
            continue
        source_index += 1
        metadata = _metadata(base)
        section_id = _section_id(base, document_title)
        parent_section_id = _parent_section_id(base, section_id, document_title)
        title = clean_text(base.get("title")) or (_path(base, document_title)[-1] if _path(base, document_title) else document_title)
        title_path = _path(base, document_title)
        source_chunk_key = clean_text(base.get("chunk_key")) or f"source_{source_index:03d}"
        parts = split_content(content, max_chars=max_small, overlap_chars=overlap) if split_primary_by_chars else [content]
        if not parts:
            continue
        filtered_parts = [part for part in parts if not _is_low_value_part(part)]
        if not filtered_parts:
            continue
        for part_index, part in enumerate(filtered_parts, 1):
            chunk_key = f"small_{source_index:03d}_{part_index:02d}"
            part_metadata = {
                **metadata,
                "profile": profile,
                "document_title": document_title,
                "retrieval_role": "primary",
                "source_chunk_key": source_chunk_key,
                "source_chunk_type": base.get("chunk_type"),
                "source_seq_no": base.get("seq_no"),
                "part_index": part_index,
                "part_count": len(filtered_parts),
                "full_section_preserved": not split_primary_by_chars,
                "parent_section_id": parent_section_id,
                "section_path": title_path,
                "max_small_chunk_chars": max_small if split_primary_by_chars else None,
                "small_chunk_overlap_chars": overlap if split_primary_by_chars else 0,
            }
            small = _make_chunk(
                chunk_key=chunk_key,
                seq_no=len(small_chunks) + 1,
                chunk_type="small_chunk",
                section_type=base.get("section_type") or base.get("chunk_type"),
                section_id=section_id,
                chunk_group_id=base.get("chunk_group_id") or f"section:{section_id}",
                title=title,
                title_path=title_path,
                content=part,
                document_title=document_title,
                page_start=base.get("page_start"),
                page_end=base.get("page_end"),
                block_ids=list(base.get("block_ids") or []),
                bbox=list(base.get("bbox") or []),
                metadata=part_metadata,
            )
            small_chunks.append(small)
            section_groups.setdefault(section_id, []).append(small)
            parent_groups.setdefault(parent_section_id, []).append(small)

    generated: list[dict[str, Any]] = list(small_chunks)
    context_seq = len(generated)

    if create_section:
        for section_id, children in section_groups.items():
            if len(children) < 1:
                continue
            first = children[0]
            joined = clean_text("\n\n".join(child.get("content") or "" for child in children))
            if not joined:
                continue
            content = joined[:max_section]
            child_hashes = {child.get("normalized_content_hash") for child in children if child.get("normalized_content_hash")}
            if _normalized_content_hash(content) in child_hashes:
                continue
            page_start, page_end = _pages(children)
            context_seq += 1
            child_keys = [child["chunk_key"] for child in children if child.get("chunk_key")]
            metadata = {
                **_metadata(first),
                "retrieval_role": "context",
                "context_level": "section",
                "child_chunk_keys": child_keys,
                "primary_chunk_key": child_keys[0] if child_keys else None,
                "section_path": first.get("title_path") or [],
                "max_section_chunk_chars": max_section,
            }
            generated.append(
                _make_chunk(
                    chunk_key=f"sectionctx_{stable_hash(section_id, 12)}",
                    seq_no=context_seq,
                    chunk_type="section_chunk",
                    section_type=first.get("section_type"),
                    section_id=section_id,
                    chunk_group_id=f"section:{section_id}",
                    title=clean_text(first.get("title")),
                    title_path=list(first.get("title_path") or []),
                    content=content,
                    document_title=document_title,
                    page_start=page_start,
                    page_end=page_end,
                    block_ids=_dedupe([block_id for child in children for block_id in (child.get("block_ids") or [])]),
                    bbox=[],
                    metadata=metadata,
                )
            )

    if create_parent:
        for parent_section_id, children in parent_groups.items():
            if not parent_section_id or len({child.get("section_id") for child in children}) <= 1:
                continue
            first = children[0]
            sections_seen: set[str] = set()
            section_texts: list[str] = []
            for child in children:
                sid = str(child.get("section_id") or "")
                if sid in sections_seen:
                    continue
                sections_seen.add(sid)
                title = clean_text(child.get("title"))
                section_text = clean_text("\n".join(s.get("content") or "" for s in children if s.get("section_id") == child.get("section_id")))
                section_texts.append(clean_text(f"{title}\n{section_text}"))
            content = clean_text("\n\n".join(section_texts))[:max_parent]
            if not content:
                continue
            page_start, page_end = _pages(children)
            context_seq += 1
            child_keys = [child["chunk_key"] for child in children if child.get("chunk_key")]
            parent_title_path = list(first.get("title_path") or [])
            if len(parent_title_path) > 1:
                parent_title_path = parent_title_path[:-1]
            metadata = {
                **_metadata(first),
                "retrieval_role": "context",
                "context_level": "parent",
                "parent_section_id": parent_section_id,
                "child_chunk_keys": child_keys,
                "child_section_ids": list(sections_seen),
                "primary_chunk_key": child_keys[0] if child_keys else None,
                "section_path": parent_title_path,
                "max_parent_chunk_chars": max_parent,
            }
            generated.append(
                _make_chunk(
                    chunk_key=f"parentctx_{stable_hash(parent_section_id, 12)}",
                    seq_no=context_seq,
                    chunk_type="parent_chunk",
                    section_type=first.get("section_type"),
                    section_id=parent_section_id,
                    chunk_group_id=f"parent:{parent_section_id}",
                    title=parent_title_path[-1] if parent_title_path else document_title,
                    title_path=parent_title_path or [document_title],
                    content=content,
                    document_title=document_title,
                    page_start=page_start,
                    page_end=page_end,
                    block_ids=_dedupe([block_id for child in children for block_id in (child.get("block_ids") or [])]),
                    bbox=[],
                    metadata=metadata,
                )
            )

    for index, chunk in enumerate(generated, 1):
        chunk["seq_no"] = index
    return generated


def primary_chunks_for_extraction(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primary = [chunk for chunk in chunks if chunk.get("chunk_type") == "small_chunk"]
    main_primary = [chunk for chunk in primary if _metadata(chunk).get("content_role") != "appendix" and chunk.get("section_type") != "appendix"]
    if main_primary:
        return main_primary
    return primary or chunks
