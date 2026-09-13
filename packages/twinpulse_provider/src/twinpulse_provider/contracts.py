"""Credential-free request, response, and configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from .errors import ProviderConfigurationError


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    supports_images: bool
    supports_structured_output: bool
    max_images: int = 0
    accepted_mime_types: tuple[str, ...] = ("image/jpeg", "image/png")


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    base_url: str
    endpoint_path: str
    model_id: str
    api_key_env: str
    capabilities: ProviderCapabilities
    timeout_s: float = 30.0
    max_attempts: int = 1

    def endpoint_url(self) -> str:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderConfigurationError("provider base_url must be an absolute HTTPS URL")
        if not self.model_id.strip():
            raise ProviderConfigurationError("provider model_id is required")
        if not self.api_key_env.strip():
            raise ProviderConfigurationError("api_key_env name is required")
        if self.max_attempts != 1:
            raise ProviderConfigurationError("M2-A permits one attempt and no automatic retry")
        return urljoin(self.base_url.rstrip("/") + "/", self.endpoint_path.lstrip("/"))


@dataclass(frozen=True, slots=True)
class ImageInput:
    name: str
    mime_type: str
    content: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    request_id: str
    prompt: str
    images: tuple[ImageInput, ...] = ()
    schema_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    request_id: str
    payload: Mapping[str, Any]
    provider_name: str
    model_id: str


class CancellationToken:
    """Small thread-safe token usable by async and blocking adapters."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()
