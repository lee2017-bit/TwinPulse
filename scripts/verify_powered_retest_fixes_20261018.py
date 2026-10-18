# SPDX-License-Identifier: Apache-2.0
"""Run supplementary regression suites, preserving outputs; no robot connection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    out=ROOT/'outputs/robot-retest-20261018'
    suites=['packages.twinpulse_robot_safety.tests.test_residual_telemetry',
        'packages.twinpulse_robot_safety.tests.teleop_test',
        'packages.twinpulse_robot_safety.tests.test_fleet_native',
        'packages.twinpulse_robot_safety.tests.test_field_tests',
        'tests.integration.test_physical_live_session','tests.integration.test_robot_fleet']
    began=time.time()
    done=subprocess.run([sys.executable,'-m','unittest',*suites,'-v'],cwd=ROOT,capture_output=True,timeout=90)
    (out/'regressions.log').write_bytes(done.stdout+done.stderr)
    files=['packages/twinpulse_robot_safety/teleop_ros.py','packages/twinpulse_robot_safety/teleop_contract.py',
        'packages/twinpulse_robot_safety/fleet_control.py','packages/twinpulse_app/src/twinpulse_app/robot_fleet.py',
        'apps/twinpulse-web/src/RobotFleet.tsx']
    result=dict(scope='SUPPLEMENTARY_DEVICE_FREE_NOT_USER_ACCEPTANCE',suites=suites,
        returncode=done.returncode,started_utc_s=began,elapsed_s=time.time()-began,
        log_sha256=hashlib.sha256(done.stdout+done.stderr).hexdigest(),
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
        installed_package_changed=False,hardware_retest='NOT_RUN_AFTER_FIXES')
    (out/'regressions.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(done.stderr.decode('utf-8',errors='replace')[-1800:]);print(json.dumps(result,indent=2))
    raise SystemExit(done.returncode)
