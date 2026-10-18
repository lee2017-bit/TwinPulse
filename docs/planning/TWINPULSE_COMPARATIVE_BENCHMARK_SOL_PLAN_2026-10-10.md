# TwinPulse 모델 조합 비교 벤치마크 구현 및 시험 계획

작성일 2026-10-10 · 갱신일 2026-10-11 · 계획 버전 2.3 · 연결 기준 Baseline v1.0.411 · 상태 RUNNING_UNDISPATCHED_CONTINUATION

v2.3 현재: 사용자 명시승인에 따라 old UNKNOWN/.0764288을 fully carry한 미실행136건만 새v411b source로 재개했다. 원979개와시작74/중단Qwen 모두보존·재호출0·순서/caps/policy/공유관측 동일. carryN2.31278064/O1.81365030·각5/오늘18KST 불변, 새UNKNOWN/length/402/5모델동일실패는중단. 역할종료 원감사→안전gate/기한/잔액이허용한 실제photo·text ordinary App/Isaac→분모/source별정직한표와조건부추천·정확한잔여 순서. nativeACTIVE/owner8344, 결과/whole 미리PASS금지. [검증/초기admission결함/회귀87PASS](../verification/comparative-benchmark-overnight-20261011.md#명시-승인된-미실행-역할-재개-v411). 아래PAUSED는재개전이력.

v2.2 현재: v40974번째 설계의300초 timeout 뒤 raw-file race로 owner종료. [수정전 감사/수정검증](../verification/comparative-benchmark-overnight-20261011.md#타임아웃-후-집계-중단-수정과-부분-비교-v410), [35역할 전체표](../../outputs/benchmark-public-roles-20261011-v410-audit/metrics-only.md). 73보고·102HTTP·49역할PASS/11응답FAIL·13미호출/UNKNOWN1·미배정136이며 전체모델2회/actual전체인수 미완료. 소비자는raw완료를가정하지않고 예약/원timeout을보존하며 정상중단; host예외도interruption/부분보고를남기고재시도금지. 기존원본/한도/기한/UNKNOWN.0764288과N2.31278064 O1.81365030노출을보존, nativePAUSED. 미확정비용중단은 예산잔여/단순계속지시로무효화하지않는다. 다음유효한새범위판단에서도 미배정case를 새sourcecohort로동결하고이전성과와합치지않으며 관측/설계계약→actualApp/Isaac→독립품질의순서를유지한다. Flash·Luna관측각6/6은후보유지근거이지품질우열결론이아니다. 아래v2.1은당시진행이력이다.

v2.1 실행 순서: ①거절·출력 진단 및 명시40k 설정을 UI/API/manifest/ordinary wire에 결속(기본값/옛20k불변) ②Flash 동일공개입력 critic40k2회 계약시험(2/2PASS, 모두20k미만·한도 단독 원인 미입증) ③새현재카탈로그25/공개사진3 ×역할가능 모델(관측9+Luna/설계24+Luna)×2=210 역할선별. planner는 방별첫Luna관측을 같은고정입력으로 쓰며 정답이 아님; old private-fixture 실행 금지. 문맥≤40k 모델은 같은40k설정을 받을 수 없으므로 미실행사유 보존(성능FAIL아님), 공통요청300초/설계12HTTP·repair3·1800초, Nano/Lightning만기존no-thinking/Luna none/다른모델default. ④보호gate 통과 후 역할결과가 좋은 조합을 새 sourcefreeze·같은공개photo/text actual ordinary App/API/Isaac currentrender→현재semantic plan/run/거리→별도movingStop/stable→reload/reset/reopen으로 검증 ⑤관측계약/설계기하/전체기능/독립품질과 비용·미실행·원인을 분리한 metrics-only 보고. 이번 새 승인은 공개사진/렌더/텍스트만·기존노출 포함 각USD5·오늘18:00KST; 옛407승인/실패/held 변경 없음. 실행 중 source/설정 수정 및 동일 실패 재호출 금지. 출력소진/미확정비용/같은역할5모델동일실패 또는 마감이면 정상 중단하고 정확한 미완료를 보고한다. 전체모델2회/독립품질/globalwinner/실물 인수 완료를 미리 선언하지 않는다.

v2.0 현재: source40720actual/113HTTP·기능8PASS12FAIL40NOT_RUN·현재정산/cleanup완료/예약PAUSED, [원감사](../verification/comparative-benchmark-overnight-20261011.md)와 [비교·조건부선택·재사용](../benchmarks/comparative-pilot-20261011.md) 보존. 15번째length/20k는rejected metadata finish null로 gate누락하여후속5/37HTTP가추가됐고 모두원FAIL/비용에유지했다. 정상owner중단·편집전 frozen원감사report저장후 typed truncation 또는wirelength 양쪽gate수정·33PASS/실제savedstate STOP·새paid0. 각5/원기한/UNKNOWNheld불변·N1.34577603/O1.80602030. 관측photo2/text1 독립입력의부분pilot이며 예정photo3/text3완료·25전체모델·human품질/wholePASS를뜻하지않는다. 새승인/새cohort없는재개금지·옛source성적합산금지. 아래 진행문단은 이력이다.

v1.9 현재: 406actual2/11HTTP에서 semantic currentplan/actualrun 도착2를 확인했으나 복귀의 과거/새 chat문구 global locator 중복으로 wholeFAIL2. 원본감사와 정산/cleanup·부분report/ZIP 보존 후 현재 UI exactplan+Run활성만 readiness로 검사하는 e2e 범용 수정/Node8syntaxPASS. 407동결·동일조건60·원기간/5씩·carryN1.13080437/O1.75276130/UNKNOWNheld 불변. [근거](../verification/comparative-benchmark-overnight-20261011.md). 모델성적과 시험결함·기능과 인간품질은 구분한다.

v1.8 현재: 405의2host 실패로 이전 preview완료와 새 이동완료가 섞임을 재현했고 actual4/26HTTP 정산 후owner중단/부분원본감사보고서 보존. 현재request/cursor/text·routeevent·UIplan→runtime run/epoch/sequence·목표거리·실제movingStop/stable의 증거를 browser+auditor에서 검증한다. chatpending에는oldRun잠금/Stop유지, 전송전owner정상중단지원. Python101/Node8/Web52/type/buildPASS 후406 source동결·소규모actual smoke→같은60잔여순서를 실행한다. 모델문제와host문제분리·원실패/NOT_RUN/held/N1.11227037/O1.74196590carry·원5씩/기간불변. [증거](../verification/comparative-benchmark-overnight-20261011.md). 인간품질/통계전체우승/wholePASS는 미충족이다.

v1.7 현재: 실제 첫 사진블록5조합 중 FlashLuna만 기능전체PASS/4FAIL을 보존했다. text2응답·초안저장 뒤 사진용render기록 필수라는 시험 결함을 수정하고 같은60조건을405 source로 재동결한다. room prop 목표·currentID/storage 후보군·semantic거리 분리·99Python/Node6PASS. 이전UNKNOWN/held를 모두 새상한에서 차감하며 원기간/5달러씩 연장0. Text는 실제 two-stage planner/localgeometry로 관측모델 비교가 아니다. source/조건 수정 없이 일괄 actual 시험 후 재감사·모든 실패/NOT_RUN 분모·보조recall·시간/비용/방단위구간·조건부추천을 기록한다. 인간/blind정밀품질 미평가, qualifiedfull0/holdout아님/wholePARTIAL. [검증](../verification/comparative-benchmark-overnight-20261011.md).

v1.6 현재: [새 독립 입력 pilot](../verification/comparative-benchmark-overnight-20261011.md)은 공개 사진3·텍스트3/5조합×2이며 새8시간·공급자각USD5 승인 안의 actual App/Isaac 시험이다. 개발품질 보조 required-kind recall은 agent 사전 최소종류/명시 text 기준이고 인간/blind labels를 대체하지 않는다. 전체예정60/동일조건/paired균형·raw/실패/held유지·qualifiedfull0/holdout미시작·통계우승 주장금지. 최초 모델전 backend 카탈로그 복사 결함과 실제 dining table 목표 명칭 결함을 수정·8/22회귀·Node6PASS(겹침합산금지) 후 source404로 재동결했다. 이전2실행은 별도 cohort·누적비용/held에 포함. 진단CPU ON 공통/HTTP·진단모드wall만 비교하며 비계측 latency로 일반화하지 않는다. 아래 버전별 문단은 이력이다.

수신 대상은 후속 구현을 맡을 6.1 Sol이다. 목적은 사용자가 모델 조합을 선택하고 GitHub에서 그 선택의 근거를 설명할 수 있는 **TwinPulse 작업별 비교시험**을 만드는 것이다. 현재 단일 사진의 전체 경로 시험은 유용한 개발 근거지만, 사진 복원 품질이나 일반적인 모델 우열을 확정하기에는 부족하다. 제품 결함의 원인 구분, 독립 평가, 동일 조건 시험 도구를 먼저 보완한다.

v1.5 현재: [실행 환경과 독립 평가 결속](../verification/comparative-benchmark-code-preparation-20261010.md#실행-환경과-독립-평가-결속-v402)을 기존 제품 시험 경로에 연결했다. manifest1.2는 실행 환경·선택rubric·답안/provenance를 SHA로 고정하며 환경 변경을 비용/키 경계 전에 차단한다. 실행 전후 증거는 원본 감사와 collector가 검사한다. 실제 로컬 source/asset520개·runtime9개·Burger9개·원39SHA 불변/HTTP0; 관련105/Core302/Provider332 PASS다. 빈 worksheet 생성은 사람 정답 확보가 아니며 독립 데이터0이다. 사전 답안 없는 holdout은 시작하지 못한다. **runtime 진입 파일과 reviewed 자산만 동결했고 설치 전체 DLL/wheel/extension·GPU/driver는 미동결/미관측이다.** 다음은 독립 data/권한·사람 labels/blindreview·최종rubric, 환경 비교범위 관측, 새 유효 승인 actual smoke/holdout이다. 실제 LLM/Isaac 성적을 늘리지 않았고 독립repair/critic 라우팅도 남는다. 아래 버전별 문단은 이력이다.

v1.0은 계획만 작성했다. v1.1에서 목표 오류 분류·배치 탐색 진단과 manifest/실패 분모/통계 기반을 추가했고, v1.2에서는 parent+drape 경계의 범용 결함을 수정하고 원 patch 진전·rollback을 대조했다. 별도 manifest campaign controller와 독립 annotation/matching/품질 evaluator, 원 raw 재감사→collector CLI→공개 exporter를 기존 ordinary 경로에 연결했다. [현재 코드·회귀·정확한 잔여](../verification/comparative-benchmark-code-preparation-20261010.md#후속-구현-결과-v399). Provider327/Core302/관련 benchmark·App 라우팅·승인95/Node2 PASS(중복 합산 금지), 저장 실패3건·원본192 SHA 불변/HTTP0이다. B0 이번 확인결함/오프라인 인수는 통과했지만 B1/B2 전체는 PARTIAL이다. 미지원 역할 모델·기대 거절 adapter, 인간 labels/rubric, actual 새명세 smoke/runtime/profiler/holdout이 남는다. 추가 모델 호출·새 데이터 외부 전송·Isaac·로봇은 실행하지 않았다. 기존 제품 PARTIAL / whole=false와 예약 PAUSED, 이전 유료 사용량·예약·실패·승인 마감은 유지한다.

v1.3 이력: [CPU 교정·지원표·분모 보호](../verification/comparative-benchmark-code-preparation-20261010.md#프로파일-교정과-결과-분모-보호-v400)를 구현·오프라인 검증했다. owner-thread profiler/원 후보2개 재컴파일·39원SHA 보존, legacy/비정상/불완전 계측 제외, instrumented 오버헤드와 OFF wall/HTTP 분리를 확인했다. 예상 거절·질문은 도달 성공률에서 분리하고 예정별 adapter 지원 사유를 공개했다. Provider327/Core302/Web445/benchmark76 PASS(겹침합산금지), type/build PASS. 당시 all-model/진단 adapter 잔여는 아래 v1.4로 갱신한다.

v1.4 현재: [모델 카탈로그와 진단 과제 연결](../verification/comparative-benchmark-code-preparation-20261010.md#모델-카탈로그와-진단-과제-연결-v401)을 구현했다. 저장 Nebius25모델→관측9/설계24 ordinary gateway/InputRevision 계약, manifest1.1·격리 라우팅·승인 가격/scope 장부·실행 감사가 오프라인 검증됐다. 새 역할/가격/계정 가용성은 actual 시험 직전에 대조한다. App의 현재 질문/typed 거절 이벤트와 browser 증거→독립 diagnostic 판정·collector/accounting1.2도 연결했으며 arrival/fullPASS로 합산하지 않는다. Core302/Provider332/Web445/관련144·30/Node4/type PASS(겹침합산금지)·39원SHA 불변. **독립 데이터/인간 labels·rubric, 전체runtime/asset freeze, 새 actual photo/text 및 진단 Isaac smoke, holdout은 여전히 미완료다.** repair=planner/critic=observer 상속만 구현됐고 독립 역할 조합은 별도 작업이다. 기존 실패·장부·wholefalse/예약PAUSED 유지, 새HTTP/Isaac/로봇0이며 종료된 옛 grant를 재사용하지 않는다.

## 1 사용자 의도와 주장 범위

> 뭐가 최적인지, 어떤게 성능이 좋은지에 대해 주장할만큼 근거자료가 될 수 있으면 좋을거같은데? 그정도로 할 수 있는 테스트계획을 다시 짜봐. 코드 추가수정이 필요한상황인가?

기존 요구도 유지한다. 사진 또는 텍스트로 식별 가능한 파라메트릭 3D Twin을 만들고, 잘못된 생성은 자동 검사·수정·되돌림을 거쳐 저장한다. 일반 채팅 App에서 실제 Isaac 시연·Stop·재열기가 연결되어야 한다. 추정 방 크기가 실측과 다르다는 이유만으로 실패시키거나 특정 침실의 정답 배치를 주입하지 않는다. 이후 LiDAR 보정과 실물 승인 단계는 별도 인수다.

이번 1차 모집단은 **가정집 실내의 근사 Twin 생성과 제한된 SIM 작업**이다. 침실·거실·작업방을 포함한다. 창고·공장 성능, 실측 복원 정밀도, 실제 로봇 안전성과 전체 12단계 데모 완료는 이 결과로 주장하지 않는다. 해당 도메인은 별도 데이터와 동일 절차로 확장한다.

발표 가능한 결론은 다음처럼 한정한다.

- 명시된 데이터·제품 버전·시간/토큰/수정 예산에서 비교한 후보 중 품질 충족 전체 경로 성공률이 가장 높았는가.
- 품질 차이가 실무적으로 작다고 확인된 후보 중 비용 또는 완료 시간이 유리한가.
- Nebius 및 NVIDIA 사용 제약을 충족하는 후보 집합에서는 어느 조합이 유리한가.
- 이미지 관측, 설계, 자동 수정 중 어느 단계가 성능 차이와 연관되는가.

전체 모델 세계의 보편적 최적 조합을 주장하지 않는다. 후보 선별에서 제외한 모델은 전체 경로 열등성이 입증된 것으로 표시하지 않는다. 유의미한 차이가 확인되지 않으면 `INCONCLUSIVE` 또는 여러 유력 후보로 보고한다. 통계적으로 차이가 안 보인다는 사실만으로 동등하다고 선언하지 않는다.

## 2 현재 근거와 재사용할 구현

근거: [현재 공개 표](../benchmarks/model-combinations-20261010.md), [실행 기록](../verification/model-combination-benchmark-20261010.md), [기존 기하 수정 계획](TWINPULSE_GEOMETRY_REPAIR_TO_DEMO_SOL_PLAN_2026-10-09.md).

| 확인 사실 | 비교 해석 |
| --- | --- |
| 전체 19 actual 시험, 129 HTTP, 8 PASS·11 FAIL, 별도 0-call preflight 1건 | 서로 다른 코드 버전의 개발 이력이다. 전체를 한 순위로 합치지 않는다 |
| 최신 inference SHA `64289a04a616`의 13건, 전체 경로 PASS 5건 | 같은 코드의 제한된 통합 시험 근거 |
| 최신 Luna/Lightning 2/2, Flash/Luna 1/2, Luna/Luna 2/5, Qwen/Lightning 0/2, Flash/Lightning 0/2 | 횟수 불균형, Qwen의 402 포함, 단일 사진이므로 확정 순위가 아니다 |
| 같은 사진·첫 사용자 문구·20k 출력·300초 요청·900초 활성시간·수정3·HTTP24 | 공통 자원 정책은 있지만 provider 파라미터와 실제 생성 난도까지 같다는 뜻은 아니다 |
| 성공한 Luna/Lightning 저장 9·10개, 다른 관측 결과는 20개 이상도 존재 | 물체 수는 정답 수가 아니다. 누락이 쉬운 성공으로 보이는 평가 편향을 보완해야 한다 |
| 모든 전체 PASS의 최종 critic은 `uncertain` | 근사 초안/SIM 통과이며 독립 사진 품질 PASS가 아니다 |
| 실제 수정 후 저장·현재 Isaac 렌더·PhysX 도착·Stop·재열기 성공 사례 있음 | 실제 제품 경로와 수정 기능을 재사용한다. mock부터 재구축하지 않는다 |

이미 존재하는 공통 실행 ID, attempt/span, 송신/응답/검사 원본 SHA, 단계 시간, 비용 장부, 불명 청구 예약, checkpoint, typed patch, scope 확대, 되돌림, 현재 후보의 렌더 결속, App/SIM 실행 도구는 유지한다. 별도 유료 관측 서비스나 새 에이전트 프레임워크는 필요하지 않다.

## 3 선행 코드 작업과 완료 조건

### B0 배치 및 목표 실패의 원인 구분

현재: 알려진 거절/내부오류 분리, 실행ID 진단, 탐색 종료 원인·작은 독립 격자 대조, generic attachment 경계 수정과 원 patch 적용/진전/rollback 대조를 오프라인 검증했다. 원 packing 후보는 한도/빈 domain의 typed 실패, 원 목표는16후보14blocked/2no-path로 보존한다. 이번 확인결함 범위는 통과했지만 보수적 envelope와 제한 solver가 모든 가능한 형상/연속 공간을 해결한다는 뜻은 아니다. 예산·물체·안전 조건을 바꾸거나 원 모델 FAIL을 새 회복으로 기록하지 않았다.

`packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py::_bounded_region_repack`에는 이미 되돌림 탐색이 있다. 현재 10cm 격자, 최대512노드, 2초, 분기32개를 사용한다. `PHOTO_LAYOUT_REGION_FULL`은 제한 탐색의 실패이며 연속 공간 전체의 배치 불가능 증명이 아니다. 이 제한 자체를 결함으로 단정하거나 무조건 늘리지 않는다.

1. 원 실패 후보를 변경 없이 재생한다. 기존 greedy 단계와 fallback 각각의 후보 수·빈 domain·가지치기·실제 종료 조건·소비시간·노드를 같은 실행 ID로 기록한다. 노드/시간/분기 제한과 실제 탐색 공간 소진을 구별한다.
2. 특정 침실과 무관한 작은 문제를 만든다. 알려진 해가 있는 배치, 초기에 잘못 놓았지만 되돌리면 해결되는 배치, 명시 치수 내 불가능한 배치, 추정 크기 변경으로만 가능한 배치, 격자 사이에만 해가 있는 배치를 포함한다. 작은 유한 격자는 독립 완전탐색과 대조하되 그 결과도 해당 격자 범위의 증명으로만 쓴다.
3. 모델 수정이 요구된 범위를 바꾸었는지, 실제 적용 후 상태가 달라졌는지, 정상 물체가 보존됐는지, 실패 rollback 이후 최신 진단이 연결됐는지 확인한다. 수정 횟수 증가만을 진전으로 세지 않는다.
4. 재현으로 확인된 오분류·탐색 구현·수정 적용 오류만 먼저 고친다. 정상적으로 예산이 끝난 경우는 별도 코드로 남긴다. 더 큰 탐색 예산은 개발군에서 자원 곡선을 비교하여 결정하고 최종 시험 전에 동결한다.

`packages/twinpulse_core/src/twinpulse_core/simulation_goal.py::goal_review`는 목표 외곽16개 접근 후보의 planner `ValueError`를 넘기고 마지막에 `SIM_TARGET_NO_REACHABLE_APPROACH`를 반환한다. 알려진 경로 거절과 예상 밖 내부 오류를 구별하고, 후보별 원인·현재 scene/start/footprint를 기록하도록 보완한다. 내부 오류를 조용히 경로 없음으로 합치지 않는다.

목표 접근 실패도 유효한 결과다. 실제로 막힌 방을 열어 보이도록 물체를 삭제하거나 collider·로봇 크기를 줄이지 않는다. 알려진 도달/비도달 장면으로 판정기를 검증하고, 사용자가 요구한 목표의 접근성은 생성 품질과 별도의 필수 작업 지표로 연결한다. 관측 기반 장애물 위치를 임무 성공을 위해 임의 변경하지 않는다.

관련 변경 지점: 위 두 파일, `repair_scope.py`, `budgeted_pipeline.py`, 기존 `test_generic_photo_policy.py`·기하/rollback 회귀·SIM goal 회귀. 이미 해결된 v384–v388 결함을 새 미구현으로 다시 만들지 않는다.

**완료 조건:** 원 실패 재생의 typed 원인, 범용 양성·음성 검사, 적용 전후/rollback 근거, 관련 회귀가 확보되어야 한다. 모든 실제 후보가 성공할 필요는 없다. 공통 host 결함이 여러 모델을 잘못 실패시키는 상태로 본시험을 시작하지 않는다. 저장 응답 재생 성공은 새 LLM 성공으로 집계하지 않는다.

### B1 선언형 시험 명세와 같은 조건 실행

현재: 명세/prepare CLI·입력/정답 격리·사진2/text2·균형 순서·소스 freeze·기존 ordinary/verify/browser 연결에 별도 manifest campaign controller를 더했다. 인간 승인/공급자별 상한·기존노출·held·paired budget·UTC 만료/HTTP 직전 검사·명시 재개감사·역할별5모델 중단을 파일 경로 회귀로 검증했다. manifest1.1 동결 카탈로그의 역할/문맥/가격/출처·만료 SHA를 ordinary 경로에 연결했고 App 질문/거절 증거 adapter를 추가했다. 저장 목록의 모든25모델은 지원/제외 사유를 유지하지만 생성 가능 역할의9관측/24설계만 로컬 계약을 통과했다. 미지원 구성이 섞인 manifest는 admission을 막으며 모델 대체/실패 삭제를 하지 않는다. actual 직전 metadata·계정 가용성 대조와 실제 새명세 smoke 인수, 독립 repair·critic 라우팅은 남는다. 명세의 전송 가능 표시는 금융 실행 승인이 아니고 종료된 옛 grant를 재사용하지 않는다. 비싼 모델의 보수 예약이 공통 trial cap을 넘으면 NOT_RUN으로 남긴다. 다음 cohort의 공통 cap과 인간 승인을 먼저 확정한 뒤 시험해야 한다.

다음 기존 도구를 확장한다.

- `scripts/compare_model_roles_live.py`: 단일 사진/공유 관측 상수 대신 승인된 case manifest를 입력받는다.
- `scripts/run_model_combination_benchmark.py`: 고정 `PAIRS`, 단일 캠페인 순서 대신 동결된 config·case·repeat·schedule을 받는다.
- `scripts/run_ordinary_staged_live_ten.py`: 특정 사진 SHA 고정 검사는 일반화하되 **승인된 입력 SHA 검사 자체는 유지**한다. 사진 없는 text case도 같은 예산·감사 경로를 쓴다.
- `scripts/verify_chat_sim_journey.py`와 `apps/twinpulse-web/e2e/chat-sim-journey.mjs`: 입력·일반 UI 행동·목표를 명세에서 읽는다. 침실/bed 전용 성공 조건을 일반 목표/기대 거절로 확장한다. actual lane에서는 고정 응답·과거 후보 주입이 금지된다.
- 기존 audit/export 도구: 실행된 설정에서 조건 표를 생성한다. 보고서의 고정 문구를 수작업으로 바꾸어 실제와 다른 조건을 쓰지 않는다.

명세는 최소한 다음을 가진다. 새 CLI 이름은 구현 시 확정하며 아래는 데이터 계약이다.

| 구분 | 필수 항목 |
| --- | --- |
| 입력 | dataset/version/case/room_group/split, photo 또는 text, input SHA, 원문 SHA, 출처·라이선스·전송 범위 |
| 기준 답안 | annotation SHA, visibility/unknown, 평가 대상 relation·요구사항, 실측 또는 추정 여부. 평가 전용 경로로 격리 |
| 조합 | config ID, 정확 provider/model ID, observer/planner/repair/production critic 역할, sampling/reasoning/출력/시간 설정 |
| 실행 | code·prompt·schema·compiler·library·evaluator 버전, repeat, schedule seed/block/order, engine·hardware 환경 |
| 목표 | 대상 선택 규칙, 시작점 규칙, 기대 도달/거절, waypoint/Stop/reload 절차, 실행 한도 |
| 승인 | 별도 campaign 승인 ID, provider별 비용 한도·기존 노출 차감, 입력 및 파생 렌더 전송 대상, 만료·중단 조건 |

기준 답안은 제품 모델 prompt·repair feedback·UI에 주입하지 않는다. SHA 검사는 전송 범위를 지키는 용도이며 특정 사진의 성공 답안을 고르는 분기가 아니다. 사례별 결과 디렉터리와 예산은 격리하고 사용자 전역 설정은 변경하지 않는다. manifest 검증/비용 견적/보고서 명령은 inference 0회여야 한다.

**완료 조건:** 최소 사진2건·text2건을 오프라인으로 검증해 입력 누출/교차 혼입 0, 순서 재현, 시작/종료 SHA 대조, 다른 버전/정책의 분리 집계, 예산 부족 시 NOT_RUN 유지, 재개 시 원 실패 보존이 입증된다. fixture 테스트와 actual lane 표시는 강제 분리한다.

### B2 독립 품질 채점과 실패 단계 기록

현재: 전체 분모·감사/미평가·실패 비용·held·fixture/replay 격리·방 단위 paired 통계에 독립 annotation/rubric·일대일 semantic matching/장애물/배치/지지·unknown 크기/occlusion·blind current-frame 품질 evaluator를 연결했다. 원 raw/wire/ledger 재감사→collector CLI→공개 whitelist JSON/Markdown·split/modality 분리·가족alpha를 오프라인 파일 회귀로 검증했다. 실제 독립 데이터·인간 labels와 blind 시각 판정·평가자 일치도/임계값 동결, actual fresh 수집 인수는 남는다. 생산 critic의 uncertain과 엔진 연결을 독립 품질 PASS로 대체하지 않는다.

현재 `render_review.py`의 production critic은 자동 수정에 계속 사용한다. 그 critic은 모델 조합의 일부이며 벤치마크 최종 채점자로 간주하지 않는다. 독립 채점은 동일한 답안·규칙을 모든 조합에 적용하고 결과를 제품 수정 루프에 돌려주지 않는다.

기존 `public_summary`는 주로 actual 요청이 있는 감사 통과 시험을 집계한다. 새 요약은 예정·시작·provider응답·생성·품질·렌더·SIM·저장·재열기 각각의 분모를 기록한다. 감사 실패·평가 미완료가 조용히 사라지지 않아야 한다. 독립 evaluator/report 모듈은 scripts 또는 시험 전용 package에 두고 제품 core에 비공개 답안을 넣지 않는다.

**완료 조건:** 물체 누락으로 쉬워진 PASS, 내부 critic의 uncertain, 렌더 미도달, 402, timeout, 출력 잘림, 감사 실패, 실제 목표 비도달을 의도적으로 넣은 오프라인 예제에서 각 점수와 분모가 예상대로 나온다. 실패 비용도 비용 대비 성공 지표에 포함한다.

v1.4 추가: expected outcome별 집계·양성/진단 분모 보호와 예정별 eligibility 사유 표를 유지한다. App 질문/typed거절→browser before/after·request/scene/event·case/goal SHA→판정 증거→raw auditor/collector의 diagnostic PASS 경로를 오프라인 검증했다. 증거 없는 PASS·내부 오류·예산 소진·위치 상실·추가 Run은 정상 보호 결과가 아니다. 실제 새 Isaac 브라우저 인수는 NOT_RUN이다. diagnostic 의미 목표 도착/움직이는Stop은 NOT_EVALUATED이고 fullPASS·arrival통계에 합산하지 않는다. 지원표는 공급자 account availability 검사가 아니다.

### B3 실제 제품 경로와 계측 고정

현재: CPU 계측의 thread 혼입 원인 수정과 중첩/재귀/대기/동시/원 후보 교정은 오프라인 통과했다. 계측 오버헤드 및 짧은 CPU 양자화 때문에 ON 값을 모델 속도 순위로 쓰지 않고 OFF wall/HTTP를 사용한다. 기존 비정상/legacy 원본은 유지·순위 제외한다. manifest1.2에서 제품/runner 코드·reviewed Burger closure·runtime 진입 파일·host와 PC package metadata·선택 평가표의 결속을 검증했다. 전체 설치 의존성 byte closure와 GPU/driver는 아직 미동결/미관측이며 새명세 actual photo/text 및 진단 Isaac smoke도 NOT_RUN이다. 공개 보고서는 진입 파일 동결을 전체 runtime PASS로 표시하지 않는다.

관련 회귀와 기존 App build/type 검사를 실행한 뒤 일반 제품 경로에서 사진 및 text 각각 소규모 smoke를 한다. 실제 모델/Isaac smoke는 실행 당시 유효한 승인 안에서만 수행한다. 고정 응답 테스트만으로 actual readiness를 승인하지 않는다.

함수 CPU profiler의 `self > cumulative`가 남은 기록은 계속 제외한다. 함수 병목 순위를 발표하려면 먼저 알려진 CPU 작업·대기 작업·중첩 함수·동시 작업으로 timer를 교정한다. 모델 비교의 wall/HTTP 단계 시간은 CPU 지표와 분리할 수 있으므로 CPU profiler를 전면 개편하느라 시험을 무기한 지연시키지 않는다.

제품/runner/평가 기준 변경이 끝나면 파일별 SHA manifest를 동결한다. inference 코드만의 SHA가 아닌 UI·engine adapter·asset·goal/evaluator·prompt·wire schema까지 범위를 명시한다. dirty 작업은 보존하며 commit/push는 필요하지 않다. 테스트 도중 코드가 바뀌면 새 cohort로 분리하고 동일 조건 비교에 필요한 후보를 함께 재시험한다.

## 4 데이터와 정답 준비

현재 독립 데이터 확보는0건이다. `scripts/prepare_benchmark_evaluation.py --manifest <manifest.json> --rubric <rubric.json> --output <새 worksheet 폴더>`는 입력 SHA에 결속된 빈 답안·사람 검토 provenance 초안을 만들 뿐, 물체·관계·실측·검토자를 채우지 않는다. 사람이 검토한 답안의1.0 schema/coverage/검토자와 provenance SHA·입력/rubric/답안 결속을 동결해야1.2 holdout admission이 열린다. source=`human`은 attestation이며 신원 증명이 아니고, 1인 검토는 2인 독립 평가가 아니다. 답안 없이 실행한 개발 smoke와 최종 품질 채점은 분리한다. 같은 text input은 같은 room group으로 묶고 paraphrase/crop/합성 family 누출은 수동 검토한다. 현재 `package-v402-r2`의 자가작성 계약 text2·임시 평가표는 본시험 dataset/rubric으로 승격하지 않는다.

현재 침실 사진은 이미 여러 번 수정·선별에 사용되었으므로 `development`에 고정한다. 최종 holdout에 넣지 않는다. 실제 사진의 관측 가능한 물체·관계와 합성 장면의 정확한 3D 좌표는 별도 기준이다.

| 묶음 | 제안 수량 | 용도 |
| --- | ---: | --- |
| 개발 사진 | 독립 방 8개 | 단순/복잡, 가림, 다수 작은 장애물, 다양한 지지 관계. 기존 침실은 이 안에 포함 가능 |
| 개발 text | 독립 설명 4개 | 사진 없이 생성, 명시 치수, 추정 치수, 모호한 목표의 질문/거절 |
| 최종 사진 | 새로운 독립 방 30개를 시작 설계로 사용 | 침실·거실·작업방 각10개, 각 유형 내 단순/혼잡 균형. 최종 N은 8절에서 동결 |
| 최종 text | 새로운 독립 설명 12개 | 명시/미지정 치수와 목표·지원 관계·장애물 요구를 고르게 배치. 사진군과 별도 보고 |
| 진단용 기하/수정 문제 | 범용 family 최소8종 | 명백한 지지 오류, 경계 침범, pack 순서, 무변화·악화·rollback, 도달/비도달 등. 실제사진 성공률과 합산 금지 |

사진30개는 같은 방30장이라는 뜻이 아니다. 같은 집·방·원본의 crop·회전·여러 시점은 같은 group으로 묶고 개발/최종 간 누출을 막는다. 실질적으로 같은 구조의 합성 seed도 한 family로 묶는다. 라이브러리가 지원하지 않는 항목은 사전 범주화하고 임의 제외하지 않는다. 지원 밖 도메인은 별도 확장 시험으로 공개한다.

데이터가 아직 확보된 것은 아니다. 사용자가 30장을 새로 찍어야만 하는 계획으로 만들지 않는다. 전송·재현·공개 이용이 허용된 공개 실내 자료 또는 사용자가 승인한 추가 자료를 검토해 manifest에 출처/권한을 기록한다. 이 문서 작성은 사진 수집이나 외부 전송 승인이 아니다. 확보가 부족하면 작은 데이터 파일럿이라고 보고하고 범위를 넓혔다고 주장하지 않는다.

실측 없는 사진의 10×12m 추정을 임의 정답 치수와 비교하여 FAIL 처리하지 않는다. 명시 치수가 있는 case에서만 수치 준수를 평가한다. 절대 미터 오차를 주장하려면 실측 또는 별도 known-3D 합성 집합이 필요하며, 합성 성적은 실제 방의 정밀도로 옮겨 쓰지 않는다.

## 5 평가표와 성공 정의

최종 주 지표는 사진군과 text군 각각의 **품질 기준을 충족한 전체 경로 완료율**이다. 연속 품질 점수와 단계별 통과율도 함께 공개한다. 임의 가중 총점 하나로 품질 부족을 빠른 속도와 상쇄하지 않는다.

### 공통 독립 답안

사진에서 확인 가능한 semantic entity 단위로 category·위치 관계·지지 parent·가림·확신도를 기록한다. 침대의 부품20개를 물체20개로 세지 않는다. 동일 범주의 여러 물체는 ID 이름이 아닌 관측 근거·위치의 일대일 대응으로 채점한다. 작은 반복 물체의 묶음 규칙도 사전에 정한다.

가능하면 두 사람이 모델 이름과 비용을 보지 않고 답안을 작성/검토한다. 두 평가자의 일치율과 불일치 adjudication을 남긴다. 기준 답안은 본시험 출력 열람 전에 고정한다. 결과에 맞춰 정답을 바꾸지 않으며 명백한 라벨 오류를 정정해야 하면 모든 조합을 동일한 새 evaluator 버전으로 재채점하고 전후 결과를 남긴다. 사람이 한 명뿐이면 그 한계를 공개하고 독립 2인 평가라고 쓰지 않는다. LLM judge는 보조로 쓸 수 있지만 단독 정답으로 승격하지 않는다. 사용한다면 모든 후보에 같은 judge/버전/rubric, 익명 결과, 순서 교환 검사와 사람 대조를 적용한다. 추가 judge 호출도 별도 비용/전송 승인에 포함한다.

| 축 | 실제 측정 | 실패·불확실성 처리 |
| --- | --- | --- |
| 물체 인식/보존 | 독립 답안 기준 precision/recall/F1, 큰 가구와 작은 바닥 장애물 별도, 원관측→선언→최종 손실 | 독립 답안에 없는 추측은 hypothesis 표시. 명백한 누락과 가림을 구분 |
| 공간 배치 | 확인 가능한 좌/우·앞/뒤·인접·상하 관계의 정확도, 관계 종류별/방별 macro 평균 | 단일 사진에서 모르는 깊이·가려진 면은 N/A, 채점 가능한 비율도 보고 |
| 지지 관계 | 바닥/표면/벽/천장/걸림/덮임과 parent 일치, 떠 있음·침범·부모 순환 | 소프트 시각 불확실성과 명백한 기하/물리 모순을 구분 |
| 식별 가능한 3D | 동일한 고정 카메라 묶음에서 침대·옷장·옷걸이 등 분류 가능성, library ID·치수·부품 연결 | 네모 proxy만으로 3D 외형 품질 PASS를 만들지 않음. 2D 요약은 별도 |
| text 준수 | 명시한 물체·수량·치수·관계·수정 요구 충족률, 근거 없는 추가 항목 | 사진 요구 없이 수행. 미지정 값 추정은 허용/표시 |
| 실제 경로 | 일반 채팅→생성/수정→저장→현재 Isaac frame→자연어 목표/Run·도착→Stop·재열기 | 중간 생성 PASS와 전체 PASS를 분리, 목표를 누락하면 성공 아님 |
| 자율 수정 | 초기 오류/종류/수정수/최종회복, 정상 항목 회귀, rollback·예산 종료 | 자연 오류 회복과 주입 오류 회복의 분모를 분리 |
| 비용과 시간 | 성공·실패 전체 사용량, provider별 USD 추정/예약, 성공 완료시간/실패 종료시간/HTTP·host·engine 단계 | 실패가 빨리 끝나는 조합을 가장 빠른 조합이라고 하지 않음 |

본시험 전 개발군에서 rubric을 검토해 수락선을 동결한다. 출발 제안은 semantic entity F1 0.80 이상, 확실히 보이는 바닥 장애물 recall 0.90 이상, 평가 가능한 배치/지지 관계 정확도 0.85 이상, 명백한 기하 모순 0이다. 이 수치는 TwinPulse 근사 초안 비교를 위한 **제안값**이며 공인 기준·실물 안전 기준이 아니다. 관계 수가 적으면 분자/분모를 함께 보이며, 평가 불가를 만점 처리하지 않는다. 명시 치수 준수 허용오차와 외형 채점 등 나머지 기준도 개발군에서 명시한 뒤 변경 금지한다.

실제 기능 경로 성공에는 현재 보호 조건과 기존 도착≤0.04m·Stop 후 정지 확인·동일 revision 저장/재열기를 유지한다. 최종 품질 답안이 준비되지 않은 결과는 `QUALITY_NOT_EVALUATED`다. production critic의 `uncertain`는 그대로 보존하되 독립 평가로 관측 가능 항목을 판단한다. 불확실한 절대 크기만으로 근사 초안을 탈락시키지 않는다.

## 6 단계별 모델 시험

### 1차 역할별 선별

실행 시점의 계정 가용 모델/정확 ID·지원 입력·출력 계약을 snapshot으로 남긴다. 과거 모델 수를 현재 전체 목록으로 복사하지 않는다. 이미지 지원 모델과 설계용 텍스트 모델, embedding/reranker/audio 등 범위 밖 모델을 구별한다. 지원하지 않는 계약·권한·context 한도는 `INELIGIBLE` 이유로 공개한다.

- 이미지 역할: 사전 선정한 개발 사진4개 × 모델마다2회. 같은 image bytes·사용자문구·canonical 관측 계약을 사용하고 독립 답안으로 채점한다.
- 설계 역할: 동일한 개발 case4개 × 모델마다2회. **모든 설계 모델에 동일한 검토된 관측 입력**을 주어 이미지 모델 영향 없이 설계·수정을 비교한다. 이 oracle-observation 성적은 자연 전체 경로 성적으로 집계하지 않는다.
- 기본 선별량은 이미지 모델 V개, 설계 모델 T개일 때 `8V + 8T` stage jobs다. job에는 여러 HTTP가 있을 수 있다. 모델2회가 서로 다른 입력 두 개를 뜻하지 않도록 case/repeat를 분리한다.
- 5개의 서로 다른 실제 모델이 연속으로 같은 근본 코드에서 실패하면 추가 호출을 멈추고 공통 원인을 분석한다. 조합5개와 모델5개는 다르므로 현재 pair 기준 중단기와 role 기준 중단기를 구별한다.

후보3개를 골라 동결한다: 제약 충족형, 비용/품질 균형형, 제약 없는 품질 우선형. 현재 Luna+Lightning, Nebius image+Lightning, Luna+Luna는 후보일 뿐 승자로 미리 고정하지 않는다. 세 유형이 같은 조합을 고르면 다음 Pareto 후보를 비교군으로 포함한다. 선정 규칙은 개발 성적만 사용하고 탈락 이유를 공개한다. 모든 Cartesian 조합을 자동 실행하지 않는다.

### 2차 실제 전체 경로 비교

시작 설계는 `새 사진30방 × 후보3 × fresh 반복2 = 180시험`, 별도로 `새 text12 × 후보3 × 반복2 = 72시험`, 합계252시험이다. **252는 HTTP 호출 수가 아니다.** 최종 N과 비용은 본시험 전에 확정하며, 자원에 맞지 않으면 표본/주장의 범위를 축소한다.

모든 조합이 동일한 case와 반복 수를 받는다. `(case, repeat)` 안에서 후보 순서를 seed로 섞고 실행 위치와 시간대가 한 모델에 치우치지 않게 균형을 맞춘다. 같은 host에서는 actual Isaac 시험을 직렬 실행한다. provider load·시간대·warm/cold 상태를 기록한다. 워밍업은 별도 사례와 비용으로 남기고 본시험 표본에서 제외한다.

각 시험은 fresh 일반 App 승인 및 실제 요청으로 시작한다. 최종 모델 비교에는 공유 관측 캐시나 성공한 저장 후보를 재사용하지 않는다. 실행 중 개발자가 결과를 고쳐 넣거나 편한 시작점·목표로 바꿀 수 없다.

목표는 정답 집합에서 미리 지정한 semantic target을 일반 사용자 문구로 요청한다. 생성 결과가 그 물체를 빼먹으면 실패다. 목표/시작 배치 규칙은 모든 조합에 동일하고 source viewpoint·주어진 entrance 등 사용 가능한 정보만 활용한다. 결과마다 가장 쉬운 목표를 고르지 않는다. 원점이 막히거나 적법한 시작점을 찾지 못하면 그 상태를 기록하며 숨은 teleport로 통과시키지 않는다.

경로 길이에 따라 주행시간이 달라진다. 공통 bounded SIM 시간 내 완료 가능한 과제 분포를 개발군에서 정하고 동결한다. timeout은 `SIM_TIME_BUDGET_EXCEEDED`로 별도 기록하며 이미지 해석 실패와 구별한다. 일부러 장애물을 치워 성공시키지 않는다. 주 비교252건은 도달을 요청하는 양성 과제의 계획량이다. 사전에 blocked/모호하게 만든 과제는 별도 진단군에서 기대 거절/질문을 채점하며252건의 주 완료율에 합산하지 않는다. 양성 과제에서 실제 생성 결과가 막혔으면 정상 거절 자체는 보호 동작으로 인정하되 전체 임무 완료로 세지 않는다.

### 3차 자동 수정의 효과와 안정성

자연 오류가 난 시험 중 최종 전체 회복 비율과 오류 유형을 보고한다. 처음부터 잘 만든 조합은 회복 분모가 적을 수 있으므로 회복률만으로 순위를 만들지 않는다.

별도 고정 진단군에서 같은 오류 후보·같은 진단·같은 범위를 각 repair 모델에 제공한다. 복합 크기/지지, 이전 배치 되돌림, 부분 개선, 잘못된 수정 후 회복, 반복 무변화와 예산 종료를 포함한다. injected/replayed라는 사실을 명시한다. 자연 오류군과 합산하지 않는다.

수정 loop가 성능을 올렸다는 인과적 주장은 selected config에 대한 개발군 ablation에서 확인한다. 동일한 초기 후보를 두 branch로 복사하여 repair OFF/ON을 비교하고 외부 답안은 어느 branch에도 주지 않는다. 자연 full-run 성공 수치와 구별하며 초기 후보 재사용 사실을 공개한다. 이 시험을 하지 않으면 초기→최종 개선은 기술통계로만 보고한다.

## 7 같은 조건의 구체적 정의

모든 모델에 숫자 몇 개만 같게 지정했다고 완전히 동일한 실험이라고 쓰지 않는다. 비교 단위는 **provider/model/adapter/생성 정책을 포함한 구성**이다.

- 동일: 입력 bytes·언어·요구사항, canonical schema·library, host 검사, 수정 정보 접근, 최대 요청·repair·active time, 실제 engine/RobotProfile/주행 조건, 독립 평가 기준.
- 기록/차이 공개: provider의 이미지 resize/detail, tokenizer, seed 지원, reasoning/thinking, temperature/top_p, rate limit, 모델 revision, endpoint/응답 metadata, USD 단가.
- 초기 자원 정책 후보: 단계 출력20,000, 요청300초, 전체 active900초(initial420/repair300/final180), HTTP24/repair3/stalled2. B0 개발 시험으로 정책을 바꾸면 **전체 후보에 적용 후** 동결하고 기존 기록과 별도 cohort로 둔다.
- 지원되는 temperature0를 쓰더라도 결정적 출력이라고 주장하지 않는다. 미지원 값은 미지정으로 기록한다. Luna reasoning none과 Lightning thinking off는 숨기지 않는다. 모델별 전용 prompt 튜닝은 본시험 중 금지하고, 필요하면 별도 best-config 실험으로 같은 튜닝 예산을 부여한다.
- 시간/토큰 제한이 같은 주 비교와 동일 USD 예산 비교는 서로 다른 실험이다. 우선 자원 정책 고정으로 품질/비용을 함께 보고한다. 금액 한도가 일부 비싼 모델만 먼저 자르면 그 영향을 budget-limited 결과로 공개하거나 별도 실험으로 분리한다.
- 각 trial의 금액 상한·provider별 캠페인 잔여가 고정 정책 수행을 막지 않는지 예약 전에 확인한다. 잔여에 맞춰 마지막 모델만 작은 grant로 몰래 실행하지 않는다. 부족하면 남은 paired block은 NOT_RUN이다.
- 실행에 영향을 주는 코드/프롬프트/schema/asset/시간 정책 변화는 새 cohort다. model alias의 서버 내부 weight 고정이 불가능하면 정확 ID·시간·provider revision 가용 여부를 공개하고 완전 결정 재현을 약속하지 않는다.

## 8 통계와 추천 규칙

독립 단위는 HTTP나 반복 실행이 아니라 방 또는 독립 과제다. 같은 방의 두 반복은 안정성 관측이지 서로 다른 방 두 개가 아니다. 방별 평균을 먼저 구하고 유형별 결과를 분리한다. 사진·text는 기본적으로 하나의 평균으로 합치지 않는다. 실제 사용 비중을 정하지 않았다면 임의 가중 종합점수를 만들지 않는다.

paired 차이를 계산하고 방 group을 함께 재표집하는 cluster bootstrap으로 95% 불확실성 구간을 제시한다. 후보 간 동일 방의 대응 관계를 보존한다. 유형별 동일 가중을 쓰면 층화된 방 재표집으로 그 가중도 보존한다. 단순 run별 Wilson 구간은 반복 의존성을 반영하지 못하므로 주 결론으로 쓰지 않는다. 모든 표본이 같은 결과여서 bootstrap 분산이 0인 경우도 완전 확실성으로 표시하지 않는다. 저정보/퇴화 표본은 그 사실을 표시하고, 독립 방의 bounded 평균에 대한 보수적 구간 등 사전에 정한 대안을 사용한다. 집계/검정은 알려진 합성 데이터의 coverage·null case로 먼저 검증한다.

후보3개의 3쌍 비교와 사진/text의 확인적 가설 범위를 본시험 전 등록한다. room-level paired randomization 등 적합한 검정을 사용하고 다중 비교를 보정한다. 예를 들어 사전 family에 Holm 보정을 적용한다. 신뢰구간과 실제 효과 크기를 같이 보고, 단순히 개별 모델의 구간이 겹치는지로 유의성을 판단하지 않는다. 사후 subgroup 발견은 탐색적 결과로 표시한다.

**표본 수를 횟수만 보고 충분하다고 선언하지 않는다.** 개발군의 방별 paired 변동으로 성공률 차이 15–20%p 같은 실용적 효과를 탐지할 power/precision을 추정하고 최종 N을 결정한다. 목표 power80%, 양측 family 오류5%를 출발안으로 하며 assumptions·simulation seed·한계를 기록한다. 방30개는 시작 설계이지 작은 차이를 판별한다는 보장이 아니다. 참고로 독립 이항 표본의 단일 비율을 최악 조건에서 대략 ±10%p로 추정하려면 약97개, ±5%p면 약385개가 필요하다. 이 숫자를 반복이 있는 paired 비교의 필요 N으로 그대로 적용하지 않는다.

본시험을 본 뒤 유리해질 때까지 반복하거나 중간 1위를 보고 조기 성공 종료하지 않는다. 본시험 전 결정한 N/예산을 사용한다. 외부 차단으로 중단되면 불완전 비교다. 추가 데이터를 별도 확인 시험으로 사용할 경우 새 승인·사전 계획을 남기고 오래된 holdout 결과를 개발 정보로 취급한다.

추천 규칙도 사전에 고정한다.

1. 품질 기준 충족 전체 경로 완료율과 각 품질 축을 먼저 비교한다. 실용적 차이와 통계적 근거가 있으면 해당 범위의 우위를 주장한다.
2. 충분한 근거 없이 동등성을 가정하지 않는다. 비용 우선 선택을 위해 비열등성을 주장하려면 허용 성공률 손실(출발안5%p)과 품질 하한을 사전에 정하고 이에 대한 충분한 구간/표본이 있어야 한다.
3. 동등/비열등성이 확인된 후보에서는 `모든 시도 비용 / 품질 충족 전체 성공 수`, 성공 완료시간, repair 부담을 비교한다. 성공0이면 성공당 비용은 계산 불가/무한대로 처리한다. 실패 비용을 분자에서 빼지 않는다.
4. 근거가 부족하면 비용·품질·성공률의 Pareto 후보를 제시하고 단일 최적이라고 쓰지 않는다. 소표본 p95는 안정적인 운영 지연으로 광고하지 않는다.

## 9 실패 처리와 중단

모든 예정 trial은 최종 상태가 있어야 한다. `NOT_RUN`, `PREFLIGHT_BLOCKED`, `STARTED_FAILED`, `COMPLETED`, `AUDIT_INVALID`, `QUALITY_NOT_EVALUATED`를 보존한다. 실제 실패 원인은 모델 의미/계약, host/compiler, 검색 예산, 목표/경로, provider HTTP·billing, runtime/harness, 증거 부족으로 구분한다. 원인을 확정하지 못하면 unresolved로 둔다.

전체 시작 시도 기준 제품 완료율에는 운영 장애도 남긴다. 모델 능력 조건부 표는 사전에 정의한 비모델 인프라 실패만 분리할 수 있고 그 제외 수·사유 및 원 전체 표를 함께 공개한다. 조건부 paired 비교에서 한 조합만 결측이면 그 방/block을 완전 대응 집합에서 제외하고 제외 전 전체 결과와 민감도 범위를 함께 제시한다. 결측을 성공으로 메우거나 다른 case로 대체하지 않는다. 402를 모델의 공간 이해 실패로 해석하지 않는다. 반대로 출력 잘림·모델 계약 미준수·모델의 잘못된 배치를 인프라 탓으로 빼지 않는다. host 원인도 제품 전체 성능에서는 실패다.

timeout/출력 잘림/UNKNOWN 결과/기록 저장 실패/해시 불일치/미결 예약 등 기존 중단 정책을 유지한다. 출력 제한을 맞히면 추가 자동 호출을 멈추고 원 요청·usage·finish reason으로 먼저 진단한다. 동일 결과를 성공할 때까지 재시도하여 처음 실패를 덮지 않는다. 재시험은 새 attempt와 사유를 기록하고 고정된 집계 규칙을 따른다.

서로 다른 모델5개 연속 동일 근본 실패는 공통 경로 점검 중단 조건이다. 후보3개 full-run만 있는 단계에서는 똑같은 host/harness 결함이 모든 후보를 막는 것이 확인되면5개가 될 때까지 낭비하지 않는다. 단순히 성능이 나쁜 결과를 공통 코드 결함으로 추정해 시험을 중지하거나 실패 표본을 삭제해서도 안 된다.

## 10 비용 및 실행 승인

이번 요청은 계획 작성이며 새로운 대규모 유료 캠페인 실행은 하지 않는다. 과거 승인 Nebius USD5/OpenAI USD1과 기존 사용/예약, 시간 범위는 그대로 보존한다. 계정 잔액이 충분하다는 사실은 새 사진 전송·무제한 추가 호출·카드 청구 승인이 아니다.

현재 보수 노출 기록은 Nebius USD0.25743975, OpenAI USD0.20603480이며 원 사용량·불명 예약·별도 probe를 포함한 추정이다. 실제 청구서/잔액 차감과 동일시하지 않는다. 새 캠페인 승인 시 기존 사용을 포함하는 총상한인지 별도 상한인지 먼저 명확히 기록한다.

실행 전 무료 견적표를 생성한다: eligible V/T, stage jobs, 선택조합 수, 방/설명 수, 반복, 예상 HTTP 및 최악24HTTP, input/output 토큰, provider별 관측 단가·가격 시점, 정상/repair-heavy 비용·시간, judge/워밍업/실패 예약 비용. 기존 최신 소표본의 조합 평균 비용은 약USD0.0044–0.0357/시험이지만 새 복잡한 방·선별·추가 채점까지 이 범위에 든다고 보장하지 않는다.

252시험의 세션 상한만 계산해도 `252 × 900초 = 63시간`이며 이는 최대 활성시간의 합이지 예상 완료시간이 아니다. 기존 한 사진의 약1–2분 실행을 수백 새 방의 고정 ETA로 외삽하지 않는다. 개발 pilot 실측으로 예상 소요와 불확실성을 갱신한다. 모든 모델 선별·사람 라벨링 시간도 별도 제시한다.

지출은 provider별 hard cap과 미결 예약을 모두 확인한 뒤 dispatch한다. 비용이 부족하면 전체 계획을 PARTIAL로 보고한다. OpenAI 예산에 맞추려면 후보를 줄이거나 판별 목표를 낮추는 선택이 가능하지만, **특정 모델의 어려운 case만 빼거나 반복 수를 줄이지 않는다.** 실제 실행은 데이터·목적지·파생 렌더·기간·가격/한도가 확인된 유효 승인에서만 한다. 승인된 범위 내 각 호출마다 재승인을 요구하지 않는다.

## 11 공개 산출물과 해커톤 해석

GitHub용 산출물은 frozen manifest, 환경/모델 목록 snapshot, 재현 명령, metrics JSON/CSV·표, 익명 trial 상태/실행 ID, confidence/effect/실패 taxonomy, 승인된 공개 사례의 원사진/최종 3D/관계 비교, 모든 실패 포함 감사 요약이다. `report` 재생성은 inference0회다. push는 별도 사용자 승인 전 수행하지 않는다.

비공개 사진·원문·좌표·생응답·키는 공개 export에서 제외한다. 권한 있는 공개 데이터가 없으면 집계 공개는 가능하지만 독립 재현 범위가 제한된다고 설명한다. 재현 가능한 공개 subset과 private subset 성적을 구분한다. 가장 잘 나온 스크린샷만 고르지 않고 사전 선택 사례 또는 전 사례의 익명 contact sheet를 사용한다.

결과표는 최소 아래 세 부분이다.

1. 역할별 전체 eligible/미시험/실패 포함 선별표: 이미지 관측 품질, 공통 관측 기반 설계/repair, 비용/지연.
2. 최종 후보의 독립 사진/text 전체 경로 표: N/반복/버전, 품질 충족 완료율·paired 차이/구간, 누락·관계·지지·외형, 자연수정 회복, 성공/실패 시간, 실패 포함 성공당 비용, 인프라·미평가 수.
3. 제약별 추천: Nebius/NVIDIA 조건부 후보, 제약 없는 후보, 불확실성/추가 데이터 필요 여부. 범위 밖 모델을 포함한 전세계 최적처럼 쓰지 않는다.

해커톤 자격은 성능 점수와 별도 열이다. 실행 당시 공식 규정 snapshot으로 API/모델의 실질 runtime 역할, 제출언어·현장·track 조건을 확인한다. 현재 기록의 일반 Nebius/NVIDIA 사용 경로와 Physical AI의 별도 요구를 합쳐 자동 충족으로 표시하지 않는다. 가짜 호출로 자격을 맞추지 않으며, 벤치마크에서 고득점이라는 이유로 규정 PASS를 부여하지 않는다.

## 12 구현 순서와 인수 체크리스트

| 순서 | 작업 | 완료 근거 |
| --- | --- | --- |
| B0 | 원 packing·goal 실패 재생, 검색/수정/내부오류 분류, 확인된 제품 결함만 수정 | immutable 원본, 범용 정답 있는/없는 회귀, 개선 전후 원인 대조 |
| B1 | dataset/config/schedule 승인 명세, 사진/text/목표 일반화, 버전 freeze | 명세 검증·분리·유출방지·예산·재개·실행순서 회귀 |
| B2 | 독립 답안·품질 evaluator·단계별 분모·cluster 통계·export | 누락 유리함/동일방 반복/실패비용/평가불가 반례에서 올바른 점수 |
| B3 | 기존 관련 suite·App build, 실제 소규모 승인 smoke, 환경 snapshot | actual 일반 경로 사진/text, 현재 frame/저장/SIM/Stop/재열기 근거 |
| B4 | 개발 데이터에서 역할 선별·자원정책/power·예산 확정 | 전체 eligible/exclusion, 후보 선정 이유, 최종 rubric/N/config SHA |
| B5 | 동결 holdout balanced 시험·익명 평가 | 모든 예정 trial 상태·같은 버전·전송/비용/로그 감사, 중간 튜닝0 |
| B6 | 비교·추천·공개 패키지 | 불확실성·실패·범위 포함, 성능/규정 별도, 코드로 보고서 재생성 |

오프라인 synthetic 회귀와 저장 응답 재생은 먼저 수행할 수 있다. 모델 성공률 표는 actual 호출에서만, SIM PASS는 actual Isaac에서만, 실물 PASS는 별도 현장 인수에서만 나온다. 테스트를 완주하는 일과 비교 차이가 충분히 확인되는 일은 별개다. 차이가 안 나와도 올바른 시험의 완료 결과다.

### 6.1 Sol 전달문

> 이 계획의 B0부터 의존 순서로 구현한다. 현재 로깅·scope/rollback·budget·App/Isaac 경로를 재사용하고 특정 침실/모델의 성공을 위한 분기를 만들지 않는다. 최신 Baseline/Memory/검증 기록과 기존 dirty 변경을 먼저 확인한다. packing과 goal의 원 실패를 보존한 재생으로 제품 결함과 제한 탐색·후보 오류를 분류하고, 확인된 결함만 고친다. 이어서 선언형 다중 case·같은 반복/순서 균형·독립 품질 평가·paired 통계를 기존 runner에 연결한다. 원사진/정답은 서로 격리하며 text-only도 끝까지 검사한다. 실제 외부 실행은 그 시점의 유효한 데이터/목적지/비용/시간 승인 안에서만 한다. 실패한 시험과 미실행을 숨기지 말고, output length/UNKNOWN/예산/공통결함 중단을 지킨다. 본시험 결과를 보고 기준·prompt·코드를 바꾸면 새 cohort로 분리한다. 의미 있는 증분마다 회귀와 Baseline/Memory를 동기화하고, 범위 내 안전한 다음 작업을 이어간다. 구현 완료, 실제 시험 완료, 우위 입증, 실물 인수를 각각 구분한다.

## 13 설계 참고

다음 자료는 방법론 근거이며 TwinPulse의 표본 수·수락선·실행 성공을 보증하지 않는다.

- [Stanford HELM](https://crfm.stanford.edu/2022/11/17/helm.html): 동일 시나리오에서 여러 평가 축을 함께 측정하여 성능 간 trade-off와 미측정 범위를 공개하는 원칙을 참고했다.
- [Judging LLM as a Judge](https://arxiv.org/abs/2306.05685): 위치·길이·자기 선호 등 judge 편향의 한계를 고려해 production critic과 독립 채점을 분리한다.
- [Dror 등의 NLP 통계 검정 가이드](https://aclanthology.org/P18-1128/): 과제·측정량·실험 구조에 맞는 검정이 필요하다는 원칙을 참고했다. 이 계획의 방 단위 대응/반복 구조와 구체적 N·threshold는 TwinPulse용 설계다.
