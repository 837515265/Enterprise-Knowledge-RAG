from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .chunk_generation import build_multigranularity_chunks, representative_text_for_embedding
from .chunker_common import embedding_text
from .common import clean_text, normalize_html_text, stable_hash
from .openai_compat import JsonChatClient
from .prompt_views import build_catalog_window_text
from .profiles.prompt_templates import catalog_section_types_for_profile


@dataclass
class CatalogBuildResult:
    chunks: list[dict[str, Any]]
    catalog_artifact: dict[str, Any]
    warnings: list[str]


def _option(options: dict[str, Any] | None, path: str, default: Any) -> Any:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _int_option(options: dict[str, Any] | None, path: str, default: int) -> int:
    try:
        return int(_option(options, path, default))
    except Exception:
        return default


def _float_option(options: dict[str, Any] | None, path: str, default: float) -> float:
    try:
        return float(_option(options, path, default))
    except Exception:
        return default


def _flatten_blocks(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for page in middle_document.get("pages") or []:
        page_no = page.get("page_no")
        for block in page.get("blocks") or []:
            text = normalize_html_text(block.get("text") or block.get("markdown"))
            if not text:
                continue
            item = dict(block)
            item["page_no"] = item.get("page_no") or page_no
            item["text"] = text
            blocks.append(item)
    return sorted(blocks, key=lambda row: (row.get("page_no") or 0, row.get("order") or 0, row.get("block_id") or ""))


def build_merged_text(middle_document: dict[str, Any]) -> dict[str, Any]:
    """Build the 4.2 merged text and block-level char map."""
    blocks = _flatten_blocks(middle_document)
    parts: list[str] = []
    spans: list[dict[str, Any]] = []
    for block in blocks:
        text = clean_text(block.get("text"))
        if not text:
            continue
        if parts:
            parts.append("\n")
        start = sum(len(part) for part in parts)
        parts.append(text)
        end = start + len(text)
        spans.append(
            {
                "global_char_start": start,
                "global_char_end": end,
                "block_id": block.get("block_id"),
                "page_no": block.get("page_no"),
                "bbox": block.get("bbox") or [],
                "block_type": block.get("type") or block.get("block_type"),
                "block_label": block.get("label"),
                "text": text,
            }
        )
    merged_text = "".join(parts)
    return {"merged_text": merged_text, "char_map": {"text_version": "merged_v1", "spans": spans}, "blocks": blocks}


def _window_spans(spans: list[dict[str, Any]], *, budget_chars: int, overlap_blocks: int) -> list[list[dict[str, Any]]]:
    windows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_len = 0
    for span in spans:
        text_len = len(str(span.get("text") or "")) + 1
        if current and current_len + text_len > budget_chars:
            windows.append(current)
            current = current[-overlap_blocks:] if overlap_blocks > 0 else []
            current_len = sum(len(str(item.get("text") or "")) + 1 for item in current)
        current.append(span)
        current_len += text_len
    if current:
        windows.append(current)
    return windows or [[]]


def _compact_window(spans: list[dict[str, Any]], max_chars: int) -> str:
    return build_catalog_window_text(spans, max_chars)


HEADING_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("markdown_h1", re.compile(r"^#{1}\s+(.{1,120})$"), 1),
    ("markdown_h2", re.compile(r"^#{2}\s+(.{1,120})$"), 2),
    ("markdown_h3", re.compile(r"^#{3,6}\s+(.{1,120})$"), 3),
    ("chapter", re.compile(r"^(第[一二三四五六七八九十百零〇0-9]+章)\s*(.{0,80})$"), 1),
    ("section", re.compile(r"^(第[一二三四五六七八九十百零〇0-9]+节)\s*(.{0,80})$"), 2),
    ("article", re.compile(r"^(第[一二三四五六七八九十百零〇0-9]+条)\s*(.{0,100})$"), 3),
    ("appendix", re.compile(r"^(附件\s*[一二三四五六七八九十百零〇0-9]*)(?:[：:、.\s]*(.{0,100}))?$"), 1),
    ("cn_top", re.compile(r"^([一二三四五六七八九十百零〇]+[、.．])\s*(.{1,100})$"), 1),
    ("cn_paren", re.compile(r"^(（[一二三四五六七八九十百零〇]+）)\s*(.{1,100})$"), 2),
    ("num_dot", re.compile(r"^([0-9]{1,2}[.．、])\s*(.{1,50})$"), 3),
    ("num_multi", re.compile(r"^([0-9]{1,2}(?:\.[0-9]{1,2})+[.．]?)\s*(.{1,100})$"), 3),
]


_LIST_ITEM_PUNCT = set("、，；《》（）():：;.,")  # punctuation that indicates a list item, not a heading
_HEADING_LABELS = {"title", "paragraph_title", "doc_title", "heading"}
_BUSINESS_PLAN_NUM_DOT_HEADING_KEYWORDS = {
    "服务对象",
    "支持对象",
    "适用范围",
    "业务范围",
    "准入条件",
    "准入要求",
    "申请条件",
    "额度",
    "额度测算",
    "授信额度",
    "担保额度",
    "期限",
    "贷款期限",
    "授信用途",
    "贷款用途",
    "资金用途",
    "费率",
    "担保费",
    "反担保",
    "风险缓释",
    "风险控制",
    "申请材料",
    "资料清单",
    "流程",
    "操作流程",
    "办理流程",
}


def _normalized_label(label: str | None) -> str:
    return clean_text(label).lower()


def _is_heading_label(label: str | None) -> bool:
    return _normalized_label(label) in _HEADING_LABELS


def _is_probable_num_dot_body_item(title: str, *, label: str | None, profile: str | None, content_role: str | None) -> bool:
    """Detect numbered body-list items that should not become catalog headings."""
    normalized_profile = clean_text(profile or "")
    if content_role == "appendix":
        return False
    if _is_heading_label(label):
        return False
    if normalized_profile not in {"business_plan", "guarantee_plan"}:
        return False
    text = clean_text(title)
    if not text:
        return True
    if any(ch in _LIST_ITEM_PUNCT for ch in text):
        return True
    if len(text) > 24:
        return True
    return not any(keyword in text for keyword in _BUSINESS_PLAN_NUM_DOT_HEADING_KEYWORDS)


def _heading_from_line(line: str, label: str | None = None, profile: str | None = None, content_role: str | None = None) -> tuple[str, int, str] | None:
    text = clean_text(line)
    if not text or len(text) > 160:
        return None
    for numbering_type, pattern, level in HEADING_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        title = clean_text("".join(part for part in match.groups() if part))
        # Reject num_dot matches that look like list items (contain sentence-level punctuation)
        if numbering_type == "num_dot" and any(ch in _LIST_ITEM_PUNCT for ch in title):
            continue
        if numbering_type == "num_dot" and _is_probable_num_dot_body_item(title, label=label, profile=profile, content_role=content_role):
            continue
        return title or text, level, numbering_type
    if _is_heading_label(label) and len(text) <= 120:
        if not text.startswith("|"):
            return text, 1, "layout_title"
    return None


def _content_role_for_title(title: str, section_type: str | None = None) -> str:
    text = clean_text(title)
    section_type = clean_text(section_type)
    if section_type in {"appendix", "table_template"}:
        return "appendix"
    if re.match(r"^附件\s*[一二三四五六七八九十百零〇0-9]*", text):
        return "appendix"
    if any(word in text for word in ["推荐函", "调查表", "承诺函", "资料清单", "模板"]):
        return "appendix"
    return "main_body"


def _extract_heading_candidates(
    spans: list[dict[str, Any]],
    parse_options: dict[str, Any] | None = None,
    profile: str | None = None,
) -> list[dict[str, Any]]:
    max_candidates = max(20, _int_option(parse_options, "chunking.max_heading_candidates", 260))
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for span in spans:
        text = str(span.get("text") or "")
        if not text:
            continue
        label = span.get("block_label") or span.get("block_type")
        offset = 0
        for raw_line in text.splitlines() or [text]:
            line = clean_text(raw_line)
            found_at = text.find(raw_line, offset)
            if found_at < 0:
                found_at = offset
            offset = found_at + len(raw_line)
            provisional_role = _content_role_for_title(line)
            parsed = _heading_from_line(line, str(label or ""), profile=profile, content_role=provisional_role)
            if not parsed:
                continue
            title, level_guess, numbering_type = parsed
            start_char = int(span.get("global_char_start") or 0) + found_at
            key = (start_char, title)
            if key in seen:
                continue
            seen.add(key)
            candidate_id = f"h_{len(candidates) + 1:05d}"
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "text": line,
                    "title": title,
                    "level_guess": level_guess,
                    "numbering_type": numbering_type,
                    "start_char": start_char,
                    "end_char": start_char + len(line),
                    "page_no": span.get("page_no"),
                    "block_id": span.get("block_id"),
                    "block_type": span.get("block_type"),
                    "content_role": _content_role_for_title(title),
                    "confidence": 0.9 if numbering_type != "layout_title" else 0.72,
                }
            )
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def _candidate_prompt_rows(candidates: list[dict[str, Any]], *, start_char: int, end_char: int, max_items: int = 80) -> str:
    rows: list[str] = []
    for item in candidates:
        pos = int(item.get("start_char") or 0)
        if pos < start_char or pos >= end_char:
            continue
        rows.append(
            {
                "candidate_id": item.get("candidate_id"),
                "text": item.get("text"),
                "title": item.get("title"),
                "level_guess": item.get("level_guess"),
                "numbering_type": item.get("numbering_type"),
                "page_no": item.get("page_no"),
                "block_id": item.get("block_id"),
                "content_role": item.get("content_role"),
            }
        )
        if len(rows) >= max_items:
            break
    return json_dumps_compact(rows)


def json_dumps_compact(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _partial_catalog_context(sections: list[dict[str, Any]], max_items: int = 30) -> str:
    if not sections:
        return "无"
    rows: list[str] = []
    for item in sections[-max_items:]:
        rows.append(
            f"- level={item.get('level')} title={item.get('title')} "
            f"type={item.get('section_type') or 'text_section'} "
            f"candidate_id={item.get('candidate_id') or ''} anchor={item.get('start_anchor') or ''}"
        )
    return "\n".join(rows)


def _merge_partial_catalogs(partials: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for partial_index, partial in enumerate(partials, 1):
        for item in partial.get("sections") or []:
            if not isinstance(item, dict):
                continue
            anchor = clean_text(item.get("start_anchor"))
            candidate_id = clean_text(item.get("candidate_id"))
            title = clean_text(item.get("title"))
            if not anchor and not candidate_id:
                continue
            dedupe_key = (candidate_id or "".join(anchor.split()), "".join(title.split()))
            if dedupe_key in seen:
                duplicate_count += 1
                continue
            seen.add(dedupe_key)
            merged.append({**item, "partial_index": partial_index})
    return merged, {
        "partial_count": len(partials),
        "merged_node_count": len(merged),
        "overlap_duplicate_count": duplicate_count,
    }


CATALOG_SYSTEM_PROMPT = """你是企业知识库 RAG-Doc 的目录规划模型。
你的唯一核心任务是根据文档文本识别真实层级目录。不要回答问题，不要输出 chunk 正文。

必须遵守：
1. 只输出 JSON object，不要输出 Markdown。
2. 每个目录节点只输出 candidate_id、level、title、title_source、section_type、confidence；只有没有候选标题可用时才补充 start_anchor。
3. candidate_id 必须优先来自输入的 heading_candidates；不要编造 candidate_id。
4. 如果原文有真实标题，title_source=explicit；如果是语义标题，title_source=inferred。
5. 不要输出 block_id、page_no、bbox、数据库 id。
6. 不要省略附件、表格、接口、错误码、关键条款。
7. 同名标题不能简单合并；例如多个"准入条件"要分别输出。
8. 正文列表项不是目录标题；例如"1. xxx；""7. xxx，"通常属于上级标题正文，不要输出为 section。
9. section_type 只是辅助分类；无法稳定判断时写 text_section，不能为了分类改变目录层级。
10. 如果文档开头有目录页（章节标题列表+页码，非正文），请在 toc_range 字段中输出目录的起止字符位置。没有目录则省略此字段。
"""


def _llm_catalog(
    profile: str,
    merged_text: str,
    spans: list[dict[str, Any]],
    parse_options: dict[str, Any] | None,
    heading_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    budget = max(3000, _int_option(parse_options, "chunking.catalog_window_chars", 19000))
    overlap = max(0, _int_option(parse_options, "chunking.catalog_overlap_blocks", 8))
    windows = _window_spans(spans, budget_chars=budget, overlap_blocks=overlap)
    client = JsonChatClient("CATALOG", default_model=True)
    partials: list[dict[str, Any]] = []
    previous_sections: list[dict[str, Any]] = []
    for index, window in enumerate(windows, 1):
        window_start = min((int(span.get("global_char_start") or 0) for span in window), default=0)
        window_end = max((int(span.get("global_char_end") or 0) for span in window), default=len(merged_text))
        candidate_context = _candidate_prompt_rows(heading_candidates, start_char=window_start, end_char=window_end)
        window_candidate_count = sum(1 for item in heading_candidates if window_start <= int(item.get("start_char") or 0) < window_end)
        window_text = _compact_window(window, budget)
        rolling_guidance = ""
        if len(windows) > 1:
            rolling_guidance = f"""## 已有目录摘要
{_partial_catalog_context(previous_sections)}

## 滚动窗口要求
1. 如果当前窗口开头承接上一个窗口的章节，不要重复输出已经出现过的目录节点，除非当前窗口出现新的真实标题。
2. 如果当前窗口继续展开上一窗口最后一个父级章节，请保持 level 连续，不要把子级误提成一级。
3. overlap 区域中的重复标题只保留一次。
"""
        user_prompt = f"""## 目录规划目标
只识别真实目录层级。正文编号条目、条件清单、流程步骤、长句列表都必须保留在上级 section 正文中，不要拆成 section。

当前 profile: {profile}

## 当前窗口
window_index: {index}
window_count: {len(windows)}
char_range: {window_start}-{window_end}

{rolling_guidance}

## 输出 JSON Schema
{{
  "sections": [...],
  "toc_range": {{"start_char": 0, "end_char": 800}},
  "warnings": []
}}
注：toc_range 只在当前窗口开头有目录页时输出，标识目录的起止字符位置。

## heading_candidates
{candidate_context}

## 文档窗口文本
{window_text}
"""
        payload = client.complete_json(CATALOG_SYSTEM_PROMPT, user_prompt, temperature=0, max_tokens=4000)
        payload.setdefault("prompt_view", {"window_index": index, "char_range": [window_start, window_end], "heading_candidate_count": window_candidate_count})
        partials.append(payload)
        previous_sections.extend([item for item in payload.get("sections") or [] if isinstance(item, dict)])
    merged, merge_report = _merge_partial_catalogs(partials)
    partials.append({"catalog_merge_report": merge_report})
    return merged, partials


def _compact_with_map(text: str) -> tuple[str, list[int]]:
    compact_chars: list[str] = []
    index_map: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        compact_chars.append(char)
        index_map.append(index)
    return "".join(compact_chars), index_map


def _best_fuzzy_position(
    merged_text: str,
    *,
    anchor: str,
    title: str,
    lower_bound: int,
    search_window_chars: int,
) -> tuple[int | None, str, float]:
    query = clean_text(anchor) or clean_text(title)
    if not query:
        return None, "missing_anchor", 0.0
    query_compact = "".join(query.split())
    if len(query_compact) < 4:
        return None, "anchor_too_short", 0.0
    start = max(0, lower_bound - 120)
    end = min(len(merged_text), lower_bound + search_window_chars)
    best: tuple[float, int, str] = (0.0, -1, "fuzzy")
    pattern_len = min(max(len(query), 8), 120)
    candidate_text = merged_text[start:end]
    lines = candidate_text.splitlines(keepends=True)
    offset = start
    for line in lines:
        line_text = clean_text(line)
        if line_text:
            if query in line_text:
                return offset + line.find(query), "line_contains_anchor", 0.88
            ratio = SequenceMatcher(None, query_compact, "".join(line_text.split())).ratio()
            if ratio > best[0]:
                best = (ratio, offset + max(0, line.find(line_text[: min(len(line_text), pattern_len)])), "fuzzy_line")
            title_text = clean_text(title)
            if title_text:
                title_ratio = SequenceMatcher(None, "".join(title_text.split()), "".join(line_text.split())).ratio()
                if title_ratio > best[0]:
                    best = (title_ratio, offset + max(0, line.find(line_text[: min(len(line_text), pattern_len)])), "fuzzy_title")
        offset += len(line)
    if best[0] >= 0.72 and best[1] >= 0:
        return best[1], best[2], best[0]
    return None, "not_found", best[0]


def _locate_anchor(
    merged_text: str,
    anchor: str,
    lower_bound: int,
    *,
    title: str = "",
    search_window_chars: int = 6000,
) -> tuple[int | None, str, float]:
    anchor = clean_text(anchor)
    if not anchor:
        return None, "missing_anchor", 0.0
    pos = merged_text.find(anchor, max(0, lower_bound))
    if pos >= 0:
        return pos, "exact", 1.0
    compact_anchor = "".join(anchor.split())
    compact_text, compact_map = _compact_with_map(merged_text)
    compact_pos = compact_text.find(compact_anchor) if compact_anchor else -1
    if compact_pos >= 0:
        original_pos = compact_map[compact_pos] if compact_pos < len(compact_map) else None
        if original_pos is not None and original_pos >= max(0, lower_bound - 120):
            return original_pos, "normalized_exact", 0.94
    return _best_fuzzy_position(
        merged_text,
        anchor=anchor,
        title=title,
        lower_bound=lower_bound,
        search_window_chars=search_window_chars,
    )


def _spans_for_range(spans: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    return [
        span
        for span in spans
        if int(span.get("global_char_end") or 0) > start and int(span.get("global_char_start") or 0) < end
    ]


def _compact_key(value: Any) -> str:
    return "".join(clean_text(value).split()).lower()


def _candidate_matches_catalog_item(candidate: dict[str, Any], item: dict[str, Any]) -> bool:
    title = _compact_key(item.get("title"))
    anchor = _compact_key(item.get("start_anchor"))
    candidate_title = _compact_key(candidate.get("title"))
    candidate_text = _compact_key(candidate.get("text"))
    if not title and not anchor:
        return True
    probes = [value for value in [title, anchor] if value]
    targets = [value for value in [candidate_title, candidate_text] if value]
    for probe in probes:
        for target in targets:
            if probe == target or probe in target or target in probe:
                return True
            if len(probe) >= 6 and len(target) >= 6 and SequenceMatcher(None, probe, target).ratio() >= 0.82:
                return True
    return False


def _validate_catalog(
    catalog: list[dict[str, Any]],
    *,
    allowed_section_types: set[str] | None = None,
    candidate_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    cleaned: list[dict[str, Any]] = []
    duplicate_keys: set[tuple[str, str]] = set()
    duplicate_count = 0
    parsed_count = 0
    last_level = 0
    for index, raw in enumerate(catalog, 1):
        if not isinstance(raw, dict):
            warnings.append(f"catalog_node_invalid_type:{index}")
            continue
        try:
            level = int(raw.get("level") or 0)
        except Exception:
            level = 0
        title = clean_text(raw.get("title"))
        candidate_id = clean_text(raw.get("candidate_id"))
        candidate = (candidate_by_id or {}).get(candidate_id) if candidate_id else None
        if not title and candidate:
            title = clean_text(candidate.get("title") or candidate.get("text"))
        anchor = clean_text(raw.get("start_anchor"))
        if not anchor and candidate:
            anchor = clean_text(candidate.get("text") or candidate.get("title"))
        title_source = clean_text(raw.get("title_source")) or "inferred"
        if level <= 0:
            warnings.append(f"catalog_node_invalid_level:{index}:{title}")
            continue
        if last_level and level > last_level + 1:
            warnings.append(f"catalog_level_jump:{last_level}->{level}:{title}")
            level = last_level + 1
        if not title:
            warnings.append(f"catalog_node_missing_title:{index}")
            continue
        if not anchor and not candidate_id:
            warnings.append(f"catalog_node_missing_anchor:{title}")
            continue
        if title_source not in {"explicit", "inferred", "explicit_heading", "numbered_heading", "semantic_heading"}:
            warnings.append(f"catalog_node_invalid_title_source:{title}:{title_source}")
            title_source = "inferred"
        normalized_source = "explicit" if title_source in {"explicit", "explicit_heading", "numbered_heading"} else "inferred"
        section_type = clean_text(raw.get("section_type")) or "text_section"
        if allowed_section_types and section_type not in allowed_section_types:
            warnings.append(f"catalog_section_type_out_of_profile:{title}:{section_type}")
            section_type = "text_section"
        key = (candidate_id or anchor, title)
        if key in duplicate_keys:
            duplicate_count += 1
            warnings.append(f"catalog_duplicate_node:{title}")
        else:
            duplicate_keys.add(key)
        parsed_count += 1
        last_level = level
        cleaned.append(
            {
                **raw,
                "candidate_id": candidate_id,
                "level": level,
                "title": title,
                "start_anchor": anchor,
                "title_source": normalized_source,
                "section_type": section_type,
                "confidence": raw.get("confidence"),
            }
        )
    quality = {
        "raw_node_count": len(catalog),
        "valid_node_count": len(cleaned),
        "duplicate_node_count": duplicate_count,
        "node_parse_success_rate": parsed_count / max(len(catalog), 1),
    }
    if len(catalog) > 0 and len(cleaned) <= 1:
        warnings.append("catalog_node_count_too_low")
    return cleaned, warnings, quality


def _coverage_estimate(mapped: list[dict[str, Any]], merged_text: str) -> dict[str, Any]:
    ranges: list[tuple[int, int]] = []
    for item in mapped:
        start = int(item.get("start_char") or 0)
        end = int(item.get("end_char") or start)
        if end > start:
            ranges.append((max(0, start), min(len(merged_text), end)))
    ranges.sort()
    merged_ranges: list[tuple[int, int]] = []
    for start, end in ranges:
        if not merged_ranges or start > merged_ranges[-1][1]:
            merged_ranges.append((start, end))
        else:
            merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], end))
    covered = sum(end - start for start, end in merged_ranges)
    text_len = len(merged_text)
    gaps: list[dict[str, int]] = []
    cursor = 0
    for start, end in merged_ranges:
        if start > cursor:
            gaps.append({"start_char": cursor, "end_char": start, "length": start - cursor})
        cursor = max(cursor, end)
    if cursor < text_len:
        gaps.append({"start_char": cursor, "end_char": text_len, "length": text_len - cursor})
    return {
        "merged_text_length": text_len,
        "covered_chars": covered,
        "coverage_estimate": covered / max(text_len, 1),
        "range_count": len(merged_ranges),
        "large_gaps": [gap for gap in gaps if gap["length"] >= 500][:20],
    }


def _validate_mapped_structure(mapped: list[dict[str, Any]], merged_text: str) -> tuple[list[str], dict[str, Any]]:
    warnings: list[str] = []
    title_only_count = 0
    overlap_count = 0
    parent_violation_count = 0
    invalid_page_count = 0
    previous: dict[str, Any] | None = None
    by_section_id = {item.get("section_id"): item for item in mapped if item.get("section_id")}
    for item in mapped:
        start = int(item.get("start_char") or 0)
        end = int(item.get("end_char") or start)
        title = clean_text(item.get("title"))
        content = clean_text(merged_text[start:end])
        if previous and start < int(previous.get("end_char") or 0) and int(item.get("level") or 1) <= int(previous.get("level") or 1):
            overlap_count += 1
            warnings.append(f"mapped_section_overlap:{title}")
        if content and len(content) <= len(title) + 8:
            title_only_count += 1
            warnings.append(f"mapped_title_only_section:{title}")
        if item.get("page_start") is not None and item.get("page_end") is not None and int(item["page_start"]) > int(item["page_end"]):
            invalid_page_count += 1
            warnings.append(f"mapped_invalid_page_range:{title}")
        parent_id = item.get("parent_section_id")
        parent = by_section_id.get(parent_id)
        if parent:
            parent_start = int(parent.get("start_char") or 0)
            parent_end = int(parent.get("end_char") or 0)
            if start < parent_start or end > parent_end:
                parent_violation_count += 1
                warnings.append(f"mapped_parent_range_violation:{title}")
        previous = item
    coverage = _coverage_estimate(mapped, merged_text)
    if coverage["coverage_estimate"] < 0.8:
        warnings.append(f"mapped_coverage_low:{coverage['coverage_estimate']:.4f}")
    report = {
        **coverage,
        "section_count": len(mapped),
        "title_only_count": title_only_count,
        "overlap_count": overlap_count,
        "parent_violation_count": parent_violation_count,
        "invalid_page_count": invalid_page_count,
        "structure_warning_count": len(warnings),
    }
    return warnings, report


def _drop_title_only_leaf_sections(mapped: list[dict[str, Any]], merged_text: str) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    child_parent_ids = {item.get("parent_section_id") for item in mapped if item.get("parent_section_id")}
    cleaned: list[dict[str, Any]] = []
    warnings: list[str] = []
    dropped = 0
    for item in mapped:
        start = int(item.get("start_char") or 0)
        end = int(item.get("end_char") or start)
        title = clean_text(item.get("title"))
        content = clean_text(merged_text[start:end])
        is_title_only = bool(content) and len(content) <= len(title) + 8
        if is_title_only and item.get("section_id") not in child_parent_ids:
            dropped += 1
            warnings.append(f"catalog_title_only_leaf_dropped:{title}")
            continue
        cleaned.append(item)
    return cleaned, warnings, {"title_only_leaf_dropped_count": dropped}


def _is_protected_span(span: dict[str, Any]) -> bool:
    protected = {"table", "table_body", "table_caption", "code", "formula", "list", "numbered_clause_group", "appendix_table"}
    block_type = clean_text(span.get("block_type") or span.get("block_label")).lower()
    if block_type in protected:
        return True
    text = clean_text(span.get("text"))
    compact = text.replace(" ", "")
    if "<table" in text.lower() or "</table>" in text.lower():
        return True
    if text.count("|") >= 2 or text.count("\t") >= 2:
        return True
    if re.match(r"^(附件|附表)\s*[0-9一二三四五六七八九十]*", compact):
        return True
    return False


def _protected_block_ranges(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for span in spans:
        if not _is_protected_span(span):
            continue
        block_id = clean_text(span.get("block_id")) or clean_text(span.get("span_id"))
        if not block_id:
            continue
        start = int(span.get("global_char_start") or 0)
        end = int(span.get("global_char_end") or start)
        if end <= start:
            continue
        row = grouped.setdefault(
            block_id,
            {
                "block_id": block_id,
                "start": start,
                "end": end,
                "block_type": clean_text(span.get("block_type") or span.get("block_label")).lower(),
            },
        )
        row["start"] = min(int(row["start"]), start)
        row["end"] = max(int(row["end"]), end)
    return sorted(grouped.values(), key=lambda row: (int(row["start"]), int(row["end"])))


def _adjust_protected_block_boundaries(mapped: list[dict[str, Any]], spans: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    adjusted = [dict(item) for item in mapped]
    adjusted_count = 0
    warnings: list[str] = []
    for protected_range in _protected_block_ranges(spans):
        block_start = int(protected_range["start"])
        block_end = int(protected_range["end"])
        overlaps: list[tuple[int, int]] = []
        for index, item in enumerate(adjusted):
            start = int(item.get("start_char") or 0)
            end = int(item.get("end_char") or 0)
            overlap = max(0, min(end, block_end) - max(start, block_start))
            if overlap > 0:
                overlaps.append((index, overlap))
        if len(overlaps) <= 1:
            continue
        winner_index = max(overlaps, key=lambda row: row[1])[0]
        winner = adjusted[winner_index]
        winner["start_char"] = min(int(winner.get("start_char") or block_start), block_start)
        winner["end_char"] = max(int(winner.get("end_char") or block_end), block_end)
        for index, _overlap in overlaps:
            if index == winner_index:
                continue
            item = adjusted[index]
            start = int(item.get("start_char") or 0)
            end = int(item.get("end_char") or 0)
            if start < block_start < end <= block_end:
                item["end_char"] = block_start
            elif block_start <= start < block_end < end:
                item["start_char"] = block_end
            elif block_start <= start and end <= block_end:
                item["end_char"] = start
        adjusted_count += 1
        warnings.append(f"protected_block_boundary_adjusted:{protected_range['block_id']}")
    adjusted = [item for item in adjusted if int(item.get("end_char") or 0) > int(item.get("start_char") or 0)]
    return adjusted, warnings, {"protected_block_adjusted_count": adjusted_count}


def _validate_protected_block_boundaries(mapped: list[dict[str, Any]], spans: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    section_hits_by_block: dict[str, set[str]] = {}
    protected_ranges = _protected_block_ranges(spans)
    for protected_range in protected_ranges:
        block_id = protected_range["block_id"]
        span_start = int(protected_range["start"])
        span_end = int(protected_range["end"])
        for item in mapped:
            start = int(item.get("start_char") or 0)
            end = int(item.get("end_char") or 0)
            if span_end > start and span_start < end:
                section_hits_by_block.setdefault(block_id, set()).add(str(item.get("section_id") or item.get("title")))
    split_blocks = {block_id: section_ids for block_id, section_ids in section_hits_by_block.items() if len(section_ids) > 1}
    warnings = [f"protected_block_crosses_sections:{block_id}" for block_id in sorted(split_blocks)]
    return warnings, {
        "protected_block_count": len(protected_ranges),
        "protected_block_split_count": len(split_blocks),
        "protected_block_split_ids": sorted(split_blocks)[:50],
    }


def _detect_toc_end(merged_text: str, spans: list[dict[str, Any]]) -> int:
    """Detect table-of-contents pages and return the char position after them.

    TOC pages contain many chapter/article markers (第X章, 第X条) in a
    compact region. Actual content has these markers spread across pages.
    """
    import re
    TOC_MARKER = re.compile(r'第[一二三四五六七八九十百零\d]+[章节条]')
    # Sample the first 3000 chars to detect TOC density
    sample_end = min(3000, len(merged_text))
    sample = merged_text[:sample_end]
    markers = TOC_MARKER.findall(sample)
    if len(markers) < 5:
        return 0  # Not enough markers for a TOC

    # Find where the markers become sparse — that's the TOC boundary
    # Group markers by their character position
    marker_positions = [m.start() for m in TOC_MARKER.finditer(sample)]
    if not marker_positions:
        return 0

    # Find the largest gap between consecutive markers
    max_gap = 0
    gap_end = 0
    for i in range(1, len(marker_positions)):
        gap = marker_positions[i] - marker_positions[i - 1]
        if gap > max_gap:
            max_gap = gap
            gap_end = marker_positions[i]

    # If there's a significant gap (>500 chars), assume TOC ends at the gap
    if max_gap > 500:
        return gap_end

    # If markers are very dense in a small region (<2000 chars for >10 markers), that's TOC
    if len(markers) > 10 and (marker_positions[-1] - marker_positions[0]) < 2000:
        # TOC ends at the last marker of the dense cluster
        return marker_positions[-1] + 100  # small buffer

    return 0


def _map_catalog(
    catalog: list[dict[str, Any]],
    merged: dict[str, Any],
    document_title: str,
    profile: str,
    parse_options: dict[str, Any] | None,
    candidate_by_id: dict[str, dict[str, Any]] | None = None,
    start_offset: int = 0,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    merged_text = merged.get("merged_text") or ""
    spans = merged.get("char_map", {}).get("spans") or []
    warnings: list[str] = []
    mapped: list[dict[str, Any]] = []
    lower_bound = start_offset
    search_window_chars = max(1000, _int_option(parse_options, "chunking.anchor_search_window_chars", 6000))
    for item in catalog:
        candidate = (candidate_by_id or {}).get(clean_text(item.get("candidate_id")))
        if candidate and _candidate_matches_catalog_item(candidate, item):
            start = int(candidate.get("start_char") or 0)
            method = "candidate_id"
            confidence = float(candidate.get("confidence") or 0.95)
            if start < max(0, lower_bound - 120):
                warnings.append(f"catalog_candidate_out_of_order:{item.get('title')}:{item.get('candidate_id')}")
                continue
        else:
            if candidate:
                warnings.append(f"catalog_candidate_title_mismatch:{item.get('title')}:{item.get('candidate_id')}")
            start, method, confidence = _locate_anchor(
                merged_text,
                str(item.get("start_anchor") or item.get("title") or ""),
                lower_bound,
                title=str(item.get("title") or ""),
                search_window_chars=search_window_chars,
            )
        if start is None:
            warnings.append(f"catalog_anchor_not_found:{item.get('title')}")
            continue
        lower_bound = start + 1
        mapped.append({**item, "start_char": start, "anchor_match_method": method, "anchor_match_confidence": confidence})
    mapped.sort(key=lambda row: int(row.get("start_char") or 0))
    for index, item in enumerate(mapped):
        level = max(1, int(item.get("level") or 1))
        end = len(merged_text)
        for next_item in mapped[index + 1 :]:
            next_level = max(1, int(next_item.get("level") or 1))
            if next_level <= level:
                end = int(next_item.get("start_char") or end)
                break
        item["end_char"] = max(int(item.get("start_char") or 0), end)

    mapped, protected_adjust_warnings, protected_adjust_report = _adjust_protected_block_boundaries(mapped, spans)
    warnings.extend(protected_adjust_warnings)

    stack: list[dict[str, Any]] = []
    for index, item in enumerate(mapped, 1):
        level = max(1, int(item.get("level") or 1))
        while stack and int(stack[-1].get("level") or 1) >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        section_path = list(parent.get("section_path") or []) if parent else [document_title]
        title = clean_text(item.get("title")) or clean_text(item.get("start_anchor"))[:80]
        if not section_path or section_path[-1] != title:
            section_path.append(title)
        content_role = _content_role_for_title(" > ".join(str(value) for value in section_path), item.get("section_type"))
        start = int(item.get("start_char") or 0)
        end = int(item.get("end_char") or start)
        covered = _spans_for_range(spans, start, end)
        pages = [span.get("page_no") for span in covered if span.get("page_no") is not None]
        section_id = f"section_{stable_hash(f'{profile}:{index}:{start}:{title}', 16)}"
        item.update(
            {
                "section_id": section_id,
                "parent_section_id": parent.get("section_id") if parent else None,
                "section_path": section_path,
                "section_level": level,
                "content_role": content_role,
                "start_block_id": covered[0].get("block_id") if covered else None,
                "end_block_id": covered[-1].get("block_id") if covered else None,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "block_ids": [span.get("block_id") for span in covered if span.get("block_id")],
                "bbox": [span.get("bbox") for span in covered if span.get("bbox")],
                "mapping_confidence": min(float(item.get("anchor_match_confidence") or 0.3), 0.96) if covered else 0.3,
            }
        )
        stack.append(item)
    mapped, drop_warnings, drop_report = _drop_title_only_leaf_sections(mapped, merged_text)
    warnings.extend(drop_warnings)
    structure_warnings, structure_report = _validate_mapped_structure(mapped, merged_text)
    warnings.extend(structure_warnings)
    protected_warnings, protected_report = _validate_protected_block_boundaries(mapped, spans)
    warnings.extend(protected_warnings)
    return mapped, warnings, {**structure_report, **drop_report, **protected_adjust_report, **protected_report}


def _chunks_from_mapped_sections(mapped: list[dict[str, Any]], merged: dict[str, Any], document_title: str, profile: str) -> list[dict[str, Any]]:
    merged_text = merged.get("merged_text") or ""
    chunks: list[dict[str, Any]] = []
    parent_ids = {item.get("parent_section_id") for item in mapped if item.get("parent_section_id")}
    for index, section in enumerate(mapped, 1):
        if section.get("section_id") in parent_ids:
            continue
        start = int(section.get("start_char") or 0)
        end = int(section.get("end_char") or start)
        content = clean_text(merged_text[start:end])
        if not content:
            continue
        title = clean_text(section.get("title")) or clean_text(content[:80])
        title_path = section.get("section_path") or [document_title, title]
        metadata = {
            "profile": profile,
            "document_title": document_title,
            "section_path": title_path,
            "parent_section_id": section.get("parent_section_id"),
            "title_source": section.get("title_source"),
            "start_anchor": section.get("start_anchor"),
            "start_char": start,
            "end_char": end,
            "start_block_id": section.get("start_block_id"),
            "end_block_id": section.get("end_block_id"),
            "mapping_confidence": section.get("mapping_confidence"),
            "catalog_source": "llm_catalog",
            "content_role": section.get("content_role") or _content_role_for_title(" > ".join(str(item) for item in title_path), section.get("section_type")),
            "source_catalog_candidate_id": section.get("candidate_id"),
        }
        chunks.append(
            {
                "chunk_key": f"catalog_{index:03d}",
                "seq_no": index,
                "chunk_type": "catalog_section",
                "section_type": section.get("section_type") or "text_section",
                "section_id": section.get("section_id"),
                "chunk_group_id": f"section:{section.get('section_id')}",
                "title": title,
                "title_path": title_path,
                "content": content,
                "summary": content[:180],
                "content_hash": stable_hash(content, 40),
                "content_for_embedding": embedding_text(document_title, " > ".join(str(item) for item in title_path), content),
                "content_for_bm25": clean_text(f"{' '.join(str(item) for item in title_path)} {content}"),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
                "block_ids": section.get("block_ids") or [],
                "bbox": section.get("bbox") or [],
                "metadata": metadata,
            }
        )
    return chunks


def _raw_fallback_chunks(merged: dict[str, Any], document_title: str, profile: str, parse_options: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Fallback chunker: split by heading candidates + page boundaries.

    When LLM catalog fails and script catalog also fails, we don't collapse to one chunk.
    Instead, use detected heading positions and page breaks to split the document into
    reasonable sections.
    """
    merged_text = clean_text(merged.get("merged_text") or "")
    if not merged_text:
        return []
    spans = merged.get("char_map", {}).get("spans") or []

    # Collect split points from heading candidates and page boundaries
    heading_candidates = _extract_heading_candidates(spans, parse_options, profile=profile)
    split_points: set[int] = {0, len(merged_text)}
    for hc in heading_candidates:
        start = hc.get("start_char")
        if start is not None and 0 < start < len(merged_text):
            split_points.add(start)

    # Add page boundaries as split points
    last_page = None
    for span in sorted(spans, key=lambda s: s.get("start_char", 0)):
        page = span.get("page_no")
        if page is not None and page != last_page:
            last_page = page
            split_points.add(span.get("start_char", 0))

    split_points = sorted(split_points)

    # Build chunks between split points
    chunks: list[dict[str, Any]] = []
    seq_no = 0
    max_chars = max(500, _int_option(parse_options, "chunking.raw_fallback_chunk_chars", 3000))
    page_map = _build_page_map(spans)

    for i in range(len(split_points) - 1):
        start = split_points[i]
        end = split_points[i + 1]
        content = merged_text[start:end].strip()
        if not content:
            continue

        # Merge consecutive short segments
        while i + 2 < len(split_points) and len(content) < 200:
            end = split_points[i + 2]
            content = merged_text[start:end].strip()
            i += 1

        # Split long segments further by paragraphs
        sub_chunks = _split_by_paragraphs(content, max_chars) if len(content) > max_chars else [content]

        for sub_idx, sub_content in enumerate(sub_chunks):
            seq_no += 1
            covered = _spans_for_range(spans, start, end)
            pages = sorted({s.get("page_no") for s in covered if s.get("page_no") is not None})
            title = _infer_section_title(sub_content, heading_candidates, start, end) or f"第{seq_no}段"
            chunks.append({
                "chunk_key": f"fallback_{seq_no:03d}",
                "seq_no": seq_no,
                "chunk_type": "original",
                "section_type": _infer_section_type_for_profile(title, sub_content, "", profile),
                "section_id": f"fallback_section_{seq_no:03d}",
                "chunk_group_id": f"fallback:section_{seq_no:03d}",
                "title": title,
                "title_path": [document_title, title],
                "content": sub_content,
                "summary": sub_content[:300],
                "content_hash": stable_hash(sub_content, 40),
                "content_for_embedding": embedding_text(document_title, title, representative_text_for_embedding(sub_content)),
                "content_for_bm25": clean_text(f"{document_title} {title} {sub_content}"),
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "block_ids": [s.get("block_id") for s in covered if s.get("block_id")],
                "bbox": [s.get("bbox") for s in covered if s.get("bbox")],
                "metadata": {
                    "profile": profile,
                    "document_title": document_title,
                    "section_path": [document_title, title],
                    "start_char": start,
                    "end_char": end,
                    "catalog_source": "heading_fallback",
                    "confidence": "INFERRED",
                },
            })
    return chunks


def _build_page_map(spans: list[dict[str, Any]]) -> dict[int, int]:
    """Build a mapping from char position to page number."""
    pmap: dict[int, int] = {}
    for span in spans:
        page = span.get("page_no")
        if page is not None:
            pmap[span.get("start_char", 0)] = page
    return pmap


def _infer_section_title(content: str, heading_candidates: list[dict[str, Any]], start: int, end: int) -> str | None:
    """Find the nearest heading candidate that overlaps with this content range."""
    best = None
    for hc in heading_candidates:
        hc_start = hc.get("start_char", 0)
        if start <= hc_start < end:
            text = clean_text(hc.get("text") or hc.get("title") or "")
            if text:
                best = text[:100]
                break
    return best


def _split_by_paragraphs(content: str, max_chars: int) -> list[str]:
    """Split content by paragraph breaks, merging short paragraphs."""
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    if not paragraphs:
        return [content]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks or [content]


def _infer_section_type_for_profile(title: str, content: str, content_role: str, profile: str) -> str:
    allowed = set(catalog_section_types_for_profile(profile))
    text = clean_text(f"{title}\n{content[:800]}")
    if profile == "sql_analytics":
        # The SQL analytics profile accepts ordinary Markdown.  Classification
        # is deliberately based on the section's visible evidence rather than
        # requiring governed object ids or exact metadata fields.
        if "verified_sql" in allowed and ("参考 SQL" in text or "参考SQL" in text):
            return "verified_sql"
        if "metric" in allowed and any(
            marker in text
            for marker in ("聚合方式", "SQL表达式", "固定过滤条件", "指标口径", "计算口径")
        ):
            return "metric"
        if "verified_sql" in allowed and re.search(r"(?is)(?:```sql\s*)?\bselect\b.{1,600}\bfrom\b", text):
            return "verified_sql"
        if "field" in allowed and (
            re.search(r"(^|[\n#])\s*字段(?:定义|清单|说明)?\s*$", text)
            or ("| 字段 |" in text and "| 中文名 |" in text)
            or ("物理表" in text and "字段" in text)
        ):
            return "field"
        if "table" in allowed and any(marker in text for marker in ("物理表", "表结构", "主键", "切片字段")):
            return "table"
        if "enum" in allowed and any(marker in text for marker in ("枚举值", "允许取值", "状态取值")):
            return "enum"
        if "dimension" in allowed and any(marker in text for marker in ("分析维度", "分组维度", "维度字段")):
            return "dimension"
        if "term" in allowed and any(marker in text for marker in ("别名：", "别名:", "关联字段：", "业务域：")):
            return "term"
        if "time_rule" in allowed and any(
            marker in text
            for marker in ("时间规则", "自然月", "自然年", "同比口径", "环比口径", "数据截止日")
        ):
            return "time_rule"
        return "text_section"
    if content_role == "appendix" or re.search(r"附件\s*[一二三四五六七八九十百零〇0-9]*|附表|资料清单|推荐函|模板", text):
        return "appendix" if "appendix" in allowed else "text_section"
    rules = [
        ("service_object", ["服务对象", "支持对象", "客户范围", "适用主体"]),
        ("business_scope", ["业务范围", "适用范围", "产业范围", "区域范围", "业务模式"]),
        ("admission_requirement", ["准入条件", "准入要求", "申请条件", "基本条件", "客户准入"]),
        ("credit_limit", ["授信额度", "担保额度", "贷款额度", "额度测算", "单户额度", "总授信额度"]),
        ("guarantee_term", ["授信期限", "担保期限", "贷款期限", "还款方式", "期限"]),
        ("credit_purpose", ["贷款用途", "授信用途", "资金用途", "用途"]),
        ("fee_rate", ["担保费率", "担保费收取", "费率", "收费标准", "收费"]),
        ("counter_guarantee", ["反担保", "抵押", "质押", "保证措施"]),
        ("risk_mitigation", ["风险缓释", "风险控制", "风险分担", "贷后管理", "保后管理"]),
        ("material_requirement", ["申请材料", "资料清单", "所需材料"]),
        ("procedure", ["办理流程", "操作流程", "业务流程", "审批流程", "流程", "程序"]),
        ("cooperation_org", ["合作机构", "职责分工", "参与主体"]),
        ("general_principle", ["总则", "原则"]),
        ("applicable_scope", ["适用范围", "适用对象"]),
        ("responsibility_clause", ["职责", "权限", "负责"]),
        ("procedure_clause", ["流程", "程序", "审批", "办理"]),
        ("effective_clause", ["生效", "施行", "废止", "解释权"]),
        ("requirement", ["需求", "业务需求", "功能需求"]),
        ("architecture", ["架构", "总体设计", "系统架构"]),
        ("module_design", ["模块", "功能设计", "详细设计"]),
        ("api_spec", ["接口", "API", "请求参数", "响应参数"]),
        ("db_table", ["数据库", "数据表", "表结构"]),
        ("config_item", ["配置", "参数"]),
    ]
    for section_type, keywords in rules:
        if section_type in allowed and any(keyword in text for keyword in keywords):
            return section_type
    if "document_meta" in allowed and any(keyword in text for keyword in ["通知", "方案名称", "文号", "背景", "目标", "依据"]):
        return "document_meta"
    return "text_section"


def _classify_mapped_sections(mapped: list[dict[str, Any]], merged: dict[str, Any], profile: str) -> tuple[list[dict[str, Any]], list[str]]:
    merged_text = merged.get("merged_text") or ""
    warnings: list[str] = []
    classified: list[dict[str, Any]] = []
    for section in mapped:
        start = int(section.get("start_char") or 0)
        end = int(section.get("end_char") or start)
        content = clean_text(merged_text[start:end])
        inferred = _infer_section_type_for_profile(
            clean_text(section.get("title")),
            content,
            clean_text(section.get("content_role")),
            profile,
        )
        old_type = clean_text(section.get("section_type")) or "text_section"
        row = {**section, "section_type": inferred}
        if old_type not in {"", "text_section"} and old_type != inferred:
            warnings.append(f"section_type_reclassified:{section.get('title')}:{old_type}->{inferred}")
        classified.append(row)
    return classified, warnings


def _catalog_from_heading_candidates(candidates: list[dict[str, Any]], profile: str) -> list[dict[str, Any]]:

    catalog: list[dict[str, Any]] = []
    for candidate in candidates:
        title = clean_text(candidate.get("title") or candidate.get("text"))
        if not title:
            continue
        catalog.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "level": max(1, int(candidate.get("level_guess") or 1)),
                "title": title,
                "start_anchor": clean_text(candidate.get("text") or title),
                "title_source": "explicit",
                "section_type": _infer_section_type_for_profile(title, "", clean_text(candidate.get("content_role")), profile),
                "confidence": candidate.get("confidence") or 0.72,
            }
        )
    return catalog


def _supplement_sql_analytics_headings(
    catalog: list[dict[str, Any]],
    heading_candidates: list[dict[str, Any]],
    merged_text: str,
) -> tuple[list[dict[str, Any]], int]:
    """Keep explicit Markdown knowledge sections even if the LLM omits one.

    The model remains responsible for the catalog plan.  This only restores
    source headings that are objective boundaries in the uploaded document;
    it does not require governed metadata or reject any loose section.
    """
    if not heading_candidates:
        return catalog, 0
    candidate_by_id = {
        clean_text(item.get("candidate_id")): item
        for item in heading_candidates
        if clean_text(item.get("candidate_id"))
    }
    used_ids = {
        clean_text(item.get("candidate_id"))
        for item in catalog
        if isinstance(item, dict) and clean_text(item.get("candidate_id")) in candidate_by_id
    }
    supplemented = list(catalog)
    for item in _catalog_from_heading_candidates(heading_candidates, "sql_analytics"):
        if clean_text(item.get("candidate_id")) not in used_ids:
            supplemented.append(item)

    def source_position(row: dict[str, Any]) -> int:
        candidate = candidate_by_id.get(clean_text(row.get("candidate_id")))
        if candidate:
            return int(candidate.get("start_char") or 0)
        anchor = clean_text(row.get("start_anchor")) or clean_text(row.get("title"))
        located = merged_text.find(anchor) if anchor else -1
        return located if located >= 0 else len(merged_text) + 1

    supplemented.sort(key=source_position)
    return supplemented, len(supplemented) - len(catalog)


def build_catalog_driven_chunks(
    middle_document: dict[str, Any],
    *,
    profile: str,
    document_title: str,
    parse_options: dict[str, Any] | None,
) -> CatalogBuildResult:
    merged = build_merged_text(middle_document)
    catalog_source = "llm_catalog"
    partials: list[dict[str, Any]] = []
    warnings: list[str] = []
    heading_candidates = _extract_heading_candidates(merged.get("char_map", {}).get("spans") or [], parse_options, profile=profile)
    candidate_by_id = {str(item.get("candidate_id")): item for item in heading_candidates if item.get("candidate_id")}
    try:
        catalog, partials = _llm_catalog(
            profile,
            merged.get("merged_text") or "",
            merged.get("char_map", {}).get("spans") or [],
            parse_options,
            heading_candidates,
        )
    except Exception as exc:
        # Retry on transport errors (model queue, timeout); skip retry on permanent errors
        from .openai_compat import ModelTransportError
        retry_delay = 600 if isinstance(exc, ModelTransportError) else 0
        if retry_delay > 0:
            import time
            warnings.append(f"llm_catalog_transport_error_retry_in_{retry_delay}s:{exc}")
            time.sleep(retry_delay)
            try:
                catalog, partials = _llm_catalog(
                    profile,
                    merged.get("merged_text") or "",
                    merged.get("char_map", {}).get("spans") or [],
                    parse_options,
                    heading_candidates,
                )
                warnings.append("llm_catalog_retry_succeeded")
            except Exception as retry_exc:
                warnings.append(f"llm_catalog_retry_failed:{retry_exc}")
                catalog = _catalog_from_heading_candidates(heading_candidates, profile)
                catalog_source = "script_heading_candidates" if catalog else "llm_catalog_failed"
        else:
            warnings.append(f"llm_catalog_failed:{exc}")
            catalog = _catalog_from_heading_candidates(heading_candidates, profile)
            catalog_source = "script_heading_candidates" if catalog else "llm_catalog_failed"

    if profile == "sql_analytics" and heading_candidates:
        catalog, supplemented_count = _supplement_sql_analytics_headings(
            catalog,
            heading_candidates,
            merged.get("merged_text") or "",
        )
        if supplemented_count:
            warnings.append(f"sql_analytics_explicit_headings_supplemented:{supplemented_count}")

    allowed_section_types = set(catalog_section_types_for_profile(profile))
    catalog, catalog_warnings, catalog_quality = _validate_catalog(
        catalog,
        allowed_section_types=allowed_section_types,
        candidate_by_id=candidate_by_id,
    )
    warnings.extend(catalog_warnings)
    # Use LLM-reported TOC range if available, fall back to heuristic
    toc_offset = 0
    for partial in partials:
        toc = partial.get("toc_range") if isinstance(partial.get("toc_range"), dict) else None
        if toc and isinstance(toc.get("end_char"), (int, float)):
            toc_offset = max(toc_offset, int(toc["end_char"]))
    if not toc_offset:
        toc_offset = _detect_toc_end(merged.get("merged_text") or "", merged.get("char_map", {}).get("spans") or [])
    if toc_offset > 0:
        warnings.append(f"toc_skipped_offset_{toc_offset}")
    mapped, map_warnings, structure_report = _map_catalog(catalog, merged, document_title, profile, parse_options, candidate_by_id, start_offset=toc_offset)
    warnings.extend(map_warnings)
    mapped, class_warnings = _classify_mapped_sections(mapped, merged, profile)
    warnings.extend(class_warnings)
    locate_rate = len(mapped) / max(len(catalog), 1)
    min_locate_rate = _float_option(parse_options, "chunking.anchor_locate_rate_threshold", 0.55)
    min_coverage = _float_option(parse_options, "chunking.coverage_threshold", 0.35)
    coverage = float(structure_report.get("coverage_estimate") or 0.0)
    locate_rate_low = locate_rate < min_locate_rate
    coverage_low = coverage < min_coverage
    should_fallback = (
        not mapped
        or coverage_low
        or (locate_rate_low and coverage < 0.8)
        or int(structure_report.get("parent_violation_count") or 0) > 0
    )
    if should_fallback and heading_candidates and catalog_source != "script_heading_candidates":
        script_catalog_raw = _catalog_from_heading_candidates(heading_candidates, profile)
        script_catalog, script_warnings, script_quality = _validate_catalog(
            script_catalog_raw,
            allowed_section_types=allowed_section_types,
            candidate_by_id=candidate_by_id,
        )
        script_mapped, script_map_warnings, script_structure = _map_catalog(
            script_catalog,
            merged,
            document_title,
            profile,
            parse_options,
            candidate_by_id,
            start_offset=toc_offset,
        )
        script_mapped, script_class_warnings = _classify_mapped_sections(script_mapped, merged, profile)
        script_locate_rate = len(script_mapped) / max(len(script_catalog), 1)
        script_coverage = float(script_structure.get("coverage_estimate") or 0.0)
        script_usable = bool(script_mapped) and script_locate_rate >= min_locate_rate and script_coverage >= min_coverage
        if script_usable:
            warnings.append("catalog_llm_low_quality_replaced_by_heading_candidates")
            warnings.extend(script_warnings)
            warnings.extend(script_map_warnings)
            warnings.extend(script_class_warnings)
            catalog = script_catalog
            mapped = script_mapped
            catalog_quality = {**catalog_quality, "llm_catalog_quality": catalog_quality, "script_catalog_quality": script_quality}
            structure_report = script_structure
            locate_rate = script_locate_rate
            coverage = script_coverage
            catalog_source = "script_heading_candidates"
            should_fallback = False
    if should_fallback:
        fallback_mode = "raw_chunk"
        fallback = _raw_fallback_chunks(merged, document_title, profile, parse_options)
        chunks = build_multigranularity_chunks(
            fallback,
            document_title=document_title,
            profile=profile,
            parse_options=parse_options,
        )
        return CatalogBuildResult(
            chunks=chunks,
            warnings=[*warnings, f"catalog_quality_low_fallback_to_{fallback_mode}"],
            catalog_artifact={
                "catalog_source": catalog_source,
                "fallback": fallback_mode,
                "fallback_reason": {
                    "locate_rate_below_threshold": locate_rate_low,
                    "coverage_below_threshold": coverage_low,
                    "parent_violation_count": int(structure_report.get("parent_violation_count") or 0),
                    "mapped_empty": not mapped,
                },
                "locate_rate": locate_rate,
                "quality": {**catalog_quality, **structure_report},
                "catalog": catalog,
                "mapped_sections": mapped,
                "heading_candidates": heading_candidates,
                "partials": partials,
                "merged_text_length": len(merged.get("merged_text") or ""),
            },
        )

    base_chunks = _chunks_from_mapped_sections(mapped, merged, document_title, profile)
    chunks = build_multigranularity_chunks(
        base_chunks,
        document_title=document_title,
        profile=profile,
        parse_options=parse_options,
    )
    return CatalogBuildResult(
        chunks=chunks,
        warnings=warnings,
        catalog_artifact={
            "catalog_source": catalog_source,
            "fallback": None,
            "locate_rate": locate_rate,
            "quality": {**catalog_quality, **structure_report},
            "catalog": catalog,
            "mapped_sections": mapped,
            "heading_candidates": heading_candidates,
            "partials": partials,
            "merged_text_length": len(merged.get("merged_text") or ""),
        },
    )
