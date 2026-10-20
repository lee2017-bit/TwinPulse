# SPDX-License-Identifier: Apache-2.0
"""Read-only installation/owned runtime check and local evidence receipt."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
from twinpulse_app.windows_package import verify_package

out = ROOT / 'outputs/robot-protocol-prep-20261020'
local = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse'
active = json.loads((local / 'installed/active-release.json').read_bytes())
verified = verify_package((local / 'installed' / active['exe']).parent)
if verified['build_id'] != '20261020T034213Z-ee4c39105987':
    raise ValueError('Active release changed')
ports_raw = subprocess.run(['powershell', '-NoProfile', '-Command',
    "@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {$_.LocalPort -in 8765,19222} | Select-Object LocalPort,OwningProcess) | ConvertTo-Json -Compress"],
    capture_output=True, text=True, check=True).stdout.strip()
ports = json.loads(ports_raw) if ports_raw else []
lock = (local / 'runtime/launcher.lock').exists()
last_ui = json.loads((out / 'actual-ui12/result.json').read_bytes())
launch = last_ui['identity']['engine']['launch_id']
cleanup = json.loads((local / 'runtime/launches' / launch / 'cleanup-receipt.json').read_bytes())
record = dict(schema='robot-protocol-final-state-1.0', at=datetime.now(timezone.utc).isoformat(),
    active=active, verification=verified, ports=ports, launcher_lock_present=lock,
    cleanup=cleanup, physical_connections=last_ui['physical'],
    disk_free_bytes=shutil.disk_usage('C:\\').free,
    limitation='No robot connection or new provider call. Disk is low despite reviewed cleanup; final runtime minimum free was about0.6GB, not a stable capacity guarantee.')
if ports or lock or not cleanup.get('owned_processes_stopped') or any(r['state'] != 'DISCONNECTED' or r.get('operation') for r in record['physical_connections']):
    raise ValueError('Runtime not cleaned or physical connection unexpectedly active')
(out / 'final-state.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(dict(status='VERIFIED_AND_STOPPED', files=verified['files'], free=record['disk_free_bytes'], launch=launch)))
