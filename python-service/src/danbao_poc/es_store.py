from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

from elasticsearch import Elasticsearch, helpers

from urllib.parse import unquote

from .openai_compat import EmbeddingClient
from .product_name_extractor import extract_product_names
from .term_weight import get_term_weighter
from .tokenizer import tokenize_list, tokenize_text

_logger = logging.getLogger(__name__)


def _index_exists_safe(es: Elasticsearch, index: str) -> bool:
    """Check if index exists, handling 403 from ES security plugin on non-existent indices."""
    if not hasattr(es.indices, "exists"):
        return True
    try:
        return es.indices.exists(index=index)
    except Exception as exc:
        if "403" in str(exc) or "AuthorizationException" in type(exc).__name__:
            _logger.debug("indices.exists(%s) returned 403, treating as non-existent", index)
            return False
        raise


CHUNK_INDEX = "knowledge_chunks_v1"
FIELD_INDEX = "knowledge_fields_v1"
QA_INDEX = "knowledge_qa_v1"
SECTION_SUMMARY_INDEX = "section_summary_v1"
ANCHOR_INDEX = "knowledge_anchor_v1"
KNOWLEDGE_UNIT_INDEX = "knowledge_unit_v1"


def clean_join(parts: list[Any]) -> str:
    return "\n".join(str(item).strip() for item in parts if str(item or "").strip())


def _embedding_dimension() -> int:
    return int(os.getenv("EMBEDDING_DIMENSION", "1024"))


_CONFIDENCE_MAP = {"high": 0.95, "medium": 0.7, "low": 0.4, "very_high": 1.0, "very_low": 0.2}


def _safe_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if s in _CONFIDENCE_MAP:
        return _CONFIDENCE_MAP[s]
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _normalize_search_scores(group: list[dict[str, Any]]) -> None:
    if not group:
        return
    scores = [float(row.get("score") or 0.0) for row in group]
    lo, hi = min(scores), max(scores)
    if hi > lo:
        for row in group:
            row["raw_score"] = float(row.get("score") or 0.0)
            row["score"] = (float(row.get("score") or 0.0) - lo) / (hi - lo)
        return
    for row in group:
        raw = float(row.get("score") or 0.0)
        row["raw_score"] = raw
        row["score"] = 1.0 / (1.0 + math.exp(-0.5 * (raw - 5.0)))


def _boost_query_clause(query: dict[str, Any], boost: float) -> dict[str, Any]:
    if "multi_match" in query:
        clause = dict(query)
        clause["multi_match"] = dict(query["multi_match"])
        clause["multi_match"]["boost"] = float(boost) * float(clause["multi_match"].get("boost") or 1.0)
        return clause
    if "bool" in query:
        clause = dict(query)
        clause["bool"] = dict(query["bool"])
        clause["bool"]["boost"] = float(boost) * float(clause["bool"].get("boost") or 1.0)
        return clause
    return query


def _expanded_text_query(
    tw: Any,
    query: str,
    fields: list[str],
    *,
    scope_key: str | None,
    expanded_terms: list[str] | None,
    original_boost: float = 3.0,
    expansion_boost: float = 0.75,
) -> dict[str, Any]:
    original_query = tw.build_weighted_query(tokenize_text(query) or query, fields, scope_key=scope_key)
    expansion_text = tokenize_text(" ".join(expanded_terms or []))
    if not expansion_text:
        return original_query
    expansion_query = tw.build_weighted_query(expansion_text, fields, scope_key=scope_key)
    return {
        "bool": {
            "should": [
                _boost_query_clause(original_query, original_boost),
                _boost_query_clause(expansion_query, expansion_boost),
            ],
            "minimum_should_match": 1,
        }
    }


def _profile_in(profiles: list[str] | None, profile: str) -> bool:
    return bool(profiles) and profile in {str(item) for item in profiles if item}


def client() -> Elasticsearch:
    url = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200").strip().strip('"').strip("'")
    username = os.getenv("ELASTICSEARCH_USERNAME", "").strip().strip('"').strip("'")
    password = os.getenv("ELASTICSEARCH_PASSWORD", "").strip().strip('"').strip("'")
    hosts = [item.strip() for item in url.split(",") if item.strip()] or [url]
    
    if not username and not password:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        if parsed.username or parsed.password:
            username = urllib.parse.unquote(parsed.username or "")
            password = urllib.parse.unquote(parsed.password or "")
            
    if username or password:
        return Elasticsearch(hosts, http_auth=(username, password), verify_certs=False, ssl_show_warn=False)
    return Elasticsearch(hosts, verify_certs=False, ssl_show_warn=False)


def _is_css() -> bool:
    """Check if ES is Huawei Cloud CSS. Controlled by ES_VECTOR_TYPE env var.
    Set to 'css' for Huawei Cloud CSS (SIT/PRD), leave unset for standard ES (dev)."""
    return os.getenv("ES_VECTOR_TYPE", "").strip().lower() == "css"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _css_vector_indexing() -> bool:
    return _env_bool("ES_VECTOR_INDEXING", True)


def _css_vector_metric() -> str:
    return os.getenv("ES_VECTOR_METRIC", "cosine").strip().lower() or "cosine"


def _bulk_index(es: Elasticsearch, actions: list[dict[str, Any]]) -> int:
    if not actions:
        return 0
    chunk_size = int(os.getenv("ES_BULK_CHUNK_SIZE", "500"))
    success, errors = helpers.bulk(
        es,
        actions,
        chunk_size=chunk_size,
        request_timeout=int(os.getenv("ES_BULK_REQUEST_TIMEOUT", "3600")),
        raise_on_error=False,
    )
    if errors:
        sample = errors[:3] if isinstance(errors, list) else errors
        raise RuntimeError(f"bulk index failed: {sample}")
    return int(success)


def _index_action(index: str, doc_id: str, routing: str, document: dict[str, Any]) -> dict[str, Any]:
    return {"_index": index, "_id": doc_id, "_routing": routing, **document}


def ensure_indices(es: Elasticsearch | None = None) -> None:
    es = es or client()
    dim = _embedding_dimension()
    is_css = _is_css()

    if is_css:
        css_indexing = _css_vector_indexing()
        if css_indexing:
            vector_mapping = {"type": "vector", "dimension": dim, "indexing": True, "algorithm": "GRAPH", "metric": _css_vector_metric()}
        else:
            vector_mapping = {"type": "vector", "dimension": dim, "indexing": False}
        _logger.info("ensure_indices: ES_VECTOR_TYPE=css, indexing=%s", css_indexing)
        print(f"[es_store] ES_VECTOR_TYPE=css, vector indexing={css_indexing}", flush=True)
    else:
        vector_mapping = {"type": "dense_vector", "dims": dim}

    # Determine Chinese analyzer: prefer ik_max_word, fallback to standard
    cn_analyzer_name = "cn_analyzer"
    cn_analyzer_settings = {
        "analysis": {
            "analyzer": {
                cn_analyzer_name: {"type": "ik_max_word"}
            }
        },
        "similarity": {
            "scripted_tks": {
                "type": "scripted",
                "script": {
                    "source": "double idf = Math.log(1+(field.docCount-term.docFreq+0.5)/(term.docFreq+0.5)) / Math.log(1+((field.docCount-0.5)/1.5)); return query.boost * idf * Math.min(doc.freq, 1);"
                }
            }
        },
    }
    if is_css:
        cn_analyzer_settings["index"] = {"vector": "true", "number_of_shards": 1, "number_of_replicas": 0}
    # Check if IK plugin is available by attempting to use it;
    # fallback to standard analyzer if not installed
    try:
        es.indices.analyze(body={"analyzer": "ik_max_word", "text": "测试"})
    except Exception:
        cn_analyzer_settings = {
            "analysis": {
                "analyzer": {
                    cn_analyzer_name: {"type": "standard"}
                }
            },
            "similarity": {
                "scripted_tks": {
                    "type": "scripted",
                    "script": {
                        "source": "double idf = Math.log(1+(field.docCount-term.docFreq+0.5)/(term.docFreq+0.5)) / Math.log(1+((field.docCount-0.5)/1.5)); return query.boost * idf * Math.min(doc.freq, 1);"
                    }
                }
            },
        }
        if is_css:
            cn_analyzer_settings["index"] = {"vector": "true", "number_of_shards": 1, "number_of_replicas": 0}

    def _cn_text(extra: dict | None = None) -> dict:
        """Text field with Chinese analyzer."""
        mapping = {"type": "text", "analyzer": cn_analyzer_name}
        if extra:
            mapping.update(extra)
        return mapping

    def _tks_text(extra: dict | None = None) -> dict:
        """Pre-tokenized text field with whitespace analyzer + scripted BM25 (RAGFLOW pattern)."""
        mapping = {"type": "text", "analyzer": "whitespace", "similarity": "scripted_tks"}
        if extra:
            mapping.update(extra)
        return mapping

    def _validate_existing_dims(index_name: str) -> None:
        """Warn if existing index has different vector dimensions than current config."""
        try:
            mapping = es.indices.get_mapping(index=index_name)
            index_mapping = mapping.get(index_name) or next(iter(mapping.values()), {})
            props = (index_mapping.get("mappings") or {}).get("properties", {})
            vec_field = props.get("embedding_vector", {})
            existing_dims = vec_field.get("dims") or vec_field.get("dimension")
            if existing_dims and int(existing_dims) != dim:
                import logging
                logging.getLogger(__name__).warning(
                    "ES index '%s' has embedding_vector dims=%s but current config is %s. "
                    "Delete the index and rebuild if you changed embedding models.",
                    index_name, existing_dims, dim,
                )
        except Exception:
            pass

    def _put_mapping_fields(index_name: str, fields: dict[str, Any]) -> None:
        missing_fields = dict(fields)
        try:
            mapping = es.indices.get_mapping(index=index_name)
            index_mapping = mapping.get(index_name) or next(iter(mapping.values()), {})
            existing_props = (index_mapping.get("mappings") or {}).get("properties") or {}
            missing_fields = {name: value for name, value in fields.items() if name not in existing_props}
        except Exception:
            missing_fields = dict(fields)
        if not missing_fields:
            return
        try:
            try:
                es.indices.put_mapping(index=index_name, properties=missing_fields)
            except TypeError:
                es.indices.put_mapping(index=index_name, body={"properties": missing_fields})
        except Exception:
            import logging
            logging.getLogger(__name__).warning("ES index '%s' mapping patch skipped: %s", index_name, sorted(missing_fields.keys()), exc_info=True)

    def _update_tks_similarity(index_name: str) -> None:
        """Update existing _tks fields to use scripted_tks similarity.

        Only works if scripted_tks similarity is defined in index settings.
        Silently skips if similarity is not available.
        """
        try:
            # Check if scripted_tks similarity exists in this index
            settings = es.indices.get_settings(index=index_name)
            index_settings = settings.get(index_name) or next(iter(settings.values()), {})
            existing_sims = (index_settings.get("settings") or {}).get("index", {}).get("similarity", {})
            if "scripted_tks" not in existing_sims:
                _logger.debug("ensure_indices: scripted_tks not in '%s' settings, skipping tks update", index_name)
                return

            mapping = es.indices.get_mapping(index=index_name)
            index_mapping = mapping.get(index_name) or next(iter(mapping.values()), {})
            existing_props = (index_mapping.get("mappings") or {}).get("properties") or {}
            tks_updates = {}
            for field_name, field_mapping in existing_props.items():
                if field_name.endswith("_tks") and field_mapping.get("type") == "text" and field_mapping.get("similarity") != "scripted_tks":
                    tks_updates[field_name] = {"type": "text", "analyzer": "whitespace", "similarity": "scripted_tks"}
            if tks_updates:
                es.indices.put_mapping(index=index_name, body={"properties": tks_updates})
                _logger.info("ensure_indices: updated %d _tks fields to scripted_tks in '%s'", len(tks_updates), index_name)
        except Exception:
            _logger.warning("ensure_indices: failed to update _tks similarity in '%s'", index_name, exc_info=True)

    def _ensure_similarity(index_name: str) -> None:
        """Add scripted_tks similarity to existing index if missing.

        Note: similarity is a static setting - can only be set during index creation.
        If the index already exists without scripted_tks, we skip the update silently.
        """
        try:
            settings = es.indices.get_settings(index=index_name)
            index_settings = settings.get(index_name) or next(iter(settings.values()), {})
            existing_sims = (index_settings.get("settings") or {}).get("index", {}).get("similarity", {})
            if "scripted_tks" not in existing_sims:
                # Similarity is static - cannot be added to existing open indices
                # Skip silently; will be included on next index creation
                _logger.debug("ensure_indices: scripted_tks similarity missing in '%s' (cannot add to existing index)", index_name)
        except Exception:
            _logger.debug("ensure_indices: failed to check similarity for '%s'", index_name)

    def _ensure_one(index_name: str, create_mappings: dict[str, Any], patch_fields: dict[str, Any]) -> None:
        try:
            if not _index_exists_safe(es, index_name):
                if is_css:
                    # CSS requires body format with settings + mappings combined
                    body = {
                        "settings": cn_analyzer_settings,
                        "mappings": {"properties": create_mappings},
                    }
                    es.indices.create(index=index_name, body=body)
                else:
                    es.indices.create(index=index_name, settings=cn_analyzer_settings, mappings={"properties": create_mappings})
            else:
                _validate_existing_dims(index_name)
                # Similarity updates may fail on existing indices (static settings)
                # Catch individually so they don't block field additions
                try:
                    _ensure_similarity(index_name)
                except Exception:
                    pass
                try:
                    _update_tks_similarity(index_name)
                except Exception:
                    pass
                # Always try to add missing fields incrementally
                _put_mapping_fields(index_name, patch_fields)
        except Exception:
            _logger.warning("ensure_indices: failed to create/patch index '%s'", index_name, exc_info=True)

    _ensure_one(CHUNK_INDEX, {
        "kb_id": {"type": "long"}, "file_node_id": {"type": "long"}, "profile": {"type": "keyword"},
        "chunk_id": {"type": "long"}, "primary_chunk_id": {"type": "long"}, "parent_chunk_id": {"type": "long"},
        "revision_id": {"type": "long"}, "parse_generation": {"type": "keyword"}, "index_generation": {"type": "keyword"},
        "chunk_group_id": {"type": "keyword"}, "content_hash": {"type": "keyword"}, "chunk_type": {"type": "keyword"},
        "section_type": {"type": "keyword"}, "section_id": {"type": "keyword"}, "retrieval_role": {"type": "keyword"},
        "context_level": {"type": "keyword"}, "source_chunk_type": {"type": "keyword"},
        "section_path_text": {"type": "text", "analyzer": cn_analyzer_name},
        "enabled": {"type": "boolean"}, "audit_status": {"type": "keyword"}, "deleted": {"type": "boolean"},
        "doc_name": _cn_text(), "title": _cn_text(), "content": _cn_text(), "content_preview": _cn_text(), "content_for_bm25": _cn_text(),
        "product_names": {"type": "keyword"},
        "keywords": _cn_text(), "possible_questions": _cn_text(),
        "doc_name_tks": _tks_text(), "title_tks": _tks_text(), "content_tks": _tks_text(), "content_for_bm25_tks": _tks_text(), "section_path_text_tks": _tks_text(),
        "keywords_tks": _tks_text(), "questions_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "content_tks_tokens": {"type": "keyword"},
        "embedding_text": {"type": "text"}, "embedding_model": {"type": "keyword"}, "embedding_vector": vector_mapping,
        "page_start": {"type": "integer"}, "page_end": {"type": "integer"},
    }, {
        "index_generation": {"type": "keyword"}, "chunk_group_id": {"type": "keyword"}, "content_hash": {"type": "keyword"},
        "profile": {"type": "keyword"}, "primary_chunk_id": {"type": "long"}, "parent_chunk_id": {"type": "long"},
        "section_id": {"type": "keyword"}, "retrieval_role": {"type": "keyword"}, "context_level": {"type": "keyword"},
        "source_chunk_type": {"type": "keyword"}, "section_path_text": _cn_text(), "section_path_text_tks": _tks_text(),
        "enabled": {"type": "boolean"}, "audit_status": {"type": "keyword"}, "deleted": {"type": "boolean"},
        "doc_name": _cn_text(), "content_preview": _cn_text(), "embedding_model": {"type": "keyword"},
        "product_names": {"type": "keyword"},
        "keywords": _cn_text(), "possible_questions": _cn_text(),
        "doc_name_tks": _tks_text(), "title_tks": _tks_text(), "content_tks": _tks_text(), "content_for_bm25_tks": _tks_text(),
        "keywords_tks": _tks_text(), "questions_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "content_tks_tokens": {"type": "keyword"},
    })

    _ensure_one(FIELD_INDEX, {
        "kb_id": {"type": "long"}, "file_node_id": {"type": "long"}, "profile": {"type": "keyword"},
        "field_id": {"type": "long"}, "source_chunk_id": {"type": "long"}, "parse_generation": {"type": "keyword"},
        "index_generation": {"type": "keyword"}, "enabled": {"type": "boolean"}, "audit_status": {"type": "keyword"},
        "deleted": {"type": "boolean"}, "field_code": {"type": "keyword"}, "doc_name": _cn_text(), "field_name_cn": _cn_text(),
        "product_names": {"type": "keyword"},
        "value_text": _cn_text(), "aliases": _cn_text(),
        "doc_name_tks": _tks_text(), "field_name_cn_tks": _tks_text(), "value_text_tks": _tks_text(), "aliases_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "value_text_tks_tokens": {"type": "keyword"},
        "embedding_text": {"type": "text"}, "embedding_model": {"type": "keyword"}, "embedding_vector": vector_mapping,
    }, {
        "index_generation": {"type": "keyword"}, "profile": {"type": "keyword"}, "enabled": {"type": "boolean"},
        "audit_status": {"type": "keyword"}, "deleted": {"type": "boolean"}, "embedding_model": {"type": "keyword"},
        "product_names": {"type": "keyword"},
        "doc_name": _cn_text(), "doc_name_tks": _tks_text(), "field_name_cn_tks": _tks_text(), "value_text_tks": _tks_text(), "aliases_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "value_text_tks_tokens": {"type": "keyword"},
    })

    _ensure_one(QA_INDEX, {
        "kb_id": {"type": "long"}, "file_node_id": {"type": "long"}, "qa_id": {"type": "long"},
        "product_names": {"type": "keyword"},
        "doc_name": _cn_text(), "question": _cn_text(), "answer": _cn_text(), "extended_questions": _cn_text(),
        "doc_name_tks": _tks_text(), "question_tks": _tks_text(), "answer_tks": _tks_text(), "extended_questions_tks": _tks_text(), "evidence_quotes_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "question_tks_tokens": {"type": "keyword"},
        "answer_type": {"type": "keyword"}, "generation_source": {"type": "keyword"}, "source_type": {"type": "keyword"},
        "source_chunk_ids": {"type": "long"}, "source_field_ids": {"type": "long"}, "evidence_quotes": _cn_text(),
        "evidence_quality": {"type": "keyword"}, "confidence": {"type": "float"}, "priority": {"type": "integer"}, "manual_override": {"type": "boolean"},
        "embedding_text": {"type": "text"}, "embedding_vector": vector_mapping, "index_generation": {"type": "keyword"},
        "audit_status": {"type": "keyword"}, "deleted": {"type": "boolean"},
    }, {
        "file_node_id": {"type": "long"}, "index_generation": {"type": "keyword"}, "audit_status": {"type": "keyword"},
        "deleted": {"type": "boolean"}, "answer_type": {"type": "keyword"}, "generation_source": {"type": "keyword"},
        "source_type": {"type": "keyword"}, "source_chunk_ids": {"type": "long"}, "source_field_ids": {"type": "long"},
        "evidence_quality": {"type": "keyword"}, "evidence_quotes": _cn_text(), "confidence": {"type": "float"}, "priority": {"type": "integer"},
        "manual_override": {"type": "boolean"},
        "product_names": {"type": "keyword"},
        "doc_name": _cn_text(), "doc_name_tks": _tks_text(), "question_tks": _tks_text(), "answer_tks": _tks_text(), "extended_questions_tks": _tks_text(), "evidence_quotes_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "question_tks_tokens": {"type": "keyword"},
    })

    _ensure_one(KNOWLEDGE_UNIT_INDEX, {
        "kb_id": {"type": "long"}, "file_node_id": {"type": "long"}, "profile": {"type": "keyword"},
        "unit_pk": {"type": "long"}, "unit_id": {"type": "keyword"}, "unit_type": {"type": "keyword"},
        "unit_subtype": {"type": "keyword"}, "anchor_id": {"type": "keyword"}, "source_section_id": {"type": "keyword"},
        "source_section_type": {"type": "keyword"}, "doc_name": _cn_text(), "subject_text": _cn_text(), "predicate_text": _cn_text(),
        "object_text": _cn_text(), "value_type": {"type": "keyword"}, "evidence_quote": _cn_text(),
        "doc_name_tks": _tks_text(), "subject_text_tks": _tks_text(), "predicate_text_tks": _tks_text(), "object_text_tks": _tks_text(),
        "evidence_quote_tks": _tks_text(), "section_path_text_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "subject_text_tks_tokens": {"type": "keyword"}, "object_text_tks_tokens": {"type": "keyword"},
        "section_path_text": _cn_text(), "primary_chunk_id": {"type": "long"}, "parse_generation": {"type": "keyword"},
        "index_generation": {"type": "keyword"}, "status": {"type": "keyword"}, "confidence": {"type": "float"},
        "embedding_text": {"type": "text"}, "embedding_model": {"type": "keyword"}, "embedding_vector": vector_mapping,
    }, {
        "profile": {"type": "keyword"}, "unit_type": {"type": "keyword"}, "unit_subtype": {"type": "keyword"},
        "anchor_id": {"type": "keyword"}, "source_section_id": {"type": "keyword"}, "source_section_type": {"type": "keyword"},
        "value_type": {"type": "keyword"}, "section_path_text": _cn_text(), "primary_chunk_id": {"type": "long"},
        "index_generation": {"type": "keyword"}, "status": {"type": "keyword"}, "confidence": {"type": "float"},
        "embedding_model": {"type": "keyword"},
        "doc_name": _cn_text(), "doc_name_tks": _tks_text(), "subject_text_tks": _tks_text(), "predicate_text_tks": _tks_text(), "object_text_tks": _tks_text(),
        "evidence_quote_tks": _tks_text(), "section_path_text_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "subject_text_tks_tokens": {"type": "keyword"}, "object_text_tks_tokens": {"type": "keyword"},
    })

    _ensure_one(SECTION_SUMMARY_INDEX, {
        "kb_id": {"type": "long"}, "file_node_id": {"type": "long"}, "profile": {"type": "keyword"},
        "summary_pk": {"type": "long"}, "section_id": {"type": "keyword"}, "section_type": {"type": "keyword"},
        "doc_name": _cn_text(), "section_title": _cn_text(), "section_path_text": _cn_text(), "section_level": {"type": "integer"},
        "product_names": {"type": "keyword"},
        "summary_type": {"type": "keyword"}, "node_summary": _cn_text(), "structured_summary_text": _cn_text(),
        "keywords": _cn_text(), "possible_questions": _cn_text(),
        "doc_name_tks": _tks_text(), "section_title_tks": _tks_text(), "section_path_text_tks": _tks_text(), "node_summary_tks": _tks_text(), "structured_summary_text_tks": _tks_text(),
        "keywords_tks": _tks_text(), "questions_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "section_title_tks_tokens": {"type": "keyword"}, "node_summary_tks_tokens": {"type": "keyword"},
        "covered_chunk_ids": {"type": "long"}, "summary_source": {"type": "keyword"}, "confidence": {"type": "float"},
        "parse_generation": {"type": "keyword"}, "index_generation": {"type": "keyword"},
        "embedding_text": {"type": "text"}, "embedding_model": {"type": "keyword"}, "embedding_vector": vector_mapping,
    }, {
        "profile": {"type": "keyword"}, "section_type": {"type": "keyword"}, "covered_chunk_ids": {"type": "long"},
        "index_generation": {"type": "keyword"}, "embedding_model": {"type": "keyword"},
        "product_names": {"type": "keyword"},
        "doc_name": _cn_text(), "doc_name_tks": _tks_text(), "section_title_tks": _tks_text(), "section_path_text_tks": _tks_text(), "node_summary_tks": _tks_text(), "structured_summary_text_tks": _tks_text(),
        "keywords": _cn_text(), "possible_questions": _cn_text(), "keywords_tks": _tks_text(), "questions_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "section_title_tks_tokens": {"type": "keyword"}, "node_summary_tks_tokens": {"type": "keyword"},
    })

    _ensure_one(ANCHOR_INDEX, {
        "kb_id": {"type": "long"}, "file_node_id": {"type": "long"}, "profile": {"type": "keyword"},
        "anchor_pk": {"type": "long"}, "anchor_id": {"type": "keyword"}, "anchor_type": {"type": "keyword"},
        "doc_name": _cn_text(), "anchor_name": _cn_text(), "normalized_name": {"type": "keyword"}, "aliases": _cn_text(),
        "doc_name_tks": _tks_text(), "anchor_name_tks": _tks_text(), "aliases_tks": _tks_text(), "section_path_text_tks": _tks_text(), "evidence_quote_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "anchor_name_tks_tokens": {"type": "keyword"},
        "source_section_id": {"type": "keyword"}, "source_section_type": {"type": "keyword"},
        "source_chunk_id": {"type": "long"}, "primary_chunk_id": {"type": "long"}, "section_path_text": _cn_text(),
        "evidence_quote": _cn_text(), "confidence": {"type": "float"}, "status": {"type": "keyword"},
        "parse_generation": {"type": "keyword"}, "index_generation": {"type": "keyword"},
        "embedding_text": {"type": "text"}, "embedding_model": {"type": "keyword"}, "embedding_vector": vector_mapping,
    }, {
        "profile": {"type": "keyword"}, "source_section_type": {"type": "keyword"}, "primary_chunk_id": {"type": "long"},
        "section_path_text": _cn_text(), "index_generation": {"type": "keyword"}, "embedding_model": {"type": "keyword"},
        "doc_name": _cn_text(), "doc_name_tks": _tks_text(), "anchor_name_tks": _tks_text(), "aliases_tks": _tks_text(), "section_path_text_tks": _tks_text(), "evidence_quote_tks": _tks_text(),
        "doc_name_tks_tokens": {"type": "keyword"}, "anchor_name_tks_tokens": {"type": "keyword"},
    })

def _file_filters(kb_id: int, file_node_id: int, index_generation: str | None = None) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = [{"term": {"kb_id": kb_id}}, {"term": {"file_node_id": file_node_id}}]
    if index_generation:
        filters.append({"term": {"index_generation": index_generation}})
    return filters


def delete_file_documents(es: Elasticsearch, kb_id: int, file_node_id: int, index_generation: str | None = None) -> None:
    query = {"query": {"bool": {"filter": _file_filters(kb_id, file_node_id, index_generation)}}}
    for index in [CHUNK_INDEX, FIELD_INDEX, SECTION_SUMMARY_INDEX, ANCHOR_INDEX, KNOWLEDGE_UNIT_INDEX]:
        if _index_exists_safe(es, index):
            es.delete_by_query(index=index, body=query, routing=str(kb_id), refresh=True, conflicts="proceed")


def delete_chunk_documents(es: Elasticsearch, kb_id: int, file_node_id: int, chunk_ids: list[int]) -> None:
    if not chunk_ids:
        return
    chunk_query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"kb_id": kb_id}},
                    {"term": {"file_node_id": file_node_id}},
                    {"terms": {"chunk_id": chunk_ids}},
                ]
            }
        }
    }
    field_query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"kb_id": kb_id}},
                    {"term": {"file_node_id": file_node_id}},
                    {"terms": {"source_chunk_id": chunk_ids}},
                ]
            }
        }
    }
    section_summary_query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"kb_id": kb_id}},
                    {"term": {"file_node_id": file_node_id}},
                    {"terms": {"covered_chunk_ids": chunk_ids}},
                ]
            }
        }
    }
    anchor_query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"kb_id": kb_id}},
                    {"term": {"file_node_id": file_node_id}},
                    {"terms": {"source_chunk_id": chunk_ids}},
                ]
            }
        }
    }
    unit_query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"kb_id": kb_id}},
                    {"term": {"file_node_id": file_node_id}},
                    {"terms": {"primary_chunk_id": chunk_ids}},
                ]
            }
        }
    }
    if _index_exists_safe(es, CHUNK_INDEX):
        es.delete_by_query(index=CHUNK_INDEX, body=chunk_query, routing=str(kb_id), refresh=True, conflicts="proceed")
    if _index_exists_safe(es, FIELD_INDEX):
        es.delete_by_query(index=FIELD_INDEX, body=field_query, routing=str(kb_id), refresh=True, conflicts="proceed")
    if _index_exists_safe(es, SECTION_SUMMARY_INDEX):
        es.delete_by_query(index=SECTION_SUMMARY_INDEX, body=section_summary_query, routing=str(kb_id), refresh=True, conflicts="proceed")
    if _index_exists_safe(es, ANCHOR_INDEX):
        es.delete_by_query(index=ANCHOR_INDEX, body=anchor_query, routing=str(kb_id), refresh=True, conflicts="proceed")
    if _index_exists_safe(es, KNOWLEDGE_UNIT_INDEX):
        es.delete_by_query(index=KNOWLEDGE_UNIT_INDEX, body=unit_query, routing=str(kb_id), refresh=True, conflicts="proceed")


def delete_kb_qa_documents(es: Elasticsearch, kb_id: int) -> None:
    query = {"query": {"bool": {"filter": [{"term": {"kb_id": kb_id}}]}}}
    if _index_exists_safe(es, QA_INDEX):
        es.delete_by_query(index=QA_INDEX, body=query, routing=str(kb_id), refresh=True, conflicts="proceed")


def delete_qa_documents(es: Elasticsearch, kb_id: int, qa_ids: list[int]) -> None:
    if not qa_ids or not _index_exists_safe(es, QA_INDEX):
        return
    query = {"query": {"bool": {"filter": [{"term": {"kb_id": kb_id}}, {"terms": {"qa_id": qa_ids}}]}}}
    es.delete_by_query(index=QA_INDEX, body=query, routing=str(kb_id), refresh=True, conflicts="proceed")


def _json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _json_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _chunk_section_path_text(row: dict[str, Any]) -> str:
    title_path = _json_array(row.get("title_path"))
    metadata = row.get("metadata_json")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    metadata = metadata if isinstance(metadata, dict) else {}
    section_path = metadata.get("section_path") or title_path
    if not isinstance(section_path, list):
        section_path = title_path
    return " > ".join(str(item) for item in section_path if item)


def _chunk_embedding_text(row: dict[str, Any]) -> str:
    return clean_join([_chunk_section_path_text(row), row.get("content_for_embedding") or row.get("content") or ""])


def _section_path_text(row: dict[str, Any]) -> str:
    section_path = _json_array(row.get("section_path"))
    if not section_path and row.get("section_path_text"):
        return str(row.get("section_path_text"))
    return " > ".join(str(item) for item in section_path if item)


def _section_summary_embedding_text(row: dict[str, Any]) -> str:
    structured = _json_object(row.get("structured_summary_json"))
    return clean_join(
        [
            _section_path_text(row),
            row.get("section_title"),
            row.get("section_type"),
            row.get("node_summary"),
            clean_join(structured.get("retrieval_keywords") or []),
            clean_join(structured.get("possible_questions") or []),
            _json_text(structured),
        ]
    )


def _anchor_embedding_text(row: dict[str, Any]) -> str:
    return clean_join(
        [
            row.get("anchor_type"),
            row.get("anchor_name"),
            row.get("normalized_name"),
            " ".join(str(item) for item in _json_array(row.get("aliases_json"))),
            row.get("section_path_text"),
            row.get("evidence_quote"),
        ]
    )


def _knowledge_unit_embedding_text(row: dict[str, Any]) -> str:
    return clean_join(
        [
            row.get("section_path_text"),
            row.get("unit_type"),
            row.get("unit_subtype"),
            row.get("subject_text"),
            row.get("predicate_text"),
            row.get("object_text"),
            row.get("evidence_quote"),
            _json_text(row.get("normalized_json")),
        ]
    )


def _index_chunk_rows(
    es: Elasticsearch,
    parse_generation: str,
    index_generation: str,
    chunk_rows: list[dict[str, Any]],
    vectors: list[list[float]],
    embedding_texts: list[str],
) -> int:
    actions: list[dict[str, Any]] = []
    for row, vector, embedding_text in zip(chunk_rows, vectors, embedding_texts):
        kb_id = row["kb_id"]
        section_path_text = _chunk_section_path_text(row)
        doc_name = row.get("doc_name") or ""
        metadata = row.get("metadata_json")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        keywords = metadata.get("keywords") if isinstance(metadata.get("keywords"), list) else []
        possible_questions = metadata.get("possible_questions") if isinstance(metadata.get("possible_questions"), list) else []
        keywords_text = clean_join(keywords)
        questions_text = clean_join(possible_questions)
        product_names = extract_product_names(unquote(doc_name), row.get("title"), metadata=metadata)
        document = {
                "kb_id": row["kb_id"],
                "file_node_id": row["file_node_id"],
                "profile": row.get("profile") or "guarantee_plan",
                "chunk_id": row["id"],
                "primary_chunk_id": row.get("primary_chunk_id") or row["id"],
                "parent_chunk_id": row.get("parent_chunk_id"),
                "revision_id": row["revision_id"],
                "parse_generation": parse_generation,
                "index_generation": index_generation,
                "chunk_group_id": row.get("chunk_group_id"),
                "content_hash": row.get("content_hash"),
                "chunk_type": row.get("chunk_type"),
                "section_type": row.get("section_type"),
                "section_id": row.get("section_id"),
                "retrieval_role": metadata.get("retrieval_role"),
                "context_level": metadata.get("context_level"),
                "source_chunk_type": metadata.get("source_chunk_type"),
                "doc_name": doc_name,
                "product_names": product_names,
                "doc_name_tks": tokenize_text(doc_name),
                "doc_name_tks_tokens": tokenize_list(doc_name),
                "section_path_text": section_path_text,
                "section_path_text_tks": tokenize_text(section_path_text),
                "enabled": bool(row.get("enabled", 1)),
                "audit_status": row.get("audit_status") or "approved",
                "deleted": bool(row.get("del_flag", 0)),
                "title": row.get("title"),
                "title_tks": tokenize_text(row.get("title")),
                "content": row.get("content"),
                "content_tks": tokenize_text(row.get("content")),
                "content_tks_tokens": tokenize_list(row.get("content")),
                "content_preview": (row.get("content") or "")[:500],
                "content_for_bm25": row.get("content_for_bm25") or clean_join([section_path_text, row.get("content")]),
                "content_for_bm25_tks": tokenize_text(row.get("content_for_bm25") or clean_join([section_path_text, row.get("content")])),
                "keywords": keywords_text,
                "keywords_tks": tokenize_text(keywords_text),
                "possible_questions": questions_text,
                "questions_tks": tokenize_text(questions_text),
                "embedding_text": embedding_text,
                "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", ""),
                "embedding_vector": vector,
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
            }
        actions.append(
            _index_action(
                CHUNK_INDEX,
                f'{row["kb_id"]}_{row["file_node_id"]}_{index_generation}_{row["id"]}',
                str(kb_id),
                document,
            )
        )
    return _bulk_index(es, actions)


def _index_field_rows(
    es: Elasticsearch,
    parse_generation: str,
    index_generation: str,
    field_rows: list[dict[str, Any]],
    vectors: list[list[float]],
    embedding_texts: list[str],
) -> int:
    actions: list[dict[str, Any]] = []
    for row, vector, embedding_text in zip(field_rows, vectors, embedding_texts):
        aliases = _json_array(row.get("aliases_json"))
        kb_id = row["kb_id"]
        doc_name = row.get("doc_name") or ""
        metadata = _json_object(row.get("metadata_json"))
        product_names = extract_product_names(
            unquote(doc_name),
            row.get("value_text") if row.get("field_code") in {"plan_name", "product_name"} else "",
            metadata=metadata,
        )
        document = {
                "kb_id": row["kb_id"],
                "file_node_id": row["file_node_id"],
                "profile": row.get("profile") or "guarantee_plan",
                "field_id": row["id"],
                "source_chunk_id": row.get("source_chunk_id"),
                "parse_generation": parse_generation,
                "index_generation": index_generation,
                "enabled": True,
                "audit_status": "approved",
                "deleted": bool(row.get("del_flag", 0)),
                "field_code": row.get("field_code"),
                "doc_name": doc_name,
                "product_names": product_names,
                "doc_name_tks": tokenize_text(doc_name),
                "doc_name_tks_tokens": tokenize_list(doc_name),
                "field_name_cn": row.get("field_name_cn"),
                "field_name_cn_tks": tokenize_text(row.get("field_name_cn")),
                "value_text": row.get("value_text"),
                "value_text_tks": tokenize_text(row.get("value_text")),
                "value_text_tks_tokens": tokenize_list(row.get("value_text")),
                "aliases": aliases,
                "aliases_tks": tokenize_text(" ".join(aliases) if isinstance(aliases, list) else str(aliases or "")),
                "embedding_text": embedding_text,
                "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", ""),
                "embedding_vector": vector,
            }
        actions.append(
            _index_action(
                FIELD_INDEX,
                f'{row["kb_id"]}_{row["file_node_id"]}_{index_generation}_{row["id"]}',
                str(kb_id),
                document,
            )
        )
    return _bulk_index(es, actions)


def _index_qa_rows(es: Elasticsearch, kb_id: int, index_generation: str, qa_rows: list[dict[str, Any]], vectors: list[list[float]], embedding_texts: list[str]) -> int:
    actions: list[dict[str, Any]] = []
    for row, vector, embedding_text in zip(qa_rows, vectors, embedding_texts):
        extended_questions = _json_array(row.get("extended_questions"))
        source_chunk_ids = _json_array(row.get("source_chunk_ids_json"))
        source_field_ids = _json_array(row.get("source_field_ids_json"))
        evidence_quotes = _json_array(row.get("evidence_quotes_json"))
        metadata = _json_object(row.get("metadata_json"))
        evidence_quality = str(metadata.get("evidence_quality") or row.get("evidence_quality") or "").strip() or (
            "exact_evidence" if evidence_quotes else "no_evidence"
        )
        kb_id = row["kb_id"]
        doc_name = row.get("doc_name") or ""
        product_names = extract_product_names(unquote(doc_name), row.get("question"), metadata=metadata)
        document = {
                "kb_id": row["kb_id"],
                "file_node_id": row.get("file_node_id"),
                "qa_id": row["id"],
                "doc_name": doc_name,
                "product_names": product_names,
                "doc_name_tks": tokenize_text(doc_name),
                "doc_name_tks_tokens": tokenize_list(doc_name),
                "question": row.get("question"),
                "question_tks": tokenize_text(row.get("question")),
                "question_tks_tokens": tokenize_list(row.get("question")),
                "answer": row.get("answer"),
                "answer_tks": tokenize_text(row.get("answer")),
                "extended_questions": extended_questions,
                "extended_questions_tks": tokenize_text(" ".join(extended_questions) if isinstance(extended_questions, list) else str(extended_questions or "")),
                "answer_type": row.get("answer_type") or "manual_qa",
                "generation_source": row.get("generation_source") or "manual_import",
                "source_type": row.get("source_type"),
                "source_chunk_ids": source_chunk_ids,
                "source_field_ids": source_field_ids,
                "evidence_quotes": evidence_quotes,
                "evidence_quotes_tks": tokenize_text(" ".join(evidence_quotes) if isinstance(evidence_quotes, list) else str(evidence_quotes or "")),
                "evidence_quality": evidence_quality,
                "confidence": _safe_confidence(row.get("confidence")),
                "priority": int(row.get("priority") or 0),
                "manual_override": bool(row.get("manual_override")),
                "embedding_text": embedding_text,
                "embedding_vector": vector,
                "index_generation": index_generation,
                "audit_status": row.get("audit_status") or "approved",
                "deleted": bool(row.get("del_flag", 0)),
            }
        actions.append(
            _index_action(
                QA_INDEX,
                f'{row["kb_id"]}_{row["id"]}',
                str(kb_id),
                document,
            )
        )
    return _bulk_index(es, actions)


def _index_section_summary_rows(
    es: Elasticsearch,
    parse_generation: str,
    index_generation: str,
    summary_rows: list[dict[str, Any]],
    vectors: list[list[float]],
    embedding_texts: list[str],
) -> int:
    actions: list[dict[str, Any]] = []
    for row, vector, embedding_text in zip(summary_rows, vectors, embedding_texts):
        kb_id = row["kb_id"]
        section_path_text = _section_path_text(row)
        doc_name = row.get("doc_name") or ""
        structured_summary = _json_object(row.get("structured_summary_json"))
        keywords = structured_summary.get("retrieval_keywords") if isinstance(structured_summary.get("retrieval_keywords"), list) else []
        possible_questions = structured_summary.get("possible_questions") if isinstance(structured_summary.get("possible_questions"), list) else []
        keywords_text = clean_join(keywords)
        questions_text = clean_join(possible_questions)
        product_names = extract_product_names(unquote(doc_name), row.get("section_title"), section_path_text, metadata=structured_summary)
        document = {
                "kb_id": row["kb_id"],
                "file_node_id": row["file_node_id"],
                "profile": row.get("profile") or "general_document",
                "summary_pk": row["id"],
                "section_id": row.get("section_id"),
                "section_type": row.get("section_type"),
                "doc_name": doc_name,
                "product_names": product_names,
                "doc_name_tks": tokenize_text(doc_name),
                "doc_name_tks_tokens": tokenize_list(doc_name),
                "section_title": row.get("section_title"),
                "section_title_tks": tokenize_text(row.get("section_title")),
                "section_title_tks_tokens": tokenize_list(row.get("section_title")),
                "section_path_text": section_path_text,
                "section_path_text_tks": tokenize_text(section_path_text),
                "section_level": row.get("section_level"),
                "summary_type": row.get("summary_type") or "node_summary",
                "node_summary": row.get("node_summary"),
                "node_summary_tks": tokenize_text(row.get("node_summary")),
                "node_summary_tks_tokens": tokenize_list(row.get("node_summary")),
                "structured_summary_text": _json_text(row.get("structured_summary_json")),
                "structured_summary_text_tks": tokenize_text(_json_text(row.get("structured_summary_json"))),
                "keywords": keywords_text,
                "keywords_tks": tokenize_text(keywords_text),
                "possible_questions": questions_text,
                "questions_tks": tokenize_text(questions_text),
                "covered_chunk_ids": _json_array(row.get("covered_chunk_ids_json")),
                "summary_source": row.get("summary_source"),
                "confidence": _safe_confidence(row.get("confidence")),
                "parse_generation": parse_generation,
                "index_generation": index_generation,
                "embedding_text": embedding_text,
                "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", ""),
                "embedding_vector": vector,
            }
        actions.append(
            _index_action(
                SECTION_SUMMARY_INDEX,
                f'{row["kb_id"]}_{row["file_node_id"]}_{index_generation}_{row["id"]}',
                str(kb_id),
                document,
            )
        )
    return _bulk_index(es, actions)


def _index_anchor_rows(
    es: Elasticsearch,
    parse_generation: str,
    index_generation: str,
    anchor_rows: list[dict[str, Any]],
    vectors: list[list[float]],
    embedding_texts: list[str],
) -> int:
    actions: list[dict[str, Any]] = []
    for row, vector, embedding_text in zip(anchor_rows, vectors, embedding_texts):
        kb_id = row["kb_id"]
        doc_name = row.get("doc_name") or ""
        document = {
                "kb_id": row["kb_id"],
                "file_node_id": row["file_node_id"],
                "profile": row.get("profile") or "general_document",
                "anchor_pk": row["id"],
                "anchor_id": row.get("anchor_id"),
                "anchor_type": row.get("anchor_type"),
                "doc_name": doc_name,
                "doc_name_tks": tokenize_text(doc_name),
                "doc_name_tks_tokens": tokenize_list(doc_name),
                "anchor_name": row.get("anchor_name"),
                "anchor_name_tks": tokenize_text(row.get("anchor_name")),
                "anchor_name_tks_tokens": tokenize_list(row.get("anchor_name")),
                "normalized_name": row.get("normalized_name"),
                "aliases": _json_array(row.get("aliases_json")),
                "aliases_tks": tokenize_text(" ".join(_json_array(row.get("aliases_json")))),
                "source_section_id": row.get("source_section_id"),
                "source_section_type": row.get("source_section_type"),
                "source_chunk_id": row.get("source_chunk_id"),
                "primary_chunk_id": row.get("primary_chunk_id") or row.get("source_chunk_id"),
                "section_path_text": row.get("section_path_text"),
                "section_path_text_tks": tokenize_text(row.get("section_path_text")),
                "evidence_quote": row.get("evidence_quote"),
                "evidence_quote_tks": tokenize_text(row.get("evidence_quote")),
                "confidence": _safe_confidence(row.get("confidence")),
                "status": row.get("status") or "active",
                "parse_generation": parse_generation,
                "index_generation": index_generation,
                "embedding_text": embedding_text,
                "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", ""),
                "embedding_vector": vector,
            }
        actions.append(
            _index_action(
                ANCHOR_INDEX,
                f'{row["kb_id"]}_{row["file_node_id"]}_{index_generation}_{row["id"]}',
                str(kb_id),
                document,
            )
        )
    return _bulk_index(es, actions)


def _index_knowledge_unit_rows(
    es: Elasticsearch,
    parse_generation: str,
    index_generation: str,
    unit_rows: list[dict[str, Any]],
    vectors: list[list[float]],
    embedding_texts: list[str],
) -> int:
    actions: list[dict[str, Any]] = []
    for row, vector, embedding_text in zip(unit_rows, vectors, embedding_texts):
        kb_id = row["kb_id"]
        doc_name = row.get("doc_name") or ""
        document = {
                "kb_id": row["kb_id"],
                "file_node_id": row["file_node_id"],
                "profile": row.get("profile") or "general_document",
                "unit_pk": row["id"],
                "unit_id": row.get("unit_id"),
                "unit_type": row.get("unit_type"),
                "unit_subtype": row.get("unit_subtype"),
                "anchor_id": row.get("anchor_id"),
                "source_section_id": row.get("source_section_id"),
                "source_section_type": row.get("source_section_type"),
                "doc_name": doc_name,
                "doc_name_tks": tokenize_text(doc_name),
                "doc_name_tks_tokens": tokenize_list(doc_name),
                "subject_text": row.get("subject_text"),
                "subject_text_tks": tokenize_text(row.get("subject_text")),
                "subject_text_tks_tokens": tokenize_list(row.get("subject_text")),
                "predicate_text": row.get("predicate_text"),
                "predicate_text_tks": tokenize_text(row.get("predicate_text")),
                "object_text": row.get("object_text"),
                "object_text_tks": tokenize_text(row.get("object_text")),
                "object_text_tks_tokens": tokenize_list(row.get("object_text")),
                "value_type": row.get("value_type"),
                "evidence_quote": row.get("evidence_quote"),
                "evidence_quote_tks": tokenize_text(row.get("evidence_quote")),
                "section_path_text": row.get("section_path_text"),
                "section_path_text_tks": tokenize_text(row.get("section_path_text")),
                "primary_chunk_id": row.get("primary_chunk_id"),
                "parse_generation": parse_generation,
                "index_generation": index_generation,
                "status": row.get("status") or "active",
                "confidence": _safe_confidence(row.get("confidence")),
                "embedding_text": embedding_text,
                "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", ""),
                "embedding_vector": vector,
            }
        actions.append(
            _index_action(
                KNOWLEDGE_UNIT_INDEX,
                f'{row["kb_id"]}_{row["file_node_id"]}_{index_generation}_{row["id"]}',
                str(kb_id),
                document,
            )
        )
    return _bulk_index(es, actions)


def index_rows(
    es: Elasticsearch,
    parse_generation: str,
    index_generation: str,
    chunk_rows: list[dict[str, Any]] | None = None,
    field_rows: list[dict[str, Any]] | None = None,
    qa_rows: list[dict[str, Any]] | None = None,
    section_summary_rows: list[dict[str, Any]] | None = None,
    anchor_rows: list[dict[str, Any]] | None = None,
    knowledge_unit_rows: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    embedding_client = EmbeddingClient()
    chunk_rows = chunk_rows or []
    field_rows = field_rows or []
    qa_rows = qa_rows or []
    section_summary_rows = section_summary_rows or []
    anchor_rows = anchor_rows or []
    knowledge_unit_rows = knowledge_unit_rows or []

    # Skip rows for indices that don't exist (e.g. section_summary_v1 may be missing due to permissions)
    if section_summary_rows and not _index_exists_safe(es, SECTION_SUMMARY_INDEX):
        _logger.warning("index_rows: skipping %d section_summaries, index '%s' does not exist", len(section_summary_rows), SECTION_SUMMARY_INDEX)
        section_summary_rows = []
    if anchor_rows and not _index_exists_safe(es, ANCHOR_INDEX):
        _logger.warning("index_rows: skipping %d anchors, index '%s' does not exist", len(anchor_rows), ANCHOR_INDEX)
        anchor_rows = []
    if knowledge_unit_rows and not _index_exists_safe(es, KNOWLEDGE_UNIT_INDEX):
        _logger.warning("index_rows: skipping %d knowledge_units, index '%s' does not exist", len(knowledge_unit_rows), KNOWLEDGE_UNIT_INDEX)
        knowledge_unit_rows = []

    chunk_texts = [_chunk_embedding_text(row) for row in chunk_rows]
    field_texts = [f'{row.get("field_name_cn") or ""} {row.get("value_text") or ""}' for row in field_rows]
    qa_texts = [
        " ".join(
            item
            for item in [
                row.get("question") or "",
                row.get("answer") or "",
                " ".join(_json_array(row.get("extended_questions"))),
                " ".join(_json_array(row.get("evidence_quotes_json"))),
            ]
            if item
        )
        for row in qa_rows
    ]
    section_summary_texts = [_section_summary_embedding_text(row) for row in section_summary_rows]
    anchor_texts = [_anchor_embedding_text(row) for row in anchor_rows]
    knowledge_unit_texts = [_knowledge_unit_embedding_text(row) for row in knowledge_unit_rows]

    chunk_vectors = embedding_client.embed_texts(chunk_texts) if chunk_texts else []
    field_vectors = embedding_client.embed_texts(field_texts) if field_texts else []
    qa_vectors = embedding_client.embed_texts(qa_texts) if qa_texts else []
    section_summary_vectors = embedding_client.embed_texts(section_summary_texts) if section_summary_texts else []
    anchor_vectors = embedding_client.embed_texts(anchor_texts) if anchor_texts else []
    knowledge_unit_vectors = embedding_client.embed_texts(knowledge_unit_texts) if knowledge_unit_texts else []

    chunk_count = _index_chunk_rows(es, parse_generation, index_generation, chunk_rows, chunk_vectors, chunk_texts)
    field_count = _index_field_rows(es, parse_generation, index_generation, field_rows, field_vectors, field_texts)
    qa_count = _index_qa_rows(es, chunk_rows[0]["kb_id"] if chunk_rows else (field_rows[0]["kb_id"] if field_rows else 0), index_generation, qa_rows, qa_vectors, qa_texts)
    section_summary_count = _index_section_summary_rows(es, parse_generation, index_generation, section_summary_rows, section_summary_vectors, section_summary_texts)
    anchor_count = _index_anchor_rows(es, parse_generation, index_generation, anchor_rows, anchor_vectors, anchor_texts)
    knowledge_unit_count = _index_knowledge_unit_rows(es, parse_generation, index_generation, knowledge_unit_rows, knowledge_unit_vectors, knowledge_unit_texts)
    touched_indices = [
        name
        for name, rows in [
            (CHUNK_INDEX, chunk_rows),
            (FIELD_INDEX, field_rows),
            (QA_INDEX, qa_rows),
            (SECTION_SUMMARY_INDEX, section_summary_rows),
            (ANCHOR_INDEX, anchor_rows),
            (KNOWLEDGE_UNIT_INDEX, knowledge_unit_rows),
        ]
        if rows
    ]
    if touched_indices:
        es.indices.refresh(index=touched_indices, request_timeout=int(os.getenv("ES_BULK_REQUEST_TIMEOUT", "3600")))
    return {
        "chunk_count": chunk_count,
        "field_count": field_count,
        "qa_count": qa_count,
        "section_summary_count": section_summary_count,
        "anchor_count": anchor_count,
        "knowledge_unit_count": knowledge_unit_count,
    }


def index_snapshot(es: Elasticsearch, snapshot: dict[str, Any], index_generation: str) -> dict[str, int]:
    # NOTE: Do NOT delete KB-wide QA documents here. QA index lifecycle is
    # independent of file-level index rebuilds. QA cleanup should only be
    # triggered through the /api/v1/index/qas endpoint.
    return index_rows(
        es,
        parse_generation=snapshot["parse_generation"],
        index_generation=index_generation,
        chunk_rows=snapshot["chunks"],
        field_rows=snapshot["fields"],
        qa_rows=snapshot["qa_rows"],
        section_summary_rows=snapshot.get("section_summaries") or [],
        anchor_rows=snapshot.get("anchors") or [],
        knowledge_unit_rows=snapshot.get("knowledge_units") or [],
    )


def _active_filters(
    kb_id: int,
    file_node_ids: list[int] | None,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = [
        {"term": {"kb_id": kb_id}},
        {"term": {"enabled": True}},
        {"term": {"audit_status": "approved"}},
        {"term": {"deleted": False}},
    ]
    if file_node_ids:
        filters.append({"terms": {"file_node_id": file_node_ids}})
    if index_generations:
        filters.append({"terms": {"index_generation": index_generations}})
    # NOTE: profile 不作为检索硬性过滤。跨 profile 的文档应一起召回，
    # profile 只用于内部字段权重选择（见 search_bm25 的 _profile_in 等）。
    return filters


def _structural_filters(
    kb_id: int,
    file_node_ids: list[int] | None,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = [{"term": {"kb_id": kb_id}}]
    if file_node_ids:
        filters.append({"terms": {"file_node_id": file_node_ids}})
    if index_generations:
        filters.append({"terms": {"index_generation": index_generations}})
    # NOTE: profile 不作为检索硬性过滤，见 _active_filters 注释。
    if active_only:
        filters.append({"term": {"status": "active"}})
    return filters


def _chunk_filters(
    base_filters: list[dict[str, Any]],
    chunk_types: list[str] | None = None,
    section_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters = list(base_filters)
    if chunk_types:
        filters.append({"terms": {"chunk_type": chunk_types}})
    if section_types:
        filters.append({"terms": {"section_type": section_types}})
    return filters


def _kb_id_from_filters(filters: list[dict[str, Any]]) -> int:
    for item in filters:
        term = item.get("term") if isinstance(item, dict) else None
        if isinstance(term, dict) and "kb_id" in term:
            return int(term["kb_id"])
    return 0


def _term_weight_scope(
    es: Elasticsearch,
    *,
    index: str,
    token_field: str,
    kb_id: int,
    index_generations: list[str] | None,
    profiles: list[str] | None,
    term_weight_options: dict[str, Any] | None,
) -> str | None:
    options = term_weight_options or {}
    enabled = str(options.get("enabled", "true")).lower() not in {"false", "0", "no", "off"}
    if not enabled:
        return None
    scope = str(options.get("scope") or "kb_profile_generation").lower()
    if scope in {"global", "none"}:
        return None
    if not hasattr(es, "count"):
        return None
    refresh = str(options.get("refresh", "false")).lower() in {"true", "1", "yes", "on"}
    max_terms = int(options.get("max_terms") or 50000)
    scoped_profiles = profiles if scope in {"profile", "kb_profile", "kb_profile_generation"} else None
    scoped_generations = index_generations if scope in {"generation", "kb_generation", "kb_profile_generation"} else None
    scoped_kb_id = kb_id if scope.startswith("kb") or scope in {"kb_profile", "kb_generation", "kb_profile_generation"} else None
    return get_term_weighter().ensure_scope_from_es(
        es,
        index=index,
        token_field=token_field,
        kb_id=scoped_kb_id,
        index_generations=scoped_generations,
        profiles=scoped_profiles,
        max_terms=max_terms,
        refresh=refresh,
    )


def search_bm25(
    es: Elasticsearch,
    kb_id: int,
    query: str,
    file_node_ids: list[int] | None,
    top_k: int,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
    chunk_types: list[str] | None = None,
    section_types: list[str] | None = None,
    term_weight_options: dict[str, Any] | None = None,
    expanded_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters = _active_filters(kb_id, file_node_ids, index_generations, profiles)
    tks_query = tokenize_text(query) or query
    tw = get_term_weighter()
    results: list[dict[str, Any]] = []
    governance = _profile_in(profiles, "governance_rule")
    field_fields = (
        ["field_name_cn_tks^4", "product_names^4", "value_text_tks^3", "aliases_tks^3", "doc_name_tks^2"]
        if governance
        else ["doc_name_tks^5", "product_names^4", "field_name_cn_tks^3", "value_text_tks^2", "aliases_tks"]
    )
    field_scope = _term_weight_scope(
        es,
        index=FIELD_INDEX,
        token_field="value_text_tks_tokens",
        kb_id=kb_id,
        index_generations=index_generations,
        profiles=profiles,
        term_weight_options=term_weight_options,
    )
    field_query = _expanded_text_query(tw, query, field_fields, scope_key=field_scope, expanded_terms=expanded_terms)
    field_resp = es.search(
        index=FIELD_INDEX,
        routing=str(kb_id),
        size=top_k,
        query={"bool": {"filter": filters, "must": [field_query]}},
    )
    field_results = []
    for hit in field_resp["hits"]["hits"]:
        source = hit["_source"]
        source["hit_type"] = "bm25"
        source["score"] = hit["_score"]
        source["title"] = source.get("field_name_cn")
        source["content"] = source.get("value_text")
        source["term_weight_scope"] = field_scope
        source["_bm25_sub"] = "field"
        field_results.append(source)

    chunk_fields = (
        ["section_path_text_tks^6", "product_names^3", "title_tks^4", "doc_name_tks^3", "keywords_tks^3", "questions_tks^2.5", "content_for_bm25_tks^2", "content_tks"]
        if governance
        else ["doc_name_tks^5", "product_names^3", "section_path_text_tks^3", "keywords_tks^3", "questions_tks^2.5", "title_tks^2", "content_for_bm25_tks^2", "content_tks"]
    )
    chunk_scope = _term_weight_scope(
        es,
        index=CHUNK_INDEX,
        token_field="content_tks_tokens",
        kb_id=kb_id,
        index_generations=index_generations,
        profiles=profiles,
        term_weight_options=term_weight_options,
    )
    chunk_query = _expanded_text_query(tw, query, chunk_fields, scope_key=chunk_scope, expanded_terms=expanded_terms)
    chunk_resp = es.search(
        index=CHUNK_INDEX,
        routing=str(kb_id),
        size=top_k,
        query={"bool": {"filter": _chunk_filters(filters, chunk_types, section_types), "must": [chunk_query]}},
    )
    chunk_results = []
    for hit in chunk_resp["hits"]["hits"]:
        source = hit["_source"]
        source["hit_type"] = "bm25"
        source["score"] = hit["_score"]
        source["evidence_text"] = source.get("content")
        source["term_weight_scope"] = chunk_scope
        source["_bm25_sub"] = "chunk"
        chunk_results.append(source)

    # Normalize scores within each sub-index before merging
    for group in (field_results, chunk_results):
        _normalize_search_scores(group)
        for r in group:
            r.pop("_bm25_sub", None)
    results = field_results + chunk_results
    results.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    return results[:top_k]


def _first_long(value: Any) -> int | None:
    if isinstance(value, list):
        for item in value:
            parsed = _first_long(item)
            if parsed is not None:
                return parsed
        return None
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def search_structured(
    es: Elasticsearch,
    kb_id: int,
    query: str,
    file_node_ids: list[int] | None,
    top_k: int,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
    *,
    include_units: bool = True,
    include_anchors: bool = True,
    term_weight_options: dict[str, Any] | None = None,
    expanded_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters = _structural_filters(kb_id, file_node_ids, index_generations, profiles, active_only=True)
    tks_query = tokenize_text(query) or query
    tw = get_term_weighter()
    results: list[dict[str, Any]] = []
    if include_units:
        unit_fields = [
            "doc_name_tks^3",
            "section_path_text_tks^2",
            "subject_text_tks^3",
            "predicate_text_tks^3",
            "object_text_tks^4",
            "evidence_quote_tks^3",
            "unit_type",
            "unit_subtype",
        ]
        unit_scope = _term_weight_scope(
            es,
            index=KNOWLEDGE_UNIT_INDEX,
            token_field="object_text_tks_tokens",
            kb_id=kb_id,
            index_generations=index_generations,
            profiles=profiles,
            term_weight_options=term_weight_options,
        )
        unit_query = _expanded_text_query(tw, query, unit_fields, scope_key=unit_scope, expanded_terms=expanded_terms)
        unit_resp = es.search(
            index=KNOWLEDGE_UNIT_INDEX,
            routing=str(kb_id),
            size=top_k,
            query={
                "bool": {
                    "filter": filters,
                    "must": [unit_query],
                }
            },
        )
        for hit in unit_resp["hits"]["hits"]:
            source = hit["_source"]
            primary_chunk_id = _first_long(source.get("primary_chunk_id"))
            source["hit_type"] = "knowledge_unit"
            source["score"] = hit["_score"]
            source["chunk_id"] = primary_chunk_id
            source["primary_chunk_id"] = primary_chunk_id
            source["title"] = source.get("predicate_text") or source.get("unit_subtype") or source.get("unit_type")
            source["content"] = source.get("object_text") or source.get("evidence_quote")
            source["value_text"] = source.get("object_text")
            source["evidence_text"] = source.get("evidence_quote") or source.get("object_text")
            source["match_type"] = "knowledge_unit"
            source["term_weight_scope"] = unit_scope
            results.append(source)
    if include_anchors:
        anchor_fields = [
            "doc_name_tks^3",
            "anchor_name_tks^4",
            "normalized_name^3",
            "aliases_tks^3",
            "anchor_type^2",
            "section_path_text_tks^2",
            "evidence_quote_tks^3",
        ]
        anchor_scope = _term_weight_scope(
            es,
            index=ANCHOR_INDEX,
            token_field="anchor_name_tks_tokens",
            kb_id=kb_id,
            index_generations=index_generations,
            profiles=profiles,
            term_weight_options=term_weight_options,
        )
        anchor_query = _expanded_text_query(tw, query, anchor_fields, scope_key=anchor_scope, expanded_terms=expanded_terms)
        anchor_resp = es.search(
            index=ANCHOR_INDEX,
            routing=str(kb_id),
            size=top_k,
            query={
                "bool": {
                    "filter": filters,
                    "must": [anchor_query],
                }
            },
        )
        for hit in anchor_resp["hits"]["hits"]:
            source = hit["_source"]
            primary_chunk_id = _first_long(source.get("primary_chunk_id") or source.get("source_chunk_id"))
            source["hit_type"] = "anchor"
            source["score"] = hit["_score"]
            source["chunk_id"] = primary_chunk_id
            source["primary_chunk_id"] = primary_chunk_id
            source["title"] = source.get("anchor_name") or source.get("normalized_name")
            source["content"] = source.get("evidence_quote") or source.get("anchor_name")
            source["evidence_text"] = source.get("evidence_quote")
            source["match_type"] = "anchor"
            source["term_weight_scope"] = anchor_scope
            results.append(source)
    # Normalize scores within each sub-type before merging
    unit_results = [r for r in results if r.get("hit_type") == "knowledge_unit"]
    anchor_results = [r for r in results if r.get("hit_type") == "anchor"]
    for group in (unit_results, anchor_results):
        _normalize_search_scores(group)
    results.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    return results[:top_k]


def search_section_summary(
    es: Elasticsearch,
    kb_id: int,
    query: str,
    file_node_ids: list[int] | None,
    top_k: int,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
    term_weight_options: dict[str, Any] | None = None,
    expanded_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters = _structural_filters(kb_id, file_node_ids, index_generations, profiles)
    tks_query = tokenize_text(query) or query
    tw = get_term_weighter()
    ss_fields = (
        [
            "section_path_text_tks^6",
            "product_names^3",
            "section_title_tks^5",
            "node_summary_tks^3",
            "keywords_tks^3",
            "questions_tks^2.5",
            "doc_name_tks^2",
            "structured_summary_text_tks^2",
            "section_type",
        ]
        if _profile_in(profiles, "governance_rule")
        else [
            "doc_name_tks^4",
            "product_names^3",
            "section_title_tks^4",
            "section_path_text_tks^3",
            "keywords_tks^3",
            "questions_tks^2.5",
            "node_summary_tks^3",
            "structured_summary_text_tks^2",
            "section_type",
        ]
    )
    ss_scope = _term_weight_scope(
        es,
        index=SECTION_SUMMARY_INDEX,
        token_field="node_summary_tks_tokens",
        kb_id=kb_id,
        index_generations=index_generations,
        profiles=profiles,
        term_weight_options=term_weight_options,
    )
    ss_query = _expanded_text_query(tw, query, ss_fields, scope_key=ss_scope, expanded_terms=expanded_terms)
    resp = es.search(
        index=SECTION_SUMMARY_INDEX,
        routing=str(kb_id),
        size=top_k,
        query={
            "bool": {
                "filter": filters,
                "must": [ss_query],
            }
        },
    )
    results: list[dict[str, Any]] = []
    for hit in resp["hits"]["hits"]:
        source = hit["_source"]
        covered_chunk_ids = source.get("covered_chunk_ids") or []
        if not isinstance(covered_chunk_ids, list):
            covered_chunk_ids = [covered_chunk_ids]
        primary_chunk_id = _first_long(covered_chunk_ids)
        source["hit_type"] = "section_summary"
        source["score"] = hit["_score"]
        source["chunk_id"] = primary_chunk_id
        source["primary_chunk_id"] = primary_chunk_id
        source["title"] = source.get("section_title")
        source["content"] = source.get("node_summary") or source.get("structured_summary_text")
        source["evidence_text"] = source.get("node_summary")
        source["match_type"] = "section_summary"
        source["covered_chunk_ids"] = [_first_long(item) for item in covered_chunk_ids if _first_long(item) is not None]
        source["term_weight_scope"] = ss_scope
        results.append(source)
    return results


def _search_vector_index(
    es: Elasticsearch,
    index: str,
    filters: list[dict[str, Any]],
    vector: list[float],
    top_k: int,
) -> dict[str, Any]:
    routing = str(_kb_id_from_filters(filters))
    is_css = _is_css()

    if is_css:
        css_indexing = _css_vector_indexing()
        if css_indexing:
            # CSS native vector query (requires indexing=true)
            body = {
                "size": top_k,
                "query": {
                    "bool": {
                        "filter": filters,
                        "must": [
                            {
                                "vector": {
                                    "embedding_vector": {
                                        "vector": vector,
                                        "topk": top_k,
                                    }
                                }
                            }
                        ],
                    }
                },
            }
        else:
            # CSS ScriptScore query (indexing=false, brute force)
            bool_query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
            body = {
                "size": top_k,
                "query": {
                    "script_score": {
                        "query": bool_query,
                        "script": {
                            "source": "vector_score",
                            "lang": "vector",
                            "params": {
                                "field": "embedding_vector",
                                "vector": vector,
                                "metric": "cosine",
                            },
                        },
                    }
                },
            }
        return es.search(index=index, routing=routing, body=body)

    # Standard ES: try knn first, fallback to script_score
    knn = {
        "field": "embedding_vector",
        "query_vector": vector,
        "k": top_k,
        "num_candidates": max(top_k * 4, 20),
        "filter": filters,
    }
    try:
        return es.search(index=index, routing=routing, body={"size": top_k, "knn": knn})
    except Exception:
        return es.search(
            index=index,
            routing=routing,
            body={
                "size": top_k,
                "query": {
                    "script_score": {
                        "query": {"bool": {"filter": filters}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding_vector') + 1.0",
                            "params": {"query_vector": vector},
                        },
                    }
                },
            },
        )


def search_vector(
    es: Elasticsearch,
    kb_id: int,
    query: str,
    file_node_ids: list[int] | None,
    top_k: int,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
    chunk_types: list[str] | None = None,
    section_types: list[str] | None = None,
    embedding_cache_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    vector = EmbeddingClient().embed_texts([query], cache_context=embedding_cache_context)[0]
    filters = _active_filters(kb_id, file_node_ids, index_generations, profiles)
    results: list[dict[str, Any]] = []
    chunk_resp = _search_vector_index(es, CHUNK_INDEX, _chunk_filters(filters, chunk_types, section_types), vector, top_k)
    for hit in chunk_resp["hits"]["hits"]:
        source = hit["_source"]
        source["hit_type"] = "vector"
        source["score"] = hit["_score"]
        source["evidence_text"] = source.get("content")
        results.append(source)

    field_resp = _search_vector_index(es, FIELD_INDEX, filters, vector, top_k)
    for hit in field_resp["hits"]["hits"]:
        source = hit["_source"]
        source["hit_type"] = "vector"
        source["score"] = hit["_score"]
        source["title"] = source.get("field_name_cn")
        source["content"] = source.get("value_text")
        results.append(source)
    return results


def search_qa(
    es: Elasticsearch,
    kb_id: int,
    query: str,
    top_k: int,
    file_node_ids: list[int] | None = None,
    index_generations: list[str] | None = None,
    profiles: list[str] | None = None,
    term_weight_options: dict[str, Any] | None = None,
    expanded_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    tks_query = tokenize_text(query) or query
    filters: list[dict[str, Any]] = [
        {"term": {"kb_id": kb_id}},
        {"term": {"audit_status": "approved"}},
        {"term": {"deleted": False}},
    ]
    if file_node_ids:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"terms": {"file_node_id": file_node_ids}},
                        {"bool": {"must_not": {"exists": {"field": "file_node_id"}}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if index_generations:
        filters.append({"terms": {"index_generation": index_generations}})
    tw = get_term_weighter()
    qa_fields = ["doc_name_tks^4", "product_names^3", "question_tks^3", "extended_questions_tks^2", "evidence_quotes_tks^2", "answer_tks"]
    qa_scope = _term_weight_scope(
        es,
        index=QA_INDEX,
        token_field="question_tks_tokens",
        kb_id=kb_id,
        index_generations=index_generations,
        profiles=None,
        term_weight_options=term_weight_options,
    )
    qa_query = _expanded_text_query(tw, query, qa_fields, scope_key=qa_scope, expanded_terms=expanded_terms)
    resp = es.search(
        index=QA_INDEX,
        routing=str(kb_id),
        size=top_k,
        query={
            "bool": {
                "filter": filters,
                "must": [qa_query],
                "should": [
                    {"term": {"evidence_quality": {"value": "exact_evidence", "boost": 1.8}}},
                    {"term": {"evidence_quality": {"value": "fuzzy_evidence", "boost": 1.2}}},
                    {"range": {"confidence": {"gte": 0.85, "boost": 1.2}}},
                    {"range": {"priority": {"gte": 10, "boost": 1.1}}},
                ],
            }
        },
    )
    for hit in resp["hits"]["hits"]:
        source = hit["_source"]
        source["hit_type"] = "qa"
        source["score"] = hit["_score"]
        source["title"] = source.get("question")
        source["content"] = source.get("answer")
        source["term_weight_scope"] = qa_scope
        results.append(source)
    return results
