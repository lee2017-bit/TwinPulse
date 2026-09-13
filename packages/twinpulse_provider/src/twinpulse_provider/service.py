"""Timeout, cancellation, stale-response rejection, and core validation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import Protocol

from twinpulse_core import SceneToolPlan, SceneToolRegistry, SpecBundle, scene_tool_plan_from_json

from .contracts import CancellationToken, GenerationRequest, ProviderConfig, ProviderResponse
from .errors import GenerationCancelledError, InvalidProviderResponseError, ProviderTimeoutError


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


class GenerationService:
    def __init__(self, provider: Provider, config: ProviderConfig) -> None:
        self._provider = provider
        self._config = config
        self._active_id: str | None = None
        self._active_token: CancellationToken | None = None

    def cancel_active(self) -> None:
        if self._active_token is not None:
            self._active_token.cancel()
        self._active_id = None

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.cancel_active()
        token = CancellationToken()
        self._active_id = request.request_id
        self._active_token = token
        try:
            try:
                response = await asyncio.wait_for(
                    self._provider.generate(request, token, self._config), timeout=self._config.timeout_s
                )
            except TimeoutError as error:
                token.cancel()
                raise ProviderTimeoutError(f"provider exceeded {self._config.timeout_s:g}s timeout") from error
            if token.is_cancelled or self._active_id != request.request_id or response.request_id != request.request_id:
                raise GenerationCancelledError("late or cancelled response was ignored")
            try:
                plan = scene_tool_plan_from_json(json.dumps(response.payload))
                bundle = SceneToolRegistry().execute(plan)
                return GenerationResult(
                    request_id=request.request_id,
                    provider_name=response.provider_name,
                    model_id=response.model_id,
                    image_count=len(request.images),
                    plan=plan,
                    bundle=bundle,
                )
            except (KeyError, TypeError, ValueError) as error:
                detail = " ".join(str(error).split()) or type(error).__name__
                if len(detail) > 320:
                    detail = detail[:317] + "..."
                raise InvalidProviderResponseError(f"Scene plan rejected: {detail}") from error
        finally:
            if self._active_id == request.request_id:
                self._active_id = None
                self._active_token = None
