# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit offline fixtures, not fresh model or physical acceptance."""
import asyncio
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import sys
from unittest.mock import patch as mock_patch
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
import test_budgeted_generation as generation_fixtures
from test_budgeted_generation import FixtureTransport,config
from test_scope_quality_loop import photo_case,patch
from twinpulse_provider import GenerationService,InvalidProviderResponseError
from twinpulse_provider.generation_policy import GenerationBudgetError
from twinpulse_core import InputRevision,SiteToolPlan,canonical_sha256,InputArtifactStore
from twinpulse_core.draft_refinement import checked_refinement
from twinpulse_core.photo_placement import placement_contract_from_trace
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.project_store import ProjectRecord,ProjectStore
from twinpulse_app.scene_changes import SceneChangeHistory


def result_case(*,store_root=None,transport_type=FixtureTransport):
    request,observation,structure,objects,candidate=photo_case()
    changed=dict(objects['bed'],dimensions_m=[1.3,2,.9])
    from twinpulse_provider.semantic_scene import patch_candidate
    middle=patch_candidate(candidate,patch(candidate,[dict(op='update',id='bed',value=changed)]),observation,request)
    changed2=dict(changed,dimensions_m=[1.2,2,.9])
    transport=transport_type([observation.to_dict(),structure,objects,
        patch(candidate,[dict(op='update',id='bed',value=changed)]),
        patch(middle,[dict(op='update',id='bed',value=changed2)])])
    provider=generation_fixtures.PipelineTests.provider(None,transport,store_root=store_root)
    result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
    return request,result,provider,transport


def record_for(request,result):
    # The actual InputArtifactStore path is covered by Application integration;
    # this explicit synthetic InputRevision retains a typed image digest.
    input_revision=InputRevision.create(input_kind='photo',prompt=request.prompt,
        images=[('fixture.jpg','image/jpeg',synthetic_image())],measurement_constraints=[],
        profile_id='fixture',generation_settings={'provider_profile':'fixture','model_id':'scripted'})
    return SiteDraftRecord.create(request_id=result.request_id,provider_name=result.provider_name,
        model_id=result.model_id,image_count=1,input_revision=input_revision,plan=result.plan,
        placement_contract=placement_contract_from_trace(result.provider_provenance),
        progressive_twin=result.provider_provenance['progressive_twin'],
        draft_refinement=result.provider_provenance['draft_refinement'])


def synthetic_image():
    from PIL import Image
    output=BytesIO();Image.new('RGB',(8,8),'gray').save(output,format='JPEG')
    return output.getvalue() # Explicit offline image, never real photo evidence.


def subset_result_case():
    from twinpulse_provider.nebius_pipeline import ObservationArtifact
    from twinpulse_provider.semantic_scene import checked_structure,scene_draft,checked_batch,patch_candidate
    request,observation,structure,objects,_=photo_case()
    observed=observation.to_dict()
    observed['entities'].append(dict(id='seen_bedding',kind='static_obstacle',description='Synthetic native supported cloth',
        confidence=.9,role='object',category='bedding_overhang',region='unknown',spatial_confidence=.9,instance_count=1,
        footprint_alignment=__import__('twinpulse_provider.observation_alignment',fromlist=['unknown_alignment']).unknown_alignment()))
    observation=ObservationArtifact.from_mapping(observed)
    structure['inventory'].append(dict(id='bedding',kind='bedding_overhang',evidence_ref='seen:seen_bedding'))
    objects['bedding']=dict(region='rear_right',yaw_deg=0,model_id='home.bedding_overhang',dimensions_m=[1.4,2,.05],
        variant='standard',finish='catalog_default',placement=dict(relation='surface',parent_id='bed',part='mattress',anchor='centre',elevation_m=None))
    candidate=checked_batch(objects,scene_draft(checked_structure(structure,request,observation,bound=True)),list(objects))
    responses=[observation.to_dict(),structure,objects]
    for width in (1.3,1.2):
        operation=patch(candidate,[dict(op='update',id='bed',value=dict(candidate['objects']['bed'],dimensions_m=[width,2,.9]))])
        responses.append(operation);candidate=patch_candidate(candidate,operation,observation,request)
    transport=FixtureTransport(responses);provider=generation_fixtures.PipelineTests.provider(None,transport)
    result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
    return request,result,provider,transport


class ValidRefinementDraftTests(unittest.TestCase):
    def test_pending_native_hazard_and_quality_terminal_return_only_checked_latest_subset(self):
        request,result,provider,transport=subset_result_case();value=result.provider_provenance['draft_refinement']
        progressive=result.provider_provenance['progressive_twin']
        self.assertEqual(value['schema_version'],'draft-refinement-1.1')
        self.assertEqual(value['acceptance'],'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE')
        self.assertEqual(value['progressive_sha256'],progressive['sha256'])
        self.assertEqual(value['quality_review']['status'],'needs_revision')
        self.assertFalse(value['geometry_checks']['checks_complete']);self.assertTrue(value['geometry_checks']['materialized_subset_checked'])
        self.assertFalse(value['geometry_checks']['inventory_complete']);self.assertEqual(len(transport.bodies),5)
        self.assertEqual(progressive['unresolved'][0]['hazard'],'entanglement')
        self.assertEqual(progressive['unresolved'][0]['bounds_z_m'][0],0.)
        self.assertNotIn('bedding',{c.arguments['id'] for c in result.plan.calls})
        self.assertEqual(next(c.arguments['dimensions_m'][0] for c in result.plan.calls if c.arguments['id']=='bed'),1.2)
        self.assertEqual(provider.diagnostic_for(request.request_id)['stage_acceptance']['approximate_draft'],'partial')
        source=record_for(request,result)
        with TemporaryDirectory() as root:
            store=ProjectStore(Path(root)/'project.json');store.save(ProjectRecord('default',source.input_revision,site_draft=source))
            restored=ProjectStore(store.path).load().site_draft
            self.assertEqual(restored.to_dict(),source.to_dict())
        from twinpulse_core.progressive_twin import require_task_context
        from twinpulse_app.dependency_patch import initial_state,public_progressive
        current=initial_state(restored).progressive(restored)
        self.assertEqual(current['unresolved'][0]['hazard'],'entanglement');self.assertEqual(current['unresolved'][0]['bounds_z_m'][0],0.)
        self.assertEqual(public_progressive(restored,initial_state(restored))['unresolved'][0]['hazard'],'entanglement')
        for physical in (False,True):
            with self.assertRaises(ValueError):require_task_context(current,robot_top_m=.3,physical=physical)

    def test_subset_cannot_lose_witness_promote_full_or_hide_failed_phase(self):
        request,result,_,_=subset_result_case();original=result.provider_provenance['draft_refinement'];progressive=result.provider_provenance['progressive_twin']
        with self.assertRaises(ValueError):checked_refinement(original,result.plan.to_dict(),request_id=request.request_id)
        for mutate in (lambda v:v.update(progressive_sha256='a'*64),
                lambda v:v['geometry_checks']['checks'][4].update(status='failed'),
                lambda v:v['geometry_checks'].update(checks_complete=True),
                lambda v:v['geometry_checks'].update(materialized_subset_checked=False),
                lambda v:v.update(schema_version='draft-refinement-1.0',acceptance='GEOMETRY_VALID_REFINEMENT_INCOMPLETE'),
                lambda v:v['budget']['attempts'][-1].update(status='unknown',settled=False)):
            value=deepcopy(original);mutate(value);value['sha256']=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
            with self.subTest(value=value['schema_version']),self.assertRaises(ValueError):
                checked_refinement(value,result.plan.to_dict(),request_id=request.request_id,progressive=progressive)

    def test_subset_current_parent_edit_undo_and_app_task_gates_keep_native_evidence(self):
        sys.path.insert(0,str(ROOT/'packages/twinpulse_robot/src'));sys.path.insert(0,str(ROOT))
        from tests.integration.test_scene_edit_transaction import workflow,attach
        from tests.integration.test_dependency_scene_changes import edit,preview,adopt
        from twinpulse_app.conversation_service import ConversationService
        from twinpulse_app.command_broker import BrokerError
        request,result,_,_=subset_result_case();source=record_for(request,result)
        history=SceneChangeHistory.empty('default',source)
        original=history.effective(source).progressive(source)['unresolved'][0]
        parent=deepcopy(next(c.to_dict() for c in source.plan.calls if c.arguments['id']=='bed'))
        parent['arguments']['dimensions_m'][2]=1.1
        value=preview(history,source,'resize_pending_parent',edit('change','bed',tool_call=parent))
        edited=adopt(history,source,value);current=edited.effective(source).progressive(source)['unresolved'][0]
        self.assertEqual(current['hazard'],original['hazard']);self.assertEqual(current['bounds_z_m'][0],0.)
        from twinpulse_core.progressive_twin import pending_support_geometry
        parameters=deepcopy(source.progressive_twin['inventory'][-1]['parameters'])
        expected=pending_support_geometry(parameters,parent['arguments'],'mattress')[1]
        self.assertEqual(current['bounds_z_m'],expected)
        self.assertEqual(current['source'],original['source']);self.assertEqual(current['evidence'],original['evidence'])
        restored=SceneChangeHistory.from_dict(edited.to_dict(),source,'default')
        undo=restored.preview(source,operation_id='undo_pending_parent',mode='undo')
        from twinpulse_app.scene_changes import SceneChange
        undone=restored.append(source,SceneChange.from_dict(undo['operation']))
        self.assertEqual(undone.effective(source).progressive(source)['unresolved'],history.effective(source).progressive(source)['unresolved'])
        with TemporaryDirectory() as root:
            store=ProjectStore.for_project(Path(root),'default')
            InputArtifactStore(store.input_root()).save(source.input_revision,(('fixture.jpg',synthetic_image()),))
            store.save(ProjectRecord('default',source.input_revision,site_draft=source))
            product=workflow(Path(root));attach(product);summary=product.snapshot()['site_draft']
            self.assertFalse(summary['run_allowed']);self.assertEqual(summary['progressive_twin']['unresolved'][0]['hazard'],'entanglement')
            for operation in (product.simulation_preview,product._assert_room_inventory_complete):
                with self.assertRaises(BrokerError) as caught:operation()
                self.assertEqual(caught.exception.code,'progressive_task_unresolved')
            chat=ConversationService(product,Path(root)/'chat.json');chat._state['mode']='SIM'
            chat._state['generation']=dict(state='running',generation_id=product.snapshot()['generation_id'],operation_id='fixture_generation',request_id='fixture')
            with mock_patch.object(product,'simulation_preview') as automatic:chat._sync_generation();automatic.assert_not_called()
            self.assertIn('pending objects preserved',chat._state['generation']['summary'])
            self.assertIn('Sensor correction and robot operation are not yet verified',chat._state['generation']['summary'])
            self.assertIsNone(chat._state['simulation_review']);self.assertIsNone(product._broker.claim('engine','stage'))
            self.assertTrue(product._application.diagnostics.flush())

    def test_pending_only_state_change_rechecks_quality_and_exact_undo_restores_current(self):
        sys.path.insert(0,str(ROOT));from tests.integration.test_dependency_scene_changes import edit,preview,adopt
        from twinpulse_core.draft_refinement import public_refinement
        from twinpulse_app.scene_changes import SceneChange
        request,result,_,_=subset_result_case();source=record_for(request,result)
        history=SceneChangeHistory.empty('default',source);initial=history.effective(source)
        removed=adopt(history,source,preview(history,source,'remove_pending',edit('remove','bedding')))
        current=removed.effective(source)
        self.assertEqual(current.plan,initial.plan);self.assertNotEqual(current.inventory,initial.inventory)
        self.assertFalse(public_refinement(source.draft_refinement,current.plan.to_dict())['current'])
        same=lambda state:state.inventory==initial.inventory and state.placement==initial.placement
        self.assertFalse(public_refinement(source.draft_refinement,current.plan.to_dict(),pending_context_current=same(current))['current'])
        undo=removed.preview(source,operation_id='undo_pending_only',mode='undo')
        restored=removed.append(source,SceneChange.from_dict(undo['operation'])).effective(source)
        self.assertTrue(public_refinement(source.draft_refinement,restored.plan.to_dict(),pending_context_current=same(restored))['current'])
    def test_incomplete_critic_keeps_actual_preview_receipt_without_marking_quality_or_run_passed(self):
        import test_render_review_loop as render_fixtures
        from twinpulse_provider.semantic_scene import patch_candidate
        request,port,observation,structure,objects,candidate=render_fixtures.case()
        responses=[observation.to_dict(),structure,objects,lambda body:render_fixtures.review_response(body,contradiction=True)]
        for width in (1.3,1.2):
            operation=patch(candidate,[dict(op='update',id='bed',value=dict(candidate['objects']['bed'],dimensions_m=[width,2,.9]))])
            responses.extend([operation,lambda body:render_fixtures.review_response(body,contradiction=True)])
            candidate=patch_candidate(candidate,operation,observation,request)
        transport=render_fixtures.DynamicFixtureTransport(responses);provider=render_fixtures.provider(transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        value=result.provider_provenance['draft_refinement'];stages=provider.diagnostic_for(request.request_id)['stage_acceptance']
        self.assertEqual(value['quality_review']['schema_version'],render_fixtures.RENDER_REVIEW_REVISION)
        self.assertEqual(value['quality_review']['status'],'needs_revision');self.assertEqual(value['stop_reason'],'REPAIR_STALLED')
        self.assertEqual(stages['Isaac_Build'],'preview_passed')
        self.assertEqual(stages['photo_quality'],'needs_revision');self.assertEqual(stages['SIM_Run_Stop'],'not_run')
        self.assertEqual(value['quality_review']['capture'],port.captures[-1]['metadata'])
        self.assertEqual(len(port.captures),3);self.assertEqual(len(transport.bodies),8)

    def test_three_actual_quality_improvements_stop_at_limit_without_photo_pass(self):
        from twinpulse_provider.semantic_scene import patch_candidate
        request,observation,structure,objects,candidate=photo_case()
        responses=[observation.to_dict(),structure,objects]
        for width in (5.8,5.6,5.4):
            operation=patch(candidate,[dict(op='room',value=dict(candidate['room'],width_m=width))])
            responses.append(operation);candidate=patch_candidate(candidate,operation,observation,request)
        transport=FixtureTransport(responses);provider=generation_fixtures.PipelineTests.provider(None,transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        value=result.provider_provenance['draft_refinement']
        self.assertEqual(value['stop_reason'],'QUALITY_REPAIR_LIMIT_REACHED')
        self.assertEqual(value['budget']['repairs'],3);self.assertEqual(value['budget']['stalled_repairs'],0)
        self.assertEqual(value['quality_review']['status'],'needs_revision');self.assertEqual(len(transport.bodies),6)
        self.assertEqual(next(c.arguments for c in result.plan.calls if c.tool=='create_floor')['size_m'][0],5.4)

    def test_quality_stalled_preserves_latest_valid_geometry_and_failure_budget(self):
        request,result,provider,transport=result_case()
        value=result.provider_provenance['draft_refinement']
        self.assertEqual(value['acceptance'],'GEOMETRY_VALID_REFINEMENT_INCOMPLETE')
        self.assertEqual(value['stop_reason'],'REPAIR_STALLED')
        self.assertEqual(value['quality_review']['status'],'needs_revision')
        self.assertTrue(value['quality_review']['issues'])
        self.assertTrue(all(r['status']=='passed' for r in value['geometry_checks']['checks']))
        self.assertEqual(value['plan_sha256'],canonical_sha256(result.plan.to_dict()))
        self.assertEqual(value['budget']['repairs'],2);self.assertEqual(len(transport.bodies),5)
        self.assertEqual(provider.diagnostic_for(request.request_id)['stage_acceptance']['approximate_draft'],'partial')
        self.assertEqual(provider.diagnostic_for(request.request_id)['stage_acceptance']['photo_quality'],'needs_revision')
        bed=next(c.arguments for c in result.plan.calls if c.arguments['id']=='bed')
        self.assertEqual(bed['dimensions_m'],[1.2,2,.9]) # not stale best's 1.4 m.
        self.assertFalse(value['physical_authority'])

    def test_durable_record_closed_project_and_history_state_preserve_exact_issues(self):
        request,result,_,_=result_case();record=record_for(request,result)
        self.assertEqual(record.schema_version,'2.3')
        with TemporaryDirectory() as root:
            store=ProjectStore(Path(root)/'active_project.json');store.save(ProjectRecord('default',record.input_revision,site_draft=record))
            restored=ProjectStore(Path(root)/'active_project.json').load().site_draft
            self.assertEqual(restored.draft_refinement,record.draft_refinement)
            history=SceneChangeHistory.empty('default',record);closed=SceneChangeHistory.from_dict(history.to_dict(),restored,'default')
            self.assertEqual(history.state_sha256(history.effective(record)),closed.state_sha256(closed.effective(restored)))
            self.assertEqual(closed.effective(restored).refinement,record.draft_refinement)

    def test_stale_plan_quality_candidate_checks_and_unknown_receipt_fail_closed(self):
        _,result,_,_=result_case();original=result.provider_provenance['draft_refinement']
        for defect in ('plan','quality_candidate','ledger_candidate','geometry','quality_pass','unknown','geometry_row','issue_id','held','counters'):
            value=deepcopy(original)
            if defect=='plan':value['plan_sha256']='a'*64
            elif defect=='quality_candidate':value['quality_review']['candidate_revision']='a'*64
            elif defect=='ledger_candidate':value['geometry_checks']['checks'][0]['candidate_revision']='a'*64
            elif defect=='geometry':value['geometry_checks']['checks'][2]['status']='failed'
            elif defect=='quality_pass':value['quality_review']['status']='consistent'
            elif defect=='unknown':value['budget']['attempts'][-1]['status']='outcome_unknown'
            elif defect=='geometry_row':value['geometry_checks']['checks'][0]=None
            elif defect=='issue_id':value['quality_review']['issues'][0]['target_ids']=[{}]
            elif defect=='held':value['budget'].update(financial_scope='bound',cost={'reserved_unknown_usd':'0.01'})
            else:value['budget']['requests']=0
            value['sha256']=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                checked_refinement(value,result.plan.to_dict(),request_id=result.request_id)

    def test_usage_only_product_scope_retains_unfinished_quality_and_receipt_guard(self):
        _,result,_,_=result_case();value=deepcopy(result.provider_provenance['draft_refinement'])
        value['budget']['financial_scope']='usage_only'
        value['sha256']=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
        checked=checked_refinement(value,result.plan.to_dict(),request_id=result.request_id)
        self.assertEqual(checked['quality_review']['status'],'needs_revision')
        self.assertFalse(checked['physical_authority'])
        value['budget']['attempts'][-1]['status']='outcome_unknown'
        value['sha256']=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'DRAFT_REFINEMENT_OUTCOME_UNKNOWN'):
            checked_refinement(value,result.plan.to_dict(),request_id=result.request_id)

    def test_legacy_saved_record_remains_unmodified_and_cannot_sneak_new_metadata(self):
        request,result,_,_=result_case();record=record_for(request,result)
        legacy=record.to_dict();legacy.pop('draft_refinement');legacy['schema_version']='2.2'
        restored=SiteDraftRecord.from_dict(legacy)
        self.assertIsNone(restored.draft_refinement);self.assertEqual(restored.to_dict(),legacy)
        legacy['draft_refinement']=record.draft_refinement
        with self.assertRaises(ValueError):SiteDraftRecord.from_dict(legacy)

    def test_configured_limits_and_stalled_threshold_match_shared_policy(self):
        _,result,_,_=result_case();original=result.provider_provenance['draft_refinement']
        def checked(value):
            value['sha256']=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
            return checked_refinement(value,result.plan.to_dict(),request_id=result.request_id)
        for ceiling in (24,32):
            value=deepcopy(original);value['budget']['max_requests']=ceiling
            self.assertEqual(checked(value)['quality_review']['status'],'needs_revision')
        for key,invalid in (('max_requests',33),('max_repairs',9),('stalled_repair_limit',5)):
            value=deepcopy(original);value['budget'][key]=invalid
            with self.subTest(key=key),self.assertRaises(ValueError):checked(value)
        value=deepcopy(original);value['budget'].update(stalled_repair_limit=1,stalled_repairs=1)
        self.assertFalse(checked(value)['physical_authority'])
        value['budget'].pop('stalled_repair_limit')
        with self.assertRaises(ValueError):checked(value) # legacy threshold remains2.
        value=deepcopy(original);budget=value['budget'];budget.update(max_repairs=8,stalled_repair_limit=4,stalled_repairs=4,repairs=4)
        for i in range(2):
            row=deepcopy(next(r for r in budget['attempts'] if r['role']=='repair'));row['attempt_id']='extra_'+str(i)
            budget['attempts'].append(row)
        budget['requests']=len(budget['attempts']);budget['cumulative_requests']=budget['requests']
        checked(value)

    def test_continuation_counters_preserve_local_requests_and_cumulative_repairs(self):
        _,result,_,_=result_case();original=result.provider_provenance['draft_refinement']
        value=deepcopy(original);budget=value['budget']
        budget.update(max_requests=24,max_repairs=8,prior_executions=[{'requests':4,'repairs':1},{'requests':2,'repairs':2}],
            carried_requests=6,carried_repairs=2,repairs=4,cumulative_requests=6+budget['requests'])
        def checked(candidate):
            candidate['sha256']=canonical_sha256({k:v for k,v in candidate.items() if k!='sha256'})
            return checked_refinement(candidate,result.plan.to_dict(),request_id=result.request_id)
        self.assertEqual(checked(value)['budget']['repairs'],4) # not1+2+2.
        for key,invalid in (('carried_repairs',3),('carried_requests',7),('cumulative_requests',99)):
            bad=deepcopy(value);bad['budget'][key]=invalid
            with self.subTest(key=key),self.assertRaises(ValueError):checked(bad)
        budget.update(requests=0,attempts=[],repairs=2,cumulative_requests=6)
        checked(value) # known carried work can be revalidated without a new HTTP.
        bad=deepcopy(value);bad['budget'].update(prior_executions=[],carried_requests=0,carried_repairs=0,cumulative_requests=0)
        with self.assertRaises(ValueError):checked(bad)
        bad=deepcopy(value);bad['budget']['prior_executions'][0]['stop_reason']='REMOTE_OUTCOME_UNKNOWN'
        with self.assertRaises(ValueError):checked(bad)

    def test_refinement_evidence_storage_failure_never_returns_draft(self):
        class FailedEvidence(FixtureTransport):
            def record_validation(self,name,identity,record):
                if name=='draft_refinement':raise OSError('explicit fixture evidence failure')
        with self.assertRaisesRegex(Exception,'Validation evidence could not be persisted'):
            result_case(transport_type=FailedEvidence)

    def test_derived_public_view_keeps_original_quality_but_never_claims_current_assessment(self):
        from twinpulse_core.draft_refinement import public_refinement
        from types import SimpleNamespace
        from unittest.mock import PropertyMock
        from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow
        request,result,_,_=result_case();record=record_for(request,result)
        value=public_refinement(record.draft_refinement,None)
        self.assertFalse(value['current']);self.assertEqual(value['assessment_state'],'recheck_required')
        self.assertEqual(value['quality_review'],record.draft_refinement['quality_review'])
        with TemporaryDirectory() as folder:
            store=ProjectStore(Path(folder)/'project.json');store.save(ProjectRecord('default',record.input_revision,site_draft=record))
            app=ApplicationService(SimpleNamespace(),project_store=store)
            product=ProductWorkflow(app,CommandBroker(),mode='explicit_fixture',generation_settings_getter=lambda:{})
            # Presentation-only branch fixture; no sensor fit/derived authority,
            # Build, adoption or mutation is injected or asserted here.
            product._derived_revision='derived_fixture'
            with mock_patch.object(ApplicationService,'derived_review',new_callable=PropertyMock,
                    return_value=SimpleNamespace(site=record.site,revision='derived_fixture',
                        to_dict=lambda:dict(site=record.site.to_dict(),revision='derived_fixture'))):
                summary=product._site_draft_summary(record)
            self.assertEqual(summary['draft_refinement'],value)
            self.assertIsNone(summary['scene_state_sha256'])
            self.assertFalse(summary['run_allowed']);self.assertTrue(app.diagnostics.flush())

    def test_application_generation_archives_typed_refinement_and_closed_input_without_commands(self):
        from twinpulse_app import ApplicationService
        from twinpulse_provider.semantic_scene import patch_candidate
        request,observation,structure,objects,candidate=photo_case()
        changed=dict(objects['bed'],dimensions_m=[1.3,2,.9])
        middle=patch_candidate(candidate,patch(candidate,[dict(op='update',id='bed',value=changed)]),observation,request)
        transport=FixtureTransport([observation.to_dict(),structure,objects,
            patch(candidate,[dict(op='update',id='bed',value=changed)]),
            patch(middle,[dict(op='update',id='bed',value=dict(changed,dimensions_m=[1.2,2,.9]))])])
        gateway=GenerationService(generation_fixtures.PipelineTests.provider(None,transport),config(timeout_s=300),plan_version='2.2')
        with TemporaryDirectory() as root:
            store=ProjectStore.for_project(Path(root),'default');app=ApplicationService(gateway,project_store=store)
            prepared=app.prepare_input(prompt=request.prompt,images=request.images,measurement_constraints=[],
                generation_settings={'provider_profile':'fixture','model_id':'scripted'})
            app.select_input(prepared);outcome=asyncio.run(app.generate())
            self.assertTrue(outcome.persisted);self.assertEqual(outcome.record.schema_version,'2.3')
            closed=ApplicationService(gateway,project_store=ProjectStore(store.path))
            self.assertEqual(closed.site_draft.draft_refinement,outcome.record.draft_refinement)
            self.assertEqual(closed.restored_saved_input().revision,prepared.revision)
            self.assertTrue(app.diagnostics.flush());self.assertTrue(closed.diagnostics.flush())

    def test_current_summary_edit_undo_and_closed_restore_keep_quality_ledger_without_auto_sim(self):
        sys.path.insert(0,str(ROOT/'packages/twinpulse_robot/src'));sys.path.insert(0,str(ROOT))
        from tests.integration.test_scene_edit_transaction import workflow,attach,claim,acknowledge
        from tests.integration.test_dependency_scene_changes import edit,preview
        from twinpulse_app.conversation_service import ConversationService
        from twinpulse_app.command_broker import BrokerError
        request,result,_,_=result_case();record=record_for(request,result)
        with TemporaryDirectory() as root:
            store=ProjectStore.for_project(Path(root),'default')
            InputArtifactStore(store.input_root()).save(record.input_revision,(('fixture.jpg',synthetic_image()),))
            store.save(ProjectRecord('default',record.input_revision,site_draft=record))
            product=workflow(Path(root));attach(product);initial=product.snapshot()['site_draft']
            self.assertTrue(initial['draft_refinement']['current'])
            self.assertEqual(initial['draft_refinement']['quality_review'],record.draft_refinement['quality_review'])
            self.assertIsNone(product._broker.claim('engine','stage'))
            with self.assertRaisesRegex(BrokerError,'Photo refinement remains incomplete'):product.inspection_room(Path(root),'default')
            chat=ConversationService(product,Path(root)/'chat.json');chat._state['mode']='SIM'
            chat._state['generation']=dict(state='running',generation_id=product.snapshot()['generation_id'],
                operation_id='explicit_fixture_generation',request_id='fixture_generation')
            with mock_patch.object(product,'simulation_preview') as automatic:
                chat._sync_generation();automatic.assert_not_called()
            self.assertIsNone(chat._state['simulation_review'])
            self.assertEqual(chat._state['generation']['state'],'completed')
            self.assertTrue(any(e['type']=='draft_visual_refinement_pending' for e in chat._state['events']))
            # An explicit user SIM request still runs the real local planner's
            # current geometry/asset checks, not a photo-quality blanket gate.
            review=product.simulation_preview()
            self.assertEqual(review['scene_revision'],initial['revision'])
            self.assertIsNone(product._broker.claim('engine','stage'))
            changes=product._application.scene_change_store();before=changes.load().state_sha256(changes.load().effective(record))
            bed=deepcopy(next(c.to_dict() for c in record.plan.calls if c.arguments['id']=='bed'))
            bed['arguments']['dimensions_m'][0]*=.98
            value=preview(changes.load(),record,'manual_current_edit',edit('change','bed',tool_call=bed))
            transaction=product.scene_edit_transaction;transaction.start('owner',value['operation'],value['preview_digest'])
            command=claim(product._broker);acknowledge(product._broker,command);transaction.worker.join(3)
            edited=product.snapshot()['site_draft']['draft_refinement'];self.assertFalse(edited['current'])
            self.assertEqual(edited['assessment_state'],'recheck_required')
            self.assertEqual(edited['quality_review'],record.draft_refinement['quality_review'])
            self.assertNotEqual(changes.load().state_sha256(changes.load().effective(record)),before)
            undo=changes.load().preview(record,operation_id='undo_refinement_edit',mode='undo')
            transaction.start('owner',undo['operation'],undo['preview_digest']);command=claim(product._broker)
            acknowledge(product._broker,command);transaction.worker.join(3)
            self.assertTrue(product.snapshot()['site_draft']['draft_refinement']['current'])
            closed=workflow(Path(root),product._broker)
            self.assertEqual(closed.snapshot()['site_draft']['draft_refinement'],initial['draft_refinement'])
            self.assertIsNone(product._broker.claim('engine','stage'))
            self.assertTrue(product._application.diagnostics.flush());self.assertTrue(closed._application.diagnostics.flush())


if __name__=='__main__':unittest.main()
