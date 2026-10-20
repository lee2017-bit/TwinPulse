# SPDX-License-Identifier: Apache-2.0
"""Read immutable actual powered-session evidence; never connects to a robot."""
from pathlib import Path
import hashlib
import html
import json
import os
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-powered-20261019-fix'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def stats(values):
    return dict(n=len(values),mean_s=statistics.mean(values),max_s=max(values)) if values else dict(n=0)
attempts=[]
for number in (1,2,3):
    directory=ROOT/f'outputs/robot-powered-20261019-current{number:02d}'
    session=load(directory/'session.json')
    operation=load(directory/'failure-final-operation.json')
    receipt=load(directory/'native-original/receipt.json')
    source=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local/physical-fleet-operations'/f"{operation['operation_id']}.jsonl"
    if source.exists():
        target=directory/'original-device-operation.jsonl'
        if not target.exists():target.write_bytes(source.read_bytes())
        if sha(source)!=sha(target):raise ValueError('Original physical operation changed')
    trials={};watches=[];rejections=[];cleanups=[];heartbeat=[];source_files=set()
    all_hashes=True
    for segment in receipt['segments']:
        p=directory/'native-original'/segment['path']
        all_hashes=all_hashes and sha(p)==segment['sha256']
        with p.open(encoding='utf-8') as stream:
            for line in stream:
                event=json.loads(line);data=event.get('data',{});t=event.get('robot_monotonic_s')
                if event.get('kind')=='command':
                    trial=data.get('trial')
                    if trial:trials[trial['trial_id']]=trial
                    if data.get('action')=='watch' and data.get('status')=='COMPLETED':watches.append(t)
                    if data.get('status')=='REJECTED':rejections.append(dict(t=t,**data))
                elif event.get('kind')=='cleanup':cleanups.append(dict(t=t,**data))
                elif event.get('kind')=='heartbeat':
                    heartbeat.append(dict(t=t,reason=data.get('reason'),state=data.get('control_state'),
                        generation=data.get('motion_generation'),source_age_s=data.get('telemetry_diagnostic',{}).get('source_age_s')))
                elif event.get('kind')=='raw_source':
                    name=data.get('name') or data.get('path')
                    if isinstance(name,str):source_files.add(name)
    rows=[]
    for trial in trials.values():
        started,ended=trial['started_s'],trial.get('ended_s',trial['started_s'])
        accepted=[v for v in watches if v is not None and started<=v<=ended]
        h=[v for v in heartbeat if v['t'] is not None and started<=v['t']<=ended]
        rows.append(dict(trial_id=trial['trial_id'],case=trial['case'],status=trial['status'],reason=trial.get('reason'),
            started_s=started,ended_s=ended,result=trial.get('result'),persistence=trial.get('persistence'),
            accepted_watch_count=len(accepted),accepted_watch_gap=stats([b-a for a,b in zip(accepted,accepted[1:])]),
            heartbeat_window=h,rejected_watch=[v for v in rejections if v['t'] is not None and started<=v['t']<=ended]))
    video=directory/'app-screen.mp4';times=load(directory/'frame-times.json')
    attempts.append(dict(attempt=number,release=session['identity']['engine']['release_id'],
        launch=session['identity']['engine']['launch_id'],operation=operation['operation_id'],project=operation['project_id'],
        twin_context=operation['manifest']['source_twin_context'],operation_sha256=sha(directory/'failure-final-operation.json'),
        directory=str(directory),video_bytes=video.stat().st_size,video_sha256=sha(video),
        sampled_wall_ms=times['end']-times['began'],frames=len(times['frames']),
        recording=dict(complete=receipt['complete'],error=receipt.get('error'),segments=len(receipt['segments']),
            bytes=receipt['bytes'],all_segment_sha_match=all_hashes,accepted=receipt.get('accepted'),saved=receipt.get('saved')),
        operation_complete=operation['manifest'].get('complete'),cleanup_confirmed=operation['manifest'].get('cleanup_confirmed'),
        trials=rows,cleanups=cleanups,source_files=sorted(source_files)))
report=dict(schema='powered-actual-session-20261019-1.0',status='NOT_READY_FOR_PHYSICAL_TEST',
    physical_outcome='BOOTSTRAP_INCONCLUSIVE_NO_DRIVE_RECEIPT',attempts=attempts,
    blocking=['SUSTAINED_INPUT_DEADLINE_EXPIRED_AFTER_POST_ARM_WATCH','STOP_READBACK_UNCONFIRMED_IN_ATTEMPT_3'],
    not_run=['MANUAL_FOUR_DIRECTIONS','CHAT_MOTION','FULL_TURN_SCAN','OBJECT_DESTINATION','WORLD_ALIGNMENT','FULL_CYCLE_PASS'],
    performed=['INSTALLED_ELECTRON_TEST_UI','PC_PREPARATION','READ_ONLY_ROS_CHECK','AUTHENTICATED_NATIVE_CONNECTION',
        'BATTERY','ZERO_PREPARE','NATIVE_LIDAR','8_SECOND_STATIONARY_COLLECTION','THREE_BOOTSTRAP_ATTEMPTS',
        'STOP_OFF_DISCONNECT','UI_JSON_AND_RAW_EXPORT','RENDERER_RECORDING','NORMAL_APP_EXIT'],
    root_cause=dict(confirmed=['PRE_ARM_QUALIFICATION_LEASE_CONSUMED_BY_ENABLE',
        'FIRST_PATCH_CHANGED_SIMILAR_LEGACY_INCOMING_INSTEAD_OF_FIELD_BRANCH'],
        partial_fix_observed='Attempt 3 rejects old generation and accepts current post-arm watches, but later lease still expires.',
        unknown=['EXACT_NONCE_ISSUE_TO_ACCEPT_AGE_AT_FINAL_EXPIRY','SOLE_CAUSE_OF_STOP_READBACK_FAILURE'],
        constraints='No deadline, speed, clearance or stop-assessment threshold relaxed.'),
    operator=dict(power_off_requested=True,power_off_confirmation='USER_CONFIRMED_STOPPED_BUT_STILL_POWERED',
        current_stop_observation='USER: 로봇이 멈춰 있지만 아직 켜져 있습니다',
        physical_motion_observation='Initial bootstrap movement observation NOT_RECEIVED; no measured body-motion PASS'),
    provenance=dict(entry='Same installed Start-TwinPulse-Test.cmd via exec, not Explorer',
        control='Visible installed BrowserWindow Playwright click/typing, no product mutation API or state injection',
        recording='Sampled actual Electron renderer, not native desktop or robot video',
        scene='Existing original living-room Twin; supplied latest photo was not sent to an LLM or regenerated',
        ui_export='Interactive CDP download PASS. Earlier passive-client native Save dialog result NOT_CONFIRMED; raw results preserved.',
        frozen_log_paths='Generic freezer SIM operation paths ENOENT; actual physical device journal, exported JSON and raw segments separately preserved.'),
    cost=dict(new_llm_http=0,new_llm_usd='0',additional_50_ledger_remaining_usd='46.8551834',basis='Prior campaign ledger, not provider account balance'),
    no_changes=['No robot OS/ROS/driver installation','No timeout increase','No Git commit/push/upload','No cleanup deletion'])
(OUT/'powered-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
esc=html.escape
parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>실물 집중시험 — 실패·미검증 포함</title>',
    '<style>body{max-width:1080px;margin:30px auto;font:16px/1.6 system-ui}table{border-collapse:collapse;width:100%}td,th{padding:9px;border:1px solid #bbb}video,img{max-width:100%}code{word-break:break-all}.warn{background:#fff1df;padding:16px}</style>',
    '<h1>2026-10-19 실제 로봇 집중시험</h1><p class="warn"><b>NOT_READY_FOR_PHYSICAL_TEST.</b> 첫 정지시험 3회가 INCONCLUSIVE. 수동·채팅·360도·목적지 이동은 실행하지 않았으며 전체 완료가 아니다. 세 번째 Stop readback 미확인으로 즉시 Stop/OFF/Disconnect와 현장 전원 차단을 요청했다. 사용자가 현재 로봇은 멈춰 있지만 아직 켜져 있다고 확인했다. 현재 정지 관측을 기계 Stop readback PASS나 제동거리 실측으로 바꾸지 않는다.</p>',
    '<p>실제 설치 Electron Test 창 클릭으로 시행했다. 원래 거실을 재열었으며 새 첨부 사진으로 새 모델을 만들거나 외부 전송하지 않았다. 첫 연결은 현재 Twin이 없어 NO_CURRENT_TWIN, 두 번째·세 번째는 원 scene revision 1ca0b0f1…7fa436b에 결속했다. 이 차이를 소급 수정하지 않는다.</p>',
    '<h2>판정과 원인</h2><p>연결·전압·native 수집·8초 수집 구간과 저장은 확인했다. 주기적인 불완전 회전은 엄격 품질 INCONCLUSIVE로 보존했다. 첫 시험은 활성화 전 입력 기한 소진, 두 번째는 내 수정이 유사한 기존 분기에 잘못 적용된 누락으로 generation 거절, 세 번째는 올바른 post-arm watch 수락 뒤에도 입력 만료와 STOP_READBACK_UNCONFIRMED가 발생했다. 최초 두 결함의 제한적 수정은 있었으나 전체 해결이 아니다. 세 번째의 정확한 nonce 생성→수락 나이와 정지 readback 실패의 단일 원인은 미확정이다. 임계값을 늘리지 않았다.</p>',
    '<p>활성화 후 새 입력·이전 generation 거절·Stop 중단 분기의 보조 회귀는 통과했지만 실물 PASS를 대신하지 않는다. 현재 설치 20261019T113540Z-e56c81f86afd는 알려진 실물 차단이 남는 개발본이다. 이전 PC/SIM 준비 판정을 이번 실물 성공으로 사용하지 않는다.</p>',
    '<p><a href="powered-result.json">모든 trial·watch 간격·원문 SHA·cleanup JSON</a> · <a href="installation02-active.json">현재 설치 1627 파일 일치</a></p>',
    '<table><tr><th>시도 / 설치</th><th>실행 ID / 결과</th><th>원문 보존</th></tr>']
for a in attempts:
    rel='../robot-powered-20261019-current%02d'%a['attempt']
    labels='; '.join(f"{t['case']} {t['status']}: {t.get('result',{}).get('receipt',{}).get('observed',{}).get('reason',t['reason'])}" for t in a['trials'])
    parts.append(f"<tr><td>{a['attempt']}<br>{esc(a['release'])}</td><td><code>{a['operation']}</code><br>{esc(labels)}<br>cleanup {a['cleanup_confirmed']}</td><td>{a['recording']['bytes']:,} bytes / {a['recording']['segments']} segments<br>SHA 일치 {a['recording']['all_segment_sha_match']} / complete {a['recording']['complete']}<br><a href='{rel}/failure-final-operation.json'>실제 UI 반출</a> · <a href='{rel}/native-original/receipt.json'>원문 manifest</a></td></tr>")
parts.append('</table><h2>실제 녹화</h2><p>아래는 실패를 포함한 원본 순서의 렌더러 표본 녹화다. 실물 카메라나 성공 데모가 아니다. 재접속·대기 구간도 유지했다.</p>')
for a in attempts:
    rel='../robot-powered-20261019-current%02d'%a['attempt']
    parts.append(f"<h3>시도 {a['attempt']}</h3><video controls preload='none' src='{rel}/app-screen.mp4'></video><p>{a['sampled_wall_ms']/1000:.3f}s / {a['frames']} 원표본 / {a['video_bytes']:,} bytes<br>SHA256 <code>{a['video_sha256']}</code></p>")
parts += ['<h2>마지막 실제 화면</h2><img src="../robot-powered-20261019-current03/final-physical-failure.png" alt="실물 실패 후 상태와 원문 로그">',
    '<h2>잔여와 종료</h2><p>수동·채팅·회전·물체 목적지·실제 제동 거리/정합은 NOT_RUN. 사용자는 현재 정지·전원 ON을 확인했고 최초 짧은 시험에서의 이동량은 현장 확인되지 않았다. ROS stop readback false와 별도의 base reaped / board idle true를 모두 보존하며 이를 전체 정지 PASS로 바꾸지 않는다. 세 번째 원문은 accepted=saved이고 각 분할 SHA가 일치하지만 원격 cleanup 미확인으로 complete=false다.</p>',
    '<p>추가 LLM 호출 0 / USD0. 이전 추가50 캠페인 장부 잔여 USD46.8551834, 공급자 계정 잔액이 아니다. 새 의존성·ROS·OS·드라이버·Cloud 변경, 삭제, commit/push/영상 업로드는 하지 않았다. 일반 Explorer 시작·전체 native UI·로봇 촬영은 NOT_RUN. 이전 실패·원사진·프로젝트·기존 dirty는 보존했다.</p></html>']
(OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
print(json.dumps(dict(status=report['status'],attempts=[dict(attempt=a['attempt'],operation=a['operation'],
    trials=[dict(case=t['case'],status=t['status']) for t in a['trials']],raw_sha_ok=a['recording']['all_segment_sha_match']) for a in attempts]),ensure_ascii=False))
