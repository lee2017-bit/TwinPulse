# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local, screenshot-embedded actual-Isaac acceptance report; no remote IO."""
import base64
import hashlib
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from build_generation_preview_report import execution_id

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/generation-preview-20261012'
STEM = 'report-isaac-final'
TITLE = 'TwinPulse 실제 Isaac 재시작 검증'

CASES = (
    ('isaac-text-03', '텍스트 생성', 'summary.json',
     ('02-building-six.png', '03-partial-stop.png', '05-resumed-current.png')),
    ('isaac-image-02', '이미지 생성', 'summary.json',
     ('02-building-six.png', '04-stale-reload.png')),
    ('isaac-image-text-02', '텍스트와 이미지 생성', 'summary.json',
     ('06-completed-reload.png',)),
    ('isaac-cancel-02', '취소와 늦은 응답 차단', 'summary.json',
     ('03-partial-stop.png',)),
    ('isaac-repair-02', '현재 렌더 검사와 수정', 'summary.json',
     ('01-candidate-under-review.png', '02-repair-pending-old-render.png', '03-corrected-current-render.png')),
    ('isaac-feedback-03', '제어권 만료 후 안전한 Undo', 'result.json', ()),
    ('isaac-feedback-04', '자연어 수정과 Undo 및 완전 재열기', 'result.json',
     ('04-feedback-applied-current.png', '05-feedback-rejected-current.png',
      '06-feedback-undo-current.png', '09-closed-restart-current.png')),
    ('isaac-rollback-01', '저장 실패 뒤 이전 장면 복구', 'result.json',
     ('04-compensated-ui-settled.png',)),
    ('isaac-project-switch-03', '프로젝트 전환과 새 세션 복원', 'result.json',
     ('create_switch-current.png', 'switch_back.png', 'reopen-current.png')),
)
CAPTIONS = {
    '02-building-six.png': '전체 12개 중 첫 6개가 실제 Isaac에 표시되고, 나머지는 대기합니다.',
    '03-partial-stop.png': '의도한 출력 중단 또는 취소 뒤에도 마지막 부분 장면과 대기 목록을 보존합니다.',
    '04-stale-reload.png': '프레임 전달을 잠시 끊고 새로고침해도 마지막 정적 미리보기가 남습니다.',
    '05-resumed-current.png': '명시 재개에서 미완료 묶음만 처리한 뒤 12개가 현재 렌더에 표시됩니다.',
    '06-completed-reload.png': '완료 뒤 새로고침에서도 저장된 장면과 현재 프레임이 일치합니다.',
    '01-candidate-under-review.png': '실제 후보 프레임을 화면에 띄운 상태에서 검사합니다.',
    '02-repair-pending-old-render.png': '수정 응답을 기다리는 동안 마지막 후보 화면을 유지합니다.',
    '03-corrected-current-render.png': '같은 컴파일과 Build 경로로 수정된 침대 배치를 표시합니다.',
    '04-feedback-applied-current.png': '자연어 제안 확인 뒤 실제 Apply와 저장이 끝난 현재 장면입니다.',
    '05-feedback-rejected-current.png': '잘못된 위치 제안은 거절하고 현재 장면은 바꾸지 않습니다.',
    '06-feedback-undo-current.png': '일반 Undo의 실제 엔진 ACK, 저장, 현재 프레임을 확인합니다.',
    '09-closed-restart-current.png': 'App과 Isaac를 완전히 닫고 새 세션에서 같은 저장 상태를 다시 표시합니다.',
    '04-compensated-ui-settled.png': '저장 직전 오류 뒤 보상 Build와 현재 프레임으로 이전 장면에 복귀합니다.',
    'create_switch-current.png': '첫 프로젝트의 저장 장면입니다. 이 캡처는 마지막 정적 미리보기이며 현재 프레임은 별도 API/캔버스 검사로 확인했습니다.',
    'switch_back.png': '빈 새 프로젝트에 이전 장면이나 미리보기 캐시가 전달되지 않습니다.',
    'reopen-current.png': '원 프로젝트를 새 엔진 세션에서 다시 표시합니다. 이 캡처는 정적 미리보기이고 별도 현재 프레임 검사는 같은 revision과 새 세션을 확인했습니다.',
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def h(value):
    return escape(str(value))


def table(headings, rows):
    return '<div class="table"><table><thead><tr>' + ''.join(f'<th>{h(v)}</th>' for v in headings) + \
        '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{h(v)}</td>' for v in row) + '</tr>' for row in rows) + \
        '</tbody></table></div>'


def suite(path):
    root = ET.parse(path).getroot().find('testsuite')
    failed = [dict(name=c.attrib['name'], classname=c.attrib.get('classname'))
              for c in root.findall('testcase') if c.find('failure') is not None or c.find('error') is not None]
    return dict(xml_tests=int(root.attrib['tests']), failures=int(root.attrib['failures']),
                errors=int(root.attrib['errors']), time_s=float(root.attrib['time']), failed=failed)


def case_metrics(name, label, value):
    browser = value.get('browser', {})
    ids = {}
    for field in ('failed_operation', 'completed_operation'):
        if browser.get(field):
            ids[field.replace('operation', 'execution_id')] = execution_id(value, browser[field])
    for field in ('feedback_transaction', 'undo_transaction', 'fault_transaction'):
        if browser.get(field):
            tx = browser[field]
            ids[field] = {k: tx.get(k) for k in ('execution_id', 'operation_id', 'command_id', 'state',
                'engine_acknowledged', 'durable_committed', 'current_frame', 'compensation_acknowledged')}
    if value.get('launches'):
        ids['launches'] = [{k: row.get(k) for k in ('project', 'launch_id', 'stage_epoch', 'host_scene_verdict',
                                                  'host_startup_idle_observed')} for row in value['launches']]
    frame_checks = {}
    for field in ('initial', 'feedback_frame', 'final'):
        observation = browser.get(field)
        if isinstance(observation, dict) and observation.get('frame'):
            frame_checks[field] = {k: observation['frame'].get(k) for k in
                ('frame_id', 'applied_revision', 'engine_session_id', 'stage_epoch', 'captured_at_ms')}
    restart = value.get('closed_runtime_restart', {})
    if restart.get('initial', {}).get('frame'):
        frame_checks['cold_reopen'] = {k: restart['initial']['frame'].get(k) for k in
            ('frame_id', 'applied_revision', 'engine_session_id', 'stage_epoch', 'captured_at_ms')}
    engine = value.get('engine', {})
    return dict(case=name, label=label, status=value['status'], ids=ids, subsequent_current_frames=frame_checks,
        actual_isaac=value.get('actual_isaac', value.get('actual_runtime', name.startswith('isaac-project-switch'))),
        fixture_dispatches=value.get('fixture_dispatches', value.get('scripted_feedback', {}).get('calls', 0)),
        engine_frames_sent=engine.get('live_viewport', {}).get('sent'),
        engine_capture_timeouts=engine.get('live_viewport', {}).get('capture_timeouts'),
        exact_storage_restore=value.get('exact_storage_restore', value.get('closed_storage_replay', {}).get('matches_browser',
                                                       value.get('original_project_unchanged'))),
        source_and_build_unchanged=value.get('source_and_build_unchanged'),
        controlled_slow_undo_s=value.get('controlled_slow_undo_s', 0),
        controlled_frame_delivery_interruption=value.get('controlled_frame_delivery_interruption'),
        source_sha256=value.get('source_sha256'), source_and_build_sha256=value.get('source_and_build_sha256'),
        external_api_requests=0, external_cost_usd='0')


def main():
    metrics, sections, images = [], [], 0
    rows = []
    for name, label, filename, pictures in CASES:
        value = load(OUT / name / filename)
        if value['status'] != 'PASS' or not value['source_and_build_unchanged']:
            raise ValueError('Final named acceptance is not a frozen PASS: ' + name)
        if filename == 'summary.json' and value.get('actual_isaac') is not True:
            raise ValueError('Synthetic engine must not enter the actual-Isaac report: ' + name)
        if value.get('engine') and value['engine'].get('status') != 'PASS':
            raise ValueError('Named built-scene acceptance lacks a native host PASS: ' + name)
        metric = case_metrics(name, label, value)
        metrics.append(metric)
        primary = metric['ids'].get('completed_execution_id')
        if name == 'isaac-feedback-03':
            primary = metric['ids']['undo_transaction']['execution_id']
        if not primary:
            primary = next((v['execution_id'] for v in metric['ids'].values()
                            if isinstance(v, dict) and v.get('execution_id')), None)
        if not primary and metric['ids'].get('launches'):
            primary = metric['ids']['launches'][-1]['launch_id'] + ' (launch ID)'
        rows.append((label, metric['status'], name, primary or '별도 원 기록 참조'))
        text = f'<section class="case-section"><h2>{h(label)}</h2><p>시험 <code>{h(name)}</code> - PASS, 실제 App/API/Isaac. '
        text += '각 시험의 입력·소스 해시와 원 로그는 해당 폴더에 보존했습니다.</p>'
        if metric['ids']:
            text += '<div class="ids"><pre>' + h(json.dumps(metric['ids'], ensure_ascii=False, indent=2)) + '</pre></div>'
        if name.startswith('isaac-feedback'):
            text += '<p>transaction의 current_frame은 해당 응답 순간의 값입니다. 뒤이어 새 Build ACK와 더 신선한 현재 프레임을 기다린 검사, 완전 재열기 검사는 별도 원 기록과 JSON의 subsequent_current_frames에 보존했습니다.</p>'
        for picture in pictures:
            data = base64.b64encode((OUT / name / picture).read_bytes()).decode('ascii')
            text += f'<figure><figcaption>{h(label)} - {h(CAPTIONS[picture])}</figcaption>' \
                    f'<img alt="{h(label + " " + picture)}" src="data:image/png;base64,{data}"></figure>'
            images += 1
        sections.append(text + '</section>')
    attempts = []
    for directory in sorted(OUT.glob('isaac-*')):
        path = next((directory / name for name in ('summary.json', 'result.json') if (directory / name).is_file()), None)
        if not path:
            continue
        value = load(path)
        attempts.append(dict(case=directory.name, status=value.get('status'), error=value.get('error'),
                             source_and_build_unchanged=value.get('source_and_build_unchanged')))
    regression = suite(OUT / 'python-runtime-full.xml')
    focused = suite(OUT / 'lease-regression-02.xml')
    original = suite(OUT / 'python-full.xml')
    if {(v['classname'], v['name']) for v in regression['failed']} != {(v['classname'], v['name']) for v in original['failed']}:
        raise ValueError('Regression failure set changed; report requires explicit investigation')
    expected_user = {
        'active_project.json': '2a87c4892164cc91d27c1e875b29f6c298783c705b476c7b5e3887e97247cb9b',
        'active_project.conversation.json': '96612f9f4618f2f6fdaf6201dee5a293c76f5800112f3d3e4ede04c34bbd4efa',
    }
    actual_user = {name: hashlib.sha256((Path.home() / 'AppData/Local/TwinPulse/runtime' / name).read_bytes()).hexdigest()
                   for name in expected_user}
    if actual_user != expected_user:
        raise ValueError('Original user project/history changed; cannot claim preservation')
    web = load(OUT / 'web-final.json')
    report = dict(status='PARTIAL',product_whole_pass=False, baseline='1.0.466',
        runtime_acceptance='PASS_IN_NAMED_SCOPES', fresh_external_LLM='NOT_RUN_EXPIRED_TIME_SCOPE',
        photo_quality='NOT_RUN_SCRIPTED_MODEL_REPLIES', physical_robot='NOT_RUN', motion_this_turn='NOT_RUN',
        external_api_requests=0, new_external_cost_usd='0', past_unknown_held='UNCHANGED',
        cases=metrics, attempts=attempts, focused_python=focused, broad_python=regression,
        broad_failure_set_unchanged=True, web_previous_frozen=dict(passed=web['numPassedTests'],failed=web['numFailedTests']),
        original_user_sha256=actual_user, original_user_unchanged=True,
        prior_user_launch=dict(launch_id='44f039a25f684a1592050109416c28b4',
            owner_pid=20576, engine_pid=1708, normally_closed=True, raw_scene_verdict='FAIL_IDLE_CAPTURE_NOT_RUN'),
        source_review='Astra high read-only; no new P1/P2 in targeted lease patch review',
        model_settings='Production Flash/Super unchanged. Test replies are explicit fixtures; root model/effort not independently observable.',
        expected_images=images)
    failures = [a for a in attempts if a['status'] != 'PASS']
    html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + TITLE + '''</title><style>
body{font:16px/1.65 "Malgun Gothic",system-ui,sans-serif;margin:0;background:#f2f5f7;color:#172a36}
main{max-width:1100px;margin:auto;padding:28px}h1{font-size:28px}h2{font-size:22px}
section,.summary{background:white;border:1px solid #d7e0e6;border-radius:12px;padding:20px;margin:18px 0}
table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{border-bottom:1px solid #ccd6dd;padding:9px;text-align:left;overflow-wrap:anywhere}
code,pre{font:12px/1.55 Consolas,monospace;overflow-wrap:anywhere;white-space:pre-wrap}figure{margin:22px 0}
figcaption{font-weight:600;margin-bottom:8px}img{display:block;width:100%;height:auto;border:1px solid #d7e0e6}
.limit{background:#fff2df}.ids{background:#f5f7f9;padding:10px}.table{width:100%}li{margin:7px 0}
@media(max-width:640px){main{padding:12px}section,.summary{padding:12px}table{font-size:12px}td,th{padding:5px}}
@media print{body{background:white;font-size:12px;line-height:1.5}main{max-width:none;padding:0}
section,.summary{border:0;padding:0}h2{break-after:avoid;font-size:20px}.case-section>h2{break-before:page}figure{break-inside:avoid}
figure img{max-height:153mm;width:auto;max-width:100%;margin:auto}figcaption{font-size:11px}tr{break-inside:avoid}pre{font-size:10px}}
</style><main><h1>''' + TITLE + '''</h1><p>2026년 10월 12일 - Baseline 1.0.466</p>
<div class="summary"><p>기존 사용자 프로그램을 정상 종료한 뒤 격리된 실제 Isaac에서 생성 중 표시, 실패 화면 보존, 재개, 수정, Undo, 완전 재열기와 프로젝트 격리를 확인했습니다.
단색 합성 브리지 대신 네이티브 Isaac 렌더와 실제 엔진 ACK를 사용했습니다.</p>
<p>모델 응답은 고정 테스트 데이터입니다. 실제 Flash/Super 생성 품질·사진 정밀도와 실물 LiDAR는 이번 시험의 통과 범위가 아닙니다.
이번 결과는 제품 경로의 개발 인수 시험이며 모델 벤치마크나 전체 제품 완료 판정이 아닙니다.</p></div>
<section><h2>확인한 사용자 흐름</h2>'''
    html += table(('흐름', '결과', '원 시험 폴더', '주 실행 식별자'), rows)
    html += '''<p>세 입력은 전체 목록 12개를 보존한 채 6개를 먼저 표시하고, 의도한 출력 중단 뒤 정적 화면·대기 6개를 유지했습니다.
명시 재개는 남은 묶음만 처리하며 최종 12개 저장 상태와 현재 프레임을 확인했습니다. 사진 입력은 명시 합성 PNG로 입력 경로만 검사했습니다.</p></section>
<section><h2>실제 발견한 오류와 수정</h2><p>첫 재열기와 프로젝트 시험 일부는 새 홈 화면을 선택하지 않은 스크립트 오류였습니다.
원 실패를 보존하고 저장 대화를 명시적으로 여는 동일한 사용자 순서로 재시험했습니다.</p>
<p>별도 Undo 시험에서 제어권 유효시간 3초보다 로컬 보관·기록 준비가 길어지면 명령 제출 전에 제어권이 만료되는 실제 제품 결함을 확인했습니다.
원 실패는 ACK 지연이 아니라 command ID가 없는 제출 전 오류였고, 기존 메시지는 연결·세션·제어권 문제를 구분하지 못했습니다.</p>
<p>동일 엔진·대기·안전 상태를 먼저 확인한 뒤 제출 직전과 허가 대기 중 자신의 제어권만 새로 확보하도록 수정했습니다.
다른 소유자의 유효 제어권을 빼앗지 않으며 세션 교체는 거절합니다. 유효시간·ACK 제한·저장 조건은 늘리거나 완화하지 않았습니다.
4초 준비 지연을 넣은 실제 Undo와 지연 없는 정상 Undo 모두 완전 재열기까지 통과했습니다.</p>
<p>새 로그는 갱신 단계·갱신 직전 제어권 소유 여부·기대 엔진 일치 여부를 남깁니다. 토큰이나 인증 정보는 기록하지 않습니다.
과거 UNKNOWN 기록은 삭제하거나 성공으로 변경하지 않았습니다.</p></section>
<section><h2>원 실패와 검사 수치</h2>'''
    html += table(('시험', '원 결과', '종류'), [(v['case'], v['status'],
        '실제 Undo 제출 전 제어권 오류' if v['case'] == 'isaac-feedback-02' else '홈 선택/재열기 시험 스크립트 오류') for v in failures])
    html += '''<p>최종 영향 검사: Python 176 PASS + 35 subtests PASS, 오류 0. 전체 확장 검사: 866 PASS / 기존 4 FAIL + 469 subtests PASS, 오류 0.
이전 실행과 실패 이름 네 개가 동일하며 중복 검사를 합산하지 않았습니다. Web 511 PASS와 타입·빌드는 기존 동결 결과이고, 이번 생산 UI/dist는 변경하지 않았습니다.</p>'''
    html += table(('남은 검사 실패', '파일'), [(v['name'], v['classname']) for v in regression['failed']])
    html += '''<p>기존 네 실패는 경계 규격 기대값과 미완성 초안/요청 횟수/정체 판정의 계약 차이입니다.
기대값을 바꿔 전체 PASS로 만들지 않았으며 별도 검토가 남아 있습니다.</p></section>
<section><h2>비용과 데이터 보존</h2><p>이번 외부 API 요청 0, 신규 외부 비용 USD 0. 테스트 장부의 가상 비용은 실제 청구가 아닙니다.
과거 사용액과 UNKNOWN/held는 그대로 유지했습니다. 운영 Flash/Super 조합·키·사용자 저장 프로젝트와 대화 파일은 변경하지 않았습니다.</p>
<p>기존 런처와 엔진은 정상 종료 요청으로 닫았습니다. 기존 엔진의 원 FAIL은 장면 미생성·idle·capture NOT_RUN 범위이며 이를 성공으로 바꾸지 않았습니다.
사용자 프로젝트와 대화의 SHA256은 종료 전·후 동일합니다. 각 시험은 별도 runtime 폴더에서 진행하고 소유 엔진을 순차적으로 정상 종료했습니다.</p></section>
<section class="limit"><h2>정확한 잔여 작업</h2><ol>
<li>새 승인 기간과 사진 전송 범위에서 실제 Flash/Super의 텍스트·사진·혼합 생성 및 현재 렌더 수정 품질을 재시험해야 합니다. 이전 외부 시험 승인 기간은 만료됐습니다.</li>
<li>실제 사진에서 물체 위치·지지·규격과 외부 모델의 오류 회복 능력을 검사해야 합니다. 이번 고정 응답 시험은 그 품질을 보증하지 않습니다.</li>
<li>기존 네 검사 실패의 기대값·현재 계약을 원 근거에 따라 검토해야 합니다.</li>
<li>live LiDAR 자동 보정의 공통 저장/Undo 연결과 현장 안전·정합 인수가 남아 있습니다. 이번에 로봇 연결·센서·모터·전원·Cloud는 사용하지 않았습니다.</li>
</ol><p>프레임 중단 시험은 실제 퍼블리셔를 유지한 채 격리된 API 입구에서 프레임만 누락시킨 재현입니다.
픽셀이나 엔진 ACK를 대체하지 않았지만, 과거 사용자 화면 중단의 원인을 모두 확정한 것은 아닙니다.
콜백 미수신 코드 경로의 단위 재현·제한된 복구와 이 실제 전달 중단 시험은 별도 근거입니다.</p></section>'''
    html += ''.join(sections) + '</main></html>'
    report['expected_headings'] = html.count('<h2>')
    (OUT / (STEM + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / (STEM + '.html')).write_text(html, encoding='utf-8')
    print(json.dumps(dict(status='REPORT_CREATED', images=images, headings=report['expected_headings'])))


if __name__ == '__main__':
    main()
