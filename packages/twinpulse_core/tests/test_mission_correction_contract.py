# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import unittest
from twinpulse_core.adaptive_mission_contract import adaptive_scope,adaptive_bootstrap,nominal_room
from twinpulse_core.mission_contract import document_hash
from twinpulse_core.mission_correction_contract import correction_proposal,checked_proposal,correction_reply,checked_reply
from twinpulse_core.automatic_photo_alignment import align_photo_map
from packages.twinpulse_core.tests.test_automatic_photo_alignment import room,mapping


class CorrectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        outline,objects=room();objects[1]['transform']['position_m'][1]-=.12
        cls.nominal=nominal_room(objects,.182,'a'*64)
        saved=mapping(outline)
        for view in saved['keyframes']:view['sequence']+=1
        saved['revision']=document_hash(saved)
        cls.fit=align_photo_map(saved,cls.nominal['objects'],policy='correct_walls')

    def scope(self):
        return {'schema':'observed-mission-scope-3.0','project_id':'room','goal':{'mode':'SURVEY_THEN_NAVIGATE',
            'xy':[.15,-.6],'duration_s':45.,'room_revision':'a'*64},'reference':None,'alignment':None,
            'nominal':copy.deepcopy(self.nominal),'photo_policy':'idle-bounded-wall-ack-1.0'}

    def proposal(self):return correction_proposal(self.scope(),'b'*32,'c'*64,'d'*24,self.fit,10.)

    def test_v5_survey_ack_cannot_become_destination_authority(self):
        scope=self.scope();scope['schema']='observed-mission-scope-5.0'
        scope['goal'].update(mode='SURVEY_ONLY',xy=[0.,0.])
        proposal=correction_proposal(scope,'b'*32,'c'*64,'d'*24,self.fit,10.)
        checked_proposal(proposal,scope,'b'*32,'c'*64)
        binding={'schema':'mission-photo-binding-1.0','goal':{**scope['goal'],'room_revision':'e'*64},'applied_revision':'f'*64}
        reply=correction_reply(proposal,scope,binding)
        self.assertEqual(checked_reply(reply,proposal,scope,11.)['binding'],binding)
        for key,bad in (('mode','SURVEY_THEN_NAVIGATE'),('xy',[.1,0.]),('duration_s',44.)):
            with self.assertRaises(ValueError):correction_reply(proposal,scope,{**binding,'goal':{**binding['goal'],key:bad}})
        with self.assertRaises(ValueError):
            correction_proposal({**scope,'schema':'observed-mission-scope-4.0'},'b'*32,'c'*64,'d'*24,self.fit,10.)

    def test_explicit_v3_policy_and_old_scope_bootstrap_bytes_unchanged(self):
        v3=self.scope();v2={k:v for k,v in v3.items() if k!='photo_policy'};v2['schema']='observed-mission-scope-2.0'
        context={'state':'MISSION_CONTEXT','boot_id':'test','release_id':'c'*64,'calibration_sha256':'d'*64,'issued_s':10.,'nonce':'e'*24}
        before=document_hash(adaptive_bootstrap(context,'f'*32,v2))
        adaptive_scope(v3);self.proposal()
        self.assertEqual(before,document_hash(adaptive_bootstrap(context,'f'*32,v2)))
        for wrong in ({**v2,'photo_policy':v3['photo_policy']},{**v3,'photo_policy':'automatic-anything'},
                      {**v3,'goal':{**v3['goal'],'duration_s':46}}):
            with self.assertRaises(ValueError):adaptive_scope(wrong)

    def test_actual_fit_bound_proposal_ack_and_deadline_no_scope_extension(self):
        original=self.scope();proposal=self.proposal();checked_proposal(proposal,original,'b'*32,'c'*64)
        binding={'schema':'mission-photo-binding-1.0','goal':{**original['goal'],'room_revision':'e'*64},'applied_revision':'f'*64}
        reply=correction_reply(proposal,original,binding)
        self.assertEqual(checked_reply(reply,proposal,original,11.9),reply)
        self.assertEqual(original,self.scope())
        for key,bad in (('nonce','0'*24),('mission_id','0'*32),('scope_sha256','0'*64),('proposal_revision','0'*64),('revision','0'*64)):
            with self.subTest(key=key),self.assertRaises(ValueError):checked_reply({**reply,key:bad},proposal,original,11.)
        for at in (9.,12.,float('nan')):
            with self.assertRaises(ValueError):checked_reply(reply,proposal,original,at)
        for key,bad in (('xy',[.2,-.6]),('duration_s',44.),('mode','NAVIGATE_TWIN_GOAL'),('room_revision','a'*64)):
            with self.assertRaises(ValueError):correction_reply(proposal,original,{**binding,'goal':{**binding['goal'],key:bad}})

    def test_rejection_exact_reason_and_untrusted_fit_cannot_be_promoted(self):
        proposal=self.proposal();reply=correction_reply(proposal,self.scope(),reason='PHOTO_LEDGER_HEAD_CHANGED')
        self.assertEqual(checked_reply(reply,proposal,self.scope(),11.)['reason'],'PHOTO_LEDGER_HEAD_CHANGED')
        for changes in ({'motion_authorized':True},{'alignment_verified':True},{'validation_sequences':[1]},
                        {'scene_revision_after':'0'*64},{'additional_evidence':'secret=DO_NOT_STORE'},{'approved':True}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                correction_proposal(self.scope(),'b'*32,'c'*64,'d'*24,{**self.fit,**changes},10.)


if __name__=='__main__':unittest.main()
