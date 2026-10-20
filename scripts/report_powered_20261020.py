# SPDX-License-Identifier: Apache-2.0
"""Read-only, SHA-checked powered-session analysis; writes local report artifacts."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib, html, json, statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-powered-20261020-storage-fix'


def file_identity(path):
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def dist(values):
    if not values:return None
    values=sorted(values)
    return dict(n=len(values),mean_ms=statistics.mean(values)*1000,
        std_ms=statistics.pstdev(values)*1000,p99_ms=values[min(len(values)-1,int(len(values)*.99))]*1000,
        maximum_ms=values[-1]*1000,at_least_200ms=sum(v>=.2 for v in values))


def examine(directory):
    session=json.loads((directory/'session.json').read_text())
    operation=json.loads((directory/'operation.json').read_text())
    receipt=json.loads((directory/'raw/receipt.json').read_text())
    capture=json.loads((directory/'frame-times.json').read_text())
    trials={};commands=[];cleanup=[];verified=[];ages={};pauses=Counter();native={};publications=Counter()
    for segment in receipt['segments']:
        source=directory/'raw'/segment['path']
        with source.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=segment['sha256']:raise ValueError('ORIGINAL_SEGMENT_SHA_CHANGED:'+str(source))
        verified.append(dict(path=str(source),sha256=digest,bytes=source.stat().st_size))
        with source.open('rb') as stream:
            for line in stream:
                event=json.loads(line);data=event.get('data',{});kind=event.get('kind')
                if kind=='heartbeat':
                    field=data.get('field') or {}
                    for trial in field.get('trials',[]):trials[trial['trial_id']]=trial
                    diagnostic=data.get('telemetry_diagnostic') or {}
                    age=diagnostic.get('source_age_s');checked=diagnostic.get('checked_monotonic_s')
                    if type(age) in (int,float) and checked is not None:
                        ages[checked]=(data.get('lidar_state','UNKNOWN'),age)
                    observation=field.get('native_observation')
                    if observation:native[(observation.get('stream_id'),observation.get('frame_sequence'))]=observation
                if kind=='command':
                    trial=data.get('trial')
                    if trial:trials[trial['trial_id']]=trial
                    if data.get('action') in {'drive','task'}:
                        row=dict(robot_s=event.get('robot_monotonic_s'),**data)
                        commands.append(row)
                        if data.get('status')=='PUBLISHED':publications[data.get('direction','UNKNOWN')]+=1
                if kind=='control_pause':pauses[data.get('reason','UNKNOWN')]+=1
                if kind=='cleanup':cleanup.append(data)
    result=dict(directory=str(directory),identity=session['identity'],began=session['began'],
        elapsed_ms=session['elapsed_ms'],operation_id=operation['operation_id'],project_id=operation['project_id'],
        trials=list(trials.values()),commands=commands,publication_counts=dict(publications),pauses=dict(pauses),
        sensor_source_age_by_lidar={mode:dist([age for state,age in ages.values() if state==mode]) for mode in ('ON','STREAMING','OFF')},
        native_unique_status_frames=len(native),native_incomplete_status_frames=sum(not o.get('raw_ring_complete') for o in native.values()),
        cleanup=cleanup,receipt=receipt,verified_sources=verified,ui_errors=session.get('errors',[]),
        renderer_video=str(directory/'app-screen.mp4'),video_identity=file_identity(directory/'app-screen.mp4'),
        renderer_capture=dict(began_epoch_ms=capture['began'],end_epoch_ms=capture['end'],
            frames=len(capture['frames']),first_frame=capture['frames'][0],last_frame=capture['frames'][-1],
            scope='Periodic actual renderer frames with original wall-clock spacing; not native screen or physical robot footage'),
        operation_export_identity=file_identity(directory/'operation.json'),
        source_twin_context=operation['manifest'].get('source_twin_context'),
        worker_sources=operation['manifest'].get('worker_sources'),binding_sha256=operation['manifest'].get('binding_sha256'))
    (directory/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    attempts=[examine(p) for p in sorted((ROOT/'outputs').glob('robot-powered-20261020-current*'))
              if (p/'operation.json').exists() and (p/'raw/receipt.json').exists()]
    result=dict(schema='powered-user-journey-20261020-1.0',at=datetime.now(timezone.utc).isoformat(),attempts=attempts,
        verdict='PARTIAL_ACTUAL_HARDWARE_EVIDENCE_NOT_FULL_ACCEPTANCE',
        method='Root Start-TwinPulse-Test.cmd via exec; same installed Electron BrowserWindow actual clicks/typing; passive renderer capture. Not Explorer double-click/native OS input/robot camera.',
        provider_http=0,provider_usd=0,additional_50_campaign_remaining_usd=46.8551834,
        statistics_scope='Original heartbeat diagnostic check times deduplicated, not independent samples or Wi-Fi RTT. No normal-distribution/safety certification claim.',
        limitations=['Restored original living-room Twin, not fresh photo generation.',
            'No physical/Twin absolute alignment established. No estimated furniture destination is certified.',
            'Unknown native LiDAR bytes remain incomplete. Received raw-byte integrity does not prove all publisher samples were delivered.',
            'Voltage SOC is a configured estimate, not measured battery capacity.',
            'A strict inconclusive stop/collection result remains inconclusive even if later cleanup confirms zero/OFF.',
            'No Git publication, dependency/OS/ROS installation, photo cloud transmission or deletion.'])
    final=attempts[-1] if attempts else None
    result['final_installation']=json.loads((OUT/'installation07-final.json').read_text())
    result['final_shutdown']=json.loads((OUT/'final-cleanup/shutdown.json').read_text())
    result['supplementary_tests']=json.loads((OUT/'supplementary-checks.json').read_text())
    result['package_identity']=file_identity(OUT/'build-07/TwinPulse-Windows-x64-0.1.0-alpha.1-20261019T225937Z-92d0b83d50a7.zip')
    result['clearance_photo']=dict(**file_identity(Path('C:/Users/jaewo/.codex/codex-remote-attachments/01a09495-5d9b-7680-8c59-9ac914c939fb/B397180E-62C4-4C95-9E13-773E7223D6CE/1-사진-1.jpg')),
        purpose='Operator-provided clearance context only; not a fresh generation input and not sent to a provider')
    result['session_timing']=dict(first_began=attempts[0]['began'],last_began=final['began'],
        sum_recorded_session_elapsed_ms=sum(a['elapsed_ms'] for a in attempts),
        last_recorded_end=(datetime.fromisoformat(final['began'].replace('Z','+00:00'))+timedelta(milliseconds=final['elapsed_ms'])).isoformat(),
        scope='Recorded App sessions, not motor-on duration; source clocks remain separate')
    result['final_acceptance']=dict(status='NOT_READY_FOR_CONTINUOUS_PHYSICAL_DRIVING',
        passed=['App connection / measured voltage / correct original living-room context',
            '8-second raw acquisition interval / durable archive with incomplete-ring quality retained',
            'Same first supervised forward-wheel stop observation / final zero-OFF readback',
            'Original source replay-stamp repair: final 36 Twist stamps strictly increasing in integer milliseconds; no stale-replay latch',
            'Final Stop / LiDAR OFF / Disconnect / UI export / normal App shutdown'],
        incomplete=['Final chat 90 degrees interrupted at approximately 0.287 rad by INPUT_DEADLINE_EXPIRED',
            'Final full turn interrupted at approximately 0.616 rad total odom yaw by TASK_ODOM_JUMP; not a 360-degree turn',
            'Final manual four-direction hold/release was not rerun after the last source-stamp fix; earlier build published in all four directions but had interruptions',
            'Absolute Twin/robot alignment and furniture destination navigation not tested'],
        final_operation=final['operation_id'] if final else None,
        odom_gap_original=dict(previous_sample_s=3017.826405435,current_sample_s=3018.033490343,
            dt_s=.207084908,limit_s=.2,yaw_delta_rad=.0426007509231569,
            yaw_delta_limit_rad=.0931882086,planar_delta_m=.000050615794127,
            raw_odom_source_gap_ms=207.091055,raw_odom_callback_receipt_gap_ms=184.102376,
            reason='Sample interval exceeded 200ms by 7.085ms; not a measured physical pose jump',
            source='current07/raw/events-00011.jsonl:1300, control_pause at line 1339'),
        input_renewal_original=dict(last_source_created_s=2958.887241402,original_deadline_s=2959.137241402,
            next_window_issued_s=2959.126655235,next_window_emitted_s=2959.141390726,
            next_watch_pc_queue_ms=0,next_window_emit_after_deadline_ms=4.149324,
            original_guard_explicit_stop_receipt_s=2959.162897489,later_pause_readback_record_s=2959.489185268,
            reason='Next renewal was not accepted before the original 250ms lease; queue/transport/cycle attribution UNKNOWN',
            source='current07/raw/events-00005.jsonl:52,55,71,75,86,146,147'),
        pending=['Resolve finite input/presence renewal latency from original queue and acceptance clocks; no automatic replay of old input.',
            'Separate odometry sample-gap diagnostics from actual geometric jumps and validate a purpose-specific timing policy; do not silently widen physical criteria.',
            'UI finite command remains ACCEPTED after robot rejection in some paths; bind eventual result to request ID.',
            'Independent review also identified unreserved one-shot nonce and HTTP pre-arrival epoch rebinding risks; not proven causes of these final failures and not fixed in this turn.',
            'Reaccept same final installed App manual directions, 90-degree goal, single continuous 360-degree scan, stop and complete export before declaring ready.',
            'Physical sensor/Twin absolute registration, furniture destination and deliberate obstacle-stop/long-duration driving were not accepted in this session.'])
    (OUT/'powered-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda s:html.escape(str(s))
    parts=['<!doctype html><meta charset="utf-8"><title>TwinPulse 실제 로봇 시험 2026-10-20</title>',
        '<style>body{font:16px/1.6 system-ui;margin:32px auto;padding:0 16px;max-width:1200px;color:#172b38}table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{border:1px solid #ccd;padding:8px;text-align:left;overflow-wrap:anywhere}code{overflow-wrap:anywhere}img{max-width:100%;border:1px solid #ccd}video{width:100%;max-height:650px}section{margin:32px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.verdict{background:#fff1d8;border-left:5px solid #b56b00;padding:16px}</style>',
        '<h1>TwinPulse 실제 로봇 집중시험 · 2026-10-20</h1>',
        '<p><strong>부분 실물 증거입니다. 전체 기능·주행·정합 인수 완료가 아닙니다.</strong> 각 실패·재시도는 아래에 독립 보존했습니다.</p>',
        '<h2>최종 판정: 연속 실물 주행 준비 미완료</h2><p class="verdict">최종 App 연결·전압·8초 구간 수집/원문 저장·첫 바퀴 정지 관측·종료/반출은 확인했습니다. 최종 채팅90도는 약0.287rad 뒤 입력만료, 한 바퀴는15회 회전출력 뒤 관측 간격으로 중단됐습니다. 두 부분 회전을 합해360도로 세지 않습니다. 마지막 수정 후 패드4방향 전체 재인수·물체 목적지·실물 world 정합은 미완료입니다.</p>',
        '<p>원 odom 표본 간격은207.085ms로200ms 조건을7.085ms 초과했습니다. yaw/평면 변화량은 각각 기존 속도·거리 한도 안에 있으므로 실제 로봇 위치가 점프했다고 단정할 수 없습니다. 숫자를 늘려 PASS로 바꾸지 않았습니다. 입력 갱신 지연·목적별 odom 간격 판정·최종 결과 UI 결속을 해결하고 같은 전체 여정을 재검증해야 합니다.</p>',
        '<p>채팅 회전은 다음 입력창 발행이 기존250ms lease 마감보다4.149ms 늦었고, 다음 watch는 PC 대기0ms였지만 마감 전에 수락되지 않았습니다. SSH 전달·로봇 큐·각 cycle의 기여는 아직 UNKNOWN입니다. 원 guard의 explicit_stop 수신은2959.162897489이고, 나중 pause/readback 완료2959.489185268을 최초 정지시각으로 쓰지 않습니다. full-turn의 연속 raw odom 원본도 source 간격207.091ms/콜백 수신 간격184.102ms이며 해당 사이 원기록은 없습니다. 생성·전달·콜백 중 단일 원인을 입증한 것은 아닙니다.</p>',
        '<p>현재 추가 이동은 중단했습니다. 마지막 Stop·토크OFF·LiDAR OFF·Disconnect·정상Exit가 확인됐고, 소유10프로세스→0/lock·앱·시험 포트0입니다. 로봇 전원 자체를 껐다고 기록하지 않습니다. <a href="final-cleanup/shutdown.json">종료 원영수증</a></p>',
        '<h2>최종본·입력·시간</h2><p>설치 '+esc(result['final_shutdown']['release_id'])+' / source <code>'+esc(result['final_shutdown']['source_sha256'])+'</code>,1627파일 exact. ZIP <code>'+esc(result['package_identity']['sha256'])+'</code>. 문서/보고서는 제품 패키지 동결 후 갱신했습니다. <a href="installation07-final.json">설치 검증</a> · <a href="powered-result.json">전체 기계 판정·원 SHA</a></p>',
        '<p>기록 세션 '+esc(result['session_timing']['first_began'])+' ~ '+esc(result['session_timing']['last_recorded_end'])+' (UTC; KST=+9시간),7개 시험 세션 경과 합계 '+str(round(result['session_timing']['sum_recorded_session_elapsed_ms']/60000,3))+'분. 연속 모터 가동시간이나 인코딩 영상 길이의 합계가 아닙니다. 영상은 주기적으로 캡처한 실제 렌더러 프레임을 원시각 간격으로 인코딩했으며 OS 전체·실물 카메라 녹화가 아닙니다. 최종407프레임/260.8초 영상의 첫 Home·마지막 Disconnect 화면을 직접 검토했습니다.</p>',
        '<p>현재 첨부 사진은 현장 정리 확인용으로만 사용했고 새 사진 생성·외부전송은 없습니다. 원 bytes SHA <code>'+esc(result['clearance_photo']['sha256'])+'</code>. 복원한 기존 거실의 project/chat/revision/실제 worker SHA는 아래 각 분석에 결속했습니다. 동일 context라도 절대 world 정합은 UNALIGNED입니다.</p>',
        '<h2>수정과 범위</h2><p>저장 500ms를 제어 기한으로 혼용하던 실패를 분리: 500ms buffering / 2초 bounded durable ACK, 완료 전 권한 금지. 센서 제어·오도메트리 QoS 최근5→최신1(신뢰성/내구성 유지), 미수신 표본 보존 주장 금지. 과거 세대 입력은 부작용 전 거절하고 새 준비 세대를 폐기하지 않음. 명령 최대8개/10ms 한정 drain·Stop 우선, 큰 정상 표시 heartbeat 20→10Hz/준비·정리는 기존20Hz·소형 입력20Hz 유지. 최종 후보는 같은 원 입력을 다시 출력하지 않고 새 원 입력을 기다림: 원06 raw guard가 stale_replayed_or_invalid_stamp, 동일 timestamp 재출력의 ms 동일/미세 역전을 실제 확인. C++ 보호·모터입력250ms/출력400ms/센서200ms/물리 기하·제동 기준은 완화하지 않음.</p>',
        '<p>'+esc(result['method'])+'</p>',
        '<p>새 API 호출/비용 0. 추가 USD50 장부잔여 USD46.8551834, 이전 USD20 장부와 별도. 개인 사진 외부전송 0.</p>',
        '<p>보조 로컬 safety167개 PASS(22.656초)는 실물 사용자 여정 개수나 전체 성공 판정이 아닙니다. 최종 같은 입력 stamp 원문36건은 정수ms 기준 비증가0/원 C++ replay 차단 재발0입니다. 초기500ms 저장 hard-fault와 오래된센서·과거세대 폐기·대기열·동일원입력 재출력 문제는 각각 원실패와 수정 후 결과를 분리해 보존했습니다. 시도06 뒤의 첫 build06 후보는 미설치이며 실제 시도로 세지 않습니다.</p>',
        '<h2>실제 시도별 판정</h2><table><tr><th>시도 / 실행 ID</th><th>원 시험과 결과</th><th>실제 출력 / 원문</th></tr>']
    for a in attempts:
        trials='<br>'.join(esc(t['case']+' · '+t['status']+' · '+str(t.get('reason'))+' · '+t['trial_id']) for t in a['trials'])
        parts.append('<tr><td>'+esc(Path(a['directory']).name)+'<br><code>'+esc(a['operation_id'])+'</code></td><td>'+trials+'</td><td>Published '+esc(a['publication_counts'])+'<br>Archive complete='+esc(a['receipt']['complete'])+'<br>'+esc(a['receipt'].get('error'))+'</td></tr>')
    parts.append('</table><p>PASS는 해당 trial의 기록된 제한 범위만 뜻합니다. 전진 바퀴 정지 관측은 회전 제동·차체 미끄러짐·실측 정합·가구 도착의 증명이 아닙니다.</p>')
    for a in attempts:
        rel=Path(a['directory']).relative_to(OUT.parent).as_posix()
        parts+=['<section><h2>'+esc(Path(a['directory']).name)+'</h2><code>'+esc(a['operation_id'])+'</code>',
            '<pre>소스/실행 버전: '+esc(json.dumps(a['identity'],ensure_ascii=False,indent=2))+'</pre>',
            '<p>시작 '+esc(a['began'])+' / 기록 '+str(round(a['elapsed_ms']/1000,3))+'초 · 영상 SHA <code>'+esc(a['video_identity']['sha256'])+'</code></p>',
            '<p>원문 '+str(len(a['verified_sources']))+'분할 SHA 전부 일치 · accepted/saved '+str(a['receipt']['accepted'])+'/'+str(a['receipt']['saved'])+'</p>',
            '<pre>'+esc(json.dumps(a['sensor_source_age_by_lidar'],ensure_ascii=False,indent=2))+'</pre>',
            '<p>상관된 원본 timestamp 나이 진단의 분포이며 네트워크 RTT/독립 표본/보증 한도가 아닙니다.</p>',
            '<video controls preload="metadata" src="../'+rel+'/app-screen.mp4"></video>',
            '<p><a href="../'+rel+'/analysis.json">전체 분석·명령·trial·cleanup·원문 SHA</a> · <a href="../'+rel+'/operation.json">실제 App UI 반출</a></p>']
        for shot in sorted(Path(a['directory']).glob('*.png'))[:3]:parts.append('<img src="../'+rel+'/'+shot.name+'" alt="실제 설치 App 화면">')
        parts.append('</section>')
    parts+=['<h2>정확한 잔여</h2><ul>']+['<li>'+esc(v)+'</li>' for v in result['final_acceptance']['pending']]+['</ul>']
    parts+=['<h2>미검증·보고 한계</h2><ul>']+['<li>'+esc(v)+'</li>' for v in result['limitations']]+['</ul><p>자세한 최종 원 trial과 진행/차단 상태는 powered-result.json을 기준으로 합니다. 원 실패를 새 성공으로 덮어쓰지 않습니다.</p>']
    (OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),attempts=len(attempts),operations=[a['operation_id'] for a in attempts])))


if __name__=='__main__':main()
