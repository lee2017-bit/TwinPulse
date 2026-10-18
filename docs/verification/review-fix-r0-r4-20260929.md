# TwinPulse F1–F3 수정 검증 — 2026-09-29

## 판정 범위

| 결함 | 이전 사용자 경로 | 이번 수정·검증 | 남은 검증 |
|---|---|---|---|
| F1 | 엔진 starting/error에서 정지 요청이 HTTP 409로 제어기에 도달하지 않음 | 인증·CSRF 후 stop action만 런타임/전환 대기 게이트에서 전달. 로컬 HTTP→가짜 소유 제어기→가짜 transport, 실제 Chrome의 오류 자동 close·새 이동 잠금, 오류 중 화면 상태가 잠깐 이전 값인 경쟁 상황의 일반 정지·강제 Stop·Esc 각각 HTTP 200/`STOPPING`/소유 가짜 작업 종료 PASS. **VERIFIED_LOCAL_FAKE_PRODUCT_FLOW** | 실제 로봇 정지·통신 실패 시 최종 정지는 **NOT_RUN** |
| F2 | 일반 provider v2 저장 장면을 재시작 뒤 UI로 이어볼 수 없음 | 입력 archive 검증 읽기, provider/recipe 공통 검토 재개 API, App 버튼, 동일 원본만 재첨부. 텍스트/사진 각각 새 backend→실제 Chrome 검토·새 승인→기존 로컬 Isaac Build PASS. 누락 manifest/사진도 Chrome 재첨부, 다른 사진 거절 후 동일 사진만 승인·Build PASS. named 방 recipe+Burger도 동일 수정본으로 PASS. 저장 승인/원본 덮어쓰기 없음. **PRODUCT_FLOW_VERIFIED_FOR_TESTED_BRANCHES** | 임의 named 일반 provider 장면은 별도 사례로 NOT_RUN |
| F3 | 방 복사 실패가 최종 프로젝트 ID를 고착 | 별도 transaction 공간에서 준비·검증 후 동일 파일시스템 rename 게시, 요청 ID 재시도/영수증, legacy 잔류 폴더 fingerprint 확인·보관 후 명시 복구. 실제 Chrome→로컬 API의 복사 준비 실패·동일 ID 재시도·명시 복구 PASS. 추가 단일 실행에서 격리 저장소의 일시 잠금 충돌 409→같은 요청 ID 재시도 201→Open→새 소유 Isaac 세션 검토 PASS. **VERIFIED_TESTED_LOCAL_PRODUCT_FLOWS** | 복사 준비 단계 자체의 실패→Open을 동일 실행으로 합친 사례는 NOT_RUN; 회사 PC에서는 미검증 |

이는 사진방의 실측 기하·좌표 정합, Isaac 물리주행 또는 실물 데모의 완료 판정이 아니다. 로봇은 꺼진 상태로 보고됐으며 SSH/serial/센서/모터/배포·유료 provider 요청을 하지 않았다. 과거 정지 FAIL, 저장 자료, 실물 임무 잠금을 유지했다.

## 구현 경계

- F1: `api.py`에서 두 로봇 input endpoint의 body를 인증 뒤 한 번만 읽고 정확한 stop action만 준비 게이트의 예외로 분류한다. 소유자/job/sequence 판정은 원래 controller에 남긴다. cancel endpoint도 기존 소유 작업 계약을 사용한다. backend 자체가 종료되면 HTTP 전달은 불가능하며 자동 재연결·정지 완료 주장을 하지 않는다.
- F2: `revisions.py`의 `InputArtifactStore.load`가 저장 revision/이미지 hash·크기·경로를 검증한다. `application.py`는 저장된 원래 입력을 메모리 검토 상태로 선택하고, 디스크의 더 새 latest input을 보존한다. `product_workflow_service.py`는 pending generation/scene command를 거절하고 새 승인을 요구한다. API/React는 일반 v2와 방 recipe를 같은 복구 입구에 연결한다. 누락 archive는 같은 이름·MIME·bytes를 검증하여 명시 재첨부한다. 손상 자료는 덮어쓰지 않는다.
- F3: `project_catalog.py`에서 최종 프로젝트와 요청 ID를 별도 lock으로 직렬화하고, 검증된 폴더만 게시한다. 실패 transaction은 기록으로 남기고 다른 프로젝트 원본은 삭제하지 않는다. 기존 빈/부분 방은 fingerprint가 같고 active/draft가 아닐 때만 원본을 보관한 뒤 다시 만든다. UI는 같은 request ID를 재시도에 재사용한다.

## 실행 증거

- 최종 전체 오프라인 검증: [`artifacts/runs/review-fix-20260929-r8/manifest.json`](../../artifacts/runs/review-fix-20260929-r8/manifest.json) — `PASS`; core 176, Web 141, production Web build PASS, Isaac `NOT_RUN`. `test_h2b2_site_review`도 포함. r7은 Windows 임시 폴더 쓰기 거부로 중단되어 실패 기록을 보존했으며, 동일 검사만 해당 권한으로 r8 재실행했다.
- 집중 회귀: Python 114건 실행/디렉터리 symlink 미지원 1 SKIP(동시요청 보강 전); 새 lock과 로컬 HTTP 복구 추가 후 `test_a2_project_catalog` 13건 실행/동일 symlink 1 SKIP. 최종 전체 검사는 추가분까지 포함한다.
- 수정 전 F1의 엔진 오류 시 stop 전달 관련 7개 실패를 재현한 뒤 동일 종류 테스트 통과. `test_physical_controller`는 HTTP 200에서 멈추지 않고 가짜 transport의 stop packet을 확인한다.
- F2의 원래 텍스트/사진 archive와 project bytes 불변, stale revision/없는 원본/변조 거절을 `test_r5_product_api`로 확인. App 단위 테스트는 저장 v2 버튼·검토 phase 전환을 확인하나 실제 Chrome/Isaac 증거로 승격하지 않는다.
- F3의 실패 주입과 원본 보관, 실제 loopback API의 오류→같은 request ID 재시도와 복구를 `test_a2_project_catalog`로 확인. 같은 request ID의 이중 프로젝트 진입은 잠긴 상태에서 거절한다.
- 격리 실제 Chrome/로컬 backend/기존 Isaac: [`review-fix-20260929-v2-isaac-r2/result.json`](../../artifacts/runs/review-fix-20260929-v2-isaac-r2/result.json) 일반 v2 텍스트 PASS, [`review-fix-20260929-v2-photo-isaac-r1/result.json`](../../artifacts/runs/review-fix-20260929-v2-photo-isaac-r1/result.json) 일반 v2 사진 PASS, [`review-fix-20260929-room-isaac-r1/result.json`](../../artifacts/runs/review-fix-20260929-room-isaac-r1/result.json) 사용자 보존 방 recipe/Burger PASS. 각 경우 `build_site_scene` 1회, Run/실물 요청 0, 새 검토 승인 필요. 일반 v2 재개 뒤 프로젝트·archive byte SHA 불변. 일반 v2 첫 harness r1은 Isaac 초기화 전 `omni.timeline` import 오류로 FAIL이며 제품 판정이 아니다; r2는 초기화 순서 수정 후 PASS.
- 누락 원본 실제 Chrome 재첨부: [`review-fix-20260929-v2-reattach-photo-r2/result.json`](../../artifacts/runs/review-fix-20260929-v2-reattach-photo-r2/result.json) 사진 PASS(다른 bytes 거절→원본 동일 bytes 재첨부→검토·Build), [`review-fix-20260929-v2-reattach-text-r1/result.json`](../../artifacts/runs/review-fix-20260929-v2-reattach-text-r1/result.json) 텍스트 manifest PASS. 사진 r1은 브라우저 시험기가 다른 파일 input을 선택해 재첨부 버튼이 비활성인 harness FAIL; r2에서 저장 장면 폼의 input으로 수정했다.
- 실제 Chrome/로컬 backend 가짜 흐름: [`review-fix-20260929-project-browser-r2/result.json`](../../artifacts/runs/review-fix-20260929-project-browser-r2/result.json)은 방 생성 주입실패→같은 request ID 재시도→완성 목록, legacy 원본 보관·재생성 PASS. r1은 browser 판정기가 읽기 전용 로봇 보고 GET을 제어 요청으로 오분류한 harness FAIL; r2에서 POST/변경 요청 0 확인. [`review-fix-20260929-stop-error-browser-r2/result.json`](../../artifacts/runs/review-fix-20260929-stop-error-browser-r2/result.json)은 fake 소유 세션 활성 중 엔진 오류에서 자동 close가 전달되고 방향키 잠김을 확인. r1은 오류 주입 marker 이전의 watch를 오류 후 명령으로 계산한 harness FAIL; r2에서 분리. 기존 전체 fake 컨트롤러 [`review-fix-20260929-physical-fake-r2/result.json`](../../artifacts/runs/review-fix-20260929-physical-fake-r2/result.json) PASS(launcher ready는 합성 fixture, 실제 로봇 아님). r1은 fixture 준비 상태가 새 UI 게이트와 달라 bootstrap 단계 FAIL; 원본 보존.
- 실제 소유 런처의 프로젝트 재열기: [`review-fix-20260929-project-switch-r1/result.json`](../../artifacts/runs/review-fix-20260929-project-switch-r1/result.json) — Chrome 방 생성→Open 요청→이전 소유 엔진/backend 종료→새 launch ID/인증 세션으로 saved room 검토 PASS, 기존 프로젝트 byte 보존·승인 비승계·엔진 명령/로봇 요청 0. 방 생성 첫 요청 실패 주입은 이 run에 포함되지 않고 위 `project-browser-r2`에서 독립 검증했다.
- 명시적 오류 중 정지: [`finish-stop-ui-r3`](../../artifacts/runs/review-fix-20260929-finish-stop-ui-r3/result.json), [`force-stop-ui-r2`](../../artifacts/runs/review-fix-20260929-force-stop-ui-r2/result.json), [`escape-stop-ui-r2`](../../artifacts/runs/review-fix-20260929-escape-stop-ui-r2/result.json) — 실제 Chrome/로컬 backend/소유 가짜 제어기에서 각각 backend 오류 이후 `finish_stop`, `force_stop`, Esc→`force_stop` 요청이 HTTP 200/`STOPPING`과 해당 `stop_request`로 수락되고 가짜 작업이 종료됨. 테스트는 화면의 launcher ready 응답과 `watch` 응답만 이전 가짜 상태로 고정하여 오류 반영 직전 경쟁 상황을 재현했다. 원래 제품의 자동 close 동작은 바꾸지 않았다. r1은 watch가 409를 먼저 받아 UI가 자동 close되었고 r2 시험기 수정 후 PASS; 최종 HTTP 응답 확인은 일반 r3/강제·Esc r2에서 수행했다.
- 한 실행의 오류→재시도→Open: [`review-fix-20260929-project-retry-switch-r3/result.json`](../../artifacts/runs/review-fix-20260929-project-retry-switch-r3/result.json) — 격리 프로젝트 잠금을 첫 요청에만 주입해 Chrome의 생성 409→동일 요청 ID 재시도 201→Open→이전 소유 세션 종료→새 ID/인증 세션/Isaac ready→저장 방 검토를 연속 확인. 구 프로젝트 byte 불변, 승인 비승계, 외부/로봇/장면 명령 0. r1은 샌드박스의 Chrome `spawn EPERM`으로 브라우저 시작 전 FAIL, r2는 흐름 PASS, r3은 HTTP 409/201까지 명시 확인한 최종 PASS. 이 주입은 복사 중 파일 오류가 아니라 일시 잠금 충돌이다.
- 최종 소스 SHA-256: `api.py` `4e83777a31c331847ae70495857c3ab2748ab913736078e93079b4fdd2eed091`, `project_catalog.py` `d1cb175bb1b59376d837f4e2b6afe2c86ccb190c9b60d896718baa3b15de8595`, `App.tsx` `2b8569126d912093d20f2305a363845756f57148cd7392ef0a2aeb4075db39e2`, production JS `7acf7ba44a049065279baf4ad68de9f804f57f3f30b3770693060ebfa64f1663`.
- `git diff --check`는 종료코드 0; 기존 작업트리의 LF/CRLF 경고만 출력. 기존 dirty 변경을 초기화하거나 commit/push하지 않았다.

원본 사용자 방 사진 `artifacts/photo-scan-review-20260927/room.jpg` SHA-256은 기존 기록과 같은 `a183bf7e30cb6d1ddc712aa25f484f8763bca6ccbc75d4c8977aa99cbb6f6ea0`이다. 이 hash 일치가 실제 방 치수나 TF 검증을 뜻하지 않는다.

## R4 판정과 남은 경계

1. 지정된 F1–F3 로컬 제품경로의 R4 오프라인 수용은 **PASS_WITH_LIMITS**. F1 명시 정지는 서버 오류·화면 상태 지연 경쟁 상황에서 검증했고, 정상 UI 오류 반영 시 자동 close가 우선한다. 자동 close를 약화하거나 UI를 오류 후 활성 상태로 유지하지 않는다.
2. F3 한 실행의 첫 실패는 격리 잠금 충돌이다. 복사 중 실제 I/O 실패→재시도·legacy 보존 복구는 다른 실제 Chrome 시험에서 PASS지만, 그 실패 형태와 새 Isaac 소유 세션 Open을 한 실행으로 연결한 것은 아니다. 임의 named 일반 provider 장면, 회사 PC 설치·시작 실패 원인도 별도 검증이다.
3. 로봇 실제 통신·정지·주행과 방 사진의 실측 크기/TF는 전부 **NOT_RUN/미검증**. 사용자 현장 승인 및 별도 안전 확인 없이는 실물 단계로 가지 않는다. 다음 개발은 [기존 통합계획](../planning/TWINPULSE_INTEGRATED_OFFLINE_SOL_WORKPLAN_2026-09-29.md)의 P3 비파괴 편집/P1 회사 PC/P2 일반 프로젝트 흐름을 독립 범위로 인계한다.

이번 수정본의 실제 Chrome·로컬 Isaac 재Build는 일반 v2 텍스트/사진, named recipe, 누락 원본 사진/텍스트의 다섯 분기에서 수행했다. 지정한 R4 로컬 사용자 흐름은 위의 제한 아래 수용하되, 이를 전체 데모·실물 안전 PASS로 승격하지 않는다. 이전 날짜의 Isaac PASS를 이번 수정본의 PASS로 재사용하지 않았다.
