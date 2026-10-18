# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only ROS CDR review for the fixed Sep 30 moving qualification record."""
import hashlib
import json
import math
from pathlib import Path
import sys

HOME = Path('/home/twinpulse/.local/share/twinpulse/robot')
DIRECTORY = HOME / 'reports/manual-5108c2c03f5c4ac993f39115dd204aa3'
EXPECTED_SHA = '806cab7bb266a0758901277af629a2dd310c4b3756ea7a06fe2b5850a58e5a21'


def main():
    if sys.argv[1:]:
        raise SystemExit('No runtime overrides accepted')
    raw = DIRECTORY / 'ros-messages.raw'
    if hashlib.sha256(raw.read_bytes()).hexdigest() != EXPECTED_SHA:
        raise ValueError('RAW_SHA_MISMATCH')
    sys.path.insert(0, str((HOME / 'current').resolve(strict=True)))
    from raw_ros_record import inspect_recording
    from rclpy.serialization import deserialize_message
    from nav_msgs.msg import Odometry
    from turtlebot3_msgs.msg import SensorState
    frames = inspect_recording(raw)
    poses = []
    sensors = []
    for meta, payload in frames:
        if meta['topic'] == 'sensor_state':
            sensor = deserialize_message(payload, SensorState)
            sensors.append({'battery_v': float(sensor.battery),
                            'button': int(sensor.button),
                            'encoders': [int(sensor.left_encoder), int(sensor.right_encoder)]})
        if meta['topic'] != 'odom':
            continue
        msg = deserialize_message(payload, Odometry)
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        values = [p.x, p.y, p.z, q.x, q.y, q.z, q.w]
        if not all(math.isfinite(value) for value in values):
            raise ValueError('NONFINITE_ODOM')
        poses.append({'sequence': meta['sequence'],
                      'receipt_monotonic_ns': meta['receipt_monotonic_ns'],
                      'stamp_ns': msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec,
                      'frame_id': msg.header.frame_id,
                      'child_frame_id': msg.child_frame_id,
                      'position_m': values[:3], 'quaternion_xyzw': values[3:]})
    if not poses:
        raise ValueError('NO_ODOM_IN_VERIFIED_RAW')
    first, last = poses[0], poses[-1]
    result = {'schema_version': 'moving-odom-review-1.0', 'source_sha256': EXPECTED_SHA,
              'source_status': 'VERIFIED_COMPLETE_RAW', 'count': len(poses),
              'frames': sorted(set((p['frame_id'], p['child_frame_id']) for p in poses)),
              'stamp_monotonic': all(a['stamp_ns'] <= b['stamp_ns'] for a,b in zip(poses,poses[1:])),
              'first': first, 'last': last,
              'delta_position_m': [b-a for a,b in zip(first['position_m'],last['position_m'])],
              'x_range_m': [min(p['position_m'][0] for p in poses),
                            max(p['position_m'][0] for p in poses)],
              'all_positions_m': [p['position_m'] for p in poses],
              'sensor_state_count': len(sensors),
              'minimum_sensor_battery_v': min(s['battery_v'] for s in sensors) if sensors else None,
              'button_values': sorted(set(s['button'] for s in sensors)),
              'first_sensor': sensors[0] if sensors else None,
              'last_sensor': sensors[-1] if sensors else None,
              'meaning': 'moving wheel diagnostic only; no room transform or floor pose measurement'}
    print(json.dumps(result, allow_nan=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
