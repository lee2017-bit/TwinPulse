"""Provider boundary for TwinPulse structured scene generation."""

from .contracts import (
    CancellationToken,
    GenerationRequest,
    ImageInput,
    ProviderCapabilities,
    ProviderConfig,
    ProviderResponse,
)
from .errors import (
    GenerationCancelledError,
    InvalidProviderResponseError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from .providers import MockMode, MockProvider, OpenAIResponsesProvider, StructuredJsonHttpProvider
from .schema import scene_tool_plan_json_schema, spec_bundle_json_schema
from .service import GenerationResult, GenerationService

__all__ = [
    "CancellationToken",
    "GenerationCancelledError",
    "GenerationRequest",
    "GenerationResult",
    "GenerationService",
    "ImageInput",
    "InvalidProviderResponseError",
    "MockMode",
    "MockProvider",
    "OpenAIResponsesProvider",
    "ProviderCapabilities",
    "ProviderAuthenticationError",
    "ProviderCapabilityError",
    "ProviderConfig",
    "ProviderConfigurationError",
    "ProviderRateLimitError",
    "ProviderResponse",
    "ProviderTimeoutError",
    "StructuredJsonHttpProvider",
    "scene_tool_plan_json_schema",
    "spec_bundle_json_schema",
]
