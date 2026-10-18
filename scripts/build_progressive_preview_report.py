# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Screenshot-embedded scoped acceptance report; local evidence, no network."""
import base64
import hashlib
from html import escape
import json
from pathlib import Path
from build_generation_preview_report import execution_id

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/progressive-preview-20261013'
TITLE='TwinPulse 단계별 미리보기 검증 결과'
CASES=(
    ('isaac-settled-text-01','텍스트 생성',('03-valid-five-before-repair.png','05-repair-updated-twelve.png')),
    ('isaac-settled-image-01','이미지 생성',('02-room-before-inventory.png','03-valid-five-before-repair.png','05-repair-updated-twelve.png')),
    ('isaac-settled-mixed-01','텍스트와 이미지 생성',('04-eleven-during-repair.png','06-saved-reload.png')),
    ('isaac-repair-failure-03','Repair 실패와 동일 조건 재개 차단',('05-repair-failed-eleven-retained.png','06-stalled-resume-blocked.png')),
    ('isaac-cancel-01','취소와 늦은 응답 및 정상 재개',('02-building-six.png','03-partial-stop.png','04-stale-reload.png','05-resumed-current.png')),
    ('isaac-current-repair-01','현재 렌더 검사와 수정',('01-candidate-under-review.png','02-repair-pending-old-render.png','03-corrected-current-render.png','04-corrected-reload.png')),
)
CAPTIONS={
    '02-room-before-inventory.png':'전체 목록 설계가 끝나기 전에 방 외곽과 바닥을 표시합니다.',
    '03-valid-five-before-repair.png':'잘못된 1개는 대기로 남기고 유효한 5개를 먼저 표시합니다.',
    '04-eleven-during-repair.png':'Repair를 기다리는 동안 이미 유효한 11개를 보여줍니다.',
    '05-repair-updated-twelve.png':'Repair 후 12개 카탈로그 외형과 저장 장면이 갱신됩니다.',
    '06-saved-reload.png':'저장 후 새로고침한 같은 장면입니다.',
    '05-repair-failed-eleven-retained.png':'정체 실패 뒤 11개와 대기 1개를 보존합니다. 전체 생성 성공이 아닙니다.',
    '06-stalled-resume-blocked.png':'소진된 정체 정책은 같은 조건 재개를 차단하며 추가 요청이나 장면 교체가 없습니다.',
    '02-building-six.png':'다음 묶음 처리 중 먼저 준비된 6개를 표시합니다.',
    '03-partial-stop.png':'취소 후 마지막 6개와 미완료 목록을 유지합니다.',
    '04-stale-reload.png':'실제 프레임 전달을 끊고 새로고침해도 정적 미리보기가 남습니다.',
    '05-resumed-current.png':'정상 재개 승인을 받아 남은 묶음만 처리한 12개 장면입니다.',
    '01-candidate-under-review.png':'실제 현재 침대 장면을 명시 고정 응답 검사기로 넘깁니다.',
    '02-repair-pending-old-render.png':'수정 응답을 기다려도 침대 미리보기가 유지됩니다.',
    '03-corrected-current-render.png':'수정된 배치와 새 현재 프레임입니다.',
    '04-corrected-reload.png':'수정 결과가 저장되고 새로고침 후 복원됩니다.',
}


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def h(value):return escape(str(value))
def table(headings,rows):
    return '<div class="table"><table><thead><tr>'+''.join('<th>'+h(v)+'</th>' for v in headings)+\
        '</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+h(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    if (OUT/'report-final.html').exists():raise ValueError('Report already exists; preserve it')
    metrics=[];sections=[];rows=[];images=0;production=None
    for name,label,pictures in CASES:
        value=load(OUT/name/'summary.json');browser=value['browser']
        assert value['status']=='PASS' and value['actual_isaac'] and value['source_and_build_unchanged']
        assert value['owned_api_and_engine_closed'] and value['external_api_requests']==0
        current={key:sha for key,sha in value['source_sha256'].items() if key.startswith(('packages','extensions','apps\\twinpulse-web\\dist'))}
        if production is None:production=current
        assert current==production, 'Production source differs between final cases'
        operation=(browser.get('completed_operation') or browser.get('final',{}).get('operation_id') or browser.get('failed_operation'))
        identity=execution_id(value,operation)
        metric=dict(case=name,label=label,status=value['status'],execution_id=identity,operation_id=operation,
            expected_generation_failure=name=='isaac-repair-failure-03',fixture_dispatches=value['fixture_dispatches'],
            expected_fixture_dispatches=value['expected_fixture_dispatches'],exact_storage_restore=value['exact_storage_restore'],
            source_sha256=value['source_sha256'],source_and_build_unchanged=True,actual_isaac=True,
            external_api_requests=0,external_cost_usd='0',physical_requests=0,
            catalog_receipts=browser.get('catalog_receipts',[]),checks=browser.get('checks',[]),
            native_host_status=value.get('engine',{}).get('status'),
            capture_frames_sent=value.get('engine',{}).get('live_viewport',{}).get('sent'))
        assert metric['fixture_dispatches']==metric['expected_fixture_dispatches']
        metrics.append(metric);rows.append((label,'PASS (해당 기능 범위)',identity,value['fixture_dispatches']))
        section=f'<section><h2>{h(label)}</h2><p>실행 ID <code>{h(identity)}</code><br>operation <code>{h(operation)}</code></p>'
        for picture in pictures:
            raw=(OUT/name/picture).read_bytes();data=base64.b64encode(raw).decode('ascii')
            section+=f'<figure><figcaption>{h(CAPTIONS[picture])}</figcaption><img alt="{h(label+" "+picture)}" src="data:image/png;base64,{data}"></figure>'
            images+=1
        sections.append(section+'</section>')
    attempts=[]
    for directory in sorted(OUT.glob('isaac-*')):
        path=directory/'summary.json'
        if path.exists():
            value=load(path)
            attempts.append(dict(case=directory.name,status=value['status'],error=value.get('error'),
                source_and_build_unchanged=value.get('source_and_build_unchanged'),external_api_requests=value.get('external_api_requests')))
    replay=load(OUT/'original-replay-01/summary.json')
    api=load(OUT/'api-checks-05/summary.json');core=load(OUT/'core-final/summary.json')
    provider=load(OUT/'provider-checks-02/summary.json');prior=load(OUT/'provider-checks-final/summary.json')
    assert {row['test'] for row in provider['failures']}=={row['test'] for row in prior['failures']}
    web=load(OUT/'web-final.json')
    expected={
        'project.json':'cb1374a02cccd5d7eaee0a884670abaab14270c966962ff7ec011b6087e648cf',
        'project.conversation.json':'72e052ef3c2d0e56a4fce3195d88deb6c8e09c44d2ceaabcfbcf6c51226ce651'}
    user=Path.home()/'AppData/Local/TwinPulse/runtime/projects/chat_mv5d5hwj_a7d5d5f5'
    hashes={name:hashlib.sha256((user/name).read_bytes()).hexdigest() for name in expected}
    assert hashes==expected, 'User original project changed'
    report=dict(status='PARTIAL',whole_product_pass=False,baseline='1.0.467',cases=metrics,attempts=attempts,
        original_replay=dict(scope=replay['scope'],stages=[{k:row[k] for k in ('parameterized','inventory','rendered','pending')} for row in replay['stages']],
            original_checkpoint_sha256=replay['original_checkpoint_sha256'],full_candidate=replay['full_candidate'],original_file_unchanged=replay['original_file_unchanged']),
        regressions=dict(api=api,core=core,provider=provider,web=dict(passed=web['numPassedTests'],failed=web['numFailedTests'])),
        original_user_sha256=hashes,original_user_unchanged=True,production_sha256=production,
        fresh_external_LLM='NOT_RUN_EXPIRED_TIME_SCOPE',photo_fidelity='UNVERIFIED_SCRIPTED_REPLIES',physical_robot='NOT_RUN',
        new_external_cost_usd='0',external_api_requests=0,past_unknown_reservations='UNCHANGED',
        original_failed_generation_estimated_cost_usd='0.1139037',original_failed_generation_invoice_verified=False,
        helper_review='GPT-6-Astra xhigh read-only; P2 same-revision frame binding fixed and reviewed',images=images)
    style='''body{margin:0;background:#f3f6f8;color:#18313c;font:16px/1.65 "Malgun Gothic",sans-serif}main{max-width:1050px;margin:auto;padding:30px}section{background:white;border:1px solid #d7e1e5;border-radius:12px;padding:22px;margin:20px 0}h1{font-size:30px}h2{font-size:22px}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}figure{margin:24px 0;break-inside:avoid}img{width:100%;height:auto;border:1px solid #c9d2d9}figcaption{font-weight:600;margin-bottom:8px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;border:1px solid #d7e1e5;padding:10px;overflow-wrap:anywhere}th{background:#e6f4ee}.scope{border-left:5px solid #2f8a7b}.limit{border-left:5px solid #bc7e20}li{margin:8px 0}@media(max-width:600px){main{padding:12px}section{padding:14px}h1{font-size:24px}}@media print{body{background:white;font-size:11px}main{padding:0;max-width:none}section{border:0;padding:0;margin:15px 0;border-radius:0}h1{font-size:23px}h2{font-size:18px}table{font-size:10px}th,td{padding:6px}figure{break-before:page;break-inside:avoid}img{max-height:215mm;object-fit:contain}figcaption{font-size:12px}.table{overflow:visible}}'''
    html=f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title><style>{style}</style><main><h1>{TITLE}</h1><p>2026-10-13 / Baseline 1.0.467</p>'
    html+='''<section class="scope"><h2>결과와 검증 범위</h2><p>바닥과 방 외곽을 먼저 표시하고, 유효한 물체 묶음은 Repair 전에 실제 Isaac에 보여줍니다. 실패한 물체와 부모가 준비되지 않은 물체는 삭제하지 않고 대기로 남깁니다. 원본 사진 DOM을 유지하고 표시 수량·매개변수 준비 수량·전체 완료를 분리했습니다.</p><p>텍스트·이미지·혼합 입력, 실패 화면 보존, 취소와 늦은 결과 차단, 명시 재개, 현재 렌더 검사·수정, 저장 후 새로고침을 실제 App/API/Chrome/Isaac에서 검증했습니다. <strong>모델 응답과 작은 파란 입력 이미지는 명시 시험 데이터입니다. 새 Flash/Super의 사진 인식 품질이나 실제 방 정확성 시험이 아닙니다.</strong> 실물·주행·Cloud는 이번 시험에 없습니다.</p></section>'''
    html+='<section><h2>실제 사용자 흐름 결과</h2>'+table(('흐름','판정','실행 ID','로컬 응답 수'),rows)+'</section>'
    html+='''<section><h2>원 실패의 원인과 수정</h2><p>원 실행 <code>89d9006ddcc14ffcb8fc74767e90a6db</code>은 10개 응답을 모두 받았고 약 326.75초 뒤 REPAIR_STALLED로 끝났습니다. 전체 목록 설계가 약 144.55초 걸렸고, 유효 물체도 전체 검사에 묶여 바닥만 표시됐습니다. 저장소에 아직 확정 계획이 없는 부분 미리보기에서는 카탈로그 외형 정보가 Isaac까지 전달되지 않아 충돌 박스만 보이는 연결 누락도 있었습니다.</p><p>이제 작은 방 외곽 단계, 주요 가구·관측된 부모 우선 순서, 6개 이하 상세 묶음, 유효 부분 투영과 Repair 직후 갱신을 연결했습니다. 새 미리보기는 프로젝트·계획 hash·정확한 장면 재컴파일로 결속합니다. 같은 충돌 장면의 외형만 바뀌어도 새 Build별 GPU 캡처를 무효화하고 완료 뒤 새 프레임을 기다립니다. 임의 코드나 실행 권한은 전달하지 않습니다.</p><p>generic 바닥 덮개·벽 부착물·천장 부착물·벽 수납장을 추가하고, drape 치수는 모서리에 매달린 부분의 envelope임을 명확히 했습니다. 기존 10cm 격자가 놓친 좁은 공간은 경계·접촉 후보로 검사하며 바닥 여유 .11m와 물체 간격 .03m는 유지했습니다. 원 사진 물체를 이름으로 자동 재분류하거나 충돌 검사를 완화하지 않았습니다.</p></section>'''
    html+='<section><h2>원 후보 재생과 회귀 검사</h2><p>같은 원 후보의 순수 로컬 재컴파일 결과입니다. 전체 29개 배치는 여전히 실패이며 새 모델 성공으로 승격하지 않았습니다.</p>'+table(('매개변수 준비','전체 목록','표시 가능한 수','대기 수'),[(row['parameterized'],row['inventory'],row['rendered'],row['pending']) for row in report['original_replay']['stages']])
    html+=table(('검사','통과','실패','범위'),(('API·표시·저장',api['tests'],0,'123개 검사'),('Core',core['tests'],0,'305개 검사'),('Web',web['numPassedTests'],web['numFailedTests'],'517개 검사'),('Provider',provider['tests']-len(provider['failures']),len(provider['failures']),'451개 중 기존 네 실패 유지')))
    html+='<p>Provider 기존 실패는 compiler 버전 기대값, 품질 미완성 초안 반환, support 보류의 요청 횟수 및 unchanged Repair 반환 계약입니다. 원 실패 로그를 보존했고 기대값만 바꿔 전체 PASS로 만들지 않았습니다. 첫 room-stage routing 누락과 시험 함수 파싱/재개 정책을 잘못 기대한 인수 실패도 각각 원 폴더에 남겼습니다.</p></section>'
    html+='''<section><h2>비용과 보존</h2><p>이번 외부 API 호출 0회, 신규 비용 USD 0입니다. Flash/Nemotron 운영 조합과 키는 변경하지 않았습니다. 과거 실제 실패의 추정 USD 0.1139037은 별도 이력이며 청구서 검증값이 아닙니다. 기존 UNKNOWN 예약은 삭제·환급·초기화하지 않았습니다. 로컬 고정 응답 시험의 보수적 예약 장부는 실제 외부 청구가 아닙니다.</p><p>사용자 원 프로젝트와 대화 SHA가 종료 전후 동일합니다. 기존 엔진과 모든 시험 엔진은 정상 종료했으며 새 설치·실물·유료 Cloud·commit·push·공개 배포는 없습니다. Astra xhigh는 독립 읽기 검토에만 사용했습니다.</p></section>'''
    html+='''<section class="limit"><h2>정확한 잔여 작업</h2><ol><li>새 기간·사진 범위가 승인되면 실제 Flash V4.1/Nemotron Super의 세 입력 생성, 첫 화면 지연과 Repair 회복을 재시험해야 합니다. 이전 외부 승인 기간은 만료되어 이번에는 외부 호출을 하지 않았습니다.</li><li>원 29개 전체 후보는 여전히 배치 실패입니다. 새 generic kind와 drape 의미를 모델이 올바르게 사용하고 blocker 수정을 요청하는지 실제 시험이 필요합니다.</li><li>전체 이불의 윗부분과 매달린 부분을 하나의 연속 패브릭으로 만드는 새 모델, 벽 수납장에 다시 물체를 지지하는 확장 계약은 이번에 구현하지 않았습니다.</li><li>기존 네 Provider 계약 검토와 live LiDAR 공통 저장·Undo 연결 및 현장 안전·정합 인수가 남습니다. 이번 fixture 화면을 사진 정밀도·전체 실물 준비 완료의 근거로 사용하면 안 됩니다.</li></ol><p>정체 정책이 소진된 동일 조건 재개 차단은 유지했습니다. 취소·출력 중단의 정상 재개와 구분하며, 실패를 숨기거나 자동으로 추가 한도를 생성하지 않습니다.</p></section>'''
    html+=''.join(sections)+'</main></html>'
    report['expected_headings']=html.count('<h2>')
    (OUT/'report-final.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'report-final.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(status='REPORT_CREATED',images=images,headings=report['expected_headings'])))


if __name__=='__main__':main()
