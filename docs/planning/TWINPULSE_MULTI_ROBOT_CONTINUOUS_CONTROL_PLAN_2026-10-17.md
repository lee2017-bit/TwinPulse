# TwinPulse — 다중 로봇·연속 수동 운전·Twin 조종 UI 수정 계획

작성: 2026-10-17. 기준: Project Memory v527 / Baseline 1.0.527.
상태: **로그·소스·공식 자료 기반 제안 / 구현 전**. 이 문서는 주행 설정 변경이나 실물 시험을 수행한 기록이 아니다.

## 1. 목표와 이번 판단

여러 로봇의 연결을 유지하면서 Twin에 이름·연결점·배터리를 표시하고, 로봇을 클릭해 수동 조종과 LiDAR를 사용할 수 있게 한다. 최초 준비 후 방향을 누르고 있는 동안 연속 운전하고, 버튼 해제나 일시 입력 만료는 바퀴를 멈추되 연결·센서·기록을 유지한다. 사용자에게 보이는 작업 ID 하나로 명령부터 실제 센서와 정지 원인까지 찾는다.

핵심 수정은 기존 안전조건을 일괄 삭제하거나 타임아웃 하나만 늘리는 일이 아니다. 현재 코드의 **연결 수명, 제어권, 모터 준비, 이동 입력 수명, 센서 수명, 기록 상태**가 잘못 결합된 지점을 분리한다. 운전을 보호하는 조건은 로봇에서 처리하고, 화면 표시나 디스크의 짧은 지연이 연결을 파괴하지 않게 한다.

물리 시험은 현재 보유 TurtleBot3 Burger 한 대로 진행할 수 있도록 계획한다. 다중 등록·동시 상태·선택/명령 격리는 실제 Isaac SIM 두 대와 실물 한 대를 조합해 시험한다. 실물 두 대의 동시 무선 통신/주행은 NOT_RUN으로 남긴다. 새로운 로봇을 등록한다고 지원하지 않는 구동기까지 자동 지원한다고 표시하지 않는다.

## 2. 원본 근거와 원인

기존 [moving-session-23.json](../../outputs/robot-obstacle-prior-20261017/moving-session-23.json), [실제 시험 보고서](../../outputs/robot-obstacle-prior-20261017/report.html#moving-session-23), `artifacts/manual-control/<job_id>/robot-evidence/session.jsonl`과 `report.json`을 대조했다. 이전 7개 실물 시도의 FAILED 판정은 보존한다.

| 시도 / job_id | 확인한 원인 | 구분 |
|---|---|---|
| 23b / `352fb9c4acec4cf5a66642fd9dfff168` | 마지막 seq196은 publish됨. 입력 나이112.755ms, 마지막 arm은6.66초 전 | 주행 중 입력 갱신 만료. Wi-Fi 실제 단절 원인은 미확정 |
| 23c / `35568331bf2e4986a83ca96f1a7a9790` | 마지막 seq264 publish됨. 입력 나이187.729ms, 잔여62.271ms | 주행 중 입력 갱신 만료. 모든 문제를 arm으로 설명하지 않음 |
| 23d / `e96fff309323492ea81a84e222c303d8` | 첫 이동 전 INPUT_CLOSED_OR_OVERFLOW | EOF/overflow를 하나로 기록해 원인 분해 불충분 |
| 23e / `d19108540a584a7eb336c5ec958b4d60` | observation journal 쓰기5.274820초, pending200ms 조건이 실패로 고정됨 | 기록 지연이 제어 작업 종료로 이어짐 |
| 23f / `468c072be6ce42acb0266509c3e0f61d` | 전진9.137cm/후진8.957cm wheel odom 뒤 종료. helper가 graceful close 직후 EOF 유발 | 실제 움직임 자료 확보와 시험 도구 종료 결함을 분리. 차체 실측 아님 |
| 23g / `19c30f7ca43b4372acf03187b38812f6` | 같은 seq352의 source age152.670ms + arm109.484ms =262.154ms | 250ms 입력 수명을 준비 중 소모. 해당 입력 publish 전 만료 |
| 23h / `3a13385e02cd49e18d86bc1e68f8556a` | 같은 seq313의186.362 +117.652 =304.014ms | 같은 arm/입력 수명 결함 |

4회 입력 만료 중2회는 arm 준비와의 결합으로 직접 설명된다. 나머지2회는 주행 중 갱신 문제다. ping2/6/8/238ms 네 표본은 지연 가능성의 근거일 뿐 원인 전체나 p99 통계가 아니다. b의 odom 최대 간격 약62ms였으므로 뒤에 표시된 OBSERVER_ODOM_STALE이 최초 원인이라고 단정할 수 없다.

원시 native3,456,369bytes, 움직임 odom802표본을 확보했지만 한 세션360도는 실패했다(최장205.664도). f/g/h의 byte-time sidecar 누락, 비균일 빔, vendor decoder 최초25샘플 누락, sensor-to-base/방 정합 미확정도 독립 결함이다.

### 2.1 코드에서 추가 확인한 제품 결합

- `teleop_contract.py:149`: 입력 만료 시 closed + 예외. `teleop_worker.py:585`와 finally에서 FAILED→센서/base 종료·OFF로 이어진다.
- `teleop_worker.py:224` 부근: arm 후 새 입력을 요구하는 의도는 이미 있으나, 준비 중 기존 gate deadline이 살아 있어 다음 반복에서 먼저 만료될 수 있다.
- `PhysicalRobotController.tsx:226`:100ms 입력 송신이 이전 HTTP 완료를 기다린다. 응답 지연이 입력 공백이 된다.
- 같은 파일240–245: 표시용 상태조회 실패가 close로 연결된다.216–221/330–331: 창/패널 포커스 이탈도 세션 종료를 유발한다.
- 버튼 해제→RELEASING→READY, `fresh-intent-1.0`, `until-stop-1.0`는 이미 있다. 이 구조를 재사용하고 잘못된 종료 조건을 고친다.
- `control_scan`도 `teleop_ros.py:377`→`local_navigation.py:39`에서 `require_scan=False`인 수동 경로를 사용한다. **LiDAR 기록 중이라는 사실이 장애물 정지 기능 작동을 뜻하지 않는다.**
- `WorkspaceDevices`에는 controller/readiness/diagnostics가 각 하나다. 등록 목록의 active_id를 바꾸면 재바인딩한다. 다중 등록과 동시 연결은 현재 다른 수준이다.
- Twin은 bitmap canvas이며 로봇별 화면 좌표/클릭 계약이 없다. `ChatWorkspace.tsx:489,900` 부근은 단일 Burger/배터리 표시다.
- 현재 설치16은 `physical_robot=false`이다. 보조 SSH/controller 시험은 설치 App의 실제 물리 조종 버튼을 통과한 증거가 아니다.

## 3. 현재 제한을 보이게 만드는 감사표

다음16행은 확인한 주요 조건/자원 제한이다. 같은 값을 여러 곳에서 검사하는 부분도 있으며 저장소 전체 안전장치의 정확한 총개수라는 뜻은 아니다. 구현 첫 단계에서 중복·사문화·실제 발동 여부를 포함한 기계 판독 가능한 조건 목록을 만든다.

| 계층 | 현재 조건 | 개선 방향 |
|---|---|---|
| PC 입력 | 입력 expiry 최대300ms, watch 공백500ms | 원격 조작 수명과 연결 생존 분리 |
| nonce 중계 | PC에서 받은 nonce150ms 넘으면 대기 | 인증은 유지, RTT/대기시간 계측 및 준비와 분리 |
| 로봇 입력 | nonce 왕복+PC 입력 나이 합산250ms | 준비 완료 뒤 새 입력에서 유효기간 시작; 만료→정지/PAUSED |
| idle 존재 확인 |500ms | 관찰/센서 세션을 방향 입력과 분리 |
| 세션/hold | 신형 until-stop, fresh 입력으로2초 hold 갱신; 구형60초 | 신형 경로 재사용, 제품에 남은 구형1.4초 분할 확인 |
| 최종 로컬 출력 |400ms watchdog,20ms tick,100ms heartbeat | PC 운전 임대와 별도 유지·검증 |
| 속도 | 수동±0.05m/s·±0.30rad/s, nav 별도 | 속도·가속도 프로필 한곳에서 관리 |
| 센서/guard 시각 | 수신/원본 timestamp200ms | 센서 종류별 실제 주기·허용 구간·오차 기준화 |
| 보드 상태 |11.1V 이하, 버튼, 중복 publisher 등 | 고장/소유권 유지, 연결 표시와 이동 가능 상태 구분 |
| RPC | arm/stop/torque500ms | ARMING의 별도 deadline; Stop 우선 |
| journal | pending200ms,queue256,64MiB | 기록 지연과 제어 중단 분리, bounded buffer/분할 파일 |
| protocol outbox | pending200ms,queue128,1MiB | 제어 ACK와 telemetry/file export 큐 분리 |
| 초기 준비 |12초,torqueOFF,explicit stop,encoder 안정200ms | 실제 부팅 ON과 이동/정지 관찰을 구분 |
| 버튼 해제 |torqueOFF 포함,최대0.9초 확인,안정200ms,10mm | 정상zero 정지/보유토크 정책을 검증해 불필요 재arm 제거 |
| 자원 한도 |여유128MiB,base/driver log8MiB,event131072 | 파일 회전·보존·누락 상태; 임계 실제 소진 시 제어 pause |
| 루프 정지 |동작 중 갱신하는10초 alarm | 최종 출력 watchdog과 역할을 명시 |

참고 코드: `physical_controller.py:413,474,841`; `teleop_contract.py:135–154`; `teleop_ros.py:302,316,335,408`; `teleop_worker.py:44,458,569`; `robot_journal.py:12`; `command_guard.hpp:16`.

사용자가 보는 화면에는 모든 내부 코드 대신 `운전 준비 / 장애물 / 입력 연결 / 센서·보드 / 기록` 상태와 **현재 막는 이유 하나 + 펼치기**를 제공한다. 펼치면 측정값·기준값·발동 시각·해제 조건·횟수·operation ID가 나온다. 등록/관찰에 불필요한 주행 조건을 요구하지 않는다.

## 4. 벤치마킹한 것과 적용할 것

아래 공식 자료를2026-10-17에 확인했다. 기존 프로그램 전체를 이식하거나 ROS/Isaac을 최신 버전으로 일괄 변경하자는 제안은 아니다.

| 근거 | 확인한 기능 | TwinPulse 적용 |
|---|---|---|
| [Foxglove Teleop](https://docs.foxglove.dev/docs/visualization/panels/teleop) / [3D panel](https://docs.foxglove.dev/docs/visualization/panels/3d) | 방향패드·정지·버튼 해제 정지, 객체 클릭/선택 ID | Twin 객체 클릭→로봇별 조종 drawer, 방향/정지와 상태 표시 |
| [ROS2 control Humble diff drive](https://control.ros.org/humble/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html) | 속도/가속도 제한, cmd_vel_timeout 기본0.5초, hardware feedback odom | 제어 루프와 UI 분리;0.5초는 비교용 후보이며 자동 안전 보증 아님 |
| [ROS teleop_twist_joy](https://github.com/ros2/teleop_twist_joy) | enable 버튼, joystick→Twist; autorepeat는 별도 입력 계층 담당 | hold-to-drive·해제/포커스 손실 정지·입력 생존을 분명히 관리 |
| [Nav2 Collision Monitor](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/) | 센서 기반 stop/slowdown/접근 모델, footprint와 방향/속도별 영역, PointCloud2 지원 | 명령을 로봇에서 필터링. 장면/LLM 완성을 기다리지 않고 근접 장애물 정지 |
| [Nav2 Progress Checker](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/simple_progress_checker/) | 시간창 내 최소 이동 검사 | 저속 프로필에 맞는 정체 검사. 문서 기본0.5m/10s를 작은 저속 시험에 그대로 복사하지 않음 |
| [Open-RMF robot state](https://github.com/open-rmf/rmf_api_msgs/blob/main/rmf_api_msgs/schemas/robot_state.json) | 로봇 상태·위치·배터리·task·issues 모델 | 로봇별 상태와 작업 ID. 전체 fleet scheduler 도입은 현재 범위 밖 |
| [Isaac6.0.1 ROS namespace](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/ros2_tutorials/tutorial_ros2_auto_namespace.html) | 로봇별 ROS 이름공간 | topic/service/TF ID/prim과 로봇 고유 ID 결속 |
| [OpenTelemetry log correlation](https://opentelemetry.io/docs/specs/otel/logs/) | trace/span과 로그 문맥 연결 | 기존 execution diagnostics 재사용, 명령/센서/오류를 상위operation ID로 조회 |

Nav2 문서의 최신 Jazzy/rolling 옵션을 현재 로봇 Humble에 그대로 넣지 않는다. 설치된 지원 기능을 확인하고 같은 인터페이스의 좁은 어댑터를 우선한다. 새 의존성/드라이버 설치는 후속 구현 때 범위를 명시한다. Nav2 Collision Monitor 자체는 인증된 하드웨어 안전장치가 아니다.

## 5. 권장 구조와 공통 계약

```text
Twin 로봇 badge / 조종 drawer
    → 로봇 ID가 명시된 입력·상태 채널
    → PC RobotSessionManager (로봇별 지속 연결, lease, 상태)
    → 기존 인증 SSH/로봇 세션 어댑터
    → 로봇 local supervisor → 충돌/정체/속도 필터 → 최종 guard → 모터
                            ↘ sensor streams / bounded recorder
       telemetry·ACK·원본 반출 → operation timeline → Twin
```

### 5.1 다중 연결과 선택

- 기존 `robots[]`를 유지하고 `sessions[robot_id]`를 도입한다. `focused_robot_id`는 화면 선택일 뿐 다른 세션을 종료하지 않는다.
- 로봇별 연결/진단/controller/sensor/기록 큐/lock을 분리한다. 전체 워크스페이스 단일 controller는 단계적으로 이관한다.
- `robot_id`는 불변 UUID, display name/IP는 가변이다. endpoint와 검증된 장비 identity를 함께 확인해 같은 실물을 별칭 두 개로 동시에 소유하지 않는다. legacy zero UUID를 실물 식별자로 사용하지 않는다.
- 각 로봇에 adapter/version, credential reference, ROS domain/namespace, TF frame IDs, footprint, 제한/보정 프로필을 둔다. 비밀값을 로그에 넣지 않는다. topic namespace만 바꾸고 TF frame_id 충돌을 방치하지 않는다.
- 여러 로봇 telemetry를 동시에 볼 수 있다. 첫 버전의 사람이 조작하는 키보드/패드는 한 번에 선택한 한 로봇에만 보낸다. 로봇별 제어권 소유를 유지한다. 향후 병렬 임무는 별도 작업이다.
- 프로젝트 전환·Twin 숨김으로 연결을 임의 끊지 않는다. 현재 수동 입력은 정지시키고 작업/장면 binding을 보존한다. 구프로젝트의 늦은 명령이 신프로젝트 로봇으로 넘어가지 않게 한다.

### 5.2 서로 독립인 상태

| 상태 축 | 예 |
|---|---|
| connection | CONNECTING / CONNECTED / DEGRADED / DISCONNECTED |
| control | UNPREPARED / ARMING / READY / DRIVING / PAUSED / FAULT |
| lidar | OFF / STARTING / STREAMING / STOPPING / FAULT |
| recording | RECORDING / BUFFERING / EXPORTING / COMPLETE / INCOMPLETE |
| pose | UNALIGNED / ODOM_ONLY / ALIGNED / STALE |

`INPUT_STALE`·버튼 해제·창 포커스 이탈은 이동 정지/PAUSED로 처리한다. 창을 다시 클릭하거나 네트워크가 돌아온 것만으로 과거 방향을 재생하지 않는다. 새 현재 방향 입력을 받아야 움직인다. heartbeat만으로 운전 권한을 연장하지 않는다.

Stop·입력 만료·조종 로봇 전환마다 `motion_epoch`/control lease를 폐기하고 새 조작에 새 세대를 발급한다. 같은 connection 안에서도 이전 세대의 방향 패킷은 sequence가 더 크더라도 거절한다. 저장된 held 상태나 heartbeat만으로 새 운전 lease를 발급하지 않는다.

정상 Stop은 세션을 보존한다. Disconnect/앱 종료는 정지→확인→센서·기록 마무리→연결 종료다. 실제 보드/제어권/guard 고장은 FAULT와 별도 복구로 처리하되 가능한 상태·기록 조회는 유지한다. 다른 로봇 세션까지 종료하지 않는다.

실제 무선 단절·로봇 전원 상실에서는 센서 수신을 계속한다고 보장할 수 없다. 이때 유지하는 것은 PC의 논리 작업·기존 기록·재접속 관리이며, 연결과 관측은 stale/disconnected로 표시한다.

## 6. 연속 운전과 최초 점검

1. 부팅 torque ON은 연결 실패나 실제 이동으로 판정하지 않는다. 연결 시 신선한 명령값·속도·encoder·전압·guard·장치 identity를 읽어 현재 상태를 표시한다.
2. 최초 운전 준비는 제어권 취득→zero 목표→실제 정지/guard 확인→READY. 센서 관찰과 준비 권한을 구분한다. 의도하지 않은 자동 주행은 없다.
3. ARMING 입력은 준비 요청으로만 소비한다. 준비 완료 뒤 새 challenge/현재 입력을 받기 전까지 zero를 유지한다. 준비 전에 받은 방향의 timestamp를 새 것으로 바꿔 재생하지 않는다.
4. 정상 방향 유지 중 매2초마다 정지/재arm하지 않는다. 버튼을 놓으면zero, 다시 누르면 현재 준비 상태에서 이어간다. 정상 zero 대기에서 토크 유지가 해당 하드웨어에 적합한지는 정지/브레이크 시험으로 확인한다. 무조건 OFF가 더 짧게 멈춘다고 가정하지 않는다.
5. 정지 성능 qualification은 개발/릴리스·제어 정책·구동계 변경을 검증하는 항목과 부팅 때의 빠른 무이동 상태 확인을 구분한다. 장기적으로 매 클릭/재접속마다 물리 정지시험을 반복하지 않도록 버전결속 qualification을 설계한다. 현재 same-boot receipt를 무검증으로 재해석하지 않고 새 정책 버전으로 인수한다.
6. 사진 품질·방 전체 SLAM·Library 완성은 감독 수동 조종의 선행 조건이 아니다. 근접 정지에는 센서→차체 변환/footprint와 현재 장애물 자료가 필요하지만 전역 방 위치까지 요구하지 않는다.

### 6.1 타이밍 개편

- 우선 기존250ms에서도 arm 소모와 상태조회/입력 직렬화를 없애는 효과를 재현한다.
- PC 입력은20Hz 후보, ACK/상태와 비동기 전달. 방향은 latest-only bounded queue, Stop/제어권 해제는 우선 처리한다. 밀린 방향을 FIFO로 나중에 실행하지 않는다.
- PC↔로봇은 기존 SSH를 연결당 지속 사용한다. 원시 파일 반출/대용량 센서 스트림은 제어와 별도 전송 작업/큐로 분리한다. 같은 TCP stream에 넣은 여러 논리 큐만으로 네트워크 정체가 해결된다고 가정하지 않는다.
- 현재 입력 expiry를 **500ms 후보**와 비교한다. 이는 제안값이며 즉시 배포값이 아니다. 신규 프로필은 인증 nonce·PC expiry 상한·robot gate·최종 guard의 관계를 함께 정의한다. 한 상수만500으로 바꾸면 기존300ms 상한/다른 freshness 검사를 통과하지 못한다.
- 로봇 local guard400ms를 네트워크 lease와 같은 의미로 사용하지 않는다. source age·operator lease의 절대 만료를 끝단까지 보존하고, local 재발행이 stale operator intent를 새 것으로 세탁하지 않게 한다. 각 단계 deadline과 마지막 허용 시각을 기록한다.
- 새 계약은 `operator_intent_deadline`과 `local_output_refresh_deadline`을 구분하며 최종 출력은 둘 중 먼저 끝나는 시각을 넘지 않는다. 현재 C++는 원명령 나이400ms부터 거절하므로 그대로라면500ms 후보도400ms에서 잘릴 수 있다. 이 호환 문제까지 버전결속 시험하고, local 재발행은 operator deadline을 연장할 수 없도록 한다.
- 계측: UI event→PC수신→큐대기→SSH쓰기→로봇수신→허가→구동출력→센서반응, release→zero→실제 정지. p50/p95/p99/max·연속 누락·clock 오차를 수집한다.
- 링크 입력과 최종 watchdog이 직렬로 정지 지연을 더할 수 있는 최악 경로까지 계산한다.500ms만 보고 전체정지500ms라고 주장하지 않는다. 실측 제동거리/반응시간 범위와 연결한 프로필만 사용한다.
- 재접속은 인증·관찰까지 자동 복구할 수 있다. 이동은 새 connection epoch와 새 입력을 요구한다. 오래된 ack/방향 명령은 거절한다.

## 7. 사용자가 제안한 보호를 실제로 연결하기

사용자 조정 항목은 최대 속도, 장애물 여유거리, 정체 민감도 중심으로 단순화한다. 입력 상실 정지·사용자 Stop·센서/보드 고장·제어권 검사는 기본 동작으로 유지한다. 설정이 많아 보이지 않도록 현재 발동 이유만 표면에 표시한다.

### 7.1 장애물10cm

- 권고 목표는 **정지 완료 후 로봇 차체 외곽과 장애물 사이에10cm 여유를 남기는 것**이다. LiDAR 중심에서10cm라는 뜻이 아니다. 전진은 전방 swept footprint, 후진은 후방, 회전은 차체가 쓸고 지나가는 영역을 검사한다.
- 실제 정지 시작 경계는 `0.10m + abs(v)*T_effective + d_brake + uncertainty_margin`을 기본으로 한다.10cm에서야 정지를 시작하면 제동 중10cm 안으로 들어갈 수 있기 때문이다. 회전은 각속도와 외곽 반경을 반영한다. T에는 센서 주기·입력/제어·최종 watchdog 최악 경로를 중복/누락 없이 반영한다. 측정되지 않은 값은 추정으로 표시한다.
- 경계에서 깜빡이며 주행/정지를 반복하지 않게 해제 hysteresis를 둔다. 전방 장애물이면 전진을 막고, 후방이 확인되면 사용자의 새 후진 조작으로 빠져나올 수 있다. 자동 후진/자동 재출발은 하지 않는다.
- 비균일 원래 각도를 보존한 point cloud/beam 표현을 우선한다. 유효 PointCloud2→로컬 충돌 검사 경로를 검토하면 전체 SLAM이나 가짜 균일 LaserScan을 선행할 필요가 없다.
- 최초25샘플 parser 누락·min range·센서 장착 변환·회전각 관례를 먼저 고친다. missing/no return/막힌 시야를 free space로 만들지 않는다.2D LiDAR가 끈·낮은 물체·스캔면 밖 장애물을 항상 감지한다고 약속하지 않는다.
- LiDAR Off는 먼저 이동 정지→센서Off, 연결/배터리는 유지한다. 보호 모드에서 센서를 끈 채 새 이동은 허용하지 않는다. 단순 포인트 표시 숨김과 실제 센서 종료는 별도 동작이다. 물리 회전 정지 피드백이 없으면 '수신 중지/정지 명령 확인'으로 표시한다.

### 7.2 움직이라고 했는데 안 움직임

- 바퀴 정체: 비zero 최종 허용 명령을 보냈으나 encoder 속도/변위가 시간창 동안 거의 없음.
- 차체 정체/헛돎: encoder는 돌지만 LiDAR scan matching/독립 pose 이동이 거의 없음. wheel odom만으로 차체 이동을 증명하지 않는다.
- 회전은yaw 진전, 직진은선형 진전을 따로 검사한다. 목표zero·장애물 정지·ARMING·정상 가감속 구간은 정체로 세지 않는다.
- 초기 저속 후보는1–2초 창에서 기대 이동량과 관측 오차를 비교하되 기존 저장 자료의 노이즈/정상 주행과 SIM 정체 재현으로 threshold를 결정한다. 작은 값 하나가 같다고 즉시 고장 처리하지 않는다.
- 독립 pose가 불충분하면 '바퀴 정체 감시 사용/차체 헛돎 미검증'으로 표시한다. 이 한계를 숨기지 않고 감독 수동/자동 운전의 지원 범위를 분리한다.

## 8. Twin 화면과 조종기

로봇 아래에 작은 badge: `● 거실 TurtleBot · 11.8V`처럼 표시한다. SOC가 검증된 로봇은 `%`를 함께 표시하고, 전압으로만 추정하면 `약`을 붙인다. 마지막11.49V 역사값을 현재값으로 쓰지 않는다.

- 초록점: 현재 인증된 로봇 연결과 신선 heartbeat. 노랑: 지연/갱신중. 회색: 끊김/미확인. 색 외에도 상태문구/접근성 label 제공.
- badge는 연결을 의미하며 운전 가능/안전을 뜻하지 않는다. 선택하면 현재제어상태·센서·정지이유가 drawer에 나온다.
- connection/control event는 즉시 전달, battery는 실제 지원 주기에 맞춰 약1Hz, pose는 초기10–20Hz 후보. stale이면 마지막값과 나이를 보여주고 live처럼 움직임을 합성하지 않는다.
- telemetry에 robot_id, connection_epoch, boot_id, sequence, observed_at/received_at를 포함해 이전 연결의 늦은 값을 거절한다. SIM 배터리는 simulated 출처를 표시한다.
- `frame_robot_anchors[]`에 robot_id, scene_instance_id/prim, screen_anchor_uv/hitbox, visibility, engine_session_id, frame_id, camera_sequence, stage_epoch/revision, pose frame/source/time을 넣는다.
- React overlay는 해당 프레임과 맞는 anchor에만 붙인다. 배터리 갱신 때문에 Isaac scene 전체를 rebuild하지 않는다. 카메라 이동/resize/가려짐/이름 겹침/저장된 미리보기 처리를 검증한다.
- 실물 odom이 아직 방에 정합되지 않았으면 Twin 영역의 로봇 목록에 '위치 미확정'으로 보여준다. 사용자 배치/추정 위치를 실제 추적 위치로 위장하지 않는다. 추정 scene instance와실물 robot ID의 연결을 명시한다.
- 로봇/이름 클릭→선택 로봇 조종기. 전진/후진/좌회전/우회전, Stop, LiDAR On/Off, 속도, 기록상태·ID·로그 버튼. 버튼누름/키보드hold를 기존 DriveJoystick 기반으로 처리한다.
- 다른로봇 선택·창 blur·키해제·pointercancel·컨트롤포커스 이탈 시 기존조종은zero. 조종기 재선택만으로 자동 이동하지 않는다. 연결/수집은 유지한다.
- 여러 연결에 대한 '모든 로봇 정지'도 명시 기능으로 제공하되 소프트웨어 Stop을 인증된 물리 E-stop이라고 부르지 않는다.

## 9. 하나의 작업 ID와 기록 경로

사용자는 `operation_id` 하나를 보고 검색·복사한다. 내부 job/execution/robot_session ID를 삭제하지 않고 계보로 묶는다.

```text
operation_id (사용자가 보는 한 번의 연결·운전·스캔 작업)
 ├─ project_id / conversation_id / scene_revision
 ├─ robot_id → connection_epoch / boot_id / adapter / release / policy
 │    ├─ control_session_id → job_id / execution_id / 실제 robot_session_id
 │    │    └─ command_id + seq: requested→received→accepted/rejected→published→stop
 │    └─ capture_id: native/points, odom, IMU, battery, TF, timing chunks
 └─ manifest: 파일 SHA·count·offset·시각·누락·footer·반출 확인
```

- 새 명령은 robot_id/connection_epoch/motion_epoch/control lease/action/sequence/유효기간/원래 생성시각을 포함한다. 같은 방향 재시도는 오래된 이동을 중복 실행하지 않는다. Stop은 멱등·우선 처리한다.
- current project가`default`로 잘못 고정되거나 요청ID를 실제robot session ID로 부르는 기존 alias를 교정한다. 구로그는 migration mapping으로 연결하고 원본을 다시 쓰지 않는다.
- UTC는 사람이보는시각, monotonic은 각호스트구간측정. 서로다른호스트 monotonic을그냥빼지않는다. offset/uncertainty를보존하고 순서불확실 이벤트를억지정렬하지않는다.
- 명령요청/수락/최종publish/encoder/차체이동을구분한다. 명령마다모든sensor를복제하지않고stream시간범위/sequence로참조한다.
- EOF/QUEUE_FULL/INVALID_PACKET/INPUT_STALE/BOARD_TIMEOUT/RECORDER_BACKLOG를분리한다. 최초원인과뒤따른정리오류를따로남긴다.
- 기록은이미비동기지만현재200ms pending이전체실패를유발한다. bounded RAM queue→batch write/rotate→background export로개편하고제어queue와분리한다. 짧은지연은BUFFERING;버퍼포화/필수명령기록불능이면이동pause,연결·가능한상태조회유지. 무한메모리나조용한손실은금지한다.
- tmpfs자료는raw뿐아니라chunk timing/footer까지PC반출SHA를확인한뒤삭제한다. 미완료manifest는INCOMPLETE. 재시작후복구·재반출을지원하며'이동성공'과'자료완전성'을별도판정한다.
- 로그열기 한곳에서명령·궤적·센서·배터리·정지/재개사유·누락을동일타임라인으로표시한다. UI/Isaac/사진모델처리와분리해센서로그저장이전체화면을막지않도록한다.

## 10. 구현 순서·파일 소유

### P0 — 계약·원인 재현

주작업자가 `RobotSession`, 상태축, operation/command/stream ID, timer profile, capability/telemetry, frame anchor 계약을 먼저 동결한다. 기존7원본으로 arm후만료·EOF·journalstall·sidecar누락을오프라인재현한다. 현재소스/설치해시·실패로그를보존한다.

### P1 — 연속 연결·제어 안정화

`teleop_contract.py`, `teleop_worker.py`, `teleop_ros.py`, `physical_controller.py`, `robot_journal.py`의준비/이동/정지/종료를분리한다. 입력/Stop/heartbeat의우선경로와recording queue를고친다.500ms후보는측정·fault시험후profile버전으로결정한다. 일단숫자만올린버전을실물로반복시험하지않는다.

### P2 — 다중로봇과 Twin 조종 화면

주작업자는 `workspace_devices.py`, `robot_registry_service.py`, `robot_adapters.py`, API와 `twinpulse_live_viewport.py`를맡는다. 로봇별session/ownership/transport·frame anchor구현. UI보조1명은 `TwinViewport.tsx`, `viewport-types.ts`, `ChatWorkspace.tsx`, `RobotRegistry.tsx`, `PhysicalRobotController.tsx` 및새overlay/drawer를맡는다. `api.ts`는계약확정후한담당자만수정한다.

### P3 — 실제 LiDAR 보호·정체·기록 연결

원각도보존decoder/PointCloud2·sensor-to-base검사→방향별footprint정지→wheelstall/가능한bodyprogress→LiDAR독립수명→통합manifest를연결한다. 방전체정합은기본수동UI완성의선행조건으로걸지않는다. 현재manual의scan-check=false를사용자에게숨긴채'보호조종'으로출시하지않는다.

### P4 — 설치본 동결·일반 사용자 인수

일반 Start→실제Electron→Robots연결→Twin선택/조종→기록→종료/재열기를주작업자가순차시험한다. 실제Isaac·실물·설치판교체는병렬실행하지않는다. 필요하면독립검토자1명으로정지경로와다중robot오염을검토하고보조최대2명을유지한다.

우선순위는 P1의끊김원인과P2의실제조종경로다. 범용로봇관제/자율fleet최적화/새프레임워크이관을같이추가하지않는다. 다만실물보호수동출시는P3의핵심센서보호가준비된기능범위에서한다.

## 11. 인수 기준 — 다음 실물 시간을 낭비하지 않는 순서

| ID | 방법 | 통과 기준 |
|---|---|---|
| R01 | 저장23g/h timing replay | arm전입력은실제출력에쓰지않음;READY후새입력으로동작,기존deadline때문에연결종료없음 |
| R02 | 지연/누락 fault test |100/250/500/1000ms·burstloss/Stop전후순서변경/구motion_epoch지연방향/lateack를기록.입력만료·표시조회오류는정지·PAUSED와연결/센서유지,새입력만재개.실제단절은논리작업/기록보존·센서stale |
| R03 | 기록5.275초stall/디스크full/queuefull | control/Stop응답이기록write를기다리지않음,필요시pause,최초원인/누락이manifest에남음 |
| R04 | 정상close/강제EOF/앱종료 | helper가정상close를EOF로바꾸지않음,EOF와overflow별도이유;zero/복원/반출기록 |
| R05 | 실제Isaac SIM2대·실물1대+SIM격리 | 이름·simulated배터리·연결선택/명령/TF격리. A지연·종료가B상태를종료하지않음.재접속이전epoch의telemetry거절.실물2대인수아님 |
| R06 | 실제Electron/Twin | 로봇클릭→drawer,hold/release/keyboard/blur/다른로봇선택;마지막프레임/원사진깜빡임회귀;Isaac재시작뒤같은frame/camera번호의구anchor거절 |
| R07 | 관측재생·SIM근접정지 | 전후/회전footprint·10cm외곽기준,stale/unknown·재개/빠져나오기;가짜거리주입을실물PASS로세지않음 |
| R08 | SIM정체·저속·회전·slip | wheelstall과bodyprogress구분,정상회전·정지명령오탐없음. 불충분pose는UNKNOWN |
| R09 | 일반설치실물1대처음연결 | 정상부팅torqueON을연결실패로표시하지않음;준비→READY,현재이름/전압/연결점확인 |
| R10 | 실제Twin수동연속세션 | 하나의control_session에서최소60초연속회전과최소1회360도,정지/방향변경/짧은전후진.한번의약5분관찰세션에서불필요close/rearm0.현장/전압부족시중단이유기록 |
| R11 | 실제센서·보호 | LiDAR On/Off/restart,전후접근정지·회전영역;견고한표적과측정거리로확인.고의충돌/로봇을손으로막는시험은하지않음 |
| R12 | 연결/입력상실 | 명시된fault조건에서zero·PAUSED;transport복구후이전방향자동재생0;배터리·포즈stale표시정확 |
| R13 | 한ID기록/복원 | 모든명령/robot/stream/scene계보,raw+timing+footer+SHA반출.앱재열기후같은ID조회;연속360과분할누적구분 |
| R14 | 일반모드/설치회귀 | Test BrowserWindow와일반debug-off·OS입력을구분.불가항목NOT_RUN. 보조API시험을사용자시험으로대체하지않음 |

R01–R08을로봇전원없이끝내고일반설치에반영한뒤실물R09–R13을한현장세션으로묶는다. R10은주기적부하결함을잡는최소인수이지무기한신뢰성보증이아니다. 실제한대로여러실물동시운전PASS를주지않는다. 지원속도·허용지연별release-to-stop시간/이동거리의사전경계를정하고초과를그대로FAIL로남긴다. 초기한정0.05m/s·0.30rad/s에서확인후별도승인/검증없이속도를올리지않는다.

정체의바퀴헛돎분기나외부Wi-Fi차단이실물로발생하지않으면그분기는SIM/보조와실물NOT_RUN을분리한다. 로봇전원이필요하기전UI/빌드/오프라인준비를끝내며기존저장자료로할수있는분석때문에다시켜달라고하지않는다.

## 12. 완료 표시와 권한

이번계획완료는제품완료가아니다. 후속보고서는 기능/연속운전/센서보호/정합/로그완전성/일반설치인수를따로판정한다. 최초실패와변경후결과를모두같은인덱스에남긴다.

이번분석은로컬read-only검토와공식웹검색,문서작성만수행했다. 로봇접속·이동·정책/타이머수정·제품코드수정·새설치·모델전송·commit/push없음. 추가Nebius비용USD0,기존누적USD14.9450973/20을변경하지않는다. 외부문서는설계참고이며사용자의현재승인범위와기존비밀/개인자료보존규칙을대체하지않는다.
