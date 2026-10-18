# 실패 실행의 요청·수정 계약 점검

2026-10-09 KST · Baseline v1.0.372 · DIAGNOSTIC_ONLY · 후속 제품 수정 미실시

**현재 로그와 당시 코드로 실패 요청을 재구성할 수 있었다. Nemotron 설계·수정 요청 3개의 본문 해시와 응답 스키마 해시가 모두 실제 송신 직전 기록과 일치했다. 요청·수정 계약의 결함과 공개 로그 절단도 확인했다.** 이번 점검의 외부 모델 요청·유료 호출·로봇·Isaac 실행은 0이다. 기존 실제 생성 실패를 통과로 바꾸지 않는다.

대상 실행 ID는 `55188c91a3ea4caf93faa56c739a3b05`다. 기존 [v371 실제 시험](ordinary-staged-live-ten-20261009.md)의 원응답4, 장부4, 입력 archive, checkpoint, source SHA를 사용했다. 입력·응답·장부·checkpoint는 변경하지 않았다. 새 진단 스크립트와 별도 재구성 결과만 추가했다.

## 확인 방법과 한계

`scripts/audit_budgeted_request_trace.py`가 기존 BudgetedPipeline에 저장 응답을 차례대로 반환하는 로컬 transport를 연결했다. 시험 응답을 다시 모델에 보내거나 새 답을 생성하지 않았다. 실행 중 socket 연결과 urllib 전송을 명시적으로 차단했다. 원래 inference source 전체 SHA가 실제 시험 당시와 같을 때만 재생하며, 판정은 동일한 `REPAIR_STALLED`로 종료됐다.

Nano 최초/수정1/수정2 각각에서 기존 감사 코드와 같은 직렬화의 `request_sha256`와 `schema_sha256`가 모두 일치했다. 이는 원문이 당시 별도 저장되지 않았어도 이번 입력·관측·소스에서 동일 요청 본문을 복원했다는 근거다. 인증 헤더나 전송 바이트 전체 캡처를 복원한 것은 아니다. GPT 관측 단계의 OpenAI 변환 후 요청은 이번 해시 대조 대상에서 제외했다.

복원한 Nano 본문은 사진 바이트나 인증정보 없이 별도 로컬 감사 파일에 보존했다. 최초 스크립트에서 모든 socket 연결을 일찍 차단해 Windows asyncio의 내부 loopback self-pipe 생성이 실패했다. event loop를 먼저 만들고 실제 감사 구간부터 차단하도록 진단 스크립트만 수정한 후 통과했다. 제품 코드의 네트워크 제한을 변경한 것이 아니다.

## 결과

| 항목 | 직접 확인 사실 | 영향과 판단 |
| --- | --- | --- |
| 관측 전달 | 세 Nano 요청 모두 entity18/물체·장애물14개를 포함, 요청 해시 일치 | 관측을 전혀 전달하지 않은 오류는 아니다 |
| 수정 필드명 | 응답 스키마는 `inventory`, 수정 진단은 `$.objects` | 내부 변환용 필드명이 모델 수정 지시에 그대로 노출되는 확정 불일치 |
| 이전 후보 전달 | 최초·수정 모두 system/user 두 메시지. 수정은 원 user 내용에 오류 JSON을1회/2회 누적. 직전 실패 후보 JSON은 없음 | 모델은 수정할 자신의 이전 결과를 받지 않는다. 이 설계가 반복 실패를 유발한 비중은 실제 비교 시험 전 미확정 |
| 관측 커버리지 | inventory minItems0, user 출처/빈 관측ID 허용. 침대1개인 세 후보 모두 schema shape 검사0오류, 의미 검사에서는14ID 누락 | 형식 조건과 실제 승인 조건 사이 간극. 사진 관측과 글 양쪽에 있는 물체의 출처 연결 규칙도 명확히 해야 함 |
| 부분 개선 판정 | 별도 로컬 반례에서 누락14→7→1도 `progressed=false`로 판정, 두 수정 후 REPAIR_STALLED | code:path만 비교하여 오류 대상 감소를 놓치는 확정 결함. 이번 실제 응답은 동일 inventory여서 실제 중단 자체는 적절했음 |
| 호출 목록 | provider 최종4개 → 제품 공개 DTO3개, budget.requests4, 생략 표시 없음 | API의 `attempts[:3]` 고정 절단 때문. 원응답 유실이나 UI 타이밍 문제는 아님 |
| 수정 호출 표시 | replay의 개별 attempt repair flag는 네 개 모두false, budget.repairs는2 | 실제 역할은 예산에 있으나 개별 호출 표시는 초기 `_diagnostic.repair_count=0`을 읽음 |

세 Nano 후보의 누락14개는 기존 저장응답을 검사한 실제 실패다. 부분 개선14→7→1은 진행 판정의 결함을 분리하기 위해 메모리 안에서 만든 **합성 반례**이며 실제 모델의 개선 성과나 유효한 3D 결과가 아니다. 방 크기·배치·지지 관계의 품질 검증으로 확대하지 않는다.

`minItems:0` 자체는 텍스트로 빈방을 만드는 경우 필요할 수 있다. 고정 최소 가구수나 사용자 침실 전용 목록으로 바꾸는 것이 해법은 아니다. 매 요청에서 실제 관측한 항목·근거를 바탕으로 요구 조건을 구성하고, 중복/불확실 항목의 처리 근거를 보존해야 한다.

## 코드 근거

- `budgeted_pipeline.py:244` 최초 관측 전체 포함 지시와 observations 전달. `semantic_scene.py:79`는 inventory minItems0, `scene_contract.py:53`은 user 출처 분기다.
- `semantic_scene.py:104`에서 inventory를 objects로 감싸 검사한다. `scene_contract.py:111`에서 `$.objects` 진단을 만들고 `budgeted_pipeline.py:211`에서 그대로 수정 요청에 넣는다.
- `budgeted_pipeline.py:202`의 candidate는 진행 계산에만 쓰이며, `:210–221`에서 직전 후보 없이 오류만 누적한다.
- `budgeted_pipeline.py:198`은 blocker를 code:path로 줄이고, `generation_policy.py:227`은 오류 집합의 엄격한 감소를 요구한다. missing_ids 감소가 계산에서 사라진다.
- `product_workflow_service.py:1166`이 `attempts[:3]`을 적용한다. 진행 상태와 최종 오류 모두 같은 함수를 쓴다.
- `budgeted_pipeline.py:92`의 초기 repair_count와 `nebius_pipeline.py:724`의 개별 repair 플래그 계산이 실제 공통 예산 횟수와 일치하지 않는다.

## 다음 수정 순서와 인수 조건

1. **진단 경로 정합화:** structure 오류 경로를 실제 응답의 `$.inventory`로 돌려준다. 동일 오류를 objects batch·최종 compiler에서 보고할 때는 각 단계 실제 경로를 유지한다.
2. **실패 후보와 수정 목표 연결:** 추론 설명이 아닌 직전 구조화 JSON, 해당 attempt ID, 최신 검사 결과를 함께 전달한다. 과거 오류를 계속 붙이는 대신 현재 후보의 수정 대상을 명확히 한다. 관측 내용·미측정 치수는 정답으로 조작하지 않는다.
3. **관측과 inventory 계약:** 동적으로 요구 관측 ID를 연결하고 사진과 사용자 글에 동시에 존재하는 물체를 중복 생성하지 않도록 출처 규칙을 명시한다. 텍스트 빈방·여러 방·다른 물체 목록에도 적용해야 한다. 특정 사진의14개/크기 고정은 금지한다.
4. **진행 척도 보완:** 누락 ID·개별 field 오류 대상이 줄면 개선으로 인정하고, 순서/요약만 바뀜·동일 실패·오류 대상 교환·A→B→A 반복은 구분한다. 같은 원응답은 여전히 중단해야 하며, 기존 shared budget과 출력소진 즉시중단은 유지한다.
5. **실행 ID 진단 완결:** 각 attempt에 민감정보 제거 요청 본문, 응답, 검증 보고서, 수정 대상/전후 비교, 역할·시간·사용량을 결속한다. 공개 호출 목록은 현재 정책의 최대치를 지원하고 생략 시 전체 수·생략 여부를 표시한다. 원본 기록과 사후 재검사를 구분한다.

원응답 무호출 재생, 관측 항목 수/종류가 다른 입력, 텍스트 빈방, 부분 개선·반복·악화 반례를 먼저 검증한다. 이후 실제 GPT→Nano 회복과 유효 후보의 Isaac Build/Run/Stop를 다시 확인해야 한다. 이번은 점검 요청이므로 위 제품 수정은 실행하지 않았다. 사용하지 않은 v371 호출6회를 이번 점검에서 소모하지 않았다.

## 산출물

- [최종 요청 재구성·검사 결과](../../outputs/ordinary-staged-request-audit-20261009/reconstructed-final.json): planner 해시3/3 일치, 원본/source 불변, 실패 재현, 부분 개선 오판, 내부4/공개3 재현.
- [로컬 진단 스크립트](../../scripts/audit_budgeted_request_trace.py): 원본 읽기 전용, 새 출력 파일에만 기록, 외부 연결 차단. AST/diff 검사와 실제 재생 통과. 모델 성공률·전체 회귀 PASS를 주장하지 않는다.
- 전체 계획 **PARTIAL / whole=false**. 실제 모델 회복과 사진 품질, 계약 확장/렌더 critic/가격 갱신/패키지/현장 잔여는 유지한다.
