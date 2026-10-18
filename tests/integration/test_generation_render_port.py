# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real broker/viewport, explicit local engine fixture. Not actual Isaac PASS."""
import asyncio
import base64
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import sys
import time
import json
from threading import Thread, Event
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_core import SimulationSnapshot, CommandReceipt, InputRevision
from twinpulse_provider import CancellationToken, ProviderConfigurationError, GenerationCancelledError
from twinpulse_provider.generation_policy import GenerationBudgetError
from twinpulse_app.command_broker import CommandBroker
from twinpulse_app.generation_render_port import GenerationRenderPort
from twinpulse_app.viewport_service import ViewportService
from tests.integration import test_generation_approval as approvals


class RenderPortTests(unittest.TestCase):
    def setUp(self):
        self.broker=CommandBroker()
        self.broker.register_engine('fixture-engine','fixture-epoch')
        self.snapshot=SimulationSnapshot('fixture-engine','fixture-epoch','default',None,None,1,'idle',None,None,
            ('build_site_scene',),('site_scene_build_v2','generation_room_visual_v1'))
        self.broker.record_snapshot(self.snapshot)
        self.viewport=ViewportService(self.broker)
        self.input=InputRevision.create(prompt='Create an estimated room',input_kind='photo',images=(('fixture.jpg','image/jpeg',b'fixture'),),generation_settings={'model_id':'fixture'},
            measurement_constraints=(),profile_id='compact_2wd.v1')
        self.port=GenerationRenderPort(self.broker,self.viewport,'owner',self.input,current=lambda:True)
        # Existing typed text fixture produces a complete plan without LLM.
        from twinpulse_provider.semantic_scene import checked_structure,checked_batch,scene_draft,compile_scene,revision
        from twinpulse_provider.nebius_pipeline import ObservationArtifact
        from twinpulse_provider import GenerationRequest
        request=GenerationRequest('render-fixture','Create a bed')
        obs=ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Fixture',entities=[],relations=[],dimensions=[],ambiguities=[]))
        structure=approvals.structure();structure['inventory'][0]={'id':'bed','kind':'bed',
            'source':{'basis':'user','observation_ids':[],'user_quote':'a bed'}}
        candidate=checked_batch(approvals.furniture(),scene_draft(checked_structure(structure,request,obs)),['bed'])
        self.plan,_=compile_scene(candidate,obs,request);self.revision=revision(candidate)

    async def engine_fixture(self, *, frames=True, replacement=False):
        for _ in range(40):
            command=self.broker.claim('fixture-engine','fixture-epoch')
            if command:
                scene=command.payload['scene'];revision=command.payload['scene_revision']
                self.broker.record_receipt(CommandReceipt(command.command_id,command.command_type,'default',
                    'fixture-engine','fixture-epoch','succeeded',applied_revision=revision,build_fingerprint='fixture'))
                self.broker.record_snapshot(replace(self.snapshot,sequence=self.broker.supervisor_state()['snapshot']['sequence']+1,
                    applied_revision=revision,runtime_state='built'))
                if replacement:
                    self.broker.register_engine('replacement','new-epoch');return
                if frames:
                    from PIL import Image
                    stream=BytesIO();Image.new('RGB',(64,64),'white').save(stream,format='JPEG')
                    for identity in (1,2):
                        if identity==2:await asyncio.sleep(.15)
                        self.viewport.exchange('fixture-engine','fixture-epoch',dict(engine_session_id='fixture-engine',stage_epoch='fixture-epoch',
                            frame=dict(frame_id=identity,applied_revision=revision,captured_at_ms=time.time()*1000,
                                width=64,height=64,camera_sequence=0,jpeg_base64=base64.b64encode(stream.getvalue()).decode()),camera_result=None))
                return
            await asyncio.sleep(.01)

    def run_capture(self, *, frames=True, replacement=False, timeout=6):
        self.port.preflight()
        async def run():
            task=asyncio.create_task(self.engine_fixture(frames=frames,replacement=replacement))
            try:return await self.port.capture(self.plan,self.revision,CancellationToken(),timeout)
            finally:await task
        return asyncio.run(run())

    def test_receipt_then_fresh_frame_matches_same_scene_input_and_plan(self):
        result=self.run_capture()
        from twinpulse_core import SiteToolPlan, execute_site_tool_plan
        expected=execute_site_tool_plan(SiteToolPlan.from_dict(self.plan),source='photo',source_ref=self.input.digest).scene
        self.assertEqual(result['metadata']['scene_revision'],expected.revision)
        self.assertEqual(result['metadata']['candidate_revision'],self.revision)
        self.assertFalse(result['metadata']['physical_authority'])
        state=self.broker.public_state('owner')
        self.assertEqual([o['command_type'] for o in state['operations']],['build_site_scene'])
        self.assertEqual(state['build_view']['status'],'succeeded')

    def test_old_adapter_capability_does_not_silently_fall_back_to_boxes(self):
        self.broker.record_snapshot(replace(self.snapshot,sequence=2,capabilities=('site_scene_build_v2',)))
        with self.assertRaisesRegex(ProviderConfigurationError,'VISUAL_CAPABILITY_MISSING'):
            self.port.preflight()
        self.assertFalse(self.broker.public_state('owner')['operations'])

    def test_same_revision_pre_build_jpeg_cannot_be_bound_to_new_appearance(self):
        self.run_capture()  # Old same-revision image remains fresh in viewport.
        self.assertIsNotNone(self.viewport.image_packet()[1])
        # This accelerated fixture tests post-submit stale-frame rejection,
        # separately from the production minimum-window admission tests below.
        with patch('twinpulse_app.generation_render_port._MIN_BUILD_SUBMISSION_WINDOW_S',0), \
                self.assertRaisesRegex(ProviderConfigurationError,'FRAME_TIMEOUT'):
            self.run_capture(frames=False,timeout=.3)

    def test_same_revision_rebuild_waits_for_new_frame_after_receipt(self):
        first=self.run_capture()
        # Reuse fixture frame sequence only after recording the old baseline;
        # production publisher always increases within its engine identity.
        old=self.viewport.sequence
        original_exchange=self.viewport.exchange
        def newer(engine,epoch,body):
            body={**body,'frame':{**body['frame'],'frame_id':body['frame']['frame_id']+old}}
            return original_exchange(engine,epoch,body)
        self.viewport.exchange=newer
        second=self.run_capture(timeout=6)
        self.assertGreater(second['metadata']['frame_id'],first['metadata']['frame_id'])

    def test_build_receipt_without_frame_is_not_a_review(self):
        with patch('twinpulse_app.generation_render_port._MIN_BUILD_SUBMISSION_WINDOW_S',0), \
                self.assertRaisesRegex(ProviderConfigurationError,'FRAME_TIMEOUT'):
            self.run_capture(frames=False,timeout=.4)

    def test_short_phase_budget_never_submits_an_irreversible_build(self):
        self.port.preflight()
        with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_TIME_BUDGET'):
            asyncio.run(self.port.capture(self.plan,self.revision,CancellationToken(),1.3))
        self.assertEqual(self.broker.public_state('owner')['operations'],[])

    def test_payload_preparation_can_use_up_the_admission_window(self):
        self.port.preflight()
        original=self.broker.register_site_scene
        async def run():
            loop=asyncio.get_running_loop()
            original_time=loop.time
            initial=loop.time()
            # Only this diagnostic clock changes after real payload preparation;
            # no runtime/engine state is injected into a user's App.
            def register(*args,**kwargs):
                original(*args,**kwargs)
                loop.time=lambda:initial+2
            with patch.object(self.broker,'register_site_scene',side_effect=register):
                try:
                    with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_TIME_BUDGET'):
                        await self.port.capture(self.plan,self.revision,CancellationToken(),6)
                finally:
                    loop.time=original_time
        asyncio.run(run())
        self.assertEqual(self.broker.public_state('owner')['operations'],[])

    def test_plan_compilation_is_inside_the_original_phase_deadline(self):
        self.port.preflight()
        from twinpulse_core import execute_site_tool_plan
        async def run():
            loop=asyncio.get_running_loop()
            original_time=loop.time
            initial=loop.time()
            def compile(*args,**kwargs):
                result=execute_site_tool_plan(*args,**kwargs)
                loop.time=lambda:initial+2
                return result
            try:
                with patch('twinpulse_app.generation_render_port.execute_site_tool_plan',side_effect=compile):
                    with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_TIME_BUDGET'):
                        await self.port.capture(self.plan,self.revision,CancellationToken(),6)
            finally:
                loop.time=original_time
        asyncio.run(run())
        self.assertEqual(self.broker.public_state('owner')['operations'],[])

    def test_idle_capability_waits_for_lease_permission_then_submits_once(self):
        self.broker.record_snapshot(replace(self.snapshot,sequence=2,permitted_commands=('get_state',)))
        self.port.preflight()
        async def run():
            async def ready():
                while not self.broker.public_state('owner')['lease_owned']:await asyncio.sleep(.01)
                self.assertFalse(self.broker.public_state('owner')['operations'])
                self.broker.record_snapshot(replace(self.snapshot,sequence=3))
                await self.engine_fixture()
            task=asyncio.create_task(ready())
            try:return await self.port.capture(self.plan,self.revision,CancellationToken(),6)
            finally:await task
        self.assertEqual(asyncio.run(run())['metadata']['candidate_revision'],self.revision)

    def test_missing_permission_times_out_without_submitting_build(self):
        self.broker.record_snapshot(replace(self.snapshot,sequence=2,permitted_commands=('get_state',)))
        self.port.preflight()
        with self.assertRaisesRegex(ProviderConfigurationError,'COMMAND_PERMISSION_TIMEOUT'):
            asyncio.run(self.port.capture(self.plan,self.revision,CancellationToken(),.1))
        self.assertFalse(self.broker.public_state('owner')['operations'])

    def test_engine_replacement_never_accepts_old_frame(self):
        with self.assertRaises(ProviderConfigurationError):self.run_capture(replacement=True)

    def test_other_owner_lease_not_stolen(self):
        self.broker.acquire_lease('other')
        self.port.preflight()
        with self.assertRaisesRegex(ProviderConfigurationError,'LEASE_CONFLICT'):
            asyncio.run(self.port.capture(self.plan,self.revision,CancellationToken(),1))
        self.assertFalse(self.broker.public_state('owner')['operations'])

    def test_cancel_before_submit_no_build(self):
        self.port.preflight();token=CancellationToken();token.cancel()
        with self.assertRaises(GenerationCancelledError):asyncio.run(self.port.capture(self.plan,self.revision,token,1))
        self.assertFalse(self.broker.public_state('owner')['operations'])

    def test_running_or_missing_capability_block_preflight(self):
        for changes in (dict(runtime_state='running'),dict(capabilities=())):
            self.broker.record_snapshot(replace(self.snapshot,sequence=self.broker.supervisor_state()['snapshot']['sequence']+1,**changes))
            with self.assertRaises(ProviderConfigurationError):self.port.preflight()

    def test_current_input_invalidated_after_capture(self):
        result=self.run_capture();self.port.current=lambda:False
        with self.assertRaisesRegex(ProviderConfigurationError,'SUPERSEDED'):self.port.assert_current(result['metadata'])


class RenderApprovalJourneyTests(unittest.TestCase):
    setUp=approvals.GenerationApprovalTests.setUp
    tearDown=approvals.GenerationApprovalTests.tearDown
    request=approvals.GenerationApprovalTests.request
    product_headers=approvals.GenerationApprovalTests.product_headers
    call=approvals.GenerationApprovalTests.call
    answer=approvals.GenerationApprovalTests.answer
    begin=approvals.GenerationApprovalTests.begin
    approve=approvals.GenerationApprovalTests.approve
    install_audited_fixture=approvals.GenerationApprovalTests.install_audited_fixture

    def test_ordinary_chat_approval_render_repair_rebuild_save_same_candidate(self):
        self.route['generation_policy']['external_final_review']=True
        self.routes.save(self.route,lambda:None)
        observation=dict(schema_version='1.1',summary='Explicit synthetic photo fixture',
            entities=[dict(id='seen_bed',kind='static_obstacle',description='bed',confidence=.9,
                role='object',category='bed',region='unknown',spatial_confidence=.9)],
            relations=[],dimensions=[],ambiguities=['Not real photo accuracy'])
        structure=approvals.structure();structure['inventory'][0]['evidence_ref']='seen:seen_bed'
        reviews=[]
        def critic(body):
            self.assertEqual(sum(row.get('type')=='image_url' for row in body['messages'][-1]['content']),2)
            props=body['response_format']['json_schema']['schema']['properties']
            key=props['frame_key']['enum'][0];reviews.append(key)
            return dict(review_version=props['review_version']['enum'][0],frame_key=key,
                objects={'bed':{aspect:dict(status='contradiction' if len(reviews)==1 and aspect=='layout' else 'consistent',
                    confidence=.9,reason='Explicit offline fixture, not a photo judgement.') for aspect in ('layout','support','appearance')}})
        def correction(body):
            content=json.loads(body['messages'][-1]['content']);value=dict(content['candidate']['objects']['bed'],region='rear_right')
            return dict(patch_version='semantic-patch-1.0',
                base_revision=body['response_format']['json_schema']['schema']['properties']['base_revision']['enum'][0],
                operations=[dict(op='update',id='bed',value=value)])
        self.responses=[observation,structure,approvals.furniture(),critic,correction,critic]
        self.install_audited_fixture()
        self.broker.register_engine('fixture-engine','fixture-epoch')
        initial=SimulationSnapshot('fixture-engine','fixture-epoch','default',None,None,1,'idle',None,None,
            ('build_site_scene',),('site_scene_build_v2','generation_room_visual_v1'))
        self.broker.record_snapshot(initial)
        state=self.begin(image=True)
        descriptor=state['cards'][-1]['generation_approval']
        self.assertTrue(descriptor['render_review_approved'])
        self.assertIn('derived renders',descriptor['purpose'])
        self.assertEqual(self.wires,[]) # Settings/approval preview alone do not Build or upload.
        commands=[];errors=[];stop=Event()
        def engine():
            try:
                while not stop.wait(.01):
                    command=self.broker.claim('fixture-engine','fixture-epoch')
                    if not command:continue
                    commands.append(command)
                    revision=command.payload['scene_revision']
                    self.broker.record_receipt(CommandReceipt(command.command_id,command.command_type,'default',
                        'fixture-engine','fixture-epoch','succeeded',applied_revision=revision,build_fingerprint='fixture'))
                    self.broker.record_snapshot(replace(initial,sequence=len(commands)+1,applied_revision=revision,runtime_state='built'))
                    from PIL import Image
                    stream=BytesIO();Image.new('RGB',(64,64),'white').save(stream,format='JPEG')
                    for identity in (len(commands)*2-1,len(commands)*2):
                        if identity%2==0:time.sleep(.15)
                        self.server.viewport.exchange('fixture-engine','fixture-epoch',dict(engine_session_id='fixture-engine',stage_epoch='fixture-epoch',
                            frame=dict(frame_id=identity,applied_revision=revision,captured_at_ms=time.time()*1000,
                                width=64,height=64,camera_sequence=0,jpeg_base64=base64.b64encode(stream.getvalue()).decode()),camera_result=None))
            except BaseException as error:errors.append(error)
        worker=Thread(target=engine,daemon=True);worker.start()
        try:
            action=self.approve(state);self.call(action)
            for _ in range(400):
                final=self.call()
                if final.get('generation') and final['generation']['state'] not in ('accepted','running'):break
                time.sleep(.01)
            self.assertEqual(final['generation']['state'],'completed',final['generation'])
        finally:stop.set();worker.join(2)
        self.assertEqual(errors,[])
        self.assertEqual(len(self.wires),8);self.assertEqual(len(commands),4)
        self.assertEqual(len(commands[0].payload['scene']['objects']),4)  # Early floor and three walls.
        self.assertEqual({c.command_type for c in commands},{'build_site_scene'})
        self.assertEqual(len({c.payload['scene_revision'] for c in commands}),3)
        record=self.workflow._application.site_draft
        self.assertEqual(record.site.scene.revision,commands[-1].payload['scene_revision'])
        from twinpulse_app.project_store import ProjectStore
        stored=ProjectStore(self.workflow._application._project_store.path).load().site_draft
        self.assertEqual(stored.plan_sha256,record.plan_sha256)
        progress=final['generation']['progress']
        self.assertEqual(progress['stage_acceptance']['Isaac_Build'],'preview_passed')
        self.assertEqual(progress['stage_acceptance']['SIM_Run_Stop'],'not_run')
        ledger=json.loads(next(self.manager.root.glob('*.ledger.json')).read_text())
        self.assertEqual(len(ledger['requests']),8)
        self.assertEqual(progress['budget']['repairs'],1)
        before=len(self.wires);self.call(action);self.call()
        self.assertEqual(len(self.wires),before) # Re-query/duplicate action cannot re-upload.
