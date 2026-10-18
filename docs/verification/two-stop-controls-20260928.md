# 일반 정지와 강제 STOP 분리

2026-09-28. 사용자 요청에 따른 오프라인 구현. 로봇 접속·배포·실센서·실물 구동 없음.

## 동작 계약

- **정지 · 현재 명령까지만**: 다음 이동과 대기 입력을 폐기하고 마지막으로 발행한
  짧은 구간의 **남은 시간**만 기다린 후 기존 정지/모터 OFF/종료 확인으로 들어간다.
  수동 100ms, 임무 50ms 구간이다. 버튼을 누른 시점부터 새 100ms를 부여하거나
  전체 직진 거리·경유점·임무 완료를 기다리지 않는다. 이미 구간이 끝났으면 즉시 요청한다.
- **강제 STOP · Esc**: 위 기다림을 생략/취소하고 기존 정지·모터 OFF를 요청한다.
  일반 정지 대기 중에도 활성화되며 재확인 체크박스가 필요 없다. 중앙 패드의
  `즉시 정지`도 같은 경로다. 강제 요청을 일반 정지로 다시 낮출 수 없다.
- 두 terminal 동작 모두 연결/임무를 종료하며 자동 재개하지 않는다. 기존 방향키를
  놓는 ordinary `stop`은 동일 연결에서 다음 조작을 허용하는 별도 동작으로 유지한다.
- 통신 단절/기존 입력 기한/세션 기한/센서 오류 및 임무의 충돌 검사 실패가 일반
  정지 대기보다 우선한다. 대기 동안 명령·기한을 갱신하지 않는다. 로컬 loop 정체는
  기존 하위 command-expiry 보호에 의존하며 소프트웨어 버튼은 독립 물리 비상정지가 아니다.

## 구현 경로

기존 PhysicalRobotController → 인증된 physical/input → PC 소유 작업/우선 대기열 →
기존 worker의 control / run_mission → 기존 ROS stop·OFF 및 독립 종료 확인을 연결했다.
`finish_stop`, `force_stop`, `stop_requested`와 종료 상태를 기존 세션 journal에 보존한다.
UI의 요청 중 표시는 실제 종료 확인과 별개이고, 연결이 없을 때는 정지 보장을 하지 않는다.

`finish_segment`는 출력하지 않으며 원래의 입력/hold/session 기한을 상한으로 사용한다.
미발행 입력은 재생하지 않는다. mission 출력 직전 들어온 정지 요청은 상위 loop로
전달해 일반 정지와 강제 정지를 구분하되 finally 정리는 항상 수행한다.
최종 ROS/독립 OFF 실패는 새 성공 상태보다 우선하며 기존 실패 기록/정지 정책은 유지한다.

## 검증 기록

- 관련 Python 83개 PASS: 남은 구간만 기다림/이미 만료된 구간, 강제 우선순위,
  통신·센서 오류/기한, 대기열 교체/강제 이후 일반 정지 무효, mission 정지 후 추가 출력 없음.
- UI 단독22개, 전체 Web120개 PASS. 일반 정지 후 방향/heartbeat 차단,
  강제 승격/활성 연결 Esc/기존 late-start 취소/한글 물리키 회귀 포함.
- `artifacts/two-stop-regression-20260928-r1`은 새 테스트의 Testing Library
  selector 타입 오류로 build FAIL. 테스트는 PASS였으나 전체 PASS로 간주하지 않는다.
  해당 옵션 수정 후 `artifacts/two-stop-regression-20260928-r2/manifest.json`
  전체/core163/Web120/production build PASS.
- 초기 fake mission 검사에서는 초미세 최종 spin이 같은 nanosecond timestamp의
  가짜 센서 메시지를 중복 생성하여 observation 누락으로 FAIL했다. fixture가 실제처럼
  새 timestamp에만 메시지를 생성하도록 수정했다. production 센서 검증 기준은 완화하지 않았다.

## 최종 확인 — 08:44 KST

- `artifacts/two-stop-browser-20260928-r2/result.json`: 실제 App/Chrome와
  생산 worker의 **가짜 장치 통합 20단계 PASS**. 수동 조작 및 mission 양쪽에서
  일반/강제 정지, 키를 누른 중 Esc, 이력 내보내기, 단절 종료를 확인했다.
  terminal 정지5세션 모두 수락 후 추가 published=0, cleanup_confirmed=true.
  13로그/1074events(robot664), 가짜 출력80회. 실물 이동 증거가 아니다.
- r1 통합도 PASS였으나 캡처에서 기존 패드의 grid 배치가 강제 버튼을 다음 줄로
  옮기는 것을 확인했다. CSS만 수정하고 `pnpm build` PASS 후 r2 통합을 재실행했다.
  최종 `two-stop-controls.png`를 직접 확인했다. 모바일 가로 넘침·외부 요청·페이지 오류0.
- `artifacts/two-stop-isaac-20260928-r2/result.json`: 같은 최종 빌드의 기존
  실제 App/bridge/Isaac 표시 회귀 **8체크 PASS**. 기존 근사 방/Burger·합성B
  3시점과 USD 재열기/원본 보존 검사다. 새로운 정지 동작을 물리 시뮬레이션한
  결과가 아니며 Physics Run/로봇/provider0. 기존 VtValue 종료 경고는 보존했다.
- `artifacts/two-stop-evidence-audit-20260928-r2/result.json`: 현재 선택50개
  source/build 및 공통해시/dist 목록 일치 PASS. audit 자체 단위6개 PASS.
  전체 회귀 r2는 CSS 배치 수정 전이며, 최종 CSS에는 재빌드/브라우저20/Isaac8을
  수행했다. regression manifest에는 source hash 결속이 없고, audit은 완전한
  저장소 인증이나 독립 실물 acceptance가 아니다. 모든 검증 프로세스 정상 종료.

## 실물 경계 및 다음 단계

구현·가짜 장치 검증은 실물 정지 성공이 아니다. 새 코드가 로봇에 배포되지 않았으므로
기존 열린 화면/로봇 패키지에 적용됐다고 가정할 수 없다. 패키지 변경 시 기존
boot/release 결속 자격을 재사용하지 않는다. 실제 배포·제동 확인은 별도 승인 이후다.

100/50ms는 로컬 **논리 구간 상한**이지 클릭부터 실제 정지까지의 보장 시간이 아니다.
통신/스케줄링/서비스 호출/기계 감속·관측 시간이 더해진다. 두 동작 모두 기존 halt/OFF를
쓰며 새 토크 ramp나 제동 제어를 구현한 것은 아니다. 부하 감소·제동 거리·정지 시간은
실물 미검증이다. 위험 시 부하 걱정으로 강제 STOP을 늦추지 않는다.

실제 자율 임무의 검토된 보정·배포 등록/readiness, 방 Twin 목표↔odom 결속,
장애물 우회/재계획 및 실측 정합 재생은 기존 잔여 작업으로 유지한다.
