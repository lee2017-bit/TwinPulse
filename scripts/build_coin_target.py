# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit isolated ARM64 build only; never launch a driver or switch a release."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

from robot_field_candidate import sensor_target, sha, safe_path, MAX_ARCHIVE

ROOT = Path(__file__).resolve().parents[1]
PARENT = '/home/twinpulse/.local/share/twinpulse/robot/candidates'
REMOTE = r'''
import hashlib,json,os,platform,signal,subprocess,sys,tarfile,time
from pathlib import Path,PurePosixPath
base=Path(sys.argv[1]); expected=sys.argv[2]
parent=Path('/home/twinpulse/.local/share/twinpulse/robot/candidates')
if base.parent!=parent or not base.name.startswith('coin-time-build-'):
    raise ValueError('BUILD_PATH_REJECTED')
if any(p.is_symlink() for p in (base,*base.parents)):
    raise ValueError('BUILD_PATH_SYMLINK')
report={'schema':'coin-target-build-1.0','status':'BUILD_RUNNING','stages':[],
        'sensor_started':False,'motor_command_sent':False,'release_selected':False,
        'timing_basis':'HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY'}
def save():
    with (base/'report.json').open('w') as f:
        json.dump(report,f,indent=2); f.flush(); os.fsync(f.fileno())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():
    old=parent/'coin-d4-5fdc-9c25-20260930/install/coin_d4_driver/lib'
    current=parent.parent/'current'
    return {'current':os.readlink(current),
            'binary':digest(old/'coin_d4_driver/single_coin_d4_node'),
            'library':digest(old/'libcoin_d4_driver_lib.so')}
def stage(name,args,timeout=120):
    item={'name':name,'command':args,'status':'RUNNING'}
    report['stages'].append(item); save(); print('STAGE '+name,flush=True)
    started=time.monotonic()
    with (base/(name+'.stdout')).open('wb') as out,(base/(name+'.stderr')).open('wb') as err:
        p=subprocess.Popen(args,cwd=base,stdout=out,stderr=err,start_new_session=True)
        try:code=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL); p.wait()
            code=-1; item['timeout']=True
    item.update(exit_code=code,seconds=round(time.monotonic()-started,3),
                status='PASS' if code==0 else 'FAILED')
    save()
    if code:raise RuntimeError('BUILD_STAGE_FAILED:'+name)
def ros(args):return ['bash','-c','source /opt/ros/humble/setup.bash && exec "$@"','coin-build',*args]
try:
    report['before']=snapshot(); report['architecture']=platform.machine()
    report['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if report['architecture']!='aarch64':raise ValueError('TARGET_ARCHITECTURE')
    archive=base/'sensor-target.tar'
    if digest(archive)!=expected:raise ValueError('ARCHIVE_SHA_MISMATCH')
    source=base/'source'; source.mkdir()
    with tarfile.open(archive) as tar:
        entries=tar.getmembers(); names=set()
        if len(entries)>512 or sum(x.size for x in entries)>32*1024*1024:raise ValueError('ARCHIVE_BUDGET')
        for item in entries:
            path=PurePosixPath(item.name)
            if not item.isfile() or path.is_absolute() or '..' in path.parts or item.name in names:
                raise ValueError('ARCHIVE_MEMBER_REJECTED')
            names.add(item.name)
        for item in entries:
            dest=source/item.name; dest.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(item) as stream:dest.write_bytes(stream.read())
    receipt=json.loads((source/'twinpulse-candidate.json').read_bytes())
    actual={p.relative_to(source).as_posix():digest(p) for p in source.rglob('*')
            if p.is_file() and p.name!='twinpulse-candidate.json'}
    wanted={k:v for k,v in receipt['source_files'].items() if '.github' not in k.split('/')}
    if actual!=wanted:raise ValueError('EXTRACTED_SOURCE_MISMATCH')
    report['archive_sha256']=expected; report['source_files']=actual
    stage('clock_compile',['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(source/'include'),
          str(source/'offline_tests/scan_clock_test.cpp'),'-o',str(base/'scan_clock_test')])
    stage('clock_test',[str(base/'scan_clock_test')],10)
    stage('configure',ros(['cmake','-S',str(source),'-B',str(base/'build'),
          '-DCMAKE_INSTALL_PREFIX='+str(base/'install')]))
    stage('driver_build',ros(['cmake','--build',str(base/'build'),'--parallel','1']),900)
    artifacts=['single_coin_d4_node','multi_coin_d4_node','libcoin_d4_driver_lib.so']
    report['artifacts']={name:{'path':str(base/'build'/name),'sha256':digest(base/'build'/name)} for name in artifacts}
    stage('elf_headers',['readelf','-h',*[str(base/'build'/name) for name in artifacts]],30)
    report['status']='TARGET_BUILD_PASS_NOT_ACTIVATED'
except Exception as e:
    report.update(status='TARGET_BUILD_FAILED',reason=type(e).__name__+': '+str(e))
finally:
    try:
        report['after']=snapshot(); report['existing_state_unchanged']=report.get('before')==report['after']
        if not report['existing_state_unchanged']:report['status']='EXISTING_STATE_CHANGED'
    except Exception as e:report.update(status='PRESERVATION_CHECK_FAILED',preservation_error=str(e))
    save(); print(json.dumps({'status':report['status'],'report':str(base/'report.json')}),flush=True)
sys.exit(0 if report['status']=='TARGET_BUILD_PASS_NOT_ACTIVATED' else 1)
'''


def reviewed_archive(path, root=ROOT):
    path = safe_path(path)
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('FROZEN_ARCHIVE_BUDGET')
    expected = sensor_target(root)
    if expected['status'] not in ('CORRECTED_DRIVER_SOURCE_FROZEN_NOT_BUILT',
                                  'CORRECTED_DRIVER_SOURCE_FROZEN_BUILD_VERIFIED_NOT_ACTIVATED'):
        raise ValueError('CORRECTED_SOURCE_NOT_AVAILABLE')
    with tarfile.open(path) as tar:
        entries = tar.getmembers()
        if (any(not entry.isfile() for entry in entries) or len(entries) != expected['members']
                or len({e.name for e in entries}) != len(entries)):
            raise ValueError('FROZEN_ARCHIVE_MEMBERS')
        members = {e.name: sha(tar.extractfile(e).read()) for e in entries}
    identity = sha(json.dumps(members, sort_keys=True).encode())
    if identity != expected['source_sha256']:
        raise ValueError('FROZEN_SENSOR_ARCHIVE_CHANGED')
    return sha(path.read_bytes()), expected


def verify_export(directory, digest):
    report=json.loads((directory/'report.json').read_bytes())
    if report['status'] != 'TARGET_BUILD_PASS_NOT_ACTIVATED':
        return report  # Preserve the exact remote compiler/receipt failure.
    if report.get('archive_sha256') != digest or sha((directory/'sensor-target.tar').read_bytes()) != digest:
        raise ValueError('TARGET_ARCHIVE_RECEIPT_MISMATCH')
    if (report.get('existing_state_unchanged') is not True
            or report.get('before') != report.get('after')
            or report.get('architecture') != 'aarch64'
            or any(report.get(key) is not False for key in ('sensor_started','motor_command_sent','release_selected'))):
        raise ValueError('TARGET_BUILD_SCOPE_OR_PRESERVATION')
    artifacts=report.get('artifacts',{})
    if set(artifacts) != {'single_coin_d4_node','multi_coin_d4_node','libcoin_d4_driver_lib.so'}:
        raise ValueError('TARGET_BINARY_SET')
    for name, artifact in artifacts.items():
        if sha((directory/'build'/name).read_bytes()) != artifact['sha256']:
            raise ValueError('EXPORTED_BINARY_SHA_MISMATCH:'+name)
    for name,value in report['source_files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('EXPORTED_SOURCE_PATH')
        if sha((directory/'source'/path).read_bytes()) != value:
            raise ValueError('EXPORTED_SOURCE_SHA_MISMATCH:'+name)
    return report


def record_verified_build(root, output):
    """Passive source-build receipt only, never an admission/profile update."""
    root=Path(root).resolve(); output=safe_path(output)
    if not output.is_relative_to(root/'artifacts/coin-target-build'):
        raise ValueError('BUILD_RECEIPT_ROOT')
    digest,source=reviewed_archive(output/'target/sensor-target.tar',root)
    result=verify_export(output/'target',digest)
    if result['status']!='TARGET_BUILD_PASS_NOT_ACTIVATED':
        raise ValueError('BUILD_RECEIPT_REQUIRES_ACTUAL_PASS')
    pointer={'schema':'coin-compiled-source-1.0','source_sha256':source['source_sha256'],
             'archive_sha256':digest,'target':(output/'target').relative_to(root).as_posix(),
             'report_sha256':sha((output/'target/report.json').read_bytes()),
             'activation_authorized':False}
    (root/'artifacts/coin-target-build/compiled-source.json').write_text(json.dumps(pointer,indent=2),encoding='utf-8')
    return pointer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Explicit approved SSH, source transfer and isolated build')
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    digest, source = reviewed_archive(args.archive)
    if not args.build:
        print(json.dumps({'status':'OFFLINE_SOURCE_VERIFIED_NO_CONTACT','sha256':digest}))
        return 0
    run = 'coin-time-build-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    output = ROOT/'artifacts/coin-target-build'/run
    output.mkdir(parents=True)
    remote = PARENT+'/'+run
    report = {'status':'RUNNING','remote':remote,'archive_sha256':digest,'source':source,
              'worker_sha256':sha(REMOTE.encode()),
              'sensor_started':False,'motor_command_sent':False,'release_selected':False,'steps':[]}
    options = ['-i',str(Path.home()/'.ssh/twinpulse-burger/id_ed25519_automation'),
               '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
               '-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',
               '-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','PermitLocalCommand=no']
    target = 'twinpulse@192.168.35.139'
    def call(name, command, input_data=None, timeout=60, required=True):
        try:
            result = subprocess.run(command,input=input_data,capture_output=True,timeout=timeout)
            code = result.returncode
            (output/(name+'.stdout')).write_bytes(result.stdout)
            (output/(name+'.stderr')).write_bytes(result.stderr)
        except subprocess.TimeoutExpired as error:
            code = -1
            (output/(name+'.stdout')).write_bytes(error.stdout or b'')
            (output/(name+'.stderr')).write_bytes(error.stderr or b'')
        report['steps'].append({'name':name,'exit_code':code})
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(name+': '+str(code),flush=True)
        if code and required:raise RuntimeError('TARGET_STEP_FAILED:'+name)
        return code
    try:
        # A new exclusive leaf only; never mkdir over a prior build or a symlink.
        setup = ('from pathlib import Path; p=Path('+repr(remote)+'); '
                 'assert not any(x.is_symlink() for x in (p,*p.parents)); p.mkdir()')
        call('new_candidate',['ssh',*options,target,'python3 -'],setup.encode())
        call('transfer_source',['scp',*options,str(args.archive),target+':'+remote+'/sensor-target.tar'])
        call('build',['ssh',*options,target,'python3 - '+remote+' '+digest],REMOTE.encode(),1100,False)
        call('export',['scp',*options,'-r',target+':'+remote,str(output/'target')],timeout=180)
        target_report=verify_export(output/'target',digest)
        report.update(status=target_report['status'],target_report=target_report)
        if report['status']=='TARGET_BUILD_PASS_NOT_ACTIVATED':
            report['compiled_source_receipt']=record_verified_build(ROOT,output)
    except Exception as error:
        report.update(status='TARGET_TRANSPORT_OR_EXPORT_FAILED',reason=type(error).__name__+': '+str(error))
    finally:
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'output':str(output)}),flush=True)
    return 0 if report['status']=='TARGET_BUILD_PASS_NOT_ACTIVATED' else 1


if __name__ == '__main__':
    sys.exit(main())
