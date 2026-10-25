# TwinPulse 실행과 검증 절차

이 문서의 명령은 검토·재현 방법입니다. 문서 수령이 설치·유료 호출·실물 구동 승인은 아닙니다. 현재는 충전 중이므로 Claude 독립 검토는 파일 읽기와 승인된 무구동 검사에 한정합니다.

## 1. 실행 전에 구분할 것

- ZIP은 소스 검토 묶음이며 실행 설치본이 아닙니다. `.venv`, `node_modules`, Electron/Isaac/ROS, 사용자 프로젝트와 개인 USD를 포함하지 않습니다.
- 원 PC 기준 개발 root는 `C:\Users\jaewo\Documents\TwinPulse`, Isaac은 `C:\isaacsim`, App runtime은 `%LOCALAPPDATA%\TwinPulse\runtime`, 설치본은 `%LOCALAPPDATA%\TwinPulse\installed`입니다.
- Python은3.12 계열입니다. 현재 web lock은 pnpm11.19.0/React19.3.0/Playwright1.63.0, desktop은 Electron44.7.2입니다. ZIP 내 lockfile을 기준으로 하며 최신 버전 자동 갱신은 하지 않습니다.
- 환경이 없으면 **무엇이 없는지 보고**합니다. ROS/SDK/브라우저/driver를 자동 설치하지 않습니다. PC에 ROS SDK가 없다고 Pi의 기존 ROS가 없거나 삭제됐다는 뜻은 아닙니다.

## 2. 가장 작은 무구동 검토

원 PC에서는 repository root, ZIP만 받은 별도 환경에서는 `source/`를 cwd로 사용합니다. 이미 준비된 compatible Python이 있을 때만 실행합니다.

```powershell
# 신규 finite authority 경계 10개: fake clock/device + 실제 Python publish 경계
.\.venv\Scripts\python.exe -B packages\twinpulse_robot_safety\tests\test_finite_execution.py -v

# 현재 test_*.py 로봇 회귀 252개
.\.venv\Scripts\python.exe -B -m unittest discover -s packages\twinpulse_robot_safety\tests -p 'test_*.py'
```

위252개는 파일명이 `*_test.py`인 legacy 시험과 C++/실ROS/HW/UI 전체를 포함하지 않습니다. 실제 원로그는 `evidence/latest/finite-execution-green04.log`, `finite-robot-regression03.log`입니다. 이 인계 작업에서는 전체 시험을 다시 반복한 것으로 기록하지 않습니다.

필요한 변경에 한해 실행할 추가 예:

```powershell
# App/transport/registry 경계. 원 PC의 기존 .venv와 repo import 배치를 사용
.\.venv\Scripts\python.exe -B -m unittest tests.integration.test_physical_live_session tests.integration.test_physical_fleet_adapter tests.integration.test_registry_control_contention

# UI/타입: 이미 있는 pnpm dependency만 사용, 외부 model/하드웨어 시험 아님
pnpm --dir apps\twinpulse-web test -- src/RobotFleet.test.tsx src/RobotTimingSettings.test.tsx src/PhysicalLidarPanel.test.tsx
pnpm --dir apps\twinpulse-web exec tsc -b
```

보조검사의 mock sensor/fake SDK·clock은 반례 재현 수단입니다. 새 설치 GUI·실제 ROS/MCU·물리 결과로 승격하지 않습니다. 전역 `PYTHONPATH`나 시스템 PATH를 영구 변경하지 마세요. broad verifier `scripts/verify_twinpulse.ps1`는 더 넓은 부하/의존성이 있어 이번 검토의 필수 첫 단계가 아닙니다.

기존 C++ compiler/CMake가 이미 준비된 경우의 한정 guard 시험:

```powershell
# 새 전용 output, 기존 폴더 재사용/삭제 금지. compiler 없으면 설치하지 않고 NOT_RUN
cmake -S packages/twinpulse_robot_safety -B outputs/claude-guard-review-01 -DBUILD_ROS_TESTS=OFF
cmake --build outputs/claude-guard-review-01
ctest --test-dir outputs/claude-guard-review-01 --output-on-failure
```

이는 PC guard/legacy device-free 검사입니다. Pi ARM64 ROS target build/readback과 다릅니다. `BUILD_ROS_TESTS=ON`은 별도 ROS 환경을 요구하므로 임의 활성화하지 않습니다.

## 3. 실제 App 실행 경로

일반 사용자 진입은 repository root의 `Start-TwinPulse.cmd`입니다. 설치본이 있으면 그 설치본을 엽니다. **소스를 고쳤다고 이 진입의 설치 코드가 바뀌지 않습니다.** 명시적 소스개발은 `Start-TwinPulse-Development.cmd`로 구분합니다. 설치·업데이트가 필요하면 먼저 기존 source/release와 변경 범위를 확인합니다.

검증용은 `Start-TwinPulse-Test.cmd`로 같은 설치 Electron 창을 엽니다. Test는 sandbox/별도 사용자 profile/SIM-only를 뜻하지 않습니다. 실제 프로젝트와 provider·물리 기능이 열릴 수 있습니다.

기존 로컬 UI helper 사용 예는 `source/docs/DESKTOP_UI_TESTING.md`에 있습니다. 현재 launch의 identity/endpoint를 돌려주는 `scripts/start_installed_electron_ui_test.ps1`를 사용하고 포트19222를 고정 가정하지 않습니다. normal Start는 debugger off, Test는 loopback19222–19231 범위입니다.

일반 UI 인수는 실제 동일 BrowserWindow에 attach해 클릭·입력합니다. 별도 Chrome/context·직접 product mutation API·상태 주입·고정 LLM 응답·상시 request interception으로 대체하지 않습니다. locator는 보이는 text보다 실제 accessible name을 확인합니다. 예: `Exit`의 accessible name은 `Exit TwinPulse`, LiDAR는 `Turn LiDAR on/off`입니다. Playwright locator 제한보다 도구 실행 제한을 길게 잡아 recorder kernel reset을 피합니다.

## 4. 무구동 화면 확인과 SIM 여정

단순 화면 확인을 하더라도 실제 새 App/Isaac 부하가 생깁니다. 현재 검토에서 필요 없다면 시작하지 않습니다. 시작했으면 실제 창의 Home/Isaac readiness, 설치 source/release/launch ID를 확인합니다. 디버그 포트만 있다고 PASS가 아닙니다.

유료 입력/모델 호출이 승인된 SIM 데모는 Home→New chat→실제 텍스트/사진 또는 명시 Import→Inspect/Import/Show Twin→engine ACK/live frame→로봇 등록/채팅 이력→Connect/Prepare→동작/목표·scan/OFF·Stop→편집/Apply/Undo→저장/재열기를 보여줍니다. RoomPlan 원본은 별도 제공되어야 하며 ZIP의 generic fixture로 바꿔 원본 인수라 하지 않습니다.

UI 입력은 English, 로봇 추가 과정과 이름/모델/좌표를 읽을 시간을 둡니다. command 입력 후 Enter 전3초를 두고 제출 후 입력창이 지워지는지 확인합니다. 이미 만들어진 방을 조종하는 excerpt는 fresh 생성 데모와 구분합니다.

## 5. 충전 이후 실제 로봇 시험

현재 충전 중에는 진행하지 않습니다. 다음 명시 현장 승인에서 충전선 분리·주변 확보·감독·즉시 전원 차단을 확인해야 합니다. 사진만으로 전면 공간의 거리/안전을 확정하지 않습니다. 아래는 **다음 시험 계획**이며 완료 이력이 아닙니다.

1. 같은 현재 설치의 원 RoomPlan project를 review/Show Twin하여 실제 frame과 source context를 확인합니다. scene 변화 후 옛 권한/목표를 재사용하지 않습니다.
2. physical robot을 명시 선택→Connect. 최신 heartbeat·ROS 측 전압/나이 확인. green 연결은 이동 허가가 아닙니다.
3. zero-command 준비 checkbox→Prepare. source-bound guard/기존 캐시·1200ms readback 확인. ad-hoc SSH로 성공한 일부 경로를 App 성공으로 대체하지 않습니다.
4. LiDAR ON→정지 collection·기록. 전압이11.1V 이하 경계에 닿으면 이번처럼 중단합니다. 저장/센서/제어 부하에서 여유를 확인하고 기준을 낮춰 진행하지 않습니다.
5. 현재 감독 checkbox→Arm **실제 ACK/armed 상태를 기다림**→명시 한정 bootstrap Stop. 클릭 성공/HTTP200만으로 다음 단계에 넘어가지 않습니다. 직전 실패에서는 도구가 Arm 거절 뒤 bootstrap을 눌러 후속 거절을 만들었으므로 재현하지 않습니다.
6. Stop readback/durable receipt가 성립하면 ordinary Robot command로 `Move forward 10 cm`, `Move backward 10 cm`, `Turn left 90 degrees`, `Turn right 90 degrees`를 각각 새로 제출합니다. 첫 실패를 보존하고 자동 재시도/다음 명령 chaining을 하지 않습니다.
7. 네 유한명령의 실제 terminal/Stop 근거가 통과하면 별도 `Turn left 360 degrees`. 약정된 fixed deadline과 supervision/source/발행 근거를 유지합니다.
8. 수동 pad/키보드는 이번 범위에서 제외합니다. 실물 `nearest sofa/bed/chair`는 정합·relative tracking·estimated route의 별도 승인/검증 없이 실행하지 않습니다.
9. 마감은 Stop→LiDAR OFF→Disconnect→cleanup/recording complete→원본 export→정상 App Exit입니다. 정리 미확인 시 사용자에게 즉시 전원 차단을 요청하고 추가 움직임을 멈춥니다.

거리/각도 target은 wheel basis와 실제 몸체를 구분합니다. 독립 LiDAR 비교는 같은 세션 stationary noise·전후 coverage·원시각을 확인하고 애매하면 INCONCLUSIVE를 유지합니다. 사용자를 반복해서 “움직였나” 답하게 하지 않습니다.

## 6. 기록과 종료의 필수 확인

- ID: 설치 source/release, launch, project/conversation/scene, robot, operation, connection/motion epoch, request를 구분합니다.
- 원 실패: `control_pause`와 같은 원예외에 결속된 `fault_diagnostic`/`original_failed_gate`, publish phases/source/나이·최초거절을 보존합니다. 후기 정상 heartbeat는 대체가 아닙니다.
- PC receipt: accepted=saved, complete=true, error=null, segment별 SHA/크기/행수. 원문은 UI `Operation logs`의 operation JSON과 별도 runtime files입니다.
- Pi 최종 session cleanup: ROS Stop/torque false/encoder 안정, device lease/worker 회수, journal/native accepted=saved·queued0·error없음·writer exit. complete sensor archive는 unknown 패킷을 해석 완료했다는 뜻이 아닙니다.
- App: visible Exit/일반닫기→해당 launch의 engine/backend root disposition/return0·내부join·Job정리를 각각 확인. CDP client 닫기는 App 종료가 아닙니다. 남의 프로세스 강제종료/launcher lock 삭제 금지.
- 다음 Start 전에 해당 runtime/Kit를 `archive_roomplan_runtime_20261023.py`로 새 copy-set에 hash-bound 보존합니다. unavailable 원문은 UNKNOWN으로 남깁니다.
- 영상은 실제 encoded frame과 decode를 검수합니다. renderer+mouse-event표식은 OS cursor/native desktop/실물 카메라 영상이 아닙니다. 최종 제출영상에는 별도 실제 하드웨어 footage 조건을 확인해야 합니다.

## 7. 빌드가 정말 필요한 경우

새 수정이 승인될 때만 기존 `.build-venv`와 locked web dependencies로 `scripts/build_windows_exe.py`를 사용합니다. 사용자용 current executable을 직접 편집하지 않습니다. 먼저 디스크여유·기존 소유세션 종료와 새 output 경로를 확인합니다.

현재 형식 예는 `--output-dir <new folder> --channel development --package-only --reuse-desktop-from <verified immutable previous package>`입니다. 재사용은 desktop 소스/버전 일치 검증을 통과하는 경우만 가능합니다. exact package verification→명시 installer→실제 같은 설치 시험을 구분합니다. `Install-TwinPulse.cmd`/dependency install을 단순 검토를 위해 자동 실행하지 않습니다.

이번 ZIP 자체를 새 release나 설치후보로 간주하지 마세요. package 생성은 소스 복사·SHA·ZIP roundtrip 검사만 수행합니다.
