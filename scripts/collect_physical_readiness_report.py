# SPDX-License-Identifier: Apache-2.0
"""Local receipt-only report generation; no model, network or device execution."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-physical-readiness-20261018'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def attempt_ids(v):
    if isinstance(v,dict):
        if v.get('attempt_id'):yield v['attempt_id']
        for i in v.values():yield from attempt_ids(i)
    elif isinstance(v,list):
        for i in v:yield from attempt_ids(i)
attempts=[]
for p in sorted(OUT.glob('ui-*/result.json')):
    value=read(p)
    counts={key:len(value.pop(key,[])) for key in ('samples','fleet_requests')}
    attempts.append(dict(path=p.relative_to(OUT).as_posix(),raw_sha256=digest(p),raw_counts=counts,
        raw_evidence='Complete original observations and request order remain in the linked immutable result.json; not duplicated here',result=value))
projects=sorted({a['result']['project'] for a in attempts if a['result'].get('project')})
records=[];ids=set();operations=[]
for project in projects:
    p=RUNTIME/'projects'/project/'project.conversation.json'
    if p.exists():
        d=read(p);ids.update(attempt_ids(d))
        records.append(dict(project_id=project,conversation_sha256=digest(p),
            generation_operation_ids=sorted({m['operation_id'] for m in d.get('messages',[]) if m.get('operation_id')})))
    for p in sorted((RUNTIME/'projects'/project/'robot-operations').glob('*.json')):
        d=read(p);j=p.with_suffix('.events.jsonl');m=d.get('manifest',{})
        operations.append(dict(project_id=project,operation_id=d.get('operation_id'),robot_id=d.get('robot_id'),
            manifest=m,summary_sha256=digest(p),journal_sha256=digest(j) if j.exists() else None,
            events=d.get('events',[])))
catalog=read(RUNTIME/'stage_model_catalog.json');rates={m['model_id']:m for m in catalog['models']}
usage=[];cost=Decimal(0);unknown=Decimal(0)
for p in (RUNTIME/'ordinary-generation').glob('*.ledger.json'):
    for r in read(p).get('requests',[]):
        if r.get('attempt_id') not in ids:continue
        rate=rates[r['model_id']];u=r.get('usage');estimate=None
        if u:
            estimate=(Decimal(str(rate['input_per_million']))*u['prompt_tokens']+Decimal(str(rate['output_per_million']))*u['completion_tokens'])/1000000
            cost+=estimate
        else:unknown+=(Decimal(str(rate['input_per_million']))*rate['context_tokens']+Decimal(str(rate['output_per_million']))*r['max_tokens'])/1000000
        usage.append(dict(**r,ledger=p.name,ledger_sha256=digest(p),estimated_usd=str(estimate)))
builds=[dict(path=p.relative_to(OUT).as_posix(),manifest_sha256=digest(p),manifest=read(p)) for p in sorted(OUT.glob('build-*/dist/TwinPulse/windows-release-manifest.json'))]
offline=[dict(path=p.relative_to(OUT).as_posix(),result=read(p)) for p in sorted(OUT.glob('offline-*/result.json'))]
lifecycle=[dict(path=p.relative_to(OUT).as_posix(),result=read(p)) for p in sorted(OUT.glob('*-attempt.json'))]
if (OUT/'normal/result.json').exists():lifecycle.append(dict(path='normal/result.json',result=read(OUT/'normal/result.json')))
data=dict(schema='physical-readiness-report-1.0',generated_at=datetime.now(timezone.utc).isoformat(),
    status='PARTIAL_NOT_PHYSICAL_ACCEPTANCE',attempts=attempts,projects=records,operations=operations,builds=builds,
    offline=offline,lifecycle=lifecycle,model_usage=usage,new_http=len(usage),estimated_usd=str(cost),unknown_usd=str(unknown),
    additional_50_campaign_total=str(Decimal('.2689242')+cost+unknown),prior_20_campaign='14.9450973 including UNKNOWN .4770432',
    hardware_io=0,independent_models=['gpt-6-astra ultra','gpt-6.1-sol high'],main_model='existing setting; tool cannot inspect actual model ID',
    astra_review=read(OUT/'astra-review.json'),supplementary_ui=read(OUT/'supplementary-ui.json'),
    supplementary_ui_attempts=[dict(path=p.name,result=read(p)) for p in sorted(OUT.glob('supplementary-ui-*-attempt.json'))],
    astra_final_review=read(OUT/'astra-final-review.json') if (OUT/'astra-final-review.json').exists() else {'status':'IN_PROGRESS'},
    requirements=read(OUT/'requirements.json') if (OUT/'requirements.json').exists() else {'status':'IN_PROGRESS'},
    composer_review=read(OUT/'composer-ack-review.json') if (OUT/'composer-ack-review.json').exists() else {'status':'IN_PROGRESS'},
    composer_followup_reviews=[dict(path=p.name,result=read(p)) for p in sorted(OUT.glob('composer-*-fence-review.json'))],
    composer_astra_review=read(OUT/'composer-astra-review.json') if (OUT/'composer-astra-review.json').exists() else {'status':'NOT_RECORDED'},
    null_body_review=read(OUT/'astra-null-body-review.json') if (OUT/'astra-null-body-review.json').exists() else {'status':'NOT_RECORDED'},
    null_body_ui_review=read(OUT/'null-body-ui-review.json') if (OUT/'null-body-ui-review.json').exists() else {'status':'NOT_RECORDED'},
    active_install=read(RUNTIME.parent/'installed/active-release.json'))
(OUT/'report-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def pre(v):return '<pre>'+escape(json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
def link(p,label=None):return '<a href="'+escape(p,quote=True)+'">'+escape(label or p)+'</a>'
def requirements_table(value):
    rows=value.get('rows',[])
    if not rows:return pre(value)
    return '<p>'+escape(value.get('scope',''))+'</p><table><tr><th>요구</th><th>구현·검증</th><th>정확한 한계</th></tr>'+''.join(
        '<tr><td>'+escape(row['requirement'])+'</td><td>'+escape(row['result'])+'</td><td>'+escape(row['limits'])+'</td></tr>' for row in rows)+'</table>'
html=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 실물 준비 감사</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:32px auto;padding:24px;background:#f3f7f8;color:#173841}article{background:white;margin:20px 0;padding:24px;border-radius:12px}h1,h2{color:#08675c}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:460px;overflow:auto}img{width:100%;border:1px solid #ccd8dd}.warn{color:#9c4300}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:9px}</style>',
 '<h1>실물 제어 누락 감사·구현·설치 시험</h1><p class="warn">전체 실물 준비 완료 아님. 로봇 OFF/충전 유지, SSH·센서·모터 활성 0. 소프트웨어 구현과 실제 장비 인수를 구분합니다.</p>',
 '<article><h2>현재 설치본과 보고 범위</h2>'+pre(data['active_install'])+'<p>이번 로봇 연결·조종 요청의 구현/실제 SIM 인수와, 실측 자료가 있어야 하는 장비 인수를 분리합니다. 과거 사진 품질·CAD/BRep 전체 제품 완료 보고가 아닙니다.</p></article>',
 '<article><h2>요구사항별 판정</h2>'+requirements_table(data['requirements'])+'</article>',
 '<article><h2>현재 설치본의 실제 최종 인수</h2>']
for a in attempts:
    v=a['result']
    if v.get('phase') not in {'fresh','reopen'} or v.get('status')!='PASS' or v.get('desktop',{}).get('engine',{}).get('release_id')!=data['active_install']['release_id']:continue
    folder=Path(a['path']).parent
    html.append('<h3>'+escape(a['path'])+'</h3>'+link(a['path'],'원문 실행·단계·명령 ID')+pre(dict(project=v.get('project'),steps=len(v['steps']),launch_id=v['desktop']['engine']['launch_id'])))
    for name in ('held-60s.png','two-task-stop-all.png','physical-profile-editor.png','cold-restored.png','cold-backward-right.png'):
        if (OUT/folder/name).exists():html.append('<figure><img loading="lazy" src="'+(folder/name).as_posix()+'"><figcaption>'+escape(name)+'</figcaption></figure>')
html.extend(['</article>',
 '<article><h2>최종 감독 모드 계약 수정</h2><p>독립 차체 진행을 명시적으로 미검증으로 둔 감독 모드에서도 사용하지 않는 차체 전용4개 측정을 필수로 요구하던 P2를 수정했습니다. 이 모드에만 null을 원문 그대로 보존하고 body 진행/정체·slip은 UNKNOWN입니다. 독립 측정 필수 모드와 footprint·센서 변환·제동·바퀴 진행·시간 측정은 완화하지 않았습니다. 자동 실측값은 만들지 않았습니다.</p>'+pre(data['null_body_review'])+pre(data['null_body_ui_review'])+'</article>',
 '<article><h2>최종 fresh10 판정 보존</h2><p>build07 fresh10의 실제 기능25단계는 모두 PASS였으나 전체 HTTP 판정은 FAIL로 보존했습니다. 원drive 요청471301b8-f97e-4b9b-8f1b-0e10f37abc16은 동일 oldepoch의 Stop62d044d2-2fc1-4dca-82e1-f24c16f31a3e/200 뒤 fleet_motion_changed409를 받았습니다. 새epoch의 applied 확인은 당시 단계에서 통과했으나 시험기 최근1000표본 제한이 초기 표본을 마지막 판정 전에 버려 정확한 결속을 재검증하지 못했습니다. 수신 표본을5000개까지 원순서로 보존하고 초과시 시험FAIL로 기록하도록 변경했습니다. 제품/250ms 만료/Stop/기하 기준 변경이나 원판정 덮어쓰기가 아니며 새 fresh11과 분리합니다. fault POST abort와 viewport GET abort도 원문에 남깁니다.</p></article>',
 '<article><h2>두 로봇 연속 채팅과 Stop 응답의 구분</h2><p>build06 fresh09는17단계 뒤 Beta를 선택하지 않은 명령이 명시 focus 계약으로 차단되었습니다. 새 초안은 보존되었고 이전 ACK 결함의 재발은 아닙니다. 후속 시험은 실제 Beta 선택→새 초안 유지→전송을 따릅니다. tail06의15개 기능 단계는 통과했지만 병렬 drive/Stop HTTP 응답이1ms 역전되어 당시 전체FAIL 판정을 그대로 보존합니다. 최종 시험기는 정확한 로봇/연결/operation/old-epoch의 Stop 요청과 겹친 fleet_motion_changed만, Stop200의 새epoch와 별도 현재 엔진 applied-epoch가 일치하고 새drive가 아직 없는 관측에 결속해 분리합니다. Stop이 유일한 원인이라고 단정하지 않으며 일반409·다른실패는 제외하지 않습니다.</p></article>',
 '<article><h2>왜 전에는 준비됐다고 했는데 부족했나</h2><p>이전 v529는 실제 SIM2대 조종·채팅·로그 시험까지 성공했지만 물리 prepare/drive/LiDAR는 차단 stub이었습니다. SIM 성공을 실물 전체 준비로 확대 해석할 수 없습니다. Astra Ultra 독립검토로 실제 payload 유실, heartbeat age 덮어쓰기, grace-close 직후 EOF, Stop의 종료/전환 예외 누락, guard publish 미연결과 측정 프로필 부재를 확인했습니다.</p>'+pre(data['astra_review'])+'</article>',
 '<article><h2>이번 최초 실패와 재검증</h2><p>ui-fresh01/02/03은 SIM 전용판과 다른 개발 채널의 실제 모드 선택 화면을 시험기가 처리하지 못한 실패입니다. 실제 화면을 읽고 radio 선택→Create Twin으로 시험 경로만 수정했으며 모델 호출0입니다. ui-fresh04에서는 실제 모델 생성은 성공했지만 SIM 등록이15초 응답 제한으로 실패했습니다. API Stop 분류가 본문을 먼저 소비한 뒤 fleet dispatch가 다시 읽는 제품 결함을 확인하고 gated_body를 재사용하도록 수정했습니다. timeout 상향/실패 무시가 아닙니다.</p><p>이 결함은 앞선 Astra PC49의 검토 범위가 HTTP body 경계를 포함하지 않아 놓쳤습니다. Workspace→API single-read 회귀와 나머지5 Stop 경로 검토를 추가했습니다. 새 보조 시험 fixture의 import 경로/virtual port/read1 집계 오류도 최종 원문과 분리하며 offline03의 실패를 보존했습니다.</p><p>ui-fresh05에서는 등록은1.962초에 통과했지만 첫 held input의 병렬 요청이 뒤집혀 fleet_sequence409→UI Stop, 실제 이동2.5mm로 실패했습니다. UI는 drive 한 건만 outstanding으로 보내고 expiry를 넘기면 대기열/자동재개 없이 정지하도록 수정했습니다. Stop은 독립 전송하며 shutdown/scene 준비검사에 기다리지 않습니다. Fleet 일반 입력은 런처 상태 검사는 유지하고 불필요한 shutdown 준비검사만 생략합니다. 기존250ms 입력·속도·기하 기준은 늘리지 않았습니다. 최종 후보 build03 이전 실패도 삭제하지 않습니다.</p></article>',
 '<article><h2>후속 재현·원인</h2><p>build03/ui-fresh06은 새 입력이205ms 유효한데 과거 입력의 INPUT_STALE 결과가 새 입력까지 취소했습니다. 입력/결과 sequence를 결속하여 원래 만료를 늘리거나 옛 입력을 재생하지 않고 차단했습니다. build04 fresh07의 matrix 실패 메시지는 연결 단절로 뭉뚱그렸으나 실제 연결/센서는 유지됐고 drive dispatch0이었습니다. 실제 버튼을 화면 안으로 스크롤하고 클릭 해제→Stop과 다음 키 입력을 구분하도록 시험기를 고쳤습니다. ui-controls-build04b 17단계는 실제 창에서 통과했지만 fresh 성적에 합치지 않습니다.</p><p>cold04는 현재 Isaac 장면을 명시적으로 표시하지 않고 Connect해409, cold04b는 Reopen saved scene을 생략해버튼을 찾지 못했습니다. cold04c는 실제 Reopen→View current Twin→연결/후진/우회전 등9단계를 통과했지만 평상 해제 뒤 늦은 drive409 때문에 전체FAIL로 보존했습니다. 최종 시험기는 원래 drive→같은 robot/connection/old-epoch의 Stop200→old-drive409가 실제 관측된 경우만 종료 fence로 분리합니다. 일반409·무관 Stop·실패 Stop을 제외하지 않습니다.</p>'+pre(data['astra_final_review'])+'</article>',
 '<article><h2>추가 인수에서 찾은 채팅 결함</h2><p>build05 fresh08의 60초 연속 hold는61.040초/정상4방향까지 PASS. 뒤의 키보드 포커스 시험기 실패를 보존하고, 실제 패드 빈 셀 클릭으로 수정했습니다. tail05는 WASD/모든 방향키/Space와 단일 유한 명령은 통과했지만 두 로봇 연속 채팅 중 다음 초안이 사라져 Send10초 timeout이 발생했습니다. 이전 Stop 응답의 무조건 setText/setFile이 전송 후 작성한 새 초안까지 지우는 제품 결함이며, 시험을 느리게 하는 대신 요청ID와 각 편집 revision에 결속해 수정했습니다.</p>'+pre(data['composer_review'])+'</article>',
 '<article><h2>확인 요청·첨부 변환의 추가 회복</h2><p>과거 UNKNOWN 조회가 새 UNKNOWN의 대기 장치를 해제하는 경계와, 첨부 변환 중 fresh/admission이 바뀌면 Sending이 남는 경계도 수정했습니다. 오래된 결과는 상태 적용/오류/초안/busy 모두 변경할 수 없습니다. 전송 조건은 풀지 않고 POST0·원초안 보존과 자기 요청의 spinner 해제를 확인했습니다.</p>'+pre(data['composer_followup_reviews'])+pre(data['composer_astra_review'])+'</article>',
 '<article><h2>이번 구현</h2><ul><li>로봇별 persistent SSH worker, 현재 boot/release/source SHA·왕복 ACK에 결속한 heartbeat와 별도 배터리/센서/제어/기록/정리 상태. Connect만으로 센서나 모터를 켜지 않음.</li>',
 '<li>정확 native bytes와 시간창, ROS 원문, 입력/실제 publish/guard 결과를 한 operation ID에 연결. PC 비동기 회전 기록, SHA와 cold read, helper·qualification 고정 원로그 반출. 잘림/미저장/원격 정리 미확인은 incomplete.</li>',
 '<li>Prepare/qualification·프로필 검토 UI, 실제 publisher 직전 native guard. 무한 주행 대신 거리/각도 유한 명령. 만료와 focus 해제는 수동 intent만 중단, 연결·센서·독립 유한 작업과 분리.</li>',
 '<li>Stop은 종료·전환 중에도 전달, 기록 fsync가 Stop lock을 잡지 않음. finite→manual 전환의 watch 갱신 오류, 재Prepare 누적 보드로그 파싱 오류 수정. 부팅 torque ON 하나를 동작/안전 확인으로 쓰지 않음.</li>',
 '<li>명시적 실제 Twin 위치 추정 marker: 현재 revision에만 표시/저장, 클릭 조종기. static visualization이며 실제 이동 추적·월드 정합이 아님. root Start도 같은 설치판을 실행, 개발 Start는 별도.</li></ul></article>',
 '<article><h2>반드시 남는 것 / 아직 못하는 것</h2><ol><li>실측 geometry/extrinsic·차체 외곽·검출 coverage·pipeline 상한·제동/오차 프로필이 없습니다. 기존 raw/odom은 이를 대체하지 못합니다. 빈 양식/수동 작성 안내는 측정 지원이지 자동 측정 wizard가 아닙니다. 이 자료 없이 실제 drive는 막힙니다.</li>',
 '<li>실물 pose를 Twin 월드로 정합하여 움직임에 따라 marker를 갱신하는 기능은 미완성입니다. 현재 static estimate만 있습니다. 독립 차체 progress/slip은 UNKNOWN이며 바퀴 odom을 실제 차체 이동으로 위장하지 않습니다.</li>',
 '<li>새 경로의 실제 부팅/전압·LiDAR On/Off/restart·same-boot qualification·10cm 외곽 근접정지/탈출·정체·60초/360도/약5분·Wi-Fi 상실·원격 cleanup/반출은 전부 hardware NOT_RUN. 이전 v527 한세션360 실패/누락 sidecar는 그대로 보존.</li>',
 '<li>native OS 입력/Explorer 더블클릭/OS Ctrl+V·clean PC·실물2대는 별도 NOT_RUN. same installed Electron Test/Playwright는 native OS 클릭과 다릅니다. 일반모드 결과는 아래 시작 기록을 따릅니다.</li>',
 '<li>역사적 CAD/BRep 실제 변환·사진 품질/repair 전체 코호트 등 제품 전체 잔여는 이번 robot 범위로 해결했다고 하지 않습니다. 측정 wizard 자동수집·센서/월드 정합은 소프트웨어 잔여이며 단순 hardware NOT_RUN으로 축소하지 않습니다.</li></ol></article>',
 '<article><h2>모델·권한·비용</h2><p>독립 Astra Ultra와 UI Sol high, 최대 보조2명. 주 작업자 모델은 기존 설정/실제 ID 조회 불가. Flash/Nemotron 유지, 새 텍스트와 파생 렌더만 사용. 추가 HTTP '+str(len(usage))+' · 아카이브 단가 추정 USD '+str(cost)+' · 미확정 '+str(unknown)+' · 이번 추가50 캠페인 합계 '+data['additional_50_campaign_total']+'. 이전20 캠페인14.9450973(UNKNOWN .4770432 포함)은 별도/변경0. 청구서가 아닙니다. 새 의존성 설치·실물 활성·Cloud·공개·commit/push 0.</p></article>',
 '<article><h2>원자료 디코더와 보조시험</h2><p>보존 실제 raw4개 398,894nodes/990LiDAR rings를 원 vendor와 대조. ring 수는 차체 회전 수가 아님. Fake IO/논리시간·synthetic guard 시험은 실물 성공이 아니며 UI 성적과 합산하지 않습니다. 과거 광역136 중 환경3오류(PIL/systemPython·Win symlink권한·SIGHUP)는 은폐하거나 새 설치로 해결하지 않았습니다.</p>'])
for row in offline:
    html.append('<h3>'+escape(row['path'])+'</h3>'+pre(row['result']))
    for g in row['result'].get('groups',[]):html.append(link(str(Path(row['path']).parent/g['log']).replace('\\','/'),'시험 출력 원문 · '+g['name']))
html.append('</article><article><h2>시작·종료·native 시도</h2>'+pre(lifecycle)+'</article>')
html.append('<article><h2>UI 보조시험</h2>'+pre(data['supplementary_ui'])+link('ui-supplementary-final.log','최종 보조 시험 원문')+pre(data['supplementary_ui_attempts'])+'</article>')
for a in attempts:
    v=a['result'];folder=Path(a['path']).parent
    html.append('<article><details><summary>'+escape(a['path']+' — '+v['status']+' · '+str(sum(s['status']=='PASS' for s in v.get('steps',[])))+'/'+str(len(v.get('steps',[])))+' functional steps')+'</summary>'+pre({k:v.get(k) for k in ('desktop','project','input_sha256','error','http_errors','request_failures','fault_rejections','stop_fence_rejections','expected_rejections')}))
    for s in v.get('steps',[]):html.append('<details><summary>'+escape(s['status']+' · '+s['name']+' · '+str(s.get('elapsed_ms'))+'ms')+'</summary>'+pre(s)+'</details>')
    for name in v.get('screenshots',[]):
        if name.startswith('generation-') and name not in {'generation-0.png','generation-3.png'}:continue
        html.append('<figure><img loading="lazy" src="'+(folder/name).as_posix()+'"><figcaption>'+escape(name)+'</figcaption></figure>')
    html.append(link(a['path'],'모든 단계·상태 표본·원 실패')+'</details></article>')
html.extend(['<article><h2>정확한 ID·SHA·모든 비용·빌드 파일 인벤토리</h2>'+link('report-data.json','원문 보고 자료')+pre(records)+pre([dict(path=b['path'],build_id=b['manifest']['build_id'],source_sha=b['manifest']['source_manifest_sha256'],manifest_sha=b['manifest_sha256'],channel=b['manifest']['channel']) for b in builds])+'</article>',
 '<article><h2>보고서 자체 점검</h2><p>이 HTML의 로컬 링크·이미지 존재,18개 최종 판정과 동결 설치 fresh/cold 성적을 검사하고 렌더링을 확인했습니다. 별도 브라우저 사용은 이 로컬 문서의 시각 점검만이며 제품 인수로 세지 않습니다. 첫 문서용 headless runtime 부재 오류는 보존하고 이미 설치된 브라우저로 렌더링했습니다.</p>'+link('report-qa.json','보고서 SHA·렌더 점검')+'</article>',
 '<p>원사진/사용자 프로젝트/원장부/실패는 보존했습니다. 이번 보고서의 PARTIAL을 전체 완료로 해석하지 마세요.</p></html>'])
(OUT/'report.html').write_text('\n'.join(html),encoding='utf-8')
print(json.dumps(dict(report=str(OUT/'report.html'),attempts=len(attempts),new_http=len(usage),estimated_usd=str(cost),unknown_usd=str(unknown))))
