# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Resource limits apply to serialized work, not the room's object count."""
OBSERVATION_PAYLOAD_BYTES = 2 * 1024 * 1024
SEMANTIC_PAYLOAD_BYTES = 2 * 1024 * 1024
PARAMETER_BATCH_SIZE = 6


def checked_payload_bytes(value, limit, code):
    import json
    from .errors import ProviderConfigurationError
    # This checks byte resources only. Domain validators retain their original
    # finite-number/type diagnostics (including malformed model candidates).
    size = 0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False).iterencode(value):
            size += len(chunk.encode('utf-8'))
            if size > limit:
                raise ProviderConfigurationError(code)
    except (TypeError, ValueError, RecursionError) as error:
        raise ProviderConfigurationError('SCENE_PAYLOAD_NOT_SERIALIZABLE') from error
    return size
