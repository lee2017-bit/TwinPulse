# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only post-test evidence/report, never an App/model/robot caller."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess
import sys
from verify_robot_lineage_offline import source_receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--tag',default='01')
    p.add_argument('--installation-file',default='installation.json');p.add_argument('--offline-dir',default='offline');a=p.parse_args()
    root=a.root.resolve();identity=source_receipt();prior=root.parent/'robot-test-entry-20261019'
    load=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    digest=lambda path:sha256(path.read_bytes()).hexdigest()
    def save(name,value):
        with (root/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    normal=load(root/'normal/result.json');restart=load(root/'normal-restart/result.json');native=load(root/'native-lifecycle.json')
    shut=load(root/'normal/shutdown.json');shut2=load(root/'normal-restart/shutdown.json')
    lifecycle=dict(**identity,status='PASS' if shut['shutdown_clean'] and shut2['shutdown_clean'] and native.get('normal_native_close') is True and native.get('restart_native_close') is True and native.get('restart_authenticated_ready') is True else 'FAIL',
        normal_start_launch_id=normal['launch_id'],shutdown_clean=shut['shutdown_clean'],restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_launch_id=restart['launch_id'],restart_debug_listener_count=restart['debug_listener_count'],restart_app_listener_count=restart['app_listener_count'],
        restart_authenticated_ready=native.get('restart_authenticated_ready') is True,restart_ready_wait_ms=restart['ready_wait_ms'],restart_shutdown_clean=shut2['shutdown_clean'])
    save('normal-lifecycle.json',lifecycle)
    with (root/'observation-replay.json').open('xb') as f:f.write((prior/'observation-replay-final.json').read_bytes())
    review=load(prior/'evidence-manifest10.json')['physical_readiness_review']
    review['replay']=dict(path='observation-replay.json',sha256=digest(root/'observation-replay.json'))
    review['basis']='Unchanged hardware safety sources; exact original-input replay is source-hash checked. New actual installed SIM/UI and ordinary lifecycle evidence is separate. Historical unknown causes are not claimed repaired.'
    names=dict(fresh=f'ui-fresh-{a.tag}/result.json',cold=f'ui-cold-{a.tag}/result.json',lineage=f'lineage-{a.tag}/result.json',lineage_cold=f'lineage-cold-{a.tag}/result.json',
        normal='normal/result.json',lifecycle='normal-lifecycle.json',installation=a.installation_file,supplementary=a.offline_dir+'/result.json',budget='budget-final.json')
    records={k:load(root/v) for k,v in names.items()}
    review['unresolved']=['CURRENT_JOURNEY_NOT_PASS:'+role for role in ('fresh','cold','lineage','lineage_cold') if records[role].get('status')!='PASS']
    review['status']='KNOWN_RUNTIME_BLOCKER' if review['unresolved'] else 'SOFTWARE_NO_KNOWN_BLOCKER'
    manifest=dict(**identity,physical_readiness_review=review,evidence=[dict(role=k,path=v,sha256=digest(root/v)) for k,v in names.items()])
    save('evidence-manifest.json',manifest)
    gate=Path(__file__).with_name('verify_robot_focus_gate.py')
    def check(name,out):
        r=subprocess.run([sys.executable,str(gate),'--manifest',str(root/name),'--output',str(root/out)],capture_output=True,text=True)
        if r.returncode not in (0,1):raise ValueError(r.stderr)
        return load(root/out)
    verdict=check('evidence-manifest.json','gate-result.json')
    for condition in ('broken-stop','original-failure'):
        negative=json.loads(json.dumps(manifest))
        if condition=='broken-stop':negative['physical_readiness_review']['unresolved']=['LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST']
        else:
            with (root/'original-fresh08.json').open('xb') as f:f.write((prior/'ui-fresh-08/result.json').read_bytes())
            negative['evidence']=[dict(r,path='original-fresh08.json',sha256=digest(root/'original-fresh08.json')) if r['role']=='fresh' else r for r in negative['evidence']]
        save('negative-'+condition+'-manifest.json',negative)
        rejected=check('negative-'+condition+'-manifest.json','negative-'+condition+'-result.json')
        expected='RUN_NOT_PASS:fresh' if condition=='original-failure' else 'KNOWN_PHYSICAL_BLOCKER:LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST'
        if rejected['status']!='NOT_READY' or expected not in rejected['issues']:raise ValueError('Negative failed '+condition)
    videos=[]
    for folder in (f'recording-fresh{a.tag}',f'recording-cold{a.tag}',f'recording-lineage{a.tag}',f'recording-lineage-cold{a.tag}'):
        path=root/folder/'app-screen.mp4';clock=load(root/folder/'frame-times.json');frames=clock['frames'];expected=[(r['at']-frames[0]['at'])/1000 for r in frames]+[(clock['end']-frames[0]['at'])/1000]
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v','-show_packets','-show_entries','packet=pts_time:format=duration','-of','json',str(path)],text=True))
        pts=[float(v['pts_time']) for v in probe['packets']];error=max((abs(x-y) for x,y in zip(pts,expected)),default=1000);duration=float(probe['format']['duration'])
        if len(pts)!=len(expected) or error>.05 or abs(duration-expected[-1])>.1:raise ValueError('Video clock mismatch '+folder)
        videos.append(dict(path=folder+'/app-screen.mp4',bytes=path.stat().st_size,sha256=digest(path),duration_s=duration,maximum_pts_error_s=error,maximum_sample_gap_s=max(b-a for a,b in zip(expected,expected[1:]))))
    save('video-receipts.json',videos)
    attempts=[]
    for path in sorted(root.glob('*/result.json')):
        r=load(path);engine=r.get('desktop',{}).get('engine',{})
        attempts.append(dict(path=str(path.relative_to(root)),sha256=digest(path),status=r.get('status'),error=r.get('error'),release=engine.get('release_id',r.get('release_id')),launch_id=engine.get('launch_id',r.get('launch_id')),project=r.get('project'),input_sha256=r.get('input_sha256'),steps=r.get('steps'),operation_id=r.get('operation_id')))
    save('attempts.json',attempts)
    fresh=records['fresh'];display=fresh['display_samples'];budget=records['budget'];layout=next(s['evidence'] for s in fresh['steps'] if s['name'].startswith('Non-overlapping dock'))
    hold=fresh['sustained_hold_observations'];hold_samples=[v for v in display if hold[0]['at']-50<=v['at']<=hold[-1]['at']+50]
    if len(hold_samples)<100:raise ValueError('Continuous geometry evidence missing')
    drift={k:{dim:max(v[k][dim] for v in hold_samples)-min(v[k][dim] for v in hold_samples) for dim in ('x','y','width','height')} for k in ('canvas','dock')}
    if max(n for row in drift.values() for n in row.values())>1:raise ValueError('Held control geometry drift exceeds one pixel')
    destinations=[]
    for s in fresh['steps']:
        if s['name'].startswith(('Actual panel nearest','Actual main-chat nearest')):
            row=s['evidence']['after'];c=row['command'];destinations.append(dict(journey=s['name'],elapsed_ms=s['elapsed_ms'],request_id=c['request_id'],operation_id=row['operation_id'],state=c['state'],target_id=c['target_id'],target_kind=c['target_kind'],goal_xy=c['goal_xy'],actual_position_m=row['pose']['position_m'],path_length_m=c['path_length_m']))
    save('layout-stability.json',dict(continuous_samples=len(hold_samples),maximum_drift_px=drift,body_selections=layout['bodySelections'],criterion='Original fixed viewport; <=1 CSS px throughout the recorded 60-second hold. Four direction/status transitions independently assert <=1 px in the real journey.'))
    summary=dict(at=datetime.now(timezone.utc).isoformat(),**identity,gate=verdict['status'],issues=verdict['issues'],display_samples=len(display),maximum_display_age_ms=max(v['frame_age_ms'] for v in display),body_selection=layout['bodySelections'],
        continuous_hold_geometry_drift_px=drift,destination_arrivals=destinations,
        new_http=budget['new_http'],new_estimated_usd=budget['new_estimated_usd'],new_unknown_usd=budget['new_unknown_usd'],campaign_total_usd=budget['protected_additional_50_total'],remaining_usd=str(Decimal(50)-Decimal(budget['protected_additional_50_total'])),physical='NOT_RUN_ROBOT_OFF')
    save('summary.json',summary)
    esc=html.escape;link=lambda file,label:'<a href="'+esc(file)+'">'+esc(label)+'</a>'
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 장면 목적지·안정 화면 검증</title><style>body{font:16px/1.65 system-ui;max-width:1200px;margin:30px auto;padding:0 20px;color:#183743}img,video{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f5;padding:14px}td,th{border:1px solid #bbcdd6;padding:8px}table{border-collapse:collapse}</style>',
        '<h1>TwinPulse: 장면 목적지 이동 · 안정된 Twin 화면</h1><p>현재 판정: '+esc(verdict['status'])+'. 로봇 OFF / 실제 설치 Electron Test BrowserWindow + 실제 Flash/Nemotron + Isaac SIM의 성적이다. 실물 목적지 내비게이션·주행·위치보정은 통과하지 않았다.</p>',
        '<p>새 데모 입력과 UI 진행 표시는 영어 우선이다. 기존 한국어 데이터·정지 명령은 유지하며 자동 다국어 응답은 아직 보장하지 않는다. 연결점은 실제 USD 모델 bounds를 투영하고 이름 배치와 분리한다. 공통 fresh CSS의 여백 상속을 제거했다. 상태·명령 결과는 공간을 예약해 패드 조작 중 화면 크기를 유지한다.</p>',
        '<p>SIM 목적지는 현재 장면의 가장 가까운 대상과 장애물로 계획하고 원래 저속·충돌 검사를 통과하는 경유점을 따른다. 접수/계획/주행/도착/취소/실패·request ID를 표시한다. 물체 이동 지시와 로봇 이동을 구분하며 없는 목적지·불가 경로는 명시 실패한다. 실물 목적지 이동은 검증된 지도/어댑터 없이 실행하지 않는다.</p>',
        '<p>LiDAR는 선택한 로봇의 원시각·원위치에 묶인 최신 SIM 반사점만 기본 표시한다. 선택적 소수 레이/Off가 있으며 애니메이션 가짜 관측·실물 측위·보정 완료를 주장하지 않는다. <a href="https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1GZ__SIM__VERSION__NAMESPACE_1_1VisualizeLidar.html">Gazebo VisualizeLidar</a>와 <a href="https://docs.foxglove.dev/docs/visualization/panels/3d">Foxglove 3D</a>의 선택형 시각화를 참고했다.</p>',
        '<h2>SHA·응답성·비용</h2><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
        '<p>'+link('evidence-manifest.json','최종 SHA 명세')+' · '+link('gate-result.json','게이트')+' · '+link('attempts.json','모든 실행/ID/입력 SHA')+' · '+link('budget-final.json','사용/미확정 비용 장부')+' · '+link('implementation-notes.json','초기 실패·수정·제약')+'</p>']
    for image in ('name-only-body-selection','four-pad-directions','lidar-sparse-rays','destination-missing','destination-cancelled','destination-bed-arrived','destination-chair-arrived'):
        parts.append('<h2>'+esc(image)+'</h2><img src="ui-fresh-'+a.tag+'/'+image+'.png" alt="실제 설치 화면 '+esc(image)+'">')
    parts.append('<h2>현재 전체 여정</h2><table><tr><th>여정</th><th>결과</th><th>근거</th></tr>')
    for role in ('fresh','cold','lineage','lineage_cold','normal','lifecycle','supplementary'):parts.append('<tr><td>'+esc(role)+'</td><td>'+esc(records[role]['status'])+'</td><td>'+link(names[role],names[role])+'</td></tr>')
    parts.append('</table><h2>실제 녹화 (배속·움직임 보간 없음)</h2><p>렌더러 표본 사이 마지막 화면 유지는 미관측 움직임의 증거가 아니다. 원 PTS/실제 표본 간격을 보존했다.</p>')
    for v in videos:parts.append('<p>'+link(v['path'],v['path'])+' · '+str(v['duration_s'])+'초</p><video controls preload="metadata" src="'+v['path']+'"></video>')
    parts.append('<h2>남은 범위·정직한 한계</h2><p>실물 로봇·Pi 부하/저장·센서·제동/주행·실제 지도 정합·물리 내비게이션 NOT_RUN. Explorer 더블클릭·OS 붙여넣기·실제 OS DPI·다른 PC·새 사진 품질 NOT_RUN. 동일 Start 파일을 실행 도구로 열고 설치된 같은 Test 창에서 클릭/입력했다. 정상 시작은 debug OFF와 native 종료를 별도로 기록했다. 과거 AV/startup/통신 abort/일시 프레임 지연 원인 UNKNOWN은 보존하며 새 PASS가 원인 해결이나 무재발 보장은 아니다. 현재 변경의 Git commit/push/Release 업로드는 수행하지 않았다.</p></html>')
    with (root/'report.html').open('x',encoding='utf-8') as f:f.write('\n'.join(parts))
    print(json.dumps(summary,ensure_ascii=False));return 0 if not verdict['issues'] else 1


if __name__=='__main__':raise SystemExit(main())
