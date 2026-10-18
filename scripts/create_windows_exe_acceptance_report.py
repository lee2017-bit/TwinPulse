# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local, private acceptance report. Never reads credential stores or raw prompts."""
from pathlib import Path
import argparse
import base64
import hashlib
import html
import json
from datetime import datetime, timezone


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--screens', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
    manifest = json.loads((args.package / 'windows-release-manifest.json').read_text(encoding='utf-8'))
    evidence['package'] = {key: value for key, value in manifest.items() if key != 'files'}
    evidence['package'].update(zip_path=str(args.zip), zip_sha256=digest(args.zip), file_count=len(manifest['files']))
    for launch in evidence['launches']:
        status_file = args.state / 'launches' / launch['id'] / 'supervisor-status.json'
        if status_file.is_file():
            status = json.loads(status_file.read_text(encoding='utf-8'))
            launch['status'] = {key: status.get(key) for key in ('status', 'phase', 'started_at_utc', 'updated_at_utc', 'backend', 'engine')}
    pictures = []
    for entry in evidence['screens']:
        path = args.screens / entry['file']
        raw = path.read_bytes()
        mime = 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
        entry['sha256'] = hashlib.sha256(raw).hexdigest()
        pictures.append('<figure><img src="data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii')
                        + '"><figcaption>' + html.escape(entry['caption']) + '</figcaption></figure>')
    rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(row[key])) + '</td>' for key in ('id', 'result', 'evidence'))
                   + '</tr>' for row in evidence['tests'])
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>TwinPulse Windows EXE 실제 인수</title><style>body{font:16px/1.65 system-ui,sans-serif;color:#1c2834;max-width:1080px;margin:32px auto;padding:0 24px}h1,h2{line-height:1.25}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccd7df;padding:10px;text-align:left;vertical-align:top}img{max-width:100%;height:auto;border:1px solid #d7dce0}figure{margin:32px 0}figcaption{padding:8px;background:#eef5f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f6;padding:20px;font-size:13px}.notice{padding:18px;border-left:5px solid #bc8432;background:#fff7e9}</style>
<h1>TwinPulse Windows EXE — 실제 사용자 경로 인수</h1>
<p>2026-10-14 · Baseline 1.0.476 · 로컬 비공개 보고서 · 전체 PARTIAL</p>
<p class="notice">EXE 실행·인증 연결·저장 복원·재열기는 확인했다. 새 LLM 생성/수정, 사진 품질, 새 PC, 공개 배포를 통과했다고 주장하지 않는다. 화면은 실제 EXE와 브라우저 버튼으로 얻었다. 과거 저장 장면의 복원은 새 생성 성적이 아니다.</p>
<h2>결과와 시험 방법</h2><p>일반 TwinPulse.exe를 실행 도구로 시작하고 Computer Use 브라우저의 실제 버튼/키로 New chat, 대화 선택, Reopen, View draft, 메뉴 Exit를 수행했다. Explorer 더블클릭·native Isaac 패널·OS Ctrl+V는 현재 제어 도구에서 NOT_RUN. 제품 API 직접 호출, 고정 모델 응답, 내부 상태 주입으로 사용자 인수를 대체하지 않았다. 보조 회귀의 fixture는 별도 표시한다.</p>
<table><thead><tr><th>ID</th><th>판정</th><th>실제 근거/미검증</th></tr></thead><tbody>''' + rows + '''</tbody></table>
<h2>실제 화면</h2>''' + ''.join(pictures) + '''<h2>실행·빌드·입력·시간·비용 원자료</h2>
<p>아래 식별자는 로컬 감사용이다. 이전 후보의 PASS를 최종 후보의 PASS에 합치지 않는다. 엔진 ready 시간과 브라우저 탭 생성 시간을 첫 pixel이나 모델 시간으로 오인하지 않는다. 외부 API 추가 비용은 USD0/HTTP0이며 이전 보호 장부 USD3.7011867/10과 과거 UNKNOWN은 그대로 유지한다.</p><pre>''' + html.escape(json.dumps(evidence, ensure_ascii=False, indent=2)) + '''</pre>
<h2>정확한 후속 순서</h2><ol><li>유효한 기간의 기존 사진·Nebius 전송 승인이 확인되면 최종 EXE의 텍스트/원사진/혼합 새 생성과 자연어 Apply·Undo·취소/재개를 실제 UI로 인수한다. 현재 갱신 답변은 미수신이다.</li><li>원사진의 긴 오른쪽 책상/선반·부착 관계, 3개 pending과 전체 repair 회복을 검증한다. 수량 충족만으로 사진 품질 PASS를 주지 않는다.</li><li>별도 Windows/GPU/Isaac 장비에서 동일 ZIP으로 Python/Node 없는 새 PC 인수를 한다. OS Attach/붙여넣기와 native Extension 로그도 확인한다.</li><li>시작 메뉴/바탕화면 활성 포인터 진입점, 데이터 schema 검사 기반 rollback, 안전한 제거, 설치 중단 복구를 완성·인수한다. 현재는 버전별 복사·해시 검증·활성 포인터 이전 보존까지만 확인했다.</li><li>원 자산/변환 자산의 권리·bytecode 개인 경로·출처/고지·clean checkout 빌드를 공개 전에 검토한다. 서명/Setup.exe/WebView/자동 업데이트와 GitHub Release 업로드는 이번 완료 범위가 아니다.</li></ol>
<p>실물 로봇·유료 Cloud·시스템 설정·전역 설치·공개 업로드·commit/push 없음. 사용자 원사진/프로젝트/실패 기록은 보존했다. 개인 화면이 들어 있으므로 이 보고서를 그대로 GitHub에 올리지 않는다.</p></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding='utf-8')
    evidence['report_generated_at'] = datetime.now(timezone.utc).isoformat()
    args.output.with_suffix('.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(args.output), 'bytes': args.output.stat().st_size, 'screens': len(pictures),
                      'zip_sha256': evidence['package']['zip_sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
