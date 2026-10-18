# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current room, saved report, ledger, authenticated chat; no devices."""
from tests.integration import test_chat_inspection as inspection_tests
from tests.integration import test_cold_start_mission as cold_tests
from twinpulse_app.chat_inspection_visual import (KIND,checked_inspection_visual,load_current_source)
from twinpulse_app.automatic_photo_store import AutomaticPhotoStore
from twinpulse_core.revisions import canonical_sha256
from copy import deepcopy
import json
import shutil
import unittest
from uuid import uuid4
from unittest.mock import patch

def save_report(root,pid,source,*,correction=True):
    """Explicit synthetic report for rejection/persistence tests, not runtime evidence."""
    identity=uuid4().hex;room=source['room'];store=AutomaticPhotoStore(root,pid)
    effective=store.current(room);event=None
    if correction:
        objects=deepcopy(effective['objects']);wall=next(o for o in objects if o['kind']=='wall')
        wall['transform']['position_m'][0]+=.05
        event=store.append(room,effective['head'],objects,action='apply',job_id=identity,map_revision='f'*64)
        effective=store.current(room)
    visual={'session_id':identity,'room_revision':effective['effective_revision'],'pose_room':[0.,0.,0.],
        'scan_room':[[.3,.4]],'trajectory_room':[[0.,0.,0.],[.01,0.,0.]],'route_room':[],'goal_room':None,
        'motion_authorized':False,'physical_demo_ready':False,'state':'ARRIVED'}
    visual['revision']=canonical_sha256(visual)
    report={'schema':'automatic-mission-report-1.0','project_id':pid,'job_id':identity,
        'state':'MISSION_ARRIVED','goal':{'mode':'SURVEY_ONLY','room_revision':effective['effective_revision']},
        'cold_start':{'stage':'SURVEY_COMPLETE','alignment_status':'ALIGNMENT_CANDIDATE'},
        'room_source':source,'room_base_revision':room['revision'],'objects_revision':effective['effective_revision'],
        'visual':visual,'motion_authorized':False,'physical_demo_ready':False}
    if event:report['photo_correction']={'applied_revision':event['revision'],
        'effective_revision':effective['effective_revision'],'goal_revalidation':'SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL'}
    report['revision']=canonical_sha256(report)
    path=root/'artifacts'/'automatic-mission'/pid/(identity+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report),encoding='utf-8')
    return {'kind':KIND,'mission_id':identity,'manifest_sha256':report['revision']},path,report

class CurrentRoomVisualTests(unittest.TestCase):
    setUp=cold_tests.ColdStartTests.setUp
    execute=cold_tests.ColdStartTests.execute
    def test_active_chat_placement_uses_current_derived_scene_and_rejects_old_scene(self):
        from tests.integration.test_automatic_photo_service import recipe
        from twinpulse_app.chat_inspection_visual import active_chat_placement,derived_scene,checked_source
        recipe(self.root,'active_room',1.)
        room,source=checked_source(load_current_source(self.root,'active_room'),'active_room')
        store=AutomaticPhotoStore(self.root,'active_room');effective=store.current(room)
        manifest=active_chat_placement(self.root,'active_room',source)
        self.assertGreaterEqual(manifest['robot_placement']['position_m'][2],0.)
        objects=deepcopy(effective['objects']);next(o for o in objects if o['kind']=='wall')['transform']['position_m'][0]+=.05
        store.append(room,effective['head'],objects,action='apply',job_id=uuid4().hex,map_revision='f'*64)
        with self.assertRaisesRegex(ValueError,'ACTIVE_CHAT_ROOM_REVISION_CHANGED'):
            active_chat_placement(self.root,'active_room',source)
        corrected=derived_scene(source,store.current(room))
        self.assertEqual(active_chat_placement(self.root,'active_room',corrected),manifest)
    def test_default_active_draft_never_uses_a_legacy_room_when_record_is_bad(self):
        from tests.integration.test_automatic_photo_service import recipe
        from twinpulse_app.chat_inspection_visual import active_chat_placement,checked_source
        from twinpulse_app.project_store import ProjectStore
        from dataclasses import replace
        recipe(self.root,'default_source',1.)
        record=ProjectStore.for_project(self.root,'default_source').load()
        ProjectStore.for_project(self.root,'default').save(replace(record,project_id='default'))
        _,scene=checked_source(load_current_source(self.root,'default'),'default')
        self.assertEqual(len(active_chat_placement(self.root,'default',scene)['robot_placement']['position_m']),3)
        ProjectStore.for_project(self.root,'default').path.write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):active_chat_placement(self.root,'default',scene)
    def test_shared_current_chat_survey_correction_report_reopens_derived_scene(self):
        job,adapter,report=self.execute('current_chat',1.,[0.,-.6,0.],[0.,0.],
            mode='SURVEY_ONLY',photo_policy='correct_walls',current_chat=True)
        self.assertEqual(job['state'],'MISSION_ARRIVED',job.get('error'))
        descriptor={'kind':KIND,'mission_id':job['job_id'],'manifest_sha256':job['report_revision']}
        scene,visual=checked_inspection_visual(self.root,'current_chat',descriptor)
        source=load_current_source(self.root,'current_chat')
        self.assertEqual(report['room_source'],source)
        self.assertEqual(scene.parent_revision,source['scene']['revision'])
        self.assertNotEqual(scene.revision,source['scene']['revision'])
        self.assertEqual(visual['route_room'],[]);self.assertIsNone(visual['goal_room'])
        self.assertFalse(visual['motion_authorized']);self.assertEqual(adapter.velocity,(0.,0.))
        self.assertEqual(checked_inspection_visual(self.root,'current_chat',descriptor)[0],scene)

    def test_failed_tampered_changed_room_and_ledger_never_fall_back(self):
        from tests.integration.test_automatic_photo_service import recipe
        recipe(self.root,'checked',1.);source=load_current_source(self.root,'checked')
        descriptor,path,report=save_report(self.root,'checked',source)
        original=path.read_bytes();scene,_=checked_inspection_visual(self.root,'checked',descriptor)
        self.assertEqual(scene.parent_revision,source['scene']['revision'])
        changed=deepcopy(source);changed['room']['input_revision']='e'*64
        changed['room']['revision']=canonical_sha256({k:v for k,v in changed['room'].items() if k!='revision'})
        with self.assertRaisesRegex(ValueError,'CURRENT_ROOM_CHANGED'):
            checked_inspection_visual(self.root,'checked',descriptor,current_source=changed)
        for key,value in (('state','FAILED'),('cleanup_error','CLEANUP_FAILED'),('physical_demo_ready',True)):
            bad={**report,key:value};bad['revision']=canonical_sha256({k:v for k,v in bad.items() if k!='revision'})
            path.write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'SURVEY_NOT_COMPLETE'):
                checked_inspection_visual(self.root,'checked',{**descriptor,'manifest_sha256':bad['revision']})
        path.write_bytes(original)
        store=AutomaticPhotoStore(self.root,'checked');current=store.current(source['room'])
        store.append(source['room'],current['head'],current['events'][-1]['before_objects'],action='rollback',job_id=uuid4().hex,map_revision='f'*64)
        with self.assertRaisesRegex(ValueError,'LEDGER_CHANGED'):checked_inspection_visual(self.root,'checked',descriptor)
        self.assertEqual(path.read_bytes(),original)
        with self.assertRaises(ValueError):checked_inspection_visual(self.root,'checked',{**descriptor,'mission_id':'../escape'})

    def test_split_archive_and_project_roots_are_explicit_not_fallback(self):
        from tests.integration.test_automatic_photo_service import recipe
        recipe(self.root,'split',1.);source=load_current_source(self.root,'split')
        descriptor,path,_=save_report(self.root,'split',source)
        archive=self.root/'separate-archive';archive.mkdir()
        shutil.copytree(self.root/'artifacts',archive/'artifacts')
        original=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'CURRENT_ROOM_UNAVAILABLE'):
            checked_inspection_visual(archive,'split',descriptor)
        scene,_=checked_inspection_visual(archive,'split',descriptor,source_root=self.root)
        self.assertEqual(scene.parent_revision,source['scene']['revision'])
        self.assertEqual(path.read_bytes(),original)

class ChatSavedVisualTests(unittest.TestCase):
    setUp=inspection_tests.ChatInspectionTests.setUp
    tearDown=inspection_tests.ChatInspectionTests.tearDown
    request=inspection_tests.ChatInspectionTests.request
    product_headers=inspection_tests.ChatInspectionTests.product_headers
    call=inspection_tests.ChatInspectionTests.call
    send=inspection_tests.ChatInspectionTests.send
    use_room_gateway=inspection_tests.ChatInspectionTests.use_room_gateway
    attach=inspection_tests.ChatInspectionTests.attach
    start_real=inspection_tests.ChatInspectionTests.start_real
    wait=inspection_tests.ChatInspectionTests.wait
    choose=inspection_tests.ChatInspectionTests.choose
    configure_inspection=inspection_tests.ChatInspectionTests.configure_inspection
    def test_completion_persists_descriptor_restart_reads_only_and_explicit_display(self):
        self.configure_inspection()
        source={'room':self.workflow.inspection_room(self.static,'default'),
                'scene':self.workflow.inspection_scene(self.static,'default')}
        descriptor,path,report=save_report(self.static,'default',source,correction=False)
        owner=self.server.chat_robot_preparation.owner
        self.mission.job={**report,'owner':owner,'started':self.mission.clock(),
            'report_status':'SAVED','report_revision':report['revision']}
        self.inspection.owner=owner;self.inspection.job_id=descriptor['mission_id']
        self.inspection.scene_revision=source['scene']['revision']
        state=self.call();self.assertTrue(state['inspection_display']['ready'])
        self.assertEqual(state['inspection_display']['descriptor'],descriptor)
        from twinpulse_app.conversation_service import ConversationService
        restored=ConversationService(self.workflow,self.server.conversation.path);restored.inspection=self.inspection
        result=restored.snapshot(owner)
        self.assertIsNone(result['restore_error']);self.assertFalse(result['inspection_display']['current_pose_available'])
        self.assertEqual(self.started,[]);self.assertEqual(self.controller.calls,['qualify'])
        with patch.object(self.broker,'submit',return_value={'command_id':'visual-only'}) as submit, \
                patch.object(self.broker,'register_site_scene',wraps=self.broker.register_site_scene) as register:
            status,value,_=self.request('/v1/product/conversation/inspection/display',
                {'descriptor':descriptor,'request_id':'display-once'},headers=self.product_headers)
            self.assertEqual(status,202,value);self.assertEqual(submit.call_args.args[1]['command_type'],'build_site_scene')
            self.assertEqual(register.call_args.kwargs['presentation']['view'],'top')
        self.assertEqual(self.started,[]);self.assertEqual(self.controller.calls,['qualify'])
