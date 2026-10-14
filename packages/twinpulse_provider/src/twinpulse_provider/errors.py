# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
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


class PhotoQualityValidationError(InvalidProviderResponseError):
    """Typed, bounded geometry failure; unsupported repairs must not dispatch."""

    def __init__(self, report):
        self.quality_report = report
        self.repairable = report['repairable']
        failures = ', '.join(i['code']+':'+i['id'] for i in report['issues'][:4])
        super().__init__('Photo geometry validation failed: '+failures)


class ProviderTimeoutError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


class GenerationCancelledError(ProviderError):
    pass
