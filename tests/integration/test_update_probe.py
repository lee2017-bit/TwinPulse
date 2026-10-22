# SPDX-License-Identifier: Apache-2.0
"""Read-only Kit diagnostics, no Isaac/renderer/device import."""
import gc
import time
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from threading import Lock
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from twinpulse_update_probe import UpdateProbe

class ProbeTests(unittest.TestCase):
    def test_optional_cpu_failure_never_masks_original_update_or_normal_return(self):
        for fail_body in (False,True):
            with self.subTest(fail_body=fail_body):
                probe=UpdateProbe();self.addCleanup(probe.close);original=ValueError('original app update')
                def update():
                    probe.begin()
                    try:
                        if fail_body:raise original
                        return 'normal update'
                    finally:probe.finish(.9,'ValueError' if fail_body else None)
                with patch('twinpulse_update_probe.time.thread_time',side_effect=OSError('optional CPU read')),patch('twinpulse_update_probe.time.process_time',side_effect=OSError('optional CPU read')):
                    if fail_body:
                        with self.assertRaises(ValueError) as caught:update()
                        self.assertIs(caught.exception,original)
                    else:self.assertEqual(update(),'normal update')
                self.assertGreaterEqual(probe.diagnostic_errors,4)
                row=probe.snapshot()['phases'][-1];self.assertEqual(row['error_type'],'ValueError' if fail_body else None)
                self.assertIn('gc_pause_s',row);self.assertNotIn('thread_cpu_s',row)

    def test_app_update_keeps_cpu_and_before_after_working_set_separate(self):
        probe=UpdateProbe();self.addCleanup(probe.close)
        probe._memory=Mock(side_effect=[dict(page_fault_count=10,process_working_set_mib=2),dict(page_fault_count=20,process_working_set_mib=3),{}])
        probe.begin();row=probe.finish(.9)
        self.assertEqual(row['page_fault_delta'],10);self.assertEqual(row['before_resources']['process_working_set_mib'],2)
        self.assertEqual(row['process_working_set_mib'],3);self.assertGreaterEqual(row['thread_cpu_s'],0);self.assertGreaterEqual(row['process_cpu_s'],0)

    def test_tail_gc_and_other_thread_gc_are_not_lost_at_next_app_begin(self):
        probe=UpdateProbe();self.addCleanup(probe.close)
        with probe.phase('tail_idle'):
            with patch('twinpulse_update_probe.threading.get_ident',return_value=probe.thread+1):
                probe._gc('start',{});probe.process_gc_started-=.7;probe._gc('stop',{})
        row=probe.snapshot()['worst_by_phase']['tail_idle']
        self.assertAlmostEqual(row['process_gc_pause_s'],.7,places=6);self.assertEqual(row['gc_pause_s'],0.)
        self.assertGreaterEqual(row['thread_cpu_s'],0.)
        for i in range(100):probe._phase_record('app_update',10+i,.001)
        self.assertEqual(probe.snapshot()['worst_by_phase']['tail_idle'],row)

    def test_gc_cycle_keeps_original_collector_identity_generation_and_bounded_stack(self):
        probe=UpdateProbe(record_gc_cycles=True);self.addCleanup(probe.close)
        with probe.phase('tail_idle'):
            with patch('twinpulse_update_probe.threading.get_ident',return_value=probe.thread+1):
                probe._gc('start',{'generation':2})
                probe._gc('stop',{'generation':2,'collected':3,'uncollectable':0})
        row=probe.snapshot()['gc_cycles']['recent'][-1]
        self.assertEqual(row['generation'],2)
        self.assertFalse(row['collector_is_kit_thread'])
        self.assertEqual(row['kit_phase_at_start'],'tail_idle')
        self.assertEqual(row['collected'],3)
        self.assertEqual(row['uncollectable'],0)
        self.assertGreaterEqual(row['elapsed_s'],0)
        self.assertGreaterEqual(row['collector_thread_cpu_s'],0)
        self.assertLessEqual(len(row['stack']),8)
        self.assertTrue(row['stack'])
        self.assertTrue(all(set(r)=={'file','function','line'} and '/' not in r['file'] and '\\' not in r['file'] for r in row['stack']))
        row['stack'][0]['function']='changed'
        self.assertNotEqual(probe.snapshot()['gc_cycles']['recent'][-1]['stack'][0]['function'],'changed')

    def test_gc_cycle_ledger_is_bounded_and_never_changes_collection_policy(self):
        probe=UpdateProbe(record_gc_cycles=True);self.addCleanup(probe.close)
        before=(gc.isenabled(),gc.get_threshold())
        for i in range(70):
            probe._gc('start',{'generation':i%3})
            probe._gc('stop',{'generation':i%3,'collected':i,'uncollectable':0})
        value=probe.snapshot()['gc_cycles']
        self.assertLessEqual(len(value['recent']),32)
        self.assertGreaterEqual(value['completed'],70)
        self.assertIsNotNone(value['first'])
        self.assertIsNotNone(value['worst'])
        self.assertEqual((gc.isenabled(),gc.get_threshold()),before)

    def test_gc_diagnostic_failure_cannot_escape_callback_or_mask_body(self):
        probe=UpdateProbe(record_gc_cycles=True);self.addCleanup(probe.close)
        with patch('twinpulse_update_probe.sys._getframe',side_effect=RuntimeError('optional stack unavailable')):
            with self.assertRaisesRegex(ValueError,'ORIGINAL'):
                with probe.phase('tail_idle'):
                    probe._gc('start',{'generation':2})
                    probe._gc('stop',{'generation':2,'collected':0,'uncollectable':0})
                    raise ValueError('ORIGINAL')
        self.assertGreater(probe.diagnostic_errors,0)

    def test_gc_slow_motion_cycle_survives_larger_startup_and_normal_ring_churn(self):
        probe=UpdateProbe(record_gc_cycles=True);self.addCleanup(probe.close)
        clock=[10.]
        def cycle(elapsed,generation=2):
            probe._gc('start',{'generation':generation});clock[0]+=elapsed
            probe._gc('stop',{'generation':generation,'collected':0,'uncollectable':0})
        with patch('twinpulse_update_probe.time.monotonic',side_effect=lambda:clock[0]):
            cycle(2.)
            with probe.phase('tail_idle'):cycle(.563)
            for _ in range(80):cycle(.001,0)
        v=probe.snapshot()['gc_cycles']
        self.assertEqual(v['worst']['elapsed_s'],2.)
        self.assertAlmostEqual(v['recent_slow'][-1]['elapsed_s'],.563)
        self.assertEqual(v['recent_slow'][-1]['kit_phase_at_start'],'tail_idle')
        self.assertTrue(all(r['generation']==0 for r in v['recent']))

    def test_only_explicit_host_probe_collects_stack_and_pairing_mismatch_is_unknown(self):
        host=UpdateProbe(record_gc_cycles=True);self.addCleanup(host.close)
        viewport=UpdateProbe();self.addCleanup(viewport.close)
        with patch('twinpulse_update_probe.UpdateProbe._gc_stack',return_value=[]) as stack:
            host._gc('start',{'generation':2});viewport._gc('start',{'generation':2})
            host._gc('stop',{'generation':1,'collected':0,'uncollectable':0})
            viewport._gc('stop',{'generation':2,'collected':0,'uncollectable':0})
        self.assertEqual(stack.call_count,1)
        row=host.snapshot()['gc_cycles']['recent'][-1]
        self.assertEqual(row['pairing'],'UNKNOWN_OR_MISMATCHED')
        self.assertNotIn('collector_thread_cpu_s',row)
        self.assertFalse(viewport.snapshot()['gc_cycles']['enabled'])
        self.assertEqual(viewport.snapshot()['gc_cycles']['completed'],0)
        self.assertGreaterEqual(viewport.process_gc_total,0)

    def test_nested_phase_tuple_restores_after_body_and_copy_failure(self):
        probe=UpdateProbe(record_gc_cycles=True);self.addCleanup(probe.close)
        before=probe.kit_phase
        scope=probe.phase('host_tail');scope.__enter__();outer=probe.kit_phase
        with self.assertRaisesRegex(ValueError,'INNER'):
            with probe.phase('tail_idle'):raise ValueError('INNER')
        self.assertEqual(probe.kit_phase,outer)
        original=ValueError('ORIGINAL')
        with patch('twinpulse_update_probe.deepcopy',side_effect=OSError('optional diagnostic copy')) as copy:
            self.assertFalse(scope.__exit__(ValueError,original,None))
            self.assertGreater(copy.call_count,0)
        self.assertEqual(str(original),'ORIGINAL')
        self.assertEqual(probe.kit_phase,before)

    def test_app_update_phase_restores_outer_tuple_even_when_finish_diagnostic_fails(self):
        probe=UpdateProbe(record_gc_cycles=True);self.addCleanup(probe.close)
        with probe.phase('outer'):
            outer=probe.kit_phase
            probe.begin()
            self.assertEqual(probe.kit_phase[0],'app_update')
            with patch.object(probe,'_phase_record',side_effect=OSError('optional phase storage')):
                with self.assertRaisesRegex(ValueError,'ORIGINAL APP'):
                    try:raise ValueError('ORIGINAL APP')
                    finally:probe.finish(.9,'ValueError')
            self.assertEqual(probe.kit_phase,outer)
        self.assertGreater(probe.diagnostic_errors,0)

    def test_same_slow_tail_keeps_its_child_phases_and_branch_context(self):
        probe=UpdateProbe();self.addCleanup(probe.close);context=dict(frame=99,frame_mod10=9,capture_finished=True)
        with probe.phase('host_tail',context=context):
            with probe.phase('tail_idle'):time.sleep(.26)
        context['frame']=100
        for i in range(100):probe._phase_record('app_update',10+i,.001)
        row=probe.snapshot()['worst_by_phase']['host_tail']
        self.assertEqual(row['context']['frame'],99)
        self.assertEqual([r['phase'] for r in row['child_phases']],['tail_idle'])
        self.assertGreaterEqual(row['child_phases'][0]['elapsed_s'],.25)
        self.assertLess(row['child_phases'][0]['thread_cpu_s'],.1)

    def test_slow_child_copy_failure_never_breaks_body_or_masks_original(self):
        for fail_body in (False,True):
            with self.subTest(fail_body=fail_body):
                probe=UpdateProbe();self.addCleanup(probe.close)
                scope=probe.phase('host_tail',context=dict(frame=99));scope.__enter__()
                with probe.phase('tail_idle'):time.sleep(.26)
                original=ValueError('ORIGINAL') if fail_body else None
                with patch('twinpulse_update_probe.deepcopy',side_effect=OSError('diagnostic copy')):
                    # contextmanager.__exit__ returns False for the unchanged
                    # original body exception, so the caller propagates it.
                    self.assertFalse(scope.__exit__(ValueError if fail_body else None,original,None))
                self.assertGreater(probe.diagnostic_errors,0)

    def test_failed_http_keeps_elapsed_and_original_capture_subphases_after_stdout_budget(self):
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        clock=[10.]
        bridge=SimpleNamespace(connected=True,_lock=Lock(),_shared_stage_epoch='stage',
            adapter=SimpleNamespace(engine_session_id='engine'))
        def fail(*_):clock[0]+=.6;raise TimeoutError('original transport')
        bridge._post=fail
        publisher=LiveViewportPublisher(bridge);self.addCleanup(publisher.stop)
        publisher.render_epoch=1;publisher.viewport_diag_count=32
        publisher.raw=({'frame_id':7,'captured_at_ms':10000,'stage_epoch':'stage'},1,1,b'\x00\x00\x00\xff',1)
        publisher.capture_phases[7]={'scheduled_s':9.8,'callback_s':9.9}
        publisher.stop_event=Mock();publisher.stop_event.wait.side_effect=[False,True]
        with patch('scripts.twinpulse_live_viewport.time.monotonic',side_effect=lambda:clock[0]),patch('scripts.twinpulse_live_viewport.time.time',return_value=10.):
            publisher._io()
        value=publisher.diagnostic_snapshot()
        self.assertAlmostEqual(value['latest_io']['http_ms'],600)
        self.assertFalse(value['latest_io']['http_completed'])
        self.assertAlmostEqual(value['latest_io']['callback_ms'],100)
        self.assertAlmostEqual(value['latest_io']['raw_wait_ms'],100)
        self.assertEqual(value['latest_io']['captured_at_ms'],10000)
        self.assertEqual(value['latest_io']['error'],'viewport_transport_TimeoutError')
        self.assertIsNone(value['active_io']);self.assertTrue(publisher.fleet_diag_queue.empty())
        value['latest_io']['frame_id']=99
        self.assertEqual(publisher.diagnostic_snapshot()['latest_io']['frame_id'],7)

    def test_stop_retains_join_status_and_last_return_without_claiming_pending_io_finished(self):
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        publisher=LiveViewportPublisher(Mock());self.addCleanup(publisher.stop)
        thread=Mock();thread.is_alive.return_value=True
        def joined(**_):publisher.viewport_latest={'http_ms':6500,'http_completed':False}
        thread.join.side_effect=joined;publisher.thread=thread
        publisher.viewport_active={'frame_id':7,'entered_monotonic_s':10.,'stage':'http'}
        publisher.stop();value=publisher.diagnostic_snapshot()
        self.assertTrue(value['join_status']['viewport_alive'])
        self.assertEqual(value['active_io']['frame_id'],7)
        self.assertEqual(value['latest_io']['http_ms'],6500)

    def test_first_long_phase_survives_more_than_32_reports_and_final_ring(self):
        probe=UpdateProbe();self.addCleanup(probe.close)
        probe._memory=lambda:{'page_fault_count':42,'available_ram_mib':700}
        probe._phase_record('capture_schedule',10.,6.53)
        for i in range(100):probe._phase_record('fleet_update',11.+i,.001)
        final=probe.snapshot()
        self.assertEqual(final['retained'],64);self.assertEqual(final['phase_count'],101)
        self.assertEqual(final['first_stall']['phase'],'capture_schedule')
        self.assertEqual(final['worst_phase']['elapsed_s'],6.53)
        self.assertEqual(final['recent_stalls'][0]['elapsed_s'],6.53)
        self.assertEqual(final['first_stall']['available_ram_mib'],700)
        self.assertEqual(final['first_stall']['entered_monotonic_s'],10.)
        final['first_stall']['phase']='changed';self.assertEqual(probe.snapshot()['first_stall']['phase'],'capture_schedule')

    def test_diagnostic_failure_preserves_original_exception_and_close_removes_callback(self):
        probe=UpdateProbe()
        def fail():raise OSError('diagnostic unavailable')
        probe._memory=fail
        try:
            probe.begin();probe.finish(.5)
            with self.assertRaisesRegex(ValueError,'ORIGINAL'):
                with probe.phase('app_update'):raise ValueError('ORIGINAL')
            self.assertGreater(probe.snapshot()['diagnostic_errors'],0)
        finally:probe.close()
        self.assertNotIn(probe._gc,gc.callbacks)

if __name__=='__main__':unittest.main()
