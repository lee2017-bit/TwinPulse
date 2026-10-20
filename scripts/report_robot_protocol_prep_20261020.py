# SPDX-License-Identifier: Apache-2.0
"""One local evidence report. Does not connect to an App, provider or robot."""
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-protocol-prep-20261020'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    value = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def link(path, label=None):
    return '<a href="' + escape(path, quote=True) + '">' + escape(label or path) + '</a>'


def table(head, rows):
    return '<table><tr>' + ''.join('<th>' + escape(v) + '</th>' for v in head) + '</tr>' + ''.join(
        '<tr>' + ''.join('<td>' + str(v) + '</td>' for v in row) + '</tr>' for row in rows) + '</table>'


if __name__ == '__main__':
    install = read(OUT / 'installation04.json')
    ui = read(OUT / 'actual-ui11/result.json')
    cold = read(OUT / 'actual-ui12/result.json')
    physical = read(OUT / 'actual-ui10/result.json')
    ack = read(OUT / 'ack-gate.json')
    if not (ui['status'].startswith('PASS') and cold['status'].startswith('PASS')
            and physical['status'].startswith('PASS') and ack['status'].startswith('PASS')):
        raise ValueError('Final scoped evidence is not PASS; do not publish a positive report')
    # Report prose is Korean; stored historical notes never become product UI.
    attempt_notes = {
        '01': '후보01. 62초·4방향·90도·360도를 실행했으나 Stop all 적용 증거/다운로드 미관측. 원본 FAIL 유지.',
        '02': '후보01 cold 반출 진단. 실제 다운로드 시작 뒤 canceled. 합격 아님.',
        '03': '최종04. 디스크 여유0/도구 세션 소실. 원기록 미완료, 정상 UI 종료 미증명.',
        '04': '최종04. Isaac 시작 전 비활성 저장 chat을 누른 시험기 오류. 독립 재시험.',
        '05': '최종04 cold 반출 한정 성공. Windows 저장 경로·전송 완료·원기록 동일 확인.',
        '06': '최종04 전체 여정은 Stop all 기록 대기 경쟁으로 FAIL. 뒤에 찾은 응답으로 원본을 고치지 않음.',
        '08': 'UI8단계 PASS였으나 엄격 gate가 Stop all 새 epoch 적용 증거 누락을 검출. 최종 합격으로 사용하지 않음.',
        '09': '08의 cold 반출/PC 준비 한정 성공. 08 전체 실패를 구제하지 않음.',
        '10': '접속 없이 원 실물 이력과 센서 원문 분할1개를 실제 UI로 반출. 원 bytes/SHA 일치.',
        '11': 'Stop all의 정확한 operation/connection/새 motion/applied epoch를 기다리게 수정하고 같은 최종04의 전체8단계를 독립 재시험.',
        '12': '11의 실제 다운로드 원본과 cold 재반출 비교. PC 준비/연결 진입 버튼 확인, 접속 없음.',
    }
    attempts, cleanups = [], []
    runtime = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime'
    for name, note in attempt_notes.items():
        folder = OUT / ('actual-ui' + name)
        result_path = folder / 'result.json'
        value = read(result_path) if result_path.exists() else {}
        session_path = folder / 'session.json'
        session = read(session_path) if session_path.exists() else {}
        identity = value.get('identity', session.get('identity', {}))
        launch = identity.get('engine', {}).get('launch_id')
        original_status = value.get('status', 'DIAGNOSTIC_NOT_FINALIZED')
        attempt = dict(run='actual-ui' + name, status=original_status, note=note,
                       identity=identity, operation_id=value.get('operation_id'),
                       began=session.get('began'), exit=value.get('exit'),
                       result_file=str(result_path.relative_to(OUT)) if result_path.exists() else None)
        if name == '08':
            attempt['derived_verdict'] = 'REJECTED_BY_EXACT_ACK_GATE'
        attempts.append(attempt)
        if launch:
            source = runtime / 'launches' / launch / 'cleanup-receipt.json'
            if source.exists():
                target = OUT / ('cleanup-launch-' + launch + '.json')
                if not target.exists():
                    shutil.copyfile(source, target)
                cleanups.append(dict(launch=launch, path=target.name, sha256=digest(target), receipt=read(target)))
    cleanup_names = ['cleanup-receipt.json', 'cleanup-layout-receipt.json', 'cleanup-unused-timing-receipt.json']
    cleanup = [dict(path=name, value=read(OUT / name)) for name in cleanup_names]
    recovered = sum(r['value']['free_after'] - r['value']['free_before'] for r in cleanup)
    final_state = read(OUT / 'final-state.json')
    not_run = [
        '실제 Pi ARM64/ROS 출력 노드 전체 빌드·배포·설정 readback. 로봇 OFF이므로 첫 명시 Prepare의 무구동 단계에서 확인해야 함.',
        '새 연결에서 최초 시간 자동계측, 실제 센서 부하/저장/배터리·제동·연속 주행·실제 가구 목적지/세계 정합.',
        '일반 모드 전체/native Windows 입력·Explorer 더블클릭·OS 붙여넣기·다른 PC/DPI. root Start-Test를 실행 도구로 호출한 같은 설치 BrowserWindow 시험임.',
        '이번 최종본의 새 사진/텍스트 생성, 목적지 bed/chair 도착·전체 F01~F12/9-role 재인수. 기존 저장 scene을 사용했고 전체 제품 완료로 승격하지 않음.',
        '새 외부 LLM 호출·Git commit/push·GitHub/Release/공개 영상 게시.',
    ]
    tests = [
        ('PC 세션/installer/fleet/목적지/시간 통합', '81 tests OK, 1 skip', 'integration07.log', '현재 PC 변경 포함. skip은 Windows symlink 생성 권한.'),
        ('로봇 Python 보조', '183 tests OK', 'robot-all02.log', '이후 PC-side pause 보완 전 기록. 로봇 쪽 source는 그 뒤 불변.'),
        ('C++17 guard ASan/UBSan', '1320 checks PASS', 'cpp-sanitized.log', '기존 WSL GCC11.4, fake 출력만. ROS 통합/ARM64/기기 시험 아님.'),
        ('target 빌드 orchestration', '2 tests OK', 'guard-build-tests02.log', '고정 build runner fixture. 실제 ROS 컴파일 PASS 아님.'),
        ('UI 보조', '234 tests/4 files + 93 tests/2 files', 'ui-download02.log', '일부 중복이므로 고유 합계나 실제 사용자 여정 수로 합산하지 않음.'),
        ('실제 원문 재생', '6081 frames; 202 strict incomplete; 2259 unknown bytes', 'original-native-replay.json', '원시각/최신 위험 veto 유지. 과거 실패 PASS로 변경하지 않음.'),
        ('원 실물19분할 SHA 재검증', 'PASS_ORIGINAL_BYTES_UNCHANGED', 'original19-recheck.json', '재계산만. 앱 등록값/추천값 자동 변경0, 실물 새 계측 아님.'),
        ('정확 Stop ACK gate', ack['status'], 'ack-gate.json', '개별5개+Stop all2대의 원응답/새 적용 epoch. 누락/오염4개 음성시험 모두 거절.'),
    ]
    artifacts = []
    folders = [OUT] + [OUT / ('actual-ui' + n) for n in attempt_notes]
    for folder in folders:
        for file in sorted(folder.glob('*')):
            if file.is_file() and file.suffix in {'.json', '.log', '.mp4', '.png'} and file.name not in {'result.json', 'report-qa.png'}:
                artifacts.append(dict(path=file.relative_to(OUT).as_posix(), bytes=file.stat().st_size, sha256=digest(file)))
        if folder != OUT and (folder / 'result.json').exists():
            file = folder / 'result.json'
            artifacts.append(dict(path=file.relative_to(OUT).as_posix(), bytes=file.stat().st_size, sha256=digest(file)))
        for file in sorted((folder / 'downloads').glob('*')):
            if file.is_file():
                artifacts.append(dict(path=file.relative_to(OUT).as_posix(), bytes=file.stat().st_size, sha256=digest(file)))
    aggregate = dict(schema='robot-protocol-preparation-report-1.0', at=datetime.now(timezone.utc).isoformat(),
        status='PASS_SCOPED_SOFTWARE_PREPARATION_NOT_FULL_PRODUCT_OR_HARDWARE_ACCEPTANCE',
        installation=install, attempts=attempts, final_sim=ui, final_cold=cold, physical_history=physical,
        ack_gate=ack, cleanup=cleanup, recovered_free_bytes=recovered, launch_cleanup=cleanups,
        final_state=final_state, supplementary=tests, not_run=not_run, artifacts=artifacts,
        provider_http=0, provider_usd=0, last_recorded_additional50_remaining_usd='46.8551834',
        budget_note='마지막 장부 기준. 새 공급자 청구 조회/과거 USD20 합산 또는 새 예산 승인 아님.',
        full_product_readiness='NOT_QUALIFIED_NO_CURRENT_FULL_9_ROLE_GATE')
    (OUT / 'result.json').write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding='utf-8')
    html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse · 로봇 프로토콜 준비 검증</title><style>body{font:16px/1.65 system-ui;max-width:1160px;margin:32px auto;padding:0 22px;color:#173240;background:#f4f7f9}section{background:white;border:1px solid #d8e2e6;border-radius:12px;padding:23px;margin:22px 0}h1{line-height:1.25}img,video{width:100%;height:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px;border-bottom:1px solid #dae4e8;text-align:left;vertical-align:top;overflow-wrap:anywhere}code{overflow-wrap:anywhere}a{color:#087768}.notice{border-left:5px solid #bb7c1d;padding:12px;background:#fff4de}</style><h1>로봇 제어·실물 시험 준비 수정</h1>'''
    html += '<p>2026-10-20 · 한국어 보고 / 제품 UI 영어 · ' + escape(aggregate['status']) + '</p>'
    html += '<p class="notice">PC/SIM 경로와 저장 자료 반출은 확인했습니다. 실제 Pi/ROS 전체 빌드·센서·제동·주행은 로봇 OFF로 미실행입니다. 전체 제품·실물 성공 보장이 아니며, 첫 실물 Prepare는 이동 전에 새 출력 노드 빌드/적용값 확인부터 수행합니다.</p>'
    html += '<section><h2>1. 반영한 수정</h2><ul><li>로봇 nonce를 한 번만 사용하고 수동 갱신은 새 창을 기다립니다. 원 입력 만료시각/세대/연결/Stop epoch를 유지하며 만료·Stop·재연결 뒤 재생하지 않습니다. 보류/대체는 별도 원인 이벤트로 남기고 실행 ACK로 위장하지 않습니다.</li><li>느린 상태 갱신 전에 HTTP 입력의 연결·motion epoch를 고정합니다. 로봇 자동 pause가 활성 권한을 끊으면 PC에도 새 Stop fence를 만들고 이전 held 입력을 새 nonce에 재결속하지 않습니다.</li><li>새 시간 설정이 구 고정 binary로 실행되던 경로를 제거했습니다. 명시 Prepare가 shipped source SHA에 묶인 별도 C++/ROS 출력 노드를 빌드/검사하고 캐시·실행 SHA와 latched 설정 readback을 검증합니다. 실패하면 구 binary로 우회하지 않습니다. 실제 target 실행은 아직 미검증입니다.</li><li>영문 준비 단계는 기존 compact 행에 표시합니다. 파일 반출은 연결된 download anchor/Blob 수명을 보존합니다. 입력350ms·odom300ms, 최초 이후 명시 Recalculate/Apply recommended 계약과 기존 Stop/기하/속도 보호는 유지합니다.</li></ul><p>최종 설치 <code>' + install['verification']['build_id'] + '</code><br>source <code>' + install['verification']['source_manifest_sha256'] + '</code><br>1668 files verified · 변경 없는 desktop73파일만 검증된 hardlink 재사용. 데이터 epoch1, 기존 사용자 자료 유지.</p></section>'
    html += '<section><h2>2. 최종 실제 설치 SIM 여정</h2><p>root Start-TwinPulse-Test.cmd를 실행 도구로 호출 → 같은 설치 Electron BrowserWindow의 실제 클릭/입력. 별도 Chrome·제품 변경 API 직접 호출·고정 응답·state 주입·request routing 없음. 원 저장 데모 scene 재열기이며 새 생성이 아닙니다.</p>'
    html += table(['실제 단계', '판정'], [(escape(s['name']), escape(s['status'])) for s in ui['steps']])
    hold = ui['steps'][2]['evidence']
    html += '<p>단일62초 hold의 ' + str(hold['samples']) + '개 연속 화면 표본, 최대 frame age ' + str(round(hold['frame_age_max'], 2)) + 'ms. 모델/이름/Stop/pad/current image를 함께 관찰. 90도와 한 번의360도는 실제 명령 완료로 확인했습니다. 물리 센서/제동 증거가 아닙니다.</p><p>SIM op <code>' + escape(ui['operation_id']) + '</code>; launch <code>' + escape(ui['identity']['engine']['launch_id']) + '</code>.</p><img src="actual-ui11/hold-release.png" alt="최종 실제 설치 앱, 드러난 로봇과 하단 compact 조종기"><p>' + link('actual-ui11/result.json', '전체 원결과') + ' · ' + link('ack-gate.json', '정확한 Stop ACK/적용 epoch와 음성시험') + '</p><video controls preload="none" src="actual-ui11/app-screen.mp4"></video><p>원 renderer 녹화, 무편집. fresh 생성 데모·native 시작 화면·실물 영상이 아닙니다.</p></section>'
    html += '<section><h2>3. 재시작·PC 연결 준비·실물 원문 보존</h2><p>최종 SIM 반출본을 불변 원본으로 삼아 cold 재다운로드의 canonical events/동일 Twin 출처를 대조했습니다. Robots → Check PC preparation → PC prerequisites found / robot connection not checked와 명시 Check connection 버튼을 확인했지만 누르지 않았습니다.</p><img src="actual-ui12/pc-preparation.png" alt="실제 PC 준비 확인과 명시 연결 버튼"><p>원 실물 op <code>39557dac1c1f44d3aebc01615d2df74b</code>의114 events와 원stream/source가 동일합니다. 첫 raw 분할은4,193,980B / SHA <code>1d301cefc56b08058aebebbe84ccaa97eeeb0740258820ee3dec35f3171c22ee</code>로 실제 다운로드와 일치했습니다. 과거 실패는 그대로 실패이며 현재 실물 연결 성공으로 세지 않습니다.</p><img src="actual-ui10/physical-history-raw.png" alt="원 실물 실패 이력과 원문 반출"><p>' + link('actual-ui12/result.json', '최종 cold/PC 결과') + ' · ' + link('actual-ui10/result.json', '실물 이력·원문 SHA 결과') + '</p></section>'
    html += '<section><h2>4. 모든 실제 시도와 원 실패</h2>' + table(['시도', '원 결과 / 파생 판정', '구분'], [(link(a['run'] + '/', a['run']), escape(a['status'] + (' → ' + a['derived_verdict'] if a.get('derived_verdict') else '')), escape(a['note'])) for a in attempts])
    html += '<p>08의 UI PASS를 그대로 믿지 않고 exact Stop all gate가 거절했습니다. 원 응답을 후대 telemetry로 채우지 않았고, 시험기의 새 epoch 대기를 고친 뒤11 전체를 독립 실행했습니다. 08 원본과 거절 gate를 모두 보존했습니다.</p><p>초기 반출 취소에는 C:0B 압박과 CDP 저장 경로/이벤트 차이가 얽혔습니다. 즉시 Blob revoke 수정은 타당하지만 과거 취소의 단독 원인으로 입증하지 않았습니다. UI01의 해제 뒤 drive409는 정확한 앞선 Stop fence에 의해 거절된 것으로, 정상 명령 성공/재시도로 위장하지 않습니다. native 캡처 timeout·도구변수 소실·보조시험 import/fixture 오류도 원본 log에 유지합니다. integration04/05 log에는 거대한 source bundle dump가 있어 요약 없이 전문 출력하지 않습니다.</p></section>'
    html += '<section><h2>5. 보조 검증 — 실제 사용자·실물 시험과 분리</h2>' + table(['범위', '결과', '증거/한계'], [(escape(a), escape(b), link(c) + '<br>' + escape(d)) for a,b,c,d in tests]) + '</section>'
    html += '<section><h2>6. 용량·정리·최종 종료</h2><p>별도 설치 ZIP이 필요 없는 package-only build를 추가했습니다. 현재04/직전 실제 UI 정상본v561/필요 재현본01 및 원사진·프로젝트·장부·원문·실패영상을 보호하고, 정확한 검토 경로의 중간 generated EXE만 제거했습니다. 3회 실제 free-space 차이 합계 <b>' + str(recovered) + 'B</b> (약2.35GiB)를 회수했습니다. 동일 immutable desktop만 hardlink하며 사용자 자료는 공유하지 않습니다.</p><p>삭제된 중간 EXE의 정확한 binary bytes 복원을 보장하지 않습니다. source/resources/manifest는 보존했습니다. 두 layout 중간본은 과거 실제 FAIL 시험본이었고, 원 실패 자료는 삭제하지 않았습니다. 이 정리 script는 날짜별 검토 작업이며 앱 자동 GC 완성 주장이 아닙니다.</p><p>' + ' · '.join(link(name) for name in cleanup_names) + '</p><p>기존 WSL GCC로 pure C++ 검증, 기존 Docker에 ROS image가 있는지 확인했으나 없었습니다. 새 설치/pull은 없고 이번에 시작한 runtime만 종료했습니다. RAM/pagefile 압박 시 디스크0이 관측되었으며 OS pagefile·Docker volume·WSL/Isaac 설치를 삭제/변경하지 않았습니다.</p><p>' + link('final-state.json', '최종 포인터·포트·lock·디스크 검사') + ' · ' + link('result.json', '실행별 cleanup와 전체 artifact SHA') + '</p></section>'
    html += '<section><h2>7. 정확히 남은 범위와 다음 실물 순서</h2><ul>' + ''.join('<li>' + escape(v) + '</li>' for v in not_run) + '</ul><p>다음 실물 세션은 원 거실 프로젝트 → 명시 Check connection → Prepare의 새 source 빌드/검사/적용 readback(무구동) → 정지 센서/원문 수집 → 기존 짧은 정지시험 → 수동/채팅90도·한 번의360도 → Stop/OFF/반출 순서입니다. 새 준비 기능을 만들기 위해 먼저 이동할 필요는 없습니다. 현재 target build 실패가 확인된 것은 아니지만 실제 컴파일 성공도 아직 주장하지 않습니다.</p><p>전체 제품9-role gate는 이번 범위로 충족하지 않았으므로 전체 READY/모든 기능 완료로 기록하지 않습니다. 감독하 첫 무구동 검증과 이후 live guard를 통과한 시험을 구분합니다.</p></section>'
    html += '<section><h2>8. 시간·비용·승인 경계</h2><p>각 session.json의 UTC 시작시각과 단계 elapsed_ms/녹화 packet time을 보존했습니다. 2026-10-20 KST 작업이며 시도·재빌드·실패를 제외한 단축 성공시간으로 제시하지 않습니다.</p><p>새 LLM HTTP0 / USD0. 추가USD50의 마지막 장부 잔여 <b>46.8551834</b>, 이전USD20 별도·불변. 공급자 최신 청구 재조회나 추가 예산이 아닙니다. 새 의존성/ROS/드라이버/유료Cloud 설치, 실물 SSH·센서·모터, commit/push·게시 없음. 이번 모델명/추론설정은 도구로 조회하지 못했고 새 보조 에이전트는 생성하지 않았습니다.</p><p>' + link('result.json', '모든 시도·launch/operation·SHA·미검증·cleanup·비용 원장 기준') + '</p></section></html>'
    (OUT / 'report.html').write_text(html, encoding='utf-8')
    print(json.dumps(dict(report=str(OUT / 'report.html'), status=aggregate['status'], recovered_free_bytes=recovered), ensure_ascii=False))
