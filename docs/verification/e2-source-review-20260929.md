# E2h 방 계획 출처·근거 표시 — 2026-09-29

저장된 v2 방의 기존 검토 화면에 **읽기 전용 출처 패널**을 연결했다. 원본 입력·plan·scene revision, 로컬 편집 이력 횟수(되돌리기 포함), 도구 호출별 원본/사용자 수정과 기록된 근거 유형을 표시한다. 출처 설명은 원본/편집 plan을 재검사한 현재 workflow snapshot에서 계산하며 새 모델 호출이나 원본 저장 형식 변경은 없다. 임의 모델 `note` 원문은 이 패널로 되돌리지 않는다.

- `local-room-recipe` + `no-provider-call`은 **이번 로컬 가져오기에서** 사진 자동 해석/모델 호출이 없었음을 표시한다. recipe가 과거에 어떻게 작성됐는지는 증명하지 않는다. 그 외에는 저장된 provider/fixture 계획으로 표시하며 provider 이름만으로 이번 세션의 유료 호출·사진 정확도를 주장하지 않는다.
- 호출별 `visual`은 기록상 사진 관련 주장, `inferred`는 추정, 근거 부재는 미기록으로 표시한다. 기존 scene-change sidecar로 바뀐 호출은 사용자 로컬 수정으로 구분한다. 관측 ID/기록된 측정 분류도 실물 정합·물리 안전성의 통과 판정이 아니다.
- [저장 방](../../tests/integration/test_a2_room_recipe.py)·[가짜 provider](../../tests/integration/test_h2b2_site_review.py) 통합 테스트 합계 22개, [전체 비-Isaac verifier 최종 r3](../../artifacts/runs/e2-evidence-verifier-20260929-final-r3/manifest.json) PASS: core 178, Web 155, production build. [실제 Chrome→API→Isaac r3](../../artifacts/runs/e2-evidence-20260929-r3/result.json) PASS: 로컬 출처 패널 표시, 명시 검토/승인/Build 1회, Burger 시각 mesh 4, 외부·로봇 요청 0/Run 없음. r1/r2도 통과했으나 이후 문구를 더 정확하게 고쳐 r3로 재검증했다. 앞선 최종 검증 시도 두 건은 Windows 임시 폴더 샌드박스 접근 거부로 중단되었고, 로컬 검증 실행 권한을 받은 뒤 최종 r3가 통과했다.
- 한계: 제공된 plan의 의미/사진 위치가 참인지는 검증하지 않는다. 다른 일반 방·창고 및 E1 모드/선택 대상/가구 문맥을 모델에 전달하는 경로, 자유 자연어 이해, 실제 회사 PC·Physics·로봇은 별도. 따라서 E2 전체는 PARTIAL, 실물 정지 FAIL/임무 잠금은 그대로다.
