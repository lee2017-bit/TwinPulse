# SPDX-License-Identifier: Apache-2.0
"""Verify the original supervised failure and cleanup; no hardware actions."""
import hashlib,json,os,html,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-environment-field-20261025-01'
read=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
op='1c3bce27a64e4b088d4ff30669ca5a4e';identity='9ab857c208416c83892dfa59bc09de2d'
runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
raw=runtime/'devices/local/physical-live'/op;receipt=read(raw/'receipt.json')
taskdir=runtime/'projects/chat_mvmcf9wa_18f1e6d1/robot-tasks'/identity;task=read(taskdir/'task.json')
segments=[];kinds=collections.Counter();pc_actions=collections.Counter();robot_actions=collections.Counter();last={};issues=[]
for row in receipt['segments']:
    path=raw/row['path'];digest=hashlib.sha256();count=0;size=0
    with path.open('rb') as stream:
        for line in stream:
            digest.update(line);size+=len(line);count+=1;event=json.loads(line);kind=event.get('kind');data=event.get('data') or {}
            kinds[kind]+=1
            if event.get('schema','').startswith('physical-live-pc-command'):pc_actions[event.get('action')]+=1
            if kind=='command':robot_actions[data.get('action')]+=1
            if kind=='heartbeat':
                for key in ('field','recording','task_local_state','battery','pose'):
                    if data.get(key) is not None:last[key]=data[key]
            if kind=='cleanup' and data.get('subsystem')=='session':last['cleanup']=data
    exact=(digest.hexdigest()==row['sha256'] and size==row['bytes'] and count==row['events'])
    if not exact:issues.append('SEGMENT_MISMATCH:'+row['path'])
    segments.append(dict(**row,exact=exact))
stops=[e for e in task['events'] if e['kind']=='stop_confirmed'];children=[e for e in task['events'] if e['kind']=='child_started']
runtimecopy=OUT/'runtime-copies01/6ee891a3ef214c11a2dab5cfdfbaceb1'
cleanup=read(runtimecopy/'cleanup-receipt.json');engine=read(runtimecopy/'engine-result.json')
checks=dict(original_recording_complete=receipt['complete'] and not receipt.get('error') and receipt['accepted']==receipt['saved']==receipt['event_count']==sum(r['events'] for r in segments),
    all_segments_exact=all(r['exact'] for r in segments),task_failure_preserved=task['state']=='FAILED' and task['segments']==0 and not children,
    task_stop_confirmed=bool(stops) and all(e.get('receipt',{}).get('zero_off_readback_confirmed') for e in stops),
    terminal_robot_cleanup_confirmed=last.get('cleanup',{}).get('confirmed') is True,
    normal_owned_exit=cleanup['exit_evidence_complete'] and cleanup['owned_processes_stopped'] and all(v['return_code']==0 and v['root_disposition']=='EXITED_DURING_GRACE' for v in cleanup['process_exit_observations'].values()),
    inner_cleanup=engine['cleanup_status']=='PRE_CLOSE_COMPLETE' and not engine['cleanup_errors'])
field=last.get('field') or {};trials=field.get('trials',[])
value=dict(status='FAILED_BEFORE_FIRST_COMMON_TASK_CHILD',scope='ACTUAL_PHYSICAL_TRIAL_NOT_SIM_ACCEPTANCE',
    checks=checks,issues=issues,release_id='20261024T205438Z-be150e10b23f',launch_id=runtimecopy.name,
    operation_id=op,task_id=identity,task_reason=task['reason'],task_sha256=sha((taskdir/'task.json').read_bytes()),
    requested_plan=task['plan'],distance_m=task['distance_m'],segments=task['segments'],task_events=task['events'],
    receipt_path=str(raw/'receipt.json'),receipt_sha256=sha((raw/'receipt.json').read_bytes()),
    raw_count=receipt['event_count'],raw_bytes=receipt['bytes'],raw_segments=segments,
    original_event_kinds=dict(kinds),pc_command_actions=dict(pc_actions),robot_command_actions=dict(robot_actions),
    latest_field_trials=trials,terminal_cleanup=last.get('cleanup'),
    conclusion='Connection/Prepare/native sensing and scoped bootstrap wheel Stop succeeded. The new common survey task was rejected by PC pose/map admission before its first child. It did not complete moving collection or return.',
    cause_status='UNCONFIRMED_EXACT_GUARD_BRANCH',
    leading_candidate='The pinned original stationary-ring age exceeds500ms after repeated snapshot/planning/persistence checks; adjacent original rows show no meaningful pose/config/connection change. No original failed-guard branch timestamp/age was retained.',
    next_change_proposal=['Persist typed failed-guard branch and original age without changing the exception.',
        'Acquire a bounded fresh stationary native observation immediately before pinning each physical child, then revalidate that exact primitive and preserve final wire/Stop guards.',
        'Cover the real500ms adapter/fleet admission boundary, not only the prior fake1000ms fixture. No threshold relaxation or automatic motion retry.'],
    model_claim='outputs/environment-task-loop-20261025-01/call-claims/012.json',model_calls_this_attempt=1,
    independent_chassis_accuracy='UNQUALIFIED',world_registration='NOT_ESTABLISHED',whole_room_coverage_verified=False,
    recording_limitations=['session01 interrupted by inspection-tool kernel timeout; original frames/timestamps retained, not whole video.',
        'session02 recorder failed on orphan recording-pointer ownership before capture; retained.',
        'session03 is the actual post-recovery renderer recording, not native or robot-camera footage.'])
with (OUT/'result01.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
e=lambda s:html.escape(str(s))
body=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 현장시험 결과</title>
<style>body{{max-width:1050px;margin:32px auto;padding:20px;font:16px/1.7 system-ui;background:#f7faf9;color:#17313a}}section{{background:white;padding:22px;margin:16px 0;border:1px solid #d4e3de;border-radius:12px}}video{{width:100%}}.fail{{color:#a42d37}}code{{overflow-wrap:anywhere}}</style>
<h1>2026-10-25 감독 실물시험</h1><h2 class="fail">이동 수집 FAIL — 첫 common task child 발행 전 차단</h2>
<p><a href="result01.json">원 결과·해시·정리 검사</a> · <a href="admission-analysis01.json">인접 원관측 대조</a> · 설치 {e(value['release_id'])}</p>
<section><h2>실제 결과</h2><p>앱 연결·Prepare/출력1200ms readback·12.2–12.3V·약390개 실제 LiDAR점을 확인했다. 8초 정지수집은완료했으나 일부incomplete ring때문에INCONCLUSIVE다. bootstrap Stop은FORWARD_WHEEL_STOP_OBSERVATION 범위PASS이며독립차체정확도·제동거리인증이아니다.</p>
<p>실제 모델의 survey→return_to_start→stop(3m/180s/64segments)을 Run했다. 첫정지관측/후보선택후 <b>{e(task['reason'])}</b>로거절. 이동수집 child0·거리0이며방순회·귀환성공이아니다. task의actualStopreadback/zeroOFF는확인했다.</p></section>
<section><h2>원인과 보완 대상</h2><p>인접원문은PAUSED·동일config/boot/frame/epoch·XY불변이며yaw차이는약1.43e-6rad다. 반복snapshot/저장/경로검사중같은원ring의500ms가소진된가능성이가장높다. 다만정확한실패분기·원age가없어단독원인은미확정이다. 새기본값확대나새timestamp로PASS시키지않는다.</p>
<ol><li>최종guard의거절code/원sourceage·정확request결속을보존한다.</li><li>physical pin직전에bounded최신stationary native관측을확보하고해당primitive를재검증한다.</li><li>실제500ms와adapter/fleet admission전이를재현한다. 이보고서는제품수정·실물재시험완료를뜻하지않는다.</li></ol></section>
<section><h2>종료·원자료</h2><p>Stop·LiDAR OFF·Disconnect·앱정상Exit. 로봇세션최종cleanup confirmed={e(checks['terminal_robot_cleanup_confirmed'])}, root정상종료={e(checks['normal_owned_exit'])}, innercleanup={e(checks['inner_cleanup'])}.</p>
<p>원 {receipt['event_count']:,}행/{receipt['bytes']:,}bytes/{len(segments)}segments를원receipt와SHA·bytes·행수대조했다. 원문삭제/직접SSH우회/시스템변경/제품수정/GitHub업로드0. 새텍스트모델1회(기존50중누적12/38미사용).</p></section>
<section><h2>실제 후반 화면 기록</h2><p>session01 도구timeout과session02 녹화pointer충돌은실물원기록과분리보존했다. 아래는session03의실제renderer/마우스이벤트표시며완성제출물·OS커서·실물카메라영상이아니다.</p><video controls preload="metadata" src="session03/app-screen.mp4"></video></section></html>'''
with (OUT/'report.html').open('x',encoding='utf-8') as f:f.write(body)
print(json.dumps(dict(status=value['status'],checks=checks,raw_count=value['raw_count'],raw_bytes=value['raw_bytes'],segments=len(segments),pc_actions=dict(pc_actions),robot_actions=dict(robot_actions))))
sys_exit=0 if all(checks.values()) and not issues else 1
raise SystemExit(sys_exit)
