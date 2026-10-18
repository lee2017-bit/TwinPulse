# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Zero-network compiler/service/save/reopen tests, never fresh model scores."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_support_repacking import supported_fixture
import test_budgeted_generation as generation_fixtures
from test_budgeted_generation import FixtureTransport, config
from twinpulse_provider import GenerationService
from twinpulse_provider.semantic_scene import compile_scene
from twinpulse_core import InputRevision, SiteToolPlan, canonical_sha256
from twinpulse_core.geometry_diagnostics import GeometryValidationError
from twinpulse_core.photo_placement import placement_contract_from_trace
from twinpulse_core.progressive_twin import checked_envelope, issue_impact, require_task_context, summary
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.project_store import ProjectRecord, ProjectStore


def fixture():
    request, observation, draft = supported_fixture('storage', (.8,.445,.9), (.9,.6,.1), 1, 'body')
    draft['inventory'][1]['kind']='tabletop_item'
    draft['objects']['item_0']['model_id']='common.tabletop_item'
    return request, observation, draft


def native_child_fixture(kind='bedding_overhang'):
    request,observation,draft=supported_fixture('bed',(1.4,2.,.9),(1.4,2.,.05),1,'mattress')
    draft['inventory'][1]['kind']=kind
    from twinpulse_core.model_library import library_models
    draft['objects']['item_0']['model_id']=next(r['model_id'] for r in library_models() if r['kind']==kind)
    return request,observation,draft


def nested_pending_fixture():
    request,observation,draft=native_child_fixture('surface_covering')
    row=deepcopy(draft['inventory'][1]);row.update(id='nested_prop',kind='unknown')
    draft['inventory'].append(row)
    from test_warehouse_semantics import parameter
    draft['objects']['nested_prop']=parameter('unknown',(.1,.1,.1),parent='item_0',part='top')
    return request,observation,draft


def record(request, payload, trace, *, progressive=True):
    revision=InputRevision.create(prompt=request.prompt, images=[], measurement_constraints=[],
        profile_id='fixture', generation_settings={'model_id':'fixture'})
    return SiteDraftRecord.create(request_id=request.request_id,provider_name='fixture',model_id='fixture',
        image_count=0,input_revision=revision,plan=SiteToolPlan.from_dict(payload),
        placement_contract=placement_contract_from_trace(trace),
        progressive_twin=trace['progressive_twin'] if progressive else None)


class ProgressiveTwinTests(unittest.TestCase):
    def test_pending_support_closure_keeps_original_parent_and_all_risk(self):
        request,obs,draft=nested_pending_fixture();before=deepcopy(draft)
        with self.assertRaises(GeometryValidationError):compile_scene(draft,obs,request)
        payload,trace=compile_scene(draft,obs,request,progressive=True)
        witness=checked_envelope(trace['progressive_twin'],payload)
        self.assertEqual(witness['schema_version'],'progressive-twin-1.2')
        self.assertEqual(witness['policy_version'],'progressive-acceptance-1.1')
        self.assertEqual(draft,before)
        by_id={r['id']:r for r in witness['unresolved']}
        self.assertEqual(set(by_id),{'item_0','nested_prop'})
        child=by_id['nested_prop']
        self.assertEqual(child['parent_id'],'item_0');self.assertEqual(child['part'],'top')
        self.assertEqual(child['code'],'PARENT_VALIDATION_PENDING')
        self.assertEqual(child['bounds_z_m'],[0.,8.]);self.assertEqual(child['hazard'],'unknown')
        self.assertEqual(child['materialized_anchor_id'],'support')
        self.assertEqual(child['ancestor_path'],['nested_prop','item_0','support'])
        self.assertEqual(child['root_issue_id'],by_id['item_0']['evidence']['issue_id'])
        self.assertFalse({'item_0','nested_prop'}&{c['arguments']['id'] for c in payload['calls']})
        from twinpulse_provider.partial_refinement import support_refinement_quality
        quality=support_refinement_quality(draft,payload,trace)
        self.assertTrue(all(r['target_ids']==['support'] for r in quality['issues']))
        for physical in (False,True):
            with self.assertRaisesRegex(ValueError,'PROGRESSIVE_TASK_UNRESOLVED'):
                require_task_context(witness,robot_top_m=4.,physical=physical)

    def test_pending_closure_rejects_rehashed_cycle_orphan_bounds_model_and_wrong_part(self):
        request,obs,draft=nested_pending_fixture();payload,trace=compile_scene(draft,obs,request,progressive=True)
        original=trace['progressive_twin']
        for mutate in (lambda v:v['unresolved'][1].update(bounds_z_m=[5.,6.]),
                lambda v:v['unresolved'][1].update(materialized_anchor_id='missing'),
                lambda v:v['unresolved'][1].update(ancestor_path=['nested_prop','support']),
                lambda v:v['unresolved'][1].update(root_issue_id='f'*64),
                lambda v:v['unresolved'][1].update(parent_id='nested_prop'),
                lambda v:v['inventory'][2]['parameters'].update(model_id='common.invented'),
                lambda v:v['inventory'][2]['parameters']['placement'].update(part='missing'),
                lambda v:v['inventory'][1]['parameters']['placement'].update(relation='floor')):
            bad=deepcopy(original);mutate(bad);bad['sha256']=canonical_sha256({k:v for k,v in bad.items() if k!='sha256'})
            with self.subTest(bad=bad['sha256']),self.assertRaises((ValueError,KeyError)):
                checked_envelope(bad,payload)

    def test_pending_closure_saved_reopen_parent_move_and_undo_preserve_graph_and_gate(self):
        request,obs,draft=nested_pending_fixture();payload,trace=compile_scene(draft,obs,request,progressive=True)
        source=record(request,payload,trace)
        with TemporaryDirectory() as folder:
            store=ProjectStore(Path(folder)/'project.json');store.save(ProjectRecord('default',source.input_revision,site_draft=source))
            source=ProjectStore(store.path).load().site_draft
        from twinpulse_app.dependency_patch import initial_state,apply_patch_state,PATCH_VERSION
        state=initial_state(source);call=deepcopy(next(c.to_dict() for c in state.plan.calls if c.arguments['id']=='support'))
        call['arguments']['center_m'][0]+=.1
        changed,affected=apply_patch_state(source,state,dict(patch_version=PATCH_VERSION,
            edits=[dict(action='change',target_id='support',reason='Synthetic user feedback',tool_call=call)]),state.site.scene.revision)
        self.assertTrue({'support','item_0','nested_prop'}<=affected)
        current=changed.progressive(source)
        self.assertEqual(current['policy_version'],'progressive-acceptance-1.1')
        self.assertEqual(changed.inventory['nested_prop']['placement']['parent_id'],'item_0')
        with self.assertRaises(ValueError):require_task_context(current,robot_top_m=4.)
        # Common Undo restores the exact prior EffectiveScene; it must not
        # materialize the child or reuse the changed scene's authority.
        self.assertEqual(initial_state(source).inventory,state.inventory)

    def test_three_level_pending_closure_keeps_entanglement_and_rejects_materialized_descendant(self):
        request,obs,draft=nested_pending_fixture()
        draft['inventory'][2]['kind']='tabletop_item'
        draft['objects']['nested_prop']['model_id']='common.tabletop_item'
        row=deepcopy(draft['inventory'][2]);row.update(id='third',kind='clothing_pile')
        draft['inventory'].append(row)
        from test_warehouse_semantics import parameter
        draft['objects']['third']=parameter('clothing_pile',(.1,.1,.1),parent='nested_prop',part='top')
        from twinpulse_core.model_library import library_models
        draft['objects']['third']['model_id']=next(r['model_id'] for r in library_models() if r['kind']=='clothing_pile')
        payload,trace=compile_scene(draft,obs,request,progressive=True)
        witness=checked_envelope(trace['progressive_twin'],payload)
        child=next(r for r in witness['unresolved'] if r['id']=='third')
        self.assertEqual(child['ancestor_path'],['third','nested_prop','item_0','support'])
        self.assertEqual(child['hazard'],'entanglement');self.assertEqual(child['bounds_z_m'],[0.,8.])
        source=SiteDraftRecord.from_dict(record(request,payload,trace).to_dict())
        from twinpulse_app.dependency_patch import initial_state
        current=initial_state(source).progressive(source)
        self.assertEqual(next(r for r in current['unresolved'] if r['id']=='third')['hazard'],'entanglement')
        with self.assertRaises(ValueError):require_task_context(current,robot_top_m=4.)
        invalid=deepcopy(witness);plan=deepcopy(payload)
        plan['calls'].append(dict(call_id='fake_third',tool='place_room_item',arguments=dict(id='third')))
        invalid['plan_sha256']=canonical_sha256(plan)
        invalid['unresolved']=[r for r in invalid['unresolved'] if r['id']!='third']
        next(r for r in invalid['inventory'] if r['id']=='third')['status']='render_pending'
        invalid['sha256']=canonical_sha256({k:v for k,v in invalid.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'PROGRESSIVE_PENDING_CHILD_MATERIALIZED'):
            checked_envelope(invalid,plan)

    def test_same_rigid_error_above_robot_is_not_equivalent_to_floor_hazard(self):
        self.assertEqual(issue_impact([.9,1.],hazard='rigid',robot_top_m=.3),'outside_sim_envelope')
        self.assertEqual(issue_impact([0.,.1],hazard='rigid',robot_top_m=.3),'task_blocked')
        for hazard in ('unknown','entanglement'):
            self.assertEqual(issue_impact([.9,1.],hazard=hazard,robot_top_m=.3),'task_blocked')
        self.assertEqual(issue_impact([.9,1.],hazard='rigid'),'task_context_required')
        for bound in ([float('nan'),1.],[-.1,1.],[1.,0.]):
            with self.assertRaises(ValueError):issue_impact(bound,hazard='rigid')

    def test_strict_reproduction_then_partial_keeps_inventory_source_and_reason(self):
        request,obs,draft=fixture();original=deepcopy(draft)
        with self.assertRaises(GeometryValidationError):compile_scene(draft,obs,request)
        payload,trace=compile_scene(draft,obs,request,progressive=True)
        sidecar=checked_envelope(trace['progressive_twin'],payload)
        self.assertEqual(draft,original)
        self.assertEqual({r['id'] for r in sidecar['inventory']},{'support','item_0'})
        self.assertEqual(sidecar['unresolved'][0]['id'],'item_0')
        self.assertEqual(sidecar['unresolved'][0]['source']['basis'],'user')
        self.assertEqual(sidecar['unresolved'][0]['reason'],'SURFACE_CAPACITY_EXCEEDED')
        self.assertFalse(trace['checks_complete']);self.assertTrue(trace['materialized_subset_checked'])
        self.assertEqual([r['id'] for r in trace['model_parameters']],['support'])
        self.assertNotIn('item_0',{c['arguments']['id'] for c in payload['calls']})
        self.assertFalse(sidecar['physical_authority'])

    def test_atomic_project_save_closed_reopen_and_legacy_readers(self):
        request,obs,draft=fixture();payload,trace=compile_scene(draft,obs,request,progressive=True)
        source=record(request,payload,trace)
        self.assertEqual(source.schema_version,'2.2')
        with TemporaryDirectory() as folder:
            store=ProjectStore(Path(folder)/'active_project.json')
            store.save(ProjectRecord('default',source.input_revision,site_draft=source))
            reopened=ProjectStore(store.path).load().site_draft
            self.assertEqual(reopened.to_dict(),source.to_dict())
        legacy=record(request,payload,trace,progressive=False)
        self.assertEqual(legacy.schema_version,'2.1')
        self.assertEqual(SiteDraftRecord.from_dict(legacy.to_dict()),legacy)
        old=SiteDraftRecord.create(request_id='old',provider_name='fixture',model_id='fixture',
            image_count=0,input_revision=source.input_revision,plan=source.plan)
        self.assertEqual(old.schema_version,'2.0')
        self.assertEqual(SiteDraftRecord.from_dict(old.to_dict()),old)

    def test_grounded_photo_partial_visual_and_inferred_sources_survive_save(self):
        from dataclasses import replace
        from twinpulse_provider import ImageInput
        from twinpulse_provider.nebius_pipeline import ObservationArtifact
        from twinpulse_provider.semantic_scene import checked_structure, checked_batch, scene_draft
        request,_,draft=fixture()
        request=replace(request,images=(ImageInput('synthetic.jpg','image/jpeg',b'zero-network-fixture'),))
        observation=ObservationArtifact.from_mapping(dict(schema_version='1.1',summary='Synthetic support',
            entities=[dict(id='seen_'+r['id'],kind='static_obstacle',description=r['kind'],
                confidence=.9,role='object',category=r['kind'],region='unknown',spatial_confidence=.9)
                for r in draft['inventory']],relations=[],dimensions=[],ambiguities=['Unmeasured']))
        for basis in ('visual','inferred'):
            with self.subTest(basis=basis):
                structure={k:deepcopy(draft[k]) for k in ('summary','room','inventory')}
                for row in structure['inventory']:
                    row['source']=dict(basis=basis,observation_ids=['seen_'+row['id']],user_quote=None)
                candidate=checked_batch(draft['objects'],scene_draft(
                    checked_structure(structure,request,observation)),list(draft['objects']))
                payload,trace=compile_scene(candidate,observation,request,progressive=True)
                source=record(request,payload,trace)
                reopened=SiteDraftRecord.from_dict(source.to_dict())
                self.assertEqual(reopened.progressive_twin['unresolved'][0]['source'],
                    dict(basis=basis,observation_ids=['seen_item_0'],user_quote=None))
                self.assertEqual(reopened.progressive_twin['inventory'][1]['parameters']['observation_ids'],
                    ['seen_item_0'])
                self.assertEqual(reopened.plan_sha256,source.plan_sha256)

    def test_corrupt_missing_pending_plan_mismatch_and_false_pass_are_rejected(self):
        request,obs,draft=fixture();payload,trace=compile_scene(draft,obs,request,progressive=True)
        source=record(request,payload,trace)
        for mutate in (lambda s:s['unresolved'].clear(),lambda s:s['inventory'].pop(),
                       lambda s:s['axes'].update(sim_task_pass='passed'),lambda s:s.update(physical_authority=True),
                       lambda s:s['unresolved'][0].update(bounds_z_m=[2,2.1]),
                       lambda s:s['unresolved'][0].update(hazard='unknown'),
                       lambda s:s['inventory'][1]['parameters'].update(dimensions_m=[.9,.6,0]),
                       lambda s:s['unresolved'][0]['source'].update(basis='unverified-authority'),
                       lambda s:s['unresolved'][0]['source'].update(basis='observed'),
                       lambda s:s['unresolved'][0].update(part='nonexistent')):
            bad=source.to_dict();mutate(bad['progressive_twin'])
            bad['progressive_twin']['sha256']=canonical_sha256({k:v for k,v in bad['progressive_twin'].items() if k!='sha256'})
            with self.assertRaises(ValueError):SiteDraftRecord.from_dict(bad)
        bad=source.to_dict();bad['progressive_twin']['inventory'][1]['parameters']['dimensions_m'][2]=float('nan')
        with self.assertRaises(ValueError):SiteDraftRecord.from_dict(bad)
        changed=deepcopy(payload);changed['summary']+=' edited'
        with self.assertRaises(ValueError):checked_envelope(trace['progressive_twin'],changed)

    def test_task_context_physical_block_and_edit_staleness_survive_reload(self):
        request,obs,draft=fixture();payload,trace=compile_scene(draft,obs,request,progressive=True)
        value=trace['progressive_twin']
        with self.assertRaisesRegex(ValueError,'PROGRESSIVE_TASK_UNRESOLVED'):require_task_context(value)
        require_task_context(value,robot_top_m=.3)
        with self.assertRaises(ValueError):require_task_context(value,robot_top_m=1.)
        with self.assertRaises(ValueError):require_task_context(value,robot_top_m=.3,physical=True)
        self.assertTrue(summary(value,current_plan_sha256=canonical_sha256(payload))['current'])
        self.assertFalse(summary(value,current_plan_sha256='changed')['current'])

    def test_missing_parent_and_floor_overflow_remain_hard_errors(self):
        request,obs,draft=fixture()
        draft['objects']['item_0']['placement']['parent_id']='missing'
        with self.assertRaises(ValueError):compile_scene(draft,obs,request,progressive=True)
        request,obs,draft=fixture();draft['room'].update(width_m=2,length_m=2)
        draft['objects']['support']['dimensions_m']=[5,5,.9]
        with self.assertRaises(ValueError):compile_scene(draft,obs,request,progressive=True)

    def test_native_surface_hazards_are_draft_only_pending_not_driveable_omissions(self):
        for kind in ('unknown','cable_bundle','small_equipment'):
            request,obs,draft=fixture()
            draft['inventory'][1]['kind']=kind
            draft['objects']['item_0']['model_id']='common.'+kind
            original=deepcopy(draft)
            with self.subTest(kind=kind):
                with self.assertRaises(GeometryValidationError):compile_scene(draft,obs,request)
                payload,trace=compile_scene(draft,obs,request,progressive=True)
                issue=checked_envelope(trace['progressive_twin'],payload)['unresolved'][0]
                self.assertEqual(issue['hazard'],kind if kind=='unknown' else 'entanglement' if kind=='cable_bundle' else 'rigid')
                if kind in ('unknown','cable_bundle'):
                    self.assertEqual(issue['bounds_z_m'][0],0.)
                    with self.assertRaises(ValueError):require_task_context(trace['progressive_twin'],robot_top_m=.3)
                with self.assertRaises(ValueError):require_task_context(trace['progressive_twin'],physical=True)
            self.assertEqual(draft,original)
        request,obs,draft=fixture()
        draft['objects']['support']['dimensions_m'][2]=.3
        payload,trace=compile_scene(draft,obs,request,progressive=True)
        with self.assertRaises(ValueError):require_task_context(trace['progressive_twin'],robot_top_m=.3)

    def test_native_bedding_preserves_surface_and_floor_keepout_union_closed_restore(self):
        request,obs,draft=native_child_fixture();original=deepcopy(draft)
        payload,trace=compile_scene(draft,obs,request,progressive=True)
        pending=trace['progressive_twin']['unresolved'][0]
        self.assertEqual(pending['hazard'],'entanglement');self.assertEqual(pending['bounds_z_m'][0],0.)
        self.assertGreaterEqual(pending['bounds_z_m'][1],.35)
        self.assertEqual(draft,original)
        self.assertEqual(pending['evidence']['actual']['child']['placement']['relation'],'surface')
        self.assertTrue(trace['materialized_subset_checked']);self.assertFalse(trace['checks_complete'])
        self.assertEqual(next(r['status'] for r in trace['checks'] if r['check_id']=='support_packing'),'partial')
        self.assertTrue(all(r['status']=='passed' for r in trace['checks'] if r['check_id']!='support_packing'))
        saved=record(request,payload,trace)
        with TemporaryDirectory() as root:
            store=ProjectStore(Path(root)/'project.json');store.save(ProjectRecord('default',saved.input_revision,site_draft=saved))
            restored=ProjectStore(store.path).load().site_draft
            self.assertEqual(restored.to_dict(),saved.to_dict())
        for physical in (False,True):
            with self.assertRaises(ValueError):require_task_context(restored.progressive_twin,robot_top_m=.3,physical=physical)

    def test_pending_risk_forgery_native_floor_and_invalid_part_remain_rejected(self):
        request,obs,draft=native_child_fixture();payload,trace=compile_scene(draft,obs,request,progressive=True)
        for changes in ({'hazard':'rigid'},{'bounds_z_m':[.46,.51]}):
            bad=deepcopy(trace['progressive_twin']);bad['unresolved'][0].update(changes)
            bad['sha256']=canonical_sha256({k:v for k,v in bad.items() if k!='sha256'})
            with self.assertRaises(ValueError):checked_envelope(bad,payload)
        from twinpulse_core.progressive_twin import pending_support_geometry
        parent=next(c['arguments'] for c in payload['calls'] if c['arguments']['id']=='support')
        for relation,kind,part in (('floor','bedding_overhang','mattress'),('surface','bed','mattress'),
                ('surface','office_chair','mattress'),('surface','bedding_overhang','missing')):
            item=deepcopy(trace['progressive_twin']['inventory'][1]['parameters'])
            item['kind']=kind;item['placement']['relation']=relation;item['placement']['part']=part
            with self.assertRaises(ValueError):pending_support_geometry(item,parent,part)
        bad=deepcopy(trace['progressive_twin']);bad['inventory'][1]['parameters']['model_id']='unsupported.bedding_overhang'
        bad['sha256']=canonical_sha256({k:v for k,v in bad.items() if k!='sha256'})
        with self.assertRaises(ValueError):checked_envelope(bad,payload)

    def test_materialized_render_review_cannot_accept_pending_or_claim_full_coverage(self):
        from dataclasses import replace
        import test_render_review_loop as render_fixtures
        from twinpulse_provider import ImageInput
        from twinpulse_provider.render_review import body,checked
        from twinpulse_provider.semantic_scene import revision,review_candidate_quality
        from twinpulse_provider.scene_contract import SceneContractError
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        request,obs,draft=fixture()
        request=replace(request,images=(ImageInput('fixture.png','image/png',b'fixture-not-a-photo'),))
        payload,trace=compile_scene(draft,obs,request,progressive=True)
        capture=asyncio.run(render_fixtures.CaptureFixture().capture(payload,revision(draft),None,1))
        capture['plan']=payload
        wire=body(request,draft,obs,capture,model='fixture',cap=20000)
        response=render_fixtures.review_response(wire)
        self.assertEqual(set(response['objects']),{'support'})
        content=json.loads(wire['messages'][-1]['content'][0]['text'])
        self.assertEqual(content['deferred_object_ids'],['item_0'])
        reviewed=checked(response,draft,payload,capture,obs_quality:=review_candidate_quality(draft,payload,trace,obs,request))
        self.assertEqual(reviewed['status'],'consistent')
        self.assertEqual(reviewed['review_scope'],'materialized_subset')
        self.assertEqual(reviewed['visual_completeness'],'needs_refinement')
        self.assertFalse(reviewed['physical_authority'])
        response['objects']['item_0']=deepcopy(response['objects']['support'])
        with self.assertRaises(SceneContractError):checked(response,draft,payload,capture,obs_quality)
        public=_public_generation_diagnostics(dict(stage_acceptance={'approximate_draft':'partial'},quality_review=reviewed))
        self.assertEqual(public['stage_acceptance']['approximate_draft'],'partial')
        self.assertEqual(public['quality_review']['review_scope'],'materialized_subset')
        self.assertNotIn('assessments',public['quality_review'])

    def test_ordinary_budgeted_service_returns_partial_without_extra_repair_calls(self):
        request,obs,draft=fixture()
        structure={k:deepcopy(draft[k]) for k in ('summary','room','inventory')}
        structure['inventory']=[dict(id=r['id'],kind=r['kind'],evidence_ref='text:0') for r in draft['inventory']]
        transport=FixtureTransport([structure,draft['objects']])
        provider=generation_fixtures.PipelineTests().provider(transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies),2)
        self.assertEqual(result.provider_provenance['progressive_twin']['unresolved'][0]['id'],'item_0')
        self.assertEqual(result.provider_provenance['budget']['repairs'],0)
        self.assertFalse(result.provider_provenance['checks_complete'])
        self.assertFalse(result.provider_provenance['physical_authority'])
        self.assertEqual(provider.diagnostic_for(request.request_id)['stage_acceptance']['approximate_draft'],'partial')

    def test_actual_app_api_generation_reload_and_task_gate_keep_pending(self):
        import sys
        import time
        sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
        from tests.integration.test_chat_conversation import ChatConversationTests
        from twinpulse_app.conversation_service import ConversationService
        case=ChatConversationTests('test_photo_generation_does_not_inject_fixed_room_inventory')
        case.setUp()
        try:
            request,obs,draft=fixture()
            structure={k:deepcopy(draft[k]) for k in ('summary','room','inventory')}
            structure['inventory']=[dict(id=r['id'],kind=r['kind'],evidence_ref='text:0') for r in draft['inventory']]
            transport=FixtureTransport([structure,draft['objects']])
            service=GenerationService(generation_fixtures.PipelineTests().provider(transport),config(timeout_s=300),plan_version='2.2')
            case.workflow._application.set_generation_gateway(service)
            first=case.send();case.call(case.answer(first))
            for _ in range(100):
                state=case.call()
                if state['generation']['state']!='running':break
                time.sleep(.02)
            failure=state['generation'].get('error') or {}
            self.assertEqual(state['generation']['state'],'completed',
                msg={**{key:failure.get(key) for key in ('code','message')},
                    'fixture_stages':[body['response_format']['json_schema']['name'] for body in transport.bodies]})
            self.assertEqual(len(transport.bodies),3)  # Early room seed is separately accounted.
            saved=case.workflow.snapshot()['site_draft']['progressive_twin']
            self.assertEqual(saved['inventory_count'],2)
            self.assertEqual(saved['materialized_count'],1)
            self.assertEqual(saved['unresolved'][0]['id'],'item_0')
            self.assertIsNone(state['simulation_review'])
            self.assertEqual(state['messages'][-1]['status'],'completed')
            self.assertIn('need support-placement refinement',state['messages'][-1]['content'])
            self.assertIn('draft_refinement_pending',[e['type'] for e in state['events']])
            restored=ConversationService(case.workflow,case.server.conversation.path).snapshot()
            self.assertIsNone(restored['restore_error'])
            reopened=ProjectStore(case.workflow._application._project_store.path).load().site_draft
            self.assertEqual(reopened.progressive_twin['unresolved'][0]['id'],'item_0')
            with self.assertRaisesRegex(Exception,'PROGRESSIVE_TASK_UNRESOLVED'):
                case.workflow.simulation_preview()
            self.assertEqual(case.broker.public_state('unowned')['operations'],[])
        finally:case.tearDown()
