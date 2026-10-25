# RoomPlan·사진·수집주행의 전체 연결

## v655 실제 이동 자료 확보 — 자율 순회·복귀 미완료

같은 설치1387861a7bfd의 실제 survey→return→stop은 `TASK_LOCAL_FRESH_RING_REQUIRED_BEFORE_MOTION`/0child FAILED다. Astra가 `_survey`의 계획용 `_geometry→PhysicalTaskMap.scene` 원500ms gate에서 child 직전 fresh ring 취득보다 먼저 실패함을 확인했다. 이전 보완은 이 경로를 커버하지 못했다. PC 단계 시각은 없어 정확 지연/v653 단독 원인은 미확정이다. 다음 최소 변경은 **계획 전용 누적지도와 엄격한 child 전송 freshness의 명시 분리**다. Map.scene와 _geometry 종료 age gate 양쪽을 검토하고, 계획 조회가 pin/권한을 만들거나 unknown을 free로 바꾸지 않도록 해야 한다. 아직 미구현이다.

별도 승인 후 기존 앱 finite 전진1m·좌90°·전진0.5m·좌1.505504rad 네 건 COMPLETED/Stop 확인, 복귀 전진0.97m는 .0181729m에서 FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP/Stop 확인이다. 원 body delta1.765975mm<2mm를 정확 재구성하는 tracking 쌍은1.186796초지만 첫 PUBLISHED 전501ms 표본을 포함하고 마지막 표본은685ms 뒤다. 실제 모터 시작 독립계측/guard 양끝 receipt가 아니며 동기화되지 않은 encoder 전체/target progress와 비교해 정체·슬립을 단정하면 안 된다. reset 후 progress 잔존값도 현재 실패와 구분한다. 다음 보완은 거절 순간 두 추적 표본·출력 경계·동일 구간 encoder·require_body 결속 진단이며 기준/Stop 완화 없이 검토한다.

원166471event/383520936bytes·3807scan/5359pose heartbeat 전SHA·행수·바이트 COMPLETE, wheel progress 합1.516168m/귀환false다. 준비/정지 포함796.845초를 전체 이동/방 coverage로 세지 않는다. 최종 Stop torqueOFF/zero·LiDAR OFF·Disconnect·정상 root둘0/inner PRE_CLOSE_COMPLETE·Kit 동결 확인. 제품수정/새설치0·text1/사진0·50중13사용37남음·raw/USD/좌표 전송/SSH/SDK/시스템/삭제/GitHub0. in-place의 place 오분류400/409도 미해결 보존했다. 과거 생성 build만 NTFS 압축/원byte 동일·삭제0, 원영수증 scope 오류는 별도 정정했다. [현장 결과·원자료·부분 녹화](../../outputs/robot-moving-survey-20261025-01/report.html) · [Astra 결속 검토](../../outputs/robot-moving-survey-20261025-01/astra-body-window-review01.json). 아래 v654는 이전 한정 보완 이력이다.

## v654 데이터 우선 보존·PC 보완 설치 — 새 실물 이동 미실행

사용자가 출발 전 재시험 시간이 없다고 하여, 바퀴 구동 없이 실제LiDAR331scan/67.8915초·16311event/23865126bytes/6segment COMPLETE를 우선 확보했다. 새wheel pose는0이며 앞선 실물실패세션107157건/원task/receipt는 그대로보존했다. 모터UNPREPARED의 Stop readback미확인을후행OFF/Disconnect·정상Exit와구분한다.

새 설치 `20261025T034741Z-1387861a7bfd`/1706exact·source `1387861a7bfd5774a83c8ad06e1cd4538de51f0fe6adec71f6e4c0b703b2c895`는이전584manifest 중제품3파일만변경했다. physical `_command`의 request전 bounded 새stationary ring1회→같은직렬화primitive·fresh cells재검사, snapshot시작PC시각−원age 고정(처리/저장시간포함), 최초typed guard거절 memory→Stop시도후저장·terminal save실패와원예외분리를적용했다. 동일PhysicalTaskMap을쓰는 current_frame도시작시각을전달한다. 큐/전송후refresh/자동retry/TTL확대/원시각갱신·충돌/10도/Stop보호변경0.

최종584무구동회귀/실제500ms adapter/fleet·queue후만료·느린저장·snapshot+grid시간·원인보존/receiver114·전체installed manifest/격리importPASS다. Astra sourceclosure 및 actualcold의원FAILED문구·3physical무권한/robotPOST0·정상종료를확인했다. [최종19/19 gate](../../outputs/robot-data-priority-20261025-01/acceptance01.json)는PC보완+정지자료에만한정하며새SIM주행/실물주행성공·하드웨어ready판정이아니다. 원실패정확분기는미확정이며 tests02·05와검수기오류도보존했다. 새모델0·로봇추가이동0/SDK·시스템·삭제·GitHub0.

[데이터/설치 보고서](../../outputs/robot-data-priority-20261025-01/report.html) · [원 오류부터 현재까지 색인](TWINPULSE_RECURRING_FAILURES_2026-10-25.md).

## v653 감독 실물시험 — 첫 child 전 실패, 보완 미구현

v652와 같은 설치에서 실제 현장 감독 승인을 받고 연결/Prepare(output1200ms)/native LiDAR/Arm/bootstrap wheel Stop을 확인했다. 실제 text planner의 survey→return→stop(총3m/180s/64segment) task `9ab857c208416c83892dfa59bc09de2d`는 `Physical task pose or observed map changed before admission.`으로 **0segment/0distance/0child FAILED**다. 아래 v652의 PC/SIM 준비 판정은 보존하되, 현재 이 physical common-task 경로는 수정 전 NOT_READY다.

- 원 native packet/인접 fleet 표본은 같은 연결/config/pose epoch·거의 같은 yaw(차이 약1.43e-6rad)다. `_survey → geometry 기록/replan → _go geometry → _command geometry → _send/_check → fleet ingress/snapshot/final admission` 동안 pin된 ring의 원500ms가 소모됐을 가능성이 우선이다. Astra도 원문과 소스를 독립 대조했다. **정확 실패분기/그 순간 source age가 남지 않아 단독 원인 확정은 하지 않는다.** 인접 GET은 실패 guard snapshot의 대체물이 아니다.
- 다음 최소 보완은 typed 거절분기/원 source age 기록, physical pin 직전 bounded fresh stationary ring 취득과 정확 primitive 재검증, 실제500ms adapter/fleet 경계 재현이다. 기존 fake fixture의1000ms 한정검증을 실물500ms 충분조건으로 해석하지 않는다. 제안은 아직 미구현이며 TTL 확대/시각 재부여/자동 motion retry/15·17cm/10도/최종wire/Stop guard 변경은 없다.
- exact task Stop/readback과 추가 Stop/OFF/Disconnect·terminal cleanup 및 정상 App Exit를 확인했다. 원107157행/216491018bytes/52segment COMPLETE를 전 SHA/크기/행수로 대조, 원 runtime/Kit도 동결했다. 8초 정지수집 INCONCLUSIVE·bootstrap wheel Stop PASS와 독립 차체/제동 UNQUALIFIED를 구분한다.
- 초기 Reopen 누락은 운영절차 오류다. session01 녹화는 도구 timeout으로 중단됐고 session02 orphan pointer 거절도 보존했다. session03 466.88s/721frame은 녹화복구 이후 실제 renderer 영상이며 decode/PTS/contact를 확인했다. 전체시작·실물카메라·완성 제출영상이 아니다. 이번에는 세계등록하지 않아 USD 위 실제 body/점 투영이 없고 실제 sensor-local panel만 보인다.
- 제품변경/새빌드·설치0. 새모델 text1/사진0, 추가50중12사용/38미사용, SSH우회/SDK·시스템·삭제·GitHub0. 추가 이동시험0, 앱닫힘/로봇정리확인.

[현장 보고서·원문·녹화](../../outputs/robot-environment-field-20261025-01/report.html) · [원 실패/정리 판정](../../outputs/robot-environment-field-20261025-01/result01.json) · [인접 admission 자료 분석](../../outputs/robot-environment-field-20261025-01/admission-analysis01.json).

## v652 현장시험 전 PC 준비 이력

2026-10-25 / v652: **PC에서 가능한 전체 연결·설치 인수 완료, 다음은 감독 현장시험**. [최종 gate01 87/87](../../outputs/environment-task-loop-20261025-01/acceptance01.json) · [결과·실패·실행절차·실제 검수녹화](../../outputs/environment-task-loop-20261025-01/report.html). v646의 로컬수집만으로 전체 완료를 선언하지 않고 아래 환경/사진/현재표시/재계획/취소/cold까지 추가로 확인했다. 실물의 주행·제동·정합·방전체 coverage는 아직 미검증이다. 추가 LLM50회/기존 사용자 사진 재사용 승인, 무감독 실물 연결·구동 및 새 시스템·SDK·유료GPU·삭제·GitHub 업로드는 승인되지 않았다.

## v652 최종 구현·실제 검증

- 설치 `20261024T205438Z-be150e10b23f`, source manifest `be150e10b23f3c35db84ff1ac478395917489d0967004b355f788c084db25a64`, 1706exact/584source·physical=true. 일반 `Start-TwinPulse-Test.cmd`와 같은 entry를 실행하고 실제 설치 renderer/Isaac의 클릭·입력을 검증했다. Explorer native double-click/OS 화면 캡처는 NOT_RUN이다.
- `TaskCollection` → 고정 멀티위치 구조 정합 → 센서보다 먼 모델의 잔차 XY cluster → 사진 종류와 명시 연결 → 기존 공통 transaction/ACK 후 원자료 재검증/Undo → 현재 session 등록 → native-free ∩ USD-free 기반 공통 physical task를 연결했다. LLM은 capability 계획/사진 종류만 제안한다. 임의 생성 코드를 실행하지 않으며 새 문장마다 Codex로 함수를 만드는 구조가 아니다.
- 환경의 실제 `hybrid16/reapply16`은 원14관측·현재기하 비교·SAVED fresh frame→새 photo call005 basket→XY/종류/높이 명시→Apply·Undo·재적용을 통과했다. 원USD30mesh/38339bytes·원사진 SHA는 불변이다. 최종18은 planner2파일+task service1파일만 달라 전체manifest closure로 선행 환경 근거를 분리한다. 소스16 영상/Apply를18 실행처럼 소급하지 않는다.
- 최종 `survey18`은 실제 설정된 Nemotron의 survey→return→stop 계획, 11finite/2.219718117m/14실제SIM관측, XY/yaw복귀·Stop/OFF/Disconnect를 확인했다. `PARTIAL`, whole-room=false다. `compose18`은 원실패 `compose17`의 출발pose/명령/원결과SHA를 먼저 대조한 후5finite/.2m·복귀COMPLETED다.
- `session18`은 현재 정지3scan Check와 명시 Use를 분리하고, 실제 fleet body/name/현재점 표시→회전완료 후 새 원capture/동일robot·operation·connection·applied epoch·실제DOM frame을 대조했다. OFF는 점/활성표시를 제거하고 body·연결은 유지한다. Disconnect/Clear가 뒤따른다. cold는 같은job/digest를 SAVED/hidden/noreg로 읽을 뿐 권한을 복원하지 않는다.
- `cancel18`은 PLANNING 중 exact Stop, worker종료/lateoutputignored/0child다. `open19/cold18/robot-cold18`은 별도 새 launch에서 saved장면/사진후보·검토결과 복원/명시Build·3physical disconnected/no drive를 확인했다. source16/18/19의 모든두root자연0·PRE_CLOSE_COMPLETE/오류0이며 각9EXACT_COPY(Kit포함)+선택liveness1ORIGINAL_UNAVAILABLE을구분했다. 원문이없던선택파일을정상복사한것처럼세지않는다. Astra최종task/frame/cold/source·archive SHA대조에서새확정P1/P2는없었다([검토](../../outputs/environment-task-loop-20261025-01/astra-final-review01.json)).
- Python574/Web1234(skip0)·실제bootstrap receiver114·fresh `python -I -B` installed-only import/원source SHA는 보조다. gate는 actual UI/원scan/수정chain/사진응답·Apply/Undo·Stop/영상원path/bytes/SHA/wall_ms/PTS·각launchcleanup을 결속하고14개의 누락·stale·실패사진/영상·중복역할 반례를 거절한다. encoded contact를 직접 보았으며 녹화용 실제 mouse-event 포인터/작은 실제body·이름/점/OFF를 확인했다. 짧은cold 영상은 해당권한복원검사만 보여주며 전체시작은별도open19를따른다. 완성1분제출물/OS커서/실물카메라 영상은아니다.

## 마지막 원인 보완과 남긴 실패

소스17의 `compose17`은 모델이 정확한4단계 계획을 냈지만 첫 child 전에 `ROBOT_TASK_CURRENT_GEOMETRY_REQUIRED`였다. 원 step_started→geometry_recorded674.5ms, 386782bytes의 지도 진단 원문 저장·event 뒤 동일 snapshot의 .5s가 소진됐다. 소스18은 **SIM 새digest 저장 완료 뒤만 최신 owner/pose/map/peers/원timestamp를1회 재조회**한다. 두번째도새기하라면기록하되3번째재조회는없고, 원.5s/최종dispatch guard·physical native 한도/Stop·15/17cm·10도gap은그대로다. 저장실패·취소·새stage·새telemetry없음·계속기하변경을추가5보조시험으로검사했다. 원FAIL은삭제하지않았다.

session17은 비동기references 조회 전 접근,17b는 finite완료 뒤 latestheader와 decodedDOM frame/수신scan의 관측경쟁으로 검수를 마치지 못했다. 원FAIL/정확cleanup을보존하고 frameid→원headerMap·동일완료후capture 조건을유지한17c/18 전체재검수를했다. 제품센서 deadline을늘리지않았다. 원source13 UNKNOWN/ABORT, source15 Recover 한정성공, source16 임의 relative waypoint/route 차단, photo basket누락·disk0는각원범위로남긴다. 초기heartbeat공백의단일원인은아직미확정이다.

## 현장 절차와 완료 경계

1. 새 로봇ON/충전선분리/현장감독/즉시차단 확인 후만실물Connect한다. 현재는앱정상종료·lock/listener0, 무감독실물접속0이다.
2. 기존실물선택→Connect/Prepare→실제전압/정지LiDAR baseline→명시Arm/bootstrapStop. PC별도ROS SDK나새iPhone앱/외부모델설치는선행조건이아니다. 기존Prepare가target검사·readback을담당한다.
3. 짧은총거리/시간예산을명시해 이동측정·귀환·정지 목표를 입력하고 정확계획을검토후Run한다. Arm잔여시간은전체계획예산이상이어야한다. 로컬수집은 USD정합/ICP 성공을요구하지않지만 unknown/실제센서/충돌/저전압/저장/Stop 위험은보존한다. 실제 저장지연 내성은이번SIM보완으로PASS가아니므로원packet/저장시간을첫현장시험에기록한다.
4. 수집후같은벽span실측·초기위치/방향·센서높이/TF를검토해 Import space/Collected survey의Task→Check/Show/명시Use를사용한다. 사진은종류/bbox후보이지metric위치·높이가아니다. 잔차XY/명시높이·중복검토후Preview/Apply한다. semantic가구목적지이동은현재명시registration이필요하다. HELD/POOR_FIT를강제로적용하지않는다.
5. Stop/OFF/Disconnect/정상Exit 및원로그저장을확인한다. 실제몸체/제동·세계정합/방전체coverage는그실물데이터로판정한다. 복잡한부정/모호한문장의상대이동추론을완전보장하지않으므로exact plan Review는생략하지않는다.

새50장부는11claim(text7/photo4·실패/취소포함),39미사용·자동retry0다. 원USD/metric좌표/실물raw로그의모델전송0, 새SDK/시스템/유료GPU/삭제/GitHub0. 구source13의죽은launcher.lock은exact소유확인후evidence로이동보존했고사용자파일은삭제하지않았다. 종료후Cfree약7.1GiB이며Isaac실행중약1.5GB까지낮아졌으므로다음실행전disk를다시측정한다. DWM/private·pagefile압박은관측했지만단독원인으로단정하거나시스템설정을변경하지않았다.

## 현재 단절과 구현 순서

1. 저장 common task의 원 observation/native packet·pose·Stop·task/op/connection/source를 검증하는 TaskCollection 어댑터. 실패한 task도 원 실패를 유지하며 검증된 수집 부분을 명시 검토할 수 있게 한다.
2. 여러 위치의 정지 관측을 기존 StructuralMatcher의 고정 ROI/first-hit/heldout으로 검토. 첫 anchor의 world_from_local과 각 원 wheel-local pose를 따로 결속한다. 이동한 scan을 같은 위치의3frame으로 처리하지 않는다.
3. 명시 registration snapshot·표시/숨김. 원 collection/TF/reference/transform/validation/current scene SHA를 고정한다. 몸체와 점은 같은 좌표를 사용하며 cold 저장 결과는 SAVED/무권한이다.
4. 여러 관측의 모델보다 가까운 표면 잔차를 장애물 XY 후보로 모으고, 기존 사진 후보의 종류/이미지 bbox와 명시 연결한다. 높이·전체3D치수·얽힘위험·중복은 별도 추정/검토다. 원USD 보존·기존 transaction/Apply/ACK/Undo/저장 검증을 재사용한다.
5. 새 revision에서 SIM 및 supervised physical 공통 task가 승인된 world/local registration을 소비하도록 연결한다. physical은 매 primitive 최신 local ring/unknown/Stop 보호를 유지하며 registration이 Arm 또는 측정된 차체 정확도를 대신하지 않는다. geometry/connection/boot/pose epoch/TF 변경은 등록·경로를 무효화하고 자동 재개하지 않는다.

## 실제 설치 인수 기준

- 일반 시작·사용자 입력과 configured 실제 planner/사진 모델을 사용한다. 응답 가로채기·고정 답변·직접 제품 API 변경으로 일반 UI acceptance를 대신하지 않는다.
- 원USD/사진 보존 → 실제 SIM 수집 → 저장 수집 선택/정합 검토/표시 → 누락 후보와 사진 종류 연결 → Preview/Apply/새frame → Undo/재적용 → 새 revision task 재계획 → Stop/OFF/Disconnect.
- 단독 cold 재열기에서 동일 source/review/receipt를 복원하되 connection/Arm/작업권한 복원0. 실패·stale registration/불완전 원자료/취소/저장오류·오래된ACK 음성 검증.
- 현재 source/최종 설치/실제 Isaac·원 로그·정상 종료·비용 ledger를 evidence gate로 결속한다. 이전 scoped PASS를 새 전체 경로의 PASS로 재사용하지 않는다.
- 원 physical POOR_FIT/차체UNQUALIFIED·하드웨어 NOT_RUN은 유지한다. PC 구현 누락은 현장 검증으로 미루지 않는다.

## 현장에서만 확인할 입력

현재USD metersPerUnit 미작성에 대한 같은 벽 끝점 실측 길이, 초기 로봇 위치/방향, 설치된 센서 높이/장착변환/각도부호·footprint 및 현재 전압·Stop/readback·센서 baseline. 이 값들을 입력하는 UI·검증 경로까지 미리 개발한다. SIM의 치수/명목 TF를 실측값으로 바꾸어 쓰지 않는다. 이미지 두 장만으로 metric 위치를 보장하거나 새 iPhone 앱이 필수라고 단정하지 않는다.

## v650 복구·자원 장애 추가 기록 — 아직 전체 인수 아님

- 원 디스크0 때문에 build12 staging, tests06 결과쓰기, restore11 Undo 완료 확인이 실패했다. 이를 성공으로 대체하지 않는다. 원 launch fde8…는 root0이어도 inner cleanup 결과가 없어 UNKNOWN이다. 파일 삭제는 하지 않았다.
- 설치13의 명시 Recover `7ea5424c…`는 claim3.58s 뒤 engine_disconnected UNKNOWN, 나중에는 엔진에 저장 revision77f598…가 나타났다. heartbeat 회복 후에도 snapshot5712는 정지했다. 초기 공백의 단일 원인은 미확정이다.
- 확정 코드 결함: broker terminal UNKNOWN이 late ACK와 충돌하면 bridge는 같은 head를 snapshot보다 먼저 계속 전송한다. 새 코드는 정확한 원/현재 engine identity와 revision 검증→원UNKNOWN+lateACK 별도 immutable/fsync evidence→exact terminal disposition→head 제거만 허용한다. 원operation/transaction/lease를 성공 승격하거나 자동 재실행하지 않는다. 재전송에서도 fsync 성공이 필요하다. ACK 없는 reconcile의 전후 chain replay도 제거했다.
- 구버전13은 정상Exit/명시Recover 모두 실패·GUI console=False여서 exact소유 launch7153…를 유지보수 ABORT로 중단했다. `aborted13`은 LIVE_PRE_ABORT 원문이며 정상cleanup 인수 자료가 아니다. 죽은launcher.lock은 삭제하지 않고 같은 폴더로 보존했다. project journal은 수정하지 않았다.
- 새설치14 `20261024T200751Z-c1a80d75d1a6`/1706exact. 실제 복구→hybrid/재적용/새revision task/current session/취소/cold/정상cleanup 인수 후에만 준비판정한다. 새50중4예약/실제call(text1/photo3), 나머지46; 두 photo basket누락을 임의association하지 않았다.

## 04:02 중간 상태 — 아직 전체 인수 아님

- 구현: `TaskCollection`의 원 task/관측/native 기록 검증, 고정 멀티뷰 정합·잔차 XY 후보, `EnvironmentSurveyReview`와 영어 UI, 공통 transaction sensor binding/ACK 후 재검증/Undo, 현재 정지 관측의 명시 session registration, physical 자연어 목적지의 공통 task 경로, 원 native free ∩ 현재 USD free의 보수적 회전 grid 교집합/최종 wire guard.
- Astra 지적의 pose/scan/capture 결속, strict archive 검증, Apply trace 신규 분기, overlay 잠금 순서, odometry fault/frame 거절, CHECKING 한정 취소, registration snapshot/token CAS를 보완했다. 이전 원실패는 지우지 않았다.
- 설치01 actual SIM `survey01`: configured 실제 planner1회, 2.02885662m 이상 유한 수집·최종 복귀/Stop/OFF/Disconnect PASS. 정확한 최종 수치/관측은 해당 result/task 원문을 따른다. `review01` 실제 멀티위치 관측 정합·fresh Isaac frame 표시·1280/1440 overflow 검사 PASS. 이는 source01의 한정 인수이며 새 최종본 전체 PASS로 합산하지 않는다.
- 최신 설치05 `20261024T185805Z-c4fe0dd7aeaf`/1705 exact의 전체 실제 UI 인수 진행 중. `hybrid04`는 일반 Remove Apply 전에 API `deepcopy` import 누락으로 FAIL, product transaction 시작 전 실패를 원실행7831ebafe27f43d4a0bff8d2bf9d08e9/정상종료와 Kit 포함 runtime-copies04에 보존했다. import를 고친 뒤05에 설치했으며 성공으로 소급하지 않는다. build03은 새 test의 unimported `test()` TS2593 실패이며 `it()` 수정 후04/05 build 성공.
- 현재 보조 `tests01` 346/346, 별도 UI157 및 routing/import/alignment42 PASS. afterACK 원pose 변조 거절과 store.apply 미실행은 device-free 보조다. 실제 hybrid Apply/Undo/재적용·새revision수집/정합·cold/종료/gate는 아직 남았다.
- 새50 장부 `call-claims/001.json` text1회 사용, 나머지49회 미사용(이전 승인 장부 별도). 취침 중 실물 연결/구동·시스템/SDK·삭제·GitHub0. Native Computer Use list는 가능하나 첫 screen capture는 FrameArrived timeout으로 UNKNOWN, 기존 installed renderer 테스트 UI 경로와 구분한다.
