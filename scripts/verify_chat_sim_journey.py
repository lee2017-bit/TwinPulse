# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fresh chat input/choice/generation → actual owned Isaac SIM acceptance.

Default provider responses are explicit v2 fixtures. --live-campaign instead
uses the existing credential and an approved shared inference ledger. Neither
mode connects to a robot or executes generated programs.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT/'packages'/name/'src'))


def copy_ordinary_settings(settings_path, target):
    """Copy the reviewed settings closure, including a SHA-bound catalog.

    Only registry metadata is copied; credentials remain in the OS store.
    A missing or changed bound catalog fails before backend/model dispatch.
    """
    import shutil
    from twinpulse_provider.model_contracts import load_catalog
    directory=Path(settings_path).parent
    target=Path(target)
    route_path=directory/'provider_stage_routing.json'
    route=json.loads(route_path.read_text(encoding='utf-8')).get('route') if route_path.is_file() else None
    catalog_sha=route.get('model_catalog_sha256') if isinstance(route,dict) else None
    names=['provider_settings.json','provider_keys.json','provider_stage_routing.json']
    if catalog_sha is not None:
        load_catalog(directory/'stage_model_catalog.json',catalog_sha)
        names.append('stage_model_catalog.json')
    target.mkdir(parents=True,exist_ok=True)
    for name in names:
        source=directory/name
        if source.is_file():
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            shutil.copyfile(source,target/name)
            if (hashlib.sha256(source.read_bytes()).hexdigest()!=before
                    or hashlib.sha256((target/name).read_bytes()).hexdigest()!=before):
                raise ValueError('ORDINARY_SETTINGS_COPY_CHANGED')
    if catalog_sha is not None:
        load_catalog(target/'stage_model_catalog.json',catalog_sha)


def audit_render_review_reopen(output):
    """Read-only post-shutdown load; never revive an approval or dispatch."""
    from twinpulse_app.project_store import ProjectStore
    from twinpulse_provider.generation_store import GenerationStore
    from twinpulse_core.photo_placement import validate_placement_plan
    output=Path(output)
    state_files=list((output/'runtime'/'launches').glob('*/supervisor-status.json'))
    if len(state_files)!=1:raise ValueError('Expected one isolated launch')
    supervisor=json.loads(state_files[0].read_text(encoding='utf-8'))
    if supervisor['status']!='stopped' or any(supervisor[key]['owned'] for key in ('backend','engine')):
        raise ValueError('Post-shutdown audit requires owned processes stopped')
    project=ProjectStore(output/'runtime'/'active_project.json')
    before=project.path.read_bytes();saved=project.load().site_draft
    store=GenerationStore(output/'runtime'/'provider-evidence'/'generation-store')
    checkpoints=[store.read('checkpoint',path.stem) for path in (store.root/'checkpoint').glob('*.json')]
    current=[row for row in checkpoints if row['state']=='APPROXIMATE_TWIN_READY']
    if len(current)!=1:raise ValueError('Expected one ready generation')
    checkpoint=current[0]
    history=checkpoint.get('render_history',[])
    text_only=saved.input_revision.to_dict()['input_kind']=='text'
    if not history and not text_only:
        raise ValueError('Photo generation requires its reviewed current render')
    review=history[-1] if history else None
    if (checkpoint['plan_sha256']!=saved.plan_sha256
            or review and (review['plan_sha256']!=saved.plan_sha256
                or review['capture']['scene_revision']!=saved.site.scene.revision)
            or project.path.read_bytes()!=before):
        raise ValueError('Reopened project changed or does not match reviewed render')
    validate_placement_plan(saved.plan,saved.placement_contract)
    return dict(status='PASS',schema_version=saved.schema_version,plan_sha256=saved.plan_sha256,
        scene_revision=saved.site.scene.revision,input_revision=saved.input_revision.digest,
        relations=len(saved.placement_contract['relations']) if saved.placement_contract else 0,
        source_unchanged=True,automatic_dispatch=False,physical_authority=False,
        input_kind='text' if text_only else 'photo',
        render_review='CURRENT_RENDER_REVIEWED' if review else 'NOT_APPLICABLE_TEXT')


def fixture_backend():
    # An isolated test entrypoint; the production launcher's default/live
    # provider and serialization are not changed or silently substituted.
    if '--fixture-mode' not in sys.argv:
        raise SystemExit('Explicit --fixture-mode is required')
    sys.argv.remove('--backend-child')
    if os.environ.get('TWINPULSE_JOURNEY_DIAGNOSTICS')=='1':
        sys.argv.append('--profile-generation')
    from scripts import twinpulse_backend as backend
    if os.environ.get('TWINPULSE_ORDINARY_APPROVAL_FIXTURE') == '1':
        from scripts.fixture_ordinary_generation import install
        install(backend)
        backend.main()
        return
    from twinpulse_provider import GenerationService
    from twinpulse_provider.contracts import ProviderResponse
    accepted = os.environ.get('TWINPULSE_ACCEPTED_GEOMETRY_REPAIR')
    if accepted:
        from scripts.verify_semantic_scoped_live_recovery import audited_geometry
        from twinpulse_provider.generation_store import input_digest
        from packages.twinpulse_provider.tests.test_nebius_pipeline import config
        data,payload,unused,saved,audit=audited_geometry(Path(accepted))
        class AcceptedResultReplay:
            async def generate(self,request,token,configuration):
                if input_digest(request)!=input_digest(data['request']):
                    raise ValueError('Accepted result replay requires the exact original input')
                if token.diagnostics:
                    token.diagnostics.bind(evidence_id=saved['execution_id'],
                        plan_sha256=saved['compiled_plan_sha256'],
                        evidence_kind='audited_real_result_replay',requests=0)
                # Explicit test-only replay of the complete audited real result.
                # No invented response, geometry edit, credential or HTTP.
                return ProviderResponse(request.request_id,payload,'audited_real_geometry_result_replay',
                    audit['rows'][-1]['model_id'],saved['provenance'])
        service=GenerationService(AcceptedResultReplay(),config(timeout_s=90),plan_version='2.2')
        backend.GenerationService=lambda *unused,**kwargs:service
        original_workflow=backend.ProductWorkflow
        def workflow_with_saved_settings(*arguments,**kwargs):
            kwargs['generation_settings_getter']=lambda:dict(data['input_settings'])
            return original_workflow(*arguments,**kwargs)
        backend.ProductWorkflow=workflow_with_saved_settings
        backend.main()
        return
    from tests.integration.test_scene_changes import furnished_source
    from twinpulse_app.manual_room import manual_room_plan
    from tests.integration.test_room_items import clutter_plan
    storage_fault=os.environ.get('TWINPULSE_JOURNEY_STORAGE_FAULT','')
    if storage_fault=='project':
        from twinpulse_app.project_store import ProjectStore
        original_save=ProjectStore.save
        def fail_generated_commit(self,record):
            if record.site_draft is not None:
                raise OSError('TEST_PROJECT_COMMIT_UNAVAILABLE')
            return original_save(self,record)
        ProjectStore.save=fail_generated_commit
    elif storage_fault=='diagnostics':
        from twinpulse_core.execution_diagnostics import ExecutionStore
        original_directory=ExecutionStore._directory
        def fail_optional_manifest(self,identity,*,create=False):
            if create:raise OSError('TEST_OPTIONAL_DIAGNOSTICS_UNAVAILABLE')
            return original_directory(self,identity,create=create)
        ExecutionStore._directory=fail_optional_manifest
    replay_root = os.environ.get('TWINPULSE_EXACT_LIVE_REPLAY')
    if replay_root:
        from scripts.replay_audited_inference import ExactAuditedResponses, live_run_inputs, failed_packing_run_inputs
        from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider
        from packages.twinpulse_provider.tests.test_nebius_pipeline import config
        from twinpulse_app import JsonProviderSettingsStore
        read_inputs=failed_packing_run_inputs if os.environ.get('TWINPULSE_REPLAY_FAILED_PACKING')=='1' else live_run_inputs
        draft, evidence_root, ids = read_inputs(replay_root)
        settings = JsonProviderSettingsStore(Path(replay_root)/'runtime/provider_settings.json').load().validated()
        original_result=json.loads((Path(replay_root)/'result.json').read_text(encoding='utf-8'))
        transport = ExactAuditedResponses(os.environ['TWINPULSE_EXACT_REPLAY_CAMPAIGN'], evidence_root, ids)
        adapter = NebiusChatCompletionsPipelineProvider(transport, observer_model_id=settings.observer_model_id,
            planner_model_id=settings.model_id, site_plan_version='2.2', max_repairs=len(ids)-2, compact_photo_layout=True,
            planner_template_no_thinking=original_result.get('planner_template_policy')=='off',
            output_token_cap=original_result.get('output_token_cap'))
        service = GenerationService(adapter, config(timeout_s=90.), plan_version='2.2')
        backend.GenerationService = lambda *unused, **kwargs: service
        original_workflow = backend.ProductWorkflow
        def workflow_with_original_input_settings(*arguments, **kwargs):
            kwargs['generation_settings_getter'] = lambda: dict(draft.input_revision.generation_settings)
            return original_workflow(*arguments, **kwargs)
        backend.ProductWorkflow = workflow_with_original_input_settings
        backend.main()
        return
    class RoomProvider:
        async def generate(self, request, token, config):
            await asyncio.sleep(.8)
            if token.is_cancelled:
                from twinpulse_provider.errors import GenerationCancelledError
                raise GenerationCancelledError('fixture cancelled')
            plan=(clutter_plan() if os.environ.get('TWINPULSE_CONTRACT_LAYOUT')=='cluttered_room' else manual_room_plan('living_fixture',6.,7.,2.6,[
                {'kind':'sofa','center_m':[-1.4,1.6],'yaw_deg':90},
                {'kind':'dining_table','center_m':[1.4,1.6],'yaw_deg':0},
                {'kind':'storage','center_m':[-1.6,-1.6],'yaw_deg':0}])
                if os.environ.get('TWINPULSE_CONTRACT_LAYOUT')=='living_room' else furnished_source().plan)
            return ProviderResponse(request.request_id, plan.to_dict(),
                                    'Explicit v2 room fixture; no photo inference', config.model_id)
    if os.environ.get('TWINPULSE_SITE_TRANSPORT_FIXTURE')=='1':
        from tests.integration.test_chat_site_text_generation import provider, completion, observation, OBSERVER_MODEL, PLANNER_MODEL, ScriptedTransport, config
        class SiteTransportProvider:
            async def generate(self,request,token,_config):
                if os.environ.get('TWINPULSE_BUDGETED_FIXTURE')=='1':
                    from scripts.fixture_budgeted_generation import RecoveryFixture
                    adapter = RecoveryFixture(request, os.environ['TWINPULSE_BUDGETED_FIXTURE_STORE'],
                                              OBSERVER_MODEL, PLANNER_MODEL)
                    return await adapter.generate(request, token, config(timeout_s=300))
                if os.environ.get('TWINPULSE_COMPACT_PHOTO')=='1':
                    from twinpulse_provider.photo_layout import REVISION
                    from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider
                    from tests.fixtures.historical_room_photo_inventory import photo_reference
                    if len(request.images)!=1:raise ValueError('Compact fixture requires exactly one photo')
                    reference=photo_reference(hashlib.sha256(request.images[0].content).hexdigest())
                    generic=os.environ.get('TWINPULSE_GENERIC_PHOTO')=='1'
                    if generic:reference={'items':[]}
                    if not reference:raise ValueError('Historical compact fixture requires its original source')
                    # Explicit invented regional intent tests wiring, NOT photo recognition or scale.
                    regions=['front_left','middle_right','rear_left','middle_left','front_centre',
                             'front_right','rear_right','middle_centre','rear_centre']
                    intent=dict(layout_version=REVISION,summary='Explicit 8 by 8 regional inventory fixture; not reconstructed.',
                        room=dict(width_m=8,length_m=8,height_m=2.5),objects={item['id']:
                            dict(region=regions[n%9],yaw_deg=0,observation_ids=[])
                            for n,item in enumerate(reference['items'])})
                    for identity,region in {'bed':'middle_right','desk':'rear_left','wardrobe':'rear_right',
                            'floor_bags':'front_left','boxes':'front_left'}.items():
                        if identity in intent['objects']:
                            intent['objects'][identity]['region']=region
                    if os.environ.get('TWINPULSE_PARAMETRIC_PHOTO')=='1':
                        from twinpulse_provider.photo_layout import PARAMETRIC_REVISION,SIZES
                        from twinpulse_core.model_library import library_models,FURNITURE_MODELS
                        from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
                        models={m['kind']:m for m in library_models() if m['kind'] in (*FURNITURE_MODELS,*SIZES)}
                        intent['layout_version']=PARAMETRIC_REVISION
                        for item in reference['items']:
                            kind=item['kind'];model=models[kind];slot=intent['objects'][item['id']]
                            slot.update(model_id=model['model_id'],
                                dimensions_m=list(FURNITURE_MODELS[kind][0] if kind in FURNITURE_MODELS else SIZES[kind]),
                                variant=model['variants'][0],finish=model['finishes'][0],
                                placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
                        intent['objects']['bed'].update(dimensions_m=[1.1,2.,.9],variant='single',finish='white')
                        intent['objects']['wardrobe'].update(dimensions_m=[.9,.55,1.8],variant='open',finish='white')
                        intent['objects']['desk'].update(dimensions_m=[1.1,.6,.8],variant='metal')
                        for child,parent,part in reviewed_photo_constraints(reference['image_sha256']).supports:
                            intent['objects'][child]['placement'].update(relation='surface',parent_id=parent,part=part)
                        for child,parent,part,anchor in [('bedding_overhang','bed','mattress','left'),
                                ('hanging_clothes','wood_frame','body','front')]:
                            intent['objects'][child]['placement'].update(relation='drape',parent_id=parent,part=part,anchor=anchor)
                        intent['objects']['window_blind']['placement'].update(relation='wall',parent_id='rear_wall',elevation_m=1.5)
                        intent['objects']['ceiling_light']['placement'].update(relation='ceiling',parent_id='ceiling')
                    # Historical fixtures remain explicit tests. They are emitted
                    # as a generic array, never injected by an image hash in product.
                    if generic:
                        from tests.fixtures.generic_room_layout import object_intent, intent as generic_intent
                        from twinpulse_provider.scene_contract import GROUNDING_REVISION
                        intent=generic_intent(object_intent('bed','bed','middle_right',size=[1.1,2.,.9]),
                            object_intent('desk','desk','rear_left',size=[1.1,.6,.8]),
                            object_intent('display','monitor','rear_left',relation='surface',parent='desk',part='top'),
                            object_intent('parcel','box','front_left'),width=4,length=5)
                        intent['layout_version']=GROUNDING_REVISION
                        for item in intent['objects']:
                            item.pop('observation_ids')
                            item['source']=dict(basis='visual',observation_ids=['seen_'+item['id']],user_quote=None)
                        observed=dict(schema_version='1.1',summary='Explicit synthetic object observation, not image inference.',
                            entities=[dict(id='seen_'+item['id'],kind='static_obstacle',description=item['kind'],confidence=.9,
                                role='object',category=item['kind'],region=item['region'],spatial_confidence=.9)
                                for item in intent['objects']],
                            relations=[],dimensions=[],ambiguities=['Fixture only; scale unmeasured'])
                    else:
                        kinds={row['id']:row['kind'] for row in reference['items']}
                        intent['objects']=[dict(id=i,kind=kinds[i],**slot) for i,slot in intent['objects'].items()]
                        for slot in intent['objects']:slot['observation_ids']=['bed_visual']
                        observed=dict(schema_version='1.0',summary='Historical synthetic inventory fixture.',
                            entities=[dict(id='bed_visual',kind='static_obstacle',description='Synthetic selected inventory',confidence=.8)],
                            relations=[],dimensions=[],ambiguities=['Fixture only'])
                    transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observed),
                        completion('compact',PLANNER_MODEL,intent))
                    adapter=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
                        planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
                    return await adapter.generate(request,token,config())
                plan=furnished_source().plan.to_dict();plan['plan_version']='2.2'
                if os.environ.get('TWINPULSE_LIBRARY_MODELS')=='1':
                    from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION
                    for call in plan['calls']:
                        if call['tool']=='place_furniture':
                            args=call['arguments']
                            args.update(catalog_version=PARAMETRIC_FURNITURE_VERSION,
                                dimensions_m=[1.5,2.,.9] if args['kind']=='bed' else [1.1,.6,.74],
                                variant='double' if args['kind']=='bed' else 'metal',finish='white')
                observed_objects=[]
                by_call={c['call_id']:c for c in plan['calls']}
                for item in plan['call_evidence']:
                    call=by_call[item['call_id']];args=call['arguments']
                    item.update(basis='user',observation_ids=[],user_quote=request.prompt)
                    if request.images and call['tool'] in ('place_furniture','place_room_item'):
                        identity='seen_'+args['id']
                        item.update(basis='visual',observation_ids=[identity],user_quote=None)
                        observed_objects.append(dict(id=identity,kind='static_obstacle',description=args['kind'],confidence=.9,
                            role='object',category=args['kind'],region='unknown',spatial_confidence=0))
                from twinpulse_provider.scene_contract import PROPOSAL_REVISION
                floor=next(c for c in plan['calls'] if c['tool']=='create_floor')
                proposal={**{k:plan[k] for k in ('plan_version','scene_id','summary','image_observations')},
                    'proposal_version':PROPOSAL_REVISION,'coordinate_frame':'photo_view_right_rear' if request.images else 'local_xy',
                    'floor_call':floor,'floor_evidence':next(e for e in plan['call_evidence'] if e['call_id']==floor['call_id']),
                    'scene_calls':[c for c in plan['calls'] if c['tool']!='create_floor'],
                    'call_evidence':[e for e in plan['call_evidence'] if e['call_id']!=floor['call_id']]}
                responses=[completion('plan',PLANNER_MODEL,proposal)]
                if request.images and os.environ.get('TWINPULSE_JOURNEY_DIAGNOSTICS')=='1':
                    # Exercise the existing single repair, not a production fallback.
                    responses.insert(0,completion('invalid-plan',PLANNER_MODEL,{'invalid':True}))
                if request.images:responses.insert(0,completion('obs',OBSERVER_MODEL,dict(schema_version='1.1',
                    summary='Explicit synthetic observation, not image recognition.',entities=observed_objects,
                    relations=[],dimensions=[],ambiguities=['Fixture only; scale and photo placement unverified'])))
                adapter=provider(ScriptedTransport(*responses))
                if os.environ.get('TWINPULSE_JOURNEY_DIAGNOSTICS')=='1':
                    adapter.max_repairs=1  # Explicit test-only fixture, bounded as production.
                return await adapter.generate(request,token,config(timeout_s=20.) if
                    os.environ.get('TWINPULSE_JOURNEY_DIAGNOSTICS')=='1' else config())
        backend.MockProvider=SiteTransportProvider
        backend.GenerationService=lambda adapter,settings:GenerationService(adapter,settings,plan_version='2.2')
    else:
        backend.MockProvider = RoomProvider
        backend.GenerationService = lambda provider, config: GenerationService(provider, config, plan_version='2.0')
    backend.main()


def main():
    from twinpulse_app.process_manager import TwinPulseProcessManager
    from tests.integration.test_r5_product_api import png
    class FixtureManager(TwinPulseProcessManager):
        def _engine_command(self):
            command=super()._engine_command()
            if args.fault or args.frame_fault or args.apply_fault:
                command[2]=str(ROOT/'scripts/verify_chat_sim_fault_host.py')
                command.insert(3,'--inject-build-apply-fault' if args.apply_fault else '--inject-first-frame-loss' if args.frame_fault else '--inject-sim-fault')
                if args.fault_cleanup:
                    command.insert(4,'--inject-sim-cleanup-fault')
            return command
        def _backend_command(self):
            command = super()._backend_command()
            command[1] = str(Path(__file__).resolve())
            command.insert(2, '--backend-child')
            return command
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--case', choices=('text', 'image'), required=True)
    parser.add_argument('--image-only', action='store_true', help='Submit an attached image with an empty user textarea; not a text+image benchmark packet.')
    parser.add_argument('--fault',action='store_true',help='Explicit isolated actual SIM pose-fault and HTTP receipt-loss acceptance')
    parser.add_argument('--fault-cleanup',action='store_true',help='Add an explicit owned SIM cleanup fault; requires --fault --diagnostics, never physical.')
    parser.add_argument('--frame-fault',action='store_true',help='Isolated actual Build with current frame delivery suppressed; diagnostics required, never live/physical.')
    parser.add_argument('--apply-fault',action='store_true',help='Isolated actual adapter apply-boundary exception before mutation; no rollback claim.')
    parser.add_argument('--storage-fault',choices=('project','diagnostics'),help='Isolated mandatory project commit or optional diagnostic manifest write failure.')
    parser.add_argument('--browser-image-fault',action='store_true',help='Explicit browser image HTTP 503 while actual Isaac still renders; fixture-only diagnostics.')
    parser.add_argument('--browser-diagnostic-delay',action='store_true',help='Hold one actual saved display-diagnosis ACK until image reception recovers; requires browser-image-fault.')
    parser.add_argument('--browser-decode-stall',action='store_true',help='Hold one actual decoded bitmap past freshness, then release it and verify recovery; fixture-only diagnostics.')
    parser.add_argument('--browser-image-delay',action='store_true',help='Delay one actual JPEG response past freshness and verify transport-vs-decode diagnosis; isolated fixture only.')
    parser.add_argument('--browser-metadata-delay',action='store_true',help='Delay metadata GETs 250ms during a bounded render soak and prove latest JPEG/receipt pairing; fixture-only.')
    parser.add_argument('--soak-seconds',type=int,default=0,help='Bounded 60..1800 second current-render/idle observation after the existing actual SIM journey.')
    parser.add_argument('--layout',choices=('bedroom','living_room','cluttered_room'),default='bedroom')
    parser.add_argument('--site-transport-fixture',action='store_true',help='Use the actual Nebius v2.2 pipeline with scripted transport, never paid network.')
    parser.add_argument('--budgeted-fixture',action='store_true',help='Explicit semantic structure/batch/patch recovery; zero network, actual App/Isaac.')
    parser.add_argument('--ordinary-approval-fixture',action='store_true',help='Isolated ordinary chat approval, truncated response and explicit checkpoint resume; no paid network.')
    parser.add_argument('--render-review-fixture',action='store_true',help='Synthetic source + actual Isaac renders + scripted critic/patch; zero network, not photo fidelity.')
    parser.add_argument('--ordinary-live-settings',type=Path,help='Explicit isolated reviewed settings for one live ordinary chat approval; never fixture or old campaign.')
    parser.add_argument('--benchmark-case',type=Path,help='Validated input/goal packet only; requires actual ordinary live settings, never a fixture')
    parser.add_argument('--library-models',action='store_true',help='Explicit parametric furniture transport fixture; no live inference.')
    parser.add_argument('--diagnostics',action='store_true',help='Verify saved execution correlation, developer UI/export and pure function profile in the existing journey.')
    parser.add_argument('--diagnostics-edits',action='store_true',help='Explicit fixture-only committed edit/Undo, actual frame and closed-backend origin re-open acceptance.')
    parser.add_argument('--live-campaign',type=Path,help='Explicit live provider with existing approved USD1 campaign/history; no scripted model response.')
    parser.add_argument('--split-provider-scope',type=Path,help='Explicit registered OpenAI observer/NVIDIA planner scope with a separate ten-call ledger.')
    parser.add_argument('--live-request-cap',type=int,choices=(1,2,3,4,5),default=5,
                        help='Reduce the existing host-only per-run inference cap; never expands approval.')
    parser.add_argument('--live-photo',type=Path,help='Original photo for explicit live image acceptance')
    parser.add_argument('--generic-photo',action='store_true',help='Generic four-object compact transport fixture, not photo recognition.')
    parser.add_argument('--compact-photo',action='store_true',help='Explicit experimental photo-layout path; fixture or approved live, never default.')
    parser.add_argument('--parametric-photo',action='store_true',help='Explicit new compact1.2 model/relationship fixture with persisted source2.1; zero inference.')
    parser.add_argument('--placement-edits',action='store_true',help='Explicit existing UI drag/rotate/preview/save/Undo and actual-frame acceptance; requires parametric-photo fixture.')
    parser.add_argument('--planner-template-policy',choices=('default','off'),default='default')
    parser.add_argument('--output-token-cap',type=int)
    parser.add_argument('--live-timeout-s',type=int,default=90,
                        help='Explicit approved evaluation total provider deadline 90..300s; not a default change.')
    parser.add_argument('--replay-live-run',type=Path,help='Explicit exact audited real responses; zero new calls, never a production fallback.')
    parser.add_argument('--replay-campaign',type=Path,help='Read-only original ledger binding for exact live response replay.')
    parser.add_argument('--replay-failed-packing',action='store_true',help='Explicit zero-network regression of a stopped two-response packing rejection; never historical/fresh model PASS.')
    parser.add_argument('--accepted-geometry-repair',type=Path,
        help='Exact audited accepted semantic result through App/actual Isaac, zero new inference')
    args = parser.parse_args()
    accepted_data=None
    if args.accepted_geometry_repair:
        if (args.case!='image' or not args.diagnostics or not args.live_photo or args.live_campaign
                or args.ordinary_live_settings or args.site_transport_fixture or args.replay_live_run
                or args.fault or args.compact_photo or args.library_models):
            raise SystemExit('Accepted geometry replay requires image/diagnostics/original photo, no live/fault/other fixture')
        from scripts.verify_semantic_scoped_live_recovery import audited_geometry
        accepted_data,accepted_payload,unused,accepted_result,accepted_audit=audited_geometry(args.accepted_geometry_repair)
        if hashlib.sha256(args.live_photo.read_bytes()).hexdigest()!=hashlib.sha256(accepted_data['request'].images[0].content).hexdigest():
            raise SystemExit('Accepted geometry photo hash changed')
        args.compact_photo=True
        os.environ['TWINPULSE_ACCEPTED_GEOMETRY_REPAIR']=str(args.accepted_geometry_repair.resolve())
        os.environ['TWINPULSE_ACCEPTED_GEOMETRY_PROMPT']=accepted_data['request'].prompt
        os.environ['TWINPULSE_ACCEPTED_MODEL_EXECUTION_ID']=accepted_result['execution_id']
    else:
        os.environ.pop('TWINPULSE_ACCEPTED_GEOMETRY_REPAIR',None)
        os.environ.pop('TWINPULSE_ACCEPTED_GEOMETRY_PROMPT',None)
    benchmark_case=None
    if args.benchmark_case:
        from scripts.benchmark_protocol import read_json,checked_packet
        if not args.ordinary_live_settings:raise SystemExit('Benchmark input requires actual ordinary live path')
        benchmark_case=checked_packet(read_json(args.benchmark_case),actual=True)
        from scripts.benchmark_protocol import canonical_sha
        os.environ['TWINPULSE_BENCHMARK_CASE_SHA256']=canonical_sha(benchmark_case)
        if (args.case!=('image' if benchmark_case['modality']=='photo' else 'text')
                or bool(args.live_photo)!=bool(benchmark_case['photo'])
                or args.live_photo and args.live_photo.resolve()!=Path(benchmark_case['photo']['path'])):
            raise SystemExit('Benchmark modality or approved photo path differs')
    if args.ordinary_live_settings:
        if (args.live_campaign or args.split_provider_scope or args.replay_live_run or args.site_transport_fixture
                or args.budgeted_fixture or args.ordinary_approval_fixture or args.compact_photo or args.fault
                or args.frame_fault or args.apply_fault or args.storage_fault or args.library_models
                or args.diagnostics_edits or args.parametric_photo or args.generic_photo or args.placement_edits
                or args.browser_image_fault or args.browser_diagnostic_delay or args.browser_decode_stall
                or args.browser_image_delay or args.browser_metadata_delay or args.fault_cleanup or args.soak_seconds
                or (args.case!='image' or not args.live_photo) and benchmark_case is None):
            raise SystemExit('Ordinary live acceptance requires approved input, isolated settings, no fixture/replay/fault/campaign mode')
        from twinpulse_app.generation_approval import GenerationApprovals
        from twinpulse_app.settings import JsonProviderSettingsStore
        from twinpulse_app.credentials import WindowsCredentialStore
        from twinpulse_app.key_registry import KeyRegistry
        from twinpulse_app.stage_routing import StageRoutingSettings
        reviewed=JsonProviderSettingsStore(args.ordinary_live_settings)
        reviewed_registry=KeyRegistry(reviewed,WindowsCredentialStore())
        reviewed_route=StageRoutingSettings(reviewed_registry).load()
        if not reviewed_route or reviewed_route.get('generation_policy',{}).get('max_requests')!=int(os.environ.get('TWINPULSE_ORDINARY_TEST_CAP','10')):
            raise SystemExit('Ordinary live ten-call approval policy missing')
    if args.ordinary_approval_fixture and not args.budgeted_fixture:
        raise SystemExit('Ordinary approval acceptance requires the isolated budgeted fixture')
    if args.render_review_fixture and (not args.ordinary_approval_fixture or args.case!='image' or args.live_photo
            or args.ordinary_live_settings or args.accepted_geometry_repair):
        raise SystemExit('Render review requires isolated ordinary approval and synthetic image, never private/live input')
    if args.budgeted_fixture and (not args.site_transport_fixture or not args.diagnostics or
            args.case!=('image' if args.render_review_fixture else 'text') or args.layout!='bedroom' or args.live_campaign or args.replay_live_run or
            args.compact_photo or args.fault or args.diagnostics_edits):
        raise SystemExit('Budgeted recovery requires isolated text/bedroom/diagnostics/site-transport fixture')
    if args.split_provider_scope and (not args.live_campaign or args.replay_live_run or args.site_transport_fixture
            or args.case!='image' or args.fault):
        raise SystemExit('Split provider acceptance requires explicit live photo/campaign and no fixture/replay/fault')
    if args.replay_failed_packing and not args.replay_live_run:
        raise SystemExit('Failed packing replay requires an explicit original live run and read-only ledger')
    if args.browser_metadata_delay and (not args.soak_seconds or args.case!='text'):
        raise SystemExit('Metadata delay requires the explicit text render soak')
    if args.browser_diagnostic_delay and not args.browser_image_fault:
        raise SystemExit('Diagnostic delay requires the explicit browser-image fault fixture')
    if args.generic_photo and (not args.compact_photo or not args.site_transport_fixture or args.live_campaign or args.replay_live_run or args.parametric_photo):
        raise SystemExit('Generic photo requires compact/site-transport fixture only; no live/replay modes')
    if args.placement_edits and not args.parametric_photo:
        raise SystemExit('Placement edits require the parametric-photo fixture')
    if args.parametric_photo and (not args.compact_photo or not args.site_transport_fixture or not args.diagnostics or
            args.live_campaign or args.replay_live_run or args.fault):
        raise SystemExit('Parametric photo requires compact/image/site-transport/diagnostics fixture only')
    if (args.browser_image_fault or args.browser_decode_stall or args.browser_image_delay or args.soak_seconds) and (not args.diagnostics or not args.site_transport_fixture or
            (args.case!='text' and not (args.soak_seconds and args.parametric_photo and args.placement_edits)) or
            (args.browser_image_fault and args.case!='text') or
            args.fault or args.fault_cleanup or args.frame_fault or args.apply_fault or args.storage_fault or args.live_campaign or args.replay_live_run or args.diagnostics_edits):
        raise SystemExit('Browser display/soak requires isolated diagnostics fixture; photo soak also requires parametric placement edits')
    if args.soak_seconds and not 60<=args.soak_seconds<=1800:
        raise SystemExit('Soak duration must be 60..1800 seconds')
    if (args.apply_fault or args.storage_fault) and (not args.diagnostics or not args.site_transport_fixture or args.case!='text' or
            args.fault or args.fault_cleanup or args.frame_fault or args.live_campaign or args.replay_live_run or args.library_models or args.diagnostics_edits or
            bool(args.apply_fault and args.storage_fault)):
        raise SystemExit('Apply/storage faults require isolated diagnostics/text/site-transport fixture only')
    if args.frame_fault and (not args.diagnostics or not args.site_transport_fixture or args.case!='text' or
            args.fault or args.fault_cleanup or args.live_campaign or args.replay_live_run or args.library_models or args.diagnostics_edits):
        raise SystemExit('First frame fault requires isolated diagnostics/text/site-transport fixture only')
    if args.fault_cleanup and (not args.fault or not args.diagnostics or args.live_campaign or args.replay_live_run):
        raise SystemExit('Compound cleanup fault requires isolated --fault --diagnostics without live/replay')
    if args.library_models and (not args.site_transport_fixture or args.live_campaign or args.replay_live_run or args.compact_photo or args.fault or args.case!='text' or args.layout!='bedroom'):
        raise SystemExit('Library fixture requires text bedroom site-transport fixture only')
    if bool(args.replay_live_run) != bool(args.replay_campaign):
        raise SystemExit('Exact replay requires both the live run and its original campaign')
    if args.replay_live_run and (args.live_campaign or args.site_transport_fixture or args.fault or not args.compact_photo):
        raise SystemExit('Exact replay cannot mix live/scripted/fault modes and requires compact photo')
    if args.live_campaign and (args.site_transport_fixture or args.fault):
        raise SystemExit('Live and scripted/fault model modes must not be mixed')
    if args.live_request_cap!=5 and not args.live_campaign:
        raise SystemExit('Live request cap requires an explicit approved campaign')
    if args.live_timeout_s!=90 and (not args.live_campaign or not 90<=args.live_timeout_s<=300):
        raise SystemExit('Timeout override requires an explicit live campaign and bounded deadline 90..300')
    if args.output_token_cap is not None and (not args.live_campaign or not 1 <= args.output_token_cap <= 10000):
        raise SystemExit('Output token override requires an explicit live campaign and cap 1..10000')
    if args.planner_template_policy=='off' and not args.live_campaign:
        raise SystemExit('Experimental template policy requires an explicit live campaign')
    if args.live_campaign and args.case=='image' and not args.live_photo:
        raise SystemExit('Live image acceptance requires an original photo')
    if args.compact_photo and (args.case!='image' or not args.live_photo or
            not (args.live_campaign or args.site_transport_fixture or args.replay_live_run or args.accepted_geometry_repair) or args.fault):
        raise SystemExit('Compact photo requires an original image and explicit live/site-transport fixture mode, without faults')
    if args.diagnostics_edits and (not args.diagnostics or not args.library_models or
            not args.site_transport_fixture or args.case!='text' or args.fault or args.live_campaign or args.replay_live_run):
        raise SystemExit('Diagnostic edit acceptance requires diagnostics/library/text/site-transport fixture, without live/replay/fault modes')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = dict(status='FAIL', case=args.case, provider='explicit_fixture_v2',
                  photo_inference='NOT_RUN', physics='actual_local_Isaac',
                  paid_calls=0, robot_connections=0,fault_contract=args.fault,layout=args.layout,
                  site_transport_fixture=args.site_transport_fixture)
    result['experimental_compact_photo']=args.compact_photo
    if args.image_only and (args.case!='image' or args.benchmark_case):
        raise ValueError('IMAGE_ONLY_REQUIRES_IMAGE_AND_NO_TEXT_BENCHMARK_PACKET')
    result['image_only']=args.image_only
    result['parametric_photo']=args.parametric_photo
    result['generic_photo']=args.generic_photo
    result['placement_edits']=args.placement_edits
    result['library_models']=args.library_models
    result['budgeted_fixture']=args.budgeted_fixture
    result['ordinary_approval_fixture']=args.ordinary_approval_fixture
    result['render_review_fixture']=args.render_review_fixture
    result['planner_template_policy']=args.planner_template_policy
    result['output_token_cap']=args.output_token_cap
    result['live_request_cap']=args.live_request_cap if args.live_campaign else None
    result['live_timeout_s']=args.live_timeout_s if args.live_campaign else None
    result['production_default']=False
    result['split_provider_evaluation']=bool(args.split_provider_scope)
    result['physical_authority']=False
    if accepted_data:
        result.update(provider='audited_real_geometry_result_replay',photo_inference='SAVED_LIVE_OBSERVATION',
            accepted_model_execution_id=accepted_result['execution_id'],
            accepted_original_plan_sha256=accepted_result['compiled_plan_sha256'],
            accepted_semantic_revision=accepted_result['after_revision'],new_model_calls=0)
    result['cleanup_fault_contract']=args.fault_cleanup
    result['frame_fault_contract']=args.frame_fault
    result['apply_fault_contract']=args.apply_fault
    result['storage_fault_contract']=args.storage_fault
    result['browser_image_fault_contract']=args.browser_image_fault
    result['browser_diagnostic_delay_contract']=args.browser_diagnostic_delay
    result['browser_decode_stall_contract']=args.browser_decode_stall
    result['browser_image_delay_contract']=args.browser_image_delay
    result['browser_metadata_delay_contract']=args.browser_metadata_delay
    result['soak_seconds']=args.soak_seconds
    if args.frame_fault:result['injected_failure']='current_frame_delivery_suppressed_not_GPU_failure'
    if args.live_campaign:
        result.update(provider='live_configured_provider',paid_calls='see_shared_campaign',photo_inference='LIVE' if args.case=='image' else 'NOT_APPLICABLE')
    if args.ordinary_live_settings:
        result.update(provider='live_ordinary_chat_approval',paid_calls='see_ordinary_ledger',
            photo_inference='LIVE' if args.case=='image' else 'NOT_APPLICABLE',production_default=False)
    if benchmark_case:
        result['benchmark_input']={key:benchmark_case[key] for key in
            ('case_id','room_group','split','modality','prompt_sha256')}
        result['benchmark_input']['goal_sha256']=benchmark_case['goal']['sha256']
    source_draft = None
    if args.replay_live_run:
        from scripts.replay_audited_inference import ExactAuditedResponses, live_run_inputs, failed_packing_run_inputs
        read_inputs=failed_packing_run_inputs if args.replay_failed_packing else live_run_inputs
        source_draft, evidence_root, ids = read_inputs(args.replay_live_run)
        ExactAuditedResponses(args.replay_campaign,evidence_root,ids)
        if hashlib.sha256(args.live_photo.read_bytes()).hexdigest() != source_draft.input_revision.images[0]['sha256']:
            raise SystemExit('Replay photo differs from original live input')
        result.update(provider='exact_previous_real_responses',photo_inference='PREVIOUS_LIVE_RESULT_REPLAY',
            original_live_attempts=ids,original_plan_sha256=source_draft.plan_sha256,
            original_input_revision=source_draft.input_revision.digest,original_scene_revision=source_draft.site.scene.revision if source_draft.site else None,
            original_packing_rejection=args.replay_failed_packing,
            original_live_result_sha256=hashlib.sha256((args.replay_live_run/'result.json').read_bytes()).hexdigest())
        if args.replay_failed_packing:
            from scripts.replay_audited_inference import expected_failed_packing_plan
            from twinpulse_core.revisions import canonical_sha256
            plan,provenance,quality=expected_failed_packing_plan(source_draft,evidence_root,ids,args.live_photo)
            result['packing_regression_expected']=dict(plan_sha256=canonical_sha256(plan),provenance=provenance,
                photo_quality=quality,claim='Current compile of unchanged previously rejected raw intent, not historical or fresh LLM PASS')
        replay_sources=[args.replay_campaign,args.replay_live_run/'result.json',
            args.replay_live_run/'runtime/active_project.json',
            *evidence_root.glob('*.json'),*(args.replay_live_run/'runtime/inputs').rglob('*')]
        result['replay_source_at_start']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in replay_sources if p.is_file()}
        os.environ['TWINPULSE_EXACT_LIVE_REPLAY']=str(args.replay_live_run.resolve())
        os.environ['TWINPULSE_EXACT_REPLAY_CAMPAIGN']=str(args.replay_campaign.resolve())
        os.environ['TWINPULSE_REPLAY_FAILED_PACKING']='1' if args.replay_failed_packing else '0'
    else:
        os.environ.pop('TWINPULSE_EXACT_LIVE_REPLAY',None)
        os.environ.pop('TWINPULSE_EXACT_REPLAY_CAMPAIGN',None)
        os.environ.pop('TWINPULSE_REPLAY_FAILED_PACKING',None)
    inference_paths=('packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py',
        'packages/twinpulse_provider/src/twinpulse_provider/budgeted_pipeline.py',
        'packages/twinpulse_provider/src/twinpulse_provider/generation_policy.py',
        'packages/twinpulse_provider/src/twinpulse_provider/generation_store.py',
        'packages/twinpulse_provider/src/twinpulse_provider/semantic_scene.py',
        'packages/twinpulse_app/src/twinpulse_app/generation_scope.py',
        'packages/twinpulse_app/src/twinpulse_app/generation_approval.py',
        'packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
        'packages/twinpulse_app/src/twinpulse_app/stage_routing.py',
        'scripts/fixture_budgeted_generation.py',
        'scripts/fixture_ordinary_generation.py',
        'packages/twinpulse_provider/src/twinpulse_provider/stage_transport.py',
        'packages/twinpulse_app/src/twinpulse_app/split_evaluation.py',
        'packages/twinpulse_app/src/twinpulse_app/key_registry.py',
        'packages/twinpulse_core/src/twinpulse_core/revisions.py',
        'packages/twinpulse_provider/src/twinpulse_provider/schema.py',
        'packages/twinpulse_provider/src/twinpulse_provider/scene_contract.py',
        'packages/twinpulse_provider/src/twinpulse_provider/reliability.py',
        'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py',
        'packages/twinpulse_provider/src/twinpulse_provider/support_packing.py',
        'packages/twinpulse_provider/src/twinpulse_provider/service.py',
        'packages/twinpulse_app/src/twinpulse_app/provider_composition.py',
        'packages/twinpulse_app/src/twinpulse_app/application.py',
        'packages/twinpulse_app/src/twinpulse_app/site_draft.py',
        'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
        'scripts/twinpulse_backend.py',
        'packages/twinpulse_core/src/twinpulse_core/furniture.py',
        'packages/twinpulse_core/src/twinpulse_core/room_items.py',
        'packages/twinpulse_core/src/twinpulse_core/photo_placement.py',
        'packages/twinpulse_core/src/twinpulse_core/photo_quality.py',
        'packages/twinpulse_core/src/twinpulse_core/site_simulation.py',
        'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py',
        'packages/twinpulse_core/src/twinpulse_core/simulation_goal.py',
        'scripts/replay_audited_inference.py')
    result['inference_source_at_start']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inference_paths}
    manager = None
    try:
        original=args.live_photo if args.case=='image' and (args.live_campaign or args.compact_photo or args.ordinary_live_settings) else None
        image = output/(accepted_data['request'].images[0].name if accepted_data else original.name if original else 'test-image.png')
        image.write_bytes(original.read_bytes() if original else png())
        Manager=FixtureManager
        if args.live_campaign:
            from twinpulse_app import JsonProviderSettingsStore,WindowsCredentialStore
            actual=JsonProviderSettingsStore().load().validated()
            JsonProviderSettingsStore(output/'runtime/provider_settings.json').save(actual)
            if not WindowsCredentialStore(actual.credential_ref).is_configured():raise RuntimeError('Existing live credential absent')
            class LiveManager(TwinPulseProcessManager):
                def _backend_command(self):
                    return [*super()._backend_command(),'--credential-target',actual.credential_ref,
                            '--inference-campaign',str(args.live_campaign.resolve()),
                            '--inference-request-cap',str(args.live_request_cap),
                            '--inference-timeout-s',str(args.live_timeout_s),
                            *(['--split-provider-scope',str(args.split_provider_scope.resolve())] if args.split_provider_scope else []),
                            *(['--profile-generation'] if args.diagnostics else []),
                            *(['--experimental-planner-no-thinking'] if args.planner_template_policy=='off' else []),
                            *(['--inference-output-token-cap',str(args.output_token_cap)] if args.output_token_cap is not None else []),
                            *(['--experimental-compact-photo'] if args.compact_photo else [])]
            Manager=LiveManager
        if args.ordinary_live_settings:
            target=output/'runtime'
            copy_ordinary_settings(args.ordinary_live_settings,target)
            class OrdinaryLiveManager(TwinPulseProcessManager):
                def _backend_command(self):
                    return [*super()._backend_command(),*(['--profile-generation'] if args.diagnostics else [])]
            Manager=OrdinaryLiveManager
        manager = Manager(repo_root=ROOT, state_dir=output/'runtime',
            python_executable=Path(sys.executable), isaac_python=Path('C:/isaacsim/python.bat'),
            browser_executable=None, headless=True, fixture_mode=not bool(args.live_campaign or args.ordinary_live_settings), ready_timeout_s=180.)
        os.environ['TWINPULSE_CONTRACT_LAYOUT']=args.layout
        os.environ['TWINPULSE_SITE_TRANSPORT_FIXTURE']='1' if args.site_transport_fixture else '0'
        os.environ['TWINPULSE_BUDGETED_FIXTURE']='1' if args.budgeted_fixture else '0'
        os.environ['TWINPULSE_ORDINARY_APPROVAL_FIXTURE']='1' if args.ordinary_approval_fixture else '0'
        os.environ['TWINPULSE_RENDER_REVIEW_FIXTURE']='1' if args.render_review_fixture else '0'
        os.environ['TWINPULSE_BUDGETED_FIXTURE_STORE']=str(output/'budgeted-fixture')
        os.environ['TWINPULSE_GENERIC_PHOTO']='1' if args.generic_photo else '0'
        os.environ['TWINPULSE_COMPACT_PHOTO']='1' if args.compact_photo else '0'
        os.environ['TWINPULSE_PARAMETRIC_PHOTO']='1' if args.parametric_photo else '0'
        os.environ['TWINPULSE_LIBRARY_MODELS']='1' if args.library_models else '0'
        # The backend is spawned by start(), not by the later browser subprocess.
        os.environ['TWINPULSE_JOURNEY_DIAGNOSTICS']='1' if args.diagnostics else '0'
        os.environ['TWINPULSE_JOURNEY_STORAGE_FAULT']=args.storage_fault or ''
        manager.start(open_browser=False)
        base, ticket = manager.product_bootstrap()
        env = {**os.environ, 'TWINPULSE_VIEW_URL': base, 'TWINPULSE_VIEW_BOOTSTRAP': ticket,
               'TWINPULSE_VIEW_OUTPUT': str(output), 'TWINPULSE_JOURNEY_IMAGE': str(image),
               'TWINPULSE_JOURNEY_CASE': args.case,'TWINPULSE_JOURNEY_FAULT':'1' if args.fault else '0',
               'TWINPULSE_JOURNEY_LAYOUT':args.layout}
        env['TWINPULSE_JOURNEY_LIVE']='1' if args.live_campaign or args.ordinary_live_settings else '0'
        env['TWINPULSE_JOURNEY_IMAGE_ONLY']='1' if args.image_only else '0'
        env['TWINPULSE_JOURNEY_LIVE_TIMEOUT_S']=str(900 if args.ordinary_live_settings else args.live_timeout_s)
        env['TWINPULSE_ORDINARY_LIVE']='1' if args.ordinary_live_settings else '0'
        env.pop('TWINPULSE_BENCHMARK_INPUT_JSON',None)
        if benchmark_case:
            env['TWINPULSE_BENCHMARK_INPUT_JSON']=json.dumps(benchmark_case,ensure_ascii=False)
        env['TWINPULSE_GENERIC_PHOTO']='1' if args.generic_photo else '0'
        env['TWINPULSE_JOURNEY_COMPACT']='1' if args.compact_photo else '0'
        env['TWINPULSE_PARAMETRIC_PHOTO']='1' if args.parametric_photo else '0'
        env['TWINPULSE_PLACEMENT_EDITS']='1' if args.placement_edits else '0'
        env['TWINPULSE_JOURNEY_DIAGNOSTICS']='1' if args.diagnostics else '0'
        env['TWINPULSE_JOURNEY_DIAGNOSTICS_EDITS']='1' if args.diagnostics_edits else '0'
        env['TWINPULSE_JOURNEY_CLEANUP_FAULT']='1' if args.fault_cleanup else '0'
        env['TWINPULSE_JOURNEY_FRAME_FAULT']='1' if args.frame_fault else '0'
        env['TWINPULSE_JOURNEY_APPLY_FAULT']='1' if args.apply_fault else '0'
        env['TWINPULSE_JOURNEY_BROWSER_IMAGE_FAULT']='1' if args.browser_image_fault else '0'
        env['TWINPULSE_JOURNEY_BROWSER_DIAGNOSTIC_DELAY']='1' if args.browser_diagnostic_delay else '0'
        env['TWINPULSE_JOURNEY_BROWSER_DECODE_STALL']='1' if args.browser_decode_stall else '0'
        env['TWINPULSE_JOURNEY_BROWSER_IMAGE_DELAY']='1' if args.browser_image_delay else '0'
        env['TWINPULSE_JOURNEY_METADATA_DELAY']='1' if args.browser_metadata_delay else '0'
        env['TWINPULSE_JOURNEY_SOAK_SECONDS']=str(args.soak_seconds)
        with (output/'browser-worker.log').open('w',encoding='utf-8') as browser_log:
            completed = subprocess.run(['node', str(ROOT/'apps/twinpulse-web/e2e/chat-sim-journey.mjs')],
                cwd=ROOT/'apps/twinpulse-web', env=env,
                timeout=(1200 if args.ordinary_live_settings else max(300,args.live_timeout_s+180) if args.live_campaign else 300 if args.placement_edits else 180)+args.soak_seconds,
                check=False,
                stdout=browser_log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        result['browser_worker']={'returncode':completed.returncode,'log':'browser-worker.log'}
        if not (output/'browser.json').is_file():
            raise RuntimeError(f'Browser worker ended with exit {completed.returncode} without a result; see browser-worker.log')
        result['browser'] = json.loads((output/'browser.json').read_text(encoding='utf-8'))
        if benchmark_case and benchmark_case['goal']['expected']!='arrival' and result['browser']['status']=='PASS':
            from scripts.benchmark_diagnostic import validate_diagnostic
            result['diagnostic_goal_acceptance']=validate_diagnostic(benchmark_case,result['browser'].get('diagnostic_goal'))
        if accepted_data and result['browser']['status']=='PASS':
            if result['browser']['workflow']['site_draft']['plan_sha256']!=accepted_result['compiled_plan_sha256']:
                raise RuntimeError('App changed the actual accepted model result')
            audited_geometry(args.accepted_geometry_repair)
            result['accepted_geometry_source_unchanged']=True
        if source_draft:
            result['browser'].update(provider='exact_previous_real_responses',photo_inference='PREVIOUS_LIVE_RESULT_REPLAY',paid_calls=0)
            expected_plan=result['packing_regression_expected']['plan_sha256'] if args.replay_failed_packing else source_draft.plan_sha256
            if result['browser'].get('compact_inventory',{}).get('plan_sha256') != expected_plan:
                raise RuntimeError('Exact replay changed the original real model plan')
            replay_draft=result['browser']['workflow']['site_draft']
            if (replay_draft['input_revision'] != source_draft.input_revision.digest
                    or not args.replay_failed_packing and result['browser']['initial_preview_plan']['scene_revision'] != source_draft.site.scene.revision):
                raise RuntimeError('Exact replay changed original input or scene identity')
        if completed.returncode or result['browser']['status'] != 'PASS':
            raise RuntimeError(result['browser'].get('error', 'Browser acceptance failed'))
        if args.render_review_fixture:
            ledgers = [json.loads(p.read_text(encoding='utf-8')) for p in (output/'runtime'/'ordinary-generation').glob('*.ledger.json')]
            progress = result['browser']['conversation']['generation']['progress']
            if len(ledgers)!=1 or len(ledgers[0]['requests'])!=6 or progress['budget']['repairs']!=1:
                raise RuntimeError('Render loop must retain one approval, six audited fixture responses, one repair')
            if progress['stage_acceptance']['Isaac_Build']!='preview_passed':
                raise RuntimeError('Generation render review did not pass the actual preview path')
            from twinpulse_provider.generation_store import GenerationStore
            from twinpulse_app.project_store import ProjectStore
            store=GenerationStore(output/'runtime'/'provider-evidence'/'generation-store')
            checkpoints=[store.read('checkpoint',p.stem) for p in (store.root/'checkpoint').glob('*.json')]
            ready=[value for value in checkpoints if value['state']=='APPROXIMATE_TWIN_READY']
            if len(ready)!=1:raise RuntimeError('Expected one completed current render checkpoint')
            reviews=ready[0]['render_history']
            if (len(reviews)!=2 or [row['status'] for row in reviews]!=['needs_revision','consistent']
                    or reviews[0]['candidate_revision']==reviews[1]['candidate_revision']
                    or reviews[0]['frame_key']==reviews[1]['frame_key']):
                raise RuntimeError('Expected distinct before/after candidate render evidence')
            stored=ProjectStore(output/'runtime'/'active_project.json').load().site_draft
            if (reviews[-1]['plan_sha256']!=stored.plan_sha256 or
                    reviews[-1]['capture']['scene_revision']!=stored.site.scene.revision):
                raise RuntimeError('Reviewed final render does not bind to saved draft')
            for row in reviews:
                frozen=store.read('render',row['frame_key'])
                if (frozen['metadata']!=row['capture'] or hashlib.sha256(
                        __import__('base64').b64decode(frozen['jpeg_base64'])).hexdigest()!=row['capture']['sha256']):
                    raise RuntimeError('Frozen render and reviewed metadata differ')
                if row['capture']['engine_session_id']!=reviews[-1]['capture']['engine_session_id']:
                    raise RuntimeError('Review crossed engine identities')
            result['ordinary_approval_audit']={'status':'PASS','approvals':1,'recorded_requests':6,
                'network_calls':0,'physical_authority':False,'photo_fidelity':'NOT_TESTED',
                'statuses':[r['status'] for r in ledgers[0]['requests']],
                'render_reviews':[{key:row[key] for key in ('status','candidate_revision','frame_key','plan_sha256')} for row in reviews],
                'stored_scene_revision':stored.site.scene.revision,'stored_plan_sha256':stored.plan_sha256}
        elif args.ordinary_approval_fixture:
            ledgers = [json.loads(p.read_text(encoding='utf-8')) for p in (output/'runtime'/'ordinary-generation').glob('*.ledger.json')]
            if len(ledgers)!=2 or sorted(len(v['requests']) for v in ledgers)!=[2,2]:
                raise RuntimeError('Ordinary approval fixture did not retain exactly two separate 2-request ledgers')
            progress = result['browser']['conversation']['generation']['progress']
            if progress['budget']['cumulative_requests']!=4 or progress['budget']['repairs']!=1:
                raise RuntimeError('Ordinary continuation counters differ from audited attempts')
            result['ordinary_approval_audit'] = {'status':'PASS','approvals':2,'recorded_requests':4,
                'statuses':sorted(r['status'] for v in ledgers for r in v['requests']),
                'cumulative_cost':progress['budget']['cumulative_cost'],'network_calls':0}
        result['status'] = 'PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error)[:1800])
    finally:
        if args.replay_live_run:
            result['replay_source_unchanged']=all(Path(p).is_file() and
                hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest
                for p,digest in result['replay_source_at_start'].items())
            if not result['replay_source_unchanged']:
                result.update(status='FAIL',error='Original live evidence/input/ledger changed during replay')
        if manager:
            if args.ordinary_live_settings:
                import time
                drain_deadline=time.monotonic()+310
                directory=output/'runtime'/'ordinary-generation'
                while any(directory.glob('*.dispatch-lock')) and time.monotonic()<drain_deadline:
                    time.sleep(.5)
                ledgers=[json.loads(p.read_text(encoding='utf-8')) for p in directory.glob('*.ledger.json')]
                rows=[r for v in ledgers for r in v['requests']]
                result['ordinary_live_audit']={'approvals':len(ledgers),'requests':len(rows),
                    'limits_usd':[v['limit_usd'] for v in ledgers],
                    'max_requests':[v['max_requests'] for v in ledgers],
                    'statuses':[r['status'] for r in rows],
                    'locks_pending':len(list(directory.glob('*.dispatch-lock'))),
                    'robot_connections':0,'claim':'Fresh ordinary approvals, actual HTTP, no fixture/replay'}
                if len(ledgers)>1 or len(rows)>int(os.environ.get('TWINPULSE_ORDINARY_TEST_CAP','10')):
                    result.update(status='FAIL',error='Ordinary live approval/count audit exceeded this one-grant test')
            if args.live_campaign:
                # Cancelled blocking HTTP may outlive the public 90s deadline.
                # Drain its local evidence/accounting before owned teardown.
                import time
                drain_deadline=time.monotonic()+95.
                while args.live_campaign.with_suffix('.dispatch-lock').exists() and time.monotonic()<drain_deadline:
                    time.sleep(.5)
            manager.stop()
            if args.diagnostics and getattr(manager, '_shutdown_trace', None):
                trace = manager._shutdown_trace
                trace.store.flush()
                result['launcher_shutdown_diagnostics'] = trace.store.detail(trace.execution_id)
                if result['launcher_shutdown_diagnostics']['status'] != 'succeeded':
                    result.update(status='FAIL', error='Owned launcher cleanup diagnostics recorded a failure')
            if manager.engine_result_file.is_file():
                result['host'] = json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
            # Browser/live-stream acceptance cannot hide a separate failed
            # host file capture. Intentional negative host cases remain distinct.
            if (result['status']=='PASS' and not args.fault and not args.frame_fault and not args.apply_fault
                    and args.storage_fault!='project'):
                host=result.get('host',{})
                result['host_capture_required']=True
                if host.get('status')!='PASS' or host.get('capture',{}).get('status')!='PASS':
                    result.update(status='FAIL',error='Owned host capture did not pass: '+str(host.get('capture',{}).get('reason','missing_host_result')))
            result['supervisor'] = json.loads(manager.supervisor_status_file.read_text(encoding='utf-8'))
            if any(result['supervisor'].get(key,{}).get('owned') for key in ('backend','engine')):
                result.update(status='FAIL',error='Owned supervisor process was not cleaned up')
            if result['status']=='PASS' and not args.fault and not args.frame_fault and not args.apply_fault and args.storage_fault!='project':
                observations=result.get('host',{}).get('simulation_preview_observations',[])
                visible=[o for o in observations if o['visibility']=='inherited' and not o['site_plan_present']]
                hidden=[o for o in observations if o['visibility']=='invisible' and o['site_plan_present']]
                expected=result['browser']['initial_preview_plan']
                if (len(visible)<2 or not hidden or any(o['physics_schema_count'] or not o['mesh_count'] or
                        o['motion_authorized'] is not False or o['scene_revision']!=expected['scene_revision'] or
                        o['plan_id']!=expected['plan_id'] for o in observations) or
                        any(o['timeline_playing'] or o['sim_burger_present'] or
                            o['position_m']!=[*expected['start'],expected['spawn_z_m']] for o in visible)):
                    result.update(status='FAIL',error='Pre-Run visual/handoff/reset USD invariants were not observed')
        if result['status']=='PASS' and args.storage_fault=='project':
            from twinpulse_app.project_store import ProjectStore
            saved=ProjectStore(output/'runtime/active_project.json').load()
            if saved.site_draft is not None:
                result.update(status='FAIL',error='Failed project commit appeared persisted after owned backend shutdown')
            else:
                result['storage_closed_backend_reopen']={'status':'PASS','site_draft_present':False,
                    'claim':'Failed commit cannot be reopened as a saved draft'}
        if result['status']=='PASS' and (args.render_review_fixture or
                args.ordinary_live_settings and reviewed_route['generation_policy']['external_final_review']):
            try:result['render_review_closed_backend_reopen']=audit_render_review_reopen(output)
            except Exception as error:result.update(status='FAIL',error='Render review closed-backend re-open: '+str(error)[:500])
        if result['status']=='PASS' and args.library_models:
            try:
                from twinpulse_app.project_store import ProjectStore
                from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION
                saved=ProjectStore(output/'runtime/active_project.json').load().site_draft
                furniture=[call for call in saved.plan.calls if call.tool=='place_furniture']
                assert len(furniture)==2 and saved.plan.plan_version=='2.2'
                for call in furniture:
                    values=call.arguments
                    assert values['catalog_version']==PARAMETRIC_FURNITURE_VERSION and values['finish']=='white'
                    assert values['dimensions_m']==([1.5,2.,.9] if values['kind']=='bed' else [1.1,.6,.74])
                result['library_saved_reopen']=dict(status='PASS',plan_sha256=saved.plan_sha256,
                    models=[dict(call.arguments) for call in furniture],physical_validation='NOT_RUN')
            except Exception as error:
                result.update(status='FAIL',error='Library saved project re-open: '+str(error)[:500])
        if result['status']=='PASS' and args.diagnostics_edits:
            try:
                from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow
                from twinpulse_app.project_store import ProjectStore
                project=ProjectStore(output/'runtime/active_project.json')
                original=project.path.read_bytes()
                restored=ApplicationService(None,project_store=project)
                source=restored.site_draft
                history=restored.scene_change_store().load()
                history_bytes=restored.scene_change_store().path.read_bytes()
                broker=CommandBroker()
                workflow=ProductWorkflow(restored,broker,mode='explicit_fixture',generation_settings_getter=lambda:{})
                reopened=workflow.resume_saved_scene(restored.project_id,source.site.scene.revision,source.input_revision.digest)
                refs=broker.artifact_diagnostic_refs(reopened['site_draft']['artifact_id'])
                expected=result['browser']['diagnostic_edits']
                assert refs['scene_edit_execution_id']==expected['undo_execution_id']
                assert refs['scene_edit_revision']==expected['undo_revision']
                assert restored.diagnostics.detail(expected['edit_execution_id'])['status']=='succeeded'
                undo=restored.diagnostics.detail(expected['undo_execution_id'])
                assert undo['manifest']['metadata']['scene_edit_execution_id']==expected['edit_execution_id']
                assert refs['evidence_id']==result['browser']['diagnostics']['detail']['manifest']['execution_id']
                assert reopened['acknowledged_revision'] is None and not broker.has_pending_operations()
                assert original==project.path.read_bytes() and history_bytes==restored.scene_change_store().path.read_bytes()
                assert len(history.operations)==2
                result['diagnostic_edit_reopen']=dict(status='PASS',refs=refs,original_unchanged=True,
                    history_unchanged=True,automatic_dispatch=False,physical_authority=False)
            except Exception as error:
                result.update(status='FAIL',error='Closed-backend diagnostic edit re-open: '+type(error).__name__)
        if result['status']=='PASS' and (args.compact_photo or args.ordinary_live_settings):
            # Re-open through the real project loader after the owned backend
            # exits. A browser reload alone could still read its in-memory draft.
            try:
                from twinpulse_app.project_store import ProjectStore
                from twinpulse_core.room_items import room_inventory
                saved=ProjectStore(output/'runtime/active_project.json').load().site_draft
                expected=result['browser']['compact_inventory']
                inventory=room_inventory(saved.plan,saved.site.scene)
                if (saved.plan_sha256!=expected['plan_sha256'] or saved.input_revision.digest!=expected['input_revision']
                        or len(inventory['items'])!=expected['items']):
                    raise ValueError('Saved compact photo identity or all-item coverage changed')
                result['saved_project_reopen']={'status':'PASS','schema_version':saved.schema_version,
                    'plan_sha256':saved.plan_sha256,'input_revision':saved.input_revision.digest,
                    'scene_revision':saved.site.scene.revision,'items':len(inventory['items']),
                    'physical_validation':inventory['physical_validation']}
                if args.live_campaign or args.accepted_geometry_repair or args.ordinary_live_settings:
                    # Fresh compact1.3 must retain every support relation on disk.
                    # No photograph-specific object names or expected positions.
                    from twinpulse_core.photo_placement import validate_placement_plan
                    assert saved.schema_version=='2.1'
                    assert len(saved.placement_contract['relations'])==expected['items']
                    validate_placement_plan(saved.plan,saved.placement_contract)
                    result['saved_project_reopen']['placement_contract_status']='PASS'
                    result['saved_project_reopen']['placement_relation_count']=len(saved.placement_contract['relations'])
                if args.generic_photo:
                    from twinpulse_core.photo_placement import validate_placement_plan
                    assert saved.schema_version=='2.1' and len(saved.placement_contract['relations'])==expected['items']
                    validate_placement_plan(saved.plan,saved.placement_contract)
                    monitor=next(r for r in saved.placement_contract['relations'] if r['id']=='display')
                    assert monitor['relation']=='surface' and monitor['parent_id']=='desk' and monitor['part']=='top'
                    result['saved_project_reopen']['placement_contract']=saved.placement_contract
                if args.parametric_photo:
                    from twinpulse_core.photo_placement import validate_placement_plan
                    assert saved.schema_version=='2.1' and len(saved.placement_contract['relations'])==24
                    validate_placement_plan(saved.plan,saved.placement_contract)
                    result['saved_project_reopen']['placement_contract']=saved.placement_contract
                    from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow
                    store=ProjectStore(output/'runtime/active_project.json')
                    source_bytes=store.path.read_bytes()
                    restored=ApplicationService(None,project_store=store)
                    history_store=restored.scene_change_store()
                    history_bytes=history_store.path.read_bytes()
                    history=history_store.load()
                    replayed,_=history.replay(saved)
                    validate_placement_plan(replayed,saved.placement_contract)
                    expected_operations=8 if args.placement_edits else 4
                    assert len(history.operations)==expected_operations and replayed.to_dict()==saved.plan.to_dict()
                    broker=CommandBroker()
                    workflow=ProductWorkflow(restored,broker,mode='explicit_fixture',generation_settings_getter=lambda:{})
                    reopened=workflow.resume_saved_scene(restored.project_id,saved.site.scene.revision,saved.input_revision.digest)
                    assert reopened['acknowledged_revision'] is None and not broker.has_pending_operations()
                    assert store.path.read_bytes()==source_bytes and history_store.path.read_bytes()==history_bytes
                    result['parametric_edit_reopen']=dict(status='PASS',history_operations=expected_operations,
                        source_unchanged=True,history_unchanged=True,automatic_dispatch=False,physical_authority=False)
            except Exception as error:
                result.update(status='FAIL',error='Saved compact project re-open: '+str(error)[:500])
        paths = ('scripts/verify_chat_sim_journey.py','apps/twinpulse-web/e2e/chat-sim-journey.mjs',
            'packages/twinpulse_core/src/twinpulse_core/simulation_goal.py',
            'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
            'packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
            'apps/twinpulse-web/src/ChatWorkspace.tsx','apps/twinpulse-web/src/SimulationRunCard.tsx',
            'apps/twinpulse-web/src/SimulationRouteView.tsx','apps/twinpulse-web/src/TwinViewport.tsx',
            'packages/twinpulse_core/src/twinpulse_core/site_simulation.py',
            'packages/twinpulse_app/src/twinpulse_app/command_broker.py',
            'packages/twinpulse_app/src/twinpulse_app/simulation_assets.py',
            'scripts/twinpulse_backend.py','scripts/twinpulse_engine_host.py',
            'extensions/twinpulse.extension/twinpulse/extension/runtime.py',
            'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
            'extensions/twinpulse.extension/twinpulse/extension/scene_compiler.py',
            'packages/twinpulse_app/src/twinpulse_app/api.py',
            'packages/twinpulse_app/src/twinpulse_app/application.py',
            'packages/twinpulse_app/src/twinpulse_app/process_manager.py',
            'packages/twinpulse_provider/src/twinpulse_provider/service.py',
            'apps/twinpulse-web/src/api.ts','apps/twinpulse-web/src/conversation-types.ts',
            'apps/twinpulse-web/src/conversation-intent.ts','apps/twinpulse-web/src/chat.css',
            'tests/integration/test_scene_changes.py')
        paths += ('extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py',)
        paths += ('extensions/twinpulse.extension/twinpulse/extension/room_visuals.py',
                  'packages/twinpulse_core/src/twinpulse_core/room_visuals.py',)
        paths += ('packages/twinpulse_core/src/twinpulse_core/model_library.py',
                  'packages/twinpulse_core/src/twinpulse_core/furniture.py',)
        if args.parametric_photo:
            paths += ('packages/twinpulse_core/src/twinpulse_core/photo_placement.py',
                'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py',
                'packages/twinpulse_provider/src/twinpulse_provider/support_packing.py',
                'packages/twinpulse_app/src/twinpulse_app/site_draft.py',
                'packages/twinpulse_app/src/twinpulse_app/scene_edit_proposals.py',
                'packages/twinpulse_provider/src/twinpulse_provider/scene_edit_provider.py',)
        if args.placement_edits:
            paths += ('apps/twinpulse-web/src/ScenePlacementMap.tsx','apps/twinpulse-web/src/ScenePlacementMap.test.tsx',)
        if args.diagnostics:
            paths += ('packages/twinpulse_core/src/twinpulse_core/execution_diagnostics.py',
                'packages/twinpulse_provider/src/twinpulse_provider/reliability.py',
                'packages/twinpulse_provider/src/twinpulse_provider/providers.py',
                'packages/twinpulse_provider/src/twinpulse_provider/contracts.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
                'packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
                'packages/twinpulse_app/src/twinpulse_app/chat_robot_preparation.py',
                'packages/twinpulse_app/src/twinpulse_app/robot_readiness.py',
                'packages/twinpulse_app/src/twinpulse_app/goal_task_loop.py',
                'packages/twinpulse_app/src/twinpulse_app/viewport_service.py',
                'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py',
                'tests/integration/test_execution_diagnostics.py',
                'scripts/twinpulse_launcher.py','tests/integration/test_r6_process_manager.py',
                'apps/twinpulse-web/src/ExecutionDiagnostics.tsx','apps/twinpulse-web/src/execution-diagnostics.css')
            paths += ('apps/twinpulse-web/src/ExecutionDiagnostics.test.tsx','apps/twinpulse-web/src/api.test.ts')
        paths += ('scripts/verify_chat_sim_fault_host.py','packages/twinpulse_core/src/twinpulse_core/sim_robot_selection.py',)
        paths += ('packages/twinpulse_core/src/twinpulse_core/room_item_catalog.py',
            'packages/twinpulse_core/src/twinpulse_core/room_items.py','packages/twinpulse_core/src/twinpulse_core/room_photo_inventory.py',
            'packages/twinpulse_core/src/twinpulse_core/site_tools.py','packages/twinpulse_core/src/twinpulse_core/tool_catalog.py',
            'packages/twinpulse_app/src/twinpulse_app/manual_room.py','packages/twinpulse_app/src/twinpulse_app/scene_changes.py',
            'packages/twinpulse_app/src/twinpulse_app/provider_composition.py','packages/twinpulse_provider/src/twinpulse_provider/schema.py',
            'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py','apps/twinpulse-web/src/RoomInventory.tsx',
            'apps/twinpulse-web/src/SceneEditReview.tsx','apps/twinpulse-web/src/types.ts','tests/integration/test_room_items.py')
        result['source_sha256'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
        result['inference_source_at_end']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inference_paths}
        result['inference_source_unchanged']=result['inference_source_at_start']==result['inference_source_at_end']
        if not result['inference_source_unchanged']:result.update(status='FAIL',error='Inference source changed during acceptance')
        result['web_sha256'] = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('CHAT_SIM_JOURNEY='+result['status'], flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__ == '__main__':
    if '--backend-child' in sys.argv:
        fixture_backend()
    else:
        raise SystemExit(main())
