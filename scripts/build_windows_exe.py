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
# Installed path for a 20-character Windows user name; MAX_PATH leaves 259 characters.
INSTALL_RELEASES = 'C:\\Users\\' + 'u' * 20 + '\\AppData\\Local\\TwinPulse\\installed\\releases\\'
MAX_PATH_CHARS = 259
# The read-only company-PC check. It ships in the ZIP, so a company PC needs nothing else.
PC_CHECK = 'scripts/twinpulse_company_pc_check.py'
# Repository files staged beside the sources (and so hash-bound in source-manifest.json).
EXTRA_FILES = ('LICENSE', 'NOTICE', 'CITATION.cff', 'THIRD_PARTY_NOTICES.md',
               'docs/LICENSING.md', 'docs/RELEASE_PROVENANCE.md', 'docs/WINDOWS_EXE_QUICKSTART.md',
               'docs/WINDOWS_EXE_BUILD.md', 'docs/ROBOT_FLEET_PREPARATION_GUIDE.md', 'scripts/build_windows_exe.ps1',
               'config/python-runtime-requirements.lock', 'config/python-build-requirements.lock',
               'assets/simulation/turtlebot3_burger/ROBOTIS-LICENSE',
               'assets/simulation/turtlebot3_burger/SOURCE.json', PC_CHECK)
# Top-level package files, beside TwinPulse.exe and Install-TwinPulse.cmd (the ZIP's
# TwinPulse/ folder): published name -> its staged copy. The manifest lists every one.
TOP_LEVEL_FILES = {'LICENSE': 'LICENSE', 'NOTICE': 'NOTICE', 'CITATION.cff': 'CITATION.cff',
                   'THIRD_PARTY_NOTICES.md': 'THIRD_PARTY_NOTICES.md',
                   'README.md': 'docs/WINDOWS_EXE_QUICKSTART.md',
                   'twinpulse_company_pc_check.py': PC_CHECK}


def hash_file(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def stage(relative, resources, sources):
    """Copy one repository file into the staging snapshot and record its SHA-256 in sources."""
    source = ROOT / relative
    if not source.is_file() or any(p.is_symlink() for p in [source, *source.parents]):
        raise ValueError('RELEASE_SOURCE_MISSING_OR_LINK: ' + relative)
    destination = resources / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    sources[relative.replace('\\', '/')] = hash_file(source)


def add_top_level_files(resources, package):
    """Copy the staged top-level files into the package and write its two .cmd entries."""
    for name, staged in TOP_LEVEL_FILES.items():
        shutil.copy2(resources / staged, package / name)
    (package/'Install-TwinPulse.cmd').write_text('@echo off\n"%~dp0TwinPulse.exe" --install\n',encoding='utf-8')
    (package/'Start-TwinPulse-Test.cmd').write_text('@echo off\n"%~dp0TwinPulse.exe" --automation-test\n',encoding='utf-8')


def package_files(package):
    """Manifest rows (path, bytes, sha256) for every file in the package folder."""
    return [{'path': p.relative_to(package).as_posix(), 'bytes': p.stat().st_size, 'sha256': hash_file(p)}
            for p in sorted(package.rglob('*')) if p.is_file()]


def write_zip(package, archive):
    """The distribution ZIP: every package file under one top folder, TwinPulse/."""
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zipfile_out:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                zipfile_out.write(path, 'TwinPulse/' + path.relative_to(package).as_posix())


def finish_package(resources, package, manifest, archive=None, *, allow_long=False):
    """Complete the package folder in the one order an installable ZIP needs.

    The top-level files come first, so the file list and the manifest include
    them (a file added after the listing is an unlisted extra that install
    refuses: WINDOWS_PACKAGE_UNMANIFESTED_FILE). Then the install path check,
    then the manifest, and the ZIP last, so it carries the manifest. No ZIP
    when archive is None (--package-only).
    """
    add_top_level_files(resources, package)
    files = package_files(package)
    install_path_check([row['path'] for row in files], manifest['build_id'], allow_long=allow_long)
    manifest['files'] = files
    (package / 'windows-release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if archive is not None:
        write_zip(package, archive)
    return manifest


def reuse_desktop(package, destination, sources):
    """Reuse unchanged, verified desktop bytes through same-volume hard links.

    Build output is immutable: no linked file is edited. This keeps incremental
    Python/web builds possible on a nearly full development disk. Installation
    still follows the ordinary package verifier and installer.
    """
    verify = runpy.run_path(str(ROOT/'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
    verified = verify(package)
    previous = json.loads((package/'_internal/resources/source-manifest.json').read_text(encoding='utf-8'))
    names = [name for name in sources if name.startswith('apps/twinpulse-desktop/')]
    names += ['LICENSE','NOTICE']
    if any(previous.get(name) != sources[name] for name in names):
        raise ValueError('DESKTOP_REUSE_SOURCE_CHANGED')
    manifest = json.loads((package/'windows-release-manifest.json').read_text(encoding='utf-8'))
    declared = json.loads((ROOT/'apps/twinpulse-desktop/package.json').read_text(encoding='utf-8'))
    if manifest['tools'].get('Electron') != declared['devDependencies']['electron']:
        raise ValueError('DESKTOP_REUSE_RUNTIME_CHANGED')
    shutil.copytree(package/'desktop',destination,copy_function=os.link)
    return dict(electron=manifest['tools']['Electron'],source_build_id=verified['build_id'])


def burger_asset_check(assets):
    """The packaged Burger USD folder must hold exactly the reviewed public bytes."""
    sys.dont_write_bytecode = True
    for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
        if str(ROOT / 'packages' / name / 'src') not in sys.path:
            sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
    from twinpulse_app.simulation_assets import PUBLIC_BURGER_MANIFEST, _inventory
    inventory = _inventory(Path(assets))
    changed = sorted(name for name in {*inventory, *PUBLIC_BURGER_MANIFEST} if inventory.get(name) != PUBLIC_BURGER_MANIFEST.get(name))
    if changed:
        raise ValueError('BUILD_BURGER_ASSET_NOT_PUBLIC: ' + ', '.join(changed))
    return inventory


def install_path_check(names, release_id, *, allow_long=False):
    """Print the five longest package paths as installed; fail past MAX_PATH.

    The staged copy (.stage- plus 12 hex) and the final release folder are
    both measured; the longer one counts. allow_long (--allow-long-paths)
    keeps the warning but builds anyway."""
    prefix = len(INSTALL_RELEASES + max('.stage-' + 'x' * 12, release_id, key=len) + '\\')
    longest = sorted(names, key=lambda name: (-len(name), name))[:5]
    print('Longest installed paths (limit %d, 20-character user name):' % MAX_PATH_CHARS)
    for name in longest:
        print('  %d (%d relative) %s' % (prefix + len(name), len(name), name))
    total = prefix + len(longest[0])
    if total > MAX_PATH_CHARS:
        message = 'BUILD_INSTALL_PATH_TOO_LONG: %d > %d: %s' % (total, MAX_PATH_CHARS, longest[0])
        if not allow_long:
            raise ValueError(message)
        print('WARNING ' + message + ' (--allow-long-paths; needs Windows long paths on the target PC)')
    return total, longest[0]


def sprint_gate_receipt(root,max_age_s=24*3600):
    """Refuse to build unless Verify-Sprint passed on this exact commit recently (phys09 review P0-8).

    A fix that was never run through its own test suite reached installed builds 33-52 on
    2026-10-26 (a red regression test sat on main). The receipt is written by scripts/verify_sprint.ps1.
    """
    path=root/'outputs/verify-sprint/latest.json'
    if not path.is_file():
        raise ValueError('SPRINT_GATE_RECEIPT_MISSING: run Verify-Sprint.cmd first (or --skip-sprint-gate)')
    receipt=json.loads(path.read_text(encoding='utf-8-sig'))
    head=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],stdout=subprocess.PIPE,check=True,text=True).stdout.strip()
    dirty=subprocess.run(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],stdout=subprocess.PIPE,check=True,text=True).stdout.strip()
    if receipt.get('status')!='PASS':
        raise ValueError('SPRINT_GATE_FAILED: last Verify-Sprint run did not pass (%s)'%receipt.get('run_id'))
    if receipt.get('head')!=head:
        raise ValueError('SPRINT_GATE_STALE_COMMIT: receipt is for %s, HEAD is %s; run Verify-Sprint.cmd again'%(receipt.get('head'),head))
    if receipt.get('dirty') or dirty:
        # The tested tree and the built tree must be the same tree: commit, then Verify-Sprint, then build.
        raise ValueError('SPRINT_GATE_DIRTY_TREE: tracked files changed since/at the Verify-Sprint run; commit and run Verify-Sprint.cmd again')
    finished=datetime.strptime(receipt['finished_utc'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc)-finished).total_seconds()>max_age_s:
        raise ValueError('SPRINT_GATE_STALE_TIME: receipt older than %d min; run Verify-Sprint.cmd again'%(max_age_s//60))
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--channel', choices=['development', 'sim-alpha', 'robot-observation'], default='sim-alpha')
    parser.add_argument('--package-only',action='store_true',help='Build the verified local package without a redundant distribution ZIP.')
    parser.add_argument('--reuse-desktop-from',type=Path,
        help='Verified immutable prior package with identical desktop sources; same-volume hard links only.')
    parser.add_argument('--skip-sprint-gate',action='store_true',
        help='Build without a fresh Verify-Sprint PASS receipt (emergency only; the receipt check is the default).')
    parser.add_argument('--allow-long-paths',action='store_true',
        help='Build even if an installed path would pass 259 characters (20-character user name); the warning is '
             'still printed. Without Windows long paths such a package may fail to install or start.')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError('BUILD_OUTPUT_ALREADY_EXISTS')
    if not args.skip_sprint_gate:
        sprint_gate_receipt(ROOT)
    if version('PyInstaller') != '6.22.3' or version('Pillow') != '12.3.0':
        raise ValueError('BUILD_TOOL_VERSION_MISMATCH')
    # A pre-existing dist can be older than the very sources copied below.
    # Always regenerate with the already-installed locked tools; never install
    # packages implicitly and never package stale UI after a source-only edit.
    web = ROOT / 'apps/twinpulse-web'
    suffix = '.cmd' if os.name == 'nt' else ''
    for tool, arguments in (('tsc', ['-b']), ('vite', ['build'])):
        executable=web/'node_modules/.bin'/(tool+suffix)
        if not executable.is_file():raise ValueError('BUILD_WEB_TOOLING_MISSING')
        subprocess.run([str(executable), *arguments],cwd=web,check=True)
    web_dist = ROOT / 'apps/twinpulse-web/dist'
    assets = ROOT / 'assets/simulation/turtlebot3_burger/usd'
    if not (web_dist / 'index.html').is_file() or not list((web_dist / 'assets').glob('*.js')):
        raise ValueError('BUILD_WEB_DIST_MISSING_RUN_LOCKED_WEB_BUILD')
    # A wrong Burger byte fails here, on the build PC, not on a company PC.
    burger_asset_check(assets)
    if not (ROOT / 'assets/simulation/turtlebot3_burger/ROBOTIS-LICENSE').is_file():
        raise ValueError('BUILD_BURGER_UPSTREAM_NOTICE_MISSING')
    output.mkdir(parents=True)
    resources = output / 'staging' / 'resources'
    sources = {}

    def copy(relative):
        stage(relative, resources, sources)

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
        'prepare_robot.py', 'run_robot_readiness.py', 'check_robot_connection.py',
        'robot_health.py', 'turtlebot_probe.py', 'robot_source_identity.py','twinpulse_library_worker.py','twinpulse_motion_review_worker.py',
        'twinpulse_environment_worker.py','twinpulse_alignment_archive_worker.py')
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
                and (source.suffix in {'.py', '.json', '.cpp', '.hpp', '.txt', '.patch', '.md', '.sh','.xml'}
                     or source.name in {'LICENSE','NOTICE'})):
            copy(source.relative_to(ROOT).as_posix())
    for source in web_dist.rglob('*'):
        if source.is_file():
            copy(source.relative_to(ROOT).as_posix())
    for source in assets.rglob('*'):
        if source.is_file() and source.suffix in {'.usd', '.usda', '.usdc'}:
            copy(source.relative_to(ROOT).as_posix())
    for name in EXTRA_FILES:
        copy(name)
    for name in ('LICENSE', 'NOTICE'):
        copy('extensions/twinpulse.extension/' + name)
    for name in ('package.json', 'package-lock.json', 'main.mjs', 'preload.cjs', 'protocol.mjs', 'package.mjs', 'automation.cjs', 'self-test-runner.cjs', 'icon.ico'):
        copy('apps/twinpulse-desktop/' + name)
    runtime_path = json.loads(subprocess.check_output(['node','-e',
        "const p=require.resolve('playwright/package.json',{paths:[require.resolve('@playwright/test')]});console.log(JSON.stringify(require.resolve('playwright-core/package.json',{paths:[p]})))"],
        cwd=ROOT/'apps/twinpulse-web',text=True)).strip()
    runtime_root=Path(runtime_path).parent
    if json.loads(Path(runtime_path).read_text(encoding='utf-8'))['version']!='1.63.0':
        raise ValueError('TEST_RUNTIME_VERSION_MISMATCH')
    for source in sorted(runtime_root.rglob('*')):
        if source.is_file():
            relative='apps/twinpulse-desktop/testing/playwright-core/'+source.relative_to(runtime_root).as_posix()
            destination=resources/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,destination);sources[relative]=hash_file(source)
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
    # Desktop host is separate from the Python engine and the external Isaac
    # installation. Both are hash-inventoried in the same immutable release.
    if args.reuse_desktop_from is not None:
        desktop=reuse_desktop(args.reuse_desktop_from.resolve(),package/'desktop',sources)
    else:
        desktop_result = subprocess.check_output(['node', str(ROOT / 'apps/twinpulse-desktop/package.mjs'),
            '--output', str(output / 'desktop-build'), '--source-dir', str(resources / 'apps/twinpulse-desktop')], cwd=ROOT, text=True)
        desktop = json.loads(desktop_result.strip().splitlines()[-1])
        shutil.copytree(desktop['package'], package / 'desktop')
    tool_metadata['Electron'] = desktop['electron']
    tool_metadata['@electron/packager'] = '20.3.0'
    if list((package/'_internal/resources').rglob('*.pyc')):
        raise ValueError('PACKAGE_SOURCE_BYTECODE_CACHE_PRESENT')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = {'schema': 'twinpulse-windows-exe-1.0', 'build_id': build_id,
        'product_version': product, 'git_revision': revision, 'dirty': bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=ROOT)), 'source_manifest_sha256': source_sha,
        'platform': 'win-x64', 'tools': tool_metadata, 'signed': False,
        'public_release_status': 'LOCAL_CANDIDATE_REQUIRES_REVIEW', 'files': None}  # filled by finish_package
    DATA_CONTRACT = runpy.run_path(str(resources/'packages/twinpulse_app/src/twinpulse_app/release_contract.py'))['DATA_CONTRACT']
    manifest.update(channel=args.channel, data_contract=DATA_CONTRACT,
        capabilities=dict(simulation=True, physical_robot=args.channel == 'development',
                          robot_observation=args.channel == 'robot-observation'),
        release_version=product.replace('a', '-alpha.') if 'a' in product else product)
    if desktop.get('source_build_id'):
        manifest['desktop_reused_from']=desktop['source_build_id']
    archive = None if args.package_only else output / (
        'TwinPulse-Windows-x64-' + manifest['release_version'] + '-' + build_id + '.zip')
    finish_package(resources, package, manifest, archive, allow_long=args.allow_long_paths)
    if archive is None:
        print(json.dumps({'package':str(package),'zip':None,'sha256':None,'build_id':build_id,'archive_status':'NOT_REQUESTED_LOCAL_PACKAGE_ONLY'}))
        return
    (output / 'SHA256SUMS.txt').write_text(hash_file(archive) + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps({'package': str(package), 'zip': str(archive), 'sha256': hash_file(archive), 'build_id': build_id}))


if __name__ == '__main__':
    main()
