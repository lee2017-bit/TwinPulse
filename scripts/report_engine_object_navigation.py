# SPDX-License-Identifier: Apache-2.0
"""Read-only local evidence/report. Never calls App, provider or a robot."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys
from verify_robot_lineage_offline import source_receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--tag',default='07');p.add_argument('--build-tag',default='06');p.add_argument('--lineage-cold-tag',default='07b');a=p.parse_args();tag=a.tag;build=a.build_tag;cold_tag=a.lineage_cold_tag
    root=a.root.resolve();identity=source_receipt()
    def load(name):
        f=root/name
        return json.loads(f.read_text(encoding='utf-8-sig')) if f.is_file() else {'status':'NOT_RUN'}
    def digest(name):return hashlib.sha256((root/name).read_bytes()).hexdigest()
    def save(name,value):
        if (root/name).exists():
            if load(name)!=value:raise ValueError('Existing derived evidence changed; preserve and use a new report revision: '+name)
            return
        with (root/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    names=dict(fresh=f'ui-fresh-{tag}/result.json',cold=f'ui-cold-{tag}/result.json',lineage=f'lineage-{tag}/result.json',
        lineage_cold=f'lineage-cold-{cold_tag}/result.json',normal=f'normal{build}/result.json',lifecycle=f'normal-lifecycle{build}.json',
        installation=f'installation{build}.json',supplementary=f'offline{build}/result.json',budget='budget-final.json')
    records={role:load(name) for role,name in names.items()}
    native=load(f'native-observations{build}.json');restart=load(f'normal-restart{build}/result.json')
    shutdown=load(f'normal{build}/shutdown.json');shutdown2=load(f'normal-restart{build}/shutdown.json')
    ready=load(f'normal-restart{build}/authenticated-ready.json')
    if records['lifecycle']['status']=='NOT_RUN' and native.get('schema')=='actual-native-observations-1.0':
        native_ok=all(native.get(role,{}).get('input_returned') is True and native[role].get('owned_shutdown_request_observed_after_input') is True
            and native[role].get('launch_id')==run.get('launch_id') for role,run in [('normal',records['normal']),('restart',restart)])
        authenticated=ready.get('status')=='ready' and ready.get('phase')=='ready' and ready.get('message')=='Authenticated Isaac stage is ready'
        ok=native_ok and authenticated and shutdown.get('shutdown_clean') is True and shutdown2.get('shutdown_clean') is True
        save(names['lifecycle'],dict(**identity,status='PASS' if ok else 'FAIL',normal_start_launch_id=records['normal'].get('launch_id'),
            shutdown_clean=shutdown.get('shutdown_clean'),restart_ready=restart.get('status')=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
            restart_launch_id=restart.get('launch_id'),restart_debug_listener_count=restart.get('debug_listener_count'),
            restart_app_listener_count=restart.get('app_listener_count'),restart_authenticated_ready=authenticated,
            restart_ready_wait_ms=restart.get('ready_wait_ms'),restart_shutdown_clean=shutdown2.get('shutdown_clean'),
            native_observations=native,authenticated_ready_source=f'normal-restart{build}/authenticated-ready.json',
            classification='Actual native close twice, authenticated engine readiness from the exact launch supervisor. Native Home/Explorer/full-native UI contents NOT_RUN; no screenshots claimed.'))
        records['lifecycle']=load(names['lifecycle'])
    # A failed native tool is not a passing native close. No old-release receipt
    # is relabelled current, and cleanup by launcher file is not UI acceptance.
    if records['lifecycle']['status']=='NOT_RUN':
        save(names['lifecycle'],dict(**identity,status='NOT_RUN',normal_start_launch_id=records['normal'].get('launch_id'),
            native_input='NOT_RUN_CAPTURE_TOOL_FAILURE',normal_tool_error=['FrameArrived timed out: timed out waiting on channel',
                'window capture timed out: timed out waiting on channel'],
            cleanup_only=load(f'normal{build}/shutdown-cleanup-only.json'),
            classification='Explicit owned launcher cleanup request, not native Exit/AltF4 acceptance; no force kill.'))
        records['lifecycle']=load(names['lifecycle'])
    replay='native-full-replay04.json'
    blockers=['CURRENT_UI_NOT_PASS:'+role for role in ('fresh','cold','lineage','lineage_cold') if records[role].get('status')!='PASS']
    original_file=f'original-goal{build}/result.json';original=load(original_file)
    if original.get('status')!='PASS_ORIGINAL_SAVED_SCENE_GOALS':blockers.append('ORIGINAL_START_REGRESSION_NOT_PASS')
    review=dict(schema='physical-readiness-review-1.1',scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
        status='KNOWN_RUNTIME_BLOCKER' if blockers else 'SOFTWARE_NO_KNOWN_BLOCKER',unresolved=blockers,
        observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
        protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',
        not_run=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT'],
        replay=dict(path=replay,sha256=digest(replay)),
        evidence=[f'offline{build}/lineage-and-pc.log',f'offline{build}/field.log','native-full-replay04.json',
            names['fresh'],names['cold'],original_file],
        basis='Current source review by primary agent, not an Astra review. New physical object-route, worker bundle, relative-anchor and unknown-ring skip are exercised only by supplementary tests/raw replay. No unchanged-hardware claim. Actual Pi acquisition, output and driving were NOT_RUN (robot OFF).')
    manifest=dict(**identity,physical_readiness_review=review,evidence=[dict(role=k,path=v,sha256=digest(v)) for k,v in names.items() if (root/v).is_file()])
    save('evidence-manifest.json',manifest)
    gate=Path(__file__).with_name('verify_robot_focus_gate.py')
    def check(name,out):
        if (root/out).is_file():return load(out) # Same hash-bound manifest, checked by save() above.
        r=subprocess.run([sys.executable,str(gate),'--manifest',str(root/name),'--output',str(root/out)],capture_output=True,text=True)
        if r.returncode not in (0,1):raise RuntimeError(r.stderr)
        return load(out)
    verdict=check('evidence-manifest.json','gate-result.json')
    negative=json.loads(json.dumps(manifest));negative['physical_readiness_review']['unresolved']=['LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST']
    save('negative-stop-manifest.json',negative);rejected=check('negative-stop-manifest.json','negative-stop-result.json')
    if 'KNOWN_PHYSICAL_BLOCKER:LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST' not in rejected['issues']:raise ValueError('Broken Stop negative not rejected')
    for label,role,file,expected in [('partial-cold','lineage_cold','lineage-cold-07/result.json','MISSING_OR_FAILED_STEP:lineage_cold:'),
            ('original-failure','fresh','ui-fresh-04/result.json','RUN_NOT_PASS:fresh')]:
        negative=json.loads(json.dumps(manifest))
        negative['evidence']=[dict(e,path=file,sha256=digest(file)) if e['role']==role else e for e in negative['evidence']]
        save('negative-'+label+'-manifest.json',negative);v=check('negative-'+label+'-manifest.json','negative-'+label+'-result.json')
        if v['status']!='NOT_READY' or not any(i.startswith(expected) for i in v['issues']):raise ValueError('Negative not rejected '+label)
    attempts=[]
    for directory in sorted(root.iterdir()):
        f=directory/'result.json'
        if not directory.is_dir() or not f.is_file() or directory.name.startswith(('build-','diagnostic-build-')):continue
        r=json.loads(f.read_text(encoding='utf-8-sig'));engine=r.get('desktop',r.get('identity',{})).get('engine',{})
        attempts.append(dict(path=f.relative_to(root).as_posix(),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),status=r.get('status'),
            release_id=r.get('release_id',engine.get('release_id')),launch_id=r.get('launch_id',engine.get('launch_id')),
            diagnostic_execution_id=r.get('diagnostic_execution_id',engine.get('diagnostic_execution_id')),
            project=r.get('project'),operation_id=r.get('operation_id'),error=r.get('error'),
            steps=[dict(name=s.get('name'),status=s.get('status'),elapsed_ms=s.get('elapsed_ms')) for s in r.get('steps',[])]))
    save('attempts.json',attempts)
    notes=load('implementation-notes.json');fresh=records['fresh']
    original_inputs=dict(original_sha256='039643560c55a7a1b2489cd13bcebd43b88559dacdd1ca86fff8da638a8c1eaf',
        final_input_sha256=hashlib.sha256(next((s.get('evidence',{}).get('text','') for s in fresh.get('steps',[]) if s.get('name')=='Visible New chat and original robot-containing scene brief'),'').encode()).hexdigest())
    summary=dict(**identity,at=load('final-summary.json').get('at',datetime.now(timezone.utc).isoformat()),gate=verdict,status='PARTIAL_NOT_READY' if verdict['status']=='NOT_READY' else 'SCOPED_PC_SIM_PASS',
        robot_off=True,ssh_calls=0,motor_calls=0,git_writes=0,new_dependencies=0,
        original_failure=notes['original_failure'],original_start_regression=original,
        original_inputs=original_inputs,budget=records['budget'],
        known_limits=notes['limits'],ordinary_start=records['normal'],native_lifecycle=records['lifecycle'])
    samples=fresh.get('display_samples',[])
    summary['quality']=dict(current_input='TEXT_ONLY_ESTIMATED_LAYOUT',photo_quality='NOT_RUN',
        physical_motion='NOT_RUN',world_registration='NOT_RUN',simulator='Actual USD kinematic transforms, not wheel/dynamics qualification')
    summary['responsiveness']=dict(generation_ms=next((s.get('elapsed_ms') for s in fresh.get('steps',[]) if s.get('name')=='Real provider generation and current Isaac frame'),None),
        decoded_display_samples=len(samples),max_observed_frame_age_ms=max((s.get('frame_age_ms',0) for s in samples),default=None),
        frame_limit_ms=1000,sim_no_catchup_limit_s=.5,
        original_stall_single_cause='UNKNOWN; fixed identified defects and retested original conditions, no no-recurrence guarantee',
        statistics_limit='Sampled/abnormal engine diagnostics are not a normal latency population; no Wi-Fi p99, sigma or false-stop probability inferred.')
    summary['remaining_additional_50_usd']=str(Decimal('50')-Decimal(records['budget']['protected_additional_50_total']))
    demo=load(f'fresh-demo{build}/result.json')
    summary['demo']=dict(status=demo['status'],project=demo.get('project'),operation_id=demo.get('operation_id'),
        video=demo.get('video'),command_inputs=demo.get('command_inputs'),steps=demo.get('steps'))
    summary['log_receipts']=[dict(path=f.relative_to(root).as_posix(),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in root.glob('*logs*/receipt.json')]
    save('final-summary.json',summary)
    esc=lambda v:html.escape(str(v));link=lambda name,label=None:'<a href="'+esc(name)+'">'+esc(label or name)+'</a>'
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 실물 목적지·엔진 정체 검증</title>',
        '<style>body{font:16px system-ui;max-width:1180px;margin:32px auto;line-height:1.65;padding:0 20px;color:#172633}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f7;padding:16px}img,video{max-width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left}table{border-collapse:collapse;width:100%}h2{margin-top:32px}</style>',
        '<h1>실물 추정 목적지 이동·엔진 정체 수정 검증</h1>',
        '<p>현재 판정: '+esc(summary['status'])+' / '+esc(verdict['status'])+'. 로봇 OFF: 새 SSH·센서·바퀴 명령 0. 현재 소스 '+esc(identity['source_sha256'])+'.</p>',
        '<h2>무엇을 바꿨나</h2><p>실물 목적지의 일괄 SIM 전용 거절을 제거했다. 사용자가 검토한 초기 X/Y/yaw와 같은 연결의 상대 LiDAR 추적을 추정 Twin 경로에 연결한다. 정확한 실측 지도는 요구하지 않지만, 모르는 현재 위치를 아는 것처럼 진행하지 않는다. 로봇 쪽 기존 위험·속도·입력·기록 보호가 최종 출력을 소유하며, 추정 완료는 ESTIMATE_REACHED로 표시한다.</p>',
        '<p>엔진 작업 진단 키 유실·최초 fault 덮어쓰기·2,000개 진단 이력 상한 뒤 capture 정지·중복 USD 검색을 수정했다. 큰 operation JSON은 잘게 인코딩하고 GET이 디스크 재저장을 시작하지 않게 했다. 시험기의 31MB 진행 파일 반복 쓰기/0.3초 파싱도 제거했다. 보호 기한·기하 기준·속도 완화나 정상 응답 고정 대체는 없다.</p>',
        '<h2>원인과 증거의 한계</h2><pre>'+esc(json.dumps(notes,ensure_ascii=False,indent=2))+'</pre>',
        '<p>원 v553 정체의 단일 OS/Kit 원인은 UNKNOWN으로 보존한다. 중간 fresh04의 468ms 목적지 작업·2.547초 FleetIO는 확인했지만 캐시/JSON/시험기/메모리 중 하나만 유일한 원인이라고 단정하지 않는다. 새 clean run은 재현 조건 검증이지 과거 단일 인과나 무재발 보증이 아니다.</p>',
        '<h2>최종 설치본 실제 여정</h2><table><tr><th>여정</th><th>판정</th><th>원문</th></tr>']
    for role in names:parts.append('<tr><td>'+esc(role)+'</td><td>'+esc(records[role].get('status','BUDGET_CONFIRMED' if records[role].get('within_approved_total') else 'NOT_RUN'))+'</td><td>'+link(names[role])+'</td></tr>')
    parts+=['</table><p>'+link(original_file,'원 장면·원 침대 출발 pose 회귀')+' · '+link(f'fresh-demo{build}/result.json','최신 처음부터 전체 데모 결과')+'</p>',
        '<h2>실제 화면</h2>']
    for name in ('control-layout-1920-1080','destination-missing','destination-cancelled','destination-bed-arrived','destination-chair-arrived'):
        f=f'ui-fresh-{tag}/'+name+'.png'
        if (root/f).is_file():parts.append('<h3>'+esc(name)+'</h3><img src="'+esc(f)+'" alt="실제 설치 창">')
    parts.append('<h2>실제 렌더러 녹화</h2><p>같은 설치 Test BrowserWindow 실제 조작 표본이다. Explorer·OS 붙여넣기·실물 차체 영상이 아니다. 배속/움직임 보간 없이 원 표본 시각을 유지했다.</p>')
    for folder in (f'fresh-demo{build}',f'original-goal{build}',f'recording-fresh{tag}',f'recording-cold{tag}',f'recording-lineage{tag}',f'recording-lineage-cold{cold_tag}'):
        video=folder+'/app-screen.mp4'
        if (root/video).is_file():parts.append('<h3>'+esc(folder)+'</h3><video controls preload="none" src="'+esc(video)+'"></video><p>'+link(video)+' · '+link(folder+'/session.json','시각/실행 ID')+'</p>')
    parts+=['<h2>모든 시도·ID·SHA·시간</h2><pre>'+esc(json.dumps(attempts,ensure_ascii=False,indent=2))+'</pre>',
        '<h2>정확한 비용·잔여·게이트·미검증</h2><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
        '<p>'+link('evidence-manifest.json','SHA 명세')+' · '+link('gate-result.json','최종 게이트')+' · '+link('budget-final.json','예산 장부')+' · '+link('native-full-replay04.json','원 LiDAR 전체 재생')+' · '+link('label-unit06.json','이름/조종 분리 보조 시험')+' · '+link('../command-draft-enter-20261019/failure-demo03-logs/after-exit/receipt.json','원 v553 실패 로그 SHA')+'</p></html>']
    with (root/'report.html').open('x',encoding='utf-8') as f:f.write('\n'.join(parts))
    print(json.dumps(dict(report=str(root/'report.html'),gate=verdict,status=summary['status']),ensure_ascii=False))


if __name__=='__main__':main()
