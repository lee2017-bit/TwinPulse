# E2k-1 저장 장면 편집 제안 문맥 — 2026-09-29

판정: **오프라인 가짜 응답→기존 편집 미리보기 계약 PASS; 실제 provider 연결과 E2 전체는 PARTIAL.** 저장 v2 방의 현재 project·원본/현재 revision·선택 가구·가구 호출 목록·현 객체 기하와 사용자 요청을 읽기 전용 `scene-edit-context-1.0`으로 만든다. 문맥에는 원본 사진 바이트/인증정보를 넣지 않는다. 문맥 digest는 요청 문구/선택/장면 변경 시 달라진다.

`scene-edit-proposal-1.0` 응답은 정확히 하나의 가구 추가·선택 가구 위치/방향 변경 또는 명확화만 허용한다. 전체 장면 교체 필드, floor/robot/mission, 다른 대상, 기존 가구의 ID·종류·카탈로그 변경, 오래된 digest/revision, 무변경 제안을 거절한다. 수용된 제안도 **자동 저장·Build가 아니라** 기존 E1 `preview_scene_edit`로 이동하며, 저장에는 여전히 preview digest/명시 apply, Build에는 새 승인/lease가 필요하다. 원본 recipe/project는 변경되지 않는다.

- 새 인증 API: `POST /v1/product/scene-edit/context`는 현재 저장 장면 문맥만 반환한다. `POST /v1/product/scene-edit/proposal-preview`는 외부/가짜 제안의 엄격한 형태와 문맥을 검사한 뒤 기존 미리보기를 반환한다. 현재 UI·유료 모델은 이 API를 자동 호출하지 않는다.
- [가짜 응답 통합시험](../../tests/integration/test_scene_edit_proposals.py): 실제 로컬 API를 통해 선택 침대 이동, clarification, 전체 장면·대상/종류 변경·무변경·오래된 문맥/장면 거절, 미리보기 전 저장 0, 명시 apply 뒤 sidecar 1회·승인 해제를 확인했다. 선택된 다른 가구는 보존된다. 로봇/외부/provider 호출 없음.
- 집중 편집/방 시험 33 PASS. [전체 오프라인 검증](../../artifacts/runs/20260929-e2k-edit-context-offline-r1/manifest.json) PASS: core 178, Web 155/production build 및 기존 통합 경로. 해당 실행의 Isaac suite는 `NOT_RUN`이며, 이 증분에 대한 Isaac/브라우저 UI·실모델 품질 증거로 쓰지 않는다.

남음: 기존 provider 어댑터의 실제 구조화 응답 생성, 모델 출력의 설명/모호성 품질, UI에서 문맥 확인·제안 검토, 실제 Chrome→Isaac 편집 재리허설. 모델 호출은 비용/설정 승인 전까지 하지 않는다. 사진 자동 해석·실측/TF·회사 PC·Physics·실물은 미검증이고 과거 실물 정지 FAIL과 실행 잠금을 유지한다.
