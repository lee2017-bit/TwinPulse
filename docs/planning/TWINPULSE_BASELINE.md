# TwinPulse — 구현 기준 지침서

- 문서 버전: **Baseline v1.0.28**
- 기준일: **2026-09-15 (KST)**
- 상태: **기존 M0-A/B, M1-A/B, M2-A/B/C의 제한된 PASS 기록 보존; M2-D PARTIAL; App 전환 R0 인수인계 완료, R1~R10 미착수**. M2-D 실제 provider는 10 calls/32 objects를 생성했으나 랙 높이 3.0m를 두 행 모두 2.0m로 오독해 기존 scorer 27/29 FAIL이었다. 동일 bundle은 실제 Isaac 84 prim/8m 주행으로 physics PASS했다. scorer 검사 범위 밖의 정확도나 임의 장면의 안정성을 보장하지 않는다. 아래 최신 검토 보정과 App 전환 지침을 먼저 읽는다.
- 목적: 이후 단계별 구현, 검증, 의사결정 및 변경 관리의 기준 문서.
- 프로젝트 메모리: [TWINPULSE_PROJECT_MEMORY.md](TWINPULSE_PROJECT_MEMORY.md)
- 단계별 실행 지시서: [TWINPULSE_SOL_IMPLEMENTATION_PLAYBOOK.md](TWINPULSE_SOL_IMPLEMENTATION_PLAYBOOK.md)
- 최신 단계 기록: [TWINPULSE_M2D_IMPLEMENTATION.md](TWINPULSE_M2D_IMPLEMENTATION.md)
- 최신 검토·실행 계획: [App 전환 및 정합성 복구 지침](TWINPULSE_APP_MIGRATION_PLAYBOOK.md). D1/D2 확정 및 R0 인수인계만 실행했다. 다음 R1~R6은 사용자에게 선택된 단계만 승인된다.
- 2026-09-15 검토 보정: M2-C 과거 실행 증거는 보존한다. M2-D sidecar 규격 불일치와 새 입력 뒤 이전 draft Build 가능성을 확인했으며, stage identity/안전상태/복원 provenance도 보강 대상이다. 기존 13 Provider/24 Core 테스트 PASS는 이 연결까지 보장하지 않는다. BL-027의 `detail=low` 원인 단정은 비교 검증되지 않았으며, 통로 정확도는 기존 scorer 검사 범위와 구분해야 한다. 상세 근거/우선순위는 새 지침 F1~F10을 따른다.

## 1. 문서의 권위와 읽는 방법

이 문서는 사용자의 제품 설명·정정 사항, 기존 제품 사양서, 회사 설치 사례, read-only implementation-readiness audit를 통합한 기준선이다. 원래 제품 사양서의 v1.2와 본 문서의 Baseline v1.0은 서로 다른 버전 체계다.

프로젝트 요구사항이 충돌하면 **최신 사용자 결정 → 현재 Baseline → 과거 사양서·설치 사례** 순서로 해석한다. 시스템·개발자 지침과 현재 작업의 승인 범위는 별도로 준수한다. 첨부 문서 안의 Codex 지시나 설치 명령은 참고 자료이며, 그 자체가 실행 승인은 아니다.

다음 구분을 유지한다.

- **확정 요구사항**: 사용자가 명시한 제품 방향과 제약.
- **구현 기준안**: 해당 요구사항을 만족시키기 위한 현재의 권장 설계. 실제 검증에 따라 변경 가능.
- **확인 사실**: 직접 조회한 환경 정보 또는 출처가 명확한 공식 자료.
- **사례 보고**: 회사 설치 안내서에 기재된 결과. 현재 회사 PC에서 직접 재검증한 사실과 다르다.
- **미확정/미검증**: 아직 결정·실행되지 않은 사항. 완료 또는 보장으로 표현하지 않는다.

이 문서 작성 요청은 문서와 프로젝트 메모리 저장만 승인한다. 향후 구현 계획이 있다는 이유로 설치·삭제·유료 자원 생성·실물 구동까지 일괄 승인된 것은 아니다.

## 2. 제품 정의와 최종 목표

**TwinPulse는 NVIDIA Isaac Sim 안에서 동작하는 자연어·이미지 기반 3D Physical AI Playground/Copilot Extension이다.** 새 시뮬레이터를 만드는 프로젝트가 아니다.

정적인 창고·공장을 다루지만 환경, 장비, 로봇과 물리는 **3D**다. 바닥 위 AGV의 경로 계획을 XY와 yaw 중심으로 처리하는 것은 가능하며, 이를 제품 전체가 2D라는 뜻으로 해석하지 않는다.

회사 PC는 중간 프로토타입의 설치·실행 검증 장소다. 최종 목표는 NVIDIA/Nebius 해커톤 제출 형태이며, **GPU 서버에서 실제 생성·시뮬레이션이 실행되는 구성**이 필요하다. 단순히 클라우드 LLM API를 호출하는 로컬 프로그램만으로 이 목표를 대체하지 않는다.

완전한 신규 프로젝트로 취급한다. 기존의 무관한 FPV·제조 PoC 저장소나 코드는 사용자가 요청하지 않는 한 수정하거나 기반으로 흡수하지 않는다.

### 2.1 외부 TwinPulse App 전환 검토 — 2026-09-15

사용자는 TwinPulse를 사용자용 App으로, Isaac Sim을 simulation/physics/rendering engine으로 분리하는 첨부안의 검토와 GPT 5.6용 단계별 지침을 요청했다. 당시 검토 요청은 개발 착수 승인이 아니었고, 후속 사용자 요청에서 **R0만** 승인했다.

권장 구조는 React 제품 UI → 별도 Python application/backend → typed local bridge → 기존 Isaac Extension adapter/compiler/runtime이다. 기존 Extension과 검증된 물리 코드는 재사용하며, 외부 UI 대체 검증 전에는 legacy omni.ui를 삭제하지 않는다. 기존 본문의 “Extension 내부 제품 UI”는 현재 구현/이전 기준이고 새 목표 UI 위치는 이번 계획에서 변경 검토 중이다.

첫 범위는 사용자 결정으로 **로컬 React 웹 UI + 별도 Isaac 3D 창**이며, GitHub 연결 clone `C:\Users\jaewo\Documents\TwinPulse`가 기준 개발 root다. 새 폴더는 만들지 않았다. 기존 `Codex\TwinPulse` 개발본은 삭제·이동하지 않고 M2-D 관련 소스만 비파괴적으로 이관했다. R0에서는 시스템 설치·Isaac 기동·GitHub push를 하지 않았다. 첫 전환에 Tauri/native viewport embed/ROS2/Lab/최적화/실물 Deploy를 포함하지 않는다. 실물 2WD와 GPU 서버 최종 목표는 유지한다.

## 3. 1차 프로토타입 — 실물 AGV 없이 가능한 범위

### 3.1 핵심 사용자 흐름

1. 사용자가 일반적인 창고·공장 내부 이미지와 자연어 설명을 입력한다.
2. 시스템이 지원하는 장비 템플릿과 형상을 사용하여 개략적인 **3D 환경**을 생성한다.
3. 미리 정의된 AGV를 배치하고 간단한 이동·순찰 작업을 지정한다.
4. 실행 시 개략 모델임을 알리는 경고를 표시한다.
5. 사용자가 시뮬레이션을 실행·일시정지·초기화하고 이동 결과를 관찰한다.
6. 자연어로 배치나 작업을 수정하고, 저장·재열기·Replay로 이어간다.

첫 공개 가능한 vertical slice에는 **이미지 입력과 실제 3D 시뮬레이션을 모두 포함**한다. 내부 개발 중 고정 장면이나 텍스트만 사용하는 중간 테스트는 허용하지만 이를 이미지 기반 첫 프로토타입의 완성으로 선언하지 않는다.

### 3.2 생성의 의미와 신뢰성 안내

일반 사진만으로 실제 치수·가려진 공간·정확한 재질을 복원한다고 약속하지 않는다. 첫 버전의 가치는 “창고 사진을 대략 넣고 물리적인 시험을 쉽게 시작한다”는 데 있다.

사용자는 실행 시 경고창 하나로 이 한계를 알리는 UX를 원한다. 각 추정 치수마다 승인을 받는 절차를 기본 UX로 추가하지 않는다. 예시 문구:

> 일반 사진을 바탕으로 생성한 개략적인 3D 시험 환경입니다. 실제 치수와 배치를 보장하지 않습니다. 정확한 환경이 필요하면 치수가 있는 탑다운 도면이나 스캔 결과를 사용하세요.

이 경고는 데이터 검증을 생략한다는 뜻이 아니다. 내부적으로 단위·범위·객체 개수·충돌체·AGV 생성 위치·유효한 경로 시작점 등을 검사한다. 이후 실물 Deploy 승인과 비상정지는 별개의 안전 절차다.

### 3.3 초기 지원 범위

- 바닥, 벽, 랙, 박스, 간단한 장비 외형 등 파라미터화된 primitive/curated asset 조합.
- 공장 장비는 우선 시각 형상과 정적 collider 중심. 임의 장비의 실제 작동 원리까지 자동 복원하지 않는다.
- AGV는 치수·바퀴·구동 방식·센서 구성을 정의한 RobotProfile을 사용한다.
- `2W`는 두 개의 구동륜을 뜻하며 총 접지점 수를 뜻하지 않는다. 현재 기본 RobotProfile은 differential 2WD와 전·후 passive ball caster를 사용한다. 실제 하드웨어가 4WD이면 planner를 바꾸지 않고 별도 profile/adapter를 선택한다.
- “랙을 옮겨줘”, “A와 B 사이를 순찰해줘” 같은 지원된 구조적 편집과 작업.
- 기본 경로 표시, 충돌·이동 시간·거리 측정, 저장 및 Replay.
- 요청 취소·실패 표시·재시도, 잘못된 모델 출력의 안전한 거부.

AGV 미선택 시 기본 모델 사용 여부, 로봇 없는 장면만 생성하는 UI의 세부 동작은 아직 확정하지 않았다. 첫 테스트용 AGV 모델과 입력 이미지 fixture는 구현 초기에 선정한다.

### 3.4 첫 버전에서 선행 조건으로 삼지 않을 것

실물 AGV 구매, 전체 Isaac Lab 설치, ROS2/WSL/Docker 설치, 임의 사진의 정밀 3D 복원, 범용 SLAM 자체 개발, 완전한 디지털 트윈, 임의 기계 동작 생성은 첫 Playground 완성의 선행 조건이 아니다.

## 4. 최종 실물 연동 흐름

1. 사용자의 실제 운용 환경 이미지·자연어·동영상을 입력한다.
2. predefined AGV를 선택하고 반영하여 1차 3D 환경과 AGV를 만든다.
3. 실물 AGV를 연결하고 환경을 스캔한다.
4. 스캔 결과를 기반으로 좌표계를 정합하고 장애물 위치를 수정하여 시뮬레이션 환경을 갱신한다.
5. 시뮬레이션에서 점수 기반 강화학습/최적화를 수행한다.
6. 선택된 최종 파라미터·로직·동선 산출물을 검증한다.
7. 실제 AGV에 Deploy하고 실제 주행 결과를 확인한다.

실물 트랙의 현재 아이디어는 약 2m × 2m 바닥판, 약 0.5m 벽, 내부 장애물이다. **확정 도면·제작 치수는 아니다.** 최종 AGV 크기·회전 반경·센서 최소 거리·제동 거리와 함께 설계한다.

### 4.1 스캔과 보정

- 1차 초점은 좌표계 정합과 장애물 위치 수정이다.
- “전체 Scan 한 번”은 가려진 영역까지 한 위치에서 관측한다는 뜻이 아니다. 필요한 시점을 이동하며 확보하는 mapping/coverage 과정이 필요하다.
- 기존 ROS2 mapping 도구 활용을 우선 검토한다. 제한된 트랙의 기존 SLAM 활용과 범용 3D SLAM 자체 개발은 구분한다.
- 2D LiDAR는 설치 높이의 단면을 관측한다. 알려진 벽 높이를 적용해 3D로 만들 수 있지만, 임의 장비의 높이·상부 형상을 측정했다고 주장하지 않는다.
- 높이·상부 장애물 복원이 실제 요구사항이 되면 depth/3D 센서 도입을 별도 판단한다.
- 바퀴 모델 자동 보정은 초기 필수 기능이 아니다. predefined 모델로 시작하고 직진·회전 오차를 측정한 뒤 필요할 때 보정한다. 동일 기종이라도 하중·타이어·바닥에 따른 오차는 가능하다.

실물 도착 전에는 가상 LiDAR, 합성 지도, 모의 telemetry로 정합·장애물 갱신 파이프라인을 검증할 수 있다.

### 4.2 AGV 구매 검토용 최소 인터페이스·센서 기준안

- 제어 가능한 구동부, 바퀴 encoder 기반 odometry, 실제 치수·wheelbase·wheel radius 정보.
- 제한된 실내 트랙 mapping/navigation에는 360° 2D LiDAR를 우선 검토.
- IMU는 회전·상태 추정 보완용으로 권장하되 필수성은 플랫폼 테스트 후 결정.
- ROS2에서 odometry, scan, TF 및 속도 명령을 연동할 수 있는 driver/interface.
- 비상정지, 통신 끊김 시 정지, 속도·가속도 상한. 센서만으로 안전 인증을 대체하지 않는다.
- Nav2를 실행할 Linux 컴퓨터는 탑재형 또는 외부 호스트로 구성 가능. ESP32 같은 MCU만으로 전체 Nav2 실행을 전제하지 않는다.

RPLIDAR C1은 저가 센서 후보로 조사되었으나 구매 결정은 아니다. 실제 공급가·드라이버의 Jazzy 동작·시야·최소 거리·장착 가능성을 구매 전에 재확인한다. AGV 총예산은 미정이며, 센서 단품 가격을 완제품 AGV 가격처럼 제시하지 않는다. [S11]

2m 트랙에 임의의 큰 clearance 수치를 고정하지 않는다. 로봇 폭 0.21m에 좌우 각각 0.5m를 더하면 1.21m 통로가 필요하므로 실제 footprint와 측정 오차·제동 여유로 결정한다.

## 5. 주행 최적화와 강화학습

### 5.1 사용자가 원하는 결과

정적 장애물을 피하면서 거리와 시간 낭비를 줄이고, 충돌 없이 더 부드럽게 이동하는 것이다. 사용자가 생각한 초기 배포 대상은 **ROS2 navigation logic의 parameter**다.

Nav2의 기존 smoother/controller도 곡선 경로를 만들 수 있다. 잘못 설정된 수평·수직 경로를 비교 대상으로 만들어 개선을 과장하지 않는다. **적절히 설정된 비학습 Nav2 baseline**과 비교한다. MPPI와 constrained smoother는 검토 대상이지 확정된 알고리즘 선택은 아니다. [S10]

### 5.2 구현 기준안

- 동일한 Nav2 controller/version을 시뮬레이션과 실제 환경에서 가능한 한 일치시킨다.
- 각 rollout/episode에 제한된 navigation parameter를 선택하고 주행 결과로 평가하는 구조를 우선 검토한다.
- 후보 파라미터: 경로·장애물 비용 가중치, smoothing 관련 값, 허용 범위 안의 속도·회전·가속도 관련 값.
- 하드웨어 안전 한계는 학습이 완화할 수 없는 별도 제약으로 둔다.
- 최종 RL 목표를 유지하되, 단순 탐색/비학습 최적화와 공정하게 비교한다. 일반 parameter search를 RL이라고 부르지 않는다.
- Isaac Lab의 PPO 예제를 실행하는 것만으로 Nav2 YAML이 자동 산출되는 것은 아니다. 파라미터 공간·관측·보상·episode·artifact 변환을 연결하는 adapter가 필요하다.
- 외부 ROS2/Nav2 프로세스가 병목일 수 있으므로 대규모 Isaac Lab 병렬화 성능을 미리 보장하지 않는다.

### 5.3 평가와 산출물

성공률, 충돌, 최소 여유 거리, 주행 시간, 이동 거리, 회전·가속도·jerk 등의 부드러움 지표를 기록한다. 정지한 채 충돌을 피하는 보상 편법을 막기 위해 도착 여부와 제한 시간을 함께 평가한다.

안전 제약과 성능 보상을 분리하고, 학습에 사용하지 않은 배치/seed에서도 평가한다. 마찰·센서 잡음·지연 변화에 대한 검증 범위를 점진적으로 추가한다.

배포 산출물에는 최소한 navigation parameters, RobotProfile 버전, 환경/map revision, controller 버전, 평가 결과, 생성 실행 ID를 묶는다. 개선율·허용 오차의 수치 목표는 baseline 실측 후 결정한다.

## 6. 실행 모드와 프로세스 경계

| 모드 | 상태/pose의 기준 | 주요 동작 | 실물 구동 |
|---|---|---|---|
| Isaac Simulation | Isaac physics | 가상 환경 생성·실행·평가 | 없음 |
| Replay | 기록된 시간축과 telemetry | 과거 실행 재생·비교 | 없음 |
| Live | 실물 telemetry | 실물 상태를 3D 장면에 반영 | 관측 모드 자체는 구동하지 않음 |
| Deploy | 실물의 로컬 navigation/control | 승인된 mission/parameter 적용 후 관측 | 별도 승인·안전 조건 필요 |

모드마다 pose를 쓰는 주체는 하나로 관리한다. Replay나 Live 중 시뮬레이터 controller가 같은 실물 표현의 pose를 동시에 덮어쓰지 않는다. sim time과 wall time, namespace와 좌표계 변환을 명시한다.

### 6.1 Extension 안에서 수행

UI, 입력 수집, 비동기 LLM 요청, schema 검증, 허용된 scene operation, 3D scene compiler, 시뮬레이션 제어, 실행 상태 표시를 담당한다. LLM 응답을 임의 Python/셸로 실행하지 않는다.

LLM 대기와 장기 작업이 Kit UI thread를 막지 않도록 한다. 생성 취소와 실패 시 기존 장면 보존 정책을 테스트한다. Extension unload 시 callback·subscription·task를 정리한다.

#### 6.1.1 Multimodal tool orchestration 목표

사용자가 확정한 목표 동작은 이미지와 자연어를 LLM이 분석한 뒤, 미리 구현하고 허용 목록에 등록한 장면 생성·검증·시뮬레이션 도구를 선택해 호출하는 Copilot형 orchestration이다. 현재의 `LLM → 단일 SpecBundle → monolithic primitive compiler`는 provider·schema·안전 경계 검증용 중간 구현이며 최종 interaction model로 간주하지 않는다.

- planner 입력: 이미지, 자연어 제약, 현재 장면 상태, 사용 가능한 tool schema.
- 허용 tool 예: floor/aisle/rack-row/rack-bay/pallet/box-cluster/predefined-AGV/camera-light 생성, clearance·collision 검사, scene build, simulation control.
- orchestrator: tool 이름·인자·순서·상한을 검증한 뒤 deterministic implementation만 실행하고 결과를 다시 planner/UI에 전달한다.
- scene authoring, RobotProfile 선택, navigation task intent, simulation episode/runtime을 별도 domain으로 유지한다. LLM은 프로필 ID와 고수준 task만 선택하며 물리 파라미터나 실시간 wheel command를 만들지 않는다.
- LLM이 임의 Python·셸·USD 코드를 직접 실행하게 하지 않는다.
- MCP는 외부 process/service와 도구를 공유할 때 사용할 수 있는 transport 선택지다. Isaac Extension 내부 구현은 typed tool registry로 시작하고 필요 시 같은 계약을 MCP로 노출할 수 있다. 제품 acceptance는 특정 transport 명칭보다 허용된 도구 선택·검증·실행·감사 가능성으로 판단한다.
- 실시간 simulation/physical motor loop와 watchdog은 MCP/LLM 호출에서 분리한다. 외부 planner·evaluation worker·artifact service에 동일 계약을 노출할 때만 MCP adapter를 둔다.
- generated draft/tool plan은 Extension reload 후에도 복원 가능하게 비밀값을 제외하고 프로젝트 runtime state에 저장한다. 생성되지 않은 상태에서 generated-build가 sample fixture로 조용히 fallback하지 않게 하고, sample은 명시적인 별도 action으로만 실행한다.
- 비밀 없는 audit에 request ID, model, image count/attachment 여부, plan/draft hash, 생성 시각, 실제 build source를 남겨 이미지 사용과 결과 출처를 검증한다.

### 6.2 별도 프로세스에서 수행

Isaac Lab/RL 학습, 장기 최적화, 필요 시 ROS2/Nav2 실행은 Extension과 분리한다. 학습 worker의 종료·오류가 UI 전체를 종료시키지 않게 한다. 서로 다른 Python/torch 환경을 무리하게 하나로 합치지 않는다.

실물의 빠른 제어 루프와 watchdog은 로봇 측/현장 컴퓨터에서 실행한다. GPU 클라우드가 인터넷을 통해 모터 제어 주기를 직접 책임지는 구조를 기본으로 삼지 않는다.

## 7. 권장 저장소와 데이터 계약

아래는 **아직 생성하지 않은 권장 구조**다. 첫 구현에서는 필요한 부분부터 만들고 불필요한 서비스 분할은 피한다.

```text
twinpulse/
  extensions/twinpulse.extension/   # Kit UI와 lifecycle
  packages/twinpulse_core/          # schema, validation, provider interface
  packages/twinpulse_isaac/         # scene compiler, simulation/robot adapter
  workers/optimization/            # 별도 학습·평가 runner
  ros2/                            # bridge, Nav2 설정과 launch
  assets/                          # 허용된 템플릿·모델·asset manifest
  deployment/                      # 회사 Windows / GPU Linux 실행 설정
  tests/                           # schema, scene, lifecycle, E2E fixture
  docs/                            # 향후 이전할 Baseline와 결정 이력
```

초기 데이터 계약 후보는 SceneSpec, RobotProfile, TaskSpec이다. 뒤이어 OptimizationSpec, CalibrationResult 및 배포 bundle을 도입한다. 필드의 정확한 명세는 구현 단계에서 정한다.

- SI 단위, Z-up 및 map/odom/base_link/sensor frame 관계를 명시한다.
- 객체마다 안정적인 ID를 사용해 자연어 수정 대상을 추적한다.
- scene compiler는 같은 입력 반복 적용 시 불필요한 중복 prim을 만들지 않는다.
- 원본 입력, 추정된 치수, 스캔으로 보정된 값과 revision을 구분한다.
- API key, token, 인증 헤더와 실제 회사 자격증명은 문서·로그·저장소에 저장하지 않는다.
- 외부 asset은 라이선스·출처와 재배포 가능 여부를 확인한다.

## 8. LLM 및 Nebius 실행 방안

### 8.1 사내 LLM

사용자가 말한 a.biz는 **사내 LLM Base URL에 사용되는 이름에 대한 설명**이다. 특정 제품인 A.dot Biz로 단정하지 않는다. SKT 계열사가 제공하며, 모델 이름이 공개 모델명과 다를 수 있다.

Base URL, 인증 방식, model ID, 이미지 입력, structured output/tool 지원 여부는 미확정이다. 공개 OpenAI endpoint나 특정 SDK 프로토콜과 같다고 가정하지 않는다. 사용자는 이 프로젝트 입력 데이터의 외부 전송이 가능하다고 밝혔다. 공개 저장소나 외부 발표에 포함할 권리는 별도로 확인한다.

provider adapter는 endpoint/model/capability를 분리한다. vision 미지원이면 지원되는 다른 provider 또는 사용자 설명 보완을 명시적으로 선택한다. 이미지 처리에 실패한 것을 성공으로 표시하거나 이미지 기능을 조용히 제거하지 않는다.

### 8.2 Token Factory와 AI Cloud 구분

| 구분 | 역할 | 확인할 사항 |
|---|---|---|
| Nebius Token Factory | LLM/VLM 추론 API | 실제 model ID, vision 지원, 인증, 요청 비용 |
| Nebius AI Cloud | GPU VM에서 full Isaac Sim/worker 실행 | RT 지원 GPU, region/quota, 드라이버, 스토리지, 네트워크, 예산 |

Token Factory 크레딧은 GPU VM 사용 가능 여부를 증명하지 않는다. 프로모션·계정 quota·실시간 GPU 재고·실제 결제 가능 범위는 확인하지 않았다. 특정 Nemotron 모델이 이미지와 구조화 출력을 동시에 지원한다고 단정하지 않는다. [S12, S13]

### 8.3 GPU 선택 기준

full Isaac Sim은 RTX rendering 지원 여부가 중요하다. 조사한 세 후보 중 **L40S를 우선 검토**한다. H100/H200을 VRAM이 많다는 이유만으로 full Isaac Sim 후보로 선택하지 않는다. 공식 요구사항은 RT Core 없는 A100/H100을 지원하지 않는다고 명시한다. H200 배제는 같은 RT 요구조건에 따른 판단이며, 별도 학습 workload 활용 가능성과는 다른 문제다. [S1, S13]

L40S가 없으면 RT 지원 RTX 계열 GPU/다른 가용 region을 검토한다. 서버에서 동일 Extension을 실행하고 WebRTC 등 원격 화면으로 이용하는 방향을 기본안으로 둔다. 실제 포트·방화벽·인증 설계는 배포 시 검증·승인한다.

## 9. 설치·API·환경 조사 기준선

아래는 **2026-09-12 조사 snapshot**이다. 새 회사 PC나 서버에서 그대로 확인된 사실로 재사용하지 말고 M0에서 갱신한다.

### 9.1 현재 접근한 PC — 직접 확인

| 항목 | 조사 결과 |
|---|---|
| OS | Windows 10 Pro 22H2, build 19045.6466 |
| CPU | Intel Core i7-10750H |
| GPU | RTX 2070 Max-Q, VRAM 8192 MiB |
| GPU driver | 592.82 |
| RAM | 약 15.77 GiB, 당시 여유 약 6.33 GiB |
| C: 디스크 | 약 470.4 GiB. 6.0.1 추출 후 확인 시 여유 약 47.3 GiB; cache와 백업 상태에 따라 변동 |
| Isaac 위치 | C:\isaacsim |
| Isaac VERSION | 6.0.1-rc.7+release.42383.32955d8d.gl |
| Kit launcher | 110.1.2+production.326809.f9bf0dda.gl |
| Isaac 내장 Python | C:\isaacsim\kit\python\python.exe, 3.12.13 |
| 별도 일반 Python | 사용자 AppData의 Python312, 3.12.10 |
| 6.0.1 설치 | 공식 Windows standalone ZIP 10,600,096,696 bytes, MD5 `c7fa3a830b251f10305cd7883039df9b` 검증 후 배치 |
| compatibility checker | driver/GPU/OS supported, VRAM 8.59GB < 10GB 및 RAM 16.94GB < 32GB로 최종 `FAILED` |
| runtime smoke | Full 앱 부팅 PASS. procedural differential-drive physics 3회 PASS |
| 이전 5.1 | 활성 root에서는 제거됨. 작업 폴더의 약 21.85GiB 안전 백업은 삭제 정책 차단으로 보존 중 |
| Isaac Lab | 확인한 예상 경로·관련 metadata에서는 찾지 못함 |
| ROS2 / Pixi | PATH에서 실행 파일 미발견, 관련 환경변수 및 확인한 workspace 경로 없음 |
| ROS2 bridge | 6.0.1 설치본에 관련 Extension이 포함돼 있으나 Jazzy 송수신 실행 검증은 아직 하지 않음 |
| Docker | CLI 29.5.2 존재. desktop-linux engine 연결은 확인되지 않음 |
| WSL | 조회가 E_ACCESSDENIED로 실패하여 설치·동작 상태 미확인 |
| 새 프로젝트 | 현재 작업 폴더는 제품 코드/Git 저장소 없는 상태에서 시작 |

6.0.1 bundled checker와 Full 앱을 직접 실행했다. Full 앱은 PhysX·wheeled robot Extension을 로드한 뒤 2분 이상 유지됐고, procedural fixture는 CPU physics/MinimalRendering 60Hz에서 중력·접촉·직진·회전·pause/resume/reset을 3회 통과했다. 매 회 직진 0.078613m, 회전 0.692385rad, pause drift 0m, reset 위치·yaw 오차 0이었다. 최신 smoke 로그에서 PhysX/CUDA fatal 또는 non-uniform scale 오류가 없었다. 자세한 실행 근거는 M0-B 보고서를 따른다.

이 PC는 공식 권장 구성과 bundled checker의 VRAM/RAM 최소치에 미달한다. 최소 CPU physics 성공을 복잡한 TwinPulse scene, RTX rendering 또는 최종 서버 적합성으로 확대 해석하지 않는다. 일반 Python 3.12와 Isaac bundled Python을 계속 분리한다. 별도 제조/FPV 관련 파일은 이 프로젝트 범위 밖이다. [S1]

### 9.2 회사 설치 안내서 — 문서상 사례

- Isaac Sim: D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64
- Isaac Lab: D:\IsaacLab, _isaac_sim 연결 사용.
- 문서상 Python 3.12.13, torch 2.10+cu128, torchvision 0.25+cu128, RSL-RL 5.0.1, Warp 1.13.
- 문서상 GPU RTX 3500 Ada 약 12GB, driver 580.92. 해당 회사 PC의 OS/RAM 등은 직접 재조회하지 않았다.
- 로컬 assets: D:\isaacsim_assets\Assets\Isaac\6.0
- wheel 모음: D:\isaacsim_assets\wheels_correct\wheels_correct, 문서상 123개 약 2.9GB.
- import, CUDA 인식, Kit 화면과 로컬 Franka USD 로딩의 성공 사례가 있다.
- 동시에 PhysX CUDA error 700, Warp 경고, articulation root 문제도 기록되어 있다.

따라서 이 안내서는 유용한 재설치 사례이지 **전체 physics·학습의 정상 완료 증명은 아니다**. 회사 GPU도 공식 최소 VRAM보다 작으므로 가벼운 scene 실측이 필요하다. GPU 구매를 바로 결론내리지 말고 오류와 실제 workload를 먼저 확인한다.

wheel 모음만으로 재현 가능한 dependency lock이 완성되지 않는다. 패키지 목록·hash·설치 결과·dependency check·runtime 시험이 필요하다. Windows wheel을 Linux 서버에 재사용하지 않는다. 첫 Extension에 전체 Lab 의존성이나 전체 asset pack이 반드시 필요한 것은 아니다.

안내서의 PythonServer(loopback 127.0.0.1:8226)는 개발 도구 사례다. 이를 외부 LLM의 임의 코드 실행 endpoint 또는 WAN 공개 서비스로 제품화하지 않는다.

### 9.3 목표 버전과 API 기준

목표는 Isaac Sim **6.0.1**, 공식 release notes의 Kit **110.1.2**, Python **3.12 계열**이다. 회사 안내서의 Python patch version과 실제 설치 build/hash는 별도로 재확인해야 한다. [S2]

공식 extension template는 Isaac Sim 소스 저장소의 template workflow를 기준으로 확인했다. standalone 폴더에 소스 저장소용 repo.bat가 있다고 가정하지 않는다. 6.0.0 계열 template 문서를 참고했으므로 실제 6.0.1 checkout/runtime에서 생성 경로를 다시 확인한다. [S3]

API 검토 대상:

- omni.ext.IExt: Extension lifecycle.
- omni.ui, omni.usd: UI와 stage 접근.
- pxr.UsdGeom, pxr.UsdPhysics: 형상·물리 schema.
- isaacsim.core.simulation_manager.SimulationManager.
- isaacsim.core.experimental.*: 필요한 항목의 안정성·버전별 API 확인 후 사용.
- isaacsim.robot.wheeled_robots: 바퀴 로봇 제어 관련 경로 확인.
- isaacsim.simulation_app.SimulationApp: 별도 실행 프로그램용.

모듈 경로를 조사했다는 사실과 실제 대상 runtime의 import/행동 검증은 다르다. 오래된 omni.isaac 예제를 무검증 복사하지 않고 6.0.1 deprecation을 확인한다. [S2, S4]

### 9.4 Isaac Lab 호환성

검토 기준 tag는 **v3.0.0-beta2.patch1**이다. 해당 source의 setup metadata는 Python >=3.12, Isaac Sim extra 6.0.1.0, torch >=2.10, Warp 1.13 계열을 명시한다. RL package의 RSL-RL 5.0.1 등도 확인 대상에 포함한다. 정확한 사용 commit/hash는 아직 고정하지 않았다. [S5]

이 tag의 호환성 근거는 첫 Playground에 Lab 설치가 필수라는 뜻이 아니다. M6 진입 전 별도 worker 환경을 구성하고 해당 tag/commit·dependencies·GPU·실행 결과를 고정한다.

### 9.5 ROS2 Jazzy / Pixi / RMW

Windows에서는 공식 Windows 11/Jazzy/Pixi 경로를 우선 검토하되, Linux GPU 서버와 현장 ROS2 host 구성도 분리해서 설계한다. WSL을 무조건 설치하거나 기존 설정을 변경하지 않는다. 일부 최신 공식 경로에서 WSL이 deprecated/비지원된다는 점과 모든 ROS2 WSL 실행이 불가능하다는 주장은 구분한다. [S6, S7]

조사 당시 IsaacSim-ros_workspaces main의 Jazzy pixi.toml은 rmw_zenoh_cpp, pip isaacsim 6.0.1.0, torch 2.11 등을 포함했다. 회사의 standalone/torch 2.10 사례와 같은 환경이 아니다. moving main을 따라 설치하지 말고 **standalone bridge 방식 또는 Pixi 관리 runtime 중 전략을 선택하고 commit/lock을 고정**한다. [S8]

현재 6.0.1에 ROS2 관련 Extension이 포함돼 있다는 사실은 Jazzy bridge의 검증 결과가 아니다. publisher/subscriber, RMW 조합, namespace/domain, TF·clock·odom·scan, 목표 명령을 실제 송수신해야 bridge 가능성을 통과로 판정한다.

## 10. 단계별 구현과 Acceptance Test

현재 상태는 Baseline, **M0-A/B**, **M1-A/B**, **M2-A/B/C**까지 완료했고 **M2-D 치수 도면 시험은 PARTIAL**이다. 개발 root `C:\Users\jaewo\Documents\Codex\TwinPulse`의 `twinpulse.extension-0.1.0`은 prompt-first Copilot UI, persistent provider 설정, 안전한 key 저장, 단일 이미지 preview, image-first strict scene-tool plan, allowlisted local execution, generated draft persistence/source audit와 자동 episode 계측을 포함한다. M2-D 실제 Luna는 10 calls/32 objects를 생성했고 실제 Isaac 84 prim/8m 무충돌 주행까지 성공했지만, 이미지의 랙 높이 3.0m를 2.0m로 두 번 오독해 정밀 scorer는 27/29 FAIL이다. 장거리 주행은 현재 pose/yaw를 매 physics step 읽는 폐루프 조향과 통로 이탈 안전정지를 사용한다. 내장 hardware checker의 VRAM/RAM 실패와 사진 기반 치수의 개략성은 유지된다.

| 단계 | 산출물과 완료 기준 | Acceptance test |
|---|---|---|
| M0 — 실행 환경 고정 | 회사 또는 GPU 서버의 대상 runtime inventory | Isaac/Kit/Python/GPU/driver 기록. 기본 physics·단일 AGV 실행/정지/reset. PhysX/CUDA 오류 없이 관찰 구간 완료. 정확한 구간·scene 규모는 첫 실행 때 기록 |
| M1 — Extension 뼈대 | 로딩 가능한 Extension + 보이는 고정 3D scene + predefined AGV | enable/disable/reload, 실행/reset 반복. 중복 prim·callback 누적 없음. 필수 collider·관성·스케일 확인. Build 직후 camera/light/object가 실제 viewport에 보이고 렌더 캡처가 black frame이 아님 |
| M2 — 첫 Playground | 이미지+자연어 → scene/task → 주행 | M2-A/B/C PASS. 서로 다른 창고 이미지 3개 생성·실행 완료. 치수 탑다운 도면은 real provider/Isaac E2E를 실행했으나 랙 높이 오독으로 27/29 FAIL(M2-D PARTIAL), physics는 PASS. AGV 실제 이동과 충돌/시간/거리/횡이탈/roll/pitch/support structure 기록 |
| M3 — Copilot / Replay | 구조적 수정, 저장·재열기, 재생 | 지정 객체만 변경. 저장 후 scene/task/profile 복원. 기록 재생이 실물 명령을 발행하지 않음 |
| M4 — GPU 서버 데모 | Linux full Isaac Sim에서 동일 Extension 실행 | 원격 입력 → 생성 → 서버 시뮬레이션 → 관찰·저장 E2E. 사용 GPU/버전·Nebius 사용 증거·실행비용 기록 |
| M5 — ROS2/Nav2 시뮬레이션 | sim bridge, map/TF/odom/scan, 목표 이동 | frame·time 정합, 목표 도착, 장애물 회피. parameter 변경이 주행에 반영됨. 통신 실패 처리 |
| M6 — 독립 학습/최적화 | 별도 worker와 검증된 parameter artifact | baseline 대비 동일 조건 비교, 충돌/성공/시간/거리/부드러움 기록. held-out 시험. worker 실패가 UI를 죽이지 않음. 실제 RL과 단순 탐색 구분 |
| M7 — 실물 Scan / Deploy | 스캔 보정·승인된 배포·실측 비교 | 비상정지·통신 끊김 정지 확인 후 제한 구역 저속 시험. 정합/장애물 오차 측정. artifact 적용·rollback 및 실물 결과 기록 |

기본 진행 순서는 M0 → M1 → M2 → M3이다. M4는 핵심 Extension 동작이 확인되면 조기에 수행해 최종 배포 위험을 줄인다. M5 → M6는 별도 확장선이다. M7의 일부 mapping/telemetry 시험은 가상 입력으로 앞당길 수 있으나 실물 Deploy 완료를 대신하지 않는다.

성능 수치나 개선율은 측정 전에 임의로 확정하지 않는다. 각 단계 종료 시 실행 환경·입력·예상·실제·로그 위치·pass/fail을 남긴다. import 성공, UI 표시, USD 로딩, physics 성공, 학습 완료는 서로 다른 검증 수준이다.

### 다음 구현 작업의 시작점

2026-09-15 현재 **D1/D2는 확정되고 R0 기준 소스 정리는 완료**했다. 다음 재개점은 사용자에게 선택된 R1 입력/치수/복원 정합성이다. 이어 R2 stage identity/안전, R3~R6 app service/bridge/외부 UI/자동 검증 순서다. 사용자가 해당 단계를 선택하기 전 구현하지 않는다. M2-D 유료 29/29 재시험부터 자동 시작하지 않는다. 도면 정확도는 후속 R9로 유지하며 a.biz 호환성은 계속 미확인이다. 기존 headless 자동화는 재사용하지만 Full viewport 캡처와 실제 UI 검증은 별도 acceptance로 추가해야 한다.

## 11. Blocking risk와 fallback

| 위험 | 영향 | 우선 대응 / fallback |
|---|---|---|
| 현재 PC의 OS·VRAM·RAM 부족 | 작은 CPU physics는 통과했지만 full RTX/복잡 scene 시험 불안정 | MinimalRendering·작은 fixture로 초기 개발, 최종 검증은 RT GPU 서버 |
| local Kit registry 연결 실패 | 온라인 index sync error, 새 dependency가 필요하면 enable 실패 가능 | M1은 local dependency로 통과. 다음 외부 dependency 도입 전 bundle/lock과 network 조건 확인 |
| 회사 사례의 CUDA/PhysX 오류와 제한된 VRAM | 화면 성공만으로 physics 신뢰 불가 | 최소 scene부터 원인 분리, 복잡도 축소, 필요 시 서버 |
| 일반 사진의 치수·가림 정보 부족 | 실제 환경과 차이 | 개략 경고, 도면·명시 치수·후속 scan 보정 |
| provider의 vision/구조화 출력 미확인 | 이미지 기반 생성 차단 | capability 시험, 지원 provider 선택. mock은 내부 시험만 |
| reload 뒤 generated draft 소실 및 sample fallback | 이미지 기반 생성처럼 보이지만 실제로 고정 fixture가 Build됨 | draft/tool plan persistence, generated/sample action 분리, generated-build fallback 금지, UI·로그에 build source 표시 |
| 제한된 primitive compiler와 고정 prompt | 서로 다른 이미지도 두 랙·단일 AGV의 유사 장면으로 축약됨 | image-first prompt, typed scene-tool catalog 확장, tool-plan preview, 3-image diversity acceptance |
| 버전/torch/Pixi 혼합 | dependency 또는 ABI 충돌 | 실행 방식 선택, version/commit/lock 분리 |
| GPU quota·credit·재고 미확인 | 최종 서버 데모 지연 | 조기 M4 검증, L40S 또는 다른 RT GPU 검토 |
| RL 비용과 Nav2 연동 throughput | 일정 지연·비교 불공정 | 별도 worker, 작은 파라미터 공간, 비학습 baseline 먼저 |
| 실물 구매 지연 | M7 실측 불가 | 가상 센서·Replay·모의 bridge까지 진행, 실물 완료 주장 금지 |
| sim-to-real 오차 | 실물 충돌·성능 저하 | 정합 검증, 제한 저속, watchdog, 승인된 artifact와 rollback |
| `2W`를 총 접지점 2개로 모델링 | 차체 pitch/nose-dive인데 XY metric만 PASS | 2 driven wheels와 passive support를 구분한 versioned RobotProfile, CoM/inertia, attitude/contact acceptance |
| 해커톤 규칙/일정 변경 | 제출 누락 | 공식 규정 재확인, 서버 증거·영상·README를 일찍 준비 |

## 12. 권한 및 승인 경계

| 작업 | 기본 경계 |
|---|---|
| 현재 Baseline·메모리 작성 | 이번 사용자 요청으로 승인. 원본 첨부 문서는 수정하지 않음 |
| 이후 선택한 신규 프로젝트 내부 구현 | 해당 구현 요청의 범위 안에서 파일·테스트 변경 |
| `C:\isaacsim` 하위 | 사용자가 이 기존 설치 root 하위의 TwinPulse 설치·runtime·scratch 변경을 승인. 새 `C:\Isaac` 경로를 만들라는 뜻이 아님 |
| 비파괴 환경 조회·공식 문서 조사 | 필요한 범위만 읽기. 접근 거부를 우회하지 않음 |
| 패키지/Isaac/Lab/ROS2 설치 | 대상 경로·버전·용량·격리 방식·실행 범위를 설명하고 필요한 권한 확보 |
| 기존 Isaac 삭제·자료 이동 | 정확한 대상과 보존/복구 계획에 대한 별도 명시 승인 |
| driver·OS·WSL·Docker·방화벽 변경 | 시스템 영향이 있으므로 별도 승인, 회사 정책 준수 |
| API 연결 | 비밀값을 채팅으로 요청/출력하지 않음. 사용자가 안전한 저장소에 설정한 뒤 비밀값을 제외한 연결 시험 |
| 유료 API/VM/스토리지 | provider·예산 상한·시간·자동 종료/정리 범위 승인 후 사용 |
| 외부 포트 공개 | 필요한 접속자·인증·허용 범위 확인 후 최소 개방 |
| 실물 AGV 모터/Deploy | 현장 준비·비상정지·저속 범위·명시적 구동 승인 필요 |
| 공개 저장소/영상 제출 | 공개 대상·라이선스·회사 자료 포함 여부 확인 후 승인된 범위만 공개 |

M0-B에서 사용자 승인에 따라 `C:\isaacsim`의 5.1 활성 설치를 공식 6.0.1 standalone으로 교체했고, M1에서 승인된 제품 root 내부에 신규 Git 저장소와 Extension을 만들었다. 시스템 설정, driver/WSL/Docker/방화벽, ROS2/Lab 설치, API key 요청·출력, 클라우드 자원 생성, 모터 구동은 수행하지 않았다. 5.1 안전 백업의 재귀 삭제는 정책 차단으로 실행되지 않았으며 우회하지 않는다. M2-B는 사용자 설정 UI와 Windows 자격 증명 저장소를 구현했지만 Codex가 key를 만들거나 열람하지 않았고 유료 API 요청도 보내지 않았다. 실제 호출은 사용자가 UI에서 key를 설정하고 명시적으로 Generate를 누르는 범위로 한정한다.

## 13. 남은 결정과 질문 시점

다음 항목은 Baseline 작성의 blocker가 아니며 필요한 단계 직전에 묻는다.

1. M0: 실제 실행할 회사 PC 접근 방식·현재 사양·설치 상태, 또는 서버 사용 여부.
2. M1~M2: 첫 predefined AGV, 지원할 장비 템플릿, 공개 가능한 이미지 fixture.
3. M2: 사내 endpoint의 비밀값 없는 접속 규격·실제 model ID·vision 지원. 키 자체를 문서에 기록하지 않음.
4. M4: Nebius 계정의 실제 GPU quota/credit, region, 비용 상한과 실행 시간.
5. M5: 현장/서버 ROS2 배치, standalone/Pixi 방식, RMW 및 version lock.
6. M6: parameter 범위, reward, 성공·안전·성능 임계값, 학습 예산.
7. M7: AGV 총예산·모델·구매 일정, 최종 트랙 도면과 센서 위치.

## 14. 변경 관리와 프로젝트 메모리

Baseline은 고정된 출발점이지만 영구 불변 사양은 아니다. 실제 구현 결과와 사용자 결정에 따라 갱신한다.

- canonical 파일명은 TWINPULSE_BASELINE.md로 유지한다.
- 의미 있는 변경 때 버전과 기준일, 아래 변경 이력을 갱신한다.
- 이전 결정은 조용히 삭제하지 말고 변경 전/후·이유·영향·근거를 남긴다.
- 요구사항 범위, 비용, 하드웨어, 보안/배포 권한이 실질적으로 달라지면 사용자 결정을 받는다.
- 승인된 범위 내의 기술 오류 수정·테스트 상태 업데이트는 진행하면서 기록한다.
- PROJECT_MEMORY는 요약본이다. Baseline과 같은 버전을 가리키고, 현 단계·다음 단계·blocker를 동기화한다.
- 중요한 상태 변화 또는 milestone 종료 시 Baseline와 메모리를 함께 갱신한다.
- 구현하지 않은 기능을 완료 처리하지 않는다. 테스트하지 않은 주장을 새 확인 사실로 승격하지 않는다.
- 새 저장소로 이전할 때 Baseline·메모리·변경 이력을 함께 옮기고 AGENTS.md 참조 경로를 수정한다.

현재 메모리는 **프로젝트 파일 기반의 지속 기록**이다. 계정 전체의 내장 메모리에 저장했다는 뜻은 아니다. R0 이후 기준 저장소 `AGENTS.md`가 `docs/planning/`의 두 문서를 참조한다. 다른 작업 폴더나 별도 프로젝트에서는 기준 저장소를 사용하거나 파일을 함께 전달하고 참조를 연결해야 한다. 이는 Codex의 프로젝트 지침 방식에 따른 구성이다. [S15]

### 변경 기록 양식

`변경 ID / 날짜 / 버전 / 변경 전 → 변경 후 / 이유·근거 / 영향 받는 단계·시험 / 승인 여부 / 검증 상태`

### 변경 이력

| ID | 날짜 | 버전 | 변경 | 근거·상태 |
|---|---|---|---|---|
| BL-029 | 2026-09-15 | 1.0.28 | 사용자 D1/D2 확정 및 R0 인수인계 | React 로컬 웹 App+별도 Isaac 창으로 확정. GitHub 연결 기존 clone을 단일 기준 root로 선정하고 M2-D 신규 6/수정 11파일을 원본 해시 일치로 이관. 기존 개발본/제품 사양서 보존. 기준 root에서 Core 24/24·Provider 13/13 PASS. M2-D 정확도, 실제 Isaac/UI, R1~R10은 미검증·미착수. 설치·유료 호출·push 없음 |
| BL-028 | 2026-09-15 | 1.0.27 | 전체 코드 검토와 외부 App 전환 단계 계획 | sidecar 규격/입력-draft 연결 오류 및 stale stage/안전/검증 범위 위험을 정리. R0~R10 지침, Phase 1 파일 단위 변경안/API/소유권/회귀 gate 작성. D1/D2 확인 대기. 문서만 수정했으며 제품 코드·설치·유료 호출·push·실물 명령 없음. 과거 M2-C PASS와 M2-D PARTIAL 유지 |
| BL-001 | 2026-09-12 | 1.0 | 기존 사양·사용자 정정·환경 조사를 통합. 3D Playground 우선, 실물 확장, 서버 최종 목표, 프로세스 분리, 승인 경계와 단계별 시험 정의 | 사용자의 Baseline 문서·메모리 저장 요청. 문서화 완료, 구현 미착수 |
| BL-002 | 2026-09-12 | 1.0.1 | Sol용 단계별 지시서 연결 및 메모리 갱신. M0~M7을 실행 가능한 하위 단계로 분해 | 사용자 요청에 따른 문서 추가. 제품 범위·권한·구현 상태 변경 없음. 추론 수준은 운영 권고이며 앱 설정 변경 아님 |
| BL-003 | 2026-09-12 | 1.0.2 | M0-A 비파괴 readiness 결과 연결. 현재 PC를 개발 host 후보로 분리하고 신규 root 및 M0-B host 결정을 gate로 기록 | 직접 조회 완료. 제품 요구사항 변경 없음. 코드·설치·Isaac 실행 미착수 |
| BL-004 | 2026-09-12 | 1.0.3 | 개발 root를 `C:\Users\jaewo\Documents\Codex\TwinPulse`로 확정. 초기 Extension에 필요한 M1-A를 현재 PC에서 선행하고, M0-B/M1-B runtime 검증은 회사 6.0.1 PC에서 수행하는 순서 확정 | 사용자 승인 및 범위 정리. M0-B는 생략하지 않되 현재 5.1 PC에서는 수행하지 않음. 구현·runtime 실행 미착수 |
| BL-005 | 2026-09-12 | 1.0.4 | 사용자가 기존 `C:\isaacsim` 하위 변경을 승인해 5.1 활성 설치를 공식 6.0.1로 교체. Full 앱 부팅 및 외부 asset 없는 procedural wheeled-robot smoke 3회 통과 | M0-B 제한 조건부 PASS. bundled checker는 VRAM/RAM 부족으로 FAILED. 약 21.85GiB의 5.1 안전 백업 정리는 정책 차단으로 미완료. 제품 범위 변경 없음 |
| BL-006 | 2026-09-12 | 1.0.5 | 신규 Git 저장소, pure core/schema/validation, 고정 3D scene과 `twinpulse.extension-0.1.0` 구현 | M1-A 단위시험 10개 PASS. M1-B enable/disable 및 run/pause/reset 각 3회 PASS. local registry sync 및 headless harness frame-retention warning 기록. 다음 단계 M2-A. 제품 범위 변경 없음 |
| BL-007 | 2026-09-13 | 1.0.6 | 사용자 화면에서 0.1.0 Build 후 black viewport를 확인. 0.1.1에 overview camera, dome/sun light, viewport focus, 목표 마커, 1.5m route와 UI yield를 추가하고 M1 acceptance에 visible-frame 조건을 명시 | core 10개 PASS. 구조 계약(camera/light/goal)과 physics 3회 결과는 PASS 출력을 확인했으나 이중 Isaac 실행의 registry/OptiX lock 및 메모리 압박으로 clean shutdown/렌더 캡처는 보류. 한 인스턴스 재시작 후 시각 재검증 필요 |
| BL-008 | 2026-09-13 | 1.0.7 | 후속 사용자 화면으로 초기 scene이 실제 렌더링됐고 black 상태는 긴 초기 지연이었음을 확인. manifest 0.1.1은 기존 Isaac enable list의 정확한 0.1.0 pin과 충돌해 로드 실패했으므로 사용자 설정 대신 package version을 0.1.0으로 복귀 | compatible visible-scene code를 유지한 Full 앱 단일 인스턴스가 재실행되어 응답 중. headless RTX capture는 8GB host에서 정지해 제거. fresh Build/Focus/Run 화면 확인 대기 |
| BL-009 | 2026-09-13 | 1.0.8 | Codex가 `Start-Process`로 시작한 Isaac은 프로세스만 존재하고 사용자 Alt+Tab에 나타나지 않는 별도 백그라운드 세션이었음을 사용자 화면으로 확인 | 해당 Codex 생성 kit 프로세스를 종료. 이후 interactive UI 검증은 사용자가 자신의 PowerShell에서 launch script를 직접 실행하고 화면을 공유하는 방식으로 진행 |
| BL-010 | 2026-09-13 | 1.0.9 | 사용자가 launch script를 직접 실행해 visible-scene revision의 interactive acceptance 수행 | Build 후 28 prim과 camera/light/warehouse/AGV/goal 표시, Focus 성공, Run 중 remaining 0.929m 및 AGV 이동, Reset complete와 위치 복귀 확인. Full 앱 43~74 FPS, 프로세스 응답 상태. M1 local 제한 조건 PASS, 다음 M2-A |
| BL-011 | 2026-09-13 | 1.0.10 | M2-A provider boundary와 Copilot형 prompt-first UI 구현 | text+image request/capability/result, timeout/cancel/stale response, typed errors, credential-free config, local mock와 gated HTTPS adapter 추가. core 10/10, provider 6/6, Isaac lifecycle/physics 각 3회 PASS. real provider와 image picker는 NOT RUN, Full 앱 UI 외형은 사용자 재시작 후 확인 필요 |
| BL-012 | 2026-09-13 | 1.0.11 | 최초 M2-A UI 시각 검수 실패와 즉시 교정 | Isaac 기본 폰트에서 한글/특수문자가 `?`로 깨지고 auto-layout 간격이 과도하게 확장됨. UI text를 ASCII-only로 바꾸고 모든 주요 stack/card를 explicit `ui.Pixel` 크기로 고정. 수정 후 Extension lifecycle/physics 각 3회 PASS, Full 앱 재검수 대기 |
| BL-013 | 2026-09-13 | 1.0.12 | 교정 UI 사용자 확인 및 M2-B local multimodal/provider 통합 | Settings(Base URL/model/reasoning/key), persistent non-secret 설정, Windows Credential Manager, 1-image picker/preview, `POST /responses` image+strict schema adapter, generated bundle scene 교체와 1회 개략 경고 구현. 현재 controller가 수행할 수 없는 sideways/blocked route gate 추가. core 13/13, provider 8/8, Isaac lifecycle/physics 3회와 generated-bundle 교체 PASS. 실제 API와 사용자 image-preview는 NOT RUN |
| BL-014 | 2026-09-13 | 1.0.13 | Settings 기본 크기 접근성 결함 수정 | 사용자 Full 앱에서 Settings의 비스크롤 `VStack`이 API Key와 Save 버튼을 아래로 미는 현상을 확인. 560x420 compact row layout, explicit content height, `ScrollingFrame`으로 수정. compileall, core 13/13, provider 8/8 PASS. Full 앱 시각 재검수 대기 |
| BL-015 | 2026-09-13 | 1.0.14 | provider 상태 의미와 생성 진행 피드백 교정 | `LLM READY`가 key 저장을 연결 성공처럼 표시하고 생성 상태가 하단에 숨는 문제를 확인. 시작은 `KEY SAVED`, 실제 성공 후 `LLM CONNECTED`로 구분하고 Generate 버튼의 `Generating...`/비활성화 및 버튼 바로 아래 진행·오류 표시, 비밀 없는 시작/완료 로그를 추가. compileall, core 13/13, provider 8/8 PASS. 실제 호출과 Full 앱 시각 재검수는 NOT RUN |
| BL-016 | 2026-09-13 | 1.0.15 | 첫 실제 Luna draft 성공 및 draft/3D Build 상태 분리 | 사용자 실행 요청이 약 9초 후 `bright_warehouse_center_aisle`/3 objects draft로 검증 완료됨. 화면·로그로 provider→strict draft PASS를 확인했으나 이미지 포함 여부는 미확인. 경고창의 Build 확인 버튼이 잘려 실제 3D 적용은 미완료. `Draft preview`, `DRAFT VALID`, `Build Generated Scene`, `Continue and Build 3D`, 실제 Build 완료 문구로 상태를 분리하고 경고창을 확대/scroll 처리. compileall, core 13/13, provider 8/8 PASS; Full 앱 재검수 대기 |
| BL-017 | 2026-09-13 | 1.0.16 | 실제 Build 출처 확인 및 multimodal tool-orchestration 목표 명시 | 첫 Luna draft는 real provider 결과였지만 reload 뒤 유실됐고, 이후 console의 `source=sample fixture, prims=28`로 사용자에게 보인 3D가 M1 고정 fixture임을 확인. 동일 기본 prompt와 제한된 primitive compiler도 유사 장면을 유도한다. 목표를 image+text planner→allowlisted scene tools→validated execution으로 명시하고 draft persistence, silent fallback 제거, image/build-source audit를 다음 작업으로 지정. 진단·문서 갱신만 수행했으며 구현 시험은 미실행 |
| BL-018 | 2026-09-13 | 1.0.17 | image-first allowlisted tool orchestration과 source integrity 구현 | strict scene-tool plan과 8개 typed tool registry, deterministic `SpecBundle` expansion/route validation, plan-hash draft persistence, generated-only Build, image/tool/object/source UI·log·USD audit를 구현. compileall, core 18/18, provider 8/8, Isaac 50-prim generated plan·implicit fallback rejection·의도적 mid-replacement 실패 시 이전 scene/PhysicsScene 보존·lifecycle/physics 3회 PASS. 새 실제 provider image E2E와 Windows runtime save/restore는 미실행 |
| BL-019 | 2026-09-13 | 1.0.18 | 첫 image-first real 요청의 semantic reject 진단성/schema 정렬 교정 | 사용자 요청에서 `images=1`과 structured output을 확인했으나 local semantic validation이 거절했고 generic error가 원인을 숨김. exact bounded cause 표시, provider numeric schema/local limit 정렬, stable ASCII ID와 0.7m clear-route planner 지시를 추가. compileall, core 18/18, provider 8/8 PASS. 자동 유료 retry 없이 수정 후 real 재시험 대기 |
| BL-020 | 2026-09-13 | 1.0.19 | real image tool-plan E2E 확정 및 장거리 AGV 이탈 교정 | 사용자 실행에서 `images=1`, `warehouse_aisle_scene_01`, 14 tools/59 objects, generated 134 prims와 plan `a135a31a65d7` 및 reload 복원을 확인. 6.9m 주행의 동일 바퀴속도 open-loop를 목표/yaw feedback 차동조향으로 교체하고 0.20m 통로 이탈 안전정지·실시간 aisle error 상태를 추가. compileall, core 20/20, provider 8/8, Isaac lifecycle/run-reset/generated/fallback/rollback 및 long route PASS(목표 오차 0.049724m, 최대 횡이탈 0.005134m) |
| BL-021 | 2026-09-13 | 1.0.20 | RobotProfile v2와 자동 3D episode acceptance | XY metric만 통과한 2접점 AGV의 nose-dive를 사용자 화면에서 확인. `agv_compact_2wd_caster_v2`에 2 driven wheels+2 passive ball casters, CoM/inertia와 8° attitude stop을 고정하고 legacy plan alias, scene/robot/task tool domain·execution receipt, 실행별 artifact runner를 구현. core 23/23, provider 8/8, Isaac lifecycle 3/3·short run/reset 3/3·generated/fallback/rollback·6.9m long route PASS. 장거리 최대 pitch 0.0306°, roll 0.0433°, 횡이탈 0.000825m, goal error 0.049306m, geometric collision samples 0. MinimalRendering screenshot은 NOT RUN |
| BL-022 | 2026-09-13 | 1.0.21 | 회사 PC 재현용 배포 스냅샷 공개 | `verify_twinpulse.ps1`에 `-IsaacRoot`를 추가하고 회사 PC 설치·검증·키 설정·문제 해결 문서를 작성했다. 변경 후 local 전체 회귀 `20260913-232144` PASS 및 배포 clone의 core 23/23·provider 8/8 PASS를 확인하고 GitHub `lee2017-bit/TwinPulse` main의 `3873f34`로 push했다. API key 패턴은 0건이며 artifacts/cache는 제외했다. 다만 실제 이미지 persisted plan의 deterministic replay가 187 frames에서 roll 9.0393° `unstable`로 정지했으므로 임의 generated plan의 물리 안전은 미해결 제한이며 M2-C는 미완료다. 사용자의 우선순위 변경 및 공개 승인 범위 안에서 배포 후 기능 수정은 중단 |
| BL-023 | 2026-09-14 | 1.0.22 | generated-layout 대형 바닥 물리 안정성 결함 수정 | persisted real-image plan의 roll 불안정은 18×12×0.1m 바닥을 non-uniform scale `UsdGeom.Cube` collider로 컴파일한 것이 원인이었다. 랙·마킹·static AGV 제거, 좌표 이동, Reset 유무와 무관하게 재현됐고 실제 치수 closed `UsdGeom.Mesh`로 교체하면 해소됐다. 동일 8m plan은 1,889 frames에 완료(goal error 0.246468m/허용 0.25m, 최대 roll 0.086213°, pitch 0.073829°). 영구 18×12m Mesh/no-scale 계약과 6.9m 주행을 추가한 전체 회귀 `20260913-234455`도 PASS(core 23/23, provider 8/8, lifecycle 3/3, short run/reset 3/3, goal error 0.049289m, 최대 roll 0.076246°, pitch 0.066773°, collision samples 0). MCP/tool orchestration 결함이 아니라 scene compiler의 물리 primitive 결함으로 판정. 수정 commit `1c5ed27`, 배포 기록을 포함한 GitHub main `8cb2541`. 한 plan 검증일 뿐 임의 장면 보장과 M2-C 3-image 평가는 미완료 |
| BL-024 | 2026-09-14 | 1.0.23 | M2-C 서로 다른 실제 이미지 3개 provider→Isaac 자동 E2E 완료 | Wikimedia Commons fixture 3개를 출처/라이선스/SHA-256으로 고정하고 저장 key를 노출하지 않은 one-attempt Luna 요청 3회를 실행. 10/9/18 tools와 58/58/46 objects의 서로 다른 plan을 얻어 Isaac에서 136/136/112 prim 장면을 Build·Run·Pause·Reset했고 모두 `completed`, collision 0, Pause/Reset 오차 0m. goal error 0.2464/0.2444/0.2153m, 최대 횡이탈 0.00515m 이하, roll/pitch 0.1029°/0.0667° 이하. 의도적 collision 계측 regression을 추가해 core 24/24, provider 8/8 및 전체 Isaac 회귀 `20260914-062541` PASS. 사용자 수동 실행·스크린샷 없이 headless 재현 가능. 이미지 binary와 key 없이 GitHub main `c35e9fc`로 공개. 세 fixture와 positive-X controller에 한정하며 일반 navigation/실물 보장은 아님 |
| BL-025 | 2026-09-14 | 1.0.24 | M2-D 치수 탑다운 도면 자동 평가 harness 및 부분 검증 | 12×8m floor, 8×1.5×3m rack 2열, 2.5m 외벽, 2m 중앙 통로, (-4,0)→(4,0) route를 라벨링한 deterministic PNG와 SHA-256 manifest, 29개 coordinate scorer를 추가. provider/Isaac runner를 임의 non-empty fixture 수와 PNG/JPG/WEBP에 일반화. reference plan은 29/29, 9 calls/35 objects, 실제 Isaac 90 prim, 32.583s/7.903m 주행, goal error 0.09887m, cross-track 0.00390m, roll/pitch 0.10101°/0.06674°, collision/Pause drift/Reset error 0으로 PASS. 실제 Luna one-attempt는 저장된 key가 거절되어 inference 전 FAIL했고 retry하지 않았으므로 도면 판독은 미완료 |
| BL-026 | 2026-09-14 | 1.0.25 | M2-D 실제 provider 도면 판독과 Isaac E2E | 새 key로 Luna exactly one attempt 성공, `dimensioned_warehouse_floor_plan` 10 calls/32 objects 생성. 바닥 12×8m, 벽 2.5m, 랙 길이/깊이/베이, 중앙 통로, (-4,0)→(4,0) route는 통과했으나 랙 높이 3.0m를 2.0m로 두 번 오독해 27/29 FAIL. 동일 provider bundle을 실제 Isaac 84 prim으로 빌드해 32.583s/7.903m, goal error 0.09887m, cross-track 0.00390m, roll/pitch 0.10101°/0.06674°, collision/Pause drift/Reset error 0으로 physics PASS. 33,823-byte USD 저장 후 Full 앱 재오픈 |
| BL-027 | 2026-09-14 | 1.0.26 | M2-D 도면 고해상도 입력과 독립 치수 검증 gate | 기존 27/29 실패의 직접 원인 중 하나가 모든 이미지에 OpenAI `detail=low`를 강제한 호출임을 확인. 도면/평면도 cue는 `high`, 일반 사진은 `low`를 유지하도록 분기하고, 이미지와 같은 stem의 `*.measurements.json`을 strict loading하여 LLM tool plan의 치수와 대조한 뒤 registry 실행 전 불일치를 거절하도록 구현. 실제 기존 오답 plan은 `rack_height expected 3 +/- 0.25, got 2`로 차단되고 `build_allowed=false`. Provider 13/13, Core 24/24, compileall, 8개 sidecar 생성·로딩 PASS. clean Full-app 재기동에서 Extension startup 및 `app ready` 확인. 추가 유료 요청은 하지 않았으므로 M2-D는 PARTIAL 유지 |

## 15. 원본 자료 및 공식 참조

### 원본 자료 식별

원본은 수정하지 않았다. 아래 hash는 Baseline 작성 시 읽은 파일을 식별하기 위한 SHA-256이다.

| 자료 | 원본 위치 | SHA-256 |
|---|---|---|
| 제품 사양 v1.2 | C:\Users\jaewo\Downloads\TWINPULSE_PRODUCT_SPEC_v1_2.md | 6645538EE46DE8D49ABC315DA2587EE796F29559C72A307291AE9362C4C2A201 |
| 회사 재설치 사례 | C:\Users\jaewo\Downloads\IsaacSim_6.0.1_IsaacLab_3.0.0-beta2.patch1_Reinstallation_Guide.md | B6652E579B0AFE4A416A78331A7788434475265BF945492FBF37BA0AFEC3E81B |

사용자의 이 대화에 포함된 설명·정정이 제품 의도 해석의 1차 근거다. 회사 사례의 설치 성공 범위와 현재 PC의 직접 조회 결과를 혼합하지 않는다.

### 공식 참조 목록

2026-09-12 조사 기준. latest/main 문서는 변할 수 있으므로 설치·구매·제출 직전에 다시 확인한다.

- **S1**: [Isaac Sim 6.0.1 requirements](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/requirements.html)
- **S2**: [Isaac Sim 6.0.1 release notes](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/overview/release_notes.html)
- **S3**: [Extension templates — 6.0.0 계열 참고](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/utilities/cli_extension_templates.html)
- **S4**: [Simulation Manager API — 6.0.1](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/py/source/extensions/isaacsim.core.simulation_manager/config/python_api.html)
- **S5**: [Isaac Lab v3.0.0-beta2.patch1 source](https://github.com/isaac-sim/IsaacLab/tree/v3.0.0-beta2.patch1), 특히 source/isaaclab/setup.py와 source/isaaclab_rl/setup.py.
- **S6**: [ROS installation — latest, 변경 가능](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_ros.html)
- **S7**: [ROS2 launch tutorial — 6.0.1](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/ros2_tutorials/tutorial_ros2_launch.html)
- **S8**: [IsaacSim ROS Jazzy Pixi manifest — main, 변경 가능](https://github.com/isaac-sim/IsaacSim-ros_workspaces/blob/main/jazzy_ws/pixi.toml)
- **S9**: [slam_toolbox 공식 ROS 문서 — mapping 개념 참고, Humble 고정 결정 아님](https://docs.ros.org/en/humble/p/slam_toolbox/)
- **S10**: [Nav2 Jazzy MPPI](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/mppi_controller/configuring_mppic/), [Constrained smoother — rolling 참고](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/smoother_plugins/constrained_smoother/configuring_constrained_smoother/)
- **S11**: [SLAMTEC C1](https://www.slamtec.com/en/c1/), [공식 ROS2 driver](https://github.com/Slamtec/sllidar_ros2), [DFRobot 판매 페이지 — 가격은 구매 시 재확인](https://www.dfrobot.com/product-2803.html)
- **S12**: [Token Factory model API](https://docs.tokenfactory.nebius.com/api-reference/models/list-models), [Vision capabilities](https://docs.tokenfactory.nebius.com/api-reference/examples/vision-capabilities)
- **S13**: [Nebius GPU VM types](https://docs.nebius.com/compute/virtual-machines/types)
- **S14**: [Nebius Global AI Hackathon 공식 제출 페이지](https://nebiusglobalaihackathon.devpost.com/). 제출 형식·마감·필수 모델/플랫폼 사용 조건은 제출 준비 시 재확인한다.
- **S15**: [Codex AGENTS.md 프로젝트 지침](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- **S16**: [OpenAI model catalog](https://developers.openai.com/api/docs/models), [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- **S17**: [OpenAI Responses API create](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- **S18**: [OpenAI API key permissions](https://help.openai.com/en/articles/8867743-assign-api-key-permissions)

---

**이후 작업 원칙: 현재 단계를 확인하고 → 승인 범위 안에서 구현하고 → 실제 검증 결과를 남기고 → 변경된 기준과 메모리를 동기화한다.**
