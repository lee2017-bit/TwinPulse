# v359 — 관측·설계 모두 GPT 실제 10회 비교

## 결론

**실제 호출 연결은 성공했지만 사진→유효 장면→Isaac Build→SIM Run/Stop 인수는 실패했다.** 관측 4회는 모두 계약을 통과했다. GPT 설계의 정상 응답 5건은 모두 HTTP200/stop으로 도착했으나 배치 또는 출처 검사를 통과하지 못했다. 자동 수정 2회도 유효한 최종 장면으로 회복하지 못했다. 로봇 명령은 0회이며, 엔진 startup과 장면 Build 성공은 구분한다. 이번 새 장면의 저장/Build/Run/Stop은 NOT_RUN이다.

사용자 승인: “Nemotron도 GPT로 바꿔서 테스트해보자. 총 10회 실시가능”. 원사진과 입력 문장은 직전 비교와 동일하다. 새 고정 응답, 사진별 치수/위치 정답, 물체 누락, 검증기 완화로 성공을 만들지 않았다. 실제 호출은 **10/10: 관측4 + 설계 최초4(그중 API400 1) + 수정2**. 한도 도달 후 수정 요청은 HTTP 송신 전에 거절해 11번째 호출이 없다.

## 공급자·비용·보존

- 두 단계 모두 기존 선택된 OpenAI secure 등록의 `gpt-5.4-mini-2026-03-17`, low, `https://api.openai.com/v1/chat/completions`이다. 사진은 관측 단계에만 전송하고 설계/수정에는 검증된 관측·요청·라이브러리·피드백만 전송했다. [공식 모델/요금](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [구조화 출력 규격](https://developers.openai.com/api/docs/guides/structured-outputs).
- 출력 상한10000, 세션 provider deadline300초, 공통 content repair 최대1. low 추론과 structured JSON을 쓰며 model-generated 코드/명령을 실행하지 않는다. 일반 UI/active key/default legacy adapter는 바꾸지 않은 host-only 평가이다.
- 입력: 기존 승인 사진 SHA `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`, `Create a digital twin of my bedroom with a bed and desk.`. SHA는 전송 승인 확인용이며 생성 정답 lookup이 아니다.
- usage가 있는 9회 추정 비용은 **USD0.12825075**. 최초 API400에는 usage가 없으므로 청구0으로 단정하거나 예약을 환불하지 않았다. 보수적 예약 **USD0.10734**를 유지하여 비용+예약 합계 **USD0.23559075**다. 청구 확정액과 다르다.
- 최초 독립 시험의 자체 예약 상한USD.15는 schema rejection 예약에 묶였다. 사용자10회/기존 총USD1 안에서 자체 예약 상한만USD.50으로 변경한 continuation을 만들고 **기존2회와 비용/예약/attempt ID를 전부 승계**했다. 원 `gpt-provider-10-r1` scope/campaign은 불변이며 SHA/접두 requests를 감사했다. `.continued-to` receipt로 구 장부를 read-only 처리해 중복 승계를 통한 호출 초기화를 막는다. 새 batch10회나 과거 Nebius 장부 초기화가 아니다.
- 기존 Nebius155/219 장부 SHA `ad117283672bea2676e79b20b6917f1a741216829f26598eb1fafc222b5fcbb3`, 혼합10회 장부 SHA `5480a8291c78e6f31ae35fbf9d7462b6fd39c3c375aae27047b4b8d460ef5657` 불변. 원본·실패·dirty·실물 guard·예약PAUSED 보존. 키/Authorization/입력 image body를 응답 로그에 쓰지 않는다.

## 실제 시험

| 실행 | 새 호출 | 직접 확인 결과 |
|---|---:|---|
| live-r1 | 2 | 관측21 entities/15 relations 통과. 설계는 API400: 새 OpenAI 변환기가 숫자 yaw enum을 문자열 type으로 잘못 선언했다. **우리 호환 코드의 결함이며 LLM 품질 실패가 아니다.** 원응답 보존 후 enum/const의 숫자·boolean·nullable 타입을 보존하도록 수정. |
| live-r2 | 3 | 관측17/14 통과. 설계14물체/추정3.5×3m. 의자 rear_centre에 공간 없음; 자동 수정은 middle_centre로 이동했지만 그 구역도 slot0. 책상 위 tabletop_item과 옷장에 drape한 hanging_clothes는 표현했으나 전체 배치 실패. 동일 방 크기를 유지한 채 한 위치만 바꿔 회복 못함. |
| live-r3 | 3 | 관측18/14 통과. 설계14물체/추정3.2×3.6m. 침대·책상은 존재하지만 source=user/빈 observation_ids로 선언해서 관측 e5/e6 미참조. 수정도 같은 출처를 유지해 실패. **물체 누락과 관측 참조 누락은 다르다.** packing/support/photo_relations는 blocked이며 통과로 표시하지 않음. |
| live-r4 | 2 | 일반 출처 우선순위 지침을 보완한 뒤 관측19/15 통과. 설계13물체/추정3.2×2.8m, 출처 검사 통과 후 packing 실패(e9 wardrobe rear_right, e7 chair rear_centre, e12 cable_bundle front_right). 최종 repair는 송신 전 합산10회 제한으로 거절. 공개 최종 메시지는 한도지만 진단에는 **최초 REGION_FULL**이 남음. |

실제 응답 시간: GPT 관측 약6.6~10.3초, 설계/수정의 정상5건 약6.4~7.7초. 직전 Nano의 68.7초 설계보다 이 조건에서 빨랐지만, 추론 모드/응답 길이/관측 내용이 다르므로 일반 성능비율이나 성공률로 주장하지 않는다. 관측 항목 수도21/17/18/19로 달라 모든 소물체 검출을 보장하지 않는다. `dimensions`가 비었거나 null인 것은 실측 정확성이 입증됐다는 뜻이 아니다.

## 남은 근본 병목

1. **추정·배치·검사기의 결합:** 모델이 고른 방 크기, 가구 치수와 image-relative region을 host가 10cm 격자/대리 충돌 형상으로 배치한다. 현재 특정 region에는 모든 물체가 들어갈 수 없는 후보가 나왔다. 기존 bounded 재탐색은 이미 놓은 배치도 되돌리지만 branch cap32/512 nodes/2초 한계가 있다. `BOUNDED_SEARCH_FAILED`는 실물 방에 물체를 배치할 수 없다는 증명이 아니다. 실제 원응답 재검사에서 r2는97/143nodes, r4는15nodes로 재현됐다. 물체를 지우거나 검사기를 끄는 해결은 하지 않았다.
2. **자동 수정의 진전 판단:** r2는 slot0인 구역을 다른 slot0 구역으로 옮겼다. 정확한 `packing_report`는 모델 피드백과 로컬 원인 분석에 포함돼 있다. 실패 region의 단순 변경 대신 전체 추정 크기/치수/기존 배치를 함께 재계획하도록 개선할 필요가 있다. 명시 실측은 유지하고 미측정 추정만 변경해야 한다. 일반 성공률은 별도 승인 fresh 시험이 필요하다.
3. **사용자 요구와 사진 근거의 중복:** source=user 자체는 유효하지만, 같은 물체가 사진에도 보이면 관측 coverage가 별도로 필요하다. r3 뒤 “사진에도 보이면 자기 관측 ID를 인용, user-only는 보이지 않는 요청 물체에 사용”이라는 일반 프롬프트를 추가했다. r4는 이 실패를 지나 packing까지 도달했지만 전체 회복 PASS는 아니다. exact quote 검증은 자연어 의미 전체 검증이 아니다.
4. **표시/진단의 명확성:** 마지막 UI의 한도 오류와 그 앞 후보의 실제 validation failure를 같이 보여주는 개선, field별 독립 오류 진단과 라이브러리 파라미터/packing 분리, source/user/robot 경계의 잔여 작업은 남는다. r3 missing_ids와 r2/r4 packing 상세는 read-only 감사 artifact에 보존했다.

**다음 우선순위는 모델을 다시 바꾸는 것이 아니라 일반 배치/수정 정책과 근거 경계를 개선하고 실제 유효 후보를 확보하는 것이다.** 그 뒤 exact 저장→actual Isaac Build/frame→SIM Run/Stop→수정/Undo→최신 패키지→현장 인수 순서다. 지금 병목을 로봇 OFF나 사용자 전원 준비 부족 탓으로 돌리지 않는다. 추가 호출 승인 없이는 이번 장부로 더 호출할 수 없다.

## 구현·회귀·감사 범위

- 명시 `openai_planner` composition과 `gpt-evaluation-1.0` scope 추가. 같은 모델이어도 schema/stage별로 라우팅하고 planner 이미지 누출/다른 origin/model/Nebius template flag를 송신 전 거절. 과거 mixed scope는 GPT planner 호출을 승인할 수 없다.
- OpenAI wire 변환은 원입력/schema를 복사하며 max_completion_tokens/low와 enum 타입을 보존. 숫자 상수의 원 number 규격도 유지한다. generic library와 기존 host validators/repair1/실물 잠금은 유지.
- ledger에 stage_schema 기록, 이미지/텍스트 각각 보수적인 입력 upper bound와 출력 비용 예약, 공통10회·per-run cap·unknown 유지·원 장부 승계/재사용 거절. raw 감사는 model_id만으로 관측/설계를 판정하지 않고 stage로 구분한다.
- 최종 관련 **72 PASS**, 공급자 전체 **167 PASS**, 문법 compile PASS. 전송 전 Temp sandbox 권한 실패와 schema preflight 시험 코드의 dict/ObservationArtifact 혼동 실패도 별도 기록 보존. 권한 검토를 거친 재실행에서 통과했으며 실패 파일을 덮어쓰지 않았다. core 코드는 바꾸지 않았고 이번 core 전체/Web전체/새 package 재인수는 NOT_RUN이다.
- 최종 `gpt-provider-audit-r2.json` **감사 PASS**: raw10과 ledger1:1/중복0/한도/예약/lock없음/input image 미기록/사용자 설정 불변/각 실제 실행 중 source SHA 불변/승계 접두 불변/구 장부 retired/소유 browser·backend·engine 종료/로봇0. `mixed_product_journey_pass=false`, `full_physical_demo_pass=false`. 실제 시험 종료 후의 장부 retirement guard는 offline 회귀와 scope-load로 확인했으며 마지막 실행의 frozen source를 사후 변경해 기록하지 않았다.

근거: `artifacts/pre-demo-20261008/gpt-provider-10-r1`, `gpt-provider-10-r2`, `gpt-provider-live-r1..r4`, `gpt-provider-audit-r1/r2.json`, `gpt-provider-offline-r1..r8.json`(최종r8/72PASS), `gpt-provider-full-regression-r1/r2.json`. 실제 유효 새 장면이 없어 예전 3D 화면을 이번 성공 이미지로 보여주지 않는다. SSH/serial/실센서/모터/배포/설치/commit/push/새agent 실행은 없다.
