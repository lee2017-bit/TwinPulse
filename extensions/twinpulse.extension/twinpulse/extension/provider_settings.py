"""Persistent non-secret provider settings."""

from __future__ import annotations

from dataclasses import dataclass

import carb.settings


_ROOT = "/persistent/exts/twinpulse.extension/provider"
_BASE_URL = f"{_ROOT}/baseUrl"
_MODEL_ID = f"{_ROOT}/modelId"
_REASONING = f"{_ROOT}/reasoningEffort"

DEFAULT_BASE_URL = "https://api.openai.com/v1/"
DEFAULT_MODEL_ID = "gpt-5.6-luna"
DEFAULT_REASONING = "low"
ALLOWED_REASONING = frozenset({"low", "medium", "high"})


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    base_url: str
    model_id: str
    reasoning_effort: str


def load_provider_settings() -> ProviderSettings:
    settings = carb.settings.get_settings()
    base_url = settings.get_as_string(_BASE_URL).strip() or DEFAULT_BASE_URL
    model_id = settings.get_as_string(_MODEL_ID).strip() or DEFAULT_MODEL_ID
    reasoning = settings.get_as_string(_REASONING).strip().lower() or DEFAULT_REASONING
    if reasoning not in ALLOWED_REASONING:
        reasoning = DEFAULT_REASONING
    return ProviderSettings(base_url, model_id, reasoning)


def save_provider_settings(value: ProviderSettings) -> None:
    base_url = value.base_url.strip()
    model_id = value.model_id.strip()
    reasoning = value.reasoning_effort.strip().lower()
    if not base_url or not model_id:
        raise ValueError("Base URL and Model ID are required")
    if reasoning not in ALLOWED_REASONING:
        raise ValueError("Reasoning must be low, medium, or high")
    settings = carb.settings.get_settings()
    settings.set_string(_BASE_URL, base_url)
    settings.set_string(_MODEL_ID, model_id)
    settings.set_string(_REASONING, reasoning)
