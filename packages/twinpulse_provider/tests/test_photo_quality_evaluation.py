# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Evaluation oracle tests, not production fidelity/real-model acceptance."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts.verify_photo_quality_loop import facts,support_contract_probe,semantic_negative,validate_review,require_settled_dispatches
from twinpulse_core.furniture import expand_furniture
from twinpulse_provider import GenerationRequest
from twinpulse_provider.nebius_pipeline import ObservationArtifact,ChatCompletion
from twinpulse_provider.photo_layout import compile_layout,REVISION


def fixture():
    entries=[('bed','bed','middle_right'),('desk','desk','middle_left'),
        ('wardrobe','wardrobe','rear_right'),('top_storage','box','rear_left'),
        ('monitor','monitor','front_left'),('tabletop_items','tabletop_item','front_right')]
    observed=ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Synthetic oracle fixture.',
        entities=[dict(id=i+'_visual',kind='static_obstacle',description=i,confidence=.8) for i,_,_ in entries],
        relations=[],dimensions=[],ambiguities=['No measured scale']))
    intent=dict(layout_version=REVISION,summary='Synthetic estimates, not a room reconstruction.',
        room=dict(width_m=8,length_m=8,height_m=2.5),objects=[dict(id=i,kind=k,region=r,yaw_deg=0,
        observation_ids=[i+'_visual']) for i,k,r in entries])
    return compile_layout(intent,observed,GenerationRequest('fixture','Create a room 8 by 8 metres'),None)[0]


class PhotoQualityEvaluationTests(unittest.TestCase):
    def test_existence_and_same_height_do_not_mean_supported(self):
        report=facts(fixture())
        self.assertEqual(report['metric_scale_validation'],'UNVERIFIED_NO_MEASUREMENTS')
        self.assertTrue(report['large_room_scale_warning'])
        self.assertEqual(report['observed_position_support_status'],'FAIL')
        self.assertEqual([c['status'] for c in report['supported_relation_checks']],['FAIL']*3)

    def test_executor_accepts_supported_box_but_compiler_did_not_emit_it(self):
        payload=fixture();before=deepcopy(payload)
        result=support_contract_probe(payload)
        self.assertEqual(result['after_top_storage']['status'],'PASS')
        self.assertEqual(result['executor_status'],'ACCEPTED')
        self.assertIsNone(result['error'])
        self.assertEqual(result['before_top_storage']['status'],'FAIL')
        self.assertEqual(payload,before)
        self.assertTrue(result['original_unchanged'])

    def test_support_xy_and_z_and_yaw_checked(self):
        payload=fixture();objects={c['arguments'].get('id'):c['arguments'] for c in payload['calls']}
        parent=objects['desk'];parent['yaw_deg']=90
        support=next(p for p in expand_furniture(parent) if p.id=='desk_top')
        child=objects['monitor'];child['yaw_deg']=90
        child['dimensions_m']=[.4,.1,.3]
        child['position_m']=[*support.transform.position_m[:2],.74+.15]
        self.assertEqual(facts(payload)['supported_relation_checks'][1]['status'],'PASS')
        child['position_m'][2]+=.1
        self.assertEqual(facts(payload)['supported_relation_checks'][1]['status'],'FAIL')
        child['position_m'][2]-=.1;child['position_m'][0]+=1
        self.assertEqual(facts(payload)['supported_relation_checks'][1]['status'],'FAIL')

    def test_photo_side_mismatch_not_hidden_by_contract_validity(self):
        payload=fixture()
        bed=next(c['arguments'] for c in payload['calls'] if c['arguments'].get('id')=='bed')
        bed['center_m'][0]=-1
        report=facts(payload)
        self.assertIn('bed',[i['id'] for i in report['issues'] if i['code']=='PHOTO_SIDE_MISMATCH'])
        job=dict(status='CONTRACT_VALIDATED',quality=report,diagnostics=dict(repair_count=0))
        self.assertTrue(semantic_negative(job)['reproduced'])
        job['status']='FAIL'
        self.assertIsNone(semantic_negative(job)['production_detected_quality_failure'])

    def test_correct_left_right_does_not_hide_wrong_front_rear(self):
        payload=fixture()
        desk=next(c['arguments'] for c in payload['calls'] if c['arguments'].get('id')=='desk')
        desk['center_m']=[-2,-2]
        report=facts(payload)
        self.assertNotIn('desk',[i['id'] for i in report['issues'] if i['code']=='PHOTO_SIDE_MISMATCH'])
        self.assertIn('desk',[i['id'] for i in report['issues'] if i['code']=='PHOTO_DEPTH_MISMATCH'])

    def test_model_acceptance_is_not_photo_geometry_acceptance(self):
        value=dict(verdict='accept_estimated',scale='unmeasured',issues=[],summary='Estimated.')
        model_result=ChatCompletion('r','review',json.dumps(value),'stop',{})
        self.assertEqual(validate_review(model_result,'review')['verdict'],'accept_estimated')
        self.assertEqual(facts(fixture())['observed_position_support_status'],'FAIL')

    def test_critic_shape_identity_finish_and_metric_claims(self):
        value=dict(verdict='reject',scale='unmeasured',issues=[],summary='No measurements.')
        def result(value=value,model='review',finish='stop'):
            return ChatCompletion('r',model,json.dumps(value),finish,{})
        self.assertEqual(validate_review(result(),'review'),value)
        for bad in (dict(value,scale='verified'),dict(value,issues=[dict(object_id='bed',axis='code',detail='x')]),
                    dict(value,extra='execute'),dict(value,summary='x'*241)):
            with self.assertRaises(ValueError):validate_review(result(bad),'review')
        for model,finish in [('wrong','stop'),('review','length')]:
            with self.assertRaises(ValueError):validate_review(result(model=model,finish=finish),'review')

    def test_unknown_pending_or_missing_dispatch_blocks_next_paid_call(self):
        class Lock:
            def exists(self):return False
        row=dict(attempt_id='a',finished_at='now',status='received')
        ledger=SimpleNamespace(lock_path=Lock(),state=dict(requests=[row]))
        require_settled_dispatches(ledger,['a'])
        for status,finished in [('outcome_unknown','now'),('received',None)]:
            row.update(status=status,finished_at=finished)
            with self.assertRaises(ValueError):require_settled_dispatches(ledger,['a'])
        with self.assertRaises(ValueError):require_settled_dispatches(ledger,['missing'])


if __name__=='__main__':unittest.main()
