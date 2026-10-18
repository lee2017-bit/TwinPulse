# 야간 오프라인 준비 — 2026-09-27

사용자 승인: 약8시간 수면 중 데모 선행 구현·시험을 최대한 진행.
마감: 2026-09-27 10:00 KST. 전체 실물 데모 완료 보장이 아니다.

**종료 확인: 10:13 KST.** 마감 이후 새 구현/로봇접속 없이 기존 증거와 인수인계만
확인했다. `twinpulse`를 PAUSED로 변경하고 저장상태를 재확인했다. 최종 오프라인
Python271/Web37/build·실local9단계 PASS; 아래 실물 acceptance는 여전히 미완료.
자동작업을 재개하지 않고 사용자 기상·충전/전원 상태·점검 승인 답변을 기다린다.

## 실행 경계

- 로봇 OFF/충전 사용자 보고. SSH/serial/배포/센서/모터/전원 조작 전부 금지.
- 사용자에게 잠들기 전 리튬 배터리 무인 충전 중단을 안내했다. 실제 중단 여부는 미확인.
- 기존 로컬 도구로만 구현/테스트. 유료 호출·클라우드·시스템 설치/설정·push 없음.
- 기존 dirty 작업/실패기록/판정기준 보존. 실물 gate를 fake 성공으로 면제하지 않는다.
- 예약 ID `twinpulse`: 이 대화에서 시간 간격 후속 작업, 최대8회. PC/app 가동 필요.
- 권한 부족 시 우회 금지. 완료하지 않은 구현은 그대로 미완료로 기록한다.

## 실행 순서와 인수인계

1. D4 첫 부분: ApplicationService가 소유한 저장 health report review → 인증 API →
   영어 React Robot Status. live transport/주행 권한과 분리. **02:10 KST tested
   scope 완료**, [검증](../verification/robot-report-app-20260927.md). Windows40,
   HTTP12, Web23/build/browser, WSL63+C++회귀 PASS. API가 파일 import만 하며
   live RobotSession은 아직 없다. 다음은2번; 이미 완료한 부분 반복하지 않는다.
2. D3/D5: 기존 센서 검증 자료·site contracts를 재사용하여 저장 scan 입력/시간·frame·
   좌표변환/기록 재생·undo를 구현·검증. 합성 입력은 표시하고 실사진/실측을 만들지 않는다.
   **03:14 KST 첫 부분 완료:** 저장 stationary scan 계약/순수2D 투영/CLI, core68에 포함된
   scan15+CLI3 검사 및 통합 Python190/Web23/build PASS. [검증](../verification/scan-recording-offline-20260927.md).
   다음은 저장 scan App review/대응점 명시 XY proposal·parent guard·undo·map/mission
   무효화. 자동정합/실제ROS decoder/deskew/App·Isaac overlay는 아직 없음. synthetic
   fixture만 있으며 submitted TF/stationarity는 검증된 사실이 아님. 이미 끝난 계약을
   반복 구현하지 않는다. 현재 D3/D5 PARTIAL, 실제 scan/좌표/정지 gate 그대로 유지.
   **04:14 KST 두 번째 core 부분 완료:** 수동 대응점 XY proposal/apply/undo 및 전체
   parent guard·map/mission/review 무효화. correction22/core90, 최종 Python212/Web23/build PASS.
   [검증/첫 일시HTTP 실패 포함](../verification/scan-correction-offline-20260927.md).
   다음은 App saved-scan review/derived draft persistence. 기존 SiteDraftRecord의
   tool-plan expansion 검증을 건너뛰어 site만 교체하지 않는다. 오프라인 review를
   격리하거나 명시적 파생 draft 계약을 먼저 구현. live/Isaac 적용·자동정합 없음.
   **05:19 KST 격리 App 검토 완료(tested scope):** session-local workspace/서버소유
   receipt·인증 API·React overlay/explicit pairs/review/apply/undo/export. Python223,
   Web29/build, 모의HTTP desktop/mobile browser PASS. [검증/리허설](../verification/scan-review-app-20260927.md).
   활성 SiteDraftRecord/project/broker/Isaac 미변경; 영구 derived draft/promotion 미완료.
   다음은3번 D6 기하 비교와 리허설. 실HTTP browser 통합은 별도남음(HTTP unit은 PASS).
3. D6: 같은 map/profile/start/goal/제한 조건의 경로 비교와 결과 계약/화면/재현 시험.
   경로 길이만 개선해 물리 성공/속도/충돌 감소로 주장하지 않는다.
   **06:25 KST 기하 비교 완료(tested scope):** 연속선분·팽창격자 검사/동일조건 digest,
   registry profile·stale guard 및 격리 App/API/React 수동경로 비교. 최종 Python246,
   Web34/build/합성 모의HTTP desktop/mobile PASS. 최초HTTP WinError10053 기록 보존,
   단독/전체 재검사 PASS. [검증·합성파일](../verification/route-comparison-offline-20260927.md).
   자동최적화/실제backend browser E2E/실제Isaac·물리 성능 비교는 아직 아님.
   다음 우선순위는 실제backend browser E2E와 아침 통합 운영가이드. 보정 후 map/mission
   rebuild 및 derived-draft promotion은 별도 의존성; old approvals를 복원하지 않는다.
4. D2 physical runner 연결 준비는 오프라인만. consumed marker 재사용·무단 재주행 금지.
5. 한 명령 검증과 아침 실행 안내, 전체 회귀, 가능한 기존 Isaac 리허설.
   사용자 소유 runtime을 종료하지 않는다. 동시 실행/자원 문제가 있으면 미실행 기록.
   **07:20 KST 한 명령/아침 안내 완료(tested scope):** `Rehearse-Offline.cmd`가 전체
   Python246/Web34/build→실제 local backend/browser 합성8단계 PASS. mock API가 아닌
   production React/인증/CSRF/서비스 결과/실제export/reload/mobile 검증. 격리상태만 사용,
   새로 시작한 서버/브라우저만 종료. [증거](../verification/offline-app-real-rehearsal-20260927.md),
   [아침 안내](TWINPULSE_MORNING_HANDOFF_2026-09-27.md). 기존 실물FAIL/소비표식 유지.
   다음은 보정 scratch scene의 지도재생성·명시적 임무재검토 경계(오프라인만),
   active project 도구계획 검증은 건너뛰지 않는다. 실제Isaac/실물 PASS는 여전히 아님.
   **08:19 KST 보정 후 보수적 overlay 연결 완료(tested scope):** 원본grid에 보정전후
   static box occupied만 추가(free 생성0), 동일 endpoints/newscene/newmap 임무 제안·
   별도검토 후 새 조건 비교, undo 시모두무효화. full rebuild/SLAM/실측 아님.
   Python259/Web37/build·실local browser9단계 PASS. [검증](../verification/map-overlay-offline-20260927.md).
   다음 09시에는 통합 증거/아침 인수인계 일관성과 남은 의존성을 점검한다.
   activeTwin 영구파생draft·자동최적화·실물통합은 여전히 미완료.10시마감 유지.
   **09:19 KST 인수인계 통합 완료(tested scope):** 같은 새 실행폴더의 manifest/
   App/browser9단계·export·화면5개를 검사한 정적 summary HTML/JSON 추가. 오류·누락을
   FAIL로 보존, 이전PASS 검색 없음. 최초sandbox 임시폴더권한 FAIL 기록 보존 후 정식
   권한승인으로 동일검사 Python271/Web37/build/실local E2E PASS. PASS/FAIL summary
   desktop/mobile 시각·외부요청0 확인. [검증](../verification/overnight-handoff-audit-20260927.md).
   아침 안내에 재실행 없이 여는 증거페이지와 실제남은순서 연결. 로봇/Isaac0,122ms FAIL
   유지. **다음 heartbeat가10시 이후이면 새 구현 없이 최종보고하고 예약 중지.**

## 아침 실물 acceptance (밤사이 실행 금지)

전원재개 사용자 확인 → 현재 상태/전압 → Pi 배포/ARM64 → stationary →
실행 직전 현장 관찰 승인 → 제한 정지시험 → LiDAR/TF/scan → 미션 통합검증.
정지 안정122ms FAIL, 실제 LiDAR 정지·좌표/scan 미검증은 여전히 blocker다.
충전 완료나 모든 unit test 성공만으로 물리 demo_ready를 true로 만들지 않는다.
