"""Build the selected live provider without issuing a network request."""

from __future__ import annotations

from typing import Callable

from twinpulse_provider import (
    GenerationService,
    NebiusChatCompletionsPipelineProvider,
    OpenAIResponsesProvider,
    ProviderCapabilities,
    ProviderConfig,
    ProviderConfigurationError,
    UrllibChatCompletionsTransport,
)

from .settings import DEFAULT_ADAPTER_KIND, NEBIUS_ADAPTER_KIND, ProviderSettings


def build_live_generation_service(
    settings: ProviderSettings,
    api_key_getter: Callable[[], str | None],
    *,
    timeout_s: float = 90.0,
) -> GenerationService:
    """Compose an approved adapter. Construction itself performs zero provider calls."""
    value = settings.validated()
    capabilities = ProviderCapabilities(
        supports_images=value.supports_images,
        supports_structured_output=value.supports_structured_output,
        max_images=value.max_images,
        accepted_mime_types=value.accepted_mime_types,
    )
    config = ProviderConfig(
        base_url=value.base_url,
        endpoint_path=value.endpoint_path,
        model_id=value.model_id,
        api_key_env="TWINPULSE_PROVIDER_API_KEY",
        capabilities=capabilities,
        timeout_s=timeout_s,
        max_attempts=1,
    )
    if value.adapter_kind == DEFAULT_ADAPTER_KIND:
        provider = OpenAIResponsesProvider(api_key_getter, reasoning_effort=value.reasoning_effort)
    elif value.adapter_kind == NEBIUS_ADAPTER_KIND:
        provider = NebiusChatCompletionsPipelineProvider(
            UrllibChatCompletionsTransport(api_key_getter),
            observer_model_id=value.observer_model_id,
            planner_model_id=value.model_id,
        )
    else:  # validated() currently prevents this, retained as a composition safety boundary.
        raise ProviderConfigurationError("provider adapter is unsupported")
    return GenerationService(provider, config)
