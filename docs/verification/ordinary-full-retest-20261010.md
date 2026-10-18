# 새 전체 재시험: 생성 실패와 진전 판정 결함 재현

2026-10-10 KST · Baseline v1.0.382 · 전체 PARTIAL / whole=false.

## 승인과 결과

사용자 `전체 재시험 한번 해보자` → 기존 침실 사진/OpenAI GPT 분석 + Nebius Nemotron 설계·수정/추가 최대10회/USD1/실제 로컬 Isaac SIM/로봇0의 설명에 `그래`로 승인했다. 이전9/10 장부·미사용1을 빌리거나 초기화하지 않고 별도 일반 채팅 승인1건을 만들었다.

**전체 FAIL / `GENERATION_FAILED: REPAIR_STALLED`.** 새 GPT 사진 관측1 + Nano 구조1 + 객체2batch + 최종 자동 수정2 = 6/10회, 미사용4. 추정USD0.01188129, generation active28.407초(launcher 준비시간과 별도), UNKNOWN/dispatch lock0. GPT4000/Nano20000/no-thinking/호출300초·전체900초; 모든 응답 finish=stop. 사진 외부 전송은 최초 GPT1회, Nano 사진0. 저장 응답 재생·수동 정답·fault injection0.

실제 일반 React 채팅의 사진 첨부→Q1/SIM 선택→inline USD1/10회 승인→실제 HTTP/검사까지 실행했다. 생성이 실패해 장면 저장/current Build/Run/Stop/재열기는 **NOT_RUN**이다. engine은 시험 소유 launcher가 시작했으나 Build/Run operation0·capture NOT_RUN이며 이 시험의 host 최종상태FAIL을 PASS로 바꾸지 않는다. 소유 shutdown 진단 succeeded/supervisor stopped/backend·engine owned=false, page_errors/driver_errors0. 로봇·SSH·실센서·배포0.

## 오류가 실제로 진행한 순서

새 GPT 관측16개 중 방 구조 등과 구분된 실제 구성 대상12개가 Nano inventory/파라미터에 결속됐다. 방3.5×4.0×2.4m는 추정으로 허용됐으며 방 치수 자체를 실패 사유로 삼지 않았다. 같은 세 후보를 원본 기록으로 재컴파일해 아래 진단이 완전히 동일함을 확인했다(외부호출0/원본불변).

| 실제 후보/응답 | 전체 검사 | 제품 진행 판정 |
| --- | --- | --- |
| 객체 batch 완료 | 블라인드 높이2.0m, 물체 높이0.9m → 허용 중심 상한1.95m 위반 | initial |
| 수정1: 블라인드 중심2.0→1.5m | 블라인드 오류는 사라짐. 이제 small_equipment와 box를 책상1.2×0.6m 지지면에 배치하지 못함, SURFACE_CAPACITY_EXCEEDED | no_progress, regressed=false |
| 수정2: small_equipment의 surface/desk/top → floor/null/null | 앞선 지지면 실패는 사라짐. 이제 hanging_clothes를 침대 base에 drape하면 바닥 침범 | no_progress, regressed=false → stalled2로 보호 중단 |

두 수정은 같은 값을 되풀이한 NO_CHANGE가 아니다. 실제 서로 다른 대상의 의미 있는 값을 변경했다. 관측/추정에서 시작한 후보에는 잘못된 지지 관계와 유사한 반복 치수도 있어 품질 인수는 실패 상태로 둔다. **그렇다고 이 실행을 ‘모델이 아무 수정도 못 했다’로 설명하면 틀리다.** 현재 제품 판정이 수정된 오류를 통과하고 다음 종속 검사를 시작한 후보를 무진전으로 세었다.

## 직접 확인한 제품 결함 / 수정 우선순위

1. **다음 검사로의 진전을 무진전으로 집계.** `generation_policy.ProgressTracker.observe`는 blocker set의 엄격한 부분집합 또는 동일 issue 수치 개선만 progress로 인정한다. 새로 unblocked된 검사는 regression으로 보지 않지만 progress에도 넣지 않으므로, 벽→packing→placement로 두 번 진전해도 `repair_result(progressed=False)`가 2회 누적되어 REPAIR_STALLED가 난다. 이는 새 후보를 실패로 재검사해야 하는 것과 별개로 ‘진전 없는 반복’ 판단이 잘못된 것이다. 이전 v381의 단일 오류 회복 PASS는 유지하지만 여러 순차 검사의 자동 회복까지 완료한 증거는 아니다.
2. **drape 파생 계산의 typed 대상/수치 소실.** `core/photo_placement.py:drape_pose`가 객체 문맥 없이 plain ValueError('PHOTO_PLACEMENT_DRAPE_BELOW_FLOOR')를 던진다. `semantic_scene.compiler_diagnosis`가 known PHOTO 코드라는 이유로 repairable=true/target_ids=[]/path=$.room으로 되돌리며 실제 대상·parent/part·침범량을 잃는다. 실제 값은 hanging_clothes height0.9m, bed/base 지지상단0.28m → 파생 하단-0.62m/침범0.62m다. 이 수치는 저장 후보와 카탈로그 파생 함수로 계산했으며 사진별 정답 상수가 아니다. 마지막 오류는 모델에 추가 요청하기 전에 보호 중단돼 이 부정확한 진단으로 새 paid 요청은 보내지 않았다.

다음 제품 수정은 **typed 검사별 checked/blocked/통과 상태를 보존하여 이전 오류 해결+종속 검사 개방을 진전으로 판단**하는 것과, **부모 지지면/drape 파생 함수의 오류에 child ID·field·parent/part·actual/expected/위반량을 붙여 전달**하는 것이다. 새로운 오류라서 무조건 PASS하거나 진행 카운터를 무조건 초기화하지 않는다. 기존 필수 제약 회귀·반복 후보/NO_CHANGE·A→B→A·악화 rollback·출력소진·UNKNOWN guard를 보존하며 이 실제 세 후보와 여러 다른 물체/치수로 회귀해야 한다. 원본 실패나 모델 응답을 고쳐 넣지 않는다.

이번 요청은 재시험/분석이므로 위 두 **제품 결함은 아직 수정하지 않았다**. 남은4회를 동일한 실패 반복에 쓰지 않았고 새로운 승인으로 리셋하지 않았다. 수정 후 실제 회복 시험은 현재 장부/모델 호출 범위/예산을 다시 대조해야 한다. 로봇은 필요 없다.

## 실행 ID·로그·감사

- 실행: `0ab1cdf0c5224622b79edffac574420e`; operation: `03999f8f-a585-4b0b-9912-ef55e74c89ef`.
- 승인/원본 hash/가격 metadata: `outputs/ordinary-full-retest-20261010/approval.json`.
- 최종 실패: `summary.json`, `run-1/result.json`, `run-1/browser.json`, `run-1/failed-journey.png`.
- 감사: `audit.json` / 읽기 전용 `scripts/run_ordinary_staged_live_ten.py:audit_ordinary_run`로 실제6개 request/raw/validation/ledger/finish/usage/hash/소유 종료 대조. **AUDIT_PASS는 생성 PASS가 아니다.**
- 원본 송신/응답/검사: `run-1/runtime/provider-evidence/{dispatches,validations,*.json}`; 과금 장부: `run-1/runtime/ordinary-generation/*.ledger.json`.
- 진단/span/profile: `run-1/runtime/diagnostics/0ab1cdf0c5224622b79edffac574420e/{manifest.json,events.jsonl}`.
- 수정1 attempt: `dd712e2a080b464aa87c2971432871dc`; 수정2: `0b698ee634a740a39bfbfef3712ba988`. 두 원응답에 각각 실제 변경값과 base revision이 남는다.
- 기존 사용자 설정/키 metadata·앞선 장부 hash불변. 앞선 actual 회복 장부도 `audited_geometry` 재감사: 기존9/10·미사용1불변. 이번 추가6/10·미사용4와 합쳐 새10회로 세지 않는다.

## 시험 도구 보완과 관련 검증

실행 전 일반 live 경로도 fixture의 compact 스위치를 켜지 않고 actual inventory/hash를 기록하고 closed-backend ProjectStore/schema2.1/모든 placement 관계 검사를 하도록 기존 `verify_chat_sim_journey.py`와 `chat-sim-journey.mjs`를 보완했다. 이번에는 생성 단계 실패로 그 후속 인수는 미실행이다. 기존 bound/helper·paid 계약·실물 guard나 제품 생성 source를 변경하지 않았다.

- 기존 controlled scoped harness 회귀18 PASS /0.424초 (외부0).
- Python py_compile 두 runner / node --check / 해당 diff 검사 PASS.
- 실제 세 후보 compile·진단·진행 flag 재현 PASS(원 실패 재현이지 생성 성공 아님).
- raw/request/validation/usage/hash6/6 감사 PASS, 추가 외부호출0.
- full Core/Provider/App/Web 전체 suite는 이 재시험 턴에 반복하지 않았다. 이전 v381의 suite 결과와 이번 실제 생성 실패를 서로 대체하지 않는다.

전체 제품은 PARTIAL/whole=false. 현장 인수·사진 정밀도·scope 확대/장기 탐색 등 기존 잔여에 이번 두 제품 결함이 우선으로 추가된다. 설치/시스템설정/commit/push/새 에이전트/자동화/실물 변경0.
