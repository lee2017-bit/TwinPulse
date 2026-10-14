# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit one-shot maintenance wrapper; never called by prepare/check/startup."""
import argparse
import importlib.util
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operator-confirmed-flat-clear-floor', action='store_true', required=True)
    parser.parse_args()
    release = Path('/home/twinpulse/.local/share/twinpulse/robot/current').resolve(strict=True)
    spec = importlib.util.spec_from_file_location('runtime', release / 'runtime.py')
    runtime = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(release))
    spec.loader.exec_module(runtime)
    runtime.verify_release(release)
    here = Path(__file__).resolve().parent
    with runtime.ownership() as lease:
        runtime.idle_port()
        # Exclusive one-shot marker; never delete/reuse it to retry a failure.
        with (here / 'consumed').open('x') as marker:
            marker.write('Operator-approved torque OFF only; not motion permission.\n')
        try:
            runtime.run_logged([str(here / 'torque_off'), '--disable-torque'],
                               here / 'operation.log', timeout=8, pass_fds=(lease.fileno(),))
        finally:
            runtime.read_board(release, here / 'independent-board.log', lease.fileno())
    print('One-shot finished; inspect operation.log and independent-board.log.')


if __name__ == '__main__':
    main()
