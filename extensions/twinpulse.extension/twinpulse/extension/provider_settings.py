"""Legacy carb-to-application settings compatibility wrapper.

Carb is read only for the first explicit migration.  After that, the shared
credential-free JSON store is authoritative; there is no bidirectional sync.
"""

from __future__ import annotations

import carb.settings

from twinpulse_app.settings import (
    ALLOWED_REASONING,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_ID,
    DEFAULT_REASONING,
    JsonProviderSettingsStore,
    ProviderSettings,
    migrate_legacy_settings_once,
)


_ROOT = "/persistent/exts/twinpulse.extension/provider"
_BASE_URL = f"{_ROOT}/baseUrl"
_MODEL_ID = f"{_ROOT}/modelId"
_REASONING = f"{_ROOT}/reasoningEffort"


def _load_legacy_carb_settings() -> ProviderSettings:
    settings = carb.settings.get_settings()
    base_url = settings.get_as_string(_BASE_URL).strip() or DEFAULT_BASE_URL
    model_id = settings.get_as_string(_MODEL_ID).strip() or DEFAULT_MODEL_ID
    reasoning = settings.get_as_string(_REASONING).strip().lower() or DEFAULT_REASONING
    if reasoning not in ALLOWED_REASONING:
        reasoning = DEFAULT_REASONING
    return ProviderSettings(base_url, model_id, reasoning)


def load_provider_settings() -> ProviderSettings:
    value, _migrated = migrate_legacy_settings_once(JsonProviderSettingsStore(), _load_legacy_carb_settings)
    return value


def save_provider_settings(value: ProviderSettings) -> None:
    JsonProviderSettingsStore().save(value)


__all__ = [
    "ALLOWED_REASONING", "DEFAULT_BASE_URL", "DEFAULT_MODEL_ID", "DEFAULT_REASONING",
    "ProviderSettings", "load_provider_settings", "save_provider_settings",
]
