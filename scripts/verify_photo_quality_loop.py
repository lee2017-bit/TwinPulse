# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded real-model evaluation; NEVER implies a product quality gate exists.

The oracle is an assisted P01 review. Injected negatives, exact real-response
reuse, fresh planner calls and external critique/feedback remain separate.
No new compiler, source migration, credentials export or robot connection.
"""
import argparse
import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))

from twinpulse_core import SiteToolPlan,execute_site_tool_plan
from twinpulse_core.furniture import expand_furniture
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256
from twinpulse_core.revisions import canonical_sha256
from twinpulse_provider import GenerationRequest,ImageInput,GenerationService,CancellationToken
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider
from scripts.replay_audited_inference import ExactAuditedResponses,live_run_inputs


def facts(payload):
    """Inspect actual emitted geometry, not the model's self-description."""
    plan=SiteToolPlan.from_dict(payload)
    objects={c.arguments['id']:dict(c.arguments) for c in plan.calls
             if c.tool in {'place_furniture','place_room_item'}}
    floor=next(c.arguments for c in plan.calls if c.tool=='create_floor')
    issues=[];support_checks=[]
    for identity,side in (('bed','right'),('desk','left')):
        item=objects.get(identity)
        x=item.get('center_m',item.get('position_m',[None]))[0] if item else None
        if x is None or (side=='right' and x<=0) or (side=='left' and x>=0):
            issues.append(dict(code='PHOTO_SIDE_MISMATCH',id=identity,expected=side,actual_x=x))
    # Confident rear landmarks in P01. Bed depth is partially occluded, so do not
    # manufacture an exact target for it from this single perspective.
    for identity in ('desk','wardrobe'):
        item=objects.get(identity)
        y=item.get('center_m',item.get('position_m',[None,None]))[1] if item else None
        if y is None or y<=0:
            issues.append(dict(code='PHOTO_DEPTH_MISMATCH',id=identity,expected='rear',actual_y=y))
    for child,parent,part in (('top_storage','wardrobe','body'),('monitor','desk','top'),('tabletop_items','desk','top')):
        c=objects.get(child);p=objects.get(parent)
        if not c or not p or 'position_m' not in c:
            row=dict(id=child,parent=parent,status='FAIL',reason='missing geometry')
        else:
            support=next(o for o in expand_furniture(p) if o.id==parent+'_'+part)
            px,py,pz=support.transform.position_m;sx,sy,sz=support.shape.dimensions_m
            x,y,z=c['position_m'];dx,dy,dz=c['dimensions_m']
            a=math.radians(p['yaw_deg']);co,si=math.cos(a),math.sin(a)
            lx,ly=co*(x-px)+si*(y-py),-si*(x-px)+co*(y-py)
            angle=math.radians(c['yaw_deg']-p['yaw_deg'])
            hx=(abs(math.cos(angle))*dx+abs(math.sin(angle))*dy)/2
            hy=(abs(math.sin(angle))*dx+abs(math.cos(angle))*dy)/2
            inside=abs(lx)+hx<=sx/2+.015 and abs(ly)+hy<=sy/2+.015
            gap=z-dz/2-(pz+sz/2)
            valid=inside and abs(gap)<=.02
            row=dict(id=child,parent=parent,status='PASS' if valid else 'FAIL',
                     xy_contained=inside,bottom_to_support_top_gap_m=round(gap,6))
        support_checks.append(row)
        if row['status']!='PASS':issues.append(dict(code='PHOTO_SUPPORT_MISMATCH',**row))
    width,length=floor['size_m']
    return dict(schema_version='photo-quality-audit-1.0',source='human_review_assisted_P01',
        photo_sha256=PHOTO_SHA256,physical_validation='NOT_RUN',
        metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS',room_estimate_m=[width,length],
        estimated_area_m2=width*length,large_room_scale_warning=width*length>30,
        supported_relation_checks=support_checks,issues=issues,
        observed_position_support_status='PASS' if not issues else 'FAIL',
        full_photo_reconstruction='NOT_ACCEPTED',
        uncovered_relations=['hanging clothing attachment','open door hinge','bedding attachment',
                             'uncertain small floor objects','hidden surfaces'])


def support_contract_probe(payload):
    """Controlled local change only: can the existing executor represent a top box?"""
    original_hash=canonical_sha256(payload)
    candidate=deepcopy(payload)
    calls={c['arguments'].get('id'):c for c in candidate['calls']}
    parent=calls['wardrobe']['arguments'];support=next(o for o in expand_furniture(parent) if o.id=='wardrobe_body')
    child=calls['top_storage']['arguments'];sz=child['dimensions_m'][2]
    child['position_m']=[*support.transform.position_m[:2],support.transform.position_m[2]+support.shape.dimensions_m[2]/2+sz/2]
    before=facts(payload);after=facts(candidate)
    try:
        execute_site_tool_plan(SiteToolPlan.from_dict(candidate),source='photo',source_ref=PHOTO_SHA256)
        status='ACCEPTED'
        error=None
    except ValueError as failure:
        status='REJECTED';error=str(failure)[:400]
    return dict(source='controlled_local_support_probe_NOT_LLM',executor_status=status,error=error,
        before_top_storage=before['supported_relation_checks'][0],after_top_storage=after['supported_relation_checks'][0],
        original_unchanged=canonical_sha256(payload)==original_hash)


def semantic_negative(job):
    """A valid result with known geometry defects and no repair is a false negative."""
    quality=job.get('quality')
    repairs=job['diagnostics'].get('repair_count')
    reproduced=(job['status']=='CONTRACT_VALIDATED' and quality is not None
        and quality['observed_position_support_status']=='FAIL' and repairs==0)
    return dict(reproduced=reproduced,product_repair_count=repairs,
        production_detected_quality_failure=False if reproduced else None,quality=quality)


def require_settled_dispatches(ledger, attempt_ids):
    """Do not proceed to another paid experiment after an unknown outcome."""
    if ledger.lock_path.exists():raise ValueError('DISPATCH_OUTCOME_PENDING_STOP_NO_RETRY')
    rows={row['attempt_id']:row for row in ledger.state['requests']}
    for identity in attempt_ids:
        row=rows.get(identity)
        if not row or not row.get('finished_at') or row['status']=='outcome_unknown':
            raise ValueError('DISPATCH_OUTCOME_UNKNOWN_STOP_NO_RETRY')


def review_body(photo, payload, model):
    schema=dict(type='object',additionalProperties=False,required=['verdict','scale','issues','summary'],
        properties=dict(verdict=dict(enum=['reject','uncertain','accept_estimated']),
            scale=dict(enum=['unmeasured','implausible_estimate']),
            issues=dict(type='array',maxItems=8,items=dict(type='object',additionalProperties=False,
                required=['object_id','axis','detail'],properties=dict(object_id=dict(type='string',maxLength=40),
                    axis=dict(enum=['region','support','scale','unknown']),detail=dict(type='string',maxLength=180)))),
            summary=dict(type='string',maxLength=240)))
    objects=[dict(c.arguments) for c in SiteToolPlan.from_dict(payload).calls
        if c.tool in {'place_furniture','place_room_item'}]
    floor=next(c['arguments'] for c in payload['calls'] if c['tool']=='create_floor')
    text=json.dumps(dict(candidate_floor=floor,candidate_objects=objects),ensure_ascii=False,separators=(',',':'))
    return dict(model=model,temperature=0,max_tokens=1800,
        response_format=dict(type='json_schema',json_schema=dict(name='twinpulse_photo_quality_review',strict=True,schema=schema)),
        messages=[dict(role='system',content=
            'Review the supplied original bedroom photo against a candidate 3D geometry listing, not a rendered image. '
            'Coordinates: x negative=left of entry, x positive=right, y positive=rear, z=height. '
            'Furniture centre_m is its floor footprint centre; room-item position_m is the geometric centre, not bottom. '
            'Catalogue bed=1.4x2m, wardrobe=1.2x.6m height1.9m, desk=1.2x.6m top surface .74m. '
            'Check left/right/front/rear and whether upper objects actually rest on their parent in XY and Z. '
            'Do NOT accept merely because all objects exist or because the candidate says it is approximate. '
            'No measured dimensions are available: metric scale can NEVER be verified from this single photo. '
            'Identify uncertain hidden objects rather than inventing evidence. Use concise English. No commands or authority.'),
            dict(role='user',content=[dict(type='text',text=text),dict(type='image_url',image_url=dict(
                url='data:image/jpeg;base64,'+base64.b64encode(photo).decode('ascii'),detail='auto'))])])


def validate_review(completion, expected_model):
    if completion.model_id!=expected_model or completion.finish_reason!='stop':raise ValueError('REVIEW_IDENTITY_OR_FINISH')
    value=json.loads(completion.content)
    if (not isinstance(value,dict) or set(value)!={'verdict','scale','issues','summary'}
            or value['verdict'] not in {'reject','uncertain','accept_estimated'}
            or value['scale'] not in {'unmeasured','implausible_estimate'}
            or not isinstance(value['summary'],str) or len(value['summary'])>240
            or not isinstance(value['issues'],list) or len(value['issues'])>8):raise ValueError('REVIEW_SHAPE')
    for issue in value['issues']:
        if (not isinstance(issue,dict) or set(issue)!={'object_id','axis','detail'}
                or issue['axis'] not in {'region','support','scale','unknown'}
                or not isinstance(issue['object_id'],str) or len(issue['object_id'])>40
                or not isinstance(issue['detail'],str) or len(issue['detail'])>180):raise ValueError('REVIEW_ISSUE_SHAPE')
    return value


class EvaluatedTransport:
    def __init__(self, real, campaign, evidence_root, observer_id, planner_completion=None, feedback=None):
        self.real=real;self.observer=ExactAuditedResponses(campaign,evidence_root,[observer_id])
        self.seed=planner_completion;self.feedback=feedback;self.injected=False

    async def complete(self,body,token,config):
        if body['response_format']['json_schema']['name']=='twinpulse_image_observation':
            return await self.observer.complete(body,token,config)
        if self.seed is not None and not self.injected:
            self.injected=True
            bad=json.loads(self.seed.content);bad['objects']['bed']['region']='controlled_invalid_region'
            return replace(self.seed,response_id='controlled-invalid-region',attempt_id=None,content=json.dumps(bad))
        if self.feedback:
            body={**body,'messages':[*body['messages'],
                dict(role='assistant',content=json.dumps(self.feedback['candidate_layout'],separators=(',',':'))),
                dict(role='user',content=json.dumps(dict(
                    quality_feedback=self.feedback['review'],geometry_checks=self.feedback['facts'],
                    correction='Return a complete corrected SAME photo-layout-1.1 JSON. Correct the photo-side and scale estimates where possible. Preserve every inventory ID. Do not invent support fields, measurements, authority, or omit difficult items. If this schema cannot express support/attachment, say that limitation in the summary.'),separators=(',',':'))) ]}
        return await self.real.complete(body,token,config)


async def evaluate(args):
    from twinpulse_app import JsonProviderSettingsStore,WindowsCredentialStore
    from twinpulse_provider.reliability import CampaignLedger,InferenceEvidence,AuditedChatTransport,utc_now
    from packages.twinpulse_provider.tests.test_nebius_pipeline import config
    if not args.live:raise SystemExit('Explicit --live required; no inference performed')
    root=args.source_run.resolve();draft,evidence_root,ids=live_run_inputs(root)
    photo=args.photo.read_bytes()
    if hashlib.sha256(photo).hexdigest()!=PHOTO_SHA256:raise ValueError('Only approved P01 source photo supported')
    settings=JsonProviderSettingsStore(root/'runtime/provider_settings.json').load().validated()
    saved=json.loads(args.campaign.read_text(encoding='utf-8'))
    ledger=CampaignLedger(args.campaign,approval=saved['approval'],rates=saved['rates'])
    start_count=len(ledger.state['requests'])
    allowance=min(7,10,ledger.state['max_requests']-start_count)
    if allowance<4:raise ValueError('Insufficient original campaign allowance; no new campaign/reset')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    credential=WindowsCredentialStore(settings.credential_ref)
    transport=AuditedChatTransport(credential.load,InferenceEvidence(output/'responses'),ledger)
    class Budget:
        async def complete(self,body,token,cfg):
            if len(transport.calls)>=allowance:raise ValueError('LOCAL_PHOTO_REVIEW_CALL_CAP')
            return await transport.complete(body,token,cfg)
    real=Budget()
    request=GenerationRequest('quality-loop-P01',draft.input_revision.prompt,
        (ImageInput(draft.input_revision.images[0]['name'],'image/jpeg',photo),))
    originals={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [root/'runtime/active_project.json',root/'result.json',*evidence_root.glob('*.json')]}
    source_paths=['packages/twinpulse_provider/src/twinpulse_provider/'+name for name in
        ('nebius_pipeline.py','photo_layout.py','service.py','reliability.py')]+[
        'packages/twinpulse_core/src/twinpulse_core/furniture.py','packages/twinpulse_core/src/twinpulse_core/room_items.py']
    report=dict(status='IN_PROGRESS',scope='P01_assisted_test_not_product_quality_gate',
        product_quality_gate_implemented=False,metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS',
        source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_paths},
        whole_demo_ready=False,robot_connections=0,isaac_this_increment='NOT_RUN',jobs=[],started_at=utc_now())
    def save():
        report['new_attempt_ids']=transport.calls
        (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    async def generate(name,adapter_transport,max_repairs=1):
        provider=NebiusChatCompletionsPipelineProvider(adapter_transport,observer_model_id=settings.observer_model_id,
            planner_model_id=settings.model_id,site_plan_version='2.2',max_repairs=max_repairs,compact_photo_layout=True)
        started=time.monotonic();job=dict(name=name,status='FAIL');before=len(transport.calls)
        try:
            result=await GenerationService(provider,config(timeout_s=90.),plan_version='2.2').generate(request)
            job.update(status='CONTRACT_VALIDATED',plan_sha256=canonical_sha256(result.plan.to_dict()),
                quality=facts(result.plan.to_dict()))
            (output/(name+'-plan.json')).write_text(json.dumps(result.plan.to_dict(),indent=2),encoding='utf-8')
        except Exception as error:
            result=None;job.update(error_type=type(error).__name__,error=str(error)[:600])
        job.update(elapsed_s=round(time.monotonic()-started,3),diagnostics=provider.diagnostic_for(request.request_id),
            new_attempt_ids=transport.calls[before:])
        report['jobs'].append(job);save();print(name+': '+job['status'],flush=True)
        return result,job
    async def critic(name,payload):
        before=len(transport.calls);started=time.monotonic();token=CancellationToken()
        job=dict(name=name,status='FAIL',scope='photo_and_geometry_JSON_NOT_render')
        try:
            completion=await asyncio.wait_for(real.complete(review_body(photo,payload,settings.observer_model_id),token,config(timeout_s=90.)),90.)
            job.update(status='REVIEWED',review=validate_review(completion,settings.observer_model_id),attempt_id=completion.attempt_id)
        except Exception as error:
            token.cancel();job.update(error_type=type(error).__name__,error=str(error)[:600])
        job.update(elapsed_s=round(time.monotonic()-started,3),new_attempt_ids=transport.calls[before:])
        report['jobs'].append(job);save();print(name+': '+job['status'],flush=True)
        return job
    try:
        exact=ExactAuditedResponses(args.campaign,evidence_root,ids)
        baseline,baseline_job=await generate('saved_actual_negative',exact)
        report['semantic_negative']=semantic_negative(baseline_job)
        if not report['semantic_negative']['reproduced']:
            raise ValueError('SAVED_SEMANTIC_NEGATIVE_NOT_REPRODUCED_STOP')
        report['support_contract_probe']=support_contract_probe(draft.plan.to_dict())
        save()
        fresh,fresh_job=await generate('fresh_planner',EvaluatedTransport(real,args.campaign,evidence_root,ids[0]))
        # A pending/unknown dispatch must never be followed by another paid call.
        require_settled_dispatches(ledger,fresh_job['new_attempt_ids'])
        if fresh_job.get('error_type') in {'ProviderTimeoutError','TimeoutError','GenerationCancelledError'}:
            raise ValueError('FRESH_GENERATION_TIMEOUT_STOP_NO_RETRY')
        seed=ExactAuditedResponses(args.campaign,evidence_root,[ids[1]]).entries[0][1]
        controlled,controlled_job=await generate('controlled_region_repair',EvaluatedTransport(
            real,args.campaign,evidence_root,ids[0],planner_completion=seed))
        controlled_job['first_candidate_source']='CONTROLLED_MUTATION_OF_PREVIOUS_REAL_RESPONSE_NOT_FRESH_MODEL_FAILURE'
        controlled_job['count_in_model_success_rate']=False
        save()
        require_settled_dispatches(ledger,controlled_job['new_attempt_ids'])
        if controlled_job.get('error_type') in {'ProviderTimeoutError','TimeoutError','GenerationCancelledError'}:
            raise ValueError('CONTROLLED_GENERATION_TIMEOUT_STOP_NO_RETRY')
        reviewed=fresh.plan.to_dict() if fresh else draft.plan.to_dict()
        critique=await critic('independent_photo_critique',reviewed)
        require_settled_dispatches(ledger,critique['new_attempt_ids'])
        if critique['status']!='REVIEWED':raise ValueError('CRITIQUE_UNAVAILABLE_STOP')
        # Choose the actual layout corresponding to reviewed plan, not a hand-built correction.
        planner_ids=fresh_job['new_attempt_ids'] if fresh else []
        layout=json.loads(seed.content)
        if planner_ids:
            item=json.loads((output/'responses'/(planner_ids[-1]+'.json')).read_text(encoding='utf-8'))
            raw=json.loads(item['response_redacted']);layout=json.loads(raw['choices'][0]['message']['content'])
        feedback=dict(candidate_layout=layout,review=critique['review'],facts=facts(reviewed))
        corrected,corrected_job=await generate('quality_feedback_correction',EvaluatedTransport(
            real,args.campaign,evidence_root,ids[0],feedback=feedback),max_repairs=0)
        corrected_job['scope']='EXTERNAL_EVALUATOR_FEEDBACK_NOT_PRODUCT_AUTOMATIC_PHOTO_REVIEW'
        save()
        require_settled_dispatches(ledger,corrected_job['new_attempt_ids'])
        if corrected_job.get('error_type') in {'ProviderTimeoutError','TimeoutError','GenerationCancelledError'}:
            raise ValueError('CORRECTION_TIMEOUT_STOP_NO_RETRY')
        if corrected:
            await critic('post_correction_photo_critique',corrected.plan.to_dict())
        from twinpulse_provider.photo_layout import layout_schema
        from tests.fixtures.historical_room_photo_inventory import photo_reference
        schema=layout_schema(request.prompt,photo_reference(PHOTO_SHA256),None)
        slot_fields=list(schema['properties']['objects']['properties']['top_storage']['properties'])
        report['compact_support_representation']=dict(slot_fields=slot_fields,
            planner_cannot_set_parent_or_height=set(slot_fields)=={'region','yaw_deg','observation_ids'},
            executor_probe=report['support_contract_probe']['executor_status'])
        report.update(status='COMPLETED_WITH_QUALITY_GAPS',stop_reason=(
            'REGION_ONLY_COMPILER_DOES_NOT_RECONSTRUCT_SUPPORT' if report['compact_support_representation']['planner_cannot_set_parent_or_height']
            else 'BOUNDED_EVALUATION_FINISHED'),
            repeated_same_impossible_support_requests=False,
            product_fidelity_loop_acceptance='FAIL_NOT_CONNECTED',source_unchanged=all(
                hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==d for p,d in report['source_hashes'].items()))
    except Exception as error:
        report.update(status='STOPPED_WITH_DIAGNOSTICS',error_type=type(error).__name__,error=str(error)[:600])
    finally:
        deadline=time.monotonic()+95
        while ledger.lock_path.exists() and time.monotonic()<deadline:await asyncio.sleep(.5)
        end=json.loads(args.campaign.read_text(encoding='utf-8'))
        report.update(finished_at=utc_now(),new_calls=len(end['requests'])-start_count,
            source_unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==d for p,d in report['source_hashes'].items()),
            original_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in originals.items()),
            request_count=len(end['requests']),max_requests=end['max_requests'],
            estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in end['requests']),Decimal(0))),
            invoice_verified=False,pending_dispatches=len([r for r in end['requests'] if not r.get('finished_at')]))
        save();print('PHOTO_QUALITY_LOOP='+report['status'],flush=True)


async def offline_evaluate(args):
    """Exact prior evidence and controlled stored responses; NEVER live success."""
    from twinpulse_app import JsonProviderSettingsStore
    from packages.twinpulse_provider.tests.test_nebius_pipeline import config
    from twinpulse_provider.photo_layout import layout_schema
    from tests.fixtures.historical_room_photo_inventory import photo_reference
    root=args.source_run.resolve();draft,evidence_root,ids=live_run_inputs(root)
    photo=args.photo.read_bytes()
    if hashlib.sha256(photo).hexdigest()!=PHOTO_SHA256:raise ValueError('P01 source hash mismatch')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    settings=JsonProviderSettingsStore(root/'runtime/provider_settings.json').load().validated()
    request=GenerationRequest('quality-loop-P01',draft.input_revision.prompt,
        (ImageInput(draft.input_revision.images[0]['name'],'image/jpeg',photo),))
    paths=[root/'runtime/active_project.json',root/'result.json',args.campaign,*evidence_root.glob('*.json')]
    original_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    source_paths=[ROOT/'packages/twinpulse_provider/src/twinpulse_provider'/n for n in
        ('nebius_pipeline.py','photo_layout.py','service.py','reliability.py')]+[
        ROOT/'packages/twinpulse_core/src/twinpulse_core/furniture.py',ROOT/'packages/twinpulse_core/src/twinpulse_core/room_items.py']
    source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    report=dict(scope='OFFLINE_EXACT_EVIDENCE_AND_CONTROLLED_STORED_RESPONSES',new_calls=0,
        live_photo_review='BLOCKED_BY_APPROVAL_REVIEW_NOT_RUN',robot_connections=0,isaac_this_increment='NOT_RUN',
        product_quality_gate_implemented=False,whole_demo_ready=False,jobs=[])
    async def generate(name,transport):
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=settings.observer_model_id,
            planner_model_id=settings.model_id,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        result=await GenerationService(provider,config(timeout_s=90.),plan_version='2.2').generate(request)
        job=dict(name=name,status='CONTRACT_VALIDATED',diagnostics=provider.diagnostic_for(request.request_id),
            plan_sha256=canonical_sha256(result.plan.to_dict()),quality=facts(result.plan.to_dict()))
        report['jobs'].append(job)
        (output/(name+'-plan.json')).write_text(json.dumps(result.plan.to_dict(),indent=2),encoding='utf-8')
        return result,job
    baseline,job=await generate('saved_actual_negative',ExactAuditedResponses(args.campaign,evidence_root,ids))
    report['semantic_negative']=semantic_negative(job)
    report['support_contract_probe']=support_contract_probe(baseline.plan.to_dict())
    seed=ExactAuditedResponses(args.campaign,evidence_root,[ids[1]]).entries[0][1]
    class StoredRepair:
        calls=0
        async def complete(self,body,token,cfg):
            if token.is_cancelled or self.calls:raise ValueError('Offline response exhausted; no fallback')
            if 'SLOT_SHAPE_INVALID' not in body['messages'][-1]['content'] and 'OBJECT_INVALID' not in body['messages'][-1]['content']:
                raise ValueError('Expected precise injected region error')
            self.calls+=1
            report['controlled_repair_prompt']=dict(error=body['messages'][-1]['content'],
                schema_sha256=canonical_sha256(body['response_format']),
                previous_candidate_present=body['messages'][-2]['role']=='assistant')
            return replace(seed,response_id='offline-stored-repair',attempt_id=None)
    stored=StoredRepair()
    fixed,fixed_job=await generate('controlled_region_stored_repair',EvaluatedTransport(
        stored,args.campaign,evidence_root,ids[0],planner_completion=seed))
    fixed_job['response_source']='STORED_PRIOR_VALID_RESPONSE_NOT_ACTUAL_MODEL_CORRECTION'
    fixed_job['count_in_model_success_rate']=False
    report['controlled_existing_repair_mechanics']=dict(passed=stored.calls==1 and
        fixed_job['diagnostics']['repair_count']==1 and fixed.plan.to_dict()==baseline.plan.to_dict(),
        actual_model_correction='NOT_RUN')
    fields=list(layout_schema(request.prompt,photo_reference(PHOTO_SHA256))['properties']['objects']['properties']['top_storage']['properties'])
    report['compact_support_representation']=dict(slot_fields=fields,
        planner_cannot_set_parent_or_height=set(fields)=={'region','yaw_deg','observation_ids'},
        compiler_support_status=fixed.provider_provenance['photo_layout_compiler']['placement_relationships'])
    report.update(status='OFFLINE_COMPLETE_PRODUCT_FIDELITY_FAIL',
        original_evidence_and_campaign_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in original_hashes.items()),
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source_hashes.items()),
        source_hashes=source_hashes,original_hashes=original_hashes)
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','new_calls','semantic_negative','support_contract_probe',
        'controlled_existing_repair_mechanics','compact_support_representation','original_evidence_and_campaign_unchanged','source_unchanged')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--source-run',type=Path,required=True)
    parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--photo',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--live',action='store_true');mode.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    asyncio.run(offline_evaluate(args) if args.offline else evaluate(args))
