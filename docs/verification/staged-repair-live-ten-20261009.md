# 새 채팅 화면 실제 생성 시험과 출력 반복 진단

2026-10-09 KST · Baseline v1.0.374 · 실제 생성 FAIL · 로그와 화면 검증 PASS

사용자 승인 “그래 새화면에서 총 10회까지 테스트 승인한다”로 기존 침실 사진의 GPT 관측과 Nebius Nemotron 설계·수정을 시험했다. 새 일반 채팅 화면에서 명시 USD1/최대10회 승인을 입력했고 실제 HTTP 응답을 사용했다. 2번째 요청의 출력 소진으로 기존 즉시 중단 정책을 적용해 나머지8회는 사용하지 않았다. 한 번의 자연 생성 결과이며 성공률이나 전체 데모 인수가 아니다.

## 실제 결과

| 단계 | 결과 | 시간 | 출력 토큰 |
| --- | --- | --- | --- |
| GPT 사진 관측 | JSON 및 observer 검사 PASS. 12 entities 중 object8개 | 7.406초 | 988 / 4000 |
| Nemotron 구조 설계 | length, JSON 미완성, PROVIDER_OUTPUT_TRUNCATED | 137.453초 | 20000 / 20000 |
| 자동 수정 및 object batch | NOT_RUN. 출력 소진 후 추가 요청0 | — | — |
| 최종 compile 및 새 장면 저장 | NOT_RUN. 성공 후보 없음 | — | — |
| Isaac Build Run Stop 및 실물 | NOT_RUN | — | — |

활성 생성시간145.031초, 추정비용USD0.01133949, UNKNOWN 예약0, dispatch lock0이다. 실제 청구액을 검증한 값은 아니다. GPT는 gpt-5.4-mini-2026-03-17, Nemotron은 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B이며 원사진 SHA256은 ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8이다. 모델·키를 교체하거나 이전 승인 장부를 빌리지 않았다.

## 직접 확인한 실패 원인

실제 Nemotron 요청에 max_tokens20000, enable_thinking=false, strict json_schema가 적용됐다. 저장 요청 잘림은 false다. 이번 inventory 목록은 관측에서 생성한8개 ID이며 최소3/최대32와 개별 출처 스키마를 사용했다. 사진별 고정 목록이나 방 치수를 주입하지 않았다.

원응답 content34139자 중 끝의32263자는 공백·줄바꿈이고 마지막 비공백까지1876자다. source.basis=visual의 observation_ids 배열을 열고 ID를 넣지 않은 상태에서 공백이 반복됐다. reasoning_content는0자다. 원문 JSON 파싱은 Expecting value, 위치34139/줄6569에서 실패한다. 응답 캡처 잘림은 false이며 공급자 원문의 finish_reason은 length다. 8000 설정 잔존, host 로그 절단, 시간 만료, 추론 텍스트 소진으로 설명되는 이번 실패가 아니다.

반복 전 부분 출력에는 사진 물체를 user 출처로 적고 사용자 원문에 없는 office chair, wardrobe 등의 인용을 사용한 흔적도 있다. 출처 혼동의 진단 근거지만 정상 JSON이 아니므로 수동 완성해 의미검사 결과로 대신하지 않았다. 원응답은 불변이다.

**확정된 현상은 미완성 JSON 뒤 반복 공백과 출력 소진이다.** 모델 자체인지 Nebius 구조화 디코딩과 enum/anyOf 조합의 호환 문제인지는 이 응답만으로 확정하지 않는다. 다음은 범용 구조화 출처 계약·wire 변환과 제약별 호환성을 분리해 검증하는 작업이다. 한도 상향이나 동일 요청8회 반복은 하지 않았다. 실제 수정 회복은 수정 가능한 응답에 도달한 뒤 별도로 인수해야 한다.

## 실행 ID와 로그

실행 ID b0b3ce8b913c4c2eb5e593898b82744d, 채팅 operation ID 57cccb2c-ea90-4ba8-92c2-01b0e186b61a다. 관측 attempt는 bc3d251c8e8c48a48e3ebe3d8a0d67e0, 설계 attempt는 6bf7268a7b3544448031588531bb9fcf다.

- [전체 결과 및 호출 감사](../../outputs/staged-repair-live-20261009-ten/summary.json)
- [무과금 원응답 분석](../../outputs/staged-repair-live-20261009-ten/run-1/live-response-analysis.json)
- [실제 두 호출과 실패 화면](../../outputs/staged-repair-live-20261009-ten/run-1/terminal-attempt-history.png)

run-1/runtime/provider-evidence의 dispatch2/raw2/validation2가 같은 execution/attempt/span으로 결속된다. 요청·응답·검증 SHA 및 장부 usage가 일치한다. 구조 validation은 candidate=null/PROVIDER_OUTPUT_TRUNCATED/모델·한도를 보존했다. compiler는 실행되지 않아 해당 파일이 없다. rejected raw의 최상위 finish_reason은 없지만 보존한 공급자 원문 choices[0].finish_reason과 공개 진단에는 length가 있다. 분석 파일은 원문 값을 사용하며 raw를 덮어쓰지 않는다.

## 화면과 종료 검증

실제 compiled React→일반 승인 API→등록된 secure key→제품 staged gateway를 사용했다. 모델 mock/replay0이다. Tool details의 Recorded attempts2/2, passed/rejected/실패코드/두 attempt ID를 확인했다. page error0, 새로고침 뒤 operation/state 보존, 자동 추가 요청 및 engine command0이다. 시험 소유 backend 종료, 원 설정·키 metadata·보호한 과거 장부 해시 불변을 확인했다.

최초 전체 live harness 요청은 추가 Isaac Build/Run/Stop 승인 범위 때문에 **실행 전 권한 검토에서 거절**됐다. 해당 명령 외부 호출0이며 우회 재실행하지 않았다. 대신 generation-only로 독립 backend와 새 화면만 실행해 Isaac host를 시작하거나 engine을 등록하지 않았다. 화면의 Waiting for Isaac은 시험 범위에 따른 실제 상태이며 엔진 장애 인수 결과가 아니다.

시험 도구 verify_live_generation_screen.py, live-generation-screen.mjs, analyze_live_generation_screen.py를 추가했고 기존 runner에 현재 승인 문구 필수 입력과 generation-only 선택을 넣었다. Python3파일 AST/Node syntax 및 실제 브라우저 승인·종료·전체 호출목록·새로고침 검증 PASS다. 제품 생성 프롬프트/schema/모델 설정/React 제품 코드는 변경0이다. v373 Provider210/통합181/Web437은 이전 회귀이며 이번 새 전체 회귀로 재계수하지 않는다. 문서 패치 첫 시도는 계획서 제목 불일치로 원자적 거절됐고 파일 변경0을 확인한 뒤 정확한 제목으로 적용했다.

## 정확한 잔여

실제 설계·수정 회복/final compile/새 장면 저장은 미완료다. 새 후보의 실제 Isaac3D·SIM Run/Stop, 사진 정밀도 및 실측·실물도 미검증이다. 통과한 관측 checkpoint 재개는 새 명시 승인을 요구한다. 남은8회를 새 생성이나 모델 교체의 자동 승인으로 쓰지 않았다. 전체 PARTIAL/whole=false, 기존 dirty/raw/과거 실패/안전 guard/예약PAUSED를 보존한다.
