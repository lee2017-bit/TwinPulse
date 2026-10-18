# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Native task resource extraction contracts, without ROS/device initialization."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import patch
import unittest
from teleop_ros import RosLink
from observed_runtime import RobotObservedFactory
from twinpulse_app.goal_task_loop import resource_check


class TaskResourceTests(unittest.TestCase):
    def link(self):
        value=RosLink.__new__(RosLink)
        value.sensor=NS(battery=12.,torque=False,header=NS(stamp=NS(sec=10,nanosec=0)))
        value.sensor_t=10.01;value.enabled=False;value.fresh=lambda:None
        value.node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=10030000000)))
        return value

    def test_source_timestamp_voltage_and_disabled_fact_are_not_restamped(self):
        link=self.link();row=link.task_resources()
        self.assertEqual(row['sample_s'],10.01);self.assertAlmostEqual(row['source_age_s'],.03)
        self.assertEqual(resource_check({'task_resources':row},10.04)['voltage_v'],12.)
        link.sensor.torque=True
        with self.assertRaisesRegex(ValueError,'MOTOR_OFF'):resource_check({'task_resources':link.task_resources()},10.04)

    def test_existing_freshness_failure_is_preserved(self):
        link=self.link()
        with patch.object(link,'fresh',side_effect=ValueError('BATTERY_BUTTON_OR_SOURCE_AGE')):
            with self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):link.task_resources()

    def test_native_preview_adds_resources_without_mutating_legacy_sampler(self):
        factory=RobotObservedFactory.__new__(RobotObservedFactory)
        original={'sample_s':10.,'state':'TRACKING_CANDIDATE','pose_map':[0.,0.,0.]}
        factory.idle_evidence=NS(sample=lambda:deepcopy(original));factory.link=self.link()
        value=factory.preview_current()
        self.assertEqual({k:v for k,v in value.items() if k!='task_resources'},original)
        self.assertIn('task_resources',value);self.assertNotIn('task_resources',original)
        factory.link=NS()
        self.assertEqual(factory.preview_current(),original)
