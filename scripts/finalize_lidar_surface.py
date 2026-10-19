# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Aggregate unchanged original evidence. No App, model, robot or Git writes."""
import argparse
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess
import sys
from verify_robot_lineage_offline import source_receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--tag',default='03');p.add_argument('--report-only',action='store_true');p.add_argument('--proof-only',action='store_true');a=p.parse_args()
    root=a.root.resolve();repo=Path(__file__).resolve().parents[1]
    load=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    digest=lambda path:sha256(path.read_bytes()).hexdigest()
    def save(name,value):
        with (root/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    if not a.report_only:
        attempts=[]
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or not (folder/'result.json').exists():continue
            r=load(folder/'result.json')
            attempts.append(dict(path=folder.name+'/result.json',sha256=digest(folder/'result.json'),status=r.get('status'),
                release_id=r.get('release_id') or r.get('desktop',{}).get('engine',{}).get('release_id'),
                launch_id=r.get('desktop',{}).get('engine',{}).get('launch_id'),project=r.get('project'),operation=r.get('operation_id'),
                input_sha256=r.get('input_sha256'),steps=len(r.get('steps',[])),error=r.get('error')))
        save('attempts-index.json',attempts)
        notes=dict(builds={
            '01':'SIM-only channel omitted existing physical setup; not final acceptance.',
            '02':'Development channel. Fresh01 timed out finding the menu after an unconditional toggle; original pre-click open state was not recorded and sole causality is not proven. Fresh02 requested Next at the default last saved frame. Both whole failures retained, not joined to diagnostics.',
            '03':'Original scan sensor pose added to operation log; superseded before a fresh journey when sensor-review clipping was found.',
            '04':'TypeScript private contextId access failed; stale prior web distribution was packaged by a shell command that did not stop. Never installed or accepted.',
            '05':'Public api.context, explicit portal review and Stop all. Actual panel inspection showed poor inherited button contrast; not final.',
            '06':'Final readable sensor review and frozen product. Acceptance records below are bound to this exact installed release.'},
            original_failures_preserved=True,physical='OFF_NO_CONNECTION_SENSOR_OR_MOTOR_COMMANDS',
            not_run=['Live physical sensor acquisition','Verified sensor-to-Twin world overlay','Physical driving/localization/braking','Other-robot sensor occlusion','Optical reflectance/noise or exact LDS sampling','OS clipboard','Explorer double click','Other PC or actual OS DPI'],
            tool_differences='Identical installed Start invoked by execution tool; same explicit Test BrowserWindow actual clicks and typing. Normal non-debug lifecycle/native Close separately recorded. No direct mutation API or fixed provider response.',
            supplemental_setup_failures=['Initial standalone USD check lacked provider PYTHONPATH; corrected verifier only.',
                'Initial offline aggregate invalidated by switching installed release; offline-05 invalidated by rebuilding web sources. All their groups passed but whole aggregates were not accepted.',
                'Fresh03 passed 38 UI steps but omitted the opt-in model-body-click probes. Fresh04 repeats the whole journey with those probes mandatory; no evidence is backfilled into Fresh03.',
                'Cold03 failed because the caller omitted --field-config and the old argument reader treated --cdp as its filename. The CLI now rejects missing prerequisites before UI input; Cold04 repeats the whole original journey.',
                'New body-selection gate first rejected its old synthetic positive fixture; explicit synthetic fixture fields and a missing-body negative test were added. These are not App evidence.',
                'First final aggregate rejected Fresh04 because the new actual saved-native UI step was not listed in the exact required normal-step set. Added that required step and a missing-step negative test, without altering original App results or relaxing the fault boundary. Original NOT_READY aggregate is retained in aggregate-first-failed.'])
        save('implementation-notes.json',notes)
        run=subprocess.run([sys.executable,str(Path(__file__).with_name('finalize_scene_robot_ux.py')),str(root),'--tag',a.tag,
            '--installation-file','installation-06.json','--offline-dir','offline-final-gate-2'])
        if run.returncode:raise ValueError('ORIGINAL_WHOLE_JOURNEY_GATE_FAILED')
        fresh=load(root/f'ui-fresh-{a.tag}/result.json');geometry=load(root/'geometry.json')
        step=next(s for s in fresh['steps'] if s['name'].startswith('Actual saved native scan imported via UI'))
        mounted=next(s for s in fresh['steps'] if s['name'].startswith('Frame-bound selected LiDAR'))
        if step['status']!='PASS' or mounted['status']!='PASS' or geometry['status']!='PASS':raise ValueError('LIDAR_ACCEPTANCE_MISSING')
        for name,value in geometry['sources'].items():
            if digest(repo/name)!=value:raise ValueError('GEOMETRY_SOURCE_CHANGED')
        native=load(repo/'artifacts/photo-scan-review-20260927/native-scan-bundle.json')
        raw=repo/'artifacts/lidar-capture-20260927-1214/lidar-20260927T031354Z-323c99a6/raw.bin'
        nodes=repo/'artifacts/lidar-capture-20260927-1214/nodes.ndjson'
        if digest(raw)!=native['source']['raw_sha256'] or digest(nodes)!=native['source']['nodes_sha256']:raise ValueError('ORIGINAL_NATIVE_BYTES_CHANGED')
        save('lidar-acceptance.json',dict(status='PASS_SCOPED_SIM_AND_SAVED_SENSOR',**source_receipt(),geometry=geometry,
            actual_ui_scan=mounted['evidence'],actual_saved_sensor=step['evidence'],raw_bytes=raw.stat().st_size,raw_sha256=digest(raw),
            nodes_bytes=nodes.stat().st_size,nodes_sha256=digest(nodes),frames=len(native['frames']),
            saved_scan_scope='Historical native sensor coordinates, not new physical acquisition or verified world TF',
            real_live_and_world_registration='NOT_RUN_OR_UNIMPLEMENTED_NOT_PROMOTED',optical_model=False))
    if a.proof_only:return
    proof=load(root/'lidar-acceptance.json');summary=load(root/'summary.json')
    body=(root/'report.html').read_text(encoding='utf-8')
    heading='<h1>TwinPulse: 모델 장착 LiDAR · 실제 표면 검출 · 센서 검토</h1>'
    body=body.replace('<h1>TwinPulse: 장면 목적지 이동 · 안정된 Twin 화면</h1>',heading)
    section='<section><h2>이번 LiDAR 판정</h2><p>SIM 모델의 base_scan 좌표를 직접 읽어 높이 18.2cm·뒤쪽 3.2cm를 적용한다. 수평면과 실제 표시 가구의 삼각형 교차선으로 첫 반사점을 계산한다. 숨은 단순 충돌 상자를 센서 표면으로 대신 쓰지 않는다. 주행 충돌/속도/원시각/기한 정책은 변경하지 않았다. 기본은 반사점이며 선택 광선은 깊이 가림 없는 X-ray 보조 표시다.</p><p>실물·SIM·저장 점군은 같은 sensor-local 표시기를 사용한다. 정합되지 않은 실물 점군을 Twin 공간에 자동 중첩하지 않는다. 실제 로봇 OFF: 새 센서 수신·실물 주행·정합 PASS 아님. 현재 SIM은 180방향/8m의 기하 근사이며 광학·정확한 LDS 샘플링·다른 로봇의 센서 차폐는 미검증/미포함이다.</p><pre>'+html.escape(json.dumps(proof,ensure_ascii=False,indent=2))+'</pre><img src="ui-fresh-'+a.tag+'/saved-real-scan-shared.png" alt="최종 설치 앱의 실제 저장 점군 검토 창"><p><a href="implementation-notes.json">모든 빌드/실패·정확한 미검증 범위</a> · <a href="attempts.json">모든 원 실행</a> · <a href="lidar-acceptance.json">LiDAR 원본 SHA·인수</a></p></section>'
    body=body.replace(heading,heading+section)
    if (root/'media-review.json').exists():
        media=load(root/'media-review.json')
        if digest(root/media['output_video'])!=media['output_sha256']:raise ValueError('REVIEWED_DEMO_CHANGED')
        body=body.replace('</html>','<h2>게시용 SIM 발췌본</h2><p>녹화 session 시작과 첫 MP4표본의10.007초 차이를 반영했다.247개 원표본203–449만 포함하며 마지막표본의 유지시간은 미관측 움직임/최종도착 증거가 아니다. 이전 잘못 자른 local발췌본은 게시하지 않았다.</p><video controls preload="metadata" src="'+html.escape(media['output_video'])+'"></video><pre>'+html.escape(json.dumps(media,ensure_ascii=False,indent=2))+'</pre><p><a href="aggregate-first-failed/gate-result.json">첫 집계의 원 NOT_READY</a> · <a href="native-lifecycle.json">실제 native 종료/AX·도구 실패 기록</a></p></html>')
    if (root/'github-release.json').exists():
        uploaded=load(root/'github-release.json')
        body=body.replace('현재 변경의 Git commit/push/Release 업로드는 수행하지 않았다.','아래 GitHub 영수증의 기존 private 저장소에만 게시했다. 공개 전환은 하지 않았다.')
        body=body.replace('</html>','<h2>GitHub 게시 확인</h2><pre>'+html.escape(json.dumps(uploaded,ensure_ascii=False,indent=2))+'</pre></html>')
    with (root/'lidar-report.html').open('x',encoding='utf-8') as f:f.write(body)
    print(json.dumps(dict(report=str(root/'lidar-report.html'),gate=summary['gate'],lidar=proof['status'])))


if __name__=='__main__':main()
