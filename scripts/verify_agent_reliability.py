# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit sequential live campaign. Never connects to a robot or silently mocks.

--live uses an already approved campaign; the durable ledger owns the unchanged
USD 1 budget and validates any recorded human extensions of the original60 cap.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

from twinpulse_app import JsonProviderSettingsStore, WindowsCredentialStore
from twinpulse_provider import GenerationRequest, ImageInput, GenerationService, ProviderCapabilities, ProviderConfig
from twinpulse_provider.nebius_pipeline import (NebiusChatCompletionsPipelineProvider, UrllibChatCompletionsTransport,
    parse_chat_completion, ObservationArtifact, observation_json_schema)
from twinpulse_provider.reliability import CampaignLedger, InferenceEvidence, AuditedChatTransport, utc_now
from twinpulse_core import execute_site_tool_plan

APPROVAL = '2026-10-07 user: 그래 진행시작하자; H0-H6 USD1 max60'
NANO = 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
RATES = {NANO: dict(input_per_million='0.06', output_per_million='0.24', context_tokens=262144,
                   source='https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference',
                   verified_at='2026-10-07')}


class ReuseExactAuditedObserver:
    """Explicit evaluation-only reuse of one real response, not a fixture.

    Match the exact current observer request/schema hash and ledger identity;
    never read an unrelated image result or permit a second use. No network is
    sent for this observer. The ordinary provider still validates its content.
    """
    def __init__(self, transport, ledger, evidence_root, attempt_id):
        import re
        if not re.fullmatch(r'[a-f0-9]{32}',attempt_id):
            raise ValueError('Reuse requires one audited attempt identity')
        path=evidence_root/(attempt_id+'.json')
        self.evidence=json.loads(path.read_text(encoding='utf-8'))
        rows=[r for r in ledger.state['requests'] if r['attempt_id']==attempt_id]
        if (len(rows)!=1 or not rows[0].get('finished_at') or rows[0]['status']!='received'
                or self.evidence.get('status')!='received' or self.evidence.get('http_status')!=200
                or self.evidence.get('response_truncated')):
            raise ValueError('Reuse requires a completed successful actual observer dispatch')
        raw=self.evidence.get('response_redacted','').encode('utf-8')
        if (self.evidence.get('attempt_id')!=attempt_id
                or self.evidence.get('model_id')!=rows[0]['model_id']
                or hashlib.sha256(raw).hexdigest()!=self.evidence.get('response_sha256')
                or len(raw)!=self.evidence.get('response_byte_count')):
            # Only exact captured bytes may be reused. Truncated/redacted/tampered
            # content is useful for diagnosis but not an inference substitute.
            raise ValueError('Reused evidence identity or exact captured hash mismatch')
        self.completion=parse_chat_completion(json.loads(self.evidence['response_redacted']))
        if self.completion.model_id!=self.evidence['model_id']:
            raise ValueError('Reused model mismatch')
        ObservationArtifact.from_mapping(json.loads(self.completion.content))
        self.transport=transport;self.used=False;self.attempt_id=attempt_id
        self.evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest()

    async def complete(self,body,token,config):
        if not self.used:
            if token.is_cancelled:raise ValueError('Cancelled observer cannot be reused')
            request_sha=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
            schema_sha=hashlib.sha256(json.dumps(body['response_format'],sort_keys=True).encode()).hexdigest()
            allowed=[dict(type='json_schema',json_schema=dict(name='twinpulse_image_observation',
                strict=True,schema=observation_json_schema(version))) for version in ('1.0','1.1','1.2')]
            if (body.get('response_format') not in allowed or request_sha!=self.evidence['request_sha256']
                    or schema_sha!=self.evidence['schema_sha256']
                    or body['model']!=self.completion.model_id):
                raise ValueError('Reused observer does not match this exact photo/prompt/model/schema')
            self.used=True
            from dataclasses import replace
            return replace(self.completion,attempt_id=self.attempt_id)
        return await self.transport.complete(body,token,config)


async def run(args):
    if not args.live:
        raise SystemExit('No inference performed. Explicit --live is required.')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    settings=JsonProviderSettingsStore().load().validated()
    credential=WindowsCredentialStore(settings.credential_ref)
    existing_rates=json.loads(args.campaign.read_text(encoding='utf-8'))['rates'] if args.campaign.exists() else RATES
    ledger=(CampaignLedger.open_existing_approved(args.campaign,run_request_cap=5)
            if args.campaign.exists() else CampaignLedger(args.campaign,approval=APPROVAL,rates=existing_rates))
    if args.inspect_abandoned_owned_run:
        run_root=args.inspect_abandoned_owned_run.resolve()
        result_file=run_root/'result.json'
        prior=json.loads(result_file.read_text(encoding='utf-8'))
        if prior.get('provider')!='live_configured_provider' or prior.get('supervisor',{}).get('phase')!='stopped':
            raise SystemExit('Not a completed owned live acceptance run')
        receipts=list((run_root/'runtime/launches').glob('*/backend-ready.json'))
        if len(receipts)!=1:raise SystemExit('Exactly one owned backend receipt is required')
        ready=json.loads(receipts[0].read_text(encoding='utf-8'))
        pending=[r for r in ledger.state['requests'] if not r.get('finished_at')]
        if len(pending)!=1:raise SystemExit('Exactly one outstanding dispatch is required')
        # Explicit local reconciliation, no inference or lost-result replay.
        ledger.acknowledge_abandoned(pending[0]['attempt_id'],owner_pid=ready['pid'],
            evidence_ref=str(result_file)+'#sha256='+hashlib.sha256(result_file.read_bytes()).hexdigest())
        print('LOCAL_OWNER_EXITED; remote completion/billing UNKNOWN; full reservation retained',flush=True)
        return 0
    if args.verify_pricing_only:
        # Read-only endpoint used by the official model catalogue UI. No inference.
        url='https://api.tokenfactory.nebius.com/private/v1/models_info'
        from twinpulse_provider.nebius_pipeline import _RejectRedirects
        key=credential.load()
        if not key:raise SystemExit('Existing credential is not configured')
        response=urllib.request.build_opener(_RejectRedirects()).open(
            urllib.request.Request(url,headers={'Authorization':'Bearer '+key}),timeout=20)
        with response:raw=response.read(2_000_001)
        key=None
        if len(raw)>2_000_000:raise SystemExit('Pricing metadata exceeds bound')
        rows=json.loads(raw)
        checked=[]
        for model_id in (settings.observer_model_id,settings.model_id):
            selected=[f for r in rows for f in r.get('flavors',[]) if f.get('model_id')==model_id]
            if len(selected)!=1 or (model_id==settings.observer_model_id and 'image' not in selected[0].get('use_cases',[])):
                raise SystemExit('Exact existing model/capability not listed')
            metadata=selected[0]
            rate=dict(input_per_million=str(metadata['input_price_per_million_tokens']),
                output_per_million=str(metadata['output_price_per_million_tokens']),
                context_tokens=metadata['max_model_len'],source=url,verified_at=utc_now(),
                source_sha256=hashlib.sha256(raw).hexdigest())
            prior=ledger.state['rates'].get(model_id)
            if prior is not None:
                from decimal import Decimal
                if any(Decimal(prior[k])!=Decimal(rate[k]) for k in ('input_per_million','output_per_million')) or prior['context_tokens']!=rate['context_tokens']:
                    raise SystemExit('Existing campaign pricing differs; no inference or accounting rewrite')
            else:
                ledger.register_verified_rate(model_id,rate)
            checked.append(dict(model_id=model_id,rate=rate))
        (output/'pricing.json').write_text(json.dumps(dict(models=checked,inference_requests=0,
            prior_pricing_preserved=True),indent=2),encoding='utf-8')
        print('PRICING_VERIFIED exact observer and planner; no inference',flush=True)
        return 0
    transport=AuditedChatTransport(credential.load,InferenceEvidence(args.campaign.parent/'responses'),ledger)
    observer_reuse=None
    if args.reuse_audited_observer:
        if not args.compact_photo or not args.photo_only or args.repetitions!=1:
            raise SystemExit('Exact observer reuse requires one opt-in compact photo job')
        observer_reuse=ReuseExactAuditedObserver(transport,ledger,args.campaign.parent/'responses',args.reuse_audited_observer)
    report=dict(schema_version='agent-reliability-1.0',started_at=utc_now(),mode=args.phase,
                credential_configured=credential.is_configured(),robot_connections=0,
                output_policy='EXPERIMENTAL_template_off' if args.planner_template_no_thinking else
                    'EXPERIMENTAL_reasoning_none' if args.planner_no_thinking else
                    'EXPERIMENTAL_compact_photo_inventory_proxies' if args.compact_photo else 'UNCHANGED_default_thinking',
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT/'packages/twinpulse_provider/src/twinpulse_provider'/f
                              for f in ('nebius_pipeline.py','service.py','schema.py','photo_layout.py')]},jobs=[])
    if not report['credential_configured']:raise SystemExit('Existing credential is not configured')
    provider=NebiusChatCompletionsPipelineProvider(observer_reuse or transport,observer_model_id=settings.observer_model_id,
                planner_model_id=settings.model_id,site_plan_version='2.2',
                max_repairs=0 if args.phase=='baseline' or observer_reuse else 1,
                planner_reasoning_effort='none' if args.planner_no_thinking else None,
                planner_template_no_thinking=args.planner_template_no_thinking,
                compact_photo_layout=args.compact_photo)
    config=ProviderConfig(settings.base_url,settings.endpoint_path,settings.model_id,'NOT_READ_FROM_ENV',
        ProviderCapabilities(True,True,1,settings.accepted_mime_types),timeout_s=90.)
    service=GenerationService(provider,config,plan_version='2.2')
    cases=[('T01','Create an approximate small bedroom, 4 by 5 metres, with a bed, wardrobe, desk and chair. Select TurtleBot3 Burger for a short simulated preview. No measured dimensions or physical motion.',None)]
    if args.text_matrix:
        cases += [
            ('T02','Create an approximate living room, 6 by 7 metres, with sofa, dining_table and storage. No measured geometry or physical robot.',None),
            ('T03','한국 아파트 침실을 대략 4m x 5m로 만들고 침대, 옷장, 책상, 의자를 모두 넣어 주세요. 창고 랙은 넣지 마세요. 실측 치수는 아니며 물리 로봇 이동을 요청하지 않습니다.',None),
            ('T04','Create an approximate narrow 3 by 5 metre bedroom with bed and desk. Leave a conservative central passage. Do not claim physical clearance or measurements.',None)]
        cases=[(name+f'-r{n}',prompt,image) for name,prompt,image in cases for n in (1,2)]
    if args.photo:cases.append(('P01','Create an approximate Digital Twin of this bedroom with its visible furniture and floor hazards. Select TurtleBot3 Burger for SIM preview; geometry is unmeasured.',args.photo))
    if args.photo_only:
        if not args.photo:raise SystemExit('--photo-only requires --photo')
        cases=[case for case in cases if case[2] is not None]
    if args.case_id or args.prompt:
        if len(cases)!=1:raise SystemExit('Explicit case/prompt overrides require exactly one selected input')
        name,prompt,photo=cases[0]
        cases=[(args.case_id or name,args.prompt or prompt,photo)]
    if args.repetitions==2:
        cases=[(name+f'-r{n}',prompt,photo) for name,prompt,photo in cases for n in (1,2)]
    for name,prompt,photo in cases:
        item=dict(case=name,input_sha256=hashlib.sha256(prompt.encode()).hexdigest(),status='NOT_RUN',started_at=utc_now())
        if photo:
            from twinpulse_core.room_photo_inventory import photo_reference
            item['photo_sha256']=hashlib.sha256(photo.read_bytes()).hexdigest()
            reference=photo_reference(item['photo_sha256'])
            item['evaluation_mode']='ASSISTED_reviewed_inventory' if reference else 'VISUAL_only_no_reviewed_inventory'
            item['photo_geometry_accuracy']='NOT_MEASURED'
            if observer_reuse:
                item['observer_reuse']=dict(attempt_id=observer_reuse.attempt_id,
                    evidence_sha256=observer_reuse.evidence_sha256,mode='EXACT_PREVIOUS_REAL_RESPONSE',new_observer_dispatches=0,
                    additional_planner_repairs=0)
        if photo and settings.observer_model_id not in ledger.state['rates']:
            item.update(reason='Observer current official pricing/context not verified; no inference dispatched')
        else:
            request=GenerationRequest(args.phase+'-'+name,prompt,
                (ImageInput(photo.name,'image/jpeg',photo.read_bytes()),) if photo else ())
            before=len(transport.calls);started=time.monotonic()
            try:
                result=await service.generate(request)
                # Pure tool expansion is part of the product, not engine/physical acceptance.
                draft=execute_site_tool_plan(result.plan,source='manual' if photo is None else 'photo',
                                             source_ref=hashlib.sha256(prompt.encode()).hexdigest())
                (output/f'{name}-plan.json').write_text(json.dumps(result.plan.to_dict(),indent=2),encoding='utf-8')
                item.update(status='VALIDATED',scene_revision=draft.scene.revision,
                    provider_provenance=dict(result.provider_provenance))
            except Exception as error:
                item.update(status='FAIL',error_type=type(error).__name__,message=str(error)[:500],
                            diagnostics=getattr(error,'diagnostics',{}))
            item.update(elapsed_s=round(time.monotonic()-started,3),attempt_ids=transport.calls[before:])
            item['diagnostics']=provider.diagnostic_for(request.request_id)
        report['jobs'].append(item)
        (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(name+': '+item['status']+' '+item.get('message',item.get('reason','')),flush=True)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--campaign',required=True,type=Path)
    parser.add_argument('--phase',choices=('baseline','evaluation'),default='baseline')
    parser.add_argument('--photo',type=Path)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--text-matrix',action='store_true',help='Four independent text conditions x two live repetitions')
    parser.add_argument('--verify-pricing-only',action='store_true',help='Read official catalogue and add only the existing observer rate; no inference')
    parser.add_argument('--inspect-abandoned-owned-run',type=Path,help='Explicitly inspect one stopped owned live run; retain unknown charge, never retry it')
    parser.add_argument('--planner-no-thinking',action='store_true',help='Explicit exact-Nano Site2.2 policy probe: reasoning_effort none, unchanged output/deadline limits')
    parser.add_argument('--photo-only',action='store_true',help='Skip the text case for an explicitly selected photo evaluation')
    parser.add_argument('--planner-template-no-thinking',action='store_true',help='Exact-model explicit template probe via documented extra_body; no reasoning-to-content fallback')
    parser.add_argument('--compact-photo',action='store_true',help='Opt-in Site2.2 compact photo inventory-proxy experiment; not the production default or reconstructed geometry')
    parser.add_argument('--reuse-audited-observer',help='Explicit reuse of this exact real audited photo observer; only one planner call, repair disabled')
    parser.add_argument('--case-id',choices=('T01','T02','T03','T04','P01','P02','P03','P04'))
    parser.add_argument('--prompt',help='Explicit evaluation input; persisted only as a hash')
    parser.add_argument('--repetitions',type=int,choices=(1,2),default=1)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
