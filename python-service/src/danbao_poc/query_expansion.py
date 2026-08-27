from __future__ import annotations

from typing import Any


COLLOQUIAL_SYNONYMS: dict[str, dict[str, Any]] = {
    "利息": {"terms": ["担保费率", "费率", "利率", "收费标准"], "fields": ["guarantee_rate", "fee_rate"]},
    "几个点": {"terms": ["担保费率", "费率", "利率", "收费标准"], "fields": ["guarantee_rate", "fee_rate"]},
    "几个点儿": {"terms": ["担保费率", "费率", "利率", "收费标准"], "fields": ["guarantee_rate", "fee_rate"]},
    "抵押": {"terms": ["反担保", "担保措施", "抵押物", "担保物"], "fields": ["counter_guarantee"]},
    "担保物": {"terms": ["反担保", "抵押", "质押"], "fields": ["counter_guarantee"]},
    "能贷多少": {"terms": ["额度", "授信额度", "贷款额度", "最高额度"], "fields": ["credit_limit"]},
    "能批多少": {"terms": ["额度", "授信额度", "贷款额度", "最高额度"], "fields": ["credit_limit"]},
    "最多多少": {"terms": ["额度", "授信额度", "贷款额度", "最高额度"], "fields": ["credit_limit"]},
    "贷多少": {"terms": ["授信额度", "担保额度", "额度测算", "最高额度"], "fields": ["credit_limit"]},
    "多久": {"terms": ["期限", "授信期限", "担保期限", "贷款期限"], "fields": ["credit_term"]},
    "期限": {"terms": ["授信期限", "担保期限", "贷款期限", "最长期限"], "fields": ["credit_term"]},
    "多长时间": {"terms": ["期限", "授信期限", "担保期限", "贷款期限"], "fields": ["credit_term"]},
    "几年": {"terms": ["期限", "授信期限", "担保期限", "贷款期限"], "fields": ["credit_term"]},
    "还不上": {"terms": ["追偿", "风险缓释", "逾期", "代偿"], "fields": ["risk_mitigation"]},
    "逾期了": {"terms": ["追偿", "风险缓释", "逾期", "代偿"], "fields": ["risk_mitigation"]},
    "怎么办": {"terms": ["办理流程", "申请流程", "申报材料", "所需材料"], "fields": ["business_process", "required_materials"]},
    "咋办": {"terms": ["办理流程", "申请流程", "申报材料", "所需材料"], "fields": ["business_process", "required_materials"]},
    "怎么申请": {"terms": ["准入条件", "申请条件", "办理流程"], "fields": ["admission_requirement", "business_process"]},
    "能贷吗": {"terms": ["准入条件", "服务对象"], "fields": ["admission_requirement", "service_object"]},
    "能不能": {"terms": ["准入条件", "服务对象"], "fields": ["admission_requirement", "service_object"]},
    "多久能批": {"terms": ["审批流程", "办理时限"], "fields": ["business_process"]},
    "什么时候到账": {"terms": ["放款", "资金到位"], "fields": ["business_process"]},
    "靠谱": {"terms": ["担保方案", "产品介绍", "服务对象"], "fields": ["service_object"]},
    "要不要抵押": {"terms": ["反担保", "担保措施"], "fields": ["counter_guarantee"]},
    "需要什么条件": {"terms": ["准入条件", "申请条件"], "fields": ["admission_requirement"]},
}


def _append_unique(items: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def expand_colloquial_query(query: str, profile: str | None = None) -> dict[str, Any]:
    text = query or ""
    expanded_terms: list[str] = []
    expanded_field_codes: list[str] = []
    matched_terms: list[str] = []

    for colloquial, expansion in COLLOQUIAL_SYNONYMS.items():
        if colloquial not in text:
            continue
        _append_unique(matched_terms, colloquial)
        for term in expansion.get("terms") or []:
            _append_unique(expanded_terms, term)
        for field_code in expansion.get("fields") or []:
            _append_unique(expanded_field_codes, field_code)

    return {
        "expanded_terms": expanded_terms[:16],
        "expanded_field_codes": expanded_field_codes[:8],
        "matched_terms": matched_terms,
        "expansion_reason": "colloquial_synonym" if matched_terms else "",
        "profile": profile or "",
    }


def build_expanded_query_text(query: str, expanded_terms: list[str] | tuple[str, ...] | None, max_terms: int = 8) -> str:
    terms = [str(term).strip() for term in (expanded_terms or []) if str(term or "").strip()]
    if not terms:
        return query
    deduped: list[str] = []
    for term in terms:
        if term not in query and term not in deduped:
            deduped.append(term)
    if not deduped:
        return query
    return " ".join([query, *deduped[:max_terms]]).strip()
