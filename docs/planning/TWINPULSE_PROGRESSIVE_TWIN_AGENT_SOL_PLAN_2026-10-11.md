# TwinPulse 점진적 장면 생성과 피드백 수정 에이전트 구현 계획

최종 야간 기준 **v1.0.460**: G2 수정·ordinary Undo·저장/실패복구·G3 fresh 자연어 이동/크기피드백, G4 완료 survey Import/공통 수동 보정/Undo/목표 재계획과 네 입력 저장본의 최종 제품 actualPhysX/Stop/reset/closedrestart는 해당 범위 PASS다. native1.1/fullrefinement1.0 actual은 명시 합성 품질·위험 보존 인수이며 사진품질 PASS가 아니다. **다음 구현은 live 자동 결과의 공통 commit/Undo 연결**, 이후 신선한 현장 센서/안전/정합 인수다. 저장SIM→REAL 일반전환은 아직없다. 새 모델·사진/실물시험은 이번 승인기간 이후 새승인 없이는 시작하지 않는다. [최종 실제화면·ID·비용·잔여](../../outputs/progressive-twin-overnight-20261012/report-final.html) · [검증 기록](../verification/progressive-twin-overnight-20261012.md). 아래 체크포인트는 과거 이력이다.

야간 최신 **v1.0.459**: nativepending/refinement1.1 실제 편집·Undo·목표차단·저장 복원 및 같은bed robot사진Twin actualPhysX/Stop/reset/closedrestart가 PASS다. 원01FAIL은 보존한다. 최종source의 text/photo/dining 저장본 재인수를 순서대로 진행하며 fullrefinement1.0 actual/실물LiDAR/전체현장은 미검증이다. 아래 항목은 당시 이력이다. [최신 근거](../verification/progressive-twin-overnight-20261012.md).

야간 최신 **v1.0.458**: 같은 침대 원 scene/start의 안전경로 누락 두정책을 범용 bounded core에서 수정·영향회귀/독립검토 통과했다. nativeactual01 네실제tx/기대goalblock뒤 driverstrictFAIL은 원FAIL로 보존하고 helper-only02를 진행한다. samebedactual·최종source 재인수 및 fullrefinement1.0 actual은 아직미검증이다. [최신 근거](../verification/progressive-twin-overnight-20261012.md).

야간 최신 **v1.0.457**: 네 입력은 각 source에서 실제 생성/current/reload/closed exactstate 기능PASS. fresh15 로봇사진은 위험pending/품질1.1 분기에 들어가지 않아 별도 명시합성 actual 인수가 필요하며, 저장본 침대 목표는 접근 경로 FAIL/Run0로 보존·원인분석중이다. 실물/사진정밀도/전체완료는 주장하지 않는다. [최신 근거](../verification/progressive-twin-overnight-20261012.md).

야간 최신 **v1.0.456**: 위험 보존 pending·materialized subset/품질 미완성 durable 계약은 local/독립검토 완료, fresh15 actual 인수 진행 중이다. source/Web/dist/helper 동결·wholegeometry/품질PASS/주행권한승격0·원14FAIL 보존. [최신 인수 기록](../verification/progressive-twin-overnight-20261012.md). 아래는 이전 체크포인트다.

야간 최신 체크포인트 **v1.0.455**: fresh14 원 support/floor FAIL과 정확한 모델 수정 이력을 보존했다. 위험 소품의 지지 실패도 draft-only pending/보수적 keepout으로 남기는 범용 subset 계약을 보강 중이며 wholegeometry/품질PASS·SIM/REAL권한을 부여하지 않는다. 실제 인수 전에는 완료로 표시하지 않는다. [최신 원인과 범위](../verification/progressive-twin-overnight-20261012.md). 아래 체크포인트는 당시 이력이다.

야간 최신 체크포인트 **v1.0.454**: 기하 유효 초안과 사진 품질 미완성을 분리하는 durable 계약을 local 회귀·독립 읽기 검토로 확인했다. 실제 새 source 인수는 아직 NOT_RUN이며 아래 v453의 품질 gate 원FAIL은 보존한다. 기존 provider 변경 invalidation의 unreachable 회귀도 원FAIL을 남기고 최소 복구한다. [현재 증거와 다음 actual](../verification/progressive-twin-overnight-20261012.md).

작성일: 2026-10-11. 실행 담당: GPT 6.1 Sol. 기준 저장소: `C:\Users\jaewo\Documents\TwinPulse`. 방향 결정: Baseline v1.0.432. 최초 점진초안 구현 v1.0.433, 최신 야간 인수 v1.0.460. 상태: **G2/G3 및 완료 survey의 수동 common 경로, 네 입력의 해당source 실제 생성과 최종 제품 저장본SIM은 인수했다. live 자동 commoncommit/Undo 구현과 실제 LiDAR 안전/정합·전체현장 인수는 남는다.** 원433과 이후 source별 결과를 합산하거나 원 FAIL을 승격하지 않는다. [최초 구현](../verification/progressive-twin-20261011.md) · [야간 실제 화면·ID·실패·잔여](../verification/progressive-twin-overnight-20261012.md).

목표는 사진을 한 번에 완벽하게 복제하는 프로그램이 아니다. **텍스트·사진에서 주요 구조와 물체를 갖춘 수정 가능한 Twin을 만들고, 실행 결과·사람의 말·로봇 관측으로 점진적으로 개선하는 에이전트**다. 불확실성과 미해결 물체를 보존하면서 유효한 결과를 먼저 제공한다. 초안, 특정 SIM 작업, 실물 준비, 시각 품질은 서로 다른 판정이다.

이 문서는 기존 [Physical AI 제출 계획](TWINPULSE_PHYSICAL_AI_SUBMISSION_SOL_PLAN_2026-10-11.md)의 P1·P2·P4 중 생성 판정·수정 루프·피드백 연결의 최신 실행 기준이다. 충돌하는 경우 이 문서의 새 판정 기준을 앞으로의 구현에 적용한다. 기존 [12단계 채팅 데모](TWINPULSE_CHAT_DRIVEN_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-05.md), 모델 선택, 안전 조건, Cloud·현장·영상·라이선스·제출 잔여는 폐기하지 않는다. 기존 실패 기록과 과거 시험의 평가 기준은 변경하지 않는다.

최초 요청은 계획서 작성이었으며, 이후 사용자가 로컬 구현 진행을 승인했다. 계획에 적힌 미래 단계 자체가 유료 호출, 로봇 접속, Cloud 생성, 설치 또는 공개 승인이라는 뜻은 아니다. 해당 작업은 별도 유효 승인 범위에서만 실행한다.

## 1 사용자 의도와 변경하는 우선순위

사용자의 핵심 원문:

> 성공판정에 대한 기준이 너무 과도해서 진도가 안나갈수도 있을것 같은데 또 어떻게보면 실제로 로봇이 위치수정을 할정도면 실제 물체들이 대략적으로라도 다 반영되어있긴 해야할것같거든.
>
> 내가 구상하는건 코딩에이전트처럼 LLM이 코드작성하고 실행하고 실패하면 다시 실행하고 이런식으로 어느정도 검증한다음 사람이 써보고 피드백 내용을 말로 해주면 그걸 토대로 반영해서 수정하고 이런내용처럼
> 글이나 사진, 동영상을 넣고 업로드하면 LLM이 그걸 기반으로 코드작성하고 설계하고 실행하고 실패하면 다시 재구성하고 성공한다음 로봇이 재검증해서 그걸 토대로 다시 구성하고. 사람이 말하면 그 피드백도 받고.

이를 다음 원칙으로 구현한다.

1. 주요 구조·가구를 만들고 실제 실행한다. 불필요한 소품 정밀도를 방 전체 생성의 선행 조건으로 만들지 않는다.
2. 오류는 해당 영향 범위에서 고친다. 먼저 배치한 물체·부모·추정 치수도 근거가 있으면 다시 수정할 수 있다.
3. 해결 못한 물체를 삭제하거나 충돌 검사를 끄고 성공 처리하지 않는다. 유효 장면과 미해결 목록이 함께 남아야 한다.
4. 사용자용 3D는 침대·옷장·행거 등을 식별할 수 있는 크기 조절형 라이브러리 모델을 유지한다. 조감도·충돌용 단순 형상과 구별한다.
5. 사진 추정은 현실의 정답이 아니다. 실물 이동은 최신 센서·정합·정지·경로 검증과 명시 승인에 따른다.
6. 텍스트만으로도 동작해야 한다. 영상 입력은 공통 관측 경로로 확장하되, 지금의 필수 완료 조건으로 삼지 않는다.
7. 실제 작업용 LLM 출력은 기존 검증 가능한 장면 명령·패치다. 임의의 모델 생성 Python·셸을 실행하는 시스템으로 바꾸지 않는다.

**우선순위 변경:** 식당의 모든 층별 소품 지지를 완벽하게 만든 다음 진행하는 순서에서, `판정 분리 → 유효 초안과 미해결 보존 → 의존 관계 수정·되돌리기 → 사람 피드백 → 센서 피드백 → 실제 통합 인수`로 바꾼다. 층별 지지는 범용 수정의 한 기능이지 모든 후속 작업을 막는 독립 연구 과제가 아니다.

## 2 현재 구현과 확인된 한계

현재 사실의 근거는 [v431 검증 기록](../verification/warehouse-semantic-support-20261011.md#수정본-3건-종료와-실제-기능-재인수--v431)과 [실제 화면 포함 보고서](../../outputs/physical-ai-p2-20261011-v431/final-evidence/report.html)다.

- 최신 승인 3건에서 창고 텍스트·거실 사진은 실제 생성, Isaac 현재 화면, 원 명명 목표 이동, 별도 이동 중 Stop, 저장·닫힌 재열기까지 기능 통과했다. 식당 사진은 실제 수정 3회 후 `REPAIR_STALLED`로 실패했다.
- 거실의 시각 critic은 `uncertain`이다. 기능 2/3을 사진 충실도·실측·전체 데모 성공으로 표현하지 않는다.
- 식당은 매트·접시·잔을 같은 상판의 비중첩 형제로 다루다가 막혔다. 소품 간 층별 지지 표현 한계가 영향을 줄 수 있으나, 특정 후보가 반드시 해를 가진다는 증명은 아니다. 탐색 한도 소진은 전역 배치 불가능의 증명이 아니다.
- 최근 실패는 빈 최종 응답·40k 출력 소진·300초 timeout이 아니었다. 지금 토큰·시간 상한을 늘리는 것이 첫 해결책은 아니다.

| 영역 | 이미 있는 기반 | 실제 보완할 부분 |
|---|---|---|
| 물체 표현 | 크기 조절형 가구·소품 라이브러리, 시각/충돌/얽힘/unknown 구분 | robot envelope·작업·불확실성 기준의 판정 정책. 현 소품 visual 판정에는 고정 높이 기준이 있어 이미 범용이라고 주장하지 않음 |
| 생성 | 관측·설계·검사·수정, 저장 후보와 원본 로그 | 잔여 소품 지지 오류가 전체 plan 반환을 막는 결합 해소 |
| 복구 | bounded 재배치, scope 검사, 마지막 유효 후보 보존 | 부모·자식·치수·관계의 공동 수정과 부분 결과의 명시적 채택 |
| 자연어 편집 | 한 가구 중심의 제안, preview/apply/cancel, history/Undo | 소품·방·다중 객체·의존 관계 편집을 일반 채팅에서 공통 패치로 연결 |
| 센서 | 저장 scan 검토, 정합, bounded wall correction, derived revision | 생성·사용자 수정과 일관된 변경 기록 및 계획 무효화. 모든 가구의 자동 3D 재구성이 완료된 것은 아님 |
| 사용자 화면 | chat-first, 실제 Twin 화면, 단계별 질문 기반 | 판정 축과 보완 목록, 현재 유효 revision, 한 번에 한 결정의 일관성 |

새 agent framework나 별도 성공용 endpoint를 만들지 않는다. 다음 기존 모듈을 우선 재사용한다. 경로는 저장소 기준 상대 경로이며 구현 시 실제 호출 관계를 재확인한다.

| 책임 | 기존 연결 지점 |
|---|---|
| 컴파일·geometry 진단 | `packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py`, `support_packing.py`, `semantic_scene.py`, `scene_contract.py`; `packages/twinpulse_core/src/twinpulse_core/geometry_diagnostics.py`, `photo_placement.py`, `photo_quality.py`, `room_items.py` |
| 생성·수정 정책·저장 | provider의 `budgeted_pipeline.py`, `repair_scope.py`, `generation_policy.py`, `generation_store.py`, `output_diagnostics.py` |
| App 편집·revision | `packages/twinpulse_app/src/twinpulse_app/scene_changes.py`, `scene_edit_proposals.py`, `application.py`, provider의 `scene_edit_provider.py` |
| 렌더·목표·안전 | App의 `generation_render_port.py`, `chat_goal_navigation.py`, `mission_admission.py`; core의 `simulation_goal.py` |
| 센서 보정 | core의 `scan_correction.py`, `sensor_map_localization.py`, `automatic_photo_alignment.py`; App의 `mission_photo_correction.py`, `automatic_mission_service.py` |
| UI | `apps/twinpulse-web/src/ChatWorkspace.tsx`, `SceneEditReview.tsx`, `ChatRobotStatus.tsx`, `ExecutionDiagnostics.tsx` |

## 3 판정 계약

### 3.1 네 가지 판정은 독립적으로 저장한다

아래 이름은 신규 계약의 권장 의미다. 기존 호환성 조사 후 이름을 확정하되 의미를 합치지 않는다. 각 판정에는 `criteria_version`, scene revision, 평가 시각, 근거 ID, 차단 사유가 있어야 한다.

| 판정 축 | 최소 통과 조건 | 아직 남을 수 있는 것 |
|---|---|---|
| 초안 사용 가능 `draft_ready` | 유효 장면 계약, 주요 구조·핵심 물체의 식별 가능한 표현, 실제 현재 revision Build/렌더, 저장 완료, 미해결 목록의 연결 | 실측 없는 크기 추정, 주행과 무관한 소품 세부 |
| 해당 SIM 작업 검증 `sim_task_pass` | 특정 scene/task/robot profile에 결속된 목표 해석·경로·실제 이동·도달 증거. 정지 기능의 유효 인수 근거는 별도로 유지 | 비관련 시각 보완. 다른 목표·다른 revision의 성공은 아님 |
| 실물 작업 준비 `real_task_ready` | 현재 boot/release, 센서·위치·정합·경로·정지·통신·배터리 등 기존 안전 조건 충족 | 실물 이동과 무관한 외관 세부. 준비와 실행 승인은 별개 |
| 시각 품질 `visual_review` | 주요 종류 식별·상대 배치·누락과 지지 표현을 별도로 검토 | `needs_review`, `needs_refinement`, `unmeasured` 등. 사람 검토 미실시는 그대로 표시 |

예: `초안 사용 가능 / 의자 접근 SIM 검증 완료 / 실물 미검증 / 소품 3개 보완 필요`는 유효한 결과다. 하나의 전역 `success=true`로 축약하지 않는다. 실패 후보를 진단 화면에서 볼 수 있다는 사실과 초안 인수 통과도 구분한다.

**제품 능력 인수와 매번 실행하는 검사는 구분한다.** G5/G6에서는 닫힌 재열기·별도 moving Stop/stable을 반드시 검증하지만, 사용자가 매번 장면을 생성할 때 닫았다 다시 열거나 정지 시험을 반복해야 다음으로 넘어가게 만들지 않는다. 현재 scene/task의 경로·도달은 그 revision의 근거를 사용하고, 정지 기능·저장 복원의 인수 기록은 호환되는 source/engine/robot profile 범위에서 재사용한다. 변경으로 관련 근거가 무효화되면 영향 범위만 재시험한다. 실물 정지 기록의 boot/release별 유효성은 기존 안전 계약을 그대로 따른다.

`real_task_ready`는 모터 실행 권한이 아니다. 별도의 현재 사용자 승인·임무 입장 검사를 통과해야 한다. 센서·pose가 stale이면 readiness가 즉시 만료된다. 과거 ready를 저장 프로젝트에서 복원하지 않는다.

### 3.2 실패의 영향 범위

| 유형 | 처리 |
|---|---|
| 파싱·스키마·비정상 수치·깨진 참조·권한 위반 | 해당 후보 거절. 잘린 JSON을 유효한 장면으로 추측 복구하지 않음. 마지막 유효 revision은 보존 |
| 구조 또는 필수 주요 물체의 미해결 | 진단/부분 preview는 가능하나 완전한 입력 반영이나 초안 ready로 위장하지 않음. 필요한 최소 질문 또는 수정 수행 |
| 특정 경로·목표의 충돌 또는 정보 부족 | 해당 작업 차단. 이미 유효한 장면을 없애거나 다른 모든 검토를 막지 않음 |
| 현재 로봇 움직임과 무관함이 확인된 시각 소품 오류 | 유효 초안 유지, 소품은 pending/deferred로 남기고 해당 주행과 독립 평가 |
| 위험 관련성 불명확 | LLM이 장식으로 강등하지 못함. 근거 있는 경계가 있으면 보수적 keepout, 경계도 모르면 영향받는 실물 작업 보류 |
| 비용·승인·기한·출력 한도·미정산 종료 | 원 보호 중단 유지. 사용할 수 있는 기존 결과를 표시하되 생성/수정 성공으로 바꾸지 않음 |

객체 이름에 따른 `plate=optional` 같은 특례를 금지한다. robot body/footprint/높이, 이동 중 점유 공간, 물체의 높이·위치 불확실성, 얽힘·돌출 가능성, 현재 목표 관련성으로 판단한다. 센서가 보지 못한 높이를 안전하다고 간주하지 않는다. 새 정책은 버전 관리하고 기존 안전 경계를 근거 없이 줄이지 않는다.

### 3.3 현실 충실도와 사용 가능성을 혼동하지 않는다

- 입력에서 식별된 물체의 원 ID·개수·관계·출처를 유지한다. 물체가 `rendered`, `deferred`, `unresolved`, `contradicted` 중 어디에 있는지 추적하고 합계가 사라지지 않아야 한다. 이 목록은 관측기가 실제 세계의 모든 물체를 발견했다는 증거가 아니다.
- 주요 물체는 이름만 남기거나 전부 unknown 박스로 바꿔 품질을 통과시키지 않는다. 미지원 모델은 명시된 임시 표현과 보완 상태로 남긴다.
- 치수는 실측·사용자 진술·사진 추정·센서 추정을 구분한다. 미실측 10×12m 추정 자체는 실패가 아니다. 임의로 사진별 정답 치수를 강제하지 않는다.
- 주요 물체/작업 필수 항목은 시험 전에 정의하고 실패 후 목록을 줄이지 않는다. 사용자 요청에 명시된 물체는 그 요청의 충족 여부에서 빠지지 않는다.
- 사진 미관측 영역은 unknown이다. 시뮬레이터에서 비어 보이거나 모델이 자신 있다고 말한 것만으로 실물 free-space가 되지 않는다.

## 4 유효 장면과 미해결 목록의 저장 구조

기존 scene 계약을 무조건 깨거나 v1/v2 reader를 새 의미로 조용히 변경하지 않는다. 버전이 있는 생성 결과 envelope 또는 연결된 별도 레코드를 도입하고 기존 reader를 보존한다. 새 상태를 모르는 클라이언트는 보수적으로 실행을 잠그고 명시적인 설명을 보여준다.

최소 데이터:

- 원 입력·관측·개체 ID와 provenance, 원본 SHA.
- 유효한 scene revision과 현재 materialized 객체 ID 목록.
- 미해결 객체/관계의 ID, 원 parent 후보, 오류와 근거, 영향받는 객체/작업, uncertainty, 처리 상태, 필요한 다음 정보.
- 네 판정 축, 정책 버전, robot/task context 또는 아직 없다는 상태.
- source revision → patch → candidate → 검사 → commit/rollback의 연결.
- 현재 revision·camera와 결속된 렌더 receipt, 평가/목표/센서 근거의 유효기간.

유효하지 않은 객체를 엔진에 억지로 넘기지 않는다. pending 목록에 남기거나 위치 근거가 있을 때만 명확한 미확정 표시를 사용한다. diagnostic ghost는 물리 충돌체나 검증 완료 물체로 오인되지 않아야 한다. unresolved 위치가 주행에 영향을 주면 해당 위험 표시는 렌더 생략과 무관하게 남는다.

부모가 미해결이면 자식도 해당 의존 관계로 처리한다. 누락된 parent를 임의 가구로 바꾸거나 소품을 바닥에 내려놓아 성공시키지 않는다. 장면·미해결 목록·revision 메타데이터가 원자적으로 저장되어야 하며, 하나만 저장된 손상 상태는 복원 검사에서 거절한다.

## 5 공통 수정 루프

기본 흐름은 `입력/피드백 → 구조화 제안 → 영향 범위 → 후보 적용 → 검사 → 새 렌더 → 채택 또는 rollback → 판정 갱신`이다. 최종 자연어 응답은 실제 변경 결과를 설명하며 실행 증거를 대신하지 않는다.

### 5.1 수정 대상과 의존 관계

- 동일 물체 재수정을 허용한다. 같은 patch 반복과 새로운 근거를 가진 재수정을 구분한다.
- 부모·자식·치수·위치·방향·지지 관계를 함께 수정하는 트랜잭션을 지원한다. 관련 없는 객체는 원래 digest를 유지한다.
- 방 크기·벽 위치 같은 넓은 변경은 근거와 영향 범위를 명시한다. 후보 수정 중에는 가능하지만 사용자가 확인한 실측 제약을 모델이 몰래 바꾸지 못한다.
- nested support는 순환 없는 부모 관계와 실제 지지면/높이를 검증한다. 부모 자식의 의도된 XY 중첩을 모든 형제의 충돌과 혼동하지 않는다. 정상 지지와 실제 관통은 구분한다.
- 모델은 검사 오류의 수치, 관련 객체, 부모 geometry, 이미 시도한 변경과 결과를 받는다. 실행기 오류를 모호한 “다시 해라” 한 줄로 축약하지 않는다.
- `defer`는 명시 operation·이유·영향 분류를 가져야 한다. 해소된 오류가 아니라 남은 항목이다. 사용자 요청으로 물체를 제거할 때도 revision history와 원 관측은 보존한다.

### 5.2 실행과 되돌리기

기존 history·source SHA·stale-parent 검사를 확장한다. 최소 `move/resize/rotate`, `add`, `reparent`, `defer/restore`, 승인된 `remove`, 관련 객체 묶음 변경을 표현한다. 실제 API 이름은 구현 시작에 확정하고 중복 저장소를 만들지 않는다.

후보 생성 중에는 자동 수정할 수 있지만, 사용자가 이미 보고 사용하는 장면의 자연어 편집은 기존 preview/apply/cancel 경로를 유지한다. 실제 적용은 선택한 후보와 현재 revision에 결속하고 중복 클릭은 멱등 처리한다. 엔진 Build 또는 저장 실패 시 새 화면이 성공한 것처럼 표시하지 않는다.

파일과 Isaac을 하나의 원자 트랜잭션으로 가정하지 않는다. 기존 소유 작업 구조 위에 `후보 staging → 변경 의도 journal → revision에 결속된 engine ACK → durable commit → 재시작 시 대조·복구` 상태를 정의한다. 실패 시 이전 상태로 되돌리는 보상 작업의 ACK까지 확인한 경우에만 복구됐다고 표시한다. 엔진 응답 유실·프로세스 중단 등으로 실제 상태가 확인되지 않으면 `ENGINE_STATE_UNKNOWN`으로 실행을 잠그고 현재 화면을 검증 완료로 표시하지 않는다. 재시작 reconciliation으로 engine·저장 revision을 대조한 뒤 복구한다. 새 분산 프레임워크 도입보다 기존 journal/receipt와 작업 소유권을 확장한다.

Undo도 새로운 revision이다. 과거 목표·경로·실물 승인·센서 인증을 되살리지 않는다. revision이 달라지면 관련 계획을 무효화하고 재계산한다. 첫 구현에서는 범용 기하 변경의 목표·실행 계획을 보수적으로 전부 무효화해도 되며, 정밀 의존성 최적화가 선행 조건은 아니다.

로봇이 움직이는 중에는 기하 commit하지 않는다. 관련 변경이면 기존 안전 정지·idle 확인을 거친 뒤 적용하고 다시 입장 검사를 한다. 자동 재출발하지 않는다. 관측 업데이트 자체와 실제 지도/장면 변경은 구별한다.

### 5.3 정체와 종료

기존 제한된 반복 구조를 유지한다. 후보 평가는 치명 오류, 작업 안전, 주요 구조/물체 유지, 명시 제약 충족, 시각 개선을 나눠 비교한다. 오류 개수만 줄이려고 물체를 지우거나 큰 물체를 불합리하게 축소하지 못하게 한다.

같은 상태를 되풀이하면 `해당 범위·예산에서 미해결`로 종료하고 마지막 유효 결과와 보완 항목을 제공한다. “현실적으로 불가능”으로 단정하지 않는다. 추가 정보로 해결할 수 있으면 한 번에 하나의 질문을 한다. LLM·검사기·렌더 critic 의견이 충돌하면 근거와 불확실성을 남기며 자기평가만으로 통과하지 않는다.

## 6 사람과 센서 피드백의 차이와 공통점

두 피드백은 patch/검사/commit/Undo 경로를 공유하지만 권위는 합치지 않는다.

| 피드백 | 반영 예 | 주의 |
|---|---|---|
| 사람의 자연어 | “옷장은 반대 벽”, “침대를 줄여줘”, “이 물체는 빼줘” | 의도 확인은 실측·센서 정합 증명이 아님. 복수 대상이면 먼저 질문 |
| 실제 scan/odom/TF | 위치 재추정, 관측된 벽과 추정 벽의 차이, 새 장애물 | 2D scan이 색·전체 높이·상판 소품까지 검증하지 않음 |
| 렌더·시뮬레이션 검사 | 떠 있는 물체, 잘못된 종류, 충돌·도달 실패 | 합성 장면 내부 일관성이지 현실과의 일치 증명이 아님 |

실물은 두 경로를 분리한다. `로봇이 다른 곳에 놓임 → pose 재정합`과 `환경의 벽/물체가 실제로 다름 → 장면 수정`을 혼동하지 않는다. 수동으로 옮긴 로봇의 pose 차이를 방 전체 변형으로 해결하지 않는다.

센서 원 관측·시각·frame/extrinsics·map revision·등록 근거를 보존한다. 기존 bounded wall correction 범위에서 근거가 충분하면 승인된 검사 임무 안에서 새 후보를 만들 수 있지만, 모든 가구 재구성까지 자동 확장하지 않는다. 대응이 모호하거나 범위 밖이면 정지/추가 관측/최소 질문으로 전환한다. geometry 변경 후 목표·경로·3D와 현재 pose 결속을 다시 검증한다.

저장 scan replay 통과는 연결 구조의 검증이다. 실제 로봇 관측·보정·이동 인수로 기록하지 않는다. 현장 센서가 부족하면 카메라·깊이 센서 등을 추후 검토할 수 있으나 이 계획으로 새 장비·설치를 요구하지 않는다.

## 7 사용자 화면과 일반 제품 경로

사용자가 보게 될 기본 흐름:

1. 텍스트 또는 사진+텍스트 입력.
2. 실물 유무 질문 한 개. 필요한 선택지는 같은 질문 안에 표시.
3. 관측·설계·검사·수정·Isaac 준비의 현재 상태를 표시하고 자동 단계에는 불필요한 클릭을 요구하지 않음.
4. 현재 Twin과 `초안 사용 가능 / 실물 미검증 / 소품 보완 필요` 요약. 보완 목록과 기술 상세는 접기.
5. 자연어 편집 또는 목표 요청. 편집 시 변경 preview와 적용/취소, 이동 시 현재 계획의 SIM 실행 안내.
6. 실제 이동·정지 결과를 표시. 실물은 별도 준비와 현재 승인 이후에만 실행.

채팅의 현재 단계·대기 이유·다음 행동을 고정 영역에서 확인할 수 있어야 한다. 과거 질문 버튼은 기록으로만 남고 재실행되지 않는다. 한 번에 주 질문/주 행동 하나를 활성화한다. 질문의 대안과 취소·Force STOP은 예외다. 안전 정지 접근성을 줄이지 않는다.

`Isaac 연결됨`, `초안 컴파일됨`, `현재 3D 표시됨`, `해당 SIM 작업 통과`를 같은 상태로 표시하지 않는다. 이전 revision의 화면·pose·scan은 현재 증거처럼 보이지 않게 한다. 현재 화면이 없으면 그 이유와 상태를 명확히 표시한다.

예시 메시지:

> 방과 주요 가구를 만들었습니다. 식탁 위 소품 3개는 배치를 더 확인해야 합니다. 현재 초안을 확인하고 말로 수정할 수 있습니다. 실물 주행은 아직 검증하지 않았습니다.

화면 레이아웃을 다시 전면 교체하거나 개발자용 검사 버튼을 대량 추가하지 않는다. 기존 ChatGPT형 대화·질문 카드·접을 수 있는 Twin을 개선한다. 초기 구현 언어는 기존 제품 관례를 보존하되 사용자 안내에는 원인과 다음 행동을 쉬운 문장으로 적는다.

## 8 의존성 순서와 단계별 완료 조건

G0 계약 회귀와 G1의 제한된 정적 초안 범위가 v433에서 통과했다. 원 식당23개 중18개 actualIsaac 표시·5개 보완 보존·저장/재열기와 ordinary fixture App/API/UI 회귀를 확인했다. 전체 robot/task envelope가 아직 없으므로 pending 작업은 모두 차단하며 새 모델·사진품질·실제browser 전체여정의 통과가 아니다. 다음은 G2다. 아래 단계 이름은 신규 작업 단위이며 기존 P0–P7의 실적을 재명명하지 않는다. 안전한 로컬 작업은 불필요한 재승인·시간 채우기 없이 진행한다.

### G0 현재 실패 재현과 판정 계약

- 현재 dirty 변경·owner·frozen cohort 상태를 확인한다. 실행 중인 소유 시험이 있으면 소스 변경·중복 시험 금지.
- 원 식당 후보와 실패를 변경 없이 재생하고, 전체 반환이 막히는 지점을 회귀로 고정한다.
- 네 판정 축, 영향 범위, unresolved 상태, 정책 버전과 저장 호환성을 정의한다. 기존 Bool 사용 지점을 모두 찾아 소비자 목록을 남긴다.
- **완료:** 같은 소품 오류를 상판 비관련/바닥 경로 관련 두 상황으로 분류하는 순수 회귀가 통과한다. 후자를 advisory로 강등하지 않는다. 기존 FAIL을 수정하지 않는다.

### G1 유효 초안과 미해결 목록을 실제 생성 경로에 연결

- pure compiler가 검증된 결과와 structured issues를 반환할 경계를 만들고, 손상 객체는 엔진 호출에서 분리한다.
- pipeline/store/App의 결과를 함께 확장한다. 일부 소품 오류 때문에 유효한 방 전체가 사라지지 않게 한다.
- 필수 주요 물체 누락, 부모 누락, 미확정 위험 범위는 각각 draft/task 제한으로 남긴다. 추정치만 있다는 이유로 모든 초안을 차단하지 않는다.
- **완료:** 원 실패 재생과 범용 합성 반례에서 유효 부분 저장·재열기·원 개체 추적이 통과한다. 실제 Isaac의 새 revision Build/렌더·저장/재열기를 확인한 경우만 `DRAFT_RUNTIME_ACCEPTED`를 기록한다.
- **첫 사용자 확인 지점:** 유효한 방 3D와 “소품 보완 필요”가 같이 보이고, 다른 목표 작업 여부는 별도로 판단되는 화면. 모든 nested 소품 완성을 기다리지 않는다.

### G2 의존 관계 패치와 되돌리기

- 기존 scene history에 묶음 수정·재부모화·defer/restore를 연결한다. 방/벽 변경은 별도 타입과 범위 검사를 둔다.
- 부모 치수 변경 시 자식 재배치·목표 영향, nested support의 정상 접촉과 실제 관통, stale revision 거절, 중간 실패 rollback을 구현한다.
- 불필요한 전체 재생성보다 관련 객체 공동 수정을 우선한다. 표현할 수 없는 관계는 명시적 unresolved로 유지한다.
- **완료:** 이전 물체 재배치로 해결되는 사례, 여러 번 같은 물체를 고쳐 회복하는 사례, 실패 후보 취소/Undo/닫힌 재열기, 비대상 digest 보존, 계획 무효화가 통과한다. commit 전후 프로세스 중단·저장 실패·engine ACK 유실의 주입에서 확인 없는 복구 성공을 표시하지 않는다. 원자료를 변경하지 않는다.

### G3 일반 채팅과 현재 상태 표시

- 생성과 편집이 동일한 판정·patch 서비스를 사용하도록 ordinary App/API에 연결한다.
- 한 가구 regex 경로만 통과시키지 말고 모델 기반 제안의 객체 선택·관계·범위·preview/apply를 연결한다.
- 한 번에 한 결정, 단계 진행, 보완 목록, 취소, Stop, current-render/stale 상태를 desktop/mobile에서 검증한다.
- **완료:** 위치 변경, 크기 변경, 여러 대상 중 질문, 틀린 수정 취소, Undo, 재열기, 편집 뒤 목표 재계획의 UI/API 회귀. 저장응답·mock 결과와 실제 LLM 결과는 구분한다. 실제 LLM 인수는 G6에서 수행한다.

### G4 센서 피드백 연결을 로봇 없이 검증

- 저장 scan/odom/TF와 합성 오차를 기존 정합·bounded wall correction에 넣고 공통 revision/patch 기록으로 연결한다.
- pose만 달라진 경우, 벽 변화, 모호한 대응, 관측 부족, 수동 재배치, 센서 stale, 허용 범위 밖 변경을 구별한다.
- **완료:** 안전한 범위의 후보 보정→derived revision→목표/3D 재검증이 저장자료 경로에서 통과하고, 불명확한 입력은 실제 이동 권한 없이 보류된다. live robot 결과는 `NOT_RUN`이다.

#### G4 후속 — live automatic 결과의 공통 commit/Undo 연결(미완료, v460 유지)

현재 `automatic_demo_service.py`의 `photo_store.append`와 `automatic_mission_service.py`의 `RECOMPOSITION_REQUIRED`는 `AutomaticPhotoStore` 별도 derived ledger 경로다. 완료 survey→`Import saved survey`→`SceneSensorReview`→`SceneEditTransaction`/`SceneChangeHistory`의 **수동 common Apply/Undo·목표 재계획만** 실제 인수했다. live 결과의 자동 handoff/common commit 연결은 아직 미구현이며 이 절은 새 실적이나 실행 승인이 아니다. 기존 ledger·원 raw·FAIL을 보존한다. 새 live 공통 경로에서는 보정 결과를 proposal-only로 handoff하고 공통 v2 transaction만 geometry를 commit하도록 설계한다. 동일 보정의 legacy append/common commit 중복은 0이어야 하며, 기존 legacy ledger/raw는 읽기·보존하고 derived guard 우회·기존 기록 자동 이관은 하지 않는다. 이 새 경로는 아직 미구현이며 기존 legacy 기본 동작은 유지한다.

다음 구현 순서:

1. live worker lock 안에서 공통 transaction을 직접 재진입하지 않는다. worker 밖의 handoff가 robot-idle·survey-terminal·정지/cleanup·완전한 raw export를 확인한 뒤, 현재 original/input·scene revision/stateSHA와 raw/footer/report/index/map SHA, boot/release·센서 시각/offset·geometry provenance를 재검증한다. 불명확하거나 stale이면 HELD로 남기며 REAL busy/UNKNOWN guard를 완화하지 않는다.
2. pose-only와 geometry 변경을 분리하고 기존 bounded wall 검사(최대 2벽·XY 0.20m)를 통과한 typed proposal만 현재 상태에 결속한다. 비대상 geometry·placement·pending 위험/keepout은 유지한다. 기존 preview의 명시 승인 또는 동일 Start에서 사전 명시 승인한 bounded 보정 grant가 현재 project·원 revision/stateSHA·mission·boot/release·허용벽/범위·유효기간·한 번의 commit에 결속돼 유효한 경우, 공통 v2 경로의 적용 전/ACK 후 provenance 재검사→actual engine ACK→durable commit을 거친다. 유효 Start grant의 범위 안에서는 추가 클릭 없이 common commit하되, grant가 없거나 stale/재사용/타 revision/범위 밖/모호하면 HELD 또는 preview 한 결정으로 기다린다. 사전 승인된 정상 SURVEY_COMPLETE만 physical worker 종료/robot-idle·cleanup·raw SHA를 확인한 뒤 같은 논리 inspection owner의 시간 제한된 post-survey correction 단계로 handoff한다. 이 논리 owner는 active physical/UNKNOWN guard를 우회하는 권한이 아니다. 전체 inspection 종료·Stop/Cancel·연결상실·실패·예상 밖 terminal은 미사용 grant를 철회하고, commit admission 전에 철회/기간/단계 유효성을 다시 검사한다. 미사용 grant는 reload/closed reopen/프로세스 재시작에서 자동 복원하지 않는다. 이미 STAGED인 작업만 기존 journal의 명시 recovery 대상이며 새 autocommit 권한과 구별한다. 이미 STAGED/Build 중인 철회 경합은 기존 취소·보상/UNKNOWN 경로로 처리하며 확인되지 않은 rollback 성공이나 자동 재개를 표시하지 않는다. 별도 성공 endpoint·새 저장소·무승인 Apply/Run·자동 임무 재개는 만들지 않는다. 보정 grant는 geometry commit만 승인하며 새 모터 실행권한이나 과거 pose/readiness 복원을 허용하지 않는다.
3. commit 뒤 새 revision의 current 3D를 확인하고 이전 goal/route·현재 pose/readiness 결속을 무효화한다. 과거 survey pose를 현재 위치로 복원하지 않는다. Undo도 새 revision의 ACK/disk/current frame을 확인하며, 저장 실패·ACK 유실·중단은 기존 compensation/UNKNOWN 잠금·명시 fault recovery로 처리한다.

**오프라인 acceptance:** 명시 합성 typed sensor와 보존 실자료를 구분하여 정상 mapping/fit→checked handoff→preview 명시 Apply 또는 사전 승인된 정상 SURVEY_COMPLETE/physical worker 종료·idle·cleanup·raw SHA 확인→같은 시간 제한된 inspection owner→유효 Start grant의 무추가클릭 common commit→ACK/disk/current frame→목표 무효화·새 preview→Undo→closed restart의 exact state/원자료 불변을 확인한다. 동일 보정의 단일 common commit·멱등성과 legacy/common 이중 writer 거절을 확인한다. stale/재사용/타 revision/범위 밖/모호한 grant는 HELD 또는 한 질문으로 대기하고, 무승인 commit·새 모터 실행·임무 재개는 0이어야 한다. 정상완료 handoff 양성과 전체 inspection 종료·Stop/Cancel·연결상실·실패·예상 밖 terminal·기간 만료의 grant 철회 음성, admission 직전 재검사와 STAGED/Build 후 철회 race의 취소·보상/UNKNOWN을 각각 검증한다. reload/closed reopen/프로세스 재시작의 미사용 grant 자동 복원 거절과 이미 STAGED journal의 명시 recovery를 구분하며, 새 autocommit 권한·확인 없는 rollback/자동 재개는 0이어야 한다. stale/source/raw 변조·중복 dispatch·저장 실패·ACK 유실/중단·복구 반례는 fail-closed여야 한다. 원 실자료 HELD를 성공으로 바꾸거나 fit/ACK를 주입하지 않으며, 이 통과는 현장 정합/REAL PASS가 아니다.

**현장 acceptance는 별도 유효 승인 후:** 새 REAL 프로젝트에서 `Use my robot`을 선택하고 현재 boot/release·신선한 scan/odom/TF·정지/배터리/통신·정합/경로와 기존 안전 한도를 다시 확인한다. 저장 SIM→REAL 일반 전환은 미구현이다. 실제 survey→handoff/common commit·current 3D→새 현재센서 goal preview/명시 승인·이동/Stop/cleanup까지 인수하기 전에는 네 번째 실물 전체 흐름을 완료로 표시하지 않는다.

### G5 통합 회귀와 실제 Isaac 인수

- 아래 시험 행렬의 오프라인/API/browser/Isaac 부분을 실행한다. 외부 LLM은 저장응답을 재생하며 실제 호출과 혼동하지 않는다.
- 실제 revision 화면, 명명 목표, PhysX 이동·도달, 별도 moving Stop/stable, reset/reload/닫힌 재열기와 bounded SIM 왕복을 확인한다.
- **완료:** 해당 로컬 기능의 근거가 완결되고 예상 차단 사례도 그대로 차단된다. 단위 테스트 수만으로 전체 완료 처리하지 않는다.

### G6 승인된 실제 모델로 새 기준 인수

- 기존 선택을 유지한다: 사진 관측·시각 검토는 Nebius `deepseek-ai/DeepSeek-V4.1-Flash`, 설계·수정은 `nvidia/nemotron-3-super-120b-a12b`. 모델 자동 교체 없음. 텍스트는 사진 관측 호출 없음.
- 승인 요청용 최소 묶음은 기존 식당 사진, 기존 거실 사진, 창고 텍스트, 개발에 쓰지 않은 별도 공개 공간 사진의 4개 생성과 사진/텍스트 각 1개 새 세션 반복으로 **최대 6개 생성**이다. 독립 새 사진은 권리·외부 전송 범위를 먼저 확인한다. 이것은 실행 승인이나 6개 성공 보장이 아니다.
- 최초 photo/text 각 1개로 일반 경로를 확인한 뒤 나머지를 진행한다. host 결함이면 원 감사 후 수정하고 영향 범위만 새 cohort로 재시험한다. 모델의 개별 실패를 숨기거나 성공할 때까지 무제한 재호출하지 않는다.
- 최소 위치 변경·부모 크기 변경의 **실제 자연어 모델 편집 2종**을 포함한다. clarification/취소/Undo는 같은 사용자 흐름에서 확인한다. 편집 호출도 별도 실행 ID로 전체 승인 금액·HTTP 상한에 포함하며 생성 예산 밖의 무료 작업처럼 취급하지 않는다. 승인 전 실제 요청 상한과 공유/별도 정책을 manifest에 명시한다.
- **시험 종료:** fresh 모델 결과와 실제 engine 증거가 연결된 판정 축별 보고서를 만들면 `TEST_COMPLETED`다. 실패 보고서도 시험 종료일 수 있지만 제품 인수 통과를 뜻하지 않는다. 보완이 남은 초안을 완전 품질 PASS로 표기하지 않는다. 실제 수정 회복이 자연 발생하지 않았으면 fault injection 사례를 별도 표기하고 자연 실패 회복률을 만들지 않는다.

유료 호출 전에 case/task별 필수 판정 축, 예상 차단, 영향 범위와 인수할 제품 범위를 동결한다. 그 범위의 `LOCAL_SCOPE_ACCEPTED` 최소 근거는 **사진 1건과 텍스트 1건의 ordinary fresh 생성→현재 Isaac→원 목표 이동→별도 moving Stop/stable→저장/재열기**, **실제 자연어 편집 2종과 적용 후 영향 재검증**, **필수 안전 반례의 예상 차단**이다. 필수 근거가 없거나 공통 안전·저장·수정 결함이 남으면 `PARTIAL`이다. 장식 보완은 남을 수 있고 모든 표본의 모든 시각 축 PASS를 요구하지는 않지만, 실패한 다른 사례는 분모와 제한 범위에 남긴다. 이 인수는 통과한 작업 범위의 근거이지 임의 새 공간의 현장 주행 허가나 과거 P2 전체 성공의 소급 선언이 아니다.

### G7 현장과 후속 확장

G5/G6의 해당 범위 `LOCAL_SCOPE_ACCEPTED` 이후 유효한 현장 승인을 받아 기존 P4의 안전 초기화→신선한 scan→위치 재정합→bounded 검사→derived revision→목표 preview→Confirm→이동·Stop을 수행한다. 현장 입력도 그 작업의 준비 조건을 새로 충족해야 한다. 임의 시작 위치와 사람의 추가 수정이 함께 처리되는지 확인한다. 로봇 OFF 상태에서는 준비/계약 검증만 완료할 수 있다.

Cloud·Physical AI 트랙 요건·촬영·라이선스/출처·공개/제출은 기존 제출 계획을 따른다. 소품 장식이 전부 완벽해야 Cloud 준비를 검토할 수 있는 것은 아니지만, **G5/G6의 합의된 기능 범위와 모든 필수 안전·통합 인수**가 없는 상태에서 ready라고 이름만 바꿔 유료 Cloud로 넘어가지 않는다. 새 기준의 로컬 완료 상태에는 criteria version과 아직 남은 품질/현장 항목을 붙인다.

영상은 후속 입력 adapter다. 대표 프레임→기존 관측 계약→장면/patch 경로를 먼저 설계한다. TAP 설치·수동 점 찍기·새 3D 재구성 엔진은 이번 G0–G6 필수 작업에서 제외한다.

## 9 최소 회귀와 인수 행렬

| 시험 | 기대 결과 | 필요한 근거 |
|---|---|---|
| 텍스트 only | 사진 요구 없이 동일 초안·SIM 경로 | API/browser, 실제 모델 인수 시 observer 미호출 |
| 상판 소품 배치 실패 | 유효 초안과 보완 목록 병존 | compiler/store→현재 Isaac 렌더 |
| 동일 소품이 바닥 통로 또는 위치 불명 | 장식으로 강등하지 않고 해당 작업 차단 | 위험 판정·keepout/불명 영역·admission |
| 주요 가구 미지원/누락 | 목록과 미충족 상태 보존, 완전 품질로 오인 금지 | 원 관측 ID와 저장/화면 비교 |
| 매트 위 접시와 실제 관통 | 정상 층별 지지와 잘못된 겹침 구분 | 범용 geometry fixture, 실제 새 geometry |
| 부모 크기·위치 변경 | 자식과 목표 의존 관계 함께 처리 | revision diff·변경 scope·재계획 |
| 반복 재수정 | 같은 객체라도 개선 근거가 있으면 허용 | patch SHA·오류 변화·마지막 유효 상태 |
| 파싱/빈final/출력 소진 | 잘린 출력 실행 금지, 기존 보호 종료 | 저장 raw/진단/원 실패 보존 |
| 저장/엔진 중간 실패 | 반쪽 결과를 완료로 표시하지 않음, 복구 ACK 없으면 unknown/실행잠금 | commit 전후 crash·ACK 유실·저장 실패 주입, journal/reconciliation |
| stale response/중복 Apply/다른 프로젝트 | 과거 제안 적용·교차오염 없음 | source/current hash·멱등성 |
| 자연어 편집·모호한 대상 | 현재 장면에 grounded proposal 또는 질문 한 개 | 일반 chat→실제 모델→preview/apply |
| Cancel/Undo/reload | revision 일관성, 이전 실행 승인 부활 없음 | UI·history·admission |
| 저장 센서의 pose 변화/벽 변화 | 서로 다른 원인으로 처리 | map/pose/scene revision·정합 근거 |
| 센서 부족/정지/통신 오류 | REAL 작업 보류/정지, 오래된 pose/scan 비활성 | 기존 안전 회귀·현장은 별도 |
| SIM 명명 목표·이동 중 Stop | 해당 작업 도달과 별도 정지 검증 | actual PhysX transform/receipt/안정 구간 |
| SIM 왕복·동적 장애물·배터리 이상 주입 | 제한된 작업·정지·재승인 동작 일관 | actual SIM와 주입 표기, 실물 PASS 아님 |
| 다른 방·방향·규모·객체 순서 | 사진 ID/좌표 예외 없이 동일 정책 | 합성 변형 + 새 공개 입력의 분리 결과 |

회귀는 각 단계의 영향 범위를 먼저 실행하고 G5에서 통합한다. 라이브러리 전체 조합·모든 공개 모델·모든 새 방을 통과해야 다음으로 가는 무한 범위는 만들지 않는다. 실패 시 정확한 원인을 분류하고 사전 정의한 최소 인수 범위를 유지한다.

## 10 벤치마크와 디버깅 기록

기존 execution ID와 diagnostics를 확장한다. `입력 → 관측 → 설계 → 컴파일 → issue 분류 → patch → 실제 적용 → 렌더 → SIM/센서 → 저장`을 동일 root 실행 ID 아래 연결하고 각 시도의 ID·parent를 보존한다.

각 수정에는 원 오류, issue 영향 범위, 요청/응답, 변경 전후 SHA, 바뀐 ID, defer/restore 이유, 검사 결과, 실제 렌더·engine receipt, rollback/정체 사유를 남긴다. 기존 redaction·크기 제한·완전성 hash를 유지하며 키·인증 헤더·개인 자료를 공개 로그에 넣지 않는다. 단계 시간과 병목 함수 측정은 기존 profiling을 재사용한다.

보고서 지표:

- `draft_ready / 전체 시도`와 필수 구조·주요 물체 반영 상태.
- `sim_task_pass / 계획된 해당 작업`, 도달·moving Stop·재열기의 개별 결과.
- 주요 물체의 종류/인스턴스/대략적 관계 coverage. 정답 주석이 없으면 recall이라고 부르지 않고 관측 목록 대비 반영률로 표시.
- deferred/unresolved의 수·중요도·잔여 작업 부담. 많이 보류해서 높아진 초안 성공률을 정밀도 향상으로 표현하지 않음.
- 최초 성공, 실제 수정 후 회복, 정체, host 오류, 모델 오류, 승인/비용 차단의 분리.
- 실제 HTTP/수정 횟수, 단계·전체 시간, 비용 추정/확정/held. 적은 표본의 p95 불안정성 명시.
- 실측 상태·사람 품질 검토 상태·현장 여부. 미실시를 0점이나 PASS로 바꾸지 않음.

평가기준·prompt/schema·모델 route·입력·정책·source/Web/build·Isaac 환경을 사전 동결한다. 기존 v431 2/3과 원 식당 FAIL은 그대로 유지한다. 같은 raw를 새 기준으로 오프라인 재평가한 표는 `재분류 분석`이며 실제 모델 재시험/회복 성적으로 세지 않는다. 새 입력에서 실패하면 특정 사진 hardcode가 아니라 범용 원인과 반례로 수정한다.

새 공개 사진도 첫 평가 후에는 개발에 노출된 입력으로 기록한다. 그 실패를 보고 수정한 뒤 같은 사진을 다시 실행한 결과는 `regression/retest`이며 최초 새 입력 성적과 합치지 않는다. 별도의 미노출 입력 없이 holdout 일반화 주장을 확대하지 않는다.

이 시험은 선택한 조합의 제품 인수와 제한된 일반화 검사다. 모델을 바꾸지 않았다면 모델 순위 벤치마크라고 부르지 않는다. 이후 모델 비교에는 같은 입력·예산·조건·criteria version을 사용하고 실패/NOT_RUN 분모를 보존한다.

산출물은 JSON metrics와 실제 원입력·현재 3D·수정 전후 화면을 포함한 자기완결형 HTML 하나를 기본으로 한다. 독립 비교표에 기능·시각·실물 상태를 나란히 보여준다. raw/개인사진/좌표·비밀의 GitHub 공개는 별도 승인·권리 검토 없이 하지 않는다.

## 11 예산과 안전 및 범위 제한

- 현재 모델·출력/시간 설정의 기준은 40,000 tokens, 요청 300초, 생성 전체 900초, 공유 최대 12 HTTP, 수정 최대 3회다. 단계별 할당과 실제 제품 readback을 확인한다. 계획 작성으로 늘리거나 초기화하지 않는다.
- 출력 소진, 미확정 비용, 승인 만료, 해당 campaign의 동일 원인 연속 실패 규칙을 유지한다. timeout 뒤 원 요청의 후행 결과·usage는 기존 소유권/한도 안에서 정산하며 임의 재전송하지 않는다.
- 외부 시험은 데이터·파생 렌더·목적지·횟수/HTTP·누적 상한·기한을 유효하게 승인받은 뒤 진행한다. 잔액이 많다는 사실로 만료된 시험 승인이나 무제한 범위를 만들지 않는다. 과거 UNKNOWN/held를 초기화하지 않는다.
- 로봇 OFF를 기본으로 한다. 계획 또는 오프라인 구현만으로 SSH/serial/실센서/모터/전원/배포/현장시험을 시작하지 않는다.
- 기존 자율 임무의 scan 200ms/input 250ms/segment 50ms/0.03m/s/0.20rad/s/45초, 정지·실물 임무 잠금을 보존한다. 수동 주행 속도와 혼동하지 않는다. 지속 loop는 별도 계약·현장 인수 항목이다.
- 임의 설치·시스템 설정·유료 Cloud·commit/push·저장소 공개·타 프로세스 강제 종료·권한 거부 우회는 하지 않는다. `/World/TwinPulse`와 기존 권한 경계를 지킨다.
- Apache-2.0/NOTICE/외부 자산·사진 고지를 보존한다. 생성 장면/리포트에 자체 코드 라이선스가 자동 적용된다고 쓰지 않는다.

## 12 완료 보고와 6.1 Sol 전달문

각 단계 종료 시 다음을 짧게 기록한다: 바꾼 제품 경로, 최초 재현 실패, 통과한 검사와 실제 runtime 여부, 미해결 항목, 원자료 불변성, 다음 안전한 단계. Baseline/Memory를 함께 동기화하되 과거 성적과 현재 상태를 혼합하지 않는다. 문서·mock만 추가하고 제품 연결을 완료로 기록하지 않는다.

후속 구현 요청 때 사용할 전달문:

> 기준 저장소의 AGENTS.md, 최신 PROJECT_MEMORY/BASELINE 및 이 계획서를 읽고 G0부터 의존성 순서대로 구현한다. 목표는 완벽한 사진 복원이 아니라 주요 구조와 물체를 갖춘 수정 가능한 Twin을 실행·사람·센서 피드백으로 개선하는 제품이다. 초안 사용 가능, 작업별 SIM 검증, 실물 준비, 시각 품질을 분리하라. 소품 실패 때문에 전체 유효 장면을 버리지 말고, 원 관측과 미해결 항목을 보존하라. 반대로 미확정 장애물을 삭제하거나 장식으로 강등해 주행을 허용하지 말라. 기존 compiler/store/patch/history/ordinary chat/Isaac 경로를 확장하고, 판정 계약과 저장 → 부분 초안 → 의존 관계 수정·Undo → UI → 센서 연결 → 실제 인수 순서로 진행하라. 첫 확인 지점은 상판 소품 미해결에서도 현재 3D와 보완 목록이 보이되 같은 바닥 위험은 해당 주행을 막는 것이다. 임의 모델 코드 실행·사진별 hardcode·원 FAIL 승격·예산/안전 완화는 금지한다. 실제 LLM/Cloud/로봇은 별도 유효한 승인 없이는 호출하지 않는다. 미검증은 그대로 남기고, 로컬에서 안전하게 진행할 수 있는 후속 단계는 불필요하게 멈추지 말고 수행하라.

## 13 영상 입력의 참고 범위

DeepMind의 [TAP 공식 저장소](https://github.com/google-deepmind/tapnet)는 영상의 점 추적과 관련 모델·벤치마크를 제공한다. 점 추적은 여러 프레임의 대응점 확보에 활용할 수 있지만, 그 자체를 가구 종류·실측 치수·지지 관계를 갖춘 Twin 생성기로 간주하지 않는다. 이번에는 설치·평가를 수행하지 않으며 영상이 필요한 단계에서 공통 관측 adapter에 들어갈 보조 기능으로 검토한다.

[Nav2 공식 tuning 문서](https://docs.nav2.org/rolling/configuration_and_development/tuning_guide/)는 2D 평면 LiDAR와 3D 센서용 장애물 처리를 구분한다. 따라서 2D scan만으로 전체 3D 외관 검증을 완료했다고 표시하지 않는 원칙을 유지한다. 이 링크는 TwinPulse에 새 Nav2 구성이나 센서 설치를 지시하는 것이 아니다.
