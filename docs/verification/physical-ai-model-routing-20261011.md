# Physical AI P0·P1 로컬 적용 및 회귀 — 2026-10-11

기준: [제출 실행계획](../planning/TWINPULSE_PHYSICAL_AI_SUBMISSION_SOL_PLAN_2026-10-11.md), Baseline v1.0.417. 사용자 지시: 계획대로 구현 진행, 라이선스는 사용자 후속 선택까지 보류.

## 완료선

| 단계 | 현재 판정 | 근거 / 제외 범위 |
|---|---|---|
| P0 | 제품 설정 적용·로컬 회귀 PASS | 실제 저장 route + reviewed catalog + 일반 gateway 재구성 + UI 저장/복원 + 요청 본문 회귀. 실제 모델 호출 성공 판정 아님 |
| P1 | 로컬 결함 수정·범용 회귀 PASS | 원 Super 실패 재진단, compiled-position 수치/지지물 피드백, 개수 보존, 전체 Provider/App/UI 회귀. 새 모델 수정 회복은 NOT_RUN |
| P2 | NOT_RUN | 현재 source의 Flash/Super 실제 생성 → ordinary App → actual Isaac 전체 시험 필요 |
| P3–P5/P7 | NOT_RUN | P2 의존성을 건너뛰어 Cloud·실물·촬영·제출하지 않음 |
| P6 | 사용자 라이선스 선택 대기 | LICENSE 생성/변경·공개/push 없음 |

이번 증분의 새 외부 LLM/사진 전송/유료 Cloud/로봇 호출은 모두 0. 테스트 fixture, 저장 원본 진단, 로컬 후보 탐색을 fresh LLM 성공·사진 정밀도·실물 인수로 표시하지 않는다. 기존 native 예약은 PAUSED 상태로 유지한다.

## P0 일반 제품 설정

- 사진 관측: Nebius `deepseek-ai/DeepSeek-V4.1-Flash`.
- 장면 설계·오류 수정: Nebius `nvidia/nemotron-3-super-120b-a12b`.
- observer/planner 출력 상한 각각 40,000. 상한이지 목표 사용량이 아니다.
- 요청당 300초, 전체 생성 900초, 공유 최대 12 HTTP / 수정 3회 / 무진전 2회 보호. 기본 render critic OFF, 사진 없는 텍스트는 관측 호출 없음.
- 일반 route에 `GenerationPolicy` 및 reviewed catalog SHA를 함께 저장한다. Super는 둘 중 하나가 없으면 거절하며, 지원 확인 없는 Nano 전용 `thinking_mode=disabled`를 붙이지 않는다. 구 route는 묵시적으로 업그레이드하지 않는다.
- UI 추천 선택은 Flash/Super·40k·새 공유 정책을 한 묶음으로 미리보여 주며 **Save 전에는 적용하지 않는다**. 수동 모델 변경 시 지원되지 않는 추론 옵션을 제거한다. 정책 사용 중 별도 legacy 90초 입력을 숨긴다.
- 승인/input metadata도 실제 요청당 300초를 표시한다. 무시되는 legacy 90초를 승인 identity에 남기지 않는다.
- 현재 runtime route에 실제 적용했고 이전 route metadata 스냅샷을 보존했다: `stage-route-before-physical-ai-4ba4003052244146b14062a361ef6cbb.json` (OS runtime 폴더, 인증 정보 없음). 키 내용은 읽어 출력하지 않았다. 기존 provider 설정과 key registry metadata 파일 hash는 변경하지 않았다.
- catalog SHA `3927f3c084731efd6d93be2f4a90cea2468313106216df781a9cffb5f75dd7c1`, 정책 SHA `5f3d1a27f34f871de82a99c2463c96e013983808ab5b281e80a491304486ddd8`.
- 해당 catalog의 원 유효기한은 **2026-10-11 18:00 KST**. 기한을 임의 연장하지 않았다. 만료 후 새 실제 시험은 새 catalog 검증과 유효한 시험 승인 범위가 필요하다. 기존 backend가 떠 있는 경우 재시작해야 새 route를 읽으며, 이번에는 기존 Python/Kit owner가 관측되지 않았다. 타 프로세스 종료 없음.

실행: `scripts/verify_stage_routing_settings.py --apply-physical-ai --model-catalog outputs/benchmark-public-roles-20261011-v414/stage-model-catalog.json`. 이후 인자 없는 같은 도구로 readback PASS, network 0 / robot 0 / effective request 300 / whole 900 확인. 도구는 인증 정보 로딩 없이 gateway 구성을 검사하고 적용 실패 시 이전 route/catalog를 복원한다. 네트워크 금지 monkeypatch도 호출 종료 시 복구한다.

## P1 원 침실 실패 원인

원본: `outputs/benchmark-public-roles-20261011-v414/photo-bedroom/cases/planner-nebius-b358631a69c0-r2`, execution `0eb7b8eacb99494bb6019298e210c9fc`.

- 원 모델은 Super, **저장 Luna 관측 사용**. Flash/Super 새 전체 시험이 아니다.
- 원 요청 6개 모두 `finish_reason=stop`, 출력 589/1,645/469/698/982/1,815 토큰. 40,000 출력 소진이나 timeout이 원인이 아니다.
- 마지막 후보의 core geometry는 complete. 그러나 오른쪽 관측의 커튼이 왼쪽 cabinet의 drape/left anchor에서 실제 생성되었다. 선언 `region=rear_right`만 수정해도 실제 위치는 부모/anchor에서 결정되므로 변하지 않는다.
- 종전 quality feedback은 오류 코드와 관측 region만 제공했다. 현재 compiled point, 기대 half-plane 범위, 벗어난 거리와 부모 상태가 빠졌고 region 오류에 numeric progress가 없었다. 모델은 child만 수정하며 두 후보를 반복했다. 원 결과는 계속 `FAIL / REPAIR_STALLED`이다.

수정:

1. `review_photo_relations`가 현재 compiled 좌표, 동일한 photo-view 제약 범위와 위반 거리를 기록한다. 현재 원 후보는 `[-1.3, 0.0125]`, 허용 x `[-0.05, 2.1]`, y `[-0.05, 2.5]`, 위반 1.25m. **모두 추정 장면의 검사 수치이지 실측 좌표가 아니다**.
2. 품질 진단에 해당 semantic object와 support parent, 위치를 제어하는 parent/anchor 경로를 넣는다. 기존 revision-local scope에 부모/자식이 함께 포함된다. 지원 객체를 바닥으로 내려 오류를 숨기거나 unrelated 변경을 자동 허용하지 않는다.
3. 수치 개선을 기존 ProgressTracker가 비교한다. 이름/선언만 변경하거나 같은 후보 반복은 진전으로 세지 않는다. 실제 compiler/전체 품질을 다시 검사하고 best rollback·공유 소비예산·실패 branch를 유지한다.
4. 품질 repair revision `observed-quality-repair-1.1`. 옛 품질 tracker를 새 검사로 묵시 재사용하지 않는다. 기존 continuation의 dependency/quality mismatch 보호는 유지한다.

저장 원본 46 JSON 파일 hash 불변. 기존 replay 도구의 새 generic 옵션으로 진단했다:

`scripts/verify_budgeted_generation_replay.py --semantic-case <원 case> --output outputs/physical-ai-local-20261011/super-bedroom-diagnosis.json`

[파생 진단](../../outputs/physical-ai-local-20261011/super-bedroom-diagnosis.json)은 원 6개 receipt/finish/usage/SHA, 새 수치 진단 및 기존 허용 scope의 로컬 후보 탐색을 포함한다. 19개의 bounded host-only probe 후 parent와 attachment anchor를 함께 바꾸면 core complete/quality uncertain인 후보가 존재함을 확인했다. 이는 **host counterfactual이며 새 모델 응답·자동 회복·사진 지지 관계 정답·Isaac 시험이 아니다**. 원 FAIL/원 입력/원 장부를 바꾸지 않았다. 사진 특유의 object ID/좌표/크기를 제품 코드에 넣지 않았다.

## P1 반복 물체 개수

근본 원인: 종전 observer 프롬프트가 반복 물체를 대표 행으로 묶도록 지시했고, 한 관측 ID는 한 inventory 객체에만 결속되므로 묶음의 인스턴스 수가 소실됐다.

- additive observation schema **1.2**에 `instance_count`(1–24 또는 null)를 추가했다. 구 1.0/1.1은 그대로 읽고 고치거나 숫자를 추측하지 않는다.
- 가급적 개별 visible object마다 ID와 count=1. 묶음이면 관측된 개수를 명시, unknown이면 null+불확실성. 식탁마다 의자 4개 같은 관습적 숫자를 강제하지 않는다.
- 기존 compiler 전 request-local normalizer가 확인된 묶음을 distinct instance ID/ref로 풀어 기존 one-object/one-ref coverage에 연결한다. chair/box/basket/unknown 범용 회귀를 사용했다.
- 원 관측과 effective 관측을 별도 SHA/lineage/checkpoint에 보존한다. 그룹 좌표/크기/지지를 개별 물체의 확정 정보로 복제하지 않는다. 구체적 개별 위치와 지지는 추정/미검증, 그룹 relation/dimension은 unresolved로 별도 보존한다.
- 최대 24 entity의 기존 bounded 경계, count 타입/참조/중복/누락 검사를 유지한다. 알려진 개수가 초과하면 명시 실패이며 잘라서 성공 처리하지 않는다. null/legacy 개수는 미확인 상태로 남는다.
- 일반 budgeted 및 legacy 제품 경로 양쪽에 normalizer를 연결했다. 새 프레임·사진 정밀도 판정 없이 instance coverage만 통과시키지 않는다. 채팅에는 숫자 및 개수/개별 위치 미검증 경고만 추가하고 질문/실행 버튼을 늘리지 않는다. 공개 DTO에는 raw object 설명/좌표/그룹 ID를 노출하지 않는다.

## 회귀와 최초 실패 기록

| 검증 | 최종 결과 | 범위 |
|---|---|---|
| Provider 전체 | 344 PASS | 위치 수치/parent 수정·개수·scope·rollback·length/timeout·기존 계약. 가짜 HTTP/로컬 자료 |
| 관련 App 통합 9 modules | 195 PASS | route/승인, 사진·텍스트 생성, edit, 초기 질문, 로봇 준비 fake, loop/cleanup |
| Web 전체 47 files | 449 PASS | 설정 저장/복원·질문 순서·Stop·현재 상태·새 count 경고 |
| 타입 검사/production build | PASS | tsc -b / vite, 70 modules; 기존 500k chunk 경고 |
| runtime settings readback | PASS | 정확한 모델/caps/정책·구성 재구성; 외부 HTTP 0 |
| 원 Super 실패 진단 | PASS_DIAGNOSIS_ONLY | 원 FAIL/46 JSON 보존·compiled position·local scope probe; 실제 회복 NOT_RUN |

부분 UI 48, 부분 scope 15 등은 전체 회귀와 중복이므로 합산하지 않는다. 테스트 결과를 실제 모델 성공률/physical readiness로 환산하지 않는다.

최초 실패도 보존:

- 기본 sandbox 실행에서 Temp fixture Windows WinError5와 Node spawn EPERM. 정식 승인된 로컬 테스트/빌드로 재실행했고 ACL/권한 우회·설치 없음.
- 설정 검증 CLI가 네트워크 금지 monkeypatch를 복원하지 않아 후속 fixture asyncio 생성이 실패한 원인 수정. scoped try/finally 복원 후 settings 26 PASS.
- 새 count 테스트가 `SiteGenerationResult.plan_payload`라는 없는 필드를 사용해 ERROR 1. 실제 `plan.to_dict()`로 검사 수정, 제품 생성 자체는 통과했으며 전체 Provider 재시험 통과.
- 첫 Provider 전체 실행의 PYTHONPATH 미설정 import ERROR 2. 또한 과거 읽기 전용 테스트가 옛 runtime route hash까지 현재 그대로여야 한다고 가정해 FAIL 1. 사용자 승인된 P0 route 변경과 원 raw 불변을 구분하도록 **테스트에서** repository 원 seals는 유지하고 external settings는 이번 읽기 시작 hash와 비교했다. 실제 live scope의 기존 strict 보호·옛 승인 hash는 수정하지 않았다. 모듈 경로 명시 후 344 PASS.
- jsdom canvas 미구현 경고, 번들 >500k 경고는 미해결 비차단 항목이다. 새 설치로 숨기지 않았다.

## 다음 순서와 권한 경계

### P2 실제 착수와 첫 렌더 경계 수정 — v419

사용자는 공개 CC BY-SA 사진 3장·파생 Isaac 렌더·시험 텍스트만 Nebius Flash/Super로 보내 최대 8개 새 생성(각 12HTTP/3repair), 과거 사용·UNKNOWN/held 포함 **누적 USD6**, 2026-10-11 18:00KST까지 승인했다. OpenAI·개인 침실·Cloud·로봇은 제외했다. 기본 저장 설정은 바꾸지 않았으며, 실제 사진 렌더 검토를 위해 격리 시험 route의 critic만 ON, 총900초 안에서 초기420/수정300/최종180초를 동결했다. 이 검토용 프로필은 기본540/300/60·critic OFF와 구분한다.

source418 원 동결 manifest SHA `de48aa88042bc4293ddd8221699a839bd15fd77d717729d9fff9f2b33aeb087e`, source528파일. 기존 controller가 명시12회 승인도 그대로 전달하도록 확장했고 과거24회 장부는 불변, guard 회귀35PASS. 준비 영수증 생성의 duplicate `human_quality` TypeError는 0HTTP였고 기존 생성된 manifest/auth/state를 그대로 감사해 누락 영수증만 복구했다. 새 승인이나 예산 초기화가 아니다.

| source418 실제 사례 | 판정 | HTTP / 추정USD | 근거 |
|---|---|---|---|
| photo-bedroom / `ef013997cdeced6ef1d8f08fdc9e082c` | FAIL / REPAIR_STALLED | 8 / .0579714 | GPU의 초기 빈 프레임을 새 scene revision으로 전송하여 critic이 물체 전부 누락으로 판단. 실제 화면에는 이후 가구가 나타남. Run 미착수 |
| text-bedroom / `506114c7ad2409b52ad49b2e439a66fa` | 기능 PASS | 2 / .0052821 | 실제 ordinary App·Isaac 명명목표 도달·별도 이동 중 Stop·안정정지·저장/닫힌 재열기. 사진/실물 품질 PASS 아님 |

현재 새 사용 추정 .0632535, 기존 포함 Nebius 노출 **4.58730097**. 새 UNKNOWN/held0, 과거held는 그대로 carry-in에 포함. OpenAI 새0. 소유 controller 정상 종료 후 **소스 변경 전** 기존 `benchmark_pilot_report.py`로 `outputs/physical-ai-p2-20261011-v418/pre-fix-audit/`에 원감사/부분표 보존. 원 FAIL을 승격하지 않는다.

원 critic JPEG(그대로 추출): `outputs/physical-ai-p2-20261011-v418/original-critic-empty-frame.jpg`, frame1, JPEG SHA `47b101e9a2b4d6a8765bd3ea636e25b791f30aa9a41b56d8534183f590ed377f`. 같은 원 실행의 failed-journey.png에는 frame447의 가구가 보인다. USD Build receipt/metadata와 비동기 GPU 표시가 동시에 완료된다고 가정한 host 경계 오류다. 토큰 소진·Wi-Fi·로봇 오류로 단정하지 않는다.

`LiveViewportPublisher`는 scene/engine/stage/camera identity 전환 후 **후속 Kit update5회** 동안 새 revision 캡처를 시작하지 않고 이전 pending callback/queued pixels를 render epoch로 거절한다. 사진·좌표/색상 예외, scene grading 완화, 벽시계 sleep, 새 API 재시도는 없다. 최초 fixture의 patch import 누락 ERROR1 보존 후 수정, live viewport/render port/financial guards **49PASS**. 로컬 회귀만으로 GPU fence 인수를 주장하지 않는다. 새source419에서 같은 조합의 actual 재시험이 필요하다.

원 승인 8개 중 2개를 소비했으므로 새 동결에서 **최대6개**만 추가한다. 첫 사진·텍스트를 재확인한 뒤 나머지4입력을 진행한다. 원계획의 추가 C반복2개와 실제 자연어 LLM edit/왕복·이상 주입 등 이번 harness가 실행하지 않은 항목은 별도 미완료로 유지하며 6기능PASS만으로 P2 `LOCAL_FULL_PASS`라고 기록하지 않는다. source별 성적을 합쳐 최신source 성공률로 표시하지 않는다. 모든 원본·실패·기한·누적 한도/정지 보호를 유지한다.

### Host 비동기 writer 경계 — v420

source419 manifest `cc5e7366ee9285a7ddf371704a5ed5451eaa8225c3bccdcd1de41f44d18d7b4c` 첫2건 종료:

- photo-bedroom 기능PASS,6HTTP/추정 .0382425. 새 current-render frame2/uncertain, 실제 명명목표 거리 .0397308494708813m, 별도 이동 중 Stop·안정정지·저장/closedreopen. GPU fence의 실제 영향 범위 재인수이며 실측 사진 정밀도 PASS는 아니다.
- text-bedroom2HTTP/추정 .00558, 생성과 browser 전체기능 PASS지만 host 파일캡처 `viewport_missing`으로 **원전체 FAIL**. 캡처1/2는150ms이내 False 판정됐으나 종료 후 원 attempt PNG가355046/376756bytes로 실제 존재한다. live frame316개/오류없음. active viewport가 아니라 async writer 파일완료를 GPU 완료와 혼동한 host 결함이다.
- owner 정상 종료 후 **수정 전** `v419/pre-capture-fix-audit/public-pilot.json` 원감사(6예정/2착수/8HTTP) 저장. 새노출 .0438225/누적N4.63112347·과거held보존·새UNKNOWN0/OpenAI0. source418/419 성적을 최신source로 합치지 않는다.

`_capture`는 capture helper 완료 후 GPU scheduling 완료만 알리고 기존 `CaptureAttempt`가15초 안에 파일 nonempty→안정화→decode와 scene/stage identity를 검사한다. True는 캡처 PASS가 아니다. 없거나 깨진/검은/불안정 파일과 revision 변경·취소는 기존 실패를 유지한다. late-writer 새 회귀 최초FAIL→경계수정 후 capture/liveviewport/금융guard **51PASS**. 과거 raw/실패 불변, 새호출·예산/기한 연장·기준완화0. 문서 첫 patch의 history행 context 오류는 무수정으로 거절되고 정확한행으로 재적용했다.

승인8중4생성 소비, **최대4개 B입력만** source420 새동결에서 진행한다. C반복2/actual 자연어 LLM edit/통합 loop·이상주입은 남으며 전체LOCAL_FULL_PASS 아니다.

1. 새 source로 P2의 최소 photo/text 실제 Flash/Super 생성, 같은 current revision의 ordinary App/actual Isaac Build·Run·이동 중 Stop·저장/reopen·수정/재계획을 시험한다. 최종 품질은 estimated/uncertain이며 blind/실측 미검증을 유지한다.
2. 종전 총 노출 Nebius USD4.52404747/OpenAI USD1.83015270(UNKNOWN/held 포함), 종전 공급자별 USD5와 18:00 KST 기한을 초기화하지 않는다. 기존 metadata/benchmark 권한을 일반 제품 승인으로 빌리지 않는다. 외부 전체 시험 전 유효 승인과 worst-case 예약 범위를 확인한다. 새 고정 조합에서는 OpenAI 호출 예정 없음.
3. P2 완료 전 유료 시간당 Cloud 시작 없음. 그 뒤 목적 있는 bounded Job, 현장 승인된 로봇, 실제 영상, 라이선스/권리 점검, 제출 순서.
4. 로봇 OFF 전제, SSH/serial/배포/실센서/모터/전원/실물 시험 0. 새 설치/시스템 변경/force kill/새 agent/commit/push 0. LICENSE는 사용자 결정 때까지 보류.

## P2 8생성 종료와 파생 관측 용량 — v421

사용자가 명시 승인한 8개 생성은 모두 종료했다. 원owner 정상 종료 후 source420을 수정하기 **전에** 기존 `benchmark_pilot_report.py`로 `v420/final-audit`를 만들었다. source418/419의 실패와 pre-change audit는 불변이다. 서로 다른 source의 결과를 최신 성공률이나 완결된 동일조건 모델 순위로 합치지 않는다.

| source | 실제 생성 / HTTP | 기능 PASS / FAIL | 상태와 원인 |
|---|---|---|---|
| 418 | 2 / 10 | 1 / 1 | text-bedroom actual PASS; photo 첫GPU빈frame→REPAIR_STALLED 원FAIL |
| 419 | 2 / 8 | 1 / 1 | photo-bedroom actual PASS; text browser 기능PASS지만 host late-writer 원전체FAIL |
| 420 | 4 / 9 | 1 / 3 | office actual PASS; warehouse REPAIR_STALLED; dining/living OBSERVER_INSTANCE_LIMIT_EXCEEDED |

source420 manifest SHA `1511beb53d3d94d796f7c45661a46973ab2287b5e9c7568852e22b8c59867eb4`. 공개 입력/Flash→Super/각40k·300s/900s·12HTTP/3repair·격리critic ON420/300/180은 동일하다. 기본 저장 설정의 critic OFF와 구분한다.

| source420 사례 / 원 job ID | 전체 판정 | HTTP / repair | HTTP총초 | 추정 Nebius USD |
|---|---|---|---|---|
| text-warehouse / `cd3af43a5774797737f85e825964e549` | FAIL / REPAIR_STALLED, support unavailable | 4 / 2 | 34.312 | .0181935 |
| photo-dining / `1daba3bbc0e37c4c11c10eac8a34a3f9` | FAIL / observer instance limit | 1 / 0 | 16.469 | .0045696 |
| text-office / `664f6cb90ab66a20f3cd26bf36cfcbbd` | 기능 PASS | 3 / 0 | 17.641 | .0079866 |
| photo-living / `f10de97b1ee5a670ae02a3eb0f1fe763` | FAIL / observer instance limit | 1 / 0 | 39.984 | .0052104 |

office는 실제 ordinary App/API/Isaac 새생성→current3D→명명목표 거리 **.0397711874809292m**→별도 움직이는 return 구간 Stop→안정정지→reload/reset→닫힌 reopen 및 host PNG까지 PASS다. 상기 별도 Stop 시험은 **중단 없는 완전 왕복/loop 인수**가 아니다. warehouse는 생성 중 실패, 사진2개는 observer 뒤 실패하여 Run 미착수다. 모든 FAIL을 분모에 남긴다.

source420 새추정 .0359601, 이번 세source 합계 **27HTTP / 새추정USD.1430361**. 과거 사용·UNKNOWN/held를 포함한 Nebius 노출 **USD4.66708357 / 누적USD6**, 새UNKNOWN/held0·과거held불변·OpenAI새0/과거1.83015270 보존. invoice/실제 balance 차감 확정값이 아니다. **원8개 생성 cap 소진**: 비용 잔액과 관계없이 추가 유료dispatch0. 기한은 원2026-10-11 18:00KST 그대로이며 새grant/환급/예산초기화 없음.

### 사진2건의 host 용량 근본 원인과 수정

원 schema1.2 응답은 모두 wire24행 이내다. dining18원행에서 반복 물체를 풀면 object22+structure/opening/free-space6=28행, living23원행에서 object19+metadata6=25행이다. 종전 normalizer는 전부를 object24개 cap로 세어 실패했다. 토큰소진이나 timeout 때문이 아니다.

- 외부 raw observation1.0/1.1/1.2의 **24행**과 물체 인스턴스 **24개** 상한을 유지한다. 숨은 사진별 예외/삭제/임의 묶기/무제한 cap 확장 없음.
- typed **host-only derived1.3**은 object≤24, metadata≤24, 총≤48을 별도로 검사한다. 24행 이내 파생은 기존1.1을 유지하며 1.0/1.1 외부 계약도 바꾸지 않는다. 모델 wire에는1.3을 노출하지 않고 default parser가 거절한다.
- normalizer와 hash-approved local continuation만 명시적으로 derived를 읽는다. source/effective SHA·개별ref·typed category binding·metadata·미확인 개별pose/support와 unresolved group관계/규격을 보존한다. 객체 누락/중복/25object/25metadata/raw25행은 계속 거절한다.
- 합성20chair+8shell 최초 `OBSERVER_INSTANCE_LIMIT_EXCEEDED` ERROR→수정 후 PASS. 합성 checkpoint에서 source/파생 inventory20개를 저장하고 새 승인 재개에서 관측/구조 재호출 없이 batch부터 진행, 이전 checkpoint/length stop/누적4회 소비 보존을 검증했다. 가짜 transport이며 실제 생성 PASS가 아니다.
- [0HTTP 원자료 replay/보고서 QA](../../outputs/physical-ai-p2-20261011-v421/offline-evidence-qa.json): dining22개/living19개를 기존 required inventory로 정확히 전달하고 typed readback SHA 동일. **PASS_COUNT_NORMALIZATION_ONLY**다. 새 실제 LLM/Build/Run/Isaac 회복은 **NOT_RUN**, 원FAIL 승격0.

Provider전체 **347PASS**, 관련 capture/liveviewport/render approval/route/chat/goal loop/causal loop 9modules **215PASS**. 부분7/앞51 등 중복을 합산하지 않는다. Web/Core코드 변경0·이번 새Web빌드/실물/Cloud시험0. 최초 Temp sandbox WinError5는 권한 우회 없이 정식 fixture-only 실행 승인으로 재시험; 초기 테스트 import 오경로와 diagnostic 필드 위치 KeyError를 실제 App/grounding API로 바로잡았다. 문서 patch의 progress title context 실패는 무수정 거절 후 정확한 제목으로 재적용했다.

### 창고는 모델 단독 문제가 아니다

원모델은 box1의 부모를 요청된 pallet 대신 shelf2로 선택했다. .5×.5m child footprint가 .8×.42m surface에 맞지 않아 capacity 진단이 나왔고, 실제 footprint/부모/surface 수치를 받고도 같은 box를 두번 반복했다. 응답1051~1804토큰/정상 finish이며40k/300초 부족이 아니다. 이름이나 관계 없는 turtle object 추가는 오류 해소가 아니므로 REPAIR_STALLED/원FAIL 보존.

추가 [0HTTP capability 감사](../../outputs/physical-ai-p2-20261011-v421/warehouse-capability-gap.json)는 `library_for_request`에 있는 `warehouse.rack`/`warehouse.pallet_stack`이 semantic `KINDS`/model grammar에는 제외되고, unknown pallet은 surface parent로 선택할 수 없는 gap를 확인했다. 따라서 올바른 팔레트 부모를 선택하라는 프롬프트만으로 해결됐다고 말할 수 없다. **범용 typed warehouse lowering/지원부품·지지 geometry를 기존 compiler/core에 연결하고 회귀하는 작업이 다음 우선순위**다. 사진/ID별 자동상자배치나 바닥변경으로 통과시키지 않는다. 그 뒤 원모델의 의미관계 선택·수정 진전도 실제 재인수한다.

### 보고서와 정확한 잔여

[사진11개를 내장한 단일 HTML](../../outputs/physical-ai-p2-20261011-v421/final-evidence/report.html)은 원 수치·실패·입력과 실제 UI·빈 첫GPU frame까지 포함한다. 외부 이미지 링크/추가 다운로드 없음. `metrics-only.json`/`raw-seal.json`도 같은 디렉터리에 있다. 원421JSON SHA, 기존 보고서 SHA, 11개 embedded PNG/JPEG decode/수치/wholefalse 검증 통과. report generator 최초 unmatched parenthesis SyntaxError는 artifact 코드에서 수정 후 생성했다. 원 raw/이미지/장부/FAIL은 수정하지 않았다. source421 오프라인 수정은 source420 실제 점수를 승격하지 않는 별도 절이다.

1. 범용 warehouse semantic/support 어댑터 연결과 관련 회귀.
2. 개수 수정·warehouse의 새 실제 영향 범위 인수와 C 새세션 반복. 새 유효한 횟수/데이터/금액/기한 범위 필요; 이번8개를 재사용하지 않는다.
3. 일반 chat의 실제 모델 scene edit→preview/apply/cancel→재계획 연결. 현재 regex 편집과 별도 proposal 서비스가 있다는 사실은 ordinary LLM 연결 완료가 아니다.
4. SIM 연속왕복/loop·battery/sensor/comms 이상 주입의 통합 인수, 독립 사진별 개수/배치/지지 품질 검토. 사람blind/실측 크기는 미검증.
5. **P2 LOCAL_FULL_PASS 이후에만** 승인된 bounded Cloud Job, 현장 로봇 인수·영상·사용자 라이선스 선택/자산권리·공개/제출. P3/P4 미착수, whole_demo_pass=false, nativePAUSED 유지.

로봇SSH/serial/센서·모터·전원·배포/실물·Cloud·설치·시스템설정·force kill·새agent·commit/push·LICENSE 적용·공개0. 라이선스는 사용자 추후 선택을 기다린다.
