# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""AD1 live duck-ROS and PC diagnostics: no ROS daemon, SSH or devices."""
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from pathlib import Path
from twinpulse_core.observation_stream import ObservationWindow
from twinpulse_app.session_history import transport_diagnostics,valid_pc
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/twinpulse_robot_safety'))
from teleop_ros import RosLink
from packages.twinpulse_core.tests.test_observation_stream import CONTEXT,odom

class BridgeTests(unittest.TestCase):
    def test_live_health_distinguishes_endpoint_missing_multiple_and_qos_failure(self):
        link=RosLink.__new__(RosLink);link.observation_window=ObservationWindow({**CONTEXT,'origin':'live_ros'})
        link.observation_qos=dict.fromkeys(('odom','scan','/tf','/tf_static'),'requested')
        infos={'odom':[],'/scan':[NS(qos_profile='bad')],'/tf':[NS(),NS()],
               '/tf_static':[NS(qos_profile='unknown')]}
        link.node=NS(get_publishers_info_by_topic=lambda topic:infos[topic])
        qos=NS(QoSCompatibility=NS(ERROR=2,WARNING=1),
               qos_check_compatible=lambda pub,_:(2 if pub=='bad' else 1,'not logged raw'))
        with patch.dict(sys.modules,{'rclpy':NS(),'rclpy.qos':qos}),patch('teleop_ros.time.monotonic_ns',return_value=0):
            health=link.observation_health()
        self.assertEqual(health['faults'],{'odom':'ENDPOINT_MISSING','scan':'ENDPOINT_QOS_INCOMPATIBLE',
            '/tf':'ENDPOINT_MULTIPLE_OR_UNKNOWN','/tf_static':'ENDPOINT_QOS_UNVERIFIED'})
        self.assertFalse(health['motion_authorized'])

    def test_live_window_consumer_cursor_never_provides_future_odom(self):
        link=RosLink.__new__(RosLink);link.observation_window=ObservationWindow({**CONTEXT,'origin':'live_ros'})
        self.assertEqual(link.observations_since(-1),[])
        link.observation_window.receive('odom',odom(),4,10)
        events=link.observations_since(-1);self.assertEqual(events[0]['sequence'],4)
        self.assertEqual(link.observations_since(4),[])

    def test_transport_intervals_never_subtract_different_host_clocks(self):
        def pc(t,kind,**data):return {'t':t,'kind':kind,'data':data}
        def robot(t,kind,**data):return pc(1000,'robot_event',event={'t':t,'kind':kind,'data':data})
        rows=[pc(100,'input_received',sequence=1,action='forward'),
              pc(100.1,'pipe_written',sequence=1,action='forward',pipe_write_s=.002),
              robot(1,'accepted',sequence=1,action='forward'),
              robot(1.03,'published',sequence=1,action='forward'),
              pc(101,'input_received',sequence=2,action='close')]
        result=transport_diagnostics(rows)
        self.assertAlmostEqual(result['pc_accept_to_pipe_max_s'],.1)
        self.assertAlmostEqual(result['robot_accept_to_publish_max_s'],.03)
        self.assertIsNone(result['wifi_delay_s']);self.assertEqual(result['cause'],'UNKNOWN_CAUSE')
        self.assertFalse(result['last_terminal_intent']['pipe_written'])
        self.assertFalse(result['last_terminal_intent']['robot_accepted'])
        self.assertFalse(result['physical_stop_verified'])

if __name__=='__main__':unittest.main()
