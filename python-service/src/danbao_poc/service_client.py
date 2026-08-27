from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests

from danbao_poc.nacos_client import nacos_enabled, resolve_service_base_url
from danbao_poc.settings import env_int, env_str, service_auth_settings

logger = logging.getLogger(__name__)


class ServiceClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.service_name = service_name
        self.status_code = status_code
        self.response_body = response_body
        self.retryable = retryable


@dataclass(frozen=True)
class ServiceClientConfig:
    service_name: str | None
    base_url: str | None
    context_path: str | None
    scheme: str | None
    timeout: int
    retries: int


class ServiceClient:
    def __init__(
        self,
        *,
        service_name: str | None = None,
        base_url: str | None = None,
        context_path: str | None = None,
        scheme: str | None = None,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        self.config = ServiceClientConfig(
            service_name=(service_name or "").strip() or None,
            base_url=(base_url or "").strip().rstrip("/") or None,
            context_path=(context_path or "").strip() or None,
            scheme=(scheme or "").strip() or None,
            timeout=timeout or env_int("SERVICE_CLIENT_TIMEOUT", 30),
            retries=max(0, retries if retries is not None else env_int("SERVICE_CLIENT_RETRIES", 2)),
        )

    def _base_url(self) -> str:
        if self.config.base_url:
            return self.config.base_url
        if not self.config.service_name:
            raise ServiceClientError("service name or base_url must be configured", service_name=None, retryable=False)
        if not nacos_enabled():
            raise ServiceClientError(
                f"Nacos is disabled and no base_url is configured for service {self.config.service_name}",
                service_name=self.config.service_name,
                retryable=False,
            )
        return resolve_service_base_url(
            self.config.service_name,
            context_path=self.config.context_path,
            scheme=self.config.scheme,
        )

    def _headers(self, headers: dict[str, str] | None = None, request_id: str | None = None) -> dict[str, str]:
        merged = dict(headers or {})
        auth = service_auth_settings()
        if auth.header and auth.token:
            merged.setdefault(auth.header, auth.token)
        merged.setdefault(auth.request_id_header, request_id or f"req_{uuid.uuid4().hex}")
        return merged

    def request(
        self,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        last_exc: Exception | None = None
        normalized_path = f"/{path.lstrip('/')}"
        attempts = self.config.retries + 1
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                base_url = self._base_url()
                response = requests.request(
                    method,
                    f"{base_url}{normalized_path}",
                    headers=self._headers(headers, request_id),
                    timeout=self.config.timeout,
                    **kwargs,
                )
                cost_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "downstream request service=%s method=%s path=%s status=%s cost_ms=%s",
                    self.config.service_name or base_url,
                    method.upper(),
                    normalized_path,
                    response.status_code,
                    cost_ms,
                )
                if response.status_code >= 500 and attempt < attempts - 1:
                    last_exc = ServiceClientError(
                        f"downstream returned {response.status_code}",
                        service_name=self.config.service_name,
                        status_code=response.status_code,
                        response_body=response.text[:1000],
                        retryable=True,
                    )
                    time.sleep(min(2.0, 0.2 * (2**attempt)))
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError, ServiceClientError) as exc:
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                time.sleep(min(2.0, 0.2 * (2**attempt)))
            except requests.HTTPError as exc:
                response = exc.response
                raise ServiceClientError(
                    f"downstream returned {response.status_code if response is not None else 'HTTP error'}",
                    service_name=self.config.service_name,
                    status_code=response.status_code if response is not None else None,
                    response_body=response.text[:1000] if response is not None else None,
                    retryable=response is not None and response.status_code >= 500,
                ) from exc
        raise ServiceClientError(
            f"downstream request failed: {last_exc}",
            service_name=self.config.service_name,
            retryable=True,
        ) from last_exc

    def json(
        self,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        response = self.request(method, path, request_id=request_id, headers=headers, **kwargs)
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceClientError(
                "downstream response is not valid JSON",
                service_name=self.config.service_name,
                status_code=response.status_code,
                response_body=response.text[:1000],
                retryable=False,
            ) from exc
        if isinstance(data, dict) and "code" in data and data.get("code") not in {0, "0", None}:
            raise ServiceClientError(
                str(data.get("message") or data.get("msg") or "downstream business error"),
                service_name=self.config.service_name,
                status_code=response.status_code,
                response_body=response.text[:1000],
                retryable=False,
            )
        return data

    def ready(self) -> dict[str, Any]:
        try:
            base_url = self._base_url()
            return {"status": "ok", "base_url": base_url, "service_name": self.config.service_name}
        except Exception as exc:
            return {"status": "error", "service_name": self.config.service_name, "error": str(exc)}


def configured_service_name(primary_env: str, fallback_env: str | None = None) -> str:
    return env_str(primary_env) or (env_str(fallback_env) if fallback_env else "")

