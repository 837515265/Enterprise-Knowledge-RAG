from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .profiles.registry import normalize_profile

ALLOWED_MODES = {"qa", "structured", "section_summary", "graph", "bm25", "vector"}
PROFILE_DEFAULT_MODES = {
    "business_plan": ["qa", "structured", "section_summary", "graph", "bm25", "vector"],
    "guarantee_plan": ["qa", "structured", "section_summary", "graph", "bm25", "vector"],
    "general_document": ["qa", "structured", "section_summary", "bm25", "vector"],
    "governance_rule": ["qa", "structured", "section_summary", "graph", "bm25", "vector"],
    "project_doc": ["qa", "structured", "section_summary", "bm25", "vector"],
    "contract_agreement": ["qa", "structured", "section_summary", "bm25", "vector"],
    "structured_data": ["qa", "structured", "section_summary", "bm25", "vector"],
    "sql_analytics": ["structured", "bm25", "vector"],
    "default": ["qa", "structured", "section_summary", "bm25", "vector"],
}
PROFILE_CONTEXT_RELATIONS = {
    "business_plan": ["section_context", "parent_context", "adjacent_next", "same_business_block", "same_section_type", "same_group", "same_title_parent"],
    "general_document": ["section_context", "parent_context", "adjacent_next", "same_section_type", "same_group", "same_title_parent"],
    "governance_rule": ["section_context", "parent_context", "parent_clause", "adjacent_clause", "same_clause", "same_chapter", "same_section_type", "same_group", "same_title_parent"],
    "project_doc": ["section_context", "parent_context", "same_api", "api_param", "api_example", "api_error_code", "db_schema_related", "config_related", "same_module", "same_section_type", "same_group", "same_title_parent"],
    "contract_agreement": ["section_context", "parent_context", "same_clause", "related_obligation", "payment_breach_related", "term_breach_related", "same_party", "same_section_type", "same_group", "same_title_parent"],
    "structured_data": ["section_context", "same_table", "same_section_type"],
    "sql_analytics": ["same_section_type"],
    "default": ["section_context", "parent_context", "adjacent_next", "same_section_type"],
}


@dataclass(frozen=True)
class RetrievalPlan:
    profile: str
    retrieve_modes: list[str]
    expand_context: bool
    context_relation_types: list[str]
    context_max_chunks: int
    route_reason: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "retrieve_modes": self.retrieve_modes,
            "expand_context": self.expand_context,
            "context_relation_types": self.context_relation_types,
            "context_max_chunks": self.context_max_chunks,
            "route_reason": self.route_reason or {},
        }


class RetrievalPlanBuilder:
    def build(
        self,
        profile: str,
        understanding: dict[str, Any],
        requested_method: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> RetrievalPlan:
        options = options or {}
        normalized_profile = normalize_profile(profile) or profile or "general_document"
        graph_allowed = normalized_profile in {"business_plan", "governance_rule"}
        modes = self._requested_modes(requested_method)
        if not modes:
            modes = [mode for mode in understanding.get("retrieve_modes") or [] if mode in ALLOWED_MODES]
        if not modes:
            modes = list(PROFILE_DEFAULT_MODES.get(normalized_profile, PROFILE_DEFAULT_MODES["default"]))

        relation_intent_hit = bool((understanding.get("route_features") or {}).get("relation_intent_hit"))
        if normalized_profile == "governance_rule" and not relation_intent_hit:
            modes = [mode for mode in modes if mode != "graph"]
        if graph_allowed and normalized_profile == "business_plan" and understanding.get("target_field_codes") and "graph" not in modes:
            modes.insert(0, "graph")
        if not graph_allowed:
            modes = [mode for mode in modes if mode != "graph"]
        # Governed SQL objects must not be replaced by model-generated QA text.
        qa_allowed = normalized_profile != "sql_analytics"
        section_summary_allowed = normalized_profile != "sql_analytics"
        if not qa_allowed:
            modes = [mode for mode in modes if mode != "qa"]
        if not section_summary_allowed:
            modes = [mode for mode in modes if mode != "section_summary"]
        if qa_allowed and "qa" not in modes:
            modes.insert(0, "qa")
        if qa_allowed and float(understanding.get("faq_likelihood") or 0) >= 0.2 and "qa" not in modes:
            modes.insert(0, "qa")
        route_features = understanding.get("route_features") if isinstance(understanding.get("route_features"), dict) else {}
        if route_features.get("possible_question_like"):
            if qa_allowed and "qa" not in modes:
                modes.insert(0, "qa")
            if section_summary_allowed and "section_summary" not in modes:
                modes.insert(1 if modes and modes[0] == "qa" else 0, "section_summary")
        if route_features.get("field_alias_exact"):
            if "structured" not in modes:
                insert_at = 1 if modes and modes[0] == "graph" else 0
                modes.insert(insert_at, "structured")
            if "bm25" not in modes:
                modes.append("bm25")
        if graph_allowed and route_features.get("relation_intent_hit") and "graph" not in modes:
            modes.insert(0, "graph")

        expand_context = bool(options.get("expand_context", True))
        relation_types = options.get("context_relation_types") or PROFILE_CONTEXT_RELATIONS.get(normalized_profile, PROFILE_CONTEXT_RELATIONS["default"])
        context_max_chunks = int(options.get("context_max_chunks") or 8)
        return RetrievalPlan(
            profile=normalized_profile,
            retrieve_modes=self._dedupe_modes(modes),
            expand_context=expand_context,
            context_relation_types=[str(item) for item in relation_types if str(item)],
            context_max_chunks=max(0, min(context_max_chunks, 50)),
            route_reason=understanding.get("route_reason") if isinstance(understanding.get("route_reason"), dict) else {},
        )

    def _requested_modes(self, requested_method: str | None) -> list[str]:
        method = (requested_method or "").strip().lower()
        if not method or method == "hybrid":
            return []
        return [method] if method in ALLOWED_MODES else []

    def _dedupe_modes(self, modes: list[str]) -> list[str]:
        result: list[str] = []
        for mode in modes:
            if mode in ALLOWED_MODES and mode not in result:
                result.append(mode)
        return result or ["bm25", "vector"]
