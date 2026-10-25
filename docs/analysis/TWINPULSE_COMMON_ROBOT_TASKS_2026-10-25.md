# 공통 자연어 로봇 작업계층 — 구현과 실제 검증 범위

현재 v646: 공통 physical task의 native stationary pair/wheel-estimated local map→finite executor→exact 새Stop/readback→새관측·귀환을 연결했고, 최종설치 `20261024T180541Z-be5c534652eb`의 [gate03 47/47](../../outputs/physical-task-preparation-20261025-01/acceptance03.json)이 다음 감독 실물 로컬수집 시험의 PC 준비를 인수했다. 실제SIM11finite2.006m15scan/복합5finite·Stop취소/cold·정상종료를 확인했다. USD/ICP 미정합만으로 수집을 차단하지 않으나 semantic navigate/세계정합·몸체/제동·방전체 coverage는 미인수다. 사용자15cm는최소값이며 기존SIM실행보호와의 실제불일치를 보완해 SIMeffective20.75/계획22.75cm, physical15/17cm를 쓴다. 수동/native보호를 낮춘 것이 아니다. [최신 구현·원실패·실행절차](TWINPULSE_PHYSICAL_TASK_PREPARATION_2026-10-25.md).

## 아래는 v644까지의 보존 이력

2026-10-25 / v644. 사용자 요청으로 공통 task의 지도상 충돌 검사 envelope를 `.30m`에서 `.15m`로 변경했다. 이는 로봇 기준점에서 장애물까지의 지도상 거리이며, 실측 차체 외곽에서 추가 15cm를 보장하는 값은 아니다. 계획 여유 `.02m`를 더해 survey/귀환/객체 접근 경로계획은 `.17m`, 실제 직렬화된 이동 구간 검사와 기록은 `.15m`를 쓴다. unknown 차단·동적 peer 검사·Stop·실물 제동/센서 보호는 유지하며, 독립 단일 객체 접근의 기존 기본값 `.25m`는 변경하지 않는다. 새 실물 task는 여전히 HELD다. 아래 v643 결과는 **이전 `.30/.32m` 설치본의 역사적 SIM 한정 인수**이며 변경본의 실제 Isaac/실물 인수로 재사용하지 않는다. [이전 보고서/실제 녹화](../../outputs/robot-task-20261025-01/report.html) · [이전 gate06 68/68](../../outputs/robot-task-20261025-01/acceptance06.json).

설치 `20261024T170219Z-25197f6df7ec`/1698 exact에 반영했다. [새 정책 verification02](../../outputs/robot-task-clearance-20261025-01/verification02.json)는 전체 packaged source와 설치 경로만 사용하는 격리 subprocess의15cm 경계/17cm 계획/unknown 차단·기존 기본값을 검사한다. Python151 및 수정 후task24는 중복되는 보조 회귀다. 새 UI/Isaac/실물 주행은 NOT_RUN이며 모델 호출0/앱 시작0/실물0이다. verification01의117개 npm runtime 가상목적경로를 실제 repo 경로로 잘못 검사한 FAIL은 보존했다. builder와 같은 runtime 원본117개를 명시 remap하여 해시를 모두 확인했으며 검사 제외나 제품 기준 완화로 통과시키지 않았다.

## 구현한 경로

TwinPulse 채팅 또는 Robot command → 한 번의 text-only configured planner 요청 동의 → 데이터 계획 제안 → 정확한 단계/방향/거리·각도/전체 예산 확인 → 별도 Run → 기존 finite executor → 정확한 child 종료/새 적용 Stop epoch → 관측 → 현재 기하에서 다음 경로 재계산 → 귀환/최종 Stop.

허용 capability는 `observe`, `move_relative`, `navigate`, `survey`, `return_to_start`, `stop`이다. 모델은 이 능력을 순서대로 조합하며 임의 Python·shell·설정 변경을 실행하지 않는다. 새 문장마다 Codex가 별도 제어 함수를 추가할 필요는 없지만, 실제 미지원 센서/행동 자체는 검증된 capability 구현이 필요하다. 무제한 agent나 자연어의 모든 의미를 보장하는 시스템은 아니다.

- 계획은 최대12단계, 전체 최대12m/600초/128 finite segments다. 기본 제어속도·센서/Stop 보호를 완화하지 않았다.
- 단일 이동/회전·수동조종·즉시 Stop은 기존 경로를 유지한다. `Stop survey`, `Cancel task`, 즉시 정지는 모델/모드/대기 질문보다 우선한다.
- `survey`는 고정 방 순회 경로 또는 제자리360도가 아니다. 현재 geometry에서 미방문 관측 위치를 고르고 .4m/π 이하 finite 이동·회전 후 새 관측과 경로를 확인한다. 귀환 거리·회전시간·관측·segment 여유를 예약한다.
- 경로 prior의 free cell은 측정 범위가 아니다. actual SIM surface rays·원 시각·sensor world pose·connection/operation/scene binding을 저장하고 별도 EvidenceGrid를 누적한다. `whole_room_coverage_verified=false`다.
- `return_to_start`는 역명령 나열이 아니라 현재 위치에서 재계획하고 출발 XY와 yaw로 복귀한다. 최종 각 .04m/.04rad 검사와 실제 새 관측을 남긴다.

## 승인·경합·정지

모델 호출 동의와 Run 승인은 분리한다. 모델로 나가는 것은 시험 명령문·capability 이름·SIM/physical 종류뿐이며 사진·USD·좌표·실물 로그는 제외한다. 한 승인당 actual dispatch는 최대1회, 실패/unknown도 사용으로 계산하며 자동 retry/repair는 없다.

계획 SHA·project/scene의 effective state·선택 robot/kind·connection/operation을 결속한다. scene transaction/다른 robot 작업과 같은 admission을 사용하며 broker 직접 Build/Reset/Run도 상호 제외한다. Stop/manual/Disconnect/focus 변경은 별도 cancellation permit을 먼저 철회하고 오래된 child가 최신 epoch를 재사용하지 못하게 한다.

정상 다음 child는 정확한 이전 request ID·정상 terminal 결과·새 zero-output epoch의 engine 적용 뒤만 허용한다. Stop 미확정은 실패 표시와 별개로 UNKNOWN ownership을 유지한다. 늦은 ACK는 같은 pending pin에만 적용되며 새 Stop pin을 지우지 않는다. 취소는 fleet admission 뒤 Stop을 직렬화한다. 재실행/재열기는 실행권한을 복원하지 않는다.

## 실제 발견한 실패 — 덮어쓰지 않음

1. `ui01`: 로봇 roster 접근성 이름 prefix를 잘못 예상한 검수 선택자 실패. 모델0/이동0.
2. `ui02`: 실제 선택 UI가 radio+Continue인데 button으로 찾은 검수 실패. 계획 질문까지만 생성, 모델0/이동0. 별도 Cancel/Stop/OFF/Disconnect 후 전체 재시험.
3. `ui03`: 실제 Nemotron이 observe/survey/return/stop 제안. 원 RoomPlan SIM에서 6 finite, 명령거리 약1.334m, 새 관측10회, exact new-applied Stop·XY 귀환을 확인했다. 당시 release `20261024T153112Z-5be46fec1627`. 원source의 단위 선택은 SIM용이며 실제 거실 실측 정확도가 아니다. 결과 PARTIAL이며 방 전체 coverage·실물 증명이 아니다.
4. `compose01`: 같은 설치에서 실제 모델이 “10cm 전진 →30° 좌회전 →복귀 →정지” 설명과 달리 실행 step2개만 반환했다. 앱이 받은2개 완료를 목표 완료(COMPLETED)로 표시한 결함이다. 최종 약10cm 위치 차로 actual UI gate가 FAIL. 원 응답/작업 record/영상/오판정은 보존한다.

4번 보완은 원 출력을 자동 수정하는 것이 아니다. provider 응답과 Run 직전에 원문에 명시된 return/survey/stop의 누락·return 뒤 추가 이동·마지막이 아닌 stop을 거절한다. 설명문은 실행 증거가 아니다. 방향/거리·각도도 Review에 명시하며, 귀환은 최종 XY/yaw 관측으로 확인한다. 이는 제한된 명시 요구 검사이며 자연어 의미 전체를 검증했다고 말하지 않는다. 같은 원실패 문장의 최종 compose04 재시험은 통과했다.

5. `survey04`: 7finite/명령거리1.178856594m/10관측 뒤 `START_OR_GOAL_BLOCKED`. 원 scene을 별도 OpenUSD Stage에 같은 author로 재생했을 때 마지막 실제 pose와 occupied 셀 `[19,8]` 사이가 `.2999999840645028m`라 같은 거절을 재현했다. 원 live grid 자체를 캡처한 증거는 아니다. 여유 없는 접경 waypoint와 실제 yaw/직렬화된 이동의 미세 차이가 문제였으며, 거절 자체는 정상 보호였다.
6. 계획 반경을 `.32m`로 보수 강화하고 실제 직렬화된 이동 전구간은 기존 `.30m`/unknown 차단으로 재검사한다. pose 스냅·충돌 epsilon 완화는 하지 않았다. `.001rad` 경로 회전 기준과 귀환 시간/segment 예약을 함께 맞췄다. 최종 발행 직전에 같은 pose·map·정지된 peer 로봇의 ID/연결/위치/epoch를 재확인하고, 다른 SIM이 실행 중이거나 Stop 적용 미확정이면 새 task를 거절한다. 최초 navigation map 원문·출처·해시도 저장한다.
7. `survey05`: 실제 모델이 survey 대신 고정 사각 순찰을 제안하고 left/right 회전을 metres로 설명했다. host가 `REQUESTED_CAPABILITY_MISSING: survey`로 **실행 전에 거절/segments0**했다. 원 응답/2170tokens와 검수기의 READY 대기 timeout을 보존한다. 기존 필수 capability 이름을 실제 모델 입력에 명시하고 단위를 강화했으나 자동 repair/retry는 추가하지 않았다.

## 최종 실제 결과와 정확한 범위

설치 `20261024T162654Z-7e6badc20842`, source SHA `7e6badc20842ea65e4fb56605a6a933cd557c8702462faa4921e4f8218904d53`,1698 exact files다. 모든 실제 모델 호출은 configured `nvidia/nemotron-3-super-120b-a12b`를 사용했다.

- `survey07`: 원 survey04의 문장·출발 pose·같은 room grid를 유지했다. 실제 계획은 survey→return_to_start→stop이며 **11finite/명령거리2.219718223m/14 actual SIM scan**을 저장하고 XY/yaw 복귀·새 Stop 적용·OFF 새 epoch 적용/CONNECTED/scan null·점 제거 프레임/PNG→Disconnect를 확인했다. 결과는 `PARTIAL`, `whole_room_coverage_verified=false`다. 단일 제자리360도나 사전 녹화된 경로가 아니다. 실제 통과한 영역 전체를 측정했다는 뜻도 아니다.
- `compose04`: 같은 원실패 문장의 전진10cm→좌회전30°→복귀→정지를 실제 모델이4단계로 제안했다. 5finite/왕복 명령거리.2m·실제 위치와 방향 복귀·Stop/OFF/Disconnect를 확인했다. 수치 오차는 결정론적 Isaac 기구학 값이며 실물 정밀도에 인용하지 않는다.
- `cancel07`: 모델이 PLANNING 중인 원 Stop ACK·새 epoch 적용을 확인했고 늦은 응답은 무시, CANCELLED/segments0/workerfalse다. usage는 UNKNOWN이 아니라1877tokens로 확인된다. 첫 Stop의 정확한 새 applied epoch는 같은 operation의 두 번째 Stop 응답에서도 관측되며 원 첫 ACK를 그 응답으로 대신 만들지 않는다.
- `cold04`: 같은 설치를 정상 종료/다시 시작하고 Home의 저장 채팅→Reopen→명시 Build 뒤 robot DISCONNECTED/계획·Run 카드·실행 복원0을 확인했다. `.72s/2frame` 영상은 짧은 무권한 관측이고 Home→Build→종료 전체 영상이 아니다. 그 실제 여정의 원 open09/exit 로그는 별도다.
- `off-dom02`: 모델0/이동0의 **독립 sensor-render 여정**이다. own operation/ACK/new applied epoch·CONNECTED/OFF/scan null과 실제 DOM canvas live/frame/captured/scene/stage를 HTTP 프레임에 결속하고 디코딩된 픽셀/SVG·PNG의 ON점→OFF제거/몸체 유지를 확인했다. survey07 원 DOM frame ID 미기록을 이 자료로 소급보완하거나 작업의 연속 증거로 이어붙이지 않는다. off-dom01의 숫자 frame ID/DOM 문자열 키 검수 오류는 보존하고 전체 fresh02를 실행했다.

최종 gate06은68/68 `PASS_SCOPED_NATURAL_TASKS_SIM`, Python150/Web120/TypeScript는 보조다. 원문 scan–pose/event SHA·navigation 파일명/내용 해시·실제 EvidenceGrid 전체 재생·exact child/Stop/OFF/Disconnect 결속·현재 설치/소스 일치·원 실패·예산을 검사했다. source와 같은 알고리즘의 grid 재생은 독립 물리 측정이나 새 관측이 아니다. 모든9ownedlaunch의18root 자연 종료·Kit 포함81원문 exact와 optional liveness9개 부재를 기록했다. 완성1분 제출물이 아닌112.600s/54.680s/23.320s 실제 renderer 검수 영상의 원 PTS/DTS·전체 decode·첫/중간/끝 픽셀을 확인했다. 실제 pointer annotation은 OS cursor가 아니다.

acceptance01의 optional 파일 처리, acceptance04의 OFF 추가 zero-epoch 추적 누락, acceptance05의 survey06 OFF 적용 관측 미확인 및 startup07 observer 실패를 보존했다. survey06의 이동 성공을 전체 정리 인수로 승격하지 않고 기록기 보완 후 원 조건 전체 survey07을 다시 실행했다. Astra는 접경 재생·peer P1·잠금/취소/귀환 예산·최종 원문/68항목을 독립 대조했고 해당 범위 새 확정 P1/허위 승격을 찾지 못했다.

사용자 text 승인3+2+2+10=17 중 **9claim/9usage 확인/16308tokens·8미사용**이다. 자동 재시도0. 원 approval 파일의 requests_submitted:0은 초기 스냅샷이며 현재 사용량이 아니다. 사진·USD·좌표·실물 로그 외부전송0, 실물 접속/구동·새SDK/시스템/iOS/유료 자원·GitHub 업로드·삭제0이다.

## 앱에서 사용하는 방법

1. 일반 TwinPulse에서 장면을 열고 명시적으로 Build한다. Robots에서 SIM을 선택·Connect·Prepare한다. 이번 실제 검수는 같은 `Start-TwinPulse-Test.cmd` 진입 파일을 execution 도구로 시작하고 설치된 Electron UI로 조작했으며 native double-click은 NOT_RUN이다.
2. Robot command 또는 채팅에 예를 들어 `Measure the reachable room by moving to observation locations, then return to the start and stop. This short SIM test has a total travel limit of 2.5 metres, 180 seconds and 64 finite segments.`를 입력한다. 채팅은 `new/add/change` 모드와 무관하게 즉시 Stop을 먼저 처리한다.
3. text 전송 범위를 보고 **Plan task → Continue**를 선택한다. 제안된 방향/거리/각도/순서/전체 예산을 확인한 뒤 별도로 **Run task → Continue**한다. 제안은 아직 이동 권한이나 완료 증거가 아니다. 센서 관측은 각 유한 이동/회전 뒤 fresh stationary scan–pose 쌍이며 모든 원 주파수의 실물 연속 스트림을 수집했다는 뜻은 아니다.
4. Stop/Cancel task/즉시 정지로 작업 권한을 철회한다. 미확정 Stop은 ownership을 유지하며 cold reopen은 연결·실행 권한을 복원하지 않는다. 새 실물 task는 아래 미완료 계약 때문에 HELD이며 자동 Prepare/Arm하지 않는다.

## 실물 미완료와 유지하는 결정

새 공통 task의 실물 Run은 `PHYSICAL_TASK_HANDOFF_AND_CURRENT_LOCAL_MAP_POSE_CONTRACT_REQUIRED`로 HELD다. 기존 단일 finite 성공은 현재 handoff와 다단계 수집·귀환 계약의 대체가 아니다. field tracking은 ESTIMATED/UNQUALIFIED이고 fault 시 epoch/원점이 바뀔 수 있다. 이를 로컬 지도/귀환 보장으로 재명명하지 않는다.

다음 실물 adapter는 기존 raw scan·odom 원자료와 현재 시각/TF·local pose epoch·unknown-cell·Stop readback을 결속해야 한다. 세계/USD 정합이 안 맞는 것만으로 수집을 중단할 필요는 없지만, 유효한 로컬 관측 위치와 안전 제어가 없다는 사실은 별도다. `SURVEY_LOCAL`/`SESSION_LOCAL_OBSERVED` 기존 계약을 재사용할 수 있으나 현재 새 task와의 실물 연결은 완료되지 않았다. 이 문서는 로봇을 켜달라는 요청이 아니다.

원 RoomPlan·사진 overlay·원 실물 48376행/30segment·몸체 UNQUALIFIED·POOR_FIT·실물 alignment HELD를 변경하지 않았다. 신규 SDK/ROS/iOS/유료 GPU/외부 자료 업로드/실물 구동/Git push는 하지 않았다.

## 검증 자료

- 로컬 artifact: `outputs/robot-task-20261025-01/`.
- supplement: `tests/integration/test_robot_tasks.py`, 채팅/기존 fleet/navigation/model move 회귀 및 web routing/RobotFleet 회귀. fake engine/model을 쓰는 테스트는 실제 Isaac/모델 검수의 대체가 아니다.
- 실제 UI: `scripts/verify_robot_task_ui_20261025.mjs`. 고정 응답·request interception·직접 product API 쓰기 없이 설치된 동일 Electron과 현재 Isaac을 조작한다. 실제 pointer annotation 녹화는 renderer capture이며 OS cursor/실물 카메라 영상이 아니다.
- 원 실패 release의 live01은 정상 Exit 후 launch `ae70462e7cab4c74832ab20feee7d4a2`의 Kit 포함9개 원문 exact/선택 liveness1개 부재를 `runtime-copiesruntime-copies01/`에 동결했다. 이후8launch도 같은 기준이다. 이후 결과가 이전 실패 원인을 지우지 않는다.
- 최종 전송/검수/권한 범위는 위 v643과 gate06을 따른다. 완성1분 제출 영상이나 실물 준비완료를 주장하지 않는다.
