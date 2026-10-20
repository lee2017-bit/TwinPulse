# SPDX-License-Identifier: Apache-2.0
"""One local scope-aware report, compiled from actual artifacts, not a PASS stub."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,html,json,os
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-timing-settings-20261020'


def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def identity(path):return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    analysis=read('original-analysis.json');tests=read('supplementary.json');install=read('installation06.json')
    ui=read('ui-final/session.json');previous=read('ui/session.json')
    values=analysis['recommendation']['profile']['values'];metrics=analysis['import_report']['measurement']['metrics']
    issues=['C++ output-guard compilation/ROS execution and robot-runtime deployment/readback were NOT_RUN: no existing compiler/running WSL/Docker. New guard code is shipped as reviewed source, not an installed-robot result.',
        'No robot connection, sensor acquisition, motor, braking, physical90/360 or full physical driving acceptance. Current measured defaults are pending a future explicit connection with a compatible robot runtime.',
        'First live registration/Connect→passive timing→Disconnect automatic baseline was verified with local contracts only, NOT_RUN on hardware. Actual UI imported the original recorded measurement instead; it is labelled imported, not live authentication.',
        'Short/correlated records, missing loads/metrics and no long-duration tail evidence: PROVISIONAL, not p99.9 assurance or false-stop rate.',
        'Strict measured braking/geometry/profile constraints are not overwritten; original physical failures and earlier unrelated nonce/late HTTP/result-display risks remain open.',
        'Same installed Test BrowserWindow path, not Explorer/native OS input. Native screenshot failed FrameArrived timeout; a retry had a recorder binding error. No native-input PASS claimed.',
        'Earlier UI nested-summary selector ambiguity was a harness error; retained separately from the corrected final flow. No stitched whole-SIM or physical claim.',
        'This is a settings/review report, not a new full-generation demo or completed video. No Git/Release upload or deletion.']
    result=dict(schema='robot-timing-settings-result-1.0',at=datetime.now(timezone.utc).isoformat(),
        verdict='APP_TIMING_SETTINGS_VERIFIED_ROBOT_RUNTIME_AND_PHYSICAL_ACCEPTANCE_NOT_RUN',
        installation=install,calculation=analysis['recommendation'],original_source_count=len(analysis['sources']),
        original_operation=analysis['import_report']['operation_id'],original_failures=analysis['original_failures'],
        final_ui=ui,earlier_ui=previous,supplementary=tests,issues=issues,
        provider_http=0,provider_usd=0,last_recorded_additional50_remaining_usd=46.8551834,previous20_ledger='separate/unchanged',
        build_attempts={'01':'NOT_INSTALLED: stale prebuilt UI detected before install','02':'Installed settings UI/cold flow passed; later runtime policy logging/cleanup-lock review changes followed',
            '03':'Built, not installed; superseded by cleanup locking correction',
            '04':'Installed; actual early-start save failed runtime_not_ready. Preserved ui-final/attempt1.json; fixed API metadata admission after this failure.',
            '05':'Built, not installed; followed by malformed-action validation hardening',
            '06':'Final installed and verified; actual final UI flow recorded'},
        final_input_import=identity(OUT/'recorded-measurement-import.json'))
    runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
    cleanup=[]
    for launch in ui.get('launch_ids',[]):
        path=runtime/'launches'/launch/'cleanup-receipt.json'
        if path.is_file():cleanup.append(json.loads(path.read_text(encoding='utf-8')))
    result['cleanup']=cleanup
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda v:html.escape(str(v))
    parts=['<!doctype html><meta charset="utf-8"><title>TwinPulse 로봇별 시간 정책·설정</title>',
        '<style>body{font:16px/1.65 system-ui;max-width:1150px;margin:30px auto;padding:0 20px;color:#19323d}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}.warn{background:#fff0d9;padding:16px}</style>',
        '<h1>로봇별 시간 정책 재검토·상세설정 · 2026-10-20</h1>',
        '<p class="warn">앱의 실측 자료 가져오기·권장값 계산·19개 상세 파라미터·저장/취소/분리/재시작 복원을 확인했습니다. 로봇은 미접속입니다. C++ 컴파일·로봇 런타임 업데이트/실제 값 확인·실물 연속주행은 미검증이며 전체 로봇 준비 완료 판정이 아닙니다.</p>',
        '<h2>산출 기준</h2><p>부하(base / LiDAR / tracking+recording), 원본 나이, 수신 나이, 표본 간격, 입력 수락, 최종 출력 사이 공백을 분리했습니다. 네트워크 RTT나 평균+3σ로 혼용하지 않습니다. 규칙은 <code>ceil25(max(관측최대,p99 histogram 상단)+max(25ms,tail의25%))</code>와 기존 기본값 하한입니다. 이는 공학적 여유이며 신뢰구간·안전 인증이 아닙니다. 출력은 입력보다 최소100ms, odom freshness는 간격보다50ms 이상을 권장합니다.</p>',
        '<p>최초 등록만으로 연결하지 않습니다. 사용자가 Connect하면 모터 활성화 없는 PC watch 왕복 측정을 시작하고, 첫 종료 시 초기 기본값을 계산·저장합니다. Prepare·LiDAR는 각각 명시 요청 후 추가 부하를 관측합니다. 미측정 필드는 미측정 preset으로 남습니다. 이후 측정은 권장값만 바꾸며 custom/기존 baseline을 자동 덮어쓰지 않습니다. 설정은 다음 명시 연결에 고정되며 원 입력·센서 시각을 갱신하지 않습니다.</p>',
        '<p>공식 ROS 제어 문서도 <a href="https://control.ros.org/humble/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html">명령 만료와 제어 파라미터를 구분</a>합니다. TwinPulse의 수치·여유율은 해당 기본값을 안전 표준처럼 복사한 것이 아니라 이번 별도 설계입니다.</p>',
        '<h2>이번 원자료에서 산출한 잠정값</h2><table><tr><th>파라미터</th><th>권장 ms</th></tr>']
    parts+=['<tr><td>'+esc(k)+'</td><td>'+str(v)+'</td></tr>' for k,v in values.items()]
    parts+=['</table><p>원 operation <code>'+esc(analysis['import_report']['operation_id'])+'</code>.19개 분할 원문 SHA 검증, 원 CDR 사용 chunk SHA 검증. 최대 원 센서나이108.104ms / odom source간격207.091ms / wheel 수신간격174.684ms / guard 수신나이144.157ms / 이전 출력 원시각→다음 출력356.769ms. 마지막은 입력 수락 지연과 다른 시계 의미이므로 입력 TTL을 그 값으로 늘리지 않습니다. 원250ms 입력 실패와 다른 결과는 소급 PASS로 변경하지 않습니다.</p>',
        '<p><a href="original-analysis.json">분포·원문SHA·모든 산출 근거</a> · <a href="recorded-measurement-import.json">실제 앱으로 가져온 원자료 기반 파일</a></p>',
        '<h2>실제 설치 앱 인수</h2><pre>'+esc(json.dumps(install,ensure_ascii=False,indent=2))+'</pre>',
        '<img src="ui-final/settings.png" alt="최종 설치 앱의 실제 시간 설정 화면">',
        '<p><a href="ui-final/session.json">최종 실제 UI 시도/응답/실행ID</a> · <a href="ui/session.json">이전 설치 설정·cold 시험과 시험기 오류 원본</a></p>',
        '<h2>보조검사</h2><table><tr><th>집합</th><th>판정</th><th>원 출력</th></tr>']
    parts+=['<tr><td>'+esc(r['name'])+'</td><td>'+r['status']+'</td><td><a href="'+esc(Path(r['log']).name)+'">로그</a></td></tr>' for r in tests['checks']]
    parts+=['</table><p>보조시험은 실제 로봇 결과나 전체 사용자 여정으로 세지 않습니다. C++용 원시각/설정 경계 테스트는 추가했으나 컴파일·실행은 NOT_RUN입니다.</p><h2>실패·미검증·잔여</h2><ul>']
    parts+=['<li>'+esc(v)+'</li>' for v in issues]
    parts+=['</ul><p>빌드01의 오래된 UI 번들을 설치 전에 발견했습니다. EXE build에 기존 잠금 의존성의 웹 타입검사/재빌드를 포함시켰습니다.02 실제 설정 시험 뒤 런타임 정책 로그 정합성·자동 저장 잠금 순서를 보강했고03은 미설치입니다.04 실제 시작 직후 runtime_not_ready 저장 거절을 보존하고 로컬 설정만의 서버 예외를 수정했습니다.05는 미설치,06이 최종본입니다. 중간 결과를 합쳐 전체 주행 PASS로 만들지 않습니다. <a href="ui-final/attempt1.json">04 원 실패 응답</a></p>',
        '<h2>정상 종료·비용·보존</h2><pre>'+esc(json.dumps(cleanup,ensure_ascii=False,indent=2))+'</pre>',
        '<p>이번 Nebius HTTP/USD0. 마지막 장부 기준 추가USD50 잔여46.8551834, 이전USD20 별도·불변이며 공급자 청구서를 새로 조회한 값은 아닙니다. 기존 raw/사진/프로젝트/dirty/실패 보존. 새 의존성·OS/ROS/Isaac 설치·실물·Git쓰기/업로드·삭제0.</p><p><a href="result.json">전체 판정/ID/SHA/잔여</a></p>']
    (OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),verdict=result['verdict'])))


if __name__=='__main__':main()
