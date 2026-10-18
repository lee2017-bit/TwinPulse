# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.recorded_replay import RecordedReplayPacer
from tests.integration.test_automatic_demo_service import Source, GEOMETRY
from packages.twinpulse_core.tests.test_automatic_mapping import CONTEXT


class RecordedReplayTests(unittest.TestCase):
    def make(self, factory=lambda *args: Source(positions=[[0, -.6, .4]]*4)):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        service=AutomaticDemoService(Path(temp.name),'default',source_factory=factory,
                                     geometry_loader=lambda:GEOMETRY)
        self.addCleanup(service.close)
        return service

    def finish(self, service):
        service.worker.join(8)
        self.assertFalse(service.worker.is_alive())
        return service.snapshot('owner')['job']

    def test_real_wait_retains_all_events_original_map_and_no_authority(self):
        service=self.make();service.start('owner','a'*32)
        fast=self.finish(service);fast_map=service.reopen('owner',fast['map_id'])['map']
        start=time.monotonic();service.start('owner','a'*32,replay_mode='recorded_1x')
        paced=self.finish(service);elapsed=time.monotonic()-start
        self.assertEqual(paced['state'],'COMPLETED',paced)
        self.assertGreaterEqual(elapsed,.3)
        self.assertEqual(paced['replay_timing']['receipt_span_s'],.3)
        self.assertEqual(paced['replay_timing']['events'],8)
        self.assertEqual(paced['replay_timing']['delivered_events'],8)
        self.assertEqual(paced['replay_timing']['pending_event_bound'],1)
        self.assertFalse(paced['replay_timing']['timing_verified'])
        paced_map=service.reopen('owner',paced['map_id'])['map']
        self.assertEqual(paced_map,fast_map)
        self.assertIsNone(service.reopen('owner',paced['map_id'])['pose_candidate'])
        self.assertFalse(paced['motion_authorized'])

    def test_cancel_interrupts_long_receipt_wait_without_restarting(self):
        class GapSource(Source):
            def __iter__(self):
                for index,event in enumerate(super().__iter__()):
                    event['receipt_monotonic_ns']+=20_000_000_000 if index else 0
                    yield event
        calls=[]
        def factory(*args):
            calls.append(1);return GapSource(positions=[[0,-.6,.4]]*2)
        service=self.make(factory);started=service.start('owner','a'*32,replay_mode='recorded_1x')['job']
        deadline=time.monotonic()+2
        while service.snapshot('owner')['job']['state']!='REPLAYING_1X' and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertEqual(service.snapshot('owner')['job']['state'],'REPLAYING_1X')
        before=time.monotonic();service.control('owner',started['job_id'],'cancel')
        ended=self.finish(service)
        self.assertLess(time.monotonic()-before,1)
        self.assertEqual(ended['state'],'CANCELLED')
        self.assertIsNone(ended['map_id']);self.assertEqual(len(calls),1)

    def test_invalid_mode_live_origin_backward_and_span_reject(self):
        service=self.make()
        for value in (True,1,None,'speed_up','live'):
            with self.subTest(value=value),self.assertRaises(BrokerError):
                service.start('owner','a'*32,replay_mode=value)
        context=copy.deepcopy(CONTEXT);context['origin']='live_ros'
        service.source_factory=lambda *args:Source(context=context)
        service.start('owner','a'*32,replay_mode='recorded_1x')
        rejected=self.finish(service)
        self.assertEqual(rejected['error'],'RECORDED_REPLAY_ORIGIN_REQUIRED')
        self.assertEqual(rejected['error_stage'],'VERIFY_SOURCE')
        self.assertIsNone(rejected['map_id'])
        pacer=RecordedReplayPacer(10)
        self.assertEqual(pacer.target(100),10)
        self.assertEqual(pacer.target(1_000_000_100),11)
        with self.assertRaisesRegex(ValueError,'BACKWARD'):pacer.target(99)
        with self.assertRaisesRegex(ValueError,'SPAN_BUDGET'):pacer.target(600_000_000_101)
        for receipt in (True,-1,None,1.0):
            with self.assertRaisesRegex(ValueError,'RECEIPT_REQUIRED'):pacer.target(receipt)

    def test_pacing_wait_only_excludes_actual_wait_and_keeps_lateness(self):
        pacer=RecordedReplayPacer(10)
        target=pacer.target(100);pacer.waited(.2);pacer.delivered(target,10.3)
        summary=pacer.summary(11)
        self.assertAlmostEqual(summary['processing_elapsed_s'],.8)
        self.assertAlmostEqual(summary['maximum_lateness_s'],.3)
        self.assertEqual(summary['late_over_200ms_events'],1)
        self.assertEqual(summary['late_over_250ms_events'],1)
        with self.assertRaisesRegex(ValueError,'WALL_CLOCK'):pacer.waited(-1)

    def test_slow_processing_still_expires_not_subtracting_recorded_duration(self):
        clock=[0.]
        class SlowSource(Source):
            def __iter__(self):
                for event in super().__iter__():
                    clock[0]+=61.
                    yield event
        service=self.make(lambda *args:SlowSource(positions=[[0,-.6,.4]]*3))
        service.clock=lambda:clock[0]
        service.start('owner','a'*32,replay_mode='recorded_1x')
        ended=self.finish(service)
        self.assertEqual(ended['state'],'FAILED')
        self.assertEqual(ended['error'],'AUTOMATIC_PROCESSING_TIME_BUDGET')
        self.assertEqual(ended['replay_timing']['pacing_wait_s'],0.)
        self.assertGreater(ended['replay_timing']['processing_elapsed_s'],120.)
        self.assertIsNone(ended['map_id'])
