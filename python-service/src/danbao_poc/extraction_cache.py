from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid
from typing import Any


def build_extraction_cache_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_root() -> Path:
    return Path(os.getenv("KNOWLEDGE_EXTRACTION_CACHE_DIR", "/data/cache/knowledge-extraction"))


def load_extraction_cache(cache_key: str) -> dict[str, Any] | None:
    if not cache_key:
        return None
    try:
        path = _cache_root() / cache_key[:2] / f"{cache_key}.json"
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("cache_key") != cache_key:
            return None
        return payload
    except Exception:
        return None


def save_extraction_cache(cache_key: str, payload: dict[str, Any]) -> bool:
    if not cache_key or not isinstance(payload, dict):
        return False
    try:
        directory = _cache_root() / cache_key[:2]
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{cache_key}.json"
        temporary = directory / f".{cache_key}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps({"cache_key": cache_key, **payload}, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(target)
        return True
    except Exception:
        return False
