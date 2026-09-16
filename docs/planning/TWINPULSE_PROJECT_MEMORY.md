# TwinPulse — 프로젝트 메모리

- 연결된 기준: **Baseline v1.0.33**
- 갱신일: **2026-09-16 (KST)**
- 상세 기준 문서: [TWINPULSE_BASELINE.md](TWINPULSE_BASELINE.md)
- 단계별 Sol 지시서: [TWINPULSE_SOL_IMPLEMENTATION_PLAYBOOK.md](TWINPULSE_SOL_IMPLEMENTATION_PLAYBOOK.md)
- 최신 App 전환/결함 수정 지침: [TWINPULSE_APP_MIGRATION_PLAYBOOK.md](TWINPULSE_APP_MIGRATION_PLAYBOOK.md). **D1/D2·R0 완료, R1 로컬 자동 acceptance PASS, R2 actual-Isaac acceptance PASS, R3 application/contract acceptance PASS, R4 loopback/actual-Isaac bridge acceptance PASS; R5~R10 미착수.** 다음 구현 요청은 선택한 Step만 따른다.
- M0-A 결과: [TWINPULSE_M0A_READINESS.md](TWINPULSE_M0A_READINESS.md)
- M0-B 결과: [TWINPULSE_M0B_RUNTIME_PRECHECK.md](TWINPULSE_M0B_RUNTIME_PRECHECK.md)
- M1 결과: [TWINPULSE_M1_IMPLEMENTATION.md](TWINPULSE_M1_IMPLEMENTATION.md)
- M2-A 결과: [TWINPULSE_M2A_IMPLEMENTATION.md](TWINPULSE_M2A_IMPLEMENTATION.md)
- M2-B 결과: [TWINPULSE_M2B_IMPLEMENTATION.md](TWINPULSE_M2B_IMPLEMENTATION.md)
- M2-C 결과: [TWINPULSE_M2C_IMPLEMENTATION.md](TWINPULSE_M2C_IMPLEMENTATION.md)
- M2-D 치수 도면 결과: [TWINPULSE_M2D_IMPLEMENTATION.md](TWINPULSE_M2D_IMPLEMENTATION.md)
- M2 RobotProfile v2 교정: [TWINPULSE_M2_ROBOT_PROFILE_V2.md](TWINPULSE_M2_ROBOT_PROFILE_V2.md)
- generated-floor 안정성 결과: [TwinPulse repository `docs/verification/M2-generated-floor-stability.md`](../verification/M2-generated-floor-stability.md)
- 현재 상태: **기존 M0-A/B, M1-A/B, M2-A/B/C의 제한된 PASS 기록 보존; M2-D PARTIAL; App 전환 R0 완료·R1 로컬 자동 acceptance PASS·R2 actual-Isaac acceptance PASS·R3 application/contract acceptance PASS·R4 loopback/actual-Isaac bridge acceptance PASS·R5~R10 미착수**. R4는 인증된 loopback broker와 실제 Isaac managed bridge, 연결 상실 watchdog을 검증했으며 React/원격 접속/유료 provider/wheel 공개·회사 PC 설치는 포함하지 않는다. M2-D 실제 provider의 랙 높이 오류로 27/29와 동일 bundle의 Isaac 주행 PASS는 보존한다.
- 성격: 프로젝트 파일 기반의 지속 기록. 계정 전체 내장 메모리 저장을 의미하지 않음.

### 최신 결정·R0/R1/R2/R3/R4 실행 — 2026-09-16 (아래 과거 상태 설명보다 우선)

- **D1 확정:** 첫 제품 UI는 로컬 React 웹 App, 3D/물리는 별도 Isaac 창. legacy Extension UI는 대체 검증 전 보존.
- **D2 확정:** `C:\Users\jaewo\Documents\TwinPulse` 기존 GitHub 연결 clone이 단일 기준 개발 root. 새 폴더 불필요. `C:\Users\jaewo\Documents\Codex\TwinPulse`는 삭제·이동하지 않은 보존 개발본.
- **R0 완료:** clone의 clean M2-C `c35e9fc`에 M2-D 신규 6·수정 11 소스 파일을 정확한 원본 해시로 이관; clone 전용 제품 사양서 보존. 기준 root에서 Core 24/24, Provider 13/13 PASS. 이관은 M2-D 29/29 또는 새 UI/Isaac runtime 검증이 아니다. 증거/rollback은 기준 저장소 `docs/planning/TWINPULSE_R0_HANDOFF.md`.
- **R1 로컬 검증 PASS:** 입력 bytes/prompt/측정/profile/settings revision, 변경 시 generation supersede와 stale Build gate, v2 receipt의 저장·복원·Build 재검증, v1 legacy-unverified 및 별도 이전 draft 검토/rebind를 구현. 실제 generator sidecar의 정답 PASS/높이·좌표 오답 FAIL, 통합 9/9·Core 24/24·Provider 13/13, Isaac 6.0.1 headless Extension smoke PASS. 증거는 [R1-input-draft-integrity.md](../verification/R1-input-draft-integrity.md). 실제 유료 multimodal/visible UI는 미실행.
- **R2 actual-Isaac 검증 PASS:** 동일 scene ID의 변경 치수 미반영(F4)을 실제 USD에서 재현한 뒤 canonical bundle/compiler/catalog/resolved-profile fingerprint, success-only build receipt, authored-content 검사·복구, reload/new-stage/단위·ownership, replacement rollback, stage binding 무효화 및 off_route/unstable Reset latch를 구현했다. R2 전용 acceptance와 기존 lifecycle 3/3, short run 3/3, 2WD+2 passive support, large mesh-floor/6.9m route가 PASS했다. 증거는 [R2-stage-identity-safety.md](../verification/R2-stage-identity-safety.md).
- **R3 application/contract 검증 PASS:** `twinpulse_app`로 generation/input epoch/project persistence/Build gate를 추출하고, `twinpulse_core.engine_contracts` schema 1.0과 Windows credential/non-secret settings adapter를 고정했다. 일반 Python R3 9/9, Core 24/24, Provider 13/13, R1 통합 9/9 및 full actual-Isaac runner가 PASS했다. 격리된 환경에서 core/provider/app 0.1.0 wheel build와 별도 clean install/`pip check`도 PASS했다. 증거는 [R3-application-service-contracts.md](../verification/R3-application-service-contracts.md).
- **R4 loopback/actual-Isaac bridge 검증 PASS:** 127.0.0.1 인증 API, product/engine 역할 분리, 단일 writer/lease/session broker, bounded network-to-Kit queue, managed Extension adapter와 연결 상실 watchdog을 구현했다. R4 일반 Python 6/6, HTTP를 통한 실제 Isaac Build/Run/Pause/Reset/GetState/Focus, backend 종료 후 pause, lifecycle/reconnect 3/3 및 full runner `20260916-212014`가 PASS했다. 증거는 [R4-loopback-isaac-bridge.md](../verification/R4-loopback-isaac-bridge.md).
- **현재 다음 단계:** R5 React 제품 UI는 사용자 선택 전 미착수. R4에서 외부 포트, 유료 호출, GitHub push, ROS2/MCP/WebRTC, 실물 구동 없음.

### 이전 검토·요청 — 2026-09-15 (이하 이력)

- 사용자 요청: 기존 구현 전체 검토 후, 첨부된 외부 TwinPulse App 구조와 결함 수정을 통합한 GPT 5.6용 상세 단계 지침. 지금은 개발하지 않는다.
- 리뷰: sidecar generator가 실제 도구와 다른 좌표 필드/차원을 사용해 정답 plan도 거절; 새 입력 뒤 이전 draft Build 가능성을 재현했다. 기존 13/24 단위 테스트만으로 workflow 안전성을 보장하지 않는다. stage identity/ownership, safety latch, 복원 provenance도 수정 대상이다.
- 과거 high-detail 보강이 오독 원인을 해결했다는 확정 근거는 없다. sidecar는 독립 치수 기준 파일이며 자동 OCR이 아니다. 통로/방향 등 scorer 범위도 보강한다.
- 권장 구조: React UI → 별도 Python app/backend → typed loopback bridge → 기존 Isaac runtime/compiler. legacy UI는 대체 검증 전 삭제 금지. 2WD/실물/서버 최종 목표 유지.
- 당시 사용자 확인 대기였던 D1/D2는 위 최신 결정으로 확정됐다.
- 소스 snapshot: GitHub 연결 local clone은 clean `c35e9fc`(M2-C), `Codex\TwinPulse`에는 untracked M2-D 개발분과 commit 없는 main이 있다. 원격 fetch/push 또는 파일 이동은 하지 않았다.
- 환경 snapshot: Node v24.19.0(Codex bundled), WebView2 등록 확인. npm/Rust/Cargo/MSVC는 조사한 PATH/표준 경로에서 미확인. Python FastAPI/Uvicorn/Pydantic 발견은 설치·구동 검증 완료를 뜻하지 않는다.
- 다음 권장 순서: D1/D2 확인 → R0 소스 정리 → R1 정합성 → R2 stage/안전 → R3 app service → R4 bridge → R5 React → R6 자동 E2E. R7~R10 장면/주행 분리·편집·도면 정확도·Replay는 후속.
- 이번에는 문서만 작성/수정. 코드, 시스템/패키지 설치, Isaac 기동, 유료 호출, GitHub push, 실물 명령 없음.

## 반드시 유지할 사용자 결정

1. TwinPulse는 새로운 시뮬레이터가 아니다. 현재 구현은 **Isaac Sim Extension**이며, 최신 요청에 따라 외부 TwinPulse App이 제품 UI를 소유하고 Extension이 엔진 어댑터로 남는 전환을 검토 중이다. 실제 전환 구현은 미착수다.
2. 대상은 정적 창고/공장이지만 **3D 환경과 물리 시뮬레이션**이다. AGV의 planar navigation과 2D 제품을 혼동하지 않는다.
3. 첫 버전은 실물 AGV 없이 **일반 이미지+자연어 → 대략적인 3D 환경/장비+predefined AGV → 실제 시뮬레이션 실행**에 집중한다.
4. 일반 사진은 정밀 복원 입력이 아니다. 실행 시 개략 모델 경고창 하나를 표시한다. 정확한 환경에는 치수 있는 탑다운 도면/스캔이 필요하다. 치수별 반복 승인 UX를 기본으로 넣지 않는다.
5. 첫 prototype에서 이미지 기능을 조용히 빼지 않는다. 내부 텍스트-only/mock 시험을 multimodal 완성으로 보고하지 않는다.
6. 회사 설치는 중간 테스트다. 최종 목표는 NVIDIA/Nebius 해커톤 제출이며 **GPU 서버에서 full Isaac Sim 실행**이 필요하다.
7. 실물 최종 흐름: 실제 환경 이미지·영상·설명 → predefined AGV 선택 → 1차 scene → AGV scan → 좌표/장애물 보정 → 점수 기반 학습 → 실제 Deploy와 결과 확인.
8. 사용자가 생각한 배포 대상은 ROS2 navigation parameter다. 충돌을 피하면서 이동 거리·시간 낭비를 줄이고 부드러운 주행을 얻는 것이 목표다.
9. Isaac Simulation / Replay / Live / Deploy의 상태 주체를 구분한다. 학습은 Extension 안이 아닌 **별도 worker**에서 실행한다.
10. 실물 AGV는 아직 없으며 사용자가 저렴한 센서 탑재 AGV 구매를 검토할 예정이다. 총예산·모델 미정.
11. 트랙은 약 2m×2m 바닥과 0.5m 벽을 생각 중이지만 확정 설계가 아니다.
12. 보정의 우선순위는 좌표 정합과 장애물 위치다. wheel 자동 보정은 측정 후 필요할 때 추가한다.
13. 완전 신규 프로젝트다. 무관한 기존 FPV/제조 PoC를 수정·재사용하지 않는다.
14. 사용자는 이 프로젝트 입력의 외부 전송이 가능하다고 했다. 공개 배포/저장소 공개는 별도 권리와 승인 확인이 필요하다.
15. a.biz는 사내 LLM Base URL 이름에 관한 설명이다. **A.dot Biz라는 제품으로 단정하지 않는다.** SKT 계열사 제공, custom model ID. 실제 endpoint/protocol/vision capability 미확정.
16. 목표 interaction은 LLM이 이미지와 자연어를 분석해 미리 허용된 장면 생성·검증·시뮬레이션 도구를 선택·호출하는 Copilot형 orchestration이다. MCP는 외부 도구 transport 선택지이며, Extension 내부 typed tool registry로 같은 안전 계약을 구현할 수 있다.
17. 실물 목표의 `2W`는 총 바퀴 수가 아니라 **좌·우 2개 구동륜**을 뜻한다. 기본안은 differential 2WD+passive caster 1~2개이며, 실제 구매 기체가 4WD이면 별도 RobotProfile/adapter로 교체한다. LLM이 바퀴·캐스터·질량·관성·안전한계를 생성하지 않는다.

## 핵심 구현 판단

- 첫 장비 생성은 parameterized primitive/curated template 기반. 임의 사진의 정확한 역설계나 임의 장비의 작동 모델 생성은 아님.
- 목표는 multimodal LLM planner → 검증된 tool plan/calls → 허용된 scene tool registry/compiler. 현재 단일 SceneSpec/TaskSpec compiler는 중간 구현이다. 임의 Python/셸 실행 금지.
- scene authoring, RobotProfile 선택, navigation task intent와 simulation runtime을 구분한다. MCP는 외부 process/service용 선택적 adapter이며 실시간 wheel/motor loop를 담당하지 않는다.
- 자동 acceptance는 XY 도착만으로 PASS하지 않고 support structure, roll/pitch, vertical range, 횡이탈, collider overlap과 goal error를 기록한다. `scripts/verify_twinpulse.ps1`이 실행별 artifact를 만든다.
- generated plan/draft는 reload 뒤 복원하고, generated-build가 sample fixture로 조용히 fallback하지 않게 한다. sample action은 별도이며 UI/로그에 image count와 실제 build source를 표시한다.
- 첫 Playground의 필수 선행 조건으로 ROS2·Isaac Lab·WSL·Docker를 만들지 않음.
- ROS2/Nav2와 학습 worker는 단계적으로 분리 도입. 실물 저수준 제어와 watchdog은 현장에 둠.
- Nav2 자체가 smooth path를 만들 수 있으므로 적절히 설정된 비학습 baseline과 비교.
- PPO 예제가 자동으로 Nav2 parameter artifact를 만들지는 않음. adapter와 평가 설계 필요. 일반 탐색을 RL로 부르지 않음.
- 2D LiDAR는 3D 환경의 한 높이 단면만 관측. 알려진 높이를 적용한 extrude와 실제 높이 측정을 구분.
- 가려진 환경의 전체 scan은 이동과 여러 시점을 필요로 함. 기존 mapping 도구 활용을 우선 검토.
- 센서 기준안: encoder/odom + 360° 2D LiDAR 우선, IMU 권장, ROS2 driver와 비상정지/watchdog. 구매 전 예산·모델·Jazzy 동작 확인.
- Token Factory는 추론 API, AI Cloud는 GPU 실행 자원. 크레딧과 quota를 혼동하지 않음.
- H100/H200/L40S 중 full Isaac Sim은 L40S 우선 검토. VRAM만 보지 말고 RT 지원을 확인.

## 환경 조사 snapshot — 2026-09-12

### 현재 접근한 PC: 직접 조회

- Windows 10 Pro 22H2, i7-10750H, RTX 2070 Max-Q 8GB, driver 592.82, RAM 약 16GB.
- `C:\isaacsim`은 **6.0.1-rc.7+release.42383.32955d8d.gl**, Kit 110.1.2, bundled Python 3.12.13.
- 공식 standalone ZIP 10,600,096,696 bytes와 MD5 `c7fa3a830b251f10305cd7883039df9b`를 검증해 설치. ZIP은 작업 폴더에 보존.
- bundled checker: driver/GPU/Windows supported, VRAM 8.59GB < 10GB 및 RAM 16.94GB < 32GB로 최종 FAILED.
- Full 앱은 PhysX/wheeled-robot Extension을 포함해 부팅. procedural differential-drive, CPU physics, MinimalRendering 시험은 직진·회전·pause/resume/reset을 3회 PASS.
- 매 회 직진 0.078613m, 회전 0.692385rad, pause drift 0m, reset 위치/yaw 오차 0. 최신 smoke 로그에 PhysX/CUDA fatal 및 non-uniform scale 오류 없음.
- 활성 root의 5.1은 제거됐다. 약 21.85GiB의 안전 백업 `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\work\isaacsim-5.1-backup`은 삭제 정책 차단으로 남아 있음.
- 일반 Python 3.12.10은 Isaac bundled Python과 별도다.
- Isaac Lab 미설치, ROS2/Pixi PATH 미발견. 전체 디스크 부재 단정은 금지.
- Docker CLI는 있으나 engine 연결 미확인. WSL 조회 접근 거부로 상태 미확인.
- 현재 PC는 6.0.1 권장 실행 기준과 checker VRAM/RAM 최소치에 미달. 최소 CPU physics PASS를 복잡 scene/RTX 안정성으로 확대 해석하지 않음.

### 회사 안내서: 보고된 사례, 직접 재검증 아님

- D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64, D:\IsaacLab.
- Python 3.12.13, torch 2.10+cu128, torchvision 0.25+cu128, RSL-RL 5.0.1, Warp 1.13.
- RTX 3500 Ada 약 12GB / driver 580.92 보고.
- CUDA 인식·Kit 표시·USD 로딩 사례와 PhysX CUDA error 700 등 실패 기록이 함께 있음.
- **완전한 physics/학습 성공이 증명된 환경으로 취급하지 않음.**

### 목표와 주의점

- Isaac Sim 6.0.1 / Kit 110.1.2 / Python 3.12 계열. 실제 build/patch/hash는 대상에서 고정.
- Lab 검토 tag v3.0.0-beta2.patch1. exact commit은 아직 미고정.
- Windows ROS2 Jazzy/Pixi의 moving main과 회사 standalone/torch 조합은 다름. 전략·RMW·commit/lock 선택 필요.
- M0-B에서 Isaac 6.0.1 설치와 제한된 local runtime 시험만 수행. Lab/ROS2 설치, 시스템 설정 변경, 클라우드 생성, 실물 구동은 하지 않았음.

## 단계와 재개 지점

| 단계 | 목표 | 상태 |
|---|---|---|
| Baseline | 지침서·메모리·변경 규칙 | 완료 |
| M0-A | 작업 경로·실행 대상·환경 차이 확인 | PASS |
| M0-B | 승인된 runtime의 physics·AGV smoke test | 제한 조건부 PASS |
| M1 | Extension + 고정 3D scene + predefined AGV | local 제한 조건 PASS |
| M2-A | provider contract/mock + Copilot형 UI shell | PASS; 교정 UI 사용자 확인 |
| M2-B | 이미지+자연어 planner→허용 도구→검증→scene 연결 | PASS; real image 1장→14 tools/59 objects→134 prim generated Build 및 reload 복원 확인 |
| M2-C | 3개 이미지 fixture E2E와 계측 | PASS; 실제 provider 3/3, Isaac physics 3/3, collision 0 |
| M2-D | 치수 탑다운 도면의 정확 좌표 판독과 3D 변환 | PARTIAL; real provider/Isaac E2E 실행, 27/29 FAIL(랙 높이 3m→2m 오독), physics PASS |
| M3 | Copilot 수정·저장·Replay | 미착수 |
| M4 | GPU 서버에서 동일 Extension E2E | 미착수 |
| M5 | ROS2/Nav2 시뮬레이션 연동 | 미착수 |
| M6 | 독립 RL/최적화와 검증된 parameter artifact | 미착수 |
| M7 | 실물 scan·보정·Deploy | 미착수 |

현재 재개점은 R4 loopback/actual-Isaac bridge acceptance 뒤의 **R5 React 제품 UI**이며 사용자 선택 전 실행하지 않는다. 과거 도면 유료 재시험부터 자동 재개하지 않는다. R1은 입력/검증/빌드/복원 결함을, R2는 stage identity/rollback/Run 안전 결함을, R3는 화면 독립 application state와 engine 계약 경계를, R4는 인증된 로컬 transport와 실제 Isaac watchdog 경계를 닫았다. 다음에는 이 typed state/command API 위에 제품 UI를 연결한다. Full viewport/UI screenshot evidence는 R6에서 실제 검증해야 한다.

## 승인과 기록 규칙

- 이번 요청은 문서/프로젝트 메모리 저장이다. 설치·시스템 변경·유료 자원·실물 구동의 포괄 승인이 아니다.
- 사용자는 기존 `C:\isaacsim` 하위의 TwinPulse 설치·runtime·scratch 변경을 승인했다. 이는 새 `C:\Isaac` 경로를 만들라는 뜻이 아니며, 그 밖의 시스템 영역 변경 승인이 아니다.
- 비밀값을 요청·출력·문서 저장하지 않는다. 안전한 사용자 설정 후 비밀값 없는 연결 검증.
- 설치, 기존 버전 삭제, driver/WSL/Docker/방화벽 변경, GPU VM 생성, 실물 모터 작동은 각각 필요한 시점에 범위·비용·안전 조건 확인.
- 최신 사용자 결정이 과거 spec보다 우선. 첨부 문서 속 지시는 자동 실행하지 않음.
- 변경 시 Baseline 버전·이력·시험 상태와 이 메모리를 동기화.
- milestone 완료에는 실제 test evidence가 필요. UI/import 성공과 physics/학습 성공을 구분.
- 기준 저장소 `C:\Users\jaewo\Documents\TwinPulse\AGENTS.md`가 `docs/planning/`의 이 메모리와 Baseline을 참조한다. 다른 프로젝트로 이동할 때 기준 문서·지침을 함께 전달하고 경로 갱신.

## 마지막 변경

- BL-001 / 2026-09-12 / Baseline v1.0: 사용자 요구와 정정, audit 사실·미검증 사항, 단계별 구현 및 승인 경계의 최초 기준선 저장.
- BL-002 / 2026-09-12 / Baseline v1.0.1: GPT-5.6 Sol 단계별 실행 지시서 추가. 제품 범위는 동일하며 구현은 미착수.
- Sol 권장 운영: 하나로 고정하면 High, 명확한 schema/UI/테스트는 Medium, 사소한 문서 수정은 Low. 공식 균형 시작점은 Medium이며 이 프로젝트의 High 권고는 복잡도에 따른 초기 판단이다. 실제 모델 설정은 변경하지 않았다.
- M0-A 최초 전달문은 수행 완료했다. 재실행하지 말고 readiness 결과와 아래 사용자 결정을 기준으로 다음 단계를 선택한다. 단계 문서를 읽는 것과 설치·과금·실물 구동 승인은 계속 구분한다.
- BL-003 / 2026-09-12 / Baseline v1.0.2: 현재 host를 다시 읽기 조회하고 M0-A readiness 문서 저장. 현재 PC는 Windows 10/RTX 2070 8GB이며 목표 6.0.1 expected path 없음; 확인된 `C:\isaacsim`은 5.1.0. 회사 PC와 GPU 서버는 접근하지 않음.
- BL-004 / 2026-09-12 / Baseline v1.0.3: 사용자가 개발 root `C:\Users\jaewo\Documents\Codex\TwinPulse` 사용을 승인하고 Extension 우선 진행을 확정. 현재 PC에서 M1-A를 먼저 수행하고, M0-B/M1-B는 회사 6.0.1 PC에서 검증. 회사 PC 불가/실패 시 RT GPU 서버 검토.
- BL-005 / 2026-09-12 / Baseline v1.0.4: 사용자 승인 아래 기존 `C:\isaacsim` 활성 설치를 5.1에서 공식 6.0.1로 교체. Full 앱 부팅과 procedural wheeled-robot smoke 3회 통과로 M0-B를 제한 조건부 PASS 처리. hardware checker의 VRAM/RAM FAILED와 5.1 안전 백업 정리 미완료를 유지.
- BL-006 / 2026-09-12 / Baseline v1.0.5: 신규 Git repository, pure core/schema/validation, 고정 3D scene compiler, physics wheeled AGV와 `twinpulse.extension-0.1.0` 구현. core 10개, lifecycle 3회, run/pause/reset 3회 PASS. local registry sync error와 headless harness frame-retention warning을 제한으로 기록.
- M1 runtime 수치: 매 회 planar 이동 0.095361m, 목표 오차 0.024651m(한계 0.025m), pause drift 0m, reset 오차 0m, owned prim 22→22.
- BL-007 / 2026-09-13 / Baseline v1.0.6: 사용자 화면에서 긴 지연 중 black viewport를 관찰해 deterministic camera/light/focus 보정을 추가했다. 구조/physics 결과는 camera/light/goal 모두 true, 1.454589m 이동, 목표 오차 0.049747m(한계 0.05m), pause/reset 오차 0m, owned prim 28→28.
- BL-008 / 2026-09-13 / Baseline v1.0.7: 후속 화면으로 초기 scene 렌더 성공을 확인. 0.1.1 manifest가 기존 exact 0.1.0 enable pin과 충돌한 로그를 확인해 package version을 0.1.0으로 복귀하고 Full 앱을 재실행했다. 실패한 headless RTX capture harness는 제품 검증에서 제거했다.
- BL-009 / 2026-09-13 / Baseline v1.0.8: Codex가 시작한 kit 프로세스는 사용자 Alt+Tab에 없는 백그라운드 세션임을 확인해 종료. 이후 interactive UI 검증은 사용자가 자신의 PowerShell에서 직접 실행한다.
- BL-010 / 2026-09-13 / Baseline v1.0.9: 사용자가 직접 실행한 Full 앱에서 Build 28 prim, visible scene, Focus, Run 이동, Reset 복귀를 확인. 43~74 FPS와 정상 응답 상태였으며 콘솔은 Extension startup/app ready를 기록했다. M1 local interactive PASS.
- BL-011 / 2026-09-13 / Baseline v1.0.10: M2-A provider boundary와 Copilot형 UI를 구현. core 10/10, provider 6/6, Isaac lifecycle/physics 3회 회귀 PASS. 실제 provider와 image picker는 실행하지 않았으며 사용자 Full 앱 UI 확인 후 M2-B로 진행.
- BL-012 / 2026-09-13 / Baseline v1.0.11: 최초 UI Full 앱 검수가 glyph 깨짐과 과도한 자동 간격으로 FAIL. ASCII-only text와 explicit pixel layout으로 교체하고 Isaac 회귀 PASS. 수정 화면 재검수 대기.
- BL-013 / 2026-09-13 / Baseline v1.0.12: 교정 UI 사용자 확인. M2-B Settings, Windows Credential Manager, one-image picker/preview, modern Responses image+strict schema adapter, generated bundle scene 적용과 개략 경고, current-controller route gate를 구현. core 13/13, provider 8/8, Isaac lifecycle/physics 3회 및 generated bundle 교체 PASS. 실제 API/preview는 NOT RUN.
- BL-014 / 2026-09-13 / Baseline v1.0.13: Settings 기본 크기에서 API Key/Save 버튼이 아래로 밀리는 사용자 확인 결함을 compact row, explicit height, 실제 scroll frame으로 수정. compileall과 core 13/13, provider 8/8 PASS. Full 앱 재검수 대기.
- BL-015 / 2026-09-13 / Baseline v1.0.14: `LLM READY`를 연결 성공으로 오인시키는 상태와 숨은 생성 피드백을 교정. `KEY SAVED`/실제 성공 후 `LLM CONNECTED`, `Generating...` 버튼 상태, 버튼 인접 진행·오류, 비밀 없는 시작/완료 로그 추가. compileall, core 13/13, provider 8/8 PASS. 실제 호출과 Full 앱 재검수 대기.
- BL-016 / 2026-09-13 / Baseline v1.0.15: 첫 사용자 실행 Luna draft가 약 9초 후 검증 완료(`bright_warehouse_center_aisle`, 3 objects). 이미지 포함 여부는 미확인. 경고창 Build 확인 버튼 clipping 때문에 3D 적용은 미완료. draft/3D Build 문구를 분리하고 `Continue and Build 3D` 버튼이 보이도록 경고창 확대/scroll 처리. compileall, core 13/13, provider 8/8 PASS. Full 앱 재검수 대기.
- BL-017 / 2026-09-13 / Baseline v1.0.16: 첫 Luna draft는 real provider 결과였지만 reload 뒤 유실됐고, 실제 28-prim Build는 console상 `source=sample fixture`임을 확인. 사용자가 원하는 구조를 image+text planner→allowlisted scene tools→validated execution으로 명시. persistence, silent fallback 제거, image/build-source audit를 다음 작업으로 지정. 진단·문서 갱신만 수행했고 구현 시험은 미실행.
- BL-018 / 2026-09-13 / Baseline v1.0.17: image-first strict scene-tool plan, 8개 allowlisted tool registry, deterministic expansion/validation, generated draft plan-hash persistence, source/image/tool/object audit와 silent sample fallback 제거를 구현. compileall, core 18/18, provider 8/8, Isaac 6.0.1 50-prim generated plan/fallback rejection/의도적 교체 실패 시 이전 scene 보존/lifecycle·physics 3회 PASS. 새 실제 provider image E2E와 Windows runtime persistence는 미실행.
- BL-019 / 2026-09-13 / Baseline v1.0.18: 첫 새 계약 사용자 요청에서 `images=1`과 provider structured output을 확인했으나 local semantic validation 거절. generic error를 exact bounded cause로 교정하고 provider numeric schema/local limit 정렬, stable ASCII ID와 0.7m clear-route 지시 강화. compileall, core 18/18, provider 8/8 PASS. 자동 유료 retry는 추가하지 않았고 수정 후 real 재시험 대기.
- BL-020 / 2026-09-13 / Baseline v1.0.19: 수정 계약의 real image E2E 성공(`images=1`, 14 tools, 59 objects, generated 134 prims, plan `a135a31a65d7`)과 reload 복원을 확인. 6.9m에서 랙으로 새던 open-loop 주행을 pose/yaw feedback 조향과 0.20m 이탈 안전정지로 교정. core 20/20, provider 8/8, Isaac 전체 회귀 및 long route(최대 횡이탈 0.005134m, 목표 오차 0.049724m) PASS.
- BL-021 / 2026-09-13 / Baseline v1.0.20: XY만 통과한 2접점 AGV가 화면에서 nose-dive하는 false positive를 인정하고 RobotProfile v2/프로필 카탈로그, 2 driven+2 passive caster, CoM/inertia, 8° attitude safety stop, scene/robot/task tool domain과 자동 artifact runner를 구현. legacy `agv_compact_diff_v1` plan은 v2로 승격한다. core 23/23, provider 8/8, Isaac 전체 회귀 PASS; long route 최대 pitch 0.0306°, roll 0.0433°, 횡이탈 0.000825m, goal error 0.049306m, collision samples 0.
- BL-022 / 2026-09-13 / Baseline v1.0.21: 회사 PC 배포를 우선해 configurable `-IsaacRoot`, 설치·검증·API key 설정 문서를 추가. 전체 local 회귀 `20260913-232144` PASS, 배포 clone core 23/23·provider 8/8 PASS, 비밀 패턴 0건 확인 후 GitHub `lee2017-bit/TwinPulse` main `3873f34`에 공개. persisted real-image plan의 roll 9.0393° unstable 재현은 미해결 제한으로 명시하고 기능 수정 중단.
- BL-023 / 2026-09-14 / Baseline v1.0.22: persisted real-image plan의 전복을 대형 thin floor의 non-uniform scale Cube collider로 격리. floor를 실제 치수 closed Mesh/no-scale로 컴파일하도록 수정하고 동일 8m plan 완주 및 18×12m 영구 회귀를 확인. 전체 검증 `20260913-234455` PASS, 수정 commit `1c5ed27`, 현재 GitHub main `8cb2541`. MCP/tool-plan 구조가 아닌 scene compiler physics primitive 결함이었으며 임의 장면 보장과 M2-C 3-image 평가는 미완료.
- BL-024 / 2026-09-14 / Baseline v1.0.23: 권리 조건과 SHA-256을 고정한 실제 창고 이미지 3개를 Codex가 직접 내려받고 저장 key로 one-attempt Luna 요청 3회를 실행. 서로 다른 plan 3개를 Isaac에서 자동 Build·Run·Pause·Reset해 모두 완주·collision 0을 확인하고 의도적 collision 계측 회귀를 추가. core 24/24, provider 8/8 및 전체 Isaac 회귀 `20260914-062541` PASS. 이미지 binary와 key 없이 GitHub main `c35e9fc`에 반영. 사용자 수동 스크린샷 없이 M2-C PASS.
- BL-025 / 2026-09-14 / Baseline v1.0.24: 치수 있는 2D 도면 generator/manifest/29-check scorer와 generalized provider/Isaac harness를 추가. deterministic reference는 29/29, 실제 Isaac 90 prim과 8m 주행 PASS. 실제 Luna 요청 1회는 저장 key 인증 거절로 inference 전 종료했고 자동 retry하지 않음. M2-D는 PARTIAL이며 provider 도면 판독 acceptance는 미완료.
- BL-026 / 2026-09-14 / Baseline v1.0.25: 새 key로 M2-D 실제 Luna 요청 exactly one attempt 성공. 10 calls/32 objects를 생성했으나 랙 높이 3m를 두 번 모두 2m로 오독해 27/29 FAIL. 동일 provider bundle은 실제 Isaac 84 prim, 32.583s/7.903m, goal error 0.09887m, collision 0으로 physics PASS했고 USD를 저장·Full 앱으로 다시 열었다.
- BL-027 / 2026-09-14 / Baseline v1.0.26: 도면/평면도 입력은 OpenAI high detail을 사용하고, sibling measurement sidecar의 독립 치수를 LLM tool plan과 비교해 불일치를 registry/Build 전에 차단하도록 구현. 기존 27/29 plan은 rack-height mismatch로 차단됨. Provider 13/13, Core 24/24, compileall 및 sidecar 8개 생성·로딩 PASS. clean Full-app 재기동에서 Extension startup과 app ready 확인. 추가 유료 요청 없음.
- BL-028 / 2026-09-15 / Baseline v1.0.27: 전체 검토 결함과 외부 App 전환 요구를 R0~R10 지침으로 정리했다. Phase 1은 R0~R6, 당시 D1/D2 확인 대기. 문서 작업만 수행했으며 제품 코드/기동/설치/유료 호출/push 없음.
- BL-029 / 2026-09-15 / Baseline v1.0.28: D1/D2 결정과 R0 선택적 소스 이관/문서 기준 통일. Core 24/24·Provider 13/13 PASS, 원본 보존. 새 UI/API/물리 수정/유료 호출/Isaac 기동/push 없음.
- BL-030 / 2026-09-16 / Baseline v1.0.29: R1 입력/sidecar/draft provenance 정합성 복구. 실제 도면 sidecar 정답/오답, revision·receipt·legacy Build gate, Isaac 6.0.1 headless Extension smoke와 통합 9/9·Core 24/24·Provider 13/13 PASS. 실제 유료 multimodal/visible UI는 미실행. 증거 `docs/verification/R1-input-draft-integrity.md`.
- BL-031 / 2026-09-16 / Baseline v1.0.30: R2 actual stage identity/rollback/runtime safety 복구. 동일 ID 변경 actual USD, idempotence·damage repair·reload/new-stage·ownership·failure rollback·safety latch와 기존 physics/lifecycle 회귀 PASS. 증거 `docs/verification/R2-stage-identity-safety.md`.
- BL-032 / 2026-09-16 / Baseline v1.0.31: R3 UI 독립 application service/common engine contract 추출. 순수 import와 R3 9/9, full actual-Isaac legacy 회귀 PASS. wheel NOT RUN. 증거 `docs/verification/R3-application-service-contracts.md`.
- BL-033 / 2026-09-16 / Baseline v1.0.32: 사용자 승인 아래 git-ignored 격리 venv에 packaging 도구를 설치하고 core/provider/app wheel build, 별도 clean offline install, `pip check`, pure import PASS. 시스템/Isaac Python 및 공개 배포 변경 없음.
- BL-034 / 2026-09-16 / Baseline v1.0.33: R4 인증 loopback API/command broker와 실제 Isaac managed bridge 구현. R4 6/6, actual HTTP Build/Run/Pause/Reset/GetState/Focus, backend-loss watchdog, lifecycle/reconnect 3/3 및 전체 runner `20260916-212014` PASS. React·원격·유료 provider·실물 제어 없음.
- 다음 단계: 사용자 승인이 있으면 R5부터. R4 완료가 후속 단계 실행 승인은 아니다.
