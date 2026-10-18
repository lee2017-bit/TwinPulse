# 벤치마크 timeout 후행 응답·비용 수집 — 2026-10-11 v415 (v413/414 구현 이력 포함)

## 승인과 원인

사용자는 시간 초과 시험의 성공 판정을 바꾸라는 것이 아니라, 다른 모델 시험을 계속하면서 같은 요청의 후행 응답·사용량을 보존하라고 명시 요청했다. 과거 transport는 socket timeout300초라 그 이후 연결에서 응답을 읽을 수 없었고, 전체 controller는 UNKNOWN 한 건에 중단했다. 기존 audit worker는 수신한 rejected/cancelled raw의 usage도 보존했지만, 이미 종료된 socket에서 없던 usage를 복구하지는 못한다.

공식 OpenAI [Chat Completion 조회](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/retrieve)는 `store=true`로 생성된 completion만 대상이다. 이전 요청은 이 사후조회 전제를 갖추지 않았으므로 재조회·확정비용 복구를 주장하지 않는다. Nebius와 OpenAI 기존 동기 HTTP/API·키·모델을 그대로 사용하고 새 inference 재전송/SDK/서버 저장 설정은 추가하지 않았다.

## 실제 구현

- 기존 AuditedChatTransport에 trusted host의 optional collection adapter만 연결. 기본 제품 transport/단일 dispatch fail-closed 정책은 그대로이다.
- 명시 `--collect-late-usage`: 시험 HTTP300초/같은 receiver900초/최대4. 타임아웃은 FAIL 고정·application token cancel, 연결은 receiver가 bounded 수집. 무제한 queue/재호출/late PASS 승격0.
- 같은 attempt ID·Execution ID의 dispatch/raw/validation + 별도 immutable timeout/settlement receipt. 수신 중에는 검증된 context+max-output 가격 최대예약을 전액 차감한다.
- 단일 live ledger owner와 짧은 O_EXCL transaction + thread RLock, 여러 pending 요청을 각각 보존. 다른 프로세스나 foreign lock 인수·삭제0. valid usage가 오면1회만 실제 토큰 가격 추정으로 정산한다. raw 먼저 durable 저장 후 장부 정산; 실패는 보호 중단.
- 수신되지 않거나 usage 없으면 full hold/UNKNOWN 유지. 실제 청구서 금액이 아니라 고정 단가에 따른 추정이다. 두 과거 .0764288 hold는 carry에 포함하며 자동 환급0.
- 후행 finish length/402/회계·원본 저장 실패도 다음 dispatch 전 중단. 비timeout UNKNOWN, 출력·동일역할5모델 연속근본실패, 시간/예산/입력·소스 SHA guard 유지.
- 시험 result/progress를 덮어쓰지 않고 수신 종료 후 별도 accounting-results/summary financial view만 계산. 생성/설계 품질과 후행 회계를 분리한다.

## 오프라인 검증과 원본 보존

관련64 unittest PASS: 새 receiver9 + 실제 sealed closed-prefix admission5 + timeout reporting/continuation/role controller/pricing/agent reliability 회귀. 앞34는64의 부분집합이다. fixture는 fake opener/인공짧은 지연이며 모델 성능 결과가 아니다. 최초 Windows Temp sandbox 권한 오류가 있었고, 시스템 ACL 변경 없이 권한 검토를 거친 fixture-only 명령으로 재실행했다.

핵심 재현: 시험 timeout 후 첫 요청이 아직 안 끝난 상태에서 다른 모델이 먼저 완료; 이후 첫 응답의 raw와usage가 저장되고 예약.0012→추정.00002로1회정산; 원FAIL/HTTP2(재전송0) 보존. 수신 상실/usage 누락·이중정산·예산 부족·foreign lock·원승인 만료·late length·기본 제품 single-dispatch 회귀 확인.

v411b 독립 integrityPASS/settlementUNRESOLVED 감사와 scope/summary/result SHA를 봉인했다. [seal](../../outputs/benchmark-evidence-report-20261011-v412/closed-prefix-seal.json) SHA `85981b7fe0de1c7001cfaab5d48d2b3759b65fb275117f50201fbfbd3a3295e0` · v411b736파일/older979파일 모두 검사 · skip98/미착수112 · 공유 Luna 관측3방 SHA 동일. 과거 실패/0HTTP admission은 다시 호출하지 않는다.

carry Nebius3.05355147/OpenAI1.81365030, 총USD5/provider 및2026-10-11 18:00KST 원기한 불변. 새source cohort 결과와 과거성적은 합치지 않는다. 실제 늦은 모델응답 회복, 남은 역할 전수, 새40k App/Isaac full journey, blind 사진품질/holdout/실물 인수는 아직 미검증이다. 로봇/배포/설치/시스템설정/commit/push/새agent0.

## 실제 재개

12:46KST 새 owner PID14728로 `outputs/benchmark-public-roles-20261011-v413` 미착수112를 실제 재개했다. scope SHA `dc044bdccba2e881e1bd3c16bedcf1f2bf85fc7fafb174ccc29911a9b218256f`. frozen source/Web/build·원입력·공유관측·평가기준 실행 중 변경0; 앞선9 receiver/5 seal admission 포함64회귀 및provider 전체339PASS(중복합산금지). 초기 GLM5.3Flash 실제 설계89.531초/4HTTP/계약PASS. native ACTIVE의 follow-up도 정확한owner/원기간·상한·timeoutreceipt 예외/후행 회계/최종 원감사·PDF·PAUSED를 저장했다. 이 기록은 진행 증거일 뿐 전체 종료/후행 응답 회복/whole App·Isaac·품질PASS가 아니다.

## 상위 deadline 경계 수정 v414

v413은23/112처리 후REMOTE_UNKNOWN으로 정상 종료했다. 실제19시험 중10계약PASS/9FAIL,0HTTP4·총73HTTP·89미착수. 원인: BudgetedPipeline의300초 wait_for가 collector의동일300초 wait_for보다 먼저 취소하여 collector timeout receipt 생성 경로를 타지 않았다. receiver 자체는 shield로 유지되었다. Gemma attempt `63292d793b21444eabe06dc5f2e3e571`은601.407초 후실제HTTP504/HTML로끝났고 rawSHA `c9c89d274726b86306e1c97d80360f820bce86042c34c9bb2487aac4ada6d606`/usage없음/.023full hold를 저장했다. 따라서 늦은 응답 수신은 실제확인, 늦은usage회복은 미검증이다. 원scoredFAIL/결과/장부를 덮어쓰거나 재호출하지 않았다.

코드 수정 전 외부 읽기전용 감사 `role-audit-413-closed.json`: integrityPASS/settlementUNRESOLVED, 원73HTTP/ExecutionID/raw/ledger/summary/후행receipt/원본SHA 결속. 최초 감사는504HTML을JSON으로강제파싱하여JSONDecodeError로실패했으며, auditor는 rejected non-JSON HTTP오류를 rawSHA/상태로 보존하도록 수정했다. 성공응답의invalidJSON은 여전히 거절하고usage/품질을 합성하지 않는다.750파일새sealSHA `09eb059f03ba595e725e239fb07f4d6d0ddeb3fddb09c0d3366e81ad3131c2c2`·원89미착수/carryN3.81467627/O1.82310740. 이전.0764288hold2개+이번.023을 모두 유지한다.

기존 BudgetedPipeline per-call 실패에실제timeout metadata만추가하고 host catch에서그 typed deadline을 같은 live collector/calls/ledger/attempt에 연결한다. 외부 취소/전체generation기한/foreigncall/수신없는deadline은예외로승격하지 않는다. 같은receipt는 중복작성하지 않고 후행usage정산이같은원FAIL을바꾸지 않는다. usage없는finished HTTP오류도예약/UNKNOWN이며 알려진scoredtimeout외에는 중단한다.

오프라인 실제경로 `run_case→GenerationService→BudgetedPipeline→AuditedChatTransport→collector`: 수정전 FAIL/REMOTE_UNKNOWN 재현, 수정후 FAIL은그대로/terminal_stop없음/같은receiver활성·timeoutreceipt검증·다른모델먼저완료·후행usage1회정산 PASS. receiver11PASS(앞9포함),provider전체339PASS,외부감사5PASS(합산독립점수금지). 최초Temp sandbox PermissionError도보존, 공식권한검토 fixture-only실행/시스템ACL변경0. 정확히121기시작skip/89미착수만새414admissionPASS/HTTP0; 공개사진3/Luna관측SHA/원seed/40k/HTTP300/12HTTP/3repair/1800s·각총5/18KST불변. 이후새모델전수·actualfullApp/Isaac·사진품질은실제증거확인전미완료.

13:18:40KST ownerPID9148로미착수89 실제재개, source scopeSHA `3a7d816b53ce481f828e63889ad5fa36ba71e72f15f1f5e720360b679e6a08b1`. Qwen235B37.265초/4HTTP REPAIR_STALLED, GLM5.3Flash270.828초/4HTTP계약PASS. 이는진행근거이며전수/후행usage/전체품질PASS가아니다. nativeACTIVE prompt도owner/새scope/원750봉인·knownhold3/carry/18KST/원감사·단일PDF·정확한잔여·PAUSED로실제동기화했다. frozen source/Web/build/설정/평가기준 변경0.

13:45:52KST 실제Qwen235B attempt `ab1a4fbfd71c4abeb693e07bfaebc941` per-call300초/동일receive900초/`deadline_origin=budgeted_pipeline_per_call` timeoutreceipt저장. 원trialFAIL/전체310.000초/2HTTP·terminal_stop없음, 이전응답 수신/최대예약.0764288이남은상태에서 다음GLM5.3Flash실제dispatch가시작되었다. 따라서 실제 timeout→다른모델시험을먼저이어가는경계수정은확인됐다. 이후원응답/usage도착·정산과전체종료는아직별도확인전미완료이며원FAIL을승격하지않는다.

## 최종 실제 수신 검증과 단일 보고서 v415

동결 source414의 owner9148은 `OUTPUT_LIMIT`로 정상 종료했다. 원89개 후속 슬롯 중30개 처리: **실제 모델시험23개(설계 계약PASS8/FAIL15), 호출 전 제외7, 미착수59, HTTP96(Nebius91/OpenAI5)**. 원controller의 FAIL21에는0HTTP admission6개가 포함되어 있으므로 모델실패15개와 분리했다. 무수정PASS3, 수정시험17개 중회복PASS5. original scored/progress/result는 불변이며 후행 정산은 accounting-results에만 반영했다. 단일 모델 실패 때문에 계획을 줄인 것이 아니라 명시된 출력 소진 보호가 발동했다. 추가 유료시험은0이다.

| 같은 요청의 실제 근거 | 시험 결과 | 후행 응답·비용 |
|---|---|---|
| Qwen235B `ab1a4fbfd71c4abeb693e07bfaebc941` | per-call300초 원FAIL 유지·다음GLM이 먼저dispatch | 601.141초 뒤HTTP504 HTML, usage없음, 최대예약USD.0764288유지. rawSHA `c9c89d274726b86306e1c97d80360f820bce86042c34c9bb2487aac4ada6d606` |
| GLM5.3Flash `27a818d61f834f45bf1bcfc8e2ddbbed` | per-call300초 원FAIL 유지·다음모델 먼저 진행 | 424.125초 뒤HTTP200/length, prompt7325+completion40000(reasoning40000)/최종문자0. 같은ID1회 추정 정산USD.02109875. rawSHA `1b3ce9c761a00a0e5f1488de5166519ef56762619775d4113ffa783ac9ee9a22` |
| Flash0731 `02011bb8d23e4d068459c168667f593f` | PROVIDER_OUTPUT_TRUNCATED/OUTPUT_LIMIT | 80.453초HTTP200/length, prompt8074+completion40000(reasoning40000)/최종문자0, 추정USD.01233036. rawSHA `c126825cb42617570539df3fc9b815284738dc357707815bb345053a174f71c1` |

GLM의 후행 length와Flash의length를 모두 보존했고 수신기는 정상cleanup/active0/fatalOUTPUT_LIMIT이다. 위lateusage는 실제 회수 근거이며 공급자 청구서 확인은 아니다. 받은504에usage가 없는 경우도0원으로 바꾸지 않는다. **총노출(과거사용·모든이월예약 포함) NebiusUSD4.52404747/OpenAIUSD1.83015270**, 이번source 추정+예약N.70937120/O.0070453, 이번heldN.0764288/O0. 이전named Qwenhold2개와Gemma504/.023도 원carry에서 보존했고 새예산/환급0이다.

독립 외부auditor를 종료 후 실행: integrityPASS/settlementUNRESOLVED(UNKNOWN_COST_OR_COMPLETION). `outputs/benchmark-late-usage-report-20261011-v414/audit.json`과actualIsaac 후재감사는 SHA가 동일하다(`12196ef486bc9e41438940f10686dbe44e3ece4cfb522ff4fc2f5df55f280a1f`). 원96HTTP dispatch/raw/ExecutionID/ledger/timeout·settlement/derived 회계 및 source/settings/input/공유관측을 결속했다. 과거413750파일/411b736파일/409979파일 봉인도 모두 검증했다. source414 code/build/asset527파일 ZIP SHA `64cbb151602d76d194f268ca2beb0fb9d547a91034ed71d8f758ca8a42372242`를 로컬에 보존했으며 키/계정설정/입력사진/raw는 ZIP에 없다.

안전한0HTTP 대안으로 현재PASS한 **같은식사공간의 Flash0731/MiniMaxM3/KimiK2.7Code/GLM5.3Flash 원plan4개**를 기존ProjectStore→App adapter→실제Isaac에Build/저장·재열기·1280×960 캡처했다. `outputs/benchmark-role-plan-render-20261011-v414/result.json` PASS_STATIC_REPLAY_ONLY/originals_unchangedtrue/provider0/robot0/Run0. scene revision/실제receipt/plan·frame SHA를 연결했다. 캐시쓰기·OmniCache/OptiX/DerivedDataCache 경고를 보존했고 삭제/ACL변경/권한우회/새설정 없이 실제캡처4개 완료/자체runtime 정상 종료했다. 경고 없는PC 전체 준비 또는 새LLM 전체경로PASS를 주장하지 않는다.

직접 시각검토는 **눈가림 품질점수가 아니다**. 실제 사진의 여러의자를 두 모델은`chairs`그룹1개로만만들었고, 다른 두모델은여러인스턴스를만들었다. 식기·유리재질·등의형상은 단순하다. 앞쪽회색unknown/occluded 영역은실제사진가구가아니라안전영역표시이다. 따라서 종류·지지·기하 계약PASS로 사진의객체수/정밀배치/photorealism을보증하지 않는다. 다음개선은사진특정4개강제값이아닌범용그룹/개수/개별인스턴스보존계약과표현라이브러리이며, 이번동결 source는수정하지않았다.

[최종 단일PDF](../../outputs/benchmark-late-usage-report-20261011-v414/report.pdf): **24쪽, 실제프레임9개(새414정적4+이전정적4+407실제이동UI1), 원사진 포함 총18이미지**, SHA `34f975f973eeed4c4c5d7819fa014ddeac1641afebd74100a65748ac1c26e236`. 관측409/설계411b/413/414를분리하고모든미호출·실패·수정회복·HTTP정상응답p50/p95·최종수신시간/추정/held·조건부추천·규정/미완료를기록했다. 전쪽Poppler렌더/구조검사/시각검토, 마지막가독성수정은동일18쪽PNG SHA확인+변경6쪽직접검토. 생성·검증의PowerShell foreach pipeline구문오류1건은0HTTP로보존 후정정했고모델FAIL로세지않았다. metrics-only JSON과감사/실제캡처를로컬저장, 원사진/개인prompt/raw/키를GitHub에업로드하지않았다. native`twinpulse` **PAUSED**를도구응답으로확인했다.

정확한 미완료/다음 순서:

1. 40k가전부추론으로소진되어final이없는원인: 공급자가지원하는reasoning설정/단계별작업과최종출력계약을새source에서일반형으로진단한다. 긴timeout/더큰cap만으로해결했다고표시하지않는다. 현재guard를풀거나새paiddispatch하지않는다.
2. 중단판단·새동결/유효승인후59미착수와7미호출의문맥/최대예약조건을재검토한다. 과거FAIL재호출은별도repeat로분리하고원59suffix·budgetcarry·원결과를덮어쓰지않는다. 모든TokenFactory모델2회actual완료가아니다.
3. 새40k 추천조합의사진/텍스트 ordinaryApp/API/Isaac currentrender→semantic현재plan/run·도착→별도movingStop/stable→reload/reset·닫힌reopen. 현재정적Build와옛407한사례로대체하지않는다.
4. 범용개별물체인스턴스보존·사진품질/지지/실측과독립blind라벨/holdout/역할독립·방단위paired비교. 실제방3개/개발선별만으로최적/일반성능우승주장금지.
5. 과거socket종료·504/no-usage 비용은공급자사용량/청구증거가있어야확정된다. 로봇OFF의실물재스캔·보정·안전정지·자율/Loop인수는별도현장승인이필요하다.
