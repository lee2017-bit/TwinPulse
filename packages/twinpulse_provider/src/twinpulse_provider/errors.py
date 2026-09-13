"""Typed failures that the Extension can present without parsing strings."""


class ProviderError(RuntimeError):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderCapabilityError(ProviderError):
    pass


class InvalidProviderResponseError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class GenerationCancelledError(ProviderError):
    pass
