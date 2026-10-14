# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only launcher prerequisites. Presence is not runtime qualification."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import os
import tempfile
import json
import re
import sys
import tomllib
from hashlib import sha256
from html.parser import HTMLParser
from importlib.metadata import version, PackageNotFoundError


def _row(name, state, detail, action=None, **extra):
    return dict(id=name, state=state, detail=detail, action=action,
                sampled_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), **extra)


def prepare_owned_directories(launch_dir: Path):
    """One attempt per derived directory; no source replacement or retries.

    Only call after acquiring the launcher lock, with its fresh launch ID.
    A colliding file/link is a failure, never removed to make the repair work.
    """
    if launch_dir.parent.name != 'launches':
        raise ValueError('OWNED_LAUNCH_PATH_REQUIRED')
    rows = []
    for name, path in [('owned_launch_directory', launch_dir),
                       ('owned_engine_directory', launch_dir/'engine-state')]:
        attempts = 0
        try:
            if any(p.is_symlink() for p in [path, *path.parents]):
                raise ValueError('OWNED_DIRECTORY_LINK_REJECTED')
            existed = path.is_dir()
            if not existed:
                attempts = 1
                path.mkdir(parents=True, exist_ok=True)
            rows.append(_row(name, 'ready', 'Owned derived directory already exists; preserved.' if existed
                             else 'Created the fresh owned derived directory once. No original project was changed.', attempts=attempts))
        except (OSError, ValueError) as error:
            # Do not publish arbitrary filesystem error messages/user paths.
            rows.append(_row(name, 'failed', f'OWNED_DIRECTORY_PREPARE_FAILED ({type(error).__name__}).',
                             'Check local access or the colliding file. No deletion or permission changes are attempted.', attempts=attempts))
    return rows


class _WebReferences(HTMLParser):
    def __init__(self):
        super().__init__(); self.paths = []
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script' and attributes.get('src'):
            self.paths.append(attributes['src'])
        if tag == 'link' and attributes.get('rel') == 'stylesheet' and attributes.get('href'):
            self.paths.append(attributes['href'])


def _web_manifest(web: Path):
    manifest = web/'twinpulse-build-manifest.json'
    if any(p.is_symlink() for p in [manifest, *manifest.parents]): raise ValueError('BUILD_MANIFEST_UNSAFE')
    if not manifest.is_file(): raise ValueError('BUILD_MANIFEST_MISSING')
    if manifest.stat().st_size > 65536: raise ValueError('BUILD_MANIFEST_INVALID')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    files = data.get('files') if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get('schema_version') != '1.0' or not isinstance(files, dict) or not 1 <= len(files) <= 128:
        raise ValueError('BUILD_MANIFEST_INVALID')
    for name, digest in files.items():
        if (not isinstance(name, str) or not re.fullmatch(r'(?:assets/[A-Za-z0-9_.-]+|index\.html)', name)
                or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)):
            raise ValueError('BUILD_MANIFEST_UNSAFE')
        path = web/name
        if any(p.is_symlink() for p in [path, *path.parents]) or not path.resolve().is_relative_to(web.resolve()):
            raise ValueError('BUILD_MANIFEST_UNSAFE')
        if not path.is_file(): raise ValueError('BUILD_DEPENDENCY_MISSING')
        if path.stat().st_size > 32*1024*1024: raise ValueError('BUILD_DEPENDENCY_TOO_LARGE')
        if sha256(path.read_bytes()).hexdigest() != digest: raise ValueError('BUILD_DIGEST_MISMATCH')
    if 'index.html' not in files: raise ValueError('BUILD_INDEX_NOT_BOUND')
    parser = _WebReferences(); parser.feed((web/'index.html').read_text(encoding='utf-8'))
    if not parser.paths: raise ValueError('BUILD_ENTRYPOINT_MISSING')
    if any(not ref.startswith('/assets/') or ref[1:] not in files for ref in parser.paths):
        raise ValueError('BUILD_REFERENCE_NOT_BOUND')
    return len(files)


def package_checklist(repo_root: Path, *, python_executable: Path | None = None):
    """Read reviewed static contracts, not provider secrets or Isaac imports."""
    from .simulation_assets import _inventory, asset_root
    rows=[]
    checks = [
        ('web_dependencies', lambda: f'{_web_manifest(repo_root/"apps/twinpulse-web/dist")} built Web files match their build manifest.',
         'Restore a reviewed built Web package or explicitly rebuild locally. No source is overwritten automatically.'),
        ('burger_asset_manifest', lambda: f'{len(_inventory(asset_root(repo_root)))} bundled Burger dependencies match reviewed SHA256 values.',
         'Restore the reviewed bundled asset. Do not download or replace the model automatically.'),
        ('extension_contract', lambda: _extension_contract(repo_root),
         'Restore the reviewed extension package. Engine dependency availability is checked at runtime.'),
        ('python_dependencies', lambda: _python_dependencies(python_executable),
         'Use the existing qualified Python environment. No package installer is run.'),
    ]
    for name, check, action in checks:
        try: rows.append(_row(name, 'ready', check()+' Static check only; not runtime qualification.'))
        except (OSError, ValueError, UnicodeError, PackageNotFoundError) as error:
            code = str(error) if type(error) is ValueError and re.fullmatch(r'[A-Z0-9_]{1,80}', str(error)) else type(error).__name__
            rows.append(_row(name, 'needs_action', code, action))
    return rows


def _extension_contract(repo_root):
    extension=repo_root/'extensions/twinpulse.extension'
    data=tomllib.loads((extension/'config/extension.toml').read_text(encoding='utf-8'))
    if (not isinstance(data.get('python'),dict) or not isinstance(data.get('settings'),dict)
            or not isinstance(data['settings'].get('exts'),dict)
            or not isinstance(data['settings']['exts'].get('twinpulse.extension'),dict)):
        raise ValueError('EXTENSION_CONTRACT_INVALID')
    if ({'name':'twinpulse.extension'} not in data.get('python',{}).get('module',[]) or
            data.get('settings',{}).get('exts',{}).get('twinpulse.extension',{}).get('ownedRoot') != '/World/TwinPulse'):
        raise ValueError('EXTENSION_CONTRACT_INVALID')
    required = ['twinpulse/extension/__init__.py','twinpulse/extension/isaac_adapter.py','twinpulse/extension/runtime.py']
    if any(not (extension/name).is_file() for name in required): raise ValueError('EXTENSION_MODULE_MISSING')
    return 'Extension module and owned-root contract found; declared engine dependencies are not imported by this check.'


def _python_dependencies(python_executable=None):
    if python_executable is not None and python_executable.resolve() != Path(sys.executable).resolve():
        raise ValueError('CONFIGURED_PYTHON_ENVIRONMENT_NOT_OBSERVED')
    parts=version('Pillow').split('.')
    if len(parts)<2 or any(not p.isdigit() for p in parts[:2]): raise ValueError('PYTHON_DEPENDENCY_VERSION_UNQUALIFIED')
    observed=tuple(int(p) for p in parts[:2])
    if sys.version_info < (3,12) or not (12,2) <= observed < (13,0):
        raise ValueError('PYTHON_DEPENDENCY_VERSION_UNQUALIFIED')
    return f'Python >=3.12 and Pillow {version("Pillow")} match application requirements.'


def file_checklist(required: dict[str, Path], *, state_dir: Path, isaac_python: Path):
    sampled = datetime.now(timezone.utc).isoformat(timespec='seconds')
    rows = []
    for name, path in required.items():
        try:
            found = path.is_file()
            rows.append({'id':name, 'state':'ready' if found else 'needs_action',
                         'detail':'Required file found; runtime behavior is checked separately.' if found else 'Required file is missing.',
                         'action':None if found else 'Restore the reviewed local package or configure the existing runtime. No automatic installation.',
                         'sampled_at':sampled})
        except OSError:
            rows.append({'id':name,'state':'failed','detail':'File observation failed.',
                         'action':'Check local filesystem access. No permission changes are attempted.', 'sampled_at':sampled})
    existing = state_dir
    while not existing.exists() and existing != existing.parent: existing = existing.parent
    try:
        free = shutil.disk_usage(existing).free
        rows.append({'id':'project_disk','state':'ready' if free >= 256*1024*1024 else 'needs_action',
                     'detail':f'{free // (1024*1024)} MiB free. This does not verify project write permission.',
                     'action':None if free >= 256*1024*1024 else 'Free disk space without removing source projects.', 'sampled_at':sampled})
    except OSError:
        rows.append({'id':'project_disk','state':'failed','detail':'Disk space observation unavailable.',
                     'action':'Check local filesystem access.', 'sampled_at':sampled})
    probe = None
    try:
        # The launcher already owns this state directory. Test only a newly
        # allocated file there, never an input, project source or user setting.
        with tempfile.NamedTemporaryFile(prefix='twinpulse-write-check-',dir=state_dir,delete=False) as stream:
            probe=Path(stream.name);stream.write(b'TwinPulse startup write check');stream.flush();os.fsync(stream.fileno())
        probe.unlink();probe=None
        rows.append({'id':'project_write','state':'ready','detail':'Owned launcher state directory accepted a flushed temporary write.',
                     'action':None,'sampled_at':sampled})
    except OSError:
        rows.append({'id':'project_write','state':'failed','detail':'Owned launcher state directory write check failed.',
                     'action':'Check available space and access to this project. No permission changes are attempted.','sampled_at':sampled})
    finally:
        if probe is not None:
            try:probe.unlink()
            except OSError:pass
    version_path = isaac_python.parent / 'VERSION'
    try:
        if version_path.stat().st_size > 1024: raise OSError('version metadata size limit')
        version = version_path.read_text(encoding='utf-8').strip()[:120]
        reviewed = version == '6.0.1-rc.7+release.42383.32955d8d.gl'
        rows.append({'id':'isaac_version','state':'ready' if reviewed else 'needs_action',
                     'detail':f'Observed Isaac version: {version}. '+('Matches the reviewed local runtime.' if reviewed else 'This runtime version has not been qualified by this checkout.'),
                     'action':None if reviewed else 'Qualify this version or point the launcher to the reviewed existing runtime.', 'sampled_at':sampled})
    except (OSError, UnicodeError):
        rows.append({'id':'isaac_version','state':'needs_action','detail':'Isaac version metadata not available beside the configured executable.',
                     'action':'Verify the existing Isaac runtime path; no installer is run.', 'sampled_at':sampled})
    return rows
