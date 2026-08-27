from __future__ import annotations

import logging
from typing import Any

from danbao_poc.service_client import ServiceClient, ServiceClientError, configured_service_name
from danbao_poc.settings import env_int, env_str

logger = logging.getLogger(__name__)


class JavaBackendClient:
    def __init__(
        self,
        *,
        service_name: str | None = None,
        base_url: str | None = None,
        context_path: str | None = None,
        scheme: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.service_name = (service_name or configured_service_name("JAVA_PLATFORM_SERVICE_NAME")).strip()
        self.base_url = (base_url or env_str("JAVA_PLATFORM_BASE_URL")).strip().rstrip("/")
        self.callback_path = env_str("JAVA_PARSE_CALLBACK_PATH", "/internal/platform/parse-callback")
        self.client = ServiceClient(
            service_name=self.service_name or None,
            base_url=self.base_url or None,
            context_path=context_path or env_str("JAVA_PLATFORM_CONTEXT_PATH") or None,
            scheme=scheme or env_str("JAVA_PLATFORM_SCHEME") or None,
            timeout=timeout or env_int("JAVA_SERVICE_TIMEOUT", 30),
            retries=env_int("JAVA_SERVICE_RETRIES", 2),
        )

    def is_configured(self) -> bool:
        return bool(self.service_name or self.base_url)

    def callback_parse_task(
        self,
        *,
        task_id: int | str,
        file_node_id: int | str,
        kb_id: int | str,
        stage: str,
        status: str,
        parse_generation: str | None = None,
        index_generation: str | None = None,
        engine_task_id: str | None = None,
        indexed_chunk_count: int | None = None,
        parse_result_url: str | None = None,
        error_msg: str | None = None,
        retryable: bool | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise ServiceClientError("JAVA_PLATFORM_SERVICE_NAME or JAVA_PLATFORM_BASE_URL is not configured")
        payload: dict[str, Any] = {
            "task_id": task_id,
            "file_node_id": file_node_id,
            "kb_id": kb_id,
            "stage": stage,
            "status": status,
            "parse_generation": parse_generation,
            "index_generation": index_generation,
            "engine_task_id": engine_task_id,
            "indexed_chunk_count": indexed_chunk_count,
            "parse_result_url": parse_result_url,
            "error_msg": error_msg,
        }
        if retryable is not None:
            payload["retryable"] = retryable
        payload = {key: value for key, value in payload.items() if value is not None}
        data = self.client.json("POST", self.callback_path, json=payload, request_id=request_id)
        if isinstance(data, dict):
            return data
        return {"data": data}


def callback_enabled() -> bool:
    return env_str("JAVA_CALLBACK_ENABLED", "true").lower() in {"1", "true", "yes", "y", "on"}


def safe_callback_parse_task(**kwargs: Any) -> dict[str, Any]:
    if not callback_enabled():
        return {"status": "skipped", "reason": "JAVA_CALLBACK_ENABLED=false"}
    client = JavaBackendClient()
    if not client.is_configured():
        return {"status": "skipped", "reason": "java backend not configured"}
    try:
        result = client.callback_parse_task(**kwargs)
        return {"status": "success", "response": result}
    except Exception as exc:
        logger.warning("failed to callback Java platform: %s", exc)
        return {"status": "failed", "error": str(exc)}

