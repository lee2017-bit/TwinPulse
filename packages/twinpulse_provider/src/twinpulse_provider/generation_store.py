# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded local snapshots/cache; reading never dispatches, builds or resumes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from twinpulse_core import canonical_sha256
from .errors import ProviderConfigurationError

LIMIT = 2 * 1024 * 1024
_WINDOWS = os.name == 'nt'
_POINTER_REPLACE_DELAYS = (.025, .05, .1, .2, .4, .8)


def _replace_checkpoint_pointer(temporary, destination):
    """Retry only the same durable local write, never generation or dispatch.

    Windows readers without FILE_SHARE_DELETE (including scanners) can briefly
    deny replacing an existing pointer. Immutable history is already durable.
    A permanent denial still fails after at most 1.575 seconds of backoff; the
    old pointer is never removed first or treated as the newly saved version.
    """
    for attempt in range(len(_POINTER_REPLACE_DELAYS) + 1):
        try:
            os.replace(temporary, destination)
            return
        except OSError as error:
            if (not _WINDOWS or getattr(error, 'winerror', None) not in (5, 32, 33)
                    or attempt == len(_POINTER_REPLACE_DELAYS)):
                raise
            time.sleep(_POINTER_REPLACE_DELAYS[attempt])


class GenerationStore:
    def __init__(self, root):
        self.root = Path(root)

    def _path(self, kind, key):
        import re
        if kind not in ('observation', 'checkpoint', 'render') or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ProviderConfigurationError('Generation store identity invalid')
        return self.root / kind / (key+'.json')

    def read(self, kind, key):
        path = self._path(kind, key)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > LIMIT:
                raise ValueError('oversized')
            envelope = json.loads(path.read_text(encoding='utf-8'))
            if (set(envelope) != {'schema_version', 'payload_sha256', 'payload'}
                    or envelope['schema_version'] != 'generation-store-1.0'
                    or canonical_sha256(envelope['payload']) != envelope['payload_sha256']):
                raise ValueError('digest')
            return deepcopy(envelope['payload'])
        except (ValueError, OSError, TypeError) as error:
            raise ProviderConfigurationError('GENERATION_STORE_CORRUPT') from error

    def save(self, kind, key, value):
        path = self._path(kind, key)
        payload = deepcopy(value)
        data = json.dumps({'schema_version': 'generation-store-1.0',
            'payload_sha256': canonical_sha256(payload), 'payload': payload},
            ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(data) > LIMIT:
            raise ProviderConfigurationError('GENERATION_STORE_LIMIT')
        if kind == 'render' and path.exists():
            if path.read_bytes() != data:
                raise ProviderConfigurationError('GENERATION_RENDER_EVIDENCE_CONFLICT')
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name('.'+uuid4().hex+'.tmp')
        primary_error = None
        try:
            with temporary.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if kind == 'checkpoint':
                # Immutable versions preserve failed and last valid candidates;
                # the latest pointer is merely a convenience, not the history.
                history = self.root/'checkpoint-history'/key
                history.mkdir(parents=True, exist_ok=True)
                snapshot = history/(canonical_sha256(payload)+'.json')
                if snapshot.exists():
                    if snapshot.read_bytes() != data:
                        raise ProviderConfigurationError('GENERATION_HISTORY_CORRUPT')
                else:
                    with snapshot.open('xb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
            if kind == 'checkpoint':
                _replace_checkpoint_pointer(temporary, path)
            else:
                os.replace(temporary, path)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                if primary_error is None:
                    raise
                # Keep the primary failure, not a misleading cleanup error.
                # An unremoved temp is not promoted or reused automatically.
                primary_error.add_note('Generation temporary cleanup also failed: '
                    + type(cleanup_error).__name__
                    + ' winerror=' + str(getattr(cleanup_error, 'winerror', None)))


def input_digest(request):
    import hashlib
    return canonical_sha256({'prompt': request.prompt, 'image_detail': request.image_detail,
        'images': [{'sha256': hashlib.sha256(image.content).hexdigest(), 'mime_type': image.mime_type}
                   for image in request.images]})
