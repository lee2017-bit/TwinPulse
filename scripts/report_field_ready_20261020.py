# SPDX-License-Identifier: Apache-2.0
"""Hash-bound field-test-entry evidence/report; never contacts a device/provider."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-field-ready-20261020'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    value = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    attempt = sys.argv[1] if len(sys.argv) == 2 else '08'
    if attempt not in {'06', '07', '08', '09'}:
        raise ValueError('Explicit original whole-journey attempt required')
    normal_path=f'normal{attempt}-restart'
    restart_path=f'normal{attempt}-final-restart'
    supplementary_path='supplementary09' if attempt=='08' else f'supplementary{attempt}'
    normal = read(OUT / normal_path / 'result.json')
    restart = read(OUT / restart_path / 'result.json')
    shutdown = read(OUT / normal_path / 'shutdown.json')
    restart_shutdown = read(OUT / restart_path / 'shutdown.json')
    native = read(OUT / f'native-input{attempt}.json')
    lifecycle = dict(status='PASS' if shutdown['status'] == restart_shutdown['status'] == 'PASS' else 'FAIL',
        release_id=normal['release_id'], source_sha256=normal['source_sha256'],
        normal_start_launch_id=normal['launch_id'], shutdown_clean=shutdown['shutdown_clean'],
        restart_ready=restart['status'] == 'PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_launch_id=restart['launch_id'], restart_debug_listener_count=restart['debug_listener_count'],
        restart_app_listener_count=restart['app_listener_count'], restart_authenticated_ready=native['restart_authenticated_home_verified'],
        restart_ready_wait_ms=restart['ready_wait_ms'], restart_shutdown_clean=restart_shutdown['shutdown_clean'],
        shutdown_input='Computer Use @oai/sky actual selected normal Electron window Alt_L+F4; no terminal/UIA substitute',
        first_window_id=native['normal_window_id'], restart_window_id=native['restart_window_id'],
        native_full_interaction='NOT_RUN: graphics capture timed out; authenticated Home confirmed by actual AX, full interaction used the same Test BrowserWindow',
        explorer_double_click='NOT_RUN: identical Start file invoked by execution tool',
        references={str(p.relative_to(OUT)): digest(p) for p in (OUT/normal_path/'result.json', OUT/normal_path/'shutdown.json',
                      OUT/restart_path/'result.json', OUT/restart_path/'shutdown.json', OUT/f'native-input{attempt}.json')})
    write(OUT / 'normal-lifecycle.json', lifecycle)
    roles = dict(fresh=f'ui-{attempt}/result.json', cold=f'ui-cold-{attempt}/result.json', lineage=f'lineage-{attempt}/result.json',
                 lineage_cold=f'lineage-cold-{attempt}/result.json', normal=normal_path+'/result.json', lifecycle='normal-lifecycle.json',
                 installation=f'installation-final{attempt}.json', supplementary=supplementary_path+'/result.json', budget='budget-final.json')
    review = dict(schema='physical-readiness-review-1.1', status='SOFTWARE_NO_KNOWN_BLOCKER', unresolved=[],
        scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
        observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
        not_run=['PI_LOAD_AND_STORAGE', 'PHYSICAL_STOPPING_AND_DRIVING', 'WORLD_ALIGNMENT'],
        protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',
        replay=dict(path='observation-replay-final.json', sha256=digest(OUT/'observation-replay-final.json')),
        evidence=[dict(path=name, sha256=digest(OUT/name)) for name in
                  ('transport-before-after-final.json', 'transport-final.log', supplementary_path+'/result.json', 'observation-replay-final.json')],
        target_guard_ROS_ARM64='NOT_RUN_OFF: first explicit App Prepare builds/tests before the device lease, then verifies applied settings; no old-binary fallback',
        SDK_installation='NONE: PC SDK absent is not evidence that the existing Pi ROS installation was deleted. No new ROS installation authorized or performed.',
        historical_open_risks=['Original engine/render and 847ms GET latency sole causes remain UNKNOWN; current original full conditions passed, not proof of a historical root fix or no recurrence.',
                               'New ARM64/ROS target node compilation and actual applied readback are NOT_RUN_ROBOT_OFF; first explicit Prepare must verify before device lease.'],
        limitation='Permission to begin supervised no-motion Prepare and subsequent live trials, not proof that target compilation or driving will succeed.')
    manifest = dict(release_id=normal['release_id'], source_sha256=normal['source_sha256'], physical_readiness_review=review,
        evidence=[dict(role=role, path=name, sha256=digest(OUT/name)) for role, name in roles.items()])
    write(OUT/'evidence-manifest.json', manifest)
    gate = subprocess.run([sys.executable, str(ROOT/'scripts/verify_robot_focus_gate.py'), '--manifest', str(OUT/'evidence-manifest.json'),
                           '--output', str(OUT/'gate-result.json')], cwd=ROOT, capture_output=True, text=True)
    write(OUT/'gate-tool-receipt.json', dict(exit_code=gate.returncode, stdout=gate.stdout, stderr=gate.stderr))
    # Evidence-only negatives; never edit an original App result or inject App state.
    negative_manifest = deepcopy(manifest)
    fresh = read(OUT/roles['fresh']); fresh['steps'] = fresh['steps'][1:]
    write(OUT/'negative-missing-start-step.json', fresh)
    reference = next(row for row in negative_manifest['evidence'] if row['role'] == 'fresh')
    reference.update(path='negative-missing-start-step.json', sha256=digest(OUT/'negative-missing-start-step.json'))
    negative_manifest['classification'] = 'EVIDENCE_ONLY_NEGATIVE_NOT_APP_ACCEPTANCE'
    write(OUT/'negative-manifest.json', negative_manifest)
    negative = subprocess.run([sys.executable, str(ROOT/'scripts/verify_robot_focus_gate.py'), '--manifest', str(OUT/'negative-manifest.json'),
                               '--output', str(OUT/'negative-gate-result.json')], cwd=ROOT, capture_output=True, text=True)
    verdict = read(OUT/'gate-result.json'); rejected = read(OUT/'negative-gate-result.json')
    attempts = []
    for folder in sorted(OUT.iterdir()):
        if not folder.is_dir() or not (folder/'result.json').exists():
            continue
        value = read(folder/'result.json')
        engine=value.get('desktop',{}).get('engine',{})
        operation_ids={value['operation_id']} if value.get('operation_id') else set()
        operation_ids.update(r['operation_id'] for s in value.get('samples',[]) if isinstance(s,dict)
            for r in s.get('robots',[]) if isinstance(r,dict) and r.get('operation_id'))
        attempts.append(dict(path=str((folder/'result.json').relative_to(OUT)), status=value.get('status'),
                             project=value.get('project'), operation_id=value.get('operation_id'), error=value.get('error'),
                             operation_ids=sorted(operation_ids),launch_id=engine.get('launch_id') or value.get('launch_id'),
                             release_id=engine.get('release_id') or value.get('release_id'),input_sha256=value.get('input_sha256'),
                             sha256=digest(folder/'result.json'),
                             classification=value.get('classification'), steps=len(value.get('steps', []))))
    budget = {k: v for k, v in read(OUT/'budget-final.json').items() if k not in {'requests','new_requests','files'}}
    budget['exact_remaining_usd'] = str(Decimal(budget['limit_usd']) - Decimal(budget['protected_additional_50_total']))
    result = dict(at=datetime.now(timezone.utc).isoformat(), status=verdict['status'],
                  release_id=normal['release_id'], source_sha256=normal['source_sha256'], gate=verdict,
                  negative_missing_required_step_rejected=negative.returncode == 1 and rejected['status'] == 'NOT_READY',
                  attempts=attempts, budget=budget,
                  original_input_sha256=read(OUT/roles['fresh'])['input_sha256'],
                  actual_video_qa=read(OUT/'recording-final-qa.json'),
                  disk_free_bytes=shutil.disk_usage('C:\\').free,
                  physical='NOT_RUN_OFF_NO_SSH_OR_SENSOR_OR_MOTOR', new_dependency_installations=0,
                  target_build='NOT_RUN_ROBOT_OFF: PC SDK is not a required App dependency', full_product='NOT_QUALIFIED: focused robot-entry scope, not CAD/photo/industrial acceptance')
    write(OUT/'result.json', result)
    index_paths=set(OUT.glob('*.json'))|set(OUT.glob('*.log'))|{OUT/a['path'] for a in attempts}
    index=[dict(path=str(p.relative_to(OUT)),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(index_paths)]
    write(OUT/'evidence-index.json',index)
    rows = ''.join('<tr><td><a href="'+escape(a['path'])+'">'+escape(a['path'])+'</a></td><td>'+escape(str(a['status']))+
                   '</td><td>'+escape(str(a['error'] or ''))+'</td></tr>' for a in attempts)
    pictures = [p for p in (OUT/f'ui-{attempt}').glob('*.png') if any(token in p.name for token in ('power-on', 'destination-chair', 'lidar-sparse', 'robot-pc'))]
    pictures.extend(OUT/f'ui-{attempt}/recording'/name for name in ('frames/000000.jpg','frames/000571.jpg'))
    media = ''.join('<figure><img src="'+escape(p.relative_to(OUT).as_posix())+'"><figcaption>'+escape(p.name)+'</figcaption></figure>' for p in pictures)
    videos = ''.join('<p><a href="'+p.relative_to(OUT).as_posix()+'">'+escape(p.relative_to(OUT).as_posix())+' 실제 시험 영상</a></p>'
                     for p in sorted([*OUT.glob('recording-*/app-screen.mp4'), *OUT.glob('ui-*/recording/app-screen.mp4')]))
    report = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse 현장시험 진입 준비</title><style>body{font:16px/1.6 system-ui;max-width:1150px;margin:32px auto;padding:20px;background:#f6f8fa;color:#142634}section{background:white;border:1px solid #d2dce3;border-radius:12px;padding:20px;margin:20px 0}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd6df;padding:8px;text-align:left;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}img{max-width:100%}figure{margin:20px 0}a{color:#006b80}</style>'
    report += '<h1>TwinPulse 현장시험 진입 준비</h1><p>'+escape(verdict['status'])+' · 실물 시험 성공이나 전체 제품 완료가 아닙니다.</p>'
    report += '<section><h2>수정 원인</h2><p>송신 묶음의 guard_base 하위 경로를 수신 BOOTSTRAP 정규식이 거절했습니다. 원 설치 코드로 실제 수신 subprocess를 재현하면 BOOTSTRAP_PATH, 수정 후84파일 해시 일치·워커의 무구동 START_SHAPE 거절까지 도달했습니다. 별도 prepare archive의 고정 core 목록은 robot_timing_profile을 누락했습니다. 실제 robot 소스의 절대 import 의존성을 추적하고 독립 import 회귀를 추가했습니다. 예전 파일을 지워 발생한 SDK 오류가 아니라 코드/검증 경계 결함입니다.</p><p>축약 UI와 옛 시험 선택자 불일치, 대기중 엔진 fixture, 만료 bitmap과 다음 정상 bitmap의 close 호출을 혼합한 시험 경쟁을 각각 원 실패로 보존했습니다. 실제 제어 제한을 완화해 통과시키지 않았습니다.</p></section>'
    report += '<section><h2>렌더 정체 원 실패는 보존</h2><p>최종본03의 침대 목적지 이동에서 frame 나이1037.264ms와 ISAAC_UPDATE_STALLED가 발생했습니다. op144055bcd5e34c209371d7c4412d70f9의 원 실행/Kit8파일을 SHA 고정했습니다. 같은 시간 HTTP는 약 수ms였고, 엔진 first-fault는 previous_viewport_s0.796 / app_update_s0.094 / 전체 gap0.906초를 기록했습니다. viewport update 하위 단계 중 어느 호출이 지연했는지는 미확정이며 새 통과가 그 근본원인을 고쳤다는 뜻은 아닙니다. <a href="failed03-original-logs/receipt.json">원문 보존 목록</a>. 이후 같은 동결본의 독립 전체 실행을 별도로 판정하며1초 frame/500ms engine 기준을 늘리지 않았습니다.</p></section>'
    report += '<section><h2>새 실패06과 지연 계측</h2><p>05는60초 회전 중,06은60초 통과 뒤90도 명령 중 원시각1초 초과로 실패했습니다.06은同 op26eba88be38f45aa9642852a6fb0aa70에서 task COMPLETED·engine runtime_fault null인데 작은725B viewport GET이842.266ms(sendEnd→headersStart) 지연됐습니다. DNS0.094ms/연결1.734ms로 TCP연결 지연만으로 설명되지 않습니다. 직전 전체 로그 요약 저장 CPU 부하를 Astra xhigh가 독립 검토했으나 원record 단독 재생은~0.31–0.35초 CPU/heartbeat 최대32–38ms로847ms 정지를 재현하지 못했습니다. GC·특정 잠금을 단일 원인으로 확정하지 않습니다.</p><p>현재 추가한 Server-Timing·최초 TCP수락/HTTP스레드·broker/viewport 대기·캡처 예약/콜백/JPEG/POST·요약 저장/GC와 bounded no-locals stack은 진단입니다.0.15/0.2초는 기록 기준일 뿐 주행 거절/권한 조건이 아니며 제어 한도를 바꾸지 않습니다. 새 PASS는 이전 UNKNOWN 원인을 소급 해결한 증거가 아닙니다. <a href="failed06-original-logs/receipt.json">실패 시 원문</a>·<a href="failed06-after-exit/receipt.json">정상 종료 후 원문</a>·<a href="ros-build-scope.json">ROS/삭제/준비 범위</a>.</p></section>'
    report += '<section><h2>ROS와 삭제에 대한 구분</h2><p>이전 전체 ARM64/ROS 빌드는 Pi의 기존 Humble에서 실행했습니다. PC의1320검사는 ROS 없는 순수 C++ 보호 로직이었습니다. 정리339개는 지정 TwinPulse outputs/artifacts/installed releases 내부에만 있으며 ROS 설치 경로 삭제는 없습니다. 현재 PC의 ROS SDK 부재를 Pi SDK 삭제로 해석하지 않습니다.</p><p>ROS 빌드는 별도 사용자용 앱이 아니라 컴파일 도구 과정입니다. 현재 TwinPulse Prepare가 고정 source-SHA 빌드→검사→적용값 확인을 관리합니다. PC에 ROS를 새로 설치할 필요는 없으며, 첫 실제 Pi 빌드/readback은 전원 후 확인할 결과로 남습니다. 이번에 새 ROS 환경을 설치하거나 이 미검증 항목을 PASS로 바꾸지 않았습니다.</p></section>'
    report += '<section><h2>설치 앱 전용 프로필 오류와 진단 격리</h2><p>07은 생성·조종·목적지·센서·PC 준비 등32단계를 통과한 뒤 잘못된 measured profile 저장에서 ERR_EMPTY_RESPONSE로 실패했습니다. PC가 physical_profile을 직접 로드할 때 로봇 peer control_timing을 찾지 못한 실제 ModuleNotFoundError였습니다. pure-core import로 고쳤고 App/Core/Provider만 허용한 새 -I subprocess의 App save entry에서 원 FAIL과 수정 후400 PROFILE_SHAPE를 검증했습니다. 기존 시험 전역 search path가 설치 경계 결함을 가렸으므로 AGENTS에 독립 로더 회귀를 추가했습니다.</p><p>예상 밖 backend 예외는 이제 재시도 없이 unknown 결과와 조회용 execution ID를 반환합니다. request/operation UUID만 결속하고 예외 prose·소스 줄·locals는 출력하지 않습니다. Astra가 발견한 traceback 소스 literal 노출의 원 실패와 수정 후 회귀를 보존했습니다. 또 진단 print/flush가 느리면 다음 keep-alive 요청·viewport 전송까지 막을 수 있어 bounded queue와 별도 writer로 분리했습니다. 실제 blocked sink에서 요청 종료/화면 sender가 완료하는 보조 시험을 추가했으며 이는 실물 성공을 뜻하지 않습니다.</p><p><a href="failed07-original-logs/receipt.json">07 원로그/SHA</a> · <a href="profile-isolated-before.log">격리 원 실패</a> · <a href="profile-isolated-after.log">격리 수정 후</a> · <a href="redacted-stack-before.log">원 redaction 실패</a> · <a href="redacted-stack-after.log">수정 후</a> · <a href="async-isolation08.log">느린 로그 출력 격리</a>. build07은 변경 도중 만들어진 중간본으로 설치하지 않았고 최종 frozen package와 구분합니다.</p></section>'
    report += '<section><h2>동결본·게이트·한계</h2><pre>'+escape(json.dumps(verdict, ensure_ascii=False, indent=2))+'</pre></section>'
    report += '<section><h2>일반 Start·종료 관찰의 원 실패</h2><p>normal08은 실제 창 닫기 뒤 확인기가5일 전부터 열려 있던 notepad.exe를 현재 Electron의 자식으로 잘못 포함했습니다. Windows 부모 PID는 재사용될 수 있으며 프로세스 생성 시각이 부모보다 이른 것은 현재 소유가 아닙니다. 원 before-shutdown/shutdown FAIL은 보존했고 무관한 앱은 종료하지 않았습니다. 또한 그 관찰이 끝나기 전 재시작해 전역 lock/port 표본을 혼합한 시험 순서 오류도 남겼습니다.</p><p>생성 시각을 비교하는 읽기전용 확인기와 PID 재사용 음성 회귀를 추가한 뒤, normal08-restart와 normal08-final-restart 두 독립 전체 시작/닫기 여정에서 실제 Home·인증 Isaac 상태를 AX로 확인하고 Computer Use AltF4→현재 소유 PID/lock/port0을 각각 확인한 후 다음 Start를 실행했습니다. 원 FAIL을 수정하거나 옛 창147394032를 최종 근거로 재사용하지 않았습니다. graphics capture 두 번의 도구 시간 초과·native 전체/Explorer/OSpaste/DPI NOT_RUN은 별도로 유지합니다. <a href="observer-pid-reuse08.log">순수 확인기 회귀</a> · <a href="native-input08.json">실제 창/입력 영수증</a>.</p></section>'
    report += '<section><h2>모든 시도</h2><table><tr><th>원 기록</th><th>판정</th><th>실패</th></tr>'+rows+'</table></section>'
    report += '<section><h2>실행 ID·입력 SHA·원자료 인덱스</h2><p><a href="evidence-index.json">모든 최상위 로그/JSON·원 시도 결과의 bytes/SHA 인덱스</a>. 입력 SHA는 원 요청 bytes 기준이며 서로 다른 사진의 성적을 합치지 않습니다. 이번 새 생성은 텍스트이고 새 개인사진을 전송하지 않았습니다. <a href="accepted08-original-logs/receipt.json">최종 fresh 실행의 원8로그/Kit/SHA</a>.</p><pre>'+escape(json.dumps(attempts,ensure_ascii=False,indent=2))+'</pre></section>'
    report += '<section><h2>보조 시험의 실패도 분리</h2><p>supplementary08의 HTTP lifecycle 여섯 실패/오류는 같은 세 테스트가 다른 모듈에서도 수집된 중복입니다. 새 request 진단이 immutable api.broker.project_id를 읽는데, 과거 SimpleNamespace fixture 세 곳에 broker가 없어 business callback 전에 AttributeError가 났습니다. 실제 설치 서비스의 broker 계약은 그대로이며 실제 앱 전체39/14/8/4는 별도 통과했습니다. 단위 fixture에 원 계약의 project_id를 추가했으며 제품 소스·기한은 바꾸지 않았습니다. 원08 FAIL은 보존하고 같은 설치/source SHA에서 새09의5집합 전체를 독립 재실행했습니다. 단위 수를 사용자 여정 수나 실물 성적으로 합산하지 않습니다.</p></section>'
    report += '<section><h2>실제 화면과 녹화</h2><p>동일 설치 Electron Test BrowserWindow의 클릭·입력입니다. 일반 Start 파일은 실행 도구 호출이며 Explorer 더블클릭은 아닙니다. 일반 종료 두 번만 Computer Use Alt+F4로 검증했으며 native 전체 조작/OS 붙여넣기/DPI는 NOT_RUN입니다. 별도 Chrome·직접 제품 변경 API·고정 모델 성공 응답은 사용하지 않았습니다. 최종 영상은 Home부터 시작한 실제 전체 회귀시험이며 deliberate fault와 local 설정도 들어 있어 일반 공개용 데모로 게시하지 않았습니다.</p><pre>'+escape(json.dumps(result['actual_video_qa'],ensure_ascii=False,indent=2))+'</pre>'+videos+media+'</section>'
    report += '<section><h2>전원 후 실행</h2><p>같은 LAN·충전선 분리·현장 감독 → 원 거실 프로젝트 선택 → Check connection → Prepare(무구동 빌드·검사·적용 확인) → 정지 센서 수집 → Bootstrap stop → 수동·채팅90°·한 바퀴 스캔 → Stop/OFF → 원문 반출·Disconnect. 성공을 보장하거나 실제 차체/세계 정합 완료로 표시하지 않습니다. 실패하면 원 operation ID로 로그를 보존하고 추가 이동을 중단합니다.</p></section>'
    report += '<section><h2>비용·정확한 잔여</h2><pre>'+escape(json.dumps(result['budget'], ensure_ascii=False, indent=2))+'</pre><p>추정 usage와 미확정 예약을 포함한 기존 추가50 장부 기준이며 공급자 청구서가 아닙니다. 이전20 캠페인은 별도입니다. 새 로봇 접속·새 설치·삭제·Git 게시0.</p></section></html>'
    (OUT/'report.html').write_text(report, encoding='utf-8')
    print(json.dumps(dict(status=verdict['status'], issues=verdict['issues'], report=str(OUT/'report.html'))))
    return 0 if gate.returncode == 0 and result['negative_missing_required_step_rejected'] else 1


def finalize_review():
    """Finalize the human-facing artifact; never rewrite gate or App receipts."""
    from html.parser import HTMLParser
    from urllib.parse import unquote
    target=OUT/'report.html'
    review=read(OUT/'independent-final-review.json')
    text=target.read_text(encoding='utf-8')
    if '최종 독립 검토와 기록 마감' in text:raise ValueError('Final review already recorded')
    text=text.replace('조회용 execution ID','진단 ID(기록 성공 시 앱에서 조회)')
    text=text.replace('최종본03의','후보03의').replace('06은同 op','06은 operation ')
    text=text.replace('새 로봇 접속·새 설치·삭제·Git 게시0.','새 로봇 접속·의존성/ROS 설치·삭제·Git 게시0. 로컬 App 후보08 설치는 수행했습니다.')
    section='<section><h2>최종 독립 검토와 기록 마감</h2><p>진단 저장 자체가 실패하면 fallback ID는 로그에만 남을 수 있습니다. 앱에서 반드시 조회된다고 보장하지 않습니다. Baseline/Memory v565를 함께 갱신했고 현재 로컬 후보는 GitHub에 게시하지 않았습니다.</p><pre>'+escape(json.dumps(review,ensure_ascii=False,indent=2))+'</pre></section>'
    text=text.replace('</html>',section+'</html>')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):
            self.links.extend(v for k,v in attrs if k in {'src','href'} and v)
    parser=Links();parser.feed(text)
    missing=[link for link in parser.links if not link.startswith(('http:','https:','#','data:'))
             and not (target.parent/unquote(link.split('#')[0]).replace('\\','/')).exists()]
    if missing:raise ValueError('Report has missing local targets: '+str(missing))
    target.write_text(text,encoding='utf-8')
    receipt=dict(status='PASS_LOCAL_ARTIFACT_LINKS_AND_REVIEW',local_links_checked=len(parser.links),missing=[],
        report_sha256=digest(target),review_sha256=digest(OUT/'independent-final-review.json'),
        source_sha256=read(OUT/'result.json')['source_sha256'],
        docs={name:digest(ROOT/name) for name in ('docs/planning/TWINPULSE_PROJECT_MEMORY.md','docs/planning/TWINPULSE_BASELINE.md','docs/progress.md','README.md','AGENTS.md')})
    write(OUT/'report-finalization.json',receipt)
    print(json.dumps(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(finalize_review() if sys.argv[1:]==['--finalize-review'] else main())
