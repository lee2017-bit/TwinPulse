# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only product/raw audit; writes one new bounded report, never calls models.

The approved image digest binds the input only, not a reference room layout.
No fixed inventory, room dimensions, object positions or support parents.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_core import canonical_sha256
from twinpulse_app.project_store import ProjectStore
from twinpulse_core.room_items import room_inventory
from twinpulse_core.photo_placement import validate_placement_plan


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def audit(approval_path,campaign_path,runs):
    approval=json.loads(approval_path.read_bytes()); ledger=json.loads(campaign_path.read_bytes())
    start=approval['start_request_count']; requests=ledger['requests']; fresh=requests[start:]
    assert digest(requests[:start])==approval['prior_requests_sha256'],'PRIOR_REQUESTS_CHANGED'
    assert len(fresh)<=approval['max_new_requests'] and len(requests)<=approval['batch_request_ceiling']
    assert ledger['max_requests']==approval['campaign_request_limit_unchanged']
    assert Decimal(ledger['limit_usd'])==Decimal(approval['campaign_usd_limit_unchanged'])
    assert not campaign_path.with_suffix('.dispatch-lock').exists(),'DISPATCH_STILL_ACTIVE'
    assert all(r.get('finished_at') for r in fresh),'PENDING_REQUEST'
    rows={r['attempt_id']:r for r in fresh}; seen=set(); audits=[]; source=None
    for directory in runs:
        original=(directory/'result.json').read_bytes(); result=json.loads(original)
        assert any(hashlib.sha256(p.read_bytes()).hexdigest()==approval['photo_sha256']
            for p in directory.glob('*.jpg')),'APPROVED_PHOTO_COPY_MISSING'
        assert result['provider']=='live_configured_provider' and result['photo_inference']=='LIVE'
        assert result['robot_connections']==0 and result['physical_authority'] is False
        assert result['inference_source_unchanged'] and result['inference_source_at_start']==result['inference_source_at_end']
        if source is None:source=result['inference_source_at_start']
        assert result['inference_source_at_start']==source,'SOURCE_CHANGED_BETWEEN_TRIALS'
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in source.items())
        browser=result.get('browser',{}); generation=browser.get('conversation',{}).get('generation',{})
        progress=generation.get('progress') or {}; attempts=progress.get('attempts',[])
        raw_audits=[]
        for path in sorted((directory/'runtime/provider-evidence').glob('*.json')):
            facts=json.loads(path.read_bytes()); identifier=path.stem
            assert identifier in rows and identifier not in seen,'UNBOUND_OR_DUPLICATE_RAW'
            seen.add(identifier); row=rows[identifier]
            if 'response_redacted' not in facts:
                assert row['status']=='outcome_unknown' and facts['status']=='outcome_unknown'
                assert row.get('finished_at') and facts['attempt_id']==identifier
                assert facts['model_id']==row['model_id'] and facts.get('execution_id')
                raw_audits.append(dict(attempt_id=identifier,model=row['model_id'],status='outcome_unknown',
                    remote_response='NOT_RECEIVED',elapsed_s=facts['elapsed_s'],error_type=facts.get('error_type'),
                    dispatch_metadata_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    execution_id=facts['execution_id'],reserved_usd=row['charged_or_reserved_usd']))
                continue
            raw=facts['response_redacted'].encode('utf-8'); payload=json.loads(raw)
            assert identifier==facts['attempt_id'] and not facts['response_truncated']
            assert hashlib.sha256(raw).hexdigest()==facts['response_sha256'] and len(raw)==facts['response_byte_count']
            if not payload.get('choices'):
                assert facts['status']=='rejected' and row['status']=='rejected'
                assert 400<=facts['http_status']<=599 and payload.get('error')
                raw_audits.append(dict(attempt_id=identifier,model=row['model_id'],status='rejected',
                    http_status=facts['http_status'],error_type=facts.get('error_type'),
                    api_error=payload['error'],raw_sha256=facts['response_sha256'],raw_bytes=len(raw),
                    elapsed_s=facts['elapsed_s'],usage=None,reserved_usd=row['charged_or_reserved_usd']))
                continue
            assert payload['model']==row['model_id']
            assert all(payload['usage'].get(k)==v for k,v in (row.get('usage') or {}).items())
            choice=payload['choices'][0]; content=choice['message'].get('content') or ''
            try:candidate=json.loads(content)
            except (ValueError,TypeError):candidate={}
            safe=dict(attempt_id=identifier,model=row['model_id'],status=row['status'],
                raw_sha256=facts['response_sha256'],raw_bytes=len(raw),elapsed_s=facts['elapsed_s'],
                finish_reason=choice['finish_reason'],usage=row.get('usage',{}),json_valid=bool(candidate),
                wire_version=candidate.get('schema_version',candidate.get('layout_version',candidate.get('proposal_version'))))
            safe['content_chars']=len(content)
            safe['trailing_whitespace_chars']=len(content)-len(content.rstrip())
            safe['request_sha256']=facts['request_sha256']
            safe['schema_sha256']=facts['schema_sha256']
            if 'entities' in candidate:safe['entity_count']=len(candidate['entities'])
            if 'objects' in candidate:
                safe['object_count']=len(candidate['objects'])
                safe['objects_with_source']=sum(isinstance(o.get('source'),dict) for o in candidate['objects'])
            if 'floor_call' in candidate:
                safe['floor_tool']=candidate['floor_call'].get('tool');safe['scene_call_count']=len(candidate['scene_calls'])
            raw_audits.append(safe)
        published={a['attempt_id'] for a in attempts if a.get('attempt_id')}
        received={r['attempt_id'] for r in raw_audits if r['status']!='outcome_unknown'}
        assert published==received,'PUBLIC_PROVENANCE_RAW_MISMATCH'
        assert sum(not a.get('attempt_id') for a in attempts)==sum(r['status']=='outcome_unknown' for r in raw_audits)
        repairs=progress.get('repair_count',max(0,len(attempts)-len({a['stage'] for a in attempts})))
        accepted=generation.get('state')=='completed'
        record=dict(path=str(directory.relative_to(ROOT)),status=result['status'],generation_state=generation.get('state'),
            route='compact1.3' if result['experimental_compact_photo'] else 'site-proposal1.0',
            accepted=accepted,repair_count=repairs,attempts=attempts,raw_audits=raw_audits,
            generation_error=generation.get('error'),runner_error=result.get('error'),
            browser_closed=browser.get('browser_closed',False),supervisor_status=result['supervisor']['status'],
            inference_source_unchanged=True,original_result_sha256=hashlib.sha256(original).hexdigest())
        record['generation_progress']=progress
        record['execution_ids']=sorted({r['execution_id'] for r in raw_audits if r.get('execution_id')})
        assert record['browser_closed'] and record['supervisor_status']=='stopped'
        assert not any(result['supervisor'][k].get('owned') for k in ('backend','engine'))
        if accepted:
            saved=ProjectStore(directory/'runtime/active_project.json').load().site_draft
            assert saved.input_revision.images[0]['sha256']==approval['photo_sha256']
            assert canonical_sha256(saved.plan.to_dict())==saved.plan_sha256
            inventory=room_inventory(saved.plan,saved.site.scene)
            record['saved_project']=dict(plan_sha256=saved.plan_sha256,input_revision=saved.input_revision.digest,
                schema_version=saved.schema_version,items=len(inventory['items']),
                room_scale='ESTIMATED_NOT_MEASURED',full_photo_fidelity='UNVERIFIED')
            if result['experimental_compact_photo']:
                assert saved.schema_version=='2.1' and len(saved.placement_contract['relations'])==len(inventory['items'])
                validate_placement_plan(saved.plan,saved.placement_contract)
                record['saved_project']['support_contract']='PASS'
                record['saved_project']['support_relations']=len(saved.placement_contract['relations'])
            if result['status']=='PASS':
                assert result['physics']=='actual_local_Isaac' and browser['status']=='PASS'
                assert result['host']['status']=='PASS' and result['host']['capture']['status']=='PASS'
                assert browser['arrival']['distance_to_goal_m']<=.05
                assert len(browser['frames'])>0
                record['actual_isaac']=dict(status='PASS',frames=len(browser['frames']),
                    arrival_error_m=browser['arrival']['distance_to_goal_m'],checks=browser['checks'])
        assert (directory/'result.json').read_bytes()==original
        audits.append(record)
    assert seen==set(rows),'MISSING_FRESH_LEDGER_EVIDENCE'
    cost=sum((Decimal(r['charged_or_reserved_usd']) for r in requests),Decimal(0))
    return dict(schema_version='scene-contract-live-batch-audit-1.0',audit_status='PASS',
        source_baseline=approval.get('source_baseline','1.0.352'),approval_record=str(approval_path.relative_to(ROOT)),
        calls_used=len(fresh),calls_allowed=approval['max_new_requests'],calls_unused=approval['max_new_requests']-len(fresh),
        campaign_calls=len(requests),pending=0,increment_estimated_usd=str(cost-Decimal(approval['start_estimated_plus_reserved_usd'])),
        cumulative_estimated_plus_reserved_usd=str(cost),invoice_verified=False,
        unknown_new_calls=sum(r['status']=='outcome_unknown' for r in fresh),
        responses_received=sum('finish_reason' in raw for run in audits for raw in run['raw_audits']),
        raw_bodies_received=sum('raw_bytes' in raw for run in audits for raw in run['raw_audits']),
        http_error_responses=sum('http_status' in raw for run in audits for raw in run['raw_audits']),
        ledger_received_status_count=sum(r['status']=='received' for r in fresh),
        stop_reason='Repeated observer deadline; no redundant dispatch' if all(
            not r['accepted'] and r['generation_error'] and r['generation_error']['code']=='provider_timeout'
            for r in audits) else 'Bounded batch completed; see per-run result',
        prior_requests_unchanged=True,inference_source_unchanged=True,raw_bound_and_immutable=True,
        session_count=len(audits),accepted_scenes=sum(r['accepted'] for r in audits),
        repaired_sessions=sum(r['repair_count']>0 for r in audits),
        recovered_sessions=sum(r['accepted'] and r['repair_count']>0 for r in audits),
        actual_isaac_pass=sum(r['status']=='PASS' for r in audits),
        production_default_acceptance=False,evaluation_overrides=approval['evaluation_overrides'],
        floorplan_transmitted=False,robot_connections=0,full_photo_fidelity='UNVERIFIED',
        metric_scale='UNVERIFIED_NO_MEASUREMENTS',whole_demo_ready=False,runs=audits)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approval',type=Path,required=True);parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('runs',nargs='+',type=Path)
    args=parser.parse_args()
    value=audit(args.approval.resolve(),args.campaign.resolve(),[p.resolve() for p in args.runs])
    with args.output.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in value.items() if k!='runs'},ensure_ascii=True))
