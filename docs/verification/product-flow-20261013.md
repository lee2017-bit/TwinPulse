# TwinPulse 금액 승인 제거와 실제 사용자 흐름 검증

2026-10-13 / Baseline 1.0.468. 사용자가 승인한 제품 단순화를 구현했다. 실제 Flash/Super와 ordinary App/API/Chrome/Isaac에서 텍스트 생성, 공개 사진 생성, 혼합 입력의 잔여 재개, 자연어 Cancel/Apply/Undo, 저장 복원과 단일 프로세스 대화 전환을 확인했다. 사진 정확도·미노출 입력 일반화·실물 전체 흐름은 완료가 아니다.

[단일 PDF 10페이지](../../outputs/product-flow-20261013/TwinPulse-product-flow-final-report.pdf), [전체 화면과 원 실패를 포함한 단일 HTML](../../outputs/product-flow-20261013/report-complete.html), [결론 JSON](../../outputs/product-flow-20261013/implementation-summary.json). 로컬 개발 자료이며 공개 배포 승인이 아니다.

## 반영한 구조

- ordinary App은 `ProductGenerationActions`/`ProductInferenceScope`/`ProductUsageLedger`를 사용한다. USD1, 매 생성 금액 승인, 가격 만료에 따른 생성 차단을 제거했다. 유효 입력·route/policy SHA·프로젝트/체크포인트 소유권·중복 dispatch·usage/UNKNOWN 기록은 보존한다. 기존 승인/캠페인 자료는 삭제하지 않았고 이번 에이전트 시험 장부는 제품 금액 제한과 별개다.
- `PersistentWorkspace`는 하나의 listener와 고정 Kit에서 프로젝트별 서비스와 context를 교체한다. ticket/epoch/snapshot ACK 이전에는 새 변경을 막는다. JSON/JPEG context와 UI cache fences가 이전 작업의 늦은 결과를 현재 장면에 붙이지 않게 한다. New chat은 기존 launcher restart 파일을 쓰지 않는다. 앱을 완전히 종료 후 재실행하면 OS가 다른 포트를 배정할 수 있지만 New chat마다 재실행하지 않는다.
- generation, queued edit, 비동기 feedback preview와 transaction 응답을 원 user turn에 연결했다. 과거 고지/실패/대화 자료는 보존한다.
- 첫 Nebius 키가 실제 신규 설정이고 기존 설정·사용 가능한 키가 없을 때만 현재 모델 목록 GET으로 Flash/Super route를 자동 적용한다. 기존 route와 credential refs는 자동 교체하지 않는다. 키 저장, metadata 확인, 조합 적용을 UI에서 구분한다. 40k는 요청 상한이며 metadata가 공급자 최대 출력이나 품질을 입증한다는 주장이 아니다.
- 미완성 초안의 `usage_only` 상태를 기존 refinement 계약에 연결했다. 기하·수신/settled 상태·사진 품질·UNKNOWN·실물 권한 기준은 완화하지 않았다. 금액과 별도로 현재 40k/300s request/900s action/12 HTTP/3 Repair 및 소진 재개 guard는 유지한다. 규모별 유한 예산 확대는 별도 잔여다.

## 실제 실패 원인과 회복

첫 `live-01` 텍스트는 성공했지만 장면이 존재하면 USD checkpoint verify에서 Sdf.Layer 임시 참조가 소멸해 전환에 실패했다. 강참조로 보유한 후 `saved-switch-05`는 실제 원 장면 재열기와 세 번 동일 URL 전환을 통과했다. 초기 saved-switch driver의 홈/열린 대화 selector 실패와 설치된 viewport import 경로 오류도 별도 보존했다. 이 준비 시험의 추론 호출은 0이다.

`live-02` 사진 세 건은 정상 수신된 응답의 `financial_scope=usage_only`를 기존 core 계약이 모르는 탓에 `DRAFT_REFINEMENT_OUTCOME_UNKNOWN`으로 거절했다. 금액 제한을 제거한 연결 누락이며 모델 출력 한도 실패가 아니었다.

나머지 Build 실패는 `Existing TwinPulse root is not owned by this extension`이었다. 삭제된 active 카메라를 RTX가 다시 정의해 278바이트 camera-only foreign ancestor를 만들었다. interactive viewport detach만으로는 offscreen capture 참조까지 해제되지 않았다. 현재는 소유권을 먼저 확인하고 원 USD를 durable backup한 뒤 geometry/overlay를 지우되 owned Camera/Light/PhysicsScene identity를 유지한다. empty-project-context는 applied=None/idle/새 compiler이고 이전 revision/fingerprint가 없어 장면 완료나 Run 권한을 뜻하지 않는다. 다음 Build는 기존 camera-preserving hot-build 경로를 재사용한다. 이미 foreign인 root에 owner를 덧붙이거나 삭제해 회복하지 않는다.

빠른 ACK 뒤 pending=None이 되는 경쟁은 지역 event 참조로 수정했다. failed/pending context와 virtual workflow/diagnostics/readiness는 정상 종료에서 정리한다. 해당 fault-edge 전체를 새 실제 이상주입으로 인수한 것은 아니다.

## 실제 실행 결과

| 입력/작업 | 근거 | 결과 | 시간 |
| --- | --- | --- | --- |
| 텍스트 침실 생성 | live-01, c86eb0c2-eeeb-4987-b23e-863b75bfd96a | 현재 frame/저장/reload PASS | 76.871s |
| 공개 침실 사진 | live-03, 5c755f84-19f5-4b64-9e0b-9a1f08a5fe9d / de797bdea03749e9868fe30eabc9ab3b | 17개 현재 표시/저장/reload PASS, 품질 needs_revision | 99.860s |
| 공개 거실 사진 | live-03, 375da391-db62-443f-b631-f14125235b9f / 6be87d87136943bea2cdd084c6c5148b | 17개 현재 표시/저장/reload PASS | 128.430s |
| 식당 혼합 입력 | live-03 원 FAIL → mixed-resume-01 | 원 관측/25개 파라미터/8 HTTP를 이월하고 미완료 검사 1 HTTP만 진행해 현재 25개/저장/reload PASS | 재개 20.091s |
| 자연어 desk1 이동 | feedback-live-01, feedback_eed682ad57894deab5ee2dc4d3115aa6 / 6d5522daa2b64a5b9089223b74924349 | 실제 제안2회: Cancel 원본 유지, Apply/현재 frame/저장, Undo/reload PASS | 별도 미측정 |
| 실제 사진 cold scene의 전환 | saved-photo-switch-01 | 3× New chat→원 대화→Reopen→Build/current frame PASS, 같은 URL/Kit | 추론0 |
| 최종 수정/Undo cold reopen | final-closed-reopen-02 | exact revision/state SHA와 3×전환/rebuild PASS | 추론0 |

desk1은 원 center [2,-1.7]에서 실제 모델 제안 [1.8,-1.7]로 변경됐다. Undo의 plan SHA는 원본 `d1d643e7551f4d55a9f74f7a6b41e09c4087569a080fb11e36c8682f0dfda725`와 동일하다. 닫힌 재열기 후 revision은 `f3ba01905e71a4acb9481da942143909e6ce405137091d2110b9f3bdcd01943c`, state SHA는 `8baa8bdce9f1e9c62360103e4cd55ade4364be01fe3032db3b0a75f8a0d58e26`로 정확히 일치했다. 새 편집 이력이므로 state SHA가 최초 원본과 달라지는 것은 원 형상 복원 실패가 아니다.

식당은 처음부터 다시 생성한 최신 소스 성공으로 집계하지 않는다. 첫6건은 1PASS/5FAIL, 추가3건은 2PASS/1FAIL이며 혼합은 이후 동일 job 재개로 회복했다. 원 FAIL/원 raw/각 source SHA는 보존한다. 이번은 제품 acceptance이며 모델 비교 benchmark나 최적 모델/photorealism/실측 증명이 아니다.

## 호출 비용과 검사

사용자가 승인한 원 추가 USD2/2026-10-13 14:00 KST 및 추가3회 승인 범위를 유지했다. 새로운 생성9개, 동일 job 미완료 재개1개, 자연어 feedback2 HTTP를 포함해 추론 **67 HTTP**, 추정 **USD0.3759000**, usage 미확정 보호 예약 **USD0**다. 공급자 청구서가 아니다. 복사한 잔여 재개 장부의 과거 요청을 새 비용으로 더하지 않았다. 원 과거 비용/UNKNOWN도 초기화하지 않았다. 공식 metadata GET은 최초 시험 준비2와 실제 onboarding2로 별도다.

최종 관련 Python 135 tests(134PASS/1SKIP), refinement 계약15PASS, 별도 중첩30PASS, Web51파일/527PASS, TypeScript/Vite production build PASS다. local fixture 회귀를 실제 LLM 성공으로 집계하지 않는다. 기존 Provider4FAIL은 전체 재시험하지 않았으며 잔여로 보존한다.

최종 dist manifest SHA는 `02fcaf06c7545cd233a7d0407d3e90a9e102252caede242e5bd8129fcb38f96f`; final-closed-reopen-02는 source 동결을 확인했다. HTML의 1440/430px 레이아웃과 28개 embedded 이미지 디코드/가로 넘침0/외부 요청0/페이지 오류0를 확인했다. PDF는 주요 실제 화면4개·수치·실행 ID·원 실패 요약을 한 파일로 제공하며 전체 gallery는 HTML에 있다.

onboarding-live는 현재 metadata GET2와 production gateway 구성, 원 사용자 설정 SHA 불변만 PASS다. 실제 첫 신규 키의 OS 저장/UI 등록 전체 인수는 아직 아니며 해당 단위시험은 metadata fixture다. UI 보조는 GPT-6.1 Sol/high, 독립 설계 검토는 Astra/xhigh를 사용했다. 주 작업자의 채팅 모델은 이 턴에서 변경하지 않았다.

## 남은 작업 순서

1. 미노출 사진/더 큰 inventory/실제 신규 키 등록 전체 UI/장시간 끊김·지연 결과·generation Cancel의 확대 인수. foreign root 보존 등 새 보호 경계의 실제 fault injection.
2. 사진 외형·배치·크기·지지 관계의 품질 검토와 추가 피드백. 현재 품질 미완성·실측 미검증을 유지한다.
3. 규모별 유한 요청·시간 정책과 core refinement 정책 범위의 정합성, 기존4계약 회귀 검토.
4. live LiDAR common commit/Undo/저장 정합과 실제 안전 현장 인수. 실물/Cloud/설치/공개 배포는 이번에 수행하지 않았다.

이전 개인 사진·사용자 runtime 파일은 시험 대상으로 변경하지 않았다. 새 시험은 공개 CC BY-SA3.0 사진만 사용하며 저자 Afifa Afrin/Tim Collins/Stilfehler와 원 링크·변경·라이선스 고지는 보고서에 보존했다. 모든 소유 시험은 정상 종료했다.
