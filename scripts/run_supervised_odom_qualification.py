# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One existing fixed stop qualification, retaining its moving ROS raw evidence.

No retries and no directional input outside the robot's built-in 0.6 s trial.
The already qualified robot-local guard and same-boot receipt remain authoritative.
"""
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/twinpulse_app/src'),
                str(ROOT / 'packages/twinpulse_core/src'),
                str(ROOT / 'packages/twinpulse_provider/src')]
from twinpulse_app.physical_controller import PhysicalController


def main():
    if sys.argv[1:]:
        raise SystemExit('No runtime overrides accepted')
    controller = PhysicalController(ROOT)
    owner = 'supervised-odom-' + uuid.uuid4().hex
    job = uuid.uuid4().hex
    sequence = 0
    qualified_input_sent = False
    last_input = 0.0
    deadline = time.monotonic() + 100
    controller.start(owner, 'qualify_scan', job, True)
    try:
        while time.monotonic() < deadline:
            state = controller.snapshot(owner)
            phase = state.get('state')
            if phase in {'FINISHED', 'FAILED', 'REJECTED', 'CONNECTION_LOST'}:
                break
            now = time.monotonic()
            if phase == 'READY' and not qualified_input_sent:
                sequence += 1
                controller.input(owner, job, sequence, 'qualify', controller.wall() + 220)
                qualified_input_sent = True
                last_input = now
            elif now - last_input >= .15:
                sequence += 1
                controller.input(owner, job, sequence, 'watch', controller.wall() + 220)
                last_input = now
            time.sleep(.025)
        else:
            state = {'state': 'LOCAL_DEADLINE', 'reason': 'Owned session did not finish'}
        if controller.thread:
            controller.thread.join(timeout=22)
        result = controller.snapshot(owner)
        # A failed copy may be retried as transfer-only after the owned robot
        # operation has ended. Never repeat the sensor or wheel trial.
        if (result.get('state') == 'FINISHED' and result.get('evidence_export') != 'COMPLETE'
                and controller.thread and not controller.thread.is_alive()):
            try:
                from twinpulse_app.robot_evidence_export import export_finished_session
                directory = ROOT / 'artifacts/manual-control' / job
                report = json.loads((directory / 'robot-report.json').read_text(encoding='utf-8'))
                receipt = export_finished_session(report, directory / 'robot-evidence')
                result = {**result, 'transfer_only_recovery': receipt.get('status')}
            except Exception as exc:
                result = {**result, 'transfer_only_error': type(exc).__name__ + ':' + str(exc)[:160]}
        print(json.dumps({'job_id': job, 'qualified_input_sent': qualified_input_sent,
                          'state': result.get('state'), 'result': result.get('result'),
                          'reason': result.get('reason'), 'cleanup_confirmed': result.get('cleanup_confirmed'),
                          'physical_verified': result.get('physical_verified'),
                          'evidence_export': result.get('evidence_export'),
                          'transfer_only_recovery': result.get('transfer_only_recovery'),
                          'transfer_only_error': result.get('transfer_only_error'),
                          'session_log_complete': result.get('session_log_complete'),
                          'artifact_directory': str(ROOT / 'artifacts/manual-control' / job)},
                         allow_nan=False), flush=True)
        return 0 if (result.get('state') == 'FINISHED' and result.get('result') == 'QUALIFIED'
                     and result.get('cleanup_confirmed') is True) else 2
    finally:
        controller.close()


if __name__ == '__main__':
    raise SystemExit(main())
