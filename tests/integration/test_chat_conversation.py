# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Chat product journey through the authenticated API, using an explicit provider fixture."""
import time
import unittest
from tests.integration.test_r5_product_api import R5ProductApiTests, png
import base64
from unittest.mock import patch


class ChatConversationTests(unittest.TestCase):
    def test_restored_navigation_hint_is_process_local_and_restores_no_authority(self):
        from twinpulse_app.conversation_service import ConversationService
        import json
        self.assertFalse(self.call()['restored_session'])
        sent = self.send('history-navigation')
        restored = ConversationService(self.workflow, self.server.conversation.path)
        state = restored.snapshot()
        self.assertTrue(state['restored_session'])
        self.assertEqual(state['messages'], sent['messages'])
        self.assertFalse(state['physical_authority'])
        self.assertNotIn('restored_session', json.loads(self.server.conversation.path.read_text(encoding='utf-8')))
        self.assertEqual(self.broker.public_state('unowned')['operations'], [])

    def test_supported_semantic_target_through_saved_product_api_uses_current_contract(self):
        from tests.integration.test_scene_changes import furnished_source
        from tests.integration.test_room_items import item
        from twinpulse_app.manual_room import manual_room_plan
        from twinpulse_app.site_draft import SiteDraftRecord
        parent = item('pallet', 'carrier', z=.06)
        parent['dimensions_m'] = [2., 2., .12]
        child = item('box', 'cargo', z=.22)
        child['dimensions_m'] = [.2, .2, .2]
        contract = dict(schema_version='photo-placement-contract-1.0', relations=[
            dict(id='carrier', relation='floor', parent_id=None, part=None, anchor='centre', elevation_m=None),
            dict(id='cargo', relation='surface', parent_id='carrier', part='deck', anchor='centre', elevation_m=None)])
        source = SiteDraftRecord.create(request_id='supported-api', provider_name='fixture', model_id='fixture',
            image_count=0, input_revision=furnished_source().input_revision,
            plan=manual_room_plan('supported_api', 5., 5., 2.6, room_items=[parent, child]),
            placement_contract=contract)
        original = source.to_dict()
        with patch('tests.integration.test_scene_changes.furnished_source', return_value=source):
            self.saved_room()
        self.workflow.resume_saved_scene('default', source.site.scene.revision, source.input_revision.digest)
        state = self.call(dict(action='message', request_id='supported-goal',
            text='Go from x=0 y=-1.8 to box', mode='new', attachment=None))
        review = state['simulation_review']
        self.assertEqual(review['target']['id'], 'cargo')
        self.assertEqual(review['approach_diagnostic']['support_parent_ids'], ['carrier'])
        self.assertIsNotNone(review['plan'])
        self.assertFalse(review['plan']['physical_authority'])
        self.assertEqual(self.workflow._application.site_draft.to_dict(), original)
        self.assertEqual(self.broker.public_state('unowned')['operations'], [])

    def test_room_props_are_current_semantic_targets_not_visual_child_names(self):
        from tests.integration.test_scene_changes import furnished_source
        from tests.integration.test_room_items import item
        from twinpulse_app.manual_room import manual_room_plan
        from twinpulse_app.site_draft import SiteDraftRecord
        source=SiteDraftRecord.create(request_id='two-props',provider_name='fixture',model_id='fixture',image_count=0,
            input_revision=furnished_source().input_revision,
            plan=manual_room_plan('two_props',6.,6.,2.6,room_items=[
                item('box','arbitrary_left',x=-1.5,y=.8),
                item('box','arbitrary_right',x=1.5,y=.8)]))
        original=source.to_dict()
        with patch('tests.integration.test_scene_changes.furnished_source',return_value=source):self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        state=self.call({'action':'message','request_id':'prop-goal',
            'text':'Go from x=0 y=-2 to box','mode':'new','attachment':None})
        self.assertIsNone(state['simulation_review']['plan'])
        choices=state['simulation_review']['choices']
        self.assertEqual({row['id'] for row in choices},{'arbitrary_left','arbitrary_right'})
        self.assertTrue(all(row['label']=='box' and len(row['object_ids'])>=1 for row in choices))
        card=state['cards'][-1]
        result=self.call({'action':'answer','request_id':'choose-prop','card_id':card['id'],
            'choice_id':'object_1','expected_session_revision':card['expected_session_revision']})
        self.assertEqual(result['simulation_review']['target']['id'],'arbitrary_right')
        self.assertIsNotNone(result['simulation_review']['plan'])
        self.assertFalse(result['simulation_review']['plan']['physical_authority'])
        self.assertEqual(self.workflow._application.site_draft.to_dict(),original)
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_goal_failure_keeps_conversation_and_linked_execution_diagnosis(self):
        from twinpulse_core.simulation_goal import GoalApproachError
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        diagnostic=dict(schema_version='goal-approach-diagnostic-1.0',
            termination_code='NO_ACCEPTED_EXTERIOR_CANDIDATE',physical_authority=False,
            attempts=[dict(point=[0.,0.],accepted=False) for _ in range(16)],
            reason_counts={'START_OR_GOAL_BLOCKED':16})
        with patch('twinpulse_core.simulation_goal.goal_review',side_effect=GoalApproachError(diagnostic)):
            state=self.call(dict(action='message',request_id='blocked-goal',
                text='Go from x=0 y=-1.4 to bed',mode='new',attachment=None))
        event=next(e for e in state['events'] if e['type']=='simulation_goal_rejected')
        self.assertEqual(event['payload']['goal_diagnostic'],diagnostic)
        self.assertEqual(event['payload']['goal_error_code'],'SIM_TARGET_NO_REACHABLE_APPROACH')
        self.assertEqual(event['payload']['request_id'],'blocked-goal')
        self.assertEqual(event['payload']['scene_revision'],source.site.scene.revision)
        store=self.workflow._application.diagnostics;store.flush()
        execution=next(e for e in store.list()['executions'] if e['stage']=='simulation_goal_review')
        detail=store.detail(execution['execution_id'])
        values=[span['metadata'] for span in detail['spans']]
        self.assertTrue(any(v.get('termination_code')=='NO_ACCEPTED_EXTERIOR_CANDIDATE'
                            and v.get('candidate_count')==16 for v in values))
        self.assertTrue(any(v.get('error_code')=='START_OR_GOAL_BLOCKED' for v in values))
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_photo_generation_does_not_inject_fixed_room_inventory(self):
        self.use_room_gateway()
        first=self.send(image=True);self.call(self.answer(first))
        for _ in range(100):
            state=self.call()
            if state['generation']['state']!='running':break
            time.sleep(.02)
        self.assertEqual(state['generation']['state'],'completed')
        saved=self.workflow.snapshot()
        self.assertEqual(saved['phase'],'draft_ready')
        self.assertIsNone(saved['photo_inventory'])
        self.assertIsNone(state['simulation_review'])
        self.assertIsNone(state['robot_id'])
        self.assertFalse(any(e['type']=='simulation_preview_prepared' for e in state['events']))
        self.assertNotIn('Photo hazards still require placement',state['messages'][-1]['content'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def use_room_gateway(self):
        from twinpulse_provider import SiteGenerationResult
        from tests.integration.test_scene_changes import furnished_source
        class Gateway:
            def cancel_active(self): pass
            async def generate(self, request):
                return SiteGenerationResult(request.request_id,'explicit-room-fixture','fixture',len(request.images),furnished_source().plan)
        self.workflow._application.set_generation_gateway(Gateway())

    def cold_workflow(self):
        from twinpulse_app import ApplicationService, CommandBroker, ProductWorkflow, ProjectStore
        from twinpulse_core import InputArtifactStore
        app=self.workflow._application
        broker=CommandBroker()
        workflow=ProductWorkflow(ApplicationService(app._generation_gateway,
            project_store=ProjectStore(app._project_store.path),
            artifact_store=InputArtifactStore(app._artifact_store.root)),broker,mode='explicit_fixture',
            generation_settings_getter=self.workflow._generation_settings_getter,
            provider_state_getter=self.workflow._provider_state_getter)
        return workflow,broker

    def test_explicit_robot_generation_prepares_sim_route_once_and_restores_as_history(self):
        self.use_room_gateway()
        first=self.send(image=True,text='Create a compact warehouse for TurtleBot3 Burger')
        self.assertIsNone(first['simulation_review'])
        answer=self.answer(first)
        self.call(answer)
        for _ in range(100):
            state=self.call()
            if state['generation']['state']!='running':break
            time.sleep(.02)
        self.assertEqual(state['generation']['state'],'completed')
        review=state['simulation_review']
        self.assertEqual(review['request_id'],answer['request_id'])
        self.assertEqual(review['start_source'],'planned_sim_spawn')
        self.assertEqual(state['robot_id'],'turtlebot3_burger')
        self.assertEqual(self.workflow._application.site_draft.image_count,1)
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])
        self.call(answer);self.call()
        self.assertEqual(len([e for e in self.call()['events'] if e['type']=='simulation_preview_prepared']),1)
        from twinpulse_app.conversation_service import ConversationService
        cold,broker=self.cold_workflow()
        with patch.object(cold,'simulation_preview') as preview,patch.object(broker,'register_simulation_plan') as register:
            restored=ConversationService(cold,self.server.conversation.path)
            self.assertIsNone(restored.snapshot()['restore_error'])
            self.assertEqual(restored.snapshot()['simulation_review'],review)
            self.assertEqual(broker._simulation_plans,{})
            self.assertFalse(hasattr(cold,'_simulation_seed'))
            cold.resume_saved_scene('default',review['scene_revision'],cold.snapshot()['site_draft']['input_revision'])
            missing=restored.dispatch({'action':'message','request_id':'goal-after-cold','text':'Go to the bed','mode':'new','attachment':None})
            self.assertIsNone(missing['simulation_review'])
            self.assertIn('SIM_START_REQUIRED',missing['messages'][-1]['content'])
            preview.assert_not_called();register.assert_not_called()
        next_goal=restored.dispatch({'action':'message','request_id':'goal-after-create',
            'text':'Go from x=0 y=-1.4 to x=0 y=-0.4','mode':'new','attachment':None})
        self.assertIsNotNone(next_goal['simulation_review']['plan'])
        self.assertFalse(next_goal['physical_authority'])

    def test_preview_failure_preserves_generated_scene_and_never_builds(self):
        self.use_room_gateway()
        from twinpulse_app.command_broker import BrokerError
        first=self.send(text='Create a compact warehouse for TurtleBot3 Burger')
        with patch.object(self.workflow,'simulation_preview',side_effect=BrokerError('simulation_preview_rejected','SIM_PREVIEW_NO_REACHABLE_ROUTE')):
            self.call(self.answer(first))
            for _ in range(100):
                state=self.call()
                if state['generation']['state']!='running':break
                time.sleep(.02)
        self.assertEqual(state['generation']['state'],'completed')
        self.assertEqual(self.workflow.snapshot()['phase'],'draft_ready')
        self.assertIsNone(state['simulation_review'])
        self.assertEqual(state['messages'][-1]['status'],'failed')
        self.assertIn('SIM_PREVIEW_NO_REACHABLE_ROUTE',state['messages'][-1]['content'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_no_robot_generation_keeps_environment_and_later_explicit_sim_goal_is_separate(self):
        self.use_room_gateway()
        # A new environment request cannot borrow a previous SIM selection.
        self.server.conversation._state['robot_id']='turtlebot3_burger'
        self.server.conversation._state['mode']='SIM'
        first=self.send(text='방을 만들고 로봇은 추가하지마')
        with patch.object(self.workflow,'simulation_preview') as preview:
            self.call(self.answer(first))
            for _ in range(100):
                state=self.call()
                if state['generation']['state']!='running':break
                time.sleep(.02)
            preview.assert_not_called()
        self.assertEqual(state['generation']['state'],'completed')
        self.assertIsNone(state['robot_id'])
        self.assertIsNone(state['simulation_review'])
        self.assertFalse(any(c['kind']=='robot_selection' for c in state['cards']))
        self.assertIn('without a SIM robot',state['messages'][-1]['content'])
        source=self.workflow._application.site_draft.to_dict()
        from twinpulse_app.conversation_service import ConversationService
        cold,broker=self.cold_workflow()
        with patch.object(cold,'simulation_preview') as preview,patch.object(broker,'register_simulation_plan') as register:
            restored=ConversationService(cold,self.server.conversation.path)
            self.assertIsNone(restored.snapshot()['restore_error'])
            self.assertIsNone(restored.snapshot()['simulation_review'])
            self.assertIsNone(restored.snapshot()['robot_id'])
            current=cold.snapshot()['site_draft']
            cold.resume_saved_scene('default',current['revision'],current['input_revision'])
            rejected=restored.dispatch(dict(action='message',request_id='no-implicit-start',text='Go to bed',mode='new',attachment=None))
            preview.assert_not_called();register.assert_not_called()
            self.assertEqual(broker._simulation_plans,{})
        self.assertIsNone(rejected['robot_id'])
        self.assertIsNone(rejected['simulation_review'])
        self.assertIn('Please provide the simulated start position',rejected['messages'][-1]['content'])
        ready=restored.dispatch(dict(action='message',request_id='explicit-sim-start',
            text='Go from x=0 y=-1.4 to x=0 y=-0.4',mode='new',attachment=None))
        self.assertEqual(ready['robot_id'],'turtlebot3_burger')
        self.assertEqual(ready['simulation_review']['start_source'],'explicit_start')
        self.assertEqual(ready['simulation_review']['scene_revision'],cold.snapshot()['site_draft']['revision'])
        self.assertFalse(ready['simulation_review']['plan']['physical_authority'])
        self.assertEqual(cold._application.site_draft.to_dict(),source)
        self.assertEqual(broker.public_state('unowned')['operations'],[])

    def test_unsupported_sim_robot_waits_for_explicit_alternative_before_generation(self):
        first=self.call({'action':'message','request_id':'spot-request','text':'Build my home for a Spot quadruped',
                         'mode':'new','attachment':None})
        state=self.call(self.answer(first))
        self.assertIsNone(state['generation'])
        self.assertEqual(self.workflow.snapshot()['phase'],'input_ready')
        card=state['cards'][-1]
        self.assertEqual(card['kind'],'robot_selection')
        self.assertEqual(card['choices'][0]['label'],'Use TurtleBot3 Burger instead')
        self.assertEqual(state['mode'],'SIM')
        self.use_room_gateway()
        state=self.call({'action':'answer','request_id':'explicit-alternative','card_id':card['id'],
                         'choice_id':'turtlebot3_burger','expected_session_revision':card['expected_session_revision']})
        for _ in range(100):
            state=self.call()
            if state['generation']['state']!='running':break
            time.sleep(.02)
        self.assertEqual(state['generation']['state'],'completed')
        self.assertEqual(state['robot_id'],'turtlebot3_burger')
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    setUp = R5ProductApiTests.setUp
    tearDown = R5ProductApiTests.tearDown
    request = R5ProductApiTests.request
    product_headers = R5ProductApiTests.product_headers

    def call(self, action=None):
        status, body, _ = self.request('/v1/product/conversation', action, headers=self.product_headers)
        self.assertEqual(status, 200, body)
        return body

    def send(self, request_id='message-1', image=False, text='Create a compact warehouse'):
        return self.call({'action': 'message', 'request_id': request_id, 'text': text,
                          'mode': 'new', 'attachment': {'name': 'room.png', 'media_type': 'image/png',
                          'content_base64': base64.b64encode(png()).decode()} if image else None})

    def test_question_blocks_generation_duplicate_message_and_choice(self):
        initial = self.send()
        self.assertEqual(self.workflow.snapshot()['phase'], 'input_ready')
        self.assertEqual(self.call()['cards'][-1]['kind'], 'robot_presence')
        self.assertEqual(self.send(), initial)
        card = initial['cards'][-1]
        answer = {'action': 'answer', 'request_id': 'answer-1', 'card_id': card['id'], 'choice_id': 'sim', 'expected_session_revision': card['expected_session_revision']}
        self.call(answer)
        self.call(answer)
        for _ in range(100):
            state = self.call()
            if state['generation']['state'] != 'running': break
            time.sleep(.02)
        self.assertEqual(state['generation']['state'], 'completed')
        self.assertEqual(len([e for e in state['events'] if e['type'] == 'generation_started']), 1)
        self.assertEqual(len([m for m in state['messages'] if m['role'] == 'user']), 2)
        self.assertEqual(self.broker.public_state('unowned')['operations'], [])
        self.assertFalse(state['physical_authority'])

    def test_real_robot_selection_never_starts_motion(self):
        first = self.send(image=True)
        selected = self.call({'action': 'answer', 'request_id': 'real-1', 'card_id': first['cards'][-1]['id'], 'choice_id': 'real', 'expected_session_revision': first['cards'][-1]['expected_session_revision']})
        self.assertEqual(self.workflow.snapshot()['phase'], 'input_ready')
        self.assertEqual(selected['cards'][-1]['kind'], 'robot_selection')
        status, error, _ = self.request('/v1/product/conversation', {'action': 'answer', 'request_id': 'bad',
            'card_id': first['cards'][-1]['id'], 'choice_id': 'sim', 'expected_session_revision': first['cards'][-1]['expected_session_revision']}, headers=self.product_headers)
        self.assertEqual(status, 409)
        self.assertEqual(error['error']['code'], 'card_expired')

    def test_validation_failure_retains_question_and_auth_is_required(self):
        self.send()
        status, _, _ = self.request('/v1/product/conversation', {'action': 'message', 'request_id': 'bad',
            'text': 'new message', 'mode': 'new', 'attachment': None}, headers=self.product_headers)
        self.assertEqual(status, 409)
        self.assertEqual(self.call()['cards'][-1]['state'], 'waiting')
        status, _, _ = self.request('/v1/product/conversation')
        self.assertEqual(status, 401)

    def test_persisted_choice_and_restart_does_not_resume_generation(self):
        first = self.send()
        from twinpulse_app.conversation_service import ConversationService
        restarted = ConversationService(self.workflow, self.server.conversation.path)
        self.assertEqual(restarted.snapshot()['cards'], first['cards'])
        self.assertFalse(restarted.snapshot()['physical_authority'])

    def test_idempotency_key_cannot_be_reused_for_different_payload(self):
        self.send()
        status, body, _ = self.request('/v1/product/conversation', {'action': 'message', 'request_id': 'message-1',
            'text': 'different', 'mode': 'new', 'attachment': None}, headers=self.product_headers)
        self.assertEqual(status, 409)
        self.assertEqual(body['error']['code'], 'request_id_conflict')

    def answer(self, state):
        card = state['cards'][-1]
        return {'action':'answer','request_id':'answer-1','card_id':card['id'],'choice_id':'sim',
                'expected_session_revision':card['expected_session_revision']}

    def test_cancel_retains_history_and_never_restarts(self):
        first=self.send()
        self.call(self.answer(first))
        state=self.call()
        result=self.call({'action':'cancel','request_id':'cancel-1','operation_id':state['generation']['operation_id']})
        self.assertIn(result['generation']['state'], {'cancelled','completed'})
        self.assertEqual(len([e for e in result['events'] if e['type']=='generation_started']),1)
        self.assertFalse(result['physical_authority'])

    def test_cancel_settling_hint_is_bound_to_job_and_not_persisted(self):
        # Supplementary snapshot fixture only, not a user-flow acceptance.
        first=self.send()
        self.call(self.answer(first))
        service=self.server.conversation
        with service._lock,patch.object(service,'_sync_generation'):
            job=service._state['generation']
            job['state']='cancelled'
            with patch.object(self.workflow,'generation_settling',return_value=True) as settling:
                public=service.snapshot()
                settling.assert_called_once_with(job['generation_id'])
                self.assertEqual(public['generation_settling'],dict(
                    operation_id=job['operation_id'],generation_id=job['generation_id']))
            with patch.object(self.workflow,'generation_settling',return_value=False):
                self.assertIsNone(service.snapshot()['generation_settling'])
            service._persist()
            import json
            self.assertNotIn('generation_settling',json.loads(service.path.read_text(encoding='utf-8')))

    def test_failure_is_visible_and_no_retry_on_refresh(self):
        first=self.send()
        from twinpulse_app.command_broker import BrokerError
        with patch.object(self.workflow,'start_generation',side_effect=BrokerError('provider_missing','Provider configuration required')) as start:
            result=self.call(self.answer(first))
            self.assertEqual(result['generation']['state'],'failed')
            self.assertEqual(result['generation']['error']['code'],'provider_missing')
            self.call();self.call(self.answer(first))
            self.assertEqual(start.call_count,1)

    def test_save_failure_prevents_external_start(self):
        first=self.send()
        from twinpulse_app.command_broker import BrokerError
        with patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','Disk write failed')):
            with patch.object(self.workflow,'start_generation') as start:
                status,_,_=self.request('/v1/product/conversation',self.answer(first),headers=self.product_headers)
                self.assertEqual(status,409)
                start.assert_not_called()
        self.assertEqual(self.call()['cards'][-1]['state'],'waiting')

    def test_restart_interrupts_in_flight_operation_without_resuming(self):
        first=self.send()
        self.call(self.answer(first))
        from twinpulse_app.conversation_service import ConversationService
        with patch.object(self.workflow,'start_generation') as start:
            recovered=ConversationService(self.workflow,self.server.conversation.path).snapshot()
            self.assertEqual(recovered['generation']['state'],'interrupted')
            start.assert_not_called()

    def test_corrupt_conversation_does_not_crash_backend_or_overwrite_source(self):
        from twinpulse_app.conversation_service import ConversationService
        path=self.static/'corrupt.conversation.json';path.write_text('[]',encoding='utf-8')
        restored=ConversationService(self.workflow,path)
        self.assertEqual(restored.snapshot()['restore_error']['code'],'conversation_restore_invalid')
        self.assertEqual(path.read_text(encoding='utf-8'),'[]')

    def test_invalid_conversation_polling_never_syncs_transaction_or_overwrites_original(self):
        from twinpulse_app.conversation_service import ConversationService
        from twinpulse_app.command_broker import BrokerError
        path=self.static/'corrupt-with-transaction.json';path.write_text('[]',encoding='utf-8')
        restored=ConversationService(self.workflow,path)
        with patch.object(restored,'_sync_feedback') as sync:
            restored.snapshot();restored.snapshot()
            sync.assert_not_called()
            with self.assertRaises(BrokerError):restored.dispatch({'action':'cancel'})
            sync.assert_not_called()
        with self.assertRaises(BrokerError):restored._persist()
        self.assertEqual(path.read_text(encoding='utf-8'),'[]')

    def test_sim_only_presence_card_is_valid_durable_history(self):
        from twinpulse_app.conversation_service import ConversationService
        with patch.dict('os.environ',{'TWINPULSE_SIM_ONLY':'1'}):
            first=self.send('SIM alpha history')
            self.assertEqual({c['id'] for c in first['cards'][-1]['choices']},{'sim'})
            restored=ConversationService(self.workflow,self.server.conversation.path)
            self.assertIsNone(restored.snapshot()['restore_error'])
            self.assertEqual(restored.snapshot()['messages'],first['messages'])

    def test_discarded_response_does_not_raise_or_reexecute(self):
        from unittest.mock import Mock
        from twinpulse_app.api import LocalApiServer
        request=Mock();request.wfile.write.side_effect=ConnectionAbortedError('reload fixture')
        request.connection.gettimeout.return_value=None
        LocalApiServer._json(request,200,{'accepted_request_ids':['committed-id']})
        self.assertTrue(request.close_connection);self.assertEqual(request.wfile.write.call_count,1)

    def test_thumbnail_requires_auth_and_does_not_expose_raw_input(self):
        state=self.send(image=True)
        attachment=state['messages'][0]['attachments'][0]
        status,body,_=self.request(attachment['preview_url'],headers=self.product_headers)
        self.assertEqual(status,200);self.assertTrue(body.startswith(b'\x89PNG'))
        status,_,_=self.request(attachment['preview_url']);self.assertEqual(status,401)
        self.assertNotIn('content_base64',str(state))
        self.assertNotIn('thumbnails',state)

    def test_status_question_preserves_pending_choice(self):
        first=self.send()
        result=self.call({'action':'message','request_id':'status-1','text':'status','mode':'new','attachment':None})
        self.assertEqual(result['cards'],first['cards'])
        self.assertIn('Waiting for your choice',result['messages'][-1]['content'])

    def test_external_input_change_expires_old_choice_without_generation(self):
        first=self.send()
        self.workflow.select_input({'name':None,'media_type':None,'content_base64':None,'input_kind':'auto',
            'prompt':'A different input','sidecar_name':None,'sidecar_content_base64':None})
        with patch.object(self.workflow,'start_generation') as start:
            result=self.call(self.answer(first));start.assert_not_called()
        self.assertEqual(result['cards'][-1]['state'],'expired')
        self.assertEqual(self.workflow.snapshot()['phase'],'input_ready')

    def test_schema_and_stale_revision_and_unknown_choice_are_rejected(self):
        first=self.send();answer=self.answer(first)
        for body in [{**answer,'choice_id':'drive'}, {**answer,'expected_session_revision':-1}, {**answer,'motor':True}]:
            status,_,_=self.request('/v1/product/conversation',body,headers=self.product_headers)
            self.assertIn(status,{400,409})
        self.assertEqual(self.call()['cards'][-1]['state'],'waiting')
        for body in [{**answer,'expected_session_revision':True}, {**answer,'choice_id':[]},
                     {'action':{},'request_id':'invalid'}, {'action':'message','request_id':'invalid','text':'test','mode':[],'attachment':None}]:
            status,_,_=self.request('/v1/product/conversation',body,headers=self.product_headers)
            self.assertEqual(status,400)

    def saved_room(self):
        from tests.integration.test_scene_changes import furnished_source
        from twinpulse_app.project_store import ProjectRecord
        source=furnished_source()
        record=ProjectRecord(project_id='default',latest_input=source.input_revision,site_draft=source)
        app=self.workflow._application
        app._artifact_store.save(source.input_revision, ())
        app._project_store.save(record);app._project=record
        self.workflow._phase='restore_review_required'
        return source

    def test_chat_add_and_change_use_saved_revision_and_preserve_original(self):
        source=self.saved_room()
        state=self.call({'action':'message','request_id':'edit-1','text':'Add a chair x=0.8 y=-1.4','mode':'add','attachment':None})
        card=state['cards'][-1];self.assertEqual(card['kind'],'scene_edit')
        operation={'action':'answer','request_id':'edit-apply','card_id':card['id'],'choice_id':'apply',
                   'expected_session_revision':card['expected_session_revision']}
        result=self.call(operation);self.call(operation)
        site=self.workflow.snapshot()['site_draft']
        self.assertNotEqual(site['revision'],source.site.scene.revision)
        self.assertEqual(self.workflow._application.site_draft.to_dict(),source.to_dict())
        self.assertEqual(len([event for event in result['events'] if event['type']=='scene_edit_completed']),1)
        changed=self.call({'action':'message','request_id':'edit-2','text':'Move chair x=0.5 y=-1.4 yaw=90','mode':'change','attachment':None})
        next_card=changed['cards'][-1]
        self.call({'action':'answer','request_id':'edit-cancel','card_id':next_card['id'],'choice_id':'cancel',
                   'expected_session_revision':next_card['expected_session_revision']})
        self.assertEqual(self.workflow.snapshot()['site_draft']['revision'],site['revision'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_chat_edit_requests_missing_placement_without_inventing_coordinates(self):
        source=self.saved_room()
        result=self.call({'action':'message','request_id':'edit-1','text':'Add a chair','mode':'add','attachment':None})
        self.assertIn('Provide X and Y',result['messages'][-1]['content'])
        self.assertEqual(result['cards'],[])
        self.assertEqual(self.workflow._application.site_draft.to_dict(),source.to_dict())

    def test_edit_apply_unexpected_error_is_recorded_and_not_repeated(self):
        self.saved_room()
        state=self.call({'action':'message','request_id':'edit-1','text':'Add chair x=0.8 y=-1.4','mode':'add','attachment':None})
        card=state['cards'][-1]
        action={'action':'answer','request_id':'apply-1','card_id':card['id'],'choice_id':'apply','expected_session_revision':card['expected_session_revision']}
        with patch.object(self.workflow,'apply_scene_edit',side_effect=RuntimeError('private diagnostic never exposed')) as apply:
            result=self.call(action);self.call(action);self.assertEqual(apply.call_count,1)
        self.assertEqual(result['messages'][-1]['status'],'failed')
        self.assertEqual(result['events'][-1]['payload']['error_type'],'RuntimeError')
        self.assertNotIn('private diagnostic',str(result))

    def test_reopen_saved_scene_is_idempotent_and_never_builds(self):
        source=self.saved_room()
        action={'action':'resume','request_id':'reopen-1','expected_scene_revision':source.site.scene.revision,
                'expected_input_revision':source.input_revision.digest}
        with patch.object(self.workflow,'resume_saved_scene',wraps=self.workflow.resume_saved_scene) as reopen:
            result=self.call(action);self.call(action);self.assertEqual(reopen.call_count,1)
        self.assertEqual(result['events'][-1]['type'],'scene_reopened')
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_resume_failure_keeps_error_and_does_not_reexecute(self):
        self.saved_room()
        action={'action':'resume','request_id':'reopen-1','expected_scene_revision':'wrong','expected_input_revision':'wrong'}
        with patch.object(self.workflow,'resume_saved_scene',wraps=self.workflow.resume_saved_scene) as reopen:
            result=self.call(action);self.call(action);self.assertEqual(reopen.call_count,1)
        self.assertEqual(result['events'][-1]['type'],'scene_reopen_failed')
        self.assertEqual(result['messages'][-1]['status'],'failed')

    def test_corrupted_nested_cards_are_preserved_and_block_mutation(self):
        import json
        from twinpulse_app.conversation_service import ConversationService
        self.send()
        path=self.server.conversation.path
        saved=json.loads(path.read_text(encoding='utf-8'));saved['cards'][0]['choices'][0]['label']={}
        path.write_text(json.dumps(saved),encoding='utf-8');before=path.read_bytes()
        recovered=ConversationService(self.workflow,path)
        self.assertIsNotNone(recovered.snapshot()['restore_error'])
        self.assertEqual(path.read_bytes(),before)

    def test_clear_text_choice_is_gated_like_button_and_does_not_authorize_robot(self):
        self.send()
        result=self.call({'action':'message','request_id':'text-real','text':'I have a robot','mode':'new','attachment':None})
        self.assertEqual(result['mode'],'REAL');self.assertEqual(result['cards'][-1]['kind'],'robot_selection')
        self.assertEqual(self.workflow.snapshot()['phase'],'input_ready')
        result=self.call({'action':'message','request_id':'text-burger','text':'Burger3','mode':'new','attachment':None})
        self.assertEqual(result['robot_id'],'turtlebot3_burger');self.assertFalse(result['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_edit_queued_during_generation_becomes_preview_only_after_terminal(self):
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        service=self.server.conversation
        service._state['generation']={'state':'running','operation_id':'queue-test','generation_id':None,
            'summary':'Explicit generation fixture','last_progress_at':'now','started_at':'now','can_cancel':True,'error':None}
        self.workflow._phase='generating'
        request={'action':'message','request_id':'queued-edit','text':'Add chair x=0.8 y=-1.4','mode':'add','attachment':None}
        with patch.object(self.workflow,'has_active_generation',return_value=True):
            result=self.call(request);self.call(request)
            self.assertEqual(result['queued_edit']['text'],request['text']);self.assertEqual(result['cards'],[])
        self.workflow._phase='draft_ready'
        result=self.call()
        self.assertIsNone(result['queued_edit']);self.assertEqual(result['cards'][-1]['kind'],'scene_edit')
        self.assertEqual(len([event for event in result['events'] if event['type']=='edit_queued']),1)
        self.assertEqual(self.workflow.snapshot()['site_draft']['revision'],source.site.scene.revision)

    def test_navigation_plans_in_same_chat_without_edits_or_commands_and_is_idempotent(self):
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        body={'action':'message','request_id':'goal-1','text':'Go from x=0 y=-1.4 to x=0 y=-0.4','mode':'new','attachment':None}
        result=self.call(body);self.assertEqual(self.call(body),result)
        review=result['simulation_review'];self.assertIsNotNone(review['plan'])
        self.assertEqual(result['robot_id'],'turtlebot3_burger')
        self.assertEqual(review['scene_revision'],source.site.scene.revision)
        self.assertFalse(review['plan']['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])
        self.assertEqual(self.workflow._application.site_draft.to_dict(),source.to_dict())
        from twinpulse_app.conversation_service import ConversationService
        restored=ConversationService(self.workflow,self.server.conversation.path)
        self.assertIsNone(restored.snapshot()['restore_error'])
        self.assertEqual(restored.snapshot()['simulation_review'],review)
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_sim_goal_records_robot_only_for_supported_current_revision_plan(self):
        from copy import deepcopy
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        text='Go from x=0 y=-1.4 to x=0 y=-0.4'
        checked=self.workflow.simulation_goal(text)
        for index,change in enumerate(('review_revision','plan_revision','asset')):
            result=deepcopy(checked)
            if change=='review_revision':result['scene_revision']='old-revision'
            elif change=='plan_revision':result['plan']['scene_revision']='old-revision'
            else:result['plan']['asset_id']='unsupported-model'
            with self.subTest(change=change),patch.object(self.workflow,'simulation_goal',return_value=result):
                self.server.conversation._review_navigation(text,'stale-plan-'+str(index))
                self.assertIsNone(self.server.conversation._state['robot_id'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])
        self.assertEqual(self.workflow._application.site_draft.to_dict(),source.to_dict())

    def test_explicit_change_and_add_are_not_overridden_by_navigation_language(self):
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        for mode,text in [('change','침대는 그대로 두고 책상을 오른쪽으로 0.2m 이동해줘. 다른 물체는 바꾸지 마.'),
                          ('add','Move to the new desk layout and add a chair')]:
            body={'action':'message','request_id':'explicit-'+mode,'text':text,'mode':mode,'attachment':None}
            with patch.object(self.server.conversation,'_edit_message') as edit,patch.object(self.server.conversation,'_review_navigation') as navigation:
                self.call(body)
                edit.assert_called_once_with(body)
                navigation.assert_not_called()
        self.assertEqual(self.workflow._application.site_draft.to_dict(),source.to_dict())
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_navigation_missing_start_and_real_rejection_are_recorded(self):
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        body={'action':'message','request_id':'missing-start','text':'Go to bed','mode':'new','attachment':None}
        result=self.call(body);self.assertIn('SIM_START_REQUIRED',result['messages'][-1]['content'])
        self.assertIn('not a measured robot location',result['messages'][-1]['content'])
        self.assertIsNone(result['robot_id'])
        self.assertIsNone(result['simulation_review'])
        self.server.conversation._state['mode']='REAL'
        result=self.call({**body,'request_id':'real-goal'})
        self.assertIn('current_goal_preview_unavailable',result['messages'][-1]['content'])
        self.assertIn('saved survey pose is historical',result['messages'][-1]['content'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_ambiguous_navigation_choice_rechecks_scene_and_does_not_generate(self):
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        choice={'id':'desk','label':'desk','object_ids':['desk'],'bounds':[0,1,0,1]}
        with patch.object(self.workflow,'simulation_goal',return_value={'plan':None,'target':None,'choices':[choice,{**choice,'id':'desk2'}],
                'drawing':{'bounds':[-2,2,-2,2],'boxes':[],'discs':[]},'scene_revision':source.site.scene.revision,'start_source':'explicit_start'}):
            state=self.call({'action':'message','request_id':'ambiguous','text':'Go to desk','mode':'new','attachment':None})
        card=state['cards'][-1];self.assertEqual(card['kind'],'simulation_target')
        self.assertIsNone(state['robot_id'])
        with patch.object(self.workflow,'simulation_goal',side_effect=__import__('twinpulse_app.command_broker',fromlist=['BrokerError']).BrokerError('simulation_scene_stale','Scene changed')) as goal:
            result=self.call({'action':'answer','request_id':'select-desk','card_id':card['id'],'choice_id':'object_1','expected_session_revision':card['expected_session_revision']})
        goal.assert_called_once_with('Go to desk',expected_revision=source.site.scene.revision,selection='desk2')
        self.assertIsNone(result['simulation_review']);self.assertIn('simulation_scene_stale',result['messages'][-1]['content'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_current_sim_pose_overrides_supplied_start_and_lost_pose_rejected(self):
        from twinpulse_core import SimulationSnapshot
        source=self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        self.broker.register_engine('sim-engine','sim-stage')
        snap=SimulationSnapshot(engine_session_id='sim-engine',stage_epoch='sim-stage',project_id='default',
            applied_revision=source.site.scene.revision,run_id='prior-plan',sequence=1,runtime_state='paused',
            position_m=(0.,-1.4,.02),yaw_rad=0.,telemetry_available=True,
            safety_state=None,safety_reason=None,permitted_commands=('pause','get_state'),
            capabilities=('simulation','site_simulation_v1'))
        self.broker.record_snapshot(snap)
        body={'action':'message','request_id':'current-pose','text':'Go from x=1 y=1 to x=0 y=-0.4','mode':'new','attachment':None}
        result=self.call(body)
        self.assertEqual(result['simulation_review']['plan']['start'],[0.,-1.4])
        self.assertEqual(result['simulation_review']['start_source'],'current_sim_pose')
        from dataclasses import replace
        self.broker.record_snapshot(replace(snap,sequence=2,telemetry_available=False,position_m=None,yaw_rad=None))
        result=self.call({**body,'request_id':'lost-pose'})
        self.assertIsNone(result['simulation_review'])
        self.assertIn('simulation_pose_unavailable',result['messages'][-1]['content'])

    def test_stop_is_journal_only_and_does_not_dismiss_question_or_restore_authority(self):
        self.send()
        result=self.call({'action':'message','request_id':'stop-1','text':'Stop simulation','mode':'new','attachment':None})
        self.assertEqual(result['cards'][-1]['state'],'waiting')
        self.assertIn('not proof of a stop',result['messages'][-1]['content'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_real_local_api_ambiguous_objects_select_one_without_build_or_generation(self):
        from tests.integration.test_scene_changes import furnished_source
        from twinpulse_app.manual_room import manual_room_plan
        from twinpulse_app.site_draft import SiteDraftRecord
        from twinpulse_app.conversation_service import ConversationService
        source=SiteDraftRecord.create(request_id='two-beds',provider_name='fixture',model_id='fixture',image_count=0,
            input_revision=furnished_source().input_revision,
            plan=manual_room_plan('two_beds',6.,6.,2.6,[{'kind':'bed','center_m':[-1.5,.8],'yaw_deg':0},
                {'kind':'bed','center_m':[1.5,.8],'yaw_deg':0}]))
        with patch('tests.integration.test_scene_changes.furnished_source',return_value=source):self.saved_room()
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        state=self.call({'action':'message','request_id':'two-beds-goal','text':'Go from x=0 y=-2 to the bed','mode':'new','attachment':None})
        self.assertIsNone(state['simulation_review']['plan'])
        card=state['cards'][-1];self.assertEqual(card['kind'],'simulation_target');self.assertEqual(len(card['choices']),3)
        event=next(e for e in state['events'] if e['type']=='simulation_goal_clarification')
        self.assertEqual(event['payload']['request_id'],'two-beds-goal')
        self.assertEqual(event['payload']['card_id'],card['id']);self.assertEqual(event['payload']['choices'],2)
        self.assertEqual(event['payload']['scene_revision'],source.site.scene.revision)
        restored=ConversationService(self.workflow,self.server.conversation.path)
        self.assertIsNone(restored.snapshot()['restore_error'])
        answer={'action':'answer','request_id':'choose-second-bed','card_id':card['id'],'choice_id':'object_1','expected_session_revision':card['expected_session_revision']}
        result=self.call(answer);self.assertEqual(self.call(answer),result)
        self.assertEqual(result['simulation_review']['target']['id'],'furn_2_bed')
        self.assertIsNotNone(result['simulation_review']['plan'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])


if __name__ == '__main__': unittest.main()
