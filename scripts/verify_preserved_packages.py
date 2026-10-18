# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Verify retained package/ZIP bytes without starting any application/device."""
import hashlib
import json
import os
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/github-preservation-20261018'
PINS={
    '20261018T044930Z-d0d4e62d6701':('artifacts/robot-focused-test-20261018/build06','b40e498fc19eda8b045152c92cddc91def3b90f824e047146a47f01bc1f1dd8f'),
    '20261018T054101Z-10f256a1732a':('artifacts/robot-powered-ui-20261018/build01','09a209c22720f914bd9d0c35980763669c09b81c755d75b484fd7e76fdd04120'),
    '20261018T060740Z-eb840a4afcaa':('artifacts/robot-powered-ui-20261018/build02','dfbb6e94bea236b0f5c7c87cd4f82fae4882eb01208bd1882f1371fceaf04cb3'),
}


def main():
    verify=runpy.run_path(str(ROOT/'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
    installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
    results=[]
    for build,(relative,expected) in PINS.items():
        result=dict(build_id=build)
        for name,package in [('installed',installed/'releases'/build),('local_build',ROOT/relative/'dist/TwinPulse')]:
            checked=verify(package)
            if checked['build_id']!=build:raise ValueError('PINNED_PACKAGE_ID_MISMATCH')
            result[name]=dict(status=checked['status'],files=checked['files'],source_sha256=checked['source_manifest_sha256'])
        archives=list((ROOT/relative).glob('TwinPulse-Windows-*'+build+'.zip'))
        if len(archives)!=1:raise ValueError('PINNED_ZIP_MISSING_OR_DUPLICATE')
        h=hashlib.sha256()
        with archives[0].open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
        if h.hexdigest()!=expected:raise ValueError('PINNED_ZIP_SHA_CHANGED')
        result['zip_sha256']=expected;results.append(result)
    active=json.loads((installed/'active-release.json').read_text(encoding='utf-8'))['release_id']
    if active!='20261018T060740Z-eb840a4afcaa':raise ValueError('ACTIVE_POINTER_CHANGED')
    observed=sorted(p.name for p in (installed/'releases').iterdir() if p.is_dir())
    result=dict(status='PASS',active_release=active,remaining_installed=observed,packages=results)
    (OUT/'protected-package-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
