# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Display contracts, not actual Isaac or physics acceptance."""
import base64
import json
from io import BytesIO
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from threading import Lock

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from PIL import Image
from twinpulse_app.viewport_service import ViewportService
from twinpulse_app.command_broker import BrokerError
from tests.integration.test_r4_bridge_api import R4ApiTests


class ViewportTests(unittest.TestCase):
    def test_top_view_orbit_restores_oblique_direction_and_current_zoom_distance(self):
        from scripts.twinpulse_live_viewport import orbit_offset
        import math
        self.assertEqual(orbit_offset([3,4,12]),[3,4,12])
        for previous in ([3,4,12],None,[0,0,12],[float('nan'),1,1]):
            result=orbit_offset([0,0,9],previous)
            self.assertAlmostEqual(math.sqrt(sum(v*v for v in result)),9)
            self.assertGreater(math.hypot(result[0],result[1]),.01)
        self.assertAlmostEqual(orbit_offset([0,0,9],[3,4,12])[0],27/13)

    def test_basic_image_plugins_are_initialized_before_first_frame(self):
        with patch('twinpulse_app.viewport_service.Image.preinit') as warm:
            ViewportService(Mock())
        warm.assert_called_once_with()
    def test_diagnostic_shutdown_explicitly_wakes_queue_without_waiting_for_timeout(self):
        from queue import Queue
        from threading import Event, Thread
        from types import SimpleNamespace
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        entered=Event()
        class WaitingQueue(Queue):
            def get(self,*args,**kwargs):
                # Controlled no-device wait: a Stop event alone cannot wake a
                # queue consumer. Only a real queue item releases this wait.
                entered.set()
                return super().get()
        publisher=LiveViewportPublisher(SimpleNamespace())
        publisher.fleet_diag_queue=WaitingQueue()
        with patch('builtins.print') as printed:
            publisher.fleet_diag_thread=Thread(target=publisher._fleet_diag_io,daemon=True)
            publisher.fleet_diag_thread.start();self.assertTrue(entered.wait(1))
            try:
                publisher.stop()
                self.assertFalse(publisher.diagnostic_snapshot()['join_status']['diagnostic_alive'])
                printed.assert_not_called()  # Stop must not write a fetched stale item.
            finally:
                if publisher.fleet_diag_thread.is_alive():
                    publisher.fleet_diag_queue.put({})
                    publisher.fleet_diag_thread.join(1)

    def test_diagnostic_blocked_stdout_and_full_queue_still_fail_handoff(self):
        from queue import Queue
        from threading import Event, Thread
        from types import SimpleNamespace
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        entered,release=Event(),Event()
        publisher=LiveViewportPublisher(SimpleNamespace())
        publisher.fleet_diag_queue=Queue(maxsize=1)
        publisher.fleet_diag_queue.put({'diagnostic_kind':'viewport'})
        def blocked(*args,**kwargs):entered.set();release.wait(2)
        with patch('builtins.print',side_effect=blocked):
            publisher.fleet_diag_thread=Thread(target=publisher._fleet_diag_io,daemon=True)
            publisher.fleet_diag_thread.start();self.assertTrue(entered.wait(1))
            publisher.fleet_diag_queue.put({'diagnostic_kind':'viewport'})
            try:
                publisher.stop()
                self.assertTrue(publisher.diagnostic_snapshot()['join_status']['diagnostic_alive'])
                self.assertTrue(publisher.fleet_diag_queue.full())
            finally:
                release.set();publisher.fleet_diag_thread.join(1)

    def test_diagnostic_wake_join_probe_errors_do_not_skip_other_cleanup(self):
        from types import SimpleNamespace
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        publisher=LiveViewportPublisher(SimpleNamespace())
        probe_close=publisher.phase_probe.close
        publisher.phase_probe.close=Mock(side_effect=OSError('optional probe close'))
        publisher.fleet_diag_queue.put_nowait=Mock(side_effect=RuntimeError('wake failed'))
        publisher.thread=SimpleNamespace(join=Mock(side_effect=ValueError('join failed')),is_alive=lambda:False)
        fleet_join=Mock();publisher.fleet_thread=SimpleNamespace(join=fleet_join,is_alive=lambda:False)
        scan_close=Mock(return_value=dict(closed=True,worker_alive=False,cleanup_errors=[]))
        publisher.fleet_runtime.close=scan_close
        cancel=Mock();publisher.capture_wait=SimpleNamespace(done=lambda:False,cancel=cancel)
        try:
            publisher.stop()
            fleet_join.assert_called_once_with(timeout=3.);scan_close.assert_called_once();cancel.assert_called_once()
            owners={r['owner'] for r in publisher.diagnostic_snapshot()['join_status']['cleanup_errors']}
            self.assertEqual(owners,{'viewport_probe','viewport_diagnostic_wake','viewport_join'})
        finally:probe_close()

    def test_diagnostic_print_failure_remains_visible_and_worker_can_stop(self):
        from queue import Queue
        from threading import Thread
        from types import SimpleNamespace
        import time
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        publisher=LiveViewportPublisher(SimpleNamespace());publisher.fleet_diag_queue=Queue()
        publisher.fleet_diag_queue.put({'diagnostic_kind':'viewport'})
        with patch('builtins.print',side_effect=OSError('log write failed')):
            publisher.fleet_diag_thread=Thread(target=publisher._fleet_diag_io,daemon=True)
            publisher.fleet_diag_thread.start()
            until=time.monotonic()+1
            while publisher.fleet_diag_write_errors!=1 and time.monotonic()<until:time.sleep(.001)
            try:
                self.assertEqual(publisher.fleet_diag_write_errors,1)
                publisher.stop();self.assertFalse(publisher.diagnostic_snapshot()['join_status']['diagnostic_alive'])
            finally:
                publisher.stop_event.set();publisher.fleet_diag_queue.put({});publisher.fleet_diag_thread.join(1)

    def test_prior_transport_failure_cannot_relabel_next_jpeg_or_discarded_frame(self):
        from types import SimpleNamespace
        import time
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        for second in ('jpeg','discard'):
            with self.subTest(second=second):
                prior=dict(phase='request_connect_or_send',reused=True,error_type='TimeoutError',errno=10060,winerror=None)
                bridge=SimpleNamespace(connected=True,_lock=Lock(),_shared_stage_epoch='stage',adapter=SimpleNamespace(engine_session_id='engine'),
                    viewport_transport_error=Mock(return_value=prior))
                publisher=LiveViewportPublisher(bridge);publisher.render_epoch=1
                publisher.stop_event=SimpleNamespace(wait=Mock(side_effect=[False,False,True]),set=Mock())
                def raw(number,epoch=1):return (dict(frame_id=number,captured_at_ms=time.time()*1000,stage_epoch='stage',engine_session_id='engine'),1,1,b'\x00'*4,epoch)
                publisher.raw=raw(1)
                def timeout(*args,**kwargs):
                    publisher.raw=raw(2,2 if second=='discard' else 1)
                    raise TimeoutError('prior transport')
                bridge._post=Mock(side_effect=timeout);original=Image.frombytes;calls=[]
                def image(*args,**kwargs):
                    calls.append(1)
                    if len(calls)==2:raise OSError('new jpeg failure')
                    return original(*args,**kwargs)
                try:
                    with patch.object(Image,'frombytes',side_effect=image):publisher._io_loop()
                    latest=publisher.diagnostic_snapshot()['latest_io']
                    self.assertEqual(latest['frame_id'],2);self.assertIsNone(latest['transport_detail'])
                    self.assertEqual(latest['error'],'viewport_transport_OSError' if second=='jpeg' else None)
                    bridge._post.assert_called_once();bridge.viewport_transport_error.assert_called_once()
                finally:publisher.stop()

    def test_viewport_owner_close_failure_does_not_mask_body_and_is_in_handoff(self):
        from types import SimpleNamespace
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        bridge=SimpleNamespace(close_viewport_channel=Mock(side_effect=OSError('close failure')),viewport_cleanup_error=lambda:None)
        publisher=LiveViewportPublisher(bridge)
        publisher._io_loop=Mock(side_effect=ValueError('original loop failure'))
        with self.assertRaisesRegex(ValueError,'original loop failure'):publisher._io()
        publisher.stop()
        self.assertEqual(publisher.diagnostic_snapshot()['join_status']['cleanup_errors'],[dict(owner='viewport_http',error='OSError')])

    def test_surface_scan_requires_finite_model_height(self):
        packet=self.frame();packet['frame']['lidar_overlay']=dict(robot_id='a',origin_uv=[.5,.5],points_uv=[[.1,.2]],
            captured_at_ms=100000,source='isaac_usd_surface_rays',height_m=.182,connection_epoch='epoch',motion_epoch='motion',physical_authority=False)
        self.service.exchange('engine','stage',packet)
        self.assertEqual(self.service.status()['frame']['lidar_overlay']['height_m'],.182)
        for height in (None,float('nan'),-1,3):
            row=self.frame(2);row['frame']['lidar_overlay']={**packet['frame']['lidar_overlay'],'height_m':height}
            with self.assertRaisesRegex(BrokerError,'frame-bound SIM scan'):self.service.exchange('engine','stage',row)
    def test_maximum_visual_metadata_fits_original_atomic_receipt_without_static_scan_duplication(self):
        packet=self.frame();uv=[.12345678901234567,.8765432109876543]
        packet['frame']['robot_anchors']=[dict(robot_id=str(i)+'a'*98,screen_anchor_uv=uv,screen_bounds_uv=[*uv,.99,.99],visible=True) for i in range(16)]
        packet['frame']['lidar_overlay']=dict(robot_id='a'*100,origin_uv=uv,points_uv=[uv]*90,captured_at_ms=100000,source='isaac_usd_surface_rays',height_m=.182,connection_epoch='a'*100,motion_epoch='b'*100,physical_authority=False)
        packet['frame']['alignment_overlay']=dict(review_id='a'*32,source='CURRENT',body_bounds_uv=[*uv,.99,.99],origin_uv=uv,
            points_uv=[uv]*180,original_captured_at_ms=100000,physical_authority=False)
        self.service.exchange('engine','stage',packet)
        state=self.service.status();header=json.dumps(state)
        self.assertLessEqual(len(header.encode()),8192)
        self.assertNotIn('lidar_overlay',state['last_frame']);self.assertNotIn('robot_anchors',state['last_frame'])
        self.assertNotIn('alignment_overlay',state['last_frame'])
        self.assertLessEqual(len(state['frame']['alignment_overlay']['points_uv']),40)
        self.assertEqual(len(self.service.latest['alignment_overlay']['points_uv']),180)
        self.assertEqual(state['frame']['captured_at_ms'],100000)
        self.assertEqual(self.service.latest['lidar_overlay']['points_uv'][0],uv)
        self.assertLess(abs(state['frame']['lidar_overlay']['points_uv'][0][0]-uv[0])*1280,.002)
    def test_scan_overlay_is_frame_bound_bounded_and_not_physical_authority(self):
        packet=self.frame();packet['frame']['lidar_overlay']=dict(robot_id='a',origin_uv=[.5,.5],points_uv=[[.1,.2]],
            captured_at_ms=100000,source='isaac_usd_aabb_rays',physical_authority=False)
        self.service.exchange('engine','stage',packet)
        self.assertEqual(self.service.status()['frame']['lidar_overlay']['points_uv'],[[.1,.2]])
        for patch in (dict(captured_at_ms=99000),dict(physical_authority=True),dict(points_uv=[[2.,0.]]),dict(points_uv=[[0.,0.]]*91)):
            row=self.frame(2);row['frame']['lidar_overlay']={**packet['frame']['lidar_overlay'],**patch}
            with self.assertRaisesRegex(BrokerError,'frame-bound SIM scan'):
                self.service.exchange('engine','stage',row)
    def test_alignment_header_budget_includes_long_ids_and_all_visual_layers(self):
        self.engine.update(engine_session_id='e'*160,stage_epoch='s'*160,snapshot={'applied_revision':'r'*160})
        packet=self.frame();packet.update(engine_session_id='e'*160,stage_epoch='s'*160)
        packet['frame']['applied_revision']='r'*160;uv=[.12345678901234567,.8765432109876543]
        packet['frame']['robot_anchors']=[dict(robot_id=str(i)+'a'*98,screen_anchor_uv=uv,screen_bounds_uv=[*uv,.99,.99],visible=True) for i in range(16)]
        packet['frame']['lidar_overlay']=dict(robot_id='a'*100,origin_uv=uv,points_uv=[uv]*90,captured_at_ms=100000,source='isaac_usd_surface_rays',height_m=.182,connection_epoch='a'*100,motion_epoch='b'*100,physical_authority=False)
        packet['frame']['alignment_overlay']=dict(review_id='a'*32,source='CURRENT',body_bounds_uv=[*uv,.99,.99],origin_uv=uv,points_uv=[uv]*180,original_captured_at_ms=100000,physical_authority=False)
        self.service.exchange('e'*160,'s'*160,packet);self.service.camera_result=dict(request_id='😀'*80,state='completed',code='😀'*80)
        state=self.service.status();self.assertLessEqual(len(json.dumps(state,ensure_ascii=True,separators=(',',':')).encode('ascii')),8000)
        self.assertEqual(len(self.service.latest['alignment_overlay']['points_uv']),180)
    def setUp(self):
        self.now=100.
        self.broker=Mock()
        self.broker.diagnostics=None
        self.engine={'engine_connected':True,'engine_session_id':'engine','stage_epoch':'stage',
                     'snapshot':{'applied_revision':'revision'}}
        self.broker.supervisor_state.side_effect=lambda:self.engine
        self.service=ViewportService(self.broker,clock=lambda:self.now,wall_clock=lambda:self.now)
        output=BytesIO();Image.new('RGB',(64,64),'blue').save(output,format='JPEG')
        self.image=output.getvalue()
    def frame(self,seq=1,**kw):
        frame={'frame_id':seq,'applied_revision':'revision','captured_at_ms':self.now*1000,'width':64,'height':64,
               'camera_sequence':0,'jpeg_base64':base64.b64encode(self.image).decode()}
        frame.update(kw)
        return {'engine_session_id':'engine','stage_epoch':'stage','frame':frame,'camera_result':None}
    def test_latest_only_not_persisted_and_stale_removed(self):
        for i in range(1,6):
            self.service.exchange('engine','stage',self.frame(i));self.now+=.15
        state=self.service.status();self.assertEqual(state['state'],'live');self.assertFalse(state['physical_authority'])
        self.assertNotIn('jpeg_base64',state['frame']);self.assertEqual(self.service.image('5'),self.image)
        with self.assertRaises(BrokerError):self.service.image('1')
        self.now+=1.1;self.assertIsNone(self.service.status()['frame'])
        with self.assertRaises(BrokerError):self.service.image('5')
    def test_replaced_engine_or_geometry_hides_previous_image(self):
        self.service.exchange('engine','stage',self.frame())
        self.engine['snapshot']['applied_revision']='new'
        self.assertIsNone(self.service.status()['frame'])
        with self.assertRaises(BrokerError):self.service.exchange('engine','stage',self.frame(2))
        self.engine['engine_connected']=False
        self.assertIsNone(self.service.status()['frame'])
    def test_last_preview_survives_stale_and_revision_change_without_camera_authority(self):
        self.service.exchange('engine','stage',self.frame())
        digest=self.service.status()['last_frame']['sha256']
        self.now+=2
        state=self.service.status()
        self.assertIsNone(state['frame']);self.assertTrue(state['last_frame']['preview_only'])
        self.assertEqual(self.service.preview_image(digest),self.image)
        with self.assertRaises(BrokerError):
            self.service.camera_action(dict(request_id='old',frame_id=1,action='orbit_left'))
        self.engine['snapshot']['applied_revision']='new'
        self.assertEqual(self.service.status()['last_frame']['applied_revision'],'revision')
        self.assertIsNone(self.service.status()['frame'])
        other=ViewportService(self.broker,clock=lambda:self.now,wall_clock=lambda:self.now)
        self.assertIsNone(other.status()['last_frame'])
        with self.assertRaises(BrokerError):other.preview_image(digest)
    def test_atomic_latest_packet_eliminates_metadata_image_replacement_race(self):
        self.service.exchange('engine','stage',self.frame(1));old=self.service.status()
        self.now+=.15;self.service.exchange('engine','stage',self.frame(2))
        with self.assertRaises(BrokerError):self.service.image(str(old['frame']['frame_id']))
        state,image=self.service.image_packet()
        self.assertEqual(state['frame']['frame_id'],2);self.assertEqual(image,self.image)
        import hashlib
        self.assertEqual(state['frame']['sha256'],hashlib.sha256(image).hexdigest())
        self.engine['snapshot']['applied_revision']='other'
        state,image=self.service.image_packet();self.assertIsNone(state['frame']);self.assertIsNone(image)
        self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()
    def test_live_packet_image_and_camera_never_call_optional_disk_restore(self):
        loader=Mock(side_effect=AssertionError('history loader entered live path'))
        self.service.static_preview_loader=loader
        state,image=self.service.image_packet()
        self.assertIsNone(state['frame']);self.assertIsNone(image)
        self.service.exchange('engine','stage',self.frame(1))
        self.assertIsNotNone(self.service.status()['frame'])
        self.assertEqual(self.service.image('1'),self.image)
        self.assertEqual(self.service.image_packet()[1],self.image)
        self.service.camera_action(dict(request_id='camera',frame_id=1,action='orbit_left'))
        loader.assert_not_called()
        self.now+=2
        self.assertIsNone(self.service.image_packet()[0]['frame'])
        with self.assertRaises(BrokerError):self.service.image('1')
        loader.assert_not_called()
    def test_optional_restore_deferred_does_not_clear_last_preview(self):
        self.service.exchange('engine','stage',self.frame(1))
        retained=self.service.last_preview
        self.service.latest=None
        self.service.static_preview_loader=Mock(return_value=None)
        state=self.service.status()
        self.assertIs(self.service.last_preview,retained)
        self.assertIsNone(state['frame']);self.assertTrue(state['last_frame']['preview_only'])
    def test_history_restore_is_single_flight_nonblocking_and_binding_fenced(self):
        from types import SimpleNamespace
        from twinpulse_app.api import LocalApiServer
        api=object.__new__(LocalApiServer)
        generation={'request_id':'job','progress':{'request_id':'provider','checkpoint_id':'checkpoint',
            'generation_preview':{'candidate_revision':'candidate','scene_revision':'scene'}}}
        api.conversation=SimpleNamespace(_lock=Lock(),_state={'generation':generation})
        api._key_registry=SimpleNamespace(settings=SimpleNamespace(path=ROOT/'placeholder-settings.json'))
        api._static_generation_preview_lock=Lock()
        api._static_generation_preview_cache=None;api._static_generation_preview_at=0
        api.broker=SimpleNamespace(project_id='example')
        module='twinpulse_app.generation_preview_restore.load_generation_preview'
        with patch(module,return_value={'fixture':'static'}) as load:
            api.conversation._lock.acquire()
            try:self.assertIsNone(api._retained_generation_preview())
            finally:api.conversation._lock.release()
            load.assert_not_called()
            api._static_generation_preview_lock.acquire()
            try:self.assertIsNone(api._retained_generation_preview())
            finally:api._static_generation_preview_lock.release()
            load.assert_not_called()
            def superseded(*_):
                generation['progress']['generation_preview']['scene_revision']='replaced'
                return {'fixture':'late'}
            load.side_effect=superseded
            self.assertIsNone(api._retained_generation_preview())
            self.assertIsNone(api._static_generation_preview_cache)
            load.side_effect=None
            restored=api._retained_generation_preview()
            self.assertEqual(restored[0][-1],'replaced')
            self.assertEqual(restored[1],{'fixture':'static'})
            before=load.call_count
            self.assertEqual(api._retained_generation_preview(),restored)
            self.assertEqual(load.call_count,before)
    def test_invalid_image_and_timestamp_are_rejected(self):
        for kw in ({'captured_at_ms':self.now*1000-1100},{'frame_id':True},
                   {'width':100000},{'jpeg_base64':'bad'},{'camera_sequence':False}):
            with self.subTest(kw=kw),self.assertRaises(BrokerError):self.service.exchange('engine','stage',self.frame(**kw))
    def test_camera_idempotency_result_expiry_and_no_motion(self):
        self.service.exchange('engine','stage',self.frame())
        action={'request_id':'camera1','frame_id':1,'action':'orbit_left'}
        self.assertTrue(self.service.camera_action(action)['camera_pending'])
        self.assertTrue(self.service.camera_action(action)['camera_pending'])
        with self.assertRaises(BrokerError):self.service.camera_action({**action,'action':'zoom_in'})
        with self.assertRaises(BrokerError):self.service.camera_action({**action,'action':[]})
        result=self.service.exchange('engine','stage',{**self.frame(),'frame':None})
        self.assertEqual(result['camera']['action'],'orbit_left')
        self.now+=2.1
        result=self.service.exchange('engine','stage',{**self.frame(),'frame':None})
        self.assertIsNone(result['camera']);self.assertEqual(self.service.status()['camera_result']['code'],'camera_delivery_expired')
        self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()

    def test_top_view_uses_the_same_fresh_frame_gate_without_scene_authority(self):
        body=dict(request_id='top',frame_id=1,action='top_view')
        with self.assertRaises(BrokerError):self.service.camera_action(body)
        self.service.exchange('engine','stage',self.frame())
        self.assertTrue(self.service.camera_action(body)['camera_pending'])
        result=self.service.exchange('engine','stage',{**self.frame(),'frame':None})
        self.assertEqual(result['camera']['action'],'top_view')
        self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()

    def test_browser_failure_is_typed_deduplicated_and_not_control_authority(self):
        import tempfile
        from twinpulse_core.execution_diagnostics import ExecutionStore
        with tempfile.TemporaryDirectory() as directory:
            store=ExecutionStore(Path(directory),'project')
            self.broker.diagnostics=store
            command=store.begin('engine_command',command_id='build1');command.finish()
            self.broker.public_state.return_value={'build_view':{'command_execution_id':command.execution_id,'command_id':'build1','status':'succeeded'}}
            self.service.exchange('engine','stage',self.frame())
            body={'frame_id':1,'engine_session_id':'engine','stage_epoch':'stage','applied_revision':'revision','error_code':'viewport_http_error'}
            result=self.service.report_browser_failure('owner',body)
            self.assertFalse(result['physical_authority']);self.assertTrue(store.flush())
            detail=store.detail(result['execution_id'])
            self.assertEqual(detail['status'],'failed')
            self.assertEqual(detail['first_error']['stage'],'browser_image_display')
            self.assertEqual(detail['manifest']['metadata']['command_execution_id'],command.execution_id)
            self.assertEqual(detail['manifest']['metadata']['measurement_source'],'browser_reported')
            self.service.exchange('engine','stage',self.frame(2))
            self.assertEqual(self.service.report_browser_failure('owner',{**body,'frame_id':2}),result)
            self.assertEqual(store.detail(command.execution_id)['status'],'succeeded')
            self.assertIsNotNone(self.service.status()['frame'])
            self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()
            for changed in ({'error_code':[]},{'error_code':'secret prose'},{'frame_id':True}):
                with self.subTest(changed=changed),self.assertRaises(BrokerError):
                    self.service.report_browser_failure('owner',{**body,**changed})
            count=len(self.service.browser_failures)
            for changed in ({'applied_revision':'old'},{'frame_id':999}):
                discarded=self.service.report_browser_failure('owner',{**body,**changed})
                self.assertEqual(discarded['disposition'],'discarded')
                self.assertIsNone(discarded['execution_id']);self.assertFalse(discarded['physical_authority'])
            self.assertEqual(len(self.service.browser_failures),count)
            self.now+=5
            self.assertEqual(self.service.report_browser_failure('owner',body)['disposition'],'discarded')
            self.assertEqual(len(self.service.browser_failures),count)
            self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()

    def test_browser_sink_failure_preserves_frame_and_bounded_metadata_history(self):
        self.broker.diagnostics=Mock()
        self.broker.diagnostics.begin.side_effect=OSError('optional sink unavailable')
        self.broker.public_state.return_value={}
        for seq in range(1,80):self.service.exchange('engine','stage',self.frame(seq))
        body={'frame_id':79,'engine_session_id':'engine','stage_epoch':'stage','applied_revision':'revision','error_code':'viewport_draw_failed'}
        for owner in range(70):
            self.assertIsNone(self.service.report_browser_failure(str(owner),body)['execution_id'])
        self.assertEqual(len(self.service.observed_frames),64)
        self.assertEqual(len(self.service.browser_failures),64)
        self.assertEqual(self.service.image('79'),self.image)
        self.broker.diagnostics.note_storage_error.assert_called()

    def test_browser_stage_timings_are_optional_bounded_and_preserved_without_control_authority(self):
        import tempfile
        from twinpulse_core.execution_diagnostics import ExecutionStore
        with tempfile.TemporaryDirectory() as directory:
            store=ExecutionStore(Path(directory),'project');self.broker.diagnostics=store
            self.broker.public_state.return_value={};self.service.exchange('engine','stage',self.frame())
            timings={'metadata_ms':10,'image_ms':1100,'decode_ms':0,'poll_ms':1110,'frame_age_ms':1115,'schedule_lag_ms':2}
            body={'frame_id':1,'engine_session_id':'engine','stage_epoch':'stage','applied_revision':'revision',
                  'error_code':'viewport_image_expired','timings':timings}
            for changed in (None,[],{},dict(timings,headers='private'),dict(timings,image_ms=True),
                            dict(timings,image_ms=-1),dict(timings,image_ms=60001),dict(timings,image_ms=float('nan')),
                            dict(timings,image_ms=float('inf')),dict(timings,image_ms='1100')):
                with self.subTest(changed=changed),self.assertRaises(BrokerError):
                    self.service.report_browser_failure('owner',{**body,'timings':changed})
            result=self.service.report_browser_failure('owner',body);self.assertTrue(store.flush())
            detail=store.detail(result['execution_id'])
            self.assertEqual(detail['manifest']['metadata']['browser_image_ms'],1100)
            self.assertEqual(detail['manifest']['metadata']['browser_decode_ms'],0)
            self.assertEqual(detail['first_error']['error_code'],'viewport_image_expired')
            self.assertEqual(detail['manifest']['metadata']['measurement_source'],'browser_reported')
            self.assertEqual(self.service.report_browser_failure('owner',body),result)
            self.assertFalse(result['physical_authority']);self.assertIsNotNone(self.service.status()['frame'])
            self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()

    def test_camera_displayed_frame_race_does_not_retain_pixels_or_cross_stage(self):
        self.service.exchange('engine','stage',self.frame(1));self.now+=.15
        self.service.exchange('engine','stage',self.frame(2))
        with self.assertRaises(BrokerError):self.service.image('1')
        self.assertTrue(self.service.camera_action({'request_id':'fresh','frame_id':1,'action':'pan_up'})['camera_pending'])
        self.now+=2.1
        self.assertFalse(self.service.status()['camera_pending'])
        self.assertEqual(self.service.status()['camera_result']['code'],'camera_delivery_expired')
        self.service.exchange('engine','stage',self.frame(3))
        with self.assertRaises(BrokerError):self.service.camera_action({'request_id':'old','frame_id':1,'action':'zoom_out'})
        self.engine['snapshot']['applied_revision']='new'
        with self.assertRaises(BrokerError):self.service.camera_action({'request_id':'new','frame_id':3,'action':'zoom_out'})
        self.broker.submit.assert_not_called();self.broker.acquire_lease.assert_not_called()


class ViewportApiTests(R4ApiTests):
    def test_unexpected_backend_error_has_redacted_unknown_outcome_and_queryable_id_not_empty_socket(self):
        import re
        cookie,_,_=self.bootstrap()
        from io import StringIO
        log=StringIO()
        def fail_without_disclosing_source(*_args,**_kwargs):
            raise RuntimeError('PRIVATE_EXCEPTION_FIXTURE')
        with patch.object(self.server.viewport,'status',side_effect=fail_without_disclosing_source),patch('sys.stderr',log):
            status,body,_=self.request('/v1/product/viewport',headers={'Cookie':cookie})
        self.assertEqual(status,500);self.assertEqual(body['error']['code'],'unexpected_backend_error')
        self.assertIn('outcome unconfirmed',body['error']['message'])
        execution=re.search(r'execution ([a-f0-9]{32})',body['error']['message']).group(1)
        self.assertIn(execution,log.getvalue());self.assertNotIn('PRIVATE_EXCEPTION_FIXTURE',log.getvalue())
        self.assertNotIn('PRIVATE_EXCEPTION_FIXTURE',str(body))
        self.assertFalse(self.broker.public_state('anything')['lease_owned'])

    def test_display_authentication_csrf_and_no_lease(self):
        cookie,csrf,token=self.bootstrap()
        for path in ('/v1/product/viewport','/v1/product/viewport/frame/1','/v1/product/viewport/current'):
            self.assertEqual(self.request(path)[0],401)
        self.assertEqual(self.request('/v1/engine/viewport',{
            'engine_session_id':'engine-1','stage_epoch':'stage-1','frame':None,'camera_result':None},
            headers={'Authorization':'Bearer '+token})[0],200)
        self.assertEqual(self.request('/v1/product/viewport',headers={'Cookie':cookie})[0],200)
        self.assertEqual(self.request('/v1/product/viewport/camera',{'request_id':'one','frame_id':1,'action':'orbit_left'},
            headers={'Cookie':cookie})[0],403)
        self.assertFalse(self.broker.public_state('anything')['lease_owned'])
        body={'frame_id':1,'engine_session_id':'engine-1','stage_epoch':'stage-1','applied_revision':'revision','error_code':'viewport_http_error'}
        self.assertEqual(self.request('/v1/product/viewport/observation',body)[0],401)
        self.assertEqual(self.request('/v1/product/viewport/observation',body,headers={'Cookie':cookie})[0],403)
        self.assertEqual(self.request('/v1/product/viewport/observation',body,headers={'Authorization':'Bearer '+token})[0],401)

    def test_atomic_image_api_is_authenticated_no_store_and_keeps_receipt_with_bytes(self):
        import json
        from urllib.request import Request,urlopen
        from unittest.mock import patch
        cookie,_,_=self.bootstrap()
        state={'state':'live','frame':{'frame_id':7},'physical_authority':False}
        content=b'local-jpeg-fixture'
        with patch.object(self.server.viewport,'image_packet',return_value=(state,content)):
            with urlopen(Request(self.server.base_url+'/v1/product/viewport/current',headers={'Cookie':cookie}),timeout=3) as response:
                self.assertEqual(response.status,200);self.assertEqual(response.read(),content)
                self.assertEqual(json.loads(response.headers['X-TwinPulse-Viewport']),state)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                self.assertEqual(response.headers['Content-Type'],'image/jpeg')
        with patch.object(self.server.viewport,'image_packet',return_value=({'state':'stale','frame':None,'physical_authority':False},None)):
            with urlopen(Request(self.server.base_url+'/v1/product/viewport/current',headers={'Cookie':cookie}),timeout=3) as response:
                self.assertEqual(response.status,204);self.assertEqual(response.read(),b'')
                self.assertIsNone(json.loads(response.headers['X-TwinPulse-Viewport'])['frame'])
        self.assertFalse(self.broker.public_state('anything')['lease_owned'])


class PublisherTests(unittest.TestCase):
    def test_capture_does_not_reapply_unchanged_native_resolution(self):
        from types import SimpleNamespace
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        class Viewport:
            def __init__(self):self.value=(800,600);self.writes=[]
            @property
            def resolution(self):return self.value
            @resolution.setter
            def resolution(self,value):self.writes.append(value);self.value=value
        viewport=Viewport();bridge=Mock();bridge.connected=True
        publisher=LiveViewportPublisher(bridge)
        publisher.fleet_runtime=SimpleNamespace(rendered=lambda *_:None,receive=lambda *_:None,update=lambda *_:None,
            report=[],navigation_scene=None,scene_produced_at=None,frame_scan=None,
            frame_anchors=lambda *_:[],render_tokens=lambda:[])
        utility=SimpleNamespace(capture_viewport_to_buffer=Mock(),get_active_viewport=lambda:viewport)
        snapshot=SimpleNamespace(engine_session_id='engine',stage_epoch='stage',applied_revision='scene')
        with patch.dict(sys.modules,{'omni.kit.viewport.utility':utility}):
            for _ in range(8):
                publisher.capture=None;publisher.last_capture=0;publisher.update(snapshot)
            self.assertEqual(viewport.writes,[(960,640)])
            viewport.value=(1024,768);publisher.capture=None;publisher.last_capture=0
            publisher.update(snapshot)
            self.assertEqual(viewport.writes,[(960,640),(960,640)])

    def test_completed_delegate_with_missing_callback_recovers_with_bounded_tickets(self):
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        publisher=LiveViewportPublisher(Mock());publisher.capture=True;publisher.capture_ticket=1
        publisher.started_capture=0
        done=Mock();done.done.return_value=True;done.cancelled.return_value=False
        publisher.capture_wait=done
        self.assertTrue(publisher._retire_completed_capture(4))
        self.assertIsNone(publisher.capture);self.assertEqual(publisher.retired_captures,{1})
        publisher.capture=True;publisher.capture_ticket=2;publisher.capture_wait=done
        self.assertTrue(publisher._retire_completed_capture(4))
        publisher.capture=True;publisher.capture_ticket=3;publisher.capture_wait=done
        self.assertFalse(publisher._retire_completed_capture(4))
        self.assertEqual(len(publisher.retired_captures),2)
        publisher.retired_captures.clear();done.done.return_value=False
        self.assertFalse(publisher._retire_completed_capture(4))
        self.assertTrue(publisher.capture)  # No endless native queue on an unconsumed delegate.

    def test_build_and_camera_transition_wait_for_subsequent_kit_updates(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        bridge=Mock();bridge.connected=True
        publisher=LiveViewportPublisher(bridge)
        utility=SimpleNamespace(capture_viewport_to_buffer=Mock(),get_active_viewport=Mock(return_value=SimpleNamespace()))
        first=SimpleNamespace(engine_session_id='engine',stage_epoch='stage',applied_revision='first')
        with patch.dict(sys.modules,{'omni.kit.viewport.utility':utility}):
            for _ in range(publisher.RENDER_WARMUP_UPDATES):publisher.update(first)
            utility.capture_viewport_to_buffer.assert_not_called()
            publisher.update(first)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,1)
            previous_epoch=publisher.render_epoch
            changed=SimpleNamespace(engine_session_id='engine',stage_epoch='stage',applied_revision='second')
            publisher.update(changed)
            self.assertFalse(publisher._queue_capture(previous_epoch,{'applied_revision':'first'},64,64,b'old GPU buffer'))
            self.assertIsNone(publisher.raw)
            publisher.capture=None;publisher.last_capture=0
            for _ in range(publisher.RENDER_WARMUP_UPDATES-1):publisher.update(changed)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,1)
            publisher.update(changed)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,2)
            publisher.capture=None;publisher.last_capture=0
            publisher.camera=dict(request_id='camera',engine_session_id='engine',stage_epoch='stage',applied_revision='second',action='orbit_left')
            with patch.object(publisher,'_camera_action') as action:
                publisher.update(changed);action.assert_called_once_with('orbit_left')
            self.assertEqual(publisher.camera_sequence,1)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,2)
            for _ in range(publisher.RENDER_WARMUP_UPDATES):publisher.update(changed)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,3)

    def test_old_callback_and_already_queued_pixels_cannot_relabel_a_new_revision(self):
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        publisher=LiveViewportPublisher(Mock())
        publisher._begin_render_epoch(('engine','stage','first'))
        old=publisher.render_epoch
        self.assertTrue(publisher._queue_capture(old,{'applied_revision':'first'},64,64,b'first'))
        publisher._begin_render_epoch(('engine','stage','second'))
        self.assertIsNone(publisher.raw)
        self.assertFalse(publisher._queue_capture(old,{'applied_revision':'first'},64,64,b'late'))
        self.assertTrue(publisher._queue_capture(publisher.render_epoch,{'applied_revision':'second'},64,64,b'current'))
        self.assertEqual(publisher.raw[3],b'current')
        self.assertEqual(publisher.dropped,2)

    def test_same_collision_revision_new_visual_build_invalidates_gpu_and_waits(self):
        from types import SimpleNamespace
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        bridge=Mock();bridge.connected=True;bridge.adapter.display_build_id='first-build'
        publisher=LiveViewportPublisher(bridge)
        utility=SimpleNamespace(capture_viewport_to_buffer=Mock(),get_active_viewport=Mock(return_value=SimpleNamespace()))
        snap=SimpleNamespace(engine_session_id='engine',stage_epoch='stage',applied_revision='same-geometry')
        with patch.dict(sys.modules,{'omni.kit.viewport.utility':utility}):
            for _ in range(publisher.RENDER_WARMUP_UPDATES+1):publisher.update(snap)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,1)
            old=publisher.render_epoch
            self.assertTrue(publisher._queue_capture(old,{},64,64,b'old-appearance'))
            bridge.adapter.display_build_id='new-appearance-build'
            publisher.update(snap)
            self.assertIsNone(publisher.raw)
            self.assertFalse(publisher._queue_capture(old,{},64,64,b'late-old-appearance'))
            publisher.capture=None;publisher.last_capture=0
            for _ in range(publisher.RENDER_WARMUP_UPDATES-1):publisher.update(snap)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,1)
            publisher.update(snap)
            self.assertEqual(utility.capture_viewport_to_buffer.call_count,2)

    def test_camera_poll_transport_success_does_not_erase_gpu_capture_failure(self):
        sys.path.insert(0,str(ROOT))
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        bridge=Mock();bridge.connected=True;bridge._lock=Lock();bridge._shared_stage_epoch='stage'
        bridge.adapter.engine_session_id='engine'
        publisher=LiveViewportPublisher(bridge)
        publisher.last_error='viewport_capture_timeout';publisher.transport_error='previous_transport_failure'
        def reply(path,body):
            publisher.stop_event.set()
            return {'camera':None}
        bridge._post.side_effect=reply
        publisher._io()
        self.assertEqual(publisher.last_error,'viewport_capture_timeout')
        self.assertIsNone(publisher.transport_error)
        bridge.adapter.snapshot.assert_not_called()

    def test_fleet_poll_subtracts_http_time_without_overlapping_or_extending_input(self):
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        for rtt,expected in ((.01,.04),(.10,.001)):
            publisher=LiveViewportPublisher(Mock());clock=[0.];active=[False];requests=[]
            class EndAfterTwo:
                def is_set(self):return False
                def wait(self,delay):
                    requests.append(delay);clock[0]+=delay
                    return len(requests)==2
            publisher.stop_event=EndAfterTwo()
            def exchange():
                self.assertFalse(active[0]);active[0]=True
                clock[0]+=rtt;active[0]=False
            publisher._fleet_exchange=exchange
            with patch('scripts.twinpulse_live_viewport.time.monotonic',side_effect=lambda:clock[0]):
                publisher._fleet_io()
            self.assertEqual(len(requests),2)
            for delay in requests:self.assertAlmostEqual(delay,expected)

    def test_fleet_exchange_preserves_server_intent_and_receipt_time(self):
        from scripts.twinpulse_live_viewport import LiveViewportPublisher
        bridge=Mock();bridge.connected=True;bridge._lock=Lock();bridge._shared_stage_epoch='stage'
        bridge.adapter.engine_session_id='engine'
        original={'intent':{'sequence':8,'expires_at_ms':250}}
        bridge._post.return_value={'fleet':original}
        publisher=LiveViewportPublisher(bridge);publisher.fleet_report={'robots':[]}
        with patch('scripts.twinpulse_live_viewport.time.monotonic',return_value=12.):publisher._fleet_exchange()
        self.assertEqual(list(publisher.fleet_pending),[(original,12.)])
        self.assertEqual(original['intent']['expires_at_ms'],250)
        bridge.adapter.snapshot.assert_not_called()
