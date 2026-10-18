# TwinPulse 단계별 생성과 예산 기반 수정 루프 구현 계획

현재 v1.0.374 **실제 새화면 생성 FAIL·진단/UI 감사 PASS·전체 PARTIAL**: [결과](../verification/staged-repair-live-ten-20261009.md). 새일반승인1/USD1·GPT관측PASS/Nano구조lengthFAIL=2/10, 실제20000/no-thinking·JSON미완성뒤공백32263자·출력소진즉시중단/남은8미사용/repair0. 로그2/화면2/실행ID·SHA·usage·원본불변/종료PASS, actual 수정/compile/새저장/새IsaacNOT_RUN·S5/S6미완료. 모델/구조화decoder호환성원인분리가다음이며 추가한도/동일반복안함. 전체harness권한거절0calls뒤generation-only검증·로봇/Isaac0·제품생성source불변. 아래 v373 이하는 당시 이력이다.

현재 v1.0.373 **v372 발견결함 제품수정/offline PASS·전체 PARTIAL**: [검증기록](../verification/staged-repair-evidence-fixes-20261009.md). structure 오류경로/직전후보·ID·최신오류/동적 관측목록과 출처/세부대상 개선판정, 실제송신요청·후보검사·수정판단·compiler 로컬증거 및 API/UI 전체호출이력32개가 연결됐다. Provider210/통합181/Web437/type/build PASS·원실패4 재생은동일보호중단·원본불변. 실제GPT→Nano 회복과 새장면App→Isaac 인수는 NOT_RUN이며 S5/S6 미완료다. 추가토큰·유료호출·로봇·Isaac승인을 이번구현으로 확대하지 않는다. 아래 v372 이하는 당시 이력이다.

현재 v1.0.372 **점검 완료/제품 수정 대기·PARTIAL**: [실패 요청 재구성 감사](../verification/ordinary-staged-request-audit-20261009.md)로 Nano본문/schema3개 모두 당시 해시 일치, 관측 전달을 확인했다. 우선 보완은 오류경로 inventory/objects 정합화·직전 실패 후보 전달·동적 관측계약·부분 개선 척도·전체 호출/요청/검사 로그다. 합성14→7→1도중단, API첫3개절단을 재현했다. 새 유료·로봇·Isaac0이며 아래 v371 실패와 기존 인수 미완료를 유지한다.

현재 v1.0.371 **PARTIAL**: [새 일반 채팅 실제모델 max10 시험](../verification/ordinary-staged-live-ten-20261009.md)은 4요청에서 관측14물체→Nano inventory1개/수정2회 비진전으로 실패했다. 출력·시간 한도는 이번 표본에서 소진되지 않았다. S5 실제 성공 인수 FAIL, S6 전체 인수 미완료이며 아래 v370까지의 고정응답 PASS를 실제 생성 PASS로 승격하지 않는다. 우선 개선은 범용 관측 inventory/근거 결속 및 실제 수정 회복이다. 이하 문서의 승인 범위와 이전 이력은 보존한다.

작성일 2026-10-09 KST. 실행 담당 6.1 Sol. 출발점은 Baseline v1.0.367이며 v1.0.368은 이 계획의 문서 등록이다. 작성 당시 상태는 PLAN_ONLY였으며 제품 코드·외부 실행은 없었다. 사용자 후속 구현 지시에 따른 현재 상태는 **v1.0.370 제품 연결 PARTIAL**이다. [v369 기반 구현](../verification/budgeted-generation-foundation-20261009.md) 이후 [일반 채팅 승인·checkpoint 재개 및 실제 Isaac 검증](../verification/ordinary-generation-approval-resume-20261009.md)을 추가했다. 일반 승인 UI/API·새 승인 미완료 재개·UNKNOWN 원응답 대조는 연결했지만 warehouse/openings/전체 편집 계약·렌더 critic·신뢰 가격 갱신·S5/S6 실제 모델 인수·패키지/현장은 미완료다. S0–S4 전체 완료로 해석하지 않는다. 실제 모델/사진 전송은 이번 승인 연결 구현만으로 승인되지 않는다.

목표는 사진 또는 글에서 편집 가능한 3D Twin을 만들고, 잘못된 결과를 스스로 검사·수정하여 실제 App과 Isaac에서 사용하는 것이다. 출력 한도 변경이나 JSON 한 건 성공으로 끝내지 않는다. 생성·수정 결과가 저장, 현재 3D 표시, SIM 실행까지 같은 revision으로 연결돼야 한다. 이후 로봇의 LiDAR 보정과 주행에 필요한 출처·좌표·불확실성 정보도 보존한다.

## 1 사용자 의도와 권한

이번 방향을 결정한 사용자 원문:

> 그게 근본원인 해결이 맞아? 내 최종 목적에 맞는?
>
> 그래 한도나 횟수도 다시 고민해봐
>
> 그래 진행하는 상세계획을 짜면 6.1Sol에 시킬게

이번 작업에도 적용되는 기존 요구 원문:

> 방을 10x12m 로 추정할수도 있지 내가 정확한 규격을 준적이 없는데. 그건 실패가 아니야
>
> 먼저 놓은 물체 배치는 되돌릴 수 있어야지
>
> 아무튼 지금 하드코딩으로 내 사진에만 맞게 되어있는 내용들은 싹 지워라. 그리고 성공판단은 좀 여유롭게 잡아도 될거같다. 어차피 로봇이 돌아다니면서 라이다로 재검증할거니까
>
> 아니 사진은 GPT로 하고 설계랑 수정은 Nemotron으로 하라고.
>
> Nemotron 출력한도 설정은 너가 한거지? 8000토큰이 아니라 20000토큰으로 해주고 앞으로 이러한 출력제한 문제가 있으면 바로 멈춰줘라. 그리고 아까 만든 설정에도 토큰 한도 설정 직접 할 수 있게끔 넣어주고

이 계획은 [채팅 중심 12단계 데모 계획](TWINPULSE_CHAT_DRIVEN_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-05.md)을 축소하지 않는다. ChatGPT형 채팅, 현재 질문 하나, 사진 선택 사항, SIM/REAL 분리, 우측 접이식 실제 3D, 파라미터 가구 라이브러리, 명시적 Run·실물 Confirm·Stop을 유지한다. 기존 [신뢰성 계획](TWINPULSE_AGENT_RELIABILITY_NEMOTRON_SOL_PLAN_2026-10-07.md)의 단일 수정·단일 총시간 정책은 새 정책 적용 범위에서 대체한다. 과거 문서·실패·원응답은 이력으로 보존한다.

권한은 다음과 같이 구분한다.

- **계획 작성 당시 승인:** 상세계획서 작성, Baseline/Memory의 문서 상태 동기화. 이후 사용자가 “좋아 진행하자”로 제품 구현·무과금 회귀/허용된 로컬 Isaac 검증을 지시했다.
- **후속 구현 지시 후:** 기존 제품 코드와 오프라인 회귀, 허용 범위의 로컬 App·실제 Isaac 검증. 안전하게 진행 가능한 단계마다 사용자에게 다시 진행을 묻지 않는다.
- **별도 실제 호출 승인 필요:** 입력 사진·렌더 이미지, 공급자·모델·목적, 요청·비용 상한, 시간·출력 설정을 결속한 범위. 아래 12회는 설정 제안이지 새 유료 호출 승인이나 과거 잔여 3회 사용 승인이 아니다.
- **포함되지 않음:** 로봇 SSH/serial/센서/모터/전원/배포/실물시험, 설치·시스템 변경, 새 유료 서비스, commit/push, 타 프로세스 강제 종료, 다른 채팅에 작업 발송. 로봇 OFF로 간주한다.

키·인증 헤더를 출력하지 않는다. 기존 보안 저장소와 공급자별 origin 검사를 유지한다. 모델이 작성한 임의 Python/shell을 실행하지 않는다. 생성 시간 변경을 로봇의 정지·입력·센서 watchdog 변경에 적용하지 않는다.

## 2 확인된 원인과 미검증 사항

| 확인 사실 | 근거 | 개선 방향 |
|---|---|---|
| 최근 Nano는 실제 20,000토큰 요청에서 89.453초에 한도를 소진하고 최종 JSON 없이 length로 종료했다. | [300초 시험](../verification/saved-stage-300s-five-20261009.md) | 설정 미저장이나 300초 만료가 아니다. 추론·최종 응답 소진을 구분한다. |
| 이전에는 JSON을 받았지만 scene-1과 call-1의 근거 참조가 달랐고, 수정은 총 90초 뒤 도착했다. | [20,000토큰 시험](../verification/saved-stage-20000-five-20261009.md) | 출력·계약·시간 배분 오류를 각각 해결한다. |
| 일반 builder는 max_repairs=1, provider는 0/1만 허용하며 수정 때 전체 JSON을 다시 요구한다. | `stage_routing.py`, `nebius_pipeline.py` | 작은 단위 생성·부분 수정을 위한 계약과 공통 예산이 필요하다. |
| 총 deadline, transport timeout, 서비스 wait_for가 같은 timeout을 사용한다. | `stage_routing.py`, provider `service.py` | 호출별 대기와 작업 전체 시간을 분리한다. |
| Nano template no-thinking은 provider에 있지만 일반 builder에서 전달하지 않는다. | `nebius_pipeline.py`, `stage_routing.py` | 실제 wire 옵션을 설정·UI·진단에 연결한다. |
| 과거 no-thinking의 JSON·SIM 성공에는 compact·검토 목록·위치 제약 조건이 섞여 있다. | [출력 시험](../verification/photo-output10000-20261007.md), [형상 시험](../verification/photo-geometry-live-20261007.md) | 과거 목록·치수를 일반 제품 정답으로 되살리지 않는다. |
| 일반 builder는 host 평가 campaign을 거절하고 실제 시험은 별도 host 장부 조합을 쓴다. | `build_configured_stage_service`, `verify_saved_stage_live.py` | 일반 App에도 같은 예산 원칙을 연결하되 승인 경계를 우회하지 않는다. |

위 증거는 출력 소진과 계약·시간 배분 결함을 보여준다. Nemotron이 모든 작업에 부적합하다거나 추론 끄기만으로 방 복원이 정확해진다는 근거는 아니다. 사진의 실측 치수·가려진 장애물 전체·범용 생성 성공률은 미검증이다.

## 3 코드 연결 지점

경로는 기준 저장소 상대 경로다. 새 helper는 기존 계층 안에 두고 역할이 같은 별도 프레임워크나 시험 전용 생성기를 만들지 않는다.

| 책임 | 현재 파일 | 변경 내용 |
|---|---|---|
| 일반 생성 설정 | `packages/twinpulse_app/src/twinpulse_app/stage_routing.py`, `scripts/twinpulse_backend.py` | 버전 있는 실행 정책, 실제 wire, 공통 예산 주입 |
| 모델 실행 | `packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py`, `stage_transport.py`, `contracts.py`, `service.py` | 관측·설계 단위·수정 분리, 중첩 retry 제거 |
| 비용과 요청 기록 | `packages/twinpulse_provider/src/twinpulse_provider/reliability.py` | AuditedChatTransport/CampaignLedger/InferenceEvidence 확장, 일반 승인과 평가 승인 분리 |
| 의미 계약과 compiler | `packages/twinpulse_provider/src/twinpulse_provider/scene_contract.py`, `photo_layout.py` | 범용 장면 의도, revision patch, ID/evidence 동시 생성 |
| 라이브러리와 검사 | `packages/twinpulse_core/src/twinpulse_core/model_library.py`, `tool_catalog.py`, `site_tools.py`, `site_contracts.py`, `photo_quality.py`, `photo_placement.py` | 실제 모델·회전·지지·출처·범용 배치·되돌림 |
| 제품 상태와 저장 | `packages/twinpulse_app/src/twinpulse_app/application.py`, `product_workflow_service.py`, `conversation_service.py`, `session_journal.py` | checkpoint·취소·재개·현재 단계·revision 결속 |
| 화면 | `apps/twinpulse-web/src/ApiKeySettings.tsx`, `ChatWorkspace.tsx`, `conversation-types.ts` | 호출/전체 한도, 수정 횟수, 단일 진행 카드 |
| 진단 | `packages/twinpulse_core/src/twinpulse_core/execution_diagnostics.py`, 기존 진단 API/UI | 동일 실행 ID로 요청·수정·Build·frame·비용·병목 연결 |
| 실제 인수 | `scripts/verify_saved_stage_live.py`, `verify_chat_single_step.py`, `verify_chat_sim_journey.py`, 기존 audit scripts | 일반 제품 정책의 offline/live/actual Isaac 모드 분리 |

`photo_layout.py`의 범용 재배치·attachment·compiler를 재사용한다. 기존 compact 정책을 무조건 켜지 않는다. `room_photo_inventory.py`와 과거 quality fixture의 사진별 검토 정보는 평가·이력으로 구분하고 일반 입력에 자동 주입하지 않는다.

## 4 생성 구조와 성공의 경계

`입력 고정 → 사진 관측 또는 텍스트 해석 → 공간 구조 → 연결된 물체 묶음 → 결정적 변환과 검사 → 부분 수정 → 전체 검사와 시각 검토 → 후보 확정 → 실제 Build와 현재 frame → 명시적 SIM Run`

### 4.1 모델의 판단과 프로그램의 책임

버전 있는 중간 장면 표현을 도입한다. 다음은 의미 계약이며 실제 필드명은 기존 계약과 검증기를 확인해 확정한다.

- 공간: 추정 가로·세로·높이, 벽·개구부, 기준 좌표계·단위. 치수마다 estimated/explicit_user/measured를 구분한다.
- 물체: host가 결속한 안정적 entity ID, 종류, library family/model, width/depth/height, variant/finish, yaw, 배치와 근거 참조.
- 관계: 바닥 위, 다른 물체 위, 내부, 벽·천장 부착, 걸린 상태 등의 타입과 parent/part/offset/근거.
- 불확실성: 정체불명은 unknown, 미측정은 추정이다. 관찰하지 않은 자유 공간·실측·현재 로봇 상태를 발명하지 않는다.

LLM은 무엇을 어디에 어떻게 놓을지 제안한다. 프로그램은 아래를 담당한다.

1. 같은 entity 매핑에서 `call_id`와 `call_evidence`를 함께 생성한다. LLM에게 같은 ID 목록을 두 번 쓰게 하지 않는다. legacy 직접 tool-plan은 엄격히 검증하며 잘못된 참조를 추측 치환하지 않는다.
2. 라이브러리 도구 인자, 단위 변환, 회전 footprint, 접촉면 높이, parent 이동에 따른 자식 좌표, typed tool 호출을 계산한다. 범용 compile이어야 하며 사진별 정답 주입은 금지한다.
3. parent 순환·없는 ID·비정상 수치·미지원 도구·명시 치수 위반·금지된 편집 범위·위험한 collider를 검사한다.
4. home/warehouse/common 파라미터 모델을 적용한다. 침대·옷장 등을 단순 충돌 박스만으로 표시하고 시각 인수 PASS로 처리하지 않는다. 2D 간략 표시는 별도다.
5. v1/v2/Site2.2 저장본·직렬화·hash는 보존한다. 새 표현은 additive version/sidecar를 사용하고 최종 기존 typed plan으로 내린다.

사진은 GPT, 설계·수정은 설정된 Nebius NVIDIA Nemotron을 유지한다. 원본 사진은 사진 모델에만 전달한다. 텍스트-only는 사진 모델을 호출하지 않는다. 시각 검토로 원본과 렌더 이미지를 외부에 전송할 때는 전송 항목을 승인 범위에 명시한다.

### 4.2 분할과 품질 판정

공간 구조를 먼저 만들고 지지 관계가 연결된 물체 묶음·주변 장애물을 나눠 처리한다. 고정 침실 3묶음이나 24개 물체 목록을 강제하지 않는다. parent/child를 끊는 분할이나 묶음마다 방 전체를 다시 생성하는 분할도 피한다. 전체 관측 목록, 유효 후보, 미배치 목록을 공유한다.

상태를 구별한다.

- `DRAFT_INCOMPLETE`: 처리할 물체·검사가 남음. 중간 보기만 가능하며 완료·Run으로 승격하지 않는다.
- `APPROXIMATE_TWIN_READY`: 요청·관측 근거를 충족하는 개략 장면. 추정 치수·불확실성 경고를 보존한다.
- `SIM_READY`: 동일 revision의 actual Build·현재 frame·SIM 경로/robot 조건 통과. Run은 기존 명시 동작으로 시작한다.
- `PHYSICAL_READY`: 이번 계획에서 부여하지 않는다. 실물 정합·센서·정지·배터리·현장 승인 자격이 별도로 필요하다.

치수를 주지 않은 방의 10×12m 추정 자체는 실패가 아니다. 작은 방이나 synthetic region grid 포화만으로 실제 배치 불가능을 확정하지 않는다. solver 탐색 예산 소진은 `PACKING_SEARCH_EXHAUSTED` 등 계산상의 미해결로 구분한다. 추정 공간·기존 배치는 재검토하되 물체를 숨기거나 방을 자동으로 부풀려 검사만 통과시키지 않는다.

사진 픽셀 좌우와 world XY를 동일시하지 않는다. 시점·가림이 불명확한 관계는 경고/불확실성으로, 명백한 출처·형상 오류는 수정 대상으로 분류한다. LiDAR가 나중에 보정한다는 이유로 뜬 가구·잘못된 지지를 무조건 허용하지 않는다. 2D LiDAR가 높이·상부 형상을 전부 검증할 수 있다고 가정하지 않는다.

## 5 호출 시간 비용 정책

### 5.1 개발 검증용 시작값

| 설정 | 제안값 | 의미 |
|---|---:|---|
| 사진 모델 출력 | 4,000 tokens | 현재 값 유지. 모두 소비하는 목표가 아님 |
| 설계 및 수정 출력 | 20,000 tokens | 호출별 상한. 추론 포함 실제 usage 기록, 조용한 축소·증액 금지 |
| 호출별 timeout | 300초 | 외부 요청 한 건의 최대 대기 |
| 전체 active deadline | 900초 | 생성·수정·검사의 총시간. 호출마다 초기화하지 않음 |
| 작업당 외부 요청 | 최대 12회 | 관측·구조·물체·시각검사·수정·재시도 모두 합산 |
| 수정 요청 | 최대 3회 | 모든 단계 공유. 단계마다 3회가 아님 |
| 비진전 중단 | 연속 수정 2회 | 의미 후보·검사 결과에 개선 없음 |
| 자동 transport retry | 0회 | 원격 불명 요청의 자동 중복 전송 금지 |
| 비용 | 실행별 명시 승인액 | 과거 USD1·미사용 횟수를 새 승인으로 추정하지 않음 |

이 값은 시작 기준이며 모든 방에 충분하다는 보장이 아니다. **명시적인 새 정책 저장과 실행 승인 결속**으로 적용한다. 이전 `generation_timeout_s=300`을 읽는 것만으로 호출당300/전체900으로 확대하지 않는다. 기존 파일은 기존 의미대로 읽고 새 정책 저장 시 차이를 표시한다.

전체900/호출300을 동시에 강제한다. 12회 모두 300초씩 실행할 수 있다는 뜻이 아니다. 실제 요청 timeout은 전체 잔여를 넘지 않으며 유효한 대기시간이 부족하면 시작하지 않고 checkpoint를 보존한다. Isaac 초기 준비·사용자 응답 대기·명시적 SIM 주행 시간은 생성 active 시간과 별도 계측하고 총 체감 시간도 표시한다.

### 5.2 예산의 단일 소유자

논리적 생성 작업 하나에 하나의 공통 예산 상태를 둔다. provider 단계·repair·runner·UI가 각각 새 예산을 만들지 않는다. 필수 필드는 execution/generation ID, 정책·승인 ID, 실제 요청 수, 단계별 수, 수정 사용/예약, 누적 active 시간, 비용 추정·예약·정산, in-flight attempt, 종료 이유다. 기존 장부의 배타 잠금·원자성·손상 검사를 재사용한다.

1. dispatch 직전 provider/model/origin, 이미지 범위, body cap, 입력 revision, 정책·승인을 확인한다.
2. 횟수·금액·시간을 원자적으로 검사·예약한다. 승인 총량과 작업 설정 중 작은 한도를 적용한다.
3. 실제 HTTP 시도는 실패·불명도 1회다. 로컬 검사·캐시 hit·전송 전 거절은 0회이며 별도 이벤트다. 내부 retry를 숨기지 않는다.
4. 응답 뒤 usage를 정산한다. timeout·취소는 원격 실행/청구 UNKNOWN일 수 있고 예약을 삭제하지 않는다.
5. length·취소·terminal 뒤 큐의 후속 dispatch를 차단한다. 늦은 응답은 장부 정산에만 반영하고 현재 장면에 적용하지 않는다.

현재 CampaignLedger는 전체 model context를 입력 비용 상한으로 예약한다. 그 계산으로 실제 허용 횟수를 사전에 표시한다. 평균 사용액이 낮다는 이유로 입증되지 않은 저렴한 상한을 만들지 않는다. 정확한 상한을 확보하지 못하면 승인액과 가능한 요청 수 차이를 설명한다. usage 추정액과 실제 청구액을 구별한다.

일반 App 승인과 host 평가 승인은 분리하되 같은 예산 알고리즘을 사용한다. 일반 builder의 host campaign 거절을 없애 우회하지 말고 별도의 적법한 scope adapter로 연결한다. 키 선택·설정 저장 자체는 유료 생성 승인이 아니다.

### 5.3 수정과 최종 검사의 예산 예약

- 12회 중 수정용 3회를 먼저 예약한다. 사용한 수정 수만큼 총 잔여와 예약을 함께 줄인다. 초기 생성이 예약을 몰래 소모하지 않는다.
- 외부 최종 시각 검사를 필수로 선택하면 그 1회도 예약한다. 이 경우 초기 일반 요청은 최대8회 안에서 구성되지만 실제로는 더 적게 쓰는 것이 바람직하다. 외부 검사도 무료 추가 호출이 아니다.
- 시간은 초기 생성540초, 수정 여유300초, 로컬 마무리·적용 확인60초를 시작 배분안으로 둔다. 수정3회 각각300초를 보장하지 않는다. 수정 불필요가 확정된 뒤에만 예약을 해제한다.
- dispatch 전 같은 단계의 실제 지연과 남은 시간을 비교한다. 초기 검증에서는 수정 시작 여유를 최소90초로 두어 과거 19초 남기고 수정 시작하는 사례를 막는다. 값은 정책·진단에 표시하고 측정 후 명시 조정한다. 승인 기한은 자동 확대하지 않는다.
- 처리할 물체/검사가 남고 최소 예산이 부족하면 `NEEDS_BUDGET`와 미완료 목록을 남긴다. 큰 방은 추가 승인 후 이어갈 수 있다. 객체 생략·미검증 PASS로 한도를 맞추지 않는다.

### 5.4 추론 옵션

기존 `planner_template_no_thinking`을 일반 설정·실제 body에 연결한다. 지원이 확인된 Nano 모델에만 default/disabled를 제공한다. SDK의 extra_body와 raw HTTP 최상위 chat_template_kwargs를 혼동하지 않는다. wire 검사로 최초 설계·수정의 일치 여부를 확인한다.

미확인 provider에 reasoning_effort=none이나 임의 숫자 추론 예산을 공통 전송하지 않는다. OpenAI와 Nebius 옵션은 provider별로 분리하고 unsupported는 전송 전에 거절한다. disabled는 명시 시험 설정으로 사용할 수 있으나 JSON 성공과 장면 품질을 각각 측정한다. 품질 실패 시 모델·추론 모드를 자동 변경하지 않는다. 비교 시험도 별도 승인 범위에서만 한다.

## 6 검사 수정 재개 규칙

### 6.1 검사와 실패 분류

형식·ID·parent 순환·수치·회전 footprint·접촉/지지·출처·편집 범위는 프로그램으로 검사한다. 사진 대조는 실제 현재 revision 렌더와 원본 관측을 근거로 한다. 모델의 looks_good=true만으로 합격시키지 않는다.

검사 보고서는 code, object/field path, severity, source, expected/observed, uncertainty, dependent 항목을 포함한다. 독립 오류를 한 번에 모으고 선행 오류 때문에 못 한 검사는 blocked로 남긴다. 물체를 조금 바꿀 때마다 전체 외부 모델 재검사를 부르지 않는다. 최종 판정은 수정 후 revision에 대한 것이어야 하며 수정 전 critic 결과를 재사용하지 않는다.

| 분류 | 예시 | 처리 |
|---|---|---|
| 즉시 중단 | 출력 length, 인증/결제/모델 미지원, 요청 schema 400, 비용·횟수 한도, 사용자 취소 | 후속 모델 요청0, 원인·원응답·checkpoint 저장 |
| 결과 불명 | timeout, 연결 단절 후 원격 완료 불명 | UNKNOWN 예약 유지, 조회/정산 후 명시 재개. 자동 retry 없음 |
| 수정 가능 | 완성 응답의 형식·source 참조·겹침·지지·library 인자 오류 | 공통 수정 예산 안에서 해당 단계·연관 물체 수정 |
| 추정 경고 | 미실측 크기, 가림, 애매한 재질·시점 | 경고 보존. 실측 또는 실물 권한으로 승격하지 않음 |
| 엔진 실패 | Build/현재 frame/저장 실패 | 엔진·저장 진단과 transaction 복구. LLM 재생성으로 숨기지 않음 |

완성 응답의 형식이 잘못되면 필요한 해당 단계의 전체 응답을 다시 받을 수 있다. length 응답은 이 규칙에 포함하지 않는다. 잘림을 일반 JSON 오류로 바꿔 repair를 호출하는 회귀를 금지한다. 소프트 품질 경고 때문에 무한 수정하거나, 확실한 물체 누락·지지 오류를 경고로 낮춰 성공시키지 않는다.

### 6.2 수정 거래와 되돌림

새 typed patch는 base revision·대상 entity를 결속한다. 허용된 add/update/remove/reposition/reparent/추정 공간 변경을 지원하되 자유 JSON path나 도구 이름을 실행 권한으로 사용하지 않는다.

1. 실패 후보, 마지막 검증 후보, 현재 적용 장면을 각각 보존한다.
2. 실제 오류와 관련 물체·관계만 수정 컨텍스트로 보낸다. 원본 요구·확정 제약·전체 미완료 목록은 유지한다.
3. patch의 base revision과 범위를 검사한다. New의 추정 배치는 주변 물체와 함께 재계획할 수 있다. Add/Change는 지정 범위를 지키고 범위 확대가 필요하면 질문 하나로 확인한다.
4. 후보 복사본에서 parent/child 영향을 함께 계산하고 전체 검사를 다시 한다. 구조가 바뀌면 기존 SIM 경로를 폐기·재계산한다.
5. 유효하면 checkpoint를 원자적으로 저장한다. 실패하면 마지막 유효 상태를 보존하고 새 실패를 별도 기록한다. 엔진 표시 후보도 검증된 복구 revision으로 되돌릴 수 있어야 한다.

삭제에는 중복·오검출 또는 명시 삭제 근거가 필요하다. 배치가 어렵다는 이유로 장애물을 지우지 않는다. 치수 축소·방 확대는 미측정 제안으로 기록·재검사하며 명시 치수는 지킨다. 임시 침실 좌표나 고정 가구 배열을 복구 답안으로 넣지 않는다. 원래 올바르던 물체를 옮길 수는 있지만 이유·변경 범위·재검사 결과를 남긴다.

### 6.3 진전 판정

표현 순서·ID만 바뀐 결과를 진전으로 보지 않는다. 정규화 의미 hash, blocker 집합, coverage, 관계 위반과 새 오류를 비교한다. 오류 문장 변경으로 카운터를 초기화하지 않고 A→B→A 진동도 탐지한다.

blocker 해결·누락 복구가 있고 동급 이상 결함이 새로 생기지 않으면 진전으로 기록한다. 최초 실패는 수정 비진전1회로 세지 않는다. 연속 수정2회 비진전은 REPAIR_STALLED, 전체 수정3회 소진은 REPAIR_LIMIT_REACHED로 구별한다. 동일 객체에 다른 오류가 생긴 경우와 실제 개선을 테스트로 확인한다.

### 6.4 관측 캐시와 checkpoint 재개

관측 키는 이미지 hash, 관련 사용자 설명, observer 모델/설정/prompt/schema, 승인된 입력 범위를 포함한다. planner만 바뀌면 유효성 확인 후 관측을 재사용할 수 있다. observer 정책·원본이 바뀌면 해당 캐시는 무효다. 캐시 hit는 새 모델 성공 표본이 아니다.

checkpoint에는 parent execution, 입력/후보 revision, 정책·compiler/library/schema 버전, 관측 출처, 완료/미완료 단계, 예산 이력·UNKNOWN 예약을 저장한다. 코드·library 변경 시 재컴파일·재검사하며 바로 유효로 복원하지 않는다. hash 손상·저장 실패는 마지막 유효 상태를 보존하고 정확한 오류로 종료한다.

재개는 사용자 동작과 현재 승인 범위가 필요하다. 추가 승인 시 기존 이력을 지우지 않고 연결된 continuation을 만든다. 누적 active 사용량·호출·비용과 이번 추가 허용량을 구분한다. 설정 저장·새로고침·프로젝트 재열기만으로 유료 요청·Build·SIM Run·로봇을 재개하지 않는다. UNKNOWN은 먼저 정산/소유권 확인하고 새 요청으로 덮지 않는다.

## 7 화면과 통합 진단

기존 영어 제품 UI를 유지하고 개발 보고서는 한국어로 작성한다. 사용 화면을 개발자 콘솔로 바꾸지 않는다.

- 현재 단계 하나를 중심으로 Understanding the photo, Planning the room, Placing objects, Checking the scene, Adjusting the layout 1 of 3, Building 3D, Ready to simulate를 실제 상태에 맞게 표시한다.
- 자동 진행 중 단계별 클릭을 요구하지 않는다. 취소와 기존 Stop/Force STOP은 독립적으로 접근 가능하다. 예산 추가·재시도·모호한 조건 등 현재 필요한 결정 하나만 제시한다.
- 세부 펼침에는 API requests 6/12, Repairs 1/3, 경과/잔여 시간, 비용 추정/미확정 예약, 종료 이유, 실행 ID를 표시한다. 호출 수를 완성된 방 개수처럼 표시하지 않는다.
- 기존 설정창에서 모델 조합, 출력 상한, Nano 추론 모드, 호출별/전체 시간, 요청 상한, 수정 상한을 명시 저장한다. 현재 실행은 시작 당시 snapshot을 사용하고 도중 변경을 반영하지 않는다.
- 수정 상한이 총 요청보다 크거나 예약 뒤 최소 초기 호출도 불가능하면 시작 전에 부족한 조건을 알려준다. 설정값과 승인으로 실제 허용되는 값이 다르면 둘 다 표시한다.
- 우측 3D는 현재 적용 revision과 frame 시각을 보여준다. 중간·과거 장면은 그렇게 표시한다. 새 Build를 시작했다는 이유로 옛 frame을 현재 결과로 표시하지 않는다.
- 실제 조건 충족 뒤에만 Run을 활성화한다. 생성 취소와 로봇 Force STOP의 의미를 혼동시키지 않는다.

진단은 기존 execution ID를 이어 쓴다. stage/attempt/parent ID, 최초/수정, 입력·정책 hash, 모델·실제 wire 설정, HTTP/finish_reason/usage/final-content 유무, 검사 code, patch 전후 hash, 저장/Build/frame receipt를 연결한다. 자격증명·이미지 data URI·비공개 추론 내용을 채팅·보고서에 출력하지 않는다. raw 응답은 기존 접근/크기 제한 로컬 evidence 정책을 따른다.

네트워크 대기, 파싱, 검증, 배치 탐색, compile, 저장, Build, frame 대기를 별도 계측한다. 함수별 CPU profiler는 기존 opt-in 기능을 재사용한다. 느린 외부 호출을 CPU 병목으로 보고하거나 profiler를 상시 켜 제어에 간섭하지 않는다.

## 8 순서대로 구현할 완료 단위

### S0 기준 고정과 무과금 재현

AGENTS, 최신 Memory/Baseline, 이 계획, 20,000/300초 검증 기록을 읽는다. 다른 실행과 dirty 변경을 확인하고 비밀 없는 source/설정 snapshot·회귀 상태를 남긴다.

원응답을 바꾸지 않는 로컬 replay로 length+본문 없음, call/evidence 불일치, late 응답, 동일 후보 재수정 실패를 재현한다. 유료 기준 시험을 먼저 반복하지 않는다. 과거 시험과 현재 일반 App 조합의 차이를 기록한다.

완료: 실패별 재현과 변경 대상 지도. replay를 새 모델 성공으로 집계하지 않는다.

### S1 공통 실행 정책과 예산

정책 계약·명시 마이그레이션, 호출/전체 시간 분리, 원자적 예약/정산, 수정/최종 검사 예약, no-thinking wire 연결을 구현한다. provider의 0/1 repair 제한과 전체 wait_for를 각각 늘리는 데 그치지 않고 공통 소유자로 합친다. 자동 transport retry0와 출력 잘림 즉시 중단을 유지한다.

완료: 외부 호출 없이 12회 경계·공통 수정3·비진전2·시간 배분·금액 부족·UNKNOWN·중복 worker·late·설정 호환 검사 PASS. UI 값과 실제 body가 일치한다. 상한만 바꾼 상태는 이 단계도 완료가 아니다.

### S2 중간 계약과 compiler

기존 library/photo_layout를 활용해 공간·물체·관계·출처 계약, ID/evidence 동시 생성, 부분 후보와 최종 Site2.2 구분을 구현한다. parent 변경·삭제·rollback과 범용 재배치를 검사한다. 사진 정답 주입, grid 포화를 물리 불가능으로 오인하는 제품 경로를 제거한다.

완료: 텍스트 침실·거실·창고, 크기 변경, 밀집 배치, 지지·부착, 가림/unknown, New/Add/Change를 검증한다. 명시 치수와 추정 치수를 구분한다. 현재 Site2.2 trusted measurement 입력 제한도 지원 여부를 명확히 처리하고 조용히 무시하지 않는다. actual library mesh를 별도로 확인한다.

### S3 단계 실행과 수정과 저장

관측 재사용, 공간/물체 묶음, 결정적 전체 검사, 필요 시 시각 검사, patch repair, 진전 판정, checkpoint/재개를 일반 생성 경로에 연결한다. observer/planner가 각각 독립3회씩 수정하지 못하게 한다. 실패마다 방 전체를 재생성하는 경로를 기본으로 삼지 않는다.

완료: 실패→patch→재검사 성공, rollback, 수정3 소진, 비진전2, parent 영향, 취소·재시작·승인 후 재개를 오프라인 통합 검증한다. 중간 저장을 최종 PASS와 구별한다.

### S4 채팅과 actual 3D와 진단

일반 App/API에 상태·설정을 연결하고 production Web build로 검증한다. 현재 진행/질문 하나, revision, 저장·재열기, Twin 접기, 원인·재개 동작·실행 ID를 일관되게 만든다. 기존 진단 화면에 전후 비교·계수·병목이 연결돼야 한다.

완료: built browser→일반 API→actual 로컬 Isaac에서 fixture 생성·수정·Build·현재 frame·명시 Run·Stop·재열기를 검증한다. fixture LLM과 actual Isaac의 근거를 분리한다. Isaac이 준비되지 않으면 독립 코드/UI는 계속하고 runtime만 NOT_RUN으로 남긴다.

### S5 승인된 실제 모델 인수

S1–S4 통과 뒤 입력·모델·실제 cap/시간·횟수·비용·사진/렌더 전송 범위를 담은 manifest로 실행 승인을 확인한다. 현재 문서는 그 승인이 아니다. 키·공급자를 몰래 바꾸지 않는다.

첫 목표는 자연 사진 한 건의 최초 생성과 필요한 자동 수정, 동일 결과의 actual App/Isaac 연결이다. API최대12는 제안 상한이며 성공하면 잔여를 채우지 않는다. 처음부터 성공하면 일부러 망가뜨리지 않는다. 수정 시험은 별도 controlled recovery 조건으로 분리하고 그만큼 예산을 배정한다.

최종 major object/배치·지지·library 모양, 추정 치수, 원응답, current frame, SIM Run/Stop을 확인한다. 출력 잘림이면 실행과 후속 자동 batch dispatch를 즉시 멈춘다. 오프라인 진단은 계속할 수 있다.

완료: 자연 생성과 통제 수정의 분리된 실제 근거. 한 건 PASS를 일반 성공률·실물 데모 완료로 확대하지 않는다.

### S6 다양성 검증과 최종 인수

유효한 추가 승인 범위에서 text-only, 다른 배치/환경 사진, 명시 크기, 애매한 사진, 기존 장면 편집을 검사한다. 부족한 조건은 NOT_RUN이며 호출을 소진하기 위해 반복하지 않는다.

모델 응답을 사람이 고쳐 성공으로 만들지 않는다. 일반 앱의 저장 모델 설정·정책으로 실행되어야 하며 host mock metadata로 UI 인수를 대신하지 않는다. 최종 source/Web/정책·library revision과 actual receipt를 결속하고 문서를 동기화한다.

완료: 구현/오프라인/실제 모델/actual Isaac/실물 미검증을 구별한 종합 보고. 재현 입력·실행 방법·정확한 잔여가 있어야 한다. 문서 추가나 회귀 개수만으로 끝내지 않는다.

## 9 필수 검증 목록

| 범주 | 확인할 경우 |
|---|---|
| 설정 | 구90/300초 총시간 의미, 새 정책 명시 저장/재시작, busy 변경, key/provider/origin, 잘못된 값 전송 전 거절 |
| 출력 | 20,000 실제 wire, 최초/수정 같은 옵션, unsupported 거절, length+empty/partial 즉시 중단, 추론 내용 미출력 |
| 계수 | 12번째까지/13번째0, 실패도 계수, 캐시0, 공통 수정3, 시각검사 포함, 비용 예약·UNKNOWN·경쟁 dispatch |
| 시간 | 약71초+수정19초의 fake clock 재현, 호출300/전체900, 부족 시 미전송, 수정3×300 보장 오표시 금지, late 미적용 |
| 계약 | compiler ID/evidence 일치, 없는 parent/순환, 비정상 수치, schema 복사/역할 혼동/미지원 도구 |
| 일반성 | 사진 hash/침실2 좌표/24개 목록 무주입, text-only 이미지0, 거실/창고, 축소·확대, 밀집 배치와 탐색 예산 구분 |
| 형상 | actual parametric mesh, width/depth/height/yaw, 지지면·부착, 의도된 포함과 고체 충돌, 누락/unknown |
| 수정 | 부분 수정, 전체 구조 재배치 필요, New/Add/Change 범위, parent 영향, 실패 rollback, 진동/비진전, 3회 후4번째0 |
| 재개 | backend 종료 후 복원, source/library 변경 재검사, 승인 연장 이력, 장부·실패 보존, 저장 실패/손상, 재열기 자동실행0 |
| UI | 현재 단계 하나, 수정 중 클릭 불필요, 취소·Force STOP, stale frame 구분, 모바일·중복 클릭·계수 일치 |
| 제품 | 일반 설정→실제 모델→검증 후보→저장→actual Build/frame→명시 Run/도착/Stop→reload 비재실행 |
| 안전 | REAL 준비 실패와 SIM 생성 독립, 생성 예산 변경이 robot watchdog·qualification·임무잠금에 영향0 |

기존 provider/core/integration/Web 회귀와 TypeScript/build를 실행하고 관련 테스트에 새 항목을 추가한다. 실제 호출 없는 wire·clock·failure-injection을 먼저 끝내 유료 호출로 코드 오류를 찾는 낭비를 줄인다. 테스트 개수 자체를 목표로 삼지 않는다.

## 10 실제 시험 조건과 결과 분모

각 조건은 승인된 호출 묶음 안에서만 시행한다.

| 조건 | 방식 | 판정 |
|---|---|---|
| G1 현재 방 사진 | 정답 inventory/위치 주입 없이 GPT→Nano | 최초/수정 후 별도 평가, 치수 실측 미검증 |
| G2 text-only | 사진 없는 거실/창고·지정 물체 | observer0, actual 모델·SIM |
| G3 독립 사진 | 새 승인된 다른 사진, 정답 주입0 | 일반성, 입력 미확보면 NOT_RUN |
| R1 통제 수정 | 일반성 있는 지지/겹침 결함을 명시 주입 | 실제 모델 patch→재검사→actual frame, 자연 성공률에서 제외 |
| R2 편집과 재개 | Change/Undo, 중간 종료·승인 후 재개 | 원본 보존, 불필요한 관측 재호출0, 예산 연속성 |

G1 완성 경로부터 확인하고 부족한 조건을 이어간다. 표 전체를 실행 승인받았다고 해석하지 않는다. fixture는 무과금 실패 제어용이며 실제 모델 표본이 아니다. 평가용 정답은 생성 컨텍스트에 주입하지 않는다.

보고 항목:

- API시도·모델/단계별 수·유효응답·잘림·UNKNOWN·완성 작업 수를 분리한다.
- 최초/수정 후 성공률은 같은 자연 작업 집합을 분모로 한다. 예산 중단·NOT_RUN을 숨기지 않는다. 캐시 재생·통제 수정은 별도다.
- 형식/참조, coverage, 배치·지지, 시각 library 품질, 근거 없는 추가, 실측 여부를 나눠 평가한다. 자기평가 점수 하나로 합격시키지 않는다.
- 성공까지 호출/시간/비용, 수정 사용량, 단계별 대기·CPU·Build, 사용자 추가 클릭 수를 기록한다.
- source/정책/입력/후보 hash, raw 참조, 실패→수정 diff, actual frame·SIM receipt, 소유 프로세스 정리를 연결한다.

## 11 완료 선언과 실물 잔여

다음을 모두 확인해야 이번 생성 개선을 완료로 선언한다.

1. 일반 앱의 사진·텍스트가 같은 예산·수정 정책을 사용한다.
2. 추론 옵션·cap·시간·실제 요청 계수가 설정과 기록에 일치한다.
3. 실제 모델 정상 생성과 적어도 한 건의 실제 수정 회복을 구분된 근거로 확보한다.
4. 수정된 동일 결과가 현재3D·저장·재열기·actual SIM Run/Stop에 연결된다.
5. 한도·취소·UNKNOWN·재시작·rollback 회귀를 통과하고 사진별 hardcoding이 없다.
6. 실측·독립 사진·표본 수·미실행 조건의 한계를 보고한다. 외부 조건으로 3/4를 못 하면 오프라인 완료와 전체 PARTIAL을 구별한다.

로봇 없이 위 생성 구조를 구현·검증할 수 있다. 실물은 별도의 현재 boot/release 초기화·정지시험, scan/odom/TF·driver lifecycle, 현재 방/시작 위치 정합, 짧은 목표·Stop·동적 장애물·배터리/정체·왕복 임무 인수가 남는다. 전원만 켜면 전체 데모가 보장된다고 보고하지 않는다.

## 12 6.1 Sol 전달문

> 기준 저장소의 AGENTS.md, 최신 PROJECT_MEMORY와 BASELINE, 이 계획을 읽고 사용자 구현 지시 후 S0부터 S6까지 의존성 순서로 진행하라. no-thinking이나 토큰·시간·횟수만 바꾸고 완료하지 마라. 기존 일반 App/API/provider/core/Isaac 경로에 단계별 생성, 공통 예산, 관측 재사용, 부분 수정·되돌림, 검증된 checkpoint·명시 재개, 현재 상태 UI·통합 진단을 연결하라. 원본·dirty·과거 실패·장부·구형 계약·실물 안전 잠금을 보존하고 사진 정답을 하드코딩하지 마라. 출력 잘림이면 즉시 후속 모델 dispatch를 중단하라. 공통 수정3/총12회/900초는 명시 정책의 상한이며 새 유료 승인이나 성공 보장이 아니다. 유료 승인 전에도 S0–S4의 독립 구현·무과금 검증을 이어가고 live 항목만 정확히 남겨라. 실제 호출은 입력·목적지·설정·횟수·비용·시간이 결속된 승인 안에서만 시행하라. 모델 응답을 수동으로 고쳐 통과시키지 말고 일반 앱의 실제 모델→저장→현재 Isaac3D→명시 Run/Stop까지 확인하라. 완료·실패·미검증·현장 잔여를 한 번에 보고하라. 안전한 작업이 남았는데 작은 변경마다 다음 승인을 묻지 마라. 새 설치·로봇·배포·타 프로세스 강제 종료·commit/push·다른 채팅 발송은 별도 승인 없이는 하지 마라.

문서 전달은 사용자가 한다. 이 계획 작성 자체로 다른 모델 작업이나 예약 실행을 시작하지 않는다.
