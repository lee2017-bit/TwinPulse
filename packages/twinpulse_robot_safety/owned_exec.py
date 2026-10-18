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
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in {'base', 'observe', 'read-board', 'torque-off'}:
        return 2
    role, expected_parent = sys.argv[1], int(sys.argv[2])
    if (role in {'base', 'read-board', 'torque-off'} and len(sys.argv) != 3) or (role == 'observe' and len(sys.argv) != 4):
        return 2
    # PR_SET_PDEATHSIG survives exec. Check after setting it to close the fork race.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != expected_parent:
        return 2
    root = Path(__file__).resolve().parent
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
