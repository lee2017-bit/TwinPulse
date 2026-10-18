# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic bounded conflict evidence; scripted transport is not model quality."""
import asyncio
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from test_photo_parametric import object_intent,intent,compile
from test_geometry_repair_loop import RecordedFixture
import test_budgeted_generation as generation_fixtures
from test_budgeted_generation import text_request,empty_observation,config
from twinpulse_provider import GenerationService
from twinpulse_provider.photo_layout import PhotoLayoutPackingError,_packing_separated
from twinpulse_provider.semantic_scene import (checked_structure,checked_batch,scene_draft,
    compiler_diagnosis,compile_scene,geometry_repair_context,patch_candidate,revision,PATCH_REVISION)
from twinpulse_provider.repair_scope import scope_options
from twinpulse_provider.scene_contract import SceneContractError
from twinpulse_provider.generation_policy import (ProgressTracker,diagnostic_blockers,
    ExecutionBudget,GenerationPolicy,GenerationBudgetError)
from twinpulse_core.geometry_checks import GeometryChecks
from twinpulse_core.geometry_diagnostics import geometry_issue,geometry_report
from twinpulse_core import canonical_sha256


def crowded():
    rows=[object_intent(identity,'bed',size=[2.5,2.5,.5]) for identity in ('a','b','c')]
    rows.append(object_intent('fabric','bedding_overhang',parent='a',part='mattress',
        relation='drape',anchor='front',size=[.5,.2,.1]))
    return rows


def draft_for(rows):
    structure=dict(summary='Explicit synthetic estimated assemblies',
        room=dict(width_m=4,length_m=4,height_m=2.6),
        inventory=[dict(id=r['id'],kind=r['kind'],evidence_ref='hypothesis') for r in rows])
    objects={r['id']:{k:deepcopy(v) for k,v in r.items() if k not in ('id','kind','observation_ids')} for r in rows}
    value=checked_batch(objects,scene_draft(checked_structure(structure,text_request(),empty_observation())),list(objects))
    return structure,objects,value


def diagnose(value):
    try:compile_scene(value,empty_observation(),text_request())
    except ValueError as error:return compiler_diagnosis(error,value,text_request())
    raise AssertionError('fixture must fail the ordinary compiler')


def ledger(branch,identities,*,broken_input=False,resolved_floor=False):
    issues=[geometry_issue('PHOTO_LAYOUT_REGION_FULL',i,path='$.objects.'+i+'.region') for i in identities]
    if resolved_floor:issues=[geometry_issue('PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE','child',path='$.objects.child.placement')]
    if broken_input:issues.append(geometry_issue('INDEPENDENT_INPUT_FAILURE','source',path='$.source'))
    checks=GeometryChecks(canonical_sha256({'branch':branch}),'generic-fixture','catalog',identities)
    for row in checks.rows:
        phase=row['check_id']
        row['status']='passed' if phase in ('input_contract','model_relations') else 'blocked'
        if phase=='floor_packing':row['status']='passed' if resolved_floor else 'failed'
        if phase=='support_packing' and resolved_floor:row['status']='failed'
        if phase=='input_contract' and broken_input:row['status']='failed'
        row['issue_refs']=[i['issue_id'] for i in issues if
            (i['code']=='PHOTO_LAYOUT_REGION_FULL' and phase=='floor_packing') or
            (i['code']=='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE' and phase=='support_packing') or
            (i['code']=='INDEPENDENT_INPUT_FAILURE' and phase=='input_contract')]
    return {**geometry_report(issues),**checks.report()}


class PackingConflictSetTests(unittest.TestCase):
    def test_every_failed_assembly_and_actual_blocker_counts_are_retained(self):
        value=intent(*crowded(),width=4,length=4);original=deepcopy(value)
        with self.assertRaises(PhotoLayoutPackingError) as caught:compile(value)
        report=caught.exception.packing_report;proof=report['conflict_set']
        self.assertEqual(proof['failed_ids'],['b','c']);self.assertTrue(proof['complete'])
        self.assertFalse(proof['physical_authority'])
        self.assertEqual({tuple(i['target_ids']) for i in caught.exception.contract_report['issues']},{('b',),('c',)})
        self.assertEqual([v['id'] for v in proof['placed_assemblies']],['a'])
        placed=proof['placed_assemblies'][0];px,py=placed['centre_xy_m']
        bounds=placed['assembly']['local_xy_bounds_m']
        self.assertEqual(placed['translated_proxy_xy_bounds_m'],[px+bounds[0],px+bounds[1],py+bounds[2],py+bounds[3]])
        for failed in proof['conflicts']:
            self.assertEqual(failed['grid']['blocked_candidate_count'],failed['grid']['domain_count'])
            blocker=failed['placed_blockers'][0]
            self.assertEqual(blocker['id'],'a');self.assertEqual(blocker['dependency_ids'],['fabric'])
            self.assertEqual(blocker['blocked_candidate_count'],failed['grid']['domain_count'])
            xmin,xmax,ymin,ymax=failed['assembly']['parent_floor_domain_xy_m']
            # The ordinary compiler's entire middle-centre grid is blocked by
            # the same signed AABB predicate, not a claimed global proof.
            from twinpulse_provider.packing_candidates import floor_candidates
            actual=sum(not _packing_separated(failed['assembly']['local_xy_bounds_m'],x,y,bounds,px,py)
                for _,x,y in floor_candidates(failed['assembly']['local_xy_bounds_m'],4,4,
                    failed['region'],[('a',px,py,bounds)]))
            self.assertEqual(actual,blocker['blocked_candidate_count'])
        search=report['bounded_search']
        self.assertEqual((search['max_nodes'],search['timeout_s'],search['branch_cap']),(512,2,32))
        self.assertFalse(search['global_infeasibility_proved']);self.assertEqual(value,original)

    def test_scope_evidence_reaches_repair_without_implicitly_unlocking_blocker(self):
        _,_,value=draft_for(crowded());original=deepcopy(value);report=diagnose(value)
        scope,options=scope_options(value,report)
        self.assertEqual({r['id'] for r in scope['targets']},{'b','c'})
        self.assertEqual({(r['id'],r['anchor_id'],r['evidence']) for r in options},
            {('a',i,'compiled_occupied_proxy_blocks_candidate_grid') for i in ('b','c')})
        changed=dict(value['objects']['a'],region='rear_left')
        patch=dict(patch_version=PATCH_REVISION,base_revision=revision(value),
            operations=[dict(op='update',id='a',value=changed)])
        with self.assertRaisesRegex(SceneContractError,'SEMANTIC_PATCH_OUTSIDE_REPAIR_SCOPE'):
            patch_candidate(value,patch,empty_observation(),text_request(),repair_diagnosis=report)
        patch['operations'].insert(0,dict(op='request_scope',id='a',anchor_id='b',reason_code='packing_neighbor'))
        after=patch_candidate(value,patch,empty_observation(),text_request(),repair_diagnosis=report)
        self.assertEqual(after['objects']['a']['region'],'rear_left')
        self.assertEqual(after['objects']['fabric'],value['objects']['fabric']);self.assertEqual(value,original)
        self.assertIn('fabric',geometry_repair_context(value,{'issues':[dict(target_ids=['a'])]})['room_change_requires_recheck'])

    def test_actual_blocker_eligible_across_estimated_regions_but_unrelated_is_not(self):
        _,_,value=draft_for(crowded())
        value['objects']['b']['region']='rear_right';value['objects']['a']['region']='front_left'
        value['objects']['c']['region']='front_left'
        report=dict(issues=[dict(code='PHOTO_LAYOUT_REGION_FULL',target_ids=['b'],actual={'packing':{
            'conflict_set':dict(schema_version='photo-packing-conflict-set-1.0',physical_authority=False,
                conflicts=[dict(id='b',placed_blockers=[dict(id='a',blocked_candidate_count=1)])])}})])
        context,options=scope_options(value,report)
        self.assertEqual({r['id'] for r in context['targets']},{'b'})
        self.assertEqual({r['id'] for r in options},{'a'})
        report['issues'][0]['actual']=2.2
        self.assertEqual(scope_options(value,report)[1],[])

    def test_full_set_order_first_target_exchange_and_subset_are_comparison_uncertain(self):
        for first,later in ((['b','c'],['c','b']),(['b'],['c']),(['b','c'],['c'])):
            with self.subTest(first=first,later=later):
                tracker=ProgressTracker();initial=ledger(1,first);last=ledger(2,later)
                self.assertFalse(tracker.observe({'branch':1},diagnostic_blockers(initial,''),initial))
                self.assertFalse(tracker.observe({'branch':2},diagnostic_blockers(last,''),last))
                self.assertFalse(tracker.regressed);self.assertTrue(tracker.comparison_uncertain)
                self.assertEqual(tracker.decision,'no_progress');self.assertEqual(tracker.history[-1]['comparison_basis'],
                    'same_unresolved_bounded_floor_packing_phase')
                self.assertEqual(tracker.best_errors,frozenset(diagnostic_blockers(initial,'')))

    def test_independent_pass_regression_still_blocks_and_true_phase_completion_advances(self):
        initial=ledger(1,['b','c'])
        for broken,expected in ((True,False),(False,True)):
            tracker=ProgressTracker();tracker.observe({'branch':1},diagnostic_blockers(initial,''),initial)
            last=ledger(2,['c'],broken_input=broken,resolved_floor=not broken)
            self.assertEqual(tracker.observe({'branch':2},diagnostic_blockers(last,''),last),expected)
            self.assertEqual(tracker.regressed,broken)
            self.assertEqual(tracker.comparison_uncertain,broken)
            if not broken:self.assertIn('support_packing',tracker.advanced_checks)

    def test_restore_keeps_no_progress_and_stalled_two_without_false_rollback(self):
        tracker=ProgressTracker();initial=ledger(1,['b','c'])
        tracker.observe({'branch':1},diagnostic_blockers(initial,''),initial)
        budget=ExecutionBudget(GenerationPolicy())
        for index,ids in ((2,['c']),(3,['b'])):
            tracker=ProgressTracker.restore(tracker.snapshot());last=ledger(index,ids)
            progress=tracker.observe({'branch':index},diagnostic_blockers(last,''),last)
            self.assertFalse(progress);self.assertFalse(tracker.regressed)
            if index==2:budget.repair_result(progressed=progress);self.assertEqual(budget.no_progress,1)
            else:
                with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):budget.repair_result(progressed=progress)

    def test_scripted_provider_receives_full_conflicts_and_stalls_in_original_budget(self):
        structure,objects,value=draft_for(crowded());original=deepcopy(value)
        patch1=dict(patch_version=PATCH_REVISION,base_revision=revision(value),operations=[
            dict(op='update',id='b',value=dict(objects['b'],region='front_left'))])
        middle=patch_candidate(value,patch1,empty_observation(),text_request(),repair_diagnosis=diagnose(value))
        patch2=dict(patch_version=PATCH_REVISION,base_revision=revision(middle),operations=[
            dict(op='update',id='c',value=dict(objects['c'],region='rear_right'))])
        transport=RecordedFixture([structure,objects,patch1,patch2]);provider=generation_fixtures.PipelineTests.provider(self,transport)
        with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):
            asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(text_request()))
        self.assertEqual(len(transport.bodies),4)
        for body in transport.bodies[2:]:
            content=json.loads(body['messages'][-1]['content'])
            proof=content['validation']['issues'][0]['actual']['packing']['conflict_set']
            self.assertEqual(proof['failed_ids'],['b','c']);self.assertTrue(proof['complete'])
            self.assertIn('conflict_set',body['messages'][0]['content'])
        decisions=[record for name,_,record in transport.records if name=='geometry_repair_decision']
        self.assertEqual(decisions[0]['decision'],'initial')
        self.assertTrue(all(row['comparison_uncertain'] and not row['regressed'] and not row['progressed'] for row in decisions[1:]))
        self.assertEqual(provider.diagnostic_for('generation-test')['budget']['repairs'],2)
        self.assertEqual(value,original)


if __name__=='__main__':unittest.main()
