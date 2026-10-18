# SPDX-License-Identifier: Apache-2.0
"""Read-only evidence checks and one generated local report. No App/robot calls."""
import argparse
from decimal import Decimal
from datetime import datetime,timezone
from hashlib import sha256
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from verify_robot_lineage_offline import source_receipt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();root=args.output.resolve()
    def read(name):return json.loads((root/name).read_text(encoding='utf-8-sig'))
    def save(name,value):
        target=root/name
        if target.exists():
            previous=json.loads(target.read_text(encoding='utf-8-sig'))
            if previous==value:return
            if name=='completion-verification.json' and {k:v for k,v in previous.items() if k!='checked_at_utc'}=={k:v for k,v in value.items() if k!='checked_at_utc'}:return
            raise ValueError('Refusing to overwrite different preserved evidence: '+name)
        with (root/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    identity=source_receipt();normal=read('normal-08/result.json');restart=read('normal-restart-08/result.json')
    close=read('normal-08/shutdown.json');close2=read('normal-restart-08/shutdown.json');auth=read('normal-authentication08.json')
    lifecycle=dict(status='PASS' if close['shutdown_clean'] and close2['shutdown_clean'] and auth['restart_authenticated_ready'] else 'FAIL',**identity,
        normal_start_launch_id=normal['launch_id'],shutdown_clean=close['shutdown_clean'],restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_launch_id=restart['launch_id'],restart_debug_listener_count=restart['debug_listener_count'],restart_app_listener_count=restart['app_listener_count'],
        restart_authenticated_ready=auth['restart_authenticated_ready'],restart_ready_wait_ms=restart['ready_wait_ms'],restart_shutdown_clean=close2['shutdown_clean'])
    save('normal-lifecycle.json',lifecycle)
    diagnostic=read('diagnostics-08b/result.json')
    if diagnostic.get('status') not in {'PASS','FAIL'} or diagnostic.get('desktop',{}).get('engine',{}).get('release_id')!=identity['release_id']:
        raise ValueError('Final diagnostic whole journey evidence missing/wrong release')
    roles=dict(fresh='ui-fresh-08/result.json',cold='ui-cold-08b/result.json',lineage='lineage-08b/result.json',lineage_cold='lineage-cold-08b/result.json',
        normal='normal-08/result.json',lifecycle='normal-lifecycle.json',installation='installation-final08.json',supplementary='offline-final08/result.json',budget='budget-final08.json')
    for role in ('fresh','cold','lineage','lineage_cold'):
        value=read(roles[role])
        if value.get('status') not in {'PASS','FAIL'} or value.get('desktop',{}).get('engine',{}).get('release_id')!=identity['release_id']:
            raise ValueError('Current whole journey missing/wrong release: '+role)
    ref=lambda role,name:dict(role=role,path=name,sha256=sha256((root/name).read_bytes()).hexdigest())
    # A later successful rerun does not erase the actual native engine fault.
    # This manifest must refuse a fully ready verdict while its cause is open.
    fault_root=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
    fault_launch='639879094c7148d08a3d3fc8b93c198b'
    copied=[];unavailable=[]
    preserved=root/'native-failure';preserved.mkdir(exist_ok=True)
    for source in [fault_root/'launches'/fault_launch/name for name in ('engine.log','engine-status.json','supervisor-status.json','cleanup-receipt.json')]+[
            fault_root/'diagnostics/11e555b5465e4bf3ac038b7380569226/events.jsonl',
            fault_root/'diagnostics/b4b6602100ce47d188e3bc8f806cfa26/events.jsonl',
            Path('C:/isaacsim/kit/logs/Kit/Isaac-Sim Python/6.0/kit_20261019_024835.log')]:
        if not source.is_file() and source.name=='kit_20261019_024835.log':
            unavailable.append(dict(original_path=str(source),status='ORIGINAL_PATH_CURRENTLY_ABSENT',
                scope='Previously directly inspected and recorded in astra-native-fault-review.json, but not copied before subsequent Isaac starts. No matching copy found within this evidence root. Automatic log rotation is a possibility, not a directly observed deletion cause. Do not claim exact original Kit bytes preserved.'))
            continue
        destination=preserved/((source.parent.name+'-')+source.name if source.name=='events.jsonl' else source.name)
        if destination.exists():
            if sha256(source.read_bytes()).digest()!=sha256(destination.read_bytes()).digest():raise ValueError('Preserved native evidence differs: '+str(destination))
        else:shutil.copyfile(source,destination)
        copied.append(dict(path=destination.relative_to(root).as_posix(),bytes=destination.stat().st_size,sha256=sha256(destination.read_bytes()).hexdigest()))
    save('native-evidence-unavailable.json',unavailable)
    save('native-failure-review.json',dict(status='UNRESOLVED_NATIVE_RUNTIME_FAULT',launch_id=fault_launch,
        monitor_execution_id='11e555b5465e4bf3ac038b7380569226',shutdown_execution_id='b4b6602100ce47d188e3bc8f806cfa26',fault='Windows access violation diagnostic in SimulationApp.update / engine_host main line370',
        root_cause='UNKNOWN: no fault module/address/native stack or synchronous RAM/commit/VRAM trace was found',
        observed='Authenticated ready at17:49:20Z; last Kit17:49:21Z; UI click17:49:22.906Z; monitor fault17:49:25.151Z; owned cleanup17:49:46.062Z',
        platform='Windows10,16GB RAM,RTX2070MaxQ8GB,driver592.82,Isaac6.0.1-rc.7',
        facts=['Engine was idle/applied_revision null; physical native/tracker/motion paths were not entered',
            'Startup log freeRAM6059MB does not establish OOM; later low-RAM samples belong to other runs',
            'Cleanup receipt proves owned children stopped, not a normal native engine exit',
            'diagnostics02 is an independent whole rerun PASS, not proof of a native cause repair',
            'Existing runtime fault full-owned shutdown retained; no automatic retry or robot authority restored'],
        native_termination_qualification='AV diagnostic preceded manager stop request. Manager observed engine_unresponsive, not engine_exited, but polls a python.bat wrapper: actual kit.exe spontaneous death versus handled-exception/hang is UNKNOWN. Three startup lines after AV are buffered earlier Kit17:49:10/17:49:14 UTC log entries, not relative seconds or recovery. No engine-result or child exit code/dump exists. Do not assert unhandled crash, harmless first-chance, or manager-caused AV.',
        dump_checks='No matching Windows Application1000/1001 event, top-level CrashDumps/Temp dump or matching Kit crash file was found in scoped read-only checks. This is not a full-disk assertion.',
        sources=['https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html',
            'https://docs.isaacsim.omniverse.nvidia.com/6.0.0/overview/known_issues.html'],
        documentation_scope='Official6.0 requirements exceed this reviewed local PC; not a confirmed cause for this6.0.1RC access violation. No driver/runtime/system change was made.',evidence=copied,unavailable_originals=unavailable))
    remaining=['ISAAC_NATIVE_ACCESS_VIOLATION_ROOT_UNKNOWN','ISAAC_STARTUP_120S_TIMEOUT_ROOT_UNKNOWN','ORDINARY_DRIVE_REPLY_ABORT_ROOT_UNKNOWN']
    if read(roles['fresh'])['status']!='PASS':remaining.append('CURRENT_FRESH_UI_JOURNEY_FAILED')
    if diagnostic['status']!='PASS':remaining.append('CURRENT_DIAGNOSTIC_UI_JOURNEY_FAILED')
    review=dict(schema='physical-readiness-review-1.1',status='KNOWN_RUNTIME_BLOCKER',unresolved=remaining,
        scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
        not_run=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT'],protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',
        replay=dict(path='observation-replay-final.json',sha256=sha256((root/'observation-replay-final.json').read_bytes()).hexdigest()),
        evidence=[dict(path=n,sha256=sha256((root/n).read_bytes()).hexdigest()) for n in ('astra-review.json','astra-runtime-review.json','astra-liveness-review.json','astra-native-fault-review.json','astra-final-readiness-review.json','native-failure-review.json','startup05-review.json','normal05-late-failure.json','fresh06-failure-review.json','fresh07-failure-review.json','fresh08-failure-review.json','cold08-failure-review.json','cold07b-failure-review.json','diagnostics08-failure-review.json','diagnostics-08b/result.json','diagnostics08b-native-input.json','marker-setup-08b/result.json','viewport-probe08/result.json','viewport-probe08b/result.json','fault-classification-review.json','gate-supplementary-07b.log','observation-replay-final.json','offline-final08/field.log')],
        basis='Original full raw replay and current installed software evidence. Mandatory live bootstrap/guards remain. Unknown bytes and strict-tracker stall uncertainty are not physical PASS.')
    manifest=dict(release_id=identity['release_id'],source_sha256=identity['source_sha256'],physical_readiness_review=review,evidence=[ref(role,name) for role,name in roles.items()])
    save('evidence-manifest.json',manifest)
    gate=Path(__file__).with_name('verify_robot_focus_gate.py')
    run=subprocess.run([sys.executable,str(gate),'--manifest',str(root/'evidence-manifest.json'),'--output',str(root/'gate-result.json')],capture_output=True,text=True)
    actual=read('gate-result.json')
    if run.returncode!=1 or actual['status']!='NOT_READY' or not {'KNOWN_PHYSICAL_BLOCKER:'+item for item in remaining}.issubset(actual['issues']):
        raise ValueError('Unexpected gate result; inspect all original evidence before reporting')
    negative=json.loads(json.dumps(manifest));negative['physical_readiness_review']['unresolved']=['LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST']
    save('gate-negative-stop-manifest.json',negative)
    run=subprocess.run([sys.executable,str(gate),'--manifest',str(root/'gate-negative-stop-manifest.json'),'--output',str(root/'gate-negative-stop-result.json')],capture_output=True,text=True)
    if run.returncode!=1 or 'KNOWN_PHYSICAL_BLOCKER:LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST' not in read('gate-negative-stop-result.json')['issues']:raise ValueError('Broken Stop incorrectly passed gate')
    old=root.parent/'robot-recovery-completion-20261019/ui-cold-01/result.json'
    shutil.copyfile(old,root/'negative-original-cold.json')
    negative=json.loads(json.dumps(manifest));negative['evidence']=[ref(role,'negative-original-cold.json' if role=='cold' else name) for role,name in roles.items()]
    save('gate-negative-original-manifest.json',negative)
    run=subprocess.run([sys.executable,str(gate),'--manifest',str(root/'gate-negative-original-manifest.json'),'--output',str(root/'gate-negative-original-result.json')],capture_output=True,text=True)
    if run.returncode!=1 or not any(i.startswith('RUN_NOT_PASS:cold') for i in read('gate-negative-original-result.json')['issues']):raise ValueError('Original failed cold incorrectly passed gate')
    videos=[]
    for path in sorted(root.glob('recording-*/app-screen.mp4')):
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,text=True,check=True)
        duration=float(json.loads(probe.stdout)['format']['duration']);session=read(path.parent.name+'/session.json')
        frame_data=read(path.parent.name+'/frame-times.json');frames=frame_data['frames']
        observed=(frames[-1]['at']-frames[0]['at'])/1000 if len(frames)>1 else None
        videos.append(dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=sha256(path.read_bytes()).hexdigest(),duration_s=duration,
            session=path.parent.name+'/session.json',frame_times=path.parent.name+'/frame-times.json',frames=len(frames),
            original_first_to_last_s=observed,timing_status='CONSISTENT_WITHIN_1_SECOND' if observed is not None and abs(duration-observed)<=1 else 'TIMING_NOT_QUALIFIED_USE_ORIGINAL_FRAME_CLOCKS',
            method='Same installed Electron renderer screencast, not native desktop/robot camera',errors=session.get('errors',[])))
    save('video-receipts.json',videos)
    clocks=[]
    for video in videos:
        clock_data=read(video['frame_times']);first=clock_data['frames'][0]['at'];end=clock_data['end']
        expected=(end-first)/1000;delta=video['duration_s']-expected
        clocks.append(dict(path=video['path'],expected_first_frame_to_recording_end_s=expected,
            encoded_duration_s=video['duration_s'],difference_s=delta,
            status='CONSISTENT_WITHIN_1_SECOND' if abs(delta)<=1 else 'TIMING_UNQUALIFIED',
            scope='ffconcat holds the final image until recording end. Earlier last-frame-minus-first comparison omitted that explicit final hold; original receipt is preserved. This is not proof of motion or unseen frames.'))
    save('video-clock-review.json',clocks)
    esc=lambda v:html.escape(str(v))
    link=lambda p,title=None:'<a href="'+esc(p)+'">'+esc(title or p)+'</a>'
    table=lambda heads,rows:'<table><tr>'+''.join('<th>'+esc(h)+'</th>' for h in heads)+'</tr>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'
    gate_result=read('gate-result.json');budget=read('budget-final08.json');replay=read('observation-replay-final.json')
    fresh=read(roles['fresh']);cold=read(roles['cold']);diagnostic=read('diagnostics-08b/result.json')
    fresh_passed={row['name'] for row in fresh['steps'] if row['status']=='PASS'}
    preparation_passed={'Robots menu PC preparation and connection entry while hardware stays OFF',
        'Physical setup shown while robot remains off; no Connect or movement',
        'App-only supervised setup saves offline; all eleven trial paths visible without physical activation',
        'In-App measured-profile editor preserves identity and blocks null or mismatched measurements'}.issubset(fresh_passed)
    zip_sha=(root/'build-08/SHA256SUMS.txt').read_text(encoding='utf-8').split()[0]
    builds=[];source_by_release={}
    for build in sorted(root.glob('build-*')):
        package=build/'dist/TwinPulse';manifest_path=package/'windows-release-manifest.json'
        if not manifest_path.is_file():continue
        package_manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        source_manifest=json.loads((package/'_internal/resources/source-manifest.json').read_text(encoding='utf-8-sig'))
        source_hash=sha256(json.dumps(source_manifest,sort_keys=True).encode()).hexdigest()
        build_id=package_manifest.get('build_id',package_manifest.get('release_id'))
        if build_id:source_by_release[build_id]=source_hash
        sums=build/'SHA256SUMS.txt'
        builds.append(dict(folder=build.name,release_id=build_id,source_sha256=source_hash,
            zip_sha256=sums.read_text(encoding='utf-8').split()[0] if sums.is_file() else None,
            scope='Built candidate, not itself installed/user/hardware acceptance; see each original run'))
    save('build-identities.json',builds)
    hold=fresh.get('sustained_hold_observations',[])
    continuous=[r for r in fresh.get('display_samples',[]) if hold and hold[0]['at']-1000<=r['at']<=hold[-1]['at']+1000]
    hold_metrics=dict(hold_observations=len(hold),hold_observed_interval_ms=hold[-1]['at']-hold[0]['at'] if hold else None,
        display_observations=len(continuous),maximum_observed_display_gap_ms=max((b['at']-a['at'] for a,b in zip(continuous,continuous[1:])),default=None),
        scope='Only the continuously sampled 60-second hold; unsampled gaps between other steps are not continuity evidence')
    save('response-display-scope.json',hold_metrics)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 감독 로봇시험 진입 준비</title>',
        '<style>body{font:16px/1.65 system-ui;max-width:1200px;margin:30px auto;padding:0 22px;color:#182c39;background:#f7f9fa}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bdcbd3;padding:8px;overflow-wrap:anywhere;text-align:left}img,video{max-width:100%;background:#122028}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e8eef2;padding:12px}a{color:#005c83}</style>',
        '<h1>로봇 OFF 사전수정·설치 인수</h1><p>'+esc(datetime.now(timezone.utc).isoformat())+'</p>',
        '<h2>결론</h2><p><strong>'+esc(gate_result['status'])+'</strong> — 설치08의 새 생성 여정은14단계 뒤360도 스캔 중 frame982가1014.789ms로 원1초 화면 기준을 벗어나 FAIL했다.60초hold·90도·겹침0의 앞선 통과와 복원/진단의 독립 성적이 이를 전체PASS로 바꾸지 않는다. 원 native 예외/heartbeat loss,120초 시작 실패,정상 drive 응답 취소도 원인 해소 근거가 부족하다. native 프로세스가 스스로 죽었는지/예외 후 멈췄는지는 wrapper 감시만으로 확정하지 못한다. 실물 Pi·제동·주행·정합은 로봇을 켠 뒤 측정할 결과이며, 그 결과가 미리 PASS여야 시험을 시작할 수 있다는 순환 조건은 제거했다. 실제 관측된 PC/Isaac/응답 실패는 실물 NOT_RUN으로 이관하지 않는다.</p>',
        '<pre>'+esc(json.dumps(identity,indent=2))+'</pre><p>설치'+esc(read(roles['installation'])['file_count'])+'파일 exact · ZIP SHA '+esc(zip_sha)+' · 새 의존성/삭제/Cloud/Git/공개/로봇접속·센서·모터 0.</p>',
        '<h2>이번에 고친 실제 차단</h2><ol>',
        '<li>미해석 ring 전체 거절과 이동 관측을 분리했다. 201개 UNKNOWN은 모두 내부 gap이며 trailing이라고 해석하지 않는다. 마지막 strict complete frame을 같은 stream의 원 수신350ms 안에서만 사용한다. 최신 불완전 ring은 free-space 근거가 아니라 근접/관측부족의 stop-only veto다. 부팅 부분ring·CRC·malformed-header·fallback·stream교체·Stop/fault는 캐시로 우회하지 않는다.</li>',
        '<li>no-return 하나로 전체 후진/회전을 거절하던 조건을 유효 양수 반사점만의 방향 coverage로 교정했다. 0을 free로 보간하지 않는다. 원5도 최대 gap과10cm를 유지하되, gap 중간점만 보던 결함도 실제 방향구간 교집합으로 수정했다. 이는 숫자 상한 확대가 아닌 <strong>감독용 관측 정책의 명시적 변경</strong>이며 센서 인증이나 물리 안전 보증이 아니다.</li>',
        '<li>8초 수집창 종료, strict ring 품질, 원문 저장 최종manifest/ACK, 이동 권한을 분리했다. 품질 경고는 누적해 수집할 수 있으나 writer/저장 fault는 즉시 INCONCLUSIVE/권한폐기다. 안내서의 “오류가 있어도 끝까지 수집”은 정상 기록 경로가 살아 있는 동안의 ring 품질 경고에만 해당한다.</li>',
        '<li>Pi부하·저장·제동·주행 NOT_RUN을 그 시험을 시작하기 위한 순환조건에서 분리했다. 기존 v545의 writer/ROS격리·durable ACK·Stop/입력만료·compact dock·마지막화면보존을 재사용하고 실제 현재 설치여정을 다시 검사했다.</li><li>일반 native Close가 오래된 unavailable 힌트만 보고 서버 요청 없이 거절하던 문제를 실제 재현했다. native Close만 기존 권한 검사의 동일 POST를 한 번 제출하도록 고쳤다. 실제 작업/장치 admission·배출·재검사·fsync·ACK·중복 방지는 유지했다. 원 normal-restart01 첫 종료 FAIL과 두 번째 시도 recovery PASS를 분리 보존했다. Unit48에서 최초 retained-message 중복 selector1FAIL을 교정했고 이를 실제 사용자 인수 대신 쓰지 않았다.</li></ol>',
        '<h2>추가로 재현한 엔진 상태 오판</h2><p>build02 lineage02 launch5f9d4906563042fa87f310711a6bc8e1은 새SIM Connect 중 FAIL했다. manager가 첫 stale 파일을 읽고18:32:52.138Z에 종료를 결정했고 FleetIO는562ms 뒤 회복했다. 두 FleetIO 로그 사이109ms와 마지막 report attempt age3.657s는 별개이며 Wi-Fi RTT로 해석하지 않는다. heartbeat TTL3초는 그대로 두고, <strong>현재 실물 소유/정리 불확실성이 없다고 로컬에서 확인된 idle/SIM만</strong> 서로 다른 두 stale 발행과 최소1초 dwell로 종료를 재확인한다. 발행이 멈추면 최대3초에서 종료한다. 확인 중 새 pooled/legacy Connect와 이동은 shared start-lock에서 차단하고 이전 제어 lease/queued/inflight는 폐기한다. 실제 실물 소유·현실행 cleanup 미확인·readiness UNKNOWN/기록불가·lock 경합은 기존 즉시 종료다. 63개 scoped 음성/회복시험과 Astra 읽기 재검토를 거쳤으며 이것이 실물 Wi-Fi 연속성이나 native 접근위반을 고쳤다는 뜻은 아니다. '+link('astra-liveness-review.json','별도 원 실패·설계·검토 범위')+'</p>',
        '<p>이전 build05 첫 시작 launch d53952fa0426402da87164e3570cf16a는 Kit 자체 startup111.014초 뒤 인증 ready가 전체 제한 안에 들어오지 못해 FAIL했다. 당시 가용 RAM984792KiB, 후속 다른 시각 commit51.51/58.75GB·nonpaged3.19GB를 확인했으나 원 AV 원인/OOM을 확정하지 않는다. timeout을 늘리지 않고 정상 AltF4 종료 후 별도05b 전체 시험했다. '+link('startup05-review.json','첫 기동 실패·자원 시각 구분')+'</p>',
        '<h2>사용자 여정 / 정확한 판정</h2>'+table(['축','판정','근거'],[
            ['설치 App·Isaac SIM','PASS_SCOPED' if fresh['status']=='PASS' and cold['status']=='PASS' else 'PARTIAL / FAIL',f'fresh {fresh["status"]} {len(fresh["steps"])}단계 / cold {cold["status"]} {len(cold["steps"])}단계. 실제 모델 새 생성·2SIM·60초hold·4방향·키·90°/360scan·Stop·장애물/후진·반출. 세부 원결과가 우선이며 실패를 하위 통과 수로 덮지 않는다.'],
            ['저장/복원/로그','PASS_SCOPED' if all(read(roles[n])['status']=='PASS' for n in ('lineage','lineage_cold')) else 'PARTIAL / FAIL','장면 검토폼 편집·Save/Build·Undo 새revision·전환·cold원문SHA·권한복원0. 자연어 장면변경/사진품질 전체 인수와 다름.'],
            ['연결 준비 UI','PASS_SCOPED' if preparation_passed else 'PARTIAL / FAIL','실제 Robots PC 준비·연결진입·오프라인설정·11case·시험순서 제목 실제 화면노출을 각 원 단계에서 판정. 로봇이 꺼져 있어 Connect/모터 실행은0.'],
            ['음성 녹음','없음','녹화는 무음이다. 원 native 파일과 현재 사용자 사진은 새 외부 전송하지 않았다.'],
            ['원자료 재생','PASS_SUPPLEMENTARY',f'원8,336,993B/51,791chunk/6,081ring/불완전202/UNKNOWN2259B 보존. 201개 last-strict 원나이 평균{replay["held_age_mean_ms"]:.3f}/최대{replay["held_age_max_ms"]:.3f}ms. 첫부분1개 거절.'],
            ['실물 Pi·제동·주행·정합','NOT_RUN','로봇 OFF. 4방향6080/6081은 fresh wheel fixture/매frame 새guard의 native 관측검사이며 연속 ROS/encoder/Pi 부하 재생이 아니다.'],
            ['strict 보호주행·stall','미인증/제한','strict complete·ICP는 그대로다. stall은 strict tracker 불확실성에서 INCONCLUSIVE 정지할 수 있다. 이 가지의 성공은 약속하지 않는다.'],
            ['native/Explorer/OS붙여넣기','범위 분리','동일 Start를 실행도구로 실행, 실제 Test BrowserWindow 조작. 일반 native 정상종료는 별도 영수증. Explorer더블클릭/OSpaste/실제DPI·일반 전체native 조작은NOT_RUN.'],
            ['로봇 표시 판정의 범위','한정','console/canvas 교집합과 현재 decode frame은 실측 DOM이다. screen_bounds_uv는 엔진 pose의 투영점 주변 추정 envelope이며 USD 전체mesh의 실제 분할·가림 측정치가 아니다. 아래 실제 회전 스크린샷을 함께 검토했고 화면 안의 이름/센서/연결 표시는 측정 위치정합을 뜻하지 않는다.']]),
        '<p>'+link('gate-result.json','현재9역할 해시결속 gate')+' · '+link('gate-negative-stop-result.json','Stop 고장 negative 거절')+' · '+link('gate-negative-original-result.json','보존 원cold FAIL 거절')+' · '+link('astra-review.json','독립 검토와 반영')+'</p>',
        '<h2>남은 확정 장애와 불확실성</h2><p>diagnostics01 launch639879094c7148d08a3d3fc8b93c198b, execution11e555b5465e4bf3ac038b7380569226에서 실제 access violation이 main-thread APP.update 내부에 기록됐다. 프로젝트 전환이 원인이라는 근거도, OOM/드라이버가 원인이라는 근거도 없다. 후속 diagnostics02 전체6단계와 일반 Start/재시작이 PASS여도 이 결함의 근본 해결로 합산하지 않는다. 기존 전체 owned 종료 경계는 유지했다. backend만 계속 살려 진단을 표시하는 변경은 자동 physical watch/채팅 예외 경로에 영향이 있어 이번에 추가하지 않았다. '+link('native-failure-review.json','실패 원본·SHA·시간·현재 판정')+'</p><p>공식6.0 문서는 RAM32GB/VRAM16GB와Windows11을 최소로 제시한다. 현재PC의16GB/8GB/Windows10은 그 기준보다 낮다. 다만 설치본은6.0.1RC이고 특정 access violation의 원인으로 확정할 수는 없다. '+link('https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html','NVIDIA 공식 요구사항')+' · '+link('https://docs.isaacsim.omniverse.nvidia.com/6.0.0/overview/known_issues.html','공식 알려진 문제')+'. 일반 조건의 반복 실패가 재현되면 main-update/native fault 기록을 더 확보해야 하며, 새 드라이버/Isaac 설치·시스템 변경은 하지 않았다.</p>',
        '<h2>모든 이번 App 시도</h2>']
    attempts=[];identities=[]
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/'result.json').is_file():continue
        value=read(folder.name+'/result.json');desktop=value.get('desktop',value.get('identity',{})).get('engine',{})
        attempts.append([link(folder.name+'/result.json',folder.name),esc(value.get('status')),esc(len(value.get('steps',[]))),esc(desktop.get('launch_id',value.get('launch_id',''))),esc(value.get('error',''))])
        elapsed=sum(step.get('elapsed_ms',0) for step in value.get('steps',[]))
        attempts[-1].insert(3,esc(f'{elapsed/1000:.3f}s (step sum)' if value.get('steps') else f'{value.get("ready_wait_ms", "unknown")}ms (startup)'))
        operations={}
        for sample in value.get('samples',[]):
            for robot in sample.get('robots',[]):
                if robot.get('operation_id'):operations[robot['operation_id']]=dict(robot_id=robot['robot_id'],source_twin_context=robot.get('source_twin_context'))
        files=[]
        for operation_path in sorted(folder.glob('*operation.json')):
            try:
                original=operation_path.read_bytes();operation=json.loads(original)
                if operation.get('operation_id'):
                    operations[operation['operation_id']]=dict(robot_id=operation.get('robot_id'),project_id=operation.get('project_id'),source_twin_context=operation.get('source_twin_context',operation.get('manifest',{}).get('source_twin_context')),
                        event_count=len(operation.get('events',[])),file=operation_path.relative_to(root).as_posix())
                    files.append(dict(path=operation_path.relative_to(root).as_posix(),bytes=len(original),sha256=sha256(original).hexdigest()))
            except (OSError,ValueError):raise ValueError('Invalid preserved operation evidence: '+str(operation_path))
        release=desktop.get('release_id',value.get('release_id'))
        identities.append(dict(run=folder.name,release_id=release,source_sha256=source_by_release.get(release,value.get('source_sha256')),launch_id=desktop.get('launch_id',value.get('launch_id')),project=value.get('project'),conversation=value.get('conversation'),input_sha256=value.get('input_sha256'),operations=operations,files=files))
    save('identity-index.json',identities);parts.append(table(['시도','판정','단계','관측 시간 범위','실행 ID','실패'],attempts))
    parts.append('<h3>생성한 빌드의 불변 식별자</h3>'+table(['후보','release','source SHA','ZIP SHA'],[[esc(v['folder']),esc(v['release_id']),esc(v['source_sha256']),esc(v['zip_sha256'])] for v in builds])+'<p>03은 설치하지 않은 후보다. 빌드 성공은 사용자 인수가 아니다. 일부 범위가 통과했던 구버전과 현재08의 성적은 합산하지 않는다.</p>')
    parts.append('<p>원 실패는 모두 보존했다. build01 cold01은 긴 안내 영역 가운데로 스크롤한 시험기 문제였고, 제목으로 스크롤한 뒤 cold02 전체를 새로 수행했다. diagnostics01은 실제 native 예외/heartbeat loss이며 normal-restart01은 Close 요청 미전송 결함이다. build02 lineage02는 첫 stale 표본으로 종료한 실제 오판이다. build03은 미설치 후보이고, 현재 불확실 소유권/Connect 경합을 보완한 build04는 fresh31/cold13/lineage8/history4를 각각 통과했다. build04 cold의 영상 code0 뒤 PowerShell ExitCode=null 오판과 diagnostics04의 fault GET 도착 전 검사 경합은 시험기 결함이다. build05는 unchanged flag의 불필요한 잠금 대기를 제거했지만 첫 시작120초 FAIL, fresh05b aggregate FAIL, normal05의 뒤늦은 종료가 발견됐다. 최종 gate는08의 독립 전체 여정·설치·보조·장부·ZIP만 사용하고 이전 FAIL을 지우지 않는다. 읽기보조 decode/glob/import/없는 파일·스크립트/생기기 전 결과 읽기 오류와 최종화 패치 문자열 매치 실패는 제품 장애와 별개이며 원 도구 출력에 남긴다. 일반 Start는 실행 도구 호출이지 Explorer 더블클릭이 아니다.</p>')
    parts.append('<h2>최종08 추가 수정·인수 계약</h2><p>최종 설치와 gate의 모든 역할은08에만 결속한다.05b/06의31개 하위 단계가 통과했더라도 aggregate FAIL은 유지한다.100ms 명시 fault의 응답 본문 없는409와 ERR_ABORTED는 원인UNKNOWN이며, 뒤의 정확한 Stop/새 applied epoch·400ms 이상 pose불변·증가telemetry가 갖춰질 때만 한정 회복으로 분류한다. 평상시/미분류 오류는 계속FAIL이다. Fresh는 일반26단계를 중계 없이 먼저 끝낸 뒤 마지막 단일 fault구간으로 들어간다. delay handler만 해제하고 interception은 Exit까지 유지하므로 Fetch해제 직후의 일반조종 회복을 증명한 시험은 아니다. Cold도 일반 후진/우회전을 fault보다 먼저 한다. gate는 양쪽 순서와 실제 Stop 새 applied epoch·동일 scene/stage의 전진하는 decoded frame을 검사한다.20개 gate 보조 음성시험은 사용자 인수와 별개다. '+link('fault-classification-review.json','사전 명시 계약·음성 검사·독립 검토')+'</p>')
    parts.append('<p>07b fresh32단계는 전체PASS였으나 cold의 첫 대화GET3초 만료 뒤 영구적으로 조회가 멈추는 실제UI결함을 발견했다.08은 draftRestored를 읽기 재시도의 선행조건에서 제거하고, 인증 완료·단일inflight·750ms주기·원3초기한·context/epoch/sequence fence를 유지한다. 본문 project/context 거절도 connected/workflow-fresh를 열지 않는다.135개 Chat 보조 회귀PASS는 별도이며, 실제 설치의 첫조회 지연/복구는 diagnostics08에 별도로 기록한다. 최초GET 지연의 OS 원인 자체를 해결했다고 하지는 않는다. '+link('cold07b-failure-review.json','원 실패·확정 회복불능 원인·Astra 검토·녹화부하 변경 범위')+'</p>')
    parts.append('<p>현재08 fresh의1초 화면 초과도 원FAIL로 보존했다. 해당 표본은 HTTP/요청/브라우저 오류0,canvas/console교차0,이름표/투영영역교차0이며 Stop·pad·badge가 보였다. live표시는100ms주기 재계산이고 카메라 handler는클릭당실제Date.now로원1초를다시검사한다. 따라서1014.789ms의live표시를stale카메라실행증거로확대하지않는다. 별도 UI Stop all/Exit는정리영수증이지이어하기PASS가아니다. cold의오프라인설정입력은명시한원07b파일이며08fresh가실행하지않은설정단계를가짜로채우지않았다. '+link('fresh08-failure-review.json','현재08 화면 실패·원 시각·정리·독립 후속 범위')+'</p>')
    parts.append('<p>cold08의marker 없음은fresh가그단계전에실패한시험선행조건누락이었다. 실제UI의별도marker저장후cold08b 전체를새로수행했으며원cold08을PASS로바꾸지않았다. 진단08은reload뒤정상Home의caption을잘못검사해FAIL했고,08b는실제Open saved chat버튼을거쳐전체7단계를새Start에서수행했다. '+link('cold08-failure-review.json','선행조건과제품유실의구분')+' · '+link('diagnostics08-failure-review.json','Home시험기오류와재시험')+'</p>')
    probe=read('viewport-probe08b/result.json')
    parts.append('<p>추가표시진단은기존저장장면·이미등록2SIM을명시재연결해원한세션360도명령을3회실행했다. '+esc(json.dumps(probe.get('turns',[]),ensure_ascii=False))+' 이는별도진단이며새생성/실물PASS가아니다. 첫probe08의누락된Reopen단계FAIL과같은창의08b 진단은원영상에함께남겼다. 메타데이터/current JPEG/decoded DOM기록은분리했으나이번에는초과가재현되지않아원인해결로닫지않는다. '+link('viewport-probe08b/result.json','별도frame진단원문')+'</p>')
    parts.append('<p>06 키 해제의 정상 drive 취소는 일반 오류로 보존했다. 원 HTTP200 뒤에도 이전 applied epoch가 남고 yaw가0.028202rad 변한 뒤 약883ms에 새 epoch를 관찰했다. 이는 실제 제동 실측이 아니다.07은 키를 놓은 뒤 새 applied epoch부터700ms간 움직임 없음/telemetry 증가를 추가로 검사하며, 정상 abort 예외는 추가하지 않았다. 라벨은 모든 로봇의 투영 영역을 피한다. DOM의 라벨/투영 영역 교집합0과 실제 화면을 새로 확인하되, 투영 영역은 정확 mesh분할/가구 가림 판정이 아니다. '+link('fresh06-failure-review.json','원06 실패·시각·화면 제한')+'</p>')
    parts.append('<p>normal05의 시작한정PASS는 나중에 감시기 상태읽기실패로 무효화됐다.06은 engine상태파일에만 read/stat 경합을 없애고 읽기·파싱 오류 때 즉시최대3회 재읽는다. 성공한stale·빈dict·badmarker를 healthy로 바꾸려고 반복하지 않으며 cache·원시각 변경·sleep·TTL완화가 없다. OS read 자체의벽시계최대시간을3회가보장하는것은아니다. 실패종류/errno/winerror/valuekind를 새로그에 기록하고 scoped68보조 및06 일반시작·재시작/현재전체여정을별도로수행했다. '+link('normal05-late-failure.json','원실패와06보강의정확경계')+'</p>')
    parts.append('<p>주작업자 요청설정Sol6.1 xhigh 및 읽기검토Astra xhigh는runtime모델ID를독립조회하지못했다. 검토자가실물/설치인수를대신하지않았고제품파일은주작업자가순차수정했다. 현재화면·음성없는녹화·원실패·소스/입력/명령ID를아래에함께보존했다. '+link('astra-final-readiness-review.json','최종 독립 검토: 추가 확정 코드 원인과 과거 원인 증거 부족의 구분')+'</p>')
    parts.append('<h2>실제 화면</h2>')
    parts.append('<p>증거 보존 누락: 원Kit024835 경로 로그1개는 최종복사시점에 없어 exact bytes/SHA를 보존하지 못했다. 원엔진로그·상태·launcher monitor/shutdown·cleanup6파일은 원본과SHA를대조해보호했다. 과거Kit직접열람결과가있는review기록을 원문파일로 위장하지 않는다. 앱이실행될때자동로그정리가원인인지직접확인하지못했으며제가삭제한파일은없다. 다음실패는추가시작전에관련Kit원문을즉시동결해야한다. '+link('native-evidence-unavailable.json','없어진원경로와보존범위')+'</p>')
    for name in ['ui-fresh-08/turn-scan-running.png','viewport-probe08b/probe-finished.png','ui-cold-08b/power-on-test-sequence.png','lineage-08b/undo-context.png','diagnostics-08b/03-distribution.png','diagnostics-08b/09-switch-first-read-recovered.png','ui-cold-07b/failure-3.png','diagnostics-01/failure.png']:
        if (root/name).is_file():parts.append('<figure><img src="'+esc(name)+'"><figcaption>'+esc(name)+'</figcaption></figure>')
    parts.append('<h2>녹화</h2><p>실제 설치 Electron renderer, 무음·native 데스크톱/로봇 카메라 아님. 원 frame times/ffconcat/오류는 각 폴더에 보존했다. 실패 cold01의 영상도 실패 증거이며 성공 데모로 취급하지 않는다.08부터 everyNthFrame4로 렌더러 측 캡처를 샘플링했고 받은 뒤450ms 미만 저장 생략을 함께 사용했다. 이 관찰부하 변경과 원07의 everyNthFrame1은 구분한다. 앱의 실제 decoded frame 관측과 녹화 프레임 수는 서로 다른 측정이며 native 무녹화 일반 실행의 응답시간도 별도다.</p>')
    parts.append('<p>시각QA정정:원video-receipts의일부TIMING_NOT_QUALIFIED는마지막프레임뒤명시적정지화면유지시간을빼고비교한메트릭이었다. 실제ffconcat은recording end까지유지한다. first frame→기록end와영상길이를다시대조한별도자료를따른다. 관측하지않은중간움직임을만들어낸것은아니다. '+link('video-clock-review.json','원시계·최종정지화면유지시간·인코딩길이대조')+'</p>')
    for video in videos:parts.append('<h3>'+esc(video['path'])+' · '+esc(round(video['duration_s'],3))+'s</h3><video controls preload="none" src="'+esc(video['path'])+'"></video>')
    parts.append('<h2>비용·잔여</h2><pre>'+esc(json.dumps({k:v for k,v in budget.items() if k not in ('requests','new_requests','files')},ensure_ascii=False,indent=2))+'</pre>')
    parts.append('<p>추가USD50캠페인추정잔여 USD'+esc(Decimal('50')-Decimal(budget['protected_additional_50_total']))+' · 앞선USD20캠페인의미확정.4770432는별도원장에이미포함되어있으며0으로지우지않았다.</p>')
    parts.append('<p>provider 사용량/저장 catalog 기준 추정이며 공급자 최종 청구서가 아니다. 이전 USD20 장부는 별도 불변이다. USD50은 추가 캠페인의 누적 한도이며 매턴 새50이 아니다.</p><h2>진입 차단 해소 후의 로봇 집중시험 순서</h2><p>현재 NOT_READY를 로봇을 켜 달라는 요청으로 해석하지 않는다. 현재 확인된 추가 소스 수정 원인은 없지만 원 native fault의 module/stack/kit.exe 종료 상태와 원 요청의 admission/응답 처리 시각이 없어 세 실패의 해소를 증명하지 못했다. 단순 재시작 반복을 원인 해결로 쓰지 않는다. 새 드라이버/Isaac/OS 변경은 하지 않았고 필요하다고 확정하지도 않았다. native dump는 읽기 전용 범위에서 확인했지만 일치 자료를 확보하지 못했다. 이는 추가 권한을 거절당했다는 뜻이 아니다.</p><ol><li>로봇 전원·같은 LAN → 그 시점 충전선 분리/둘레30cm/감독·즉시 차단 확인. 사진 품질/정밀 정합/완성 실측 프로필을 기다리지 않는다.</li><li>일반 Start → 저장 거실 Twin 검토 → Robots PC 준비/Check Connection → Connect/현재 전압·boot → Prepare zero/OFF → LiDAR On.</li><li>정지8초 수집·실제 Pi/저장/추적 진단 확보 → Arm → 별도 Bootstrap Stop. 이것이 첫 바퀴 시험이며 실제 Stop 실패면 추가 바퀴를 금지하고 수집·반출은 유지한다.</li><li>같은 연결에서 패드/키4방향·채팅90도·단일360scan·Stop → operation/trial/command/stream/rawSHA 반출 → Disconnect/cleanup → 사용자 촬영 로봇 영상과 ID 연결.</li></ol><p>현장 전압·센서 신선도·각도 범위·바퀴와 차체 차이로 특정 시험은 INCONCLUSIVE일 수 있다. 이를 사전 소프트웨어 기능 미구현과 혼동하지 않고 새 로그로 판정한다. 자동 자율주행·정밀 세계 정합·실물2대·CAD/BRep 등 전체 제품 완성은 이번 준비의 성적이 아니다.</p>')
    parts.append('<p>'+link('identity-index.json','입력·채팅/Twin/operation 결속')+' · '+link('video-receipts.json','영상 SHA/시간')+' · '+link('evidence-manifest.json','원문 인수자료')+'</p></html>')
    rendered='\n'.join(parts);(root/'report.html').write_text(rendered,encoding='utf-8')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.refs=[]
        def handle_starttag(self,tag,attrs):self.refs.extend(value for key,value in attrs if key in {'src','href'} and value)
    links=Links();links.feed(rendered)
    local=[ref for ref in links.refs if not ref.startswith(('https://','http://'))]
    missing=[ref for ref in local if not (root/ref).is_file()]
    if missing:raise ValueError('Local report has missing linked evidence: '+str(missing))
    save('artifact-qa.json',dict(status='PASS_LOCAL_LINKS_AND_BOUND_SOURCE_NOT_PRODUCT_READY',release_id=identity['release_id'],
        report_sha256=sha256((root/'report.html').read_bytes()).hexdigest(),local_links=len(local),missing=[],
        image_count=rendered.count('<img '),video_count=len(videos),source_unchanged=source_receipt()==identity,
        video_clock_review='video-clock-review.json',visual_scope='Original App screenshots inspected; report CSS/OS DPI not user acceptance.'))
    save('completion-verification.json',dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),**identity,status=gate_result['status'],source_unchanged=True,physical_actions=0,report='report.html'))
    print(json.dumps(dict(status=gate_result['status'],release_id=identity['release_id'],report=str(root/'report.html')),ensure_ascii=False))


if __name__=='__main__':main()
