from __future__ import annotations

import json
import re
import os
from typing import Any

from .chunker import SECTION_ALIASES
from .common import clean_text, stable_hash
from .evidence_aligner import align_quote_to_text
from .field_confidence import attach_consistency_confidence, compute_field_confidence
from .openai_compat import JsonChatClient
from .profiles.prompt_templates import build_extract_prompt


FIELD_NAME_CN = {
    "plan_name": "方案名称",
    "document_no": "文号",
    "product_name": "产品名称",
    "service_object": "服务对象",
    "customer_type": "适用客群",
    "access_condition": "准入条件",
    "credit_purpose": "授信用途",
    "credit_limit": "授信额度",
    "credit_term": "授信期限",
    "guarantee_rate": "担保费率",
    "risk_mitigation": "风险缓释措施",
    "risk_share_ratio": "风险分担比例",
    "counter_guarantee": "反担保措施",
    "applicable_scope": "适用范围",
    "region": "适用地区",
    "industry": "适用产业",
    "business_process": "办理流程",
    "required_materials": "申请资料",
    "cooperation_org": "合作机构",
    "policy_basis": "政策依据",
}

FIELD_ALIAS_MAP = {
    "plan_name": ["方案名称", "方案名"],
    "document_no": ["文号", "发文号", "批文号"],
    "product_name": ["产品名称", "产品名"],
    "service_object": ["服务对象", "支持对象", "适用客户"],
    "customer_type": ["适用客群", "客户类型", "支持客群"],
    "access_condition": ["准入条件", "准入要求", "申请条件", "办理条件"],
    "credit_purpose": ["授信用途", "贷款用途", "资金用途"],
    "credit_limit": ["授信额度", "最高额度", "贷款额度", "担保额度", "授信金额"],
    "credit_term": ["授信期限", "贷款期限", "担保期限", "最长期限"],
    "guarantee_rate": ["担保费率", "担保费", "费率"],
    "risk_mitigation": ["风险缓释", "风险分担", "财政分险", "分险比例"],
    "risk_share_ratio": ["风险分担比例", "分险比例", "风险承担比例"],
    "counter_guarantee": ["反担保", "抵押反担保", "保证反担保"],
    "applicable_scope": ["适用范围", "适用地区", "支持区域"],
    "region": ["适用地区", "适用区域", "支持区域", "经营区域", "辖区"],
    "industry": ["产业", "行业", "产业集群"],
    "business_process": ["办理流程", "业务流程", "申请流程"],
    "required_materials": ["申请资料", "申报材料", "所需材料"],
    "cooperation_org": ["合作机构", "合作银行", "承办机构"],
    "policy_basis": ["政策依据", "文件依据", "文号依据"],
}

FIELD_SECTION_HINTS = {
    "service_object": ["service_object"],
    "customer_type": ["service_object"],
    "access_condition": ["access_condition"],
    "credit_purpose": ["credit_purpose"],
    "credit_limit": ["credit_limit"],
    "credit_term": ["credit_term"],
    "guarantee_rate": ["risk_mitigation", "credit_limit"],
    "risk_mitigation": ["risk_mitigation"],
    "risk_share_ratio": ["risk_mitigation"],
    "counter_guarantee": ["counter_guarantee"],
    "applicable_scope": ["applicable_scope"],
    "region": ["applicable_scope"],
    "industry": ["applicable_scope", "service_object"],
    "business_process": ["business_process"],
    "required_materials": ["required_materials"],
    "cooperation_org": ["other", "applicable_scope"],
    "policy_basis": ["other"],
}

INVALID_REGION_TOKENS = {
    "市场",
    "证券",
    "期货",
    "房地产",
    "资金",
    "贷款",
    "担保",
    "业务",
    "方案",
    "产业",
    "行业",
    "重点",
    "特色",
    "公司",
    "银行",
    "客户",
    "主体",
    "任何形式",
}
BODY_REQUIRED_FIELDS = {"service_object", "access_condition", "credit_purpose", "credit_limit", "credit_term", "risk_mitigation", "counter_guarantee", "applicable_scope", "business_process", "required_materials"}
DETERMINISTIC_FIELDS = {"document_no", "credit_limit", "credit_term", "guarantee_rate", "risk_share_ratio", "region", "cooperation_org"}

FIELD_REGEX_PROFILE: dict[str, list[re.Pattern[str]]] = {
    # Adapted from GraphRAG-Example's pattern-first extraction style, but
    # constrained to guarantee-plan deterministic fields.
    "credit_limit": [
        re.compile(r"(?:单户)?(?:担保额度|授信额度|贷款额度|最高(?:担保)?额度|额度上限)[：:\s]*(?P<value>[^。\n；;]{2,120})"),
        re.compile(r"最高(?:担保)?额度(?:为|不超过|不得超过|最高可达)?(?P<value>[^。\n；;]{2,80})"),
    ],
    "credit_term": [
        re.compile(r"(?:授信期限|贷款期限|担保期限|最长期限)[：:\s]*(?P<value>[^。\n；;]{2,100})"),
        re.compile(r"(?:期限|期间)(?:不超过|不得超过|最长)?(?P<value>\d+(?:\.\d+)?\s*(?:年|个月)[^。\n；;]{0,40})"),
    ],
    "guarantee_rate": [
        re.compile(r"(?:担保费率|担保费|费率)[：:\s]*(?P<value>[^。\n；;]{2,100})"),
    ],
    "risk_share_ratio": [
        re.compile(r"(?:风险分担比例|分险比例|风险承担比例|财政分险)[：:\s]*(?P<value>[^。\n；;]{2,100})"),
    ],
    "region": [
        re.compile(r"(?:适用区域|适用地区|支持区域|经营区域)[：:\s]*(?P<value>[^。\n；;]{2,100})"),
    ],
    "cooperation_org": [
        re.compile(r"(?:合作银行|合作机构|经办机构|承办机构)[：:\s]*(?P<value>[^。\n；;]{2,120})"),
    ],
}


def _first(pattern: str, text: str) -> str | None:
    matched = re.search(pattern, text)
    return matched.group(1) if matched else None


def _extract_plan_name(text: str, fallback: str | None) -> str | None:
    return _first(r"《([^》]{4,120})》", text) or fallback


def _extract_document_no(text: str) -> str | None:
    for pattern in [r"(鲁农担批〔\d{4}〕\d+号)", r"([^\s，,。；;]{1,24}〔\d{4}〕\d+号)"]:
        value = _first(pattern, text)
        if value:
            return value
    return None


def _extract_regions(text: str) -> list[str]:
    rows = re.findall(r"[\u4e00-\u9fa5]{2,12}(?:省|市|县|区|镇|乡|村|街道)", text or "")
    result: list[str] = []
    for item in rows:
        item = _normalize_region_name(item)
        if item and item not in result:
            result.append(item)
    return result[:20]


def _extract_organizations(text: str) -> list[str]:
    rows = re.findall(r"[\u4e00-\u9fa5]{3,40}(?:公司|银行|财政局|农业局|担保中心|合作社)", text or "")
    result: list[str] = []
    for item in rows:
        item = clean_text(item)
        if item and item not in result:
            result.append(item)
    return result[:20]


def _extract_industries(text: str) -> list[str]:
    rows = re.findall(r"[\u4e00-\u9fa5]{2,20}(?:产业集群|产业|行业)", text or "")
    result: list[str] = []
    for item in rows:
        if item and item not in result:
            result.append(item)
    for keyword in ["草莓", "农业", "种植", "养殖", "果蔬", "粮食"]:
        if keyword in (text or "") and keyword not in result:
            result.append(keyword)
    return result[:10]


def _normalized_money(text: str) -> dict[str, Any]:
    amounts = re.findall(r"(\d+(?:\.\d+)?)\s*(万元|万|亿元|元)", text or "")
    values: list[int] = []
    for amount, unit in amounts:
        value = float(amount)
        if unit in {"万元", "万"}:
            value *= 10000
        elif unit == "亿元":
            value *= 100000000
        values.append(int(value))
    if not values:
        return {}
    return {
        "amount_min_yuan": min(values),
        "amount_max_yuan": max(values),
        "currency": "CNY",
    }


def _normalized_term(text: str) -> dict[str, Any]:
    years = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*年", text or "")]
    months = [int(item) for item in re.findall(r"(\d+)\s*个月", text or "")]
    result: dict[str, Any] = {}
    if years:
        result["term_max_months"] = int(max(years) * 12)
    if months:
        result["term_max_months"] = max(result.get("term_max_months", 0), max(months))
    return result


def _normalized_ratio(text: str) -> dict[str, Any]:
    m = re.findall(r"(\d+(?:\.\d+)?)\s*%", text or "")
    if not m:
        return {}
    values = [float(item) / 100.0 for item in m]
    return {"ratio_min": min(values), "ratio_max": max(values)}


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [item.strip() for item in re.split(r"[、，,；;\n]", value) if item.strip()]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = clean_text(item)
        if text and text not in result:
            result.append(text)
    return result[:20]


def _normalize_region_name(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"^(适用于|适用|支持|覆盖|面向)", "", text)
    text = re.sub(r"(辖区内|范围内|区域内|地区内|境内|内)$", "", text)
    text = text.strip("，,。、；;：:（）()[]【】 ")
    if not text or len(text) > 16:
        return ""
    if any(token in text for token in INVALID_REGION_TOKENS):
        return ""
    if not re.fullmatch(r"[\u4e00-\u9fa5]{2,16}(?:省|市|县|区|镇|乡|村|街道)", text):
        return ""
    return text


def _normalize_region_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [item.strip() for item in re.split(r"[、，,；;\n]", value) if item.strip()]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        region = _normalize_region_name(item)
        if region and region not in result:
            result.append(region)
    return result[:20]


def _normalize_field_value(field_code: str, value_text: str) -> dict[str, Any]:
    if field_code == "credit_limit":
        return _normalized_money(value_text)
    if field_code == "credit_term":
        return _normalized_term(value_text)
    if field_code in {"guarantee_rate", "risk_share_ratio"}:
        return _normalized_ratio(value_text)
    return {}


def _extract_regex_field_candidates(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        content = clean_text(chunk.get("content"))
        if not content:
            continue
        for field_code, patterns in FIELD_REGEX_PROFILE.items():
            for pattern in patterns:
                for match in pattern.finditer(content):
                    evidence_quote = clean_text(match.group(0))
                    value_text = clean_text(match.groupdict().get("value") or evidence_quote)
                    if field_code == "region":
                        regions = _normalize_region_list(value_text)
                        value_text = "、".join(regions) if regions else value_text
                    if field_code == "cooperation_org":
                        orgs = _extract_organizations(value_text)
                        value_text = "、".join(orgs) if orgs else value_text
                    has_deterministic_value = bool(_normalize_field_value(field_code, value_text)) or bool(re.search(r"\d", value_text))
                    if not value_text or (_looks_like_heading_only(field_code, value_text) and not has_deterministic_value):
                        continue
                    key = (field_code, value_text, str(chunk.get("chunk_key") or ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        {
                            "field_code": field_code,
                            "value_text": value_text,
                            "source_chunk_key": chunk.get("chunk_key"),
                            "evidence_quote": evidence_quote,
                            "confidence": "HIGH",
                            "extraction_strategy": "regex_first",
                            "extraction_source": "graph_rag_cn_patterns",
                            "normalized_json": {
                                **_normalize_field_value(field_code, value_text),
                                "extraction_source": "graph_rag_cn_patterns",
                                "matched_pattern": pattern.pattern,
                            },
                        }
                    )
                    break
    return candidates


def _looks_like_heading_only(field_code: str, value_text: str) -> bool:
    if field_code not in BODY_REQUIRED_FIELDS:
        return False
    text = clean_text(value_text)
    if len(text) > 40:
        return False
    if any(mark in text for mark in ["。", "；", ";", "：", ":"]) or "\n" in text:
        return False
    aliases = FIELD_ALIAS_MAP.get(field_code, [])
    return any(alias in text for alias in aliases)


def _chunk_business_block(chunk: dict[str, Any]) -> tuple[str, str]:
    metadata = chunk.get("metadata") or {}
    return clean_text(metadata.get("business_block_id")), clean_text(metadata.get("business_block_title"))


def _compact_chunks_for_llm(chunks: list[dict[str, Any]], max_chars: int = 20000) -> str:
    rows: list[str] = []
    size = 0
    section_index: dict[str, list[str]] = {}
    for field_code, section_types in FIELD_SECTION_HINTS.items():
        keys = [
            str(chunk.get("chunk_key"))
            for chunk in chunks
            if chunk.get("section_type") in section_types and chunk.get("chunk_key")
        ][:12]
        if keys:
            section_index[field_code] = keys
    if section_index:
        header = "## 字段优先上下文索引\n" + "\n".join(
            f"- {field_code}: {', '.join(keys)}"
            for field_code, keys in sorted(section_index.items())
        ) + "\n\n## 分块明细\n"
        rows.append(header)
        size += len(header)
    ordered = sorted(
        chunks,
        key=lambda item: (
            _chunk_business_block(item)[0],
            item.get("section_type") or "other",
            item.get("seq_no") or 0,
        ),
    )
    for chunk in ordered:
        business_block_id, business_block_title = _chunk_business_block(chunk)
        block = (
            f"[{chunk['chunk_key']}] 标题: {chunk.get('title') or ''}\n"
            f"section_type: {chunk.get('section_type') or 'other'}\n"
            f"business_block_id: {business_block_id}\n"
            f"business_block_title: {business_block_title}\n"
            f"page: {chunk.get('page_start')}~{chunk.get('page_end')}\n"
            f"content: {chunk.get('content') or ''}\n"
        )
        if size + len(block) > max_chars:
            break
        rows.append(block)
        size += len(block)
    return "\n".join(rows)


def _rule_based_extraction(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    all_text = "\n".join(chunk.get("content") or "" for chunk in chunks)
    title = chunks[0]["title_path"][0] if chunks and chunks[0].get("title_path") else None
    plan_name = _extract_plan_name(all_text, title)
    document_no = _extract_document_no(all_text)
    plan = {
        "plan_name": plan_name,
        "document_no": document_no,
        "regions": [],
        "organizations": [],
        "industries": [],
    }
    field_items: list[dict[str, Any]] = []
    if plan_name:
        field_items.append({"field_code": "plan_name", "value_text": plan_name})
    if document_no:
        field_items.append({"field_code": "document_no", "value_text": document_no})
    for chunk in chunks:
        section_type = chunk.get("section_type")
        if section_type in FIELD_NAME_CN and chunk.get("content"):
            field_items.append({"field_code": section_type, "value_text": clean_text(chunk["content"])})
    field_items.extend(_extract_regex_field_candidates(chunks))
    return {"plan": plan, "fields": field_items}


def _llm_extract(chunks: list[dict[str, Any]], parse_options: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """P1: 支持分组抽取的 LLM 字段抽取。

    当 chunks 总量超过上下文预算时，按 business_block + section_type
    分组分批抽取，最后合并去重。
    """
    try:
        client = JsonChatClient("EXTRACT", default_model=True, enable_fallback=True)
    except Exception as exc:
        return {"_debug": {"llm_enabled": False, "error": str(exc)}}

    from .extraction_merge import extraction_pass_count, merge_overlaps_enabled, merge_pass_record_lists

    pass_count = extraction_pass_count(parse_options)
    merge_overlaps = merge_overlaps_enabled(parse_options)
    if pass_count > 1:
        pass_results: list[dict[str, Any]] = []
        for pass_index in range(pass_count):
            temperature = 0 if pass_index == 0 else min(0.35, 0.15 + (pass_index - 1) * 0.1)
            result = _llm_extract_once(client, chunks, temperature=temperature)
            if result and isinstance(result, dict):
                result.setdefault("_debug", {})
                result["_debug"].update(
                    {
                        "pass_index": pass_index + 1,
                        "pass_name": "stable" if pass_index == 0 else "recall",
                        "temperature": temperature,
                    }
                )
                pass_results.append(result)
        if not pass_results:
            return {"_debug": {"llm_enabled": True, "error": "all_passes_failed"}}

        from .context_budget import merge_plan_dicts

        merged_plan: dict[str, Any] = {}
        field_lists: list[list[dict[str, Any]]] = []
        for result in pass_results:
            if isinstance(result.get("plan"), dict):
                merged_plan = merge_plan_dicts(merged_plan, result["plan"])
            field_lists.append(result.get("fields") or [])
        merged_fields, merge_report = merge_pass_record_lists(
            field_lists,
            exact_fields=["field_code", "business_block_id", "source_chunk_key", "value_text", "evidence_quote"],
            group_fields=["field_code", "business_block_id", "source_chunk_key"],
            text_fields=["evidence_quote", "value_text"],
            merge_overlaps=merge_overlaps,
        )
        return {
            "plan": merged_plan,
            "fields": merged_fields,
            "_debug": {
                "llm_enabled": True,
                "multi_pass": {
                    **merge_report,
                    "merge_overlaps": merge_overlaps,
                    "pass_debug": [result.get("_debug") or {} for result in pass_results],
                },
                "field_count": len(merged_fields),
                "plan_keys": sorted(merged_plan.keys()),
            },
        }

    return _llm_extract_once(client, chunks, temperature=0)


def _llm_extract_once(client: JsonChatClient, chunks: list[dict[str, Any]], *, temperature: float = 0) -> dict[str, Any] | None:
    from .context_budget import group_chunks_for_extraction, dedupe_fields, merge_plan_dicts

    max_chars = int(os.getenv("EXTRACT_MAX_CONTENT_CHARS", "20000"))
    batches = group_chunks_for_extraction(chunks, max_chars_per_group=max_chars)

    if len(batches) == 1:
        return _llm_extract_single(client, batches[0], temperature=temperature)

    # 多批次：分组抽取 + 合并
    all_fields: list[dict[str, Any]] = []
    merged_plan: dict[str, Any] = {}
    batch_debug: list[dict[str, Any]] = []

    for batch_idx, batch_chunks in enumerate(batches):
        result = _llm_extract_single(client, batch_chunks, temperature=temperature)
        if result and isinstance(result, dict):
            all_fields.extend(result.get("fields") or [])
            if result.get("plan") and isinstance(result["plan"], dict):
                merged_plan = merge_plan_dicts(merged_plan, result["plan"])
            batch_debug.append({
                "batch": batch_idx,
                "chunk_count": len(batch_chunks),
                "field_count": len(result.get("fields") or []),
            })

    deduped = dedupe_fields(all_fields)
    return {
        "plan": merged_plan,
        "fields": deduped,
        "_debug": {
            "llm_enabled": True,
            "batch_count": len(batches),
            "temperature": temperature,
            "total_fields_before_dedup": len(all_fields),
            "field_count": len(deduped),
            "batches": batch_debug,
            "plan_keys": sorted(merged_plan.keys()),
        },
    }


def _llm_extract_single(client: JsonChatClient, chunks: list[dict[str, Any]], *, temperature: float = 0) -> dict[str, Any] | None:
    """单批次 LLM 字段抽取。"""
    from .context_budget import select_priority_chunks

    max_chars = int(os.getenv("EXTRACT_MAX_CONTENT_CHARS", "20000"))
    selected = select_priority_chunks(chunks, max_chars=max_chars)
    chunk_text = _compact_chunks_for_llm(selected)
    system_prompt, prompt = build_extract_prompt("business_plan", chunk_text)
    try:
        parsed = client.complete_json(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperature,
            max_tokens=3000,
        )
        if isinstance(parsed, dict):
            parsed["_debug"] = {
                "llm_enabled": True,
                "field_count": len(parsed.get("fields") or []),
                "chunks_selected": len(selected),
                "chunks_total": len(chunks),
                "temperature": temperature,
                "plan_keys": sorted((parsed.get("plan") or {}).keys()) if isinstance(parsed.get("plan"), dict) else [],
            }
            return parsed
    except Exception as exc:
        return {"_debug": {"llm_enabled": True, "error": str(exc)}}
    return {"_debug": {"llm_enabled": True, "error": "empty_or_invalid_response"}}


def _score_chunk_for_field(field_code: str, value_text: str, chunk: dict[str, Any]) -> float:
    score = 0.0
    content = chunk.get("content") or ""
    title = chunk.get("title") or ""
    section_type = chunk.get("section_type") or ""

    if value_text and value_text in content:
        score += 8.0
    aliases = FIELD_ALIAS_MAP.get(field_code, [])
    if any(alias in title for alias in aliases):
        score += 4.0
    if any(alias in content[:300] for alias in aliases):
        score += 2.5
    if section_type in FIELD_SECTION_HINTS.get(field_code, []):
        score += 3.0

    if field_code in {"plan_name", "document_no", "policy_basis"} and chunk.get("seq_no") == 1:
        score += 2.0
    if field_code in {"region", "industry", "cooperation_org"} and any(term in content for term in [value_text] if value_text):
        score += 2.0

    return score


def _best_chunk_for_field(field_code: str, value_text: str, source_chunk_key: str | None, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if source_chunk_key:
        for chunk in chunks:
            if chunk.get("chunk_key") == source_chunk_key:
                return chunk
    ranked = sorted(chunks, key=lambda item: _score_chunk_for_field(field_code, value_text, item), reverse=True)
    if not ranked:
        return None
    if _score_chunk_for_field(field_code, value_text, ranked[0]) <= 0:
        return ranked[0] if field_code in {"plan_name", "document_no"} else None
    return ranked[0]


def _snippet_for_evidence(value_text: str, chunk: dict[str, Any] | None) -> str:
    if not chunk:
        return value_text[:1000]
    content = chunk.get("content") or ""
    if not value_text:
        return content[:400]
    pos = content.find(value_text)
    if pos < 0:
        return content[:400]
    start = max(0, pos - 80)
    end = min(len(content), pos + len(value_text) + 120)
    return content[start:end]


def _make_field(
    field_key: str,
    field_code: str,
    value_text: str,
    chunk: dict[str, Any] | None,
    source_chunk_key: str | None = None,
    evidence_quote: str | None = None,
    confidence: str | None = None,
    business_block_id: str | None = None,
    business_block_title: str | None = None,
    normalized_json: dict[str, Any] | None = None,
    extraction_strategy: str | None = None,
    extraction_source: str | None = None,
) -> dict[str, Any]:
    normalized_json = normalized_json if normalized_json is not None else _normalize_field_value(field_code, value_text)
    evidence_text = clean_text(evidence_quote) or _snippet_for_evidence(value_text, chunk)
    confidence_value = clean_text(confidence).upper()
    if confidence_value not in {"HIGH", "MEDIUM", "LOW"}:
        confidence_value = "MEDIUM"
    alignment = align_quote_to_text(evidence_text, chunk.get("content") or "") if chunk and evidence_text else None
    if alignment and alignment.status == "failed" and confidence_value == "HIGH":
        confidence_value = "MEDIUM"
    chunk_metadata = chunk.get("metadata") if chunk else {}
    if not isinstance(chunk_metadata, dict):
        chunk_metadata = {}
    block_id = clean_text(business_block_id) or clean_text(chunk_metadata.get("business_block_id") if isinstance(chunk_metadata, dict) else "")
    block_title = clean_text(business_block_title) or clean_text(chunk_metadata.get("business_block_title") if isinstance(chunk_metadata, dict) else "")
    mention = {
        "evidence_text": evidence_text,
        "page_no": chunk.get("page_start") if chunk else None,
        "block_ids": chunk.get("block_ids") if chunk else [],
        "bbox": chunk.get("bbox") if chunk else [],
    }
    alignment_payload = alignment.to_dict() if alignment else None
    field_confidence = compute_field_confidence(
        field_code=field_code,
        chunk=chunk,
        evidence_alignment=alignment_payload,
        extraction_strategy=extraction_strategy,
        extraction_source=extraction_source,
        llm_confidence=confidence_value,
    )
    return {
        "field_key": field_key,
        "field_code": field_code,
        "field_name_cn": FIELD_NAME_CN[field_code],
        "value_text": value_text,
        "aliases": FIELD_ALIAS_MAP.get(field_code) or SECTION_ALIASES.get(field_code, []),
        "normalized_json": normalized_json,
        "source_chunk_key": source_chunk_key or (chunk.get("chunk_key") if chunk else None),
        "source_section_type": chunk.get("section_type") if chunk else None,
        "metadata": {
            "content_hash": stable_hash(value_text),
            "evidence_quote": evidence_text,
            "confidence": confidence_value,
            "business_block_id": block_id,
            "business_block_title": block_title,
            "extraction_strategy": clean_text(extraction_strategy),
            "extraction_source": clean_text(extraction_source),
            "evidence_alignment": alignment_payload,
            "field_confidence": field_confidence,
            "field_confidence_score": field_confidence["score"],
            "field_confidence_factors": field_confidence["factors"],
        },
        "mention": mention,
    }


def _llm_success(llm_result: dict[str, Any]) -> bool:
    debug = llm_result.get("_debug") if isinstance(llm_result, dict) else {}
    return bool(debug and debug.get("llm_enabled") and not debug.get("error"))


def _merge_plan(rule_plan: dict[str, Any], llm_plan: dict[str, Any] | None, *, use_llm_dimensions: bool) -> dict[str, Any]:
    llm_plan = llm_plan or {}
    return {
        "plan_name": clean_text(llm_plan.get("plan_name") or rule_plan.get("plan_name")),
        "document_no": clean_text(llm_plan.get("document_no") or rule_plan.get("document_no")),
        "product_name": clean_text(llm_plan.get("product_name") or ""),
        "regions": _normalize_region_list(llm_plan.get("regions")) if use_llm_dimensions else [],
        "industries": _normalize_list(llm_plan.get("industries")) if use_llm_dimensions else [],
        "organizations": _normalize_list(llm_plan.get("organizations")) if use_llm_dimensions else [],
    }


def _merge_field_items(rule_items: list[dict[str, Any]], llm_items: list[dict[str, Any]] | None, *, use_rule_fallback: bool) -> list[dict[str, Any]]:
    """Merge rule and LLM field items. LLM items always take priority when available."""
    llm_items = llm_items or []
    merged: dict[str, dict[str, Any]] = {}

    # Rule items only used as fallback when LLM fails completely
    if use_rule_fallback:
        for item in rule_items:
            field_code = item.get("field_code")
            value_text = clean_text(item.get("value_text"))
            if field_code in FIELD_NAME_CN and value_text and not _looks_like_heading_only(field_code, value_text):
                merged[field_code] = {"field_code": field_code, "value_text": value_text, "confidence": "LOW"}

    for item in llm_items:
        field_code = clean_text(item.get("field_code"))
        value_text = clean_text(item.get("value_text"))
        if field_code not in FIELD_NAME_CN or not value_text or _looks_like_heading_only(field_code, value_text):
            continue
        business_block_id = clean_text(item.get("business_block_id"))
        business_block_title = clean_text(item.get("business_block_title"))
        merge_key = f"{business_block_id}:{field_code}" if business_block_id else field_code
        merged[merge_key] = {
            "field_code": field_code,
            "value_text": value_text,
            "source_chunk_key": item.get("source_chunk_key"),
            "evidence_quote": item.get("evidence_quote"),
            "confidence": item.get("confidence"),
            "business_block_id": business_block_id,
            "business_block_title": business_block_title,
            "normalized_json": item.get("normalized_json"),
            "extraction_strategy": item.get("extraction_strategy"),
            "extraction_source": item.get("extraction_source"),
        }

    return list(merged.values())


def _filter_regions_by_evidence(plan: dict[str, Any], merged_items: list[dict[str, Any]]) -> None:
    evidence_parts = [plan.get("plan_name") or "", plan.get("product_name") or ""]
    evidence_parts.extend(
        clean_text(item.get("value_text"))
        for item in merged_items
        if item.get("field_code") in {"region", "applicable_scope"}
    )
    evidence_text = "\n".join(part for part in evidence_parts if part)
    plan["regions"] = [region for region in plan.get("regions") or [] if region and region in evidence_text]


def extract_guarantee_plan(chunks: list[dict[str, Any]], parse_options: dict[str, Any] | None = None) -> dict[str, Any]:
    # Extract document-level metadata (plan name, document number) from document header
    all_text = "\n".join(chunk.get("content") or "" for chunk in chunks)
    title = chunks[0]["title_path"][0] if chunks and chunks[0].get("title_path") else None
    plan_name = _extract_plan_name(all_text, title)
    document_no = _extract_document_no(all_text)

    # LLM handles all field extraction
    llm_result = _llm_extract(chunks, parse_options=parse_options) or {}
    llm_ok = _llm_success(llm_result) if isinstance(llm_result, dict) else False

    if not llm_ok:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.error("LLM field extraction failed for %d chunks, falling back to partial results", len(chunks))
        # Use whatever LLM managed to produce, or empty extraction
        llm_plan = llm_result.get("plan") if isinstance(llm_result, dict) else {}
        llm_fields = llm_result.get("fields") if isinstance(llm_result, dict) else []

    plan = _merge_plan(
        {"plan_name": plan_name, "document_no": document_no, "regions": [], "organizations": [], "industries": []},
        llm_result.get("plan") if isinstance(llm_result, dict) else None,
        use_llm_dimensions=True,
    )
    merged_items = _merge_field_items(
        [],
        llm_result.get("fields") if isinstance(llm_result, dict) else None,
        use_rule_fallback=False,
    )
    # Prepend plan_name and document_no as field items
    if plan_name:
        merged_items.insert(0, {"field_code": "plan_name", "value_text": plan_name, "confidence": "HIGH"})
    if document_no:
        merged_items.insert(0, {"field_code": "document_no", "value_text": document_no, "confidence": "HIGH"})
    _filter_regions_by_evidence(plan, merged_items)

    fields: list[dict[str, Any]] = []
    for index, item in enumerate(merged_items, 1):
        field_code = item["field_code"]
        value_text = clean_text(item["value_text"])
        chunk = _best_chunk_for_field(field_code, value_text, item.get("source_chunk_key"), chunks)
        fields.append(
            _make_field(
                field_key=f"field_{index:03d}_{field_code}",
                field_code=field_code,
                value_text=value_text,
                chunk=chunk,
                source_chunk_key=item.get("source_chunk_key"),
                evidence_quote=item.get("evidence_quote"),
                confidence=item.get("confidence"),
                business_block_id=item.get("business_block_id"),
                business_block_title=item.get("business_block_title"),
                normalized_json=item.get("normalized_json"),
                extraction_strategy=item.get("extraction_strategy"),
                extraction_source=item.get("extraction_source"),
            )
        )

    if plan.get("plan_name") and not any(field["field_code"] == "plan_name" for field in fields):
        chunk = _best_chunk_for_field("plan_name", plan["plan_name"], None, chunks)
        fields.insert(0, _make_field("field_plan_name", "plan_name", plan["plan_name"], chunk))
    if plan.get("document_no") and not any(field["field_code"] == "document_no" for field in fields):
        chunk = _best_chunk_for_field("document_no", plan["document_no"], None, chunks)
        fields.insert(1 if fields else 0, _make_field("field_document_no", "document_no", plan["document_no"], chunk))
    fields = attach_consistency_confidence(fields)

    return {
        "plan": plan,
        "fields": fields,
        "_debug": {
            "llm": llm_result.get("_debug") if isinstance(llm_result, dict) else None,
            "llm_used_for_dimensions": llm_ok,
            "merged_field_count": len(fields),
        },
    }
