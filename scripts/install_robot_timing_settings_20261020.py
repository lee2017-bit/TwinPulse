# SPDX-License-Identifier: Apache-2.0
"""One verified development install; never modifies robot/system installations."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_install import install_package
from twinpulse_app.windows_package import verify_package
OUT=ROOT/'outputs/robot-timing-settings-20261020'
build=sys.argv[1] if len(sys.argv)==2 else '02'
if build not in {'02','03','04','05','06'}:raise ValueError('Unknown reviewed build')
source=OUT/('build-'+build)/'dist/TwinPulse'
checked=verify_package(source)
receipt=install_package(source,Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed')
target=Path(receipt['exe']).parent
verification=verify_package(target)
record=dict(receipt=receipt,verification=verification)
(OUT/('installation'+build+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
