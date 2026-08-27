from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from danbao_poc.api import parse_service, retrieve_service
from danbao_poc.health_checks import readiness
from danbao_poc.metrics import render_prometheus
from danbao_poc.nacos_config_loader import load_nacos_config_to_env
from danbao_poc.profile_config import load_profile_config
from danbao_poc.nacos_client import NacosServiceRegistrar, register_current_service
from danbao_poc.rate_limiter import check_rate_limit


app = FastAPI(title="RAG Doc Service", version="1.0.0")
_nacos_app_registrar: NacosServiceRegistrar | None = None


@app.middleware("http")
async def auth_rate_limit_and_request_id(request: Request, call_next):
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
    if request.url.path.startswith("/api/v1/retrieve"):
        identity = request.headers.get("X-API-Token") or (request.client.host if request.client else "unknown")
        allowed, count, limit = check_rate_limit(
            "retrieve",
            identity,
            "RETRIEVE_RATE_LIMIT_PER_MINUTE",
            "RETRIEVE_RATE_LIMIT_WINDOW_SECONDS",
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "error_code": "RATE_LIMITED",
                        "message": f"retrieve rate limit exceeded: {count}/{limit}",
                        "retryable": True,
                        "stage": "rate_limit",
                        "request_id": request_id,
                    }
                },
                headers={"X-Request-Id": request_id},
            )
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.on_event("startup")
def startup() -> None:
    global _nacos_app_registrar
    print("[startup] begin, APP_ENV=%s" % os.getenv("APP_ENV", "(unset)"), flush=True)
    app_port = os.getenv("APP_PORT", "20751")
    os.environ.setdefault("PARSE_PORT", app_port)
    os.environ.setdefault("RETRIEVE_PORT", app_port)
    os.environ.setdefault("NACOS_PARSE_REGISTER_PORT", app_port)
    os.environ.setdefault("NACOS_RETRIEVE_REGISTER_PORT", app_port)
    try:
        load_profile_config()
    except Exception as exc:
        print(f"[startup] ERROR in load_profile_config: {exc}", flush=True)
        import traceback; traceback.print_exc()
    print("[startup] NACOS_SERVER_ADDR=%s" % os.getenv("NACOS_SERVER_ADDR", "(unset)"), flush=True)
    print("[startup] NACOS_ENABLED=%s" % os.getenv("NACOS_ENABLED", "(unset)"), flush=True)
    load_nacos_config_to_env()
    parse_service.startup()
    retrieve_service.startup()
    _nacos_app_registrar = register_current_service(
        "NACOS_APP_SERVICE_NAME",
        "app-rag-doc",
        "APP_PORT",
        {"service": "app-rag-doc", "version": app.version or ""},
        fallback_port_env="APP_PORT",
    )


@app.on_event("shutdown")
def shutdown() -> None:
    parse_service.shutdown()
    retrieve_service.shutdown()
    if _nacos_app_registrar:
        _nacos_app_registrar.stop()


@app.get("/health")
def health() -> dict[str, Any]:
    from danbao_poc import BUILD_TAG
    return {"status": "ok", "service": "app-rag-doc", "modules": ["parse-service", "retrieve-service"], "build_tag": BUILD_TAG}


@app.get("/ready")
def ready() -> dict[str, Any]:
    return readiness(include_es=True, include_file_center=True, include_java=True)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


def _copy_routes(source: FastAPI) -> None:
    skipped = {"/health", "/ready", "/metrics"}
    for route in source.router.routes:
        if getattr(route, "path", None) in skipped:
            continue
        app.router.routes.append(route)


_copy_routes(parse_service.app)
_copy_routes(retrieve_service.app)
