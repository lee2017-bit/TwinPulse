# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline benchmark contracts. No credentials, model calls or answer injection.

Case annotations remain evaluator-only. A journey packet contains only the
same user's input/goal and their digests, never labels or judged geometry.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import re

ID=re.compile(r'[a-z0-9][a-z0-9_-]{0,63}\Z')
DIGEST=re.compile(r'[a-f0-9]{64}\Z')


def text_sha(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical_sha(value):return text_sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))


def _shape(value,fields,code):
    if type(value) is not dict or set(value)!=set(fields):raise ValueError(code)


def _text(value,limit,code):
    if type(value) is not str or not value.strip() or len(value)>limit:raise ValueError(code)


def _id(value):
    if type(value) is not str or not ID.fullmatch(value):raise ValueError('BENCHMARK_ID_INVALID')


def _digest(value):
    if type(value) is not str or not DIGEST.fullmatch(value):raise ValueError('BENCHMARK_DIGEST_INVALID')


def read_json(path):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('BENCHMARK_FILE_INVALID')
    def pairs(rows):
        value={}
        for key,item in rows:
            if key in value:raise ValueError('BENCHMARK_DUPLICATE_FIELD')
            value[key]=item
        return value
    def invalid(_):raise ValueError('BENCHMARK_NONFINITE_JSON')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def _file(reference,base,verify):
    _digest(reference['sha256']);_text(reference['path'],1024,'BENCHMARK_PATH_INVALID')
    path=Path(reference['path'])
    if not path.is_absolute():path=Path(base)/path
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('BENCHMARK_LINKED_INPUT')
    path=path.resolve()
    if verify and (not path.is_file() or file_sha(path)!=reference['sha256']):
        raise ValueError('BENCHMARK_INPUT_SHA_CHANGED')
    return str(path)


def checked_case(value,base,*,verify_files=True):
    _shape(value,('schema_version','case_id','room_group','split','modality','prompt',
        'prompt_sha256','photo','goal','source','annotations'),'BENCHMARK_CASE_SHAPE_INVALID')
    if value['schema_version']!='benchmark-case-1.0':raise ValueError('BENCHMARK_CASE_VERSION_INVALID')
    for key in ('case_id','room_group'):_id(value[key])
    if value['split'] not in ('development','holdout','diagnostic'):raise ValueError('BENCHMARK_SPLIT_INVALID')
    if value['modality'] not in ('photo','text'):raise ValueError('BENCHMARK_MODALITY_INVALID')
    _text(value['prompt'],10000,'BENCHMARK_PROMPT_INVALID');_digest(value['prompt_sha256'])
    if value['prompt']!=value['prompt'].strip():raise ValueError('BENCHMARK_PROMPT_UI_TRIM_MISMATCH')
    if text_sha(value['prompt'])!=value['prompt_sha256']:raise ValueError('BENCHMARK_PROMPT_SHA_CHANGED')
    result=deepcopy(value)
    if value['modality']=='photo':
        _shape(value['photo'],('path','sha256','mime_type'),'BENCHMARK_PHOTO_INVALID')
        if value['photo']['mime_type'] not in ('image/jpeg','image/png'):raise ValueError('BENCHMARK_MIME_INVALID')
        result['photo']['path']=_file(value['photo'],base,verify_files)
        if verify_files:
            path=Path(result['photo']['path'])
            if path.stat().st_size>10*1024*1024:raise ValueError('BENCHMARK_IMAGE_TOO_LARGE')
            try:
                from PIL import Image
                with Image.open(path) as image:
                    if image.format!=('JPEG' if value['photo']['mime_type']=='image/jpeg' else 'PNG'):
                        raise ValueError('BENCHMARK_IMAGE_MIME_MISMATCH')
                    if image.width*image.height>16_000_000:raise ValueError('BENCHMARK_IMAGE_TOO_LARGE')
                    image.verify()
            except ImportError as error:raise ValueError('BENCHMARK_IMAGE_VALIDATION_UNAVAILABLE') from error
            except OSError as error:raise ValueError('BENCHMARK_IMAGE_INVALID') from error
    elif value['photo'] is not None:raise ValueError('TEXT_BENCHMARK_MUST_NOT_SEND_IMAGE')
    _shape(value['goal'],('text','sha256','expected','start_policy'),'BENCHMARK_GOAL_INVALID')
    _text(value['goal']['text'],1000,'BENCHMARK_GOAL_TEXT_INVALID');_digest(value['goal']['sha256'])
    if value['goal']['text']!=value['goal']['text'].strip():raise ValueError('BENCHMARK_GOAL_UI_TRIM_MISMATCH')
    if text_sha(value['goal']['text'])!=value['goal']['sha256']:raise ValueError('BENCHMARK_GOAL_SHA_CHANGED')
    if value['goal']['expected'] not in ('arrival','rejection','clarification'):
        raise ValueError('BENCHMARK_EXPECTED_OUTCOME_INVALID')
    if value['goal']['start_policy']!='checked_sim_preview':raise ValueError('BENCHMARK_START_POLICY_UNSUPPORTED')
    if value['split']!='diagnostic' and value['goal']['expected']!='arrival':
        raise ValueError('NEGATIVE_CASE_REQUIRES_DIAGNOSTIC_SPLIT')
    _shape(value['source'],('reference','license','external_transmission_allowed','public_release_allowed'),
           'BENCHMARK_SOURCE_INVALID')
    for key in ('reference','license'):_text(value['source'][key],1000,'BENCHMARK_SOURCE_INVALID')
    for key in ('external_transmission_allowed','public_release_allowed'):
        if type(value['source'][key]) is not bool:raise ValueError('BENCHMARK_SOURCE_PERMISSION_INVALID')
    if value['annotations'] is not None:
        _shape(value['annotations'],('path','sha256'),'BENCHMARK_ANNOTATION_INVALID')
        result['annotations']['path']=_file(value['annotations'],base,verify_files)
        if result['photo'] and result['annotations']['path']==result['photo']['path']:
            raise ValueError('BENCHMARK_INPUT_ANNOTATION_COLLISION')
    return result


def journey_packet(case):
    """Only model-visible input and predeclared goal; annotation access forbidden."""
    return dict(schema_version='benchmark-journey-case-1.0',
        **{key:deepcopy(case[key]) for key in ('case_id','room_group','split','modality','prompt',
            'prompt_sha256','photo','goal')},
        external_transmission_allowed=case['source']['external_transmission_allowed'])


def checked_packet(value,*,actual=False):
    _shape(value,('schema_version','case_id','room_group','split','modality','prompt',
        'prompt_sha256','photo','goal','external_transmission_allowed'),'BENCHMARK_PACKET_INVALID')
    if value['schema_version']!='benchmark-journey-case-1.0':raise ValueError('BENCHMARK_PACKET_VERSION_INVALID')
    reconstructed={key:deepcopy(value[key]) for key in ('case_id','room_group','split','modality',
        'prompt','prompt_sha256','photo','goal')}
    reconstructed.update(schema_version='benchmark-case-1.0',annotations=None,
        source=dict(reference='packet',license='dataset manifest records permission',
            external_transmission_allowed=value['external_transmission_allowed'],public_release_allowed=False))
    checked=checked_case(reconstructed,Path.cwd())
    if actual and not value['external_transmission_allowed']:raise ValueError('BENCHMARK_TRANSMISSION_NOT_APPROVED')
    return journey_packet(checked)


def checked_manifest(value,base):
    fields=('schema_version','dataset_id','version','seed','repeats','cases','configs','freeze')
    if isinstance(value,dict) and value.get('schema_version') in ('comparative-benchmark-1.1','comparative-benchmark-1.2','comparative-benchmark-1.3'):
        fields+=('model_catalog',)
    if isinstance(value,dict) and value.get('schema_version') in ('comparative-benchmark-1.2','comparative-benchmark-1.3'):
        fields+=('execution_environment','evaluation')
    _shape(value,fields,
           'BENCHMARK_MANIFEST_INVALID')
    if value['schema_version'] not in ('comparative-benchmark-1.0','comparative-benchmark-1.1','comparative-benchmark-1.2','comparative-benchmark-1.3'):raise ValueError('BENCHMARK_MANIFEST_VERSION_INVALID')
    _id(value['dataset_id']);_text(value['version'],64,'BENCHMARK_DATASET_VERSION_INVALID')
    if type(value['seed']) is not int or not 0<=value['seed']<2**32:raise ValueError('BENCHMARK_SEED_INVALID')
    if type(value['repeats']) is not int or not 1<=value['repeats']<=10:raise ValueError('BENCHMARK_REPEATS_INVALID')
    if type(value['cases']) is not list or not 1<=len(value['cases'])<=1000:
        raise ValueError('BENCHMARK_CASE_COUNT_INVALID')
    cases=[checked_case(case,base) for case in value['cases']]
    if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('BENCHMARK_DUPLICATE_CASE')
    groups={};images={};texts={}
    for case in cases:
        group=case['room_group'];split=case['split']
        if group in groups and groups[group]!=split:raise ValueError('BENCHMARK_ROOM_SPLIT_LEAKAGE')
        groups[group]=split
        if case['photo']:
            digest=case['photo']['sha256']
            if digest in images and images[digest]!=group:raise ValueError('BENCHMARK_DUPLICATE_IMAGE_GROUP')
            images[digest]=group
        else:
            # Identical text scenes are one room cluster, not independent data.
            digest=case['prompt_sha256']
            if value['schema_version'] in ('comparative-benchmark-1.2','comparative-benchmark-1.3') and digest in texts and texts[digest]!=group:
                raise ValueError('BENCHMARK_DUPLICATE_TEXT_GROUP')
            texts[digest]=group
    if type(value['configs']) is not list or not 1<=len(value['configs'])<=(256 if 'model_catalog' in value else 16):
        raise ValueError('BENCHMARK_CONFIG_COUNT_INVALID')
    ids=[]
    for config in value['configs']:
        config_fields=('config_id','roles','settings_sha256')
        if value['schema_version']=='comparative-benchmark-1.3':config_fields+=('stage_output_token_caps',)
        _shape(config,config_fields,'BENCHMARK_CONFIG_INVALID')
        frozen_stage_output_caps(config)
        _id(config['config_id']);_digest(config['settings_sha256']);ids.append(config['config_id'])
        _shape(config['roles'],('observer','planner','repair','critic'),'BENCHMARK_ROLES_INVALID')
        for role in config['roles'].values():
            _shape(role,('provider','model'),'BENCHMARK_ROLE_INVALID')
            if role['provider'] not in ('nebius','openai'):raise ValueError('BENCHMARK_PROVIDER_UNSUPPORTED')
            _text(role['model'],160,'BENCHMARK_MODEL_INVALID')
    if len(set(ids))!=len(ids):raise ValueError('BENCHMARK_DUPLICATE_CONFIG')
    if type(value['freeze']) is not dict or not value['freeze']:raise ValueError('BENCHMARK_FREEZE_REQUIRED')
    frozen={}
    for path,digest in value['freeze'].items():
        frozen[_file(dict(path=path,sha256=digest),base,True)]=digest
    result={**deepcopy(value),'cases':cases,'freeze':frozen}
    if 'model_catalog' in value:
        _shape(value['model_catalog'],('path','sha256'),'BENCHMARK_MODEL_CATALOG_REFERENCE_INVALID')
        reference=value['model_catalog'];catalog_path=_file(reference,base,True)
        from twinpulse_provider.model_contracts import checked_catalog
        result['model_catalog']=checked_catalog(read_json(catalog_path))
        result['freeze'][catalog_path]=reference['sha256']
    if 'execution_environment' in value:
        _shape(value['execution_environment'],('path','sha256'),'BENCHMARK_ENVIRONMENT_REFERENCE_INVALID')
        reference=value['execution_environment'];environment_path=_file(reference,base,True)
        from scripts.benchmark_environment import checked_environment
        result['execution_environment']=checked_environment(read_json(environment_path))
        result['freeze'][environment_path]=reference['sha256']
        _shape(value['evaluation'],('rubric','review_provenance'),'BENCHMARK_EVALUATION_INVALID')
        reference=value['evaluation']['rubric']
        _shape(reference,('path','sha256'),'BENCHMARK_RUBRIC_REFERENCE_INVALID')
        rubric_path=_file(reference,base,True)
        from scripts.benchmark_quality import checked_rubric
        rubric=checked_rubric(read_json(rubric_path))
        result['evaluation']=dict(rubric=dict(path=rubric_path,sha256=reference['sha256']),
                                  rubric_sha256=canonical_sha(rubric),review_provenance=None)
        result['freeze'][rubric_path]=reference['sha256']
        reference=value['evaluation']['review_provenance']
        if reference is not None:
            _shape(reference,('path','sha256'),'BENCHMARK_REVIEW_PROVENANCE_REFERENCE_INVALID')
            review_path=_file(reference,base,True)
            result['evaluation']['review_provenance']=dict(path=review_path,sha256=reference['sha256'])
            result['freeze'][review_path]=reference['sha256']
        for case in cases:
            if case['annotations']:result['freeze'][case['annotations']['path']]=case['annotations']['sha256']
    return result


def frozen_stage_output_caps(config):
    """Old cohorts keep their actual 20k setting; new settings are explicit.

    Does not infer values from the current UI or increase an existing grant.
    """
    from twinpulse_provider.output_diagnostics import MAX_STAGE_OUTPUT_TOKENS
    caps=config.get('stage_output_token_caps',dict(observer=20000,planner=20000))
    _shape(caps,('observer','planner'),'BENCHMARK_OUTPUT_CAPS_INVALID')
    if any(type(v) is not int or not 1<=v<=MAX_STAGE_OUTPUT_TOKENS for v in caps.values()):
        raise ValueError('BENCHMARK_OUTPUT_CAPS_INVALID')
    return deepcopy(caps)


def effective_settings_sha(route,roles):
    """Hash isolated route policy, not a substitute for runtime/provider audit."""
    value=dict(roles=roles,generation_policy=route['generation_policy'],
        generation_timeout_s=route.get('generation_timeout_s'),
        stage_settings={stage:{key:value for key,value in route[stage].items() if key!='key_id'}
                        for stage in ('observer','planner')})
    if 'model_catalog_sha256' in route:value['model_catalog_sha256']=route['model_catalog_sha256']
    return canonical_sha(value)


def source_freeze(root):
    """Product/harness source inventory; no outputs, caches or account settings."""
    root=Path(root);paths=set()
    for package in ('twinpulse_core','twinpulse_provider','twinpulse_app','twinpulse_robot_safety'):
        paths.update((root/'packages'/package/'src').rglob('*.py'))
    for directory in ('apps/twinpulse-web/src','apps/twinpulse-web/e2e','apps/twinpulse-web/dist','scripts',
                      'extensions/twinpulse.extension'):
        paths.update(p for p in (root/directory).rglob('*') if p.is_file()
            and p.suffix in {'.py','.ts','.tsx','.js','.mjs','.css','.html','.toml'})
    paths.update(root/name for name in ('apps/twinpulse-web/package.json','apps/twinpulse-web/package-lock.json',
                 'apps/twinpulse-web/vite.config.ts','apps/twinpulse-web/index.html')
                 if (root/name).is_file())
    asset_root=root/'artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1'
    if asset_root.exists():
        from twinpulse_app.simulation_assets import _inventory
        paths.update(asset_root/name for name in _inventory(asset_root))
    return {str(p.resolve()):file_sha(p) for p in sorted(paths)}


def schedule(manifest):
    """Seeded paired blocks; each config's execution position is balanced ±1."""
    rng=random.Random(manifest['seed'])
    blocks=[(case,repeat) for case in manifest['cases'] for repeat in range(1,manifest['repeats']+1)]
    rng.shuffle(blocks);configs=[c['config_id'] for c in manifest['configs']];jobs=[]
    for block,(case,repeat) in enumerate(blocks):
        if block%len(configs)==0:rng.shuffle(configs)
        offset=block%len(configs);order=configs[offset:]+configs[:offset]
        for position,config in enumerate(order):
            identity=dict(case_id=case['case_id'],config_id=config,repeat=repeat)
            jobs.append(dict(job_id=canonical_sha(identity)[:32],**identity,
                room_group=case['room_group'],split=case['split'],modality=case['modality'],
                block=block,position=position))
    return jobs


def prepare(manifest_path):
    """Read/hash only. This is not financial or sensor/motion authorization."""
    path=Path(manifest_path).resolve();original=read_json(path)
    manifest=checked_manifest(original,path.parent);jobs=schedule(manifest)
    result=dict(schema_version='prepared-benchmark-1.0',manifest_sha256=file_sha(path),
        dataset_id=manifest['dataset_id'],version=manifest['version'],jobs=jobs,
        packets={case['case_id']:journey_packet(case) for case in manifest['cases']},
        freeze=manifest['freeze'],configs=manifest['configs'],
        HTTP=0,actual_run_authorized=False,physical_authority=False)
    if 'model_catalog' in manifest:result['model_catalog']=manifest['model_catalog']
    for key in ('execution_environment','evaluation'):
        if key in manifest:result[key]=manifest[key]
    if 'evaluation' in manifest:
        from scripts.benchmark_evaluation import readiness
        result['evaluation_readiness']=readiness(manifest,result['packets'])
    return result
