# SPDX-License-Identifier: Apache-2.0
"""Local supplementary checks/report. Never connects to a robot or provider."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import hashlib,html,json,os,re,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-timing-policy-20261020'
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.robot_control_timing import TIMING_POLICY


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def identity(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def check(item):
    name,command,cwd=item;start=time.monotonic()
    run=subprocess.run(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/(name+'.log')).write_bytes(run.stdout)
    text=run.stdout.decode('utf-8',errors='replace')
    return dict(name=name,status='PASS' if run.returncode==0 else 'FAIL',exit_code=run.returncode,
                elapsed_s=time.monotonic()-start,command=command,log=identity(OUT/(name+'.log')),
                scope='Supplementary no-device tests, not physical or user-journey acceptance')


def main():
    py=str(ROOT/'.venv/Scripts/python.exe')
    suite=lambda name,directory,pattern:(name,[py,'-m','unittest','discover','-s',directory,'-p',pattern,'-q'],ROOT)
    suites=[suite('safety','packages/twinpulse_robot_safety/tests','test*.py'),
        suite('pc-live-session','tests/integration','test_physical_live_session.py'),
        suite('legacy-controller','tests/integration','test_physical_controller.py'),
        suite('fleet','tests/integration','test_robot_fleet.py'),
        suite('manual','tests/integration','test_manual_controller.py'),
        suite('local-navigation','packages/twinpulse_core/tests','test_local_navigation.py'),
        suite('native-geometry','packages/twinpulse_core/tests','test_manual_motion_guard.py'),
        ('ui',[str(ROOT/'apps/twinpulse-web/node_modules/.bin/vitest.cmd'),'run','src/RobotFleet.test.tsx','src/api.test.ts','src/PhysicalRobotController.test.tsx'],ROOT/'apps/twinpulse-web')]
    with ThreadPoolExecutor(max_workers=3) as pool:checks=list(pool.map(check,suites))
    local=Path(os.environ['LOCALAPPDATA'])/'TwinPulse'
    install=read(OUT/'installation.json');ui=read(OUT/'ui-02/session.json')
    operation=read(OUT/'ui-02/operation-ui-response.json')
    cleanup=read(local/'runtime/launches/b7de3e12cca54b43b78308d73f6e3d28/cleanup-receipt.json')
    (OUT/'cleanup-receipt.json').write_text(json.dumps(cleanup,indent=2),encoding='utf-8')
    result=dict(schema='robot-timing-policy-change-1.0',at=datetime.now(timezone.utc).isoformat(),
        verdict='TIMING_CHANGE_INSTALLED_SCOPED_SIM_VERIFIED_NOT_FULL_PHYSICAL_ACCEPTANCE',
        policy=TIMING_POLICY,installation=install,checks=checks,ui_session=ui,operation=operation['operation_id'],
        source_twin_context=operation['manifest']['source_twin_context'],manifest=operation['manifest'],
        operation_response=identity(OUT/'ui-02/operation-ui-response.json'),cleanup=cleanup,
        original_failure_operation='39557dac1c1f44d3aebc01615d2df74b',
        original_timing_recheck='Recorded 254.149ms age and207.085ms odom interval pass only the new timing limits; original physical failures remain failures. No physical90/360 success inferred.',
        limitations=['Robot remained disconnected: no SSH, raw acquisition, motor, braking or physical replay tests.',
            'Same installed Test BrowserWindow UI; root Test Start called through exec, not Explorer/native OS input.',
            'Saved scene restored: no fresh generation or photo-quality claim. Actual USD kinematic readback is not physical wheel/body evidence.',
            'Original UI-01 card/panel locator timeout reset the recorder; independent UI-02 is not combined into a whole fresh journey.',
            'Browser operation download cancelled in repeated actual-button attempts. Root cause UNKNOWN; actual UI GET response1284events/FINALIZED retained, not a download PASS.',
            'UI-02 recorder reset during download wait before video finalization. Original JPEG frames retained, no fabricated timestamp reconstruction or completed video claim.',
            'Prior physical command result/nonce reservation/late HTTP epoch risks remain outside this timing change. No full readiness verdict.',
            'Existing stricter measured profiles are not silently rewritten or promoted to new measurements.'],
        development_attempts=['Initial supplementary runs exposed old250ms fixture expectations, three standalone test imports missing the new core dependency, and an old string QoS fixture. They were corrected and all final checks rerun.',
            'The first install helper omitted core/provider module search paths and exited before installation. Correct module roots installed the single verified package.',
            'Initial two multi-file patches were rejected because duplicate file operations were present; no partial application was claimed.'],
        provider_http=0,provider_usd=0,additional_50_remaining_usd=46.8551834,old_20_ledger='unchanged/separate',
        publication='No commit/push/upload/release/deletion/new dependency or OS/ROS/Isaac installation')
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda x:html.escape(str(x))
    parts=['<!doctype html><meta charset="utf-8"><title>TwinPulse 350/300ms 정책 변경</title>',
        '<style>body{font:16px/1.65 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#19323d}td,th{border:1px solid #ccd;padding:10px;text-align:left}table{border-collapse:collapse;width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}.warn{padding:16px;background:#fff1d8}</style>',
        '<h1>TwinPulse 입력350ms / 오도메트리300ms 변경 · 2026-10-20</h1>',
        '<p class="warn">설정 변경·설치·경계/원문 재검사와 저장 장면 SIM 조작은 확인했습니다. 실물 연속주행 완료 또는 전체 준비 완료 판정이 아닙니다. 로그 다운로드 취소와 미완성 녹화는 별도 실패/미검증으로 남깁니다.</p>',
        '<h2>확정한 기준</h2><table><tr><th>항목</th><th>기준</th><th>의미</th></tr>',
        '<tr><td>입력 유효기간</td><td>원 입력 나이 &lt;350ms</td><td>원 생성/nonce+PC 대기 포함. 수신·기록·재시도로 새350ms 부여하지 않음.350ms부터 거절/정지.</td></tr>',
        '<tr><td>오도메트리 표본 간격</td><td>0&lt;간격≤300ms</td><td>초과 TASK_ODOM_SAMPLE_GAP / 역행·비정상시각 TASK_ODOM_TIME_INVALID. 실제 기하점프 TASK_ODOM_JUMP 별도.</td></tr>',
        '<tr><td>그 외 보호</td><td>원 센서 나이200 / C++400 / 존재500 / native350 / ICP80ms</td><td>최신성·속도·위치/각도·Stop 기준 유지.50ms 입력창 목표/100ms UI 갱신 주기를350ms로 느리게 바꾼 것이 아님.</td></tr></table>',
        '<p>공식 제조사 기준이나 통계 자동산출이 아니라 사용자가 명시한 개발 정책입니다. 기존 실측 프로필의 더 엄격한 제한은 자동 덮어쓰기하지 않습니다. 같은 속도에서 입력 한도100ms 증가의 등속 이동분은0.03m/s에서3mm지만, 물리 제동거리나 안전 인증을 뜻하지 않습니다.</p>',
        '<h2>설치·원문 결속</h2><pre>'+esc(json.dumps(install,ensure_ascii=False,indent=2))+'</pre>',
        '<p>같은 설치 launch <code>b7de3e12cca54b43b78308d73f6e3d28</code>, SIM operation <code>'+esc(operation['operation_id'])+'</code>. 원 물리 실패의19분할 중 해당 SHA를 검증한 시간/기하 재검사는 새 정책 통과 범위만 확인합니다. 원 실패 결과를 고치거나 실물 회전 성공으로 바꾸지 않습니다.</p>',
        '<h2>실제 설치 SIM 화면·조작</h2><p>저장된 원 SIM 장면 재열기→현재 Isaac 표시→SIM 명시 선택/Connect/Prepare→정책350ms DOM 확인→수동68.466초 hold/네방향/해제→오른쪽90° COMPLETED→왼쪽 채팅 단일360°+142점 LiDAR COMPLETED→Stop/OFF/Disconnect→실제 로그 재조회 FINALIZED1284이벤트→UI Exit. 실물 항목은 모두 DISCONNECTED/operation null. 전체 fresh 생성·복원/일반 native 인수와 구분합니다.</p>',
        '<img src="ui-02/02-full-turn-result.png" alt="실제 설치된 SIM 한 바퀴 완료 화면">',
        '<p><a href="ui-02/session.json">원 UI 단계·실행 ID</a> · <a href="ui-02/operation-ui-response.json">실제 UI GET 원문(다운로드 성공 아님)</a> · <a href="frozen/receipt.json">원 Kit/엔진/작업 로그 SHA</a> · <a href="ui-02/download-diagnostics.json">다운로드 취소 진단</a></p>',
        '<h2>최종 보조검사</h2><table><tr><th>집합</th><th>판정</th><th>시간</th><th>실제 출력</th></tr>']
    parts += ['<tr><td>'+esc(c['name'])+'</td><td>'+esc(c['status'])+'</td><td>'+str(round(c['elapsed_s'],3))+'s</td><td><a href="'+c['name']+'.log">로그</a></td></tr>' for c in checks]
    parts += ['</table><p>단위/모델/로컬 파이프 시험은 실제 로봇 성적이나 실제 사용자 여정 수가 아닙니다.</p><h2>정확한 실패·미검증·잔여</h2><ul>']
    parts += ['<li>'+esc(v)+'</li>' for v in result['limitations']]
    parts += ['</ul><h2>정상 종료·비용</h2><pre>'+esc(json.dumps(cleanup,indent=2))+'</pre>',
        '<p>새LLM HTTP/USD0, 추가USD50 장부잔여46.8551834·기존USD20 별도불변. 새 공개/commit/push/삭제·의존성/OS/ROS 설치0. 원자료·dirty·프로젝트·실패 보존.</p><p><a href="result.json">전체 기계 판정/정책·SHA·잔여</a></p>']
    (OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),checks=[dict(name=c['name'],status=c['status']) for c in checks])))
    if any(c['status']!='PASS' for c in checks):raise SystemExit(1)


if __name__=='__main__':main()
