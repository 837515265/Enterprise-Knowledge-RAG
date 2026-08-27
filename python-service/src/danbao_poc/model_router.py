from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    prefix: str
    tier: str
    model_name: str
    base_url: str
    api_key: str
    timeout: int


class ModelRouter:
    def select(self, prefix: str, prompt_chars: int = 0) -> ModelRoute:
        prefix = prefix.upper().rstrip("_")
        threshold = int(os.getenv(f"{prefix}_TIER_THRESHOLD_CHARS", os.getenv("MODEL_TIER_THRESHOLD_CHARS", "28000")))
        tier = "long_context" if prompt_chars > threshold else "primary"
        env_prefix = f"{prefix}_{tier.upper()}"
        model_name = os.getenv(f"{env_prefix}_MODEL_NAME") or os.getenv(f"{prefix}_MODEL_NAME") or os.getenv("DEFAULT_MODEL_NAME", "")
        base_url = os.getenv(f"{env_prefix}_BASE_URL") or os.getenv(f"{prefix}_BASE_URL") or os.getenv("DEFAULT_MODEL_BASE_URL", "")
        api_key = os.getenv(f"{env_prefix}_API_KEY") or os.getenv(f"{prefix}_API_KEY") or os.getenv("DEFAULT_MODEL_API_KEY", "EMPTY")
        timeout = int(os.getenv(f"{env_prefix}_TIMEOUT", os.getenv(f"{prefix}_TIMEOUT", os.getenv("DEFAULT_MODEL_TIMEOUT", "120"))))
        return ModelRoute(prefix=prefix, tier=tier, model_name=model_name, base_url=base_url, api_key=api_key, timeout=timeout)
