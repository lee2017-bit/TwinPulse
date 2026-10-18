# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Ordinary authenticated App/API + actual Chrome, audited provider fixture only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.integration.test_generation_approval import GenerationApprovalTests
from tests.integration.test_r5_product_api import png


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--photo-paste',action='store_true')
    parser.add_argument('--inventory-count',type=int,choices=(36,60))
    args=parser.parse_args();output=args.output.resolve()
    if args.photo_paste and args.inventory_count:parser.error('Choose one explicit UI fixture')
    allowed=ROOT/('outputs/inventory-work-20261012' if args.inventory_count else
        'outputs/photo-paste-capacity-20261012' if args.photo_paste else 'outputs/sim-generation-ux-20261012')
    if allowed not in output.parents:
        raise SystemExit('OWNED_NEW_OUTPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=False)
    harness=GenerationApprovalTests();harness.setUp()
    result={'status':'FAIL','external_api_requests':0,'physical_requests':0,'actual_isaac':False,
        'audited_provider_fixture':True,'owned_api_and_browser_closed':False}
    try:
        if args.inventory_count:
            sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/tests'))
            from test_inventory_work import many_objects
            raw,inventory,batches=many_objects(args.inventory_count)
            harness.responses=[raw,inventory,*batches]
            (output/'fixture.png').write_bytes(png())
        if args.photo_paste:
            # Explicit synthetic observation over a small PNG. Not the user's
            # photo or a live provider request; preserve the regular compiler.
            observation=dict(schema_version='1.2',summary='Synthetic bed, not a real photo test',
                entities=[dict(id='bed',kind='static_obstacle',role='object',category='bed',description='Bed',
                    confidence=.9,region='unknown',spatial_confidence=0,instance_count=1)],
                relations=[],dimensions=[],ambiguities=['Unmeasured fixture'])
            harness.responses.insert(0,observation)
            harness.responses[1]['inventory'][0]['evidence_ref']='seen:bed'
            (output/'fixture.png').write_bytes(png())
        harness.install_audited_fixture()
        harness.server._static_root=ROOT/'apps/twinpulse-web/dist'
        bootstrap=secrets.token_urlsafe(32);harness.server._bootstrap['product']=bootstrap
        env={**os.environ,'TWINPULSE_UI_URL':harness.server.base_url,
            'TWINPULSE_UI_BOOTSTRAP':bootstrap,'TWINPULSE_UI_OUTPUT':str(output),
            'TWINPULSE_UI_CASE':'inventory' if args.inventory_count else 'photo-paste' if args.photo_paste else 'text',
            'TWINPULSE_UI_COUNT':str(args.inventory_count or ''),
            'TWINPULSE_UI_IMAGE':str(output/'fixture.png') if args.photo_paste or args.inventory_count else ''}
        child=subprocess.run([str(args.node),str(ROOT/'apps/twinpulse-web/e2e/direct-generation-ui.mjs')],
            cwd=ROOT/'apps/twinpulse-web',env=env,timeout=60,capture_output=True,text=True,encoding='utf-8')
        result.update(json.loads((output/'browser.json').read_text(encoding='utf-8')))
        result['audited_fixture_dispatches']=len(harness.wires)
        result['broker_commands']=len(harness.broker.public_state('unowned')['operations'])
        result['source_sha256']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__),ROOT/'apps/twinpulse-web/e2e/direct-generation-ui.mjs',
                ROOT/'apps/twinpulse-web/dist/index.html',ROOT/'packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
                ROOT/'apps/twinpulse-web/src/clipboard-image.ts',ROOT/'apps/twinpulse-web/src/ChatWorkspace.tsx',
                ROOT/'packages/twinpulse_provider/src/twinpulse_provider/observation_instances.py',
                ROOT/'packages/twinpulse_provider/src/twinpulse_provider/budgeted_pipeline.py',
                ROOT/'packages/twinpulse_provider/src/twinpulse_provider/scene_capacity.py',
                ROOT/'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py',
                ROOT/'packages/twinpulse_provider/src/twinpulse_provider/semantic_scene.py',
                ROOT/'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/validation.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/site_contracts.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/site_tools.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/scene_resources.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/photo_placement.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/progressive_twin.py',
                ROOT/'packages/twinpulse_core/src/twinpulse_core/photo_quality.py',
                ROOT/'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py']}
        manifest=json.loads((ROOT/'apps/twinpulse-web/dist/twinpulse-build-manifest.json').read_text(encoding='utf-8'))
        result['build_manifest_verified']=all(hashlib.sha256((ROOT/'apps/twinpulse-web/dist'/name).read_bytes()).hexdigest()==sha
            for name,sha in manifest['files'].items())
        if args.photo_paste:
            request=harness.manager.request()
            result['pasted_image_bytes_match']=bool(request.images) and request.images[0].content==png()
        if args.inventory_count:
            state=harness.call();progress=state['generation']['progress']
            result.update(inventory_count=args.inventory_count,generation=state['generation'],
                declared_fixture_only=True,photographic_quality='NOT_TESTED')
            checkpoint=harness.manager.store.read('checkpoint',progress['checkpoint_id'])
            result['checkpoint_inventory_count']=len(checkpoint['draft']['inventory'])
            result['checkpoint_parameter_count']=len(checkpoint['draft']['objects'])
            result['checkpoint_pending_count']=len(checkpoint['pending_parameter_ids'])
            expected=(60,42,18) if args.inventory_count==60 else (36,36,0)
            if (result['checkpoint_inventory_count'],result['checkpoint_parameter_count'],result['checkpoint_pending_count'])!=expected:
                result['status']='FAIL'
        expected_requests=9 if args.inventory_count==60 else 8 if args.inventory_count==36 else 3 if args.photo_paste else 2
        if child.returncode or not result['build_manifest_verified'] or len(harness.wires)!=expected_requests or result['broker_commands'] or (
                args.photo_paste and not result.get('pasted_image_bytes_match')):
            result['status']='FAIL'
    except Exception as error:
        result['error_type']=type(error).__name__
    finally:
        harness.tearDown();result['owned_api_and_browser_closed']=True
        (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('DIRECT_GENERATION_UI_'+result['status'])
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
