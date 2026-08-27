from __future__ import annotations

import math
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from .common import clean_text


_ENTROPY_THRESHOLD = 1.2
_FUZZY_CANDIDATE_THRESHOLD = 0.88
_AUTO_ACCEPT_THRESHOLD = 0.94
_MINHASH_PERMUTATIONS = 32
_MINHASH_BAND_SIZE = 4


def _norm(label: str) -> str:
    """Graphify-style label normalization, adapted to keep Chinese text."""
    value = clean_text(label).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def _entropy(label: str) -> float:
    normalized = _norm(label)
    if not normalized:
        return 0.0
    counts: dict[str, int] = defaultdict(int)
    for char in normalized:
        counts[char] += 1
    size = len(normalized)
    return -sum((count / size) * math.log2(count / size) for count in counts.values())


def _shingles(text: str) -> set[str]:
    normalized = _norm(text)
    if not normalized:
        return set()
    k = 2 if len(normalized) <= 6 else 3
    if len(normalized) <= k:
        return {normalized}
    return {normalized[i : i + k] for i in range(len(normalized) - k + 1)}


def _similarity(left: str, right: str) -> float:
    left_norm = _norm(left)
    right_norm = _norm(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if (left_norm in right_norm or right_norm in left_norm) and min(len(left_norm), len(right_norm)) >= 4:
        return 0.9
    left_shingles = _shingles(left_norm)
    right_shingles = _shingles(right_norm)
    jaccard = len(left_shingles & right_shingles) / max(1, len(left_shingles | right_shingles))
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(jaccard, sequence)


def _stable_hash_int(value: str) -> int:
    # FNV-1a keeps MinHash deterministic without external dependencies.
    result = 2166136261
    for char in value:
        result ^= ord(char)
        result = (result * 16777619) & 0xFFFFFFFF
    return result


def _minhash_signature(shingles: set[str], permutations: int = _MINHASH_PERMUTATIONS) -> tuple[int, ...]:
    if not shingles:
        return tuple()
    signature: list[int] = []
    for seed in range(permutations):
        signature.append(min(_stable_hash_int(f"{seed}:{shingle}") for shingle in shingles))
    return tuple(signature)


def _lsh_candidate_pairs(anchors: list[dict[str, Any]]) -> set[tuple[int, int]]:
    buckets: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    normalized_names: list[str] = []
    for index, anchor in enumerate(anchors):
        name = str(anchor.get("anchor_name") or anchor.get("normalized_name") or "")
        normalized = _norm(name)
        normalized_names.append(normalized)
        signature = _minhash_signature(_shingles(normalized))
        if not signature:
            continue
        for band_start in range(0, len(signature), _MINHASH_BAND_SIZE):
            band = signature[band_start : band_start + _MINHASH_BAND_SIZE]
            if len(band) == _MINHASH_BAND_SIZE:
                buckets[(band_start // _MINHASH_BAND_SIZE, band)].append(index)

    pairs: set[tuple[int, int]] = set()
    for indexes in buckets.values():
        if len(indexes) <= 1:
            continue
        for left_pos, left_index in enumerate(indexes):
            for right_index in indexes[left_pos + 1 :]:
                pairs.add((min(left_index, right_index), max(left_index, right_index)))

    for left_index, left_name in enumerate(normalized_names):
        for right_index in range(left_index + 1, len(normalized_names)):
            right_name = normalized_names[right_index]
            if not left_name or not right_name:
                continue
            if (left_name in right_name or right_name in left_name) and abs(len(left_name) - len(right_name)) <= 6:
                pairs.add((left_index, right_index))
    return pairs


def _pick_winner(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    def _score(anchor: dict[str, Any]) -> tuple[float, int, int]:
        anchor_type_rank = 0 if anchor.get("anchor_type") == "primary" else 1
        confidence = float(anchor.get("confidence") or 0)
        return (-confidence, anchor_type_rank, len(str(anchor.get("anchor_id") or "")))

    return min(anchors, key=_score)


def _merge_into(winner: dict[str, Any], duplicate: dict[str, Any]) -> None:
    aliases = [clean_text(item) for item in (winner.get("aliases") or []) if clean_text(item)]
    duplicate_aliases = [clean_text(item) for item in (duplicate.get("aliases") or []) if clean_text(item)]
    duplicate_name = clean_text(duplicate.get("anchor_name"))
    for item in [duplicate_name, *duplicate_aliases]:
        if item and item != winner.get("anchor_name") and item not in aliases:
            aliases.append(item)
    winner["aliases"] = aliases
    winner["confidence"] = max(float(winner.get("confidence") or 0), float(duplicate.get("confidence") or 0))

    metadata = winner.setdefault("metadata", {})
    duplicate_metadata = duplicate.get("metadata") if isinstance(duplicate.get("metadata"), dict) else {}
    raw_ids = list(metadata.get("raw_anchor_ids") or [])
    for item in [metadata.get("raw_anchor_id"), duplicate_metadata.get("raw_anchor_id"), *(duplicate_metadata.get("raw_anchor_ids") or [])]:
        item = clean_text(item)
        if item and item not in raw_ids:
            raw_ids.append(item)
    metadata["raw_anchor_ids"] = raw_ids

    merged_ids = list(metadata.get("dedup_merged_anchor_ids") or [])
    duplicate_id = clean_text(duplicate.get("anchor_id"))
    if duplicate_id and duplicate_id not in merged_ids:
        merged_ids.append(duplicate_id)
    metadata["dedup_merged_anchor_ids"] = merged_ids

    quotes = list(metadata.get("merged_evidence_quotes") or [])
    for quote in [winner.get("evidence_quote"), duplicate.get("evidence_quote")]:
        quote = clean_text(quote)
        if quote and quote not in quotes:
            quotes.append(quote)
    metadata["merged_evidence_quotes"] = quotes
    metadata["dedup_source"] = "graphify_exact_norm"


def deduplicate_anchors(
    anchors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    """Deduplicate normalized duplicate anchors before registry insertion.

    This mirrors graphify's deterministic stages: exact normalized grouping first,
    entropy-gated fuzzy candidate discovery second, then survivor remapping.
    Fuzzy matches are annotated for review instead of merged automatically.
    """
    if len(anchors) <= 1:
        return anchors, {}, []

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        normalized = _norm(anchor.get("anchor_name") or anchor.get("normalized_name") or "")
        if normalized:
            groups[normalized].append(anchor)

    remap: dict[str, str] = {}
    warnings: list[str] = []
    removed_ids: set[str] = set()

    for normalized, group in groups.items():
        if len(group) <= 1:
            continue
        winner = _pick_winner(group)
        winner_id = str(winner.get("anchor_id") or "")
        for duplicate in group:
            duplicate_id = str(duplicate.get("anchor_id") or "")
            if not duplicate_id or duplicate_id == winner_id:
                continue
            _merge_into(winner, duplicate)
            remap[duplicate_id] = winner_id
            removed_ids.add(duplicate_id)
        warnings.append(f"anchor_dedup_exact:{normalized}:{len(group) - 1}")

    survivors = [anchor for anchor in anchors if str(anchor.get("anchor_id") or "") not in removed_ids]
    high_entropy = [
        anchor
        for anchor in survivors
        if _entropy(str(anchor.get("anchor_name") or anchor.get("normalized_name") or "")) >= _ENTROPY_THRESHOLD
    ]
    for left_index, right_index in sorted(_lsh_candidate_pairs(high_entropy)):
        left = high_entropy[left_index]
        left_name = str(left.get("anchor_name") or "")
        right = high_entropy[right_index]
        right_name = str(right.get("anchor_name") or "")
        score = _similarity(left_name, right_name)
        if score < _FUZZY_CANDIDATE_THRESHOLD:
            continue
        left_meta = left.setdefault("metadata", {})
        right_meta = right.setdefault("metadata", {})
        decision = "auto_accept" if score >= _AUTO_ACCEPT_THRESHOLD and left.get("anchor_type") == right.get("anchor_type") else "pending_review"
        candidate_reason = "graphify_minhash_lsh_candidate"
        left_meta.setdefault("dedup_candidates", []).append(
            {"anchor_id": right.get("anchor_id"), "anchor_name": right_name, "score": round(score, 4), "decision": decision, "reason": candidate_reason}
        )
        right_meta.setdefault("dedup_candidates", []).append(
            {"anchor_id": left.get("anchor_id"), "anchor_name": left_name, "score": round(score, 4), "decision": decision, "reason": candidate_reason}
        )
        warnings.append(f"anchor_dedup_candidate:{left_name}:{right_name}:{round(score, 4)}")

    for anchor in survivors:
        anchor["normalized_name"] = _norm(anchor.get("anchor_name") or anchor.get("normalized_name") or "")
    return survivors, remap, warnings


def extract_anchor_merge_candidates(
    anchors: list[dict[str, Any]],
    *,
    kb_id: int,
    file_node_id: int,
    parse_generation: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    by_id = {str(anchor.get("anchor_id") or ""): anchor for anchor in anchors}
    for anchor in anchors:
        anchor_id = str(anchor.get("anchor_id") or "")
        metadata = anchor.get("metadata") if isinstance(anchor.get("metadata"), dict) else {}
        for candidate in metadata.get("dedup_candidates") or []:
            other_id = str(candidate.get("anchor_id") or "")
            if not anchor_id or not other_id:
                continue
            left_id, right_id = sorted([anchor_id, other_id])
            key = (left_id, right_id)
            if key in seen:
                continue
            seen.add(key)
            left = by_id.get(left_id) or {}
            right = by_id.get(right_id) or {}
            score = float(candidate.get("score") or 0.0)
            decision = str(candidate.get("decision") or "")
            if not decision:
                decision = "auto_accept" if score >= _AUTO_ACCEPT_THRESHOLD and left.get("anchor_type") == right.get("anchor_type") else "pending_review"
            rows.append(
                {
                    "kb_id": kb_id,
                    "file_node_id": file_node_id,
                    "parse_generation": parse_generation,
                    "left_anchor_id": left_id,
                    "right_anchor_id": right_id,
                    "left_anchor_name": left.get("anchor_name"),
                    "right_anchor_name": right.get("anchor_name"),
                    "left_anchor_type": left.get("anchor_type"),
                    "right_anchor_type": right.get("anchor_type"),
                    "similarity_score": round(score, 4),
                    "similarity_reason": candidate.get("reason") or "graphify_fuzzy_candidate",
                    "decision": decision,
                    "status": "pending" if decision == "pending_review" else "auto_accepted",
                    "metadata": {
                        "left_normalized_name": left.get("normalized_name"),
                        "right_normalized_name": right.get("normalized_name"),
                    },
                }
            )
    return rows
