# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only installed evidence/report aggregation, never a product caller."""
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
        with (root/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    if not a.report_only:
        save('implementation-notes.json',dict(scope='Registration menu history/slow full demo; hardware OFF',
            contract='Same-project/conversation persistent definition outbox consumed on chat observation only, not under drive/Stop/telemetry locks. Explicit menu action, built-in model/name/start pose and IDs. No legacy history invented; no authority restore.',
            source='Existing fleet registration/scene context and conversation message/event persistence; no new endpoint or direct UI state injection.',
            test_recovery='Initial patch referenced a nonexistent helper filename and was atomically rejected before any of that patch applied. Correct path used; no product test PASS inferred from tool success.',
            historical_risk='v551 saved-scene60GB GPU allocation/OOM/native crash root remains UNKNOWN. Its exact originals stay in the prior report; this new acceptance is not a cause repair/no-recurrence guarantee.',
            not_run=['Physical robot','World alignment','Explorer double click','OS clipboard','Actual OS DPI','Another PC','Full native generation/control']))
        run=subprocess.run([sys.executable,str(Path(__file__).with_name('finalize_scene_robot_ux.py')),str(root),'--tag','01'])
        if run.returncode:raise ValueError('Current whole acceptance gate failed')
        demo=load('recording-demo01/result.json');cold=load('recording-demo-cold01/result.json');media=load('media-review.json')
        if demo['status']!='PASS_SEPARATE_FRESH_DEMO' or cold['status']!='PASS_CHAT_REGISTRATION_COLD':raise ValueError('Required actual demo/restore failed')
        if demo['registration_event']!=cold['event'] or cold['source_sha256']!=digest('recording-demo01/result.json'):raise ValueError('Cold receipt not bound to original event')
        for row in (demo,cold):
            if row['identity']['engine']['release_id']!=source_receipt()['release_id']:raise ValueError('Wrong demo installation')
        if media['output_sha256']!=digest(media['output_video']):raise ValueError('Reviewed full recording changed')
        save('requested-acceptance.json',dict(status='PASS_SCOPED_PERSISTENT_MENU_HISTORY_AND_SLOW_FULL_DEMO',**source_receipt(),
            registration_event=demo['registration_event'],cold_original_event_exact=True,cold_original_result_sha256=cold['source_sha256'],
            full_demo_project=demo['project'],full_demo_operation=demo['operation_id'],media=media,physical='NOT_RUN_ROBOT_OFF'))
        return
    proof=load('requested-acceptance.json');body=(root/'report.html').read_text(encoding='utf-8')
    body=body.replace('<h1>TwinPulse: 장면 목적지 이동 · 안정된 Twin 화면</h1>','<h1>TwinPulse 로봇 추가 이력과 천천히 보여주는 전체 데모</h1>')
    body=body.replace('연결점은 실제 USD 모델 bounds를 투영하고 이름 배치와 분리한다.','Twin의 원은 없고 이름은 모델 하단+2px에 붙는다. 메뉴 등록 이력과 현재 연결·조종 상태는 서로 구분한다.')
    extra='<h2>이번 요청의 직접 판정</h2><p>Simulation only는 환경 생성 모드이며 로봇 추가 요청이 아니다. 실제 Manage→Add SIM robot의 등록 영수증을 같은 프로젝트/채팅에 한번만 기록한다. 이름·내장Burger모델·시작 좌표·robot/request/Twin/채팅ID를 보존하며 메뉴 작업을 사용자가 입력한 문장으로 위장하지 않는다. 등록만으로 접속·실제 표시·이동했다고 말하지 않는다. 실제 새 생성과 메뉴 추가·연결·조종을 촬영했고 같은 데모 프로젝트의 앱 재시작 후 원event/메시지를 UI로 다시 확인했다. 권한 자동복원0이다.</p><pre>'+html.escape(json.dumps(proof,ensure_ascii=False,indent=2))+'</pre>'
    for name in ('recording-demo01/registration-form.png','recording-demo01/registration-chat-receipt.png','recording-demo-cold01/restored-registration.png'):
        extra+='<img src="'+name+'" alt="실제 설치 앱 '+html.escape(name)+'">'
    extra+='<h2>처음부터 전체 영상</h2><p>이름은 천천히 실제 키 입력하고 모델/좌표/추가/채팅 결과를 원시간으로 유지했다. 배속·보간·처음 자르기0. 실제 renderer 표본이며 native splash/Explorer/실물촬영은 아니다. 원시각/packet대조·개인정보 검토는 아래 media-review에 있다.</p><video controls preload="metadata" src="'+proof['media']['output_video']+'"></video>'
    extra+='<h2>원 실패와 정확한 범위</h2><p>원 v551 GPU OOM/native crash의 정확 원문·실패는 <a href="../robot-undername-off-20261019/requested-report.html">이전 보고서</a>에 보존한다. 이 수정은 그 비정상 할당의 근본원인을 해결한 것이 아니다. 새 모델 선택기나 자연어 로봇 추가를 구현·검증한 것도 아니다. 내장 Burger 등록 메뉴의 이력과 설명용 녹화를 개선했다. 모든 새 시도는 attempts.json에 남겼으며 replay/unit를 실제 UI/실물 성적에 합치지 않았다.</p>'
    if (root/'github-release.json').exists():
        body=body.replace('현재 변경의 Git commit/push/Release 업로드는 수행하지 않았다.','기존 private 저장소에만 게시했고 아래 재다운로드 SHA 영수증을 확인했다.')
        extra+='<h2>게시 영수증</h2><pre>'+html.escape(json.dumps(load('github-release.json'),ensure_ascii=False,indent=2))+'</pre>'
    with (root/'requested-report.html').open('x',encoding='utf-8') as f:f.write(body.replace('</html>',extra+'</html>'))
    print(json.dumps(dict(report=str(root/'requested-report.html'),status=proof['status'])))


if __name__=='__main__':main()
