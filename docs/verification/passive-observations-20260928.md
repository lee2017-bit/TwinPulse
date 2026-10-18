# N3/N4 부분 — 기존 ROS 수신과 세션 관측 경계

2026-09-28 05:00 KST. 로봇 OFF, 실제 SSH/ROS/serial/센서/모터/배포/Isaac0.
이번 구현은 기존 세션에 **수동적인 odom/scan 관측 기록**을 붙인 것이다.
실물 자율 실행이나 라이다 충돌 방지 완성으로 해석하지 않는다.

## 기존 제품에 연결한 내용

- `RosLink`의 기존 namespace(`/tp_guard_stationary`)에 `odom`, `scan` 구독 추가.
  드라이버/라이다 회전/TF listener/서비스/센서 발행자를 시작하지 않는다.
  실제 scan이 다른 namespace에만 발행되거나 꺼져 있으면 미수신이다.
  기존 serial 라이다8초 작업과 동시 구동하거나 합치지 않았다.
- core `RosObservations`를 동일 바이트로 robot bundle에 포함하고 필수 manifest에
  추가했다. PC와 worker가 같은 검토 schema를 사용한다. 새 bundle은 미배포다.
- 각 topic의 ROS header 원래 stamp, 수신 monotonic 시각, 원래 frame을 보존한다.
  `sample_s=receipt_s-source_age`로 계산하며 수신 순간을 측정 순간으로 바꾸지 않는다.
  source age 0..200ms 미만, 증가하는 stamp, 발행자 수1, 유한수/크기/범위를 검사한다.
  ROS-monotonic offset이 초기값에서50ms 넘게 바뀌거나 시간 역행이면 두 관측을
  해당 객체 수명 동안 CLOCK_FAULT로 고정한다. 이는 PC/로봇 시계 동기화가 아니다.
- odom 원래 position3/quaternion4/parent·child frame을 보존한다. quaternion 정규화
  오차0.001 한도, 위치±1000m는 자료 형식 상한이지 위치 정확도 증명이 아니다.
  covariance/위치 추정 품질/휠 미끄러짐은 검사하지 않는다.
- scan72..720개, 증가하는 균일 각도/전방위 범위(허용오차0.01rad), 유한 유효거리,
  첫 ray source stamp부터 마지막 ray까지 수신 전에 끝난 sweep만 기록한다.
  결측/NaN/Inf를 최대거리로 채우지 않는다. 자료가 이 보수적인 계약과 다르면
  INVALID_MESSAGE로 기록한다. 실제 장치의 timestamp/각도 형식 호환성은 미검증이다.
- 잘못된 새 메시지로 이전 정상 값을 계속 보여주지 않는다. snapshot 시점에 낡은
  값은 STALE/null로 표시한다. 원본 `base_scan`/`base_footprint` 등을 임의로
  `base_link`로 바꾸지 않는다. source count는 인증된 센서 신원/TF 증명이 아니다.
- 기존 control loop가 약1초 간격으로 `navigation` 이벤트를 세션 journal에 저장.
  최대720ray를 보존할 수 있도록 이벤트 전달 상한16→32KiB로 늘렸고, 전체 로그
  8192행/조회8MiB·기존 robot4096행/실행시간 제한은 그대로 유지했다.
  정지 정책이나 출력/입력 만료 기준 변경이 아니다. 기록은 모든 센서 frame이
  아니며 실시간 collision loop 또는 센서 손실 watchdog가 아니다.
- 인증된 기존 이력 조회/JSON에 최근60개 navigation snapshot과 생략 수를 추가.
  App에는 기록 수와 실제로 값이 있는 odom/scan 수를 구분한다. 없는 자료는 null,
  `alignment_verified=false`, `motion_authorized=false`를 강제한다. 이전 로그는
  관측0으로 표시하며 원본은 변경하지 않는다. odom을 바닥 실측 pose로 인증하지 않는다.

## 검증 결과

- 첫 focused 실행은 새 test 모듈의 core import 경로 누락으로1 ERROR. 장치 실행
  전 오류이며 테스트 경로를 추가해 수정했다. 최종 focused57 PASS(core6 신규,
  ROS init/callback fake 및 journal review2 신규, 기존 worker/physical 포함).
- 가짜 ROS 모듈로 실제 `RosLink.__init__`와 callback 경로를 실행: 네 구독만 생성,
  기존 command publisher1 유지, enable/driver start 없음. raw frame/age 보존 확인.
  유효자료·미수신·stale/future/중복/역행·발행자0/2·잘못된 각도/거리/부분sweep·
  clock jump·권한/정합 위조·사본 변조를 검사했다. 실제 rclpy runtime 검증은 아니다.
- `artifacts/passive-observations-regression-20260928-r1/manifest.json`: 전체
  오프라인 회귀 PASS, core156/Web106/TypeScript/build. Web 신규1은 수신 수와
  미정합 안내/읽기 전용 동작을 검증한다.
- `artifacts/passive-observations-browser-20260928-r1/result.json`: actual Chrome→
  격리 App/API→가짜 장치12단계 PASS. fake 출력28, 5로그498events(robot240),
  이력 JSON에 미수신 navigation9개/null/권한false 보존. 실제 센서 값을 가짜로
  채우지 않았다. 외부요청0·pageerror0·원래 project 불변·source/dist 불일치0.
  이력 desktop 캡처를 직접 확인했다. 기존 EOF 종료 FAILED는 그대로 보존했다.

## 미완료와 다음

현재 수동 출력은 여전히 scan 검사를 사용하지 않는다. 수신값을 `LocalScan`/
`LocalPose`의 검증된 base 좌표로 승격시키는 변환 경로도 없다. **실측 TF, 장치
timestamp/scan 형식 확인, ROS runtime, 실제 라이다 수신/주행 및 새 배포는 미검증.**
임무 robot-local 실행/중단 lifecycle와 센서 연결·재계획도 남아 있다.

다음은 새 기능을 늘리기 전에 **정상 종료 의도와 EOF/통신 실패 분류를 기존
controller/worker에서 바로잡고 통합 리허설에 묶기**다. 지금 정상 UI 종료도
가짜 실행에서 FAILED/INPUT_CLOSED_OR_OVERFLOW로 남는 것이 확인되어 있으며,
실제 정지 확인 실패를 성공으로 바꾸지 않는 조건에서 수정해야 한다.
이후 07:00까지 가능한 N2/N4 준비와 통합 인수인계를 진행한다. 실물 작업은 별도 승인 대기.
