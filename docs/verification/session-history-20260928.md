# N3 부분 — 저장 조작 이력 / 명령-관측 조회

2026-09-28 04:00 KST. 로봇 OFF, SSH/serial/실센서/모터/배포/Isaac 실행0.
정지 정책·과거 FAIL·실측 원본은 변경하지 않았다.

## 연결한 제품 경로

기존 실물 컨트롤러 아래 `저장된 조작 이력` → 명시 목록 조회 → 기록 선택 →
명령·관측 표/종료 결과 → 검토 JSON 저장. 인증된 GET 두 경로
`/v1/product/robot/physical/history`, `.../history/<32hex-job>`만 추가했다.
기존 PhysicalController root 아래의 고정 `artifacts/manual-control`만 읽으며
호스트/파일 경로/명령 입력을 받지 않는다. 생성·변경·연결·재실행은 하지 않는다.
사용자 기존 실행창을 자동 교체하거나 재시작하지 않았다.

- root/하위 경로가 다른 곳으로 해석되는 링크와 잘못된 ID를 거절한다.
  디렉터리 항목1024개까지, 파일 수정 시각 순 최근20개 목록, 파일8MiB/8192행/
  한 행64KiB, 최종 result512KiB 상한. 목록의 날짜는 실행 시각 보장이 아닌 파일 mtime다.
- JSON 중복키·비유한수·알 수 없는 필드/종류·다른 PC job·순서/clock/provenance
  혼합·robot session/index/time 불연속을 거절한다. 내부 오류/경로/원시 내용은 반환하지 않는다.
  완전한 행 중 하나라도 손상됐으면 일부를 성공으로 꾸며내지 않고 전체 조회를 거절한다.
- 마지막 newline 없는 tail만 제외하고 앞의 검증된 행을 미완료로 표시한다.
  원본을 자르거나 덮어쓰지 않는다. 파일이 읽는 중 변경되면 조회를 거절한다.
- 기록 종료 표식과 event 수/transport가 맞고 tail이 없을 때만 COMPLETE_RECORD.
  완료 표식 누락/손상/불일치는 INCOMPLETE_RECORD. 이 표식은 로컬 기록 메타데이터이며
  인증된 실물 증명이나 조작 승인으로 사용하지 않는다.
- 가짜/실제 transport 선언을 구분한다. `motion_authorized=false`,
  `physical_success=null`, `floor_pose_measured=false`는 항상 유지한다.
- 입력/전송/수락/발행/관측 개수와 기록된 종료 status/reason을 표시한다.
  **종료 기록 일치와 작업 성공은 다르다.** 검사한 가짜 수동 종료는 기존 EOF
  처리 때문에 FAILED/INPUT_CLOSED_OR_OVERFLOW를 기록했고, 그대로 표시·보존했다.
  명시 종료 의도와 원격 EOF 오류 분류의 개선은 이번 변경에 포함하지 않았다.
- 최근200개 ROS 발행에 대해 같은 로봇 clock에서 뒤따르는 0.5초 이내 표본만
  나란히 표시한다. 표본 time이 발행보다 이르면 사용하지 않으며 없으면 `관측 없음`.
  명령의 인과적 결과나 실제 차체 이동량으로 해석하지 않는다. PC clock과 합치지 않고
  encoder를 바닥 pose로 변환하거나 누락 odom/scan을 생성하지 않는다.
- JSON export는 검증·상한 적용된 **검토 요약**이다. 전체 원시 로그 대체/재실행
  입력이 아니며 원본 SHA256와 표시 생략 개수를 담는다. 예전 journal 없는 보고서는
  목록에 나오지 않고 기존 정지시험 요약 경로로만 조회된다.

## 검증

- 신규 history/API6 PASS: 새 PhysicalController 인스턴스에서 파일 읽기/연결0,
  인증 거절, 경로 거절, 20/200 표시 한도, 결과 count 불일치, 손상/tail 원본보존,
  잘못된 clock/provenance/index/session/비유한수/중복키/크기 거절, 관측 없음 유지.
- `artifacts/session-history-regression-20260928-r2/manifest.json`: 전체 오프라인
  회귀 PASS, core146/Web105/TypeScript/build. Web 신규3은 명시 조회만 실행,
  과거 상세 제거 후 실패/재시도 없음, backend 미준비·busy 조회 불가를 확인한다.
- `artifacts/session-history-browser-20260928-r2/result.json`: actual Chrome→
  격리 App/API→가짜 device12단계 PASS. 네 방향/한글키/해제/입력손실 회귀에
  저장 이력 선택·JSON 다운로드·페이지 reload 후 같은 파일 조회를 추가했다.
  조회 전후 job/sequence 불변, 새 연결 없이 다운로드한 provenance/authority 확인.
  fake 출력23, 5로그451events(robot210); 외부요청0/pageerror0/실수집0,
  원래 project 불변·source/dist SHA256 바인딩. 데스크톱/모바일 캡처 직접 확인.
  모바일 표는 자체 가로 스크롤이며 페이지 수평 넘침 없음.
- r1도 PASS였으며 보존했다. 종료 원인 표시와 명령/목록 상한 시험을 보강하고
  최종 고정 빌드 r2로 전체/브라우저를 재검증했다. 이번 runtime 테스트 실패 없음.

## 잔여와 다음 우선순위

현재 명령/표본 조회는 N3의 일부다. 로봇별 이동 보정/실제 odom·scan 시간축,
실측 TF·연속 Twin 재생·실물 인수는 남아 있다. 과거 기록이 현재 로봇 상태를
보증하지 않는다. 물리 센서/전원손실/주행 시험은 하지 않았다.

다음은 로그 화면 확대보다 **N4 기존 제품의 공통 제어 경로와 로봇 로컬 보호**다.
`local_navigation.py`의 합성용 검사를 기존 worker/adapter와 연결할 의존성을 읽고,
센서 source·TF·신선도·명령 만료·임무수명 검사를 가짜 장치에서 검증한다.
관측 없는 상황을 허용/회피 성공으로 바꾸지 않으며 실제 배포/작동은 하지 않는다.
N2 통합 readiness, N4 자동 우회/재계획, N5 실측/연속 재생, N6 실물 확인도 잔여다.
