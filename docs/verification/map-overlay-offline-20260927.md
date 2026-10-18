# 보정 후 보수적 지도·임무 검토 — 2026-09-27 08:19 KST

## 결과

**오프라인 scratch 보정→지도 제안/검토→같은 시작·목표의 새 비교→undo 연결 PASS.**
실물 접속/배포/센서/모터/전원/Isaac/유료 provider는 NOT_RUN. 기존 실물 정지
안정122ms<200ms FAIL을 유지한다. D5/D6 전체 완료나 자동 navigation은 아니다.

## 설계: 전체 지도 재생성이 아닌 장애물 추가 overlay

- pure `map_refresh.py`는 서버소유 AppliedCorrection을 원본 recording에서 다시
  계산해 동일 receipt인지 확인한다. 현재 scratch plan은 정확한 applied.after여야
  하며 원본 scene/map/profile/mission 바인딩도 검사한다.
- 기존 grid의 크기/해상도/origin을 유지하고, 수정 전·후의 모든 collision static
  box의 보수적 XY AABB에 닿는 셀을 occupied로 만든다. 각도에 따라 AABB가 넓어질
  수 있고, 이전 물체 위치도 지우지 않는다. **새 free cell을 만들지 않는다.**
- 기존 unknown은 장애물 영역에서 occupied로 바뀔 수 있지만 free로 승격하지 않는다.
  나머지 셀은 그대로다. inherited free 셀은 원본의 미검증 주장일 뿐 새 실측이 아니다.
  이동 후 비워진 영역의 사용 가능성을 알려면 별도 관측/검토가 필요하다.
- static upright box, 단일 axis-aligned floor만 지원. grid가 floor 밖이면 거부,
  동적/기울어진/미지원 collision shape는 거부. 셀 쓰기200,000회를 넘으면 부분
  결과 없이 거부. 높이에 따른 통과공간은 추정하지 않고 보수적으로 막는다.
- 새 scene/map/기존 map/보정 receipt/policy의 관계를 digest에 고정. 원본과 동일
  시작/목표를 새 scene/map에 연결한 **오프라인 임무 초안**을 함께 제안한다.
  `review_required=true`, `execution_authorized=false`, source_verified=false.
  profile 변화·옛 조건·변조된 제안/recording·잘못된 review는 거부한다.
- 적용 시 exact proposal digest로 재계산 검증. undo는 서버소유 overlay만 제거한
  후 기존 correction undo를 수행하고 새 scene revision을 낸다. map/mission/비교
  결과는 제거하며 예전 실행 승인이나 map을 복원하지 않는다.

## App/UI

- `ScanReview`가 map proposal/applied receipt를 소유하고 nonce를 갱신한다.
  인증/CSRF API `map-propose`/`map-apply`, 입력 exact shape, 반복·stale 요청 거부.
- React `Conservative map and mission review`: 정책, 추가 occupied 수, 남은 unknown,
  inherited free 수,0 freed와 같은 endpoints를 보여준다. 별도의 review checkbox를
  누른 뒤에만 **Use reviewed map in scratch draft** 가능. 옛 route 조건은 거부한다.
- 적용 후 **다시 입력·비교**해야 결과가 생긴다. 기존 active project/도구계획/broker/
  Isaac/runtime lease는 변경하지 않는다. export는 검토 기록이며 재시작 시 scratch
  상태 소실·실행/restore 불가라는 기존 제한을 유지한다.
- 일반적인 새 지도작성/SLAM/자동정합/자유공간검증 UI가 아니다. 현재 grid 셀 전체를
  그림으로 편집하는 기능은 없고, overlay 정책·카운트·장면·endpoints 검토 범위다.

## 직접 수행한 검증

- 새 core10 / core전체117 PASS: 새 바인딩/결정성, unknown·occupied를 free로
  바꾸지 않음, 보정 전후/미관측 box 포함, 회전 AABB, stale/변조/review 거부,
  missing map/mission·잘못된 profile·dynamic/floor bounds·예산 거부, undo 제거.
- App 신규2 / ScanReview전체16 PASS: preview/exact apply/새 조건 비교/undo,
  같은 nonce 재사용/반복적용 거부·import reset·원본 불변.
- 실제 HTTP 신규1 / R5전체17, 통합 R5/S2/S3묶음43 PASS: CSRF/shape/review/실행권한없음.
- React 신규3 / Web전체37 및 production build PASS: 검토 전 비활성, 정확한 digest,
  false claims 없는 문구, 적용 후 자동재적용 없음.
- **전체 Python259/Web37/build + 실제 local browser E2E9단계 PASS**:
  `artifacts/offline-rehearsal-20260927-081712-63d2df32/`의 regression.log 및 browser 결과.
  manifest: `artifacts/runs/20260927-081712/manifest.json`.
- 별도 실제 browser 재검증 `artifacts/map-overlay-real-20260927-0820/` PASS.
  `map-proposal-desktop.png`, `map-proposal-mobile.png`(직접 시각검수), 적용 후 화면,
  export/undo/reload. 외부요청0·페이지오류0·engine명령0, active project 바이트 불변.
  합성0.1m XY 보정 예제는12 occupied 추가/0 freed, 기존 비교8m/4.828m를 새 조건으로
  재계산했다. 수동 합성 길이39.64%는 자동최적화/실물 성능 향상 수치가 아니다.
- 이번 최초 전체 회귀 PASS, 과거 HTTP/실행기 실패 기록은 삭제하지 않았다.

## 사용 순서와 남은 것

현재 `Rehearse-Offline.cmd`에 이 연결 검증을 포함했다. [아침 안내](../planning/TWINPULSE_MORNING_HANDOFF_2026-09-27.md).
직접 UI에서는 등록 profile·map·mission이 있는 원본 bundle → 대응점 correction
검토/적용 → Preview conservative map overlay → endpoints/정책 검토 checkbox →
Use reviewed map → 새 경로 비교. missing/지원하지 않는 원본이면 명확히 거부된다.

현재 한 번의 서버소유 correction 후 overlay만 지원한다. 지속적인 scan 업데이트,
새 관측으로 old obstacle 해제, 영구 derived draft/active Twin promotion, 자동 경로
최적화·실제Isaac 양 경로 실행, 실제Burger profile/scan/TF/정지 qualification은 미완료.
아침 전 실물 시험은 하지 않으며 10시까지 남은 시간은 통합 증거/인수인계 점검에 우선 사용한다.
