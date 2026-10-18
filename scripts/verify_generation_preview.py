# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Ordinary App/API/Chrome preview journey, explicit model fixtures only.

--isaac uses one owned installed engine. Default has a synthetic bridge and is
never reported as actual Isaac. No credential, paid provider or physical robot.
"""
import argparse
import base64
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import json
import hashlib
import os
import secrets
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/tests'))
from tests.integration.test_generation_approval import GenerationApprovalTests,structure as bed_structure,furniture as bed_objects
from tests.integration.test_r5_product_api import png
from test_inventory_work import many_objects
from twinpulse_core import SimulationSnapshot,CommandReceipt
from twinpulse_app.process_manager import TwinPulseProcessManager


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--mode',choices=('text','image','image-text'),default='image-text')
    parser.add_argument('--isaac',action='store_true')
    parser.add_argument('--cancel',action='store_true',help='Cancel a running batch; a late valid fixture reply must not publish')
    parser.add_argument('--repair',action='store_true',help='Actual current render to scripted critic to scoped patch and rebuilt render')
    parser.add_argument('--partial-invalid',action='store_true',help='One invalid geometry slot; show independent objects before repair')
    parser.add_argument('--typed-items',action='store_true',help='Include the four new explicit layer/attachment kinds in the scripted candidate')
    parser.add_argument('--failed-repair',action='store_true',help='Two unchanged repairs stop, preserve eleven objects, then explicitly resume')
    args=parser.parse_args();output=args.output.resolve()
    if args.repair and (args.cancel or args.mode=='text'):
        parser.error('Render repair needs image input and cannot be combined with cancellation')
    if args.failed_repair and not args.partial_invalid:parser.error('Failed repair requires partial-invalid scenario')
    if not any(output.is_relative_to(ROOT/'outputs'/name) for name in ('generation-preview-20261012','progressive-preview-20261013')):
        raise SystemExit('OWNED_NEW_OUTPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=False)
    source_paths=[ROOT/p for p in ('packages/twinpulse_provider/src/twinpulse_provider/budgeted_pipeline.py',
        'packages/twinpulse_provider/src/twinpulse_provider/generation_preview.py',
        'packages/twinpulse_app/src/twinpulse_app/generation_render_port.py',
        'packages/twinpulse_app/src/twinpulse_app/viewport_service.py','packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/scene_edit_transaction.py',
        'packages/twinpulse_core/src/twinpulse_core/execution_diagnostics.py',
        'scripts/twinpulse_live_viewport.py','apps/twinpulse-web/dist/index.html',
        'apps/twinpulse-web/dist/twinpulse-build-manifest.json','apps/twinpulse-web/e2e/generation-preview.mjs',
        'apps/twinpulse-web/e2e/generation-preview-repair.mjs',
        'apps/twinpulse-web/e2e/progressive-preview.mjs',
        'packages/twinpulse_provider/src/twinpulse_provider/packing_candidates.py',
        'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py',
        'packages/twinpulse_provider/src/twinpulse_provider/semantic_scene.py',
        'packages/twinpulse_provider/src/twinpulse_provider/stage_transport.py',
        'packages/twinpulse_core/src/twinpulse_core/room_items.py',
        'packages/twinpulse_core/src/twinpulse_core/room_item_catalog.py',
        'packages/twinpulse_core/src/twinpulse_core/geometry_diagnostics.py',
        'packages/twinpulse_core/src/twinpulse_core/photo_placement.py',
        'packages/twinpulse_core/src/twinpulse_core/room_visuals.py',
        'packages/twinpulse_core/src/twinpulse_core/generation_visual.py',
        'packages/twinpulse_core/src/twinpulse_core/engine_contracts.py',
        'packages/twinpulse_app/src/twinpulse_app/command_broker.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/room_visuals.py',
        'scripts/verify_generation_preview.py')]
    frozen={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    os.environ['TWINPULSE_TEST_TMP']=str(output/'retained-runtime')
    harness=GenerationApprovalTests();harness.setUp()
    stop=Event();worker=None;manager=None
    result=dict(status='FAIL',actual_isaac=args.isaac,provider='explicit audited replies',
        external_api_requests=0,external_cost_usd='0',physical_requests=0,mode=args.mode,
        cancellation_test=args.cancel,render_repair_test=args.repair)
    try:
        raw,structure,batches=many_objects(12)
        if args.typed_items:
            kinds=('floor_covering','wall_fixture','ceiling_fixture','wall_storage')
            for row,kind in zip(structure['inventory'][-4:],kinds):
                row['kind']=kind
                value=batches[1][row['id']]
                relation='floor' if kind=='floor_covering' else 'ceiling' if kind=='ceiling_fixture' else 'wall'
                value.update(model_id='common.'+kind,dimensions_m=[1.2,.8,.02] if kind=='floor_covering' else [.8,.3,.6],
                    region='rear_centre' if relation=='wall' else 'middle_centre',
                    finish='catalog_default',variant='standard',placement=dict(relation=relation,
                        parent_id=None if relation=='floor' else 'ceiling' if relation=='ceiling' else 'rear_wall',
                        part=None,anchor='centre',elevation_m=1.8 if relation=='wall' else None))
            raw=dict(schema_version='1.2',summary='Explicit scripted catalogue observations, not actual photo recognition',
                entities=[dict(id=row['id'],kind='static_obstacle',role='object',category=row['kind'],
                    description='Explicit fixture '+row['kind'],confidence=.9,
                    region='rear_centre' if row['kind'] in ('wall_fixture','wall_storage') else 'middle_centre',
                    spatial_confidence=.8,instance_count=1) for row in structure['inventory']],
                relations=[],dimensions=[],ambiguities=['Fixture positions and dimensions are estimates'])
            for row in structure['inventory']:row['evidence_ref']='seen:'+row['id']
        if args.mode=='text':
            for row in structure['inventory']:row['evidence_ref']='text:0'
        harness.route['generation_policy']['external_final_review']=False
        harness.routes.save(harness.route,lambda:None)
        # A complete first batch precedes a single explicit output-stop. Resume
        # must request only the second batch, using a new ordinary approval.
        def stopped_batch(_body):
            time.sleep(3)  # Keep the real UI observable while a fixture response is pending.
            return batches[1] if args.cancel else ('length','')
        harness.responses=([raw] if args.mode!='text' else [])+[structure,batches[0],stopped_batch,batches[1]]
        if args.partial_invalid:
            invalid=deepcopy(batches[0]);bad_id=next(iter(invalid))
            invalid[bad_id]['dimensions_m'][0]=.2  # Schema-valid, library minimum violation.
            def remaining_objects(_body):
                time.sleep(4)
                return batches[1]
            def corrected_geometry(body):
                time.sleep(4)
                return dict(patch_version='semantic-patch-1.0',
                    base_revision=body['response_format']['json_schema']['schema']['properties']['base_revision']['enum'][0],
                    operations=[dict(op='update',id=bad_id,value=batches[0][bad_id])])
            # Slow inventory fixture proves the room appears BEFORE inventory completes.
            def planned_inventory(_body):
                time.sleep(4)
                return structure
            harness.room_seed_fixture={key:deepcopy(structure[key]) for key in ('summary','room')}
            def unchanged_geometry(body):
                time.sleep(4)
                return dict(patch_version='semantic-patch-1.0',
                    base_revision=body['response_format']['json_schema']['schema']['properties']['base_revision']['enum'][0],
                    operations=[dict(op='update',id=bad_id,value=deepcopy(invalid[bad_id]))])
            repairs=[unchanged_geometry,unchanged_geometry,corrected_geometry] if args.failed_repair else [corrected_geometry]
            harness.responses=([raw] if args.mode!='text' else [])+[planned_inventory,invalid,remaining_objects]+repairs
        if args.repair:
            harness.route['generation_policy']['external_final_review']=True
            harness.routes.save(harness.route,lambda:None)
            observation=dict(schema_version='1.1',summary='Explicit scripted observation; not photo quality',
                entities=[dict(id='seen_bed',kind='static_obstacle',description='bed',confidence=.9,
                    role='object',category='bed',region='unknown',spatial_confidence=.9)],
                relations=[],dimensions=[],ambiguities=['Explicit fixture, no real photo recognition'])
            planned=bed_structure();planned['inventory'][0]['evidence_ref']='seen:seen_bed'
            reviews=[]
            def critic(body):
                assert sum(row.get('type')=='image_url' for row in body['messages'][-1]['content'])==2
                props=body['response_format']['json_schema']['schema']['properties']
                key=props['frame_key']['enum'][0];reviews.append(key)
                time.sleep(3)  # Observe the real current candidate while the scripted critic is pending.
                return dict(review_version=props['review_version']['enum'][0],frame_key=key,
                    objects={'bed':{aspect:dict(status='contradiction' if len(reviews)==1 and aspect=='layout' else 'consistent',
                        confidence=.9,reason='Explicit scripted loop validation, not measured photo quality.')
                        for aspect in ('layout','support','appearance')}})
            def correction(body):
                content=json.loads(body['messages'][-1]['content'])
                value=dict(content['candidate']['objects']['bed'],region='rear_right')
                time.sleep(3)  # Verify the old render stays visible while the scoped correction is pending.
                return dict(patch_version='semantic-patch-1.0',
                    base_revision=body['response_format']['json_schema']['schema']['properties']['base_revision']['enum'][0],
                    operations=[dict(op='update',id='bed',value=value)])
            harness.responses=[observation,planned,bed_objects(),critic,correction,critic]
        harness.install_audited_fixture()
        harness.server._static_root=ROOT/'apps/twinpulse-web/dist'
        (output/'fixture.png').write_bytes(png())
        initial=SimulationSnapshot('preview-fixture','preview-epoch','default',None,None,1,'idle',None,None,
            ('build_site_scene',),('site_scene_build_v2','generation_room_visual_v1'))
        commands=[]
        if args.isaac:
            # Explicit ingress interruption, not fake pixels or engine receipts:
            # keep the real publisher/heartbeat running, temporarily omit its
            # frame from the normal exchange to exercise stale/reload recovery.
            normal_exchange=harness.server.viewport.exchange
            dropped_frames=[]
            def exchange_with_delivery_gate(engine_id,stage_epoch,body):
                if (output/'pause-frames.flag').exists() and body.get('frame') is not None:
                    dropped_frames.append(body['frame']['frame_id'])
                    body={**body,'frame':None}
                return normal_exchange(engine_id,stage_epoch,body)
            harness.server.viewport.exchange=exchange_with_delivery_gate
            # Refuse a concurrent Kit before allocating another GPU engine.
            live=subprocess.run(['powershell','-NoProfile','-Command',
                '(Get-Process kit -ErrorAction SilentlyContinue | Measure-Object).Count'],capture_output=True,text=True)
            if live.returncode or int(live.stdout.strip() or '0'):
                raise RuntimeError('OTHER_ISAAC_ACTIVE: close the existing user engine normally first')
            manager=TwinPulseProcessManager(repo_root=ROOT,state_dir=output/'owned-engine',
                python_executable=Path(sys.executable),isaac_python=Path('C:/isaacsim/python.bat'),
                browser_executable=None,headless=True,fixture_mode=True,ready_timeout_s=180)
            env={**os.environ,'TWINPULSE_BRIDGE_URL':harness.server.base_url,
                'TWINPULSE_ENGINE_BOOTSTRAP':'e'*43,'TWINPULSE_STATE_DIR':str(manager.engine_state_dir),
                'TWINPULSE_PROJECT_STATE_ROOT':str(harness.static),'TWINPULSE_PROJECT_ID':'default',
                'TWINPULSE_SESSION_HISTORY_ROOT':str(output/'owned-engine/history')}
            child=manager._spawn('engine',manager._engine_command(),env,hidden=True)
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                state=harness.broker.supervisor_state()
                if state['engine_connected'] and state.get('snapshot'):break
                if child.poll() is not None:raise RuntimeError('OWNED_ENGINE_START_FAILED')
                time.sleep(.2)
            else:raise RuntimeError('OWNED_ENGINE_READY_TIMEOUT')
        else:
            from PIL import Image
            harness.broker.register_engine('preview-fixture','preview-epoch')
            def engine():
                sequence=1;frame_sequence=0;revision=None;image=None
                while not stop.wait(.1):
                    command=harness.broker.claim('preview-fixture','preview-epoch')
                    if command:
                        commands.append(command.command_id);revision=command.payload['scene_revision']
                        harness.broker.record_receipt(CommandReceipt(command.command_id,command.command_type,'default',
                            'preview-fixture','preview-epoch','succeeded',applied_revision=revision,build_fingerprint='synthetic-bridge'))
                        stream=BytesIO();Image.new('RGB',(640,420),'#'+revision[:6]).save(stream,format='JPEG')
                        image=stream.getvalue()
                    harness.broker.record_snapshot(replace(initial,sequence=sequence,applied_revision=revision,
                        runtime_state='built' if revision else 'idle'));sequence+=1
                    if image and not (output/'pause-frames.flag').exists():
                        frame_sequence+=1
                        harness.server.viewport.exchange('preview-fixture','preview-epoch',dict(
                            engine_session_id='preview-fixture',stage_epoch='preview-epoch',camera_result=None,
                            frame=dict(frame_id=frame_sequence,applied_revision=revision,captured_at_ms=time.time()*1000,
                                width=640,height=420,camera_sequence=0,jpeg_base64=base64.b64encode(image).decode())))
            worker=Thread(target=engine,daemon=True);worker.start()
        bootstrap=secrets.token_urlsafe(32)
        harness.server._bootstrap['product']=bootstrap
        env={**os.environ,'TWINPULSE_PREVIEW_URL':harness.server.base_url,
            'TWINPULSE_PREVIEW_BOOTSTRAP':bootstrap,'TWINPULSE_PREVIEW_OUTPUT':str(output),
            'TWINPULSE_PREVIEW_MODE':args.mode,'TWINPULSE_PREVIEW_ACTUAL':str(args.isaac).lower(),
            'TWINPULSE_PREVIEW_CANCEL':str(args.cancel).lower(),
            'TWINPULSE_PREVIEW_FAILED_REPAIR':str(args.failed_repair).lower(),
            'TWINPULSE_PREVIEW_TYPED':str(args.typed_items).lower()}
        driver='progressive-preview.mjs' if args.partial_invalid else 'generation-preview-repair.mjs' if args.repair else 'generation-preview.mjs'
        completed=subprocess.run([str(args.node),str(ROOT/'apps/twinpulse-web/e2e'/driver)],
            cwd=ROOT/'apps/twinpulse-web',env=env,capture_output=True,text=True,encoding='utf-8',timeout=360,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (output/'browser-driver.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
        browser=json.loads((output/'browser.json').read_text())
        result['browser']=browser;result['fixture_dispatches']=len(harness.wires)
        result['expected_fixture_dispatches']=(5 if args.mode=='text' else 6) if args.partial_invalid else 7 if args.repair else 6 if args.mode!='text' else 5
        if args.failed_repair:result['expected_fixture_dispatches']+=1
        if args.repair:result['critic_frame_keys']=reviews
        result['checkpoint_count']=len(list((harness.manager.store.root/'checkpoint').glob('*.json')))
        result['runtime_directory']=str(harness.static)
        result['commands']=browser.get('engine_commands',[])
        if args.isaac:
            result['controlled_frame_delivery_interruption']=dict(dropped=len(dropped_frames),
                fake_pixels=False,fake_engine_receipts=False,scope='isolated viewport ingress')
        if completed.returncode or browser['status']!='PASS':raise RuntimeError('BROWSER_FAILED: '+str(browser.get('error',''))[:300])
        from twinpulse_app import ApplicationService
        from twinpulse_app.project_store import ProjectStore
        store=harness.workflow._application._project_store
        original=store.path.read_bytes();saved=store.load()
        restored=ApplicationService(None,project_store=ProjectStore(store.path))
        if args.failed_repair:
            result['exact_storage_restore']=restored.site_draft is None and saved.site_draft is None and store.path.read_bytes()==original
            files=list((harness.manager.store.root/'checkpoint').glob('*.json'))
            if len(files)!=1:raise ValueError('INCOMPLETE_CHECKPOINT_COUNT')
            checkpoint=json.loads(files[0].read_text(encoding='utf-8'))
            from twinpulse_core import canonical_sha256
            payload=checkpoint['payload']
            if (canonical_sha256(payload)!=checkpoint['payload_sha256'] or len(payload['draft']['inventory'])!=12
                    or len(payload['draft']['objects'])!=12 or payload['error_code']!='REPAIR_STALLED'
                    or payload['compiled_plan'] is not None or payload['Run']!='NOT_RUN'):
                raise ValueError('INCOMPLETE_WORK_NOT_PRESERVED')
            result['incomplete_checkpoint']=dict(sha256=hashlib.sha256(files[0].read_bytes()).hexdigest(),
                inventory=12,parameters=12,whole_pass=False,Run='NOT_RUN',committed_scene=False)
        else:
            result['exact_storage_restore']=restored.site_draft.to_dict()==saved.site_draft.to_dict() and store.path.read_bytes()==original
        if completed.returncode or browser['status']!='PASS' or not result['exact_storage_restore']:
            raise RuntimeError('BROWSER_OR_RESTORE_FAILED')
        result['status']='PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:500])
    finally:
        stop.set()
        if worker:worker.join(2)
        if manager:
            manager.engine_stop_file.parent.mkdir(parents=True,exist_ok=True)
            manager.engine_stop_file.write_text('normal owned shutdown',encoding='utf-8')
            manager._stop_owned('engine',graceful_s=30)
            if manager.engine_result_file.is_file():result['engine']=json.loads(manager.engine_result_file.read_text())
        harness.server.stop()  # Keep this named fixture's raw/ledger/checkpoint evidence.
        result['source_sha256']=frozen
        result['source_and_build_unchanged']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in frozen.items())
        if not result['source_and_build_unchanged']:result.update(status='FAIL',freeze_error='SOURCE_CHANGED')
        result['owned_api_and_engine_closed']=True
        (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('GENERATION_PREVIEW_'+result['status'])
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
