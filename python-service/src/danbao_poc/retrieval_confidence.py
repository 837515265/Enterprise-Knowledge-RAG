"""Retrieval confidence scoring adapted from RAG-Pro.

RAG-Pro uses a simple and useful formula:
confidence = 0.6 * top_score + 0.4 * average_score.

This module keeps that core idea, then applies danbao-specific penalties for
missing answer context and product-scope mismatch.
"""

from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed < 0:
        return default
    return parsed


def _bounded_score(value: Any) -> float:
    score = _as_float(value, 0.0)
    return max(0.0, min(score, 1.0))


def _score_for_group(group: dict[str, Any]) -> float:
    details = group.get("score_details") if isinstance(group.get("score_details"), dict) else {}
    for key in ("rerank_normalized_score", "normalized_score", "original_fusion_score", "final_score"):
        if details.get(key) is not None:
            return _bounded_score(details.get(key))
    return _bounded_score(group.get("final_score") or group.get("rerank_score"))


def _iter_nested_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_nested_dicts(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_nested_dicts(item)


def _has_failed_evidence_alignment(group: dict[str, Any]) -> bool:
    for row in _iter_nested_dicts(group):
        alignment = row.get("evidence_alignment")
        if isinstance(alignment, dict) and str(alignment.get("status") or "").lower() == "failed":
            return True
        if str(row.get("evidence_alignment_status") or "").lower() == "failed":
            return True
    return False


def _has_evidence_text(group: dict[str, Any]) -> bool:
    for item in group.get("evidence_items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("evidence_text") or item.get("content") or item.get("title"):
            return True
    return bool(group.get("display_text") or group.get("answer_hint"))


def _penalty_factor(group: dict[str, Any]) -> tuple[float, list[str]]:
    factor = 1.0
    reasons: list[str] = []

    if _has_failed_evidence_alignment(group):
        factor *= 0.6
        reasons.append("evidence_alignment_failed")

    parent_context = group.get("parent_context") if isinstance(group.get("parent_context"), dict) else {}
    parent_enabled = bool(parent_context.get("enabled"))
    has_answer_context = bool(group.get("answer_context_chunk") or parent_context.get("answer_context_chunk_id"))
    if parent_enabled and not has_answer_context:
        factor *= 0.85
        reasons.append("parent_context_missing")

    if not _has_evidence_text(group):
        factor *= 0.75
        reasons.append("evidence_text_missing")

    details = group.get("score_details") if isinstance(group.get("score_details"), dict) else {}
    doc_match = details.get("document_match") if isinstance(details.get("document_match"), dict) else {}
    if doc_match.get("doc_name") and doc_match.get("original_score") is not None:
        anchors = doc_match.get("matched_anchors") or []
        penalty = _as_float(doc_match.get("document_mismatch_penalty"), 1.0)
        if penalty < 1.0 and not anchors:
            factor *= 0.2
            reasons.append("product_scope_mismatch")

    return max(0.0, min(factor, 1.0)), reasons


def confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.3:
        return "low"
    return "very_low"


def compute_retrieval_confidence(evidence_groups: list[dict[str, Any]], top_n: int = 5) -> dict[str, Any]:
    """Compute response-level confidence from final evidence groups.

    The score uses top evidence groups only, because low-ranked long-tail
    candidates should not dominate the user-visible confidence.
    """
    if not evidence_groups:
        return {
            "confidence": 0.0,
            "confidence_label": "very_low",
            "confidence_factors": {
                "score_count": 0,
                "base_confidence": 0.0,
                "penalty_factor": 1.0,
                "penalty_reasons": ["no_evidence"],
            },
        }

    selected = evidence_groups[: max(1, top_n)]
    scores = [_score_for_group(group) for group in selected]
    top_score = max(scores) if scores else 0.0
    average_score = sum(scores) / len(scores) if scores else 0.0
    base_confidence = max(0.0, min(0.6 * top_score + 0.4 * average_score, 1.0))

    top_group = selected[0]
    penalty_factor, penalty_reasons = _penalty_factor(top_group)
    confidence = max(0.0, min(base_confidence * penalty_factor, 1.0))
    return {
        "confidence": round(confidence, 4),
        "confidence_label": confidence_label(confidence),
        "confidence_factors": {
            "formula": "0.6 * top_score + 0.4 * average_top_scores",
            "score_count": len(scores),
            "top_score": round(top_score, 4),
            "average_top_scores": round(average_score, 4),
            "base_confidence": round(base_confidence, 4),
            "penalty_factor": round(penalty_factor, 4),
            "penalty_reasons": penalty_reasons,
        },
    }
