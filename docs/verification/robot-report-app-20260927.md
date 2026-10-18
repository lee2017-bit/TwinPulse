# D4 첫 부분: 저장 로봇 보고서 → App — 2026-09-27

사용자가 수면 중 약8시간 동안 가능한 선행 구현·시험을 요청했다.
이번 실행은 로컬 파일/HTTP/Chrome/기존 WSL만 사용했다. 실제 로봇 접속,
SSH/serial/센서/모터/전원 조작, 유료 API, 시스템 설치, commit/push는0회.

## 구현

- `ApplicationService.robot_reports`가 표준 라이브러리 기반 저장 보고서
  정규화/보관을 소유한다. ProductWorkflow는 이를 위임한다.
- 인증된 `GET/POST /v1/product/robot/report`. POST는 기존 CSRF 검사,
  256KiB JSON 한도, 고정 report 필드만 허용. 파일 경로/셸/실행 인자 없음.
- `robot-health-1.0` 또는 이를 포함한 `robot-connection-1.0`을 받는다.
  UTC/boot ID/전압/boolean/두 바퀴 속도/배포 ID 검증. 원본 미지 필드·raw
  출력/경로는 보관·반환하지 않고 원본 JSON digest와 선택된 측정값만 보관.
- 추정 잔량은 전압에서 다시 계산(공개 공식 기준10.5→0/12.3→100),
  20% 충전 안내와11.1V 보호 근처 안내를 분리. 실제 용량/남은시간 아님.
- React의 접힌 `Robot status · Saved diagnostics`에서 JSON 가져오기/
  저장 보고서 새로고침 제공. 초기 mount에 로봇/새 endpoint 호출 없음.
  과거 전압/측정시각/age/boot/release/idle-at-observation 표시.
- **항상 NOT_CONNECTED, current UNKNOWN, source_verified=false,
  motion_authorized=false, demo_ready=false.** 보고서는 업로드된 미검증 증거.
  건강한 보고서나 최신 타임스탬프도 live 상태나 실행권한으로 승격하지 않음.
- 메모리 내 현재 App session에만 저장. 앱 재기동하면 비워진다.
  영구 보고서 카탈로그/실시간 worker/실물 명령은 후속 범위.

## 검증 결과

- 새 정규화/시간/오류/한도/보호 구분/권한 검사12 PASS.
- 기존 로봇 검사와 합쳐 Windows40 PASS. 최초 샌드박스 실행은 기존
  TemporaryDirectory ACL로2ERROR, 동일 suite 허용 실행에서40 PASS.
- R5 HTTP12 PASS(기존10+신규2): auth/CSRF, path 거부, 보고서 import/get,
  sim lease와operation이 생기지 않음. 기존 생성/입력/설정 회귀 포함.
- Web23 PASS, TypeScript와production build PASS. 최초 Vite는 child spawn
  EPERM으로 미시작, 기존도구의 허용 실행으로 통과. 새 패키지 설치 없음.
- Chrome headless 모의 API: desktop1366×768/mobile390×844 및 수평overflow0.
  이전 Build accepted→receipt→matching snapshot, stage 교체 Run 차단 회귀 PASS.
  `artifacts/overnight-report-browser/robot-report-{desktop,mobile}.png` 및
  accepted.png/confirmed.png. 모바일 PNG를 직접 열어 확인.
- WSL 통합40+runtime6+stationary17 = **Python63 PASS**, C++guard1314와
  battery615 checks PASS. 최초 run-BENbh3b8은 App import의 Pillow 의존성으로
  실패. 새 순수 검사의 import를 모듈 단위로 분리, HTTP suite에서는 실제
  package composition을 계속 검사. 최종 `run-WYRUqI2E/checks.log` PASS.
- 오프라인 소스 묶음 `artifacts/robot-preparation/20260926T171000Z-d30304cd`.
  이는 robot package만이며 웹 앱 변경을 포함한 전체 제품 release가 아니다.

## 미완료 / 다음

D4 전체가 아니라 **저장 보고서 review만 완료**. 실시간 RobotSession worker,
실물 준비/취소/실행 API, 영구 receipt, scan/TF, map 보정, 공정 경로 비교,
실제 Isaac 새 기능 검증과 E2E 최종 데모는 아직 완료되지 않았다.
과거 정지 안정122ms<200ms FAIL 유지. 밤사이 실물 검증 금지.
다음 작업은 `TWINPULSE_OVERNIGHT_PREP_2026-09-27.md`의2번부터.
