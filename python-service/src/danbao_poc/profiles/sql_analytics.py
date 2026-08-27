"""Structured indexing helpers for NL2SQL knowledge objects.

The active ``sql_analytics`` profile uses the shared LLM catalog planner and
accepts ordinary Markdown.  The deterministic builder in this module remains
available for callers that explicitly publish governed knowledge objects.
"""
from __future__ import annotations

import json
import re
from typing import Any

from danbao_poc.catalog_chunker import CatalogBuildResult
from danbao_poc.chunk_generation import build_multigranularity_chunks
from danbao_poc.common import clean_text, stable_hash


PROFILE_CODE = "sql_analytics"

_BEGIN = "===== BEGIN_KNOWLEDGE_CHUNK ====="
_END = "===== END_KNOWLEDGE_CHUNK ====="
_OBJECT_TYPES = {
    "SCENE",
    "SCHEMA",
    "TABLE",
    "FIELD",
    "DIMENSION",
    "ENUM",
    "TERM",
    "METRIC",
    "TIME_RULE",
    "VERIFIED_SQL",
    "VERIFIED_QUERY",
}
_SECTION_TYPE_BY_OBJECT_TYPE = {
    "SCENE": "scene",
    "SCHEMA": "schema",
    "TABLE": "table",
    "FIELD": "field",
    "DIMENSION": "dimension",
    "ENUM": "enum",
    "TERM": "term",
    "METRIC": "metric",
    "TIME_RULE": "time_rule",
    "VERIFIED_SQL": "verified_sql",
    "VERIFIED_QUERY": "verified_sql",
}
_KEY_ALIASES = {
    "objectid": "object_id",
    "objecttype": "object_type",
    "scenecode": "scene_code",
    "businessdomaincode": "business_domain_code",
    "reviewstatus": "review_status",
    "retrievalenabled": "retrieval_enabled",
    "termcode": "term_code",
    "metriccode": "metric_code",
    "examplecode": "example_code",
    "querytype": "query_type",
    "aggregationtype": "aggregation_type",
    "timegrains": "time_grains",
    "datafreshness": "data_freshness",
    "fixedfilter": "fixed_filter",
    "fixedfilterjson": "fixed_filter",
    "relatedtableids": "related_table_ids",
    "relatedfieldids": "related_field_ids",
    "relatedmetriccodes": "related_metric_codes",
    "relatedmetricids": "related_metric_ids",
    "metricids": "metric_ids",
    "aliases": "aliases",
    "aliasesjson": "aliases",
    "examplequestions": "example_questions",
    "examplequestionsjson": "example_questions",
    "timegrainsjson": "time_grains",
    "relatedtableidsjson": "related_table_ids",
    "relatedfieldidsjson": "related_field_ids",
    "relatedmetriccodesjson": "related_metric_codes",
    "relatedmetricidsjson": "related_metric_ids",
    "metricidsjson": "metric_ids",
    "validationslice": "validation_slice",
    "validatedvalue": "validated_value",
    "validatedresult": "validated_result",
    "contenthash": "declared_content_hash",
    "datasourcekey": "datasource_key",
    "tablename": "table_name",
    "fieldname": "field_name",
    "fieldcode": "field_code",
    "dimensioncode": "dimension_code",
}
_LINE_FIELD = re.compile(r"^\s*(?:[-*]\s*)?([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")
_H1 = re.compile(r"(?m)^#\s+(.+?)\s*$")
_SQL_BLOCK = re.compile(r"```sql\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_BEGIN_END = re.compile(
    rf"{re.escape(_BEGIN)}\s*(.*?)\s*{re.escape(_END)}",
    re.DOTALL,
)


def _canonical_key(raw: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]", "", raw).lower()
    if compact in _KEY_ALIASES:
        return _KEY_ALIASES[compact]
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", raw).replace("-", "_").lower()
    return snake


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    try:
        return json.loads(value)
    except Exception:
        return value.strip('"').strip("'")


def _section_text(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\s*(.*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(text)
    return clean_text(match.group(1)) if match else ""


def _source_text(middle_document: dict[str, Any]) -> str:
    text = middle_document.get("normalized_text") or middle_document.get("plain_text")
    if clean_text(text):
        return str(text)
    parts: list[str] = []
    for page in middle_document.get("pages") or []:
        for block in page.get("blocks") or []:
            value = block.get("markdown") or block.get("text")
            if clean_text(value):
                parts.append(str(value))
    return "\n\n".join(parts)


def _split_objects(text: str) -> list[str]:
    marked = [match.group(1).strip() for match in _BEGIN_END.finditer(text)]
    return marked or ([text.strip()] if text.strip() else [])


def _metadata_from_object(text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for line in text.splitlines():
        match = _LINE_FIELD.match(line)
        if not match:
            continue
        key = _canonical_key(match.group(1))
        value = _parse_value(match.group(2))
        if value != "":
            metadata[key] = value

    object_type = clean_text(metadata.get("object_type")).upper()
    metadata["object_type"] = "VERIFIED_SQL" if object_type == "VERIFIED_QUERY" else object_type
    h1 = _H1.search(text)
    if h1:
        metadata["source_title"] = clean_text(h1.group(1))

    # Single-object Markdown stores the main values under semantic headings.
    if metadata["object_type"] == "TERM":
        metadata.setdefault("definition", _section_text(text, "定义"))
    elif metadata["object_type"] == "METRIC":
        metadata.setdefault("business_definition", _section_text(text, "业务定义"))
        metadata.setdefault("pitfall_notes", _section_text(text, "易错点"))
    elif metadata["object_type"] == "VERIFIED_SQL":
        metadata.setdefault("question_text", _section_text(text, "用户问题"))
        metadata.setdefault("normalized_question", _section_text(text, "归一化问题"))
        metadata.setdefault("description", _section_text(text, "说明"))

    sql_blocks = [clean_text(value) for value in _SQL_BLOCK.findall(text) if clean_text(value)]
    if sql_blocks:
        if metadata["object_type"] == "METRIC":
            metadata.setdefault("sql_expression", sql_blocks[0])
        elif metadata["object_type"] == "VERIFIED_SQL":
            metadata.setdefault("sql_text", sql_blocks[0])
    return metadata


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    if clean_text(value):
        return [clean_text(value)]
    return []


def _title(metadata: dict[str, Any]) -> str:
    for key in (
        "name",
        "source_title",
        "question_text",
        "table_name",
        "field_name",
        "metric_code",
        "term_code",
        "example_code",
        "object_id",
    ):
        if clean_text(metadata.get(key)):
            return clean_text(metadata[key])
    return "SQL问数知识对象"


def _required_fields(object_type: str) -> tuple[str, ...]:
    return {
        "TERM": ("term_code", "definition"),
        "METRIC": ("metric_code", "business_definition", "aggregation_type", "sql_expression"),
        "VERIFIED_SQL": ("example_code", "question_text", "sql_text", "review_status"),
        "TABLE": ("table_name",),
        "FIELD": ("field_name",),
        "DIMENSION": ("dimension_code",),
    }.get(object_type, ())


def _publishability_errors(metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    object_id = clean_text(metadata.get("object_id"))
    object_type = clean_text(metadata.get("object_type")).upper()
    scene_code = clean_text(metadata.get("scene_code"))
    if not object_id:
        errors.append("missing_object_id")
    if object_type not in _OBJECT_TYPES:
        errors.append(f"unsupported_object_type:{object_type or 'EMPTY'}")
    if not scene_code:
        errors.append("missing_scene_code")
    for field in _required_fields(object_type):
        if not clean_text(metadata.get(field)):
            errors.append(f"missing_{field}")
    status = clean_text(metadata.get("status")).upper()
    if status and status != "ACTIVE":
        errors.append(f"status_not_active:{status}")
    if object_type in {"METRIC", "VERIFIED_SQL"}:
        review_status = clean_text(metadata.get("review_status")).upper()
        if review_status != "VERIFIED":
            errors.append(f"review_status_not_verified:{review_status or 'EMPTY'}")
    if object_type == "VERIFIED_SQL" and metadata.get("retrieval_enabled") is not True:
        errors.append("retrieval_not_enabled")
    if object_id and object_type:
        expected_prefix = {
            "TERM": "term.",
            "METRIC": "metric.",
            "VERIFIED_SQL": "verified_sql.",
        }.get(object_type)
        if expected_prefix and not object_id.lower().startswith(expected_prefix):
            errors.append(f"object_id_prefix_mismatch:{expected_prefix}")
    return errors


def _embedding_source(metadata: dict[str, Any]) -> str:
    values: list[str] = [_title(metadata)]
    for key in (
        "object_id",
        "metric_code",
        "term_code",
        "example_code",
        "aliases",
        "example_questions",
        "definition",
        "business_definition",
        "question_text",
        "normalized_question",
        "description",
        "pitfall_notes",
        "aggregation_type",
        "unit",
        "time_grains",
        "fixed_filter",
    ):
        value = metadata.get(key)
        if isinstance(value, list):
            values.extend(clean_text(item) for item in value if clean_text(item))
        elif clean_text(value):
            values.append(clean_text(value))
    return clean_text("\n".join(values))[:4000]


def build_sql_analytics_catalog(
    middle_document: dict[str, Any],
    *,
    profile: str,
    document_title: str,
    parse_options: dict[str, Any] | None,
) -> CatalogBuildResult:
    source_text = _source_text(middle_document)
    records = _split_objects(source_text)
    warnings: list[str] = []
    rejected: list[dict[str, Any]] = []
    base_chunks: list[dict[str, Any]] = []
    mapped_sections: list[dict[str, Any]] = []
    seen_object_ids: set[str] = set()

    for record_index, record in enumerate(records, 1):
        metadata = _metadata_from_object(record)
        object_id = clean_text(metadata.get("object_id"))
        errors = _publishability_errors(metadata)
        if object_id in seen_object_ids:
            errors.append("duplicate_object_id")
        if errors:
            rejected.append({"recordIndex": record_index, "objectId": object_id or None, "errors": errors})
            warnings.extend(f"sql_analytics_object_rejected:{record_index}:{error}" for error in errors)
            continue
        seen_object_ids.add(object_id)
        object_type = clean_text(metadata.get("object_type")).upper()
        section_type = _SECTION_TYPE_BY_OBJECT_TYPE[object_type]
        title = _title(metadata)
        section_id = f"sqlobj_{stable_hash(object_id, 16)}"
        aliases = _as_list(metadata.get("aliases"))
        example_questions = _as_list(metadata.get("example_questions"))
        possible_questions = list(example_questions)
        if clean_text(metadata.get("question_text")):
            possible_questions.insert(0, clean_text(metadata["question_text"]))
        if object_type == "TERM" and title:
            possible_questions.append(f"什么是{title}？")
        keywords = [
            value
            for value in [object_id, object_type, metadata.get("metric_code"), metadata.get("term_code"), metadata.get("example_code"), title, *aliases]
            if clean_text(value)
        ]
        chunk_metadata = {
            **metadata,
            "profile": PROFILE_CODE,
            "catalog_source": "deterministic_sql_analytics",
            "confidence": "VERIFIED",
            "content_role": "knowledge_object",
            "section_path": [document_title, object_type, title],
            "embedding_source_text": _embedding_source(metadata),
            "keywords": keywords,
            "possible_questions": possible_questions,
            "enrichment_source": "governed_sql_analytics_object",
        }
        base_chunks.append(
            {
                "chunk_key": f"sql_object_{record_index:03d}",
                "seq_no": len(base_chunks) + 1,
                "chunk_type": "knowledge_object",
                "section_type": section_type,
                "section_id": section_id,
                "chunk_group_id": f"object:{object_id}",
                "title": title,
                "title_path": [document_title, object_type, title],
                "content": record,
                "page_start": None,
                "page_end": None,
                "block_ids": [],
                "bbox": [],
                "metadata": chunk_metadata,
            }
        )
        mapped_sections.append(
            {
                "section_id": section_id,
                "parent_section_id": None,
                "title": title,
                "section_path": [document_title, object_type, title],
                "section_level": 1,
                "section_type": section_type,
                "content_role": "knowledge_object",
                "page_start": None,
                "page_end": None,
                "block_ids": [],
                "mapping_confidence": 1.0,
                "object_id": object_id,
                "object_type": object_type,
            }
        )

    if not base_chunks:
        details = "; ".join(error for item in rejected for error in item.get("errors") or [])[:500]
        raise ValueError(f"sql_analytics_no_publishable_objects: {details or 'no knowledge object found'}")

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
            "catalog_source": "deterministic_sql_analytics",
            "fallback": None,
            "profile": profile,
            "record_count": len(records),
            "published_object_count": len(base_chunks),
            "rejected_object_count": len(rejected),
            "rejected_objects": rejected,
            "object_ids": sorted(seen_object_ids),
            "object_types": sorted({clean_text(item["metadata"].get("object_type")) for item in base_chunks}),
            "mapped_sections": mapped_sections,
        },
    )


def extract_sql_analytics_fields(
    chunks: list[dict[str, Any]],
    parse_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose governed objects and LLM-planned Markdown chunks to retrieval.

    This is a local, deterministic projection.  It does not call a model or
    create a summary, so loose Markdown keeps the structured search route
    without reintroducing the expensive enrichment pipeline.
    """
    del parse_options
    fields: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        section_type = clean_text(chunk.get("section_type")) or "text_section"
        object_type = clean_text(metadata.get("object_type")).lower() or section_type
        content = clean_text(chunk.get("content"))
        title = clean_text(chunk.get("title")) or "SQL问数知识"
        semantic_identity = f"{title}\n{content}"
        object_id = clean_text(metadata.get("object_id")) or (
            f"semantic_chunk.{object_type}.{stable_hash(semantic_identity, 16)}"
        )
        aliases = _as_list(metadata.get("aliases"))
        if not aliases:
            alias_match = re.search(r"(?m)^\s*别名\s*[：:]\s*(.+?)\s*$", content)
            if alias_match:
                aliases = _as_list(_parse_value(alias_match.group(1)))
        governed = bool(metadata.get("object_id") and metadata.get("object_type"))
        fields.append(
            {
                "field_key": f"sql_object_{index:03d}_{stable_hash(object_id, 12)}",
                "field_code": object_type,
                "field_name_cn": title,
                "value_text": content,
                "aliases": aliases,
                "normalized_json": {
                    "object_id": object_id,
                    "object_type": object_type.upper(),
                    **{
                        key: metadata.get(key)
                        for key in (
                            "scene_code",
                            "metric_code",
                            "term_code",
                            "example_code",
                            "query_type",
                            "aggregation_type",
                            "unit",
                            "related_metric_codes",
                            "related_table_ids",
                            "related_field_ids",
                        )
                        if metadata.get(key) not in (None, "", [])
                    },
                },
                "source_chunk_key": chunk.get("chunk_key"),
                "source_section_type": chunk.get("section_type"),
                "metadata": {
                    "profile": PROFILE_CODE,
                    "content_hash": stable_hash(content),
                    "evidence_quote": content,
                    "confidence": "HIGH" if governed else "MEDIUM",
                    "object_id": object_id,
                    "object_type": object_type.upper(),
                    "catalog_source": clean_text(metadata.get("catalog_source")) or "llm_catalog",
                    "governed_object": governed,
                },
                "mention": {
                    "evidence_text": content,
                    "page_no": chunk.get("page_start"),
                    "block_ids": chunk.get("block_ids") or [],
                    "bbox": chunk.get("bbox") or [],
                },
            }
        )
    return {"fields": fields, "_debug": {"source": "sql_analytics_lightweight_projection"}}
