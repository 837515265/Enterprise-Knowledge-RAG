from __future__ import annotations

import logging
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from danbao_poc.answer_context_protocol import build_answer_context_protocol
from danbao_poc.common import clean_text
from danbao_poc.citation_formatter import build_citations
from danbao_poc.error_codes import INDEX_FAILED, INDEX_INVALID_OPERATION, INDEX_LOCKED, INDEX_TASK_NOT_FOUND, RATE_LIMITED, RETRIEVE_FAILED, REVIEW_FAILED, TABLE_RETRIEVE_FAILED
from danbao_poc.es_store import (
    client as es_client,
    delete_chunk_documents,
    delete_file_documents,
    delete_qa_documents,
    ensure_indices,
    index_rows,
    index_snapshot,
    search_bm25,
    search_qa,
    search_section_summary,
    search_structured,
    search_vector,
)
from danbao_poc.graph_writer import apply_constraints, audit_kb_graph, delete_file_graph, import_business_graph, import_knowledge_graph, load_file_graph, load_kb_graph, rebuild_kb_communities, search_community_reports, sync_file_graph_delta, update_business_field
from danbao_poc.health_checks import readiness
from danbao_poc.index_incremental import plan_incremental_index
from danbao_poc.index_task_store import create_index_task, delete_index_task, enqueue_index_task, get_index_task, new_index_task_id, retry_index_task, take_next_index_task, update_index_task
from danbao_poc.mysql_store import (
    filter_snapshot_by_chunk_ids,
    get_index_status,
    init_db,
    load_active_index_scope,
    load_char_map,
    load_chunk_snapshot,
    load_chunks_by_ids,
    load_field_snapshot,
    load_index_snapshot,
    load_qa_snapshot,
    load_related_chunks,
    load_retrieval_profile_config,
    load_review_extractions,
    load_section_summaries_by_chunk_ids,
    connect as mysql_connect,
    review_file,
    mark_chunk_index_state,
    mark_file_index_deleted,
    mark_index_finished,
    mark_index_started,
    mark_qa_index_state,
    next_index_generation,
    release_index_lock,
    review_chunk,
    load_section_tree,
    save_qa_pairs,
    search_file_tables,
    try_acquire_index_lock,
    upsert_index_state,
    update_field_value,
)
from danbao_poc.metrics import inc, observe, render_prometheus, timer
from danbao_poc.nacos_client import NacosServiceRegistrar, register_current_service
from danbao_poc.profiles.registry import normalize_profile, profile_filter_values
from danbao_poc.product_name_extractor import expand_product_aliases, extract_product_names
from danbao_poc.query import (
    build_evidence_groups,
    cached_understand_query,
    filter_by_similarity_threshold,
    graph_context_plan,
    graph_expand_query,
    heuristic_query_understanding,
    normalize_candidates,
    rerank_candidates,
    resolve_weighted_rrf_config,
    weighted_rrf_fuse,
)
from danbao_poc.retrieval_plan import RetrievalPlanBuilder
from danbao_poc.retrieval_confidence import compute_retrieval_confidence
from danbao_poc.rate_limiter import check_rate_limit
from danbao_poc.retrieve_cache import get_cached, set_cached


app = FastAPI(title="Danbao Retrieve Service", version="1.0.0")
logger = logging.getLogger(__name__)
_worker_threads_started = False
_nacos_registrar: NacosServiceRegistrar | None = None


class IndexOptions(BaseModel):
    write_es: bool = True
    write_neo4j: bool = True
    lock_ttl_seconds: int = 1800
    incremental_reuse: bool = True
    force_rebuild: bool = False
    rebuild_communities: bool = False
    graph_delta_merge: bool = True


class IndexRequest(BaseModel):
    kb_id: int
    file_node_id: int
    parse_generation: str | None = None
    index_generation: str | None = None
    operation: str = "rebuild"
    async_mode: bool = False
    index_options: IndexOptions = Field(default_factory=IndexOptions)


class KbRebuildRequest(BaseModel):
    kb_id: int
    async_mode: bool = True
    index_options: IndexOptions = Field(default_factory=IndexOptions)


class KbQaIndexRequest(BaseModel):
    kb_id: int
    index_generation: str | None = None


class ChunkIndexRequest(BaseModel):
    kb_id: int
    file_node_id: int
    chunk_ids: list[int] = Field(default_factory=list)
    parse_generation: str | None = None
    index_generation: str | None = None
    operation: str = "upsert"


class QaIndexRequest(BaseModel):
    kb_id: int
    qa_ids: list[int] = Field(default_factory=list)
    index_generation: str | None = None
    operation: str = "upsert"


class QaGenerateRequest(BaseModel):
    kb_id: int
    file_node_id: int
    parse_generation: str | None = None
    max_pairs: int = 20
    audit_status: str = "pending"
    include_chunks: bool = True
    include_fields: bool = True
    sync_index: bool = False
    index_generation: str | None = None


class RetrieveRequest(BaseModel):
    kb_id: int | None = None
    kb_ids: list[int] = Field(default_factory=list)
    query: str
    file_node_ids: list[int] = Field(default_factory=list)
    allowed_file_ids: list[int] = Field(default_factory=list)
    top_k: int = 5
    retrieval_method: str | None = None
    graph: bool | None = None
    filters: dict[str, Any] | None = None
    options: dict[str, Any] | None = None


class FieldUpdateRequest(BaseModel):
    kb_id: int
    file_node_id: int
    field_id: int
    value_text: str
    normalized_json: dict[str, Any] | None = None
    parse_generation: str | None = None
    index_generation: str | None = None
    reason: str | None = None
    reviewer: str | None = None
    review_status: str | None = None
    evidence_chunk_id: int | None = None
    evidence_quote: str | None = None


class ReviewFieldRequest(BaseModel):
    kb_id: int
    file_node_id: int
    value_text: str
    normalized_json: dict[str, Any] | None = None
    parse_generation: str | None = None
    index_generation: str | None = None
    reason: str | None = None
    reviewer: str | None = None
    review_status: str = "corrected"
    evidence_chunk_id: int | None = None
    evidence_quote: str | None = None


class ReviewFieldUpdateItem(BaseModel):
    field_id: int
    value_text: str
    normalized_json: dict[str, Any] | None = None
    reason: str | None = None
    review_status: str = "corrected"
    evidence_chunk_id: int | None = None
    evidence_quote: str | None = None


class BatchReviewFieldsRequest(BaseModel):
    kb_id: int
    file_node_id: int
    parse_generation: str | None = None
    index_generation: str | None = None
    reviewer: str | None = None
    field_updates: list[ReviewFieldUpdateItem] = Field(default_factory=list)


class ReviewChunkRequest(BaseModel):
    kb_id: int
    file_node_id: int
    action: str = "approve"
    content: str | None = None
    summary: str | None = None
    parse_generation: str | None = None
    index_generation: str | None = None
    reviewer: str | None = None
    reason: str | None = None
    sync_index: bool = True


class ReviewFileRequest(BaseModel):
    kb_id: int
    action: str = "approve"
    reviewer: str | None = None
    reason: str | None = None
    sync_index: bool = True


class TableRetrieveRequest(BaseModel):
    kb_id: int
    query: str
    file_node_ids: list[int] = Field(default_factory=list)
    allowed_file_ids: list[int] = Field(default_factory=list)
    parse_generation: str | None = None
    top_k: int = 20


def _error(status_code: int, code: str, message: str, retryable: bool = False, stage: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": code,
            "message": message,
            "retryable": retryable,
            "stage": stage,
        },
    )


def neo4j_config() -> tuple[str, str, str]:
    return (
        os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "danbao123456"),
    )


@app.middleware("http")
async def auth_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or f"req_{int(time.time() * 1000)}"
    request.state.request_id = request_id
    token = os.getenv("DANBAO_API_TOKEN", "").strip()
    if token and request.url.path not in {"/health", "/ready", "/metrics"}:
        provided = request.headers.get("X-API-Token") or request.headers.get("Authorization", "").replace("Bearer ", "", 1)
        if provided != token:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error_code": "UNAUTHORIZED",
                        "message": "invalid or missing API token",
                        "retryable": False,
                        "stage": "auth",
                        "request_id": request_id,
                    }
                },
                headers={"X-Request-Id": request_id},
            )
    identity = request.headers.get("X-API-Token") or (request.client.host if request.client else "unknown")
    if request.url.path.startswith("/api/v1/retrieve"):
        allowed, count, limit = check_rate_limit("retrieve", identity, "RETRIEVE_RATE_LIMIT_PER_MINUTE", "RETRIEVE_RATE_LIMIT_WINDOW_SECONDS")
        if not allowed:
            inc("danbao_rate_limited_total")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "error_code": RATE_LIMITED.code,
                        "message": f"retrieve rate limit exceeded: {count}/{limit}",
                        "retryable": RATE_LIMITED.retryable,
                        "stage": RATE_LIMITED.stage,
                        "request_id": request_id,
                    }
                },
                headers={"X-Request-Id": request_id},
            )
    start = time.perf_counter()
    response = await call_next(request)
    inc("danbao_http_requests_total")
    observe("danbao_http_request_duration", time.perf_counter() - start)
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = request.headers.get("X-Request-Id") or f"req_{int(time.time() * 1000)}"
    detail = exc.detail
    if not isinstance(detail, dict) or "error_code" not in detail:
        detail = {
            "error_code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
            "retryable": exc.status_code >= 500,
            "stage": None,
        }
    detail["request_id"] = request_id
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers={"X-Request-Id": request_id})


@app.on_event("startup")
def startup() -> None:
    global _nacos_registrar
    init_db()
    _start_index_workers()
    try:
        ensure_indices()
    except Exception as exc:
        logger.warning("retrieve-service startup skipped ES ensure_indices: %s", exc)
    try:
        from ..term_weight import get_term_weighter
        get_term_weighter().build_idf_from_es(es_client())
    except Exception as exc:
        logger.warning("retrieve-service startup skipped TermWeighter IDF init: %s", exc)
    path = Path(os.getenv("NEO4J_CONSTRAINTS_PATH", "/app/cypher/constraints.cypher"))
    if path.exists():
        try:
            uri, user, password = neo4j_config()
            apply_constraints(uri, user, password, path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("retrieve-service startup skipped Neo4j constraints: %s", exc)
    _nacos_registrar = register_current_service(
        "NACOS_RETRIEVE_SERVICE_NAME",
        "danbao-retrieve-service",
        "NACOS_RETRIEVE_REGISTER_PORT",
        {"service": "retrieve-service", "version": app.version or ""},
        fallback_port_env="RETRIEVE_PORT",
    )


@app.on_event("shutdown")
def shutdown() -> None:
    if _nacos_registrar:
        _nacos_registrar.stop()


@app.get("/health")
def health() -> dict[str, str]:
    from danbao_poc import BUILD_TAG
    return {"status": "ok", "service": "retrieve-service", "build_tag": BUILD_TAG}


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


@app.get("/ready")
def ready() -> dict[str, Any]:
    return readiness(include_es=True, include_file_center=False, include_java=True)


@app.get("/api/v1/index/files/{file_node_id}/status")
def get_file_index_status(kb_id: int, file_node_id: int) -> dict[str, Any]:
    try:
        return get_index_status(kb_id, file_node_id)
    except Exception as exc:
        raise _error(500, "INDEX_STATUS_FAILED", str(exc), True, "index_status") from exc


@app.get("/api/v1/ops/index/{file_node_id}")
def get_ops_index_status(kb_id: int, file_node_id: int) -> dict[str, Any]:
    return get_file_index_status(kb_id, file_node_id)


@app.get("/api/v1/graph/files/{file_node_id}")
def get_file_knowledge_graph(
    file_node_id: int,
    kb_id: int,
    include_chunks: bool = False,
    limit: int = 160,
) -> dict[str, Any]:
    """Return the document-level Neo4j subgraph used by the Java knowledge workbench."""
    try:
        uri, user, password = neo4j_config()
        return load_file_graph(
            uri,
            user,
            password,
            kb_id,
            file_node_id,
            include_chunks=include_chunks,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("failed to load file graph kb_id=%s file_node_id=%s", kb_id, file_node_id)
        raise _error(503, "GRAPH_READ_FAILED", str(exc), True, "neo4j") from exc


@app.get("/api/v1/graph/knowledge-bases/{kb_id}")
def get_kb_knowledge_graph(
    kb_id: int,
    include_chunks: bool = False,
    limit: int = 120,
) -> dict[str, Any]:
    """Return the KB-level Neo4j graph used by the Java knowledge workspace."""
    try:
        uri, user, password = neo4j_config()
        return load_kb_graph(
            uri,
            user,
            password,
            kb_id,
            include_chunks=include_chunks,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("failed to load kb graph kb_id=%s", kb_id)
        raise _error(503, "GRAPH_READ_FAILED", str(exc), True, "neo4j") from exc


@app.get("/api/v1/graph/knowledge-bases/{kb_id}/audit")
def get_kb_graph_audit(
    kb_id: int,
    hub_degree: int = 20,
    limit: int = 100,
) -> dict[str, Any]:
    """Return read-only graph quality diagnostics and surprise-ranked facts."""
    try:
        uri, user, password = neo4j_config()
        return audit_kb_graph(
            uri,
            user,
            password,
            kb_id,
            hub_degree=hub_degree,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("failed to audit kb graph kb_id=%s", kb_id)
        raise _error(503, "GRAPH_AUDIT_FAILED", str(exc), True, "neo4j") from exc


@app.post("/api/v1/graph/knowledge-bases/{kb_id}/communities/rebuild")
def rebuild_kb_graph_communities(kb_id: int, min_size: int = 2) -> dict[str, Any]:
    """Explicitly rebuild KB communities and their precomputed global reports."""
    try:
        uri, user, password = neo4j_config()
        return rebuild_kb_communities(uri, user, password, kb_id, min_size=min_size)
    except Exception as exc:
        logger.exception("failed to rebuild kb graph communities kb_id=%s", kb_id)
        raise _error(503, "GRAPH_COMMUNITY_REBUILD_FAILED", str(exc), True, "neo4j") from exc


def _worker_count() -> int:
    try:
        return max(1, int(os.getenv("INDEX_WORKER_COUNT", "1")))
    except Exception:
        return 1


def _start_index_workers() -> None:
    global _worker_threads_started
    if _worker_threads_started:
        return
    _worker_threads_started = True
    for idx in range(_worker_count()):
        thread = threading.Thread(target=_index_worker_loop, name=f"index-worker-{idx + 1}", daemon=True)
        thread.start()


def _bool_option(options: dict[str, Any] | None, names: list[str], default: bool) -> bool:
    options = options or {}
    for name in names:
        if "." in name:
            current: Any = options
            found = True
            for part in name.split("."):
                if isinstance(current, dict) and part in current:
                    current = current.get(part)
                else:
                    found = False
                    break
            if found:
                value = current
            else:
                continue
        elif name in options:
            value = options.get(name)
        else:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)
    return default


def _is_debug_mode(options: dict[str, Any] | None) -> bool:
    """是否返回完整调试信息。options.debug / options.verbose / options.full_response"""
    return _bool_option(options, ["debug", "verbose", "full_response"], False)


def _float_option(options: dict[str, Any] | None, names: list[str], default: float) -> float:
    options = options or {}
    for name in names:
        value_found = False
        value: Any = None
        if "." in name:
            current: Any = options
            value_found = True
            for part in name.split("."):
                if isinstance(current, dict) and part in current:
                    current = current.get(part)
                else:
                    value_found = False
                    break
            value = current
        elif name in options:
            value_found = True
            value = options.get(name)
        if value_found:
            try:
                return float(value)
            except Exception:
                return default
    fusion = options.get("fusion")
    if isinstance(fusion, dict):
        for name in names:
            if name in fusion:
                try:
                    return float(fusion.get(name))
                except Exception:
                    return default
    return default


def _query_rewrite_guard(
    query: str,
    options: dict[str, Any] | None,
    heuristic: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    options = options or {}
    if _bool_option(options, ["query_assist.force_model", "force_query_model"], False):
        return True, {"enabled": True, "use_model": True, "reason": "forced"}
    enabled = _bool_option(options, ["query_assist.rewrite_guard.enabled", "rewrite_guard.enabled"], True)
    if not enabled:
        return True, {"enabled": False, "use_model": True, "reason": "disabled"}

    compact_query = clean_text(query)
    min_rewrite_chars = int(_float_option(options, ["query_assist.min_rewrite_chars", "rewrite_guard.min_rewrite_chars"], 50))
    exact_field_max_chars = int(_float_option(options, ["query_assist.exact_field_max_chars", "rewrite_guard.exact_field_max_chars"], 80))
    scope_anchor_max_chars = int(_float_option(options, ["query_assist.scope_anchor_max_chars", "rewrite_guard.scope_anchor_max_chars"], 120))
    min_rewrite_chars = max(0, min(min_rewrite_chars, 500))
    exact_field_max_chars = max(min_rewrite_chars, min(exact_field_max_chars, 500))
    scope_anchor_max_chars = max(exact_field_max_chars, min(scope_anchor_max_chars, 500))
    target_fields = heuristic.get("target_field_codes") or []
    scope_anchors = heuristic.get("scope_anchor_candidates") or []

    if scope_anchors and len(compact_query) <= scope_anchor_max_chars:
        return False, {
            "enabled": True,
            "use_model": False,
            "reason": "scope_anchor_detected",
            "query_length": len(compact_query),
            "scope_anchor_max_chars": scope_anchor_max_chars,
            "scope_anchor_candidates": scope_anchors,
        }
    if len(compact_query) <= min_rewrite_chars:
        return False, {
            "enabled": True,
            "use_model": False,
            "reason": "short_query",
            "query_length": len(compact_query),
            "min_rewrite_chars": min_rewrite_chars,
        }
    if target_fields and len(compact_query) <= exact_field_max_chars:
        return False, {
            "enabled": True,
            "use_model": False,
            "reason": "exact_field_query",
            "query_length": len(compact_query),
            "exact_field_max_chars": exact_field_max_chars,
            "target_field_codes": target_fields,
        }
    return True, {
        "enabled": True,
        "use_model": True,
        "reason": "long_or_complex_query",
        "query_length": len(compact_query),
        "min_rewrite_chars": min_rewrite_chars,
    }


def _effective_kb_ids(request: RetrieveRequest) -> list[int]:
    kb_ids = [int(item) for item in request.kb_ids if item is not None]
    if request.kb_id is not None and int(request.kb_id) not in kb_ids:
        kb_ids.insert(0, int(request.kb_id))
    seen: set[int] = set()
    result: list[int] = []
    for kb_id in kb_ids:
        if kb_id not in seen:
            seen.add(kb_id)
            result.append(kb_id)
    return result


def _file_display_name(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return unquote(str(row.get("name") or row.get("original_name") or "")).strip()


def _load_active_file_meta(active_file_ids_by_kb: dict[int, list[int]]) -> dict[int, dict[str, Any]]:
    file_ids = sorted({int(file_id) for rows in active_file_ids_by_kb.values() for file_id in (rows or [])})
    if not file_ids:
        return {}
    result: dict[int, dict[str, Any]] = {}
    try:
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                for offset in range(0, len(file_ids), 500):
                    batch = file_ids[offset : offset + 500]
                    placeholders = ", ".join(["%s"] * len(batch))
                    cur.execute(
                        f"""
                        SELECT id, kb_id, name, original_name, profile
                        FROM kb_file_node
                        WHERE id IN ({placeholders}) AND del_flag=0 AND node_type='file'
                        """,
                        batch,
                    )
                    for row in cur.fetchall():
                        row["doc_name"] = _file_display_name(row)
                        result[int(row["id"])] = row
    except Exception as exc:
        logger.debug("active file metadata lookup failed: %s", exc)
    return result


def _resolve_retrieve_profile(
    request_options: dict[str, Any],
    file_meta_by_id: dict[int, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    raw_profile = request_options.get("profile")
    if raw_profile:
        profile = normalize_profile(str(raw_profile)) or str(raw_profile)
        return profile, {"source": "request_options", "profile": profile, "raw_profile": raw_profile}
    profiles = [
        normalize_profile(str(row.get("profile") or "")) or str(row.get("profile") or "")
        for row in file_meta_by_id.values()
        if row.get("profile")
    ]
    profiles = [profile for profile in profiles if profile]
    if not profiles:
        return "business_plan", {"source": "default", "profile": "business_plan", "reason": "no_active_file_profile"}
    counts = Counter(profiles)
    profile, count = counts.most_common(1)[0]
    if len(counts) == 1:
        reason = "all_files_same_profile"
    elif count > (len(profiles) / 2):
        reason = "majority_profile"
    else:
        profile = "business_plan"
        reason = "mixed_profiles_default_business_plan"
    return profile, {
        "source": "active_file_scope",
        "profile": profile,
        "reason": reason,
        "profile_counts": dict(counts),
    }


def _resolve_scope_anchor_file_filter(
    *,
    kb_ids: list[int],
    active_file_ids_by_kb: dict[int, list[int]],
    file_meta_by_id: dict[int, dict[str, Any]],
    scope_anchors: list[str],
    enabled: bool,
    strict: bool,
) -> tuple[dict[int, list[int]], dict[str, Any]]:
    active_sets = {kb_id: {int(item) for item in active_file_ids_by_kb.get(kb_id) or []} for kb_id in kb_ids}
    debug: dict[str, Any] = {
        "enabled": bool(enabled and scope_anchors),
        "strict": strict,
        "scope_anchors": scope_anchors,
        "matched_files": [],
        "scoped_file_ids_by_kb": {},
        "fallback_to_active_scope": False,
        "filter_mode": "disabled",
    }
    if not enabled or not scope_anchors:
        return {}, debug

    matched_by_kb: dict[int, list[int]] = {}
    normalized_anchors = [anchor.strip() for anchor in scope_anchors if anchor and anchor.strip()]
    anchor_aliases = expand_product_aliases(normalized_anchors)
    for file_id, row in file_meta_by_id.items():
        kb_id = int(row.get("kb_id") or 0)
        if kb_id not in active_sets or file_id not in active_sets[kb_id]:
            continue
        doc_name = _file_display_name(row)
        metadata = row.get("metadata_json") or row.get("metadata")
        product_names = extract_product_names(doc_name, row.get("original_name"), metadata=metadata)
        match_text = " ".join([doc_name, *product_names])
        matched = [anchor for anchor in normalized_anchors if any(alias and alias in match_text for alias in expand_product_aliases([anchor]))]
        if not matched:
            matched = [anchor for anchor in normalized_anchors if anchor and anchor in doc_name]
        if not matched:
            continue
        matched_by_kb.setdefault(kb_id, []).append(file_id)
        debug["matched_files"].append({
            "kb_id": kb_id,
            "file_node_id": file_id,
            "doc_name": doc_name,
            "matched_anchors": matched,
            "product_names": product_names,
        })

    if not matched_by_kb:
        debug["fallback_to_active_scope"] = True
        debug["filter_mode"] = "fallback_no_matched_file"
        return {}, debug

    scoped: dict[int, list[int]] = {}
    for kb_id in kb_ids:
        active = active_sets.get(kb_id) or set()
        matched = set(matched_by_kb.get(kb_id) or [])
        intersection = sorted(active & matched)
        if intersection:
            scoped[kb_id] = intersection
        elif strict and matched:
            scoped[kb_id] = sorted(matched)

    if not scoped:
        debug["fallback_to_active_scope"] = True
        debug["filter_mode"] = "fallback_empty_intersection"
        return {}, debug

    debug["filter_mode"] = "active_intersection"
    debug["scoped_file_ids_by_kb"] = {str(k): v for k, v in scoped.items()}
    debug["anchor_aliases"] = anchor_aliases
    return scoped, debug


def _route_enabled(options: dict[str, Any], route: str, default: bool) -> bool:
    aliases = {
        "qa": ["routes.qa_preset_enabled", "routes.qa_enabled", "qa_preset_enabled", "qa_enabled"],
        "structured": ["routes.structured_enabled", "routes.knowledge_unit_enabled", "structured_enabled", "knowledge_unit_enabled"],
        "section_summary": ["routes.section_summary_enabled", "section_summary_enabled", "summary_enabled"],
        "graph": ["graph", "routes.graph_enabled", "graph_enabled", "use_graph"],
        "bm25": ["routes.bm25_enabled", "bm25_enabled"],
        "vector": ["routes.vector_enabled", "vector_enabled"],
    }
    return _bool_option(options, aliases.get(route, [f"routes.{route}_enabled", f"{route}_enabled"]), default)


def _chunk_type_filters_from_options(options: dict[str, Any]) -> tuple[list[str] | None, str]:
    explicit = options.get("chunk_types") or options.get("chunk_type_filters")
    if isinstance(explicit, list):
        return [str(item) for item in explicit if item], "custom"
    return_mode = str(options.get("return_mode") or options.get("retrieval_return_mode") or "evidence_group")
    if return_mode == "debug_full":
        return None, return_mode
    # 多模态视觉 chunk（image/chart/diagram）也应纳入默认召回，见 multimodal._CHUNK_TYPE_BY_VISUAL
    visual_types = ["image", "chart", "diagram", "image_group"]
    if return_mode == "raw_chunk_first":
        return ["small_chunk", "original", "text_section", "clause", "project_section", "contract_clause", "table_text"] + visual_types, return_mode
    if return_mode == "structured_first":
        return ["small_chunk", "section_chunk"] + visual_types, return_mode
    return ["small_chunk", "section_chunk"] + visual_types, return_mode


def _dict_option(options: dict[str, Any] | None, name: str) -> dict[str, Any]:
    options = options or {}
    current: Any = options
    for part in name.split("."):
        if not isinstance(current, dict) or part not in current:
            return {}
        current = current.get(part)
    return current if isinstance(current, dict) else {}


def _retry_options(options: dict[str, Any] | None) -> dict[str, Any]:
    enabled = _bool_option(options, ["retry.enabled", "enable_retrieve_retry"], True)
    return {
        "enabled": enabled,
        "low_confidence_threshold": _float_option(options, ["retry.low_confidence_threshold"], 0.12),
        "min_matched_channels": int(_float_option(options, ["retry.min_matched_channels"], 1)),
        "top_k_multiplier": max(1, int(_float_option(options, ["retry.top_k_multiplier"], 2))),
        "include_structured": _bool_option(options, ["retry.include_structured"], True),
        "include_section_summary": _bool_option(options, ["retry.include_section_summary"], True),
        "include_bm25": _bool_option(options, ["retry.include_bm25"], True),
    }


def _needs_retrieve_retry(candidates: list[dict[str, Any]], retry_options: dict[str, Any]) -> tuple[bool, str]:
    if not retry_options.get("enabled"):
        return False, "disabled"
    if not candidates:
        return True, "empty_candidates"
    top = candidates[0]
    top_score = float(top.get("normalized_score") or top.get("score") or 0.0)
    threshold = float(retry_options.get("low_confidence_threshold") or 0.0)
    if threshold > 0 and top_score < threshold:
        return True, "low_confidence"
    matched = (top.get("score_details") or {}).get("matched_channels") or top.get("route_names") or []
    if len(matched) < int(retry_options.get("min_matched_channels") or 1):
        return True, "too_few_matched_channels"
    return False, "not_needed"


def _merge_route_rows(existing: list[dict[str, Any]], retry_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {str(item.get("identity_key") or item.get("candidate_id") or item.get("chunk_id") or id(item)) for item in merged}
    for row in retry_rows:
        key = str(row.get("identity_key") or row.get("candidate_id") or row.get("chunk_id") or id(row))
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _candidate_field_codes(item: dict[str, Any]) -> set[str]:
    codes = {str(item.get("field_code"))} if item.get("field_code") else set()
    for raw in item.get("raw_items") or []:
        if isinstance(raw, dict) and raw.get("field_code"):
            codes.add(str(raw.get("field_code")))
    for merged in item.get("merged_candidates") or []:
        if isinstance(merged, dict) and merged.get("field_code"):
            codes.add(str(merged.get("field_code")))
    return {code for code in codes if code}


def _apply_document_and_field_scoring(
    candidates: list[dict[str, Any]],
    *,
    scope_anchors: list[str],
    file_meta_by_id: dict[int, dict[str, Any]],
    target_field_codes: list[str],
    document_match_boost: float = 0.30,
    document_mismatch_penalty: float = 0.55,
    qa_mismatch_penalty: float = 0.50,
    field_mismatch_penalty: float = 0.65,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not candidates:
        return candidates, {"enabled": False, "candidate_count": 0}

    anchors = [anchor.strip() for anchor in scope_anchors if anchor and anchor.strip()]
    target_set = {str(code) for code in target_field_codes if code}
    document_boosted = 0
    document_penalized = 0
    qa_penalized = 0
    field_penalized = 0
    for item in candidates:
        original_score = float(item.get("score") or 0.0)
        score = original_score
        file_id = item.get("file_node_id")
        try:
            file_id = int(file_id) if file_id is not None and file_id != "" else None
        except Exception:
            file_id = None
        doc_name = _file_display_name(file_meta_by_id.get(file_id)) if file_id is not None else str(item.get("doc_name") or "")
        if doc_name:
            item["doc_name"] = doc_name

        file_meta = file_meta_by_id.get(file_id) if file_id is not None else {}
        product_names = extract_product_names(doc_name, item.get("title"), item.get("content"), metadata=(file_meta or {}).get("metadata_json") or item.get("metadata_json"))
        match_text = " ".join([doc_name, *product_names])
        matched_anchors = [anchor for anchor in anchors if any(alias and alias in match_text for alias in expand_product_aliases([anchor]))]
        if not matched_anchors:
            matched_anchors = [anchor for anchor in anchors if anchor in doc_name]
        document_match = {
            "doc_name": doc_name,
            "matched_anchors": matched_anchors,
            "matched_product_names": product_names,
            "original_score": original_score,
            "document_match_boost": 0.0,
            "document_mismatch_penalty": 1.0,
            "qa_mismatch_penalty": 1.0,
            "field_mismatch_penalty": 1.0,
        }
        if anchors and matched_anchors:
            boost = document_match_boost * len(matched_anchors)
            score += boost
            document_match["document_match_boost"] = boost
            document_boosted += 1
        elif anchors and doc_name:
            score *= document_mismatch_penalty
            document_match["document_mismatch_penalty"] = document_mismatch_penalty
            document_penalized += 1
            generation_source = str(item.get("generation_source") or "")
            answer_type = str(item.get("answer_type") or "")
            hit_types = set(item.get("hit_types") or [])
            route_names = set(item.get("route_names") or [])
            is_auto_qa = (
                "qa" in hit_types
                or "qa" in route_names
                or generation_source == "auto_pregenerated"
                or answer_type in {"auto_qa", "field_answer"}
            ) and not bool(item.get("manual_override"))
            if is_auto_qa:
                score *= qa_mismatch_penalty
                document_match["qa_mismatch_penalty"] = qa_mismatch_penalty
                qa_penalized += 1

        field_codes = _candidate_field_codes(item)
        if target_set and field_codes and not (field_codes & target_set):
            score *= field_mismatch_penalty
            document_match["field_mismatch_penalty"] = field_mismatch_penalty
            document_match["candidate_field_codes"] = sorted(field_codes)
            document_match["target_field_codes"] = sorted(target_set)
            field_penalized += 1

        item["score"] = score
        score_details = item.get("score_details") or {}
        document_match["final_score"] = score
        score_details["document_match"] = document_match
        item["score_details"] = score_details

    candidates.sort(key=lambda r: -float(r.get("score") or 0.0))
    max_score = max((float(r.get("score") or 0.0) for r in candidates), default=0.0)
    if max_score > 0:
        for item in candidates:
            item["normalized_score"] = float(item.get("score") or 0.0) / max_score

    return candidates, {
        "enabled": True,
        "scope_anchors": anchors,
        "document_match_boost": document_match_boost,
        "document_mismatch_penalty": document_mismatch_penalty,
        "qa_mismatch_penalty": qa_mismatch_penalty,
        "field_mismatch_penalty": field_mismatch_penalty,
        "document_boosted": document_boosted,
        "document_penalized": document_penalized,
        "qa_penalized": qa_penalized,
        "field_penalized": field_penalized,
        "total_candidates": len(candidates),
    }

def _visual_asset_ids(chunk: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """从 chunk 的 metadata_json 里取多模态原图引用（file_center_file_id / visual_asset_id）。"""
    if not chunk:
        return None, None
    metadata = chunk.get("metadata_json") or chunk.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    metadata = metadata if isinstance(metadata, dict) else {}
    return metadata.get("file_center_file_id"), metadata.get("visual_asset_id")


def _image_group_payload(chunk: dict[str, Any] | None) -> dict[str, Any] | None:
    """image_group chunk 的步骤绑定信息（steps → evidence_images → image_file_id）。

    命中流程组（procedure）时，把步骤与证据图片的绑定透传给答案层，做到「按步骤回图」。
    """
    if not chunk:
        return None
    metadata = chunk.get("metadata_json") or chunk.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    metadata = metadata if isinstance(metadata, dict) else {}
    if metadata.get("source_kind") != "image_group":
        return None
    return {
        "group_id": metadata.get("group_id"),
        "group_type": metadata.get("group_type"),
        "topic": metadata.get("topic"),
        "ordered_image_ids": metadata.get("ordered_image_ids") or [],
        "steps": metadata.get("steps") or [],
    }


def _enrich_evidence_groups(
    evidence_groups: list[dict[str, Any]],
    *,
    active_file_ids_by_kb: dict[int, list[int]],
    active_index_generations_by_kb: dict[int, list[str]],
    options: dict[str, Any] | None = None,
    query: str = "",
    understanding: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    options = options or {}
    understanding = understanding or {}
    parent_context_enabled = _bool_option(options, ["parent_context.enabled", "enable_parent_context"], True)
    replace_child_context = _bool_option(options, ["parent_context.replace_child_context", "replace_child_context"], True)
    min_context_chars = int(_float_option(options, ["parent_context.min_context_chars", "min_parent_context_chars"], 700))
    min_context_chars = max(100, min_context_chars)
    text = query or str(understanding.get("query_rewrite") or "")
    target_fields = [str(item) for item in understanding.get("target_field_codes") or [] if item]
    comparison_query = bool(understanding.get("comparison_query"))
    broad_query = any(term in text for term in ["有哪些", "介绍", "完整", "整体", "流程", "怎么申请", "如何办理", "办理流程", "分别"])
    context_mode = "comparison" if comparison_query else ("broad" if broad_query else ("field" if target_fields else "semantic"))

    chunk_ids_by_kb: dict[int, list[int]] = {}
    for group in evidence_groups:
        kb_id = group.get("kb_id")
        chunk_id = group.get("primary_chunk_id")
        if kb_id is None or not chunk_id:
            continue
        chunk_ids_by_kb.setdefault(int(kb_id), []).append(int(chunk_id))

    chunks_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    summaries_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for kb_id, chunk_ids in chunk_ids_by_kb.items():
        unique_chunk_ids = sorted(set(chunk_ids))
        chunks = load_chunks_by_ids(
            kb_id,
            active_file_ids_by_kb.get(kb_id) or [],
            unique_chunk_ids,
            active_index_generations_by_kb.get(kb_id) or None,
            limit=max(len(unique_chunk_ids), 1),
        )
        for chunk in chunks:
            if chunk.get("chunk_id"):
                chunks_by_key[(kb_id, int(chunk["chunk_id"]))] = chunk
        summaries = load_section_summaries_by_chunk_ids(
            kb_id,
            unique_chunk_ids,
            active_file_ids_by_kb.get(kb_id) or [],
            active_index_generations_by_kb.get(kb_id) or None,
            limit=max(len(unique_chunk_ids) * 2, 1),
        )
        for summary in summaries:
            if summary.get("chunk_id"):
                summaries_by_key[(kb_id, int(summary["chunk_id"]))] = summary

    context_by_source: dict[tuple[int, int], list[dict[str, Any]]] = {}
    if parent_context_enabled:
        for kb_id, chunk_ids in chunk_ids_by_kb.items():
            related_chunks = load_related_chunks(
                kb_id,
                active_file_ids_by_kb.get(kb_id) or [],
                sorted(set(chunk_ids)),
                active_index_generations_by_kb.get(kb_id) or None,
                ["parent_context", "section_context"],
                max(len(set(chunk_ids)) * 3, 1),
            )
            for row in related_chunks:
                source_chunk_id = row.get("source_chunk_id")
                if not source_chunk_id:
                    continue
                context_by_source.setdefault((kb_id, int(source_chunk_id)), []).append(row)

    def _choose_context(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        debug = {
            "mode": context_mode,
            "min_context_chars": min_context_chars,
            "max_context_chars": None,
            "candidate_count": len(rows),
            "selected_reason": "missing",
        }
        if not rows:
            return None, debug

        def _content_len(row: dict[str, Any]) -> int:
            return len(clean_text(row.get("content")))

        def _weight(row: dict[str, Any]) -> float:
            try:
                return float(row.get("relation_weight") or 0.0)
            except Exception:
                return 0.0

        def _best(relation_type: str) -> dict[str, Any] | None:
            candidates = [row for row in rows if str(row.get("relation_type") or "") == relation_type]
            if not candidates:
                return None
            return sorted(
                candidates,
                key=lambda row: (
                    -_weight(row),
                    int(row.get("seq_no") or 999999),
                    -_content_len(row),
                ),
            )[0]

        section_context = _best("section_context")
        parent_context = _best("parent_context")
        section_len = _content_len(section_context) if section_context else 0
        parent_len = _content_len(parent_context) if parent_context else 0
        debug.update({
            "section_context_chunk_id": section_context.get("chunk_id") if section_context else None,
            "section_context_chars": section_len,
            "parent_context_chunk_id": parent_context.get("chunk_id") if parent_context else None,
            "parent_context_chars": parent_len,
        })

        selected: dict[str, Any] | None = None
        reason = "fallback"
        if context_mode in {"broad", "comparison"}:
            selected = parent_context or section_context
            reason = "upper_parent_for_broad_query" if parent_context else "section_fallback_for_broad_query"
        elif context_mode == "field":
            if section_context and section_len >= min_context_chars:
                selected = section_context
                reason = "direct_parent_for_field_query"
            else:
                selected = parent_context or section_context
                reason = "upper_parent_for_short_direct_parent" if parent_context else "short_direct_parent_fallback"
        else:
            if section_context and section_len >= min_context_chars:
                selected = section_context
                reason = "direct_parent_for_semantic_query"
            else:
                selected = parent_context or section_context
                reason = "upper_parent_for_short_semantic_context" if parent_context else "semantic_fallback"

        debug["selected_reason"] = reason
        debug["selected_relation_type"] = selected.get("relation_type") if selected else None
        debug["selected_chunk_id"] = selected.get("chunk_id") if selected else None
        return selected, debug

    def _chunk_payload(chunk: dict[str, Any] | None, *, relation_type: str | None = None, source_chunk_id: Any = None) -> dict[str, Any] | None:
        if not chunk:
            return None
        file_center_file_id, visual_asset_id = _visual_asset_ids(chunk)
        image_group = _image_group_payload(chunk)
        return {
            "chunk_id": chunk.get("chunk_id"),
            "kb_id": chunk.get("kb_id"),
            "file_node_id": chunk.get("file_node_id"),
            "chunk_type": chunk.get("chunk_type"),
            "section_id": chunk.get("section_id"),
            "section_type": chunk.get("section_type"),
            "chunk_group_id": chunk.get("chunk_group_id"),
            "title": chunk.get("title"),
            "content": chunk.get("content"),
            "summary": chunk.get("summary"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "file_center_file_id": file_center_file_id,
            "visual_asset_id": visual_asset_id,
            "image_group": image_group,
            "relation_type": relation_type,
            "context_level": "grandparent" if relation_type == "parent_context" else ("parent" if relation_type == "section_context" else "hit"),
            "source_chunk_id": source_chunk_id,
        }

    for group in evidence_groups:
        kb_id = group.get("kb_id")
        chunk_id = group.get("primary_chunk_id")
        if kb_id is None or not chunk_id:
            group.setdefault("parent_context", {})
            continue
        key = (int(kb_id), int(chunk_id))
        chunk = chunks_by_key.get(key)
        if chunk:
            file_center_file_id, visual_asset_id = _visual_asset_ids(chunk)
            image_group = _image_group_payload(chunk)
            group["primary_chunk"] = {
                "chunk_id": chunk.get("chunk_id"),
                "kb_id": chunk.get("kb_id"),
                "file_node_id": chunk.get("file_node_id"),
                "chunk_type": chunk.get("chunk_type"),
                "section_id": chunk.get("section_id"),
                "section_type": chunk.get("section_type"),
                "chunk_group_id": chunk.get("chunk_group_id"),
                "title": chunk.get("title"),
                "content": chunk.get("content"),
                "summary": chunk.get("summary"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "file_center_file_id": file_center_file_id,
                "visual_asset_id": visual_asset_id,
                "image_group": image_group,
            }
            group["display_text"] = chunk.get("content") or group.get("display_text")
        summary = summaries_by_key.get(key)
        summary_match = (group.get("matched_section_summaries") or [{}])[0] if group.get("matched_section_summaries") else {}
        context_chunk, context_selection = _choose_context(context_by_source.get(key) or [])
        primary_chunk_payload = _chunk_payload(chunk, relation_type="primary_chunk", source_chunk_id=chunk_id)
        context_chunk_payload = _chunk_payload(
            context_chunk,
            relation_type=context_chunk.get("relation_type") if context_chunk else None,
            source_chunk_id=context_chunk.get("source_chunk_id") if context_chunk else None,
        )
        answer_context = context_chunk_payload or primary_chunk_payload
        if answer_context:
            group["retrieval_hit_chunk"] = primary_chunk_payload
            group["answer_context_chunk"] = answer_context
            if replace_child_context:
                group["answer_hint"] = answer_context.get("content") or group.get("answer_hint")
        group["parent_context"] = {
            "section_id": summary.get("section_id") if summary else (summary_match.get("section_id") or (chunk.get("section_id") if chunk else None)),
            "section_title": summary.get("section_title") if summary else (summary_match.get("section_title") or (chunk.get("title") if chunk else None)),
            "section_path": unquote(sp) if (sp := (summary.get("section_path") if summary else summary_match.get("section_path"))) else None,
            "section_level": summary.get("section_level") if summary else summary_match.get("section_level"),
            "section_summary": summary.get("node_summary") if summary else summary_match.get("node_summary"),
            "summary_source": summary.get("summary_source") if summary else summary_match.get("summary_source"),
            "enabled": parent_context_enabled,
            "replace_child_context": replace_child_context,
            "context_chunk_id": context_chunk_payload.get("chunk_id") if context_chunk_payload else None,
            "context_relation_type": context_chunk_payload.get("relation_type") if context_chunk_payload else None,
            "context_level": context_chunk_payload.get("context_level") if context_chunk_payload else None,
            "source_chunk_id": context_chunk_payload.get("source_chunk_id") if context_chunk_payload else None,
            "context_title": context_chunk_payload.get("title") if context_chunk_payload else None,
            "context_page_start": context_chunk_payload.get("page_start") if context_chunk_payload else None,
            "context_page_end": context_chunk_payload.get("page_end") if context_chunk_payload else None,
            "context_available": bool(context_chunk_payload),
            "answer_context_chunk_id": answer_context.get("chunk_id") if answer_context else None,
            "selection": context_selection,
        }
    return evidence_groups


def _unquote_all(obj: Any) -> Any:
    """Recursively URL-decode all strings in a nested structure."""
    if isinstance(obj, str):
        return unquote(obj)
    if isinstance(obj, dict):
        return {k: _unquote_all(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unquote_all(item) for item in obj]
    return obj


# ---- results 精简字段白名单 ----
_RESULT_KEEP_FIELDS = [
    "kb_id", "file_node_id", "chunk_id", "primary_chunk_id",
    "title", "content", "value_text", "answer_hint",
    "score", "normalized_score",
    "page_no", "chunk_type",
    "file_center_file_id", "visual_asset_id", "image_group",
    "field_code", "field_id", "qa_id",
    "section_id", "section_title", "section_path",
    "hit_type", "hit_types", "route_name", "route_names",
    "match_type", "reason",
    "hit_routes", "page_numbers", "group_rank",
    "citation_index", "evidence_chain", "graph_path",
    "parent_context",
    "answer_context_chunk",
    "retrieval_hit_chunk",
]


def _simplify_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """精简 results：只保留对外展示/LLM 有用的 28 个字段。"""
    return [{k: r.get(k) for k in _RESULT_KEEP_FIELDS} for r in results if isinstance(r, dict)]


def _build_llm_context(
    evidence_groups: list[dict[str, Any]],
    *,
    top_k: int = 5,
    file_meta_by_id: dict[int, dict[str, Any]] | None = None,
) -> str:
    """基于 evidence_groups 构建带来源/章节/摘要的富上下文文本。"""
    blocks: list[str] = []
    for idx, group in enumerate(evidence_groups[:max(top_k, 1)], 1):
        file_id = group.get("file_node_id")
        meta = (file_meta_by_id or {}).get(file_id) if file_id is not None else None
        doc_name = (meta or {}).get("doc_name") or group.get("doc_name") or ""

        pc = group.get("parent_context") or {}
        section_path = unquote(pc.get("section_path") or "")
        section_summary = pc.get("section_summary") or ""
        section_title = pc.get("section_title") or ""

        answer_hint = group.get("answer_hint") or group.get("display_text") or ""
        primary_chunk = group.get("primary_chunk") or {}
        title = primary_chunk.get("title") or group.get("title") or section_title or ""
        page_start = primary_chunk.get("page_start") or group.get("page_start")
        page_end = primary_chunk.get("page_end") or group.get("page_end")

        lines: list[str] = []
        lines.append(f"[ref_{idx}]")
        if doc_name:
            lines.append(f"来源文件：{doc_name}")
        if title and title != doc_name:
            lines.append(f"标题：{title}")
        if section_path:
            lines.append(f"所属章节：{section_path}")
        if section_summary:
            lines.append(f"章节摘要：{section_summary}")
        if page_start is not None:
            page_info = f"页码 {page_start}"
            if page_end is not None and page_end != page_start:
                page_info += f"-{page_end}"
            lines.append(page_info)
        lines.append("")
        lines.append(answer_hint)
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


def _flatten_context_into_results(results: list[dict[str, Any]], evidence_groups: list[dict[str, Any]]) -> None:
    """Copy parent/child context fields from evidence_groups into results in-place.

    Java-side clients only read the ``results`` array, so we flatten the
    evidence_group's context enrichment (parent_context, answer_context_chunk,
    answer_hint) directly into each matching result dict.
    """
    if not results or not evidence_groups:
        return
    group_by_chunk: dict[tuple[int, int], dict[str, Any]] = {}
    for group in evidence_groups:
        kb_id = group.get("kb_id")
        chunk_id = group.get("primary_chunk_id")
        if kb_id is not None and chunk_id is not None:
            group_by_chunk[(int(kb_id), int(chunk_id))] = group

    citation_index: dict[tuple[int, int], int] = {}
    for group in evidence_groups:
        kb_id = group.get("kb_id")
        chunk_id = group.get("primary_chunk_id")
        rank = group.get("rank")
        if kb_id is not None and chunk_id is not None and rank is not None:
            citation_index[(int(kb_id), int(chunk_id))] = int(rank)

    for result in results:
        if not isinstance(result, dict):
            continue
        kb_id = result.get("kb_id")
        chunk_id = result.get("chunk_id") or result.get("primary_chunk_id")
        if kb_id is None or chunk_id is None:
            continue
        key = (int(kb_id), int(chunk_id))
        group = group_by_chunk.get(key)
        if not group:
            continue

        # ---- parent_context ----
        pc = group.get("parent_context") or {}
        result["parent_context"] = {
            "enabled": pc.get("enabled"),
            "available": pc.get("context_available"),
            "section_id": pc.get("section_id"),
            "section_title": pc.get("section_title"),
            "section_path": pc.get("section_path"),
            "section_level": pc.get("section_level"),
            "section_summary": pc.get("section_summary"),
            "summary_source": pc.get("summary_source"),
            "context_chunk_id": pc.get("context_chunk_id"),
            "context_relation_type": pc.get("context_relation_type"),
            "context_level": pc.get("context_level"),
            "context_title": pc.get("context_title"),
            "context_page_start": pc.get("context_page_start"),
            "context_page_end": pc.get("context_page_end"),
        }

        # ---- answer_context_chunk (the chunk actually used for answering) ----
        acc = group.get("answer_context_chunk") or {}
        result["answer_context_chunk"] = {
            "chunk_id": acc.get("chunk_id"),
            "chunk_type": acc.get("chunk_type"),
            "section_id": acc.get("section_id"),
            "section_type": acc.get("section_type"),
            "title": acc.get("title"),
            "content": acc.get("content"),
            "page_start": acc.get("page_start"),
            "page_end": acc.get("page_end"),
            "relation_type": acc.get("relation_type"),
            "context_level": acc.get("context_level"),
        }

        # ---- retrieval_hit_chunk ----
        rhc = group.get("retrieval_hit_chunk") or {}
        result["retrieval_hit_chunk"] = {
            "chunk_id": rhc.get("chunk_id"),
            "chunk_type": rhc.get("chunk_type"),
            "title": rhc.get("title"),
            "content": rhc.get("content"),
            "page_start": rhc.get("page_start"),
            "page_end": rhc.get("page_end"),
            "file_center_file_id": rhc.get("file_center_file_id"),
            "visual_asset_id": rhc.get("visual_asset_id"),
            "image_group": rhc.get("image_group"),
        }
        # ---- 多模态原图引用（顶层，供 Java 端 @JsonProperty 映射）----
        result["file_center_file_id"] = rhc.get("file_center_file_id")
        result["visual_asset_id"] = rhc.get("visual_asset_id")
        # ---- 流程组步骤绑定（顶层，供答案阶段按步骤回图）----
        result["image_group"] = rhc.get("image_group")

        # ---- answer_hint (the context-replaced hint text) ----
        result["answer_hint"] = group.get("answer_hint")

        # ---- citation index ----
        ref_idx = citation_index.get(key)
        if ref_idx is not None:
            result["citation_index"] = ref_idx

        # ---- evidence summary ----
        result["hit_routes"] = sorted(group.get("hit_routes") or [])
        result["hit_types"] = sorted(group.get("hit_types") or [])
        result["page_numbers"] = sorted(group.get("page_numbers") or [])
        result["group_rank"] = group.get("rank")
        result["graph_path"] = result.get("graph_path") or next(
            (
                item.get("graph_path")
                for item in (group.get("matched_graph_paths") or [])
                if isinstance(item, dict) and item.get("graph_path")
            ),
            None,
        )


def _apply_evidence_diversity(evidence_groups: list[dict[str, Any]], options: dict[str, Any], top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    max_per_section = int(_float_option(options, ["diversity.max_groups_per_section", "max_groups_per_section"], 0))
    max_per_file = int(_float_option(options, ["diversity.max_groups_per_file", "max_groups_per_file"], 0))
    max_per_section = max(0, min(max_per_section, top_k))
    max_per_file = max(0, min(max_per_file, top_k))
    if max_per_section <= 0 and max_per_file <= 0:
        return evidence_groups[:top_k], {"enabled": False, "before": len(evidence_groups), "after": min(len(evidence_groups), top_k)}

    section_counts: dict[str, int] = {}
    file_counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for group in evidence_groups:
        section_id = str((group.get("parent_context") or {}).get("section_id") or (group.get("primary_chunk") or {}).get("section_id") or "")
        file_id = str(group.get("file_node_id") or (group.get("primary_chunk") or {}).get("file_node_id") or "")
        section_blocked = bool(section_id and max_per_section > 0 and section_counts.get(section_id, 0) >= max_per_section)
        file_blocked = bool(file_id and max_per_file > 0 and file_counts.get(file_id, 0) >= max_per_file)
        if section_blocked or file_blocked:
            deferred.append(group)
            continue
        selected.append(group)
        if section_id:
            section_counts[section_id] = section_counts.get(section_id, 0) + 1
        if file_id:
            file_counts[file_id] = file_counts.get(file_id, 0) + 1
        if len(selected) >= top_k:
            break
    if len(selected) < top_k:
        selected.extend(deferred[: top_k - len(selected)])
    for index, group in enumerate(selected[:top_k], 1):
        group["rank"] = index
    return selected[:top_k], {
        "enabled": True,
        "before": len(evidence_groups),
        "after": len(selected[:top_k]),
        "max_groups_per_section": max_per_section,
        "max_groups_per_file": max_per_file,
        "deferred_count": len(deferred),
    }


def _apply_comparison_anchor_coverage(
    evidence_groups: list[dict[str, Any]],
    *,
    comparison_anchors: list[str],
    file_meta_by_id: dict[int, dict[str, Any]],
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    anchors = [anchor.strip() for anchor in comparison_anchors if anchor and anchor.strip()]
    debug: dict[str, Any] = {
        "enabled": bool(anchors),
        "comparison_anchors": anchors,
        "covered_anchors": [],
        "missing_comparison_targets": [],
        "comparison_groups": [],
    }
    if not anchors or not evidence_groups:
        debug["missing_comparison_targets"] = anchors
        return evidence_groups[:top_k], debug

    match_cache: dict[str, str] = {}

    def _group_match_text(group: dict[str, Any]) -> str:
        group_id = str(group.get("group_id") or "")
        if group_id in match_cache:
            return match_cache[group_id]
        file_id = group.get("file_node_id")
        try:
            file_id = int(file_id) if file_id is not None and file_id != "" else None
        except Exception:
            file_id = None
        file_meta = file_meta_by_id.get(file_id) if file_id is not None else {}
        doc_name = _file_display_name(file_meta) if file_meta else str(group.get("doc_name") or "")
        product_names = extract_product_names(doc_name, group.get("display_text"), metadata=(file_meta or {}).get("metadata_json"))
        match_cache[group_id] = " ".join([doc_name, *product_names])
        return match_cache[group_id]

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    covered: list[str] = []
    for anchor in anchors:
        aliases = expand_product_aliases([anchor])
        matching_groups = [
            group
            for group in evidence_groups
            if str(group.get("group_id")) not in selected_ids
            and any(alias and alias in _group_match_text(group) for alias in aliases)
        ]
        matched_group = max(
            matching_groups,
            key=lambda group: float(group.get("final_score") or 0.0),
            default=None,
        )
        if not matched_group:
            continue
        selected.append(matched_group)
        selected_ids.add(str(matched_group.get("group_id")))
        covered.append(anchor)
        debug["comparison_groups"].append({
            "anchor": anchor,
            "group_id": matched_group.get("group_id"),
            "file_node_id": matched_group.get("file_node_id"),
            "final_score": matched_group.get("final_score"),
        })

    for group in evidence_groups:
        if len(selected) >= top_k:
            break
        if str(group.get("group_id")) in selected_ids:
            continue
        selected.append(group)
        selected_ids.add(str(group.get("group_id")))

    debug["covered_anchors"] = covered
    debug["missing_comparison_targets"] = [anchor for anchor in anchors if anchor not in covered]
    for index, group in enumerate(selected[:top_k], 1):
        group["rank"] = index
    return selected[:top_k], debug


def _index_worker_loop() -> None:
    while True:
        try:
            task_id = take_next_index_task(timeout_seconds=3)
        except Exception:
            time.sleep(3)
            continue
        if not task_id:
            continue
        task = get_index_task(task_id)
        if not task:
            continue
        try:
            request = IndexRequest(**(task.get("request") or {}))
        except Exception as exc:
            update_index_task(task_id, status="failed", stage="invalid_request", error=str(exc))
            continue
        try:
            result = _run_index_file(request, task_id=task_id)
            update_index_task(task_id, status="success", stage="done", result=result, error=None)
        except Exception as exc:
            try:
                update_index_task(task_id, status="failed", stage="failed", error=str(exc))
            except Exception:
                pass


def _run_index_file(request: IndexRequest, task_id: str | None = None) -> dict[str, Any]:
    if request.operation not in {"rebuild", "delete"}:
        raise _error(400, INDEX_INVALID_OPERATION.code, "operation must be rebuild or delete", INDEX_INVALID_OPERATION.retryable, INDEX_INVALID_OPERATION.stage)
    if request.operation == "delete":
        try:
            if task_id:
                update_index_task(task_id, status="running", stage="delete")
            es = es_client()
            delete_file_documents(es, request.kb_id, request.file_node_id)
            uri, user, password = neo4j_config()
            delete_file_graph(uri, user, password, request.kb_id, request.file_node_id)
            mark_file_index_deleted(request.kb_id, request.file_node_id)
            return {
                "status": "success",
                "operation": "delete",
                "kb_id": request.kb_id,
                "file_node_id": request.file_node_id,
            }
        except Exception as exc:
            raise _error(500, "INDEX_DELETE_FAILED", str(exc), True, "delete") from exc

    index_generation = request.index_generation or next_index_generation(request.file_node_id)
    locked = False
    try:
        if not try_acquire_index_lock(request.kb_id, request.file_node_id, index_generation, request.index_options.lock_ttl_seconds):
            raise _error(409, INDEX_LOCKED.code, f"file is already indexing: {request.file_node_id}", INDEX_LOCKED.retryable, INDEX_LOCKED.stage)
        locked = True
        if task_id:
            update_index_task(task_id, status="running", stage="loading_snapshot", index_generation=index_generation)
        snapshot = load_index_snapshot(request.kb_id, request.file_node_id, request.parse_generation)
        parse_generation = snapshot["parse_generation"]
        incremental_plan = plan_incremental_index(
            snapshot,
            requested_index_generation=request.index_generation,
            incremental_reuse=request.index_options.incremental_reuse,
            force_rebuild=request.index_options.force_rebuild,
        )
        if incremental_plan["reuse_previous"]:
            reused_generation = incremental_plan["reuse_index_generation"]
            if task_id:
                update_index_task(task_id, stage="reuse_previous_index", index_generation=reused_generation)
            es_status = "reused" if request.index_options.write_es else "skipped"
            neo4j_status = "reused" if request.index_options.write_neo4j else "skipped"
            upsert_index_state(request.kb_id, request.file_node_id, parse_generation, reused_generation, "elasticsearch", es_status, 0)
            upsert_index_state(request.kb_id, request.file_node_id, parse_generation, reused_generation, "neo4j", neo4j_status, 0)
            release_index_lock(request.kb_id, request.file_node_id, index_generation, True)
            return {
                "status": "success",
                "operation": "reuse_previous",
                "kb_id": request.kb_id,
                "file_node_id": request.file_node_id,
                "parse_generation": parse_generation,
                "index_generation": reused_generation,
                "requested_index_generation": index_generation,
                "incremental_reuse": True,
                "incremental_reason": incremental_plan["reason"],
                "snapshot_hash": incremental_plan["snapshot_hash"],
                "snapshot_row_counts": incremental_plan["row_counts"],
                "indexed_chunks": 0,
                "indexed_fields": 0,
                "indexed_qa": 0,
                "indexed_section_summaries": 0,
                "indexed_anchors": 0,
                "indexed_knowledge_units": 0,
                "graph_nodes": 0,
                "graph_edges": 0,
            }
        mark_index_started(request.kb_id, request.file_node_id, parse_generation, index_generation)

        index_counts = {
            "chunk_count": 0,
            "field_count": 0,
            "qa_count": 0,
            "section_summary_count": 0,
            "anchor_count": 0,
            "knowledge_unit_count": 0,
        }
        if request.index_options.write_es:
            if task_id:
                update_index_task(task_id, stage="elasticsearch")
            es = es_client()
            delete_file_documents(es, request.kb_id, request.file_node_id, index_generation)
            index_counts = index_snapshot(es, snapshot, index_generation)
            upsert_index_state(request.kb_id, request.file_node_id, parse_generation, index_generation, "elasticsearch", "success", sum(index_counts.values()))
        else:
            upsert_index_state(request.kb_id, request.file_node_id, parse_generation, index_generation, "elasticsearch", "skipped", 0)

        community_result: dict[str, Any] | None = None
        written_graph_nodes = 0
        written_graph_edges = 0
        if request.index_options.write_neo4j:
            if task_id:
                update_index_task(task_id, stage="neo4j")
            uri, user, password = neo4j_config()
            # 优先从 anchors/units/relations 构建通用图，fallback 到旧的 graph_nodes
            anchors = snapshot.get("anchors") or []
            knowledge_units = snapshot.get("knowledge_units") or []
            relations = snapshot.get("relations") or []
            if anchors or knowledge_units or relations:
                from danbao_poc.knowledge_graph_builder import build_knowledge_graph
                profile = snapshot.get("profile") or snapshot.get("file_node", {}).get("profile") or "business_plan"
                graph_nodes, graph_edges = build_knowledge_graph(
                    profile=profile,
                    anchors=anchors,
                    knowledge_units=knowledge_units,
                    relations=relations,
                    chunks=snapshot["chunks"],
                    fields=snapshot.get("fields") or [],
                )
            else:
                graph_nodes = snapshot["graph_nodes"]
                graph_edges = snapshot["graph_edges"]
            if request.index_options.graph_delta_merge:
                sync_file_graph_delta(
                    uri,
                    user,
                    password,
                    request.kb_id,
                    request.file_node_id,
                    snapshot["file_node"]["name"],
                    parse_generation,
                    index_generation,
                    graph_nodes,
                    graph_edges,
                    snapshot["chunks"],
                )
            else:
                delete_file_graph(uri, user, password, request.kb_id, request.file_node_id)
                import_knowledge_graph(
                    uri,
                    user,
                    password,
                    request.kb_id,
                    request.file_node_id,
                    snapshot["file_node"]["name"],
                    parse_generation,
                    index_generation,
                    graph_nodes,
                    graph_edges,
                    snapshot["chunks"],
                )
            written_graph_nodes = len(graph_nodes)
            written_graph_edges = len(graph_edges)
            if request.index_options.rebuild_communities:
                community_result = rebuild_kb_communities(uri, user, password, request.kb_id)
            upsert_index_state(request.kb_id, request.file_node_id, parse_generation, index_generation, "neo4j", "success", len(graph_nodes) + len(graph_edges))
        else:
            upsert_index_state(request.kb_id, request.file_node_id, parse_generation, index_generation, "neo4j", "skipped", 0)

        if task_id:
            update_index_task(task_id, stage="switch_pointer")
        mark_index_finished(request.kb_id, request.file_node_id, parse_generation, index_generation, index_counts["chunk_count"], True)
        release_index_lock(request.kb_id, request.file_node_id, index_generation, True)
        return {
            "status": "success",
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "parse_generation": parse_generation,
            "index_generation": index_generation,
            "indexed_chunks": index_counts["chunk_count"],
            "indexed_fields": index_counts["field_count"],
            "indexed_qa": index_counts["qa_count"],
            "indexed_section_summaries": index_counts["section_summary_count"],
            "indexed_anchors": index_counts["anchor_count"],
            "indexed_knowledge_units": index_counts["knowledge_unit_count"],
            "graph_nodes": written_graph_nodes,
            "graph_edges": written_graph_edges,
            "graph_communities": community_result,
            "incremental_reuse": False,
            "incremental_reason": incremental_plan["reason"],
            "snapshot_hash": incremental_plan["snapshot_hash"],
            "snapshot_row_counts": incremental_plan["row_counts"],
        }
    except Exception as exc:
        parse_generation = request.parse_generation or ""
        upsert_index_state(request.kb_id, request.file_node_id, parse_generation, index_generation, "elasticsearch", "failed", 0, str(exc))
        upsert_index_state(request.kb_id, request.file_node_id, parse_generation, index_generation, "neo4j", "failed", 0, str(exc))
        mark_index_finished(request.kb_id, request.file_node_id, parse_generation, index_generation, 0, False, str(exc))
        if locked:
            release_index_lock(request.kb_id, request.file_node_id, index_generation, False, str(exc))
        if isinstance(exc, HTTPException):
            raise
        raise _error(500, INDEX_FAILED.code, str(exc), INDEX_FAILED.retryable, INDEX_FAILED.stage) from exc


@app.post("/api/v1/index/files")
def index_file(request: IndexRequest) -> dict[str, Any]:
    if request.async_mode:
        task_id = new_index_task_id(request.file_node_id)
        create_index_task(task_id, request.dict())
        enqueue_index_task(task_id)
        return {
            "status": "accepted",
            "task_id": task_id,
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "operation": request.operation,
        }
    return _run_index_file(request)


@app.post("/api/v1/index/kb/rebuild")
def index_kb_rebuild(request: KbRebuildRequest) -> dict[str, Any]:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM kb_file_node WHERE kb_id = %s AND del_flag = 0 AND node_type = 'file'",
                (request.kb_id,),
            )
            rows = cur.fetchall()
    file_ids = [int(row["id"]) for row in rows]
    if not file_ids:
        return {"status": "success", "kb_id": request.kb_id, "file_count": 0, "message": "no files found"}

    results = []
    for fid in file_ids:
        index_req = IndexRequest(
            kb_id=request.kb_id,
            file_node_id=fid,
            operation="rebuild",
            async_mode=request.async_mode,
            index_options=request.index_options,
        )
        if request.async_mode:
            task_id = new_index_task_id(fid)
            create_index_task(task_id, index_req.dict())
            enqueue_index_task(task_id)
            results.append({"file_node_id": fid, "status": "accepted", "task_id": task_id})
        else:
            res = _run_index_file(index_req)
            results.append({"file_node_id": fid, "status": "success", "details": res})

    return {
        "status": "success",
        "kb_id": request.kb_id,
        "file_count": len(file_ids),
        "file_ids": file_ids,
        "results": results,
    }


@app.get("/api/v1/index/tasks/{task_id}")
def get_index_task_status(task_id: str) -> dict[str, Any]:
    task = get_index_task(task_id)
    if not task:
        raise _error(404, INDEX_TASK_NOT_FOUND.code, f"index task not found: {task_id}", INDEX_TASK_NOT_FOUND.retryable, INDEX_TASK_NOT_FOUND.stage)
    return task


@app.delete("/api/v1/index/tasks/{task_id}")
def delete_index_task_api(task_id: str) -> dict[str, Any]:
    if not delete_index_task(task_id):
        raise _error(404, INDEX_TASK_NOT_FOUND.code, f"index task not found: {task_id}", INDEX_TASK_NOT_FOUND.retryable, INDEX_TASK_NOT_FOUND.stage)
    return {"status": "deleted", "task_id": task_id}


@app.post("/api/v1/index/tasks/{task_id}/retry")
def retry_index_task_api(task_id: str) -> dict[str, Any]:
    try:
        task = retry_index_task(task_id)
    except RuntimeError as exc:
        raise _error(400, "INVALID_TASK_STATUS", str(exc), False, "validate")
    if not task:
        raise _error(404, INDEX_TASK_NOT_FOUND.code, f"index task not found: {task_id}", INDEX_TASK_NOT_FOUND.retryable, INDEX_TASK_NOT_FOUND.stage)
    return task


@app.post("/api/v1/index/chunks")
def index_chunks(request: ChunkIndexRequest) -> dict[str, Any]:
    if request.operation not in {"upsert", "delete"}:
        raise _error(400, "INVALID_CHUNK_INDEX_OPERATION", "operation must be upsert or delete", False, "validate")
    if not request.chunk_ids:
        raise _error(400, "EMPTY_CHUNK_IDS", "chunk_ids must not be empty", False, "validate")
    try:
        full_snapshot = load_index_snapshot(request.kb_id, request.file_node_id, request.parse_generation)
        index_generation = request.index_generation or full_snapshot["file_node"].get("current_index_generation") or next_index_generation(request.file_node_id)
        partial_snapshot = filter_snapshot_by_chunk_ids(full_snapshot, request.chunk_ids)
        es = es_client()
        delete_chunk_documents(es, request.kb_id, request.file_node_id, request.chunk_ids)
        index_counts = {
            "chunk_count": 0,
            "field_count": 0,
            "qa_count": 0,
            "section_summary_count": 0,
            "anchor_count": 0,
            "knowledge_unit_count": 0,
        }
        if request.operation == "upsert":
            index_counts = index_rows(
                es,
                parse_generation=full_snapshot["parse_generation"],
                index_generation=index_generation,
                chunk_rows=partial_snapshot["chunks"],
                field_rows=partial_snapshot["fields"],
                qa_rows=[],
                section_summary_rows=partial_snapshot.get("section_summaries") or [],
                anchor_rows=partial_snapshot.get("anchors") or [],
                knowledge_unit_rows=partial_snapshot.get("knowledge_units") or [],
            )

        uri, user, password = neo4j_config()
        graph_rebuilt = False
        if request.operation == "delete":
            delete_file_graph(uri, user, password, request.kb_id, request.file_node_id)
            # 优先从 anchors/units/relations 构建通用图
            anchors = full_snapshot.get("anchors") or []
            knowledge_units = full_snapshot.get("knowledge_units") or []
            relations = full_snapshot.get("relations") or []
            if anchors or knowledge_units or relations:
                from danbao_poc.knowledge_graph_builder import build_knowledge_graph
                profile = full_snapshot.get("profile") or full_snapshot.get("file_node", {}).get("profile") or "business_plan"
                graph_nodes, graph_edges = build_knowledge_graph(
                    profile=profile,
                    anchors=anchors,
                    knowledge_units=knowledge_units,
                    relations=relations,
                    chunks=full_snapshot["chunks"],
                    fields=full_snapshot.get("fields") or [],
                )
            else:
                graph_nodes = full_snapshot["graph_nodes"]
                graph_edges = full_snapshot["graph_edges"]
            import_knowledge_graph(
                uri,
                user,
                password,
                request.kb_id,
                request.file_node_id,
                full_snapshot["file_node"]["name"],
                full_snapshot["parse_generation"],
                index_generation,
                graph_nodes,
                graph_edges,
                full_snapshot["chunks"],
            )
            graph_rebuilt = True
        else:
            mention_by_field_id = {row["field_id"]: row for row in partial_snapshot["mentions"]}
            chunk_by_id = {row["id"]: row for row in partial_snapshot["chunks"]}
            for field_row in partial_snapshot["fields"]:
                update_business_field(
                    uri,
                    user,
                    password,
                    request.kb_id,
                    request.file_node_id,
                    field_row["field_code"],
                    field_row["field_name_cn"],
                    field_row["value_text"],
                    chunk_by_id.get(field_row.get("source_chunk_id")),
                    mention_by_field_id.get(field_row["id"]),
                    index_generation,
                )
        mark_chunk_index_state(
            request.kb_id,
            request.file_node_id,
            request.chunk_ids,
            index_generation if request.operation == "upsert" else None,
            True,
        )
        return {
            "status": "success",
            "operation": request.operation,
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "index_generation": index_generation if request.operation == "upsert" else None,
            "indexed_chunks": index_counts["chunk_count"],
            "indexed_fields": index_counts["field_count"],
            "indexed_section_summaries": index_counts["section_summary_count"],
            "indexed_anchors": index_counts["anchor_count"],
            "indexed_knowledge_units": index_counts["knowledge_unit_count"],
            "graph_rebuilt": graph_rebuilt,
        }
    except Exception as exc:
        mark_chunk_index_state(request.kb_id, request.file_node_id, request.chunk_ids, None, False, str(exc))
        raise _error(500, "CHUNK_INDEX_FAILED", str(exc), True, "chunk_index") from exc


@app.post("/api/v1/index/qas")
def index_qas(request: QaIndexRequest) -> dict[str, Any]:
    if request.operation not in {"upsert", "delete"}:
        raise _error(400, "INVALID_QA_INDEX_OPERATION", "operation must be upsert or delete", False, "validate")
    if not request.qa_ids:
        raise _error(400, "EMPTY_QA_IDS", "qa_ids must not be empty", False, "validate")
    index_generation = request.index_generation or f"qa_{request.kb_id}"
    try:
        es = es_client()
        delete_qa_documents(es, request.kb_id, request.qa_ids)
        indexed_qa = 0
        if request.operation == "upsert":
            snapshot = load_qa_snapshot(request.kb_id, request.qa_ids)
            index_counts = index_rows(
                es,
                parse_generation="qa",
                index_generation=index_generation,
                chunk_rows=[],
                field_rows=[],
                qa_rows=snapshot["qa_rows"],
            )
            indexed_qa = index_counts["qa_count"]
        mark_qa_index_state(request.kb_id, request.qa_ids, index_generation if request.operation == "upsert" else None, True)
        return {
            "status": "success",
            "operation": request.operation,
            "kb_id": request.kb_id,
            "index_generation": index_generation if request.operation == "upsert" else None,
            "indexed_qa": indexed_qa,
        }
    except Exception as exc:
        mark_qa_index_state(request.kb_id, request.qa_ids, None, False, str(exc))
        raise _error(500, "QA_INDEX_FAILED", str(exc), True, "qa_index") from exc


@app.post("/api/v1/index/kb/qas")
def index_kb_qas(request: KbQaIndexRequest) -> dict[str, Any]:
    """Index all approved QAs for a knowledge base to ES."""
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM kb_qa_pair WHERE kb_id = %s AND audit_status = 'approved' AND del_flag = 0",
                (request.kb_id,),
            )
            rows = cur.fetchall()
    qa_ids = [int(row["id"]) for row in rows]
    if not qa_ids:
        return {"status": "success", "kb_id": request.kb_id, "qa_count": 0, "message": "no approved QAs found"}
    index_generation = request.index_generation or f"qa_{request.kb_id}"
    es = es_client()
    delete_qa_documents(es, request.kb_id, qa_ids)
    snapshot = load_qa_snapshot(request.kb_id, qa_ids)
    index_counts = index_rows(
        es,
        parse_generation="qa",
        index_generation=index_generation,
        chunk_rows=[],
        field_rows=[],
        qa_rows=snapshot["qa_rows"],
    )
    indexed_qa = index_counts["qa_count"]
    mark_qa_index_state(request.kb_id, qa_ids, index_generation, True)
    return {
        "status": "success",
        "kb_id": request.kb_id,
        "index_generation": index_generation,
        "qa_count": len(qa_ids),
        "indexed_qa": indexed_qa,
    }


@app.post("/api/v1/index/kb-qas")
def index_kb_qas_compat(request: KbQaIndexRequest) -> dict[str, Any]:
    return index_kb_qas(request)


def _generate_qa_candidates(snapshot: dict[str, Any], request: QaGenerateRequest) -> list[dict[str, Any]]:
    qa_pairs: list[dict[str, Any]] = []
    seen_questions: set[str] = set()

    def append(
        question: str,
        answer: str,
        extended_questions: list[str] | None = None,
        *,
        source_type: str | None = None,
        source_chunk_ids: list[int] | None = None,
        source_field_ids: list[int] | None = None,
        evidence_quotes: list[str] | None = None,
    ) -> None:
        question = clean_text(question)
        answer = clean_text(answer)
        if not question or not answer or question in seen_questions:
            return
        seen_questions.add(question)
        qa_pairs.append(
            {
                "question": question,
                "answer": answer[:1200],
                "extended_questions": [clean_text(item) for item in (extended_questions or []) if clean_text(item)],
                "answer_type": "auto_qa",
                "generation_source": "auto_pregenerated",
                "source_type": source_type,
                "source_chunk_ids": source_chunk_ids or [],
                "source_field_ids": source_field_ids or [],
                "evidence_quotes": [clean_text(item) for item in (evidence_quotes or []) if clean_text(item)],
                "confidence": 0.72 if source_chunk_ids or source_field_ids else 0.55,
                "priority": 0,
                "metadata": {"generator": "retrieve_service.generate_qas"},
            }
        )

    if request.include_fields:
        for field in snapshot.get("fields") or []:
            field_name = clean_text(field.get("field_name_cn") or field.get("field_code"))
            value = clean_text(field.get("value_text"))
            if not field_name or not value:
                continue
            append(
                f"{field_name}是什么？",
                value,
                [f"请问{field_name}是多少？", f"查询{field_name}"],
                source_type="field",
                source_chunk_ids=[int(field["source_chunk_id"])] if field.get("source_chunk_id") else [],
                source_field_ids=[int(field["id"])] if field.get("id") else [],
                evidence_quotes=[value],
            )
            if len(qa_pairs) >= request.max_pairs:
                return qa_pairs

    if request.include_chunks:
        for chunk in snapshot.get("chunks") or []:
            title = clean_text(chunk.get("title") or chunk.get("section_type") or "文档内容")
            answer = clean_text(chunk.get("summary") or chunk.get("content"))
            if len(answer) < 8:
                continue
            append(
                f"{title}的主要内容是什么？",
                answer,
                [f"{title}有哪些要点？", f"介绍一下{title}"],
                source_type="chunk",
                source_chunk_ids=[int(chunk["id"])] if chunk.get("id") else [],
                evidence_quotes=[answer],
            )
            if len(qa_pairs) >= request.max_pairs:
                return qa_pairs
    return qa_pairs


@app.post("/api/v1/qas/generate")
def generate_qas(request: QaGenerateRequest) -> dict[str, Any]:
    if request.max_pairs <= 0:
        raise _error(400, "INVALID_QA_GENERATE_LIMIT", "max_pairs must be greater than 0", False, "validate")
    try:
        snapshot = load_index_snapshot(request.kb_id, request.file_node_id, request.parse_generation)
        qa_pairs = _generate_qa_candidates(snapshot, request)[: min(request.max_pairs, 200)]
        qa_ids = save_qa_pairs(
            request.kb_id,
            request.file_node_id,
            qa_pairs,
            audit_status=request.audit_status,
        )
        index_result: dict[str, Any] | None = None
        if qa_ids and request.audit_status == "approved":
            index_result = index_qas(
                QaIndexRequest(
                    kb_id=request.kb_id,
                    qa_ids=qa_ids,
                    index_generation=request.index_generation,
                    operation="upsert",
                )
            )
        return {
            "status": "success",
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "parse_generation": snapshot.get("parse_generation"),
            "generated": len(qa_ids),
            "qa_ids": qa_ids,
            "audit_status": request.audit_status if request.audit_status in {"pending", "approved"} else "pending",
            "index_result": index_result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(500, "QA_GENERATE_FAILED", str(exc), True, "qa_generate") from exc


@app.post("/api/v1/index/fields/update")
def update_field(request: FieldUpdateRequest) -> dict[str, Any]:
    try:
        updated = update_field_value(
            request.kb_id,
            request.file_node_id,
            request.field_id,
            request.value_text,
            request.normalized_json,
            request.reason,
            request.reviewer,
            request.review_status,
            request.evidence_chunk_id,
            request.evidence_quote,
        )
        snapshot = load_field_snapshot(request.kb_id, request.file_node_id, request.field_id, request.parse_generation)
        index_generation = request.index_generation or snapshot["file_node"].get("current_index_generation") or next_index_generation(request.file_node_id)
        es = es_client()
        index_rows(
            es,
            parse_generation=snapshot["parse_generation"],
            index_generation=index_generation,
            chunk_rows=[],
            field_rows=snapshot["fields"],
            qa_rows=[],
        )
        uri, user, password = neo4j_config()
        field_row = snapshot["fields"][0]
        chunk_row = snapshot["chunks"][0] if snapshot["chunks"] else None
        mention_row = snapshot["mentions"][0] if snapshot["mentions"] else None
        update_business_field(
            uri,
            user,
            password,
            request.kb_id,
            request.file_node_id,
            field_row["field_code"],
            field_row["field_name_cn"],
            field_row["value_text"],
            chunk_row,
            mention_row,
            index_generation,
        )
        return {
            "status": "success",
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "field_id": request.field_id,
            "index_generation": index_generation,
            "field": updated,
        }
    except Exception as exc:
        raise _error(500, "FIELD_UPDATE_FAILED", str(exc), True, "field_update") from exc


@app.get("/api/v1/review/files/{file_node_id}/extractions")
def get_review_extractions(kb_id: int, file_node_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    try:
        return load_review_extractions(kb_id, file_node_id, parse_generation)
    except Exception as exc:
        raise _error(500, "REVIEW_EXTRACTIONS_FAILED", str(exc), True, "review_extractions") from exc


@app.get("/api/v1/review/files/{file_node_id}/char-map")
def get_review_char_map(kb_id: int, file_node_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    try:
        return load_char_map(kb_id, file_node_id, parse_generation)
    except Exception as exc:
        raise _error(500, "REVIEW_CHAR_MAP_FAILED", str(exc), True, "review_char_map") from exc


@app.post("/api/v1/review/fields/{field_id}")
def review_field(field_id: int, request: ReviewFieldRequest) -> dict[str, Any]:
    return update_field(
        FieldUpdateRequest(
            kb_id=request.kb_id,
            file_node_id=request.file_node_id,
            field_id=field_id,
            value_text=request.value_text,
            normalized_json=request.normalized_json,
            parse_generation=request.parse_generation,
            index_generation=request.index_generation,
            reason=request.reason,
            reviewer=request.reviewer,
            review_status=request.review_status,
            evidence_chunk_id=request.evidence_chunk_id,
            evidence_quote=request.evidence_quote,
        )
    )


@app.post("/api/v1/review/fields:batch")
def review_fields_batch(request: BatchReviewFieldsRequest) -> dict[str, Any]:
    if not request.field_updates:
        raise _error(400, "EMPTY_FIELD_UPDATES", "field_updates must not be empty", False, "validate")
    results: list[dict[str, Any]] = []
    for item in request.field_updates:
        results.append(
            update_field(
                FieldUpdateRequest(
                    kb_id=request.kb_id,
                    file_node_id=request.file_node_id,
                    field_id=item.field_id,
                    value_text=item.value_text,
                    normalized_json=item.normalized_json,
                    parse_generation=request.parse_generation,
                    index_generation=request.index_generation,
                    reason=item.reason,
                    reviewer=request.reviewer,
                    review_status=item.review_status,
                    evidence_chunk_id=item.evidence_chunk_id,
                    evidence_quote=item.evidence_quote,
                )
            )
        )
    return {
        "status": "success",
        "kb_id": request.kb_id,
        "file_node_id": request.file_node_id,
        "updated_count": len(results),
        "results": results,
    }


@app.post("/api/v1/review/chunks/{chunk_id}")
def review_chunk_endpoint(chunk_id: int, request: ReviewChunkRequest) -> dict[str, Any]:
    try:
        reviewed = review_chunk(
            kb_id=request.kb_id,
            file_node_id=request.file_node_id,
            chunk_id=chunk_id,
            action=request.action,
            content=request.content,
            summary=request.summary,
            reviewer=request.reviewer,
            reason=request.reason,
        )
        index_result: dict[str, Any] | None = None
        if request.sync_index:
            index_result = index_chunks(
                ChunkIndexRequest(
                    kb_id=request.kb_id,
                    file_node_id=request.file_node_id,
                    chunk_ids=[chunk_id],
                    parse_generation=request.parse_generation,
                    index_generation=request.index_generation,
                    operation="delete" if request.action == "reject" else "upsert",
                )
            )
        return {
            "status": "success",
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "chunk": reviewed,
            "index_result": index_result,
        }
    except Exception as exc:
        raise _error(500, REVIEW_FAILED.code, str(exc), REVIEW_FAILED.retryable, REVIEW_FAILED.stage) from exc


@app.post("/api/v1/chunks/{chunk_id}/approve")
def approve_chunk_compat(chunk_id: int, request: ReviewChunkRequest) -> dict[str, Any]:
    request.action = "approve"
    return review_chunk_endpoint(chunk_id, request)


@app.post("/api/v1/chunks/{chunk_id}/reject")
def reject_chunk_compat(chunk_id: int, request: ReviewChunkRequest) -> dict[str, Any]:
    request.action = "reject"
    return review_chunk_endpoint(chunk_id, request)


@app.post("/api/v1/review/files/{file_node_id}")
def review_file_endpoint(file_node_id: int, request: ReviewFileRequest) -> dict[str, Any]:
    try:
        reviewed = review_file(
            kb_id=request.kb_id,
            file_node_id=file_node_id,
            action=request.action,
            reviewer=request.reviewer,
            reason=request.reason,
        )
        index_result: dict[str, Any] | None = None
        if request.sync_index:
            index_result = index_file(
                IndexRequest(
                    kb_id=request.kb_id,
                    file_node_id=file_node_id,
                    operation="delete" if request.action == "reject" else "rebuild",
                )
            )
        return {
            "status": "success",
            "file": reviewed,
            "index_result": index_result,
        }
    except Exception as exc:
        raise _error(500, REVIEW_FAILED.code, str(exc), REVIEW_FAILED.retryable, REVIEW_FAILED.stage) from exc


@app.get("/api/v1/files/{file_node_id}/sections")
def get_section_tree(file_node_id: int, kb_id: int) -> dict[str, Any]:
    """Return the hierarchical section tree for a parsed file."""
    return load_section_tree(kb_id, file_node_id)


@app.post("/api/v1/retrieve/tables")
def retrieve_tables(request: TableRetrieveRequest) -> dict[str, Any]:
    try:
        file_scope = request.allowed_file_ids or request.file_node_ids
        rows = search_file_tables(
            request.kb_id,
            request.query,
            file_scope or None,
            request.parse_generation,
            request.top_k,
        )
        return {
            "kb_id": request.kb_id,
            "query": request.query,
            "results": rows,
            "debug": {
                "file_node_ids": file_scope,
                "result_count": len(rows),
                "mode": "readonly_keyword_table_search",
            },
        }
    except Exception as exc:
        raise _error(500, TABLE_RETRIEVE_FAILED.code, str(exc), TABLE_RETRIEVE_FAILED.retryable, TABLE_RETRIEVE_FAILED.stage) from exc


@app.post("/api/v1/retrieve/query")
def retrieve(request: RetrieveRequest) -> dict[str, Any]:
    try:
        request_options = request.options or {}
        kb_ids = _effective_kb_ids(request)
        if not kb_ids:
            raise _error(400, "INVALID_KB_SCOPE", "kb_id or kb_ids is required", False, "validate")
        primary_kb_id = kb_ids[0]
        filter_file_ids = []
        if request.filters:
            raw_file_ids = request.filters.get("file_node_ids") or request.filters.get("allowed_file_ids") or request.filters.get("file_node_id")
            if isinstance(raw_file_ids, list):
                filter_file_ids = [int(item) for item in raw_file_ids]
            elif raw_file_ids:
                filter_file_ids = [int(raw_file_ids)]
        effective_allowed_file_ids = request.allowed_file_ids or request.file_node_ids or filter_file_ids
        with timer("danbao_retrieve_total"):
            active_scopes = {kb_id: load_active_index_scope(kb_id, effective_allowed_file_ids or None) for kb_id in kb_ids}
        active_file_ids_by_kb = {kb_id: scope["file_node_ids"] for kb_id, scope in active_scopes.items()}
        active_index_generations_by_kb = {kb_id: scope["index_generations"] for kb_id, scope in active_scopes.items()}
        active_file_ids = sorted({item for rows in active_file_ids_by_kb.values() for item in rows})
        active_index_generations = sorted({item for rows in active_index_generations_by_kb.values() for item in rows})
        file_meta_by_id = _load_active_file_meta(active_file_ids_by_kb)
        profile, profile_resolution_debug = _resolve_retrieve_profile(request_options, file_meta_by_id)
        mysql_retrieval_config = load_retrieval_profile_config(primary_kb_id, profile)
        cache_context = {
            "kb_ids": kb_ids,
            "active_file_ids": active_file_ids,
            "active_index_generations": active_index_generations,
            "profile": profile,
        }
        cache_payload = {
            **request.dict(),
            "_response_content_version": "graph_opt_in_v2",
            "_resolved_profile": profile,
            "_mysql_retrieval_config": mysql_retrieval_config,
            "_active_file_ids": active_file_ids,
            "_active_index_generations": active_index_generations,
        }
        cached = get_cached(cache_payload)
        if cached is not None:
            inc("danbao_retrieve_cache_hit_total")
            return _unquote_all(cached)
        inc("danbao_retrieve_cache_miss_total")
        profile_filters = profile_filter_values(profile)
        with timer("danbao_query_understanding"):
            query_assist_enabled = _bool_option(request_options, ["query_assist.enabled", "enable_query_optimization", "query_optimization", "optimize_query"], False)
            heuristic_understanding = heuristic_query_understanding(request.query, request.top_k, profile)
            if query_assist_enabled:
                use_model_understanding, rewrite_guard_debug = _query_rewrite_guard(request.query, request_options, heuristic_understanding)
            else:
                use_model_understanding, rewrite_guard_debug = False, {"enabled": False, "use_model": False, "reason": "query_assist_disabled"}
            if query_assist_enabled and use_model_understanding:
                understanding = cached_understand_query(request.query, request.top_k, profile=profile, cache_context=cache_context)
                understanding["query_rewrite_guard"] = rewrite_guard_debug
            else:
                understanding = heuristic_understanding
                understanding["query_rewrite_guard"] = rewrite_guard_debug
        plan = RetrievalPlanBuilder().build(profile, understanding, request.retrieval_method, request_options)
        # Neo4j retrieval is deliberately opt-in.  The planner may still describe
        # graph as a useful route, but it must never change existing callers'
        # results unless the request explicitly asks for it.
        graph_global_requested = _bool_option(
            request_options,
            ["graph_global", "graph.global", "graph.global_enabled", "routes.graph_global_enabled"],
            False,
        )
        graph_requested = graph_global_requested or (
            bool(request.graph)
            if request.graph is not None
            else _route_enabled(request_options, "graph", False)
        )
        retrieve_modes = [
            route
            for route in ["qa", "structured", "section_summary", "graph", "bm25", "vector"]
            if (
                graph_requested
                if route == "graph"
                else _route_enabled(request_options, route, route in plan.retrieve_modes)
            )
        ]
        if not retrieve_modes:
            retrieve_modes = ["qa", "structured", "section_summary", "bm25", "vector"]
        elif graph_requested and not any(route != "graph" for route in retrieve_modes):
            # A graph expansion needs evidence seeds.  Keep this fallback narrow
            # and local to explicit graph-only requests.
            retrieve_modes.extend(["bm25", "vector"])
        fusion_config = resolve_weighted_rrf_config(
            profile,
            retrieve_modes,
            mysql_config=mysql_retrieval_config,
            request_options=request_options,
        )
        if not active_index_generations and "qa" not in retrieve_modes:
            is_debug = _is_debug_mode(request_options)
            response: dict[str, Any] = {
                "kb_id": primary_kb_id,
                "kb_ids": kb_ids,
                "query": request.query,
                "confidence": 0.0,
                "confidence_label": "low",
                "llm_context": "",
                "results": [],
                "citations": [],
                "debug": None,
            }
            if is_debug:
                response.update({
                    "query_understanding": understanding,
                    "retrieval_plan": plan.as_dict(),
                    "fusion_config": fusion_config,
                    "confidence_factors": {},
                    "evidence_groups": [],
                    "answer_context": {"protocol": "", "citation_style": "", "instruction": "", "blocks": [], "prompt_context": ""},
                    "context_plan": [],
                    "context_chunks": [],
                    "debug": {
                        "allowed_file_ids": effective_allowed_file_ids,
                        "active_file_ids": [],
                        "active_index_generations": [],
                        "qa_hits": 0,
                        "structured_hits": 0,
                        "section_summary_hits": 0,
                        "graph_hits": 0,
                        "bm25_hits": 0,
                        "vector_hits": 0,
                        "candidate_count": 0,
                        "profile": profile,
                        "profile_resolution": profile_resolution_debug,
                        "warning": "no active indexed files matched the request scope",
                    },
                })
            set_cached(cache_payload, response)
            return response
        effective_query = understanding.get("query_rewrite") or request.query
        expanded_terms = [str(term) for term in (understanding.get("expanded_terms") or []) if str(term).strip()]
        uri, user, password = neo4j_config()
        es = es_client()
        recall_top_k = max(request.top_k, int(request.top_k * float(fusion_config.get("recall_multiplier") or 4)))
        chunk_type_filters, return_mode = _chunk_type_filters_from_options(request_options)
        section_type_filters = request_options.get("section_types") or request_options.get("section_type_filters")
        section_type_filters = [str(item) for item in section_type_filters] if isinstance(section_type_filters, list) else None
        term_weight_options = _dict_option(request_options, "term_weight")
        # Product-name scoped file filtering: narrow search to files whose names match scope anchors
        scope_anchors = [str(s) for s in (understanding.get("scope_anchor_candidates") or []) if str(s).strip()]
        scope_filter_options = _dict_option(request_options, "scope_anchor_filter")
        scope_filter_enabled = _bool_option(request_options, ["scope_anchor_filter.enabled"], True)
        scope_filter_strict = _bool_option(request_options, ["scope_anchor_filter.strict"], True)
        # When query contains both product name AND generic field alias,
        # relax strict scope to avoid filtering out correct results from other products
        if scope_filter_strict and scope_anchors and understanding.get("target_field_codes"):
            scope_filter_strict = False
        if scope_filter_options:
            scope_filter_enabled = bool(scope_filter_options.get("enabled", scope_filter_enabled))
            scope_filter_strict = bool(scope_filter_options.get("strict", scope_filter_strict))
        scoped_file_ids_by_kb, scope_anchor_filter_debug = _resolve_scope_anchor_file_filter(
            kb_ids=kb_ids,
            active_file_ids_by_kb=active_file_ids_by_kb,
            file_meta_by_id=file_meta_by_id,
            scope_anchors=scope_anchors,
            enabled=scope_filter_enabled,
            strict=scope_filter_strict,
        )
        cross_doc_query = any(term in request.query for term in ["哪些方案", "哪些文件", "哪些产品", "哪些制度"])
        compare_multi_anchor_query = bool(understanding.get("comparison_query")) or (
            len(scope_anchors) >= 2 and any(term in request.query for term in ["对比", "区别", "比较", "分别", "各自", "和", "与"])
        )
        comparison_anchors = [
            str(item)
            for item in ((understanding.get("comparison_anchors") or scope_anchors) if compare_multi_anchor_query else [])
            if str(item).strip()
        ]
        if compare_multi_anchor_query:
            recall_top_k = max(recall_top_k, request.top_k * max(6, len(comparison_anchors) * 4))
        graph_error: str | None = None
        recall_errors: dict[str, str] = {}
        recall_durations_ms: dict[str, int] = {}

        def _file_ids_for(kb_id: int, channel: str) -> list[int] | None:
            """Return scoped file IDs if product name detected, else original scope.

            Scope anchor filtering now applies to ALL channels (including graph
            and qa) so that product-specific queries like "农贸贷的反担保" don't
            accidentally match results from other products via unscoped channels.
            """
            scoped = scoped_file_ids_by_kb.get(kb_id)
            if scoped:
                if channel in ("graph", "qa"):
                    # For graph/qa, merge scoped IDs with active IDs so we don't
                    # miss KB-level QAs that have no file_node_id, but still
                    # prefer scoped files when available.
                    active = active_file_ids_by_kb.get(kb_id) or []
                    return sorted(set(scoped) | set(active)) if not active else scoped
                return scoped
            return active_file_ids_by_kb.get(kb_id) or None

        with timer("danbao_retrieve_recall"):
            recall_tasks: dict[str, Any] = {}
            if "qa" in retrieve_modes:
                recall_tasks["qa"] = lambda: [
                    row
                    for kb_id in kb_ids
                    for row in search_qa(
                        es,
                        kb_id,
                        effective_query,
                        recall_top_k,
                        _file_ids_for(kb_id, "qa"),
                        active_index_generations_by_kb.get(kb_id) or None,
                        profiles=None,
                        term_weight_options=term_weight_options,
                        expanded_terms=expanded_terms,
                    )
                ]
            if "structured" in retrieve_modes:
                include_units = _bool_option(request_options, ["structured.include_units", "include_knowledge_units"], True)
                include_anchors = _bool_option(request_options, ["structured.include_anchors", "include_anchors"], True)
                recall_tasks["structured"] = lambda: [
                    row
                    for kb_id in kb_ids
                    for row in search_structured(
                        es,
                        kb_id,
                        effective_query,
                        _file_ids_for(kb_id, "structured"),
                        recall_top_k,
                        active_index_generations_by_kb.get(kb_id) or None,
                        profiles=profile_filters,
                        include_units=include_units,
                        include_anchors=include_anchors,
                        term_weight_options=term_weight_options,
                        expanded_terms=expanded_terms,
                    )
                ]
            if "section_summary" in retrieve_modes:
                recall_tasks["section_summary"] = lambda: [
                    row
                    for kb_id in kb_ids
                    for row in search_section_summary(
                        es,
                        kb_id,
                        effective_query,
                        _file_ids_for(kb_id, "section_summary"),
                        recall_top_k,
                        active_index_generations_by_kb.get(kb_id) or None,
                        profiles=profile_filters,
                        term_weight_options=term_weight_options,
                        expanded_terms=expanded_terms,
                    )
                ]
            if "bm25" in retrieve_modes:
                recall_tasks["bm25"] = lambda: [
                    row
                    for kb_id in kb_ids
                    for row in search_bm25(
                        es,
                        kb_id,
                        effective_query,
                        _file_ids_for(kb_id, "bm25"),
                        recall_top_k,
                        active_index_generations_by_kb.get(kb_id) or None,
                        profiles=profile_filters,
                        chunk_types=chunk_type_filters,
                        section_types=section_type_filters,
                        term_weight_options=term_weight_options,
                        expanded_terms=expanded_terms,
                    )
                ]
            if "vector" in retrieve_modes:
                recall_tasks["vector"] = lambda: [
                    row
                    for kb_id in kb_ids
                    for row in search_vector(
                        es,
                        kb_id,
                        effective_query,
                        _file_ids_for(kb_id, "vector"),
                        recall_top_k,
                        active_index_generations_by_kb.get(kb_id) or None,
                        profiles=profile_filters,
                        chunk_types=chunk_type_filters,
                        section_types=section_type_filters,
                        embedding_cache_context={**cache_context, "kb_id": kb_id},
                    )
                ]
            qa_hits: list[dict[str, Any]] = []
            structured_hits: list[dict[str, Any]] = []
            section_summary_hits: list[dict[str, Any]] = []
            graph_hits: list[dict[str, Any]] = []
            bm25_hits: list[dict[str, Any]] = []
            vector_hits: list[dict[str, Any]] = []
            hit_targets = {
                "qa": qa_hits,
                "structured": structured_hits,
                "section_summary": section_summary_hits,
                "bm25": bm25_hits,
                "vector": vector_hits,
            }
            if recall_tasks:
                with ThreadPoolExecutor(max_workers=min(6, len(recall_tasks))) as pool:
                    future_to_route = {}
                    for route, task in recall_tasks.items():
                        started_at = time.perf_counter()

                        def _timed(task=task, route=route, started_at=started_at):
                            rows = task()
                            recall_durations_ms[route] = int((time.perf_counter() - started_at) * 1000)
                            return rows

                        future_to_route[pool.submit(_timed)] = route
                    for future in as_completed(future_to_route):
                        route = future_to_route[future]
                        try:
                            hit_targets[route].extend(future.result())
                        except Exception as exc:
                            recall_errors[route] = str(exc)
                            if route == "graph":
                                graph_error = str(exc)
                                logger.warning("graph direct hit failed: %s", exc)
                            else:
                                logger.warning("%s recall failed: %s", route, exc)
        route_candidates = {
            "qa": normalize_candidates("qa", qa_hits),
            "structured": normalize_candidates("structured", structured_hits),
            "section_summary": normalize_candidates("section_summary", section_summary_hits),
            "graph": [],
            "bm25": normalize_candidates("bm25", bm25_hits),
            "vector": normalize_candidates("vector", vector_hits),
        }
        candidates, fusion_debug = weighted_rrf_fuse(
            {route: rows for route, rows in route_candidates.items() if route in retrieve_modes},
            fusion_config=fusion_config,
            top_k=recall_top_k,
        )
        retry_options = _retry_options(request_options)
        retry_debug: dict[str, Any] = {"enabled": bool(retry_options.get("enabled")), "attempted": False}
        should_retry, retry_reason = _needs_retrieve_retry(candidates, retry_options)
        if should_retry:
            retry_debug.update({"attempted": True, "reason": retry_reason, "before_candidate_count": len(candidates)})
            retry_query = request.query if effective_query != request.query else effective_query
            retry_top_k = max(recall_top_k, request.top_k * int(retry_options.get("top_k_multiplier") or 2))
            retry_rows_by_route: dict[str, list[dict[str, Any]]] = {}
            try:
                if retry_options.get("include_bm25", True):
                    retry_rows_by_route["bm25"] = [
                        row
                        for kb_id in kb_ids
                        for row in search_bm25(
                            es,
                            kb_id,
                            retry_query,
                            active_file_ids_by_kb.get(kb_id) or None,
                            retry_top_k,
                            active_index_generations_by_kb.get(kb_id) or None,
                            profiles=profile_filters,
                            chunk_types=None,
                            section_types=None,
                            term_weight_options={**term_weight_options, "refresh": bool(term_weight_options.get("refresh", False))},
                            expanded_terms=expanded_terms,
                        )
                    ]
                if retry_options.get("include_structured", True) and "structured" in retrieve_modes:
                    retry_rows_by_route["structured"] = [
                        row
                        for kb_id in kb_ids
                        for row in search_structured(
                            es,
                            kb_id,
                            retry_query,
                            active_file_ids_by_kb.get(kb_id) or None,
                            retry_top_k,
                            active_index_generations_by_kb.get(kb_id) or None,
                            profiles=profile_filters,
                            include_units=True,
                            include_anchors=True,
                            term_weight_options=term_weight_options,
                            expanded_terms=expanded_terms,
                        )
                    ]
                if retry_options.get("include_section_summary", True) and "section_summary" in retrieve_modes:
                    retry_rows_by_route["section_summary"] = [
                        row
                        for kb_id in kb_ids
                        for row in search_section_summary(
                            es,
                            kb_id,
                            retry_query,
                            active_file_ids_by_kb.get(kb_id) or None,
                            retry_top_k,
                            active_index_generations_by_kb.get(kb_id) or None,
                            profiles=profile_filters,
                            term_weight_options=term_weight_options,
                            expanded_terms=expanded_terms,
                        )
                    ]
                for route, rows in retry_rows_by_route.items():
                    route_candidates[route] = _merge_route_rows(route_candidates.get(route) or [], normalize_candidates(route, rows))
                candidates, retry_fusion_debug = weighted_rrf_fuse(
                    {route: rows for route, rows in route_candidates.items() if route in retrieve_modes},
                    fusion_config=fusion_config,
                    top_k=recall_top_k,
                )
                retry_debug.update(
                    {
                        "query": retry_query,
                        "retry_top_k": retry_top_k,
                        "route_counts": {route: len(rows) for route, rows in retry_rows_by_route.items()},
                        "after_candidate_count": len(candidates),
                        "fusion": retry_fusion_debug,
                    }
                )
            except Exception as exc:
                retry_debug.update({"error": str(exc)})
                logger.warning("retrieve retry failed: %s", exc)

        # Stage 2: expand only from chunks already recalled by ES/structured
        # routes.  This prevents the old unanchored MATCH ... LIMIT behaviour
        # from injecting arbitrary graph facts into otherwise stable results.
        graph_debug: dict[str, Any] = {
            "requested": graph_requested,
            "global_requested": graph_global_requested,
            "strategy": "seed_chunk_expansion_v2",
            "seed_count": 0,
            "max_hops": 0,
            "max_nodes_per_seed": 0,
            "max_total_nodes": 0,
            "min_confidence": 0.0,
        }
        if graph_requested and "graph" in retrieve_modes and candidates:
            graph_seed_top_k = max(1, min(int(_float_option(request_options, ["graph_seed_top_k", "graph.seed_top_k"], 8)), 30))
            graph_max_hops = max(1, min(int(_float_option(request_options, ["graph_max_hops", "graph.max_hops"], 1)), 2))
            graph_max_nodes_per_seed = max(1, min(int(_float_option(request_options, ["graph_max_nodes_per_seed", "graph.max_nodes_per_seed"], 8)), 50))
            graph_max_total_nodes = max(1, min(int(_float_option(request_options, ["graph_max_total_nodes", "graph.max_total_nodes"], max(recall_top_k * 4, recall_top_k))), 200))
            graph_min_confidence = max(0.0, min(_float_option(request_options, ["graph_min_confidence", "graph.min_confidence"], 0.0), 1.0))
            graph_debug.update({
                "max_hops": graph_max_hops,
                "max_nodes_per_seed": graph_max_nodes_per_seed,
                "max_total_nodes": graph_max_total_nodes,
                "min_confidence": graph_min_confidence,
            })
            graph_started_at = time.perf_counter()
            try:
                graph_hits = [
                    row
                    for kb_id in kb_ids
                    for row in graph_expand_query(
                        uri,
                        user,
                        password,
                        kb_id,
                        effective_query,
                        [row for row in candidates if int(row.get("kb_id") or kb_id) == kb_id],
                        _file_ids_for(kb_id, "graph"),
                        active_index_generations_by_kb.get(kb_id) or None,
                        recall_top_k,
                        profile=profile,
                        seed_top_k=graph_seed_top_k,
                        max_hops=graph_max_hops,
                        max_nodes_per_seed=graph_max_nodes_per_seed,
                        max_total_nodes=graph_max_total_nodes,
                        min_confidence=graph_min_confidence,
                    )
                ]
                route_candidates["graph"] = normalize_candidates("graph", graph_hits)
                graph_debug["seed_count"] = sum(
                    1 for row in candidates[:graph_seed_top_k] if row.get("chunk_id") or row.get("primary_chunk_id")
                )
                graph_debug["hit_count"] = len(graph_hits)
                candidates, graph_fusion_debug = weighted_rrf_fuse(
                    {route: rows for route, rows in route_candidates.items() if route in retrieve_modes},
                    fusion_config=fusion_config,
                    top_k=recall_top_k,
                )
                graph_debug["fusion"] = graph_fusion_debug
            except Exception as exc:
                graph_error = str(exc)
                recall_errors["graph"] = str(exc)
                graph_debug["error"] = str(exc)
                logger.warning("seeded graph expansion failed: %s", exc)
            finally:
                recall_durations_ms["graph"] = int((time.perf_counter() - graph_started_at) * 1000)
        if graph_requested and graph_global_requested and "graph" in retrieve_modes:
            global_started_at = time.perf_counter()
            try:
                global_top_k = max(1, min(int(_float_option(request_options, ["graph_global_top_k", "graph.global_top_k"], 8)), 30))
                global_hits = [
                    row
                    for kb_id in kb_ids
                    for row in search_community_reports(
                        uri,
                        user,
                        password,
                        kb_id,
                        effective_query,
                        top_k=global_top_k,
                    )
                ]
                graph_hits.extend(global_hits)
                route_candidates["graph"] = normalize_candidates("graph", graph_hits)
                candidates, global_fusion_debug = weighted_rrf_fuse(
                    {route: rows for route, rows in route_candidates.items() if route in retrieve_modes},
                    fusion_config=fusion_config,
                    top_k=recall_top_k,
                )
                graph_debug["global_hit_count"] = len(global_hits)
                graph_debug["global_top_k"] = global_top_k
                graph_debug["global_fusion"] = global_fusion_debug
            except Exception as exc:
                graph_debug["global_error"] = str(exc)
                recall_errors["graph_global"] = str(exc)
                logger.warning("global graph retrieval failed: %s", exc)
            finally:
                recall_durations_ms["graph_global"] = int((time.perf_counter() - global_started_at) * 1000)
        document_match_boost = _float_option(request_options, ["document_match_boost"], 0.30)
        document_mismatch_penalty = _float_option(request_options, ["document_mismatch_penalty"], 0.55)
        candidates, document_scoring_debug = _apply_document_and_field_scoring(
            candidates,
            scope_anchors=scope_anchors,
            file_meta_by_id=file_meta_by_id,
            target_field_codes=understanding.get("target_field_codes") or [],
            document_match_boost=document_match_boost,
            document_mismatch_penalty=document_mismatch_penalty,
        )
        similarity_threshold = _float_option(request_options, ["similarity_threshold"], 0.0)
        candidates, threshold_debug = filter_by_similarity_threshold(candidates, similarity_threshold)
        with timer("danbao_retrieve_rerank"):
            rerank_enabled = _bool_option(request_options, ["rerank.enabled", "use_rerank", "enable_rerank"], True)
            rerank_top_n = int(_float_option(request_options, ["rerank.top_n", "rerank_top_n"], max(request.top_k, 30)))
            rerank_score_weight = _float_option(request_options, ["rerank.score_weight", "rerank_score_weight"], 0.55)
            rerank_top_n = max(request.top_k, min(rerank_top_n, max(len(candidates), request.top_k)))
            results = rerank_candidates(
                request.query,
                candidates[:rerank_top_n],
                rerank_top_n if rerank_enabled else request.top_k,
                understanding.get("target_field_codes") or [],
                understanding.get("keywords") or [],
                profile=profile,
                use_rerank=rerank_enabled,
                rerank_score_weight=rerank_score_weight if rerank_enabled else 0.0,
            )
        results = results[:request.top_k]
        evidence_groups = build_evidence_groups(results, request.top_k)
        chunk_ids_by_kb: dict[int, list[int]] = {}
        for row in results:
            if row.get("chunk_id") and row.get("kb_id"):
                chunk_ids_by_kb.setdefault(int(row["kb_id"]), []).append(int(row["chunk_id"]))
        chunk_ids = [item for rows in chunk_ids_by_kb.values() for item in rows]
        evidence_groups = _enrich_evidence_groups(
            evidence_groups,
            active_file_ids_by_kb=active_file_ids_by_kb,
            active_index_generations_by_kb=active_index_generations_by_kb,
            options=request_options,
            query=request.query,
            understanding=understanding,
        )
        diversity_options = request_options
        if cross_doc_query and not _dict_option(request_options, "diversity") and "max_groups_per_file" not in request_options:
            diversity_options = {**request_options, "diversity": {"max_groups_per_file": 1}}
        evidence_groups, diversity_debug = _apply_evidence_diversity(evidence_groups, diversity_options, request.top_k)
        diversity_debug["auto_cross_doc_diversity"] = bool(cross_doc_query)
        diversity_debug["compare_multi_anchor_query"] = bool(compare_multi_anchor_query)
        comparison_debug: dict[str, Any] = {"enabled": False}
        if compare_multi_anchor_query:
            evidence_groups, comparison_debug = _apply_comparison_anchor_coverage(
                evidence_groups,
                comparison_anchors=comparison_anchors,
                file_meta_by_id=file_meta_by_id,
                top_k=request.top_k,
            )
        confidence_payload = compute_retrieval_confidence(evidence_groups, top_n=max(request.top_k, 1))
        graph_plan: list[dict[str, Any]] = []
        use_graph_context_plan = _bool_option(
            request_options,
            ["use_graph_context_plan", "graph_context_plan", "graph_context_planning"],
            False,
        )
        if use_graph_context_plan and plan.expand_context and chunk_ids and "graph" in retrieve_modes:
            try:
                graph_plan = graph_context_plan(
                    uri,
                    user,
                    password,
                    primary_kb_id,
                    chunk_ids,
                    active_file_ids,
                    active_index_generations,
                    max_sibling_chunks=plan.context_max_chunks,
                )
            except Exception as exc:
                logger.warning("graph context plan failed: %s", exc)
        context_chunks = (
            [
                row
                for kb_id, scoped_chunk_ids in chunk_ids_by_kb.items()
                for row in load_related_chunks(
                    kb_id,
                    active_file_ids_by_kb.get(kb_id) or [],
                    scoped_chunk_ids,
                    active_index_generations_by_kb.get(kb_id) or None,
                    plan.context_relation_types,
                    plan.context_max_chunks,
                )
            ]
            if plan.expand_context and chunk_ids
            else []
        )
        graph_context_chunk_ids = sorted({int(item) for plan_item in graph_plan for item in (plan_item.get("sibling_chunk_ids") or []) if item})
        if graph_context_chunk_ids:
            existing_context_ids = {row.get("chunk_id") for row in context_chunks}
            context_chunks.extend(
                row for row in load_chunks_by_ids(
                    primary_kb_id,
                    active_file_ids,
                    graph_context_chunk_ids,
                    active_index_generations,
                    plan.context_max_chunks,
                )
                if row.get("chunk_id") not in existing_context_ids
            )
        citations = build_citations(evidence_groups, max_items=max(request.top_k, 12))
        answer_context = build_answer_context_protocol(evidence_groups, citations, max_items=max(request.top_k, 12))

        # Flatten evidence_group context into results so Java clients see parent/child context
        _flatten_context_into_results(results, evidence_groups)

        is_debug = _is_debug_mode(request_options)
        response: dict[str, Any] = {
            "kb_id": primary_kb_id,
            "kb_ids": kb_ids,
            "query": request.query,
            "confidence": confidence_payload["confidence"],
            "confidence_label": confidence_payload["confidence_label"],
            "llm_context": _build_llm_context(evidence_groups, top_k=request.top_k, file_meta_by_id=file_meta_by_id),
            "results": _simplify_results(results),
            "citations": citations,
            "debug": None,
        }
        if is_debug:
            response.update({
                "confidence_factors": confidence_payload["confidence_factors"],
                "query_understanding": understanding,
                "retrieval_plan": plan.as_dict(),
                "fusion_config": fusion_config,
                "evidence_groups": evidence_groups,
                "answer_context": answer_context,
                "context_plan": graph_plan,
                "context_chunks": context_chunks,
                "debug": {
                    "allowed_file_ids": effective_allowed_file_ids,
                    "active_scopes": active_scopes,
                    "active_file_ids": active_file_ids,
                    "active_index_generations": active_index_generations,
                    "profile": profile,
                    "profile_filters": profile_filters,
                    "return_mode": return_mode,
                    "chunk_type_filters": chunk_type_filters,
                    "qa_hits": len(qa_hits),
                    "structured_hits": len(structured_hits),
                    "section_summary_hits": len(section_summary_hits),
                    "graph_hits": len(graph_hits),
                    "graph_requested": graph_requested,
                    "graph_expansion": graph_debug,
                    "graph_error": graph_error,
                    "bm25_hits": len(bm25_hits),
                    "vector_hits": len(vector_hits),
                    "candidate_count": len(candidates),
                    "fusion": fusion_debug,
                    "retry": retry_debug,
                    "scope_anchor_filter": scope_anchor_filter_debug,
                    "document_scoring": document_scoring_debug,
                    "profile_resolution": profile_resolution_debug,
                    "similarity_threshold": threshold_debug,
                    "diversity": diversity_debug,
                    "comparison": comparison_debug,
                    "confidence": confidence_payload["confidence_factors"],
                    "recall_top_k": recall_top_k,
                    "recall_errors": recall_errors,
                    "recall_durations_ms": recall_durations_ms,
                    "route_candidate_counts": {route: len(rows) for route, rows in route_candidates.items()},
                    "route_reason": plan.as_dict().get("route_reason") or understanding.get("route_reason") or {},
                    "query_optimization_enabled": _bool_option(request_options, ["query_assist.enabled", "enable_query_optimization", "query_optimization", "optimize_query"], False),
                    "query_rewrite_guard": understanding.get("query_rewrite_guard"),
                    "rerank_enabled": rerank_enabled,
                    "rerank_top_n": rerank_top_n,
                    "rerank_score_weight": rerank_score_weight,
                    "graph_context_plan_enabled": use_graph_context_plan,
                    "graph_context_plan_count": len(graph_plan),
                    "context_chunk_count": len(context_chunks),
                    "cache_hit": False,
                },
            })
        response = _unquote_all(response)
        set_cached(cache_payload, response)
        return response
    except Exception as exc:
        import traceback as _tb
        tb = _tb.format_exc()
        logger.error("RETRIEVE CRASH:\n%s", tb)
        inc("danbao_retrieve_errors_total")
        raise _error(500, RETRIEVE_FAILED.code, f"{exc}\n{tb[-500:]}", RETRIEVE_FAILED.retryable, RETRIEVE_FAILED.stage) from exc


@app.post("/api/v1/retrieve")
def retrieve_compat(request: RetrieveRequest) -> dict[str, Any]:
    return retrieve(request)


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/v1/retrieve/query/stream")
def retrieve_stream(request: RetrieveRequest) -> StreamingResponse:
    def _events():
        started_at = time.perf_counter()
        yield _sse_event("stage", {"stage": "retrieval_started", "query": request.query})
        try:
            response = retrieve(request)
            yield _sse_event(
                "references",
                {
                    "stage": "references_ready",
                    "references": response.get("references") or response.get("citations") or [],
                    "answer_context": response.get("answer_context") or {},
                },
            )
            yield _sse_event("result", response)
            yield _sse_event("done", {"elapsed_ms": int((time.perf_counter() - started_at) * 1000)})
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            yield _sse_event("error", {"status_code": exc.status_code, **detail})
        except Exception as exc:
            yield _sse_event("error", {"status_code": 500, "code": "RETRIEVE_STREAM_FAILED", "message": str(exc)})

    return StreamingResponse(_events(), media_type="text/event-stream")


@app.post("/api/v1/retrieve/stream")
def retrieve_stream_compat(request: RetrieveRequest) -> StreamingResponse:
    return retrieve_stream(request)


@app.post("/api/v1/index/rebuild")
def index_rebuild_compat(request: IndexRequest) -> dict[str, Any]:
    request.operation = "rebuild"
    return index_file(request)


@app.post("/api/v1/index/delete")
def index_delete_compat(request: IndexRequest) -> dict[str, Any]:
    request.operation = "delete"
    return index_file(request)


@app.post("/api/v1/index/kb-rebuild")
def index_kb_rebuild_compat(request: KbRebuildRequest) -> dict[str, Any]:
    return index_kb_rebuild(request)
