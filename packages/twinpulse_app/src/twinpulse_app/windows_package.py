# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Hash-bound local EXE package verification, without executing its contents."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath


def digest(path):
    value = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def verify_package(root: Path):
    root = root.resolve()
    manifest = root / 'windows-release-manifest.json'
    if manifest.is_symlink() or manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    value = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != 'twinpulse-windows-exe-1.0':
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    files = value.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 20000:
        raise ValueError('WINDOWS_MANIFEST_INVALID')
    names = set()
    for entry in files:
        name = entry.get('path') if isinstance(entry, dict) else None
        if (not isinstance(name, str) or '\\' in name or ':' in name
                or PurePosixPath(name).is_absolute() or any(part in {'', '.', '..'} for part in name.split('/'))
                or name.casefold() in names or name == manifest.name):
            raise ValueError('WINDOWS_MANIFEST_PATH_INVALID')
        names.add(name.casefold())
        path = root / name
        if (not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents])
                or not path.is_file() or path.stat().st_size != entry.get('bytes')
                or digest(path) != entry.get('sha256')):
            raise ValueError('WINDOWS_PACKAGE_FILE_MISMATCH: ' + name)
    observed = {p.relative_to(root).as_posix().casefold() for p in root.rglob('*') if p.is_file() and p != manifest}
    if observed != names:
        raise ValueError('WINDOWS_PACKAGE_UNMANIFESTED_FILE')
    contract = value.get('data_contract')
    if contract is not None and (not isinstance(contract, dict) or
            contract.get('schema') != 'twinpulse-data-contract-1.0' or
            not isinstance(contract.get('read_epochs'), list) or
            type(contract.get('write_epoch')) is not int):
        raise ValueError('WINDOWS_DATA_CONTRACT_INVALID')
    return {'status': 'verified', 'build_id': value['build_id'], 'files': len(names),
            'product_version': value.get('product_version'),
            'data_contract': contract,
            'capabilities': value.get('capabilities', {}),
            'source_manifest_sha256': value['source_manifest_sha256'], 'public_ready': False}
