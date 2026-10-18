# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Build the selected live provider without issuing a network request."""

from __future__ import annotations

from typing import Callable
from pathlib import Path

from twinpulse_provider import (
    GenerationService,
    NebiusChatCompletionsPipelineProvider,
    OpenAIResponsesProvider,
    ProviderCapabilities,
    ProviderConfig,
    ProviderConfigurationError,
    UrllibChatCompletionsTransport,
)

from .settings import DEFAULT_ADAPTER_KIND, NEBIUS_ADAPTER_KIND, NEBIUS_SITE_PROVIDER_PROFILE, ProviderSettings


def build_split_generation_service(observer_settings, observer_transport, planner_settings, planner_transport,
                                   *, timeout_s=90., compact_photo_layout=False,
                                   planner_template_no_thinking=False, output_token_cap=None,
                                   openai_planner=False):
    """Explicit mixed-provider composition; callers own stage-specific budgets."""
    from twinpulse_provider.stage_transport import StageRoutingTransport, OPENAI_MINI_SNAPSHOT
    observer = observer_settings.validated()
    planner = planner_settings.validated()
    if (observer.provider_profile != 'openai' or observer.model_id != 'gpt-5.4-mini'
            or observer.base_url != 'https://api.openai.com/v1/'
            or (not openai_planner and planner.adapter_kind != NEBIUS_ADAPTER_KIND)
            or (openai_planner and (planner.provider_profile != 'openai'
                or planner.model_id != 'gpt-5.4-mini' or planner.base_url != observer.base_url
                or planner.reasoning_effort != observer.reasoning_effort or planner_template_no_thinking))):
        raise ProviderConfigurationError('Select reviewed OpenAI observer and Nebius NVIDIA planner separately')
    capability = ProviderCapabilities(True, True, 1, observer.accepted_mime_types)
    observer_config = ProviderConfig(observer.base_url, 'chat/completions', OPENAI_MINI_SNAPSHOT,
        'UNUSED_SECURE_STORE', capability, timeout_s=timeout_s, max_attempts=1)
    planner_model = OPENAI_MINI_SNAPSHOT if openai_planner else planner.model_id
    planner_config = ProviderConfig(planner.base_url, 'chat/completions' if openai_planner else planner.endpoint_path, planner_model,
        'UNUSED_SECURE_STORE', capability, timeout_s=timeout_s, max_attempts=1)
    transport = StageRoutingTransport(observer_transport, observer_config, planner_transport, planner_config,
        reasoning_effort=observer.reasoning_effort, openai_planner=openai_planner)
    provider = NebiusChatCompletionsPipelineProvider(transport, observer_model_id=OPENAI_MINI_SNAPSHOT,
        planner_model_id=planner_model, site_plan_version='2.2', max_repairs=1,
        compact_photo_layout=compact_photo_layout, planner_template_no_thinking=planner_template_no_thinking,
        output_token_cap=output_token_cap)
    return GenerationService(provider, planner_config, plan_version='2.2')


def generation_request_schema(adapter_kind: str, *, compact_photo_layout: bool = False) -> str:
    """Current wire metadata only; never rewrite saved input revisions."""
    if adapter_kind != NEBIUS_ADAPTER_KIND:
        return '1.0'
    from twinpulse_provider.scene_contract import GROUNDING_REVISION, PROPOSAL_REVISION
    return GROUNDING_REVISION if compact_photo_layout else PROPOSAL_REVISION


def build_live_generation_service(
    settings: ProviderSettings,
    api_key_getter: Callable[[], str | None],
    *,
    timeout_s: float = 90.0,
    plan_version: str | None = None,
    evidence_root: Path | None = None,
    campaign=None,
    compact_photo_layout: bool = False,
    planner_template_no_thinking: bool = False,
    output_token_cap: int | None = None,
) -> GenerationService:
    """Compose an approved adapter. Construction itself performs zero provider calls."""
    value = settings.validated()
    if campaign is not None and value.adapter_kind != NEBIUS_ADAPTER_KIND:
        raise ProviderConfigurationError('An approved Nebius campaign cannot authorize another provider')
    if output_token_cap is not None and (campaign is None or value.adapter_kind != NEBIUS_ADAPTER_KIND):
        raise ProviderConfigurationError('Host output override requires an approved Nebius campaign')
    selected_version = plan_version or ("2.2" if value.provider_profile == NEBIUS_SITE_PROVIDER_PROFILE else "1.0")
    if plan_version is not None and value.adapter_kind != NEBIUS_ADAPTER_KIND:
        raise ProviderConfigurationError("Explicit site composition requires the Nebius site adapter")
    if compact_photo_layout and (value.adapter_kind != NEBIUS_ADAPTER_KIND or selected_version != '2.2'):
        raise ProviderConfigurationError('Experimental compact photo composition requires Nebius Site2.2')
    if planner_template_no_thinking and (value.adapter_kind != NEBIUS_ADAPTER_KIND or selected_version != '2.2'):
        raise ProviderConfigurationError('Experimental template policy requires Nebius Site2.2')
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
        from twinpulse_provider.reliability import InferenceEvidence
        from .settings import default_settings_path
        provider = OpenAIResponsesProvider(api_key_getter, reasoning_effort=value.reasoning_effort,
            evidence=InferenceEvidence(evidence_root or default_settings_path().parent/'provider-evidence'))
    elif value.adapter_kind == NEBIUS_ADAPTER_KIND:
        from twinpulse_provider.reliability import AuditedChatTransport, InferenceEvidence
        from .settings import default_settings_path
        transport = AuditedChatTransport(api_key_getter,
            InferenceEvidence(evidence_root or default_settings_path().parent/'provider-evidence'), campaign)
        provider = NebiusChatCompletionsPipelineProvider(
            transport,
            observer_model_id=value.observer_model_id,
            planner_model_id=value.model_id,
            site_plan_version=selected_version,
            max_repairs=1 if selected_version == '2.2' else 0,
            compact_photo_layout=compact_photo_layout,
            planner_template_no_thinking=planner_template_no_thinking,
            output_token_cap=output_token_cap,
        )
    else:  # validated() currently prevents this, retained as a composition safety boundary.
        raise ProviderConfigurationError("provider adapter is unsupported")
    return GenerationService(
        provider, config,
        plan_version=selected_version,
    )
