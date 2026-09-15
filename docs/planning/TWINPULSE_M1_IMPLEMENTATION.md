# TwinPulse M1 — Extension 구현 및 검증 보고서

- 수행일: **2026-09-12 (KST), visible correction 2026-09-13**
- 프로젝트 root: `C:\Users\jaewo\Documents\Codex\TwinPulse`
- 단계 / 상태: **M1-A PASS / M1-B PASS (local limited runtime + interactive visual)**
- Runtime: Isaac Sim 6.0.1-rc.7, Kit 110.1.2, Python 3.12.13
- Extension: `twinpulse.extension-0.1.0` visible-scene revision

## 1. 구현 결과

새 Git 저장소를 `main` branch로 초기화했다. 아직 commit은 만들지 않았다.

구현된 범위:

- Isaac 의존성이 없는 `twinpulse_core` package.
- versioned `SceneSpec`, `RobotProfile`, `TaskSpec`, `SpecBundle`과 JSON round-trip.
- 유한값·양수 치수·ID/참조·asset/operation allowlist·장면 크기 상한 검증.
- 바닥, 벽 2개, rack 2개, box와 procedural differential-drive AGV로 구성된 고정 3D fixture.
- `/World/TwinPulse`만 소유하는 scene compiler. 기존 사용자 scene 전체를 삭제하지 않음.
- `Build Scene`, `Focus Scene`, `Run / Resume`, `Pause`, `Reset`이 있는 **TwinPulse Playground** 창.
- pose teleport가 아닌 RevoluteJoint wheel drive와 PhysX 기반 주행.
- timeline reset으로 active articulation을 삭제하지 않는 lifecycle 처리.
- core 단위시험과 유한 Isaac runtime acceptance script.

LLM, 이미지 입력, ROS2, Isaac Lab, cloud, 실물 AGV는 이번 단계에 포함하지 않았다.

## 2. 검증 결과

### M1-A core

```text
C:\isaacsim\python.bat -m unittest discover -s packages\twinpulse_core\tests -v
```

10개 시험 PASS. 정상 fixture/JSON round-trip과 음수 치수, NaN, ID 중복, 잘못된 robot reference, 허용되지 않은 asset/operation, object 상한, dynamic mass 누락을 확인했다. 새 package를 설치하지 않았다.

### M1-B runtime

```text
C:\isaacsim\python.bat scripts\verify_m1_extension.py
```

최종 결과: `TWINPULSE_M1_RESULT.status=PASS`.

| 항목 | 결과 |
|---|---|
| Extension enable/disable | 3/3 PASS |
| shutdown 후 physics subscription | 3회 모두 inactive |
| 반복 compile prim 수 | 매 회 22 → 22, 중복 없음 |
| run/pause/reset | 3/3 PASS |
| planar 이동 | 매 회 0.095361m |
| planar 목표 오차 | 매 회 0.024651m, 허용 0.025m |
| pause drift | 0m |
| reset 위치 오차 | 0m |
| 바닥 접촉 높이 | 0.211652m, 설정 범위 통과 |
| PhysX/CUDA/device-loss/non-uniform-scale 오류 | 최종 로그에서 없음 |

증거 로그:

`C:\isaacsim\kit\logs\Kit\Isaac-Sim Python\6.0\kit_20260912_233617.log`

## 3. 제한 및 관찰 경고

- 이 PC는 여전히 bundled checker의 VRAM/RAM 최소치에 미달한다. M1-B PASS는 headless MinimalRendering, CPU PhysX, 작은 fixture 조건이다.
- 로컬 Kit registry가 온라인 index를 동기화하려다 연결 오류 2건을 기록했다. 필요한 Extension dependency는 로컬에서 로드됐고 TwinPulse acceptance는 모두 통과했다.
- headless harness의 첫 immediate disable에서 Python 검증 frame이 Extension 객체를 잠시 참조한다는 warning이 1건 발생했다. 실제 `on_shutdown`, UI window destroy, physics subscription 해제는 완료됐다. visible interactive UI unload는 별도 시각 검증 권고 항목이다.
- M1 planner는 고정 +X smoke route만 처리한다. 장애물 회피나 임의 목표 planner가 아니다.
- 고정 fixture가 이미 존재하면 Build는 안전한 no-op이다. 알 수 없는 `/World/TwinPulse` 내용은 삭제하지 않고 중단한다.

## 4. 실행 방법

```powershell
Set-Location C:\Users\jaewo\Documents\Codex\TwinPulse
.\scripts\launch_twinpulse.ps1
```

직접 실행:

```powershell
C:\isaacsim\isaac-sim.bat --ext-folder C:\Users\jaewo\Documents\Codex\TwinPulse\extensions --enable twinpulse.extension
```

Isaac Sim에서 **TwinPulse Playground** 창이 열리면 `Build Scene`을 누른 직후 warehouse와 초록 목표 마커가 보여야 한다. 필요하면 `Focus Scene`으로 overview camera를 복구한 뒤 `Run / Resume`를 사용한다.

## 5. 0.1.0 visible-scene 보정

사용자가 2026-09-13 제공한 화면에서 Build 후 `/World/TwinPulse` prim과 `Ready - 22 TwinPulse prims`는 생성됐지만 viewport가 계속 검었고, Run 중 Windows가 일시적으로 `응답 없음`을 표시했다. 원인은 0.1.0 compiler에 camera/light가 없고 Build가 viewport를 scene에 맞추지 않았으며, 기존 목표가 0.12m라 화면이 있더라도 이동을 알아보기 어려웠던 데 있다.

visible-scene revision은 TwinPulse-owned overview camera, dome/sun light, 초록 goal marker, Build 자동 focus와 수동 `Focus Scene`, 1.5m route를 추가했다. UI 버튼은 상태 문구를 먼저 그린 다음 무거운 Build/Run/Reset 작업을 시작하도록 한 프레임 양보한다. 알 수 없는 사용자 prim은 계속 건드리지 않는다. manifest를 0.1.1로 올리자 기존 Isaac enable list가 정확히 0.1.0을 요구해 dependency resolution이 실패했으므로, 사용자 설정을 수정하지 않고 package version만 0.1.0으로 복귀했다. Codex가 시작한 Full 앱은 프로세스가 응답했지만 사용자 Alt+Tab에 없는 백그라운드 세션이어서 종료했다.

보정 후 core 시험 10개와 Python 문법 검사는 PASS했다. headless functional run은 camera/dome/sun/goal 모두 true, prim 28→28, 주행 1.454589m, 목표 오차 0.049747m, pause/reset 오차 0m의 PASS 결과를 출력했다. 사용자의 후속 화면으로 초기 scene이 실제 렌더링됐음도 확인했다. 별도 headless RTX capture는 이 8GB host에서 `--no-window` 프레임 완료가 정지해 acceptance 근거에서 제외하고 검증 스크립트도 제거했다. fresh Full-app 수동 확인은 남아 있다.

## 6. Interactive visual acceptance

2026-09-13 사용자가 자신의 PowerShell에서 launch script를 실행하고 다음 화면을 제공했다.

- Build: `Ready - 28 TwinPulse prims`, overview camera와 조명된 warehouse/AGV/초록 goal marker 표시.
- Focus: `Scene focused`와 안정된 overview 구도 확인.
- Run: AGV 위치 이동과 `Running - remaining 0.929 m` 확인.
- Reset: `Reset complete`와 AGV 시작 위치 복귀 확인.
- Runtime: 관찰 화면 43~74 FPS, 프로세스 응답 상태. 콘솔에 `twinpulse.extension-0.1.0 startup`, `Isaac Sim Full App is loaded`, `app ready`가 표시됐다.

cache server 설정 없음과 Fabric interface version 가능성은 warning이며 이번 실행의 Build/physics/UI 동작을 중단하지 않았다. 따라서 M1 interactive visual acceptance를 PASS로 판정한다.

## 7. 다음 단계

M2-A의 이미지+자연어 provider contract와 mock/error handling 구현으로 이동한다.
