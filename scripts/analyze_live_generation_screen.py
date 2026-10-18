# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline audit of existing ordinary live screen evidence, no API/engine/robot.

Never repair, trim-to-parse, or replace the original model answer. Whitespace
counts are diagnostics only; success still comes from the production validator.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run.resolve()
    root=run/'runtime/provider-evidence'
    protected=[p for p in run.rglob('*') if p.is_file() and p.name!='live-response-analysis.json']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    result=json.loads((run/'result.json').read_text(encoding='utf-8'))
    browser=result['browser'];terminal=browser.get('terminal') or browser['failure_state']
    generation=terminal['conversation']['generation']
    rows=[]
    ledgers=[json.loads(p.read_text(encoding='utf-8')) for p in (run/'runtime/ordinary-generation').glob('*.ledger.json')]
    for row in [r for ledger in ledgers for r in ledger['requests']]:
        attempt=row['attempt_id'];raw=json.loads((root/f'{attempt}.json').read_text(encoding='utf-8'))
        dispatch=json.loads((root/'dispatches'/f'{attempt}.json').read_text(encoding='utf-8'))
        body=json.loads(dispatch['request_redacted'])
        response=json.loads(raw['response_redacted']);choice=response['choices'][0]
        content=choice['message'].get('content') or ''
        validations=[json.loads(p.read_text(encoding='utf-8')) for p in (root/'validations').glob(f'{attempt}-*.json')]
        facts={'attempt_id':attempt,'execution_id':dispatch['execution_id'],'span_id':dispatch['span_id'],
               'stage':dispatch['schema_stage'],'role':dispatch['role'],'model_id':row['model_id'],
               'elapsed_s':raw['elapsed_s'],'finish_reason':choice['finish_reason'],'max_tokens':row['max_tokens'],
               'usage':row['usage'],'estimated_usd':row['estimated_usd'],
               'content_chars':len(content),'trailing_whitespace_chars':len(content)-len(content.rstrip()),
               'reasoning_content_chars':len(choice['message'].get('reasoning_content') or ''),
               'response_truncated_by_capture':raw['response_truncated'],
               'request_truncated_by_capture':dispatch['request_truncated'],
               'thinking_option':body.get('chat_template_kwargs'),
               'validations':[{'stage':v['stage'],**{k:r.get(k) for k in ('validation','validation_code','role')}}
                              for v in validations for r in [json.loads(v['record_redacted'])]],
               'validation_identity_sha_valid':all(v['execution_id']==dispatch['execution_id'] and
                   v['span_id']==dispatch['span_id'] and
                   hashlib.sha256(v['record_redacted'].encode()).hexdigest()==v['stored_record_sha256'] for v in validations)}
        try:
            candidate=json.loads(content);facts['json_parse']='PASS'
            if any(v['stage']=='observer' for v in validations):
                facts['observed_entities']=len(candidate['entities'])
                facts['required_objects']=[e['id'] for e in candidate['entities'] if e.get('role') in ('object','unknown')]
        except json.JSONDecodeError as error:
            facts['json_parse']='FAIL';facts['json_error']={'message':error.msg,'position':error.pos,
                                                         'line':error.lineno,'column':error.colno}
            facts['last_nonblank_excerpt']=content.rstrip()[-600:]
        rows.append(facts)
    audit={'generation_status':generation['state'],'execution_id':terminal['workflow']['execution_id'],
           'operation_id':generation['operation_id'],'requests':len(rows),'unused_requests':10-len(rows),
           'rows':rows,'budget':generation.get('error',{}).get('diagnostics',generation.get('progress',{})).get('budget'),
           'browser_verification':browser.get('verification_status'),'page_errors':browser['page_errors'],
           'engine_requests':browser['engine_requests'],'engine_operations':terminal['product']['operations'],
           'owned_backend_exited':result['owned_backend_exited'],'new_model_calls':0,
           'originals_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())}
    (run/'live-response-analysis.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'generation_status':audit['generation_status'],'requests':len(rows),
                     'originals_unchanged':audit['originals_unchanged'],'rows':rows},ensure_ascii=True))


if __name__=='__main__':main()
