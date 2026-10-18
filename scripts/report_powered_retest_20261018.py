# SPDX-License-Identifier: Apache-2.0
"""One local report from actual App downloads and offline verification artifacts."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-retest-20261018'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def esc(value):return html.escape(str(value))
def code(value):return '<code>'+esc(value)+'</code>'
def table(headers,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def main():
    raw=read('analysis/original-analysis.json');replay=read('analysis/native-replay.json')
    ui=read('analysis/actual-ui-actions.json');recording=read('recording-01/session.json')
    tests=read('regressions.json');web=read('web-tests-final.json');scope=read('session-scope.json')
    installed=read('installation-unchanged.json')
    photo=Path(scope['input_photo']);photo_sha=hashlib.sha256(photo.read_bytes()).hexdigest()
    exported=[dict(file=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((OUT/'raw').iterdir()) if p.is_file()]
    (OUT/'downloaded-file-manifest.json').write_text(json.dumps(exported,indent=2),encoding='utf-8')
    ended=next(c for c in reversed(raw['cleanup']) if c.get('subsystem')=='session')
    native_cleanup=next(c for c in raw['cleanup'] if c.get('subsystem')=='native_sensor')
    trial=next(c['trial'] for c in raw['commands'] if c.get('trial'))
    arm=next(c for c in raw['commands'] if c.get('action')=='field_arm')
    summary=read('operation-summary.json')
    status=dict(schema='powered-focused-session-verdict-1.0',verdict='PARTIAL_NOT_READY_FOR_DRIVING',
        installed_release=installed['release_id'],operation_id=raw['identity']['operation_id'],
        trial_id=trial['trial_id'],wheel_publications=len(raw['motion_publications']),
        stationary=trial['status'],arm=arm['status'],cleanup_confirmed=ended['confirmed'],
        raw_files_verified=len(exported),raw_events=raw['receipt']['event_count'],
        fixed_source_only=True,installed_package_changed=False,
        remaining=['COIN-D4 unclassified11byte response/scan continuity',
            'ROS source-age latency publisher/DDS/executor attribution and correction',
            'Raspberry Pi tracker80ms real-time budget',
            'candidate package freeze and actual installed non-motion/movement reacceptance',
            'bootstrap/manual/chat90/full-turn/soak/proximity/slip/Wi-Fi/IMU/world alignment'],
        provider_http=0,additional_usd=0,prior_ledgers_changed=False)
    (OUT/'verdict.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    ids=raw['identity'];context=ids['source_twin_context']
    frames=ui['cleanup_frame'];cleanup_image='recording-01/'+frames['file'] if frames else 'cleanup-confirmed.png'
    metric_rows=[]
    for name,m in raw['metrics'].items():
        if m:metric_rows.append((esc(name),m['n'],f"{m['median_s']*1000:.3f}",f"{m['p95_s']*1000:.3f}",f"{m['max_s']*1000:.3f}"))
    actions=table(['응답 UTC','실제 App 요청','request ID','서버 응답 표시'],[
        (esc(datetime.fromtimestamp(a['at']/1000,timezone.utc).isoformat()),esc(a['request']['action']),code(a['request'].get('request_id')),
         esc((a.get('last_command') or {}).get('status','not recorded'))) for a in ui['actions']])
    commands=table(['로봇 시각/sequence','실행 명령','상태/사유','request ID'],[
        (f"{c['t']:.6f} / {c['sequence']}",esc(c.get('action')),esc(str(c.get('status'))+' / '+str(c.get('reason',''))),code(c.get('request_id','not recorded'))) for c in raw['commands']])
    identity_rows=[('설치/소스',code(installed['release_id'])+'<br>'+code(installed['source_manifest_sha256'])),
        ('launch / 진단 실행',code(recording['identity']['engine']['launch_id'])+'<br>'+code('e9a790c03a1e4407967f359b452a9e16')),
        ('읽기 검사 execution / observation',code('c1849b93f4164f10a504fa4a7d8a8db0')+'<br>'+code('80910450497f33920efdfa93')),
        ('operation / stationary trial',code(ids['operation_id'])+'<br>'+code(trial['trial_id'])),
        ('robot / connection epoch',code(ids['robot_id'])+'<br>'+code(ids['connection_epoch'])),
        ('binding / 실제 worker SHA',code(ids['binding_sha256'])+'<br>'+code(ids['worker_sha256'])),
        ('chat / conversation',code(context['project_id'])+'<br>'+code(context['conversation_session_id'])),
        ('Twin revision / engine / stage',code(context['scene_revision'])+'<br>'+code(context['engine_session_id'])+'<br>'+code(context['stage_epoch'])),
        ('source context / 좌표 관계',code(context['context_id'])+'<br>TWIN_REFERENCE / UNALIGNED — 물리 localization이 아님'),
        ('사진 입력 SHA',code(photo_sha)+'<br>현재 현장 참고 사진만 사용. 외부 전송/새 Twin 생성0.'),
        ('native 원문 SHA',code(replay['raw_sha256'])),
        ('최종 UI 화면 MP4 SHA',code(hashlib.sha256((OUT/'recording-01/app-screen.mp4').read_bytes()).hexdigest()))]
    report=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwinPulse — 2026-10-18 실제 전원 재시험</title><style>
body{{font:16px/1.65 "Segoe UI","Malgun Gothic",sans-serif;color:#172a32;background:#f4f7f8;margin:0}}main{{max-width:1120px;margin:auto;padding:28px}}section{{background:white;padding:24px;margin:20px 0;border:1px solid #d5e0e4;border-radius:10px}}h1{{line-height:1.3}}h2{{font-size:23px}}.verdict{{border-left:7px solid #bd452c;background:#fff1e8}}code{{font-size:13px;overflow-wrap:anywhere;white-space:normal}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border:1px solid #d4dde0;padding:10px;text-align:left;vertical-align:top}}th{{background:#e9f0f2}}.scroll{{overflow:auto}}img,video{{max-width:100%;height:auto;border:1px solid #b7c4ca}}a{{color:#006b79}}li{{margin:6px 0}}small{{color:#435d68}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.bad{{color:#a82715}}.good{{color:#116b45}}
</style><main><h1>TwinPulse 실제 전원 재시험·원인 분석</h1><p>2026-10-18 · 실제 설치 Electron Test 창/Isaac · 하나의 현재 작업 보고서</p>
<section class="verdict"><h2>전체 PARTIAL / 실물 주행 NOT_READY</h2><p>연결·전압·원시 LiDAR/ROS 수집·원문 반출·정상 정리는 성공했지만, stationary 시험은 INCONCLUSIVE이고 arm은 거절되었습니다. 바퀴 비영(非零) 이동 publication은0입니다. 따라서 수동·채팅 조종·단일360도 시험을 통과했다고 하지 않습니다.</p><p>진단 누락·반복 fault 세대 경합·arm 신선도 명시 확인·물리/SIM 정지 문구를 <strong>소스에서 수정</strong>했습니다. 보조 회귀129/웹104/tsc·build는 통과했지만, <strong>새 설치본 동결·실물 재인수는 아직 하지 않았습니다.</strong> 현재 설치는 시험에 사용한08 그대로입니다. 이전 v541 PC/SIM gate READY를 현재 실물 준비 판정으로 재사용하지 않습니다.</p></section>
<section><h2>실제 수행 경로와 차이</h2><p>사용자는 충전선 분리·둘레30cm 확보·현장 감독·즉시 전원 차단 가능을 이번 시험 직전에 확인했습니다. 동일 root <code>Start-TwinPulse-Test.cmd</code>를 실행 도구로 호출하고, 실제 설치 BrowserWindow에서 Robots→PC 준비→읽기 검사→저장 거실→View current Twin→Connect→LiDAR On→Stationary→Prepare→Arm→Off→Disconnect→로그/파일 다운로드→Exit를 클릭했습니다.</p><p>Explorer 더블클릭·일반 모드 전체 native 입력·OS 붙여넣기·native Isaac 입력은 NOT_RUN입니다. Computer Use 지침을 읽고 이전 geometry/capture 한계에 따라 명시 Test/Playwright 같은 창을 사용했습니다. 별도 Chrome·직접 제품 변경 API·SSH 명령·내부 상태 주입·고정 모델 응답으로 대체하지 않았습니다. 읽기 분석은 수집 종료 뒤 원본 파일에 대해서만 했습니다.</p><p>녹화는 실제 Electron renderer1844프레임/약{recording['events'][-1]['evidence']['wall_ms']/1000:.3f}초, 무음입니다. 로봇 실물 영상이나 native desktop 전체 녹화는 아닙니다. 로봇 operation 시각 창은 {raw['elapsed_robot_s']:.3f}초입니다.</p></section>
<section><h2>기능별 판정</h2>{table(['항목','결과','실제 근거/범위'],[
('PC 준비·읽기 SSH','PASS_SCOPED','실측12.44V·command zero·wheel0·port restore. torqueON만으로 움직임으로 판정하지 않음. NO_SENSOR_DATA는 당시 미시작 상태.'),
('저장 Twin·Isaac 표시','PASS_SCOPED','기존 거실 revision을 명시 적용. 현재 사진으로 새 재구성/정합을 했다는 뜻 아님.'),
('지속 연결·전압 갱신','PASS_SCOPED','같은 boot/operation에서 native와 ROS를 받음. ROS 구간12.33~12.22V대 갱신. 최신 전압과 주행 허가를 분리.'),
('native 원시 수집','PASS_SCOPED',f"{replay['raw_bytes']:,}B/{len(read('analysis/native-chunks.json')):,}chunks 원SHA 검증. 전체{replay['nodes']:,}node/byte accounting exact. 기하/빔시각/주행 안전 인증 아님."),
('8초 Stationary','INCONCLUSIVE',f"trial {trial['trial_id']} · {trial['ended_s']-trial['started_s']:.6f}초/10frame에서 FIELD_COMPLETE_NATIVE_RING_REQUIRED. 뒤 raw 수집을 합쳐8초PASS로 만들지 않음."),
('Prepare·ROS','PARTIAL','Prepare COMPLETED·zero/OFF, sensor_state/odom/tf/guard 원문39212개. source-age가 반복 기준을 넘으므로 주행 준비 성공 아님. IMU·tf_static 수신 증명 없음.'),
('감독 Arm','REJECTED',f"{arm['request_id']} / MOTION_GENERATION_CHANGED. 해당 순간 native ring 검사는 먼저 통과했음. ring거절로 잘못 귀속하지 않음."),
('Bootstrap·패드·채팅90·단일360·Soak','NOT_RUN','Arm 거절 후 바퀴 명령/자동 retry0. 근접10cm·slip·Wi-Fi·제동·실물 정합도 미검증.'),
('LiDAR Off·Disconnect·로그 반출','PASS_SCOPED','로봇 cleanup confirmed/recording complete·PC117133accepted=saved/224750258B. 실제 UI로56개 다운로드,54segment 원SHA exact·9개 생성된 helper 원본 exact.'),
('정상 App 종료','PASS_SCOPED','반출 뒤 실제 Exit 버튼으로 App/Isaac 종료,8765/19222 listener 없음 확인. native rotor 물리 시각 정지 확인은 UNCONFIRMED.'),
('수정 후 재검증','SUPPLEMENTARY_ONLY','Python129/웹104/tsc·build 통과. 새 설치/실물 전체 재시험을 대신하지 않음.')])}</section>
<section><h2>원인 — 확인 사실과 남은 가설</h2><h3>1. LiDAR ring 불완전: 알려지지 않은11바이트 구간</h3><p>실패 frame393의 원byte offset537379–537389에 <code>a5 5a 04 00 fe 3a 06 39 00 00 00</code>가 있습니다. 앞뒤 scan packet CRC는 유효하지만 byte-span이 불연속이라 현재 complete 검사가 거절했습니다. 전체 원문에서11byte gap201회/불완전 frame202개·checksum오류0·interval fallback1개를 확인했습니다. 복구/삭제하여 PASS시키지 않았습니다.</p><p>ROBOTIS 보존 SDK <code>8277b288902f28b37948b42e1bb80ba59afbba60</code>의 일반 A55A 응답 구조에 대입하면 선언 길이가0x3AFE0004가 되어4byte payload와 맞지 않습니다. 별도 구형 FAFA 경로도 이를 정의하지 않습니다. <a href="https://github.com/ROBOTIS-GIT/coin_d4_driver/blob/main/include/coin_d4_driver/lidar_sdk/lidar_information.hpp">공식 SDK</a>와 보존본을 Astra가 읽었으며, timestamp/control이라는 근거를 찾지 못했습니다. 제조사 매뉴얼 fetch timeout은 미확정으로 남깁니다.</p><h3>2. ROS 원본 age와 callback receipt age는 다름</h3><p>event20220은 source223.906ms/receipt0.876ms/guard20.917ms·12.33V/button0입니다. 배터리 부족이 아닙니다.8016진단 중CURRENT4130/SENSOR_SOURCE_AGE3886, 원본 age 중앙값198.933ms/p95259.771ms입니다. callback 입장 추정 age 중앙값188.737ms는 로깅 이후만의 지연으로 설명되지 않지만, publisher·DDS·executor 어느 단계가 주원인인지는 이 로그만으로 확정하지 못합니다. 아래 시각 차이 추정은 ROS와 monotonic 속도가 안정적이라는 조건부 계산입니다.</p>{table(['관측 지표','n','중앙값 ms','p95 ms','최대 ms'],metric_rows)}<h3>3. 진단 누락과 generation 경합</h3><p>worker/adapter에는 telemetry_diagnostic/native_diagnostic가 있었지만 RobotFleet 기본 row가 두 키를 선언하지 않아 기존 키만 복사하는 allowlist에서 버렸습니다. 또한 source-age 반복 pause가 무권한인 상태에서도 generation을 계속 올려 최종{raw['max_generation']}이 됐습니다. Arm request의 generation1880이 worker 경계에서 낡아 거절됐습니다. 이 두 소프트웨어 결함은 소스 수정·회귀 검증했습니다. 실제 source freshness가 해결됐다는 뜻은 아닙니다.</p><h3>4. tracker와 정지 표시</h3><p>실제 Raspberry Pi에서 TRACKING_COMPUTE_DEADLINE이 반복됐습니다. 과거 Windows replay의 개선은 Pi80ms 인수의 보증이 아닙니다. 현재도 차체 pose/정합은 UNQUALIFIED입니다. 또 실제 물리 PAUSED 상태에 Isaac의 “engine stop” 대기 문구가 표시됐습니다. 물리 정지는 별도 readback 증거이며 SIM ACK로 대신하지 않도록 문구를 수정했습니다.</p></section>
<section><h2>수정 내용·검증 범위</h2><ol><li>공개 fleet row에 두 진단 키를 선언하고 deepcopy/unknown null·capability 불변을 회귀했습니다. UI에 원본 age도 표시합니다.</li><li>같은 자동 tick fault를 이미 무권한 상태에서 반복 관측할 때만 세대 증가를 생략합니다. nonce는 매번 폐기하며 새 watch/입력·reason변경·Stop·close·config·arm은 새 fence를 유지합니다. release재시도·작업 취소도 생략하지 않습니다.</li><li>field_arm은 현재 link.fresh를 먼저 확인합니다. native 완전 ring/현재 nonce/generation/post-arm 새 입력도 여전히 필요합니다.</li><li>callback 입장 ROS source clock과 monotonic 시각을 serialization 이전에 기록하고 로깅 비용을 별도로 계측합니다. 원문/원시각을 갱신하여 fresh로 위장하지 않습니다.</li></ol><p>ROS200ms/native350ms/tracker80ms·11.1V 보호·속도·10cm/coverage·stop 기준·기하를 완화하지 않았습니다. unknown11bytes는 decoder에서 임의 정상화하지 않았습니다. 새 driver/설치·Cloud·commit/push·삭제0.</p><p>최종 보조 결과는 <a href="regressions.json">Python129/source SHA/원로그</a>, <a href="web-tests-final.json">웹104</a>, <a href="installation-unchanged.json">기존 설치1612파일 원SHA 불변</a>입니다. Astra xhigh1명은 독립 원인/설계/변경 소스 읽기만 했으며 App/실물/시험 실행·수정은 주 작업자가 순서대로 했습니다. 주 모델 ID는 도구로 직접 확인할 수 없었습니다.</p><p class="bad">이 변경은 아직 소스 후보입니다. 알려진 실물 blocker가 남아 있으므로 전체 ready 설치본으로 교체하거나 “완료”라고 하지 않았습니다.</p></section>
<section><h2>실제 화면·녹화</h2><p>아래는 편집한 mockup이 아니라 원 App 캡처입니다. 실패와 정리 자료를 그대로 보존했습니다.</p><figure><img src="stationary-inconclusive.png" alt="실제 Stationary INCONCLUSIVE 화면"><figcaption>Stationary 실패·원 실행ID</figcaption></figure><figure><img src="{cleanup_image}" alt="실제 Disconnect/cleanup 이후 프레임"><figcaption>녹화 원본 중 Disconnect 이후 프레임. 녹화 시각/번호는 actual-ui-actions.json 참조.</figcaption></figure><video controls preload="metadata" src="recording-01/app-screen.mp4"></video><p><a href="recording-01/app-screen.mp4">원 녹화 열기</a> · <a href="recording-01/frame-times.json">프레임 시각</a> · <a href="recording-01/session.json">recorder 원 receipt/errors0</a></p></section>
<section><h2>모든 실제 요청과 로봇 결과</h2><p>UI의 request body/응답 시각과 로봇 raw ACK를 분리해 보존합니다. UIaccepted는 실행완료/주행성공이 아닙니다. 이벤트 stage가 PC_PREPARATION에 남았던 REPL closure 관측기 결함도 삭제하지 않았습니다. 아래 표는 별도 recorder 원 요청에서 파생했습니다. locator timeout·최초 recorder 디렉터리 오류·native geometry/capture 미수행은 시험 도구 차이이며 제품 실패와 합치지 않습니다.</p><details><summary>App POST 요청 전부</summary>{actions}</details><details><summary>watch 제외 로봇 명령 ACK 전부</summary>{commands}</details><details><summary>원 command fault</summary><pre>{esc(json.dumps(raw['faults'],ensure_ascii=False,indent=2))}</pre></details></section>
<section><h2>실행·출처 식별</h2>{table(['구분','정확 ID/SHA'],identity_rows)}<p>이전 operation55e281..의0frame 실패와 이번ee988..의10frame 실패는 별도입니다. 원사진ITM0018 생성·공개 Brisbane·집 사진 품질·CAD·자산 확장 인수로 합치지 않습니다. 현재 사진과 기존Twin은 정합하지 않았습니다.</p></section>
<section><h2>반출·최종 상태·비용</h2><p>PC receipt117133accepted=saved/complete=true/error=null. 원 다운로드56개/54segments SHA exact·CRC검사를 포함한 raw8336993B 전량 accounting·생성된9helper 원문 전량 SHA exact입니다. field-stop/qualification은 실제 만들어지지 않았으므로 NOT_CREATED를 유지합니다. native STOP write/data quiet/port restore와 base reap/finalOFF/독립readback은 기록되었으나 물리 rotor 시각검증·차체 실측은 하지 않았습니다. 최종 board read는12.20V/OFF·wheelvelocity0·명령zero/port restored입니다.</p><p>App 종료 후 로봇 추가접속/구동0. 이번 Nebius/다른 모델 HTTP0·추가비용USD0. 추가50캠페인 이전 추정1.3933014/잔여48.6066986, 이전20캠페인14.9450973(UNKNOWN.4770432포함)은 별도/장부불변이며 공급자 청구서가 아닙니다. API키/인증 헤더 출력0·현재 사진 외부전송0. 새EXE/ZIP/installer0·원dirty/원사진/프로젝트/이력보존·삭제0. 종료 뒤 C여유 약55.95GB 관측은 전체 원인별 사용량 산정이 아닙니다.</p><p><a href="downloaded-file-manifest.json">56개 파일 SHA</a> · <a href="operation-summary.json">실제 App 요약</a> · <a href="raw/receipt.json">PC원문 receipt</a> · <a href="analysis/original-analysis.json">원문 분석</a> · <a href="analysis/native-replay.json">전량 native 재현</a> · <a href="analysis/robot-sources/final-read.log">독립 최종 readback</a> · <a href="verdict.json">현재 판정</a></p></section>
<section class="verdict"><h2>정확히 남은 작업</h2><ol><li>COIN-D4의 반복11byte 구간을 제조사 정의/독립 검증식으로 식별하고, gap을 몰래 지우지 않는 protocol-aware decoder를 구현·전량 원데이터 재현할 것.</li><li>추가한 callback source/receipt/기록 시간으로 publisher→DDS→executor 지연을 분리하고 제어와 기록/추적 계산 스케줄링을 개선할 것.200ms 판정을 단순 증가시켜 통과시키지 않을 것.</li><li>Pi tracker80ms 초과의 CPU/스케줄 지연을 분리·개선하고 원 데이터 결과/기하 기준을 유지할 것.</li><li>수정 후보 동결·새 설치본의 비구동 인수 후, 새 현장 확인 아래 원 Stationary→원 bounded bootstrap→수동/해제→채팅90→단일360+scan→Stop/raw반출을 실제 앱에서 재검증할 것. 현재 알려진 차단을 고치기 전에 사용자를 다시 켜 달라고 요청하지 않을 것.</li><li>IMU/정합/센서 시각·근접외곽10cm·독립 slip·실제Wi-Fi·2대 실물·자율주행은 별도 미검증으로 유지할 것.</li></ol><p>따라서 이번 결과는 “전원만 켜면 전체 기능이 검증됨”이 아닙니다. 연결·데이터 확보·정리 성공과 주행 미성공을 분리합니다.</p></section><p><small>생성 {datetime.now(timezone.utc).isoformat()} · 로컬 보고서/외부 전송 없음</small></p></main></html>'''
    (OUT/'report.html').write_text(report,encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),verdict=status['verdict'],files=len(exported),web=web['numPassedTests'],photo_sha256=photo_sha),ensure_ascii=False))

if __name__=='__main__':main()
