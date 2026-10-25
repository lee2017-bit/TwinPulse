# SPDX-License-Identifier: Apache-2.0
"""Read-only final package/source and fresh isolated App/Core import checks."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physical-task-preparation-20261025-01'
parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--output-root',type=Path);parser.add_argument('--bundle',default='bundle02');parser.add_argument('--tests',default='tests07');parser.add_argument('--expected-tests',type=int,default=203);args=parser.parse_args()
if args.output_root:OUT=args.output_root
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
for p in ('twinpulse_core','twinpulse_provider','twinpulse_app'):sys.path.insert(0,str(ROOT/'packages'/p/'src'))
from twinpulse_app.windows_package import verify_package
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
installed=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed';active=read(installed/'active-release.json')
release=installed/Path(active['exe']).parent;package=verify_package(release);resources=release/'_internal/resources'
manifest=read(resources/'source-manifest.json')
runtime_path=json.loads(subprocess.check_output(['node','-e',"const p=require.resolve('playwright/package.json',{paths:[require.resolve('@playwright/test')]});console.log(JSON.stringify(require.resolve('playwright-core/package.json',{paths:[p]})))"],cwd=ROOT/'apps/twinpulse-web',text=True))
runtime_root=Path(runtime_path).parent;prefix='apps/twinpulse-desktop/testing/playwright-core/'
def original(n):return runtime_root/n[len(prefix):] if n.startswith(prefix) else ROOT/n
mismatches=[n for n,h in manifest.items() if not original(n).is_file() or sha(original(n))!=h]
probe=r'''
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for p in ('twinpulse_core','twinpulse_provider','twinpulse_app'):sys.path.insert(0,str(root/'packages'/p/'src'))
from twinpulse_app.physical_task_map import PhysicalTaskMap
from twinpulse_app.robot_task_service import RobotTaskService
from twinpulse_app.physical_live_session import reviewed_bundle
from twinpulse_app.physical_live_history import checked_worker_sources
from twinpulse_core.robot_survey import task_clearance
from twinpulse_core.physical_task_observation import StationaryTaskCollector
from twinpulse_app.environment_survey_review import EnvironmentSurveyReview
from twinpulse_app.environment_survey_binding import checked_survey_binding
from twinpulse_app.task_collection import TaskCollection
from twinpulse_core.environment_survey import review_collection
from twinpulse_core.registered_navigation import intersect_model_free
from twinpulse_app.release_contract import DATA_CONTRACT
assert 'environment-survey-binding-1.0' in DATA_CONTRACT['read_capabilities']
bundle,wire,members=reviewed_bundle(root)
assert checked_worker_sources(members,bundle)==members
assert abs(task_clearance('sim')-.2075)<1e-12 and abs(task_clearance('sim',planning=True)-.2275)<1e-12
assert task_clearance('physical')==.15 and abs(task_clearance('physical',planning=True)-.17)<1e-12
assert all('twinpulse_robot_safety' not in p for p in sys.path)
print(json.dumps(dict(bundle_sha256=bundle,members=len(members),history_complete_manifest=True,isolated_app_import=True)))
'''
result=subprocess.run([sys.executable,'-I','-B','-c',probe,str(resources)],capture_output=True,text=True,timeout=30)
data=json.loads(result.stdout) if result.returncode==0 else {}
bundle=read(OUT/args.bundle/'result.json')
checks=dict(package_verified=package['status']=='verified',all_packaged_sources_match=not mismatches,
    isolated_installed_app_import=result.returncode==0,receiver_manifest_matches_installed=data.get('bundle_sha256')==bundle['bundle_sha256'] and data.get('members')==bundle['members'],
    history_validator_complete_manifest=data.get('history_complete_manifest') is True,final_tests=read(OUT/args.tests/'result.json')['status']=='PASS' and read(OUT/args.tests/'result.json')['tests']==args.expected_tests)
value=dict(status='PASS' if all(checks.values()) else 'FAIL',scope='FINAL_INSTALLED_SOURCE_IMPORT_NOT_UI_OR_HARDWARE',checks=checks,
    package=package,source_mismatches=mismatches,remapped_testing_runtime_members=sum(n.startswith(prefix) for n in manifest),
    isolated_probe=data,probe_stderr=result.stderr,physical_actions=0,model_calls=0)
with (OUT/('installed'+args.attempt+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps(value));sys.exit(0 if value['status']=='PASS' else 1)
