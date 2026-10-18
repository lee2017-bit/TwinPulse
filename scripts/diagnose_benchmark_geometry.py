# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only saved failures through current core/compiler. Never a fresh model run.

All source JSON/photo hashes are checked before/after. Derived diagnostics use a
new exclusive output file; no settings, old ledger, checkpoint or result writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))

from twinpulse_core import canonical_sha256
from twinpulse_core.simulation_goal import goal_review
from twinpulse_provider import GenerationRequest, ImageInput
from twinpulse_provider.errors import ProviderError
from twinpulse_provider.generation_store import GenerationStore, input_digest
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.semantic_scene import compile_scene
from twinpulse_provider.semantic_scene import patch_candidate,revision
from twinpulse_app.project_store import ProjectRecord
from twinpulse_app.simulation_assets import burger_inventory


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_audit(evidence,state,observation,request):
    """Replay original typed patches from their hash-checked request/response.

    Changed siblings, actual input revisions and original rollback are checked;
    original progress decisions stay separate from current-code diagnostics.
    No model answer, current candidate or historical verdict is overwritten.
    """
    rows=[]
    for path in sorted((evidence/'dispatches').glob('*.json')):
        dispatch=read(path);body=json.loads(dispatch['request_redacted'])
        if body.get('response_format',{}).get('json_schema',{}).get('name')!='twinpulse_semantic_patch':continue
        raw=read(evidence/(path.stem+'.json'))
        if (dispatch.get('request_truncated') or raw.get('response_truncated')
                or hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest()!=dispatch['stored_request_sha256']
                or hashlib.sha256(raw['response_redacted'].encode()).hexdigest()!=raw['stored_response_sha256']
                or dispatch['request_sha256']!=raw['request_sha256']):
            raise ValueError('SAVED_PATCH_WIRE_BINDING_CHANGED')
        feedback=json.loads(body['messages'][-1]['content']);candidate=feedback['candidate']
        before=canonical_sha256(candidate)
        row=dict(attempt_id=path.stem,before_revision=revision(candidate),
            original_reason_codes=[i.get('code') for i in feedback['validation'].get('issues',[])],
            raw_response_sha256=raw['stored_response_sha256'])
        def compiler(draft):
            try:
                plan,trace=compile_scene(draft,observation,request)
                return dict(status='PASSED',plan_sha256=canonical_sha256(plan))
            except (ValueError,ProviderError) as error:
                report=getattr(error,'contract_report',{}) or {}
                return dict(status='REJECTED',code=getattr(error,'code',str(error).split(':')[0]),
                    reason_codes=[i.get('code') for i in report.get('issues',[])],
                    check_ledger=report.get('check_ledger'),
                    termination_code=(getattr(error,'packing_report',{}) or {}).get('bounded_search',{}).get('termination_code'))
        row['current_before']=compiler(candidate)
        try:
            response=json.loads(raw['response_redacted'])
            patch=json.loads(response['choices'][0]['message']['content'])
            changed=patch_candidate(candidate,patch,observation,request,repair_diagnosis=feedback['validation'])
            ids=set(candidate['objects'])|set(changed['objects'])
            changed_ids=sorted(i for i in ids if candidate['objects'].get(i)!=changed['objects'].get(i))
            after=revision(changed)
            original=next((p for p in state['patches'] if p['before']==revision(candidate) and p['after']==after),None)
            progress_candidate={**changed,'objects':sorted([dict(id=i,**v)
                for i,v in changed['objects'].items()],key=lambda v:v['id'])}
            progress_candidate.pop('summary',None)  # ProgressTracker's historical identity contract.
            if isinstance(progress_candidate.get('inventory'),list):
                progress_candidate['inventory'].sort(key=lambda v:str(v.get('id','')) if isinstance(v,dict) else str(v))
            row.update(patch_status='APPLIED_COPY',after_revision=after,changed_ids=changed_ids,
                room_changed=candidate['room']!=changed['room'],original_patch_log_bound=original is not None,
                original_changed_ids_match=bool(original and sorted(original.get('changed_ids',[]))==changed_ids),
                original_validation=(original or {}).get('validation'),current_after=compiler(changed),
                unchanged_sibling_ids=sorted(i for i in ids if i not in changed_ids),
                original_progress=[h for h in (state.get('geometry_progress') or {}).get('history',[])
                                   if h.get('candidate_sha256')==canonical_sha256(progress_candidate)])
        except (ValueError,ProviderError) as error:
            row.update(patch_status='REJECTED_COPY',code=getattr(error,'code',str(error).split(':')[0]))
        if canonical_sha256(candidate)!=before:raise AssertionError('SAVED_PATCH_BASE_MUTATED')
        rows.append(row)
    branch=state.get('working_branch') or {};expected=branch.get('rollback_to')
    return dict(patches=rows,rollback_expected_revision=expected,
        restored_revision=revision(state['draft']),rollback_matches_expected=revision(state['draft'])==expected if expected else None,
        failed_branch_revision=branch.get('candidate_revision'),branch_abandoned=branch.get('branch_abandoned'),
        original_error_code=state.get('error_code'),original_progress=state.get('geometry_progress'),
        original_rollback_revalidation=state.get('rollback_revalidation'),
        scope='ORIGINAL_PATCH_PROGRESS_AND_ROLLBACK_NOT_FRESH_RECOVERY')


def packing(run,photo):
    latest=read(run/'runtime/active_project.json')['latest_input']
    if latest['measurement_constraints']:
        raise ValueError('SAVED_MEASUREMENT_REPLAY_REQUIRES_EXPLICIT_ADAPTER')
    images=[]
    for image in latest['images']:
        if photo is None or digest(photo)!=image['sha256']:
            raise ValueError('SAVED_INPUT_PHOTO_BINDING_CHANGED')
        images.append(ImageInput(image['name'],image['mime_type'],photo.read_bytes()))
    root=run/'runtime/provider-evidence/generation-store'
    store=GenerationStore(root);rows=[];seen=set();latest_state=latest_request=None
    paths=[*sorted((root/'checkpoint').glob('*.json')),
           *sorted((root/'checkpoint-history').glob('*/*.json'))]
    for path in paths:
        if path.parent==root/'checkpoint':state=store.read('checkpoint',path.stem)
        else:
            envelope=read(path)
            if (set(envelope)!={'schema_version','payload_sha256','payload'}
                    or envelope['schema_version']!='generation-store-1.0'
                    or canonical_sha256(envelope['payload'])!=envelope['payload_sha256']):
                raise ValueError('SAVED_CHECKPOINT_HISTORY_DIGEST_CHANGED')
            state=envelope['payload']
        if not state.get('draft') or not state.get('observation'):continue
        identity=canonical_sha256(dict(draft=state['draft'],observation=state['observation']))
        if identity in seen:continue
        seen.add(identity)
        request=None
        for detail in ('auto','low','high'):
            candidate=GenerationRequest(state['request_id'],latest['prompt'],tuple(images),image_detail=detail)
            if input_digest(candidate)==state['input_sha256']:request=candidate;break
        if request is None:raise ValueError('SAVED_INPUT_REQUEST_BINDING_CHANGED')
        if path.parent==root/'checkpoint':latest_state=state;latest_request=request
        before=canonical_sha256(state)
        row=dict(source_checkpoint_sha256=digest(path),checkpoint_id=path.stem,
            original_error_code=state.get('error_code'),request_id=state['request_id'],
            original_candidate_sha256=canonical_sha256(state['draft']),
            source_snapshot=str(path.relative_to(root)))
        try:
            payload,trace=compile_scene(state['draft'],ObservationArtifact.from_mapping(state['observation']),request)
            row.update(compile_status='PASSED',plan_sha256=canonical_sha256(payload),
                       bounded_search=trace.get('bounded_packing_search'))
        except (ValueError,ProviderError) as error:
            row.update(compile_status='REJECTED',error_type=type(error).__name__,error=str(error),
                packing_diagnostic=getattr(error,'packing_report',None),
                geometry_diagnostic=getattr(error,'contract_report',None))
        if canonical_sha256(state)!=before:raise AssertionError('SAVED_CANDIDATE_MUTATED')
        rows.append(row)
    if not rows:raise ValueError('NO_SAVED_CANDIDATES')
    return dict(case_id=run.parent.name,kind='SAVED_COMPILER_DIAGNOSIS',candidates=rows,
        patch_audit=patch_audit(root.parent,latest_state,
            ObservationArtifact.from_mapping(latest_state['observation']),latest_request) if latest_state else None)


def goal(run):
    project=ProjectRecord.from_dict(read(run/'runtime/active_project.json'))
    record=project.site_draft
    browser=read(run/'result.json')['browser']
    conversation=browser['failure_state']['conversation']
    text=next(m['content'] for m in reversed(conversation['messages']) if m['role']=='user')
    pose=browser['samples'][-1]
    if pose['applied_revision']!=record.site.scene.revision:
        raise ValueError('SAVED_SCENE_POSE_BINDING_CHANGED')
    furniture={c.arguments['id']:c.arguments['kind'] for c in record.plan.calls if c.tool=='place_furniture'}
    before=canonical_sha256(record.to_dict())
    row=dict(case_id=run.parent.name,kind='SAVED_CORE_GOAL_DIAGNOSIS',
             scene_revision=record.site.scene.revision,start_source='ORIGINAL_LAST_SAVED_SIM_POSE')
    try:
        review=goal_review(record.site.scene,text,pose['position_m'][:2],burger_inventory(),
                           yaw=pose['yaw_rad'],furniture=furniture)
        row.update(planning_status='PASSED',diagnostic=review.get('approach_diagnostic'))
    except ValueError as error:
        row.update(planning_status='REJECTED',error=str(error),diagnostic=getattr(error,'goal_diagnostic',None))
    if canonical_sha256(record.to_dict())!=before:raise AssertionError('SAVED_SCENE_MUTATED')
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packing-run',type=Path,action='append',default=[])
    parser.add_argument('--goal-run',type=Path,action='append',default=[])
    parser.add_argument('--photo',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    runs=args.packing_run+args.goal_run
    if not runs:parser.error('At least one saved run required')
    output=args.output.resolve()
    if any(output.is_relative_to(run.resolve()) for run in runs):
        raise ValueError('DERIVED_OUTPUT_MUST_NOT_MODIFY_SOURCE_TREE')
    preserved={p:digest(p) for run in runs for p in run.rglob('*.json')}
    if args.photo:preserved[args.photo]=digest(args.photo)
    repo=Path(__file__).resolve().parents[1]
    code_paths=[Path(__file__).resolve(),
        repo/'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py',
        repo/'packages/twinpulse_core/src/twinpulse_core/simulation_goal.py',
        repo/'packages/twinpulse_core/src/twinpulse_core/site_simulation.py',
        repo/'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py']
    code_paths.append(repo/'packages/twinpulse_core/src/twinpulse_core/photo_placement.py')
    diagnostic_code={str(path.relative_to(repo)):digest(path) for path in code_paths}
    def forbidden(*_args,**_kwargs):raise AssertionError('NETWORK_FORBIDDEN_IN_SAVED_DIAGNOSIS')
    socket.create_connection=forbidden
    socket.socket.connect=forbidden
    rows=[packing(run,args.photo) for run in args.packing_run]+[goal(run) for run in args.goal_run]
    unchanged=all(digest(path)==value for path,value in preserved.items())
    code_unchanged=all(digest(repo/path)==value for path,value in diagnostic_code.items())
    report=dict(status='DIAGNOSTIC_COMPLETE' if unchanged else 'SOURCE_CHANGED',
        cases=rows,original_evidence_unchanged=unchanged,immutable_files=len(preserved),
        diagnostic_code_sha256=diagnostic_code,diagnostic_code_unchanged=code_unchanged,
        scope='Saved candidate/scene diagnosis only, not fresh model or actual Isaac acceptance',
        HTTP=0,Isaac='NOT_RUN',robot_commands=0,whole_demo_pass=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(status=report['status'],cases=len(rows),immutable_files=len(preserved),
        original_evidence_unchanged=unchanged,HTTP=0),ensure_ascii=True))
    for row in rows:
        reports=([candidate.get('packing_diagnostic',{}).get('bounded_search',{})
                  for candidate in row.get('candidates',[]) if candidate.get('packing_diagnostic')]
                 if row['kind']=='SAVED_COMPILER_DIAGNOSIS' else [row.get('diagnostic') or {}])
        print(json.dumps(dict(case_id=row['case_id'],termination_codes=[v.get('termination_code') for v in reports],
            reason_counts=[v.get('reason_counts') for v in reports]),ensure_ascii=True))
    if not unchanged or not code_unchanged:raise SystemExit(1)


if __name__=='__main__':main()
