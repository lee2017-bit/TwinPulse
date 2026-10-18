# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Display contracts, not actual Isaac or physics acceptance."""
import base64
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
