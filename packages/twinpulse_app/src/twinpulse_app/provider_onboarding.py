# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""First-key setup using fresh account metadata, never a price approval gate."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
import urllib.request
from uuid import uuid4
from .key_registry import KeyRegistryError
from .stage_routing import StageRoutingSettings,PHYSICAL_AI_OBSERVER,PHYSICAL_AI_PLANNER

class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('METADATA_REDIRECT_REFUSED')

def metadata(url,credential):
    if url not in ('https://api.tokenfactory.nebius.com/private/v1/models_info',
                   'https://api.tokenfactory.nebius.com/v1/models'):
        raise ValueError('METADATA_ORIGIN_INVALID')
    secret=credential.load()
    if not secret:raise ValueError('KEY_MISSING')
    request=urllib.request.Request(url,headers={'Authorization':'Bearer '+secret})
    with urllib.request.build_opener(RejectRedirects()).open(request,timeout=20) as response:
        if response.geturl()!=url:raise ValueError('METADATA_REDIRECT_REFUSED')
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('METADATA_SIZE_LIMIT')
    return json.loads(raw),hashlib.sha256(raw).hexdigest()

def configure_first_nebius_key(registry,key_id,changed,*,get=metadata):
    calls=0
    def counted(url,credential):
        nonlocal calls
        calls+=1
        return get(url,credential)
    try:return _configure_first_nebius_key(registry,key_id,changed,get=counted)
    except Exception as error:
        error.metadata_gets=calls
        raise

def _configure_first_nebius_key(registry,key_id,changed,*,get):
    """Known adapter + fresh visibility/modalities/context; quality is unverified.

    40k is the user's configured REQUEST ceiling, not a claim that metadata
    exposes a provider output maximum or proves every structured response.
    Actual generation errors remain typed and no inference probe is sent.
    """
    routes=StageRoutingSettings(registry)
    if routes.path.exists():raise KeyRegistryError('existing_route_preserved','기존 모델 설정은 자동 변경하지 않습니다.',409)
    settings=registry.settings_for_entry(key_id)
    if routes.provider(settings)!='nebius':raise KeyRegistryError('default_provider_unsupported','Nebius 기본 조합만 자동 설정합니다.')
    credential=registry.resolve(settings)
    info,source_sha=get('https://api.tokenfactory.nebius.com/private/v1/models_info',credential)
    account,_=get('https://api.tokenfactory.nebius.com/v1/models',credential)
    visible={r['id'] for r in account['data']};rows=[]
    for stage,model in (('observer',PHYSICAL_AI_OBSERVER),('planner',PHYSICAL_AI_PLANNER)):
        item=next((r for group in info for r in group.get('flavors',[]) if r.get('model_id')==model),None)
        if not item or model not in visible or not {'text',*(('image',) if stage=='observer' else ())}<=set(item.get('use_cases',[])):
            raise KeyRegistryError('default_model_unavailable','요청한 Flash/Super가 계정 또는 입력 역할에서 사용 가능하지 않습니다.',409)
        if type(item.get('max_model_len')) is not int or item['max_model_len']<=40000:
            raise KeyRegistryError('default_context_unverified','기본 출력 설정에 필요한 문맥 여유를 확인하지 못했습니다.',409)
        rows.append(dict(provider='nebius',model_id=model,visible=True,use_cases=item['use_cases'],
            context_tokens=item['max_model_len'],input_per_million=str(item['input_price_per_million_tokens']),
            output_per_million=str(item['output_price_per_million_tokens'])))
    from twinpulse_provider.model_contracts import catalog_from_inventory,catalog_sha
    from twinpulse_provider.generation_policy import GenerationPolicy
    now=datetime.now(timezone.utc)
    catalog=catalog_from_inventory(dict(created_at=now.isoformat(),catalog_sha256=source_sha,models=rows),
        valid_until=(now+timedelta(days=7)).isoformat())
    path=routes.path.with_name('stage_model_catalog.json');previous=path.read_bytes() if path.exists() else None
    temporary=path.with_name('.'+path.name+'.'+uuid4().hex+'.tmp')
    def write(payload):
        try:
            with temporary.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    try:
        write(json.dumps(catalog).encode('utf-8'))
        route={stage:dict(key_id=key_id,model_id=model,max_output_tokens=40000)
            for stage,model in (('observer',PHYSICAL_AI_OBSERVER),('planner',PHYSICAL_AI_PLANNER))}
        route.update(generation_policy=GenerationPolicy().to_dict(),model_catalog_sha256=catalog_sha(catalog))
        routes.save(route,changed)
    except Exception:
        if previous is None:path.unlink(missing_ok=True)
        else:write(previous)
        raise
    return dict(state='applied',metadata_gets=2,message='Flash/Super configured from current account metadata. Generation quality and provider output maximum are not guaranteed.')
