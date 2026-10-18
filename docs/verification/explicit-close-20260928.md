# N3 부분 — 명시 종료와 통신 실패 분리

2026-09-28 05:25 KST. 로봇 OFF, 실제 접속/센서/모터/배포0.

## 원인과 수정

이전 PC `input(close)`는 `_cancel()`로 곧바로 stdin을 닫았다. worker는 명시적
close 명령을 받지 못하고 EOF를 INPUT_CLOSED_OR_OVERFLOW로 처리했다. 실제 App→
가짜 worker에서도 UI 정상 종료가 FAILED로 저장되는 현상이 확인되어 있었다.

- 준비된 control/qualify 세션의 명시 close는 기존 sequence로 close packet을
  보내고 입력 통로를 열어 둔 채 FINISHED를 기다린다. 대기 중 신규 이동 입력은
  거절하고 대기열의 이전 입력을 제거한다. 이미 전송 중인 입력의 전달을 취소했다고
  주장하지 않으며 원래 입력 기한·로봇 출력 만료 계층을 그대로 유지한다.
- 대기 중 PC 500ms 무입력 감시가 먼저 EOF를 보내지 않도록 분리했다. **로봇
  입력250ms/hold2초/session60초/출력 만료·정지 정책은 변경하지 않았다.**
  종료는 challenge 없이 기존 stop/close 계약으로 처리하며 재활성화하지 않는다.
- 실제 전송/기록 실패, 앱 종료, FINISHED 이후 정리는 기존 EOF 경로로 전환한다.
  기존20초 한도의 소유 child 종료도 유지하며 다른 프로세스는 종료하지 않는다.
  종료 버튼 반복 입력은 기한을 늘리거나 close를 반복 전송하지 않는다.
- 결과가 도착하지 않으면 STOPPING/CONNECTION_LOST이며 cleanup 성공을 추정하지
  않는다. 명시 종료 도중 정지시험 중단은 기존 TRIAL_INTERRUPTED 실패로 남는다.
  준비 전 취소와 off/prepare/lidar 기존 취소 동작은 바꾸지 않았다.
- worker의 OPERATOR_STOP도 최종 ROS halt 실패가 있으면
  FINAL_ROS_STOP_UNCONFIRMED로 표시한다. 최종 독립 OFF/idle 실패는 별도로
  FINAL_IDLE_UNCONFIRMED가 우선한다. 기존 qualification 생성 조건은 그대로다.

## 검증

- focused54 PASS: 신규 PC2는 close packet/대기열 제거/반복 전송 없음/EOF 전환,
  650ms 대기 중 통로 유지·무응답 결과 미확인·추가 이동 거절·앱 종료를 검사한다.
  신규 worker1은 ROS/최종idle 조합3종을 검사한다. 이전 close loop/시간만료 회귀 포함.
- `artifacts/explicit-close-regression-20260928-r1/manifest.json`: 전체 오프라인
  core156/Web106/TypeScript/build PASS. 이번 수정의 테스트 실패 없음.
- `artifacts/explicit-close-browser-20260928-r1/result.json`: 실제 Chrome→격리
  App/API→가짜 device12단계 PASS. UI 종료→OPERATOR_STOP·cleanup true가 저장이력
  JSON까지 일치하고, 입력 전달을 끊은 별도 세션은 FAILED로 남는 것을 새 assert로 검사.
  fake 출력29, 5로그500events(robot244), 미수신 navigation9개 보존.
  source/dist 불일치0, 외부요청0/페이지오류0/원래 project 불변.
- 이전 FAILED 기록을 수정하거나 지우지 않았다. 이번 OPERATOR_STOP는 가짜
  장치 결과이며 실제 로봇 정지·주행 성공이나 새 실물 qualification이 아니다.

실제 배포·반복 입력·종료 인수는 사용자 복귀 후 별도 승인까지 대기한다.
같은 빌드의 N6 실제 Isaac 재검증도 완료했다:
`artifacts/overnight-integration-isaac-20260928-r1/result.json` PASS, 실제 browser/API/
broker/production bridge→방·공식 Burger 표시·합성 A/B 비교·B0/140/280 시점 pose/yaw,
저장 USD 재열기·변조거절·원래 project/외부 prim 보존·단절/복구 포함8체크 PASS.
source/dist 불일치0, 캡처 직접 확인. 로봇/외부provider0·Physics Run0이며 사진의
상자형 근사 방과 표시 모델이다. 실제 물리 주행/측정 pose 재생으로 승격하지 않는다.
다음은 최종 같은 build에서 사진 방/Burger→합성 임무/비교→actual Isaac 시점
표시 결과를 묶고, 남은 실물 의존성과 아침 순서를 하나의 인수인계로 정리하는 N6다.
