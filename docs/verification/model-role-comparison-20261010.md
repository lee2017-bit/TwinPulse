# Nebius와 GPT 6 Luna 모델 역할 비교 결과

2026-10-10 KST · Baseline v1.0.387 · **출력 소진 보호 중단, 계획 70건 중 49건 실행, 전체 데모 PARTIAL**

후속 v388에서 [rollback 빈 진단 제품 결함을 수정하고 원 응답을 재생 검증했다](rollback-revalidation-20261010.md). 아래 표는 수정 전 실제 비교 기록이며 결과·비용·원 실패는 바꾸지 않았다. 수정 후 새 모델의 추가 응답과 추천 조합 전체 인수는 아직 별도다.

이번 조건에서 우선 추천할 후보는 **DeepSeek V4.1 Flash 사진 관측 + Nebius Nemotron Lightning 설계·수정**이다. Qwen 3.8은 사진 관측의 대안이다. 두 역할을 독립 비교한 결과이며, 이 새 조합의 전체 사진→실제 Isaac 렌더→자동 수정→저장 인수는 아직 하지 않았다. 일반 App의 모델 허용 목록이나 저장 라우팅도 변경하지 않았다.

## 실행 범위와 중단 사유

사용자는 현재 Nebius Token Factory에서 사용 가능한 모델을 역할별 동일 조건에서 두 번씩 비교하고, 서로 다른 모델 다섯 개가 연속으로 같은 원인으로 실패하면 중단하도록 승인했다. OpenAI는 GPT 6 Luna만 사용했다. 기존의 출력 소진 즉시 중단 지시도 유지했다.

계정의 실제 모델 목록과 모델별 modality·가격을 인증된 GET으로 확인했다. Nebius 25개 중 생성 가능한 텍스트 모델은 24개, 이미지 입력 모델은 9개였다. Qwen3 Embedding 8B는 생성 모델이 아니므로 제외했고 실패로 세지 않았다. Luna는 계정 모델 목록에 있었고 실제 이미지·설계 호출도 실행했다. 신규 설치·GPU 리소스 생성·로봇 명령은 없다.

- 계획: 이미지 10모델 × 2회 = 20건, 설계 25모델 × 2회 = 50건, 총 70건. Luna는 각 역할에 포함된다.
- 실행: 이미지 20건 모두 완료, 설계 29건. 이미지 계약 15/20 통과, 설계 검사 14/29 통과. 설계 21모델의 두 번째 시험은 미실행이다.
- 마지막 시험은 Ultra 설계 2회차의 `PROVIDER_OUTPUT_TRUNCATED`. 이후 추가 inference는 0이다. 다섯 모델의 연속 동일 실패 조건은 최종 시간순 기록에서 발생하지 않았다.
- 원본 기준시각 12:37:14 KST, 최종 중단 기록 13:13:28 KST. 요청한 조건으로 진행했으며 시간을 채우기 위한 대기는 없다.
- Nebius 130 HTTP, 비용 추정 USD **1.912220660**; OpenAI 12 HTTP, **0.0168195**; 합계 **1.929040160**. 각각 USD10/0.50의 별도 캠페인 한도 내이다. 실제 청구서·잔여 크레딧 확인 값은 아니다. UNKNOWN·pending lock은 최종 0이다.

## 동일 조건과 판정의 의미

사진 원본은 기존 승인 침실 사진 `outputs/ordinary-full-retest-20261010/run-1/1-사진-1.jpg`, SHA256 `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`이다. 문장은 모든 모델에 `Create a digital twin of my bedroom with a bed and desk.`를 사용했다. 각 호출의 출력 상한은 20,000토큰, 네트워크 대기는 최대 300초다.

이미지는 기존 제품 관측 schema와 객체·역할·참조 검사에 실제 응답을 넣었다. **이미지 통과는 사진 정확도나 모든 장애물 검출을 보장하지 않는다.** 원 사진과 관측 목록을 사람이 대조한 정성 검토를 아래에 따로 적었다. 실측 치수는 없으며 새로 만들어 넣지 않았다.

설계에는 관측 모델의 차이가 섞이지 않도록 모든 모델에 동일한 기존 실제 GPT 관측을 재사용했다. 이 과거 응답은 정답이나 이번 새 응답으로 취급하지 않는다. 16개 entity/12개 물체의 같은 입력이며 파일 SHA256은 `940cae91512170d4ecb72cd4602bd3212acfe81b7a16825886ce476aecada1ff`다. 이 단계의 사진 송신과 새로운 GPT 5.4 호출은 0이다.

설계는 단순 JSON 생성이 아니라 **기존 BudgetedPipeline의 구조→객체 batch→전체 compiler→관측 배치 검사→최대 세 번의 자동 수정**까지 실행했다. 시험당 HTTP 최대12, 반복 무진전 두 번, 동일 시간 정책을 사용했다. 통과는 근사 기하와 검사 가능한 관측 위치 관계의 통과이며, 사진 지지 관계·정밀 크기·실제 렌더 품질은 여전히 불확실이다. 품질 수정 요청 두 번으로 Luna 2회차가 수락된 사례도 포함한다.

공통 schema의 동등 정규화와 본문 명시를 사용했다. OpenAI는 공식 구조화 출력 호환 설정 `reasoning_effort=none`을 사용했고 Nebius 비이미지 요청에는 같은 no-thinking flag를 보냈다. API별 호환 필드가 다르므로 wire byte 자체가 같다는 주장은 아니다. 모델별 특별 정답·사진 치수·추가 예제·검사 완화는 넣지 않았다. 두 표본은 한 사진의 현재 파이프라인 호환 시험이지 일반 모델 성능의 통계적 순위가 아니다.

## 이미지 분석 결과

비용은 해당 역할의 실행 건 전체 합계다. 시간은 실행 건 평균이며 모델별 서버 지연도 포함한다.

| 모델 | 계약 통과/실행 | 평균 초 | 비용 USD | 원 사진 대조와 실패 이유 |
| --- | --- | --- | --- | --- |
| GPT 6 Luna | 2/2 | 11.6 | 0.0015804 | 10/11물체. 침대·책상·옷장·케이블은 있으나 모니터·문·바닥 물건 등을 빠뜨림. 1회차 별도 옷걸이 누락 |
| DeepSeek V4.1 Flash | 2/2 | 10.9 | 0.0093456 | 각 20물체. 침대·책상·옷장·옷걸이·의자·팬·모니터·문·가방·바구니·케이블·침구 돌출 등을 자세히 분리. 일부 centre/left 구역과 장치 범주는 불확실 |
| Qwen 3.8 27B | 2/2 | 15.9 | 0.0452505 | 각 17물체. 주요 가구와 문·바구니·케이블·어댑터를 안정적으로 분리. 옷장 속 옷·침구 돌출 등 세부 누락은 남음 |
| MiniMax M3 | 1/2 | 7.8 | 0.0052500 | 첫 관측은 상세하지만 두 번째 응답의 dimension target이 실제 entity를 참조하지 않아 거절 |
| Gemma 3 27B | 2/2 | 36.8 | 0.0012498 | 형식 통과와 별개로 두 응답 모두 책상을 middle_right로 판단. 사진의 왼쪽 책상·모니터와 맞지 않음 |
| Kimi K2.6 | 0/2 | 33.5 | 0.0874898 | 두 번 모두 JSON 문법 불가. 첫 기록은 일반 validation code, 이후 엄격 parser는 JSON_INVALID로 분류 |
| Kimi K2.7 Code | 2/2 | 9.6 | 0.0187658 | 첫 관측 14물체, 주요 가구 방향 확인. monitor inside desk 등 지지와 포함 관계 해석의 불확실성 있음 |
| Kimi K3 | 2/2 | 82.2 | 0.1736790 | 세부 목록은 풍부하나 비싸고 첫 응답 127.8초. 정밀 위치·지지 검증의 증거는 아님 |
| MiniCPM V4.5 | 0/2 | 19.1 | 0.007687744 | OBSERVER_ROLE_CATEGORY_MISMATCH 반복. 영상 이해 전반의 능력이 없다는 뜻이 아니라 현재 계약 불일치 |
| GLM 5.3 Flash | 2/2 | 61.0 | 0.0102590 | 세부 장애물 포함. 첫 관측의 rear_left 추가 wardrobe 등 과잉 분류 가능성; 느린 응답 |

이미지 미지원 모델은 해당 사진 시험을 실행하지 않았다. 물체 수만으로 정확도를 채점하거나 지지 관계를 수락하지 않는다. 위 사진별 검토는 평가 기록에만 있으며 제품 하드코딩·통과 정답으로 들어가지 않는다.

## 설계와 자동 수정 결과

`1/1`과 `0/1`은 첫 시험만 실행한 결과이다. 그 모델의 두 번째 시험은 중단 때문에 미실행이며 `2/2`와 동일한 안정성 근거가 아니다. ★는 아래 우리 rollback 진단 결함의 영향을 받은 실패다.

| 모델 ID | 통과/실행 | 평균 초 | 비용 USD | 실패 또는 범위 |
| --- | --- | --- | --- | --- |
| nvidia/Nemotron-3_5-Lightning | 2/2 | 11.9 | 0.00373908 | 두 번 모두 초기 구조·batch·검사 통과, 각각 HTTP3 |
| nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 0/2 | 22.4 | 0.01177956 | 관측 품질/기하 수정 한도 소진 |
| nvidia/Nemotron-3-Ultra-550b-a55b | 1/2 | 38.2 | 0.118962 | 첫 시험 수정 후 통과, 두 번째 구조 출력 소진으로 전체 중단 |
| nvidia/nemotron-3-super-120b-a12b | 0/1 | 18.3 | 0.0202467 | 품질 수정 정체 |
| gpt-6-luna | 1/2 | 20.0 | 0.0152391 | 첫 시험 케이블·침대 관계 수정 정체, 두 번째 수정 요청2 후 통과 |
| MiniMaxAI/MiniMax-M3 | 0/1 | 15.1 | 0.0172992 | 품질 수정 정체 |
| NousResearch/Hermes-4-405B | 1/1 | 64.9 | 0.0272150 | 2회차 미실행 |
| Qwen/Qwen3-235B-A22B-Instruct-2507 | 1/1 | 28.2 | 0.0056934 | 2회차 미실행 |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | 1/1 | 57.2 | 0.0027778 | 2회차 미실행 |
| Qwen/Qwen3.5-397B-A17B | 1/1 | 22.8 | 0.0218238 | 2회차 미실행 |
| Qwen/Qwen3.8-27B | 1/1 | 9.0 | 0.01704615 | 2회차 미실행 |
| deepseek-ai/DeepSeek-V4-Flash-0731 | 1/1 | 38.9 | 0.00394016 | 2회차 미실행 |
| deepseek-ai/DeepSeek-V4-Pro | 1/1 | 13.9 | 0.0495740 | 2회차 미실행 |
| deepseek-ai/DeepSeek-V4-Pro-0813 | 0/1 | 42.3 | 0.10544424 | ★ packing 실패 뒤 빈 진단 rollback |
| deepseek-ai/DeepSeek-V4.1-Flash | 0/1 | 32.3 | 0.0398778 | ★ packing 실패 뒤 빈 진단 rollback |
| google/gemma-3-27b-it | 0/1 | 75.8 | 0.0103172 | 수정 한도 소진 |
| moonshotai/Kimi-K2.6 | 0/1 | 189.6 | 0.2999990 | 수정 한도 소진 |
| moonshotai/Kimi-K2.7-Code | 1/1 | 10.6 | 0.0277756 | 2회차 미실행 |
| moonshotai/Kimi-K3 | 0/1 | 83.5 | 0.3511380 | ★ packing 실패 뒤 빈 진단 rollback |
| openai/gpt-oss-120b | 1/1 | 15.8 | 0.00556095 | Nebius에서 실행. 2회차 미실행 |
| openbmb/MiniCPM-V-4_5 | 0/1 | 19.6 | 0.061761676 | 수정 요청 input12001 + output20000 > context32000, HTTP400 |
| zai-org/GLM-5.1 | 0/1 | 73.2 | 0.1143696 | 품질 수정 정체 |
| zai-org/GLM-5.2 | 1/1 | 9.5 | 0.0385904 | 2회차 미실행 |
| zai-org/GLM-5.3 | 0/1 | 175.3 | 0.1809478 | ★ packing 실패 뒤 빈 진단 rollback |
| zai-org/GLM-5.3-Flash | 0/1 | 138.5 | 0.0173643 | ★ packing 실패 뒤 빈 진단 rollback |

## 실패 원인과 재검사 조건

### Ultra 출력 소진

실행 ID `ba69221dd5f341dbbb3d814c5c2bada2`의 요청 상한과 사용량은 실제 20,000이다. 50.875초 후 `finish_reason=length`, prompt6805/completion20000, 서버 보고 reasoning_tokens0이다. 응답 content20,285자 중 끝 공백19,869자, trim416자의 JSON은 미완성이다. source 관측12물체가 있는데 응답은 inventory에 hypothesis bed 하나를 만들다가 끊겼다.

따라서 상한 설정 미적용이나 진짜 20,000토큰짜리 방 설계가 필요한 상황은 아니다. **구조화 생성의 공백 퇴행**이 확인 사실이다. Ultra 자체·서빙 decoder·이 schema의 상호작용 중 어느 구성요소가 책임인지는 자유 JSON/완화 schema 대조를 아직 하지 않아 확정할 수 없다. 출력 상한만 다시 올리거나 공백을 잘라 PASS로 만드는 조치는 하지 않았다. 다음 유료 대조·미실행 재개는 새로운 명시 실행 지시 후 진행한다.

### 우리 rollback 진단 결함

별표 다섯 모델의 원 `PHOTO_LAYOUT_REGION_FULL`은 대상·packing·repairable=true를 가진 typed 진단이다. checkpoint의 working_branch에도 이 오류가 남아 있다. 그러나 이전에 기하만 통과한 후보의 `best_diagnosis.issues=[]`로 rollback하면 `budgeted_pipeline.py`가 그 빈 진단을 가지고 `UNMAPPED_COMPILER_ERROR`를 던진다. 원 packing 실패와 복원한 후보의 검증·품질 상태를 분리하지 못하는 제품 문제다. 이 다섯 모델의 시험 실패를 순수 모델 능력 실패로 판정하면 안 된다.

대상은 `BudgetedPipeline`의 compiler 예외→tracker regression→best rollback→최종 판단 경로다. 복원 후보를 실제로 재검증하고, 실패 working branch의 typed 진단은 별도로 보존하며, best가 품질 미완성이라면 해당 quality 단계로 돌아가거나 명확한 정체 상태로 끝내야 한다. 빈 진단을 보완하려고 현재 실패를 임의로 주입하거나 best를 최종 성공으로 바꾸면 안 된다. 이 비교 중 제품 코드는 고치지 않았고, 다음 우선 수정 및 원 로그 replay 회귀 대상으로 남겼다. 중간 성공·다른 원인 실패가 있어 연속 다섯 실패 조건은 아니었다.

### 계약과 모델 수정안의 실패

MiniMax 이미지 2회차는 잘못된 dimension entity 참조, MiniCPM 이미지는 역할·범주 모순, Kimi K2.6 이미지는 실제 JSON 문법 오류다. MiniCPM 설계의 400은 32k context와 20k 출력 예약이 합쳐진 입력 길이 문제로, 생성 품질 오류와 구분한다. Luna 첫 품질 수정은 케이블을 책상 지지 물체로 바꾸는 등 원 관측의 배치 문제를 해결하지 못했고, 두 번째 독립 시험은 수락까지 도달했다. Nano·Super·GLM5.1 등의 실패도 원 품질/기하·patch 로그를 함께 보아야 한다.

## 추천 조합과 해커톤 조건

| 목적 | 사진 관측 | 설계와 수정 | 판단 |
| --- | --- | --- | --- |
| 이번 증거의 우선 후보, Nebius 활용 | DeepSeek V4.1 Flash | Nemotron 3.5 Lightning | 관측2/2와 풍부한 장애물 목록, 설계2/2·평균11.9초·회당 약 USD0.00187. 조합 전체 인수는 다음 작업 |
| 이미지 대안 | Qwen 3.8 27B | Nemotron 3.5 Lightning | 관측2/2·가구/장치 분리가 비교적 안정적, 사진 회당 약 USD0.02263으로 더 비쌈 |
| OpenAI 비용 최소화가 필요할 때 | GPT 6 Luna | Nemotron 3.5 Lightning | Luna 이미지 회당 약 USD0.00079이나 장애물 누락을 보완할 별도 품질 확인 필요 |
| 규정과 관계없는 현재 우선 후보 | DeepSeek V4.1 Flash, Qwen 대안 | Nemotron 3.5 Lightning | 제한을 없애도 Luna 설계1/2보다 현 표본이 유리. 제한 때문만의 선택이 아님 |

Luna는 실제 API/image 호출을 확인했고 공식 문서에도 image input·structured output이 있다. 짧은 입력 Standard 단가는 입력 USD0.10/출력 USD0.50 per 1M이다. 이번에는 기존 등록 OpenAI 키와 Luna만 실제로 사용했다. [OpenAI 공식 Luna 문서](https://developers.openai.com/api/docs/models/gpt-6-luna).

[현재 공식 해커톤 규정](https://nebiusglobalaihackathon.devpost.com/rules)은 Nebius inference/compute를 실제 제품 runtime에서 쓰고 NVIDIA 오픈 모델을 포함할 것을 요구한다. **Apps and Agents의 Nemotron 역할을 Lightning이 실제 제품 설계·수정에서 수행하도록 연결하는 방향**이 이번 후보와 맞는다. 규정에 OpenAI 혼합을 명시적으로 금지한 조항은 확인하지 못했으므로 Luna 관측+Nebius Nemotron 설계도 가능한 해석이지만, 참가 적합성의 확정 보장은 아니다. 벤치마크 호출이나 더미 NVIDIA 호출만으로 제품 runtime 요건을 충족했다고 주장하지 않는다.

Lightning은 NVIDIA가 가중치·데이터·학습 recipe를 OpenMDW-1.1로 공개한 오픈 모델이다. [NVIDIA 공식 Lightning 문서](https://docs.nvidia.com/nemotron/nightly/nemotron/lightning35/README.html).

Physical AI 경로는 별도로 Nebius Serverless Jobs를 시뮬레이션·평가·센서 처리 등에 사용해야 한다. 현재 로컬 Isaac+Token Factory 비교만으로 그 조건이 충족된 것은 아니다. Apps and Agents에서는 Jobs/Endpoints 활용이 권장이다. 영어 제출물·공개 코드·설치/시험 접근 및 트랙 데모 요건도 별도로 충족해야 한다. 새 유료 compute를 이번에 생성하지 않았다.

## 로그 감사와 보존

주 근거는 `outputs/model-role-comparison-20261010/{inventory,scope,summary-final,audit}.json`, 공급자별 별도 ledger, `cases/<case_id>/{start,result}.json`, 원 redacted response·dispatch·validation·generation-store/checkpoint/history다. 모델마다 execution ID, HTTP마다 attempt ID, 실제 usage·응답 SHA·schema stage·실패가 연결된다. 키·인증 헤더는 저장하지 않는다.

독립 read-only 감사는 실제 HTTP142개에 대해 result↔raw↔dispatch↔validation↔ledger 연결, 저장 응답 SHA·20k 상한·모델 ID·건별 비용 합계를 검사해 오류0이다. HTTP131개는 execution ID 직접 결속, 초기 Luna/Nano 설계 HTTP11개는 당시 누락을 보존하고 case↔attempt↔장부 join으로 확인했다. 이 누락은 비교 도구를 수정해 후속 요청에는 직접 결속했다. 과거 raw를 소급 편집하지 않았다.

초기 비교 도구가 Nano 전용 constructor 정책을 다른 모델에 넘겨 여섯 항목을 **HTTP0으로** 막았다. 첫 `summary.json`의 잘못된 stop 기록을 보존하고, 도구만 보완한 뒤 실제 호출된 Luna/Nano/관측 응답은 재호출하지 않았다. 미호출 항목만 `-hostfix`에 최초 실제 실행해 최종 `summary-final.json`으로 구분했다. parser 코드 명칭·partial finish-reason 감사도 보완했지만 입력·schema·정답·제품 guard는 바꾸지 않았다.

비교 도구 회귀7 PASS, Python 구문 PASS. 이 회귀 수를 실제 모델 성공률에 더하지 않는다. 사용자 provider/key registry/stage routing 설정 3개와 원 사진/과거 관측의 SHA는 불변이다. 과거 생성 실패·별도 예산·이번 최초 실패는 그대로 남는다.

## 정확한 잔여

1. 제품 rollback 진단 결함을 원 응답 replay 및 실패 반례 회귀로 수정하고 같은 입력의 실제 회복을 별도 검증한다.
2. Ultra 공백 퇴행은 명시 승인된 작은 대조 시험으로 model/decoder/schema 원인을 분리한다. 자동 상한 증대·자동 재시작은 하지 않는다.
3. 중단된 설계21건의 2회차는 미실행이다. 이번에 모두 두 번 완료했다는 주장은 불가하다.
4. 추천 모델의 계정·modality·가격·cap을 기존 일반 App 라우팅 허용 경로에 연결하고, 새 관측(17~20물체)을 사용하는 **실제 조합 전체 생성→current Isaac 렌더 비교→자동 수정→저장/SIM**을 인수한다. 역할별 PASS로 이 과정을 대체하지 않는다.
5. 실제 사진 지지·정밀 형상/크기, 도메인/편집/패키지, 트랙 규정, 로봇 정합·자율·Loop·안전 인수는 기존대로 남는다. 실물 명령0, 이번 actual Isaac0, 전체 `whole_demo_pass=false`다.
