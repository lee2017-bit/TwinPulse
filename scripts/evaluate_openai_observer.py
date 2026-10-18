# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit two-attempt photo observation comparison, not a product adapter.

Requires human approval for the photo/OpenAI destination. No robot, planner,
deployment, model-generated code execution or automatic transport retries.
"""
import argparse
import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_provider import GenerationRequest,ImageInput,CancellationToken,ProviderConfig,ProviderCapabilities
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider,ObservationArtifact
from twinpulse_provider.reliability import CampaignLedger,AuditedChatTransport,InferenceEvidence,safe_text,utc_now
from twinpulse_provider.errors import ProviderConfigurationError,InvalidProviderResponseError

PHOTO_SHA='ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8'
MODEL='gpt-5.4-mini'
ORIGIN='https://api.openai.com/v1/'
PROMPT='Create a digital twin of my bedroom with a bed and desk.'

def write_new(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())

def wire_body(original):
    """Only API-compatible keywords/types; no changed observation semantics."""
    body=deepcopy(original)
    body['max_completion_tokens']=body.pop('max_tokens')
    body.pop('temperature',None)  # low reasoning models reject temperature overrides
    body['reasoning_effort']='low'
    def types(node):
        if isinstance(node,dict):
            if 'const' in node:node['enum']=[node.pop('const')];node.setdefault('type','string')
            if 'enum' in node:node.setdefault('type','string')
            for value in node.values():types(value)
        elif isinstance(node,list):
            for value in node:types(value)
    types(body['response_format'])
    return body

class BoundedPhotoLedger(CampaignLedger):
    """Request-specific conservative byte/patch reservation, not guessed size.

Text token count <= UTF-8 byte count, plus 4096 framing tokens (<=4 messages).
One GPT-5.4-mini image: <=30,000 patches *1.2 per official image guide.
Model context remains recorded at400k; this does NOT rewrite Nebius accounting.
"""
    @staticmethod
    def input_bound(body):
        text=deepcopy(body);images=0
        messages=text.get('messages')
        if not isinstance(messages,list) or not 1<=len(messages)<=4:
            raise ProviderConfigurationError('Bounded comparison supports up to four messages')
        for message in messages:
            content=message.get('content')
            if isinstance(content,list):
                for part in content:
                    if part.get('type')=='image_url':
                        images+=1
                        url=part.get('image_url',{}).get('url','')
                        if not url.startswith('data:image/jpeg;base64,'):
                            raise ProviderConfigurationError('Only the approved embedded JPEG is supported')
                        part['image_url']['url']='[APPROVED_IMAGE_NOT_SAVED]'
                    elif part.get('type')!='text':
                        raise ProviderConfigurationError('Unsupported input modality')
        if images!=1:raise ProviderConfigurationError('Exactly one approved image is required')
        return len(json.dumps(text,ensure_ascii=False).encode('utf-8'))+4096+36000

    def reserve(self,body):
        with self._lock:
            identity=uuid4().hex
            try:
                fd=os.open(self.lock_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            except FileExistsError:
                raise ProviderConfigurationError('Comparison has an in-flight attempt; no retry') from None
            with os.fdopen(fd,'w') as stream:
                json.dump({'owner_pid':os.getpid(),'attempt_id':identity},stream)
                stream.flush();os.fsync(stream.fileno())
            try:
                self.state=json.loads(self.path.read_text(encoding='utf-8'))
                rate=self.state['rates'].get(body.get('model'))
                maximum=body.get('max_completion_tokens');bound=self.input_bound(body)
                if body.get('model')!=MODEL or type(maximum)is not int or not 1<=maximum<=10000 or not rate:
                    raise ProviderConfigurationError('Comparison model/output cap mismatch')
                if bound+maximum>rate['context_tokens']:
                    raise ProviderConfigurationError('Comparison context bound exceeded')
                reserved=(Decimal(rate['input_per_million'])*bound+Decimal(rate['output_per_million'])*maximum)/1000000
                spent=sum(Decimal(row['charged_or_reserved_usd']) for row in self.state['requests'])
                if len(self.state['requests'])>=2 or spent+reserved>Decimal(self.state['limit_usd']):
                    raise ProviderConfigurationError('Two-call/USD0.15 comparison limit reached')
                self.state['requests'].append({'attempt_id':identity,'model_id':MODEL,'started_at':utc_now(),
                    'status':'outcome_unknown','max_tokens':maximum,'input_token_bound':bound,
                    'reservation_policy':'utf8_bytes_plus4096_framing_plus36000_image_tokens',
                    'reserved_usd':str(reserved),'charged_or_reserved_usd':str(reserved)})
                self._write()
                return identity
            except BaseException:
                self.lock_path.unlink(missing_ok=True)
                raise

async def evaluate(args):
    store=JsonProviderSettingsStore();settings=store.load().validated()
    if (settings.provider_profile!='openai' or settings.base_url!=ORIGIN or settings.model_id!=MODEL
            or settings.reasoning_effort!='low'):
        raise ProviderConfigurationError('Select the registered OpenAI/gpt-5.4-mini/low key first')
    credential=KeyRegistry(store,WindowsCredentialStore()).resolve(settings)
    if not credential.is_configured():raise ProviderConfigurationError('Selected secure key is missing')
    photo=args.photo.read_bytes()
    if hashlib.sha256(photo).hexdigest()!=PHOTO_SHA:
        raise ProviderConfigurationError('Photo differs from the approved source')
    args.output.mkdir(parents=True,exist_ok=False)
    rate={'input_per_million':'0.75','output_per_million':'4.50','context_tokens':400000,
        'source':'https://developers.openai.com/api/docs/models/gpt-5.4-mini','verified_at':utc_now()}
    approval='User approved OpenAI comparison, registered key and confirmed Use this key; existing bedroom photo; max2 calls/USD0.15; no robot'
    write_new(args.output/'approval.json',{'approval':approval,'created_at':utc_now(),'photo_sha256':PHOTO_SHA,
        'model_id':MODEL,'origin':ORIGIN,'max_requests':2,'limit_usd':'0.15','timeout_s':120,
        'rates':rate,'image_bound_source':'https://developers.openai.com/api/docs/guides/images-vision',
        'default_provider_unchanged_by_evaluation':True,'is_diagnostic_not_product_adapter':True})
    ledger=BoundedPhotoLedger(args.output/'campaign.json',approval=approval,rates={MODEL:rate},limit_usd='0.15',max_requests=2)
    transport=AuditedChatTransport(credential.load,InferenceEvidence(args.output/'responses'),ledger)
    builder=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=MODEL,
        planner_model_id='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',site_plan_version='2.2',output_token_cap=10000)
    request=GenerationRequest('openai-observer-comparison',PROMPT,(ImageInput('approved-bedroom.jpg','image/jpeg',photo),))
    original=builder.build_observer_body(request)
    body=wire_body(original)
    schema=body['response_format']['json_schema']['schema']
    write_new(args.output/'request-metadata.json',{'original_schema_sha256':hashlib.sha256(json.dumps(original['response_format'],sort_keys=True).encode()).hexdigest(),
        'wire_schema_sha256':hashlib.sha256(json.dumps(body['response_format'],sort_keys=True).encode()).hexdigest(),
        'schema':schema,'prompt':PROMPT,'system_prompt':body['messages'][0]['content'],
        'api_keyword_changes':['max_tokens→max_completion_tokens','temperature removed','reasoning_effort=low','const→singleton enum; explicit string types'],
        'input_images_saved':False,'input_token_bound':ledger.input_bound(body)})
    config=ProviderConfig(base_url=ORIGIN,endpoint_path='chat/completions',model_id=MODEL,
        api_key_env='UNUSED_SECURE_STORE',capabilities=ProviderCapabilities(True,True,1,('image/jpeg',)),timeout_s=120,max_attempts=1)
    token=CancellationToken();rows=[];started=time.monotonic();observation=None
    try:
        for index in range(2):
            before=time.monotonic();completion=None
            try:
                completion=await transport.complete(body,token,config)
                if completion.model_id not in {MODEL,'gpt-5.4-mini-2026-03-17'}:
                    raise InvalidProviderResponseError('Response model identity changed')
                candidate=ObservationArtifact.from_mapping(json.loads(completion.content))
                if not candidate.entities:
                    raise InvalidProviderResponseError('Observation contains no visible entities')
                observation=candidate
                rows.append({'attempt':index+1,'status':'OBSERVATION_VALIDATED','elapsed_s':round(time.monotonic()-before,3),
                    'attempt_id':completion.attempt_id,'response_model_id':completion.model_id,
                    'finish_reason':completion.finish_reason,'usage':dict(completion.usage)})
                write_new(args.output/'observation.json',observation.to_dict())
                break
            except Exception as error:
                rows.append({'attempt':index+1,'status':'FAIL','elapsed_s':round(time.monotonic()-before,3),
                    'error_type':type(error).__name__,'code':getattr(error,'code',None),
                    'error':safe_text(str(error),limit=500),'attempt_id':getattr(error,'attempt_id',None) or (completion.attempt_id if completion else None)})
                if (index or completion is None or completion.model_id not in {MODEL,'gpt-5.4-mini-2026-03-17'}
                        or not isinstance(error,(InvalidProviderResponseError,ValueError))):break
                # One bounded content repair; no transport/auth/timeout retry.
                body=deepcopy(body)
                body['messages'].extend([{'role':'assistant','content':completion.content},
                    {'role':'user','content':'Your observation failed the existing validator: '+safe_text(str(error),limit=400)+
                     '. Correct the complete JSON instance using the unchanged schema. Do not emit schema definitions or new unobserved objects.'}])
    finally:
        token.cancel()
        state=json.loads(ledger.path.read_text(encoding='utf-8'))
        summary={'status':'OBSERVATION_VALIDATED' if observation else 'FAIL','rows':rows,
            'elapsed_s':round(time.monotonic()-started,3),'calls_used':len(state['requests']),
            'estimated_plus_reserved_usd':str(sum(Decimal(x['charged_or_reserved_usd']) for x in state['requests'])),
            'pending':sum(not x.get('finished_at') for x in state['requests']),'dispatch_lock':ledger.lock_path.exists(),
            'entities':len(observation.entities) if observation else 0,'relations':len(observation.relations) if observation else 0,
            'dimensions':len(observation.dimensions) if observation else 0,'invoice_verified':False,
            'metric_accuracy':'UNVERIFIED','planner':'NOT_RUN','actual_isaac':'NOT_RUN','robot_calls':0,'whole_demo_pass':False}
        write_new(args.output/'summary.json',summary)
        print(json.dumps(summary),flush=True)
    return 0 if observation else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--photo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(asyncio.run(evaluate(args)))
