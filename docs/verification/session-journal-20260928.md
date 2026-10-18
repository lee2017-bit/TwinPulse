# N3 부분 — 종료 전 세션 기록 보존과 App 관측 요약

2026-09-28 03:27 KST. 야간 오프라인 승인 범위. 로봇 OFF,
SSH/serial/실센서/모터/배포/Isaac 실행 0. 정지 정책과 기존 FAIL은 변경하지 않았다.

## 제품 경로와 구현

기존 PhysicalController의 메모리-only→종료 시 전체 저장을 별도의 bounded
`SessionJournal` writer로 변경했다. 기존 `artifacts/manual-control/<job>/session.jsonl`
파일을 실행 중에도 append하고 최대32개 묶음마다 flush+fsync를 요청한다.
명령/관측 원본 스키마와 서로 다른 PC/robot monotonic clock domain을 유지한다.

- 입력/HTTP/watchdog lock에서 디스크 쓰기·fsync를 하지 않는다. 저장 queue는
  256개, 기존 세션8192개 상한은 그대로다. 저장 queue 포화·쓰기 실패·미저장
  1초 초과가 감지되면 PC가 조작 종료를 요청한다. 기존 로봇 로컬 입력 만료와
  최종 독립 OFF는 그대로이며 PC 요청만으로 실제 정지를 보장하지 않는다.
- 저장된 개수는 fsync 호출 성공 후 올린다. close 대기는 최대2초이며 실패나
  미종료 writer/세션 중단은 `session_log_complete=false`다. FINISHED가 원격
  FAILED인 경우에도 로그는 완전할 수 있다. **기록 완전성 ≠ 임무/이동 성공.**
- 독점 생성으로 이전 job 폴더·session/result를 덮어쓰지 않는다. 폴더 충돌은
  transport 시작 전 실패하며 예전 결과도 보존한다. 자체 test child 외 다른
  프로세스를 종료하지 않았다.
- 기존 인증 GET snapshot에 저장 현황과 PC 수신/pipe 전송/로봇 수락/ROS 발행/
  관측 개수를 연결하고 App 결과 패널에 표시한다. 저장 오류와 미완료를 표시하고
  읽기만으로 연결·이동 권한을 만들지 않는다. 입력 수에는 watch 유지 신호도 있다.
- 마지막 encoder/torque/원본 나이는 **스트림 표본 당시** 값이다. 최종 독립
  OFF 보고서와 시점이 다를 수 있으며, 마지막 표본이 ON이고 종료 보고서가 OFF일
  수 있다. encoder는 바닥 pose/거리/충돌 검증이 아니다. 없는 odom/scan을 만들지 않았다.

## 검증

- `tests.integration.test_physical_controller` 27 PASS(기존21+신규6).
  실행 중 파일 확인, queue 포화, fsync 지연/오류, 기존 폴더 보존, 인증/소유권,
  자기 child의 `os._exit` 후 fsync 완료12행 보존을 검사했다.
  최초 신규 crash fixture는 패키지 import 경로 누락으로 26/27 PASS·1 FAIL;
  경로만 수정한 후 단독27 및 전체 회귀 PASS. 테스트 실패를 실물 실패로 해석하지 않는다.
- `artifacts/session-journal-regression-20260928-r1/manifest.json`: 전체 오프라인
  회귀 PASS, core146 / 관련 physical·진단·robot단위 묶음80 / Web102 / build PASS.
  각 부분 집합 개수는 중복되므로 총합으로 표시하지 않는다.
- `artifacts/session-journal-browser-20260928-r1/result.json`: 실제 Chrome→격리
  App/API→가짜 device process 10단계 PASS. 조작 중 저장 확인/관측 요약,
  한글·WASD·네 방향 마우스·550ms 해제 후 같은 세션 유지/입력손실 종료 검증.
  fake 출력27, 세션5개/475 events/robot226. 종료 전 화면 363/364 저장 확인.
  외부 요청0/pageerror0/실수집0, 원래 project 불변·source/dist SHA 바인딩.
  `session-evidence.png`, `physical-mobile.png` 직접 확인. 모두 가짜 장치이며 실물 성공 아님.

## 한계 / 다음

OS fsync 성공과 process-exit 시험만 확인했다. 디스크 전원손실·하드웨어 캐시까지
보장하지 않으며 비정상 종료 직전 미저장 tail/부분 행이 남거나 유실될 수 있다.
완료 표식 없는 파일은 미완료 기록으로 다뤄야 한다. 파일은 남지만 **앱 서버 재시작
후 세션 이력 탐색/부분 행 복구·export는 아직 없다**. 현재/최근 메모리 세션 요약만
표시하며 과거 qualification 보고서 조회는 기존 경로다. 기존 원본은 수정하지 않는다.

다음 N3는 보존 로그를 bounded read-only history로 검증·조회하고 명령별 관측을
사용자가 볼 수 있게 연결하는 것이다. 임의 경로/비밀정보/손상 행/clock 혼합과
완료·실행 권한을 구분한다. 이후 N2 readiness 통합, N4 실물 local sensor/공통
adapter/임무 watchdog·재계획, N5 실측/연속재생, N6 실물 인수가 남아 있다.
실물 시험은 사용자 복귀 후 새 임무 범위 승인 전 실행하지 않는다.
