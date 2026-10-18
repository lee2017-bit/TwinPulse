# TwinPulse Physical AI 제출을 위한 모델 고정과 단계별 작업계획

작성일은 2026-10-11이며 실행 대상은 GPT 6.1 Sol이다. 기준 저장소는 `C:\Users\jaewo\Documents\TwinPulse`이다. 이 계획은 사용자의 기존 12단계 데모를 유지하면서, **모델 선택 → 로컬 오류 수정 → 실제 모델과 Isaac 전체 실행 → 제한된 클라우드 작업 → 실물 → 영상과 공개 제출** 순서로 완성하기 위한 것이다. 모델을 더 비교하는 연구를 무기한 이어가는 계획이 아니다.

사진 분석은 **DeepSeek V4.1 Flash / Nebius**, 장면 설계와 모델 기반 오류 수정은 **Nemotron 3 Super 120B / Nebius**로 결정한다. 다만 선택의 확정은 설정 적용, 해당 조합의 전체 동작, 실물 인수의 완료를 뜻하지 않는다. 현재 전체 데모 상태는 계속 **PARTIAL**이다.

이 문서를 작성한 턴의 범위는 계획과 결정 기록이다. 제품 설정 변경, 신규 LLM 호출, 클라우드 생성, 로봇 접속, 라이선스 적용, 공개 업로드 및 제출은 실행하지 않았다. 아래 단계의 실행은 이후 사용자가 승인한 범위와 유효한 비용·데이터·기한 조건을 따른다.

## 2026-10-11 최신 방향 보완

Baseline v1.0.432의 [점진적 Twin 에이전트 상세 계획](TWINPULSE_PROGRESSIVE_TWIN_AGENT_SOL_PLAN_2026-10-11.md)을 P1·P2·P4의 생성 판정·수정·피드백 연결에 우선 적용한다. 초안 사용 가능, 특정 SIM 작업 검증, 실물 준비, 시각 품질을 분리하고 유효 장면과 미해결 목록을 함께 보존한다. 다음 구현은 **G0 판정/회귀 → G1 부분 초안 → G2 의존 관계 패치/Undo → G3 일반 채팅 → G4 저장 센서 → G5 실제 Isaac → 새 승인 G6 실제 모델 → G7 현장**이다. 모든 소품의 층별 지지를 먼저 완성해야 한다는 우선순위는 대체한다. 안전·실물 승인·모델 선택·외부 비용·Cloud/공개/제출의 기존 조건은 유지한다. 현재는 계획 작성만 완료했으며, 아래 v431의 원 결과·평가기준·FAIL을 소급 변경하지 않는다. 새 기준 인수는 별도 criteria version과 새 시험 근거로 기록한다.

## 2026-10-11 구현과 시험 현황 v431

새 승인3건은 모두 실제 종료했다. 창고 텍스트와 거실 사진은 실제 생성/Isaac 현재화면/원 명명목표 이동/별도movingStop·stable/reset·reload/닫힌재열기까지 **기능2/3PASS**, 식당은3geometry repair후REPAIR_STALLED다. 거실 critic uncertain·보조kindrecall3/7로 사진 정밀도/독립품질 또는P2LOCAL_FULL_PASS를 주장하지 않는다. [10이미지·수치 단일 보고서](../../outputs/physical-ai-p2-20261011-v431/final-evidence/report.html), [원인·감사·잔여](../verification/warehouse-semantic-support-20261011.md#수정본-3건-종료와-실제-기능-재인수--v431)를 현재 근거로 사용한다.17HTTP 완전감사/새추정N.1272345/새held0·과거포함7.15488417/누적10(invoice아님)/과거UNKNOWN식당USD1hold유지다. catalog 유효기간만 같은 원기한까지 metadataGET2로 다시 확인했고 남은사진2만 이어갔다. product/harness/Web/build/원사진·prompt·goal/evaluator불변·owner정상종료/nativePAUSED/새3cap소진·OpenAI/Cloud/로봇0. 아래430 RUNNING은 종료 전 이력이다.

다음 구현·인수 우선순위는 다음과 같다.

1. 식당 동일원후보의층별지지(매트/접시 같은 nested 관계)와 flat sibling 충돌 모델, 치수·부모 dependency 수정범위를0HTTP로 분리 진단한다.512노드 한도를16,384노드/5초로만확대한진단도witness를못찾았으므로한도증가를해결로채택하거나전역불가능으로단정하지않는다. 실제geometry witness와범용합성회귀를확보하고특정사진/규격/물체삭제/충돌제외로통과시키지않는다.
2. 범용수정후새동결·새횟수/기한으로원입력실제재시험한다. 과거FAIL을승격하지않고원목표·movingStop·closedreopen까지검증한다.이번3cap는소진했으므로잔액만근거로추가LLM생성을시작하지않는다.
3. 독립 사진품질/세션반복·ordinary실제LLM편집preview/apply/cancel·재계획·SIM loop와배터리/장애물/오류주입을통합 인수한다. 기능PASS와사진충실도/실측/현장인수를분리한다.
4. P2LOCAL_FULL_PASS후에만boundedCloud·현장로봇/안전초기화·영상·외부권리/개인정보·공개재현·PhysicalAI 제출요건을승인/검증한다.현재전체PARTIAL/wholefalse다.

사용자가 수정본 새3회·Nebius 누적10·승인후2시간 제안을 승인했다. 같은 공개사진2/파생render/창고text와Flash/Super·40k/300s/900s/12HTTP·3repair를 유지한 새source430 manifest56022b1c…0846d로실제착수했다. carry7.02764967에과거미정산·held를모두포함하고보수적22:59KST를지킨다. owner19844/session33583·현재RUNNING이므로 제품source/Web/build/입력·평가기준을변경하지않는다. 결과는소유runner정상종료후기존reporter원감사·실제프레임단일보고서로확인한다. 아직P2LOCAL_FULL_PASS가아니며Cloud/실물/전체완료를허용하지않는다. 아래429승인대기는이번승인전이력이다.

최신 승인3건은 모두 실제 실행을 마쳤다. 전체 경로0/3PASS, 생성1/3이며 원 source427/428의 FAIL/UNKNOWN을 유지한다. source429는 지지면 형제 되돌리기/재배치, 정확히 맞는 격자의 반올림과 목표 종류/부모 keepout을 범용 제품 경로로 수정했다. 동일 저장 후보의 컴파일 회복과 실제 Isaac 정적 Build/표시/저장·재열기2건, 마지막 회귀810+359는 통과했지만 새 모델 전체 인수나 수정 후 이동/Stop 통과로 세지 않는다. 원 목표는Go to pallet이며 box_on_pallet을 후보로 오인한 결함을 교정했다. [9이미지와 수치 단일 보고서](../../outputs/physical-ai-p2-20261011-v429/final-evidence/report.html), [원인·감사·다음 순서](../verification/warehouse-semantic-support-20261011.md#실제-3건-종료와-범용-host-수정--v429)를 기준으로 한다. 신규 완전감사 추정N0.0605661/식당UNKNOWN1hold·누적 보호노출7.02764967/8, invoice미검증이다. 최대3생성은 소진했으며 추가 유료 시험은 새 횟수·기한 확인 뒤 새 cohort로 진행한다. 다음은 수정본 새 실제 생성→현재렌더/critic→올바른 목표 이동→이동 중Stop/안정 상태→reset/reload/닫힌 재열기, 이후C반복/ordinary LLM편집/loop·독립품질이다. P2 LOCAL_FULL_PASS 전Cloud에 진입하지 않는다. nativePAUSED·전체PARTIAL/wholefalse·OpenAI/Cloud/로봇0를 유지한다. 아래 v426–v428 준비/실행중 기록은 당시 이력이다.

source427 두actual의수정전원감사를보존했다. warehouse 생성/첫preview actual이동PASS지만명명선택box 접근FAIL; dining8stop/REPAIR_STALLED와repair request256KiB로그잘림으로strictUNKNOWN/fullhold1. structured redacted2MiB byte-bound226PASS로수정하며원wire/토큰/회계guard·원실패보존. 같은최신3승인중미착수거실1만source428·carry6.97317207/누적8·원21:04KST로진행한다. [근거/정확한잔여](../verification/warehouse-semantic-support-20261011.md#요청-로그-잘림과-미착수-1건--v428). 다른선택/사진hardcode/hold해제로통과시키지않으며아래준비상태는당시이력이다.

추가 사용 승인으로 같은 공개사진2·파생렌더·창고text, 같은 Flash/Super의 최대3새생성을 source427로 동결했다. 누적Nebius8에 과거보호노출5.96708357/UNKNOWN1.30을 전부 포함하고 trial1·원21:04KST 기한을 유지한다. 새 diagnostic phase/terminal 기록은 미래 디버깅용이며 금융정산자료나 hold해제권한이 아니다(관련87PASS). 실제결과는 종료후원감사로별도확인한다. 아래426차단은 추가승인 전 이력이며, 이승인이 Cloud/OpenAI/실물/P2전체완료를허용하지않는다.

현재는 source425도 정상 종료됐다. 첫 warehouse catalog 격리 충돌과 두 번째 dining의 시험 cap.30<제품 최소예약.5916864는 모두 LLM 전 host 준비 실패다. 새 inference0, 원 UNKNOWN/fullhold1.30 보존, carry포함 Nebius 보호노출5.96708357/누적6(실제 invoice 아님), livingNOT_RUN이다. 같은 App 예약 계산을 campaign 시작 전에 적용해 금융예약·child·UI 전에 거절하도록 수정했고 관련83회귀가 통과했다. 합성 빈팔레트/rack/적재팔레트3종의 actual semantic→savedApp→Isaac Build/지지·현재표시/저장·재열기·캡처는 PASS_STATIC_SUPPORT_ONLY다. [4이미지 단일 보고서](../../outputs/warehouse-semantics-20261011-v426/report.html), [실패/원감사/정확한 잔여](../verification/warehouse-semantic-support-20261011.md#비용-사전-점검-수정과-실제-isaac-정적-검증--v426)를 기준으로 한다. 정적 fixture 통과는 actual Flash/Super 생성·수정 회복이나 P2 LOCAL_FULL_PASS가 아니다.

다음은 원 미정산/전송전 terminal audit evidence 경계 확인 → 유효 비용·횟수·기한 아래 새 cohort의 실제 영향 재인수 → C 반복/ordinary LLM 편집/loop·독립품질 순서다. Cloud·현장·영상·공개·제출은 의존성 뒤에 둔다. native PAUSED/wholefalse를 유지하며 아래 source425 실행중 설명은 종료 전 이력이다.

새3슬롯의 첫 warehouse는 LLM전 catalog/oldroute 충돌로 종료했다. 원UNKNOWN과 USD1fullhold를 보존하고 manifest 준비 경계만38회귀로 수정했다. 동일승인의 미착수사진2만 source425에서 실행하며 carryN5.66708357/원총6·각trialUSD.30·원21:04KST로 제한한다. 원창고job 재호출과 hold제거는 하지 않는다. 결과는 종료·원감사 뒤 [검증 기록](../verification/warehouse-semantic-support-20261011.md)에 반영한다. 아직 P2 LOCAL_FULL_PASS가 아니며 warehouse actual/C반복·LLMedit/loop·품질이 남는다.

사용자가 Apache-2.0과 출처 기록 정책을 확정하여 P6의 **라이선스 선택/자체 코드 적용·고지/패키지 메타데이터**를 먼저 반영했다. [정책](../LICENSING.md), [적용 검증](../verification/licensing-attribution-20261011.md), [v423 잔여 점검](../verification/licensing-followup-20261011.md)을 따른다. 기존 builder에 오프라인 의존성/콘텐츠 감사가 연결됐지만 변환 자산별 권리·개인 경로·선택한 공개 자료별 검토는 남아 있다. 외부 권리·개인정보/공개 재현·영상·저장소 공개/제출은 별도이며 P6 전체 완료가 아니다. 아래 추천/보류 문구는 선택 이전 이력이다.

P0 모델 설정 적용/복원과 P1의 위치 피드백·개별 개수 보존 회귀는 실행했다. P2 승인8개 실제 생성은 종료했지만 **전체 인수 PARTIAL**이다. [사진11개와 수치 단일 보고서](../../outputs/physical-ai-p2-20261011-v421/final-evidence/report.html), [원 실패와 수정 기록](../verification/physical-ai-model-routing-20261011.md#p2-8생성-종료와-파생-관측-용량--v421)을 기준으로 후속 작업한다. 총27HTTP/새추정USD.1430361·과거held포함N4.66708357/6. 8개 cap는 모두 사용했으므로 잔액만 보고 추가 호출하지 않는다.

GPU 초기빈frame/비동기파일 완료 경계는 수정 후 실제 사진/office 경로에서 영향 범위를 재인수했다. source420 사진2건의 object+metadata 혼합cap는 후속 오프라인 수정·stored replay만 통과했으며 실제postfix시험은 남는다. 창고의 범용 typed lowering·지지 geometry·저장/편집·현재 목표 경로 연결은 [v424 오프라인 회귀](../verification/warehouse-semantic-support-20261011.md)에서 통과했다. 빈 팔레트와 적재 팔레트를 구분하고 shelf/화물/기둥 clearance를 검사하며, 기존 factory의 yaw=0 한계를 명시한다. 모양만 unknown 박스로 바꾸거나 상자를 바닥에 내려 오류를 숨기지 않는다. **다음은 새 승인된 공개 식당·거실 사진과 창고 텍스트 최대3생성으로 실제 영향 범위 인수**다. 누적N6·승인후2시간·각12HTTP/3repair를 지키며 원8cap를 초기화하지 않는다. 모델의 parent 선택·수정 진전과 actual Isaac 결과는 별도 확인 전 NOT_RUN이다.

이후 새 유효 범위 내 실패 영향 재인수와 C 새세션 반복 → 일반 채팅의 실제 LLM scene edit→preview/apply/cancel/재계획(현재 regex 경로·별도 proposal 서비스만으로 완료 아님) → SIM 연속왕복/loop와 이상주입/독립품질 순서다. P2 LOCAL_FULL_PASS 전 유료 Cloud 진입하지 않는다. 로봇·영상·외부 권리 점검/공개/제출은 미완료다. 라이선스 선택 보류는 v422에서 해소했다. 아래 작성 당시 PLAN_ONLY/NOT_RUN 내용은 당시 기준 설명이지 이번 실행을 지우는 상태가 아니다.

## 1 사용자 의견과 검토 결과

사용자의 이번 의견을 실행 기준으로 보존한다.

> 내 의견은 좀 쉬운거부터 순서대로 해보자는거야.
> 먼저 최종 모델 조합은 사진분석은 DeepSeek V4.1 Flash — Nebius, 장면설계와 오류수정은 Nemotron 3 Super 120B — Nebius 로 하자.
> 이유는 벤치마킹 근거를 토대로 이게 최적이다 라고 설득할만한 내용으로 작성해주면 될거같네. 그 이후 이 조합으로 고정해서 이후 테스트도 진행하자. 그럼 1번 해결 된거지?
> 2번은 AI Cloud Credit을 쓰는거같은데 시간당 돈이 나가는 구조니까 오류나 버그 생기면 그대로 돈 버리는거니까 여기 가기전에 미리 오류랑 버그는 좀 잡고 한바퀴는 정상적으로 도는걸 본다음에 진입하자.
> 그럼 1번 정상적으로 되면 3번도 되는거지?
> 4번은 그럼 3번 기준으로 정상적으로 된다음에 로봇 연결도 해보면 되는거고.
> 5번은 4번내용을 녹화해서 편집하면 될거같고.
> 6번은 보통 MiT나 BSD, Apache 계열인거같은데 나는 어떤 라이센스 해야 좋을지 추천해주면 내가 고를게.
> 7번은 그럼 나머지 내용이 다 완성이됐을때 끝나는거니까 그냥 전체 링크로 제출하는과정이라 이거 자체에는 큰 시간소요 없을거같네.

이전 대화의 번호와 이 계획의 단계는 다음처럼 연결된다.

| 기존 번호 | 검토 결론 | 실제 완료 조건 | 실행 단계 |
|---|---|---|---|
| 1 모델과 NVIDIA 활용 | 모델 선택은 확정. 제품 적용과 작동 증거는 남음 | 일반 App에서 Flash 관측과 Super 설계·수정이 실제 실행되고 결과가 장면에 사용됨 | P0, P2 |
| 2 Serverless Jobs | 로컬 검증 뒤 진입하는 데 동의 | 규정 해석 확인, 로컬 동일 작업 성공, 비용 승인, 실제 Job 결과 반영과 자원 종료 확인 | P3 |
| 3 최신 App 전체 경로 | 1번만으로 자동 완료되지 않음. 같은 통합시험에서 함께 검증하면 됨 | 실제 입력부터 생성·수정·3D·목표 시연·Stop·저장·재열기까지 연결 | P1, P2 |
| 4 실물 | 로컬 통과 뒤 진행하는 데 동의 | 현장 승인, 현재 부팅·배포본 검증, 스캔 정합·목표 주행·정지·복귀의 실측 | P4 |
| 5 영상 | 실물 시험과 동시에 촬영하면 재시험 낭비 감소 | 실제 동작 영상, 실행 근거와 일치하는 설명, 분량·영문 요건 점검 | P4, P5 |
| 6 라이선스 | 사용자 Apache-2.0 선택·자체 코드/고지 적용 v422 | 외부 권리·개인정보·공개 재현 점검은 별도 잔여 | 라이선스 먼저 적용, P6 전체는 미완료 |
| 7 제출 | 자료가 준비되면 입력은 짧지만 링크 모음만으로 끝나지는 않음 | 설명·실행법·피드백·트랙·공개 접근성·실제 제출 확인 | P7 |

**권장 순서:** P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7. 라이선스 재료 조사, 공개 문서 초안, 촬영 구도는 앞에서 준비한다. P3의 외부 답변을 기다리는 동안 비용 없는 P4 준비와 문서 작업은 계속할 수 있다. P4의 기술적 선행 조건은 P2이며, 클라우드가 로봇의 실시간 안전 제어에 끼어들어야 하는 것은 아니다.

## 2 모델 결정과 주장할 수 있는 근거

### 2.1 고정할 역할

| 역할 | 공급자와 정확한 API 모델 ID | 적용 범위 |
|---|---|---|
| 사진 관측 | Nebius `deepseek-ai/DeepSeek-V4.1-Flash` | 사진의 물체·공간 관계·불확실성 추출 |
| 장면 설계 | Nebius `nvidia/nemotron-3-super-120b-a12b` | 텍스트 또는 관측 결과를 구조화된 장면 계획으로 변환 |
| 모델 기반 수정 | 동일 Super | 검증 오류를 받아 장면 또는 영향받은 부분을 수정 |
| 추가 시각 검토를 실행하는 경우 | 동일 Flash | 사진과 현재 Isaac 렌더 비교. 별도 승인된 호출 예산 안에서만 실행 |
| 로컬 검사와 안전 제어 | 기존 결정론적 코드 | 스키마·참조·충돌·정지·비용 보호. 모델로 대체하지 않음 |

텍스트만 입력하면 사진 관측을 호출하지 않는다. 사진 첨부가 SIM의 필수 조건이 되어서는 안 된다. 별도 critic 모델이나 독립적인 repair 모델을 구현했다고 표시하지 않는다. 현재 역할별 설정의 공유 관계를 UI와 로그에 그대로 나타낸다.

`DeepSeek-V4.1-Flash`를 `DeepSeek-V4-Flash-0731`과 혼동하지 않는다. `Super`를 기존 기본값인 `NVIDIA-Nemotron-3-Nano-30B-A3B`나 `Nemotron-3_5-Lightning`으로 대체하지 않는다. 실패 시 GPT/Luna로 자동 전환하지 않는다. 모델 변경은 별도 결정과 새 시험 조건으로 남긴다.

### 2.2 기존 수치의 정확한 해석

원자료는 [최종 비교 metrics](../../outputs/benchmark-late-usage-report-20261011-v414/metrics.json)와 [이미지 포함 단일 보고서](../../outputs/benchmark-late-usage-report-20261011-v414/report.pdf), [최종 검증 기록](../verification/benchmark-late-usage-20261011.md)이다.

| 구분 | 고정된 시험 경계 | 확인 결과 | 소요 시간과 추정 비용 |
|---|---|---|---|
| Flash 사진 관측 | source409, 공개 방 3종 × 2회 | 6/6 구조화 관측 통과 | 전체 역할 시간 중앙값 10.750초, 6회 합계 USD 0.0278250 |
| Super 설계 | source411b, 거실 1회 | 장면 계약 통과 | 20.937초, USD 0.0103932 |
| Super 설계 | source413, 식당 1회 | 장면 계약 통과 | 11.969초, USD 0.0057615 |
| Super 설계 | source414, 침실 1회 | `REPAIR_STALLED`, 실패 | 40.484초, USD 0.0238089 |

Super의 위 설계 시험은 **공통으로 저장한 Luna 관측을 입력한 역할 비교**다. Flash가 직접 만든 관측을 Super에 넘긴 최신 전체 제품 시험의 성적으로 대체해서는 안 된다. 서로 다른 source 결과를 합쳐 동일 조건의 성공률로 광고하지 않는다. Super의 첫 두 사례는 수정 회복 사례가 아니므로 “수정 성공률이 높다”는 주장에도 사용하지 않는다.

Flash의 구조화 성공은 사진 배치·지지 관계의 정밀도, 실측 크기, 실물 주행 성공을 뜻하지 않는다. 세 방의 개발용 시험이며 대규모 미공개 holdout이나 모든 Token Factory 모델의 완결된 순위도 아니다. 기존 미착수·실패·UNKNOWN 결과를 지우지 않는다.

**선정 논리:** Flash는 이 과제의 관측 시험에서 짧은 대기시간과 안정적인 구조화 출력을 보였다. Super는 실제 장면 설계 성공 사례가 있고, NVIDIA 모델이 제품의 핵심 설계·수정에 기여하도록 한다. 둘 다 Nebius에서 호출하므로 운영 경로도 단순해진다. 따라서 “현재 확보한 근거와 Nebius/NVIDIA 활용 목적에 맞춰 선정한 조합”이라고 설명할 수 있다. **“모든 모델 중 최적임이 입증됐다” 또는 “가장 싸고 정확하다”는 표현은 현재 근거로 사용할 수 없다.**

제출 설명에 사용할 영문 초안은 다음과 같다. P2 결과가 생기면 선택 조합의 실제 end-to-end 성적을 별도 문장으로 추가한다.

> We selected DeepSeek V4.1 Flash for visual observation and NVIDIA Nemotron 3 Super for scene planning and repair, both served through Nebius Token Factory. In our task-specific development pilot, Flash produced valid structured observations in all six tested runs, with a median role latency of 10.75 seconds. Super produced successful scene-contract outputs in the tested living-room and dining-room cases, while the bedroom case exposed an unresolved repair failure. These results support our engineering choice, not a universal model ranking. The final Flash-to-Super application workflow requires its own end-to-end validation.

## 3 기존 구현과 먼저 확인할 결함

아래는 새 프레임워크를 만들 대상이 아니라 기존 제품 경로에서 마무리할 위치다.

| 영역 | 현재 코드와 증거 | 이번에 확인하거나 보완할 것 |
|---|---|---|
| 모델 설정 | `stage_routing.py`, `ApiKeySettings.tsx`, catalog 기반 모델 지원 | 새 기본 추천, 정확한 Super 지원, 저장 후 재실행 시 동일 route |
| 일반 생성 | `build_configured_stage_service`, `BudgetedPipeline` | benchmark 전용 override 없이 최신 예산형 파이프라인 선택 |
| 오류 수정 | `semantic_scene.py`, `scene_contract.py`, `repair_scope.py`, `generation_store.py` | 침실 원실패 재현, 이전 배치 되돌림, 영향 관계를 따라 범위 확장 |
| 객체 표현 | `photo_layout.py`, `semantic_bindings.py`, core site tools | 여러 물체가 하나의 그룹 박스로 소실되지 않게 개별 인스턴스 보존 |
| UI와 Isaac | `ChatWorkspace.tsx`, generation render port, engine host | 현재 단계 하나, 실제 현재 장면, build·Run·Stop·재열기 연결 |
| 비용과 진단 | `ExecutionBudget`, output diagnostics, late usage 수신 | 빈 출력·length·timeout·미정산 원인과 원장 유지 |
| 실물 | robot field suite, corrected driver path, observation bridge | 최신 드라이버의 실제 scan과 정합·임무 인수는 별도 현장 시험 |

코드 점검에서 확인한 차이:

1. `StageRoutingSettings.state()`의 기존 추천은 OpenAI 관측 + 첫 Nebius 설계를 선택한다. 새 결정을 UI와 제품 기본 경로에 반영해야 한다.
2. 정적 planner 목록은 Nano/Lightning이며, 다른 모델은 catalog 및 generation policy 검증을 거친다. Super를 benchmark에서 썼다는 사실만으로 일반 설정창에서 정확히 적용된다고 가정하지 않는다.
3. policy 없는 경로는 기존 pipeline이며, policy가 있어야 `BudgetedPipeline`으로 간다. 설정 누락으로 구형 `max_repairs=1` 경로에 들어가는지 회귀해야 한다.
4. 기존 출력 기본값은 observer 4,000 / planner 20,000이다. 새 프로필의 명시적 상한이 wire 요청까지 전달되는지 검사해야 한다.
5. Super에 Nano용 `thinking_mode=disabled`를 그대로 붙이지 않는다. 모델별 지원 계약을 확인하지 않은 reasoning 옵션은 금지한다.
6. source414의 `REPAIR_STALLED`는 원인 코드이지 근본 원인 설명은 아니다. 요청·응답·검증 차이·수정 범위를 읽어 모델 오류인지 host 오류인지 먼저 분류한다.

기존 최신 보고서는 전체 데모 완료가 아니며, 정적 Isaac build·저장·재열기 이미지는 이동 검증을 대체하지 않는다. 과거 다른 조합의 이동 성공도 새 조합의 인수로 재사용하지 않는다.

## 4 P0 고정 모델을 일반 제품 설정에 연결

### 작업

1. `AGENTS.md`, 최신 Memory/Baseline, 이 계획과 관련 검증 기록을 읽고 dirty 파일 및 실행 중인 owner를 확인한다. 오래된 비교시험을 자동 재개하지 않는다.
2. 현재 설정을 내용에 키를 포함하지 않는 metadata snapshot으로 보존한다. 새로운 “Physical AI demo” 추천 프로필을 기존 설정 저장 경로에 추가한다. 선택/적용 상태와 정확한 모델 ID를 표시한다.
3. catalog 검증과 UI 옵션을 연결하여 Flash/Super를 일반 App에서 선택·저장·재시작 복원할 수 있게 한다. catalog에서 사라졌거나 지원이 바뀌면 명시적으로 막고 다른 모델을 대신 쓰지 않는다.
4. `StageRoutingSettings` → `build_configured_stage_service` → `ConfiguredStageTransport` → `BudgetedPipeline` → 실제 wire request의 역할별 ID를 검사한다. 벤치마크 전용 우회 경로를 제품 기본값으로 복사하지 않는다.
5. 설정 저장은 원자적으로 처리하고 실패 시 복구한다. 실행 중 route 교체 금지, 설정 변경 후 오래된 scene/plan 승인 무효화, API key OS 보안 저장소 유지 조건을 보존한다.
6. 역할별 출력 상한, timeout, 전체 generation policy를 UI에서 확인·조절할 수 있게 한다. 입력값과 실제 적용값이 다르면 시작 전에 차단한다.

첫 검증용 프로필은 아래 값을 명시적으로 저장한다. 상한은 목표 출력량이 아니다. 모델에 전체 코드나 같은 장면을 불필요하게 반복 출력시키지 않는다.

| 값 | 제안 초기값 |
|---|---|
| observer / planner 최대 출력 | 각 40,000 tokens. 지원 계약을 통과한 경우만 적용 |
| 요청당 응답 제한 | 300초 |
| 생성 전체 제한 | 900초 |
| 시간 배분 | 초기 540초 / 수정 300초 / 최종 로컬 검증 60초 |
| 생성당 총 HTTP / 수정 호출 | 최대 12회 / 그 안에 최대 3회 |
| 진전 없는 수정 | 연속 2회면 `REPAIR_STALLED` |
| 수정 시작 여유 | 90초 |
| 추가 외부 최종 검토 | 기본 꺼짐. 켜면 같은 총 호출·시간·비용 안에서 사전 배분 |

이는 코드의 `GenerationPolicy`를 기준으로 만든 **새 제품 인수 프로필**이다. 과거 source별 20k/40k, 12/24 HTTP, 서로 다른 총 timeout 성적과 동조건인 것처럼 합치지 않는다. 실제 여유가 부족하면 세부 병목 근거를 남기고 프로필 revision을 새로 정한다. 숫자만 올려 실패를 없애지 않는다.

`finish_reason=length` 또는 출력 소진, 402, 미확정 비용, 승인 기한 종료는 기존 중단 규칙을 유지한다. 특히 다른 모델의 빈 final을 이유로 Super까지 실패했다고 가정하지 말고 해당 모델의 reasoning/final 분리 진단을 사용한다.

### 회귀와 완료 조건

- `tests/integration/test_stage_routing_settings.py`, `test_generation_approval.py`와 `scripts/verify_stage_routing_settings.py`, `ApiKeySettings` 테스트를 확장한다.
- 사진은 Flash→Super, 텍스트는 Super만, repair는 Super로 호출될 body를 네트워크 없이 확인한다.
- 프로세스 재실행 후 같은 설정 SHA, catalog SHA, policy SHA가 복원된다. 설정 저장 자체의 유료 호출은 0회다.
- 기본 UI에 다른 모델이 선택되거나 무음 fallback, 4k/20k 묵시적 복귀, 구형 repair 경로 진입이 없다.
- 산출물은 설정 변경 코드, 회귀, `docs/verification/physical-ai-model-routing-20261011.md`이다. 검증 파일은 구현 시 생성하며 이 계획이 존재한다고 PASS가 되지는 않는다.

## 5 P1 원실패를 재현하고 범용 오류 수정 루프 완성

### 5.1 실패별 원인 분류

Super 침실 실패의 execution ID를 원 보고서에서 찾고 다음을 한 묶음으로 남긴다: 관측 입력, 초기 proposal, compiler 오류, 각 repair 요청과 응답, 적용 전후 장면 hash, invalidated dependency, 변경 거절 이유, 누적 시간·호출·비용. 비밀·개인자료는 출력하거나 공개하지 않는다.

분류는 최소 `MODEL_OUTPUT`, `SCHEMA_ADAPTER`, `CONSTRAINT_CONFLICT`, `REPAIR_SCOPE`, `APPLY_ROLLBACK`, `RENDER_OR_RUNTIME`, `TIME_OR_BUDGET`로 한다. 각 수정에는 원 재현 FAIL → 수정 후 PASS와 다른 방·객체에서도 통하는 반례 테스트가 있어야 한다. 저장 응답 재생이 통과한 것과 실제 모델 재시험 성공은 분리한다.

### 5.2 수정 원칙

- 먼저 놓은 물체도 옮길 수 있다. child만 수정해서는 해결 안 되는 충돌이면 parent/support/room 등 영향 범위를 근거와 함께 확장한다. 변경 불가능한 고정 anchor를 임의로 늘리지 않는다.
- 후보 장면에 변경을 적용하고 전체 제약을 다시 검사한 다음 commit한다. 실패하면 마지막 유효 revision으로 되돌린다. 기존 좌표계·goal·render 승인도 revision 변화에 따라 무효화한다.
- 방 크기는 단일 사진의 추정치다. 실측이 없는 10×12m 추정 자체를 실패로 만들지 않는다. 사용자가 준 크기는 별도 provenance가 있는 제약으로 취급한다.
- 합리적인 축소·확대 후보도 재검증할 수 있어야 한다. 후보가 경로 불가이면 해당 후보의 결과로 기록하고 “이 방은 불가능”이라고 일반화하지 않는다.
- 물체의 종류뿐 아니라 인스턴스 수, ID, 부모·지지 관계를 보존한다. 예를 들어 관측에 의자 여러 개가 있으면 그룹 하나가 아니라 표현 가능한 개별 인스턴스로 풀되, 모든 식탁에 특정 개수의 의자를 강제하지 않는다.
- 후보가 바뀌어도 같은 오류 집합이 유지되는지, 다른 제약은 개선되는지 비교한다. 수정했다고 무조건 진전으로 세지 않으며, 허용된 같은 물체의 재수정을 일괄 금지하지 않는다.
- 남은 문제가 외관·실측 미확정뿐이라면 `estimated` 또는 품질 경고로 진행할 수 있다. 비정상 수치, 끊긴 참조, 실물 충돌 여유, 안전 정지 실패는 경고로 완화하지 않는다.
- 침대·옷장·행거 등은 기존 크기 조절 가능한 household 자산/절차형 표현을 쓴다. 조감도 충돌 박스와 사용자용 3D를 구분하고 우측 화면을 전부 단색 박스로 대체하지 않는다.
- “나중에 LiDAR가 보정한다”는 이유로 모든 오차를 허용하지 않는다. 2D LiDAR로 가구 높이·색상·숨은 영역·가느다란 바닥 케이블을 모두 확인할 수 없으며, 미관측은 빈 공간이 아니다.

### 5.3 상태 표시와 오류 처리

- 채팅에는 지금 답해야 할 질문 한 개 또는 다음 주 행동 한 개만 활성화한다. 질문 자체에 필요한 대안 버튼은 한 질문 안에서 보여준다. Stop/취소는 안전상 예외로 계속 접근 가능하다.
- 관측·설계·수정·Isaac build·렌더 대기·완료를 구분한다. 사진이나 scene이 없는데 다음 검사·수집·주행 버튼이 우르르 나오지 않게 한다.
- 텍스트 입력에서 사진 요구가 없어야 하며, 실제 생성 실패 시 `generation_failed`와 구체적 원인·다음 행동을 표시한다. 연결됨과 현재 3D 장면 완성을 구분한다.
- 사용자에게 timeout을 알린 뒤 원 응답/usage를 무조건 버리지 않는다. 기존 승인·수신 한도에서 동일 요청의 후행 결과를 소유권 있게 정산하되 원 timeout 판정은 유지한다. 새 요청으로 재전송하지 않는다.
- benchmark의 후행 수신 900초/동시 4개 옵션이 일반 App에 자동 적용된 것으로 간주하지 않는다. 일반 경로의 bounded 수신·종료·소유권이 검증되지 않으면 미확정 비용을 유지하고 제한을 설명한다.
- Stop, cleanup error, 위치 상실 시의 stale pose/scan, 5초 요약의 관측 시각이 기존 안전 경계를 유지하는지 관련 회귀를 돌린다.

### 완료 조건

원 침실 실패와 그룹 인스턴스 누락을 재현하는 회귀, 성공 후 재수정·rollback·범위 확장·텍스트 only·출력 소진·timeout/후행 정산·중복 적용 방지 회귀가 통과한다. UI 타입 검사와 production build를 통과한다. 변경과 무관한 전체 장시간 시험을 매번 반복하지 말고, 단계 끝에서 통합 회귀를 한 번 수행한다.

주요 대상은 `budgeted_pipeline.py`, `semantic_scene.py`, `semantic_bindings.py`, `scene_contract.py`, `repair_scope.py`, `generation_store.py`, `photo_layout.py`, `output_diagnostics.py`, `ChatWorkspace.tsx`, `SceneEditReview.tsx`이다. `verify_saved_generation.py`, `verify_staged_repair_saved_response.py`, `audit_budgeted_request_trace.py`, `audit_scene_contract_batch.py`를 재사용한다. 새 독립 agent framework를 만들지 않는다.

## 6 P2 고정 조합으로 일반 App 전체 로컬 인수

### 6.1 시험 전에 동결할 것

source/web build, public input/license, model catalog, prompt/schema, route, policy, 평가 기준, Isaac 버전·장치·자산 목록을 hash와 함께 고정한다. 일반 App의 승인 경로와 비용 원장을 사용하고 benchmark campaign의 권한을 제품에 빌려주지 않는다.

기존 원장의 held와 사용분을 모두 포함한다. v415 원노출은 Nebius USD 4.52404747, OpenAI USD 1.83015270였고 청구서 확정값이 아니다. 기존 USD5 상한이나 18:00 KST 기한을 초기화하지 않는다. 이 계획은 새 금액·기간·사진 전송 승인이 아니다. 유효한 범위가 없거나 최악 예약 비용이 남은 한도를 초과하면 유료 시험 전에 필요한 범위를 한 번에 제시한다. OpenAI 호출은 새 고정 조합에서 예정하지 않는다.

### 6.2 최소 시험 묶음

| 순서 | 입력 | 목적 |
|---|---|---|
| A | 공개 사진 1종, 텍스트 1종 | 각각 일반 UI에서 전체 경로가 도는지 먼저 확인 |
| B | 나머지 공개 사진 2종, 텍스트 2종 | 총 3방 × photo/text 개발용 인수. 관측 모델 비교와 혼동 금지 |
| C | A의 사진과 텍스트 각 1회 새 세션 | 같은 설정에서 반복 실행·이전 상태 누출·재시작 검증 |

계획된 새 generation은 최대 8개다. 이는 HTTP 8회가 아니며 각각 P0의 공유 호출 한도 안에 관측·설계·수정이 포함된다. 처음 두 개가 실패하면 나머지 여섯 개를 무작정 소진하지 않는다. 원인을 고쳐 새 source로 해당 실패와 영향받는 공통 경로를 재검증한다. 수정 전 실패를 삭제하거나 성공까지 시도한 횟수를 숨기지 않는다. 모든 모델 재비교와 과거 59개 미착수 슬롯은 이 제출 준비의 선행 과제가 아니다.

### 6.3 각 전체 경로

1. 원클릭 launcher → 기존 Isaac 백그라운드 기동과 준비 확인. 실패 시 누락 항목과 조치, 안전하게 가능한 project-local 복구만 제공한다. 새 시스템 설치·권한 우회는 하지 않는다.
2. 새 채팅 → 텍스트 또는 사진+텍스트 입력 → 실물 유무 질문 → SIM 선택. 모델은 Flash/Super로 유지한다.
3. 실제 LLM 생성과 필요시 검증·수정 → 유효 scene revision → 실제 Isaac build → 그 revision의 새 렌더를 우측에 표시한다. 이전 저장 이미지를 현재 생성 성공으로 사용하지 않는다.
4. 자연어로 현재 위치에서 명명된 목표 주변의 도달 가능한 위치를 요청 → goal binding → 경로 계산 → 실제 Isaac robot Run → 실제 transform/거리와 terminal 도달 근거를 기록한다. 모서리 벽·가구 중심으로 관통하는 목표를 성공 처리하지 않는다.
5. 별도 이동 중 Stop → 안정 정지 → 새로운 명령 없이 자동 재개하지 않음을 확인한다. “이미 정지한 장면에서 Stop 클릭”만으로 통과시키지 않는다.
6. 저장 → reload/reset → 닫고 다시 열기 → scene·모델·현재 상태 복원. 이전 실행 권한이나 움직임은 자동 복원하지 않는다.
7. 수정 요청 → 후보 preview → 적용/취소 → goal/preview 무효화와 재계획. 적어도 한 사례에서 실제 모델 기반 수정 요청도 실행한다. 자연스러운 오류가 없으면 지정된 결함을 넣은 시험은 fault injection으로 따로 표시한다.

사용자 요청의 loop는 먼저 SIM에서 왕복·Stop과 배터리/센서/통신 이상 주입을 시험한다. SIM 성공이 physical loop 승인은 아니다. 실제 5초 상황 요약은 관측 데이터 기반으로 만들며 5초마다 유료 LLM을 호출해야 하는 요구로 바꾸지 않는다.

### 6.4 평가와 완료 기준

- 기능: 계획된 photo/text 각각 모든 필수 단계가 통과해야 `LOCAL_FULL_PASS`. 결함 발견 후 수정됐다면 최종 source의 영향 범위 재시험 근거를 붙인다.
- 품질: 입력에 확실히 보이는 주요 물체 누락, 개별 수량 소실, 잘못된 지지 관계, 공중 부양·중대한 관통, 조작 불가능한 잘못된 goal binding은 별도로 검사한다. 미확정 치수·가림·시점 한계는 추정으로 표기한다.
- 사진, 조감도, 동일 scene의 실제 Isaac 3D를 나란히 남긴다. schema PASS를 사진 정밀도 PASS로 바꾸지 않는다. 사람의 품질 검토를 하지 않았으면 `HUMAN_REVIEW_NOT_RUN`이다.
- 자동 품질 기준은 시험 시작 전에 고정한다. 임의 사진·좌표·파일 hash에 대한 예외를 넣어 통과시키지 않는다. 본인 침실에만 맞춘 조건은 금지한다.
- 기록: 성공/실패 단계, 최초 성공/수정 후 회복, HTTP와 전체 지연 p50/p95, 사용 추정액/held, 실제 렌더와 scene/source SHA를 표로 만든다. 표본이 적으면 p95 안정성이 낮다고 적는다.
- P0와 P2가 통과하면 기존 1번의 제품 연결과 3번의 로컬 전체 검증을 함께 닫는다. **Physical AI 전체 제출 완료나 실물 정합 완료로는 닫지 않는다.**

`live-generation-screen.mjs`, `benchmark-journey-policy.mjs`, `verify_live_generation_screen.py`, `verify_chat_inspection_isaac.py`와 기존 runner를 연결한다. 기존 ordinary App/API 경로를 그대로 사용하고 테스트 전용 성공 endpoint를 만들지 않는다.

## 7 P3 로컬 통과 후 제한된 Serverless 작업

### 7.1 규정과 비용 판단

공식 규칙의 Physical AI 설명은 Serverless Jobs의 시뮬레이션·정책 평가·센서 처리 활용을 적고 있다. 반면 운영진의 일반 답변은 Jobs/Endpoints가 필수는 아니라고 설명한다. 일반 답변이 Physical AI의 특정 문구까지 면제하는지는 확인되지 않았다. 따라서 **무조건 필수라고 단정하거나, Apps and Agents의 선택 사항을 Physical AI에 그대로 적용하지 않는다.** [공식 규칙](https://nebiusglobalaihackathon.devpost.com/rules), [운영진 답변](https://nebiusglobalaihackathon.devpost.com/forum_topics/45163-does-calling-an-nvidia-model-via-token-factory-satisfy-the-must-run-on-nebius-requirement)

운영진에게 확인할 질문 초안:

> TwinPulse enters the Physical AI track, runs local Isaac Sim and a physical TurtleBot3, and uses DeepSeek observation plus NVIDIA Nemotron planning through Nebius Token Factory at runtime. Is an actual Nebius Serverless Job required for this track, or recommended? Would a bounded job evaluating a saved sensor/scene session, with its results used in the application, satisfy the intended Serverless usage?

질문을 문서에 준비하는 것과 외부에 게시하는 것은 다르다. 승인 없이 메시지를 보내지 않는다. 트랙별 명시 답변을 받으면 URL과 날짜를 기록하고 이 항목만 조정한다. 현재 보수적 준비안은 **실제로 유용한 작은 Job 하나**다.

Serverless의 실행 중 compute/storage는 Compute 요금 체계를 적용하고 별도 저장소 비용은 종료 후에도 남을 수 있다. 특히 문서상 Jobs에는 Devlab과 같은 stopped 상태가 없으므로 “Stop 버튼만 누르면 과금이 끝난다”는 설계를 하지 않는다. Token Factory 크레딧과 AI Cloud 크레딧의 공용 여부, 적용 region/SKU/가격/청구 단위는 실제 계정에서 확인할 항목이다. [공식 과금 안내](https://docs.nebius.com/serverless/pricing-quotas)

### 7.2 최소 작업 범위

기본 후보는 **저장된 센서 또는 시뮬레이션 관측과 scene revision을 검증하는 유한 배치 작업**이다. 기존 comparison/observation 코어를 재사용하고 입력 revision·관측 품질·오차 요약·불확실성·실패 코드를 돌려준다. App은 이를 “클라우드 재검증” 결과로 표시하고 해당 revision과 연결한다. 장식용 Hello World나 API ping은 사용 근거로 삼지 않는다.

1. `observation_model_comparison.py`, `world_observation.py`, `scan_observation.py`의 필요한 순수 로직만 worker 경계로 분리한다. 새 worker entrypoint와 request/result schema가 필요하면 이때 추가하되, 이름과 API를 구현 전에 정의한다.
2. 입력은 승인된 공개 장면/합성 관측을 우선 사용한다. 저장 로봇 데이터 사용 시 좌표·공간 정보의 외부 전송 범위를 별도 승인받는다. LLM 사진 전송 승인을 Cloud 업로드 승인으로 확장하지 않는다.
3. 로컬에서 동일 worker의 정상 입력, 깨진 입력, timeout, 중복 결과, 오래된 scene 결과 거절을 검증한다. 로컬 dry run은 Cloud 실행 PASS가 아니다.
4. 전체 Isaac GUI/로봇 제어/LLM 모델 hosting을 클라우드로 이사시키지 않는다. CPU로 충분한 작업이면 GPU를 요청하지 않는다. 플랫폼이 제공하는 실제 SKU와 호환성은 사전 확인한다.
5. cloud job ID를 기존 execution ID에 연결한다. upload/job/poll/download/cleanup 시간을 각각 기록한다. 로봇 제어는 로컬에 남고 클라우드 연결 불량으로 정지 경계가 느슨해지지 않는다.

### 7.3 유료 실행 전 문턱

- P2 `LOCAL_FULL_PASS`와 worker local dry run PASS가 있어야 한다.
- 견적은 compute와 disk, 저장소, 전송, 초기 준비 시간을 포함한다. 1개 Job, 동시 실행 1개, 자동 재시도 0회를 기본으로 한다.
- 예상 상한과 별도로 실제 플랫폼이 보장하는 runtime 제한/취소·삭제 방법을 공식 API에서 확인한다. 애플리케이션 watchdog과 비용 알림만으로 hard billing cap이 생긴다고 주장하지 않는다.
- 정상 종료 및 실패 경로의 소유 자원 ID cleanup을 설계한다. 타인의 자원과 기존 저장 원본은 건드리지 않는다. 완료 확인 뒤 보존할 결과와 제거할 임시 자원을 분리한다.
- 구체적인 실행시간·SKU·최대 비용·데이터 범위·종료 방법을 사용자에게 한 번에 제시해 승인받는다. 승인 전 생성/배포하지 않는다. 종료를 보장할 방법이 확인되지 않으면 아직 진입하지 않는다.

완료는 실제 Job의 terminal 상태, 결과 원본/요약, App의 해당 revision 표시, 자원 종료/잔여 저장 비용, 청구 확인 또는 미확정액을 남겼을 때다. 트랙별 공식 확인으로 Jobs가 불필요해졌더라도 Sol이 임의로 생략하지 말고 사용자와 범위를 확정해 기록한다.

## 8 P4 실물 연결과 같은 사용자 흐름 인수

### 현장 전에 끝낼 준비

기존 `scripts/run_robot_field_suite.py`와 `robot_field_candidate.py`를 유지한다. 사용자에게 여러 스크립트를 순서대로 찾아 실행시키지 말고 기존 단일 진입점/웹 흐름에 진단·원본 로그 수집을 연결한다. [드라이버 경로 검증](../verification/robot-driver-path-integration-20261006.md)은 수정본 build·연결 준비의 근거이며, 그 수정본의 실제 scan 인수와 자율 임무 성공 근거는 아니다.

현재 부팅/배포본의 정지 기록, 센서 시각 기준, extrinsics/footprint, room registration과 임무 qualification이 필요한지 기존 gate를 점검한다. 누락된 파일을 내용 없는 PASS로 생성하지 않는다. raw scan, odom, TF, 명령, 수신 시각, 정지·cleanup 결과를 동일 execution ID와 묶는다.

### 현장 실행 순서

1. 사용자가 현장 감독·충전 분리·공간 확보와 해당 시험 범위를 승인한 뒤 시작한다. 과거 승인을 현재 새 시험의 현장 확인으로 대신하지 않는다.
2. 전원/SSH/현재 boot·release·배터리·board idle·motor 상태를 한 번에 검사한다. 전원을 켰을 때의 torque 상태를 제품의 안전 초기화로 처리할 수 있는지 승인된 범위에서 확인한다. 무조건 고장이라고 단정하지 않는다.
3. 실패해도 독립적으로 안전하게 확인할 수 있는 항목과 로그 수집은 계속하되 이동은 gate 통과 전 금지한다. cleanup이 불명확하거나 안전 정지가 확인되지 않으면 추가 구동을 멈춘다.
4. 최신 드라이버 scan 시작→신선한 scan/odom/TF→정지 수신과 실제 LiDAR 멈춤을 확인한다. 살아 있는 상태와 과거 snapshot을 구분한다.
5. 같은 boot/release의 bounded 주행·정지 검증 및 사용자 실제 움직임 확인을 끝낸다. 기존 유효한 동일 조건 증거를 불필요하게 반복하지 않는다.
6. 채팅의 Twin 검사 Confirm→현재 위치 추정→필요한 안전한 스캔→bounded wall correction→derived scene revision→목표와 Isaac preview 재검증을 연결한다. 수동으로 조금 다르게 놓은 시작 위치도 다루며 저장된 시작 pose를 현재로 강제하지 않는다.
7. 목적지 채팅→현재 revision의 SIM preview→실물 Confirm→주행→실제 도달/정지→복귀를 확인한다. 가능하면 독립 측정으로 위치 오차도 기록하고, odom 자체를 절대 위치 정답으로 쓰지 않는다.
8. loop는 초기 위치와 목표를 명시하고 승인된 제한 안에서 먼저 한 번 왕복한다. 지속 loop 허용 여부는 기존 mission 계약과 별개로 검증한다. 무기한 무감독 주행이나 자동 재연결·재개를 허용하지 않는다.
9. Stop, 센서 stale, 통신 단절, 배터리 기준 미달, 구동 이상 시 안전 종료와 로그를 확인한다. 로봇을 일부러 충돌시키거나 모터를 물리적으로 막아 고장을 만들지 않는다. 위험한 오류는 먼저 주입 시험으로 확인하고 실제 확인 범위를 제한한다.

자율 임무의 기존 scan 200ms/input 250ms/segment 50ms/0.03m/s/0.20rad/s/45초 guard를 이 계획으로 완화하지 않는다. 수동 조이스틱의 별도 속도 설정과 혼동하지 않는다. 사용자의 긴 loop 요구와 45초 계약이 충돌하면 먼저 제한된 반복 세션의 의미와 재승인 정책을 설계·검증하며, 단순히 제한을 삭제하지 않는다.

완료 기록에는 실제 scan 유효성·좌표 정합·재배치 시작 위치·정지·goal 도달·loop의 검증/미검증을 각각 표시한다. 로봇 전원을 켜기만 하면 모두 끝난다는 표현은 금지한다.

## 9 기존 12단계 데모의 누락 방지표

| 원 요구 | 구현 또는 인수할 내용 | 연결 단계 |
|---|---|---|
| 1 원클릭 | launcher 한 번으로 일반 App, 실패 시 명확한 안내 | P2 |
| 2 Isaac와 준비 상태 | 백그라운드 기동, 필수 파일/설정 체크, 가능한 로컬 복구와 불가 항목 구분 | P1, P2 |
| 3 채팅과 입력 | ChatGPT 형태의 텍스트·사진 입력, 사진은 선택 사항, 음성은 후속 | P1, P2 |
| 4 로봇 유무 질문 | 답할 때까지 해당 질문 대기, 후속 질문을 동시에 열지 않음 | P1, P2 |
| 5 SIM | 텍스트/사진으로 Twin 생성, 생성 진행 설명, 실제 Isaac Run·자연어 목표, 우측 접기 | P2 |
| 6 로봇 선택 | 등록 Burger 선택, 미지원 로봇을 이미 지원하는 듯 표시 금지 | P4 |
| 7 생성과 연결 | 생성과 읽기 전용 연결 점검을 독립 진행, 1회 검증 버튼과 사람의 움직임 확인, 배터리/작업/연결 상태 | P1, P4 |
| 8 Twin 검사 승인 | 현재 scene와 로봇 준비가 갖춰진 뒤 하나의 Confirm | P4 |
| 9 LiDAR 보정 | 실제 관측 기반 위치/벽 보정, 새 revision과 품질·불확실성 표시 | P4 |
| 10 경로 시연 | 현재 위치와 목표의 경로를 3D에서 먼저 시연, 실물 실행은 따로 승인 | P2, P4 |
| 11 실행과 5초 설명 | 실제 관측 기반 요약, stale와 오류 명시, 실행 ID 연결 | P4 |
| 12 왕복 loop | 초기 위치 복귀·재출발, 현재 작업 표시, Stop/배터리/구동 이상 보호 | P2 주입 시험, P4 제한된 실제 인수 |

배터리 %는 전압 기반 추정이면 그렇게 표시하고 시각을 붙인다. “최적 경로”는 선택한 지도·비용함수·계획기 제약 안에서의 경로이며 실제 방의 전역 최적이라고 과장하지 않는다.

## 10 P5 촬영과 제출 영상

촬영은 P4 이전에 구도를 정하고 P4 검증 중 함께 한다. 화면 녹화와 외부 로봇 촬영을 같은 실행의 시각/ID로 연결한다. 이후 편집만 하면 되게 성공·실패 원본을 보존한다.

목표 길이는 여유를 둔 약 165초다: 문제와 입력 15초, 실제 모델 생성과 Twin 30초, 실제 로봇 동작 최소 65초, 보정·목표·정지·loop 결과 35초, 기술/근거/한계 20초. 촬영 품질에 따라 구간은 조절하되 실제 하드웨어 구간을 화면 애니메이션으로 대체하지 않는다. 정상 속도의 연속 하드웨어 구간을 확보하고 시간 압축은 명시한다.

공식 제출 영상은 3분 미만의 공개 YouTube이며, Physical AI 하드웨어 프로젝트는 실제 하드웨어가 작동하는 최소 1분 구간을 요구한다. 제출 자료는 영어 또는 영어 번역을 포함한다. [공식 규칙](https://nebiusglobalaihackathon.devpost.com/rules)

Nebius/NVIDIA의 역할, 실제 모델/생성 revision/사용자 Confirm, 결과와 미검증 범위를 설명한다. 실물 없이 실제로 주행한 듯 합성하지 않는다. 개인 방·화면·주소·계정 정보와 제3자 이미지 공개 권한을 점검한 후 사용자 승인으로 업로드한다.

## 11 P6 라이선스와 재현 가능한 공개 저장소

### 라이선스 추천 (선택 이전 이력)

현재 결정: Apache-2.0. 아래 비교는 선택 전 자료이며 새 결정이나 추가 조건이 아니다. 사용자 확정 정책과 적용 파일은 `docs/LICENSING.md` 및 v422 검증이 기준이다.

**Apache-2.0을 우선 추천한다.** TwinPulse를 다른 개발자가 확장할 수 있는 로봇·AI 도구로 공개하려는 목적에 맞고, 기여자의 관련 특허에 대한 명시적 허락 조항이 있다. 모든 특허 위험을 없애주는 보증은 아니다. 최대한 짧고 단순한 허용 라이선스를 원하면 MIT도 적절하다.

| 선택 | 성격과 유지 의무 | 이 프로젝트에 대한 판단 |
|---|---|---|
| MIT | 상업 사용·수정·배포 가능, 저작권/허락문 유지. 명시적 특허 허락 조항은 없음 | 단순 공개를 최우선할 때 |
| BSD-3-Clause | 허용적 이용, 고지 유지 및 저자/기여자 이름의 무단 보증·홍보 사용 제한 | 비보증 명칭 조건을 중시할 때 |
| Apache-2.0 | 명시적 기여자 특허 허락, 라이선스·변경·관련 고지 유지, 해당 upstream NOTICE 보존 | 협업과 재사용할 기술 프로젝트에 우선 추천 |

[MIT 원문](https://opensource.org/license/mit), [BSD-3-Clause 원문](https://opensource.org/license/bsd-3-clause), [Apache-2.0 원문](https://www.apache.org/licenses/LICENSE-2.0)을 기준으로 최종 선택한다. 이는 기술적 선택 안내이며 개별 권리 관계의 법률 판단을 대체하지 않는다. **사용자가 선택하기 전 LICENSE를 추가하거나 라이선스가 확정됐다고 표시하지 않는다.**

### 작업과 완료 조건

1. 본인 코드, third-party 코드, URDF/mesh/texture, 사진, 모델, Isaac 런타임을 구분한 자산 목록을 먼저 만든다. 의존성마다 출처·버전·라이선스·재배포 여부를 기록한다.
2. 프로젝트의 Apache/MIT 선택이 외부 사진·모델·Isaac까지 같은 라이선스로 바꾸지는 않는다. CC BY-SA 사진은 필요한 attribution/조건을 따로 처리하고, 재배포 불가 자산은 허용된 획득 방법만 문서화한다.
3. 사용자 선택 후 LICENSE와 필요한 고지를 추가한다. 저작권자 이름을 임의로 정하지 않는다. 비밀 키, 계정 정보, 개인 사진/원본 좌표·raw 로그, 모델 weights/상용 설치본을 무심코 공개하지 않는다.
4. 영어 README에 설치 전제, 기존 런타임 버전, 원클릭 실행, 텍스트/사진/SIM/REAL 예제, 선택 모델 설정, 제한·비용·안전·종료법을 작성한다. 로봇 없는 재현 경로를 제공한다.
5. 실제 유료 생성 시험과 무료 saved replay를 구분한다. saved replay는 실제 LLM·클라우드 동작을 입증하지 않는다. 공개 benchmark 문서는 metrics와 허용된 이미지·입력 출처 중심이며 full raw 공개를 강제하지 않는다.
6. 기존 dirty checkout을 청소하거나 새 저장소로 갈아엎지 않는다. 허용 목록으로 재현용 사본/패키지를 만들어 누락 파일을 확인한다. 새 설치·git commit/push/공개 전환은 별도 승인 범위에서만 한다.
7. 익명 사용자가 README와 예제 입력/자산 획득법으로 실행할 수 있는지 확인한다. 확인한 환경과 아직 확인하지 못한 타 환경을 구분한다.

## 12 P7 최종 제출 점검

서술 초안은 앞 단계에서 모아 마지막에 새로 쓰지 않는다. 제목·문제·제품 흐름·기술 구조·Nebius/NVIDIA의 실제 기여·모델 선정 근거·실패와 한계·공급자 피드백·기간 내 변경 사항을 준비한다.

공식 마감은 2026-10-30 10:00 PDT, 한국 시각으로 **2026-10-31 02:00 KST**다. 공개 코드/라이선스/실행법, 3분 미만 영상, 트랙, 기술 설명과 피드백을 확인한다. 규칙상 물리 프로젝트의 demo URL 예외와 심사 접근 요구는 구분한다. 저장소·영상·테스트 패키지를 익명으로 접근 확인하고 심사 요청에 대응 가능한 실행 지침을 둔다. [공식 규칙](https://nebiusglobalaihackathon.devpost.com/rules)

제출 직전 체크:

- 모델·코드·영상·benchmark 표가 같은 제품 버전을 설명하는가.
- 실패/NOT_RUN/미정산 비용/물리 정밀도 미검증을 숨기지 않았는가.
- Physical AI 트랙으로 선택했는가. Apps and Agents 체크리스트로 대체하지 않았는가.
- 공개 링크, 영상 권한, 이미지 권리, 비밀 제거, 라이선스가 완료됐는가.
- 실제 Submit 후 confirmation을 저장했는가. 초안 저장과 최종 제출을 구분했는가.

최종 제출·계정 작업은 사용자의 승인에 따라 수행한다. “링크를 준비했으므로 제출 완료”라고 기록하지 않는다.

## 13 실행 근거와 단계 종료 형식

로그는 기존 실행 ID 체계를 확장해서 사용한다. 새 로깅 SaaS 구독은 필요 없다. 각 UI 요청의 `execution_id` 아래 generation/HTTP/scene/Isaac/Job/robot/video artifact를 자식 ID로 묶는다. 단계별 시작·종료와 wall time, 호출 수, 모델 ID, 입력/설정/source/scene SHA, 최초 실패·수정 diff·최종 상태·추정 비용과 held를 기록한다. CPU 병목은 필요한 함수만 profiling하고 외부 HTTP 대기와 분리한다.

단계 종료 보고에는 다음만 포함한다.

1. 완료한 사용자 동작과 실제 실행 경로.
2. PASS/FAIL/NOT_RUN 및 각 execution ID와 원 로그·화면.
3. 소비 추정액, 미정산액, 남은 승인 범위.
4. 미검증 내용과 바로 다음 작업. 새로운 권한이 필요한 경우 그 범위를 한 번에 요청.

P0/P1/P2의 의미 있는 증분마다 관련 회귀와 verification 문서를 남기고 Baseline/Memory를 동기화한다. 실제 milestone 종료 때 README/progress도 갱신한다. 다른 source의 결과를 덮어쓰거나 과거 실패를 PASS로 바꾸지 않는다. 완료한 후속 단계가 없으면 대기 시간을 채우지 말고 종료한다.

| 단계 | 계획 시점 상태 | 종료를 허용하는 증거 |
|---|---|---|
| 모델 선택 | DECIDED | 사용자 Flash/Super 선택 |
| P0 제품 적용 | NOT_RUN | 일반 설정·wire·재시작 회귀 |
| P1 결함 수정 | NOT_RUN | 원실패 재현과 범용 회귀 |
| P2 로컬 전체 | NOT_RUN | 실제 고정 조합 + ordinary App + actual Isaac |
| P3 Cloud | NOT_RUN | 필요 범위 확정, 실제 Job와 종료/비용 근거 |
| P4 실물 | NOT_RUN | 현장 승인과 최신 실측 인수 |
| P5 영상 | NOT_RUN | 제출 가능한 실제 영상 |
| P6 공개 패키지 | Apache-2.0 선택/자체 코드 고지 적용 v422 | 외부 권리·개인정보·공개 재현은 잔여 |
| P7 제출 | NOT_RUN | 실제 제출 확인 |

2026-10-11 실행 증분(v417): **P0 일반 설정 실제 적용/재구성·P1 로컬 결함 회귀 PASS**. 위 표는 계획 작성 시점 상태이며 [현재 검증](../verification/physical-ai-model-routing-20261011.md)이 최신이다. Provider344/관련App195/Web449/type/build, Super 원FAIL read-only 수치 진단과 범용 개수 보존을 확인했다. 새 Flash/Super 실제 생성·ordinary App/actual Isaac 전체는 P2 NOT_RUN, Cloud/실물/제출 완료가 아니다. 라이선스는 사용자 요청으로 보류하며 기존 유료/held/18KST 기한을 늘리지 않는다.

## 14 GPT 6.1 Sol 실행 지시문

> 기준 저장소 AGENTS와 최신 Memory/Baseline, 이 계획을 읽고 P0부터 의존성 순서로 진행하라. 최종 목적은 사진 또는 텍스트 → 자동 검증·수정되는 Isaac Twin → 사용자의 승인 아래 실제 로봇 재스캔·목표 주행·정지로 이어지는 Physical AI 제품이다. 문서나 mock만 늘리지 말고 기존 App/API/provider/core/Isaac/robot-local 경로를 연결하라.
>
> 모델은 사진 관측 DeepSeek V4.1 Flash와 설계·수정 Nemotron 3 Super 120B, 모두 Nebius로 고정한다. 실패를 피하려 다른 모델이나 방별 하드코딩으로 바꾸지 마라. 먼저 원실패를 저장 자료로 재현·수정하고, 같은 조합을 일반 UI에서 실제 검증하라. 모델 선택 완료, 로컬 전체 통과, 실제 Cloud, 실제 로봇 인수는 별도로 보고하라.
>
> 허용된 로컬 작업은 사소한 증분마다 멈추지 말고 다음 안전한 작업까지 계속하라. 유료 호출은 유효한 데이터·목적지·금액·기한의 승인과 원장 범위 안에서만 수행하라. 한도 소진, 비용 미확정, 402, 출력 소진과 안전 guard를 완화하지 마라. 새 승인이나 클라우드·현장 권한이 필요하면 필요한 범위를 한 번에 제시하되 영향을 받지 않는 오프라인 준비는 진행하라.
>
> P2 전체 로컬 성공 전에 Cloud를 띄우지 마라. 새 설치·시스템 설정·키 출력·원본 삭제·타 프로세스 강제 종료·새 에이전트 생성·commit/push·외부 메시지·영상 공개·최종 제출은 별도 승인 없이 하지 마라. 실물은 현장 승인 전 OFF로 취급하라. 사용자 라이선스 선택 전에 LICENSE를 확정하지 마라. dirty 변경, raw, 과거 실패, source별 시험 경계와 실물 임무 잠금을 보존하라.
>
> 각 단계의 완료 기준을 실제로 검증하고 execution ID·화면·오류 원인·비용과 미검증을 함께 보고하라. 최종 결과는 “이 모델이 최고”가 아니라 재현 가능한 선택 근거와 제품 전체 동작의 증거여야 한다.
