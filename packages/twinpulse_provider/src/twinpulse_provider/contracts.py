# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Credential-free request, response, and configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from .errors import ProviderConfigurationError
from .measurement_constraints import MeasurementConstraint


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
    image_detail: str = "auto"
    measurement_constraints: tuple[MeasurementConstraint, ...] = ()
    # Internal context only: excluded from provider bodies and canonical hashes.
    diagnostics: Any = field(default=None, repr=False, compare=False)
    # Trusted internal scope adapter only. Never serialized into a model body.
    inference_scope: Any = field(default=None, repr=False, compare=False)
    # Explicit trusted continuation only; GET/reopen never supplies this field.
    continuation_checkpoint: str | None = None
    render_review_port: Any = field(default=None, repr=False, compare=False)
    model_library_port: Any = field(default=None, repr=False, compare=False)
    # Host-only frozen feedback evidence. The transmitted prompt contains a
    # compact summary bound to its full context SHA, never mesh geometry.
    feedback_context: Any = field(default=None, repr=False, compare=False)
    # Trusted App-only candidate compiler/fence; never part of a model body.
    feedback_candidate_validator: Any = field(default=None, repr=False, compare=False)
    feedback_deadline: float | None = field(default=None, repr=False, compare=False)
    # Host-selected acceptance purpose. Never sent as executable/model content.
    draft_goal: str = 'photo_reconstruction'

    def __post_init__(self) -> None:
        if self.image_detail not in {"auto", "low", "high"}:
            raise ValueError("image_detail must be auto, low, or high")
        if self.draft_goal not in {'photo_reconstruction','editable_obstacle_prior'}:
            raise ValueError('unsupported draft goal')


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    request_id: str
    payload: Mapping[str, Any]
    provider_name: str
    model_id: str
    provenance: Mapping[str, Any] = field(default_factory=dict)


class CancellationToken:
    """Small thread-safe token usable by async and blocking adapters."""

    def __init__(self) -> None:
        self._event = Event()
        self.diagnostics = None

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()
