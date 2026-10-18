# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Render the local, evidence-based Git preservation and pruning receipt."""
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/github-preservation-20261018'


def read(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))


def main():
    remote=read('remote-verification.json')
    plan=read('prune-applied/plan.json')
    result=read('prune-applied/result.json')
    sentinel=read('protected-after.json')
    removed=[r for r in result['results'] if r['status']=='REMOVED']
    failed=[r for r in result['results'] if r['status']!='REMOVED']
    counts={kind:sum(t['kind']==kind for t in plan['targets']) for kind in {t['kind'] for t in plan['targets']}}
    verified=read('protected-package-verification.json')
    gib=lambda n:f'{n/1024**3:.2f}'
    source='https://github.com/lee2017-bit/TwinPulse/commit/'+remote['source_commit']
    assets=''.join('<li>'+html.escape(a['name'])+' — '+str(a['bytes'])+'B / SHA256 <code>'+a['sha256']+'</code> / remote download verified</li>' for a in remote['assets'])
    pins=''.join('<li><code>'+html.escape(p)+'</code></li>' for p in plan['pins'])
    rows=''.join('<tr><td>'+html.escape(k)+'</td><td>'+str(v)+'</td></tr>' for k,v in sorted(counts.items()))
    document=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse GitHub 보존·용량 정리</title>
<style>body{{font:16px/1.65 system-ui;max-width:1050px;margin:34px auto;padding:0 20px;color:#182536}}table{{border-collapse:collapse}}td,th{{border:1px solid #bdc9d7;padding:10px}}code{{overflow-wrap:anywhere}}aside{{background:#fff1d9;padding:16px}}h1{{font-size:27px}}</style>
<h1>TwinPulse — 비공개 GitHub 보존 후 구버전 정리</h1>
<p>2026-10-18 KST. 사용자 요청 순서: 정상 SIM 롤백/최신 소스 원격 보존 → 원격 내용 확인 → 현재/롤백/필요 재현본 보호 → 불필요한 설치본·중간 빌드 삭제. 공개 전환·실물 테스트·새 설치·유료 Cloud는 수행하지 않았다.</p>
<h2>1. 원격 보존: 확인됨</h2><p><a href="{source}">원격 소스 커밋 {remote['source_commit'][:12]}</a> / <a href="{remote['release_url']}">비공개 SIM 아카이브 프리릴리스</a>. 소스 commit이 main과 일치함을 git ls-remote로 확인한 뒤 삭제를 시작했다. 개인 사진·사용자 프로젝트·원시 로봇 기록·설치 EXE/ZIP은 Git 소스에 넣지 않았다. 소스 preflight1571파일/약21.46MB, 알려진 키 형태 검사 findings0(완전한 비밀정보 부재 보증은 아님). 로컬 검증 화면 PNG7장은 업로드에서 제외했다.</p><ul>{assets}</ul>
<aside>SIM 롤백은06의 실제 SIM 인수 범위다. 최신 소스에는08의 배터리 표시/시작 진단 수정이 추가되어 태그 checkout이 frozen06 ZIP을 byte-identical 재빌드한다고 주장하지 않는다. 원 ZIP의 exact runtime/source manifest와 original notices는 그대로 보존했다. 실제 로봇은 native/ROS freshness 및 저장 실패로 NOT_READY, 바퀴 명령0이다.</aside>
<h2>2. 삭제 결과</h2><table><tr><th>검토한 대상 종류</th><th>대상 수</th></tr>{rows}</table>
<p>검토 대상 {len(plan['targets'])}개, 삭제 완료 <b>{len(removed)}개</b>, 실패 <b>{len(failed)}개</b>. 후보 논리 크기 {gib(plan['logical_candidate_bytes'])}GiB와 실제 할당 해제량은 같지 않다. 디스크 여유는 <b>{gib(result['before_free_bytes'])} → {gib(result['after_free_bytes'])}GiB</b>, 관측 증가 <b>{gib(result['observed_free_increase_bytes'])}GiB</b>이다. 같은 시간 다른 시스템 활동도 있으므로 증가량 전부를 개별 파일의 정확한 할당량 합계로 해석하지 않는다.</p>
<p>삭제는 검토된 절대경로의 원래 outputs/artifacts 하위 중간 dist/work/staging/desktop-build, 오래된 배포 ZIP과 installed/releases의 비보호 설치본만 대상으로 했다. maintenance kernel lock·현재 active pointer·실행 프로세스 참조·reparse point·보호 ID를 확인했다. 사용자 데이터/원사진/센서 로그/설정/의존성/Isaac/Docker/pagefile/Git 소스는 삭제하지 않았다. 구 버전의 작은 Windows/source manifest는 build-records에 남겼다.</p>
<h2>3. 보호·복원 검사</h2><ul>{pins}</ul><p>현재08, SIM 롤백06, 시작 실패 재현01의 설치 디렉터리·빌드 디렉터리·ZIP을 보존했다. 보호 설치본 검증: <code>{html.escape(json.dumps(verified,ensure_ascii=False))}</code>. 사용자 데이터 {sentinel['count']}파일/{sentinel['bytes']}B의 사전/사후 SHA 비교: <b>{sentinel['status']}</b>. 파일 추가/수정/삭제가 없음을 비교했다.</p>
<p>삭제한 오래된 바이너리 전체는 원격에 보관하지 않았다. exact 구버전 실행물의 일괄 복구는 제공하지 않으며, 보존한06 ZIP은 GitHub에서 원 SHA로 다시 받을 수 있다. 현재/필요 재현본은 로컬에도 남았다. 나머지는 매니페스트와 사용 가능한 소스로 재구성하는 범위이며 byte-identical 재생성을 보장하지 않는다.</p>
<h2>4. 시험·실패·미검증</h2><ul><li>정리 전 frozen06 전체1609파일 무결성 검사PASS, private source push/ZIP 원격 다운로드 SHA PASS.</li><li>기존 프로젝트 전용 Python으로 보조 device-free19+32 tests PASS. 최초 시스템 Python은 pytest/Pillow가 없어 실패했으며 설치하지 않고 기존 build venv로 재실행했다. 이를 새 실제 App/로봇 인수라고 하지 않는다.</li><li>source diff whitespace 점검은 기존 원문 라이선스/patch 및 CRLF에서 발견했다. upstream notices/원 patch를 자동 포맷하여 바꾸지 않았다.</li><li>원07/08 물리 실패 및 raw receipt complete=false/녹화 미완성은 해결됐다고 하지 않는다. 공간 정리는 처리 지연·물리 제동·정합 시험의 대체가 아니다.</li><li>이 스크립트는 이번 승인 범위의 고정 ID/preservation proof를 요구하는 재사용 가능한 검토 정리 도구다. 기존 설치 EXE의 자동 보관 상한/자동 GC를 새로 설치한 것은 아니다. 후속 빌드 전 보관 정책을 제품 설치 경로에 적용·검증해야 한다.</li></ul>
<h2>5. 비용·로컬 기록</h2><p>이 작업의 모델/로봇 HTTP0, 추가 API 비용USD0, GitHub Actions 실행0, 새 의존성 설치0. 기존 private 저장소 visibility 불변, force push/history rewrite0. 이번 Git commit/push 및 prerelease 첨부는 사용자가 명시 요청한 범위다.</p>
<p>증거: <a href="remote-verification.json">remote-verification</a>, <a href="prune-applied/plan.json">삭제 계획</a>, <a href="prune-applied/result.json">실제 삭제 결과</a>, <a href="protected-after.json">사용자 데이터 비교</a>, <a href="protected-package-verification.json">보호 설치본 확인</a>. 이 보고서는 새 전체 App 인수 보고서가 아니라 요청한 원격 보존·정리의 실행 영수증이다.</p></html>'''
    (OUT/'report.html').write_text(document,encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),removed=len(removed),failed=len(failed),protected_data=sentinel['status'])))


if __name__=='__main__':main()
