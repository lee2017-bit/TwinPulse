# SPDX-License-Identifier: Apache-2.0
"""Install the reviewed local field-preparation candidate, never contact a robot."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
from twinpulse_app.windows_install import install_package
from twinpulse_app.windows_package import verify_package

OUT = ROOT / 'outputs/robot-field-ready-20261020'
attempt = sys.argv[1] if len(sys.argv) == 2 else '02'
if attempt not in {'02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18'}:
    raise ValueError('Explicit reviewed candidate required')
source = OUT / ('build' + attempt) / 'dist/TwinPulse'
verify_package(source)
manifest=json.loads((source/'windows-release-manifest.json').read_text(encoding='utf-8'))
if attempt in {'11','12','13','14','15','16','17','18'} and manifest.get('capabilities',{}).get('physical_robot') is not True:
    raise ValueError('FIELD_CANDIDATE_PHYSICAL_CAPABILITY_REQUIRED')
installed = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed'
if (installed.parent / 'runtime/launcher.lock').exists():
    raise ValueError('Exit the current App normally before replacing installation')
reuse = ('20261020T145921Z-cef2890a955c' if attempt=='18' else
         '20261020T142821Z-2f5fd1f23976' if attempt in {'16','17'} else
         '20261020T141317Z-975cebb8d8b6' if attempt=='15' else
         '20261020T135124Z-819dba0740d7' if attempt=='14' else
         '20261020T130655Z-7464ec6bcea2' if attempt=='13' else
         '20261020T121823Z-9f0a5bb0ae10' if attempt in {'11','12'} else
         '20261020T121021Z-584facc28b70' if attempt=='10' else
         '20261020T081059Z-29c886bf13b1' if attempt=='09' else
         '20261020T070644Z-121b7f208205' if attempt in {'05','06','07','08'} else '20261020T034213Z-ee4c39105987')
options = {} if attempt == '04' else {'reuse_desktop_from': installed / 'releases' / reuse}
receipt = install_package(source, installed, **options)
checked = verify_package(Path(receipt['exe']).parent)
with (OUT / ('installation' + attempt + '.json')).open('x', encoding='utf-8') as stream:
    json.dump(dict(receipt=receipt, verification=checked), stream, indent=2)
print(json.dumps(dict(status=receipt['status'], build_id=receipt['build_id'], files=checked['files'])))
