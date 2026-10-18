# SPDX-License-Identifier: Apache-2.0
"""Generate a local evidence report from actual receipts, never run a device."""
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-app-field-tests-20261018'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def checksum(p):return sha256(p.read_bytes()).hexdigest()
def ids(v):
    if isinstance(v,dict):
        if v.get('attempt_id'):yield v['attempt_id']
        for item in v.values():yield from ids(item)
    elif isinstance(v,list):
        for item in v:yield from ids(item)

attempts=[];projects=set();model_ids=set();operations=[]
for p in sorted(OUT.glob('ui-*/result.json')):
    value=read(p)
    if value.get('project'):projects.add(value['project'])
    counts={k:len(value.pop(k,[])) for k in ('samples','fleet_requests')}
    attempts.append(dict(path=p.relative_to(OUT).as_posix(),sha256=checksum(p),counts=counts,result=value))
project_records=[]
for project in sorted(projects):
    folder=RUNTIME/'projects'/project;p=folder/'project.conversation.json'
    if p.exists():
        conversation=read(p);model_ids.update(ids(conversation))
        project_records.append(dict(project_id=project,conversation_sha256=checksum(p),
            generation_operation_ids=sorted({m['operation_id'] for m in conversation.get('messages',[]) if m.get('operation_id')})))
    for p in sorted((folder/'robot-operations').glob('*.json')):
        value=read(p);j=p.with_suffix('.events.jsonl')
        operations.append(dict(project_id=project,operation_id=value.get('operation_id'),robot_id=value.get('robot_id'),
            sha256=checksum(p),journal_sha256=checksum(j) if j.exists() else None,manifest=value.get('manifest')))
rates={m['model_id']:m for m in read(RUNTIME/'stage_model_catalog.json')['models']}
usage=[];cost=Decimal(0);unknown=Decimal(0)
for p in (RUNTIME/'ordinary-generation').glob('*.ledger.json'):
    for row in read(p).get('requests',[]):
        if row.get('attempt_id') not in model_ids:continue
        r=rates[row['model_id']];u=row.get('usage');estimate=None
        if u:
            estimate=(Decimal(str(r['input_per_million']))*u['prompt_tokens']+Decimal(str(r['output_per_million']))*u['completion_tokens'])/1000000
            cost+=estimate
        else:unknown+=(Decimal(str(r['input_per_million']))*r['context_tokens']+Decimal(str(r['output_per_million']))*row['max_tokens'])/1000000
        usage.append(dict(**row,ledger=p.name,ledger_sha256=checksum(p),estimated_usd=str(estimate)))
builds=[dict(path=p.relative_to(OUT).as_posix(),sha256=checksum(p),manifest=read(p)) for p in sorted(OUT.glob('build-*/dist/TwinPulse/windows-release-manifest.json'))]
offline=[dict(path=p.relative_to(OUT).as_posix(),sha256=checksum(p),result=read(p)) for p in sorted(OUT.glob('offline-*/result.json'))]
lifecycle=[dict(path=p.relative_to(OUT).as_posix(),sha256=checksum(p),result=read(p)) for p in sorted(OUT.glob('*-attempt.json'))]
for p in sorted(OUT.glob('normal*/result.json')):
    lifecycle.append(dict(path=p.relative_to(OUT).as_posix(),sha256=checksum(p),result=read(p)))
active=read(RUNTIME.parent/'installed/active-release.json')
requirements=[
 ('준비 순환 제거','IMPLEMENTED · 앱 감독시험 설정/정지 수집/0.03 전용 정지 관측','엄격 measured profile과 다른 scope. 명목값을 실측으로 승격하지 않음.'),
 ('앱만으로 초기 설정','설정 폼·검토·저장·다시 열기 · 설치 UI 판정 참조','참고 제원의 로봇 적합성/축은 현장 검토 필요. 외부 JSON/SHA 작성 불필요.'),
 ('11종 시험 실행 경로','정지8초/저속정지/전후10cm/좌우90/한회전/근접/정체/실제입력갭/정지5분 수집','실물 outcomes NOT_RUN. 고의 충돌/차체 고정/실제 Wi-Fi 단절 자동화 아님.'),
 ('연속 패드·채팅·다중 로봇','실제 Isaac SIM 인수 참조','사용자 로봇 한 대 OFF. 여러 실물 동시 성능 미검증. 60초 hold는 SIM.'),
 ('Stop·손 떼기','zero/OFF와 원 입력/task/nonce 폐기; 감독 확인은 최대15분 유지','LiDAR Off/연결/boot/config/기록fault는 감독 확인까지 폐기. 자동 재생 없음.'),
 ('독립 차체 관측','바퀴 seed/deskew 없는 bounded native scan tracker·stall 관측 경로','정합은 추정/accuracy UNQUALIFIED. 모호·stale body 시험 INCONCLUSIVE/정지. strict independent_required의 인증된 외부 계측 source 연결은 이 추정 tracker로 대체하지 않으며 계속 차단.'),
 ('Twin 이동 표시','작업자 초기 anchor + native 상대 pose·epoch 결속·stale 유지','실물/world 정확도 NOT_RUN. 새stream/scene/연결/epoch는 새 anchor 필요.'),
 ('장애물·역방향·정체','실제 publish 경계 native guard, signed wheel mismatch/jump/timeout','수신기준10cm와 실제 외곽10cm 보장은 다름. 실물 제동/낮은 장애물/유리 성능 미검증.'),
 ('로그/회복','operation 아래 trial ID·명령/원시/검토/receipt·고정4파일 반출','저장 오류/잘림은 incomplete; 이전 물리 실패/누락 sidecar를 복구했다고 하지 않음.'),
 ('실물 전체 성공','NOT_RUN · 로봇 OFF/충전 유지','이 보고서는 시험 소프트웨어 준비 및 SIM 결과. 실제 전압·스캔·바퀴·정지거리 PASS 아님.'),
 ('일반 시작·재시작','첫42.581s/중복owner·debug-off/실제native Alt+F4정리8.296s PASS. 두번째120s 기준FAIL 뒤121.597s에ready','실패를 PASS로 바꾸지 않음. 현재 실제 일반 창/Isaac 연결완료, 시작 응답성은 잔여. 당시 freeRAM 약0.69GiB, 단독 원인 미확정.'),
]
data=dict(schema='robot-app-field-test-report-1.0',generated_at=datetime.now(timezone.utc).isoformat(),
    scope='APP_TEST_PATHS_IMPLEMENTED_PHYSICAL_ACCEPTANCE_NOT_RUN',active_install=active,attempts=attempts,
    projects=project_records,operations=operations,builds=builds,offline=offline,lifecycle=lifecycle,
    requirements=requirements,model_usage=usage,new_http=len(usage),estimated_usd=str(cost),unknown_usd=str(unknown),
    additional_50_campaign_total=str(Decimal('.6283398')+cost+unknown),prior_20_campaign='14.9450973 including UNKNOWN .4770432; unchanged',
    hardware_actions=0,new_dependencies=0,main_model='existing configured model; actual ID not exposed',helpers=['Astra ultra read-only','Sol high UI'],
    preservation='Existing dirty files, original photographs, projects, ledgers, failures retained. No commit/push/public/cloud.',
    independent_review='Astra found bootstrap circularity, Arm expiry renewal, Stop epoch, collection movement, coverage, candidate abort, storage-before-stop, stale receipt, premature ACK, false proximity PASS, stream/gap and signed wheel flaws; corrected with scope-separated tests. Final read-only review is not hardware PASS.')
(OUT/'report-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def pre(v):return '<pre>'+escape(json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
def link(p,label):return '<a href="'+escape(p,quote=True)+'">'+escape(label)+'</a>'
html=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 앱 현장시험 준비</title><style>body{font:16px/1.6 system-ui;max-width:1180px;margin:24px auto;padding:24px;background:#f3f7f8;color:#183e43}section{background:white;padding:24px;margin:20px 0;border-radius:12px}h1,h2{color:#08675c}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #c8d6d8;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:440px;overflow:auto}img{max-width:100%;border:1px solid #cad7d7}.warn{color:#974700}</style>',
 '<h1>TwinPulse · 로봇 전원 이후 앱만으로 진행하는 시험 준비</h1><p class="warn">실물은 OFF. 소프트웨어 경로·실제 설치 SIM 인수와 하드웨어 성공을 구분합니다. 이전 제품 전체의 사진 품질/CAD/BRep 잔여를 완료했다고 하지 않습니다.</p>',
 '<section><h2>원인과 변경</h2><p>이전 버전은 정지 관측을 시작하는 데 이미 완성된 정지 측정 프로필이 필요했습니다. 엄격 보호 주행을 유지하면서 별도의 명시 감독시험 경로를 구현했습니다. App이 입력/원문/해시/시험 ID를 관리하지만, 해시는 측정 정확도 인증이 아닙니다.</p><p>감독 확인(최대15분)과 현재 모터 입력을 분리했습니다. 손을 떼거나 Stop을 누르면 실제 zero/OFF·새 generation·새 입력 필요 상태가 됩니다. 매번 전체 준비를 반복하지 않으며 과거 입력은 자동 재생하지 않습니다.</p>'+pre(active)+'</section>',
 '<section><h2>전원을 켠 뒤 앱 순서</h2><ol><li>같은 네트워크에서 등록 로봇 선택 → Connect. 현재 heartbeat/전압을 확인.</li><li>참고 제원·센서 위치·방향 검토/저장 → LiDAR On → 정지 수집(8초).</li><li>Prepare 확인 → 감독 조건 확인/Arm → Bootstrap stop(0.03m/s, 최대0.6초).</li><li>원래 패드/채팅 또는 각 시험 버튼. Stop/해제 뒤에는 새 입력. 근접정지 실제 간격은 현장 관측값을 별도 입력.</li><li>Twin에 추정 초기 위치를 놓으면 상대 스캔 추적을 표시. 모호/epoch 변경은 stale 및 재anchor 필요.</li><li>Operation logs에서 같은 실행 ID와 trial·원시 세그먼트·cleanup·미완료를 확인/다운로드.</li></ol><p>연결 또는 장치 준비에 실제 오류가 생기면 해당 ID로 원인을 확인하며 PASS를 보장하거나 하드웨어 오류를 무시하지 않습니다.</p></section>',
 '<section><h2>요구별 판정</h2><table><tr><th>요구</th><th>구현/시험</th><th>한계</th></tr>'+''.join('<tr>'+''.join('<td>'+escape(c)+'</td>' for c in row)+'</tr>' for row in requirements)+'</table></section>',
 '<section><h2>비용·승인·설정</h2>'+pre({k:data[k] for k in ('new_http','estimated_usd','unknown_usd','additional_50_campaign_total','prior_20_campaign','hardware_actions','new_dependencies','helpers','main_model')})+'<p>Flash/Nemotron·기존 승인 유지. 중복/실패도 위 장부 합산. 아카이브 단가에 의한 추정이며 청구서 아님. 새 의존성·실물 활성·Cloud·공개·Git 쓰기 없음.</p></section>']
for a in attempts:
    v=a['result'];folder=Path(a['path']).parent
    html.append('<section><h2>'+escape(a['path']+' · '+v.get('status','UNKNOWN'))+'</h2>'+link(a['path'],'모든 원관측/요청/실패 · SHA '+a['sha256'])+pre(dict(desktop=v.get('desktop'),project=v.get('project'),input_sha256=v.get('input_sha256'),counts=a['counts'],error=v.get('error'),
        http_errors=v.get('http_errors'),request_failures=v.get('request_failures'),expected_rejections=v.get('expected_rejections'),stop_fence_rejections=v.get('stop_fence_rejections'))))
    html.append('<table><tr><th>단계</th><th>판정</th><th>시간ms</th></tr>'+''.join('<tr><td>'+escape(s['name'])+'</td><td>'+s['status']+'</td><td>'+str(s.get('elapsed_ms'))+'</td></tr>' for s in v.get('steps',[]))+'</table>')
    for name in ('generated.png','held-60s.png','two-task-stop-all.png','field-offline-saved.png','field-cold-restored.png','cold-restored.png','physical-static-marker.png'):
        p=OUT/folder/name
        if p.exists():html.append('<figure><img loading="lazy" src="'+(folder/name).as_posix()+'"><figcaption>'+escape(name)+'</figcaption></figure>')
    html.append('</section>')
html.append('<section><h2>실패 이력 보존</h2><p>offline01의 불확실 진행값에 대한 기존 STALLED 기대는 실제 INCONCLUSIVE로 구분하는 변경에 맞춰 수정했습니다. 정지 요구는 그대로입니다. 새 replay 첫 대형chunk 거절과 PC fixture 필드 누락도 수정 후 별도 재시험했습니다. 첫 설치 fresh01은24개 기능단계 뒤, drawer 재열기 후 접힌 고급 프로필을 열지 않은 시험기 visibility 실패였습니다. 원 FAIL과 화면을 보존하고 시험기에서 명시적으로 열도록 수정했습니다. 그 설치본은 signed-wheel 감사/감독 consent 분리 이전 후보이며 최종본 성적에 합치지 않습니다.</p></section>')
for group in offline:
    html.append('<section><h2>'+escape(group['path'])+' · 보조시험</h2>'+link(group['path'],'원판정/SHA')+pre(group['result']))
    for row in group['result'].get('groups',[]):html.append('<p>'+link((Path(group['path']).parent/row['log']).as_posix(),row['name']+' · '+row['status'])+'</p>')
    html.append('</section>')
html.append('<section><h2>시작·정상 종료·일반모드 및 설치 검증</h2>'+pre(lifecycle)+'<p>Start 파일은 실행 도구로 동일 파일을 호출했습니다. Explorer 더블클릭과 OS 붙여넣기는 NOT_RUN. 설치된 같은 Electron BrowserWindow Test 경로를 사용하며 별도 Chrome/직접 변경 API/고정 모델 응답/상태 주입을 실제 사용자 시험으로 대체하지 않았습니다.</p></section>')
html.append('<section><h2>현재 정확한 잔여</h2><p>실물 현재 연결/배터리/장치 소유/센서 원각·clock·guard·바퀴·360/60초/5분·실제 제동/차체 정체·위치 정확도·종료 원문 반출은 로봇 OFF로 NOT_RUN입니다. 실제 Wi-Fi 장애·2대 실물·정밀 계측/industrial qualification·clean PC도 별도입니다. 상대 스캔 정합/참고 반경은 추정이며 strict measured profile을 자동 완성하거나 10cm 정지 보장을 만들지 않습니다. 인증된 strict independent source는 이 추정 tracker로 대체하지 않습니다. 유리/낮은 장애물/전선 등 사각이 있습니다. 이전 v527 이동 실패·누락 sidecar와 사진/CAD/BRep 제품 잔여는 보존합니다. 일반 두번째 시작은120초 기준FAIL/이후121.597초ready이며 저가용RAM/동시QA가 관측됐지만 단독 원인은 미확정입니다. 응답성 잔여를 전체PASS로 숨기지 않습니다.</p><p>이번 목적은 실물 시험을 시작할 소프트웨어 버튼/입력/결과/로그 경로를 미리 준비하는 것입니다. 전원 이후 실제 시험 실패가 나오면 수정이 필요할 수 있으며 모든 물리 결과 PASS를 사전에 보장하지 않습니다.</p></section>')
html.append('<section><h2>모든 ID·SHA·비용 원문</h2>'+link('report-data.json','전체 보고 자료')+pre(project_records)+pre(operations)+pre([dict(path=b['path'],build=b['manifest']['build_id'],source=b['manifest']['source_manifest_sha256']) for b in builds])+'</section></html>')
(OUT/'report.html').write_text('\n'.join(html),encoding='utf-8')
print(json.dumps(dict(report=str(OUT/'report.html'),new_http=len(usage),estimated_usd=str(cost),unknown_usd=str(unknown),campaign=data['additional_50_campaign_total'])))
