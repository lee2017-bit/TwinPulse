# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Single offline HTML report from audited actual user-flow evidence."""
import base64
from html import escape
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/model-library-20261015'
audit=json.loads((OUT/'audit.json').read_text(encoding='utf-8'))
builds={}
for number in range(1,8):
    folder=OUT/f'build{number:02}'
    manifest=json.loads((folder/'dist/TwinPulse/windows-release-manifest.json').read_text(encoding='utf-8'))
    builds[number]=manifest

cases=[
 ('A01',2,'175db913-0fc2-4a71-998d-55b1bec0cd89','새 비대칭 책장 제작',
  'FAIL · 수식의 선반이 일부 파라미터 범위에서 가구 경계 초과; repair 2회 정체. 바닥과 2 pending 보존.'),
 ('A02',3,'62f447e6-eaa9-4059-9ab5-d5292a330c28','동일 텍스트 새 제작',
  '설계도 제작·한 번의 수식 수정·자동 등록 PASS. 전체 FAIL: 새 모델에 기존 open variant를 허용한 host schema와 SHA 진척 검사 누락.'),
 ('A03',4,'c5fea6a3-8806-4707-a4e5-95bd56184dfc','A02 원 후보 UI 재개',
  'FAIL · 0 HTTP. 현재 variant 계약의 로컬 재검증 실패를 수정 입력으로 넘기기 전에 거절. 새 생성으로 대체하지 않음.'),
 ('A04',4,'676555d5-3099-4ed2-a8ae-6ae1a80051ed','Library 선택·1.5×0.5×1.8m 새 재사용',
  '기하 검사·기존 모델 선택 PASS; 전체 FAIL: 새 도구 yaw int/float 직렬화 SHA 불일치. 이 잘못된 파일은 원본 보존·source invalid 차단 상태이며 복구 완료 아님.'),
 ('A05',6,None,'A02 UI 재개 재시도',
  'FAIL · 0 HTTP. 앞선 preflight 실패 후 새 CP가 없을 때 parent CP 연결을 잃은 host 결함. 07에서 연결 보존을 수정; 실패 기록 보존.'),
 ('A06',7,'01502ecc-026d-4c9d-a569-002fc5db60d8','A02 원 후보 실제 모델 재개',
  '기능 PASS · 새 1 HTTP로 variant만 수정. 기존 5 HTTP·repair 1회 이월, 총 repair 2/3. 책장·선반 상자 2/2 실제 Isaac current·durable 저장. fresh 새 생성 성적 아님.'),
 ('A07',7,'7451c165-6dee-4011-8228-407cb9f2c88a','자연어 왼쪽 20cm·Apply·Undo',
  'PASS · 모델 6부품+지원 상자가 함께 x=-0.2m 이동, ACK·disk·current 확인. Undo 후 원 objects exact, 모델 SHA 동일. Undo 추가 모델 호출 0.'),
 ('A08',7,None,'정상 Exit→같은 Start→Reopen→View current',
  'PASS · 새 Isaac stage 6eb7c934-1741-4012-a614-f9e800fe25bb/current 7FPS. 이력 SHA a4d49e90… 불변. 추가 모델 호출 0. 과거 transaction frame을 새 live로 승격하지 않음.'),
 ('A09',7,'82aef791-45c2-47a1-896d-7d2c018b2e97','동결 최종본의 같은 재사용 새 생성',
  'FAIL/UNKNOWN · room 호출 21.094s 뒤 provider connection failed; 사용량 없음. 후속 유료 시험 중단. 현재 DNS/TCP443/무인증 HTTPS GET401 정상이나 원 실패 원인·청구 0은 확인 못함.'),
]

parts=['''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwinPulse — Library 실제 사용자 인수 2026-10-15</title><style>
body{font:16px/1.6 system-ui,sans-serif;margin:30px auto;max-width:1160px;padding:0 24px;color:#172435;background:#f9fbfc}
h1,h2{line-height:1.3}h2{border-top:1px solid #cad7df;padding-top:22px;margin-top:30px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #cad7df;padding:10px;vertical-align:top;text-align:left}
code{font-size:12px;overflow-wrap:anywhere}figure{margin:25px 0;break-inside:avoid}img{max-width:100%;border:1px solid #bdcbd7;border-radius:9px}
figcaption{color:#526271}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.status{background:#edf4f7;padding:18px;border-radius:12px}
@media print{body{background:white;max-width:none;margin:0;font-size:11px}td,th{font-size:9px;padding:5px}figure img{max-height:22cm}h2{break-after:avoid}}
</style><h1>TwinPulse 모델 라이브러리 실제 사용자 인수</h1><p>2026-10-15 · 로컬 비공개 보고서 · 전체 상태 PARTIAL</p>
<div class="status"><p>새 가구 검색→없으면 선언형 설계도 제작→검증→로컬 자동 등록과 Library 화면을 구현했다.
실제 Nemotron 제작·수정·등록, 원 실패 후보 재개→Isaac 표시·저장, 자연어 이동·Undo·완전 재시작 복원은 확인했다.
최종본 fresh 재사용 시험은 공급자 연결 오류와 사용량 미확정으로 종료했다. 사진 회귀·모든 모델/모든 사진 품질·독립 PC 배포 완료를 주장하지 않는다.</p></div>
<h2>구현 범위와 사용 방법</h2><p>상단 Library에서 기존/AI-created 모델을 검색하고 가족(home/warehouse/common), 조절 파라미터, 실제 컴파일된 기본 형상,
지원면 이름, 생성 모델·request·내용 SHA를 확인할 수 있다. Use this model in chat는 입력만 채우며 자동 호출·저장 장면 덮어쓰기를 하지 않는다.
새 장면에서는 기존 모델을 우선 선택하고 맞는 형상이 없으면 Nemotron이 안전한 데이터 설계도를 만든다. 별도 금액·등록 승인창은 없다.</p>
<p>v1은 바닥에 서는 가구 7종의 box 조립식 파라메트릭 설계도와 실제 수평 패널 위 기존 소품을 지원한다.
임의 Python/shell/USD 경로 실행은 없다. default와 파라미터 min/max corner를 검사하고 실제 인스턴스마다 다시 검사한다.
전 범위의 형상 품질·사진 정합·실물 안전을 보증하지 않는다. cloth drape, 자유 곡면, 중첩 가동 구조는 아직 이 제작기의 범위가 아니다.
저장 장면에는 정의·전체 SHA·interpreter version이 포함되며 라이브러리의 새 버전이 옛 장면을 바꾸지 않는다.</p>
<h2>시험 방법과 분리</h2><p>일반 설치 Start-TwinPulse.cmd를 실행 도구로 호출했고 실제 Chrome New chat·Library·키보드 입력·Send/Create·Apply/Undo·Exit/Reopen/View를 Computer Use로 조작했다.
실제 Flash/Super 설정과 사용자 runtime를 사용했으며 제품 API 직접 호출·내부 상태 주입·고정 모델 응답·완성 결과 복제를 사용자 인수로 사용하지 않았다.
Native Explorer 더블클릭·OS 이미지 Ctrl+V·Isaac native 패널은 제어 도구가 제공되지 않아 NOT_RUN이다.
이번 모델 시험은 텍스트이므로 Flash 관측·사진 critic은 미호출이다. 보조 scripted 응답 시험은 계약 회귀용이며 실제 모델 성공률에 합치지 않는다.</p>
<p>이 표는 수정 중 여러 소스의 개발 인수 기록이다. 단일 동결 소스의 대규모 모델 비교 벤치마크나 일반화 성공률이 아니다.
실측 없는 크기는 추정이며 입력 물체 수가 찼다는 것으로 사진 품질 PASS를 주지 않는다.</p>
<h2>모든 시도</h2><table><tr><th>시도/설치본</th><th>실제 작업·판정</th><th>식별·호출</th></tr>''']
for identity,number,request,label,result in cases:
    ledger=next((r for r in audit['ledgers'] if r.get('request_id')==request),{}) if request else {}
    cp=next((r for r in audit['checkpoints'] if r.get('request_id')==request),{}) if request else {}
    lines=[label,result]
    ids=['request: '+str(request)] if request else ['UI/local-only · 새 LLM request 없음']
    if ledger:ids+=['project: '+str(ledger.get('project_id')),'new HTTP: '+str(ledger['http'])]
    if cp:ids+=['execution: '+', '.join(cp['execution_ids']),'checkpoint: '+cp['checkpoint'],
        'input SHA: '+str(cp['input_sha256']),'budget elapsed: '+str(cp['elapsed_s'])+'s']
    parts.append(f'<tr><td>{identity}<br>Build{number:02}<br><code>{escape(builds[number]["build_id"])}</code></td>'+
        '<td>'+''.join('<p>'+escape(x)+'</p>' for x in lines)+'</td><td><code>'+'<br>'.join(escape(x) for x in ids)+'</code></td></tr>')
parts.append('</table><h2>실행·Undo·복원 근거</h2>')
for key in ('after-edit','after-undo'):
    value=audit['edits'][key];tx=value['transaction']
    parts.append('<h3>'+escape(key)+'</h3><pre>'+escape(json.dumps(dict(
        execution_id=tx['execution_id'],command_id=tx['command_id'],operation_ids=value['operation_ids'],
        state=tx['state'],effective_revision=value['effective_scene_revision'],
        exact_original_objects=value['exact_original_objects'],recipe_sha=value['recipe_hashes'],moved=value['moved']),
        ensure_ascii=False,indent=2))+'</pre>')
parts.append('''<p>Cold-open 뒤 이력 SHA는 <code>a4d49e906297d6ac5fd721592eae99772cf7bd60aff2f53cba0cee4ef2718bd7</code>로 동일했다.
Undo는 같은 geometry지만 새로운 parent revision이므로 scene revision 자체가 과거 revision과 같아야 한다고 판정하지 않았다.</p>''')
parts.append('<h2>비용·미확정</h2><pre>'+escape(json.dumps({k:audit[k] for k in (
    'http','totals','new_unknown_attempt_ids','new_held_usd','protected_carry_in_usd','protected_exposure_usd','limit_usd','rates_catalog_sha256')},
    ensure_ascii=False,indent=2))+'''</pre><p>실제17 dispatch 중16개는 응답 usage를 받았다. 신규 미확정1개는 전체 context+40k 출력 단가 예약으로 유지했다.
보존한 카탈로그 단가의 추정이며 공급자 청구서·현금 결제액 확정이 아니다. 기존 UNKNOWN/중복을 포함한4.4934696은 초기화·환급하지 않았다.
OpenAI·실물 로봇·유료 Cloud·추가 의존성 설치·commit/push/공개 배포는 이번 작업0.</p>''')
parts.append('<h2>동결 소스</h2><table><tr><th>설치본</th><th>source manifest SHA</th></tr>')
for number,manifest in builds.items():
    parts.append('<tr><td>'+escape(manifest['build_id'])+'</td><td><code>'+escape(manifest['source_manifest_sha256'])+'</code></td></tr>')
parts.append('''</table><p>최종 실제 인수07 ZIP SHA: <code>6ab63eb26d7cb7d0bcb0f57f7d09c2bcb41dc907dc6974acdc09ee25bd5dfc01</code>.
현재 canonical dirty 변경을 보존한 로컬 후보이며 기존 private branch에 이 기능을 올렸다고 주장하지 않는다. 독립 PC/공개 권리 검토는 미완료다.</p>''')
parts.append('''<h2>정확한 잔여 순서</h2><ol><li>원 연결 실패의 usage/과금 미확정 보류는 유지한다. 원 raw에는 네트워크 하위 원인이 없으므로 영구적으로0원 또는 모델 성능 문제라고 판정할 수 없다.</li>
<li>유효한 다음 시험 범위에서 최종 동결본의 fresh 모델 제작, 규격 변경 재사용, 사진/혼합 회귀를 끝낸다. 이번 fresh 재사용은 성공이 아니다.</li>
<li>ITM0018의 duvet cover/drape 의미와 여러 기존 부모의 joint 재배치·full photo repair 회복을 별도로 검증한다. 원 R05의22/26 표시·4대기를 이 책장 인수로 승격하지 않는다.</li>
<li>A04의 손상된 pilot source는 비파괴 복구 UX가 남는다. 구버전 실행기의 새 recipe 도구 미지원/rollback 호환, 독립 PC/native/OSpaste 인수도 남는다.</li>
<li>위 실제 인수와 기존 알파 공개 gate를 닫은 뒤 clean 소스·권리/개인정보 목록을 검토해 별도 Git/Release 작업을 한다.</li></ol>
<p>Astra Ultra 보조1명은 독립적인 읽기 전용 계약 검토를 수행했다. 검토 PASS는 실제 모델·Isaac 인수 PASS가 아니다.
관련 Python/UI 회귀와 type/build는 보조 근거이며 원 실패 기록을 삭제하거나 기준을 완화하지 않았다.</p><h2>실제 화면</h2>''')
captions={
 '02-generated-library.jpg':'A02: 실제 Nemotron이 만든 모델의 자동 등록·compiled preview·파라미터·지원면. 전체 장면은 이 소스에서 실패했다.',
 '03-storage-failure.jpg':'A04: 실제 재사용 요청의 host 직렬화 실패를 보존했다.',
 '04-recovered-bookcase.jpg':'A06: 원 후보의 실제 수정 재개 후 2/2 materialized/current·저장 확인.',
 '07-recovered-front.jpg':'A06: 실제 Isaac 전면. 기존 solid storage box가 아니라 독립 패널·2 full shelves·상부 half shelf·하단 상자가 있다.',
 '08-move-committed.jpg':'A07: 실제 자연어 이동 적용·engine/disk/current 완료.',
 '09-undo-committed.jpg':'A07: 일반 Undo 적용 완료. 원 기하 exact는 별도 파일 재감사로 확인했다.',
 '10-closed-reopen-current.jpg':'A08: 완전 재시작 뒤 새 stage의 현재 frame. 이전 transaction frame 상태와 구분한다.',
 '11-provider-network-stop.jpg':'A09: 실제 새 생성의 공급자 연결 실패·미확정 비용 중단. 성공에 합치지 않았다.',
}
for filename,caption in captions.items():
    path=OUT/'screens'/filename
    encoded=base64.b64encode(path.read_bytes()).decode('ascii')
    parts.append('<figure><img src="data:image/jpeg;base64,'+encoded+'" alt="'+escape(caption)+'"><figcaption>'+escape(caption)+'</figcaption></figure>')
parts.append('</html>')
target=OUT/'report.html';target.write_text('\n'.join(parts),encoding='utf-8')
print(json.dumps(dict(report=str(target),screens=len(captions),bytes=target.stat().st_size),ensure_ascii=False))
