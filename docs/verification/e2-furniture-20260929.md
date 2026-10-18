# E2b 로컬 가구 프리셋 — 2026-09-29

**제한된 로컬 경로 PASS, E2 전체 PARTIAL.** 사용자 사진+직접 입력한 방 치수로 새 프로젝트를 만들 때 최대 3개의 로컬 매개변수 가구를 종류·중심 XY·yaw로 고를 수 있다. 사진에서 가구·치수·배치를 판독하지 않는다. 방 원점은 바닥 중심, +Y는 닫힌 뒷벽 방향, 회전은 Z축 yaw다. 각 종류의 치수와 바닥 기준 피벗·부품 높이는 `furniture-blocks-1.0`에 고정된다. 7종(침대·옷장·책상·의자·소파·식탁·수납장)은 서로 다른 부품 형상이며 기존 rack/pallet 경로는 변경하지 않았다.

## 경계와 구현

- 새 가구는 `SiteToolPlan 2.1`의 로컬 `place_furniture`만 사용한다. 종전 `2.0` 기본값·직렬화·허용 도구와 v1 계획은 그대로다. 가구가 없는 새 방도 2.0으로 남는다. 임의 외부 자산 다운로드·provider 추론·로봇 명령은 없다.
- 원본 사진, user evidence, plan/version, InputRevision, source digest와 프로젝트별 recipe를 함께 저장하고 재열기 때 결정적으로 재확장한다. 프로젝트 생성은 원자 게시·같은 요청 ID/같은 입력 재시도 정책을 유지한다. 기존 프로젝트를 덮지 않는다.
- 가구 범위/유형/값/벽 밖·가구끼리의 보수적 XY 겹침을 거절한다. 각 부품은 `equipment` box 및 충돌 API를 가진다. 충돌 API 존재는 물리 충돌시험의 성공을 뜻하지 않는다. 실측 인테리어 정확도·로봇 통과가능공간·TF도 아니다.
- 현재 App은 새 프로젝트 생성 때만 가구를 고른다. 기존 장면의 E1 수치 박스 Add/Change/Undo는 유지하지만 의미 단위 가구 추가/변경/Undo나 자연어 처리는 아직 없다.

## 검증

| 범위 | 결과 |
|---|---|
| Python core | 178 PASS. v2.0 기존 계획 복원, v2.1 가구 형상/높이/yaw, 잘못된 카탈로그/입력 거절. |
| Python 저장·API·E1 통합 | 39 실행: 38 PASS, Windows symlink 1 SKIP. 가구 저장/복원, 잘못된 배치 미게시, 인증 API, 기존 프로젝트·편집 회귀. |
| Web | 145 PASS, production build PASS. 가구 수동 선택 전달/기존 방 생성 경로. |
| [실제 Chrome 새 프로젝트](../../artifacts/runs/20260929-e2b-furniture-browser-r1/result.json) | PASS. 합성 PNG, 3.6×5.2×2.6m 입력, 침대·책상 선택, Burger 옵션, 로봇/API 외부·장면명령 0. 격리 가짜 launcher이며 Isaac은 별도. |
| [같은 저장본의 새 실제 Isaac](../../artifacts/runs/20260929-e2b-furniture-isaac-r2/result.json) | PASS. 명시 검토·승인→Chrome/API/bridge/Isaac Build, 가구 prim·충돌 API·서로 다른 색, Burger visual mesh 4, USD 재열기, 원본 recipe 보존, Physics Run/실물 0. [시점 이미지](../../artifacts/runs/20260929-e2b-furniture-isaac-r2/authored-camera-viewport.png)에서 침대·책상과 Burger 위치를 육안 확인. |

초기 자동 시험은 sandbox가 Python 임시폴더 쓰기를 거절해 ERROR였다. 승인된 저장소의 임시폴더로 같은 시험을 재실행해 PASS했으며 기준을 완화하지 않았다. Isaac r1은 형상 Build PASS였지만 가구 prim 충돌/색별 명시 assertion 전 결과라 r2로 보강했다.

## 다음 E2

가구 의미 단위의 비파괴 Add/Change/Undo를 기존 E1 change-set에 연결하고, 저장/가짜 provider로 자연어 대상 명확성·출처 설명을 시험한다. 사용자 조절 가능한 내부·탑다운·사선/fit 보기와 밝기 모드, 두 번째 일반 방·기존 창고의 동일 제품 경로 리허설도 남았다. 회사 PC, 사진 해석 품질, 실측 기하/TF, 물리/실물은 별도 판정이다.
