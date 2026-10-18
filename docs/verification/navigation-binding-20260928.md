# N4 부분 — 수신 센서와 로봇 출력 검사 연결

2026-09-28 07:20 KST. 07:00 야간 예약은 PAUSED로 종료했고, 사용자
`그래? 그럼 일단 그거 계속 진행해`의 새 승인으로 오프라인 구현을 이어갔다.
로봇 접속·센서 실행·배포·구동은 하지 않았다. **실물 자율 실행 완료가 아니다.**

## 구현

- 기존 `RosObservations`의 raw odom/scan을 새 `navigation_inputs`에 연결했다.
  프레임 이름, source/receipt 시각, 200ms 미만 신선도, 50ms 이내 표본 시차,
  평면 odom quaternion, 완결된 전방위 스캔을 검사한다. 누락/오래된 값은 거절한다.
- `PlanarBinding`은 odom child→base와 base→scan의 평면 변환, 차체 원형 반경,
  근거 digest를 명시적으로 요구한다. **digest 형식 검사만으로 근거의 진위나
  실측 보정을 증명하지 않는다.** 실제 사용자 로봇용 binding은 만들지 않았으며
  테스트만 인공 binding을 주입한다. 향후 검토된 근거를 읽고 결속하는 loader가 필요하다.
- odom의 child 좌표를 회전/이동해 base pose로 변환한다. scan 원본을 base 프레임
  실측 ray로 바꿔 표시하지 않는다. 센서 중심에서 계산한 원형 여유 공간에서
  센서 offset 길이를 빼 `LocalClearance`라는 별도 파생값으로 전달한다.
  마지막 ray→첫 ray의 각도 간격도 포함하며, 차체 반경은 기존 0.18m보다 줄이지 않는다.
- 기존 `RosLink`에 `navigation_step`을 추가했다. `CheckedMission` 판단 →
  arm 전 검사 → arm 후 최신 관측 재검사 → 최종 publish 직전 재검사를 연결한다.
  원래 명령 생성 시각을 보존하며 활성화 중 만료를 새 명령으로 갱신하지 않는다.
  부분 arm 실패도 stop/OFF 정리를 시도하고, 정지 확인 실패를 성공으로 바꾸지 않는다.
- 이 메서드는 **아직 CLI/UI의 자율 실행 진입점에서 호출하지 않는다.** 기존
  현장주시 수동 조작은 여전히 scan 검사를 사용하지 않는 별도 경로다.
  자율 owner가 qualification/lease·bounded loop·독립 최종 OFF를 책임지는 연결이 남았다.
- 새 core 파일은 로봇 bundle에 동일 바이트로 포함되며 manifest 필수 파일로 검사한다.
  패키지를 준비하는 코드만 수정했으며 전송·배포하지 않았다. 과거 FAIL/정지 정책은 불변이다.

## 실제 수행한 오프라인 검증

| 검증 | 결과와 근거 |
|---|---|
| 좌표/시간/누락/offset/원본보존/반경 | 신규 core 7 PASS |
| production RosLink + 가짜 관측/시계/출력 | 신규 5 포함 `test_physical_controller` 44 PASS. 정상 출력의 원래 stamp, arm 전 장애물/누락 거절, arm 중 stale/장애물/서비스 실패/명령 만료, 최종 출력 재검사, 도착/정지 실패 검사 |
| 전체 회귀 | `artifacts/navigation-binding-regression-20260928-r2/manifest.json` PASS. core163/Web111/build 및 기존 integration 그룹 |
| 실제 App/Chrome→가짜 장치 | `artifacts/navigation-binding-browser-20260928-r1/result.json` PASS, 13단계·출력28·6로그487events(robot235). 실제 로봇 수신이 아니며 기존 수동 경로 회귀 |
| 실제 App/bridge/Isaac 표시 | `artifacts/navigation-binding-isaac-20260928-r1/result.json` PASS, 8체크·Burger4mesh·합성B0/140/280 pose/yaw·USD재열기·원본보존. physics Run/실물0 |
| 기록과 현재 파일 대조 | `artifacts/navigation-binding-evidence-audit-20260928-r1/result.json` PASS,43파일·공통해시/dist목록 일치. audit 기존6 PASS |

초기 단독 integration은 sandbox Temp 접근 오류가 발생했고 허용된 로컬 재실행으로
44 PASS를 확인했다. 전체 r1은 가짜 release manifest에 새 파일을 반영하지 않아
9 ERROR로 종료했다. 해당 fixture를 수정한 r2가 PASS이며 r1은 삭제하지 않았다.
Isaac 종료의 기존 VtValue 경고는 기록에 남으며 결과 파일/실제 stage 확인은 PASS다.
검증 스크립트의 source hash 목록은 새 binding/test/prepare 코드까지 추가했다.

## 아직 미완료인 것 / 다음 구현

1. 검토된 로봇 frame/footprint 근거를 현재 boot·release·sensor 설정과 결속하는
   loader/readiness. 현재 숫자나 사진에서 실측 TF를 추측하지 않는다.
2. 기존 worker 소유권·정지검증·로컬 시간제한에 새 navigation adapter를 연결한
   자율 임무 loop, 독립 watchdog/종료·취소 및 명령/관측/판단 세션 기록.
   임무 내 매 명령 사용자 클릭을 요구하지 않는 구조로 구현한다.
3. 현재 장애물 처리는 terminal stop이다. 센서 기반 우회·재계획은 아직 없다.
4. 별도 승인 후 실제 센서/배포/정지·주행 검증. 2D ray 사이, 유리/낮거나 높은
   물체, 미끄러짐, 실제 정지거리와 반경은 이 테스트로 보장되지 않는다.

합성 기존 trace/사진 근사방을 실제 측정 결과로 승격하지 않았고, 새 API/조작 버튼이나
자동 연결·자동 실물 실행 권한도 추가하지 않았다. 야간 예약은 계속 PAUSED다.
