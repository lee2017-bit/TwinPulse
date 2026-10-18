# SPDX-License-Identifier: Apache-2.0
"""Offline report from this session's original App downloads. No device/API calls."""
from datetime import datetime,timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-recovery-powered-20261018'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def pre(v):return '<pre>'+escape(json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
def stats(values):
    if not values:return None
    s=sorted(values)
    return dict(n=len(s),mean_ms=statistics.mean(s)*1000,sd_ms=statistics.pstdev(s)*1000,
        median_ms=statistics.median(s)*1000,p95_ms=s[min(len(s)-1,int(.95*len(s))) ]*1000,
        max_ms=max(s)*1000,at_or_above_200ms=sum(v>=.2 for v in s))

def main():
    scope=read(OUT/'session-scope.json');analysis=read(OUT/'analysis/original-analysis.json')
    receipt=read(OUT/'raw/receipt.json');summary=read(OUT/'operation-summary.json')
    final=read(OUT/'after-cleanup-read-only.json');recording=read(OUT/'recording-01/session.json')
    visual_review=read(OUT/'visual-review.json')
    frame_times=read(OUT/'recording-01/frame-times.json')
    encode=next(e['evidence'] for e in recording['events'] if e['name']=='VIDEO_ENCODE')
    recording_facts=dict(frames=len(frame_times['frames']),
        observation_window_s=(frame_times['end']-frame_times['began'])/1000,
        first_to_last_frame_s=(frame_times['frames'][-1]['at']-frame_times['frames'][0]['at'])/1000,
        session_including_encoding_s=recording['elapsed_ms']/1000,
        encode_returncode=encode['code'],errors=recording.get('errors',[]),
        limitation='Renderer screencast timestamps are not physical robot footage or a claim of gap-free native video.')
    dump(OUT/'recording-receipt.json',recording_facts)
    files=[];callbacks=[];frozen=[];first_fault=None;last_sensor=None;first_resumed_sensor=None
    for row in receipt['segments']:
        p=OUT/'raw'/row['path'];b=p.read_bytes()
        assert len(b)==row['bytes'] and sha256(b).hexdigest()==row['sha256']
        files.append(dict(path='raw/'+p.name,bytes=len(b),sha256=sha256(b).hexdigest()))
        for line in b.splitlines():
            e=json.loads(line);d=e.get('data',{});t=e.get('robot_monotonic_s')
            if e.get('kind')=='heartbeat' and d.get('reason')=='FIELD_EVIDENCE_STALLED':first_fault=first_fault or t
            if e.get('kind')=='raw' and d.get('topic')=='sensor_state':
                timing=d.get('callback_timing',{});age=timing.get('source_age_at_receipt_s')
                if age is not None:callbacks.append(dict(sequence=e['sequence'],t=t,source_age_s=age))
                if first_fault is None:last_sensor=d['receipt_end_s']
                elif first_resumed_sensor is None:first_resumed_sensor=d['receipt_end_s']
            if e.get('kind')=='heartbeat' and first_fault is not None:
                q=d.get('telemetry_diagnostic') or {}
                if q.get('reason')=='CURRENT':frozen.append(dict(t=t,source_age_s=q.get('source_age_s'),
                    sensor_age_s=q.get('sensor_receipt_age_s')))
    frozen=[v for v in frozen if first_resumed_sensor is None or v['t']<first_resumed_sensor]
    before=[v['source_age_s'] for v in callbacks if first_fault is None or v['t']<first_fault]
    after=[v['source_age_s'] for v in callbacks if first_fault is not None and v['t']>=first_fault]
    facts=dict(classification='ORIGINAL_DEDUPLICATED_CALLBACKS_NOT_CONTINUOUS_FRESHNESS_PASS',
        first_archive_fault_s=first_fault,last_pre_fault_sensor_receipt_s=last_sensor,
        first_resumed_sensor_receipt_s=first_resumed_sensor,
        sensor_receipt_gap_s=first_resumed_sensor-last_sensor if first_resumed_sensor and last_sensor else None,
        before_fault=stats(before),after_fault_cleanup=stats(after),frozen_current_heartbeat_count=len(frozen),
        limitation='Do not treat repeated frozen heartbeat diagnostic values as new samples or hide the56s acquisition gap.')
    dump(OUT/'callback-analysis.json',facts)
    trial=analysis['cleanup'][-1]['control']['field']['active_trial']
    verdict=dict(status='FAIL_BEFORE_DRIVING_PARTIAL_SENSOR_AND_RECOVERY_EVIDENCE',release_id=scope['release_id'],
        launch_id=scope['launch_id'],operation_id=summary['operation_id'],trial_id=trial['trial_id'],
        trial_status=trial['status'],trial_reason=trial['reason'],native_frames_in_trial=trial['frames'],
        nonzero_publications=len(analysis['motion_publications']),remote_session_cleanup_confirmed=False,
        original_record_complete=receipt['complete'],pc_accepted=receipt['accepted'],pc_saved=receipt['saved'],
        independent_final_read=dict(observation=final['job_id'],execution=final['execution_id'],record=final['record']),
        candidate_state='SOURCE_ONLY_NOT_FROZEN_NOT_PACKAGED_NOT_INSTALLED_NOT_HARDWARE_ACCEPTED',
        unresolved=['initial storage stall OS phase not measured','asynchronous pending write to trial/receipt persistence binding',
            'corrected-driver candidate SENSOR_TARGET_HARNESS_CHANGED regression','native unknown bytes and movement qualification',
            'manual/chat90/single360/proximity/body-stall/long driving NOT_RUN',
            'displayed bedroom-like Twin does not match current living-room photo; selection vs stale scene UNKNOWN',
            'after Disconnect the UI still labels LiDAR STREAMING alongside stale telemetry; not proof of active streaming'],
        provider_http=0,additional_usd=0,prior_ledgers_changed=False)
    dump(OUT/'verdict.json',verdict)
    dump(OUT/'downloaded-file-manifest.json',files)
    sources={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'packages/twinpulse_robot_safety/fleet_control.py','packages/twinpulse_app/src/twinpulse_app/physical_live_session.py',
        'packages/twinpulse_robot_safety/tests/test_control_recovery.py','packages/twinpulse_robot_safety/tests/test_field_tests.py',
        'tests/integration/test_physical_live_session.py')}
    dump(OUT/'candidate-source-sha.json',sources)
    sections=[('<h1>TwinPulse 실제 로봇 재시험 — 실패와 수정 후보</h1><p>'+escape(datetime.now(timezone.utc).isoformat())+'</p>'),
      '<section class="warn"><h2>판정: 주행 전 FAIL / 실물 준비 NOT_READY</h2><p>현장30cm·충전선분리·감독·전원차단 확인 후 실제 설치 App으로 연결·Prepare·native On·정지수집을 요청했다. 주행 명령은 아직0이며 Bootstrap/수동/채팅90/한세션360을 통과했다고 하지 않는다. 기록 정체 뒤 Stop/Disconnect·독립읽기를 수행했고 이후 로봇접속0. 전원꺼도됨 안내 완료.</p>'+pre(verdict)+'</section>',
      '<section><h2>실제 방법·계보</h2><p>동일 root Start-TwinPulse-Test.cmd를 실행도구로 호출(Explorer 더블클릭 아님)→동일설치 Electron 실제 Robots·PC준비·읽기검사→기존저장Twin·명시Connect→zero-command Prepare→LiDAR On→8초 정지수집 요청→Stop/Disconnect→독립읽기→실제16파일 다운로드→Exit. 별도Chrome/직접제품변경API/고정응답/상태주입0. 최초native FrameArrived timeout→fresh선택AX확인; 전체native/Explorer/OSpaste NOT_RUN. REPL timeout/reset과 초기recorder ENOENT도 있었지만 독립 recorder와원파일은보존했다.</p><p><strong>계획서의 original living-room 명칭은 실제 표시 일치 증거가 아니다.</strong> 최종 원화면 검토에서는 침대가 있는 방이 표시되고 현재 현장 사진은 거실이다. 프로젝트 선택 오류인지 오래된 장면 갱신 문제인지는 미확정이다. 현재 사진 기반 Twin 생성·일치·world정합은 NOT_RUN이며, 같은 ID가 기록되었다는 것만으로 화면 내용 일치를 통과시키지 않는다. Disconnect 뒤 LiDAR STREAMING 문구도 과거 상태와 구분되지 않아 후속 수정 대상이며 실제 수신 지속 증거로 쓰지 않는다.</p>'+pre(visual_review)+pre(scope)+pre(analysis['identity'])+'</section>',
      '<section><h2>확정 원인과 미확정</h2><ol><li>기록writer가 .5초 미완료를 latch한 뒤 _field_tick의 반복예외가 같은try의 _tick을 건너뛰었다. ROS 수신·fresh 갱신이 약56.7초 멈추고 정지trial도12frame/RUNNING에 고정됐다.</li><li>Stop의 trial종결이 같은고장writer에 다시저장하다 예외전파→control종료. 최초OS원인은미계측이며 fsync·rename·스케줄링 중하나라고 단정하지않는다. 동시 journal의1.759초 지연과복구는관측됐다.</li><li>오래된 CURRENT 진단이 heartbeat908개에반복됐다. 아래통계는 원ROS callback header/receipt를 직접집계해동결중복을빼되 실제수신공백을별도로남긴다.</li><li>실제 motor zero/OFF/idle·native포트정리는성공했고session최종ACK도받았지만 field-evidence완료가false였다. PC의 REMOTE_EXIT_WITHOUT_CLEANUP 표시는 ACK부재와부분실패를혼동한것이다. 기존aggregatefalse/원FAIL은유지한다.</li></ol>'+pre(facts)+'<p>원인을 배터리부족이나 사진품질 실패로 해석하지 않는다. 초기11.97V/81.7%, 최종11.84V/74.4%는전압식추정이며실측용량이아니다.</p></section>',
      '<section><h2>후보 코드 수정과 보조시험 — 설치/실물 PASS 아님</h2><p>기록오류와ROS관측을분리하고fault에서motion권한폐기·INCONCLUSIVE종결, Stop저장예외비전파, 최종publisher의fieldwriter재검사, 실패event상태일치, 오래된진단STALE표시, terminalACK수신/부분실패구분, owner의저장실패를최종completeness에반영했다. 시간/기하/속도/전압보호완화0. 비동기append뒤늦은write실패와trial/receipt의영속화결속은아직잔여여서 후보동결/배포하지않는다.</p><p><a href="recovery-regressions-scoped-final-02.log">한정최종보조147시험</a> · <a href="recovery-regressions-final.log">넓은162시험중 candidate1ERROR</a> · <a href="candidate-source-sha.json">소스SHA</a>. 해당driver-target원본과현재scan_clock_test.cpp의SHA불일치는기준완화/덮어쓰기로통과시키지않았다. 최초fixture누락/기존예외전파expectation 2FAIL·존재하지않는test모듈ERROR도원로그보존. 단위시험을실물성적으로합산하지않는다.</p>'+pre(sources)+'</section>',
      '<section><h2>실제 화면과 녹화</h2><video controls preload="none" src="recording-01/app-screen.mp4"></video><p>동일Electron renderer887frame·무음. 관찰창571.762초, 첫→마지막frame567.964초, 인코딩포함세션575.848초를 구분한다. MP4 인코딩code0이지만 앱 종료 뒤 recorder_stop의 Target page/context/browser closed 오류도 원문에 남았다. native desktop/실물카메라영상이나 무공백영상 증거가 아니다. 사용자가촬영한사진은로컬현장참고만사용하고새모델전송0.</p>'+pre(recording_facts)+''.join('<figure><img src="'+p.name+'"><figcaption>'+escape(p.name)+'</figcaption></figure>' for p in OUT.glob('*.png'))+'</section>',
      '<section><h2>원문 반출·정지 증거</h2><p>실제UI16다운로드/14segment의크기·SHA exact, PC29844accepted=saved/57131838B지만전체recordcomplete=false. native1489203B/13395chunks/SHA8ef13f...exact,ROS6016원문·8source재구성. 센서포트복원을실제rotor정지시각증명으로바꾸지않는다.</p>'+pre(files)+'<p><a href="read-only-observation.json">최초읽기</a> · <a href="after-cleanup-read-only.json">독립최종zero/OFF</a> · <a href="operation-summary.json">원작업JSON</a> · <a href="analysis/original-analysis.json">전체원문분석</a> · <a href="analysis/actual-ui-actions.json">실제요청시각/ID</a> · <a href="callback-analysis.json">중복제외callback분석</a> · <a href="session-scope.json">승인/방법/한계</a></p></section>',
      '<section class="warn"><h2>정확한 잔여</h2><p>최초쓰기지연단계계측,늦은write실패의trial/receipt결속,drivercandidate SHA불일치검토,수정후동결·설치/비구동전체회귀,미해석native처리근거,그다음현재부팅정지검증/저속이동·채팅/360·cleanup인수가필요하다. 지금다시전원을요청하지않는다. 현재설치04는이번실패본이고소스후보는미설치다. 사용자프로젝트/사진/장부/원FAIL불변·새의존성/Cloud/공개/Git/삭제0. 모델0HTTP/USD0·기존USD50장부불변. App/ownedIsaac는정상Exit·lock/listener0.</p></section>']
    html='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse powered recovery test</title><style>body{max-width:1100px;margin:24px auto;padding:16px;background:#edf3f5;color:#143c46;font:16px/1.65 system-ui}section{background:white;border:1px solid #ccdbe0;border-radius:10px;padding:20px;margin:20px 0}.warn{background:#fff2df}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}img,video{max-width:100%}a{color:#006b78}</style>'+''.join(sections)+'</html>'
    html=html.replace('heartbeat908개','heartbeat'+str(len(frozen))+'개')
    (OUT/'report.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),verdict=verdict['status'],operation=summary['operation_id'],callback_analysis=facts),ensure_ascii=False))

if __name__=='__main__':main()
