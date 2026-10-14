# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bound serialized scene metadata without imposing a room-wide object quota."""
SCENE_PAYLOAD_BYTES=2*1024*1024


def check_scene_payload(value):
    import json
    size=0
    try:
        # Numeric validity belongs to the unchanged geometry/domain validators.
        for chunk in json.JSONEncoder(ensure_ascii=False).iterencode(value):
            size+=len(chunk.encode('utf-8'))
            if size>SCENE_PAYLOAD_BYTES:
                raise ValueError('SCENE_SERIALIZED_MEMORY_BUDGET_REACHED')
    except (TypeError,RecursionError) as error:
        raise ValueError('SCENE_PAYLOAD_INVALID') from error
    return size
