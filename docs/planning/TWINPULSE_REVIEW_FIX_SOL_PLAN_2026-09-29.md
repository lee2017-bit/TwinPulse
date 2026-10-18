# TwinPulse — 3시간 작업 후 발견 결함 상세 수정계획 / Sol 인수인계

- 작성일: 2026-09-29 KST, 계획 v1.0.
- 기준 저장소: `C:\Users\jaewo\Documents\TwinPulse`의 현재 작업 트리. 기존 미커밋 변경을 포함한다.
- 현재 상태(2026-09-29 후속 구현): **R0–R3 코드 수정과 오프라인 회귀 PASS, R4 지정 로컬 경로 PASS_WITH_LIMITS**. 실제 Chrome+격리 Isaac의 일반 v2 텍스트/사진 및 방 recipe 재개·Build, 누락 archive 재첨부, Chrome 생성 실패·동일 ID 재시도·복구, 소유 런처 Open→새 세션 검토 PASS. 추가 Chrome/가짜 제어기에서 서버 오류 중 화면 지연 경쟁 상황의 일반 정지·강제 Stop·Esc HTTP 200/`STOPPING`·가짜 종료 PASS. 격리 잠금 충돌 409→같은 요청 ID 재시도 201→Open→새 소유 Isaac 검토 단일 실행 PASS. 실물 정지·회사PC 및 다른 실패 종류의 단일 실행은 NOT_RUN. [수정 검증기록](../verification/review-fix-r0-r4-20260929.md)을 먼저 확인한다. 이하의 원인/구현 결정은 당시 계획으로 보존한다.
- 구현 대상: GPT 6 Sol. 이 문서를 읽으라는 요청만으로 구현·예약을 시작하지 않는다. 사용자가 후속 구현을 지시하면 아래 순서대로 진행한다.
- 우선순위: **R0 재현 고정 → R1 정지 전달 → R2 저장 장면 재개 → R3 프로젝트 생성 복구 → R4 제품 흐름 검증**. 완료 후 기존 [통합계획](TWINPULSE_INTEGRATED_OFFLINE_SOL_WORKPLAN_2026-09-29.md)의 미완료 P3/P1/P2부터 재개한다.
- 이 작업으로 P3의 Add/Change/Undo, 프로젝트별 실물 기록, 최종 자율주행 데모가 완료되는 것은 아니다.

## 1. 확인된 결함과 수정 후 사용자 경험

| ID | 우선순위 | 실제 확인 | 수정 후 동작 |
|---|---|---|---|
| F1 | 높음 | 인증된 physical input의 `force_stop`·`finish_stop`이 ready에서는 200/가짜 제어기 도달, error/starting에서는 409/미도달 | 엔진 오류 중에도 소유한 기존 작업에 대한 정지 요청 전달. 새 이동·작업 시작은 기존 조건에 따라 차단 |
| F2 | 높음 | 일반 provider v2 장면을 재시작하면 `restore_review_required`, artifact 없음, 생성 보호 잠금. room 이어보기는 `local-room-recipe`만 허용 | 일반 생성 장면과 방 recipe 모두 저장 원본을 검증하고 화면에서 검토 재개. 재생성·유료 호출 없이 현재 Isaac에 명시 Build 가능 |
| F3 | 중간 | 방 복사 중 오류를 주입하면 미완성 프로젝트가 `import_required`로 남고 같은 ID 재시도는 `FileExistsError` | 복사·검증이 끝난 프로젝트만 정상 목록에 게시. 실패 후 동일 이름 재시도 또는 명시적 보관·복구 가능 |

근거: [재현 기록](../verification/three-hour-review-findings-20260929.md). 이전 core176/Web140/build PASS는 당시 실행한 검사 결과이며 이 세 사용자 경로를 통과했다는 뜻이 아니다. 기존 PASS/FAIL 원본은 수정하지 않는다.

## 2. 범위와 공통 구현 원칙

1. AGENTS, 최신 PROJECT_MEMORY/BASELINE, 이 계획, 위 재현 기록을 읽고 현재 파일·상태를 대조한다. 기존 dirty 트리를 초기화하거나 예전 GitHub 코드로 되돌리지 않는다.
2. 기존 App/API/워크플로/저장소를 수정한다. 별도 데모 앱이나 병렬 제어기를 만들지 않는다.
3. 이 수정은 로봇 없이 구현·검증 가능하다. 로봇 SSH/serial/센서/모터/배포/전원 및 실물 시험은 범위에 없다. 기존 설치의 로컬 Isaac은 격리된 장면 검증에만 사용한다.
4. 새 유료 호출·클라우드·시스템 설치·설정, git commit/push, 임의 프로세스 종료, 자동화 재개는 포함하지 않는다. 3시간 작업 예약은 PAUSED 상태다. 새 마감을 추정하지 않는다.
5. v1/v2 입력·계획·장면의 기존 직렬화와 hash, 원본 사진/모델, 이전 정지 시험 결과·실물 임무 잠금을 보존한다. 결함 수정 때문에 정지 판정 시간을 완화하지 않는다.
6. 증분마다 해당 결함의 실패 재현→수정→관련 회귀를 기록한다. 전체 검사는 마지막에 한 번 수행하고 이후 변경·실패가 있을 때 필요한 범위만 다시 검사한다.
7. 인증 토큰·키·쿠키·사진 원문을 테스트 출력에 남기지 않는다. 외부 provider와 실제 로봇 transport가 호출되면 실패하는 오프라인 fixture를 사용한다.

## 3. R0 — 실패 재현을 정식 회귀로 고정

기존 `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\review_twinpulse_20260929.py`는 임시 진단 스크립트다. 공식 검증기는 아니며 이를 그대로 복사해 PASS 개수를 늘리지 않는다. 재현 동작을 아래 테스트에 편입한다.

| 결함 | 기존 테스트 확장 지점 | 수정 전 반드시 실패해야 할 요구 |
|---|---|---|
| F1 | `tests/integration/test_r5_product_api.py`, `test_physical_controller.py`, `apps/twinpulse-web/src/PhysicalRobotController.test.tsx` | 엔진 error 상태의 유효한 강제 Stop이 소유 제어기까지 도달 |
| F2 | `tests/integration/test_h2b2_site_review.py`, `test_a2_room_recipe.py`, `apps/twinpulse-web/src/App.test.tsx` | provider v2 재열기에서 화면 버튼으로 검토 재개·새 승인·Build 가능 |
| F3 | `tests/integration/test_a2_project_catalog.py`, `test_a2_room_recipe.py` | 복사/검증 실패가 정상 프로젝트를 게시하지 않고 동일 이름으로 재시도 가능 |

실패 이유가 fixture 인증 오류나 임시 디렉터리 권한 오류면 제품 결함 재현과 구분한다. 이전 임시 점검에서도 잘못된 CSRF 헤더를 바로잡은 뒤 F1을 재현했다. 정식 테스트는 기존 `product_headers`를 재사용하고 정상 상태 전달을 대조군으로 둔다.

완료 조건: F1~F3에 각각 제품 결함 때문에 실패하는 테스트가 있고, 기존 자료는 변경되지 않는다.

## 4. R1 — 정지 요청과 새 실행 요청의 공통 검사 분리

### 원인과 코드 위치

- `packages/twinpulse_app/src/twinpulse_app/api.py`: 제품 요청 인증 뒤 supervisor가 starting/error이면 POST를 일괄 거절한다. 정지 처리에 도달하기 전에 실패한다.
- `PhysicalRobotController.tsx`의 `input()`은 backendReady가 false여도 정지는 전송하도록 되어 있다. 이 의도를 서버가 깨고 있다.
- `physical_controller.py`는 소유자/job/sequence 검사와 Stop 종류를 이미 구분한다. 이 제어기를 새로 만들 필요가 없다.

### 구현 결정

1. 제품 요청을 **읽기 / 기존 작업의 정지·취소 / 새 실행·변경**으로 분류하는 작은 공통 함수를 API에 둔다. URL만 보고 입력 endpoint 전체를 예외로 두지 않는다.
2. Host/Origin/session/CSRF 검사는 항상 먼저 유지한다. 정지 후보 endpoint의 JSON을 크기 제한 아래 한 번만 읽고 정확한 body shape/action을 검사한다. 이후 handler는 같은 검증된 body를 사용한다.
3. 정지 예외는 endpoint별 현재 지원 action만 허용한다.

| Endpoint | 엔진 준비와 분리할 action |
|---|---|
| `/v1/product/robot/physical/input` | `stop`, `close`, `finish_stop`, `force_stop` |
| `/v1/product/robot/controller/input` | `stop`, `stop_all`, `close`, `lidar_stop` |
| 기존 generation/command cancel endpoint | 기존 소유 작업 취소 계약을 검증한 요청만 |

4. starting/error 및 상태 파일 누락으로 발생하는 `status_unavailable`에서도 위 정지 요청을 기존 controller에 전달한다. unmanaged/ready 장면 동작의 기존 계약은 유지한다. 나머지 미준비 managed 상태에서 새 실행이 실수로 열리지 않는지도 검사한다.
5. 실제 처리 단계에서 owner, job/session ID, sequence, mode를 그대로 검사한다. 현재 세션이 없으면 정확한 session 오류를 반환한다. 정지를 위해 새 연결이나 작업을 만들지 않는다. 이미 종료된 작업을 되살리지 않는다.
6. 정지에 유효시간을 새로 강제하지 않는다. 기존 코드가 stop의 expiry를 면제하는 계약을 보존한다. 반면 오래된 sequence, 다른 소유자의 작업, 알 수 없는 action은 계속 거절한다.
7. 프로젝트 전환 대기 게이트도 같은 분류를 사용한다. 현재 예외 목록의 input endpoint 전체 허용이 새 `forward`/`watch` 요청까지 열지 않게 한다. pending switch 이후에는 정지·취소만 예외다.
8. `finish_stop`은 이미 수락한 제한된 명령을 마친 뒤 추가 명령을 끊는 기존 의미를 유지한다. `force_stop`은 이를 상향 중단할 수 있고, 늦게 도착한 일반 정지가 강제 정지를 되돌리지 못한다.
9. UI는 활성 소유 작업의 정지 버튼과 Esc를 오류 중에도 사용할 수 있게 유지한다. 표시를 '요청 전달/접수'와 '정지 관측 확인'으로 구분한다. 서버 접수만으로 실제 정지 완료라고 표시하지 않는다.
10. 런처/backend가 이미 완전히 종료된 경우 HTTP 전달 자체는 불가능하다. 기존 종료 처리와 로봇 로컬 watchdog을 보존하고 UI에는 전달 불확실 상태를 표시한다. backend를 자동 재시작하여 과거 이동 세션을 복원하지 않는다.

### 필수 수용 검사

- ready/error/starting/status 파일 누락 × `force_stop`/`finish_stop`에서 정상 요청이 fake controller에 도달한다. 현재 job 없는 경우는 session 오류이며 새 job 생성 0.
- 같은 상태에서 forward/backward/회전/watch/qualify/새 mission·lidar 시작은 준비조건을 우회하지 않는다.
- 잘못된 CSRF·owner·job·sequence·body shape·action은 거절된다. 정지 예외로 인증 검사가 약해지면 실패다.
- 전환 대기 중 정지는 도달하고 새 방향 입력은 거절된다. 늦은 방향 응답이나 일반 정지가 terminal stop을 취소하지 않는다.
- 실제 HTTP→가짜 소유 controller 입력까지 검사한다. HTTP 200만 반환하는 stub 통과에 그치지 말고 기존 controller의 가짜 transport에도 stop packet이 기록되는지 확인한다.
- 브라우저에서 활성 가짜 작업→엔진 오류 주입→일반 정지/강제 Stop/Esc를 누르고 전달 상태·실패 안내를 검사한다. 실제 로봇은 사용하지 않는다.

R1 완료: 서버·UI 회귀 PASS, 기존 인증/소유권/정지 기준 불변. **실물 정지 재검증은 NOT_RUN**으로 남긴다.

## 5. R2 — 모든 저장 v2 장면의 화면상 검토 재개

### 원인과 기존 재사용 지점

- `App.tsx`: Create Draft가 `saved_site_scene_protected`에서 잠기며 입력 선택도 해당 함수 안에 묶여 있다. 이어보기는 `provider_name == local-room-recipe`에만 나타난다.
- `product_workflow_service.py`: `continue_room_recipe()`도 같은 제한을 가진다. 기존 테스트는 `select_input()`을 직접 호출해 UI 단절을 놓쳤다.
- `application.py`: 생성 직전 원본 입력을 `InputArtifactStore`에 저장한다.
- `packages/twinpulse_core/src/twinpulse_core/revisions.py`: 현재 `InputArtifactStore`에는 `save()`만 있고 읽기 API가 없다. 이 누락을 구현 범위에 포함한다.

### 구현 결정

1. 기존 v2 전체 재생성 보호는 유지한다. '생성 잠금 해제'를 복구책으로 사용하지 않는다.
2. `InputArtifactStore`에 검증된 읽기 기능을 추가한다. 저장된 draft의 `input_revision`을 기준으로 `inputs/<digest>/revision.json`과 `<image-sha>.bin`을 읽는다. 반환값은 검증된 revision과 원본 이미지 바이트이며 저장소 밖 경로를 받지 않는다.
3. manifest와 저장 draft의 revision 동일성, 이미지 순서·이름·SHA·MIME·디코딩/크기 제한을 확인한다. 현재 허용된 이미지 수와 기존 직렬화를 유지한다. 링크/경로탈출/과대 파일/변조를 거절한다. 텍스트 전용 입력도 지원한다.
4. 저장된 measurement constraints를 기존 schema/parser로 복원한다. 현재 provider 설정, 현재 기본 모델, 새 tool catalog 값을 덮어 넣어 digest를 다시 만들지 않는다. 원래 generation settings는 생성 이력이고 현재 호출 권한은 아니다.
5. ApplicationService에 원본 저장 장면을 **메모리의 검토 상태로 재개**하는 공통 경로를 둔다. 모든 파일/plan 검증을 먼저 마치고 입력·artifact·phase를 함께 갱신한다. 실패 시 기존 in-memory 상태나 project 파일을 반쯤 변경하지 않는다.
6. workflow의 공통 `resume_saved_scene`은 일반 provider v2와 local room recipe를 구분해 소스를 검증하고 같은 review 상태로 연결한다. local recipe의 사진/Burger/recipe hash 검사도 유지한다. 기존 continue-room API는 호환 wrapper로 남길 수 있다.
7. 권장 새 API: `POST /v1/product/project/resume-scene`, body는 `project_id`, `expected_scene_revision`, `expected_input_revision`. 인증/CSRF 뒤 서버가 현재 저장 draft와 일치 여부를 검사한다. active generation·pending command·프로젝트 전환 도중 재개는 거절한다. 클라이언트가 raw plan이나 임의 경로를 공급하지 않는다.
8. 복원 대상은 저장된 draft의 원래 입력이다. `latest_input`이 다른 더 새 입력이면 UI에 '저장 장면의 입력 버전으로 검토 재개'라고 표시한다. 사용자의 버튼 선택으로 이 버전을 검토하되 디스크의 더 새 입력/기존 draft를 덮어쓰지 않는다.
9. 재개는 provider 호출 0, 자동 Build/Run 0이다. 저장된 승인을 복원하지 않고 현재 revision 검토 승인과 현재 Isaac 제어권으로 Build한다. 이 승인은 장면 검토 단계이며 실물 이동 명령마다 승인을 추가하는 설계가 아니다.
10. App에 provider 이름과 무관한 '저장 장면 열기/검토 계속'을 제공한다. 저장 입력 요약·생성 출처·복구 가능 여부를 표시하고 원본이 있으면 다시 사진을 올리게 하지 않는다. 재개 성공 후 review 화면으로 이동한다.
11. provider 설정 변경 후에도 저장 장면이 있으면 재개 동작을 제공한다. 현재 `provider_settings_changed()`가 phase를 empty로 만드는 경로를 함께 검토한다. 현재 모델 설정과 과거 장면 출처를 혼동하지 않는다.
12. 구 프로젝트에 원본 archive가 없는 경우에는 '원본 필요'를 표시하고 동일 원본 재첨부 경로를 제공한다. 서버가 저장 참조/hash와 대조한 후에만 재개한다. 손상된 원본을 자동 덮어쓰거나 새 생성으로 대체하지 않는다. 실제로 부족한 자료가 있을 때만 재첨부를 요구한다.
13. 기존 v1 동작/직렬화는 회귀 검사한다. 범용 새/추가/변경 편집, 자동 schema 마이그레이션은 이 수정에 끼워 넣지 않는다.

### 필수 수용 검사

- 일반 v2: 텍스트/사진 각각 저장→backend 재시작→App 재열기→저장 장면 버튼→review→새 승인·lease→Build 요청.
- default/named 프로젝트 각각 검증한다. local-room-recipe 사진/Burger도 같은 검토 재개 후 유지된다.
- 저장 이후 provider 설정이 달라져도 원래 입력·plan·scene hash는 같고 provider 호출 수는 0이다.
- manifest/이미지/recipe 변경·누락, stale scene revision, 다른 프로젝트 ID, 중복 재개·동시 입력 변경을 거절하거나 동일 결과로 처리한다. 반쯤 갱신된 검토 상태는 허용하지 않는다.
- missing archive는 명확한 원본 복구 UI로 연결한다. 다른 사진을 첨부해 과거 draft의 입력으로 인정하면 실패다.
- 실제 브라우저 테스트에서는 테스트 코드가 `workflow.select_input()`이나 내부 상태를 직접 세팅하여 복구를 대신하지 않는다. 초기 생성용 결정적 가짜 provider와 고정 입력은 허용하되 재열기는 실제 UI/API를 통한다.
- 독립된 기존 로컬 Isaac 세션에서 일반 v2 장면 한 건을 위 UI로 재개·Build하고 객체/revision을 확인한다. 방 recipe 한 건도 회귀한다. 이 테스트는 scene-only이며 물리 주행을 요구하지 않는다.

R2 완료: 일반 v2와 recipe 모두 UI 재개가 검증됨. 실제 Isaac 실행이 막혔다면 `TESTED_OFFLINE / ISAAC_NOT_RUN`으로 구분하고 runtime 완료를 주장하지 않는다.

## 6. R3 — 방 프로젝트 생성의 임시 준비·게시·복구

### 원인과 코드 위치

`project_catalog.py:create_from_preserved_bedroom()`이 `create_empty()`로 최종 폴더부터 만든 뒤 사진→recipe→Burger→import를 수행한다. 실패 시 최종 ID는 이미 사용 중이고, API는 실패라고 응답하지만 catalog에는 사용 가능한 항목처럼 남는다.

### 구현 결정

1. 기존 빈 프로젝트 생성과 방 복사 생성을 분리한다. 방 복사에서는 최종 위치에 먼저 `create_empty()`를 호출하지 않는다.
2. 같은 state root/파일시스템 안의 비공개 transaction 공간에 임시 state root를 만든다. 권장 구조는 `project-transactions/<operation-id>/staged-state/projects/<project-id>/...`다. recipe의 최종 project ID를 유지하면서 기존 `ProjectStore.for_project`와 room 검증기를 재사용할 수 있다.
3. 입력 확인→사진/recipe 저장→전체 pinned Burger 복사/hash 검사→input archive와 project.json 저장→정식 로더로 재읽기를 모두 임시 위치에서 끝낸다. catalog는 이 transaction 공간을 정상 프로젝트로 나열하지 않는다.
4. 최종 ID별 생성 lock을 두고 목적지 부재를 확인한다. 동일 파일시스템의 디렉터리 이동으로 완성 프로젝트를 게시한다. 존재하는 최종 프로젝트를 덮어쓰는 `replace`는 금지한다. Windows에서 실제 동작을 검사한다.
5. operation ID/대상 ID/원본 fingerprint/단계/검증된 결과를 별도 transaction journal에 기록한다. 사용자 원본이나 인증자료는 journal에 넣지 않는다. 성공 표시와 응답은 게시 및 최종 위치 검증 이후에 한다.
6. 새 UI 요청은 `request_id`를 가져 재시도할 수 있게 한다. 기존 `{project_id}` 요청도 지원하되 새 idempotency 계약과 구 요청을 구분한다. 같은 request ID+같은 대상/원본은 동일 결과, 다른 내용으로 같은 ID 재사용은 거절한다.
7. publish 직후 응답 유실/프로세스 종료도 다룬다. 최종 폴더의 생성 receipt와 transaction journal을 대조해 해당 작업이 게시한 프로젝트임을 확인한 경우만 성공을 다시 반환한다. 단순히 같은 이름이나 파일 내용이 같다는 이유로 다른 기존 프로젝트를 인수하지 않는다.
8. publish 전 실패는 최종 ID를 점유하지 않는다. own transaction만 FAILED로 기록하고 재시도 가능하게 한다. 오래된 lock은 PID만으로 타 프로세스를 종료하거나 무조건 삭제하지 않는다. 종료된 자기 작업임을 확인할 수 없으면 명확한 복구 상태로 남긴다.
9. 이전 코드가 남긴 미완성 최종 폴더도 안내한다. 자동 삭제하지 말고 '불완전 프로젝트 보관 후 다시 만들기'를 제공한다. active 프로젝트/유효한 draft/알 수 없는 자료가 있는 폴더는 자동 복구 대상에서 제외한다. 명시 선택 시 검사 당시 fingerprint를 다시 확인하고 state root 내 복구 보관소로 원본을 보존한 뒤 같은 이름으로 재생성한다. 임의 경로나 광범위한 디렉터리 이동을 허용하지 않는다.
10. UI는 생성 중/실패/복구 필요/완료를 구분한다. 실패한 operation을 정상 Open 버튼으로 보여주지 않고, 동일 요청 재시도 동작을 제공한다. 실패할 때마다 사용자가 새 이름을 만들어야 하는 흐름은 통과시키지 않는다.

### 필수 수용 검사

- 사진 쓰기, recipe 쓰기, Burger 중간 복사, hash 검사, project 저장, publish 직전에 각각 오류 주입: 기존 프로젝트/원본 hash 불변, 정상 catalog에 반제품 0, 같은 이름 재시도 성공.
- publish 직후 응답 유실: 동일 request 재시도 결과가 같은 완료 프로젝트이며 복사 중복/기존 데이터 덮어쓰기 0.
- 동일 ID 동시 요청: 완성 프로젝트 하나만 게시된다. 다른 요청은 명확한 충돌 결과이며 winner 원본을 건드리지 않는다.
- 부분 복사 후 backend 재시작: 복구 상태를 읽을 수 있고 같은 이름으로 완료할 수 있다. 임의 기존 프로젝트나 타 작업 폴더를 지우지 않는다.
- 이전 형태의 empty/import_required 잔류 폴더: 원본 보관·동시변경 거절·유효 draft 보호를 검증한다.
- 실제 App 버튼→실제 local API→오류 주입→오류 안내→재시도→목록의 완성 프로젝트→Open→R2 검토 재개를 확인한다.

R3 완료: 새 실패에서 최종 ID가 고착되지 않고, 과거 잔류 폴더에도 보존 가능한 복구 안내가 있다. 정상 프로젝트와 원본의 byte/hash 보존 증거를 남긴다.

## 7. R4 — 누락된 사용자 경로 중심의 통합 검증

### 실행 순서

1. R1 집중 API/controller/UI 회귀.
2. R2 archive/워크플로/UI 회귀와 R3 transaction/복구 회귀.
3. 실제 Chrome+local backend에서 세 결함의 정상·실패·복귀 흐름을 수행한다. 로봇은 가짜 transport만 쓴다.
4. 같은 Web build로 격리된 기존 로컬 Isaac의 저장 장면 재개·Build, 기존 방+Burger, 새 프로젝트 전환을 확인한다.
5. 최종 소스의 기존 오프라인 전체 검사와 변경분 검사를 수행한다. 관련 신규 검사가 `verify_twinpulse.ps1` 또는 그 명시적 후속 suite에 포함됐는지 확인한다. 특히 H2b2가 기존 전체 verifier에서 빠져 있으므로 이번 회귀가 보고서 밖에 남지 않게 한다.

권장 명령의 기준 cwd는 저장소 root다. Sol은 실제 파일/환경을 먼저 확인하고 새 테스트 모듈명을 명령에 반영한다.

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.integration.test_r5_product_api tests.integration.test_physical_controller tests.integration.test_manual_controller
.\.venv\Scripts\python.exe -B -m unittest -v tests.integration.test_h2b2_site_review tests.integration.test_a2_room_recipe tests.integration.test_a2_project_catalog tests.integration.test_a2_project_isolation
pnpm --dir apps/twinpulse-web test
pnpm --dir apps/twinpulse-web build
```

최종 전체 검사는 `scripts/verify_twinpulse.ps1 -SkipIsaac -ArtifactDirectory <새로운_실행_폴더>`를 사용한다. 실제 Isaac/browser 검증은 별도 결과로 연결한다. test suite의 PASS 개수가 아니라 시나리오별 결과·source/build hash·원본 hash·provider/robot 호출 0이 수용 근거다.

### 증거와 보고 규칙

- 매 수정 증분의 상태표: F1/F2/F3 `OPEN → REPRODUCED → FIXED_OFFLINE → VERIFIED_PRODUCT_FLOW`. 실제 Isaac 항목은 별도 기록한다.
- UI 요청/응답·제어기 전달·최종 관측을 구분한다. Stop 200을 실물 정지 성공으로 기록하지 않는다.
- 재시도 검증의 범위를 정확히 쓴다. 기존 startup harness는 테스트가 직접 새 manager를 만들고 optional recovery에서 Python 경로를 바꾼다. 실제 운영 런처가 환경 오류를 자동 수리했다고 주장하지 않는다. 이 계획은 회사 PC 원인 수정을 약속하지 않는다.
- 신규 실패는 새 폴더에 보존하고 원래 PASS/FAIL 파일을 고치지 않는다. 권한/환경 실패는 NOT_RUN/BLOCKED이지 PASS가 아니다.
- 완료 시 `docs/verification/`에 수정 검증기록을 남기고 Baseline 버전/이력, PROJECT_MEMORY, 통합계획의 현재 상태를 함께 갱신한다.
- 제품 흐름에서 세 결함을 닫기 전 P3 편집 기능을 먼저 추가하여 원인을 가리지 않는다. 특정 Isaac 검증이 환경 문제로 막히면 미검증을 기록하고 독립적인 R3 검사는 계속할 수 있다.

## 8. Sol에게 전달할 실행 지시문

> `C:\Users\jaewo\Documents\TwinPulse`의 AGENTS.md와 최신 PROJECT_MEMORY/BASELINE, `docs/planning/TWINPULSE_REVIEW_FIX_SOL_PLAN_2026-09-29.md`를 읽고 R0→R4를 구현·검증하라. F1 엔진 오류 중 정지 전달, F2 일반 저장 장면의 실제 UI 재개, F3 방 복사 실패의 동일 이름 재시도·보존 복구를 먼저 해결하라. 기존 코드 경로와 원본/dirty 변경/hash/인증·소유권/실물 잠금을 보존하라. 내부 함수 호출만으로 사용자 흐름이 성공했다고 판정하지 말고 실제 App/API 및 필요한 격리 로컬 Isaac 흐름을 검증하라. 로봇·유료 호출·설치·시스템 설정·commit/push·예약 재개는 하지 말라. 관련 검증기록과 Baseline/Memory를 동기화하고, 실제 수정 완료와 미검증을 분리해 보고하라. 세 결함 수정 후 기존 통합계획의 남은 P3/P1/P2 작업을 다음 순서로 인계하라.

## 9. 현재 인수인계 상태

| 단계 | 현재 상태 | 다음 결과물 |
|---|---|---|
| R0 | REPRODUCED / 정식 회귀 편입 | F1은 수정 전 로컬 HTTP 7개 실패를 확인. F2/F3은 회귀에 편입; 상세는 수정 검증기록 |
| R1 | VERIFIED_LOCAL_FAKE_PRODUCT_FLOW | 정지 전용 게이트·가짜 제어기 전송·인증, Chrome fake 오류 자동 close와 서버 오류 중 화면 지연 경쟁 상황의 일반 정지·강제 Stop·Esc 각각 수락/가짜 종료 PASS. 실물 정지는 NOT_RUN |
| R2 | PRODUCT_FLOW_VERIFIED_FOR_TESTED_BRANCHES | 일반 v2 텍스트·사진 및 named recipe, 누락 원본 텍스트·사진 재첨부의 실제 Chrome 재개·새 승인→격리 Isaac Build PASS. 임의 named 일반 provider는 NOT_RUN |
| R3 | VERIFIED_TESTED_LOCAL_PRODUCT_FLOWS | 임시 준비·게시, 요청 ID 재시도, 잔류 폴더 명시 보관·복구, 로컬 HTTP·오류 주입·Chrome 생성/재시도/복구 PASS. 격리 잠금 충돌→같은 ID 재시도→소유런처 Chrome Open→새 세션 검토 단일 실행 PASS. 복사 중 I/O 실패→Open 단일 실행은 NOT_RUN |
| R4 | PASS_WITH_LIMITS | 최종 `review-fix-20260929-r8` core176/Web141/build 및 위 범위별 Chrome/Isaac PASS; 회사PC·다른 실패 종류·실물은 별도 검증 필요 |

이번 문서 작성으로 구현 상태를 승격하지 않는다. 사용자가 Sol에 구현을 지시한 시점부터 실행한다.
