# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only audit AFTER actual browser actions; never performs acceptance UI."""
import argparse
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_core import canonical_sha256


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(runtime,output,start,carry_in=Decimal('4.4934696')):
    catalog=read(runtime/'stage_model_catalog.json')
    rates={m['model_id']:m for m in catalog['models']}
    grouped=[];requests={};duplicates=[]
    for path in (runtime/'ordinary-generation').glob('*.ledger.json'):
        ledger=read(path)
        if datetime.fromisoformat(ledger['created_at'])<start:continue
        claim=path.with_suffix('.ordinary-scope.json')
        owner=read(claim) if claim.exists() else {}
        grouped.append(dict(ledger=path.name,sha256=sha(path),approval=ledger['approval'],
            project_id=owner.get('project_id'),request_id=owner.get('request_id'),
            input_sha256=owner.get('input_sha256'),http=len(ledger['requests']),
            attempt_ids=[r['attempt_id'] for r in ledger['requests']],execution_ids=sorted({
                read(dispatch).get('execution_id') for r in ledger['requests']
                if (dispatch:=runtime/'provider-evidence/dispatches'/f"{r['attempt_id']}.json").exists()
                and read(dispatch).get('execution_id')})))
        for row in ledger['requests']:
            if row['attempt_id'] in requests:duplicates.append(row['attempt_id'])
            else:requests[row['attempt_id']]=row
    totals=defaultdict(lambda:dict(http=0,input_tokens=0,output_tokens=0,estimate=Decimal(0)))
    unknown=[];held=Decimal(0)
    for identity,row in requests.items():
        summary=totals[row['model_id']];summary['http']+=1
        usage=row.get('usage',{})
        if not row.get('finished_at') or row.get('status')!='received' or not all(
                type(usage.get(k)) is int for k in ('prompt_tokens','completion_tokens')):
            unknown.append(identity)
            rate=rates.get(row['model_id'])
            if rate:
                held+=(Decimal(str(rate['input_per_million']))*rate['context_tokens']+
                    Decimal(str(rate['output_per_million']))*row['max_tokens'])/1000000
            continue
        summary['input_tokens']+=usage['prompt_tokens'];summary['output_tokens']+=usage['completion_tokens']
        rate=rates.get(row['model_id'])
        if rate:
            summary['estimate']+=(Decimal(str(rate['input_per_million']))*usage['prompt_tokens']+
                Decimal(str(rate['output_per_million']))*usage['completion_tokens'])/1000000
        else:unknown.append(identity)
    for summary in totals.values():summary['estimated_usd']=str(summary.pop('estimate'))
    checkpoints=[]
    for path in (runtime/'provider-evidence/generation-store/checkpoint').glob('*.json'):
        payload=read(path)['payload']
        if payload.get('approval_id') not in {r['approval'] for r in grouped}:continue
        budget=payload.get('budget',{})
        attempt_ids=[r['attempt_id'] for r in budget.get('attempts',[])]
        executions=set()
        for identity in attempt_ids:
            dispatch=runtime/'provider-evidence/dispatches'/f'{identity}.json'
            if dispatch.exists():executions.add(read(dispatch).get('execution_id'))
        checkpoints.append(dict(checkpoint=path.stem,sha256=sha(path),request_id=payload.get('request_id'),
            parent=payload.get('parent_checkpoint_id'),input_sha256=payload.get('input_sha256'),
            execution_ids=sorted(x for x in executions if x),state=payload.get('state'),
            http=budget.get('requests'),carried_http=budget.get('carried_requests'),
            repairs=budget.get('repairs'),carried_repairs=budget.get('carried_repairs'),
            elapsed_s=budget.get('elapsed_s'),stop=budget.get('stop_reason'),
            model_selections=(payload.get('draft') or {}).get('model_selections',{})))
    edits={}
    for prefix in ('','ready25-','original33-'):
        base=output/(prefix+'before-edit.project.json')
        if not base.exists():continue
        project=read(base);source=SiteDraftRecord.from_dict(project['site_draft'])
        initial=source.site.scene
        for label in ('after-edit','after-undo'):
            path=output/(prefix+label+'.changes.json')
            if not path.exists():continue
            history=SceneChangeHistory.from_dict(read(path),source,project['project_id'])
            state=history.effective(source)
            old={p.id:p for p in initial.objects};new={p.id:p for p in state.site.scene.objects}
            moved={identity:[round(new[identity].transform.position_m[i]-p.transform.position_m[i],9)
                for i in range(3)] for identity,p in old.items() if new[identity]!=p}
            recipes=[c.arguments['recipe_sha256'] for c in state.plan.calls if c.tool=='place_model_recipe']
            edits[prefix+label]=dict(history_sha256=sha(path),operation_ids=[o.operation_id for o in history.operations],
                effective_scene_revision=state.site.scene.revision,original_scene_revision=initial.revision,
                exact_original_objects=state.site.scene.objects==initial.objects,moved=moved,recipe_hashes=recipes,
                inventory_count=len(state.inventory),unresolved=state.progressive(source)['unresolved'] if source.progressive_twin else [],
                transaction=read(output/(prefix+label+'.transaction.json')) if (output/(prefix+label+'.transaction.json')).exists() else None)
        cold=output/(prefix+'after-cold.project.json')
        cold_history=output/(prefix+'after-cold.changes.json')
        if cold.exists() and cold_history.exists():
            restored=read(cold);history=SceneChangeHistory.from_dict(read(cold_history),source,project['project_id'])
            state=history.effective(source)
            edits[prefix+'cold']=dict(source_record_exact=restored['site_draft']==project['site_draft'],
                exact_original_objects=state.site.scene.objects==initial.objects,
                history_sha256=sha(cold_history),operation_ids=[o.operation_id for o in history.operations],
                unresolved=state.progressive(source)['unresolved'] if source.progressive_twin else [])
    result=dict(schema_version='model-library-user-acceptance-1.0',local_only=True,
        source_of_acceptance='ordinary Start + actual browser clicks + Isaac; this script only audits stored evidence',
        start=start.isoformat(),http=len(requests),duplicate_attempt_ids=duplicates,new_unknown_attempt_ids=unknown,
        rates_catalog_sha256=sha(runtime/'stage_model_catalog.json'),
        cost_basis='received token usage multiplied by preserved catalog rates, not a provider invoice',
        totals=dict(totals),new_held_usd=str(held),
        protected_carry_in_usd=str(carry_in),
        protected_exposure_usd=str(carry_in+held+
            sum(Decimal(v['estimated_usd']) for v in totals.values())),
        limit_usd='10',ledgers=grouped,checkpoints=checkpoints,edits=edits)
    # Explicitly do not copy raw replies, credentials or catalog content.
    output.mkdir(parents=True,exist_ok=True)
    (output/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('http','new_unknown_attempt_ids','duplicate_attempt_ids','totals')},ensure_ascii=False))
    print(json.dumps({k:{f:v for f,v in row.items() if f not in {'transaction','unresolved'}} for k,row in edits.items()},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--start',required=True)
    parser.add_argument('--carry-in',type=Decimal,default=Decimal('4.4934696'))
    args=parser.parse_args();audit(args.runtime,args.output,datetime.fromisoformat(args.start),args.carry_in)
