# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic phase regressions, not a real-model/user acceptance substitute."""
from pathlib import Path
import sys
import unittest
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[3]
for name in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core.geometry_checks import GeometryChecks
from twinpulse_core import canonical_sha256
from twinpulse_provider.generation_policy import ProgressTracker, ExecutionBudget, GenerationPolicy, GenerationBudgetError
from twinpulse_provider.errors import ProviderConfigurationError


def ledger(rev, **statuses):
    checks=GeometryChecks(rev,'compiler','library',['example'])
    for row in checks.rows:row['status']=statuses.get(row['check_id'],'passed')
    return checks.report()|{'issues':[]}


class PartialProgressTests(unittest.TestCase):
    def test_time_limited_witness_probe_count_is_telemetry_not_geometry(self):
        from twinpulse_provider.partial_refinement import same_support_witness
        search=dict(schema_version='photo-support-bounded-search-1.0',status='BOUNDED_SEARCH_FAILED',
            termination_code='TIME_BUDGET_EXHAUSTED',parent_id='parent',part='top',nodes=0,max_nodes=512,
            geometry_checks=394,max_geometry_checks=65536,timeout_s=2.,branch_cap=32,branches_truncated=0,
            overlap_pruned=0,phase='domain_generation',domain_generation_complete=False,
            domain_counts={'item':0},elapsed_s=2.003189,global_infeasibility_proved=False,
            scope='SAME_SELECTED_SURFACE_GRID_NOT_MEASURED_FREE_SPACE',physical_authority=False)
        witness=dict(sha256='a'*64,source_sha256='b'*64,inventory=[dict(id='item')],
            unresolved=[dict(id='item',hazard='low',parent_id='parent',
                evidence=dict(issue_id='c'*64,actual={'reason':'SUPPORT_CLEARANCE_EXCEEDED'},
                    expected=dict(parent_id='parent',bounded_search=search)))])
        original=deepcopy(witness);fresh=deepcopy(witness)
        fresh['sha256']='d'*64
        observed=fresh['unresolved'][0]['evidence']['expected']['bounded_search']
        observed.update(geometry_checks=392,elapsed_s=2.001999)
        self.assertTrue(same_support_witness(fresh,witness))
        self.assertEqual(witness,original)
        self.assertEqual(observed['geometry_checks'],392)
        for key in ('schema_version','max_nodes','max_geometry_checks','timeout_s','branch_cap','nodes',
                    'branches_truncated','overlap_pruned','phase','domain_generation_complete',
                    'domain_counts','parent_id','part','status','termination_code','scope',
                    'global_infeasibility_proved','physical_authority'):
            bad=deepcopy(fresh);s=bad['unresolved'][0]['evidence']['expected']['bounded_search']
            s[key]=('changed' if type(s[key]) is str else not s[key] if type(s[key]) is bool
                else {'changed':1} if isinstance(s[key],dict) else s[key]+1)
            with self.subTest(field=key):self.assertFalse(same_support_witness(bad,witness))
        for count in (None,True,-1,65537,392.0):
            bad=deepcopy(fresh);bad['unresolved'][0]['evidence']['expected']['bounded_search']['geometry_checks']=count
            with self.subTest(count=count):self.assertFalse(same_support_witness(bad,witness))
        for path in ('hazard','parent_id','id'):
            bad=deepcopy(fresh);bad['unresolved'][0][path]='changed'
            with self.subTest(field=path):self.assertFalse(same_support_witness(bad,witness))
        bad=deepcopy(fresh);bad['source_sha256']='e'*64
        self.assertFalse(same_support_witness(bad,witness))
        bad=deepcopy(fresh);bad['inventory'][0]['dimensions_m']=[1,2,3]
        self.assertFalse(same_support_witness(bad,witness))
        for termination in ('FOUND','EMPTY_VALID_DOMAIN','GEOMETRY_CHECK_BUDGET_EXHAUSTED',
                            'GRID_SEARCH_EXHAUSTED','BRANCH_BUDGET_EXHAUSTED'):
            a,b=deepcopy(witness),deepcopy(fresh)
            for value in (a,b):
                value['unresolved'][0]['evidence']['expected']['bounded_search']['termination_code']=termination
            with self.subTest(termination=termination):self.assertFalse(same_support_witness(a,b))

    def test_mixed_layout_keeps_numerical_support_capability_without_layout_authority(self):
        from twinpulse_provider.model_capability_repair import capability_diagnosis
        from test_progressive_twin import fixture
        from twinpulse_provider.semantic_scene import compile_scene
        request,obs,draft=fixture();_,report=compile_scene(draft,obs,request,progressive=True)
        layout=dict(code='RENDER_LAYOUT_MISMATCH',target_ids=['unrelated_desk'])
        quality=dict(issues=[layout],layout_hypotheses=[{'id':'desk'}])
        value=capability_diagnosis(quality,report['progressive_twin'])
        self.assertNotIn(layout,value['issues'])
        self.assertEqual(value['issues'],[r['evidence'] for r in report['progressive_twin']['unresolved']])
        self.assertEqual(quality['issues'],[layout])
        self.assertEqual(capability_diagnosis(quality,{})['issues'],[])

    def test_support_alternatives_include_surface_materialized_later_in_same_group(self):
        from test_support_repacking import supported_fixture
        from twinpulse_provider.semantic_scene import compile_scene
        request,obs,draft=supported_fixture('dining_table',(1.8,1.,.75),(.3,.3,.1),2,'top')
        draft['inventory'][1]['kind']='surface_covering'
        draft['objects']['item_0'].update(model_id='common.surface_covering',dimensions_m=[1.7,.9,.03])
        draft['inventory'][2]['kind']='tabletop_item'
        draft['objects']['item_1']['model_id']='common.tabletop_item'
        before=deepcopy(draft);plan,report=compile_scene(draft,obs,request,progressive=True)
        pending=report['progressive_twin']['unresolved']
        self.assertEqual([r['id'] for r in pending],['item_1'])
        options=pending[0]['evidence']['expected']['support_options']
        nested=next(r for r in options if r['parent_id']=='item_0' and r['part']=='top')
        self.assertTrue(nested['footprint_fits'])
        self.assertEqual(nested['clearance_and_photo_relation'],'requires_revalidation')
        self.assertEqual(draft,before)
        self.assertNotIn('item_1',{c['arguments']['id'] for c in plan['calls']})

    def test_executed_blocked_to_partial_requires_exact_plan_and_pending_witness(self):
        from test_progressive_twin import fixture
        from twinpulse_provider.semantic_scene import compile_scene,revision
        from twinpulse_provider.generation_policy import diagnostic_blockers
        request,obs,draft=fixture()
        plan,report=compile_scene(draft,obs,request,progressive=True)
        report['issues']=[r['evidence'] for r in report['progressive_twin']['unresolved']]
        initial=deepcopy(report)
        initial['issues']=[{'code':'PHOTO_LAYOUT_REGION_FULL','path':'$','target_ids':['support']}]
        for row in initial['checks']:
            if row['check_id']=='floor_packing':row.update(status='failed',issue_refs=['PHOTO_LAYOUT_REGION_FULL'])
            elif row['check_id'] in ('support_packing','attachment_placement','tool_executor','placement_validation','evidence_binding'):
                row.update(status='blocked',issue_refs=[])
        initial['candidate_revision']='a'*64
        for row in initial['checks']:row['candidate_revision']='a'*64
        def tracker():
            t=ProgressTracker();t.observe({'fixture':'initial'},diagnostic_blockers(initial,''),initial);return t
        t=tracker()
        self.assertTrue(t.observe(draft,diagnostic_blockers(report,''),report,checked_plan=plan))
        self.assertFalse(t.regressed);self.assertIn('support_packing',t.advanced_checks)
        self.assertEqual(t.best_checks['support_packing']['status'],'partial')
        for change in ('no_plan','witness','issue_refs','candidate','plan'):
            changed=deepcopy(report);changed_plan=deepcopy(plan);candidate=deepcopy(draft)
            if change=='witness':changed['progressive_twin']['sha256']='b'*64
            if change=='issue_refs':next(r for r in changed['checks'] if r['check_id']=='support_packing')['issue_refs']=[]
            if change=='candidate':candidate['room']['width_m']+=1
            if change=='plan':changed_plan['calls'][0]['arguments']['size_m'][0]+=1
            with self.subTest(change=change):
                t=tracker();self.assertFalse(t.observe(candidate,diagnostic_blockers(changed,''),changed,
                    checked_plan=None if change=='no_plan' else changed_plan))
        # A formerly passed support phase remains a regression even with a
        # valid partial witness, not permission to discard its child.
        full=deepcopy(report)
        for row in full['checks']:row['status']='passed'
        full['issues']=[]
        t=ProgressTracker();t.observe({'fixture':'full'},[],full)
        self.assertFalse(t.observe(draft,diagnostic_blockers(report,''),report,checked_plan=plan))
        self.assertTrue(t.regressed)

    def test_support_quality_wrapper_preserves_original_pending_risk_and_parent(self):
        from test_progressive_twin import fixture
        from twinpulse_provider.semantic_scene import compile_scene
        from twinpulse_provider.partial_refinement import support_refinement_quality
        request,obs,draft=fixture();plan,report=compile_scene(draft,obs,request,progressive=True)
        original=deepcopy(report)
        quality=support_refinement_quality(draft,plan,report)
        self.assertEqual(quality['status'],'needs_revision');self.assertEqual(quality['photo_comparison'],'not_run')
        self.assertEqual(quality['render_comparison'],'not_run')
        for wrapper,pending in zip(quality['issues'],report['progressive_twin']['unresolved']):
            self.assertEqual(wrapper['target_ids'],[pending['parent_id']])
            self.assertEqual(wrapper['source_issue'],pending)
            self.assertNotEqual(wrapper['issue_id'],pending['evidence']['issue_id'])
        self.assertEqual(report,original)

    def test_support_limit_retains_subset_only_after_settled_exact_limit(self):
        from test_progressive_twin import fixture
        from twinpulse_provider.semantic_scene import compile_scene,revision
        from twinpulse_provider.partial_refinement import support_refinement_quality,same_support_witness
        from twinpulse_core.draft_refinement import create_refinement,checked_refinement
        request,obs,draft=fixture();plan,report=compile_scene(draft,obs,request,progressive=True)
        quality=support_refinement_quality(draft,plan,report)
        budget=ExecutionBudget(GenerationPolicy())
        for _ in range(budget.policy.max_repairs):
            identity=budget.reserve({'model':'fixture-no-network','max_tokens':10},role='repair')
            budget.settle(identity,usage={'prompt_tokens':1,'completion_tokens':1},status='received')
        budget.stop('SUPPORT_REPAIR_LIMIT_REACHED')
        value=create_refinement(plan,request_id=request.request_id,candidate_revision=revision(draft),
            source_observation_sha256='a'*64,quality=quality,checks=report,budget=budget.snapshot(),
            progressive=report['progressive_twin'])
        self.assertEqual(value['stop_reason'],'SUPPORT_REPAIR_LIMIT_REACHED')
        self.assertEqual(value['acceptance'],'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE')
        for mutation in ('premature','unknown','full'):
            bad=deepcopy(value)
            if mutation=='premature':bad['budget']['max_repairs']+=1
            if mutation=='unknown':bad['budget']['attempts'][-1]['status']='outcome_unknown'
            if mutation=='full':
                bad.update(schema_version='draft-refinement-1.0',acceptance='GEOMETRY_VALID_REFINEMENT_INCOMPLETE')
                bad.pop('progressive_sha256')
            bad['sha256']=canonical_sha256({k:v for k,v in bad.items() if k!='sha256'})
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                checked_refinement(bad,plan,request_id=request.request_id,
                    progressive=None if mutation=='full' else report['progressive_twin'])
        fresh=deepcopy(report['progressive_twin'])
        fresh['unresolved'][0]['evidence']['expected']['bounded_search']['elapsed_s']+=1
        self.assertTrue(same_support_witness(fresh,report['progressive_twin']))
        fresh['unresolved'][0]['hazard']='unknown'
        self.assertFalse(same_support_witness(fresh,report['progressive_twin']))

    def test_rebound_partial_keeps_pending_evidence_and_does_not_self_regress(self):
        pending={'code':'PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE','target_ids':['example'],'related_ids':['parent'],
            'issue_id':'a'*64,'actual':{'reason':'SURFACE_CAPACITY_EXCEEDED'},'expected':{'parent_id':'parent'}}
        report=ledger('a'*64,support_packing='partial')
        report['progressive_twin']={'unresolved':[{'id':'example','evidence':pending}]}
        t=ProgressTracker();t.rebind_locally_checked_best({'value':1},report)
        checked={**report,'issues':[pending]}
        from twinpulse_provider.generation_policy import diagnostic_blockers
        t.observe({'value':1},diagnostic_blockers(checked,''),checked)
        self.assertFalse(t.regressed)
        self.assertTrue(t.best_errors)

    def test_terminal_stall_allows_local_preview_time_but_zero_external_dispatch(self):
        budget=ExecutionBudget(GenerationPolicy())
        budget.stop('REPAIR_STALLED')
        self.assertGreater(budget.timeout_for('final_review'),0)
        for role in ('initial','repair','final_review'):
            with self.subTest(role=role),self.assertRaises(GenerationBudgetError):
                budget.reserve({'model':'explicit-fixture-no-network','max_tokens':10},role=role)
        self.assertEqual(budget.rows,[])
        self.assertEqual(budget.terminal,'REPAIR_STALLED')

    def test_partial_is_valid_unfinished_and_protects_passed_floor(self):
        t=ProgressTracker()
        partial=ledger('a'*64,support_packing='partial')
        self.assertFalse(t.observe({'value':1},[],partial))
        self.assertEqual(t.decision,'initial')
        self.assertFalse(partial['checks_complete'])
        self.assertEqual(t.best_checks['support_packing']['status'],'partial')
        bad=ledger('b'*64,floor_packing='failed',support_packing='blocked')
        self.assertFalse(t.observe({'value':2},['PHOTO_LAYOUT_REGION_FULL'],bad))
        self.assertTrue(t.regressed)
        self.assertEqual(t.best_checks['floor_packing']['status'],'passed')

    def test_passed_to_partial_is_regression_not_success(self):
        t=ProgressTracker();t.observe({'value':1},[],ledger('a'*64))
        t.observe({'value':2},[],ledger('b'*64,support_packing='partial'))
        self.assertTrue(t.regressed)
        self.assertFalse(t.advanced_checks)

    def test_old_baseline_rebind_preserves_seen_history_and_requires_fresh_evidence(self):
        t=ProgressTracker();t.observe({'value':1},['old'],ledger('a'*64,floor_packing='failed'))
        seen=set(t.seen);history=deepcopy(t.history)
        partial=ledger('b'*64,support_packing='partial')
        t.rebind_locally_checked_best({'value':2},partial)
        self.assertTrue(seen <= t.seen)
        self.assertEqual(t.history[:len(history)],history)
        self.assertFalse(t.history[-1]['checks_complete'])
        with self.assertRaises(ProviderConfigurationError):
            t.rebind_locally_checked_best({'value':3},ledger('c'*64,floor_packing='failed'))

    def test_rebind_uses_the_pipeline_object_identity_representation(self):
        raw={'room':{'width_m':5},'inventory':[{'id':'example'}],
             'objects':{'example':{'region':'rear_left'}}}
        report=ledger(canonical_sha256(raw),support_packing='partial')
        public={**raw,'objects':[dict(id=i,**v) for i,v in raw['objects'].items()]}
        t=ProgressTracker();t.observe(public,[],report)
        prior=t.best_previous
        t.rebind_locally_checked_best(raw,report)
        self.assertEqual(t.best_previous,prior)
