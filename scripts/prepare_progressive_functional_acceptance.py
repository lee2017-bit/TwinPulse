# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prepare four ordinary input flows; no inference or benchmark ranking claim."""
import hashlib
import shutil
from pathlib import Path
from decimal import Decimal

from scripts.progressive_functional_scope import OBSERVER, PLANNER, DEADLINE, exclusive
from scripts.benchmark_protocol import source_freeze, canonical_sha, file_sha


def build_functional(output, root, catalog, carry, settings, registry, entry_id, prior_scopes=()):
    from twinpulse_app.settings import JsonProviderSettingsStore
    from twinpulse_app.key_registry import KeyRegistry
    from twinpulse_app.credentials import WindowsCredentialStore
    from twinpulse_app.stage_routing import StageRoutingSettings
    from twinpulse_provider.model_contracts import catalog_sha
    from twinpulse_provider.generation_policy import GenerationPolicy
    from dataclasses import replace
    from scripts.progressive_functional_scope import check_scope,audit_runtime,read_host_finance_supplement
    from scripts.benchmark_protocol import read_json
    prior_exposure=Decimal(0);prior_freeze={};prior_records=[]
    normalized=[Path(p).resolve() for p in prior_scopes]
    if len(set(normalized))!=len(normalized):raise ValueError('FUNCTIONAL_DUPLICATE_PRIOR_SCOPE')
    for prior_path in normalized:
        if not prior_path.is_relative_to(root/'outputs/progressive-twin-overnight-20261012'):
            raise ValueError('FUNCTIONAL_PRIOR_SCOPE_OUTSIDE_APPROVED_OUTPUT')
        previous=check_scope(prior_path,root,frozen=False)
        state_path=prior_path.parent/'functional-finance.json';state=read_json(state_path)
        if state['scope_sha256']!=canonical_sha(previous) or (prior_path.parent/'functional-owner.lock').exists():
            raise ValueError('FUNCTIONAL_PRIOR_OWNER_OR_SCOPE_UNRESOLVED')
        if any(Path(r['scope_path']).resolve() not in normalized for r in previous.get('prior_runs',[])):
            raise ValueError('FUNCTIONAL_PRIOR_ANCESTOR_NOT_INCLUDED')
        for row in state['runs']:
            if not row['settled'] or row['unknown_requests'] or Decimal(row['held_usd']):
                supplement_path,supplement=read_host_finance_supplement(prior_path,root)
                if supplement['case_id']!=row['case_id']:raise ValueError('FUNCTIONAL_PRIOR_UNKNOWN_STOP')
                prior_exposure+=Decimal(supplement['protected_exposure_usd'])
                prior_freeze[str(supplement_path)]=file_sha(supplement_path)
                for witness,digest in supplement['witnesses'].items():
                    if witness in prior_freeze and prior_freeze[witness]!=digest:
                        raise ValueError('FUNCTIONAL_PRIOR_WITNESS_HASH_CONFLICT')
                    prior_freeze[witness]=digest
                prior_records.append(dict(scope_path=str(prior_path),case_id=row['case_id'],
                    status=row['status'],product_status='FAIL',estimated_usd=row['estimated_usd'],held_usd=row['held_usd'],
                    protected_exposure_usd=supplement['protected_exposure_usd'],
                    supplementary_monetary_audit=supplement['classification'],
                    request_count=supplement['raw_audit']['request_count'],original_hold_released=False))
                continue
            case=next(c for c in previous['cases'] if c['case_id']==row['case_id'])
            audited=audit_runtime(prior_path.parent/row['case_id']/'runtime',request_limit=case['request_limit'],total_limit=case['reservation_usd'])
            if audited['estimated_usd']!=row['estimated_usd'] or audited['held_usd']!=row['held_usd']:
                raise ValueError('FUNCTIONAL_PRIOR_RAW_EXPOSURE_CHANGED')
            prior_exposure+=Decimal(audited['estimated_usd'])+Decimal(audited['held_usd'])
            prior_records.append(dict(scope_path=str(prior_path),case_id=row['case_id'],status=row['status'],
                estimated_usd=row['estimated_usd'],held_usd=row['held_usd'],request_count=audited['request_count']))
        prior_freeze[str(prior_path)]=file_sha(prior_path);prior_freeze[str(state_path)]=file_sha(state_path)
    configuration=output/'reviewed-settings';configuration.mkdir()
    for path in (settings.path,registry.path):shutil.copyfile(path,configuration/path.name)
    exclusive(configuration/'stage_model_catalog.json',catalog)
    trial_registry=KeyRegistry(JsonProviderSettingsStore(configuration/settings.path.name),WindowsCredentialStore())
    route=dict(observer=dict(key_id=entry_id,model_id=OBSERVER,max_output_tokens=40000),
        planner=dict(key_id=entry_id,model_id=PLANNER,max_output_tokens=40000,thinking_mode='default'),
        model_catalog_sha256=catalog_sha(catalog),generation_policy=replace(GenerationPolicy(),
            max_requests=12,external_final_review=True,initial_timeout_s=420,final_timeout_s=180).validate().to_dict())
    StageRoutingSettings(trial_registry).save(route,lambda:None)
    photos=output/'inputs';photos.mkdir()
    robot_source=Path('C:/Users/jaewo/AppData/Local/TwinPulse/runtime/inputs/c88acab57c704cfdf859932273d82d0a8bf46de84b7a2fc4883a4c17cae33797/6cef4e2b6a153671e5cd5d0dd77f031bebe764bee87f82f2b7a492456118f971.bin')
    if file_sha(robot_source)!='6cef4e2b6a153671e5cd5d0dd77f031bebe764bee87f82f2b7a492456118f971':
        raise ValueError('ORIGINAL_USER_ROBOT_PHOTO_CHANGED')
    robot_photo=photos/'user-robot-room.jpg';shutil.copyfile(robot_source,robot_photo)
    cases=[]
    definitions=[
        ('text-workspace','text_only',None,'Create an approximate 6 by 8 metre workspace with a desk against the back wall, a chair and a storage cabinet. Keep the central passage open. Dimensions are user estimates, not measurements.',True),
        ('image-living','image_only',root/'outputs/benchmark-overnight-20261011/public-living.jpg','',False),
        ('image-text-dining','text_plus_image',root/'outputs/benchmark-overnight-20261011/public-dining.jpg','Create an approximate Digital Twin from this dining room photo. Preserve the visible furniture and support relations, keep uncertain sizes marked as estimates and retain anything that needs refinement.',False),
        ('robot-photo-room','robot_photo',robot_photo,'Create an approximate Digital Twin from this photo of my bedroom with my TurtleBot3 Burger. Keep the visible robot distinguishable from room obstacles. This offline test must not connect to or move the physical robot.',False),
    ]
    for case_id,mode,image,prompt,feedback in definitions:
        cases.append(dict(case_id=case_id,input_mode=mode,prompt=prompt,
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            image=dict(path=str(image),sha256=file_sha(image),mime_type='image/jpeg') if image else None,
            external_transmission_allowed=True,public_release_allowed=mode!='robot_photo',
            origin='Existing user robot photo; private report only' if mode=='robot_photo' else 'Existing approved CC BY-SA photo or authored functional text',
            feedback=feedback,feedback_kinds=['move','resize'] if feedback else [],
            reservation_usd='3.00' if feedback else '1.00',
            request_limit=14 if feedback else 12))
    scope=dict(schema_version='progressive-functional-scope-1.0',approval_at='2026-10-11T14:33:20+00:00',
        expires_at=DEADLINE,models=dict(observer=OBSERVER,planner=PLANNER),additional_limit_usd='10.00',
        historical_protected_usd=str(carry),invoice_verified=False,
        prior_new_exposure_usd=str(prior_exposure),prior_finance_freeze=prior_freeze,prior_runs=prior_records,
        human_approval='Human approved the existing Flash/Super combination, photos, up to eight hours and an additional total USD10 including duplicates/UNKNOWN/held. Four morning input flows; physical robot and paid Cloud excluded.',
        physical_authority=False,cloud_authority=False,comparison_benchmark=False,
        host_driver_timeout_s=2500,deadline_admission_reserve_s=3600,
        settings_path=str(configuration/settings.path.name),
        settings_freeze={str(p):file_sha(p) for p in configuration.iterdir() if p.is_file()},
        source_freeze=source_freeze(root),cases=cases)
    exclusive(output/'functional-scope.json',scope)
    exclusive(output/'functional-finance.json',dict(schema_version='progressive-functional-finance-1.0',
        scope_sha256=canonical_sha(scope),historical_protected_usd=str(carry),additional_limit_usd='10.00',
        prior_new_exposure_usd=str(prior_exposure),
        runs=[],other_new_campaign_dispatches=0))
    return dict(status='APPROVED_FUNCTIONAL_SCOPE_PREPARED_NO_INFERENCE',cases=len(cases),
        image_only_empty_prompt=True,existing_robot_photo_sha256=file_sha(robot_photo),
        new_total_limit_usd='10.00',historical_exposure_usd=str(carry),inference=0,
        prior_new_exposure_usd=str(prior_exposure),prior_finance_reaudited=True,
        comparative_benchmark=False,physical_authority=False)
