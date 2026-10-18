"""Collect immutable actual evidence, run readiness gate, create one local report."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def digest(path):return sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    for role in ('fresh','cold','lineage','lineage-cold','normal','restart','shutdown','supplementary','budget','installation'):
        parser.add_argument('--'+role,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve()
    normal=load(args.normal);restart=load(args.restart);shutdown=load(args.shutdown)
    lifecycle=dict(status='PASS' if shutdown['status']=='PASS' and restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF' else 'FAIL',
        release_id=normal['release_id'],source_sha256=normal['source_sha256'],normal_start_launch_id=normal['launch_id'],
        shutdown_clean=shutdown['shutdown_clean'],restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_launch_id=restart['launch_id'],restart_debug_listener_count=restart['debug_listener_count'],
        restart_app_listener_count=restart['app_listener_count'],restart_authenticated_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_ready_wait_ms=restart['ready_wait_ms'],
        normal_shutdown_input='Exact owned launcher graceful request, NOT native UI input; Test-mode Exit button separately verified.',
        references=[dict(path=str(p.resolve()),sha256=digest(p)) for p in (args.normal,args.restart,args.shutdown)])
    write(out/'normal-lifecycle.json',lifecycle)
    refs={role.replace('-','_'):getattr(args,role.replace('-','_')) for role in ('fresh','cold','lineage','lineage-cold','normal','supplementary','budget','installation')}
    refs['lifecycle']=out/'normal-lifecycle.json'
    manifest=dict(release_id=normal['release_id'],source_sha256=normal['source_sha256'],evidence=[dict(role=k,path=p.resolve().relative_to(out).as_posix(),sha256=digest(p)) for k,p in refs.items()],
        acceptance_tools=[dict(path=name,sha256=digest(ROOT/name)) for name in ['scripts/verify_robot_focus_gate.py','scripts/verify_robot_fleet_ui.mjs',
            'scripts/verify_robot_lineage_ui.mjs','scripts/verify_robot_lineage_offline.py','tests/integration/test_robot_focus_gate.py','tests/integration/test_fleet_elapsed_motion.py']])
    write(out/'evidence-manifest.json',manifest)
    gate=subprocess.run([sys.executable,str(ROOT/'scripts/verify_robot_focus_gate.py'),'--manifest',str(out/'evidence-manifest.json'),'--output',str(out/'gate-result.json')],cwd=ROOT)
    result=load(out/'gate-result.json');budget=load(args.budget);fresh=load(args.fresh)
    # Real older receipts said PASS but contain five unexplained GET failures.
    # Prove the final gate rejects them, without editing those receipts.
    older_fresh=out/'ui-02/result.json';older_cold=out/'ui-cold-02/result.json'
    if older_fresh.is_file() and older_cold.is_file():
        negative=deepcopy(manifest);negative['classification']='EVIDENCE_GATE_NEGATIVE_NOT_APP_ACCEPTANCE'
        for entry in negative['evidence']:
            previous=older_fresh if entry['role']=='fresh' else older_cold if entry['role']=='cold' else None
            if previous:entry.update(path=previous.relative_to(out).as_posix(),sha256=digest(previous))
        write(out/'gate-negative-get-manifest.json',negative)
        rejected=subprocess.run([sys.executable,str(ROOT/'scripts/verify_robot_focus_gate.py'),'--manifest',str(out/'gate-negative-get-manifest.json'),'--output',str(out/'gate-negative-get-result.json')],cwd=ROOT)
        negative_result=load(out/'gate-negative-get-result.json')
        if rejected.returncode!=1 or 'UNCLASSIFIED_REQUEST_FAILURE:fresh' not in negative_result['issues']:raise ValueError('Gate failed to reject actual unclassified GET evidence')
    artifact_index=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(out.rglob('*'))
        if p.is_file() and p.suffix.lower() in {'.json','.png','.log'}]
    write(out/'artifact-index.json',artifact_index)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse 로봇 집중시험 준비 인수</title>',
        '<style>body{font:16px/1.6 system-ui,sans-serif;color:#152634;max-width:1160px;margin:32px auto;padding:0 24px;background:#f8fafc}h1,h2{line-height:1.25}section{background:white;border:1px solid #d4dde4;border-radius:12px;padding:20px;margin:22px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;vertical-align:top;border:1px solid #d5dfe6;padding:8px;overflow-wrap:anywhere}code{overflow-wrap:anywhere}img{max-width:100%;border:1px solid #d5dfe6}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}a{color:#006b83}.status{font-size:22px;font-weight:700}figure{margin:20px 0}small{color:#526371}</style>',
        '<h1>TwinPulse — 로봇 집중시험 준비</h1><p>'+escape(datetime.now(timezone.utc).isoformat())+'</p>',
        '<p class="status">'+escape(result['status'])+'</p>',
        '<p>소프트웨어 경로 인수와 실물 시험 성공은 다릅니다. 실물은 OFF/충전 유지, 이번 SSH·실제 센서·모터 활성 0. 자동 주행·제동·world 위치 정합 성공을 선언하지 않습니다.</p>',
        '<section><h2>최종 설치본과 판정</h2><p>release <code>'+escape(normal['release_id'])+'</code><br>source SHA <code>'+escape(normal['source_sha256'])+'</code></p><pre>'+escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre></section>',
        '<section><h2>무엇을 고쳤는가</h2><p>저FPS에서 매 tick 50ms로 잘리던 SIM 시간을 원래 500ms watchdog 안에서 ≤50ms 충돌검사 substep으로 적분합니다. 유한 90°/360°의 속도·deadline은 늘리지 않았습니다. 첫 입력·방향 전환·만료 공백·task 전환의 수신 시각 경계를 보존하고, 중간 I/O 상태를 bounded queue로 순차 소비합니다. 500ms 이상 정지 시간은 재생하지 않습니다.</p><p>설치 무결성 검사에서 같은 호출의 조상 경로 검사만 재사용하고 모든 파일 SHA·symlink·미선언 파일 검사는 유지했습니다. 엔진 인증 직후/런처 준비 이전 PC 준비 요청409는 UI 버튼과 handler를 runtime ready에 결속하고 starting 표시를 우선해 해결했습니다. 보조시험/사용자 흐름/원 조건/릴리스/일반 재시작/미분류 GET 오류 누락을 거절하는 gate를 추가했습니다. Astra xhigh가 발견한 시간·완료 판정 경계를 수정·재검토했고 실제 인수는 Main이 순서대로 담당했습니다.</p></section>',
        '<section><h2>시험 방법과 차이</h2><p>일반 root Start는 실행 도구로 동일 파일을 호출했습니다(Explorer 더블클릭 NOT_RUN). 일반 8765/동일 owner/디버그19222=0과 재시작을 관측했습니다. Windows Computer Use는 좌표 geometry 오류·FrameArrived timeout으로 전체 native 입력 NOT_RUN입니다. 실제 인수는 같은 설치판의 명시 Test/Playwright BrowserWindow이며 별도 Chrome·직접 변경 API·고정 생성 응답·내부 상태 주입으로 대체하지 않았습니다. DOM 키 입력은 OS 입력/붙여넣기와 다릅니다.</p><p>일반 종료는 정확한 owned launcher의 graceful shutdown request로 관측했으며 native UI 종료라고 하지 않습니다. Test 창에서는 Exit 버튼을 실제 클릭했습니다. 의도적 지연 fault와 잘못된 프로필 거절은 정상 사용자 실패와 분리되어 원 result에 남아 있습니다.</p></section>',
        '<section><h2>최종 인수와 모든 시도</h2><p>한 번의 fresh 전체 통과와 cold/lineage를 별도 판정합니다. 이전 후보·원 실패·실패한 재시험은 삭제하거나 최종 PASS로 바꾸지 않습니다.</p><table><tr><th>기록</th><th>상태/실행</th><th>상세</th></tr>']
    parts.insert(-1, '<section><h2>원 차단 B01–B03와 동일 조건 재인수</h2><p>아래 원문은 이전 robot-twin-lineage 캠페인의 실패입니다. 이번 캠페인의 같은 이름 normal-01과 혼동하지 않습니다. 원 FAIL은 보존하며 최종 설치06의 후속 결과를 별도로 연결합니다.</p><table><tr><th>원 차단/원문</th><th>원인·변경</th><th>최종 동일 조건/한계</th></tr><tr><td>B01 · <a href="../robot-twin-lineage-20261018/ui-11/result.json">원 ui-11 FAIL</a><br>operation 8f1ed1ef821f40d7af9f3f624e8e0d3b<br>90° 요청/85.94° TASK_TIMEOUT</td><td>tick당 최대50ms 적분과 실제 벽시계 deadline 불일치. 허용 elapsed를 충돌검사 substep으로 적분하고 첫 입력·전환·만료 공백의 수신 경계를 보존. 속도/deadline/500ms watchdog 불변.</td><td><a href="ui-03/result.json">fresh03</a> 원90° 실제 delta1.5707963267948983rad/5.984s와 <a href="lineage-03/result.json">lineage03</a> 원90° 모두 완료. 10° 대체 아님.</td></tr><tr><td>B02 · <a href="../robot-twin-lineage-20261018/normal-01/result.json">원 normal-01 FAIL</a><br>entry120.210s 내 ready 미관찰</td><td>무결성 검사에서 동일 호출의 조상 경로 검사만 재사용; 모든 파일 SHA/링크/미선언 파일 검사 유지. 이 변경이 과거 전체 지연의 유일 원인이었다고 확정하지 않음.</td><td><a href="normal-06/result.json">일반06 43.817s</a> / <a href="normal-06-restart/result.json">동일조건 재시작43.244s</a>, 동일owner/8765 하나·debug19222 없음. 기준120s 상향 없음. Explorer/native 전체 입력은 NOT_RUN.</td></tr><tr><td>B03 · <a href="../robot-twin-lineage-20261018/ui-16/result.json">원 ui-16 FAIL</a><br>센서 stale409/preview_expired409·상태/이미지 abort</td><td>현재 인증 연결과 launcher ready를 분리하고 PC 준비 버튼/handler를 ready에 결속. 최신성·현재 frame guard 유지. 과거 abort 전체의 단일 원인은 미확정이며 이 시작 경합 수정으로 모두 설명하지 않음.</td><td>최종 <a href="ui-03/result.json">fresh03</a>·<a href="ui-cold-03/result.json">cold03</a>·<a href="lineage-03/result.json">lineage03</a>의 실제 LiDAR/현재 화면/기록 정상 경로 통과. 일반 HTTP/page/미분류 GET 오류0. 중간 ui02의 미귀속 GET5개는 별도 원실패/negative gate로 보존.</td></tr></table><p><a href="../robot-twin-lineage-20261018/report.html">이전 원 캠페인 전체 보고서</a>. 최종 정상 경로 재시험 통과는 모든 과거 네트워크 장애의 원인 규명이나 미래 무결함 보장이 아닙니다.</p></section>')
    attempts=[]
    for path in sorted(out.rglob('result.json')):
        row=load(path);rel=path.relative_to(out).as_posix();engine=row.get('desktop',{}).get('engine',{})
        item=dict(path=rel,sha256=digest(path),status=row.get('status'),phase=row.get('phase'),release=engine.get('release_id',row.get('release_id')),
            launch=engine.get('launch_id',row.get('launch_id')),project=row.get('project'),operation=row.get('operation_id'),
            steps=[dict(name=s.get('name'),status=s.get('status'),elapsed_ms=s.get('elapsed_ms'),error=s.get('error')) for s in row.get('steps',[])],error=row.get('error'))
        if any(not r.get('exiting') and not r.get('fault') for r in row.get('request_failures',[])+row.get('request_failed',[])):
            item['qualification']='NOT_ELIGIBLE_UNCLASSIFIED_REQUEST_FAILURES_DESPITE_RAW_STATUS'
        attempts.append(item);detail=json.dumps(item,ensure_ascii=False,indent=2)
        parts.append('<tr><td><a href="'+escape(rel)+'">'+escape(rel)+'</a></td><td>'+escape(str(item['status']))+'<br>'+escape(str(item.get('qualification','')))+'<br>'+escape(str(item['launch'] or ''))+'</td><td><details><summary>실행 ID·전체 단계·오류</summary><pre>'+escape(detail)+'</pre></details></td></tr>')
    parts.append('</table><p>인수 전 후보 build01은 제 실수로 observation-only였고 제외했습니다. build02–04는 추가 시간 경계 수정 이전 미인수 후보입니다. build05는 fresh27 PASS였으나 cold PC 준비에서 runtime_not_ready409가 실제 발생해 최종본에서 제외했습니다. 버튼 readiness 결속·시작 표시 우선순위를 고친 뒤 위 최종 release에서 재인수했습니다. 모든 ZIP·원문 manifest는 artifacts/robot-focused-test-20261018 아래 보존했습니다. normal 종료 직후 너무 빠른 Test Start1회는 lock 가드가 거절했고, 종료를 기다렸습니다. 단위시험 matcher/기존 로그 조회 timeout·modal에 가려진 cleanup 드라이버 실패도 additional-attempt-notes.json에 별도 보존합니다.</p><p><a href="additional-attempt-notes.json">추가 도구·보조 시험 실패 원문 요약</a> · 주 작업자 정확한 모델ID 도구 확인 불가 / 검토 gpt-6-astra xhigh 1명 / 같은 파일 동시 수정 없음.</p></section>')
    write(out/'attempts.json',attempts)
    parts+=['<section><h2>기능·품질·복원·응답성 판정</h2><table><tr><th>분류</th><th>판정 근거</th></tr>'+''.join('<tr><td>'+escape(k)+'</td><td>'+escape(v)+'</td></tr>' for k,v in [
        ('기능',load(args.fresh)['status']+' / same-installed fresh 전체; 위 단계 원문 참조'),
        ('복원/연결 기록',load(args.cold)['status']+' cold / '+load(args.lineage)['status']+' lineage / '+load(args.lineage_cold)['status']+' immutable history'),
        ('응답성',f"일반 {normal['ready_wait_ms']/1000:.3f}s / 재시작 {restart['ready_wait_ms']/1000:.3f}s / 각 UI 단계 실제 elapsed 원문"),
        ('사진·환경 품질','이번 새 생성은 텍스트 기능시험. 실측 치수·실제 방 사진의 배치 품질·장애물 완전성은 새 PASS가 아님. 이전 사용자 거실은 PARTIAL/uncertain 유지.'),
        ('실물/정합','NOT_RUN_ROBOT_OFF / world 계측·차체 정체·제동거리·2대 실물·실제 무선 장애 등 미검증')])+'</table></section>',
        '<section><h2>비용·원문 연결</h2><p>원 입력 SHA <code>'+escape(str(fresh.get('input_sha256')))+'</code>. 각 기록의 project/conversation/operation/command/trial/stream/frame/Twin revision과 raw SHA는 연결된 JSON에 보존됩니다. <a href="artifact-index.json">모든 JSON·화면·로그 bytes/SHA 목록</a></p><pre>'+escape(json.dumps({k:v for k,v in budget.items() if k not in ('requests','new_requests','files')},ensure_ascii=False,indent=2))+'</pre><p>usage 기반 추정이며 공급자 청구서가 아닙니다. 이전20 캠페인과 추가50 캠페인은 분리합니다.</p></section>',
        '<section><h2>전원을 켠 뒤 할 일</h2><ol><li>같은 LAN, 충전선 분리, 직접 감독·즉시 전원 차단 가능한 상태. 시야 밖/유선·끈·높낮이 장애물은 센서가 못 볼 수 있습니다.</li><li>일반 Start → 실제 시험하는 공간의 저장 Twin 열기/현재 Isaac 표시 → Robots에서 저장 이름 선택 → PC 준비·Check connection → Twin 로봇 Connect. 이번 새 텍스트 project는 SIM 기능시험용이며 실제 거실 모델로 혼용하지 않습니다. 사용자 거실 원사진 project는 chat_mvcck71j_6d94b13d(원사진SHA 6e812bd1d7a339660ed8c8a77c8af84e03437aa4cbba842a55e19cf05c81ba7f). 저장 context는 참조이며 실제 world 정합 증명이 아닙니다.</li><li>실제 연결·전압·boot 확인 → LiDAR On → 정지 native 수집/저장. 전압 미수신은 unknown이며 토크 ON만으로 안전 PASS가 아닙니다.</li><li>Supervised field setup의 명목값·한계를 검토 → Prepare → 감독 확인 → 저속 bootstrap stop 관측. strict measured 경로는 별도이며 이 감독 시험의 순환 선행조건이 아닙니다.</li><li>짧은 전후진/좌우·해제/Stop → 90°·한 바퀴+scan/연속 수신 → 현장 조건에 맞는 장애물 정지 관찰. 고의 충돌/차체 구속은 하지 않습니다.</li><li>11개 field trial 결과·관찰을 기록 → Operation/trial/native raw 반출 → Disconnect. 사용자 촬영에도 operation ID를 맞춥니다.</li></ol></section>',
        '<section><h2>정확한 미검증·별도 잔여</h2><p>실물 전원 후 SSH 인증/boot/배터리, 실제 native 수신·명령 ACK·차체 이동·정지거리·10cm 외곽 보장·정체/미끄럼·360도/60초/5분·실제 Wi-Fi 장애/cleanup·2대 실물은 NOT_RUN_ROBOT_OFF입니다. 엄격한 independent body 계측 공급자·world 정합 정확도는 미구현/미검증이며 앱의 추정 marker를 실제 위치로 부르지 않습니다. Clean PC·다기종·Explorer/OS 붙여넣기/native 전체 조작·사진/CAD/BRep의 이전 잔여도 이번 로봇 준비 PASS에 합산하지 않습니다. 안전 조건과 실제 자료가 충족되지 않으면 해당 가지의 정확한 사유를 기록하고 가능한 독립 시험부터 진행합니다.</p></section>',
        '<section><h2>실제 설치 App 화면</h2><p>각 화면은 해당 실행 디렉터리의 실제 캡처입니다. SIM은 USD kinematic/AABB LiDAR이며 실제 PhysX/RTX·물리 성공 증거가 아닙니다.</p>']
    for role in ('fresh','cold','lineage','lineage_cold'):
        path=refs[role];row=load(path);parts.append('<h3>'+escape(role)+'</h3>')
        for name in row.get('screenshots',[]):
            image=path.parent/name
            if image.is_file():
                rel=image.resolve().relative_to(out).as_posix();parts.append('<figure><img loading="lazy" src="'+escape(rel)+'"><figcaption>'+escape(role+' / '+name)+'</figcaption></figure>')
    parts.append('</section></html>')
    extras=[]
    for directory in ('routing-diagnostic-01','user-room-01'):
        extra=out/directory/'result.json'
        if extra.is_file():
            data=load(extra);extras.append('<section><h2>'+escape(directory)+'</h2><p>'+escape(data['status'])+'</p><pre>'+escape(json.dumps(data.get('steps',data),ensure_ascii=False,indent=2))+'</pre>')
            if directory=='user-room-01':extras.append('<img src="user-room-01/user-room-current.png"><p>기존 사진 Twin 재열기·표시만 통과. 사진의 소파/배치/형상은 여전히 PARTIAL/uncertain이며 실제 정합 또는 새 사진 품질 PASS가 아닙니다.</p>')
            else:extras.append('<p>조용한 상태에서 routing on/off8회는 GET 실패를 재현하지 못했습니다. 따라서 이전5GET의 단일 원인을 확정하지 않습니다. 최종03에서는 stable interception·시각/context/CDP 계측으로 미분류 GET0을 확인했으며, 이전02의 미귀속5개는 negative gate로 거절합니다. 제품 통신 결함을 전부 해결했다고 주장하지 않습니다.</p>')
            extras.append('</section>')
    parts[-1:-1]=extras
    with (out/'report.html').open('x',encoding='utf-8') as stream:stream.write('\n'.join(parts))
    print(json.dumps(dict(status=result['status'],report=str(out/'report.html'),gate_exit=gate.returncode),ensure_ascii=False));return gate.returncode
if __name__=='__main__':raise SystemExit(main())
