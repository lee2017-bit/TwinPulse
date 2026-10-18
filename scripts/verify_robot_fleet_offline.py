# SPDX-License-Identifier: Apache-2.0
"""Run supplementary no-device suites and preserve their output separately from UI acceptance."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[1]
out=root/'outputs/robot-fleet-20261017/offline-final'
out.mkdir(exist_ok=False)
commands=[
 ('python-contracts',[sys.executable,'-m','unittest',
  'tests.integration.test_robot_fleet','tests.integration.test_physical_controller',
  'tests.integration.test_physical_fleet_adapter','tests.integration.test_workspace_devices',
  'tests.integration.test_live_viewport','tests.integration.test_r5_product_api',
  'packages.twinpulse_robot_safety.tests.test_continuous_intent',
  'packages.twinpulse_robot_safety.tests.test_continuous_worker_recovery']),
 ('legacy-teleop',[sys.executable,'-m','unittest','packages.twinpulse_robot_safety.tests.teleop_test']),
 ('native-guard',[sys.executable,'-m','unittest','packages.twinpulse_core.tests.test_manual_motion_guard']),
 ('ui-components',['node','node_modules/vitest/vitest.mjs','run','src/RobotFleet.test.tsx',
  'src/TwinViewport.test.tsx','src/PhysicalRobotController.test.tsx','src/ChatWorkspace.test.tsx'])]
result=dict(status='IN_PROGRESS',started_at=datetime.now(timezone.utc).isoformat(),
            hardware='NOT_RUN_OFF_CHARGING',actual_user_flow='NOT_A_SUBSTITUTE',commands=[])
for name,command in commands:
    start=time.monotonic()
    completed=subprocess.run(command,cwd=root/'apps/twinpulse-web' if name=='ui-components' else root,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    content=completed.stdout
    (out/(name+'.log')).write_bytes(content)
    row=dict(name=name,command=command,exit_code=completed.returncode,elapsed_s=time.monotonic()-start,
        output_sha256=sha256(content).hexdigest(),log=name+'.log',passed=completed.returncode==0)
    result['commands'].append(row)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(row),flush=True)
result.update(status='PASS' if all(row['passed'] for row in result['commands']) else 'FAIL',
              ended_at=datetime.now(timezone.utc).isoformat())
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
if result['status']!='PASS':sys.exit(1)
