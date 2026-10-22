# SPDX-License-Identifier: Apache-2.0
"""Bind the selected SIM demo and future repair plan to actual saved UI evidence."""
from decimal import Decimal
from hashlib import sha256
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/'outputs/sim-zoom-demo-20261021'


def main():
    session = json.loads((ROOT/'take01/session.json').read_text(encoding='utf-8'))
    events = {e['name']: e for e in session['events']}
    at = lambda name: events[name]['at']
    snapshots = []
    for line in (ROOT/'take01/fleet-observations.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        robots = (row['response'].get('fleet') or row['response']).get('robots', [])
        for robot in robots:
            if robot['label'] == 'Scout':
                snapshots.append((row['at'], robot))
    turn_request = events['SCOUT_CHAT_TURN_COMPLETE']['evidence']['robot']['command']['request_id']
    goal_request = events['SCOUT_GOAL_ARRIVED']['evidence']['robot']['command']['request_id']
    turn_complete = next(t for t, r in snapshots if (r.get('command') or {}).get('request_id') == turn_request
                         and r['command']['state'] == 'COMPLETED')
    goal_arrival = next(t for t, r in snapshots if (r.get('command') or {}).get('request_id') == goal_request
                        and r['command']['state'] == 'ARRIVED')
    segments = []
    def add(title, start, end, duration):
        segments.append(dict(title=title, start_at=start, end_at=end, duration_s=duration))
    frame_clock = json.loads((ROOT/'take01/frame-times.json').read_text(encoding='utf-8'))
    home_frame = next(f for f in frame_clock['frames'] if f['at'] >= at('HOME_READY_BEFORE_NEW_CHAT'))
    add('TwinPulse | Text + photo to a Digital Twin', home_frame['at'], home_frame['at']+1000, 1)
    add('1. Describe a room in chat', at('TEXT_INPUT_VISIBLE'), at('TEXT_INPUT_VISIBLE')+4300, 4)
    add('Generate a text-based Twin', at('TEXT_CREATE_TWIN')-400, at('TEXT_TWIN_GENERATED'), 3)
    add('Estimated text-based room', at('TEXT_TWIN_GENERATED'), at('TEXT_TWIN_GENERATED')+3400, 3)
    add('2. Attach a photo | Request coarse major obstacles', at('PHOTO02_NEW_CHAT_BEFORE_ATTACH'), at('PHOTO02_CREATE_TWIN'), 5)
    add('Generate the photo-based estimate', at('PHOTO02_CREATE_TWIN')-300, at('PHOTO02_TWIN_GENERATED'), 4)
    add('Photo-based coarse furniture layout', at('PHOTO02_TWIN_GENERATED'), at('PHOTO02_TWIN_GENERATED')+4000, 4)
    add('3. Add a TurtleBot3 SIM robot named Scout', at('SCOUT_REGISTRATION_START'), at('SCOUT_REGISTRATION_RECEIPT'), 6)
    add('Robot added | Registration saved in chat', at('SCOUT_REGISTRATION_RECEIPT'), at('SCOUT_CONNECT_PREPARE_START'), 3)
    add('Explicit Connect and Prepare', at('SCOUT_CONNECT_PREPARE_START'), at('SCOUT_READY_VISIBLE'), 3)
    add('4. Manual forward, reverse, left and right | LiDAR rays', at('SCOUT_MANUAL_AND_LIDAR_START'), at('SCOUT_MANUAL_COMPLETE'), 4)
    add('5. Chat command | One full turn and LiDAR scan', at('SCOUT_CHAT_TURN_INPUT_VISIBLE'), at('SCOUT_CHAT_TURN_ENTER'), 3.5)
    add('One complete SIM rotation with live scan', at('SCOUT_CHAT_TURN_ENTER'), turn_complete+900, 6)
    add('6. Type a scene destination | Go to the nearest bed', at('SCOUT_GOAL_INPUT_VISIBLE'), at('SCOUT_GOAL_ENTER'), 3.5)
    add('SIM destination movement and arrival', at('SCOUT_GOAL_ENTER'), goal_arrival+1100, 4)
    add('Stop and LiDAR OFF | No physical robot operated', at('SCOUT_STOP_AND_SENSOR_OFF_START'), at('SCOUT_STOPPED_SENSOR_OFF')+100, 3)
    (ROOT/'edit-list.json').write_text(json.dumps(dict(recording='take01',segments=segments,
        classification='SELECTED_EDITED_SIM_DEMONSTRATION_NOT_FULL_ACCEPTANCE',
        excludes_preserved_detailed_partial=True, excludes_initial_wall_placement=True), indent=2), encoding='utf-8')
    budget = json.loads((ROOT/'budget-final.json').read_text(encoding='utf-8'))
    stopped = events['SCOUT_STOPPED_SENSOR_OFF']['evidence']['robot']
    final = events['SIM_DISCONNECTED_AFTER_RECORDING']['evidence']['robot']
    turns = events['SCOUT_CHAT_TURN_COMPLETE']['evidence']['robot']
    origin_yaw = events['SCOUT_CHAT_TURN_ENTER']['evidence']['before']['position_m'][2]
    summary = dict(status='SCOPED_SIM_DEMO_RECORDED_NOT_PHYSICAL_ACCEPTANCE',
        identity=session['identity'],installed_product_changes=0,physical_connections=0,uploaded=False,
        inputs=dict(photo='C:/Projects/TwinPulse/ITM0018.jpg',photo_sha256=sha256(Path('C:/Projects/TwinPulse/ITM0018.jpg').read_bytes()).hexdigest()),
        text=events['TEXT_TWIN_GENERATED']['evidence'],
        detailed_photo=events['PHOTO01_PARTIAL_RETAINED_NOT_MOTION_PASS']['evidence'],
        coarse_photo=events['PHOTO02_TWIN_GENERATED']['evidence'],
        initial_sim_placement=events['INITIAL_SIM_PLACEMENT_RETAINED']['evidence'],
        robot_id=stopped['robot_id'],operation_id=stopped['operation_id'],
        manual=events['SCOUT_MANUAL_COMPLETE']['evidence'],
        chat_full_turn=dict(request_id=turn_request,state=turns['command']['state'],
                            yaw_delta_rad=turns['pose']['position_m'][2]-origin_yaw),
        destination=events['SCOUT_GOAL_ARRIVED']['evidence']['robot']['command'],
        stopped=dict(control_state=stopped['control_state'],lidar_state=stopped['lidar_state'],
                     motion_epoch=stopped['motion_epoch'],applied_motion_epoch=stopped['applied_motion_epoch'],
                     overlay_count=events['SCOUT_STOPPED_SENSOR_OFF']['evidence']['overlay_count']),
        disconnected=dict(connection_state=final['connection_state'],lidar_state=final['lidar_state']),
        page_closed=events['APP_EXIT_CLICKED']['evidence']['page_closed'],
        errors=session['errors'],harness=events['DEMO_HARNESS_NOTES']['evidence'],
        new_http=budget['new_http'],new_estimated_usd=budget['new_estimated_usd'],
        additional_50_total=budget['protected_additional_50_total'],
        additional_50_remaining=str(Decimal('50')-Decimal(budget['protected_additional_50_total'])),
        interpretation='Coarse library proxy estimate. Full photo quality and physical world alignment/driving remain unqualified. Initial detailed partial and old-position registration remain unchanged.')
    (ROOT/'session-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    report = ROOT/'report.html'
    body = report.read_text(encoding='utf-8').split('<!-- actual-summary -->')[0]
    details = {
        'installed_release':session['identity'].get('engine',{}),
        'text_project':summary['text']['project_id'],
        'first_detailed_photo_project':summary['detailed_photo']['project_id'],
        'coarse_photo_project':summary['coarse_photo']['project_id'],
        'robot_id':summary['robot_id'],'operation_id':summary['operation_id'],
        'chat_turn':summary['chat_full_turn'],'destination':summary['destination'],
        'stopped':summary['stopped'],'page_closed':summary['page_closed'],
        'new_http':summary['new_http'],'new_estimated_usd':summary['new_estimated_usd'],
        'additional_50_remaining':summary['additional_50_remaining'],
    }
    body += '<!-- actual-summary --><h2>실제 촬영 결과와 모든 시도</h2>'
    body += '<p>텍스트 새 생성 1회와 같은 원사진 새 생성 2회를 수행했습니다. 첫 상세 사진 초안은 26개 중22개 표시/4개 pending과 GET abort4개로 보존했습니다. 새로 명시한 거친 주요 가구 요청은5개를 표시했고 자동 repair1회가 실제 기록됐습니다. 이는 원 상세 사진 회귀 통과나 사진 품질 완전 PASS가 아닙니다. 책상·책장 표현/배치도 실측 복원이 아닌 추정입니다.</p>'
    body += '<p>초기 TurtleBot3 등록의 X=1.75가 생성된 방의 우측 벽 위치여서 가려졌습니다. 이동하지 않고 Disconnect했고 정의/이력을 그대로 보존했습니다. 장면의 빈 앞바닥 좌표를 확인한 뒤 새 Scout를 명시 등록했습니다. 편집 영상은 이 정상 가시 위치 등록만 선택하며, 실패를 없었던 것으로 처리하거나 한 번의 무결점 전체 인수라고 주장하지 않습니다. 생성 대기 중 위치를 제품 코드에 하드코딩하거나 물체를 삭제·완화하지 않았습니다.</p>'
    body += '<p>Scout의 SIM 전진 약30.3cm/후진22.8cm/좌우회전, 채팅 한바퀴, 패널 침대 도착, Stop의 새 applied epoch, LiDAR OFF/overlay0, Disconnect·Exit를 관측했습니다. strict 물리 부하/제동/주행 시험이 아니며 반복 현장 목격 질문이나 새 실물 접속은 없습니다. 촬영기의 Continue/Create 및 ON/STREAMING 이름 가정 두 건은 실제 화면을 재확인해 복구했으며 제품 오류로 합산하지 않습니다.</p>'
    body += '<pre>'+html.escape(json.dumps(details,ensure_ascii=False,indent=2))+'</pre>'
    body += '<p><a href="take01/app-screen.mp4">편집 전 실제 renderer 원 녹화</a> · <a href="take01/frame-times.json">원 프레임 시각</a> · <a href="take01/fleet-http-receipts.json">SIM 요청/상태 원 영수증</a> · <a href="take01/session.json">모든 촬영 이벤트/오류</a></p>'
    report.write_text(body,encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('status','robot_id','operation_id','new_http','new_estimated_usd','additional_50_remaining')},ensure_ascii=False))


if __name__ == '__main__':
    main()
