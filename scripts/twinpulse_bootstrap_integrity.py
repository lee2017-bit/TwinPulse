# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Compiled bootstrap check: run before importing any external App payload.

Installation hashes every file (verify_package on the extracted source and on
the staged copy), and so does --inspect-package. A normal start runs the quick
check: every listed file exists, is no link, stays under the root and has its
recorded size; full=True also hashes every byte. A launcher child only reads
the manifest (read_manifest). Owner decision, 2026-11-03."""
from pathlib import Path
from hashlib import sha256
import json

# File-manager metadata (Explorer, Finder); never imported, executed or read.
OS_JUNK = frozenset({'thumbs.db', 'desktop.ini', '.ds_store'})


def read_manifest(root):
    """Validate the manifest and its path rules without opening any listed file."""
    manifest = Path(root).resolve() / 'windows-release-manifest.json'
    if manifest.is_symlink() or manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    value = json.loads(manifest.read_text(encoding='utf-8-sig'))
    entries = value.get('files') if isinstance(value, dict) else None
    if not isinstance(entries, list) or value.get('schema') != 'twinpulse-windows-exe-1.0' or not 1 <= len(entries) <= 20000:
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    seen = set()
    for entry in entries:
        name = entry.get('path') if isinstance(entry, dict) else None
        if (not isinstance(name, str) or ':' in name or '\\' in name or name.startswith('/')
                or any(p in {'', '.', '..'} for p in name.split('/')) or name.casefold() in seen):
            raise ValueError('WINDOWS_MANIFEST_PATH_INVALID')
        seen.add(name.casefold())
    return value


def unmanifested(names):
    shown = ', '.join(names[:5]) + (' (+%d more)' % (len(names) - 5) if len(names) > 5 else '')
    return 'WINDOWS_PACKAGE_UNMANIFESTED_FILE' + (': ' + shown if names else '')


def verify_before_import(root, *, full=False):
    root = Path(root).resolve()
    value = read_manifest(root)
    manifest = root / 'windows-release-manifest.json'
    seen = set();checked_parents=set()
    for entry in value['files']:
        name = entry['path'];seen.add(name.casefold())
        path = root / name
        # Check each shared ancestor once per verification, not once per file.
        # Still resolve every file, check its own link/size, hash every byte
        # when full, and enumerate undeclared files. No trust/cache is kept.
        parents=[p for p in path.parents if p not in checked_parents]
        if (not path.is_file() or not path.resolve().is_relative_to(root)
                or path.is_symlink() or any(p.is_symlink() for p in parents) or path.stat().st_size != entry.get('bytes')):
            raise ValueError('WINDOWS_PACKAGE_FILE_MISMATCH: ' + name)
        checked_parents.update(parents)
        if full:
            h = sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != entry.get('sha256'):
                raise ValueError('WINDOWS_PACKAGE_FILE_MISMATCH: ' + name)
    observed = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != manifest}
    extra = sorted(n for n in observed if n.casefold() not in seen and n.rsplit('/', 1)[-1].casefold() not in OS_JUNK)
    if extra or not seen <= {n.casefold() for n in observed}:
        raise ValueError(unmanifested(extra))
    return value
