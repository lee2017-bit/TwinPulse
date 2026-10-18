# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline contract tests. No SSH, robot, ROS installation, or motor command."""

import ast
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_robot_connection import endpoint, parse_report, payload
from turtlebot_probe import choose_topic, inventory
import check_robot_connection as connection


class RobotConnectionTests(unittest.TestCase):
    def _run_cli(self, response):
        with patch.object(sys, "argv", ["check", "--host", "robot.local", "--user", "ubuntu", "--batch"]), \
             patch.object(connection.shutil, "which", return_value="ssh.exe"), \
             patch.object(connection.subprocess, "run", side_effect=response) as run, \
             patch.object(connection, "write_report", return_value=Path("report.html")) as write:
            code = connection.main()
            return code, write.call_args.args[0], run.call_args

    def test_cli_timeout_is_bounded_and_not_ready(self):
        code, report, call = self._run_cli(subprocess.TimeoutExpired("ssh", 120))
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "CONNECTION_CHECK_TIMEOUT")
        self.assertFalse(report["motion_authorized"])
        self.assertEqual(call.kwargs["timeout"], 120)
        self.assertIsInstance(call.kwargs["input"], bytes)
        self.assertNotIn(b"\r\n", call.kwargs["input"])
        self.assertIn("StrictHostKeyChecking=yes", call.args[0])

    def test_cli_auth_failure_does_not_fall_back_or_retry(self):
        response = subprocess.CompletedProcess([], 255, "", b"Permission denied (publickey,password).\n")
        code, report, _ = self._run_cli(lambda *a, **k: response)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "SSH_OR_REMOTE_SETUP_FAILED")
        self.assertEqual(report["reason"], "Permission denied (publickey,password).")

    def test_cli_sensor_receipt_still_has_no_motion_permission(self):
        record = {"schema_version": "robot-connection-1.0", "mode": "read_only",
                  "motion_authorized": False, "physical_identity_verified": False,
                  "status": "SENSOR_MESSAGES_RECEIVED"}
        response = subprocess.CompletedProcess([], 0, "TWINPULSE_ROBOT_REPORT=" + json.dumps(record))
        code, report, _ = self._run_cli(lambda *a, **k: response)
        self.assertEqual(code, 0)
        self.assertFalse(report["motion_authorized"])

    def test_endpoint_rejects_shell_and_option_injection(self):
        self.assertEqual(endpoint("192.168.0.22", "ubuntu"), "ubuntu@192.168.0.22")
        self.assertEqual(endpoint("turtlebot.local", "robot"), "robot@turtlebot.local")
        for host in ("-oProxyCommand=x", "host;id", "host $(id)", "user@host", "http://host"):
            with self.assertRaises(ValueError):
                endpoint(host, "ubuntu")
        with self.assertRaises(ValueError):
            endpoint("robot.local", "root;id")

    def test_payload_has_explicit_domain_no_driver_start(self):
        script = payload("auto", 30)
        self.assertIn("export ROS_DOMAIN_ID=30", script)
        for bad in ("rolling;id", "jazzy && id"):
            with self.assertRaises(ValueError):
                payload(bad)
        for bad in (-1, 233, True):
            with self.assertRaises(ValueError):
                payload("auto", bad)
        for forbidden in ("ros2 launch", "topic pub", "sudo ", "apt install", "motor_power"):
            self.assertNotIn(forbidden, script)

    def test_probe_has_no_application_publisher_or_service_client(self):
        tree = ast.parse((ROOT / "scripts/turtlebot_probe.py").read_text(encoding="utf-8"))
        calls = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("create_publisher", calls)
        self.assertNotIn("create_client", calls)
        self.assertIn("create_subscription", calls)

    def test_report_requires_readonly_unverified_identity(self):
        report = {"schema_version": "robot-connection-1.0", "mode": "read_only",
                  "motion_authorized": False, "physical_identity_verified": False,
                  "status": "SENSOR_MESSAGES_RECEIVED"}
        line = "TWINPULSE_ROBOT_REPORT=" + json.dumps(report)
        self.assertEqual(parse_report("noise\n" + line), report)
        with self.assertRaises(ValueError):
            parse_report(line + "\n" + line)
        report["motion_authorized"] = True
        with self.assertRaises(ValueError):
            parse_report("TWINPULSE_ROBOT_REPORT=" + json.dumps(report))

    def test_topic_discovery_handles_namespace_and_ambiguity(self):
        msg = "sensor_msgs/msg/LaserScan"
        self.assertEqual(choose_topic([("/robot/scan", [msg])], "/scan", msg), "/robot/scan")
        self.assertIsNone(choose_topic([("/a/scan", [msg]), ("/b/scan", [msg])], "/scan", msg))

    def test_inventory_does_not_dump_environment_or_serial_ids(self):
        data = inventory()
        self.assertEqual(set(data), {"os", "architecture", "ros_installations", "active_ros",
                                     "ros_domain_id", "rmw_implementation", "serial_device_count"})


if __name__ == "__main__":
    unittest.main()
