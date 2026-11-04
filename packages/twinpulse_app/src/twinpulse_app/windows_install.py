# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Per-user immutable releases and atomic active-pointer installation."""
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4
from .windows_package import OS_JUNK, verify_package
from .release_contract import MaintenanceLock, DATA_CONTRACT, check_data_epoch, atomic_json


def install_package(source: Path, destination: Path, *, reuse_desktop_from: Path | None = None):
    state = Path(os.environ.get('LOCALAPPDATA', Path(destination).parent)) / 'TwinPulse/runtime'
    with MaintenanceLock(state):
        return _install_package(source, destination, state,reuse_desktop_from=reuse_desktop_from)


def _retire_launcher_lock(launcher_lock: Path, state: Path):
    """Keep a dead or replaced owner's launcher.lock as a record; refuse anything else.

    The launcher applies the same rule (process_manager._owner_replaced).
    """
    from .process_manager import _owner_replaced, _pid_alive, _process_identity
    try:
        owner = json.loads(launcher_lock.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        owner = None
    pid = owner.get('owner_pid', owner.get('pid')) if isinstance(owner, dict) else None
    if type(pid) is not int or pid <= 0:
        # Not a record this installer can judge, for example an empty file left
        # by a crash: keep it unchanged rather than guess that it is stale.
        raise ValueError('INSTALL_LAUNCHER_LOCK_UNREADABLE')
    if _pid_alive(pid) and not _owner_replaced(owner.get('process_identity'), _process_identity(pid)):
        # The PID runs and is not proven to be another process now (both
        # identities with differing int creation times): never take over.
        raise ValueError('EXIT_TWINPULSE_BEFORE_INSTALL')
    # A proven dead or replaced owner is retained as a diagnostic, never a lock.
    preserved = state / 'stale-launch-records' / (uuid4().hex + '.json')
    preserved.parent.mkdir(parents=True, exist_ok=True)
    launcher_lock.rename(preserved)


def _install_package(source: Path, destination: Path, state: Path, *, reuse_desktop_from: Path | None = None):
    source, destination = source.resolve(), destination.resolve()
    checked = verify_package(source)
    identity = checked['build_id']
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}', identity):
        raise ValueError('INSTALL_BUILD_ID_INVALID')
    # Updating a live release must never replace the files under its supervisor.
    launcher_lock = state / 'launcher.lock'
    if launcher_lock.exists():
        _retire_launcher_lock(launcher_lock, state)
    # A legacy package has no support for newly required capabilities. Never
    # attribute the current program's feature support to an older package.
    contract = checked.get('data_contract') or {k:v for k,v in DATA_CONTRACT.items() if k!='read_capabilities'}
    epoch = check_data_epoch(state, contract)
    if contract.get('write_epoch') != epoch:
        raise ValueError('DATA_MIGRATION_NOT_IMPLEMENTED')
    if any(p.is_symlink() for p in [destination, *destination.parents]):
        raise ValueError('INSTALL_PATH_INVALID')
    releases = destination / 'releases'
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / identity
    desktop_links=0
    if not target.exists():
        # A short stage name keeps deep package paths under MAX_PATH.
        stage = releases / ('.stage-' + uuid4().hex[:12])
        previous=None;old_files={}
        new_files={x['path']:x for x in json.loads((source/'windows-release-manifest.json').read_text(encoding='utf-8-sig'))['files']}
        listed={name.casefold() for name in new_files}
        if reuse_desktop_from is not None:
            previous=Path(reuse_desktop_from).resolve()
            if previous.parent!=releases:raise ValueError('INSTALL_DESKTOP_REUSE_OUTSIDE_RELEASE_STORE')
            verify_package(previous)
            old_files={x['path']:x for x in json.loads((previous/'windows-release-manifest.json').read_text(encoding='utf-8-sig'))['files']}
        def copy_file(src,dst):
            nonlocal desktop_links
            name=Path(src).relative_to(source).as_posix()
            # Only identical, verified immutable desktop bytes share storage.
            # Changed files, Python/service code and all user data are copied.
            if previous is not None and name.startswith('desktop/') and old_files.get(name)==new_files.get(name) and name in new_files:
                try:os.link(previous/name,dst);desktop_links+=1;return dst
                except OSError:pass  # Cross-volume/non-NTFS: ordinary copy.
            return shutil.copy2(src,dst)
        def unlisted_junk(directory,names):
            # Explorer/Finder files beside the extracted ZIP never enter a release.
            base=Path(directory).relative_to(source).as_posix()
            return {n for n in names if n.casefold() in OS_JUNK and os.path.isfile(os.path.join(directory,n))
                    and (n if base=='.' else base+'/'+n).casefold() not in listed}
        shutil.copytree(source, stage,copy_function=copy_file,ignore=unlisted_junk)
        verify_package(stage)
        stage.rename(target)
    elif verify_package(target)['source_manifest_sha256'] != checked['source_manifest_sha256']:
        raise ValueError('INSTALL_RELEASE_COLLISION')
    active = destination / 'active-release.json'
    if active.is_symlink():
        raise ValueError('INSTALL_ACTIVE_PATH_INVALID')
    value = {'schema': 'twinpulse-windows-install-1.0', 'release_id': identity,
             'source_manifest_sha256': checked['source_manifest_sha256'],
             'exe': 'releases/' + identity + '/TwinPulse.exe'}
    old = None
    if active.exists():
        # An offline-installer pointer may carry a UTF-8 BOM. An unreadable one
        # never blocks the update; its bytes are copied unchanged below.
        raw = active.read_bytes()
        try:old = json.loads(raw.decode('utf-8-sig'))
        except ValueError:old = {'unparsed': True, 'bytes': len(raw)}
    journal = destination / 'update-journals' / (uuid4().hex + '.json')
    transaction = dict(schema='twinpulse-update-1.0', previous=old, target=value,
        data_epoch=epoch, data_conversion=False, phase='package_verified')
    atomic_json(journal, transaction)
    if active.exists():
        # Keep every old pointer, including a legacy Python installation.
        shutil.copy2(active, destination / ('active-release.previous.' + uuid4().hex + '.json'))
    temporary = destination / ('.active-' + uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, active)
    transaction['phase'] = 'active_pointer_committed'
    atomic_json(journal, transaction)
    # Stable entries are rewritten at every install and rollback, so they follow
    # the pointer. The .cmd entries need no PowerShell; the .ps1 is a fallback.
    # User data stays outside releases.
    program = '"%~dp0releases\\' + identity + '\\TwinPulse.exe"'
    for filename, script in (
        ('Start-TwinPulse.cmd', '@echo off\r\nstart "" ' + program + ' %*\r\n'),
        ('Start-TwinPulse-Test.cmd', '@echo off\r\nstart "" ' + program + ' --automation-test %*\r\n'),
        ('start-installed.ps1', 'param([switch]$AutomationTest)\n$ErrorActionPreference="Stop"\n'
            '$pointer=Get-Content -LiteralPath (Join-Path $PSScriptRoot "active-release.json") -Raw -Encoding UTF8 | ConvertFrom-Json\n'
            'if ($pointer.schema -ne "twinpulse-windows-install-1.0" -or $pointer.release_id -notmatch "^[A-Za-z0-9_-]{1,80}$" '
            '-or $pointer.exe -ne ("releases/"+$pointer.release_id+"/TwinPulse.exe")) { throw "Invalid installed release" }\n'
            'if ($AutomationTest) { & (Join-Path $PSScriptRoot $pointer.exe) --automation-test } else { & (Join-Path $PSScriptRoot $pointer.exe) }\n')):
        path = destination / filename
        if path.is_symlink():
            raise ValueError('INSTALL_ENTRY_PATH_INVALID')
        stage = path.with_name('.' + filename + '-' + uuid4().hex + '.tmp')
        with stage.open('x', encoding='utf-8', newline='') as stream:
            stream.write(script); stream.flush(); os.fsync(stream.fileno())
        os.replace(stage, path)
    transaction['phase'] = 'completed'
    atomic_json(journal, transaction)
    return {'status': 'installed', 'build_id': identity, 'exe': str(target / 'TwinPulse.exe'),
            'verified_desktop_hardlinks':desktop_links,
            'start': str(destination / 'Start-TwinPulse.cmd'), 'user_data': 'preserved',
            'test_start': str(destination / 'Start-TwinPulse-Test.cmd'),
            'data_epoch': epoch, 'rollback': 'same epoch and required capabilities only; no project conversion'}


def rollback_package(destination: Path, release_id: str):
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}', release_id):
        raise ValueError('INSTALL_BUILD_ID_INVALID')
    package = Path(destination) / 'releases' / release_id
    if verify_package(package).get('data_contract') is None:
        raise ValueError('ROLLBACK_TARGET_HAS_NO_DATA_CONTRACT')
    return install_package(package, destination)
