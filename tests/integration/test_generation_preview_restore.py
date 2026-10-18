# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Static restore contract only, not fresh-model or actual Isaac acceptance."""
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from PIL import Image
from twinpulse_core import canonical_sha256
from twinpulse_provider.generation_store import GenerationStore
from twinpulse_app.generation_preview_restore import load_generation_preview
from twinpulse_app.viewport_service import ViewportService
from twinpulse_app.command_broker import BrokerError

class StaticPreviewRestoreTests(unittest.TestCase):
    def records(self,root):
        output=BytesIO();Image.new('RGB',(64,64),'blue').save(output,format='JPEG');data=output.getvalue()
        meta=dict(frame_id=4,applied_revision='a'*64,captured_at_ms=1000,width=64,height=64,camera_sequence=0,
            sha256=hashlib.sha256(data).hexdigest(),engine_session_id='old-engine',stage_epoch='old-stage',
            candidate_revision='b'*64,scene_revision='a'*64,plan_sha256=canonical_sha256({'calls':[]}),project_id='project')
        preview=dict(candidate_revision='b'*64,scene_revision='a'*64,rendered_count=3,pending_count=1)
        key='c'*64;render_key=canonical_sha256(meta);store=GenerationStore(root)
        cp=dict(request_id='provider-request',generation_preview=preview,preview_plan={'calls':[]},preview_render_key=render_key)
        store.save('checkpoint',key,cp);store.save('render',render_key,dict(metadata=meta,jpeg_base64=base64.b64encode(data).decode()))
        generation=dict(request_id='outer-request',progress=dict(request_id='provider-request',checkpoint_id=key,generation_preview=preview))
        return generation,meta,data,cp,store,render_key

    def test_disk_preview_never_restores_live_or_camera_authority(self):
        with TemporaryDirectory() as folder:
            generation,meta,data,_,_,_=self.records(Path(folder))
            frame=load_generation_preview(folder,'project',generation)
            self.assertEqual(frame['data'],data)
            broker=Mock();broker.supervisor_state.return_value=dict(engine_connected=True,engine_session_id='new',stage_epoch='new',snapshot={})
            service=ViewportService(broker);service.static_preview_loader=lambda:('binding',frame)
            state=service.status();self.assertIsNone(state['frame']);self.assertTrue(state['last_frame']['preview_only'])
            self.assertIsNone(service.latest);self.assertEqual(list(service.observed_frames),[])
            with self.assertRaises(BrokerError):service.camera_action(dict(request_id='camera',frame_id=4,action='orbit_left'))
            service.static_preview_loader=lambda:(None,None)
            self.assertIsNone(service.status()['last_frame'])
            broker.submit.assert_not_called();broker.record_current_frame.assert_not_called()

    def test_project_request_candidate_scene_and_plan_mismatch_are_not_adopted(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);generation,_,_,cp,store,_=self.records(root)
            self.assertIsNone(load_generation_preview(root,'foreign',generation))
            for field in ('request_id','candidate_revision','scene_revision'):
                changed=deepcopy(generation)
                if field=='request_id':changed['progress'][field]='foreign'
                else:changed['progress']['generation_preview'][field]='d'*64
                with self.subTest(field=field):self.assertIsNone(load_generation_preview(root,'project',changed))
            store.save('checkpoint','c'*64,{**cp,'preview_plan':{'calls':['different']}})
            self.assertIsNone(load_generation_preview(root,'project',generation))

    def test_legacy_exact_capture_and_corrupt_evidence_are_read_only(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);generation,_,data,cp,store,render_key=self.records(root)
            cp.pop('preview_render_key');store.save('checkpoint','c'*64,cp)
            self.assertEqual(load_generation_preview(root,'project',generation)['data'],data)
            path=root/'render'/(render_key+'.json');path.write_bytes(b'corrupt');before=path.read_bytes()
            self.assertIsNone(load_generation_preview(root,'project',generation));self.assertEqual(path.read_bytes(),before)

    def test_oversized_record_is_skipped_without_overwriting(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);generation,_,_,_,_,render_key=self.records(root)
            path=root/'render'/(render_key+'.json');path.write_bytes(b' '* (2*1024*1024+1))
            self.assertIsNone(load_generation_preview(root,'project',generation));self.assertEqual(path.stat().st_size,2*1024*1024+1)

    def test_unrelated_legacy_corruption_does_not_hide_exact_capture(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);generation,_,data,cp,store,_=self.records(root)
            cp.pop('preview_render_key');store.save('checkpoint','c'*64,cp)
            corrupt=root/'render'/('0'*64+'.json');corrupt.write_bytes(b'corrupt unrelated file')
            self.assertEqual(load_generation_preview(root,'project',generation)['data'],data)
            self.assertEqual(corrupt.read_bytes(),b'corrupt unrelated file')

    def test_digest_valid_nonobject_payload_is_skipped(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);generation,_,_,_,store,_=self.records(root)
            store.save('checkpoint','c'*64,[])
            before=(root/'checkpoint'/('c'*64+'.json')).read_bytes()
            self.assertIsNone(load_generation_preview(root,'project',generation))
            self.assertEqual((root/'checkpoint'/('c'*64+'.json')).read_bytes(),before)

    def test_same_binding_missing_then_present_snapshot_is_adopted(self):
        with TemporaryDirectory() as folder:
            generation,_,_,_,_,_=self.records(Path(folder))
            frame=load_generation_preview(folder,'project',generation)
            broker=Mock();broker.supervisor_state.return_value=dict(engine_connected=False,snapshot={})
            service=ViewportService(broker);service.static_preview_loader=lambda:('binding',None)
            self.assertIsNone(service.status()['last_frame'])
            service.static_preview_loader=lambda:('binding',frame)
            self.assertIsNotNone(service.status()['last_frame']);self.assertIsNone(service.status()['frame'])

    def test_api_negative_cache_retries_after_checkpoint_publish(self):
        from threading import RLock
        from unittest.mock import patch
        from twinpulse_app.api import LocalApiServer
        with TemporaryDirectory() as folder:
            parent=Path(folder);root=parent/'provider-evidence/generation-store'
            generation,_,_,cp,store,_=self.records(root)
            path=root/'checkpoint'/('c'*64+'.json');original=path.read_bytes();path.unlink()
            server=LocalApiServer.__new__(LocalApiServer)
            server.conversation=Mock();server.conversation._lock=RLock();server.conversation._state={'generation':generation}
            server._key_registry=Mock();server._key_registry.settings.path=parent/'settings.json'
            server.broker=Mock();server.broker.project_id='project'
            server._static_generation_preview_cache=None;server._static_generation_preview_at=0
            with patch('twinpulse_app.api.time.monotonic',return_value=10):self.assertIsNone(server._retained_generation_preview()[1])
            path.write_bytes(original)
            with patch('twinpulse_app.api.time.monotonic',return_value=12):self.assertIsNotNone(server._retained_generation_preview()[1])
