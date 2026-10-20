# SPDX-License-Identifier: Apache-2.0
"""Supplementary real test runner. No robot, model, or success-response injection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-timing-settings-20261020'


def run(item):
    name,command,cwd=item
    process=subprocess.run(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    raw=process.stdout;path=OUT/(name+'.log');path.write_bytes(raw)
    return dict(name=name,command=command,exit_code=process.returncode,status='PASS' if not process.returncode else 'FAIL',
        log=str(path),sha256=hashlib.sha256(raw).hexdigest(),scope='Supplementary no-device verification, not physical acceptance')


if __name__=='__main__':
    OUT.mkdir(exist_ok=True);py=str(ROOT/'.venv/Scripts/python.exe');web=ROOT/'apps/twinpulse-web'
    def unit(name,path,pattern):return name,[py,'-m','unittest','discover','-s',path,'-p',pattern,'-q'],ROOT
    commands=[unit('safety','packages/twinpulse_robot_safety/tests','test*.py'),
        unit('registry','tests/integration','test_robot_registry_binding.py'),unit('timing-store','tests/integration','test_robot_timing_settings.py'),
        unit('live-session','tests/integration','test_physical_live_session.py'),unit('physical-pool','tests/integration','test_physical_fleet_adapter.py'),
        unit('fleet','tests/integration','test_robot_fleet.py'),unit('object-navigation','tests/integration','test_physical_object_navigation.py'),
        unit('local-navigation','packages/twinpulse_core/tests','test_local_navigation.py'),
        unit('ros-observations','packages/twinpulse_core/tests','test_ros_observations.py'),
        ('startup-settings',[py,'-m','unittest','tests.integration.test_r5_product_api.R5ProductApiTests.test_only_data_only_robot_settings_can_save_before_isaac_is_ready','-q'],ROOT),
        ('ui',[str(web/'node_modules/.bin/vitest.cmd'),'run','src/RobotTimingSettings.test.tsx','src/RobotRegistry.test.tsx','src/RobotFleet.test.tsx','src/api.test.ts'],web),
        ('types',[str(web/'node_modules/.bin/tsc.cmd'),'-b'],web)]
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,commands))
    record=dict(at=datetime.now(timezone.utc).isoformat(),checks=results,
        cpp_compile='NOT_RUN: no C++ compiler, running WSL or Docker daemon available; no new installation performed',
        robot='NOT_RUN: no SSH, motor, sensor or robot-runtime deployment actions')
    (OUT/'supplementary.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(checks=[dict(name=r['name'],status=r['status']) for r in results],cpp=record['cpp_compile'])))
    raise SystemExit(0 if all(r['exit_code']==0 for r in results) else 1)
