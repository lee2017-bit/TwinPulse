# SPDX-License-Identifier: Apache-2.0
"""Read-only retained-package/user-data integrity check; no credentials or App."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/github-preservation-20261020'
STORE = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed'
PINS = ['20261020T034213Z-ee4c39105987', '20261020T022703Z-d349de20d29b',
        '20261019T091021Z-ab4cc1fdeb77', '20261020T031424Z-a31becb620c7']


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--after', action='store_true')
    args = parser.parse_args()
    verify = runpy.run_path(str(ROOT / 'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
    packages = [verify(STORE / 'releases' / build) for build in PINS]
    manifest = json.loads((STORE / 'releases' / PINS[0] / '_internal/resources/source-manifest.json').read_bytes())
    if sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest() != packages[0]['source_manifest_sha256']:
        raise ValueError('CURRENT_SOURCE_MANIFEST_CHANGED')
    differences = []
    for name, value in manifest.items():
        if name.startswith('apps/twinpulse-desktop/testing/playwright-core/'):
            continue  # Exact immutable dependency bytes are covered by package verification.
        if not (ROOT / name).is_file() or digest(ROOT / name) != value:
            differences.append(name)
    runtime_differences = [name for name in differences if not name.startswith('docs/') and name != 'README.md']
    if runtime_differences:
        raise ValueError('RUNTIME_SOURCE_DIFFERS_FROM_TESTED_PACKAGE:' + str(runtime_differences))
    roots = [Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime/projects',
             Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime/devices',
             ROOT / 'saved-projects', ROOT / 'captures']
    protected = {}
    for root in roots:
        if not root.exists():
            continue
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(directory)/d).is_symlink() and not (Path(directory)/d).is_junction()]
            for name in files:
                file = Path(directory) / name
                if file.is_symlink() or file.is_junction():
                    raise ValueError('PROTECTED_DATA_LINK_REFUSED')
                protected[str(file)] = dict(bytes=file.stat().st_size, sha256=digest(file))
    original = Path('C:/Projects/TwinPulse/ITM0018.jpg')
    if original.exists():
        protected[str(original)] = dict(bytes=original.stat().st_size, sha256=digest(original))
    # Unrelated untracked diagrams must neither be staged nor cleaned.
    for file in (ROOT/'docs/verification').glob('*.png'):
        protected[str(file)] = dict(bytes=file.stat().st_size, sha256=digest(file))
    result = dict(status='PASS', active=json.loads((STORE/'active-release.json').read_bytes()),
        packages=packages, packaged_source_differences=sorted(differences),
        source_difference_scope='README/docs only; original package retains original bytes', protected=protected,
        remaining_installed=sorted(p.name for p in (STORE/'releases').iterdir() if p.is_dir()))
    if result['active']['release_id'] != PINS[0]:
        raise ValueError('ACTIVE_CHECKPOINT_CHANGED')
    if args.after:
        before=json.loads((OUT/'protected-before.json').read_bytes())
        if before['protected'] != protected:
            raise ValueError('PROTECTED_USER_DATA_CHANGED')
        plan=json.loads((ROOT/'outputs/build-retention-20261020-applied/plan.json').read_text(encoding='utf-8-sig'))
        running=[]
        for row in plan['protected']:
            path=Path(row['path'])
            if row['reason']=='RUNNING_REFERENCE' and path.parent == STORE/'releases':
                running.append(path.name)
                verify(path)
        result['protected_running_references']=sorted(running)
        if result['remaining_installed'] != sorted(set(PINS+running)):
            raise ValueError('UNEXPECTED_RETAINED_RELEASE_SET')
    OUT.mkdir(parents=True,exist_ok=True)
    file = OUT / ('protected-after.json' if args.after else 'protected-before.json')
    file.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(status='PASS', packages=len(packages), protected_files=len(protected),
        protected_bytes=sum(r['bytes'] for r in protected.values()), source_difference_paths=differences,
        after=args.after, remaining_installed=len(result['remaining_installed']))))


if __name__ == '__main__':
    main()
