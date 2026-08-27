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
        raise RuntimeError("REDIS_URL must be configured for parse task state")
    return redis.Redis.from_url(url, decode_responses=True)


def _task_key(task_id: str) -> str:
    return f"danbao:parse:task:{task_id}"


def _active_key() -> str:
    return "danbao:parse:active_count"


def _queue_key() -> str:
    return "danbao:parse:queue"


def reset_parse_slots() -> None:
    client = _redis_client()
    client.set(_active_key(), "0")


def _max_concurrency() -> int:
    try:
        return max(1, int(os.getenv("PARSE_MAX_CONCURRENCY", "1")))
    except Exception:
        return 1


def _slot_wait_seconds() -> int:
    try:
        return max(0, int(os.getenv("PARSE_SLOT_WAIT_SECONDS", "1800")))
    except Exception:
        return 1800


def _ttl_seconds() -> int:
    try:
        return max(3600, int(os.getenv("PARSE_TASK_TTL_SECONDS", "172800")))
    except Exception:
        return 172800


def new_parse_task_id(file_node_id: int) -> str:
    return f"parse_{file_node_id}_{new_id()}"


def create_parse_task(task_id: str, payload: dict[str, Any]) -> None:
    client = _redis_client()
    now = int(time.time())
    task = {
        "task_id": task_id,
        "status": "pending",
        "stage": "accepted",
        "kb_id": payload.get("kb_id"),
        "file_node_id": payload.get("file_node_id"),
        "profile": payload.get("profile"),
        "parse_generation": payload.get("parse_generation"),
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
        "request": payload,
    }
    client.set(_task_key(task_id), json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())


def update_parse_task(task_id: str, **fields: Any) -> dict[str, Any]:
    client = _redis_client()
    raw = client.get(_task_key(task_id))
    if not raw:
        raise RuntimeError(f"parse task not found: {task_id}")
    task = json.loads(raw)
    task.update(fields)
    task["updated_at"] = int(time.time())
    client.set(_task_key(task_id), json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())
    return task


def get_parse_task(task_id: str) -> dict[str, Any] | None:
    client = _redis_client()
    raw = client.get(_task_key(task_id))
    return json.loads(raw) if raw else None


def _summarize_task(task: dict[str, Any]) -> dict[str, Any]:
    request = task.get("request") if isinstance(task.get("request"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "stage": task.get("stage"),
        "kb_id": task.get("kb_id"),
        "file_node_id": task.get("file_node_id"),
        "file_id": request.get("file_id"),
        "file_center_file_id": request.get("file_center_file_id"),
        "profile": task.get("profile"),
        "parse_generation": task.get("parse_generation"),
        "index_generation": task.get("index_generation") or result.get("index_generation"),
        "engine_task_id": request.get("engine_task_id") or result.get("engine_task_id"),
        "platform_task_id": request.get("task_id") or result.get("platform_task_id"),
        "request_id": request.get("request_id"),
        "active_count": task.get("active_count"),
        "slot_wait_seconds": task.get("slot_wait_seconds"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "error": task.get("error"),
        "callback": task.get("callback"),
        "summary": result.get("summary") if isinstance(result.get("summary"), dict) else None,
    }


def list_parse_tasks(
    *,
    status: str | None = None,
    kb_id: int | str | None = None,
    file_node_id: int | str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    client = _redis_client()
    rows: list[dict[str, Any]] = []
    for key in client.scan_iter(match=f"{_task_key('*')}", count=200):
        raw = client.get(key)
        if not raw:
            continue
        try:
            task = json.loads(raw)
        except Exception:
            continue
        if status and str(task.get("status") or "") != str(status):
            continue
        if kb_id is not None and str(task.get("kb_id") or "") != str(kb_id):
            continue
        if file_node_id is not None and str(task.get("file_node_id") or "") != str(file_node_id):
            continue
        rows.append(_summarize_task(task))
    rows.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
    return rows[: max(1, min(int(limit or 50), 200))]


def _max_queue_depth() -> int:
    try:
        return int(os.getenv("PARSE_MAX_QUEUE_DEPTH", "20"))
    except Exception:
        return 20


def enqueue_parse_task(task_id: str) -> None:
    client = _redis_client()
    max_queue = _max_queue_depth()
    if max_queue > 0:
        current_len = client.llen(_queue_key())
        if current_len >= max_queue:
            update_parse_task(task_id, status="failed", stage="queue_full", error=f"queue full: {current_len}/{max_queue}")
            raise RuntimeError(f"queue full: {current_len}/{max_queue}")
    client.rpush(_queue_key(), task_id)
    update_parse_task(task_id, status="queued", stage="queued")


def take_next_parse_task(timeout_seconds: int = 3) -> str | None:
    client = _redis_client()
    item = client.blpop(_queue_key(), timeout=timeout_seconds)
    if not item:
        return None
    _, task_id = item
    return task_id


def acquire_parse_slot(task_id: str) -> None:
    client = _redis_client()
    max_concurrency = _max_concurrency()
    wait_seconds = _slot_wait_seconds()
    deadline = time.time() + wait_seconds
    last_wait_update = 0.0
    while True:
        value = client.incr(_active_key())
        if value <= max_concurrency:
            update_parse_task(task_id, status="running", stage="slot_acquired", error=None, active_count=value)
            return

        client.decr(_active_key())
        now = time.time()
        if now - last_wait_update >= 5:
            update_parse_task(
                task_id,
                status="queued",
                stage="waiting_slot",
                error=None,
                active_count=max_concurrency,
                slot_wait_seconds=wait_seconds,
            )
            last_wait_update = now
        if wait_seconds == 0 or now >= deadline:
            message = f"parse concurrency slot wait timeout: {max_concurrency}"
            update_parse_task(task_id, status="failed", stage="busy", error=message, active_count=max_concurrency)
            raise RuntimeError(message)
        time.sleep(1)


def delete_parse_task(task_id: str) -> bool:
    client = _redis_client()
    key = _task_key(task_id)
    if not client.exists(key):
        return False
    client.delete(key)
    return True


def delete_parse_tasks_by_status(status: str) -> int:
    client = _redis_client()
    deleted = 0
    for key in client.scan_iter(match=f"{_task_key('*')}", count=200):
        raw = client.get(key)
        if not raw:
            continue
        try:
            task = json.loads(raw)
        except Exception:
            continue
        if task.get("status") == status:
            client.delete(key)
            deleted += 1
    return deleted


def cancel_parse_task(task_id: str) -> dict[str, Any] | None:
    client = _redis_client()
    raw = client.get(_task_key(task_id))
    if not raw:
        return None
    task = json.loads(raw)
    status = task.get("status")
    if status in ("success", "failed", "cancelled"):
        return None
    task["status"] = "cancelled"
    task["stage"] = "cancelled"
    task["error"] = "user cancelled"
    task["updated_at"] = int(time.time())
    client.set(_task_key(task_id), json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())
    return _summarize_task(task)


def is_parse_task_cancelled(task_id: str) -> bool:
    client = _redis_client()
    raw = client.get(_task_key(task_id))
    if not raw:
        return False
    task = json.loads(raw)
    return task.get("status") == "cancelled"


def retry_parse_task(task_id: str) -> dict[str, Any] | None:
    client = _redis_client()
    raw = client.get(_task_key(task_id))
    if not raw:
        return None
    task = json.loads(raw)
    if task.get("status") not in ("failed",):
        return None
    task["status"] = "queued"
    task["stage"] = "queued"
    task["error"] = None
    task["updated_at"] = int(time.time())
    client.set(_task_key(task_id), json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())
    client.rpush(_queue_key(), task_id)
    return _summarize_task(task)


def release_parse_slot(task_id: str) -> None:
    client = _redis_client()
    try:
        value = client.decr(_active_key())
        if value < 0:
            client.set(_active_key(), "0")
            value = 0
        update_parse_task(task_id, active_count=value)
    except Exception:
        pass


def _stale_seconds() -> int:
    try:
        return max(3600, int(os.getenv("PARSE_TASK_STALE_SECONDS", "43200")))
    except Exception:
        return 43200


def recover_stale_tasks() -> tuple[int, int]:
    """扫描 running/queued 状态的任务，超时的标记 failed，未超时的重新入队。返回 (re-enqueued, failed) 数量。"""
    client = _redis_client()
    now = int(time.time())
    stale_seconds = _stale_seconds()
    recovered = 0
    failed = 0
    for key in client.scan_iter(match=f"{_task_key('*')}", count=200):
        raw = client.get(key)
        if not raw:
            continue
        try:
            task = json.loads(raw)
        except Exception:
            continue
        status = task.get("status")
        if status not in ("running", "queued"):
            continue
        updated_at = int(task.get("updated_at") or 0)
        age = now - updated_at
        if age > stale_seconds:
            task["status"] = "failed"
            task["stage"] = "stale_timeout"
            task["error"] = f"task stale: {age}s > {stale_seconds}s threshold"
            task["updated_at"] = now
            client.set(key, json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())
            failed += 1
        elif status == "running":
            task["status"] = "queued"
            task["stage"] = "recovered"
            task["error"] = None
            task["updated_at"] = now
            client.set(key, json.dumps(task, ensure_ascii=False), ex=_ttl_seconds())
            client.rpush(_queue_key(), task.get("task_id"))
            recovered += 1
    return recovered, failed
