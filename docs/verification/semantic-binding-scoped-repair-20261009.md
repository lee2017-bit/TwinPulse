# 관측 근거 결속·공통 응답 계약·부분 수정 검증

2026-10-09 KST · Baseline v1.0.376 · 제품 구현 및 오프라인 검증 완료 · 실제 모델 성공률 미검증

사용자가 승인한 [v375의 수정 순서](model-schema-attribution-20261009.md) 1–3을 기존 `BudgetedPipeline`과 설정된 stage transport에 반영했다. 새 모델 호출·사진 전송·Isaac·로봇 실행은 모두 0이다. 전체 데모 상태는 **PARTIAL, whole=false**이며 S5/S6를 완료로 바꾸지 않는다.

## 실제 바뀐 제품 경로

1. 관측 artifact를 보존하고 host가 요청별 `evidence_catalog`를 만든다. 모델은 `{id, kind, evidence_ref}`만 반환한다. `seen:<관측ID>`는 해당 물체 하나의 근거, `text:<번호>`는 원 요청의 정확한 최대256자 조각, `hypothesis`는 미관측 추정이다. 출처·관측 ID 배열·인용문은 모델이 다시 쓰지 않으며, host가 검증된 참조로 합친다. 사진별 ID 목록·정답 가구수·치수·좌표는 코드에 넣지 않았다.
2. 각 `object/unknown` 관측이 개별 물체로 표현되는지 검사한다. 한 물체에 여러 관측을 몰아넣기, 다른 종류의 근거, 같은 관측의 중복 물체, 존재하지 않는/구조·문·빈 공간의 참조를 거절한다. 현재 생성에서는 옛 `source` 응답을 받지 않는다. 옛 저장 후보의 출처 계약은 명시적 읽기·재검증 용도로 유지하며 조용히 새 형식으로 고치지 않는다.
3. GPT와 Nebius 요청에 같은 host-owned JSON Schema를 사용한다. `const`는 동등한 단일 `enum`과 명시 타입으로 정규화하고 system 본문에도 **실제 송신 스키마**를 넣는다. 변환은 복사본에서 하며 중복 삽입하지 않는다. OpenAI의 출력 한도 필드 변환은 기존 어댑터를 사용한다. 모델·키·출력 한도·timeout·정책을 자동 변경하거나 다른 모델로 우회하지 않는다.
4. 파싱 가능한 구조 후보의 오류에는 `base_revision + operations`를 요청한다. 실패한 항목의 kind/reference, 누락 관측 추가, 실패한 room/summary만 수정할 수 있다. 정상 항목은 host가 보존하며 해당 항목을 건드리는 patch는 거절한다. 파라미터 batch도 정상 slot을 보존하고 잘못된/누락 slot만 set, 불필요한 key만 discard한다. 중간 후보는 게시하지 않는다.
5. 구조가 아닌 깨진 JSON/잘못된 envelope는 이름을 안전하게 지정할 수 없으므로 그 작은 단계 계약만 다시 요청한다. 관측·정상 batch·전체 scene을 처음부터 다시 만드는 fallback이 아니다. 최종 기하 수정은 기존 typed patch와 전체 library/compiler 재검증을 사용한다. 미관측 hypothesis는 제거할 수 있지만 고유 관측 물체와 사용자 요청 물체를 단순 삭제해 성공시키지 않는다. 최종 add 및 compiler에서도 관측 중복을 다시 차단한다.

Canonical `semantic-scene-1.0`과 `semantic-patch-1.0` 저장 형식은 유지했다. 새 wire 결속은 `semantic-binding-1.0`, 공통 송신 계약은 `explicit-json-contract-1.0`, compiler는 `semantic-scene-compiler-1.1`이다. checkpoint에 revision을 저장하고 관측 캐시 키에 wire revision을 포함한다. 이전 checkpoint를 READY 표시만 보고 신뢰하지 않으며 현재 host 검사로 재검증한다.

## 추정과 안전의 경계

미관측 추정은 canonical `inferred + observation_ids=[]`로 보존되고 provenance의 `hypotheses`, `hypotheses_status=unobserved_estimates`에 표시된다. 관측 누락을 대신 채우는 근거로 계산하지 않는다. 방 크기·배치는 실측이 없으면 여전히 추정이며, 사용자 명시 치수는 보존한다. 정확한 텍스트 조각의 출처 확인은 완전한 자연어 의미검사가 아니므로 기존 `EXACT_QUOTE_ONLY_NOT_FULL_NLU` 한계를 유지한다.

새 UI 표시 방식·렌더 critic·실측 정합을 이번에 검증했다고 주장하지 않는다. hypothesis metadata는 기존 provider provenance 반환 경로를 사용한다. 실제 로봇 권한·정지 기준·scan/input/segment 시간·속도·임무 잠금은 변경하지 않았다.

## 실행 ID로 남는 진단

기존 `provider-evidence`의 `dispatches`, raw 응답, `validations` 기록 및 execution/attempt/span ID 결속을 사용한다. 새 별도 로깅 서비스를 만들지 않았다.

- `candidate`: 해당 호출이 실제 반환한 JSON이다. 수정 호출이면 patch 그대로 기록한다.
- `validation_candidate`: host가 복사본에 적용한 후보다. 원 응답과 구분해서 재검사할 수 있다.
- `repair_context.mode`: `targeted_operations` 또는 envelope를 교체하는 `stage_contract_replacement`다. 직전 attempt ID·후보 해시·남은 오류 대상도 유지한다.
- 잘못된 patch를 적용할 수 없으면 원 후보와 원 후보의 진단을 다음 수정에 유지하고 `failed_patch_validation`으로 patch 자체의 오류도 전달한다. patch JSON을 다음 scene 후보로 착각하지 않는다.
- 부분 수정 후에도 실패하면 **적용된 최신 후보**와 새 진단을 다음 호출에 전달한다. 이전 실패/원본 파일을 덮어쓰지 않는다.

출력 소진, 모델 불일치, 응답 결과 불명(UNKNOWN), 기록 저장 실패는 기존 보호 중단을 유지한다. 공통 요청·repair·시간·USD 예산은 새로 얻지 않으며, 같은 오류 반복은 비진전 중단한다. 사진·등록키·인증 헤더·후보 전문은 공개 DTO로 유출하지 않는다.

## 검증 결과

| 검사 | 최종 결과 | 근거 범위 |
| --- | --- | --- |
| Provider 전체 | 238 tests PASS / 4.866초 | 신규 28개 포함. 가짜 HTTP/고정 응답을 사용한 host 경로 회귀 |
| App 관련 통합 | 194 tests PASS / 81.066초 | 승인·routing·키 registry·기존 평가·진단, 실제 채팅 worker의 typed summary 수정→batch→저장 추가 |
| 과거 coverage 반례 | 현재 host 거절 | 당시 schema에는 들어가던 8관측→3물체 합집합을 `SOURCE_MULTI_OBJECT_BINDING`으로 거절 |
| 역사 보존 | SHA256 불변 | 원 요청 파일·기존 campaign/scope/audit 읽기 전후 대조. 원 실패/유료 장부 갱신 없음 |

위 묶음의 테스트 수를 합산해 고유 검사 수 또는 실제 모델 성공률로 표시하지 않는다. Web/Isaac/실물은 이번에 실행하지 않았다.

신규 회귀는 요청별 목록0/1/17개, typed role과 legacy kind 모순, 원 관측 불변, text-only 입력, unknown/추정, 근거 위조·중복·종류 불일치, 정상 sibling 수정 거절, 잘못된 base revision/중복 patch, 관측 삭제 후 coverage 실패, 누락 참조만 추가, batch slot 보존, 최종 duplicate add 거절을 다룬다. 두 단계 부분 수정의 공통 예산, 최신 적용 후보 로그, malformed JSON, patch 오류 후 원 진단 보존, 출력 소진·UNKNOWN·비진전 추가 호출 중단도 검사했다. 관측14→7→1 부분 개선의 기존 회귀도 새 typed patch로 통과했다. 기존 무과금 회복 fixture도 현행 wire와 host 결속으로 갱신했으며 scripted 요청3회(수정1회) 경로를 Isaac 없이 재검증했다. 이는 새 실제 Isaac 인수가 아니다.

재현 명령(기존 로컬 환경, 외부 호출 없음):

```powershell
$env:PYTHONPATH='C:\Users\jaewo\Documents\TwinPulse;C:\Users\jaewo\Documents\TwinPulse\packages\twinpulse_core\src;C:\Users\jaewo\Documents\TwinPulse\packages\twinpulse_provider\src;C:\Users\jaewo\Documents\TwinPulse\packages\twinpulse_app\src'
# packages/twinpulse_provider/tests에서 실행
& 'C:\Users\jaewo\Documents\TwinPulse\.venv\Scripts\python.exe' -B -m unittest discover -s . -p 'test_*.py'
# 저장소 root에서 실행
& 'C:\Users\jaewo\Documents\TwinPulse\.venv\Scripts\python.exe' -B -m unittest tests.integration.test_generation_approval tests.integration.test_stage_routing_settings tests.integration.test_provider_key_registry tests.integration.test_s2c_provider_settings tests.integration.test_split_provider_evaluation tests.integration.test_a4_saved_provider_evaluation tests.integration.test_execution_diagnostics
```

초기 sandbox 실행은 Windows 임시 파일 권한 오류와 root PYTHONPATH 누락으로 실패했다(34 tests/12 errors). ACL 변경·우회 없이 허용된 오프라인 테스트 실행으로 해결했다. 신규 회귀 중 최초26 실행은 fixture의 free-space 범주를 잘못 지정해1 error가 났고, 실제 관측 계약의 aisle로 정정했다. 초기 통합193개에서 나온5 failures는 옛 `source` fixture4건과 hypothesis 추가 후 옛 schema branch 수 기대값1건이었다. 제품에서 source 쓰기를 다시 허용하지 않고 fixture를 현행 계약으로 갱신하고 한 채팅 수정 사례를 추가한 동일 통합 묶음이194개 통과했다. 초기 실패를 실제 모델 실패나 성공으로 세지 않는다.

v375 원인 비교의 저장 raw/audit는 당시 정책 이력이다. 옛 `audit_model_schema_diagnosis.py`에는 그때 coverage 빈틈이 남아 있음을 요구하는 역사 assertion이 있으므로 현 정책 인수 도구로 재실행하지 않았다. 이번 별도 현재-정책 반례 회귀가 거절과 원본 불변을 검증했다.

## 정확한 다음 단계

새 계약을 실제 Nemotron이 지키는지, 같은 실패에서 유효한 부분 patch를 반환해 최종 장면을 회복하는지 **새 승인된 제한 안에서** 시험해야 한다. 앞선 원인 비교10회는 소진됐으며 이번 구현 승인을 추가 유료 횟수로 해석하지 않았다. 성공 후보가 나오면 일반 App 저장→현재 Isaac 3D→Run/Stop으로 연결해서 별도로 인수한다. 실패하면 같은 실행 ID의 실제 wire·patch·적용 후보·compiler 진단으로 다음 원인을 구분한다.

범용 warehouse/openings/전체 편집·렌더 critic, 신뢰 가격 갱신, 최신 패키지·현장 인수와 Physical AI Jobs 규정 확인 등 기존 잔여는 유지한다. 현재 앱을 강제 재시작·재배포하지 않았으므로 변경은 다음 TwinPulse backend 실행부터 적용된다. 전원을 켜면 전체 데모가 완료된다고 보장하지 않는다.
