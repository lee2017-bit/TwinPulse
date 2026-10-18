# 실제 로컬 App 통합 리허설 — 2026-09-27 07:20 KST

## 결과와 범위

**React production build → 실제 LocalApiServer → ApplicationService의 오프라인
review 흐름 PASS.** 이전의 HTTP mock 브라우저 검사와 다르게 API 응답을 만들어
대신하지 않았다. 그러나 입력 health/scan/geometry/경로는 **모두 합성 fixture**이며,
실물·Isaac·유료 provider는 NOT_RUN이다. 전체 TwinPulse 최종 데모 PASS가 아니다.

- `scripts/rehearse_offline_app.py`: 새로운 출력/격리 state에만 쓰고 loopback port0,
  메모리 전용 credential stub, ephemeral bootstrap, existing production dist로 실제
  서버를 시작한다. 세션 비밀은 child env로만 전달하며 결과·로그에 쓰지 않는다.
  사용 중인 App/프로젝트/설정/키/로봇을 탐색하거나 사용하지 않는다.
- `e2e/offline-app-real.mjs`: 자신이 연 headless Chrome에서 실제 인증/쿠키/CSRF와
  UI 작업을 수행한다. 외부 URL과 engine command 요청은 차단하고 시도 횟수가0인지
  확인. 실제 API 응답을 mock/fulfill하지 않는다. 로그에는 URL/인증값이 들어갈 수
  있는 Playwright call stack 대신 실패 단계와 error_type만 기록한다.
- `scripts/rehearse_offline_app.ps1` / `Rehearse-Offline.cmd`: 기존 전체 `-SkipIsaac`
  회귀/production build 후 이 E2E를 실행하는 한 명령. 실패 시 다음 단계 중단,
  종료 코드 유지, 기존 결과 덮어쓰지 않음. 설치/시스템 설정 변경 없음.
- README의 “route comparison 미구현”이라는 오래된 문장을 제한된 오프라인 구현과
  미완료 live/자동최적화/실물 통합으로 구분해 바로잡았다.

## 검증한 8단계

1. 실제 bootstrap→session, 주소 fragment 제거.
2. 합성11.21V report를 historical로 표시, 임의99% 입력을39.4%로 재계산.
   NOT_CONNECTED/source_verified=false/motion_authorized=false/demo_ready=false 유지.
3. 합성 scan bundle/등록 simulation profile, 동일 조건 두 경로8m/4.828m 비교.
4. 더 짧은 직선4m라도 occupied cell 통과는 비교 거부, winner 없음.
5. 물체 XY +0.1/+0.1 제안→명시 검토 checkbox 전 적용 불가→scratch 적용,
   기존 map/mission/비교 결과 무효화, active_project_changed=false.
6. 브라우저 다운로드로 실제 inspection export 저장, 실행/복원 권한false,
   서버 snapshot scene revision과 export 일치.
7. undo로 원래 geometry 복구하되 새 revision, map/mission/기존 승인 복구 안 함.
8. reload 후 기존 쿠키/session 복구·scratch 상태 유지,390px 화면 가로넘침 없음,
   페이지 오류0, 외부 요청0, engine command0, product operations/artifacts없음,
   engine연결/lease없음. 초기 격리 프로젝트 바이트 불변.

## 증거

- 최종 one-command 결과:
  `artifacts/offline-rehearsal-20260927-071857-3bdc2597/`
  - `regression.log`: **Python246/Web34/build PASS**.
  - `browser/result.json`, `browser/browser-result.json`: 실제 local E2E8단계 PASS.
  - `browser/desktop-comparison.png`, `browser/mobile-review.png`, `browser/browser-export.json`.
- 회귀 manifest: `artifacts/runs/20260927-071857/manifest.json`.
- 앞선 실제 backend 리허설 `artifacts/offline-app-real-20260927-0718/`도 PASS,
  모바일 screenshot 직접 시각검수. 이후 wrapper 통합 실행071642/071820도 PASS.
- 새 시연 입력은 simulation profile `agv_compact_2wd_caster_v2`. 실제 Burger의
  치수/지도/배터리로 주장하지 않는다. 단독 script는 이미 있는 출력 폴더를 거부한다.

## 발견한 실행기 문제와 보존 기록

1. 최초 실행 `offline-app-real-20260927-0715`: 테스트 실행기의
   ProductWorkflow generation_settings_getter 누락으로 시작 실패. 추가 후 재실행.
   로봇/서버/브라우저 시작 이전의 실행기 구성 오류다.
2. `offline-app-real-20260927-0716`: 브라우저8단계 PASS지만 Python 실행기가 앱의
   초기 empty project 생성도 변경으로 판정해 overall FAIL. ApplicationService의
   load_or_import_legacy가 생성하는 빈 record를 확인하고 **초기화 직후와 검토 종료
   후의 바이트 동일성**을 비교하도록 수정. 기존 파일/FAIL result 그대로 보존.
3. `offline-rehearsal-20260927-071553-47270029`: Windows PowerShell의 Stop 정책이
   unittest의 정상 stderr 진행 출력을 NativeCommandError로 처리해 wrapper 중단.
   native child 출력 수집 구간만 Continue, 실제 종료 코드는 별도 검사하여 실패 시
   중단하도록 수정. ErrorRecord는 메시지만 출력해 정상 빈 줄이 RemoteException으로
   표시되지 않도록 정리했다. 성공 기준/단위 테스트는 변경하지 않았다.

이번 milestone은 제품 core/실물 기준을 변경하지 않았다. 기존 HTTP 일시 중단의
근본 원인을 해결했다거나 실제 정지122ms FAIL을 해소했다고 주장하지 않는다.

## 다음

[아침 운영 안내](../planning/TWINPULSE_MORNING_HANDOFF_2026-09-27.md) 참고.
다음 오프라인 의존성은 보정된 scratch scene에서 지도 재생성·임무 재검토 경계를
명시적으로 준비하는 것. 현재 apply/undo 뒤 map/mission이 없어 비교가 막히는 것은
정상이며 옛 지도를 그대로 재사용하지 않는다. derived-draft의 영구 저장/active Twin
promotion 및 실제 Isaac·실물 통합은 별도 미완료. 오전10시까지 로봇접속 금지 유지.
