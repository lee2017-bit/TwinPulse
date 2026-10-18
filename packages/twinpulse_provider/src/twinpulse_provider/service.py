# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Timeout, cancellation, stale-response rejection, and core validation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Protocol

from twinpulse_core import (
    SceneToolPlan,
    SiteToolPlan,
    SceneToolRegistry,
    SpecBundle,
    LOCAL_ROUTE_RESOLVER_REVISION,
    resolve_current_controller_route,
    scene_tool_plan_from_json,
    site_tool_plan_from_json,
)

from .contracts import CancellationToken, GenerationRequest, ProviderConfig, ProviderResponse
from .errors import GenerationCancelledError, InvalidProviderResponseError, ProviderTimeoutError
from .measurement_constraints import validate_measurement_constraints


class Provider(Protocol):
    async def generate(
        self, request: GenerationRequest, token: CancellationToken, config: ProviderConfig
    ) -> ProviderResponse: ...


@dataclass(frozen=True, slots=True)
class GenerationResult:
    request_id: str
    provider_name: str
    model_id: str
    image_count: int
    plan: SceneToolPlan
    bundle: SpecBundle
    measurement_constraint_count: int = 0
    measurement_checked_value_count: int = 0
    provider_provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SiteGenerationResult:
    """Typed v2 result for the single App owner."""

    request_id: str
    provider_name: str
    model_id: str
    image_count: int
    plan: SiteToolPlan
    provider_provenance: Mapping[str, Any] = field(default_factory=dict)


class GenerationService:
    def __init__(self, provider: Provider, config: ProviderConfig, *, plan_version: str = "1.0") -> None:
        if plan_version not in {"1.0", "2.0", "2.1", "2.2"}:
            raise ValueError("generation plan version is unsupported")
        self._provider = provider
        self._config = config
        self._plan_version = plan_version
        self._active_id: str | None = None
        self._active_token: CancellationToken | None = None
        self._last_diagnostic: dict[str, Any] = {}

    def cancel_active(self) -> None:
        if self._active_token is not None:
            self._active_token.cancel()
        self._active_id = None

    def diagnostic_snapshot(self) -> dict[str, Any]:
        if self._active_id is None:
            return dict(self._last_diagnostic)
        return getattr(self._provider, 'diagnostic_for', lambda _: {})(self._active_id)

    async def generate(self, request: GenerationRequest) -> GenerationResult | SiteGenerationResult:
        self.cancel_active()
        if self._plan_version in {"2.0", "2.1", "2.2"} and request.measurement_constraints:
            # This contract is not wired for v2 yet; reject before any paid provider call.
            raise ValueError("site plan 2.0 does not yet support trusted measurement constraints")
        token = CancellationToken()
        token.diagnostics = request.diagnostics
        self._active_id = request.request_id
        self._active_token = token
        self._last_diagnostic = {}
        terminal_diagnostic = None
        try:
            try:
                response = await asyncio.wait_for(
                    self._provider.generate(request, token, self._config),
                    timeout=getattr(self._provider, 'total_timeout_s', self._config.timeout_s)
                )
            except TimeoutError as error:
                token.cancel()
                diagnostic = getattr(self._provider, "diagnostic_for", lambda _: {})(request.request_id)
                stage = diagnostic.get("stage")
                detail = f" during {stage} stage (model={diagnostic.get('model_id')})" if stage else ""
                timeout = getattr(self._provider, 'total_timeout_s', self._config.timeout_s)
                failure = ProviderTimeoutError(f"provider exceeded {timeout:g}s timeout{detail}")
                failure.diagnostics = {**diagnostic, "status": "outcome_unknown", "timeout_s": timeout,
                                       "remote_outcome": "unknown", "automatic_retry": False}
                terminal_diagnostic = failure.diagnostics
                raise failure from error
            if token.is_cancelled or self._active_id != request.request_id or response.request_id != request.request_id:
                raise GenerationCancelledError("late or cancelled response was ignored")
            try:
                if self._plan_version in {"2.0", "2.1", "2.2"}:
                    site_plan = site_tool_plan_from_json(json.dumps(response.payload))
                    return SiteGenerationResult(
                        request_id=request.request_id, provider_name=response.provider_name,
                        model_id=response.model_id, image_count=len(request.images), plan=site_plan,
                        provider_provenance=dict(response.provenance),
                    )
                plan = scene_tool_plan_from_json(json.dumps(response.payload))
                plan, route_resolved = resolve_current_controller_route(plan)
                measurement_result = validate_measurement_constraints(plan, request.measurement_constraints)
                bundle = SceneToolRegistry().execute(plan)
                provenance = dict(response.provenance)
                if route_resolved:
                    provenance["local_route_resolution"] = {
                        "applied": True,
                        "revision": LOCAL_ROUTE_RESOLVER_REVISION,
                    }
                return GenerationResult(
                    request_id=request.request_id,
                    provider_name=response.provider_name,
                    model_id=response.model_id,
                    image_count=len(request.images),
                    plan=plan,
                    bundle=bundle,
                    measurement_constraint_count=measurement_result.constraint_count,
                    measurement_checked_value_count=measurement_result.checked_value_count,
                    provider_provenance=provenance,
                )
            except (KeyError, TypeError, ValueError) as error:
                detail = " ".join(str(error).split()) or type(error).__name__
                if len(detail) > 320:
                    detail = detail[:317] + "..."
                raise InvalidProviderResponseError(f"Scene plan rejected: {detail}") from error
        finally:
            if self._active_id == request.request_id:
                self._last_diagnostic = terminal_diagnostic or getattr(self._provider, 'diagnostic_for', lambda _: {})(request.request_id)
                self._active_id = None
                self._active_token = None
