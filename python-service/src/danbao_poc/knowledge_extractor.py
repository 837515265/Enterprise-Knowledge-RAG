from __future__ import annotations

import json
from typing import Any

from .anchor_deduper import deduplicate_anchors
from .common import canonical_key, clean_text, stable_hash
from .evidence_aligner import align_quote_to_chunks
from .extraction_cache import build_extraction_cache_key, load_extraction_cache, save_extraction_cache
from .extraction_merge import extraction_pass_count, merge_overlaps_enabled, merge_pass_record_lists
from .graph_schema import relation_type_allowed
from .openai_compat import JsonChatClient
from .prompt_views import format_chunks_for_prompt, format_summaries_for_prompt
from .relation_rule_extractor import ALLOWED_RELATION_TYPES, build_rule_relations


KNOWLEDGE_SYSTEM_PROMPT = """你是企业知识库 RAG-Doc 的 Anchor、Knowledge Unit、Relation 联合抽取模型。
你的任务是从原文 chunk、目录和层级摘要中抽取可检索、可回源、可用于问答的结构化知识。

核心原则：
1. Anchor 是可问对象，不是所有名词；只抽方案、制度、模块、接口、主体、章节对象等高价值对象。
2. Knowledge Unit 是能支撑问答的最小知识单元，可以是条件、规则、公式、额度、费率、职责、流程、参数、引用。
3. Unit 不能替代原文，必须回挂 evidence_quote。
4. evidence_quote 必须来自输入原文，不要改写。
5. 同一个事实不要拆得过碎；每个 Unit 必须语义完整。
6. Relation 只抽高价值关系，不要为了建图而建图；关系必须能支持多跳检索，而不是复述整个段落。
7. 不要编造原文没有的信息；不确定就降低 confidence 并写 warnings。
8. 只输出 JSON object。
9. Relation 必须同时输出 confidence_label：原文明示为 EXTRACTED，基于上下文推导为 INFERRED，
   存在指代/方向/主体歧义为 AMBIGUOUS；AMBIGUOUS 不得伪装成高置信关系。

Neo4j 图投影重点（与 ES Chunk 检索互补）：
- 优先抽取“主体/角色—职责—事项”“流程步骤—先后/依赖—流程步骤”“制度—引用—制度”、
  “产品—要求/约束—材料或条件”“审批主体—审批—业务事项”等可遍历关系。
- from/to 必须是稳定 Anchor 或语义完整 Unit；不要把一整段原文当成节点名。
- 同一关系只保留一个方向明确的事实，predicate/relationship 要可读、可比较、可跨文档连接。
- 图片、流程图、页面截图中的步骤与字段若有明确文字证据，也应形成 Unit 和 Relation。

profile 抽取重点：
- business_plan：方案对象、服务对象、适用范围、准入条件、额度公式、额度上限、担保费率、贷款用途、授信期限、反担保、风险缓释、批复依据。
- governance_rule：制度名称、适用范围、职责部门、条款要求、审批流程、禁止/必须/应当、引用文件、生效/废止。
- project_doc：系统、模块、接口、参数、流程、任务、缺陷、部署步骤、配置项、数据库对象、测试和上线要求。
"""

KNOWLEDGE_PROMPT_VERSION = "knowledge_graph_v2_1"

PROFILE_KNOWLEDGE_RULES: dict[str, str] = {
    "business_plan": """当前 profile=business_plan，只抽担保方案知识。
Anchor 优先级：
- primary：方案名称、产品/服务名称。
- secondary：服务对象、准入条件、授信额度、担保费率、贷款用途、授信期限、反担保、风险缓释等业务章节或业务对象。
- 不要把“额度”“期限”“条件”“客户”“主体”等泛词单独作为 Anchor。
Knowledge Unit 颗粒度：
- 额度公式、额度上限、准入条件、适用范围、费率、期限、用途、反担保措施必须拆成语义完整的 unit。
- 同一个小节下多个条件可以分别成 unit，但 evidence_quote 必须是一句或一条原文。
- 公式类 normalized_json 应尽量包含 formula、variables、cap、unit 等字段。""",
    "governance_rule": """当前 profile=governance_rule，只抽制度/办法知识。
Anchor 优先级：
- primary：制度名称。
- secondary：高价值管理事项，例如 KPI考核、目标责任制考核、考核结果应用、考核程序、职责部门。
- auxiliary：重要章节入口。
- 不要把“季度”“年度”“项目”“考核”“方式”“周期”“范围”“维度”等泛词单独作为 Anchor。
- 条款号如“第三条”通常不要作为 Anchor；除非该条款本身是用户会问的独立制度对象。
Knowledge Unit 颗粒度：
- KPI考核、目标责任制考核应分别作为 subject。
- 季度KPI考核、年度KPI考核、目标责任制季度考核、目标责任制年度考核、项目考核应写入 condition_key 或 normalized_json.branch，不要抢占 Anchor 位。
- 考核维度、适用范围、考核周期、评价形式、结果应用、职责要求要分别成 unit。
- 每个 unit 的 object_text 必须能独立回答一个问题，不能只写“适用于技术序列”。应包含 subject、条件和谓词语义。""",
    "project_doc": """当前 profile=project_doc，只抽项目/技术文档知识。
Anchor 优先级：
- primary：系统、项目、平台、核心模块。
- secondary：接口、数据库表、配置项、任务、流程、页面、服务。
- 不要把“接口”“字段”“模块”“流程”“配置”等泛词单独作为 Anchor。
Knowledge Unit 颗粒度：
- 接口路径、请求参数、响应字段、数据库字段、配置项、部署步骤、异常处理、测试要求要分别成 unit。
- 参数/字段类 normalized_json 应尽量包含 name、type、required、default、description。""",
    "general_document": """当前 profile=general_document，按通用文档处理。
Anchor 只抽文档标题、稳定主题对象和重要章节入口。
不要抽泛词、编号、普通短语。
Knowledge Unit 应围绕事实、规则、流程、适用范围、条件、引用关系抽取，保持语义完整。""",
}

GENERIC_ANCHOR_TEXTS = {
    "季度",
    "年度",
    "项目",
    "考核",
    "方式",
    "周期",
    "范围",
    "维度",
    "条件",
    "额度",
    "期限",
    "流程",
    "规则",
    "对象",
    "主体",
}


def _knowledge_system_prompt(profile: str) -> str:
    profile_rules = PROFILE_KNOWLEDGE_RULES.get(profile) or PROFILE_KNOWLEDGE_RULES["general_document"]
    return f"""{KNOWLEDGE_SYSTEM_PROMPT}

【当前 Profile 专属规则】
{profile_rules}

【质量硬约束】
1. Anchor 是用户会问的稳定对象；泛词、编号、短周期词不能作为 Anchor。
2. Knowledge Unit 可以比 Anchor 细；周期、分支、客户类型、角色类型写入 object_text/normalized_json/condition_key，不要滥造 Anchor。
3. 每个 unit 的 object_text 必须包含完整语义，不允许只有半句话。
4. evidence_quote 必须逐字来自输入 chunk；没有证据的对象不要输出。
5. 输出必须是 anchors、knowledge_units、relations、warnings 四个顶层字段。"""


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


def _bool_option(options: dict[str, Any] | None, path: str, default: bool) -> bool:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    if isinstance(current, str):
        return current.strip().lower() in {"1", "true", "yes", "on"}
    return bool(current)


def _knowledge_cache_identity(
    *,
    chunks: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    section_summaries: list[dict[str, Any]],
    profile: str,
    parse_options: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    options = parse_options or {}
    identity = {
        "prompt_version": KNOWLEDGE_PROMPT_VERSION,
        "profile": profile,
        "chunks": [
            {
                "hash": chunk.get("normalized_content_hash") or chunk.get("content_hash") or stable_hash(clean_text(chunk.get("content")), 40),
                "chunk_type": chunk.get("chunk_type"),
                "section_type": chunk.get("section_type"),
            }
            for chunk in chunks
        ],
        "sections": [
            {
                "section_id": section.get("section_id"),
                "parent_section_id": section.get("parent_section_id"),
                "title": clean_text(section.get("title") or section.get("section_title")),
                "section_path": section.get("section_path") or section.get("section_path_text"),
                "section_type": section.get("section_type"),
            }
            for section in sections
        ],
        "section_summaries": [
            stable_hash(clean_text(summary.get("node_summary") or summary.get("summary")), 40)
            for summary in section_summaries
        ],
        "settings": {
            "max_input_chars": _int_option(options, "knowledge.max_input_chars", 18000),
            "pass_count": extraction_pass_count(options),
            "merge_overlaps": merge_overlaps_enabled(options),
            "gleanings_enabled": _bool_option(options, "knowledge.gleanings.enabled", False),
            "gleanings_max_rounds": _int_option(options, "knowledge.gleanings.max_rounds", 1),
        },
    }
    return build_extraction_cache_key(identity), identity


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except Exception:
        return default
    if result < 0:
        return 0.0
    if result > 1:
        return 1.0
    return result


def _quote_alignment_in_chunks(quote: str, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    quote = clean_text(quote)
    if not quote:
        return None
    return align_quote_to_chunks(quote, chunks)


def _quote_in_chunks(quote: str, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    result = _quote_alignment_in_chunks(quote, chunks)
    return result.get("chunk") if result else None


def _chunk_context(chunks: list[dict[str, Any]], max_chars: int) -> str:
    return format_chunks_for_prompt(chunks, max_chars=max_chars, chunk_type=None, max_text_chars=4000)


def _summary_context(section_summaries: list[dict[str, Any]], max_items: int = 24) -> str:
    return format_summaries_for_prompt(section_summaries, max_items=max_items, max_chars=8000, max_summary_chars=450)


def _is_main_chunk(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    return metadata.get("content_role") != "appendix" and chunk.get("section_type") != "appendix"


# Profiles where the business terms above are NOT generic — they are core domain anchors
_NON_GENERIC_PROFILES = {"business_plan", "guarantee_plan"}


def _is_generic_anchor(name: str, profile: str | None = None) -> bool:
    normalized = clean_text(name).replace(" ", "")
    if not normalized:
        return True
    # For business/guarantee plans, terms like 额度, 期限, 对象 are core anchors
    if (profile or "").strip().lower() in _NON_GENERIC_PROFILES:
        return _is_clause_number(normalized)
    if normalized in GENERIC_ANCHOR_TEXTS:
        return True
    return _is_clause_number(normalized)


def _is_clause_number(name: str) -> bool:
    return name.startswith("第") and name.endswith(("条", "章", "节", "款")) and len(name) <= 6


def _normalize_payload_schema(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"anchors": [], "knowledge_units": [], "relations": [], "warnings": ["knowledge_payload_not_object"]}
    if "anchors" in payload or "knowledge_units" in payload:
        return payload
    anchors: list[dict[str, Any]] = []
    anchor_name_to_id: dict[str, str] = {}
    for index, raw in enumerate(payload.get("new_anchor_candidates") or [], 1):
        if not isinstance(raw, dict):
            continue
        name = clean_text(raw.get("anchor_text"))
        if not name:
            continue
        anchor_id = f"a{index}"
        anchor_name_to_id[name] = anchor_id
        anchors.append(
            {
                "anchor_id": anchor_id,
                "anchor_type": clean_text(raw.get("anchor_type")) or "other",
                "name": name,
                "aliases": raw.get("aliases") if isinstance(raw.get("aliases"), list) else [],
                "description": clean_text(raw.get("parent_path")),
                "evidence_quote": clean_text(raw.get("evidence_quote")),
                "confidence": raw.get("confidence", 0.7),
            }
        )
    units: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("knowledge_unit_candidates") or [], 1):
        if not isinstance(raw, dict):
            continue
        subject = clean_text(raw.get("subject_anchor_text"))
        condition_key = clean_text(raw.get("condition_key"))
        normalized_json = raw.get("normalized_json") if isinstance(raw.get("normalized_json"), dict) else {}
        if condition_key:
            normalized_json = {**normalized_json, "condition_key": condition_key}
        units.append(
            {
                "unit_id": f"u{index}",
                "anchor_id": anchor_name_to_id.get(subject, ""),
                "unit_type": clean_text(raw.get("unit_type")) or "other",
                "unit_subtype": clean_text(raw.get("unit_subtype")),
                "subject": subject,
                "predicate": clean_text(raw.get("predicate_name")),
                "object_text": clean_text(raw.get("object_text")),
                "value_type": clean_text(raw.get("value_type")) or "text",
                "normalized_json": normalized_json,
                "searchable_text": clean_text(f"{subject} {condition_key} {raw.get('predicate_name')} {raw.get('object_text')} {raw.get('evidence_quote')}"),
                "evidence_quote": clean_text(raw.get("evidence_quote")),
                "confidence": raw.get("confidence", 0.7),
            }
        )
    return {
        "anchors": anchors,
        "knowledge_units": units,
        "relations": payload.get("relations") or [],
        "warnings": payload.get("warnings") or [],
    }


def extract_knowledge_structure(
    *,
    chunks: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    section_summaries: list[dict[str, Any]],
    profile: str,
    parse_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the 1.4 LLM extraction layer and script-side evidence alignment."""
    small_chunks = [chunk for chunk in chunks if chunk.get("chunk_type") == "small_chunk"]
    primary_chunks = [chunk for chunk in small_chunks if _is_main_chunk(chunk)] or small_chunks or chunks
    graph_visual_types = {"image", "image_group", "chart", "diagram", "flowchart"}
    visual_chunks = [
        chunk for chunk in chunks
        if chunk.get("chunk_type") in graph_visual_types and _is_main_chunk(chunk)
    ]
    # Preserve text-first extraction while reserving graph evidence for visual
    # process/field relationships that plain Chunk retrieval cannot express.
    evidence_chunks = [*primary_chunks, *visual_chunks]
    max_chars = max(2000, _int_option(parse_options, "knowledge.max_input_chars", 18000))
    client = JsonChatClient("KNOWLEDGE", default_model=True)
    section_index = {
        str(section.get("section_id")): section
        for section in sections
        if section.get("section_id")
    }
    user_prompt = f"""## Profile
{profile}

## Section Summaries
{_summary_context(section_summaries)}

## 输出 JSON Schema
{{
  "anchors": [
    {{
      "anchor_id": "a1",
      "anchor_type": "plan|rule_document|department|role|system|module|api|process|subject|section_object|other",
      "name": "Anchor 名称",
      "aliases": [],
      "description": "为什么它是可问对象",
      "evidence_quote": "原文短句",
      "confidence": 0.95
    }}
  ],
  "knowledge_units": [
    {{
      "unit_id": "u1",
      "anchor_id": "a1",
      "unit_type": "scope|condition|rule|formula|amount|rate|term|purpose|responsibility|process_step|api_param|config|reference|risk_control|other",
      "unit_subtype": "更细分类",
      "subject": "该知识单元说的是谁/什么",
      "predicate": "规则/条件/职责/参数名",
      "object_text": "完整知识内容",
      "value_type": "text|number|amount|rate|date|duration|formula|list|json|unknown",
      "normalized_json": {{}},
      "searchable_text": "用于检索的增强文本，包含对象、章节、谓词、原文证据",
      "evidence_quote": "原文短句，必须来自输入",
      "confidence": 0.95
    }}
  ],
  "relations": [
    {{
      "relation_id": "r1",
      "relation_type": "has_unit|applies_to|belongs_to|responsible_for|approves|prohibits|requires|constrained_by|depends_on|occurs_before|references|contains|alias_of|related_to",
      "from_type": "anchor|unit|section",
      "from_id": "a1",
      "to_type": "anchor|unit|section",
      "to_id": "u1",
      "evidence_quote": "原文短句",
      "confidence": 0.9,
      "confidence_label": "EXTRACTED|INFERRED|AMBIGUOUS"
    }}
  ],
  "warnings": []
}}

## 原文文本 chunks（用于事实与原文证据）
{_chunk_context(primary_chunks, int(max_chars * 0.75))}

## 多模态/流程图 chunks（用于步骤、角色、字段和依赖关系；不可臆测图片中没有的内容）
{_chunk_context(visual_chunks, int(max_chars * 0.25))}
"""
    cache_key, cache_identity = _knowledge_cache_identity(
        chunks=evidence_chunks,
        sections=sections,
        section_summaries=section_summaries,
        profile=profile,
        parse_options=parse_options,
    )
    cache_enabled = _bool_option(parse_options, "knowledge.cache.enabled", True)
    cached = load_extraction_cache(cache_key) if cache_enabled else None
    cache_hit = bool(cached and isinstance(cached.get("payload"), dict))
    pass_warnings: list[str] = []
    raw_payloads: list[dict[str, Any]] = []
    gleaning_count = 0
    if cache_hit:
        payload = dict(cached.get("payload") or {})
        merge_report = dict(cached.get("merge_report") or {})
        raw_pass_count = int(cached.get("raw_pass_count") or 0)
        gleaning_count = int(cached.get("gleaning_count") or 0)
    else:
        pass_count = extraction_pass_count(parse_options)
        for pass_index in range(pass_count):
            temperature = 0 if pass_index == 0 else min(0.35, 0.15 + (pass_index - 1) * 0.1)
            try:
                raw = client.complete_json(_knowledge_system_prompt(profile), user_prompt, temperature=temperature)
            except Exception as exc:
                pass_warnings.append(f"knowledge_llm_failed_pass_{pass_index + 1}:{exc}")
                continue
            if isinstance(raw, dict):
                raw_payloads.append(_normalize_payload_schema(raw))
        if not raw_payloads:
            return {"anchors": [], "knowledge_units": [], "relations": [], "warnings": pass_warnings or ["knowledge_llm_failed:empty_response"]}

        if _bool_option(parse_options, "knowledge.gleanings.enabled", False):
            max_gleanings = max(0, min(_int_option(parse_options, "knowledge.gleanings.max_rounds", 1), 3))
            for gleaning_index in range(max_gleanings):
                current_payload, _ = _merge_knowledge_payload_passes(
                    raw_payloads,
                    merge_overlaps=merge_overlaps_enabled(parse_options),
                )
                existing = json.dumps(current_payload, ensure_ascii=False)[:12000]
                gleaning_prompt = f"""请对上一轮知识图抽取做遗漏检查，只补充尚未出现且有逐字原文证据的 Anchor、Knowledge Unit 和 Relation。
不得重复已有事实，不得改写 evidence_quote；没有遗漏时返回 anchors、knowledge_units、relations 均为空的 JSON。

## 已有抽取
{existing}

## 原文
{_chunk_context(evidence_chunks, max_chars)}
"""
                try:
                    gleaned = client.complete_json(
                        _knowledge_system_prompt(profile),
                        gleaning_prompt,
                        temperature=0,
                    )
                except Exception as exc:
                    pass_warnings.append(f"knowledge_gleaning_failed_{gleaning_index + 1}:{exc}")
                    break
                normalized_gleaning = _normalize_payload_schema(gleaned if isinstance(gleaned, dict) else {})
                if not any(normalized_gleaning.get(key) for key in ("anchors", "knowledge_units", "relations")):
                    break
                raw_payloads.append(normalized_gleaning)
                gleaning_count += 1

        raw_pass_count = len(raw_payloads) - gleaning_count
        payload, merge_report = _merge_knowledge_payload_passes(
            raw_payloads,
            merge_overlaps=merge_overlaps_enabled(parse_options),
        )
        if cache_enabled:
            save_extraction_cache(
                cache_key,
                {
                    "prompt_version": KNOWLEDGE_PROMPT_VERSION,
                    "identity": cache_identity,
                    "payload": payload,
                    "merge_report": merge_report,
                    "raw_pass_count": raw_pass_count,
                    "gleaning_count": gleaning_count,
                },
            )
    normalized = normalize_knowledge_payload(payload, primary_chunks=evidence_chunks, section_index=section_index, profile=profile)
    normalized["_debug"] = {
        "multi_pass": {
            **merge_report,
            "merge_overlaps": merge_overlaps_enabled(parse_options),
            "pass_count": int(merge_report.get("pass_count") or raw_pass_count + gleaning_count),
            "base_pass_count": raw_pass_count,
            "gleaning_count": gleaning_count,
        },
        "extraction_cache": {
            "enabled": cache_enabled,
            "hit": cache_hit,
            "cache_key": cache_key,
            "prompt_version": KNOWLEDGE_PROMPT_VERSION,
        },
    }
    if pass_warnings:
        normalized["warnings"] = [*(normalized.get("warnings") or []), *pass_warnings]
    return normalized


def _merge_knowledge_payload_passes(
    payloads: list[dict[str, Any]],
    *,
    merge_overlaps: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    anchor_lists = [payload.get("anchors") or [] for payload in payloads]
    unit_lists = [payload.get("knowledge_units") or [] for payload in payloads]
    relation_lists = [payload.get("relations") or [] for payload in payloads]
    anchors, anchor_report = merge_pass_record_lists(
        anchor_lists,
        exact_fields=["anchor_type", "name", "evidence_quote"],
        group_fields=["anchor_type", "name"],
        text_fields=["evidence_quote", "description"],
        merge_overlaps=merge_overlaps,
    )
    units, unit_report = merge_pass_record_lists(
        unit_lists,
        exact_fields=["unit_type", "anchor_id", "subject", "predicate", "object_text", "evidence_quote"],
        group_fields=["unit_type", "anchor_id", "subject", "predicate"],
        text_fields=["evidence_quote", "object_text"],
        merge_overlaps=merge_overlaps,
    )
    relations, relation_report = merge_pass_record_lists(
        relation_lists,
        exact_fields=["relation_type", "from_type", "from_id", "to_type", "to_id", "evidence_quote"],
        group_fields=["relation_type", "from_type", "from_id", "to_type", "to_id"],
        text_fields=["evidence_quote"],
        merge_overlaps=False,
    )
    warnings = []
    for payload in payloads:
        warnings.extend(clean_text(item) for item in (payload.get("warnings") or []) if clean_text(item))
    report = {
        "pass_count": len(payloads),
        "anchor_newly_added_count": anchor_report["newly_added_count"],
        "unit_newly_added_count": unit_report["newly_added_count"],
        "relation_newly_added_count": relation_report["newly_added_count"],
        "newly_added_count": anchor_report["newly_added_count"] + unit_report["newly_added_count"] + relation_report["newly_added_count"],
        "anchor_overlap_dropped_count": anchor_report["overlap_dropped_count"],
        "unit_overlap_dropped_count": unit_report["overlap_dropped_count"],
        "relation_overlap_dropped_count": relation_report["overlap_dropped_count"],
        "overlap_dropped_count": anchor_report["overlap_dropped_count"] + unit_report["overlap_dropped_count"] + relation_report["overlap_dropped_count"],
        "exact_dropped_count": anchor_report["exact_dropped_count"] + unit_report["exact_dropped_count"] + relation_report["exact_dropped_count"],
    }
    return {
        "anchors": anchors,
        "knowledge_units": units,
        "relations": relations,
        "warnings": warnings,
    }, report


def normalize_knowledge_payload(
    payload: dict[str, Any],
    *,
    primary_chunks: list[dict[str, Any]],
    section_index: dict[str, dict[str, Any]],
    profile: str | None = None,
) -> dict[str, Any]:
    anchors: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    warnings: list[str] = []
    anchor_id_map: dict[str, str] = {}
    for index, raw in enumerate(payload.get("anchors") or [], 1):
        if not isinstance(raw, dict):
            continue
        name = clean_text(raw.get("name") or raw.get("anchor_name"))
        quote = clean_text(raw.get("evidence_quote"))
        alignment_result = _quote_alignment_in_chunks(quote, primary_chunks)
        chunk = alignment_result.get("chunk") if alignment_result else None
        alignment = alignment_result.get("alignment") if alignment_result else None
        if _is_generic_anchor(name, profile):
            warnings.append(f"anchor_generic_dropped:{name or index}")
            continue
        if not name or not quote or not chunk:
            warnings.append(f"anchor_evidence_unaligned:{name or index}")
            continue
        anchor_id = clean_text(raw.get("anchor_id")) or f"a_{stable_hash(name, 12)}"
        stable_id = f"anchor_{canonical_key('anchor', name, quote, length=16) or stable_hash(anchor_id, 16)}"
        anchor_id_map[anchor_id] = stable_id
        anchors.append(
            {
                "anchor_id": stable_id,
                "anchor_type": clean_text(raw.get("anchor_type")) or "other",
                "anchor_name": name,
                "normalized_name": clean_text(name).lower(),
                "aliases": [clean_text(item) for item in (raw.get("aliases") or []) if clean_text(item)],
                "source_section_id": chunk.get("section_id"),
                "source_chunk_key": chunk.get("chunk_key"),
                "evidence_quote": quote,
                "confidence": _float(raw.get("confidence"), 0.7),
                "metadata": {
                    "description": clean_text(raw.get("description")),
                    "raw_anchor_id": anchor_id,
                    "evidence_alignment": alignment.to_dict() if alignment else None,
                },
            }
        )
    anchors, anchor_remap, anchor_dedup_warnings = deduplicate_anchors(anchors)
    if anchor_remap:
        anchor_id_map = {raw_id: anchor_remap.get(stable_id, stable_id) for raw_id, stable_id in anchor_id_map.items()}
    warnings.extend(anchor_dedup_warnings)
    for index, raw in enumerate(payload.get("knowledge_units") or [], 1):
        if not isinstance(raw, dict):
            continue
        quote = clean_text(raw.get("evidence_quote"))
        alignment_result = _quote_alignment_in_chunks(quote, primary_chunks)
        chunk = alignment_result.get("chunk") if alignment_result else None
        alignment = alignment_result.get("alignment") if alignment_result else None
        object_text = clean_text(raw.get("object_text"))
        if not quote or not chunk or not object_text:
            warnings.append(f"unit_evidence_unaligned:{raw.get('unit_id') or index}")
            continue
        raw_anchor_id = clean_text(raw.get("anchor_id"))
        anchor_id = anchor_id_map.get(raw_anchor_id, raw_anchor_id or None)
        unit_id = clean_text(raw.get("unit_id")) or f"u_{index}"
        stable_id = f"unit_{canonical_key('unit', raw.get('unit_type'), raw.get('subject'), raw.get('predicate'), object_text, quote, length=18) or stable_hash(unit_id, 18)}"
        normalized_json = raw.get("normalized_json") if isinstance(raw.get("normalized_json"), dict) else {}
        units.append(
            {
                "unit_id": stable_id,
                "unit_type": clean_text(raw.get("unit_type")) or "other",
                "unit_subtype": clean_text(raw.get("unit_subtype")) or None,
                "anchor_id": anchor_id,
                "subject_text": clean_text(raw.get("subject")),
                "predicate_text": clean_text(raw.get("predicate")),
                "object_text": object_text,
                "value_type": clean_text(raw.get("value_type")) or "text",
                "normalized_json": normalized_json,
                "source_section_id": chunk.get("section_id"),
                "primary_chunk_key": chunk.get("chunk_key"),
                "evidence_quote": quote,
                "confidence": _float(raw.get("confidence"), 0.7),
                "metadata": {
                    "searchable_text": clean_text(raw.get("searchable_text")) or clean_text(f"{raw.get('subject')} {raw.get('predicate')} {object_text} {quote}"),
                    "raw_unit_id": unit_id,
                    "section_known": chunk.get("section_id") in section_index,
                    "evidence_alignment": alignment.to_dict() if alignment else None,
                },
            }
        )
    known_ids = {item["anchor_id"] for item in anchors} | {item["unit_id"] for item in units} | set(section_index)
    id_map = {**anchor_id_map}
    for item in units:
        raw_unit_id = item.get("metadata", {}).get("raw_unit_id")
        if raw_unit_id:
            id_map[str(raw_unit_id)] = item["unit_id"]
    for index, raw in enumerate(payload.get("relations") or [], 1):
        if not isinstance(raw, dict):
            continue
        from_id = id_map.get(clean_text(raw.get("from_id")), clean_text(raw.get("from_id")))
        to_id = id_map.get(clean_text(raw.get("to_id")), clean_text(raw.get("to_id")))
        if not from_id or not to_id or from_id not in known_ids or to_id not in known_ids:
            warnings.append(f"relation_endpoint_unresolved:{raw.get('relation_id') or index}")
            continue
        quote = clean_text(raw.get("evidence_quote"))
        alignment_result = _quote_alignment_in_chunks(quote, primary_chunks) if quote else None
        chunk = alignment_result.get("chunk") if alignment_result else None
        alignment = alignment_result.get("alignment") if alignment_result else None
        relation_id = clean_text(raw.get("relation_id")) or f"r_{index}"
        relation_type = clean_text(raw.get("relation_type")) or "related_to"
        if relation_type not in ALLOWED_RELATION_TYPES:
            relation_type = "related_to"
        if not relation_type_allowed(profile, relation_type):
            warnings.append(f"relation_schema_rejected:{relation_id}:{relation_type}")
            continue
        stable_id = f"rel_{canonical_key('relation', raw.get('relation_type'), from_id, to_id, quote, length=18) or stable_hash(relation_id, 18)}"
        confidence_label = clean_text(raw.get("confidence_label")).upper()
        if confidence_label not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
            confidence_label = "EXTRACTED" if chunk and quote else "INFERRED"
        relations.append(
            {
                "relation_id": stable_id,
                "relation_type": relation_type,
                "from_type": clean_text(raw.get("from_type")) or "unknown",
                "from_id": from_id,
                "to_type": clean_text(raw.get("to_type")) or "unknown",
                "to_id": to_id,
                "source_chunk_key": chunk.get("chunk_key") if chunk else None,
                "evidence_quote": quote,
                "confidence": _float(raw.get("confidence"), 0.6),
                "metadata": {
                    "raw_relation_id": relation_id,
                    "confidence_label": confidence_label,
                    "evidence_alignment": alignment.to_dict() if alignment else None,
                },
            }
        )
    rule_relations = build_rule_relations(anchors=anchors, units=units, existing_relations=relations)
    if rule_relations:
        allowed_rule_relations = []
        for relation in rule_relations:
            if relation_type_allowed(profile, clean_text(relation.get("relation_type"))):
                allowed_rule_relations.append(relation)
            else:
                warnings.append(f"relation_schema_rejected:{relation.get('relation_id')}:{relation.get('relation_type')}")
        relations.extend(allowed_rule_relations)
        if allowed_rule_relations:
            warnings.append(f"rule_relation_added:{len(allowed_rule_relations)}")
    return {
        "anchors": anchors,
        "knowledge_units": units,
        "relations": relations,
        "warnings": warnings + [clean_text(item) for item in (payload.get("warnings") or []) if clean_text(item)],
    }
