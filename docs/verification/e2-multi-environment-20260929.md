# E2j 저장 장면의 환경별 동일 제품 경로 — 2026-09-29

판정: **검증한 세 가지 로컬 Build 경로 PASS, E2 전체 PARTIAL**. 기존 `room-recipe-1.0` 저장/import와 App 검토→명시 승인→단일 `build_site_scene`→bridge→실제 Isaac을 재사용했다. 세 리허설은 각각 격리된 프로젝트 상태/새 Isaac 프로세스로 실행했으며, 실행 중 프로젝트 간 전환 검증은 아니다.

| 격리 결과 | 입력의 성격 | 결과 |
|---|---|---|
| [사용자 방 보존 사진](../../artifacts/runs/20260929-e2j-preserved-bedroom-browser-r1/result.json) | 기존 보존 사진과 저장 recipe. 사진 정확도·치수 실측 아님 | PASS |
| [다른 치수의 방](../../artifacts/runs/20260929-e2j-other-room-browser-r1/result.json) | 합성 사진 + 사용자 입력 3.2×4.4 m. 사진 자동 해석 아님 | PASS |
| [합성 창고](../../artifacts/runs/20260929-e2j-warehouse-browser-r1/result.json) | 합성 placeholder + 결정적 8×6 m 바닥/두 rack 행. 사진 자동 해석·실제 창고 아님 | PASS |

창고 fixture는 기존 정적 rack 도구 세 개(바닥 1, rack 행 2)만 v2 site plan에 넣고 각 호출의 근거를 `inferred`/synthetic으로 표기했다. 로봇/임무 호출은 제외한다. 브라우저는 창고의 rack 검토와 robot/mission 부재를 확인했고 Isaac은 rack prim, 별도 visual-only Burger(4 mesh, physics variant `none`)를 확인했다. 공통 확인: Build 1회·Run 0, 저장 recipe 및 imported draft 불변, 외부/모델/로봇 요청 0, 저장 USD와 기존 무관 prim 유지, 물리 timeline 정지. `tests.integration.test_a2_room_recipe` 17 tests PASS. 실패 기준 완화 없음.

이 세 PASS는 서로 다른 **종류의 장면이 같은 코드 경로에서 열리고 Build된다**는 회귀 증거다. 사용자 사진만으로 일반 방/창고의 가구와 배치를 추론한 증거도, 같은 실행 세션에서 여러 프로젝트를 전환한 증거도 아니다. 실제 방 치수·라이다/TF 정합, 실제 창고 사진, 회사 PC GUI 가독성, Isaac Physics/자율 임무, 실물 로봇 주행·정지 모두 미검증이다. 기존 실물 정지 FAIL과 실행 잠금은 유지한다. 다음 E2 작업은 저장/가짜 provider 편집 문맥을 E1 비파괴 변경 계약에 결속하는 것이다.
