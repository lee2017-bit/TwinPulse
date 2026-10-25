# SPDX-License-Identifier: Apache-2.0
"""Install exactly the local RoomPlan candidate, preserving runtime/user data."""
import json
import argparse
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for name in ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider'):
    sys.path.insert(0, str(root / 'packages' / name / 'src'))
from twinpulse_app.windows_package import verify_package
from twinpulse_app.windows_install import install_package

parser=argparse.ArgumentParser()
parser.add_argument('--output-root',type=Path,default=root/'outputs/roomplan-import-20261023')
parser.add_argument('--candidate',default='18')
args=parser.parse_args()
if len(args.candidate)!=2 or not args.candidate.isdecimal():raise ValueError('TWO_DIGIT_CANDIDATE_REQUIRED')
output = args.output_root.resolve()
source = output / ('build'+args.candidate) / 'dist/TwinPulse'
installed = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed'
if (installed.parent / 'runtime/launcher.lock').exists():
    raise ValueError('EXIT_APP_NORMALLY_FIRST')
verified = verify_package(source)
active=json.loads((installed/'active-release.json').read_text(encoding='utf-8-sig'))
receipt = install_package(source, installed,
    reuse_desktop_from=installed / Path(active['exe']).parent)
checked = verify_package(Path(receipt['exe']).parent)
with (output / ('installation'+args.candidate+'.json')).open('x', encoding='utf-8') as stream:
    json.dump(dict(receipt=receipt, verification=checked), stream, indent=2)
print(json.dumps(dict(status=receipt['status'], build_id=receipt['build_id'], files=checked['files'])))
