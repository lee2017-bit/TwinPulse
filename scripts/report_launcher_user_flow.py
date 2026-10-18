# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Package already observed entry-file/UI evidence; never dispatch a test."""
from pathlib import Path
from decimal import Decimal
import base64
import hashlib
import html
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/launcher-user-flow-20261013'


def main():
    record = json.loads((OUT/'acceptance.json').read_text(encoding='utf-8'))
    ledger = json.loads((ROOT/'outputs/product-flow-20261013/device-authorized-live/agent-test.ledger.json').read_text())
    paid = sum((Decimal(r['charged_or_reserved_usd']) for r in ledger['requests'] if r.get('usage')), Decimal(0))
    held = sum((Decimal(r['charged_or_reserved_usd']) for r in ledger['requests'] if not r.get('usage')), Decimal(0))
    assert len(ledger['requests']) == record['same_authorization_total_http']
    assert paid == Decimal(record['same_authorization_estimated_usd'])
    assert held == Decimal(record['same_authorization_new_held_usd'])
    sources = ['Start-TwinPulse.cmd','scripts/launch_twinpulse_app.ps1','scripts/twinpulse_launcher.py',
        'packages/twinpulse_app/src/twinpulse_app/process_manager.py','packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/persistent_workspace.py','apps/twinpulse-web/src/api.ts',
        'apps/twinpulse-web/dist/twinpulse-build-manifest.json']
    source = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    (OUT/'source-manifest.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 실제 시작과 클릭 검증</title>',
        '<style>body{font:16px/1.7 "Malgun Gothic",sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#17242c}h1{font-size:30px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5df;padding:10px;text-align:left}img{max-width:100%;display:block;margin:auto}figure{border:1px solid #cbd5df;padding:16px;margin:24px 0}code{overflow-wrap:anywhere}small{color:#546475}</style>',
        '<h1>TwinPulse 실제 시작과 클릭 검증</h1><p>2026년 10월 13일. 기존 실행이 살아 있을 때 Start 파일이 오류로 종료하던 결함을 수정했다. 이번 결과는 현재 개발 저장소의 실제 시작 파일과 Chrome 클릭 시험이다. 설치 배포본·전체 프로젝트·사진 정밀도 인수가 아니다.</p>',
        '<h2>실제 원인과 수정</h2><ol><li>살아 있는 소유자를 발견하면 두 번째 실행이 오류로 끝났다. 이제 같은 소유자에게 인증된 앱 창 재열기를 요청하며 프로세스·포트·Isaac을 추가하지 않는다.</li><li>잠금과 첫 상태 파일 사이의 초기 구간은 같은 소유자를 최대 5초 기다린다.</li><li>동시에 열린 창의 일회용 토큰은 덮어쓰지 않고 메모리에서 독립 관리한다. 원 유효기간·일회용·인증 조건은 유지한다.</li><li>같은 앱의 유효 세션/CSRF를 보존한다. 실행 전 명확한 CSRF 거절만 동일 프로젝트에서 한 번 복구하고, 불명 응답과 다른 프로젝트 쓰기는 재전송하지 않는다.</li><li>준비 완료 뒤 Isaac의 종료 코드0은 정상 종료로 기록한다. 소유하지 않은 프로세스는 종료하지 않는다.</li></ol>',
        '<h2>사용자 경로 결과</h2><table><tr><th>경로</th><th>결과</th></tr>']
    labels = ['같은 시작 파일 동시 실행과 두 창','첫 창 New chat 클릭','직접 입력·Enter·SIM only·Create Twin',
        '현재 텍스트 3D와 Orbit','Run simulation 클릭','연결 완료 후 시작 파일 재실행',
        '사진 Attach·Send·SIM only·Create Twin','앱 창 모두 닫은 뒤 시작 파일로 재열기',
        '시험 계측 없는 일반 재시작의 New chat','일반 재시작→사진 선택→Reopen→View current Twin']
    for label, value in zip(labels,record['actual_tests'].values()):
        parts.append('<tr><td>'+html.escape(label)+'</td><td>'+html.escape(value)+'</td></tr>')
    parts.append('</table><p>기본 장면·대화 SHA 불변. 사진 저장 SHA와 장면 revision도 완전 재시작 후 동일하다. 완전 재시작에서는 Reopen만으로 실행하지 않으며 사용자가 View current Twin을 눌러 현재 3D를 표시한다.</p>')
    parts.append('<h2>원 실패 보존</h2><p>사용자 원 실패 e71b5aad…는 보존했다. 첫 재시험은 상태 파일 초기 경합으로 FAIL(5464648f…), 두 번째는 첫 창 인증 토큰 덮어쓰기 FAIL, 세 번째는 두 창 연결 후 첫 New chat의 CSRF 불일치 FAIL이었다. CLI 종료 코드0이나 홈 표시만으로 통과시키지 않았으며 실제 버튼을 눌러 발견·수정했다. 시험 도구의 임시 진단 쓰기 경합2개와 테스트 metadata 누락2개도 별도 보조 실패다.</p>')
    parts.append('<h2>비용과 실행 ID</h2><p>추가 실제 추론10HTTP, 추정 USD0.0450567. 같은 승인 장부 누적42HTTP/USD0.2361993, 새 미확정0. 과거 미확정 USD3을 유지해 USD10 안에서 보호했다. 공급자 청구서 대조는 하지 않았다. OpenAI·로봇·Cloud·설치·공개 배포0.</p>')
    for name in ('text','photo'):
        data=record[name]
        parts.append('<p>'+html.escape(name)+': operation <code>'+data['operation_id']+'</code><br>execution <code>'+data['execution_id']+'</code><br>stored SHA <code>'+data['stored_sha256']+'</code></p>')
    parts.append('<p>보조 회귀 Python75, Web534, TypeScript/production build PASS. 이 수치는 실제 사용자 클릭의 대체 인수가 아니다.</p><h2>실제 화면</h2>')
    figures=[('bootstrap-failure.jpg','원래 연타 첫 창 인증 실패'),('launcher-normal-newchat-20261013.jpg','일반 시작 파일의 New chat 완료'),
        ('launcher-text-twin-top-20261013.jpg','실제 모델 텍스트 생성과 현재 4개 3D'),('launcher-sim-completed-20261013.jpg','사용자가 Run을 눌러 목표 도착·정상 정지'),
        ('launcher-photo-progress-20261013.jpg','실제 사진 생성 후 모델 inventory18개 표시'),('launcher-photo-scene-20261013.jpg','첫 실제 사진 장면'),
        ('launcher-final-restored-20261013.jpg','새 App/Isaac의 같은 저장 장면 재표시')]
    for filename, caption in figures:
        data=base64.b64encode((OUT/filename).read_bytes()).decode()
        parts.append('<figure><figcaption>'+html.escape(caption)+'</figcaption><img alt="'+html.escape(caption)+'" src="data:image/jpeg;base64,'+data+'"></figure>')
    parts.append('<h2>정확한 남은 범위</h2><ul>')
    for limit in record['limitations']:parts.append('<li>'+html.escape(limit)+'</li>')
    parts.append('</ul><p>사진 18/18은 모델 목록의 표시 수이며, 실측·누락 없는 사진 복원·인간 품질 검증이 아니다. 기존 Provider4 계약, live LiDAR/common Undo와 현장·새 설치 인수는 이전 잔여다. 여러 창의 대화 자동 동기화도 아직 완성되지 않았다.</p>')
    parts.append('<p>사진 출처: Chris Olszewski (Kgbo), <a href="https://commons.wikimedia.org/wiki/File:Bedroom,_Interior_of_apartment_in_Brisbane,_2025,_02.jpg">Brisbane bedroom 2025</a>, <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA4.0</a>. 원 사진 SHA3888e47a… 보존, 모델 전송에서 MPO의 첫 사진 JPEG 표현을 사용했다. 개인 사진·키·raw는 공개 업로드하지 않았다.</p></html>')
    (OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps({'status':'REPORT_READY','screens':len(figures),'http':len(ledger['requests']),'estimated_usd':str(paid),'new_held_usd':str(held)}))


if __name__=='__main__':main()
