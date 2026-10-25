# 실물 자연어 수집 작업 준비 — 2026-10-25

현재 상태: **이 PC의 명시 Test entry에서 다음 감독 실물 로컬수집 시험을 시작할 소프트웨어 준비 인수**. [최종 gate03 47/47](../../outputs/physical-task-preparation-20261025-01/acceptance03.json) · [보고서/실제 검수 영상](../../outputs/physical-task-preparation-20261025-01/report.html). 로봇은 사용자 감독이 없는 동안 연결·구동하지 않았다. 실제 하드웨어 성공·방전체 측정·공개제품 출시 준비라는 뜻은 아니다.

## 바꾼 구조

TwinPulse의 채팅/Robot command → 설정된 planner의 capability 조합 → 별도 정확 계획 Review/Run → 기존 finite executor를 유지했다. 문장별 함수를 추가하거나 모델이 생성한 코드를 실행하지 않는다. `survey`는 제자리360도가 아니라 관측 위치를 선택해 이동·정지·측정·재계획하고 귀환 예산을 예약한다. 상한은12m/600초/128 finite segments이며 whole-room coverage 인증은 아니다.

실물 공통 작업을 무조건 HELD하던 경로에 다음 어댑터를 연결했다.

- `twinpulse_core/physical_task_observation.py`: 완전한 native ring·원 raw/node SHA·serial receipt 시각·원 wheel odom의 분리된 yaw·동일 encoder 정지 구간·고정 pose epoch를 결속한다. Stop 이후 원 ring부터 pose 시각까지 stationary bracket이 있어야 한다. timestamp를 새로 찍어 신선하게 만들지 않는다. 명목 센서 설치값은 실측 TF/deskew/차체 위치 증명이 아니다.
- `twinpulse_app/physical_task_map.py`: 실제 유효 ray만으로 free/occupied/unknown을 쌓는다. 시작 원점은 최초 승인 쌍에 고정한다. 누적 지도는 후보 선택에 사용하되 매 실제 primitive는 최신 단일 정지 ring의 free cell로 다시 검사한다. frame/boot/연결/설정 변경과 odom reset은 자동 재기준화하지 않는다.
- `fleet_control.py`/`fleet_worker.py`: 기존 bootstrap Stop 증거와 구분되는 request·connection·새 motion epoch·실제 zero/OFF readback receipt를 발행한다. 관측 계산은 최종 motor-output tick/Stop mutex 밖이다.
- `physical_live_session.py` → `physical_fleet_adapter.py` → `robot_fleet.py`: 원 ring/odom 나이와 실제 PC 수신 이후 경과를 보존한다. 네트워크 transit 시간은 unknown이다. 취소 guard는 queue 진입과 실제 wire admission에서 확인하며 OS pipe write 동안 Stop lock을 잡지 않는다. 이미 admission된 write의 취소를 소급 보장하지 않으며 native nonce/expiry가 남는다.
- `robot_task_service.py`: 실물 finite 완료 뒤 별도 exact Stop/readback·applied를 확립하고 새 정지 관측을 기다린다. 복합 이동도 매 동작 후 관측한다. 지도/pose fault와 무관하게 Stop 및 늦은 정확 ACK는 처리한다. Stop 미확정은 실패와 UNKNOWN ownership으로 남긴다.

USD/ICP 정합 실패만으로 이 로컬 수집 경로를 차단하지 않는다. 반대로 USD상의 가구 목표로 자동 이동하는 `navigate`는 세계정합 전 계속 HELD다. wheel-estimated local frame은 독립 LiDAR localization·측정된 차체 pose·SLAM loop closure가 아니다. 사진 추정 장애물·원RoomPlan30mesh·기존 정합 review/POOR_FIT는 변경하지 않았다.

## 발견·보완한 실패

1. bootstrap receipt를 일반 Stop ACK처럼 읽는 오류, odom `[x,y,z]`의 z를 yaw처럼 사용하는 오류, peer 순수 모듈 누락/전달 가능성을 분리했다.
2. packet 생성 시점으로 원 sensor age가 갱신되던 문제, pose 이후까지 encoder bracket이 없는 문제, 로컬 fault가 Stop ACK 확인도 막는 문제를 수정했다.
3. Astra가 실제 native 완료→PC 자동 Stop fence→늦은 heartbeat의 epoch 경쟁과 일반 복합 move 뒤 관측 누락을 찾아 보완/재검토했다. fake survey만으로 놓칠 수 있는 조건이다.
4. 새 설치 survey02는15cm 계획 뒤 귀환 중 **OBSTACLE_STOP으로 실제 실패**했다. 기존 SIM executor는 `.105m` 차체 반경 + `.10m` skin + `.0025m` substep 여유를 요구했다. 계획17cm와 불일치했다. 기존 보호를 낮추지 않고 같은 상수를 공유하여 SIM effective 실행 검사는20.75cm, 계획22.75cm로 맞췄다. 사용자 최소15cm는 별도로 기록한다. 실물15/17cm와 기존 native footprint/센서/제동 보호는 유지한다.15cm가 실측 차체 외곽+15cm 보장이라는 뜻은 아니다.
5. 원 기하의 imported navigation `obstacles=[]`만 재생한 clearance-replay01 진단은 원 정지를 재현하지 못해 FAIL로 남겼다. 실제 non-free cell의 manual-box union을 포함한02는 같은 정지와 수정 경로의 우회·귀환을 재현했다. 원 실패를 성공으로 덮어쓰지 않았다.
6. tests01/04의 fixture 오류, survey01의 기존 SIM pose yaw2π/부동소수점 차에 대한 bit-exact 검사 실패, open02의 다른 검수기가 패널을 닫아 Build 문구를 관측하지 못한 조정 오류는 제품 실패와 구분하고 원문을 보존한다. cold 재검수는 단독으로 수행한다.

## 검증과 한계

- `outputs/physical-task-preparation-20261025-01/tests07/`:203개 device-free 보조시험. 실제 bridge/adapter/fleet projection 및 queue guard를 사용하는 시험과 synthetic physical finite composition/수집·귀환·Stop을 포함한다. 센서와 모터는 가짜이며 실물 PASS가 아니다.
- `bundle02/`:114개 전체 wire manifest를 실제 bootstrap receiver로 격리 수신·hash검증·device 진입 전 import. 별도 SDK/ROS 빌드나 Pi 실행은 아니다.
- `installed01.json`:최종 설치1700파일·전 source/가상 npm117원본 hash·fresh `python -I -B` App/Core import 및 cold-history complete manifest 검증. 공개 일반 release의 물리 기능을 켠 것이 아니라 명시 Test entry의 개발 후보이다.
- `original-replay01/`:원30segment/48376event를 보존하고 stationary eligibility105쌍을 확인했다. 원 callback receipt/source age 재구성은 정확한 원 `RosLink.rows.t`와 같다는 보장이 없으므로 **REPLAYED_WITH_LIMITS**다. live packet/독립 차체 motion 증거가 아니다.
- `clearance-replay02/`:원 실패 지도/명령/원점에서 기존 executor 보호와 새 계획의 호환 검증. 별도 실제 UI 여정이 필수다.
- `survey03/`:최종 설치 실제 Nemotron→Review/Run→11finite/명령거리2.006145570m/15actual SIM관측→XY/yaw귀환·Stop·OFF·Disconnect. 결과 PARTIAL/whole-roomfalse다. renderer 검수 영상이며 완성 제출 영상/OS커서/실물 카메라가 아니다.

최종 설치 `20261024T180541Z-be5c534652eb`, source manifest `be5c534652eb48a1b1c5a7cf51cde3cacff99d6b0ddc0cea8db6423546c3c894`. compose01은5finite/.2m/XYyaw귀환Stop, cancel01은PLANNING에서Stop·최종worker종료/늦은응답무시·0motion을 확인했다. 단독open03/cold01은같은프로젝트/사진후보·30원mesh+추정prop/명시Build와3physical모두무권한을 확인했다. 모든3ownedlaunch는두root자연0/innercleanup·Kit포함27exact원문을보존했고선택liveness3부재는명시했다. 앱닫힘·lock/8765/19222 listener0이다.

최종 gate03은 Stop/OFF의 원 request/robot/operation/connection·old→new→applied, OFF frame의 engine/stage/applied_revision·클릭 이후시각/몸체유지/점제거, 취소의 원proposal_binding·worker종료/outputignored·0child와9음성반례를 결속한다. 원 gate01은 결속이 약한 옛 검수로 보존하며 최종판정에 사용하지 않는다. gate02는 PLANNING job에 아직없는 실행op/conn 필드를 요구해 FAIL한 검수오류다. 실제원proposal_binding과Plan전start를대조한03으로수정했으며원App결과/자료를고치지않았다. 추가실물/모델호출없이원문으로검사했다.

이번 텍스트 호출은4회/7154tokens(취소후무시1790포함), 누적17승인중13claim·23462tokens/4미사용이다. 자동재시도0·사진/USD/좌표/실물로그외부전송0이다. 검수영상은114.680s/52.080s/23.560s이며0.560s cold영상은권한복원관측뿐이지전체시작녹화가아니다. 모든영상은원PTS/DTS와전체decode를확인했다.

## 다음 감독 실물시험

1. 사용자가 로봇 ON·충전선 분리·현장 감독·즉시 전원 차단 가능을 새로 확인한다. 취침 중 무인시험은 하지 않는다.
2. `Start-TwinPulse-Test.cmd`로 최종 설치를 열고 기존 거실 프로젝트/실물 등록을 선택한다. 별도 SSH 우회나 새 iPhone 앱은 필요 없다.
3. 기존 Connect → Prepare → 실제 heartbeat/전압/원 LiDAR·정지 수집 → 명시 Arm → bootstrap Stop readback을 확인한다. 이전 세션/cold 기록은 권한을 복원하지 않는다.
4. Robot command 또는 채팅에 방 안의 도달 가능한 공간을 이동 측정하고 출발점으로 돌아와 정지하라는 목표와 예산을 입력한다. 예: `Explore the reachable room, collect LiDAR observations while moving, return to the start and stop. Limit the task to 8 metres, 600 seconds and 128 finite segments.` 별도 text-only 모델 동의와 exact plan Run이 필요하다. Arm 잔여시간이 전체 계획 예산보다 짧으면 Run 전 새 명시 확인이 필요하다.
5. 시작 stationary pair → 유한 이동 → 새 exact Stop/readback → 다음 native pair → free-space 재계획을 확인한다. 정합 불일치와 실제 sensor/충돌/배터리/기록/Stop 위험을 구분한다. 반복되는 단순 현장 “움직였나요” 질문을 증거로 사용하지 않는다.
6. 원 packet/command/readback/wheel·LiDAR와 중단 조건을 저장하고 종료 Stop/OFF/Disconnect/정상 Exit를 확인한다. 몸체/제동·정합·실제 방 전체 coverage는 실제 데이터로 별도 판정한다. 보호를 없애거나 실패를 스킵하여 완료하지 않는다.

## 지금 하지 않은 것

실물 접속·주행, SSH 우회, 새 ROS/SDK/iOS 앱·모델 설치, 유료 GPU·클라우드, 사진/USD/좌표/실물 로그 외부 전송, 사용자 자료 삭제, GitHub 업로드는0이다. 승인된 텍스트 검증만 별도 call-claim으로 계산한다. 수동조종 기능은 동결하며 기존 독립 단일 finite 경로는 유지한다.
