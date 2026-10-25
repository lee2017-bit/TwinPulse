# SPDX-License-Identifier: Apache-2.0
"""Diagnostic observations cannot admit, resend or modify product actions."""
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.request_latency import RequestLatencyProbe, observe_operation_phase


class RequestLatencyTests(unittest.TestCase):
    def test_catalog_header_optional_clock_failure_never_sends_partial_diagnostic(self):
        from twinpulse_app.api import LocalApiServer
        from unittest.mock import Mock
        request=SimpleNamespace(_twinpulse_latency_started=1.,_twinpulse_latency_phases={},send_header=Mock())
        for clock in (RuntimeError('optional clock'),float('nan')):
            with self.subTest(clock=clock),patch('twinpulse_app.api.time.perf_counter',side_effect=clock if isinstance(clock,Exception) else None,return_value=clock):
                LocalApiServer._latency_header(request)
        request.send_header.assert_not_called()

    def test_operation_phase_clock_failure_preserves_normal_and_original_error(self):
        from twinpulse_app.command_broker import BrokerError
        request=SimpleNamespace(_twinpulse_latency_phases={})
        for name in ('tp_operation_read','tp_operation_encode','tp_project_catalog'):
            for clock in (RuntimeError('optional clock'), [1.,RuntimeError('optional end clock')]):
                with patch('twinpulse_app.request_latency.time.perf_counter',side_effect=clock):
                    with observe_operation_phase(request,name):value='original success'
                self.assertEqual(value,'original success')
            for original in (BrokerError('original','original read failure',status=409),ValueError('original encoder')):
                with patch('twinpulse_app.request_latency.time.perf_counter',side_effect=RuntimeError('optional clock')):
                    with self.assertRaises(type(original)) as caught:
                        with observe_operation_phase(request,name):raise original
                self.assertIs(caught.exception,original)

    def test_operation_phase_sink_failure_preserves_normal_and_original_error(self):
        class Broken(dict):
            def __setitem__(self,*_):raise OSError('optional phase store')
        request=SimpleNamespace(_twinpulse_latency_phases=Broken())
        with observe_operation_phase(request,'tp_operation_read'):value='original success'
        self.assertEqual(value,'original success')
        original=ValueError('original encode failure')
        with self.assertRaises(ValueError) as caught:
            with observe_operation_phase(request,'tp_operation_encode'):raise original
        self.assertIs(caught.exception,original)

    def test_operation_phase_records_only_finite_known_durations(self):
        request=SimpleNamespace(_twinpulse_latency_phases={})
        with patch('twinpulse_app.request_latency.time.perf_counter',side_effect=[1.,1.025]):
            with observe_operation_phase(request,'tp_operation_read'):pass
        self.assertAlmostEqual(request._twinpulse_latency_phases['tp_operation_read'],25.)
        with patch('twinpulse_app.request_latency.time.perf_counter',side_effect=[1.,float('nan')]):
            with observe_operation_phase(request,'tp_operation_encode'):pass
        self.assertNotIn('tp_operation_encode',request._twinpulse_latency_phases)
        with observe_operation_phase(request,'unsafe;header'):pass
        self.assertNotIn('unsafe;header',request._twinpulse_latency_phases)

    def test_history_reads_have_one_bounded_bucket_and_do_not_log_arbitrary_paths(self):
        now=[0.];events=[]
        probe=RequestLatencyProbe(clock=lambda:now[0],emit=events.append,dump=lambda:None)
        for number in range(20):
            request=SimpleNamespace(command='GET',path='/v1/product/robot-fleet/operations/'+format(number,'032x'))
            probe.begin(request);now[0]+=.3;probe.finish(request);probe._write_once()
        self.assertEqual(len(events),16)
        self.assertEqual(set(probe.observations_by_route),{'GET /v1/product/robot-fleet/operations/:id'})
        self.assertEqual(events[-1]['route'],'GET /v1/product/robot-fleet/operations/:id')
        for path in ('/v1/product/robot-fleet/operations/'+'a'*32+'?secret=NO',
                     '/v1/product/robot-fleet/operations/private-name',
                     '/v1/product/robot-fleet/operations/'+'a'*32+'/evidence/receipt.json'):
            request.path=path;probe.begin(request)
            self.assertFalse(hasattr(request,'_twinpulse_latency_route'))
            self.assertFalse(hasattr(request,'_twinpulse_latency_started'))
            probe.finish(request)

    def test_bound_stage_gc_and_pending_stack_without_headers_or_bodies(self):
        now=[1.];events=[];dumps=[]
        probe=RequestLatencyProbe(clock=lambda:now[0],emit=events.append,dump=lambda:dumps.append(True))
        request=SimpleNamespace(command='GET',path='/v1/product/viewport',
            headers={'Authorization':'NEVER_COPY_THIS'},body='NEVER_COPY_BODY',
            _twinpulse_context_id='context',_twinpulse_project_id='project')
        probe.begin(request);now[0]=1.1;probe._gc('start',{'generation':2})
        now[0]=1.3;probe._gc('stop',{'generation':2});probe._watch_once();probe._watch_once()
        self.assertEqual(len(dumps),1)
        request._twinpulse_latency_phases['tp_view_wait']=190
        probe.finish(request)
        probe._write_once();probe._write_once()
        self.assertEqual(events[-1]['gc'],[{'generation':2,'elapsed_ms':200.}])
        self.assertEqual(events[-1]['project_id'],'project')
        self.assertEqual(events[-1]['phases_ms'],{'tp_view_wait':190})
        self.assertNotIn('NEVER_COPY',str(events));self.assertEqual(probe.requests,{})

    def test_ignore_other_routes_and_do_not_turn_sink_failure_into_product_error(self):
        now=[0.]
        def failed(_):raise OSError('optional unavailable')
        probe=RequestLatencyProbe(clock=lambda:now[0],emit=failed,dump=lambda:None)
        unrelated=SimpleNamespace(command='POST',path='/v1/product/unrelated')
        probe.begin(unrelated);self.assertFalse(hasattr(unrelated,'_twinpulse_latency_started'))
        request=SimpleNamespace(command='GET',path='/v1/product/viewport/current')
        probe.begin(request);now[0]=1.;probe._watch_once();probe.finish(request)
        self.assertEqual(probe.requests,{})

    def test_fleet_diagnostics_renew_bounded_window_without_copying_payload(self):
        now=[0.];events=[];dumps=[]
        probe=RequestLatencyProbe(clock=lambda:now[0],emit=events.append,dump=lambda:dumps.append(True))
        for method in ('GET','POST'):
            for _ in range(20):
                request=SimpleNamespace(command=method,path='/v1/product/robot-fleet',
                    headers={'Authorization':'NEVER_COPY_SECRET'},body='NEVER_COPY_BODY')
                probe.begin(request)
                request._twinpulse_error_references={'request_id':'b'*32,'private':'NEVER_COPY_PRIVATE','operation_id':'NOT_AN_ID'}
                now[0]+=.3;probe.finish(request);probe._write_once()
            self.assertEqual(probe.observations_by_route[method+' /v1/product/robot-fleet'],16)
        self.assertEqual(len(events),32)
        now[0]=80.;probe.begin(request)
        self.assertFalse(hasattr(request,'_twinpulse_error_references'))
        request._twinpulse_error_references={'request_id':'b'*32}
        now[0]+=.3;probe._watch_once();probe.finish(request)
        while not probe.records.empty():probe._write_once()
        self.assertEqual(probe.observations_by_route['POST /v1/product/robot-fleet'],1)
        self.assertEqual(events[-1]['references'],{'request_id':'b'*32})
        self.assertTrue(dumps);self.assertNotIn('NEVER_COPY',str(events))

    def test_first_connection_accept_and_read_are_not_relabelled_on_keepalive(self):
        now=[2.]
        probe=RequestLatencyProbe(clock=lambda:now[0],emit=lambda _:None)
        request=SimpleNamespace(command='GET',path='/v1/product/viewport',connection=None,
            server=SimpleNamespace(request_admission=lambda _:(1.,1000.,1.2)))
        probe.begin(request)
        self.assertAlmostEqual(request._twinpulse_latency_phases['tp_accept_wait'],200)
        self.assertAlmostEqual(request._twinpulse_latency_phases['tp_first_read'],800)
        self.assertEqual(request._twinpulse_accepted_at_ms,1000.)
        probe.finish(request);now[0]=3.;probe.begin(request)
        self.assertEqual(request._twinpulse_latency_phases,{})
        self.assertFalse(hasattr(request,'_twinpulse_accepted_at_ms'))
        probe.finish(request)
        request.path='/v1/product/unrelated';probe.begin(request)
        self.assertFalse(hasattr(request,'_twinpulse_latency_started'));probe.finish(request)

    def test_slow_diagnostic_sink_never_blocks_request_finish_and_queue_is_bounded(self):
        from threading import Event,Thread
        now=[0.];entered=Event();release=Event()
        def slow(_):entered.set();release.wait(2)
        probe=RequestLatencyProbe(clock=lambda:now[0],emit=slow)
        probe._enqueue({'kind':'fixture'})
        writer=Thread(target=probe._write_once,daemon=True);writer.start()
        self.assertTrue(entered.wait(1))
        try:
            for _ in range(40):
                request=SimpleNamespace(command='GET',path='/v1/product/viewport')
                probe.begin(request);now[0]+=.2;probe.finish(request)
            self.assertEqual(probe.requests,{})
            self.assertLessEqual(probe.records.qsize(),16)
            self.assertEqual(probe.observations,16)
        finally:release.set();writer.join(1)

    def test_error_references_survive_cached_body_consumption_without_payload(self):
        from twinpulse_app.api import LocalApiServer
        request=SimpleNamespace(_twinpulse_saved_json={'request_id':'b'*32,
            'operation_id':'c'*32,'private':'MUST_NOT_KEEP'})
        value=LocalApiServer._read_json(LocalApiServer.__new__(LocalApiServer),request)
        self.assertEqual(value['private'],'MUST_NOT_KEEP')
        self.assertFalse(hasattr(request,'_twinpulse_saved_json'))
        self.assertEqual(request._twinpulse_error_references,{'request_id':'b'*32,'operation_id':'c'*32})

    def test_state_routes_have_independent_bounded_observations_and_exact_read_uuid(self):
        now=[0.];events=[];probe=RequestLatencyProbe(clock=lambda:now[0],emit=events.append,dump=lambda:None)
        for _ in range(16):
            request=SimpleNamespace(command='GET',path='/v1/product/viewport');probe.begin(request);now[0]+=.2;probe.finish(request);probe._write_once()
        identity='c96319ec-7e3c-4c39-8b95-253177ee548a'
        for route in ('/v1/product/workflow','/v1/product/conversation'):
            request=SimpleNamespace(command='GET',path=route,headers={'X-TwinPulse-Read-ID':identity,'Authorization':'NEVER_COPY_SECRET'})
            probe.begin(request);now[0]+=.4;probe._watch_once();probe.finish(request)
            while not probe.records.empty():probe._write_once()
            self.assertEqual(events[-1]['read_id'],identity);self.assertEqual(events[-1]['route'],'GET '+route)
        self.assertEqual(probe.observations,18);self.assertNotIn('NEVER_COPY_SECRET',str(events))
        self.assertTrue(all(v<=16 for v in probe.observations_by_route.values()))


if __name__=='__main__':unittest.main()
