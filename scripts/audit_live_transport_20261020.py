# SPDX-License-Identifier: Apache-2.0
"""Reproduce installed bootstrap rejection and check corrected bytes offline."""
import ast
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))
sys.path.insert(0, str(ROOT))
from twinpulse_app.physical_live_session import BOOTSTRAP, reviewed_bundle
from tests.integration.test_live_bootstrap_roundtrip import probe


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--original-package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();package=args.original_package.resolve()
    manifest=json.loads((package/'windows-release-manifest.json').read_bytes())
    source = package / '_internal/resources/packages/twinpulse_app/src/twinpulse_app/physical_live_session.py'
    declared=next(row['sha256'] for row in manifest['files'] if row['path']=='_internal/resources/packages/twinpulse_app/src/twinpulse_app/physical_live_session.py')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=declared:raise ValueError('ORIGINAL_SOURCE_HASH_CHANGED')
    old = next(ast.literal_eval(n.value) for n in ast.parse(source.read_bytes()).body
               if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'BOOTSTRAP' for t in n.targets))
    identity, encoded, expected = reviewed_bundle(ROOT)
    attempts = []
    for label, code in (('original_installed', old), ('corrected_checkout', BOOTSTRAP)):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = probe(code, encoded, home)
            release = home / '.local/share/twinpulse/fleet/releases' / identity
            actual = {p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in release.rglob('*') if p.is_file()}
            attempts.append(dict(label=label, bootstrap_sha256=hashlib.sha256(code.encode()).hexdigest(),
                                 exit_code=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode(),
                                 extracted_files=len(actual), all_members_exact=actual == expected,
                                 worker_sessions_created=(home / '.local/share/twinpulse/fleet/sessions').exists(),
                                 robot_data_created=(home / '.local/share/twinpulse/robot').exists()))
    passed = (b'BOOTSTRAP_PATH' in attempts[0]['stderr'].encode()
              and attempts[1]['stderr'].strip() == 'FLEET_WORKER_REJECTED:START_SHAPE'
              and attempts[1]['all_members_exact']
              and all(not a['worker_sessions_created'] and not a['robot_data_created'] for a in attempts))
    record = dict(schema='live-transport-offline-review-1.0', at=datetime.now(timezone.utc).isoformat(),
                  status='PASS_ORIGINAL_REPRODUCED_AND_CORRECTED' if passed else 'FAIL',
                  classification='OFFLINE_REAL_RECEIVER_SUBPROCESS_NOT_HARDWARE_OR_INSTALLED_UI',
                  original_release=manifest['build_id'], original_source_sha256=declared,bundle_sha256=identity,
                  bundle_bytes=len(encoded), member_count=len(expected), attempts=attempts,
                  ssh_connections=0, device_actions=0)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
    print(json.dumps(record))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
