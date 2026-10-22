# SPDX-License-Identifier: Apache-2.0
"""Read-only original failure analysis and one local report. No device/network."""
from pathlib import Path
from collections import Counter
from hashlib import sha256
from html import escape
from datetime import datetime, timezone
import json
import os
import shutil
import importlib.util
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-powered-20261020-final01b'
for package in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def identity(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha256(path.read_bytes()).hexdigest())


def main():
    operation=read(OUT/'final-operation.json')
    receipt=read(OUT/'raw-receipt.json')
    phases=[];commands=[];cleanup=[];kinds=Counter();raw_count=0;verifications=[]
    for segment in receipt['segments']:
        path=OUT/('raw-'+segment['path'])
        info=identity(path)
        assert info['sha256']==segment['sha256'] and info['bytes']==segment['bytes']
        verifications.append(info)
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                event=json.loads(line);raw_count+=1
                kind=event.get('kind');kinds[kind or event.get('schema','unknown')]+=1
                data=event.get('data') or {}
                if kind=='heartbeat':
                    phase=data.get('maintenance_phase')
                    if not phases or phases[-1]['phase']!=phase:
                        phases.append(dict(phase=phase,robot_s=event.get('robot_monotonic_s'),sequence=event.get('sequence')))
                if kind=='command' and data.get('action') not in {'watch','input_window'}:
                    commands.append(dict(sequence=event.get('sequence'),robot_s=event.get('robot_monotonic_s'),data=data))
                if kind=='cleanup':cleanup.append(dict(sequence=event.get('sequence'),data=data))
    assert raw_count==receipt['event_count']==receipt['accepted']==receipt['saved']
    motions=[row for row in commands if row['data'].get('action') in {'drive','task','field_trial'}]
    copies=OUT/'original-launch-logs';copies.mkdir(exist_ok=True)
    launch=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches/9ca3aefc87bc4f0ca8943b95fb6e59bc'
    original_logs=[]
    for name in ('backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json','supervisor-status.json','cleanup-receipt.json'):
        path=launch/name
        if path.is_file():
            dest=copies/name
            if not dest.exists():shutil.copy2(path,dest)
            assert identity(path)['sha256']==identity(dest)['sha256']
            original_logs.append(identity(dest))
    active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    from twinpulse_app.physical_live_history import recover_live_history
    actual=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local/physical-live'/operation['operation_id']
    for segment in receipt['segments']:
        assert identity(actual/segment['path'])['sha256']==segment['sha256']
    with (actual/'events-00000.jsonl').open(encoding='utf-8') as stream:first=json.loads(stream.readline())
    context={key:first[key] for key in ('operation_id','project_id','robot_id','connection_epoch','binding_sha256','source_twin_context')}
    recovered=recover_live_history(actual,receipt,**context)
    old_path=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/releases/20261020T121021Z-584facc28b70/_internal/resources/packages/twinpulse_app/src/twinpulse_app/physical_live_history.py'
    spec=importlib.util.spec_from_file_location('history_before_fix',old_path);old_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_module)
    try:old_module.recover_live_history(actual,receipt,**context);old_error='UNEXPECTED_ACCEPT'
    except ValueError as exc:old_error=str(exc)
    original_tail=[e for e in operation['events'] if e.get('schema') in {'physical-live-event-1.0','physical-live-event-2.0'}]
    assert old_error=='WORKER_SOURCES_MEMBER'
    assert recovered['events']==original_tail
    assert recovered['worker_sources']==first['worker_sources'] and recovered['cleanup_confirmed'] is False
    replay=dict(before_source=identity(old_path),before_error=old_error,original_summary_events=len(operation['events']),
        originally_restored_summary_events=7,recovered_runtime_events=len(recovered['events']),
        recovered_summary_events=7+len(recovered['events']),runtime_tail_deep_equal=True,
        worker_sources_exact=len(recovered['worker_sources']),runtime_event_count=recovered['runtime_event_count'],
        cleanup_confirmed=False,field_trial_resolution=recovered['field_trial_resolution'],
        transport_or_device_contact=False,originals_rewritten=False)
    (OUT/'history-replay.json').write_text(json.dumps(replay,ensure_ascii=False,indent=2),encoding='utf-8')
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),verdict='POWERED_PREPARE_FAILED_NO_MOTION',
        failed_installed_release='20261020T081059Z-29c886bf13b1',launch_id='9ca3aefc87bc4f0ca8943b95fb6e59bc',
        operation_id=operation['operation_id'],project_id=operation['project_id'],
        source_twin_context=operation['manifest'].get('source_twin_context'),
        connection_observation=read(OUT/'connection-observation.json'),
        phases=phases,commands=commands,motion_requests=len(motions),cleanup=cleanup,
        raw_count=raw_count,raw_kinds=dict(kinds),receipt=receipt,verified_segments=verifications,
        original_launch_logs=original_logs,active_candidate=active,history_replay=replay,
        independent_review=dict(agent='astra_prepare_cold_review',requested_model='gpt-6-astra',requested_effort='xhigh',
            scope='Read-only original failure/source/replay review; no file/device/UI changes.',
            result='Agrees with source contract/history fixes; exact Pi missing filename and new target success remain unverified.'),
        diagnosis=dict(observed='Prepare rejected FileNotFoundError after CHECKING_OUTPUT_GUARD.',
            source_defect='CMake add_library omitted SHARED while guard_runtime requires libturtlebot3_node_lib.so.',
            boundary='Exact Pi missing filename/build.log was not exported. Do not claim sole hardware root independently proven.',
            missed_test='The previous build runner explicitly manufactured the expected .so fixture and did not exercise CMake output type.'),
        changes=['Explicit SHARED; origin-relative executable build RPATH.','Required artifact existence/hash checked immediately after build; bounded OUTPUT_GUARD_ARTIFACT_MISSING.',
            'Single interactive recorder uses normal Playwright download initialization; passive recorder keeps noDefaults.',
            'Cold-history source validator accepts reviewed C++/CMake/XML/notice members, preserving hashes/bounds/path rejection.'],
        verification=dict(guard_orchestration_tests=4,bootstrap_no_device_tests=3,source_archive_tests=2,
            initial_test_command='One integration invocation missed PYTHONPATH; ImportError preserved in tool output, rerun with package paths passed.',
            actual_ROS_recompile='NOT_RUN',readback='NOT_RUN',lidar='NOT_RUN',driving='NOT_RUN',
            full_new_candidate_SIM='NOT_RUN',native_Explorer='NOT_RUN'),
        budget=dict(new_provider_http=0,new_estimated_usd=0,new_unknown_usd=0,
            additional_50_cumulative='3.5109468',additional_50_remaining='46.4890532',previous_20_separate_total='14.9450973'),
        videos=[identity(ROOT/'outputs/robot-powered-20261020-final01/app-screen.mp4'),identity(OUT/'app-screen.mp4')])
    photo=Path('C:/Users/jaewo/.codex/codex-remote-attachments/01a09495-5d9b-7680-8c59-9ac914c939fb/1DC04F8F-358A-4ACA-91C2-F0EAE0C5AC84/1-사진-1.jpg')
    result['current_clearance_photo']={**identity(photo),
        'purpose':'Visual reference only; operator separately confirmed charging unplugged, supervision and emergency power-off.',
        'used_for_generation':False,'external_model_upload':False} if photo.is_file() else dict(status='ATTACHMENT_PATH_NOT_AVAILABLE')
    result['final_source_files']=[identity(ROOT/name) for name in (
        'packages/twinpulse_robot_safety/guard_base/CMakeLists.txt','packages/twinpulse_robot_safety/guard_runtime.py',
        'packages/twinpulse_app/src/twinpulse_app/physical_live_history.py','scripts/robot_powered_ui_session.mjs')]
    cold=ROOT/'outputs/robot-powered-20261020-final01-cold10/cold-result.json'
    if cold.exists():
        result['verification']['candidate_cold_UI']=read(cold)
        original_first=OUT/'raw-events-00000.jsonl';new_first=cold.parent/'restored-events-00000.jsonl'
        original_receipt=OUT/'raw-receipt.json';new_receipt=cold.parent/'restored-receipt.json'
        assert identity(original_first)['sha256']==identity(new_first)['sha256']
        assert identity(original_receipt)['sha256']==identity(new_receipt)['sha256']
        result['verification']['cold_download_original_bytes_exact']=True
        result['videos'].append(identity(cold.parent/'app-screen.mp4'))
    (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    link=lambda p,label:'<a href="'+p+'">'+escape(label)+'</a>'
    report='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse powered Prepare failure</title>
<style>body{font:16px/1.65 system-ui;max-width:1050px;margin:36px auto;padding:0 20px;color:#172b35}h1{font-size:26px}img,video{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f6;padding:18px}.fail{color:#a12626}</style>
<h1>실제 App 전원 시험 · Prepare 실패 / 주행 미실행</h1>
<p class="fail">이번 전체 사이클은 통과하지 못했습니다. 연결은 성공했지만 무구동 Prepare의 산출물 검사에서 실패했습니다. 수정 후보를 설치한 것과 실제 Pi 수정 성공은 다릅니다.</p>'''
    report+='<p>Operation <code>'+escape(operation['operation_id'])+'</code> · 원 거실 '+escape(operation['project_id'])+'</p>'
    report+='<h2>실제 수행과 경계</h2><p>동일 root Test Start를 실행 도구로 호출 → 같은 설치 Electron Home → Robots 선택·PC 준비·실제 read-only SSH → 원 거실 복원/View → Connect → zero-command Prepare → 실패 후 Stop/Disconnect → operation·원문 반출 → 실제 Exit. 별도 Chrome/변경 API/고정 모델 응답/직접 SSH 우회 없음. 첫 녹화는 passive 다운로드 이벤트 누락으로 보존한 뒤 같은 창/연결에 단일 interactive 관측기로 재연결했으므로 두 영상을 한 연속 녹화로 주장하지 않습니다.</p>'
    report+='<p>관측 11.38V(약49%, 전압 환산), 연결시11.32V. 부팅 torque ON·wheel raw0·command bytes0. 토크를 안전 통과로 쓰지 않았습니다. 새 센서/Arm/Bootstrap/수동·채팅·360도 요청은 0건입니다. 마지막 좌표 정합은 UNALIGNED입니다.</p>'
    report+='<h2>실패 분석 및 수정</h2><p>FileNotFoundError가 Checking 단계 뒤 발생했습니다. 실제 빌드 CMake는 라이브러리 형식을 생략했지만 검사는 .so를 요구했습니다. '+link('https://cmake.org/cmake/help/latest/command/add_library.html','CMake 공식 규칙')+'상 형식을 생략하면 BUILD_SHARED_LIBS에 따라 달라집니다. SHARED를 명시하고 이동 가능한 실행파일 경로를 지정했으며, 잘못된 산출물은 별도 검사보다 먼저 구체적 오류로 거절합니다. 정확한 Pi 누락 파일 경로와 build.log는 기존 export에 없어 미확인입니다. 이 소스 결함이 실제 실패와 일치하지만 단독 원인의 확정과 수정 실물 성공은 새 타깃 검증이 필요합니다.</p>'
    report+='<p>기존 단위 runner는 예상 .so를 직접 만들어 실제 CMake 설정 오류를 놓쳤습니다. 새4개 보조시험은 해당 선언·정적/누락 산출물 거절·SHA/취소·캐시를 확인합니다. 추가 무구동 실제 receiver3/별도 archive2 통과. PC에 CMake/ROS SDK를 새 설치하지 않았고 이 결과를 ROS/ARM64 빌드 성공으로 세지 않습니다.</p>'
    report+='<h2>재열기 오류와 수정</h2><p>첫 후보584에서 실제 UI 이력이107→7로 줄었습니다. read-only 원문 재생으로 옛 history validator의 WORKER_SOURCES_MEMBER를 재현했고,84-member C++/CMake/XML/notice 형식을 허용한 새 reader에서 원 runtime tail100개·source84 모두 원본과 정확히 일치했습니다. incomplete 자체가 거절 원인은 아니었습니다. 형식·경로·SHA 검증과 cleanup=false를 유지합니다. '+link('history-replay.json','원본 before/after 재생 증거')+'. cold09 최초 도구 메타데이터의104 기대값은 잘못된 중간 snapshot 숫자이며 실제 원본107을 기준으로 정정합니다. UI JSON 원본은 수정하지 않았습니다.</p>'
    report+='<h2>기록과 정리</h2><p>원문 '+str(raw_count)+' accepted=saved,13세그먼트 '+str(receipt['bytes'])+' bytes의 전 SHA 일치. complete=false / REMOTE_CLEANUP_UNCONFIRMED는 그대로 남깁니다. source manifest상 base.log·prepare-off.log는 NOT_CREATED이고 ROS stop/독립 idle 확인도 false입니다. 이동이 없었다고 cleanup PASS로 바꾸지 않았습니다. 사용자에게 전원을 꺼 달라고 안내했고 실제 전원 OFF는 답변 전에는 확인하지 않았습니다.</p>'
    report+='<img src="02-prepare-failed-no-motion.png" alt="실제 Prepare 실패 화면">'
    report+='<h2>실제 영상·원문</h2><p>'+link('../robot-powered-20261020-final01/app-screen.mp4','처음 연결·Prepare 진행 녹화')+' · '+link('app-screen.mp4','동일 연결 후속·실패·반출·Exit 녹화')+' · '+link('analysis.json','모든 ID/SHA/단계/검증 원문')+' · '+link('final-operation.json','최종 operation JSON')+' · '+link('raw-receipt.json','원문 receipt')+'</p>'
    report+='<h2>현재 설치 후보와 미검증</h2><pre>'+escape(json.dumps(active,ensure_ascii=False,indent=2))+'</pre><p>현재 후보의 재열기·이력/비자동 연결은 별도 검증으로 기록합니다. 수정 Pi 재컴파일/readback·센서·제동·주행·정합·전체 새 SIM은 NOT_RUN이며 이전 준비 판정을 재사용하지 않습니다. 보호 시간/속도/기하 완화0. 신규 모델 HTTP/USD0, 추가50 누적3.5109468/정확잔여46.4890532(이전20 별도). Git 게시/새 의존성 설치/삭제0.</p>'
    if cold.exists():
        report+='<p>'+link('../robot-powered-20261020-final01-cold10/app-screen.mp4','최종 후보의 실제 cold 복원 녹화')+' · '+link('../robot-powered-20261020-final01-cold10/cold-result.json','107/107 정확 비교')+'</p>'
        report+='<pre>'+escape(json.dumps(read(cold),ensure_ascii=False,indent=2))+'</pre>'
    (OUT/'report.html').write_text(report,encoding='utf-8')
    print(json.dumps(dict(verdict=result['verdict'],operation_id=result['operation_id'],segments=len(verifications),raw_events=raw_count,motion_requests=len(motions),report=str(OUT/'report.html'))))


if __name__=='__main__':main()
