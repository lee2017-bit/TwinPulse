# TurtleBot3 Burger RPi4 4 GB — 단계별 실험·TwinPulse 연결 계획

- 작성일: 2026-09-22 / 상태: **계획만 작성, 실물 미점검·미구동**.
- 확정 사실: 사용자가 TurtleBot3 Burger, Raspberry Pi 4 4 GB 구성을 구매해 받았다.
- 미확인: 조립 상태, LDS 모델, OpenCR/펌웨어, microSD OS/ROS, 배터리, 실제 치수/센서 frame, 네트워크.
- 연결: [종합 검토](TWINPULSE_ASTRA_REVIEW_2026-09-22.md), [Sol 공통 규칙·체크포인트](TWINPULSE_SOL_EXECUTION_PLAN_2026-09-22.md).
- 승인 경계: 이 문서를 읽었다고 SD 초기화·OS/ROS/펌웨어 설치·방화벽 변경·모터 명령을 실행하지 않는다. 사용자가 선택한 B 단계 및 해당 실물 시험만 수행한다.

## 1. 실험 목적과 범위

목표는 “로봇이 한 번 움직인다”가 아니라 다음 연결을 증명하는 것이다.

1. 실제 기체가 공식 소프트웨어로 재현 가능하게 작동한다.
2. 센서/좌표/시간과 정지 동작을 확인한다.
3. TwinPulse가 만든 환경과 실제 트랙의 차이를 측정한다.
4. 측정한 위치/장애물 보정을 3D에 적용해 동일 mission을 재검증한다.
5. 승인된 저속 실물 mission 결과를 sim과 비교한다.

초기에는 한 대, 평평한 제한 구역, 성인 운영자 입회, 저속 주행만 다룬다. 실물 자동 학습, unattended 주행, cloud에서 motor 직접 제어, 계단/공공장소/사람 사이 주행은 제외한다. 산업 안전 인증 시험이 아니다.

**2WD 선택은 유지한다.** 실물에 맞춘 좌·우 구동륜+실제 passive support 모델이 필요하다. generic `agv_compact_2wd_caster_v2`를 이름만 Burger로 바꾸지 않는다. 기구/센서/제어 정확성은 별도 gate다.

## 2. 권장 호스트 구성

| 호스트 | 책임 | 하지 않을 일 |
|---|---|---|
| Raspberry Pi 4 4 GB | OpenCR/LiDAR/IMU/odom driver, 현장 command arbitration·watchdog, 최소 telemetry | full Isaac, 대형 LLM, 대규모 학습 |
| Linux 원격 PC(우선 검토) | ROS2/Nav2/SLAM/RViz/rosbag, mission adapter, 분석 | 첫날부터 TwinPulse와 모든 서비스를 한꺼번에 연결 |
| 현재 Windows PC | 기존 React/Python/Isaac 개발·회귀·보고서 | 기존 Isaac 환경에 임의 ROS/Python DLL 혼합 |
| Nebius | 승인된 모델 추론, RT GPU Isaac batch 평가 | WAN 연결에 의존하는 실물 정지/모터 제어 |

Pi에서 Nav2까지 가능한지는 센서 rate/CPU/RAM/열/네트워크를 측정해 결정한다. 4 GB라는 이유로 불가능하다고 단정하지도, 모든 계산을 올리지도 않는다. 초기 분리는 문제를 좁히기 위한 권고다.

새로 설치한다면 Ubuntu 24.04+ROS2 Jazzy 조합을 우선 검토한다. ROBOTIS SBC 문서는 RPi4에 Ubuntu Server 24.04 계열 64-bit를 안내한다. 기존에 안정적인 Ubuntu22.04/Humble 구성이 있으면 자동 초기화하지 않고 보존/지원 조합을 판단한다. [ROBOTIS SBC setup](https://emanual.robotis.com/docs/en/platform/turtlebot3/sbc_setup/)

현재 Windows10/Isaac6.0.1 설치에서 ROS bridge 호환을 검증한 적은 없다. NVIDIA 6.0 계열 자료를 6.0.1의 특정 host에 그대로 적용하지 않는다. OS/ROS/Python/RMW를 일치시킨 Linux sim/ROS host를 검토하고, 추가 PC·WSL·container 도입은 사용자의 승인 후 정한다. [NVIDIA ROS 설치 안내(6.0.0 참고)](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_ros.html)

## 3. 공통 안전·실험 계약

### 운영자와 장치

- 사람/동물/전선/가구 모서리/낙하 위험을 제거한 바닥에서 시험한다. 로봇을 일반 책상 위에서 주행시키지 않는다.
- 첫 motor 확인은 제조사 지침을 따른 안정적인 지지대에서 구동륜을 지면과 분리한 짧은 시험 또는 충분히 비운 바닥에서 수행한다. 돌아가는 바퀴를 손으로 잡지 않는다.
- 접근 가능한 물리 전원 차단 방법을 B0에서 확인한다. 키보드 Ctrl+C, browser Pause, Wi-Fi는 독립적인 비상정지 수단으로 간주하지 않는다. 일반 전원 스위치도 인증된 E-stop이라고 부르지 않는다.
- 충전/배선/펌웨어는 정확한 모델의 제조사 절차를 따른다. 배터리 전압/극성/커넥터를 추정하지 않는다.
- 원격 작업자는 케이블/조립/배터리 상태를 스스로 확인할 수 없다. 현장 운영자의 확인 없는 모터 활성화 금지.

### 제어 소유권과 정지

```text
Teleop 또는 Nav2 또는 승인된 mission (한 번에 하나)
  → command selector / lease
  → 로봇 근처 safety supervisor (속도·freshness·영역·정지 latch)
  → 실제 driver/OpenCR

LLM → 고수준 goal/parameter 제안 → 검증·승인
Replay / LiveObserve → read-only; real command sink 없음
```

- 두 publisher가 같은 motor topic에 동시에 쓰지 않게 한다. source 바뀔 때 우선 stop, 이전 lease 무효화 후 새 source를 승인한다.
- 통신 끊김/오래된 sensor/TF 불능/프로세스 종료 시 정지. 재연결만으로 이전 goal을 자동 재개하지 않는다.
- Pi supervisor가 죽었을 때의 lower-level driver/firmware timeout도 확인한다. supervisor 하나만 살아 있다고 전체 안전이 보장되지 않는다.
- Nav2 Collision Monitor는 추가 보호 계층으로 검토하되 hard real-time 안전 인증의 대체물이 아니다. [Nav2 Jazzy Collision Monitor](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/)

### 최초 시험용 제안값 — 실측 전 확정 사양 아님

| 항목 | 시작 제안 | gate |
|---|---|---|
| 직진 속도 | 0.05 m/s | 정지/방향 확인 후 최대 0.10 m/s 범위 재승인 |
| 회전 속도 | 0.3 rad/s 이하 | footprint/측정 오차/지지 안정성 확인 |
| command freshness | 0.3~0.5초 후보 | driver 주기·네트워크 지연·실측 정지 거리로 확정 |
| 첫 이동 | 0.2~0.5m 짧은 직진 | 장소 여유/정지 범위 확인 후 확대 |
| 물리 반복 | 각 조건 3~5회 | 한 번 PASS로 안정성 완료 선언 금지 |
| 첫 goal 허용 오차 | 위치 0.10m 후보 | localization/트랙 크기 기준으로 기록 후 확정 |

속도 상한/가속도/stop 영역은 LLM이나 optimizer가 완화할 수 없다. 필요한 여유는 footprint에 위치 오차, 센서 사각, `v × latency + 제동거리`를 더해 실제로 정한다. 약 2m×2m 트랙과 0.5m 벽은 사용자의 구상이지 확정 치수다. 좁아서 회전/안전 정지가 안 되면 트랙을 넓히거나 속도를 낮추고 시험을 중단한다.

### 데이터/시간/좌표

- `map → odom → base_footprint/base_link → 실제 lidar frame`의 TF 연결 및 각 transform publisher를 기록한다. 이름은 실제 driver를 확인한다.
- map 좌표를 Isaac world로 옮기는 SE(2) transform/units/yaw convention을 artifact에 고정. 단순 x/y swap이나 degree/radian 혼용 금지.
- 실물 `use_sim_time=false`, sim은 `/clock`과 `use_sim_time=true`. bag replay는 별도 ROS domain/namespace에서 sim-time 소비자만 연결한다.
- ROS_DOMAIN_ID는 통신 격리에 도움을 주지만 인증/보안 경계가 아니다. 공유 회사 네트워크나 인터넷에 DDS를 임의 공개하지 않는다.
- topic type/QoS/rate/frame_id/stamp age를 확인한다. `ros2 topic hz`가 출력된다는 사실만으로 데이터가 fresh라고 하지 않는다.
- Jazzy TurtleBot3 bringup은 `TwistStamped` 사용을 안내한다. 설치 버전에서 `/cmd_vel` 실제 type을 조회하고 teleop/Nav2/supervisor/driver 전체를 맞춘다. 꼭 Twist가 필요하면 지원 parameter를 확인해 전체 경로를 명시적으로 맞춘다. [ROBOTIS bringup](https://emanual.robotis.com/docs/en/platform/turtlebot3/bringup/)

## B0 — 무구동 inventory와 작업환경 결정

**사용자 확인 필요:** 실물 사진/제품 라벨, 조립 상태, microSD 준비 상태, Linux PC 유무, 시험 공간과 물리 전원 차단 방법. 사진에 Wi-Fi 비밀번호/계정 정보는 포함하지 않는다.

**Sol 작업:**

1. `docs/hardware/turtlebot3-burger-inventory.md`(향후 생성)에 부품/serial은 필요한 최소만, LDS-01/02/03, OpenCR 모델, Pi RAM, 배터리/충전기, OS, firmware, accessory, 측정 상태를 표로 작성.
2. 이미 접근 가능한 Pi에서 아래 read-only 명령으로 OS/메모리/USB/장치 경로를 확인. 새 SSH 연결/설치는 별도 승인 후. 비밀 env 전체 dump 금지.

```bash
# Pi: 이미 로그인/접근 승인이 된 경우만; 모터 명령 아님
cat /etc/os-release
uname -m
free -h
df -h
lsusb
ls -l /dev/serial/by-id
```

3. 기존 SD를 덮어쓸 이유/backup/복구 계획 없이 초기화하지 않음. 새 환경이면 정확한 OS image/ROS distro/source commit/설치 위치/예상 용량을 제안.
4. ROS host 배치를 정하고 사용자에게 설치 승인 요청. Pi4에 Jetson 전용 패키지를 설치하지 않음.

**PASS:** inventory unknown이 숨겨지지 않음, 맞는 설치 runbook 후보, 현장 정지 수단/제한 구역 확인. **아직 motor NO-GO.**

## B1 — 버전 고정 설치와 무구동 bringup

**선행:** B0 + 대상별 설치/flash 승인. **산출물:** `host_versions.json`, 설치 log/rollback, 패키지 및 firmware 버전.

- 공식 ROBOTIS 문서에서 **선택한 ROS 탭**을 사용한다. 한 페이지에 ROS1/Humble/Jazzy 예제가 함께 있으므로 `roslaunch`와 `ros2 launch`를 섞지 않는다. 실행 전에 명령을 선택한 버전에 맞게 별도 runbook에 고정한다.
- OpenCR update는 정확한 Burger firmware/배포판 확인 후, 필요한 경우에만 한다. [ROBOTIS OpenCR setup](https://emanual.robotis.com/docs/en/platform/turtlebot3/opencr_setup/)
- 원격 PC/SBC 동일 ROS distribution, 적절한 RMW, 격리 domain, 실제 LDS_MODEL을 맞춘다. 상시 방화벽 끄기를 진단 해결책으로 사용하지 않는다.
- 설치 시간이 길면 제조사 전원 지침을 따라 안정적인 전원을 사용한다. 작업 중 연결 상실/전원 중단 시 재flash부터 반복하지 말고 마지막 완료 단계를 확인한다.
- bringup launch 파일과 기본 동작을 읽어 시작 시 motor 명령이 없는지 확인하고 주변을 비운다. 기존 teleop/Nav2 source는 실행하지 않은 상태다.

```bash
# Pi, 선택된 환경 source가 끝난 뒤. B1 현장 확인 이후에만 실행.
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_bringup robot.launch.py
```

**PASS:** 재부팅/재연결 뒤 무구동 bringup 2회, driver 장치/센서 정상, motor 명령 source 0, 즉시 fatal 없음. `cmd_vel`이 없으면 무조건 로봇을 움직여 확인하지 않는다.

## B2 — 정지 상태 telemetry·TF·timeout 확인

**선행:** B1. 바퀴는 아직 주행하지 않음. **수집:** 120초 정지 telemetry, ROS graph, 버전, topic manifest.

```bash
# ROS 원격 PC: 실제 존재하는 topic/frame을 먼저 조회
ros2 node list
ros2 topic list -t
ros2 topic info /cmd_vel -v
ros2 topic info /scan -v
ros2 topic info /odom -v
ros2 topic echo /scan --once
ros2 topic echo /odom --once
```

- topic/frame/QoS 이름이 다르면 inventory/runbook에 반영하고 다음 명령을 고친다. `/imu`, `/joint_states`, `/battery_state` 존재를 가정하지 않는다.
- `/scan`, `/odom`, TF와 가능하면 IMU/battery를 고유 run 폴더에 rosbag으로 기록. `topic hz`와 TF 관찰은 supervisor가 20~30초 유한 실행하고 종료한다.
- scan이 실제 벽 방향/거리와 맞는지 자/줄자로 측정한 2~3개 위치와 비교한다. footprint 안 phantom obstacle, TF jump, invalid range 비율을 기록.
- Pi/원격 PC time skew, sensor stamp age distribution, Wi-Fi drop을 확인. 임의 최대 latency 기준을 정답으로 쓰지 말고 B3 안전 예산과 비교한다.
- motor 입력 경로에서 deadman/command timeout/driver watchdog이 어디 있는지 코드를 확인한다. command가 끊겼을 때 정지를 실제로 보장하는지는 B3에서 별도 시험.

**PASS:** 정지 상태 TF 연결·sensor data가 안정, expected publisher 수 확인, timestamp freshness 정책 및 command gating 설계 준비. **동작 시험 전 운영자 재확인.**

## B3 — 보호된 수동 제어와 정지 시험

**선행:** B2, 속도/영역/정지 수단/현장 운영자의 **이번 구동 승인**.

1. teleop/default motor command를 supervisor 아래로 연결한다. 낮은 속도 상한이 실제 publish 값과 driver 입력에서 적용되는지 확인.
2. 아주 짧은 forward/stop/left/right/stop. 바퀴 회전 방향과 odom yaw 부호가 맞는지 확인한다. 정해진 동작 중 nose-dive/쏠림/바닥 끌림이 있으면 profile tuning 이전에 기구/조립부터 점검.
3. 운영자 시야에서 명령 source 종료, 통신 상실, supervisor 종료 시 정지를 각각 검증한다. 제일 위험한 전체 연결 상실 시험은 낮은 속도/충분한 여유/즉시 물리 차단 조건에서만 한다.
4. latency(마지막 유효 명령→stop 요청)와 실제 정지까지 거리/시간을 별도로 측정한다. driver timeout 문서만으로 physical stop PASS 하지 않음.
5. 정지 후 연결 복구 시 자동 출발하지 않음을 확인. resume는 새 운영자 명령.

공식 teleop는 시작점으로 참고하되, stock 키보드 UI 자체가 요구하는 deadman/timeout을 만족한다고 가정하지 않는다. [ROBOTIS teleoperation](https://emanual.robotis.com/docs/en/platform/turtlebot3/teleoperation/)

**PASS:** 방향/제한 속도/정지 3~5회 재현, 불시 command source 없음, measured stop envelope가 시험 구역 안에 들어옴. 하나라도 실패하면 B4 이후 금지.

## B4 — TwinPulse 없이 SLAM·Nav2 기준선

**목적:** 로봇/ROS 문제를 LLM·Isaac 문제와 분리한다.

1. 빈 통로/직각 코너/한 장애물을 가진 실측 트랙을 만든다. 반사/투명체를 초기 장애물로 쓰지 않고 LiDAR 스캔 높이를 가로지르는 안정적인 물체를 선택한다.
2. 자/줄자로 벽/장애물 위치, 통로 폭, 측정 불확실도를 기록. 위치 표시와 origin 기준점을 둔다.
3. 선택한 ROS 버전의 공식 SLAM 절차로 저속 mapping. map 저장 후 새 session에서 localization 복원. 공식 예시는 [ROBOTIS SLAM](https://emanual.robotis.com/docs/en/platform/turtlebot3/slam/) 참조.
4. raw map와 yaml(해상도/origin 포함), bag, transform/config/패키지 version, 시작 위치를 묶어 hash. 수동 편집본은 새 revision.
5. 공식 Nav2 launch/parameter를 기준으로 같은 3개 목적지(직진·90도 회전·장애물 우회)를 각각 3회 제안. robot footprint/센서/속도/명령 타입을 실제에 맞춘다. [ROBOTIS navigation](https://emanual.robotis.com/docs/en/platform/turtlebot3/navigation/)
6. map/goal/현재 위치를 RViz에서 먼저 확인. 매 goal마다 현장 승인. 운행 중 사람이 손으로 장애물을 갑자기 넣는 시험은 하지 않음.

**PASS:** 로봇 baseline 성공/실패/개입/시간/거리/최소 여유/goal 오차를 기록하고, 재시작 후 반복 가능한 map/config가 있음. 실패를 숨기기 위해 미리 정한 경로만 원격 teleop로 따라가지 않음.

## B5 — TurtleBot-specific Isaac 모델

**선행:** B0 inventory, S4 scene/mission 분리. ROS 설치와 별개로 profile 준비는 가능. 실물 구동 없음.

- 실제 Burger revision에 맞는 공식 URDF/xacro/mesh에서 시작하고 source commit/license를 기록한다. 모델 자산 출처는 [ROBOTIS 기능/기종 안내](https://emanual.robotis.com/docs/en/platform/turtlebot3/features/)와 공식 저장소로 추적.
- wheel joint name/axis/sign, radius/separation, passive support, body collision, footprint, LiDAR pose, IMU pose, mass/inertia를 각각 점검한다. URDF의 visual을 collider와 혼동하지 않음.
- import default unit/scale/Z-up/heading/joint drive/solver/contact를 기록. profile ID 예: `turtlebot3_burger_<hardware-revision>_v1`; generic profile을 덮어쓰지 않음.
- 정지 settle, 짧은 직진, ±90도 회전, pause/reset/rebuild, floor contact/roll/pitch/z/collision/odom 부호 시험.
- 실제 B3 이동량과 sim 이동량을 비교하되 하나의 숫자에 맞추기 위해 기하/마찰/관성을 동시에 임의 변경하지 않음. 소스 nominal값과 실측 correction을 구분한다.

**PASS:** 물리적으로 지지되고, 명령 방향/센서 frame이 일치하며, profile+import config+테스트 evidence 재생 가능. 아직 완전한 동역학 twin이라고 주장하지 않음.

## B6 — 동일 Nav2를 Isaac 센서와 연결

**선행:** B4 baseline, B5 model, ROS/Isaac host 설치 승인 및 호환 smoke.

- 별도 sim domain/namespace에서 `/clock`, scan, odom, TF를 제공. 같은 transform을 Isaac과 robot_state_publisher가 이중 발행하지 않음.
- real driver namespace를 연결하지 않은 상태에서 Nav2 goal→sim command→virtual sensor 피드백을 확인한다. native mock teleport가 아닌 physics 동작을 확인.
- 실물과 가능한 한 같은 Nav2/controller/config를 사용하되 sim-time/driver remap 등 필요한 차이를 명시한다.
- 직진/좌·우회전/우회/막힌 goal/센서 stale/TF 끊김/clock pause/Reset 시험. unsupported goal은 안전하게 실패.
- ROS `/cmd_vel` type이 다르면 명시적인 검증된 adapter만 사용. 자동 guessing으로 type 변환하지 않음.

**PASS:** 동일 mission이 sim에서 동작, clock/TF 정합, stop/failure 관찰, real publisher 0. 기존 +X controller PASS를 이 단계의 대체로 쓰지 않음.

## B7 — 실물 관측·스캔 보정·shadow (motor 권한 없음)

**선행:** B2 이상 telemetry, S5a/b. **목적:** 로봇의 상태를 TwinPulse에 읽기 전용으로 연결한다.

1. 자체 촬영 사진/치수 도면에서 만든 3D scene를 불확실성 표시와 함께 보존한다. 원본 추정본은 수정 전 revision으로 남김.
2. robot map의 실측 기준점 3개 이상(비일직선)과 Isaac 좌표를 대응시켜 SE(2) 정합을 계산하고 residual을 기록. scan geometry의 대칭/모호함을 경고.
3. 2D scan으로 벽/장애물 XY를 보정 제안. 높이는 사용자/도면의 출처를 유지한다. scan으로 보이지 않는 부분은 측정됐다고 하지 않음.
4. 사용자 검토 후 위치 diff를 apply, scene/map revision 증가, 기존 mission run/배포 artifact invalidation, sim 재검증.
5. LiveObserve와 bag replay로 위치/scan을 표시. 기체 움직임은 별도 B3/B4 승인된 controller만 담당. 해당 mode의 real command sink는 존재하지 않거나 권한 차단됨을 spy publisher로 시험.

**PASS:** 보정 전후 registration/장애물 위치 오차 수치, 변경 ID/출처, replay 시 real motor publish 0. 보기 좋은 위치 animation만으로 sensor alignment PASS 하지 않음.

## B8 — 제한된 sim-to-real mission

**선행:** B3 정지 gate, B4 baseline, B6 sim, B7 정합, 이번 회차 구동 승인.

배포 artifact 필수 항목:

```text
artifact_id / robot_profile_id+hash / map_revision / scene_revision
mission_goal(frame_id, x, y, yaw, units) / approved_parameter_set+hash
Nav2+driver version / sim_evaluation_id / safety_envelope_version
approved_operator / approval_time / expiry / rollback_artifact_id
```

- 별도 mission adapter가 `NavigateToPose` 등 고수준 action을 제한적으로 발행한다. LLM이 motor topic에 연결되지 않음.
- 기체/profile/map/config mismatch, stale approval, mode wrong, battery/TF/sensor 준비 미달이면 NO-GO. Apply parameters와 Start mission을 분리한다.
- 처음에는 B4의 같은 목적지로 낮은 속도 1회. 성공 후 3~5회 반복. 현재 controller state와 terminal reason, operator 개입을 기록.
- obstacle-change 시험은 **로봇 정지 상태에서** 물체를 옮긴 다음 재관측한다. 추가 위험이 없고 운영자가 승인한 경우에만 실행. 불확실한 경로는 정지/거절하는 것도 올바른 결과다.
- cloud API를 끊어도 local safety/stop은 작동해야 한다. 응답 재개로 오래된 mission 자동 실행 금지.
- 실패 시 zero command/goal cancel/stop latch, 로그 저장, 이전 validated parameter 복구. 장애물을 통과하려고 safety margin을 임의 축소하지 않음.

**PASS:** approved artifact와 실제 run이 연결되고, 성공/안전 정지/실패를 모두 정확히 기록. 실험 구간 바깥 배포 가능성을 주장하지 않음.

## B9 — 통제 비교와 해커톤 증거

**1차 비교:** A=사진/도면 기반 개략 scene, B=동일 scene의 scan 보정본. robot/Nav2 parameter/mission/바닥/시작 위치는 고정한다. A를 일부러 잘못된 controller로 설정하지 않는다.

- 같은 조건 각 5회 제안. A가 사전검증에서 NO-GO이면 실물에서 위험하게 실행하지 않고 rejected를 기록한다.
- 독립 ground truth는 줄자/바닥 마커/외부 영상 등으로 마련한다. odom만으로 odom 정확도를 평가하지 않는다.
- geometry registration residual, 도입 준비 시간, sim/real 도착 오차, 주행 시간/거리, 접촉/근접, operator interventions, command timeout 반응을 분리한다.
- timestamp/단위/검출 방법을 명시하고 collision 관측이 빠진 항목을 0으로 채우지 않는다. unknown/null로 남긴다.
- report는 raw trace/bag hashes+profile/map/model/software revision을 참조한다. 공개용은 key/계정/집 내부 민감 영상 제외하고 허용된 부분만 사용한다.
- “TwinPulse가 현장 준비 및 차이 파악을 얼마나 도왔는지”가 핵심 지표다. 단순히 Nav2가 움직였다는 영상만으로 제품 가치를 입증했다고 하지 않음.

후속 parameter 탐색은 B9 기준선 이후 별도 승인한다. grid/random/Bayesian search와 RL을 구분하고 held-out scene에서 비교한다. 초파리 connectome controller는 더 뒤의 independent research worker로 유지한다.

## 4. 자동화와 사용자의 역할

| 사용자/현장 운영자가 해야 할 것 | Sol/시스템이 자동화할 것 |
|---|---|
| 조립/전원/배터리/차단 수단 확인 | 버전/장치/topic 계약 수집 |
| 처음 OS 초기화/설치/실물 구동 승인 | 승인된 runbook 실행·검증·checkpoint |
| 안전한 트랙과 실제 길이/장애물 배치 | rosbag/telemetry/evidence manifest |
| 최초 저속/통신 상실 시험 입회 | 유한 테스트·프로세스 상태·결과 분석 |
| 공개할 사진/영상/예산 결정 | Isaac/UI 캡처·비교표·보고서 생성 |

**매번 수동 PowerShell 실행과 screenshot 전달이 필요하도록 만들지 않는다.** 다만 접근 도구가 없는 현장 물리 조작이나 안전 확인까지 자동으로 했다고 주장하지 않는다. remote host 연결은 명시적으로 승인받은 SSH/서비스만 사용하며 credential은 안전 저장소에 둔다.

## 5. 단계별 최소 결과 파일(향후 생성)

각 B 단계는 `artifacts/robot/<run-id>/` 아래 고유 폴더를 쓴다. Git에는 sanitized 요약과 schema/fixture만 올린다.

```text
manifest.json          # stage, mode, code/config/profile hashes, start/end, approvals, verdict
host_versions.json     # OS/ROS/RMW/driver/OpenCR/LDS; secrets 없음
topic_contract.json    # name/type/QoS/frame/rate/stamp freshness
safety_report.json     # stop cases, measured latency/distance, operator intervention
metrics.json           # nullable measured values + units + method + thresholds
transforms.json        # map-to-Isaac registration + residual/source
map/                   # map.yaml + occupancy image + version
bags/                  # 원본 recording, gitignored
captures/              # run 연결이 확인되는 Isaac/UI/실물 영상
summary.md             # PASS/FAIL/NOT_RUN, 제한, 바로 다음 한 작업
```

최초 다음 행동은 **B0 inventory**다. Wi-Fi/OS/부품 확인 전에 긴 설치 스크립트나 motor 명령부터 작성·실행하지 않는다. 선택한 ROS 버전의 정확한 설치 명령은 B0 결정을 받은 후 B1 runbook으로 고정한다. 이는 불확실한 명령을 추정해 실행하지 않기 위한 의도적인 gate다.
