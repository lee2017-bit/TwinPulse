# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline, metrics-only audit rendering with explicit human UI judgements.

No test execution, model call, API key read, or inference of PASS from counts.
Private report images are embedded so the report is one self-contained file.
"""
import argparse
import base64
from html import escape as esc
import json
from pathlib import Path


def build(folder):
    audit=json.loads((folder/'audit.json').read_text(encoding='utf-8'))
    assessment=json.loads((folder/'acceptance.json').read_text(encoding='utf-8'))
    text=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>TwinPulse 실제 사용자 인수</title><style>body{max-width:1160px;margin:30px auto;padding:0 20px;font:16px/1.65 system-ui;color:#182737;background:#fafcfd}h2{border-top:1px solid #ced9e1;padding-top:20px;margin-top:32px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;border:1px solid #ced9e1;vertical-align:top;text-align:left}code,pre{font-size:12px;overflow-wrap:anywhere;white-space:pre-wrap}img{max-width:100%;border:1px solid #ccd7df;border-radius:8px}figure{margin:28px 0;break-inside:avoid}figcaption{color:#526571}.status{background:#edf3f7;padding:18px;border-radius:12px}</style>',
        '<h1>'+esc(assessment.get('title','TwinPulse 생성형 Library · 실제 사용자 흐름 검증'))+'</h1>',
        '<p>로컬 비공개 단일 보고서 · '+esc(assessment['status'])+'</p>',
        '<div class="status">'+esc(assessment['summary'])+'</div><h2>시험 방법·한계</h2>']
    for line in assessment['method']:text.append('<p>'+esc(line)+'</p>')
    text.append('<h2>모든 실제 시도</h2><table><tr><th>입력/설치본</th><th>판정</th><th>실행 식별·시간·호출</th></tr>')
    covered=set()
    for case in assessment['cases']:
        request=case.get('request_id')
        ledger=next((x for x in audit['ledgers'] if x['request_id']==request),{}) if request else {}
        cp=next((x for x in audit['checkpoints'] if x['request_id']==request),{}) if request else {}
        if request:covered.add(request)
        ids={k:ledger[k] for k in ('request_id','project_id','input_sha256','http','execution_ids','attempt_ids') if k in ledger}
        ids.update({k:cp[k] for k in ('checkpoint','state','repairs','carried_http','elapsed_s','stop') if k in cp})
        if case.get('execution_ids'):ids['ui_execution_ids']=case['execution_ids']
        text.append('<tr><td>'+esc(case['title'])+'<br>'+esc(str(case.get('build','local')))+'</td><td>'+
            esc(case['verdict'])+'</td><td><pre>'+esc(json.dumps(ids,ensure_ascii=False,indent=2))+'</pre></td></tr>')
    for ledger in audit['ledgers']:
        if ledger['request_id'] in covered:continue
        text.append('<tr><td>추가 장부 기록</td><td>판정 누락 · PASS로 세지 않음</td><td><pre>'+esc(json.dumps(ledger,ensure_ascii=False,indent=2))+'</pre></td></tr>')
    text.append('</table><h2>저장·수정·Undo 재감사</h2><pre>'+esc(json.dumps(audit['edits'],ensure_ascii=False,indent=2))+'</pre>')
    for line in assessment.get('restoration',[]):text.append('<p>'+esc(line)+'</p>')
    text.append('<h2>비용·미확정·중복</h2><pre>'+esc(json.dumps({k:audit[k] for k in (
        'http','totals','new_unknown_attempt_ids','duplicate_attempt_ids','new_held_usd','protected_carry_in_usd',
        'protected_exposure_usd','limit_usd','rates_catalog_sha256')},ensure_ascii=False,indent=2))+'</pre>')
    text.append('<p>응답 usage×보존 카탈로그 단가의 추정, 공급자 청구서 확정액 아님. 기존 UNKNOWN/중복 보류를 포함한 원 누적 한도를 초기화하거나 환급하지 않았다. OpenAI·실물·유료 Cloud·공개 배포·commit/push·새 의존성 설치는 이번 작업 0.</p>')
    text.append('<h2>구현·정확한 잔여</h2>')
    for line in assessment['changes']:text.append('<p>'+esc(line)+'</p>')
    text.append('<ul>')
    for line in assessment['remaining']:text.append('<li>'+esc(line)+'</li>')
    text.append('</ul><h2>동결 설치본</h2><table><tr><th>Build</th><th>Source manifest SHA</th></tr>')
    for path in sorted(folder.glob('build*/dist/TwinPulse/windows-release-manifest.json')):
        item=json.loads(path.read_text(encoding='utf-8'))
        text.append('<tr><td>'+esc(item['build_id'])+'</td><td><code>'+esc(item['source_manifest_sha256'])+'</code></td></tr>')
    text.append('</table><h2>실제 화면</h2>')
    count=0
    for screen in assessment['screens']:
        path=folder/screen['file']
        if not path.exists():raise ValueError('Missing actual screenshot: '+str(path))
        encoded=base64.b64encode(path.read_bytes()).decode('ascii')
        text.append('<figure><img alt="'+esc(screen['caption'])+'" src="data:image/jpeg;base64,'+encoded+'"><figcaption>'+esc(screen['caption'])+'</figcaption></figure>')
        count+=1
    text.append('</html>')
    target=folder/'report.html';target.write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps(dict(report=str(target),screens=count,bytes=target.stat().st_size),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    build(parser.parse_args().folder)
