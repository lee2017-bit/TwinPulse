# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only package hashes, with a new evidence receipt. No App/device calls."""
import json
import os
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
    active=json.loads((installed/'active-release.json').read_text(encoding='utf-8-sig'))
    verify=runpy.run_path(str(ROOT/'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
    package=installed/Path(active['exe']).parent
    result=verify(package)
    if result['build_id']!=active['release_id'] or result['source_manifest_sha256']!=active['source_manifest_sha256']:
        raise ValueError('ACTIVE_INSTALLATION_MISMATCH')
    if result['status']!='verified':raise ValueError('PACKAGE_NOT_VERIFIED')
    result.update(status='PASS',package_verification='verified',release_id=active['release_id'],mismatches=[],package=str(package))
    with a.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))
