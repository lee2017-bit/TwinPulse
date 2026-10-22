# SPDX-License-Identifier: Apache-2.0
"""Local consolidated report from preserved actual UI evidence; no robot calls."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import html
import json
import os

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-powered-20261021-report'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def info(path):return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def esc(value):return html.escape(str(value))
def href(path):return os.path.relpath(path,OUT).replace('\\','/')

def main():
    OUT.mkdir(exist_ok=True)
    captions={
        '01':'Pi 실제 빌드·loader 성공 / base ROS publisher 구성 실패 / 바퀴 0',
        '02c':'수정 ROS base·timing readback 성공 / 정지 수집 자기취소 / 바퀴 0',
        '03':'정지 수집 완료 / 첫 바퀴·정지 확인 / 원 100ms 표본 정책 INCONCLUSIVE',
        '04c':'새 감독 225ms 정지 관측 PASS / 수동 전진 중 신선도 정지 / robot·PC 기록 용량 실패',
        '05':'새 감독 정지 관측 PASS / 네 방향 중 만료·신선도 정지 / 기록·정리 완료 / 전체 NOT_READY',
    }
    attempts=[];files=[]
    for key,caption in captions.items():
        directory=ROOT/('outputs/robot-powered-20261020-guard'+key)
        data=read(directory/'powered-analysis.json')
        operation=read(directory/'prepare-final-operation.json')
        row=dict(attempt=key,caption=caption,launch_id=data['launch_id'],operation_id=data['operation_id'],
            release=data['release'],source_twin_context=data['source_twin_context'],
            raw_count=data['raw_count'],raw_bytes=data['receipt']['bytes'],
            recording_complete=data['receipt']['complete'],recording_error=data['receipt']['error'],
            cleanup_confirmed=operation['manifest']['cleanup_confirmed'],
            field_trials=data.get('field_trials',[]),source_body_missing=data.get('source_body_missing',[]),
            video=data['video'],report=str(directory/'report.html'))
        if key in {'02c','04c'}:row['video_scope']='Final evidence recovery segment only; original full recording timing unavailable after automation runtime reset.'
        else:row['video_scope']='Actual sampled renderer recording of this App journey; not native desktop/robot camera or a fresh generation demo.'
        attempts.append(row)
        for name in ('session.json','prepare-final-operation.json','receipt.json','source-export-manifest.json','powered-analysis.json','app-screen.mp4'):
            files.append(info(directory/name))
        for segment in data['receipt']['segments']:
            path=directory/segment['path'];actual=info(path)
            assert actual['sha256']==segment['sha256'] and actual['bytes']==segment['bytes']
            files.append(actual)
    faults=[];original05=ROOT/'outputs/robot-powered-20261020-guard05'
    receipt=read(original05/'receipt.json')
    for member in receipt['segments']:
        for line in (original05/member['path']).read_bytes().splitlines():
            event=json.loads(line);data=event.get('data',{})
            if event.get('kind')=='control_pause' and data.get('reason') in {'TELEMETRY_STALE','INPUT_DEADLINE_EXPIRED'}:
                faults.append(dict(file=member['path'],sequence=event['sequence'],robot_monotonic_s=event['robot_monotonic_s'],**data))
    installed=read(ROOT/'outputs/robot-field-ready-20261020/installation18.json')
    motion_path=OUT/'sensor-motion-analysis.json'
    motion=read(motion_path) if motion_path.exists() else None
    cold_dir=ROOT/'outputs/robot-powered-20261021-cold18'
    restored=read(cold_dir/'restored-operation.json')
    original=read(original05/'prepare-final-operation.json')
    assert restored['operation_id']==original['operation_id']
    assert restored['manifest']['source_twin_context']==original['manifest']['source_twin_context']
    assert restored['manifest']['stream']==original['manifest']['stream']
    assert restored['manifest']['worker_sources']==original['manifest']['worker_sources']
    cold_session=read(cold_dir/'session.json')
    cold_http=read(cold_dir/'fleet-http-receipts.json')
    assert all(r['action'] not in {'connect','prepare','drive','task','field_arm','field_test','lidar'} for r in cold_http['requests'])
    cold_result=dict(verdict='PASS_SCOPED_HISTORY_ONLY_NO_AUTHORITY',operation_id=restored['operation_id'],
        identity=cold_session['identity'],exact_stream_and_source_reference=True,
        actions=[r['action'] for r in cold_http['requests']],export=info(cold_dir/'restored-operation.json'))
    photo=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvcck71j_6d94b13d/inputs/d1077a172498d187b627c474916c4c32a1c3e46f8ba7b9efe07f72f0edf20a2c/6e812bd1d7a339660ed8c8a77c8af84e03437aa4cbba842a55e19cf05c81ba7f.bin'
    photo_info=info(photo);assert photo_info['sha256']==photo.stem
    final=dict(schema='powered-robot-review-20261021-1.0',generated_utc=datetime.now(timezone.utc).isoformat(),
        verdict='NOT_READY_FOR_FULL_CONTINUOUS_PHYSICAL_CYCLE',attempts=attempts,
        roles=dict(main='Inherited current session setting; actual root model ID independently unavailable.',review_agent_requested='gpt-6-astra / xhigh',additional_review_agents=1),
        current_installed=installed,cold18=cold_result,source_photo=photo_info,final_05_faults=faults,
        saved_sensor_motion=motion,
        current_candidate_scope='First-cycle ready callbacks and original failed input/output stage diagnostics: no-device tests and install only. Physical re-test NOT_RUN.',
        supplemental='152 tests + 55 subtests, no failures; supplementary, not hardware acceptance.',
        video05_qc=dict(original_capture_frames=451,encoded_frames=452,encoded_duration_s=340.600,
            original_first_to_end_s=340.555,first_and_last_original_frames_inspected=True,
            explanation='Last original image is repeated once by concat finalization; no interpolated motion or fabricated old cursor path. Renderer capture only.'),
        not_run=['Completed physical chat90','Completed physical360 scan','Physical object-destination arrival','Measured world alignment','Measured chassis stopping distance','Actual final18 powered retry'],
        budget=dict(new_nebius_http=0,new_usd='0',additional_50_used='3.5109468',additional_50_remaining='46.4890532',previous_20_separate='14.9450973',previous_unknown_included='0.4770432'),
        boundaries=['Same installed Electron explicit Test BrowserWindow; Start invoked by execution tool, not Explorer doubleclick.',
            'Original room reopened; no fresh generation or LLM response used as test fixture.',
            'No product mutation API, SSH command, network interception or internal state injection substituted for user acceptance.',
            'No deletion, commit/push, public video upload, new SDK/ROS/global dependency installation.',
            '05 robot-local Stop/OFF and independent idle cleanup confirmed; user physical power-OFF confirmation not yet supplied.'],
        evidence_files=files)
    write('result.json',final)
    rows=''.join('<tr><td>'+esc(a['attempt'])+'</td><td>'+esc(a['caption'])+'</td><td><code>'+esc(a['operation_id'])+'</code></td><td>'+esc(a['raw_count'])+' / '+esc(a['raw_bytes'])+' B<br>complete='+esc(a['recording_complete'])+'<br>'+esc(a['recording_error'])+'</td><td><a href="'+href(Path(a['report']))+'">원자료 상세</a></td></tr>' for a in attempts)
    screenshots=''
    for name in ('05-current-live-twin.png','05-bootstrap-pass.png','05-final-stop-disconnect.png'):
        path=original05/name
        screenshots+='<figure><img src="'+href(path)+'"><figcaption>'+esc(name)+'</figcaption></figure>'
    movement_html=''
    if motion:
        movement_rows=''
        for window in motion['motion_windows']:
            wheel=window.get('wheel_odometry',{})
            movement_rows+='<tr><td>'+esc(window['direction'])+'</td><td>'+esc(round(wheel.get('signed_forward_mm',0.),3))+' mm</td><td>'+esc(round(wheel.get('yaw_deg',0.),3))+'°</td><td>'+esc(window.get('pause_reason'))+'</td></tr>'
        movement_html='<h2>후속: 실제 센서로 계산한 이동량</h2><p>사용자 지적대로 사람에게 재확인하는 대신 원 센서를 계산했다. 아래는 바퀴 오도메트리 추정이며 독립 차체 실측은 아니다. 전진 약1.1cm/후진 약3mm/좌회전 약2.7°/우회전 뚜렷한 변화 없음으로, 의미 있는 연속주행 완료가 아니다.</p><table><tr><th>입력</th><th>바퀴 전후 변위 추정</th><th>바퀴 yaw 변화 추정</th><th>원 중단 사유</th></tr>'+movement_rows+'</table><p>같은 실제 정지8초 구간의 6쌍을 기존 unseeded ICP로 재생하면 추정 병진 중앙값3.318mm/최대13.431mm였다. 이동 전후 LiDAR 추정도 수mm 수준으로 정지 잡음과 겹친다. 점군 bytes 변화 자체를 몸 이동 성공으로 쓰지 않는다. LiDAR 대응·바퀴 변화·원 명령/출력/정지 시각을 함께 보고, 불일치/작은 이동은 INCONCLUSIVE/미완료로 남긴다. LiDAR alone은2D 평면/잡음/동적물체 한계가 있어 차체 이동의 무조건 증명이 아니다.</p><p><a href="sensor-motion-analysis.json">원 스캔 프레임·SHA·전후 pose·정지 baseline·재생 수치</a></p><p>일상적인 “움직였나요?” 질문은 반복하지 않는다. 사람 관측은 선택 피드백이며, 센서가 입증하지 못한 가지를 사람 답변으로 PASS 처리하지 않는다. 감독 여부·현장 위험 변화·비상 전원 차단 같은 필요한 안전 확인은 별개다. 이번에는 저장 로그 분석만 수행했으며 새 로봇 연결/주행/클라우드 전송은 없다.</p>'
    body='''<!doctype html><meta charset="utf-8"><title>TwinPulse 실제 로봇 시험 종합</title>
<style>body{font:16px system-ui;max-width:1250px;margin:2rem auto;padding:0 1rem;color:#17242c}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd5dc;padding:.65rem;text-align:left;vertical-align:top}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}img,video{max-width:100%}figure{margin:1rem 0}.fail{background:#fff0db;padding:1rem;border-left:5px solid #b75c18}</style>
<h1>TwinPulse 실제 로봇 시험 · 종합 보고</h1>
<p class="fail">전체 판정: NOT_READY. 짧은 전진·출력 차단·정지 관측은 성공했으나, 일반 수동 연속 조작은 실제 원문에서 실패했습니다. 네 방향/채팅/360도 풀사이클 완료로 보고하지 않습니다.</p>
<h2>결과와 정정</h2><p>사용자는 04에서 전진·정지를, 05에서 전후진·짧은 좌회전 후 정지를 목격했습니다. 움직였다는 사실과 연속 기능 성공은 다릅니다. 05 초반 HTTP 오류 0만 보고 전진·후진이 오류 없이 완료됐다고 안내한 것은 잘못이며 원문 판정으로 정정합니다.</p>
<p>05 forward 마지막 출력 입력 나이339.026ms, 다음 nonce 창은 기존350ms deadline보다12.462ms 늦었습니다. left는 UI가88~114ms 간격으로 갱신됐지만 ADMITTED 뒤 약115ms가 더 소모돼 출력 전 만료됐습니다. backward/right는 첫 _tick freshness 검사에서 guard 수신 나이226.722/212.419ms가200ms 기준을 넘었습니다. 생산자 발행과 executor 대기의 단독 원인은 미확정입니다.</p>
<h2>원 실패를 보존한 모든 실제 시도</h2><table><tr><th>시도</th><th>기능·품질·복원 판정</th><th>Operation ID</th><th>PC 원문</th><th>근거</th></tr>'''+rows+'''</table>
<h2>원인별 수정·검증 상태</h2><ul>
<li>실제 Pi base의 intra-process/transient-local 충돌: timing publisher만 intra-process Disable. 실제 새 Pi C++ build·loader·late timing readback과 base 시작 확인.</li>
<li>최초 센서 부재가 Stop/OFF보다 먼저 예외를 내던 문제: 두 서비스 모두 시도하고 원 미확정을 별도 보존.</li>
<li>무구동 수집이 자기 명령을 취소하던 PC intent fence: collection과 motion authority 구분. 03~05 실제8초 collection 완료. 원 불완전 링은 INCONCLUSIVE 유지.</li>
<li>정지 관측은 새225ms engineering 정책 ID/SHA로 분리. 옛100ms 엄격 판정과03 INCONCLUSIVE를 재분류하지 않음. 차체 제동/안전 인증 아님.</li>
<li>수신 진단 원값과 입력 만료 전 deadline을 예외에 결속. 출력 전 메모리상 고정 단계 시간표를 실패 시 보존. 최초 current17 preflight만으로 충분하지 않았고, 최종18은 _tick 첫 검사에도 bounded ready callback 처리를 추가. 실제18 재시험 미실행.</li>
<li>04는 PC뿐 아니라 로봇 journal도256MiB 한도 도달. 약59%가 반복 heartbeat였음. 완료 trial의 active 중복만 제거하고 full trial/receipt/원문은 유지. robot/PC/cold 모두 유한768MiB/256segment로 정렬. 관측900초 예상461MB에 여유를 둔 값이며 중복 전송의 완전 해결·무제한 지속 보장은 아님. 실제768MiB 장시간 시험은 미실행.</li>
<li>04 최종 source manifest의 로봇 측 요약은 남지만, 용량 초과 뒤 PC에서 source body가 저장되지 않아 정확한 본문 누락을 유지. accepted=saved라도 whole complete로 바꾸지 않음.</li>
</ul><h2>실제 화면과 최신 완전 녹화</h2><p>05 같은 설치 앱의 Home→원 저장 거실 재열기→접속·센서·짧은 정지 관측→수동 네 방향 시도→실패→정리·반출 구간입니다. 새 생성 데모·실물 카메라 동영상이 아닙니다. 02/04 도구 runtime reset으로 원 full 영상 타임라인은 미확보이며 종료 증거 구간만 별도로 보존했습니다.</p>
<video controls src="'''+href(original05/'app-screen.mp4')+'''"></video>'''+screenshots+'''
'''+movement_html+'''<h2>현재 설치·소스와 정확한 잔여</h2><pre>'''+esc(json.dumps({k:final[k] for k in ('current_installed','cold18','current_candidate_scope','source_photo','supplemental','not_run','budget','boundaries')},ensure_ascii=False,indent=2))+'''</pre><p><a href="result.json">전체 ID·SHA·원 실패 시각·증거 파일 명세</a></p>
<h2>다음 작업의 기준</h2><p>현재는 ‘로봇만 켜면 전체 완료’ 상태가 아닙니다. 원350ms/200ms 기준을 무작정 늘리지 않고 nonce 공급·명령 admission·ROS callback·기하 검사·기록 enqueue·출력 경계를 같은 원시계로 분리해야 합니다. 새 최종18의 동일 네 방향 원 조건 재시험 후에만 채팅90도·360도·전체 로그 여정을 진행합니다. UI 오류가 없어도 로봇 원 pause·command rejection·최종 complete/cleanup까지 확인해야 PASS입니다.</p>'''
    (OUT/'report.html').write_text(body,encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),verdict=final['verdict'],attempts=len(attempts),raw_events=sum(a['raw_count'] for a in attempts),faults05=len(faults)),ensure_ascii=False))

if __name__=='__main__':main()
