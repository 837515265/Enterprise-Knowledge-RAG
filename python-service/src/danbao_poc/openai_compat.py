from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from .prompt_views import build_rerank_document
from .rate_limiter import check_rate_limit
from .retrieve_cache import get_json_cached, set_json_cached

logger = logging.getLogger(__name__)


class ModelClientError(RuntimeError):
    pass


class ModelResponseError(ModelClientError):
    pass


class ModelTransportError(ModelClientError):
    pass


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _proxy_config() -> dict[str, str]:
    http_proxy = os.getenv("MODEL_HTTP_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("MODEL_HTTPS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    proxies: dict[str, str] = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies


def _inner_proxy_enabled() -> bool:
    return os.getenv("LLM_PROXY_ENABLED", "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_inner_proxy_url() -> str:
    """Resolve common-inner-proxy base URL from Nacos or env override."""
    override = os.getenv("LLM_PROXY_BASE_URL", "").strip()
    if override:
        return override.rstrip("/")
    try:
        from .nacos_client import nacos_enabled, resolve_service_base_url
        if not nacos_enabled():
            raise RuntimeError("Nacos is disabled, set LLM_PROXY_BASE_URL instead")
        service_name = os.getenv("LLM_PROXY_SERVICE_NAME", "common-inner-proxy")
        return resolve_service_base_url(service_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to resolve inner proxy URL: {exc}") from exc


class ProxyModelClient:
    """Routes model requests through common-inner-proxy service."""

    def __init__(self, api_key: str, timeout: int, client_name: str) -> None:
        self.api_key = api_key or "EMPTY"
        self.timeout = timeout
        self.client_name = client_name
        self.apply_app_id = os.getenv("LLM_PROXY_APPLY_APP_ID", "APP_KNOWLEDGE_SERVICE")
        self.session = requests.Session()
        proxies = _proxy_config()
        if proxies:
            self.session.proxies.update(proxies)
        self._proxy_url: str | None = None

    def _get_proxy_url(self) -> str:
        if self._proxy_url is None:
            self._proxy_url = _resolve_inner_proxy_url()
        return self._proxy_url

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        proxy_url = self._get_proxy_url()
        endpoint = f"{proxy_url}/proxy/inner/request"

        # Default to chat-completions; allow per-client override via env
        interface_id = "chat-completions"
        _path = path.rstrip("/").lower()
        if _path.endswith("/embeddings") or "/embeddings" in _path:
            interface_id = os.getenv("EMBEDDING_PROXY_INTERFACE_ID", "chat-completions").strip() or "chat-completions"
        elif _path.endswith("/rerank") or "/rerank" in _path:
            interface_id = os.getenv("RERANK_PROXY_INTERFACE_ID", "chat-completions").strip() or "chat-completions"

        # Wrap in proxy envelope
        envelope = {
            "thirdAppId": "NEW_API",
            "thirdInterfaceId": interface_id,
            "applyAppId": self.apply_app_id,
            "thirdUrl": f"/v1{path}" if not path.startswith("/v1") else path,
            "methodType": "POST",
            "contentType": "application/json",
            "headerMap": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            "data": dict(payload),
        }
        # api_key also in data for compatibility
        envelope["data"]["api_key"] = self.api_key

        allowed, count, limit = check_rate_limit(
            f"model:{self.client_name}",
            payload.get("model") or self.client_name,
            "MODEL_RATE_LIMIT_PER_MINUTE",
            "MODEL_RATE_LIMIT_WINDOW_SECONDS",
        )
        if not allowed:
            raise ModelTransportError(f"{self.client_name} model rate limit exceeded: {count}/{limit}")

        from .rate_limiter import acquire_llm_slot, release_llm_slot
        acquire_llm_slot()
        try:
            response = self.session.post(endpoint, json=envelope, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ModelTransportError(f"{self.client_name} proxy request failed: {exc}") from exc
        finally:
            release_llm_slot()

        if response.status_code >= 500:
            raise ModelTransportError(f"{self.client_name} proxy server error: {response.status_code} {response.text[:500]}")
        if response.status_code >= 400:
            raise ModelResponseError(f"{self.client_name} proxy client error: {response.status_code} {response.text[:500]}")

        try:
            result = response.json()
        except Exception as exc:
            raise ModelResponseError(f"{self.client_name} proxy returned non-json: {response.text[:500]}") from exc

        # Unwrap proxy envelope
        code = result.get("resp_code") if "resp_code" in result else result.get("code")
        if code not in (0, 200, None):
            msg = result.get("resp_msg") or result.get("msg") or result.get("message") or "unknown proxy error"
            raise ModelResponseError(f"{self.client_name} proxy error: code={code}, msg={msg}")

        datas = result.get("datas") if "datas" in result else result.get("data") or result.get("result")
        if datas is None:
            raise ModelResponseError(f"{self.client_name} proxy returned empty datas: {json.dumps(result, ensure_ascii=False)[:500]}")

        # datas can be a dict (JSON response) or a string (SSE or JSON string)
        if isinstance(datas, dict):
            return datas
        if isinstance(datas, str):
            try:
                return json.loads(datas)
            except Exception:
                raise ModelResponseError(f"{self.client_name} proxy datas is not valid JSON: {datas[:500]}")
        raise ModelResponseError(f"{self.client_name} unexpected datas type: {type(datas).__name__}")


class HttpModelClient:
    def __init__(self, base_url: str, api_key: str, timeout: int, client_name: str) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.api_key = api_key or "EMPTY"
        self.timeout = timeout
        self.client_name = client_name
        self.session = requests.Session()
        self.session.headers.update(_headers(self.api_key))
        proxies = _proxy_config()
        if proxies:
            self.session.proxies.update(proxies)
        self._proxy_client: ProxyModelClient | None = None
        if _inner_proxy_enabled():
            self._proxy_client = ProxyModelClient(api_key, timeout, client_name)
            print(f"[proxy] HttpModelClient({client_name}) routed through inner proxy", flush=True)

    @retry(
        retry=retry_if_exception_type((ModelTransportError, ModelResponseError)),
        stop=stop_after_attempt(max(1, _int_env("MODEL_RETRY_ATTEMPTS", 3))),
        wait=wait_random_exponential(
            multiplier=_float_env("MODEL_RETRY_MULTIPLIER", 1.0),
            min=_float_env("MODEL_RETRY_MIN_SECONDS", 1.0),
            max=_float_env("MODEL_RETRY_MAX_SECONDS", 8.0),
        ),
        reraise=True,
    )
    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._proxy_client is not None:
            return self._proxy_client.post_json(path, payload)
        url = f"{self.base_url}{path}"
        allowed, count, limit = check_rate_limit(
            f"model:{self.client_name}",
            payload.get("model") or self.client_name,
            "MODEL_RATE_LIMIT_PER_MINUTE",
            "MODEL_RATE_LIMIT_WINDOW_SECONDS",
        )
        if not allowed:
            raise ModelTransportError(f"{self.client_name} model rate limit exceeded: {count}/{limit}")
        from .rate_limiter import acquire_llm_slot, release_llm_slot
        acquire_llm_slot()
        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ModelTransportError(f"{self.client_name} request failed: {exc}") from exc
        finally:
            release_llm_slot()
        if response.status_code >= 500:
            raise ModelTransportError(f"{self.client_name} server error: {response.status_code} {response.text[:500]}")
        if response.status_code >= 400:
            raise ModelResponseError(f"{self.client_name} client error: {response.status_code} {response.text[:500]}")
        try:
            return response.json()
        except Exception as exc:
            raise ModelResponseError(f"{self.client_name} returned non-json response: {response.text[:500]}") from exc


class EmbeddingClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("DEFAULT_MODEL_BASE_URL", "")
        self.api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("DEFAULT_MODEL_API_KEY", "EMPTY")
        self.model = os.getenv("EMBEDDING_MODEL_NAME", "")
        self.timeout = _int_env("EMBEDDING_TIMEOUT", 120)
        if not self.base_url or not self.model:
            raise RuntimeError("EMBEDDING_BASE_URL and EMBEDDING_MODEL_NAME must be configured")
        self.http = HttpModelClient(self.base_url, self.api_key, self.timeout, "embedding")
        self.max_batch_size = max(1, _int_env("EMBEDDING_MAX_BATCH_SIZE", 64))
        self.retry_attempts = max(1, _int_env("EMBEDDING_RETRY_ATTEMPTS", 3))
        self.retry_delay = max(1.0, _float_env("EMBEDDING_RETRY_DELAY_SECONDS", 3.0))

    def embed_texts(self, texts: list[str], cache_context: dict[str, Any] | None = None) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float] | None] = [None] * len(texts)
        misses: list[tuple[int, str, dict[str, Any]]] = []
        if cache_context:
            for idx, text in enumerate(texts):
                payload = {"model": self.model, "text": text, "context": cache_context}
                cached = get_json_cached("query_embedding", payload)
                if isinstance(cached, list) and cached:
                    vectors[idx] = [float(value) for value in cached]
                else:
                    misses.append((idx, text, payload))
        else:
            misses = [(idx, text, {}) for idx, text in enumerate(texts)]

        for start in range(0, len(misses), self.max_batch_size):
            batch_items = misses[start : start + self.max_batch_size]
            batch = [text for _, text, _ in batch_items]
            payload = {"model": self.model, "input": batch}
            data = None
            for attempt in range(self.retry_attempts):
                try:
                    data = self.http.post_json("/embeddings", payload)
                    break
                except (ModelClientError, ModelTransportError) as exc:
                    if attempt < self.retry_attempts - 1:
                        delay = self.retry_delay * (attempt + 1)
                        logger.warning("embedding batch %d/%d failed (attempt %d/%d), retrying in %.1fs: %s",
                                       start // self.max_batch_size + 1,
                                       (len(misses) + self.max_batch_size - 1) // self.max_batch_size,
                                       attempt + 1, self.retry_attempts, delay, exc)
                        time.sleep(delay)
                    else:
                        raise
            items = sorted(data.get("data") or [], key=lambda item: item.get("index", 0))
            if len(items) != len(batch_items):
                raise ModelResponseError(f"embedding result count mismatch: expected {len(batch_items)}, got {len(items)}")
            for (idx, _, cache_payload), item in zip(batch_items, items):
                embedding = item.get("embedding")
                vectors[idx] = embedding
                if cache_context:
                    set_json_cached(
                        "query_embedding",
                        cache_payload,
                        embedding,
                        ttl_env="QUERY_EMBEDDING_CACHE_TTL_SECONDS",
                        default_ttl_seconds=86400,
                    )
        if any(vector is None for vector in vectors):
            raise ModelResponseError(f"embedding result count mismatch: expected {len(texts)}, got incomplete result")
        return [vector for vector in vectors if vector is not None]


class JsonChatClient:
    def __init__(self, prefix: str, default_model: bool = False, enable_fallback: bool = True) -> None:
        prefix = prefix.upper().rstrip("_")
        self.prefix = prefix
        self.base_url = os.getenv(f"{prefix}_BASE_URL", "")
        self.api_key = os.getenv(f"{prefix}_API_KEY", "")
        self.model = os.getenv(f"{prefix}_MODEL_NAME", "")
        self.timeout = _int_env(f"{prefix}_TIMEOUT", 120)
        self.enable_fallback = enable_fallback
        self.max_prompt_chars = _int_env(f"{prefix}_MAX_PROMPT_CHARS", _int_env("DEFAULT_MODEL_MAX_PROMPT_CHARS", 28000))

        if default_model:
            self.base_url = self.base_url or os.getenv("DEFAULT_MODEL_BASE_URL", "")
            self.api_key = self.api_key or os.getenv("DEFAULT_MODEL_API_KEY", "EMPTY")
            self.model = self.model or os.getenv("DEFAULT_MODEL_NAME", "")

        if not self.base_url or not self.model:
            raise RuntimeError(f"{prefix}_BASE_URL and {prefix}_MODEL_NAME must be configured")
        self.http = HttpModelClient(self.base_url, self.api_key or "EMPTY", self.timeout, prefix.lower())

        self.fallback_base_url = os.getenv("FALLBACK_MODEL_BASE_URL", "")
        self.fallback_api_key = os.getenv("FALLBACK_MODEL_API_KEY", "EMPTY")
        self.fallback_model = os.getenv("FALLBACK_MODEL_NAME", "")
        self.fallback_timeout = _int_env("FALLBACK_MODEL_TIMEOUT", self.timeout)
        self.fallback_http = (
            HttpModelClient(self.fallback_base_url, self.fallback_api_key, self.fallback_timeout, f"{prefix.lower()}_fallback")
            if self.fallback_base_url and self.fallback_model and self.enable_fallback
            else None
        )

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = self._payload(self.model, system_prompt, user_prompt, temperature, max_tokens)
        prompt_size = len(system_prompt) + len(user_prompt)
        use_fallback_first = self.fallback_http is not None and prompt_size > self.max_prompt_chars

        if use_fallback_first:
            return self._complete_with_http(self.fallback_http, self.fallback_model, system_prompt, user_prompt, temperature, max_tokens)

        try:
            return self._complete_with_http(self.http, self.model, system_prompt, user_prompt, temperature, max_tokens)
        except ModelClientError:
            if self.fallback_http is None:
                raise
            return self._complete_with_http(self.fallback_http, self.fallback_model, system_prompt, user_prompt, temperature, max_tokens)

    def _payload(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "stream": False,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    def _complete_with_http(
        self,
        http: HttpModelClient,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload = self._payload(model, system_prompt, user_prompt, temperature, max_tokens)
        data = http.post_json("/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ModelResponseError(f"{http.client_name} response missing choices/message/content") from exc
        try:
            return json.loads(content)
        except Exception as exc:
            raise ModelResponseError(f"{http.client_name} returned invalid json content: {content[:500]}") from exc


class RerankClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("RERANK_BASE_URL") or os.getenv("DEFAULT_MODEL_BASE_URL", "")
        self.api_key = os.getenv("RERANK_API_KEY") or os.getenv("DEFAULT_MODEL_API_KEY", "EMPTY")
        self.model = os.getenv("RERANK_MODEL_NAME", "") or os.getenv("DEFAULT_MODEL_NAME", "")
        self.timeout = _int_env("RERANK_TIMEOUT", 120)
        self.rerank_path = os.getenv("RERANK_PATH", "/rerank")
        self.http = HttpModelClient(self.base_url, self.api_key, self.timeout, "rerank_native") if self.base_url and self.model else None

    def rerank(self, query: str, candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if not candidates:
            return []
        native = self._rerank_native(query, candidates, top_k)
        return native

    def _rerank_native(self, query: str, candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if self.http is None:
            return []
        documents = [build_rerank_document(item) for item in candidates]
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_k,
        }
        try:
            data = self.http.post_json(self.rerank_path, payload)
        except ModelClientError:
            return []
        items = data.get("results") or data.get("data") or []
        by_index = {idx: item for idx, item in enumerate(candidates)}
        results: list[dict[str, Any]] = []
        for rank, row in enumerate(items[:top_k], 1):
            idx = row.get("index")
            if idx is None or idx not in by_index:
                continue
            item = dict(by_index[idx])
            item["rank"] = rank
            item["rerank_score"] = float(row.get("relevance_score") or row.get("score") or (top_k - rank + 1))
            results.append(item)
        return results


def _build_rerank_prompt(query: str, candidates: list[dict[str, Any]], top_k: int) -> str:
    compact = []
    for item in candidates:
        compact.append(
            {
                "candidate_id": item["candidate_id"],
                "hit_type": item.get("hit_type"),
                "field_code": item.get("field_code"),
                "title": item.get("title"),
                "content": item.get("content"),
                "value_text": item.get("value_text"),
                "evidence_text": item.get("evidence_text"),
            }
        )
    return (
        "请根据用户问题对候选证据进行相关性重排。\n\n"
        "## 排序规则\n"
        "1. 直接回答问题、包含具体数值/条件/步骤的候选优先。\n"
        "2. 字段类型与问题匹配的候选优先（如问额度时，field_code=credit_limit 的候选优先）。\n"
        "3. 只包含章节标题但没有正文内容的候选应排在最后。\n"
        "4. 证据文本（evidence_text）越具体越完整的候选排名越高。\n\n"
        f"返回格式：{{\"ordered_ids\": [\"c1\", \"c2\"]}}，最多返回 {top_k} 个 candidate_id。\n\n"
        f"用户问题：{query}\n\n"
        f"候选证据：{json.dumps(compact, ensure_ascii=False)}"
    )
