# 현재 Isaac 렌더 → 사진 비교 → 자동 수정 연결

2026-10-10 KST · Baseline v1.0.386 · **제품 연결/오프라인 회귀/실제 로컬 Isaac 통합 PASS, 실제 LLM 사진 품질 NOT_RUN, 전체 PARTIAL / whole=false**

## 이번에 연결한 제품 경로

일반 채팅 입력 → SIM/REAL 선택 → 입력·모델·가격·공통 한도의 명시 생성 승인 → 의미 장면/전체 기하 검사 → idle Isaac preview Build → 현재 JPEG 고정 → 원본 사진+그 렌더를 선택 observer에 비교 요청 → typed 품질 모순 → 기존 planner의 scoped patch → 전체 기하 재검사 → 새 후보 Build/새 렌더 재검토 → 최종 동일 후보 저장. 별도 생성기나 임의 모델 코드 실행을 추가하지 않았다.

- `render_review.py`: 후보 revision/plan SHA/scene revision/engine session/epoch/command/frame/JPEG SHA를 결속한다. 모든 현재 물체 ID의 배치·지지·외형을 consistent/contradiction/uncertain으로 받는다. 높은 신뢰도 모순만 기존 typed 품질 수정으로 넘기고, 시점 차이·가림·실측 없는 크기는 불확실/추정으로 남긴다. 모델의 consistent 응답도 제한된 시각 판단이지 실측 또는 로봇 준비 판정이 아니다.
- `GenerationRenderPort`: 실제 broker/viewport 및 동일 product session ownership 사용. 자동 Build는 `/World/TwinPulse` 미리보기만이며 Run/모터/로봇 명령은 없다. receipt+현재 JPEG 둘 다 필요하고, 엔진/입력/장면이 바뀌면 수락·저장을 거절한다. 기능과 lease에 따른 일시적 command permission은 별도로 검사한다.
- 기존 `BudgetedPipeline`: observer → critic → repair → recapture 모두 하나의 request/repair/time/financial owner 한도. final reserve는 Build 대기와 모든 critic이 나눠 쓰며 checkpoint에도 소비량을 보존한다. 다음 critic 슬롯이 없는 수정은 시작하지 않으며 출력 소진은 즉시 중단한다. invalid critic을 기하 오류로 바꿔 planner에게 재시도시키지 않는다.
- 기존 불변 GenerationStore에 고정 JPEG와 metadata, checkpoint에 render history/quality/typed issue/실패/Build 상태를 저장한다. API에는 안전한 상태·ID·해시만 공개하고 이미지·모델 설명 원문은 공개 진단 DTO에 넣지 않는다. render preview의 실행 span으로 소요시간/실패 원인도 기록한다.
- App 저장 직전에 비교한 plan/scene과 저장 후보를 다시 대조한다. 중간 프리뷰가 있다고 최종 장면이 저장되거나 Run이 승인되는 것은 아니다.
- 설정 `API keys → Model routing → Use experimental staged generation → Compare current Isaac renders with the source photo`는 명시 저장할 때만 적용된다. 기존 사용자 설정은 변경하지 않았고 기본은 OFF다. 생성 승인 카드에 원본+파생 렌더의 외부 전송, idle preview Build, 동일 예산, Run/로봇 없음이 표시된다. 텍스트 전용 생성은 이 선택이 있어도 사진/critic/엔진을 요구하지 않는다.

주요 코드: provider `render_review.py`, `budgeted_pipeline.py`, `generation_policy.py`, `generation_store.py`, `stage_transport.py`; App `generation_render_port.py`, `generation_approval.py`, `generation_scope.py`, `application.py`, `product_workflow_service.py`, `conversation_service.py`, `api.py`; Web 설정/승인/채팅. 새로운 paid scope, 원 사진 전송, 실물 구동, 설치, commit/push, 강제 종료, 에이전트 생성은 0이다.

## 검증과 정확한 증거 범위

| 검증 | 결과 | 의미 |
| --- | --- | --- |
| Provider 전체 | 301 PASS / 최종 6.545초 | 신규 render loop 9개 포함, 고정 transport/zero network |
| App 관련 5 modules | 124 PASS / 60.565초 | real broker/viewport/ordinary approval+audited 고정 HTTP/저장 경로. 신규 render port 10개 포함 |
| Web 전체 | 47 files / 442 PASS / 25.19초 | 별도 집중 53개와 겹침, 합산하지 않음 |
| TypeScript/Vite build, Python/Node 구문 | PASS | 기존 jsdom canvas 및 bundle >500kB 경고 유지 |
| 실제 로컬 Isaac r4 | PASS | 일반 App/실제 JPEG 두 후보/전체 compile/저장/PhysX 도착/Stop/reload/reset/진단/owned 종료 |
| r4 종료 후 독립 read-only ProjectStore 재열기 | PASS | schema2.1/2개 지지 관계/동일 최종 plan·scene/input SHA/원 파일 불변/자동 dispatch0 |
| 실제 외부 LLM 및 침실 사진 충실도 | NOT_RUN | 이번 관측·critic·patch는 합성 source+명시 고정 HTTP 응답 |
| 실측·LiDAR 정합·실물 임무 | NOT_RUN | 로봇 0, 생성 통합 시험의 선행조건이 아님 |

실제 엔진 결과: `outputs/verification/current-render-review-20261010-r4/result.json`. 고정 HTTP 6개(초기3 + critic1 + repair1 + critic1), 승인1, repair1, 외부 network0. fixture 장부의 비용은 고정 usage로 계산한 시험 값이지 실제 청구/LLM 성공률 표본이 아니다. fixture에만 final reserve180/total1020을 명시했으며 사용자 저장 정책/default60/900을 바꾸지 않았다.

실제 capture frame1→4, 후보 `f4e110e5…abc58d`→`182cb66d…cee88`, scene `6010d7f7…33f4e`→`f65d4a81…c73f8`. 새 render key와 JPEG SHA를 감사했고 최종 plan `4113a8d4…cac24`가 저장본과 일치했다. bed의 추정 region rear_left→front_left 변경은 **스크립트로 의도한 오류/회복 fixture**이며 침실 사진 정답이 아니다. 실제 엔진 Build는 preview2 + SIM 준비1, 그 뒤 명시 Run이다. PhysX 최대 변위0.360566047m, goal distance0.039560447m/도착, 다음 임무 Stop 후 paused pose 불변, reload 추가 Build/Run0, reset·host capture PASS, pageerror0, frame 관측201. owned backend/engine false 및 shutdown diagnostics succeeded.

종료 후 독립 재열기는 기존 도구의 `audit_render_review_reopen('outputs/verification/current-render-review-20261010-r4')`를 실행했다. r4 원 result는 덮어쓰지 않았다. future 동일 harness에도 이 감사가 들어가며 새 전체 Isaac 재실행을 했다는 주장은 아니다.

## 최초 실패 보존 및 수정

1. 초기 offline: local import가 ProviderConfigurationError를 가려 UnboundLocalError, 잘못된 token property/expected revision 사용 등 제품 결함을 수정했다. 시험의 InputRevision 필수값/모델 provenance property/claim·payload 및 snapshot sequence 기대도 실제 계약으로 정정했다. 최초 App 합동121 검사 중 신규7 error는 PASS로 세지 않았으며 최종124개는 전부 통과했다.
2. 실제 r1: `RENDER_PREVIEW_CAPABILITY_MISSING`, 모델/Build0. 실제 adapter는 capability가 있어도 owned lease를 아직 관측하지 않은 동안 `build_site_scene` permission을 내주지 않는다. 제품 preflight의 capability/permission 혼동을 수정하고 acquire→bounded bridge permission 확인→submit으로 연결했다. missing capability/running/other lease/timeout/cancel/engine replacement/current input superseded의 음성 검사를 추가했다. gate를 우회하지 않았다.
3. 실제 r2: 렌더2/수정/저장 통과 후 기존 `Build count=1` 시험이 실제3을 거절. 해당 명시 fixture에서만 preview2+SIM준비1을 검사하도록 정정했다. 다른 모드 기대는 유지했다.
4. 실제 r3: SIM 도착·Stop·reload·reset 이후 진단 assertion이 존재하지 않는 `repair_scene` span을 요구. 기존 제품 stage `repair`를 검사하도록 정정했다. 제품 루프 성공과 전체 harness FAIL을 분리하며 r1–r3 결과를 삭제/덮어쓰지 않았다.
5. 실제 r4: 전체 harness PASS + frozen render/최종 저장 identity/장부 audit PASS. preview 대기시간 trace와 checkpoint의 `Build=PREVIEW_ONLY`도 반영했다. 임시/과거 실패/원자료/사용자 설정 및 별도 v3826/10, v3819/10 장부를 수정하거나 합치지 않았다.

## 남은 작업 / 다음 실행

- G3 current-render critic의 **제품 경로 구현 및 고정 응답 통합 인수**는 완료. 실제 모델이 서로 다른 시점·가림·종류·지지를 정확히 판단하는 품질 인수는 미검증이다. 근사 geometry PASS와 사진 품질·실측·실물 PASS는 구분한다.
- G2 복합 packing/domain의 실제 모델 장기 탐색 및 G5 최신 계약의 actual 회복/새 자연 생성은 남아 있다. 유효한 별도 명시 승인(원본 사진과 파생 렌더 목적지·호출/비용/시간 포함)이 있어야 실행한다. 과거 미사용4회를 임의 재바인딩/리셋하지 않는다.
- 다음 actual 검증은 일반 App 승인에서 observer 관측/critic을 선택 이미지 모델로, 구조/patch를 선택 planner(Nebius NVIDIA 조합 보존)로 실행하고 **새 자연 생성과 모순 수정 회복을 따로** 감사한다. critic 출력 cap은 observer 설정이고, 모든 단계는 기존 공유 budget/로그를 쓴다. length/UNKNOWN/예산중단을 성공으로 바꾸지 않는다.
- G6 엔진 연결·저장·SIM의 이번 fixture 범위 PASS와 actual 사진 품질은 별도다. 원 12단계 데모의 도메인·opening/편집 전범위·패키지/규정·현장 정합/자율/Loop·배터리/막힘/Stop 인수도 계속 남는다. 이번 성공은 전체 Full Process 완료 또는 전원만 켜면 실물 데모 완료라는 뜻이 아니다.
