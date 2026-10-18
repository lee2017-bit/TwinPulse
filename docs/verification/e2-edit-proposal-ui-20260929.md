# E2k-2 가짜 편집 제안 UI와 작업 피드백 — 2026-09-29

**판정: 저장 가구 1개에 대한 오프라인 가짜 제안→검토→명시 저장→실제 Isaac Build 경로 PASS; E2 전체는 PARTIAL.** E2k-1의 읽기 문맥/API를 기존 `SceneEditReview`에 연결했다. 현재 저장 revision·선택 가구와 요청 문구로 가짜 구조화 응답을 만들고, 서버의 엄격한 검증을 통과한 응답만 기존 E1 미리보기로 보여준다. 모호하거나 지원하지 않는 요청은 설명하고 자동 저장하지 않는다. 이는 유료/실제 모델 응답이 아니라 제한된 로컬 규칙 기반 가짜 응답이다.

사용자 피드백: 편집 문맥 조회·검증·미리보기·저장, 배치 대기 가구의 미리보기·저장 중에는 화면 중앙에 진행 표시와 중복 요청 방지 상태를 띄운다. API/검증/저장 오류는 닫을 수 있는 키보드 접근 가능한 팝업으로 알린다. 연결 실패는 `Failed to fetch`만 표시하지 않고 App 서버 연결과 저장 장면 재조회가 필요함을 안내한다. 실패 뒤 자동 재시도·자동 저장·자동 Build는 없다. 기존 저장 결과가 불확실하면 다시 조회하도록 안내한다.

- `pnpm --dir apps/twinpulse-web test`: **21파일/161테스트 PASS**. 보류 요청의 로딩, 가짜 제안과 저장 분리, 실패 팝업·키보드 닫기, 배치 오류, 연결 실패 안내 및 기존 편집 회귀 포함. 첫 전체 실행에서 새 테스트의 중복 `role=status` 선택 때문에 **1 FAIL**; 테스트 선택자를 바로잡은 뒤 전체 PASS. 실패 이력 삭제/기준 완화 없음.
- `pnpm --dir apps/twinpulse-web build`: TypeScript + production build **PASS**.
- [최종 실제 Chrome→App→bridge→Isaac r3](../../artifacts/runs/20260929-e2k2-fake-edit-ui-r3/result.json): **PASS**. 격리 복사한 합성 사진 방의 저장 침대를 선택, 첫 문맥 요청을 의도적으로 실패시켜 [오류 팝업](../../artifacts/runs/20260929-e2k2-fake-edit-ui-r3/edit-error-popup.png) 확인, 다음 요청을 지연해 [로딩창](../../artifacts/runs/20260929-e2k2-fake-edit-ui-r3/edit-loading.png) 확인. 가짜 이동 제안→기존 미리보기에서 저장 0→명시 저장 1→승인 해제→별도 승인·Build 1회, 원본 recipe/draft 보존. [브라우저 결과](../../artifacts/runs/20260929-e2k2-fake-edit-ui-r3/browser-result.json): 외부/로봇 요청 0, 명령 `build_site_scene` 1, 페이지 오류 0. r1/r2도 PASS이나 r3가 최종 한국어 오류 문구/화면 캡처를 포함한다.
- `git -c core.safecrlf=false diff --check`: 최종 패치 공백 검사 PASS.

**남은 경계:** 이 팝업/로딩은 현재 장면 편집·배치 흐름의 요청에 적용되며 앱의 모든 기능에 대한 전역 오류 처리 완료를 뜻하지 않는다. 실제 provider가 이 편집 계약을 반환하도록 연결하지 않았고 자유 자연어 품질/실사진 의미 해석·사진→실측 좌표/회사PC/Physics/실물 조작은 미검증이다. Isaac 결과는 합성 방의 정적 Build이며 Run/로봇 시험이 아니다. 과거 실물 정지 FAIL·실물 임무 잠금은 변경하지 않았다.
