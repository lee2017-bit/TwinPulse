# SPDX-License-Identifier: Apache-2.0
"""Local evidence report. Read-only to product data; never publishes anything."""
import hashlib,html,json,os,shutil,subprocess
from pathlib import Path
from datetime import datetime
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChangeHistory
from roomplan_runtime_copy_gate import check_runtime_copy

root=Path('outputs/roomplan-import-20261023').resolve()
selected=['ui-import17','ui-edit16','ui-sim17','ui-cold14']
release=json.loads((root/'build18/dist/TwinPulse/windows-release-manifest.json').read_text(encoding='utf-8'))
esc=lambda v:html.escape(str(v))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
records={p.parent.name:json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*/result.json')}
issues=[]
for name in selected:
    r=records.get(name,{})
    if r.get('status') not in ('PASS','PASS_WITH_EXPECTED_STOP_REJECTION'):issues.append(name+': not PASS')
    if r.get('versions',{}).get('engine',{}).get('release_id')!=release['build_id']:issues.append(name+': wrong release')
    # Re-read the immutable UI download, rather than trusting the recorder's
    # derived operation_events projection. This never alters the original result.
    native_gate=subprocess.run(['node','--input-type=module','-e',"import fs from 'node:fs';import path from 'node:path';import {classifyRoomplanResponses as gate} from './scripts/roomplan_response_gate.mjs';const p=process.argv[1],r=JSON.parse(fs.readFileSync(p,'utf8'));if(r.phase==='sim'){const e=JSON.parse(fs.readFileSync(path.join(path.dirname(p),r.operation_download),'utf8'));if(e.operation_id!==r.registered.operation_id||e.robot_id!==r.registered.robot_id)throw Error('Wrong original operation export');r.operation_events=e.events;}process.stdout.write(JSON.stringify(gate(r)));",str(root/name/'result.json')],capture_output=True,text=True) if r else None
    checked_gate=json.loads(native_gate.stdout) if native_gate and native_gate.returncode==0 else {'status':'FAIL'}
    if r.get('errors') or r.get('failed_requests') or r.get('video_error') or checked_gate['status']!='PASS':issues.append(name+': renderer/network/recording errors')
    if r:(root/name/'independent-response-gate.json').write_text(json.dumps(checked_gate,indent=2))
    if not r.get('video',{}).get('frames'):issues.append(name+': actual recording absent')
    required=dict(zip(selected,[6,3,12,3]))[name]
    if len([s for s in r.get('steps',[]) if s.get('status')=='PASS'])!=required:issues.append(name+': required step count mismatch')
normal=records.get('normal18',{})
if normal.get('status')!='PASS_NORMAL_START_REUSE_DEBUG_OFF' or normal.get('release_id')!=release['build_id']:issues.append('normal18 not PASS/current release')
shutdown=root/'normal18/shutdown.json'
if not shutdown.exists() or json.loads(shutdown.read_text(encoding='utf-8')).get('status')!='PASS':issues.append('normal18 cleanup absent/failed')
native_close=root/'normal18/native-close.json'
native_after=root/'normal18/native-after-cleanup.json'
if not native_close.exists() or json.loads(native_close.read_text(encoding='utf-8')).get('action')!='Alt_L+F4':issues.append('normal native close evidence absent')
if not native_after.exists() or json.loads(native_after.read_text(encoding='utf-8')).get('windows')!=[]:issues.append('normal native window did not close')
fresh=records.get(selected[0],{})
adopt=next((r['body'] for r in fresh.get('responses',[]) if r.get('path')=='/v1/product/environment/action' and r.get('body',{}).get('status')=='imported'),{})
project=adopt.get('project_id')
proof={}
if project:
    folder=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects'/project
    original=Path('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd')
    raw=json.loads((folder/'project.json').read_text(encoding='utf-8'))
    source=SiteDraftRecord.from_dict(raw['site_draft'])
    history=SceneChangeHistory.from_dict(json.loads((folder/'project.scene-changes.json').read_text(encoding='utf-8')),source,project)
    _,site=history.replay(source)
    archives=list((folder/'inputs').glob('*/environment-source.bin'))
    proof=dict(project_id=project,input_revision=source.input_revision.digest,source_sha256=sha(original),
        archive_sha256=[sha(p) for p in archives],original_geometry_restored=site.scene.environment==source.site.scene.environment,
        final_scene_revision=site.scene.revision,history_schema=history.schema_version,
        operations=[dict(id=op.operation_id,mode=op.mode,parent=op.parent_revision,result=op.result_revision) for op in history.operations],
        meshes=len(site.scene.environment['meshes']),triangles=sum(len(m['triangles']) for m in site.scene.environment['meshes']),
        units_basis=site.scene.environment['units_basis'],meters_per_unit=site.scene.environment['meters_per_unit'])
    if proof['source_sha256']!='844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b' or proof['source_sha256'] not in proof['archive_sha256']:issues.append('source bytes mismatch')
    if not proof['original_geometry_restored']:issues.append('Undo geometry not original')
else:issues.append('fresh project absent')
if records.get(selected[3],{}).get('selected_project')!=project:issues.append('cold project not same fresh import')
cold=records.get(selected[3],{})
if not any(row.get('body',{}).get('project_id')==project and row['body'].get('status')=='imported' and row['body'].get('source_sha256')==proof.get('source_sha256') and row['body'].get('scene_revision')==proof.get('final_scene_revision') for row in cold.get('responses',[]) if row.get('path','').startswith('/v1/product/environment')):issues.append('cold UI response did not confirm same project/source/restored revision')
sim=records.get(selected[2],{})
policy=Path('scripts/roomplan_response_gate.mjs')
if sim.get('video',{}).get('began',0)/1000<policy.stat().st_mtime:issues.append('response policy changed after selected SIM began')
if sim.get('response_policy_sha256')!=sha(policy):issues.append('selected SIM did not record this exact response policy SHA')
robot=sim.get('registered',{})
if sim.get('arrival',{}).get('command',{}).get('state')!='ARRIVED' or sim.get('arrival',{}).get('command',{}).get('target_id')!='Env_cc8fbcdf2f69d0ebdbd8':issues.append('original Sofa0 arrival missing')
if sim.get('chat_motion',{}).get('command',{}).get('state')!='COMPLETED' or sim.get('full_turn',{}).get('command',{}).get('state')!='COMPLETED':issues.append('chat/360 command incomplete')
if robot.get('source_twin_context',{}).get('project_id')!=project:issues.append('SIM belongs to another project')
if robot.get('source_twin_context',{}).get('scene_revision')!=proof.get('final_scene_revision'):issues.append('SIM belongs to a different saved Twin revision')
for stop in (row for row in sim.get('responses',[]) if row.get('request',{}).get('action')=='stop'):
    request=stop['request'];after=next((r for r in stop.get('body',{}).get('robots',[]) if r.get('robot_id')==request.get('robot_id')),{})
    epoch=after.get('motion_epoch')
    if stop.get('status')!=200 or not epoch or epoch==request.get('motion_epoch') or after.get('operation_id')!=robot.get('operation_id'):issues.append('Stop receipt not same operation/new epoch')
    if not any(row.get('at',0)>=stop.get('at',0) and row.get('at',0)-stop.get('at',0)<=12000 and any(r.get('robot_id')==request.get('robot_id') and r.get('operation_id')==robot.get('operation_id') and r.get('connection_epoch')==request.get('connection_epoch') and r.get('control_state')=='PAUSED' and r.get('motion_epoch')==r.get('applied_motion_epoch')==epoch for r in row.get('body',{}).get('robots',[])) for row in sim.get('responses',[])):issues.append('Stop new epoch lacks actual engine ACK')
if len([row for row in sim.get('responses',[]) if row.get('request',{}).get('action')=='stop'])<7:issues.append('four release and three explicit Stop receipts missing')
export=root/selected[2]/sim.get('operation_download','absent')
if not export.is_file():issues.append('operation export missing')
proof['sim_robot_id']=robot.get('robot_id');proof['sim_operation_id']=robot.get('operation_id')
proof['sim_export_sha256']=sha(export) if export.is_file() else None
final_log=records.get('ui-final-log17',{})
final_export=root/'ui-final-log17'/final_log.get('operation_download','absent')
if final_log.get('status')!='PASS' or final_log.get('versions',{}).get('engine',{}).get('release_id')!=release['build_id'] or not final_export.is_file():
    issues.append('finalized original operation UI download missing')
else:
    complete=json.loads(final_export.read_text(encoding='utf-8'));manifest=complete.get('manifest',{});events=complete.get('events',[])
    earlier=json.loads(export.read_text(encoding='utf-8')) if export.is_file() else {}
    if complete.get('operation_id')!=robot.get('operation_id') or complete.get('robot_id')!=robot.get('robot_id') or complete.get('project_id')!=project:issues.append('finalized export has different original identity')
    if manifest.get('source_twin_context')!=robot.get('source_twin_context'):issues.append('final export changed original Twin context')
    if manifest.get('complete') is not True or manifest.get('completeness')!='FINALIZED' or manifest.get('event_count')!=len(events) or manifest.get('missing')!=[] or manifest.get('journal',{}).get('complete') is not True or manifest.get('journal',{}).get('saved')!=len(events):issues.append('original final export incomplete')
    if not earlier.get('events') or events[:len(earlier['events'])]!=earlier['events']:issues.append('final export does not retain immutable earlier event prefix')
    proof['sim_finalized_export']=dict(path=str(final_export.relative_to(root)),sha256=sha(final_export),events=len(events),manifest=manifest)
runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
launches={records.get(name,{}).get('versions',{}).get('engine',{}).get('launch_id') for name in selected}|{normal.get('launch_id')}
cleanup=[]
for launch in sorted(v for v in launches if v):
    folder=runtime/'launches'/launch;dest=root/'runtime-final18'/launch;dest.mkdir(parents=True,exist_ok=True)
    for filename in ('cleanup-receipt.json','owned-exit-observations.json','engine-result.json'):
        path=folder/filename
        if path.is_file():shutil.copy2(path,dest/filename)
        else:issues.append(launch+': missing '+filename)
    receipt=dest/'cleanup-receipt.json'
    if receipt.is_file():
        value=json.loads(receipt.read_text(encoding='utf-8'));cleanup.append(dict(launch_id=launch,sha256=sha(receipt),receipt=value))
        if value.get('exit_evidence_complete') is not True or value.get('owned_processes_stopped') is not True:issues.append(launch+': incomplete shutdown')
        for role in ('backend','engine'):
            observed=value.get('process_exit_observations',{}).get(role,{})
            if observed.get('root_disposition')!='EXITED_DURING_GRACE' or observed.get('return_code')!=0 or observed.get('evidence_complete') is not True or observed.get('errors')!=[]:issues.append(launch+': '+role+' natural exit unconfirmed')
    engine=dest/'engine-result.json'
    if engine.is_file():
        value=json.loads(engine.read_text(encoding='utf-8'));joins=value.get('viewport_phase_diagnostics',{}).get('join_status',{})
        if value.get('launch_id')!=launch or value.get('cleanup_status')!='PRE_CLOSE_COMPLETE' or value.get('cleanup_errors')!=[] or any(joins.get(k) is not False for k in ('viewport_alive','fleet_alive','diagnostic_alive')) or joins.get('scan_worker',{}).get('worker_alive') is not False:issues.append(launch+': inner cleanup not complete')
runtime_copies=[]
for launch in sorted(v for v in launches if v):
    copied=root/'runtime-copies18'/launch/'copy-receipt.json'
    if not copied.is_file():issues.append(launch+': original runtime copy missing');continue
    value=json.loads(copied.read_text(encoding='utf-8'))
    issues.extend(launch+': '+error for error in check_runtime_copy(copied.parent,launch,value))
    runtime_copies.append(dict(path=str(copied.relative_to(root)),sha256=sha(copied),receipt=value))
from twinpulse_app.windows_package import verify_package
try:
    integrity=verify_package(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/releases'/release['build_id'])
except Exception as error:
    integrity={'error':str(error)};issues.append('final installed integrity failure')
media_file=root/'media-checks.json'
media=json.loads(media_file.read_text(encoding='utf-8')) if media_file.is_file() else {}
if media.get('status')!='PASS':issues.append('encoded-media verification incomplete')
if media.get('visual_review',{}).get('status')!='PASS':issues.append('encoded contact-sheet visual review absent')
for name in selected:
    checked=next((v for v in media.get('videos',[]) if v.get('name')==name),{})
    video=root/name/'recording/app-screen.mp4'
    if checked.get('decode_return_code')!=0 or not video.is_file() or checked.get('sha256')!=sha(video):issues.append(name+': encoded-media evidence mismatch')
open_risks=[dict(id='ROOMPLAN_HELD_INPUT_EXPIRY',status='OPEN_ROOT_UNKNOWN',trial='ui-sim10',operation_id='f04e77d16d3c46b8ac632605afb9c684',launch_id='33989c9c7cd14edbb4d1f2faa682d4f6',reason='INPUT_STALE while pointer remained held; simultaneous fleet GET 561.7ms. Backend/renderer/OS attribution unavailable. A new session passing does not repair this failure.',last_accepted_sequence=75,last_expires_at_ms=1792710159559,automatic_stop_native_start_ms=1792710159681.545,pointer_up_ms=1792710160210,diagnostic_gap='Original fleet routes excluded from request probe; other route finish samples exhausted. Candidate15 adds bounded fleet/renewing route diagnostics; this is not a root fix.'),dict(id='ROOMPLAN_SECOND_HELD_INPUT_ABORT',status='OPEN_ROOT_UNKNOWN',trial='ui-sim12',operation_id='7978dac10fd4412f9f85c784d83ec8d9',reason='First forward drive sequence5 aborted and automatic Stop preceded awaited release Stop. Whole FAIL retained. No joining recovery to motion acceptance.')]
open_risks.append(dict(id='ROOMPLAN_SIM13_HELD_INPUT',status='OPEN_ROOT_UNKNOWN',trial='ui-sim13',
    operation_id='37ab8c46ed1f446cb29b2c8748756382',reason='Second forward input took 317 ms and original engine reported INPUT_STALE. Earlier slow workflow snapshot is not proven the direct cause of this input failure.'))
open_risks.append(dict(id='PREVIEW_REPLACEMENT_RACE',status='HANDLED_PROTOCOL_RACE_NOT_REMOVED',trial='ui-edit15',
    reason='Original whole FAIL retained for viewport_preview_expired HTTP409. Server keeps one preview; UI explicitly waits for replacement without current-frame authority. Exact replacement-to-request binding unavailable; a new clean run is not proof this race was eliminated.'))
supplementary=json.loads((root/'supplementary-attempts17.json').read_text(encoding='utf-8'))
scope_matrix={
    'S01':'PARTIAL: normal Start/reuse/native Home and engine-connected AX/native close and cold Test restart passed; native screen capture, full native journey and Explorer start not run',
    'S02':'SELECTED_GATE: actual New chat/Attach/explicit units/local inspection/import/Build',
    'S03':'PARTIAL: preserved original bytes/geometry IDs and mesh rendering; real dimensions/photo fidelity not qualified',
    'S04':'PARTIAL: one SIM, four short holds/releases, Sofa0, chat/360 and seven exact Stops; new 60-second hold/Stop all not run here',
    'S05':'PARTIAL: mesh LiDAR streaming/OFF in UI; detailed first-hit cases are supplementary, not physical calibration',
    'S06':'PARTIAL: manual Chair0 translation/ACK/durable Undo; model-interpreted furniture edit not run',
    'S07':'PARTIAL: same source/units/scene/history restoration and explicit rebuild; cold operation-log UI journey not run here',
    'S08':'PARTIAL: negative contract/unit guards; complete installed failure/cancellation/late-result matrix not run',
    'S09':'NOT_RUN: previous full existing text/2SIM/60-second/history journeys not reacquired on this candidate',
    'S10':'PARTIAL: concave floor supplementary test; second fresh installed import environment not run',
    'S11':'NOT_RUN: clean-user profile, other PC, public-rights/package review and distribution',
}
builds=[]
for path in sorted(root.glob('build*/dist/TwinPulse/windows-release-manifest.json')):
    value=json.loads(path.read_text(encoding='utf-8'))
    builds.append(dict(folder=path.parents[2].name,build_id=value['build_id'],source_manifest_sha256=value['source_manifest_sha256'],manifest_sha256=sha(path),files=len(value['files'])))
summary=dict(schema='roomplan-local-acceptance-1.0',at=datetime.now().astimezone().isoformat(),
    status='ROOMPLAN_SCOPE_VERIFIED_WITH_OPEN_CONTROL_LATENCY_RISK' if not issues else 'INCOMPLETE',issues=issues,
    release=release['build_id'],source_manifest_sha256=release['source_manifest_sha256'],files=len(release['files']),
    selected=selected,normal=normal,proof=proof,cleanup=cleanup,runtime_copies=runtime_copies,builds=builds,installed_integrity=integrity,submission_plan_scope=scope_matrix,new_llm_http=0,new_cost_usd=0,
    additional_50_cumulative_usd='4.6899930',additional_50_remaining_usd='45.3100070',
    physical_robot='NOT_RUN',full_robot_ready=False,open_risks=open_risks,photofidelity='NOT_SOLVED',native_os_dialog='NOT_RUN',normal_native_observation=json.loads((root/'normal18/native-observation.json').read_text(encoding='utf-8')),response_policy_sha256=sha(policy),media=media,supplementary=supplementary,
    sim_raw_http_error_count=len([r for r in sim.get('responses',[]) if r.get('status',0)>=400]),sim_response_gate=sim.get('response_gate'))
(root/'acceptance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse RoomPlan 가져오기 검증</title>',
 '<style>body{font:16px/1.65 system-ui;max-width:1120px;margin:35px auto;padding:0 22px;color:#17333d}h1,h2{line-height:1.3}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccd8df;padding:8px;vertical-align:top}img,video{max-width:100%;border:1px solid #d3dce0}small{color:#52666e}.status{padding:16px;background:#e2f2eb}</style>',
 '<h1>RoomPlan 환경 가져오기 — 실제 설치 검증</h1>',f'<p>{esc(summary["at"])} · 로컬 전용, 개인 평면도/원사진/USD 비공개</p>',
 f'<p class="status">{esc(summary["status"])} · {esc(issues)}</p>',
 '<p>이번 인수 범위는 원본 공간 Import → 실제 Isaac 표시 → 가구 한 개 평행이동/Undo → SIM 조작·원 가구 목표 → 저장·cold 재열기다. 각 결과는 아래 선택 여정과 원문을 따른다. 이전 후보의 입력 만료 원인은 아직 미확정이다. <b>전체 연속 제어 안정성·로봇 현장시험 준비 완료로 판정하지 않는다.</b> 사진→3D 충실도, 새 모델 해석·자연어 가구편집, 실제 로봇/세계 정합 또는 전체 제출계획 완료도 아니다.</p>',
 '<h2>구현과 판정 경계</h2><p>공통 Attach의 USD 목적 선택을 Import space / Library asset으로 분리했다. 환경은 원본 bytes/SHA·stable prim ID를 보존하고 실제 삼각형을 meter/Z-up으로 파생한다. 메타데이터 bounds는 실제 방 collider가 아니다. 가구 1개 XY 이동만 허용하고 구조는 읽기 전용이다. 원본 파일은 바꾸지 않고 override와 기존 Apply→ACK→저장 트랜잭션을 사용한다.</p>',
 '<p><b>실제 사용:</b> New chat → Attach USD → Import space → Source units → Inspect space → Import space → Show Twin. 재실행 후에는 저장 채팅 열기 → Reopen saved scene → Import space → Show Twin. 재열기 자체로 Build·SIM·로봇 동작이 시작되지 않는다.</p>',
 '<p>원본에 metersPerUnit이 없어 실제 UI에서 Meters(m)를 선택했다. <b>미보정 SIM 선택값</b>이며 실측 미터 정확도가 아니다. 원본 전체 hierarchy/transform은 원본 bytes에 보존되지만 파생 장면은 world mesh·원 prim path·객체ID 중심이다. 임의 편집 가능한 완전 CAD나 정확한 실제 가구 재현이라고 주장하지 않는다.</p>',
 '<p>원 floor 삼각형 mask와 높이 0.005–0.30m의 차체 장애물을 0.1m 격자로 처리해 기존 bounded planner/manual guard에 연결했다. SIM LiDAR는 nominal mount 높이 0.182m에서 원 mesh 첫 교차를 사용한다. 실물 외부보정은 미검증이다. 원 RoomPlan이 생략한 다리·작은 물건까지 복원된 것은 아니다. 기존 다른 단일-floor SIM 경로는 이 입력에 대해 명시 거절하고 Fleet 콘솔로 안내한다. 실물 semantic 경로는 아직 이 새 입력에 연결하지 않는다.</p>',
 '<h2>전체 계획과 이번 1차 경로를 구분</h2><p>선택 여정 gate 통과가 S01–S11 전체 통과를 뜻하지 않는다. 이번 사용자 승인은 RoomPlan 환경 가져오기를 먼저 진행하는 범위다.</p><pre>'+esc(json.dumps(scope_matrix,ensure_ascii=False,indent=2))+'</pre>',
 '<h2>최종 설치와 원본</h2><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
 '<h2>실제 사용자 시험</h2><p>root Start 명령을 실행 도구로 호출했다(Explorer 더블클릭 아님). normal 시작시간·반복Start/단일8765/debug-off는 위 원 receipt에 기록한다. Windows Computer Use의 앞선 화면 캡처는 FrameArrived/window capture timeout, 요소 클릭은 coordinate input geometry unavailable이었다. 최종 normal18의 native 접근성 원문에서는 Home과 Isaac connected를 모두 확인했다. 현재 native 화면 캡처는 NOT_RUN으로 남긴다. native Alt+F4 요청 뒤 창 소멸·프로세스/포트0·자연종료를 검사했다. 전체 조작은 명시 Test Start가 연 동일 설치 Electron BrowserWindow에 Playwright로 연결했다. 별도 Chrome·제품 변경 API·모델 고정응답·내부 상태 주입은 쓰지 않았다. 파일 첨부는 DOM file input이며 OS 대화창/클립보드는 NOT_RUN이다.</p>',
 '<table><tr><th>여정</th><th>결과/원문</th><th>단계</th></tr>']
for name in selected:
    r=records.get(name,{})
    steps=[{'name':s.get('name'),'status':s.get('status'),'ms':s.get('ms')} for s in r.get('steps',[]) if s.get('status')]
    parts.append(f'<tr><td>{esc(name)}</td><td>{esc(r.get("status","NOT_RUN"))} · <a href="{name}/result.json">원 결과</a></td><td>{esc(json.dumps(steps,ensure_ascii=False))}</td></tr>')
parts.append('</table><h2>실제 화면과 녹화</h2><p>실제 renderer 녹화이며 OS 화면/실물 로봇 영상이나 완성된 제출 데모가 아니다. 녹화용 pointer 이벤트 화살표가 포함된다. 순서별 별도 여정이며 사이를 이어 한 번의 연속 녹화라고 부르지 않는다.</p>')
for name in selected:
    shots=sorted((root/name).glob('*.png'))
    if shots:parts.append(f'<h3>{esc(name)}</h3><a href="{name}/{shots[-1].name}"><img src="{name}/{shots[-1].name}"></a>')
    video=root/name/'recording/app-screen.mp4'
    if video.exists():parts.append(f'<video controls preload="metadata" src="{name}/recording/app-screen.mp4"></video><small>{video.stat().st_size:,} bytes · SHA256 {sha(video)}</small>')
    contact=root/name/'recording/encoded-contact.png'
    if contact.exists():parts.append(f'<p>실제 인코딩 영상의 처음·중간·마지막 프레임</p><img src="{name}/recording/encoded-contact.png">')
parts.append('<h2>모든 중간 시도 — 실패를 최신 성공으로 덮지 않음</h2><table><tr><th>시도</th><th>판정</th><th>실패/시간</th></tr>')
for name,r in sorted(records.items()):
    rejected=bool(r.get('errors') or r.get('failed_requests') or any(row.get('status',0)>=400 for row in r.get('responses',[]))) and not (name==selected[2] and r.get('status')=='PASS_WITH_EXPECTED_STOP_REJECTION' and r.get('response_gate',{}).get('status')=='PASS')
    shown=str(r.get('status'))+(' · WHOLE_GATE_REJECTED' if rejected else '')
    interruption=root/name/'interruption.json'
    note=json.loads(interruption.read_text(encoding='utf-8')).get('reason','') if interruption.is_file() else ''
    parts.append(f'<tr><td><a href="{name}/result.json">{esc(name)}</a></td><td>{esc(shown)}</td><td>{esc(r.get("error",""))} {esc(r.get("ready_wait_ms",""))} {esc(note)}</td></tr>')
parts += ['</table><p>probe02는 상대 cwd의 USD open 실패, probe03는 수정 후 실제 worker/서비스 보조 통과이며 UI 인수와 별도다. build01–18 중 01/02/05/14는 실제 사용자 여정에 쓰이지 않은 중간 후보다. 다른 후보의 성공을 최종18의 인수로 합산하지 않는다. ui-edit05는 정상 Undo preview 응답 전에 시험기5초 대기가 끝난 실패였다. 제품15초 한도는 불변이며 시험기를15초+화면1초로 맞췄다. 17후보의 첫 import14/edit13 결과는 남기되 SIM15를 edit13 종료 확인 전에 시작한 주 작업자의 실행 순서 오류로 선택 인수에서 제외했다. SIM15는 Ctrl+C 중단 뒤 recovery-sim15로 Stop/OFF/반출/Disconnect/Exit만 확인했다. 선택 여정은 위 selected 목록이며 후반 복구를 실패 주행에 합치지 않는다.</p>',
 '<p>ui-sim03의 단계 PASS는 409 fleet_motion_changed 1건 때문에 최종 인수에서 거절했다(acceptance-rejected09.json). 정지 뒤 이전 epoch 입력을 거절하는 보호는 유지하며, 원03에는 요청 상관 정보가 부족해 정상 방어로 사후 면제하지 않았다. 새 시험기는 실제 요청 action/ID/epoch를 기록하고 HTTP·page·abort·녹화 오류도 전체 판정에 포함한다. ui-cold01은 준비 전 CDP 연결 실패 뒤 실제 시작창 WINDOWS_PACKAGE_UNMANIFESTED_FILE을 확인했다. 원 검사기가 설치 scripts에 peer-module pyc를 쓴 원인을 -B와 peer import 전 dont_write_bytecode로 차단했다. 패키지 검증은 완화하지 않았다. ui-import08은 등록 중 workflow GET이3초를 넘겨 전체 FAIL이다. 명시 adopt의 이전 조회를 drain하고 새 조회는 등록 트랜잭션 종료까지 대기시키되 기존 조회3초/변경15초·정지 채널·서버 검증은 유지한다. 앞선 원 실패는 그대로 보존했다.</p>',
 '<p>발견·수정: 대형 grid wire 크기 초과·worker packaging 누락·top camera up 계산(Astra), lease 이전 Build 검사(실제 UI), 숫자 UUID 편집ID(실제 UI), 연속 Undo가 취소 작업 재적용(Astra), JS 숫자 왕복의 exact digest 불일치(실제 UI, server-pinned review로 수정), ACK 뒤 이전 revision으로 즉시 Undo하는 UI race(실제 UI). build08 SIM02는 Sofa0 접근 중 719ms 갱신 공백/641ms MainThread generation2 GC로 실패했다. 원 operation1bdec11c653842b4934b696b31d655fa·원영상은 보존한다. 매 tick 객체 hash만 필요한 곳의 scene.to_dict()가 전체 mesh revision까지 계산한 불필요 할당 경로를 asdict(objects)만으로 좁혔다. 같은 객체 hash는 불변이며 GC/시간/속도/기하 기준은 바꾸지 않았다. 별도 순수 데이터 200회 대조는 1.356→0.129초, GC[547,49,4]→[9,0,0]이다. 이는 Kit 전체 GC 해결이나 실물 성공 보장이 아니다.</p>',
 '<p>ui-import09/10은 조회 경합 보완 후 오류0이었다. ui-edit09는 동작3개가 통과해도 Undo preview/초기 Apply 중 workflow GET abort2건으로 전체 FAIL을 보존했다. 같은 조회 drain을 environment preview/build/초기 Apply 응답까지 공통화했다. 비동기 commit 전체에서 경합이 절대로 없음을 보장하는 수정은 아니므로 실제 후속 구간도 재시험했다. Twin pane을 미리 열어 둔 이미지 네 경로는 전송 전 대기를 기존2초 timer 바깥으로 이동했다. 원 시각·프레임 신선도 기준은 불변이다.</p>',
 '<h2>원 실패·현재 통과·미해결을 분리</h2><p>ui-sim07/09의 미분류409와 ui-sim10 FAIL은 그대로 보존한다. 동결 전 명시한 response policy1.1은 원 HTTP409를 숨기지 않으며 실제 pointer-up 이후 Stop이 epoch를 바꾸는 동안 진행 중이던 이전 입력의 거절만 EXPECTED_STOP_REJECTION으로 분류한다. 실제 요청ID/원시각·한 개 in-flight·무큐/무재시도·같은operation Stop·새 epoch 엔진 ACK·후속 정지 표본·원 엔진event를 모두 요구한다. 정책 양성1/음성20=21통과. 보고서는 원 UI 다운로드의 events를 다시 읽어 독립 재검사한다. 원 정보가 없는 이전 실패에 소급 면제하지 않는다.</p>',
 '<p><b>미해결:</b> ui-sim10의 operation f04e77d16d3c46b8ac632605afb9c684는 pointer-up 약528ms 전에 자동Stop이 시작됐고 INPUT_STALE이 원 event18에 남았다. 마지막 성공seq75의 TTL이 만료됐으며 동시fleet GET561.7ms가 관측됐다. Kit update47ms/전체63ms/GC0이라 그 시각의 Kit stall 근거는 없다. backend probe가 fleet GET/POST를 수집하지 않고 다른 경로의16표본도 소진돼 backend lock/GC·renderer/OS 중 단독원인은 UNKNOWN이다. 약37.7초 뒤 snapshot IO466ms를 이 실패 원인으로 소급하지 않는다. 이후 새 세션의 제한된 여정 통과는 원 만료 수정·장시간 재발 방지 증거가 아니다. 다음 제어 안정화에는 해당 경로의 bounded 지연 진단과 동일 장시간 조건 재현/재시험이 남는다. 시간·속도·센서 기준은 완화하지 않았다.</p>',
 '<p>ui-cold05는 exact 프로젝트가 약7초 뒤 열렸지만 시험기의5초 assertion이 먼저 종료된 원 FAIL이다. 15초 switch+15초 pending+5초 화면 범위로 시험기만 정렬하고 새 cold06 전체를 별도로 수행했다. cold06의103ms는 이미 준비된 창에 기록기가 붙은 뒤 Isaac-ready assertion 시간이지 전체 cold 시작시간이 아니다. 실제 프로젝트 재열기7336ms, 명시ShowTwin 원형상 표시12767ms다. ui-sim11은 동작12개/원HTTP409두건의 명시 분류는 통과했지만, 마지막Stop 새epoch의 엔진ACK 없이 LiDAR OFF로 넘어가 최종gate에서 거절했다(acceptance-rejected13-sim11.json). 시험기의 이전 PAUSED snapshot 조건을 정확Stop응답/new epoch ACK 대기로 고쳤다. 그 뒤 원13의 ui-sim12는 첫forward 입력갱신 seq5 HTTP abort로 FAIL이며, Stop/OFF/반출/Disconnect/Exit 복구와 주행 성적을 합치지 않는다. 최초 복구 기록기의 고정 robot caption 오류도 recovery-sim12 FAIL로 보존, 실제 등록label로 바꾼 recovery-sim12b는 정리만 통과했다.</p>',
 '<p>반복 cold07도 장면은 표시됐으나 viewport/current abort1로 wholeFAIL을 보존했다. Astra 읽기검토로 같은 launch backend.log의1792711584753 시각에서 engine viewport POST2075.783ms, current GET2002.470ms/이미지잠금대기1986.476ms를 확인했다. lock 보유 thread는 Image.open→Pillow 첫 플러그인 로딩→PyInstaller 모듈추출 중이었다. request ID가 없어 개별GET 완전결속에는 한계가 있지만 실제 잠금지연·2초deadline 경합의 강한 근거다. 새15는 Image.preinit을 HTTP 시작 전으로 옮기고 JPEG전용 open을 명시했다. 크기/verify/원시각/1초freshness/2초delivery는 불변이다. fleet GET/POST도 기존 비차단 Queue16에 진단하며 기존16행/2stack한도를 route별60초마다 갱신한다. UUID 참조만 보존하고 keepalive의 이전 accepted시각/참조를 지운다. 이는 입력만료 원인을 이미 해결했다는 뜻이 아니라 다음 원인을 놓치지 않기 위한 보완이다.</p>',
 '<p>설치15의 import12/edit11/normal15가 통과해도 sim13은 첫forward seq2/native317ms/첫바이트대기약300ms 후 fleet_motion_changed·원INPUT_STALE로wholeFAIL이다. 해당UUID backend표본은없고 handler150ms미만이면 accept/read대기를 놓치는 진단한계가남았다. 동시fleet GET의 registry설정file읽기는fleet lock밖이며SIM drive가건너뛰므로직접원인으로단정하지않는다. 그보다8.6초전 workflow read_id da0ef112…의3145.030ms 중 snapshot3101.047ms는 workflow lock아래 history.replay→scene.revision→canonical전체직렬화 stack으로확인했다. 새16은표시용 private cache키만전체content JSON SHA로계산하고공개canonical digest/권한/validation은불변, effective()의검증된단일replay결과를재사용한다. nonprogressive의공개progressive/placement의미를바꾸지않았고기존/환경state SHA동등성57개·16subtestsPASS다. cache hit전record.to_dict/scene revision비용은남으며seq2직접원인해결보장도아니다.</p>',
 '<p>설치16은 import13/edit12/SIM14가 통과해도 cold09의 environment GET abort9건과 ShowTwin53.100초 때문에 전체 FAIL이다. 원 backend stack은 매 조회마다 SceneChangeStore.load→replay→전체canonical 기하를 재계산하고 다른 GET이 env lock을 기다리는 경로를 확인했다. 새17은 같은 workflow→env 잠금 아래 이미 검증·게시된 input/history/artifact revision을 결합한 metadata만 표시한다. 불일치·derived·미등록은 failed/revision null로 차단하고 current_review_not_disk_validation을 명시한다. 중복Inspect의 env→workflow 역순도 제거했다. 표시값은 실행권한이 아니며 명시Build 직전에 fresh project/input archive SHA/journal replay와 current revision을 검사해 변경 시 거절한다. Preview/Apply의 기존 fresh 검증과 unknown Tx 차단도 유지한다. Astra 읽기검토에서 추가 확정P1/P2는 없었고 실제cold는 별도 시험이다. 이전 실패는 runtime-original16-cold에 원문 그대로 보존했다.</p>',
 '<p>17후보의 순차 import15/edit14/SIM16/확정반출16은 통과했지만 cold11은 명시 Reopen saved scene을 생략한 시험기 기대 오류로 실패했다. 메타데이터 검증을 풀지 않고 기존 실제 버튼을 누르도록 기록기를 수정했다. 새 cold12는 그 버튼 뒤 실제 conversation/environment/projects GET abort3건으로 실패했다. 원 abort 시각은1792715487228/1792715487439/1792715489800이며 native startTime=0/-1이어서 완전 개별요청 결속에는 한계가 있다. 같은 원stack에서 resume_saved_scene→snapshot→effective/replay 중 workflow lock과 환경GET의 workflow lock 대기, conversation GET의 conversation lock 대기는 확인됐지만 projects는 별도 catalog filesystem I/O이며 같은 lock으로 단정하지 않는다. 원 resume POST는 이전 기록기/probe 수집 밖이어서 정확 POST 시간은 UNKNOWN이다. 새18은 명시 resume 두 경로에만 기존 조회 drain/barrier를 적용했다. Stop/drive는 우회하고 context 재검사·finally해제·no retry·기존3초/15초 제한을 유지한다. 기록기도 새 resume POST의 ID/응답/native timing을 보존한다. 관련 API/환경UI99개 및 tsc/Vite PASS; 처음 추가시험의 Stop payload 누락 TS 오류는 시험소스에서 고쳤다. 새18의 일반Start와 전체 순차 여정은 다른 후보 결과와 합산하지 않는다.</p>',
 '<p>최종18의 ui-edit15는 세 동작이 통과해도 viewport_preview_expired HTTP409 한 건 때문에 전체 FAIL로 남겼다. 서버의 단일 preview 교체 중 UI가 처리하는 응답이지만 정확한 교체 결속이 없어 사후 면제하지 않았다. 새 독립 import17/edit16은 같은 정책으로 오류0 통과했으며 경쟁조건 자체를 제거했다는 뜻이 아니다. ui-cold13은 resume POST200/2878.743ms와 environment200/391.680ms, HTTP·page·abort0이었지만 기록기의5초 assertion이 응답 완료 전에 시작해 FAIL했다. 기록기를 실제 resume 응답 대기부터 진행하도록 고쳤다(기존6초 read+15초 mutation+4초 화면의25초 시험 한도, metadata assertion20초). 제품 HTTP 한도나 검증은 바꾸지 않았다. 새 cold14는 새 launch에서 전체3단계를 통과했으며 실패 후반을 이어 합산하지 않았다.</p>',
 '<p>최초 최종 보고기는 정상 종료 시 생성되지 않을 수 있는 optional engine-liveness-observations.json을 필수로 잘못 요구해 INCOMPLETE였다. 원 <a href="acceptance-rejected18-collector.json">거절 결과</a>와 <a href="report-rejected18-collector.html">당시 보고서</a>를 보존했다. 진단 파일은 의심/회복 관측 시 조건부 생성되므로 부재를 ORIGINAL_UNAVAILABLE로 표시하고 건강 증거로 쓰지 않는다. 필수8개와 optional 진단의 typed 행, 실제 Kit 원문 총10개를 exact unique 목록·launch·허용된 Kit 경로·bytes/SHA로 재검사한다. 파일이 실제 있으면 unavailable로 면제하지 않는다. Astra가 지적한 빈 목록·누락·중복 행을 놓칠 수 있는 보고기 결함도 엄격 검사와 음성10종 보조시험으로 보완했다. 실제 선택 원문은 기존에도 필수 행을 포함했으며 제품/설치본을 다시 바꾼 것은 아니다.</p>',
 '<h2>보조 시험과 한계</h2><p>이전 보조 environment/site simulation/goal45개·13subtests, viewport/latency/environment67개·27subtests, summary/기존편집/placement/feedback57개·16subtests와 UI 관련5집합224개(환경17 포함)는 중복 집계하지 않는다. snapshot no-load/no-replay·결합불일치8종·Build 원project/archive/journal 변조·중복Inspect lock을 포함한 Python82개 PASS, 환경UI17개/tsc·Vite PASS, response policy21개 PASS다. 보고기 원문 복사 검증1개(양성2종·음성10subtests 및 존재 파일의 부재 면제 거절)도 통과했다. 별도 전체 UI 병렬 실행에서는 viewport/App/ChatWorkspace 타이밍 시험3개가 실패했고 Ctrl+C로 중단했으므로 전체PASS가 아니다. 세 원 실패는 단독 직렬 재검사3PASS/미선택292였지만 그것이 원인 해결이나 전체시험 통과를 뜻하지 않는다. <a href="supplementary-attempts17.json">정확 보조 실행 이력</a>·<a href="ui-supplementary-timing-recheck17.log">단독 재검사 로그</a>·<a href="ui-api-environment18.log">마지막99개 로그</a>를 보존했다. 기존 SystemExit fault injection warning, 잘못된 경로/PYTHONPATH/시험 소스 syntax·disabled 검사·-I/보고기Python·UTF8 가정 오류도 제품 실패와 구분한다. 새 의존성 설치0. 테스트 수는 실제 여정 대체가 아니다.</p>',
 '<p>주 작업·통합/설치는 현재 대화의 주 작업자가 수행했다(실제 주 모델/effort를 조회·변경할 도구는 없어 설정을 단정하지 않음). UI 보조는 명시 Sol6.1 high, 독립 읽기검토는 Astra xhigh였다. Astra는 실행 인수를 수행하지 않았고 원 입력만료를 실패·원인미확정으로 유지하라고 검토했다. 읽기검토 의견은 실제 시험 통과나 실물 성공 보장이 아니다.</p>',
 '<h2>비용·권한·남은 작업</h2><p>이번 새 LLM HTTP 0, 외부 전송 0, 추가 USD0. 기존 추가50 장부의 누적 USD4.6899930/잔여45.3100070은 변동 없음(새 계정 잔액 조회 아님). 이전20 장부14.9450973/미확정0.4770432는 별도다. 시스템/Isaac/새 SDK 설치·실물/SSH·유료 Cloud·공개·commit/push·삭제는 실행하지 않았다. 기존 도구로 로컬 후보만 패키징했다.</p>',
 '<p>남음: 사진 의미/누락 보완과 실제 모델 기반 가구 변경 제안, 개인 자료 전송 범위 확인이 필요한 새 모델 시험, 실측 scale/실제 로봇 pose·LiDAR 정합과 현장 주행, 새 환경에서 Library 자산 추가, 제출용 영문 압축영상/공개 권리 검수·Git 업로드. 원 사진-only 품질 0/6은 이 결과로 해결 처리하지 않는다. 모든 9단계/17항목 완료가 아니다.</p></html>']
(root/'report.html').write_text(''.join(parts),encoding='utf-8')
print(json.dumps({'status':summary['status'],'issues':issues,'report':str(root/'report.html')},ensure_ascii=False))
if issues:
    raise SystemExit(1)
