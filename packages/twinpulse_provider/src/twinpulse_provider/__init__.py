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
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .nebius_pipeline import (
    ChatCompletion,
    ChatCompletionsTransport,
    NebiusChatCompletionsPipelineProvider,
    ObservationArtifact,
    UrllibChatCompletionsTransport,
    observation_json_schema,
    parse_chat_completion,
)
from .providers import MockMode, MockProvider, OpenAIResponsesProvider, StructuredJsonHttpProvider
from .measurement_constraints import (
    load_measurement_constraints,
    MeasurementConstraint,
    MeasurementConstraintError,
    MeasurementValidationResult,
    measurement_sidecar_path,
    parse_measurement_constraints,
    validate_measurement_constraints,
)
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
    "load_measurement_constraints",
    "MeasurementConstraint",
    "MeasurementConstraintError",
    "MeasurementValidationResult",
    "measurement_sidecar_path",
    "parse_measurement_constraints",
    "MockMode",
    "MockProvider",
    "OpenAIResponsesProvider",
    "ProviderCapabilities",
    "ProviderAuthenticationError",
    "ProviderCapabilityError",
    "ProviderConfig",
    "ProviderConfigurationError",
    "ProviderRateLimitError",
    "ProviderRequestError",
    "ProviderResponse",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "ChatCompletion",
    "ChatCompletionsTransport",
    "NebiusChatCompletionsPipelineProvider",
    "ObservationArtifact",
    "UrllibChatCompletionsTransport",
    "observation_json_schema",
    "parse_chat_completion",
    "StructuredJsonHttpProvider",
    "scene_tool_plan_json_schema",
    "spec_bundle_json_schema",
    "validate_measurement_constraints",
]
