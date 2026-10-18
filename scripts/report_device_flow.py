# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One local evidence report; original failures and incomplete photo objects remain visible."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import base64
import hashlib
import html
import json

ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'outputs/product-flow-20261013'
OUT=HOME/'device-final-report'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
    OUT.mkdir(exist_ok=False)
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
    style=ParagraphStyle('body',fontName='Malgun',fontSize=10.3,leading=16,wordWrap='CJK',spaceAfter=8)
    title=ParagraphStyle('title',parent=style,fontSize=20,leading=28,spaceAfter=18)
    heading=ParagraphStyle('heading',parent=style,fontSize=14,leading=22,spaceAfter=12)
    small=ParagraphStyle('small',parent=style,fontSize=8.5,leading=13,wordWrap='CJK')
    story=[];sections=[];rows=[];evidence=[]
    def para(text,kind=style):
        story.append(Paragraph(html.escape(str(text)),kind))
    def picture(path,label):
        if not path.exists():return
        from PIL import Image as PILImage
        with PILImage.open(path) as opened: width,height=opened.size
        story.append(Image(str(path),width=510,height=510*height/width))
        para(label,small)
        mime='image/jpeg' if path.suffix.lower()=='.jpg' else 'image/png'
        sections.append('<figure><img src="data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()+'"><figcaption>'+html.escape(label)+'</figcaption></figure>')
    ledger=load(HOME/'device-authorized-live/agent-test.ledger.json')
    paid=sum((Decimal(row['charged_or_reserved_usd']) for row in ledger['requests'] if row.get('usage')),Decimal(0))
    held=sum((Decimal(row['charged_or_reserved_usd']) for row in ledger['requests'] if not row.get('usage')),Decimal(0))
    para('TwinPulse 새 대화·실제 사용자 흐름 검증',title)
    para('2026-10-13. 과거 로봇 준비 실패 때문에 새 대화가 막히던 결함을 수정하고 실제 App/API/Chrome/Isaac/Nebius 경로로 검증했다.')
    para('반영한 동작',heading)
    for text in (
        '대화·SIM 편집은 현재 실행 중인 작업을 검사한다. 과거 실패·불명 기록은 새 대화를 막지 않는다.',
        '워크스페이스당 로봇 관리자와 시작 잠금 하나를 공유한다. 대화를 바꿔도 같은 장치를 중복 생성하지 않는다.',
        'OS 소유 잠금은 프로세스 종료 시 해제된다. 다른 프로세스의 실물 장치 중복 소유는 거절하며 SIM은 사용할 수 있다.',
        '사용자 데이터 폴더로 수집 상태·실행 이력·연결 진단을 복사 검증해 이전한다. 원본을 삭제하지 않고 이전을 반복해도 현재 자료를 덮어쓰지 않는다.',
        '연결 진단은 기간·512 MiB 기준으로 별도 보관할 수 있다. 현재 장치 상태·프로젝트·사진·센서 자료는 이 정리 대상에 포함하지 않는다.',
        'MPO 형식의 전화기 사진을 검사하고, 모델에는 첫 사진을 JPEG로 전송한다. 원 업로드는 byte-exact하게 보존한다.',
        '서재·복도·회의실 등 일반 공간 명칭의 치수 바인딩을 보완했다. 사진별 치수·물체 배치 특례는 추가하지 않았다.'
    ):para('• '+text)
    para('실제 추론 '+str(len(ledger['requests']))+' HTTP · usage 기반 추정 USD '+str(paid)+' · 새 미확정 USD '+str(held)+'. 과거 미확정 USD3을 포함해 이번 USD10 안에서 관리했다. 공급자 청구서와 모델 비교 벤치마크는 아니다.')
    story.append(PageBreak())
    para('실행 결과와 원 실패',heading)
    for folder in sorted(HOME.glob('device-*')):
        if not (folder/'result.json').is_file():continue
        result=load(folder/'result.json');browser=result.get('browser') or {}
        evidence.append(dict(run=folder.name,status=result['status'],source_sha256=result.get('source_sha256'),
            source_unchanged=result.get('source_unchanged'),launch=result.get('launch'),
            result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest(),
            cleanup=result.get('supervisor',{}).get('phase')))
        if result.get('smoke_only'):
            description='대화·저장 복원 (추론 0)'
            para(folder.name+' · '+result['status']+' · '+description)
            if browser.get('error'):para(browser['error'],small)
        for case in browser.get('cases',[]):
            draft=(case.get('workflow') or {}).get('site_draft') or {}
            progress=draft.get('progressive_twin') or {}
            pending=len(progress.get('unresolved') or [])
            row=dict(run=folder.name,case=case['id'],status=case['status'],elapsed_s=case.get('elapsed_s'),
                operation_id=case.get('operation_id'),execution_id=case.get('execution_id'),
                materialized=progress.get('materialized_count'),inventory=progress.get('inventory_count'),
                pending=pending,error=case.get('error'),revision=draft.get('revision'),state_sha256=draft.get('scene_state_sha256'))
            rows.append(row)
            para(folder.name+' / '+case['id']+' · '+case['status']+' · '+str(case.get('elapsed_s','별도 미측정'))+'초')
            if progress:para('표시 '+str(row['materialized'])+'/'+str(row['inventory'])+' · 보류 '+str(pending)+'개. 추정·품질 미완성은 유지한다.',small)
            if case.get('operation_id'):para('작업 '+str(case['operation_id'])+' / 실행 '+str(case.get('execution_id')),small)
            if case.get('error'):para(case['error'],small)
    story.append(PageBreak())
    para('실제 화면: 기본 대화에서 새 대화',heading)
    default=HOME/'device-default-final-01'
    if not (default/'new-chat-from-default.png').exists():default=HOME/'device-default-smoke-02'
    picture(default/'default-startup.png','과거 기본 대화의 이력을 남겨 둔 실제 시작 화면')
    story.append(Spacer(1,12))
    picture(default/'new-chat-from-default.png','같은 App/Kit에서 새 대화를 여는 화면. 과거 UNKNOWN을 정상 상태로 위장하지 않는다.')
    if (default/'connection-log-storage.png').exists():
        story.append(PageBreak());para('실제 화면: 연결 로그 정리',heading)
        picture(default/'connection-log-storage.png','Readiness에서 연결 로그 보관 기능. 현재 상태·장면과 분리된다.')
    for folder_name in ('device-live-02','device-live-final-02','device-feedback-01','device-closed-reopen-01'):
        folder=HOME/folder_name
        for name in ('text-01-terminal.png','image-01-terminal.png','mixed-01-terminal.png',
                     'feedback-applied.png','feedback-undo-reload.png','saved-after-switch-3.png'):
            if (folder/name).exists():
                story.append(PageBreak());para('실제 화면: '+folder_name,heading);picture(folder/name,name)
    story.append(PageBreak())
    para('검증의 한계와 정확한 잔여',heading)
    for text in (
        'PASS는 해당 사용자 흐름의 생성·현재 표시·저장·수정·복원을 뜻한다. 보류 물체나 사진 품질, 방 실측까지 모두 통과했다는 뜻이 아니다.',
        '사진 초안의 표시/전체/보류 수는 위 결과에 기록했다. 숨은 공간, 실제 위치·치수와 사진 외형의 인간 품질 평가는 미검증이다.',
        '실물 로봇·LiDAR·유료 Cloud·설치·공개 배포는 실행하지 않았다. 실물 정합/실행 승인 자료의 자동 이전은 자동 검토에서 차단돼 제외했다.',
        'Isaac 연결 이전의 독립 대화 활성화는 별도 후속이다. 현재 엔진을 사용하는 장면 전환은 실제 ACK와 실행 중 작업 조건을 유지한다.',
        '기존 provider 계약 4건의 실패와 실물 LiDAR 공통 commit/Undo/현장 인수는 이전 잔여이며 이번 결과로 전체 프로젝트 완료를 주장하지 않는다.',
        '첫 default-smoke의 버튼 이름 누락과 첫 live의 서재/MPO 전송 전 실패는 원본에 보존했다. 재시험 PASS로 과거 FAIL을 덮어쓰지 않았다.'
    ):para('• '+text)
    para('사진 출처',heading)
    para('Chris Olszewski (Kgbo), Bedroom, Interior of apartment in Brisbane, 2025, 02. CC BY-SA 4.0. 원본 파일을 보존했고 모델 전송 때 MPO 첫 사진의 JPEG 표현을 만들었다. UI 삽입/축소 화면을 로컬 보고서에 포함했다.',small)
    para('https://commons.wikimedia.org/wiki/File:Bedroom,_Interior_of_apartment_in_Brisbane,_2025,_02.jpg',small)
    para('https://creativecommons.org/licenses/by-sa/4.0/',small)
    metadata=dict(created_at=datetime.now(timezone.utc).isoformat(),rows=rows,evidence=evidence,
        actual_http=len(ledger['requests']),estimated_usd=str(paid),new_held_usd=str(held),
        carried_unknown_usd='3.00',authorized_usd='10.00',physical_tests='NOT_RUN')
    (OUT/'summary.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    def footer(canvas,document):
        canvas.setFont('Malgun',8);canvas.setFillColor(colors.HexColor('#536575'))
        canvas.drawString(42,25,'TwinPulse · 로컬 개발 검증 · '+str(document.page))
    SimpleDocTemplate(str(OUT/'TwinPulse-device-flow-report.pdf'),pagesize=A4,leftMargin=42,rightMargin=42,
                      topMargin=42,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(row[k]))+'</td>' for k in ('run','case','status','elapsed_s','materialized','inventory','pending','operation_id','execution_id'))+'</tr>' for row in rows)
    document='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TwinPulse 실제 검증</title><style>body{font:16px/1.6 system-ui;margin:24px;background:#f4f6f8;color:#172c3c}main{max-width:1200px;margin:auto}img{max-width:100%;height:auto}td,th{padding:8px;border:1px solid #bdcbd6;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:13px}.table{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}figure{margin:20px 0}</style><main><h1>TwinPulse 실제 검증</h1><p>실제 모델 '+str(len(ledger['requests']))+' HTTP · 추정 USD '+str(paid)+' · 새 미확정 USD '+str(held)+' · 이전 미확정 USD3 별도 보호. 부분 초안의 기능 PASS이며 사진 완전 복원 인증이 아니다.</p><div class="table"><table>'+table+'</table></div>'+''.join(sections)+'<p>사진: Chris Olszewski (Kgbo), <a href="https://commons.wikimedia.org/wiki/File:Bedroom,_Interior_of_apartment_in_Brisbane,_2025,_02.jpg">Wikimedia Commons 원본</a>, <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>. 원본은 보존하고 모델에는 MPO 첫 사진을 JPEG로 전송했다. 공개 업로드를 수행하지 않았다.</p><details><summary>실행·소스·원 실패</summary><pre>'+html.escape(json.dumps(metadata,ensure_ascii=False,indent=2))+'</pre></details></main></html>'
    (OUT/'report.html').write_text(document,encoding='utf-8')
    print(json.dumps(dict(pdf=str(OUT/'TwinPulse-device-flow-report.pdf'),http=len(ledger['requests']),estimated_usd=str(paid))))


if __name__=='__main__':main()
