"""Spring-like profile-based configuration loader.

Reads application.yml, selects the profile block matching APP_ENV,
and sets environment variables so downstream code (NacosClient, etc.)
sees the correct config before any connection is made.

Usage:
    from danbao_poc.profile_config import load_profile_config
    load_profile_config()  # call early, before NacosClient()
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).resolve().parent / "application.yml"


def _resolve_active_profile() -> str:
    """Determine active profile from APP_ENV (default: dev)."""
    return os.getenv("APP_ENV", "dev").strip() or "dev"


def _parse_profile_documents(path: Path) -> dict[str, dict[str, Any]]:
    """Parse multi-document YAML into {profile_name: config_dict}."""
    with open(path, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    profiles: dict[str, dict[str, Any]] = {}
    global_section: dict[str, Any] = {}

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        # First document without a 'profiles' key is the global section
        profile_key = doc.get("profiles")
        if profile_key is None:
            global_section = doc
            continue
        # profiles can be a string or a list
        if isinstance(profile_key, str):
            names = [profile_key.strip()]
        elif isinstance(profile_key, list):
            names = [str(n).strip() for n in profile_key]
        else:
            continue
        for name in names:
            if name:
                profiles[name] = doc

    # Attach global section info for reference
    if global_section:
        profiles["__global__"] = global_section

    return profiles


def _flatten_config(prefix: str, value: Any, output: dict[str, Any]) -> None:
    """Recursively flatten nested dict to UPPER_SNAKE_CASE env keys."""
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}_{key}" if prefix else str(key)
            _flatten_config(next_prefix, child, output)
        return
    if value is not None:
        output[prefix] = value


def _config_to_env_keys(config: dict[str, Any]) -> dict[str, str]:
    """Convert nested config dict to flat {ENV_KEY: str_value} mapping.

    Keys are normalized to UPPER_SNAKE_CASE matching the existing
    NACOS_* / APP_* convention.
    """
    flat: dict[str, Any] = {}
    _flatten_config("", config, flat)

    result: dict[str, str] = {}
    for raw_key, value in flat.items():
        env_key = raw_key.upper()
        # collapse consecutive underscores
        while "__" in env_key:
            env_key = env_key.replace("__", "_")
        env_key = env_key.strip("_")
        if env_key:
            result[env_key] = str(value)
    return result


def load_profile_config(path: Path | None = None) -> dict[str, str]:
    """Load application.yml, select profile by APP_ENV, set env vars.

    Returns the dict of {env_key: value} that were applied.
    Existing env vars are NOT overridden (env takes precedence).
    """
    config_path = path or _CONFIG_FILE
    if not config_path.exists():
        logger.debug("application.yml not found at %s, skip profile config", config_path)
        return {}

    profile_name = _resolve_active_profile()
    profiles = _parse_profile_documents(config_path)

    if profile_name not in profiles:
        available = [k for k in profiles if k != "__global__"]
        logger.warning(
            "profile %r not found in application.yml, available: %s. Using first available.",
            profile_name,
            available,
        )
        if available:
            profile_name = available[0]
        else:
            return {}

    profile_config = profiles[profile_name]
    # Remove the 'profiles' key itself from the config to be flattened
    config_to_apply = {k: v for k, v in profile_config.items() if k != "profiles"}

    env_mapping = _config_to_env_keys(config_to_apply)

    applied: dict[str, str] = {}
    for env_key, value in env_mapping.items():
        # Respect existing env vars (docker -e, .env, etc. take precedence)
        existing = os.getenv(env_key)
        if existing is not None and existing.strip() != "":
            continue
        os.environ[env_key] = value
        applied[env_key] = value

    if applied:
        logger.info(
            "profile_config [%s]: applied %d env vars: %s",
            profile_name,
            len(applied),
            ", ".join(sorted(applied.keys())),
        )
        print(
            f"[profile_config] profile={profile_name}, applied {len(applied)} env vars",
            flush=True,
        )
    else:
        logger.info("profile_config [%s]: no new env vars to apply", profile_name)
        print(f"[profile_config] profile={profile_name}, all env vars already set", flush=True)

    return applied
