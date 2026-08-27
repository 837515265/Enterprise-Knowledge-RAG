from __future__ import annotations

import os
from dataclasses import dataclass


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class ServiceAuthSettings:
    header: str
    token: str
    request_id_header: str


def service_auth_settings() -> ServiceAuthSettings:
    return ServiceAuthSettings(
        header=env_str("SERVICE_AUTH_HEADER"),
        token=env_str("SERVICE_AUTH_TOKEN"),
        request_id_header=env_str("REQUEST_ID_HEADER", "X-Request-Id"),
    )

