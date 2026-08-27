from __future__ import annotations

import logging
import os
import time

import redis

logger = logging.getLogger(__name__)


def _redis_client() -> redis.Redis | None:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def check_rate_limit(scope: str, identity: str, limit_env: str, window_env: str) -> tuple[bool, int, int]:
    limit = int(os.getenv(limit_env, "0") or "0")
    window = max(1, int(os.getenv(window_env, "60") or "60"))
    if limit <= 0:
        return True, 0, limit
    identity = identity or "anonymous"
    client = _redis_client()
    current_window = int(time.time()) // window
    key = f"danbao:rate:{scope}:{identity}:{current_window}"
    if client is None:
        return True, 0, limit
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, window * 2)
    return count <= limit, count, limit


_LLM_ACTIVE_KEY = "danbao:llm:active_count"


def _llm_max_concurrency() -> int:
    try:
        return max(1, int(os.getenv("LLM_MAX_CONCURRENCY", "3")))
    except Exception:
        return 3


def _llm_slot_wait_seconds() -> int:
    try:
        return max(0, int(os.getenv("LLM_SLOT_WAIT_SECONDS", "300")))
    except Exception:
        return 300


def acquire_llm_slot(task_id: str = "") -> int:
    """阻塞等待 LLM 并发槽，返回当前占用数。超时抛 RuntimeError。"""
    client = _redis_client()
    if client is None:
        return 0
    max_concurrency = _llm_max_concurrency()
    wait_seconds = _llm_slot_wait_seconds()
    deadline = time.time() + wait_seconds
    while True:
        value = client.incr(_LLM_ACTIVE_KEY)
        if value <= max_concurrency:
            return value
        client.decr(_LLM_ACTIVE_KEY)
        if wait_seconds == 0 or time.time() >= deadline:
            raise RuntimeError(f"llm concurrency slot wait timeout: {max_concurrency}")
        time.sleep(1)


def release_llm_slot() -> int:
    """释放 LLM 并发槽，返回剩余占用数。"""
    client = _redis_client()
    if client is None:
        return 0
    value = client.decr(_LLM_ACTIVE_KEY)
    if value < 0:
        client.set(_LLM_ACTIVE_KEY, "0")
        return 0
    return value


def reset_llm_slots() -> None:
    """重置 LLM 并发计数（服务启动时调用）。"""
    client = _redis_client()
    if client is not None:
        client.set(_LLM_ACTIVE_KEY, "0")
