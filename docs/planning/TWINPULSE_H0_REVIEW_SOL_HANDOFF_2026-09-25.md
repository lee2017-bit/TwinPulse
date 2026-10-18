# TwinPulse H0 검토 결과와 Sol 실행 계약

- 검토일: 2026-09-25 KST. 기준 root: `C:\Users\jaewo\Documents\TwinPulse`.
- 검토 소스: HEAD `5c42899a95a0bf2422550bd17df7556a92ab3232` + 기존 dirty working tree. remote fetch는 하지 않았다.
- 현재 요청: **H0 검토와 상세 계획만. 제품 코드·테스트·설정·실행환경은 수정하지 않는다. 구현은 후속 Sol 담당.**
- 판정: **H0 문서/설계 검토 완료. 아래 보완을 반영한 방향을 권고한다. H1~H8 구현은 NOT_STARTED이며 runtime/실물 PASS가 아니다.**
- 읽기 순서: AGENTS.md → PROJECT_MEMORY의 최신 상태 → [통합계획](TWINPULSE_HACKATHON_DEMO_MASTER_PLAN_2026-09-25.md) → 이 문서의 선택 단계. 기존 S/R/B의 안전·검증 규칙은 유지한다.
- 이 문서의 설계 선택은 후속 구현 기준안이다. 사용자 확정 요구·구현 제안·미결정을 구분한다. 변경 전 Sol은 현재 diff와 파일 경로를 다시 확인한다.

## 1. 사용자 의도 — 구현자가 줄이거나 바꾸면 안 되는 것

### 고정된 최종 목표

**AGV가 있는 현장 사진 + 자연어 → 초기 3D Twin → 그 공간에서 로봇이 추가 스캔 → Twin 보정 → 같은 보정 환경에서 기존/새 주행 로직 비교 → 검증된 로직을 실제 TurtleBot에 적용 → 실측 결과 제시.**

| 요구 ID | 반드시 유지 | 의도와 다른 대체물 |
|---|---|---|
| U1 | 사진과 자연어가 실제 장면 도구/배치 결정에 반영 | 같은 fixture를 매번 생성하거나 사진은 썸네일로만 사용 |
| U2 | 창고는 예시, 평평한 실내 현장의 제한된 형상을 지원 | 창고·두 랙·중앙 직선 통로를 제품 정의로 고정 |
| U3 | Isaac의 실제 3D 장면·물리·센서·주행 | 웹 CSS 애니메이션/2D 경로 그림만으로 3D 실행 완료 표시 |
| U4 | TurtleBot3 Burger RPi4 4GB는 데모 AGV 대역 | generic 2WD에 Burger 이름만 붙이거나 산업 AGV 성능을 주장 |
| U5 | 같은 공간의 스캔으로 근거 있는 Twin revision 생성 | scan overlay만 표시하거나 원래 Twin을 버리고 별도 SLAM map으로 교체 |
| U6 | 동일 목표·지도·로봇·안전 조건에서 기존/새 로직을 측정 | goal 이동, 속도 상한 완화, 실패 삭제로 개선율 만들기 |
| U7 | 검증된 산출물을 실물에 연결해 비교 | sim 결과만으로 실물 개선 또는 산업 효율 향상 주장 |
| U8 | 쉬운 영어 기본 UI·공개 안내, 한국어 입력 허용 | 내부 코드/과거 문서까지 번역하거나 한국어 사용자 입력 거부 |
| U9 | 실행·상태 수집·Isaac/브라우저 캡처를 가능한 범위에서 자동화 | 매번 사용자의 PowerShell 실행과 수동 스크린샷을 필수로 요구 |
| U10 | 개인 PC 간편 실행, release 전달 후 회사 GPU 워크스테이션 단독 실행 | PC 간 장면 교환/CPU 기획기/VDI 우회 네트워크를 다시 구현 |

대표 실물 데모는 한 장소·한 로봇으로 제한해도 U1~U10은 유지한다. 일정 부족 시 추가 도메인/ko toggle/추가 알고리즘/RL/cloud full Isaac부터 미룬다. 스캔·비교·실물 구간을 삭제하는 것은 사용자에게 별도 제안할 범위 변경이지 구현자의 편의 결정이 아니다.

### 아직 확정하지 않은 사항

- 실제 트랙을 촬영할지, 산업 사진을 참고한 축소 트랙을 만들지. 전자를 권고하지만 사용자가 이미 선택했다고 기록하지 않는다.
- 정확한 트랙 크기, LDS/OpenCR/OS/ROS 버전, Linux host, 첫 실물 속도/정지 기준.
- 실제 baseline보다 빨라지는지. 구현이 정상이어도 개선 없음이 정직한 결과일 수 있다.
- Public license, 공개 사진/영상의 권리, 새 유료 batch 상한, Physical AI 트랙 추가 서비스 요구 해석.

## 2. H0 확인 결과 — 코드 근거와 수정 판단

행 번호는 현재 snapshot 기준이고 이후 바뀔 수 있다. 함수 이름을 함께 검색한다. 아래는 정적 검토이며 결함의 실제 재현 시험을 새로 했다는 뜻이 아니다.

| ID | 근거 파일/지점 | 확인 사실 / 위험 | 처리 단계 |
|---|---|---|---|
| F01 | `apps/twinpulse-web/src/App.tsx`: `Screen`, prompt 초기값, `messageOf`, stage/review 렌더; `index.html`; `src/api.ts` | 기존 3화면은 한국어 중심, warehouse 기본 입력, 오류 code+message 직접 노출. 번역만으로 내부 제한이 사라지지는 않음 | H1a/H1b |
| F02 | `App.test.tsx`; `e2e/r5-browser.mjs:38–57,77,86`; `e2e/s1c-session.mjs` | 한국어 accessible name/문구에 의존. 기본 prompt를 비우면 입력 없는 생성 테스트도 함께 수정 필요 | H1a |
| F03 | `nebius_pipeline.py`: `build_observer_body`, `build_planner_body` | warehouse 관찰, generic profile, +X/equal-y/z=0/0.2~10m task와 route 이동 가능성이 명시됨 | H2/H3 |
| F04 | `scene_tools.py:154–215`, `resolve_current_controller_route`; `validation.py:validate_current_controller_route` | robot/task 필수, scene expansion 즉시 controller gate 적용. resolver는 start/goal 변경 가능. 단순 validation 제거는 안전 퇴행 | H2 |
| F05 | `models.py:SceneSpec,SpecBundle`; `scene_compiler.py:build_fingerprint,_create_robot` 및 task 참조; `isaac_adapter.py` | scene-only가 현재 지원되지 않음. task를 None으로만 바꾸면 compiler/Reset/마커/snapshot 등 연쇄 영향 | H2a~c |
| F06 | `revisions.py`, `draft_store.py`, `project_store.py`, `application.py:build_candidate`, broker, `src/types.ts` | 입력/plan/bundle/validator/receipt 결합은 보존 가치가 있음. 계약 변경 시 저장본·provider·engine·TS 전 구간 migration 필요 | H2 |
| F07 | `App.tsx`: `command`, `applied`, `stage-visual` | command accepted 뒤 화면 전환은 완료 증거가 아님. 고정 랙/AGV 그래픽은 actual scene처럼 오인 가능. `applied`는 revision 비교를 사용하므로 이 장치는 보존 | H1b |
| F08 | `robot_profiles.py`, `motion_control.py`, `runtime.py` | generic 2WD+caster/positive-X 폐루프와 안전정지는 존재. TurtleBot profile/일반 navigation/scan worker 구현 증거는 없음 | H3c/H4/H5/H6 |
| F09 | `verify_app_e2e.py`, `verify_s2d_managed_replay.py`, process manager | 실제 Isaac·브라우저·capture를 자동화하는 기존 기반이 있음. 새 runner 전체 재작성 불필요 | 전 단계 |
| F10 | [S3c audit](../verification/S3c-release-install-audit.md), [O1/O2](../verification/O1-O2-local-offline-release.md) | earlier live 90-prim 주행과 후속 overlap guard는 다른 시험 경계. post-guard actual, fidelity, 회사 cold install은 미검증 | 회귀 gate 유지 |
| F11 | `TWINPULSE_APP_MIGRATION_PLAYBOOK.md`의 한국어 우선/old R6 설명, checkpoint historical YAML, progress의 Next | 오래된 실행 지시를 새 기준으로 오해할 수 있음 | 최신 pointer 우선, 역사 삭제 금지 |

**방향 판단:** typed registry → ApplicationService → authenticated broker → Isaac compiler/runtime을 재사용한다. 현 문제는 MCP 프로토콜 부재가 아니라 장면/임무/실행의 결합과 아직 없는 scan/navigation/실물 계약이다. 대외 설명에서도 현재를 외부 MCP 서버로 구현했다고 부르지 않는다. 필요 시 동일 typed 계약에 transport adapter를 추가하는 것은 후순위다.

## 3. 기존 통합계획에서 보완할 설계와 순서

### D1. 처음 스캔하는 방법을 최적화 결과에 의존시키지 않는다

잘못된 순환: 보정 Twin이 있어야 안전 주행 → 스캔하려면 주행 필요 → 보정 Twin 대기.

권고: B0~B3 정지/센서/제한 teleop gate 뒤, 운영자 입회하에 표준 mapping 도구로 천천히 관측한다. 초기에는 기록한 실제 bag도 허용하되 `Recorded real scan`으로 표시한다. 사진 기반 미검증 경로를 초기 scan mission으로 자동 실행하지 않는다. 가상 scan fixture는 개발용이며 실물 스캔의 대체 완료 근거가 아니다. 자동 탐색은 추가 기능이지 첫 필수 조건이 아니다.

### D2. B0와 ROS/Isaac 호환성 결정을 앞당긴다

- H1과 별개로 사용자가 B0를 선택하면 **무구동 inventory**를 먼저 할 수 있다. H6까지 기다리지 않는다.
- H2 계약 단계에서 단위/frame/time/goal·velocity 타입의 adapter 경계를 정의한다. OS/ROS를 추정해 고정하지 않는다.
- 실제 센서/host를 확보한 뒤 최소 bridge compatibility spike를 **H5 전체 구현 전** 완료한다. `/clock`, TF, odom, scan, 명령 타입/방향, QoS, pause/reset 후 time jump를 시험한다.
- 호환 안 되면 지원 host 구성을 제안하고 설치 승인을 받는다. 몰래 WSL/driver/OS를 변경하거나 RPi4에 모든 연산을 올리지 않는다. 회사 VDI GPU 배정을 개발 전제로 두지 않는다.

### D3. Scene, NavigationMap, Mission, Run을 분리한다

- `SceneRevision`: 환경 geometry와 속성별 evidence. `RobotInstance`: 확인된 demo profile·초기 pose. `MissionSpec`: start/goal/waypoint/허용 오차와 의도.
- `NavigationMapRevision`: scene/scan에서 도출한 점유 공간·unknown·해상도/origin/frame·변환·생성기 버전. Nav2 map과 Isaac collider가 서로 다른 세계를 표현하지 않게 검증한다.
- 초기 photo scene, scan-aligned scene, 실제 SLAM map의 관계를 manifest에 명시한다. scan을 읽기만 하고 다른 map에서 최적화한 결과는 U5/U6 PASS가 아니다.
- live robot의 현재 pose와 scene에 배치된 robot의 시작 pose를 분리. photo의 로봇을 정적 장애물과 구동 로봇으로 이중 생성하지 않도록 observation ID→role mapping을 기록한다. 다른 정지 물체/AGV는 별도 obstacle로 유지 가능하다.

### D4. 평가 정의를 H7까지 미루지 않는다

H2에서 비교 identity와 성공/실패 필드를 정의하고 H5 구현 전에 baseline·후보 공간·안전·timeout·metric 방법을 고정한다. H7은 그 규칙으로 최종 실험을 실행하는 단계다. 후보를 본 뒤 불리한 실패/seed/환경을 삭제하거나 점수 가중치를 바꾸지 않는다. 변경하면 새 evaluation batch로 남긴다.

### D5. 영어화와 새 기능 출시를 분리한다

H1은 기존 3단계 UX를 제대로 영어화한다. Scan/Compare/Robot 페이지를 동작하는 척 추가하지 않는다. 미래 5단계는 실제 기능 gate가 붙을 때 순차 노출한다. 영어 UI가 완성돼도 generation의 warehouse/직선 제한은 H2/H3 전까지 알려진 한계다.

### D6. 트랙 요건을 일반 참가 요건과 분리한다

2026-09-25 [공식 규칙](https://nebiusglobalaihackathon.devpost.com/rules)은 일반 요건에서 Token Factory runtime 호출 또는 Nebius compute를 허용하지만, Physical AI 항목에는 Serverless Jobs 사용 문구가 있다. **Token Factory+로컬 Isaac만으로 Physical AI 세부 요건까지 확정 충족이라고 단정하지 않는다.** 주최 측에 해당 조합의 적합성/Jobs 의무 여부를 확인할 항목으로 기록한다. 이번에는 문의를 발송하지 않는다.

전체 Isaac cloud 이전은 여전히 선행하지 않는다. 추가 서비스가 필요하다고 확인되면 bounded sensor-processing/evaluation job 등 실제 기여가 있는 작은 worker를 별도 설계·비용 승인한다. 단순 빈 job 실행으로 사용 증거만 꾸미지 않는다. 확인 전 임의로 트랙을 변경하거나 cloud 계정을 구성하지 않는다.

## 4. 실행 작업 묶음 — 한 번에 한 acceptance 단위

| 순서 / 묶음 | 산출물과 통과 조건 | 의도 보호 / 중단 조건 |
|---|---|---|
| H1a-1 | 영어 웹 사전·UI·API fallback·HTML·unit/browser selector 갱신; §5 기준 | contract/provider/물리 수정 금지 |
| H1a-2 | 사용자에게 보이는 backend/launcher/설치 안내와 English Quick Start | machine code/log marker/CLI flag/credential 경로 보존 |
| H1b | pending/success/stale/failed 분리, 상태 그림 정직성, layout·details | accepted만으로 Build 완료 표시 금지 |
| H2a | Scene/Robot/Mission/Map/Run 계약, migration matrix, core roundtrip/failure fixtures | version 하나만 올려 옛 데이터 자동 승인 금지 |
| H2b | app/store/broker/API/provider protocol/TS 연결, legacy replay adapter | UI와 backend 양쪽에 독립 generation owner 생성 금지 |
| H2c | scene-only 실제 Isaac Build/receipt/Reset, capability-aware Run | scene-only를 가짜 짧은 task로 우회 금지; 일반 주행은 아직 gate |
| H3a | 일반 현장 관찰·최소 catalog·evidence→object mapping | warehouse→site 문자열만 바꾸고 범용 완료 선언 금지 |
| H3b | 사용자 선택 photo-track manifest/실측 기준·test corpus | 축척/장소 관계 미확정이면 미확인 표시 |
| H3c | B0 기준 TurtleBot profile/asset license/import·physics/sensor gate | generic 모델 회귀는 별도로 유지 |
| H4a | scan/map/raw artifact 계약·known-transform fixture·readonly import | recorded/real/virtual 출처 혼합 금지 |
| H4b | 정합/불확실성·diff preview·검증 | 숫자 residual 하나만 작다고 다른 장소 정합 승인 금지 |
| H4c | reviewed partial apply/undo, actual Isaac 변경 및 map 재생성 | Apply 실패 시 기존 scene/receipt 그대로 유지 |
| H5a | 검증된 host에서 Nav2/bridge·actual Isaac 코너/우회/막힘 | +X gate 삭제를 일반 navigation 구현으로 취급 금지 |
| H5b | 작은 후보 batch·cancel/timeout·frozen identity·실행 계측 | 상한 없는 search/RL/유료 반복 금지 |
| H5c | 현재/새 경로와 성공·실패 포함 비교 UI/파일 | 더 빠름을 선결론으로 넣지 않음 |
| H6a | B0~B4 표준 실물 준비/기준선; H1~H5와 독립 가능한 gate부터 | 승인된 현장 시험만; H0가 motor 승인 아님 |
| H6b | B5~B7 정합된 real scan으로 동일 Twin 갱신 | 실제 관측이 반영된 object/map/receipt 증거 |
| H6c | B8 immutable config 적용·별도 Start·stop/rollback | model output/브라우저 lease가 직접 motor sink가 되지 않음 |
| H7 | E1 지도 보정 / E2 같은-map 경로 비교 / E3 실물 반복 평가 | 탐색용 run과 최종 평가 run 분리 |
| H8 | 영어 제출·허가된 데이터·clean release·영상·규칙 확인 | 기능 주장마다 actual 근거; 회사 actual 미실행은 별도 표기 |

B0 정보 수집과 공개 자료 권리/트랙 요건 확인은 일찍 할 수 있지만 H1a-1 구현을 막지는 않는다. H4 합성 입력도 early development는 가능하나 실제 scan integration은 H6b까지 묶어 검증해야 한다.

## 5. Sol의 첫 구현 — H1a 상세 작업 지시

### 5.1 시작 경계

후속 사용자가 `H1a-1 구현`을 요청하면 아래 웹 범위만 실행한다. `H1a 전체`를 요청하면 H1a-1, H1a-2를 각각 검증·기록한 뒤 종료한다. 이번 H0 요청은 둘 다 구현 승인이 아니다.

1. 현재 HEAD/status/diff를 읽는다. `App.tsx`, `types.ts`, process/deployment 파일은 이미 dirty이므로 본인 변경과 기존 변경을 구분한다. reset/checkout 덮어쓰기 금지.
2. 현재 테스트와 production 화면의 문자열 사용처를 조사한다. fixtures/사용자 프롬프트/원본 OCR/과거 증거는 제품 문구가 아니므로 일괄 한글 치환하지 않는다.
3. 기존 pnpm·Python을 사용한다. 번역 라이브러리 신규 설치나 lock 변경은 불필요하다. toolchain이 없으면 경로/기존 설치부터 확인하고 누락 설치는 별도 범위로 보고한다.

### 5.2 H1a-1 파일 allowlist와 변경 내용

| 파일 | 작업 | 보존해야 할 것 |
|---|---|---|
| `apps/twinpulse-web/src/i18n/en.ts` (신규 제안) | 타입 있는 영어 고정 문구, 변수 치환 helper를 최소 구성으로 정의 | UI locale이 input/provider revision에 들어가지 않음 |
| `src/App.tsx` | 제목/3단계/버튼/설명/aria/alt/empty/error/settings를 사전 사용으로 정리. prompt 초기값은 빈 문자열, 일반 현장 placeholder | `DEFAULT_API` identity, polling/lease 주기, 요청 payload, disabled gate, acknowledgement, credential 입력 clearing |
| `src/api.ts` | 한국어 fallback/session expired의 영어 표현. 필요 시 presentation error helper 분리 | code, HTTP/auth/CSRF/session 동작·401 non-retry 불변 |
| `index.html` | `lang=en`, 현재 기능에 맞는 title | base/static routing 보존 |
| `src/App.test.tsx`, `src/api.test.ts`, 필요한 i18n test | 영어 accessible name·행동·실패 검증; 기본 prompt 제거에 맞춰 실제 테스트 입력 명시 | 안전/secret/non-retry assertion을 삭제하지 않음 |
| `e2e/r5-browser.mjs`, 필요 시 `e2e/s1c-session.mjs` | 변경한 UI selector 동기화; 영어 chrome+한국어 입력 시나리오 보존 | 실제 revision/이동/Reset/캡처 검증 유지 |
| `src/styles.css` | 번역 길이로 잘리는 부분만 최소 보정 | 디자인 전면 교체/가짜 기능 추가 금지 |

`src/types.ts`, `src/engine-contracts.ts` 및 `scripts/generate_engine_ts.py`는 H1a-1 수정 대상이 아니다. 계약 생성 파일은 H2에서 원본과 generator로 변경한다. 실제 추가 파일이 필요하면 그 이유를 보고하고 해당 범위만 추가한다.

### 5.3 영어 문구 기준안

| 용도 | 영어 기준 | 주의 |
|---|---|---|
| 소개 | `Turn a site photo into a 3D twin.` | scan/real 기능 구현 전 완료형 홍보 금지 |
| 현재 3단계 | `Add Photo`, `Review Twin`, `Simulate` | 사진과 2D drawing 선택은 유지 |
| 입력 | `Photo or drawing`, `Instructions (optional)` | 사진 없이 설명만은 지원 provider에서만, Nebius 이미지 필요 안내 유지 |
| 생성 | `Create Draft` / `Creating Draft…` | 실제 generation 중만 진행형 |
| 적용 | `Build in Isaac Sim` | accepted와 succeeded를 구분하는 H1b 작업 연결 |
| 상태 | `API key saved`, `AI request not tested`, `Draft ready`, `Scene built` | ready/connected 한 단어로 전체 성공 표시 금지 |
| 주행 | `Run`, `Pause`, `Reset`, `Show 3D View` | 현재는 시뮬레이션 버튼이며 실물 실행이 아님 |
| 제한 안내 | `This is an approximate 3D model. Check the layout before running.` | 치수·가림의 한계 상세 설명과 review gate 보존 |
| 기술 정보 | `Details`, `Scene version`, `Request ID` | hash/receipt/code는 표시용 label만 번역 |
| 빈 결과 | `Not measured` | 미측정을 0 또는 성공으로 대체하지 않음 |

한국어 locale picker는 H1a에서 새로 만들지 않아도 된다. 영어 사전 구조만 두고 `ko`는 P1. 기존 사용자의 입력/파일명/저장 프롬프트를 영어로 덮어쓰지 않는다. AI summary의 영어 강제는 provider 변경이므로 H3로 남긴다.

### 5.4 오류와 상태 문구의 특별 주의

- `ApiError.code`는 계약, 메시지는 표현이다. 알려진 code를 쉬운 안내와 다음 행동에 매핑하고 unknown은 `The request failed. Open Details for more information.`처럼 표현한다. code와 backend가 이미 정제한 진단은 Details에서 추적 가능하게 한다.
- `workflow.error`, supervisor/phase, safety reason, operation status처럼 서버에서 오는 텍스트도 조사한다. **H1a-1은 UI에서 처리 가능한 범위**, 서버 payload 확장이 필요하면 H1b/H2로 넘기고 완료 범위를 명시한다.
- 키/인증 헤더/raw body를 오류 표시/테스트 스냅샷에 추가하지 않는다. 기존 credential binding과 provider 선택은 바꾸지 않는다.
- 안정적인 error code가 없는 메시지를 영어 문장 부분 문자열로 분류하지 않는다. 필요한 code 추가는 별도 작은 backend 작업으로 명시한다.

### 5.5 H1a-1 acceptance matrix

| 시험 | 기대 결과 |
|---|---|
| 첫 진입 | 영어 chrome, `lang=en`, warehouse 자동 프롬프트 없음; LLM 호출 0 |
| 입력 없음 | Generate disabled; 이를 테스트 통과 위해 기본 fixture prompt로 되돌리지 않음 |
| photo + 빈 텍스트 / 한국어 텍스트·파일명 | image/prompt가 원래 값으로 제출. 한국어는 사용자 데이터로 그대로 보존 |
| draft 생성/ack | draft만으로 Build 허용되지 않음; 해당 revision ack 뒤 기존 조건대로 허용 |
| saved key, live not tested | 두 상태가 다름을 읽을 수 있음; saved secret을 화면에 받지 않음 |
| 실패/취소/late result | 영어 안내; 취소 후 늦은 응답이 새 draft 성공으로 승격되지 않음 |
| expired session / 401 | 기존 session recovery/non-retry 동작 유지, 안전하게 다시 여는 방법 안내 |
| disconnected/stale/safety | Run 비활성화와 Reset 필요 안내 보존. 영어화 때문에 안전 latch 해제 금지 |
| viewport/keyboard | 1366×768, 1920×1080, 125%에서 주요 action/경고 접근, label/포커스 확인 |
| 자동 캡처 | 브라우저 capture를 결과에 연결. 실제 Isaac을 돌렸다면 해당 receipt/capture를 함께 기록 |

검증 명령은 현재 package scripts에 있는 아래 항목부터 사용한다(이번 H0에서 실행하지 않음).

```powershell
# Working directory: C:\Users\jaewo\Documents\TwinPulse
pnpm --dir apps\twinpulse-web test
pnpm --dir apps\twinpulse-web build
```

설치된 pnpm이 PATH에 없으면 저장소 installer가 사용하는 기존 실행 경로를 먼저 확인한다. command를 실패한 채 넘어가거나 테스트를 skip으로 바꿔 PASS라고 하지 않는다.

브라우저/actual 검증은 기존 `scripts/verify_app_e2e.py`와 `e2e/r5-browser.mjs`를 재사용한다. `--isaac-root`, `--artifact-dir`, `--timeout-s`, `--visible-isaac` 옵션은 현재 parser에 존재한다. 실제 launcher 실행 전 소유 instance/미저장 stage를 점검하고 승인 범위 내 한 instance만 사용한다. 기존 앱을 임의로 종료하지 않는다. 이 runner의 fixture smoke는 영어 흐름/engine 연결 검증이지 새 live 생성 검증이 아니다.

H1a-1 완료 보고에는 수정 파일, 실행 command/exit, UI 테스트, browser 검수, actual Isaac `PASS/NOT_RUN`, 남은 server/generated text를 구분한다. actual 미실행을 숨기지 않되 문구 변경마다 전체 물리 suite를 반복할 필요는 없다. H1b에서 상태 변경을 포함한 end-to-end gate를 완료한다.

### 5.6 H1a-2 및 H1b의 명확한 경계

**H1a-2:** `scripts/install_twinpulse.ps1`, `install_twinpulse_offline.ps1`, `start_twinpulse_installed.ps1`, `launch_twinpulse_app.ps1`, `twinpulse_launcher.py`, `.cmd` entrypoint, backend의 사용자 문구를 조사한다. 실제 한글/모호한 visible text만 정리하고 이미 적합한 영어 파일은 무변경으로 기록한다. `TWINPULSE_*_RESULT=...`, enum/code/CLI flag와 기계 파싱 가능한 stdout을 번역하지 않는다. 설치/네트워크/권한/경로 로직 변경은 범위 밖. README는 현재 동작/미구현을 정확히 설명하고 영어 `docs/QUICKSTART.md`를 마련한다. 번역 시험 때문에 installer를 실제 실행해 의존성을 재설치하지 않는다.

**H1b:** accepted→running→succeeded/failed/unknown 구분, 현재 입력/draft/applied/run 분리, 고정 CSS 도식에 `Status illustration — not the live 3D view` 또는 실제 캡처 출처·시각 표시. 기존 live scene 창은 그대로 사용. time-series plotting/streaming/전체 레이아웃 재설계는 필수 아님. 기준 revision 불일치/engine reconnect/실패 Build에서도 이전 scene 상태를 정확히 표시해야 한다.

## 6. H2 이후 Sol이 먼저 고정할 기술 계약

### 6.1 H2 migration/validation 순서

현 버전은 InputRevision 1.0, draft record 3.0(1/2 legacy reader), ProjectRecord 1.0, engine contract 1.1, workflow 1.1, provider settings 3.0이다. **서로 독립된 버전**이며 한 숫자로 일괄 변경하지 않는다. H2a에서 각 payload의 추가/제거 필드·writer/reader·hash·회귀 fixture·legacy 처리 표를 작성한다.

권장 순서:

1. 현 v1 bundle은 legacy adapter로 유지하고 새 scene/robot/mission 조합 계약을 추가한다. core는 HTTP/ROS/Isaac을 import하지 않는다.
2. scene geometry gate, robot/profile gate, mission semantics gate, selected-controller capability gate를 독립 결과로 돌려준다. invalid geometry는 Build 거절, unsupported mission은 Run 거절. 검증을 완화하지 않는다.
3. 새 도구 schema와 parser/expander, persisted receipt, app result, compiler가 같은 새 버전을 처리하도록 연결한다. Nebius의 required call slots도 이 단계에서 versioned 변경한다. 일반 현장 prompt 품질 작업은 H3에서 하되, **H2에서 old provider schema로 새 scene-only를 약속하지 않는다.**
4. Build는 scene와 optional robot instance를 수락하며 없는 mission/robot을 dummy로 생성하지 않는다. run은 tested robot+valid mission+capability+actual receipt가 있어야 한다.
5. engine handshake capability, command/receipt, TS generator, UI와 replay reader를 연결한다. 구 엔진이면 지원 못 하는 command를 발행하지 않는다.
6. 저장본 migration은 원본 보존→현재 validator 재검증→새 derived artifact/lineage→review 요구. validator/catalog/hash가 바뀌었는데 옛 승인과 build receipt를 자동 승계하지 않는다.
7. 실제 Isaac scene-only/legacy straight/unsupported mission/rollback/Reset/reload gate로 종료한다.

| 변경 | 새 version 또는 무효화 | 남겨야 할 것 |
|---|---|---|
| locale/도움말 | generation identity 변화 없음 | input/draft/key/ack |
| 입력 사진·실측·semantic prompt | 새 input/draft, old ack 해제 | 이전 artifact·결과 |
| scene geometry/scan apply | 새 scene/map, 기존 Run/배포 자격 무효화 | 원본 scene·과거 run |
| robot geometry/sensor/config | 새 profile/runtime fingerprint 및 관련 map/run 재검증 | 원 profile |
| start/goal/waypoint | 새 mission; 비교 baseline/candidate 공통 identity 재설정 | 이전 임무를 같은 임무로 덮어쓰지 않음 |
| candidate navigation parameter | 새 candidate/config/run | 공통 map/mission/safety caps |
| Isaac stage 새로 열기/reconnect | stage epoch/session/actual receipt 재확인 | 저장 draft만으로 applied 선언 금지 |
| scan view/replay만 | source scene의 승인 유지 가능, real command 없음 | 모드/출처·시간 표시 |

필수 negative fixtures: scene-only, reverse/L-shaped mission, blocked start/goal, off-floor, wrong robot, expired/stale receipt, unsupported schema, corrupt saved state, cancelled generation, old replay+new validator. `goal moved`를 `goal reached`로 평가하지 않는다.

### 6.2 H3 입력 충실도와 의도 해석

- 시각 관찰/신뢰 실측/사용자의 의도적 수정/모델 추정을 서로 다른 evidence로 기록한다. 사용자가 ‘사진과 달리 이 벽을 옮겨’라고 했으면 반영하되 `User change`로 표시한다. 사진을 항상 text보다 우선시해 명시 수정까지 무시하지 않는다.
- 치수 또는 안전 한계 충돌은 변경 제안/오류로 보이고 임의로 덮어쓰지 않는다. 자연어를 arbitrary tool/ROS/shell 명령 권한으로 해석하지 않는다.
- `Observation entity → tool call → stable scene object → prim → scan diff` 연결이 있어야 함. 배열 순서가 바뀌었다고 새 객체로 모두 재생성하지 않는다. group tool의 child ID도 parent+semantic role로 추적한다.
- 지원하지 않는 형상/사진 밖 공간은 unknown/approximate로 처리. 보기 좋게 만들기 위해 free corridor를 발명하거나 관측 장애물을 삭제하지 않는다.
- 사진 속 industrial AGV identity와 confirmed demo TurtleBot profile은 별개. 사진의 로봇 후보가 여러 개면 활성 데모 대상 선택은 확인해야 한다.

### 6.3 H4 scan→3D 변경의 최소 계약

scan session에 source(sim/real), acquisition mode(live/recorded), site binding, sensor/profile hash, timestamp/clock domain, TF samples, valid range/coverage, raw hash, map resolution/origin을 기록한다. recorded-real은 real capture지만 현재 live는 아니다.

정합은 `source_frame → target_frame` 방향과 단위, scale을 고정한다. metric frame 사이 기본 scale=1; 사진 기반 scale 보정이나 축소 트랙은 별도 명시 값/근거로 처리한다. 축/회전 단위와 TF authority를 검사한다. [Nav2 공식 TF 가이드](https://docs.nav2.org/rolling/configuration_and_development/first_time_robot_setup_guide/transformation/setup_transforms/)의 map/odom/base/sensor 역할을 참고하되 rolling 문서를 설치 버전 lock으로 사용하지 않는다.

구현 1차는 제한된 벽/상자 등의 XY 이동·크기 보정+관측 신규 장애물 제안이다. 전체 semantic 3D reconstruction을 약속하지 않는다. lidar plane 밖 높이는 원 출처를 보존한다. unknown space/가려진 물체를 지우지 않는다. robot/self return·이동 물체·invalid scan 값은 구분한다.

Apply는 parent scene hash 검사→pure diff validation→새 navigation map 파생→Isaac transactional Build→receipt 성공 확인→현재 version 전환 순서다. 실제 구현에서 순서를 바꾸면 crash recovery/원자성 근거를 ADR에 남긴다. 실패는 이전 scene 유지; undo도 새 derived revision으로 기록하고 과거 evidence를 삭제하지 않는다. run 중 Apply는 거절하거나 명시 Pause/Stop 뒤 실행하며 implicit physical stop/start를 묶지 않는다.

### 6.4 H5/H6 배포 산출물과 제어 경계

‘주행 로직 투입’의 첫 산출물은 실행 가능한 임의 코드가 아니라 **선택된 navigation config/경로·임무 artifact**다. 최소 robot/profile hash, map+transform hash, goal/waypoints, Nav2/controller version, parameter allowlist/hash, safety envelope, simulation evaluation reference를 묶는다. 실물 적용 때 실제 robot/map와 일치 검증 후 Apply와 Start를 분리한다.

시뮬레이터의 지상진실 pose와 실물 odometry/localization 입력을 구분한다. Isaac ground truth를 평가에 쓰는 것은 가능하지만 controller에만 몰래 제공하면 sim-real 동등성 주장 불가. localization 실패, stale scan/TF, simulator reset의 clock rewind를 다룬다.

작은 후보 탐색은 검증된 baseline 주변에서 시작한다. collision-free 성공/안전 gate를 먼저 통과시키고 그 안에서 시간/거리 등을 비교한다. 목표/footprint/가속도·속도 안전 상한을 후보마다 바꾸지 않는다. 합리적 baseline에 개선이 없으면 그대로 보고하고 환경/기준선을 의도적으로 나쁘게 만들지 않는다.

실물 데이터 관측과 motor authority는 분리한다. 기본 제품 API는 loopback/auth 경계를 유지하고 웹 서버를 `0.0.0.0`으로 열어 로봇을 연결하지 않는다. 별도 mission/telemetry adapter의 인증·freshness·명령 소유권·현장 driver timeout을 B 단계에서 검증한다. [ROBOTIS bringup](https://emanual.robotis.com/docs/en/platform/turtlebot3/bringup/)의 Jazzy `TwistStamped` 안내를 확인했지만 실제 버전의 type/QoS를 inventory에서 재확인한다.

### 6.5 H7에서 남겨야 할 데이터

- E1: 정합에 사용하지 않은 독립 기준점/장애물 실측을 포함해 before/after 위치 오차·미관측 비율과 실패를 보고. ICP fitting residual만을 정확도 전체라고 부르지 않음.
- E2: 고정된 updated scene/map/profile/mission/config 제한에서 baseline과 후보를 반복. candidate 선정용 run과 held-out 평가 run 분리.
- E3: 동일 실물 트랙에서 baseline/candidate 실행 순서를 교대하는 등 배터리·바닥·초기 위치 영향을 기록. 통신/개입/timeout/collision과 성공률 포함.
- metric은 `sim_time_s`, `real_elapsed_s`, `path_length_m`, `goal_error_m`, `min_clearance_m`, `intervention_count`, `termination_reason` 등을 방법/version과 함께 저장. 가능한 측정만 제공하고 geometric overlap과 실제 contact를 같은 `collision=0`으로 합치지 않는다.
- 원본/derived data, config, run ID, 평가 기준, 캡처를 연결. 안전 실패 시 즉시 stop하고 재시작/자동 재개를 금지한다. 단 한 번의 주행 숫자로 안정성과 개선율을 확정하지 않는다.

## 7. 완료 보고·중단 재개·회귀 비용 관리

각 작은 묶음 종료 시 아래 항목만이라도 반드시 남긴다.

```text
Step / implementation status / tested scope
Source HEAD + own changed files + pre-existing dirty changes preserved
Intent IDs covered / intentionally not implemented
Commands, exit codes, evidence paths, actual Isaac yes/no
Paid request count/status / physical command count
Open issues and next ONE step
```

- `PLAN_REVIEW_COMPLETE`, `UNIT_PASS`, `ACTUAL_ISAAC_PASS`, `PHYSICAL_PASS`를 구분한다. 이 H0는 첫 항목만 해당한다.
- 중단 직전 write-ahead job/input/config identity, 마지막 completed action, process ownership, paid outcome를 checkpoint에 남긴다. 프로세스가 살아 있다는 이유로 재실행하지 않고 완료·실패·timeout을 확인한다.
- 알려진 실패를 숨기려고 assertion/validator를 삭제하지 않는다. 새 계약으로 기대값이 바뀌면 old behavior와 새 behavior를 별도 test로 문서화한다.
- stage/job/credential를 임의 삭제해 처음부터 다시 만들지 않는다. 사용자 미저장 scene이나 비소유 Isaac은 종료하지 않는다. H0/영어 수정 때문에 새 유료 생성은 불필요하다.
- 단위 변경마다 전체 suite를 반복하지 않는다. H1a는 웹 test/build 중심, H1b는 no-call E2E, H2는 계약/저장/replay/actual, H3는 한정 live+fidelity, H4~H7은 각 actual gate 순서다.
- 자동화 실패 때 같은 실행을 무한 재시도하지 말고 bounded error를 기록한다. 사람이 필요한 항목은 조립/전원/현장 안전/실측/실물 촬영이며, software screenshot/log는 기존 자동 도구로 최대한 확보한다.

## 8. 사용자 결정 목록 — 지금 막지 않는 항목과 실제 gate

| 결정 | 언제까지 | 권고 / 선택 영향 |
|---|---|---|
| 데모 사진·장소 | H3b 전 | 자체 실험장 사진 권고. 산업 사진 축소 재현이면 원산업현장 실제 보정이라고 주장하지 않음 |
| TurtleBot inventory와 host | H3c/H5a 전, 가능하면 조기 B0 | 현재 OS/LDS/조립/Linux host를 알아야 구체 설치 지침 작성 가능 |
| baseline mission/비교 기준 | H5b 평가 전 | 같은 출발/도착/안전; 성공률·시간·거리 측정법 사전 고정 |
| Physical AI 세부 서비스 요건 | 제출 전략/추가 cloud 설계 전 | 주최 측 확인 필요. 문의·새 과금은 현재 미승인 |
| 공개 권리/license | H8 public release 전 | 자체 사진 우선, 제3자 assets/URDF별 권리 분리 |
| 유료/실물 실행 상한 | 각 해당 batch/현장 시험 전 | 기존 유효 승인 확인 후 필요한 차이만 질문 |

영어 기본값·창고 비한정·TurtleBot 대역·로컬 App+Isaac·회사 release 전달은 재질문하지 않는다. **H1a-1 착수에 필요한 사용자 선택은 추가로 없다. 다만 착수 요청 자체는 다음 사용자/Sol 턴에서 받아야 한다.**

## 9. Sol에게 전달할 첫 작업 프롬프트

> TwinPulse canonical root `C:\Users\jaewo\Documents\TwinPulse`에서 AGENTS.md, 최신 PROJECT_MEMORY, 통합계획 및 `TWINPULSE_H0_REVIEW_SOL_HANDOFF_2026-09-25.md`를 읽고 **H1a-1만 구현**해라. 기존 dirty 변경을 보존하고 영어 사전·현재 웹 3단계 UI·API fallback·HTML 및 관련 unit/browser selector만 수정해라. 기본 warehouse prompt는 비우되 photo+빈 텍스트와 한국어 입력을 보존하고 기존 no-input test를 올바른 입력으로 수정해라. generation/auth/lease/revision/ack/credential/physics/engine schema와 provider system prompt는 바꾸지 마라. 제품의 최종 목표 U1~U10은 유지하되 Scan/Compare/Robot 기능을 가짜로 추가하지 마라. 현재 toolchain으로 web test/build와 가능한 browser 검증을 하고 실제 Isaac 여부를 별도 보고해라. 새 유료 호출·설치·실물·commit/push는 하지 마라. 세부 검증/금지사항은 5절을 따른다. 끝나면 결과·미검증·다음 H1a-2만 제시하고 임의로 다음 단계까지 확대하지 마라.

## 10. H0 검토 범위와 증거 한계

- 소스/계획/README/progress/S3c/O1-O2를 읽고 공식 해커톤 규칙·ROBOTIS bringup·Nav2 TF 참고를 확인했다. 공식 문서 확인은 현재 host의 ROS 지원·실물 안전 검증이 아니다.
- 제품 소스·scripts·tests 등 122개 파일의 SHA-256을 문서 편집 전후 대조했으며 변경·추가·삭제 0건을 확인했다. 비밀 credential/runtime 저장소는 읽지 않았다.
- 실행한 것은 읽기·hash·문서 정합성 확인뿐이다. test suite/앱/Isaac/ROS/LLM/실물 실행은 0이며 이전 PASS를 새로운 PASS로 재발행하지 않는다.
- 전체 설계 방향은 위 보완 조건으로 채택 권고한다. 아직 불확실한 hardware/track/정확도/성능/트랙 자격을 계획서의 확정 사실로 만들지 않는다.
