# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Non-secret installation settings; publish only after a successful bind."""
import json
import os
from pathlib import Path
from uuid import uuid4

DEFAULT_PORT = 8765
PORT_CANDIDATES = 10


def read_settings(state_dir: Path):
    path = state_dir / 'desktop-settings.json'
    if not path.exists():
        return {'schema_version': '1.0', 'preferred_port': DEFAULT_PORT}
    if path.is_symlink() or path.stat().st_size > 8192:
        raise ValueError('DESKTOP_SETTINGS_INVALID')
    value = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or value.get('schema_version') != '1.0'
            or type(value.get('preferred_port')) is not int
            or not 1024 <= value['preferred_port'] <= 65535
            or set(value) - {'schema_version', 'preferred_port', 'isaac_root'}
            or ('isaac_root' in value and not isinstance(value['isaac_root'], str))):
        raise ValueError('DESKTOP_SETTINGS_INVALID')
    return value


def save_settings(state_dir: Path, **changes):
    value = {**read_settings(state_dir), **changes}
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / 'desktop-settings.json'
    temporary = path.with_name('.desktop-settings.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
