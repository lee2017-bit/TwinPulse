# 방 Twin → 합성 임무 → 명령/관측 기록 (N4 부분)

2026-09-28 01:58 KST. 승인된 야간 PC 작업. 로봇 OFF, 새 SSH/serial/실센서/
배포/모터/Isaac Run/유료 서비스 접근 없음.

## 실제 제품 경로

기존 `BedroomTwin`의 저장 방·모델 검토 → 인증/CSRF 적용된
`POST /v1/product/bedroom/rehearse` → `BedroomReview` 원본 재검증 →
`bedroom_rehearsal` → 순수 `local_navigation` 판단 → 화면 XY 경로/JSON 다운로드.
엔진이나 실물 연결 없이 실행되며 기존 active project/사진/asset을 변경하지 않는다.
서버는 route/blocked/stale_scan 세 가지 고정 시나리오만 허용한다. 클라이언트가
속도·footprint·센서 표본·경로·물리 모드·파일 경로를 주입할 수 없다.

실제 제공 사진의 기존 **근사** scene revision과 manifest를 재사용한다. 동일한
12개 객체 중 바닥 경계 및 11개 가구/벽 box에서 72방향 거리값을 합성한다.
높이를 무시한 보수적 2D envelope이며 바닥 경계는 simulation limit이다.
보이지 않는 근처 벽을 새로 실측한 것이 아니며 저장 native scan과 정합하지 않는다.

## 판단과 제한

- 임무 시작 한 번 → 50ms 합성 시간 간격으로 목표 각도/제자리 회전/전진/도착을
  결정한다. 각 이동마다 승인하지 않는다. route는 현재 예시 두 waypoint에 고정된다.
- 검토한 방의 표시용 Burger pose `(0,-.65,90deg)`를 **합성 시작 자세**로 사용한다.
  이는 실제 로봇 방향 증명이 아니다. 로봇 dynamics 또는 실제 Isaac 주행도 아니다.
- `LocalScan`은 full-circle/base_link/oldest sample/transform basis/source kind를 요구한다.
  누락·0·NaN·Inf·불완전 표본·과거/미래 시각·saved recording·photo hypothesis는 거절한다.
  live_sensor/측정 extrinsic 표식은 향후 trusted adapter 계약이지 측정 사실 인증이 아니다.
- 고정 저속 `.03m/s`, `.2rad/s` 범위. 원형 body radius `.18m` + margin `.05m` +
  `abs(v)*1.2s`의 전체 swept-envelope를 사용한다. 1.2s는 기존400ms 만료+
  800ms 관측 예산에서 얻은 설계값이며 실제 정지거리 보장이 아니다.
  반경은 리허설 가정이며 캘리브레이션된 Burger 외형 스펙이라고 하지 않는다.
- 전방뿐 아니라 전후좌우 전체 최소 여유를 본다. 방향별 capsule보다 보수적이며
  가까운 뒤쪽 물체에도 전진을 거절할 수 있다. 센서 사각/유리/높이/미끄럼/
  빔 사이 물체에 대한 보장은 없다. 실제 로봇의 안전 인증이나 자율주행 허가가 아니다.
- 장애물·불확실성 발견은 출력0 및 terminal stop이다. 현재 자동 우회/재계획 없음.
  접촉을 시도하거나 충돌 감점을 학습시키지 않는다. collision/contact 수치도 꾸며내지 않는다.
- 새 `RehearsalAdapter.apply`의 manual/mission 제안은 같은 guard를 거친다.
  **기존 실물 `teleop_ros` 및 기존 PC 수동 패널과의 공용화는 아직 미완료**다.
  이번 테스트의 manual source는 이 새 adapter에 직접 주입한 테스트다.

## 기록

모든 step의 제안 속도, 허용/거절 이유, 최종 출력, 전후 합성 pose, synthetic clock,
source/scene/manifest revision을 반환하며 JSON 저장 버튼으로 내보낸다. 거절된 원래
제안도 삭제하지 않는다. pose/거리/시간은 명령의 운동학 적분이며 실제 계측이 아니다.
PC 서버의 자동 영구 저장/새로고침 복원은 아직 없고 사용자 다운로드가 제공된다.
다른 시나리오는 목표가 다르므로 이 세 결과를 동일조건 성능 비교로 사용하지 않는다.

## 검증 결과

- core 신규8, 새 방 리허설 integration4, 기존 방 HTTP에서 auth/CSRF/shape/physical
  mode 거절 검사 추가, Web2 추가 PASS. 전체회귀는 부분집합을 중복 합산하지 않는다.
- `artifacts/bedroom-mission-regression-20260928-r1/manifest.json` PASS:
  core146 / bedroom19 / Web97 / TypeScript·production build 및 기존 전체회귀 PASS.
- `artifacts/bedroom-mission-browser-20260928-r1/result.json` 실제 Chrome/App/API
  5단계 PASS. 시작 요청 총3회, 외부/금지된 로봇·엔진 명령0, pageerror0,
  원본 project 불변, source/dist SHA256 최종 불일치0. 데스크톱/모바일 캡처 직접 확인.
- 정상: ARRIVED, **합성**21.8s / 0.4215m / 437판단. 회전·전진 모두 포함.
- 장애물: OBSTACLE_IN_SWEPT_ENVELOPE, **합성**26.65s / 0.5655m / 534판단,
  마지막 출력0·pose 불변. 충돌 계측 성공이나 물리 정지 증명이 아니다.
- 센서 지연: SCAN_STALE, **합성**0.25s / 0.0075m / 6판단,
  마지막 출력0·pose 불변.
- 내보낸 JSON revision이 API 결과와 일치한다. route/blocked/stale_scan JSON과
  캡처는 위 browser 증거 폴더에 보존했다.
- 최초 core 단독 실행은 테스트의 repo src 경로 누락으로 import 실패했다.
  기존 테스트와 동일한 src 로딩을 추가한 뒤 신규8 및 전체146 PASS.

## 남은 작업

N4 전체 완료 아님: 실제 ROS local scan 수집/검증된 extrinsic/pose 신선도/현재
qualification·부팅 binding/실물 공통 adapter/비동기 watchdog/자동 재계획 미완료.
기존 수동 및 최종 OFF·정지 판정은 변경하지 않았고 실물 gate를 열지 않았다.

다음 의존성이 준비된 작업은 이 source-bound 합성 기록의 **기존 3D Twin 표시
재생 연결**이다. Physics=none인 preview를 물리 simulation으로 승격하지 않아야 한다.
실측 로그 재생·동일조건 비교(N5), N2 통합 readiness, N3 로그 내구성/odom/scan,
N4 실물 adapter 및 N6 통합 실물 인수는 별도로 남는다.
