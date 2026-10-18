# N4 부분 — 공통 출력 검사와 관측 기반 임무 계약

2026-09-28 04:30 KST. 로봇 OFF; SSH/serial/실센서/모터/배포/Isaac 실행0.
기존 정지 정책·qualification·수동 입력/연결 기한·과거 FAIL을 바꾸지 않았다.

## 실제 연결한 경로

- `local_navigation.checked_command`를 기존 방 합성 adapter와 `RosLink.publish`에
  연결했다. 유한 속도/저속 상한(0.03m/s, 0.2rad/s), 원래 명령 나이(0≤age<250ms)를
  검사한다. 출력 시각으로 입력을 새로 고치거나 arm/lease를 부여하지 않는다.
- 준비 tar에 core의 `local_navigation.py` 바이트를 그대로 넣고 로봇 worker의
  필수 manifest 파일로 검사한다. 기존 ROS adapter는 이 묶음 파일을 우선 import한다.
  PC 테스트만 core package fallback을 사용한다. 이번에는 임시 tar 내용을 검사했을
  뿐 실제 준비 명령 실행·로봇 전송·설치·새 qualification은 하지 않았다.
- **기존 현장 주시 수동/정지시험 경로는 `require_scan=False`다.** 이 경로가 통과한
  이유는 `SUPERVISED_WITHOUT_SCAN_CHECK`이며 라이다 충돌 검사 통과가 아니다.
  현재 RosLink에는 실제 scan/odom/TF 수신이 없으므로 있는 것으로 꾸미지 않았다.
- `CheckedMission`을 기존 제품 합성 임무에 적용했다. 현재 pose/source/frame/basis와
  200ms 미만 표본 나이, scan의 출처·좌표·200ms 신선도·전방위 자료, 명령 만료를
  검사한다. 임무 기한은 수동 2초 hold와 별도이며 임무 안의 매 명령 승인은 없다.
  누락/과거/미래/출처 혼합/clock 역행/기한 만료는 0 출력과 종료 상태로 고정한다.
  신선한 표본이 뒤늦게 와도 자동 재개하지 않는다.
- 합성 임무는 이 결정의 출력을 그대로 기존 kinematic adapter에 적용한다.
  기존 route/blocked/stale/direct 기록·비교 해시는 유지된다. 저속 원형 envelope,
  반경0.18m/여유0.05m/1.2초 예산은 기존 합성 설계값이며 실측 정지거리 보증이 아니다.

`live_sensor`, `measured_odometry`, `measured_sensor_extrinsic`은 입력 계약의 선언이다.
이 문자열만으로 관측의 진실성/실측 TF를 증명하지 않는다. 실제 수신 adapter,
출처 결속·ROS/monotonic clock 변환, robot-local 임무 루프/중단 처리와 실측 검증이
남았다. `CheckedMission`은 호출될 때 검사하는 순수 함수 계층으로, 혼자 작동하는
watchdog나 실제 자율 실행 진입점이 아니다. 기존 수동 출력 만료 계층은 유지했다.

## 검증

- focused core/bedroom/physical/worker70 PASS, 최종 합성 adapter 정리 후 bedroom9 PASS.
  신규 core4, physical2 및 기존 ROS 나이 시험의 NaN/속도 상한 사례를 추가했다.
  임무 수명/도착/clock·pose·scan·명령 오류의 terminal0, fake ROS 발행 원래 시각
  보존과 scan 누락 후0 출력·재개 불가, tar의 core 원본 바이트 일치를 검사했다.
  fake ROS 시험은 실제 rclpy/센서/모터를 생성하지 않는다.
- `artifacts/shared-command-regression-20260928-r2/manifest.json`: 전체 오프라인
  회귀 PASS, core150/Web105/TypeScript/build. r1도 PASS였지만 합성 adapter의
  checked decision 직접 적용 정리 전 실행이므로 최종 고정 코드로 r2를 재실행했다.
- `artifacts/shared-command-bedroom-20260928-r1/result.json`: 실제 Chrome→격리
  App/API 합성 임무6단계 PASS. 정상·장애물·센서 지연, 동일조건 비교/기록선택/
  JSON export·모바일. 외부/로봇/engine 요청0, 원래 project 불변.
- `artifacts/shared-command-browser-20260928-r1/result.json`: 실제 Chrome→격리
  App/API→가짜 장치12단계 PASS. 네 방향·한글/code·같은 연결 반복입력·해제·
  입력 손실·기록 저장/이력 export/reload. fake 출력25, 5로그462events(robot215).
  외부요청0/페이지오류0/실수집0, 원래 project 불변. 두 브라우저 source/dist
  SHA256와 최종 파일의 불일치0. UI 시각 디자인은 이번 증분에서 변경하지 않았다.

## 남은 작업

공통 출력의 속도/나이 검사는 제품 양쪽에 연결됐지만 **실물 공통 자율 adapter와
로봇 로컬 라이다 충돌방지는 아직 완료되지 않았다.** 다음 우선순위는 실제 센서
수신 경계/시간·좌표 결속과 기존 worker lifecycle의 오프라인 가짜 검증이다.
센서 드라이버 시작이나 실제 연결은 사용자가 돌아온 뒤 새 승인 전까지 금지한다.
자동 우회/재계획, 실측 TF·odom/scan 로그와 연속 Twin 재생, N2 readiness,
통합 실물 인수도 잔여다. 새 bundle은 미배포이며 과거 실물 receipt를 새 버전의
통과 증거로 재사용하지 않는다. 이 결과는 전체 실물 데모 완료가 아니다.
