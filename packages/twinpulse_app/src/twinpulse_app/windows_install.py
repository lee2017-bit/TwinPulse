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
from .windows_package import verify_package
from .release_contract import MaintenanceLock, DATA_CONTRACT, check_data_epoch, atomic_json


def install_package(source: Path, destination: Path):
    state = Path(os.environ.get('LOCALAPPDATA', Path(destination).parent)) / 'TwinPulse/runtime'
    with MaintenanceLock(state):
        return _install_package(source, destination, state)


def _install_package(source: Path, destination: Path, state: Path):
    source, destination = source.resolve(), destination.resolve()
    checked = verify_package(source)
    identity = checked['build_id']
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}', identity):
        raise ValueError('INSTALL_BUILD_ID_INVALID')
    # Updating a live release must never replace the files under its supervisor.
    launcher_lock = state / 'launcher.lock'
    if launcher_lock.exists():
        from .process_manager import _pid_alive, _process_identity
        try:
            owner = json.loads(launcher_lock.read_text(encoding='utf-8'))
            pid = owner.get('owner_pid', owner.get('pid'))
            if type(pid) is not int or pid <= 0 or _pid_alive(pid):
                raise ValueError('EXIT_TWINPULSE_BEFORE_INSTALL')
            # A proven dead owner is retained as a diagnostic, never a lock.
            preserved = state / 'stale-launch-records' / (uuid4().hex + '.json')
            preserved.parent.mkdir(parents=True, exist_ok=True)
            launcher_lock.rename(preserved)
        except (json.JSONDecodeError, AttributeError):
            raise ValueError('EXIT_TWINPULSE_BEFORE_INSTALL') from None
    contract = checked.get('data_contract') or DATA_CONTRACT
    epoch = check_data_epoch(state, contract)
    if contract.get('write_epoch') != epoch:
        raise ValueError('DATA_MIGRATION_NOT_IMPLEMENTED')
    if any(p.is_symlink() for p in [destination, *destination.parents]):
        raise ValueError('INSTALL_PATH_INVALID')
    releases = destination / 'releases'
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / identity
    if not target.exists():
        stage = releases / ('.stage-' + uuid4().hex)
        shutil.copytree(source, stage)
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
    old = json.loads(active.read_text(encoding='utf-8')) if active.exists() else None
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
    # A stable entry follows the current pointer. User data stays outside releases.
    for filename, script in (
        ('Start-TwinPulse.cmd', '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-installed.ps1"\r\n'),
        ('Start-TwinPulse-Test.cmd', '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-installed.ps1" -AutomationTest\r\n'),
        ('start-installed.ps1', 'param([switch]$AutomationTest)\n$ErrorActionPreference="Stop"\n'
            '$pointer=Get-Content -LiteralPath (Join-Path $PSScriptRoot "active-release.json") -Raw | ConvertFrom-Json\n'
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
            'start': str(destination / 'Start-TwinPulse.cmd'), 'user_data': 'preserved',
            'test_start': str(destination / 'Start-TwinPulse-Test.cmd'),
            'data_epoch': epoch, 'rollback': 'same declared epoch only; original formats preserved'}


def rollback_package(destination: Path, release_id: str):
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}', release_id):
        raise ValueError('INSTALL_BUILD_ID_INVALID')
    package = Path(destination) / 'releases' / release_id
    if verify_package(package).get('data_contract') is None:
        raise ValueError('ROLLBACK_TARGET_HAS_NO_DATA_CONTRACT')
    return install_package(package, destination)
