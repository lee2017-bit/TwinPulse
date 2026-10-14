# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline actual product paths. Scripted replies are not real-model evidence."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
from dataclasses import replace

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
import test_budgeted_generation as generation_fixtures
from test_budgeted_generation import (FixtureTransport,bed,text_request,
    empty_observation,config)
from twinpulse_provider import GenerationService,InvalidProviderResponseError
from twinpulse_provider.semantic_scene import (checked_structure,scene_draft,checked_batch,
    patch_candidate,revision,PATCH_REVISION,compile_scene,compiler_diagnosis,geometry_repair_context)
from twinpulse_provider.photo_layout import _checked_model_relations
from twinpulse_core.geometry_diagnostics import GeometryValidationError
from twinpulse_core.geometry_checks import GeometryChecks,PHASES
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.generation_policy import ProgressTracker,diagnostic_blockers
from twinpulse_provider.generation_policy import ExecutionBudget,GenerationPolicy
from twinpulse_provider.generation_policy import GenerationBudgetError
from twinpulse_app.product_workflow_service import _public_generation_diagnostics


def blind(center=2.2):
    return dict(region='rear_centre',yaw_deg=0,model_id='home.window_blind',
        dimensions_m=[1.2,.08,.5],variant='standard',finish='catalog_default',
        placement=dict(relation='wall',parent_id='rear_wall',part=None,anchor='centre',elevation_m=center))


def fixture(center=2.2):
    structure=dict(summary='Synthetic unmeasured room',room=dict(width_m=6,length_m=6,height_m=2.4),
        inventory=[dict(id=i,kind=k,evidence_ref='hypothesis') for i,k in (('shade','window_blind'),('bed','bed'))])
    parameters={'shade':blind(center),'bed':bed()}
    draft=checked_batch(parameters,scene_draft(checked_structure(structure,text_request(),empty_observation())),list(parameters))
    return structure,parameters,draft


def patch(draft,identity,value):
    return dict(patch_version=PATCH_REVISION,base_revision=revision(draft),
        operations=[dict(op='update',id=identity,value=value)])


def diagnosis(draft):
    try:compile_scene(draft,empty_observation(),text_request())
    except ValueError as error:return compiler_diagnosis(error,draft,text_request())
    raise AssertionError('fixture must fail')


class RecordedFixture(FixtureTransport):
    def __init__(self,responses):
        super().__init__(responses);self.records=[]
    def record_validation(self,name,identity,record):
        self.records.append((name,identity,deepcopy(record)))


class GeometryRepairTests(unittest.TestCase):
    def test_wall_attachment_tangent_fits_independent_room_widths_and_regions(self):
        for width,length,span,parent,region in (
                (4.2,4.8,1.5,'rear_wall','rear_left'),
                (3.0,5.0,2.5,'rear_wall','rear_right'),
                (5.0,3.0,2.5,'left_wall','front_left'),
                (5.0,3.0,2.5,'right_wall','rear_right')):
            structure,parameters,draft=fixture(center=1.2)
            draft['room'].update(width_m=width,length_m=length)
            draft['objects'].pop('bed');draft['inventory']=[r for r in draft['inventory'] if r['id']=='shade']
            shade=draft['objects']['shade'];shade.update(region=region,dimensions_m=[span,.1,.5])
            shade['placement']['parent_id']=parent
            original=deepcopy(draft)
            payload,provenance=compile_scene(draft,empty_observation(),text_request())
            self.assertTrue(provenance['checks_complete'])
            args=next(r['arguments'] for r in payload['calls'] if r['tool']=='place_room_item')
            axis=0 if parent=='rear_wall' else 1
            limit=width if axis==0 else length
            self.assertLessEqual(abs(args['position_m'][axis])+span/2,limit/2)
            self.assertEqual(draft,original)

    def test_wall_span_too_large_has_typed_target_and_dynamic_limit(self):
        _,_,draft=fixture(center=1.2)
        draft['room']['width_m']=2
        draft['objects']['shade']['dimensions_m'][0]=2.5
        with self.assertRaises(GeometryValidationError) as caught:
            compile_scene(draft,empty_observation(),text_request())
        row=next(i for i in caught.exception.contract_report['issues'] if i['code']=='PHOTO_WALL_SPAN_EXCEEDED')
        self.assertEqual(row['target_ids'],['shade']);self.assertAlmostEqual(row['expected']['max_m'],1.996)

    def run_pipeline(self,responses):
        transport=RecordedFixture(responses)
        provider=generation_fixtures.PipelineTests.provider(self,transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(text_request()))
        return result,provider,transport

    def test_dynamic_bounds_independent_ids_and_multiple_errors(self):
        for identity,height,size,center in [('other',3.1,.8,2.9),('different',2.7,.4,.1)]:
            row=dict(id=identity,kind='window_blind',**blind(center));row['dimensions_m'][2]=size
            with self.assertRaises(GeometryValidationError) as caught:
                _checked_model_relations([row],height,{})
            issue=caught.exception.contract_report['issues'][0]
            self.assertEqual(issue['target_ids'],[identity])
            self.assertEqual(issue['expected']['min_m'],size/2)
            self.assertEqual(issue['expected']['max_m'],height-size/2)
        _,_,draft=fixture()
        row=dict(id='broken_floor',kind='bed',**bed());row['placement']['parent_id']='missing'
        rows=[dict(id='shade',kind='window_blind',**blind()),row]
        with self.assertRaises(GeometryValidationError) as caught:_checked_model_relations(rows,2.4,{})
        self.assertEqual({i['code'] for i in caught.exception.contract_report['issues']},
            {'PHOTO_RELATION_WALL_HEIGHT_INVALID','PHOTO_RELATION_FLOOR_INVALID'})
        self.assertTrue(caught.exception.contract_report['blocked_checks'])

    def test_exact_diagnosis_and_scope_reach_repair_and_full_validation(self):
        structure,parameters,draft=fixture();result,provider,transport=self.run_pipeline([
            structure,parameters,patch(draft,'shade',blind(2.1))])
        request=json.loads(transport.bodies[2]['messages'][-1]['content'])
        issue=request['validation']['issues'][0]
        self.assertEqual(issue['target_ids'],['shade'])
        self.assertEqual(issue['path'],'$.objects.shade.placement.elevation_m')
        self.assertIn('shade',[i['id'] for i in request['repair_scope']['targets']])
        self.assertEqual(provider.diagnostic_for('generation-test')['attempts'][-1]['candidate_validation'],'passed')
        self.assertEqual(result.provider_provenance['patches'][0]['changed_ids'],['shade'])
        self.assertFalse(result.provider_provenance['physical_authority'])
        self.assertTrue(any(name=='semantic_compile' and row['validation']=='passed' for name,_,row in transport.records))

    def test_no_change_feedback_keeps_geometry_candidate_and_recovers(self):
        structure,parameters,draft=fixture()
        _,provider,transport=self.run_pipeline([structure,parameters,patch(draft,'bed',bed()),patch(draft,'shade',blind(2.1))])
        last=json.loads(transport.bodies[-1]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(last['error_code'],'SEMANTIC_PATCH_NO_CHANGE')
        self.assertEqual(last['previous_candidate'],draft)
        self.assertEqual(last['validation']['issues'][0]['target_ids'],['shade'])
        self.assertEqual(provider.diagnostic_for('generation-test')['budget']['repairs'],2)

    def test_same_object_partial_numeric_improvement_then_final_success(self):
        structure,parameters,draft=fixture();middle=patch_candidate(draft,patch(draft,'shade',blind(2.18)),empty_observation(),text_request())
        _,provider,transport=self.run_pipeline([structure,parameters,patch(draft,'shade',blind(2.18)),patch(middle,'shade',blind(2.1))])
        decisions=[r for name,_,r in transport.records if name=='geometry_repair_decision']
        self.assertTrue(decisions[-1]['progressed'])
        self.assertEqual(provider.diagnostic_for('generation-test')['budget']['repairs'],2)

    def test_bounded_exploration_keeps_best_without_mutating_original(self):
        structure,parameters,draft=fixture();original=deepcopy(draft)
        worse=patch_candidate(draft,patch(draft,'shade',blind(2.3)),empty_observation(),text_request())
        _,_,transport=self.run_pipeline([structure,parameters,patch(draft,'shade',blind(2.3)),patch(worse,'shade',blind(2.1))])
        body=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(body['candidate'],worse)
        self.assertEqual(body['previous_patch_decision']['decision'],'exploring')
        self.assertEqual(body['previous_patch_decision']['rollback_to'],revision(original))
        self.assertFalse(body['previous_patch_decision']['progressed'])
        self.assertEqual(draft,original)

    def test_no_change_and_order_only_have_precise_error(self):
        _,_,draft=fixture()
        with self.assertRaisesRegex(InvalidProviderResponseError,'SEMANTIC_PATCH_NO_CHANGE'):
            patch_candidate(draft,patch(draft,'bed',bed()),empty_observation(),text_request())
        shuffled=deepcopy(draft);shuffled['inventory'].reverse()
        self.assertEqual(revision(draft),revision(shuffled))

    def test_scope_includes_healthy_parent_children_and_siblings(self):
        _,_,draft=fixture();draft['objects']['child']=dict(placement={'parent_id':'bed'})
        draft['inventory'].append(dict(id='child',source={'basis':'inferred'}))
        report={'issues':[{'target_ids':['child'],'related_ids':[]}]}
        scope=geometry_repair_context(draft,report)
        self.assertEqual({i['id'] for i in scope['targets']},{'bed','child'})
        self.assertIn('shade',scope['room_change_requires_recheck'])

    def test_unknown_compiler_error_is_not_a_blind_retry(self):
        _,_,draft=fixture();report=compiler_diagnosis(ValueError('unregistered internal failure'),draft,text_request())
        self.assertEqual(report['issues'][0]['code'],'UNMAPPED_COMPILER_ERROR')
        self.assertFalse(report['issues'][0]['repairable'])
        self.assertIn('unregistered internal failure',report['original_error'])

    def test_public_diagnostic_numeric_bounds_and_no_arbitrary_details(self):
        _,_,draft=fixture();report=diagnosis(draft)
        report['issues'][0]['secret']='do not expose'
        public=_public_generation_diagnostics(dict(scene_contract=report,
            patch_shape='passed',candidate_validation='failed'))
        issue=public['scene_contract']['issues'][0]
        self.assertEqual(issue['target_ids'],['shade'])
        self.assertEqual(issue['actual_m'],2.2)
        self.assertEqual(issue['expected_bounds_m']['max_m'],2.15)
        self.assertNotIn('secret',issue)
        self.assertEqual(public['candidate_validation'],'failed')

    def test_progress_target_exchange_and_oscillation_are_not_success(self):
        _,_,first=fixture();second=deepcopy(first);second['objects']['shade']=blind(2.18)
        third=deepcopy(first);third['objects']['shade']=blind(2.3)
        tracker=ProgressTracker()
        for draft,expected in [(first,False),(second,True),(third,False),(first,False)]:
            report=diagnosis(draft);problems=diagnostic_blockers(report,'fallback')
            self.assertEqual(tracker.observe(draft,problems,report),expected)

    def test_blocked_check_removed_without_execution_is_not_progress(self):
        tracker=ProgressTracker()
        initial={'issues':[{'code':'PHOTO_RELATION_WALL_HEIGHT_INVALID','path':'$.objects.a.placement',
            'target_ids':['a']}],'blocked_checks':[{'check':'packing','blocked_by':'first'}]}
        later={'issues':[{'code':'PHOTO_LAYOUT_REGION_FULL','path':'$.objects.b.region',
            'target_ids':['b']}],'blocked_checks':[]}
        self.assertFalse(tracker.observe({'geometry':1},diagnostic_blockers(initial,'error'),initial))
        self.assertFalse(tracker.observe({'geometry':2},diagnostic_blockers(later,'error'),later))
        self.assertTrue(tracker.regressed)
        broken={'issues':[{'code':'PHOTO_RELATION_FLOOR_INVALID','path':'$.objects.c.placement',
            'target_ids':['c']}],'blocked_checks':[]}
        self.assertFalse(tracker.observe({'geometry':3},diagnostic_blockers(broken,'error'),broken))
        self.assertTrue(tracker.regressed)

    def test_advance_and_existing_regression_does_not_promote_best(self):
        def ledger(rev,states,issues):
            checks=GeometryChecks(rev,'fixture','library',[])
            for row in checks.rows:
                row['status']=states.get(row['check_id'],'blocked')
                row['issue_refs']=[i['code'] for i in issues if i['check']==row['check_id']]
            return {**checks.report(),'issues':issues}
        initial=ledger('a'*64,{'input_contract':'passed','model_relations':'failed'},[
            {'code':'FIRST','path':'$','check':'model_relations'}])
        later=ledger('b'*64,{'input_contract':'failed','model_relations':'passed','floor_packing':'failed'},[
            {'code':'NEW','path':'$','check':'floor_packing'}, {'code':'BROKEN','path':'$','check':'input_contract'}])
        tracker=ProgressTracker();tracker.observe({'v':1},['FIRST:$'],initial)
        self.assertFalse(tracker.observe({'v':2},['NEW:$','BROKEN:$'],later))
        self.assertIn('floor_packing',tracker.advanced_checks)
        self.assertTrue(tracker.regressed)
        self.assertEqual(tracker.best_errors,frozenset(['FIRST:$']))

    def test_tracker_resume_preserves_cycle_and_high_water(self):
        _,_,first=fixture();second=deepcopy(first);second['objects']['shade']=blind(2.18)
        tracker=ProgressTracker()
        for draft in (first,second):
            report=diagnosis(draft);tracker.observe(draft,diagnostic_blockers(report,'error'),report)
        snapshot=tracker.snapshot();restored=ProgressTracker.restore(snapshot)
        for draft in (first,second):
            report=diagnosis(draft)
            self.assertFalse(restored.observe(draft,diagnostic_blockers(report,'error'),report))
            self.assertEqual(restored.decision,'repeated_candidate')
        self.assertEqual(restored.best_metrics,tracker.best_metrics)
        self.assertEqual(len(snapshot['history']),2)

    def test_targetless_photo_error_is_not_guessed_room_failure(self):
        _,_,draft=fixture()
        report=compiler_diagnosis(ValueError('PHOTO_PLACEMENT_DRAPE_BELOW_FLOOR'),draft,text_request())
        self.assertEqual(report['issues'][0]['code'],'UNMAPPED_COMPILER_ERROR')
        self.assertEqual(report['issues'][0]['path'],'$')
        self.assertIsNone(report['issues'][0]['actual'])

    def test_complete_candidate_has_only_executed_passes_no_physical_authority(self):
        _,_,draft=fixture(1.5);_,provenance=compile_scene(draft,empty_observation(),text_request())
        self.assertTrue(provenance['checks_complete'])
        self.assertEqual([r['check_id'] for r in provenance['checks']],list(PHASES))
        self.assertTrue(all(r['status']=='passed' for r in provenance['checks']))
        self.assertFalse(provenance['physical_authority'])

    def test_drape_final_check_and_derived_pose_keep_id_numeric_details(self):
        from twinpulse_core.photo_placement import drape_pose,validate_placement_plan,PLACEMENT_VERSION
        from twinpulse_core import SiteToolPlan
        for identity,parent_id,size in [('clothA','supportA',.91),('clothB','supportB',.73)]:
            _,_,draft=fixture(1.5);draft['objects'].pop('shade');draft['inventory']=draft['inventory'][1:]
            draft['inventory'][0]['id']=parent_id;draft['objects']={parent_id:bed()}
            payload,_=compile_scene(draft,empty_observation(),text_request())
            parent=next(c['arguments'] for c in payload['calls'] if c['tool']=='place_furniture')
            row=dict(id=identity,relation='drape',parent_id=parent_id,part='base',anchor='front',elevation_m=None)
            with self.assertRaises(GeometryValidationError) as generated:
                drape_pose(parent,'base','front',[.2,.1,size],identity=identity,placement=row)
            payload['calls'].append(dict(call_id='obj_'+identity,tool='place_room_item',arguments=dict(id=identity,
                kind='hanging_clothes',label='Cloth',catalog_version='room-items-1.0',position_m=[0,0,size/2],
                dimensions_m=[.2,.1,size],yaw_deg=0,observation_time_utc=None)))
            payload['call_evidence'].append(dict(call_id='obj_'+identity,basis='inferred',observation_ids=[],note='Controlled invalid drape'))
            with self.assertRaises(GeometryValidationError) as final:
                validate_placement_plan(SiteToolPlan.from_dict(payload),dict(schema_version=PLACEMENT_VERSION,relations=[
                    dict(id=parent_id,relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None),row]))
            issue=final.exception.contract_report['issues'][0]
            self.assertEqual(issue['target_ids'],[identity]);self.assertEqual(issue['related_ids'],[parent_id])
            self.assertEqual(issue['actual'],generated.exception.contract_report['issues'][0]['actual'])
            self.assertGreater(issue['violation_m'],0)

    def test_failed_exploration_budget_restores_best_in_checkpoint(self):
        structure,parameters,draft=fixture();worse=deepcopy(draft);worse['objects']['shade']=blind(2.3)
        with TemporaryDirectory() as folder:
            transport=RecordedFixture([structure,parameters,patch(draft,'shade',blind(2.3)),
                patch(worse,'shade',blind(2.35)),patch(draft,'shade',blind(2.4))])
            provider=generation_fixtures.PipelineTests.provider(self,transport,store_root=folder)
            with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):
                asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(text_request()))
            state=provider.store.read('checkpoint',provider.diagnostic_for('generation-test')['checkpoint_id'])
            self.assertEqual(state['draft']['objects']['shade'],draft['objects']['shade'])
            self.assertEqual(state['best_candidate']['objects']['shade'],draft['objects']['shade'])
            self.assertGreaterEqual(state['budget']['repairs'],2)
            self.assertGreaterEqual(state['budget']['stalled_repairs'],2)
            self.assertTrue(state['geometry_progress']['seen'])

    def test_version_mismatch_and_skipped_failures_do_not_fake_improvement(self):
        _,_,draft=fixture();initial=diagnosis(draft);tracker=ProgressTracker()
        tracker.observe(draft,diagnostic_blockers(initial,'error'),initial)
        for change in ('version','skipped'):
            report=deepcopy(initial)
            for row in report['checks']:
                if change=='version':row['compiler_revision']='changed'
                elif row['status']=='failed':row['status']='blocked'
            report['issues']=[]
            self.assertFalse(tracker.observe({'branch':change},[],report))
            self.assertEqual(tracker.decision,'evidence_insufficient')

    def test_corrupt_check_identity_is_insufficient_not_a_crash_or_pass(self):
        _,_,draft=fixture();initial=diagnosis(draft)
        for defect in ('missing_id','duplicate_id','invalid_dependencies'):
            tracker=ProgressTracker();tracker.observe(draft,diagnostic_blockers(initial,'error'),initial)
            report=deepcopy(initial)
            if defect=='missing_id':report['checks'][0].pop('check_id')
            elif defect=='duplicate_id':report['checks'][0]['check_id']=report['checks'][1]['check_id']
            else:report['checks'][0]['depends_on']=None
            self.assertFalse(tracker.observe({'branch':defect},[],report))
            self.assertEqual(tracker.decision,'evidence_insufficient')

    def test_estimated_geometry_pass_does_not_claim_photo_support_or_render_pass(self):
        from twinpulse_provider.semantic_scene import review_candidate_quality
        from twinpulse_provider.contracts import ImageInput
        _,_,draft=fixture(1.5);payload,provenance=compile_scene(draft,empty_observation(),text_request())
        original=deepcopy(draft)
        request=replace(text_request(),images=(ImageInput('explicit-fixture.jpg','image/jpeg',b'fixture-not-model-input'),))
        review=review_candidate_quality(draft,payload,provenance,empty_observation(),request)
        self.assertEqual(review['status'],'uncertain')
        self.assertEqual(review['support_relations'],'unverified_against_photo')
        self.assertEqual(review['render_comparison'],'not_run')
        self.assertEqual(review['candidate_revision'],revision(draft))
        self.assertEqual(draft,original)
        public=_public_generation_diagnostics({'quality_review':review,'stage_acceptance':{
            'approximate_draft':'passed','photo_quality':'uncertain','SIM_Run_Stop':'not_run'}})
        self.assertEqual(public['stage_acceptance']['approximate_draft'],'passed')
        self.assertEqual(public['stage_acceptance']['photo_quality'],'uncertain')
        self.assertNotIn('observed_photo_relations',public['quality_review'])

    def test_estimated_room_change_can_resolve_error_without_object_edit(self):
        structure,parameters,draft=fixture()
        corrected=dict(draft['room'],height_m=2.6)
        operation=dict(patch_version=PATCH_REVISION,base_revision=revision(draft),
            operations=[dict(op='room',value=corrected)])
        result,provider,transport=self.run_pipeline([structure,parameters,operation])
        self.assertTrue(result.provider_provenance['patches'][0]['room_changed'])
        self.assertEqual(result.provider_provenance['patches'][0]['changed_ids'],[])
        self.assertEqual(provider.diagnostic_for('generation-test')['attempts'][-1]['candidate_validation'],'passed')

    def test_independent_parent_graph_failures_keep_ids_and_blocked_checks(self):
        a=dict(id='a',kind='window_blind',**blind(1.2))
        b=dict(id='b',kind='window_blind',**blind(1.2))
        for row,parent in ((a,'b'),(b,'a')):
            row['placement'].update(relation='surface',parent_id=parent,part='body',elevation_m=None)
        with self.assertRaises(GeometryValidationError) as caught:
            _checked_model_relations([a,b],3,{})
        report=caught.exception.contract_report
        self.assertTrue(any('CYCLE' in i['code'] for i in report['issues']))
        self.assertTrue(report['blocked_checks'])
        self.assertEqual(set(i for row in report['issues'] for i in row['target_ids']),{'a','b'})


if __name__=='__main__':unittest.main()
