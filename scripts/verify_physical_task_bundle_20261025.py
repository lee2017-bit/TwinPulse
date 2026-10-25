# SPDX-License-Identifier: Apache-2.0
"""Exercise the real bundle receiver in an isolated local home, never devices."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.physical_live_session import reviewed_bundle,BOOTSTRAP
parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--output-root',type=Path);args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
out=(args.output_root or ROOT/'outputs/physical-task-preparation-20261025-01')/('bundle'+args.attempt);out.mkdir(parents=True,exist_ok=False)
bundle,wire,manifest=reviewed_bundle(ROOT)
wrapper=r'''
import pathlib,runpy,sys,json,hashlib,importlib.abc
home=pathlib.Path(sys.argv[1]);home.mkdir()
pathlib.Path.home=classmethod(lambda cls:home)
original=runpy.run_path
class NoDeviceImports(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path,target=None):
        if fullname.split('.')[0] in {'rclpy','serial','paramiko'}:raise RuntimeError('DEVICE_IMPORT_FORBIDDEN:'+fullname)
sys.meta_path.insert(0,NoDeviceImports())
def inspect(path,run_name=None):
    namespace=original(path,run_name='__received_source_import_only__')
    from twinpulse_core.physical_task_observation import StationaryTaskCollector,wheel_se2
    assert 'FleetWorker' in namespace
    release=pathlib.Path(path).parent
    files={p.relative_to(release).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in release.rglob('*') if p.is_file()}
    print(json.dumps(dict(status='RECEIVED_AND_IMPORTED_BEFORE_DEVICE_ACCESS',files=files,release=str(release))))
runpy.run_path=inspect
exec(sys.argv[2])
'''
proc=subprocess.run([sys.executable,'-I','-B','-c',wrapper,str(out/'isolated-home'),BOOTSTRAP],input=wire,capture_output=True,timeout=30)
(out/'stdout.txt').write_bytes(proc.stdout);(out/'stderr.txt').write_bytes(proc.stderr)
received=json.loads(proc.stdout) if proc.returncode==0 else {}
value=dict(scope='REAL_RECEIVER_LOCAL_ISOLATED_SOURCE_IMPORT_ONLY_NOT_ROBOT_RUNTIME_OR_ROS_BUILD',
    status='PASS' if proc.returncode==0 and received.get('files')==manifest else 'FAIL',bundle_sha256=bundle,members=len(manifest),
    return_code=proc.returncode,receiver=received,device_access=False,physical_actions=0,new_sdk=False,
    required_new_members_present=all(n in manifest for n in ('twinpulse_core/physical_task_observation.py','physical_task_observation.py')))
(out/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in value.items() if k!='receiver'}))
sys.exit(0 if value['status']=='PASS' and value['required_new_members_present'] else 1)
