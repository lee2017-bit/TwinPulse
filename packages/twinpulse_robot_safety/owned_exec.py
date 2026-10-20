# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Linux parent-death binding for the two fixed stationary process roles."""
import ctypes
import os
from pathlib import Path
import signal
import sys


def main():
    if len(sys.argv) not in (3, 4, 5) or sys.argv[1] not in {'base', 'reviewed-base', 'observe', 'read-board', 'torque-off'}:
        return 2
    role, expected_parent = sys.argv[1], int(sys.argv[2])
    if (role in {'base', 'read-board', 'torque-off'} and len(sys.argv) != 3) or (role == 'observe' and len(sys.argv) != 4):
        return 2
    if role=='reviewed-base' and len(sys.argv)!=5:return 2
    # PR_SET_PDEATHSIG survives exec. Check after setting it to close the fork race.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != expected_parent:
        return 2
    root = Path(__file__).resolve().parent
    if role=='reviewed-base':
        import json
        import re
        from runtime import HOME,verify_release
        from guard_runtime import verify,sources
        release=Path(sys.argv[3]).resolve(strict=True);identity=sys.argv[4]
        if not re.fullmatch('[a-f0-9]{64}',identity) or release!=(HOME/'current').resolve(strict=True):return 2
        verify_release(release)
        binary,_=verify(HOME/'guard-builds'/identity,sources(root))
        profile=json.loads((release/'profile.json').read_text())
        os.execv('/bin/bash',['bash','-c','source /opt/ros/humble/setup.bash && exec "$@"','guard-base',str(binary),
            '-i',profile['device'],'--ros-args','--params-file',str(release/'burger.yaml'),
            '-r','__ns:=/tp_guard_stationary','-p','namespace:=""'])
    if role == 'torque-off':
        helper = str(root / 'bin/opencr_torque_off')
        os.execv(helper, [helper, '--disable-torque'])
    if role == 'read-board':
        helper = str(root / 'bin/opencr_readonly')
        os.execv(helper, [helper])
    script = str(root / 'stationary.sh')
    os.execv('/bin/bash', ['bash', script, role, *sys.argv[3:]])


if __name__ == '__main__':
    raise SystemExit(main())
