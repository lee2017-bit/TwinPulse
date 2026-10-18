# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline exact-byte review of one owned qualify+scan robot recording.

Receipt timestamps share the robot monotonic clock. This establishes overlap
with issued commands, not measured floor motion or calibrated transforms.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_robot_safety'))
from raw_ros_record import inspect_recording


def inspect(report, raw_path, export_receipt):
    result = {'status': 'INCOMPLETE', 'physical_motion_verified': False,
              'alignment_verified': False, 'reason': None}
    if report.get('mode') != 'qualify_scan':
        return {**result, 'reason': 'NOT_COMBINED_SESSION'}
    if (export_receipt.get('status') != 'COMPLETE' or
            export_receipt.get('robot_session_id') != report.get('robot_session_id') or
            export_receipt.get('binding') != 'VERIFIED'):
        return {**result, 'reason': 'EVIDENCE_EXPORT_OR_CONTEXT_INCOMPLETE'}
    try:
        frames = inspect_recording(raw_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {**result, 'reason': 'RAW_' + type(exc).__name__ + ':' + str(exc)[:100]}
    times = report.get('moving_command_ns')
    if (not isinstance(times, list) or len(times) < 2 or
            any(type(t) is not int or t <= 0 for t in times) or
            times != sorted(times) or times[-1] - times[0] > 2_000_000_000):
        return {**result, 'reason': 'MOTION_COMMAND_WINDOW_MISSING_OR_INVALID'}
    first, last = times[0], times[-1] + 500_000_000
    topics = ('scan', 'odom', '/tf')
    in_window = {name: sum(meta['topic'] == name and first <= meta['receipt_monotonic_ns'] <= last
                           for meta, _ in frames) for name in topics}
    totals = {name: sum(meta['topic'] == name for meta, _ in frames)
              for name in (*topics, '/tf_static', 'guarded_cmd_vel')}
    result.update(window_robot_monotonic_ns=[first, last], in_command_window=in_window,
                  full_session_counts=totals, robot_boot_id=report.get('boot_id'),
                  robot_release_id=report.get('release_id'),
                  source='ORIGINAL_ROS_CDR_BYTES_NOT_DECODED')
    received = report.get('received_counts', {})
    if (not isinstance(received, dict) or any(received.get(name) != totals[name]
                                               for name in (*topics, '/tf_static'))):
        result['reason'] = 'ROBOT_REPORT_RAW_TOPIC_COUNT_MISMATCH'
    elif totals['guarded_cmd_vel'] < 2:
        result['reason'] = 'GUARDED_COMMAND_RAW_MISSING'
    elif any(in_window[name] < 1 for name in topics):
        result['reason'] = 'COMMAND_WINDOW_SCAN_ODOM_OR_DYNAMIC_TF_MISSING'
    elif totals['/tf_static'] < 1:
        result['reason'] = 'STATIC_TF_NOT_CAPTURED'
    else:
        result['status'] = 'COMMAND_WINDOW_RAW_CAPTURED_UNALIGNED'
        result['reason'] = None
    return result
