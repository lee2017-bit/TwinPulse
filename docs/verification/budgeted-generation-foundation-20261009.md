# TwinPulse 생성 예산·단계별 수정 구현 검증

이 문서는 v369 당시 근거다. 일반 채팅 승인·재개는 후속 v370에서 연결·검증했으며 현재 상태는 [새 검증 기록](ordinary-generation-approval-resume-20261009.md)을 따른다. 아래 당시 미완료/실패 기록을 소급 수정하지 않는다.

2026-10-09 KST · Baseline v1.0.369 · [구현 계획](../planning/TWINPULSE_BUDGETED_GENERATION_REPAIR_SOL_PLAN_2026-10-09.md)

현재 상태는 **PARTIAL**이다. 호출·시간·공통 수정 예산, 중간 장면 계약과 결정적 컴파일, checkpoint와 명시적 backend 재개를 구현했다. 고정 모델 응답으로 잘못된 장면을 수정한 뒤 기존 채팅·저장·실제 Isaac의 화면·이동·Stop까지 연결해 확인했다. **일반 채팅의 새 유료 승인·checkpoint 재개 UI와 실제 GPT/Nemotron 성능 검증은 아직 끝나지 않았다.**

이번 증분의 외부 API 요청·사진 전송·유료 호출·로봇 접속은 모두 0이다. 저장된 일반 모델 조합/출력 한도/기존 총 300초 설정과 과거 승인 장부를 변경하지 않았다. 새로운 예산 정책은 명시적으로 선택하는 실험 경로이며 일반 기본값으로 자동 전환하지 않는다.

## 구현한 내용

- `generation-policy-1.0`: 기본 제안은 호출별 300초, 전체 900초, 요청 12회, 모든 단계가 공유하는 수정 3회, 연속 비진전 2회다. 초기 540초·공통 수정 풀 300초·마무리 60초를 분리하고 수정 시작 최소 잔여 90초를 확인한다. 기존 파일의 90/300초는 여전히 전체 생성 deadline이다.
- 송신 전 한 번 예약하고 관측·batch·수정·실패·불명 결과를 같은 예산으로 센다. 승인 없는 audited 송신은 키를 읽거나 HTTP를 보내기 전에 거절한다. 기존 전량 context 비용 예약 알고리즘과 동일 attempt ID를 사용하고 원응답 기록 전에 정산하지 않는다. UNKNOWN은 예약을 유지하며 자동 재송신하지 않는다.
- 출력 `length`는 빈 본문이나 부분 JSON보다 먼저 분류하여 즉시 중단한다. 20,000토큰 wire와 선택한 Nano no-thinking 옵션을 최초·수정 호출 모두에 연결했다. 이는 실제 모델 성공률 향상을 입증한 결과가 아니다.
- 중간 계약은 방·inventory를 먼저 받고 필요한 ID별 파라미터를 최대 6개씩 받는다. host가 ID·근거를 연결하므로 모델이 실행 call ID와 근거 ID를 각각 다시 작성하지 않는다. 불완전한 draft는 실행 가능한 장면이 아니다.
- 완성 후보는 기존 파라미터 라이브러리와 typed executor로 전체 컴파일한다. 10×12m 추정 자체를 실패로 보지 않으며 실측 미검증 상태를 유지한다. 특정 침실 사진의 정답 좌표·목록·치수를 새 계약에 넣지 않았다.
- 작은 typed patch로 방 크기·객체 파라미터·부모 관계 변경, 출처가 있는 누락 물체 추가, 동일 관측의 입증된 중복 제거를 처리한다. 다시 전체 컴파일에 실패하면 이전 후보를 바꾸지 않는다. 고유 장애물을 삭제해 packing을 통과시키는 수정은 거절한다. 기존 사용자의 명시적 scene 삭제·New/Add/Change 편집 경로는 별도로 유지한다.
- 물체 순서·요약 문구 변경은 진전으로 세지 않으며 A→B→A 반복도 감지한다. 최초 구조 오류·batch 오류·장면 오류가 공통 수정 횟수를 쓴다.
- 관측 캐시와 SHA 검증 checkpoint/불변 history를 저장한다. 동일 승인 재사용으로 예산을 초기화할 수 없다. backend의 명시적 새 승인 재개는 완료 단계부터 이어가고 이전 실행의 호출 수·활성 시간을 별도 누계로 보존한다. UNKNOWN/송신 중인 checkpoint는 재개하지 않는다. 읽기·재열기는 Build/Run/호출을 실행하지 않는다.
- 기존 실행 진단에 policy/checkpoint/semantic revision/plan SHA·호출/수정 수·중단 이유를 연결했다. 현재 진행 카드와 상세 정보에 남은 시간·추정 사용 비용·불명 예약을 구분한다. invoice 확인으로 표시하지 않는다.
- 설정 화면에서 새 정책과 추론 옵션을 명시적으로 저장할 수 있다. 일반 채팅 승인·재개 UI가 아직 없다는 경고를 표시하며 정상 사용에서는 실험 정책을 끄도록 안내한다. 설정 저장은 유료 실행 승인이 아니다.

## 회귀 결과

서로 겹치는 시험을 합쳐 성공률이나 고유 test 수로 표시하지 않는다.

| 실행 | 결과 | 확인 범위 |
|---|---|---|
| Provider 전체 | 200 PASS · 4.616초 | 신규 budgeted generation 33개 포함; 실제 외부 모델 응답 아님 |
| Core 전체 | 302 PASS · 26.738초 | 지정한 package `PYTHONPATH` 환경에서 실행 |
| 관련 통합 7개 모듈 | 305 PASS · 148.567초 | stage routing, 채팅, 텍스트 생성, 실행 진단, 제품 API, scene 변경, key registry |
| Web 전체 | 46 files / 428 PASS | 마지막 비용 표시의 작은 변경 전 전체 회귀 |
| 마지막 Web 관련 재회귀 | 39 PASS | 최종 설정·채팅 표시 변경 포함 |
| 최종 TypeScript / Vite build | PASS | 기존 큰 chunk 경고는 남아 있음 |
| 과거 실제 실패 readonly 재생 | PASS | 출력 length와 근거 불일치 분류; socket 송신 차단·원본 SHA 불변 |

신규 시험은 12/13번째 호출 경계, 공통 수정 3회, 시간 풀·돈 예약, UNKNOWN/late/cancel, 누락 승인 시 키 읽기·송신 0, strict JSON/boolean 치수, typed patch rollback/add/중복/재부모화, 관측 캐시 무효화, checkpoint 변조 거절, 실제 TraceContext, 명시 재개와 과거 누계 보존을 포함한다. 테스트의 응답·usage·가격은 fixture이며 실사용 품질·청구 금액으로 집계하지 않는다.

초기 Core 3개·관련 통합 4개 실패는 자식 프로세스의 package import 경로 누락이었다. 프로세스별 `PYTHONPATH`를 지정한 전체 재회귀 결과가 위 표다. 설치나 ACL 변경으로 해결하지 않았다. Windows sandbox 임시 파일 접근 실패는 승인된 실행 권한으로 재검사했으며 기존 접근 거부 폴더를 우회하지 않았다.

## 실제 App → Isaac 연결 결과

최종 [r4 결과](../../outputs/budgeted-recovery-isaac-20261009-r4/result.json), [browser 결과](../../outputs/budgeted-recovery-isaac-20261009-r4/browser.json), [수정 기록](../../outputs/budgeted-recovery-isaac-20261009-r4/budgeted-fixture/recovery-result.json), [실제 생성 화면](../../outputs/budgeted-recovery-isaac-20261009-r4/generated-ready.png)을 보존했다.

LLM transport만 명시적 fixture다. 방 2×2m에 침대·책상을 넣는 후보의 `PHOTO_LAYOUT_REGION_FULL`을 작은 방 크기 patch로 수정하고 같은 제품 compiler의 검증을 통과했다. 이 시험의 6×6m는 **실험 응답이지 사진의 정답이나 제품 기본 치수가 아니다.** 요청 3개(구조/batch/patch), 수정 1개, 네트워크 요청 0이다.

검증된 후보를 기존 채팅→저장→Build에 연결했고 실제 로컬 Isaac의 현재 3D frame, 명시적 Run의 PhysX 목표 도착, 채팅 Stop, 정지 pose 유지, reload 비재실행, reset, 저장 프로젝트 재열기를 확인했다. 실제 화면에는 `home.bed`의 프레임·매트리스·헤드보드와 `common.desk`의 상판·다리가 나타났다. 이는 해당 두 모델의 화면 근거이며 모든 가구 변형이나 사용자 사진 정밀도의 PASS가 아니다.

- 최종 status/browser/host/capture: PASS. Browser page errors: 0. Frame 관측 172회는 중복 metadata를 포함할 수 있으며 고유 frame 172장이라는 뜻이 아니다.
- 입력 request ID: `6b36fbc1-d07b-4dc8-897c-6b84dd5acb2c`.
- Checkpoint ID: `1d6e2f8bd5a69e3487f9551a1a729760a4ca70108fd52af6ef6fa2c25d57e421`.
- 최종 semantic revision: `1f82fd59afe3eac59ca3ec635c445b4707d29f1383f0124c53c051d7601a22ab`.
- 실제 applied revision: `109523a7b2813b86c275bd7f733282c87c240b9712cee289c19a86c305178e9a`.
- 실제 capture SHA: `b990027b74efd147895d3cec36e550c65effb1237fc40fdb3077f9b2bc09a3be` · 960×640.
- inference source 전후 SHA 불변. 소유 launcher/engine/backend 종료 감사 succeeded. 타 프로세스 강제 종료 없음.

처음 실행의 실패도 남겼다. r1은 시험용 desk ID가 라이브러리와 달랐다. r2는 실제 진단 연결에서 `TraceContext.span()`에 `stage` 인자가 충돌하는 제품 결함이었다. 실제 registry ID와 `semantic_stage` 필드로 수정하고 회귀를 추가했다. r3 PASS 후 추가 코드 변경이 있어 최종 source의 r4를 별도로 검증했으며 이전 FAIL을 PASS로 덮어쓰지 않았다.

## 아직 남은 작업 — 로봇 없이 진행할 수 있음

1. **일반 채팅의 서버 소유 유료 승인 manifest와 현재 질문 하나:** 현재 입력·사진·공급자/origin·모델·정책·검증된 단가·전체 context 예약·요청/비용 한도를 표시하고 명시 승인 후 `OrdinaryInferenceScope`를 만든다. 지금은 trusted 내부 adapter만 있으며 일반 HTTP/채팅은 이 scope를 만들지 않는다. 과거 campaign이나 브라우저의 임의 scope를 신뢰하면 안 된다.
2. **일반 checkpoint 재개와 불명 결과 정산 UI:** 현재 checkpoint 선택·새 승인·재검증·기존 누계·새 예산을 구분하는 UI/API가 필요하다. backend 재개만 검증됐다. late 정산 이후 persisted checkpoint와 ledger의 상태를 안전하게 대조하는 제품 경로도 남았다.
3. **중간 장면 계약의 범위 확대:** 새 계약은 home/common의 기존 종류를 사용한다. warehouse rack/pallet stack, 임의 벽·문/창문 opening, 기존 New/Add/Change의 모든 입력 의미와 실측 입력 version을 새 단계 경로에 연결하는 인수는 미완료다. 기존 라이브러리·편집 기능이 없어졌다는 뜻은 아니다.
4. **최종 실제 렌더 검토:** 렌더 이미지 critic의 별도 승인·계약·예약·유효성 검사가 아직 없다. `external_final_review=true`는 조용히 무시하지 않고 호출 전에 거절한다. 60초 reserve가 실제 외부 리뷰까지 구현됐다는 뜻은 아니다.
5. **S5/S6 실제 모델 인수:** 위 승인 연결 후 새 범위로 GPT 관측→Nemotron 단계별 생성/오류 수정→동일 저장/Isaac 경로를 평가한다. 다른 방·텍스트·명시 치수·편집/되돌리기도 포함해야 한다. 이번 fixture PASS를 실제 모델 성공률로 바꿀 수 없다.
6. **최종 패키지 및 별도 현장 인수:** 이전 패키지의 PASS는 이번 source의 패키지 PASS가 아니다. 사진 정밀도·실측·로봇 LiDAR 정합·실물 자율주행·물리 정지는 별도 미검증이다.

계획 상태는 S0 확인, S1 budget/adapter 오프라인 검증·승인 UI 잔여, S2 중간 계약 일부 구현, S3 backend 단계 생성/재개 검증·일반 재개 UI 잔여, S4 fixture 기반 실제 App/Isaac 검증·일반 유료 경로 인수 잔여, S5/S6 NOT_RUN이다. **S0–S4 전체 완료나 전체 데모 준비 완료로 표시하지 않는다.**

## 재현

기존 가상환경을 사용한다. 명령은 유료 호출이나 로봇 명령을 포함하지 않는다.

```powershell
Set-Location C:\Users\jaewo\Documents\TwinPulse
$env:PYTHONPATH='C:\Users\jaewo\Documents\TwinPulse\packages\twinpulse_core\src;C:\Users\jaewo\Documents\TwinPulse\packages\twinpulse_provider\src;C:\Users\jaewo\Documents\TwinPulse\packages\twinpulse_app\src'
.\.venv\Scripts\python.exe -m unittest discover -s packages/twinpulse_provider/tests
.\.venv\Scripts\python.exe -m unittest discover -s packages/twinpulse_core/tests
.\.venv\Scripts\python.exe -m unittest tests.integration.test_stage_routing_settings tests.integration.test_chat_conversation tests.integration.test_chat_site_text_generation tests.integration.test_execution_diagnostics tests.integration.test_r5_product_api tests.integration.test_scene_changes tests.integration.test_provider_key_registry
.\.venv\Scripts\python.exe scripts/verify_budgeted_generation_replay.py
```

Actual harness는 기존 Isaac 설치와 비어 있는 별도 output 경로가 필요하다. 과거 output에 덮어쓰지 않는다. 실행 전 다른 사용자의 Isaac을 종료하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/verify_chat_sim_journey.py outputs/budgeted-recovery-isaac-new-run --case text --site-transport-fixture --budgeted-fixture --diagnostics --library-models
```

실물 guard(scan 200ms/input 250ms/segment 50ms/.03m/s/.20rad/s/45s), physical mission 잠금, v1/v2 계약, 과거 raw/FAIL/장부/dirty 변경과 예약 PAUSED를 보존했다. 전체 준비 상태는 `whole=false`다.
