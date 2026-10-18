# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline review semantics: correlated commands, not route/pose authority."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from review_manual_scan_session import event_summary


def robot(kind,t,data,pc_t=None):
    return {'kind':'robot_event','t':t+100 if pc_t is None else pc_t,
            'data':{'event':{'kind':kind,'t':t,'data':data}}}


class SessionReviewTests(unittest.TestCase):
    def test_pc_close_after_finished_is_not_last_robot_command(self):
        rows=[robot('published',1.,{'sequence':1,'action':'forward'}),
              {'kind':'pipe_written','t':102.,'data':{'sequence':2,'action':'finish_stop'}},
              robot('accepted',2.,{'sequence':2,'action':'finish_stop'}),
              robot('idle_confirmed',2.3,{'sequence':2}),
              {'kind':'robot_finished','t':105.,'data':{'status':'COMMAND_SEGMENT_STOPPED'}},
              {'kind':'input_received','t':105.1,'data':{'sequence':3,'action':'close'}}]
        result=event_summary(rows)
        self.assertEqual(result['last_pc_input']['action'],'close')
        self.assertEqual(result['last_robot_accepted']['action'],'finish_stop')
        self.assertEqual(result['last_idle_confirmation']['sequence'],2)
        self.assertEqual(result['published_after_terminal_count'],0)
        self.assertEqual(result['pc_inputs_after_finished'][0]['sequence'],3)

    def test_unexpected_publication_after_terminal_is_not_hidden(self):
        rows=[robot('accepted',1.,{'sequence':1,'action':'close'}),
              robot('published',2.,{'sequence':2,'action':'right'})]
        self.assertEqual(event_summary(rows)['published_after_terminal_count'],1)

    def test_no_accepted_terminal_is_not_a_verified_final_stop(self):
        result=event_summary([robot('published',1.,{'sequence':1,'action':'forward'})])
        self.assertIsNone(result['terminal_accepted'])
        self.assertIsNone(result['published_after_terminal_count'])

    def test_clock_domain_offsets_do_not_become_network_latency(self):
        rows=[robot('observation',100.,{},pc_t=50000.),
              robot('observation',100.05,{},pc_t=50001.5)]
        self.assertAlmostEqual(event_summary(rows)['max_observation_receipt_interval_excess_s'],1.45)


if __name__=='__main__':unittest.main()
