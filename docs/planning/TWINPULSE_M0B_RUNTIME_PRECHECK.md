# TwinPulse M0-B — Isaac Sim 6.0.1 설치 및 Runtime Precheck

- 수행일: **2026-09-12 (KST)**
- 연결 기준: **Baseline v1.0.4**
- 실행 host: `DESKTOP-511RPFE`
- 단계 / 상태: **PASS (제한 조건부) — 설치·Full 앱 부팅·최소 physics/AGV acceptance 통과**
- 범위: Isaac Sim 5.1.0을 6.0.1 standalone으로 교체하고 Extension 개발에 필요한 runtime을 사전 검증

## 1. 결론

`C:\isaacsim`의 활성 설치는 Isaac Sim 6.0.1로 교체됐다. 공식 Windows standalone ZIP의 MD5를 검증했고, 설치 파일의 VERSION·Kit·Python을 확인했다. compatibility checker와 Full 앱이 실제로 실행됐으며, Full 앱은 무창 모드에서 PhysX와 wheeled robot 관련 Extension을 포함해 부팅한 뒤 2분 이상 유지됐다.

그러나 이 PC의 RTX 2070 Max-Q 8GB와 RAM 16GB는 6.0.1 내장 compatibility checker의 최소치인 VRAM 10GB와 RAM 32GB보다 작다. checker의 최종 결과는 `FAILED`다. 따라서 설치·부팅 성공을 권장 사양 충족이나 복잡한 TwinPulse scene의 안정성 보장으로 해석하지 않는다.

외부 자산에 의존하지 않는 procedural differential-drive fixture로 중력·접촉, 직진·회전, pause/resume/reset을 3회 반복했고 모두 통과했다. 각 실행에서 직진 0.078613m, 회전 0.692385rad, pause drift 0m, reset 위치·yaw 오차 0을 기록했으며 최신 로그에 PhysX/CUDA fatal 또는 non-uniform scale 오류가 없었다. 따라서 M0-B는 **작은 scene·CPU physics·MinimalRendering 조건에서 PASS**다. 이는 복잡한 이미지 기반 scene이나 RTX rendering의 안정성을 보장하지 않는다. 제품 코드, ROS2, Isaac Lab은 만들거나 설치하지 않았다.

## 2. 설치 결과

| 항목 | 확인값 | 상태 |
|---|---|---|
| 활성 설치 root | `C:\isaacsim` | PASS |
| Isaac VERSION | `6.0.1-rc.7+release.42383.32955d8d.gl` | PASS |
| Kit core | `110.1.2+production.326809.f9bf0dda.gl` | PASS |
| bundled Python | 3.12.13 | PASS |
| 다운로드 파일 | `isaac-sim-standalone-6.0.1-windows-x86_64.zip` | PASS |
| 다운로드 크기 | 10,600,096,696 bytes | PASS |
| MD5 | `c7fa3a830b251f10305cd7883039df9b` | 공식값과 일치 |
| `extension_examples` | 기존 symlink의 대상이 새 6.0.1 경로에서 존재 | 기능상 확인 |
| 공식 설치 ZIP | 작업 폴더에 보존 | 재설치용 |

`post_install.bat`은 기존 `extension_examples` symlink를 제거하지 못해 재생성 경고를 냈다. 하지만 남아 있던 링크의 상대 대상 `exts\isaacsim.examples.interactive\isaacsim\examples\interactive`가 새 설치에서도 존재함을 확인했다. 배치의 exit code 0만으로 성공 처리하지 않고 이 경고를 기록한다.

## 3. 기존 5.1 처리 상태

- `C:\isaacsim`에는 5.1 활성 설치가 남아 있지 않으며 6.0.1이 배치돼 있다.
- 교체 중 안전을 위해 5.1 파일을 아래 작업 폴더로 먼저 이동했다.
  - `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\work\isaacsim-5.1-backup`
  - 확인 VERSION: `5.1.0-rc.19+release.26219.9c81211b.gl`
- 직접 재귀 삭제는 실행 전에 샌드박스 정책이 차단했고, Windows 휴지통 이동도 unauthorized로 실패했다. 두 시도에서 해당 백업은 삭제되지 않았다.
- 따라서 사용자 요청의 **활성 설치 교체는 완료**됐지만, 약 21.85GiB의 안전 백업 정리는 남아 있다. 우회 삭제하지 않는다.

## 4. Compatibility checker

실행:

```text
C:\isaacsim\isaac-sim.compatibility_check.bat --no-window --/app/quitAfter=30
```

| 검사 | 결과 |
|---|---|
| NVIDIA driver 592.82 | supported, minimum 537.58 |
| RTX 2070 Max-Q | supported |
| VRAM | 8.59GB, minimum 10GB — **not enough** |
| CPU | supported, 12 logical cores — good |
| RAM | 16.94GB, minimum 32GB — **not enough** |
| storage | 당시 51.24GB available, minimum 50GB — enough, more recommended |
| Windows 10 Pro 22H2 | bundled checker에서는 supported |
| 최종 결과 | **FAILED** |

이 결과에는 문서와 실행 checker의 차이가 있다. 앞선 공식 요구사항 조사에서는 Windows 11과 더 높은 GPU 권장/최소 구성이 제시됐지만, 실제 6.0.1 bundled checker는 Windows 10을 supported로 판정하고 VRAM 최소치를 10GB로 표시했다. 현재 PC는 어느 해석에서도 RAM이 부족하고 checker VRAM 최소치에도 미달하므로 권장 runtime host로 승격하지 않는다.

## 5. Full 앱 부팅 smoke

실행:

```text
C:\isaacsim\isaac-sim.bat --no-window --no-ros-env --/app/quitAfter=75
```

확인 사항:

- `Isaac Sim Full Version: 6.0.1-rc.7`
- PhysX 110.1.13 및 `isaacsim.robot.wheeled_robots` 로드
- 캐시가 생성된 두 번째 실행에서 Full 앱 초기 Extension 로딩 약 21초
- 2분 이상 프로세스 유지, OOM·GPU device loss·PhysX/CUDA fatal 오류 없음
- `quitAfter`가 Full 앱을 자동 종료하지 않아 검증 후 Ctrl+C로 중단했다. 이 때문에 shell 종료 코드는 1이지만 crash에 의한 종료가 아니다.
- 선택적 Behavior 녹화 폴더 `C:\Users\jaewo\Documents\NVIDIA\...` 생성 권한 오류 1건이 남았다. TwinPulse 핵심 physics 부팅 오류로 판정하지 않되, 해당 기능을 사용할 때 재검증한다.

증거 로그:

`C:\Users\jaewo\.nvidia-omniverse\logs\Kit\Isaac-Sim Full\6.0\kit_20260912_223537.log`

## 6. M0-B physics/AGV 시험

### 시도 1 — 공식 Jetbot

작업 폴더의 `work/twinpulse_m0b_smoke.py`에서 공식 6.0.1 wheeled robot API를 사용해 유한 3회 시험을 준비했다. 그러나 `get_assets_root_path()`가 다음 자산 root에 연결하지 못해 robot 생성 전에 종료됐다.

```text
https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0
```

이 실패는 본체 ZIP 누락이 아니다. standalone 본체와 별도의 원격/로컬 Isaac 자산 가용성 문제다.

### 시도 2 — 설치본 포함 local URDF

설치본에 포함된 아래 primitive differential-drive URDF를 발견했다.

```text
C:\isaacsim\exts\isaacsim.asset.importer.urdf\data\urdf\tests\differential_base.urdf
```

공식 `URDFImporter` 3.11.2가 실행되고 app ready까지 도달했지만, importer가 내부 임시 `.usdc` 파일을 만들 때 샌드박스 권한 오류가 발생했다. 사용자 Temp와 작업 폴더 Temp를 각각 시도했으나 같은 유형으로 실패했다. 시스템 ACL이나 보안 설정을 변경해 우회하지 않았다.

### 현재 판정

| M0-B 하위 항목 | 상태 |
|---|---|
| 6.0.1 build/Kit/Python inventory | PASS |
| Full 앱 및 PhysX Extension 부팅 | PASS |
| 최소 3D scene | PASS — ground, chassis, two wheels, revolute joints를 runtime stage에 생성 |
| wheeled robot 생성 | PASS — 외부 asset 없는 M0-B procedural fixture |
| 중력·접촉 | PASS — 주행 후 높이 0.177699m, 바닥 이탈 없음 |
| 직진·회전 | PASS — 3회 모두 0.078613m / 0.692385rad |
| pause/resume/reset 3회 | PASS — pause drift 0m, reset 위치·yaw 오차 0 |
| PhysX/CUDA 오류 없는 실제 주행 구간 | PASS — 최신 smoke 로그에서 관련 오류 없음 |

### 시도 3 — 외부 asset 없는 procedural fixture

공식 6.0.1 `SimulationApp`, `WheeledRobot`, `DifferentialController`, USD/PhysX API로 바닥·차체·두 구동 바퀴와 joint를 메모리 stage에 구성했다. `MinimalRendering`, CPU physics, 60Hz에서 유한 시험을 수행했다. 자산 다운로드 실패나 URDF importer 임시파일 권한과 분리된 runtime 검증이다.

| 실행 | 직진 | 회전 | pause drift | reset 위치/yaw | 결과 |
|---|---:|---:|---:|---:|---|
| 1 | 0.078613m | 0.692385rad | 0m | 0m / 0rad | PASS |
| 2 | 0.078613m | 0.692385rad | 0m | 0m / 0rad | PASS |
| 3 | 0.078613m | 0.692385rad | 0m | 0m / 0rad | PASS |

판정 기준은 직진 >0.05m, 회전 >0.10rad, pause drift <0.001m, reset 위치 오차 <0.02m, reset yaw 오차 <0.05rad, 주행 후 높이 0~0.20m다. 모든 check가 3회 연속 통과했다.

증거 로그:

`C:\isaacsim\kit\logs\Kit\Isaac-Sim Python\6.0\kit_20260912_230117.log`

따라서 **M0-B는 제한 조건부 PASS**다. 공식 predefined asset 선택과 실제 Extension lifecycle 검증은 M1-B 범위에서 별도로 수행한다.

## 7. 권한 및 경로 결정

사용자는 기존 설치 root인 `C:\isaacsim` 하위는 TwinPulse 관련 작업에 자유롭게 사용해도 된다고 승인했다. 새 `C:\Isaac` 경로를 만들라는 뜻이 아니며, 해당 경로는 생성하지 않았다. 향후 runtime assets와 scratch는 vendor 파일과 구분되는 `C:\isaacsim\twinpulse_work` 아래로 모아 AppData 경로별 요청을 줄인다.

시스템 파일, driver, OS, WSL, Docker, 방화벽 및 `C:\isaacsim` 밖의 새로운 지속 변경은 계속 별도 승인 경계다. 이미 승인된 프로젝트 출력 문서 갱신은 기존 작업 범위에 포함된다. 이번 과정에서 시스템 설정은 변경하지 않았다.

## 8. 다음 단계

1. 5.1 안전 백업을 보존할 필요가 없으면 사용자가 일반 Windows 세션에서 정확한 폴더만 삭제해 약 21.85GiB를 회수한다. 자동 삭제는 정책 차단 때문에 미완료다.
2. 다음 구현은 승인된 제품 root에서 M1-A core/schema/repository를 시작한다.
3. M1-B에서 실제 Extension enable/disable/reload와 선정한 predefined AGV를 6.0.1 runtime으로 검증한다.
4. 하드웨어 checker FAIL을 유지한 채 이 PC에서는 작은 scene과 MinimalRendering 중심으로 개발하고, 이미지 기반 복잡 scene과 최종 acceptance는 RT GPU 서버에서 재검증한다.
