# N2/N3 — 시작 응답과 현장 확인 수명 경합 수정

2026-09-28 06:24 KST. 로봇 OFF. 실제 접속·배포·센서·모터·전원 제어0.

## 재현과 수정

기존 PhysicalRobotController는 start 응답 전에 창을 떠나면 job id가 없어 종료
요청을 보내지 못했고, 나중에 READY 응답이 오면 현장 확인 ref가 남아 방향 입력을
활성화할 수 있었다. backendReady=false일 때 확인/시작 버튼도 잠기지 않았다.

- 신규 UI 테스트 **5 FAIL / 기존9 PASS**로 재현했다: 시작 응답을 지연시킨 뒤
  window blur, Esc, backend 상실, unmount4종 및 backend 준비 전 작업 거절.
- 시작 요청의 context epoch와 요청 job을 결속했다. 창/영역 이탈·Esc·연결 상실·
  unmount는 승인 ref를 즉시 폐기한다. 늦은 응답은 해당 요청의 **owned job에만
  close**를 보낼 수 있고 이동/유지 입력을 보내거나 권한을 복원할 수 없다.
- 해제/종료 응답 및 읽기 조회는 승인하지 않는다. 종료 후 읽기 polling은 해당
  job 결과 관찰만 가능하다. backend 복구·옛 READY 조회로 재활성화하지 않는다.
- 방향/시험 실행에 backend 준비·현재 owned job·유효 현장 확인을 함께 요구한다.
  backend가 없으면 새 작업/확인/읽기 버튼을 비활성화한다. 종료 요청은 별개다.
- 동기 ref로 중복 시작을 막는다. 시작 응답 자체가 실패하면 같은 요청 id의
  관측된 작업만 종료하며 시작을 자동 재시도하지 않는다.

**서버가 이미 수락한 준비 작업을 소급 취소했다는 뜻은 아니다.** 종료 응답이
없으면 실제 정지는 미확인이다. 기존 로봇 local 입력/출력 기한, hold2초/session60초,
정지시험 기준/boot-release receipt는 바꾸지 않았다. 실제 로봇에서 시험하지 않았다.

## 검증

- 수정 후 컨트롤러 React14 PASS(신규5 포함).
- `artifacts/start-context-regression-20260928-r1/manifest.json`: 전체 오프라인
  core156/Web111/TypeScript/build 및 기존 integration 그룹 PASS.
- `artifacts/start-context-browser-20260928-r1/result.json`: 실제 Chrome→격리
  App/API→가짜 process13단계 PASS. 시작 응답 보류→blur→응답 전달 경우 요청은
  **close1회만**, watch/이동0, 해당 job robot_published0. 결과 조회 후에도 잠김.
  기존 같은 세션 WASD/마우스4방향·release/종료·이력/라이다·입력 손실도 PASS.
  전체 fake 출력27,6로그495events(robot240), 외부요청/페이지오류0·원본project불변.
- `artifacts/start-context-isaac-20260928-r1/result.json`: 같은 빌드 actual App/
  broker/production bridge/Isaac8체크 PASS. 합성B0/140/280 pose/yaw, USD재열기,
  단절/복구/변조 거절·원본/외부prim 보존. 사진 근사 상자 방/Burger 캡처 직접 확인.
  Physics Run/실물/유료provider0, alignment_verified=false.
- `artifacts/overnight-evidence-audit-20260928-r2/result.json`: 현재 source/build
  기록39파일·공통해시·dist목록 일치. audit기존6 재검사 PASS. 새 회귀/브라우저/Isaac
  경로를 명시적으로 선택했으며 예전 r1 결과/과거 FAIL은 보존했다.

현재 source를 수정했으므로 05:55 r1 audit는 **당시 빌드의 역사적 기록**이다.
새 current 증거는 위 r2이며, checksum 대조를 runtime/실물 성공으로 해석하지 않는다.
N2 통합 readiness 및 실TF/로컬 scan guard/자율worker·재계획 등 실물 자율 구현
잔여는 그대로다. 다음은 07:00 이전 최종 증거/인수인계 확인, 마감 후 예약 중지.

## 06:49 마감 전 최종 검수

`launch_robot_console.py`의 오래된 "Use PC preparation first" 시작 문구를 연결
버튼 내부 PC 점검 방식으로 수정했다. 읽기 점검이 이동을 활성화하지 않는다는
안내를 함께 출력한다. 기존 local launcher lifecycle 테스트에 출력 assertion을
추가했고, mock browser/격리 root에서 실제 loopback server 시작·종료 및 collector
호출0을 검사했다. 사용자 창/실제 로봇을 열거나 연결하지 않았다.

- `artifacts/overnight-final-regression-20260928-r1/manifest.json` 전체 PASS:
  core156/Web111/build와 기존 integration 그룹(수정된 launcher 시험 포함).
- `artifacts/overnight-evidence-audit-20260928-r3/result.json` PASS/39파일일치;
  audit6 재검사 PASS. Web 빌드 해시는 06:24 actual browser13/Isaac8 검증과 동일하다.
  이번에는 실제 브라우저/Isaac를 새로 실행하지 않았다. launcher 파일은 해당
  두 browser-run의39파일 coverage 밖이며 이번 전체회귀의 lifecycle 시험으로 확인했다.
- 로봇/배포/실물/유료0. 기준·입력 제한·현재 실물 자율 준비 상태 변경 없음.

현재 작업 프로세스는 종료됐고 07:00 이후 새 구현 없이 최종 보고/예약 PAUSED가
남는다. 실제 자율 데모는 미완료다. 추가 실물 준비를 사용자에게 요구하기 전에
N2 readiness·N4 실센서/TF/local guard·자율 worker 등 개발 잔여부터 해결해야 한다.
