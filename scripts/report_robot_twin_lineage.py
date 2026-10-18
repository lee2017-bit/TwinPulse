# SPDX-License-Identifier: Apache-2.0
"""Build a local evidence index; never opens an API or hardware connection."""
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-twin-lineage-20261018'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def safe(value):
    return escape(str(value))


def block(value):
    return '<pre>'+safe(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'


def main():
    sections=[]
    sections.append('''<h1>로봇 기록 ↔ 채팅 ↔ Twin 버전 연결</h1>
<p>2026-10-18 · 로컬 설치 검증. 이번 변경은 기록 추적성 범위다. TwinPulse 전체 제품·실물 주행·사진 품질 완료 보고가 아니다.</p>
<h2>바뀐 계약</h2><ul>
<li>같은 ID를 재사용하지 않는다. project/chat + conversation session → Twin revision/engine/stage → robot operation/robot/connection → request/command/trial/stream/frame와 원문 SHA로 연결한다.</li>
<li>실물 연결 시작의 source_twin_context를 불변 SHA로 보존한다. 각 사용자 명령의 request_twin_context는 별도다. sensor 원문은 native/unaligned이며 연결 시작 참고 Twin을 취득시각의 동기화 장면으로 주장하지 않는다.</li>
<li>SIM은 각 실제 engine observation의 revision을 기록한다. 수정·Undo·engine 변경 뒤에도 과거 이벤트를 최신 버전으로 덮지 않는다. Undo의 geometry 복원과 새 revision 생성은 동시에 성립한다.</li>
<li>기록 연결을 위해 새 물리 운전 제한을 추가하지 않았다. Stop/Close 우선권과 기존 expiry/guard를 유지한다. 인증 owner/token은 conversation ID가 아니며 기록에 복사하지 않는다.</li>
<li>예전 기록은 LEGACY_UNKNOWN으로 읽는다. 오늘의 장면으로 빈 과거 정보를 채우지 않는다. source/current 차이와 정합 상태를 조종기에서 펼쳐 확인한다.</li>
</ul>
<h2>사용자 시험 방법과 제한</h2>
<p>설치 Start-TwinPulse-Test.cmd → 같은 설치 Electron BrowserWindow 실제 클릭/입력 → 저장 Twin을 실제 Isaac에 표시 → SIM 등록/명시 연결 → 유한 회전·LiDAR·Stop all → 실제 편집/Undo/Build → 프로젝트 전환/기록 다운로드 → Exit/재시작/기록 재열기. 직접 제품 변경 API·고정 모델 응답·내부 상태 주입·별도 Chrome 사용 0. 저장 Twin 재사용은 ID 추적성 시험이며 fresh 생성·모델 품질 성적이 아니다.</p>
<p>실행 도구로 동일 Start 파일을 호출했다. Explorer 더블클릭·일반모드 전체 native 입력·OS 붙여넣기는 이 변경에서 NOT_RUN이다. 실물 로봇은 OFF/충전 상태를 유지했고 SSH/센서/모터/외부 모델 호출 0이다.</p>''')
    installed=OUT/'installed-files-05.json'
    if not installed.exists():installed=OUT/'installed-files-final.json'
    if not installed.exists():installed=OUT/'installed-files.json'
    if installed.exists():
        sections.append('<h2>최종 설치 파일</h2>'+block(read(installed)))
    for p in sorted(OUT.glob('ui-*/initial-scene.json'),reverse=True):
        rpath=p.parent/'result.json'
        if rpath.exists() and read(rpath).get('phase') not in {'cold','verify-switched-history'} and read(rpath).get('desktop',{}).get('engine',{}).get('release_id')==read(installed).get('release_id'):
            scene=read(p);r=read(rpath)
            evidence={k:scene.get(k) for k in ('revision','scene_state_sha256','original_scene_revision','artifact_id','input_revision','plan_sha256')}
            evidence.update(saved_scene_export_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_file=str(p.relative_to(OUT)))
            command=r.get('requested_command')
            if not command:
                for other in OUT.glob('ui-*/result.json'):
                    prior=read(other)
                    if prior.get('operation_id')==r.get('operation_id') and prior.get('requested_command'):command=prior['requested_command'];break
            if command:evidence.update(requested_command=command,command_utf8_sha256=hashlib.sha256(command.encode()).hexdigest())
            sections.append('<h2>시험 입력 참조 · 새 사진/모델 호출 없음</h2>'+block(evidence));break
    builds=[]
    for candidate in sorted((ROOT/'artifacts/robot-twin-lineage-20261018').glob('build*/dist/TwinPulse/windows-release-manifest.json')):
        m=read(candidate)
        sums=candidate.parents[2]/'SHA256SUMS.txt'
        builds.append(dict(candidate=candidate.parents[2].name,build_id=m['build_id'],source_manifest_sha256=m['source_manifest_sha256'],file_count=len(m['files']),
                           archive_sha256=sums.read_text().strip() if sums.exists() else 'BUILD_NOT_COMPLETE'))
    sections.append('<details><summary>모든 빌드 후보 · 이전판 보존</summary>'+block(builds)+'</details>')
    sections.append('<h2>실제 설치 UI의 모든 시도</h2><p>실패 시도를 지우거나 뒤의 PASS와 합산하지 않는다. 각각의 result.json과 화면이 원본 근거다.</p>')
    notes={
        'ui-01':'첫 View current Twin은 fresh observation unavailable로 거절됐다. 무단 자동 재송신 없음. 3초 admission/state read timeout 의심이나 단일 원인은 미확정; 원 실패 유지.',
        'ui-02':'명령·완료·scan·Stop all 연결 PASS 후 Advanced→chat Home/Twin 닫힘을 시험기가 기다리지 못해 FAIL. lease renew409 한 건 별도 보존. 실제 B 편집은 저장/적용됨.',
        'ui-03':'Undo 저장은 됐으나 controlled ack 체크박스의 비동기 반영을 시험기가 즉시 판정해 실패. geometry 복원은 새 revision이며 원 revision 해시 동일 기대가 잘못됨.',
        'ui-04':'Advanced 화면에서 chat 전용 연결 문구를 기다리던 시험기만 종료. App/Isaac 프로세스 종료나 상태 주입 없음.',
        'ui-05':'원 revision과 Undo 새 revision을 동일하다고 본 시험기 보호 조건이 중단. 임의 추가 Undo 미전송.',
        'ui-06':'선택 인자 --label 누락을 arg helper가 --cdp로 오해한 시험기 오류. 제품 명령/추가 Undo 미전송.',
        'ui-07':'저장 Undo의 실제 Build는 완료. Return to chat 직후 Home/Show Twin 전환을 기다리지 못한 시험기 FAIL.',
        'ui-08':'A/B/Undo 세 revision 및 원 event prefix 유지 PASS. 프로젝트 전환 후 5.36MB 과거 로그 GET이 공통 3초 deadline에 걸려 FAIL. 최종판에서 명시 기록 읽기만20초로 분리. fleet/viewport/status3초와 운전 freshness는 불변.',
        'ui-09':'최종03 설치 후보: Reopen POST503 conversation_save_failed로 draft_ready에 진입하지 못함. 임시파일 SHA7b8d102c65f42e0e3a19928aaac4bbc5beced611bbe04152cdad7abeb7fd2528 보존. C약20GB/readonly false. 원 OSError코드는 당시 숨겨져 있어 실제 sharing 원인 확정불가. 후속04에서 atomic rename만 Windows5/32/33 bounded backoff 및 안전한 오류코드 기록 보강.',
        'ui-10':'같은03 세션은 Delivery unknown을 유지해 추가 Reopen을 전송하지 않고 멈춤. 재전송으로 통과시키지 않음. 저장 실패를 이전 selector 문제와 구분한다.',
        'ui-11':'최종04 실제 재열기/Isaac표시/새SIM연결 PASS. 90도 요청은10.391초 뒤1.50000005rad(약85.94도)에서 TASK_TIMEOUT. 완료로 위장하지 않았다. runtime의 frame dt<=.05와 wall deadline(각도/.30+5초) 불일치가 저FPS에서 설명 가능한 가설이나 개별 프레임 계측은 미수행. 기준/속도/기한 완화0.',
        'ui-12':'실패 command/result의 동일 context 연결 PASS. scan UI 준비 직후 journal의0.5초 기록 간격 전에 다운로드해 scan이 아직 없는 시험기 관찰 경합으로 중단. 화면의 센서 준비와 durable 기록을 분리한다. 뒤 시험은 원 cadence 이후 실제 UI로 다시 내려받음.',
        'ui-13':'실패 명령·실제 scan·채팅/Twin join 및 실제 CSS 가독성 PASS. Add box는 저장됐으나 Save 응답 직후 구 acknowledgement를 읽어 새 revision의 checkbox 초기화와 Build 클릭이 경합. 원 Build는 미전송/Isaac은 기존revision유지. 뒤 시험은 현재 저장 revision을 UI에서 확인한 뒤 명시 Build한다.',
        'ui-14':'저장 B의 실제 Build는 됐으나 Advanced→chat 전환을 시험기가 너무 빨리 읽음. 이후에는 sidebar의 실제 저장 채팅을 명시 선택하여 계속한다. 임의 상태 주입 없음.',
        'ui-15':'실제 B 적용·Undo 새revision660f… 및 pre-edit geometry SHA 비교·원 이벤트 prefix 보존 PASS. 프로젝트 전환 뒤 old SIM recorder가 App종료까지 살아 있어 기록이 RECOVERED_INCOMPLETE로 나오는 실제 결함을 확인. 최종05에서 engine ACK 이후 비동기 SIM retirement, 같은프로젝트 새writer 전 done+실제thread 종료 fence를 구현. 공유 physical pool은 닫지 않는다.',
        'ui-16':'최종05 10도 명령 자체는 실제TASK_COMPLETED. 이후 LiDAR 시도는 fleet_connection_required409/현재 telemetry stale로 거절되어 전체FAIL. preview_expired409 두 건·상태/이미지 abort도 보존. 90도 기준 완화나 기하/신선도 gate 해제 없음. 다음은 같은 operation의 명령 결과를 조회하고 명시 Prepare/센서 시험만 이어감.',
        'ui-17':'실제 완료 명령/scan/layout 수치·수정/Undo/원 geometry+event prefix PASS. 최종 캡처의 기록 연결 details는 접힌 상태이므로 이 캡처를 펼친 값의 시각 검증으로 사용하지 않는다. 열린 패널의 실제 시각 근거는 동일 UI의 후보04 ui-13이며 최종05 캡처와 구분한다. 전환 후 manifest는 실제 COMPLETE/PROJECT_SWITCH였으나 시험기가 context마다 초기화되는 fleet revision을 전역 증가값으로 비교해 구context의 operation_id를 계속 사용했다. 검증기 observer를 공개X-TwinPulse-Context별로 분리하고 제품 상태 주입 없이 UI조회로 재확인한다. 단일 실행 전체PASS로 합치지 않음.',
    }
    all_results=[]
    for directory in sorted(OUT.glob('ui-*')):
        result_path=directory/'result.json'
        if not result_path.exists():result_path=directory/'cancelled.json'
        if not result_path.exists():continue
        r=read(result_path);all_results.append(r)
        summary={k:r.get(k) for k in ('phase','status','started_at','desktop','conversation','operation_id','robot_id','requested_command','motion_result','initial_events_sha256','closed_event_sha256','lineage_layout','http_errors','page_errors','request_failed','error') if k in r}
        sections.append('<section><h3>'+safe(directory.name)+' · '+safe(r.get('status'))+'</h3><p>'+safe(notes.get(directory.name,''))+'</p><a href="'+directory.name+'/'+result_path.name+'">원본 결과 JSON</a>'+block(summary))
        if r.get('steps'):
            sections.append('<table><thead><tr><th>실제 단계</th><th>판정</th><th>초</th><th>근거/오류</th></tr></thead><tbody>')
            for step in r['steps']:
                sections.append('<tr><td>'+safe(step['name'])+'</td><td>'+safe(step['status'])+'</td><td>'+safe(round(step.get('elapsed_ms',0)/1000,3))+'</td><td>'+safe(json.dumps(step.get('evidence',step.get('error','')),ensure_ascii=False))+'</td></tr>')
            sections.append('</tbody></table>')
        screens=list(directory.glob('*.png'))
        if screens:
            sections.append('<details><summary>실제 화면 '+str(len(screens))+'장</summary>')
            for screen in screens:
                relative=screen.relative_to(OUT).as_posix();sections.append('<figure><img loading="lazy" src="'+relative+'"><figcaption>'+safe(relative)+'</figcaption></figure>')
            sections.append('</details>')
        sections.append('</section>')
    final_id=read(installed).get('release_id') if installed.exists() else None
    final_runs=[r for r in all_results if r.get('desktop',{}).get('engine',{}).get('release_id')==final_id]
    functional=any(r.get('phase')=='run' and r.get('status')=='PASS' for r in final_runs)
    cold=any(r.get('phase')=='cold' and r.get('status')=='PASS' for r in final_runs)
    trace=any(r.get('phase')=='verify-switched-history' and r.get('status')=='PASS' for r in final_runs)
    scan=any(r.get('lineage_layout') for r in final_runs)
    verdict='기록 연결 구현 + 최종 설치 SIM/수정/Undo/재열기 PASS · 실물 OFF/NOT_RUN' if functional and cold else '구현됨 · 최종 설치 사용자 인수 PARTIAL (아래 실제 결과 확인)'
    if functional and cold:verdict='기록 연결·10도 동작/수정/Undo·재열기 PASS · 기존90도 회전 FAIL 유지 · 실물 OFF/NOT_RUN'
    if not functional and trace and scan and cold:verdict='기록 연결·수정/Undo·전환/재열기 분할 인수 PASS · 90도 회전 FAIL 유지 · 실물 OFF/NOT_RUN'
    sections.insert(1,'<h2>'+safe(verdict)+'</h2><p>최종 release '+safe(final_id)+' · 새 API 비용 USD0. 과거 실패는 삭제하지 않았으며 전체 제품 완료를 뜻하지 않는다.</p>')
    for directory in sorted(OUT.glob('ui-*'),reverse=True):
        rpath=directory/'result.json';screen=directory/'03-linked-ids.png'
        if rpath.exists() and screen.exists() and read(rpath).get('lineage_layout'):
            sections.insert(2,'<figure><img src="'+screen.relative_to(OUT).as_posix()+'"><figcaption>최종 설치 실제 조종기 · 작업 ID/로그와 기록 연결 메뉴. 이 캡처에서 기록 연결 details는 접혀 있다.</figcaption></figure>');break
    sections.append('<h2>보조 시험 · 실물 인수와 합산하지 않음</h2><p>system Python의 Pillow 미설치 import 실패 후 기존 .venv로 실행했다. 새 의존성 설치 0. 초기 UI selector/type 단위 시험기 오류도 수정했으며 실제 설치 인수를 대체하지 않는다.</p>')
    for result_path in sorted(OUT.glob('offline-*/result.json')):
        sections.append('<details><summary>'+safe(result_path.parent.name)+'</summary>'+block(read(result_path))+'</details>')
    for result_path in sorted(OUT.glob('normal-*/result.json')):
        sections.append('<h2>'+safe(result_path.parent.name)+' · 일반 Start</h2>'+block(read(result_path)))
    for path in sorted(OUT.glob('*exit.json')):
        sections.append('<details><summary>'+safe(path.name)+'</summary>'+block(read(path))+'</details>')
    native=OUT/'normal-native.json'
    if native.exists():sections.append('<h2>일반 설치 native 관찰</h2><p>일반 Start의 entry 타이머120.210초 ready미관찰 FAIL은 보존한다. supervisor 자체 started→ready118.319363초와는 측정 시작점이 다르며 정확한 entry→ready 시간은 기록되지 않았다. 이후 같은 일반창의 인증 Isaac 연결을 Computer Use AX로 확인했으나 이를 원 시작 기준 PASS나 전체 native 입력 PASS로 바꾸지 않는다. 현재 일반 App은 열어뒀다.</p>'+block(read(native)))
    integrity=OUT/'cold-file-integrity.json'
    if integrity.exists():sections.append('<h2>Cold 전후 원 파일 SHA · 별도 보조 확인</h2>'+block(read(integrity)))
    sections.append('''<h2>원인·수정·남은 것</h2>
<table><tr><th>항목</th><th>이번 범위</th><th>판정 한계</th></tr>
<tr><td>명령/LiDAR의 Twin 참조 공백</td><td>연결 시작·request·SIM 관측 context/불변 SHA/worker v2/operation export</td><td>새 실물 취득/전송은 전원 후 검증 필요</td></tr>
<tr><td>Stop all의 request 연결 누락</td><td>원 request ID와 요청 context fan-out, Stop 우선 유지</td><td>실물 정지거리/통신단절 성능 아님</td></tr>
<tr><td>ID 가독성</td><td>실제 화면의 CSS specificity 충돌 수정, 최종 UI layout 수치/화면 확인</td><td>전체 해상도/다국어 인수 아님</td></tr>
<tr><td>대용량 과거 로그</td><td>명시 operation record만20초 bounded/coalesced read; 실시간 state3초 유지</td><td>32/33MiB 저장 reader 경계와 긴 기록의 페이지화는 기존 제한</td></tr>
<tr><td>대화 atomic 저장 실패</td><td>Windows5/32/33의 이미 flush된 rename만 최대5회/추가 대기150ms; 실패 errno/winerror 기록·기존 원본/임시본 보존</td><td>원503의 구체적 OSError는 미기록이므로 sharing 원인 확정 아님. 모델/로봇/POST의 재실행 없음. 영구권한·disk fault는 실패로 남김</td></tr>
<tr><td>프로젝트 전환 시 열린 SIM 기록기</td><td>rebind ACK는 기존2초 switched/failed 규약 유지; lock 밖 SIM close(PROJECT_SWITCH), 중복ACK 동일결과, 재열기 factory 전 done+실제writer 종료검사</td><td>3초 drain을 넘으면 명시409·새writer 생성0. 미완료를 COMPLETE로 위장하거나 실물연결을 종료하지 않음. shutdown/close 예외 event도 검증</td></tr>
<tr><td>시작/상태 경합</td><td>첫 View 거절·과거 lease409 보존. 무단 최신성 완화·자동 재전송 없음</td><td>모든 시작 부하의 응답성 해결 아님; v531의 약122초 시작 실패도 유지</td></tr>
<tr><td>최종 SIM 90도 회전</td><td>85.94도/TASK_TIMEOUT 실패와 원 command/result/context 보존</td><td>저FPS에서 dt clipping과 wall deadline 불일치 의심. bounded substep 시간적분/계측/재인수는 미완료; 성공으로 합산하지 않음</td></tr>
<tr><td>실물 정합</td><td>UNALIGNED/native_sensor, operator estimate 명시</td><td>센서 취득시각 동기화/world 정합/실측 TF·정지/정체·Wi-Fi·360/장시간은 NOT_RUN</td></tr>
<tr><td>다른 기존 과제</td><td>원 프로젝트/사진/실패/장부/dirty 변경 보존</td><td>사진 품질·CAD/BRep·clean PC·실물2대 잔여 불변</td></tr></table>
<h2>비용·설정·안전</h2>
<p>이번 새 provider HTTP0 / 추가 USD0 / 새 미확정0. 추가50 캠페인 기존 추정 USD0.8546553 불변; 이전20 캠페인 USD14.9450973(UNKNOWN0.4770432 포함)은 별도이며 새 예산으로 합치지 않았다. 공급자 청구서가 아니다.</p>
<p>Astra xhigh 1명은 provenance 설계와 최종 소스 읽기 검토만 수행했고 그 경로에서 추가 blocker를 찾지 못했다. 후속 저장 오류 검토 요청은 model capacity 오류로 수행되지 않아 main이 범위를 한정해 수정/시험했다. main 실제 모델/effort ID는 도구로 확인 불가, 임의 설정 변경 주장 없음. 별도 UI 보조를 이번 범위에서 사용하지 않았다. 새 설치 의존성·실물·Cloud·공개·commit/push 0.</p>
<p>실물 다음 확인: 전원/같은 LAN → 실제 App Check Connection → source context 및 request/scan/trial/raw receipt 연결 확인 → 명시 현장시험. 연결 시작 Twin이 없는 경우 NO_CURRENT_TWIN이 맞으며 과거 자료를 현재 Twin으로 재분류하지 않는다. 이후 장면을 수집 기준으로 바꿀 때는 새 작업을 명시적으로 시작한다.</p>''')
    sections.append('<footer>보고서 생성 UTC '+safe(datetime.now(timezone.utc).isoformat())+'</footer>')
    body=''.join(sections)
    html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse · Robot Twin lineage</title><style>body{font:16px/1.65 Segoe UI,Malgun Gothic,sans-serif;color:#16333d;max-width:1180px;margin:36px auto;padding:0 24px;background:#f5f9fa}h1,h2,h3{line-height:1.3}h2{margin-top:42px;border-top:1px solid #bdd1d8;padding-top:22px}section,details{background:white;padding:16px;margin:12px 0;border:1px solid #cadce0;border-radius:10px}summary{cursor:pointer;font-weight:600}pre{font:12px/1.6 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#edf3f6;padding:12px}table{border-collapse:collapse;width:100%;font-size:13px;table-layout:fixed}th,td{border:1px solid #bdcdd5;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}figure{margin:20px 0}img{width:100%;height:auto;border:1px solid #bad0d8}figcaption{font-size:12px}a{color:#075eac}footer{font-size:12px;margin-top:40px}</style>'+body+'</html>'
    (OUT/'report.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(path=str(OUT/'report.html'),sha256=hashlib.sha256((OUT/'report.html').read_bytes()).hexdigest(),ui_attempts=len(all_results)),ensure_ascii=False))


if __name__=='__main__':main()
