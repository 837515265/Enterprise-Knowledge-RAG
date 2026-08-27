from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .chunk_generation import _extract_keywords, _generate_questions
from .common import clean_text, stable_hash
from .openai_compat import JsonChatClient
from .prompt_views import format_chunks_for_prompt, format_summaries_for_prompt, section_prompt_item


SECTION_SUMMARY_SYSTEM_PROMPT = """你是企业知识库 RAG-Doc 的层级摘要模型。
你的任务是给目录章节生成可检索、可路由、可回挂原文 chunk 的摘要。

必须遵守：
1. 只输出 JSON object。
2. 摘要不是最终答案，不能替代原文 chunk。
3. node_summary 要短、准、完整，适合作为检索路由和父级上下文。
4. structured_summary_json 要按 profile 提炼对象、规则、数值、条件、流程、引用。
5. 不确定的信息不要编造；缺失就写 null 或空数组。
6. evidence_quotes 每条必须来自输入原文，不要改写。
"""


PROFILE_REQUIRED_SECTION_TYPES: dict[str, set[str]] = {
    "business_plan": {
        "service_object",
        "business_scope",
        "admission_requirement",
        "credit_limit",
        "guarantee_term",
        "credit_purpose",
        "fee_rate",
    },
    "governance_rule": {
        "general_principle",
        "applicable_scope",
        "responsibility_clause",
        "procedure_clause",
        "effective_clause",
    },
    "project_doc": {
        "document_meta",
        "requirement",
        "architecture",
        "module_design",
    },
}


def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    value = chunk.get("metadata") or {}
    return value if isinstance(value, dict) else {}


def validate_profile_summary_coverage(
    *,
    profile: str,
    chunks: list[dict[str, Any]],
    section_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    required = PROFILE_REQUIRED_SECTION_TYPES.get(profile) or set()
    present = {
        clean_text(chunk.get("section_type"))
        for chunk in chunks
        if clean_text(chunk.get("section_type"))
    }
    summarized_sections = {
        clean_text(summary.get("section_id"))
        for summary in section_summaries
        if clean_text(summary.get("section_id")) and clean_text(summary.get("node_summary"))
    }
    chunk_sections = {
        clean_text(chunk.get("section_id"))
        for chunk in chunks
        if clean_text(chunk.get("section_id"))
    }
    missing_required = sorted(required - present)
    unsummarized_sections = sorted(chunk_sections - summarized_sections)
    warnings = [f"profile_required_section_missing:{profile}:{item}" for item in missing_required]
    warnings.extend(f"section_summary_missing:{item}" for item in unsummarized_sections[:50])
    return {
        "profile": profile,
        "required_section_types": sorted(required),
        "present_section_types": sorted(item for item in present if item),
        "missing_required_section_types": missing_required,
        "section_count": len(chunk_sections),
        "summarized_section_count": len(summarized_sections),
        "unsummarized_section_ids": unsummarized_sections[:100],
        "warnings": warnings,
    }


def _title_path(chunk: dict[str, Any]) -> list[str]:
    value = chunk.get("title_path") or []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


def _section_path(chunk: dict[str, Any], document_title: str) -> list[str]:
    metadata = _metadata(chunk)
    path = metadata.get("section_path")
    if isinstance(path, list):
        cleaned = [clean_text(item) for item in path if clean_text(item)]
        if cleaned:
            return cleaned
    path = _title_path(chunk)
    if path:
        return path
    title = clean_text(chunk.get("title"))
    return [item for item in [document_title, title] if item]


def _section_id(chunk: dict[str, Any], document_title: str) -> str:
    value = clean_text(chunk.get("section_id"))
    if value:
        return value
    path = " > ".join(_section_path(chunk, document_title))
    return f"section_{stable_hash(path or chunk.get('content') or '', 16)}"


def _int_option(options: dict[str, Any] | None, path: str, default: int) -> int:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    try:
        return int(current)
    except Exception:
        return default


def _float_option(options: dict[str, Any] | None, path: str, default: float) -> float:
    try:
        return float(_option(options, path, default))
    except Exception:
        return default


def _option(options: dict[str, Any] | None, path: str, default: Any = None) -> Any:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _parse_level_set(value: Any) -> set[int] | None:
    if value is None:
        return None
    if isinstance(value, str):
        values = [item.strip() for item in value.replace("，", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    result: set[int] = set()
    for item in values:
        try:
            result.add(int(item))
        except Exception:
            continue
    return result if result else set()


def _section_level(section: dict[str, Any]) -> int:
    try:
        return int(section.get("section_level") or 1)
    except Exception:
        return 1


def _summary_level_allowed(section: dict[str, Any], options: dict[str, Any] | None) -> bool:
    level = _section_level(section)
    explicit = (
        _parse_level_set(_option(options, "summary.enabled_section_levels"))
        or _parse_level_set(_option(options, "summary.section_levels"))
        or _parse_level_set(_option(options, "summary.summarize_section_levels"))
    )
    if explicit is not None and level not in explicit:
        return False
    skipped = (
        _parse_level_set(_option(options, "summary.skip_section_levels"))
        or _parse_level_set(_option(options, "summary.disabled_section_levels"))
    )
    if skipped is not None and level in skipped:
        return False
    min_level = _option(options, "summary.min_section_level")
    max_level = _option(options, "summary.max_section_level")
    try:
        if min_level is not None and level < int(min_level):
            return False
    except Exception:
        pass
    try:
        if max_level is not None and level > int(max_level):
            return False
    except Exception:
        pass
    return True


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


def _normalize_evidence_quotes(value: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    evidence: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            quote = clean_text(item)
            row: dict[str, Any] = {"quote": quote}
        elif isinstance(item, dict):
            quote = clean_text(item.get("quote") or item.get("evidence_quote") or item.get("text"))
            row = {
                "quote": quote,
                "chunk_key": clean_text(item.get("chunk_key")),
                "evidence_role": clean_text(item.get("evidence_role")) or "source_quote",
                "source_summary_section_id": clean_text(item.get("source_summary_section_id")),
            }
        else:
            continue
        if not quote:
            continue
        evidence.append(row)
        if len(evidence) >= limit:
            break
    return evidence


def _merge_structured_summaries(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "main_objects": [],
        "key_rules": [],
        "amounts_or_rates": [],
        "conditions": [],
        "process_steps": [],
        "references": [],
        "open_questions": [],
    }
    for summary in child_summaries:
        structured = summary.get("structured_summary") or {}
        if not isinstance(structured, dict):
            continue
        for key in merged:
            values = structured.get(key) or []
            if isinstance(values, list):
                merged[key].extend(values)
    for key in list(merged):
        merged[key] = _dedupe(merged[key])[:50]
    return merged


def _summary_structured_text(structured: dict[str, Any]) -> str:
    try:
        return json.dumps(structured, ensure_ascii=False)
    except Exception:
        return clean_text(structured)


def _retrieval_summary_fields(
    *,
    section: dict[str, Any],
    node_summary: str,
    structured: dict[str, Any],
    section_chunks: list[dict[str, Any]],
    child_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    source_text = clean_text(
        "\n".join(
            [
                clean_text(section.get("section_title")),
                node_summary,
                _summary_structured_text(structured),
                *[clean_text(chunk.get("content"))[:800] for chunk in section_chunks],
                *[clean_text(summary.get("node_summary")) for summary in child_summaries],
            ]
        )
    )
    keywords = _dedupe(
        [
            clean_text(section.get("section_title")),
            clean_text(section.get("section_type")),
            *_extract_keywords(source_text, top_k=8),
        ]
    )
    questions = _dedupe(_generate_questions(source_text or node_summary, count=4))
    child_keywords: list[str] = []
    child_questions: list[str] = []
    for summary in child_summaries:
        child_structured = summary.get("structured_summary") if isinstance(summary.get("structured_summary"), dict) else {}
        child_keywords.extend(child_structured.get("retrieval_keywords") or [])
        child_questions.extend(child_structured.get("possible_questions") or [])
    keywords = _dedupe(keywords + [clean_text(item) for item in child_keywords if clean_text(item)])[:12]
    questions = _dedupe(questions + [clean_text(item) for item in child_questions if clean_text(item)])[:8]
    fields = _dedupe(
        [
            clean_text(section.get("section_type")),
            *[clean_text(chunk.get("section_type")) for chunk in section_chunks],
            *[clean_text(item) for item in structured.get("conditions") or []],
            *[clean_text(item) for item in structured.get("amounts_or_rates") or []],
        ]
    )[:20]
    anchors = _dedupe(
        [
            *[clean_text(item) for item in structured.get("main_objects") or []],
            *[clean_text(item) for item in structured.get("references") or []],
        ]
    )[:20]
    return {
        "section_brief": node_summary[:300],
        "retrieval_keywords": [item for item in keywords if item],
        "possible_questions": [item for item in questions if item],
        "structured_hints": {
            "fields": [item for item in fields if item],
            "anchors": [item for item in anchors if item],
        },
    }


def _attach_retrieval_summary_fields(
    summary: dict[str, Any],
    *,
    section: dict[str, Any],
    section_chunks: list[dict[str, Any]],
    child_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    structured = summary.get("structured_summary") if isinstance(summary.get("structured_summary"), dict) else {}
    fields = _retrieval_summary_fields(
        section=section,
        node_summary=clean_text(summary.get("node_summary")),
        structured=structured,
        section_chunks=section_chunks,
        child_summaries=child_summaries,
    )
    structured["section_brief"] = structured.get("section_brief") or fields["section_brief"]
    structured["retrieval_keywords"] = _dedupe((structured.get("retrieval_keywords") or []) + fields["retrieval_keywords"])[:12]
    structured["possible_questions"] = _dedupe((structured.get("possible_questions") or []) + fields["possible_questions"])[:8]
    hints = structured.get("structured_hints") if isinstance(structured.get("structured_hints"), dict) else {}
    structured["structured_hints"] = {
        "fields": _dedupe((hints.get("fields") or []) + fields["structured_hints"]["fields"])[:20],
        "anchors": _dedupe((hints.get("anchors") or []) + fields["structured_hints"]["anchors"])[:20],
    }
    summary["structured_summary"] = structured
    return summary


def _summary_quality_thresholds(options: dict[str, Any] | None) -> dict[str, float]:
    return {
        "min_child_coverage_rate": max(0.0, min(1.0, _float_option(options, "summary.min_child_coverage_rate", 0.95))),
        "min_evidence_chunk_coverage_rate": max(0.0, min(1.0, _float_option(options, "summary.min_evidence_chunk_coverage_rate", 0.2))),
        "max_evidence_single_chunk_ratio": max(0.0, min(1.0, _float_option(options, "summary.max_evidence_single_chunk_ratio", 0.8))),
        "min_child_title_mention_rate": max(0.0, min(1.0, _float_option(options, "summary.min_child_title_mention_rate", 0.5))),
    }


def _attach_summary_quality(
    summary: dict[str, Any],
    *,
    section: dict[str, Any],
    direct_children: list[dict[str, Any]],
    descendant_section_ids: set[str],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    evidence_quotes = summary.get("evidence_quotes") or []
    evidence_chunk_keys = [
        clean_text(item.get("chunk_key"))
        for item in evidence_quotes
        if isinstance(item, dict) and clean_text(item.get("chunk_key"))
    ]
    covered_chunk_keys = [clean_text(item) for item in (summary.get("covered_chunk_keys") or []) if clean_text(item)]
    covered_section_ids = {clean_text(item) for item in (summary.get("covered_section_ids") or []) if clean_text(item)}
    covered_descendants = covered_section_ids & descendant_section_ids
    child_coverage_rate = len(covered_descendants) / max(len(descendant_section_ids), 1) if descendant_section_ids else 1.0

    chunk_quote_counts: dict[str, int] = defaultdict(int)
    for key in evidence_chunk_keys:
        chunk_quote_counts[key] += 1
    max_single_chunk_quotes = max(chunk_quote_counts.values(), default=0)
    evidence_quote_count = len(evidence_quotes)
    evidence_single_chunk_ratio = max_single_chunk_quotes / max(evidence_quote_count, 1)
    evidence_chunk_coverage_rate = len(set(evidence_chunk_keys)) / max(len(set(covered_chunk_keys)), 1) if covered_chunk_keys else 1.0

    node_summary = clean_text(summary.get("node_summary"))
    missing_child_title_ids: list[str] = []
    for child in direct_children:
        child_id = clean_text(child.get("section_id"))
        child_title = clean_text(child.get("section_title"))
        if not child_id or not child_title:
            continue
        if child_title not in node_summary:
            missing_child_title_ids.append(child_id)
    child_title_mention_rate = 1.0
    if direct_children:
        child_title_mention_rate = (len(direct_children) - len(missing_child_title_ids)) / max(len(direct_children), 1)

    warnings: list[str] = []
    if descendant_section_ids and child_coverage_rate < thresholds["min_child_coverage_rate"]:
        warnings.append(f"summary_child_coverage_low:{section.get('section_id')}:{child_coverage_rate:.4f}")
    if len(set(covered_chunk_keys)) >= 3 and evidence_chunk_coverage_rate < thresholds["min_evidence_chunk_coverage_rate"]:
        warnings.append(f"summary_evidence_chunk_coverage_low:{section.get('section_id')}:{evidence_chunk_coverage_rate:.4f}")
    if evidence_quote_count >= 3 and evidence_single_chunk_ratio > thresholds["max_evidence_single_chunk_ratio"]:
        warnings.append(f"summary_evidence_concentrated:{section.get('section_id')}:{evidence_single_chunk_ratio:.4f}")
    if len(direct_children) >= 2 and child_title_mention_rate < thresholds["min_child_title_mention_rate"]:
        warnings.append(f"summary_child_title_mention_low:{section.get('section_id')}:{child_title_mention_rate:.4f}")

    quality_report = {
        "descendant_section_count": len(descendant_section_ids),
        "covered_descendant_section_count": len(covered_descendants),
        "child_coverage_rate": child_coverage_rate,
        "missing_child_section_ids": sorted(descendant_section_ids - covered_descendants),
        "direct_child_count": len(direct_children),
        "child_title_mention_rate": child_title_mention_rate,
        "missing_child_title_ids": missing_child_title_ids,
        "covered_chunk_count": len(set(covered_chunk_keys)),
        "evidence_quote_count": evidence_quote_count,
        "evidence_chunk_count": len(set(evidence_chunk_keys)),
        "evidence_chunk_coverage_rate": evidence_chunk_coverage_rate,
        "evidence_single_chunk_ratio": evidence_single_chunk_ratio,
        "quality_warnings": warnings,
    }
    structured = summary.get("structured_summary") if isinstance(summary.get("structured_summary"), dict) else {}
    structured["quality_report"] = quality_report
    structured["quality_warnings"] = warnings
    summary["structured_summary"] = structured
    summary["quality_report"] = quality_report
    summary["quality_warnings"] = warnings
    return summary


def build_sections_from_chunks(
    chunks: list[dict[str, Any]],
    *,
    document_title: str,
    profile: str,
) -> list[dict[str, Any]]:
    """Derive a stable section list from existing chunk output.

    The current project already has profile-specific chunkers. This layer does
    not replace them; it gives Java/MySQL/retrieval a first-class section tree
    to reference while preserving the current chunk behavior.
    """
    sections: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for chunk in chunks:
        section_id = _section_id(chunk, document_title)
        metadata = _metadata(chunk)
        path = _section_path(chunk, document_title)
        title = clean_text(chunk.get("title")) or (path[-1] if path else document_title)
        parent_section_id = clean_text(metadata.get("parent_section_id"))
        if parent_section_id == section_id:
            parent_section_id = ""
        hierarchy_level = metadata.get("hierarchy_level")
        try:
            section_level = int(hierarchy_level)
        except Exception:
            section_level = max(1, len(path) - 1) if path else 1
        section_type = clean_text(chunk.get("section_type")) or clean_text(chunk.get("chunk_type")) or "text_section"
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        block_ids = [item for item in (chunk.get("block_ids") or []) if item]
        key = section_id
        if key not in sections:
            order.append(key)
            sections[key] = {
                "section_key": key,
                "section_id": section_id,
                "parent_section_id": parent_section_id or None,
                "section_title": title,
                "section_path": path,
                "section_level": section_level,
                "section_type": section_type,
                "seq_start": int(chunk.get("seq_no") or len(order)),
                "seq_end": int(chunk.get("seq_no") or len(order)),
                "page_start": page_start,
                "page_end": page_end,
                "chunk_keys": [],
                "block_ids": [],
                "metadata": {
                    "profile": profile,
                    "document_title": document_title,
                    "chunk_group_id": chunk.get("chunk_group_id"),
                    "business_block_id": metadata.get("business_block_id"),
                    "business_block_title": metadata.get("business_block_title"),
                    "confidence": metadata.get("confidence") or "INFERRED",
                },
            }
        section = sections[key]
        section["seq_start"] = min(int(section["seq_start"]), int(chunk.get("seq_no") or section["seq_start"]))
        section["seq_end"] = max(int(section["seq_end"]), int(chunk.get("seq_no") or section["seq_end"]))
        if page_start is not None:
            section["page_start"] = page_start if section.get("page_start") is None else min(section["page_start"], page_start)
        if page_end is not None:
            section["page_end"] = page_end if section.get("page_end") is None else max(section["page_end"], page_end)
        if chunk.get("chunk_key"):
            section["chunk_keys"].append(chunk["chunk_key"])
        for block_id in block_ids:
            if block_id not in section["block_ids"]:
                section["block_ids"].append(block_id)

    return [sections[key] for key in order]


def build_sections_from_mapped_sections(
    mapped_sections: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    document_title: str,
    profile: str,
) -> list[dict[str, Any]]:
    """Build the first-class section tree from catalog mapping output.

    Catalog mapping is the authority for hierarchy. Chunks are evidence attached
    to sections, not the source of truth for the section tree.
    """
    if not mapped_sections:
        return build_sections_from_chunks(chunks, document_title=document_title, profile=profile)

    chunks_by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        section_id = clean_text(chunk.get("section_id"))
        if section_id:
            chunks_by_section[section_id].append(chunk)
    for rows in chunks_by_section.values():
        rows.sort(key=lambda item: int(item.get("seq_no") or 0))

    sections: list[dict[str, Any]] = []
    for index, mapped in enumerate(mapped_sections, 1):
        section_hash_source = f"{document_title}:{index}:{mapped.get('title') or ''}"
        section_id = clean_text(mapped.get("section_id")) or f"section_{stable_hash(section_hash_source, 16)}"
        section_chunks = chunks_by_section.get(section_id, [])
        chunk_keys = [chunk.get("chunk_key") for chunk in section_chunks if chunk.get("chunk_key")]
        seq_values = [int(chunk.get("seq_no") or 0) for chunk in section_chunks if chunk.get("seq_no")]
        section_path = [clean_text(item) for item in (mapped.get("section_path") or []) if clean_text(item)]
        if not section_path:
            title = clean_text(mapped.get("title")) or document_title
            section_path = [document_title, title] if title != document_title else [document_title]
        block_ids = [item for item in (mapped.get("block_ids") or []) if item]
        sections.append(
            {
                "section_key": section_id,
                "section_id": section_id,
                "parent_section_id": clean_text(mapped.get("parent_section_id")) or None,
                "section_title": clean_text(mapped.get("title")) or section_path[-1],
                "section_path": section_path,
                "section_level": int(mapped.get("section_level") or mapped.get("level") or max(1, len(section_path) - 1)),
                "section_type": clean_text(mapped.get("section_type")) or "text_section",
                "seq_start": min(seq_values) if seq_values else index,
                "seq_end": max(seq_values) if seq_values else index,
                "page_start": mapped.get("page_start"),
                "page_end": mapped.get("page_end"),
                "chunk_keys": chunk_keys,
                "block_ids": block_ids,
                "metadata": {
                    "profile": profile,
                    "document_title": document_title,
                    "source": "catalog_mapped_sections",
                    "catalog_candidate_id": mapped.get("candidate_id"),
                    "title_source": mapped.get("title_source"),
                    "mapping_confidence": mapped.get("mapping_confidence"),
                    "start_char": mapped.get("start_char"),
                    "end_char": mapped.get("end_char"),
                    "start_block_id": mapped.get("start_block_id"),
                    "end_block_id": mapped.get("end_block_id"),
                    "confidence": "EXTRACTED",
                },
            }
        )
    return sections


def build_section_summaries(
    sections: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    summary_source: str = "llm",
    profile: str | None = None,
    parse_options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    chunks_by_key = {chunk.get("chunk_key"): chunk for chunk in chunks}
    sections_by_id = {str(section.get("section_id")): section for section in sections if section.get("section_id")}
    children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in sections:
        section_id = clean_text(section.get("section_id"))
        parent_id = clean_text(section.get("parent_section_id"))
        if parent_id and parent_id != section_id:
            children_by_parent[parent_id].append(section)
    for rows in children_by_parent.values():
        rows.sort(key=lambda item: (int(item.get("seq_start") or 0), str(item.get("section_id") or "")))

    summaries_by_section: dict[str, dict[str, Any]] = {}
    client: JsonChatClient | None = None
    max_chars = max(1000, _int_option(parse_options, "summary.max_section_input_chars", 12000))
    max_evidence_quotes = max(1, _int_option(parse_options, "summary.max_evidence_quotes", 20))
    thresholds = _summary_quality_thresholds(parse_options)

    def collect_descendant_section_ids(section_id: str, visited: set[str] | None = None) -> set[str]:
        visited = set(visited or set())
        if section_id in visited:
            return set()
        visited.add(section_id)
        result: set[str] = set()
        for child in children_by_parent.get(section_id, []):
            child_id = clean_text(child.get("section_id"))
            if not child_id or child_id in visited:
                continue
            result.add(child_id)
            result.update(collect_descendant_section_ids(child_id, visited))
        return result

    def collect_child_summaries(section_id: str, visited: set[str] | None = None) -> list[dict[str, Any]]:
        visited = set(visited or set())
        if section_id in visited:
            return []
        visited.add(section_id)
        collected: list[dict[str, Any]] = []
        for child in children_by_parent.get(section_id, []):
            child_id = str(child.get("section_id") or "")
            if not child_id or child_id in visited:
                continue
            child_summary = summaries_by_section.get(child_id)
            if child_summary:
                collected.append(child_summary)
            else:
                collected.extend(collect_child_summaries(child_id, visited))
        return collected

    ordered_sections = sorted(
        sections,
        key=lambda item: (-_section_level(item), -(int(item.get("seq_start") or 0))),
    )
    for section in ordered_sections:
        if not _summary_level_allowed(section, parse_options):
            continue
        section_chunks = [chunks_by_key[key] for key in section.get("chunk_keys") or [] if key in chunks_by_key]
        child_summaries = collect_child_summaries(str(section.get("section_id") or ""))
        fallback = _script_section_summary(
            section,
            section_chunks,
            child_summaries=child_summaries,
            summary_source="script_fallback" if summary_source == "llm" else summary_source,
            max_evidence_quotes=max_evidence_quotes,
        )
        selected = fallback
        if summary_source == "llm":
            try:
                if client is None:
                    client = JsonChatClient("SUMMARY", default_model=True)
                llm_summary = _llm_section_summary(
                    client,
                    section,
                    section_chunks,
                    child_summaries=child_summaries,
                    profile=profile,
                    max_chars=max_chars,
                    max_evidence_quotes=max_evidence_quotes,
                )
                if llm_summary.get("node_summary"):
                    selected = llm_summary
            except Exception as exc:
                import logging
                _logger = logging.getLogger(__name__)
                _logger.error("LLM section summary failed for section %s (profile=%s): %s",
                              section.get("section_id"), profile, exc)
                warnings = fallback.get("quality_warnings") or []
                warnings.append(f"llm_summary_failed:{type(exc).__name__}")
                fallback["quality_warnings"] = warnings
        section_id = str(section.get("section_id") or "")
        selected = _attach_retrieval_summary_fields(
            selected,
            section=section,
            section_chunks=section_chunks,
            child_summaries=child_summaries,
        )
        selected = _attach_summary_quality(
            selected,
            section=section,
            direct_children=children_by_parent.get(section_id, []),
            descendant_section_ids=collect_descendant_section_ids(section_id),
            thresholds=thresholds,
        )
        summaries_by_section[section_id] = selected
    return [
        summaries_by_section[str(section.get("section_id"))]
        for section in sections
        if str(section.get("section_id")) in summaries_by_section and str(section.get("section_id")) in sections_by_id
    ]


def _script_section_summary(
    section: dict[str, Any],
    section_chunks: list[dict[str, Any]],
    *,
    child_summaries: list[dict[str, Any]] | None = None,
    summary_source: str,
    max_evidence_quotes: int = 20,
) -> dict[str, Any]:
    child_summaries = child_summaries or []
    chunk_summaries = [clean_text(chunk.get("summary")) for chunk in section_chunks if clean_text(chunk.get("summary"))]
    child_lines = [
        clean_text(f"{summary.get('section_title') or summary.get('section_id')}：{summary.get('node_summary')}")
        for summary in child_summaries
        if clean_text(summary.get("node_summary"))
    ]
    if child_lines:
        node_summary = clean_text("；".join(child_lines + chunk_summaries))[:1200]
    elif chunk_summaries:
        node_summary = clean_text("；".join(chunk_summaries))[:1200]
    else:
        joined = clean_text("\n".join(str(chunk.get("content") or "") for chunk in section_chunks))
        node_summary = joined[:1200]
    structured = _merge_structured_summaries(child_summaries)
    structured.update(
        {
            "section_type": section.get("section_type"),
            "chunk_count": len(section_chunks),
            "child_summary_count": len(child_summaries),
            "page_start": section.get("page_start"),
            "page_end": section.get("page_end"),
        }
    )
    evidence_quotes: list[dict[str, Any]] = []
    for summary in child_summaries:
        for evidence in summary.get("evidence_quotes") or []:
            if isinstance(evidence, dict):
                evidence_quotes.append({**evidence, "source_summary_section_id": summary.get("section_id")})
    if len(evidence_quotes) < max_evidence_quotes:
        for chunk in section_chunks:
            text = clean_text(chunk.get("content"))
            if not text:
                continue
            evidence_quotes.append(
                {
                    "quote": text[:160],
                    "chunk_key": chunk.get("chunk_key"),
                    "evidence_role": "source_quote",
                }
            )
            if len(evidence_quotes) >= max_evidence_quotes:
                break
    covered_chunk_keys = _dedupe(
        [chunk.get("chunk_key") for chunk in section_chunks if chunk.get("chunk_key")]
        + [key for summary in child_summaries for key in (summary.get("covered_chunk_keys") or [])]
    )
    covered_section_ids = _dedupe(
        [section.get("section_id")]
        + [section_id for summary in child_summaries for section_id in (summary.get("covered_section_ids") or [summary.get("section_id")])]
    )
    return {
        "section_id": section["section_id"],
        "section_title": section.get("section_title"),
        "section_path": section.get("section_path") or [],
        "section_level": section.get("section_level"),
        "summary_type": "node_summary",
        "node_summary": node_summary,
        "structured_summary": structured,
        "evidence_quotes": _normalize_evidence_quotes(evidence_quotes, limit=max_evidence_quotes),
        "covered_chunk_keys": covered_chunk_keys,
        "covered_section_ids": covered_section_ids,
        "child_section_ids": [summary.get("section_id") for summary in child_summaries if summary.get("section_id")],
        "summary_source": summary_source,
        "confidence": "medium" if node_summary else "low",
    }


def _llm_section_summary(
    client: JsonChatClient,
    section: dict[str, Any],
    section_chunks: list[dict[str, Any]],
    *,
    child_summaries: list[dict[str, Any]] | None,
    profile: str | None,
    max_chars: int,
    max_evidence_quotes: int,
) -> dict[str, Any]:
    child_summaries = child_summaries or []
    child_context_budget = max(1000, max_chars // 3)
    chunk_context_budget = max(1000, max_chars - child_context_budget)
    child_summary_text = format_summaries_for_prompt(
        child_summaries,
        max_items=40,
        max_chars=child_context_budget,
        max_summary_chars=500,
    )
    chunk_text = format_chunks_for_prompt(
        section_chunks,
        max_chars=chunk_context_budget,
        chunk_type=None,
        max_text_chars=4000,
    )
    user_prompt = f"""## Profile
{profile or ""}

## 当前章节
{json.dumps(section_prompt_item(section), ensure_ascii=False)}

## 输出 JSON Schema
{{
  "node_summary": "100-300字摘要。叶子章节概括本节原文；父级章节必须自底向上综合子级摘要，并用本级原文校正。",
  "structured_summary_json": {{
    "main_objects": [],
    "key_rules": [],
    "amounts_or_rates": [],
    "conditions": [],
    "process_steps": [],
    "references": [],
    "open_questions": []
  }},
  "evidence_quotes": [
    {{"quote": "原文短句", "chunk_key": "small_001_01", "evidence_role": "source_quote"}}
  ],
  "quality_notes": []
}}

## 已生成的子级摘要
{child_summary_text}

## 章节原文 chunks
{chunk_text}
"""
    payload = client.complete_json(SECTION_SUMMARY_SYSTEM_PROMPT, user_prompt, temperature=0)
    structured = payload.get("structured_summary_json") or payload.get("structured_summary") or {}
    if not isinstance(structured, dict):
        structured = {}
    evidence_quotes = payload.get("evidence_quotes") or []
    if not isinstance(evidence_quotes, list):
        evidence_quotes = []
    structured.setdefault("section_type", section.get("section_type"))
    structured.setdefault("chunk_count", len(section_chunks))
    structured.setdefault("child_summary_count", len(child_summaries))
    structured.setdefault("page_start", section.get("page_start"))
    structured.setdefault("page_end", section.get("page_end"))
    structured["quality_notes"] = payload.get("quality_notes") if isinstance(payload.get("quality_notes"), list) else []
    node_summary = clean_text(payload.get("node_summary"))[:1200]
    covered_chunk_keys = _dedupe(
        [chunk.get("chunk_key") for chunk in section_chunks if chunk.get("chunk_key")]
        + [key for summary in child_summaries for key in (summary.get("covered_chunk_keys") or [])]
    )
    covered_section_ids = _dedupe(
        [section.get("section_id")]
        + [section_id for summary in child_summaries for section_id in (summary.get("covered_section_ids") or [summary.get("section_id")])]
    )
    return {
        "section_id": section["section_id"],
        "section_title": section.get("section_title"),
        "section_path": section.get("section_path") or [],
        "section_level": section.get("section_level"),
        "summary_type": "node_summary",
        "node_summary": node_summary,
        "structured_summary": structured,
        "evidence_quotes": _normalize_evidence_quotes(evidence_quotes, limit=max_evidence_quotes),
        "covered_chunk_keys": covered_chunk_keys,
        "covered_section_ids": covered_section_ids,
        "child_section_ids": [summary.get("section_id") for summary in child_summaries if summary.get("section_id")],
        "summary_source": "llm",
        "confidence": "high" if node_summary else "low",
    }
