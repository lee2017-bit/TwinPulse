# 제품 사진 geometry gate 실제 재평가 — 2026-10-07 / v327

## v327 — 추가50 승인·실제 수정루프 및 App/Isaac 인수

사용자 “그래 추가 50회를 승인할게”에 따라 같은 ledger에 `approved-additional50-v327` 승인 이력을 추가했다. 원래69요청·실패·unknown 예약/가격/기존USD1은 보존, 누적119 한도다. 실제28회를 사용해 **97/119·남은22·pending0**이다. 신규 추정USD.02027148/누적 추정·예약USD.13446040이며 공급자 청구는 확인하지 않았다. 이 상한을 소진하려는 반복은 하지 않았다. 로봇/SSH/serial/센서/모터/배포/설치/commit/push/새agent0; owned App/Isaac child만 정상 종료했다. 실물 guard와dirty/원본은 보존했다.

### 실제 결과 — 서로 다른 표본을 합치지 않음

| 실행 | 신규 HTTP | 사진 전체 fresh | cached 관측·새 planner | 의미 |
|---|---:|---|---|---|
| r4 | 4 | 0/1 | 해당 없음 | no-thinking 밀집 배치FAIL; 별도통제repairPASS는 자연성공 아님 |
| r5 | 4 | 실행 안 함 | 2/2·각repair1 | 기본thinking 비교, 원본 actual 관측2종 재사용 |
| r6 | 3 | 0/1 | 실행 안 함 | fresh 관측→length8000→repair1 packingFAIL,73.687s |
| r7 | 5 | 1/1·repair1 | 1/1·repair1 | literal label 제약후 no-thinking,4×5m 추정/42.063s |
| App/Isaac live | 3 | 1/1·repair1 | 없음 | 새 actual 응답→기존 실제 제품/Isaac 전체 SIM 연결 |
| r8/r9/r10 | 9 | 3/3·각repair1 | 없음 | 독립 코호트,26.563/25.203/21.969s·4×5/4.5×3.8/4×5m 추정 |

최종 **같은 literal-label/compact/no-thinking 정책의 fresh 전체5건은 첫시도0/5, 수정1회 후5/5**다. 24 inventory 항목, 검토4위치·catalogue 파생3지지 조건만 통과했다. r7cached1건/r5cached2건/통제수정/과거다른정책FAIL은 해당5건 분모에 넣지 않는다. 마지막3건은 사전 계획된 독립 fresh observer→planner 소규모 코호트이며 건당cap3/sharedrepair1/90s/8000·transport/unknown에서중단 조건을 지켰다. 일반 사진의 안정 성공률이나 실제 방 치수 정확도를 확정하는 표본은 아니다. 지원면은 모델이 직접 실측 좌표를 고친 결과가 아니라 compiler가 추정 catalogue geometry에서 파생했다.

원본 근거: `artifacts/agent-reliability-20261007/photo-geometry-live-r4`–`r10`의 result/raw/개별 savedplan/`post-run-analysis.json`; 실제 제품은 `photo-geometry-chat-isaac-r1/result.json`과`post-run-analysis.json`이다. 평가마다 지난 요청·원본 hashes·그 당시 source 불변을 검사했다. r4/r5/r6 source는 이후 의도적으로 개선했으므로 과거 감사의 “source unchanged”를 현재 source와 같다는 뜻으로 읽지 않는다. r7–r10 모델정책/제품 source는 고정한 상태로 평가했다. 모든 원래 raw/실패는 덮어쓰지 않았다.

### 실제 수정과 예방

- REGION_FULL에 처음 실패한 항목뿐 아니라 전체 미배치ID/footprint·각 구역 항목 수·이미 배치된 synthetic proxy 기준 alternative slot을 함께 보낸다. 전역 불가능성 증명/실측 free space/로봇 안전경로가 아니다. same sharedrepair1에서 모델이 배치를 다시 결정하며 좌표를 자동으로 덮어쓰거나 객체를 삭제하지 않는다.
- packing 실패 뒤 width/length 확장은 거절한다. 기존 좌표프레임/크기quality guard도 유지했다. observer ID 공유를 위치 공유로 해석하지 말라는 입력을 명시했다.
- r6는 기존 reviewed label의 “left floor bags/left-edge boxes”도 right로 배치했다. 새 사진정보나 좌표를 만들어 추가하지 않고 **이미 명시된 literal left/right**를 strict slot enum/입력 choices와local compiler에 같은 조건으로 반영했다. 무관한 inventory/관측 alias를 정규화하지 않는다. 기존 독립4위치/3지지quality gate와v1/v2 plan·저장hash는 그대로다.
- App은 ledger의옛60 cap을고정하여 새 승인119를거절할수있었다. host-only로 기존 승인chain·각추가cap≤50·old/new 연결·같은USD1·각prefix SHA·pending/foreignlock를 검증해 같은ledger를 열고, 소유 backend 한 실행은최대5 HTTP만 사용한다. browser/model이한도를주거나 새campaign/reset/refund를 만들지 않는다. schema/request/누락된 가격/unknown 회계는기존fail-closed다.
- template off는exact Nano Site2.2 명시host 실험으로만 App에연결했다. default는false/기본thinking이며 compact도false다. 실제공급자 내부reasoning 원인은 확정하지 않는다. 현재실험에서12planner 응답이완전JSON이고 각연산이약4–5초라는사실만 관측했다.

### 실제 제품·원본 재검사

`photo-geometry-chat-isaac-r1`은 fixture/replay가 아니라 새Gemma1+Nano2의 실제3HTTP다. Q1선택전 generation/Build/Run 없음→사진24항목siteartifact 저장→동일plan/input으로 실제현재Isaac3D99frame→명시Run/PhysX 목표도착오차 **0.0395716426m**→reload시같은plan·24항목/재실행없음→새채팅goal/접은화면chatStop/pose정지→reset시visual만복원→owned종료후ProjectStore2.0 재열기/같은hash까지PASS다. 실제 source11/추가product source·builtweb hashes·raw3 SHA/바이트수/usage·동일ledger attempted IDs·savedplan/quality/렌더·도착/정리 감사도PASS다. 기존물리권한복원·자동Run·실물명령은없다.

![실제 새LLM→현재Isaac 생성 화면](../../artifacts/agent-reliability-20261007/photo-geometry-chat-isaac-r1/generated-ready.png)

위 화면은 **추정 proxy scene**이며 사진처럼 재질·형상·문힌지/침구·의복 attachment가 재구성된 결과가 아니다. 현재runtime 연결PASS와완전사진복원을혼동하지 않는다.

회귀: 최종provider103/관련integration92/추가집중17 PASS(중복포함). 정합·정지·실물mission 정책/200ms·250ms·50ms·.03/.20/45s/v1-v2 저장·hash는변경하지 않았다. 준비중 provider 음성fixture를 전체schema 위치까지 compiler 조기차단하는로컬실패는 literal label만local 검증/독립 quality 유지로 수정했다. 새 양성fixture는literal 방향을명시하고 실제과거raw는손대지않았다. r7첫preflight는과거통제음성후보의새label 불일치로HTTP0에서차단; natural-only를무관한후보검사와분리/회귀후실행했다. 제품감사도SiteDraftRecord에없는 provenance접근과chat/provider서로다른request ID를동일시하는local오류를수정하고, 실제draft providerID+canonicalplan/constraints+HTTPattempt IDs로결속했다. 감사원본오류/수정은이기록에보존하며제품모델실패로세지않는다.

### 정확한 잔여

1. **완전사진 geometry/attachment:** 현재7관계와literal2좌우만검사했다. wardrobe좌우·가구간상대거리/bed깊이·실측치수·hidden면·문힌지·의복/침구부착·일반사진은미검증이다. compiler는일부벽/천장/의복proxy도2D공간을예약하므로바닥장애물/지지/부착의의미를분리해야한다. collision/keepout/원본을없애거나방을확대하는식으로숨기지않는다.
2. **수정효율·반복안정성:**5건모두첫배치실패/repair1에의존한다. 작은P01 host-assisted 표본의5/5를일반성공보장으로표시하지않는다. 다음은semantic packing/관계검사의개선과독립평가, 같은조건추가22회소진이아니다.
3. **정책채택/일반화:** compact/no-thinking은아직host-only실험이며기본경로에조용히적용하지않았다. defaultSite2.2/no-review/generalphoto 품질·다른장면/실패 matrix를근거로채택판단해야한다.
4. **실물/전체데모:** 이번새로봇근거0. corrected driver와현재boot정지/scan/odom/TF·실측frame/timing/자율임무정합·현장인수는별도다. H5/H6·C3–C6 PARTIAL/whole_demo_ready=false·예약PAUSED 유지. 로봇전원만켜면전체완료라고보장하지않는다.

## 아래 v326 이력

## v326 — HTTP 옵션 수정·제약 생성·승인 묶음 종료

사용자 “그래 계속해보자”에 따라 같은 승인 묶음의 **남은5회만 사용**했다. 새 캠페인/한도연장/추가 repair/토큰·90초 확대는 하지 않았다. 기본 compact/no-thinking은 OFF, whole=false/H5-H6/C3–C6 PARTIAL 유지다.

### 확인한 구현 오류와 수정

- [공식 NVIDIA Nano 모델 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)의 raw curl JSON은 최상위 `chat_template_kwargs.enable_thinking=false`, SDK 호출은 `extra_body={...}`다. 기존 raw urllib 경로는 SDK 인수를 HTTP에 중첩하여 보내고 있었다. **기존 nested 실험의 빠른 응답은 옵션 적용 증거가 아니다.** 실제 urllib 직렬화 회귀를 추가하고 exact Nano/Site2.2의 명시 host opt-in만 최상위 정책을 보낸다. compact 생성/같은 repair와 기존 App provider composition까지 연결했다. observer/default/다른 모델에 묵시 적용하거나 reasoning-only 본문을 scene으로 승격하지 않는다.
- CLI Tavily가 없고 skill의 설치 참조 문서도 없어서 새 설치 없이 기본 웹 검색으로 공식 문서를 확인했다. NVIDIA의 공식 wire 방식과 Nebius가 정확히 내부 thinking을 끄는지는 구분한다. 이번 Nebius 실제 HTTP가 옵션을 받아 완전 JSON을 반환한 사실은 확인했지만, 반환되지 않는 내부 추론량은 증명하지 않는다.
- r2에서는 정책만 바꾸고 schema/prompt/8000/shared1/geometry gate는 유지하여 원인을 분리했다. 자연 최초+repair 모두 **24개 중14개를 front_right에 몰아** 4×5m `PHOTO_LAYOUT_REGION_FULL: clothing_pile`이 재현됐다. 수정 전후 region 분포가 같아 형식문제가 아닌 모델의 packing 피드백 반영 실패다. 객체 누락/방 확대/자동 재배치를 해서 PASS로 바꾸지 않았다.
- r2 통제 위치 repair는 침대 좌측·책상 앞쪽을 남겼다. 후속 r3에서 기존 **SHA-bound host-reviewed 위치조건**을 per-ID schema region enum으로 컴파일했다: 침대 right, 책상 rear_left, 옷장 rear. 동일 초기/repair schema이며 unknown 사진에는 P01 조건을 빌려주지 않는다. reference SHA/항목·종류·모순조건을 거절하고 다른 항목의 enum/치수/wire1.1은 보존한다. 검토 목록이 있으면 무관련 전체 kind 목록만 생략한다. 이는 **human-assisted 제약 생성이지 일반 사진의 자동 이해/실측 정확성 증거가 아니다**. 실제 compiler/executor/geometry gate는 그대로 검증한다.

### 실제 결과 (자연·통제 분리)

| 현재 증분 | 새 요청 | 결과 |
|---|---:|---|
| r2 새 observer→Nano→repair1 | 3 | FAIL/28.000s. 관측 성공, 두 Nano 모두 stop/완전JSON·약4.3초/1011·1007tokens. 동일 front_right packing 오류로 두 번 거절 |
| r2 통제 위치오류→정책만 수정한 actual repair | 1 | FAIL/4.000s. stop/717tokens, 침대 좌측·책상 앞쪽2오류 잔류. no-thinking만으로 품질 해결 아님 |
| r3 검토 region schema→통제 actual repair | 1 | **위치4·지지3조건 PASS, 전체PARTIAL/4.500s**. stop/722tokens/4.234s. 첫 후보는 과거 actual 잘못된 위치의 주입 데이터이며 새 자연 생성 성공으로 집계하지 않음 |

이번 Nano4응답은 모두 완전JSON/stop이며 length0이나 작은 표본이다. r2 자연0/1, r3 자연 trial0·통제수정1PASS. **최종 strict-schema의 새 전체 observer→planner 자연 성공은 미검증**이다. r3도10×12m/120㎡ 추정이므로 실제 작은 침실 복원으로 표시하지 않는다. 부모 위 세 객체의 높이/XY는 기존 compiler가 파생한다. 실측·가림·부착·일반사진 fidelity는 미완료이며 실제 새 Isaac/Browser/로봇은 NOT_RUN다.

### 근거·예산·회귀

- r2: `artifacts/agent-reliability-20261007/photo-geometry-live-r2/result.json`, `post-run-analysis.json`, raw4. 신규USD.00166908/68 of69. 옵션 분리 시험 중 source/원본·지난64requests 보존 감사PASS; 그 뒤 r3용 소스 변경은 별도 증분이며 r2 source가 현재도 동일하다고 주장하지 않는다.
- r3: `artifacts/agent-reliability-20261007/photo-geometry-live-r3/result.json`, `post-run-analysis.json`, `controlled_reviewed_schema_actual_quality_repair-plan.json`, 실제ID `e710450710ab4af1a97fbd15c9956cf2`. 동일 saved plan geometry 재검사·raw UTF8 SHA/byte/model/usage·원본29(기존 FAIL/성공/raw 포함)/source10/지난68requests 불변 감사PASS. planSHA `b93a1fe911e48e0ff4ad2b8d7f92ad0468c68af3ba3c437fd278a80b3c2288bb`.
- 현재 증분5/승인 묶음 총10 사용. **69/69·pending0·기존USD1 유지·추정+unknown 예약USD.11418892·청구 미검증**. 이번5 추정USD.00213342, 승인10 전체USD.00950556. 지난 unknown/rates/approval history 보존. 추가 외부 호출은 새 승인 전 실행하지 않는다.
- 최종 Provider **98 PASS/2.568s**, 예산·기존repair·채팅 text/photo·exact observer 통합 **80 PASS/25.697s**(중복 있음). urllib fake-wire/기본값/다른모델 거절/shared1/schema 불변/constraint SHA·충돌·슬롯 독립성과 read-only 잔여 allowance를 포함한다. 신규 테스트 최초 `bag`은 kind를 ID로 잘못 사용해1ERROR였고 실제 ID `floor_bags`로 테스트만 고친 뒤 전체 재실행PASS; 제품 오류나 actual FAIL을 숨기지 않았다.
- prepare-only 두 번은 credential/HTTP0. Live 상태표시는 RUNNING으로 고쳤고 exact 관측 재현은 원래 요청 SHA 일치 때만 허용한다. 신규 설치/SSH/serial/센서/모터/배포/commit/push/새 agent0. 기존 dirty/실물 guard/v1-v2/hash/원본·과거 실패는 보존했다.

정확한 잔여: **작은 방에서24항목을 밀집 배치하는 compiler/관계 표현과 실패 피드백 반영 개선 → 최종 정책의 새 자연생성 재평가(추가 API 승인 필요) → 동일 통과후보 실제 chat/저장/Isaac 인수 → 일반사진·부착/실측 및 별도 실물 정합 인수**. 현재 병목은 로봇 부재가 아니라 사진 생성/배치 경로다. 기본 정책 채택과 전체 Full Process 완료는 주장하지 않는다.

아래 v325는 이전 실제 시험 이력이다.

## v325 실제 결과 — 전체 생성 FAIL, 통제 위치 수정 PASS

추가10/누적69·기존USD1 유지 질문에 사용자가 “그래 해봐”라고 승인한 후, 허용된 네트워크/파일 권한과 실제 실행 심사를 거쳐 기존 Nebius Gemma/Nemotron으로 **5회만 실행**했다. 자연 실패를 같은 조건으로 반복해 잔여5회를 소비하지 않았다. 평가 완료는 제품 전체 성공이 아니다.

| 시험 | 새 실제 요청 | 결과 | 정확한 의미 |
|---|---:|---|---|
| 새 사진 전체 observer→planner→repair1 | 3 | FAIL / 82.437s | Gemma 관측 성공. 첫 Nano는8000 tokens/length·content0. shared1을 사용한 두 번째 Nano는 완전JSON이나 침대 우측·책상 좌측/후방3조건 위반, gate가 거절. 지지3조건은 PASS |
| 통제 compact 위치 오류→실제 Nano repair | 1 | 조건PASS·전체PARTIAL / 13.422s | 저장 actual intent의 잘못된 위치3개를 현재 제품 gate가 진단하고, 실제 Nano가1회 수정. 침대x3.3/책상x-3.3,y4/옷장y2.6. 위치4·지지3 조건 재검사 PASS |
| 통제 기본 Site2.2 지지 오류→실제 Nano repair | 1 | FAIL / 28.984s | 3지지/위치 오류 전체 feedback 전달 후 실제 모델 응답8000 tokens/length·content0. 불완전 응답을 성공으로 만들지 않음 |

**자연 전체 성공0/1과 통제 수정 성공1건은 분리**한다. 이를 합산 성공률이나 신뢰성 입증으로 표시하지 않는다. 성공한 compact 결과의 지지 높이·XY는 현재 결정적 compiler가 파생한 것이며 모델이 직접 지원/높이 좌표를 고친 성과로 주장하지 않는다. 모델은 region 위치를 수정했고 실제 geometry로 검사했다.

성공 후보도10×12m/120㎡ 추정·경고/실측 없음이다. `checked_relation_status=PASS`, `status=PARTIAL`, `full_photo_reconstruction=UNVERIFIED`, `metric_scale_validation=UNVERIFIED_NO_MEASUREMENTS`. 숨은 물체·부착·hinge·침구·일반사진 및 metric 정확도는 미완료. 현재 기본compactOFF/wholefalse/H5-H6/C3–C6 PARTIAL 유지.

## actual 원본·진단·비용

- 실제 결과: `artifacts/agent-reliability-20261007/photo-geometry-live-r1/result.json`.
- 실제 수정된 plan: 같은 폴더의 `controlled_compact_actual_quality_repair-plan.json`.
- 원본을 바꾸지 않는 독립 감사: `post-run-analysis.json`, 실행기 `scripts/summarize_photo_geometry_live.py`. 저장 plan을 같은quality 검사로 재확인했고 모델 raw5의 UTF8 SHA/byte/model/usage/finish·ledger finished·원본/소스 해시를 대조했다.
- 새 actual IDs: Gemma `229287811a9c4b078755ce2998c2d3d2`; Nano length `85b7db6f15524fc9b90a217eb238558b`; 자연 repair `00e95cc679ce4a74af6831c2cf416d73`; 통제 compact repair `cce9b3dbdd2142b9b020fcb83235893a`; 기본 repair length `1ea17c4b8ee34ab196c7aaf4a668af1b`.
- completion8000/length/HTTP200/content0은 확정했다. API reasoning 세부 usage는null이며, 반환되지 않은 출력이 왜 한도를 소진했는지 **추론/네트워크 원인으로 확정하지 않는다**. 단순 요청 실패/PC 팝업 문제로도 바꾸지 않는다.
- 자연 작업은 최초 형식 잘림에 shared repair1을 써서 최종 위치 오류를 한 번 더 수정할 여유가 없었다. product budget을 임의로 늘리거나 새로운 job으로 은밀히 반복하지 않았다.
- 원래 campaign에 명시 추가승인1건·old60/new69/start59·prior requests SHA를 기록했다. 지난59개 요청 전체 불변/기존USD1·rates·unknown 예약 그대로, pending0. **현재64/69·신규 추정USD.00737214·전체 추정+예약USD.11205550**, 청구서 미검증. 새10 중5남음; 원격 불명 신규0.
- raw5 SHA/byte 모두일치·저장 성공후보 재검사PASS·이전16원본/제품 및 실행8source 검사중·사후불변. 실제 credential은 기존Windows 저장소에서 인증에만 사용; 사진/base64/key/header 로그 없음.

## 회귀·중간 오류·잔여

- 현재 provider 전체 **94 PASS / 2.701s**. 앞서 신규 예산4+geometry29=33 PASS는 준비단계 근거이며 중복합산하지 않는다.
- 실제 평가 종료 후 예산guard/기존repair/채팅 사진·텍스트 생성 통합 **63 PASS / 24.318s**. 겹치는 provider 검사를 합산하지 않는다.
- 사후 감사 첫 명령은 rawusage의 optional null 필드를 제품의 numeric-only usage와 전체dict 비교해 `INFERENCE_MODEL_USAGE_MISMATCH`로 거절했다. 실제 기록을 고치지 않고 필드별 동등검사로 바로잡아 최종감사PASS. 모델/제품usage 오류가 아니며 첫 감사 실패도 보고한다.
- 제품·UI·default policy 변경0. 실제 새Browser/Isaac/robot/SSH/배포/설치/commit/push/agent0. 이번 실행기 최초 결과상태는 진행 중에도 `PREPARED_NOT_RUN`으로 남았지만 완료기록은 별도 확정상태/시도별결과를 보존한다. live 실행 중 원본source를 고치지 않았다.

다음은 **첫 생성의8000-token 잘림/형식수정이shared1을 먼저 소모하는 병목**을 개선하고, 같은budget 안의 새 자연생성 성공→동일후보 actual제품/Isaac 인수다. 현재 검사기가 오류를 놓치지 않고 실제 한 번의 위치수정에 성공한 것은 확인했지만, 처음 사진을 넣어 안정적으로 완성되는 상태는 아니다. 로봇이 이번 실패의 병목은 아니다. 실측/현장 정합 인수는 별도다.

아래 v324는 준비 당시 상태/원래 승인 대기 이력이며 현재 결과로 대체하지 않는다.

## 현재 결과

사용자가 새 테스트 최대10회를 요청했다. 실제 실행 전 새 [검사계획](../planning/TWINPULSE_PHOTO_GEOMETRY_LIVE_TEST_PLAN_2026-10-07.md)과 `scripts/verify_photo_geometry_live.py`를 준비했다. **현재는 실행 전 준비·로컬33 PASS이며 신규 실제 모델 성공 검증이 아니다.**

기존 campaign은 **59/60·USD1·추정/예약USD.10468336/pending0**이다. 이번 새10회 요청과 기존 누적60 한도가 충돌하므로, **추가10·누적69·USD1 유지**의 사용자 확인을 질문했다. 답변 전 추가 승인 이력을 적용하거나 외부 요청을 보내지 않았다. 새 캠페인/횟수 초기화/unknown 예약 환불 없이 원래 기록을 유지한다.

## 준비된 시험

- 기존 실제 source/settings/P01 SHA를 읽고 credential 접근 없이 preflight한다. 원래 실제 observer의 response SHA·byte/model/finish 및 현재 observer 요청의 exact hash 일치를 검사했다.
- 과거 실제 Nano intent를 현 compiler/gate에 적용해 실제 위치 오류 FAIL·repairable을 재현했다. 이 결과를 신선한 모델 실패로 표시하지 않는다.
- 실제 전체 observer→planner→shared repair1 자연 시험, 성공시 독립1회 재현, 통제 compact 위치 오류→실제 수정, 통제 기본 Site2.2 지지 오류→실제 수정 순서. 예정 최대8/절대10 요청; 실패/잘림도 각각 센다.
- actual model의 self-accept는 통과 기준이 아니다. 동일 floor size/centre와 P01 위치·3지지의 XY/Z·coverage/실제 executor를 통과해야 한다. 알려진 관계PASS도 전체PARTIAL/metricUNVERIFIED이며 기본compactOFF를 유지한다.
- transport timeout/auth/rate/unknown이면 후속 유료 요청을 중단하고 bounded late evidence만 기다린다. 원본/소스 SHA와 raw·usage·정확한 오류/시도별 quality를 분리 저장한다.
- 명시 추가 승인 확정 후에만 같은 campaign에 승인 이력·old/new cap·기존 requests SHA를 기록하는 평가 전용 기능을 준비했다. 중복 실행은 같은 승인을 재연장하지 않는다. USD/가격/지난unknown 비용은 바꾸지 않는다. **실제 원래 ledger에 적용하지 않았다.**

## 검증

- `--prepare-only`: **PASS**, credential/HTTP 접근0. 결과 `artifacts/agent-reliability-20261007/photo-geometry-live-preflight-r1/result.json`.
- 신규 예산 보호4 + 기존 제품 geometry29 = **33 PASS / 1.786s**. 최대10 actual dispatch·rejected 포함, 기존59요청/unknown비용 보존,69cap/동일USD1, 중복 승인·pending·다른 소유lock·approval 부재 거절을 로컬 temporary ledger로 검사했다. 정상 사용자 로컬 테스트 권한 심사를 거쳐 실행했고 시스템 ACL/설정은 변경하지 않았다.
- Python 실행기 compile PASS. 잘못 지정한 provider filename/Windows rg wildcard 탐색 오류는 존재하는 `settings.py`/`credentials.py` 경로로 바로잡았다. 모델/제품 실패로 분류하지 않는다.

신규 외부0/추가비용0/실제 campaign 변경0. 새 actual model/Browser/Isaac/robot/배포/설치/commit/push/agent 모두 NOT_RUN/0. 기존v323 검사·원본·과거FAIL·dirty·v1/v2/hash·실물잠금 보존. H5/H6/C3–C6 PARTIAL/whole=false.

## 다음

추가10/총USD1 확인→권한 검토→동일 현재 source 실제 모델 평가→통과한 같은 결과의 제품/actual Isaac 연결 인수. 현재 전원만 켜면 전체 데모 완료라는 의미가 아니다.
