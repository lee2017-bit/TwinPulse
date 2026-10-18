# TwinPulse 로봇 지연·반복 실패 검토 — 2026-10-18

후속 구현·검증: **v543 최종 설치04의 조종 UI/SIM·callback/FIFO/ICP/field_config 경로를 실제 검증했다. 실물은 계속 NOT_READY.** 아래 분석은 당시 근거이며, 현재 구현·별도전체여정·원FAIL/UNKNOWN·미해석프로토콜과 정확잔여는 [단일 보고서](../../outputs/control-recovery-20261018/report.html)와 PROJECT_MEMORY v543을 따른다. 실제Pi부하/ROS개선분포·물리검증은 로봇OFF로 미수행이며 제한값 완화0이다.

상태: **분석 및 제안, 제품 변경·새 설치·실물 재시험 없음.** 현재 실물 주행 NOT_READY 판정 유지. 사용자 보고에 따라 로봇 OFF이며 접속하지 않았다. 아래 제안은 신규 실행 승인이나 완료 판정이 아니다.

## 결론

현재 200ms 센서 신선도 제한은 실제 LiDAR 동시 부하에서 관측 표본의 절반 이상을 거절한다. 이를 정상 사용 가능한 상태라고 인수한 것은 적절하지 않다. 다만 LiDAR를 끄자 같은 ROS 세션의 원본 데이터 나이가 평균 207ms에서 30ms로 줄었다. 제한값을 늘리기 전에 동시 처리 부하를 분리할 강한 근거가 생겼다.

또한 11바이트 미해석 구간은 30~31프레임마다 반복된다. 현재 8초 정지 수집은 불완전 프레임 하나에 즉시 종료하므로 단순 재시도는 해결책이 아니다. 데이터 파서·상태 판정·동시 처리 경로의 결함을 저장 원문으로 먼저 해결하고, 다음 전원 세션을 실제 Pi 부하 확인과 동작 인수에 집중해야 한다.

현재 수치는 평균·표준편차 또는 p99에서 자동 산출한 정책이 아니다. 검사 코드는 고정 설계값이고 기존 문서에는 주로 보호 유지가 기록되어 있다. 안전 상한을 변경할 수 없다는 뜻은 아니다. 변경에는 목적별 근거와 동일 조건의 회귀가 필요하다.

## 1. 분석 원본과 방법

- 설치 release: `20261018T111819Z-f42d23014b1c`.
- operation: `ee9883a7e6834278ac3a9c6d8ed932a2`.
- 원본: `outputs/robot-retest-20261018/raw/receipt.json`와 그 54개 JSONL segment.
- 원시험 보고서: [report.html](../../outputs/robot-retest-20261018/report.html).
- 원본 117,133개 사건, 224,750,258바이트. 이번에는 복사·삭제·재업로드하지 않았다.
- native 원문 SHA: `7a50ff3fec3cb24e500faead1e5b5d0caeea8b0654ad2db615aa491ebaa21522`.
- `kind=heartbeat` 중 `data.telemetry_diagnostic.source_age_s`가 유효한 8,016개 진단을 사용했다. 같은 센서 표본이 여러 진단에 쓰일 수 있다. 독립된 센서 패킷 8,016개라는 뜻이 아니다.
- 표준편차는 표본 SD(n−1), 분위수는 nearest-rank: 정렬 배열의 `ceil(p*N)-1` 원소. 단위 ms.
- `source_age`는 ROS 현재 시각과 sensor header 시각의 차이다. PC↔로봇 HTTP/SSH 왕복 응답시간이 아니며, header가 하드웨어 취득시각이라는 보증도 별도다.
- 메인과 통계 보조가 원문에서 N·평균·SD·초과 횟수·ON/OFF 분리를 독립 교차 확인했다. Astra xhigh 보조는 코드 및 설계 읽기 검토만 수행했다.

## 2. 실측 분포

| 상태 | N | 평균 | 표본 SD | p95 | p99 | 최대 | 200ms 이상 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 전체 진단 | 8,016 | 194.026 | 54.840 | 259.771 | 284.558 | 339.359 | 3,886 / 48.478% |
| 실제 LiDAR STREAMING | 7,427 | 206.921 | 30.927 | 260.882 | 286.043 | 339.359 | 3,886 / 52.323% |
| 실제 LiDAR OFF | 539 | 30.476 | 15.022 | 55.585 | 61.696 | 63.060 | 0 / 0% |

나머지 50개는 STOPPING 상태다. STREAMING과 OFF의 평균 차이는 약 6.79배다. ROS 시작 후 30초를 제외한 STREAMING 6,958개도 평균 206.947ms, SD 30.593ms, 200ms 이상 52.185%로 같은 현상이 유지된다.

전체를 혼합해 계산하면 200ms는 평균+0.109 SD에 불과하다. 실제 STREAMING 구간에서는 평균보다 0.224 SD 아래다. 드문 이상치만 거르는 문턱으로 작동하지 않는다. 그러나 실패를 포함한 두 부하 상태의 혼합 분포를 '정상 응답시간'으로 삼아서는 안 된다.

| 전체 진단에 가정한 제한 | 초과 표본 | 비율 |
|---|---:|---:|
| 200ms | 3,886 | 48.478% |
| 250ms | 725 | 9.044% |
| 300ms | 26 | 0.324% |
| 350ms | 0 | 0% |
| 500ms | 0 | 0% |

이는 저장 관측에 대한 민감도 분석이다. 제한 변경 후 부하·상태 전이가 달라질 수 있으며, 350ms에서 관측 초과가 없다는 사실은 실물 안전·연속 운전 성공을 입증하지 않는다.

같은 전체 진단의 sensor callback 이후 나이는 평균 13.537ms/SD 19.782ms/p99 104.321ms/최대 145.007ms, guard callback 이후 나이는 평균 19.505ms/SD 22.331ms/p99 108.605ms/최대 164.803ms다. 최근 콜백을 받았는데 그 안의 원본 timestamp는 오래된 상태가 반복된다.

200ms 초과가 연속 관측된 묶음은 1,507개다. 첫 초과 진단부터 다음 정상 진단까지 중앙 123.249ms/p95 438.540ms/최대 846.311ms다. 이 값은 heartbeat 표본 사이의 관측 구간이며 실제 연속시간의 정확한 경계가 아니다. 인접 표본 자기상관은 약 0.78로 독립 표본 가정과 맞지 않는다.

### ON/OFF 비교의 시간적 근거와 한계

- seq106344, robot_t `1017.201584868`: LiDAR Off 요청 ACCEPTED/STOPPING. request `5820e1f4-9f53-4a67-9ac8-9acf3254a3e7`.
- seq106734, `1020.228159085`: native_sensor cleanup complete.
- seq106739, `1020.262404531`: 최초 OFF heartbeat. 원본 나이 8.398ms.
- OFF 진단 구간: `1020.262404531~1053.426865854`, 약 33.16초.
- control cleanup/base reaped는 이후 `1055.673309544`다. 비교 구간에서 ROS 원문과 기록은 계속 수신되었으며, 양쪽 모두 PAUSED/drive_ready=false였다.
- OFF는 native 취득·파싱·ICP·로그량을 동시에 줄인다. 어느 하나가 단독 원인이라고 확정할 수 없고, 순차 A/B라 시간·열·스케줄 영향도 완전히 통제되지 않았다. 그러나 단순 Wi-Fi 고정 지연 가설보다 동시 처리 경로를 먼저 조사할 충분한 근거다.

## 3. 서로 다른 제한을 구분

| 현재 값 | 의미 | 근거 |
|---|---|---|
| 200ms | ROS sensor/guard 수신 나이와 sensor 원본 나이 | `packages/twinpulse_robot_safety/teleop_ros.py:319` 이후 `fresh()` |
| 250ms | 원 조작 입력 유효기간, robot nonce 왕복과 PC 입력 나이 포함 | `teleop_contract.py:164` 이후 |
| 350ms | native ring 수신 종료 후 나이 및 ring 수신 폭 | `field_tests.py:56` |
| 80ms | ICP 반복 계산 예산 | `field_tests.py:96,164` |
| 400ms | 로봇 측 C++ 최종 출력 command guard | `include/twinpulse_robot_safety/command_guard.hpp:16` |
| 500ms | 조작자 presence/watch 소실 | `teleop_contract.py:183` |
| 500ms | 별도의 arm/stop/torque RPC 완료 대기 | `teleop_ros.py:345` 이후 `call()` |

500ms를 모두 하드웨어 watchdog이라고 부르면 틀린다. 위 400ms도 로봇 측 소프트웨어 guard이며 물리 E-stop 인증이 아니다. HTTP 화면 응답, 연결 생존, 원입력 만료, 센서 유효기간, 알고리즘 계산 예산을 같은 타이머로 조정하지 않는다.

RPC 완료가 늦어지더라도 Stop 요청은 즉시 우선 실행되어야 한다. 화면은 요청 수락·실제 출력·정지 관측을 따로 보여야 한다. 응답 timeout만으로 '로봇에서 실행 안 됨'을 단정하거나 이동 명령을 자동 재전송해서는 안 된다.

## 4. 실패를 계속 새 현장에서 발견한 이유

### 4.1 주기적인 LiDAR 비해석 구간

저장 native 재생 결과: 6,081프레임 중 불완전 202개, scan CRC 오류 0, 미해석 11바이트 구간 201회. gap frame 간격은 30프레임 171회, 31프레임 29회다. 약 10Hz 스트림에서 약 3초 주기다.

`fleet_control.py:738` 이후 stationary는 불완전 ring 하나에 즉시 INCONCLUSIVE로 종료하고 8초를 채우지 못한다. 원 stationary는 약 0.997초/10프레임에서 멈췄다. 이 패턴은 시작 시점 변경이나 timeout 연장으로 해결되지 않는다.

공식 packet 정의/길이/검증식 또는 확인 가능한 SDK 동작으로 비scan 응답을 분류해야 한다. 단순 byte 삭제·unknown을 free 공간으로 취급·원 실패 PASS 재분류는 하지 않는다. 순수 데이터 취득은 불완전 구간을 표시하며 지속할 수 있도록 하고, 연속 유효 scan을 요구하는 시험 성적과 분리할 것을 제안한다.

### 4.2 동시 처리 부하

현재도 로봇 측 guard·별도 owner thread·비동기 파일 writer는 있다. 이미 구현된 이 원칙을 다시 선언하는 것으로는 해결되지 않는다.

남은 hot path는 다음과 같다.

- ROS sensor callback은 `_record()` 완료 후 최신 sensor를 대입한다 (`teleop_ros.py:287~300`).
- `_record`의 emit 경로에는 CDR 직렬화·SHA·base64가 있다 (`fleet_control.py:210~221`).
- worker emit의 공유 RLock 안에는 deepcopy와 journal/protocol JSON 직렬화가 남아 있다 (`fleet_worker.py:179~191`).
- native 수집은 raw write·emit 뒤 decode하며, 프레임당 beams JSON hash/freeze를 수행한다 (`native_stream.py:201~206,274~281`).
- ROS spin은 명령 queue 대기와 같은 제어 루프에서 실행된다. Python CPU 작업들이 같은 프로세스에서 경쟁한다.

이전 수정에서 immutable frame 공유와 lock 밖 decode/hash는 이미 적용되었다. 이를 다시 미구현으로 보고하지 않는다. 실제 native publish lock 대기 p95 약 0.032ms만으로 200ms 지연을 설명할 수 없다. CPU/GIL/직렬화/ROS executor/publisher/DDS 기여는 분리 계측해야 한다.

### 4.3 논리 결함과 성능 결함을 구분

Arm 실패 `125f54cd-c792-41df-9832-e932d5a1bf25`는 native ring 검사를 통과한 뒤 MOTION_GENERATION_CHANGED로 거절되었다. 반복 자동 fault가 이미 해제된 권한의 generation까지 계속 증가시킨 결함이다. v542 소스의 idempotent 수정은 이 논리 결함을 줄이지만 ROS 지연과 LiDAR 프로토콜을 해결하지 않는다. 설치본은 여전히 원본이다.

ICP 80ms 실패는 실제 Pi에서 관측되었지만 성공/실패 `sample_s` 의미가 다르고 연산 시작·종료 전용 계측이 없어 계산시간의 평균·SD를 정확히 낼 수 없다. 같은 결과가 heartbeat에 반복 노출된 횟수를 독립 연산 실패 수로 세지 않는다. Windows의 빠른 재생 결과를 Pi 실제 성능으로 인수한 것도 부적절하다.

## 5. 공식 시스템에서 가져올 것

공식 문서와 upstream 소스를 2026-10-18 확인했다. 설치 또는 실행한 것은 아니다.

| 대상 | 확인 내용 | TwinPulse 적용 제안 |
|---|---|---|
| [ros2_control Humble diff_drive_controller](https://control.ros.org/humble/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html) | cmd_vel_timeout 기본 0.5초, 속도·가속도·jerk 제한과 timeout 정지 | 제어 설정별 근거·표시·검증, UI와 최종 제어 경계 유지 |
| [ROS2 Humble QoS 공식 원문](https://github.com/ros2/ros2_documentation/blob/humble/source/Concepts/Intermediate/About-Quality-of-Service-Settings.rst) | sensor data는 신속한 최신값을 위해 best effort·작은 queue 사용; deadline/lifespan/liveliness 목적 구분 | 제어용 최신 표본과 분석용 원문 기록을 독립 처리; publisher 호환성 확인 |
| [Nav2 Collision Monitor 현행 문서](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/) | Stop/Slowdown/Approach 모델, source_timeout과 stop_pub_timeout 구분 | 거리·속도·센서 유효기간을 묶은 local 필터, 최신 버전 옵션 무검증 복사 금지 |
| [Nav2 Humble 구현](https://github.com/ros-navigation/navigation2/blob/humble/nav2_collision_monitor/src/collision_monitor_node.cpp) | source_timeout 기본2초, stop_pub_timeout 기본1초 | 참고 기본값이지 2초 안전 표준이나 현재 TB3에 맞는 값은 아님 |
| [Nav2 Humble source 검사](https://github.com/ros-navigation/navigation2/blob/humble/nav2_collision_monitor/src/source.cpp) | 오래된 source를 invalid/ignore로 처리하는 구현 | 구버전과 현행 문서의 실패 동작까지 대조해야 함. 숫자만 복사하면 안 됨 |
| [Foxglove Teleop](https://docs.foxglove.dev/docs/visualization/panels/teleop) | 방향패드·Stop·발행주기·버튼 해제 Stop 설정 | 일반 App의 조작/표시 기준 비교. 기본발행1Hz를 현재250ms lease에 그대로 조합하면 부적합 |
| [Foxglove Plot](https://docs.foxglove.dev/docs/visualization/panels/plot)·[Playback](https://docs.foxglove.dev/docs/visualization/playback) | log time/header stamp/publish time 구분, 기록 재생 | 한 operation의 입력·원본시각·지연·배터리·scan·정지 이벤트를 동기 표시 |
| [ros2_tracing](https://github.com/ros2/ros2_tracing) | ROS 계층 tracing 제공 | publisher·executor·callback 지연 귀속. 현재 설치 지원 여부는 별도 확인 |
| [rosbag2](https://github.com/ros2/rosbag2)·[PlotJuggler](https://github.com/PlotJuggler/PlotJuggler) | 기록/재생과 시계열 분석 도구 | 원 자료를 보존하며 MCAP/rosbag 또는 CSV 분석용 사본을 만들어 재사용 |

TwinPulse를 Foxglove로 대체할 필요는 없다. 외부 도구는 진단·교차검증에 활용하고, 사용자에게는 TwinPulse의 연결/조종/원인 표시/반출 흐름을 유지한다. 공식 드라이버로 교체할 때도 과거 pinned COIN의 각도순서·index0·timestamp 문제 이력(`docs/verification/ad1-observation-transport-20261004.md`)을 확인해야 한다.

## 6. 타임아웃 정책을 어떻게 정할 것인가

1. 연결 준비·정보 조회·파일 반출에는 진행 상태와 용도별 응답 deadline을 둔다. 이 값이 바퀴 출력을 연장하지 않게 한다.
2. 조작 원입력·최종 출력에는 고정된 유한 만료를 유지하되, 각 로봇 프로필의 동작 주기·끝단 제동 시험으로 값을 검증한다. 원 timestamp·sequence·Stop 이후 늦은 입력 차단은 보존한다.
3. 센서 신선도는 부팅/센서ON/추적ON/기록ON/Isaac표시ON/장시간 부하별로 나눠 관측한다. 결함을 수정한 정상 구간의 p99/p99.9·최대·연속 공백과 clock 불확실성을 함께 본다.
4. 평균+3 SD를 자동 공식으로 쓰지 않는다. 정규·독립 가정이 성립하지 않고 부하 상태가 혼합되어 있다. 표본당 0.1% 초과도 20Hz에서 단순 기대치로 시간당72회이므로 제품 목표는 false pause/hour와 연속 가용시간까지 포함해야 한다.
5. 허용 지연 상한은 물리 여유로 제한한다. 예: `필요 여유 ≥ |v|×실효 지연 + 제동거리 + 측정·형상 불확실성`. 회전은 외곽의 swept 영역을 사용한다. watchdog과 다른 지연이 겹치는 경로는 중복 합산하지 않는다.
6. 200→500ms 추가300ms는 등속0.03m/s에서9mm,0.05m/s에서15mm 이동에 해당한다. 이 계산에는 실제 제동·움직이는 장애물·시각/형상 오차가 빠져 있으므로 안전 승인값이 아니다.
7. 통계적 요구 지연이 물리 상한을 넘으면 부하를 줄이거나 속도/작업 범위를 조정한다. 오류가 날 때마다 자동으로 timeout을 늘리지 않는다.
8. ICP 계산 예산과 pose 결과의 유효 나이를 분리한다. 오래된 결과는 STALE이며, 새 작업마다 오래된 계산을 줄 세우지 않는다. pose가 필수인 차체 정체·목표 도달 기능은 미검증으로 남긴다. 간단한 센서 표시/원문 수집까지 종료할 이유는 없다.

사용자 설정은 속도·여유거리·사용 목적 중심으로 유지하고, 펼친 진단에는 측정값/제한/지속시간/원인/회복조건/프로필버전을 제공한다. 승인 없는 실시간 자동 기준 완화는 하지 않는다.

## 7. 권장 구현·검증 순서

### A. 로봇 OFF에서 먼저 해결

1. 이번 원문을 고정 회귀 자료로 삼아 패킷 분할·11바이트 응답·손상·누락·역순·재연결을 재생한다. SDK와 결과를 대조하고, 정상 비scan 패킷이면 검증된 분류로 처리한다. unknown이 남으면 그 구간의 품질은 명시한다.
2. 동일 bytes/타이밍에 native decode만, frame 처리 추가, ICP 추가, raw mirror/log 추가, 전체 조합을 비교한다. 원본을 사용한 replay는 고정 성공 응답 시험과 다르지만 실물 통과로 합산하지 않는다.
3. 최신 control snapshot 공개를 동기 직렬화/전송 뒤에 두지 않는다. 제어용 최신값 전달과 원문 보존을 분리하며 bounded queue 초과·기록 손실은 별도로 기록한다. 관측 근거가 필요한 동작은 기록 불능 시 일시정지한다.
4. CPU가 큰 ICP/native 작업을 별도 process 또는 검증된 C++ adapter로 분리한다. 단순 thread/MultiThreadedExecutor 추가만으로 Python CPU 경쟁이 해결된다고 가정하지 않는다. 기존 immutable frame/비동기 disk 구현은 재사용한다.
5. startup/정지/입력/감독/추적/연결/기록 상태를 분리하고 generation 반복 회전·late reply를 회귀한다. soft 지연 경고의 회복에는 hysteresis를 적용할 수 있으나, 유효기간을 넘은 입력을 추가 대기시키는 데 쓰지 않는다.
6. 각 제한을 이름·단위·clock·근거·실측분포·동작·회복·검증버전과 함께 단일 계약으로 정리한다. 250/300/400/500ms가 여러 계층에서 서로 충돌하는 변경을 방지한다.
7. 설치 후보를 한 번 동결하여 실제 Electron 사용자 흐름과 원문 replay를 검증한다. delay/loss/reorder/disk-stall/CPU-load 시험은 일반 사용자 시험과 구분하고 실제 출력 장치와 연결하지 않는다.

### B. 다음 전원 세션에 묶을 것

먼저 이동 없이 같은 Pi에서 ROS 단독→native→ICP→기록 전체를 켜고 끄는 짧은 비교를 수행한다. 로봇 내부 구간 시각과 원 timestamp를 함께 수집한다. 통과한 동일 설치·동일 연결에서 정지 수집→Arm→정지 관측→수동/해제→채팅90도→단일360도+scan→Stop/반출을 수행한다.

PC replay만으로 Pi 스케줄·serial·RF·제동 성능을 증명할 수는 없다. 그러나 지금 확인된 parser/계약 결함을 고치지 않은 상태에서 같은 전체 현장 시험을 다시 시작할 필요도 없다. 새 하드웨어 미지수와 이미 알려진 소프트웨어 결함을 분리해 전원 세션의 효율을 높인다.

## 8. 다음 준비 판정에서 요구할 증거

- 원본 전체 bytes와 packet/frame accounting이 맞고, 주기적인 unknown 처리의 근거가 확인된다. 원 실패는 변경하지 않는다.
- ROS/control 필수 경로가 native/ICP/기록 부하에 밀리지 않는 단계별 계측이 있다. PC 성공과 실제 Pi 결과는 별도다.
- 수신은 최신인데 원본은 오래된 상황, 입력 만료, 실제 연결 단절, 추적 계산 부족을 UI가 다른 이유로 보여준다.
- 원 장면·chat·operation·command·profile·input SHA 계보에서 Stop 요청/수락/출력/관측과 timeout 원인을 따라갈 수 있다.
- 동일 설치의 기본 조작·취소·회복·정상 종료가 사용자 경로로 통과한다. 바퀴 시험 이전에는 실물 주행 완료로 표시하지 않는다.

검토 중 Nebius 호출·사진 전송·로봇 접속·새 설치·제품 코드 변경은 0이다. Tavily 심층 조사 도구는429 요청 제한으로 실패해 공식 웹 문서/소스 직접 조회로 대체했다. 위 해결책은 구현 전 검토안이며 기존 인수 상태를 상향하지 않는다.
