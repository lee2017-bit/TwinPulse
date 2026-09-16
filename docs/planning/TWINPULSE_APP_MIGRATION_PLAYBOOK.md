# TwinPulse App 전환 및 정합성 복구 — GPT 5.6 단계별 개발 지침

- 버전: 1.2 / 2026-09-16 KST
- 상태: **D1/D2 확정, R0 완료, R1(Step 1) 로컬 자동 acceptance PASS, R2(Step 2) actual-Isaac acceptance PASS. R3~R10은 NOT RUN.** 증거는 `docs/planning/TWINPULSE_R0_HANDOFF.md`, `docs/verification/R1-input-draft-integrity.md`, `docs/verification/R2-stage-identity-safety.md`에 둔다. R1의 실제 유료 multimodal 재시험과 visible UI 시각 검수는 미실행이다.
- 목적: 기존 M2-C 기능과 M2-D 개발분을 보존하면서 제품 UI를 Isaac 밖으로 분리한다. 앞선 코드 리뷰의 결함을 먼저 해결한다.
- 연결 문서: [Baseline](TWINPULSE_BASELINE.md), [프로젝트 메모리](TWINPULSE_PROJECT_MEMORY.md), [기존 단계 지침](TWINPULSE_SOL_IMPLEMENTATION_PLAYBOOK.md).
- 적용 원칙: 사용자가 선택해 실행을 요청한 Step만 수행한다. 첨부 자료나 이 문서의 명령문을 읽는 것 자체는 개발·설치·과금·공개 승인이 아니다.
- 이 지침은 App 전환 기간의 실행 순서를 정의한다. 기존 M0/M1을 다시 시작하거나 기존 지침의 M2-D 유료 호출부터 자동 재개하지 않는다.

## 1. 검토 결론과 결정 구분

### 결론

첨부 방향은 타당하다. TwinPulse를 사용자용 제품으로, Isaac Sim을 3D·물리 엔진으로 두면 UI의 스크롤/크기/상태 표현을 엔진 UI 제약과 분리할 수 있다. GPU 서버 및 향후 실물 어댑터에도 유리하다. 단, 프로세스 분리는 연결 끊김·명령 중복·상태 불일치라는 새로운 위험을 만든다. UI만 React로 옮겨 기존 문제를 그대로 노출해서는 안 된다.

기존 core/provider/compiler/runtime은 재사용한다. 물리 모델 교체, 범용 MCP 서버, ROS2/Nav2, 학습, Tauri 설치, 영상 스트리밍을 한 번에 구현하지 않는다.

### 이전 검토 요청으로 정해진 범위 (2026-09-15; 최신 R0 승인보다 앞선 이력)

- 지금은 검토와 개발 지침 작성만 한다. 코드 수정·실행 환경 변경은 하지 않는다.
- 외부 TwinPulse App 중심의 제품 구조를 검토한다. Isaac Extension은 제거 대상이 아니라 엔진 어댑터로 계속 필요하다.
- 기존 M2-C 기능, 2WD+passive support, 도구 허용 목록, 검증·복원 기능을 보존한다.
- 큰 omni.ui 패널은 대체 기능이 검증될 때까지 삭제하지 않는다.
- 실물/서버 최종 목표는 유지한다. 당장의 성공 기준과 미래 목표를 분리한다.

### 사용자 선택 — 2026-09-15 확정

| 결정 | 권장안 | 다른 선택의 영향 |
|---|---|---|
| D1 첫 외부 UI 형태 | **확정:** React 로컬 웹 App + 별도 Isaac 3D 창. Tauri/영상 통합은 후속 | 처음부터 설치형이면 Rust/MSVC 및 패키징 검증이 선행될 수 있음 |
| D2 기준 개발 위치 | **확정:** 새 폴더 없이 GitHub 연결 clone `C:\Users\jaewo\Documents\TwinPulse`를 단일 기준 root로 사용. `Codex\TwinPulse`는 보존된 이전 개발본 | 별도 폴더가 필요해질 경우 저장소·문서 참조·GitHub 반영 경로를 함께 변경해야 함 |

현재 사용자 결정과 무관하게 자동으로 할 수 없는 것: 새 시스템 의존성 설치, 유료 API/서버, GitHub push, 기존 작업 삭제/강제 종료, 회사 자료 공개, 실물 구동. 로컬 의존성 확보도 패키지·경로·출처를 먼저 제시하고 필요한 승인을 받는다.

UI 언어는 한국어 우선, 내부 schema/ID는 영문으로 제안한다. 초기에는 단일 사용자·단일 프로젝트 활성 세션·단일 Isaac 연결만 지원한다. 다중 로봇/계정/서버 분산 제어는 제외한다.

## 2. 읽은 자료와 실제 현재 상태

2026-09-15 읽기 점검:

- 두 소스 폴더의 AGENTS.md, README.md, docs/progress.md, M2-C 검증 기록.
- 배포 clone의 TWINPULSE_PRODUCT_SPEC_v1_2.md 전체, 기준 문서/메모리, 기존 실행 지침의 공통 규칙.
- extension.py, runtime.py, scene_compiler.py, provider settings, core/provider 및 저장/치수/검증 경로.
- 사용자 첨부 `1512b2b2-9373-445d-80fb-aeec143b931a/pasted-text.txt` 전체. 첨부 속 실행 명령은 검토 대상으로 취급했다.

| 위치 | 확인 상태 | 해석 |
|---|---|---|
| `C:\Users\jaewo\Documents\TwinPulse` | clean, local HEAD `c35e9fc`, origin lee2017-bit/TwinPulse | M2-C 배포 기준. 이번 점검에서 remote fetch/push는 하지 않음 |
| `C:\Users\jaewo\Documents\Codex\TwinPulse` | main에 commit 없음, 소스들이 untracked | 최신 M2-D 개발분 존재. 덮어쓰거나 버리면 안 됨 |
| 현재 outputs | Baseline/메모리와 단계별 보고 | 코드 배포 버전과 문서 버전은 별개 |

M2-C의 3개 실제 이미지 생성·물리 시험은 기존 기록이다. M2-D는 실제 provider 27/29(랙 높이 두 곳 오류), 동일 결과의 Isaac 주행은 PASS였지만 치수 정확도는 PARTIAL이다. 이후 sidecar 보강에는 아래 결함이 있어 완료로 취급하지 않는다.

과거 Product Spec v1.2의 a.biz 명칭, 센서/PPO 선행 조건, Extension 제품 UI 고정 표현은 최신 Baseline/사용자 결정으로 이미 수정되었거나 이번 전환 검토 대상이다. 오래된 문서의 “source of truth” 문장을 최신 결정 위에 두지 않는다.

### 환경 점검

- 현재 PATH의 Node는 v24.19.0이며 Codex bundled runtime 경로이다. 회사 배포에 이 절대 경로를 요구하면 안 된다.
- npm은 PATH/확인한 일반 설치 경로에서 발견되지 않았고 Node bin에는 node.exe만 확인했다.
- rustc/cargo/cl은 PATH에서 미확인, `.cargo\bin`의 rustc/cargo 및 표준 vswhere 경로도 미발견. 전체 디스크에 없다고 단정하지 않는다.
- WebView2 runtime 등록은 확인했다. Tauri 빌드 성공을 확인한 것은 아니다.
- 일반 Python 환경에서 FastAPI/Uvicorn/Pydantic의 module spec은 발견됐다. 프로젝트 lock/독립 환경/실제 서버 구동 검증은 아직이다.
- 신규 설치, 앱 기동, 유료 요청은 이번 계획 작업에서 하지 않았다.

## 3. 현재 파일별 책임과 이동 판단

아래 경로는 개발/배포 root 아래의 상대 경로다. Step 0에서 정한 REPO_ROOT를 기준으로 해석한다.

| 현재 파일/모듈 | 현재 역할 | 변경 방향 |
|---|---|---|
| `packages/twinpulse_core/src/twinpulse_core/models.py`, `scene_tools.py`, `validation.py` | spec, typed plan, deterministic expansion, route gate | 유지. 모델·물리와 무관한 검증/식별 계약 추가. route capability는 후속 분리 |
| 같은 패키지 `robot_profiles.py`, `motion_control.py`, `acceptance.py` | 물리 프로필, 직선 제어 계산, 판정 | 유지. 2WD/지지륜/관성 변경 금지. 판정 범위와 계측 명칭 보완 |
| 같은 패키지 `draft_store.py` | last-generated plan 저장/복원 | v1 호환 읽기 유지, 입력·검증·bundle revision 기록으로 확장 |
| `packages/twinpulse_provider/src/twinpulse_provider/providers.py`, `service.py` | 실제 요청, cancel/timeout, 결과 검증 | 재사용. 제품 선택·파일·프로젝트 상태는 app service가 소유 |
| 같은 패키지 `measurement_constraints.py` | sidecar 읽기·plan 치수 대조 | 순수 계약/비교와 파일 읽기를 분리. core가 provider를 import하는 역의존 금지 |
| `extensions/twinpulse.extension/twinpulse/extension/extension.py` | lifecycle, omni.ui, 입력, provider 구성, key, draft, Build orchestration | lifecycle/legacy view는 남기고 orchestration을 app service로 추출 |
| 같은 폴더 `runtime.py` | Isaac 상태·timeline·physics callback·AGV 제어 | 엔진 안에 유지. 얇은 adapter로 감싸고 typed snapshot/명령 전제조건 추가 |
| 같은 폴더 `scene_compiler.py` | USD·PhysX·camera·rollback | 엔진 안에 유지. content identity와 stage ownership 수정. 다른 Python으로 이동 금지 |
| 같은 폴더 `provider_settings.py`, `credential_store.py` | carb 설정, Windows secret store | OS credential adapter를 app backend가 사용. carb 설정은 1회 비밀 없는 가져오기 |
| `scripts/verify_*.py`, `run_m2c_*.py` | 검증 runner | 유지하고 app/API/UI 회귀 추가. 기준 수치를 느슨하게 바꿔 통과시키지 않음 |

현재는 한 번의 LLM 응답으로 SceneToolPlan을 받고 로컬 registry가 실행한다. 실제 MCP transport/다중 turn 관찰-수정 agent가 이미 있다고 표현하지 않는다. MCP는 향후 명시적 도구 계약의 외부 어댑터일 뿐, 이번 UI 전환 필수 작업이 아니다.

## 4. 목표 경계와 상태 소유권

1. React UI는 입력·검토·버튼·상태 표시를 담당한다. LLM provider 키나 Isaac 객체를 보유하지 않는다.
2. Python app/backend는 project/input/draft/revision, provider job, validation receipt, API, 명령 중계를 소유한다.
3. Isaac adapter는 scene/compiler/runtime, 실제 simulation state, telemetry, camera를 소유한다.
4. core는 순수 계약·검증·결정적 변환을 제공한다. omni/pxr/carb/FastAPI/React를 import하지 않는다.

상태의 진실은 UI가 아니다. project/draft는 backend, 실제 빌드·주행은 Isaac가 권위자다. backend의 desired revision과 Isaac의 applied revision을 따로 보존한다.

외부 관리 모드에서는 기존 omni.ui의 제품 명령을 비활성화하거나 동일 app 경로로만 전달한다. 단순한 첫 구현에서는 비활성화가 우선이다. standalone legacy 모드는 기존 사용성을 유지하되, 같은 프로젝트에 두 orchestrator/저장 writer가 동시에 붙지 못하게 한다. backend 장애가 나도 자동으로 legacy writer로 전환하지 않는다.

미래 SIM/REAL은 capability가 다른 어댑터다. `reset`/`build_scene`은 simulation 전용이다. 실물 초기화/귀환 명령에 같은 의미를 부여하지 않는다. REAL/Deploy는 현재 unavailable이며 ROS2 adapter나 모터 명령을 만들지 않는다.

## 5. 추천 UI 구성

Phase 1에서 실제로 만드는 기능은 Setup / Build / Scene Review(읽기) / Simulate다. Edit는 Step 8, Replay는 Step 10에 연결한다. Optimize/Deploy는 숨기거나 “준비 예정”으로 비활성화하며 fake 결과를 넣지 않는다. 미래 Calibrate는 실물 연결 workflow에 둔다.

- 상단 고정: 프로젝트, SIM 배지, 엔진 연결/준비 상태, 입력 revision, 현재 적용된 scene revision.
- Build: 이미지 preview/교체/제거, 입력 종류(사진/도면/자동), prompt, Generate/Cancel, 바로 인접한 진행·오류.
- Scene Review: 객체 ID/종류/치수/위치, 도구 수·객체 수, 검증 항목, “추정/명시/미확인” 출처. 새 draft와 현재 stage의 차이 표시.
- Simulate: 3D 적용, Run, Pause, Reset, 카메라 맞춤. disabled 사유를 텍스트로 표시.
- Telemetry: 위치/기울기/목표 거리/횡이탈, 수집 시각·신선도·정지 이유. 미수집 값은 0이 아니라 미수집/null.
- 저장 상태/오류는 보이는 곳에 유지. 큰 빈 카드와 고정 과대 높이로 화면을 채우지 않는다.
- 1280×720/1920×1080, 브라우저 125% 배율, 작은 높이에서 버튼·키 입력·확인창이 접근 가능해야 한다. 한글 입력/IME, 키보드 tab, 실제 스크롤을 검사한다.

UI 문구: “키 저장됨” ≠ “연결 확인됨” ≠ “초안 검증됨” ≠ “3D 적용 완료” ≠ “주행 완료”. Generate 완료 후 자동 Run하지 않는다. 개략 모델 경고는 Build 전 한 번 표시하고 acknowledgement를 해당 revision에 연결한다. 치수별 반복 승인창은 기본 UX가 아니다.

Phase 1은 별도 Isaac 창을 유지한다. `focus_scene`은 카메라 맞춤이며 OS 창 foreground 전환과 다르다. 관리 launcher로 Simulation 창을 열 수 있게 하되, 이미 열린 창 활성화가 지원되지 않으면 성공처럼 표시하지 않는다. native embed나 좌표 클릭 자동화를 제품 의존성으로 넣지 않는다.

## 6. API/IPC 권장안

### 선택

**하나의 loopback HTTP/JSON backend + React 상태 polling + Isaac outbound bridge worker**를 권장한다. backend는 FastAPI/Uvicorn 단일 worker 후보이며 버전은 Step 0의 환경/lock 조사 후 고정한다.

- browser → backend: typed REST command/job/state API. 배포 빌드는 backend가 정적 UI를 제공해 same-origin으로 한다.
- Isaac → backend: stdlib HTTP client를 사용하는 전용 I/O worker가 인증 후 대기 command를 claim하고 receipt/telemetry를 보낸다. Isaac 안에 두 번째 FastAPI 서버나 웹 프레임워크를 설치하지 않는다.
- I/O worker는 USD/PhysX를 접근하지 않는다. bounded queue → Kit update 경로 → 기존 runtime/adapter 실행 → immutable snapshot/receipt queue로 처리한다.
- UI 상태 polling 제안값 5Hz, bridge command pickup 10Hz, telemetry 10Hz. 물리 loop는 기존 60Hz를 유지한다. 수치는 초기 설계값이며 실측으로 조정한다.
- 장기적으로 telemetry를 SSE/WebSocket으로 바꿔도 domain/command schema는 바꾸지 않도록 한다. 처음부터 스트리밍·gRPC·메시지 broker를 추가하지 않는다.

이 방식은 로컬 디버깅과 브라우저 테스트가 쉽고 Kit 의존성을 줄인다. 대신 polling 지연과 queue 관리 비용이 있다. 긴 build를 네트워크 thread에서 수행하거나 main thread에서 HTTP 대기하는 구현은 금지한다. USD 다중 writer의 thread safety 문제는 NVIDIA 문서에서도 경고한다. 실제 Kit API는 설치된 버전에서 확인한다. [N1]

### 두 종류 API를 구분

- Product API: 입력 업로드/수정, generation start/cancel/status, draft review, project save/load, simulation command submission.
- Engine bridge: `build_scene`, `run`, `pause`, `reset`, `focus_scene`, `get_state`; command claim/receipt/heartbeat/snapshot.
- generation은 backend가 실행한다. Isaac는 LLM 키/원본 이미지/자연어를 받을 필요가 없다.
- 서버가 관리하는 artifact ID로 이미지/프로젝트를 참조한다. UI가 임의 절대 경로, URL fetch, 셸, Python, USD 텍스트를 전달해 실행하는 endpoint를 만들지 않는다.

### versioned 계약 필수 항목

`CommandEnvelope`:

- schema_version, command_id, command_type, project_id.
- engine_session_id(엔진 재기동 때 변경), stage_epoch(새 stage/load 때 변경), control_lease_id.
- expected_applied_revision(초기 empty는 명시적 null), payload, deadline/TTL.
- Build payload는 불변 validated bundle와 identity/receipt. browser가 직접 bundle를 신뢰 가능한 것으로 지정할 수 없음.
- backend는 현재 입력과 receipt를 재검증하고, Isaac adapter도 수신 bundle의 schema/범위/ownership 및 현재 실행 capability를 독립 재검증한다. “validated=true” 플래그만으로 mutation하지 않는다.

`CommandReceipt`:

- 동일 command/session/project 식별, status=`accepted|running|succeeded|failed|cancelled|expired|unknown`.
- error_code/안전하게 정리한 message, 시작/종료 시각, 적용된 bundle/build fingerprint, stage_epoch.
- HTTP 202/accepted는 실행 성공이 아님. 성공 receipt와 Isaac snapshot이 일치한 뒤에만 3D 적용 완료 표시.

`SimulationSnapshot`:

- schema_version, engine_session_id, stage_epoch, project_id, applied_revision, run_id, sequence.
- runtime_state, safety_state/reason, permitted_commands/capabilities.
- sim_time_s, sampled_at_utc, backend 수신시각; heartbeat timeout에는 로컬 monotonic clock 사용.
- frame_id, SI units, position_m(x/y/z), yaw_rad, roll_rad, pitch_rad.
- linear_speed_mps(null 가능, 실제 측정/추정 출처), distance_to_goal_m, cross_track_error_m.
- telemetry availability/age. command 속도를 실제 속도처럼 표시하지 않는다. 새 run/engine에서 sequence와 시간이 초기화되는 것을 처리한다.

Python schema를 단일 기준으로 JSON schema/TypeScript 타입을 생성하고 drift test를 둔다. 입력은 unknown field/command/version, NaN/Inf, 과대 배열/파일, 부적절한 단위·범위를 거절한다.

### 명령·연결 안전 정책

- 한 project/engine의 mutating command는 직렬화한다. 중복 command_id+동일 payload는 기존 receipt, 다른 payload면 conflict. 무한 재전송 금지.
- timeout은 “실행 안 됨”이 아니라 결과 불명일 수 있다. 상태 조회로 reconciliation한 뒤 재시도 여부를 결정한다. exactly-once를 보장한다고 주장하지 않는다.
- 취소는 queue에서 미실행 command에는 가능. 이미 stage 변경 중이면 transaction 완료/rollback 결과를 기다리고 취소 성공을 꾸미지 않는다.
- Run은 matching built revision + route-ready + 연결 + safety-clear에서만 허용. off_route/unstable 후 Pause→Run으로 safety latch를 우회하지 못하게 한다. Reset 성공 후 새 snapshot으로 확인해야 latch 해제.
- Build/Reset은 running에서 우선 거절한다. 사용자가 Pause한 뒤 다시 요청한다. UI 밖 호출에도 같은 규칙 적용.
- UI/엔진/backend disconnect, lease 만료 때 simulation zero-drive + pause. 초기 제안은 heartbeat 1s/lease TTL 3s이며 로컬 watchdog에서 TTL+최대 2 physics/update frame 안의 반응을 검증한다. main-thread 전체 정지까지 안전을 보장한다는 뜻은 아니다.
- 재접속/재기동은 자동 Run 금지. 오래된 queue는 폐기/expired, session과 실제 scene을 다시 조회한다. 의도된 headless 시험은 browser 대신 runner가 명시적인 lease holder다.
- 전송되는 telemetry는 latest-wins coalescing으로 제한, command queue/operation history는 상한을 둔다. 빌드 중 응답을 physics 성공으로 오인하지 않는다.

### 로컬 보안

- 127.0.0.1 loopback에만 bind. 기본 외부 공개/0.0.0.0/방화벽 변경 금지.
- loopback만으로 인증이 해결되지 않는다. 세션 인증과 UI/engine 역할 구분, Host/Origin allowlist, CSRF 방어를 포함한다. CORS는 인증 대체가 아니다. [W1]
- 브라우저는 인증된 product API만, engine credential은 engine 전용 endpoint만 사용. 상호 역할 사칭 시험을 둔다.
- bootstrap 비밀은 제한 수명/일회용으로 전달하고 URL query·로그·localStorage·프로젝트에 장기 저장하지 않는다. 구체 전달 방식/TTL은 Step 3 계약 문서에 고정 후 구현한다.
- provider key는 OS credential store가 소유한다. Setup 입력은 write-only로 backend에 전달하고 읽기 API는 configured 여부만 반환. 기존 Windows credential target을 재사용하되 값은 출력하지 않는다.
- base URL 변경 시 다른 endpoint에 기존 키를 자동 재사용하지 않는 정책을 둔다. 로컬/사내 HTTP 등 예외는 사용자 설정으로 명확히 제한한다.
- 원본 이미지/도면/프로젝트는 기본 로컬 비공개. diagnostics/public repository에 자동 포함하지 않는다.

## 7. 결함 목록과 계획상 처리 위치

| ID | 근거와 위험 | 처리/회귀 |
|---|---|---|
| F1 | fixture generator의 position_m/goal_m, 2D 값이 실제 start_position_m/goal_position_m, 3D 계약과 불일치. 정답 plan 거절을 메모리 검사로 재현 | Step 1: 공통 기준 정의, generator→실제 loader→정답/오답 계획 통합 시험 |
| F2 | 새 이미지 선택/새 generation 실패 후 이전 draft Build 가능. 실제 메서드 분리 검사로 재현 | Step 1/3/5: input revision, 늦은 결과 격리, stale draft 표시, latest-input Build gate |
| F3 | restore가 plan만 검증, 원본/치수 기준/검증 버전 기록 없음 | Step 1/3: provenance+receipt, 구형 파일의 unverified import와 재검증 |
| F4 | fresh compiler가 scene.id+profile ID/prim 존재로 같은 장면 판단. runtime 캐시도 stage 변경 확인 부족 | Step 2: 실제 Isaac 재현, bundle/build fingerprint+stage epoch, 동일 ID 다른 형상 테스트 |
| F5 | stage Z-up/meters를 전체에 적용, 첫 PhysicsScene을 선택. 소유 root만 변경한다는 계약과 충돌 가능 | Step 2: 전용 stage/비호환 stage 거부 정책, unrelated stage 속성·prim 불변 검사 |
| F6 | run()이 안전정지 후 running으로 변경 가능, pause가 상태 문자열을 덮음 | Step 2/4: 별도 safety latch와 명령 전제조건, UI/API 우회 시험 |
| F7 | registry 검증이 +X 직선 controller와 결합 | Step 7: scene validity와 navigation capability 분리. controller 한계 자체는 유지 |
| F8 | sidecar는 수동 정답 파일이지 치수 OCR 아님. detail 선택은 파일명/문구 휴리스틱 | Step 5/9: 입력 타입 명시, 치수 출처, bounded extraction/검증. 유료 retry 반복 금지 |
| F9 | core/provider 통과가 UI 연결을 검사하지 않음. 도면 scorer 통로 폭/방향 범위 부족, M2-C Pause는 주행 완료 후 검사 | Step 1/6/9: 실제 workflow와 주행 중 Pause, scorer blind spot 추가 |
| F10 | 개발본/배포본이 분리되고 최신 개발본 commit 없음 | Step 0: 비교·보존·기준 경로 확정 및 검증 revision 추적 |

이전 리뷰의 확정 재현과 코드상 위험을 구분한다. 원인 추정은 실제 failure test 전에 확정 원인으로 기록하지 않는다. 특히 detail=low가 도면 오독의 확정 원인이라는 과거 표현은 A/B 검증되지 않았다.

## 8. 제안 저장소 구조

아래는 변경 예정 위치이며 현재 존재한다고 가정하지 않는다. 비어 있는 미래 폴더를 미리 모두 만들지 않는다.

```text
TwinPulse/
  apps/twinpulse-web/                         # React/TypeScript; 후속 Tauri wrapper와 UI 공유
  packages/twinpulse_core/src/twinpulse_core/  # 기존 + revision/measurement/typed contracts
  packages/twinpulse_provider/src/twinpulse_provider/ # 기존 actual/mock provider
  packages/twinpulse_app/src/twinpulse_app/    # 신규: application service, persistence, API
    application.py
    project_store.py
    settings.py
    credentials.py
    api.py
    command_broker.py
    process_manager.py
  extensions/twinpulse.extension/twinpulse/extension/
    extension.py                             # lifecycle + legacy UI 유지/managed-mode 분기
    runtime.py                               # 기존 physics 실행 유지
    scene_compiler.py                        # 기존 USD compiler 유지
    isaac_adapter.py                         # 신규 typed port
    bridge_client.py                          # 신규 loopback I/O, USD 접근 없음
  schemas/                                   # 생성한 API/TS schema 산출물
  tests/integration/                         # input/job/revision/storage/API 회귀
  tests/e2e/                                 # browser + real Isaac orchestration
  scripts/                                   # 기존 + launcher/bridge/UI 검증 runner
  docs/decisions/                             # UI/API/auth/revision/ownership ADR
  docs/verification/                          # Step별 증거
  docs/planning/                             # 승인된 이 문서 사본과 기준 문서
```

FastAPI/React 의존성은 app 전용 lock, Isaac는 기존 Python/extension 환경을 유지한다. `pyproject.toml`이 현재 core만 패키징한다는 점을 반영해 provider/app 설치 및 순수 import를 별도 검증한다. 기존 테스트용 sys.path 우회만으로 회사 설치 성공을 주장하지 않는다.

## 9. 단계별 상세 실행 지침

### 공통 실행·중단 규칙

- 아래 Step 하나만 선택하여 수행하고 증거와 다음 Step을 보고한 뒤 멈춘다. 사용자가 여러 Step을 명시 승인하면 범위 안에서 이어가되 실패 gate를 건너뛰지 않는다.
- 변경 전 실패를 재현하는 테스트를 먼저 만든다. 정상/오류/취소/재기동을 함께 검사한다.
- 현재 소스 diff에 없는 API를 있다고 가정하지 않는다. 계획의 파일 분할은 최소 범위에서 조정 가능하나 이유를 기록한다.
- mock/recorded real output/새 real provider/actual Isaac/Full viewport/UI를 결과에 구별한다.
- 일반 회귀는 유료 호출 0회. 기존 실제 provider report 재생은 “새 이미지 추론 검증”이 아니다. 승인된 새 호출은 제공자·횟수 상한을 지키고 자동 유료 retry 금지.
- 실행/검증 중 기존 사용자 Isaac 프로세스를 임의 종료하지 않는다. 새로 소유한 테스트 프로세스만 PID·시작시각·실행파일·session으로 식별한다. unsaved stage는 보존한다.
- 매 Step에 변경 파일, base/head commit 또는 dirty patch hash, 명령, 결과 JSON/로그/화면, 미검증, rollback을 기록한다. PASS는 실제 실행한 하위 범위만 의미한다.
- baseline/메모리에 미래 항목을 완료로 적지 않는다. Git push/설치/실물/과금은 단계 명칭과 별도 승인이다.

### Step 0 — 기준 코드 확정과 인수인계 (R0)

목표: 중복 개발본 때문에 작업을 잃거나 옛 코드를 수정하지 않게 한다.

작업:

1. D1/D2 답변, 두 경로 git 상태/remotes/현재 실행 extension 경로를 재확인한다. 지정하지 않은 브랜치 이름을 임의로 만들지 않는다.
2. 두 root의 소스/fixture/docs/config 차이를 파일별로 비교한다. secrets/runtime/cache/artifacts를 무차별 출력·복사하지 않는다.
3. M2-C 기준, 최신 M2-D 추가, 사용자 편집, 문서만 다른 항목을 나눈 source inventory와 보존 계획을 만든다.
4. 승인된 기준 root에 선택한 변경을 비파괴적으로 통합한다. 기존 개발본은 삭제하지 않는다. 이름 충돌/기존 수정이 있으면 중단한다.
5. AGENTS/README/Baseline/메모리/이 지침의 authoritative 위치를 맞춘다. “TwinPulse App + Isaac engine adapter”는 승인된 제품 변경으로 기록하고 과거 버전은 이력으로 보존한다.
6. Node/npm/Rust/MSVC/Python 및 lock 필요사항을 재확인한다. npm 미확인 상태에서 React build 가능이라고 가정하지 않는다. 시스템 설치 없이 필요한 로컬 toolchain 확보안을 제시한다.

예상 diff: 문서·설정 참조와 기존 M2-D 파일의 선택적 이관. 신규 UI/API/물리 로직 없음.

Acceptance: 소스 차이 전부 분류, 최신 개발분 보존 확인, 기준 root 명확, core/provider 회귀와 dependency manifest. 통합 시점을 식별할 수 있는 checkpoint를 남긴다. commit을 만들 경우 대상 파일만 검토하고 원격 push하지 않는다.

중단: D2 미확정 또는 파일 충돌이면 inventory까지만. API 호출/Isaac 재설치 금지.

### Step 1 — 입력·치수·생성 기록 정합성 복구 (R1)

목표: 새 입력의 결과와 과거 성공 결과가 섞이지 않고, 올바른 도면 계획이 올바르게 검증된다.

예상 diff:

- 기존: core/draft_store.py, provider/service.py, measurement_constraints.py, contracts.py, extension.py의 attach/prompt/generate/build/restore 관련 메서드.
- 기존: scripts/create_m2d_floorplan_fixture.py, fixtures/m2d/dimensioned_floorplan.json, core/provider tests.
- 신규 제안: core/revisions.py, core/measurements.py, tests/integration/test_generation_provenance.py.

작업:

1. F1의 필드명·차원 오류를 고치고 fixture/sidecar/scorer의 기대값 정의를 한 곳에서 파생한다. 입력에서 읽지 않은 정답을 provider 추론 결과로 위장하지 않는다.
2. InputRevision은 이미지 bytes hash, prompt, 명시 입력 종류, 독립 치수 내용, 선택 profile 및 generation 설정의 versioned digest를 포함한다. 같은 파일명에서 내용만 바뀌는 경우를 포함한다. 원본은 immutable local artifact로 snapshot한다.
3. 입력 변경 시 generation을 supersede하고 late result를 현재 draft로 승격하지 않는다. 실패 시 과거 draft/stage를 보존하되 `stale`로 구분한다. 최신 입력 Build는 차단하고 “이전 버전 열기”는 별도 명시 행동으로 둔다.
4. plan hash와 canonical expanded bundle hash를 구분한다. key 정렬, finite number, -0, default/alias normalization, ordered calls 보존 규칙을 정한다. tolerance 기반 rounding으로 다른 치수를 같은 hash로 만들지 않는다.
5. ValidationReceipt에 input/plan/bundle/measurement digest, validator version, dimensional verification 상태·오류를 기록한다. 해시는 서명이 아니므로 load/Build 때 서버가 재검증한다.
6. 구형 GeneratedDraftRecord 1.0은 보존하며 읽을 수 있게 한다. provenance가 없는 기록에 이미지 신뢰성을 만들어 붙이지 않는다. legacy-unverified로 가져온 뒤 명시 선택과 현행 검증을 거쳐 새 revision을 만든다.

Acceptance:

- generator가 만든 실제 sidecar를 loader로 읽어 올바른 실제 규격 plan은 PASS, 높이/좌표 오답은 FAIL.
- A 생성 성공 → B 이미지/문구/sidecar 변경 → A Build 차단. B 실패/취소/늦은 A 응답에서도 동일.
- 동일 파일명 다른 이미지, 이미지 제거, prompt-only 변경, 검증기 버전 변경 검사.
- save/load 뒤 receipt 재검증. corrupt/unknown version/hash mismatch는 명확한 오류와 원본 보존.
- core/provider 기존 회귀 통과. 아직 외부 UI/FastAPI를 만들지 않는다.

### Step 2 — 실제 stage identity와 실행 안전 계약 (R2)

목표: metadata가 아니라 실제 빌드 내용과 안전 상태가 맞아야 실행 가능하다.

예상 diff: scene_compiler.py, runtime.py, verify_m1_extension.py; 신규 tests/Isaac의 stale-stage/safety/ownership 사례.

작업:

1. fresh SceneCompiler + 같은 scene.id + 변경된 랙 치수/위치로 F4를 actual Isaac에서 먼저 재현한다.
2. build fingerprint = canonical bundle hash + compiler version + resolved RobotProfile/asset catalog version. 성공 적용 후에만 root metadata/receipt에 기록한다.
3. 동일 build fingerprint/stage epoch는 중복 prim 없이 idempotent. 다른 내용/새 stage/누락 prim/손상 metadata는 revalidate/rebuild. 외부 수동 변경은 stage change invalidation 또는 authored static-content 검사로 감지한다. metadata만 믿지 않는다.
4. replace 실패 시 이전 형상·identity·runtime binding을 보존한다. rollback 완료와 실패를 구분한다. 진행 중 장면을 새 정상 결과로 표시하지 않는다.
5. 전용 TwinPulse stage에서는 Z-up/meter를 명시한다. 사용자의 기존 Y-up/cm/multiple-PhysicsScene stage는 조용히 전역 변경하지 말고 비호환 오류를 내거나 별도 전용 stage 사용을 안내한다. 외부 prim/metadata 보존을 검증한다.
6. runtime은 safety latch와 state를 분리한다. off_route/unstable → Run 및 Pause→Run 우회 차단, Reset 확인 후 재가동. stage close/change 시 subscription·캐시·명령 유효성을 무효화한다.

Acceptance: 동일 ID 변경 치수 실제 USD 반영, 같은 내용 반복 prim 불변, reload/new-stage 오판 없음, 의도적 replacement 실패 보존, 외부 stage 불변, 기울기·횡이탈 stop 우회 금지. 기존 2WD/large mesh-floor/long-route/lifecycle 회귀 유지.

중단: physics 계수/바퀴 수/안전 허용치를 바꿔 문제를 감추지 않는다. F4가 재현되지 않으면 환경과 이유를 보고하고 불필요한 변경을 하지 않는다.

### Step 3 — Application service와 공통 계약 추출 (R3)

목표: 화면 종류와 상관없이 동일한 generation/project/build 상태 규칙을 사용한다.

예상 diff: 신규 packages/twinpulse_app의 application.py/project_store.py/settings.py/credentials.py; core의 application/engine 계약; extension.py·provider_settings.py·credential_store.py에 호환 wrapper; package metadata/tests.

작업:

1. extension.py의 파일 입력 정책, provider 구성, async generation, draft 승격, persistence, Build 전 검사를 UI 없는 ApplicationService로 추출한다. 기존 legacy view가 같은 service를 사용하도록 연결한다.
2. UI model/label/창 객체를 service로 옮기지 않는다. service는 typed state/event만 반환한다. 문자열 상태 메시지를 parse해서 로직을 결정하지 않는다.
3. 순수 SimulationPort와 command/snapshot/receipt schema를 고정한다. 실제 Isaac 객체는 import하지 않는다. fake port는 테스트에만 사용한다.
4. credentials OS adapter는 같은 Windows target 재사용; 기존 carb 비밀 없는 설정은 명시적 1회 migration. app 전용 저장이 생겼을 때 두 저장소 자동 양방향 sync 금지.
5. Product/API와 engine 계약, auth bootstrap/roles/TTL/ownership, runtime timeout 정책을 ADR로 고정한다. 다중 backend worker 금지(첫 버전은 1개).

Acceptance: 일반 Python에서 core/provider/app import와 generation/persistence/fake-port tests; omni/pxr/carb import 없음. 기존 legacy UI 실제 regression 유지. 오류/취소/late response가 모두 Step 1 규칙을 통과한다. key 로그/return payload 누출 없음.

중단: 기존 physics 코드를 신규 backend Python에 복사하지 않는다. 한 번에 파일 구조 전체를 바꾸지 않는다.

### Step 4 — Local API와 실제 Isaac bridge 최소 연결 (R4)

목표: 외부 프로그램이 typed command로 실제 Isaac을 제어하고 검증 가능한 결과를 받는다. 아직 React는 필수가 아니다.

예상 diff: app/api.py/command_broker.py, extension/isaac_adapter.py/bridge_client.py, extension lifecycle/managed mode, config/extension.toml의 필요한 설정만; scripts/verify_app_bridge.py 및 integration tests.

작업:

1. section 6 계약대로 loopback server와 session-authenticated bridge를 구현한다. 기존 vetted bundle fixture로 Build/Run/Pause/Reset/GetState/Focus를 연결한다.
2. network thread→bounded command queue→Kit update execution을 검증한다. build completion은 실제 compiler/runtime 결과에 따른다.
3. session/epoch/revision 검사, command deduplication, operation status, cancellation/expiry/reconnect를 구현한다.
4. UI 또는 runner의 lease + backend 연결 상실에 대한 engine-local watchdog. legacy product control은 managed mode에서 차단한다.
5. telemetry pose/attitude는 현재 runtime에서 읽는다. 아직 초기화 전 값은 authored/미수집 구분. 렌더·physics callback을 네트워크 대기로 막지 않는다.

Acceptance:

- HTTP command로 actual Isaac 생성·실제 바퀴 이동·주행 중 Pause·Reset 성공. SDK fake PASS로 대체 금지.
- duplicate Build/Run, 잘못된 revision/version/command, 동시 writer, old session 재접속, crash 후 불명 receipt를 검사.
- backend 강제 종료는 소유한 테스트 backend만 대상으로 하고 engine watchdog의 zero-drive/pause를 실제 측정.
- unauthorized/wrong-role/외부 Origin·Host/과대 payload 거절; 승인 없는 임의 코드 실행 경로 없음.
- shutdown/reload 3회에서 callback/thread/port/command 누적 없음. 기존 M2-C recorded-plan physics 회귀 유지.

중단: bridge가 동작하지 않으면 UI 작업으로 가리지 않는다. ROS2/MCP transport/WebRTC는 추가하지 않는다.

### Step 5 — React 제품 UI의 실제 vertical slice (R5)

목표: 사용자가 Isaac 패널을 조작하지 않고 입력→검토→3D 적용→Run/Pause/Reset을 수행한다.

예상 diff: apps/twinpulse-web(package/lock, src/api, state, screens, components), schemas의 generated TS, app의 product endpoints/static serving, 필요한 upload/settings endpoints, UI tests.

작업:

1. section 5 UI를 React/TypeScript로 구현한다. 의존성은 local lock으로 고정하며 CDN 의존 fake UI를 제품으로 제출하지 않는다.
2. 파일은 브라우저 업로드로 로컬 backend에 snapshot. 파일명/MIME뿐 아니라 실제 형식·크기·pixel 상한, 경로 탈출을 검사한다. sidecar optional import를 지원하되 일반 사용자가 JSON을 직접 작성해야 하는 흐름을 만들지 않는다.
3. 입력 종류를 사진/도면/자동으로 명시한다. 도면 선택은 파일명과 무관하게 provider detail을 선택하도록 연결하되 추가 과금 test는 승인 전 금지.
4. Generate/Cancel/job status → draft review → 개략성 acknowledgement → Build operation → actual applied revision → simulation state를 연결한다.
5. provider unavailable/키 미설정, 연결 중/불능, stale telemetry, geometry not applied, safety stop을 다른 상태로 표시한다. backend가 permitted_commands를 제공하고 UI disabled 사유를 보여준다.
6. managed mode에서 기존 omni.ui 제품 조작은 비활성화. standalone legacy 모드는 남긴다.

Acceptance: 브라우저 조작으로 deterministic backend/real Isaac 경로 E2E, 모든 단계 revision 일치, 작은 화면/배율/한글/스크롤/키보드 테스트와 screenshot. mock server만 붙은 UI는 통합 PASS가 아님. 실제 provider 새 요청은 별도 승인된 smoke에서만 확인하며 미실행이면 명시한다.

### Step 6 — 자동 기동·관찰·회귀와 Phase 1 종료 (R6)

목표: 반복 PowerShell 입력·사용자 screenshot 중계 없이 통합 상태를 검증하고 재현한다.

예상 diff: app/process_manager.py, scripts/launch_twinpulse_app.ps1, scripts/verify_app_e2e.py, tests/e2e, 기존 verify_twinpulse.ps1의 선택적 App suite, 설치/사용 docs.

작업:

1. launcher는 backend와 승인된 Isaac 실행파일을 관리하고 브라우저 UI를 연다. command allowlist와 고정 executable/config를 사용하고 browser 요청 문자열을 shell에 전달하지 않는다.
2. ready 판정은 PID 존재가 아니라 authenticated engine handshake+capability+stage readiness. stderr/error를 UI에서 볼 수 있게 한다.
3. 실행 실패/port 충돌/중복 클릭/engine exit를 유한 timeout으로 처리한다. 사용자 Isaac 프로세스는 자동 종료하지 않고 attach 가능 여부 또는 수동 저장 필요를 표시한다. 소유 process shutdown과 사용자 process를 구분한다.
4. browser screenshots + 실제 Isaac viewport의 공식 capture API 결과 + receipt/trajectory/metrics/revision manifest를 실행별로 남긴다. capture 미지원/black frame이면 명시적 FAIL/NOT RUN으로 남기고 반복 GPU 기동을 무제한 하지 않는다.
5. 기존 M2-C의 저장된 real provider output 3개를 실제 physics로 재생한다. 새 provider 추론은 별도 승인/결과로 분리한다. Pause는 주행 도중, Reset은 도중/완료 후 둘 다 검사한다.
6. fresh clone/격리 환경에서 app backend 설치, frontend build, engine 연결을 검증한다. Codex bundled 경로가 없으면 실패하는 숨은 의존을 없앤다.

Phase 1 acceptance:

- F1~F6 테스트, 기존 core/provider/Isaac 회귀, React→backend→real Isaac 통합이 각각 PASS.
- 새 입력/실패/재기동 후 stale 결과를 최신으로 표시하지 않음.
- 외부 UI로 실제 장면·주행 관찰 가능. 정지/Reset/재접속 정책 actual test.
- API auth/role/ownership 검사와 비밀 없는 evidence.
- 이미 승인된 live-provider 출력 재사용은 회귀로 표시. 새 real-provider App smoke가 승인되지 않아 NOT RUN이면 “Phase 1 통합 완료”가 아니라 “로컬 회귀 완료, live smoke 대기”로 보고.
- 기존 legacy UI 삭제는 하지 않는다. 축소/기본 숨김 전환은 parity 결과와 사용자 승인 후 별도 작은 변경으로 한다.

### Step 7 — 장면 검증과 주행 capability 분리 (R7, Phase 2)

예상 diff: core/scene_tools.py, validation.py, models.py의 필요한 versioned 분리; provider schema/service; app review/state; adapter build/run gate; tests.

1. scene schema/geometry validity, robot spawn safety, task feasibility를 별도 결과로 만든다. registry가 고정 controller 때문에 정상 geometry를 변경하도록 강요하지 않는다.
2. SceneToolPlan/SpecBundle v1은 호환 wrapper로 보존한다. 필요한 v2 authoring record에서는 scene-only/unsupported task 상태를 명시한다. 모든 필드를 nullable로 바꾸는 무계획 개편 금지.
3. 도면 geometry가 유효해도 현재 controller가 수행 못하면 Review/Build는 지원 범위에서 허용, Run은 reason과 함께 차단한다. unbuildable physics/spawn collision/invalid shape gate는 유지한다.
4. provider의 +X 경로 맞추기 지시를 scene inference에 강요하지 않도록 변경한다. 초기 task는 명시 default profile과 사용자가 볼 수 있는 제한된 proposal로 둔다.

Acceptance: 세로/반대방향/ㄱ자 작업 요청에서 geometry 보존 + unsupported navigation 표시; 기존 +X fixture 실행 유지; invalid collider/spawn 거부. 새로운 navigation 알고리즘/ROS2 도입은 이 Step의 범위가 아니다.

### Step 8 — stable ID 기반 최소 편집 (R8, Phase 2 / 기존 M3-A 연결)

예상 diff: core/edit_contracts.py/scene_tools.py, provider의 제한 edit schema, app/edit service, React Review/Edit, adapter replace, tests.

1. 첫 편집은 랙 한 행 move/resize와 task goal 변경으로 제한한다. semantic ID와 expanded child IDs의 매핑을 유지한다.
2. 입력은 현재 scene summary+base revision+사용자 요청. LLM은 허용 edit plan만 제안한다. 모호한 대상은 한 가지 질문으로 확인한다.
3. 변경 전후 diff/validation과 적용 버튼, 한 단계 undo를 제공한다. geometry revision 충돌/주행 중 수정은 거절한다.
4. “전체 재생성”과 “지정 객체 수정”을 분리한다. target 이외 객체/프로필은 불변이어야 한다. 변경이 명시 치수와 충돌하면 assumption/constraint 수정 여부를 한 번 묻고 정답을 조용히 덮어쓰지 않는다.

Acceptance: 오른쪽 랙 이동/높이 수정/goal 변경, 잘못된 ID/모호한 대상/충돌/동시 stale edit/undo, actual USD diff와 receipt 일치. 전 장면 재생성으로 편집 테스트를 통과시키지 않는다.

### Step 9 — 도면 판독 정확도와 출처 개선 (R9, 제한된 M2-D 재개)

예상 diff: provider/input observation 계약 및 optional extraction adapter, core/measurement attribution, app 검토 UI, M2-D generator/scorer/다양한 fixture.

1. PNG/JPEG 치수 탑다운 도면으로 지원 범위를 먼저 고정한다. PDF/CAD/video/general OCR 엔진 설치는 별도 범위다.
2. 관측(치수 문자열·단위·근거 영역·대상 후보·추정 여부)과 semantic scene planning을 분리한다. 같은 LLM의 2차 답변은 독립 정답으로 취급하지 않는다.
3. 독립 sidecar는 테스트 ground truth/사용자 제공 치수에 사용한다. 사용자용 제품은 sidecar 없이도 개략 생성·검토를 제공하고 unknown dimension을 정답이라고 하지 않는다.
4. floor/rack/object별 identity에 치수를 연결한다. occurrence만으로 서로 다른 랙을 같은 규격으로 강제하지 않는다. 사용자 명시 치수/도면 관측 충돌 정책을 표시한다.
5. scorer에 실제 통로 clear width, orientation, object association, units를 추가한다. 서로 다른 길이·단위·방향·랙 높이의 held-out 도면 2~3개를 확보한다.
6. 유료 횟수·비용을 승인받은 뒤 한정 실험. 같은 실패의 자동 재호출을 하지 않는다. structured rejection이면 오류 자료를 남기고 멈춘다.

Acceptance: 기본 도면 기존 29항목+새 의미 검사, held-out 도면별 실측 결과와 actual 3D 치수. 합성 fixture의 정답을 provider response에 넣은 시험은 inference PASS가 아님. 범용 정밀 복원을 주장하지 않는다.

### Step 10 — 프로젝트 저장·재열기·Replay (R10 / 기존 M3-B 연결)

예상 diff: app/project_store.py, core/project manifest/run records, React project/replay view, Isaac replay adapter, tests/docs.

1. Step 1의 draft 저장을 project bundle로 확장: input references/hash, scene/task/profile/revision, measurement/validation receipt, edit history, 실행 artifact. credentials 제외.
2. 파일 누락·버전 차이·이동 경로·corrupt/불완전 저장을 검사. 자동으로 마지막 다른 프로젝트를 여는 fallback 금지.
3. Replay는 기록 재생이다. physics controller와 배타적으로 pose writer를 선택하고 실물 command sink를 사용할 수 없게 한다.
4. 실제 USD Save와 product project Save를 구분한다. USD만 열었다고 원본 이미지·생성/편집 이력까지 복원됐다고 표현하지 않는다.

Acceptance: 다른 경로 저장/재열기에서 ID·치수·task/profile/receipt 일치; replay start/pause/seek/end와 SIM 전환 반복; Replay 중 physics/real 명령 없음. 역직렬화로 코드/임의 경로 실행 불가.

### 이후 별도 milestone — 이번 일괄 구현 대상 아님

- Tauri 설치형 wrapper: 승인된 Rust/MSVC toolchain과 packaging/signing/process lifecycle. React/product API를 재사용하고 Python backend를 Rust로 다시 쓰지 않는다.
- GPU 서버 full Isaac: 기존 M4. local API를 그대로 WAN에 열지 않고 인증/TLS/접근 범위/실행비용을 별도 설계한다.
- viewport streaming: 공식 NVIDIA 경로/버전/입력 제어/지연/라이선스 재확인 후 별도 milestone. 포트 개방 없이 가능하다고 미리 약속하지 않는다.
- ROS2/Nav2/실물 2WD/최적화: 기존 M5~M7. Reset/Deploy/비상정지는 capability별 계약과 현장 승인으로 분리한다.

## 10. Phase 1 최소 diff 범위와 회귀 위험 요약

Phase 1 = Step 0~6. 핵심 수정은 기존 파일에 집중하고 신규 코드는 app service/API, 얇은 Isaac bridge, React UI, 자동 검증만 추가한다.

- 보존: profiles, differential physics, floor mesh, current controller/한계, template implementations, 기존 fixtures/harness.
- 이동/추출: product orchestration·project/settings/credential adapter. 구현 body를 한 번만 두고 legacy wrapper로 import 호환 유지.
- 변경: provenance/identity, 안전 state, stage ownership, bridge lifecycle. 이 부분은 실제 Isaac 회귀 필수.
- 신규: pure schemas, backend broker, typed bridge adapter, UI, launcher/evidence tests.
- 제외: 새로운 wheel/contact physics, ROS2/Lab, generic code/MCP execution, native viewport embed, 학습/배포 기능, 전면 디렉터리 재작성.

최대 회귀 위험은 UI 외형이 아니라 (1) async 늦은 결과, (2) 두 writer, (3) stage reload와 stale binding, (4) network worker의 잘못된 USD 접근, (5) shutdown 중 지연 명령, (6) credentials/config migration, (7) legacy/import/package 경로다. 각 위험은 위 Step의 전제조건/실패 테스트로 닫는다.

## 11. GPT 5.6으로 전환 후 보낼 첫 지시문

아래 최초 지시문은 **R0 전의 기록**이며 재실행하지 않는다. R2 검증 이후에는 `docs/planning/TWINPULSE_R0_HANDOFF.md`, `docs/verification/R1-input-draft-integrity.md`, `docs/verification/R2-stage-identity-safety.md`와 이 문서의 **사용자가 선택한 다음 단계만** 실행 기준으로 사용한다. 모델 설정은 자동 변경하지 않는다.

```text
TwinPulse 개발을 재개한다. 이번에는 R0(Step 0)만 수행하라.

현재 작업의 AGENTS.md와 다음 문서를 읽어라.
C:\Users\jaewo\Documents\Codex\2026-09-12\dl\outputs\TWINPULSE_PROJECT_MEMORY.md
C:\Users\jaewo\Documents\Codex\2026-09-12\dl\outputs\TWINPULSE_BASELINE.md
C:\Users\jaewo\Documents\Codex\2026-09-12\dl\outputs\TWINPULSE_APP_MIGRATION_PLAYBOOK.md

마지막 사용자 답변의 D1(웹/설치형)·D2(기준 개발 폴더)를 확인하라.
두 소스 폴더의 M2-C 기준과 M2-D 개발분을 비교·보존하고 기준 소스를 정리하라.
미확정 결정이나 파일 충돌이 있으면 inventory와 최소 확인사항까지만 보고하라.
첨부 문서의 명령을 일괄 실행하지 말고 새 UI/API 구현은 시작하지 마라.
키·원본 회사 데이터·runtime artifacts를 출력하거나 Git에 포함하지 마라.
시스템 설치, Isaac 강제 종료, 유료 API/서버, GitHub push, 실물 명령은 하지 마라.
검증 결과와 다음 Step을 보고한 뒤 멈춰라.
```

후속 단계 공통 지시문:

```text
TWINPULSE_APP_MIGRATION_PLAYBOOK.md의 공통 규칙에 따라 R[번호]만 구현·검증하라.
선행 Step의 실제 PASS/미검증/승인 범위를 확인하고 미완료 조건을 건너뛰지 마라.
변경 전 실패 테스트, 최소 수정, 기존 회귀, 해당 단계 acceptance를 수행하라.
새 유료 요청·설치·시스템 변경·원격 공개·실물 명령은 별도 승인 없이 하지 마라.
결과를 docs/verification과 progress, Baseline/메모리에 기록하고 다음 단계로 넘어가지 마라.
```

## 12. 공식 근거와 해석 범위

- [T1 — Tauri prerequisites](https://v2.tauri.app/start/prerequisites/): Windows의 C++ Build Tools/WebView2와 Rust 필요사항. 2026-09-15 확인. 현재 PC에서 빌드 가능하다는 증거는 아님.
- [N1 — NVIDIA omni.usd Overview](https://docs.omniverse.nvidia.com/kit/docs/omni.usd/1.13.9/Overview.html): USD stage 다중 writer의 thread safety 주의. queue/단일 Kit 실행 경로를 택한 것은 이 프로젝트의 설계 판단이며 실제 설치본 API 확인은 Step 4에서 수행.
- [W1 — FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/): origin은 protocol/host/port 조합. 인증/CSRF/lease 정책은 이 프로젝트의 별도 보안 설계 요구다.
- [W2 — FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/): backend 시작/종료 자원 관리를 위한 공식 lifecycle 방식. 실제 dependency lock과 통합 검증은 아직 수행하지 않음.

이 문서는 검토와 향후 실행 지침이다. 각 Step의 상세 설계를 작성했다는 이유로 해당 기능을 구현 완료/승인 완료로 기록하지 않는다.
