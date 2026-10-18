# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Saved failure replay, zero HTTP/robot and no private reasoning output.

Only the failure classification and immutable evidence digest are reported.
Never modifies the saved attempts, photos, settings, or historical ledgers.
"""
import hashlib
import argparse
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

from twinpulse_provider.nebius_pipeline import parse_chat_completion, ObservationArtifact
from twinpulse_provider.scene_contract import lower_proposal, preflight_site
from twinpulse_provider import GenerationRequest, InvalidProviderResponseError


def semantic_failure(case):
    """Recompile one immutable failed semantic case, then probe allowed scope.

    The local probe is deliberately NOT a model response, replayed completion,
    metric ground truth or published Twin. The original FAIL stays unchanged.
    """
    from twinpulse_core import canonical_sha256
    from twinpulse_provider.contracts import ImageInput
    from twinpulse_provider.semantic_scene import compile_scene,review_candidate_quality,patch_candidate,revision,PATCH_REVISION
    from twinpulse_provider.photo_layout import REGIONS
    case=case.resolve()
    if not case.is_relative_to(ROOT/'outputs'):raise ValueError('Owned outputs case required')
    paths=list(case.rglob('*.json'));seals={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    source=json.loads((case/'result.json').read_text(encoding='utf-8'))
    checkpoints=list((case/'generation-store/checkpoint').glob('*.json'))
    if source.get('status')!='FAIL' or len(checkpoints)!=1:raise ValueError('One closed failed semantic case required')
    wrapper=json.loads(checkpoints[0].read_text(encoding='utf-8'));cp=wrapper['payload']
    if canonical_sha256(cp)!=wrapper['payload_sha256']:raise ValueError('Checkpoint digest mismatch')
    if cp['error_code']!='REPAIR_STALLED':raise ValueError('Expected immutable stalled repair case')
    receipts=[]
    for item in cp['budget']['attempts']:
        record=json.loads((case/'evidence'/(item['attempt_id']+'.json')).read_text(encoding='utf-8'))
        raw=record['response_redacted'];digest=hashlib.sha256(raw.encode()).hexdigest()
        if digest!=record.get('stored_response_sha256',record.get('response_sha256')):
            raise ValueError('Raw response digest mismatch')
        completion=parse_chat_completion(json.loads(raw))
        if completion.finish_reason!='stop' or record['model_id']!=item['model_id']:
            raise ValueError('Original completed model receipt mismatch')
        receipts.append(dict(attempt_id=item['attempt_id'],model_id=item['model_id'],finish_reason=completion.finish_reason,
            usage=completion.usage,response_file_sha256=seals[str(case/'evidence'/(item['attempt_id']+'.json'))]))
    observation=ObservationArtifact.from_mapping(cp['observation'])
    # Presence only enables saved-observation review; these bytes are never a
    # source photo, model input, external transmission or visual-quality proof.
    request=GenerationRequest('local-saved-diagnosis', 'Read-only saved estimated scene diagnosis',
        (ImageInput('not-a-photo.jpg','image/jpeg',b'local-observation-only'),))
    draft=deepcopy(cp['draft']);plan,checks=compile_scene(draft,observation,request)
    quality=review_candidate_quality(draft,plan,checks,observation,request)
    probes=[];solution=None
    for row in quality['issues']:
        for target in row['target_ids']:
            obj=draft['objects'][target];parent=obj['placement']['parent_id']
            if parent not in draft['objects']:continue
            anchors=['centre'] if obj['placement']['relation']=='surface' else ['front','left','right','rear']
            for region in REGIONS:
                for anchor in anchors:
                    value=deepcopy(obj);value['placement']['anchor']=anchor
                    operations=[dict(op='update',id=parent,value=dict(draft['objects'][parent],region=region))]
                    if value!=obj:operations.append(dict(op='update',id=target,value=value))
                    patch=dict(patch_version=PATCH_REVISION,base_revision=revision(draft),operations=operations)
                    probe=dict(parent_id=parent,parent_region=region,attachment_anchor=anchor,model_response=False)
                    try:
                        candidate=patch_candidate(draft,patch,observation,request,repair_diagnosis=quality)
                        p,c=compile_scene(candidate,observation,request)
                        q=review_candidate_quality(candidate,p,c,observation,request)
                        probe.update(checks_complete=c['checks_complete'],quality_status=q['status'],
                            quality_issue_codes=[r['code'] for r in q['issues']])
                        if not q['issues']:
                            solution=dict(patch=patch,candidate_revision=revision(candidate),
                                checks_complete=c['checks_complete'],quality_status=q['status'],
                                model_recovery=False,Isaac='NOT_RUN',physical_authority=False)
                    except Exception as error:
                        probe['rejection']=getattr(error,'code',type(error).__name__)
                    probes.append(probe)
                    if solution:break
                if solution:break
            if solution:break
        if solution:break
    unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in seals.items())
    if not unchanged:raise AssertionError('Protected saved evidence changed')
    if not quality['issues'] or not all('violation_m' in r and
            'estimated_position_m' in r['actual']['observation_relation'] for r in quality['issues']):
        raise AssertionError('Expected numerical compiled-position feedback')
    return dict(status='PASS_DIAGNOSIS_ONLY',scope='saved semantic failure + local dependency probe, not model recovery',
        original_execution_id=source.get('execution_id'),original_status=source['status'],original_error=cp['error_code'],
        receipts=receipts,geometry_checks_complete=checks['checks_complete'],quality_review=quality,
        local_probes=probes,local_solution=solution,original_seals=seals,original_evidence_unchanged=unchanged,
        network_calls=0,robot_commands=0,actual_model_recovery='NOT_RUN',Isaac='NOT_RUN',physical_authority=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semantic-case',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Network is forbidden in saved failure replay')
    socket.create_connection = forbidden
    socket.socket.connect = forbidden
    if args.semantic_case:
        result=semantic_failure(args.semantic_case)
        if args.output:
            destination=args.output.resolve()
            if destination.is_relative_to(args.semantic_case.resolve()):raise ValueError('Cannot overwrite source case')
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({k:result[k] for k in ('status','original_status','original_error',
            'geometry_checks_complete','original_evidence_unchanged','network_calls','actual_model_recovery')},ensure_ascii=False))
        return
    if args.output:raise ValueError('--output requires --semantic-case')
    results = []
    roots = [('length', ROOT/'artifacts/pre-demo-20261009/saved-stage-300s-five/run-1/runtime/provider-evidence'),
             ('joins', ROOT/'artifacts/pre-demo-20261009/saved-stage-20000-five/run-1/runtime/provider-evidence')]
    preserved = {}
    for case, root in roots:
        records = []
        for path in sorted(root.glob('*.json')):
            blob = path.read_bytes()
            preserved[path] = hashlib.sha256(blob).hexdigest()
            record = json.loads(blob)
            raw = record.get('response_redacted')
            if raw:
                payload = json.loads(raw)
                records.append((path, record, payload))
        if case == 'length':
            lengths = [row for row in records if any(choice.get('finish_reason') == 'length'
                for choice in row[2].get('choices', []))]
            if len(lengths) != 1:
                raise AssertionError('Expected exactly one saved length failure')
            path, record, payload = lengths[0]
            try:
                parse_chat_completion(payload)
            except InvalidProviderResponseError as error:
                if getattr(error, 'code', None) != 'PROVIDER_OUTPUT_TRUNCATED':
                    raise
                results.append({'case': 'saved_length_empty', 'status': 'REPRODUCED',
                    'code': error.code, 'evidence_sha256': preserved[path], 'network_calls': 0})
            else:
                raise AssertionError('Saved length was accepted')
        else:
            observer = next(ObservationArtifact.from_mapping(json.loads(row[2]['choices'][0]['message']['content']))
                for row in records if row[1]['model_id'].startswith('gpt-'))
            first = min((row for row in records if 'Nemotron' in row[1]['model_id']),
                        key=lambda row: row[1]['started_at'])
            path, record, payload = first
            original = json.loads(parse_chat_completion(payload).content)
            plan, proposal = lower_proposal(original)
            # Join integrity itself is independent of prompt/visual quality.
            call_ids = {row['call_id'] for row in plan['calls']}
            evidence_ids = {row['call_id'] for row in plan['call_evidence']}
            if call_ids == evidence_ids:
                raise AssertionError('Expected saved mismatched call/evidence identities')
            results.append({'case': 'saved_call_evidence_mismatch', 'status': 'REPRODUCED',
                'missing_evidence_count': len(call_ids-evidence_ids),
                'unknown_evidence_count': len(evidence_ids-call_ids),
                'evidence_sha256': preserved[path], 'network_calls': 0})
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in preserved.items())
    print(json.dumps({'status': 'PASS', 'scope': 'saved failures only, not fresh model success',
        'cases': results, 'original_evidence_unchanged': True, 'HTTP': 0, 'robot_commands': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
