from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import redis


def _redis_client() -> redis.Redis | None:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def cache_enabled() -> bool:
    return os.getenv("RETRIEVE_CACHE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y", "on"}


def cache_key(payload: dict[str, Any], namespace: str = "retrieve") -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"danbao:{namespace}:cache:{digest}"


def get_json_cached(namespace: str, payload: dict[str, Any]) -> Any | None:
    if not cache_enabled():
        return None
    client = _redis_client()
    if client is None:
        return None
    raw = client.get(cache_key(payload, namespace))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def set_json_cached(
    namespace: str,
    payload: dict[str, Any],
    value: Any,
    *,
    ttl_env: str,
    default_ttl_seconds: int,
) -> None:
    if not cache_enabled():
        return
    client = _redis_client()
    if client is None:
        return
    try:
        ttl = max(1, int(os.getenv(ttl_env, str(default_ttl_seconds))))
        client.set(cache_key(payload, namespace), json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except Exception:
        return


def get_cached(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = get_json_cached("retrieve", payload)
    if isinstance(data, dict):
        if not isinstance(data.get("debug"), dict):
            data["debug"] = {}
        data["debug"]["cache_hit"] = True
        return data
    return None


def set_cached(payload: dict[str, Any], response: dict[str, Any]) -> None:
    set_json_cached(
        "retrieve",
        payload,
        response,
        ttl_env="RETRIEVE_CACHE_TTL_SECONDS",
        default_ttl_seconds=86400,
    )
