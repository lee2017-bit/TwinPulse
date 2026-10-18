# N5 부분 — 동일조건 합성 경로 비교와 기존 Twin 연결

2026-09-28 02:58 KST. 야간 오프라인 승인 범위. 로봇/SSH/실센서/배포/모터0,
실물 정지 기준/과거 실패 불변, Isaac timeline/physics Run0.

## 구현한 제품 흐름

기존 방·모델 검토 → `동일조건 두 경로 비교` → 인증/CSRF exact-shape API
`/v1/product/bedroom/compare` → 현재 원본 재확인 → 고정 두 경로의 같은
`WaypointMission`/`RehearsalAdapter` 계산 → 지표·기록 선택·JSON 저장 →
기존 XY 표시 또는 별도의 명시적 Isaac 시점 표시로 연결했다.
클라이언트 임의 목표/속도/profile/trace를 받지 않으며 기록 선택 자체는 엔진 명령이 아니다.

- A: 기존 route 경유점 `(0,-.40)` 후 목표 `(-.20,-.40)`.
- B: 새 direct 경로로 같은 목표 `(-.20,-.40)`.
- 같은 사진/model manifest, scene, 출발 pose `(0,-.65,90deg)`, 목표 XY,
  15mm 도착 허용오차, .03m/s/.2rad/s, 50ms 적분, 90s 한도, 원형 보호 envelope,
  72방향 합성 ray/3m범위/근사 box·바닥경계 모델을 사용한다.
- conditions revision을 별도로 저장한다. 데이터 무결성·scene/manifest/start/goal
  불일치는 거절한다. 이는 현재 서버가 생성한 두 기록만을 위한 비교 함수이며,
  임의 외부 로그의 profile이나 사실을 인증하는 importer는 아니다.
- 최종 yaw는 목표 조건이 아니다. 같은 XY/허용오차의 도착이며 두 종료 방향은 다르다.
- 과거 route/blocked/stale_scan 기록 구조와 해시는 변경하지 않았다. direct를
  동일한 hash 검증/시점 표시 경로에 추가했다. 기존 실패 시나리오를 성능 비교에 섞지 않는다.

## 실제 계산값 — 모두 합성, 실물 성능 아님

| 항목 | A 경유점 | B 직행 |
|---|---:|---:|
| 도착 | ARRIVED | ARRIVED |
| 합성 시간 | 21.80s | 13.95s |
| 적분 거리 | 0.4215m | 0.3060m |
| 목표 XY 오차 | 0.014642m | 0.014348m |
| 최소 보호 여유 | 0.153600m | 0.153778m |
| 거리 검사 표본 | 436 | 279 |
| 여유5cm 이하 표본 | 0 | 0 |
| 이동 차단 | 0 | 0 |
| 충돌·접촉 | 미측정(null) | 미측정(null) |

B−A는 −7.85s/−0.1155m. 두 후보가 모두 도착한 경우에만 시간·거리 차이를
제공하며 미도착의 짧은 실행을 효율 우승으로 처리하지 않는다. 자동 최적화/경로
추천/배포는 없다. 보호 여유는 합성 ray의 보수적 내접 거리에서 반경·margin·속도별
시간예산을 뺀 값이다. 실제 장애물 거리나 충돌률이 아니다. near 표본은 시간 표본이며
서로 독립된 근접 사건 수가 아니다. 실제 충돌0이나 물리 성공을 꾸며내지 않는다.

## 검증 증거

- 비교 신규5·HTTP 경계 확장·Web2 추가. 관련19 단독 PASS.
- `artifacts/bedroom-comparison-regression-20260928-r2/manifest.json`: 전체회귀
  PASS, core146/bedroom26/Web101/tsc/build. 부분 집합 개수 중복 합산하지 않는다.
- `artifacts/bedroom-comparison-browser-20260928-r2/result.json`: actual 로컬
  App/Chrome6단계 PASS. 기존 합성3종 + 비교 요청1회, B 선택 추가 계산/엔진 명령0,
  비교·두 기록 JSON export revision 일치, 원본project 불변·외부/금지요청/pageerror0.
- `artifacts/bedroom-comparison-isaac-20260928-r2/result.json`: actual App→비교→
  B 선택→broker/productionbridge→Isaac8체크 PASS. 정적 Build1/seek3, B의
  0/140/280번 위치·yaw 일치, finalXY=(-.1898534891,-.4101442468),
  yaw132.9718323deg, trace281점. Physics=none/Run권한 없음, USD재열기/변조거절/
  원본asset9파일·project·외부prim 보존. 데스크톱/모바일/Isaac 캡처 확인.
- 위 browser/Isaac 최종 source+build SHA256 재대조 각각 불일치0.
- r1도 기능 PASS이나 화면 검토에서 '정지 거절'이 잘못 읽힐 수 있어 '이동 차단',
  'guard 여유'를 '보호 여유'로 수정하고 최종 source/build r2 전체 재검증했다.
  r1 원본 보존. 이번 실제 runtime 실패 없음.

## 남은 일

N5의 고정 합성 후보 비교만 검증했다. 자동 경로 탐색/재계획·실측 sensor TF/실측
pose·실제 로봇의 시간/거리/충돌 성능 검증은 아니다. 실제 실행 승인도 발생하지 않는다.
연속 3D 재생과 일반 기록 importer, 자동 영구 보관은 여전히 미완료다.

다음 우선 의존성은 **N3 수동 명령·관측 세션 로그의 종료 전 보존과 제품 조회**다.
현재 physical_controller는 메모리 journal을 종료 시 session.jsonl에 기록하므로
프로세스 중단 시 기록 손실 가능성이 있다. fake transport로 내구성과 조회를 검증하고,
실측 encoder를 바닥 pose로 승격하거나 없는 odom/scan을 채우지 않는다.
N2 readiness, N4 실제 local sensor/공통 adapter/임무 watchdog, N6 실물 인수도 남는다.
