# SPDX-License-Identifier: Apache-2.0
"""Supplementary no-device verification; retains every cohort's original output."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'PYTHONPATH':os.pathsep.join([str(ROOT/'packages'/name/'src') for name in
        ('twinpulse_app','twinpulse_core','twinpulse_provider')]+[str(ROOT/'packages/twinpulse_robot_safety')])}
    groups=[('pc_protocol_fleet_stop_package',['-m','unittest',
        'tests.integration.test_physical_live_session','tests.integration.test_physical_fleet_adapter',
        'tests.integration.test_robot_fleet','tests.integration.test_http_mutation_lifecycle',
        'tests.integration.test_workspace_devices','tests.integration.test_robot_source_identity',
        'tests.integration.test_field_app_readiness',
        'tests.integration.test_windows_exe_contract','tests.integration.test_windows_install','-q']),
        ('legacy_physical_controller',['-m','unittest','tests.integration.test_physical_controller','-q']),
        ('native_saved_data_and_control',['-m','unittest','discover','-s','packages/twinpulse_robot_safety/tests','-p','test_fleet_native.py','-q']),
        ('pure_protection',['-m','unittest','discover','-s','packages/twinpulse_core/tests','-p','test_manual_motion_guard.py','-q']),
        ('continuous_legacy_worker',['-m','unittest','discover','-s','packages/twinpulse_robot_safety/tests','-p','test_continuous_worker_recovery.py','-q']),
        ('supervised_field_tests',['-m','unittest','discover','-s','packages/twinpulse_robot_safety/tests','-p','test_field_tests.py','-v'])]
    result=dict(schema='physical-readiness-offline-1.0',started_at=datetime.now(timezone.utc).isoformat(),
        classification='SUPPLEMENTARY_NOT_USER_OR_HARDWARE_ACCEPTANCE',physical_io=False,groups=[])
    for name,arguments in groups:
        started=time.monotonic()
        with (out/(name+'.log')).open('xb') as log:
            try:
                process=subprocess.run([sys.executable,*arguments],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                row=dict(name=name,status='PASS' if process.returncode==0 else 'FAIL',exit_code=process.returncode)
            except subprocess.TimeoutExpired:row=dict(name=name,status='TIMEOUT')
        row.update(elapsed_s=round(time.monotonic()-started,3),log=name+'.log',
                   sha256=hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest())
        result['groups'].append(row)
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
    result['status']='PASS' if all(r['status']=='PASS' for r in result['groups']) else 'FAIL'
    result['finished_at']=datetime.now(timezone.utc).isoformat()
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
