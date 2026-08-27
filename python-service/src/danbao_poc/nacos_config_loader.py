from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from danbao_poc.nacos_client import NacosClient, env_bool, nacos_enabled


logger = logging.getLogger(__name__)


def default_config_data_id() -> str:
    app_name = os.getenv("NACOS_APP_SERVICE_NAME") or os.getenv("SERVICE_NAME") or "app-rag-doc"
    app_env = os.getenv("APP_ENV", "dev").strip() or "dev"
    return f"{app_name}-{app_env}"


def load_nacos_config_to_env() -> dict[str, str]:
    if not nacos_enabled() or not env_bool("NACOS_CONFIG_ENABLED", True):
        print("[nacos_config] skipped: nacos_enabled or config_enabled is false", flush=True)
        return {}
    data_id = os.getenv("NACOS_CONFIG_DATA_ID", "").strip() or default_config_data_id()
    group = os.getenv("NACOS_CONFIG_GROUP", os.getenv("NACOS_GROUP_NAME", "DEFAULT_GROUP"))
    try:
        client = NacosClient()
        raw = get_config_with_fallback(client, data_id, group)
    except Exception as exc:
        print(f"[nacos_config] config not found or unreachable ({data_id}), skipped: {exc}", flush=True)
        logger.warning("Nacos config %s/%s not available, using env vars only: %s", group, data_id, exc)
        return {}
    try:
        values = parse_config_values(raw)
        override = env_bool("NACOS_CONFIG_OVERRIDE_ENV", False)
        applied: dict[str, str] = {}
        for key, value in values.items():
            if value is None:
                continue
            normalized_key = normalize_env_key(key)
            if not normalized_key:
                continue
            if not override:
                env_val = os.getenv(normalized_key)
                if env_val is not None and env_val.strip().strip('"').strip("'") != "":
                    continue
            normalized_value = str(value)
            os.environ[normalized_key] = normalized_value
            applied[normalized_key] = normalized_value
        logger.info("loaded %s values from Nacos config %s/%s", len(applied), group, data_id)
        proxy_val = os.getenv("LLM_PROXY_ENABLED", "(not set)")
        print(f"[nacos_config] loaded {len(applied)} values from Nacos config {group}/{data_id}, LLM_PROXY_ENABLED={proxy_val}", flush=True)
        return applied
    except Exception as exc:
        print(f"[nacos_config] ERROR parsing config: {exc}", flush=True)
        logger.error("failed to parse Nacos config: %s", exc)
        return {}


def get_config_with_fallback(client: NacosClient, data_id: str, group: str) -> str:
    candidates = [data_id]
    if data_id.endswith((".yml", ".yaml")):
        candidates.append(data_id.rsplit(".", 1)[0])
        alt_ext = ".yaml" if data_id.endswith(".yml") else ".yml"
        candidates.append(data_id.rsplit(".", 1)[0] + alt_ext)
    else:
        candidates.append(f"{data_id}.yml")
        candidates.append(f"{data_id}.yaml")
    last_error: Exception | None = None
    for candidate in dict.fromkeys(candidates):
        try:
            return client.get_config(candidate, group)
        except Exception as exc:
            last_error = exc
            logger.warning("failed to load Nacos config %s/%s: %s", group, candidate, exc)
    raise RuntimeError(f"failed to load Nacos config from candidates: {candidates}") from last_error


def parse_config_values(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    loaded = yaml.safe_load(text)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise RuntimeError("Nacos config must be a YAML/JSON object")
    if isinstance(loaded.get("env"), dict):
        return dict(loaded["env"])
    if isinstance(loaded.get("env_params"), list):
        values: dict[str, Any] = {}
        for item in loaded["env_params"]:
            if not isinstance(item, dict):
                continue
            key = item.get("var") or item.get("name")
            if key:
                values[str(key)] = item.get("val", item.get("value", ""))
        return values
    flattened: dict[str, Any] = {}
    flatten("", loaded, flattened)
    return flattened


def flatten(prefix: str, value: Any, output: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}_{key}" if prefix else str(key)
            flatten(next_prefix, child, output)
        return
    output[prefix] = value


def normalize_env_key(key: str) -> str:
    normalized = []
    for char in str(key).strip():
        if char.isalnum():
            normalized.append(char.upper())
        else:
            normalized.append("_")
    value = "".join(normalized).strip("_")
    while "__" in value:
        value = value.replace("__", "_")
    return value
