# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only local benchmark identity, not an Isaac readiness/performance test.

Fixed entrypoints + package versions + reviewed Burger dependency closure.
No credentials, process/service launch, network, driver query or machine name.
This deliberately does NOT hash the entire Isaac/Python/browser installation.
"""
from copy import deepcopy
from datetime import datetime, timezone
from importlib import metadata
import os
from pathlib import Path
import platform
import shutil
import sys

from scripts.benchmark_protocol import _digest, _shape, _text, canonical_sha, file_sha

VERSION = 'benchmark-environment-1.0'
PACKAGES = ('Pillow', 'numpy', 'pytest', 'psutil')
RUNTIME_NAMES = ('python', 'node', 'chrome', 'isaac_version', 'isaac_launcher',
                 'isaac_setup', 'isaac_kit', 'isaac_python', 'isaac_python_kit')
COVERAGE = dict(entrypoints='SHA256', burger_dependency_closure='REVIEWED_SHA256',
                python_packages='VERSION_METADATA_ONLY', procedural_furniture='SOURCE_FREEZE',
                full_install_dependency_closure='NOT_FROZEN', gpu_driver='NOT_OBSERVED',
                actual_isaac_readiness='NOT_RUN')


def runtime_paths():
    """Match actual ordinary Manager/PATH Node/fixed Chrome entrypoints."""
    if os.environ.get('PYTHONEXE'):
        raise ValueError('BENCHMARK_ISAAC_PYTHON_OVERRIDE_UNSUPPORTED')
    node = shutil.which('node')
    if not node:
        raise ValueError('BENCHMARK_RUNTIME_MISSING_NODE')
    isaac = Path('C:/isaacsim')
    return dict(python=Path(sys.executable), node=Path(node),
                chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
                isaac_version=isaac/'VERSION', isaac_launcher=isaac/'python.bat',
                isaac_setup=isaac/'setup_python_env.bat', isaac_kit=isaac/'kit/kit.exe',
                isaac_python=isaac/'kit/python/python.exe', isaac_python_kit=isaac/'kit/python/kit.exe')


def file_record(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('BENCHMARK_LINKED_RUNTIME')
    if not path.is_file():
        raise ValueError('BENCHMARK_RUNTIME_FILE_MISSING')
    return dict(path=str(path.resolve()), sha256=file_sha(path), size_bytes=path.stat().st_size)


def asset_inventory(root):
    from twinpulse_app.simulation_assets import _inventory
    asset_root = Path(root)/'artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1'
    inventory = _inventory(asset_root)
    return {name: file_record(asset_root/name) for name in sorted(inventory)}


def capture(root):
    files = {name: file_record(path) for name, path in runtime_paths().items()}
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None  # Metadata absence is visible, not fabricated.
    return checked_environment(dict(schema_version=VERSION,
        captured_at=datetime.now(timezone.utc).isoformat(),
        host=dict(system=platform.system(), release=platform.release(), machine=platform.machine(),
                  python_version=platform.python_version(), cpu_count=os.cpu_count()),
        python_packages=versions, runtime_files=files, assets=asset_inventory(root), coverage=COVERAGE))


def checked_environment(value):
    _shape(value, ('schema_version', 'captured_at', 'host', 'python_packages',
                  'runtime_files', 'assets', 'coverage'), 'BENCHMARK_ENVIRONMENT_INVALID')
    if value['schema_version'] != VERSION or value['coverage'] != COVERAGE:
        raise ValueError('BENCHMARK_ENVIRONMENT_VERSION_OR_COVERAGE_INVALID')
    try:
        date = datetime.fromisoformat(value['captured_at'])
        if date.utcoffset() is None:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('BENCHMARK_ENVIRONMENT_DATE_INVALID') from None
    _shape(value['host'], ('system', 'release', 'machine', 'python_version', 'cpu_count'),
           'BENCHMARK_HOST_INVALID')
    for key in ('system', 'release', 'machine', 'python_version'):
        _text(value['host'][key], 160, 'BENCHMARK_HOST_INVALID')
    if type(value['host']['cpu_count']) is not int or not 1 <= value['host']['cpu_count'] <= 4096:
        raise ValueError('BENCHMARK_HOST_INVALID')
    _shape(value['python_packages'], PACKAGES, 'BENCHMARK_PACKAGE_INVENTORY_INVALID')
    for version in value['python_packages'].values():
        if version is not None:
            _text(version, 160, 'BENCHMARK_PACKAGE_VERSION_INVALID')
    _shape(value['runtime_files'], RUNTIME_NAMES, 'BENCHMARK_RUNTIME_INVENTORY_INVALID')
    from twinpulse_app.simulation_assets import BURGER_MANIFEST
    _shape(value['assets'], BURGER_MANIFEST, 'BENCHMARK_ASSET_INVENTORY_INVALID')
    for record in [*value['runtime_files'].values(), *value['assets'].values()]:
        _shape(record, ('path', 'sha256', 'size_bytes'), 'BENCHMARK_RUNTIME_FILE_INVALID')
        _text(record['path'], 1024, 'BENCHMARK_RUNTIME_PATH_INVALID')
        _digest(record['sha256'])
        if not Path(record['path']).is_absolute() or type(record['size_bytes']) is not int or record['size_bytes'] <= 0:
            raise ValueError('BENCHMARK_RUNTIME_FILE_INVALID')
    if any(value['assets'][name]['sha256'] != digest for name, digest in BURGER_MANIFEST.items()):
        raise ValueError('BENCHMARK_UNREVIEWED_ASSETS')
    return deepcopy(value)


def identity(value):
    value = checked_environment(value)
    # Capture timestamp is provenance, not a new machine/runtime cohort.
    return canonical_sha({key: item for key, item in value.items() if key != 'captured_at'})


def verify_environment(prepared, root):
    frozen = prepared.get('execution_environment')
    if frozen is None:
        return dict(status='LEGACY_PARTIAL_FREEZE', environment_sha256=None,
                    actual_isaac_readiness='NOT_RUN')
    current = capture(root)
    if identity(current) != identity(frozen):
        raise ValueError('BENCHMARK_EXECUTION_ENVIRONMENT_CHANGED')
    return dict(status='ENTRYPOINTS_ASSETS_MATCH_NOT_RUNTIME_PASS',
                environment_sha256=identity(frozen), actual_isaac_readiness='NOT_RUN')


def audit_environment_evidence(approval, summary):
    expected = approval.get('execution_environment_sha256')
    if expected is None:
        return  # Legacy raw records are not retroactively upgraded/rejected.
    _digest(expected);_digest(approval.get('evaluation_rubric_sha256'))
    audit = summary.get('benchmark_environment_audit') or {}
    for key in ('before', 'after'):
        if audit.get(key) != dict(status='ENTRYPOINTS_ASSETS_MATCH_NOT_RUNTIME_PASS',
                environment_sha256=expected, actual_isaac_readiness='NOT_RUN'):
            raise ValueError('BENCHMARK_EXECUTION_ENVIRONMENT_AUDIT_MISSING_OR_CHANGED')
