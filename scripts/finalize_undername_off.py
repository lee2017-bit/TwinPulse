# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Original installed evidence aggregator only. No App/model/robot/Git writes."""
import argparse
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess
import sys
from verify_robot_lineage_offline import source_receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--report-only',action='store_true');a=p.parse_args();root=a.root.resolve()
    load=lambda name:json.loads((root/name).read_text(encoding='utf-8-sig'))
    digest=lambda name:sha256((root/name).read_bytes()).hexdigest()
    def save(name,value):
        with (root/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    if not a.report_only:
        save('implementation-notes.json',dict(scope='SIM/UI only; hardware OFF',notes=(root/'implementation-notes.txt').read_text(encoding='utf-8'),
            prior_wrong_success_basis='v550 marker-to-metadata proximity and nonoverlap did not prove name-to-body distance or sensor-Off visual removal. Its recorded tests stay unchanged; user-visible acceptance was incomplete.',
            recorder_legacy_wording='ATTACHED_RECORDING may contain the legacy NOT_RUN_GEOMETRY_CAPTURE_FAILED string. It is not a claim that graphics capture was attempted/failed in this session. Actual native lifecycle receipt is authoritative.',
            not_run=['Physical robot','Sensor-to-world alignment','Explorer double click','OS clipboard','Actual OS DPI','Another PC','Native full journey']))
        code=subprocess.run([sys.executable,str(Path(__file__).with_name('finalize_scene_robot_ux.py')),str(root),'--tag','01','--lineage-tag','02']).returncode
        if code:raise ValueError('Whole installed acceptance failed; preserve originals')
        original=load('failure-lineage01-review.json');negative=load('evidence-manifest.json')
        negative['evidence']=[dict(row,path='lineage-01/result.json',sha256=digest('lineage-01/result.json')) if row['role']=='lineage' else row for row in negative['evidence']]
        save('negative-original-lineage01-manifest.json',negative)
        subprocess.run([sys.executable,str(Path(__file__).with_name('verify_robot_focus_gate.py')),'--manifest',str(root/'negative-original-lineage01-manifest.json'),'--output',str(root/'negative-original-lineage01-result.json')],capture_output=True,check=False)
        rejected=load('negative-original-lineage01-result.json')
        if rejected['status']!='NOT_READY' or 'RUN_NOT_PASS:lineage' not in rejected['issues']:raise ValueError('Original failed lineage was not rejected')
        save('native-failure-review.json',original)
        fresh=load('ui-fresh-01/result.json');demo=load('recording-demo03/result.json');media=load('media-review.json')
        if demo['status']!='PASS_SEPARATE_FRESH_DEMO' or digest(media['output_video'])!=media['output_sha256']:raise ValueError('Full fresh demo missing or changed')
        samples=fresh['display_samples'];off=next(s['evidence']['off'] for s in fresh['steps'] if s['name']=='LiDAR Off pauses but retains connection; On restarts sensor')
        proof=dict(status='PASS_SCOPED_NO_RING_UNDERNAME_SENSOR_OFF_FULL_DEMO',**source_receipt(),off=off,
            maximum_bottom_error_px=max(r['label_under_body_error_px'] for r in samples),maximum_center_error_px=max(r['label_horizontal_error_px'] for r in samples),
            maximum_origin_marker_count=max(r['origin_marker_count'] for r in samples),demo_project=demo['project'],demo_operation=demo['operation_id'],
            demo_input_sha256=demo['input_sha256'],demo_identity=demo['identity'],physical='NOT_RUN_ROBOT_OFF')
        if proof['maximum_origin_marker_count'] or max(proof['maximum_bottom_error_px'],proof['maximum_center_error_px'])>1:raise ValueError('Detached name or ring')
        save('requested-acceptance.json',proof)
        return
    proof=load('requested-acceptance.json');media=load('media-review.json');body=(root/'report.html').read_text(encoding='utf-8')
    body=body.replace('<h1>TwinPulse: 장면 목적지 이동 · 안정된 Twin 화면</h1>','<h1>TwinPulse 이름 위치와 LiDAR Off 및 처음부터 데모 검증</h1>')
    body=body.replace('연결점은 실제 USD 모델 bounds를 투영하고 이름 배치와 분리한다.','Twin 위 초록 원은 제거했다. 이름은 현재 모델 bounds 하단+2px에 중앙 정렬하며 이름끼리 겹쳐도 피하거나 숨기지 않는다.')
    extra='<h2>사용자 요청의 직접 판정</h2><p>이전 메타데이터 원점 비교만으로 이름 근접성을 통과시킨 검증 공백을 정정했다. 연결 상태는 클릭 후 하단에 표시한다. 센서 Off와 화면만 숨기기를 구분하고 현재 연결/동작 epoch가 일치하는 STREAMING 자료만 표시한다. 실제 sensor OFF에는 점/레이가 없음을 검사했다.</p><pre>'+html.escape(json.dumps(proof,ensure_ascii=False,indent=2))+'</pre>'
    extra+='<h2>원 GPU 실패와 범위</h2><p>저장 Twin 표시 중60GB AccelStruct GPU 할당/OOM→device lost→native crash가1회 발생했다. 원결과·Kit/엔진 로그를 보존했고 동일 저장 장면/새 연결/90도/scan/수정·Undo 전체여정02를 재실행했다. 새 definition 이름은 이미 남은 등록과 구분한 ID 차이이며 목표/각도/기한/기하는 유지했다. 새 PASS는 거대한 할당의 근본원인 해결이나 무재발 보장이 아니다. 원FAIL을 넣은 gate는 실제로 거절된다.</p><pre>'+html.escape(json.dumps(load('native-failure-review.json'),ensure_ascii=False,indent=2))+'</pre>'
    extra+='<h2>별도 데모 첫 시도 실패</h2><p>recording-demo01은 실제 생성 뒤 시험기가 로봇 선택으로 이미 켜진 Control view를 다시 클릭해 꺼버렸다. 실제 DOM의 aria-pressed=false와 선택 시 자동 열기 코드를 대조했다. 숨겨진 패드를 통과시키지 않았고 원 FAIL과 영상을 보존했다. 현재 상태를 보고 켜는 시험기 수정 후02를 Home부터 별도 새 생성했다. 일반 화면1426×787 CSS/보고된DPR1.25에서 수행했으며 OS DPI를 변경한 시험은 아니다.</p><p><a href="recording-demo01/result.json">원 FAIL</a> · <a href="recording-demo01/layout-diagnosis.json">원 화면 상태</a> · <a href="recording-demo01/app-screen.mp4">원 부분 녹화</a></p>'
    extra+='<p>demo02는 모든 기능 여정을 끝냈지만 수동 입력 해제와 겹친409 요청의 exact ID/관찰 순서를 수동 영상 기록기가 저장하지 않았다. 기능 PASS 원결과는 보존하고 최종 게시 판정에서 제외했다. 읽기 관찰기에 request/response 순서·Stop 응답·applied 새epoch를 추가한 뒤03을 Home부터 다시 생성했다. 원정지 보호·입력기한/제품소스는 바꾸지 않았다.03에서는 모든 오류를 거절하되 정확한 Stop 겹침과 engine PAUSED/새epoch가 확인된 이전 입력 거절만 별도 기록한다. 이 기록은 서버 내부의 유일 원인 추론이 아니다.</p>'
    for name in ('home-demo03/home-before-new-chat.png','ui-fresh-01/name-only-body-selection.png','ui-fresh-01/lidar-sensor-off-no-overlay.png'):
        extra+='<img src="'+name+'" alt="실제 설치 앱 '+html.escape(name)+'">'
    extra+='<h2>고정 크기 처음부터 끝까지 데모</h2><p>회귀시험의 창 크기 변경과 분리한 별도 fresh 생성이다. Home→New chat→영문 요청→실제 모델 생성→등록/Connect/Prepare→수동 조종→센서 Off/On→채팅360°→침대/의자 도착→Stop/Off. 처음을 자르거나 생성 결과를 재사용하지 않았다. 실제 renderer 표본 녹화이며 native 시작 splash/물리 로봇 영상은 아니다.</p><video controls preload="metadata" src="'+media['output_video']+'"></video><pre>'+html.escape(json.dumps(media,ensure_ascii=False,indent=2))+'</pre>'
    if (root/'github-release.json').exists():
        body=body.replace('현재 변경의 Git commit/push/Release 업로드는 수행하지 않았다.','기존 private 저장소에만 게시했고 아래 재다운로드 SHA 영수증을 확인했다.')
        extra+='<h2>GitHub 게시 영수증</h2><pre>'+html.escape(json.dumps(load('github-release.json'),ensure_ascii=False,indent=2))+'</pre>'
    with (root/'requested-report.html').open('x',encoding='utf-8') as f:f.write(body.replace('</html>',extra+'</html>'))
    print(json.dumps(dict(report=str(root/'requested-report.html'),status=proof['status'])))


if __name__=='__main__':main()
