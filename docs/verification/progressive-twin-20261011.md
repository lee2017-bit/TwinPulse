# 점진적 Twin 초안과 보완 목록 검증

2026-10-11, Baseline v1.0.433. [점진적 생성 계획](../planning/TWINPULSE_PROGRESSIVE_TWIN_AGENT_SOL_PLAN_2026-10-11.md)의 G0 판정 계약과 G1 첫 구현 범위를 검증했다. **소품 일부를 배치하지 못해도 검증된 방 초안을 저장하고 실제 Isaac에 표시하며, 미해결 물체는 원 정보와 함께 보존한다.** 이번 결과는 초안의 정적 실행 인수이며 새 모델 생성, 이동, 사진 충실도 또는 전체 데모 인수가 아니다.

## 구현한 제품 경로

기존 `BudgetedPipeline → semantic_scene → photo_layout → SiteDraftRecord → ProjectStore → ProductWorkflow → ConversationService → ChatWorkspace/SimulationRunCard`를 확장했다. 별도 성공용 API나 새 agent framework는 만들지 않았다.

- `progressive-twin-1.0` 계약에 전체 물체 ID·종류·모델 파라미터, 원 출처, 배치 상태, 부모·지지 부위, 오류·근거, 추정 높이 범위, 네 판정 축, 정책 버전, source/plan/body SHA를 보존한다.
- 기존 엄격 컴파일은 유지한다. 일반 생성 경로의 점진적 컴파일에서는 bounded 지지 재배치 후 남은 capacity/clearance 오류 중 **기존 catalog가 높은 지지면의 시각 소품으로 검증한 항목**만 별도 보완 목록으로 분리한다. 모르는 물체, 케이블·얽힘, 장비, 바닥 위험, 낮은 지지면, 부모 누락, 방 밖 주요 물체는 종전의 실패·수정 경로를 유지한다. 특정 사진·객체 ID·치수를 조건문에 넣지 않았다.
- 분리한 물체를 엔진 호출에서 제외하되 입력 inventory에서 삭제하지 않는다. 유효 subset은 기존 tool executor와 placement 검사로 실행한다. `checks_complete=false`, 지지 검사 `partial`, `materialized_subset_checked=true`를 별도로 기록한다.
- 저장 레코드 2.2는 새 계약을 재검사한다. 기존 2.0/2.1 읽기는 유지하며 SiteToolPlan 버전을 새로 만들지 않았다. reader는 hash뿐 아니라 현재 부모의 실제 catalog 지지면, 자식 치수와 출처 계약을 다시 확인한다.
- App/API 공개 요약과 재열기에 전체 개수·표시 개수·보완 목록·현재 plan 일치 여부가 남는다. 편집/derived revision 뒤 원 판정은 stale로 표시한다.
- SIM 대화가 부분 초안을 받으면 자동 경로 preview 대신 보완 안내를 남긴다. 화면의 주 행동은 `View draft in Isaac` 하나이며 Run·경로 입력은 숨긴다. 현재 단계와 보완 목록을 함께 보여준다. 이미 받은 오래된 경로 review도 표시하거나 자동 실행하지 않는다. 정지 접근성은 유지한다. 제품 UI는 기존 영어 관례를 유지한다.
- render critic의 schema와 지시는 실제 materialized subset만 검토한다. `consistent`가 나와도 `review_scope=materialized_subset`, `visual_completeness=needs_refinement`가 남는다. pending ID를 검토 결과에 끼워 넣으면 거절한다.

이번 구현은 catalog의 기존 시각 소품 분류를 제한적으로 재사용한다. robot profile의 전체 높이·돌출부·센서·작업 영향·불확실성을 사용하는 제품 수준의 판정은 아직 연결하지 않았다. 따라서 **보완 물체가 있는 초안은 보기만 허용하고 SIM·REAL 작업은 모두 409 `progressive_task_unresolved`로 차단한다.** 순수 impact 함수의 SIM 높이 제외 판정은 실물 허가가 아니다.

## 판정 소비자 점검

| 소비자 | 기존 신호의 의미 | 새 부분 결과 처리 |
|---|---|---|
| Core GeometryChecks | 모든 필수 phase passed일 때 `checks_complete` | partial을 전체 PASS로 승격하지 않음. 유효 subset 검사와 inventory 완성을 분리 |
| Provider compile와 checkpoint | `APPROXIMATE_TWIN_READY`는 반환 가능한 compiled plan 상태 | 상태 이름은 호환성 유지. stage acceptance와 progressive sidecar에 partial·pending 보존. 실제 runtime/task 인수 아님 |
| GenerationService와 ApplicationService | generation 완료와 durable draft 존재 | 완료는 저장 가능한 결과를 뜻함. 저장 실패 시 partial/passed stage도 failed로 갱신. 모델·사진·작업 PASS 아님 |
| ProductWorkflow API | Build artifact와 현재 engine receipt, SIM/inspection/run admission | 유효 draft Build 허용, pending task 차단. plan digest 변화·derived 시 원 평가 stale |
| ConversationService와 React | generation 완료 뒤 다음 질문·SIM route/Run | 부분 결과는 보완 안내와 static view만 제공. 오래된 route와 자동 preview 차단 |
| 기존 benchmark 보고서 | generation-ready/completed와 actual full journey의 종전 지표 | 이번 새 경로는 기존 cohort에 실행하거나 합산하지 않음. 기존 FAIL·분모·평가기준 불변. 새 네 축과 pending 지표의 보고서 통합은 G5/G6 잔여 |

저장된 네 축은 `draft_ready=compiled_pending_runtime`, `sim_task_pass=not_run`, `real_task_ready=not_run`, `visual_review=needs_refinement`다. 이번 실제 정적 Build 근거는 아래 별도 receipt에 있다. 저장 축을 runtime PASS나 이동 허가로 자동 갱신하지 않았다.

## 원 식당 실패의 변경 없는 재현

원 자료는 v431의 식당 run runtime이다. 완전한 pre-repair 후보를 checkpoint history에서 결정적으로 선택했다. 원 후보의 엄격 컴파일은 `PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE`을 재현했다. 기존 유료 실행의 최종 `REPAIR_STALLED`와 FAIL은 그대로다.

새 계약으로 동일 후보를 컴파일한 결과는 전체 23개 중 materialized 18개, unresolved 5개다. 남은 항목은 `table_main/top`의 매트 3개와 접시 2개이며 `SURFACE_CAPACITY_EXCEEDED`다. 높이 범위는 각각 0.77–0.78m와 0.77–0.79m이고 **실측 아닌 후보 추정치**다. 이 ID·부모·범위는 결과 설명이지 compiler의 고정 입력이나 성공 조건이 아니다.

기존 원본 82개 파일은 시험 전후 SHA가 모두 같았다. 원 후보 revision은 `18712669a09acade07d327ea0b59304c7a11a54ad31e9436416d807ecc864b0c`, 원 input digest는 `7ee16b1f2572bd7adfae746d1614a32425897ea5ca460c2a952163f189cd4e99`다. 원 budget·UNKNOWN·held·비용 성적은 변경하지 않았다.

## 실제 Isaac 정적 실행

최종 근거는 [isaac-static-5 결과](../../outputs/progressive-twin-20261011-v433/isaac-static-5/result.json)와 [현재 3D 캡처](../../outputs/progressive-twin-20261011-v433/isaac-static-5/current-partial.png)다. 기존 Isaac Sim 6.0에서 기존 adapter의 `build_site_scene` 명령을 실행했고, 새 `/World/TwinPulse` revision이 일치했다. materialized 시각 그룹은 18개이며 보완 5개는 USD prim이 없고 저장 계약에는 존재한다.

유효 SiteDraftRecord를 원자적으로 저장하고 새 ProjectStore에서 다시 읽어 같은 내용을 확인했다. 실제 USD stage도 저장 후 새 stage로 다시 열어 revision을 확인했다. 현재 viewport PNG는 디코드·SHA를 확인했다. 마지막까지 timeline은 정지 상태였으며, 사용한 headless Isaac은 정상 종료했다.

| 근거 | 값 |
|---|---|
| 정적 결과 | `DRAFT_RUNTIME_ACCEPTED_STATIC_ONLY` |
| scene revision | `5d26b4ecb8cbaaa21c882db99a317e0cbb383fe4efcf49f93019e108f8cdc298` |
| plan SHA | `82bc77039f13d6042ff18747c50204d9243adf2c38698fb842e2c36dd5a69077` |
| source manifest SHA | `579e6355610e2e462e96d9a135451d97f00c4f9207ac6dbb289a0810e7ca30f5` |
| source 무결성 | 293개 source/script 파일의 시험 전후 SHA 불변 |
| 현재 frame SHA | `379e49a043abd10fdd6c76e807d719063628d000f19fbb28630c396eafa04644` |
| engine session | `f0c70c9f-a38e-4baf-b229-a50c976a143d` |
| stage epoch | `4a16801d-1ca8-451d-a614-484b98803536` |
| command / camera | `partial-static-build` / `/World/TwinPulse/Presentation/Camera` |
| 새 provider 요청 / robot 접속 | 0 / 0 |
| Run / 사진 충실도 / 실물 | `NOT_RUN` / `NOT_VERIFIED` / `NOT_RUN` |

화면은 크기 조절형 라이브러리의 추정 표현이다. 카메라에서 벽이 일부 물체를 가리고 단순한 소품 표현도 남아 있다. 이 캡처와 그룹 개수는 사진의 배치·지지·규격이 정확하다는 증거가 아니다. 실제 브라우저와 이 Isaac session을 연결한 전체 사용자 여정은 G5에서 검증한다.

## 회귀 결과

| 범위 | 마지막 결과 | 의미 |
|---|---|---|
| Core 전체 | 302 PASS, 25.781초 | 순수 계약·기하·기존 안전 반례 |
| Provider 전체 | 384 PASS, 13.245초 | 일반 생성·수정·회복·render review와 새 부분 결과 |
| 새 progressive 모듈 | 11 PASS | 위 Provider에 포함. fixture App/API 생성·reload·보완 목록·task 거절 포함 |
| 관련 App/API 6모듈 | 148 PASS, 75.599초 | conversation/text generation/current goal/scene changes/edit proposals/site simulation |
| Web 전체 47파일 | 454 PASS | 단계 안내·영어 UI·부분 결과·old route 차단 등. jsdom이며 실제 browser/Isaac 여정 아님 |
| TypeScript와 Vite build | PASS, 70 modules | 기존 설치된 의존성 사용. 500kB 초과 bundle 경고 유지 |
| 실제 Isaac 정적 replay | PASS | 현재 revision Build/캡처·프로젝트/ USD 저장·재열기 |

개별 시험 묶음은 import된 fixture/공통 사례가 겹칠 수 있으므로 독립 표본처럼 모두 더하지 않는다. 브라우저 시험의 canvas 미구현 경고와 Vite bundle 경고를 품질 PASS로 해석하지 않는다.

재현 명령은 저장소 root에서 기존 Python을 사용한다. 단위/통합 시험용 `PYTHONPATH`는 `packages/twinpulse_core/src;packages/twinpulse_app/src;packages/twinpulse_provider/src;packages/twinpulse_robot/src;packages/twinpulse_provider/tests`다.

```text
python -m unittest discover -s packages/twinpulse_core/tests -q
python -m unittest discover -s packages/twinpulse_provider/tests -q
python -m unittest tests.integration.test_chat_conversation tests.integration.test_chat_site_text_generation tests.integration.test_current_goal_preview tests.integration.test_scene_changes tests.integration.test_scene_edit_proposals tests.integration.test_site_simulation -q
```

Web은 설치된 pnpm/Node의 `vitest run`, `tsc -b`, `vite build`를 사용했다. 실제 재현은 아래 명령이며 output은 매번 존재하지 않는 새 경로여야 한다. 외부 호출·키·Run·로봇 기능은 script에 없다.

```text
C:\isaacsim\python.bat scripts/verify_progressive_twin_replay.py outputs/physical-ai-p2-20261011-v431/approved-scope/campaign/e4d1c6c645320a1eb8e392815713b976/run-1/runtime outputs/progressive-twin-20261011-v433/isaac-static-5 --isaac
```

## 발견한 결함과 보존한 실패

- 최초 replay의 InputArtifactStore 반환 tuple 오해와 USD 임시 stage의 weak reference 수명 오류를 고쳤다. `offline`·`isaac-static` 최초 FAIL은 보존했고 각각 `offline-2`·`isaac-static-2`에 새 결과를 기록했다.
- 최초 부분 분리는 장비·warehouse 지지까지 너무 넓게 적용됐다. 기존 `room_item_risk=visual_only` 조건으로 좁혀 장비·unknown·케이블·낮은 지지면은 여전히 수정 대상으로 남겼다. 기존 warehouse/rollback 회귀를 다시 통과했다.
- 새 UI의 한국어 문구는 기존 영어 UI 회귀에서 실패했다. 문구를 영어로 고쳤으며 언어 시험을 완화하지 않았다. 새 route 시험의 잘못된 container 부재 기대도 실제 계약인 빈 plan ID·경로 SVG 없음으로 바로잡았다.
- reader 강화 뒤 `isaac-static-4`는 사진 출처 `visual`을 잘못 만든 `observed` enum 때문에 거절했다. 기존 photo-layout 계약의 `visual/user/inferred`에 맞췄고 실제 grounded 합성 사진의 visual/inferred 저장 회귀를 추가했다. 원 FAIL을 덮어쓰지 않고 최종 `isaac-static-5`로 재검증했다.
- 기본 sandbox의 Windows 임시 파일/Vite spawn 권한 오류는 승인된 동일 로컬 도구 실행으로 검사했다. ACL 변경·새 설치·권한 우회는 하지 않았다. 몇몇 진단의 잘못 추정한 파일 경로는 실제 파일 검색으로 정정했다.

## 정확한 잔여 순서

1. **G2 공통 수정 기록:** 전체 inventory와 pending을 사용하는 의존 관계 patch, 부모·자식 묶음 변경, defer/restore, Undo, stale 거절과 비대상 digest 보존. engine ACK와 disk commit 사이 중단·저장 실패·ACK 유실에서 확인되지 않은 복구를 PASS로 기록하지 않아야 한다.
2. **G3 일반 채팅 편집:** 모델 기반 대상 선택·질문·preview/apply/cancel을 같은 수정 경로에 연결한다. 지금 partial 안내/보기 UI만 보완했으며 pending 물체의 자연어 해결 기능은 아직 없다.
3. **G4 저장 센서 피드백:** 기존 scan/odom/TF·정합 보정을 공통 revision/patch에 연결하고 ambiguity·stale·범위 밖 변경을 차단한다. 현재는 live robot을 사용하지 않았다.
4. **G5 작업 영향과 실제 통합 인수:** 전체 robot envelope·불확실성 기반으로 pending의 특정 SIM 작업 영향을 판단한다. 일반 브라우저/현재 Isaac/명명 목표/이동·Stop·안정/loop/재열기를 연결하고 보고서를 네 축·pending 지표로 확장한다. 현재 모든 pending task 차단을 임의로 해제하지 않는다.
5. **G6 새 승인 실제 Flash/Super:** 기존 성적과 분리한 새 cohort에서 fresh 생성·자연어 편집을 검증한다. 이번 저장응답·합성 fixture·정적 replay는 새 모델 성공률에 포함하지 않는다.
6. **G7 현장·Cloud·영상·제출:** 기존 별도 승인과 제출 계획을 따른다. 영상/TAP는 이번 초안 인수의 필수 조건이 아니다.

G0 계약 회귀와 G1의 제한된 정적 초안 범위가 통과했다. **G2 이후, 실제 전체 사용자 여정, 모델의 새 수정 회복, 사진 충실도, 실물 데모는 미완료다.** 기존 v431 기능 2/3·식당 FAIL·품질 미검증·P2 PARTIAL은 불변이다. 네 축의 제품-level lifecycle까지 전부 완성했다고 표시하지 않는다.
