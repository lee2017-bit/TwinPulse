# SPDX-License-Identifier: Apache-2.0
"""Evidence-backed local handoff; no App writes, devices or external uploads."""
import hashlib
import html
import json
import os
from pathlib import Path
import runpy
import sys

root=Path(__file__).resolve().parents[1];out=root/'outputs/environment-hybrid-20261024-01'
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):sys.path.insert(0,str(root/'packages'/name/'src'))
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_app.environment_evidence import verify_overlay_photos
from twinpulse_app.windows_package import verify_package
from twinpulse_app.release_contract import check_data_epoch

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
fresh=read(out/'ui03/result.json');cold=read(out/'cold01/result.json');qa=read(out/'usd-geometry02/result.json')
installation=read(out/'installation02.json');package=Path(installation['receipt']['exe']).parent
verified=verify_package(package);runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
failures=[];checks=[]
def require(name,condition):
    checks.append(dict(name=name,status='PASS' if condition else 'FAIL'))
    if not condition:failures.append(name)

require('Fresh ordinary UI journey',fresh['status']=='PASS_SCOPED' and fresh.get('exit')=='WINDOW_CLOSED' and len(fresh['steps'])==9)
require('Cold ordinary UI journey',cold['status']=='PASS_SCOPED' and cold.get('exit')=='WINDOW_CLOSED')
require('Same installed build',all(r['versions']['engine']['release_id']==verified['build_id'] for r in (fresh,cold)))
require('No retained HTTP or renderer errors in final journeys',not any(r['errors'] or any(p['status']>=400 for p in r['responses']) for r in (fresh,cold)))
require('Focused final tests',read(out/'focused06/result.json')['status']=='PASS')
require('Real OpenUSD geometry',qa['status']=='PASS')
project=runtime/'projects'/fresh['project_id']/'project.json';original=SiteDraftRecord.from_dict(read(project)['site_draft'])
history=SceneChangeHistory.from_dict(read(project.with_suffix('.scene-changes.json')),original,fresh['project_id'])
_,site=history.replay(original);environment=site.scene.environment
require('Original source meshes and provenance unchanged',environment['meshes']==original.site.scene.environment['meshes'] and environment['source_sha256']==qa['source_sha256'])
require('One added estimate remains',len(environment['overlays'])==1 and environment['overlays'][0]['evidence']['alignment_verified'] is False)
require('Five exact add/move/Undo/remove/Undo commits',len(history.operations)==5 and len(fresh['edits'])==5)
require('Cold scene is the last committed revision',any(r.get('body',{}).get('scene_revision')==site.scene.revision for r in cold['responses']))
archived=list((project.parent/'inputs').rglob('environment-source.bin'))
require('Archived original USD SHA',len(archived)==1 and sha(archived[0])==qa['source_sha256'])
require('User original USD untouched',sha(Path('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd'))==qa['source_sha256'])
verify_overlay_photos(project.parent/'environment-imports',environment)
require('Reference photo original SHA',sha(Path('C:/Users/jaewo/Downloads/KakaoTalk_20261023_001642352.jpg'))==environment['overlays'][0]['evidence']['sha256'])
scan=fresh['scan']['scan'];point=min((p for p in scan['points'] if p[0]>0),key=lambda p:abs(p[1]));pose=scan['sensor_xy_yaw_world']
expected=qa['obstacle_xy'][0]-.35/2-pose[0]
require('Actual composed sensor first hit',scan['source']=='isaac_usd_surface_rays' and abs(pose[2])<1e-6 and abs(point[1])<1e-6 and abs(point[0]-expected)<.0002)
require('Finite SIM completion only',fresh['motion']['kind']=='sim' and fresh['motion']['command']['state']=='COMPLETED')
# Retain original Stop response and fresh engine epoch observation separately.
stop=next(r for r in cold['responses'] if r.get('action')=='stop')
request=stop.get('request',{});robot=next(r for r in stop['body']['robots'] if r['robot_id']==request.get('robot_id'))
require('Original same-operation Stop request and response',stop['status']==200 and robot['operation_id']==cold['cold_scan']['operation_id'] and
    robot['connection_epoch']==request['connection_epoch'] and robot['motion_epoch']!=request['motion_epoch'])
require('Stop new epoch observed by engine',any(any(r['robot_id']==robot['robot_id'] and r['operation_id']==robot['operation_id'] and
    r['applied_motion_epoch']==robot['motion_epoch'] and r['control_state']=='PAUSED' for r in row.get('body',{}).get('robots',[])) for row in cold['responses']))
require('OFF clears scan',any(any(r['robot_id']==robot['robot_id'] and r['lidar_state']=='OFF' and r['scan'] is None for r in row.get('body',{}).get('robots',[])) for row in cold['responses']))
require('No cold restored connection',cold['no_restored_connection'] not in {'CONNECTED','CONNECTING'})
marker=read(runtime/'data-compatibility.json');require('Sticky feature barrier',marker['schema']=='twinpulse-runtime-data-1.1' and 'environment-static-1.1' in marker['required_capabilities'] and check_data_epoch(runtime)==1)
old=Path('C:/Users/jaewo/AppData/Local/TwinPulse/installed/releases/20261024T072244Z-74db6d9e9868/_internal/resources/packages/twinpulse_app/src/twinpulse_app/release_contract.py')
old_error=None
try:runpy.run_path(str(old))['check_data_epoch'](runtime)
except ValueError as error:old_error=str(error)
require('Old reader rejects new marker without changing it',old_error=='DATA_COMPATIBILITY_RECORD_INVALID')
source_manifest=read(package/'_internal/resources/source-manifest.json');changed=[]
for name,digest in source_manifest.items():
    if name.startswith(('packages/','extensions/','apps/twinpulse-web/src/','scripts/twinpulse_fleet_runtime')) and (root/name).is_file() and sha(root/name)!=digest:changed.append(name)
require('Installed product source still current',not changed)
for label,launch in [('03',fresh['versions']['engine']['launch_id']),('04',cold['versions']['engine']['launch_id'])]:
    folder=out/('runtime-copies'+label)/launch
    exits=read(folder/'owned-exit-observations.json');copy=read(folder/'copy-receipt.json')
    require('Normal root exits '+label,exits['evidence_complete'] and all(v['return_code']==0 and v['root_disposition']=='EXITED_DURING_GRACE' for v in exits['roles'].values()))
    require('Frozen runtime logs '+label,all(row['status']=='EXACT_COPY' or row['name']=='engine-liveness-observations.json' for row in copy['files']))
require('Final launcher lock absent',not (runtime/'launcher.lock').exists())
result=dict(status='PASS_HYBRID_SCOPE' if not failures else 'FAIL',checks=checks,failures=failures,build=verified,
    project_id=fresh['project_id'],scene_revision=site.scene.revision,first_hit_m=point[0],expected_first_hit_m=expected,
    source_sha256=qa['source_sha256'],photo_sha256=environment['overlays'][0]['evidence']['sha256'],old_reader_error=old_error,
    previous_harness_failures=['ui01: old Manage accessibility label','ui02: registration details not opened'],
    scope_exclusions=['automatic image detection','metric photo placement','LiDAR-to-room localization','physical authority','full submission demo'],
    physical_actions=0,external_uploads=0)
(out/'acceptance01.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
rows=''.join('<tr><td>'+html.escape(c['name'])+'</td><td>'+c['status']+'</td></tr>' for c in checks)
page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse hybrid scene</title>
<style>body{font:17px/1.6 system-ui;max-width:1080px;margin:40px auto;padding:0 24px;color:#20313f}img,video{width:100%;border-radius:8px}td{padding:5px 12px;border-bottom:1px solid #ddd}small{overflow-wrap:anywhere}h2{margin-top:40px}</style>
<h1>RoomPlan + 추가 장애물: 혼합 장면 구현</h1><p>원본 USD와 사진 원문을 보존하고 기존 사진용 카탈로그의 물체를 추가·이동·삭제·Undo·재열기합니다. 사진은 로컬 참조이며 위치·치수는 사용자가 확인한 추정값입니다. 자동 사진 검출·세계 정합·실물 주행 검증 완료는 아닙니다.</p>'''
page+='<p>한정 인수: <strong>'+result['status']+'</strong> · '+html.escape(verified['build_id'])+'</p>'
page+='<p>검수용 새 프로젝트: '+html.escape(fresh['project_id'])+' · 기존 실물 프로젝트는 변경하지 않았습니다.</p>'
page+='<h2>확대된 실제 설치 앱 화면</h2><img src="cold01/05-enlarged-burger-lidar.png" alt="Current installed Burger and LiDAR">'
page+='<h2>검수 녹화</h2><p>실제 Electron renderer·이벤트 커서 표시입니다. 실물 카메라나 완성된 제출 영상이 아닙니다. 좌표는 재현 시험용이며 실제 사진 위치 정합을 주장하지 않습니다.</p><video controls preload="metadata" src="ui03/recording/app-screen.mp4"></video>'
page+='<h2>검증과 한계</h2><p>Python66개(1개 조건부 skip), UI40개, TypeScript build 검사. 실제 스캔 높이0.182m에서 앞 반사점 '+str(point[0])+'m, 모델 프레임을 포함한 예상 '+str(round(expected,6))+'m. 낮은 케이블은 라이다 반사점에 꾸며 넣지 않고 경로 금지 영역을 유지합니다.</p><table>'+rows+'</table>'
page+='<p>보존한 실패: 초기 Python 모듈 경로/구문·테스트 TypeScript 옵션·USD SDK 초기화 실패와 ui01/02 검수 스크립트 선택자 실패. 제품·장치 실패와 구분하며 원문을 덮지 않았습니다.</p>'
page+='<p>다음 핵심 작업: USD를 고정한 사진 물체 후보 제안 → 위치/관계 검토 → 안정 구조 기반 LiDAR 정합 검토. 영상·COLMAP·점 추적·새 iOS 앱은 이번에 도입하지 않았습니다.</p>'
page+='<p><a href="acceptance01.json">정확 인수 결과</a> · <a href="ui03/result.json">첫 UI 원문</a> · <a href="cold01/result.json">재열기 원문</a> · <a href="focused06/result.json">집중 검사</a></p></html>'
(out/'report.html').write_text(page,encoding='utf-8');print(json.dumps(dict(status=result['status'],failures=failures,build_id=verified['build_id'])))
raise SystemExit(1 if failures else 0)
