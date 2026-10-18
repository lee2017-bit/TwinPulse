# TwinPulse 실행 관계 진단과 편집 후 화면 유지 검증

## v358 — 혼합 공급자 10회 실제 인수 결과

단계별 키·origin/config와 공통 한도·Site2.2 제품 경로를 연결해 실제 GPT관측5/Nano설계·수정5를 실행했다. 추정USD.04494156/pending0/lock없음, 감사PASS이나 새 장면생성/저장/Build/Run/Stop은FAIL/NOT_RUN. 관측 일반규칙/다중필드 오류, 종류별 library/source/placement 규격 보완 뒤 관측3실행PASS; 마지막Nano의 robot관측→user_quote 오인이 잔여다. 관련62/Provider167/Core302 offlinePASS. 한도 뒤 추가송신0/로봇0, 기본선택·기존Nebius155/219/원본/실물guard 불변. 자세한 원응답·실패순서·구현/미검증·다음작업은 [v358 검증 기록](split-provider-live-20261008.md)을 기준으로 한다. 아래v357이하는당시이력이다.

## v357 — 등록·선택한 OpenAI 키 실제 사진 관측 성공

사용자가 OpenAI 비교를 요청하고 별도 키를 등록한 뒤 **Use this key 완료**를 알렸다. 선택된 설정은 OpenAI / `gpt-5.4-mini` / low / 공식 API origin이며 secure key 존재만 확인했다. 이전 misnamed Nebius 키를 OpenAI로 보내지 않았다. 최대2회·추정USD0.15의 별도 diagnostic ledger로 기존 승인 사진 ce2093de…eb8만 전송; 로봇·SSH·센서·배포·Isaac 실행 없음.

### 실제 결과

- **첫 호출 유효 관측 성공 / 실제1회 / 6.906초**(transport6.828초). HTTP200, `gpt-5.4-mini-2026-03-17`, finish_reason=stop. prompt2285/completion836/total3121 tokens, **추정USD0.00547575**, pending0/dispatch lock 없음. 실제 청구 미확인. 첫 성공 뒤 추가 호출·repair·인위적 실패 주입 없음.
- 기존 제품 `build_observer_body`의 원문/사진/관측1.1 의미/배열 한도/validator 유지. OpenAI wire 호환만 `max_completion_tokens`, low reasoning, temperature 제거, `const`→동등 singleton enum/enum string type 명시로 바꿨다. 제품 parser를 느슨하게 하거나 사진별 답/좌표를 넣지 않았다. 원 schema/wire schema SHA·프롬프트·원 응답 SHA·usage/HTTP/시간·새 승인/예산을 각각 보존한다.
- 실제 응답: **10 representative entities / 6 relations / 3 dimensions**. 침대 오른쪽, 옷장 뒤 오른쪽, 책상은 옷장 왼쪽, 의자는 책상 앞, 선풍기 왼쪽, 케이블 앞 오른쪽은 원사진의 대략 배치와 부합한다. 왼쪽 옷/행거는 불확실하다고 명시했다. **전체 소물체 목록은 아니며 지지/부착 관계는 검사하지 않았다.** 여섯 관계는 left/right/in-front/near뿐, 세 치수는 모두 null이므로 실측 크기/거리 검증 성공이 아니다. 사진의 clear aisle은 실물 이동 허가나 바닥 안전 확인이 아니다.
- 원 관측을 기존 **Nemotron Site2.2 planner 요청 body**에 변경 없이 넣고 가정집 모델 라이브러리가 포함됨을 zero-call 확인했다. **body 구성 PASS와 실제 planner 생성/장면/Isaac PASS는 다르다.** 이번 planner 네트워크0, actual Isaac/Run/Stop0, 전체 데모 false.

### 구현·회귀·보존

- `scripts/evaluate_openai_observer.py`: 명시 평가 전용. 선택된 origin/profile/model과 사진SHA 확인, 독립 max2/USD0.15, 출력10000/HTTP120초, timeout/auth/모델 정체성 오류 재시도 없음, 유효 데이터 오류에 한해 수정1회, 첫 성공 즉시 종료. 사진 SHA는 전송 승인 범위를 묶는 용도이며 사진별 생성 규칙이 아니다. 제품의 legacy OpenAI adapter를 전체2.2로 교체한 것은 아니다.
- 비용 예약은 공식 모델 요금과 단일 이미지 최대patch bound 및 텍스트 UTF-8 byte+메시지 framing bound를 사용한다. 모델 context400k를 낮게 조작하지 않는다. 실제 요청 input bound45022, 출력상한10000 기준 예약USD.0787665→usage에 따른USD.00547575로 정산. 기존 Nebius campaign의 승인·가격·계수는 사용하지 않았다. [공식 모델 요금](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [이미지 입력 계산](https://developers.openai.com/api/docs/guides/images-vision), [구조화 응답 규격](https://developers.openai.com/api/docs/guides/structured-outputs).
- 기존 `AuditedChatTransport`가 modern `max_completion_tokens`도 최대출력 로그에 기록하도록 보완했다. 요청 이미지/키/Authorization은 저장하지 않으며 응답 redacted/raw SHA·실행 attempt ID는 유지한다. 이번 원응답4233bytes, response/stored SHA 동일.
- 새 비교 admission/비용/lock/wire/modern audit5tests 포함 **reliability/live-budget 관련38 PASS/1.658초**, 기존 Nebius pipeline **21 PASS/.506초**. 모든 회귀는 API0회. 초기 sandbox Temp 접근거부30errors는 승인된 동일 오프라인 재검증 전 실패로 보존; handoff 검사 cp949 읽기 오류는 명시UTF-8로 수정 후0call 재검사했다. 기존 S1d 메시지 assertion 불일치/전체Web 재인수는 이번 범위에서 수정·실행하지 않았다.
- Nebius ledger155/219·추정+예약USD.234173530·pending0/소진batch 유지. 이전149 prefix SHA 및 이전 summary count/cost 일치 확인. 원사진SHA 동일, 선택된 OpenAI 설정은 사용자가 고른 그대로 유지. 기존 dirty/실물 guard/원raw/실패/예약PAUSED 보존; 설치/commit/push/새agent0.

### 해석·정확한 다음 단계

같은 관측1.1 계약을 이 모델은 첫 응답에서 만족시켰다. 따라서 계약이 모든 모델에서 작동 불가능한 것은 아니며 **Gemma/MiniCPM과의 지시·structured-output 적합성 차이**가 병목의 한 요소라는 근거다. API 호환 정규화와 reasoning 설정도 달라 완전한 model-only 통제 비교가 아니고, 한 사진/한 성공으로 일반 성공률이나 사진 복원 정밀도를 보장하지 않는다. 계약 단순화는 타 모델 호환성을 위한 별도 과제다.

다음은 키 목록을 **단계별 observer(OpenAI)/planner(Nebius NVIDIA)** 구성으로 연결하고, 공급자별 origin·secure key·timeout/예산/진단을 독립 유지한 실제2.2 생성 경로를 구현·회귀 검증하는 것이다. 지금의 **Use this key는 한 공급자 전체 선택**이며 두 모델의 혼합 파이프라인이 자동 완성된 상태가 아니다. 이후 별도 승인 실제 planner→저장→Isaac/Run/Stop→최신package→현장 검증 순서다. 자동repair 실제 회복도 첫 성공 때문에 이번에는 NOT_RUN이며 미사용1회를 소진하려고 실패를 만들지 않는다.

근거: `artifacts/pre-demo-20261008/openai-observer-comparison-r1/`의 `summary.json`, `observation.json`, `campaign.json`, `request-metadata.json`, `regression-and-audit.json`, `responses/a12b31c0a31543a1878cbf1200fd17f7.json`. 원본 응답/관측 수정 없음.

아래 v356 이하는 당시 이력이다.

## v356 — 공급자별 API 키 목록·채팅 설정창

사용자 승인: 기존 키 재사용 여부를 확인하고 불가능하면 공급자별 키를 등록·전환하는 설정창을 구현. 로봇/센서/배포는 범위 밖이다.

### 확인과 구현

- 기존 `TwinPulse/OpenAIResponsesAPI` 저장칸은 존재하지만 현재 검증된 설정은 **Nebius Token Factory/Nemotron planner**에 연결돼 있다. 이름만 보고 OpenAI 자격으로 사용하지 않았다. `OPENAI_API_KEY` 환경변수는 미설정이며 OpenAI 전용 키 인증은 미확인이다. 비밀 값 출력·로그 기록·외부 전송 없음.
- 기본 채팅 상단 **API keys** → 이름/공급자/OpenAI 모델/암호형 키 입력 → **Register key** → 목록의 **Use this key**. 여러 OpenAI/Nebius Token Factory/Site v2 항목을 등록할 수 있다. Nebius 모델 파이프라인은 기존 승인 프리셋을 유지한다.
- 비밀은 공급자+UUID의 별도 Windows Credential Manager target에만 저장. 목록 JSON은 이름/설정/opaque 참조뿐이다. GET에 키·키 일부·인증 헤더 없음, 등록과 선택은 모델 요청·로봇 명령 0회다. 브라우저 local/session storage에 키를 저장하지 않고 제출/공급자 변경/닫기 때 입력을 제거한다.
- 기존 misnamed target은 현재 실제 설정의 공급자로 표시/보존. 등록만으로 기본 선택을 바꾸지 않는다. 선택 이후 백엔드 gateway와 상태 조회가 선택된 secure target을 사용한다. origin/profile/endpoint 결속이 바뀌면 기존 키 오전송을 차단하고 임의 target 참조도 거절한다. 기존 단일키 설정 API에도 결속 검사 적용.
- 선택은 generation worker/대기 장면 명령 중에는 거절하며 이전 입력/승인 상태를 무효화한다. gateway 재구성 실패는 이전 설정으로 rollback. 등록 metadata 저장 실패 시 새 키만 정리; rollback 실패는 별도 코드. 기존 보존 키/현재 선택 키는 삭제 금지, 다른 키만 명시 확인 후 삭제. 삭제 후 metadata 쓰기 실패는 목록에 키 없음으로 드러난다.
- 기존 **Nebius campaign 승인은 OpenAI로 이전 불가**. OpenAI adapter 생성 자체는 비밀 조회/네트워크 0회. 실제 GPT 비교 batch/예산을 기존 승인으로 우회하지 않았다.

### 최종 검증

- Python **49 PASS/17.771초**: 새 registry11 + S2c/S3c + R5 Product API. 다중키 선택/재시작/기존 키 보존·원주소 결속·metadata tamper·잘못된 입력·삭제·저장 rollback·gateway rollback·worker busy·zero-call composition·budget 분리 및 실제 localhost HTTP 인증/CSRF/등록→선택→현재 settings 왕복. 비밀 저장은 테스트 더블이며 실제 Windows 새 키 등록은 NOT_RUN.
- Web **419 PASS/46 files/23.61초**, TypeScript/build PASS. 설정창 열기 조회만, 명시 등록/선택, 삭제 확인, 입력 초기화/예외 비밀 비노출 및 기존 화면 회귀 포함. jsdom canvas 경고와 기존 bundle>500kB warning은 남는다. 실제 브라우저 시각 검수/Isaac 새 인수는 NOT_RUN.
- 첫 실행은 파일쓰기/프로세스 spawn 권한 제한으로 검증 전 실패; 승인된 오프라인 테스트 실행으로 재검증했다. 테스트의 Windows UTF-8 누락 2건과 기존 S2c 상태 double의 `_application.diagnostics` 누락을 보정했다. 초기 전체 Web는 새 한글 문구 때문에 기존 English-default 규칙 1 FAIL; 테스트 우회 없이 새 UI 문구를 영어로 정정한 뒤419 PASS.
- 추가 S1d 시작 경계 **2 PASS/1 FAIL**: `engine_unresponsive` 상태 메시지에 `redacted`를 기대하지만 현 구현은 `...see local engine log`라 assertion 불일치다. 실제 비밀이 반환된 결과는 아니며 이 시작상태 로직은 이번에 수정하지 않았다. 전체 시작/clean-release 인수 PASS로 합치지 않는다.
- 마지막 기존 설정 관찰: `nebius_token_factory`, 기존 Nemotron planner, 기존 key configured=true, 실제 runtime `provider_keys.json` 미생성. **기존 사용자 키/기본 공급자 설정은 변경하지 않았다.** 테스트 내 등록/삭제는 임시 fake store다.

### 남은 항목과 실행 방법

1. TwinPulse를 정상 종료 후 다시 실행하면 새 백엔드/빌드의 **API keys** 버튼을 사용할 수 있다. 이 작업에서 실행 중 서버를 강제 종료/재시작하지 않았다.
2. OpenAI 전용 API 키를 설정창에 등록해야 GPT-5.4 mini 실제 관측 비교를 이어갈 수 있다. 채팅에 비밀을 보내지 않는다. 키가 저장된 것과 인증·모델 사용 권한 성공은 별개다.
3. 현재 OpenAI 제품 생성 어댑터는 **legacy SceneToolPlan1.0**이며 사진→관측→NVIDIA planner→가정집 Site2.2 전체 경로로 교체한 것이 아니다. 설정창에도 미연결 안내를 표시한다. GPT 비교 호출/실제 사진 품질/repair 회복/가정집 전체 연결/actual Isaac/로봇 시험 모두 이번에는 NOT_RUN이다.

기존 ledger155/219·batch소진·예약PAUSED·raw/실패·dirty/whole=false·실물 guard 불변. 새 외부 호출0/로봇·SSH·배포·설치·commit/push·새agent0. 기준: official OpenAI model/API 문서를 확인하되 비밀은 서버측 secure store로만 라우팅하고 공급자명만으로 인증된 것으로 간주하지 않는다.

## v355 — 계정 모델 확인·실제 이미지 비교6회와 관측 repair 경계 수정

사용자 “Nemotron이 잘되면 제일 좋고 안되면 어쩔수없다 가리지않고 테스트” 요청을 기존 Nebius·승인 사진 ce2093de…eb8·USD1·부모 batch ceiling155의 남은6회 안에서 실행했다. 새 GPU 배포/설치/로봇/도면 전송/생성 후보 수동 수정은 없다. 원문은 `Create a digital twin of my bedroom with a bed and desk.`, 이미지 detail auto/출력 최대10000/대기 최대300초다. 결과는 **모델 전환 성공이 아니라 비교 실패 및 원인 분리**다.

### 계정 가용성

- 기존 credential을 메모리에서만 사용하는 authenticated `/v1/models?verbose=true` 및 `/private/v1/models_info` GET으로 계정별 모델 ID·image capability·가격을 확인했다. 키/Authorization/사진 body는 저장하지 않았다. 메타데이터 GET은 추론 호출0이다.
- 이 계정의 목록/가격 카탈로그에는 **Nemotron VL 없음**. 현재 Nano/Lightning/Ultra/Super는 text 모델이며 이를 이미지 모델로 오인해 호출하지 않았다. NVIDIA planner 선택은 기존 Nano 그대로다. 이전 공식 VL 출시 안내만으로 이 계정에서 바로 사용 가능하다고 단정할 수 없다.
- 이번 비교 후보는 기존 Gemma3-27B와 image capability가 확인된 MiniCPM-V-4_5다. 추가 이미지 모델 이름도 카탈로그에 있지만 일부는 dedicated-endpoint 표시가 있어, 새 배포 없이 이번 범위에서 시험한 후보라고 구분한다. Nebius 전체의 모든 이미지 모델을 시험했다는 뜻이 아니다.
- MiniCPM 가격/context만 검증된 출처 SHA와 함께 기존 ledger에 추가했다: input USD.658/output1.11 per million/context32768. 기존 모델 가격/예산/호출 원본을 다시 쓰지 않았다. `vision-model-comparison-r1/approval.json`에 모델·범위·원사진 SHA·계정/가격 응답 SHA를 보존했다.

### 실제 응답과 실패

| 모델·시험 | 응답 시간 | 실제 결과 |
| --- | --- | --- |
| MiniCPM / 기존 strict observation1.1 | 22.500초 | HTTP200/stop,3083 output tokens. 물체 ID가 `What`으로 반복됨; 관측 거절 |
| Gemma / JSON object + 스키마 설명 | 22.453초 | HTTP200/stop,1079 output tokens. 스키마 정의의 `type/properties/required`를 데이터와 섞어 반환; 거절 |
| MiniCPM / 같은 JSON object + 스키마 설명 | 15.782초 | HTTP200/stop,2042 output tokens. role/category 불일치·kind/role 혼용·중복 unknown ID 등; 거절 |
| Gemma / 범용 instance 예시 + fresh 자동 파이프라인 | 첫17.156초/수정22.297초 | 두 HTTP200/stop,897tokens씩. 가구 category를 coarse `kind`에도 사용. 자동 repair1은 같은 JSON 후보 SHA를 그대로 반환하여 REPAIR_NO_PROGRESS; planner 실행0 |
| MiniCPM / 같은 범용 instance 예시 | 10.062초 | HTTP200/stop,1165 output tokens. schema_version 누락·role/kind 혼용·존재하지 않는 room 관계 참조/없는 물체 행 등; 거절 |

정확한 transport 시간·usage·raw 파일 SHA는 `artifacts/pre-demo-20261008/vision-model-comparison-r1/summary-final.json`이 기준이다. 위 시간은 raw transport이며 case elapsed는 각각22.594/22.531/15.859/39.594/10.141초다. 모델 및 두 JSON 모드는 같은 사진/원문/한도/지시로 비교했다. **strict↔JSON 비교는 프롬프트에도 스키마를 넣으므로 decoder-only 실험이 아니다.** 이전 Gemma strict244.031초/length 공백반복과 이번 빠른 응답 차이는 format/model 상호작용의 단서이지, 특정 서버나 모델만의 근본원인이 확정된 것은 아니다. 한 사진/소수 호출로 일반 성공률을 추정하지 않는다.

유효 관측0/6응답·완성 장면0·자동 수정 회복0/1이다. 침대·옷장·책상 등을 일부 서술했으나 관측 JSON 수용/사진의 좌우·전후 정확도는 별개다. Gemma 후보는 책상을 침대 오른쪽이라고 잘못 서술하기도 했다. MiniCPM으로 갈아 끼우면 바로 해결되는 근거는 없다. **이번에 Nemotron planner/실제 Isaac Build·Run/사진 정밀 복원 인수는 도달하지 못했다.** 유효하지 않은 관측을 고쳐 넣거나 조건을 끄고 다음 단계로 통과시키지 않았다.

### 제품 수정과 최종 오프라인 검증

1. 잘림 envelope가 실제 identity/content/usage를 갖고 있으면 이를 `partial_completion`에 보존하되 `PROVIDER_OUTPUT_TRUNCATED`로 계속 거절한다. repair에 원 assistant 문맥을 넣고, usable content가 없을 때는 마지막 user에 feedback을 합쳐 user/user를 만들지 않는다. 원본 body는 불변이다. wrong model/refusal/invalid finish는 통과시키지 않는다.
2. 확정 HTTP400을 typed http_status/rejected로 보존한다. timeout의 unknown과 구분한다. `finish_reason`의 잘못된 타입도 TypeError 대신 typed envelope 오류가 된다.
3. “unsupported”라는 오류 문구만으로 content repair를 막지 않도록 envelope/identity와 데이터 오류를 분리했다. 관측 shape/version 오류도 bounded 수정의 대상이며 모델 정체성/unsupported finish는 수정 대상이 아니다.
4. 최종 raw 검토에서 **Gemma의 ID는 유효하고 kind=bed/desk 등이 coarse enum과 어긋나는데 기존 오류는 entity identity라고 뭉뚱그렸음**을 확인했다. 최종 소스는 `OBSERVER_ENTITY_KIND_INVALID`/`$.entities[0].kind`/허용 enum과 ID 중복의 `OBSERVER_ENTITY_ID_INVALID`/정확한 path를 분리한다. 전체 후보가 유효해진다는 뜻이 아니다.
5. 관측 repair feedback에도 planner 전용 `floor_call`/centre-based geometry 지시가 섞여 있던 제품 결함을 수정했다. observer는 관측 JSON/역할·종류·참조/읽을 수 없는 치수 null만 수정하고 장면 설계·모터 명령은 만들지 않는다. planner·compact feedback은 기존 계약을 유지한다. **이 최종 feedback/field-code 수정은6회 소진 후 수행했으므로 실제 모델의 새 회복 성공은 NOT_RUN**이다.
6. 평가용 exact observer 재사용 helper의 schema1.0 고정 때문에 새1.1 exact fixture를 거절하는 결함을 수정했다. 공식1.0/1.1 schema만 whitelist하고 사진/원문/model/request SHA/schema SHA/raw SHA/ledger 정산·단 한 번 재사용 조건은 모두 유지한다. 이번 유료 시험은 저장 관측 재사용0/fresh6calls다.

최종 **Provider167 PASS/3.956초**, 예산·exact replay/reuse·가격·포맷43 PASS/2.292초(일부 inherited tests 중복). observer repair 신규8tests가 full provider suite에 포함된다. 회귀는 합성 응답을 사용하는 명시 오프라인 테스트이며 실제 모델 회복이나 물리 인수로 표시하지 않는다. 초기 test setup/import, sandbox Temp 실패·재사용 schema 오류, final 첫167의 legacy 메시지 regex 실패1, 초기 summary의 잘못된 lock suffix 기록을 `offline-final-regressions.json`과 도구 이력에 보존했다. 권한 검토된 zero-network Temp 회귀 재실행 외 ACL/시스템 변경은 없다. 초기 summary.json은 그대로 두고 actual `.dispatch-lock` 확인을 보완한 summary-final.json을 새로 생성했다.

### 정산·보존·다음 작업

- ledger149→155/219, 이번6/6·부모 추가10 총10/10·이번 batch 남은0, pending0/dispatch-lock 없음. 이번 추정USD**.011090830**, 누적 추정+unknown 예약USD**.234173530**; 실제 청구 금액은 미확인. 전체 campaign USD1/max219를 다 쓴 것이 아니라 **이번 승인 batch를 소진**했다. 새 반복0.
- 과거149 requests SHA·원사진·v354 원 두 raw SHA 불변 확인, 새6 raw/status/usage/요청·schema SHA·실패/수정의 동일 후보 SHA 보존. `summary-final`의 audit PASS는 제품 PASS가 아니다. 일부 captured redaction 표시와 raw/stored hash를 따로 유지한다.
- 제품 기본 모델/Gemma strict/90초/compactOFF는 비교만으로 변경하지 않았다. 새 `scripts/evaluate_vision_model_selection.py`는 평가 opt-in이고 사이트·실물 데이터에 해당 사진별 규칙을 주입하지 않는다. latest source package/전체 App·Isaac 회귀·현장은 NOT_RUN. robot/SSH/배포/설치/commit/push/새agent0·dirty/whole=false/physical guard/예약PAUSED 유지.
- 다음 핵심은 **관측 계약 단순화**다. 현재 legacy coarse kind + reusable category + role의 중복 분류를 새 계약에서 최소화하고, 검증된 role/category로 legacy kind를 범용 변환하는 방안을 검토한다. 사진별 치환/없는 물체 생성/숫자·좌표 하드코딩 없이 구1.0/1.1 저장 호환을 유지해야 한다. 독립 schema 오류를 path/expected로 모두 알려 bounded repair가 실제로 바꿀 수 있게 하고, 이후 별도 승인 batch로 동일 조건 Gemma/MiniCPM fresh→repair→NVIDIA planner→actual Isaac를 확인한다. Nemotron VL은 계정에 제공됐을 때만 추가 비교하며 새 endpoint 배포를 이 요청으로 승인된 것으로 보지 않는다.

아래 v354 이하는 당시 이력이다.

## v354 — 승인5분 대기: 출력 반복과 잘림 repair 역할 오류 확인

사용자 “이번에5분정도 충분한 대기시간” 승인으로 같은 사진·Gemma 관측1.1/Nemotron·output10000/template off의 **한 세션**을 총300초 한도로 실행했다. 이전 남은8 안에서 observer/repair 합계2회 사용(부모 추가10 승인 누적4회/남은6), 재시도/한도연장/사진별 후보 치환 없음. 사진SHA ce2093de…eb8과 첫 observer request SHA dfd897cc…2a47/schema SHA db7d9477…acf4는 이전 두90초 시험과 같다.

### 실제 결과: 실패지만 원인 단서 확보

1. 첫 observer 응답은 **244.031초** 뒤 도착했다(제품progress244.110초). `finish_reason=length`, prompt665/completion10000/total10665. 본문25138자 중 끝 whitespace24641자(약98%)이며 첫 물체의 `region` 뒤에서 JSON이 완성되지 않았다. 이전 세 정상 관측은26.422/33.781/36.750초·866/997/1163 출력토큰이었다. 이제 단순히90초가 짧거나 일반 HTTPS가 끊긴 것만으로 설명할 수 없다. **새 포맷/모델/서비스의 constrained JSON 생성 중 공백 반복이 관측된 사실**이며 어느 구현이 이를 유발했는지는 아직 분리하지 않았다. 공백 제거 후에도 JSON은 불완전하므로 자동 정상화하여 PASS시키지 않는다.
2. 공유 bounded repair1이 **observer에서** 실행됐지만2.312초 후 HTTP400: `Conversation roles must alternate user/assistant/user/assistant/...`. planner 단계는 실행하지 않았다. 제품 생성 FAIL, 자동수정 회복0/1, Build/Run/저장 새장면0. 실측·사진 배치·실제 Isaac 사진 후보 인수는 NOT_RUN.
3. 원raw와 현재 제품 파서/repair loop의 **zero-network 로컬 재현**에서 `parse_chat_completion`이 length를 거절해 completion이 None이고, repair가 assistant를 추가하지 않아 `system,user,user`가 되는 것을 확인했다. 합성 original-message text를 사용한 로컬 재현이지 두 번째 fresh 성공이나 전체 원요청 재생 인수는 아니다. 잘림 오류가 `_complete_stage_impl` wrapping 뒤 `PROVIDER_VALIDATION_FAILED`로 뭉개지고, 확정 HTTP400/ledger rejected가 publicprogress outcome_unknown으로 표시되는 결함도 확인했다. **이 세 제품 결함은 이번에 수정하지 않았다.** 관측 반복과 repair 구성 문제를 서로 구분해 후속 수정한다.

### 이번 변경·검증·보존

- `scripts/twinpulse_backend.py`/`verify_chat_sim_journey.py`: 평가용 trusted-host/live-campaign에만90..300초 허용. 기본90초 유지·browser가 한도 변경 불가·fixture/offline/replay 차단 유지. 외부 browser worker budget은 live deadline+180초, 이번480초로 생성 완료 전에 검사기가 끊지 않도록 했다. 실제 순수 생성 총시간은약246초,300초 한도 내 실패다.
- `artifacts/verification/photo-contract-300s-launch-tests.json`: 경계/승인 필요/fixture 분리/300초 bootstrap guard 등8tests PASS/16.193초. 앞선7tests PASS/10.780초는 별도 초기 근거. 회귀는 새모델 품질/사진 인수 아님.
- `artifacts/pre-demo-20261008/photo-contract-300s-r1/result.json`: FAIL 원본, inference source start/end 동일·browser_closed true/owned supervisor stopped. 원body/hash·두 응답·public 오류·실행ID/spanID/elapsed/정산 보존. 제품 프로세스는 이 시험 도중 수정하지 않았다.
- `photo-contract-300s-r1/offline-length-repair-analysis.json`: 원 두 raw 파일 SHA 불변, parser/repair 역할 누락 및 오류분류 로컬 재현. 추가 API0/후보 수동 수정0/실물0.
- `photo-contract-300s-summary-final.json`: ledger/response SHA·byte·model·usage·prior147prefix·source·원본/종료 audit PASS. 첫 분석 `photo-contract-300s-summary.json`의 responses_received0은 ledger의 rejected 분류를 세어 실제 body 도착과 혼동했다. 삭제/덮어쓰기 없이 검사기를 보완한 final에서는 chat응답1/raw body2/HTTP오류1/ledger received0을 따로 기록한다. **audit PASS는 제품 FAIL을 바꾸지 않는다.**

ledger147→149/219·pending0/dispatch lock없음. 누적 계산+예약USD0.22308270, 증가USD0.01706650=첫 usage 추정USD0.00306650+HTTP400 usage불명 예약USD0.014. 실제 청구액 미확인·앞선 unknown 두 예약USD0.028/과거ledger는 그대로다. 승인 `photo-contract-300s-approval.json`은 부모10회 한도를 늘리지 않았다. 추가호출 중단·기본compactOFF/90초/wholefalse/guard/dirty/raw/예약PAUSED·로봇/SSH/도면전송/설치/배포/commit/push/새agent0 유지.

다음: 잘린 응답의 근거와 repair 역할 순서/정확한 truncation·HTTP code 보존을 범용 수정 → 같은 조건에서1.0/1.1 및 JSON 반복 영향 분리 → 남은 승인6 내 명시 재개 시 fresh 성공/자동수정/같은후보 actual 인수 → 최종source package → 현장 F0/F1. 단순 대기/출력 상한 증가만으로 해결됐다고 표시하지 않는다. 아래 v353 이하는 당시 이력이다.

## v353 — 새 계약 실제 시험: 관측 시간초과2회, 추가 호출 중단

사용자가 추가 **총10회까지** 승인했다. 기존 승인 사진SHA `ce2093de…eb8`만 기존 Gemma 관측/Nemotron 계획 목적지로 시험했고, 침실2 도면은 전송하지 않았다. 현재 원본 사진과 제품 추론 소스를 고정했으며 후보 수동 편집/사진별 정답표/고정응답 대체/제품 튜닝0이다. 평가 설정은 이전 비교와 같은 output10000/template off/총90초이며 제품 기본 정책 인수는 아니다.

| 독립 세션 | 실제 호출 및 결과 | 후속 단계 |
|---|---|---|
| `artifacts/pre-demo-20261008/photo-contract-add10-r1-direct/result.json` | Gemma1회, observer90초 `provider_timeout`; 응답 없이91.797초 로컬 종료, `outcome_unknown` 보존 | 기본 proposal planner/repair/Build/Run NOT_RUN |
| `artifacts/pre-demo-20261008/photo-contract-add10-r2-compact/result.json` | Gemma1회, 같은 observer90초 `provider_timeout`; 응답 없이91.657초 로컬 종료, `outcome_unknown` 보존 | compact1.3 planner/repair/Build/Run NOT_RUN |

첫 호출은 원격 결과 불명으로 비용을 환급/초기화하지 않았다. pending/dispatch lock/owned process가 종료된 뒤 같은 승인 한도 안에서 비교용 독립세션1회만 실행했고, 동일 실패가 반복되어 추가 호출을 중단했다. 두 세션의 관측 request/schema SHA가 같아 planner 종류를 비교할 단계까지 도달하지 않았다. **0/2 생성 완료지만 이는 새 근거/필수 바닥/배치 계약 오류를 재현한 결과가 아니다.** JSON 응답·계약 검증·자동 수정이 이번에는 전혀 실행되지 않아 v352 수정의 실제 모델 성공률이나 사진 정밀도는 판단할 수 없다.

### 원인 분리와 정산

- 같은 서비스의 공개 `GET /private/v1/models_info`는 인증키/사진 없이 HTTP200·0.937초였다. 일반 HTTPS 조회 가능은 확인했지만 authenticated chat 추론, POST 업로드/응답 전송, 모델 queue/처리시간의 정상 여부를 증명하지 않는다. 현재 전송 근거에는 `ProviderTimeoutError`, cancelled=true, 응답 없음만 있어 이 세부 원인을 **확정할 수 없다**. 임의로90초 제한을 늘리거나 모델을 바꾸지 않았다.
- ledger145→147/219, 이번 실제2/최대10·미사용8, pending0/dispatch lock없음. 과거145requests canonical SHA `2eaebe66…ed65` 불변. 과거unknown2에 새unknown2가 추가됐고, 새 두 호출의 full reservation 각USD0.014를 보존한다. 누적 계산+예약USD0.20601620(증가USD0.02800000)는 **실제 청구액이 아니다**; 실제 usage/비용은 응답 부재로 미확인이다.
- `photo-contract-add10-summary.json`의 audit_status PASS는 ledger/근거/hash/같은 제품source/원본불변 및 browser_closed2/owned stopped2 감사만 의미한다. 두 제품 시험은 FAIL이며 body raw는 도착하지 않았다. 대신 attempt별 request/schema hash·실행ID/spanID·timeout/취소/시간과 저장된 공개 오류/진단을 보존했다. 원본 결과를 수정하지 않았다.

### 이번 검사기 변경과 근거

- `chat-sim-journey.mjs`: 의도적으로 실패하는 일반 합성fixture에만 repair 실패를 요구한다. live/exact replay 첫시도 성공을 강제로 FAIL시키지 않는다. Node syntax PASS.
- `verify_chat_sim_journey.py`: fresh compact 성공 시 종료 후 실제 ProjectStore로 schema2.1·동적 물체 수와 같은 관계 수·placement 검증을 요구한다. 사진별 이름/좌표/부모를 기대하지 않는다. Python syntax PASS; 첫 문법 확인의 cp949 읽기 실패는 encoding만 수정했다. **이번 두 세션은 생성 전 실패하여 이 새 runtime assertion은 NOT_REACHED**다.
- `audit_scene_contract_batch.py`: 기존 ledger prefix와 두 세션의 전송 metadata/있는 경우 raw·usage·public provenance를 바인딩하고 source·입력·소유종료를 재검증한다. 이번 실행 audit PASS, 추가 모델 호출0. 결과불명은 수신 응답으로 표시하지 않는다.
- `photo-contract-add10-approval.json`, `photo-contract-add10-timeout-decision.json`, `photo-contract-add10-connectivity.json`, `photo-contract-add10-summary.json`에 승인/중단 판단/연결 관측/최종 정산을 남겼다. 첫 공개GET 진단 명령은 로컬 SyntaxError로 전송0, 정정한 명령1회만 실제 조회했다.

정확한 잔여: 관측 timeout 원인 분리 → 명시 재개 시 남은8 한도 안에서 fresh 관측/계획/자연 repair 및 같은 후보 actual Isaac·저장 재열기 검증 → 현재source package 재인수 → 현장 F0/F1. 이번에는 로봇이 병목이 아니다. 실측·전체 사진 복원·일반 사진 성공률·실물은 미검증, compactOFF/90초/whole=false/기존 guard/raw/dirty/예약PAUSED 유지. 로봇/SSH/serial/배포/설치/commit/push/새agent0. 아래 v352 이하는 당시 이력이다.

## v352 — 일반 근거·필수 바닥·사진 상대 배치·수정 진전 계약 구현

사용자의 “찾아낸 순서대로 수정” 요청으로 v351 실패 원인의 범용 수정 다섯 항목을 구현했다. **새 외부 모델 호출0/로봇 연결0**이며 기존 실패 응답을 편집하거나 이번 사진의 정답표·좌표·도면 치수를 주입하지 않았다. 아래는 로컬 계약/제품 연결 인수이며 실제 모델 성공률 인수는 아니다.

### 실제 제품 변경

1. **근거 계약 정합:** 새 관측 `1.1`은 각 entity의 역할(object/structure/opening/free_space/robot/unknown), 카탈로그 종류, 사진-view region, 별도 spatial_confidence를 요구한다. 기존 관측1.0과 저장된 Site2.2는 유지한다. 새 실험 compact `photo-layout-1.3`에서는 visual/inferred source가 현재 관측 ID를 인용하며, user source는 시각 참조 없이 이번 요청의 정확한 문장 일부를 인용한다. 구조/통로를 가구로 바꾸거나 침대 관측을 책상 근거로 사용하는 오류를 검사한다. **문장 인용 검증은 정확한 substring 검증이지 완전한 자연어 의미 검증이 아니다.** 구 관측의 종류 검증은 UNVERIFIED로 남긴다.
2. **필수 바닥 wire:** 기본 Nebius Site2.2 생성의 새 `site-proposal-1.0`에는 floor_call/floor_evidence가 필수이며 다른 scene_calls에는 floor를 넣을 수 없다. 로봇/임무는 기존처럼 선택 사항이다. 검증된 새 응답만 기존 Site2.2 calls/evidence로 내려 저장한다. 과거 바닥 없는 raw에 바닥을 자동 삽입하지 않는다. 새 입력의 request_schema metadata도 현재 계약으로 기록하고 저장된 입력 revision은 수정하지 않는다.
3. **일반 사진 배치 검사:** 선언된 사진 좌표계에서 관측 종류/누락 항목과 신뢰도 높은 좌우·전후·region의 명확한 모순을 검사한다. 신뢰도 낮음/구 관측/불명확한 geometry/near 등의 관계·실측 크기는 UNVERIFIED다. 0.8 confidence 및 0.05m 모순 여유는 공통 검사 기준이지 이 침실의 정답 좌표가 아니다. 모든 photo-relative PASS를 실제 방 정확도나 주행 안전 PASS로 확대하지 않는다.
4. **구조화된 수정:** 근거·필수 call·종류·누락 등 독립 오류를 최대64개 모아 다음 한 번 수정에 전달한다. floor 누락 등으로 검사 못한 bounds/overlap/support는 blocked_checks로 표시한다. 후보마다 이전 실패 검사 상태를 지워 새 결과와 섞지 않는다. 공백/키 순서와 무관한 parsed JSON SHA가 이전 실패와 같으면 REPAIR_NO_PROGRESS를 기록하고 더 자동 호출하지 않는다. 공유 단일 repair·시간/호출 한도는 유지한다. 최종 API/채팅 Tool details에는 안전한 오류 code/JSON path 및 의존 검사 목록만 표시하며 인용 문장·원 응답·임의 오류 payload는 진단 공개 목록에서 제외한다.
5. **추정 수정과 저장:** “방을 확대하지 마라”라는 이전 일반 지시와 추정 근거 지시 충돌을 제거했다. 미실측 방/배치 추정은 축소·확대·재배치할 수 있고 명시 치수는 계속 보호한다. 기존 bounded MRV 재배치와 후보 원본 불변 규칙을 유지한다. 새1.3도 기존 지지/부착 sidecar를 저장한다. 실제 재열기 검사에서 이 연결의 누락을 발견해 수정했으며 현재 schema2.1로 네 관계가 보존된다.

### 회귀 및 실제 로컬 제품 검증

| 근거 파일 | 결과 및 정확한 범위 |
|---|---|
| `artifacts/verification/scene-contract-provider-final-r2.json` | Provider159 PASS/4.168초. 새 근거·필수바닥·relative/region 모순 수정·parsed JSON no-op·잘못된 입력 shape·private payload 필터·실패 raw 불변 검사를 포함한다. v351 세 raw는 여전히 여러 오류로 거절됨 |
| `artifacts/verification/scene-contract-core-final.json` | Core302 PASS/26.100초. 기존 저장/geometry/실물 계약 보존 |
| `artifacts/verification/scene-contract-related-r3.json` | App/API·진단·repair·배치·저장·launch 관련229 PASS/109.903초. 일부 imported 공통 회귀 중복으로 합계를 고유 기능 수로 세지 않는다 |
| `artifacts/verification/scene-contract-web-final.json` | Web415/45files PASS; TypeScript 및 production build PASS. jsdom canvas 미구현·bundle 크기 경고는 기존 환경 경고이며 실제 렌더 인수를 대신하지 않는다 |
| `artifacts/verification/scene-contract-text-actual-r1/result.json` | 새 기본 proposal의 **사진 없는 합성 응답**→기존 App/API→실제 Isaac/PhysX/Run/Stop/reload/진단·owned 종료 PASS.194frames/도착 오차0.039662468m. 외부 모델/사진 인식0; 이 text 검사에서는 종료 후 별도 project 재열기 NOT_RUN |
| `artifacts/verification/scene-contract-actual-r3/result.json` | 새 compact1.3의 **명시 합성4물체**→실제 App/API/Isaac/PhysX/Run/Stop/reload/reset/진단/export/mobile/owned 종료 PASS.205frames/도착 오차0.039571465m. browser_closed=true, supervisor stopped, 확대된 추론 소스 hash 목록 전후 동일. 종료 후 ProjectStore 재열기 schema2.1/4items/4relations와 display→desk.top surface 검증 PASS. 외부 모델·로봇0 |

최종 사진 인수는 제공된 사진을 **로컬 입력으로만** 사용했으며 사진 내용에 맞춰 모델이 새 장면을 만든 것이 아니다. 따라서 실제 사진 종류/방 크기/가구 위치/지지 정확도·fresh Gemma/Nemotron 응답·기본90초 성공률은 **NOT_RUN/미검증**이다. 기본 compact OFF·90초·실물 guard·whole=false·H5/H6/C3-C6/F0/F1 PARTIAL을 유지한다. 새 배포 패키지/clean install/회사 PC/현장 로봇은 이번 범위가 아니다.

### 실패와 한계 보존

- 초기 provider r3/r4는 새 회귀 fixture의 명시 치수와 결과 필드 이름이 틀린 실패였으며 원 기록을 유지하고 fixture를 수정했다. 새 계약의 negative 검사 자체는 완화하지 않았다.
- integration-r1 및 core-r1은 자체 임시파일 sandbox 권한 실패, web 첫 실행은 자식 프로세스 EPERM이었다. 승인된 로컬 테스트 권한으로만 재실행했고 임의 우회/설치는 하지 않았다.
- related-r1의 자체 자식 import 경로 실패·잘못된 관측 fixture를 보존한다. related-r2의 마지막 실패는 정확한 새 SceneContractError/REQUIRED_TOOL_COUNT를 구 generic 오류로 기대한 진단 assertion이었다. 실제 code/type을 검증하도록 변경하고 r3 전체229 PASS다.
- actual-r1은 runtime/browser 동작이 통과했어도 검증 중 프롬프트 수정으로 source hash가 달라 **전체 FAIL**이다. actual-r2는 당시 검사기 PASS였지만 저장 sidecar를 별도로 검토하자 schema2.0로 관계가 빠진 것을 발견했다. 이 결과를 최종 관계 저장 인수로 쓰지 않는다. 새1.3 sidecar 지원과 재열기 assertion 보강 후 **actual-r3만 최종 관계 저장 인수**다. 이전 결과는 덮어쓰지 않았다.

공유 ledger는145/219·pending0·계산+예약USD0.17801620, hash `bbfc62d3724053eb98bf6fff9870b67ae0505dea9491d377a7344b94cdcfbef3`로 로컬 감사 전후 동일하다. SSH/serial/실센서/모터/배포/유료 호출/새 설치/시스템 설정/commit/push/새 agent0. 실패 raw/dirty/역사 프로젝트·package/예약PAUSED를 보존했다. 다음은 **별도 승인 범위의 실제 모델 새 계약 시험**과 현재 소스 패키지 재인수이며, 로봇 전원만 켜면 전체 데모가 끝난다고 보장하지 않는다.

아래 v351 이하는 당시 이력이다.

## v351 — 사진별 정답표 제거 후 실제 LLM 최대10회 시험

사용자의 “10회까지 테스트해보고 결과 정리” 승인을 같은 원본 침실 사진(ce2093de…eb8), 기존 Nebius Gemma3-27B 관측/Nemotron3-Nano 계획에 적용했다. **9회로3개의 관측→계획→단일 수정 세션을 완료하고 종료**했다. 남은1회는 새 관측+계획2단계를 완주할 수 없어 반복성 호출하지 않았다. 침실2 도면은 참고만 유지하고 외부 전송하지 않았다. 로봇 OFF·robot/SSH/serial/모터/배포/설치/설정/commit/push/새agent0, 예약PAUSED·기존dirty/raw/FAIL/물리guard 보존.

### 시험 설정과 단계별 결과

같은 v350 제품 추론 소스, 기존 실제 App/API→모델 경로에서 sequential fresh 시험. 평가 명시 overrides는 planner-template off/output10000/전체timeout90초, compact r1/r3는 실험1.2, r2는 기존 기본 Site2.2 생성 경로다. 따라서 **제품 모든 기본 설정의 통계적 성공률 인수는 아니다**. 세션 사이 제품 코드는 고치지 않았다. 검사기만 live/exact inventory의 역사24개 고정 assertion을 nonempty 배열로 바꿨으며 명시 fixture 개수 검사는 보존했다.

| 실행·원본 | 실제 호출 | 결과·실제 수정 루프 |
|---|---:|---|
| [compact r1](../../artifacts/pre-demo-20261008/photo-general-add10-r1/result.json) | 3 | FAIL. Gemma 관측 유효; 최초 planner와 repair 모두 모든 observation_ids=[]를 보내 PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE:bed_1. free_space floor_1을 floor_fan으로 오인한 별도 문제도 raw에 존재 |
| [basic r2](../../artifacts/pre-demo-20261008/photo-general-add10-r2-direct/result.json) | 3 | FAIL. 관측 유효; 최초/repair 각각 물체9calls(가구2/room_item7)만 있고 create_floor0개. one-floor 전역 계약에서 거절 |
| [compact r3](../../artifacts/pre-demo-20261008/photo-general-add10-r3/result.json) | 3 | FAIL. 관측 유효; 최초/repair 모두8물체의 observation_ids=[]; r1과 같은 bed_1 근거 누락 반복 |

관측3/3은 **응답 계약 유효**이지 사진 인식 정확도3/3의 뜻이 아니다.9응답 모두 HTTP200/finish_reason=stop/response_truncated=false. 새 장면0/3·수정3실행/회복0. Build 허용false·operations[]·applied_revision=null·prim_count0·이동0이므로 **사진 장면의 actual Isaac 생성/물리이동/정밀배치/지지 인수는 NOT_RUN**이다. 런처에서 actual Isaac를 띄웠다는 metadata만으로 통과 처리하지 않는다. 모든 result에 inference_source_unchanged=true, browser_closed=true/supervisor stopped/cleanup succeeded.

### 원인 근거와 다음 범용 수정

1. compact photo_layout.py의 schema refs는 maxItems3/실제관측ID enum을 제공하지만 minItems1이 없고, 프롬프트는 user-text-only 근거에 []를 허용한다. compiler는 reviewed에 없는 객체+빈근거를 전부 거절한다. 모델은 관측된 bed까지 []로 출력했고 첫 오류 bed_1만 수신한 수정도 전부 []를 반복했다. **wire/schema·프롬프트·텍스트/관측 근거·검사기 정합성이 부족**하다. 모델이 ID 지시를 무시한 내부 이유를 추정 확정하지 않으며 사진별 ID 사후 연결로 숨기지 않는다.
2. 기본 Site 프롬프트는 exactly one floor를 이미 요구하지만 JSON tool-array 응답은 바닥 없는 후보를 반환했고 수정도 같은9calls다. 필수 장면 전역 규칙을 model-facing 계약/구조화 repair에 확실히 반영해야 한다. 원 JSON에 바닥을 임의 삽입해 이번 FAIL을 PASS로 바꾸지 않았다.
3. 기존 한 번 repair dispatch는 실제 작동했지만 회복하지 못했다. first-error 텍스트+일반 지시를 전달하는 것과 효과적인 오류별 수정은 다르다. missing evidence/required calls를 구조화해 요청하고 여러 결함을 모아 재검사하는 범용 개선이 필요하다. 빈근거 user/inferred를 정당하게 허용하는 조건과 visual근거 필수를 구분해야 한다. free_space/wall과 가구 분류도 일반 관측 경로에서 점검한다.
4. 이번 원인은 방10×12m 추정·미실측 크기·통신·응답잘림이 아니다. 크기/배치/지지 품질은 해당 검증까지 도달하지 못해 미검증이며 “완벽한 방이지만 근거ID만 문제”라고도 주장하지 않는다. 다음은 정확한 실패 raw를 오프라인 재검사→범용 계약 수정/회귀→별도 승인 fresh 모델/실제 Isaac 품질 검증. 사진별 고정 목록/도면 치수 주입은 금지하며 safety를 성공 판정 완화와 섞지 않는다.

### 한도·로깅·로컬 회귀

승인 원본 [batch record](../../artifacts/pre-demo-20261008/photo-general-add10-approval.json), [안전한 요약 JSON](../../artifacts/pre-demo-20261008/photo-general-add10-summary.json)에 실행ID/attempt/비용/원본 경로를 묶었다.3개 generation execution ID는6434282315cb4356a757cf305a2a6202 /6d9f98b4c3d549d995ef6499f2ed1753 /30c40c44103840dfa57556ff75c17bf5이며 각3개 raw response가 같은ID로 결속된다. API elapsed 관측은 observer26.422..36.750초, planner7.453..8.703초, repair6.797..8.093초; 모델 내부 함수CPU·네트워크 단방향 지연의 측정이 아니다.

ledger136→145/219·9new 모두received/finished·pending0, 이번 증가계산USD0.00549090·누적 계산+예약USD0.17801620(청구서 미검증). 과거unknown/예약은 보존, sharedUSD1/219 리셋/증액0·추가호출0. [Provider139](../../artifacts/verification/photo-general-add10-provider-r1.json) PASS/3.810초·Node `--check` PASS이며 새 전체Web/실제사진장면/패키지 인수가 아니다. 기본compactOFF/90초·whole_demo_ready=false, 새package/clean install/회사PC/현장 scan/odom/TF/stop/정합F0/F1 잔여를 유지한다.

아래 v350 이하는 당시 구현과 시험 이력이다.

## v350 — 사진별 정답표 제거·추정 크기/배치 수정·일반 경로 검증

사용자 최신 결정: 실측 없는10×12m 추정은 실패가 아니다. 실패 후 추정 방 크기/배치를 바꾸고 먼저 놓은 물체를 되돌려 다시 배치할 수 있어야 한다. 특정 사용자 사진에만 맞춘 코드는 제거한다. 첨부 도면의 침실2는 참고 자료이며 코드의 고정 치수/가구 위치나 독립 실측 제약으로 사용하지 않는다. 이번 작업은 로봇 OFF, 새 외부 LLM 호출/사진·도면 전송0. 기존 승인10회가 소진된 ledger136/219·pending0·USD0.17252530를 확장하지 않았다.

### 제품 변경

- Core/provider/App의 사진SHA→고정24목록·상대방향/좌표·지지 관계·추정30m² 제한 자동 주입을 제거. 사진 품질 inspector는 명시적인 검토 제약이 없으면 구조 executor 확인 후 UNVERIFIED/generation_allowed=true를 반환하며, 미실측 크기만으로 실패를 만들지 않는다. 이 표시는 정확한 복원 PASS가 아니다.
- 과거 검토표는 tests/fixtures/historical_*로 격리. 제품 packages는 이 fixture를 import하지 않는다. 기존 raw/실패/과거 인수/저장 프로젝트·frozenpackage를 삭제하거나 새 정책 PASS로 덮지 않았다. 과거 exact 재생의 엄격한 요청 hash도 우회하지 않는다.
- repair의 이전 추정 floor size/centre 고정 guard를 제거. 명시한 사용자 치수는 기존대로 지키되 미실측 크기·중심·모든 추정 배치를 바꿀 수 있다. 공유1회 repair/default90초/호출·비용 한도는 유지한다.
- Greedy 실패의 bounded512nodes/2초/32branch MRV 재배치를 모든 일반 사진 경로에 적용. 임시 emitted calls를 되돌려 처음부터 배치하되 원본 intent/저장 이력은 불변, 물체 생략이나 로봇의 측정 free-space로 위장하지 않는다. grid/region은 범용 추정 알고리즘이지 특정 방의 좌표표가 아니다.
- 일반 compact wire는 photo-layout-1.2의 가변 물체 배열과 재사용 라이브러리 model/XYZ/variant/finish/placement이다. fixed24slots를 기본으로 요청하지 않는다. 모호한 이미지의 물체·크기·배치는 모델 관측/사용자 설명에 기반한 추정이며 향후 LiDAR 확인과 별도다.
- 과거 bedroom_twin의 사진SHA·2.8×4.2m·가구/로봇 좌표 코드 생성 recipe를 제거. 명시적인 옛 프로젝트 보기만 기존 저장 site-draft/manifest를 무결성 검증 후 연다. 그 원본 데이터를 새 사진의 default로 재사용하지 않는다. goal bounds도 floor centre/size에서 계산한다.
- 구조상 잘못된 tool/JSON/비유한·음수 치수/허용 범위/침범/가구 surface 지지 오류/실측 불일치·로봇 잠금은 완화하지 않는다. LiDAR 후속 검증은 초기 오류나 물리 구동을 무조건 승인하는 근거가 아니다.

### 직접 실행한 결과와 제한

- Provider139/3.860초 PASS: 새 일반 정책8개 포함.10×12m 초안 허용, 사진 해시별 factory 비호출, parametric 배열, packing 실패2×2→8×8 repair, 일반3물체 재배치10nodes FOUND/원본 불변, 명시4×5m 변경 거부·지지 오류·공유 repair 한도 확인. 기록 artifacts/verification/generic-photo-provider-r4.json.
- Core302/26.027초 PASS, App/채팅·역사 프로젝트85/64.905초 PASS, 관련 생성/엄격한 역사 재생/배치·저장·localization123/85.787초 PASS. 일부 공통 테스트 중복이며 합계를 독립 기능 수로 표시하지 않는다. 각각 generic-photo-core-r1.json, generic-photo-app-r2.json, generic-photo-related-r2.json. 마지막 core 수정은 자동 factory 호출 제거이며 provider139 및 관련123가 그 소스에서 통과했다.
- Web45files/414tests/27.33초 PASS. jsdom canvas 미구현 경고는 존재하며 이 결과가 실제 canvas/render 인수를 대신하지 않는다. 기존 도구만 사용, 설치0.
- actual generic r3: artifacts/verification/generic-photo-actual-r3/result.json PASS. 실제 현재 App/API→Isaac/PhysX 생성·1회 명시 Run/도착·접은 화면에서 Stop·reload 무재실행·reset·실제960×640 capture·diagnostics/graph/export/mobile·브라우저 종료 및 owned backend/engine 종료 PASS. 종료 후 실제 ProjectStore 재열기 schema2.1/4items, plan5fa04291b212…/input3e1184fca8a5…/scenee9eebead1564… 동일 PASS. 임의 시험4물체 응답이며 해당 사진의 인식/실측을 대신하지 않는다. inference_source_unchanged=true·paid_calls=0·robot_connections=0.
- 실패 보존: provider-r1은 옛 정책 assertion7 FAIL 후 새 요구와 역사 fixture 명시를 구분해 수정. app-r1은 시험 임시 폴더 권한 오류, scoped test-owned temp 실행 app-r2 PASS. related-r1은 잘못 지정한 모듈2개 import 실패이며 실제 이름으로 related-r2 PASS. 실제 r1은 검사기의 비어 있는 역사 목록 bed 접근, r2는 standalone test import 의존성 실패. 각각 원 결과를 유지하고 검사기만 교정한 r3 PASS; 물리 인수 실패를 가짜 PASS로 바꾸지 않았다.

### 남은 것

새 일반 정책으로 외부 모델을 호출한 실제 생성 품질·성공률은 NOT_RUN. 침실2 도면 외부 전송/OCR/실측 확정도 NOT_RUN. 기본 compact OFF/90초는 그대로이며 default 정책 승격·새source package/clean install·현장 scan/odom/TF/stop/정합 F0/F1도 미완료다. 초안 생성·합성 응답의 제품 연결 PASS를 사진 정밀 복원이나 전체 실물 데모 완료로 표시하지 않는다. 기존 dirty/raw/v1-v2/실물guard/자동화PAUSED·whole=false 유지, SSH/serial/배포/모터/설치/commit/push/새agent0.

아래 v349 이하는 당시 정책과 당시 결과의 이력이다.

## v349 — 추가10회 사진 상대배치·부착 검사와 실제 배치기 수정

사용자 “그래 추가 10회로 또 해보자고”의 같은 사진·기존 Nebius Gemma3-27B 관측/Nemotron3-Nano 계획 승인으로 **실제10/10 호출을 사용하고 종료**했다. 공유 USD1/219 한도를 확장하지 않았다. 원본 SHA256 `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`, 로봇 OFF·SSH/serial/실센서/모터/배포/설치/시스템 설정/commit/push/새 agent0·예약 PAUSED다. 아래 v348 이하는 당시 이력이다.

### 실제 제품 수정

- 기존 `reviewed-photo-geometry-1.0` 기본 직렬화/hash를 유지하고, 명시 compact 시험의 알려진 사진만 additive1.1/`photo-semantic-review-1.0`으로 검사한다. 원본 사진을 사람이 검토한 **추정 사전조건**이며 일반 사진 인식 성능이나 센서 측정이 아니다. unknown SHA에는 이를 재사용하지 않는다.
- 침대 오른쪽·책상 왼쪽/뒤·옷장 오른쪽/뒤, 목재 랙/선풍기/의자 왼쪽, 입구 문/바구니 앞왼쪽, 케이블/어댑터 앞오른쪽을 실제 emitted geometry에서 검사한다. 기존 지지3·바닥9·드레이프2·추정 면적1을 포함해 현재32검사다. 침구는 bed/mattress, 옷은 wardrobe/wood_frame/office_chair의 허용 part만 선택하며 임의 bed/headboard 부착을 거절한다. 바닥 물체를 desk 위에 올리는 intent도 strict schema와 독립 compiler가 각각 거절한다. 실제 ray/측정으로 만든 좌표나 정확한 옷걸이 모델은 아니다.
- 실측 없는 과대 추정은 `PHOTO_SCALE_REVIEW_REQUIRED`로 분리한다.30m²는 **이 사진의 미실측 plausibility review 상한**이지 실제 방 면적이 아니다. 명시 room 실측만 이 제한을 대체한다. single repair가 scale 오류일 때만 첫 footprint를 componentwise 축소할 수 있도록 두 곳의 guard를 함께 수정했다. 다른 오류는 크기/중심 잠금 그대로이며 자동 확대·물체 삭제·수동 후보 정규화는 없다.
- 작은 방의 첫 greedy 배치 실패를 전역 불가능으로 간주하던 병목을 수정했다. 실패 시 알려진 enhanced parametric 경로만 동일10cm grid·region·치수·물체·wall margin11cm·item gap3cm·hazard buffer를 지키는 MRV bounded search를 사용한다. 최대512nodes/32branches/2초, 소진은 실패이며 전역 불가능/실제 안전 공간의 증명이 아니다. 구 성공 경로 compiler1.3은 그대로, fallback을 사용한 경우만1.4 provenance를 저장한다. 마지막 원본 응답은40nodes에서 발견됐다. emitted 모든 geometry와 placement contract를 기존 executor로 재검증한다.
- 실패 raw의 재생은 별도 명시 `--replay-failed-packing` 평가만 허용한다. stopped owned run·original FAIL·browser closed·accepted draft 없음·정확한 observer passed/planner packing failed의 두 응답·원본 input/사진/모델/요청/schema/완료 ledger/raw hash를 결속한다. 원래 plan hash가 없음을 `None`으로 기록하며 새 독립 compile hash와 비교한다. credential/network fallback0, 원본 FAIL이나 ledger를 쓰지 않는다. source 검사에 photo_quality 모듈도 포함했다.

### 이번 호출과 실패 원본

| 실행 | 실제 새 호출 | 결과 및 원인 |
|---|---:|---|
| [r1](../../artifacts/pre-demo-20261008/photo-semantic-add10-r1/result.json) | 2 | **fresh PASS**, 평가전용180초/수정0, 당시20검사·3.5×4m 추정·24항목, actual Isaac/PhysX/Stop/reload/진단/owned 종료/저장 재열기,167frames·도착오차0.039727156m. 이후 강화한32검사의 fresh 인수로 소급하지 않는다 |
| [r2](../../artifacts/pre-demo-20261008/photo-semantic-add10-r2/result.json) | 3 | **FAIL**, 기본90초.10×12m 과대 후보→5×6m 수정이 두 번째 footprint guard에서 거절됐다. 두 guard 수정/회귀로 해결했지만 원 FAIL은 유지한다 |
| [r3](../../artifacts/pre-demo-20261008/photo-semantic-add10-r3/result.json) | 3 | **FAIL**, 기본90초.3×4m에서 planner+repair 모두 `PHOTO_LAYOUT_REGION_FULL: underdesk_bag in rear_left`. 이후 문/케이블/바구니 region 조건을 보완했다. 새 PASS로 덮지 않는다 |
| [r4](../../artifacts/pre-demo-20261008/photo-semantic-add10-r4/result.json) | 2 | **FAIL**, 기본90초.3.5×4m의 첫 배치 실패·repair는 host2회 cap으로 dispatch 전 차단. repair_count1은 차단된 시도이지 실제 세 번째 호출이 아니다. 이 응답으로 bounded 배치기를 고쳤다 |
| [r4 exact packing r1](../../artifacts/pre-demo-20261008/photo-semantic-add10-r4-exact-packing-r1/result.json) | 0 | browser/actual Isaac 경로 PASS, 전체 **FAIL**: 검사기가 없는 원 accepted plan hash와 새 hash를 비교했다. 원본과 source 불변·owned 종료. 검사 수정 후 별도 r2로 확인 |
| [r4 exact packing r2](../../artifacts/pre-demo-20261008/photo-semantic-add10-r4-exact-packing-r2/result.json) | 0 | **EXACT_SAVED_RESPONSE_ACTUAL_ISAAC_REGRESSION_PASS**, 새 fresh LLM 성공 아님. 원 사진/요청/schema/두 응답/ledger 그대로·수정0, 방3.5×4m/14m²·24항목·32검사 PASS(전체 사진복원 PARTIAL). 실제184frames·PhysX 도착오차0.039767066m·Stop/reload/다음 채팅 목표/접힌 화면 Stop/reset/desktop-mobile 진단·종료 후 저장 재열기 PASS. original/input/ledger/source 불변, supervisor stopped |

최종 계획 SHA256 `4f3d9d9709bbef5b03ec3035d17e6f2bf740eda12bfd8c0db84a0d09753a7853`, input `2b2393c11597f89589f77ae9d1c1f66bb97d5e451c1275f74298cd068387f656`, scene `230fdc62179fe542ff31d1902583a64a13512751492ca92c3247d603dd314570`다. [실제 화면](../../artifacts/pre-demo-20261008/photo-semantic-add10-r4-exact-packing-r2/generated-ready.png). 화면을 직접 검토했고 침대/책상/옷장/랙/선풍기/바닥 케이블은 파라메트릭 모델로 표현됐다. 창문 블라인드·문 hinge/정확한 위치·옷 분포/가방과 잡동사니의 정확한 상대거리·실측 크기·실제 통로/충돌 안전은 여전히 미검증이다. 제한 관계 PASS를 사진 전체 정밀복원이나 전체 방 자율주행 PASS로 표시하지 않는다.

### 회귀·한도·정확한 잔여

- 최종 Provider131 PASS/3.665초, Core302 PASS/25.534초, 사진 저장·placement/live audit·budget/compact launch·observer reuse37 PASS/12.870초, explicit exact replay5 PASS/0.166초. 집계 중복이 있어 합산하지 않는다. 실제 실패 raw 재현→수정 후 hash/입력/원본 불변 및 bounds/실패 소진을 검사한다. 최초 새 시험의 import/잘못된 report field 오류와 Temp ACL12errors는 tool 이력으로 보존; 시험 import/assertion 수정 및 허용된 자체 임시파일 권한으로 재검사했다. 별도 전체 Web 새 회귀/빌드/새 package 인수는 NOT_RUN(기존 Web을 이번 actual에서 사용).
- ledger126→136/219, 이번10개 모두 received/finished, 진행 중0. 계산+예약USD0.16375798→**0.17252530**, 증가 **0.00876732**(약0.88센트, 청구서 미검증). 과거 outcome_unknown2와 예약 부담을 보존했다. 이번 추가 승인은10/10으로 종료, 공유 잔여83회를 임의 실행하지 않는다. 재생 새 호출0이고 원 ledger SHA 불변이다.
- 기본 compact OFF/90초는 그대로다. 최종 배치기/32조건 이후 **새 fresh 모델 및 기본 정책 성공률은 미검증**이다. 여러 수정/config가 다른4세션을 통계적 성공률로 발표하지 않는다. 새로운 승인이 필요한 실제 모델 평가를 제외하면 저장 응답으로는 반복 회귀 가능하다.
- v347 frozen package는 당시 source 인수이며 현재 변경 source의 새 package/clean install/회사 PC 검증이 아니다. 다음은 기본 정책/일반 사진 품질 인수, 최종 source package, 현재 boot/release의 corrected-driver scan/odom/TF/stop 및 정합·실물 F0/F1이다. Oct6 corrected ARM64 driver의 기존 build/deploy 근거는 보존한다. `whole_demo_ready=false`, P2/H5-H6/C3-C6/F0-F1 PARTIAL이며 로봇 전원만 켜면 전체 데모 완료라고 보장하지 않는다.

## v348 — 추가 승인10회 실제 사진 생성·수정·Isaac 검사 (2026-10-08)

이 절이 최신이다. 사용자의 ‘추가10회 승인’으로 동일 침실 원본 SHA `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`를 기존 Nebius Gemma3-27B 관측/Nemotron3-Nano 계획에 전송했다. 로봇 OFF·SSH/serial/실센서/모터/배포/설치/commit/push/새agent0. 기존 dirty/실측 raw/과거 실패/직렬화 의미/실물 guard·예약PAUSED는 보존했다. 10회 사용 후 추가 dispatch 없이 종료했다.

### 실제 호출과 단계별 결과

모든 경로는 `artifacts/pre-demo-20261008/` 아래다. 기존 결과나 응답은 고치지 않았다.

| 실행 | 신규 실제 호출 | 결과 및 범위 |
|---|---:|---|
| `photo-add10-r1` | 3 | FAIL. planner와 수정1 모두10000토큰 잘림, 불완전 root JSON·20개 prop의0치수·다량 trailing whitespace. 진단용 메모리 해석을 유효 후보/저장/PASS로 바꾸지 않음. Build/Run 없음. |
| `photo-add10-r2` | 2 | FAIL. observer78.110초로 기존 전체90초 deadline 소진. 늦은 planner 완성 응답은 취소 후 received 성공으로 부활시키지 않고 rejected 보존. raw의 hanging_clothes→bed/body 불법 part도 별도 오프라인 확인; 추가 호출0·Build/Run 없음. |
| `photo-add10-r3` | 3 | 첫 planner `PHOTO_RELATION_FLOOR_INVALID`(floor 배치인데 underdesk_bag parent=desk), 허용 수정1 뒤24-object 생성·actual Isaac 이동/Stop 통과. 전체 결과는 live 검사 host의 profile-generation flag 누락으로 FAIL이며 원 FAIL을 고치지 않음. 사진 의미상 hanging/bedding 부착 및 bag 위치는 여전히 잘못됨. |
| `photo-add10-replay-r1` | 0 | 위3개의 정확한 원 요청/schema/응답 SHA와 ledger 완료를 검증한 immutable replay. actual Isaac/PhysX/Stop/reload/diagnostics/owned 종료 PASS·192frames·저장 재열기 PASS. 새 LLM 성공이나 독립 새 생성으로 계산하지 않음. |
| `photo-add10-r4` | 2 | 최종 fresh Gemma/Nano, 수정0·24-item draft→actual Isaac/PhysX/Stop/reload/다음 채팅목표/접힌 화면 Stop/reset/진단·desktop/mobile/owned 종료 PASS.184frames·도착오차0.039711009m·generation28.875초. 아래 사진 품질은 별도 PARTIAL. |

`r4/post-run-analysis.json`은 원본 raw bytes/hash/model/finish=stop·ledger/계획/입력/기존 source/Web 불변을 검사했다. observer `c58ecf3e7a514975b9ee4548e00a0bff`15.516초/1049출력토큰, planner `aedcd74405b94512b519995ee7168bfb`12.969초/2912출력토큰. r4 plan SHA `b4ba07cc51dda81ea733742b8d76e5fe10d74f04d7ba546b4efc200048a4b031`, scene `7bc8cadb06e56e4b0bf8020f18a576cb136bffa8e4c9d6cdcb73b6c8e4a79aa0`; 입력 `2b2393c11597f89589f77ae9d1c1f66bb97d5e451c1275f74298cd068387f656`. `saved-generation-reopen.json` 종료 후 재열기 PASS·project SHA `0ea4dc155c528cdc19eae2bc0cd1fd801db07f04ce31c2a5c249b4ca67459e83` 불변·provider/robot/자동 Build/Run0. Host/capture PASS·browser_closed=true·supervisor stopped.

누적 ledger116→126/219, 이번10회=received7/rejected3, 진행 중0/lock없음. 계산+예약USD0.15216670→0.16375798, 증가0.01159128(약1.16센트, 청구서 확인 아님). 이전 outcome_unknown2는 보존/예약 부담 유지하며 새 미완료로 오분류하거나 환불 처리하지 않았다. 총219 잔여가 있다고 이번10회 승인을 무한 확장하지 않는다.

### 수정과 검증

- 기존 `photo_layout.py`의 모델 wire 계약: furniture 및 floor prop는 floor/null parent·part·height/centre로 묶고, 알려진 prop의 surface/drape는 parent ID와 실제 library part를 하나의 분기로 묶었다. bed/body 같은 불법 조합·floor와 desk parent의 혼합을 방지한다. blind는 wall/knownwall+height, ceiling light는 ceiling/ceiling으로 고정한다. unknown/generic 계약이나 독립 compiler의 거절을 우회하지 않는다.
- 모델 치수 wire 최소.001·모든xyz 양수 및 compact JSON/root 완료를 명시하고 기존 catalog의 추정 prop 치수를 전달했다. 0 치수 clamping·후보 수동 수정·원본 schema 버전 의미 변경은 없다.
- 기존 backend/검사 CLI에 **명시 live 평가만** 전체90..180초 deadline을 허용했다. 제품 기본90초·compact OFF/no-thinking 기본 정책은 그대로다. browser 검사기는 failed/cancelled generation의 실제 원인을 먼저 반환하여 ‘Run 버튼 안 나옴’으로 덮지 않는다.
- live host도 opt-in profile-generation을 전달한다. 검증 실패는 허용된 `PHOTO_*`/`PROVIDER_*` code만 공개 진단으로 연결하며 모델본문/secret 예외 text는 제외한다. r3 exact replay의 최종 root succeeded에도 첫 실패 `PHOTO_RELATION_FLOOR_INVALID`가 남는다. r4 정상에는 first_error=null·profile_row30을 확인했다.
- exact replay는 완료된2응답 외에 검증된 observer→planner failed→repair passed의3응답을 허용한다. 원 결과 FAIL도 이후 유효 committed plan의 provenance가 정확할 때만 이전 실제 응답 재생으로 인정하며, request/schema/raw hash나 단계/수정횟수가 다르면 거절한다.
- 최종 Provider121/Core302/사진관련 integration34/diagnostics131/exact12/cap7 PASS, Node e2e syntax PASS. 수는 중복이며 합산하지 않는다. 초기 잘못된 테스트 PYTHONPATH/Temp WinError5·검사기 assertion 실패는 당시 실패로 남고 성공 명령과 구분한다. 실제 두 run과 exact replay로 변경된 경로를 확인했으나 새 전체 Web414/type/build·현재 source package 인수로 복사하지 않는다.

### 사진 품질 및 다음 작업 — 실행 PASS와 구분

`r4/generated-ready.png`를 원 사진과 직접 비교했다. 침대/옷장/책상은 기존 parametric library의 실제 형태로 렌더되고24개 목록도 유지되지만, **방10×12m/120m² 과대 추정, 넓게 떨어진 가구와 사진에 맞지 않는 배치**가 보인다. r3는 방4×5m였지만 옷장 좌우/천 부착/책상 아래 bag의 의미상 오류가 있었다. 같은 schema 합법성과4개 축 위치·3개 지지 관계 PASS만으로 이것들을 검사할 수 없다. 자동 품질 기록도 `status=PARTIAL`, `large_room_scale_warning=true`, `metric_scale_validation=UNVERIFIED_NO_MEASUREMENTS`, `full_photo_reconstruction=UNVERIFIED`다. **사진 정밀복원/일반 모델 성공률/전체 데모 준비 PASS가 아니다.** 같은 알려진 사진·검토된 inventory를 사용한 유한 시도이고 unknown 방의 자율 관측 능력도 인수하지 않았다.

1. 과대 room scale 경고를 품질 보정/검토 단계에 연결하고, 사진의 상대 거리·옷장 오른쪽·clothing/bedding/bag의 의도된 부착/바닥 관계까지 검사를 확대한다. 실측 없는 미터 값은 추정으로 남기며 임의 크기 고정/방 확장/누락으로 통과시키지 않는다.
2. 이후 별도 승인 fresh 모델에서 수정 전후 품질을 확인하고 기본90초/출력 정책의 안정성을 인수한다.180초 평가 성공을 제품 기본 안정성으로 표시하지 않는다. 이번 승인10회는 종료했다.
3. v347 frozen554-file package/296회귀/actual4-case는 당시 버전의 근거다. 이번 source 변경을 담은 새package와 저장소 밖 재인수는 NOT_RUN; 전체 diagnostics/load/GPU/장시간도 잔여다.
4. corrected ARM64 driver는 이미 Oct6 빌드/연결돼 device-free/read-only 근거가 있다. 다음 현장에 현재 boot/release와 stop 자격·실제 corrected scan lifecycle/odom/TF/time/extrinsics/방 정합·bounded 자율 목표/Stop을 확인해야 한다. 이번 로봇 접근0이며 전원만 켜면 데모가 끝난다고 보장하지 않는다.

whole=false·P2/H5-H6/C3-C6/F0-F1 PARTIAL, 기본 정책 및 물리 guard 불변. 아래 v347 이하는 당시 이력이다.

## v347 — 요청한 로봇 없는 세 검증 묶음 (2026-10-08)

이 절이 최신이다. 아래 v346 이하의 현재/미검증 표현은 당시 이력이다. 로봇 OFF, SSH/serial/실센서/모터/배포/설치/commit/push/새 에이전트0. 기존 원본·dirty·v1/v2 의미·실물 잠금과 stop/scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s를 유지했다.

| 검증 묶음 | 현재 결과 | 근거와 한계 |
|---|---|---|
| 실제 LLM→3D→저장/재열기 | 텍스트 PASS, 사진 FAIL | 실제 모델 사용. 평가 전용 host이지 생산 정책 전체 인수/일반 성공률이 아니다. |
| 입력 만료·동적 장애물·왕복/Stop | 지정 사례 PASS | 합성 native 및 실제 Isaac; Wi-Fi/실물 안전·장시간 전체 GPU 부하 인수는 아니다. |
| 최신 패키지 저장소 밖 실행 | 고정 회귀296 및 실제4사례 PASS | 기존 런타임·개발 package. clean install/회사 PC/실물 NOT_RUN. |

### 1. 실제 LLM 텍스트·사진·저장 재열기

- `artifacts/pre-demo-20261008/pricing-r2/pricing.json`: 기존 공식 인증 catalog에서 정확한 Gemma 관측/Nemotron Nano 계획 두 모델의 가격·context/image 기능 확인, inference0. 가격 checker가 원 승인60만 고집해 확장219 ledger를 거절하던 문제를 고쳤다. 원 한도/요금/과거 request를 갱신·초기화하지 않고 기존 승인 ledger를 검증하며 한 실행 최대5를 유지한다. 첫 pre-network 실패 보존.
- `live-text-default-r1/result.json`: 기본 provider 설정(수정 옵션 없이) 실제 텍스트→실제 Isaac PhysX 도착/Stop/숨긴 우측 화면/새로고침/초기화 PASS. 실제2호출(수정1 포함), frame 관측151. `production_default=false`는 평가 host 표시다. fixture 응답을 실제 LLM 결과로 바꿔 기록하지 않았다.
- 같은 폴더 `saved-generation-reopen.json`: 프로세스 종료 후 원본 SHA `37bfa1cc7e2a7377e55eb3e12623a2417fa2f82683c183d2fd7a5510046d2776` 불변·같은 입력/계획/scene 재열기 PASS, 추가 provider/Build/Run/로봇 명령0.
- 승인된 침실 사진 SHA `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`, 기존 Nebius Gemma/Nano·USD1/219 ledger·이번 최대5호출. `live-photo-default-r1/result.json` FAIL: Gemma 관측은 성공(14.766초), Nano planner8000(36.781초)와 허용 수정1의8000(29.047초)이 모두 `finish_reason=length`. 완성 계획이 없으므로 Isaac Build/Run을 하지 않았다. 90초 timeout이나 Isaac 렌더 결함으로 오분류하지 않는다.
- 남은2만 사용한 `live-photo-compact-r1/result.json` FAIL: 명시 compact/no-thinking10000, Gemma/Nano HTTP200/finish stop(12.640/17.016초). JSON은 완성됐지만 책상(`common.desk`)의 placement를 옷장 parent/body의 surface로 반환하여 `PHOTO_RELATION_UNSUPPORTED: furniture must be floor-standing: desk`로 거절했다. 기존 host 한도2가 세 번째 수정 dispatch를 막았다. 추가 호출/자동 새 run/잘못된 후보 저장 없음.
- `photo-compact-diagnosis-r2/diagnosis.json`: 원본 두 HTTP 응답의 SHA/bytes/model/finish와 원 요청/response-format SHA를 정확히 대조해 실제 제품 validator로 거절 원인을 재생했다. **신규 호출0·수동 수정0·DIAGNOSIS_ONLY**, 원 입력/ledger/결과/응답 불변, source hash 포함. 기본 경로로 승격하거나 새 LLM 성공으로 계산하지 않는다. r1 진단도 보존.
- 누적109→116/219, 이번 실제7호출(텍스트2+사진5), pending0; 계산+예약USD0.14391436→0.15216670, 증가0.00825234. 청구서 확인 아님. 이 승인으로 추가 사진 호출을 하지 않는다. 사진 경로는 **첫 성공0/두 시도 모두 FAIL**이며 이 소수 시험을 일반 성공률로 표현하지 않는다. 방 크기 실측/사진 복원 정밀도도 미검증이다.

### 2. 입력 만료·실패 대응·동적 환경·실제 왕복

- `remote_observed_adapter.py`: admission된 SURVEY/ALIGN에도 기존 독립 input renewal/watch를 사용한다. 느린 보고서/visual callback이 native 입력250ms를 소진하지 않도록 했으며 owner/source/Stop/guard 검사를 유지하고 세션·기한을 재설정하거나 이동을 재승인하지 않는다. `goal_watch_cycle` 기록은 기존 goal-handoff adapter에만 남겨 cold archive 계약을 보존한다.
- `artifacts/pre-demo-input-red-20261008/slow-record`: `mission_started`의 PC 기록 callback350ms로 `INPUT_DEADLINE_EXPIRED`를 결정적으로 재현했다. assertion 전에 원본/EVIDENCE_ONLY 반출, cleanup0 확인. 이것은 한 로컬 원인이며 과거 원본 없는 v346 병렬 실패나 실제 Wi-Fi 단절의 동일 원인이라고 확정하지 않는다.
- 첫 green의 native 성공 뒤 archive가 새 event를 거절한 ERROR, 다음 suite의 survey 두 사례가 같은 export 폴더를 쓴 ERROR는 보존했다. 이벤트 범위와 검사기 사례명을 고쳐 `pre-demo-input-green2-20261008`의 정상·거절·Stop·survey·slow-record 및 `pre-demo-input-survey-rerun-20261008`의 정상/diagnostic survey를 확인했다. **고유6 시나리오 최종 통과, 단일 frozen suite6 PASS로 꾸미지 않는다.**
- `artifacts/verification/pre-demo-faults-20261008/verification.json`: 261/375.468초 PASS, source93 불변·17case artifacts. source/identity/time/owner·Stop·Loop resource·배터리/unsupported motor load·stall+native halt+adapter cleanup+보고서 실패의 세 원인·pose clear 등을 포함한다. 실제 Isaac/실물 시험으로 표시하지 않는다.
- `artifacts/pre-demo-changing-20261008/verification.json`: 동적7/221.756초 PASS. 반응형 합성 raycast와 실제 App/정합/planner를 사용하며 injected pose나 실제 Isaac actuator/실물은 아니다. 우회 오차.020764m/clearance.36419m, 제한 우회.019914m/.370114m; 막힌/가린 목표 이동 차단, 45초 만료, 위치 상실 때 출력0·픽셀 제거 후 복구, 재배치 때 `POSE_JUMP_REQUIRES_NEW_SESSION`; 종결 속도 모두0.
- `loop-native-isaac-r1/verification.json` FAIL은 실제 preview 후 검사기가 이전 직접 Confirm 버튼을 기다린 `UI_CONDITION_DEADLINE`다. 제품의 현재 단일 질문 radio→Continue 흐름으로 CDP/Playwright 검사기를 고쳤으며 이동 승인을 API로 우회하지 않았다. 원 FAIL/스크린샷 보존.
- `loop-native-isaac-r2/verification.json` **PASS**: 실제 별도 Isaac/authenticated Bridge와 합성 native world·actual built Chrome, 왕복6구간262.192초. 한 Repeat 승인·매 구간 fresh bounded planning/receipt, Stop 뒤7번째 구간 중단/worker_active=false/motion_authorized=false, reload 추가 operation0. current-visible/ended-hidden·source/Web 불변·owned children 정상 종료/profile 제거 PASS. 짧은 A↔B 고정 목표 시험이며 실제 방 전체 주행/실물 안전 인수가 아니다. 10초 간격 heap 약3–4.5MiB/상한256MiB, 서로 다른 실제 painted frames 확인; 새30분 soak/전체 CPU/GPU 부하 검증은 아니다.
- 최종 Web414/45files/24.89초, type/build PASS. JS `index-Bekf-UYM.js` SHA `1a6b2919c9cf3b297cd9ae7759a510e753dc2c9511c58f83ad821494afe60614`. 기존 jsdom canvas/chunk500kB 경고는 남는다. 가격/host call cap 관련14 PASS(.985초); CLI 누락 인자 FAIL과 sandbox Temp/spawn EPERM은 보존하고 범위 제한 실행에서 재검증했다. 위 테스트 수는 겹치므로 합산하지 않는다.

### 3. 최신 패키지 실행 PASS

`artifacts/offline-release/tp-20261008-v347-dev-r3`: dirty 개발 snapshot554 members/23,404,775bytes, 기존 dist·로컬 고정 Pillow wheel만 복사/hash. 새 install/download 없음. 기존 r1/r2와 v342 보존. manifest SHA `becf404457b08b6da78b39c7342a2148783ba7521645a7cf09fde8fe61b9ae30`. Canonical source에서 만들었지만 release 실행은 checkout 밖 임시 격리 복사·`-I/-B`·package module origin 확인을 사용했다. 사진/키/raw가 release member가 아니며 fixed saved scan6파일은 별도 테스트 입력으로만 전달했다.

`artifacts/pre-demo-20261008/package-r1/verification.json` **PACKAGED_WEB_API_ISAAC_OFFLINE_PASS**:

- App/core296 PASS, failure/error/skip0, rclpy import0. 원 source에 추가한 가격/한도14 회귀도 package 안에서 실행했다.
- 동일 package actual normal/storage/geometry/startup **4/4 PASS**, 모두 exit0. normal actual current frames14/active receipts15; storage frames13/receipts11과 보고서 저장 실패·주 원인 보존/오류 UI·Stop 확인. geometry는 별도 실제 Kit의 `GEOMETRY_TRANSACTION_AND_NEGATIVE_CONTRACTS_RUNTIME_PASS`다. generic aggregator의 frame0은 그 다른 receipt schema를 count하지 못한 값이며 실제 미실행으로 오분류하지 않는다. 이것은 source metadata 보정/negative contract 시험이지 사진 LLM 품질이나 실측 보정 인수는 아니다.
- startup: 의도된 `isaac_import` 실패 checklist/allowlisted 보고서/한 번 Retry UI와 새 owned session identity·기존 actual Isaac 복구 PASS; provider/scene/robot 명령0. 실제 회사 PC 전체 설치·자동 복구 가능성을 보장하지 않는다.
- release/복사 manifest·검사 driver·별도 raw 입력 불변, isolated copy 제거 PASS. Runtime마다 전용 Windows Job을 닫아 자체 하위 프로세스만 정리했다. 닫기 직전 하위 수2/2/24/0이므로 package 전체를 '모든 하위가 자연 종료했다'로 표현하지 않는다. 타 프로세스나 사용자 Chrome profile을 종료하지 않았다.
- clean_install/physical_validation NOT_RUN, package target_binary NOT_BUILT, offline_implementation_ready=false/physical_demo_ready=false 그대로다. 이 package의 target NOT_BUILT는 Oct6 실제 ARM64 빌드 사실을 취소하지 않는다. 마지막 Baseline/Memory/README/progress의 결과 기록 갱신은 frozen manifest를 다시 쓰지 않았다.

세 묶음을 모두 실행했으나 **사진 때문에 전체 데모 준비 PASS는 아니다**. 이번 turn의 공유 ledger116/219·pending0은 package/오프라인 재생 뒤에도 그대로다. WMI 진단 조회 접근 거부는 재시도/권한 우회하지 않았고 독립 검증을 계속해 완료했다.

### 남은 작업과 다음 현장 경계

1. 기본 사진 경로의 출력 정책과 종류별 지지 관계 계약/수정 budget을 검토하고 **별도 승인된 fresh 사진 시험**으로 확인해야 한다. compact의 문법 성공을 배치/품질 성공으로 바꿀 수 없다. 실측 없는 크기는 추정으로 남는다.
2. 남은 선택적 diagnostics raw 제한 조회/세부 O 및 전체 GPU/부하/장시간 안정성은 이 유한 회귀로 전부 완료하지 않는다.
3. corrected ARM64 드라이버는 Oct6에 빌드/연결돼 device-free9/9·배터리615·target read-only PASS_NO_SENSOR_ACCESS가 있다(`robot-driver-path-integration-20261006.md`, `robot-target-build-20261006.md`). 옛 '컴파일러/target binary 없음' 기록은 당시 이력이다. **그 수정본의 실제 scan lifecycle은 미검증**이다. 다음 현장은 현재 boot/release 점검→센서 scan/odom/TF·시각/footprint/extrinsics→현재 stop 자격→초기 정합/방 보정→한 bounded 자율 목표/Stop을 승인된 범위로 인수해야 한다. 전원만 켜면 전체 데모 완료라고 보장하지 않는다.

whole=false, 기본 compact OFF·P2/H5-H6/C3-C6/실물 F0-F1 PARTIAL, 예약 PAUSED 유지. 원본 사진·raw/모든 실패·기존 실물 기록은 보존했다.

v346 당시에는 아래 **임무 조사 정합과 보정 ACK 연결**로 동일 실행 ID에서 저장 성공과 ACK 확인, 실패와 Stop, cleanup과 필수 보고서 저장을 구분했다. 합성 native 정상·거절·Stop 단독 검사는 통과했지만 병렬 실행의 입력 만료 원인은 미확정이었다. 이후 v347의 결정적 callback 재현은 위 절을 따르며, 원본 없는 과거 실패의 원인을 소급 확정하지 않는다. 앞선 v345 실제 Isaac과 v342 단독30분 결과를 새 source의 실물·장시간 인수로 복사하지 않는다.

현재 실행의 앞뒤 기록을 찾아 원인 분석에 쓰는 연결 조회를 기존 Diagnostics에 추가했다. 기록에 명시된 참조만 연결하며 같은 요청 이름이나 시간만으로 인과관계를 추정하지 않는다. 이번 범위는 오프라인 진단과 화면 유지 검사이며 실제 사진 복원 품질이나 실물 데모 완료를 뜻하지 않는다.

## 구현과 조회 범위

기존 인증된 `GET /v1/product/diagnostics/{execution_id}/graph`에서 선택 실행이 참조하는 기록과 선택 실행을 참조하는 후속 기록을 함께 반환한다. `launch_execution_id`, `scene_edit_execution_id`, `command_execution_id`, `retry_of`, 그리고 `evidence_kind=generation_execution`인 `evidence_id`만 사용한다. 세부 화면의 **Show linked execution graph**를 명시적으로 눌러 조회하며 Incoming과 Outgoing을 구분하고 원 실행으로 이동할 수 있다. 화면을 떠나거나 다시 조회하면 옛 graph와 늦은 응답은 버린다. graph 조회 실패는 정상 상세 기록을 지우지 않는다.

활성 프로젝트 인증을 그대로 적용한다. 다른 프로젝트, 없는 파일, 손상·링크 파일은 unavailable/unknown이며 경로나 다른 프로젝트의 내용을 공개하지 않는다. 사진·raw 응답·credentials는 조회와 기존 기본 export에 포함되지 않는다. GET은 기록을 쓰거나 Build/Run/SSH/로봇 명령을 만들지 않는다. 기존 상세/export와 v1/v2 scene/history 직렬화 의미는 유지한다.

graph는 전체 분산 추적 시스템이 아닌 **한 단계 명시 참조 snapshot**이다. 최대32 nodes/128 edges, 역방향 검색100 records, root 디렉터리4096 entries, 각 실행의 event 디렉터리4096 entries/128 chunks, 총 read8MiB, event body1MiB 기준으로 제한한다. 큰 기록은 manifest 참조만 남기고 상태 unknown/partial로 표시한다. 부분 조회·손상·이벤트 잘림은 partial로 표시하며 빠진 링크를 성공 증거로 삼지 않는다. 최신100 범위를 넘는 역참조는 이 화면에서 모두 찾는다고 보장하지 않는다.

## 회귀 결과

- 관련 Python 전체126 PASS/64.104초. 양방향 late-bound 참조·retry·cycle·무관한 ID·타 프로젝트·없는 파일·큰 로그·node/역검색 상한·hardlink·조회 중 원본 hash 불변·인증 GET 및 원래 provider/broker/가짜 로봇 계약을 포함한다.
- 추가 대용량 read·디렉터리 탐색2 PASS/7.429초. 12개의900kB event body와 실측 read 계수로 총8MiB 이내를 확인했다. 탐색은4096 entries만 처리하고 다음 sentinel에서 중단한다. partial/unknown을 유지하며 history를 다시 쓰지 않는다.
- 최종 Web 전체387 PASS/45 files/35.92초, type/build PASS. 진단/API41 PASS도 별도로 확인했다. Python·패키지·Web 집계는 중복이 있으므로 고유 전체 테스트 수로 합산하지 않는다.
- 현재 built assets: `index-Oaq5gnp6.js`, `index-DVz_8n25.css`. JS598.64kB/gzip174.89kB, 기존500kB chunk 경고는 해결한 것으로 표시하지 않는다.
- 장시간 검사 종료 뒤 추가 경계2개를 먼저 FAIL로 재현했다: 중첩 event 폴더를15000 entries 탐색한 경우와 UTF16 manifest 허용/legacy 형태의 list·dict version에서 TypeError가 나는 경우다. UTF8 계약·version 문자열 선검사·중첩4096 entries/128 chunks 조기 제한으로 수정했다. 이후 관련 전체 **130 PASS/68.987초**, 원본 불변·손상 record unknown/partial·정상 다른 record 조회를 확인했다. 최초 제한 실행의 Temp WinError5/파일 누락은 테스트 환경 실패였고, 기존 허용된 자체 Temp 범위 실행에서 제품 결함을 별도로 재현했다. 별도 `pnpm typecheck` 명령은 없는 script라 실패했으나 기존 `build`의 `tsc -b && vite build`가 통과했다. 이 두 결과를 모두 통과한 것으로 합치지 않는다.
- 위 회귀 출력의 지속 요약은 `artifacts/verification/execution-graph-reader-boundary-20261008-r1/result.json`이다. 도구에서 관측한 수치를 정리한 수동 기록이며 자동 runtime receipt나 실제 제품 execution ID로 꾸미지 않는다. 수정 전 source는 기존 v341-dev-r2 package에 보존된다.

## 실제 Chrome과 Isaac 검사

`artifacts/verification/execution-graph-post-edit-20261008-r1/result.json`은 **FAIL**로 보존한다. 실제 generation→Build·launch graph, PhysX 도착·Stop/reload/reset, 부모/자식 치수·회전 편집, 실제 케이블 pointer drag/rotation, 두 연속 Undo는 통과했으나 편집→채팅 전환 직후 soak 첫 읽기에서 canvas0으로 실패했다. 실패 screenshot에는 이후 현재 렌더가 표시되어 있다. backend frame 준비만 기다렸던 검사 시작 조건에 browser current-image와 canvas mount의15초 bounded wait를 추가했다. 이 실패를 제품의30분 화면 유지 PASS로 바꾸지 않는다.

별도 `execution-graph-post-edit-20261008-r2`는 **FAIL**이다. 편집 후1800.876초/1699회 중 browser current-image 누락1회(elapsed819.093초), server current frame은 같은 관측에 존재했다. canvas는1개, 추가 Build/Run0, JS heap first8633676/last10561464/peak13992108bytes, page error0, 자체 launcher 종료 succeeded다. 서버 frame6151→6159→6165 동안 브라우저 표시가 한 표본에서 숨겨졌다가 복귀했다. 당시 별도 Web/패키지 회귀와 시간이 겹쳤으나 자원 경쟁은 가설이며 정확한 원인은 미확정이다. 이를 PASS로 바꾸거나1초 freshness 기준을 늘리지 않는다. 기존 검사에는 DOM frame age/상태 및 image request 지연 기록이 없으므로 보완한 별도 단독 검사에서 확인한다. 두 실행의 고정 모델 응답은 명시적8×8m/24-object 테스트 fixture이며 새 사진 해석이나 실측 정밀도 검증은 아니다.

**r3 단독 actual PASS**: 편집 후1801.016초/1698 samples/current-image 누락0, 별도 MutationObserver의 숨김 전환0, canvas1, 추가 Build/Run0. Chrome JS heap first7750100/last8136968/peak13748988bytes; 전체 process/GPU 누수 판정은 아니다. sampled API 최대250.8ms, 표시 frame 최대 age730.548ms, server frame 최대 age437.071ms다. 이미지 응답10704 중 정상 교체409은560이며 기타 HTTP 오류0, page error0다. 편집·두 연속 Undo·source2.1/24관계 및8-operation 디스크 재열기·owned shutdown succeeded·inference source 불변을 확인했다. desktop/mobile 및 현재 exact Build/launch graph도 통과했다. 단독 정상 조건 인수이며 r2의 동시 부하 실패 원인을 확정하거나 해결한 증거는 아니다.

r3의 image 응답 hook은 headers 시점이라 `responseEnd=-1`/duration null이었다. 이를 body가 완료된 `requestfinished` 시점으로 옮기고, 검사 중간 assertion이 실패해도 당시 sample을 partial로 남기며 숨김 전환0도 명시 gate로 추가했다. 30분 완료 후 로그 reader 경계가 추가로 보강됐으므로 최종 source의 **r4 PASS는60.126초/57 samples의 짧은 actual 재검사**로 구분한다. 공백/숨김 전환0·image 응답336/409 및 기타 HTTP오류0, 마지막32 image 완료 시간2.088–122.414ms, graph/편집/두 Undo/디스크 재열기/owned 종료·inference source 불변 PASS다. r3의 Web/Isaac 표시 구현과 built asset은 바뀌지 않았다. r4를30분 검사나 모든 중간 실패의 partial 수집 인수로 확대하지 않는다.

## 로깅과 함수 프로파일 비용

`scripts/verify_diagnostic_compile_overhead.py`는 기존 `SiteDraftRecord.create` 순수 계산을 동일 저장24-object source로 진단 OFF·기본 event ON·cProfile ON에서 비교한다. mode 순서를 회전하며 각각 warmup3회, 시간60회, 별도 메모리10회를 수행한다. 모든 결과 DTO가 원 저장 source와 같고 원본 bytes가 바뀌지 않으며 저장 진단에 손실이 없을 때만 PASS다. 시작/종료 trace·flush는 timed call 밖이고 비동기 writer 경쟁은 wall에 포함된다. 전체 App나 로봇 입력 deadline의 비용 측정은 아니다.

최종 `artifacts/verification/diagnostic-compile-overhead-20261008-r2/result.json` PASS:

| 모드 | wall 중앙값 | wall p95 | aggregate thread CPU 평균 | 별도 traced peak | events 및 저장량 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 진단 OFF | 6.4129ms | 7.8324ms | 6.25ms | 543145bytes | 0 |
| 기본 event ON | 6.3801ms | 8.1415ms | 6.5104ms | 339265bytes | 292 / 167435bytes |
| 함수 profile ON | 26.3101ms | 30.4445ms | 26.5625ms | 592470bytes | 2555 / 1342474bytes |

이 표에서 event ON의 작은 중앙값 차이를 성능 개선으로 단정하지 않는다. profile은 이 고정 call에서 약4.10배의 wall 비용을 보였으므로 기존 opt-in을 유지한다. Windows의 짧은 thread CPU는 OFF36/60·event35/60·profile1/60 samples에서0으로 양자화되어 중앙값이 실제 CPU 비용을 대변하지 않는다. 합산 평균과 원 sample을 함께 보관한다. traced allocation peak는 별도 검사 중 Python 할당량이며 process RSS·GPU 메모리나 누수 판정이 아니다. 앞선 r1도 PASS이지만 CPU 중앙값0의 해석 한계를 설명하기 전 결과이므로 원본을 보존한다.

## 개발 패키지와 현장 후보

앞선 dirty 개발 패키지 `artifacts/offline-release/tp-20261008-v341-dev-r1`은551files/23349519bytes로 생성했고 저장소 밖278 App/core 회귀 PASS다. 추가 경계 회귀를 포함한 중간 `tp-20261008-v341-dev-r2`는551files/23352232bytes, manifest hash `fca5d67d9124ec8f0926cf607282a378be6d2ec7fd6487b4aaab9a862a27a0a8`다. 저장소 밖280 App/core 회귀 PASS, device runtime 미수입·분리 복사 제거·원본 test scan 및 driver 불변 PASS다. `execution-graph-package-core-20261008-r2/verification.json`이 근거다. 기존 로컬 hash-pinned wheel과 built Web만 재사용하며 설치·다운로드하지 않았다. 이 중간 package의 actual runtime은 NOT_RUN이며 아래 v342가 최종 package 인수다. 과거 package와 raw/실패 기록을 수정하지 않는다.

현장 collection 후보 `artifacts/robot-field-candidates/f2e8f5ff8dcc45238d0330b41ec98514/manifest.json`은 syntax/import/contracts/unchanged PASS_LOCAL_ONLY이고 마지막 `checked()` 재조회도 PASS다. 92members/source ID `634e56cec63be2eee5ccf5ed0325f7bccb1fd96488bfb816aae3be039dfbd071`는 이전 수집 payload와 같으며 PC 코드 fingerprint는 갱신됐다. 기존 SSH/key/host는 존재만 확인했다. corrected driver는 기존 build PASS_NOT_ACTIVATED, autonomous_demo_ready=false, robot_contacted=false다. 후보의12시간 유효기간과 현장 승인 조건은 유지하며 이는 SSH·배포·센서·모터 승인이나 F0 전체 등록이 아니다.

**최종 package PASS**: 로그 reader의 마지막 수정 뒤 immutable 개발 package `tp-20261008-v342-dev-r1`을551files/23355151bytes로 생성했다. manifest SHA256은 `3223ea837043d95aad8e38803300285207924529cee0a2814c8554cbbef51c28`다. `execution-graph-package-full-20261008-r1/verification.json`은 **PACKAGED_WEB_API_ISAAC_OFFLINE_PASS**다. 저장소 밖 declared-files 복사/기존 runtime의 App/core282 tests PASS(failure/error/skip0, device runtime 미수입), 실제 local normal/storage/geometry/startup4 cases 모두 PASS/exit0, saved scan·검증기 source 불변·package manifest 검증 및 isolated copy 제거를 확인했다. geometry case는 actual owned USD/negative 계약이며 physics/browser 인수로 확대하지 않는다. 실제 외부 모델·target binary·clean install·실물 검증 NOT_RUN, offline_implementation_ready=false/physical_demo_ready=false를 보존한다. 설치·다운로드·로봇 배포는 하지 않았다. 새 개발 패키지의 한정 인수이며 전체 D01–D12 완료가 아니다.

**최신 현장 collection 후보**는 `artifacts/robot-field-candidates/ae380eb744ef4f9f8a9706ea9dbcce69/manifest.json`이다. syntax/isolated import/contracts/unchanged PASS_LOCAL_ONLY 및 `checked()` PASS,92members/source ID는 위 후보와 동일하다. 현재 PC fingerprint만 갱신됐으며 robot_contacted=false/motion_authorized=false다. 기존 후보와 원본은 보존한다. 전체 autonomous 준비 gap·12시간 유효기간·새 현장 승인 필요는 변하지 않는다.

## 남은 범위

- O3/O4/O5는 이번 한정 검사와 다른 미측정 범위를 구분한다. 일반 trace의 누락된 remote ACK/외부 edit 등 O2 경계, 권한을 갖춘 제한 raw/evidence 조회·전 범위 관계 탐색은 남아 있다.
- 30분 **idle render**는 움직이는 Loop 장시간 시험, 전체 process/GPU 누수 검사, 다른 PC의 clean install을 대신하지 않는다.
- r2의 동시 부하 조건 공백1회는 원인 미확정이다. 단독 r3의 공백0을 부하 문제 해결로 바꾸지 않는다. r4의 완료 timing은 마지막32 requests만 bounded로 보관하며 모든 과거 전송 시간을 복원한다고 보장하지 않는다. 중간 assertion의 partial sample 보존은 보강했으나 모든 crash/fault 조합의 인수는 아니다.
- opt-in photo1.2의 실제 LLM 성공률·사진 크기/위치/지지 관계 품질(P2)은 새 유료 호출 없이 이번에 확인하지 않는다. 추정 geometry를 실측이라고 표시하지 않으며 compact 기본 OFF를 유지한다.
- F0 reviewed release·autonomous profile/좌표 calibration·qualification과 F1 새 driver 실제 scan/odom/TF·Stop·survey/목표/Loop 인수는 미완료다. 전체 D01–D12·whole=false, H5-H6/C3-C6 PARTIAL을 유지한다.

로봇·SSH·serial·실센서·모터·배포·유료 호출·설치·시스템 변경·commit/push·새 agent는 모두0이다. 정지/scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s·실물 임무 잠금, 기존 dirty·raw·과거 실패·v1/v2/hash를 보존한다. 요청된 추가2시간은 상한이며 안전한 유효 작업이 끝나면 시간을 채우려고 반복하지 않는다.

2026-10-08 추가 작업은10:23:30 KST부터12:23:30 상한으로 승인됐다. 이번 graph/로그 읽기 경계·on-off 비교·편집 후 단독30분/최종 source60초·같은 package 밖282회귀/actual4-case 묶음은 완료했다. 관련 source·후보를 고정하고 검증 뒤 문서만 갱신했다. 남은 전체 범위는 위에 구분하며 추가 계획·동일 PASS 반복으로 시간을 채우지 않는다. 과거 프로그램이나 로봇을 다시 시작하지 않고 자체 실행만 종료한 상태에서 이번 묶음을 마무리한다.

12:11 KST 최종 재조회에서 package4 cases 각각 returncode0/owned_tree=WINDOWS_JOB_CLOSED, 최신 candidate `checked()` PASS/robot_contacted=false/motion_authorized=false, 선택된 제품·회귀·문서의 `git diff --check` PASS를 확인했다. Git의 기존 LF→CRLF 경고와 Vite chunk 크기 경고는 별도로 남는다. 계획된12:23:30 상한 전에 이번 묶음을 종료하며 예약을 다시 활성화하지 않는다.

## 후속 화면 수신 복구

사용자가 불필요한 시간 늘리기 없이 후속 구현을 요청한 범위다. 기존 TwinViewport/API와 기존 실제 인수 runner를 수정했으며 새 계획·외부 관측 서비스·유료 호출·로봇 실행은 추가하지 않았다.

짧은 회귀로 다음 결함을 수정 전 재현했다.

- 선택적 오류 기록 POST를 await하는 동안 다음 화면 poll도 중단됐다. 이제 기록 전달을 수신 루프에서 분리하고 fetch/JSON body를 3초로 제한한다. timeout은 저장 여부 unknown이며 자동 POST 재시도는 없다. 늦은 ACK는 원 실패 ID를 보관하지만 복구된 UI를 다시 실패로 만들지 않는다. 같은 실패 재발 시 그 ID를 재사용한다.
- engine session/stage epoch/applied revision이 바뀐 뒤 image GET이 정상 교체409를 반환하면 이전 장면 픽셀이 잠시 current로 남았다. 관측 identity가 다르면 즉시 지우며, 같은 장면의 정상409는 여전히 신선한 픽셀만 유지한다. API 교체 시에도 이전 픽셀과 camera 준비 상태를 비운다.
- 네이티브 디코더가 반환하지 않으면 수신 루프가 영구 pending이었다. 기존 1초 frame 신선도 내에서 `viewport_decode_expired`로 실패를 알리고 metadata 수신은 계속한다. 해당 수신 인스턴스에서 미완료 native decode는 하나만 유지하며, 늦은 bitmap은 그리지 않고 한 번 해제한다. native API 자체는 취소할 수 없으므로 영원히 반환하지 않는 브라우저 decoder를 자동 복구한다고 보장하지 않는다.
- 첫 scene ACK 뒤 active viewport가 아직 없으면 정적 capture가 준비 대기 없이 두 번 즉시 실패했다. 기존 attempt 15초와 stage/revision 검사·취소를 유지하며 Kit update에 양보해 준비를 기다리도록 보완했다. viewport가 왜 그 순간 없었는지 모든 cold-start 원인을 확정한 것은 아니다.

최초 Web 집중 회귀는7 FAIL/36 PASS로 앞 세 종류의 경계를 재현했고, decoder 추가 회귀1도 수정 전 FAIL이었다. 수정 후 집중44 PASS, 최종 전체 **395 PASS/45 files/23.98초**다. `artifacts/verification/viewport-recovery-20261008-unit-final.json`이 자동 결과이며 기존387개를 포함한다. 신규 기능395개나 고유 전체 테스트 합계로 해석하지 않는다. 캡처 계약 전체 **11 PASS/0.100초**에는 late readiness/finite missing/cancel3개가 포함된다. 수정 전 이3개는1 FAIL/2 ERROR였다. 타입검사·빌드 PASS, 최종 built JS `index-BDbziwiZ.js`다. JSDOM canvas 미구현 출력과 기존 Vite500kB chunk 경고는 성공과 별개로 남긴다. 최초 Vitest spawn EPERM은 제품 결함이 아닌 실행 환경 제한으로 구분하며 승인된 기존 로컬 자식 실행에서 재현·검증했다.

### 실제 실행과 판정 불일치

실제 runner에는 명시적 fixture 전용 `--browser-diagnostic-delay`와 `--browser-decode-stall`을 추가했다. actual backend 기록은 정상 저장하고 브라우저 ACK만 보류하며, 실제 JPEG를 디코딩한 bitmap 하나의 완료만 보류한다. 제품·로봇 드라이버에 시험 주입을 하지 않는다. 자식 로그와 exit code도 `browser-worker.log`에 보존하며 결과 파일 누락을 PASS로 바꾸지 않는다.

`viewport-recovery-20261008-r1/r2`는 FAIL 보존이다. 지연 응답을 완료하기 전에 시험 route를 해제해 `Route is already handled`로 worker가 종료했다. 첫 기록에는 child log가 없어 FileNotFoundError만 남았으며 r2 로그로 원인을 확인했다. 이를 제품 결함으로 확대하지 않는다. `r3`은 첫 수정본의 지연 ACK·수신 복구/PhysX/Stop/진단 조회를 통과했다. `r4`의 새 decoder 검사는 통과했으나 기존 검사기가 서로 다른 두 오류 ID를 하나로 세어 전체 FAIL이다. 정확한 code와 ID 집합을 확인하도록 고쳤으며 신선도·제어 기준을 완화하지 않았다.

`r5`는 browser PASS/124frames였지만 별도 host capture는 두 번 모두 `viewport_missing` FAIL이었다. 당시 wrapper의 최상위 PASS가 이 실패를 누락했다. **r5를 전체 인수 PASS로 인정하지 않는다.** 원 JSON은 그대로 보존하고 정상 인수에는 host/capture PASS도 필수로 판정하도록 고쳤다. 의도적 apply/frame/pose/필수 저장 실패 시험과 정상 capture 요구는 구분한다.

최종 `artifacts/verification/viewport-recovery-20261008-r6/result.json`은 **PASS**이며 `host_capture_required=true`, host/capture/browser 모두 PASS다. 실제113frames, page error0, 고정 provider 소스 불변, 지연 ACK 이전 복구·재발 ID 재사용, metadata poll 유지·단일 decode·늦은 bitmap close1을 확인했다. decoder와 HTTP 오류는 각각 다른 exact saved ID/code다. 정상 PhysX 도착 오차0.039662706m, 다음 목표·채팅 Stop·fold/reload·승인 비재사용·reset·진단 graph/search/export·모바일과 owned launcher shutdown succeeded/worker exit0을 함께 통과했다. 원113frames는 실시간 렌더 근거이며 사진 인식·실측 정밀도·실물 주행 증거가 아니다.

### 현재 완료와 잔여

이번 수신 정체·늦은 ACK·이전 장면 노출·단일 decoder 관리·정적 capture 준비와 판정 누락은 위 범위에서 닫았다. 30분/동시 부하/전체 GPU 메모리 시험은 이번에 반복하지 않았다. v342 장시간 PASS나 개발 package를 새 Web/engine source의 인수로 복사하지 않는다. 기존 v342 package·field 후보·raw·과거 FAIL·v1/v2/hash·실물 잠금은 그대로 보존했고 새 package/field 후보는 만들지 않았다.

남은 우선 범위는 동시 부하 current-image 공백의 원인, 외부 edit/정합/remote ACK 등 다른 O 경계, 제한 raw 조회, 동적 Loop/전체 process-GPU 자원, P2 실제 LLM 사진 품질, 수정 source의 패키지 인수와 F0/F1 현장이다. 전체 D01–D12/whole=false/H5-H6/C3-C6 PARTIAL은 유지한다. 로봇·SSH·배포·실센서·모터·유료·설치·시스템 변경·commit/push·새 agent0, 예약PAUSED·정지/scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s 기준은 바꾸지 않았다. 시간대별 구현 시간과 검사 대기를 따로 계측한 것은 아니며 긴 검사로 시간을 채우지 않는다.

## 화면 지연 단계 분리

JPEG 응답을1100ms 늦춘 집중 회귀에서 실제로 디코딩하기 전 만료된 이미지가 `viewport_decode_expired`로 기록되는 결함을 재현했다. 이제 이미지 body 수신 후 캡처 시각을 먼저 검사하고 `viewport_image_expired`로 구분한다. 오래된 JPEG는 native decode에 넣지 않으며 기존1초 신선도와 Run 잠금, 읽기 복구, Build/Run 무재시도를 유지한다. 이 code만으로 네트워크 장애를 단정하지 않는다.

기존 인증된 display observation POST와 실행 진단에 선택적 `timings`를 연결했다. 허용된6개 수치만0~60000ms 범위로 검증한다. 기존5-key body도 그대로 허용하고 임의 필드·본문·headers·boolean·string·NaN·Infinity·음수·상한 초과는400으로 거부한다. 현재 scene과 최근5초 내 실제 frame ID 검사·원 Build 실행 참조·owner/scene/cause별 중복 억제·64개 상한·optional sink 오류 격리는 유지한다. 기본 export에는 raw나 개인정보를 추가하지 않는다.

단계 시간은 browser `performance.now()`로 측정한 metadata 요청·JPEG body 수신·native decode 대기·전체 poll 및 예약 callback 지연이다. frame age는 캡처 wall timestamp와 비교한 값이다. CPU 소비 시간, 서버 함수 시간, GPU 시간 또는 로봇 통신 시간으로 해석하지 않는다. 전체poll과 부분 단계는 중첩하므로 합산하지 않는다. 실행 기록의 서버측 생성 시간과도 구분하며, 기존 Diagnostics의 stage metadata와 export에서 조회한다. 기록은 매 프레임을 쌓지 않고 기존 실패 ID에만 저장한다.

### 회귀와 실제 결과

- 수정 전 Web17 중1 FAIL로 code 오분류를 재현했다. 수정 후 집중45 PASS, 최종 전체 **396 PASS/45 files/23.92초**, `artifacts/verification/viewport-timing-20261008-unit-final.json`; 기존395개가 포함된다. 타입·빌드 PASS, JS `index-yv7okukb.js`. 기존 Vite chunk/JSDOM canvas 경고는 남아 있다.
- viewport Python 전체 **22 PASS/8.347초**; optional legacy·수치 검증·저장·중복 억제·현재 frame·인증·제어권 비변경을 포함한다.
- 진단 전체130회귀는 **FAIL/67.467초**다. 3개 child-process test의4개 assertion이 자식의 `ModuleNotFoundError: twinpulse_core`로 실패했고 다른127 tests는 실패가 없었다. 부모의 sys.path 변경이 자식에 상속되지 않는 실행 환경 문제다. 제품 코드를 고치거나 설치하지 않고 해당 명령의 기존 src PYTHONPATH만 지정해 실패3개와 privacy filter1개만 재검사해 **4 PASS/2.346초**를 확인했다. 전체130 재실행 PASS로 기록하지 않는다.

`artifacts/verification/viewport-timing-20261008-r1/result.json`은 FAIL 보존이다. HTTP와 held-decoder 검사는 통과했고 image-expiry 진단도 실제 저장됐지만, 다음 신선한 응답으로 빠르게 복구돼 검사기가 순간적인 오류 표시를 놓쳤다. page error0/host capture PASS/owned shutdown succeeded였으며 이를 제품 복구 실패라고 단정하지 않는다. 검사에서만 후속 image 응답을 보류해 실패 상태를 관측하고, 관측 후 해제·pending handler 완료 뒤 route를 해제한다. 제품 오류를 오래 표시하거나 복구를 지연하는 변경은 없다.

최종 `artifacts/verification/viewport-timing-20261008-r2/result.json`은 **PASS**, host_capture_required=true, browser/host/capture PASS·worker exit0·122frames·page error0·inference source unchanged=true·owned shutdown succeeded다. 실제 JPEG response를1250ms 보류해 frame26의 이미지 수신1268.1ms/metadata5.1ms/decode0ms/전체poll1273.2ms/frame age1337.03ms/schedule lag0을 저장했다. 별도 decoder 실패는 image4.6ms/decode856.3ms로 구별된다. HTTP503·decode-expiry·image-expiry는 각각 다른 exact ID이며 재발 HTTP는 기존 ID를 재사용한다. 지연 시 Run 잠금·오래된 pixel 숨김, 해제 후 신선한 화면 복구·추가Run0, 정상 PhysX 도착 오차0.039662764m·다음 채팅 목표·Stop·fold/reload·승인 비재사용·reset·진단 graph/search/export·mobile을 통과했다.

### 이번 범위의 한계와 다음 작업

실제 Isaac의 JPEG가 들어오는 경로에서 전송 지연과 decode 지연을 분리한 것이 이번 v344 완료선이다. **과거 동시 부하 공백의 원인은 여전히 미확정**이다. CPU 부하·Wi-Fi 원인이나 모든409 교체 경합·metadata 장애의 원인이 해결됐다고 주장하지 않는다. 새30분/동시 부하/GPU 자원 시험·실제 LLM 품질·새package·실물 인수를 실행하지 않았다. 다음 원인 분석은 실제 공백의 단계 시간과 당시 process/GPU 부하 근거를 대조해야 하며, 단독 PASS나 제어된 delay를 과거 원인으로 대체하지 않는다. 다른O/동적Loop/P2/패키지/F0-F1 및 whole=false/H5-H6/C3-C6 PARTIAL은 유지한다. 원본/dirty/과거FAIL/구package·candidate/v1-v2/hash/실물 guard를 보존했고 유료·로봇·설치·설정·배포·commit/push·새agent0, 예약PAUSED다.

## 현재 JPEG와 프레임 정보 동시 수신

### 결함과 제품 변경

화면 metadata의 frame 번호를 받은 뒤 별도 JPEG를 요청하는 사이 최신 프레임이 교체되면 정상적인409가 발생한다. 수정 전 집중 Python 회귀에서 이 경합을 재현했으며 새 `image_packet` 미구현의 AttributeError로1 ERROR(의도한 RED)를 확인했다. 이 경합은 실제로 존재하지만 과거 동시 부하 공백의 유일한 원인이라고 단정하지 않는다.

기존 ViewportService의 동일 lock에서 현재 receipt와 최신 JPEG를 함께 읽고, 기존 인증·동일 origin의 GET `/v1/product/viewport/current`로 보낸다. ASCII JSON `X-TwinPulse-Viewport` header와 JPEG body가 한 쌍이다. 과거 JPEG 캐시를 추가하지 않으며 legacy `/viewport`와 번호별 image GET409 계약은 보존한다. 현재 이미지가 없으면204/frame=null/body 없음이다. 응답은 no-store이며 로봇 명령·배포·lease 획득·Build/Run을 실행하지 않는다.

브라우저는 이 한 쌍의 실제 engine session/stage epoch/revision/frame/camera 정보를 사용한다. 이전 metadata 번호로 JPEG를 재요청하지 않는다.204와 identity 교체는 이전 픽셀을 지운다. metadata 조회 자체는 준비·decode 정체 진단을 위해 남으므로 전체 요청이 한 번으로 줄었다거나 FPS가 높아졌다고 주장하지 않는다. header8192자/body180000bytes 상한, JPEG/상태/receipt 형식 검사, fetch와 body 각2초 상한을 둔다. 기존1초 신선도·한 native decode·늦은 bitmap close·7Hz 상한·원 실행ID의 단계 시간·선택 진단3초/무재시도는 유지한다. 잘못된 packet은 실패로 분리하며 구 URL 자동 fallback을 하지 않는다. 구 테스트 adaptor에 새 method가 없는 경우만 기존 경로를 보존한다.

### 회귀와 실제 Isaac 검사

- Python viewport 전체 **24 PASS/8.832초**: 교체 경합·실제 로컬 API의 인증/receipt/JPEG/no-store/204·lease 비변경을 포함한다.
- 최종 Web 전체 **413 PASS/45 files/23.68초**. 기존396개와 신규17개를 포함하며 고유 전체 테스트 수로 합산하지 않는다. 자동 기록은 `artifacts/verification/viewport-pair-20261008-unit-final.json`이다. 타입·빌드 PASS, 최종 JS `index-DGeHEvQU.js`; 기존500kB chunk 및 JSDOM canvas 경고는 별도다.
- 기존 실제 runner의 명시적 fixture 전용 `--browser-metadata-delay`는 text/diagnostics/site fixture/nonzero soak에서만 허용한다. 실제 최신 JPEG를 쓰되 metadata 응답만250ms 늦춘다. CPU/GPU/Wi-Fi 부하 주입이 아니다. route callback 오류는 별도 driver error로 남기고 종료 증거도 기록한다.

`artifacts/verification/viewport-pair-20261008-r1/result.json`은 **FAIL 보존**이다. `route.fetch()`의 APIResponse에 Page Response용 `headerValue()`를 사용한 검사기 TypeError로 worker exit1, browser.json 누락이었다. 실제 제품 오류로 확대하지 않는다. worker 로그와 wrapper 실패는 남았고 owned backend/engine 종료는 확인했으나 **r1 browser 종료는 직접 확인하지 못했다**. 설치된 Playwright 타입의 APIResponse `headers()`로 고치고 route 오류 기록·pending handler 완료 대기·browser close 증거를 보완했다. 제품 신선도/안전 기준을 완화하지 않았다.

최종 `artifacts/verification/viewport-pair-20261008-r2/result.json`은 **PASS**다. host_capture_required=true, browser/host/capture PASS, worker exit0, browser_closed=true, driver/page error0, 고정 provider 소스 불변, owned launcher shutdown succeeded를 확인했다.

- 실제3번 비교는 metadata131→packet133,133→135,135→136이다. 모두 packet JPEG SHA256가 receipt와 일치했고 legacy 이전 번호 GET은409였다.
- 250ms metadata 지연60.364초/47관측에서 current image 누락0·DOM 숨김 전환0·한 canvas·추가 Build/Run0·revision 불변이었다. 지연metadata257건에는 UI와 검사기 요청이 함께 포함된다.
- 해당 soak의 JPEG 완료응답은 **113개**, expired409와 failure는0이다. 표시 최대 frame age695.870ms였다. 전체581 frame 관측은 metadata와 packet receipt의 중복을 포함하므로 고유 렌더 프레임/FPS로 해석하지 않는다.
- browser JS heap은 시작14,867,672/종료6,808,856/최대16,042,140bytes였다. 전체 process/GPU 메모리나 모든 누수 부재의 증거가 아니다.
- HTTP503·held decode·image-expiry의 정확한 실패ID/복구, 실제 PhysX 도착 오차0.039662706m, 다음 채팅 목표·Stop·fold/reload·승인 비재사용·reset·진단 graph/search/export·mobile을 함께 통과했다. renderer 입력은 고정 provider fixture이며 실제 LLM 사진 생성 품질 또는 실물 주행 증거가 아니다.

최종 빌드와 실제r2 bundle은 동일하다. HTML SHA256 `0e9d122a0223dbfaf844564a51195ff78f6693aa01dcbad60c73d70c2e102de9`, manifest `a462cec0f56954f2a2a84552e7e6f1fa1c267e88767c6bfb0d00bcb68a036074`, JS `b179ac9424d7943b82c84dfd87e5d15904cdeeadb145a56ac891daf8f6a3f34d`, CSS `d061d683eed49116b4f5c6085b48dcff90ec830264cfc060f915fe2e97a41cbc`다. 추가된 마지막 순수 API 회귀는 제품 bundle을 변경하지 않았다.

### 정확한 완료선과 잔여

최신 JPEG와 receipt가 서로 다른 프레임인 번호 교체 경합은 새 제품 경로에서 없앴고, 제어된 지연·복구·SIM 흐름을 위 범위로 검증했다. **과거 동시 부하 공백의 원인은 여전히 미확정**이다.250ms 응답 지연 시험을 CPU/GPU/Wi-Fi 전체 부하 재현이나 새30분 인수로 바꾸지 않는다. v342의 기존30분 PASS와551-file package를 새 source 인수로 복사하지 않는다.

남은 구현·인수는 다른 O 경계(외부 편집/정합/remote ACK), 제한된 raw 조회, 동적 장애물·Loop와 전체 process/GPU 자원, P2 실제 LLM 사진 품질, 최신 source 패키지와 F0/F1 현장이다. 전체 D01–D12/whole=false/H5-H6/C3-C6 PARTIAL을 유지한다. 새 package/field 후보는 만들지 않았고 raw/dirty/과거 실패/v1-v2/hash/실물 잠금·정지/scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s 기준은 그대로다. 로봇·SSH·serial·실센서·모터·배포·유료·설치·시스템 변경·commit/push·새 agent0, 예약PAUSED다. 동일 PASS 장시간 반복으로 시간을 채우지 않고 이 v345 묶음을 종료한다.

## 임무 조사 정합과 보정 ACK 연결

### 같은 실행 ID에서 구분하는 단계

기존 AutomaticMissionService의 실제 adapter/worker 경로에 admission, PC에서 관측된 조사·정합 phase, 보정 commit, 검증된 remote ACK, adapter cleanup, 필수 report save span을 연결했다. 기존 Diagnostics 상세와 export에서 조회하며 새로운 관측 서비스나 대시보드는 만들지 않았다.

저장 성공은 로봇 ACK 성공과 다르다. 보정 검증·ledger append 뒤 ACK 대기를 시작하고 기존 safety·소유 binding 검증까지 통과한 accepted callback에서만 성공으로 닫는다. 종료까지 ACK가 없으면 unknown 또는 실패/취소로 남으며 늦은 ACK가 종료 기록을 성공으로 바꾸지 않는다. Stop 중 보정 취소는 cancelled로 남기고 시스템 최초 오류로 세지 않는다. 실제 제어·정지 자격은 기존 로봇 guard가 판정하며 진단 ID나 성공 span은 이동 권한이 아니다.

phase 시간은 같은 PC process-monotonic 기준의 관측 구간이다. 기존 native protocol은 SURVEYING을 보내지만 outbound/return 시점은 보내지 않으므로 그 세부 시간을 만들어내지 않는다. 로컬 worker가 직접 내놓은 경계만 별도로 기록한다. 정상 순방향 전이만 직전 phase를 성공으로 닫고 관측을 건너뛴 phase는 unknown으로 닫는다. 최대7 phase, revision bind16회로 제한하며 센서/고속 입력/pose/scan/robot_t를 복사하지 않는다. map/alignment/correction/goal-room revision은 별도 의미의 SHA256 필드다. 이 기간은 CPU 시간·로봇 계산 시간·단방향 네트워크 지연이 아니며 병렬 commit/ACK/phase 시간을 합산하지 않는다. Diagnostics 화면에도 이 의미를 표시한다.

선택 진단의 child/bind/finish 오류는 기존 diagnostics_degraded/storage_errors에 내용 없이 계수한다. Stop·제어·필수 원본 저장을 기다리거나 실패로 바꾸지 않는다. 필수 report 저장 실패는 기존 fail-closed 정책과 최초 오류·후속 storage 오류 분리를 유지한다. 보고서·native session/protocol 및 v1/v2 hash 대상에 진단 필드를 삽입하지 않았다.

### 회귀와 저장 근거

- 수정 전 합성 native 집중1회는 전체 임무 성공에도 상세에 observed_mission/mission_worker만 있어 단계 누락 **FAIL**을 재현했다. 첫 환경 시도는 src PYTHONPATH 누락, 다음은 sandbox 임시폴더 접근 오류였다. 기존 src 경로와 승인된 로컬 subprocess 실행으로 검사했으며 설치·권한 우회는 하지 않았다.
- 첫 연결 뒤 왕복 substep span을 요구한 검사는 **FAIL**이었다. native가 그 경계를 보내지 않는 것을 확인하고 누락 시간을 추정하는 대신 실제 SURVEYING/ALIGNING_PHOTO 관측으로 검사와 표시 의미를 바로잡았다. 이후 집중1 및 합성 native 전체 **5 PASS/129.755초**는 선행 검사다.
- 관련 임무·보정·report-storage 전체 **18 PASS/79.977초**. admission/heartbeat/stale/scan/battery 실패, 정상 도착/Stop, source/ledger 변경 거절, cleanup 오류, 필수 보고서 실패와 선택 sink 오류 격리를 포함한다.
- 최종 SHA256-only 필터 뒤 진단130+새 경계3+sink 격리1을 실제 실행해 **134 PASS/74.488초**. unknown ACK/late ACK 비부활,1000개 반복 관측의 제한 기록, 잘못된 revision 타입/문자열 제거, sink 오류에도 halt·보고서 저장 유지와 degraded 표시를 확인했다. 이전18과 중복되므로 합산하지 않는다.
- 최종 Web **414 PASS/45 files/27.54초**, 타입/빌드 PASS. 신규1은 실제 제품 Diagnostics 컴포넌트에서 commit과 unknown ACK를 분리하고 조회가 제어를 실행하지 않는 검사다. DOM 회귀이며 새 실제 Isaac 브라우저 인수라고 표시하지 않는다. built JS `index-Bekf-UYM.js`, SHA256 `1a6b2919c9cf3b297cd9ae7759a510e753dc2c9511c58f83ad821494afe60614`; 기존 chunk 크기/JSDOM canvas 경고는 남는다.

단독 `artifacts/mission-trace-20261008-r2/`의 정상·보정 거절·Stop3회는 **PASS/76.514초**다. 실제 PC/합성 native subprocess와 기존 output-reactive ROS fixture를 사용했으며 로봇 접속·provider 호출0/physical_validation=NOT_RUN이다. 각 case의 원본 report/session/robot report/evidence/published, 실행 detail/export와 검증 source·artifact hash를 보존했고 **30 artifact hash 모두 일치**했다.

| 사례 | 실행 상태 | 보정 commit | ACK | cleanup와 report |
|---|---|---|---|---|
| survey | succeeded | succeeded | 검증 후 succeeded | succeeded |
| rejected | failed | PHOTO_LEDGER_HEAD_CHANGED | 시작하지 않음 | succeeded |
| stop | cancelled | cancelled | 시작하지 않음 | succeeded |

정상 실행 ID `7cf0f78a10504d77bf2c2a585256329e`는10 span/38 events, 거절 `e031b788a5214b1c8ddea5d88790c851`은9 span/35 events, Stop `4cd4dca4e19947e78e0bff8a57d69caf`은8 span/33 events다. 정상 PC 관측 조사23.375초·정합0.703초·commit0.016초·ACK0.093초·report0.078초였다. 일부0초는 Windows timer 해상도이며 계산이 무료라는 뜻이 아니다. 마지막 strict metadata 필터는 이 r2 뒤에 순수134 회귀로 검증했다. 유효한 SHA 참조의 의미는 유지하지만 r2 source hash를 최종 hash로 덮거나 전체 native 최종 source 재실행이라고 주장하지 않는다.

### 병렬 입력 만료 실패와 남은 범위

`mission-trace-20261008-r1`의3회 중 정상 survey1회는 **INPUT_DEADLINE_EXPIRED FAIL**, 나머지 거절/Stop은 PASS였다. 당시 Web 및 로컬 임무 회귀가 동시에 실행됐으나 병렬 부하가 원인이라는 것은 아직 가설이다. ALIGN/view17 상태였고 보정 commit은 시작되지 않았다. 입력250ms 등 기존 보호 기준을 늘리지 않았다. 실패 후 자동 이동 재시도도 없다.

그 실패에서는 기존 검사기의 outcome assertion이 export보다 먼저 실행되어 임시폴더 정리 뒤 원본이 남지 않았다. `r1/verification.json`에 unittest 출력 기반 상태·code와 **raw_preserved=false**를 기록했으며 원본을 재구성하지 않았다. 이후 검사기는 결과 assertion 전에 원본 bytes와 hash를 EVIDENCE_ONLY로 반출하고 검사 후에만 해당 case 검증을 PASS로 바꾼다. 단독r2 성공은 r1 실패를 삭제하거나 원인을 해결했다는 증거가 아니다.

이번 완료는 **한 실행 ID의 임무 phase·보정/ACK·cleanup/report 세부 연결과 실패 격리**다. 외부 편집·다른 정합/remote 경계의 전체 O2, 제한된 raw 조회, 동적 장애물·반복 Loop와 전체 process/GPU 자원, 실제 LLM 사진 품질, 최신 패키지와 F0/F1 현장은 남는다. 새 Isaac 실행·장시간/부하 인수·실물/유료/배포/설치/commit/push/새 agent는 하지 않았다. 기존 raw/dirty/과거FAIL/hash/guard/예약PAUSED 및 whole=false/H5-H6/C3-C6 PARTIAL을 유지한다.
