# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Render the final local report, preserving the earlier generated report.

Only derived report files in this explicit evidence root are written. Original
receipts, failures, media and hash-bound gate records are never changed.
"""
import argparse
from hashlib import sha256
import html
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    root=args.root.resolve()
    if root!=Path(__file__).resolve().parents[1]/'outputs/robot-name-visibility-20261019':raise ValueError('EXPLICIT_OWNED_REPORT_REQUIRED')
    def load(name):return json.loads((root/name).read_text(encoding='utf-8-sig'))
    summary=load('summary.json');gate=load('gate-result.json');aux=load('auxiliary-attempts.json')
    upload=load('github-release.json');media=load('publication-review.json');preflight=load('source-preflight.json')
    before=root/'report-before-publication.html'
    if before.exists():raise ValueError('FINAL_REPORT_ALREADY_RENDERED')
    original=(root/'report.html').read_bytes()
    with before.open('xb') as stream:stream.write(original)
    esc=html.escape
    pre=lambda v:'<pre>'+esc(json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    a=lambda target,label:'<a href="'+esc(target)+'">'+esc(label)+'</a>'
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 현재판·GitHub·SIM 데모 결과</title>',
        '<style>body{font:16px/1.65 system-ui;max-width:1200px;margin:30px auto;padding:0 22px;color:#183344;background:#f7f9fa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e9eff2;padding:14px}img,video{max-width:100%;background:#101c25}h2{margin-top:2em}a{color:#005b80}</style>',
        '<h1>로봇 이름표 수정 · 현재판 실제 검증 · 비공개 GitHub 보존</h1>',
        '<p>현재 설치판 gate: <strong>'+esc(gate['status'])+'</strong>/issues'+str(len(gate['issues']))+'. 감독된 실물시험을 시작할 소프트웨어 경로 판정이며 실물 주행·정합 PASS나 무결함 보장이 아니다.</p>',
        '<p>기본은 작은 연결점과 이름만 표시하고 음영·테두리·그림자·배터리 부행·leader를 제거했다. 이름 또는 현재 투영된 로봇 영역 클릭으로 하단 상태·조종기를 연다. 형상 투영 hint는 mesh picking/실측 측위가 아니며 모호한 겹침은 가까운 anchor를 선택한다. 자동 Connect/권한/이동은 시작하지 않는다. 시간·속도·기하·카메라 현재 프레임 검사를 완화하지 않았다.</p>',
        '<img src="ui-fresh-01/name-only-body-selection.png" alt="실제 설치판의 작은 이름과 노출된 로봇 형상">',
        '<h2>현재 설치본의 실제 시험</h2>',pre(summary),
        '<p>새 전체 fresh32/cold13/edit-Undo-lineage8/history4 각각 PASS.245 이동화면 관측 최대476.977ms/원1초 초과0,60초hold·4방향/키·채팅90°·단일360°scan·두작업Stopall·별도fault복구·저장/재열기/원실패로그 검사를 수행했다. 일반 Start41.120초/재시작56.559초·동일owner재사용/8765하나/debug0·실제 AltF4두번/소유프로세스·lock·포트0을 확인했다. 보조시험은 실제 여정과 별도다.</p>',
        '<p>'+a('evidence-manifest.json','현재 SHA결속 명세')+' · '+a('gate-result.json','실제 최종 gate')+' · '+a('normal-lifecycle.json','일반 실행·정리')+' · '+a('native-lifecycle.json','실제 native 입력/캡처 한계')+' · '+a('attempts.json','모든 실제 여정 ID·SHA·시간')+' · '+a('offline/result.json','보조 시험 원로그')+'</p>',
        '<h2>방법과 미검증</h2><p>root 동일 Start 파일을 실행도구로 호출했다(Explorer더블클릭 아님). 전체 생성/조종은 같은 설치판의 명시 Test BrowserWindow에서 실제 클릭/입력했고 실제 Flash/Nemotron/Isaac을 썼다. 별도 Chrome/직접 제품변경 API/고정 모델응답/내부상태 주입으로 대체하지 않았다. 네트워크중계 fault는 ordinary조종 종료·Stop 이후 별도 창이며 원응답 ACK/새applied epoch를 보존했다.</p>',
        '<p>전체 일반 native조종/Explorer/OS붙여넣기/실제Windows DPI/다른PC/새사진품질 인수는 NOT_RUN. 일반 graphics capture가 두 번 시간초과했지만 새 AX에서 인증된 Home을 읽고 실제 AltF4를 보냈다. 초기 root-only AX를 readiness로 세지 않았다. 이 지연의 단일 원인은 UNKNOWN이며 일반 정상종료만으로 모든 native조작이 가능하다고 주장하지 않는다.</p>',
        '<p>로봇OFF: 실물 연결·센서·Pi부하/저장·제동·주행·현장정합 NOT_RUN, strict tracking/stall INCONCLUSIVE가능. 과거 native AV/120초기동/ordinary abort/1014.789ms의 원인 UNKNOWN은 남아 있으며 clean rerun으로 해결했다고 주장하지 않는다. 원unknown LiDAR bytes/원사진/프로젝트/장부/실패 이력은 보존했다. '+a('../robot-test-entry-20261019/report.html','이전 전체 시도·실패·정정 보고서')+'</p>',
        '<h2>이번 보조·도구 실패도 보존</h2>',pre(aux),
        '<p>기존 model-library.css는 현재/직전HEAD Git blob이 일치한다. 이 공개용 헤더 검사 FAIL은 숨기거나 제품통과에 섞지 않으며 full public clearance는 미완료다. 기존 private 저장소의 권한·공개설정은 바꾸지 않았다.</p>',
        '<h2>최신 데모와 원영상</h2><video controls preload="metadata" src="TwinPulse-SIM-Demo-2026-10-19.mp4"></video>',
        '<p>'+a('TwinPulse-SIM-Demo-2026-10-19.mp4','로컬 데모')+' · '+a(upload['release_url'],'GitHub Release: 데모·설치 ZIP·SHA256SUMS')+'</p>',pre(media),
        '<p>단일 구간만 잘랐고 배속·보간·고정 성공 화면 삽입은 없다. 입력 장면은 합성 텍스트이며 개인 사진을 전송·게시하지 않았다. 원footage와 네 개 전체 녹화는 로컬 보존하며 각각 원frame PTS/종료길이를 검증했다. 표본 사이 마지막이미지 유지는 미관측 동작의 증거가 아니다.</p>',
        '<h2>GitHub 검증</h2>',pre(upload),
        '<p>소스 preflight '+esc(preflight['status'])+', '+str(len(preflight['files']))+'파일/'+str(preflight['bytes'])+'B/findings'+str(len(preflight['findings']))+'. 알려진 키 패턴 검사는 모든 비밀/개인정보 부재의 보증이 아니다. 데모3.39MB와 ZIP188.99MB는 Git 이력이 아닌 Release첨부다. 소스commit/main원격 일치와 각 첨부 실제 재다운로드 SHA를 확인했다. Apache-2.0과 별도 upstream 고지는 유지하고 Isaac/Kit/ROS/모델가중치/사용자데이터는 배포물에 넣지 않았다.</p>',
        '<p>이번5HTTP/추정USD.0451653/새UNKNOWN0;추가50 누적2.2043013/잔여47.7956987. 이전20의14.9450973(UNKNOWN.4770432포함)은 별도불변. 공급자 청구서 확정은 아니다. 새 의존성/OS·driver·Isaac 변경/실물/Cloud/삭제0. 현재판 App/ownedIsaac는 종료했다. 과거 별도 startup창들은 종료 성적에 포함하거나 임의 정리하지 않았다.</p>',
        '<p>발행전 로컬보고서 SHA256 '+sha256(original).hexdigest()+'. 원 결과와 gate를 수정하지 않았다.</p>']
    for row in load('video-receipts.json'):
        parts+=['<h2>'+esc(row['path'])+'</h2><video controls preload="metadata" src="'+esc(row['path'])+'"></video>'+pre(row)]
    (root/'report.html').write_text(''.join(parts)+'</html>',encoding='utf-8')
    print(json.dumps(dict(report=str(root/'report.html'),sha256=sha256((root/'report.html').read_bytes()).hexdigest())))


if __name__=='__main__':main()
