# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Credential-free application settings and explicit legacy migration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from threading import Lock, RLock
from typing import Callable, Mapping
from urllib.parse import urlsplit
from uuid import uuid4


SETTINGS_SCHEMA_VERSION = "3.0"
LEGACY_SETTINGS_SCHEMA_VERSION = "1.0"
PREVIOUS_SETTINGS_SCHEMA_VERSION = "2.0"
DEFAULT_BASE_URL = "https://api.openai.com/v1/"
DEFAULT_MODEL_ID = "gpt-5.6-luna"
DEFAULT_REASONING = "low"
DEFAULT_ADAPTER_KIND = "openai_responses"
DEFAULT_PROVIDER_PROFILE = "openai"
DEFAULT_ENDPOINT_PATH = "responses"
DEFAULT_CREDENTIAL_REF = "TwinPulse/OpenAIResponsesAPI"
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
NEBIUS_PLANNER_MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
NEBIUS_OBSERVER_MODEL_ID = "google/gemma-3-27b-it"
NEBIUS_FALLBACK_OBSERVER_MODEL_ID = "openbmb/MiniCPM-V-4_5"
NEBIUS_ADAPTER_KIND = "nebius_chat_completions_pipeline"
NEBIUS_PROVIDER_PROFILE = "nebius_token_factory"
NEBIUS_SITE_PROVIDER_PROFILE = "nebius_site_v2"
NEBIUS_ENDPOINT_PATH = "chat/completions"
DEFAULT_ACCEPTED_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")
ALLOWED_REASONING = frozenset({"low", "medium", "high"})
ALLOWED_ADAPTERS = frozenset({DEFAULT_ADAPTER_KIND, NEBIUS_ADAPTER_KIND})
_LOCKS_GUARD = Lock()
_STORE_LOCKS: dict[str, RLock] = {}


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    base_url: str = DEFAULT_BASE_URL
    model_id: str = DEFAULT_MODEL_ID
    reasoning_effort: str = DEFAULT_REASONING
    adapter_kind: str = DEFAULT_ADAPTER_KIND
    provider_profile: str = DEFAULT_PROVIDER_PROFILE
    endpoint_path: str = DEFAULT_ENDPOINT_PATH
    credential_ref: str = DEFAULT_CREDENTIAL_REF
    supports_images: bool = True
    supports_structured_output: bool = True
    max_images: int = 1
    accepted_mime_types: tuple[str, ...] = DEFAULT_ACCEPTED_MIME_TYPES
    observer_model_id: str = ""
    fallback_observer_model_id: str = ""

    def validated(self) -> "ProviderSettings":
        base_url = self.base_url.strip()
        model_id = self.model_id.strip()
        reasoning = self.reasoning_effort.strip().lower()
        adapter = self.adapter_kind.strip().lower()
        profile = self.provider_profile.strip().lower()
        endpoint = self.endpoint_path.strip().strip("/")
        credential_ref = self.credential_ref.strip()
        observer_model_id = self.observer_model_id.strip()
        fallback_observer_model_id = self.fallback_observer_model_id.strip()
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Base URL must be an absolute HTTPS URL without credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL must not contain query or fragment data")
        if not model_id or len(model_id) > 256:
            raise ValueError("Model ID is required")
        if reasoning not in ALLOWED_REASONING:
            raise ValueError("Reasoning must be low, medium, or high")
        if adapter not in ALLOWED_ADAPTERS:
            raise ValueError("Provider adapter is unsupported")
        if not profile or len(profile) > 64 or not all(character.isalnum() or character in "_-" for character in profile):
            raise ValueError("Provider profile is invalid")
        if not endpoint or len(endpoint) > 128 or any(part in {"", ".", ".."} for part in endpoint.split("/")):
            raise ValueError("Provider endpoint path is invalid")
        if (
            "?" in endpoint or "#" in endpoint or "\\" in endpoint
            or any(not all(character.isalnum() or character in "_-" for character in part) for part in endpoint.split("/"))
        ):
            raise ValueError("Provider endpoint path is invalid")
        if adapter == DEFAULT_ADAPTER_KIND:
            if profile != DEFAULT_PROVIDER_PROFILE or endpoint != DEFAULT_ENDPOINT_PATH:
                raise ValueError("OpenAI provider preset is invalid")
            if observer_model_id or fallback_observer_model_id:
                raise ValueError("OpenAI provider must not define observer models")
        else:
            if (
                profile not in {NEBIUS_PROVIDER_PROFILE, NEBIUS_SITE_PROVIDER_PROFILE}
                or base_url != NEBIUS_BASE_URL
                or endpoint != NEBIUS_ENDPOINT_PATH
                or model_id != NEBIUS_PLANNER_MODEL_ID
                or observer_model_id != NEBIUS_OBSERVER_MODEL_ID
                or fallback_observer_model_id != NEBIUS_FALLBACK_OBSERVER_MODEL_ID
            ):
                raise ValueError("Nebius provider preset must use the reviewed S3a model pipeline")
        if not credential_ref or len(credential_ref) > 256 or any(ord(character) < 32 for character in credential_ref):
            raise ValueError("Credential reference is invalid")
        if not isinstance(self.supports_images, bool) or not isinstance(self.supports_structured_output, bool):
            raise ValueError("Provider capabilities are invalid")
        if not isinstance(self.max_images, int) or isinstance(self.max_images, bool) or not 0 <= self.max_images <= 8:
            raise ValueError("Provider max_images is invalid")
        mime_types = tuple(dict.fromkeys(item.strip().lower() for item in self.accepted_mime_types))
        if any(not item.startswith("image/") or len(item) > 64 for item in mime_types):
            raise ValueError("Provider accepted MIME types are invalid")
        if self.supports_images and (self.max_images < 1 or not mime_types):
            raise ValueError("Image capability requires a positive limit and MIME types")
        if not self.supports_images and (self.max_images != 0 or mime_types):
            raise ValueError("Disabled image capability must not declare image limits")
        return ProviderSettings(
            base_url, model_id, reasoning, adapter, profile, endpoint, credential_ref,
            self.supports_images, self.supports_structured_output, self.max_images, mime_types,
            observer_model_id, fallback_observer_model_id,
        )

    @property
    def binding_identity(self) -> tuple[str, str, str, str, str]:
        value = self.validated()
        origin = urlsplit(value.base_url)
        return (
            value.adapter_kind, value.provider_profile,
            f"{origin.scheme.lower()}://{origin.netloc.lower()}", value.endpoint_path,
            value.credential_ref,
        )

    def to_dict(self) -> dict[str, object]:
        value = self.validated()
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION, "base_url": value.base_url,
            "model_id": value.model_id, "reasoning_effort": value.reasoning_effort,
            "adapter_kind": value.adapter_kind, "provider_profile": value.provider_profile,
            "endpoint_path": value.endpoint_path, "credential_ref": value.credential_ref,
            "observer_model_id": value.observer_model_id,
            "fallback_observer_model_id": value.fallback_observer_model_id,
            "capabilities": {
                "supports_images": value.supports_images,
                "supports_structured_output": value.supports_structured_output,
                "max_images": value.max_images,
                "accepted_mime_types": list(value.accepted_mime_types),
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ProviderSettings":
        if value.get("schema_version") == LEGACY_SETTINGS_SCHEMA_VERSION:
            if set(value) != {"schema_version", "base_url", "model_id", "reasoning_effort"}:
                raise ValueError("legacy provider settings shape is unsupported")
            if not all(isinstance(value[name], str) for name in ("base_url", "model_id", "reasoning_effort")):
                raise ValueError("provider settings values must be strings")
            parsed = urlsplit(str(value["base_url"]))
            if parsed.hostname != "api.openai.com":
                raise ValueError("legacy custom provider settings require explicit profile migration")
            return cls(
                str(value["base_url"]), str(value["model_id"]), str(value["reasoning_effort"]),
            ).validated()
        expected_v2 = {
            "schema_version", "base_url", "model_id", "reasoning_effort", "adapter_kind",
            "provider_profile", "endpoint_path", "credential_ref", "capabilities",
        }
        if value.get("schema_version") == PREVIOUS_SETTINGS_SCHEMA_VERSION:
            if set(value) != expected_v2:
                raise ValueError("provider settings shape is unsupported")
            migrated = dict(value)
            migrated["schema_version"] = SETTINGS_SCHEMA_VERSION
            migrated["observer_model_id"] = ""
            migrated["fallback_observer_model_id"] = ""
            return cls.from_dict(migrated)
        expected = expected_v2 | {"observer_model_id", "fallback_observer_model_id"}
        if set(value) != expected:
            raise ValueError("provider settings shape is unsupported")
        if value.get("schema_version") != SETTINGS_SCHEMA_VERSION:
            raise ValueError("provider settings version is unsupported")
        string_names = (
            "base_url", "model_id", "reasoning_effort", "adapter_kind", "provider_profile",
            "endpoint_path", "credential_ref", "observer_model_id", "fallback_observer_model_id",
        )
        if not all(isinstance(value[name], str) for name in string_names):
            raise ValueError("provider settings values must be strings")
        capabilities = value.get("capabilities")
        capability_keys = {
            "supports_images", "supports_structured_output", "max_images", "accepted_mime_types",
        }
        if not isinstance(capabilities, Mapping) or set(capabilities) != capability_keys:
            raise ValueError("provider capabilities shape is unsupported")
        accepted = capabilities.get("accepted_mime_types")
        if not isinstance(accepted, list) or not all(isinstance(item, str) for item in accepted):
            raise ValueError("provider accepted MIME types must be strings")
        return cls(
            str(value["base_url"]), str(value["model_id"]), str(value["reasoning_effort"]),
            str(value["adapter_kind"]), str(value["provider_profile"]),
            str(value["endpoint_path"]), str(value["credential_ref"]),
            capabilities.get("supports_images"), capabilities.get("supports_structured_output"),
            capabilities.get("max_images"), tuple(accepted),
            str(value["observer_model_id"]), str(value["fallback_observer_model_id"]),
        ).validated()  # type: ignore[arg-type]


def provider_settings_preset(profile: str, *, credential_ref: str = DEFAULT_CREDENTIAL_REF) -> ProviderSettings:
    normalized = profile.strip().lower()
    if normalized == DEFAULT_PROVIDER_PROFILE:
        return ProviderSettings(credential_ref=credential_ref).validated()
    if normalized in {NEBIUS_PROVIDER_PROFILE, NEBIUS_SITE_PROVIDER_PROFILE}:
        return ProviderSettings(
            base_url=NEBIUS_BASE_URL,
            model_id=NEBIUS_PLANNER_MODEL_ID,
            reasoning_effort="low",
            adapter_kind=NEBIUS_ADAPTER_KIND,
            provider_profile=normalized,
            endpoint_path=NEBIUS_ENDPOINT_PATH,
            credential_ref=credential_ref,
            observer_model_id=NEBIUS_OBSERVER_MODEL_ID,
            fallback_observer_model_id=NEBIUS_FALLBACK_OBSERVER_MODEL_ID,
        ).validated()
    raise ValueError("Provider profile is unsupported")


def default_settings_path() -> Path:
    override = os.environ.get("TWINPULSE_STATE_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TwinPulse" / "runtime"
    return root / "provider_settings.json"


class JsonProviderSettingsStore:
    def __init__(self, path: Path | None = None, *, defaults: ProviderSettings | None = None) -> None:
        self.path = path or default_settings_path()
        self._defaults = (defaults or ProviderSettings()).validated()
        key = str(self.path.resolve())
        with _LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(key, RLock())

    def exists(self) -> bool:
        with self._lock:
            return self.path.is_file()

    def load(self) -> ProviderSettings:
        with self._lock:
            if not self.path.is_file():
                return self._defaults
            if self.path.stat().st_size > 64 * 1024:
                raise ValueError("provider settings file exceeds limit")
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise ValueError("provider settings must be a JSON object")
            return ProviderSettings.from_dict(value)

    def save(self, value: ProviderSettings) -> None:
        data = value.validated().to_dict()
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_name: str | None = None
            try:
                temporary_path = self.path.parent / f".{self.path.name}.{uuid4().hex}.tmp"
                temporary_name = str(temporary_path)
                with temporary_path.open("xb") as temporary:
                    temporary.write(payload)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, self.path)
                temporary_name = None
            finally:
                if temporary_name is not None:
                    try:
                        Path(temporary_name).unlink()
                    except FileNotFoundError:
                        pass


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
