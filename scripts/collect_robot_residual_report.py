# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only evidence collection. No product, model or robot requests."""
from datetime import datetime,timezone
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-residuals-20261018'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def brief(v):
    return {k:v[k] for k in ('status','phase','project','operation_id','desktop','release_id','source_sha256','error','ready_wait_ms','steps','http_errors','request_failures','request_failed','network_failures','errors','page_errors','stop_fence_rejections') if k in v}
def main():
    paths={
        'fresh':OUT/'ui-fresh-08b/result.json','cold':OUT/'ui-cold-08/result.json',
        'lineage':OUT/'lineage-08/result.json','lineage_cold':OUT/'lineage-cold-08/result.json',
        'normal':OUT/'normal-08/result.json','supplementary':OUT/'offline-final08/result.json',
        'installation':OUT/'installation-exact08-after-install.json','budget':OUT/'budget-final.json'}
    install=read(paths['installation']);release=install['release_id'];source=install['source_manifest_sha256']
    normal=read(paths['normal']);restart=read(OUT/'normal-08-restart/result.json');shutdown=read(OUT/'normal-08/shutdown.json')
    restart_shutdown=read(OUT/'normal-08-restart/shutdown.json')
    lifecycle=dict(status='PASS' if shutdown['status']=='PASS' and restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF' and restart_shutdown['status']=='PASS' else 'FAIL',
        release_id=release,source_sha256=source,normal_start_launch_id=normal['launch_id'],shutdown_clean=shutdown['shutdown_clean'],
        restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',restart_launch_id=restart['launch_id'],
        restart_debug_listener_count=restart['debug_listener_count'],restart_app_listener_count=restart['app_listener_count'],
        restart_authenticated_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',restart_ready_wait_ms=restart['ready_wait_ms'],
        input='Identical root Start through execution tool; native observed-window Alt+F4. Explorer double-click NOT_RUN.',
        restart_shutdown_clean=restart_shutdown['shutdown_clean'],
        references=[dict(path=str(p),sha256=digest(p)) for p in (paths['normal'],OUT/'normal-08/shutdown.json',OUT/'normal-08-restart/result.json',OUT/'normal-08-restart/shutdown.json',OUT/'native-attempts.json')])
    write(OUT/'normal-lifecycle.json',lifecycle);paths['lifecycle']=OUT/'normal-lifecycle.json'
    manifest=dict(release_id=release,source_sha256=source,evidence=[dict(role=k,path=p.relative_to(OUT).as_posix(),sha256=digest(p)) for k,p in paths.items()])
    write(OUT/'evidence-manifest.json',manifest)
    run=subprocess.run([sys.executable,'scripts/verify_robot_focus_gate.py','--manifest',str(OUT/'evidence-manifest.json'),'--output',str(OUT/'gate-result.json')],cwd=ROOT)
    gate=read(OUT/'gate-result.json');budget=read(paths['budget']);before=read(OUT/'budget-before.json')
    negative=deepcopy(manifest)
    for item in negative['evidence']:
        if item['role']=='fresh':
            failed=OUT/'ui-fresh-final/result.json';item.update(path=failed.relative_to(OUT).as_posix(),sha256=digest(failed))
    negative['classification']='NEGATIVE_EVIDENCE_TEST_NOT_APP_ACCEPTANCE'
    write(OUT/'gate-negative-original-failure-manifest.json',negative)
    rejected=subprocess.run([sys.executable,'scripts/verify_robot_focus_gate.py','--manifest',str(OUT/'gate-negative-original-failure-manifest.json'),'--output',str(OUT/'gate-negative-original-failure-result.json')],cwd=ROOT)
    if rejected.returncode!=1 or 'RUN_NOT_PASS:fresh' not in read(OUT/'gate-negative-original-failure-result.json')['issues']:
        raise ValueError('GATE_DID_NOT_REJECT_ORIGINAL_FAILURE')
    new={k:r for k,r in budget['requests'].items() if k not in before['requests']}
    campaign_delta=float(budget['protected_additional_50_total'])-float(before['protected_additional_50_total'])
    accounting=dict(this_turn_http=len(new),this_turn_estimated_usd=round(campaign_delta,7),
        additional_50_total=budget['protected_additional_50_total'],unknown=budget['new_unknown_usd'],
        previous_20_campaign=budget['prior_20_campaign'],basis='Frozen catalog/usage estimate, not provider invoice',
        model_ids=sorted(set(r['model_id'] for r in new.values())))
    write(OUT/'accounting-summary.json',accounting)
    attempts=[]
    for p in sorted(OUT.glob('*/result.json')):
        value=read(p);item=dict(path=p.relative_to(OUT).as_posix(),sha256=digest(p),**brief(value))
        if any(not e.get('exiting') and not e.get('fault') for e in value.get('request_failed',[])+value.get('request_failures',[])):
            item['qualification']='NOT_FINAL_UNCLASSIFIED_REQUEST_FAILURE'
        attempts.append(item)
    raw=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local/physical-live/55e28197e6ca4f3195d69293f606acc7'
    raw_hashes=[dict(name=p.name,bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(raw.iterdir()) if p.is_file()]
    write(OUT/'attempt-index.json',attempts);write(OUT/'original-physical-file-hashes.json',raw_hashes)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse 잔여 결함 수정·재인수</title>',
        '<style>body{max-width:1180px;margin:30px auto;padding:0 24px;font:16px/1.65 system-ui;background:#f6f9fb;color:#173041}section{background:white;border:1px solid #ccdbe2;border-radius:12px;padding:20px;margin:20px 0}pre,code{white-space:pre-wrap;overflow-wrap:anywhere}pre{font-size:13px}img,video{max-width:100%}td,th{padding:8px;border:1px solid #cbd5df;text-align:left;vertical-align:top;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}a{color:#006580}</style>',
        '<h1>TwinPulse — 잔여 결함 수정 및 설치 App 재인수</h1><p>'+escape(datetime.now(timezone.utc).isoformat())+'</p>',
        '<section><h2>종료 판정</h2><pre>'+escape(json.dumps(gate,ensure_ascii=False,indent=2))+'</pre><p>위 gate는 이 PC 최종 설치의 소프트웨어 경로 판정이다. 실물 센서 지연·실제 저속 주행·제동·위치 정합을 통과했다는 뜻이나 무결함 보장이 아니다. 충전 중 로봇 SSH/연결/센서/모터 활성 0. 공개 배포·commit/push·새 의존성 설치 0.</p></section>',
        '<section><h2>이번에 확인하고 수정한 내용</h2><ol>',
        '<li>Native frame의 반복 전체 deepcopy를 불변 JSON-compatible frame 참조로 대체. 디코드/해시/동결은 publication lock 밖에서 수행. 원 native byte/node/timestamp/age 기준 유지.</li>',
        '<li>ICP 최근접 검색에 공간 색인을 사용. 원 0.15m 거리·seed·tie-break·반복·80ms 연산 deadline을 유지. 저장 raw 71쌍 결과 exact 비교. Windows replay를 Raspberry Pi 실물 성공으로 부르지 않음.</li>',
        '<li>ROS가 guard에 거절되어도 이미 수신한 실제 전압/표본 나이를 먼저 표시. callback 입장 receipt를 유지해 로그 기록 시간이 freshness를 갱신하지 않음. idle board 읽기와 event lock 분리·단계별 시간/실패 진단 추가. 로봇 측 실제 지연의 최종 원인은 재시험 필요.</li>',
        '<li>Cold 원문 journal/segment SHA·context·sequence를 검증해 요약/종료 receipt·worker source 목록을 복원. 권한/연결은 복원하지 않음. 원 physical operation/trial 사유를 같은 ID로 표시. 과거 raw 재작성 없이 검증된 33개 source map만 별도 sidecar에 추가.</li>',
        '<li>실제 최종 후보 SIM 60초 hold가 19.055초에 중단되어 원 FAIL 보존. 전체 snapshot 2회→1회·한 현재 broker observation, physical-active guard에서 과거 journal 전체 복사 제거. 엔진 교환은 80ms+RTT 대신 단일 in-flight 50ms 시작주기로 변경. 250ms intent/500ms watchdog·Stop fencing 유지. 특정 한 병목만이 유일 원인이라고 단정하지 않음.</li>',
        '<li>UI 보조 2FAIL의 실제 상태 fixture 누락/English-default copy 불일치 수정. 테스트 기준을 낮추지 않음. recorder의 수동 CDP client 기본 download-directory 덮어쓰기는 noDefaults passive 연결로 수정.</li><li>후속 실제 lineage03에서 Stop all 뒤 갱신 중 옛 JSON을 받는 결함을 재현. 실제 Stop ID는 원 journal에 존재했고 UI가 비동기 재조회 전에 옛 객체를 내려줬다. 새로고침 중 다운로드와 handler를 차단하고 pending 표시를 추가. 시험도 정확 Stop200·적용epoch 및 동일 request ID를 요구하도록 강화. <a href="log-refresh-failure-analysis.json">원 실패 분석</a>.</li></ol></section>',
        '<section><h2>원 실물 실패 — 보존</h2><p>operation <code>55e28197e6ca4f3195d69293f606acc7</code>, trial <code>9e43a4b2371b4bf2b51662d4f4e44502</code>: 0.02929649s·0frame, FIELD_NATIVE_RECEIPT_STALE_OR_BACKLOG / INCONCLUSIVE. 바퀴 0. 원 2,334 events/7,315,477B와 native 369 frames/506,899B는 그대로다. 현재 소프트웨어 수정이 이 원 조건의 실물 성공을 소급해 만들지 않는다.</p><p><a href="original-physical-file-hashes.json">원 파일 SHA</a> · <a href="original-cold-operation-build01.json">실제 App에서 내려받은 원 작업</a> · <a href="offline-replay.json">조용한 Windows replay</a> · <a href="offline-replay-frozen.json">부하 중 replay</a></p></section>',
        '<section><h2>측정 결과와 남은 원인 불확실성</h2><p>Windows 저장 데이터의 동일71쌍 ICP 중앙값은 조용한 실행에서107.49→10.998ms, 부하 중126.997→13.028ms. 80ms 초과71/71→0/71이며 결과 exact. Native frame 생성 중앙값은 부하 중9.104→2.377ms, 그러나 개선 후 최대144.762ms 스케줄링 outlier가 있어 하드 실시간 보장은 아니다. 실제 로봇에서는 별도 재시험이 필요하다.</p><p>lineage04의 Undo 미리보기 뒤 apply 요청 누락은 원 FAIL이며, 화면이 준비된 뒤 단일 Save200은 별도 진단이다. 정확한 missed-click/render 원인은 미확정. 새 전체 인수는 정확한 preview200·동일 revision 화면·Save 활성·apply200·기하/새revision/이벤트 보존을 모두 요구한다. <a href="lineage04-preview-save-diagnostic.json">진단</a>.</p><p>lineage04b는 기능8단계가 통과했지만 projects GET 취소1건에 단계 정보가 없어 최종 인수에서 제외했다. 종료보다18초 전 취소이므로 정상 Exit로 분류하지 않았다. no-App catalog 조회0.869s/0.293s만으로 당시 지연 원인을 단정하지 않는다. 새 전체 실행에는 요청/실패 시각·경과·context·단계를 계측했다. <a href="lineage04b-catalog-abort-diagnostic.json">원문과 한계</a> · <a href="astra-read-only-review.json">Astra xhigh 읽기 검토 범위</a>.</p></section>',
        '<section><h2>비용·모델</h2><pre>'+escape(json.dumps(accounting,ensure_ascii=False,indent=2))+'</pre><p>추가50 캠페인은 새 예산이 아니며 이전 사용 포함. 이전20 캠페인의 미확정 .4770432는 별도 그대로다. 전체 provider 청구 잔액이라고 해석하지 않는다.</p></section>',
        '<section><h2>실제 시험 경로와 제한</h2><p>일반 root Start-TwinPulse.cmd를 동일 파일 실행도구로 호출. 같은 설치 Electron BrowserWindow의 명시 Test/Playwright에서 실제 New chat→실제 Flash/Nemotron→Isaac 두 SIM→수동/채팅/scan→로그 download→저장·cold/편집·Undo·전환·Exit. 별도 Chrome·제품 변경 API·고정 응답·내부 상태 주입 0. native AX는 읽었지만 버튼 입력 geometry 오류/캡처 timeout으로 일반창 전체 클릭·Explorer 더블클릭·OS Ctrl+V는 NOT_RUN. 일반 종료 native Alt+F4는 별도 관찰 기록을 따른다.</p><p>실제 screencast는 동일 renderer만 녹화하며 소리·실물 로봇·native desktop 영상이 아니다. 다운로드 원본 파일의 경로가 recorder client에 바뀐 도구 실패, 초기 startup GET abort4·후속 viewport timeout, parallel UI 1FAIL/serial 1085PASS를 모두 보존한다. 추가 보조 pytest 호출은 설치되어 있지 않아 실행 전 실패했고 기존 unittest 경로로 168개를 검증했다. 파일 glob/조회 시점·verify_package 인수·증거 status 정규화 도구 오류는 제품 PASS에 합치지 않는다. 원 실패를 clean 재시험으로 삭제하지 않는다.</p></section>',
        '<section><h2>모든 시도·실행 ID·정확한 결과</h2><p><a href="attempt-index.json">SHA 결속 전체 요약</a> · <a href="evidence-manifest.json">현재 인수 증거</a> · <a href="installation-exact07.json">1612 설치 파일 무결성</a> · <a href="native-attempts.json">native/도구 시도</a></p><table><tr><th>시도</th><th>판정</th><th>단계 및 실패</th></tr>']
    parts.append('<p>추가 실제 App 실패: lineage04c는 Undo 뒤 상태 GET이 3–6초에 중단되고 lease 만료 뒤 미실행 Build가 영구 accepted로 남았다. 원 FAIL과 명시 Acquire를 통한 만료 정리는 구분해 보존했다. GET/startup/shutdown의 불필요한 결합을 제거하고 원 HTTP/lease/TTL 기한을 유지하며 미수령 명령만 종료하도록 수정했다. 실행 중 명령과 실제 shutdown admission은 그대로다. 지연의 단일 원인을 확정했다고 보지는 않는다. <a href="lineage04c-status-build-analysis.json">실행 ID·근거·수정 경계</a>. 새 보조시험 첫 실행의 read_json maximum/잘못된 lease 경로 fixture 오류 1건도 제품 실패와 구분하며, 실제 /lease 200·ID 반환과 다섯 독립 잠금 경합을 다시 검증했다.</p>')
    for a in attempts:
        detail=[dict(name=s['name'],status=s['status'],elapsed_ms=s.get('elapsed_ms'),error=s.get('error')) for s in a.get('steps',[])]
        parts.append('<tr><td><a href="'+escape(a['path'])+'">'+escape(a['path'])+'</a></td><td>'+escape(a.get('qualification',a.get('status','PARTIAL')))+'</td><td><pre>'+escape(json.dumps(dict(project=a.get('project'),operation=a.get('operation_id'),desktop=a.get('desktop'),release=a.get('release_id'),steps=detail,error=a.get('error')),ensure_ascii=False,indent=2))+'</pre></td></tr>')
    parts.append('</table><p>ui-fresh05(3.491s)와 정상 중계 제거05b(58.454s)도 원60초 hold에 실패했다. 별도 같은 App80.291s 무중계 진단은 전체 인수로 합치지 않았다. 06은 브라우저 연결 재사용/8–10ms 응답이 확인됐으나 엔진 관측seq1059가 약2초 멈추어7.169s에 실패했다. 따라서 HTTP 재사용만으로 충분하다고 하지 않는다. 07은 FleetIO 전용 연결 재사용(원2s timeout/실패POST replay0)과 produced sequence/age·교환/skip/error 구분 계측을 추가했다. 모든 원결과/녹화 보존. <a href="ui05-no-interception-diagnostic.json">별도 진단</a> · <a href="ui05b-no-route-failure-analysis.json">원 실패와 한계</a>. 보조HTTP 최초 실행의 ambiguous framing TCP reset은 오류전달 성공이 아니라 close+미실행으로 구분했고, 오래된 Bridge 회귀의 누락 command/receipt fixture 필드를 현재 계약에 맞췄다. 제품 guard 완화0.</p></section><section><h2>실제 화면</h2>')
    for directory in ('ui-fresh-08b','ui-cold-08','lineage-08','lineage-cold-08'):
        selected=[p for p in sorted((OUT/directory).glob('*.png')) if not p.stem.startswith('generation-')]
        for p in selected[-4:]:parts.append('<figure><img loading="lazy" src="'+p.relative_to(OUT).as_posix()+'"><figcaption>'+escape(p.relative_to(OUT).as_posix())+'</figcaption></figure>')
    if (OUT/'cold-history-final.png').is_file():parts.append('<img src="cold-history-final.png"><p>원 실물 작업의 cold 요약·시험 사유·source provenance. 현재 연결 아님.</p>')
    parts.append('</section><section><h2>실제 화면 녹화</h2>')
    for p in sorted(OUT.glob('recording-*/app-screen.mp4')):
        parts.append('<p>'+escape(p.parent.name)+'</p><video controls preload="metadata" src="'+p.relative_to(OUT).as_posix()+'"></video>')
    parts.append('</section><section><h2>정확한 잔여와 다음 실물 세션</h2><ul><li>로봇 전원·같은LAN·충전선 분리·감독 확인 후 현재 App에서 명시 Connect. 원 native stationary trial·Prepare ROS fresh·idle board 전압 연속 갱신을 먼저 재시험해야 한다. 이번 실물 결과 NOT_RUN.</li><li>현재 boot의 안전조건이 실제로 충족된 경우에만 저속 정지 관측→전후진/회전·release→90도→한 세션360+scan→연속수집→Stop·raw export. 실물2대/차체정체·실제10cm외곽제동/독립 world localization/Wi-Fi 단절은 보장하지 않는다.</li><li>사진 품질/CAD/BRep/clean PC 및 이전 일반 제품 잔여는 이번 로봇 소프트웨어 경로 PASS에 합치지 않는다. 정확 SOC는 전압환산 추정이며 실측 용량 아님.</li><li>생성 빌드 자동GC는 아직 설치EXE 미구현. 이번7후보는 각각 약0.7GB 논리크기+설치로 증가했고 기존 rollback/필수재현·원자료는 보존했다. build07 전 C: 약54.7GiB, 뒤 약53.6GiB였으며 사용자 데이터/시스템 파일 삭제0. 논리크기와 실할당량은 구분한다. 후속 정리는 별도 정확 대상 검토를 따른다.</li></ul></section></html>')
    fresh=read(paths['fresh'])
    actual_text=next(s['evidence']['text'] for s in fresh['steps'] if s['name']=='Visible New chat and original robot-containing scene brief')
    disk=__import__('shutil').disk_usage(ROOT)
    zip_path=ROOT/'artifacts/robot-residuals-20261018/build08'/('TwinPulse-Windows-x64-0.1.0-alpha.1-'+release+'.zip')
    receipt=dict(release_id=release,source_sha256=source,input_text=actual_text,
        zip_path=str(zip_path),zip_bytes=zip_path.stat().st_size,zip_sha256=digest(zip_path),
        accounting_baseline_at_utc=before['at_utc'],completed_at_utc=datetime.now(timezone.utc).isoformat(),
        input_utf8_sha256=sha256(actual_text.encode('utf-8')).hexdigest(),
        installed_files=install['files'],free_disk_bytes=disk.free,
        original_physical_operation='55e28197e6ca4f3195d69293f606acc7',
        native_369_frames_sha256='cbd192e6dfabd6b2e44c516eaffccccadb9f0d27729acaa8005da625fd140426',
        physical_actions=0)
    write(OUT/'final-identities.json',receipt)
    extra='<section><h2>최종 동결·회귀 및 진단 경계</h2><pre>'+escape(json.dumps(receipt,ensure_ascii=False,indent=2))+'</pre><p>후보07의 실제 fresh27단계 PASS는08의 최종 인수로 대체하지 않았다. 독립 검토에서 진단 로그의 동기 stdout이 FleetIO를 막을 가능성을 찾아08에서16개 제한 비차단 큐와 전용 daemon 출력으로 분리했다. 동일 report seq의 Kit early return은 produced 시각을 갱신하지 않고, 전송할 report와 생성/시도 시각을 같은 lock에서 캡처한다. 로그 드롭/출력 오류는 제어 권한이나 freshness 성공을 만들지 않는다. 고장 난 stdout에서 호스트 전체 종료가 항상 보장된다는 주장은 하지 않는다. 실제 종료·재시작은 별도 현재 결과를 따른다.</p><p>브라우저 HTTP/1.1 재사용은 요청별 인증/CSRF/Host/Origin/context 초기화·검증된 JSON framing/오류 연결 종료를 유지한다. 엔진 robots 전용 연결은 thread-local 단일 in-flight이며 실패한POST 재전송0·원2초 I/O timeout 유지. 최초 설치08 확인은 설치 프로세스 완료 전에 호출해07을 읽었고 원 영수증 installation-exact08.json은 그대로다. 최종08은 완료 후 installation-exact08-after-install.json 및 source 전후 검증에 결속한다.</p><p>정상 조종 중 Fetch/Playwright route 중계0. 주입 지연은 명시 fault 구간에만 사용한다. native CDP 전송시각과 Node callback 수신시각을 구분한다. 05/05b/06의 다른 실패를 단일 원인으로 단정하거나07 한 번의 PASS로 삭제하지 않았다. 새로운 최종 evidence gate는 원 실물 작업의 cold 요약108/원시2334/worker33/cleanup·과거trial 사유도 필수로 요구하며, 원 실패를 넣은 negative gate가 거부하는지 별도 확인한다.</p></section>'
    html='\n'.join(parts).replace('installation-exact07.json','installation-exact08-after-install.json')
    html=html.replace('이번7후보','이번8후보').replace('build07 전 C: 약54.7GiB, 뒤 약53.6GiB였으며','build08 직전 C: 57,758,806,016B, 설치 후 56,657,862,656B를 관측했으며')
    extra+='<p>최초08은27기능단계PASS지만 viewport GET1건이 native 시작→Node 실패관찰 약82ms 상한에 net::ERR_FAILED여서 전체FAIL이다. 일반 동시작업 단계 안의 두 번째 conversation 지연 route가 발견되어 일반경로에서 제거하고, 기존 한 fault window 안으로 분리했다. 단일 원인 확정이나 원실패 소급PASS가 아니다. 같은 설치 fresh08b28단계 전체를 새 성적으로 판정한다. 이 fresh fault의 draft 보존과 cold08의 보존된 draft 실제Send 검증은 서로 다른 여정이다. <a href="fresh08-viewport-failure-analysis.json">원 실행·시각·구체적인 한계</a>.</p><p>과거 physical 기록의 시작/종료 시각·end reason·단일 events SHA 일부는 원 메타데이터에 없어 not recorded 그대로다. runtime raw SHA·trialID/실패 사유·source33·cleanup 근거를 복원한 것이지 없는 과거 값을 생성한 것이 아니다.</p>'
    html=html.replace('</body>','').replace('</html>',extra+'</html>')
    with (OUT/'report.html').open('x',encoding='utf-8') as f:f.write(html)
    print(json.dumps(dict(gate_status=gate['status'],report=str(OUT/'report.html'),accounting=accounting),ensure_ascii=False))
    return run.returncode
if __name__=='__main__':raise SystemExit(main())
