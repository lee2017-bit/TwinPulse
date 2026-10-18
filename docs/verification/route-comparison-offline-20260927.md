# D6 — 동일 조건 기하 경로 비교 (2026-09-27 06:25 KST)

## 판정

**오프라인 core/App/API/화면 tested scope PASS, D6 전체 PARTIAL.**
로봇 접속·배포·센서·모터·전원·실물시험·Isaac·유료 요청 모두 NOT_RUN.
이 결과는 최적화기 구현, 실제 경로 추종, 시간 단축 또는 충돌 감소의 증거가 아니다.
기존 실제 정지 안정 **122ms < 200ms FAIL**을 바꾸거나 면제하지 않는다.

## 구현과 조건

- `packages/twinpulse_core/src/twinpulse_core/route_comparison.py`: 순수 2D polyline
  비교. same scene/map/robot/profile digest/mission/start/goal, footprint, clearance,
  cell work budget, policy를 canonical digest로 고정한다. 다른 digest·누락 map/mission·
  비평면/waypoint 임무·다른 endpoint·잘못된 수치/중복 연속점을 거부한다.
- 각 경로는 2–128개 좌표, 각각 ±100m 이내. clearance 0–1m, App은 고정0.05m.
  chassis 반대각선·구동바퀴 외곽·지지바퀴 범위를 모두 감싸는 반경을 사용한다.
  연속 선분과 팽창된 occupied/unknown cell AABB를 교차 검사한다. 점 샘플링이 아니다.
  경계 접촉/지도밖/미관측은 차단, 경로당200,000 cell 검사 예산 초과는
  `EVALUATION_LIMIT`이며 통과로 취급하지 않는다. 보수적 AABB로 코너 경로를 과도하게
  거부할 수 있다. 입력 지도 자체의 진실성은 검증하지 않는다.
- 두 경로 모두 `CLEAR_IN_SUPPLIED_GRID`일 때만 길이 winner/reduction을 기록한다.
  내부 회전각은 기하 통계일 뿐, 시작/목표 yaw 만족·곡률/가감속·미끄럼·동역학·
  센서 오차·동적 장애물·추종 가능성·시간을 평가하지 않는다. 시간/충돌 개선값은 null,
  source_verified/execution_authorized/demo_ready는 항상 false.
- `ScanReview`에 registry profile 해석·server-owned 결과·workspace nonce guard와
  `/v1/product/scan-review/compare` 인증/CSRF POST 추가. 임의 client profile을 받아
  실행하지 않는다. 조건은 snapshot에서 제공하고 client가 정확히 되돌려보낸다.
  import/propose/apply/undo는 이전 비교를 삭제한다. apply/undo 뒤 map/mission이
  없으므로 새 지도와 임무가 준비되기 전 비교 불가. export는 검토 기록일 뿐이다.
- React `Same-condition route comparison`: 수동 XY JSON 두 경로, 동일 조건·입력 좌표·
  길이·상태·감소율 표시. 수정 중 이전 결과를 숨기고 export가 기존 결과라는 안내.
  standalone scratch이며 active project, broker, motion lease에는 영향 없다.

## 실제 수행 검증

- 새 core17(전체107): 알려진 길이, 선분 중간의 얇은 장애물, footprint 여유/경계접촉,
  unknown/outside, 동일 조건/endpoint, profile binding, budget fail-closed, 결정성/불변성.
- ScanReview 신규5(전체14): JSON shape·stale·registry 거부, 결과 내보내기/사본격리,
  보정/되돌리기/재import 무효화, 짧아도 막힌 경로 winner 없음.
- 실제 로컬 HTTP 신규1(R5전체15): session/CSRF/shape, 비교·stale 재요청 거부,
  project/lease/operations 영향 없음. 전체 R5/S2/S3 묶음42 PASS.
- Web 신규5(전체34), TypeScript 및 production build PASS.
- 최종 전체회귀: **Python246/Web34/build PASS**, `artifacts/runs/20260927-062210/manifest.json`.
  전체 native 출력: `artifacts/route-comparison-app-regression-retry-20260927.log`.
- 첫 회귀 `artifacts/runs/20260927-062056`는 신규 HTTP 시험의 미인증 POST에서
  Windows loopback `WinError10053`으로 FAIL. 원인 미확정. 단독 동일 검사 및
  변경 없는 전체 재검사 PASS. 실패 로그 `artifacts/route-comparison-app-regression-20260927.log`
  보존; 기존에도 발생한 연결중단을 해결했다고 주장하지 않는다.
- `e2e/scan-review-browser.mjs ... --routes`: 합성 snapshot을 HTTP mock한 실제 headless
  Chrome, 1366×900 / 390×844 PASS. import→8.000m/4.828m 비교→입력 변경 시 옛 결과 숨김→
  4.000m 직선 장애물 거부, 오버플로/페이지 오류 없음. 모바일 PNG 시각 확인.
  기존 correction 브라우저 회귀도 PASS. **브라우저→실제 backend 통합 E2E는 아직 아님**.

## 아침 오프라인 리허설 파일과 순서

`artifacts/route-comparison-rehearsal-20260927/`:

1. App의 **Scan review · Offline scratch draft**에서 `bundle.json` 가져오기.
   명시적 SYNTHETIC 현장/레이저와 `agv_compact_2wd_caster_v2` profile이다.
   **실제 TurtleBot3 Burger 치수나 실측 환경이 아니다.**
2. `baseline-points.json` 내용을 Baseline, `candidate-points.json` 내용을 Candidate에
   붙여넣고 **Compare supplied routes**. 같은 시작[-2,0]/목표[2,0], 같은 지도/프로파일.
3. 예상 길이8.000m/4.828m, 길이만39.64% 차이. 수동 작성 합성 경로이며 자동 최적화 결과
   또는 실물 개선 수치로 발표하면 안 된다.
4. Candidate를 `[[-2,0],[2,0]]`로 바꾸면 더 짧아도 occupied cell 때문에 비교 거부.
5. 검토기록 export. `comparison.json`/`exported.json`은 생성기에서 저장한 합성 증거.
   UI 직접 입력은 route provenance=`manual`, scan provenance는 계속 `synthetic`이다.

새 폴더에 재생성(기존 출력 덮어쓰기 거부):

```powershell
.\.venv\Scripts\python.exe scripts/prepare_route_comparison_rehearsal.py artifacts/route-rehearsal-new
```

기존 빌드로 화면 검증(자신이 만든 preview/browser만 종료):

```powershell
# apps/twinpulse-web에서
node e2e/scan-review-browser.mjs ../../artifacts/route-comparison-rehearsal-20260927 --routes
```

## 다음 의존성 / 아직 미완료

- 실제 backend까지 묶은 브라우저 리허설과 한 번에 따라갈 아침 운영 안내.
- 보정 scene의 map rebuild·mission rebind 및 명시적 derived-draft persistence/promotion.
  기존 tool-plan deterministic expansion과 다르게 site만 덮어쓰지 않는다.
- 자동 경로 생성/최적화, actual Isaac 양 경로 실행·동일 조건 시간/충돌 비교.
- 실제 Burger profile·실측 좌표·LiDAR 정지/scan·guard 배포/ARM64/ROS 및 실물 정지 acceptance.
  사용자 기상/전원재개 확인, 새 현장 주시/명시 승인 이전에는 실행하지 않는다.
