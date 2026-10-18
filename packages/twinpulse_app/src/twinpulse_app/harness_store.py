# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Immutable local profile revisions. Routes contain only small exact refs."""
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from twinpulse_provider.harness_profiles import binding, checked_binding

MAX_PROFILE_BYTES = 256 * 1024  # Six 6,000-character stages, including UTF-8.

class HarnessStore:
    def __init__(self, state_root):
        self.root = Path(state_root) / 'harness-profiles'

    def _path(self, sha):
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
            raise ValueError('HARNESS_REF_INVALID')
        return self.root / (sha + '.json')

    def save(self, profile):
        frozen = binding(profile)
        path = self._path(frozen['sha256'])
        data = json.dumps(frozen, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(data) > MAX_PROFILE_BYTES:
            raise ValueError('HARNESS_STORAGE_LIMIT')
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / ('.' + uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes() != data:
                    raise ValueError('HARNESS_STORAGE_CONFLICT') from None
        finally:
            temporary.unlink(missing_ok=True)
        return {k: frozen[k] for k in ('id', 'revision', 'sha256')}

    def resolve(self, reference, *, provider, model, role):
        if not isinstance(reference, dict) or set(reference) != {'id', 'revision', 'sha256'}:
            raise ValueError('HARNESS_REF_INVALID')
        path = self._path(reference['sha256'])
        if path.is_symlink() or path.stat().st_size > MAX_PROFILE_BYTES:
            raise ValueError('HARNESS_STORAGE_INVALID')
        frozen = checked_binding(json.loads(path.read_text(encoding='utf-8')),
            provider=provider, model=model, role=role)
        if reference != {k: frozen[k] for k in ('id', 'revision', 'sha256')}:
            raise ValueError('HARNESS_REF_MISMATCH')
        return frozen

    def list_refs(self, *, provider, model, role):
        if not self.root.exists():
            return []
        result = []
        for path in sorted(self.root.glob('*.json')):
            if path.is_symlink() or path.stat().st_size > MAX_PROFILE_BYTES:
                continue
            try:
                raw = json.loads(path.read_text(encoding='utf-8'))
                reference = {k: raw[k] for k in ('id', 'revision', 'sha256')}
                self.resolve(reference, provider=provider, model=model, role=role)
            except (KeyError, OSError, TypeError, ValueError):
                continue
            result.append(reference)
        return result
