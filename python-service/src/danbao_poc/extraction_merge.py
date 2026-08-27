from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from danbao_poc.common import clean_text


def option_value(options: dict[str, Any] | None, names: list[str], default: Any) -> Any:
    for name in names:
        current: Any = options or {}
        found = True
        for part in name.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found:
            return current
    return default


def extraction_pass_count(options: dict[str, Any] | None, default: int = 1) -> int:
    value = option_value(options, ["extraction.extraction_passes", "extraction_passes"], default)
    try:
        return max(1, min(3, int(value)))
    except Exception:
        return default


def merge_overlaps_enabled(options: dict[str, Any] | None, default: bool = True) -> bool:
    value = option_value(options, ["extraction.merge_overlaps", "merge_overlaps"], default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def confidence_rank(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value).upper()
    return {"HIGH": 3.0, "MEDIUM": 2.0, "LOW": 1.0}.get(text, 0.0)


def _compact(text: str) -> str:
    return "".join(clean_text(text).lower().split())


def text_overlap_ratio(left: str, right: str) -> float:
    left_compact = _compact(left)
    right_compact = _compact(right)
    if not left_compact or not right_compact:
        return 0.0
    if left_compact in right_compact or right_compact in left_compact:
        return 1.0
    match = SequenceMatcher(None, left_compact, right_compact).find_longest_match(0, len(left_compact), 0, len(right_compact))
    return match.size / max(1, min(len(left_compact), len(right_compact)))


def _record_key(record: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    return tuple(clean_text(record.get(field)) for field in fields)


def _record_text(record: dict[str, Any], fields: list[str]) -> str:
    return clean_text("\n".join(clean_text(record.get(field)) for field in fields if clean_text(record.get(field))))


def _record_score(record: dict[str, Any]) -> tuple[float, int]:
    text = _record_text(record, ["evidence_quote", "object_text", "value_text", "name"])
    return (confidence_rank(record.get("confidence")), len(text))


def _record_overlap(left: dict[str, Any], right: dict[str, Any], fields: list[str]) -> float:
    scores = [
        text_overlap_ratio(clean_text(left.get(field)), clean_text(right.get(field)))
        for field in fields
        if clean_text(left.get(field)) and clean_text(right.get(field))
    ]
    if scores:
        return max(scores)
    return text_overlap_ratio(_record_text(left, fields), _record_text(right, fields))


def merge_pass_record_lists(
    record_lists: list[list[dict[str, Any]]],
    *,
    exact_fields: list[str],
    group_fields: list[str],
    text_fields: list[str],
    merge_overlaps: bool = True,
    overlap_threshold: float = 0.72,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    def merge_lists(lists: list[list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], int, int]:
        local_merged: list[dict[str, Any]] = []
        local_exact_keys: set[tuple[str, ...]] = set()
        local_exact_dropped = 0
        local_overlap_dropped = 0

        for pass_index, records in enumerate(lists, 1):
            for record in records:
                if not isinstance(record, dict):
                    continue
                item = dict(record)
                item["_extraction_pass"] = pass_index
                exact_key = _record_key(item, exact_fields)
                if exact_key in local_exact_keys:
                    local_exact_dropped += 1
                    continue
                group_key = _record_key(item, group_fields)
                item_text = _record_text(item, text_fields)
                replaced = False
                if merge_overlaps and item_text:
                    for index, existing in enumerate(local_merged):
                        if _record_key(existing, group_fields) != group_key:
                            continue
                        existing_text = _record_text(existing, text_fields)
                        if existing_text and _record_overlap(existing, item, text_fields) >= overlap_threshold:
                            if _record_score(item) > _record_score(existing):
                                local_merged[index] = item
                            local_overlap_dropped += 1
                            replaced = True
                            break
                if replaced:
                    local_exact_keys.add(exact_key)
                    continue
                local_merged.append(item)
                local_exact_keys.add(exact_key)
        return local_merged, local_exact_dropped, local_overlap_dropped

    merged, exact_dropped, overlap_dropped = merge_lists(record_lists)
    first_merged, _, _ = merge_lists(record_lists[:1]) if record_lists else ([], 0, 0)
    first_pass_count = len(first_merged)
    report = {
        "pass_count": len(record_lists),
        "field_count": len(merged),
        "newly_added_count": max(0, len(merged) - first_pass_count),
        "exact_dropped_count": exact_dropped,
        "overlap_dropped_count": overlap_dropped,
    }
    for item in merged:
        item.pop("_extraction_pass", None)
    return merged, report
