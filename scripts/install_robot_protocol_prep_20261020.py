# SPDX-License-Identifier: Apache-2.0
"""Install only this frozen local candidate; no SSH or device changes."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_install import install_package
from twinpulse_app.windows_package import verify_package
OUT=ROOT/'outputs/robot-protocol-prep-20261020'
build=sys.argv[1] if len(sys.argv)==2 else '01'
if build not in {'01','02','03','04'}:raise ValueError('Unknown preparation candidate')
source=OUT/('build-'+build)/'dist/TwinPulse'
verify_package(source)
installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
options={'reuse_desktop_from':installed/'releases/20261020T031424Z-a31becb620c7'} if build in {'02','03','04'} else {}
receipt=install_package(source,installed,**options)
checked=verify_package(Path(receipt['exe']).parent)
record=dict(receipt=receipt,verification=checked)
(OUT/('installation'+build+'.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(dict(status=receipt['status'],build_id=receipt['build_id'],files=checked['files'])))
