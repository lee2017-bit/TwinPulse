# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local, single-file product acceptance report from retained real-run evidence."""
import base64
from decimal import Decimal
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'outputs/product-flow-20261013'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def esc(value):return html.escape(str(value if value is not None else '미측정'))
def picture(path,label):
    mime='image/jpeg' if path.suffix.lower() in {'.jpg','.jpeg'} else 'image/png'
    encoded=base64.b64encode(path.read_bytes()).decode('ascii')
    return f'<figure><img loading="lazy" src="data:{mime};base64,{encoded}" alt="{esc(label)}"><figcaption>{esc(label)}</figcaption></figure>'

def main():
    evidence=[];cards=[];table=[];seen=set()
    # Original failures stay visible. No fixture or other-source model scores are merged.
    for folder in sorted(HOME.iterdir()):
        if not folder.is_dir() or not (folder/'result.json').exists():continue
        run=read(folder/'result.json');browser=run.get('browser',{})
        if 'status' not in run:continue
        evidence.append(dict(run=folder.name,status=run['status'],source_sha256=run.get('source_sha256'),
            original_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest(),
            source_unchanged=run.get('source_unchanged'),requests=run.get('usage',{}).get('requests'),
            launch=run.get('launch'),cleanup=run.get('supervisor',{}).get('phase')))
        smoke=bool(run.get('smoke_only'))
        if smoke:
            cards.append(f'<section><h2>{esc(folder.name)} 저장 장면과 대화 전환</h2><p>{esc(run["status"])} · 모델 호출 {esc(run.get("usage",{}).get("requests"))} · {esc(browser.get("error"))}</p>')
            if (folder/'saved-actual.png').exists():cards.append(picture(folder/'saved-actual.png','실제 저장 장면 재열기'))
            cards.append('<pre>'+esc(json.dumps(browser.get('switches',[]),ensure_ascii=False,indent=2))+'</pre></section>')
        for case in browser.get('cases',[]):
            job=case.get('generation') or {};workflow=case.get('workflow') or {}
            invoked=bool(job.get('operation_id'))
            key=(case['id'],job.get('operation_id'))
            if not invoked and key in seen:continue
            seen.add(key)
            invoked=invoked or bool(case.get('operation_id'))
            outcome=case.get('status','NOT_RUN') if invoked else 'NOT_RUN before generation'
            if case.get('continuation'):outcome+=' (unfinished stages resumed)'
            if case.get('type'):outcome+=' (feedback, not generation)'
            table.append('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in (folder.name,case['id'],
                job.get('state',case.get('feedback',{}).get('state','해당 없음')),outcome,case.get('elapsed_s'),job.get('operation_id') or case.get('operation_id'),case.get('execution_id') or workflow.get('execution_id'),case.get('error','')))+'</tr>')
            cards.append(f'<section><h2>{esc(folder.name)} {esc(case["id"])}</h2><p>생성 {esc(job.get("state","해당 없음"))} · 사용자 흐름 {esc(outcome)} · {esc(case.get("elapsed_s"))}초</p><p>작업 ID {esc(job.get("operation_id") or case.get("operation_id"))}<br>실행 ID {esc(case.get("execution_id") or workflow.get("execution_id"))}<br>저장 revision {esc((workflow.get("site_draft") or {}).get("revision"))}</p><p>{esc(case.get("error",""))}</p>')
            for name in case.get('screens',[]):
                path=folder/name
                if path.exists():cards.append(picture(path,folder.name+'/'+name))
            cards.append('</section>')
    ledger=read(HOME/'authorized-live/agent-test.ledger.json')
    rows=ledger['requests'];known=sum((Decimal(r['charged_or_reserved_usd']) for r in rows if r.get('usage')),Decimal(0))
    held=sum((Decimal(r['charged_or_reserved_usd']) for r in rows if not r.get('usage')),Decimal(0))
    summary=read(HOME/'implementation-summary.json') if (HOME/'implementation-summary.json').exists() else {'status':'진행 중'}
    summary_html='<p>'+esc(summary['status'])+'</p>'
    for key,title in [('implemented','반영한 내용'),('actual_pass','실제로 확인한 흐름'),('remaining_in_order','남은 작업 순서')]:
        summary_html+=f'<h3>{title}</h3><ul>'+''.join('<li>'+esc(s)+'</li>' for s in summary.get(key,[]))+'</ul>'
    summary_html+='<details><summary>회귀시험과 보존한 실패</summary><pre>'+esc(json.dumps({key:summary.get(key) for key in ('regressions','retained_failures','scope')},ensure_ascii=False,indent=2))+'</pre></details>'
    primary=''
    for filename,label in [('live-03/image-01-terminal.png','실제 사진 생성 17개 현재 화면'),('mixed-resume-01/mixed-01-terminal.png','실제 혼합 입력 잔여 재개 25개 현재 화면'),('feedback-live-01/feedback-applied.png','실제 자연어 수정 적용'),('final-closed-reopen-02/saved-after-switch-3.png','Undo 저장본의 닫힌 재열기와 현재 3D 화면')]:
        if (HOME/filename).exists():primary+=picture(HOME/filename,label)
    text=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwinPulse 실제 사용자 흐름 검증</title><style>
body{{font:16px/1.6 system-ui,sans-serif;background:#f4f6f8;color:#18242d;margin:0}}main{{max-width:1180px;margin:auto;padding:24px}}
section,.box{{background:white;border:1px solid #ccd5dc;border-radius:12px;margin:20px 0;padding:20px}}h1{{font-size:30px}}h2{{font-size:22px}}
img{{display:block;max-width:100%;height:auto;border-radius:8px}}figure{{margin:20px 0}}figcaption{{color:#526573}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{padding:9px;border:1px solid #ccd5dc;text-align:left;vertical-align:top;overflow-wrap:anywhere}}.table{{overflow:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}p{{overflow-wrap:anywhere}}
</style><main><h1>TwinPulse 실제 사용자 흐름 검증</h1>
<p>2026년 10월 13일. 실제 Nebius Flash와 Nemotron Super, ordinary App/API, Chrome, 로컬 Isaac에서 수행한 제품 인수 시험입니다. 모델 간 비교 벤치마크나 사진 정확도 인증은 아닙니다.</p>
<div class="box"><h2>결론과 잔여 작업</h2>{summary_html}</div>
<div class="box"><h2>외부 호출과 비용</h2><p>실제 HTTP {len(rows)}회 · 수신 usage 기반 추정 USD {known} · usage 미확정 보호 예약 USD {held} · 이번 승인 상한 USD {esc(ledger['limit_usd'])}. 공급자 청구서가 아닙니다. 과거 시험 비용은 이번 추가 USD2와 별도이며 원 장부를 변경하지 않았습니다.</p>
<p>제품의 금액 승인·USD1·가격 만료 차단과, 이번 에이전트 외부 시험의 승인·비용 기록은 별개입니다. 추정 크기·품질 미완성·물리 검증 미실행 상태를 유지합니다.</p></div>
<section><h2>확인한 실제 화면</h2>{primary}</section><section><h2>실제 입력별 결과</h2><div class="table"><table><thead><tr><th>시험</th><th>입력</th><th>생성</th><th>전체 흐름</th><th>초</th><th>작업 ID</th><th>실행 ID</th><th>원 실패</th></tr></thead><tbody>{''.join(table)}</tbody></table></div></section>
<details><summary>전체 시험 화면과 원 실패</summary>{''.join(cards)}</details><section><h2>실행 원본과 재현 범위</h2><details><summary>원본 SHA와 소스 cohort</summary><pre>{esc(json.dumps(evidence,ensure_ascii=False,indent=2))}</pre></details>
<p>모델 응답은 고정 데이터가 아닙니다. 저장된 실제 모델 결과를 후속 복원 시험에 사용하는 경우 새 생성 성공으로 집계하지 않습니다. 새 소스의 회복은 원 실패를 덮어쓰지 않습니다. 실제 로봇·Cloud·OpenAI·개인 사진 전송은 이번 시험에 없습니다.</p></section>
<section><h2>사진 출처와 이용 범위</h2><p>원 사진의 저작권은 원저자에게 있습니다. 보고서 내 source-photo가 보이는 화면은 UI에 삽입/축소된 파생 표시이며 코드의 Apache-2.0으로 전환하지 않습니다.</p>
<p><a href="https://commons.wikimedia.org/wiki/File:Bedroom_with_a_almirah,_a_chair_and_TV_on.jpg">침실 Afifa Afrin</a> (1280px thumbnail, MPO original retained),
<a href="https://commons.wikimedia.org/wiki/File:Living_Room.jpg">거실 Tim Collins</a> (원본 변경 없음),
<a href="https://commons.wikimedia.org/wiki/File:Orange_Dining_Room.jpg">식당 Stilfehler</a> (원본 변경 없음).
모두 <a href="https://creativecommons.org/licenses/by-sa/3.0/">CC BY-SA 3.0</a> 고지와 적용되는 share-alike 조건을 보존합니다. 이 로컬 검증으로 GitHub 공개 권한을 추가하지 않습니다.</p></section></main></html>'''
    destination=HOME/'report-complete.html'
    with destination.open('x',encoding='utf-8') as stream:stream.write(text)
    print(json.dumps(dict(report=str(destination),http_requests=len(rows),estimated_usd=str(known),held_usd=str(held))))

if __name__=='__main__':main()
