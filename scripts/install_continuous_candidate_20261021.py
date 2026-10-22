# SPDX-License-Identifier: Apache-2.0
"""Install the explicit local candidate; never create a robot connection."""
import json
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_package import verify_package
from twinpulse_app.windows_install import install_package

OUT=ROOT/'outputs/robot-continuous-repair-20261021'
parser=argparse.ArgumentParser()
parser.add_argument('--candidate',required=True,choices=[f'{n:02}' for n in range(1,100)])
args=parser.parse_args()
source=OUT/f'build{args.candidate}/dist/TwinPulse'
verified=verify_package(source)
manifest=json.loads((source/'windows-release-manifest.json').read_text(encoding='utf-8'))
if not manifest.get('capabilities',{}).get('physical_robot'):raise ValueError('DEVELOPMENT_FIELD_CAPABILITY_REQUIRED')
installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
if (installed.parent/'runtime/launcher.lock').exists():raise ValueError('EXIT_APP_NORMALLY_FIRST')
receipt=install_package(source,installed,reuse_desktop_from=installed/'releases/20261020T151454Z-77e1d4b55192')
checked=verify_package(Path(receipt['exe']).parent)
with (OUT/f'installation{args.candidate}.json').open('x',encoding='utf-8') as stream:
    json.dump(dict(receipt=receipt,verification=checked),stream,indent=2)
print(json.dumps(dict(status=receipt['status'],build_id=receipt['build_id'],files=checked['files'])))
