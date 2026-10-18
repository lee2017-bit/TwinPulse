# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary offline pose-repair boundaries; not model/Isaac acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch as mock_patch

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app','twinpulse_robot'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/tests'))
from test_budgeted_generation import FixtureTransport,config,OBSERVER_MODEL
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_app.scene_edit_proposals import feedback_edit_context
from tests.integration.test_dependency_scene_changes import partial_source,edit,patch
from twinpulse_provider import CancellationToken,InvalidProviderResponseError
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy,GenerationBudgetError
from twinpulse_provider.scene_edit_provider import feedback_generation_request,SceneEditProposalService
from twinpulse_provider.errors import GenerationCancelledError,ProviderTimeoutError
from twinpulse_provider.nebius_pipeline import ChatCompletion


class Scope:
    def __init__(self):self.binds=0
    def bind(self,*args):self.binds+=1;return None


class Transport(FixtureTransport):
    def __init__(self,values):super().__init__(values);self.validations={}
    def record_validation(self,stage,identity,record):
        key=(identity,stage)
        if key in self.validations:raise FileExistsError('immutable evidence overwritten')
        self.validations[key]=deepcopy(record)


class FeedbackPoseRepairTests(unittest.TestCase):
    def setUp(self):
        self.source=partial_source();self.history=SceneChangeHistory.empty('room',self.source)
        self.context=feedback_edit_context('room',self.source,self.history,'Move the support to the right wall; preserve its size and pending items.')
        self.old=deepcopy(next(c for c in self.context['current_plan']['calls'] if c['arguments']['id']=='support'))

    def candidate(self,x,explanation='Move support only'):
        call=deepcopy(self.old);call['arguments']['center_m']=[x,0]
        return dict(schema_version='scene-edit-proposal-1.1',context_sha256=self.context['context_sha256'],
            mode='dependency',explanation=explanation,patch=patch(edit('change','support',tool_call=call)))

    def diagnosis(self,excess=.06):
        return dict(code='FURNITURE_FLOOR_CLEARANCE',group='support_body',
            footprint_bounds_xy=[.86,1.4+excess,-.3,1.5],usable_floor_bounds_xy=[-1.4,1.4,-2.15,2.15])

    def run_values(self,values,validator,*,policy=None,token=None,transport=None,service_timeout=None,deadline=None):
        scope=Scope();transport=transport or Transport(values);token=token or CancellationToken()
        provider=BudgetedPipeline(transport,policy=policy or GenerationPolicy(),observer_model_id=OBSERVER_MODEL,
            planner_model_id='nvidia/nemotron-3-super-120b-a12b',site_plan_version='2.2',
            stage_output_token_caps={'observer':40000,'planner':40000})
        request=replace(feedback_generation_request(self.context,'pose-test'),inference_scope=scope,
            feedback_candidate_validator=validator,feedback_deadline=deadline)
        self.scope,self.transport,self.provider,self.token=scope,transport,provider,token
        if service_timeout is not None:
            return asyncio.run(SceneEditProposalService(provider,config(timeout_s=service_timeout)).propose(
                self.context,'pose-test',inference_scope=scope,token=token,feedback_candidate_validator=validator))
        return asyncio.run(provider.generate_feedback(request,token,config(timeout_s=300)))

    def test_first_valid_one_call_and_clearance_retry_same_budget(self):
        result=self.run_values([self.candidate(.2)],lambda _:None)
        self.assertEqual(len(self.transport.bodies),1);self.assertEqual(self.scope.binds,1)
        self.assertEqual(result.provenance['budget']['repairs'],0)
        bad=self.candidate(1.16);good=self.candidate(1.08)
        def validator(value):return self.diagnosis() if value and value['patch']['edits'][0]['tool_call']['arguments']['center_m'][0]>1.1 else None
        result=self.run_values([bad,good],validator)
        budget=result.provenance['budget']
        self.assertEqual((self.scope.binds,budget['requests'],budget['repairs']),(1,2,1))
        self.assertEqual([r['role'] for r in budget['attempts']],['initial','repair'])
        self.assertEqual(result.payload,good)
        self.assertIn('candidate_geometry_error',self.transport.bodies[1]['messages'][-1]['content'])
        phases=[v for v in self.transport.validations.values()]
        self.assertEqual(sum(v.get('phase')=='wire' for v in phases),2)
        self.assertEqual([v['validation'] for v in phases if v.get('phase')=='candidate_geometry'],['failed','passed'])

    def test_scope_size_support_action_and_target_changes_cannot_fix_bounds(self):
        bad=self.candidate(1.16)
        mutations=[]
        size=self.candidate(1.08);size['patch']['edits'][0]['tool_call']['arguments']['dimensions_m'][0]+=.1;mutations.append(size)
        defer=self.candidate(1.08);defer['patch']['edits']=[edit('defer','support')];mutations.append(defer)
        other=self.candidate(1.08);other['patch']['edits'].append(edit('defer','item_0'));mutations.append(other)
        for candidate in mutations:
            with self.subTest(candidate=candidate),self.assertRaises(InvalidProviderResponseError):
                self.run_values([bad,candidate],lambda value:self.diagnosis() if value else None)
            self.assertEqual(len(self.transport.bodies),2);self.assertEqual(self.scope.binds,1)
        self.assertEqual(self.history.operations,())

    def test_initial_resize_failure_does_not_enter_pose_lane(self):
        resized=self.candidate(1.16);resized['patch']['edits'][0]['tool_call']['arguments']['dimensions_m'][0]+=.1
        with self.assertRaisesRegex(InvalidProviderResponseError,'not pose-only'):
            self.run_values([resized],lambda value:self.diagnosis() if value else None)
        self.assertEqual(len(self.transport.bodies),1)

    def test_repair_cannot_abandon_first_proposed_orientation(self):
        initial=self.candidate(1.16);initial['patch']['edits'][0]['tool_call']['arguments']['yaw_deg']=90
        drift=self.candidate(.2)
        with self.assertRaisesRegex(InvalidProviderResponseError,'first proposed orientation'):
            self.run_values([initial,drift],lambda value:self.diagnosis() if value else None)
        corrected=deepcopy(initial);corrected['patch']['edits'][0]['tool_call']['arguments']['center_m']=[1.08,0]
        result=self.run_values([initial,corrected],lambda value:self.diagnosis() if value and
            value['patch']['edits'][0]['tool_call']['arguments']['center_m'][0]>1.1 else None)
        self.assertEqual(result.payload['patch']['edits'][0]['tool_call']['arguments']['yaw_deg'],90)

    def test_floor_numeric_equivalence_keeps_physical_clearance_and_overlap(self):
        from twinpulse_core.furniture import validate_furniture_layout,FurnitureFloorClearanceError,FurnitureFootprintOverlapError
        from twinpulse_core.models import SceneObject,ShapeSpec,Transform
        def floor():return SceneObject('floor','floor',Transform((0,0,0),(0,0,0)),ShapeSpec('box',(3,4.5,.1)))
        def box(identity,x,y=0,size=(.6,1.8,.7)):
            return SceneObject(identity,'equipment',Transform((x,y,.35),(0,0,0)),ShapeSpec('box',size))
        validate_furniture_layout((floor(),box('desk',1.1)),(('desk',),))
        for x in (1.1+1e-11,1.16):
            with self.assertRaises(FurnitureFloorClearanceError):
                validate_furniture_layout((floor(),box('desk',x)),(('desk',),))
        with self.assertRaises(FurnitureFootprintOverlapError):
            validate_furniture_layout((floor(),box('desk',1.1,.6),box('shelf',1.,.6,(.6,.4,.8))),
                (('desk',),('shelf',)))

    def test_typed_overlap_uses_same_pose_scope_and_shared_budget(self):
        diagnosis=dict(code='FURNITURE_FOOTPRINT_OVERLAP',groups=['support_body','other_body'],
            footprint_bounds_xy=[[.7,1.3,-1.5,.3],[.7,1.3,-1.75,-1.25]])
        result=self.run_values([self.candidate(1.16),self.candidate(.2)],lambda value:diagnosis
            if value and value['patch']['edits'][0]['tool_call']['arguments']['center_m'][0]>1 else None)
        self.assertEqual(result.provenance['budget']['repairs'],1)
        self.assertEqual((self.scope.binds,len(self.transport.bodies)),(1,2))

    def test_contained_overlap_metric_tracks_actual_separation_distance(self):
        from twinpulse_provider.feedback_pose_repair import clearance_violation
        values=[]
        for x in (0,.2,.4):
            values.append(clearance_violation(dict(code='FURNITURE_FOOTPRINT_OVERLAP',groups=['desk','drawer'],
                footprint_bounds_xy=[[-1+x,1+x,-1,1],[-.1,.1,-.1,.1]])))
        self.assertEqual([round(v,3) for v in values],[1.1,.9,.7])

    def test_floor_then_new_overlap_blocker_is_not_false_progress_or_stall(self):
        diagnoses=[self.diagnosis(),dict(code='FURNITURE_FOOTPRINT_OVERLAP',groups=['support_body','other_body'],
            footprint_bounds_xy=[[-1,1,-1,1],[-.1,.1,-.1,.1]]),None]
        def validator(value):return diagnoses.pop(0) if value else None
        result=self.run_values([self.candidate(x) for x in (1.16,1.08,.2)],validator)
        self.assertEqual(result.provenance['budget']['repairs'],2)
        self.assertEqual(result.provenance['budget']['stalled_repairs'],0)

    def test_same_or_cyclic_geometry_stalls_even_when_explanations_change(self):
        for values in ([self.candidate(1.16,'first'),self.candidate(1.16,'new prose')],
                       [self.candidate(1.16),self.candidate(1.17),self.candidate(1.16,'cycle')]):
            with self.subTest(count=len(values)),self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):
                self.run_values(values,lambda value:self.diagnosis(value['patch']['edits'][0]['tool_call']['arguments']['center_m'][0]-1.1) if value else None)
            self.assertEqual(len(self.transport.bodies),len(values))

    def test_repair_limit_unchanged(self):
        values=[self.candidate(x) for x in (1.16,1.15,1.14,1.13,1.12)]
        with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_LIMIT_REACHED'):
            self.run_values(values,lambda value:self.diagnosis(value['patch']['edits'][0]['tool_call']['arguments']['center_m'][0]-1.1) if value else None)
        self.assertEqual(len(self.transport.bodies),4);self.assertEqual(self.scope.binds,1)

    def test_cancel_stale_storage_non_geometry_never_retry(self):
        for error in (GenerationCancelledError('cancel'),ValueError('source replay stale'),OSError('disk')):
            def validator(value):
                if value:raise error
            with self.subTest(error=type(error).__name__),self.assertRaises(type(error)):
                self.run_values([self.candidate(1.16)],validator)
            self.assertEqual(len(self.transport.bodies),1)
        token=CancellationToken();token.cancel()
        with self.assertRaises(GenerationCancelledError):self.run_values([],lambda _:None,token=token)
        self.assertEqual(self.transport.bodies,[])

    def test_unknown_and_truncation_never_retry(self):
        for value in (ProviderTimeoutError('unknown'),ChatCompletion('a','nvidia/nemotron-3-super-120b-a12b','{}','length',{})):
            with self.subTest(value=type(value).__name__),self.assertRaises((ProviderTimeoutError,InvalidProviderResponseError)):
                self.run_values([value],lambda _:None)
            self.assertEqual(len(self.transport.bodies),1)

    def test_legacy_no_host_validator_stays_single_call(self):
        result=self.run_values([self.candidate(1.16)],None)
        self.assertEqual(len(self.transport.bodies),1);self.assertEqual(result.provenance['budget']['repairs'],0)

    def test_synchronous_candidate_compile_cannot_escape_absolute_deadline(self):
        clock=[0.]
        def validator(value):
            if value:clock[0]=11.
        with mock_patch('twinpulse_provider.budgeted_pipeline.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(GenerationBudgetError,'FEEDBACK_LOCAL_DEADLINE'):
                self.run_values([self.candidate(.2)],validator,deadline=10.)
        self.assertEqual(len(self.transport.bodies),1)
        self.assertEqual(self.provider._budget.rows[0]['status'],'received')
        self.assertNotEqual(self.provider._budget.terminal,'REMOTE_OUTCOME_UNKNOWN')

    def test_second_attempt_failure_evidence_belongs_only_to_second_receipt(self):
        for cancelled in (False,True):
            class ReceiptTransport(Transport):
                async def complete(inner,body,token,settings):
                    result=await super().complete(body,token,settings)
                    if len(inner.bodies)==2 and cancelled:token.cancel()
                    return result
            second=self.candidate(1.08) if cancelled else ChatCompletion('b','nvidia/nemotron-3-super-120b-a12b','{}','length',{})
            transport=ReceiptTransport([self.candidate(1.16),second])
            with self.subTest(cancelled=cancelled),self.assertRaises((GenerationCancelledError,InvalidProviderResponseError)):
                self.run_values([],lambda value:self.diagnosis() if value else None,transport=transport)
            rows=self.provider._budget.rows;first_id,second_id=[r['attempt_id'] for r in rows]
            self.assertEqual({stage for identity,stage in transport.validations if identity==first_id},
                {'scene_feedback','scene_feedback_geometry'})
            self.assertIn((second_id,'scene_feedback'),transport.validations)
            self.assertEqual(transport.validations[second_id,'scene_feedback']['role'],'repair')

    def test_next_preflight_cancel_does_not_relabel_previous_attempt(self):
        calls=[0]
        def validator(value):
            if value is None:
                calls[0]+=1
                if calls[0]==2:raise GenerationCancelledError('cancel before repair dispatch')
            else:return self.diagnosis()
        with self.assertRaises(GenerationCancelledError):self.run_values([self.candidate(1.16)],validator)
        self.assertEqual(len(self.transport.bodies),1)
        attempt=self.provider._diagnostic['attempts'][0]
        self.assertNotIn('cancelled',attempt);self.assertNotIn('ignored_by_host',attempt)
        self.assertEqual({stage for _,stage in self.transport.validations},{'scene_feedback','scene_feedback_geometry'})

    def test_candidate_exception_is_typed_but_source_replay_is_not_reclassified(self):
        from twinpulse_app.dependency_patch import CandidatePoseClearanceError,apply_patch_state
        from twinpulse_core.furniture import FurnitureFloorClearanceError
        bad=self.candidate(5)
        with self.assertRaises(CandidatePoseClearanceError) as caught:
            self.history.preview(self.source,operation_id='bad-pose',mode='dependency',tool_call=bad['patch'])
        self.assertEqual(caught.exception.diagnosis['code'],'FURNITURE_FLOOR_CLEARANCE')
        # The replay/default caller must NOT acquire candidate repair authority.
        with self.assertRaises(FurnitureFloorClearanceError):
            apply_patch_state(self.source,self.history.effective(self.source),bad['patch'],self.history.current_scene_revision)
        self.assertEqual(self.history.operations,())


if __name__=='__main__':unittest.main()
