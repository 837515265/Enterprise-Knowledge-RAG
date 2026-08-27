from __future__ import annotations

from typing import Any

import redis

from danbao_poc.es_store import client as es_client
from danbao_poc.file_center_client import FileCenterClient
from danbao_poc.java_backend_client import JavaBackendClient
from danbao_poc.mysql_store import connect
from danbao_poc.settings import env_str


def _check_mysql() -> dict[str, Any]:
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_redis() -> dict[str, Any]:
    try:
        url = env_str("REDIS_URL")
        if not url:
            return {"status": "skipped", "reason": "REDIS_URL not configured"}
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_es() -> dict[str, Any]:
    try:
        es = es_client()
        ok = es.ping()
        return {"status": "ok" if ok else "error", "error": None if ok else "Elasticsearch ping failed"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_file_center() -> dict[str, Any]:
    try:
        client = FileCenterClient()
        return {"status": "ok", "base_url": client.base_url}
    except Exception as exc:
        return {"status": "skipped" if not env_str("FILE_CENTER_BASE_URL") and not env_str("FILE_CENTER_SERVICE_NAME") and not env_str("NACOS_FILE_CENTER_SERVICE_NAME") else "error", "error": str(exc)}


def _check_java_platform() -> dict[str, Any]:
    try:
        client = JavaBackendClient()
        if not client.is_configured():
            return {"status": "skipped", "reason": "JAVA_PLATFORM_SERVICE_NAME/JAVA_PLATFORM_BASE_URL not configured"}
        return client.client.ready()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def readiness(*, include_es: bool = True, include_file_center: bool = True, include_java: bool = True) -> dict[str, Any]:
    dependencies: dict[str, Any] = {
        "mysql": _check_mysql(),
        "redis": _check_redis(),
    }
    if include_es:
        dependencies["elasticsearch"] = _check_es()
    if include_file_center:
        dependencies["file_center"] = _check_file_center()
    if include_java:
        dependencies["java_platform"] = _check_java_platform()
    hard_failures = {name: item for name, item in dependencies.items() if item.get("status") == "error"}
    return {
        "status": "ok" if not hard_failures else "degraded",
        "dependencies": dependencies,
    }

