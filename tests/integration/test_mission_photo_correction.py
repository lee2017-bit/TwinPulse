# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned revision transitions, no device/qualification/fit-success injection."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from twinpulse_app.automatic_photo_store import AutomaticPhotoStore,load_automatic_room
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.mission_photo_correction import corrected_effective_objects
from twinpulse_core.adaptive_mission_contract import nominal_room
from twinpulse_core.revisions import canonical_sha256
from tests.integration.test_automatic_photo_service import recipe
from tests.integration.test_automatic_demo_service import GEOMETRY


class MissionCorrectionTests(unittest.TestCase):
    def test_chat_status_write_is_not_a_room_edit_but_recipe_edit_still_rejects(self):
        project=self.root/'projects'/'correction'
        conversation=project/'project.conversation.json'
        conversation.write_text('{}',encoding='utf-8');self.guard()
        conversation.write_text('{"summary":"moving"}',encoding='utf-8');self.guard()
        path=project/'room_recipe.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'MISSION_ROOM_OR_LEDGER_CHANGED'):self.guard()

    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        recipe(self.root,'correction',1.);self.room=load_automatic_room(self.root,'correction')
        self.store=AutomaticPhotoStore(self.root,'correction');self.effective=self.store.current(self.room)
        self.automatic=AutomaticDemoService(self.root,'correction',geometry_loader=lambda:GEOMETRY)
        self.addCleanup(self.automatic.close);self.service=AutomaticMissionService(self.automatic)
        self.addCleanup(self.service.close);self.guard=self.service._revision_guard(self.room)
        self.after=copy.deepcopy(self.effective['objects'])
        next(o for o in self.after if o['kind']=='wall')['transform']['position_m'][1]+=.1

    def append(self):
        return self.store.append(self.room,None,self.after,action='apply',job_id='a'*32,map_revision='b'*64)

    def test_geometry_reader_reopens_only_current_owned_immutable_record(self):
        from twinpulse_app.room_recipe import prepare_project_burger_visual,import_project_room_recipe
        from twinpulse_app.automatic_mission_visual import checked_mission_geometry
        root=self.root/'geometry-state';recipe(root,'correction',1.,import_now=False)
        prepare_project_burger_visual(root,'correction',(0.,-.6,.002),0.);import_project_room_recipe(root,'correction')
        room=load_automatic_room(root,'correction');store=AutomaticPhotoStore(root,'correction')
        event=store.append(room,None,self.after,action='apply',job_id='a'*32,map_revision='b'*64)
        descriptor={'kind':'active_mission_geometry_v1','mission_id':'a'*32,'correction_revision':event['revision'],
                    'previous_objects_revision':self.effective['effective_revision'],'objects_revision':canonical_sha256(self.after)}
        scene=checked_mission_geometry(root,'correction',descriptor)[3]
        self.assertEqual(canonical_sha256(scene.to_dict()['objects']),descriptor['objects_revision'])
        for patch in ({'mission_id':'c'*32},{'correction_revision':'c'*64},{'previous_objects_revision':'c'*64},
                      {'objects_revision':'c'*64},{'pose_room':[0,0,0]}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                checked_mission_geometry(root,'correction',{**descriptor,**patch})
        store.append(room,event['revision'],self.effective['objects'],action='rollback',job_id='c'*32,map_revision='b'*64)
        with self.assertRaisesRegex(ValueError,'ACTIVE_GEOMETRY_CORRECTION_CHANGED'):
            checked_mission_geometry(root,'correction',descriptor)

    def test_owned_single_append_preserves_original_source_then_rejects_external_change(self):
        original=(self.root/'projects/correction/room_recipe.json').read_bytes()
        event=self.guard.append_owned(self.append);self.guard()
        self.assertEqual((self.root/'projects/correction/room_recipe.json').read_bytes(),original)
        self.assertEqual(self.store.current(self.room)['head'],event['revision'])
        (self.root/'projects/correction/external.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'MISSION_ROOM_OR_LEDGER_CHANGED'):self.guard()

    def test_external_edit_during_append_is_not_accepted_and_written_record_is_retained(self):
        def race():
            event=self.append();(self.root/'projects/correction/external.json').write_text('{}');return event
        with self.assertRaisesRegex(ValueError,'MISSION_SOURCE_CHANGED_DURING_CORRECTION'):
            self.guard.append_owned(race)
        self.assertEqual(len(self.store.current(self.room)['events']),1)
        with self.assertRaisesRegex(ValueError,'MISSION_ROOM_OR_LEDGER_CHANGED'):self.guard()

    def test_extra_unowned_ledger_record_is_not_accepted(self):
        def race():
            event=self.append()
            self.store.append(self.room,event['revision'],self.effective['objects'],action='rollback',job_id='c'*32,map_revision='b'*64)
            return event
        with self.assertRaisesRegex(ValueError,'MISSION_SOURCE_CHANGED_DURING_CORRECTION'):
            self.guard.append_owned(race)
        self.assertEqual(len(self.store.current(self.room)['events']),2)

    def test_nominal_change_rebinds_same_goal_and_rejects_unobserved_field_or_goal_collision(self):
        nominal=nominal_room(self.effective['objects'],.182,self.effective['effective_revision'])
        after=copy.deepcopy(nominal['objects']);wall=next(o for o in after if o['kind']=='wall')
        wall['transform']['position_m'][1]+=.1
        result={'policy':'correct_walls','status':'ALIGNMENT_CANDIDATE','geometry_status':'BOUNDED_WALL_PROPOSAL_VALIDATED',
                'source_map_revision':'b'*64,'scene_revision_before':canonical_sha256(nominal['objects']),
                'scene_revision_after':canonical_sha256(after),'corrected_objects':after}
        goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[.15,-.6],'room_revision':self.effective['effective_revision'],'duration_s':45.}
        merged,rebound=corrected_effective_objects(self.effective,nominal,result,goal)
        self.assertEqual(rebound['room_revision'],canonical_sha256(merged))
        self.assertEqual(rebound['xy'],goal['xy']);self.assertEqual(rebound['duration_s'],45.)
        broken=copy.deepcopy(result);broken['corrected_objects'][1]['shape']['dimensions_m'][0]+=.1
        broken['scene_revision_after']=canonical_sha256(broken['corrected_objects'])
        with self.assertRaisesRegex(ValueError,'PHOTO_CORRECTION_CHANGED_UNOBSERVED_FIELDS'):
            corrected_effective_objects(self.effective,nominal,broken,goal)
        interior=next(o for o in after if o['id']=='wall_2')['transform']['position_m'][:2]
        with self.assertRaisesRegex(ValueError,'MISSION_CORRECTED_GOAL_IN_WALL'):
            corrected_effective_objects(self.effective,nominal,result,{**goal,'xy':interior})
        with self.assertRaisesRegex(ValueError,'MISSION_CORRECTED_GOAL_OUTSIDE_FLOOR'):
            corrected_effective_objects(self.effective,nominal,result,{**goal,'xy':wall['transform']['position_m'][:2]})

    def test_unconfigured_remote_correction_is_rejected_before_any_adapter_or_child(self):
        called=[]
        def factory(*args):called.append(args)
        self.service.adapter_factory=factory
        goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[0.,0.],'room_revision':self.effective['effective_revision'],'duration_s':45.}
        from twinpulse_app.command_broker import BrokerError
        self.assertFalse(self.service.readiness(None)['photo_correction_available'])
        with self.assertRaisesRegex(BrokerError,'Remote correction acknowledgement'):
            self.service.start('owner',None,goal,'correct_walls')
        self.assertFalse(called);self.assertIsNone(self.service.job)
        with self.assertRaisesRegex(BrokerError,'Exact photo policy'):
            self.service.start('owner',None,goal,{'mode':'correct_walls'})


if __name__=='__main__':unittest.main()
