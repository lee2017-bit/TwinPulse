# N4 부분 — 로봇 로컬 임무 루프와 기존 제품 이력 연결

2026-09-28 07:58 KST. 사용자 `그래 계속해`의 오프라인 후속 구현 승인. 실제 로봇에
접속·배포·구동하지 않았다. **실물 자율 데모 전체 완료가 아니다.**

## 구현과 실행 경계

- 기존 `teleop_worker.main`의 소유권/정지 qualification/최종 독립 OFF 수명에
  `mission` 분기를 연결했다. `teleop.sh`의 고정 모드지만 **현재 profile에는
  autonomous policy가 없으므로 장치 접근 전에 거절한다.** App의 실제 시작
  API에도 아직 이 모드를 허용하지 않는다. 현재 설정을 활성화하거나 우회하지 않았다.
- 새 `mission_runtime.load_request`는 release의 고정 calibration JSON과 state의
  고정 mission-request JSON만 제한 크기/정확한 필드/중복키 거절로 읽는다.
  calibration bytes의 manifest hash·guard binary·namespace, request의 같은
  boot/release/calibration hash·최대90초 유효기간·최대45초 임무/16개 waypoint를 확인한다.
  **메타데이터/해시는 무결성 검사이지 실제 측정이나 사용자 동의의 독립 인증이 아니다.**
  근거 digest만으로 사진 추정치를 보정 완료로 바꾸지 않으며, 실제 로봇용 calibration은
  만들지 않았다. 정확한 실제 모델/센서 좌표 검토와 배포 승인이 별도로 필요하다.
- qualification은 기존과 동일한 boot/release/policy PASS receipt를 요구한다.
  한 임무 request는 소비 marker를 배타적으로 생성해 한 번만 실행하고 재시도하지 않는다.
  과거 receipt/FAIL을 새 버전의 PASS로 바꾸지 않는다.
- `run_mission`은 같은 입력 프로토콜의 자동 `watch` heartbeat로 연결 생존만 검사하고,
  이동·회전은 최신 odom/scan을 사용하는 기존 `CheckedMission`/`RosLink.navigation_step`이
  결정한다. 방향 입력은 거절한다. 사용자가 매 방향을 클릭하는 구조가 아니다.
  첫 입력2초/입력250ms/세션60초 기준은 유지하며 임무 자체는 최대45초다.
- arm 전·후 및 최종 publish 앞에 취소/통신/기한 검사를 넣었다. 입력단절·stale scan·
  장애물·로그 오류·기한 만료 시 루프를 종료하고 ROS stop/OFF를 시도한다.
  부모 worker의 base 회수와 독립 OFF/readback 실패가 도착/취소 결과보다 우선한다.
  정지 기준을 완화하지 않았다.
- 루프가 멈춰도 동작해야 하는 저수준 보호는 **기존 별도 base의 명령 만료 guard**에
  의존한다. 이번 Python 구현을 별도의 인증된 비상정지/새 하드웨어 watchdog으로
  주장하지 않는다. 실물의 종단간 정지/통신단절 시험은 아직 수행하지 않았다.

## 명령/관측 기록과 App

- 기존 `robot-session-1.0` 기록에 mission 시작/판단/종료를 추가했다. 각 판단은
  odom-derived pose·원래 odom/scan 시각·clearance·근거 digest·판단 결과를 보존한다.
  실제 publish stamp를 만들 때의 명령 나이를 반환해 기록하므로, 이후 로그 저장
  지연이 명령 나이에 섞이지 않는다. 임무 tick과 원격 keepalive sequence는 별개다.
- raw odom/scan은 기존 약1Hz 기록을 유지한다. 모든 사용 ray의 매 tick 완전 기록이나
  바닥 ground truth가 아니다. 관측을 명령 적분으로 채우지 않으며 좌표 정합은 false다.
- 기존 이력 validator는 크기/자료형/권한 플래그·임무 ID/증가 tick/종료 순서를 검사한다.
  최근200개 mission event를 읽기 전용으로 내보내고 App은 최근10개 판단을 표시한다.
  읽기·다운로드는 로봇 연결/재실행/권한 부여를 하지 않는다.
- 실제 생산 loop/RosLink를 인공 센서로 실행한 고정 test fixture를 기존 App 이력
  리허설에 넣었다. `real_transport=false`, `physical_success=null`을 유지한다.

## 검증 기록

- 관련 Python 77 PASS: 새 mission10, 기존 lifecycle의 새2 포함 검사,
  physical controller44 및 audit6. 첫 단독 실행은 테스트 import 경로 누락1 ERROR였고
  기존 경로 bootstrap을 적용한 뒤 통과했다.
- 정상 인공 관측에서 연속 전진, 별도 사례의 회전→전진→도착을 확인했다.
  원격 방향 입력은 없고 watch만 사용한다. consume와 arm은 각1회다.
- 단절/heartbeat 상실/stale scan/장애물/기한/로그 쓰기/정지 실패, 초기무입력,
  스캔 미수신/원격 방향 거절/이미 소비한 요청, arm 중 취소, 위조 log 및 로그
  지연에도 원래 publish age 보존을 검사했다. 이는 실물 결과가 아니다.
- 전체 회귀 `artifacts/mission-runtime-regression-20260928-r2/manifest.json` PASS:
  core163/Web112/build 및 기존 integration 그룹. r1도 PASS였으나 최종 명령나이
  기록 보완 전 이력이다. 보완 뒤 새 폴더 r2로 다시 실행했으며 덮어쓰지 않았다.
- 실제 App/Chrome + 가짜 장치 `artifacts/mission-runtime-browser-20260928-r1/result.json`
  **14단계 PASS**. 새 임무 fixture는 실제 loop/RosLink 코드로 원격 watch만 받아
  40번의 자체 전진 출력을 만들고 41번째 tick에서 도착, consume1회다.
  그 기록을 실제 App의 기존 조회/JSON 내보내기로 확인했다. 전체7로그693events
  (robot421), 기존 수동 가짜 출력26. 실물 성공이 아니며 원본 project와 source/dist 유지.
- 새 판단 표의 `mission-history-desktop.png`를 직접 확인했다. 최신10개 판단,
  odom-derived 좌표/출력/도착 표시와 저장이력·미정합 경고가 보인다.
- 같은 build의 실제 App/bridge/Isaac `artifacts/mission-runtime-isaac-20260928-r1/result.json`
  **8체크 PASS**. 기존 사진 근사방/Burger4mesh·합성B3시점/저장USD/원본 보존 확인.
  이번 새 인공 센서 임무를 Isaac에서 물리 실행한 것은 아니다. Physics Run/실물0.
  종료 시 기존 VtValue 경고는 남았고 결과와 stage 검사는 PASS다.
- `artifacts/mission-runtime-evidence-audit-20260928-r1/result.json` PASS:
  현재49파일·공통해시/dist목록 일치. 이 비교는 선택 파일의 무결성 확인이며
  전체 저장소/실물/독립 authenticity 인증은 아니다. 모든 검증 프로세스 종료.

## 남은 제품·실물 작업

1. 실제 모델/센서/footprint 자료 검토와 보정 파일 구성·검증. 현재 calibration 미제공으로
   실물 mission 경로는 잠겨 있다. 검토 라벨 자체를 실측 증거로 인정하지 않는다.
2. App에서 임무 범위를 한 번 승인하고 request 생성/전송·자동 heartbeat·취소·상태를
   처리하는 연결 준비/시작 경로. 새 실제 모드는 현재 API/버튼에서 실행할 수 없다.
3. 장애물 시 현재는 종료 정지다. 우회/재계획, 실제 실행 기록→방 Twin 정합 재생은 잔여다.
4. 새 배포/실물시험 승인 후 현재 버전의 센서·정지·단절·제한 주행 검증.

로봇 OFF 사용자 보고 유지. 야간 예약은 PAUSED이며 이번 승인으로 재시작하지 않았다.
