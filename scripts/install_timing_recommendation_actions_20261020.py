# SPDX-License-Identifier: Apache-2.0
"""Install the one scoped local candidate after package verification."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_install import install_package
from twinpulse_app.windows_package import verify_package
OUT=ROOT/'outputs/timing-recommendation-actions-20261020'
build=sys.argv[1] if len(sys.argv)==2 else '02'
if build not in {'01','02'}:raise ValueError('Unknown scoped candidate')
source=OUT/('build-'+build)/'dist/TwinPulse'
verify_package(source)
receipt=install_package(source,Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed')
record=dict(receipt=receipt,verification=verify_package(Path(receipt['exe']).parent))
(OUT/('installation'+build+'.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(dict(status=receipt['status'],build_id=receipt['build_id'],verified_files=record['verification']['files'])))
