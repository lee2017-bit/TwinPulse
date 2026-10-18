# N5 부분 — 합성 기록 시점 → 실제 Isaac 표시

2026-09-28 02:32 KST. 승인된 야간 오프라인 작업. 로봇 접속/배포/실센서/모터0,
timeline/PhysX Run0. **연속 애니메이션이 아니라 선택 시점 seek**이며 실물 기록 재생도 아니다.

## 제품 경로와 경계

- 기존 `BedroomTwin` 방 검토 → 합성 임무 계산 → 0..명령 수 슬라이더 →
  `선택 기록을 Isaac에 표시` → 인증/CSRF `/bedroom/replay` → 기존 broker의
  `build_site_scene` → production BridgeClient → actual Isaac.
- 0은 출발, N은 N번째 명령 적용 후 합성 pose. UI의 시간은 해당 명령의 적용 전 시각이다.
  slider 변경만으로 명령하지 않는다. 기존 근사 장면 교체 확인/lease/명시적 버튼을 사용한다.
  임무 내부 이동 승인을 추가한 것이 아니라 기록 표시 기능이다.
- descriptor는 scenario/revision/integer frame만 받는다. 임의 pose, trace, 경로,
  속도, 외부 파일을 입력받지 않는다. manifest(사진/scene/모델)를 PC와 Isaac에서
  재검증하고 합성 계산을 다시 수행하여 기록 hash가 같은 경우만 해당 sample을 표시한다.
  코드/원본 변경으로 이전 hash가 달라지면 재생 거절. 임의 과거 JSON import 기능은 아니다.
- frame별 artifact ID를 분리해 서로 다른 seek 요청이 같은 등록물을 덮어쓰지 않는다.
  새 `bedroom_replay_v1` capability가 없는 엔진은 API/화면에서 거절한다.
- `/World/TwinPulse`의 기존 표시용 Burger translation/yaw 및 누적 경로 BasisCurves만
  작성한다. 원본 모델/사진/active project/외부 prim은 보존한다.
  Physics=none, motionAuthorized=false, SYNTHETIC_KINEMATIC_NOT_MEASURED 유지.
  일반 방 표시 또는 scene-only Build는 이전 trace를 지운다.
- 표시할 때마다 기존 장면 Build를 재사용하므로 대량/실시간 프레임 재생 방식은 아니다.
  새 프로젝트·실제 제어 profile·mission 권한을 만들지 않는다.

## 검증과 실패 이력

- `artifacts/bedroom-replay-regression-20260928-r2/manifest.json`: 전체 오프라인
  회귀 PASS, core146/bedroom21/Web99/TypeScript/production build. 부분 개수 중복 합산 금지.
- 추가 검사는 request auth/CSRF/exact shape/null/boolean frame/범위 밖 frame/
  다른 scenario/hash/임의 pose 거절, 구형 엔진 비활성, 명시 클릭 한 번당 한 요청이다.
- `artifacts/bedroom-replay-isaac-20260928-r3/result.json`: actual App/browser→
  broker/bridge→Isaac PASS. 정적 Build1 + seek3, browser7체크, 외부/pageerror0.
  0/218/437번의 실제 USD 위치와 yaw를 각각 합성 기록과 대조했다.
  최종 XY=(-0.1853614683,-0.3996860871), yaw=178.8084564deg (합성).
  path438점, source/build hash 불변, 원본 project/asset9파일/외부prim 보존,
  robot4mesh·물리 API 없음·Run 권한 없음, 변조 hash 거절 시 stage 불변.
  저장 USD 재열기 후 replay hash/position 일치. actual-Isaac/desktop/mobile 캡처 직접 확인.
- r1/r2 실제 실패는 그대로 보존. 기존 float rotateZ에 AddXformOp 기본 정밀도로
  재등록하여 USD type mismatch가 발생했다. r2 engine receipt로 원인 확정 후
  기존 순서/자료형을 유지하고 attribute 값만 갱신하여 r3 PASS.
- 최초 sandbox 단독 HTTP 시험은 임시폴더 권한 오류로 중단되었다. 검토를 거친
  같은 로컬 시험 권한으로 14개 PASS, 추가 HTTP 거절 검사는10개 및 최종 전체회귀 PASS.
  별도 bare Isaac python `pxr` import는 SimulationApp 초기화 전 불가였으며 실제
  runtime 검증으로 대체했다. 설치/환경설정 변경 없음.

## 미완료 및 다음

N5 전체 완료 아님. 같은 지도/출발/목표/profile의 대안 경로 비교, 측정 pose 기록,
odom/scan/명령 시간축, 연속 3D 재생, 자동 영구 로그/복원은 아직 남았다.
다음 의존성 준비 항목은 **기존 방 합성 임무의 동일조건 경로 비교와 제품 결과 연결**이다.
비교 시 기존 obstacle/stale 시나리오는 목표가 달라 성능 비교 대상으로 섞지 않는다.
N2 qualification-readiness 통합, N3 내구성/실측 로그, N4 실제 로봇 로컬 센서·공통
adapter·임무 watchdog/재계획, N6 통합 실물 인수는 별도 미완료다. 정지 기준과
과거 실패는 변경하지 않았다. 기존 사용자 App/Isaac 창은 자동 교체하지 않았다.
