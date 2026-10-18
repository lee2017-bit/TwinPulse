# 실제 모델 조합 전체 경로 벤치마크

## 결제 해제 후 미실행 3건 재개 — v396

2026-10-10 사용자 최신 요청 ‘그래 그럼 다시 시작해보자’를 미실행 `flash-luna-3`, `luna-lightning-3`, `flash-lightning-4`의 명시 재개로 기록했다. 기존 18:20 마감 캠페인은 수정하지 않았다. 별도 `outputs/model-combination-benchmark-resume-20261010/resume-authorization.json`에 20:01부터 최대2시간의 새 bounded 창을 기록하고 실제 20:06에 종료했다. 전체 모델 비교나 추가 무제한 반복을 새로 시작하지 않았다. 기존 사진/후보결속 파생렌더/등록 목적지와 동일 검사 조건, 기존 총USD5/1을 유지했다.

원16 actual 시험을 먼저 raw/dispatch/validation/usage/SHA/설정 불변 감사했다. 옛 사용량+무usage held+별도 Nano probe USD.00000168까지 차감한 잔여상한은 Nebius4.76646311/OpenAI.81266440였다. 새시험의 보수적 단회 grant는 .81/.79/1.00이며 공통 출력20k/요청300초/총900초/initial420·repair300·final180/최대repair3·정체2/24HTTP는 불변이다. 제품의 inference/compiler SHA64289a04a6160139c4dc481f53edc04ef3cf2248a82d84e3120d78cdcf545c24도 동일하다.

| 새 시험 | 전체 결과 | 실제 HTTP / repair | 관측 / 선언 / 최종저장 물체 | 원인·근거 | 전체 wall |
|---|---|---:|---:|---|---:|
| flash-luna-3 | FAIL | 8 / 3 | 21 / 18 / 0 | 옷걸이 region 바닥배치 PHOTO_LAYOUT_REGION_FULL·수정정체 REPAIR_STALLED, 렌더/이동 미도달 | 86.282s |
| luna-lightning-3 | PASS | 6 / 1 | 14 / 10 / 10 | 실제 기하수정1 후 같은 최종후보 Isaac 렌더·저장·PhysX도착오차.039626669m·다음침대목표/채팅Stop·1초정지·reload/reset·종료후재열기 PASS | 88.797s |
| flash-lightning-4 | FAIL | 9 / 3 | 24 / 21 / 0 | A9 region 바닥배치 PHOTO_LAYOUT_REGION_FULL·REPAIR_STALLED, 렌더/이동 미도달. 수정요청3과 보존patch2는 구별 | 89.093s |

실행ID와 원본 폴더(사진·원응답은 사적 로컬 보존이며 공개표 제외):

- Flash/Luna: `e8d99f82b8934942a0a6b3a192e11c8f` → `outputs/model-combination-benchmark-resume-20261010/flash-luna-3/run-1/runtime/provider-evidence/`.
- Luna/Lightning: `01157049f3ef45cd9a298f163dcb2f4c` → 같은 root의 `luna-lightning-3/run-1/runtime/provider-evidence/`.
- Flash/Lightning: `5e3ae186871e4bea9108432a0c1545d5` → 같은 root의 `flash-lightning-4/run-1/runtime/provider-evidence/`.

두 실패는 이번 실행의 bounded region packing 탐색이 성공하지 못했다는 의미이며 **방 전체 연속공간에 배치가 불가능하다는 증명은 아니다**. 첫 실패의 모델 추정 방3.4×4.2m/두번째3.5×4.2m를 특정 사진 정답치와 비교해 거절한 것이 아니다. 실제 응답은 모두200/stop; 새 결제402·출력length·UNKNOWN은0. 기하/범위 제안·packing/rollback/진전 판정과 모델 수정의 상호작용을 원 request/patch/검사로 더 분석할 잔여이며, 특정 모델만 나쁘다고 확정하거나 조건을 풀어 가짜 PASS로 바꾸지 않았다.

동일 최신코드 결과는 **13건/5 full PASS**: LunaLightning2/2(그중 실제수정회복1), FlashLuna1/2(그중실제수정회복1), LunaLuna2/5, QwenLightning0/2(옛4021 포함), FlashLightning0/2. 서로 다른 코드까지 전체19 actual/129HTTP/8PASS11FAIL이며 no-call preflight1은 별도다. 물체수와 관측 범위부터 달라 LunaLightning2/2는 잠정적인 통합 안정성 신호일 뿐, 장애물 인식 recall·사진정밀도·지원관계품질 우승이나 운영신뢰성 입증이 아니다. 최종critic uncertain/독립사람판정·실측 없음/1사진·짧은SIM 제한은 유지한다.

### 재개 비용·감사·공개표

새23HTTP 사용량 추정 Nebius.02390286/OpenAI.01869920, 새 held0. 이전사용+별도probe를 포함한 총usage N.18972519/O.09103480, 기존 held N.06771456/O.115는 그대로. 보수노출 **N.25743975/O.20603480**으로 총USD5/1 이내이며 청구확정액이 아니다. 원 캠페인 파일·probe SHA는 종료까지 불변, 새3건 raw/dispatch/검사/장부 감사PASS·UNKNOWN0·pending lock0·모든소유launcher cleanup succeeded·제품/inference/전역설정/옛장부 불변. 재정예산소진은 이번에도 발생하지 않았다.

보고서회귀10/새 carryover·held·probe 예산검사3 PASS; Provider315/Core302/Web443/type/build는 직전 v394 검증 이력으로 이번에 다시 실행한 것으로 쓰지 않는다. 초기 기본권한의 새 기록폴더 생성 거부를 보존하고 정상 승인된 로컬 명령으로 정확한 폴더만 생성했다. ACL/시스템설정 변경·거부 우회·타프로세스 강제종료0. 새 orchestration helper는 기존 runner를 사용하는 별도 시험 도구이며 제품 코드 변경이 아니다.

최종 생성 보고서 감사 `FINAL_REPORT_AUDIT_PASS`: 이전 공개 trial16개가 필드별 불변, 전체19/129HTTP·최신13/5PASS 분모 일치, 원역사402 보존/현재block없음/미실행3잔여0, 원사진·좌표·raw 제외 및 physical/invoice PASS 주장없음, 합산예산상한 검사PASS. `git diff --check` exit0; 기존 dirty worktree의 LF→CRLF 안내는 보존하며 이번 수정 오류로 집계하지 않는다.

공개표/JSON1.3은 역사402와 현재provider block없음을 구분하고 이전+새 같은코드 결과를 합산하되 다른코드는 cohort로 분리했다. 옛 공개표는 resume 폴더의 before-resume snapshot, 옛 원16 장부/failed 원문/미실행 당시 상태는 원 캠페인에 보존한다. probe는 모델성능 분모에 합산하지 않는다. 사적 사진·좌표·원문·raw·key/auth 공개0·commit/push0.

20:08KST 사용량UI 새로고침 관측: Billing Active/잔액150.00, Last updated09:51UTC(18:51KST). 집계시각은 probe10:47UTC 및 재개11:01UTC 이전이므로 **이번 Account balance 실제 차감과 청구는 여전히 미확인**이다. 화면이 바뀌도록 불필요한 paid 호출을 추가하지 않았다.

### 현재 잔여

결제 때문에 NOT_RUN이던3건은 모두 실행했다. 다음 제품우선은 (1) 두 원packing 실패의 수정정체/범위·진전·rollback 근본분석 (2) ready 후 generic 목표 접근가능성/거절·수정 연결 (3) 별도사진·텍스트-only·독립품질/실측 검증 (4) 기존CPU self>cum2건의 프로파일교정 (5) 기존 전체도메인·패키지·해커톤요건과 현장 LiDAR정합/실물자율목표·Loop 인수다. 새로운 제품수정이나 새모델호출을 이번 bounded 3건 종료 후 시작하지 않았다. 전체제품/실물은 PARTIAL/wholefalse, 로봇OFF·실물시험0·예약PAUSED 유지.

아래 v395 이하는 당시 기록이다.

## 결제 전환 후 최소 요청 확인 — 별도 시험

2026-10-10 19:47 KST 사용자 요청: 차단을 직접 해제했으니 조금만 사용해 Account balance 차감을 확인한다. 전체 벤치마크 재개가 아닌 독립 연결/결제 관측이다. 브라우저 새로고침 후 `Billing: Active`, 체험 종료후 사용중지 안내 제거, 호출 전 Account balance USD150.00을 확인했다. 설정/충전/카드/키를 변경하지 않았다.

기존 TwinPulse 등록 Nebius 키는 OS 보안 저장소에서 해당 origin에만 사용했다. metadata GET1로 현재 Nano 가격 input0.06/output0.24 USD per million 확인, 비개인 `Reply only OK.` 입력의 actual POST 딱1회/출력상한16/자동재시도0/보수적 비용상한USD0.001. 19:47:16–18 KST 실행ID `336d9d21-5815-4e42-b8af-6c64d6bc322b`, HTTP200/finish_reason stop/OK, input20/output2/total22, 현재 가격 기반 추정USD0.00000168. 이 작은 출력상한은 연결확인 전용이며 제품/벤치마크20k 설정은 변경하지 않았다. 원문 결과/usage/request/SHA 및 승인 기록은 `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\outputs\nebius-balance-probe-20261010\result.json`; 키/인증헤더 저장0, 전역설정 불변.

요청 후 거래UI 새로고침에서도 Account balance150.00. Usage의 Full numbers로 읽은 Nano 누계 input0.899556M/USD0.05397336, output0.609739M/USD0.14633736이나 **Last updated09:14UTC(18:14KST)는 이번요청10:47UTC(19:47KST)보다 이전**이다. 월 Transactions의 기존 Trial +USD2.23/Consumption -USD2.23은 이번1요청의 차감 근거가 아니다. 따라서 API 차단 해제는 직접확인, USD150잔액에서의 실제 이번 차감·카드청구는 아직 미확인. 소수둘째자리 잔액/집계지연을 억지로 보이게 하려고 추가요청하지 않았다. 이전402의 trial 중지정책 원인 가능성은 높아졌지만 당시 실제 rejected 원문·비용예약을 수정/소급환불하지 않았다.

원 캠페인16fresh/106HTTP·성공/실패·미실행3·held금융예약·PARTIAL_PROVIDER_BLOCKED/예약PAUSED 및 제품잔여는 그대로다. 이번1콜은 별도 결제probe로서 모델성능 성공률 분모에 합산하지 않는다. 새 사진/파생렌더/Isaac/로봇/OpenAI/설치/commit/push0. Baseline/Memory v1.0.395는 이 환경변화만 동기화한다.

2026-10-10 KST · 15:24 부분 종료, `PARTIAL_PROVIDER_BLOCKED`. 원본 사진 한 장을 반복하는 소규모 내부 통합 벤치마크이며, 일반적인 사진 복원 성능이나 실물 주행 성공률을 뜻하지 않는다. 실제 호출과 저장 응답 재생을 분리하고, 실패도 원래 분모에 보존한다.

## 최종 결과 — Baseline v1.0.394

14:20부터 약 1시간 동안 실제 모델 시험 16건/106 HTTP를 실행했다. 코드 변경 전 이력까지 전체 경로 PASS7/FAIL9이며 호출0의 preflight 실패1은 모델 분모에서 제외한다. **서로 다른 코드 결과를 하나의 모델 성공률로 합치지 않는다.** 변경 후 inference/compiler SHA `64289a04a616…`의 동일 조건 표본은10건/PASS4다. 원본 사진·문구, 출력20k/요청300초/총900초/수정3·정체2/24 HTTP 정책은 같고, 보수적 재정 승인액은 USD.82–1.00으로 감소했다. 재정 승인액 자체의 소진은 발생하지 않았다.

| 관측·critic | 설계·repair | 최신 코드 전체 PASS / 시도 | 주요 결과 |
|---|---|---:|---|
| GPT6 Luna | Nemotron Lightning | 1/1 | 실제 전체 경로 통과, 최종 critic uncertain |
| DeepSeek Flash | GPT6 Luna | 1/1 | 기하2+품질1 실제 자동수정, 재렌더2 후 전체 통과 |
| GPT6 Luna | GPT6 Luna | 2/5 | 기하 실패1, 침대 접근경로 실패1, 렌더 외관 수정 실패1 |
| Qwen3.8 | Nemotron Lightning | 0/2 | 관측 배치 모순1, 품질repair의 공급자402 거절1 |
| DeepSeek Flash | Nemotron Lightning | 0/1 | 배치 공간 부족을 수정하지 못하고 정체 종료 |

표본 수가 달라 확정 순위를 매길 수 없다. 최신 Luna/Lightning 표본은 저장9개, Flash/Luna는20개로 선언한 물체 수부터 다르므로 적게 생성해 통과한 것을 인식·복원 품질 우승으로 부르지 않는다. 최종 통과7건의 렌더 critic은 모두 uncertain이며 독립 사람 평가/실측은 없다. 공개용 영문 결과표·JSON은 `docs/benchmarks/model-combinations-20261010.md`/JSON에 역할·코드 cohort·원 분모·Wilson95·시간·비용·개별 시험 alias와 실패를 남겼다. 원 사진·집 좌표·원문·키·raw는 포함하지 않고 commit/push하지 않았다.

### 실제 경로와 실패 진단

전체 PASS는 일반 채팅 승인→실제 외부 관측/설계→전체 기하→현재 후보에 결속된 실제 Isaac 렌더 critic→필요한 모델 수정/재렌더→동일 최종 후보 저장→PhysX 짧은 준비경로 도착(≤.04m)→침대 목표 준비/Run/채팅 Stop·1초 정지→reload/reset→소유 프로세스 종료→backend 종료 후 schema2.1/관계·SHA 재열기까지 통과한 것이다. 첫 준비경로는 짧은 SIM 이동이며 방 전체 임의 목표 최적성이나 실물 데모/루프 인수는 아니다.

Luna5는 생성·첫 실제 도착오차.039596m까지 성공한 뒤 `SIM_TARGET_NO_REACHABLE_APPROACH`로 침대 목표를 거절했다. 원 저장 장면/도착 pose를 읽기 전용으로 재검사하면 기본 외부 접근 후보16개 중14개는 `START_OR_GOAL_BLOCKED`,2개는 `NO_PATH`로 동일 실패한다. 허용된 접근 여유 .30–1.10m를 .05m 간격으로 진단해도 통과 후보가 없었다. 추가 모델 호출/원 장면 변경/안전 clearance 완화는0이다. 단순 UI15초 timeout이나 Wi-Fi 문제로 기록하지 않고 `simulation_navigation`으로 분리했다. 이는 bounded 후보 검사 근거이지 모든 연속 공간 경로의 불가능성 증명은 아니다. 생성의 기하 PASS가 다음 자연어 목표의 접근 가능성을 보장하지 않는 잔여를 확인했다.

Luna7은 실제 렌더 외관 불일치를 수정2회에서도 해소하지 못한 `REPAIR_STALLED`다. 출력 소진은 이번106건에 없었다. 기존 원 실패와 patch의 phase failed/pending을 최종 PASS로 덮어쓰지 않았다. Flash/Luna2의 fresh 실제 회복1건은 저장 응답 재생이나 주입 오류 회복과 구별한다.

### 비용·중단·감사

104 HTTP200/완결stop 응답, HTTP4001/HTTP4021, 결과 UNKNOWN0·pending lock0. 17개 기록의 raw/dispatch/usage/검사/checkpoint/최종 plan·frame SHA와 기존 사진·전역 설정·과거 장부 불변을 읽기 전용 감사했다. 실행별 `ordinary_live_audit`와 원본을 보존한다. HTTP200 자체는 host 품질검사 PASS가 아니다.

이번 신규 사용량 추정: Nebius USD.16582065 / OpenAI USD.07233560. usage가 없는 거절 예약은 Nebius .06771456 / OpenAI .11500000으로 유지한다. 합계 노출은 **Nebius .23353521 / OpenAI .18733560**, 승인USD5/1 미만이다. 이는 청구서나 계정 잔액 확인이 아니다.

Nebius의 실제 `Payment Required: You have exhausted your budget. Please add funds to continue using the API.`402 이후 해당 공급자의 유료 호출을 차단했다. 현재 USD150의 계정/프로젝트/Token Factory 적용 여부는 미확인이다. 충전·결제·key 전환·paid 재시도는 하지 않았다. 변경 후 두 번째 mixed 반복 `flash-luna-3`, `luna-lightning-3`, `flash-lightning-4`는 NOT_RUN으로 남긴다. 미영향 OpenAI 단독은 미리 고정한 최신 코드5표본(3–7)을 끝냈다. 반복해도 같은 외부 잔액 차단이어서 불필요한 호출·대기로4시간을 채우지 않고 native `twinpulse` 예약을 **PAUSED**로 중지했으며 실제 상태도 확인했다.

### 시간·프로파일·회귀

최신 Luna 단독 전체 p50/p95는90.093/103.247초, HTTP wall 합의 p50은29.781초다. 실패도 포함한 작은 표본이고 GPU 추론시간/통제된 부하 측정이 아니다. 최신 Luna/Lightning 1건은84.531초 전체/25.609초 HTTP, Flash/Luna 회복1건은148.094초 전체/82.111초 HTTP다. 따라서 이 표본에서 눈에 띄는 대기는 HTTP와 Isaac/App 준비·검사이며 임의로 한 병목 함수의 총시간으로 단정하지 않는다.

CPU profile의 Luna2/Luna4 일부 행에 self time > cumulative time 불일치가 발견됐다. 원 기록을 보존하고 공개 지표에 경고를 넣었으며 함수별 CPU 우승/순위 산출에는 사용하지 않는다. 타이머·프로파일 교정 원인은 아직 미검증이고, 별도 HTTP/전체 wall 측정과 구별한다. 현재 하드웨어 CIM 조회 거부도 우회하지 않았고 옛 snapshot을 이번 직접 검증으로 표시하지 않는다.

최종 회귀: Provider315/Core302/Web443 PASS(47파일), 라우팅·승인·벤치마크 관련42 PASS 및 이후 보고서 회귀10 PASS. 관련 suite는 겹치므로 합산하지 않는다. TypeScript/build PASS; jsdom canvas 미구현/JS bundle>500kB 경고는 유지한다. 첫 sandbox 두 실행의 임시 디렉터리 PermissionError 및 Web spawn EPERM은 기록하고, 승인된 로컬 테스트 실행 권한으로 재검증했으며 ACL/시스템 설정 변경은 하지 않았다. 현재 보고서 스키마1.2는 사적 원문 대신 typed SIM 실패와 NOT_RUN/예약/개별 trial alias만 노출한다.

### 다음 단계와 남은 인수

1. Nebius 현재 Token Factory 계정/프로젝트 잔액 적용 확인 후 미실행3개를 새 승인 범위에서 수행한다. 원402와 비용 예약을 삭제하거나 초기화하지 않는다.
2. 생성 ready 이후 목표 접근 가능성 검사를 어떤 generic 품질 단계에 포함할지 검토한다. 원 Luna5 실패를 기반으로, 실패 시 설명/목표 재선택·생성 수정까지 연결해야 하며 이번 사진 좌표나 특정 모델 답을 하드코딩하지 않는다.
3. 배치 모순·렌더 외관 수정의 정체와 부족한 물체/지지 관계를 독립 품질 데이터로 검증한다. 다른 사진·방, 텍스트만 입력, 독립 사람 평가와 실측은 이번 벤치마크 밖이다.
4. CPU 프로파일 타이머 일관성을 교정하고 재검증한다. 기존 wall 지표를 함수 CPU값으로 바꾸지 않는다.
5. 실제 로봇 LiDAR 좌표 정합·실물 자율 목표/Loop·배터리/토크 보호·패키지/전체 도메인·해커톤 요건은 이전 잔여로 유지한다. **이번 소규모 통합 PASS는 전체 실물 데모 완료가 아니다.**

아래 시간별 진행 기록은 당시 상태를 보존한 이력이다.

## 승인과 비교 조건

사용자가 14:20 KST부터 약 4시간의 실제 시험을 승인했다. 이번 신규 장부의 추정 사용량과 미정 결과 예약액 합계가 Nebius Token Factory USD5, OpenAI USD1을 넘지 않도록 한다. 기존 장부의 사용액·잔여는 합치거나 초기화하지 않는다. 18:20 KST 이후 새 시험을 시작하지 않는다. 원본 침실 사진과 같은 후보의 실제 Isaac 렌더를 기존 등록 공급자로 보내는 목적이며 로봇은 사용하지 않는다.

일반 채팅 App의 명시 생성 승인부터 관측, 구조, 물체 배치, 전체 host 기하, 현재 Isaac 렌더 critic, 필요시 실제 모델 수정과 재렌더, 동일 후보 저장, 실제 SIM 이동·도착·Stop, reload/reset 및 종료 후 재열기까지 검사한다. 새 실행마다 같은 사진·문구를 쓰고 관측 캐시를 공유하지 않는다. 모델 임의 코드를 실행하지 않는다.

모든 비교 조합: 역할별 출력 최대20,000토큰, 요청300초, 전체900초, 초기420/수정300/최종렌더180초, 최대수정3, 정체2, 실행별 최대24 HTTP. 출력 소진·결과 UNKNOWN은 즉시 중단한다. 정상 결과도 사진 실측 정확도를 뜻하지 않는다. 이 시험용 프로필은 사용자 전역 설정이나 제품 기본값을 변경하지 않는다. 실제 호출수가 가변인 것을 기록하고 요청수 상한을 성공률 분모로 쓰지 않는다.

우선 Flash 관측/critic + Lightning 설계/repair의 fresh 두 반복을 검증한다. 필요하면 이전 역할 비교 상위 Qwen 관측 및 GPT6 Luna 역할 대조를 같은 조건으로 추가한다. 추가 조합은 수행 전에 모델·계정 가용성·가격·계약을 검증한다. 조건이나 코드가 바뀌면 별도 cohort로 집계한다.

## 기록과 공개 범위

각 실행의 실패·성공 ID, 모델/단계/attempt, 원 dispatch·응답·usage·검사·checkpoint·plan/frame SHA, 실제 지연/프로파일 병목, 비용 추정, 자동수정수와 결과를 로컬에 보존한다. 공개용 지표는 표본수, 단계별 성공률, 전체 경로 성공률, p50/p95 시간, 비용, 실패 분류 및 버전 SHA를 제공하되 원본 사진·집 내부 배치/좌표·키·인증 헤더를 포함하지 않는다. 표본2회는 안정성 입증이 아니며 95% 신뢰구간도 표시한다. 자동수정 회복이 발생하지 않았으면 미검증으로 남긴다. commit/push는 하지 않는다.

## 현재 상태

15:04 KST 공급자 차단: Qwen/Lightning3는 initial/기하 수정/현재 렌더 critic까지 실제 진행했으나 후속 품질repair를 Nebius가 HTTP402로 거절했다. 원문은 `Payment Required: You have exhausted your budget. Please add funds to continue using the API.`다. 모델 품질실패나 이번 USD5 사용자 승인상한 도달로 오분류하지 않는다. 해당 공급자의 추가 paid 호출은 차단했다. USD150 계정크레딧/프로젝트한도/Token Factory 적용 여부는 직접확인하지 못했으며 충전·결제설정·다른키 자동전환은 하지 않았다.

해당402의usage없는USD.06771456도 원장부대로예약유지. 당시확정usage추정Nebius.16582065/OpenAI.0447344와예약Nebius.06771456/OpenAI.115를구분, 전체노출.23353521/.1597344. 결과불명0·pendinglock0이며 청구확인 아님. Nebius와섞인 미실행3조합반복은NOT_RUN으로남기고 OpenAI단독5회current코드표본까지검증한후무료감사/공개표/최종정리·예약PAUSED 계획. 로봇이나 잔액 충전이 없어서 오프라인 로그 분석까지 멈추는 방식은 아니다.

현재GPU/CPU/RAM의CIM읽기권한은거부되어우회하지않았다. 기존9월PC snapshot을이번직접하드웨어조회로표시하지않으며 timings는통제된부하벤치마크아닌실제동일host실행관측이다.

이전 v389 실제 생성은 host 벽면 배치 결함으로 실패했고 수정 후 저장 응답 재생만 통과했다. 그 실패는 이번 새 분모에 섞지 않으며 과거 기록을 유지한다. 이번 실제 결과는 `outputs/model-combination-benchmark-20261010/campaign.json` 및 각 실행의 `summary.json`에 누적한다. 전체 실물 데모는 계속 미검증이다.

14:42 KST 중간 결과: Luna/Luna fresh 1회와 Qwen/Lightning fresh 1회가 실제 외부 응답→현재 Isaac 렌더 재검사→저장→PhysX 도착(목표오차 각각0.039444/0.039455m)→채팅 Stop/정지 유지→reload/reset→소유 종료→backend 종료 후 저장 재열기까지 PASS. critic의 마지막 평가는 둘 다 `uncertain`이고, 저장 물체는10/17개다. **처리 경로 통과이지 사진 충실도나 실측 복원 성공이 아니다.** 자연 수정은 두 실행 모두0회라 실제 수정 회복 성공은 아직 입증되지 않았다.

Flash/Lightning fresh 두 실행은 실제7/8 HTTP·모두stop 응답을 받았지만 `PHOTO_LAYOUT_REGION_FULL` 이후 두 수정에서도 회복하지 못해 `REPAIR_STALLED` FAIL. 관측에서 생긴 복잡한 floor 배치와 설계 수정을 구분해 검사 중이다. 첫 실행은 이후 모델 허용목록 확장 전 코드 cohort이며 다른 버전과 통합 성공률로 합치지 않는다. Luna/Luna 최초 preflight의 USD 문자열 `1`/`1.00` 정규화 오류는 호출0·출력 폴더 생성 전 FAIL로 보존하고 모델 분모에서 제외했다. 신규 장부5/1 승인과 과거10회 장부를 합치지 않는다.

벤치마크 회귀4 PASS(비밀/좌표 비공개·역할/버전 분리·실패 분모·UNKNOWN 예약·5개 연속 동일실패 중단·p50/p95), 라우팅/승인 포함35 PASS, 설정Web14/type/build PASS. 중간 집계 시험 fixture의 `finish_reason` 누락 최초 ERROR는 보존하고 fixture 수정 후4/4 재검증했다. 이전 전체 Provider/Core/Web 결과와 관련부분 시험을 합산하지 않는다. 현재 Luna/Lightning 교차 시험 실행 중, 이후 Flash/Luna와 동일 조건의 fresh 반복을 계속한다.

## 시험 중 발견·수정한 스키마 연동 결함

14:53 KST: Luna/Lightning1 전체 PASS/수정0/critic uncertain. Flash/Luna1은 initial6 응답 후 첫 repair HTTP400 FAIL. 원 오류는 OpenAI strict Structured Outputs 스키마의 enum 총합 초과이며, 서버는1001에서 제한을 보고했다. 저장 wire를 직접 계수하면1303이다. 출력20k 소진이나 모델 추론능력 실패와 구분한다. [공식 enum 총합1000 및 $defs/$ref 지원](https://developers.openai.com/api/docs/guides/structured-outputs).

공통 OpenAI wire에서 동일 enum leaf를 `$defs/$ref`로 공유하고, 겹치지만 다른 ID 목록은 필요시 정확한 singleton의 anyOf로 공유했다. strict=true/값의 허용범위/부모·물체ID 제약/host 독립 전체검사를 완화하지 않았다. 원1303→916/펼친 모든 제약 동일·외부호출0. 고유값1000초과는 송신전 명확히 거절한다. WIRE_CONTRACT_REVISION1.1, 이후 fresh 결과는 새 코드 cohort로 분리한다. 서로 다른 방에 같은 사진의 답을 넣는 방식이 아니다.

HTTP400에는 usage가 없어 원 금융 장부의 USD.115 예약을 그대로 보유한다. 알려진 rejected 응답은 모델 성공으로 세지 않으며 결과불명 UNKNOWN과 분리해 raw/dispatch/status/SHA 대조 후 감사한다. 비용 집계는 usage 추정과 미청구 예약을 각각 표시하며 기존 raw·ledger는 수정하지 않았다. 당시 감사 도구가 received만 허용해 거절응답을 identity mismatch로 오분류했고, 이 제한도 보완했다. 새 호출 전 현재 노출액Nebius.06902610/OpenAI.1286492(usage .0136492 +예약 .115), 청구미검증.

Provider315 PASS(신규enum 회귀5), 라우팅/승인/벤치마크38 PASS(중복). overlapping enum 회귀의 최초 JSON표기 동등성 기대 FAIL은 수학적으로 동등한 anyOf를 펼쳐 비교하도록 시험을 교정한 후 전체315 재검증했다. 이후 Flash/Luna2부터 같은20k/300/900/24HTTP 정책으로 새5조합×2반복을 검사한다. 아직 자동수정 회복 성공이나 변경후전체PASS를 주장하지 않는다.

14:58 KST: 변경후 Flash/Luna2 actual11HTTP/repair3(기하2+사진·렌더품질1)/actual렌더2→전체PASS·20물체 저장·도착오차.039723m·85.422초 active/148.094초 전체. 처음 기하patch는 일부 개선 뒤 실패, 다음patch는 기하passed·관측품질failed, 마지막품질patch 후 새렌더uncertain/정확한최종후보저장→SIM/Stop/reopen을 확인했다. **저장 응답 재생/주입오류가 아닌 fresh 실제 자동수정 회복**이다. 중간 후보의 aggregate validation이 pending인 기록도 phase별 geometry/quality verdict와 함께 원본으로 보존하며 이를 최종후보PASS로 덮어쓰지 않는다.

변경후 Qwen/Lightning2는17물체 구성·기하통과 뒤 `PHOTO_OBSERVED_REGION_CONTRADICTION`을 두patch에서도 해소하지 못해 `REPAIR_STALLED` FAIL. 이전버전1PASS와통합해 현재100%로표시하지않는다. Luna/Lightning2는5HTTP/수정0/criticuncertain 전체PASS. 모델마다 관측물체수 차이가 크므로 물체수를 인식정답률로 부르지 않는다. 짧은 준비SIM 경로(통과예0.4m) 도착과 이어진목표의Stop를 확인한 것이며 방전체 임의목표 최적경로·실물완주 인수가 아니다. 새cohort 반복을 계속한다.

공개용 산출물은 `scripts/export_combination_benchmark.py`로 `docs/benchmarks/model-combinations-20261010.md`/JSON을 재생성한다. 원본사진/집좌표/raw/키/원문 없이 역할·cohort·실패/단계/시간/사용액/미청구예약만 export하며 실행6회귀 PASS(신규공개Markdown 비밀차단 포함). 영문본은 GitHub 준비용이고 이번에 commit/push하지 않는다.
