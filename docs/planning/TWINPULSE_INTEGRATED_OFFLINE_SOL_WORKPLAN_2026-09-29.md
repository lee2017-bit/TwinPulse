# TwinPulse — 로봇 없는 준비 5항목 + 제품 개선 4항목 통합 실행계획

> **2026-09-30 실행순서 갱신:** 아래 E3–E7/로봇 준비의 다음 실행 우선순위는 [전체 데모 사전준비 DP0–DP7](TWINPULSE_DEMO_END_TO_END_PREPARATION_PLAN_2026-09-30.md)을 따른다. 다음 증분은 DP0+DP1(데모 명령–시험 대응/전체 지정 원본 수집·PC 반출·OFF 재분석)이다. 아래 과거 NEXT와 우선순위는 이력으로 보존하며 기존 기능의 성공/실패 근거는 변경하지 않는다. 계획 변경 자체를 구현 완료로 표시하지 않는다.

## v1.1 현재 우선 실행계획 — 기능 단위로 완결하기

- **2026-09-29 E2k-3 부분 판정:** 영어 기본 구조화 편집 provider 요청/스키마와 문맥 hash 확인, 가짜 provider 응답→기존 App preview/명시 Apply 경계까지 [오프라인 PASS](../verification/e2-provider-edit-adapter-20260929.md). provider45/통합11 PASS. 실제 유료 호출·live UI 버튼은 없으며 E2 전체 PARTIAL. 비용 승인 전에는 E3의 독립 오프라인 작업 또는 추가 가짜 음성검증으로 진행.
- **2026-09-29 E2k-2 부분 판정:** 저장 장면 문맥의 오프라인 가짜 편집 응답을 실제 UI 검토에 연결하고 요청 중 로딩/실패 팝업을 추가. Web161/build, 합성 방 실제 Chrome→Isaac r3에서 고의 연결 실패·지연·미리보기·명시 저장·재승인 [PASS](../verification/e2-edit-proposal-ui-20260929.md). 실제 provider/자유 자연어·전역 오류 UI/실사진·실물은 잔여이며 E2 전체 PARTIAL.
- **2026-09-29 E2k-1 부분 판정:** 저장 장면/선택 가구를 묶은 읽기 문맥과 엄격한 가짜 편집 응답→기존 preview까지만 [오프라인 PASS](../verification/e2-edit-proposal-context-20260929.md). provider 실제 호출/UI 제안 검토/이번 Isaac 재리허설이 남아 E2 전체 PARTIAL. 자동 적용/전체 장면 재생성은 여전히 금지.
- **2026-09-29 E2j 부분 판정:** 보존방·다른 합성 사진방·합성 창고를 동일 저장 검토→실제 Chrome/Isaac Build 경로에서 각각 PASS [증거](../verification/e2-multi-environment-20260929.md). 창고는 정적 rack fixture, 일반 사진 해석·실측이 아니다. 세션 내 프로젝트 전환/provider 편집 문맥/회사·Physics·실물 미검증으로 E2 전체 PARTIAL.
- **2026-09-29 E2i 부분 판정:** 저장 장면의 현재 가구·선택 ID를 제한 로컬 요청에 결속하고, 대상 없음·종류 불일치에서 저장 없이 설명하도록 했다. Web155/build·합성 방 실제 Chrome→Isaac [제한 로컬 PASS](../verification/e2-selected-context-20260929.md). provider 편집 문맥·다른 방/창고·실사진/회사/Physics/실물은 E2 잔여.
- **2026-09-29 E2h/g 부분 판정:** 저장 검토의 [출처·근거 표시](../verification/e2-source-review-20260929.md)와 [카메라/조명 선택](../verification/e2-presentation-20260929.md)을 실제 App/Isaac 경로에 연결했다. 사진 해석 정확도·현장 좌표/Physics·실물은 주장하지 않는다.
- **2026-09-29 E2f 부분 판정:** 배치 후 마커 재드래그와 위·오른쪽·아래·왼쪽 방향의 UI/저장 yaw/실제 Isaac 연결 [로컬 PASS](../verification/e2-furniture-direction-20260929.md). E2 보기/조명·실사진·Physics/회사/실물 잔여.
- **2026-09-29 E2e 부분 판정:** 명확한 다중 가구 요청은 종류를 확정하고 위치만 배치 대기에 둔다. 평면 드래그·클릭/수치→일괄 preview/apply를 실제 Chrome→API→Isaac [로컬 PASS](../verification/e2-multi-furniture-staging-20260929.md). 사용자 실사진 자동배치·카메라/조명·모바일 이미지 전달·Physics/회사/실물은 남는다. E2 전체 PARTIAL.
- **2026-09-29 E2d 부분 판정:** `추가/이동` 한 종류만 로컬 규칙으로 해석해 기존 E2c 편집 양식→preview/apply/새 승인→실제 Chrome/Isaac Build까지 [제한 로컬 PASS](../verification/e2-offline-furniture-request-20260929.md). 모호 요청/좌표 부족은 추측·저장하지 않는다. 자유 자연어/저장·가짜 provider, 사용자 보기/조명, 다른 방/창고·Physics/회사PC/실물은 E2 잔여.
- **2026-09-29 E2c 부분 판정:** 기존 저장 방의 로컬 가구 호출 Add/Change/Undo→별도 저장 revision→새 승인/Chrome/실제 Isaac Build→새 프로세스 재열기가 [로컬 PASS](../verification/e2-furniture-edit-20260929.md). 합성 입력·수치 UI 범위이며 자연어 대상/설명·사용자 보기/조명·다중 환경/Physics/회사PC/실물은 E2 잔여다.
- **2026-09-29 E2b 부분 판정:** 7종 로컬 매개변수 가구를 사용자 선택으로 새 방에 넣는 App/API/2.1 plan/저장/실제 Isaac 연결 [PASS](../verification/e2-furniture-20260929.md). 기존 v2.0 기본/과거 실패 보존. E2 전체는 가구 의미 Add/Change/Undo·자연어·보기 조절·다중 환경 인수 잔여로 **PARTIAL**.
- **2026-09-29 E2a 부분 판정:** App의 새 사진+사용자 입력 치수 방 생성→독립 프로젝트/원본 보존→새 프로세스의 같은 저장본 실제 Chrome/Isaac Build까지 [로컬 PASS](../verification/e2-manual-room-20260929.md). 사진은 해석하지 않은 원본이며 방은 입력 치수 3벽/바닥, Burger는 선택 시 visual-only. E2 전체는 가구 종류/자연어/보기 조절/다중 방 인수가 남아 **PARTIAL**.
- **2026-09-29 E1 구현 판정:** 보존 사용자 방의 저장 v2 장면에서 App Add→Change→Undo→재변경→새 승인→실제 Chrome/Isaac Build, 별도 Isaac 프로세스 재열기와 합성 실패 후 정상 stage 복원까지 [로컬 수용](../verification/e1-scene-edit-20260929.md). 박스 수치 편집 범위이며 임의 새 방/가구·자연어·물리주행·실물은 E2 이후 또는 현장 검증으로 남는다. 다음 구현 진입점은 E2다. 아래 “계획 작성만” 문구는 v1.1 제정 당시 이력이다.
- 개정: 2026-09-29. 사용자가 상세 계획을 요청한 데 따른 **계획 작성**이다. 이번 개정에서 제품 구현·시험은 하지 않았다.
- 다음 구현 순서는 이 절의 E1–E7을 우선한다. 아래 기존 P0–P9는 요구·기술 참조 및 과거 진행 이력이다. 기존 완료/실패 증거를 변경하지 않는다.
- 목표: `방 열기 → 추가·변경·Undo → 저장·재열기 → Burger/목표 → 모의 자율 임무 → 정지 → 명령·관측 비교 → Twin 재생`을 기존 제품에서 완결한다.
- 사용자 현장시험 없이 아래 로컬 기능을 구현·검증할 수 있다. 회사 PC·실물의 미검증을 이유로 이미 수용한 로컬 기능까지 계속 PARTIAL로 묶지 않는다.

### 1. 현재 출발점과 완료 단위

최신 전체 오프라인 결과는 `artifacts/runs/review-fix-20260929-r8/manifest.json`의 core176/Web141/build PASS, Isaac suite NOT_RUN이다. 별도 실제 Chrome/Isaac 저장장면 검토·Build와 오류복구의 지정 경로는 [R4 증거](../verification/review-fix-r0-r4-20260929.md)에 있다. 이 결과를 새 기능의 통과 증거로 전용하지 않는다.

현재 정식 편집, 일반 방 작성 흐름, 프로젝트별 기록 결속, 장애물 우회, 전체 통합에는 미구현이 남아 있다. 단순히 사용자 디버깅만 기다리는 상태가 아니다. 아래 완료선은 구현 전에 고정하며, 회사/실물 결과가 추가될 때까지 무한히 확대하지 않는다.

| 순서 | 사용자에게 제공할 완결 기능 | 기존 요구 대응 | 검증 환경 |
|---|---|---|---|
| E1 | 기존 방 추가·변경·Undo·재열기 | P3, P2 일부 | 실제 App/브라우저/로컬 Isaac |
| E2 | 다른 방 작성·주거 가구·보기 조절 | P2/P4/P8 | 로컬 입력·저장/가짜 provider·실제 Isaac |
| E3 | 프로젝트별 명령·관측 기록·연속 재생·비교 | P5 | 저장 로그·가짜 제어기·실제 브라우저 |
| E4 | 목표 기반 모의 자율 주행·우회·두 정지 | P7 | 합성 2D/App 및 별도 Isaac physics |
| E5 | 연결 한 번으로 상태 수집·준비 판정 | P6 | 실제 App·가짜 robot transport |
| E6 | 작업 중 엔진 장애·저장 실패 복구 | P1 잔여/공통 실패 | 소유 로컬 프로세스·브라우저·Isaac |
| E7 | 동일 빌드 전체 사용 흐름 인수 | P9 | 실제 App·로컬 Isaac·격리 자료 |

순서는 E1→E2→E3→E4→E5→E6→E7이다. E1에서 편집 revision, E2에서 방/가구, E3에서 기록을 고정한 뒤 E4 실행에 연결한다. E4 모의 실행은 실물 readiness를 요구하지 않는다. E6 결함이 앞 단계 사용을 깨면 해당 결함을 먼저 고치고 복귀한다. E4 physics 환경이 막혀도 독립적인 E5/E6 개발은 진행한다.

### 2. E1 — 기존 방을 편집하고 다시 여는 기능

**사용자 결과:** 기존 방에 객체 하나를 추가하고 침대만 옮긴 뒤 Undo/재수정/저장/재열기가 된다. 첫 구현 목표는 이 전체 경로다.

1. **E1a 변경 계약:** 원 `SiteDraftRecord`·사진·recipe를 보존하고 별도 versioned change-set을 둔다. project/input/source/parent revision, operation ID, 대상 객체 집합, typed tool call, 결과 revision을 결속한다. 기존 `DerivedReviewStore` 검증·원자 저장 방식을 재사용하되 scan 보정 형식에 가구 편집을 억지로 넣지 않는다.
2. **E1b 보존 검사:** Add는 새 ID만, Change는 선택한 호출/객체 집합만 변경한다. 한 호출이 여러 객체를 만들면 영향 대상을 전부 보여준다. 비대상 객체·로봇·임무는 canonical digest로 동일성을 검사한다. 기존 24 call/64 객체 한계, v1/v2 직렬화/해시를 유지한다.
3. **E1c App/API:** `새 환경 / 현재에 추가 / 현재에서 변경`을 제공한다. 빈 프로젝트 기본은 새 환경, 기존 장면 기본은 추가. 새 환경은 새 프로젝트로 생성한다. 객체 선택/수치 입력→전후 위치·크기와 영향 객체 미리보기→적용을 기존 App에 연결한다. 이 첫 기능은 유료 모델 없이 사용 가능해야 한다.
4. **E1d 저장/Undo:** 같은 operation ID는 같은 결과를 반환한다. 적용 직전 source/parent 일치를 재검사하고 변경 이력/활성 revision을 원자 게시한다. Undo는 이전 상태를 결과로 갖는 새 revision이다. 중간 파일은 최신본으로 채택하지 않는다. 삭제 기능은 첫 범위에 추가하지 않는다.
5. **E1e Isaac 적용:** 저장 revision과 실제 표시 revision을 구분한다. 기존 검토/Build 경로의 engine receipt 뒤에만 3D 적용 완료로 표시한다. 저장 성공 후 엔진 실패하면 ‘저장됨·3D 반영 실패’로 안내하고 마지막 정상 stage를 유지한다. 저장과 엔진 전체가 원자적이라고 주장하지 않는다.
6. **E1f 복원:** 원본+변경 이력을 검증해 같은 장면을 재구성한다. 실행 승인·과거 실물 readiness는 복원하지 않는다. 형상 변경에 영향받는 경로/정합 참조를 stale로 처리하고 보기 변경은 제외한다.

**코드 연결:** core `site_tools.py`/`site_contracts.py`; app `site_draft.py`, `project_store.py`, `derived_site_review.py`, `application.py`, `product_workflow_service.py`, `api.py`; React 편집 패널; Isaac adapter/compiler. 새 변경 모듈 이름은 구현 시 확정한다.

**인수시험:** 실제 Chrome에서 방 열기→추가→침대 이동→Undo→다시 변경→저장→프로세스 재시작→동일 상태 재열기→실제 Isaac Build. 원사진/recipe·비대상 pose/재질·외부 prim 불변 확인. 집중 회귀는 중복 ID, stale revision, 동시 적용, 다중 객체 도구, 저장/rollback 실패, 24/64 경계, 승인 비승계다.

**완료선:** UI부터 실제 3D·재열기까지 통과하면 **비파괴 편집 로컬 완료**. 자연어 변경은 E2에 별도 귀속한다. 단위 시험만으로 E1을 닫지 않는다.

### 3. E2 — 반복 가능한 방 작성·가구·보기

**사용자 결과:** 자신의 방과 다른 방을 독립 프로젝트로 만들고, 서로 다른 주거 가구를 배치하고, 잘 보이는 화면으로 다시 연다.

1. 날짜/개인 고정 경로를 제거한 사진 업로드·검증된 recipe 가져오기·수동 치수 입력을 App에 연결한다. 원본은 해당 프로젝트에 보관하고 누락 시 기존 재첨부 경로를 사용한다. 새 사진 해석은 기존 provider를 연결하되 오프라인 검증은 저장/가짜 응답임을 표시한다.
2. 1차 가구 범위: 침대·옷장·책상·의자·소파·식탁·수납장과 기존 rack/pallet. 기존 로컬 자산 또는 매개변수 형상으로 종류를 구별한다. 크기/축/pivot/시각·충돌 형상/출처/버전을 등록한다. 매번 랜덤 자산을 고르지 않는다.
3. 기존 Burger를 일반 프로젝트에서 배치·저장·재열기한다. visual 모델과 physics 구동 모델은 구별한다.
4. E1 모드·선택 대상·기존 장면·가구 목록을 자연어 처리 문맥에 전달한다. ‘소파 추가’, ‘선택한 침대 이동’, 모호한 대상, 없는 가구를 저장/가짜 provider로 시험한다. 원사진 추정과 사용자 수정 근거를 보존한다.
5. 이해한 요청·수정 가능한 가정·실제 사용 자료·변경 예정/결과를 짧게 설명한다. 적용 성공은 receipt에 따른다. 한국형 아파트는 수정 가능한 가정이며 실제 조회 없는 ‘관련 데이터를 가져왔다’ 표현은 금지한다.
6. 실내 기본 보기, 위/사선, 화면 맞춤, 밝기, 조명 모드를 지원 범위 안에서 제공한다. 편집 후 카메라를 보존하고 보기용 벽 숨김으로 충돌 형상을 삭제하지 않는다.

**코드 연결:** `project_catalog.py`, `room_recipe.py`, `bedroom_twin.py`, ToolCatalog/site tools, 기존 provider adapter, `scene_compiler.py`, React 작성/보기 패널.

**인수시험:** 사용자 방·다른 합성 방·창고를 같은 제품 경로로 작성/전환/재열기. 다른 프로젝트 원본/이력 불변. 실제 Isaac에서 가구 구별, 내부 가림·과도한 어두움/밝음, Burger 식별, 편집 후 시점 유지 확인.

**완료선:** 로컬 자료의 작성·편집·보기·복원 완료. 새 사진의 실제 모델 해석 품질/비용은 별도 미검증이며 후속 개발을 막지 않는다.

### 4. E3 — 명령·관측 기록과 연속 재생

**2026-09-29 후속:** 새 default 세션에 App scene/profile 시점 증거 또는 null을 고정하고, 읽기 비교의 match/mismatch/unknown 및 늦은 응답 폐기를 [가짜 회귀로 확인](../verification/e3-project-session-replay-20260929.md). 이 값은 실제 로봇 좌표/배치 증명이 아니다. E3 전체 **PARTIAL**이며 named 세션 생산자·임무 전체 조건/실측 정합/3D 재생/물리 비교는 미완료.

**2026-09-29 진행:** 프로젝트 귀속/hash 색인→읽기 전용 기록 타임라인·재생/탐색/설명용 비교→보존방 합성 경로 재생을 [한 묶음으로 검증](../verification/e3-project-session-replay-20260929.md). 로컬 E3 **PARTIAL**: 새 default 제어 기록만 자동 귀속, named 생산자·scene/profile/boot/release·실제 room/odom 정합·3D 연속 표시·동일조건 물리 비교는 아래 완료선에 아직 미달. E4 진입 시 이 부분을 완료로 간주하지 않는다.

**사용자 결과:** 방별로 ‘어떤 명령에 어떤 관측이 돌아왔는지’를 보고 Twin에서 재생·비교한다.

1. 새 세션 시작에 project/scene/profile/실행원/boot/release를 고정한다. 기존 global JSONL은 보존하고 프로젝트별 참조 인덱스를 추가한다. 귀속 근거 없는 옛 로그는 미귀속 이력으로 둔다.
2. 수동/자율 공통으로 의도→전송→수락→출력→관측→종료 이유를 기록한다. 시계 영역/sequence를 유지한다. 명령 적분의 예상 이동과 odom 등의 관측 이동을 분리한다.
3. 연속 재생·일시정지·탐색·배속을 기존 이력/Twin 화면에 연결한다. 관측 공백을 표시하고 보간은 시각화라고 명시한다. 재생 transport는 현재 로봇 명령 경로와 분리한다.
4. 같은 scene/start/goal/profile/정책/센서 조건의 비교를 제공한다. 조건 차이를 명시하고 목표 도달·시간·거리·정지 이유·충돌 계측을 따로 보여준다.
5. WASD/IME, 마우스 release, blur, hold 만료를 기존 fake controller로 검사한다. 입력 종료와 세션 종료를 구분해 유효 세션에서 매 명령마다 체크/재연결을 요구하지 않는다.

**코드 연결:** `session_journal.py`, `session_history.py`, `physical_controller.py`, `bedroom_rehearsal.py`, `SessionHistory.tsx`, `RouteComparison.tsx`, Twin 재생 패널.

**인수시험:** 두 프로젝트의 수동/자율 fake 세션→저장→재시작→재생→JSON 다운로드. 타 프로젝트 혼합, 누락 관측, 부분 tail, 쓰기 실패, 변조, 시계 불일치, 장면 변경 후 옛 이력 재생을 확인한다.

**완료선:** 프로젝트별 기록·재생·비교 로컬 완료. 저장 실물 로그 재생은 새 실물 주행 검증으로 표시하지 않는다.

### 5. E4 — 목표 기반 모의 자율 임무

**사용자 결과:** 목표를 한 번 지정해 시작하면 모의 센서에 따라 이동·회전·우회하고, 두 정지 기능 및 실행 기록이 작동한다.

1. 목표를 project/geometry revision·frame·footprint·정합 근거에 결속한다. 합성 환경에는 명시 합성 변환을 사용하고 사진 방향을 실제 room↔odom 변환으로 승격하지 않는다.
2. 수동/자율에 공통 command guard를 연결한다. 목표·영역·속도·기한·중단 조건을 한 임무 범위로 고정하고 임무 안에서는 이동/회전마다 승인을 요구하지 않는다.
3. 기존 장애물 발견 시 종료 기능에 **관측된 이동 가능 공간에서의 제한된 재계획**을 추가한다. unknown은 free가 아니다. 차체를 반영해 통로/회전 여유를 검사하고 경로 없음·센서 이상·기한 초과를 이유와 함께 종료한다. 탐색 횟수/시간 상한으로 진동·무한 재시도를 막는다.
4. 일반 정지는 현재 **짧고 기한 있는 제어 구간** 이후 새 이동을 차단한다. 먼 waypoint/임무 전체 완료를 기다리지 않는다. 강제 Stop/Esc는 현재·대기 명령을 취소하고 정지 요청을 우선 전달한다. 늦은 응답/재계획이 자동 재개하지 못한다.
5. E4a는 합성 2D+실제 App, E4b는 실제 로컬 Isaac의 접촉/동역학 검증으로 나눈다. 외형 mesh 이동은 E4b 증거가 아니다. 지원 physics profile을 사용할 때 실물 Burger와의 차이를 명시한다.
6. 충돌 감점 규칙을 시험 전에 versioned 평가 설정으로 고정한다. 충돌·도달·시간·거리 원시 지표도 보존한다. 평가 점수와 매 출력 전 충돌 방지 판단을 각각 구현한다.

**코드 연결:** `room_goal.py`, `navigation_binding.py`, `mission_contract.py`, `local_navigation.py`; app 임무/기록 경로; robot mission runtime의 오프라인 계약; 기존 Isaac adapter/physics harness와 목표 UI.

**인수시험:** 열린 경로 도달, 우회 가능, 완전 차단, 차체보다 좁은 통로, 동적 장애물, scan 지연/누락, pose 점프, 연결 상실, 재계획 중 두 정지. 실제 센서 adapter 출력이 planner/guard 입력으로 들어가는지 확인한다. contact 계측은 격리된 의도적 접촉 fixture로 검증한다.

**완료선:** E4a/E4b 각각 판정 후 필수 시험 통과 시 로컬 자율 모의 주행 완료. 실제 TF/실물 출력 권한은 이 결과로 발급하지 않는다. physics가 막혀도 E5/E6은 계속한다.

### 6. E5 — 연결·준비 한 동작으로 통합

**사용자 결과:** 별도 PC 점검 없이 `연결·준비` 한 번으로 상태와 필요한 다음 행동을 확인한다.

1. 기존 PC 준비를 연결 내부에 통합하고 조건이 같으면 유효 결과를 재사용한다. 연결 성공/수집 완료/조작 가능을 구분한다.
2. 배터리 전압·시각, boot/release/profile, 모터 상태, scan/odom/TF와 신선도, 차체/정합 근거, 정지 qualification을 묶어 수집한다. OFF/인증 오류/센서 미시작/불일치를 구분한다.
3. 같은 boot/release/profile/관련 정책의 유효 qualification을 재사용한다. 무효화 이유가 있을 때만 필요한 시험을 안내한다. 매 명령마다 수동 확인·정지시험을 요구하지 않는다.
4. 읽기 연결에 모터 활성화/주행을 섞지 않는다. 필요한 능동 수집·정지시험은 준비 세션의 실제 내용을 한 번 제시하고, 이후 실행은 임무 범위 승인으로 진행한다.
5. E3 기록과 E4 상태 계약에 연결해 결과/실패/다음 행동을 저장한다. 사용자가 매번 복사하지 않아도 로컬 결과를 다시 읽을 수 있게 한다. 채팅으로 자동 전송된다는 기능은 주장하지 않는다.

**코드 연결:** `robot_diagnostics.py`, `physical_controller.py`, 기존 connection/준비 코드, `RobotDiagnostics.tsx`/`PhysicalRobotController.tsx`, robot 수집 코드의 fake 경로.

**인수시험:** 실제 App+fake transport로 OFF/센서 미시작/TF 누락/stale scan/정상/boot·버전 변경/qualification 재사용·무효화/단절·취소·저장 실패/중복·오래된 응답 확인.

**완료선:** 연결·수집·판정의 오프라인 제품 연동 완료. 실제 네트워크/장치 확인만 현장에 남긴다.

### 7. E6 — 작업 중 오류 복구

1. 초기 startup뿐 아니라 ready 이후 엔진 종료/heartbeat 상실에도 원인·저장 상태·복구 동작이 남도록 소유 launcher/backend 수명을 조정한다. 기존 정지 전달 경로를 보존한다.
2. 새 소유 세션으로 재시작하고 저장 프로젝트/로그를 복구한다. 이전 ready/receipt가 새 세션을 오염시키지 않게 한다.
3. 원인/다음 행동을 한국어로 간결하게 표시한다. 진단 export와 README/Quickstart를 현재 실행 흐름에 맞춘다. 오래된 CLI 전환 안내를 현재 필수 단계로 남기지 않는다.
4. 회사 PC는 관측 환경·오류별 복구 안내를 준비한다. 로컬 성공을 회사 근본원인 해결로 해석하지 않는다. 전역 패키지 강제 변경은 하지 않는다.

**코드 연결:** `process_manager.py`, launcher/backend/engine host, App 오류 UI와 실행 안내.

**인수시험/완료선:** 실제 브라우저+소유 프로세스의 ready 후 고장→진단→새 세션→저장 방/로그 복구. 다른 프로젝트·외부 사용자 프로세스·원본 불변. 로컬 복구 완료와 회사 PC 확인 대기를 별도 표시한다.

### 8. E7 — 같은 빌드의 전체 인수

- **리허설 A:** 사용자 방→가구 추가/변경/Undo→저장→종료·재열기→Burger/목표→모의 임무→우회→결과·연속 재생·동일 조건 비교.
- **리허설 B:** 다른 방 새 작성→가구 다양성/자연어 변경(저장·가짜 응답 표시)→프로젝트 전환→서로 다른 이력→보기 변경→원래 방 복귀.
- **리허설 C:** 준비 fake 실패/회복→일반 정지/강제 Stop→엔진 장애→진단·재시작→자료 복구. 오프라인 시험의 실제 robot transport 호출은 실패 처리한다.
- 같은 source/build fingerprint로 관련 Python/React/build, 브라우저, Isaac 시각/physics 결과를 묶는다. 오래된 결과를 최신 PASS로 합산하지 않는다.
- 검사는 변경 영향 집중 회귀→기능 완결 시 제품 E2E→최종 묶음 회귀 순이다. 새 변경/실패가 없으면 반복 검사 대신 다음 기능으로 진행한다.
- 시작/전환/편집/재생 시간과 정지 전달 지연은 측정 구간·환경·횟수를 기록한다. 제어는 기존 명령 만료/정지 정책을 지켜야 한다. 일반 UI의 미측정 성능을 임의 수치로 보장하지 않는다.
- 한 인수 기록에 화면·시험명령·증거·현장 순서를 남긴다. 기능 상태는 `미구현 / 구현중 / 로컬 수용 완료 / 환경상 시험 막힘`으로 표시한다. 사용자 미관 평가는 개선 입력이며 에이전트가 수행 가능한 기능 검증의 전제조건이 아니다.

**완료선:** E1–E6 지정 로컬 기능을 동일 빌드 A/B/C로 통과. 실패 항목만 미완료로 남기고 통과한 편집/기록 등의 상태까지 취소하지 않는다. 전체 실물 데모 완료는 별도다.

### 9. 현장에서만 필요한 확인

1. 실제 연결·수집으로 현재 boot/release·배터리·센서 상태 확인.
2. 실제 scan/odom/TF, 센서 장착/차체, 방 좌표 대응 검증. 부족한 대응점/측정만 요청.
3. 버전 비교 후 필요한 배포와 현재 조건의 제한된 정지/저속 시험. 과거 통과/실패를 현재 결과로 덮어쓰지 않음.
4. 한 번 승인한 임무 범위의 실물 자율 이동·장애물 대응·두 정지·로그 재생 확인.

이때 사용자는 현장 상태/실제 반응을 확인하고 에이전트는 수집·판정·원인 분석을 담당한다. 이 네 항목은 E1–E7 개발 대기 사유가 아니다. ‘전원만 켜면 실물 데모 완료’는 약속하지 않는다.

### 10. Sol 실행·인계 규칙

- 다음 구현 지시의 첫 대상은 **E1a–E1f 전체 사용자 경로**다. 직전 R4 시험을 처음부터 반복하거나 추가 계획 작성으로 시작하지 않는다.
- 현재 지침/관련 변경/증거를 읽고 기존 모듈을 재사용한다. 순수 계약만 만든 뒤 다음 기능으로 넘어가지 않고 App/API/저장/Isaac까지 연결한다.
- 보고는 ‘이제 사용 가능한 동작 / 확인 환경·증거 / 다음 미완료 동작’으로 한다. 시험·문서 개수나 경과시간을 기능 진척으로 대신하지 않는다.
- 의미 있는 기능 완료에 Baseline/Memory를 동기화한다. 현장 확인과 로컬 완료를 분리하고, 독립 환경 blocker 때문에 나머지를 멈추지 않는다. 같은 범위 진행 허락은 단계마다 다시 묻지 않는다.
- 기존 dirty 변경·원본·과거 실패·직렬화/hash·정지 기준 보존. 로봇 접속/배포/실물, 유료 호출/클라우드, 설치·시스템 설정, commit/push, 새 에이전트/예약은 이번 계획 작성 범위에 없다.
- **이번 개정: 계획 완료, E1–E7 신규 구현·시험 미실행.** 아래 과거 성과는 그대로 유지한다. 사용자가 계획 평가 후 구현 지시를 하면 이 순서를 적용한다.

---

## v1.0 요구사항·기술 상세와 과거 진행 이력

> **2026-09-29 수정 진행 현황:** F1 정지 전달, F2 일반 저장장면 검토 재개, F3 복사 실패의 ID 고착은 기존 App/API에서 수정했다. [R0–R4 상세 상태](TWINPULSE_REVIEW_FIX_SOL_PLAN_2026-09-29.md)와 [증거](../verification/review-fix-r0-r4-20260929.md)를 먼저 확인한다. 이번 수정본으로 실제 Chrome→격리 Isaac 장면/원본재첨부 5분기, Chrome 프로젝트 재시도·복구, 오류 중 화면 지연 조건의 Stop 3종→가짜 제어기, 격리 잠금 충돌→같은 ID 재시도→새 소유 Isaac 검토 단일 실행이 PASS다. R4 지정 로컬 경로는 `PASS_WITH_LIMITS`; 회사PC·다른 실패 종류·실물은 미검증이며 아래 P단계의 완료·실물 데모 성공으로 승격하지 않는다. 새 자동화 승인은 아니다.

- 작성: 2026-09-29 KST / 계획 v1.0 / 대상 구현자: GPT 6 Sol.
- 상태: **아래 P단계는 원래 통합계획이며 단계별 완료 판정은 별도.** 후속 요청으로 선행 R0–R3 결함 수정과 R4 지정 로컬 경로를 제한부 수용했다. 기존 부분 구현을 재사용하며 0부터 재작성하지 않는다.
- 기준 저장소: `C:\Users\jaewo\Documents\TwinPulse`. GitHub 구버전 복원/수정 요청이 아니다. 현재 dirty 작업 트리가 출발점이다.
- 이 문서는 이번 범위의 **작업 순서·인수 기준·인수인계 단일 진입점**이다. 기술 상세는 [호환성·저작 UX 계획](TWINPULSE_RUNTIME_COMPATIBILITY_AND_AUTHORING_UX_PLAN_2026-09-29.md), 구조 배경은 [적응형 아키텍처 계획](TWINPULSE_ADAPTIVE_ARCHITECTURE_REVIEW_SOL_PLAN_2026-09-29.md)을 참조한다. 충돌하면 최신 사용자 결정과 AGENTS/Baseline을 우선한다.
- 최초 작성 때는 계획만 요청됐고, 이후 사용자가 상세 수정계획의 구현을 명시 지시했다. 기존 잘못된 마감/예약을 재사용하지 않으며, 이 문서는 새 예약·새 에이전트·새 기한을 만들지 않는다.

## 1. 최종 도달점

사용자가 앱에서 **기존 방을 열고 → 필요한 부분만 고치고 → Burger와 목표를 선택하고 → 모의 임무를 실행하고 → 정지·결과·이동 기록을 Twin에서 다시 보는 흐름**을 로봇 없이 끝까지 확인한다. 동시에 실제 연결 시 필요한 수집·판정·실패 안내 코드를 준비해 현장에서 긴 개발을 반복하는 일을 줄인다.

이것은 ‘사진만으로 실측 방과 실물 자율주행이 완성’이라는 뜻이 아니다. 실제 TF/odom·방 축척·장착 치수·현재 배포본·정지/주행 특성은 현장 확인으로 남는다. 현장 시험에서 발견될 모든 수정까지 없다고 보장하지 않는다.

### 요청 누락 방지표

| 원래 요청 | 통합 단계 | 완료 시 사용자에게 보이는 결과 |
|---|---|---|
| O1 프로젝트 생성→방 가져오기→Burger→저장·재열기 | P2, P3, P4, P9 | 실제 사용자 방 자료로 작업을 이어감. 빈 프로젝트/Burger 준비 충돌 해소 |
| O2 프로젝트별 명령·관측·임무 기록 | P5, P7, P9 | 다른 방과 분리된 기록, 명령과 관측 비교, Twin 재생·동일 조건 비교 |
| O3 통합 연결 점검·자료 수집 준비 | P6, P9 | 별도 PC 점검 클릭 없이 한 번 연결→결과/필요 단계 안내. fake 검증 완료 |
| O4 방 목표→임무·장애물 대응 | P7, P9 | 좌표 근거별 실행 경로, 우회/우회 불가/센서 오류/정지 검증 |
| O5 전체 제품 리허설 | P9 | 프로젝트→목표→모의 임무→정지→재생을 실제 제품 UI에서 연속 실행 |
| I1 실행환경/Engine Startup | P1, P9 | 엔진 실패해도 남는 진단 화면, 원인·복구 선택·최소 진단 자료 |
| I2 새 환경/추가/변경 | P2, P3, P8, P9 | 기존 객체를 보존하는 수정·Undo·저장/재열기 |
| I3 카메라·조명 | P4, P9 | 읽기 쉬운 기본 보기와 밝기·화면 맞춤, 편집 후 시점 보존 |
| I4 공간별 가구·자연어 응답 | P8, P9 | 주거에 맞는 가구와 실제 사용 자료/가정/변경 결과 설명 |

## 2. 현재 출발점과 유지해야 할 기존 성과

- 공통 ToolCatalog, EngineCapabilities/관측/평가의 부분 기반, named 프로젝트 목록·빈 생성·recipe 읽기, 기존 방+Burger 표시, 세션 journal/이력, 합성 임무/일부 Twin 시점 표시가 있다. 전부 새로 만들지 않는다.
- 마지막 전체 오프라인 기록은 `artifacts/runs/20260929-project-create-r1/manifest.json`의 core176/Web131/build PASS, Isaac NOT_RUN. 새 통합계획의 시험 결과가 아니다. 실행 전에 현재 소스/검사 구성을 다시 확인한다.
- `prepare_project_burger_visual`은 빈 ProjectRecord도 기존 프로젝트로 거절한다. 목록/생성의 부분 PASS와 처음부터 끝까지의 사용자 흐름은 다르다.
- named 프로젝트의 실물 콘솔은 전역 세션 이력 혼합을 막기 위해 잠겨 있다. 프로젝트별 이력 구현을 이유로 실물 임무 잠금을 자동 해제하지 않는다.
- 저장 native scan에는 현재 로봇 odom/TF가 없다. 현재 room-goal 후보는 `mission_request=null`이며 이를 근거 없이 채우지 않는다.
- 실제 Isaac의 Burger visual 표시 검증과 동역학 주행 검증은 별개다. 사용자 방의 측정 정확도도 미검증이다.
- 현재 엔진 조기 종료 감지, 장면 rollback, non-rack box 도구는 이미 있다. 회사 보고서의 문제를 전부 ‘현재 기능 부재’로 단정하지 않는다.
- 최신 수정본의 현물 검증과 과거 정지 FAIL/후속 QUALIFIED 기록을 boot/release별로 구별한다. 과거 통과·실패를 현재 준비 상태로 재사용하지 않는다.

## 3. 순서와 단계 통과 규칙

권장 실행 순서:

**P0 기준 고정 → P1 시작 안정화 → P2 프로젝트 이어쓰기 → P3 비파괴 저작 → P4 보기 → P5 기록·재생 → P6 연결 준비 → P7 임무·우회 → P8 가구·대화 → P9 통합 리허설**

이 순서는 우선순위다. P8의 소규모 가구 작업 때문에 P6/P7을 뒤로 미루지 않는다. 반대로 Isaac 환경 하나가 막혀도 독립적인 P5 데이터 계약/P6 fake 작업까지 전부 중단하지 않는다.

| 단계 | 반드시 필요한 선행조건 | 중간 사용자 가치 |
|---|---|---|
| P0 | 없음 | 이전 실패/기능/자료를 잃지 않는 시작점 |
| P1 | P0 | 실패 원인이 보이고 다시 시작할 수 있는 앱 |
| P2 | P0, P1의 프로세스 상태·소유권 계약 | 실제 방을 만들고 저장 후 다시 열기 |
| P3 | P2의 ID/revision/저장 계약 | 추가·변경해도 기존 작업 유지 |
| P4 | P2/P3의 geometry와 view 분리 | 사용자가 보이는 화면으로 검토 가능 |
| P5 | P2의 프로젝트 경계, P3의 scene revision | 기록을 열고 입력/관측/결과 비교 |
| P6 | P1의 상태/오류 계약, P5의 수집·저장 경로 | 연결 후 무엇이 부족한지 즉시 판별 |
| P7 | P3 revision, P5 기록, P6 readiness, 기존 frame/footprint 계약 | 목표 기반 모의 임무와 우회·정지 |
| P8 | P3 change-set, P4 presentation, 기존 ToolCatalog | 공간별 가구와 정직한 대화 |
| P9 | P1–P8 해당 인수 기준 | 두 요청 묶음 전체의 제품 통합 증거 |

### 상태 규칙

- `NOT_STARTED → IMPLEMENTING → TESTED_OFFLINE → VERIFIED_ISAAC`를 해당 범위에 사용한다. 원래 Isaac을 요구하지 않는 순수 데이터 단계에는 `ISAAC_NA`를 명시한다.
- `PARTIAL / BLOCKED`는 이유·다음 작업과 함께 기록. 코드 작성/단위 시험만으로 전체 완료 처리 금지. 회사 PC와 실물은 별도 `NOT_VERIFIED` 축이다.
- 필수 불변조건을 깨는 회귀 실패는 수정 후 진행한다. 로컬 환경/권한으로 특정 시험만 못 하면 NOT_RUN을 남기고 그 증거를 필요로 하지 않는 독립 항목만 진행한다.
- 기존 성공 증거를 재사용하려면 대상 source/build/입력 fingerprint와 범위를 대조한다. 새 코드가 과거 PASS를 자동 상속하지 않는다.
- 후속 사용자가 이 전체 계획의 구현을 승인하면 단계마다 단순 진행 허락을 다시 묻지 않는다. 새 비용·시스템 변경·실물 작업 등 범위 확대만 별도로 요청한다.

## 4. P0 — 기준 고정과 실행 가능한 backlog

**할 일**

1. AGENTS, 최신 Memory/Baseline, 본 문서, 관련 검증기록을 읽는다. `git status`로 기존 dirty 변경을 보존하고 대상 파일·현재 테스트 명령·마지막 결과를 inventory로 묶는다.
2. 실제 사용자 방 사진/recipe, 기존 Burger manifest, 저장 scan·명령 journal, default/named 프로젝트, v1/v2 직렬화·hash를 원본 경로+해시로 고정한다. 원본 복사/변환이 필요하면 파생물로 기록한다.
3. 현재 App에서 할 수 있는 것/끊기는 지점을 API/UI 동작으로 확인한다. 외부/로봇 transport가 호출되면 실패하는 오프라인 harness를 재사용한다.
4. 원래 요구 O1–O5/I1–I4별 증거 위치와 P0–P9 상태표를 만든다. 기존 검사 명령과 새 시험 위치를 지정하며 테스트 수를 맞추기 위해 기준을 낮추지 않는다.

**완료**: 기존 자료/hash 불변, 현재 baseline 회귀 결과 또는 구체적 환경 blocker 확보, 모든 요구가 뒤 단계에 매핑됨. 회사 오류 재현을 위해 정상 설치를 일부러 손상시키지 않는다.

## 5. P1 — 시작 안정화·환경 진단의 실제 UI 연결

**대상**: `packages/twinpulse_app/src/twinpulse_app/process_manager.py`, `scripts/twinpulse_engine_host.py`, `scripts/twinpulse_backend.py`, `apps/twinpulse-web/src/App.tsx`, 기존 installer/회사 안내 문서.

1. Isaac import/SimulationApp 생성보다 먼저 stdlib 기반 startup reporter를 설치한다. 단계·시각·exit code·최초 관련 오류를 제한된 크기로 기록한다. native crash는 부모가 감지한다.
2. backend ready 후 UI를 열고 엔진 준비를 비동기로 표시한다. engine 실패 시 읽기/진단 기능은 유지하되 실행은 차단한다. backend 실패는 launcher 요약으로 안내한다.
3. cancel/retry/정상 종료를 소유 프로세스 lifecycle에 연결한다. 이전 엔진 종료 확인 전 재기동 금지, 잔류 job/lock/늦은 ready가 새 실행을 오염하지 않게 한다.
4. 평상시에는 빠른 경로/구성 fingerprint 검사만. 최초/변경/실패 시 상세 native provenance·필요한 SimulationApp smoke. 매번 두 번 부팅하는 사전검사는 만들지 않는다.
5. RuntimeProfile(설치 조합/관측된 로딩 경로)과 EngineCapabilities(기능 계약), readiness(현재 상태)를 분리한다. App venv와 Isaac vendor 환경을 유지하며 Lab은 해당 기능에만 요구한다.
6. allowlist 진단 export: 첫 원인+bounded log+최소 버전 정보. key/token/회사 사진/전체 환경 덤프 제외. NumPy 버전 강제/폴더 자동 교체 대신 근거 있는 복구 선택 안내.

**시험**: 초기 import 예외, SimulationApp 예외, hard exit, 살아 있는 hang, warning-only 정상, backend 실패, 초기화 취소, 재시도 중복, 거대 로그, 민감정보 제거. 가짜 프로세스 시험 후 실제 기존 로컬 Isaac의 정상 startup/종료와 UI를 확인한다. 회사 조합은 현지 증거 전 미검증.

**완료**: 엔진 실패에도 이유와 다음 행동이 화면에 남고 정상 시작이 회귀하지 않음. “timeout 증가”만으로 닫지 않는다.

## 6. P2 — 실제 사용자 방의 지속 프로젝트 흐름

**대상**: app의 `project_store.py`, `project_catalog.py`, `room_recipe.py`, `bedroom_twin.py`, `bedroom_review.py`, backend API·App·`BedroomTwin.tsx`, 기존 launcher/adapter.

1. 프로젝트/장면/객체/자료 ID와 geometry revision·view revision·evidence revision 참조를 정리한다. 한 project.json에 모든 원본을 뭉치지 않고 기존 저장소의 참조 구조를 확장한다.
2. App 새 프로젝트→방 사진/저장 recipe 가져오기→검토→Burger 표시→저장·재열기를 연결한다. 빈 레코드 허용과 실제 기존 자산 덮어쓰기 거절을 구분하여 `prepare_project_burger_visual` 연결 결함을 해결한다.
3. 날짜별 고정 사용자 방 fixture는 회귀 기준으로 보존하고, 제품은 그 자료를 명시 가져오는 프로젝트 데이터로 읽는다. 다른 방도 같은 경로 사용.
4. active project를 UI만 바꿔 전환하지 않는다. 작업 종료·저장 상태 확인→owned backend/engine 조정→새 project 연결→ID 일치 확인을 하나의 앱 동작으로 제공한다. 실패하면 이전 저장 자료 유지, 실제 활성 ID 명시.
5. 재시작은 draft와 자료만 복원한다. 실행 중 job/lease/실물 승인/과거 readiness는 복원하지 않는다.

**시험**: 사용자 방과 두 번째 합성 방을 각각 생성·열기, 사진/자산 hash 변조·누락, 중복 ID, 빈 레코드, 부분 저장 실패, 전환 취소/중간 실패, 재시작. actual App→bridge→Isaac→USD 재열기에서 Burger와 객체 ID/pose를 확인한다.

**완료**: CLI 작업 없이 실제 사용자 자료로 O1 흐름을 끝까지 수행. 치수/pose는 추정으로 표시하며 기본방 원본과 다른 프로젝트 자료가 그대로 남음.

## 7. P3 — 새 환경·추가·변경의 비파괴 계약

**대상**: core의 `site_contracts.py`/`site_tools.py`와 versioned change-set, app application/project 경로, compiler `compile_site_scene`, provider 문맥, App 검토 UI.

1. 첫 빈 화면 기본은 새 환경. 기존 장면에서는 추가를 기본 제안한다. 기존 live/offline/replay와 저작 모드를 분리한다.
2. `SceneChangeSet` envelope: project/scene/base revision/operation ID, intent, add/update/delete, 근거·예상 fingerprint. 기존 v1/v2 plan 직렬화·golden hash는 변경하지 않는다.
3. 추가는 새 객체만, 변경은 대상 ID/허용 속성만, 새 환경은 이전 장면을 보존한 새 revision/분기. ‘창가로 이동’의 대상/좌표가 불명확할 때만 필요한 질문을 한다.
4. 전후 미리보기→한 번 적용→실제 receipt→Undo/재열기. 서버가 기존 객체 보존을 검사한다. 중복 operation은 재생성하지 않고 동일 결과를 반환한다.
5. stage/저장 양쪽의 실패를 처리한다. 중간 실패 원상복원, 복원 실패는 불명 상태로 남김. 외부 prim·PhysicsScene 보존. 실행 중 geometry 편집과 job 수명을 조율한다.
6. geometry 변경 시 기존 경로·보정 참조를 stale로 표시한다. 시각 재질/보기 변경과 기하 변경을 구분한다.

**시험**: 침대 이동 시 책상 불변, 소파 추가 시 기존 전체 객체 불변, floor/ID 중복, stale base, cancel/late response, Undo·저장/재열기, 외부 stage prim, apply/rollback 실패. 실제 Isaac에서 ID·transform·재질·PhysicsScene·비대상 subgraph를 대조한다.

**완료**: 자연어 요청이 기존 장면 전체 교체로 흘러가지 않음. 화면 메시지와 실제 receipt가 일치함.

## 8. P4 — 읽기 쉬운 기본 보기와 편집 후 화면 보존

**대상**: compiler `_ensure_presentation`, 기존 engine typed command/adapter, App 3D 보기 패널.

1. 기본 보기/실내/장면 조명, 밝기, 화면 맞춤, 보기 초기화, 위/사선 시점을 제공한다. 설치된 Kit API를 확인하고 지원되지 않는 기능은 이유를 표시한다.
2. 고정 camera reset 대신 현재 장면 bounds 기반 첫 framing, 이후 사용자 시점 보존. 벽/천장으로 내부가 가리면 보기 전용 단면/숨김을 사용하며 collider는 삭제하지 않는다.
3. 보기용 lighting/exposure와 실제 장면 조명을 분리한다. 비교 실험의 렌더 설정은 고정 저장한다. 현재 고정 intensity를 무작정 낮추는 패치로 끝내지 않는다.
4. 공간 맥락과 관계없이 보이는 창고 rack 일러스트도 바꾼다. 로딩 예시 그림과 실제 장면 결과를 혼동시키지 않는다.

**시험/완료**: 방·창고·작은/큰 scene·밝은/어두운 재질 actual Isaac 캡처. 극단적 흑/백 clipping, 가림, Burger 식별을 통계와 육안으로 검토. append/edit 뒤 camera 유지, 보기 조절로 geometry·실물 권한 불변. 상세 미관을 끝없이 늘리지 않고 가독성이 확보되면 P5로 진행.

## 9. P5 — 프로젝트별 명령·관측·임무 기록과 재생

**대상**: app `physical_controller.py`, `session_journal.py`, `session_history.py`, `bedroom_rehearsal.py`, backend/React 이력·비교, 기존 robot event 계약.

1. 프로젝트/scene revision/robot profile/boot/release/session ID를 실행 시작의 불변 문맥에 묶는다. 기존 global 로그는 소급해 임의 프로젝트로 옮기지 말고 원래 범위를 표시하거나 명시 참조로 가져온다.
2. 입력 의도→PC 전송→로봇 수락→출력→관측→판정/종료를 구분한다. 원래 clock domain·시각·sequence를 유지하고 동기화 근거 없이는 PC/robot 시간을 단순 빼지 않는다.
3. 명령 적분으로 예상한 이동과 odom/관측 이동을 분리하여 화면에 표시한다. 관측 없는 구간은 빈칸/unknown; 명령만으로 ‘실제로 이동함’ 판정 금지.
4. 수동 입력 release와 세션 종료 구분, WASD/IME·포커스·blur·hold 만료 회귀를 포함한다. 유효한 수동 세션에서 매 입력마다 체크박스/재연결을 요구하지 않는다. 실제 만료/연결 상실 뒤 자동 재활성화는 하지 않는다.
5. 프로젝트별 타임라인·JSON export·Twin 재생을 연결한다. continuous replay를 구현하면 sample 간 보간은 표시용임을 명시하고 gap을 실제 관측으로 채우지 않는다. seek 기능만 있으면 continuous 완료로 쓰지 않는다.
6. 동일 scene/start/goal/profile/센서 및 policy 조건을 manifest로 묶어 경로·시간·거리·정지 이유를 비교한다. 충돌 미측정은 null, 목표 미도달 결과는 도달 결과와 단순 효율 승패로 비교하지 않는다.
7. bounded journal 저장·flush 실패·부분 tail·disk full·process 중단을 기존 내구성 계약에 연결한다. 손상 원본은 보존한다.

**시험/완료**: 두 프로젝트/두 세션 교차조회 차단, 현재 default 경로 호환, 실제 저장 로그 재읽기와 합성 로그 별도 표시, 재생 pose/시각과 원본 일치, JSON 다운로드 바이트/hash 재검사. 로봇 접속 없이 O2가 작동하며 가짜 자료를 실측으로 승격하지 않음.

## 10. P6 — 연결 한 번으로 점검·수집 준비, 불필요한 반복 제거

**대상**: 기존 backend connection/diagnostics 경로, `RobotDiagnostics.tsx`, `RobotReport.tsx`, `PhysicalRobotController.tsx`, app `physical_controller.py`, robot `teleop_worker.py`/`teleop_ros.py`의 오프라인 fake 경로.

1. `연결·준비` 내부에 PC 실행파일/구성/패키지/인증 경로 확인을 통합한다. 캐시가 유효하면 저비용 재검사만 한다. 사용자에게 PC 점검 버튼을 별도 필수 단계로 요구하지 않는다.
2. state machine: 연결 전→상태 수집→필수 자료 부족/준비 가능/오류. 사용자에게 첫 원인과 다음 한 가지 행동을 보인다. 센서 프로세스가 꺼진 `NO_SENSOR_DATA`를 통신 실패/장치 고장과 구분한다.
3. 수집 계약에 boot/release/profile, 전압·측정시각, motor 상태, odom/TF/scan 원 frame·시각·관측 주기·누락, 명목/실측 차체 근거를 넣는다. 전압 추정 잔량은 용량 실측으로 표시하지 않는다.
4. 유효한 정지 qualification을 boot/release/profile/관련 설정·정책과 결속하여 재사용 조건을 명확히 한다. 만료/변경/불일치 때만 재시험을 요구한다. 무효 결과를 과거 PASS로 덮지 않는다.
5. 연결 자체는 이동 명령을 보내지 않는다. 읽기 점검과 센서 시작·수집/움직임이 필요한 qualification은 상태·행위를 구분한다. 필요한 능동 단계는 이후 승인된 준비/시험 또는 임무 범위에 포함해 실행하도록 설계하며 매 tick 승인을 요구하지 않는다.
6. 자료 수집은 bounded 세션과 완료 manifest로 저장한다. 다음 현장 접속 시 어떤 자료가 충분하고 부족한지 자동 보고하도록 PC에서 fake end-to-end를 검증한다. 네트워크 재시도도 상한·취소·중복 방지를 적용한다.
7. ‘시뮬레이션 가능 / 저장 재생 가능 / 실물 자료 부족 / 현물 준비 확인’은 각각 표시한다. 연결 버튼 성공과 실물 자율 임무 가능을 동일시하지 않는다.

**시험**: robot OFF/접속 실패, 잘못된 인증/host 불일치, 센서 미시작, stale scan, 누락 TF, boot/release 변경, qualification 재사용/무효화, 수집 중 단절/취소/저장 실패, 준비 완료 응답 지연. 실제 SSH·serial 대신 주입 fake만 사용한다.

**완료**: 한 번 연결 동작에서 수집·판정·안내가 끝나며, 추가 클릭은 실제 필요한 행위에만 남는다. 로봇 OFF에서도 다음 수집 코드/화면/시험은 준비되어 있음. 실제 준비완료는 NOT_VERIFIED.

## 11. P7 — 방 목표→임무→장애물 대응→Twin 결과

**대상**: core `room_goal.py`, `navigation_binding.py`, `mission_contract.py`, `local_navigation.py`; app `robot_geometry_evidence.py`, `bedroom_review.py`, `bedroom_rehearsal.py`, `physical_controller.py`; robot `mission_runtime.py`/`teleop_ros.py`; `BedroomGoalReview.tsx`와 임무 화면.

### P7a 좌표·목표·범위 결속

- UI 목표를 project/scene/geometry revision·frame·footprint·calibration evidence와 묶는다. 기존 후보 검토를 verified calibration과 분리하여 후속 정식 입력 계약/검증/mission loader까지 연결한다.
- synthetic/replay/physical 실행원을 분리한다. 합성 환경의 명시 변환으로 모의 임무를 시험하되 현재 실제 방 변환은 자료 없으면 계속 거절한다. 사진 방향/명목 URDF만으로 measured TF를 발급하지 않는다.
- 한 번 선택한 임무 범위(목표/영역/기한/속도/중단 조건) 안에서는 이동·회전마다 사용자 승인을 묻지 않는다. 저장된 승인으로 다음 세션을 자동 시작하지 않는다.

### P7b 장애물 대응·재계획

- 경로 계획과 최종 local command guard를 분리한다. planner가 경로를 제안해도 각 출력은 최신 scan/pose/frame/명령 나이/footprint/기한 검사를 통과해야 한다.
- 현재 `local_navigation.py`는 전체 scan의 최소거리 기반 원형 clearance라 가까운 옆 장애물 때문에 모든 이동이 막힐 수 있다. 먼저 이를 fixture로 재현하고, 방향별 swept footprint/회전 envelope 등 더 정확한 검사 필요성을 평가한다. 단순히 거리/정지시간 기준을 낮춰 우회시키지 않는다. 변경 시 명시 정책 revision과 이전 경계 회귀·반례 검증을 남긴다.
- 장애물 발견→안전 정지→유효한 관측에 기반한 bounded 재계획→허용된 경로만 재개. 미관측 공간은 free로 가정하지 않는다. 경로 없음·좁은 틈·deadlock·기한 초과는 명확히 종료한다. 무한 재시도/진동 방지.
- 동적 장애물·센서 지연·scan 부분 결손·pose 점프·단절·취소를 local loop에서 처리한다. PC/LLM 응답을 기다리는 동안 마지막 이동을 무기한 유지하지 않는다.
- 일반 정지는 현재 허용 구간 잔여 이후 새 이동을 막고 정지한다. 강제 STOP/Esc는 대기 명령과 현재 실행을 가능한 즉시 취소하는 최우선 경로로 유지한다. 우회/재계획이 STOP을 취소하거나 자동 재개하지 못한다. 실제 제동거리/부하 감소 보장은 현물에서만 확인한다.

### P7c 검증 층위와 평가

1. 순수 core/fake: 목표 도달, 우회 성공, 경로 없음, unknown 공간, delay/단절, 목표 변경, 두 정지·재계획 경합. 판단과 모든 출력/관측을 P5 로그로 저장.
2. 실제 App+fake transport: 버튼→임무 범위→loop→상태→정지→이력까지 실행. 금지 transport 호출은 0이어야 한다.
3. 실제 Isaac: 우선 기존 지원 profile과 명시 collider로 동역학/접촉 시험 가능한 경로를 확인한다. 기존 Burger visual mesh만 움직인 재생은 physics 검증이 아니다. 동일한 소프트웨어 판단 계약을 adapter로 연결하고 로봇과 닮은 외형만으로 물리 동등성을 주장하지 않는다.
4. contact 측정이 있는 시뮬레이션에서 충돌 감점·거리·시간·목표 도달을 분리 평가한다. 실제 물리시험을 못 하면 `PHYSICS_NOT_RUN`으로 남기며 점수는 지어내지 않는다. 실물 정책은 감점과 별개로 충돌 예방 우선.

**완료**: O4의 모의 경로와 실패 처리가 제품에 연결됨. 어떤 시험이 deterministic 2D/fake이고 어떤 것이 actual Isaac physics인지 구별한 증거 확보. 실제 센서 정합·배포·실물 임무는 미검증 및 잠금 유지. physics 필수 증거가 없으면 P7 전체 VERIFIED가 아니라 부분 완료로 보고.

## 12. P8 — 공간별 가구와 변경 결과를 설명하는 대화

**대상**: core ToolCatalog/site tools/composite, provider `nebius_pipeline.py`와 기존 adapter, app generation context/recipe/asset manifest, compiler 표시 모델, React 대화·선택/변경 패널.

1. 주거/창고/사무실/혼합/불명 문맥과 사용자 명시 요구를 적용한다. 한국어 입력만으로 한국형 아파트를 확정하지 않으며 지역/스타일은 수정 가능한 가정이다.
2. 1차 가구는 침대·옷장·책상·의자·소파·식탁·수납장과 기존 rack/pallet. 기존 로컬 자산 또는 유한 parametric composite로 실제 구별 가능한 형상을 만든다. 인터넷 전체 자산 탐색·새 외부 다운로드는 선행하지 않는다.
3. category/style/치수·단위·축·pivot/asset hash·revision/출처·라이선스/시각형상/충돌 envelope/검증상태를 등록한다. 선택한 자산을 저장하고 재생성 때 랜덤 교체하지 않는다. 모르는 물체는 이름 붙인 단순 대체 모델로 안내한다.
4. 기존 장면·선택 ID·작업 모드·가용 catalog를 provider 문맥으로 제공한다. 현재 v1/v2 호환과 strict 검사 유지, 새 필드는 versioned 계약으로 도입한다. 모델 임의 코드·shell 실행 금지.
5. 이해한 요청·가정·실제 조회한 자료·예정 변경을 먼저 설명하고, 적용 후 실제 receipt로 결과를 말한다. fake/저장 provider 재생은 그 출처를 표시한다. 자료 조회 없이 ‘한국 아파트 데이터를 가져왔다’고 출력하지 않는다.
6. 실패/가구 없음/모호한 대상을 짧은 다음 선택으로 제시한다. 매 치수마다 승인받는 UI나 단순 설명문만 늘리는 구현은 피한다.

**시험/완료**: 사용자 방/일반 아파트/창고/혼합/불명 사진 fixture에서 적합한 도구·보존·대체·설명 검사; 실제 Isaac에서 가구 형상·재질·크기와 Burger 가림 검토. fixture PASS와 실제 유료 모델 의미 품질은 별도. 이번 오프라인 범위에 새 유료 모델 평가를 넣지 않는다.

## 13. P9 — 전체 리허설과 최종 인수 묶음

**리허설 A: 사용자 방 + 임무**

`App 시작 → 사용자 방 프로젝트 → 사진/recipe와 Burger → 기본 보기 → 목표 → 합성 좌표 근거 표시 → 모의 임무 → 일반 정지 → 새 명시 실행 → 장애물 우회/우회 불가 → 강제 STOP → 명령/관측 결과 → Twin 재생·비교 → 저장/종료/재열기`

**리허설 B: 주거/창고 저작과 프로젝트 분리**

`새 환경 → 주거 가구 → 소파만 추가 → 침대만 변경 → Undo → 저장 → 창고 프로젝트로 전환 → 다른 세션 기록 확인 → 원래 방 복귀`

**리허설 C: 고장과 복구**

`엔진 시작 예외 → 진단 UI 유지 → 원인/최소 자료 export → 명시 재시도 → 정상 준비`, 그리고 편집 실패/저장 실패/미완료 로그/늦은 응답/센서 지연/boot 변경을 실제 앱 fake 경로로 재현한다.

### 최종 통과 체크

- [ ] O1–O5와 I1–I4 각각 실제 UI/소스/시험/증거 링크가 있고 누락 없음.
- [ ] 기존 v1/v2/hash·default/named project·외부 prim·정지/기한·과거 실패 이력 회귀 통과.
- [ ] 같은 source/build fingerprint로 Python·React·build·제품 E2E·actual Isaac 결과를 묶음. 서로 다른 빌드의 결과를 하나의 PASS로 합치지 않음.
- [ ] 실제 사용자 방 데이터 경로와 두 번째 프로젝트 모두 저장/재시작 후 이어짐.
- [ ] 실제 browser 화면/키보드/JSON export와 actual Isaac 캡처·USD/필요한 physics 증거 확인. headless 통과만으로 GUI 가독성 통과 선언하지 않음.
- [ ] engine cold/warm 시작, 연결 fake, import/reopen, 편집 적용, STOP 처리의 측정 구간·환경·관측 지연을 기록. 구체적인 성능 기준은 P0에서 고정하고 실패 뒤 완화하지 않음.
- [ ] 매 임무 내부 명령별 사용자 승인 없음. 연결이나 재열기로 실제 이동 자동 시작 없음.
- [ ] 새 로봇 접속/센서/모터/배포·유료 호출 0, mock/저장/합성과 실측 구분.
- [ ] 회사 PC·현물에서만 남은 항목 및 실행 순서를 한 페이지로 전달.

통합 보고서는 ‘전체 완료’ 한 단어 대신 **오프라인 제품 흐름 / actual Isaac 시각 / actual Isaac physics / 새 실제 모델 품질 / 회사 환경 / 실물**을 별도로 판정한다. 해당 증거가 부족하면 그 부분만 PARTIAL/NOT_RUN으로 남긴다.

## 14. 현장에 남기는 일과 앱에서 준비할 안내

1. 현재 배터리/boot/release와 연결 상태 수집. 기존 qualification이 유효한지 자동 판정.
2. 실제 TF/odom/scan 시각·방향·신선도, 차체/센서 장착·방 미터 대응 근거 수집과 정합. 이미 있는 원본을 다시 요구하지 않고 부족한 자료만 안내.
3. 승인된 새 배포가 필요하면 버전과 이유를 표시. 오프라인 구현이 로봇에 적용된 것처럼 말하지 않음.
4. 필요한 경우에만 bounded 정지/저속 시험 후 현재 release의 결과 저장. 유효한 같은 조건 시험을 매 입력마다 반복하지 않음.
5. 임무 범위 승인 후 자율 실행·장애물 대응·정지·로그 재생 확인. 로봇을 켜기만 하면 완료된다고 보장하지 않음.

## 15. Sol 작업 규칙·재개 체크리스트

- 작업 시작 시 현재 AGENTS/Memory와 본 문서의 마지막 상태표를 확인한다. **계획을 다시 늘리는 대신 현재 미완료 최소 제품 흐름을 구현·시험**한다.
- 하나의 하위 작업은 코드→관련 테스트→기존 제품 연결→증거→Memory/Baseline 갱신 순. 문서/CLI/fake 모델만 추가하고 App 연결을 뒤로 미루지 않는다.
- 각 증분 기록: 요구 ID, 수정 파일, 재현/원인, 시험 명령·exit code·범위, artifact/source hash, 실패·NOT_RUN, 다음 미완료 단계. 실제 실패도 보존한다.
- 내부 모듈 이름은 위 대상이 출발점이지 확정 API가 아니다. 구현 시작 시 실제 서명을 확인한다. 새 DB/새 플랫폼/시뮬레이터 재작성보다 기존 adapter/store/compiler를 재사용한다.
- 기존 dirty 변경·원본·과거 결과 보존. 설치/삭제/시스템설정/유료 API·클라우드/commit·push/타 프로세스 종료/실물 접속·배포는 포함하지 않는다. 권한이 없으면 요청하고 우회하지 않는다. 새 에이전트/채팅도 만들지 않는다.
- robot transport는 fake 주입 경로로만 시험한다. 관련 준비 코드 작성과 실제 실행 승인을 구분한다. 실제 환경 검증이 막혔다고 실물 잠금·검증 기준을 낮추지 않는다.
- 사용자 부재 중 진행은 후속 승인된 범위에서만. 기존 잘못된 날짜를 새 마감으로 사용하지 않는다. 새 예약은 명시 일정 지시가 있을 때만 만든다.

### 구현 지시용 문구

> `C:\Users\jaewo\Documents\TwinPulse`의 AGENTS.md, 최신 PROJECT_MEMORY/BASELINE과 `docs/planning/TWINPULSE_INTEGRATED_OFFLINE_SOL_WORKPLAN_2026-09-29.md`를 읽고, P0부터 현재 미완료 단계의 오프라인 구현·검증을 진행해라. 이미 완료된 것은 증거로 확인해 재사용하고 P1→P9의 의존 순서를 따른다. 로봇 없는 기존 작업 O1–O5와 개선 I1–I4를 모두 기존 App/Isaac 제품 흐름에 연결해라. 단계마다 단순 진행 승인을 다시 묻지 말고 코드·회귀·인수 증거·Memory/Baseline을 함께 갱신해라. 로봇 접속/배포/실물, 유료 호출, 새 설치·시스템설정, commit/push, 새 에이전트는 하지 마라. 환경/권한 때문에 못 한 시험은 NOT_RUN으로 남기고 독립 작업을 계속해라. 최종 보고에서는 오프라인·Isaac 시각·Isaac physics·회사 환경·실물 검증을 분리해라.

이 인용문은 사용자가 구현자에게 전달할 지시 초안이며 이번 계획 작성 턴에서 자동 실행하지 않는다.

### 진행표 (초기 상태와 2026-09-29 12:40 갱신)

| 단계 | 현재 상태 | 다음 행동 |
|---|---|---|
| P0 | 원본 사진 2개/Burger USD/합성 scan SHA 고정·불변 재확인 | 전체 인수 성능 기준의 별도 측정값은 미설정 |
| P1 | PARTIAL: 조기 import 오류 보고·읽기 진단/다운로드·명시 재시도 새 소유세션·시작 취소, 고의적 실패→기존 로컬 Isaac ready PASS | 회사 PC 동일 원인 재현·운영환경 복구 UX 검증 |
| P2 | PARTIAL: 보존 방 새 named project·기존 프로젝트 바이트 보존·owned Isaac 전환/검토 재개 실제 Chrome PASS | 임의 사용자 사진/recipe 입력, 프로젝트별 기록·완전 재열기 QA |
| P3 | PARTIAL: 저장 v2 장면에 새 전체 생성 거절·App 잠금 | versioned change-set 기반 Add/Change/Undo·원자 저장/rollback·비대상 보존 |
| P4 | PARTIAL: 사용자방 열린 경계 authored 카메라/완화 조명·실제 Isaac viewport 시각 확인 | 가구 다양성, Stage Light/Light Off 및 GUI 사용자 가독성 검토 |
| P5 | 기존 global journal/재생 PARTIAL, 이번 통합 수용시험 미완료 | project-local 참조·명령/관측·비교 연결 |
| P6 | 기존 일부 연결/PC 점검 통합 PARTIAL, 새 실물시험 없음 | 수집·qualification 유효성·다음 행동의 단일 흐름 |
| P7 | 기존 합성 임무/guard/좌표 후보 PARTIAL, 실제 physics·TF 미검증 | 목표 결속·재계획·physics 범위 검증 |
| P8 | 기존 box/창고 도구 기반, 제품 다양성 미수용 | 가구 catalog/composite·대화 receipt |
| P9 | 이번 전체 통합 인수 미실행(서로 다른 부분 E2E 별도 PASS) | 동일 빌드 전체 리허설, 회사 PC·실물 별도 |

### 2026-09-29 11:19 KST 실행 체크포인트

- P0 기준 원본 SHA 기록, P1 startup reporter/읽기 진단/명시 재시도·시작 취소, P2 빈 프로젝트·보존 사용자방 복사/새 소유세션 전환, P4 사용자방 floor-fit/완화 authored 조명까지 부분 구현. 자세한 코드·실패·회귀는 [동일 날짜 검증](../verification/integrated-p0-p2-startup-20260929.md)에 둔다.
- 최신 전체 오프라인 `20260929-integrated-startup-cancel-r1` core176/Web135/build PASS, Isaac NOT_RUN. 별도 named 사용자방 Isaac Build와 camera/light metadata PASS이나 managed headless viewport 캡처는 FAIL이다. 수치상 시험 통과를 GUI 가독성·회사PC·실물 검증으로 승격하지 않는다.
- P1/P2/P4 **PARTIAL**, P3/P5–P9 미완료. 특히 P3의 추가/변경·Undo와 임의 방 입력을 안전하게 잇는 데이터 계약은 아직 제품에 없다. 기존 App의 장면 재생성 경로를 비파괴 변경 기능으로 소개하지 않는다.

### 2026-09-29 11:48 KST 후속 체크포인트

- P1 읽기 전용 진단·재시도·취소·연결실패 시 조작잠금, P2 보존 사용자방 새 프로젝트·소유 런처 전환, P3 기존 저장장면의 새 전체생성 차단, P4 열린 저작 경계 보기까지 제품 경로에 부분 연결. 상세 실패/수정/실제 화면 캡처는 [통합 검증](../verification/integrated-p0-p2-startup-20260929.md) 참조.
- 최종 오프라인 전체 `20260929-integrated-open-side-final-r2` core176/Web137/build PASS, Isaac suite NOT_RUN. 별도 실제 Isaac 프로젝트전환 r3/사용자방 카메라 r2/다른 합성방 r1은 PASS. 연결 단절 시 stale ready로 Build가 열린 실제 캡처 r1과 벽 가림 초기 캡처 r1은 **실패 증거로 보존**. 사진/모델/합성scan 원본 해시 불변.
- 다음 의존 단계는 P3 정식 `Add`/`Change` 변경집합·대상/비대상 보존·미리보기/확정·Undo와 재열기 일관성이다. 현재 `ProjectRecord`의 site draft는 원 recipe의 결정적 확장·해시와 결속되어 있으므로 저장 JSON의 scene만 바꾸는 방식은 금지. 새 versioned derived revision/recipe 계약이 필요하다. 이 단계가 통과하기 전 P5–P9를 제품 통합 완료로 선언하지 않는다.
- 회사 PC 원인 재현, 사용자 임의 방 사진/가구 품질, Isaac physics, 실제 TF/scan/로봇 시험은 미수행. 사용자 로봇 OFF 보고, 접속·배포·유료 호출 0. 각 실물 gate는 별도 현장 승인까지 잠금 유지.

### 2026-09-29 12:11 KST 제품 경로 검증 보강

- 보존 사용자방의 새 프로젝트 만들기→새 소유 세션 열기→저장된 방 검토 재개까지 실제 Chrome/App/manager/Isaac에서 PASS(`20260929-project-switch-browser-isaac-r7`). 전환 전 기존 프로젝트 파일 바이트 불변, 이전 Build 승인/실물권한은 승계 안 됨. UI가 내부 작업을 대신 승인했다는 뜻이 아니다.
- 의도적인 로컬 Isaac import 실패 fixture에서 실제 backend와 Chrome이 진단 화면·allowlist JSON 파일 다운로드·명시 재시도 요청까지 PASS(`20260929-startup-failure-browser-r8`). 실제 새 엔진 재시작은 이 시험의 범위 밖이다. 원래 회사 PC DLL/패키지 문제의 원인 확인도 아니며 시스템 패키지 설치/교체는 하지 않았다.
- 실패 화면에서 창을 작게 했을 때 가로로 찢기는 오류 카드를 수정하고 데스크톱·모바일 캡처 검수. 엔진 오류 중 새 프로젝트/초안 작성 및 방/로봇 제어 진입은 UI에서도 잠금. 서버의 기존 mutation gate를 대체하지 않는다.
- 다음 구현은 계획대로 P3의 대상/비대상 보존이 검증되는 versioned change-set과 저장/Isaac rollback이다. P4의 Stage Light/노출·가구 다양성/P5 로그/P6 준비/P7 자율/P8 대화/P9 통합은 별도 증거 없이는 완료 처리하지 않는다.

### 2026-09-29 12:20 KST 동일 소스 검증

- 최신 App은 Isaac 시작중/오류 상태에서 read-only truth card와 설정 저장 잠금을 포함한다. 전체 `20260929-integrated-three-hour-source-final-r1`은 Python core176/Web137/build PASS, Isaac suite NOT_RUN.
- 같은 빌드에서 의도적 import 오류의 실제 Chrome/backend `20260929-startup-failure-browser-final-r1`과 실제 Chrome/App/owned Isaac 프로젝트 전환 `20260929-project-switch-browser-isaac-final-r1` 각각 PASS. 전자는 재시도 요청까지만 확인(새 엔진 재시작 NOT_RUN), 후자는 저장 프로젝트 바이트/권한 비승계를 확인했다. 서로 다른 범위를 합쳐 전체 데모 PASS로 기록하지 않는다.
- 다음 실제 구현 순서: P3 versioned non-destructive Add/Change/Undo 계약·미리보기/원자 적용·재열기/rollback → P4 실GUI 노출·카메라 사용자 검토 → P5 프로젝트별 명령/관측 세션 → P6/P7 연결·목표/자율 안전 → P8 가구/대화 → P9 동일 소스 통합. 회사 PC/실물은 별도 현장 증거가 필요하다. [최신 검증](../verification/integrated-p0-p2-startup-20260929.md).

### 2026-09-29 12:23 KST P1 재시도 경계

- `20260929-startup-failure-browser-retry-r2`에서 Chrome 재시도 요청→실패 manager 종료·lock 해제→같은 격리 runtime에서 다른 ID/남은 2회로 새 manager 시작까지 PASS. 새 엔진도 선택한 비-Isaac Python이라 의도대로 import 실패한다. r1 harness 실패 보존; 회사 PC 원인/정상 Isaac 회복은 미검증. [기록](../verification/integrated-p0-p2-startup-20260929.md).

### 2026-09-29 12:36 KST 마지막 제품 회귀

- standalone browser/bridge/Isaac 사용자방 화면 재현에서 `unmanaged` UI의 과도한 잠금 r1 FAIL 발견·현재 엔진 연결/snapshot 있는 장면만 허용으로 수정. 소유 런처 실패/시작중과 로봇·프로젝트 권한은 그대로 잠금. 실제 r2 Build/화면 PASS, 단순 형상이며 physics/실물 아님.
- 새 검증의 React139는 PASS였지만 전체 r2 TypeScript fixture 누락으로 FAIL 보존; 수정 후 전체 r3 core176/Web139/build PASS. 같은 빌드에서 시작실패 재시도 브라우저 r3와 소유 Isaac 프로젝트 전환 r2 각각 PASS. [증거/남은 범위](../verification/integrated-p0-p2-startup-20260929.md).
- 다음 구현은 P3의 versioned Add/Change/Undo 비파괴 변경/원자 저장/rollback이다. 기존 v2 SiteDraftRecord 결정적 plan/site hash를 우회하거나 재생성 경로로 저장장면을 덮어쓰지 말 것. P4 가구/조명 사용자 품질 검토, P5–P9/회사PC/실물은 미완료.

### 2026-09-29 12:41 KST 현재 최종 증거

- 독립 장면경로의 연결/snapshot에 현재 engine-session/stage 신원일치 조건을 추가하고 불일치 잠금 회귀를 포함했다. 전체 오프라인 `20260929-integrated-three-hour-source-final-r4` core176/Web140/build PASS, Isaac suite NOT_RUN.
- 같은 Web 번들로 실제 사용자방 Chrome→Isaac authored 화면 `20260929-authored-room-view-isaac-final-r3`, 고의적 import 실패→새 소유세션 재시도 `20260929-startup-failure-browser-retry-final-r4`, Chrome→owned Isaac 프로젝트 전환 `20260929-project-switch-browser-isaac-final-r3` 각각 PASS. 정상 회사PC/Isaac 복구, physics, 유료 모델, 실물은 이 증거가 아니다. 실패 r1/r2와 기존 물리 정지 FAIL은 보존. [검증](../verification/integrated-p0-p2-startup-20260929.md).

### 2026-09-29 12:47 KST 격리 정상 Isaac 재시도

- 브라우저의 고의적 import 실패 진단→명시 재시도→이전 owned 세션 종료·잠금 해제→기존 로컬 Isaac에서 새 owned 세션 `ready`까지 `20260929-startup-recovery-owned-isaac-r1` PASS. 변경 없는 비-Isaac 재실패 분기도 r5 PASS. 회사 PC의 원래 문제·동일 복구는 여전히 미검증. [검증](../verification/integrated-p0-p2-startup-20260929.md).

### 2026-09-29 12:54 KST 최종 source/checkpoint

- 재시도 양쪽 분기에서 새 authenticated browser bootstrap ticket 회전까지 검증한 로컬 Isaac-ready r2/비-Isaac 재실패 r6 각각 PASS. 마지막 전체 `20260929-integrated-three-hour-source-final-r5` core176/Web140/build PASS, Isaac suite NOT_RUN. [현재 판정표](../verification/integrated-p0-p2-startup-20260929.md).

### P3 구현 착수 전 계약 감사 (현재 코드 확인, 아직 구현 아님)

- `ProjectRecord` 2.0은 정확한 필드 집합의 단일 `site_draft`만 저장하고, `SiteDraftRecord.from_dict`는 원 `SiteToolPlan`을 다시 실행해 저장 `site`와 SHA를 비교한다. 그러므로 scene JSON만 직접 편집하거나 `ProjectRecord`를 묵시적으로 v3로 바꾸면 기존 재열기·해시가 깨진다.
- 특히 named 사용자방은 `ProjectStore._check_recipe`가 사진 바이트·recipe·저장 `SiteDraftRecord`의 결속을 재검사한다. `room_recipe.py`는 사진 기반 plan에서 측정 근거·구동 AGV/임무를 금지한다. 새 가구의 `user` 근거와 원사진 `visual` 근거를 혼동하거나 원 recipe/사진을 덮어써 변경을 표현하지 말 것.
- 기존 `DerivedSiteReview`/`DerivedReviewStore`는 원 v2를 보존하고 별도 sidecar를 원본 해시·재생 이력·derived revision에 묶어 원자 교체한다. 단 현재 `ScanReview`의 action은 기존 객체 보정, map overlay, Undo뿐이다. 사용자가 요구한 새 가구 Add와 특정 가구 Change를 이미 제공한다고 표기하지 말 것.
- 다음 최소 구현 단위: 별도 versioned `scene-change-set` sidecar에 `(project_id, input_revision, source_site_revision, parent_derived_revision, operation_id, mode, target_call_id?, typed_tool_call, expected_non_target_digests)`를 묶는다. `new`는 기존 프로젝트 ID가 아닌 명시 새 프로젝트 경로만; `add`는 새 call ID/객체 ID 충돌 거절; `change`는 정확히 하나의 기존 call ID/대상 집합만 교체. 매번 기존 `SiteToolPlan.from_dict` 검증과 `execute_site_tool_plan` 재계산(최대24 call/64 객체)을 통과하고, 기존 로봇/임무/비대상 객체의 canonical digest 불변을 검증한다.
- 미리보기는 원본·변경·비대상 diff와 추정/실측 근거를 표시하되 저장/Isaac 변이·승인을 하지 않는다. Apply는 미리보기 revision과 현재 source/parent를 재확인하는 CAS로 sidecar만 원자 저장하고 새 검토/ack/lease/Build identity를 요구한다. Undo는 과거 파일을 되돌려 쓰지 말고 부모 상태를 가리키는 새 derived revision으로 남겨 이력과 비교 가능성을 보존한다. 적용/저장 실패 때 현재 활성 revision과 원본 project.json/USD를 유지한다.
- 필수 실패 회귀: 중복 ID, non-target digest 변화, 원본 또는 parent stale, 동시 Apply, 저장 중단/재열기, v1/v2 기존 직렬화, 한 호출이 여러 객체를 만드는 도구, 24/64 상한, 외부 Isaac prim 유지, old review/build 승인 비승계. 실제 앱/브라우저→API→derived typed Build까지 통과 전에는 P3 완료가 아니다. 로봇/실제 TF/물리 충돌 등은 이 작업의 승인 범위가 아니다.

### P5 사전 데이터 경계 감사 (현재 코드 확인, 아직 구현 아님)

- 현재 `PhysicalController`의 `SessionJournal`은 저장소 전역 `artifacts/manual-control/<job>/session.jsonl`에 기록된다. `session_history.list_sessions/review_session`은 이를 bounded·checksum·시계순으로 읽고 명령 후 최대 0.5초 내 관측을 연결한다. 그러나 `control-session-1.0` 행에는 `project_id`/방 revision/robot profile binding이 없다. 기존 기록을 파일 위치만 보고 특정 방 프로젝트의 실측으로 자동 귀속하면 안 된다.
- P5 최소 안전 연결은 기존 JSONL 바이트/검증을 보존하고, 별도 versioned project-local **참조 인덱스**에 사용자가 선택한 job ID와 그 당시 project/room/scene/robot/release/boot identity를 기록하는 것이다. 로그 자체가 식별 근거를 제공하지 않는 과거 세션은 `unassigned_historical`로 남기고, 새 세션의 시작 시 identity를 기록하되 중간 전환·boot/release 변경은 세션 분리 또는 실패로 처리한다. Twin 재생은 명령·수락·관측·미관측을 그대로 표시하고, 실제 바닥 pose/충돌 증명으로 승격하지 않는다.
- 회귀: 다른 프로젝트의 job 조회 거절, 옛 global journal 읽기 호환, partial tail/불완전 종료 표시, command↔observation 시계/clock-domain 경계, 로그 변조/누락·동시 기록, scene revision 변동 시 재생과 현재 실행 권한 분리. 수동 기록과 자율 기록이 같은 evidence contract로 검토되기 전 P5 완료가 아니다.

### P1 남은 런타임 관측 경계

- 현재 `monitor_diagnostics`는 **초기 엔진 시작 실패** 때 backend를 남기고 재시도 요청을 받는다. 반면 이미 `ready`인 뒤 `monitor`가 엔진 종료·heartbeat 상실을 감지하면 오류 상태를 쓰고 반환하며, 런처의 `finally`가 backend까지 정리한다. 그러므로 초기 import 오류의 읽기 진단 PASS를 모든 사후 엔진 고장에 일반화하지 말 것.
- 후속 별도 수용시험: ready 뒤 owned Isaac의 비정상 종료·heartbeat 지연을 격리 fake/실로컬 경로에서 재현하고, 저장 프로젝트/로그가 온전한 채 사용자에게 원인과 안전한 재시작 동선을 제공하는지 확인. 현재 완료 범위의 쓰기/실물 게이트는 완화하지 않는다. 회사 PC 실제 고장 로그·패키지 지문이 확보될 때까지 근본 원인은 UNKNOWN으로 남긴다.
- 현재 실제 실패 카드의 데스크톱·모바일 캡처는 줄바꿈/버튼 가독성은 확보했지만 안내 문구가 영어다. 한국어 사용자용 원인·다음 조치 표시와 실제 회사 PC 스크린리더/작은 화면 검토는 별도 UX 수용 항목으로 남긴다. 단순 번역으로 설치 오류의 근본 원인을 해결했다고 표시하지 않는다.

### P6 사용자 흐름 감사 (현재 UI 확인, 미구현)

- 현재 `RobotDiagnostics`에는 `PC만 점검`과 이후 별도 읽기/갱신 흐름이 남아 있고, `PhysicalRobotController`는 제어 준비·정지시험·연결을 단계별 버튼으로 둔다. 사용자가 지적한 ‘전원을 켤 때마다 여러 번 수동 확인’ 문제가 앱 차원에서 사라졌다고 주장하지 않는다.
- P6는 로봇이 연결된 다음 한 번의 **읽기 전용 묶음 점검**으로 전압·boot/release·센서 신선도·기존 정지 qualification 유효 범위를 동시에 판단하고, 필요한 경우에만 변경/정지 시험 이유를 한 화면에 제시해야 한다. 최초 연결이 자동 설치·모터 활성화·주행 승인으로 이어져서는 안 된다. 배터리 %는 전압 추정임을 유지하고 보드 보호 조건을 우선한다.
