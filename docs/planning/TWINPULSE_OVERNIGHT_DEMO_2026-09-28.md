# TwinPulse 야간 통합 데모 — 2026-09-28 07:00 KST 마감

**후속 사용자 요청(09:10):** 센서/차체 공식 근거와 저장74프레임 대조, 기존 방App
목표선택·명시 미터 대응점 기반 좌표 후보 연결/통합검증 완료. 최종 가짜App20/
실제Isaac10/audit53 PASS. [증거](../verification/room-goal-evidence-20260928.md).
실제TF/odom·방 실측 대응점 없음: 실물 정합과 실행권한은 미완료이며 후보를 임무에
전달하지 않는다. 로봇접속/배포0·예약PAUSED 유지. 아래 내용은 각 시점 이력이다.

**후속 사용자 요청(08:43):** 일반 정지/강제 STOP·Esc를 수동/임무 공통 입력과
기존 종료 확인·로그에 연결했다. 잔여구간100/50ms·강제/오류 우선·재개금지.
[검증/실물경계](../verification/two-stop-controls-20260928.md). 실물 미배포이며
로봇을 켤 필요 없음. 이후 보정/배포등록readiness·Twin목표결속/재계획 잔여 유지.
예약PAUSED, 로봇접속0.

**후속 상태(08:21):** 새 `그래 다음으로 가자` 승인으로 App의 임무 범위1회승인/
robot-clock bootstrap/기존로컬판단·자동watch/취소·저장이력을 연결했다.
관련79+audit6/전체core163·Web118/build·actualAppfake16/actualIsaac8/audit50 PASS.
[구현·한계](../verification/mission-app-20260928.md). 기본실물transport는 실제보정/
배포등록 부재로 서버잠금이며 테스트 주입 경로만 검증했다. 방Twin좌표결속·재계획/
실물검증 잔여. 로봇접속·배포0, 예약PAUSED, 검증프로세스종료.

**후속 상태(07:58):** 추가 `그래 계속해` 승인으로 기존 worker 자율 임무 loop와
qualification/최종OFF·request검사 및 기존 App 판단이력 표/JSON을 연결했다.
인공관측40출력→도착·관련77/전체Web112·actualAppfake14/Isaac8/audit49 PASS.
[범위/잔여](../verification/mission-runtime-20260928.md). 실제 calibration은 없고
현재profile 및 App 시작 API는 실물 mission을 허용하지 않는다. 재계획/실물검증잔여,
로봇미접속·미배포, 예약PAUSED 유지. 야간 마감 후 새 사용자 승인 작업이다.

**현재 상태(07:20):** 이 야간 예약은 마감 후 PAUSED로 종료했다. 사용자의 새
`그래? 그럼 일단 그거 계속 진행해` 승인으로 별도 오프라인 증분을 수행했으며
예약은 재개하지 않았다. [N4 센서→출력 접점 검증](../verification/navigation-binding-20260928.md):
core163/Web111/build·가짜App13/actualIsaac8/audit43 PASS(부분). 실제 frame 근거
loader·자율 worker loop/watchdog·재계획·실물 검증은 잔여다. 아래는 야간 계획과 시점별 이력이다.

## 승인과 제품 목표

2026-09-27 23:46 KST 사용자가 아래 계획에 `좋아 시작해`로 구현·검증을 승인했다.
로봇 OFF. 목표는 수동컨트롤러가 아니라 **실제 방 사진 → 근사 3D 방 + 기존
TurtleBot3 Burger → 실측 보정 → 자율 임무 → 명령/관측 로그 → Twin 재생/동일조건 비교**다.
임무 범위를 사용자가 시작하면 그 안의 이동·회전·회피·재계획마다 승인을 묻지 않는다.
현재 실물 자율 구동 승인은 아니며, 새 실물 시험은 사용자 복귀 후 별도 승인한다.

## 실행 경계

- PC 오프라인 구현/로컬 회귀/격리 Isaac/로컬 App 브라우저 검증만 수행한다.
- 로봇 SSH/serial/실센서/모터/전원/배포/실물시험 금지.
- 유료 API/클라우드, 새 설치/시스템설정, commit/push, 타 프로세스 강제 종료,
  새 에이전트 생성 금지. 현재 허용 권한만 사용하며 부족한 권한은 우회하지 않는다.
- 사용자 작업·실측 원본·과거 FAIL을 보존한다. 합성/저장 재생/Isaac와 실물 검증을 구분한다.
- 실제 사진의 위쪽=창문은 사용자 방향 근거다. 로봇 전방/센서 handedness/metric TF의 증명은 아니다.
- 치수 추정으로 초기 방을 만들 수 있지만 실측이라고 표시하지 않는다. 줄자 측정은 선행조건 아님.
- 실물 충돌은 학습 보상으로 허용하지 않는다. 로봇 로컬 센서/명령 신선도·충돌방지 정지가 필요하다.
- 매 증분에서 관련 회귀, 증거, Baseline/Memory/이 문서를 갱신한다.
- 마감 뒤 새 구현 시작 금지. 결과/미검증/아침 순서를 보고하고 twinpulse 예약 PAUSED.

## 작업 순서 및 완료 기준

1. **N1 방·Burger 장면**: 기존 source-bound SiteToolPlan/SceneRevision/compiler 재사용.
   실제 제공 사진에서 방/가구를 근사 모델링하고 기존 공식 Burger USD 배치.
   원본 사진·모델 해시와 추정/관측 구분. 실제 Isaac 장면/캡처 검증.
   기존 App 제품 경로로 열기/검토까지 이어가고 독립 증거만으로 제품 완료라고 하지 않는다.
2. **N2 연결 준비 통합**: PC 확인은 연결 내부로, 상태/버전/배터리/센서/검증 유효성 묶음.
   필요한 조건에서만 정지검증; 읽기 연결에 숨은 이동 없음. 실패 원인·다음 행동 표시.
3. **N3 공통 제어와 기록**: WASD 한글/포커스, 일반 release와 세션종료 분리,
   반복 입력을 실사용 시간축으로 검증. 입력/전송/실행/encoder/odom/scan/배터리/종료원인
   공통 session id와 단조 시간/clock domain 기록. 없는 관측을 채우지 않는다.
4. **N4 임무 실행/로컬 보호**: 수동과 자율 공통 adapter, 목표/경로/재계획;
   footprint/swept path와 신선한 scan으로 제한, 단절/지연/불확실성 정지.
   수동 단발시험 시간제한과 임무수명 분리. 현재 실물 gate는 검증 없이 풀지 않는다.
5. **N5 Twin 재생/평가**: 명령과 관측 비교, 같은 지도·출발/목표·profile로 두 경로 평가.
   도달/시간/길이/근접/충돌 구분; encoder는 실제바닥변위 보장 아님.
6. **N6 통합 리허설**: App→Twin→임무→기록→재생/비교, 성공과 단절/만료/실패;
   같은 source/build에 묶인 결과, 아침에는 잔여 실물 확인만 안내.

장식/부가 기능보다 전체 흐름과 실패 처리 우선. 단일 실제 자율주행 데모 완성을 보장하지 않는다.

## 시작 시점의 사실/결함

- 공식 Burger USD import: meshes4와 wheel revolute joints2 검증됨, simulation motion/sensor 미검증.
- 실제 방 사진·추가 위쪽 사진/74 native scan frame 보존됨. 정합/active Twin/실물임무 미완성.
- 최신 사용자 실행 stop trial `ddaf23aed5964089a1480bb9b3b151ef`는 QUALIFIED.
  이후 수동5세션의 STOP_READBACK_UNCONFIRMED2/INPUT_OR_SESSION_TIMEOUT3을
  이전 stop 실패와 혼동하지 말 것. 최종 독립 OFF 확인은 세션 사용성 통과 아님.
- 진단된 결함: WASD e.key만 처리; ordinary halt에 legacy 250ms/200ms 안정판정 잔존;
  입력/hold/session timeout 원인 합쳐짐. 세부 입력 timeline은 기존 로그에 없음.
- 기존 Memory v1.0.133의 '새배포/재시험 미실행'은 과거 구현 턴의 범위이며 최신 사용자 시험과 구분.

## 진행 현황

- STARTED: 승인 범위/계획 저장, 기존 heartbeat를 30분 간격으로 재활성화.
- N1 첫 증분 PASS: 기존 SiteDraftRecord/SiteToolPlan/compiler로 사진의12개 방/가구 객체와
  공식 Burger 표시용 모델을 합성. 실제 Isaac r2 6체크/4mesh/캡처3/저장USD재열기 PASS.
  새7·관련27·core138/전체오프라인회귀/Web82/build PASS(부분 개수 중복 포함).
  [증거/실패/제약](../verification/bedroom-twin-20260928.md), 결과 `artifacts/bedroom-twin-20260928-r2/`.
  치수/pose 추정·robot Physics=none·실측 TF없음·실물0. r1 FAIL/원본 보존.
- N1 제품 표시 경로 PASS(00:34): 실제 App 검토→기존broker/bridge→actual Isaac,
  browser6체크/4mesh/원본보존·Web87/전체회귀 PASS. r1 FAIL 및 r2/r3 증거 보존.
  [제품 연결 증거](../verification/bedroom-app-20260928.md). N1의 시각 경로만 완료,
  실측 TF·동역학·자율주행·새PC 배포 검증 아님. 기존 사용자창 자동교체 없음.
- N2/N3 UI 증분 PASS(01:02): 연결 클릭 내부 PC preflight/중복·늦은연결 방지,
  IME/CapsLock WASD·포커스·이벤트 분리. 전체회귀/Web95/build,
  합성읽기6/가짜장치9/PC모의6 PASS. [증거](../verification/connection-keyboard-20260928.md).
- N3 핵심 첫 증분 PASS(01:33): 일반release/최종halt분리·해제상관READY·원인별만료,
  PC/robot 명령·encoder·torque·배터리 세션로그. 관련45/전체회귀/Web95/build,
  실제App→가짜장치9단계(550ms해제/같은연결반복)/로그462events PASS.
  [증거](../verification/session-release-20260928.md). 실제반복구동해결/실물배포 아님.
- N4 합성 임무 제품경로 PASS(부분,01:58): 기존사진scene→합성ray/공통rehearsal
  adapter→bounded waypoint판단→App경로/JSON저장. 정상·장애물·센서지연3종,
  core146/Web97/전체회귀·실브라우저5 PASS. [증거/제약](../verification/bedroom-mission-20260928.md).
  실제센서/실물·기존수동adapter 공용화·자동우회·실측TF·물리주행은 미완료.
- N5 선택시점3D 연결 PASS(부분,02:32): 명시적 slider/표시→App/API/broker/bridge/
  actual Isaac의0/218/437 pose·yaw·trace/저장USD 일치, browser7/전체Web99 PASS.
  [증거/실패이력](../verification/bedroom-replay-20260928.md). 연속재생/실측pose 아님.
- N5 고정합성 동일조건 비교 PASS(부분,02:58): 같은scene/start/goalXY/profile의
  A/B 비교·충돌null/미도착효율제외→기록선택/JSON/actualIsaac B3시점.
  전체Web101/browser6/Isaac8 PASS. [증거](../verification/bedroom-comparison-20260928.md).
- N3 종료 전 저장·제품 요약 PASS(부분,03:27): 별도 bounded writer append/fsync,
  실패/지연시종료·원본보존·App 입력/전송/발행/관측 분리. 단독27/전체Web102/
  가짜브라우저10 PASS. [증거](../verification/session-journal-20260928.md).
- N3 저장이력 조회 PASS(부분,04:00): 인증GET→bounded 파일검사·tail미완료·
  clock/provenance/순서→App목록/종료원인/명령관측표/검토JSON. 신규6/전체Web105/
  가짜브라우저12 PASS. [증거](../verification/session-history-20260928.md).
- N4 공통 검사 PASS(부분,04:30): 동일 core 속도/age→합성adapter/ROS publish·bundle,
  CheckedMission pose/scan/frame/source/freshness/기한→기존합성제품. focused70/전체
  core150/Web105/build·합성browser6/가짜12 PASS. [증거](../verification/shared-command-20260928.md).
  실물0·미배포·기존수동은scan검사없음·실제센서/TF/자율entry 미완료.
- N3/N4 passive 수신기록 PASS(부분,05:00): RosLink odom/scan→source시간/형식검사·
  raw frame→1Hz journal/이력60·JSON. focused57/전체core156/Web106/build·가짜12 PASS.
  [증거](../verification/passive-observations-20260928.md). 실제ROS/배포0·TF/충돌보호아님.
- N3 명시종료분류 PASS(부분,05:25): closepacket/결과대기·실패EOF분리,
  로봇기한불변·최종ROS/독립OFF실패보존. focused54/전체core156/Web106/build·
  가짜browser12 정상OPERATOR_STOP/통신손실FAILED PASS. [증거](../verification/explicit-close-20260928.md).
- N6 같은build actual App/Isaac8체크 재검증 PASS(05:25): 합성B0/140/280 pose/yaw,
  USD재열기·단절/복구/원본보존. `overnight-integration-isaac-20260928-r1`, PhysicsRun/실물0.
- N6 증거 대조/중간 인수인계 PASS(05:55): 기록된 fake12/actualIsaac8의39개
  source/build·공통해시·dist목록 현재일치, audit신규6 PASS(초기temp권한오류후재검사).
  `overnight-evidence-audit-20260928-r1/result.json`,
  [현재상태/아침순서](TWINPULSE_MORNING_HANDOFF_2026-09-28.md). 제품코드/빌드불변,
  전체회귀재실행/실물/배포없음. manifest해시범위/실물미완료를 명시했다.
- N2/N3 start-context 경합 PASS(06:24): 지연된 시작응답뒤현장확인복원5FAIL재현→
  창이탈/Esc/백엔드상실/unmount시권한폐기·늦은owned작업close만,backend준비전잠금.
  controller14/전체core156/Web111/build·가짜browser13·actualIsaac8 PASS.
  [증거](../verification/start-context-20260928.md),audit r2 현재39파일일치/기존6PASS.
  실물/배포/Run0·정지정책불변,구audit r1는당시빌드이력으로보존.
- 06:49 마감전최종검수 PASS: 콘솔 별도PC점검요구 안내교정·local lifecycle assertion,
  `overnight-final-regression-20260928-r1` 전체core156/Web111/build PASS.
  audit r3 현재39파일·기존6PASS,06:24 browser13/Isaac8과Web동일·이번새runtime/실물0.
  [아침 인수인계](TWINPULSE_MORNING_HANDOFF_2026-09-28.md) 갱신,검증프로세스없음.
- **NEXT:** 07:00 이후 새 구현 없이 최종 결과보고·twinpulse 예약PAUSED.
  N2 readiness·실측 TF/local guard/자율worker·재계획과 N5 실측·연속은 여전히
  구현잔여이며 로봇전원ON만으로 해결되지 않는다. 로봇 OFF/접속금지·07:00마감 유지.
