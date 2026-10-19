# SPDX-License-Identifier: Apache-2.0
"""Supplementary only: preserve logs; never opens a robot, model or App API."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def source_receipt():
    installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
    active=json.loads((installed/'active-release.json').read_text(encoding='utf-8-sig'))
    source=installed/Path(active['exe']).parent/'_internal/resources/source-manifest.json'
    raw=source.read_bytes();manifest=json.loads(raw)
    if hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()!=active['source_manifest_sha256']:raise ValueError('Installed source manifest mismatch')
    # These immutable dependency bytes are copied by the builder from the
    # locked Playwright package, not repository paths. Installation hash
    # acceptance separately verifies them; compare all repository sources here.
    repository={name:digest for name,digest in manifest.items() if not name.startswith('apps/twinpulse-desktop/testing/playwright-core/')}
    mismatches=[name for name,digest in repository.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    if mismatches:raise ValueError('Repository differs from installed tested sources: '+str(mismatches[:10]))
    return dict(release_id=active['release_id'],source_sha256=active['source_manifest_sha256'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--group')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    before=source_receipt()
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(ROOT/'packages'/p/'src') for p in ('twinpulse_app','twinpulse_core','twinpulse_provider'))+os.pathsep+str(ROOT/'packages/twinpulse_robot_safety')+os.pathsep+str(ROOT/'packages/twinpulse_robot_safety/tests')}
    node=shutil.which('node')
    groups=[('lineage-and-pc',ROOT,[sys.executable,'-m','unittest','tests.integration.test_engine_loss_probe','tests.integration.test_r6_process_manager','tests.integration.test_backend_status_storage','tests.integration.test_robot_twin_lineage',
        'tests.integration.test_fleet_elapsed_motion','tests.integration.test_sim_fleet_navigation','tests.integration.test_bootstrap_integrity_current','tests.integration.test_robot_focus_gate',
        'tests.integration.test_physical_live_session','tests.integration.test_physical_fleet_adapter','tests.integration.test_robot_fleet','tests.integration.test_fleet_registration_history',
        'tests.integration.test_field_app_readiness','tests.integration.test_http_mutation_lifecycle','tests.integration.test_http_reuse','tests.integration.test_bridge_robot_channel','tests.integration.test_bridge_lease_rotation','tests.integration.test_live_viewport','tests.integration.test_fleet_diagnostic_isolation','tests.integration.test_residual_status_admission','tests.integration.test_workspace_devices',
        'tests.integration.test_conversation_save_rename','tests.integration.test_conversation_preservation','tests.integration.test_project_sim_retirement',
        'tests.integration.test_robot_source_identity','tests.integration.test_windows_exe_contract','tests.integration.test_windows_install','-v']),
        ('native-worker',ROOT,[sys.executable,'-m','unittest','discover','-s','packages/twinpulse_robot_safety/tests','-p','test_fleet_native.py','-v']),
        ('field',ROOT,[sys.executable,'-m','unittest','test_field_tests','test_control_recovery','test_native_parser_quality','test_control_observation','-v']),
        ('ui',ROOT/'apps/twinpulse-web',[node,'node_modules/vitest/vitest.mjs','run','src/App.test.tsx','src/RobotFleet.test.tsx','src/RobotFieldTests.test.tsx','src/RobotRegistry.test.tsx','src/IsaacConnectionStatus.test.tsx','src/api.test.ts','src/TwinViewport.test.tsx','src/ChatWorkspace.test.tsx','--maxWorkers=1','--no-file-parallelism']),
        ('web-build',ROOT/'apps/twinpulse-web',[node,'node_modules/typescript/bin/tsc','-b'])]
    if args.group:
        groups=[g for g in groups if g[0]==args.group]
        if not groups:raise ValueError('Unknown supplementary group')
    result=dict(classification='SUPPLEMENTARY_NOT_INSTALLED_UI_OR_HARDWARE_ACCEPTANCE',started_at=datetime.now(timezone.utc).isoformat(),groups=[],**before)
    for name,cwd,command in groups:
        start=time.monotonic();target=out/(name+'.log')
        with target.open('xb') as log:
            try:
                run=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                row=dict(name=name,status='PASS' if run.returncode==0 else 'FAIL',exit_code=run.returncode)
            except subprocess.TimeoutExpired:row=dict(name=name,status='TIMEOUT')
        row.update(elapsed_s=round(time.monotonic()-start,3),log=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        result['groups'].append(row);(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(row),flush=True)
    result['source_unchanged']=source_receipt()==before
    result['status']='PASS' if result['source_unchanged'] and all(r['status']=='PASS' for r in result['groups']) else 'FAIL'
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
