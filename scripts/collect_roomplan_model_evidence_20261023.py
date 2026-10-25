# SPDX-License-Identifier: Apache-2.0
"""Freeze an actual completed proposal and its audited usage, never invoke it."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--attempt',required=True)
    parser.add_argument('--preserve-failed',action='store_true',help='Freeze partial model originals; never changes failed UI verdict.')
    args=parser.parse_args()
    if not re.fullmatch('[0-9]{2}',args.attempt):raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
    root=args.output_root.resolve();ui=read(root/f'roomplan-ai-edit-{args.attempt}/result.json')
    if ui['status']!='PASS' and not args.preserve_failed:raise ValueError('ACTUAL_WHOLE_AI_EDIT_PASS_REQUIRED')
    proposal=ui['model_proposal'];job,request=proposal['job_id'],proposal['request_id']
    if not re.fullmatch('[a-f0-9]{32}',job):raise ValueError('EXACT_PROPOSAL_REQUIRED')
    projects={r['body']['project_id'] for r in ui['responses']
        if ((r.get('body') or {}).get('proposal') or {}).get('job_id')==job}
    if len(projects)!=1:raise ValueError('ONE_ORIGINAL_PROJECT_REQUIRED')
    project=projects.pop()
    if not re.fullmatch('chat_[a-z0-9_]+',project):raise ValueError('PROJECT_ID_INVALID')
    runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
    original=runtime/'projects'/project/'environment-imports/model-proposals'/job
    state=read(original/'job.json')
    if state.get('status')!='ready' or state.get('request_id')!=request or '_owner' in state:
        raise ValueError('COMPLETE_CREDENTIAL_FREE_ORIGINAL_REQUIRED')
    claims=[p for p in (runtime/'ordinary-generation').glob('*.ordinary-scope.json')
        if (v:=read(p)).get('request_id')==request and v.get('project_id')==project]
    if len(claims)!=1:raise ValueError('ONE_ACTUAL_SCOPE_CLAIM_REQUIRED')
    claim=claims[0];ledger=claim.with_name(claim.name.removesuffix('.ordinary-scope.json')+'.json')
    usage=read(ledger)
    if usage.get('approval')!=read(claim)['approval_id'] or len(usage.get('requests',[]))!=1:
        raise ValueError('ONE_ACTUAL_AUDITED_HTTP_REQUIRED')
    folder=root/('model-evidence'+args.attempt);folder.mkdir(exist_ok=False)
    refs={}
    for role,path in dict(model_request=original/'request.json',model_result=original/'result.json',
            model_job=original/'job.json',model_diagnostic=original/'provider-diagnostic.json',
            model_ledger=ledger,scope_claim=claim).items():
        if not path.resolve().is_relative_to(runtime.resolve()) or any(p.is_symlink() or p.is_junction()
                for p in (path,*path.parents) if p.is_relative_to(runtime)):
            raise ValueError('ORIGINAL_PATH_UNSAFE')
        raw=path.read_bytes();target=folder/(role+'.json')
        with target.open('xb') as stream:stream.write(raw)
        refs[role]=dict(path=target.relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
    with (folder/'copy-receipt.json').open('x',encoding='utf-8') as stream:
        json.dump(dict(project_id=project,job_id=job,request_id=request,refs=refs,original_ui_status=ui['status'],
            basis='Exact saved original bytes; no model call, API mutation or fabricated provider result'),stream,indent=2)
    print(json.dumps(dict(project_id=project,job_id=job,model_id=proposal['model_id'],copied=len(refs))))

if __name__=='__main__':main()
