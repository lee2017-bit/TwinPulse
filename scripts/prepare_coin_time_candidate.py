# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local-only source preparation, not a build, install or robot deployment.

Exports the pinned local Git object into a NEW output, applies the reviewed
parser/lifecycle/stop/timing patches and copies the compile-time test harness.
No checkout/reset modifies the preserved source or canonical dirty repository.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import shutil
import os
import re

ROOT=Path(__file__).resolve().parents[1]
PIN='8277b288902f28b37948b42e1bb80ba59afbba60'
PATCHES=('coin-d4-parser-bounds-20260926.patch','coin-d4-lifecycle-20260930.patch',
         'coin-d4-stop-order-20260930.patch','coin-d4-time-order-20261004.patch',
         'coin-d4-humble-time-api-20261006.patch')

def prepare(source,output):
    source=Path(source).resolve(strict=True);output=Path(output).absolute()
    if output.exists() or output.is_symlink() or output.parent.resolve()!=output.parent:
        raise ValueError('NEW_CANONICAL_CANDIDATE_DIRECTORY_REQUIRED')
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=PIN:
        raise ValueError('COIN_SOURCE_PIN_MISMATCH')
    archive=subprocess.check_output(['git','-C',str(source),'archive','--format=tar',PIN])
    if len(archive)>32*1024*1024:raise ValueError('COIN_SOURCE_BUDGET')
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members=tar.getmembers()
        if any(m.issym() or m.islnk() or not (output/m.name).resolve().is_relative_to(output)
               for m in members):raise ValueError('COIN_SOURCE_ARCHIVE_PATH')
        output.mkdir()
        tar.extractall(output,filter='data')
    patches={}
    # This output lives beneath the desktop repository. Without a ceiling,
    # git discovers that ancestor and may silently skip all relative paths as
    # outside its current prefix, returning zero for a patch that did nothing.
    environment = dict(os.environ)
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
        environment.pop(name, None)
    environment['GIT_CEILING_DIRECTORIES'] = output.parent.as_posix()
    discovered = subprocess.run(['git', '-C', str(output), 'rev-parse', '--show-toplevel'],
                                env=environment, capture_output=True, check=False)
    if discovered.returncode == 0:
        raise ValueError('COIN_PATCH_ANCESTOR_REPOSITORY_DISCOVERED')
    for name in PATCHES:
        path=ROOT/'docs/verification'/name
        paths = re.findall(r'^diff --git a/([A-Za-z0-9_./-]+) b/\1$',
                           path.read_text(encoding='utf-8'), re.MULTILINE)
        if not paths or any(not (output/member).resolve().is_relative_to(output) for member in paths):
            raise ValueError('COIN_PATCH_PATH_SET')
        def states():
            return {member: hashlib.sha256((output/member).read_bytes()).hexdigest()
                    if (output/member).is_file() else None for member in paths}
        before = states()
        subprocess.run(['git','-C',str(output),'apply','--check','--unidiff-zero',str(path)],
                       env=environment,check=True)
        subprocess.run(['git','-C',str(output),'apply','--unidiff-zero',str(path)],
                       env=environment,check=True)
        if any(before[member] == states()[member] for member in paths):
            raise ValueError('COIN_PATCH_DID_NOT_CHANGE_ALL_MEMBERS:' + name)
        subprocess.run(['git','-C',str(output),'apply','--reverse','--check','--unidiff-zero',str(path)],
                       env=environment,check=True)
        patches[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (output/'offline_tests').mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'packages/twinpulse_robot_safety/tests/scan_clock_test.cpp',
                    output/'offline_tests/scan_clock_test.cpp')
    result={'schema':'coin-timing-candidate-1.0','upstream_commit':PIN,'patches':patches,
            'status':'SOURCE_PREPARED','target_build':'TARGET_BUILD_NOT_RUN',
            'timing_basis':'HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY',
            'deployed':False,'motion_authorized':False,
            'patch_application':'ISOLATED_NON_REPOSITORY_CHANGED_FILES_AND_REVERSE_CHECK',
            'source_files':{p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in output.rglob('*') if p.is_file()}}
    with (output/'twinpulse-candidate.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.source,args.output),indent=2))
