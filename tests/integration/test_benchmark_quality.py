# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic independent oracle regressions, not actual model-quality evidence."""
from copy import deepcopy
import unittest
from scripts.benchmark_protocol import canonical_sha
from scripts.benchmark_quality import evaluate,matching,semantic_entities
from twinpulse_provider.photo_layout import compile_layout
from twinpulse_core.photo_placement import placement_contract_from_trace
from test_photo_layout import observation,request
from test_photo_parametric import object_intent,intent


class BenchmarkQualityTests(unittest.TestCase):
    def setUp(self):
        value=intent(object_intent('generated_support','desk','rear_left',size=[1,.7,.9]),
            object_intent('generated_hazard','cable_bundle','front_right',size=[.3,.3,.05]),width=10,length=12)
        self.plan,trace=compile_layout(value,observation(),request('An estimated space'),None)
        self.placement=placement_contract_from_trace(trace)
        self.rubric=dict(schema_version='benchmark-rubric-1.0',entity_f1_min=.8,hazard_recall_min=.9,
            relation_accuracy_min=.85,match_distance_uv=.35,relation_epsilon_uv=.02,
            adjacent_distance_uv=.25,size_relative_tolerance=.1)
        self.packet=dict(case_id='fixture',prompt='A generic space',goal='Go to desk')
        predictions=semantic_entities(self.plan,self.placement)
        self.annotation=dict(schema_version='benchmark-annotation-1.0',case_id='fixture',
            input_sha256=canonical_sha(self.packet),rubric_sha256=canonical_sha(self.rubric),
            coordinate_frame='room_xy_normalized_front_negative_y',coverage_complete=True,reviewers=['reviewer-a'],
            room_size_m=None,room_size_authority='unknown',relations=[],
            entities=[dict(label_id='label-'+str(i),kind=p['kind'],visibility='observable',hazard=p['kind']=='cable_bundle',
                centre_uv=p['centre_uv'],size_m=None,size_authority='unknown',
                placement=dict(relation='floor',parent_label_id=None,part=None)) for i,p in enumerate(predictions)])
        self.visual=dict(schema_version='benchmark-visual-review-1.0',case_id='fixture',
            input_sha256=canonical_sha(self.packet),plan_sha256=canonical_sha(self.plan),
            rubric_sha256=canonical_sha(self.rubric),frame_sha256='a'*64,reviewers=['reviewer-a'],
            source='independent_human',blinded=True,recognizable=True)

    def score(self,visual=True):
        return evaluate(self.annotation,self.packet,self.rubric,self.plan,self.placement,
                        render_review=self.visual if visual else None)

    def test_unknown_room_scale_is_not_failure_ids_not_required_and_parts_not_entities(self):
        result=self.score();self.assertEqual(result['status'],'PASS');self.assertEqual(result['entity_f1'],1)
        self.assertEqual(result['predicted_entities'],2);self.assertEqual(result['human_reviewers'],1)
        self.assertIsNone(result['room_size_compliance']['value']);self.assertFalse(result['physical_authority'])

    def test_omitted_hazard_lowers_recall_and_no_easy_quality_pass(self):
        self.annotation['entities'].append(dict(label_id='missing-cable',kind='cable_bundle',visibility='observable',
            hazard=True,centre_uv=[-.4,-.4],size_m=None,size_authority='unknown',placement=None))
        result=self.score();self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['hazard_recall']['value'],.5)
        self.assertEqual(result['entity_recall']['denominator'],3)

    def test_no_render_or_critic_or_cube_review_is_not_visual_pass(self):
        self.assertEqual(self.score(False)['status'],'NOT_EVALUATED')
        self.visual['recognizable']=False;self.assertEqual(self.score()['status'],'FAIL')
        self.visual['source']='production_critic'
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_VISUAL'):self.score()

    def test_measured_or_explicit_size_is_checked_not_estimated_photo_guess(self):
        self.annotation['room_size_m']=[3,4];self.annotation['room_size_authority']='explicit'
        self.assertEqual(self.score()['room_size_compliance']['value'],0)
        self.assertEqual(self.score()['status'],'FAIL')
        self.annotation['room_size_authority']='unknown'
        with self.assertRaisesRegex(ValueError,'UNKNOWN_SIZE'):self.score()

    def test_wrong_support_and_spatial_relation_fail(self):
        self.annotation['entities'][0]['placement']['relation']='wall'
        self.assertEqual(self.score()['support_accuracy']['value'],.5)
        self.assertEqual(self.score()['status'],'FAIL')
        self.annotation['entities'][0]['placement']['relation']='floor'
        self.annotation['relations']=[dict(subject='label-0',object='label-1',relation='right',known=True)]
        self.assertEqual(self.score()['spatial_accuracy']['value'],0)

    def test_bindings_partial_and_unobservable_do_not_become_fake_truth(self):
        self.visual['plan_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'BINDING'):self.score()
        self.visual['plan_sha256']=canonical_sha(self.plan)
        self.annotation['coverage_complete']=False;self.assertEqual(self.score()['status'],'NOT_EVALUATED')
        self.annotation['entities'][0]['visibility']='occluded'
        result=self.score();self.assertEqual(result['observable_entities'],1)
        self.assertEqual(result['excluded_unobservable'],1)

    def test_assignment_maximizes_one_to_one_matches_not_greedy_or_id_names(self):
        labels=[dict(label_id='a',kind='chair',centre_uv=[0,0]),dict(label_id='b',kind='chair',centre_uv=[.2,0])]
        predicted=[dict(id='different-one',kind='chair',centre_uv=[.1,0]),
                   dict(id='different-two',kind='chair',centre_uv=[-.1,0])]
        result=matching(labels,predicted,.2)
        self.assertEqual(len(result),2);self.assertEqual(result['b']['id'],'different-one')
        labels.append(dict(label_id='c',kind='bed',centre_uv=None))
        self.assertEqual(len(matching(labels,predicted,.2)),2)

    def test_unobservable_prediction_not_false_positive_or_known_relation_failure(self):
        self.annotation['entities'][0]['visibility']='occluded'
        result=self.score();self.assertEqual(result['entity_precision']['value'],1)
        self.assertEqual(result['excluded_unobservable_predictions'],1)
        self.annotation['relations']=[dict(subject='label-0',object='label-1',relation='left',known=True)]
        result=self.score();self.assertEqual(result['status'],'NOT_EVALUATED')
        self.assertEqual(result['spatial_accuracy']['denominator'],0)

    def test_invalid_review_and_support_annotation_cannot_become_truth(self):
        self.visual['reviewers']='reviewer-a'
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_VISUAL'):self.score()
        self.visual['reviewers']=['reviewer-a','reviewer-a']
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_VISUAL'):self.score()
        self.visual['reviewers']=['reviewer-a']
        self.annotation['entities'][0]['placement']['parent_label_id']='label-1'
        with self.assertRaisesRegex(ValueError,'SUPPORT_ANNOTATION'):self.score()


if __name__=='__main__':unittest.main()
