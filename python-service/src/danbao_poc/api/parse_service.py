from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from danbao_poc.answer_prebuilder import prebuild_answers
from danbao_poc.catalog_chunker import build_catalog_driven_chunks
from danbao_poc.common import write_json
from danbao_poc.chunk_generation import primary_chunks_for_extraction
from danbao_poc.document_parser import parse_document
from danbao_poc.error_codes import PARSE_FAILED, PARSE_TASK_NOT_FOUND, PARSE_UNSUPPORTED_PROFILE
from danbao_poc.file_center_client import FileCenterClient
from danbao_poc.health_checks import readiness
from danbao_poc.java_backend_client import safe_callback_parse_task
from danbao_poc.knowledge_extractor import extract_knowledge_structure
from danbao_poc.metrics import render_prometheus
from danbao_poc.mysql_store import find_file_node_by_file_id, init_db, load_knowledge_base_profile, load_parse_cache, mark_parse_failed, next_parse_generation, save_parse_cache, save_parse_result
from danbao_poc.nacos_client import NacosServiceRegistrar, register_current_service
from danbao_poc.parse_task_store import acquire_parse_slot, cancel_parse_task, create_parse_task, delete_parse_task, delete_parse_tasks_by_status, enqueue_parse_task, get_parse_task, is_parse_task_cancelled, list_parse_tasks, new_parse_task_id, release_parse_slot, reset_parse_slots, retry_parse_task, take_next_parse_task, update_parse_task
from danbao_poc.profiles.registry import get_profile_spec, resolve_profile
from danbao_poc.section_builder import build_section_summaries, build_sections_from_chunks, build_sections_from_mapped_sections, validate_profile_summary_coverage
from danbao_poc.settings import env_bool
from danbao_poc.validation import validate_chunks, validate_graph_items, validate_middle_document


app = FastAPI(title="Danbao Parse Service", version="1.0.0")
logger = logging.getLogger(__name__)
_worker_threads_started = False
_nacos_registrar: NacosServiceRegistrar | None = None
_HEADING_ONLY_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]+[、.．]|（[一二三四五六七八九十0-9]+）|第[一二三四五六七八九十0-9]+[章节条款]).{0,40}$")
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:[-—–－]\s*)?\d{1,4}(?:\s*[-—–－])?\s*$|^\s*第\s*\d{1,4}\s*页\s*$")


def _parse_log(message: str, *args: Any, exc_info: bool = False) -> None:
    level_name = os.getenv("PARSE_STAGE_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logger.log(level, message, *args, exc_info=exc_info)


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


def _clean_inline(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _chunk_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _looks_heading_only(value: Any) -> bool:
    text = _clean_inline(value)
    if any(mark in text for mark in ["。", "；", ";", "：", ":"]):
        return False
    return bool(text) and len(text) <= 60 and bool(_HEADING_ONLY_RE.match(text))


def _chunk_quality(chunks: list[dict[str, Any]], extraction: dict[str, Any]) -> dict[str, Any]:
    heading_only_chunks = [
        chunk.get("chunk_key")
        for chunk in chunks
        if _looks_heading_only(chunk.get("content"))
    ]
    page_number_chunks = [
        chunk.get("chunk_key")
        for chunk in chunks
        if any(_PAGE_NUMBER_RE.match(line.strip()) for line in str(chunk.get("content") or "").splitlines())
    ]
    business_blocks = {
        _clean_inline(_chunk_metadata(chunk).get("business_block_id"))
        for chunk in chunks
        if _clean_inline(_chunk_metadata(chunk).get("business_block_id"))
    }
    planner_warnings: list[str] = []
    for chunk in chunks:
        for warning in _chunk_metadata(chunk).get("planner_warnings") or []:
            warning = _clean_inline(warning)
            if warning:
                planner_warnings.append(warning)
    fields = extraction.get("fields") if isinstance(extraction, dict) else []
    heading_only_fields = [
        field.get("field_key")
        for field in fields or []
        if _looks_heading_only(field.get("value_text"))
    ]
    evidence_missing = [
        field.get("field_key")
        for field in fields or []
        if not (_chunk_metadata(field).get("evidence_quote") or (field.get("mention") or {}).get("evidence_text"))
    ]
    section_lengths = [len(_clean_inline(chunk.get("content"))) for chunk in chunks if _clean_inline(chunk.get("content"))]
    return {
        "chunk_count": len(chunks),
        "avg_section_chars": round(sum(section_lengths) / len(section_lengths), 2) if section_lengths else 0,
        "heading_only_section_count": len(heading_only_chunks),
        "heading_only_chunk_keys": heading_only_chunks[:50],
        "page_number_chunk_count": len(page_number_chunks),
        "page_number_chunk_keys": page_number_chunks[:50],
        "business_block_count": len(business_blocks),
        "business_block_ids": sorted(business_blocks),
        "planner_warning_count": len(planner_warnings),
        "planner_warnings": planner_warnings[:100],
        "heading_only_field_drop_count": len(heading_only_fields),
        "heading_only_field_keys": heading_only_fields[:50],
        "field_evidence_missing_count": len(evidence_missing),
        "field_evidence_missing_keys": evidence_missing[:50],
    }


def _layout_payload(middle_document: dict[str, Any]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page in middle_document.get("pages") or []:
        blocks = []
        for block in page.get("blocks") or []:
            blocks.append(
                {
                    "block_id": block.get("block_id"),
                    "type": block.get("type") or block.get("block_type"),
                    "label": block.get("label"),
                    "order": block.get("order"),
                    "bbox": block.get("bbox") or [],
                    "text_preview": _clean_inline(block.get("text") or block.get("markdown"))[:200],
                }
            )
        pages.append(
            {
                "page_no": page.get("page_no"),
                "width": page.get("width"),
                "height": page.get("height"),
                "blocks": blocks,
            }
        )
    return {
        "file_name": middle_document.get("file_name"),
        "parser": middle_document.get("parser"),
        "page_count": len(pages),
        "pages": pages,
    }


def _write_required_parse_artifacts(
    *,
    data_dir: Path,
    middle_document: dict[str, Any],
    raw_payload: dict[str, Any],
    artifacts: list[dict[str, Any]],
    response_artifacts: dict[str, str],
) -> None:
    """Write the canonical parse artifacts required by the technical plan."""

    def add_json(artifact_type: str, file_name: str, payload: Any) -> None:
        path = data_dir / file_name
        write_json(path, payload)
        artifacts.append({"artifact_type": artifact_type, "artifact_path": str(path)})
        response_artifacts[artifact_type] = str(path)

    def add_text(artifact_type: str, file_name: str, text: str) -> None:
        path = data_dir / file_name
        path.write_text(text or "", encoding="utf-8")
        artifacts.append({"artifact_type": artifact_type, "artifact_path": str(path)})
        response_artifacts[artifact_type] = str(path)

    add_json("middle_document", "middle_document.json", middle_document)
    normalized_text = str(middle_document.get("normalized_text") or "")
    add_text("normalized_text_txt", "normalized_text.txt", normalized_text)
    add_json(
        "normalized_text",
        "normalized_text.json",
        {
            "text_version": (middle_document.get("char_map") or {}).get("text_version") or "norm_v1",
            "normalized_text": normalized_text,
        },
    )
    add_json("char_map", "char_map.json", middle_document.get("char_map") or {"text_version": "norm_v1", "spans": []})
    add_json("layout", "layout.json", middle_document.get("layout") or _layout_payload(middle_document))
    add_json("tables", "tables.json", {"tables": middle_document.get("tables") or []})
    add_json("images", "images.json", {"images": middle_document.get("images") or []})
    add_json("ocr_raw", "ocr_raw.json", raw_payload.get("raw_ocr") or raw_payload.get("ocr_raw") or {})


def _write_process_artifact(process_dir: Path, file_name: str, payload: Any) -> str:
    process_dir.mkdir(parents=True, exist_ok=True)
    path = process_dir / file_name
    write_json(path, payload)
    return str(path)


def _write_process_text(process_dir: Path, file_name: str, text: str) -> str:
    process_dir.mkdir(parents=True, exist_ok=True)
    path = process_dir / file_name
    path.write_text(text or "", encoding="utf-8")
    return str(path)


def _warning_subset(warnings: list[str], prefixes: tuple[str, ...], limit: int = 50) -> list[str]:
    return [item for item in warnings if item.startswith(prefixes)][:limit]


def _build_parse_layer_report(
    *,
    middle_document: dict[str, Any],
    chunks: list[dict[str, Any]],
    catalog_artifact: dict[str, Any],
    sections: list[dict[str, Any]],
    section_summaries: list[dict[str, Any]],
    summary_coverage_report: dict[str, Any],
    extraction: dict[str, Any],
    knowledge_structure: dict[str, Any],
    answer_prebuild: dict[str, Any],
    validation_warnings: list[str],
) -> dict[str, Any]:
    summary_sources = {str(item.get("summary_source") or "") for item in section_summaries}
    answer_warnings = _warning_subset(validation_warnings, ("qa_prebuild_", "answer_prebuild_"))
    knowledge_warnings = _warning_subset(validation_warnings, ("anchor_", "unit_", "relation_", "knowledge_"))
    spans = (middle_document.get("char_map") or {}).get("spans") or []
    line_spans = [span for span in spans if span.get("line_no") is not None or span.get("source_type") == "line"]
    positioned_line_spans = [span for span in line_spans if span.get("positions") or span.get("bbox")]
    mapped_sections = catalog_artifact.get("mapped_sections") or []
    mapped_success = [item for item in mapped_sections if item.get("start_char") is not None and item.get("end_char") is not None]
    field_alignment_payloads = [
        ((field.get("metadata") or {}).get("evidence_alignment") or {})
        for field in extraction.get("fields") or []
        if isinstance(field.get("metadata"), dict)
    ]
    field_alignments = [item.get("status") for item in field_alignment_payloads if item.get("status")]
    field_confidences = [
        float((field.get("metadata") or {}).get("field_confidence_score") or 0.0)
        for field in extraction.get("fields") or []
        if isinstance(field.get("metadata"), dict)
    ]
    field_conflicts = [
        field
        for field in extraction.get("fields") or []
        if isinstance(field.get("metadata"), dict) and (field.get("metadata") or {}).get("field_conflict")
    ]
    knowledge_alignments = []
    knowledge_alignment_payloads = []
    for item in (knowledge_structure.get("anchors") or []) + (knowledge_structure.get("knowledge_units") or []) + (knowledge_structure.get("relations") or []):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        alignment = metadata.get("evidence_alignment") if isinstance(metadata.get("evidence_alignment"), dict) else {}
        if alignment.get("status"):
            knowledge_alignments.append(alignment.get("status"))
            knowledge_alignment_payloads.append(alignment)
    all_alignment_payloads = [*field_alignment_payloads, *knowledge_alignment_payloads]
    enriched_summaries = [
        item
        for item in section_summaries
        if isinstance(item.get("structured_summary"), dict)
        and ((item["structured_summary"].get("retrieval_keywords") or []) or (item["structured_summary"].get("possible_questions") or []))
    ]
    field_multi_pass = ((extraction.get("_debug") or {}).get("multi_pass") or {}) if isinstance(extraction.get("_debug"), dict) else {}
    knowledge_multi_pass = ((knowledge_structure.get("_debug") or {}).get("multi_pass") or {}) if isinstance(knowledge_structure.get("_debug"), dict) else {}
    knowledge_extraction_cache = ((knowledge_structure.get("_debug") or {}).get("extraction_cache") or {}) if isinstance(knowledge_structure.get("_debug"), dict) else {}

    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 1.0

    return {
        "schema_version": "parse_layer_report_v1",
        "metrics": {
            "line_span_coverage": _rate(len(positioned_line_spans), len(line_spans)),
            "catalog_locate_success_rate": _rate(len(mapped_success), len(mapped_sections)),
            "protected_block_split_count": int((catalog_artifact.get("quality") or {}).get("protected_block_split_count") or 0),
            "field_evidence_exact_rate": _rate(sum(1 for status in field_alignments if status in {"exact", "normalized_exact"}), len(field_alignments)),
            "field_evidence_aligned_rate": _rate(sum(1 for status in field_alignments if status and status != "failed"), len(field_alignments)),
            "knowledge_evidence_aligned_rate": _rate(sum(1 for status in knowledge_alignments if status and status != "failed"), len(knowledge_alignments)),
            "lcs_alignment_rate": _rate(sum(1 for item in all_alignment_payloads if item.get("status") == "lcs_aligned"), len(all_alignment_payloads)),
            "alignment_false_positive_suspect_count": sum(1 for item in all_alignment_payloads if item.get("false_positive_suspect")),
            "anchor_dedup_candidate_count": sum(1 for item in validation_warnings if item.startswith("anchor_dedup_candidate")),
            "relation_schema_reject_count": sum(1 for item in validation_warnings if item.startswith(("relation_endpoint_unresolved", "relation_schema_rejected"))),
            "qa_evidence_failed_count": sum(1 for item in answer_warnings if item.startswith("qa_prebuild_evidence_unaligned")),
            "section_summary_retrieval_enriched_rate": _rate(len(enriched_summaries), len(section_summaries)),
            "regex_field_count": len([field for field in extraction.get("fields") or [] if (field.get("metadata") or {}).get("extraction_strategy") == "regex_first"]),
            "regex_first_field_rate": _rate(
                len([field for field in extraction.get("fields") or [] if (field.get("metadata") or {}).get("extraction_strategy") == "regex_first"]),
                len(extraction.get("fields") or []),
            ),
            "field_extraction_pass_count": int(field_multi_pass.get("pass_count") or 1),
            "field_extraction_newly_added_count": int(field_multi_pass.get("newly_added_count") or 0),
            "field_extraction_overlap_dropped_count": int(field_multi_pass.get("overlap_dropped_count") or 0),
            "knowledge_extraction_pass_count": int(knowledge_multi_pass.get("pass_count") or 1),
            "knowledge_extraction_newly_added_count": int(knowledge_multi_pass.get("newly_added_count") or 0),
            "knowledge_extraction_overlap_dropped_count": int(knowledge_multi_pass.get("overlap_dropped_count") or 0),
            "knowledge_extraction_cache_hit": bool(knowledge_extraction_cache.get("hit")),
            "high_confidence_field_rate": _rate(sum(1 for score in field_confidences if score >= 0.8), len(field_confidences)),
            "field_conflict_count": len(field_conflicts),
        },
        "layers": [
            {
                "layer": "file_processing",
                "status": "ok" if middle_document.get("pages") else "degraded",
                "page_count": len(middle_document.get("pages") or []),
                "has_normalized_text": bool(middle_document.get("normalized_text")),
                "has_char_map": bool((middle_document.get("char_map") or {}).get("spans")),
                "warnings": _warning_subset(validation_warnings, ("middle_document_", "char_map_", "ocr_")),
            },
            {
                "layer": "catalog_chunking",
                "status": "degraded" if catalog_artifact.get("fallback") else "ok",
                "fallback_reason": catalog_artifact.get("fallback"),
                "chunk_count": len(chunks),
                "small_chunk_count": sum(1 for item in chunks if item.get("chunk_type") == "small_chunk"),
                "section_chunk_count": sum(1 for item in chunks if item.get("chunk_type") == "section_chunk"),
                "parent_chunk_count": sum(1 for item in chunks if item.get("chunk_type") == "parent_chunk"),
                "quality": catalog_artifact.get("quality") or {},
                "warnings": _warning_subset(validation_warnings, ("catalog_", "protected_block_")),
            },
            {
                "layer": "section_summary",
                "status": "degraded" if "script_fallback" in summary_sources else "ok",
                "section_count": len(sections),
                "summary_count": len(section_summaries),
                "summary_sources": sorted(item for item in summary_sources if item),
                "coverage_report": summary_coverage_report,
                "warnings": _warning_subset(validation_warnings, ("summary_", "section_summary_", "profile_required_section_")),
            },
            {
                "layer": "profile_extraction",
                "status": "ok",
                "field_count": len(extraction.get("fields") or []),
                "multi_pass": field_multi_pass,
                "warnings": [],
            },
            {
                "layer": "knowledge_structure",
                "status": "degraded" if knowledge_warnings else "ok",
                "anchor_count": len(knowledge_structure.get("anchors") or []),
                "knowledge_unit_count": len(knowledge_structure.get("knowledge_units") or []),
                "relation_count": len(knowledge_structure.get("relations") or []),
                "multi_pass": knowledge_multi_pass,
                "extraction_cache": knowledge_extraction_cache,
                "warnings": knowledge_warnings,
            },
            {
                "layer": "answer_prebuild",
                "status": "disabled"
                if "answer_prebuild_disabled" in answer_warnings
                else ("degraded" if answer_warnings else "ok"),
                "qa_pair_count": len(answer_prebuild.get("qa_pairs") or []),
                "warnings": answer_warnings,
            },
        ],
    }


@app.middleware("http")
async def auth_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or f"req_{int(time.time() * 1000)}"
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
    response = await call_next(request)
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


class ParseRequest(BaseModel):
    task_id: int | str | None = Field(None, description="Java 平台 kb_file_task.id；不传则使用解析服务内部任务ID回调")
    kb_id: int
    file_node_id: int
    file_id: str | None = Field(None, description="文件中心文件ID；不传则默认使用 file_node_id")
    file_center_file_id: str | None = Field(None, description="兼容字段：文件中心文件ID")
    profile: str | None = None
    parse_generation: str | None = None
    index_generation: str | None = None
    engine_task_id: str | None = None
    parse_strategy_config_id: str | None = None
    parse_options: dict[str, Any] | None = None
    model_profile: dict[str, Any] | None = None
    request_id: str | None = None
    local_file_path: str | None = Field(None, description="仅本地联调用，可跳过文件中心")
    return_payload: bool = False
    async_mode: bool = False


class BatchParseItem(BaseModel):
    task_id: int | str | None = None
    file_node_id: int
    file_id: str | None = None
    file_center_file_id: str | None = None
    local_file_path: str | None = None
    profile: str | None = None
    parse_generation: str | None = None
    index_generation: str | None = None
    engine_task_id: str | None = None
    parse_strategy_config_id: str | None = None
    parse_options: dict[str, Any] | None = None
    model_profile: dict[str, Any] | None = None
    request_id: str | None = None
    return_payload: bool = False


class BatchParseRequest(BaseModel):
    kb_id: int
    items: list[BatchParseItem]


@app.on_event("startup")
def startup() -> None:
    global _nacos_registrar
    init_db()
    if env_bool("PARSE_RESET_ACTIVE_ON_STARTUP", True):
        reset_parse_slots()
        _parse_log("parse active slot counter reset on startup")
        from danbao_poc.rate_limiter import reset_llm_slots
        reset_llm_slots()
        _parse_log("llm active slot counter reset on startup")
        from danbao_poc.parse_task_store import recover_stale_tasks
        recovered, failed = recover_stale_tasks()
        if recovered or failed:
            _parse_log("stale task recovery: %s re-enqueued, %s marked failed", recovered, failed)
    _start_parse_workers()
    _nacos_registrar = register_current_service(
        "NACOS_PARSE_SERVICE_NAME",
        "danbao-parse-service",
        "NACOS_PARSE_REGISTER_PORT",
        {"service": "parse-service", "version": app.version or ""},
        fallback_port_env="PARSE_PORT",
    )


@app.on_event("shutdown")
def shutdown() -> None:
    if _nacos_registrar:
        _nacos_registrar.stop()


@app.get("/health")
def health() -> dict[str, str]:
    from danbao_poc import BUILD_TAG
    return {"status": "ok", "service": "parse-service", "build_tag": BUILD_TAG}


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


@app.get("/ready")
def ready() -> dict[str, Any]:
    return readiness(include_es=False, include_file_center=True, include_java=True)


def _local_file_node_id(kb_id: int, file_path: str | Path) -> int:
    normalized = str(Path(file_path).resolve()).replace("\\", "/").lower()
    digest = hashlib.sha1(f"{kb_id}:{normalized}".encode("utf-8")).hexdigest()
    return 10**14 + (int(digest[:16], 16) % (9 * 10**14))


def _worker_count() -> int:
    try:
        return max(1, int(os.getenv("PARSE_WORKER_COUNT", os.getenv("PARSE_MAX_CONCURRENCY", "1"))))
    except Exception:
        return 1


def _start_parse_workers() -> None:
    global _worker_threads_started
    if _worker_threads_started:
        return
    _worker_threads_started = True
    worker_count = _worker_count()
    _parse_log("starting parse workers count=%s max_concurrency=%s", worker_count, os.getenv("PARSE_MAX_CONCURRENCY", "1"))
    for idx in range(worker_count):
        thread = threading.Thread(target=_parse_worker_loop, name=f"parse-worker-{idx+1}", daemon=True)
        thread.start()
        _parse_log("parse worker thread started name=%s", thread.name)


def _parse_worker_loop() -> None:
    while True:
        try:
            task_id = take_next_parse_task(timeout_seconds=3)
            if not task_id:
                continue
        except Exception as exc:
            _parse_log("parse worker failed while waiting queue: %s", exc, exc_info=True)
            time.sleep(3)
            continue
        try:
            task = get_parse_task(task_id)
            if not task:
                _parse_log("parse worker picked missing task_id=%s", task_id)
                continue
            request_payload = task.get("request") or {}
            _parse_log("parse worker picked task_id=%s kb_id=%s file_node_id=%s", task_id, request_payload.get("kb_id"), request_payload.get("file_node_id"))
            try:
                request = ParseRequest(**request_payload)
            except Exception as exc:
                update_parse_task(task_id, status="failed", stage="invalid_request", error=str(exc))
                _parse_log("parse worker invalid request task_id=%s error=%s", task_id, exc)
                continue
            _run_parse_task(request, task_id)
        except Exception as exc:
            file_node_id = None
            try:
                file_node_id = request.file_node_id
            except Exception:
                pass
            _parse_log("parse worker task failed task_id=%s file_node_id=%s: %s", task_id, file_node_id, exc, exc_info=True)


def _download_file(request: ParseRequest) -> tuple[str, bytes, dict[str, Any]]:
    if request.local_file_path:
        path = Path(request.local_file_path)
        file_bytes = path.read_bytes()
        return path.name, file_bytes, {"file_name": path.name, "size": len(file_bytes), "mime_type": mimetypes.guess_type(path.name)[0]}
    source_file_id = request.file_center_file_id or request.file_id or str(request.file_node_id)
    client = FileCenterClient()
    info = client.get_file_info(source_file_id, request_id=request.request_id)
    file_name, file_bytes = client.download_file(source_file_id, request_id=request.request_id)
    return file_name, file_bytes, {
        "file_id": source_file_id,
        "file_name": file_name,
        "size": info.get("size") or info.get("fileSize") or len(file_bytes),
        "mime_type": info.get("mimeType") or info.get("mime_type") or mimetypes.guess_type(file_name)[0],
    }


def _validate_file_id_binding(kb_id: int, file_node_id: int, file_id: str | None) -> None:
    if not file_id:
        return
    existing = find_file_node_by_file_id(kb_id, file_id)
    if existing and int(existing["id"]) != int(file_node_id):
        raise _error(
            409,
            "FILE_ID_ALREADY_BOUND",
            f"file_id={file_id} already belongs to file_node_id={existing['id']} in kb_id={kb_id}; use that file_node_id or upload/register a new file",
            False,
            "validate",
        )


def _parser_stage(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        return "ocr"
    if suffix in {".txt", ".md"}:
        return "read_text"
    if suffix == ".docx":
        return "read_docx"
    if suffix in {".xlsx", ".xlsm", ".csv", ".tsv"}:
        return "read_table"
    return "parse"


def _requested_profile(profile: str | None, parse_options: dict[str, Any] | None) -> str | None:
    options = parse_options or {}
    return options.get("profile") or profile


def _resolve_request_profile(profile: str | None, parse_options: dict[str, Any] | None, *, kb_id: int | None = None) -> str:
    requested = _requested_profile(profile, parse_options)
    if requested and requested != "auto":
        # 文件显式指定 profile 时只使用请求值；非法值直接报错，不做兜底推测。
        return resolve_profile(requested, allow_fallback=False)
    if kb_id is None:
        raise ValueError("kb_id is required when file profile is not provided")
    # 文件未传 / auto 时，唯一来源是知识库创建时保存的 profile。
    kb_profile = load_knowledge_base_profile(kb_id)
    if not kb_profile:
        raise ValueError(f"Knowledge base profile is not configured: kb_id={kb_id}")
    return resolve_profile(kb_profile, allow_fallback=False)


def _parser_hint(parse_options: dict[str, Any] | None) -> str | None:
    options = parse_options or {}
    value = options.get("parser_hint")
    return str(value).strip() if value else None


def _reused_middle_document_path(parse_options: dict[str, Any] | None) -> str | None:
    options = parse_options or {}
    for key in ("reuse_middle_document_path", "middle_document_path", "cached_middle_document_path"):
        value = options.get(key)
        if value:
            return str(value).strip()
    return None


def _load_reused_middle_document(
    *,
    path: str,
    file_node_id: int,
    file_name: str,
    profile: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_path = Path(path)
    if not source_path.exists():
        raise RuntimeError(f"reused middle_document not found: {source_path}")
    middle_document = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(middle_document, dict):
        raise RuntimeError(f"reused middle_document must be a JSON object: {source_path}")
    source_document_id = middle_document.get("document_id")
    source_file_name = middle_document.get("file_name")
    middle_document["document_id"] = str(file_node_id)
    middle_document["file_name"] = file_name
    middle_document["profile"] = profile
    return middle_document, {
        "reused_middle_document": {
            "source_path": str(source_path),
            "source_document_id": source_document_id,
            "source_file_name": source_file_name,
            "parser": middle_document.get("parser"),
        }
    }


def _parse_cache_enabled(parse_options: dict[str, Any] | None) -> bool:
    cache_options = parse_options.get("parse_cache") if isinstance(parse_options, dict) else None
    if isinstance(cache_options, dict) and "enabled" in cache_options:
        return bool(cache_options.get("enabled"))
    return env_bool("PARSE_CACHE_ENABLED", True)


def _parse_cache_identity(file_name: str, profile: str, parse_options: dict[str, Any] | None, file_hash: str) -> dict[str, str]:
    parser_hint = _parser_hint(parse_options) or Path(file_name).suffix.lower().lstrip(".") or "unknown"
    parser_name = f"{parser_hint}:{os.getenv('OCR_BACKEND', 'mineru')}"
    parser_version = os.getenv("PARSER_VERSION", "danbao_poc_parse_v1")
    relevant_options = {
        "parser_hint": parser_hint,
        "ocr_backend": os.getenv("OCR_BACKEND", "mineru"),
        "ocr_layout": os.getenv("OCR_LAYOUT", ""),
        "parse_options": parse_options or {},
    }
    options_hash = hashlib.sha256(json.dumps(relevant_options, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "file_hash": file_hash,
        "parser_profile": profile,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "parse_options_hash": options_hash,
    }


def _adapt_cached_middle_document(cached: dict[str, Any], *, file_node_id: int, file_name: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    middle_document = json.loads(json.dumps(cached.get("middle_document") or {}, ensure_ascii=False))
    raw_payload = json.loads(json.dumps(cached.get("raw_payload") or {}, ensure_ascii=False))
    source_document_id = middle_document.get("document_id")
    source_file_name = middle_document.get("file_name") or cached.get("source_file_name")
    middle_document["document_id"] = str(file_node_id)
    middle_document["file_name"] = file_name
    middle_document["profile"] = profile
    raw_payload["parse_cache"] = {
        "hit": True,
        "source_document_id": source_document_id,
        "source_file_name": source_file_name,
        "hit_count": cached.get("hit_count") or 0,
    }
    return middle_document, raw_payload


def _parse_and_save(
    *,
    kb_id: int,
    file_node_id: int,
    profile: str,
    parse_options: dict[str, Any] | None,
    model_profile: dict[str, Any] | None,
    file_name: str,
    file_bytes: bytes,
    file_info: dict[str, Any],
    requested_parse_generation: str | None,
    return_payload: bool,
    requested_index_generation: str | None = None,
    parse_strategy_config_id: str | None = None,
    platform_task_id: int | str | None = None,
    engine_task_id: str | None = None,
    request_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    parse_generation = requested_parse_generation or next_parse_generation(file_node_id)
    engine_task_id = engine_task_id or task_id or parse_generation
    profile = _resolve_request_profile(profile, parse_options, kb_id=kb_id)
    spec = get_profile_spec(profile)
    file_hash = hashlib.sha1(file_bytes).hexdigest()
    parse_cache_identity = _parse_cache_identity(file_name, profile, parse_options, file_hash)
    parse_cache_hit = False
    data_dir = Path(os.getenv("DATA_DIR", "/app/data")) / "parsed" / str(kb_id) / str(file_node_id) / parse_generation
    process_dir = data_dir / "process"
    _write_process_artifact(
        process_dir,
        "00_parse_request.json",
        {
            "kb_id": kb_id,
            "file_node_id": file_node_id,
            "file_name": file_name,
            "file_size": len(file_bytes),
            "profile": profile,
            "requested_parse_generation": requested_parse_generation,
            "parse_generation": parse_generation,
            "parse_options": parse_options,
            "file_info": file_info,
        },
    )
    reused_middle_path = _reused_middle_document_path(parse_options)
    visual_chunks: list[dict[str, Any]] = []
    visual_assets: list[dict[str, Any]] = []
    if task_id:
        update_parse_task(task_id, stage="reuse_middle_document" if reused_middle_path else _parser_stage(file_name), parse_generation=parse_generation)
        _parse_log(
            "parse task parsing document task_id=%s file_node_id=%s stage=%s profile=%s ocr_backend=%s",
            task_id,
            file_node_id,
            "reuse_middle_document" if reused_middle_path else _parser_stage(file_name),
            profile,
            os.getenv("OCR_BACKEND", "mineru"),
        )
    if reused_middle_path:
        middle_document, raw_payload = _load_reused_middle_document(
            path=reused_middle_path,
            file_node_id=file_node_id,
            file_name=file_name,
            profile=profile,
        )
    else:
        cached_parse = None
        # 多模态解析需要图片字节，而解析缓存里没有（字节在缓存前被剥离），
        # 命中缓存会跳过提图 + VLM 描述。故多模态开启时禁用解析缓存，强制新鲜解析。
        multimodal_enabled = bool((parse_options or {}).get("multimodal", {}).get("enabled"))
        if _parse_cache_enabled(parse_options) and not multimodal_enabled:
            try:
                cached_parse = load_parse_cache(**parse_cache_identity)
            except Exception as exc:
                _parse_log("parse cache load failed file_node_id=%s error=%s", file_node_id, exc)
        if cached_parse:
            parse_cache_hit = True
            middle_document, raw_payload = _adapt_cached_middle_document(
                cached_parse,
                file_node_id=file_node_id,
                file_name=file_name,
                profile=profile,
            )
        else:
            middle_document, raw_payload = parse_document(
                file_name,
                file_bytes,
                str(file_node_id),
                profile,
                parser_hint=_parser_hint(parse_options),
                file_id=str(file_info.get("file_id") or ""),
            )
            # ── 多模态 VLM 描述（parse_options.multimodal.enabled 门后）──
            if (parse_options or {}).get("multimodal", {}).get("enabled") and (middle_document.get("images") or []):
                if task_id:
                    update_parse_task(task_id, stage="multimodal_analyzing")
                    _parse_log("parse task multimodal_analyzing task_id=%s images=%s", task_id, len(middle_document.get("images") or []))
                from danbao_poc.multimodal import analyze_images, analyze_multi_images, build_multimodal_chunks

                multimodal_options = (parse_options or {}).get("multimodal", {})
                analyze_mode = str(multimodal_options.get("analyze_mode") or os.getenv("MULTIMODAL_ANALYZE_MODE", "single")).strip().lower()

                file_center = None
                if os.getenv("MULTIMODAL_UPLOAD_IMAGES", "false").strip().lower() in {"1", "true", "yes", "on"}:
                    try:
                        file_center = FileCenterClient()
                    except Exception as exc:
                        _parse_log("multimodal file center unavailable file_node_id=%s error=%s", file_node_id, exc)

                multimodal_relations: list[dict[str, Any]] = []
                if analyze_mode in ("multi", "hybrid"):
                    _parse_log("parse task multimodal multi-image mode task_id=%s analyze_mode=%s", task_id, analyze_mode)
                    multi_result = analyze_multi_images(
                        middle_document,
                        parse_options=parse_options,
                        profile=profile,
                        file_center=file_center,
                        request_id=request_id,
                    )
                    visual_chunks, multimodal_relations = build_multimodal_chunks(
                        multi_result,
                        multi_result.get("document") or {},
                        profile=profile,
                        source_file_id=str(file_info.get("file_id") or ""),
                    )
                    visual_assets = [multi_result]
                else:
                    visual_chunks, visual_assets = analyze_images(
                        middle_document,
                        parse_options=parse_options,
                        profile=profile,
                        file_center=file_center,
                        request_id=request_id,
                    )
                _write_process_artifact(process_dir, "02_multimodal.json", {
                    "visual_chunks": visual_chunks,
                    "visual_assets": visual_assets,
                    "relations": multimodal_relations,
                })
            # ─────────────────────────────────────────────
            # 剥离图片字节：middle_document 后续会被 json.dumps（parse cache + 01_middle_document.json），
            # 图片 bytes 无法 JSON 序列化。_parse_docx 无条件提图（带 bytes），多模态分析在上一块已用完，
            # 这里无论多模态是否开启都要清掉，否则 multimodal_enabled=0 的文件会在这里崩。
            for _img in (middle_document.get("images") or []):
                _img["bytes"] = None
            if _parse_cache_enabled(parse_options):
                try:
                    save_parse_cache(
                        **parse_cache_identity,
                        source_file_name=file_name,
                        middle_document=middle_document,
                        raw_payload=raw_payload,
                    )
                except Exception as exc:
                    _parse_log("parse cache save failed file_node_id=%s error=%s", file_node_id, exc)
    # NOTE: 不再基于内容二次推断 profile，直接用解析请求已决定的 profile
    _write_process_artifact(process_dir, "01_middle_document.json", middle_document)
    _write_process_text(process_dir, "01_normalized_text.txt", str(middle_document.get("normalized_text") or ""))
    _write_process_artifact(process_dir, "01_raw_payload.json", raw_payload)
    if task_id:
        _check_cancelled(task_id)
        update_parse_task(task_id, stage="chunking")
        _parse_log("parse task chunking task_id=%s file_node_id=%s", task_id, file_node_id)
    document_title = _clean_inline(middle_document.get("file_name") or file_name)
    for page in middle_document.get("pages") or []:
        for block in page.get("blocks") or []:
            if block.get("label") == "doc_title" and _clean_inline(block.get("text")):
                document_title = _clean_inline(block.get("text"))
                break
        else:
            continue
        break
    catalog_builder = spec.catalog_builder or build_catalog_driven_chunks
    catalog_result = catalog_builder(
        middle_document,
        profile=profile,
        document_title=document_title,
        parse_options=parse_options,
    )
    chunks = catalog_result.chunks + visual_chunks
    raw_payload["catalog_pipeline"] = catalog_result.catalog_artifact
    _write_process_artifact(
        process_dir,
        "02_catalog_chunking.json",
        {"catalog_artifact": catalog_result.catalog_artifact, "warnings": catalog_result.warnings, "chunks": chunks},
    )
    primary_chunks = primary_chunks_for_extraction(chunks)
    sections = build_sections_from_mapped_sections(
        catalog_result.catalog_artifact.get("mapped_sections") or [],
        primary_chunks,
        document_title=document_title,
        profile=profile,
    )
    _write_process_artifact(process_dir, "03_sections.json", {"sections": sections, "primary_chunks": primary_chunks})
    if task_id:
        _check_cancelled(task_id)
        update_parse_task(task_id, stage="section_summarizing")
        _parse_log("parse task section_summarizing task_id=%s file_node_id=%s sections=%s", task_id, file_node_id, len(sections))
    section_summaries = (
        build_section_summaries(sections, primary_chunks, profile=profile, parse_options=parse_options)
        if spec.enable_section_summaries
        else []
    )
    summary_coverage_report = (
        validate_profile_summary_coverage(profile=profile, chunks=primary_chunks, section_summaries=section_summaries)
        if spec.enable_section_summaries
        else {
            "profile": profile,
            "required_section_types": [],
            "present_section_types": sorted({str(chunk.get("section_type") or "") for chunk in primary_chunks if chunk.get("section_type")}),
            "summarized_section_count": 0,
            "warnings": [],
            "status": "skipped_by_profile",
        }
    )
    _write_process_artifact(
        process_dir,
        "04_section_summaries.json",
        {"section_summaries": section_summaries, "coverage_report": summary_coverage_report},
    )
    validation_warnings = validate_middle_document(middle_document) + validate_chunks(chunks) + catalog_result.warnings
    validation_warnings.extend(summary_coverage_report.get("warnings") or [])
    for summary in section_summaries:
        validation_warnings.extend(summary.get("quality_warnings") or [])
    if task_id:
        _check_cancelled(task_id)
        update_parse_task(task_id, stage="extracting")
        _parse_log("parse task extracting task_id=%s file_node_id=%s chunks=%s sections=%s", task_id, file_node_id, len(chunks), len(sections))
    extraction = spec.extractor(primary_chunks, parse_options=parse_options)
    _write_process_artifact(process_dir, "05_profile_extraction.json", extraction)
    if task_id:
        _check_cancelled(task_id)
        update_parse_task(task_id, stage="knowledge_extracting")
        _parse_log("parse task knowledge_extracting task_id=%s file_node_id=%s", task_id, file_node_id)
    knowledge_structure = (
        extract_knowledge_structure(
            chunks=chunks,
            sections=sections,
            section_summaries=section_summaries,
            profile=profile,
            parse_options=parse_options,
        )
        if spec.enable_knowledge_extraction
        else {"anchors": [], "knowledge_units": [], "relations": [], "warnings": []}
    )
    _write_process_artifact(process_dir, "06_knowledge_structure.json", knowledge_structure)
    validation_warnings.extend(knowledge_structure.get("warnings") or [])
    if task_id:
        _check_cancelled(task_id)
        update_parse_task(task_id, stage="answer_prebuilding")
        _parse_log("parse task answer_prebuilding task_id=%s file_node_id=%s", task_id, file_node_id)
    answer_prebuild = (
        prebuild_answers(
            chunks=chunks,
            section_summaries=section_summaries,
            knowledge_structure=knowledge_structure,
            profile=profile,
            parse_options=parse_options,
        )
        if spec.enable_answer_prebuild
        else {"qa_pairs": [], "warnings": []}
    )
    _write_process_artifact(process_dir, "07_answer_prebuild.json", answer_prebuild)
    validation_warnings.extend(answer_prebuild.get("warnings") or [])
    quality_report = _chunk_quality(chunks, extraction)
    # 注入知识抽取结果到 extraction，供通用图构建器使用
    extraction["_profile"] = profile
    extraction["anchors"] = knowledge_structure.get("anchors") or []
    extraction["knowledge_units"] = knowledge_structure.get("knowledge_units") or []
    extraction["relations"] = knowledge_structure.get("relations") or []
    extraction["chunks"] = chunks
    if task_id and spec.graph_builder:
        update_parse_task(task_id, stage="graph_building")
        _parse_log("parse task graph building task_id=%s file_node_id=%s", task_id, file_node_id)
    graph_nodes, graph_edges = spec.graph_builder(extraction) if spec.graph_builder else ([], [])
    validation_warnings.extend(validate_graph_items(graph_nodes, graph_edges))
    _write_process_artifact(process_dir, "08_graph.json", {"nodes": graph_nodes, "edges": graph_edges})

    data_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    response_artifacts: dict[str, str] = {}
    _write_required_parse_artifacts(
        data_dir=data_dir,
        middle_document=middle_document,
        raw_payload=raw_payload,
        artifacts=artifacts,
        response_artifacts=response_artifacts,
    )
    chunks_path = data_dir / "chunks.json"
    write_json(chunks_path, {"chunks": chunks})
    artifacts.append({"artifact_type": "chunks", "artifact_path": str(chunks_path)})
    response_artifacts["chunks"] = str(chunks_path)

    sections_path = data_dir / "sections.json"
    write_json(sections_path, {"sections": sections})
    artifacts.append({"artifact_type": "sections", "artifact_path": str(sections_path)})
    response_artifacts["sections"] = str(sections_path)

    section_summaries_path = data_dir / "section_summaries.json"
    write_json(section_summaries_path, {"section_summaries": section_summaries, "coverage_report": summary_coverage_report})
    artifacts.append({"artifact_type": "section_summaries", "artifact_path": str(section_summaries_path)})
    response_artifacts["section_summaries"] = str(section_summaries_path)

    extraction_path = data_dir / "extraction.json"
    write_json(extraction_path, extraction)
    artifacts.append({"artifact_type": "extraction", "artifact_path": str(extraction_path)})
    response_artifacts["extraction"] = str(extraction_path)

    quality_path = data_dir / "chunk_quality.json"
    write_json(quality_path, {**quality_report, "summary_coverage_report": summary_coverage_report})
    artifacts.append({"artifact_type": "chunk_quality", "artifact_path": str(quality_path)})
    response_artifacts["chunk_quality"] = str(quality_path)

    graph_path = data_dir / "graph.json"
    write_json(graph_path, {"nodes": graph_nodes, "edges": graph_edges})
    artifacts.append({"artifact_type": "graph", "artifact_path": str(graph_path)})
    response_artifacts["graph"] = str(graph_path)

    knowledge_path = data_dir / "knowledge_structure.json"
    write_json(knowledge_path, knowledge_structure)
    artifacts.append({"artifact_type": "knowledge_structure", "artifact_path": str(knowledge_path)})
    response_artifacts["knowledge_structure"] = str(knowledge_path)

    answer_prebuild_path = data_dir / "answer_prebuild.json"
    write_json(answer_prebuild_path, answer_prebuild)
    artifacts.append({"artifact_type": "answer_prebuild", "artifact_path": str(answer_prebuild_path)})
    response_artifacts["answer_prebuild"] = str(answer_prebuild_path)

    parse_layer_report = _build_parse_layer_report(
        middle_document=middle_document,
        chunks=chunks,
        catalog_artifact=catalog_result.catalog_artifact,
        sections=sections,
        section_summaries=section_summaries,
        summary_coverage_report=summary_coverage_report,
        extraction=extraction,
        knowledge_structure=knowledge_structure,
        answer_prebuild=answer_prebuild,
        validation_warnings=validation_warnings,
    )
    _write_process_artifact(process_dir, "09_parse_layer_report.json", parse_layer_report)
    _write_process_artifact(process_dir, "10_validation_warnings.json", {"warnings": validation_warnings})
    parse_layer_report_path = data_dir / "parse_layer_report.json"
    write_json(parse_layer_report_path, parse_layer_report)
    artifacts.append({"artifact_type": "parse_layer_report", "artifact_path": str(parse_layer_report_path)})
    response_artifacts["parse_layer_report"] = str(parse_layer_report_path)
    if validation_warnings:
        validation_path = data_dir / "validation_warnings.json"
        write_json(validation_path, {"warnings": validation_warnings})
        artifacts.append({"artifact_type": "validation_warnings", "artifact_path": str(validation_path)})
        response_artifacts["validation_warnings"] = str(validation_path)
    for key, value in raw_payload.items():
        if key in {"raw_ocr", "ocr_raw"}:
            continue
        if value is None:
            continue
        artifact_path = data_dir / f"{key}.json"
        write_json(artifact_path, value)
        artifacts.append({"artifact_type": key, "artifact_path": str(artifact_path)})
        response_artifacts[key] = str(artifact_path)

    parse_result_url = _upload_parse_artifacts(
        artifacts=artifacts,
        kb_id=kb_id,
        file_node_id=file_node_id,
        parse_generation=parse_generation,
        request_id=request_id,
    )

    if task_id:
        update_parse_task(task_id, stage="saving")
        _parse_log("parse task saving task_id=%s file_node_id=%s", task_id, file_node_id)
    counters = save_parse_result(
        {
            "kb_id": kb_id,
            "file_node_id": file_node_id,
            "file_id": file_info.get("file_id"),
            "file_name": file_name,
            "file_size": file_info.get("size"),
            "mime_type": file_info.get("mime_type"),
            "file_ext": Path(file_name).suffix.lstrip(".").lower() or None,
            "file_hash": file_hash,
            "parse_generation": parse_generation,
            "index_generation": requested_index_generation,
            "parse_strategy_config_id": parse_strategy_config_id,
            "engine_task_id": engine_task_id,
            "platform_task_id": platform_task_id,
            "parse_result_url": parse_result_url,
            "profile": profile,
            "model_profile": model_profile,
            "model_profile_name": (model_profile or {}).get("parse") or os.getenv("DEFAULT_MODEL_NAME", "qwen2.5-32b"),
            "chunks": chunks,
            "sections": sections,
            "section_summaries": section_summaries,
            "fields": extraction["fields"],
            "anchors": knowledge_structure.get("anchors") or [],
            "knowledge_units": knowledge_structure.get("knowledge_units") or [],
            "relations": knowledge_structure.get("relations") or [],
            "qa_pairs": answer_prebuild.get("qa_pairs") or [],
            "graph_nodes": graph_nodes,
            "graph_edges": graph_edges,
            "char_map": middle_document.get("char_map"),
            "tables": middle_document.get("tables") or [],
            "artifacts": artifacts,
            "quality_report": quality_report,
            "summary_coverage_report": summary_coverage_report,
            "parse_options": parse_options,
        }
    )
    response = {
        "status": "success",
        "kb_id": kb_id,
        "file_node_id": file_node_id,
        "profile": profile,
        "parse_generation": parse_generation,
        "index_generation": requested_index_generation,
        "engine_task_id": engine_task_id,
        "platform_task_id": platform_task_id,
        "parse_result_url": parse_result_url,
        "file_name": file_name,
        "summary": {
            "page_count": len(middle_document.get("pages", [])),
            "chunk_count": counters["chunk_count"],
            "section_count": counters.get("section_count", len(sections)),
            "section_summary_count": counters.get("section_summary_count", len(section_summaries)),
            "section_summary_evidence_count": counters.get("section_summary_evidence_count", 0),
            "field_count": counters["field_count"],
            "graph_node_count": counters["graph_node_count"],
            "graph_edge_count": counters["graph_edge_count"],
            "relation_count": counters.get("relation_count", 0),
            "anchor_count": counters.get("anchor_count", 0),
            "knowledge_unit_count": counters.get("knowledge_unit_count", 0),
            "knowledge_relation_count": counters.get("knowledge_relation_count", 0),
            "knowledge_candidate_count": counters.get("knowledge_candidate_count", 0),
            "pending_knowledge_candidate_count": counters.get("pending_knowledge_candidate_count", 0),
            "prebuilt_qa_count": counters.get("prebuilt_qa_count", 0),
        },
        "validation_warnings": validation_warnings,
        "quality_report": quality_report,
        "summary_coverage_report": summary_coverage_report,
        "parse_layer_report": parse_layer_report,
        "artifacts": response_artifacts,
        "parse_cache": {
            "enabled": _parse_cache_enabled(parse_options) and not bool(reused_middle_path),
            "hit": parse_cache_hit,
            **parse_cache_identity,
        },
    }
    if return_payload:
        response["chunks"] = chunks
        response["sections"] = sections
        response["section_summaries"] = section_summaries
        response["fields"] = extraction["fields"]
        response["anchors"] = knowledge_structure.get("anchors") or []
        response["knowledge_units"] = knowledge_structure.get("knowledge_units") or []
        response["relations"] = knowledge_structure.get("relations") or []
        response["prebuilt_qa_pairs"] = answer_prebuild.get("qa_pairs") or []
        response["graph_nodes"] = graph_nodes
        response["graph_edges"] = graph_edges
    if task_id:
        update_parse_task(task_id, status="success", stage="done", result=response, error=None)
        _parse_log("parse task done task_id=%s file_node_id=%s chunks=%s sections=%s", task_id, file_node_id, counters["chunk_count"], counters.get("section_count", len(sections)))
    return response


def _remote_url_from_upload_result(result: dict[str, Any]) -> str | None:
    for key in ["url", "fileUrl", "file_url", "downloadUrl", "download_url", "path", "uri"]:
        value = result.get(key)
        if value:
            return str(value)
    file_id = result.get("fileId") or result.get("file_id") or result.get("id")
    return f"file-center://{file_id}" if file_id else None


def _upload_parse_artifacts(
    *,
    artifacts: list[dict[str, Any]],
    kb_id: int,
    file_node_id: int,
    parse_generation: str,
    request_id: str | None,
) -> str | None:
    local_middle = next((item for item in artifacts if item.get("artifact_type") == "middle_document"), None)
    if not local_middle:
        return None
    result_url = local_middle.get("artifact_path")
    if not env_bool("FILE_CENTER_UPLOAD_PARSE_ARTIFACTS", False):
        return str(result_url) if result_url else None
    required = env_bool("FILE_CENTER_UPLOAD_REQUIRED", False)
    try:
        client = FileCenterClient()
        for artifact in artifacts:
            path = artifact.get("artifact_path")
            if not path:
                continue
            upload_result = client.upload_path(
                path,
                request_id=request_id,
                metadata={
                    "kb_id": kb_id,
                    "file_node_id": file_node_id,
                    "parse_generation": parse_generation,
                    "artifact_type": artifact.get("artifact_type"),
                },
            )
            remote_url = _remote_url_from_upload_result(upload_result)
            artifact["payload"] = {**(artifact.get("payload") or {}), "remote": upload_result, "remote_url": remote_url}
            if artifact.get("artifact_type") == "middle_document" and remote_url:
                result_url = remote_url
    except Exception:
        if required:
            raise
    return str(result_url) if result_url else None


def _check_cancelled(task_id: str) -> None:
    if task_id and is_parse_task_cancelled(task_id):
        raise RuntimeError(f"task {task_id} cancelled by user")


def _run_parse_task(request: ParseRequest, task_id: str) -> dict[str, Any]:
    slot_acquired = False
    try:
        _parse_log("parse task starting task_id=%s kb_id=%s file_node_id=%s async_mode=%s", task_id, request.kb_id, request.file_node_id, request.async_mode)
        acquire_parse_slot(task_id)
        slot_acquired = True
        _parse_log("parse task slot acquired task_id=%s file_node_id=%s", task_id, request.file_node_id)
        _check_cancelled(task_id)
        update_parse_task(task_id, stage="downloading")
        _parse_log("parse task downloading task_id=%s file_node_id=%s source=%s", task_id, request.file_node_id, "local_file_path" if request.local_file_path else "file_center")
        file_name, file_bytes, file_info = _download_file(request)
        _parse_log("parse task downloaded task_id=%s file_node_id=%s file_name=%s bytes=%s", task_id, request.file_node_id, file_name, len(file_bytes))
        _check_cancelled(task_id)
        result = _parse_and_save(
            kb_id=request.kb_id,
            file_node_id=request.file_node_id,
            profile=request.profile,
            parse_options=request.parse_options,
            model_profile=request.model_profile,
            file_name=file_name,
            file_bytes=file_bytes,
            file_info=file_info,
            requested_parse_generation=request.parse_generation,
            requested_index_generation=request.index_generation,
            parse_strategy_config_id=request.parse_strategy_config_id,
            platform_task_id=request.task_id or task_id,
            engine_task_id=request.engine_task_id or task_id,
            request_id=request.request_id,
            return_payload=request.return_payload,
            task_id=task_id,
        )
        _parse_log("parse task finished task_id=%s file_node_id=%s", task_id, request.file_node_id)
        try:
            _callback_parse_success(request, result, task_id)
        except Exception as callback_exc:
            logger.warning("parse success callback ignored task_id=%s file_node_id=%s: %s", task_id, request.file_node_id, callback_exc)
            try:
                update_parse_task(task_id, callback={"status": "failed", "error": str(callback_exc)})
            except Exception:
                pass
        return result
    except Exception as exc:
        try:
            mark_parse_failed(request.kb_id, request.file_node_id, request.parse_generation, str(exc))
        except Exception:
            pass
        update_parse_task(task_id, status="failed", stage="failed", error=str(exc))
        try:
            _callback_parse_failed(request, task_id, exc)
        except Exception as callback_exc:
            logger.warning("parse failed callback ignored task_id=%s file_node_id=%s: %s", task_id, request.file_node_id, callback_exc)
        raise
    finally:
        if slot_acquired:
            release_parse_slot(task_id)


def _callback_parse_success(request: ParseRequest, result: dict[str, Any], internal_task_id: str) -> None:
    callback_result = safe_callback_parse_task(
        task_id=request.task_id or internal_task_id,
        file_node_id=request.file_node_id,
        kb_id=request.kb_id,
        stage="done",
        status="success",
        parse_generation=result.get("parse_generation") or request.parse_generation,
        index_generation=result.get("index_generation") or request.index_generation,
        engine_task_id=result.get("engine_task_id") or request.engine_task_id or internal_task_id,
        indexed_chunk_count=(result.get("summary") or {}).get("chunk_count"),
        parse_result_url=result.get("parse_result_url"),
        error_msg=None,
        request_id=request.request_id,
    )
    try:
        update_parse_task(internal_task_id, callback=callback_result)
    except Exception:
        pass


def _callback_parse_failed(request: ParseRequest, internal_task_id: str, exc: Exception) -> None:
    callback_result = safe_callback_parse_task(
        task_id=request.task_id or internal_task_id,
        file_node_id=request.file_node_id,
        kb_id=request.kb_id,
        stage="failed",
        status="failed",
        parse_generation=request.parse_generation,
        index_generation=request.index_generation,
        engine_task_id=request.engine_task_id or internal_task_id,
        error_msg=str(exc),
        retryable=True,
        request_id=request.request_id,
    )
    try:
        update_parse_task(internal_task_id, callback=callback_result)
    except Exception:
        pass


@app.post("/api/v1/parse/files")
def parse_file(request: ParseRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    _parse_log(
        "parse request received kb_id=%s file_node_id=%s task_id=%s async_mode=%s profile=%s file_id=%s file_center_file_id=%s local_file=%s",
        request.kb_id,
        request.file_node_id,
        request.task_id,
        request.async_mode,
        request.profile,
        request.file_id,
        request.file_center_file_id,
        bool(request.local_file_path),
    )
    try:
        get_profile_spec(
            _resolve_request_profile(
                request.profile,
                request.parse_options,
                kb_id=request.kb_id,
            )
        )
    except ValueError as exc:
        raise _error(400, PARSE_UNSUPPORTED_PROFILE.code, str(exc), PARSE_UNSUPPORTED_PROFILE.retryable, PARSE_UNSUPPORTED_PROFILE.stage) from exc
    _validate_file_id_binding(request.kb_id, request.file_node_id, request.file_center_file_id or request.file_id)
    task_id = new_parse_task_id(request.file_node_id)
    create_parse_task(
        task_id,
        {
            "kb_id": request.kb_id,
            "task_id": request.task_id,
            "file_node_id": request.file_node_id,
            "file_id": request.file_id,
            "file_center_file_id": request.file_center_file_id,
            "profile": request.profile,
            "parse_generation": request.parse_generation,
            "index_generation": request.index_generation,
            "engine_task_id": request.engine_task_id,
            "parse_strategy_config_id": request.parse_strategy_config_id,
            "parse_options": request.parse_options,
            "model_profile": request.model_profile,
            "request_id": request.request_id,
            "local_file_path": request.local_file_path,
            "return_payload": request.return_payload,
        },
    )
    _parse_log("parse task created internal_task_id=%s kb_id=%s file_node_id=%s async_mode=%s", task_id, request.kb_id, request.file_node_id, request.async_mode)
    if request.async_mode:
        try:
            enqueue_parse_task(task_id)
        except RuntimeError as exc:
            if "queue full" in str(exc):
                raise _error(503, "QUEUE_FULL", str(exc), True, "enqueue")
            raise
        _parse_log("parse task enqueued internal_task_id=%s kb_id=%s file_node_id=%s", task_id, request.kb_id, request.file_node_id)
        return {
            "status": "accepted",
            "task_id": task_id,
            "kb_id": request.kb_id,
            "file_node_id": request.file_node_id,
            "profile": request.profile,
        }
    try:
        _parse_log("parse task executing inline internal_task_id=%s kb_id=%s file_node_id=%s", task_id, request.kb_id, request.file_node_id)
        result = _run_parse_task(request, task_id)
        result["task_id"] = task_id
        return result
    except Exception as exc:
        logger.exception("parse request failed task_id=%s kb_id=%s file_node_id=%s: %s", task_id, request.kb_id, request.file_node_id, exc)
        raise _error(500, PARSE_FAILED.code, str(exc), PARSE_FAILED.retryable, PARSE_FAILED.stage) from exc


@app.post("/api/v1/parse/file")
def parse_file_compat(request: ParseRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    return parse_file(request, background_tasks)


@app.get("/api/v1/parse/tasks")
def list_parse_task_status(
    status: str | None = None,
    kb_id: int | None = None,
    file_node_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    tasks = list_parse_tasks(status=status, kb_id=kb_id, file_node_id=file_node_id, limit=limit)
    return {
        "status": "success",
        "filters": {
            "status": status,
            "kb_id": kb_id,
            "file_node_id": file_node_id,
            "limit": limit,
        },
        "task_count": len(tasks),
        "tasks": tasks,
    }


@app.get("/api/v1/parse/tasks/{task_id}")
def get_parse_task_status(task_id: str) -> dict[str, Any]:
    task = get_parse_task(task_id)
    if not task:
        raise _error(404, PARSE_TASK_NOT_FOUND.code, f"parse task not found: {task_id}", PARSE_TASK_NOT_FOUND.retryable, PARSE_TASK_NOT_FOUND.stage)
    return task


@app.delete("/api/v1/parse/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    if not delete_parse_task(task_id):
        raise _error(404, PARSE_TASK_NOT_FOUND.code, f"parse task not found: {task_id}", PARSE_TASK_NOT_FOUND.retryable, PARSE_TASK_NOT_FOUND.stage)
    return {"status": "success", "message": f"task {task_id} deleted"}


@app.delete("/api/v1/parse/tasks")
def delete_tasks_by_status(status: str = "failed") -> dict[str, Any]:
    deleted = delete_parse_tasks_by_status(status)
    return {"status": "success", "deleted": deleted, "filter_status": status}


@app.post("/api/v1/parse/tasks/{task_id}/retry")
def retry_task(task_id: str) -> dict[str, Any]:
    result = retry_parse_task(task_id)
    if result is None:
        raw = get_parse_task(task_id)
        if not raw:
            raise _error(404, PARSE_TASK_NOT_FOUND.code, f"parse task not found: {task_id}", PARSE_TASK_NOT_FOUND.retryable, PARSE_TASK_NOT_FOUND.stage)
        raise _error(400, "TASK_NOT_RETRYABLE", f"task {task_id} status={raw.get('status')} is not retryable (only failed tasks can be retried)", False, "validate")
    return {"status": "success", "task": result}


@app.post("/api/v1/parse/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    result = cancel_parse_task(task_id)
    if result is None:
        raw = get_parse_task(task_id)
        if not raw:
            raise _error(404, PARSE_TASK_NOT_FOUND.code, f"parse task not found: {task_id}", PARSE_TASK_NOT_FOUND.retryable, PARSE_TASK_NOT_FOUND.stage)
        raise _error(400, "TASK_NOT_CANCELLABLE", f"task {task_id} status={raw.get('status')} is not cancellable (only pending/queued/running tasks can be cancelled)", False, "validate")
    return {"status": "success", "task": result}


@app.post("/api/v1/parse/files:batch-submit")
def batch_submit_parse_files(request: BatchParseRequest) -> dict[str, Any]:
    if not request.items:
        raise _error(400, "EMPTY_PARSE_ITEMS", "items must not be empty", False, "validate")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in request.items:
        try:
            get_profile_spec(
                _resolve_request_profile(
                    item.profile,
                    item.parse_options,
                    kb_id=request.kb_id,
                )
            )
        except ValueError as exc:
            raise _error(400, PARSE_UNSUPPORTED_PROFILE.code, str(exc), PARSE_UNSUPPORTED_PROFILE.retryable, PARSE_UNSUPPORTED_PROFILE.stage) from exc
        _validate_file_id_binding(request.kb_id, item.file_node_id, item.file_center_file_id or item.file_id)
        task_id = new_parse_task_id(item.file_node_id)
        create_parse_task(
            task_id,
            {
                "kb_id": request.kb_id,
                "task_id": item.task_id,
                "file_node_id": item.file_node_id,
                "file_id": item.file_id,
                "file_center_file_id": item.file_center_file_id,
                "profile": item.profile,
                "parse_generation": item.parse_generation,
                "index_generation": item.index_generation,
                "engine_task_id": item.engine_task_id,
                "parse_strategy_config_id": item.parse_strategy_config_id,
                "parse_options": item.parse_options,
                "model_profile": item.model_profile,
                "request_id": item.request_id,
                "local_file_path": item.local_file_path,
                "return_payload": item.return_payload,
            },
        )
        try:
            enqueue_parse_task(task_id)
        except RuntimeError as exc:
            if "queue full" in str(exc):
                rejected.append({"task_id": task_id, "file_node_id": item.file_node_id, "error": str(exc)})
                continue
            raise
        accepted.append(
            {
                "task_id": task_id,
                "kb_id": request.kb_id,
                "file_node_id": item.file_node_id,
                "file_id": item.file_id,
                "file_center_file_id": item.file_center_file_id,
                "profile": item.profile,
                "local_file_path": item.local_file_path,
                "status": "accepted",
            }
        )
    return {
        "status": "accepted",
        "mode": "batch_submit",
        "kb_id": request.kb_id,
        "task_count": len(accepted),
        "tasks": accepted,
        "rejected": rejected,
        "rejected_count": len(rejected),
    }
