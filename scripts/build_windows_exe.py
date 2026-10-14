# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Build a new local one-folder release with explicit sources and original notices."""
from pathlib import Path
from hashlib import sha256
from importlib.metadata import distribution, version
from datetime import datetime, timezone
import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
import runpy

ROOT = Path(__file__).resolve().parents[1]


def hash_file(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--channel', choices=['development', 'sim-alpha'], default='sim-alpha')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError('BUILD_OUTPUT_ALREADY_EXISTS')
    if version('PyInstaller') != '6.22.3' or version('Pillow') != '12.3.0':
        raise ValueError('BUILD_TOOL_VERSION_MISMATCH')
    web_dist = ROOT / 'apps/twinpulse-web/dist'
    assets = ROOT / 'assets/simulation/turtlebot3_burger/usd'
    if not (web_dist / 'index.html').is_file() or not list((web_dist / 'assets').glob('*.js')):
        raise ValueError('BUILD_WEB_DIST_MISSING_RUN_LOCKED_WEB_BUILD')
    if len(list(assets.rglob('*.usd'))) + len(list(assets.rglob('*.usda'))) + len(list(assets.rglob('*.usdc'))) != 9:
        raise ValueError('BUILD_BURGER_ASSET_CLOSURE_MISSING')
    if not (ROOT / 'assets/simulation/turtlebot3_burger/ROBOTIS-LICENSE').is_file():
        raise ValueError('BUILD_BURGER_UPSTREAM_NOTICE_MISSING')
    output.mkdir(parents=True)
    resources = output / 'staging' / 'resources'
    sources = {}

    def copy(relative):
        source = ROOT / relative
        if not source.is_file() or any(p.is_symlink() for p in [source, *source.parents]):
            raise ValueError('RELEASE_SOURCE_MISSING_OR_LINK: ' + relative)
        destination = resources / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        sources[relative.replace('\\', '/')] = hash_file(source)

    for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
        for source in (ROOT / 'packages' / name / 'src').rglob('*'):
            if source.is_file() and '__pycache__' not in source.parts and source.suffix in {'.py', '.json', '.toml'}:
                copy(source.relative_to(ROOT).as_posix())
    for source in (ROOT / 'extensions/twinpulse.extension').rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts and source.suffix in {'.py', '.toml', '.json', '.md'}:
            copy(source.relative_to(ROOT).as_posix())
    scripts = ('twinpulse_launcher.py', 'twinpulse_backend.py', 'twinpulse_engine_host.py',
        'twinpulse_desktop_entry.py', 'twinpulse_bootstrap_integrity.py', 'build_windows_exe.py',
        'twinpulse_capture_contract.py', 'inspect_robot_evidence.py', 'ros_message_diagnostics.py',
        'prepare_robot.py', 'run_robot_readiness.py')
    for name in scripts:
        copy('scripts/' + name)
    for name in ('packaging/windows/TwinPulse.spec', 'packages/twinpulse_app/pyproject.toml',
                 'pyproject.toml', 'packages/twinpulse_provider/pyproject.toml'):
        copy(name)
    # Include imported repository helpers without importing/running robot code.
    pending = list(scripts)
    visited = set(scripts)
    while pending:
        source = ROOT / 'scripts' / pending.pop()
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            names = [item.name for item in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                filename = name.split('.')[0] + '.py'
                if filename not in visited and (ROOT / 'scripts' / filename).is_file():
                    visited.add(filename); pending.append(filename); copy('scripts/' + filename)
    for source in (ROOT / 'packages/twinpulse_robot_safety').rglob('*'):
        if (source.is_file() and not any(part in {'build', 'checks', '__pycache__'} for part in source.parts)
                and source.suffix in {'.py', '.json', '.cpp', '.hpp', '.txt', '.patch', '.md', '.sh'}):
            copy(source.relative_to(ROOT).as_posix())
    for source in web_dist.rglob('*'):
        if source.is_file():
            copy(source.relative_to(ROOT).as_posix())
    for source in assets.rglob('*'):
        if source.is_file() and source.suffix in {'.usd', '.usda', '.usdc'}:
            copy(source.relative_to(ROOT).as_posix())
    for name in ('LICENSE', 'NOTICE', 'CITATION.cff', 'THIRD_PARTY_NOTICES.md',
                 'docs/LICENSING.md', 'docs/RELEASE_PROVENANCE.md', 'docs/WINDOWS_EXE_QUICKSTART.md',
                 'docs/WINDOWS_EXE_BUILD.md', 'scripts/build_windows_exe.ps1',
                 'config/python-runtime-requirements.lock', 'config/python-build-requirements.lock',
                 'assets/simulation/turtlebot3_burger/ROBOTIS-LICENSE',
                 'assets/simulation/turtlebot3_burger/SOURCE.json'):
        copy(name)
    for name in ('LICENSE', 'NOTICE'):
        copy('extensions/twinpulse.extension/' + name)
    # The engine payload is self-contained, while no user state or original photo is copied.
    original_tools = ('Pillow', 'PyInstaller', 'altgraph', 'packaging', 'pefile',
                      'pyinstaller-hooks-contrib', 'pywin32-ctypes', 'setuptools', 'pip')
    notices = resources / 'third-party-notices'; notices.mkdir()
    tool_metadata = {}
    for name in original_tools:
        dist = distribution(name)
        tool_metadata[name] = dist.version
        for relative in dist.files or ():
            # Metadata license directories sometimes also contain executable
            # helper/cache files. Only original notice texts belong here.
            notice_name = Path(relative).name.lower()
            if (any(notice_name.startswith(token) for token in ('license', 'copying', 'notice'))
                    or '.dist-info/licenses/' in str(relative).replace('\\', '/').lower()) and Path(relative).suffix.lower() not in {'.py', '.pyc', '.pyo', '.dll', '.exe', '.so', '.pyd'}:
                source = Path(dist.locate_file(relative))
                if source.is_file():
                    destination = notices / name / str(relative).replace('..', '_').replace('\\', '/')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    # Full original Python license; application dependency notices are not relicensed.
    for name in ('LICENSE.txt', 'LICENSE'):
        source = Path(sys.base_prefix) / name
        if source.is_file():
            shutil.copy2(source, notices / ('Python-' + name))
    product = tomllib.loads((resources / 'packages/twinpulse_app/pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    source_sha = sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    build_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + source_sha[:12]
    (resources / 'source-manifest.json').write_text(json.dumps(sources, sort_keys=True, indent=2), encoding='utf-8')
    env = {**os.environ, 'TWINPULSE_BUILD_RESOURCES': str(resources), 'PYTHONDONTWRITEBYTECODE': '1'}
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
        '--distpath', str(output / 'dist'), '--workpath', str(output / 'work'),
        str(resources / 'packaging/windows/TwinPulse.spec')], env=env, cwd=resources, check=True)
    package = output / 'dist/TwinPulse'
    if list((package/'_internal/resources').rglob('*.pyc')):
        raise ValueError('PACKAGE_SOURCE_BYTECODE_CACHE_PRESENT')
    for name in ('LICENSE', 'NOTICE', 'CITATION.cff', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(resources / name, package / name)
    shutil.copy2(resources / 'docs/WINDOWS_EXE_QUICKSTART.md', package / 'README.md')
    (package/'Install-TwinPulse.cmd').write_text('@echo off\n"%~dp0TwinPulse.exe" --install\n',encoding='utf-8')
    files = [{'path': p.relative_to(package).as_posix(), 'bytes': p.stat().st_size, 'sha256': hash_file(p)}
             for p in sorted(package.rglob('*')) if p.is_file()]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = {'schema': 'twinpulse-windows-exe-1.0', 'build_id': build_id,
        'product_version': product, 'git_revision': revision, 'dirty': bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=ROOT)), 'source_manifest_sha256': source_sha,
        'platform': 'win-x64', 'tools': tool_metadata, 'signed': False,
        'public_release_status': 'LOCAL_CANDIDATE_REQUIRES_REVIEW', 'files': files}
    DATA_CONTRACT = runpy.run_path(str(resources/'packages/twinpulse_app/src/twinpulse_app/release_contract.py'))['DATA_CONTRACT']
    manifest.update(channel=args.channel, data_contract=DATA_CONTRACT,
        capabilities=dict(simulation=True, physical_robot=args.channel != 'sim-alpha'),
        release_version=product.replace('a', '-alpha.') if 'a' in product else product)
    (package / 'windows-release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    archive = output / ('TwinPulse-Windows-x64-' + manifest['release_version'] + '-' + build_id + '.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zipfile_out:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                zipfile_out.write(path, 'TwinPulse/' + path.relative_to(package).as_posix())
    (output / 'SHA256SUMS.txt').write_text(hash_file(archive) + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps({'package': str(package), 'zip': str(archive), 'sha256': hash_file(archive), 'build_id': build_id}))


if __name__ == '__main__':
    main()
