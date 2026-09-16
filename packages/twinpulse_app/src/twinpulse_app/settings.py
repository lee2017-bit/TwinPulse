"""Credential-free application settings and explicit legacy migration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit


SETTINGS_SCHEMA_VERSION = "1.0"
DEFAULT_BASE_URL = "https://api.openai.com/v1/"
DEFAULT_MODEL_ID = "gpt-5.6-luna"
DEFAULT_REASONING = "low"
ALLOWED_REASONING = frozenset({"low", "medium", "high"})


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    base_url: str = DEFAULT_BASE_URL
    model_id: str = DEFAULT_MODEL_ID
    reasoning_effort: str = DEFAULT_REASONING

    def validated(self) -> "ProviderSettings":
        base_url = self.base_url.strip()
        model_id = self.model_id.strip()
        reasoning = self.reasoning_effort.strip().lower()
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Base URL must be an absolute HTTPS URL without credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL must not contain query or fragment data")
        if not model_id or len(model_id) > 256:
            raise ValueError("Model ID is required")
        if reasoning not in ALLOWED_REASONING:
            raise ValueError("Reasoning must be low, medium, or high")
        return ProviderSettings(base_url, model_id, reasoning)

    def to_dict(self) -> dict[str, str]:
        value = self.validated()
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION, "base_url": value.base_url,
            "model_id": value.model_id, "reasoning_effort": value.reasoning_effort,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ProviderSettings":
        if set(value) != {"schema_version", "base_url", "model_id", "reasoning_effort"}:
            raise ValueError("provider settings shape is unsupported")
        if value.get("schema_version") != SETTINGS_SCHEMA_VERSION:
            raise ValueError("provider settings version is unsupported")
        if not all(isinstance(value[name], str) for name in ("base_url", "model_id", "reasoning_effort")):
            raise ValueError("provider settings values must be strings")
        return cls(value["base_url"], value["model_id"], value["reasoning_effort"]).validated()  # type: ignore[arg-type]


def default_settings_path() -> Path:
    override = os.environ.get("TWINPULSE_STATE_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TwinPulse" / "runtime"
    return root / "provider_settings.json"


class JsonProviderSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> ProviderSettings:
        if not self.path.is_file():
            return ProviderSettings()
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("provider settings must be a JSON object")
        return ProviderSettings.from_dict(value)

    def save(self, value: ProviderSettings) -> None:
        data = value.validated().to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)


def migrate_legacy_settings_once(
    store: JsonProviderSettingsStore,
    legacy_loader: Callable[[], ProviderSettings],
) -> tuple[ProviderSettings, bool]:
    """Import carb values once; subsequent reads never synchronize backwards."""
    if store.exists():
        return store.load(), False
    value = legacy_loader().validated()
    store.save(value)
    return value, True
