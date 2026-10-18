# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only Pi inventory and finite ROS sensor observation. Never starts bringup."""

import glob
import json
import math
import os
from pathlib import Path
import platform
import time

if 'health_snapshot' not in globals():
    from robot_health import health_snapshot, summarize_health

MARKER = "TWINPULSE_ROBOT_REPORT="


def inventory():
    os_info = {}
    path = Path("/etc/os-release")
    if path.exists():
        for line in path.read_text().splitlines():
            key, _, value = line.partition("=")
            if key in {"ID", "VERSION_ID", "PRETTY_NAME"}:
                os_info[key] = value.strip('"')
    return {"os": os_info, "architecture": platform.machine(),
            "ros_installations": sorted(p.name for p in Path("/opt/ros").glob("*") if p.is_dir()),
            "active_ros": os.environ.get("ROS_DISTRO"),
            "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
            "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", "default"),
            "serial_device_count": len(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))}


def choose_topic(graph, preferred, message_type):
    matches = [name for name, types in graph if message_type in types]
    return matches[0] if len(matches) == 1 else None


def scan_snapshot(message):
    """Keep original beam indices and header for later offline diagnosis."""
    if not 2<=len(message.ranges)<=4096:return None
    metadata=(message.angle_min,message.angle_increment,message.range_min,message.range_max)
    if not all(math.isfinite(v) for v in metadata) or message.angle_increment<=0:return None
    return dict(stamp_ns=message.header.stamp.sec*1_000_000_000+message.header.stamp.nanosec,
        frame_id=message.header.frame_id,angle_min_rad=float(message.angle_min),
        angle_increment_rad=float(message.angle_increment),range_min_m=float(message.range_min),
        range_max_m=float(message.range_max),ranges_m=[float(v) if math.isfinite(v)
            and message.range_min<=v<=message.range_max else None for v in message.ranges])


def probe(duration=8.0):
    report = {"schema_version": "robot-connection-1.0", "inventory": inventory(),
              "status": "ROS_PYTHON_UNAVAILABLE", "observations": {},
              "physical_identity_verified": False, "motion_authorized": False,
              "mode": "read_only", "source": "unverified_ros_graph"}
    report['obstacle_observation']=dict(schema_version='obstacle-observation-1.0',
        provenance='ROBOT_READ_ONLY',scans=[])
    report['odometry_samples']=[]
    if os.environ.get('TWINPULSE_HEALTH') == '1':
        report['health'] = summarize_health(health_snapshot())
    try:
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan
        from nav_msgs.msg import Odometry
        from std_msgs.msg import String
    except ImportError:
        return report
    rclpy.init(args=[])
    node = rclpy.create_node("twinpulse_readonly_probe_" + str(os.getpid()), enable_rosout=False,
                             start_parameter_services=False)
    try:
        until = time.monotonic() + 2.0
        while time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.1)
        graph = node.get_topic_names_and_types()
        report["topics"] = [{"name": name, "types": types} for name, types in graph]
        report["command_publishers"] = [
            {"topic": name, "count": node.count_publishers(name), "types": types}
            for name, types in graph if name.split("/")[-1] in {"cmd_vel", "guarded_cmd_vel"}]
        report["tf_publishers"] = {name: node.count_publishers(name)
                                   for name, _ in graph if name.split("/")[-1] in {"tf", "tf_static"}}
        subscriptions = []

        def callback(kind):
            def observe(message):
                record = report["observations"][kind]
                record["messages"] += 1
                record['last_received_monotonic'] = time.monotonic()
                record["frame_id"] = message.header.frame_id
                stamp = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
                record["last_stamp_age_s"] = time.time() - stamp
                if kind == "scan":
                    finite = [r for r in message.ranges if math.isfinite(r)
                              and message.range_min <= r <= message.range_max]
                    record["valid_ranges"] = len(finite)
                    record["total_ranges"] = len(message.ranges)
                    scans=report['obstacle_observation']['scans']
                    if not scans or message.header.stamp.sec*1_000_000_000+message.header.stamp.nanosec-scans[-1]['stamp_ns']>=500_000_000:
                        snapshot=scan_snapshot(message)
                        if snapshot is not None:
                            scans.append(snapshot)
                            if len(scans)>8:scans.pop(0)
                else:
                    record["child_frame_id"] = message.child_frame_id
                    record['linear_x'] = message.twist.twist.linear.x
                    record['angular_z'] = message.twist.twist.angular.z
                    p=message.pose.pose.position;q=message.pose.pose.orientation
                    sample=dict(stamp_ns=message.header.stamp.sec*1_000_000_000+message.header.stamp.nanosec,
                        frame_id=message.header.frame_id,child_frame_id=message.child_frame_id,
                        position_m=[p.x,p.y,p.z],orientation_xyzw=[q.x,q.y,q.z,q.w],
                        linear_x=message.twist.twist.linear.x,angular_z=message.twist.twist.angular.z)
                    if all(math.isfinite(v) for v in sample['position_m']+sample['orientation_xyzw']+[sample['linear_x'],sample['angular_z']]):
                        report['odometry_samples'].append(sample)
                        if len(report['odometry_samples'])>16:report['odometry_samples'].pop(0)
            return observe

        for kind, cls, msg_type in (("scan", LaserScan, "sensor_msgs/msg/LaserScan"),
                                   ("odom", Odometry, "nav_msgs/msg/Odometry")):
            topic = choose_topic(graph, "/" + kind, msg_type)
            report["observations"][kind] = {"topic": topic, "messages": 0}
            if topic:
                subscriptions.append(node.create_subscription(cls, topic, callback(kind), qos_profile_sensor_data))
        if 'health' in report:
            guard_topics = [name for name, types in graph
                            if name.endswith('/motion_guard/status') and 'std_msgs/msg/String' in types]
            report['health']['guard_telemetry'] = {'status': 'UNAVAILABLE', 'candidates': guard_topics}
            if len(guard_topics) == 1:
                def observe_guard(message):
                    report['health']['guard_telemetry'].update(
                        status='OBSERVED', value=message.data[:100],
                        last_received_monotonic=time.monotonic())
                subscriptions.append(node.create_subscription(String, guard_topics[0], observe_guard, 1))
        until = time.monotonic() + duration
        while time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.1)
        counts = [entry["messages"] for entry in report["observations"].values()]
        for entry in list(report['observations'].values()) + [report.get('health', {}).get('guard_telemetry', {})]:
            received = entry.pop('last_received_monotonic', None)
            if received is not None:
                entry['receipt_age_s'] = round(time.monotonic() - received, 3)
        if 'health' in report:
            report['health']['ros_observations_status'] = 'OBSERVED' if any(counts) else 'NOT_RUNNING_OR_NO_DATA'
        report["status"] = ("SENSOR_MESSAGES_RECEIVED" if all(counts)
                            else "PARTIAL_SENSOR_DATA" if any(counts) else "NO_SENSOR_DATA")
        report["note"] = "Messages are not proof of physical identity, freshness, TF validity, or safe motion."
    except Exception as exc:
        report["status"] = "ROS_PROBE_FAILED"
        report["error_type"] = type(exc).__name__
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return report


if __name__ == "__main__":
    print(MARKER + json.dumps(probe(), allow_nan=False))
