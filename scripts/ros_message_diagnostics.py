# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded, read-only diagnostics for already-decoded ROS evidence.

This does not reconstruct ROS time, discover publishers, validate TF geometry,
or authorize a pose or motion. Invalid messages remain in the raw bundle.
"""
import math
import re


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _frame(value):
    return isinstance(value, str) and re.fullmatch(r'/?[A-Za-z0-9_][A-Za-z0-9_/]{0,79}', value) is not None


def _stamp(header, *, allow_zero=False):
    stamp = header.stamp
    return (type(stamp.sec) is int and type(stamp.nanosec) is int
            and 0 <= stamp.sec < 2**31 and 0 <= stamp.nanosec < 10**9
            and (allow_zero or stamp.sec * 10**9 + stamp.nanosec > 0))


def _quaternion(value):
    numbers = [getattr(value, part) for part in ('x', 'y', 'z', 'w')]
    return all(_finite(number) and abs(number) <= 1.001 for number in numbers) and abs(
        sum(number * number for number in numbers) - 1) <= .001


def _odom(msg):
    if not _stamp(msg.header):
        return 'STAMP_FORMAT'
    if not _frame(msg.header.frame_id) or not _frame(msg.child_frame_id):
        return 'FRAME_ID'
    position = msg.pose.pose.position
    if not all(_finite(getattr(position, part)) and abs(getattr(position, part)) <= 1000
               for part in ('x', 'y', 'z')):
        return 'ODOM_POSITION'
    if not _quaternion(msg.pose.pose.orientation):
        return 'ODOM_ORIENTATION'
    return 'SHAPE_OK_NOT_POSE_VERIFIED'


def _scan(msg):
    if not _stamp(msg.header):
        return 'STAMP_FORMAT'
    if not _frame(msg.header.frame_id):
        return 'FRAME_ID'
    rays = msg.ranges
    if not 72 <= len(rays) <= 720:
        return 'SCAN_RAY_COUNT'
    fields = (msg.angle_min, msg.angle_max, msg.angle_increment,
              msg.range_min, msg.range_max, msg.time_increment)
    if (not all(_finite(value) for value in fields)
            or not 0 < msg.range_min < msg.range_max <= 30
            or not 0 < msg.angle_increment <= .1
            or abs(msg.angle_min) > math.tau
            or not 0 <= msg.time_increment < .2
            or abs(msg.angle_max - (msg.angle_min + (len(rays) - 1) * msg.angle_increment)) > .01
            or abs(msg.angle_increment * len(rays) - math.tau) > .01):
        return 'SCAN_GEOMETRY'
    if any(not _finite(ray) or not msg.range_min <= ray <= msg.range_max for ray in rays):
        return 'SCAN_RANGES_UNUSABLE'
    return 'SHAPE_OK_NOT_SCAN_VERIFIED'


def _tf(msg, *, static=False):
    transforms = msg.transforms
    if len(transforms) > 64:
        return 'TF_REVIEW_BUDGET_EXCEEDED'
    if not transforms:
        return 'TF_EMPTY'
    for transform in transforms:
        if not _stamp(transform.header, allow_zero=static):
            return 'STAMP_FORMAT'
        if not _frame(transform.header.frame_id) or not _frame(transform.child_frame_id):
            return 'FRAME_ID'
        if transform.header.frame_id == transform.child_frame_id:
            return 'TF_SELF_EDGE'
        translation = transform.transform.translation
        if not all(_finite(getattr(translation, part)) and abs(getattr(translation, part)) <= 1000
                   for part in ('x', 'y', 'z')):
            return 'TF_TRANSLATION'
        if not _quaternion(transform.transform.rotation):
            return 'TF_ROTATION'
    return 'SHAPE_OK_NOT_TF_ALIGNED'


def review_replayed(replayed):
    """Summarize every decoded frame; examples contain codes/sequence only."""
    counts = {}
    findings = {}
    examples = []
    reviewers = {'odom': _odom, 'scan': _scan, '/tf': _tf,
                 '/tf_static': lambda msg: _tf(msg, static=True)}
    for metadata, message in replayed:
        topic = metadata['topic']
        counts[topic] = counts.get(topic, 0) + 1
        reviewer = reviewers.get(topic)
        try:
            reason = reviewer(message) if reviewer else 'NOT_SEMANTICALLY_REVIEWED'
        except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
            reason = 'MESSAGE_SHAPE'
        topic_findings = findings.setdefault(topic, {})
        topic_findings[reason] = topic_findings.get(reason, 0) + 1
        if reason not in {'SHAPE_OK_NOT_POSE_VERIFIED', 'SHAPE_OK_NOT_SCAN_VERIFIED',
                          'SHAPE_OK_NOT_TF_ALIGNED', 'NOT_SEMANTICALLY_REVIEWED'} and len(examples) < 12:
            examples.append({'sequence': metadata['sequence'], 'topic': topic, 'reason': reason})
    return {'schema_version': 'ros-message-diagnostics-1', 'status': 'ISSUES' if examples else 'INSPECTED',
            'scope': 'DECODED_SHAPE_ONLY_NO_POSE_OR_MOTION_AUTHORITY',
            'counts': counts, 'findings': findings, 'examples': examples}
