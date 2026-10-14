# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Passive 20-second ROS observer; no application publishers or service clients."""
import json
import math
from itertools import islice
from pathlib import Path
import re
import sys
import time

from raw_ros_record import RawRosRecorder

try:
    from ros_observations import RosObservations
except ModuleNotFoundError as exc:
    if exc.name != 'ros_observations':
        raise
    from twinpulse_core.ros_observations import RosObservations


def _number(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) else 'NONFINITE_OR_NONNUMERIC'


def _frame(value):
    # Preserve a possible leading slash, but never export arbitrary ROS strings.
    return value if isinstance(value, str) and re.fullmatch(r'/?[A-Za-z0-9_][A-Za-z0-9_/]{0,79}', value) else 'INVALID_FRAME'


class PassiveEvidence:
    """Small read-only diagnostic, independent of the stationary safety verdict."""
    def __init__(self):
        self.observations = RosObservations()
        self.counts = {'odom': 0, 'scan': 0, 'tf': 0, 'tf_static': 0}
        self.fault_counts = {'odom': {}, 'scan': {}}
        self.first = {'odom': [], 'scan': []}
        self.examples = {'odom': {}, 'scan': {}}
        self.latest = {'odom': None, 'scan': None}
        self.tf = []
        self.tf_pairs = set()
        self.errors = []
        self.endpoints = {}

    def message(self, kind, msg, ros_now_ns, receipt_s, publishers):
        self.counts[kind] += 1
        try:
            self.observations.receive(kind, msg, ros_now_ns, receipt_s, publishers)
            fault = self.observations.faults[kind]
            faults = self.fault_counts[kind]
            faults[fault] = faults.get(fault, 0) + 1
            header = msg.header
            sample = {'fault': fault, 'frame_id': _frame(header.frame_id),
                      'stamp_sec': header.stamp.sec if type(header.stamp.sec) is int else 'INVALID_STAMP',
                      'stamp_nanosec': header.stamp.nanosec if type(header.stamp.nanosec) is int else 'INVALID_STAMP',
                      'ros_now_ns': ros_now_ns, 'publisher_count': publishers}
            if kind == 'odom':
                pose = msg.pose.pose
                sample.update(child_frame_id=_frame(msg.child_frame_id),
                              position_m=[_number(getattr(pose.position, name)) for name in ('x', 'y', 'z')],
                              quaternion_xyzw=[_number(getattr(pose.orientation, name)) for name in ('x', 'y', 'z', 'w')])
            else:
                sample.update(ray_count=len(msg.ranges), angle_min_rad=_number(msg.angle_min),
                              angle_increment_rad=_number(msg.angle_increment),
                              range_min_m=_number(msg.range_min), range_max_m=_number(msg.range_max))
            if len(self.first[kind]) < 3:
                self.first[kind].append(sample)
            self.examples[kind].setdefault(fault, sample)
            self.latest[kind] = sample
        except Exception as exc:
            # A diagnostic failure must not turn an idle safety check into a pose claim.
            if len(self.errors) < 4:
                self.errors.append('RAW_EXTRACTION_' + kind.upper() + '_' + type(exc).__name__)

    def tf_message(self, msg, kind='tf'):
        try:
            if len(msg.transforms) > 64 and len(self.errors) < 4:
                self.errors.append('TF_MESSAGE_BUDGET')
            for transform in islice(msg.transforms, 64):
                self.counts[kind] += 1
                frame_id = _frame(transform.header.frame_id)
                child_frame_id = _frame(transform.child_frame_id)
                pair = (frame_id, child_frame_id)
                if len(self.tf) < 8 and pair not in self.tf_pairs:
                    self.tf_pairs.add(pair)
                    self.tf.append({'frame_id': frame_id,
                                    'child_frame_id': child_frame_id,
                                    'topic': '/' + kind,
                                    'stamp_sec': transform.header.stamp.sec,
                                    'stamp_nanosec': transform.header.stamp.nanosec,
                                    'translation_m': [_number(getattr(transform.transform.translation, name))
                                                      for name in ('x', 'y', 'z')],
                                    'quaternion_xyzw': [_number(getattr(transform.transform.rotation, name))
                                                        for name in ('x', 'y', 'z', 'w')]})
        except Exception as exc:
            if len(self.errors) < 4:
                self.errors.append('TF_EXTRACTION_' + kind.upper() + '_' + type(exc).__name__)

    def endpoint_snapshot(self, node):
        """Explain missing messages without subscribing to or starting another device."""
        for kind, topic in (('odom', 'odom'), ('scan', 'scan'), ('tf', '/tf'),
                            ('tf_static', '/tf_static')):
            try:
                publishers = node.count_publishers(topic)
                self.endpoints[kind] = {
                    'topic': topic, 'publisher_count': publishers,
                    'diagnosis': ('NO_PUBLISHER' if publishers == 0 else
                                  'MULTIPLE_PUBLISHERS' if publishers > 1 else
                                  'PUBLISHER_PRESENT')}
            except Exception as exc:
                self.endpoints[kind] = {'topic': topic, 'diagnosis': 'DISCOVERY_ERROR_' + type(exc).__name__}

    def report(self):
        status = {}
        missing_reason = {}
        for kind in ('odom', 'scan'):
            status[kind] = ('NOT_RECEIVED' if self.counts[kind] == 0 else
                            'REJECTED' if not self.fault_counts[kind].get('NONE') else
                            'SAMPLES_ACCEPTED_UNALIGNED')
            if self.counts[kind] == 0:
                endpoint = self.endpoints.get(kind, {})
                missing_reason[kind] = ('NO_PUBLISHER' if endpoint.get('publisher_count') == 0 else
                                        'NO_MESSAGE_WITH_PUBLISHER' if endpoint.get('publisher_count', 0) > 0 else
                                        'DISCOVERY_UNAVAILABLE')
        return {'source': 'passive_ros_only', 'motion_authorized': False,
                'status': status, 'tf_status': 'NOT_RECEIVED' if not self.counts['tf'] else 'RECEIVED_UNVALIDATED',
                'tf_static_status': 'NOT_RECEIVED' if not self.counts['tf_static'] else 'RECEIVED_UNVALIDATED',
                'endpoints': self.endpoints, 'missing_reason': missing_reason,
                'counts': dict(self.counts), 'fault_counts': self.fault_counts,
                'first': self.first, 'examples_by_fault': self.examples,
                'latest': self.latest, 'tf_first': self.tf,
                'capture_errors': self.errors,
                'note': 'No scan/TF/odom validity or room alignment is inferred from receipt alone.'}


class IdleWatch:
    def __init__(self):
        self.anchor = None
        self.samples = 0
        self.sensor_time = None
        self.guard_time = None
        self.guard = None
        self.errors = []

    def sensor(self, now, encoders, torque, volts, button, source_age):
        self.sensor_time = now
        self.samples += 1
        if self.anchor is None:
            self.anchor = encoders
        if (torque or button or not math.isfinite(volts) or volts <= 11.1
                or not math.isfinite(source_age) or not 0 <= source_age < .2
                or any(abs(a-b) > 2 for a, b in zip(self.anchor, encoders))):
            self.errors.append('unsafe_or_stale_sensor')

    def status(self, now, value):
        self.guard_time, self.guard = now, value
        if value != 'explicit_stop':
            self.errors.append('guard_not_disarmed')

    def verify(self, now, publisher_count, sensor_publishers=1, guard_publishers=1):
        if self.errors:
            raise ValueError(self.errors[0])
        if publisher_count != 0:
            raise ValueError('unexpected_velocity_publisher')
        if sensor_publishers != 1 or guard_publishers != 1:
            raise ValueError('ambiguous_or_missing_telemetry_source')
        if (self.samples < 10 or self.sensor_time is None or self.guard_time is None
                or now - self.sensor_time >= .2 or now - self.guard_time >= .2
                or self.guard != 'explicit_stop'):
            raise ValueError('telemetry_missing_or_stale')


def main(output):
    import rclpy
    from rclpy.serialization import serialize_message
    from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
    from turtlebot3_msgs.msg import SensorState
    from std_msgs.msg import String
    try:
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
    except ImportError:
        Odometry = LaserScan = None
    try:
        from tf2_msgs.msg import TFMessage
    except ImportError:
        TFMessage = None
    rclpy.init()
    node = rclpy.create_node('twinpulse_stationary_observer', namespace='/tp_guard_stationary')
    watch = IdleWatch()
    passive = PassiveEvidence()
    raw = RawRosRecorder(Path(output).with_name('ros-messages.raw'), serializer=serialize_message)
    rows = []
    result = {'motion_authorized': False, 'status': 'FAILED'}

    def sensor(msg):
        raw.record('sensor_state', msg)
        age = (node.get_clock().now().nanoseconds - (msg.header.stamp.sec * 1000000000 + msg.header.stamp.nanosec)) / 1e9
        now = time.monotonic()
        watch.sensor(now, (msg.left_encoder, msg.right_encoder), msg.torque, msg.battery, msg.button, age)
        rows.append({'steady_s': now, 'source_age_s': age if math.isfinite(age) else None,
                     'encoders': [msg.left_encoder, msg.right_encoder], 'torque': msg.torque,
                     'voltage_v': float(msg.battery) if math.isfinite(msg.battery) else None})

    node.create_subscription(SensorState, 'sensor_state', sensor, qos_profile_sensor_data)
    def guard_status(msg):
        raw.record('motion_guard/status', msg)
        watch.status(time.monotonic(), msg.data)

    node.create_subscription(String, 'motion_guard/status', guard_status, 1)
    if Odometry is not None:
        def odom_message(msg):
            raw.record('odom', msg)
            passive.message('odom', msg, node.get_clock().now().nanoseconds,
                            time.monotonic(), node.count_publishers('odom'))
        node.create_subscription(Odometry, 'odom',
            odom_message,
            qos_profile_sensor_data)
    if LaserScan is not None:
        def scan_message(msg):
            raw.record('scan', msg)
            passive.message('scan', msg, node.get_clock().now().nanoseconds,
                            time.monotonic(), node.count_publishers('scan'))
        node.create_subscription(LaserScan, 'scan',
            scan_message,
            qos_profile_sensor_data)
    if TFMessage is not None:
        def tf_message(msg):
            raw.record('/tf', msg)
            passive.tf_message(msg)
        node.create_subscription(TFMessage, '/tf', tf_message, qos_profile_sensor_data)
        node.create_subscription(TFMessage, '/tf_static',
                                 lambda msg: (raw.record('/tf_static', msg),
                                              passive.tf_message(msg, 'tf_static')),
                                 QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    start = time.monotonic()
    try:
        while time.monotonic() - start < 20:
            rclpy.spin_once(node, timeout_sec=.05)
            if watch.errors:
                raise ValueError(watch.errors[0])
            publishers = node.count_publishers('guarded_cmd_vel') + node.count_publishers('cmd_vel')
            if publishers:
                raise ValueError('unexpected_velocity_publisher')
            # Give base's existing IMU calibration and discovery eight seconds.
            if time.monotonic() - start >= 8:
                watch.verify(time.monotonic(), publishers, node.count_publishers('sensor_state'),
                             node.count_publishers('motion_guard/status'))
        watch.verify(time.monotonic(), node.count_publishers('guarded_cmd_vel') + node.count_publishers('cmd_vel'),
                     node.count_publishers('sensor_state'), node.count_publishers('motion_guard/status'))
        result['status'] = 'STATIONARY_OBSERVED'
    except (Exception, KeyboardInterrupt) as exc:
        result['reason'] = str(exc)
    finally:
        try:
            raw_result = raw.close()
        except (OSError, ValueError) as exc:
            raw_result = {'complete': False, 'error': type(exc).__name__ + ':' + str(exc)[:120]}
        if not raw_result['complete']:
            result['status'] = 'FAILED'
            result['reason'] = 'RAW_RECORDING_INCOMPLETE'
        passive.endpoint_snapshot(node)
        result.update(sensor_samples=watch.samples, samples=rows, guard_status=watch.guard,
                      elapsed_s=round(time.monotonic() - start, 3), passive_ros=passive.report(),
                      raw_ros=raw_result)
        Path(output).write_text(json.dumps(result, indent=2, allow_nan=False))
        node.destroy_node()
        rclpy.shutdown()
    return 0 if result['status'] == 'STATIONARY_OBSERVED' else 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
