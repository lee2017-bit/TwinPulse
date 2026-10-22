# SPDX-License-Identifier: Apache-2.0
"""Versioned local build of the shipped guard. No device access or installation.

Called only by explicit Prepare. Build/test failures never select the old
migration executable as a substitute for the configured output guard.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback
from uuid import uuid4


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


ARTIFACTS=('build/turtlebot3_ros','build/libturtlebot3_node_lib.so')


def checked_cache_path(path,home):
    path=Path(path);root=Path(home)/'guard-builds'
    if not path.absolute().is_relative_to(root.absolute()):raise ValueError('OUTPUT_GUARD_CACHE_ESCAPE')
    for member in (path,*path.parents):
        if member.is_symlink():raise ValueError('OUTPUT_GUARD_CACHE_ESCAPE')
        if member==Path(home):break
    return path


def write_record(path,value,home):
    """An interrupted receipt update preserves the previous complete JSON."""
    path=checked_cache_path(path,home)
    temporary=path.with_name(path.name+'.tmp-'+uuid4().hex)
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    checked_cache_path(path,home)
    temporary.replace(path)


def artifact_hashes(directory):
    """Reject the wrong CMake output contract with a bounded public reason."""
    directory=Path(directory)
    result={}
    for name in ARTIFACTS:
        path=directory/name
        if path.is_symlink() or path.parent.is_symlink():raise ValueError('OUTPUT_GUARD_BINARY_CHANGED')
        if not path.is_file():
            exc=ValueError('OUTPUT_GUARD_ARTIFACT_MISSING')
            exc.filename=str(path)
            raise exc
        result[name]=digest(path)
    return result


def sources(package):
    package=Path(package).resolve()
    paths=[*sorted((package/'guard_base').rglob('*')),
        package/'include/twinpulse_robot_safety/command_guard.hpp',
        package/'include/twinpulse_robot_safety/ros_guard.hpp',package/'guard_runtime.py',
        package/'CMakeLists.txt',package/'tests/command_guard_test.cpp',
        package/'tests/torque_off_test.cpp',package/'tests/ros_guard_test.cpp',
        package/'tests/fake_include/turtlebot3_node/dynamixel_sdk_wrapper.hpp']
    result={}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(package):
            raise ValueError('OUTPUT_GUARD_SOURCE_ESCAPE')
        if path.is_file():result[path.relative_to(package).as_posix()]=digest(path)
    if not {'guard_base/CMakeLists.txt','guard_base/LICENSE','guard_base/NOTICE'}.issubset(result):
        raise ValueError('OUTPUT_GUARD_SOURCE_MISSING')
    return result


def verify(directory,source_files,*,loader_required=True):
    directory=Path(directory)
    checked_cache_path(directory,directory.parent.parent)
    receipt_path=checked_cache_path(directory/'receipt.json',directory.parent.parent)
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('schema')!='output-guard-build-1.1' or receipt.get('source_files')!=source_files:
        raise ValueError('OUTPUT_GUARD_BUILD_IDENTITY')
    identity=hashlib.sha256(json.dumps(source_files,sort_keys=True).encode()).hexdigest()
    if receipt.get('source_id')!=identity or directory.name!=identity:
        raise ValueError('OUTPUT_GUARD_BUILD_IDENTITY')
    for name,value in artifact_hashes(directory).items():
        if value!=receipt['artifacts'].get(name):
            raise ValueError('OUTPUT_GUARD_BINARY_CHANGED')
    loader=receipt.get('loader_check')
    if loader_required and (not isinstance(loader,dict) or loader.get('status')!='PASS'
            or loader.get('argument')!='-h' or loader.get('ld_bind_now') is not True
            or loader.get('artifacts')!=receipt['artifacts']):
        raise ValueError('OUTPUT_GUARD_LOADER_NOT_VERIFIED')
    return directory/'build/turtlebot3_ros',receipt


def failure_detail(exc,package,home):
    """Fixed error metadata only: no locals, environment or arbitrary prose."""
    text=str(exc)
    detail=dict(exception_type=type(exc).__name__,
        code=text if re.fullmatch('[A-Z0-9_]{1,120}',text) else type(exc).__name__)
    if isinstance(getattr(exc,'errno',None),int):detail['errno']=exc.errno
    filename=getattr(exc,'filename',None)
    if filename is not None:
        path=Path(filename)
        detail['filename']=path.name[:256]
        for label,root in (('shipped_source',package),('robot_home',home)):
            try:relative=path.absolute().relative_to(root.absolute())
            except ValueError:continue
            detail['filename']=relative.as_posix()[:1024];detail['filename_root']=label;break
    detail['frames']=[dict(file=Path(frame.filename).name,line=frame.lineno,function=frame.name)
        for frame in traceback.extract_tb(exc.__traceback__)[-8:]]
    return detail


def ensure(package,home,*,safety=lambda:None,phase=lambda value:None,runner=None,
           diagnostic=lambda record,log:None):
    package=Path(package).resolve();home=Path(home)
    attempt=uuid4().hex
    report=dict(schema='output-guard-diagnostic-1.0',attempt_id=attempt,source_id=None,
        status='RUNNING',active_step='IDENTIFY_SOURCE',cache_hit=False,steps=[],motion_enabled=False)
    location=None;log=None
    env=dict(os.environ,ROS_DOMAIN_ID='87',ROS_LOCALHOST_ONLY='1')
    env.pop('TWINPULSE_OUTPUT_TIMEOUT_MS',None)  # test default400; launch applies the selected value separately

    def notify():
        try:diagnostic(json.loads(json.dumps(report)),log)
        except Exception as exc:
            # Diagnostic failure must never replace the build's original error.
            report['diagnostic_delivery_error']=type(exc).__name__

    def run(step,command,*,extra_env=None,timeout=600):
        report['active_step']=step
        row=dict(step=step,argv=list(map(str,command)),status='RUNNING',exit_code=None)
        report['steps'].append(row);notify()
        began=time.monotonic();child=None
        try:
            safety()
            checked_cache_path(log,home)
            run_env=dict(env,**(extra_env or {}))
            if runner is not None:
                code=runner(command,log,run_env)
                row['exit_code']=0 if code is None else code
            else:
                with log.open('ab') as stream:
                    child=subprocess.Popen(command,stdout=stream,stderr=stream,env=run_env,start_new_session=True)
                    while child.poll() is None:
                        safety()
                        if time.monotonic()-began>timeout:
                            raise ValueError('OUTPUT_GUARD_LOADER_TIMEOUT' if step=='LOAD_FINAL_BINARY' else 'OUTPUT_GUARD_BUILD_TIMEOUT')
                        time.sleep(.05)
                    row['exit_code']=child.returncode
            if row['exit_code']:
                raise ValueError('OUTPUT_GUARD_LOADER_FAILED' if step=='LOAD_FINAL_BINARY' else 'OUTPUT_GUARD_BUILD_FAILED')
            row['status']='PASS'
        except Exception as exc:
            row['status']='FAILED';row['error']=failure_detail(exc,package,home)
            if isinstance(exc,subprocess.CalledProcessError):row['exit_code']=exc.returncode
            raise
        finally:
            try:
                if child is not None and child.poll() is None:
                    import signal
                    try:os.killpg(child.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(child.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        child.wait(timeout=3)
                    row['exit_code']=child.returncode
                row['child_reaped']=child is None or child.poll() is not None
            except Exception as cleanup_error:
                row['child_reaped']=False
                row['cleanup_error']=failure_detail(cleanup_error,package,home)
                # The original Stop/timeout/build exception continues unwinding.
                if row['status']=='PASS':
                    row['status']='FAILED'
                    raise ValueError('OUTPUT_GUARD_BUILD_CLEANUP_FAILED') from cleanup_error
            row['elapsed_s']=time.monotonic()-began
            notify()

    def ros(*command):
        return ['/bin/bash','-c','source /opt/ros/humble/setup.bash && exec "$@"','guard-build',*map(str,command)]
    try:
        source_files=sources(package)
        identity=hashlib.sha256(json.dumps(source_files,sort_keys=True).encode()).hexdigest()
        report['source_id']=identity
        cache=checked_cache_path(home/'guard-builds',home);cache.mkdir(parents=True,exist_ok=True)
        final=cache/identity
        if final.exists():
            report['cache_hit']=True;location=final;log=final/'build.log'
            report['active_step']='VERIFY_CACHE'
            binary,receipt=verify(final,source_files,loader_required=False)
        else:
            location=cache/(identity+'.building-'+attempt);location.mkdir()
            log=location/'build.log'
            phase('BUILDING_OUTPUT_GUARD')
            run('CONFIGURE_GUARD',ros('cmake','-S',package/'guard_base','-B',location/'build','-DCMAKE_BUILD_TYPE=Release'))
            run('BUILD_GUARD',ros('cmake','--build',location/'build','--parallel','1'))
            report['active_step']='VERIFY_BUILD_ARTIFACTS'
            artifact_hashes(location)
            phase('CHECKING_OUTPUT_GUARD')
            run('CONFIGURE_CHECKS',ros('cmake','-S',package,'-B',location/'checks','-DBUILD_ROS_TESTS=ON'))
            run('BUILD_CHECKS',ros('cmake','--build',location/'checks','--parallel','1'))
            run('RUN_CHECKS',ros('ctest','--test-dir',location/'checks','-R','^(command_guard|ros_guard)$','--output-on-failure'))
            if sources(package)!=source_files:raise ValueError('OUTPUT_GUARD_SOURCE_CHANGED_DURING_BUILD')
            receipt=dict(schema='output-guard-build-1.1',source_id=identity,source_files=source_files,
                artifacts=artifact_hashes(location),loader_check=None,
                tests='command_guard_and_actual_ROS_fake_SDK_not_hardware',motion_enabled=False)
            report['active_step']='WRITE_BUILD_RECEIPT'
            write_record(location/'receipt.json',receipt,home)
            safety()
            report['active_step']='FINALIZE_BUILD'
            location.rename(final);location=final;log=final/'build.log'
            binary,receipt=verify(final,source_files,loader_required=False)
        # -h exits before ROS init and before constructing a device. Exercise the
        # real ELF and its sibling .so from their final location, even on reuse.
        phase('CHECKING_OUTPUT_GUARD_LOADER')
        receipt['loader_check']=None
        report['active_step']='INVALIDATE_LOADER_RECEIPT'
        write_record(final/'receipt.json',receipt,home)
        library=str(binary.parent)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        run('LOAD_FINAL_BINARY',ros(binary,'-h'),extra_env=dict(LD_BIND_NOW='1',LD_LIBRARY_PATH=library),timeout=10)
        if sources(package)!=source_files:raise ValueError('OUTPUT_GUARD_SOURCE_CHANGED_DURING_BUILD')
        if artifact_hashes(final)!=receipt['artifacts']:raise ValueError('OUTPUT_GUARD_BINARY_CHANGED')
        receipt['loader_check']=dict(status='PASS',argument='-h',ld_bind_now=True,
            artifacts=receipt['artifacts'],scope='HELP_BEFORE_ROS_INIT_AND_DEVICE_ACCESS',attempt_id=attempt)
        report['active_step']='WRITE_LOADER_RECEIPT'
        write_record(final/'receipt.json',receipt,home)
        safety()
        report['active_step']='VERIFY_FINAL_RECEIPT'
        result=verify(final,source_files)
        report['status']='VERIFIED_NOT_RUNNING';notify()
        return result
    except Exception as exc:
        report.update(status='FAILED_NOT_ACTIVATED',error=failure_detail(exc,package,home))
        if location is not None:
            try:
                write_record(location/'failure.json',report,home)
            except Exception as diagnostic_error:report['failure_record_error']=type(diagnostic_error).__name__
        notify()
        raise
