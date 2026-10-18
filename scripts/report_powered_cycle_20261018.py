# SPDX-License-Identifier: Apache-2.0
"""Offline report for the actual installed-App powered attempt. No device I/O."""
import base64
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OP='55e28197e6ca4f3195d69293f606acc7'
A=ROOT/'outputs/robot-powered-ui-20261018-09'
B=ROOT/'outputs/robot-powered-ui-20261018-10'
OUT=ROOT/'outputs/robot-powered-cycle-20261018'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    receipt=read(B/f'physical-{OP}-receipt.json')
    rawdir=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local/physical-live'/OP
    checks=[]
    for name in ['events-00000.jsonl','events-00001.jsonl','receipt.json','ssh-stderr.log']:
        downloaded=B/f'physical-{OP}-{name}'
        checks.append(dict(name=name,bytes=downloaded.stat().st_size,sha256=sha(downloaded),
                           original_sha256=sha(rawdir/name),exact=sha(downloaded)==sha(rawdir/name)))
    assert all(x['exact'] for x in checks)
    verify=runpy.run_path(str(ROOT/'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
    installed=verify(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/releases/20261018T073425Z-f3430f75bde7')
    events=[]
    for segment in receipt['segments']:
        downloaded=B/f'physical-{OP}-{segment["path"]}'
        assert sha(downloaded)==segment['sha256']
        events.extend(json.loads(line) for line in downloaded.read_text(encoding='utf-8').splitlines())
    cleanup=next(e for e in reversed(events) if e.get('kind')=='cleanup' and e['data'].get('subsystem')=='session')['data']
    native=cleanup['native']['manifest']
    trial=cleanup['control']['field']['trials'][0]
    raws=[e for e in events if e.get('kind')=='raw']
    cursor=0;dig=hashlib.sha256()
    for event in raws:
        data=event['data'];block=base64.b64decode(data['base64'],validate=True)
        assert data['offset']==cursor and len(block)==data['length']
        assert hashlib.sha256(block).hexdigest()==data['sha256']
        dig.update(block);cursor+=len(block)
    assert cursor==native['bytes_received']
    assert len(native['segments'])==1 and dig.hexdigest()==native['segments'][0]['raw_sha256']
    start=events[0]
    movement=[e for e in events if e.get('kind')=='command' and
              (e['data'].get('action') in ['drive','task','prepare','arm','qualify'] or e['data'].get('status')=='PUBLISHED')]
    scans=[e for e in events if e.get('kind')=='scan']
    age=[e['robot_monotonic_s']-e['data']['timing']['receipt_end_s'] for e in scans]
    before=[e for e in raws if e['robot_monotonic_s']<=trial['ended_s']]
    sessions={name:read(path/'session.json') for name,path in [('hardware08',A),('export_fix09',B)]}
    test=subprocess.run([sys.executable,'-m','unittest','tests.integration.test_fleet_evidence_http',
        'tests.integration.test_http_rejection_delivery','tests.integration.test_physical_live_session','-v'],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,
        'PYTHONPATH':os.pathsep.join(str(ROOT/'packages'/p/'src') for p in ('twinpulse_app','twinpulse_core','twinpulse_provider'))})
    (OUT/'supplementary-tests.txt').write_text(test.stdout+test.stderr,encoding='utf-8')
    result=dict(overall='PARTIAL_NOT_READY_FOR_MOTION',recorded_at=datetime.now().astimezone().isoformat(),
        battery_policy_correction='Later audit:11.4V was an unjustified reintroduced field margin, not an official cutoff.11.34V is46.7% by OpenCR10.5–12.3V mapping. Past no-motion decision is preserved as an operator/software-policy error; native backlog remains an independent blocker. Existing11.1V source guard and firmware protection are not bypassed.',
        operation_id=OP,trial=trial,source=start,cleanup=cleanup,pc_receipt=receipt,download_checks=checks,
        raw_bytes=cursor,raw_sha256=dig.hexdigest(),raw_chunks=len(raws),scan_events=len(scans),
        maximum_scan_emit_receipt_age_s=max(age,default=None),
        last_raw_before_trial_stop=({k:v for k,v in before[-1].items() if k!='data'}|
            {'data':{k:v for k,v in before[-1]['data'].items() if k!='base64'}}) if before else None,
        forbidden_movement_events=len(movement),kind_counts=dict(Counter(e.get('kind',e.get('schema')) for e in events)),
        sessions=sessions,installed_verification=installed,supplementary_test_exit=test.returncode,cost_usd=0,provider_http=0,
        attempts=['08 actual installed UI: PC preparation/read-only check/Connect/native On/stationary Inconclusive/Off/Disconnect/history',
          '08 UI JSON download PASS; binary downloads returned200 but missing context header: FAIL',
          'Node REPL automation timeout50s/kernel reset and8s download observer timeout: tooling failures retained',
          'New supplementary test setup errors: virtual server and missing stub close; repaired, then25tests PASS',
          '09 source rebuilt/verified desktop reused/offline installed: cold history five actual UI downloads PASS',
          'Report-only QA: default msedge channel path absent; existing Program Files Edge used without install. Both images loaded and videos623.52/113.60s metadata readable; no robot acceptance from report QA'],
        remaining=['Native receipt/decode/publish lag still blocks stationary trial; no deadline relaxation',
          'Prepared ROS freshness/battery presentation defect from earlier operation remains unmodified',
          'Current unprepared idle-board voltage becomes stale during native capture; exact scheduling/ownership cost uninstrumented',
          'Cold operation summary shrinks108→8 journal summaries and omits worker-source/cleanup fields; raw recording is preserved',
          'Physical Prepare/stop bootstrap/pad/chat90/single360/proximity/stall/soak NOT_RUN due11.34<11.4V and sensor blocker',
          'Native desktop clicks/Explorer launch/OS clipboard/independent body motion/world alignment NOT_RUN'])
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def j(value):return html.escape(json.dumps(value,ensure_ascii=False,indent=2))
    text=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 실제 로봇 App 시험</title>
<style>body{{max-width:1100px;margin:32px auto;font:16px/1.6 system-ui;background:#f5f7fa;color:#182b38}}h1,h2{{line-height:1.3}}section{{background:white;padding:24px;margin:18px 0;border-radius:12px}}pre{{white-space:pre-wrap;word-break:break-all;font-size:12px}}img,video{{max-width:100%}}td,th{{padding:10px;border:1px solid #ddd;text-align:left}}table{{border-collapse:collapse}}.fail{{color:#a33920}}</style>
<h1>실제 설치 App 집중시험 · 2026-10-18</h1><p class="fail">전체 PARTIAL / 실물 주행 NOT_READY. 전체 사이클 성공이 아니다.</p>
<section><h2>후속 정정 · 배터리 기준</h2><p>11.4V는공식차단값이아니라9/26에이미폐기했던추가시험여유값이재도입된것이다. OpenCR공개표시식10.5V→0%,12.3V→100%에서실제11.34V는약46.7%다. 당시이값만으로이동을거절한판단은정정하며아래원시험결정과실패기록은보존한다. 별개의native처리지연실패는여전히미해결이다. 기존11.1Vsourceguard와보드보호는20%표시정책으로우회하지않는다.</p></section>
<section><h2>이번 결과</h2><p>일반 root의 명시 Start-TwinPulse-Test.cmd를 실행 도구로 호출하고, 같은 설치 Electron BrowserWindow의 실제 버튼을 Playwright로 조작했다. 별도Chrome·제품변경API·고정응답·내부상태주입0. Explorer/native/OS붙여넣기 NOT_RUN. 과거 native geometry/capture 불가에 따른 대체 경로이며 이번에 native 실패를 재시험한 것은 아니다.</p>
<table><tr><th>여정</th><th>판정</th></tr><tr><td>PC 준비·실제 읽기 SSH 연결 / 원거실 Twin 표시 / 명시 지속 Connect</td><td>PASS · read execution ddd3e851730d4b8eaea5be8913bfa0be / observation7da6f899dfd9eae8d46c7daa</td></tr>
<tr><td>배터리 / 이동</td><td>실제11.34V, 지속 연결11.30–11.32V. 새 이동11.4V 기준 미달. Prepare·arm·bootstrap·pad·채팅회전·단일360 모두NOT_RUN. 바퀴 명령0.</td></tr>
<tr><td>native LiDAR / 정지8초 trial</td><td>수신 PASS / trial INCONCLUSIVE: {html.escape(trial['reason'])}. {(trial['ended_s']-trial['started_s']):.6f}s / {trial['frames']}frame. 숫자를채우기위한재시도0.</td></tr>
<tr><td>원문 보존 / cleanup</td><td>PC2334accepted=2334saved/7,315,477B/complete=true. native{cursor:,}B/{len(raws)}chunks/369frame, CRC오류0. close cleanupconfirmed. 물리 rotor stop 시각검증 UNCONFIRMED.</td></tr>
<tr><td>원문 UI 다운로드</td><td>08 FAIL → binary X-TwinPulse-Context누락 수정 → 새설치09에서 같은원작업5파일 실제다운로드 PASS/4원문 SHA exact. 예전FAIL보존.</td></tr>
<tr><td>cold history</td><td>원문재열기/다운로드PASS·자동연결/권한복원0. 요약108→8,worker sources33→0/cleanup표시누락은복원표현잔여. 데이터유실로단정하지않음.</td></tr></table>
<p>Skill 영향: computer-use의 native 제한을 따르고 설치본의 명시 Test/동일BrowserWindow경로를 사용·차이를기록했다. 실제렌더 녹화는사용자카메라/로봇촬영이아니며오디오없음.</p></section>
<section><h2>실제 화면·녹화</h2><p>09는센서원실패캠페인(설치08),10은수정설치09의cold다운로드만. 하나의fresh전구간성적으로합치지않는다.</p>
<img src="../robot-powered-ui-20261018-09/disconnected-export-failure.png"><video controls preload="metadata" src="../robot-powered-ui-20261018-09/app-screen.mp4"></video>
<img src="../robot-powered-ui-20261018-10/fixed-export.png"><video controls preload="metadata" src="../robot-powered-ui-20261018-10/app-screen.mp4"></video></section>
<section><h2>원인·정확한 잔여</h2><p>이번native실패는Prepare전UNPREPARED상태다. 이전Prepared ROSfresh 실패와구분한다. 저장공간은약67GiB로시작했으며ENOSPC재발0. 센서전체처리의지연이남았다. raw도착/scan방출시각은원문에있지만decode완료/lock대기별계측이없어GIL·딥카피·tracker연산비중을단정하지않는다. native_stream._frame은공통lock안에서beams JSON/SHA를만들고,latest_frame은복수소비자가큰deepcopy를반복한다. 다음은read/decode/publish/lock/ROSspin시간계측과immutableframe/중복계산분리이며안전freshness상한은유지한다.</p><p>UNPREPARED 전압은5초주기의별도read_board관측이다. LiDAR수집중오래된값이표시된것은관찰사실이나ROSfresh통과후갱신결함과동일원인이라고단정하지않는다. 기존Prepared경로의표시결함은별도로남아있다.</p><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in result['remaining'])}</ul>
<p>보조회귀25개 {test.returncode==0 and 'PASS' or 'FAIL'}는다운로드헤더/HTTP/저장계약검사이며실물주행증거가아니다. 새모델0HTTP/USD0·기존장부불변·새의존성/공개/commit/push0. 새build03 1개만추가했고이전3pin/원자료보존·추가삭제0.</p></section>
<section><h2>시간·ID·출처·모든시도</h2><pre>{j({k:result[k] for k in ['sessions','attempts','installed_verification','download_checks','source','trial','raw_bytes','raw_sha256','raw_chunks','maximum_scan_emit_receipt_age_s','last_raw_before_trial_stop']})}</pre>
<p><a href="result.json">전체기계판독결과·cleanup·ID/SHA</a> · <a href="supplementary-tests.txt">보조시험원출력</a></p></section></html>'''
    (OUT/'report.html').write_text(text,encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['overall','operation_id','raw_bytes','raw_sha256','raw_chunks','scan_events','maximum_scan_emit_receipt_age_s','forbidden_movement_events','supplementary_test_exit']},indent=2))
    print(OUT/'report.html')


if __name__=='__main__':
    main()
