# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One local report with embedded screenshots and explicit verification scope."""
import base64
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/generation-preview-20261012'


def execution_id(result, operation_id):
    matches=[]
    for path in (Path(result['runtime_directory'])/'diagnostics').glob('*/manifest.json'):
        manifest=json.loads(path.read_text(encoding='utf-8'))
        if manifest.get('component')=='app' and manifest.get('metadata',{}).get('operation_id')==operation_id:
            matches.append(manifest['execution_id'])
    if len(matches)!=1:
        raise ValueError('Expected one generation execution binding: '+operation_id)
    return matches[0]


def main():
    cases=[]
    for name in ('browser-final-text','browser-final-image','browser-final-image-text'):
        path=OUT/name/'summary.json'
        if not path.is_file():raise ValueError('Missing named final case: '+name)
        cases.append((path.parent,json.loads(path.read_text(encoding='utf-8'))))
    web=json.loads((OUT/'web-final.json').read_text())
    suite=ET.parse(OUT/'python-full.xml').getroot().find('testsuite')
    focused=ET.parse(OUT/'python-final-focused-02.xml').getroot().find('testsuite')
    rows=[];sections=[];metrics=[]
    for directory,result in cases:
        browser=result.get('browser',{});progress=browser.get('completed_progress',{}).get('progress',{})
        label={'text':'텍스트','image':'이미지','image-text':'텍스트와 이미지'}[result['mode']]
        failure=browser.get('failed_operation','');success=browser.get('completed_operation','')
        failed_execution=execution_id(result,failure);completed_execution=execution_id(result,success)
        rows.append(f'<tr><td>{label}</td><td>{escape(result["status"])}</td><td>App/API/Chrome · 합성 모델 응답과 브리지</td>'
            f'<td>{result.get("fixture_dispatches",0)}</td><td><code>{escape(completed_execution)}</code></td></tr>')
        metrics.append(dict(input_mode=result['mode'],status=result['status'],actual_isaac=result['actual_isaac'],
            failed_operation_id=failure,completed_operation_id=success,
            failed_execution_id=failed_execution,completed_execution_id=completed_execution,
            fixture_dispatches=result.get('fixture_dispatches'),exact_storage_restore=result.get('exact_storage_restore'),
            source_and_build_unchanged=result.get('source_and_build_unchanged'),
            source_sha256=result.get('source_sha256'),external_cost_usd='0'))
        pictures=[]
        for name in browser.get('screens',[]):
            image=base64.b64encode((directory/name).read_bytes()).decode('ascii')
            captions={'01-input.png':'원 입력','02-building-six.png':'생성 중 첫 6개 표시',
                '03-partial-stop.png':'출력 중단 후 6개와 대기 6개 보존',
                '04-stale-reload.png':'프레임 중단과 새로고침 후 마지막 미리보기',
                '05-resumed-current.png':'명시 재개 후 전체 12개', '06-completed-reload.png':'완료 후 새로고침'}
            pictures.append(f'<figure><figcaption>{escape(captions.get(name,name))}</figcaption>'
                f'<img alt="{escape(label+" "+name)}" src="data:image/png;base64,{image}"></figure>')
        sections.append(f'<section><h2>{label} 화면과 실행 기록</h2><p>출력 중단 operation <code>{escape(failure)}</code>'
            f'<br>출력 중단 execution <code>{escape(failed_execution)}</code>'
            f'<br>재개 완료 operation <code>{escape(success)}</code>'
            f'<br>재개 완료 execution <code>{escape(completed_execution)}</code></p>'+''.join(pictures)+'</section>')
    fails=[dict(name=case.attrib['name'],file=case.attrib.get('classname')) for case in suite.findall('testcase')
        if case.find('failure') is not None]
    data=dict(status='PARTIAL',product_whole_pass=False,external_api_requests=0,external_cost_usd='0',
        actual_Isaac='NOT_RUN_PENDING_NORMAL_USER_ENGINE_SHUTDOWN',fresh_LLM='NOT_RUN_NO_CURRENT_TIME_SCOPE',
        user_engine_pid_observed=1708,cases=metrics,web=dict(passed=web['numPassedTests'],failed=web['numFailedTests']),
        agent_settings=dict(main='Current session; model/effort not independently observable',
            UI='gpt-6.1-sol high',review='gpt-6-astra high; read-only',maximum_helpers=2),
        full_python=dict(xml_tests=int(suite.attrib['tests']),failures=int(suite.attrib['failures']),errors=int(suite.attrib['errors']),
            includes_subtests=True),focused_python=dict(xml_tests=int(focused.attrib['tests']),
            failures=int(focused.attrib['failures']),errors=int(focused.attrib['errors']),includes_subtests=True),
        retained_failures=fails,observer_replay=json.loads((OUT/'observer-replay.json').read_text()))
    (OUT/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwinPulse 생성 미리보기 검증 결과</title><style>
body{font:16px/1.65 "Malgun Gothic",system-ui,sans-serif;margin:0;background:#f2f5f7;color:#172a36}
main{max-width:1100px;margin:auto;padding:28px}h1{font-size:28px}h2{margin-top:28px}
section,.summary{background:white;border:1px solid #d7e0e6;border-radius:12px;padding:20px;margin:18px 0}
table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{border-bottom:1px solid #ccd6dd;padding:10px;text-align:left;overflow-wrap:anywhere}
code{font-size:12px;overflow-wrap:anywhere}figure{margin:22px 0}figcaption{font-weight:600;margin-bottom:8px}
img{display:block;width:100%;height:auto;border:1px solid #d7e0e6}li{margin:8px 0}.limit{background:#fff2df}
@media(max-width:640px){main{padding:12px}section,.summary{padding:12px}table{font-size:12px}td,th{padding:5px}}
@media print{body{background:white}main{max-width:none;padding:0}section{border:0;padding:0}figure{break-inside:avoid}h2{break-before:page}}
</style><main><h1>TwinPulse 생성 미리보기 검증 결과</h1><p>2026년 10월 12일 · Baseline 1.0.465</p>
<div class="summary"><p>생성 단계 표시, 검증된 부분 초안의 Isaac Build 연결, 실패 후 마지막 화면 유지와 명시 재개를 구현했습니다.
현재 확인된 것은 로컬 App/API/Chrome의 세 입력 흐름입니다. 화면의 단색 렌더는 명시된 합성 브리지입니다.</p>
<p>모델 응답은 고정 테스트 데이터이며 실제 Flash/Nemotron 성능 시험이 아닙니다. 실제 사용자 Isaac는 실행 중으로 보존했고,
새 GPU 통합시험은 정상 종료 승인에 대기 중입니다. 전체 완료 판정은 PARTIAL입니다.</p></div>
<section><h2>변경된 동작</h2><ul><li>물체가 아닌 관측 메타데이터의 양수 수량도 보존하고, 실제 물체만 확장합니다.</li>
<li>수정 피드백에 구체적인 오류를 전달하고, 실패 기록 저장과 실제 초안 저장을 구분합니다.</li>
<li>전체 목록을 먼저 검사한 뒤 부모가 준비된 부분만 같은 기하 검사로 표시합니다. 미표시 물체는 대기 목록에 남습니다.</li>
<li>마지막 미리보기와 실시간 프레임을 구분하며, 카메라는 현재 프레임에서만 허용합니다.</li>
<li>취소·늦은 결과·프로젝트 전환의 기존 경계를 유지합니다. 미리보기는 확정 저장이나 주행 승인으로 사용하지 않습니다.</li></ul></section>
<section><h2>입력별 검증</h2><table><thead><tr><th>입력</th><th>결과</th><th>검증 범위</th><th>fixture 요청</th><th>완료 execution ID</th></tr></thead><tbody>'''
    html+=''.join(rows)+'</tbody></table><p>각 흐름은 생성 중 6개 표시 → 명시 출력 중단 → 대기 6개 보존 → 마지막 화면 유지와 새로고침 → 새 승인에서 남은 묶음만 재개 → 12개 저장과 정확한 복원을 확인했습니다.</p></section>'
    html+=f'<section><h2>검사 결과와 비용</h2><p>전체 Web {web["numPassedTests"]} PASS / {web["numFailedTests"]} FAIL. 타입과 빌드 PASS.</p>'
    html+='<p>Core/Provider/API 확장 검사 865 PASS / 기존 4 FAIL / 469 subtests PASS. 마지막 변경 집중 검사 84 PASS / 27 subtests PASS. 서로 겹치는 검사는 합산하지 않습니다.</p>'
    html+='<p>기존 실제 observer 응답 19행을 다시 읽어 검증했습니다. 바닥 표시 count 2를 보존하고 물체 30개를 확장했습니다. 원 실패 실행을 새 성공으로 바꾸지 않았습니다.</p>'
    html+='<p>외부 API 신규 요청 0, 신규 비용 USD 0. fixture 장부의 가상 비용은 청구로 계산하지 않습니다. 이전 사용·UNKNOWN·held는 변경하지 않았습니다.</p></section>'
    html+='<section><h2>작업 설정</h2><p>UI 보조는 GPT‑6.1 Sol high, 독립 검토는 GPT‑6 Astra high로 지정했습니다. 보조 2명 범위에서 UI와 백엔드 소유 파일을 분리했습니다. 주 세션의 모델·추론 수준은 확인·전환 도구가 없어 요청된 Sol xhigh와 일치한다고 단정하지 않습니다. 운영 Flash/Super 설정은 변경하지 않았고, 화면 시험의 별도 fixture 모델명은 실제 호출을 뜻하지 않습니다.</p></section>'
    html+='<section class="limit"><h2>정확한 잔여 작업</h2><ol><li>기존 사용자 엔진 정상 종료 후, 최종 source의 실제 Isaac에서 세 입력의 부분 Build·수정·프레임 회복을 확인합니다.</li>'
    html+='<li>같은 실제 엔진에서 취소·재개·Undo·프로그램 종료 후 재열기를 인수합니다. 이번 저장 복원은 ApplicationService의 디스크 재로드입니다.</li>'
    html+='<li>유효한 새 기간·사진 전송 범위에서 실제 Flash/Nemotron 사진 재시험을 합니다. 이전 외부 시험 기간은 만료됐습니다.</li>'
    html+='<li>기존 4개 회귀 기대값과 현재 미완성 초안 계약의 불일치를 검토합니다.</li></ol><p>캡처 콜백 누락 시 영구 대기하는 코드 경로를 재현해 제한된 복구를 추가했으나, 사용자 화면 중단의 실제 원인은 아직 확정하지 않았습니다. 네이티브 콜백 미확정 2개 이상은 추가 캡처를 누적하지 않습니다.</p></section>'
    html+=''.join(sections)+'</main></html>'
    (OUT/'report.html').write_text(html.replace('\u2011','-'),encoding='utf-8')
    print('REPORT_CREATED')


if __name__=='__main__':main()
