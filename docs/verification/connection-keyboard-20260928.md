# N2/N3 증분 — 연결 단일 동작 / 키보드 입력

2026-09-28 01:02 KST. 승인된 야간 오프라인 범위. 실제 로봇 OFF, 새 접속/배포/구동0.

## 구현

- `로봇 연결·묶음 점검` 클릭 안에서 기존 PC preflight → 새 토큰 → 기존 읽기 수집을
  순서대로 실행한다. 필수 PC 버튼과 읽기 전용 확인란을 제거했다.
  `PC만 점검`은 충전 중 사용할 선택 항목이다. 화면 열기에는 접속 없음.
- PC 누락 시 전송하지 않음. 연속 클릭은 in-flight ref로 차단, 준비 중 화면을 떠나면
  늦게 도착한 준비 응답으로 연결하지 않는다. 응답 손실 시 새 실행을 잠그고
  결과 조회부터 요구한다. 서버의 세션/파일해시/만료/단일작업/소비토큰 검사는 유지.
- 새 연결 시 과거 배터리를 화면에서 비우고 실패를 현재 값으로 가장하지 않는다.
  상태/배포/배터리/기존 센서 수집은 기존 normalized collector 그대로다.
- 오래된 '모터 OFF 화면/새 정지 진단 미구현' 안내를 제거하고 실제 제어 패널의
  현재 boot/release 검증과 읽기 관측을 구분한다. 같은 읽기 점검 반복을 요구하지 않는다.
- 수동/PC모의의 키 매핑을 `driveKeys.ts`로 공유. `KeyboardEvent.code` 우선으로
  한글 IME·Caps Lock을 처리하고 code 없는 경우에만 키 텍스트를 사용한다.
  입력란/contenteditable/브라우저 단축키는 이동 입력에서 제외한다.
- 준비 완료 시 해당 조작 영역에 포커스, 영역 밖/창 밖 이탈 시 종료 요청.
  physical 이벤트가 부모 PC모의 패널로 중복 전달되지 않도록 분리했다.
  기존 서버 정지 기준·실물 gate·60초 세션/2초 hold 제한은 변경하지 않았다.

## 최종 동일 빌드 검증

- `artifacts/connection-keyboard-regression-20260928-r2/manifest.json`: 기존 전체
  오프라인 검사 PASS, core138 / Web95 / TypeScript·production build PASS.
  새 연결 tests6(기존2 대체), key helper3, physical UI1 추가. 부분집합 중복 합산 금지.
- `artifacts/connection-integrated-browser-20260928-r4/result.json`: 실제 Chrome/App/API,
  합성 collector3회로6단계 PASS. 선택 PC 무통신, 단일 클릭/진행/저장, reload 읽기,
  개별 토크 원인, 실패 후 과거 전압 제거, 모바일 overflow/외부요청/engine명령0.
- `artifacts/keyboard-physical-fake-20260928-r3/result.json`: 실제 App/API/프로세스 경로,
  **가짜 장치**9단계 PASS. 미검증 잠금, 가짜 시험, 한글/대문자 키4방향과 release,
  같은 가짜세션 유지, 마우스4방향, 종료/라이다/입력손실. fake출력26개이며
  모든 방향이 전달됨. 실제 로봇 정지·반복 주행 성공을 뜻하지 않는다.
- `artifacts/keyboard-rehearsal-20260928-r3/result.json`: PC모의6단계 PASS.
  실제 로봇/센서/Isaac0, collector0, 원본 프로젝트 불변.
- 위3개 결과에 source/dist 해시 기록. 데스크톱/모바일 캡처 직접 확인.
  캡처의11.21V/39.4%는 합성 fixture이며 현재 배터리 값이 아니다.
- 기존 실행창을 종료하거나 교체하지 않았고, 사용자 실행으로 새 빌드를 적용해야 한다.

## 실패와 한계

PC모의 브라우저 r1은 초기 physical 패널이 기존 저장 상태를 읽어 NOT_STARTED라고
가정한 테스트가 실패했다. 테스트 runner의 모든 physical adapter를 출력 디렉터리와
가짜 명령으로 격리해 r2/r3 PASS. r1을 보존했고 실제 연결을 시도하지 않았다.

N2는 **PC 준비 통합/읽기 경로**까지다. 연결 결과와 로봇 측 qualification receipt를
한 readiness 상태로 묶고 필요한 경우에만 정지검증을 안내하는 통합은 남았다.
N3는 **키보드/포커스**까지만 완료. 실제 매 입력 후 종료 문제는 여전히 미해결이다:

- `teleop_ros.py:halt`의 `.25s` 대기와 `.2s` 안정 확인이 일반 release에 남아 있다.
- `teleop_contract.py:InputGate.check`가 입력 만료/hold/session을 같은 오류로 묶는다.
- 명령·송신·실행·encoder/odom/scan/배터리의 공통 세션 시간축 로그는 미구현.

다음은 위 로봇 로컬 코드의 일반 release/종료 분리와 원인별 상태/관측 로그를
오프라인 시간축 시험으로 검증한다. 기존 정지 FAIL/실측 원본 및 보호 조건 보존.
실물 정지 성능 기준을 완화하거나 가짜 성공을 qualification으로 사용하지 않는다.
N4 자율 임무/로컬 충돌 방지, N5 재생/동일조건 비교, N6 전체 통합은 미완료.
