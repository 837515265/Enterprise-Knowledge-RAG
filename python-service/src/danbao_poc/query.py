from __future__ import annotations

import json
import re
from typing import Any

from .graph_intent import infer_graph_intent
from .graph_schema import allowed_graph_edge_types, allowed_node_types, graph_query_relations
from .openai_compat import JsonChatClient, RerankClient
from .profiles.field_aliases import get_field_aliases, get_field_hints
from .profiles.registry import normalize_profile
from .query_expansion import expand_colloquial_query
from .retrieve_cache import get_json_cached, set_json_cached


FIELD_ALIASES = {
    "plan_name": ["方案名称", "方案名", "文件名称"],
    "document_no": ["文号", "发文号", "批文号", "文件号"],
    "service_object": ["服务对象", "支持对象", "适用客户", "适用人群", "客群"],
    "access_condition": ["准入条件", "准入要求", "申请条件", "办理条件", "门槛"],
    "credit_purpose": ["授信用途", "贷款用途", "资金用途"],
    "credit_limit": ["最高额度", "贷款额度", "担保额度", "授信金额", "授信额度", "能贷多少", "最多能批多少", "额度上限"],
    "credit_term": ["最长期限", "贷款期限", "担保期限", "授信期限", "几年", "多久", "多长时间"],
    "risk_mitigation": ["风险缓释", "分险比例", "风险分担", "财政分险", "风险承担"],
    "counter_guarantee": ["反担保", "担保措施", "抵押反担保", "保证措施"],
    "applicable_scope": ["适用范围", "适用地区", "支持区域", "哪些地区", "什么范围"],
    "business_process": ["办理流程", "业务流程", "申请流程", "办理步骤"],
    "required_materials": ["申请资料", "申报材料", "所需材料", "需要哪些材料"],
}

FIELD_HINTS = {
    "plan_name": "方案主体名称",
    "document_no": "文号或批文编号",
    "service_object": "适用对象、客户群体",
    "access_condition": "准入门槛、申请条件",
    "credit_purpose": "贷款或授信用途",
    "credit_limit": "金额上限、最高额度",
    "credit_term": "期限、月份、年限",
    "risk_mitigation": "分险、风险缓释安排",
    "counter_guarantee": "反担保和增信要求",
    "applicable_scope": "适用地区、地域范围",
    "business_process": "办理流程和步骤",
    "required_materials": "申请资料和材料清单",
}

ALLOWED_RETRIEVE_MODES = {"qa", "structured", "section_summary", "graph", "bm25", "vector"}
INVALID_REGION_TOKENS = {"市场", "证券", "期货", "房地产", "资金", "贷款", "担保", "业务", "方案", "产业", "行业", "重点", "特色", "公司", "银行", "客户", "主体", "任何形式"}

# Known short product / plan names that may not end with 贷/保/方案 suffixes
# but should still be recognized as scope anchors for file filtering.
KNOWN_PRODUCT_NAMES = {
    "农贸贷", "农耕贷", "强村贷", "加工贷", "种业贷", "农牧贷", "农服贷",
    "果香贷", "文旅贷", "耕渔贷", "富农产业贷", "乡村文旅贷", "耕海牧渔贷",
    "鲁担惠农贷", "莱阳梨", "冠县酥梨", "锦鲤养殖", "草莓产业", "烟台苹果",
    "数字设施渔业", "水产苗种繁育",
}

DEFAULT_RRF_K = 60
DEFAULT_FUSION_WEIGHTS: dict[str, dict[str, float]] = {
    "business_plan": {"structured": 0.10, "section_summary": 0.08, "graph": 0.05, "bm25": 0.35, "vector": 0.25, "qa": 0.17},
    "guarantee_plan": {"structured": 0.10, "section_summary": 0.08, "graph": 0.05, "bm25": 0.35, "vector": 0.25, "qa": 0.17},
    "operation_knowledge": {"structured": 0.12, "section_summary": 0.08, "graph": 0.04, "bm25": 0.23, "vector": 0.23, "qa": 0.30},
    "contract_agreement": {"structured": 0.20, "section_summary": 0.10, "graph": 0.10, "bm25": 0.30, "vector": 0.20, "qa": 0.10},
    "governance_rule": {"structured": 0.18, "section_summary": 0.14, "graph": 0.08, "bm25": 0.34, "vector": 0.18, "qa": 0.08},
    "project_doc": {"structured": 0.18, "section_summary": 0.12, "graph": 0.05, "bm25": 0.33, "vector": 0.24, "qa": 0.08},
    "general_document": {"structured": 0.15, "section_summary": 0.15, "graph": 0.05, "bm25": 0.30, "vector": 0.25, "qa": 0.10},
    "structured_data": {"structured": 0.25, "section_summary": 0.10, "graph": 0.03, "bm25": 0.32, "vector": 0.15, "qa": 0.15},
    "sql_analytics": {"structured": 0.25, "section_summary": 0.00, "graph": 0.00, "bm25": 0.45, "vector": 0.30, "qa": 0.00},
}
FUSION_WEIGHT_PRESETS: dict[str, dict[str, dict[str, float]]] = {
    "baseline_current": {},
    "bm25_vector_stronger": {
        "business_plan": {"structured": 0.14, "section_summary": 0.08, "graph": 0.08, "bm25": 0.34, "vector": 0.24, "qa": 0.12},
        "guarantee_plan": {"structured": 0.14, "section_summary": 0.08, "graph": 0.08, "bm25": 0.34, "vector": 0.24, "qa": 0.12},
        "governance_rule": {"structured": 0.12, "section_summary": 0.18, "graph": 0.04, "bm25": 0.42, "vector": 0.18, "qa": 0.06},
        "general_document": {"structured": 0.12, "section_summary": 0.12, "graph": 0.03, "bm25": 0.38, "vector": 0.27, "qa": 0.08},
    },
    "graph_structured_lower": {
        "business_plan": {"structured": 0.10, "section_summary": 0.10, "graph": 0.04, "bm25": 0.36, "vector": 0.26, "qa": 0.14},
        "guarantee_plan": {"structured": 0.10, "section_summary": 0.10, "graph": 0.04, "bm25": 0.36, "vector": 0.26, "qa": 0.14},
        "governance_rule": {"structured": 0.08, "section_summary": 0.22, "graph": 0.02, "bm25": 0.42, "vector": 0.20, "qa": 0.06},
        "general_document": {"structured": 0.10, "section_summary": 0.16, "graph": 0.02, "bm25": 0.36, "vector": 0.28, "qa": 0.08},
    },
    "qa_boosted": {
        "business_plan": {"structured": 0.12, "section_summary": 0.08, "graph": 0.06, "bm25": 0.32, "vector": 0.22, "qa": 0.20},
        "guarantee_plan": {"structured": 0.12, "section_summary": 0.08, "graph": 0.06, "bm25": 0.32, "vector": 0.22, "qa": 0.20},
        "governance_rule": {"structured": 0.10, "section_summary": 0.18, "graph": 0.03, "bm25": 0.38, "vector": 0.18, "qa": 0.13},
        "general_document": {"structured": 0.10, "section_summary": 0.12, "graph": 0.03, "bm25": 0.34, "vector": 0.25, "qa": 0.16},
    },
}


def _profile_aliases(profile: str | None) -> dict[str, list[str]]:
    return get_field_aliases(normalize_profile(profile) or "business_plan")


def _profile_hints(profile: str | None) -> dict[str, str]:
    return get_field_hints(normalize_profile(profile) or "business_plan")


def _graph_enabled_profile(profile: str | None) -> bool:
    # 所有 profile 都启用 graph（通用图构建器支持所有 profile）
    return True


GRAPH_FIELD_ONLY_RELATIONS = {"HAS_FIELD", "EVIDENCED_BY", "PARSED_AS"}


def _graph_has_relation_intent(graph_intent: dict[str, Any] | None) -> bool:
    if not graph_intent:
        return False
    relations = {str(item) for item in graph_intent.get("relations") or [] if item}
    return bool(graph_intent.get("relation_query") or (relations - GRAPH_FIELD_ONLY_RELATIONS))


def _graph_default_for_profile(profile: str | None, target_fields: list[str], graph_intent: dict[str, Any]) -> bool:
    # 有字段查询时，graph 可以辅助
    if target_fields:
        return True
    # 有关系意图时，graph 应该启用
    return _graph_has_relation_intent(graph_intent)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
        if parsed < 0:
            return default
        return parsed
    except Exception:
        return default


def _normalize_weights(weights: dict[str, Any], enabled_routes: list[str]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for route in enabled_routes:
        value = _as_float(weights.get(route), 0.0)
        if value > 0:
            normalized[route] = value
    total = sum(normalized.values())
    if total <= 0:
        equal = 1.0 / max(len(enabled_routes), 1)
        return {route: equal for route in enabled_routes}
    return {route: round(value / total, 6) for route, value in normalized.items()}


def _resolve_fusion_weight_preset(preset_name: Any, profile: str) -> dict[str, float]:
    if not isinstance(preset_name, str) or not preset_name.strip():
        return {}
    preset = FUSION_WEIGHT_PRESETS.get(preset_name.strip())
    if not preset:
        return {}
    return dict(preset.get(profile) or preset.get("general_document") or {})


def resolve_weighted_rrf_config(
    profile: str | None,
    enabled_routes: list[str],
    *,
    mysql_config: dict[str, Any] | None = None,
    request_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve fusion config by priority: request options -> MySQL profile config -> code defaults."""
    normalized_profile = normalize_profile(profile) or profile or "general_document"
    mysql_config = _as_dict(mysql_config)
    request_options = _as_dict(request_options)
    request_fusion = _as_dict(request_options.get("fusion"))
    mysql_fusion = _as_dict(mysql_config.get("fusion") or mysql_config.get("retrieval_fusion"))
    default_weights = DEFAULT_FUSION_WEIGHTS.get(normalized_profile, DEFAULT_FUSION_WEIGHTS["general_document"])
    mysql_preset_name = mysql_fusion.get("weight_preset") or mysql_config.get("fusion_weight_preset")
    request_preset_name = request_fusion.get("weight_preset") or request_options.get("fusion_weight_preset")
    mysql_preset_weights = _resolve_fusion_weight_preset(mysql_preset_name, normalized_profile)
    request_preset_weights = _resolve_fusion_weight_preset(request_preset_name, normalized_profile)
    mysql_weights = _as_dict(mysql_fusion.get("weights"))
    request_weights = _as_dict(request_fusion.get("weights") or request_options.get("fusion_weights"))
    strategy = str(
        request_fusion.get("strategy")
        or request_options.get("fusion_strategy")
        or mysql_fusion.get("strategy")
        or "weighted_rrf"
    ).lower()
    rrf_k = int(
        _as_float(
            request_fusion.get("rrf_k", request_options.get("rrf_k", mysql_fusion.get("rrf_k", DEFAULT_RRF_K))),
            DEFAULT_RRF_K,
        )
    )
    rrf_k = max(10, min(rrf_k, 200))
    recall_multiplier = _as_float(
        request_fusion.get("recall_multiplier", request_options.get("recall_multiplier", mysql_fusion.get("recall_multiplier", 4))),
        4.0,
    )
    score_weight = _as_float(
        request_fusion.get("score_weight", request_options.get("fusion_score_weight", mysql_fusion.get("score_weight", 0.65))),
        0.65,
    )
    score_weight = max(0.0, min(score_weight, 1.0))
    rank_weight = _as_float(
        request_fusion.get("rank_weight", request_options.get("fusion_rank_weight", mysql_fusion.get("rank_weight", 1.0 - score_weight))),
        1.0 - score_weight,
    )
    rank_weight = max(0.0, min(rank_weight, 1.0))
    if score_weight + rank_weight <= 0:
        score_weight, rank_weight = 0.65, 0.35
    total_sr = score_weight + rank_weight
    score_weight = score_weight / total_sr
    rank_weight = rank_weight / total_sr
    multi_route_bonus = _as_float(
        request_fusion.get("multi_route_bonus", request_options.get("multi_route_bonus", mysql_fusion.get("multi_route_bonus", 0.005))),
        0.005,
    )
    route_confidence = _as_dict(request_fusion.get("route_confidence") or request_options.get("route_confidence") or mysql_fusion.get("route_confidence"))
    merged_weights = {**default_weights, **mysql_preset_weights, **mysql_weights, **request_preset_weights, **request_weights}
    active_routes = [route for route in enabled_routes if route in ALLOWED_RETRIEVE_MODES]
    normalized_strategy = strategy if strategy in {"score_aware", "adaptive_score_aware", "weighted_rrf", "rrf"} else "score_aware"
    if normalized_strategy == "rrf":
        normalized_strategy = "weighted_rrf"
    return {
        "strategy": normalized_strategy,
        "profile": normalized_profile,
        "weights": _normalize_weights(merged_weights, active_routes),
        "rrf_k": rrf_k,
        "score_weight": round(score_weight, 6),
        "rank_weight": round(rank_weight, 6),
        "multi_route_bonus": max(0.0, min(multi_route_bonus, 0.5)),
        "route_confidence": route_confidence,
        "recall_multiplier": max(1.0, min(recall_multiplier, 10.0)),
        "config_sources": {
            "request_override": bool(request_weights or request_fusion.get("rrf_k") is not None),
            "mysql_profile_config": bool(mysql_fusion),
            "mysql_weight_preset": mysql_preset_name if mysql_preset_weights else None,
            "request_weight_preset": request_preset_name if request_preset_weights else None,
            "code_default_profile": normalized_profile,
        },
    }


def detect_field_codes(query: str, profile: str | None = None) -> list[str]:
    field_aliases = _profile_aliases(profile)
    hits: list[str] = []
    for field_code, aliases in field_aliases.items():
        if any(alias in query for alias in aliases):
            hits.append(field_code)
    return hits


def _normalize_region_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 16:
        return ""
    text = re.sub(r"(辖区内|范围内|区域内|地区内|境内|内)$", "", text)
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
    return result[:10]


def _extract_regions(text: str) -> list[str]:
    rows = re.findall(r"[\u4e00-\u9fa5]{2,12}(?:省|市|县|区|镇|乡|村|街道)", text or "")
    return _normalize_region_list(rows)


def _extract_industries(text: str) -> list[str]:
    rows = re.findall(r"[\u4e00-\u9fa5]{2,20}(?:产业集群|产业|行业)", text or "")
    result: list[str] = []
    for item in rows:
        if item not in result:
            result.append(item)
    if not result:
        for keyword in ["草莓", "农业", "养殖", "种植", "粮食", "果蔬", "大蒜", "畜牧"]:
            if keyword in text and keyword not in result:
                result.append(keyword)
    return result[:10]


def _extract_orgs(text: str) -> list[str]:
    rows = re.findall(r"[\u4e00-\u9fa5]{3,40}(?:公司|银行|财政局|农业局|担保中心|合作社)", text or "")
    result: list[str] = []
    for item in rows:
        if item not in result:
            result.append(item)
    return result[:10]


def _simple_keywords(text: str, target_fields: list[str], profile: str | None = None) -> list[str]:
    field_aliases = _profile_aliases(profile)
    query = text or ""
    stop_words = {"什么", "多少", "几个", "哪些", "哪个", "一下", "这个", "那个", "一下子", "请问", "帮我", "给我", "查下", "查一下"}
    seeded = _extract_regions(query) + _extract_industries(query) + _extract_orgs(query)
    seeded.extend(alias for field in target_fields for alias in field_aliases.get(field, [])[:2] if alias in query)
    seeded.extend(item for item in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,16}", query) if item not in stop_words)
    result: list[str] = []
    for item in seeded:
        if item and item not in result:
            result.append(item)
    return result[:12]


# 疑问词前缀：正则 `{2,20}(?:贷|保|方案|业务|产品)` 会贪婪地把"怎么申请贷"、
# "怎么缴纳保"这类疑问句片段误当成产品/方案锚点。这类锚点一旦进入文档范围打分，
# 会因匹配不到任何文件名而触发全量 document_mismatch_penalty 与 confidence 的
# product_scope_mismatch ×0.2 惩罚，把置信度压到 0.2 以下。必须剔除。
_INTERROGATIVE_PREFIXES = (
    "怎么", "如何", "怎样", "咋", "哪里", "哪儿", "什么", "哪些", "哪个",
    "为什么", "为啥", "是否", "能否", "能不能", "是不是", "怎么办",
)


def _scope_anchor_candidates(text: str, target_fields: list[str], profile: str | None = None) -> list[str]:
    field_aliases = _profile_aliases(profile)
    field_terms = {alias for field in target_fields for alias in field_aliases.get(field, [])}
    field_terms.update({"多少", "什么", "哪些", "如何", "怎么", "授信", "额度", "期限", "方案"})
    candidates = _extract_orgs(text)
    candidates.extend(item for item in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:贷|保|方案|业务|产品)", text or ""))
    # Also match known short product names that the regex pattern might miss
    # (e.g. "农贸贷" appears in "农贸贷的反担保" but gets eaten by the 贷 suffix regex
    #  only when preceded by enough chars; explicit matching is more reliable).
    for name in KNOWN_PRODUCT_NAMES:
        if name in (text or ""):
            candidates.append(name)
    result: list[str] = []
    for item in candidates:
        item = str(item).strip()
        if not item or item in field_terms or any(term and item == term for term in field_terms):
            continue
        if item.startswith(_INTERROGATIVE_PREFIXES):
            continue
        if item not in result:
            result.append(item)
    return result[:8]


def _query_route_features(query: str, target_fields: list[str], graph_intent: dict[str, Any] | None = None) -> dict[str, Any]:
    text = query or ""
    question_like = bool(re.search(r"(多少|哪些|什么|如何|怎么|是否|有没有|能不能|需要.*吗|是什么|怎么办)", text))
    possible_question_like = question_like and len(text.strip()) <= 80
    field_alias_exact = bool(target_fields)
    relation_intent_hit = _graph_has_relation_intent(graph_intent)
    route_reason: dict[str, str] = {}
    if possible_question_like:
        route_reason["qa"] = "query looks like a prebuilt possible question"
        route_reason["section_summary"] = "query can benefit from section possible_questions"
    if field_alias_exact:
        route_reason["structured"] = f"exact field alias hit: {', '.join(target_fields)}"
        route_reason["bm25"] = "field alias should match keyword/BM25 evidence"
    if relation_intent_hit:
        route_reason["graph"] = f"relation intent: {', '.join((graph_intent or {}).get('relations') or [])}"
    route_reason.setdefault("vector", "semantic fallback for paraphrases")
    return {
        "possible_question_like": possible_question_like,
        "field_alias_exact": field_alias_exact,
        "relation_intent_hit": relation_intent_hit,
        "route_reason": route_reason,
    }


def _comparison_query_info(query: str, scope_anchors: list[str], target_fields: list[str]) -> dict[str, Any]:
    text = query or ""
    markers = ["对比", "比较", "区别", "分别", "各自", "和", "与"]
    normalized_anchors: list[str] = []
    for anchor in scope_anchors:
        parts = re.split(r"[和与]", anchor) if any(sep in anchor for sep in ("和", "与")) else [anchor]
        for part in parts:
            part = part.strip()
            if part and part not in normalized_anchors:
                normalized_anchors.append(part)
    comparison_query = len(normalized_anchors) >= 2 and any(marker in text for marker in markers)
    return {
        "comparison_query": comparison_query,
        "comparison_anchors": normalized_anchors if comparison_query else [],
        "comparison_fields": target_fields if comparison_query else [],
        "comparison_markers": [marker for marker in markers if marker in text],
    }


def heuristic_query_understanding(query: str, top_k: int, profile: str | None = None) -> dict[str, Any]:
    normalized_profile = normalize_profile(profile) or "business_plan"
    expansion = expand_colloquial_query(query, normalized_profile)
    detected_fields = detect_field_codes(query, normalized_profile)
    target_fields: list[str] = []
    for field_code in [*detected_fields, *(expansion.get("expanded_field_codes") or [])]:
        if field_code and field_code not in target_fields:
            target_fields.append(field_code)
    intent_type = "field_query" if target_fields else "semantic_query"
    faq_likelihood = 0.2 if ("怎么办" in query or "如何" in query or "怎么" in query) else 0.05
    graph_likelihood = 0.0
    graph_intent = infer_graph_intent(query, {
        "profile": normalized_profile,
        "target_field_codes": target_fields,
        "scope_anchor_candidates": _scope_anchor_candidates(query, target_fields, normalized_profile),
        "entities": {
            "regions": _extract_regions(query),
            "industries": _extract_industries(query),
            "organizations": _extract_orgs(query),
        },
    })
    route_features = _query_route_features(query, target_fields, graph_intent)
    graph_default = _graph_default_for_profile(normalized_profile, target_fields, graph_intent)
    graph_likelihood = 0.9 if graph_default else 0.0
    retrieve_modes = ["structured", "section_summary", "graph", "bm25", "vector"] if graph_default else ["structured", "section_summary", "bm25", "vector"]
    if faq_likelihood >= 0.2 or route_features.get("possible_question_like"):
        retrieve_modes = ["qa"] + retrieve_modes
    retrieve_modes = [mode for mode in retrieve_modes if mode in ALLOWED_RETRIEVE_MODES]
    scope_anchors = _scope_anchor_candidates(query, target_fields, normalized_profile)
    comparison_info = _comparison_query_info(query, scope_anchors, target_fields)
    result = {
        "intent_type": intent_type,
        "query_rewrite": query,
        "keywords": _simple_keywords(query, target_fields, normalized_profile) + [term for term in expansion.get("expanded_terms") or [] if term not in _simple_keywords(query, target_fields, normalized_profile)],
        "scope_anchor_candidates": scope_anchors,
        "target_field_codes": target_fields,
        **comparison_info,
        "expanded_terms": expansion.get("expanded_terms") or [],
        "expanded_field_codes": expansion.get("expanded_field_codes") or [],
        "expansion_reason": expansion.get("expansion_reason") or "",
        "matched_colloquial_terms": expansion.get("matched_terms") or [],
        "entities": {
            "regions": _extract_regions(query),
            "industries": _extract_industries(query),
            "organizations": _extract_orgs(query),
        },
        "retrieve_modes": retrieve_modes,
        "faq_likelihood": faq_likelihood,
        "graph_likelihood": graph_likelihood,
        "analysis_required": "比较" in query or "哪个更" in query or "类似" in query,
        "source": "heuristic",
        "profile": normalized_profile,
        "top_k": top_k,
        "route_features": {key: value for key, value in route_features.items() if key != "route_reason"},
        "route_reason": route_features["route_reason"],
    }
    if graph_intent["relations"] and _graph_default_for_profile(normalized_profile, target_fields, graph_intent):
        result["graph_intent"] = graph_intent
        if "graph" not in result["retrieve_modes"]:
            result["retrieve_modes"].insert(0, "graph")
            result["graph_likelihood"] = max(float(result["graph_likelihood"]), 0.65)
    return result


def understand_query(query: str, top_k: int, profile: str | None = None) -> dict[str, Any]:
    normalized_profile = normalize_profile(profile) or "business_plan"
    fallback = heuristic_query_understanding(query, top_k, normalized_profile)
    try:
        client = JsonChatClient("QUERY_UNDERSTANDING", default_model=True)
    except Exception:
        return fallback

    try:
        prompt = _build_query_understanding_prompt(query, top_k, normalized_profile)
        parsed = client.complete_json(
            system_prompt=(
                "你是企业知识问答查询理解器。\n"
                "你的职责是把用户的自然语言问题转换成结构化的检索计划。\n"
                "规则：\n"
                "1. 只返回 JSON，不要输出解释。\n"
                "2. query_rewrite 必须把口语化表述转为书面检索语句，补全省略的主语和宾语。\n"
                "3. target_field_codes 必须精确匹配用户实际在问的字段，不要过度猜测。\n"
                "4. entities.regions 只能填写用户问题中明确作为地域过滤条件的行政区划名称。\n"
                "   房地产市场/证券市场/期货市场等不是地区，不要截取。\n"
                "5. keywords 应包含问题中的核心实体和属性词，去除停用词。\n"
                "6. retrieve_modes 只能从 qa/graph/bm25/vector/structured/section_summary 中选择。"
            ),
            user_prompt=prompt,
            temperature=0,
            max_tokens=1200,
        )
        return _merge_understanding(parsed, fallback, top_k, normalized_profile)
    except Exception:
        return fallback


def cached_understand_query(query: str, top_k: int, profile: str | None = None, cache_context: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_profile = normalize_profile(profile) or "business_plan"
    payload = {
        "query": query,
        "top_k": top_k,
        "profile": normalized_profile,
        "context": cache_context or {},
    }
    cached = get_json_cached("query_understanding", payload)
    if isinstance(cached, dict):
        result = dict(cached)
        result["cache_hit"] = True
        return result
    result = understand_query(query, top_k, normalized_profile)
    set_json_cached(
        "query_understanding",
        payload,
        result,
        ttl_env="QUERY_UNDERSTANDING_CACHE_TTL_SECONDS",
        default_ttl_seconds=86400,
    )
    return result


def _build_query_understanding_prompt(query: str, top_k: int, profile: str | None = None) -> str:
    field_aliases = _profile_aliases(profile)
    field_hints = _profile_hints(profile)
    schema = {
        "intent_type": "field_query | faq_query | semantic_query | compare_query",
        "query_rewrite": "更适合检索的书面化问句",
        "keywords": ["关键词1", "关键词2"],
        "scope_anchor_candidates": ["用户明确提到的产品、方案、主体名称"],
        "target_field_codes": list(field_aliases.keys()),
        "entities": {"regions": [], "industries": [], "organizations": []},
        "retrieve_modes": ["qa", "graph", "bm25", "vector", "structured", "section_summary"],
        "faq_likelihood": 0.0,
        "graph_likelihood": 0.0,
        "analysis_required": False,
    }
    field_guide = [{"field_code": field_code, "hint": field_hints.get(field_code, ""), "aliases": aliases} for field_code, aliases in field_aliases.items()]
    return (
        "请根据用户问题生成结构化检索计划。\n\n"
        "## 要求\n"
        "1. intent_type 分类规则：\n"
        "   - field_query：问某个具体字段（如额度、期限、准入条件）\n"
        "   - faq_query：怎么办/如何操作类问题\n"
        "   - compare_query：包含比较/对比/哪个更好\n"
        "   - semantic_query：其他开放性问题\n"
        "2. target_field_codes 必须精确对应用户实际在问的字段，不要猜测。\n"
        "3. retrieve_modes 只能从 qa、graph、bm25、vector、structured、section_summary 中选择。\n"
        "   字段型问题优先 graph+bm25+structured；FAQ 优先 qa；开放性问题用 bm25+vector+section_summary。\n"
        "4. query_rewrite 要补全口语表述，将非标准用词转为标准业务术语。\n"
        "5. entities.regions 只填写用户问题中明确作为地域过滤条件的行政区划。\n"
        "   房地产市场/证券市场/期货市场等不是地区，禁止截取。\n"
        "6. scope_anchor_candidates 只填写用户明确提到的产品、方案、业务、主体名称，例如“强村贷”。\n"
        "7. keywords 应包含核心实体词和属性词，去除疑问词和停用词。\n"
        "8. 只返回一个 JSON 对象。\n\n"
        f"当前 Profile：{normalize_profile(profile) or profile or 'business_plan'}。\n"
        f"最多返回 top_k={top_k} 条候选。\n"
        f"字段参考：{json.dumps(field_guide, ensure_ascii=False)}\n"
        f"返回 JSON 结构参考：{json.dumps(schema, ensure_ascii=False)}\n"
        f"用户问题：{query}"
    )


def _merge_understanding(parsed: dict[str, Any], fallback: dict[str, Any], top_k: int, profile: str | None = None) -> dict[str, Any]:
    field_aliases = _profile_aliases(profile)
    graph_allowed = _graph_enabled_profile(profile)
    retrieve_modes = [
        mode
        for mode in parsed.get("retrieve_modes") or fallback["retrieve_modes"]
        if isinstance(mode, str) and mode in ALLOWED_RETRIEVE_MODES
    ]
    if not graph_allowed:
        retrieve_modes = [mode for mode in retrieve_modes if mode != "graph"]
    if not retrieve_modes:
        retrieve_modes = fallback["retrieve_modes"]
    target_field_codes = [
        code
        for code in parsed.get("target_field_codes") or fallback["target_field_codes"]
        if isinstance(code, str) and code in field_aliases
    ]
    entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
    # Bug fix: use 'is not None' instead of 'or' to avoid overriding intentional
    # empty lists from LLM (e.g., LLM correctly determines no region filter needed
    # and returns []). Python's 'or' treats [] as falsy, which would incorrectly
    # fall back to regex-extracted entities.
    parsed_regions = _normalize_region_list(entities.get("regions"))
    parsed_industries = _normalize_list(entities.get("industries"))
    parsed_organizations = _normalize_list(entities.get("organizations"))
    merged_entities = {
        "regions": parsed_regions if entities.get("regions") is not None else fallback["entities"]["regions"],
        "industries": parsed_industries if entities.get("industries") is not None else fallback["entities"]["industries"],
        "organizations": parsed_organizations if entities.get("organizations") is not None else fallback["entities"]["organizations"],
    }
    result = {
        "intent_type": parsed.get("intent_type") or fallback["intent_type"],
        "query_rewrite": (parsed.get("query_rewrite") or fallback["query_rewrite"] or "").strip() or fallback["query_rewrite"],
        "keywords": _normalize_list(parsed.get("keywords")) or fallback["keywords"],
        "scope_anchor_candidates": _normalize_list(parsed.get("scope_anchor_candidates")) or fallback.get("scope_anchor_candidates") or [],
        "target_field_codes": target_field_codes,
        "comparison_query": bool(fallback.get("comparison_query")),
        "comparison_anchors": fallback.get("comparison_anchors") or [],
        "comparison_fields": fallback.get("comparison_fields") or [],
        "comparison_markers": fallback.get("comparison_markers") or [],
        "expanded_terms": fallback.get("expanded_terms") or [],
        "expanded_field_codes": fallback.get("expanded_field_codes") or [],
        "expansion_reason": fallback.get("expansion_reason") or "",
        "matched_colloquial_terms": fallback.get("matched_colloquial_terms") or [],
        "entities": merged_entities,
        "retrieve_modes": retrieve_modes,
        "faq_likelihood": _normalize_probability(parsed.get("faq_likelihood"), fallback["faq_likelihood"]),
        "graph_likelihood": _normalize_probability(parsed.get("graph_likelihood"), fallback["graph_likelihood"]),
        "analysis_required": bool(parsed.get("analysis_required", fallback["analysis_required"])),
        "source": "model",
        "profile": normalize_profile(profile) or profile or "business_plan",
        "top_k": top_k,
    }
    graph_intent = infer_graph_intent(result["query_rewrite"] or fallback.get("query_rewrite") or "", result)
    route_features = _query_route_features(result["query_rewrite"], target_field_codes, graph_intent)
    result["route_features"] = {key: value for key, value in route_features.items() if key != "route_reason"}
    result["route_reason"] = {**(fallback.get("route_reason") or {}), **route_features["route_reason"]}
    if graph_intent["relations"] and _graph_default_for_profile(result.get("profile"), target_field_codes, graph_intent):
        result["graph_intent"] = graph_intent
        if "graph" not in result["retrieve_modes"]:
            result["retrieve_modes"].insert(0, "graph")
            result["graph_likelihood"] = max(float(result["graph_likelihood"]), 0.65)
    else:
        result["retrieve_modes"] = [mode for mode in result["retrieve_modes"] if mode != "graph"]
        result["graph_likelihood"] = min(float(result["graph_likelihood"]), 0.20)
    return result


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        item = str(item).strip()
        if item and item not in result:
            result.append(item)
    return result[:12]


def _normalize_probability(value: Any, fallback: float) -> float:
    try:
        score = float(value)
        if score < 0:
            return 0.0
        if score > 1:
            return 1.0
        return score
    except Exception:
        return fallback


def _graph_relation_score(*, relationship_weight: Any = None, evidence_weight: Any = None, graph_depth: Any = 1, matched_scope: bool = False, base: float = 0.82) -> float:
    try:
        weight = float(relationship_weight)
    except Exception:
        weight = 1.0
    try:
        evidence = float(evidence_weight)
    except Exception:
        evidence = 0.0
    try:
        depth = max(1, int(graph_depth or 1))
    except Exception:
        depth = 1
    score = base + min(max(weight, 0.0), 1.0) * 0.10 + min(max(evidence, 0.0), 1.0) * 0.04 - (depth - 1) * 0.06
    if matched_scope:
        score += 0.06
    return round(max(0.05, min(score, 0.99)), 4)


def _dedupe_graph_rows(rows: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    best: dict[tuple[Any, Any, Any, Any], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("file_node_id"), row.get("relationship_type") or tuple(row.get("relationship_path") or []), row.get("field_code"), row.get("related_name"))
        existing = best.get(key)
        if not existing or float(row.get("score") or 0.0) > float(existing.get("score") or 0.0):
            best[key] = row
    return sorted(best.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)[:top_k]


def graph_query(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    query: str,
    file_node_ids: list[int] | None,
    index_generations: list[str] | None,
    top_k: int,
    understanding: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from neo4j import GraphDatabase

    profile = understanding.get("profile") if understanding else None
    if not _graph_enabled_profile(profile):
        return []
    understanding = understanding or heuristic_query_understanding(query, top_k, profile)
    profile = understanding.get("profile") or profile or "business_plan"
    field_codes = understanding.get("target_field_codes") or detect_field_codes(query, profile)
    graph_intent = understanding.get("graph_intent") if isinstance(understanding.get("graph_intent"), dict) else infer_graph_intent(query, understanding)
    if not _graph_default_for_profile(profile, field_codes, graph_intent):
        return []
    allowed_relation_types = graph_query_relations(profile)
    relation_types = [
        relation
        for relation in (graph_intent.get("relations") or [])
        if relation in allowed_relation_types
    ]
    # 过滤掉 EVIDENCED_BY（不作为查询关系，只作为证据边）
    relation_types = [r for r in relation_types if r != "EVIDENCED_BY"]
    scope_anchors = [str(item) for item in understanding.get("scope_anchor_candidates") or [] if str(item)]
    entities = understanding.get("entities") or {}
    if not field_codes and not relation_types:
        return []

    # 判断使用哪种查询模式
    has_entity_nodes = "Entity" in allowed_node_types(profile)
    has_business_plan = "BusinessPlan" in allowed_node_types(profile)

    drv = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with drv.session() as session:
            rows: list[dict[str, Any]] = []

            # ── 模式 1: 通用 Entity 关系查询 ──────────────────
            if has_entity_nodes and relation_types:
                entity_rows = _graph_query_entity_relations(
                    session, kb_id, relation_types, scope_anchors,
                    file_node_ids, index_generations, entities, top_k, graph_intent,
                )
                rows.extend(entity_rows)

            # ── 模式 2: 旧 BusinessPlan 查询 (向后兼容) ───────
            if has_business_plan:
                bp_relation_types = [r for r in relation_types if r in {"HAS_FIELD", "IN_REGION", "IN_INDUSTRY", "RELATED_TO"}]
                if bp_relation_types or field_codes:
                    bp_rows = _graph_query_business_plan(
                        session, kb_id, field_codes, bp_relation_types, scope_anchors,
                        file_node_ids, index_generations, entities, top_k, graph_intent, understanding,
                    )
                    rows.extend(bp_rows)

            return _dedupe_graph_rows(rows, top_k)
    finally:
        drv.close()


_GRAPH_EXPANSION_EXCLUDED_RELATIONS = {"EVIDENCED_BY", "PARSED_AS", "MENTIONS", "MEMBER_OF_COMMUNITY"}


def graph_expand_query(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    query: str,
    seed_candidates: list[dict[str, Any]],
    file_node_ids: list[int] | None,
    index_generations: list[str] | None,
    top_k: int,
    *,
    profile: str | None = None,
    seed_top_k: int = 8,
    max_hops: int = 1,
    max_nodes_per_seed: int = 8,
    max_total_nodes: int | None = None,
    min_confidence: float = 0.0,
) -> list[dict[str, Any]]:
    """Expand graph relations from evidence chunks recalled by non-graph routes.

    Neo4j is an enrichment stage here, not a second full-text index.  Every
    returned fact is anchored to a seed Chunk and carries a compact, auditable
    node/relationship path plus a source chunk for citation.
    """
    from neo4j import GraphDatabase

    seeds_by_chunk: dict[int, dict[str, Any]] = {}
    for candidate in seed_candidates:
        chunk_id = candidate.get("chunk_id") or candidate.get("primary_chunk_id")
        if not chunk_id:
            continue
        try:
            chunk_id = int(chunk_id)
        except (TypeError, ValueError):
            continue
        seed = {
            "chunk_id": chunk_id,
            "file_node_id": candidate.get("file_node_id"),
            "score": float(candidate.get("score") or 0.0),
            "route_names": candidate.get("route_names") or [],
        }
        current = seeds_by_chunk.get(chunk_id)
        if current is None or seed["score"] > current["score"]:
            seeds_by_chunk[chunk_id] = seed
    seeds = sorted(seeds_by_chunk.values(), key=lambda item: item["score"], reverse=True)[:max(1, seed_top_k)]
    if not seeds:
        return []

    relation_types = sorted(
        relation
        for relation in allowed_graph_edge_types(profile)
        if relation not in _GRAPH_EXPANSION_EXCLUDED_RELATIONS
    )
    if not relation_types:
        return []
    max_hops = max(1, min(int(max_hops or 1), 2))
    max_nodes_per_seed = max(1, min(int(max_nodes_per_seed or 8), 50))
    max_total_nodes = max(1, min(int(max_total_nodes or max(top_k * 4, top_k)), 200))
    min_confidence = max(0.0, min(float(min_confidence or 0.0), 1.0))
    cypher = f"""
        WITH $seed AS seed
        MATCH (seed_chunk:Chunk {{kb_id: $kb_id, chunk_id: seed.chunk_id}})
        WHERE (size($file_node_ids) = 0 OR seed_chunk.file_node_id IN $file_node_ids)
          AND (size($index_generations) = 0 OR seed_chunk.index_generation IN $index_generations)
        MATCH (source)-[:EVIDENCED_BY]->(seed_chunk)
        MATCH path=(source)-[rels*1..{max_hops}]-(related)
        WHERE related <> source
          AND all(rel IN rels WHERE type(rel) IN $relation_types)
          AND all(rel IN rels WHERE coalesce(rel.confidence, 0.5) >= $min_confidence)
        WITH seed, seed_chunk, source, related, path, rels,
             head([node IN nodes(path) WHERE node:Assertion]) AS assertion_node
        OPTIONAL MATCH (assertion_node)-[assertion_ev:EVIDENCED_BY]->(assertion_chunk:Chunk)
        WHERE (size($file_node_ids) = 0 OR assertion_chunk.file_node_id IN $file_node_ids)
          AND (size($index_generations) = 0 OR assertion_chunk.index_generation IN $index_generations)
        OPTIONAL MATCH (related)-[ev:EVIDENCED_BY]->(related_chunk:Chunk)
        WHERE (size($file_node_ids) = 0 OR related_chunk.file_node_id IN $file_node_ids)
          AND (size($index_generations) = 0 OR related_chunk.index_generation IN $index_generations)
        WITH seed, seed_chunk, source, related, path, rels, assertion_node,
             coalesce(assertion_chunk, related_chunk, seed_chunk) AS evidence_chunk,
             assertion_ev, ev
        RETURN seed.chunk_id AS seed_chunk_id,
               seed.score AS seed_score,
               seed.route_names AS seed_routes,
               labels(source) AS source_labels,
               properties(source) AS source_properties,
               [node IN nodes(path) | {{labels: labels(node), properties: properties(node)}}] AS path_nodes,
               [rel IN rels | type(rel)] AS relationship_path,
               [rel IN rels | properties(rel)] AS relationship_properties,
               labels(related) AS related_labels,
               properties(related) AS related_properties,
               size([(related)--() | 1]) AS related_degree,
               size([
                   (related)-[:EVIDENCED_BY]->(support_chunk:Chunk)
                   WHERE support_chunk.chunk_id IN $seed_chunk_ids
                     AND (size($file_node_ids) = 0 OR support_chunk.file_node_id IN $file_node_ids)
                   | support_chunk
               ]) + size([
                   (assertion_node)-[:EVIDENCED_BY]->(assertion_support:Chunk)
                   WHERE assertion_support.chunk_id IN $seed_chunk_ids
                     AND (size($file_node_ids) = 0 OR assertion_support.file_node_id IN $file_node_ids)
                   | assertion_support
               ]) AS selected_seed_links,
               evidence_chunk.chunk_id AS chunk_id,
               evidence_chunk.file_node_id AS file_node_id,
               evidence_chunk.title_cn AS title,
               evidence_chunk.content_preview AS evidence_text,
               evidence_chunk.page_start AS page_no,
               coalesce(assertion_ev.evidence_quote, ev.evidence_quote, last(rels).evidence_quote, '') AS evidence_quote,
               coalesce(assertion_ev.weight, ev.weight, last(rels).weight, 0.5) AS evidence_weight
        ORDER BY seed.score DESC, size(rels) ASC, evidence_weight DESC
        LIMIT $query_limit
    """
    drv = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with drv.session() as session:
            records: list[Any] = []
            for seed in seeds:
                records.extend(session.run(
                    cypher,
                    kb_id=kb_id,
                    seed=seed,
                    seed_chunk_ids=[item["chunk_id"] for item in seeds],
                    file_node_ids=file_node_ids or [],
                    index_generations=index_generations or [],
                    relation_types=relation_types,
                    min_confidence=min_confidence,
                    query_limit=max_nodes_per_seed,
                ))
            rows: list[dict[str, Any]] = []
            query_terms = {term.lower() for term in _simple_keywords(query, [], profile) if len(term) >= 2}
            for record in records:
                raw = dict(record)
                source_props = dict(raw.pop("source_properties") or {})
                related_props = dict(raw.pop("related_properties") or {})
                if related_props.get("graph_role") == "assertion":
                    continue
                raw_path_nodes = raw.pop("path_nodes", []) or []
                relationship_path = [str(item) for item in raw.get("relationship_path") or []]
                relationship_properties = [dict(item or {}) for item in raw.pop("relationship_properties", [])]
                source_name = str(source_props.get("name_cn") or source_props.get("subject_text") or source_props.get("node_key") or "知识对象")
                related_name = str(related_props.get("name_cn") or related_props.get("object_text") or related_props.get("value_text") or related_props.get("node_key") or "关联对象")
                related_value = str(related_props.get("value_text") or related_props.get("object_text") or "").strip()
                assertion_props = next(
                    (
                        dict((item or {}).get("properties") or {})
                        for item in raw_path_nodes
                        if dict((item or {}).get("properties") or {}).get("graph_role") == "assertion"
                    ),
                    {},
                )
                semantic_relationship_path = [item for item in relationship_path if item != "ASSERTS"]
                if assertion_props:
                    source_name = str(assertion_props.get("subject_name") or source_name)
                    related_name = str(assertion_props.get("object_name") or related_name)
                    predicate = str(assertion_props.get("predicate") or (semantic_relationship_path[-1] if semantic_relationship_path else "RELATED_TO"))
                    fact = f"{source_name} --{predicate}--> {related_name}"
                else:
                    fact = f"{source_name} --{' / '.join(semantic_relationship_path or relationship_path)}--> {related_name}"
                if related_value and related_value != related_name:
                    fact = f"{fact}：{related_value}"
                evidence_quote = str(raw.get("evidence_quote") or "").strip()
                path_nodes = []
                for path_node in raw_path_nodes:
                    node_properties = dict((path_node or {}).get("properties") or {})
                    node_name = str(node_properties.get("name_cn") or node_properties.get("subject_text") or node_properties.get("object_text") or node_properties.get("node_key") or "知识对象")
                    if node_properties.get("graph_role") == "assertion":
                        continue
                    path_nodes.append({
                        "labels": (path_node or {}).get("labels") or [],
                        "name": node_name,
                        "node_key": node_properties.get("node_key"),
                        "graph_role": node_properties.get("graph_role"),
                    })
                if assertion_props:
                    path_nodes = [
                        {
                            "labels": [],
                            "name": source_name,
                            "node_key": assertion_props.get("subject_node_key"),
                            "graph_role": "subject",
                        },
                        {
                            "labels": raw.get("related_labels") or [],
                            "name": related_name,
                            "node_key": assertion_props.get("object_node_key") or related_props.get("node_key"),
                            "graph_role": "object",
                        },
                    ]
                if not path_nodes:
                    path_nodes = [
                        {"labels": raw.get("source_labels") or [], "name": source_name, "node_key": source_props.get("node_key")},
                        {"labels": raw.get("related_labels") or [], "name": related_name, "node_key": related_props.get("node_key")},
                    ]
                graph_path = {
                    "schema_version": "graph_projection_v2",
                    "seed_chunk_id": raw.get("seed_chunk_id"),
                    "seed_routes": raw.get("seed_routes") or [],
                    "nodes": path_nodes,
                    "relationships": semantic_relationship_path or relationship_path,
                    "depth": len(semantic_relationship_path or relationship_path),
                    "traversal_depth": len(relationship_path),
                    "fact": fact,
                    "evidence_quote": evidence_quote,
                    "relation_id": assertion_props.get("relation_id"),
                    "confidence_label": assertion_props.get("confidence_label"),
                }
                lexical_bonus = 0.0
                fact_lower = fact.lower()
                matched_terms = {term for term in query_terms if term in fact_lower}
                if query_terms:
                    lexical_bonus = min(0.08, 0.08 * len(matched_terms) / max(1, len(query_terms)))
                semantic_weights = [
                    float(props.get("weight") or 0.0)
                    for rel_type, props in zip(relationship_path, relationship_properties)
                    if rel_type != "ASSERTS"
                ]
                relation_weight = min(semantic_weights or [float(raw.get("evidence_weight") or 0.5)])
                generic_penalty = 0.10 if "RELATED_TO" in relationship_path else 0.0
                related_degree = int(raw.get("related_degree") or 0)
                hub_penalty = min(0.15, max(0, related_degree - 8) * 0.004)
                selected_seed_links = int(raw.get("selected_seed_links") or 0)
                link_bonus = min(0.12, max(0, selected_seed_links - 1) * 0.04)
                row = {
                    **raw,
                    "kb_id": kb_id,
                    "relationship_type": relationship_path[-1] if relationship_path else None,
                    "related_name": related_name,
                    "value_text": related_value or fact,
                    "content": fact,
                    "hit_type": "graph_relation",
                    "route": "graph",
                    "type": "relation_hit",
                    "match_type": "seed_chunk_relation",
                    "reason": f"seed_chunk={raw.get('seed_chunk_id')}, depth={len(relationship_path)}, degree={related_degree}, links={selected_seed_links}",
                    "evidence_chain": [source_name, *(semantic_relationship_path or relationship_path), related_name, f"chunk_{raw.get('chunk_id')}"] if raw.get("chunk_id") else [source_name, *(semantic_relationship_path or relationship_path), related_name],
                    "graph_path": graph_path,
                    "graph_depth": len(relationship_path),
                    "score": min(
                        0.99,
                        max(0.05, (float(raw.get("seed_score") or 0.0) * 0.52) + (relation_weight * 0.30) + lexical_bonus + link_bonus - generic_penalty - hub_penalty - ((len(relationship_path) - 1) * 0.05)),
                    ),
                }
                rows.append(row)
            support_by_fact: dict[tuple[Any, ...], set[Any]] = {}
            for row in rows:
                path = row.get("graph_path") or {}
                key = (
                    path.get("relation_id") or path.get("fact"),
                    row.get("chunk_id"),
                )
                support_by_fact.setdefault(key, set()).add(path.get("seed_chunk_id"))
            for row in rows:
                path = row.get("graph_path") or {}
                key = (path.get("relation_id") or path.get("fact"), row.get("chunk_id"))
                support_ids = sorted(item for item in support_by_fact.get(key, set()) if item is not None)
                support_count = len(support_ids)
                row["seed_support_count"] = support_count
                row["seed_support_chunk_ids"] = support_ids
                path["seed_support_count"] = support_count
                path["seed_support_chunk_ids"] = support_ids
                row["score"] = min(0.99, float(row.get("score") or 0.0) + min(0.14, max(0, support_count - 1) * 0.04))
            best_by_fact: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
            for row in rows:
                path = row.get("graph_path") or {}
                nodes = path.get("nodes") or []
                fact_key = (
                    row.get("chunk_id"),
                    (nodes[0] or {}).get("node_key") if len(nodes) > 0 else None,
                    (nodes[-1] or {}).get("node_key") if len(nodes) > 1 else None,
                )
                current = best_by_fact.get(fact_key)
                if current is None or float(row.get("score") or 0.0) > float(current.get("score") or 0.0):
                    best_by_fact[fact_key] = row
            bounded = sorted(best_by_fact.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)[:max_total_nodes]
            return bounded[:top_k]
    finally:
        drv.close()


# 通用关系类型集合（用于 Entity 查询）
_GENERIC_RELATION_TYPES = {
    "APPLIES_TO", "EXCLUDES", "REQUIRES", "CONSTRAINS",
    "RESPONSIBLE_FOR", "APPROVES", "REFERENCES", "DEPENDS_ON",
    "CONTAINS", "HAS_ATTRIBUTE", "PART_OF", "SAME_AS",
}


def _graph_query_entity_relations(
    session: Any,
    kb_id: int,
    relation_types: list[str],
    scope_anchors: list[str],
    file_node_ids: list[int] | None,
    index_generations: list[str] | None,
    entities: dict[str, Any],
    top_k: int,
    graph_intent: dict[str, Any],
) -> list[dict[str, Any]]:
    """通用 Entity 关系查询: Entity -> (各种关系) -> 目标节点。"""
    # 只用通用关系类型
    generic_relations = [r for r in relation_types if r in _GENERIC_RELATION_TYPES]
    if not generic_relations:
        return []

    # 先尝试带 scope_anchors 查询，如果结果为空则去掉 anchor 重试
    cypher_with_anchor = """
        MATCH (e:Entity {kb_id: $kb_id})-[rel]->(n)
        WHERE type(rel) IN $relation_types
          AND (size($file_node_ids) = 0 OR e.file_node_id IN $file_node_ids)
          AND (
            any(anchor IN $scope_anchors WHERE e.name_cn CONTAINS anchor)
            OR any(anchor IN $scope_anchors WHERE n.name_cn CONTAINS anchor)
            OR any(anchor IN $scope_anchors WHERE n.value_text CONTAINS anchor)
          )
        OPTIONAL MATCH (n)-[ev:EVIDENCED_BY]->(c:Chunk)
        WITH e, rel, n, c, ev
        WHERE c IS NOT NULL
        RETURN $kb_id AS kb_id,
               e.file_node_id AS file_node_id,
               e.name_cn AS plan_name,
               type(rel) AS relationship_type,
               coalesce(rel.weight, 0.5) AS relationship_weight,
               coalesce(rel.confidence, 0.5) AS rel_confidence,
               labels(n)[0] AS related_node_type,
               n.name_cn AS related_name,
               n.value_text AS value_text,
               n.domain_type AS domain_type,
               c.chunk_id AS chunk_id,
               c.title_cn AS title,
               c.content_preview AS evidence_text,
               c.page_start AS page_no,
               coalesce(ev.weight, 0.5) AS evidence_weight,
               coalesce(ev.evidence_quote, '') AS evidence_quote
        LIMIT $top_k
    """
    cypher_no_anchor = """
        MATCH (e:Entity {kb_id: $kb_id})-[rel]->(n)
        WHERE type(rel) IN $relation_types
          AND (size($file_node_ids) = 0 OR e.file_node_id IN $file_node_ids)
        OPTIONAL MATCH (n)-[ev:EVIDENCED_BY]->(c:Chunk)
        WITH e, rel, n, c, ev
        WHERE c IS NOT NULL
        RETURN $kb_id AS kb_id,
               e.file_node_id AS file_node_id,
               e.name_cn AS plan_name,
               type(rel) AS relationship_type,
               coalesce(rel.weight, 0.5) AS relationship_weight,
               coalesce(rel.confidence, 0.5) AS rel_confidence,
               labels(n)[0] AS related_node_type,
               n.name_cn AS related_name,
               n.value_text AS value_text,
               n.domain_type AS domain_type,
               c.chunk_id AS chunk_id,
               c.title_cn AS title,
               c.content_preview AS evidence_text,
               c.page_start AS page_no,
               coalesce(ev.weight, 0.5) AS evidence_weight,
               coalesce(ev.evidence_quote, '') AS evidence_quote
        LIMIT $top_k
    """
    if scope_anchors:
        result = session.run(
            cypher_with_anchor,
            kb_id=kb_id,
            relation_types=generic_relations,
            scope_anchors=scope_anchors,
            file_node_ids=file_node_ids or [],
            top_k=top_k,
        )
        result_list = list(result)
        if not result_list:
            # anchor 没匹配到，回退到不限 anchor
            result = session.run(
                cypher_no_anchor,
                kb_id=kb_id,
                relation_types=generic_relations,
                file_node_ids=file_node_ids or [],
                top_k=top_k,
            )
        else:
            result = iter(result_list)
    else:
        result = session.run(
            cypher_no_anchor,
            kb_id=kb_id,
            relation_types=generic_relations,
            file_node_ids=file_node_ids or [],
            top_k=top_k,
        )
    rows = []
    for item in result:
        row = dict(item)
        matched_scope = next(
            (a for a in scope_anchors if a and a in str(row.get("plan_name") or "")), ""
        )
        row["hit_type"] = "graph_entity_relation"
        row["route"] = "graph"
        row["type"] = "relation_hit"
        row["match_type"] = "entity_scope" if matched_scope else "entity_relation"
        row["reason"] = f"relationship_type={row.get('relationship_type')}, domain={row.get('domain_type')}"
        row["evidence_chain"] = [
            x for x in [
                matched_scope or row.get("plan_name"),
                row.get("relationship_type"),
                row.get("related_name"),
                f"chunk_{row.get('chunk_id')}" if row.get("chunk_id") else None,
            ] if x
        ]
        row["graph_depth"] = 1
        row["score"] = _graph_relation_score(
            relationship_weight=row.get("relationship_weight"),
            evidence_weight=row.get("evidence_weight"),
            graph_depth=1,
            matched_scope=bool(matched_scope),
            base=0.84,
        )
        # content 优先用 evidence_quote，其次 value_text，最后 related_name
        row["content"] = row.get("evidence_quote") or row.get("value_text") or row.get("related_name") or row.get("evidence_text")
        row["graph_intent"] = graph_intent
        rows.append(row)
    return rows


def _graph_query_business_plan(
    session: Any,
    kb_id: int,
    field_codes: list[str],
    relation_types: list[str],
    scope_anchors: list[str],
    file_node_ids: list[int] | None,
    index_generations: list[str] | None,
    entities: dict[str, Any],
    top_k: int,
    graph_intent: dict[str, Any],
    understanding: dict[str, Any],
) -> list[dict[str, Any]]:
    """旧 BusinessPlan 查询模式 (向后兼容)。"""
    rows: list[dict[str, Any]] = []

    if not field_codes and relation_types:
        # 关系查询
        cypher = """
            MATCH (p:BusinessPlan {kb_id: $kb_id})-[rel]->(n)
            WHERE type(rel) IN $relation_types
              AND (size($file_node_ids) = 0 OR p.file_node_id IN $file_node_ids)
              AND (size($index_generations) = 0 OR p.index_generation IN $index_generations)
              AND (size($scope_anchors) = 0 OR any(anchor IN $scope_anchors WHERE p.name_cn CONTAINS anchor))
              AND (size($regions) = 0 OR NOT "Region" IN labels(n) OR n.name_cn IN $regions OR any(region IN $regions WHERE p.name_cn CONTAINS region))
              AND (size($industries) = 0 OR NOT "Industry" IN labels(n) OR n.name_cn IN $industries OR any(industry IN $industries WHERE p.name_cn CONTAINS industry))
              AND (size($organizations) = 0 OR NOT "Organization" IN labels(n) OR n.name_cn IN $organizations)
            MATCH (n)-[ev:EVIDENCED_BY]->(c:Chunk)
            RETURN $kb_id AS kb_id,
                   p.file_node_id AS file_node_id,
                   p.name_cn AS plan_name,
                   type(rel) AS relationship_type,
                   coalesce(rel.weight, 1.0) AS relationship_weight,
                   labels(n)[0] AS related_node_type,
                   n.name_cn AS related_name,
                   n.value_text AS value_text,
                   n.field_code AS field_code,
                   c.chunk_id AS chunk_id,
                   c.title_cn AS title,
                   c.content_preview AS evidence_text,
                   c.page_start AS page_no,
                   coalesce(ev.weight, 0.0) AS evidence_weight
            LIMIT $top_k
        """
        result = session.run(
            cypher,
            kb_id=kb_id,
            relation_types=relation_types,
            scope_anchors=scope_anchors,
            file_node_ids=file_node_ids or [],
            index_generations=index_generations or [],
            regions=entities.get("regions") or [],
            industries=entities.get("industries") or [],
            organizations=entities.get("organizations") or [],
            top_k=top_k,
        )
        for item in result:
            row = dict(item)
            matched_scope = next((a for a in scope_anchors if a and a in str(row.get("plan_name") or "")), "")
            row["hit_type"] = "graph_neighborhood"
            row["route"] = "graph"
            row["type"] = "relation_hit"
            row["match_type"] = "relation_scope" if matched_scope else "relation"
            row["reason"] = f"relationship_type={row.get('relationship_type')}"
            row["evidence_chain"] = [
                x for x in [
                    matched_scope or row.get("plan_name"),
                    row.get("relationship_type"),
                    row.get("related_name") or row.get("field_code"),
                    f"chunk_{row.get('chunk_id')}" if row.get("chunk_id") else None,
                ] if x
            ]
            row["graph_depth"] = 1
            row["score"] = _graph_relation_score(
                relationship_weight=row.get("relationship_weight"),
                evidence_weight=row.get("evidence_weight"),
                graph_depth=1,
                matched_scope=bool(matched_scope),
                base=0.84,
            )
            row["content"] = row.get("value_text") or row.get("related_name") or row.get("evidence_text")
            row["graph_intent"] = graph_intent
            rows.append(row)

    # ── 字段查询 (field_codes) ──────────────────────────────
    if field_codes:
        cypher = """
            MATCH (p:BusinessPlan {kb_id: $kb_id})-[hasField:HAS_FIELD]->(f:BusinessField)
            WHERE f.field_code IN $field_codes
              AND (size($file_node_ids) = 0 OR p.file_node_id IN $file_node_ids)
              AND (size($index_generations) = 0 OR p.index_generation IN $index_generations)
              AND (size($scope_anchors) = 0 OR any(anchor IN $scope_anchors WHERE p.name_cn CONTAINS anchor))
            OPTIONAL MATCH (p)-[:IN_REGION]->(r:Region)
            OPTIONAL MATCH (p)-[:IN_INDUSTRY]->(i:Industry)
            OPTIONAL MATCH (p)-[:RELATED_TO]->(o:Organization)
            MATCH (f)-[ev:EVIDENCED_BY]->(c:Chunk)
            WITH p, f, r, i, o, c, hasField, ev
            WHERE (size($regions) = 0 OR r IS NULL OR r.name_cn IN $regions OR any(region IN $regions WHERE p.name_cn CONTAINS region))
              AND (size($industries) = 0 OR i IS NULL OR i.name_cn IN $industries OR any(industry IN $industries WHERE p.name_cn CONTAINS industry))
              AND (size($organizations) = 0 OR o IS NULL OR o.name_cn IN $organizations)
            RETURN $kb_id AS kb_id,
                   p.file_node_id AS file_node_id,
                   p.name_cn AS plan_name,
                   f.field_code AS field_code,
                   f.name_cn AS field_name_cn,
                   f.value_text AS value_text,
                   coalesce(hasField.weight, 1.0) AS relationship_weight,
                   c.chunk_id AS chunk_id,
                   c.title_cn AS title,
                   c.content_preview AS evidence_text,
                   c.page_start AS page_no,
                   coalesce(ev.weight, 0.0) AS evidence_weight
            LIMIT $top_k
        """
        result = session.run(
            cypher,
            kb_id=kb_id,
            field_codes=field_codes,
            file_node_ids=file_node_ids or [],
            index_generations=index_generations or [],
            scope_anchors=scope_anchors,
            regions=entities.get("regions") or [],
            industries=entities.get("industries") or [],
            organizations=entities.get("organizations") or [],
            top_k=top_k,
        )
        for item in result:
            row = dict(item)
            plan_name = str(row.get("plan_name") or "")
            matched_scope = next((a for a in scope_anchors if a and a in plan_name), "")
            row["hit_type"] = "graph_direct"
            row["route"] = "graph"
            row["type"] = "direct_hit"
            row["match_type"] = "scope_anchor_field" if matched_scope else "field"
            row["reason"] = (
                f"scope_anchor={matched_scope}, field_code={row.get('field_code')}"
                if matched_scope
                else f"field_code={row.get('field_code')}"
            )
            row["evidence_chain"] = [x for x in [matched_scope or row.get("plan_name"), row.get("field_name_cn"), f"chunk_{row.get('chunk_id')}"] if x]
            row["graph_depth"] = 1
            row["score"] = _graph_relation_score(
                relationship_weight=row.get("relationship_weight"),
                evidence_weight=row.get("evidence_weight"),
                graph_depth=1,
                matched_scope=bool(matched_scope),
                base=0.88,
            )
            row["content"] = row.get("value_text") or row.get("evidence_text")
            row["graph_intent"] = graph_intent
            rows.append(row)

    return rows


def graph_context_plan(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    chunk_ids: list[int],
    file_node_ids: list[int] | None,
    index_generations: list[str] | None,
    *,
    max_sibling_chunks: int = 6,
) -> list[dict[str, Any]]:
    """Build a lightweight graph context plan around already selected chunks.

    The plan does not generate answer text and does not affect fusion scores.
    It only describes which related evidence can be loaded from MySQL.
    """
    if not chunk_ids:
        return []
    from neo4j import GraphDatabase

    drv = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with drv.session() as session:
            result = session.run(
                """
                MATCH (c:Chunk {kb_id: $kb_id})
                WHERE c.chunk_id IN $chunk_ids
                  AND (size($file_node_ids) = 0 OR c.file_node_id IN $file_node_ids)
                  AND (size($index_generations) = 0 OR c.index_generation IN $index_generations)
                OPTIONAL MATCH (field:BusinessField)-[:EVIDENCED_BY]->(c)
                OPTIONAL MATCH (plan:BusinessPlan)-[:HAS_FIELD]->(field)
                OPTIONAL MATCH (sibling:Chunk {kb_id: $kb_id, file_node_id: c.file_node_id, section_type: c.section_type})
                WHERE sibling.chunk_id <> c.chunk_id
                  AND (size($index_generations) = 0 OR sibling.index_generation IN $index_generations)
                WITH c, field, plan, sibling
                ORDER BY abs(coalesce(sibling.chunk_id, c.chunk_id) - c.chunk_id)
                RETURN c.chunk_id AS direct_chunk_id,
                       c.file_node_id AS file_node_id,
                       c.section_type AS section_type,
                       c.title_cn AS title,
                       c.page_start AS page_start,
                       plan.name_cn AS scope_anchor,
                       collect(DISTINCT field.field_code) AS related_field_codes,
                       collect(DISTINCT sibling.chunk_id)[0..$max_sibling_chunks] AS sibling_chunk_ids
                """,
                kb_id=kb_id,
                chunk_ids=chunk_ids,
                file_node_ids=file_node_ids or [],
                index_generations=index_generations or [],
                max_sibling_chunks=max(0, min(max_sibling_chunks, 20)),
            )
            rows = [dict(row) for row in result]
    finally:
        drv.close()
    plans: list[dict[str, Any]] = []
    for row in rows:
        evidence_chain = [item for item in [row.get("scope_anchor"), row.get("section_type"), f"chunk_{row.get('direct_chunk_id')}"] if item]
        plans.append(
            {
                "type": "context_plan",
                "direct_chunk_id": row.get("direct_chunk_id"),
                "file_node_id": row.get("file_node_id"),
                "scope_anchor": row.get("scope_anchor"),
                "section_type": row.get("section_type"),
                "section_title": row.get("title"),
                "page_start": row.get("page_start"),
                "sibling_chunk_ids": [item for item in row.get("sibling_chunk_ids") or [] if item],
                "related_field_codes": [item for item in row.get("related_field_codes") or [] if item],
                "evidence_chain": evidence_chain,
                "context_mode": "graph_sibling_chunks",
            }
        )
    return plans


def normalize_candidates(route_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        clean_row = {key: value for key, value in row.items() if key not in {"embedding_vector", "field_vector", "content_vector", "question_vector"}}
        source_chunk_ids = row.get("source_chunk_ids") or row.get("source_chunk_ids_json") or []
        if isinstance(source_chunk_ids, str):
            try:
                source_chunk_ids = json.loads(source_chunk_ids)
            except Exception:
                source_chunk_ids = []
        source_chunk_ids = [int(item) for item in source_chunk_ids if item]
        source_field_ids = row.get("source_field_ids") or row.get("source_field_ids_json") or []
        if isinstance(source_field_ids, str):
            try:
                source_field_ids = json.loads(source_field_ids)
            except Exception:
                source_field_ids = []
        source_field_ids = [int(item) for item in source_field_ids if item]
        evidence_quotes = row.get("evidence_quotes") or row.get("evidence_quotes_json") or []
        if isinstance(evidence_quotes, str):
            try:
                evidence_quotes = json.loads(evidence_quotes)
            except Exception:
                evidence_quotes = []
        evidence_quotes = [str(item) for item in evidence_quotes if item]
        covered_chunk_ids = row.get("covered_chunk_ids") or row.get("covered_chunk_ids_json") or []
        if isinstance(covered_chunk_ids, str):
            try:
                covered_chunk_ids = json.loads(covered_chunk_ids)
            except Exception:
                covered_chunk_ids = []
        covered_chunk_ids = [int(item) for item in covered_chunk_ids if item]
        chunk_id = row.get("chunk_id") or row.get("source_chunk_id") or (source_chunk_ids[0] if source_chunk_ids else None)
        primary_chunk_id = row.get("primary_chunk_id") or chunk_id or (covered_chunk_ids[0] if covered_chunk_ids else None)
        field_id = row.get("field_id")
        qa_id = row.get("qa_id")
        identity = f"chunk:{primary_chunk_id}" if primary_chunk_id else (f"field:{field_id}" if field_id else (f"qa:{qa_id}" if qa_id else f"{route_name}:{index}"))
        candidate_id = f"{route_name}:{identity}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "identity_key": identity,
                "kb_id": row.get("kb_id"),
                "route_name": route_name,
                "route_names": [route_name],
                "hit_type": row.get("hit_type", route_name),
                "hit_types": [row.get("hit_type", route_name)],
                "score": float(row.get("score") or 0.0),
                "file_node_id": row.get("file_node_id"),
                "chunk_id": chunk_id,
                "primary_chunk_id": primary_chunk_id,
                "parent_chunk_id": row.get("parent_chunk_id"),
                "chunk_type": row.get("chunk_type"),
                "retrieval_role": row.get("retrieval_role"),
                "context_level": row.get("context_level"),
                "source_chunk_ids": source_chunk_ids,
                "source_field_ids": source_field_ids,
                "evidence_quotes": evidence_quotes,
                "covered_chunk_ids": covered_chunk_ids,
                "field_id": field_id,
                "qa_id": qa_id,
                "unit_pk": row.get("unit_pk"),
                "unit_id": row.get("unit_id"),
                "unit_type": row.get("unit_type"),
                "unit_subtype": row.get("unit_subtype"),
                "subject_text": row.get("subject_text"),
                "predicate_text": row.get("predicate_text"),
                "object_text": row.get("object_text"),
                "value_type": row.get("value_type"),
                "anchor_pk": row.get("anchor_pk"),
                "anchor_id": row.get("anchor_id"),
                "anchor_type": row.get("anchor_type"),
                "anchor_name": row.get("anchor_name"),
                "normalized_name": row.get("normalized_name"),
                "summary_pk": row.get("summary_pk"),
                "section_id": row.get("section_id") or row.get("source_section_id"),
                "section_type": row.get("section_type") or row.get("source_section_type"),
                "section_title": row.get("section_title"),
                "section_path": row.get("section_path") or row.get("section_path_text"),
                "section_path_text": row.get("section_path_text"),
                "section_level": row.get("section_level"),
                "summary_type": row.get("summary_type"),
                "summary_source": row.get("summary_source"),
                "answer_type": row.get("answer_type"),
                "generation_source": row.get("generation_source"),
                "evidence_quality": row.get("evidence_quality"),
                "source_type": row.get("source_type"),
                "field_code": row.get("field_code"),
                "chunk_group_id": row.get("chunk_group_id"),
                "content_hash": row.get("content_hash"),
                "title": row.get("title") or row.get("field_name_cn") or row.get("question") or row.get("section_title") or row.get("anchor_name") or row.get("predicate_text"),
                "content": row.get("content") or row.get("value_text") or row.get("answer") or row.get("object_text") or row.get("node_summary") or row.get("evidence_quote"),
                "value_text": row.get("value_text") or row.get("answer") or row.get("object_text"),
                "evidence_text": row.get("evidence_text") or row.get("evidence_quote") or row.get("node_summary") or row.get("content"),
                "page_no": row.get("page_no") or row.get("page_start"),
                "match_type": row.get("match_type"),
                "reason": row.get("reason"),
                "evidence_chain": row.get("evidence_chain") or [],
                "graph_path": row.get("graph_path"),
                "entity_text": " ".join(str(value) for value in clean_row.values() if isinstance(value, (str, int, float))),
                "raw_items": [clean_row],
            }
        )
    return candidates


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in candidates:
        semantic_key = item.get("primary_chunk_id") or item.get("chunk_id") or item.get("content_hash")
        key = (
            item.get("file_node_id"),
            item.get("field_id"),
            item.get("qa_id"),
            semantic_key or item.get("chunk_id"),
        )
        current = merged.get(key)
        if not current:
            merged[key] = dict(item)
            continue
        current["score"] = max(float(current.get("score") or 0.0), float(item.get("score") or 0.0))
        current["route_names"] = sorted(set(current.get("route_names", []) + item.get("route_names", [])))
        current["hit_types"] = sorted(set(current.get("hit_types", []) + item.get("hit_types", [])))
        current["raw_items"] = current.get("raw_items", []) + item.get("raw_items", [])
        if not current.get("content") and item.get("content"):
            current["content"] = item.get("content")
        if not current.get("title") and item.get("title"):
            current["title"] = item.get("title")
        if not current.get("value_text") and item.get("value_text"):
            current["value_text"] = item.get("value_text")
        if not current.get("evidence_text") and item.get("evidence_text"):
            current["evidence_text"] = item.get("evidence_text")
        if not current.get("page_no") and item.get("page_no"):
            current["page_no"] = item.get("page_no")
        current["entity_text"] = " ".join([current.get("entity_text") or "", item.get("entity_text") or ""]).strip()
    result = list(merged.values())
    result.sort(key=lambda row: row.get("score", 0.0), reverse=True)
    return result


def _merge_candidate_base(current: dict[str, Any], item: dict[str, Any]) -> None:
    current["route_names"] = sorted(set(current.get("route_names", []) + item.get("route_names", [])))
    current["hit_types"] = sorted(set(current.get("hit_types", []) + item.get("hit_types", [])))
    current["raw_items"] = current.get("raw_items", []) + item.get("raw_items", [])
    current.setdefault("merged_candidates", []).append(item)
    for key in [
        "kb_id",
        "content",
        "title",
        "value_text",
        "evidence_text",
        "doc_name",
        "page_no",
        "file_node_id",
        "chunk_id",
        "primary_chunk_id",
        "parent_chunk_id",
        "chunk_type",
        "retrieval_role",
        "context_level",
        "source_chunk_ids",
        "source_field_ids",
        "evidence_quotes",
        "covered_chunk_ids",
        "field_id",
        "qa_id",
        "unit_pk",
        "unit_id",
        "unit_type",
        "unit_subtype",
        "subject_text",
        "predicate_text",
        "object_text",
        "value_type",
        "anchor_pk",
        "anchor_id",
        "anchor_type",
        "anchor_name",
        "normalized_name",
        "summary_pk",
        "section_id",
        "section_type",
        "section_title",
        "section_path",
        "section_path_text",
        "section_level",
        "summary_type",
        "summary_source",
        "answer_type",
        "generation_source",
        "evidence_quality",
        "manual_override",
        "source_type",
        "field_code",
        "chunk_group_id",
        "content_hash",
        "match_type",
        "reason",
        "evidence_chain",
        "graph_path",
    ]:
        if not current.get(key) and item.get(key):
            current[key] = item.get(key)
    current["entity_text"] = " ".join([current.get("entity_text") or "", item.get("entity_text") or ""]).strip()


def _route_score_bounds(rows: list[dict[str, Any]]) -> tuple[float, float]:
    scores = [float(item.get("score") or 0.0) for item in rows]
    if not scores:
        return 0.0, 0.0
    return min(scores), max(scores)


def _normalize_route_score(score: float, min_score: float, max_score: float) -> float:
    if max_score <= min_score:
        return 1.0 if score > 0 else 0.0
    return max(0.0, min((score - min_score) / (max_score - min_score), 1.0))


def weighted_rrf_fuse(
    route_candidates: dict[str, list[dict[str, Any]]],
    *,
    fusion_config: dict[str, Any],
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fuse multi-route candidates by chunk-aware weighted score/rank fusion."""
    weights = _as_dict(fusion_config.get("weights"))
    rrf_k = int(fusion_config.get("rrf_k") or DEFAULT_RRF_K)
    strategy = str(fusion_config.get("strategy") or "score_aware")
    score_weight = max(0.0, min(float(fusion_config.get("score_weight") or 0.65), 1.0))
    rank_weight = max(0.0, min(float(fusion_config.get("rank_weight") or 0.35), 1.0))
    if score_weight + rank_weight <= 0:
        score_weight, rank_weight = 0.65, 0.35
    total_weight = score_weight + rank_weight
    score_weight = score_weight / total_weight
    rank_weight = rank_weight / total_weight
    multi_route_bonus = max(0.0, min(float(fusion_config.get("multi_route_bonus") or 0.0), 0.5))
    route_confidence = _as_dict(fusion_config.get("route_confidence"))
    merged: dict[str, dict[str, Any]] = {}
    route_debug: dict[str, Any] = {}
    for route_name, rows in route_candidates.items():
        if route_name not in weights:
            continue
        route_weight = float(weights.get(route_name) or 0.0)
        if route_weight <= 0:
            continue
        seen_in_route: set[str] = set()
        min_score, max_score = _route_score_bounds(rows)
        route_debug[route_name] = {
            "weight": route_weight,
            "candidate_count": len(rows),
            "min_raw_score": min_score,
            "max_raw_score": max_score,
        }
        for route_rank, item in enumerate(rows, 1):
            identity = str(item.get("identity_key") or item.get("candidate_id") or f"{route_name}:{route_rank}")
            if identity in seen_in_route:
                current = merged.get(identity)
                if current:
                    _merge_candidate_base(current, item)
                continue
            seen_in_route.add(identity)
            raw_score = float(item.get("score") or 0.0)
            rank_score = float(rrf_k) / float(rrf_k + route_rank)
            normalized_raw_score = _normalize_route_score(raw_score, min_score, max_score)
            confidence = _as_float(route_confidence.get(route_name), 1.0)
            if strategy == "weighted_rrf":
                contribution = route_weight * confidence / float(rrf_k + route_rank)
            else:
                contribution = route_weight * confidence * ((score_weight * normalized_raw_score) + (rank_weight * rank_score))
            current = merged.get(identity)
            if not current:
                current = dict(item)
                current["candidate_id"] = f"fused:{identity}"
                current["identity_key"] = identity
                current["route_names"] = []
                current["hit_types"] = []
                current["raw_items"] = []
                current["score"] = 0.0
                current["score_details"] = {
                    "strategy": strategy,
                    "rrf_k": rrf_k,
                    "score_weight": score_weight,
                    "rank_weight": rank_weight,
                    "channels": {},
                    "matched_channels": [],
                    "missing_channels": [],
                }
                merged[identity] = current
            _merge_candidate_base(current, item)
            current["score"] = float(current.get("score") or 0.0) + contribution
            current["score_details"]["channels"][route_name] = {
                "weight": route_weight,
                "confidence": confidence,
                "rank": route_rank,
                "raw_score": raw_score,
                "normalized_raw_score": normalized_raw_score,
                "rank_score": rank_score,
                "contribution": contribution,
                "candidate_id": item.get("candidate_id"),
                "hit_type": item.get("hit_type"),
            }
    enabled_routes = list(weights.keys())
    fused = list(merged.values())
    for item in fused:
        details = item.get("score_details") or {}
        matched = sorted((details.get("channels") or {}).keys())
        details["matched_channels"] = matched
        details["missing_channels"] = [route for route in enabled_routes if route not in matched]
        if multi_route_bonus and len(matched) > 1:
            bonus = multi_route_bonus * float(len(matched) - 1)
            item["score"] = float(item.get("score") or 0.0) + bonus
            details["multi_route_bonus"] = bonus
        details["final_score"] = float(item.get("score") or 0.0)
        item["score_details"] = details
    fused.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -len((item.get("score_details") or {}).get("matched_channels") or []),
            -float(max((ch.get("raw_score") or 0.0) for ch in ((item.get("score_details") or {}).get("channels") or {}).values()) if (item.get("score_details") or {}).get("channels") else 0.0),
        )
    )
    for rank, item in enumerate(fused, 1):
        item["fusion_rank"] = rank
    max_score = max((float(item.get("score") or 0.0) for item in fused), default=0.0)
    for item in fused:
        normalized_score = float(item.get("score") or 0.0) / max_score if max_score > 0 else 0.0
        item["normalized_score"] = normalized_score
        details = item.get("score_details") or {}
        details["normalized_score"] = normalized_score
        item["score_details"] = details
    debug = {
        "strategy": strategy,
        "rrf_k": rrf_k,
        "score_weight": score_weight,
        "rank_weight": rank_weight,
        "multi_route_bonus": multi_route_bonus,
        "weights": weights,
        "route_debug": route_debug,
        "fused_candidate_count": len(fused),
    }
    return fused[: max(top_k, 1)], debug


def filter_by_similarity_threshold(candidates: list[dict[str, Any]], threshold: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if threshold <= 0:
        return candidates, {"enabled": False, "threshold": threshold, "before": len(candidates), "after": len(candidates)}
    filtered = [item for item in candidates if float(item.get("normalized_score") or item.get("score") or 0.0) >= threshold]
    fallback_kept = False
    if candidates and not filtered:
        filtered = candidates[:1]
        fallback_kept = True
    return filtered, {
        "enabled": True,
        "threshold": threshold,
        "score_field": "normalized_score",
        "before": len(candidates),
        "after": len(filtered),
        "fallback_kept_top1": fallback_kept,
    }


def _keyword_score(item: dict[str, Any], keywords: list[str]) -> int:
    text = " ".join(
        str(part)
        for part in [
            item.get("title"),
            item.get("content"),
            item.get("value_text"),
            item.get("evidence_text"),
            item.get("entity_text"),
        ]
        if part
    )
    return sum(1 for keyword in keywords if keyword and keyword in text)


def _profile_priority(item: dict[str, Any], profile: str | None, keywords: list[str]) -> int:
    normalized_profile = normalize_profile(profile) or "business_plan"
    raw_items = item.get("raw_items") or []
    section_types = {str(raw.get("section_type") or raw.get("chunk_type") or "") for raw in raw_items if isinstance(raw, dict)}
    text = " ".join(
        str(part)
        for part in [item.get("title"), item.get("content"), item.get("value_text"), item.get("evidence_text"), item.get("entity_text")]
        if part
    )
    if normalized_profile == "business_plan":
        return 3 if item.get("field_code") else 0
    if normalized_profile == "governance_rule":
        clause_hit = bool(re.search(r"第[一二三四五六七八九十百千万0-9]+条", text))
        return (4 if "clause" in section_types else 0) + (2 if clause_hit else 0)
    if normalized_profile == "project_doc":
        exact = any(keyword and keyword in text for keyword in keywords)
        technical_hit = bool(section_types & {"api_spec", "db_table", "config_item", "code_block"})
        return (4 if technical_hit else 0) + (2 if exact else 0)
    if normalized_profile == "contract_agreement":
        contract_hit = bool(section_types & {"payment_term", "breach_clause", "confidentiality_clause", "contract_clause"})
        return 4 if contract_hit else 0
    return 0


def _prioritize_target_fields(
    candidates: list[dict[str, Any]],
    target_field_codes: list[str],
    top_k: int,
    keywords: list[str] | None = None,
    profile: str | None = None,
) -> list[dict[str, Any]]:
    keywords = keywords or []
    target_set = set(target_field_codes) if target_field_codes else set()

    def _sort_key(item: dict[str, Any]) -> tuple:
        score = float(item.get("score") or 0.0)
        field_bonus = 0.15 if target_set and item.get("field_code") in target_set else 0.0
        # 流程意图（business_process，如"怎么申请/办理流程/怎么办"）下，image_group
        # 才是完整流程答案，而非单张步骤截图。步骤截图 caption 里"贷款/申请"字面密度高，
        # rerank 会把它们排在流程组前面；这里给流程组加 boost，让"怎么申请贷款"这类
        # 泛化问法优先命中"申请流程"而非零散的"基本信息填写"截图。仅对 image_group 生效。
        procedure_bonus = 0.35 if ("business_process" in target_set and item.get("chunk_type") == "image_group") else 0.0
        effective_score = score + field_bonus + procedure_bonus
        return (
            -effective_score,
            -_profile_priority(item, profile, keywords),
            -_keyword_score(item, keywords),
        )

    ordered = sorted(candidates, key=_sort_key)[:top_k]
    for idx, item in enumerate(ordered, 1):
        item["rank"] = idx
    return ordered


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    target_field_codes: list[str] | None = None,
    keywords: list[str] | None = None,
    profile: str | None = None,
    use_rerank: bool = True,
    rerank_score_weight: float = 0.0,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    reranked: list[dict[str, Any]] = []
    if use_rerank:
        try:
            reranked = RerankClient().rerank(query, candidates, top_k)
        except Exception:
            reranked = []
    if reranked and "rank" in reranked[0]:
        seen = {item.get("candidate_id") for item in reranked}
        expanded = reranked + [item for item in candidates if item.get("candidate_id") not in seen]
        weight = max(0.0, min(float(rerank_score_weight or 0.0), 1.0))
        if weight > 0:
            max_rerank_score = max((float(item.get("rerank_score") or 0.0) for item in expanded), default=0.0)
            for item in expanded:
                fusion_score = float(item.get("normalized_score") or item.get("score") or 0.0)
                rerank_score = float(item.get("rerank_score") or 0.0)
                rerank_normalized = rerank_score / max_rerank_score if max_rerank_score > 0 else 0.0
                blended_score = fusion_score * (1.0 - weight) + rerank_normalized * weight
                item["original_fusion_score"] = fusion_score
                item["rerank_normalized_score"] = rerank_normalized
                item["score"] = blended_score
                score_details = item.get("score_details") or {}
                score_details["original_fusion_score"] = fusion_score
                score_details["rerank_score"] = rerank_score
                score_details["rerank_normalized_score"] = rerank_normalized
                score_details["rerank_score_weight"] = weight
                score_details["final_score"] = blended_score
                item["score_details"] = score_details
            expanded.sort(key=lambda row: (-float(row.get("score") or 0.0), int(row.get("rank") or 999999)))
            for rank, item in enumerate(expanded, 1):
                item["rank"] = rank
        return _prioritize_target_fields(expanded, target_field_codes or [], top_k, keywords, profile)
    for idx, item in enumerate(candidates[:top_k], 1):
        item["rank"] = idx
        item["rerank_score"] = float(top_k - idx + 1)
    return _prioritize_target_fields(candidates, target_field_codes or [], top_k, keywords, profile)


def build_evidence_groups(candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    def append_unique(group: dict[str, Any], list_key: str, dedupe_key: str, value: dict[str, Any]) -> None:
        marker_key = f"_seen_{list_key}"
        marker = group.setdefault(marker_key, set())
        marker_value = value.get(dedupe_key) or value.get("candidate_id") or json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker_value in marker:
            return
        marker.add(marker_value)
        group[list_key].append(value)

    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in candidates:
        primary_chunk_id = item.get("primary_chunk_id") or item.get("chunk_id")
        group_key = f"kb:{item.get('kb_id')}:chunk:{primary_chunk_id}" if primary_chunk_id else str(item.get("identity_key") or item.get("candidate_id"))
        if group_key not in grouped:
            order.append(group_key)
            grouped[group_key] = {
                "group_id": group_key,
                "group_type": "chunk_with_matches" if primary_chunk_id else "unanchored_match",
                "rank": item.get("rank"),
                "rerank_score": item.get("rerank_score"),
                "final_score": item.get("score"),
                "kb_id": item.get("kb_id"),
                "file_node_id": item.get("file_node_id"),
                "primary_chunk_id": primary_chunk_id,
                "primary_chunk": None,
                "display_text": item.get("content") or item.get("evidence_text") or item.get("value_text"),
                "answer_hint": item.get("value_text") or item.get("content"),
                "page_numbers": set(),
                "hit_routes": set(),
                "hit_types": set(),
                "score_details": item.get("score_details"),
                "evidence_chain": item.get("evidence_chain") or [],
                "matched_preset_answers": [],
                "matched_fields": [],
                "matched_chunks": [],
                "matched_units": [],
                "matched_anchors": [],
                "matched_section_summaries": [],
                "matched_graph_paths": [],
                "evidence_items": [],
            }
        group = grouped[group_key]
        group["rank"] = min(int(group.get("rank") or 999999), int(item.get("rank") or 999999))
        group["rerank_score"] = max(float(group.get("rerank_score") or 0.0), float(item.get("rerank_score") or 0.0))
        group["final_score"] = max(float(group.get("final_score") or 0.0), float(item.get("score") or 0.0))
        group["hit_routes"].update(item.get("route_names") or [])
        group["hit_types"].update(item.get("hit_types") or [])
        support_items = item.get("merged_candidates") or [item]
        for support in support_items:
            if not isinstance(support, dict):
                continue
            group["hit_routes"].update(support.get("route_names") or ([support.get("route_name")] if support.get("route_name") else []))
            group["hit_types"].update(support.get("hit_types") or ([support.get("hit_type")] if support.get("hit_type") else []))
            evidence_item = {
                "candidate_id": support.get("candidate_id"),
                "hit_type": support.get("hit_type"),
                "field_code": support.get("field_code"),
                "chunk_id": support.get("chunk_id"),
                "primary_chunk_id": support.get("primary_chunk_id"),
                "chunk_type": support.get("chunk_type"),
                "retrieval_role": support.get("retrieval_role"),
                "context_level": support.get("context_level"),
                "qa_id": support.get("qa_id"),
                "field_id": support.get("field_id"),
                "unit_id": support.get("unit_id"),
                "unit_type": support.get("unit_type"),
                "anchor_id": support.get("anchor_id"),
                "summary_pk": support.get("summary_pk"),
                "title": support.get("title"),
                "content": support.get("content") or support.get("value_text"),
                "evidence_text": support.get("evidence_text") or support.get("content"),
                "page_no": support.get("page_no"),
                "page_start": support.get("page_start"),
                "page_end": support.get("page_end"),
                "char_start": support.get("char_start"),
                "char_end": support.get("char_end"),
                "block_ids": support.get("block_ids") or [],
                "bbox": support.get("bbox") or support.get("bbox_json"),
                "bbox_json": support.get("bbox_json") or support.get("bbox"),
                "evidence_alignment": support.get("evidence_alignment"),
                "score": support.get("score"),
            }
            if support.get("page_no") is not None:
                group["page_numbers"].add(support.get("page_no"))
            append_unique(group, "evidence_items", "candidate_id", evidence_item)
            if support.get("qa_id"):
                append_unique(
                    group,
                    "matched_preset_answers",
                    "qa_id",
                    {
                        "qa_id": support.get("qa_id"),
                        "question": support.get("title"),
                        "answer": support.get("value_text") or support.get("content"),
                        "answer_type": support.get("answer_type"),
                        "generation_source": support.get("generation_source"),
                        "source_type": support.get("source_type"),
                        "evidence_quality": support.get("evidence_quality"),
                        "source_chunk_ids": support.get("source_chunk_ids") or [],
                        "evidence_quotes": support.get("evidence_quotes") or [],
                    },
                )
            elif support.get("field_id"):
                append_unique(
                    group,
                    "matched_fields",
                    "field_id",
                    {
                        "field_id": support.get("field_id"),
                        "field_code": support.get("field_code"),
                        "title": support.get("title"),
                        "value_text": support.get("value_text") or support.get("content"),
                        "char_start": support.get("char_start"),
                        "char_end": support.get("char_end"),
                        "page_no": support.get("page_no"),
                        "block_ids": support.get("block_ids") or [],
                        "bbox_json": support.get("bbox_json") or support.get("bbox"),
                        "evidence_alignment": support.get("evidence_alignment"),
                    },
                )
            elif support.get("unit_id") or support.get("unit_pk") or support.get("hit_type") == "knowledge_unit":
                append_unique(
                    group,
                    "matched_units",
                    "unit_key",
                    {
                        "unit_key": support.get("unit_id") or support.get("unit_pk") or support.get("candidate_id"),
                        "unit_pk": support.get("unit_pk"),
                        "unit_id": support.get("unit_id"),
                        "unit_type": support.get("unit_type"),
                        "unit_subtype": support.get("unit_subtype"),
                        "subject_text": support.get("subject_text"),
                        "predicate_text": support.get("predicate_text"),
                        "object_text": support.get("object_text") or support.get("value_text") or support.get("content"),
                        "value_type": support.get("value_type"),
                        "anchor_id": support.get("anchor_id"),
                        "section_id": support.get("section_id"),
                        "section_path": support.get("section_path") or support.get("section_path_text"),
                        "evidence_quote": support.get("evidence_text") or support.get("evidence_quote"),
                        "score": support.get("score"),
                    },
                )
            elif support.get("anchor_id") or support.get("anchor_pk") or support.get("hit_type") == "anchor":
                append_unique(
                    group,
                    "matched_anchors",
                    "anchor_key",
                    {
                        "anchor_key": support.get("anchor_id") or support.get("anchor_pk") or support.get("candidate_id"),
                        "anchor_pk": support.get("anchor_pk"),
                        "anchor_id": support.get("anchor_id"),
                        "anchor_type": support.get("anchor_type"),
                        "anchor_name": support.get("anchor_name") or support.get("title"),
                        "normalized_name": support.get("normalized_name"),
                        "section_id": support.get("section_id"),
                        "section_path": support.get("section_path") or support.get("section_path_text"),
                        "evidence_quote": support.get("evidence_text"),
                        "score": support.get("score"),
                    },
                )
            elif support.get("summary_pk") or support.get("hit_type") == "section_summary":
                append_unique(
                    group,
                    "matched_section_summaries",
                    "summary_key",
                    {
                        "summary_key": support.get("summary_pk") or support.get("section_id") or support.get("candidate_id"),
                        "summary_pk": support.get("summary_pk"),
                        "section_id": support.get("section_id"),
                        "section_type": support.get("section_type"),
                        "section_title": support.get("section_title") or support.get("title"),
                        "section_path": support.get("section_path") or support.get("section_path_text"),
                        "section_level": support.get("section_level"),
                        "summary_type": support.get("summary_type"),
                        "summary_source": support.get("summary_source"),
                        "node_summary": support.get("content") or support.get("evidence_text"),
                        "covered_chunk_ids": support.get("covered_chunk_ids") or [],
                        "score": support.get("score"),
                    },
                )
            elif "graph" in (support.get("route_names") or []) or str(support.get("hit_type") or "").startswith("graph"):
                append_unique(
                    group,
                    "matched_graph_paths",
                    "candidate_id",
                    {
                        "candidate_id": support.get("candidate_id"),
                        "reason": support.get("reason"),
                        "evidence_chain": support.get("evidence_chain") or [],
                        "graph_path": support.get("graph_path"),
                        "chunk_id": support.get("chunk_id"),
                        "score": support.get("score"),
                    },
                )
            if support.get("chunk_id"):
                chunk_match = {
                    "chunk_id": support.get("chunk_id"),
                    "primary_chunk_id": support.get("primary_chunk_id"),
                    "chunk_type": support.get("chunk_type"),
                    "retrieval_role": support.get("retrieval_role"),
                    "context_level": support.get("context_level"),
                    "title": support.get("title"),
                    "content": support.get("content"),
                    "evidence_text": support.get("evidence_text"),
                    "page_no": support.get("page_no"),
                    "page_start": support.get("page_start"),
                    "page_end": support.get("page_end"),
                    "char_start": support.get("char_start"),
                    "char_end": support.get("char_end"),
                    "block_ids": support.get("block_ids") or [],
                    "bbox": support.get("bbox") or support.get("bbox_json"),
                    "bbox_json": support.get("bbox_json") or support.get("bbox"),
                }
                append_unique(group, "matched_chunks", "chunk_id", chunk_match)
                if not group.get("primary_chunk") and support.get("chunk_id") == primary_chunk_id:
                    group["primary_chunk"] = chunk_match

    groups = [grouped[key] for key in order]
    groups.sort(key=lambda row: (-float(row.get("final_score") or 0.0), int(row.get("rank") or 999999)))
    for index, group in enumerate(groups[:top_k], 1):
        group["rank"] = index
        group["page_numbers"] = sorted(group["page_numbers"])
        group["hit_routes"] = sorted(group["hit_routes"])
        group["hit_types"] = sorted(group["hit_types"])
        group["evidence_items"] = group["evidence_items"][:8]
        for key in list(group.keys()):
            if key.startswith("_seen_"):
                group.pop(key, None)
    return groups[:top_k]
