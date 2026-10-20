# SPDX-License-Identifier: Apache-2.0
"""Versioned local build of the shipped guard. No device access or installation.

Called only by explicit Prepare. Build/test failures never select the old
migration executable as a substitute for the configured output guard.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def verify(directory,source_files):
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('OUTPUT_GUARD_CACHE_ESCAPE')
    receipt=json.loads((directory/'receipt.json').read_text())
    if receipt.get('schema')!='output-guard-build-1.0' or receipt.get('source_files')!=source_files:
        raise ValueError('OUTPUT_GUARD_BUILD_IDENTITY')
    for name in ('build/turtlebot3_ros','build/libturtlebot3_node_lib.so'):
        path=directory/name
        if path.is_symlink() or digest(path)!=receipt['artifacts'].get(name):
            raise ValueError('OUTPUT_GUARD_BINARY_CHANGED')
    return directory/'build/turtlebot3_ros',receipt


def ensure(package,home,*,safety=lambda:None,phase=lambda value:None,runner=None):
    package=Path(package).resolve();home=Path(home)
    source_files=sources(package)
    identity=hashlib.sha256(json.dumps(source_files,sort_keys=True).encode()).hexdigest()
    cache=home/'guard-builds';cache.mkdir(parents=True,exist_ok=True)
    if cache.is_symlink():raise ValueError('OUTPUT_GUARD_CACHE_ESCAPE')
    final=cache/identity
    if final.exists():return verify(final,source_files)
    stage=cache/(identity+'.building-'+uuid4().hex);stage.mkdir()
    env=dict(os.environ,ROS_DOMAIN_ID='87',ROS_LOCALHOST_ONLY='1')
    env.pop('TWINPULSE_OUTPUT_TIMEOUT_MS',None)  # test default400; launch applies the selected value separately
    log=stage/'build.log'

    def run(command):
        safety()
        if runner is not None:return runner(command,log,env)
        with log.open('ab') as stream:
            child=subprocess.Popen(command,stdout=stream,stderr=stream,env=env,start_new_session=True)
            began=time.monotonic()
            try:
                while child.poll() is None:
                    safety()
                    if time.monotonic()-began>600:raise ValueError('OUTPUT_GUARD_BUILD_TIMEOUT')
                    time.sleep(.05)
                if child.returncode:raise ValueError('OUTPUT_GUARD_BUILD_FAILED')
            finally:
                if child.poll() is None:
                    import signal
                    os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=3)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()

    def ros(*command):
        return ['/bin/bash','-c','source /opt/ros/humble/setup.bash && exec "$@"','guard-build',*map(str,command)]
    try:
        phase('BUILDING_OUTPUT_GUARD')
        run(ros('cmake','-S',package/'guard_base','-B',stage/'build','-DCMAKE_BUILD_TYPE=Release'))
        run(ros('cmake','--build',stage/'build','--parallel','1'))
        phase('CHECKING_OUTPUT_GUARD')
        run(ros('cmake','-S',package,'-B',stage/'checks','-DBUILD_ROS_TESTS=ON'))
        run(ros('cmake','--build',stage/'checks','--parallel','1'))
        run(ros('ctest','--test-dir',stage/'checks','-R','^(command_guard|ros_guard)$','--output-on-failure'))
        if sources(package)!=source_files:raise ValueError('OUTPUT_GUARD_SOURCE_CHANGED_DURING_BUILD')
        receipt=dict(schema='output-guard-build-1.0',source_id=identity,source_files=source_files,
            artifacts={name:digest(stage/name) for name in ('build/turtlebot3_ros','build/libturtlebot3_node_lib.so')},
            tests='command_guard_and_actual_ROS_fake_SDK_not_hardware',motion_enabled=False)
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        safety()
        stage.rename(final)
        return verify(final,source_files)
    except Exception as exc:
        (stage/'failure.json').write_text(json.dumps(dict(status='FAILED_NOT_ACTIVATED',reason=type(exc).__name__+':'+str(exc))),encoding='utf-8')
        raise
