# v358 — GPT 사진 관측 → NVIDIA 설계 실제 10회 검증

결론: **단계별 호출 연결·키/한도/원응답 감사는 통과, 새 혼합 사진 생성의 제품 전체 인수는 실패**다. Isaac 엔진과 실제 Chat UI는 시험마다 시작했지만 장면 후보가 검증을 통과하지 못했으므로 새 장면 저장/3D Build/SIM Run/Stop은 실행되지 않았다. 로봇 명령은 0회다. 과거 fixture/replay/다른 공급자 결과를 이번 성공으로 합산하지 않는다.

## 승인·호출·비용

사용자: “좋아. 확인해보자. 총 10회까지 시도해봐도 돼”. 기존 승인 침실 사진, 선택한 OpenAI secure 키와 등록된 Nebius secure 키를 각각 해당 목적지로만 사용했다. 이번 독립 장부의 합산 상한은 10회/USD0.15. 관측·설계·자동 수정 모두 1회씩 센다. 총 **10/10: GPT 5회 + Nemotron 5회**, 모두 HTTP200/stop/usage 수신, 추정 비용 **USD0.04494156**. 청구서상의 확정 비용은 아니다. pending0, dispatch lock 없음. 한도 도달 뒤 수정 dispatch 시도는 송신 전에 차단돼 11번째 HTTP 호출은 없었다.

- 관측: OpenAI `gpt-5.4-mini-2026-03-17`/low, 사용자가 선택한 alias를 공식 snapshot으로 명시 고정. [모델 규격·요금](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
- 설계/수정: Nebius Token Factory `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. 인증된 모델 메타데이터 GET에서 input/output USD0.06/0.24 per1M, context262144를 확인했다. 가격/모델/계수/승인은 scope에 고정했다.
- 원사진 SHA `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`. 이 값은 전송 승인 범위 확인용이며 생성 코드에 방 치수/배치/필수 물체를 넣는 용도가 아니다.
- 원사진은 OpenAI 관측 단계에만 전송. NVIDIA에는 검증된 관측/라이브러리/요청 및 실패 피드백만 전송. 키·Authorization·입력 image body는 응답 로그에 저장하지 않았다. 원응답 10건과 SHA/usage/attempt ID/실행 진단은 로컬에 보존했다.

## 실제 순서와 실패

| 시험 | 실제 호출 | 결과와 원인 |
|---|---:|---|
| live-r1 | 0 | 새 `observer_base_url` 메타데이터가 입력 저장 허용 목록에 없어 Send 단계 거절. 실패 UI/로그 보존 후 일반 입력 계약에 추가하고 URL의 credential/query 금지 유지. |
| live-r2 | 2 GPT | 의자 role=robot/category=office_chair, 블라인드 role=structure/category=window_blind. 자동 수정은 의자를 바꿨지만 블라인드를 남겨 실패. 기존 오류에는 필드 위치가 없었다. |
| live-r3 | 1 GPT + 2 Nano | 일반 role 규칙/다중 필드 진단 보완 후 관측 통과(12 entities/8 relations/3 null dimensions). Nano는 블라인드 evidence로 문짝을 만들고 수정 후 동일 후보를 반환, SOURCE_OBJECT_CATEGORY_MISMATCH/REPAIR_NO_PROGRESS. 추정 10×12m 자체는 실패 사유가 아니다. |
| live-r4 | 1 GPT + 2 Nano | Nano 추론 끄기 opt-in을 해제, 총 provider deadline300초로 비교. 관측 통과(17/11/6 null). 첫 설계 누락 물체, 수정본은 box를 추가했지만 의자 finish=natural 등 라이브러리 조합 오류와 잘못된 floor parent/블라인드 attachment를 남김. 수정의 부분 진전일 뿐 생성 성공이 아니다. |
| live-r5 | 1 GPT + 1 Nano | 종류별 library/source/placement anyOf 결속을 적용. 관측 통과(16/11/4 null). Nano 68.687초/5601 input/7641 output; 의자 finish/바닥 parent 및 블라인드 wall parent/elevation이 올바르게 나왔으나 robot/unknown 관측의 설명을 사용자 발언으로 복사해 `USER_SOURCE_QUOTE_NOT_IN_REQUEST:$.objects[8].source.user_quote`. 자동 수정 송신 전 10회 한도 차단. 방4.5×3.8×2.8m는 추정일 뿐 실측/정합 PASS가 아니다. |

live-r2의 2응답과 live-r3/4/5의 원응답은 수정하지 않았다. 현재 validator를 통한 read-only 재검사에서도 live-r2의 첫 후보는 2개 role 오류, 수정 후보는 1개 오류가 남아 있음을 확인했다. GPT 관측은 일반 프롬프트/진단 보완 뒤 세 실행에서 통과했지만 이것은 한 사진의 3회이지 일반 성공률이나 소물체 전체 검출/지지 관계 정확성을 입증하지 않는다.

## 실제 구현·회귀

1. `StageRoutingTransport`: observer/planner의 origin/config/model과 별도 secure key transport를 결속. 단계/모델 오인 및 planner 이미지 누출은 송신 전 거절. observer만 OpenAI wire(`max_completion_tokens`, reasoning low, 동등 enum/type)로 정규화. 기존 의미 계약/원입력을 바꾸지 않는다.
2. `build_split_generation_service`: 기존 Site2.2 pipeline/자동 수정1회/검증기를 그대로 사용. `--split-provider-scope`는 등록된 두 키·설정·가격·사진·prompt·10회 장부가 일치해야 허용되는 **host-only 평가 경로**다. 일반 UI의 “Use this key”가 자동으로 혼합 파이프라인으로 전환되는 것은 아니며 기본 OpenAI adapter를 바꾸지 않았다.
3. 단계별 설정을 조회해도 active key를 바꾸지 않음. 새로운 observer URL도 비밀 없는 input revision에 포함하고 동일 URL 비밀 검증 적용.
4. 관측 role/category의 독립 오류를 모두 entity/path/allowed_roles로 기록, 일반 역할 규칙 명시. 창문 가림막/조명은 object, 바퀴 달린 가구는 그것만으로 robot이 아니라는 일반 분류 기준이다. 단일 사진의 물체/배치 answer는 넣지 않았다.
5. generic photo1.3 wire에서 kind별 model_id/finish/placement/visual evidence를 anyOf로 결속. 기존 독립 union이 허용하던 잘못된 조합을 예방법으로 제한하되 host validator도 유지. 관측 object category와 기존 라이브러리 메타데이터로 동적으로 계산하며 방 치수나 필수 물체를 고정하지 않는다. unsupported source를 지우거나 재분류해 후보를 억지로 통과시키지 않는다.

최종 관련 회귀 **62 PASS**, 공급자 전체 **167 PASS**, core 전체 **302 PASS**. 모두 API0/로봇0의 별도 오프라인 회귀이며 실제 모델/사진 품질 성공을 뜻하지 않는다. 처음 만든 시험의 인자 오류/가격 fixture 누락/저장 메타데이터 인수 실패 등도 r1..r5 기록을 덮어쓰지 않고 보존했다. 문법 compile PASS. 전체 Web/패키지/회사PC/실물 재인수는 이번에 하지 않았다.

## 감사와 보존

`artifacts/pre-demo-20261008/split-provider-audit-r2.json`의 감사 PASS는 아래에만 한정된다: 10개 장부 attempt와 raw 일대일 대응/중복 없음/호출·비용 한도 준수/unknown과 lock 없음/원입력 image 미기록/사용자 provider 선택 불변/시험 중 소스 SHA 불변/소유 browser·backend·engine 종료/로봇0. `mixed_product_journey_pass=false`, `full_physical_demo_pass=false`를 별도로 기록했다. 엔진 startup 성공과 실제 장면 Build 성공은 다르며 이번 host capture는 장면 없이 NOT_RUN이다.

기존 Nebius 캠페인155/219/추정+예약USD0.234173530과 승인·가격·과거 이력은 불변이다. 파일 SHA `ad117283672bea2676e79b20b6917f1a741216829f26598eb1fafc222b5fcbb3`가 이전 기록과 일치했다. 기존 dirty/원본/과거 실패/실물 guard/예약PAUSED 유지. SSH/센서/모터/배포/설치 명령/commit/push/새agent 없음.

## 정확한 잔여 작업

1. **근거 경계/수정 피드백:** 관측 설명을 `user_quote`로 복사할 수 없도록 요청-local 인용 규격을 개선. robot role의 관측은 방 소품 목록에서 분리하고, 불확실한 후보를 user 근거/unknown 소품으로 임의 승격하지 않는다. 현재 user source는 exact substring 검증이지 전체 자연어 entailment 검증이 아님을 유지한다.
2. **한 번에 수정 가능한 진단:** source 누락과 모델/finish/배치의 독립 오류를 같은 후보에서 먼저 수집, blocked packing/graph 검사는 명시. 현재 일부 model/placement 오류는 첫 실패의 문자열/`$` 위치만 남는 한계가 있어 field/model별 허용값을 추가해야 한다. 마지막 UI의 한도 오류 아래에 최초 validation 이유/차단된 수정의 구분도 더 명료하게 제시해야 한다.
3. 위 오프라인 보완 후 **새로 승인된 호출 한도**에서 실제 Nano 설계·수정의 유효 장면 성공을 확인. 이번10회는 소진됐으며 장부를 초기화하거나 임의로 호출하지 않는다. GPT 관측만 바꾸면 전부 해결된다는 결론은 이번 결과로 반박됐다: 생성 규격/진단과 Nano의 grounding/지시 적합성도 병목이다.
4. 성공한 exact 장면으로 저장→actual Isaac Build/frame→Chat SIM Run/Stop/새로고침→수정/Undo 검증. 이후 단계별 공급자 UI/기본 선택과 최신 패키지/현장 인수. 로봇 전원만으로 해결되는 병목은 아니다.

근거 root: `artifacts/pre-demo-20261008/split-provider-10-r1/{scope.json,campaign.json}`, `split-provider-live-r1..r5/{browser.json,result.json,failed-journey.png,runtime/provider-evidence/}`, `split-provider-audit-r2.json`, `split-provider-offline-r6.json`, `split-provider-full-regression-r3.json`, `split-core-regression.json`. 실패에서 만든 새 scene/frame이 없으므로 예전 3D 이미지로 이번 구현의 성공 화면을 대신하지 않았다.
