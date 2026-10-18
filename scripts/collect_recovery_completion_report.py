"""Build one local evidence index; no App, provider or robot calls."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.output.resolve()
    def read(name):
        path=root/name
        return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    def esc(value):return html.escape(str(value))
    def link(name,title=None):return '<a href="'+esc(name)+'">'+esc(title or name)+'</a>'
    def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
    gate=read('gate-result.json');install=read('installation-final.json');budget=read('budget-final.json')
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 복구·SIM 전체 사이클 인수</title>',
        '<style>body{max-width:1200px;margin:32px auto;padding:0 22px;font:16px/1.65 system-ui;color:#182b38;background:#f5f7f9}h1,h2{line-height:1.3}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #ccd5de;padding:7px;text-align:left;overflow-wrap:anywhere}img,video{max-width:100%;background:#101a20}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e8edf3;padding:12px}small{color:#506270}section{margin:32px 0}a{color:#005a82}</style>',
        '<h1>TwinPulse 복구·SIM 전체 사이클 인수</h1>',
        '<p>'+esc(datetime.now(timezone.utc).isoformat())+' · 로봇 OFF · 실제 로봇 접속/센서/모터 0</p>',
        '<h2>판정</h2><p>소프트웨어: <strong>'+esc(gate.get('software_status','UNVERIFIED'))+'</strong> · 실물 준비 종합: <strong>'+esc(gate.get('status','UNVERIFIED'))+'</strong>.</p>',
        '<p>같은 설치 Electron Test BrowserWindow와 실제 Isaac에서 클릭한 범위만 인수했다. SIM은 USD kinematic 이동·AABB ray 관측이며, 실제 바퀴·PhysX 동역학·물리 LiDAR·현장 정합을 증명하지 않는다. Explorer 더블클릭, OS 붙여넣기, 실제 Windows DPI 및 일반 모드 전체 native 조종은 NOT_RUN이다. 아래 일반 Start는 동일 .cmd를 실행 도구로 호출했다.</p>',
        '<pre>'+esc(json.dumps({k:install.get(k) for k in ['release_id','source_manifest_sha256','files','mismatches']},ensure_ascii=False,indent=2))+'</pre>',
        '<p>'+link('evidence-manifest.json','9역할 SHA 결속 인수 자료')+' · '+link('gate-result.json','판정 원문')+'</p>',
        '<h2>판정 범위</h2>'+table(['축','판정','근거 / 한계'],[
            ['기능', 'PASS_SCOPED_SIM_AND_PC','같은 설치 실제 생성·2SIM·수동/채팅90°·360scan·정지·장애물/후진·반출'],
            ['배치/사진 품질','이번 사진 재생성 NOT_RUN','최종 새 생성은 텍스트3가구 추정 장면이다. 거실 catalogue 표현 정정은 사진 품질 PASS가 아니다.'],
            ['복원/기록','PASS_SCOPED','수정→저장→Undo새revision, cold권한복원0, 원실패 cleanup=false/CANCELLED 및 SHA 보존'],
            ['응답성','MEASURED_SCOPED','60초hold118관측/59.677초·matching display117/최대527ms, 정상Start41.194s/재시작58.316s. 향후 무정체 보장 아님.'],
            ['진단 UI','PASS_SCOPED / 표전체 unclipped 미인수','선택segment SHA/310callback/28job·필터/커서·현재/과거 분리. 일부 표제/행 라벨 잘림은 제한이다.'],
            ['field 영속화','구현+저장자료/보조시험 PASS','실제 Pi 장치의 새 fsync/부하 재인수는 NOT_RUN'],
            ['실물','NOT_READY / NOT_RUN','원 주행전 실패 유지, 미해석 protocol·Pi 부하·실측 정지 검증 필요']]),
        '<h2>빌드 시도</h2>'+table(['후보','source SHA','ZIP SHA','판정'],[
            ['20261018T160400Z-a4a8eee37172','a4a8eee371727b68a742600245505b0a8a6aefe22d00c38f9a602c943e040282','18ac7ee445d723ebab1ae74c1f0ed42cb04726edaa7f9fe6f42358c6822465e9','fresh PASS / 첫cold 실제 FAIL, 재현본 보존'],
            ['20261018T162509Z-bb041c3747e8','bb041c3747e8b32144dde4f71f6ce0f23fa370c8ade217a835ac6cab276ee75c','3f9b0c1dc44ca2006e15712ec8d5898f880d150f79e85bfc3ef337f5289a0a6e','현재 설치, 전체 SIM/PC 한정 PASS / 실물 NOT_READY']]),
        '<h2>원인과 수정</h2><ol>',
        '<li>Field writer 오류가 센서 tick과 Stop 저장으로 전파되던 경로를 분리했다. 시험 판정은 PENDING_PERSISTENCE를 거쳐 해당 writer/순번/원문 SHA의 fsync 완료 ACK와 결속한다. 늦은 실패·불완전 close·알림 실패는 INCONCLUSIVE이며 권한을 복원하지 않는다. OPEN/WRITE/FLUSH/FSYNC/REPLACE/ACK 단계와 지연을 기록한다. 이는 이번 실제 Pi 재인수 결과가 아니다.</li>',
        '<li>과거 11바이트 구간은 정상 패킷이라고 추정해 버리지 않았다. 원문 8,336,993B 전체 회계, 103,514패킷·6,081ring·202불완전ring·2,259미해석B(주기201×11+초기48), CRC오류0이다. Windows 저장 자료 재생에서 57 ICP 쌍 결과 exact와 별도 계산 프로세스 종료를 검증했다. 실제 ROS 부하 성능과 구분한다.</li>',
        '<li>조종기를 Twin과 겹치지 않는 compact dock에 유지했다. 진단 타임라인에 원센서 시각/수신시각/추적시간/정지사유/배터리/정책을 분리하고, 중복 heartbeat를 센서 표본으로 세지 않는다. 선택 원문 segment의 SD·p99·p99.9·공백·정지율은 그 관측 범위만의 통계다. 제한을 통계로 자동 확대하지 않는다.</li>',
        '<li>이번 첫 cold 시험에서 HTTP 3~8ms 정상 수락 중 Kit 갱신 공백891ms가 발생해 INPUT_STALE 정지했다. 첫 모델 보고로 너무 일찍 Prepare가 열렸고 별도 PNG 캡처도 겹쳤다. 특정 함수가891ms 전부를 썼다고 단정하지 않았다. 새 후보는 모델 세대별 실제 GPU 완료와 두 post-author 갱신(&lt;기존250ms)을 관측하고 초기 캡처 종료 후 준비를 연다. 준비 전 입력·task는 폐기한다. Environment bounds는 USD notice/revision 기반 무효화하며 실패 시 이전 polling을 유지한다. 큰 갱신/통신 공백은 sticky 정지와 epoch 폐기로 보존하며 최신 sequence가 숨길 수 없다. 기존500ms watchdog·250ms 입력·속도/기하/전압 제한은 늘리지 않았다.</li>',
        '<li>Disconnect는 현재 LiDAR OFF/FAULT·scan 없음과 과거 보고를 분리한다. 원 driver 후보 SHA 오류는 정확히134B SPDX/출처 주석만 달라진 두 SHA의 제한된 호환성으로 해결했으며 다른 변경을 허용하지 않는다.</li></ol>',
        '<h2>과거 화면 해석 정정</h2><p>v544의 “다른 침실이 표시됐다/선택·stale 원인 UNKNOWN” 단정은 후속 기록과 맞지 않았다. 원 Build 명령12957c87-5b64-4147-a058-ceb128ade423, 거실 project chat_mvcck71j_6d94b13d, revision 1ca0b0f12eacace509bbf79ee2574ddbda810ad60d4ddbc44a3ea42bc7fa436b와 실제 mesh marker는 sofa/fans/blinds를 가리키고 bed가 없다. 소파가 침대처럼 보이는 카탈로그 표현을 포함한 품질 문제다. 이 근거가 사진 품질·현재 사진 재구성·세계 정합 PASS를 뜻하지 않는다. 원 관측/스크린샷은 보존했다.</p>',
        '<h2>실제 사용자 여정과 모든 시도</h2>']
    runs=['ui-fresh-01','ui-cold-01','cold-failure-diagnosis-01','ui-fresh-02','ui-cold-02','lineage-02','lineage-cold-02','diagnostics-ui-02','diagnostics-ui-03','diagnostics-ui-04','lineage-cold-02b','normal-02','normal-restart-02']
    rows=[]
    for name in runs:
        value=read(name+'/result.json')
        if not value:continue
        rows.append([link(name+'/result.json',name),esc(value.get('status')),esc(value.get('desktop',{}).get('engine',{}).get('launch_id',value.get('launch_id',''))),esc(value.get('project','')),esc(value.get('operation_id','')),esc(value.get('error',''))])
    parts.append(table(['시도','판정','실행 ID','프로젝트','operation ID','오류'],rows))
    parts.append('<p>일반 root Start41.194초/완전 재시작58.316초, 동일owner/8765 하나/debug19222 없음. Computer Use native Alt+F4 두 번 뒤 owned10/24개가 각각0, lock·리스너0을6.733/7.703초 관찰로 확인했다. 일반 창 GraphicsCapture timeout/AX부분노출 때문에 일반 모드 전체 native 입력·영상은 NOT_RUN이다. '+link('normal-lifecycle.json','일반 시작·종료·재시작 원장')+' · '+link('native-input-receipts.json','native 입력·제한')+' · '+link('gate-negative-result.json','원 cold FAIL 재사용 시 인수 거절')+'</p>')
    parts.append('<p>lineage-cold-02는 App이 실제 최신 실패 ed7bed를 열었는데 시험 인자로 이전 ee9883 fixture를 지정한 시험 작성 오류다. diagnostics-ui-02는 엄격한 label 선택자 오류다. 원 실패를 보존했고 최신 원본 fixture의 CANCELLED/불완전 cleanup을 그대로 비교하도록 수정했다. diagnostics-ui-03은 기능 PASS지만 통계 표의 실제 가시 증거를 강화하려고04 전체를 다시 실행했다. 이 실패·보강을 제품의 성공으로 합치지 않는다.</p>')
    identities=[]
    for name in runs:
        value=read(name+'/result.json');operations={}
        for sample in value.get('samples',[]):
            for robot in sample.get('robots',[]):
                operation=robot.get('operation_id');context=robot.get('source_twin_context') or {}
                if operation:operations[operation]=dict(robot_id=robot.get('robot_id'),scene_revision=context.get('scene_revision'),conversation=context.get('conversation_session_id'))
        identities.append(dict(run=name,project=value.get('project'),conversation=value.get('conversation'),input_sha256=value.get('input_sha256'),operations=operations))
    (root/'identity-index.json').write_text(json.dumps(identities,ensure_ascii=False,indent=2),encoding='utf-8')
    parts.append('<p>'+link('identity-index.json','생성 입력 SHA·채팅·장면·각 operation 결속 색인')+' · 모든 실제 요청 ID와 원문은 각 result/operation JSON에 보존했다.</p>')
    for name in runs:
        value=read(name+'/result.json')
        if not value.get('steps'):continue
        parts.append('<details><summary>'+esc(name)+' · 단계별 기능/복원/응답성</summary>'+table(['단계','판정','ms'],[[esc(s['name']),esc(s['status']),esc(s.get('elapsed_ms',''))] for s in value['steps']])+'</details>')
    parts.append('<h2>실제 화면</h2>')
    for name,caption in [('ui-cold-01/failure-7.png','보존한 첫 cold FAIL: 조종 수락 중 Kit 갱신 정체'),('ui-fresh-02/generated.png','최종 후보 실제 텍스트 생성(사진 품질 NOT_APPLICABLE)'),('ui-fresh-02/held-release.png','마지막 화면과 겹치지 않는 조종 dock'),('ui-cold-02/cold-backward-right.png','최종 후보 cold 첫 후진/우회전'),('diagnostics-ui-04/03-distribution.png','실제 App의 원 실패 segment 통계'),('diagnostics-ui-04/03-distribution-table.png','실제 보이는 선택 구간 통계: 원 callback310개·추적 job28개'),('diagnostics-ui-04/04-history-status.png','과거 기록과 현재 연결 분리')]:
        if (root/name).is_file():parts.append('<figure><img src="'+esc(name)+'"><figcaption>'+esc(caption)+'</figcaption></figure>')
    parts.append('<h2>녹화</h2><p>실제 같은 설치 Electron renderer의 원시 screencast를 약450ms 간격으로 받고 원 프레임 시각을 인코딩 입력으로 보존했다. 무음이며 native 데스크톱/로봇 카메라 영상이 아니다. 영상만으로 센서 연속성이나 주행 품질을 판정하지 않았다. 앱 종료 후 recorder_stop의 page closed는 인코딩 성공과 별도 기록이다. 실패 시도 recording-lineage-cold-02는 원 첫→마지막177.620초/ffconcat합178.041초와 MP4169.400초가 달라 시간 정확도 미확인이다. 그 MP4를 원타이밍 근거로 사용하지 않는다. 원 frame/시각/ffconcat은 보존했다. 최종 fresh02는 원 구간254.377초/MP4254.680초이며 별도 인수 자료다.</p>')
    video_rows=[]
    for folder in sorted(root.glob('recording-*')):
        video=folder/'app-screen.mp4'
        if not video.is_file():continue
        frames=json.loads((folder/'frame-times.json').read_text());session=json.loads((folder/'session.json').read_text());samples=frames['frames']
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(video)],capture_output=True,text=True,check=True)
        seconds=float(json.loads(probe.stdout)['format']['duration'])
        intended_seconds=(frames['end']-samples[0]['at'])/1000
        row=dict(path=str(video.relative_to(root)).replace('\\','/'),sha256=sha256(video.read_bytes()).hexdigest(),bytes=video.stat().st_size,
            mp4_seconds=seconds,frames=len(samples),first_to_last_frame_seconds=(samples[-1]['at']-samples[0]['at'])/1000,
            intended_first_frame_to_finish_seconds=intended_seconds,mp4_timing_within_one_second=abs(seconds-intended_seconds)<1,
            observation_seconds=(frames['end']-frames['began'])/1000,encode=[e for e in session['events'] if e['name']=='VIDEO_ENCODE'],errors=session.get('errors',[]))
        video_rows.append(row)
        parts.append('<details '+('open' if folder.name=='recording-fresh-02' else '')+'><summary>'+esc(folder.name)+' · '+str(round(seconds,2))+'초</summary><video controls preload="none" src="'+esc(row['path'])+'"></video><p>'+link(row['path'],'MP4 열기')+' · SHA '+esc(row['sha256'])+(' · 시간 정확도 미확인' if not row['mp4_timing_within_one_second'] else '')+'</p></details>')
    (root/'video-receipts.json').write_text(json.dumps(video_rows,ensure_ascii=False,indent=2),encoding='utf-8')
    parts.append('<p>'+link('video-receipts.json','영상 길이/원프레임 구간/인코딩/오류를 분리한 원장')+'</p><h2>비용과 시험 범위</h2><pre>'+esc(json.dumps({k:v for k,v in budget.items() if k not in ('files','requests','new_requests')},ensure_ascii=False,indent=2))+'</pre>')
    parts.append('<p>이번 실제 모델 전송은 UI의 텍스트 생성만이다. 현재 개인 사진·CAD 재전송 없음. 기존 USD50 추가시험 장부와 이전 USD20 장부는 별도이며 미확정/중복을 포함했다. 공급자 청구서 실측이 아니라 usage 기반 추정이다.</p><h2>보조 시험(사용자 흐름 대체 아님)</h2>')
    supplementary=read('offline-final02/result.json')
    parts.append('<pre>'+esc(json.dumps(supplementary,ensure_ascii=False,indent=2))+'</pre>')
    logs=sorted(path.name for path in root.glob('*.log'))
    parts.append('<p>'+ ' · '.join(link(name) for name in logs)+'</p>')
    parts.append('<h2>정확한 잔여 / 전체 완료가 아닌 항목</h2><ol><li>정상 부가 패킷이라는 근거가 없는 주기11B/202불완전ring: 원문 보존·UNKNOWN 유지. 프로토콜을 확인하거나 장치에서 비교 원문을 확보해야 한다. 이를 무시해 실물 준비 PASS로 바꾸지 않았다.</li><li>실제 Pi에서 ROS 단독→LiDAR→추적→전체 기록 부하, 소스 나이/연속 공백/지속 저장/fsync 및 해제·제동 측정은 NOT_RUN. 현재 하드웨어를 켜 달라고 다시 요청하지 않았다.</li><li>실제 연결·수동/채팅90°·360도 스캔·장애물 정지·물리 로그 전체 사이클은 원 powered 실패를 유지한다. 새 설치본의 SIM 성공을 물리 성공으로 합치지 않는다.</li><li>현재 현장 사진의 배치 품질/실측 치수/실물 세계 정합, 실제2대 로봇, 새 CAD/BRep, clean PC 배포 인수는 이번 범위에서 미검증이다.</li><li>어떤 준비 장벽도 향후 GPU/OS 정체가 없음을 보장하지 않는다. 이후 정체도 원 제한대로 정지·새 입력을 요구하며 기록해야 한다.</li></ol>')
    parts.append('<p>원사진·프로젝트·기존 dirty 변경·실패 기록·과거 설치본 보존. 새 의존성/시스템 변경/Cloud/공개 배포/commit·push/삭제 0. 주 작업자 런타임 모델 ID는 조회 도구가 없어 독립 증명하지 못했다. 기존 UI Sol 높음·Astra xhigh 읽기 검토를 사용했고 Ultra로 실행했다고 주장하지 않는다.</p></html>')
    (root/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps(dict(report=str(root/'report.html'),software_status=gate.get('software_status'),status=gate.get('status'),videos=len(video_rows)),ensure_ascii=False))

if __name__=='__main__':main()
