from __future__ import annotations

import json
import os
import time
from typing import Any

import redis

from .ids import new_id


def _redis_client() -> redis.Redis:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        raise RuntimeError("REDIS_URL must be configured for index task state")
    return redis.Redis.from_url(url, decode_responses=True)


def _task_key(task_id: str) -> str:
    return f"danbao:index:task:{task_id}"


def _queue_key() -> str:
    return "danbao:index:queue"


def _ttl_seconds() -> int:
    try:
        return max(3600, int(os.getenv("INDEX_TASK_TTL_SECONDS", "172800")))
    except Exception:
        return 172800


def new_index_task_id(file_node_id: int) -> str:
    return f"index_{file_node_id}_{new_id()}"


def create_index_task(task_id: str, payload: dict[str, Any]) -> None:
    now = int(time.time())
    task = {
        "task_id": task_id,
        "status": "pending",
        "stage": "accepted",
        "kb_id": payload.get("kb_id"),
        "file_node_id": payload.get("file_node_id"),
        "parse_generation": payload.get("parse_generation"),
        "index_generation": payload.get("index_generation"),
        "operation": payload.get("operation"),
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
        "request": payload,
    }
    _redis_client().set(_task_key(task_id), json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())


def update_index_task(task_id: str, **fields: Any) -> dict[str, Any]:
    client = _redis_client()
    raw = client.get(_task_key(task_id))
    if not raw:
        raise RuntimeError(f"index task not found: {task_id}")
    task = json.loads(raw)
    task.update(fields)
    task["updated_at"] = int(time.time())
    client.set(_task_key(task_id), json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())
    return task


def get_index_task(task_id: str) -> dict[str, Any] | None:
    raw = _redis_client().get(_task_key(task_id))
    return json.loads(raw) if raw else None


def enqueue_index_task(task_id: str) -> None:
    _redis_client().rpush(_queue_key(), task_id)
    update_index_task(task_id, status="queued", stage="queued")


def take_next_index_task(timeout_seconds: int = 3) -> str | None:
    item = _redis_client().blpop(_queue_key(), timeout=timeout_seconds)
    if not item:
        return None
    _, task_id = item
    return task_id


def delete_index_task(task_id: str) -> bool:
    """Delete a task from Redis. Returns True if deleted, False if not found."""
    client = _redis_client()
    deleted = client.delete(_task_key(task_id))
    return deleted > 0


def retry_index_task(task_id: str) -> dict[str, Any] | None:
    """Retry a failed/cancelled task by re-enqueueing it. Returns updated task or None if not found."""
    task = get_index_task(task_id)
    if not task:
        return None
    if task.get("status") not in {"failed", "cancelled"}:
        raise RuntimeError(f"cannot retry task with status '{task.get('status')}'")
    updated = update_index_task(task_id, status="queued", stage="queued", error=None)
    enqueue_index_task(task_id)
    return updated
