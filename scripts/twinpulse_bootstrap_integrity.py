# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Compiled bootstrap check: run before importing any external App payload."""
from pathlib import Path
from hashlib import sha256
import json


def verify_before_import(root):
    root = Path(root).resolve()
    manifest = root / 'windows-release-manifest.json'
    if manifest.is_symlink() or manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    value = json.loads(manifest.read_text(encoding='utf-8'))
    entries = value.get('files') if isinstance(value, dict) else None
    if value.get('schema') != 'twinpulse-windows-exe-1.0' or not isinstance(entries, list) or not 1 <= len(entries) <= 20000:
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    seen = set();checked_parents=set()
    for entry in entries:
        name = entry.get('path') if isinstance(entry, dict) else None
        if (not isinstance(name, str) or ':' in name or '\\' in name or name.startswith('/')
                or any(p in {'', '.', '..'} for p in name.split('/')) or name.casefold() in seen):
            raise ValueError('WINDOWS_MANIFEST_PATH_INVALID')
        seen.add(name.casefold())
        path = root / name
        # Check each shared ancestor once per verification, not once per file.
        # Still hash every byte, resolve every file, check its own link/size,
        # and enumerate undeclared files. No persistent trust/cache is used.
        parents=[p for p in path.parents if p not in checked_parents]
        if (not path.is_file() or not path.resolve().is_relative_to(root)
                or path.is_symlink() or any(p.is_symlink() for p in parents) or path.stat().st_size != entry.get('bytes')):
            raise ValueError('WINDOWS_PACKAGE_FILE_MISMATCH: ' + name)
        checked_parents.update(parents)
        h = sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        if h.hexdigest() != entry.get('sha256'):
            raise ValueError('WINDOWS_PACKAGE_FILE_MISMATCH: ' + name)
    observed = {p.relative_to(root).as_posix().casefold() for p in root.rglob('*') if p.is_file() and p != manifest}
    if observed != seen:
        raise ValueError('WINDOWS_PACKAGE_UNMANIFESTED_FILE')
    return value
