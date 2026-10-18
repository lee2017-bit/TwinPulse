# TwinPulse 자동 정합·Twin 보정·목표 주행 — 6.1 Sol 구현 상세계획

- 2026-10-05 사용자 흐름 변경: 다음 제품 구현 순서는 [12단계 채팅 중심 데모 계획](TWINPULSE_CHAT_DRIVEN_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-05.md)의 C1–C6을 따른다. 이 문서의 AD1–AD5 센서·좌표·정합·제어 계약과 미완료 판정은 기술 기준으로 유지한다. 새 계획은 PLAN_ONLY이며 새 viewer/SIM/실물/loop 인수가 아니다.

- 10/05 최신 checkpoint: **Baseline v1.0.279**. 사용자 요청4번의 지정427파일 checkout 밖 App/core70과 actual Web/API/Isaac 정상·저장 실패·USD 기하 오류·엔진 실패/명시 새 세션 복구4흐름 PASS. 한 Start→조사/벽 보정→도착→저장3D, accepted UI 상태 수정·Web255/build/Python16, Burger/명목 자료·LICENSE 포함·private raw 제외, 원본6/manifest/driver 불변·92runtime artifact·소유 정리 확인. **지정 패키지 연결 인수만 완료**: 전체 O1–O6/AD5·clean install·실 ROS/target·실측 profile/실사진·현장 인수는 미완료, 기존 guard/실물잠금 유지·로봇0. 아래 checkpoint는 이력이다. [최종 증거](../verification/ad4-review-fixes-20261005.md#packaged-web-api-and-isaac-acceptance).

- 작성일: 2026-10-04 KST
- 10/05 최신 checkpoint: **Baseline v1.0.278**. 사용자 선택3·4의 동일조건 공유 자동임무 baseline/corrected를 실제 API/영문 UI/보고서·점수·명령/관측에 연결하고 SAVING 경쟁을 수정했다. actual Chrome03/110·19hash/core293/Web253/build/408파일 격리67 및 actual Isaac 활성17frame·종료/rollback·저장 오류·엔진 실패→새 소유 Isaac session 복구 PASS. 합성 고정 비교 개선차이0/구조벽만/실물0. **지정 합성 비교와 검사 확대는 검증됐지만 전체 O1–O6·AD5는 미인수**: 동일 패키지 Browser/Isaac/실 ROS 전체 실패 인수·clean install, target/실측/profile와 실제 사진 불일치가 남는다. 기존 한 명령 OFF runner에도 비교6·패키지 계약5를 연결했으며 새 전체 raw3 실행으로 주장하지 않는다. 아래 checkpoint는 이력이다. [근거와 다음 경계](../verification/ad4-review-fixes-20261005.md#automatic-mission-comparison-and-expanded-package-checks).
- 10/05 최신 checkpoint: **Baseline v1.0.277**. 사용자 선택 잔여1·2의 구조별 실제 정합 실패 진단과 기존 한 명령 OFF 검사/최종 보고서 경로를 연결했다. 실제 raw3 원본 불변·처리/저장/재열기, 독립 계약79/core293/관련39/Web250/build PASS, 최종433파일 해시 일치. 실제정합2불일치/1근거부족·보정0/전체NEEDS_ATTENTION/AD4 PARTIAL을 유지한다. 새 전체 runtime·동일조건 자동임무 비교·패키지 runtime·실물은 미인수다. 다음 비교→전체 패키지 실패 인수→target/실측/profile 순서이며 기본 직렬화/guard를 완화하지 않는다. 아래 checkpoint는 이력이다. [근거](../verification/ad4-review-fixes-20261005.md#structural-residual-diagnosis-and-one-command-offline-checks).
- 10/05 현재 checkpoint: **Baseline v1.0.276**. 원래 수신 시각1배속을 기존 Web/API worker에 연결했다. 계산 예산/live guard/임무45s 보존, 계약/API/사진/패키지16·Web250/build·짧은 실제raw Web/API PASS. 실제raw3 전체 최종 hash-bound 1배속·최신 Web/API/Isaac55/18frame·저장 실패 UI·400파일 격리 App/core26 PASS. **AD4 PARTIAL/AD5 전체 미인수/offline-ready=false/실제사진정합false/실물0**. 이후 자동 비교·전체 실패/패키지 인수와 target/실측/profile/현장 잔여를 분리한다. [근거·잔여](../verification/ad4-review-fixes-20261005.md#original-receipt-time-replay-and-final-handoff). 아래는 이력이다. 최종 r7 패키지·재빌드 runtime에서도 PC wall-time 표시와 임무 예산을 구별했으며 guard는 불변이다.
- 10/05 현재 checkpoint: **Baseline v1.0.275**. cold 원본점 tracking/PCA basis/새survey-only causal innovation을 연결했고 core288·changing7/goal6/degraded4/10시작407추적/symmetry2/revisit4 PASS. 격리398파일/App-core21·source archive76/import2는 선행검사만이다. 당시 최종 source actual Web/API/Isaac56/18frame PASS는 이력이며 위 v276 runtime과 구분한다. **AD4 PARTIAL/AD5 전체 미인수/offline-ready=false/실제사진정합false/실물0**. 다음 전체 O1–O6/1배속 부하·제품 자동 비교와 target/실측/profile/현장 잔여를 분리한다. [근거·실패·잔여](../verification/ad4-review-fixes-20261005.md#survey-reference-precision-degraded-scans-and-packaged-execution). 아래는 이력이다. 최종 r7 패키지·재빌드 runtime에서도 PC wall-time 표시와 임무 예산을 구별했으며 guard는 불변이다.
- 10/05 현재 checkpoint: **Baseline v1.0.274**. report 저장 ENOSPC/권한실패의 이전arrival pose/scan 잔류 수정·최초원인/stage/type/errno 분리. Python12/Web249/build·actual diskfullWeb/API/popup·reload재주행0 및 새빌드 dense/remoteIsaac70/21frame·39/34hash PASS. exact모델2 edit0/error모델2 분리holdout 개선/4case6source20artifact PASS. robotarchive·기존기준/실물잠금 보존·AD4 PARTIAL/정식AD5 미시작. 다음 넓은 degraded/heldout거절→전체O1–O6/패키지. [근거](../verification/ad4-review-fixes-20261005.md#report-storage-failure-and-accurate-model-product-boundaries). 아래는 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.273**. saved-map 재열기 drift/객체변경4case·940관측, 기록79.6초×2/1399 current TRACKING의99.713%/100% 고정95% 기준 및 identical reopen PASS. outlier2·검증기 초기FAIL 보존, frontend revisit≠자율loop/posegraph, source/artifact11/18·10/14hash 일치. production/guard/45s/runtime/archive 불변·AD4 PARTIAL/실물0; 다음 degraded/heldout·전체O1–O6/패키지. [근거](../verification/ad4-review-fixes-20261005.md#reopened-map-drift-changed-objects-and-causal-loop-bounds). 아래는 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.272**. 실제 cold App2형상×5시작1052 current TRACKING 관측 전부 기존10cm·5도 기준 만족/14source·40artifact hash 일치, square2시작 실제 AMBIGUOUS 거절/17view·navigation/append0/최종zero·10/6hash. 합성 짧은 경로이며 production/legacy/guard/45s/source archive와 v271 runtime 불변. 다음 saved-map 재배치·drift/revisit·loop→전체 O1–O6/AD5; AD4 PARTIAL/실물0. [근거](../verification/ad4-review-fixes-20261005.md#per-frame-cold-tracking-accuracy-and-symmetric-room-rejection). 아래는 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.271**. current field bilinear/subcell 정밀화로120/720 근접목표 교대회전을 수정했다. 기준·legacy 불변/core278·독립7case·6cold goal·재열기4 PASS; actual dense Web/Isaac70frame·39hash 및 분리 PC pipe/Isaac23frame·34hash PASS. 31묶음 실패·새 deadline fixture 오류/원본 보존, 76member archive/격리import는 소스 선행검사만이다. 다음 per-frame 추적 정확도→대칭/재배치·sparse/revisit/drift/loop→AD5; AD4 PARTIAL/실물0. [근거와 남은 검사](../verification/ad4-review-fixes-20261005.md#continuous-current-matching-and-subcell-control-regression). 아래는 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.270**. dense 표시/사진fit producer를160점 계약으로 연결하되 raw/grid는 전부 보존했다. App 재열기4사례/8source·24artifact/core274/cold15·source archive76member PASS; built Web/API dense 저장지도2시작/34source-build·2complete raw hash PASS. **dense cold Web/Isaac 전체주행은 목표근처 교대회전 후45s 만료로 FAIL**. 먼저 원본 기준 그대로 재현·수정하고 이후 대칭·가구재배치/sparse/revisit·drift·loop→AD5를 진행한다. AD4 PARTIAL/정식AD5 미시작/실물0, [원인·실패·근거](../verification/ad4-review-fixes-20261005.md#dense-scan-transport-and-saved-map-reuse). 아래 checkpoint는 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.269**. changing-environment6사례의 우회·정합상실 회복2도착과 시간초과·가림/차단·위치점프4정지를 실제 App/shared loop에서 검증했다. 실패/cleanup 보고서 이전 pose·scan 표시를 수정; final08/8source·18artifact 일치, core272/App17 PASS. 별도 actual Web/PC pipe/Isaac 정상 회귀30frame/31hash PASS이며 matrix의 Isaac 인수는 아니다. 새76member source archive도 검사했지만 target/profile/현장 미인수·AD4 PARTIAL/정식 AD5 미시작이다. 다음 대칭/sparse/재배치/revisit·drift·loop/확장 제품 인수→AD5; 기존45s 및 모든 guard/실패 원본 유지. [검증과 잔여](../verification/ad4-review-fixes-20261005.md#changing-obstacles-and-localization-recovery). 아래 checkpoint는 당시 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.268**. 두 recipe·각3목표·서로 다른 XY/yaw/odom0/prior없음의 실제 App/shared cold loop/출력 반응 scan에서 보정/fresh goal6case PASS, final02 최대9.79cm·7source/18raw artifact hash 일치. guard4/기존 source archive76member·checkout밖 inertimport/identity2test도 통과했으나 source audit만이며 target/실측/profile/현장 미인수다. 다음 changing obstacle 우회·무경로·위치상실/재정합 및 대칭/sparse/재배치/loop 제품 인수→정식 AD5. matrix Browser/Isaac NOT_RUN, 앞선 actual combined Web/Isaac 증거는 별도 유지; AD4 PARTIAL/로봇0. [근거와 경계](../verification/ad4-review-fixes-20261005.md#six-cold-goals-and-source-archive-prerequisite). 아래 checkpoint는 당시 이력이다.
- 10/05 현재 checkpoint: **Baseline v1.0.267**. v3 scoped robot idle proposal→owned append→robot ACK→동일goal 새revision/fresh plan→active/saved Isaac을 분리된 실제 App/built Web/API/PC pipe/robot subprocess/Bridge/paused Isaac으로 검증했다(26 corrected frame/1receipt/31hash). core271/관련56/단독remote+legacy-v2 4 PASS, 앞선 input만료/결합프로세스 실패 보존. 다음은 확장 방향/시작·대칭/조사한계·changing obstacle/다중목표 제품 인수→AD5이며 실물0/AD4 PARTIAL·target/실측/profile/실제사진/현장 잔여다. [근거](../verification/ad4-review-fixes-20261005.md#remote-idle-correction-and-combined-runtime-acceptance). 아래 checkpoint는 당시 이력이다.
- 10/05 최신 checkpoint: **Baseline v1.0.266**. local same-Start correction의 active owned geometry 재구성과 별도 fresh new-revision pose/scan/route를 실제 Web/API/Bridge/Isaac으로 검증했다(74 corrected frame/1 geometry receipt/22hash 일치). 실제 USD fault 전체rollback·신원/ledger/만료/중복 거절, core268/최종관련13·16/Web247/build PASS. remote idle correction ACK는 여전히 미연결/production remote 보정 잠금. 다음은 remote ACK→확장 O2–O4·combined remote pipe/Isaac→AD5, 실물0/AD4 PARTIAL. [최종 검증·제한](../verification/ad4-review-fixes-20261005.md#active-corrected-geometry-in-the-owned-isaac-scene). 아래 checkpoint는 당시 이력이다.
- 10/05 최신 checkpoint: Baseline v1.0.265. same-Start local survey/fit→idle bounded correction append→effective revision·동일goal/fresh plan→도착→보정 saved Isaac까지 실제 연결·오프라인 검증. remote idle correction ACK와 active corrected geometry recomposition은 미연결이고 production remote 보정은 비활성. core267/관련12·12(중복)/Web246/build·최종 actual Web/Isaac22hash PASS, 실물0. 다음은 이 두 연결→O2–O4 확장 제품 인수→AD5이며 아래 이전 checkpoint는 이력이다. [검증과 잔여](../verification/ad4-review-fixes-20261005.md#same-start-local-correction-and-revision-binding).
- 10/05 후속 checkpoint: Baseline v1.0.264. cold-v2 실제 PC subprocess→robot-local factory/ROS window의 합성 정상·scan시간차 실패·fit 중 ForceSTOP 인수11 PASS, 원본 로그/hash 보존. 단일 방/방향·별도 WebIsaac 인수이며 전체 O2–O4/실물 성공 아님. 다음은 같은 Start correction/revision·goal/3D 재결속이다. [검증 및 구현 경계](../verification/ad4-review-fixes-20261005.md#additional-cold-v2-pc-pipe-acceptance).
- 10/05 검토 수정 checkpoint: Baseline v1.0.263. stale active pose·cleanup 팝업·fit 진단 보존3건은 오프라인 회귀와 실제 로컬Isaac에서 검증했다. 상태는 AD4 PARTIAL이며 [야간 의존 작업·증거](../verification/ad4-review-fixes-20261005.md)를 따른다. 기존 인수/물리 기준은 완화하지 않는다.
- 상태: **AD1 오프라인·AD2 recorded frontend·AD3 bounded static-wall / AD4 cold align-only 및 local/remote scoped idle correction·goal rebind·분리 App/PC pipe/active·saved Isaac 연결 검증(PARTIAL) / 전체 obstacle/방향/다중목표 인수 잔여 / AD5 미시작 / 실제 사진 정합·target build·실측 proof/profile·현장 미인수**
- 기준 저장소: C:/Users/jaewo/Documents/TwinPulse
- 작성 당시 기준: Baseline v1.0.256. 현재 checkpoint: **Baseline v1.0.277**. 이전 구현·원본·실패 기록은 그대로 보존한다.
- 대상: 사용자가 이 계획으로 구현을 지시할 다음 6.1 Sol 작업.
- 최초 요청은 계획서 작성이었다. 이 문서 자체가 로봇 접속·배포·실물 주행·설치·유료 호출·예약·새 에이전트 생성의 승인은 아니다. 후속 AD1 구현 승인은 아래에 별도로 기록한다.

최신 후속은 사전 지도 없는 한 Start의 제한 조사→held-out 사진 fit→local/remote idle bounded correction commit·robot ACK→새revision 동일goal·fresh plan→active corrected Isaac/완료 report3D까지 실제 built Web/API/분리 App/PC pipe/Isaac으로 검증했다. **AD4 PARTIAL**: 전체 방향/대칭/조사한계/다중목표/changing-obstacle 인수는 미완료다. 실측 binding/acquisition/profile 등록·target 빌드/배포·현장 인수도 별도 잔여이며 전원만 켜면 해결되는 상태가 아니다. [최신 구현·검증·실패 보존](../verification/ad4-review-fixes-20261005.md#remote-idle-correction-and-combined-runtime-acceptance). 아래 과거 증분의 “remote ACK/cold-start/active3D 미구현”은 당시 이력이다.

2026-10-04 후속 사용자 요청으로 AD1만 구현했다. 공통 causal 관측·비차단 robot journal·원본 close·전송 진단을 기존 경로에 연결하고 core237·선택213/3skip·Web222/typecheck/build 및 실제3세션 검사를 마쳤다. COIN4patch 후보 소스는 준비됐으나 WSL 접근 거부로 TARGET_BUILD_NOT_RUN이며 미배포/실장·first-ray/통신 효과 미검증이다. 로봇을 켜기만 하면 전체 데모가 완료되는 상태가 아니다. [AD1 완료 범위와 잔여](../verification/ad1-observation-transport-20261004.md). 다음 AD2는 이 공통 recorded source를 소비하도록 구현하되 실물 권한을 추가하지 않는다.

이후 명시적 AD2 요청으로 기존 App Start→공통 causal 관측 자동 처리→bounded local bootstrap/scan-submap tracking·loss/global 재정합→persistent project map/재열기를 연결했다. core248·선택217/3skip·Web229/typecheck/build·실제3raw/원본불변/후속세션 재방문·실제Web/API PC·모바일 PASS, 합성2방×5시작·closedloop2 PASS다. 완료 범위는 **작은 방 recorded-input frontend OFFLINE_ACCEPTED**이며 global pose graph SLAM/live App 제어/Isaac/metric/현장 인수는 아니다. 다음 AD3 자동 map↔사진 recipe/형상 제안부터 기존 경로를 잇는다. robot 소스·정지기준·실물잠금 및 AD1 target build blocker는 변경하지 않았다. [AD1–AD2 누적 검증](../verification/ad1-observation-transport-20261004.md).

이후 명시적 AD3 요청으로 기존 Start 정책→일반 RoomRecipe/scene·nominal 센서높이 벽 구조→자동 SE2/분리 held-out→최대2벽/20cm 법선 이동→자동 derived revision/저장/재열기/재시작 후 rollback을 연결했다. core254·선택51·최종집중14·Web232/최종집중10/typecheck/build·서로 다른 합성2방·실제Web/API PC·모바일 PASS다. 실제3세션은 자동 처리했으나 긴2건 MODEL_MISMATCH·짧은 실패건 INSUFFICIENT_EVIDENCE로 실제 보정0이며 **SAVED_REAL_ALIGNMENT_SUPPORTED=false**다. 인수 범위는 recorded static-wall bounded 경로이며 가구 footprint/높이 실측·실제 방 성공·Isaac stage 갱신·실물 임무가 아니다. AD4–AD5와 AD1 target/현장 잔여는 유지한다. [AD1–AD3 누적 근거](../verification/ad1-observation-transport-20261004.md).

## 1. 목표와 이번 우선순위 변경

**사용자가 프로젝트와 목표를 정하고 한 번 실행하면, 프로그램이 센서 수집 → 현재 위치 추정 → 사진 기반 Twin과의 정합·관측 가능한 형상 보정 → 목표 주행·재계획 → Twin 표시·기록을 이어서 수행한다.** 사람이 저장 세션·프레임·대응점을 매번 골라줘야 하는 분석 도구를 최종 제품으로 삼지 않는다.

시작 위치·방향·주행 경로는 고정하지 않는다. 로봇을 손으로 옮겼거나 다시 켜면 새 관측으로 위치를 다시 찾는다. 정상적인 임무 안의 전진·회전·재계획마다 사용자 승인을 요구하지 않는다. 반대로 대칭 공간, 관측 부족, 시간·좌표 근거 누락을 억지로 정합 성공으로 바꾸지도 않는다.

최근의 “수동 좌표연결을 Isaac 3D에 먼저 표시” 순서는 아래 **AD1 → AD2 → AD3 → AD4 → AD5**로 대체한다. 기존 수동 분석 UI는 개발·실패 진단용으로 유지하되, 새 분석 화면만 만드는 일을 별도 완료 단계로 계산하지 않는다.

기존 [전체 데모 준비 계획](TWINPULSE_DEMO_END_TO_END_PREPARATION_PLAN_2026-09-30.md)의 목적을 폐기하는 것이 아니다. DP0/DP1 기록 기반을 재사용하고, 아직 끊어진 DP2/DP3 실행 경로와 DP4/DP5 제품 인수를 완결하는 최신 실행 순서다. 초기 사진+자연어 3D Playground, 지속 프로젝트, 별도 Isaac 창이라는 제품 방향도 유지한다.

### 사용자에게 보이는 정상 흐름

1. 저장 프로젝트를 열면 사진 기반 근사 방과 기존 Burger 모델이 나온다. 새 방은 기존 사진+자연어/편집 제품 경로로 RoomRecipe를 만든다.
2. 화면은 읽기 전용 연결 상태를 자동 확인한다. 연결 가능 여부와 주행 준비 완료는 다른 상태로 표시한다.
3. 사용자가 목표와 조사·주행 범위를 선택하고 Start를 누른다. 필요한 준비를 내부 단계로 진행하고 실제 진행 상태를 보여준다.
4. 센서와 로봇의 좌표·안전 조건이 충족되면 위치를 찾는다. 처음 보는 환경은 제한적 조사로 지도와 정합 근거를 늘린다.
5. 신뢰 가능한 정합 이후 Twin 목표를 현재 로봇 좌표로 변환해 이동한다. 센서에 따라 정지·우회·재계획하며 3D와 스캔 화면을 갱신한다.
6. 도착 또는 Stop 후 원본, 명령-관측 이력, 지도/정합/형상 revision, 비교 결과를 저장한다. 다음 실행은 저장 지도를 참고하지만 과거 로봇 자세를 현재 자세로 재사용하지 않는다.

“아무 사진·아무 방에서도 항상 자동 정합” 또는 “2D LiDAR만으로 완전한 실측 3D 복원”은 이번 완료 주장이 아니다. 자동화의 성공 조건과 식별 불가능한 경우를 함께 제품으로 구현한다.

## 2. 현재 재사용할 것과 실제 미구현을 구분한다

| 영역 | 확인된 현재 상태 | 이번에 채울 연결 |
|---|---|---|
| 사진 방 + Burger | 지정 사진에 결속된 2.8×4.2m 근사 recipe, 기존 3D 표시·모델 자산 | 일반 프로젝트 RoomRecipe 입력, nominal/관측 보정 모델 분리 |
| ROS 원본·수동 주행 | scan/odom/동적 TF와 명령 이력, PC 반출·OFF 재분석, 조이스틱+scan | live/replay 공통 관측 스트림, 제어와 대용량 기록의 지연 분리 |
| 저장 관측지도 | odom으로 endpoint를 누적하고 시간 재생 | 점유/자유/미관측 분리, scan 기반 추적·드리프트 검증 |
| 위치후보 | 전역 XY/yaw 탐색, 3프레임 후보·모호성 판정 | 자동 초기화·지속 추적·위치 상실·재정합 |
| 사진-센서 연결 | 수동 3개 fit+별도 validation, rigid SE2·historical 목표 | 자동 대응과 검증, 관측 가능한 geometry revision |
| 주행 | 로봇 로컬 명령검사·정지·bounded mission 구성요소 | 최신 정합/지도/목표를 같은 실행기로 전달, 실제 센서 기반 재계획 |
| 제품 진입 | App/API/CLI, 단일 현장 수집·고정 시험 스크립트 | 한 서비스로 전체 자동 흐름, 실제 제품 E2E와 배포 전 인수 |

반드시 유지할 사실:

- 보관 COIN 소스는 scan 시작 정보와 별개로 ROS header에 발행 시각을 넣는다. 시간 보정 fixture가 존재한다고 드라이버가 수정·배포·실측 검증된 것은 아니다.
- 저장 자료는 선언된 시각으로 해석할 수 있지만 실제 첫 광선 취득 시각·광선 순서·실장 외부좌표는 아직 검증되지 않았다. 원본에 가상의 정확한 시각/TF를 덮어쓰지 않는다.
- 현재 사진 비교의 낮은 일치율은 실제 로봇 위치오차의 측정값이 아니다. 사진 모델·시간·좌표·가구 단면이 함께 영향을 준다.
- 10/04 의도적으로 잘못 고른 네 대응점의 ANCHOR_MISMATCH는 올바른 거절 시험이다. 자동 정합 성공도, 실제 방의 정합 오차도 아니다.
- physical_controller.py의 실제 mission 진입은 mission_live_locked 상태다. 이것은 단순히 현장시험을 못 한 상태가 아니라 제품 연결이 남은 상태다.
- 통신 FIFO 수정본은 실물 미배포·효과 미검증이다. 현재 수동 0.05m/s·0.30rad/s, 자율 0.03m/s·0.20rad/s 경계를 보존한다. 요청된 수동 0.08m/s는 누락하지 않되 이번 자동화의 선행 조건으로 만들지 않는다.

근거: [저장 주행·통신 검토](../verification/saved-lap-control-review-20261003.md), [원인분석](../verification/room-scan-model-diagnosis-20261004.md), [관측지도](../verification/session-observation-map-20261004.md), [센서지도 위치후보](../verification/sensor-map-localization-20261004.md), [수동 사진 좌표연결](../verification/sensor-photo-link-20261004.md).

## 3. 구현 구조와 불변 계약

### 3.1 하나의 실행기, 세 입력 어댑터

공유 실행 서비스에 다음 세 어댑터를 붙인다. 아래 새 이름은 **구현 예정 논리 역할**이며 이미 존재하는 API나 파일이라고 취급하지 않는다.

| 역할 | 책임 | 해서는 안 되는 일 |
|---|---|---|
| RecordedObservationSource | 검증된 raw를 시간순으로 공급, 원 sequence·누락 유지 | 기록 전체의 미래 프레임을 현재 위치 추정에 미리 제공 |
| ClosedLoopTestSource | 제어 출력에 반응해 이동·센서값이 바뀌는 무장치 환경 | 정답 pose/도착 상태를 추정기·실행기에 직접 주입 |
| LiveObservationSource | 소유한 ROS 세션의 실제 메시지·수신 시각·건강 상태 제공 | 저장 pose를 live로 바꾸거나 센서 누락을 합성값으로 채움 |
| AutomaticDemoSession | 상태·epoch·취소·목표·지도/정합 revision·이벤트 관리 | HTTP 요청 하나가 긴 탐색 동안 제어 heartbeat를 막음 |
| Localization/Map service | 자동 초기화·추적·지도 갱신·품질 판정 | 매 프레임 전역 탐색/전체 raw 디코드를 반복 |
| Twin refinement service | 자동 대응·관측 가능한 형상 수정과 검증 | 추정 geometry를 실측 TF/실물 이동 권한으로 승격 |
| 기존 Robot worker/guard | 현재 센서로 최종 명령 허용·만료·정지 판단 | PC 연결이나 3D 화면 성공만 보고 주행 허용 |
| App/Isaac adapter | 동일 상태를 조이스틱/임무/3D/리플레이에 표시 | 화면에만 연결된 별도 데모 로직 구현 |

무거운 정합·3D·파일 반출은 안전 제어 루프 밖에서 실행한다. 지도나 렌더링이 느리면 화면 업데이트를 줄일 수 있지만, 오래된 명령의 생성 시각을 새로 찍어 통과시키면 안 된다. 소유자·동시 실행 잠금은 기존 제어기에 통합한다.

### 3.2 데이터·좌표·버전 계약

새 스키마는 기존 revision/hash/직렬화 규약에 추가한다. 기존 v1/v2 hash와 저장 실패 자료를 조용히 재작성하지 않는다.

- 관측: project/session/boot/release, 원 topic·sequence·raw offset, ROS 취득 stamp, robot 수신 monotonic 시각, PC 수신 시각, clock/beam-order 근거, drop/불완전 사유.
- 위치: parent/child frame, pose, 유효 시간, 관측 범위, localizer/map revision, epoch, 품질 지표, 근거 등급. 잔차만으로 covariance 또는 실측 정확도를 꾸며내지 않는다.
- 지도: occupied/free/unknown, 관측 시각·hit/free 근거, submap/지도 revision, 정적·일시 장애물 구분, source refs.
- Twin: nominal recipe와 보정 revision을 분리하고 각 변경에 대상 ID·관측 근거·변경 전후 값·검증 결과·되돌릴 revision을 붙인다.
- 임무: project/goal/map/alignment/calibration/release/epoch 결속, 한 번 승인한 공간·시간·속도·조사 범위, 실행/재계획/정지 reason.
- 오류: stage, code, severity, retry 조건, expected/observed, 원본 위치, 최초 원인과 후속 cleanup 오류를 분리한다.

ROS의 scan header는 첫 광선 취득 시각이라는 계약이다. 단순 수신/발행 시각을 그대로 대입하는 방식은 이 계약을 충족하지 않는다. [LaserScan 공식 정의](https://raw.githubusercontent.com/ros2/common_interfaces/humble/sensor_msgs/msg/LaserScan.msg).

좌표 연결은 기본적으로 **twin → map → odom → base_footprint/base_link → base_scan**을 사용한다. 실제 장착 frame 명칭에 맞추고 각 변환의 발행 책임은 하나로 제한한다. odom은 연속적인 로컬 움직임, map은 관측으로 보정되는 전역 위치, twin은 사진/저작 모델이다. [REP-105](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0105.rst).

- map→odom을 갱신해도 원본 odom을 수정하지 않는다.
- 목표는 twin revision에 고정한다. 실행 시 current twin→map→odom으로 변환하고, revision 변경 시 오래된 waypoint를 그대로 발행하지 않는다.
- 사진의 창문 방향은 draft 의미 정보이지 센서 mounting/실제 TF 증거가 아니다.
- 로봇을 옮기거나 boot/source/room/calibration이 바뀌면 이전 자세·명령·늦게 도착한 정합 결과를 무효화한다.
- 검증된 센서 장착값은 같은 하드웨어 구성에서 재사용할 수 있다. 매 실행마다 측정하거나 정지시험을 반복하지 않는다. 실제 결속 조건은 배포본·정지 정책·부팅/관측 유효성에 따라 판정한다.

### 3.3 상태와 자동 복구의 경계

상태 흐름은 IDLE → CHECKING → SENSOR_READY → LOCALIZING/SURVEY_LOCAL → ALIGNED → RUNNING → COMPLETED/STOPPED로 구성한다. DEGRADED, RELOCALIZING, FAILED를 별도로 두고 원인을 표시한다.

- 정상 임무 중 제한된 재정합·재계획은 승인 범위 안에서 자동 수행한다.
- 위치를 잃으면 출력을 0으로 하고 새 관측으로 재정합한다. 정지 관측만으로 식별되지 않으면 이미 승인한 조사 범위와 로컬 안전 조건을 만족할 때만 추가 조사한다.
- terminal Stop/Force STOP, 연결 소유권 상실, 정지 검증 실패 뒤에는 자동으로 무장·재개하지 않는다.
- 명령이 없거나 조이스틱을 놓은 상태는 IDLE_IN_SESSION이다. 이를 연결 종료·잠금으로 혼동하지 않는다.
- 준비 단계의 heartbeat와 이동 명령 freshness를 구분한다. 이미 만료된 준비 명령을 센서 준비 후 재사용하지 않는다.

### 3.4 초기 조사와 목표 주행의 순환 의존 제거

“사진 정합이 끝나야 이동 가능”만 구현하면 정합에 필요한 다른 시점의 스캔을 얻지 못한다. 다음 두 범위를 분리한다.

- **SURVEY_LOCAL:** 보드·정지·센서 외부좌표·로컬 충돌 검사 조건이 갖춰진 뒤, 승인된 짧은 거리/시간/회전 범위에서 odom/로컬 지도 기준으로 조사한다. 사진 목표를 사용하지 않는다.
- **NAVIGATE_TWIN_GOAL:** 사진/Twin과 map의 유효한 연결 및 현재 위치를 모두 확보한 뒤 사용자의 Twin 목표로 이동한다.

현재 알려진 free 영역만 조사 경로로 사용할 수 있다. unknown을 통로로 가정하거나 모호성 해결을 위해 무제한 회전/전진하지 않는다. 손으로 옮긴 로봇의 갑작스러운 불일치도 재정합 대상으로 처리하되 모든 물리적 이동을 센서만으로 항상 감지할 수 있다고 보장하지 않는다.

## 4. 실행 순서 — 다섯 개의 통합 작업 묶음

각 묶음은 코드·제품 경로·회귀·증거를 함께 끝낸다. 허용된 구현 요청을 받은 Sol은 매 소항목마다 사용자에게 “다음으로 갈까요”를 묻지 않는다. 새 권한이 필요한 부분만 분리하고 나머지 오프라인 작업은 이어간다.

### AD1. 센서 시간·좌표·전송을 자동 실행에 쓸 수 있는 입력으로 통합

**목적:** 잘못된 시각이나 전송 병목 위에 정합 알고리즘을 쌓지 않는다. DP0/DP1 기록 및 DP2 센서 수명주기의 잔여를 먼저 정리한다.

대상: robot_safety의 teleop_worker.py, teleop_ros.py, isolated_ros_scan.py, raw_ros_record.py 및 기존 드라이버 patch/배포 구성; core의 ros_observations.py, navigation_binding.py, scan_observation.py; App의 saved_mapping_evidence.py, physical_controller.py.

구현:

1. 현재 dirty 변경, 실제 배포 source와 미배포 source, 관련 golden/hash, 사용 가능한 로컬 빌드 도구를 짧은 inventory로 고정한다. 광범위한 새 감사 체계를 만들지 않는다.
2. 보관 COIN 코드의 scan_start_time 자료형·clock domain·wrap·광선 배열 순서를 확인하고, 기존 parser/lifecycle patch에 취득 시각 변환을 결합한다. 숫자만 header에 복사하지 않는다.
3. angle_min/max/increment·count·reverse·마지막 bin·range_max·NaN/Inf를 원본 의미대로 해석한다. 현재 display 경로가 받아들이는 COIN 데이터를 strict navigation도 의미적으로 처리할 수 있는지 시험한다. 미수신/유효하지 않은 광선은 unknown이며 안전 범위를 넓혀 PASS시키지 않는다.
4. 취득시각, 수신시각, age의 각 clock을 명시한다. 과거 자료는 TIMING_UNVERIFIED로 유지하고 신규 시각 계약을 만족한 자료와 구분한다.
5. scan/odom/TF를 같은 관측 버퍼·보간·출처 계약에 연결한다. 실장 확인 없는 nominal mounting과 검토된 calibration을 구분하고 충돌용 footprint 근거도 함께 기록한다.
6. 수동 입력·watchdog와 stdout/raw/저장/반출 경로를 분리한다. 미배포 FIFO 수정에 순서·backpressure·journal stall 시험을 보강하고 deadline을 늘려 증상을 숨기지 않는다.
7. browser intent → PC 수락 → wire 기록 → robot 수락 → publish → odom/정지 관측을 sequence로 연결한다. Wi-Fi/PC/robot 지연의 어느 구간인지 모를 때는 UNKNOWN_CAUSE를 보존한다.
8. AD2가 소비할 공통 관측 source 인터페이스를 연결한다. scan 미수신·늦음·TF 누락·복수 publisher·QoS 불일치·프로세스 exit에 구체적 원인을 제공한다.

검증·완료선:

- 보관 실제 3세션을 기존 raw 그대로 읽으며 원 count/누락/실패를 보존한다.
- 취득시각/광선순서 fixture에 회전 중 deskew, 시간 역행, wrap, gap, tail 미보간을 포함한다.
- 느린 stdout·disk·긴 분석 작업을 주입해도 제어 경로가 멎지 않거나 기존 정책대로 보호 정지하며 최초 원인이 남는다.
- C++/ROS 대상 빌드는 이용 가능한 승인된 toolchain에서만 수행한다. 빌드 불가면 TARGET_BUILD_NOT_RUN으로 남기고, 해당 live artifact는 출하 준비 완료로 표시하지 않는다. 다른 오프라인 작업은 계속한다.
- 실제 첫 광선 취득 시각·실장 calibration·통신 수정 효과는 현장 잔여다. fixture PASS를 물리 검증으로 기록하지 않는다.

### AD2. 자동 실행기 + 지속 위치 추정·지도 서비스 연결

**목적:** 사람이 프레임을 선택하지 않아도 들어오는 스캔으로 위치가 갱신되는 첫 제품 경로를 만든다. DP3를 마지막 UI 붙이기 작업으로 미루지 않는다.

대상: core의 room_localization.py, sensor_map_localization.py, scan_observation.py; App의 room_localization_review.py, saved_mapping_evidence.py, product_workflow_service.py, project_store.py, api.py; Web의 RoomLocalization.tsx, BedroomTwin.tsx.

구현:

1. AutomaticDemoSession을 기존 App 작업·취소·소유자 체계에 추가한다. replay/live/closed-loop 입력만 바뀌고 상태 전이·localization 호출·기록 방식은 공유한다.
2. 과거 저장자료를 시각 순서로 공급하는 causal replay를 먼저 제품 API에 연결한다. pause/seek는 새 epoch이며 과거 권한·후속 결과를 무효화한다.
3. 새 환경은 지도 없는 local bootstrap, 재방문은 이전에 완결해 저장한 지도 기반 global relocalization으로 나눈다. 같은 세션의 나중 스캔으로 초반 위치를 맞추는 시험을 cold start 성공으로 계산하지 않는다.
4. 기존 bounded global matcher는 초기화/위치 상실 때 재사용하고, 정상 추적은 odom 예측 주변의 scan-to-submap 정합으로 처리한다. reference decode·distance field를 source/map revision별 캐시한다.
5. 위치후보의 구분도·관측 분포·연속 프레임 일관성·innovation을 검사한다. 단일 best score 또는 3개 연속 고상관 스캔만으로 신뢰도를 높이지 않는다.
6. timestamp가 붙은 occupied/free/unknown 지도를 생성한다. 유효한 ray로 관측한 free 영역만 사용하며, endpoint 없는 공간을 자동 free로 채우지 않는다.
7. odom 누적지도와 보정 지도를 분리한다. keyframe/submap 재관측으로 드리프트를 줄이고, 일관된 제약이 부족하면 지도 확정/loop closure를 거절한다. odom-only 결과를 SLAM이라고 이름 붙이지 않는다.
8. 지도·keyframe·보정 근거를 persistent project에 저장하고 다음 실행에서 다시 읽는다. 다른 시작점/방향·odom reset·재부팅·손 이동에 대해 새 위치 추정을 한다.
9. 알고리즘의 방 크기·frame/cell·시간/메모리 예산을 명시한다. 먼저 기존 matcher 기반 작은 방 범위를 완결한다. 그 범위에서도 드리프트/성능 인수가 안 되면 SLAM backend 교체 필요를 근거로 제시하고, 새 설치를 몰래 수행하거나 끝없는 자체 SLAM 개발로 확대하지 않는다.

검증·완료선:

- **프레임 선택 없이** App Start → 관측 수신 → 후보/추적/위치 상실/재정합 → 저장/재열기가 동작한다.
- 실제 raw는 미검증 타이밍 등급을 유지하면서 시간순 처리된다. 식별 불가능한 구간은 AMBIGUOUS/LOST로 남는다.
- 독립 평가용 정답이 있는 closed-loop 환경에서 시작 XY/yaw 변경, 다른 경로, odom drift, 위치 점프를 처리한다. 정답 pose는 평가기만 가진다.
- 입력 주기보다 처리가 느릴 때 queue는 무한히 늘지 않는다. 파생 화면/분석의 생략과 원본 기록의 누락을 각각 집계한다.
- 표시 전용 local map/pose가 실제 제어 허가로 흘러가지 않는 음성 시험을 통과한다.

### AD3. 사진 Twin과 자동 정합하고 관측 가능한 형상을 갱신

**목적:** 수동 점대응을 정상 실행에서 제거하고, 사진 모델을 센서에 맞춰 보정하는 본래 데모 기능을 만든다.

대상: core의 sensor_photo_link.py, room_localization.py, scan_correction.py, map_refresh.py, revisions.py; App의 bedroom_twin.py, room_localization_review.py, 기존 RoomRecipe/scene 저장; Web의 SensorPhotoLink.tsx, SensorMapLocalization.tsx, BedroomTwin.tsx.

구현:

1. 현재 특정 PHOTO_SHA256/default project 제한을 새 자동 경로의 입력 전제로 쓰지 않는다. 기존 지정 사진 recipe는 fixture로 보존하고, 일반 프로젝트의 versioned RoomRecipe/scene/profile을 받아들인다.
2. 사진 외형 mesh와 LiDAR 높이의 예상 단면을 분리한다. 책상/침대 하부를 근거 없이 바닥부터 가득 찬 장애물로 간주하지 않는다. 근거 없는 하부 형상은 unknown이며 미관측 공간을 삭제하지 않는다.
3. 관측 지도에서 안정적인 벽 선분·모서리·구조 배치를 추출하고, 사진 recipe의 구조 후보와 자동 대응시킨다. 가구는 먼저 오차가 큰 soft prior로 취급한다.
4. 여러 SE2 후보를 만들고 서로 다른 시점·관측 영역의 데이터로 평가한다. manual fit에서 사용한 residual/degeneracy 검사를 재사용하되 자동 후보와 별도 검증 자료를 분리한다.
5. 대칭·불충분 관측·서로 모순된 구조를 탐지한다. 먼저 AD2/AD4의 제한적 추가 조사로 근거를 늘리고, 여전히 구분 불가능하면 사람의 최소 추가 정보가 필요하다고 표시한다. 틀린 정합을 성공시키지 않는다.
6. pose 정합과 geometry 수정을 번갈아 수행하더라도 한 번에 하나의 고정 revision을 평가한다. 모델을 늘리거나 이동해 모든 잔차를 없애는 퇴행 해법을 막는다.
7. 관측으로 식별되는 벽 위치/간격·평면 장애물 위치/footprint만 제한적으로 보정한다. 단일 전역 scale로 사진 오차를 덮지 않는다. 높이·재질·안 보인 면은 기존 근사값/unknown으로 유지한다.
8. 반복 관측 지지·별도 validation·형상 유효성·revision 충돌 검사를 통과한 제안만 시작 때 선택한 자동 보정 정책 안에서 새 revision으로 적용한다. 정상 흐름에 매번 Apply 버튼을 요구하지 않는다.
9. 변경 전 모델·사진·기존 물체 ID를 보존하고 rollback 가능하게 한다. 이동 물체를 벽 보정으로 고정하지 않는다. 새 revision으로 목표 의미나 안전 통로가 바뀌면 AD4에 목표 재검증을 요청한다.
10. 저장 자료 전체를 재사용하는 경우 학습/fit과 평가 구간을 기록한다. 같은 raw/boot의 odom·TF는 독립 ground truth가 아니다.

검증·완료선:

- 서로 다른 두 RoomRecipe에서 사람의 frame/point pair 선택 없이 자동 정합·보정 흐름이 실행된다. 지정 침실 크기/배치를 하드코딩한 정답이 없어야 한다.
- 정답이 있는 환경에서 위치오차와 geometry 오차를 별도로 측정한다. baseline odom-only/nominal 모델보다 개선되거나 변경을 거절하는 이유를 남긴다.
- 대칭 방·부족한 벽·가구 이동·사진 치수 오류·다른 시작 방향에서 false confident alignment를 내지 않는다.
- 실제 저장 3세션을 자동 처리한다. 기존 실패/모호성이 남아도 숨기지 않는다. 실제 사진 연결이 여전히 모호하면 “저장 실자료 정합 확인 완료”는 불합격이며 원인·최소 추가 증거를 따로 제시한다.
- 수동 대응 UI는 Advanced diagnostics에 남길 수 있지만 정상 자동화 인수시험에서는 사용하지 않는다.

### AD4. 최신 정합·실센서·목표·로봇 로컬 제어·3D를 한 임무로 연결

2026-10-05 현재: **PARTIAL**. v3 versioned idle wall correction 및 remote ACK·fresh goal/geometry를 기존 제품 경로에 구현했고, separate App/PC pipe/actual paused Isaac/built Web 통합 인수까지 통과했다. v1/v2·원본·정지/source timing/45 s 및 실제 admission 잠금은 유지한다. 다음 구현·인수 대상은 확장 방향/시작·대칭/조사 한계·changing obstacle/다중목표이며 AD5는 아직 미시작이다. 아래10/04 설명은 당시 checkpoint다. [최종 근거](../verification/ad4-review-fixes-20261005.md#remote-idle-correction-and-combined-runtime-acceptance).

2026-10-04 최신 구현 현황: **PARTIAL**. 기존 prior 경로에 추가로 no-prior `SURVEY_THEN_NAVIGATE`의0.5m 제한 조사→causal 지도→분리 held-out 자동 사진 fit→fresh matching→공유 actual goal loop, v2 robot bootstrap·75 member 의존 closure, active Isaac main-thread 갱신 및 동일 immutable report3D를 연결했다. 합성2방/2시작, Stop-during-fit late차단, pose/stale/footprint/receipt/API 회귀 및 built Web→실제Isaac 활성78frame/저장3D PASS. **다음은 같은 Start의 bounded wall correction/derived revision commit·새 goal/3D 재결속, 방향/대칭/조사 한계·전체 changing-obstacle/다중목표 제품 인수다.** 일부 코드시험을 O1–O6 전체 통과나 AD5 완료로 표시하지 않는다. qualified live adapter 코드는 연결됐으나 실측 mounting/acquisition/target/profile/release 등록·현장 검증이 없고 실제3raw 사진 정합은 여전히 unsupported다. [누적 최신 검증](../verification/ad1-observation-transport-20261004.md#ad4-cold-start-and-active-twin).

**목적:** 화면의 위치후보와 실제 실행할 명령 사이의 단절을 없앤다. DP2 목표→주행/재계획/Twin과 DP3 단일 세션을 완결한다.

대상: core의 local_navigation.py, bounded_grid_plan.py, navigation_binding.py, mission_contract.py; robot_safety의 mission_runtime.py, teleop_ros.py, teleop_worker.py; App의 physical_controller.py, bedroom_rehearsal.py, api.py; Web의 PhysicalRobotController.tsx, RobotQuickConsole.tsx, BedroomTwin.tsx; Extension의 bedroom_preview.py, isaac_adapter.py, runtime.py.

구현:

1. 사용자의 goal을 Twin revision에 결속하고 AD3 alignment와 AD2 current pose/map을 통해 current odom 목표로 변환한다. historical goal 경로를 live 경로로 재명명해 사용하지 않는다.
2. SURVEY_LOCAL과 NAVIGATE_TWIN_GOAL을 같은 mission owner·명령/관측 로깅·local guard로 실행한다. 센서 조사와 주행이 서로의 소유 프로세스를 중복 기동/종료하지 않게 한다.
3. 기존 bounded planner 입력을 실제 관측 occupancy/free/unknown과 footprint에 연결한다. 목표가 unknown/막힌 곳이면 안전한 조사 또는 명시적 거절로 처리한다.
4. 장애물 변화 → 출력 0 → 현재 pose/map에서 새 경로 → 검증 → 동일 승인 범위 내 재개를 구현한다. 고정 synthetic 이벤트만으로 재계획 PASS를 내지 않는다.
5. map/alignment revision 변경 때 waypoint를 원자적으로 교체한다. 큰 pose jump·goal 충돌·위치 상실 때는 먼저 멈추고 검증한다. old waypoint와 new transform의 혼합을 금지한다.
6. 실제 mission hardlock을 제거하는 단순 boolean을 만들지 않는다. live 지원 adapter와 release/calibration/current sensor/stop qualification/scope 검증을 구현하고, 조건을 만족한 실행만 열리게 한다. OFF 시험에서는 fake transport로 이 실제 검증 분기를 통과시킨다.
7. Stop은 새 명령/queue를 취소하고 현재 bounded segment 뒤 정지한다. Force STOP은 기다리지 않고 즉시 정지/OFF 요청을 보낸다. cleanup 중에도 Force STOP이 가능하고 terminal 이후 자동 재개는 없다.
8. 현재 local guard는 최종 방어선으로 유지한다. 보수적인 원형 envelope 때문에 회피가 불가능한 경우 먼저 이유를 기록한다. 방향별 swept-footprint 등 정책 변경이 필요하면 별도 버전·분석·회귀·현장 qualification 대상으로 명시하고 기존 기준을 몰래 완화하지 않는다.
9. 기본 mission 시간·속도·waypoint 제한을 UI/로그와 일치시킨다. 현재 로봇 요청의 45초 상한을 긴 방 순회로 홍보하지 않는다. 더 긴 임무가 필요하면 승인 범위 안의 예산/재계획 정책을 명시적으로 설계·검증하고, 45초마다 사용자 재클릭으로 대체하지 않는다.
10. Isaac에서는 같은 session/revision의 Burger pose, scan, 궤적, goal, 지도/형상 변경 전후를 표시한다. /World/TwinPulse 밖은 수정하지 않는다. 렌더 지연이 주행 heartbeat를 막지 않게 한다.
11. UI는 Connection / Preparing / Localizing / Surveying / Ready / Driving / Stopping / Failed를 구별한다. 상단에 현재 단계·진행시간·다음 행동 하나, 중앙에 3D/scan·조종, 상세 로그는 접는다. 영어가 기본이며 spinner만 무한 표시하지 않는다.
12. LiDAR 수신·stale·중단 요청·프로세스 종료·물리 회전체 정지의 증거를 구분한다. joystick release는 바퀴만 정지하며 session 유지, 명시 Stop은 정한 세션 종료 정책대로 동작한다.

검증·완료선:

- 실제 App/API → 공유 서비스 → fake transport를 쓴 실제 worker 계약 → 센서 피드백 → 제어 → Twin 상태의 닫힌 루프가 동작한다. 성공값을 주입하는 mock은 제품 인수를 대신하지 않는다.
- 시작 위치/방향·목표가 다른 복수 시나리오에서 고정 route 없이 수행하고, 장애물·위치 상실 시 적절한 재계획/정지를 한다.
- fresh input, local scan, source/epoch, 배터리, 출력 watchdog·정지 기준을 그대로 검사한다.
- 브라우저/Isaac까지 실행한 증거가 있어야 해당 runtime을 PASS로 기록한다. 엔진이 없으면 core/API 통과와 Isaac NOT_RUN을 분리한다.
- 실제 로봇 배포·실행·충돌 회피 인수는 AD5 이후 별도 현장 승인에서만 수행한다.

### AD5. 전체 제품 인수·배포 준비·한 번의 현장 세션으로 마감

**목적:** 로봇을 켠 뒤 미구현 경로를 찾아 코드를 새로 붙이는 상황을 줄인다. DP0 동작 감사와 DP4/DP5 전체 인수를 실제 실행 근거에 연결한다.

대상: 기존 demo_operation_manifest.py/demo_contract.py, audit_demo_operations.py, run_robot_field_suite.py, verify_demo_offline_operations.py, 설치/릴리스 manifest, 관련 integration/Web E2E와 검증 기록.

구현:

1. 자동 연결 점검·센서 시작/정지·초기 조사·위치 추정/상실·목표 변환·주행/재계획·일반/강제 Stop·반출/재열기를 기존 operation manifest에 추가/결속한다. 함수 존재 여부가 아니라 제품 경로의 실행 증거를 요구한다.
2. 기존 run_robot_field_suite.py를 공유 서비스의 CLI 진입점으로 확장한다. UI와 CLI가 별개의 테스트 로직/해시/준비 순서를 갖지 않게 한다. 진단 모드 호환성은 유지한다.
3. PC-only 모드에서 소스/패키지/키 존재·호스트 기록·도구·driver/library/프로필/정지 정책 결속·raw reader·자원 상한·앱 준비를 미리 확인한다. 비밀 내용은 출력하지 않는다.
4. 준비한 artifact와 실제 배포본 차이는 “해시가 다름” 하나로 끝내지 말고 로컬/원격 버전·변경 범주·필요한 준비를 표시한다. 이미 검증한 동일 부팅/배포/정책의 정지 기록은 불필요하게 다시 요구하지 않는다.
5. 하나가 실패해도 독립적인 안전한 정보 수집·원본 보존·진단·cleanup 검사는 계속한다. 단, 그 실패에 의존하는 이동/배포는 SKIPPED_DEPENDENCY로 표시하고 실행하지 않는다.
6. 실패 보고서에는 첫 실패·연쇄 미실행·cleanup 실패·최종 상태·원본 파일·재시도 조건이 한 번에 나온다. 조용한 실패, 무한 로딩, 완료처럼 보이는 연결 실패를 제거한다.
7. 제품 재시작/다른 프로젝트 재열기에서 지도·사진·goal/revision·로그를 복원한다. 신선한 연결/현재 pose/이동 권한만은 복원하지 않는다.
8. 동일 환경/목표/시드/동역학으로 baseline과 보정 후 경로를 비교한다. 충돌 감점은 우선 closed-loop/시뮬레이션에서 시험하고 실제 충돌을 의도적으로 발생시키지 않는다. 센서 기반 회피와 충돌 검출 한계를 각각 표시한다.
9. 한 번의 명령/Start로 전체 OFF 인수 보고서를 생성한다. 새 CLI 옵션·명령은 구현 후 --help 및 실제 실행으로 확인해 기록한다. 아직 없는 실행 명령을 문서에 완성품처럼 적지 않는다.
10. 패키지 설치본/배포 묶음에서도 검사한다. 개발 checkout에서만 통과하는 파일 누락·import·LD 경로 문제를 남기지 않는다. 원격 실행을 제외한 준비와 실패 진단은 로봇 OFF에서 완료한다.

완료선은 아래 5절의 O1–O6을 모두 판정한 보고서다. PASS 숫자 합계, 테스트 symbol 매핑, 모의 성공 화면으로 대신할 수 없다.

## 5. 인수시험과 완료 판정

### 5.1 서로 다른 네 종류의 증거

| 종류 | 증명할 수 있는 것 | 증명하지 못하는 것 |
|---|---|---|
| Unit/계약/fake transport | 오류 처리·검증 분기·명령 순서·정지/무효화 | 실제 센서 정확도·이동·통신 품질 |
| 실제 저장 ROS causal replay | 실제 메시지 해석·시간순 자동 분석·모호성/누락 처리 | 새 제어 출력에 대한 로봇 반응, live freshness/현재 위치 |
| 출력에 반응하는 closed-loop 환경 | 자동 초기화·목표 추종·재계획·보정 통합 논리 | 실제 마찰·제동·Wi-Fi·장착 오차 |
| 승인된 실제 현장 세션 | 해당 배포·환경·범위의 센서/정지/주행 효과 | 모든 환경·속도·장시간 무인 안전 보장 |

과거 lap 전체를 reference map으로 쓰는 재방문 시험은 유효하나, 첫 방문 cold start 시험과 반드시 구분한다. recorded replay에 내보낸 제어 명령이 실제 저장 궤적을 만들었다고 주장하지 않는다.

### 5.2 반드시 실행할 묶음

- **O1 데이터·제어 회귀:** 실제 세션 4493be87…, b6cf3467…, 실패 1a7f033a…의 원본/순서/누락/finish_stop/INPUT_DEADLINE_EXPIRED 보존. driver 시간·좌표·전송·Stop 계약 검사.
- **O2 자동 재방문/초기 지도:** known-map와 map 없는 cold start를 분리. 서로 다른 XY/yaw, odom0, 다른 경로, 대칭, sparse scan, 재배치, drift, loop 재관측 포함. 사용자 frame/pair 선택 0회.
- **O3 자동 사진 연결/보정:** 다른 두 recipe, 의도적으로 어긋난 벽/가구, 정확한 모델, 대칭 모호성. 맞는 자동 대응뿐 아니라 잘못된 confident link 거절과 검증실패 rollback 확인.
- **O4 자동 임무 closed loop:** 목표 도착, 동적 장애물 우회, 경로 없음, 위치 상실/재정합, 지도 revision 교체, 일반/강제 Stop, terminal 뒤 late 명령 차단.
- **O5 실제 제품 경로:** 브라우저→인증 API→공유 실행기→관측/제어 adapter→Isaac 표시→저장→재열기. 현재 제품 코드로 실행하며 결과를 UI mock에 미리 주입하지 않는다.
- **O6 패키지/실패 복구:** checkout 밖 패키지 구성 확인, 누락 라이브러리·ROS 시작 실패·boot/source 변경·disk full·queue full·전송 단절·엔진 종료·UI 새로고침/탭 이탈. 전체 진단과 최종 상태가 남아야 한다.

다음은 **로봇 OFF 인수를 위한 제안 기준**이다. 물리 정확도나 안전 보증 수치가 아니다. AD1에서 고정된 시험 manifest에 데이터·seed·프로필과 함께 기록하고 결과를 본 뒤 유리하게 바꾸지 않는다.

| 인수 항목 | 고정할 최소 시험과 판정 |
|---|---|
| 자동 위치 추정 | 다른 두 방, 방마다 다섯 시작 XY/yaw. 식별 가능한 ground-truth fixture에서 TRACKING 출력의 95% 이상이 XY 0.10m·yaw 5° 이내. 모호한 구간은 이 정확도 집계와 별도로 LOST/AMBIGUOUS 처리율을 보고 |
| 잘못된 자신감 방지 | 대칭·부족한 scan·다른 프로젝트·위치 점프 fixture에서 정답과 다른 위치를 주행 가능한 정합으로 수락한 횟수 0. 모든 입력을 거절해서 통과할 수 없도록 위 positive 시험도 필수 |
| 형상 보정 | 서로 다른 관측 구간을 fit/validation으로 분리. 식별 가능한 의도적 벽 오차 fixture에서 held-out 구조 오차가 nominal보다 감소. 정확한 nominal 모델을 임의 변경하거나 미관측 높이/면을 실측으로 채운 횟수 0 |
| 목표와 재계획 | 두 방의 관측된 free 영역에서 각각 세 목표. 정상·우회 가능한 환경은 기존 목표 도착 조건으로 완료, 무경로·식별불가 환경은 비도착 원인과 정지. 환경 정답 기준 충돌 0 |
| 명령 경계 | 오래된 source/epoch/revision, terminal Stop 이후 비영 명령 수락/발행 0. 조이스틱을 놓은 뒤 정상 session이 유지되는 경우와 terminal 종료를 구분 |
| 시간과 부하 | 정상 replay는 원시 기록 속도 1배로 처리하고, 장기 queue 증가 없음. 제어 freshness·scan age·출력 만료는 현재 코드의 한계를 유지. 지연 주입 때 보호 정지 이유와 최초 지연 구간 기록 |
| 반복과 저장 | 동일 seed/입력/정책은 의미적으로 같은 결정 이력. 재열기 뒤 raw/hash/지도/보정 revision이 같고, 현재 pose/실물 실행 권한은 새 관측 전 복원되지 않음 |

센서 오차·지도 해상도 때문에 위 신규 알고리즘 기준을 만족할 수 없다면 원인과 대안을 보고한다. 테스트를 빼거나 거절을 성공으로 바꾸지 않는다. 현재 정지·출력 freshness 기준은 별도의 기존 계약이며 변경하지 않는다.

임의의 “몇 mm 정합”을 물리 정확도 합격선으로 만들지 않는다. ground truth 없는 저장자료에서는 geometry consistency/ambiguity만 보고하고, 물리 오차 합격선은 현장 측정 방법과 함께 검증한다.

### 5.3 이번 과거 실패에서 빠지면 안 되는 회귀

| 과거 증상 | 이번 검증 포인트 |
|---|---|
| SSH 준비 여부가 불명확 | PC 조건·인증·호스트 신원·연결 불가를 구분, 사용자 보고의 부팅 2–3분은 추정 안내이지 무조건 성공 타이머가 아님 |
| 준비 중 input lease 만료 | PREPARING heartbeat 분리, 준비 후 fresh intent만 수락 |
| scan 드라이버 library exit127 | 묶음 구성·동적 library 경로·기동 전 검사·stderr 원본 |
| CRLF 해시 불일치 | 비교하는 파일/정규화 정책과 실제 배포 bytes를 일치시킴 |
| 수동 release 뒤 Lock/매번 재접속 | session idle와 terminal stop 분리, 정상 release 후 계속 조작 |
| INPUT_DEADLINE_EXPIRED | PC 입력/전송/로봇수락 간 지연 계측, disk/stdout stall 주입, guard 기한 불변 |
| scan이 보이지만 navigation 거절 | display와 control 검증 사유 차이, 실제 metadata/시각/TF·coverage 검사 |
| Stop LiDAR 반응 불명 | 요청/수락/종료/quiet/회전체 증거 상태 분리, cleanup 오류 누락 금지 |
| 한 시험 실패로 다른 원인 미수집 | 의존 단계만 차단하고 독립 진단·원본 반출·최종 상태 확인 지속 |
| 저장 후보를 live처럼 사용 | project/boot/source/time/epoch/scene 변경 즉시 무효화 |

### 5.4 상태 보고 규칙

각 AD 묶음에 **PLANNED / IMPLEMENTED / OFFLINE_ACCEPTED / FIELD_VERIFIED**를 따로 기록한다. BLOCKED에는 정확한 외부 조건과 계속 가능한 항목을 적는다.

- OFFLINE_IMPLEMENTATION_READY: AD1–AD5 필요한 코드·O1–O6 제품 경로 인수 완료. 예외/NOT_RUN을 숨긴 통합 PASS 금지.
- TARGET_ARTIFACT_READY: 해당 target 빌드·패키지·필수 파일·source/calibration 계약 검증 완료. 로봇 OFF에서 만들지 못했으면 별도 미완료.
- SAVED_REAL_ALIGNMENT_SUPPORTED: 저장 실자료에서 자동 연결 근거를 확보했는지 별도 표시. 실제 자동 연결이 계속 모호하면 false.
- FIELD_VERIFIED: 새 승인 현장시험을 통과한 그 범위만 해당.
- DEMO_READY: 현재 프로젝트/로봇/배포/현장 조건의 필수 검증을 모두 만족할 때만 true.

실제 데이터가 부족해도 O2–O4의 알고리즘/제품 구현은 진행한다. 그러나 실제 저장 자료 전체가 모호한 상태를 “로봇만 켜면 반드시 된다”로 표현하지 않는다.

## 6. 로봇이 필요한 시점과 그때 한 번에 할 일

로봇은 위 구현의 대체 수단이 아니다. **AD1–AD5에서 알려진 코드 단절을 제거하고, 현장 실행 파일·패키지·진단이 준비된 뒤** 아래 묶음의 검증에 필요하다. 당시 로봇 전원/현장 상태/허용 임무 범위는 새로 확인한다.

1. 읽기 연결·배포/boot·배터리·보드 상태를 수집한다. 승인된 범위에서 필요한 source 준비·안전한 초기 상태를 만들며, 동일한 유효 정지 기록은 재사용한다.
2. stationary scan/odom/TF/driver timing/실장 frame·footprint 근거를 확인한다. 소프트웨어만으로 측정할 수 없는 치수·장착·물리 정지는 해당 항목만 최소한으로 확인한다.
3. 소스·정지 정책 변경 때문에 필요한 경우 한 번의 짧은 qualification을 수행한다. 전후좌우·Stop/Force STOP·scan 동시 기록·최종 보드 관측을 같은 세션에 남긴다.
4. 승인된 제한 범위에서 자동 초기 위치/주변 조사→사진 연결/보정→짧은 목표 주행→장애물에 대한 비접촉 정지/재계획을 수행한다. 초기 위치를 바꾼 재정합 검증도 예산 안에 포함한다.
5. 전체 원본·판정·최종 상태·cleanup·반출을 저장한다. 실패 시 움직임은 멈추되 독립적인 안전한 진단은 끝낸다. 임의 재배포·무한 자동 재시험은 하지 않는다.

한 번의 현장 승인 안의 내부 동작마다 재확인을 요구하지 않는다. 반면 실패한 qualification을 몰래 반복하거나, 승인 시간/공간/속도를 늘리거나, terminal Stop 뒤 자동 재시작하지 않는다. 예산 안에 못 끝낸 항목은 정확히 NOT_RUN으로 남긴다.

## 7. 범위 관리와 Sol 작업 방식

- 기본 실행 순서는 AD1→AD2→AD3→AD4→AD5다. 작업 중간에도 같은 작은 end-to-end scenario를 확장해 제품 연결을 유지한다.
- 첫 구현 checkpoint는 AD1의 공통 관측·전송 회귀와 AD2의 최소 시간순 실행 경로다. 기존 실제 raw 한 세션이 사람의 frame 선택 없이 App/API에서 처리되고 시간/좌표 문제를 분류하는 것까지 연결한다. inventory 문서만 작성하고 첫 묶음을 종료하지 않는다.
- AD2·AD3의 자동 연결을 끝내지 않고 수동 분석 패널/새 점수표/보고서만 계속 추가하지 않는다.
- 새로운 범용 SLAM·대형 AI 학습·유료 사진 생성·클라우드 모델 라우팅은 이번 필수 범위가 아니다. 기존 사용 가능한 구성요소를 우선 재사용한다.
- 수동 0.08m/s는 별도 후속 정책 작업이다. guard/명령/UI/qualification/제동 근거를 함께 바꿔야 하며 현재 상수를 한 곳만 바꾸지 않는다.
- 회귀는 변경 관련 집중 시험 → 묶음 회귀 → AD5 전체 제품 인수 순서다. 사소한 문서 수정마다 전체 Isaac/브라우저 suite를 다시 돌리지 않는다.
- 기존 dirty 변경과 원본 자료는 보존한다. commit/push, 새 설치·시스템 설정·유료 호출, 타 프로세스 강제 종료, 로봇 접속/배포/실물시험은 별도 현재 승인이 필요하다.
- 기본 검증 보고서는 한 통합 문서의 AD1–AD5 절로 누적한다. 원본 실행 artifact는 별도 보존하되 자잘한 계획서 수십 개로 분산시키지 않는다.
- 의미 있는 완료/실패/필수 판단 때 코드 변경·실행 시험·미검증·다음 종속 작업을 짧게 보고한다. 각 묶음에서 Baseline/Memory와 실행 현황을 동기화한다.
- 외부 blocker가 생기면 그것에 의존하지 않는 안전한 작업을 진행한다. 같은 조건을 반복 확인해 토큰을 소모하지 않는다. 새 권한/설치가 필요하면 이유와 정확한 최소 요청을 남긴다.
- 종료 보고는 “몇 개 테스트 PASS”가 아니라 AD1–AD5 상태, O1–O6 근거, 아직 필요한 데이터/외부 조건, 현장 한 번의 실행 순서로 작성한다.

## 8. 6.1 Sol에 전달할 실행 지시문

다음 문단은 사용자가 구현을 맡길 때 전달하는 지시문이다. **이 계획서를 작성한 현재 턴의 실행 지시는 아니다.**

> C:/Users/jaewo/Documents/TwinPulse의 AGENTS.md, 최신 PROJECT_MEMORY/BASELINE, TWINPULSE_AUTOMATIC_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-04.md를 읽고 이 계획의 AD1부터 AD5까지 의존 순서대로 구현·검증하라. 목적은 저장자료 수동 분석 도구가 아니라, 시작 위치가 달라도 센서 수집→자동 위치 추정/지도→사진 Twin 정합·보정→목표 주행/재계획→3D/기록이 한 서비스로 연결되는 제품이다. 기존 코드·dirty 변경·원본·과거 실패·hash/직렬화·정지 기준을 보존하고 실제 App/API/worker/Isaac 경로를 연결하라. 로봇은 OFF로 간주하라. 별도 승인 전 로봇 SSH/serial/센서/모터/배포/실물시험, 새 설치·시스템 설정·유료 API·commit/push·타 프로세스 강제 종료·새 에이전트 생성은 하지 마라. 수동 frame/점대응, 정답 주입 mock, 전체 미래 lap을 이용한 cold-start 성공으로 자동화 인수를 대체하지 마라. 실제 저장자료 causal replay와 출력에 반응하는 closed-loop 시험을 구분해 둘 다 수행하라. 각 묶음에서 관련 회귀와 한 통합 검증 보고서·Baseline/Memory를 갱신하고, 진행 가능한 범위는 매번 사용자에게 다음 단계 승인을 묻지 말고 이어가라. 필수 외부 blocker는 분리하되 미구현을 현장 데이터 부족으로 넘기지 마라. 마지막에는 AD1–AD5/O1–O6의 정확한 상태, target artifact 준비, 실제 저장자료 정합 여부와 한 번의 현장 확인 순서를 보고하라. 실물 데모 완료나 무조건 성공을 보장하지 마라.
