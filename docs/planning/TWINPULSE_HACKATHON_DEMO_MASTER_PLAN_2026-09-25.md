# TwinPulse — 영어 제품 UX와 최종 해커톤 데모 통합 수정계획

- **2026-09-27 로봇 작업 순서 갱신:** [로봇 종합 재검토 D0~D6](TWINPULSE_ROBOT_REVIEW_2026-09-27.md)와 [현재 상태](TWINPULSE_ROBOT_CURRENT_STATE.md)를 H3/H6 기반 작업의 최신 기준으로 사용한다. H2/H3 일부와 실제 제한 주행은 이미 진행됐으므로 아래 최초 NOT_STARTED 상태를 현재로 읽지 않는다. 통합 health V1/23검사/실물 읽기 보고서 완료; D1영구배포·한번에준비→D2정지계측→D3LiDAR/TF→D4App→D5scanTwin→D6navigation/비교 순서. 최종 사진→scan보정→경로비교→실물 목표와 H 전체 acceptance는 유지한다.

- 작성/검토: 2026-09-25 KST. 최신 실행 상태는 PROJECT_MEMORY를 우선한다. **통합계획 v2 — H0 검토, H1 로컬 검증, H2a 코어 계약, H2b 부분 연결, H2c actual Isaac headless tested scope PASS. H2 전체 PARTIAL**: live Nebius v2/사진 충실도/interactive viewport와 H2b legacy promotion은 미검증·미완료다. H3 이후는 미착수.
- H0 상세 결과와 Sol 작업 계약: [H0 검토·Sol 인수인계](TWINPULSE_H0_REVIEW_SOL_HANDOFF_2026-09-25.md). 사용자 의도 U1~U10, 코드 근거 F01~F11, 순서 보완 D1~D6, H1a 파일/검증/금지사항 및 migration 기준은 이 문서와 함께 따른다. H1a-1 [웹 로컬 검증](../verification/H1a-1-english-web.md), H1a-2 [설치 안내 검증](../verification/H1a-2-english-setup.md), H1b [상태 정합성 검증](../verification/H1b-web-state-truth.md)을 구분한다. 후속 권고는 별도 요청 시 **H2a부터** 수행하는 것이다.
- 기준 root: `C:\Users\jaewo\Documents\TwinPulse`. 소스 조회 HEAD: `5c42899a95a0bf2422550bd17df7556a92ab3232` + 현재 미커밋 변경. 재개할 때 실제 HEAD/diff를 다시 확인한다.
- 확정 방향: 로컬 웹 App + 별도 Isaac 3D 창; AGV가 포함된 현장 입력; TurtleBot3 Burger가 실물 데모 대역; 쉬운 영어 기본 제품·제출 자료.
- 문서 우선순위: 최신 사용자 결정 → Baseline/PROJECT_MEMORY → 이 통합계획 → 기존 S/R/B/O 세부 지침. H 번호는 해커톤 작업 묶음이며 기존 milestone을 재번호화하거나 PASS로 바꾸지 않는다.
- 이 문서의 최초 작성 범위는 수정범위 검토와 계획 갱신이었다. 아래 제안 설계와 사용자 확정사항을 구분한다. 현재 구현 상태는 상단 H1a-1 검증 기록을 따르며, 이후 단계는 사용자가 선택한 범위에서만 진행한다.

## 1. 최종 데모에서 보여줄 제품

영어 소개 문구 초안:

> Turn a site photo into a 3D twin. Update it with robot scans, test better routes, and measure the results on a real robot.

TurtleBot 소개 문구:

> TurtleBot3 Burger represents the AGV in this demo. The tests use TurtleBot-specific dimensions and motion limits.

이 문구는 완성 후 목표다. 현재 공개 설명에는 `Today`와 `Planned`를 나눠 현재 동작하는 사진→3D→제한된 시뮬레이션 구간을 정확히 표시한다.

### 사용자 흐름과 화면의 증거

| 단계 / 쉬운 영어 이름 | 사용자가 하는 일 | 제품이 보여줄 실제 결과 | 다음 단계 조건 |
|---|---|---|---|
| 1. Add Photo | AGV가 포함된 현장 사진과 선택적 설명, 알려진 치수 입력 | 원본 사진, AI가 관찰한 객체·관계, 추정/미확인 값 | 이미지·생성 결과 검증 |
| 2. Review Twin | 로봇 대역 프로필과 3D 초안을 검토하고 Isaac에 적용 | 별도 Isaac 3D, 실제 적용된 장면 버전, 사진과의 차이 | 장면 적용 성공; 스캔용 좌표·단위 준비 |
| 3. Update from Scan | 기록된 스캔 또는 연결된 TurtleBot 관측을 선택 | 겹쳐 본 scan/장면, 정합 품질, 변경 전후 장애물 위치 | 정합과 수정 검증, 새 버전 적용 |
| 4. Compare Routes | 동일 지도·출발/목표에서 기존/새 경로 시험 | 두 경로, 성공률·시간·거리·최소 여유, 반복별 결과 | 같은 조건 비교, 후보의 시뮬레이션 검증 |
| 5. Run Demo Robot | 현장 준비 후 검증된 후보를 실물 실행 | TurtleBot 실측 궤적·종료 이유, 기존/새 주행 비교 | 실물 전용 준비·정지 조건 및 현장 승인 |

현재 제품에 없는 3~5단계는 구현 전까지 숨기거나 `Not available yet`로 표시한다. 화면을 추가한 것만으로 단계가 완료되지 않는다. 주요 버튼은 한 단계당 하나를 우선하며 `Run in Isaac Sim`과 `Run Demo Robot`을 명확히 구분한다.

### 사진과 실물 실험장은 같은 공간을 나타내야 한다

- **권장 최소 데모:** TurtleBot을 AGV 대역으로 배치한 실제 실험장을 직접 촬영한다. 그 사진에서 초기 Twin을 만들고 같은 공간을 실제 TurtleBot으로 스캔한다. 사진 속 로봇이 산업용 AGV여야만 한다는 요구는 아니다.
- **선택 가능한 산업 사진 데모:** 공개 가능한 산업 현장 사진을 참고해 실물 축소 트랙을 만든다. 사진의 개략 재구성, 명시적 축척/배치 변환, 실제 트랙 사진·실측, TurtleBot scan을 각각 기록한다. 다른 장소의 scan을 원래 산업 현장의 실제 관측이라고 표시하지 않는다.
- TurtleBot이 AGV 역할을 대신한다는 것은 확정이다. 기하학적으로 정확한 축소 복제 여부와 트랙 치수는 아직 미정이다. 로봇의 질량·센서·구동 한계를 산업 AGV 축척으로 자동 변환하지 않는다.
- 창고 외 범용성은 별도의 비창고 실내 사진/합성 장면으로 검증한다. 하나의 대표 실물 실험장을 먼저 완성하고 여러 산업 도메인 전체를 동시에 구현하지 않는다.

## 2. 현재 구현과 결함·수정 범위

아래는 2026-09-25 소스와 기록을 읽어 확인한 범위다. 이번 문서 작업에서 runtime/유료 API/실물 시험을 새로 실행하지 않았다.

| 영역 | 현재 근거 | 수정 판단 |
|---|---|---|
| 사용자 언어 | `App.tsx`, `api.ts` 등에 한국어; 웹 소스 한글 포함 63줄(테스트 제외); `index.html`은 `lang=ko` | 단순 버튼 번역을 넘어 상태·오류·접근성 문구·설치 안내까지 영어 일관성 필요 |
| 제품 설명 | `Warehouse control room`, 창고 hero/default prompt, README의 constrained warehouse 정의 | 현장·로봇 중심 문구; 기존 창고 사례는 예제로 보존 |
| 실제 생성 | Nebius Gemma 관찰→Nemotron 도구 계획→local 검증, S3c 1개 live draft의 Isaac Build/완주 기록 | 재사용. 최신 overlap guard 이후 live 사진 충실도는 미검증 |
| 관찰/prompt | `nebius_pipeline.py`는 warehouse 관찰, compact generic robot과 +X mission을 고정 | scene-only/확인된 profile/명시 mission 계약 이후 prompt·schema를 함께 수정 |
| 도구 실행 | `scene_tools.py` registry가 로봇·task 하나를 요구하고 controller route 검증까지 수행 | 장면 검증과 주행 가능성 분리. 기존 local typed registry 유지 |
| 주행 | `motion_control.py::straight_route_command`, `resolve_current_controller_route`의 free +X corridor | 일반 경로 최적화가 아님. 새 모드에서 출발/목표를 바꿔 성공시키는 동작 금지 |
| 물리 로봇 | 카탈로그에는 generic 2WD+caster; 실제 TurtleBot profile 없음 | 실제 hardware revision과 공식 모델에 맞춘 별도 profile/센서/adapter 필요 |
| 스캔·보정 | 구현된 scan ingest/정합/수정 이력 UI 없음 | 데이터 계약, 정합·품질 판단, 부분 수정, 원본/새 버전 보존 필요 |
| 최적화·평가 | 제한된 직선 주행 수치와 일부 physics acceptance | Nav2 또는 검증된 동등 navigation, bounded 후보 탐색, 동일 조건 비교 필요 |
| 자동 관찰 | managed launcher, broker, browser/Isaac capture 및 저장결과 replay 있음 | 새 단계도 기존 자동 runner로 확장; 사용자 수동 screenshot에 의존하지 않음 |
| 배포 | online 설치와 offline release 전달 도구 존재, 로컬 일부 시험 PASS | 유지·최종 재검증. 회사 설치는 별도 현장 acceptance이며 데모 핵심 선행조건으로 두지 않음 |
| 계획 일관성 | 기존 S3c checkpoint는 live NOT RUN으로 오래됨; S6는 cloud 우선; S8/B9는 보정 비교 중심 | 과거 증거 보존 + 최신 재개 지점 표시 + 아래 H 단계/공정 비교로 정정 |

주요 재사용 파일:

- UI: `apps/twinpulse-web/src/{App.tsx,api.ts,types.ts,styles.css,App.test.tsx,api.test.ts}`, `apps/twinpulse-web/index.html`.
- 순수 계약/검증: `packages/twinpulse_core/src/twinpulse_core/{models.py,validation.py,scene_tools.py,robot_profiles.py,revisions.py,engine_contracts.py,draft_store.py,motion_control.py,acceptance.py}`.
- 서비스/API: `packages/twinpulse_app/src/twinpulse_app/{application.py,product_workflow_service.py,api.py,project_store.py,command_broker.py,settings.py,process_manager.py}`.
- AI: `packages/twinpulse_provider/src/twinpulse_provider/{nebius_pipeline.py,schema.py,contracts.py,service.py}`.
- Isaac: `extensions/twinpulse.extension/twinpulse/extension/{scene_compiler.py,runtime.py,isaac_adapter.py,bridge_client.py,extension.py,provider_settings.py}`.
- 자동 검증/배포: `scripts/{verify_app_e2e.py,verify_r5_web.py,verify_twinpulse.ps1,verify_s2d_managed_replay.py,twinpulse_engine_host.py,install_twinpulse.ps1,install_twinpulse_offline.ps1,build_offline_release.ps1}` 및 관련 tests.

새 scan/navigation 모듈 경로는 H0/H2에서 정하며 위 파일이 이미 새 기능을 제공한다는 뜻은 아니다.

## 3. 영어 UX 범위와 원칙

### 필수 범위

1. 제품 chrome: 제목, 메뉴, 단계, 버튼, empty/loading/success/failure, 파일 입력, placeholder, 표/차트, tooltip, aria-label/alt, 재시작/연결 상태.
2. 사용자에게 노출되는 backend/launcher 오류: 안정적인 error code→간단한 설명→다음 행동. 예외 문자열을 그대로 주요 메시지로 보이지 않게 하고 sanitized diagnostic은 `Details`에 둔다.
3. AI 요약: 영어 요약을 기본 요청하고 객체/오류 코드는 데이터로 유지한다. 한국어 입력·파일명·원본 OCR은 보존한다. 사용자 입력의 한글을 제품 번역 누락으로 오인해 거부하지 않는다. 유료 번역 호출은 필요 없다.
4. Isaac 보조 창: visible Extension 메뉴·modal·경고의 용어를 웹과 맞춘다. 기존 ASCII 글꼴 제약을 고려하며 한국어 legacy UI 추가를 필수로 하지 않는다.
5. 설치·시작·문제 해결 메시지, README/Quick Start/테스트 안내, 제출 스크린샷·영상 자막·설명·결과 보고서.

### 구현 기준안

- 영어 `en`이 첫 실행 기본값. 문구를 translation key로 분리하고 한국어 `ko`는 선택적 UI로 유지할 수 있게 한다. 한국어 toggle 출시는 P1이며 영어 제품 완성의 선행조건은 아니다. 기존 사용자 한국어 입력은 계속 허용한다.
- `document.documentElement.lang`과 locale을 맞춘다. locale 변경만으로 생성 입력 revision·API key binding·검토 승인·장면 상태가 바뀌지 않는다. 언어 변경으로 generation/API 요청을 재발행하지 않는다.
- 버튼은 짧은 동사 표현, 도움말은 한 문장 중심으로 쓴다. 내부 hash·receipt·lease·adapter는 `Details`에 둔다. 이 정보가 실제 검토에 필요하면 세부 화면에서 보존한다.
- 사용자-facing 용어는 `Photo`, `3D twin`, `Robot scan`, `Current route`, `New route`, `Scene version`, `Simulation`, `Demo robot`으로 통일한다. 새 경로를 항상 `Optimal`/`Best`라고 부르지 않는다.
- `AI key saved`는 key 보관 사실; `AI request succeeded`는 실제 검증 응답; `Scene ready to build`는 draft; `Scene built in Isaac Sim`은 actual receipt; `Simulation complete`는 해당 run 결과다.
- 예: `The robot moved too far from the route. Reset the simulation before running again.` 실제 복구 가능 행동과 상태에 맞게 쓰며 새 안전 승인을 locale 작업으로 추가하지 않는다.
- 표준 SI 단위 `m`, `s`, `m/s`, `%`를 표시하고 unknown은 `Not measured`/`—`로 표현한다. `0`으로 대체하지 않는다.
- 영어 원본 설치 안내를 `docs/QUICKSTART.md`로 제공하는 방안을 권장한다. 기존 한국어 회사 안내는 번역/특수 환경 보조 자료로 유지한다. 한국어 내부 계획 이력 전체 번역은 P0 범위 밖이다.

### 완료 기준

고정 문구·버튼·오류·안전·설치 안내가 영어로 연결되고, 1366×768/1920×1080 및 125% 배율에서 주요 버튼·경고가 잘리지 않아야 한다. 영어 generation→review→Build→Run/Pause/Reset, 만료 세션, 연결 끊김, 생성 실패를 검사한다. 기존 한국어 selector를 쓰는 browser runner/test를 함께 갱신한다. 의미 있는 상태/행동 테스트를 유지하고 번역 문자열 개수만 검사한 것을 UX PASS로 삼지 않는다. API 계약·물리 회귀는 문구 변경과 분리해 필요한 범위만 실행한다.

## 4. 유지할 구조와 확장할 계약

```text
English-first React UI
  → ApplicationService / persisted jobs
      ├─ Gemma observations → Nemotron allowed tool plan → local validator
      ├─ Scene / Robot / Mission / Scan / Evaluation artifacts
      ├─ scan alignment + reviewed scene update
      └─ typed job / command broker
          ├─ Isaac adapter → physics + sensors + captures
          ├─ navigation/evaluation worker
          └─ robot mission adapter → local Nav2/control + stop handling
```

**MCP 판단:** 현재 typed tool registry와 broker를 재사용한다. 외부 MCP 서버 신설은 이 데모의 필수 작업이 아니다. 고수준 작업마다 입력 schema·버전·읽기/쓰기 효과·실행 상한·job/receipt·취소·오류를 정의하면 이후 같은 계약을 MCP transport로 노출할 수 있다. scan 정합/경로 검증/모터 제어를 LLM의 자유 코드나 긴 chat loop에 맡기지 않는다. Nemotron의 실질 역할은 관찰 근거를 허용 장면 도구·배치 결정으로 변환하는 단계이며 요청/계획/Build 증거를 연결한다. 경로 후보 설명은 확장 가능하지만 최적화의 수치 판정은 실행 결과로 결정한다.

### 신규/개정 데이터 계약의 최소 필드 (설계 제안)

| 계약 | 주요 내용 | 무효화/소유권 |
|---|---|---|
| Scene revision | object stable IDs, shape/pose, 각 속성의 근거·단위·추정 여부, parent version | topology/pose 수정 시 새 version; 과거 run 보존 |
| Robot selection/profile | 사진 속 로봇 관찰 ID, demo profile ID/hash, 기구/센서·성능 상한 | 모델 외관 추정으로 물리 profile 생성 금지 |
| Mission | map/scene/profile hash, 동일 start/goal frame·pose·tolerance, controller capability, 허용 조건 | 임무 goal이 바뀌면 다른 실험; 자동 이동으로 성공 처리 금지 |
| Scan session | sim/recorded/real origin, sensor/profile/scene IDs, timestamps, frame/TF, 범위·관측 coverage, 데이터 hash | Replay/Observe는 physical command sink 없음 |
| Calibration/update | source/target frame, 명시 metric scale, SE(2), inlier/잔차/미관측, 변경 객체/속성, expected parent | 불충분·모호한 정합 거부; 원본에 atomic partial update |
| Evaluation batch | frozen scene/map/mission/profile/controller/config versions, seeds/repeats, baseline/candidate IDs, timeout | 취소/실패 포함; 바뀐 환경에서 이전 결과를 current로 쓰지 않음 |
| Run result | source sim/real, trajectory, success/termination, time/distance/clearance/contacts/개입, 측정 방법 | immutable; 미계측=null, 로그/캡처 동일 run 연결 |
| Approved robot mission | tested candidate/config hash, 실제 robot/map binding, 현장 승인/유효기간, rollback | Apply와 Start 분리; 연결 복구만으로 자동 재개 금지 |

모든 신규 persisted schema는 기존 SpecBundle/draft/engine/TS 계약과 migration/rejection 정책을 먼저 정한다. scan 원본·sensor trace·큰 영상은 Git 제외; sanitized 결과/fixture/schema만 버전 관리한다. 한 객체의 XY가 scan으로 보정돼도 기존 높이 출처를 scan으로 덮어쓰지 않는다. 하드웨어 목표 플랫폼/ROS 호스트는 B0 후 고정한다.

## 5. 실행 순서 — H0~H8

현재 H0는 `PLAN_REVIEW_COMPLETE`, H1a-1은 웹 단위/브라우저 PASS, H1a-2는 문구·문서 관련 회귀 PASS, H1b는 `WEB_UNIT_BUILD_MOCK_BROWSER_PASS / ACTUAL_ISAAC_NOT_RUN`이다. H2a는 [순수 core 계약·migration](../verification/H2a-contract-migration.md) 단위 PASS이며 H2b/c 및 H3~H8은 `NOT_STARTED`다. 기존 PASS 결과는 재사용 근거이지 새 H 완료 증거가 아니다. 예상 크기는 일정 보장이 아닌 상대 난이도(S/M/L)이며 L은 반드시 아래 하위 단위로 나눠 실행한다.

| 작업 | 크기 / 기존 단계 대응 | 선행·주 산출물 |
|---|---|---|
| H0 현재 기준·설계 검토 | S / S0 증거 재사용 | 이 계획과 실제 diff 대조, 모호한 결정/계약·checkpoint 정리 |
| H1 쉬운 영어와 기존 UX 정리 | M / R5/R6 | H0; 작동 중 3단계 영어 UI와 설치/오류 안내 |
| H2 장면·로봇·임무 분리 | L / S4, R7 | H0; scene-only build, capability-aware Run, version migration |
| H3 입력 충실도·데모 프로필 | L / S5a/c, B0/B5 | H2; 일반 현장 관찰·TurtleBot profile 및 input/track 관계 |
| H4 Scan→Twin 갱신 | L / S5b, R8/R9, B7 일부 | H2; virtual/recorded부터 정합→diff→apply/undo |
| H5 주행·후보 비교 | L / M5/M6, S8 일부, B6 | H2/H3, fixed updated map; navigation + bounded comparison |
| H6 TurtleBot 실물 연결 | L / S7, B0~B8 | hardware 단계별 gate; 관측→검증된 임무 적용 |
| H7 최종 통제 실험·데모 자동 기록 | M / S8, B9 | H4/H5/H6; 지도 개선/경로 개선/실물 재현 각각 측정 |
| H8 영어 제출·릴리스 | M / S9, O1/O2 유지 | H7 또는 명시한 축소 범위; 재현·영상·공개 자료 |

H1은 H2 이후 기능 구현 때까지 미룰 필요가 없다. H4의 합성/기록 입력 준비와 B0의 실물 inventory는 별도로 진척 가능하다. H5의 실제 Nav2/ROS 연결과 H6는 선택한 호스트 호환 확인이 필요하다. 이 의존성 표는 자동 multi-agent 실행 지시가 아니다.

H0 보완: B0와 bridge 호환성 점검은 H6까지 미루지 않는다. 첫 real scan은 B 안전 gate 뒤 운영자 입회 표준 mapping으로 수집하며 부정확한 photo Twin의 자율주행에 의존하지 않는다. H2에 scene에서 파생되는 NavigationMap의 버전·frame·unknown 계약을 포함하고, 비교 기준은 H5 구현 전에 고정한다. 상세 순서와 완료 기준은 H0 인수인계 3~6절을 따른다.

### H0 — Astra 검토와 재개 기준 고정

- 실제 HEAD/diff, 최신 live/build 기록, O1/O2 상태, 오래된 checkpoint를 대조한다. full regression을 단지 인수인계 목적으로 재실행하지 않는다.
- 이 문서의 신규 계약/최소 데모/단계 의존성/제출 범위를 검토하고 ADR에 남길 결정과 사용자 확인사항을 구분한다.
- checkpoint에 현재 planning 상태와 다음 실행 단계(H1a 권장)를 상단 명시하고 기존 S3c hash/시험 결과는 역사 기록으로 보존한다.
- **완료:** Astra의 승인/수정 의견, 우선순위, 다음 한 작업, 선택 대기 사항이 기록됨. 하드웨어·모델·비용을 추정으로 확정하지 않음.

2026-09-25 H0 검토 당시 결과: [H0 보고서](TWINPULSE_H0_REVIEW_SOL_HANDOFF_2026-09-25.md)의 보완 조건으로 방향 채택 권고. 당시 문서 검토만 완료했다. 이후 H1a-1 웹 검증은 [별도 기록](../verification/H1a-1-english-web.md)에 있다. 다음 Sol 작업은 별도 사용자 요청 시 H1a-2다.

### H1 — 영어 기존 UI 완성

**H1a 문구·언어 처리:** App/API 오류/HTML/설치 스크립트 visible text와 관련 테스트를 조사; 영어 사전·간단한 도움말·accessibility labels; 창고 default prompt는 비어 있는 설명 또는 일반 현장 예시로 바꿔 사진에 불필요한 두 랙/직선 조건을 주입하지 않음. 모델 system prompt 변경은 H3에서 schema와 함께 수행한다.

**H1b 사용성·상태:** current draft/applied scene/run status를 구분; provider key saved/live success를 구분; main action과 오류를 현재 화면에서 확인 가능하게 함. 고정 랙+움직이는 AGV CSS 그림을 live Isaac viewport처럼 보이지 않게 하며, 실제 캡처/trace를 쓰기 전에는 명확한 상태 도식으로 표시한다.

**검증/완료:** §3 영어 흐름과 failure 상태를 기존 UI/unit/browser harness로 검증; production build; 필요 최소 actual Isaac smoke로 의미 유지 확인. 새 LLM 호출은 번역 검증에 불필요. 한국어 locale은 이후 선택 가능하되 영어 사전은 지금 분리한다.

### H2 — scene/mission 분리와 자동 goal 변경 해소

**H2a 계약:** 기존 `SpecBundle`/engine 계약의 scene·robot·task 결합을 versioned 방식으로 분리. scene-only 수락과 `scene_valid/robot_compatible/mission_supported/run_allowed` 상태를 정의. 현재 직선 모드는 capability로 남긴다.

**H2b wiring/migration:** registry→ApplicationService→store→broker→Isaac→TS/UI 연결. `resolve_current_controller_route`의 편의 경로 재배치는 legacy/sample로 명시하거나 사용자가 확인한 제안으로 제한한다. 사용자가 지정한 목적지를 조용히 이동시키는 방식은 새 demo mission에서 사용하지 않는다. valid scene + blocked/unsupported mission은 장면 검토와 주행 거절로 표현한다.

**검증/완료:** 직선 과거 replay, L자/역방향 scene, 막힌 goal, scene-only, stale scene/profile/mission, legacy record migration/rejection. actual Isaac에서 L자 장면은 Build 가능하고 미지원 Run은 명확히 거절; 기존 직선 회귀 유지. migration 실패 시 원본 보존.

### H3 — 사진 근거와 TurtleBot 프로필

**H3a 현장 입력 품질:** observer/prompt/schema/catalog의 warehouse 고정을 풀되 지원 형상 범위를 유지. 관측된 로봇 후보/벽/일반 정적 장애물/자유 공간과 불확실성을 기록. 필요한 범용 box/cylinder 등 최소 primitive를 기존 도구와 비교해 추가한다. 모호한 물체를 랙으로 강제하지 않음. planner는 사용자가 확인한 demo profile과 H2 mission 계약을 받는다.

**H3b 사진→실험장 관계:** 실제 트랙 사진/실측 또는 축소 변환 중 선택을 확정하고 manifest로 저장. 사진의 단안 추정 축척을 측정 사실로 다루지 않는다. M2-D 높이 오독과 scan 미관측 높이는 별도 검증 항목이다.

**H3c profile:** B0 inventory를 기준으로 공식 URDF/mesh/license/commit과 실제 센서·support·wheel axis를 연결. generic AGV 프로필을 이름만 바꾸지 않는다. Isaac 모델은 settle/직진/회전/Pause/Reset/센서 frame을 검증한다.

**검증/완료:** 기존 창고 1개 + 비창고 현장 1개 + 최종 실험장 사진/도면 1개를 고정해 관측·배치·단위·robot-role 차이를 평가. fake/saved 결과 회귀와 새 paid live 정확도 평가를 별도 보고. live 호출은 입력·모델·요청수·예산의 승인 범위 안에서 유한 실행; 오류 뒤 자동 retry 없음. 각 입력의 정확도/제한과 actual Build/capture를 연결한다.

### H4 — 스캔으로 Twin 갱신

**H4a 데이터·가상 입력:** sim/recorded/real을 구분하는 scan session/TF/time/profile 계약; bounded decoding; 알려진 이동·회전과 일부 가림을 가진 합성 fixture. raw scan을 전부 브라우저/LLM으로 전송하지 않고 필요한 다운샘플과 근거만 제공한다.

**H4b 정합:** 처음에는 대응 기준점으로 초기 SE(2)를 정하고 필요 시 ICP 등 refine을 검토한다. 대칭 통로·관측 부족·stale TF·틀린 단위/scale·다른 현장 입력은 명확히 거부. residual 임계값은 센서/기준점 불확실성에서 결정하고 평가 전에 고정한다. LLM 추측 transform으로 확정하지 않는다.

**H4c 수정·UI:** 변경 전후 overlay, stable object ID/허용 속성 기반 proposal, parent-version guard, apply/undo. 관측되지 않은 공간은 빈 공간으로 지우지 않고, 움직이는 TurtleBot return을 정적 벽으로 반영하지 않도록 sensor/robot footprint 처리를 명시한다. 2D scan은 해당 평면의 XY 증거이며 높이는 기존 근거를 유지한다.

**검증/완료:** 알려진 오차 복원, 부분 가림, 모호함 reject, outlier, timestamp/TF mismatch, wrong-site binding, stale apply, undo, 기존 run/배포 후보 invalidation. 실제 Isaac의 변경 prim/보존 prim/외부 prim 보호와 캡처 확인. virtual/recorded PASS와 real-scan PASS를 구분한다.

### H5 — 일반 주행과 경로 비교

**H5a navigation:** B0 호스트 결정 후 version-pinned Nav2를 우선 검토한다. ROS bridge/센서/clock/TF/odom/명령 타입을 실제 사용 호스트에서 먼저 시험한다. +X helper를 무제한 경로 최적화기로 확장하지 않는다. 초기 모의 navigation 시험은 B6 전체 완료와 구분한다.

**H5b bounded search:** 동일 지도·profile·start/goal에서 기준 Nav2 설정과 제한된 planner/smoother/controller 후보를 평가한다. 예산은 후보 수×반복×episode timeout으로 설정하고 job cancel/restart를 지원한다. 첫 구현은 적은 후보의 deterministic/grid 비교로 충분하며 RL이라는 이름을 붙이지 않는다. hardware 속도·가속도·여유 한계는 탐색 대상 밖이다.

**H5c UI·산출물:** baseline/new route overlay, 같은 조건인지 표시, 반복 결과·실패·reason과 candidate parameter artifact를 보존한다. shortest path 그림만으로 시간 개선이라고 주장하지 않음. 실제 추종 controller와 physics 실행이 필요하다.

**검증/완료:** 직진/코너/우회/막힘/센서 stale/취소/Reset을 실제 Isaac에서 검증. 평가 중 scene 변경은 취소 또는 새 batch로 처리. 동일 조건 비교, 도착/충돌/최소 여유 선행 검사, 성공한 run의 시간/거리와 실패율을 함께 보고. 개선이 없으면 `No improvement measured`를 허용한다.

### H6 — TurtleBot 실물 관측과 제한 실행

**H6a 준비:** 기존 B0~B4의 inventory→무구동 bringup→정지 센서/TF→제한 teleop/stop→표준 Nav2 기준선을 따른다. Windows/ROS 호환·Linux 호스트·RPi4 자원 배치는 B0에서 결정하고 새 OS/ROS 설치는 승인된 범위에서 수행한다.

**H6b 관측:** B5/B6 모델·센서 일치와 B7 read-only scan/bag→Twin 갱신. 실물 측정 위치와 Isaac 월드 정합 확인. Replay/Observe 경로는 motor 명령 발행 0으로 검사한다.

**H6c mission 적용:** B8에 따라 실물/map/profile에 묶인 승인 artifact만 적용. 설정 적용과 시작을 분리하고 통신 상실/취소/driver timeout 및 물리 정지 수단을 확인한다. low-level 주행과 정지는 현장 ROS/driver가 소유한다.

**완료:** 현장 승인된 동일 mission에서 sim/real trace·config·정지 결과가 대응. 사용자/운영자가 해야 할 일은 조립·전원·실측·촬영 및 실물 시험 입회다. 소프트웨어 실행·수집·분석·Isaac/UI 캡처는 접근 가능한 범위에서 자동화한다.

### H7 — 개선을 주장할 수 있는 비교 데이터

세 실험을 분리한다.

| 실험 | 고정할 것 | 바꿀 것 | 주요 결과 |
|---|---|---|---|
| E1 Twin 보정 | 같은 실제 공간·측정 기준·로봇; navigation 조건은 필요 시 고정 | photo 초기 Twin → scan 보정 Twin | 독립 기준점/장애물 위치 오차, coverage/미관측, 정합 실패 |
| E2 경로 개선 | 같은 보정 map/scene/profile/start/goal/허용 오차/안전 상한/측정법 | 합리적인 기존 경로/config → 후보 경로/config | 성공률, 충돌/개입, 최소 여유, 시간·거리·변동 |
| E3 실물 재현 | 같은 실제 트랙·로봇·mission·안전 상한 | 검증된 기존/새 config | 실물 시간/거리/성공과 simulation 차이 |

- 기본 평가 제안은 조건별 5회, 실제 실험은 B 규칙에 따라 3~5회로 사전 고정. 표본수·실패수·operator intervention과 대표값(median)·범위를 함께 공개한다. 최적 후보 선정에 쓴 run과 최종 평가 run을 구분한다.
- `time saved (%) = (baseline median - candidate median) / baseline median × 100`. baseline이 0/미측정이거나 비교 가능한 성공 자료가 부족하면 개선율을 표시하지 않는다. 성공 run만의 중앙값은 성공률과 함께 표시한다.
- simulation time과 wall-clock 평가 비용, real elapsed time을 구분. timeout/안전정지를 빼고 성공처럼 평균 내지 않는다. 안전하지 않은 baseline은 실물 실행 대신 거절 기록을 쓴다.
- 계획된 명령량/odom만으로 정지거리·실제 위치 정확도를 자기 검증하지 않는다. 최소한 바닥 마커/실측/외부 영상 등 독립 근거를 준비한다.
- 제출에서 쓰는 숫자는 `run_id → manifest → input/profile/map/config → metrics/captures`로 추적한다. simulation 개선율을 산업 AGV 또는 실물 개선율로 제시하지 않는다.

### H8 — 영어 제출과 배포

- README 첫 화면: 문제·사용자·현재 지원 범위·실제 Nemotron/Token Factory 역할·5단계 데모·TurtleBot 대역 설명. English Quick Start와 known limits, recording/replay의 구분을 제공한다.
- 개인 PC online 설치 + prebuilt release를 승인 경로로 전달해 회사 GPU 워크스테이션에 설치하는 흐름을 유지. 회사 PC 간 장면 교환/CPU planner는 다시 추가하지 않는다. offline 설치와 live LLM 네트워크 요구를 분명히 한다.
- clean source release allowlist에 신규 locale/schema/profile/worker/필요 asset·license가 포함되는지 검증; 회사 전달 조각은 기존 900MB 기본값 유지. 큰 Isaac 전체 설치본을 함께 배포하지 않음.
- 실제 설치 대상의 cold start, persistent key 상태(값 출력 없음), saved-result replay/Isaac capture를 확인. 회사 actual은 미실행이면 그대로 표시하고 개인 PC 데모 제출을 막는 조건으로 삼지 않는다.
- 공개 LICENSE는 사용자가 선택한 라이선스를 적용. 사진/URDF/mesh/model 등의 attribution과 공개 권한을 정리한다.
- 영상 초안 165초: 0~15 문제/현장, 15~45 사진→AI→Isaac, 45~110 실제 TurtleBot scan·주행과 화면 overlay(하드웨어 동작 65초), 110~150 같은 조건 비교와 실측 숫자, 150~165 사용 기술·제약·재현 경로. 영어 자막은 최종 UX와 같은 용어를 쓴다. 녹화/재생·배속을 숨기지 않음.
- [공식 규칙](https://nebiusglobalaihackathon.devpost.com/rules) 2026-09-25 확인: runtime Nebius 사용+NVIDIA 모델, 공개 소스/라이선스/설치 지침, 영어 또는 영어 번역, 3분 미만 영상 및 Physical AI의 최소 1분 동작 장면 요건. 표시 마감은 2026-10-30 10:00 PDT(한국 10-31 02:00)이며 제출 전 재확인한다.
- H0 재검토: 일반 요건과 별도로 Physical AI 설명에 Serverless Jobs 사용 문구가 있다. Token Factory+로컬 Isaac만으로 세부 트랙 적합성까지 확정하지 않고 주최 측 확인 항목으로 남긴다. 전체 cloud Isaac 이전을 선행하지 않으며 추가 서비스가 실제 필요하면 작은 sensor/evaluation worker 범위를 별도로 설계·승인한다. 현재 문의 발송/유료 실행은 하지 않았다.
- 권장 freeze: 공식 마감 7일 전 기능 고정, 3일 전 영어 자료/재현/영상 검수. 일정이 부족하면 먼저 추가 도메인·한국어 toggle·cloud/RL을 줄인다. 실물 통합을 포기하게 되면 제출 주장과 트랙 증거를 다시 검토한다.

## 6. 우선순위와 제외 범위

**P0:** 영어 기존 UX; scene/mission 분리; 사진-트랙 관계; TurtleBot profile/센서·정지; scan 정합/검토 갱신; 같은 조건 navigation 평가; 실제 데모와 영어 재현 자료.

**P1:** 선택적 한국어 UI, 추가 현장 corpus, 더 편리한 편집, 회사 현장 설치 gate, 두 번째 경로 최적화 알고리즘, 추가 성능/사용성 실험.

**후순위:** 범용 외부 MCP 플랫폼, cloud full Isaac 이전, Isaac Lab/RL 대규모 학습, multi-robot/fleet, 정밀 photoreal 재구성, 실시간 3D SLAM 자체 개발, PC 간 장면 교환, connectome 연구. 유료 cloud는 현재 제출의 필수 선행조건에서 제외하되 향후 worker adapter 확장은 유지한다.

회사 설치 스크립트는 이미 만든 범위를 검토해 마무리하고 추가 기업 배포 플랫폼으로 확장하지 않는다. 데모에서 입증할 핵심은 설치 도구가 아니라 사진→스캔 보정→검증된 경로의 실제 결과다.

## 7. 중단·재개와 완료 기록

- 하나의 H 하위 단계마다 목적/변경 파일/acceptance/상한/증거 경로를 정한다. 관련 코드와 실패를 해결한 뒤 멈춤 지점을 기록한다. 큰 전체 suite 반복을 작업 진척으로 대신하지 않는다.
- 체크포인트에는 active step, HEAD+dirty 파일 hash, 마지막 완료 동작, 시험 command/exit/report, 실행 중 job/소유 process, paid request 상태, 다음 한 작업을 적는다. 기존 승인 범위를 재사용하며 소스 변경을 문서 읽기만으로 재승인받지 않는다.
- 유료 job은 시작 전에 request/input identity와 상한을 저장한다. 중단 후 응답 여부가 불명이면 자동 재요청하지 않는다. 테스트에는 저장 응답을 활용한다.
- 기록 상태: `NOT_STARTED / IN_PROGRESS / PASS / PARTIAL / FAIL / BLOCKED`. 문서 검토 PASS, mock PASS, actual Isaac PASS, physical PASS를 별도로 쓴다.
- 관련 기능이 바뀌면 targeted tests→필요한 actual gate. 문구/문서 수정만으로 전체 물리 suite를 반복하지 않는다. 단계 보고 후 미선택 후속 단계로 무제한 확장하지 않는다.
- 로그/파일 상태 변화가 있으면 설명하고 매 단계 결과를 보고한다. 사용자가 직접 프로그램을 켜고 캡처해야 진행되는 워크플로를 기본으로 만들지 않는다.

## 8. 사용자 결정이 필요한 시점

| 결정 | 현재 권고 | 필요한 시점 |
|---|---|---|
| 최종 사진/실험장 관계 | TurtleBot 포함 자체 촬영 실제 실험장. 산업 사진 축소 재현을 원하면 transform/실측 추가 | H3b 입력 확정 전 |
| 트랙·장애물·실측 공간 | 기존 2m×2m 아이디어는 미확정; 실제 footprint·센서·정지 여유로 결정 | B0~B4 |
| ROS/Nav2 host·OS | 기존 RPi/사용 가능한 Linux host inventory 후 조합 선택 | B0; 설치 전 |
| 공개 라이선스 | LICENSE 미확정, 제3자 의존성 확인 후 선택 | H8 공개 전 |
| 유료 검증 예산 | 기존 승인 내역을 확인하고 각 새 live batch의 요청/시간/금액 상한 기록 | 새 paid batch 전 |

영어 기본값, 쉬운 영어, TurtleBot 대역, 창고 비한정, 단일 GPU 워크스테이션 실행은 재질문하지 않는다. 선택적 한국어 UI는 이후 결정 가능하며 지금 계획과 영어 작업을 막지 않는다.

## 9. Astra 인수인계 프롬프트

아래는 H0 검토에 사용한 원래 지침이다. H0와 H1a-1은 해당 범위에서 완료했다. 후속 Sol은 현 상태·[H1a-1 검증 기록](../verification/H1a-1-english-web.md)을 확인하고, 별도 사용자 요청에서 선택한 다음 단계만 실행한다. 모델 변경 때마다 전체 H0를 자동 반복하지 않는다.

> TwinPulse 기준 root는 C:\Users\jaewo\Documents\TwinPulse다. AGENTS.md, 최신 PROJECT_MEMORY/BASELINE, TWINPULSE_HACKATHON_DEMO_MASTER_PLAN_2026-09-25.md를 읽고 H0부터 검토해라. 확정 요구는 쉬운 영어 기본 UI, 창고 비한정 AGV 현장 사진→3D Twin→TurtleBot3 Burger 대역의 스캔→Twin 보정→같은 보정 지도에서 기존/새 경로 비교→검증된 로직의 실물 실행과 실측 비교다. 기존 typed tool registry/로컬 App/Isaac와 자동 캡처를 재사용하고 전체 재작성·cloud 이전·범용 MCP 서버화를 선행하지 마라. 실제 코드에서 +X route 제약과 goal 재배치, schema/receipt migration, 사진-실험장 동일성, scan 좌표·불확실성, sim/real 제어 분리, 비교 공정성, 영어 UX 범위를 점검해 계획을 보완해라. 이번에는 검토·계획만 수행하고 사용자에게 필요한 결정과 H1a의 구체적 변경 파일/검증/완료 기준을 제시해라. 오래된 checkpoint와 최신 증거를 구분하고 dirty 변경을 보존해라. 새 유료 호출·설치·실물·commit/push는 하지 마라.

후속 구현 모델이 바뀌어도 이 문서와 체크포인트를 작업 계약으로 사용한다. 채팅에 완료라고 적힌 문구보다 실제 버전·증거·최신 상태가 우선한다.

## 10. 참조와 검토 상태

- [실행 방향 요약](TWINPULSE_HACKATHON_EXECUTION_DIRECTION_2026-09-25.md), [기존 S0~S9](TWINPULSE_SOL_EXECUTION_PLAN_2026-09-22.md), [실물 B0~B9](TWINPULSE_TURTLEBOT3_EXPERIMENT_PLAN.md).
- [S3c 배포 점검](../verification/S3c-release-install-audit.md), [O1/O2 로컬 시험](../verification/O1-O2-local-offline-release.md): tested scope 재사용, 회사/새 actual gate와 구분.
- [ROBOTIS navigation](https://emanual.robotis.com/docs/en/platform/turtlebot3/navigation/): 공식 Nav2 사용 절차 참조. 실제 설치 ROS 탭/버전은 B0 뒤 확인한다. 이 페이지를 읽은 것이 Windows Isaac bridge 호환 검증은 아니다.
- v1 작성과 v2 H0 작업: 소스·기존 계획·공식 제출 규칙 읽기와 계획문서 갱신만. 제품 코드/OS/ROS/Isaac/유료 API/실물 동작/commit/push 변경 없음. H0 문서 검토 외 새로운 구현/runtime gate PASS 없음.
