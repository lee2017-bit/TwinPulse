# Nemotron 신뢰성·초기화 개선 실행 기록

2026-10-07 KST · Baseline v1.0.316. 사용자의 “그래 진행시작하자”에 따라 H0–H6 계획을 실행했다. **실제 텍스트 SIM 경로는 검증했으나 실제 사진 생성은 실패했다. H5/H6 전체 인수·전체 실물 데모는 완료가 아니다.**

## 단계별 결과

| 단계 | 이번 결과 | 미완료 |
|---|---|---|
| H0 | 기존 Nano/Gemma 인증·정확한 모델 접근·공식 가격/이미지 capability; 텍스트 기준1회 FAIL 보존 | 사진 paired baseline·잔액/청구서 |
| H1 | 실제 transport의 단계/usage/finish reason·로컬 redacted response/해시·durable 비용 예약 | timeout의 원격 완료/청구 |
| H2 | Site2.2 observer+planner 공통 추가 수정 최대1회·실제 executor 검증 | 모든 사진의 유효 생성 |
| H3 | 실제 stage/repair/경과·terminal 원인·reload 비재실행; built5case PASS | 전체 데모 정상 인수 |
| H4 | torque-only 분류·승인 MotorOFF 후 동일 boot/release fresh readback; offline PASS | 실제 초기화/새release 정지·driver·scan/odom/TF·정합 |
| H5 | text matrix·현재 코드 live→chat→actual Isaac Build/도착/Stop/reload PASS | 필수 P01 사진→Isaac, P02/P03·24작업 전체 기준 |
| H6 | Python180·관련89(중복)·Web341·build·built5case·현재 실제 text runtime·문서 동기화 | H5 전체 인수·C3–C6 현장/최종 패키지 |

로봇은 OFF로 취급했다. SSH/serial/센서/모터/전원/배포/실물 시험 **0**. 설치·시스템 설정·commit/push·타 프로세스 강제 종료·새 agent **0**. 기존 dirty 변경·원본·과거 FAIL은 보존했다. fake 응답은 오프라인 검증에만 사용했으며 제품 fallback이나 live acceptance에 섞지 않았다.

## 제품 경로 변경

### 요청 진단·회계·늦은 응답

`reliability.py`는 기존 Urllib 호출을 감싸며 다른 provider/proxy를 만들지 않는다. 인증 헤더·key·입력 사진은 저장하지 않는다. 응답은 앞262144 bytes까지 redacted local-only로 저장하고 수신 전체 길이/해시·capture 길이·잘림·usage·HTTP/finish/error facts를 남긴다. App DTO는 whitelist 진단만 제공한다. reasoning을 실행 가능한 content로 승격하지 않는다.

USD1/max60 공유 manifest 하나로 full context+max output 최악 금액을 dispatch 전에 예약하고 O_EXCL lock으로 중첩 paid 요청을 막는다. 재시작으로 요청 수/비용이 초기화되지 않는다. 알려진 usage는 pinned 가격으로 추정하고 취소/timeout·미반출 결과는 전체 예약을 유지한다. evidence 저장 실패도 자동 재호출/환급으로 처리하지 않는다.

초기 owned photo trial은 teardown 때 아직 끝나지 않은 HTTP 원본을 잃었다. 해당 ready PID 및 stopped supervisor/result hash로 local owner 종료를 확인한 **명시적 reconciliation**으로 lock만 해제했다. remote completion/billing UNKNOWN·full reservation은 유지한다. 살아 있는 owner 무시·자동 stale-lock 삭제·lost-result replay는 없다. 이후 wrapper는 owned teardown 전에 bounded evidence drain을 수행한다.

P04 actual trial에서 `wait_for(90s)`가 취소해도 `asyncio.run()`이 default executor의 blocking HTTP 종료를 기다려 App 실패 표시가 늦어지는 결함을 발견했다. 전용 inference executor 최대2·admission 최대2·무queue로 수정했다. busy 거절은 HTTP/비용 예약 이전에 일어난다. **제품 timeout은 즉시 outcome_unknown으로 고정, 늦은 응답은 evidence/accounting만 갱신·장면 미적용**이다. 기존90s와4000/8000 cap은 유지한다.

### 수정·prompt·scene 검사

같은 모델/endpoint/원래 입력/schema로 완료된 JSON·잘림·근거·기하 오류에 한해 추가1회 수정한다. observer에서 수정권을 쓰면 planner에는 남지 않으며 정상 observer는 재사용한다. 인증/HTTP/network/timeout·wrong model/refusal/지원 밖 envelope는 자동 재시도하지 않는다. 전체 남은 기한5초 미만에는 새 repair를 dispatch하지 않는다.

Site2.2에는 center-based floor/yaw footprint, room item z=height/2, 검토 inventory object ID와 visual entity ID 구분, 요청된 가구만 선택하도록 명시했다. 치수는 위치로 오인하지 않도록 named width/depth로 전달하고 legacy2.1 배열은 유지한다. executor 오류는 offending call/ID·usable floor bounds·겹친 footprint와 분리 방향·invalid/allowed observation ID를 포함한다. clearance/근거 규칙을 완화하거나 partial JSON을 적용하지 않는다.

chat2.2는 repair1, legacy 기본은0이다. site_plan_version을 non-secret input setting으로 허용했으며 해당 setting 없는 기존 hash/직렬화는 변경하지 않았다. 모델 Python/shell 실행은 추가하지 않았다.

### 채팅·로봇 안전 초기화

workflow→conversation→Web에 현재 request/sequence·stage·model·실제 경과·repair 횟수·validation/terminal 원인을 전달한다. 자동 수정 중 추가 클릭을 요구하지 않으며 raw/credential은 공개하지 않는다. 기존 현재 질문·Stop/Force·restore 비재실행을 유지한다.

torque ON은 모터 토크 고장이 아니며 바퀴/명령0일 때 초기 준비 필요로 분류한다. 승인 준비 후 같은 boot/release의 fresh snapshot에서 torqueOFF·바퀴0·명령0·포트 복원·현재 배터리 조건을 확인한다. ACK만으로 완료하지 않고 stillON/newboot/포트 실패에는 정확한 BLOCKED 원인을 남긴다. 초기화의 최초 BrokerError code를 보존한다. 초기화 성공을 정지시험·센서·정합·임무 자격으로 확대하지 않는다.

scan200ms/input250ms/segment50ms/자율 .03m/s·.20rad/s·45s·physical lock/manual 계약은 불변이다. 이번 source는 로봇에 배포하지 않았다. 과거 current release `1cede5493f5a4ade3c46c49049dc9752a8fef3476b76f5a0cc214e16e9ade1ba`의 field PASS를 이번 실물 PASS로 전용하지 않는다.

## 실제 평가와 분모

증거 root는 `artifacts/agent-reliability-20261007`이며 campaign.json/summary.json/각 result.json을 함께 확인한다. probe·역사적 source 결과를 최종 성공률로 합산하지 않는다.

- **48/60 requests**, usage 가격 추정+불명 full reservation 합계 **USD0.07615086**. 실제 청구서/잔액 미확인. 실패/repair/probe 모두 횟수에 포함했다.
- UNKNOWN2: `713b03f1bafa45439e678c3985a3c6dd`(종료한 owned photo worker), `5bc3e58733654e909af5008c70717845`(observer timeout). 원격 결과·청구는 불명이다.
- 기존 Nano/Gemma의 공식 catalogue metadata로 각각 입력/출력 USD.06/.24 및 .1/.3 perM 가격을 pin했다. 모델 목록 존재·가격 확인은 모든 입력 성공이나 무과금 확인이 아니다.

| 실제 text 실행 | 최초 valid | repair 허용 후 valid | latency 평균/중앙/최대 초 |
|---|---:|---:|---|
| baseline T01 1회 |0/1|repair 비활성·0/1|16.312/16.312/16.312|
| 첫 T01–04×2 matrix |1/8|5/8|32.422/32.688/50.125|
| 수정 matrix r2 |4/8|7/8|29.623/25.758/53.125|

r2 T03은 실제 한국어2회다. valid7개는 requested-kind coverage 통과·extra kind 없음. 주요 관계는 **NOT_SCORED**, 사진 치수는 **NOT_MEASURED**다. 작은 표본·서로 다른 prompt source이며 일반 SLA가 아니다. 최종 named-dimension/timeout 수정 후 전체8작업을 재호출하지 않았으므로 r2 비율을 최종 소스 성능으로 바꾸지 않는다.

실제 저장 live room의 동일 초기 revision으로 T05–08×2 기존 결정적 API 처리 **8/8 PASS·provider0·이번 Isaac NOT_RUN**. chair만 Add/bed만 Change·원본 보존, 가능한 SIM route 준비만 수행, 없는 target 거절을 확인했다(`local-product-cases/result.json`). 모델 성능 분모에 넣거나 일반 자유 형식 자연어 전체 지원으로 확대하지 않는다.

### 현재 source 실제 텍스트 인수

`live-chat-isaac-text-final/result.json` **PASS**:

1. 새 텍스트→현재 Q1 하나→사용자 선택 후 실제 Nano 호출·Site2.2 의미 검사·저장 artifact.
2. 자동 Build 준비(자동 Run 아님)→actual current Isaac frame→명시 Run→Burger PhysX 도착 **.039692969779782955m**, 기존 tolerance .04m 이내.
3. 다음 채팅 bed goal에 current idle pose 이용→접힌 Twin에서 채팅 Stop→paused pose 불변.
4. reload Build/Run 비재실행·과거 승인 재사용 금지, 명시 reset 후 illustrative preview·Physics telemetry 없음.

최초1call·repair0·**15.297s**, prompt1264/completion2860, 가격 추정USD.00076224. 관련6inference source 전후SHA 불변·Web hash 기록·pageerror0·owned backend/engine 정상 정리(stopped/owned=false). 가짜 provider/mock Isaac/실물 이동이 아니다. 앞선 text geometry/setting 실패도 보존했다.

### 사진은 실패: 현재 핵심 병목

- P01 사용자 방은 기존 검토 inventory24개(필수 route-risk19개)를 planner에 주는 **assisted** 경로다. 순수 사진 인식 성공으로 채점하지 않는다.
- `photo-default-policy-r3`: Gemma34.140s valid observation 뒤 Nano8000 cap length rejection25.063s, 같은 원본 repair도25.187s length rejection. 총84.390s·valid plan0·raw/usage 보존. 잘린 reasoning/없는 content를 JSON으로 승격하지 않는다.
- 최신 P04 원본 다른 방(검토 inventory 없음) actual 제품 trial은 Gemma64.899s 관측 뒤 Nano약41s·8000 length rejection. 전체90초 내 valid plan이 없어 FAIL·Build/Run0. 이때 발견한 timeout 화면 지연만 이후 blocking fake/API/built 회귀로 수정했다. **수정 후 P04 actual 성공은 주장하지 않는다.**
- reasoning_effort=none probe는 HTTP200/stop이어도 content=null·JSON이 reasoning에만 있어 거절했다. template enable_thinking=false probe는 빠른 content 뒤 겹침/불필요한 catalogue/가짜 visual ID로 실패했다. 두 옵션은 explicit 실험뿐이며 **기본 제품에 미채택**이다.
- P02 고정 floor-hazard×2 NOT_RUN. P03 과거 warehouse 원본 파일 부재로 NOT_RUN(과거20260925 PASS 대체 금지). P04 actual1회 FAIL은 matrix2회 완료가 아니다. 따라서12조건×2/24의22·23성공 목표 **미달/전체 평가 미완료**다.

시간/cap 확대가 무조건 해결한다는 증거는 없다. 다음은 확보 raw에서 사고/출력·근거·geometry 비용을 분리하고 compact typed layout와 검증된 결정적 geometry 배치 등 계약 축소 후보를 검토한 뒤 동일 사진을 제한된 live 묶음으로 확인한다. 다른 모델/endpoint 자동 변경·fake 장면·partial plan 적용은 대안이 아니다.

## 최종 회귀·실패 보존

- Python **180/102.042s PASS**: chat conversation/initial state/robot preparation/reliability/scene changes/input integrity. 관련 provider/Site **89/24.628s PASS**는 위180과 중복이며 합계 고유수로 표시하지 않는다. reliability 파일 단독22개 포함.
- Web **341/43files/24.10s PASS**·TypeScript/production build PASS. 기존500KB chunk warning은 남아 있으며 실패가 아니다.
- built Chrome/API `chat-single-step-20261007-08ff0bc3/result.json`: text/photo/retry/repair/timeout **5/5 PASS**, fixture·paid0·robot0·Isaac NOT_RUN. 실제 repair progress/추가 클릭 없음, blocking3s 응답보다 .3s timeout 실패 표시가 먼저 도착, late scene 미적용·reload 비재시도 확인.
- actual blocking API 회귀: HTTP worker가 살아 있을 때 failed/unknown·noartifact/nocommand·예약 유지/재dispatch 거절, release 후 raw/usage 보존. worker2개 점유 때3번째는 reserve/HTTP 전에 거절.
- 첫 회귀의 없는 module 이름, 새 deadline fixture의 context1000<max_tokens8000 오류, 첫 JPEG→PNG MIME 오류는 final PASS로 덮지 않았다. 올바른 module/context/원본 basename으로 수정 후 재검사했다. JPEG 오류의 paid dispatch0.
- git diff --check PASS(기존 CRLF 경고). 테스트 소유 runtime만 정상 종료. 임시 로컬파일/API 권한을 사용했고 ACL/WSL 설정 변경·권한 거부 우회는 하지 않았다.

화면은 built fixture `repair/automatic-repair-progress.png`, `timeout/timeout-before-late-response.png`와 actual text-final의 `generated-physics-arrived.png`, `generated-reset-preview.png`, `journey-mobile.png`에 보존했다.

## 정확한 잔여·다음 순서

1. **로봇 없이 우선:** P01/P04 compact planning/geometry·evidence 계약 개선→동일 입력 actual photo→Isaac 인수. 현재 완전한 사진 데모가 준비됐다고 말할 수 없다.
2. P03 원본·P02/P04×2 고정조건, 최종 source text matrix/관계 채점·24제품 평가. 공유 비용 기록을 유지하고 새 예산/모델/기한 정책을 승인 없이 확대하지 않는다.
3. **별도 현장 승인 후:** 읽기 전용 상태→필요한 MotorOFF/readback→현재 boot/release 필요한1회 정지시험→corrected driver scan/odomTF·lifecycle→실측 profile·방 정합→통과한 짧은 목표/Stop.
4. 실제 임무·loop/배터리·progress-stall 보정과 최종 C3–C6/패키지 전체 인수. 직접 motor load 측정은 UNSUPPORTED다. 합성 transport/ACK/SIM 도착은 실물 PASS가 아니다.

**whole_demo_ready=false · physical_validation=NOT_RUN · H5/H6 PARTIAL · C3–C6 PARTIAL.** 사진 모델 계약/출력 병목은 로봇 전원으로 해결되지 않는다.

## 공식 참고

[Nebius Chat Completions](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion), [공식 OpenAPI](https://api.tokenfactory.nebius.com/openapi.json), [NVIDIA Nano FP8 model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8)의 옵션을 확인해 explicit probe했다. 명목 지원과 actual endpoint 응답/품질을 구별하며 성공 판정은 local 제품 증거를 기준으로 한다.
