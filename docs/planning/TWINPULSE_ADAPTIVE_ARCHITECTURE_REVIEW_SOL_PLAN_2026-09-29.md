# TwinPulse Adaptive Architecture — 평가 및 GPT 6 Sol 구현 계획

- 작성: 2026-09-29 KST / 계획 v1.0
- 상태: **검토·계획 작성 완료 / 아래 신규 단계 구현 미착수 / 사용자 단계 승인 대기**.
- 검토 root: `C:\Users\jaewo\Documents\TwinPulse`. 코드 HEAD `5c42899a95a0bf2422550bd17df7556a92ab3232`에 다수의 기존 미커밋 변경이 포함된 작업 트리다. HEAD만으로 이번 검토 코드를 복원할 수 없다.
- 입력: `C:\Users\jaewo\Downloads\TWINPULSE_ADAPTIVE_ARCHITECTURE_CONCEPT.md`, SHA-256 `6d2232918de2c77fe1e6e9ad3770a2fccd78ae1fdf49c7fb6da46e7d848492c9`.
- 첨부 문서는 설계 제안이다. 그 안의 자동 실행·프로브·플러그인·실물 명령을 현재 실행 승인으로 취급하지 않았다. 원본은 수정하지 않았다.
- 이번에는 소스 읽기와 문서 작성만 수행했다. 로봇/Isaac/유료 모델 호출·설치·배포·새 에이전트·commit/push·예약 재개 없음. 과거 테스트 기록을 이번 재검증으로 표시하지 않는다.

## 1. 평가 결론

**방향은 채택할 가치가 높다. 다만 “새 자율 에이전트 플랫폼 구축”이 아니라 현재 제품의 계약과 데이터 경계를 점진적으로 정리하는 방식으로 반영한다.**

좋은 점은 ① 모델과 실행 엔진의 분리, ② 모델 능력과 품질의 분리, ③ 결정적 도구 조합 우선, ④ 실행 증거 기반 평가, ⑤ 무검증 자기 코드 수정 대신 제안·검증·승격이다. 현재 TwinPulse의 App/core/provider/Isaac/로봇 worker 분리와도 일치한다.

하지만 이 문서만으로 “일회용이 아닌 제품”이 되지는 않는다. 다음 네 가지를 추가해야 한다.

1. **지속되는 프로젝트**: 장면·사진·센서 원본·보정 근거·자산·임무·실행 이력의 저장/재열기/이전 버전 읽기.
2. **재사용 가능한 실행 조건**: 엔진이 구현한 기능, 검증된 환경, 지금 연결 가능한 상태와 사용자가 허용한 범위를 분리.
3. **실제 제품 경로**: 새 계약을 기존 Generate→Review→Build→Run/Replay 및 임무 이력에 연결. 별도 예제 CLI나 테스트 전용 모델만 늘리는 것은 완료가 아니다.
4. **최소 기능으로부터의 진화**: 자동 모델 탐색·다중 모델·자기 단순화를 당장 모두 만들지 않는다. 기존 방식으로 끝까지 되는 경로를 먼저 보존한다.

“Stable Kernel”은 코드가 영원히 바뀌지 않는다는 뜻이 아니다. **권한·검증·증거 책임과 버전 호환 계약이 안정적**이라는 뜻으로 수정한다. 새로운 하드웨어/제어 방식은 kernel의 검증 확장이 필요할 수 있다.

## 2. 제안별 채택·보완 판단

| 제안 | 판단 | TwinPulse 반영 조건 |
|---|---|---|
| Stable Kernel + Adaptive Shell | 채택 | 기존 패키지 유지. 엔진/로봇 빠른 제어 루프에 LLM을 넣지 않음 |
| 자동 ModelProfile | 수정 채택 | declared/verified/quality 외에 unknown·실패 종류·검증 시각·adapter/endpoint/model 식별을 저장. metadata만으로 기능 통과 처리 금지 |
| EngineCapabilities 분리 | 우선 채택 | 기능 목록과 현재 readiness·실행 승인은 별도. legacy +X, scene-only, 합성 XY, 실물 임무를 한 capability로 합치지 않음 |
| ToolCatalog 단일 기준 | 우선 채택 | 기존 registry 확장·통합. schema로 표현 가능한 구조 제약만 생성하고, 충돌·revision·시간·권한 검사는 명시 코드로 유지 |
| AI Composite Tools | 제한 채택 | 허용된 도구의 유한한 선언형 조합. 임의 코드/동적 import/셸/URL 실행 금지. 초기에는 장면 저작만 |
| Bounded Agent Loop | 후속 채택 | 초안 수정과 sandbox sim 평가부터. 실제 이동 실패를 새 동작으로 자동 재시도하지 않음 |
| 모델/전략 자동 Routing | 후속 채택 | budget·데이터 반출 허용·검증된 역할을 먼저 필터. 같은 평가셋/조건에 대한 충분한 증거 이후 도입 |
| Self-Simplification | 연구/제안 단계 | 전략 후보와 비교 보고서까지만 자동화. validator·provenance·watchdog 제거는 최적화 대상 아님 |
| Personalization | 보완 채택 | 취향과 권한·센서 사실을 분리. 프로젝트 명시 설정 우선. 과거 승인으로 새 이동·유료 호출을 승인하지 않음 |
| physical approval | 의미 수정 | **임무 범위 1회 승인 후 내부 이동은 자율 판단**. 이동 tick/회전마다 사용자 클릭 요구 금지 |
| rollback | 의미 수정 | 문서/scene revision 복원과 실제 로봇 정지·복구를 분리. 이미 일어난 이동은 트랜잭션처럼 취소되지 않음 |

### 특히 주의할 해석

- `run_simulation`도 무조건 SAFE가 아니다. 실행 중 stage 소유권·계산량·기한·중단과 실제 로봇으로의 연결 여부를 검사한다.
- 모델이 tool-call JSON을 낼 수 있다는 것과 그 도구가 장면/물리적으로 정확하게 동작한다는 것은 별개다.
- native tool calling과 JSON tool-plan 생성은 다른 능력으로 기록한다. 현재 JSON 계획 방식을 모두 native tool calling으로 부르지 않는다.
- 프로브 실패를 모두 “모델 미지원”으로 분류하지 않는다. 인증/네트워크/예산/스키마 dialect/adapter 오류를 분리한다.
- 모델 스스로 보고한 confidence는 측정 신뢰구간이나 실제 치수 근거가 아니다.
- 강한 단일 모델로 observer/planner 호출을 합쳐도 입력 근거와 출력의 관계는 남긴다. 내부 추론 과정 공개는 요구하지 않는다.
- collision 감점은 시뮬레이션 평가에 활용하되 **실물에서 충돌을 허용하는 정책으로 쓰지 않는다**. 로봇 로컬 차단이 우선이다.

## 3. 현재 코드와의 대응 — 새로 만들 것보다 재사용할 것이 많다

아래는 2026-09-29 읽기 확인 기준이며 경로는 기준 root 상대 경로다.

| 실제 파일/심볼 | 확인 사실 | 계획에서 할 일 |
|---|---|---|
| `packages/twinpulse_core/src/twinpulse_core/scene_tools.py` — `SCENE_TOOL_NAMES`, `TOOL_DOMAINS`, `SceneToolRegistry` | v1 8도구·결정적 실행·24호출 한도·+X resolver 존재 | 새 실행기 재작성 대신 카탈로그와 기존 handler 연결 |
| 같은 core `site_tools.py` — `SITE_TOOL_NAMES`, `execute_site_tool_plan` | v2는 box 추가·scene-only·evidence binding, 일부 dispatch 중복 | v1/v2의 의도적 차이는 보존하면서 공유 정의 정리 |
| `packages/twinpulse_provider/src/twinpulse_provider/schema.py` | 도구 인자/범위가 core와 별도 선언됨 | 공통 정의에서 provider별 schema view 생성 |
| 같은 provider `nebius_pipeline.py` — `ObservationArtifact`, `build_planner_body` | 관측 계약이 provider 안에 있음. v1 prompt에 +X/같은Y/0.2~10m 조건 고정, v2는 임무 선택적 | 관측의 순수 계약 분리, 엔진 조건을 요청 문맥으로 전달. v1 resolver 삭제 아님 |
| 같은 provider `contracts.py`, `providers.py`, `service.py` | 기존 Provider protocol, `ProviderCapabilities`, Responses/Chat adapter, 취소·1회 호출 정책 존재 | Provider와 PlannerStrategy를 구분. 현재 max_attempts=1 정책은 무심코 변경하지 않음 |
| `packages/twinpulse_app/src/twinpulse_app/provider_composition.py` | 설정에 따라 기존 provider를 조합, 구성만으로 network 호출 없음 | 유일한 composition root 재사용, 전략 교체·관측능력 전달 |
| 같은 app `application.py` — `GenerationContext`, `ApplicationService` | generation 단일 소유자·input revision/epoch·취소/late-result 방어 | 새 orchestrator가 별도 generation 소유자를 만들지 않음 |
| core `engine_contracts.py` / Extension `isaac_adapter.py` | snapshot의 capabilities/permitted_commands, typed command/receipt·session/stage/lease 존재 | 기존 계약과 호환되는 상세 capability view 추가 |
| core `site_contracts.py` | Scene/Map/Robot/Mission/RunIntent·revision·gate 존재 | 새 WorldState 전체로 교체하지 않고 연결 |
| app `bedroom_twin.py`, `bedroom_review.py` | 특정 photo hash·12객체·크기와 날짜별 artifacts 경로에 결속된 근사 방 | 고정 방은 regression fixture로 보존, 제품 프로젝트 데이터/recipe 경로 추가 |
| app `project_store.py`, `site_draft.py`, `session_journal.py`, `session_history.py` | 프로젝트/draft/세션 저장·조회 기반 존재 | 기존 저장체계를 확장, 별도 범용 DB 도입은 보류 |
| app `physical_controller.py` | `mission_live_locked`가 실제 transport를 차단. 가짜 주입 경로의 start_available와 구분 | capability 변경이 실물 잠금을 해제하지 못하도록 검사 |
| core `room_goal.py`, app `robot_geometry_evidence.py` | 명목 모델·실스캔 근거와 SE(2) 후보 검토; 실제 TF/정합은 없음 | 후보/검증된 보정/현재 실행권한을 계속 구분 |
| core `acceptance.py`, `scripts/evaluate_m2d_floorplan_result.py`, app `bedroom_rehearsal.py` | 실행 평가·도면 scorer·동일조건 합성 비교가 각각 있음 | 공통 평가 report로 감싸되 원래 판정/실패 보존 |
| 로봇 `teleop_worker.py`, `teleop_ros.py`, `mission_runtime.py` | 명령/관측·정지·로컬 판단 경로 존재, 최신 오프라인 변경 실물미배포 | 카탈로그 일반화 때문에 실물 watchdog/한도/정지 로직을 리팩터링하지 않음 |

따라서 현재 TwinPulse를 단순 “특정 모델에 묶인 일회용 프로그램”으로만 평가하는 것은 부정확하다. 이미 분리 기반이 있다. **부족한 것은 일관된 공통 정의, 지속 프로젝트/근거 데이터, 검증된 교체 절차, 일반화된 제품 연결**이다.

## 4. 목표 구조와 변하지 않을 경계

```text
지속 프로젝트: 입력/자산/근거/scene·map·보정 revision/실행 이력
                       ↓
ApplicationService: 단일 작업 소유·불변 실행 문맥
                       ↓
PlannerStrategy ← ModelProfile + EngineCapabilities + ProjectContext
                       ↓
선언형 계획/Composite → 정규화된 기존 primitive 계획
                       ↓
Core 검증 + Application 권한/예산 + 기존 broker
               ┌───────┴────────┐
       Isaac adapter       로봇 mission adapter
       scene/physics       로컬 센서 판단·watchdog
               └───────┬────────┘
                실행 receipt/관측/평가
                       ↓
             프로젝트 기록 + 다음 후보 검토
```

의존 방향: core는 provider/app/Isaac/ROS를 import하지 않는다. provider는 모델 I/O와 요청/응답 변환, app은 사용자 설정·권한·작업 수명·저장, Extension은 USD/PhysX, 로봇 worker는 현장 제어를 소유한다. `ToolCatalog`가 모든 실행을 직접 소유하는 거대 framework가 되어서는 안 된다.

빠른 로컬 제어와 느린 LLM 개선을 분리한다. LLM은 목표/후보 경로를 제안하고, 현재 센서 기반 충돌 차단·입력 만료·정지는 로컬 결정적 코드가 한다. 모델 통신 지연을 기다리며 마지막 이동 명령을 유지하지 않는다.

### 4.1 반드시 구분할 네 가지

1. `ModelCapability`: 특정 endpoint/adapter/model/config에서 무엇을 입력·출력할 수 있는가.
2. `EngineCapability`: 특정 엔진/컨트롤러 릴리스에 어떤 동작이 구현돼 있는가.
3. `RuntimeReadiness`: 지금 scene/boot/센서/보정/연결이 그 동작에 적합한가.
4. `ExecutionScope`: 사용자가 이번 작업에 허용한 대상·구역·시간·비용·행동 범위는 무엇인가.

실행 가능 여부는 네 조건과 정책의 교집합이다. 모델이나 saved JSON이 `ready=true`를 넣는 것으로 권한이 생기지 않는다. 계획에 사용한 capability revision이 바뀌면 실행 전에 재평가하고, 현재 센서 조건은 발행 시점에도 다시 확인한다.

### 4.2 지속 데이터와 일시적 권한

| 데이터 | 재시작 후 보존 | 무효화/검토 기준 |
|---|---|---|
| 사진/원시 스캔/scene/실행 이력 | immutable ID·hash로 보존 | 파일 손상·자산 누락을 명시, 원본 덮어쓰기 금지 |
| 명목 RobotProfile/asset | 버전/출처/해시로 보존 | 모델/장착 변경 시 현물 적합성 재검토 |
| 지도·보정 | 근거·부모 revision과 함께 보존 | 지도/센서 위치/기준 frame 변경 시 재검토; odom 부팅 원점의 수명은 별도 |
| 모델 profile/평가 | 검증 조건·시각·버전과 함께 보존 | endpoint/adapter/schema/model alias 변화 시 stale/unknown |
| 선호/비용 상한 | 사용자 설정으로 보존 | 사용자 수정 가능, 기본값은 실행 승인이 아님 |
| lease·현재 연결/센서 freshness·임무 승인 | 실행 상태로만 취급 | 새 boot/세션/범위 변경/취소/만료 시 무효. 앱 복원만으로 재개 금지 |

**준비 결과를 재사용하되 만료된 권한은 재사용하지 않는다.** 매번 모든 것을 지우고 정지 시험을 반복하는 정책도, 과거 PASS를 영구 자격으로 쓰는 정책도 이 계획에서 새로 도입하지 않는다. 항목별 의존성/무효화 표를 먼저 만들고 기존 자격 기준 변경은 별도 근거로 결정한다.

## 5. 최소 계약안 — 이름은 제안, 기존 타입 재사용 우선

### ToolDefinition / CatalogSnapshot

- `id`, `version`, `domain`, 설명, 구조적 input schema, supported plan versions.
- 결정적 semantic validator의 로컬 등록 ID와 executor 등록 ID. 외부 JSON에 Python import 경로를 넣지 않는다.
- capability requirements, effect 종류, 자원 상한, 취소/재시도/보상 가능성, idempotency 분류.
- catalogue snapshot digest와 schema adapter revision을 실행 문맥에 결속.
- pure scene expansion과 실제 `run`/physical mission 도구는 같은 메타데이터 형식을 쓸 수 있어도 실행 권한·dispatch 경계는 별개다.
- v1/v2의 호출 슬롯·선택적 robot/task·object ID/순서/수치 경계 차이를 선언적으로 보존한다.

### EngineCapabilitySnapshot

- 엔진/adapter/controller ID·release, 지원 schema/tool revision, mode별 기능·한도.
- `implemented`, `verification_level`, `evidence_refs`와 runtime readiness는 별도 필드/객체.
- 기존 string capability 읽기 호환 adapter를 먼저 둔다. 구형 엔진에 새 wire field를 일방 전송하지 않는다.
- `legacy_straight_x`, `site_scene_only`, `synthetic_xy_mission`, `physical_burger_mission`처럼 실제 경로를 구분. 명칭은 구현 시 기존 ID와 맞춘다.

### WorldObservation

- 기존 entities/relations/dimensions/ambiguities를 최소 순수 계약으로 추출.
- source artifact ID/hash, source kind(photo inference/native scan/ROS/manual measurement/synthetic), timestamp와 clock domain, frame/unit, uncertainty/unknown, 변환 근거 ID.
- 고해상도 scan 전체를 LLM 문맥에 넣는 거대 객체로 만들지 않는다. bounded 요약 + 원본 참조를 사용한다.
- 모델 관찰의 `inferred`를 자기 주장만으로 trusted measurement로 승격하지 않는다. 신뢰 등급은 수집·검토 경로가 결정한다.
- 사진와 scan이 충돌하면 어느 값을 채택/보류했는지 남기며 조용히 덮어쓰지 않는다.

### ModelProfile / ProbeReceipt / EvaluationReport

- 모델 identity = provider origin + adapter/version + model ID/revision(제공되는 경우) + 요청 protocol/schema/config digest. credential 값은 포함하지 않는다.
- declared와 observed 지원 상태(`verified`, `unsupported`, `unknown`, `stale`, `probe_error`)를 구분하고 이유/fixture revision/시각/예산 사용량을 기록.
- `EvaluationReport`는 입력/scene/map/profile/start-goal/seed/controller/전략/실행 backend/판정기 버전을 묶는다.
- metrics는 개별 단위·표본 수·출처를 가진다. 측정하지 않은 충돌/정확도/비용은 `null + reason`이지 0이 아니다.
- 실물 관측/저장 재생/인공 transport/합성 기하/실제 Isaac physics를 독립 evidence level로 기록. 상호 승격 금지.

### PlannerStrategy / Composite / WorkflowRun

- 전략은 기존 GenerationGateway에 연결되는 bounded request→typed proposal 역할. 초기엔 기존 두 전략을 wrapper로 유지한다.
- Composite는 versioned parameterized data이며 expanded primitive graph/hash를 저장한다. risk는 하위 효과의 합집합, 비용/횟수는 전체 합산; 표현을 감췄다고 권한이 줄지 않는다.
- 초기 Composite는 유한 리스트만 허용, 재귀·임의 반복·dynamic code 없음. 기존 plan 최대24호출/64객체 등의 더 엄격한 한도를 확장 후에도 검사한다.
- WorkflowRun은 proposal/evidence/revision·예산·취소·실행 receipt에 결속. 권장 수명: proposed→validated→authorized→executing→observed→evaluated, 실패/cancel/unknown은 별도 terminal 상태.
- 재연결 후 실행 여부가 unknown이면 receipt 조회로 정합성을 회복한다. 실제 효과가 있는 명령을 무조건 재전송하지 않는다.

## 6. 실행 순서 — 기존 데모와 충돌하지 않는 작은 단계

단계 ID `A0~A9`는 기존 H/N/R 단계와 별개인 아키텍처 개선 작업이다. 전면 재작성이나 아래 전체에 대한 자동 승인으로 해석하지 않는다. 일정은 고정 시간 약속 대신 아래 완료 조건으로 관리한다.

### A0. 현재 동작·데이터 경계 고정 — 가장 먼저

**산출물:** 현재 동작 inventory, 관련 소스/fixture hash manifest, golden 입력→출력, 상태/권한 무효화 표.

- legacy v1 plan, v2 scene-only/box/evidence, 방+Burger, 저장74 scan, room goal 누락/후보, 정지2종, 임무 fake 경로를 선정한다.
- `scene_tools.py`, `site_tools.py`, provider `schema.py`의 이름/범위/required/버전/실행 결과를 비교한다. 차이가 있으면 의도/결함/미확정으로 분류하고 조용히 한쪽에 맞추지 않는다.
- `scripts/verify_twinpulse.ps1`, 기존 rehearsal runner를 재사용. 시작 시 dirty working tree 파일 해시도 고정한다. Git HEAD만 기록하지 않는다.
- 기존 실패/미검증 목록 유지. 실행불가 환경은 NOT_RUN과 원인으로 남긴다.

**통과:** 동일 원본 재로딩/재계산 결과 확인, 모델·로봇 호출0, 변경 전 실패 재현과 증거 분리. A0로 물리 잠금이 풀리지 않는다.

### A1a. ToolCatalog 최소 통합 — 첫 구현 권장 범위

**의존:** A0. **예상 위치:** core `tool_catalog.py`(신규 후보), 기존 `scene_tools.py`, `site_tools.py`, provider `schema.py` 및 관련 테스트.

1. 현재 8개 v1 도구와 v2 전용 box의 정의/버전별 view를 추출한다.
2. 기존 handler와 semantic validator를 연결하고 provider schema는 view에서 만든다. 형식 adapter(예: required_call_slots)는 provider 경계에 둔다.
3. 기존 public 함수/타입/직렬화는 호환 facade로 유지한다. 새 이름이 있다고 기존 core를 통째로 교체하지 않는다.
4. schema·dispatch·planner 설명의 도구 집합 불일치 검사를 추가한다. schema로 표현하기 어려운 교차 객체 충돌/순서/단위 검사를 삭제하지 않는다.

**통과:** frozen v1/v2 sample의 ordered calls·expanded objects·canonical digest·기존 오류 경계 동일. unknown tool/extra key/bool-as-number/NaN/과대 호출·객체/잘못된 근거 거절. provider→core 의존만 허용. 기존 Generate→draft→Build 경로 회귀 통과.

**범위 밖:** 새 도구, 일반 물리 dispatch, dynamic plugin, 새 모델, +X 제거, Composite, 실물 정책 변경. 구조만 달라지고 외부 계약이 같으면 기존 catalog revision을 보존; 의미 변경이 필요하면 별도 단계/새 버전으로 분리한다.

### A1b. EngineCapabilities와 RuntimeReadiness 정리

**의존:** A1a. **위치:** core `engine_contracts.py`/`site_contracts.py`와 신규 상세 descriptor, app `application.py`/`provider_composition.py`, provider planner body, Extension `isaac_adapter.py`.

- 기존 snapshot/adapter가 공개하는 mode별 구현 사실을 한 곳에서 산출하고 동일 snapshot을 planner·UI·사전 gate에 전달한다.
- v1 prompt의 +X/sameY/거리 제한을 capability-derived context로 교체한다. runtime validator와 route resolver는 유지하며 설정만으로 arbitrary XY 구현을 주장하지 않는다.
- v2의 “사용자 목표를 옮기지 않는다” 의미와 legacy v1의 resolver 의미를 유지한다. capability migration을 핑계로 사용자 목적지를 자동 변경하지 않는다.
- capability unavailable과 runtime disconnected와 physical calibration missing을 서로 다른 코드로 표기한다.

**통과:** 구형 snapshot 호환, stale/session/release 변경 시 명령 거절, scene-only Build가 robot OFF에도 가능, sim 성공이 live 임무 권한을 주지 않음. 변경된 wire 경로는 실제 Isaac에서 확인해야 runtime PASS다.

### A2. 반복 사용 가능한 프로젝트·방 recipe·근거 저장

**의존:** A0, A1a 권장. **사용자가 원하는 연속성에 직접 필요한 단계**이며 A4 이후로 미루지 않는다.

**위치:** app `project_store.py`, `site_draft.py`, `bedroom_twin.py`, `bedroom_review.py`, `robot_geometry_evidence.py`, 기존 `BedroomTwin.tsx`, `BedroomGoalReview.tsx`, 저장/재열기 API.

- 프로젝트 내부 상대 asset/evidence 참조 + hash + 허용 root로 자료를 식별한다. 날짜별 개발 artifacts 경로는 기존 fixture adapter에서만 유지한다.
- 입력 이미지/scene recipe/Burger asset manifest/센서 recording/검토 후보/검증된 calibration/임무 이력을 명확히 분리한다. 새 DB/framework 없이 현재 파일 저장소 확장부터 한다.
- 기존 방을 versioned recipe 데이터로 표현하고, 다른 크기/배치의 **별도 테스트 프로젝트**도 코드 수정 없이 열도록 한다. 원본 방 hash와 기존 결과는 보존한다.
- 재열기 시 파일/버전/해시 검사, 누락 자산 안내, 권한 없이 “마지막 작업 이어보기”. 자동 Build/Run/로봇 접속은 하지 않는다.
- 최소 사용자 UI: `프로젝트 열기/이어보기`, `준비·연결 점검`, `임무 시작`, `정지`, `강제 STOP`, `결과`. 각각 많은 checkbox/터미널 단계로 쪼개지 않는다.
- PC preparation은 기존 연결 동작 안에서 수행. 실물 미연결이면 오프라인 작업은 가능하다고 명시하고 버튼별 실제 차단 사유를 제공한다.

**통과:** 두 프로젝트 전환/재시작으로 사진·목표·로그가 섞이지 않음. 원본 golden hash 보존. fixture의 다른 root 복사본에서도 허용된 상대 참조로 열림. path traversal/외부 실행 참조/손상/동시 저장 차단. 저장된 승인·boot freshness 복원 금지. 기존 방의 실제 Isaac 표시 유지.

**남는 물리 blocker:** 실제 센서 TF/odom·장착 외곽·방 미터 대응점은 오프라인 일반화로 만들어낼 수 없다. 준비/수집 화면의 묶음 흐름은 구현 가능하지만 “전원만 켜면 실제 정합·자율 데모 완성”을 보장하지 않는다.

### A3. Provider 독립 WorldObservation

**의존:** A1a, A2의 원본참조 경계. **위치:** core `world_observation.py`(신규 후보), provider `nebius_pipeline.py`, 기존 draft/provenance·ROS/native 자료 adapter.

- 현재 `ObservationArtifact`의 순수 파싱/형식을 core로 옮기거나 호환 타입으로 감싼다. 기존 schema 1.0 직렬화/hash는 유지하고 새 provenance envelope는 외부에 추가한다.
- image inference와 실제 sensor observation은 공통 참조 계약을 쓰되 수치/좌표/시각의 의미를 합치지 않는다.
- 모델이 “치수가 확실하다”라고 출력해도 photo estimate로 남긴다. 검증된 수집/검토 경로만 metric evidence를 추가한다.

**통과:** 같은 기존 observer 응답이 같은 observation hash/plan을 생성. 새 provider fake도 동일 계약 사용. mixed frame/time·없는 근거 ID·반사 가설의 TF 승격·unknown free-space 변환 거절. 기존 M2-D 오답도 여전히 실패한다.

### A4. 공통 평가·회귀 벤치마크 — 자동선택 전에

**의존:** A0/A3. **위치:** core 순수 evaluation report, 기존 `acceptance.py`, M2-D scorer, `bedroom_rehearsal.py`, App 결과/세션 이력에 adapter 추가.

- Scene Fidelity / Simulation Quality / Task Success / latency / cost / tool validity를 별도 점수로 제공한다. 종합 점수 하나로 안전 실패를 덮지 않는다.
- 현재 M2-D ground truth·서로 다른 기존 사진·방 recipe·입력 변조/불량 모델 응답을 고정 suite로 구성한다. 실사진의 치수 정답이 없으면 정량 치수정확도는 NOT_MEASURED다.
- 비교 조건: 입력/scene/map/start-goal/profile/controller/한도/seed/판정기 고정. 모델 routing 성능 비교와 지도 보정 효과 비교를 분리한다.
- calibration/training fixture와 held-out fixture 분리, 반복 수·실패 수·timeout·지연 분포·비용근거 기록. 단일 호출의 99% reliability 같은 표현 금지.
- rollout 충돌은 simulator contact/geometric proxy/관측불가를 구분한다. 기존 합성 collision=null을 0으로 바꾸지 않는다.

**통과:** 이전 성공/실패를 동일하게 판정, 양성·음성 regression이 모두 있음. 불동일 조건 비교에 개선율을 출력하지 않음. synthetic/Isaac/physical 별도 표기. 새로운 모델 호출 없이 저장 결과로 report 경로부터 확인.

### A5a. ModelProfile·프로브 수명과 예산

**의존:** A4. **위치:** provider 계약/adapter, app 설정·credential reference·새 profile store, Settings UI.

- 초기엔 현재 승인된 provider/model만 관리한다. 전세계 모델 목록 수집·자동 가입·자동 endpoint 생성은 만들지 않는다.
- metadata가 없거나 불충분하면 unknown. 사용자가 모든 능력을 손으로 작성할 필요는 없지만 자동 검증되지 않은 기능을 추정해서 켜지 않는다.
- 작은 합성 이미지/JSON/tool-plan probe를 adapter별로 정의한다. 개인 방 사진/회사 데이터는 기본 probe로 전송하지 않는다.
- cache identity/TTL와 모델 alias 변화 감지, 연결 오류/인증 오류/미지원/품질 미달 분리. 새 endpoint에 기존 credential을 자동 재사용하지 않는다.
- UI에서 비용/횟수/시간 한도 승인 후 실행. 초기 live probe 기본0, offline fixture만 자동 검사. 이미 허용된 예산 내 자동화 범위는 설정으로 기록한다.
- 비용 estimate/reserved/actual/unknown 구분, 동시 요청이 남은 budget을 중복 예약하지 않도록 한다. 가격 metadata가 없으면 임의 무료 처리하지 않는다.

**통과:** startup/config read에서 유료 호출0, 예산 소진/취소/late result/429·인증오류에 무제한 재시도 없음. synthetic fixture 통과를 live verification으로 표시하지 않음. secret 로그0.

### A5b. PlannerStrategy 교체

**의존:** A3/A4/A5a. **위치:** provider 기존 service/adapters + app composition root.

- 기존 단일 Responses 계획과 Nebius observer→planner 경로를 전략 wrapper로 만들고 현재 기본값을 보존한다.
- 전략 출력은 기존 typed proposal/검증/저장/Build 흐름으로 귀결된다. 전략이 UI/Isaac/로봇을 직접 호출하지 않는다.
- 단일 모델 전략도 근거 attribution을 반환하거나 명시 not_available로 남겨야 한다. 없는 관측을 지어내지 않는다.

**통과:** 전략 전환 시 입력/관측/결과 provenance 혼합 없음. 중간 취소·설정 변경의 late-result 폐기. 한 전략 실패 시 다른 paid provider로 몰래 fallback하지 않음. 가짜 테스트 후 별도 승인된 유한 live 비교가 있어야 실제 품질 향상이라고 주장 가능.

### A6. 선언형 Composite와 재사용 workflow

**의존:** A1a/A2/A4. 초기에는 장면 생성만; 실물·삭제·과금 조합은 후속.

- versioned recipe의 매개변수→유한 primitive 목록으로 확장. 기존 executor/validator를 그대로 사용한다.
- user/AI 후보는 draft로 저장, 검증 후 프로젝트에서 명시 선택. 검증 성공 자체가 production primitive 등록 승인은 아니다.
- 이름공간/ID충돌·재귀·순환·확장폭·전체 시간/도구횟수 제한, child call별 provenance, canonical expansion hash.
- 장면 작성은 scratch validation 후 commit, 실패 시 기존 scene 보존. 물리 효과 rollback은 지원한다고 선언하지 않는다.

**통과:** 두 프로젝트에서 다른 parameter로 같은 Composite를 재사용, 같은입력=같은 expansion. 중첩의 위험/예산 상속, 미등록/과대/순환 거절. v1/v2 계획으로 내려가 기존 Build 경로에서 실행됨. 새 parser만 있고 UI/제품 연결이 없으면 PARTIAL.

### A7. Bounded Observe→Plan→Validate→Evaluate→Repair

**의존:** A4/A5b/A6. 첫 범위는 **offline draft repair**, 그 다음 별도 scope의 Isaac 평가다.

- 권장 초기 한도는 최초 후보1+수정 후보 최대2, 총 deadline·호출·토큰/비용·scene 규모를 동시에 제한. 이는 신규 제안이며 기존 max_attempts=1을 몰래 변경하는 것이 아니다.
- repair attempt와 동일 요청의 통신 retry를 구분한다. 각 후보 parent hash·수정사유·평가결과 기록, 같은 오류 반복/진전 없음/unknown 실행 결과면 종료.
- 검증된 코드의 식별된 오류 코드를 피드백한다. 문서·사진·모델 출력에 포함된 지시가 정책·도구 등록을 바꾸지 못한다.
- 실패에 맞춰 scorer/안전한계/사용자 목표를 완화하지 않는다. 무한정 새 호출해 통과할 때까지 반복하지 않는다.
- physical worker는 이 loop와 독립. 임무 종료·보호 정지 뒤 LLM이 임의로 재시작하지 못한다.

**통과:** 성공/수정2회실패/취소/한도/동일오류/장면변경 경로. unknown receipt에 이중 효과0. 이전 accepted scene 보존. UI에 왜 멈췄는지와 마지막 유효 결과 표시.

### A8. 제한적 Adaptive Routing + Personalization

**의존:** A4/A5/A7. 충분한 비교 증거 전에는 추천만.

- eligibility(능력/예산/데이터 허용/엔진 호환)를 먼저 필터하고 그 안에서 품질·지연·비용을 비교한다.
- 표본 부족은 수동 고정 기본 전략 유지. 검증되지 않은 모델 탐색을 실물 임무 중 수행하지 않는다.
- 선택 이유·근거시점·fallback 이유·전략 버전을 사용자에게 보이며 override 가능하게 한다. 실행 중 임의 모델/전략 전환 금지.
- 선호는 사용자가 열람·수정·초기화 가능; 승인·비밀·현장 사실은 학습된 취향에서 생성하지 않는다.

**통과:** 더 싼 모델이 미지원이면 선택되지 않음, 변경/실패/stale evidence 시 안전한 명시 동작, 프로젝트 간 유출0. 품질 향상은 held-out·반복 비교 후 보고.

### A9. 새 primitive / 자기 단순화 제안

**의존:** 실제 A8 운영 증거. 지금 구현할 단계 아님.

- capability gap→영향 파일/계약/검증/비용을 담은 제안→격리 구현→회귀/관련 Isaac 또는 하드웨어 검증→별도 승인/배포.
- 단순화는 우선 전략 graph/config 차이로 표현한다. validator·receipt·정지·권한 계층 제거는 후보로 허용하지 않는다.
- 운영 중 자동 source patch/install/plugin activation 금지. staged→verified→approved→active 및 이전 버전 복귀 절차를 둔다.

## 7. 데모 진도와 장기 구조 작업의 우선순위

**첫 묶음 권고: A0 → A1a → A1b → A2.** 이 묶음이 끝나면 현재 데모를 잃지 않고 다른 프로젝트에도 이어 쓸 수 있는 최소 기반이 생긴다. A3/A4 이후에 모델 교체·자동 개선을 확장한다.

기존 실물 데모의 critical path는 별도로 유지한다:

1. 승인된 정지 상태에서 현재 boot의 odom/TF/ROS scan·현물 장착/외곽 근거 확보.
2. 실제 미터 대응점으로 방 정합 확인 및 scene/map revision 결속.
3. 현재 release/calibration 등록과 연결 readiness; 알려진 정지/단절 조건 확인.
4. 제한된 임무 범위 1회 승인 → 로컬 센서 보호 하의 자율 수행 → 명령/관측/종료 이력 → 같은 조건 Twin 비교.

1~3의 실제 사실이 없다고 모델 routing framework를 더 만드는 것으로 해결하지 않는다. 반대로 이 사실을 기다리는 동안 A0~A4의 오프라인 계약·저장·평가 작업은 진행할 수 있다. 이번 요청은 평가/계획이므로 이 문서 작성 뒤 자동으로 실물이나 야간 작업을 시작하지 않는다.

### 임무 승인 UX의 정확한 의미

- 한번 선택한 목표/허용구역/속도·시간·예산/로봇·지도·보정 버전에 대해 `임무 시작`을 승인한다.
- 그 범위 내 전진/회전/회피/정지는 자체 판단한다. 각 명령별 승인 UI를 추가하지 않는다.
- 목표/허용구역·안전한도 변경, 새 boot/보정·배포 변경, 취소/보호정지 후 재시작은 새 실행 문맥으로 처리한다.
- 재계획이 원래 scope 안인지 결정적으로 확인; 밖이면 중단/새 scope 요청. 현재 미구현 재계획을 있다고 표시하지 않는다.
- 전원 ON만으로 이동하지 않는다. 준비·연결 점검은 한 흐름, 실행은 명확한 임무 동작이다. 센서로 보이지 않는 낮은 물체·단차가 있으므로 LiDAR만으로 모든 현장 안전을 보장하지 않는다.

## 8. 단계별 검증·증거·호환 원칙

### 공통 회귀

기존 `scripts/verify_twinpulse.ps1 -SkipIsaac`를 기반으로 core/provider/app/React/build를 확인한다. 명령 실행 전에 script의 부작용·기존 도구/권한을 확인하며, 없는 의존성을 자동 설치하지 않는다. `-SkipIsaac`는 실제 Isaac acceptance를 대신하지 않는다.

- 관련 core/provider unit + App API integration + React 상태·취소 검사.
- model/probe/strategy 테스트는 먼저 fake transport; network/로봇 호출0 assertion.
- executor/wire/scene 적용 변경은 기존 `scripts/rehearse_bedroom_isaac.py` 및 관련 engine runner로 실제 엔진 검증. fake만으로 runtime PASS 금지.
- controller 경로 영향 시 `scripts/rehearse_robot_console.py`의 가짜 수동/임무·정지2종 회귀. 실제 로봇 시험은 별도 승인.
- 기존 M2-D 27/29 실패, room goal `MISSING_METRIC_REFERENCE`, live mission locked 음성 사례 보존.

### 완료 보고 형식

각 단계는 변경 파일, 실제 제품에서 호출된 경로, 실행 명령/exit code, immutable artifact 경로, 입력·코드·빌드·판정기 해시, PASS/FAIL/NOT_RUN 및 미검증 경계를 기록한다. 초기 FAIL을 최종 PASS로 덮어쓰지 않는다. Baseline/Memory/progress를 함께 갱신하되 실제 완료한 범위만 올린다.

### schema와 migration

- 기존 read/round-trip/hash golden을 유지. 내부 class 이동만으로 저장 계약 버전을 올리지 않는다.
- 새 필드는 strict reader 호환성을 고려한 새 envelope/버전 adapter로 추가. 기존 파일 일괄 rewrite 금지.
- 구형 기록은 original bytes와 당시 schema revision을 보존, 새 표현은 derived artifact로 연결한다.
- source/scene/model/strategy/engine/policy revision을 나눠서 저장. prompt 설명 변경과 physics profile 변경의 무효화 범위를 동일하게 취급하지 않는다.
- 깨진 JSON·잘못된 경로·oversized 파일·부분 저장/동시 저장·재시작 복구 검사. raw image와 credential은 report에 복사하지 않는다.
- 역호환이 불가능하면 범위/이유·reader/writer 전환·검증·복구안을 승인받은 뒤 진행한다. 이전 snapshot으로 돌아가도 물리 위치가 복원되는 것은 아니다.

## 9. Sol에게 넘길 첫 실행 지시문

아래는 **사용자가 선택해 전달할 때만 실행 승인**이 되는 복사 문안이다. 지금 자동 전송하거나 새 작업을 생성하지 않는다. GPT 6 Sol은 구현 담당이라는 의미이며 TwinPulse runtime 모델을 그 모델로 고정한다는 뜻이 아니다.

```text
TwinPulse Adaptive Architecture 계획을 단계적으로 반영해줘.

기준 저장소는 C:\Users\jaewo\Documents\TwinPulse다.
AGENTS.md, 최신 PROJECT_MEMORY/BASELINE, 다음 문서를 읽어:
docs/planning/TWINPULSE_ADAPTIVE_ARCHITECTURE_REVIEW_SOL_PLAN_2026-09-29.md

이번 승인 범위는 A0 + A1a만이다. A1b 이후는 자동 착수하지 마.
기존 실제 App Generate→Review→Build 경로와 v1/v2 호환성을 유지하면서
현재 scene tool 정의를 공통 카탈로그로 묶어줘. 새 framework를 병렬로 만들지 마.
기존 handler/semantic validator/plan 순서/직렬화와 golden hash를 보존해.
현재 차이가 있는 규칙은 자동으로 한쪽에 맞추지 말고 의도적 차이와 결함을 구분해.

현재 dirty/untracked 변경과 실측 원본을 먼저 inventory/hash로 기록하고 보존해.
core의 provider/app/Isaac 역의존을 만들지 마. 물리 코드·임무/정지 기준·권한은 변경하지 마.
로봇 접속/SSH/serial/모터/센서/배포·유료 모델 호출·설치/시스템 설정·commit/push·
타 프로세스 강제종료·새 에이전트/예약 생성은 승인하지 않는다.
권한이 없으면 우회하지 말고 정식 요청 또는 가능한 범위와 blocker를 보고해.

새 unit test만 아니라 기존 provider fake→core→App draft와 관련 엔진 계약 회귀를 실행해.
실제 Isaac이 필요한 변경은 가능하고 승인된 로컬 환경에서 기존 bounded runner로 검증하고,
불가능하면 NOT_RUN/PARTIAL로 기록해. 저장 실측/합성/Isaac/실물 증거를 섞지 마.

완료 시 실제 변경 파일·검증 결과·호환 여부·미검증·다음 A1b를 보고하고,
Baseline/Memory/progress/검증 기록을 동기화해.
설계 문서만 추가하거나 테스트 전용 새 registry만 만드는 것으로 완료 처리하지 마.
```

이후 A1b, A2 등은 같은 형식으로 선택 단계만 바꾸어 맡긴다. 한 번에 “전부 구현”을 지시하면 실물 데모 진도보다 추상화가 커질 위험이 있다.

## 10. 최종 완료의 정의

장기적으로 성공한 구조는 다음이 실제 제품에서 가능해야 한다.

1. 저장한 방/현장 프로젝트를 다음 날 다시 열어 근거·자산·목표·결과를 이어 쓴다.
2. 새 지원 모델/전략으로 같은 프로젝트를 처리해도 core·Isaac·로봇 제어 코드를 다시 쓰지 않는다.
3. 지원하지 않는 엔진/모델 조합과 준비되지 않은 실물 상태를 실행 전에 구분해 설명한다.
4. 승인된 primitive 조합으로 새 배치를 만들고 이전 revision을 보존한다.
5. 새 모델/단순한 전략이 나은지는 같은 조건의 실행·충실도·비용 근거로 비교한다.
6. 실물은 임무 단위로 승인하고 로컬 센서 판단으로 수행하며, 결과가 Twin 이력으로 돌아온다.

현재는 이 중 일부 기반과 오프라인 경로가 있을 뿐, 전체가 완료된 상태가 아니다. **첨부 방향을 채택하되, 우선순위는 모델 자동 진화보다 “현재 동작을 보존하는 공통 계약 + 지속 프로젝트 + 실제 데모 연결”이다.**
