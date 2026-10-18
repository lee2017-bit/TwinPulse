# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only acceptance aggregation. Never calls an App, provider or robot.

Keeps this release's evidence separate from the prior frozen release. Historical
raw failures remain referenced; a clean rerun is not an attributed repair.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess
import sys

from verify_robot_lineage_offline import source_receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    previous = root.parent/'robot-test-entry-20261019'
    identity = source_receipt()

    def load(path):
        return json.loads(path.read_text(encoding='utf-8-sig'))

    def digest(path):
        return sha256(path.read_bytes()).hexdigest()

    def save(name, value):
        with (root/name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)

    normal = load(root/'normal/result.json')
    restart = load(root/'normal-restart/result.json')
    shutdown = load(root/'normal/shutdown.json')
    shutdown_restart = load(root/'normal-restart/shutdown.json')
    native = load(root/'native-lifecycle.json')
    lifecycle = dict(**identity, status='PASS' if all([
        shutdown['shutdown_clean'], shutdown_restart['shutdown_clean'],
        restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        native.get('normal_native_close') is True, native.get('restart_native_close') is True,
        native.get('restart_authenticated_ready') is True,
    ]) else 'FAIL', normal_start_launch_id=normal['launch_id'],
        shutdown_clean=shutdown['shutdown_clean'], restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_launch_id=restart['launch_id'], restart_debug_listener_count=restart['debug_listener_count'],
        restart_app_listener_count=restart['app_listener_count'],
        restart_authenticated_ready=native.get('restart_authenticated_ready') is True,
        restart_ready_wait_ms=restart['ready_wait_ms'], restart_shutdown_clean=shutdown_restart['shutdown_clean'])
    save('normal-lifecycle.json', lifecycle)
    # Exact prior replay, with unchanged safety-source hashes checked by the gate.
    replay_raw = (previous/'observation-replay-final.json').read_bytes()
    with (root/'observation-replay.json').open('xb') as stream:
        stream.write(replay_raw)
    prior = load(previous/'evidence-manifest10.json')
    review = prior['physical_readiness_review']
    review['replay'] = dict(path='observation-replay.json', sha256=digest(root/'observation-replay.json'))
    review['evidence'] = [dict(path='../robot-test-entry-20261019/evidence-manifest10.json',
                               sha256=digest(previous/'evidence-manifest10.json')),
                          dict(path='offline/result.json', sha256=digest(root/'offline/result.json'))]
    review['basis'] = ('Prior original-input replay is source-hash checked, not new physical evidence. '
                       'Current release separately exercises ordinary UI, faults, restoration and normal lifecycle. '
                       'Historical failures/UNKNOWN roots remain open risks, not claimed repaired by rerun.')
    roles = dict(fresh='ui-fresh-01/result.json', cold='ui-cold-01/result.json',
                 lineage='lineage-01/result.json', lineage_cold='lineage-cold-01/result.json',
                 normal='normal/result.json', lifecycle='normal-lifecycle.json',
                 installation='installation.json', supplementary='offline/result.json', budget='budget-final.json')
    records = {role:load(root/name) for role,name in roles.items()}
    review['unresolved'] = ['CURRENT_JOURNEY_NOT_PASS:'+role for role in ('fresh','cold','lineage','lineage_cold')
                            if records[role].get('status')!='PASS']
    review['status'] = 'KNOWN_RUNTIME_BLOCKER' if review['unresolved'] else 'SOFTWARE_NO_KNOWN_BLOCKER'
    manifest = dict(**identity, physical_readiness_review=review,
                    evidence=[dict(role=role,path=name,sha256=digest(root/name)) for role,name in roles.items()])
    save('evidence-manifest.json', manifest)

    def gate(manifest_name, result_name):
        run = subprocess.run([sys.executable, str(Path(__file__).with_name('verify_robot_focus_gate.py')),
                              '--manifest', str(root/manifest_name), '--output', str(root/result_name)],
                             capture_output=True, text=True)
        if run.returncode not in (0,1):
            raise ValueError('Gate execution failed: '+run.stderr[-1000:])
        return load(root/result_name)

    result = gate('evidence-manifest.json','gate-result.json')
    for label in ('broken-stop','original-failure'):
        negative = json.loads(json.dumps(manifest))
        if label=='broken-stop':
            negative['physical_readiness_review']['unresolved']=['LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST']
        else:
            original = previous/'ui-fresh-08/result.json'
            # Gate rejects traversal by design: copy exact original, never edit it.
            with (root/'original-fresh08.json').open('xb') as stream:stream.write(original.read_bytes())
            negative['evidence']=[dict(row,path='original-fresh08.json',sha256=digest(original))
                                  if row['role']=='fresh' else row for row in negative['evidence']]
        save('negative-'+label+'-manifest.json',negative)
        rejected=gate('negative-'+label+'-manifest.json','negative-'+label+'-result.json')
        expected='RUN_NOT_PASS:fresh' if label=='original-failure' else 'KNOWN_PHYSICAL_BLOCKER:LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST'
        if rejected['status']!='NOT_READY' or expected not in rejected['issues']:
            raise ValueError('Negative gate did not reject exact condition: '+label)

    videos=[]
    for folder in ('recording-fresh01','recording-cold01','recording-lineage01','recording-lineage-cold01'):
        video=root/folder/'app-screen.mp4'; clock=load(root/folder/'frame-times.json')
        expected=[(frame['at']-clock['frames'][0]['at'])/1000 for frame in clock['frames']]
        expected.append((clock['end']-clock['frames'][0]['at'])/1000)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v','-show_packets',
                         '-show_entries','packet=pts_time:format=duration','-of','json',str(video)],text=True))
        pts=[float(row['pts_time']) for row in probe['packets']]
        error=max((abs(a-b) for a,b in zip(pts,expected)),default=1000)
        duration=float(probe['format']['duration'])
        if len(pts)!=len(expected) or error>.05 or abs(duration-expected[-1])>.1:
            raise ValueError('Video clock mismatch: '+folder)
        videos.append(dict(path=folder+'/app-screen.mp4',sha256=digest(video),bytes=video.stat().st_size,
                           duration_s=duration,maximum_pts_error_s=error,
                           maximum_sample_gap_s=max(b-a for a,b in zip(expected,expected[1:])),
                           frame_times_sha256=digest(root/folder/'frame-times.json')))
    save('video-receipts.json',videos)
    attempts=[]
    for path in sorted(root.glob('*/result.json')):
        value=load(path);engine=value.get('desktop',{}).get('engine',{})
        attempts.append(dict(path=str(path.relative_to(root)),sha256=digest(path),status=value.get('status'),
                             launch_id=engine.get('launch_id',value.get('launch_id')),project=value.get('project'),
                             input_sha256=value.get('input_sha256'),operation_id=value.get('operation_id'),
                             elapsed_steps_ms=sum(row.get('elapsed_ms',0) for row in value.get('steps',[]))))
    save('attempts.json',attempts)
    esc=html.escape
    link=lambda name,label:'<a href="'+esc(name)+'">'+esc(label)+'</a>'
    fresh=records['fresh'];budget=records['budget']
    layout=next(row['evidence'] for row in fresh['steps'] if row['name'].startswith('Non-overlapping dock'))
    display=fresh.get('display_samples',[])
    summary=dict(at=datetime.now(timezone.utc).isoformat(),**identity,gate=result['status'],
        current_attempts=attempts,body_selection=layout.get('bodySelections'),
        display_samples=len(display),maximum_display_age_ms=max(row['frame_age_ms'] for row in display),
        new_http=budget['new_http'],new_usd=budget['new_estimated_usd'],unknown=budget['new_unknown_usd'],
        campaign_total=budget['protected_additional_50_total'],remaining_usd=str(Decimal(50)-Decimal(budget['protected_additional_50_total'])))
    save('summary.json',summary)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 이름표 수정·재인수</title>',
           '<style>body{font:16px/1.65 system-ui;max-width:1200px;margin:32px auto;padding:0 20px;color:#163044}img,video{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f5;padding:16px}table{border-collapse:collapse}td,th{border:1px solid #bdcbd3;padding:8px}</style>',
           '<h1>로봇 이름표 가림 수정 · 현재 설치본 재인수</h1>',
           '<p>판정: '+esc(result['status'])+'. 로봇 OFF의 SIM/PC 시험이며 실물 주행·정합 보장이 아니다. 과거 오류의 원인이 모두 밝혀지거나 재발하지 않는다고 주장하지 않는다.</p>',
           '<p>기본은 작은 연결점과 이름만 표시한다. 배경/테두리/그림자/배터리 부행을 제거했다. 현재 프레임의 로봇 투영영역 클릭은 하단 조종기·상태를 연다. 이는 mesh picking/측위가 아닌 투영 hint 선택이며 모호한 겹침은 가까운 anchor를 고른다. 이름표/목록 선택 경로도 유지한다. 연결·이동 권한을 자동 부여하지 않는다.</p>',
           '<img src="ui-fresh-01/name-only-body-selection.png" alt="실제 설치 Twin의 이름만 표시 및 형상 클릭">',
           '<h2>현재 근거</h2><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
           '<p>'+link('evidence-manifest.json','SHA 결속 명세')+' · '+link('gate-result.json','현재 gate')+' · '+link('attempts.json','모든 시도')+' · '+link('video-receipts.json','영상 원시계 대조')+'</p>',
           '<h2>시험 방법·잔여</h2><p>일반 root Start.cmd는 실행도구로 동일 파일을 호출했다. 일반모드에서 debug listener 없이 중복시작·native AltF4·재시작·정리를 별도 확인했다. 전체 조종은 같은 설치본의 명시 Test BrowserWindow를 실제 클릭·입력했다. 일반 전체 native 입력/Explorer 더블클릭/OS 붙여넣기/실제 Windows DPI/다른 PC는 NOT_RUN이다. CSS 다섯 크기는 실제 DPI 변경이 아니다. 모델은 기존 Flash/Nemotron 실제 호출이며 고정 응답/직접 제품변경 API/내부상태 주입을 사용자 시험으로 대체하지 않았다. fault 주입은 ordinary movement 종료·Stop 뒤 별도 창이다.</p>',
           '<p>실물 전원·센서 수집·Pi 부하/저장·제동·주행·현장 정합은 NOT_RUN. 원 LiDAR unknown bytes는 보존하며 정상화/보간하지 않았다. strict tracker/stall은 현장에서 INCONCLUSIVE일 수 있다. 과거 native AV/startup/drive abort/1014.789ms 원인은 UNKNOWN으로 남긴다. '+link('../robot-test-entry-20261019/report.html','과거 모든 실패·원문·정정')+'</p>',
           '<p>부수 보조시험과 새 전체 여정은 구분한다. 첫 CSS 테스트 URL fixture 오류(191/192)는 테스트 파일경로 수정 후192/192 통과했으며 제품 성적에 섞지 않았다. 원사진/프로젝트/장부/원실패 삭제0. 새 의존성/실물/Cloud 동작0. 기존 private GitHub의 공개 설정 변경0. Git 업로드 결과는 별도 영수증으로 연결한다.</p>']
    for row in videos:
        parts+=['<h2>'+esc(row['path'])+'</h2><video controls preload="metadata" src="'+esc(row['path'])+'"></video><p>'+link(row['path'],'원본 녹화')+' · '+esc(row['sha256'])+'</p>']
    parts+=['<p>추가50 캠페인 잔여 USD'+esc(summary['remaining_usd'])+'; 이전20 캠페인14.9450973(UNKNOWN .4770432포함)은 별도 불변. 추정치는 공급자 청구서가 아니다. 영상은 표본 프레임의 원시각을 유지하며 표본 사이 유지 이미지는 미관측 동작의 증거가 아니다.</p></html>']
    with (root/'report.html').open('x',encoding='utf-8') as stream:stream.write(''.join(parts))
    print(json.dumps(summary,ensure_ascii=False))
    return result['status']!='READY_FOR_SUPERVISED_POWERED_TEST'


if __name__=='__main__':
    raise SystemExit(main())
