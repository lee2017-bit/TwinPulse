"""No Kit/device: optional diagnostic sink must not block robot exchange."""
from tests.integration import test_r4_bridge_api as _source_paths
from scripts.twinpulse_live_viewport import LiveViewportPublisher
from threading import Event,Thread,Lock
from types import SimpleNamespace
from unittest.mock import patch
import time
import unittest

class FleetDiagnosticIsolationTests(unittest.TestCase):
    def publisher(self):
        bridge=SimpleNamespace(connected=True,adapter=SimpleNamespace(engine_session_id='engine'),
            _lock=Lock(),_shared_stage_epoch='stage',_post=lambda *args:{'fleet':{'robots':[]}})
        publisher=LiveViewportPublisher(bridge)
        publisher.fleet_report={'applied_revision':'revision','robots':[{'sequence':1}]}
        return publisher
    def test_blocked_diagnostic_writer_does_not_block_exchange_and_queue_is_bounded(self):
        publisher=self.publisher();entered=Event();release=Event()
        def blocked(*args,**kwargs):entered.set();release.wait(2)
        with patch('builtins.print',blocked):
            worker=Thread(target=publisher._fleet_diag_io,daemon=True);worker.start()
            try:
                publisher._fleet_diagnostic('first',time.monotonic(),publisher.fleet_report)
                self.assertTrue(entered.wait(1));started=time.monotonic()
                publisher._fleet_exchange();self.assertLess(time.monotonic()-started,.1)
                for n in range(50):publisher._fleet_diagnostic(str(n),time.monotonic(),publisher.fleet_report)
                self.assertLessEqual(publisher.fleet_diag_queue.qsize(),16);self.assertGreater(publisher.fleet_diag_dropped,0)
            finally:publisher.stop_event.set();release.set();worker.join(1)
    def test_diagnostic_write_exception_is_counted_not_propagated(self):
        publisher=self.publisher()
        def failed(*args,**kwargs):publisher.stop_event.set();raise BrokenPipeError('isolated log sink fault')
        publisher._fleet_diagnostic('first',time.monotonic(),publisher.fleet_report)
        with patch('builtins.print',failed):publisher._fleet_diag_io()
        self.assertEqual(publisher.fleet_diag_write_errors,1)
    def test_same_sequence_early_return_does_not_retimestamp_produced_report(self):
        import sys
        publisher=self.publisher();publisher.fleet_runtime=SimpleNamespace(report=[dict(robot_id='r',sequence=1)],update=lambda _:None,
            navigation_scene=None,scene_produced_at=100.)
        snapshot=SimpleNamespace(engine_session_id='engine',stage_epoch='stage',applied_revision='revision')
        utility=SimpleNamespace(capture_viewport_to_buffer=lambda *args:None,get_active_viewport=lambda:None)
        with patch.dict(sys.modules,{'omni.kit.viewport.utility':utility}):
            with patch('scripts.twinpulse_live_viewport.time.monotonic',return_value=100.):publisher.update(snapshot)
            with patch('scripts.twinpulse_live_viewport.time.monotonic',return_value=130.):publisher.update(snapshot)
            self.assertEqual(publisher.fleet_produced_at,100.);self.assertEqual(publisher.fleet_attempt_at,130.)
            self.assertEqual(publisher.fleet_report['produced_monotonic_s'],100.)
            publisher.fleet_runtime.report=[dict(robot_id='r',sequence=2)]
            with patch('scripts.twinpulse_live_viewport.time.monotonic',return_value=160.):publisher.update(snapshot)
            self.assertEqual(publisher.fleet_produced_at,160.)

if __name__=='__main__':unittest.main()
