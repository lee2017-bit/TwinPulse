# TwinPulse 독립 입력 실제 모델 조합 시험

작성 2026-10-11 · 기준 v412 · 상태 PARTIAL_REMOTE_UNKNOWN_REPORT_FINAL · 예약 PAUSED

## 최종 보호 중단과 단일 PDF v412

최신 요청은 진행 중이라는 응답 대신 실제 비교 수치·결과 사진을 한 파일로 보고하라는 것이다. **보고서는 완성했으나 전체 예정 시험은 완주하지 못했다.** [단일 PDF](../../outputs/benchmark-evidence-report-20261011-v412/report.pdf)는 20쪽이며 공개 원본 사진5개와 실제 결과 프레임5개, 역할별/소스별 PASS·FAIL·NOT_RUN, 지연p50/p95·비용·수정 회복, 조건부 추천·정확한 잔여를 포함한다. SHA256 `06cf48a40c9655271a9434e03b8ccc606b193c1126fd433ca2976ae0440ada3f`. 개인 침실·키/헤더·원문 응답·기하 좌표를 PDF에 넣거나 GitHub로 업로드하지 않았다.

### 종료 원인과 분모

v411b owner8344/unifiedexec28279는 약12:10KST에 정상 종료했다. Qwen235B 거실 case `planner-nebius-12d7a45f0ca7-r1` 앞2HTTP는 received, 세번째 attempt `3e120f4070164077b0700bbbdc3a19d1`는300.609초 후 timeout/rawCancelled·usage없음·원격결과/비용미확정이었다. 새로운 UNKNOWN USD.0764288을 유지하며 REMOTE_UNKNOWN gate로 다음 dispatch를 중단했다. 후행 raw가 저장됐어도 원격 성공/청구 확정으로 바꾸지 않았다. **이전 FileNotFoundError 보고 race는 재발하지 않았으며 원격 timeout은 미해결이다.** 이전bedroom UNKNOWN 셀은 재호출0, 신규 실패는 원래 미호출 거실 셀이다. 최신 owner/dispatch-lock 부재와 owned Isaac 종료를 확인했고 강제 종료0이다.

|411b 분모/관측|수치|
|---|---:|
|예정/처리|136 / 24|
|실제 호출 시험|22|
|설계 계약PASS/FAIL|15 / 7 (FAIL 중 timeout UNKNOWN1)|
|처리됐으나0HTTP|2 (KimiK3 예산예약1 / MiniCPM 문맥1)|
|아직 착수하지 않은 예정시험|112|
|총 HTTP|89|
|무수정 PASS|13|
|수정 시도 시험/회복PASS|8 / 2|

0HTTP KimiK3의 원 status는 FAIL이지만 모델 응답 실패에서 제외했다. 전체 신규 NOT_RUN은 112미착수+2admission=114이며 원summary의 status기반113을 덮어쓰지 않고 독립 수치에서 사유를 구분했다. 결과표 모델별 planned는 이전409에서 건너뛴 셀 수에 따라4~6이다. 409 관측60슬롯/실제48시험/41계약PASS·7FAIL/0HTTP12, 원409 설계와 마지막UNKNOWN, 407의20k/20actual·8기능PASS·12FAIL·40NOT_RUN은 모두 별도 소스로 표시했다. 서로 다른 소스의 성공률을 합산하거나 이번40k full journey 성공으로 표시하지 않았다.

### 원본 감사와 비용

독립closed auditor를 실행해 scope/continuation의 정확한suffix/원본979/공유관측/전역설정/현재frozen source, case ExecutionID·HTTP attempt·raw·장부·dispatch·validation의 연결을 대조했다. [role-audit.json](../../outputs/benchmark-evidence-report-20261011-v412/role-audit.json): integrityPASS/오류0, settlementUNRESOLVED, 종합auditFAIL 사유 `UNKNOWN_COST_OR_COMPLETION`. 후행300.609초 실제raw도 요청 지연에 반영했고 UNKNOWN의 없는usage는 출력합에서 제외했다. 로컬종료와 invoice 정산을 혼동하지 않았다.

|공급자|기존 이월USD|이번 추정/예약USD|누적 노출USD|원 총상한USD|
|---|---:|---:|---:|---:|
|Nebius|2.31278064|0.74077083 (신규held.0764288포함)|3.05355147|5|
|OpenAI|1.81365030|0|1.81365030|5|

이전held.0764288도 이월에 포함, 알려진 두hold 합.1528576을 환급하지 않았다. 실제 Account balance/청구서는 미검증이다. 예산이 소진돼 멈춘 것이 아니라 새비용미확정 보호 규칙이며 별도판단 없이 추가paid를 실행하지 않았다. Native `automation_update`로 기존prompt/rrule/대상thread를 보존하고 statusPAUSED 적용·결과확인했다.

### 안전한0HTTP 실제 Isaac 이미지 대안

저장plan을 감사한4개(NemotronSuper/Flash4.1/Qwen3.8 거실은411b, Luna침실은409)를 기존 core/adapter/현재시각라이브러리 경로에 넣어 실제Isaac Build→revision/receipt/현재overlay확인→USD저장/재열기→1280×960 캡처했다. 결과 `outputs/benchmark-role-plan-render-20261011-v411-r2/result.json`는 `PASS_STATIC_REPLAY_ONLY`, 각4개 `PASS_STATIC_BUILD_CAPTURE_ONLY`, 원본SHA불변·providerCalls0·robot0·timelineRun0·movingStopNOT_RUN이며 새fulljourney 인수로 대체하지 않았다. 벽 visibility만 진단cutaway, geometry재배치0/임의모델코드 실행0. 기존407 식사공간 Luna/Luna의 actualUI1920×1080 이동완료 프레임1개는 과거20k 소스로 명확히 분리했다(최대이동.77159m/도착거리.03982m/별도Stop paused·reloadPASS·browserClosed).

의자/책상/캐비닛 파라메트릭 모델은 실제 렌더됐지만 식물·소품·러그/커튼/TV 표현과 재질·사진 배치는 단순/부정확할 수 있다. 특히 원사진 벽걸이TV가 낮은스탠드처럼 표현되는 저장사례가 있다. 계약PASS를 사진정밀도·실측규격·photorealism으로 주장하지 않는다. 독립blind평가0/qualifiedfull0/wholefalse다.

### 보고 회귀와 시각검토

외부local audit/recovery/continuation/report 도구13개 unittest PASS(기존8과겹침), budget0HTTP가 모델FAIL로세어지지않음·수정회복/무수정분리·후행wire시간과usage보존·Wilson/quantile를 확인했다. 최초 PDF helper optional attempt_id KeyError는 교정, 잘못된 unittest모듈명2개는 정확한 이름으로 재검증했다. 정적helper 미지원 `report_mode`는 Isaac실행 전0HTTP 실패 후 제거하고 새v411-r2에 재생했으며 실패원v411도 보존했다. 각 단계 실제오류를 숨기지 않았다.

PDF는 Poppler로20쪽 모두PNG렌더→전쪽contactsheet/표·실패·사진·잔여 상세 시각검토, pdfplumber로 빈페이지/가로overflow/이미지10개/필수수치를 확인했다. [metrics.json](../../outputs/benchmark-evidence-report-20261011-v412/metrics.json), [final-validation.json](../../outputs/benchmark-evidence-report-20261011-v412/final-validation.json)과 일치하며 복사본SHA도 재검사했다. canonical product/web/build와 원 시험코드는 변경하지 않고 문서와 로컬 보고만 동기화했다.

### 조건부 선택과 잔여

- Nebius/NVIDIA 우선 후보는 Flash관측6/6 + Super설계이번1/1·20.937초/.0103932·정적Build통과. Ultra도1/1·21.141초/.041111이므로 Super는 비용 후보이지 n1정확도 우승 아님. 규정없는 후속 비교기준은 Luna/Luna(관측6/6, 과거407사진기능2/3)이며 새411b전체조합미실행이다. Gemma관측6/6최소비용.0033609도 품질우열을 뜻하지 않는다.
- 공식rules 재확인: Apps&Agents는 Nebius Token Factory Nemotron runtime 사용, Cloud 배포는권장; PhysicalAI는 별도ServerlessJobs 요건/영문·공개repo·demo제출 등. 로컬시험/모델선정만으로전체규정충족을보장하지않는다. https://nebiusglobalaihackathon.devpost.com/rules
- 정확한 다음순서: 새UNKNOWN청구/요청상태·보호판단→112미착수/0HTTP2조건분리→새40k공개사진3+텍스트3/2반복 actual ordinary App/API/Isaac current-render/semantic goal/run/도착/별도movingStop/stable/reload/reset/닫힌reopen→독립blind품질/더많은방/holdout·독립repair/critic→별도현장 승인 실물인수. 40k만이실패원인해결/모든모델2회완료/최적모델/FullProcess완료는 미입증이다.

아래 RUNNING/ACTIVE는 종료 전 보존 이력이다.

## 명시 승인된 미실행 역할 재개 v411

11:55:26KST 후속 실제 snapshot: owner8344 생존/예약ACTIVE, 종료8/136·30HTTP·설계3PASS/실제응답4FAIL/예산조건0HTTP1. 새 Flash-0731은3HTTP/25.156초/.00433202로PASS, MiniMax-M3(6/.0184164)와Kimi-K2.7-Code(5/.04725535)는REPAIR_STALLED, Kimi-K3는예약 admission 거절0HTTP/비용0으로모델성능FAIL에서분리한다. canonical 동결source SHA재조회 `frozen_source_unchanged=true` 확인. independent closed감사는owner종료후만실행하며현재프로세스나전역설정을수정하지않는다. 검증된closed감사도구는 위외부local경로이며 종료후 `--output` 새파일에읽기전용감사결과를저장한다. 아래4건snapshot은그직전이력이다.

11:55KST 저장 진행 snapshot: owner8344 생존, 종료4/136·16HTTP·PASS2/FAIL2. GLM-5.3-Flash PASS(3HTTP/153.547초/.01171550), Kimi-K2.6 PASS(3/74.391/.08028820), Nemotron-3_5-Lightning FAIL REPAIR_STALLED(5/21.11/.00461166), Hermes-4-405B FAIL REPAIR_STALLED(5/50.172/.051116). 이 네 저장case의 추정합계 Nebius.14773136(진행중 요청 별도), 전체노출/최종순위/전체인수 완료가 아니다. 단일 모델실패를 숨기거나 예정136을 임의축소하지 않고 다음순서를 계속한다. 현재원본 수신/결과/장부 보고가 정상 진행되는 실제 근거이며 사진정밀도/Isaac PASS가 아니다. 독립 closed-role 감사 도구 `C:/Users/jaewo/Documents/Codex/2026-09-12/dl/audit_public_role_campaign.py`도 continuation SHA/979원본/공유관측/정확한suffix/carry 재검사를 연결했고 로컬8개 회귀PASS(옛5와겹침); canonical 동결 source는 수정하지 않았다. source 재조회 최초명령의 PYTHONPATH 누락 ModuleNotFoundError는 읽기전용검사 오류이며 경로를 명시한 재조회로 확인한다.

사용자가 기존 미확정예약을 차감하고 실패요청은 재호출하지 않은 채 남은시험을 계속하자는 질문에 명시 승인했다. 알려진 v409 UNKNOWN `dc753cecf16d41898ed9777d2a6d14c0`/USD.0764288만 fully carry한다. 원총USD5/공급자·오늘18:00KST·공개 CC BY-SA 사진3/파생렌더/시험텍스트 범위는 유지하며, 새 UNKNOWN이나 output length/402/같은역할5모델동일원인은 계속 중단한다. 개인사진/로봇/설치/배포/push/새agent0. 아래 v410 PAUSED는 재개 전 이력이며 원실패/비용은 삭제하거나 승격하지 않는다.

기존 `benchmark_role_campaign.py`에 read-only admission/새cohort 연결을 구현했다. 수정전 감사SHA `47e57d779dcab7eb10355bc122776496e881d0defeb08e442587cc17f7ad1b68`와 감사PASS, 원본979개 SHA와 파일집합, old owner/dispatch-lock 부재, 장부finished_at/상태 및 정확한 carry, 입력/기한/공통cap/전역설정/카탈로그 모델·가격·문맥을 검사한다. old jobs 첫74개(마지막 중단Qwen 포함)는 건너뛰고 정확히 나머지136개만 선택한다. 공개3방의 첫Luna r1 observation을 원 파일/semantic SHA로 검사하여 동일 artifact를 planner에 전달한다. 관측은 모델 출력이지 정답/실측이 아니다. 새 장부의 UNKNOWN 보호는 수정하지 않았고 과거 실패 streak도 이어간다. 이전 성적을 새 source의 완료 성적으로 합치지 않는다.

실제 원본을 사용하는 `--check-continuation-only`는 원본979/공유3방/skip74/remaining136/inference0으로 PASS했다. 새 회귀9개와 timeout 등 관련 전체87개 PASS(이전78과겹침), 최종 diff-check PASS. 최초 sandbox Windows Temp fixture 접근거부/cleanup 오류는 기록하고 승인된 로컬 회귀만 escalated 실행했다(ACL/설치변경0). 최초 fixture 중복case_id TypeError9개와 sealed job.repeat/결과.repetition 차이 KeyError를 비용0에서 교정했고, 실제 첫 metadata3회의 admission은 카탈로그 행의 반환 순서만 달라 `ROLE_PRIOR_SCHEDULE_CHANGED`로 추론0에서 종료했다. 이 `outputs/benchmark-public-roles-20261011-v411`을 보존했다. identity/coverage 검사를 행순서와 분리하고 실제 dispatch는 원 sealed jobs 그대로 유지해 수정했다. fixture/metadata 변화로 입력·성공기준·가격을 완화하지 않았다. 문서 첫 patch context 불일치는 변경0 확인 후 정확한 patch로 처리했다.

**실제 재개:** `outputs/benchmark-public-roles-20261011-v411b`, ownerPID8344/unifiedexec28279, 2026-10-11 11:49KST 시작. scope SHA `8e7913f0cbfdeea0774773ee8e702b832e6cd71af857b6cbc1e9aa7e8d950490`, metadata 현재25개/추론예정136개/공통40k·HTTP300초·planner12HTTP/3repair/1800초. carryNebius2.31278064/OpenAI1.81365030, 남은상한2.68721936/3.18634970이며 invoice/계정잔액은 검증한 값이 아니다. 첫 GLM-5.3-Flash 설계 STARTED를 실제 stdout/owner 생존으로 확인했으며 결과는 아직 진행 중이다. 같은 이전 실패요청을 재호출하지 않았다. Native `twinpulse`는 정확한 새owner/root/known-held 예외·새UNKNOWN 중단·기한/결과감사/actual후속 순서로 ACTIVE 재개 및 TOML readback 확인했다.

실행 중 product/harness/web/build/공통평가기준은 동결한다. 문서/outputs만 진행 근거를 갱신한다. 종료 후 새 동결 장부/raw/dispatch/validation/ExecutionID를 감사해 PASS/실제 응답FAIL/문맥·예산 NOT_RUN/UNKNOWN을 분리한다. 역할계약 결과와 실제 photo/text ordinary App/API/Isaac 기능검증, independent blind 사진정밀도/holdout는 별개이며 **전체 데모 PASS/모든모델2회완료/최적모델 확정은 아직 아니다**. 이전407/409와 다른 source 성적은 source별 명시, 과거 timeout/UNKNOWN·불명비용 환급0. 안전gate/잔여예산/기한이 허용하면 실제 일반제품 전체경로가 다음 순서다.

## 타임아웃 후 집계 중단 수정과 부분 비교 v410

현재 owner19692는 종료했다. 사용자의 계속 요청에 실제 worker/진행행/종료 stdout를 확인했으며, 초기 Get-Process 생존 snapshot 직후 종료 결과를 확보했다. **시험이 단순히 채팅 종료 때문에 멈춘 것은 아니지만, 74번째 요청의 timeout 뒤 집계 결함으로 결과표를 쓰지 못하고 종료한 것이 맞다.** 아래 v409 RUNNING/ACTIVE는 종료 전 이력이다.

직접 원인: 공개 bedroom 고정관측을 받은 `Qwen/Qwen3-235B-A22B-Instruct-2507` 설계 첫요청은정상수신했고, 두번째semantic요청 `dc753cecf16d41898ed9777d2a6d14c0`은300초 만료/응답usage없음이었다. 원 raw는 ProviderTimeoutError/cancelled=true/elapsed300.578초, saved_at02:30:04.783486UTC이다. 상위 asyncio deadline은worker스레드를즉시join하지않는데 `run_case` tail은 모든raw가이미존재한다고가정했다. raw저장전 FileNotFoundError→결과/summary 미작성→finally owner해제. 후행worker는raw와장부UNKNOWN/.0764288을정상보존했다. 로컬owner종료/장부finished_at은원격성공이나청구확정을뜻하지않는다. 출력40k소진/빈JSON/402가원인이라는근거는없고, timeout의외부서버/네트워크원인은현재원본만으로구분하지못한다.

### 수정 전 원감사

읽기전용 `C:/Users/jaewo/Documents/Codex/2026-09-12/dl/recover_public_role_audit.py`로 소스편집 전에 scope/sourcefreeze·전역설정·공개입력SHA, 진행행/원result·장부/raw/dispatch/validation/ExecutionID 전건을대조했다. integrityPASS/오류0, 감사중원파일변경0. late raw를쓰거나원result를가짜복구하지않고 별도중단case로분류했다. 감사정본은 [audit.json](../../outputs/benchmark-public-roles-20261011-v410-audit/audit.json), SHA256 `47e57d779dcab7eb10355bc122776496e881d0defeb08e442587cc17f7ad1b68`; 원본디렉터리와분리했으며초기407/옛private역할시험을합산하지않았다.

|분모 또는 상태|건수|
|---|---:|
|예정 역할×사진×반복|210|
|시작/보고작성|74 / 73|
|실제HTTP|102|
|역할 계약PASS|49|
|응답FAIL|11|
|문맥/예산조건에서0HTTP|7 / 6|
|timeout UNKNOWN·host 보고중단|1|
|아직배정하지않은예정case|136|

관측60슬롯을처리했지만실제8모델×사진3×2=48HTTP만보냈다. MiniCPM32k문맥은40k출력조건미충족6NOT_RUN, Kimi-K3는단일보수적예약3.672가잔여승인금액보다커6개0HTTP예산거절이며모델품질FAIL에서분리했다. 관측PASS41/실제응답FAIL7; 설계는8PASS/4응답FAIL/문맥미호출1과마지막UNKNOWN1이다. 모든계획210을미리완료한것으로세지않는다.

[35개 역할·모델 전체비교표](../../outputs/benchmark-public-roles-20261011-v410-audit/metrics-only.md)는PASS/응답FAIL/UNKNOWN/예산·문맥미호출/미배정·HTTP시간p50/p95·추정/held를분리한다. Flash/Luna관측각6/6은응답계약후보근거, 사진정밀도우열이아니다. Super/Ultra설계각1PASS만으로최적조합확정금지. 이cohort의actualApp/Isaac·독립human품질·로봇인수는NOT_RUN/NOT_MEASURED, wholefalse다.

|공급자|이번추정usageUSD|이번UNKNOWNheldUSD|이전노출포함총USD|
|---|---:|---:|---:|
|Nebius|.86893681|.0764288|2.31278064|
|OpenAI|.0076300|0|1.81365030|

원총5씩/18:00기한은불변, invoice/계정잔액미검증이다. UNKNOWN을환급하거나finished_at만으로정산확정하지않는다. 추가paid시험은0이며 기존미확정비용gate에따라 native예약을PAUSED했다.

### 수정과 회귀

기존 `scripts/compare_model_roles_live.py` tail을 `role_attempt_snapshot`/`role_terminal_stop`으로분리했다. raw미존재/미완성도ledger예약을사용하고 EVIDENCE_PENDING/UNREADABLE을명시하며 REMOTE_UNKNOWN 또는 EVIDENCE_INCOMPLETE로끝낸다. originaltimeout은PROVIDER_TIMEOUT으로분류, raw·ledger를대신쓰거나polling/재호출/latePASS승격하지않는다. receivedraw와ledger미정산의race도계속중단한다. `benchmark_role_campaign.py`의예상밖report/storage예외는exclusive interrupted-job과STOPPED부분summary를남기고다음job을호출하지않는다. cancellation은숨기지않는다. 옛v409 raw/result/장부는편집하지않았다.

`tests/integration/test_role_timeout_reporting.py` 새10개는pendingraw·partialJSON·미정산ledger·length/402·ledger없는요청·정상수신·실제run_case tail timeout저장/late원본불승격·report예외무재시도·cancellation·전체execute부분summary/다음dispatch0을검증했다. 관련78PASS, provider전체339PASS, 독립감사owner/classification5PASS(겹침합산금지). 첫전체78 실행의테스트용stores빈dict KeyError1은fixture를교정한뒤78PASS로재검증했고실제API0이었다. 최초apply_patch context불일치는변경0 확인후정확한절별패치했다. provider/core/웹동작·기본cap/전역모델조합/설정·기존guard/실물잠금은그대로이며 새build/Isaac/paid/로봇/설치/commit/push/agent0이다.

정확한잔여: 미배정역할136/마지막Qwen미확정 및기존문맥·금액미호출, 새코드actual사진·text ordinary App/API/Isaac 전체경로, 독립human/blind정밀도와holdout/통계근거, 별도현장인수. 현재안전한오프라인대안인원감사·보고결함수정·회귀·비교표작성을완료했지만외부timeout자체를해결했다고주장하지않는다. UNKNOWNguard를유지한새유효범위판단전에는추가paid를시작하지않으며, 원실패재호출/동일source재개로성적을혼합하지않는다.

## 출력 진단과 새 공개 입력 재시험 v409

최종 목표는 사진/텍스트→3D Twin→검사/수정→현재 Isaac 경로 실행이며, 역할 JSON 계약 성공만으로 전체 데모 완료를 선언하지 않는다. 아래 v408 및 이전 cohort의 원본/실패/한도/승인은 그대로 보존한다.

사용자가 새로 **공개 CC BY-SA 방 사진3장·그 파생 Isaac 렌더·시험 텍스트만 Nebius Token Factory 비교 모델들과 OpenAI gpt-6-luna로 전송**, 기존 사용/UNKNOWN 예약을 포함해 **공급자별 총USD5·2026-10-11 18:00KST까지** 명시 승인했다. 개인 침실 사진/로봇 제외, 출력소진/미확정비용/같은역할5서로다른모델동일실패 정상중단 유지. 옛 야간 기한을 소급 연장하지 않으며 새 결과는 새 source로 별도 집계한다. 11:08KST native `twinpulse` 후속 작업을 새 범위로 ACTIVE 재개 확인했다. owner PID19692 생존/동결source 무수정·중복실행 금지, 종료후원감사→안전gate 통과시에만 후속actual→최종표/잔여/PAUSED로 이어간다. 종료 기록41/210건·그 기록의33HTTP는 진행 snapshot이며 최종 통계가 아니다.

구현: stage 기본 observer4000/planner20000 및 저장모델조합은 유지했다. 명시 설정 상한40000이 UI→API→stage gateway뿐 아니라 manifest1.3의 config별 observer/planner cap→effective settings SHA→ordinary 실제 요청으로 연결된다. manifest1.0~1.2는 실제 옛20k 그대로다. catalog 문맥≤cap는 키/유료요청 전에 거절하며 미지원 행/미실행을 숨기지 않는다. critic=observer/repair=planner 상속은 여전히 현재 계약이다.

거절 응답도 실제 HTTP/finish_reason·visible/추론/공백 수치를 ExecutionID에 저장하고 raw는 기존 transport와 같은2MiB까지만 보존/redaction한다. hidden_reasoning_without_final_at_limit와 visible_whitespace_dominated_at_limit를 구분한다. 이 패턴은 내용 없는 진단이지 성공 조건 완화가 아니다. 실제 기존 Flash원본은20k 전량추론/빈final, Ultra원본은416자 미완성JSON+19,869자 trailing 공백이며 서로 다른 증상이다. 같은 고정 사진의 답안을 하드코딩하거나 숨은추론을 정상최종답으로 올리지 않는다.

### Flash 동일 요청 40k 결과

원 public-dining 사진+저장 current Isaac 렌더+schema+prompt를 hash 재구성했고 **max_tokens만20000→40000**으로 변경했다. 로컬 probe `C:/Users/jaewo/Documents/Codex/2026-09-12/dl/token_cap_probe.py` 및 `outputs/flash-critic-cap-40000-20261011/report.json`에 원본/body/응답/ExecutionID/장부를 보존했다.

|조건|최종 계약|출력/추론 토큰|시간초|빈final|
|---|---|---|---:|---|
|역사20k/2026-10-11 이전 동일critic 입력|FAIL length|20000/20000|35.593|예|
|새40k 반복1|PASS stop|7980/6363|24.687|아니오|
|새40k 반복2|PASS stop|3639/1951|12.265|아니오|

새2HTTP 추정비용 NebiusUSD.0216390/OpenAI0·장부정산/lock없음·전역설정과원본SHA불변. **두 새 사용량이 모두20k미만이므로 토큰 상한만이 원인/상향만으로 해결이라고 증명되지 않았다.** 역사대조이고 무작위 동시20k대조가 아니며 backend/모델 변동/캐시와 generation 변동을 분리할 수 없다. JSON/frame 계약2/2PASS는12물체의 사진 위치/지지/정밀도·전체App/Isaac·로봇 인수가 아니다(critic uncertain17/16 포함).

### 공개 입력 역할 비교 — 진행 중

`outputs/benchmark-public-roles-20261011-v409/`에 fresh metadata/inventory·scope/source freeze·2장부·ExecutionID·raw와 진행행을 저장한다. 현재catalog25=생성24+embedding1; 관측9+Luna/설계24+Luna ×사진3×2=210예정. 같은 공개사진·prompt·schema·공통40k/HTTP300초, 설계12HTTP·repair3/1800초. cap40k를 수용못하는 문맥모델은 NOT_RUN 사유를 기록하며 낮은 성능FAIL로 바꾸지 않는다. Nano/Lightning은현제품disabled/Luna none/그외providerdefault로 모델별 호환성을 고정한다. 관측Luna r1은 방별shared preprocessing 때문에 선행한다; 순수 무작위 latency 우승 주장 금지.

설계모델은 방별 첫Luna r1 관측을 정확히 같은 hash 입력으로 사용한다. 이는 기존 LLM 출력이지 사람 정답이 아니고 shared-observation 파이프라인의 상대 선별이다. observer는원사진만, planner는동일관측텍스트만 전송한다. 새공개 caller는 기존 private PHOTO/PROMPT fallback을 명시인자로 대체한다. 이 역할별 결과에는 actual Isaac가 없으며 후속 shortlist actual ordinary App/API/Isaac currentrender→새semantic request/plan/run/도착거리→별도movingStop/stable→reload/reset/reopen이 남는다. 안전gate가중단하면 우회/자동재호출하지 않는다.

첫 carry-in N1.36741503/O1.80602030은기존1.34577603/1.80602030 + 새probe.0216390이다. 원각USD5에서차감하며 새grant/UNKNOWN환급을 만들지 않는다. 통계는예정/실행/FAIL/NOT_RUN·room·role·HTTP·시간p50/p95·추정/held·원인/단계를분리하고 사진정밀도/독립blind quality/globalwinner와 구분한다.

검증: Provider전체339·관련통합50·설정UI14·타입검사/Vite build PASS, 후속benchmark/역할64 PASS(회귀63/159는겹침;합산금지), probe7 PASS. 초기 pytest 미설치, sandbox FS PermissionError62/Node spawnEPERM, 새wire test fixture의 schema/system누락2회ERROR를 보존하고 설치/ACL 변경 없이 승인된 로컬시험에서 재검증했다. wire fixture 수정은 tests만이며 실행중source freeze를 변경하지 않았다. 옛 Ultra raw/Flash raw/cohort407 manifest/role audit4개SHA 재확인 불변; metrics raw를 GitHub에 올리지 않는다.

정확한 잔여: 역할210 최종감사/중단원인→안전gate를통과한후 새동결 actual photo/text 전체경로→독립 label/사람blind geometry/지지/규격품질(실측 없는사진scale는추정)→비교표/조건부선택/재사용. 이번범위로 전체모델완전2회·완성제품·실물인수는 아직 완료라고 할 수 없다.

## 현재 종료 결과

source407의 예정60 중 실제20건/113HTTP를 정산했다. 기능8PASS·12FAIL·40NOT_RUN, 현재 UNKNOWN0/추론 lock0·소유 continuation/dispatch lock 모두 정상 해제다. 8PASS는 실제 일반App/LLM→current Isaac 렌더→현재 semantic request/plan/run/pose의 목표거리≤.04m→별도복귀 movingStop/1초stable→reload/reset→닫힌backend 재열기를 모두 포함한다. 로봇0/전체데모false/qualifiedfull0/인간blind품질미평가를 유지한다. 공개용 [조건부 추천·비교표·재사용 방법](../benchmarks/comparative-pilot-20261011.md)과 수정 전 원본 재감사 [JSON](../../outputs/benchmark-overnight-20261011/report-407-final/public-pilot.json)/[Markdown](../../outputs/benchmark-overnight-20261011/report-407-final/public-pilot.md)을 보존했다.

실제로 실행된 입력은 dining photo 반복1/2, bedroom photo 반복2, warehouse text 반복2다. 각 조합 photo3건/text1건으로 동일하지만, 예정photo3독립방/text3독립입력 중 관측photo2방/text1입력뿐이다. living전부10·text bedroom/office20·bedroom반복1의5·warehouse반복1의5는 미실행40이다. 기존403–406 성적은407 분모와 합치지 않는다. 아래 진행 중 문단은 당시 이력이다.

| 조합 | 사진 PASS / FAIL / NOT RUN | 텍스트 PASS / FAIL / NOT RUN | 사진 HTTP wall p50 / p95 초 | 현재 cohort 추정 Nebius / OpenAI USD |
| --- | ---: | ---: | ---: | ---: |
| Flash/Lightning | 0 / 3 / 3 | 1 / 0 / 5 | 39.531 / 48.671 | .04782384 / 0 |
| Qwen/Lightning | 1 / 2 / 3 | 1 / 0 / 5 | 38.468 / 48.790 | .09200052 / 0 |
| Luna/Lightning | 1 / 2 / 3 | 1 / 0 / 5 | 28.204 / 36.822 | .01193010 / .00435430 |
| Flash/Luna | 1 / 2 / 3 | 0 / 1 / 5 | 56.313 / 71.303 | .06321720 / .02736340 |
| Luna/Luna | 2 / 1 / 3 | 0 / 1 / 5 | 24.313 / 36.211 | 0 / .02154130 |

현재 실제 사용 추정 N.21497166/O.05325900, 현재 held0/미정산0이다. 이전 carry-in N1.13080437/O1.75276130의 과거 UNKNOWN 예약도 모두 포함한 노출은 **N1.34577603/O1.80602030**이며 원상한각5 이내다. 청구/계정잔액 차감 검증이 아니며 과거 예약을 환급하거나 무시하지 않았다. HTTP wall은 trial별 실제 요청시간 합계이며 운영 전체지연/개별HTTP분위수로 부르지 않는다. CPU진단 ON 공통·작은표본 p95·설치전체closure 미동결 한계를 보존한다.

실패12는 candidate/기하/품질수정10, provider 출력소진1, semantic 접근불가1로 나눈다. `SIM_TARGET_NO_REACHABLE_APPROACH`는 저장후 warehouse 목표 접근 실패이며 생성 실패와 다르다. Stop/재열기 단계에 도달한8은 모두PASS이고 앞에서 실패한12의 Stop은 미검증이다. PASS4건에서 실제 repair 요청 후 성공했으나 모든 repair회복률이나 사진정밀품질PASS를 뜻하지 않는다. goal거리8은 .039515–.039822m/감사 navigationPASS이며 실물위치·최적경로증명이 아니다. 사진PASS5의 finalcritic은 모두uncertain, text는NOT_APPLICABLE_TEXT다.

전부Nebius/NVIDIA Apps&Agents 후보는 Qwen/Lightning(사진1/3·text1/1), NVIDIA runtime을 유지하는 혼합 후보는 Luna/Lightning(동일기능횟수·관측비용/HTTP낮음)이다. 규정없는 사진 후보는 Luna/Luna(2/3·사진HTTPmedian24.313초), text는Lightning 후보지만 이 목적별 분기를 한 조합으로 통합 검증한 것은 아니다. 사진 종류·위치/지지/규격/photorealism/인간품질은 판정하지 않았으며 all20 paired비교 INCONCLUSIVE다. text의 observer/critic 미호출·planner별독립표본 아님을 명시한다. 공식 Devpost 규정의 Apps&Agents Nemotron/Nebius runtime과 PhysicalAI ServerlessJobs/제출 요건을 구분하며 이번 local시험으로 규정전체준수·실물데모완료 보장하지 않는다.

## 출력소진 중단 누락과 오프라인 수정 v408

15번째 `86cc4651fc36cb753bb312f9c3e02691` Flash/Luna dining 반복2의 최종critic `464510ccd47640fb845c20d70656feec`는 raw wire `choices[0].finish_reason=length`, completion_tokens=20000/reasoning_tokens=20000다. 기록 byte가 잘린 것은 아니다(`response_truncated=false`). 그러나 rejected raw의 top-level finish_reason이 없고 ordinary auditor가 그것만 읽어 summary.rows.finish_reason=null이 됐다. 제품 terminal은 `PROVIDER_OUTPUT_TRUNCATED`로 정확했지만 manifest와legacy controller는 rows.length만 검사하여 다음5trial/37HTTP를 실행했다. 그 비용 N.06404805/O.02039960·전부FAIL·원본/분모를 숨기거나 제외하지 않는다. 20000 한도가 실제로 적용되지 않았다는 뜻은 아니며 이번에는 추론토큰만으로 소진됐다.

heartbeat에서 결함을 확인한 직후 `pilot-stop-request.json`을 저장했다. 이미 진행 중이던20번째 정산·소유cleanup을 기다리고 wrapper가 `OWNER_STOP_BEFORE_NEXT_DISPATCH/HTTP0`로 종료했다. 강제종료/lock삭제/재호출0이다. **코드 수정 전에** 기존 frozen source 그대로 report CLI로20건 원 장부/raw/dispatch/receipt/입력/모델/환경SHA를 재감사하고 report-407-final에 저장했다. 첫 report mkdir은 sandbox WinError5였고, 지정출력 폴더의 정상권한 승인 후 같은 읽기감사 재실행 성공이다. 시스템ACL/설정 변경이나 권한우회는 하지 않았다.

공유 `output_limit_reached`가 audited rows.length 또는 typed `PROVIDER_OUTPUT_TRUNCATED` 중 하나로 중단하도록 manifest/legacy 양쪽에 연결했다. 정상 stop 응답의 completion_tokens=20000만으로는 실패를 추정하지 않는다. raw나 과거 summary/장부를 재작성하지 않았고 실제20k실패가 새정책에서 통과한 것으로 바꾸지 않았다. 새 회귀 먼저2ERROR로 기존 누락/함수부재 재현 후 수정, 관련33시험 PASS .289초·실제 저장 campaign을 읽기 전용으로 새gate검사 OUTPUT_LIMIT_STOP/HTTP0·gitdiffcheckPASS다. 처음33시험 중 파일5건은 temp 권한 ERROR이며 정상권한 승인 재검증33PASS, ACL변경/임시기록삭제0. Web/제품provider/core 변경·새전체suite·paid재시험0이다.

후속 예약 `twinpulse`는 도구 응답으로PAUSED 확인했다. source407 report의 historical status RUNNING은 원 campaign값을 보존한 것이며 현재 owner 실행중이라는 뜻이 아니다. 원목표60완료/전체품질완료로 표시하지 않는다. 원기한08:43:20KST는 연장하지 않았고 출력소진 중단을 예산 잔여로 무효화하지 않았다.

검증본 SHA256: manifest d419c730ac154e5cc20ac2f55fe3ed4408fdd896441cf0b0078e329deab5b3b4; authorization f7ab47e297b04a9c996035b7840b42d3be4acc9b7c883984630207d9cdd35562; campaign 8dc1f24708f05ec23a060c576aaa0771bda6b14a75b243c3f042905b9d0919d8; reportJSON 8205fb05929805dd6b03d60f0b81da417678a6ad43ce2ab08a9b06fca7ceccc8; reportMarkdown d30c55a12ba5ad462aefee4c4be0aa0e139119d1738d75bd9b7acc7c8d92bd1d; truncated raw stored-response e8af0ef5c2919163b8e5f3dec54e43633336943c7c6923bdba21fd0f25c3d253. source407 ZIP524/SHAca45d8cd…62118f 유지. 새v408 보호수정은 source407 성적과 다른code이며407 재실행금지다.

정확한 잔여: output소진 응답의critic 추론/구조화 정책과 범용support/region/기하·접근 실패 분석, 별도승인/새freeze의40미실행 조건 비교, 독립사람 labels/blindreview/holdout·범위확장, 독립repair/critic 라우팅, 전체설치환경closure·운영latency, 트랙 제출/ServerlessJobs 및 승인된 현장검증이다. 이번 snapshot만으로 사진복원품질순위나 전원만 켜면 전체실물데모완료를 주장하지 않는다. 새유료grant/한도초기화/사진·raw·좌표·키공개/commit/push/새agent0이다.

사용자의 이번 8시간 승인으로 공개 실내 사진3개와 독립 텍스트3개를 5조합 각2회씩, 총60개 예정 작업으로 비교한다. 기존 개인 침실은 이번 비교에 넣지 않는다. 공급자별 USD5이며 과거 추정 노출도 보수적으로 차감한다. 시작 승인 시각은 2026-10-11 00:43:20 KST, 마감은08:43:20 KST다. admission은30분의 완료 여유를 남기며 출력소진·402·미확정 비용/원본 감사 실패에서는 재호출하지 않는다. 로봇과 설치·배포·시스템 설정은 범위 밖이다.

## 입력과 비교 조건

| 조건 | 사전 고정 내용 |
| --- | --- |
| 사진 | Afifa Afrin 방, Tim Collins 거실, Stilfehler 식당. 다른 저자·다른 공간3개. 모두 CC BY-SA3.0, 같은 사진은 모든 조합에 같은 SHA의 bytes로 전달 |
| 텍스트 | 침실·사무실·창고의 독립 자연어 설계3개. 치수는 명시 설계 치수이지 실제 공간의 실측값이 아님. 창고는 별도 domain stress case |
| 조합 | Flash/Lightning, Qwen/Lightning, Luna/Lightning, Flash/Luna, Luna/Luna. 수리=설계, critic=관측 상속. 25개 카탈로그 전체 성능시험이라고 부르지 않음 |
| 공통 자원 | 단계출력20000, 호출300초, 생성총900초(초기420/수정300/최종180), 최대24HTTP·수정3·비진전2·trial USD.75 |
| 순서 | seed61146, 입력×반복 paired block마다5조합, 실행 위치 균형±1·직렬 actual runtime |
| 인수 | 일반 채팅 사진/text→실제 외부 관측/설계/수정→저장→current Isaac 렌더/critic→명시 semantic goal 도달≤.04m→이동 중 Stop→reload/reset→backend 종료 후 재열기 |
| 동결 | `outputs/benchmark-overnight-20261011/cohort-403-r3/manifest.json`, SHA885f4a5c298dc2109dc295abe25b7016bc50af9a2e69850ff4694cce796328cd. source/asset523개, 환경 진입9/Burger9·입력/평가표·사전 보조 기준SHA |
| 환경 | Windows10/AMD64, PC Python3.12.14, Isaac6.0.1-rc.7. 읽기 전용 nvidia-smi 관측: RTX2070 Max-Q/driver592.82/8192MiB. 환경 계약은 진입파일·reviewed 자산만 동결, 전체 설치 DLL/wheel/extension와 driver bytes 미동결 |

Flash와 Qwen은 기존 카탈로그의 이미지 후보이며 Lightning은 NVIDIA/Nebius 역할 제약을 보존하는 후보다. Luna/Lightning은 같은 설계 모델에서 이미지 관측을 바꾸는 비교이고 Flash/Luna는 같은 관측에서 설계 역할을 바꾼다. Luna/Luna는 제약 없는 비교 기준이다. 과거 단일사진 성적은 후보 선정의 개발 근거로만 쓰며 이번 결과에 합산하지 않는다. GPT6 Luna의 이미지 입력/structured output은 [공식 모델 문서](https://developers.openai.com/api/docs/models/gpt-6-luna)에서 확인했고 계정 가용성·가격은 각 live 진입에서 기존 보안 키로 재조회한다.

## 성공과 품질을 구분하는 기준

raw/request/validation·실행ID·장부usage·실제 입력/목표·라우팅·환경 전후SHA를 재감사한다. 실패와 NOT_RUN, 거절의 미확정 비용예약은 보존한다. 독립 인간 품질 답안과 blind 현재 렌더 검토가 없으므로 **qualified full PASS는0이며 실행 성공만 따로 센다.** 이번 데이터는 development pilot이고 holdout 잠금을 완화하지 않았다. 사람 출처·검토자·실측을 만들어 넣지 않는다.

출력 전에 사진을 직접 본 agent의 최소 보이는 종류·개수와 명시 텍스트의 필수 종류·개수를 별도 evaluator-only 기준으로 고정했다. 사전 범용 category alias와 capped matching으로 required-kind recall을 계산하며 정상 저장물체가 없으면0이다. 이는 완전한 물체 precision/F1, 사진 위치·지지 관계·규격 정확도 또는 photorealism 점수가 아니다. 관측/최종 저장 recall을 별도로 보며 내부 critic 자기판정을 독립 평가로 쓰지 않는다. 사전 기준과 답안은 모델 packet에 포함되지 않는다.

각 modality에서 독립 입력은3개뿐이며 두 반복을6개의 독립 방이라고 세지 않는다. 20개 paired 비교의 가족α.05를 나눈 방단위 구간을 기록한다. 소표본의 차이 불명은 INCONCLUSIVE로 남기며 전체 모델 우승이나 다른 사진의 일반 성능 우위를 주장하지 않는다. 생성 active·HTTP wall p50/p95와 실패 단계를 나란히 제공해 짧은 실패를 빠른 성공으로 추천하지 않는다. diagnostics의 CPU profile 값은 모델속도 순위에 쓰지 않는다.

## 데이터 출처와 전처리

- [Afifa Afrin 방](https://commons.wikimedia.org/wiki/File:Bedroom_with_a_almirah,_a_chair_and_TV_on.jpg), [Tim Collins 거실](https://commons.wikimedia.org/wiki/File:Living_Room.jpg), [Stilfehler 식당](https://commons.wikimedia.org/wiki/File:Orange_Dining_Room.jpg). [CC BY-SA3.0](https://creativecommons.org/licenses/by-sa/3.0/)의 저자·라이선스·변경 표시와 share-alike 조건을 유지한다. 생성 장면/원본 공개는 여기서 GitHub push로 승인된 것이 아니다.
- 최초 다운로드3개 SHA1은 각 Commons 원본 metadata와 동일했다. Afifa 원본은 PIL format MPO라 기존 일반JPEG gate에서 `BENCHMARK_IMAGE_MIME_MISMATCH`로 **HTTP0** 거절됐다. 원본/실패package403은 보존하고 Commons가 제공하는1280px JPEG thumbnail을 사용한다. 같은 room group이며 자체 편집·특정 사진 예외 허용은 하지 않았다. 거실·식당은 원본 그대로다.
- sandbox의 새 폴더 생성 및 HTTPS 다운로드 실패는 정확한 대상의 승인 명령으로 해결했고 TLS 검증·ACL·시스템 설정은 바꾸지 않았다. tvly/setup skill 파일이 없으므로 설치 없이 웹 도구에서 실제 Commons license 페이지를 확인했다.

## 구현과 현재 검증

기존 controller/ordinary gateway/App/Isaac 경로를 재사용하는 `prepare_benchmark_pilot.py`, 직렬·독점·현재 grant continuation인 `run_benchmark_pilot.py`, 원본을 재감사하는 `benchmark_pilot_report.py`를 추가했다. 신규4개 계약회귀 PASS(0.002초), source/환경/data 준비PASS·외부HTTP0다. builder403-r2는 report source 추가 전의 보존본이고 실제시험은r3만 사용한다. 실제 실행과 최종 결과는 아래에 이어 기록한다.

전체 제품은 PARTIAL / whole=false다. 이 문서는 실제 시험 전에 고정한 조건이며 결과가 준비됐다는 뜻이 아니다.

## 최초 실제 실행·harness 수정

16:00:25UTC r3 첫 dining/LunaLuna repeat1(job ba63e3e4d33253e3d77eee2a736efe1e)은 backend startup에서 `stage_routing_corrupt`로 실패했다. supervisor13개 선행조건은 통과했지만 backend의 일반 gateway가 bound `stage_model_catalog.json`을 찾지 못했다. reviewed-settings에는 있으나 journey가 metadata3개만 복사했다. 모델 요청0 관측·Isaac 미시작이며 ordinary ledger 자체가 없어 비용0으로 정산할 수 없다. 원 `campaign-403` UNKNOWN OUSD.75 예약과 로그를 보존한다.

`copy_ordinary_settings`는 카탈로그를 먼저 SHA로 검증하고 explicit4개 registry metadata closure를 복사·전후 검증한다. 누락/변경은 backend/request 전에 실패·무관한 파일 제외/legacy3개 호환/OS credentials 별도 유지. 새4+pilot4=8 회귀PASS(0.045초). 첫 sandbox Temp4ERROR는 보존하고 동일한 승인 로컬 시험으로 검증했다. ACL/시스템 변경은 없다. 모델·사진·성공조건·repair 예산을 바꾸지 않았다.

source 변경 이후 r3를 덮어쓰지 않고 r4로 재동결한다. 새 grant는 동일 사용자 승인/원 마감 안이며 원O.75 held를 기존 O.20603480에 더한 O.95603480부터 차감한다. N.25743975도 그대로 이월한다. 기존 실패를 재시험 성공으로 덮어쓰거나 정산되지 않은 비용을 환불하지 않는다.

## 실제 첫 생성 결과·목표 명칭 v404

r4 첫 LunaLuna/dining은 실제4HTTP200/stop·현재 입력의 초안 저장/current-render uncertain·짧은 PhysX preview를 통과했지만 `Go to table`에서 `SIM_TARGET_NOT_FOUND`로 전체FAIL. cost OpenAIUSD.0031857/held0/unknown0/lock0·소유프로세스 stopped, 로봇0이다. 저장 `dining_table`은 있으므로 모델 누락이 아니라 generic label이 전체문구만 매칭하는 제품 결함이다.

target matcher는 범용 library label의 head noun도 word-boundary로 찾는다. tabletop/stable 오매칭 금지·여러 후보면 기존 질문·명시ID 선택 유지·좌표/16접근/충돌/원본 불변. 실제 질문을 받을 때 benchmark operator는 현재 savedID 사전순으로 하나를 UI에서 답하는 고정 절차를 기록한다. 모델 관측 정답·가까운/쉬운 경로를 보고 선택하지 않는다. 기존 diagnostic expected-clarification 시험은 답하지 않고 그대로 idle 검증한다.

18goal+pilot4=22PASS(1.770초), Node6PASS; 처음 Node spawnEPERM 뒤 단일process 테스트로 검증/설치·ACL 변경0. 새 source404 cohort로 시작하며 r4FAIL은 덮어쓰지 않는다. carry-in N.25743975/O.95922050은 기존 노출+r3UNKNOWN.75+r4실제usage를 포함한다. raw와 이전실패는 계속 별도 분모다.

CPU diagnostics ON이 모든 trial에서 동일하다. CPU 함수 통계는 모델순위에서 제외하며 HTTP wall와 실제 diagnostic-mode 전체시간만 비교한다. 비계측 제품 latency로 일반화하지 않는다. profiling OFF가 필요한 미래 latency cohort는 새 동결 조건으로 실행해야 한다.

## v404 첫 블록과 텍스트 시험 경계 수정 v405

식당 repeat1의 5조합 actual39HTTP에서 Flash/Luna만 전체 기능 경로를 통과했다. Luna/Luna9HTTP·REPAIR_STALLED, Flash/Lightning8HTTP·repair정체, Qwen/Lightning6HTTP·dining_table 규격 실패, Luna/Lightning7HTTP는 FAIL로 보존한다. Flash/Luna9HTTP·quality수정2·최종uncertain→현재 Isaac 렌더→semantic도착≤.04→이동 중 Stop→reload/reset→종료 후 재열기까지 PASS다. 품질 PASS나 조합 확정 순위를 뜻하지 않는다.

6번째 warehouse/text Flash/Luna repeat2(job fd9dd8807d431426bb913501628a9d6e)은 실제2HTTP 응답과 5물체/지원 관계가 있는 초안을 저장했다. 사진용 render_history>0 조건을 browser와 collector가 text에도 적용해 시험을 실패/UNKNOWN으로 만들었다. 물체 inventory가 비었다는 뜻은 아니다. 수정은 text에서는 사진 관측/critic NOT_APPLICABLE_TEXT, saved plan SHA·기하·종료 후 재열기는 필수로 유지한다. 사진 조건은 완화하지 않는다. 원 text 저장물의 새 코드 읽기 전용 reopen은 PASS(plan ffd1d71b…83a)지만 **옛 실행의 전체 PASS 또는 비용 정산으로 바꾸지 않는다.** 소스 변경 후 옛 source freeze 재감사는 불가능하므로 그 예약 N.75/O.75와 이전 startup O.75는 계속 보수적으로 이월한다.

제품 목표 해석도 현재 persisted inventory의 room prop 부분들을 같은 목표로 묶고 rack/pallet tool group을 연결했다. storage는 범용 cabinet/shelf/bookshelf 후보군으로 해석하되 모든 후보를 남기고 질문한다. current saved ID의 head noun도 읽으며 모르는 목표를 가까운 물체로 대체하지 않는다. 라이다/실측/지원 정답을 추정하지 않는다. 예를 들어 창고 모델이 pallet을 unknown keepout으로 생성하면 그 사실은 품질/library 한계로 남고 ID로 향하는 기능 성공이 실제 pallet 복원을 증명하지 않는다.

99개 관련 Python 회귀(전체 chat/API·goal·benchmark·metadata closure·pilot) PASS 40.995초, Node6 PASS 18.298ms/syntax PASS. 처음 새 test fixture의 unsupported pallet kind 오류1은 box 일반 회귀로 교정하고 원 실패를 기록한다. 전체 suite 합산/새 Web build 성공으로 확대하지 않는다. semantic 도착 거리는 preview 도착과 별도 필드로 내보낸다.

v405는 같은 사진·prompt·goal·5조합·순서·공통 한도를 다시 동결하여 총60시험을 시작한다. v404의 5정산+1UNKNOWN을 새60 분모에 섞지 않는다. 새 carry-in은 **N1.06489857/O1.73263030**이며 이전 실사용 추정과 미확정 예약을 모두 포함한다. 원 사용자8시간/각USD5/08:43KST 마감은 연장하지 않았다. Text는 현재 제품의 실제 planner+local geometry 경로여서 observer/critic 모델은 호출되지 않는다. 같은 planner의 text 조합 차이는 다른 관측모델 성능 차이가 아니며 별도로 집계한다.

## 새 이동 완료와 과거 완료 분리 v406

v405 source에서 4개/26HTTP를 정산했고 추가 호출 전에 owner가 중단했다. LunaLuna4와 FlashLuna7은 host 시험 실패, FlashLightning8은 render appearance/layout/support 수정 정체, QwenLightning7은 PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE이다. 별도 [부분 metrics](../../outputs/benchmark-overnight-20261011/report-405-partial/public-pilot.md)는 code 변경 전에 전 원본 재감사·예정60/실행4/기능PASS0으로 저장했다. 후속 작업용 exclusive controller-log stop marker는 소유 wrapper를 다음 dispatch 전에 종료시켰으며 해당 5번째 job은 예약/모델호출 없는 NOT_RUN이다. 진행 중 요청은 정산/cleanup 후 정상 종료했고 프로세스를 강제 종료하지 않았다.

LunaLuna의 semantic_arrival.run_id가 initial preview와 동일(b7774117…b04)인데 새 검토 plan은58e0afd2…36e1이었다. 따라서 앞서 잠정 말한 새 목표 도착은 철회한다. FlashLuna는 이전 completed UI를 새 이동 완료로 읽은 뒤 실제 sample running에서 5초 timeout이다. 생성 모델 실패와 다르며 소스/전송/cap를 바꾸지 않고 시험·Run UI 동기화를 고친다. v404의 원 FlashLuna PASS는 run ID가 preview44c7f…45/semantic8b061…6ab/검토plan 동일로 실제 새 목표 도착이 확인됐다. 그래도 서로 다른 source 성적을 새60 비교분모에 넣지 않는다.

v406 공통 절차: 새 request/text/revision·cursor 이후 route event→UI 실제 current plan ID→그 plan의 engine/epoch/run ID와 sequence가 증가한 completed pose를 최대 기존150초 안에 확인→계산한 goal 거리≤.04→새 return plan의 running pose→paused+1초 후 동일pose. 감사도 이 증거 없으면 PASS를 거절한다. 과거 preview의 run/epoch/낡은event/가짜거리/누락receipt/이미완료Stop은 회귀로 차단한다. return endpoint가 preview 완료점과 겹치면 같은 이전 preview run에서 실제 관측된 최초 running 위치를 쓰고, 두 후보 모두 구분거리가 부족하면 실패를 보존한다. 원공간/LLM답안/충돌검사/실물 한도는 바꾸지 않는다.

App은 채팅 응답 중 이전 Run/Preview를 잠그고 그 상태를 표시한다. 실제 moving Stop은 계속 가능하다. 내부 Run plan ID를 DOM에 표시해 브라우저 시험도 UI에 적용된 정확한 계획을 기다린다. wrapper에는 후속 `pilot-stop-request.json`의 다음 dispatch 전 정상중단을 추가했다(현재 요청 정산 후/새 호출0). source 수정이 끝난 뒤 새 소규모 actual smoke를 먼저 검사하고 동일 동결의 남은 작업으로 이어간다.

관련 Python101 PASS40.738초·Node8PASS·Web52PASS/type/buildPASS. 최초 e2e 중복 const syntax는 실제 재호출 전에 교정/syntax재검증. Core302/Provider332의 앞선 전체회귀도 PASS며 겹침 합산하지 않는다. 원 r3/404UNKNOWN 예약은 이월하고 새 carry-in은 **N1.11227037/O1.74196590**이다. 각5 상한/원 마감 불변. 405 source/자산523 로컬 ZIP(SHA2e81a019…cb68)도 보존했으며 계정registry/키/사진은 포함하지 않았다. 아직 최종 모델추천·품질 인수 완료가 아니다.

후속 전체 Web 회귀47파일/446시험 PASS24.10초, 기존 jsdom canvas/번들 크기 경고는 실제 렌더나 성능 인수를 대신하지 않는다. 실제 재개는 **cohort-406/manifest.json SHA677f31a93d3dfc9110be331cdc9eb7ddece9b837c430e2e2b46d3a8b8c9e1e7c**와 source/자산524개를 사용한다. 위403 동결 행은 최초 계획의 이력이며 서로 다른 소스 성적을 합치지 않는다. 17:06UTC 소규모2건부터 actual 호출을 시작했고 원08:43KST 마감·각USD5·기존노출/held를 그대로 적용했다.

## 복귀 UI 문구의 중복과 소규모 결과 v407

406의 LunaLuna4HTTP/FlashLuna7HTTP 두 시험 모두 current route plan ID와 실제 semantic run ID가 같고 도착거리 .039803/.039540m였다. 그러나 복귀 route review 후 과거와 새 `SIM route ready` 채팅 문구2개를 전역 locator가 동시에 찾아 strict-mode FAIL로 종료했다. 전체 기능PASS0/예정60/실행2/11HTTP이며 동결 중 원본 재감사 [406부분보고서](../../outputs/benchmark-overnight-20261011/report-406-partial/public-pilot.md)를 보존했다. 모델 실패로 세지 않으며 movingStop/reload/reset/재열기 완료로 확대하지 않는다. 정상 정산/소유 cleanup 후 추가0, source/자산524 ZIP SHA868526ae98318d83e086c43833841ed28112077a6eea5ba5ac9a5bd37c036b25 보존.

benchmark readiness는 이미 확인하는 current `Simulation route` region의 exact plan ID와 Run 활성 상태로 판단한다. 중복된 과거 채팅 문구의 전역 검사는 benchmark에서만 제거했고 새 Run/receipt/거리/Stop 검증은 유지했다. 일반 legacy journey 문구 검사는 보존한다. Node8 PASS19.67ms/syntaxPASS; 제품/source build 변경 없이 e2e 시험 검사만 수정했다. 새407로 동결·같은조건 실제 작은시험 후 남은 순서를 계속한다. carry-in N1.13080437/O1.75276130, 원한도5씩/기간 불변·UNKNOWN 예약 이월·인간품질평가0/전체PARTIAL이다.

407 manifest SHA **d419c730ac154e5cc20ac2f55fe3ed4408fdd896441cf0b0078e329deab5b3b4**, source ZIP524 SHAca45d8cd7ed3d5c097c4271c6a913a727e1af4ca5a8ef6e5e9e12486ff62118f. 최초 LunaLuna4HTTP 및 FlashLuna7HTTP의 actual current-render→semantic도착→별도return movingStop/stable→reload/reset→닫힌 backend 재열기가 모두 PASS이고 새 navigation auditor도 PASS다. LunaLuna 도착거리 .039822m/최종렌더uncertain/repair0/저장5이며 사진품질PASS가 아니다. 두 시험 정산 후 N1.15147527/O1.76309990 노출에서 동일 campaign의 미실행 예정58건을 이어간다. 소스·prompt·평가기준·순서·한도는 바꾸지 않으며 옛cohort 결과를 합산하지 않는다.

17:36UTC 진행 snapshot은13정산/7기능PASS6FAIL/65HTTP·14번째실행 중이다(최종 통계 아님). 첫 식당 반복3/5, 텍스트 창고3/5이며 실패에는 current-render 불일치, below-floor, support-placement unavailable, semantic target no-reachable-approach가 있다. 모델 단독 성능/사진정밀도 점수로 확대하지 않는다. worker는 같은 frozen campaign의 예정60만 계속 실행하고 원본/환경/source 및 비용/시간 gate를 각 job에서 검사한다. 기존 native heartbeat `twinpulse` ACTIVE30분에 소유 PID 중복방지/변동없으면무알림/종료후원감사→최종표·추천·재사용방법→PAUSED를 연결했다. 동결 소스의 실제 일괄 실행을 종료한 것이 아니며 수동 사용자 재지시를 기다리지 않는다.

해커톤 [공식 규정](https://nebiusglobalaihackathon.devpost.com/rules)과 [NVIDIA Lightning 문서](https://docs.nvidia.com/nemotron/nightly/nemotron/lightning35/README.html)를 2026-10-11 다시 확인했다. Apps&Agents의 Nebius Nemotron runtime 사용과 선택 조합을 대조하되 참가 적합성 확정으로 표시하지 않는다. PhysicalAI의 별도 ServerlessJobs/동작 데모·제출 요건은 로컬 Isaac pilot로 충족했다고 표시하지 않는다. 새 cloud resource/배포/robot 실행0.
