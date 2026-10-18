# SPDX-License-Identifier: Apache-2.0
"""Build a local evidence report. Reads receipts, never calls models or devices."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-fleet-20261017'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return sha256(path.read_bytes()).hexdigest()
def ids(value):
    if isinstance(value,dict):
        if value.get('attempt_id'):yield value['attempt_id']
        for item in value.values():yield from ids(item)
    elif isinstance(value,list):
        for item in value:yield from ids(item)

attempts=[];projects={'chat_mvch0p3i_c4ae7a86'};attempt_ids=set()
manual=OUT/'ui-build01/evidence.json'
if manual.exists():
    value=read(manual)
    value.update(path='ui-build01/evidence.json',status='PARTIAL_CONTAINS_FAILURE',project='chat_mvch0p3i_c4ae7a86',
        screenshots=[p.name for p in sorted(manual.parent.glob('*.png'))])
    for step in value['steps']:step.setdefault('status','OBSERVED_ONLY')
    attempts.append(value)
for file in sorted(OUT.glob('ui-build*/result.json')):
    value=read(file)
    value['evidence_file_created_utc']=datetime.fromtimestamp(file.stat().st_ctime,timezone.utc).isoformat()
    value['evidence_file_updated_utc']=datetime.fromtimestamp(file.stat().st_mtime,timezone.utc).isoformat()
    if not value.get('project'):
        launch=(value.get('desktop') or {}).get('engine',{}).get('launch_id')
        status=RUNTIME/'launches'/str(launch)/'engine-status.json'
        if status.is_file():
            project=(read(status).get('snapshot') or {}).get('project_id')
            if project and project.startswith('chat_'):value['project']=project
    attempts.append(dict(path=file.relative_to(OUT).as_posix(),**value))
    if value.get('project'):projects.add(value['project'])
project_records=[]
for project in projects:
    path=RUNTIME/'projects'/project/'project.conversation.json'
    if path.is_file():
        document=read(path);attempt_ids.update(ids(document))
        project_records.append(dict(project_id=project,conversation_session_id=document.get('session_id'),
            conversation_sha256=digest(path),generation_operation_ids=sorted({m['operation_id'] for m in document.get('messages',[]) if m.get('operation_id')})))
catalog=read(RUNTIME/'stage_model_catalog.json')
rates={v['model_id']:v for v in catalog['models']}
usage=[];total=Decimal(0);unconfirmed=Decimal(0)
for path in (RUNTIME/'ordinary-generation').glob('*.ledger.json'):
    ledger=read(path)
    for row in ledger.get('requests',[]):
        if row.get('attempt_id') not in attempt_ids:continue
        rate=rates[row['model_id']];tokens=row.get('usage');cost=None
        if tokens:
            cost=(Decimal(str(rate['input_per_million']))*tokens['prompt_tokens']+Decimal(str(rate['output_per_million']))*tokens['completion_tokens'])/1000000
            total+=cost
        else:
            reserve=(Decimal(str(rate['input_per_million']))*rate['context_tokens']+Decimal(str(rate['output_per_million']))*row['max_tokens'])/1000000
            unconfirmed+=reserve
        usage.append(dict(**row,estimated_usd=str(cost) if cost is not None else None,ledger=path.name,ledger_sha256=digest(path)))
campaign=read(OUT/'campaign.json')
campaign.update(status='NON_HARDWARE_VERIFICATION_PARTIAL',additional_campaign_usage_usd=float(total),
    additional_campaign_unconfirmed_usd=float(unconfirmed),new_http_requests=len(usage),invoice_verified=False,
    rate_basis='archived catalog estimate, not current price or verified invoice',
    updated_at=datetime.now(timezone.utc).isoformat())
(OUT/'campaign.json').write_text(json.dumps(campaign,ensure_ascii=False,indent=2),encoding='utf-8')
source_names=['packages/twinpulse_app/src/twinpulse_app/robot_fleet.py','packages/twinpulse_app/src/twinpulse_app/fleet_recorder.py',
 'packages/twinpulse_app/src/twinpulse_app/physical_fleet_adapter.py','packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
 'packages/twinpulse_app/src/twinpulse_app/api.py','packages/twinpulse_app/src/twinpulse_app/workspace_devices.py',
 'packages/twinpulse_app/src/twinpulse_app/conversation_service.py','packages/twinpulse_app/src/twinpulse_app/viewport_service.py',
 'packages/twinpulse_core/src/twinpulse_core/manual_motion_guard.py','scripts/twinpulse_fleet_runtime.py','scripts/twinpulse_live_viewport.py',
 'packages/twinpulse_robot_safety/teleop_contract.py','packages/twinpulse_robot_safety/teleop_worker.py',
 'packages/twinpulse_robot_safety/teleop_ros.py','packages/twinpulse_robot_safety/robot_journal.py',
 'apps/twinpulse-web/src/RobotFleet.tsx','apps/twinpulse-web/src/PhysicalRobotController.tsx',
 'apps/twinpulse-web/src/ChatWorkspace.tsx','apps/twinpulse-web/src/TwinViewport.tsx']
pins={name:digest(ROOT/name) for name in source_names}
builds=[]
for path in sorted(OUT.glob('build-*/dist/TwinPulse/windows-release-manifest.json')):
    builds.append(dict(path=path.relative_to(OUT).as_posix(),manifest_sha256=digest(path),manifest=read(path)))
summary=dict(schema_version='robot-fleet-local-report-1.0',generated_at=datetime.now(timezone.utc).isoformat(),
    campaign=campaign,rate_catalog_source=catalog['source_sha256'],rate_verified_at=catalog['verified_at'],
    models=usage,projects=sorted(projects),project_records=project_records,attempts=attempts,source_pins=pins,builds=builds,
    independent_decoder=read(OUT/'decoder-verification.json'))
summary['acceptance_scope']=[
 ('R01','PASS_OFFLINE','원 g/h timing + 실제 worker control() 루프의 pre-arm 늦은 nonce/expiry 폐기, 새 입력만 재개. 실물 출력 재인수 아님'),
 ('R02','PARTIAL','설치 Electron 실제 지연 fault와 offline epoch/sequence 회귀. 실제 Wi-Fi 단절·모든 loss/reordering 조합 인수 아님'),
 ('R03','PARTIAL','5.275초 논리시간 journal stall BUFFERING, 실제 비동기 snapshot writer stall/타 로봇 Stop 분리. 실물 worker의 실제 queue/byte/disk 포화 terminal 정책은 잔여'),
 ('R04','PARTIAL','helper 정상 close/EOF 분리 회귀 + 설치앱 정상 Exit. 실물 zero/serial 복원 재인수 NOT_RUN'),
 ('R05','PASS_SIM_ONLY','Isaac kinematic SIM 2대 독립 연결/명령/스캔. 실물+SIM 혼합 및 물리 2대는 NOT_RUN'),
 ('R06','PARTIAL','같은 설치 BrowserWindow 실제 badge 클릭·hold/release·keyboard/focus·camera. 재시작 epoch/anchor 보조 회귀와 native 입력을 구분'),
 ('R07','PASS_SIM_PARTIAL_GUARD','실제 USD AABB 근접정지·새 후진 탈출. directional/native-angle pure guard는 보조만, 실물 제동·TF·범위 미검증'),
 ('R08','NOT_RUN_RUNTIME','wheel-stall/body-progress/slip pure 판정 시험과 실제 kinematic SIM fault는 별개. PhysX 바퀴/차체 정체 인수 없음'),
 ('R09–R12','NOT_RUN_PHYSICAL','사용자 요청대로 로봇 OFF/충전 유지. 연결·전압·연속60초/한세션360·5분·실제 장애물·전원/통신상실 시험 없음'),
 ('R13','PASS_SIM_PARTIAL_PHYSICAL','SIM 한 작업 ID의 명령·관측·원문 다운로드·종료 manifest·cold 복원. 실물 cold reader 보조/과거 f/g/h timing 누락은 분리'),
 ('R14','PARTIAL','일반 설치 파일을 실행 도구로 호출한 동일 Electron Test 인수. debug-off/OS/native 세부 범위는 해당 기록을 따름; Explorer 더블클릭·clean PC NOT_RUN')]
summary['lifecycle_attempts']=[dict(path=p.relative_to(OUT).as_posix(),result=read(p)) for p in OUT.glob('*/result.json') if not p.parent.name.startswith('ui-build')]
summary['operation_integrity']=[]
summary['command_timelines']=[]
for project in sorted(projects):
    directory=RUNTIME/'projects'/project/'robot-operations'
    if not directory.is_dir():continue
    for path in sorted(directory.glob('*.json')):
        record=read(path);manifest=record.get('manifest',{});journal=path.with_suffix('.events.jsonl')
        events=record.get('events',[])
        event_sha=sha256(json.dumps(events,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
        journal_sha=digest(journal) if journal.is_file() else None
        summary['operation_integrity'].append(dict(project_id=project,operation_id=record['operation_id'],
            summary_sha256=digest(path),events_sha256_matches=event_sha==manifest.get('events_sha256'),
            journal_sha256_matches=journal_sha==manifest.get('journal',{}).get('sha256'),
            journal_sha256=journal_sha,event_count=len(events),declared_complete=manifest.get('complete'),
            physical_motion_verified=manifest.get('physical_motion_verified')))
        summary['command_timelines'].append(dict(project_id=project,operation_id=record['operation_id'],robot_id=record.get('robot_id'),
            last_engine_binding=manifest.get('last_engine_binding'),
            events=[event for event in events if event.get('kind') in {'command_accepted','stop_requested','motion_result','prepared','lidar_requested','connection_requested','app_closed','disconnected'}]))
(OUT/'report-data.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
def link(path,label):return '<a href="'+escape(path,quote=True)+'">'+escape(label)+'</a>'
def compact(value):
    if isinstance(value,dict):return {key:({'count':len(item),'sha256':sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()}
        if key=='points' and isinstance(item,list) else compact(item)) for key,item in value.items()}
    if isinstance(value,list):return [compact(item) for item in value]
    return value
sections=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse fleet verification</title><style>body{font:16px/1.6 system-ui;max-width:1180px;margin:32px auto;padding:0 24px;color:#18333c;background:#f4f7f8}h1,h2{color:#075e58}article{background:white;padding:20px;margin:20px 0;border-radius:12px}img{max-width:100%;border:1px solid #ccd8dc}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #c6d4d8} .warn{color:#9b4d00}</style>',
 '<h1>다중 로봇·Twin 조종·채팅·기록 — 실제 설치 시험</h1>',
 '<p class="warn">전체 제품/실물 완료 아님. 로봇 OFF·충전 유지, SSH/센서/모터 활성 0. 실제 Isaac SIM은 USD transform 기반 kinematic이며 PhysX/실물 주행 인수가 아니다.</p>',
 '<article><h2>변경과 확인 범위</h2><p>입력 만료·창 포커스/상태조회 지연과 연결 종료를 분리했다. 준비 전 입력을 폐기하고 현재 입력만 사용한다. 최대 속도와 기존 250ms/400ms 경계는 늘리지 않았다. 두 SIM 로봇의 개별 연결/선택/명령·LiDAR·작업 ID, 원래 채팅 생성 경로와 조종 경로, 실제 프레임에 결속된 badge를 구현했다. 디스플레이 I/O와 fleet 제어 교환은 별도 스레드다.</p>',
 '<p>작업 기록은 bounded 비동기 append 원문과 atomic JSON 요약/종료 SHA를 남긴다. cold 재열기에는 정의·마지막 모델 위치·역사 작업 ID만 복원하고 연결/held/운전권한은 복원하지 않는다. 미완료 journal은 복구해도 INCOMPLETE다. 큰 로그는 화면 요약과 원문 다운로드를 분리했다.</p></article>',
 '<article><h2>최초 실패·복구 보존</h2><ul><li>build01 환경 요청에 로봇이 언급되면 이동 명령으로 잘못 분기: 0 HTTP, 실패 화면 보존. scene brief 선행 분기로 수정 후 원문 재시험.</li>',
 '<li>build01 로그 클릭 후 CDP/접근성 조회 응답 timeout. 662,070B·331 events 전체 JSON DOM 출력이 원인 후보이며 확정 인과로 주장하지 않는다. 화면 요약을 bounded로 수정. reload 뒤에도 접근 실패하여 소유 launcher의 cooperative shutdown request로 정리. 이것은 정상 Exit 사용자 인수로 세지 않는다.</li>',
 '<li>build02 badge 겹침으로 Alpha 클릭을 Beta가 가로챔: force click하지 않고 실패 보존. 이미지 fit 내부 packing·원래 투영점 leaderline 적용 후 양쪽 실제 클릭 재인수.</li>',
 '<li>build03 PC PAUSED 응답 뒤 최종 Isaac pose가 약0.1초 늦게 도착해 keyboard 해제 시험 실패. 요청 수락을 실제 정지로 세지 않고 applied_motion_epoch를 추가했다. fresh engine 동일 epoch 확인 이후에만 위치 유지 판정. 기하 허용 오차는 확대하지 않음.</li>',
 '<li>추가 독립 검토: 준비 직후 늦은 nonce가 enabled worker를 종료하던 경로, physical cleanup/operation snapshot 쓰기의 fleet 전역 lock, Isaac 재시작 sequence 초기화 누락을 수정. 이때 편집 중인 physical footer 시험을 광역 실행해 1 FAIL이 발생한 기록도 최종 재시험과 분리한다.</li>',
 '<li>후속 lock 변경 독립 검토에서 이전 Disconnect가 재연결된 새 recorder를 닫는 경합과 append/close의 미저장 complete 경합을 발견했다. operation/recorder ID를 종료 전에 캡처하고 현재 row-op 일치할 때만 표시를 바꾼다. append admission/close receipt는 같은 recorder lock으로 결속하되 join은 lock 밖이다. JSON 직렬화/SHA는 전체 fleet lock 밖으로 옮겼다.</li>',
 '<li>build05 첫 fresh는 기능16단계 PASS지만 구 시험기가 모든409를 동일 오류로 집계해 전체FAIL. 응답 code를 저장하지 않았으므로 원2건의 정체는 미확정으로 보존한다. 후속 시험기는 명시 지연한 drive 요청에 한해서만 정확한 만료/구motion_epoch/sequence409를 fault 증거로 분리한다. 일반 오류를 제외하지 않으며 제품 코드는 바꾸지 않았다.</li>',
 '<li>build05 다음 시작에서는 Isaac starting0:34 동안 New chat이 비활성이라10초 클릭 제한FAIL/모델0. 시작 중 입력 제한은 제품에 남아 있다. 연결 완료 UI를 별도 대기·측정하고 인수하는 것과 즉시 사용 가능한 성능PASS를 구분한다. 각 시험기의 HTTP표는 수신>=400 응답이며 requestfailed/ERR_ABORTED 전체 집계가 아니다.</li>',
 '<li>native Computer Use: 접근성 읽기 성공, 클릭 geometry unavailable·FrameArrived timeout. 동일 설치 BrowserWindow Test/Playwright로 대체. Explorer 더블클릭·OS 입력·native 창 크기 조절은 NOT_RUN.</li>',
 '<li>설치 완료를 기다리지 않아 구 release가 시작된 첫 race는 정상 Exit 후 재실행. 테스트 경로는 새 포트/별도 Chrome/내부 API 주입이 아니다.</li>',
 '<li>초기 unittest bootstrap/module 이름 실수 및 viewport helper import 5 errors는 후속 올바른 경로·회귀로 수정/분리. raw 성공 수 합산으로 감추지 않는다.</li></ul></article>',
 '<article><h2>비용·모델·데이터</h2><p>이번 실제 모델 HTTP '+str(len(usage))+'회, 아카이브 단가 기반 추정 USD '+str(total)+', 새 미확정 예약 USD '+str(unconfirmed)+'. 추가 승인 USD50 안에서 진행. 이전 USD14.9450973/20(UNKNOWN0.4770432 포함)은 별도 보존했다. 청구서·현재 단가 확인 아님. Flash/Nemotron 조합 유지. 새 전송은 시험 텍스트와 그 파생 Isaac 렌더이며 새 개인 사진/CAD·새 공급자 전송 없음.</p>',
 '<p>UI 보조: GPT‑6.1 Sol high. 독립 원인/guard 보조: Astra xhigh. 주 작업자 모델은 이 대화 설정을 변경하지 않았으며 실제 모델 ID를 조회·변경하는 도구가 없다. 보조 최대2명. commit/push/Cloud/새 의존성 설치 없음.</p></article>',
 '<article><h2>보조 검증(실제 사용자 인수와 별도)</h2><ul><li>최종 UI 선택4파일302 PASS·TypeScript/build PASS. 과거5파일374와 일부 집합이 다르므로 더하지 않음. jsdom canvas 미구현 warning은 새 설치로 숨기지 않았고 실제 Isaac 화면 인수와 구분.</li><li>최종 Python 결과는 아래 최종 시험 기록을 따른다. 연속 입력·buffered protocol9, 실제 worker loop6, legacy teleop28은 겹치는 광역 집합과 합산하지 않음. 지연/디스크/장비 fixtures는 실제 하드웨어 성적이 아니다.</li><li>신규 pure guard25 + 기존20 =45 PASS. 후방 unknown은 전진을 막지 않고 필요한 방향만 검사. wheel/body 진행 분리. 측정 extrinsic/footprint/timing 없으면 실물 변환 거절.</li><li>vendor parser 후보: 4원시자료398,894 nodes·990개 LiDAR ring(차체990회전 아님), 첫25개씩 복구, 독립 원 parser 대조. 23h 두 번째 packet24개 angle 변화는 원 vendor 이전 interval fallback 결과로 별도 보존. 오프라인만 PASS.</li></ul>',
 link('decoder-review.md','decoder 원인·전 시도·한계')+' · '+link('../../docs/verification/robot-control-conditions-20261017.json','주요 제한 감사표(전체 개수 주장 아님)')+'</article>',
 '<article><h2>정확한 잔여 / 다음 실물 세션 전 조건</h2><ol><li>pure native-angle/footprint/wheel-body guard를 실제 로봇 publish 경로에 연결하고 측정된 sensor-to-base/footprint·거리/방향·빔 시각을 결속해야 한다. 현재 physical prepare/drive/LiDAR capability=false이며 소스 준비와 작동 완료를 구분한다.</li>',
 '<li>decoder 후보는 원본을 수정하지 않았고 로봇 driver에 배포하지 않았다. 실제 serial/ROS native PointCloud 경로·TF·보정은 NOT_RUN. f/g/h 과거 timing sidecar 누락은 복구되지 않았다.</li>',
 '<li>실물에서는 release 토크OFF/재arm 정책이 남아 있고 첫 arm 때 추가 새 누름, 실제 protocol/recorder 포화·쓰기 실패의 terminal 경로가 남는다. 짧은 protocol 지연만 persistent manual BUFFERING으로 바꾸었으며 nonce/source age는 갱신하지 않는다. invalid-expiry sequence admission은 PC/worker에서 수정·회귀했으나 legacy 수동 경로의 project=default 계보는 후속 정리가 필요하다. 이번 PC/SIM 성공으로 무기한 실물 연속성을 보장하지 않는다.</li>',
 '<li>실물 R09–R12: 일반 설치에서 정상 부팅·현재 전압/실시간 heartbeat·약5분 연속/60초 회전·한세션360도·근접정지/탈출/통신상실·반출 footer/SHA를 한 세션에 확인해야 한다. 지금 로봇을 켜 달라고 요청하지 않는다.</li>',
 '<li>physical pool은 로봇별 객체/endpoint/owner/로그 격리를 제공하지만 Check Connection은 일회성 읽기다. live battery/heartbeat·독립 native sensor session은 미구현이며 단순 하드웨어 NOT_RUN으로 축소하지 않는다. cold physical reader는 장비권한을 복원하지 않는 보조 시험과 실제 UI 인수를 분리한다. SIM battery는 unavailable·simulated이며 임의 퍼센트를 만들지 않았다.</li>',
 '<li>추가 물리2대/clean PC/Explorer 더블클릭/native OS Ctrl+V·키보드·일반 debug-off 창 전체 조작/사진 품질 전체 회귀는 NOT_RUN. 이번 새 사진 생성은 수행하지 않았다. 이전 품질 미통과를 승격하지 않는다.</li></ol></article>']
sections.append('<article><h2>R01–R14 기능별 인수 — 전체 완료로 합치지 않음</h2><table><tr><th>ID</th><th>판정</th><th>근거·한계</th></tr>'+''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in summary['acceptance_scope'])+'</table></article>')
sections.append('<article><h2>저장된 SIM 원문 무결성 — 읽기 대조</h2><pre>'+escape(json.dumps(summary['operation_integrity'],ensure_ascii=False,indent=2))+'</pre><p>각 manifest의 events SHA와 실제 append journal bytes SHA를 비교한다. COMPLETE는 기록의 종료·누락 판정이지 실물 주행 성공을 뜻하지 않는다.</p></article>')
sections.append('<article><h2>프로젝트·생성 실행 ID 인덱스</h2><pre>'+escape(json.dumps(project_records,ensure_ascii=False,indent=2))+'</pre></article>')
sections.append('<article><h2>로봇별 한 ID의 명령·정지·결과 계보</h2>'+''.join('<details><summary>'+escape(item['project_id']+' / '+item['operation_id'])+'</summary><pre>'+escape(json.dumps(item,ensure_ascii=False,indent=2))+'</pre></details>' for item in summary['command_timelines'])+'</article>')
normal=OUT/'normal-build05/result.json'
if normal.is_file():sections.append('<article><h2>일반 debug-off 실행 — 기능 전체 인수 아님</h2><pre>'+escape(json.dumps(read(normal),ensure_ascii=False,indent=2))+'</pre></article>')
offline=OUT/'offline-final/result.json'
if offline.is_file():
    checks=read(offline)
    sections.append('<article><h2>최종 무장비 시험 원문 — '+escape(checks['status'])+'</h2>'+''.join(
        '<p>'+escape(row['name'])+' · exit '+str(row['exit_code'])+' · '+str(round(row['elapsed_s'],3))+'s · '+
        link('offline-final/'+row['log'],'출력 원문')+'</p><pre>'+escape((offline.parent/row['log']).read_text(encoding='utf-8',errors='replace')[-1200:])+'</pre>'
        for row in checks['commands'])+'</article>')
for attempt in attempts:
    sections.append('<article><h2>'+escape(attempt['path'])+' — '+escape(attempt['status'])+'</h2>')
    sections.append('<p>launch '+escape(str((attempt.get('desktop') or {}).get('engine',{}).get('launch_id') or attempt.get('launch_id')))+' / project '+escape(str(attempt.get('project')))+' / input SHA '+escape(str(attempt.get('input_sha256')))+'</p>')
    for step in attempt.get('steps',[]):
        sections.append('<p>'+escape(step['status']+' · '+step['name'])+' · '+str(step.get('elapsed_ms'))+' ms</p>')
        if step.get('evidence') is not None:sections.append('<details><summary>실제 측정값·작업 ID</summary><pre>'+escape(json.dumps(compact(step['evidence']),ensure_ascii=False,indent=2))+'</pre></details>')
    if attempt.get('error'):sections.append('<pre>'+escape(attempt['error'])+'</pre>')
    if attempt.get('http_errors'):sections.append('<h3>예상 밖/분류 불가 HTTP — 실패 보존</h3><pre>'+escape(json.dumps(attempt['http_errors'],ensure_ascii=False,indent=2))+'</pre>')
    if attempt.get('fault_rejections'):sections.append('<h3>명시 지연 fault에 결속된 입력 거절</h3><pre>'+escape(json.dumps(attempt['fault_rejections'],ensure_ascii=False,indent=2))+'</pre><p>정확한 drive 요청·지연 표식·409·만료/구세대/sequence 코드가 모두 일치한 경우만 별도 분류했다. 일반 요청/Stop/연결 오류는 제외하지 않는다.</p>')
    parent=Path(attempt['path']).parent
    for name in attempt.get('screenshots',[]):
        if name.startswith('generation-') and name not in {'generation-0.png','generation-3.png'}:continue
        sections.append('<figure><img loading="lazy" src="'+(parent/name).as_posix()+'"><figcaption>'+escape(name)+'</figcaption></figure>')
    sections.append(link(attempt['path'],'모든 단계·측정값·HTTP·판정 원문')+'</article>')
sections.append('<article><h2>원본과 정확한 소스/빌드 계보</h2><p>'+link('report-data.json','모든 실행·비용·모델 usage·source/ZIP manifest SHA JSON')+'</p><pre>'+escape(json.dumps(pins,indent=2))+'</pre></article></html>')
sections.insert(-1,'<article><h2>모든 시작·종료·복구 시도</h2>'+''.join('<p>'+link(v['path'],v['path'])+' — '+escape(v['result'].get('status','UNKNOWN'))+'</p>' for v in summary['lifecycle_attempts'])+'</article>')
(OUT/'report.html').write_text('\n'.join(sections),encoding='utf-8')
print(json.dumps(dict(report=str(OUT/'report.html'),http=len(usage),estimated_usd=str(total),unconfirmed_usd=str(unconfirmed),attempts=len(attempts))))
