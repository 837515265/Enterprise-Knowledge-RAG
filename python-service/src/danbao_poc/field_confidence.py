"""Explainable confidence scoring for extracted fields."""

from __future__ import annotations

from typing import Any

from .common import clean_text


FIELD_SECTION_HINTS: dict[str, set[str]] = {
    "plan_name": {"document_meta", "title"},
    "document_no": {"document_meta"},
    "service_object": {"service_object", "admission_requirement", "business_scope"},
    "access_condition": {"admission_requirement"},
    "credit_purpose": {"credit_purpose"},
    "credit_limit": {"credit_limit", "product_element"},
    "credit_term": {"guarantee_term", "credit_term", "product_element"},
    "guarantee_rate": {"guarantee_fee", "product_element"},
    "risk_share_ratio": {"risk_mitigation", "risk_share"},
    "counter_guarantee": {"counter_guarantee", "risk_mitigation"},
    "applicable_scope": {"business_scope", "applicable_scope"},
    "region": {"business_scope", "applicable_scope"},
    "cooperation_org": {"cooperation_org", "business_scope"},
    "business_process": {"business_process"},
    "required_materials": {"required_materials", "business_process"},
}


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def source_score(strategy: str | None, source: str | None, llm_confidence: str | None) -> float:
    strategy = clean_text(strategy)
    source = clean_text(source)
    label = clean_text(llm_confidence).upper()
    if strategy == "regex_first":
        return 1.0
    if source in {"llm", "model"} and label == "HIGH":
        return 0.82
    if source in {"llm", "model"} and label == "MEDIUM":
        return 0.68
    if source in {"rule", "fallback"}:
        return 0.58
    if label == "HIGH":
        return 0.76
    if label == "LOW":
        return 0.42
    return 0.60


def evidence_score(alignment: dict[str, Any] | None) -> float:
    status = clean_text((alignment or {}).get("status"))
    if status == "exact":
        return 1.0
    if status == "normalized_exact":
        return 0.92
    if status == "lcs_aligned":
        return 0.82
    if status == "fuzzy_aligned":
        return 0.72
    if status == "failed":
        return 0.25
    return 0.55


def chunk_score(field_code: str, chunk: dict[str, Any] | None) -> float:
    if not chunk:
        return 0.35
    section_type = clean_text(chunk.get("section_type"))
    chunk_type = clean_text(chunk.get("chunk_type"))
    hints = FIELD_SECTION_HINTS.get(field_code) or set()
    if section_type in hints or chunk_type in hints:
        return 1.0
    title = clean_text(chunk.get("title"))
    if title and any(term in title for term in ["额度", "期限", "准入", "范围", "对象", "材料", "流程", "反担保"]):
        return 0.78
    return 0.62


def confidence_label(score: float) -> str:
    if score >= 0.80:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    return "LOW"


def compute_field_confidence(
    *,
    field_code: str,
    chunk: dict[str, Any] | None,
    evidence_alignment: dict[str, Any] | None,
    extraction_strategy: str | None,
    extraction_source: str | None,
    llm_confidence: str | None,
    consistency_score: float = 1.0,
) -> dict[str, Any]:
    factors = {
        "source_score": source_score(extraction_strategy, extraction_source, llm_confidence),
        "evidence_score": evidence_score(evidence_alignment),
        "chunk_score": chunk_score(field_code, chunk),
        "consistency_score": _clamp(consistency_score),
    }
    score = (
        0.35 * factors["source_score"]
        + 0.30 * factors["evidence_score"]
        + 0.20 * factors["chunk_score"]
        + 0.15 * factors["consistency_score"]
    )
    return {
        "score": round(_clamp(score), 4),
        "label": confidence_label(score),
        "factors": {key: round(value, 4) for key, value in factors.items()},
        "formula": "0.35*source + 0.30*evidence + 0.20*chunk + 0.15*consistency",
    }


def attach_consistency_confidence(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Update field confidence after all same-code values are visible."""
    by_code: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        by_code.setdefault(str(field.get("field_code") or ""), []).append(field)

    for rows in by_code.values():
        normalized_counts: dict[str, int] = {}
        for field in rows:
            value = clean_text(field.get("value_text"))
            normalized_counts[value] = normalized_counts.get(value, 0) + 1
        conflict = len([value for value in normalized_counts if value]) > 1
        majority_count = max(normalized_counts.values(), default=0)
        for field in rows:
            metadata = field.get("metadata") if isinstance(field.get("metadata"), dict) else {}
            value = clean_text(field.get("value_text"))
            if not conflict:
                consistency = 1.0
            elif normalized_counts.get(value, 0) == majority_count:
                consistency = 0.75
            else:
                consistency = 0.45
            metadata["field_conflict"] = conflict
            metadata["field_confidence"] = compute_field_confidence(
                field_code=str(field.get("field_code") or ""),
                chunk={
                    "section_type": field.get("source_section_type"),
                    "chunk_key": field.get("source_chunk_key"),
                },
                evidence_alignment=metadata.get("evidence_alignment") if isinstance(metadata.get("evidence_alignment"), dict) else None,
                extraction_strategy=metadata.get("extraction_strategy"),
                extraction_source=metadata.get("extraction_source"),
                llm_confidence=metadata.get("confidence"),
                consistency_score=consistency,
            )
            metadata["field_confidence_score"] = metadata["field_confidence"]["score"]
            metadata["field_confidence_factors"] = metadata["field_confidence"]["factors"]
            field["metadata"] = metadata
    return fields
