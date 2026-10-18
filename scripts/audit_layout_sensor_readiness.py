# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only saved usage/evidence audit, never a test driver or invoice.

Outputs metrics and source hashes only. Does not read credentials, send HTTP,
change product state, release historical holds or infer photo PASS from counts.
"""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages/twinpulse_core/src'))
for name in ('twinpulse_provider','twinpulse_app','twinpulse_robot'):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages'/name/'src'))
from twinpulse_core import canonical_sha256


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(state,since,carry,catalog_path,limit=Decimal('10')):
    catalog=read(catalog_path)
    rates={r['model_id']:r for r in catalog['models']}
    totals={};ledgers=[];ids=[];unknown=[];in_flight=[];held=Decimal(0)
    for path in sorted((state/'ordinary-generation').glob('*.ledger.json')):
        value=read(path)
        if value.get('schema_version')!='product-usage-1.0' or datetime.fromisoformat(value['created_at'])<since:
            continue
        row=dict(ledger=path.name,sha256=sha(path),approval=value['approval'],http=0,attempt_ids=[],execution_ids=[])
        claim=path.with_suffix('.ordinary-scope.json')
        if claim.is_file():
            source=read(claim)
            row.update({k:source[k] for k in ('request_id','project_id','input_sha256') if k in source})
        for item in value['requests']:
            identity=item['attempt_id'];model=item['model_id'];rate=rates[model]
            row['http']+=1;row['attempt_ids'].append(identity);ids.append(identity)
            usage=item.get('usage') or {}
            # Host cancellation/schema rejection does not erase billable usage
            # received and settled by the original HTTP worker. Never count an
            # in-flight reservation or a response without validated usage here.
            known=(bool(item.get('finished_at')) and item['status'] in {'received','rejected'}
                and type(usage.get('prompt_tokens')) is int and usage['prompt_tokens']>=0
                and type(usage.get('completion_tokens')) is int and usage['completion_tokens']>=0)
            if not known:
                (unknown if item.get('finished_at') else in_flight).append(identity)
                held+=(Decimal(rate['context_tokens'])*Decimal(rate['input_per_million'])+
                    Decimal(item['max_tokens'])*Decimal(rate['output_per_million']))/1000000
            else:
                total=totals.setdefault(model,dict(http=0,input_tokens=0,output_tokens=0,estimated_usd=Decimal(0)))
                total['http']+=1;total['input_tokens']+=usage['prompt_tokens'];total['output_tokens']+=usage['completion_tokens']
                total['estimated_usd']+=(Decimal(usage['prompt_tokens'])*Decimal(rate['input_per_million'])+
                    Decimal(usage['completion_tokens'])*Decimal(rate['output_per_million']))/1000000
            proof=state/'provider-evidence'/(identity+'.json')
            if proof.is_file():
                facts=read(proof)
                for key in ('request_id','project_id','input_sha256'):
                    if isinstance(facts.get(key),str):row[key]=facts[key]
                if facts.get('execution_id') and facts['execution_id'] not in row['execution_ids']:
                    row['execution_ids'].append(facts['execution_id'])
                row.setdefault('evidence',[]).append(dict(attempt_id=identity,sha256=sha(proof),
                    stage=facts.get('schema_stage'),elapsed_s=facts.get('elapsed_s'),
                    finish_reason=facts.get('finish_reason'),status=facts.get('status')))
        ledgers.append(row)
    checkpoints=[]
    requests={r.get('request_id') for r in ledgers}
    for path in (state/'provider-evidence/generation-store/checkpoint').glob('*.json'):
        envelope=read(path)
        if envelope.get('schema_version')!='generation-store-1.0':continue
        value=envelope['payload']
        if value.get('request_id') not in requests:continue
        if envelope['payload_sha256']!=canonical_sha256(value):raise ValueError('Checkpoint hash mismatch')
        progress=value.get('progressive_twin') or {};quality=value.get('quality_review') or {}
        checkpoints.append(dict(checkpoint=path.stem,sha256=sha(path),payload_sha256=envelope['payload_sha256'],request_id=value['request_id'],
            state=value.get('state'),stop=value.get('budget',{}).get('stop_reason') or value.get('error_code'),
            error_code=value.get('error_code'),elapsed_s=value.get('budget',{}).get('elapsed_s'),
            repairs=value.get('budget',{}).get('repairs'),requests=value.get('budget',{}).get('requests'),
            render_reviews=len(value.get('render_history',[])),quality_status=quality.get('status'),
            relative_layout=quality.get('relative_layout'),
            unresolved_ids=[r['id'] for r in progress.get('unresolved',[])]))
    edits=[]
    from twinpulse_app.project_store import ProjectStore
    from twinpulse_app.scene_changes import SceneChangeStore
    for project in sorted({r['project_id'] for r in ledgers if r.get('project_id')}):
        store=ProjectStore.for_project(state,project);record=store.load()
        if record.site_draft is None:continue
        source=record.site_draft;path=store.path.with_suffix('.scene-changes.json')
        history=SceneChangeStore(path,project_id=project,source=source,project_store=store).load()
        effective=history.effective(source);progress=effective.progressive(source)
        edits.append(dict(project_id=project,source_sha256=canonical_sha256(source.to_dict()),
            project_file_sha256=sha(store.path),history_sha256=sha(path) if path.is_file() else None,
            scene_revision=effective.site.scene.revision,state_sha256=history.state_sha256(effective),
            objects_sha256=canonical_sha256(effective.site.scene.to_dict()['objects']),
            inventory_sha256=canonical_sha256(effective.inventory),
            pending_ids=[r['id'] for r in (progress or {}).get('unresolved',[])],
            pending_policy=(progress or {}).get('policy_version'),
            placements_sha256=canonical_sha256(effective.placement),
            operations=[dict(operation_id=r.operation_id,mode=r.mode) for r in history.operations]))
    estimate=sum((r['estimated_usd'] for r in totals.values()),Decimal(0))
    for row in totals.values():row['estimated_usd']=str(row['estimated_usd'])
    return dict(schema_version='relative-layout-usage-audit-1.0',local_only=True,
        cost_basis='received usage times historical catalog rates; not invoice',
        start=since.isoformat(),http=len(ids),totals=totals,ledgers=ledgers,checkpoints=checkpoints,edits=edits,
        new_unknown_attempt_ids=unknown,in_flight_attempt_ids=in_flight,
        duplicate_attempt_ids=[i for i,n in Counter(ids).items() if n>1],
        new_held_usd=str(held),new_estimated_usd=str(estimate),protected_carry_in_usd=str(carry),
        protected_exposure_usd=str(carry+estimate+held),limit_usd=str(limit),rates_catalog_sha256=sha(catalog_path))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--since',required=True)
    parser.add_argument('--carry',type=Decimal,required=True)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=Decimal,default=Decimal('10'))
    args=parser.parse_args()
    if args.limit<=0:parser.error('--limit must be positive')
    value=audit(args.state,datetime.fromisoformat(args.since),args.carry,args.catalog,args.limit)
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:value[k] for k in ('http','new_estimated_usd','new_held_usd','protected_exposure_usd',
        'new_unknown_attempt_ids','duplicate_attempt_ids')}))
