# SPDX-License-Identifier: Apache-2.0
"""Read-only installed-policy checks; no UI/Isaac, model or robot execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-task-clearance-20261025-01'
parser=argparse.ArgumentParser()
parser.add_argument('--attempt',default='01')
args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_package import verify_package

installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
active=read(installed/'active-release.json')
release=installed/Path(active['exe']).parent
package=verify_package(release)
resources=release/'_internal/resources'
manifest=read(resources/'source-manifest.json')
# Match the builder's explicit testing-runtime destination to its actual npm
# source; it is not a same-named repository folder. Do not skip those members.
runtime_path=json.loads(subprocess.check_output(['node','-e',
    "const p=require.resolve('playwright/package.json',{paths:[require.resolve('@playwright/test')]});console.log(JSON.stringify(require.resolve('playwright-core/package.json',{paths:[p]})))"],
    cwd=ROOT/'apps/twinpulse-web',text=True))
runtime_root=Path(runtime_path).parent
if read(Path(runtime_path))['version']!='1.63.0':raise ValueError('TEST_RUNTIME_VERSION_MISMATCH')
prefix='apps/twinpulse-desktop/testing/playwright-core/'
def source_path(name):return runtime_root/name[len(prefix):] if name.startswith(prefix) else ROOT/name
mismatches=[name for name,digest in manifest.items() if not source_path(name).is_file() or sha(source_path(name))!=digest]
source_match=not mismatches
probe=r'''
import sys,json
from pathlib import Path
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(Path(sys.argv[1])/'packages'/name/'src'))
from twinpulse_core.robot_survey import MIN_CLEARANCE_M,PLANNING_CLEARANCE_M,checked_motion_segment,route_to
from twinpulse_core.sim_fleet_navigation import approach_plan
from twinpulse_app.robot_task_service import RobotTaskService
def rejects(fn):
    try:fn()
    except ValueError:return True
    return False
g=dict(bounds=[0,0,3,3],obstacles=[[1.4,1.,1.6,1.2]])
t=dict(id='bed',kind='bed',bounds=g['obstacles'][0])
checks=dict(envelope_15cm=MIN_CLEARANCE_M==.15,planning_17cm=abs(PLANNING_CLEARANCE_M-.17)<1e-12,
    below_15cm_blocked=rejects(lambda:checked_motion_segment([1.,.851,0],'forward',1.,g)),
    above_15cm_clear=checked_motion_segment([1.,.849,0],'forward',1.,g)==[2.,.849],
    planning_margin_blocks_16cm=rejects(lambda:route_to([1.5,.84,0],[1.7,.84],g)),
    unknown_still_blocked=rejects(lambda:checked_motion_segment([1.,.6,0],'forward',.1,g,observed_cells=[])),
    task_approach_17cm=abs(approach_plan([.7,.6,0],'bed',[t],g['bounds'],g['obstacles'],clearance_m=PLANNING_CLEARANCE_M)['clearance_m']-.17)<1e-12,
    standalone_default_unchanged=approach_plan([.7,.6,0],'bed',[t],g['bounds'],g['obstacles'])['clearance_m']==.25)
print(json.dumps(dict(checks=checks,minimum_clearance_m=MIN_CLEARANCE_M,planning_clearance_m=PLANNING_CLEARANCE_M)))
sys.exit(0 if all(checks.values()) else 1)
'''
result=subprocess.run([sys.executable,'-I','-B','-c',probe,str(resources)],capture_output=True,text=True,check=True)
policy=json.loads(result.stdout)
prior=ROOT/'outputs/robot-task-20261025-01/acceptance06.json'
supplement=ROOT/'outputs/robot-task-20261025-01/focused-final05/result.json'
checks=dict(package_verified=package['status']=='verified',all_packaged_sources_match=source_match,
    regression151=read(supplement)['status']=='PASS' and read(supplement)['tests']==151,
    prior_30cm_gate_unchanged=sha(prior)=='4af379da23c8d81d30b07fb034a70756111d465146ef083209acbf3e457b8006',
    **policy['checks'])
value=dict(scope='INSTALLED_POLICY_AND_SUPPLEMENTARY_TESTS_NOT_UI_ISAAC_OR_PHYSICAL_ACCEPTANCE',
    status='PASS' if all(checks.values()) else 'FAIL',checks=checks,package=package,
    minimum_clearance_m=policy['minimum_clearance_m'],planning_clearance_m=policy['planning_clearance_m'],
    distance_basis='MAP_ROBOT_REFERENCE_POINT_NOT_MEASURED_BODY_CLEARANCE',
    source_mismatches=mismatches,remapped_testing_runtime_members=sum(name.startswith(prefix) for name in manifest),
    regression=dict(path=str(supplement.relative_to(ROOT)),sha256=sha(supplement)),
    physical_task_ready=False,ui_isaac_revalidation='NOT_RUN',model_calls=0,physical_actions=0)
with (OUT/('verification'+args.attempt+'.json')).open('x',encoding='utf-8') as stream:
    json.dump(value,stream,indent=2)
print(json.dumps(value))
sys.exit(0 if all(checks.values()) else 1)
