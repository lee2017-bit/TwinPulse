# TwinPulse 채팅 중심 데모 상세 구현 계획

## 실행 현황 2026 October 6 Baseline v1.0.313

검토한 compiled driver의 단일 identity를 기존 manual/scan/mission adapter와 단독 수집에 연결하고91source 동일후보를 실제 로봇 current에 반영했다. hash/ARM64/private library·cached prepare 거절을 검증했고 focused57/field212, target CTest9/9/7.69s·battery615·독립 artifact-preflight PASS다. **센서/모터 시작0, torque=true(바퀴/명령0)로 prepared attention; 배포 실패 아님.** 새release stop/실제 scan/odomTF/lifecycle·실측/정합/현장 인수 잔여, C3–C6 PARTIAL/whole false. 기존 guard/profile/원본/과거 실패·예약 PAUSED 유지. [실제 연결·다음 단계](../verification/robot-driver-path-integration-20261006.md). 아래 원문과 이력은 보존한다.

## 실행 현황 2026 October 6 Baseline v1.0.312

승인된 실제 로봇의 격리 ARM64 Humble driver build를 완료했다. `Time.to_msg()` API 오류를 additive 패치로 수정하여 clock harness/configure/single·multi/library/AArch64 ELF와 반출 해시·기존 driver/current 불변을 검증했다. focused62 PASS, compiled-source receipt를 field 후보에 연결했으나 activation=false다. **target build blocker 해소 / 센서시작·모터·driver 실행·active 배포0 / C3–C6 PARTIAL/whole false.** 다음은 검토된 scan adapter 경로·해시 연결과 별도 현장 lifecycle/scan·odom·TF/실측·새release stop/정합·목표 검증이다. [실제 결과·잔여](../verification/robot-target-build-20261006.md). 아래 원문과 이력은 보존한다.

## 실행 현황 2026 October 6 Baseline v1.0.311

기존 `run_robot_field_suite.py`의 OFF 후보 준비와 동일 manifest 소비를 연결했다. 실측값 생성/자율 profile 활성화 없이89개 source와35개 corrected COIN source를 고정했고 실제 패치 누락 결함을 수정했다. focused68, collection79(3skip)+11/field190 PASS(중복 counts). **C3 전체 완료 아님: ARM64 corrected driver build NOT_RUN·실측 timing/외부좌표/footprint·profile/등록 잔여, 실물/배포0·C3–C6 PARTIAL/whole false.** 현재 PC compiler/WSL blocker를 우회하지 않는다. 다음 별도 승인 target 무이동 확인·빌드→실측·새release qualification→통과한 정합/짧은goal/Stop 순서이며 무관한 C6 완료 대기는 필요 없다. [검증·후보·현장 준비 범위](../verification/robot-field-candidate-20261006.md). 아래 사용자 원문과 이전 현황은 보존한다.

## 실행 현황 2026 October 6 Baseline v1.0.310

2026-10-06 v310 — native cleanup·adapter cleanup·최초 원인·저장 오류를 기존 goal/채팅과 실제 nonmodal 팝업에 분리 표시했다. native worker/App ID 불일치로 current Isaac 표시가 거절되던 결함과 current-room Burger 연결을 수정했고 raw ID/hash는 보존했다. 현재 sensor prim은 종료·stale 시 숨기고 새 검증 frame만 재표시한다. 최종 Python257/370.078s·93source·17case, Web335/42files·TypeScript/build·Node1 PASS. actual built Chrome/App/Bridge/Isaac 정상 두 목표+scan/stall 복합 실패09–11 PASS·각49runtime/4build 불변·current→hidden·popup/chat·reload 비재실행·소유 child 정상종료. 새 dirty 개발 패키지 r2는502files/22,444,139bytes·체크아웃 밖71검사·분리 raw 해시 보존 PASS. **실물0/미배포·C4/C5/C6 PARTIAL·whole readiness=false**. 이전30분 결과는 새 current-render 조건의 자원 검증이 아니며 기존 FAIL도 보존한다. 다음은 새 렌더 조건의 자원/나머지 coupled fault→최종 package SIM/REAL D01–D12→target/별도 현장 인수; 로봇 없이 다음 작업 가능하다. guard/raw/dirty 유지·설치/유료/배포/commit/push/새agent0·heartbeat PAUSED. [검증·정확한 잔여](../verification/goal-coupled-ui-native-display-20261006.md). 아래 사용자 원문과 이전 현황은 이력·요구로 보존한다.

## 실행 현황 2026 October 6 Baseline v1.0.309

2026-10-06 v309 — native 입력 오류가 halt/cleanup 실패로 덮이는 결함을 수정하고 원인·bounded cleanup·보고서 저장 오류를 분리 보존했다. viewer는 단일 canvas·ImageBitmap 해제·bounded JPEG 수신으로 바꿨다. 최종 Python245/367.406s·88source·17복합case, Web332/42files·TypeScript/build, 임시 profile 경계1검사 PASS. 실제 built Chrome/App/Bridge/Isaac/native 합성 1806.823s·21왕복(42완료구간)·Stop/reload PASS·47runtime/4build 불변·88archive/독립 cleanup·소유 child 정상종료. 120자원 표본의 private-memory 변동 backend36.113/browser64.660/engine202.777MiB는 각128/256/1024MiB 이내, 최종 로그105.258MiB였다. actual viewer 8camera·stale 제거/복구·접기/reload PASS(5.717FPS/p95 202.54ms·11source 불변); 별도 legacy headless still capture의 viewport_missing FAIL은 보존한다. **합성 센서·실물0/source NOT_DEPLOYED·C4/C5 PARTIAL·whole readiness=false**. 앞선 자원/관측기 실패는 보존하고, network body를 보관하지 않는 격리 관측기의 정상 임시 profile 제거를 검증했다; 정확한 inspector 내부 원인은 미확정이다. 다음은 남은 built UI+Isaac 복합 fault 인수→C6 최종 package 두 분기/target·별도 현장 인수이며 로봇 없이 다음 코드 작업 가능하다. 기존 guard/raw/dirty/FAIL 유지·유료/새 시스템설치/배포/commit/push/새agent0·heartbeat PAUSED. [검증·정확한 잔여](../verification/goal-task-soak-faults-20261006.md). 아래는 당시 이력이다.

## 실행 현황 2026 October 6 Baseline v1.0.308

2026-10-06 v308 — 같은 native worker의 원본 시각·source-bound 배터리 추정/다음 경유지를 저장 세션→App→5초 채팅·goal card·우측 Twin에 연결했다. stale/Stop/종료·소유권/출처 변경·재전송은 현재값으로 표시하지 않는다. 실제 nonzero publish 후 odom·scan 양쪽의 충분한 위치 진척을 확인하지 못하면 OBSERVED_PROGRESS_STALLED로 다음 출력 전 정지하며 정합 오류 우선순위를 보존한다. 최종 Python184/313.125s·64 frozen source, Web327/42files·TypeScript/build PASS; 실제 Chrome/App/Bridge/Isaac/native 합성 3왕복(6반복구간)·Stop/reload 및 예상 정체 실패/원인·보고서·독립 cleanup PASS·38runtime/4build 불변·15+2archive/소유 child 정상종료. **C4/C5 PARTIAL·whole readiness=false·실물0/source NOT_DEPLOYED**. 전압 추정은 용량 실측이 아니며 motor load는 UNSUPPORTED; 진척 기준의 실물 보정은 미검증이다. 다음은 30분 실제 경과시간 자원/로그 검사·복합 fault/cleanup matrix→C6/package/target·별도 현장 인수다. 다음 오프라인 작업에 로봇 불필요·raw/dirty/과거 FAIL/기존 guard 유지·heartbeat PAUSED. [검증·정확한 잔여](../verification/mission-live-progress-20261006.md). 사용자 원문·기존 완료 기준을 보존하며 아래 실행 현황은 당시 이력이다.

## 실행 현황 2026 October 6 Baseline v1.0.307

2026-10-06 v307 — 도착 후 채팅의 Repeat A↔B 한 번 승인으로 새 관측·자원·actual Isaac 경로 검사→기존 bounded native goal을 반복하는 상위 작업을 연결했다. 독립 Stop/Force·브라우저 소유권·저장 이력/복원 비재실행·실패 시 다음 구간 차단을 검증했고 검사 후 arming 전 원본 입력/Stop 처리 지점을 추가했다. 최종 Python153/154.637s·50source, Web320/42files/build, actual Chrome/App/Bridge/Isaac/native 합성 연속 두 반복구간(왕복1회)·Stop/reload PASS·35runtime/4build·7archive/cleanup/소유 child 정상종료. **C4/C5 PARTIAL·whole readiness=false·실물0/source NOT_DEPLOYED**. 01 frame/03 input expiry FAIL 보존, 필드 지연 해결 보장 아님. 다음 live 자원/waypoint·progress-stall→C5 3왕복/30분·fault matrix→C6/target/별도 현장 인수다. 다음 코드에 로봇 불필요·guard/raw/dirty/과거실패 유지·heartbeat PAUSED. [검증·정확한 잔여](../verification/goal-task-loop-20261006.md). 사용자 원문·기존 완료 기준을 보존하며 아래 실행 현황은 당시 이력이다.

## 실행 현황 2026 October 6 Baseline v1.0.306

2026-10-06 v306 — 목표 임무의 5초 채팅 요약을 같은 메시지 갱신으로 연결했다. Stop/위치상실·도착/실패·cleanup/report 후속 원인은 5초 대기 없이 다음 poll에서 표시하고 종료·재시작 관측은 이력으로 구분한다. 최종 Python129/145.620s·44source 불변, actual App/Chrome/Bridge/Isaac/native 합성 두 목표 PASS·29runtime/4build·5archive/cleanup/소유 child 정상종료. **실물0/source NOT_DEPLOYED·C4 PARTIAL/whole readiness=false**. live 배터리·다음 waypoint는 receipt에 없어 unavailable이며 C5 persistent loop→C6/target 및 별도 현장 인수가 남는다. 유료 요약/새 이동권한 없음·guard/raw/dirty/FAIL 보존·heartbeat PAUSED. [범위와 잔여](../verification/goal-progress-chat-20261006.md). 아래는 당시 이력이다.

## 실행 현황 2026 October 6 Baseline v1.0.305

existing built chat→authenticated Bridge/actual Isaac exact preview→단일 Confirm→native 합성 도착을 두 목표에서 통과했다. reload 비재실행·지연 원본 거절·5세션 재열기·모든 peer cleanup·소유 child 정상종료까지 PASS. handoff/fsync·visual lock, 동일 mission service 결속, authenticated lease rotation, late raw/cleanup·strict archive 진단 계약을 수정했고 legacy hash와200/250/50ms·.03/.20·45s·실물잠금은 유지했다. 최종 Python165/113.903s·41source, actual25 PASS·27runtime/4build 일치. **합성 센서/test-only qualification·실물0/source NOT_DEPLOYED·C4 PARTIAL/whole readiness=false**. 두 목표는 각각 fresh worker/합성 시작점이며 실물 연속 loop 검증 아님. 다음 goal5초요약→C5 persistent 왕복 loop→C6/target 인수, 새 현장 승인 후 실물 검증은 별도. 다음 코드에 로봇 불필요·raw/dirty/이전FAIL 보존·소유 시험 종료·heartbeat PAUSED. [범위·실패·잔여](../verification/goal-separated-latency-20261006.md). 사용자 원문과 아래 이력을 보존한다.

## 실행 현황 2026 October 6 Baseline v1.0.304

분리된 실제 App/Bridge/Isaac/Chrome 경로와 native 합성 worker를 연결하고 engine lease·관측 수신 lock·반복 room reload·정합 원인 소실·첫 arming zero tick·strict event 계약을 수정했다. exact-goal watch는 같은 owner/source/engine guard를 검사하는 별도 sender로 분리했으며 보고서350ms 지연 회귀에서도 reactive 도착을 확인했다. 최종 고정소스 Python94/118.380s·28source 전후일치 PASS. **actual built UI/Isaac 첫 시연 후 Confirm 새 관측은 12번 EVIDENCE_STALE·13번 SOURCE_OR_TRANSPORT_CHANGED로 거절; 전체 통합 인수 FAIL·실물0·C4 PARTIAL/whole readiness=false**. 두 trial22source/Web 일치·원본보존·소유 child 정상종료, 실패/dirty/raw/200/250/50ms·.03/.20·45s·실물잠금 유지·source NOT_DEPLOYED·heartbeat PAUSED. 다음은 동시 runtime의 fresh-query decode/commit/transport 지연 계측/해결→두 목표 도착·reload/지연 거절 통합→goal5초요약/C5/C6; target/현장 별도. 다음 로컬 진단에 로봇은 필요하지 않다. [검증·정확한 잔여](../verification/goal-separated-journey-20261006.md). 사용자 원문·기준과 아래 이력을 보존한다.

## 실행 현황 2026 October 6 Baseline v1.0.303

검토 대기를 owned idle 정상종료/정리확인 후 memory reservation으로 분리하고, 단일 Confirm→새 disabled-wheel 관측/전체 기존경로 재검사→같은 새 worker 실행을 연결했다. additive v2는 1cm/.020rad 후보 envelope·추가1cm clearance이며 실측 정확도 아님; v1 strict·qualification·200/250/50ms·.03/.20·새 active worker 총45s는 유지한다. 좌표 round-trip/새 session 출처 거절·완료 SIM의 Stop 무효화·실패 정리를 수정했다. 최종 Python75/169.716s·19source 일치, Web319/42files/23.50s·build3hash, actual Isaac v2 두 경로/9source PASS. **combined Kit/native는 INPUT_DEADLINE_EXPIRED·출력0/정리확인 FAIL 보존, Chrome/target NOT_RUN·실물0·C4 PARTIAL/whole readiness=false**. 다음 분리된 실제 App/Bridge/Isaac 통합 지연 계측/해결→goal5초요약·C5/C6, target/현장 별도. [검증·실패·정확한 잔여](../verification/reviewed-route-admission-20261006.md). 다음 코드에 로봇 불필요·source NOT_DEPLOYED·raw/dirty/과거실패/guard 보존·소유시험 종료·heartbeat PAUSED. 아래는 당시 이력이다.

## 실행 현황 2026 October 6 Baseline v1.0.302

검토된 exact REAL review/current actual SIM receipt→단일 chat Confirm→소유 full-reference READY idle worker→같은 native mission을 연결했다. 전체 review/raw/hash/순서·새 disabled-wheel·first nonzero 전 pose/source·기존 gate/총45s/.03/.20/qualification을 보존한다. 최종 Python55/145.055s·16source 일치, Web318/42files/24.11s·기존3build 해시 PASS. **명시 합성 estimator/로컬 transport·이번 Chrome/Isaac/target NOT_RUN·실물0·C4 PARTIAL/whole readiness=false**. tiny matcher jitter exact 거절·45s review lifecycle은 미검증 gap; 다음 오프라인 noise-aware 계약/시간 lifecycle→combined actual chat/embedded Isaac/native 인수→goal5초요약·C5/C6, C3 target/현장 별도다. [범위·중간실패·정확한 잔여](../verification/exact-goal-handoff-20261006.md). source 미배포·원문/기준/이력/guard 보존·다음 코드에 로봇 불필요·소유시험 종료·heartbeat PAUSED. 아래 실행 현황은 역사 기록이다.

## 실행 현황 2026 October 6 Baseline v1.0.301

현재 REAL 목표의 exact review를 기존 broker/Isaac PhysX에 연결해 실제 두 경로 시연·도착/Pause·current engine/stage/run receipt를 검증했다. Python82/Web318/build·9source 최종일치 PASS이며 합성 센서/방·Chrome/target NOT_RUN·실물0이다. **C4 PARTIAL/whole readiness=false**. 원격 full-reference exact-plan idle→driving handoff는 아직 없으므로 Confirm 잠금이며 다음 native first-output/소유 handoff·combined actual UI→goal5초요약/C5/C6 순서다. [범위·오류·정확한 잔여](../verification/exact-goal-demonstration-20261006.md). 사용자 원문·기준은 보존하며 아래 실행 현황은 역사 기록이다.

## 실행 현황 2026 October 5 Baseline v1.0.294

현재 생성한 chat room을 기존 observed mission에 결속하고 조사 전용 SURVEY_ONLY/v4를 추가했다. inline 조사 Confirm 한 번은 survey/held-out 정합/fresh tracking까지만 승인하며 goal 주행하지 않는다. REAL fresh room-only Build와 복원 명시 표시, 오래된/변경방 승인 거절·명시 readiness 재점검·비재실행, terminal 과거 pose·fit/map 저장·독립 Stop/Force·5초 요약/즉시 오류를 연결했다. Python85/21/focused5(중복)/보존survey2/Web305/build·actual Chrome/local API10+기존6 PASS·각41source/4build 일치. **fixture 합성 관측·실물0·Isaac/target build NOT_RUN·C4 PARTIAL·whole readiness=false**. 새 survey-only는 align_only이며 wall correction/derived revision/remote fullfit-map replay, semantic 목표/actual SIM 시연/exact Confirm·viewer, C5/C6는 잔여다. 다음 오프라인 코드에 로봇 전원 불필요. [범위와 근거](../verification/chat-current-room-inspection-20261005.md). 사용자 원문·요구·이력·guard는 그대로 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.293

기존 채팅→명시 stationary 수집→개별 odom/scan/TF 원인·단계 결과→서버 결속 saved raw 전송재개를 기존 서비스/CLI에 연결했다. 수집 당시 실패와 후속 복구를 구분하며 전송 실패 후 가능한 분석/identity mismatch unbound/미실행 의존 이유·BLOCKED_LOCAL을 보존한다. fsync 멱등 예약·reload 비재실행·source SHA/receipt 검증·다른 owner 전송 중복 차단, 원본 실패 보존을 검증했다. Python154/Web301/build·actual Chrome/local API 준비9+기존6 case PASS·각30source/4build 일치·소유 테스트 종료. **명시 가짜 센서/전송·실물0·Isaac/target build NOT_RUN·C3 PARTIAL·whole readiness=false**. 전체 moving field-suite/binary/profile·실측은 잔여다. 다음은 독립 C4 current generated room survey/정합·semantic goal/digest-bound preview/Confirm·mission/3D/status, C5 TaskLoop, C6이며 target blocker는 이 오프라인 구현의 중단 사유가 아니다. [구현·근거·잔여](../verification/chat-collection-recovery-20261005.md). 아래 사용자 원문·요구·이력·guard는 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.292

REAL 로봇 선택→생성과 병렬 읽기 전용 점검→현재 boot/release에 결속된 1회 고정 검증→관찰 질문을 기존 diagnostics/PhysicalController에 연결했다. 명시 재점검·저장 복원 비재실행·단계별 원인/cleanup/원본반출 상태, 독립 Stop/모바일 global Force STOP 및 일반 정지의 자동 강제정지 방지를 검증했다. Python98/Web299/build, actual Chrome/local API 준비6+기존6 case PASS·각25source/4build 해시 일치·소유 테스트 종료. **명시 가짜 로봇 전송/실물0/Isaac NOT_RUN·target build NOT_RUN·C3 PARTIAL·whole readiness=false**. full collector/전송재개 채팅 작업·reviewed binary/profile와 C4 current-room 조사/정합/경로 Confirm, C5 TaskLoop, C6 인수가 남는다. target blocker는 독립 C4/C5 코드의 중단 사유가 아니다. [범위·근거·다음 순서](../verification/chat-real-preparation-20261005.md). 아래 사용자 원문/요구·이력·guard는 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.291

현재방 photo human-review24개 그룹, 기존가구7+생활물체19종의 site2.2/선택provider/영문chat inventory/기존saved edit·3D·SIM 연결을 구현했다. 케이블·천·unknown의 별도 합성keepout, 위치누락목록/현재source결속/필수19개 미표현 시 SIM preview/goal/plan/Run 거절을 검증했다. Numeric XYZ/크기/yaw preview·명시save는 원본보존; 새물체drag UI 인수는 아니다. Python215+focused7(6중복)/Web296/build/6case와 final actual19종fixture chat/API/Isaac Build/Burger PhysX/도착/Stop/Reset/reload/mobile PASS·43source/4build 일치·소유프로세스 종료. **사진 정확 재구성/새paid해석/실물 NOT_RUN·C1/C2 PARTIAL/whole readiness=false**, 임의사진의 자동완전성·실측/실제provider·잔여C1 및 C3–C6 REAL은 별도다. [24개 목록과 검증](../verification/room-object-inventory-20261005.md). 아래 원문/이력/guard는 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.290

실행 중 오류/응답유실과 exact USD rollback을 actual Isaac으로 인수했다. backup재컴파일·root삭제로 PhysicsScene이 만료되는 결함을 수정하고 zero/pause·원인보존·run_id소실 때도 현재오류표시·옛 route승인폐기를 연결했다. actual3장면 lower transaction, final chat/API/Isaac fault/Run응답유실 재전송0/reload비재개 및 거실 fixture→Build→Burger PhysX/sofa goal/Stop/Reset/mobile PASS; 각29source/4build·lower6source hash 일치/소유프로세스 종료. 선택된 siteprovider2.1에 기존7종 가구 계약, 미지원SIM로봇 inline 명시대체 선택을 연결했다. Python192/Web293/build/기존6case PASS. **새 paid/사진해석 NOT_RUN·실제 구동 Burger1종·C1/C2 PARTIAL/전체ready=false**: prerequisite/package/native-window/회사PC·실제provider/추가모델 인수 및 C3–C6 REAL은 별도 잔여다. [검증과 경계](../verification/chat-sim-fault-diversity-20261005.md). 사용자 원문·아래 이력·실물guard/dirty/raw는 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.289

시작 무결성 점검과 실제 소유 프로젝트 왕복 전환을 인수했다. Web build manifest/Burger 고정 9개 hash/extension/Python 독립 조건, 새 소유 derived 폴더 2개·각1회 생성/실패 lock해제·spawn0, 관측 시각과 현재 command gate를 분리했다. actual chat/API/Isaac 왕복·재열기/원본 불변·20source/4build 전후 불변, 실제 초기 import 실패→명시 기존 Isaac 새 세션 복구, 최종 text SIM Build/PhysX/Stop/Reset PASS. Python144/Web290/build/기존6case PASS·소유프로세스 종료. 무Build host scene FAIL은 보존하고 시작 범위만 인수한다. **fixture 생성/저장 방, 새 LLM사진해석·실물 인수 아님; C1/C2 PARTIAL·전체 readiness=false**. 다음 actual running fault/rollback·장면/로봇 다양성·잔여 prerequisite/package/native-window/회사PC 인수, 이후 C3–C6 REAL. 다음 코드에 로봇 불필요. [근거와 정확한 잔여](../verification/chat-startup-integrity-project-switch-20261005.md). 사용자 원문과 아래 이력은 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.288

Run 전 무물리 Burger preview를 같은 scene/검사 plan의 기존 Build에 연결했다. 명시 Run에서 visual숨김/PhysX, Stop 후 명시 Reset에서 visual복구/plan·telemetry폐기를 actual final text/image Web/API/Isaac으로 인수했다. 각27source/3build hash·Python83/Web289/build/기존6case PASS·소유프로세스 종료. 준비실패 원인·Run잠금과 복원 비재실행 유지. **생성응답만 v2 fixture; 새 LLM사진해석·실물 인수 아님. C1/C2 PARTIAL·전체 readiness=false**. 다음 startup manifest/필수항목 구분·bounded repair·actual project-switch/fault/scene·robot 선택다양성, 이후 C3–C6 REAL; 로봇 없이 가능. [범위/근거/잔여](../verification/chat-sim-burger-preview-20261005.md). 원문 요구와 아래 이력은 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.287

새 사진/글→inline Q1→SIM 생성→검사된 illustrative start/route→자동 current-room Build→명시 Run→actual Burger PhysX 도착→현재pose chat goal/Stop→reload/mobile 전체 제품 journey를 연결했다. final text03/image01 Web/API/Isaac PASS, 각26source/3build hash·Python81/Web288/build·기존6case PASS·소유프로세스 종료. 생성 응답만 명시적 v2 fixture이므로 새 LLM 사진 해석이나 실물 인수는 아니다. Auto-Build는 방 render이며 실제 PhysX Burger는 Run에서 생성; pre-Run 3D visual 배치 잔여. **C1/C2 PARTIAL·전체 readiness=false**. 다음 pre-Run visual/C1 prerequisite·repair·project-switch/actual fault-reset, 이후 C3–C6 REAL. 로봇 없이 가능. [범위/증거/잔여](../verification/chat-driven-demo-sim-journey-20261005.md). 사용자 원문·완료 기준과 아래 이력은 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.286

지원 offline SIM 문장→scene/object·도달 가능한 외곽→중복 inline 선택→경로 review→기존 Run/채팅 Stop을 제품에 연결했다. final actual10 Web/API/Isaac 좌표/침대 외곽 도착·Stop/동일pose/reload/mobile PASS, 19source/3build hash·Python77/Web286/build 확인. 중복 질문은 실제 로컬 API fixture 인수, actual Isaac 다중 선택 UI·임의 LLM 호출/새 사진 해석 인수가 아니다. **C1/C2 PARTIAL·전체 readiness=false**. 다음 fresh 사진/글→Q1→generation→Build/Run 전체 journey/C1 prerequisite·실패와 actual runtime fault/reset; C3–C6 REAL은 별도 잔여다. 다음 코드 작업에 로봇 불필요. [범위/증거](../verification/chat-driven-demo-c2-physics-20261005.md#natural-language-sim-goal-acceptance). 사용자 원문·완료 기준과 아래 이력은 보존한다.

## 실행 현황 2026 October 5 Baseline v1.0.285

최종 actual06에서 기존 채팅의 명시 좌표 preview→한 Run/현재 v2 Build→Burger PhysX 목표 도착→Stop/위치 불변→reload/mobile을 인수했다. Build receipt보다 applied snapshot이 늦는 경쟁, 응답 유실과 조회의 무한 대기, 현재 작업 누락·엔진 오류 popup·과거 오류 표시도 회귀로 수정했다. Python64/Web284/build 및 14source/3build hash 확인. **C1/C2 PARTIAL·전체 readiness=false**: 다음은 자연어 SIM 목표·경로 review와 전체 사진/텍스트 생성 journey, C1 잔여 인수다. actual runtime fault/reset과 C3–C6 REAL은 별도 잔여이며 다음 구현에 로봇은 불필요하다. [최신 근거](../verification/chat-driven-demo-c2-physics-20261005.md#current-result-after-readiness-corrections). 아래 v283 이하는 당시 실행 이력이며 사용자 원문·완료 기준은 변경하지 않는다.

## 실행 현황 — 2026-10-05 / Baseline v1.0.283

C2의 연속 viewer 기술 경로를 기존 소유 Isaac host/API/기본 채팅에 연결했다. 실제 Isaac/Chrome으로 8개 camera 동작·접기/reload·화면 수신 상실/회복과 4초 표시5.62FPS/p95 185.72ms를 확인했다. Web270/Python83/build 및 기존 채팅6case34검사 PASS. **C1·C2 모두 PARTIAL**이며 v2 실행 binding/실제 Physics Run/정상 채팅 자동 Build→Run 및 목표/Stop이 다음 제품 작업이다. C1 staging·전체 prerequisite/repair·실제 project-switch 인수도 남았다. C3–C6/전체 12단계/실물 완료가 아니며 로봇 전원은 다음 코드 작업에 필요하지 않다. [최신 구현·증거·미완료 순서](../verification/chat-driven-demo-c2-viewport-20261005.md)를 실행 기준으로 읽는다. 아래 v282와 작성 당시 PLAN_ONLY 설명은 역사 기록이며 원문 요구·기존 완료 기준은 그대로 유지한다.

## 실행 현황 — 2026-10-05 / Baseline v1.0.282

사용자가 이 계획에 따른 구현을 승인했다. C1의 기본 채팅→Q1/Q2→기존 생성, 영속·멱등/복원, Projects/저장 v2 Add/Change, pending edit와 런처 진단을 실제 제품에 연결했고 Web266/Python76/build·실제 Web/API6시나리오 및 소유 초기화 실패/재시도 경로를 확인했다. **C1은 PARTIAL**이다. 자연어 staging·전체 prerequisite/repair matrix·owned 실제 project-switch 성공 UI 인수가 남았다. 우측 연속 viewer/v2 Physics Run 및 C3–C6은 아직 구현/인수 완료가 아니다. [증거와 다음 순서](../verification/chat-driven-demo-c1-20261005.md)를 최신 실행 기준으로 읽는다. 아래 작성 당시 v279/v281 기준 및 사용자 원문은 이력/요구 원문으로 보존하며 실제 인수를 대신하지 않는다.

작성일 및 상세화: 2026-10-05 KST. 구현 담당: GPT 6.1 Sol. 제품 코드 검증 기준: Baseline v1.0.279. 문서 기준: Baseline v1.0.281. 이 문서는 사용자가 제시한 12단계 데모와 후속 UI 요구를 완성하기 위한 실행 계획이며, 작성 자체는 구현 완료가 아니다.

결론부터 말하면, 원클릭 실행기, 사진·텍스트 생성, Isaac 장면 생성, 수동 로봇 제어, 관측 기록, 자동 정합·목표 주행의 구성요소가 있다. 그러나 **사용자가 요청한 채팅 하나에서 두 분기와 반복 임무까지 이어지는 제품은 아직 없다.** 기존 기능을 버리고 새 모형을 만드는 것이 아니라, 검증된 서비스를 하나의 지속 세션에 연결하고 실제로 없는 실행 기능을 보완해야 한다. 로봇을 켜지 않아도 이 계획과 선행 구현을 진행할 수 있다.

## 0 사용자 원문과 해석 우선순위

### 최초 데모 요청 원문

다음은 사용자 원문이다. 철자·표현을 교정하거나 의미를 줄이지 않았다. 이 인용은 요구사항의 출처이며, 현재 문서 보완 요청만으로 로봇 구동·설치·유료 호출을 실행하라는 지시가 아니다.

> 아래 상세 데모 계획을 기반으로 현재 이미 되어있는부분과 추가 구현해야하는 부분을 파악하고 6.1Sol에게 시킬 상세 구현 계획서를 작성해줘라. 혹시 상세 구현 계획서 작성 전 로봇 구동이 먼저 있어야 한다고 판단하면 그것부터 해도 된다. 만약 내가 좀 더 구체적으로 말해줘야하는 내용이 있으면 물어보면 답변해주겠다.
> 
> 데모
> 1. 원클릭으로 Twin Pulse를 구동한다
> 2. 자동으로 Background에 Isaac Sim이 켜지고 필수 파일이나 세팅이 되어있는지 확인하고, 안되어있으면 스스로 해결할 수 있으면 해결시도를 해보고 해결시도 실패하거나 스스로 할 수 없는 작업이면 정확히 필요한것중 되어있는것과 안되어있는게 체크리스트 형태로 뜬다.
> 3. TwinPulse의 LLM채팅창에 사진을 업로드하고 내용을 넣는다. 글자만 넣어도 작동한다. LLM 채팅창 UI는 ChatGPT와 동일한 형태로 한다.
> 4. LLM이 묻는다, 실제 로봇이 있느냐고, 선택지가 생기고 클릭을 통해 답변할때까지 기다린다(ChatGPT가 질문하는것처럼). 로봇이 없는경우 5번, 로봇이 있는 경우 6,7,8,9,10,11,12순서대로 진행.
> 5. 실제 로봇이 없다고하면 자동으로 사진이나 LLM에 나온 설명과 유사한 형태의 로봇을 골라서 3D Twin을 만들기 시작하고 만드는 과정을 ChatGPT처럼 설명한다(Call하는 Tool등, 현재 진행상황 등). 완료가 되고 Run을 누르면 로봇이 3D Twin상에서 움직이며 이후 조작은 모두 LLM한테 말로 시켜서 작동하게 할 수 있다. 3D Twin 화면도 우측에 보이고 접을수도 있다.
> 6. 실제 로봇이 있다고하면 등록된 로봇리스트(현재 기준: Burger3)를 보여주고 그중에 하나를 고르라고 한다. 
> 7. 고르면 3D Twin을 생성하기 시작하며 동시에 자동으로 해당 로봇과 연결 Test를 진행한다.(이전에 만든 로봇 수동주행 프로그램처럼) 연결이 정상적으로 완료되고, 채팅창에 1회 주행검증 버튼이 나오고 그걸 누르면 로봇이 움직이고 실제 움직였는지 확인하는 버튼이 채팅창에 뜬다. 실제 움직였다고 확인버튼을 눌러주면 이제 로봇이랑 연동이 된 상태이다. 3D Twin을 실시간으로 만들고있는 화면은 웹화면 우측에 보이고 안보이도록 접을수도 있다. 로봇 배터리 %랑 연결상태 현황, 로봇이 현재 진행하고 있는 작업 리스트도 우측 위에 표시된다
> 8. 만들어진 3D Twin과 로봇 연동이 모두 완료가 되면 채팅창에 Twin 검사작업 시작할지에 대한 Confirm여부에 대해 버튼으로 채팅창에 올라오고, Confirm 누르면 진행한다.
> 9. Confirm 눌러서 진행하면 로봇이 움직이기 시작하고 3D Twin으로 만든 내용을 한번 더 Lidar로 구체적인 위치를 보정한다
> 10. 완성된 3D Twin에서 채팅으로 현재 위치에서 특정위치로 가는 경로를 3D Twin상에서 최적경로를 시연해달라고 말하면 최적경로를 계산해서 3D Twin상에서 움직이고 해당 경로로 움직이도록 지시할지 채팅창에 Confirm여부 버튼이 나옴. 
> 11. Confirm 버튼을 누르면 그대로 움직이고 채팅창에 실시간으로 들어오는 데이터를 통해 현재상황을 5초마다 정리해서 계속해서 알려준다.
> 12. 이동이 완료가 되고 다시 원래 위치로 돌아오는 Loop명령으로 만들건지 선택하는 버튼이 있고, 누르면 정지버튼을 누르거나 배터리가 기준치보다 낮을때, 장애물에 걸려 모터토크가 제대로 안걸릴때 등의 특이사항을 제외하고는 원래위치로 돌아왔다가 다시 해당위치로 갔다가 다시 목표위치로 가는 루프작업을 진행한다. 해당 루프작업은 3D Twin화면상에 현재 진행작업 리스트에 뜬다. 정지버튼을 누르면 정지도 가능하다.

### 후속 확정과 이번 보완 요청 원문

음성 입력 범위에 대한 사용자 답변:

> 텍스트 채팅 우선, 음성은 후속

계획서 검토 요청:

> 그러면 내가 요청한대로 Chat GPT UI의 채팅/질문버튼이 들어가있는지 등 상세 구현계획서 자세히 적혀있는지 검토해줘

이번 보완 요청:

> 그래 6.1Sol이 만든걸 내가 맨날 다시보고 수정하고 다시보고 수정하고 이러니까 너무 힘드네. 한번에 내 의도대로 만들어줄 수 있게 내 원문이랑 같이 상세 구현방향을 잘적어줘. 그래야 6.1Sol이 잘보고 수정하지

### Sol이 임의로 축소하면 안 되는 의도

원문은 사용자가 원하는 제품 행동이며, 3절의 구체적인 배치·상태·시험은 이를 구현하기 위한 기준안이다. 구체적 수치·스타일은 이미 사용자가 승인한 완성 디자인이라는 뜻이 아니다. 합리적인 미세 조정은 가능하나 채팅 밖의 점검 패널 왕복, 매명령 승인, 불명확한 버튼 상태, 정지 사진을 실시간 3D로 대체하는 변경은 요구 축소다.

핵심은 ‘채팅이 들어간 로봇 관리 대시보드’가 아니라 **채팅에서 이해·질문·선택·생성·실행을 이어가는 TwinPulse**다. 사용자는 자연어 요청과 필요한 선택 버튼을 사용하고, 준비·연결·도구 실행·상태 전환은 제품이 처리한다. 기존 수동 조이스틱은 진단 보조 기능이지 최종 화면의 중심이 아니다.

UI와 비동기 흐름을 정상적인 제품으로 만들 책임을 사용자에게 돌리지 않는다. 버튼이 눌리는지·상태가 유지되는지·입력이 사라지는지 등 개발자가 스스로 확인 가능한 문제는 Sol이 먼저 재현·수정한다. 물리 관측이나 선호가 정말 필요한 질문만 한꺼번에 짧게 묻는다. 이후 C1–C6 구현을 승인받으면 완료 조건을 충족하는 작업 묶음 단위로 진행하고, 위젯 하나마다 ‘다음으로 갈까요?’를 묻지 않는다.

읽는 순서는 **0절 원문 → 3절 화면 및 상호작용 명세 → 4·5절 서비스/기능 계약 → 6절 작업 순서 → 8절 인수 시험**이다. 원문과 구현 기준이 충돌하면 조용히 다른 기능으로 대체하지 말고 충돌을 명시한다. 안전·실측 근거 부족은 정확히 표시하되, 그것을 이유로 오프라인 UI 연결 작업까지 중단하지 않는다.

## 1 확정 요구와 이번 작업의 범위

- 사용자의 2026-10-05 12단계 요청을 최상위 사용자 흐름으로 삼는다. 기존 AD1–AD5의 시간·좌표·정합·제어 계약과 실패 기록은 계속 사용한다.
- 사용자 추가 답변: **텍스트 채팅 우선, 마이크 음성 입력은 후속**이다. 음성 인식·합성을 이번 완료 조건에 끼워 넣지 않는다.
- 사용자 입력은 한국어 등도 이해하되, 기존 Global Hackathon 요구에 따라 기본 제품 UI·상태·버튼·assistant 응답은 영어로 한다. 이 구현 계획서와 개발 중 사용자 소통은 한국어다.
- 기존의 별도 Isaac 창 중심 방향에서 **웹 우측에 접을 수 있는 실시간 Isaac 3D 화면**을 제공하는 방향으로 요구가 변경됐다. 별도 창은 진단용 보조 수단이며 우측 화면 구현의 대체 완료 조건이 아니다.
- 물리 로봇은 현재 등록 대상인 **TurtleBot3 Burger**부터 지원한다. 사용자가 부르는 Burger3와 같은 대상으로 표시하되 내부 ID는 안정적으로 관리한다.
- 실제 이동 승인 위치는 사용자 요청대로 한 번의 주행 검증, Twin 조사, 경로 실행, 반복 임무 선택이다. 승인된 임무 안의 개별 속도·회전·재계획마다 다시 질문하지 않는다.
- 자동 연결 확인과 자동 환경 복구가 자동 이동·임의 배포·시스템 설치를 뜻하지 않게 한다. 현재 계획 작성에서는 로봇 연결, 배포, 센서, 모터, 유료 호출을 실행하지 않았다.
- 사진은 근사 외형 자료이며 LiDAR는 관측 가능한 단면과 이동을 보완한다. 단일 사진에서 정확한 치수·가려진 공간·가구 전체 형상이 자동으로 측량됐다고 표시하지 않는다.

## 2 현재 구현과 12단계의 차이

판정에서 ‘기반 있음’은 해당 기능을 재사용할 수 있다는 뜻이다. 새 12단계 제품 인수를 통과했다는 뜻은 아니다. 아래 코드 경로는 기준 저장소를 기준으로 한다.

| 데모 단계 | 이미 있는 부분 | 추가 구현 또는 검증 | 현재 판정 |
| --- | --- | --- | --- |
| 1 원클릭 실행 | `scripts/twinpulse_launcher.py`, `process_manager.py`가 Web/API/소유 Isaac 프로세스를 실행한다. 패키지 밖 실제 실행 근거가 있다. | 새 채팅 화면을 기본 진입점으로 연결하고 중복 실행·다른 PC 경로·재시작을 검사한다. | 실행 기반 있음 |
| 2 백그라운드 Isaac과 자가 점검 | 시작 단계·오류·진단 화면·명시적 새 세션 재시작이 있다. 실제 엔진 실패·복구를 검사했다. | 준비 체크리스트, 제한된 자동 복구, renderer 상태, 필요한 항목만의 차단, 사용자 설정 보존을 통합한다. | 부분 구현 |
| 3 사진 또는 텍스트 채팅 | `ProductWorkflow.select_input()`은 이미지와 텍스트 또는 텍스트 단독을 받는다. Provider/ToolCatalog/생성·취소·편집 경로가 있다. | 현재 Build/Review/Simulate 폼을 지속 대화·첨부·질문 카드·실제 도구 진행 표시로 연결한다. | 생성 기반 있음, 채팅 제품 미구현 |
| 4 실물 유무 질문 | 일반 상태·입력 검증은 있다. | 답변 전 진행하지 않는 영속 질문 카드와 SIM/REAL 분기, 답변 변경에 따른 후속 상태 무효화가 필요하다. | 미구현 |
| 5 로봇 없는 생성과 Run | 방 형상, Burger 시각 자산, 기존 v1 AGV Physics 실행기가 있다. | v2 방에 구동 가능한 로봇 선택·배치·Physics/경로 실행을 연결해야 한다. 현재 `assert_run_not_site_draft()`는 Run을 거절하고 `build_site_scene()`은 controller를 만들지 않는다. 채팅 조작·우측 화면도 필요하다. | 핵심 연결 미구현 |
| 6 등록 로봇 선택 | Burger 자산·명목 치수·기존 연결 설정·실물 profile 관련 코드가 있다. | 채팅용 RobotRegistry와 SIM 자산/물리 장치/실측 profile의 분리, 선택·가용성 표시가 필요하다. | 부분 구현 |
| 7 병렬 생성과 실물 연동 | 읽기 전용 준비 점검, 수동 controller, 정지시험, 배터리 관측·원본 기록이 있다. | 하나의 채팅 작업으로 병렬 실행·상태 결합, 한 번의 주행 검증·관측 확인 카드, 현재 boot/release에 결속한 연동 상태를 구현한다. | 구성요소 있음, 통합 미구현 |
| 8 Twin 검사 Confirm | 기존 자동 임무 Start/Stop 경로가 있다. | Twin 준비와 로봇 준비를 모두 만족해야 나오는 조사 승인 카드와 조사 전용 작업을 연결한다. | 부분 구현 |
| 9 자율 조사와 위치 보정 | causal 관측, cold start, 위치 추정, 제한된 벽 보정, derived revision, 목표·Isaac 재결속이 있다. 합성 입력과 실제 Isaac 표시를 연결해 검증했다. | 조사 전용 종료 상태, 실물 adapter/배포/profile, 실제 방 불일치 원인 처리·현장 정합이 남는다. 현재 실자료 2건 MODEL_MISMATCH, 1건 INSUFFICIENT_EVIDENCE, 실제 보정 0이다. | 오프라인 경로 있음, 실물 미인수 |
| 10 채팅 목표와 경로 시연 | 점유·빈 공간·unknown 및 footprint 경로 계산, 목표 임무, 궤적·Isaac 표시가 있다. | 자연어 목표 해석, 실행 전 별도 시뮬레이션, 동일 계획·현재 위치·지도 버전에 결속한 실행 Confirm이 필요하다. 현재 완료 보고서의 3D 재생은 이 사전 시연과 다르다. | 부분 구현 |
| 11 실물 실행과 5초 요약 | 로컬 guard, 공통 mission worker, 관측·명령 로그, Stop/Force STOP, active Twin 표시 경로가 있다. | 기본 제품의 qualified live adapter 등록·인수, 채팅 실행 연결, 시간별 요약·즉시 경보·상태판을 묶어야 한다. | 부분 구현, 기본 실물 임무 잠금 |
| 12 왕복 반복 임무 | 수동 until-stop 세션과 저장 revisit 검사가 있다. | A↔B TaskLoop, 다리별 재계획·배터리/진행 정체 감시·장기 로그·재시작 정책이 필요하다. 수동 무기한 연결이나 기록 재방문은 자율 왕복이 아니다. | 미구현 |

### 기존 검증을 사용할 수 있는 범위

- `artifacts/packaged-runtime-20261005-v279-r6/verification.json`: `PACKAGED_WEB_API_ISAAC_OFFLINE_PASS`. 같은 427파일 패키지로 App/core 70검사와 실제 Web/API/Isaac 정상·저장 실패·기하 오류·시작 복구를 검사했다.
- 정상 경로는 출력에 반응하는 **합성 관측**으로 조사→벽 보정→도착→저장 3D를 연결했다. 당시 Isaac timeline은 정지 상태의 표시 검증이므로 새 데모 5·10의 Physics 주행 증거로 재사용하지 않는다.
- Web 255, TypeScript/build, 관련 Python 16검사 기록은 기존 코드의 기준이다. 새 채팅·viewer·loop의 인수 근거가 아니다.
- target binary는 `NOT_BUILT`, clean install과 physical validation은 `NOT_RUN`, whole offline/physical readiness는 false다. 목표 ROS/C++ 빌드 환경, 실측 profile, 새 release 등록과 실제 방 정합은 로봇 전원만 켠다고 없어지지 않는다.
- 이번 계획 작성에서는 코드·기록·공식 문서를 읽었다. 제품 회귀나 실물시험을 새로 수행했다고 주장하지 않는다.

## 3 사용자 화면과 정상 흐름

기본 화면은 왼쪽 대화, 오른쪽 3D와 상태판으로 구성한다. 로봇 점검·수동 조작·개발 패널은 Advanced tools로 이동한다. 일반 사용자가 그 패널을 번갈아 찾아다녀야 하면 이 계획의 완료가 아니다.

| 화면 영역 | 반드시 보여줄 내용 | 동작 규칙 |
| --- | --- | --- |
| 왼쪽 대화 | 사용자 메시지·사진, 답변, 현재 질문/선택, 도구 진행, 완료·오류 카드 | 현재 필요한 다음 행동 하나를 명확히 표시한다. 지난 카드에는 Completed/Expired 등 결과를 남긴다. |
| 하단 입력창 | 여러 줄 텍스트, 첨부, 전송, 생성 취소 | 첨부 실패·LLM 실패를 구분한다. 입력창 포커스에서 WASD가 로봇으로 전달되지 않는다. |
| 오른쪽 상단 | SIM/REAL, 선택 로봇, 연결 상태, 배터리 추정과 시각, 현재 작업·다음 작업 | 과거 관측을 실시간 상태처럼 표시하지 않는다. battery unknown은 0%가 아니다. |
| 오른쪽 3D | 생성 중 형상, 경로 시연, 현재 실측 위치·scan·목표, 화면 접기/펼치기 | 접기는 표시 구독만 줄인다. 임무 취소·새 연결·새 생성을 발생시키지 않는다. |
| 항상 접근 가능한 정지 영역 | Stop after current command, Force STOP | 채팅 응답·LLM·5초 요약·3D 로딩과 독립적으로 작동한다. 현재 연결에서 정지 확인을 받았는지 표시한다. |

대화 흐름은 다음과 같다.

1. App 실행 → 준비 상태가 표시되는 동안 입력 가능 → 사진/텍스트 전송.
2. `Do you have a physical robot?` → `Simulation only` 또는 `Use my robot`. 답변 전 로봇 접속·장면 실행을 시작하지 않는다.
3. SIM은 검증된 자산 중 로봇을 선택하고 생성한다. REAL은 `TurtleBot3 Burger` 선택 후 장면 생성과 읽기 전용 접속 점검을 병렬로 진행한다.
4. REAL의 `Verify drive once`는 필요한 준비 항목과 실제 짧은 이동 범위를 함께 보여준다. 기계적인 준비·기록은 내부에서 수행하고, 끝나면 `It moved normally` / `There was a problem`을 묻는다. 실패를 사람의 확인으로 PASS로 바꾸지 않는다.
5. REAL의 장면과 연동이 준비되면 `Start Twin inspection` / `Not now`가 나온다. 조사 종료까지 도구 카드가 단계와 중단 사유를 보여준다.
6. “현재 위치에서 책상 앞으로 가는 경로를 보여줘” → 목표 해석 → Twin 경로 시연 → `Drive this route` / `Change goal` / `Cancel`.
7. 실물 주행 중 5초 요약과 즉시 경보 → 도착 → `Repeat between start and goal` / `Finish`.
8. 반복 선택 시 B→A→B를 반복하며 우측 작업에 방향·횟수·상태를 표시한다. Stop/보호 정지 후 자동 재개하지 않는다.

준비 중에는 단계명, 경과 시간, 마지막 진전 시각을 표시한다. 정확한 진행량이 없는 작업에 가짜 백분율을 쓰지 않는다. 로봇 부팅의 2–3분은 참고 안내일 뿐, 실제 SSH·보드 준비를 확인하기 전 연결 완료라고 쓰지 않는다.

### 3A 화면 구조와 시각 기준

여기서 ‘ChatGPT와 동일한 형태’는 **대화가 주 화면이고, 아래 입력창에서 요청하며, assistant 메시지 안에서 질문에 답하고 결과를 이어 보는 사용 방식**을 뜻한다. 단순히 기존 점검 폼 옆에 채팅창을 붙이는 구현은 불합격이다. 다음은 이번 구현용 구체적인 디자인 기준안이며 특정 시점 ChatGPT의 픽셀·브랜드 자산 복제를 뜻하지 않는다.

| 영역 | 배치 및 외형 | 상세 동작 |
| --- | --- | --- |
| 상단 앱 바 | 높이 약 56px, TwinPulse·현재 프로젝트·준비 상태 한 줄 | 상태 클릭 시 체크리스트 확장. 긴 주의사항·과거 실패 전문을 상단에 상시 펼치지 않는다. |
| 프로젝트 내비게이션 | 기본 접힘, 펼치면 약 240px의 프로젝트/대화 목록 | 새 프로젝트·저장 대화 재열기. 현재 임무가 있을 때 무단 전환 금지. 설정과 Advanced tools는 여기로 모은다. |
| 대화 영역 | 본문 약 16px, 줄높이 1.5, 메시지 최대 폭 약 760px | 사용자 메시지는 오른쪽 중립색 말풍선, assistant는 왼쪽의 읽기 쉬운 본문. 시스템 로그 박스가 대화 전체를 대체하지 않는다. |
| 질문 카드 | assistant 질문 바로 아래 선택 버튼, 짧은 설명 1–2줄 | 중요한 선택을 화면 밖의 별도 Connection Setup에서 하게 만들지 않는다. 현재 질문에는 Waiting for your choice를 표시한다. |
| 입력창 | 대화 영역 하단 고정, 둥근 테두리, 내용에 따라 약 56–160px 확장 | 첨부·텍스트·전송/응답 중단. 내부 스크롤로 확장 한계를 처리하며 메시지나 질문 버튼을 가리지 않는다. |
| 우측 Twin | 데스크톱에서는 분할 영역, 접기 버튼·뷰어·상태판 | 사용 가능한 본문 폭이 1000px 이상이면 대화/Twin 약 55:45, 각 최소 약 480/400px. divider로 조절하되 가독성을 보존한다. |
| 좁은 화면 | 두 좁은 열을 강제로 유지하지 않음 | Chat/Twin 전환 또는 접이 패널. 상태 요약과 Stop은 어느 화면에서도 접근 가능하고, 화면 전환으로 작업은 다시 시작하지 않는다. |

기본 외형은 밝은 중립 배경·진한 본문·얇은 경계선·절제된 한 가지 강조색으로 한다. 실제 Stop/위험은 빨강, 주의는 황색, 정상은 텍스트+상태 아이콘으로 구분한다. 기존의 커다란 검은 카드와 장문 주의문을 기본 화면에 그대로 옮기지 않는다. 선택 버튼의 누를 수 있는 영역은 최소 44px 높이, 일반 본문 대비는 최소 4.5:1을 구현 목표로 삼는다. 색만으로 상태를 전달하지 않고 키보드 포커스를 표시한다.

데스크톱의 기본 구조는 다음과 같다. 이 배치 예시는 실제 완료 화면이나 현재 구현 상태가 아니다.

```text
TwinPulse   My room                       Preparing / Ready    Settings
┌─────────────────────────────┬────────────────────────────────┐
│ User: [photo] My room ...    │ Burger · Connected · ~71%       │
│                             │ Tasks: Building Twin / Checking │
│ Assistant: Do you have      │                                │
│ a physical robot?           │       Live Isaac 3D             │
│ [Simulation only]           │       [Hide Twin]               │
│ [Use my robot]              │                                │
│                             │                                │
│ [Attach] Message TwinPulse ↑│ [Stop] [Force STOP]              │
└─────────────────────────────┴────────────────────────────────┘
```

우측 패널을 닫아도 실물 Stop/Force STOP과 상태 요약은 앱 바 등의 접근 가능한 위치에 남긴다.

### 3B 대화로 이어지는 메시지 규칙

이 절의 구현 설명은 한국어이며, 아래 인용된 제품 문구는 영어다.

1. 첫 화면은 짧은 `Describe a space or upload a photo to build your Twin.`와 입력창이다. 이전 프로젝트가 있으면 이전 대화는 읽을 수 있지만 예전 임무를 자동 실행하지 않는다. 최초 작업 모드는 New environment이고 기존 프로젝트에서는 명시된 Add/Change 의도를 보존한다.
2. 전송한 텍스트·첨부가 사용자 메시지에 남고, 서버 접수 전에는 Sending, 접수 실패면 Not sent와 재전송을 표시한다. 입력을 먼저 지워 유실시키지 않는다. 네트워크 재시도는 같은 client message ID를 사용한다.
3. assistant 응답과 질문 카드가 시간순으로 이어진다. 질문 선택을 서버가 수락하면 사용자 답변도 대화에 한 번만 남긴다. 클릭만 했으나 아직 수락되지 않은 답변은 Sending your choice로 구분한다.
4. 다음 질문·도구 진행·완료 카드는 실제 상태 전환에 따라 자동으로 나타난다. 정상 경로에서 Refresh를 눌러야 다음 버튼이 나타나는 구조는 금지한다.
5. 서버가 제공하는 문서화된 질문 객체를 React 카드로 그린다. LLM 텍스트에서 임의 HTML이나 문자열 Confirm을 찾아 실행 버튼으로 만드는 방식은 금지한다. 부분 스트리밍 JSON은 실행 권한이 아니다.
6. 이전 메시지를 읽고 있을 때 새 진행 이벤트가 도착해도 스크롤을 강제로 아래로 당기지 않는다. 맨 아래 근처에서는 자동으로 따라가고, 그렇지 않으면 New updates 버튼을 띄운다. 입력·버튼 클릭 후 포커스가 viewer로 이동하지 않는다.
7. 기본 메시지는 짧은 상황 설명과 필요한 다음 행동을 먼저 쓴다. 오류 코드·hash·배포 상세·원본 로그는 Details에 넣되, 필요한 사용자의 조치와 차단 이유는 접힌 영역에 숨기지 않는다.

### 3C 입력창과 응답 스트리밍

- Enter는 전송, Shift+Enter는 줄바꿈으로 한다. IME 조합 중 Enter는 전송하지 않는다. 빈 메시지는 전송하지 않되 유효한 사진만 첨부된 요청은 기존 입력 계약에 따라 허용한다.
- 파일 선택·드래그앤드롭·클립보드 이미지 붙여넣기를 제공한다. 첨부에는 썸네일, 파일명, 제거 버튼, 검증/업로드 상태가 보인다. 첫 구현은 현재 입력 계약에 맞춰 메시지당 이미지 1개를 지원하고, 두 번째 이미지는 조용히 버리거나 바꾸지 말고 교체 여부를 표시한다. 여러 이미지 기능을 구현하지 않고 가능하다고 표시하지 않는다.
- PNG/JPEG/WebP·10MiB 제한 등 실제 backend 제한과 화면 안내를 일치시킨다. 실패해도 텍스트 초안과 원래 첨부 선택을 보존한다. 파일 업로드가 성공하지 않은 요청을 장면 생성으로 넘기지 않는다.
- 사용자가 전송하면 100ms 안에 버튼/메시지의 로컬 접수 반응을 보이는 것을 UI 목표로 한다. 이는 서버 처리 완료나 로봇 응답을 보장하는 시간이 아니다. 기다리는 동안 실제 상태에 따라 Waiting for response / Generating / Running tools를 보여준다.
- provider가 text delta를 제공하면 같은 assistant 메시지에 점진적으로 표시한다. 구조화된 단일 결과만 주는 기존 provider는 가짜 타이핑을 재생하지 말고 실제 도구 진행을 표시한 뒤 최종 설명을 게시한다. 두 경로의 차이를 capability로 관리한다.
- 응답 생성 중 입력창의 전송 위치에는 Stop response가 표시된다. 이 버튼은 해당 응답/생성 job을 취소하며, 이미 시작된 실물 임무를 멈춘다는 뜻이 아니다. 로봇 Stop은 별도의 항상 보이는 버튼이다. 사용자 텍스트의 명확한 정지 의도도 안전 경로로 전달하되 일반 질문을 정지 명령으로 오인하지 않는다.
- 응답 취소·중단은 부분 텍스트를 남기고 Stopped 또는 Response interrupted를 표시한다. 부분 tool call/card는 실행하지 않는다. 응답 재생성은 설명만 재생성하고 이미 끝난 scene 생성·물리 명령을 다시 호출하지 않는다.
- 재연결은 인증된 event cursor로 누락을 복구한다. 인증 헤더를 사용할 수 있는 fetch stream 등의 기존 서버 호환 방식을 사용하고, fallback polling도 같은 이벤트 ID로 중복을 제거한다. 키를 URL에 넣거나 새 모델·유료 서비스·설치를 필수로 추가하지 않는다.

### 3D 질문과 실행 버튼의 전체 목록

질문과 작업 선택은 아래처럼 **채팅 안에 표시**한다. 버튼을 누를 때 다시 동일 질문의 Submit/Confirm을 중복 요구하지 않는다. 물리 작업 버튼 자체에는 어떤 동작을 시작하는지 명시한다. 브라우저 확인창과 별도 체크박스를 정상 경로에 추가하지 않는다.

| 카드 | 표시 시점과 문구 예시 | 선택 또는 실행 버튼 | 클릭 뒤 반드시 보이는 결과 |
| --- | --- | --- | --- |
| Q1 실물 유무 | 입력 접수 후 `Do you have a physical robot?` | Simulation only / Use my robot | 선택 답변 메시지, 카드 Answered, 해당 분기 진행. 미선택은 무기한 대기 가능하며 자동 선택하지 않음 |
| Q2 로봇 선택 | Q1 REAL 후 `Choose your robot.` | TurtleBot3 Burger | Selected: TurtleBot3 Burger 후 scene 생성과 read-only connection 두 진행 표시. 현재 목록이 1개라도 선택을 기다림 |
| Q3 한 번의 주행 검증 | 연결 관측 뒤 `Verify your robot with one short drive.` | Verify drive once / Not now | 승인 범위를 짧게 표시. 내부 준비 중 Preparing verification, 실제 실행 중 Verifying drive, 최종 정지 확인까지 완료로 표시하지 않음 |
| Q4 관측 확인 | Q3의 제한 이동과 정지 결과가 수집된 뒤 `Did it move and stop normally?` | It moved normally / There was a problem | 수락된 답변+기계 판정. 둘 다 유효해야 Drive verified. 자동 검사 실패는 문제 카드로 유지하고 사람 답변으로 해제하지 않음 |
| Q5 Twin 조사 | scene·robot·sensor/profile 준비가 모두 충족되면 `The Twin and robot are ready. Start inspection?` | Start Twin inspection / Not now | Inspecting Twin과 실제 단계·3D·정지 버튼. 승인 전 자동 이동 없음 |
| Q6 SIM Run | SIM scene와 구동 capability가 준비되면 `Your Twin is ready to run.` | Run simulation | Running simulation. 사용자 목표가 없으면 planner가 만든 제한된 SIM 시연 목표·경로를 먼저 카드/뷰어에 표시해 Run의 의미를 설명함 |
| Q7 목표 확인과 실물 실행 | 자연어 목표의 경로 시연이 끝난 뒤 `Preview complete. Drive to the desk?` | Drive this route / Change goal / Cancel | 실제 실행 시작을 서버가 수락한 뒤 Driving to desk. 승인 전에는 Preview only이고 실물 출력 0 |
| Q8 왕복 반복 | 실제 목표 도착과 정지 상태가 확인되면 `Arrived. Repeat between the start and this goal?` | Repeat between start and goal / Finish | Loop active · B → A · Trip 1 등 실제 task 표시. 새 물리 segment마다 재승인 요구하지 않음 |
| Q9 정보 보충 | 객체가 둘 이상이거나 필요한 치수·입력이 없을 때만 질문 | 실제 후보 선택 또는 짧은 값 입력 | 한 번 답하면 관련 revision 동안 재사용. 사용자에게 정상 입력을 내부 ID로 다시 작성하게 하지 않음 |

Q3의 내부 준비에 reviewed source 전송·모터 OFF가 필요하면 누르기 전에 요약한다. 승인되지 않은 설치·권한·profile 근거가 필요할 때는 Q3을 실행 가능하게 보이게 하지 않고 그 항목만 Needs action으로 표시한다. 유효한 준비/qualification이 있는 경우 불필요한 재설치·정지시험·현장 확인을 반복하지 않는다.

Q5를 기다리는 병렬 단계에서는 `Twin: Building`과 `Robot: Ready`를 각각 보여준다. 아직 못 누르는 다음 행동은 한 줄 `Inspection will be available when the Twin is ready.`로 설명한다. 사용할 수 없는 이후 단계 버튼을 여러 개 늘어놓지 않는다. SIM의 후속 자연어 목표는 실제 로봇 실행 Confirm 없이 SIM에서만 수행하며 REAL로 조용히 전환하지 않는다.

### 3E 버튼 상태와 실패 후 동작

서버 실행 상태와 UI 표시 상태를 분리한다. 특히 `accepted` 응답은 작업 접수이지 성공도 실패도 아니다.

| 상태 | 사용자가 보는 표현 | 허용 동작 및 전환 |
| --- | --- | --- |
| Waiting | 질문과 활성 선택 버튼 | 선택을 기다림. 물리 승인에 미리 체크된 기본값을 사용하지 않음 |
| Blocked | 필요한 다음 행동과 이유, 예: Waiting for current scan | 해당 실행 불가. 조건이 바뀌면 자동 갱신. 무의미한 회색 버튼만 표시하지 않음 |
| Submitting | 누른 선택 강조, Sending your choice 또는 Starting… | 같은 카드의 중복 클릭 잠금. 실제 실행됐다는 문구는 아직 쓰지 않음 |
| Accepted 또는 Running | Job accepted / Checking / Driving 등 실제 단계 | 카드의 실행 버튼은 상태 표시로 전환. 취소/Stop은 해당 작업 수명에 맞게 제공 |
| Completed 또는 Answered | 선택 결과와 체크, 완료 시각, 다음 메시지 | 과거 버튼은 재실행하지 않음. 필요한 후속 카드가 자동 등장 |
| Failed | 짧은 원인·가능한 다음 행동·Details | 실패한 안전한 단계만 Retry 제공. 완료된 다른 단계는 유지 |
| Delivery unknown | Could not confirm whether the request was accepted. Checking status… | 같은 operation ID로 조회. 물리 작업 자동 재전송·새 ID 재실행 금지 |
| Cancelled 또는 Expired | Cancelled / This choice is no longer valid와 이유 | 이전 버튼 잠금. 현재 조건에서 생성된 새 카드로만 진행 |

실물 요청의 응답 유실은 ‘실행하지 않았다’는 증거가 아니다. 저장된 operation ID와 로봇/서버 기록을 조회해 결과를 확정하기 전 Retry drive를 제공하지 않는다. 선택 결과는 backend 판정을 따른다. optimistic UI로 연결·정합·도착 성공을 만들어내지 않는다.

### 3F 기다리는 동안 들어오는 다른 요청

- 현재 질문에 대한 설명·배터리·진행 상황 질문은 답하고 기존 질문 카드를 유지한다. 한 번 더 로봇 유무를 묻지 않는다.
- Q1/Q2의 명확한 텍스트 답변은 선택지로 해석할 수 있지만, 실제 물리 실행 승인은 Q3/Q5/Q7/Q8의 명시적 버튼으로 한다. 예전 메시지의 ‘그래’나 사진 속 문장은 승인이 아니다.
- 경로 Confirm 대기 중 새 목표가 들어오면 이전 카드·plan digest를 무효화하고 새 preview를 만든다. 이전 카드를 뒤로 스크롤해 눌러도 주행하지 않는다.
- 장면 생성 중 추가 편집은 현재 job을 몰래 덮어쓰지 않는다. 요청을 Pending edit로 보관하고 현재 생성의 종료/취소가 확정된 뒤 적용한다. 프로젝트 전환·파괴적 재생성은 기존 데이터를 보존하고 범위가 불명확할 때만 짧게 묻는다.
- 실물 주행 중 목표/장면 변경은 다음 task 후보로 보관하고 현재 임무의 명시적 종료 상태를 거친다. 채팅 수신 때문에 현재 목표·frame을 조용히 교체하지 않는다. Stop·Force STOP은 pending queue보다 항상 우선한다.
- 조용한 대기/질문 중에도 text draft와 선택 상태를 보존한다. 재연결 성공으로 물리 임무를 자동 재개하지 않는다.

### 3G 진행 표시와 오류를 이해할 수 있게 만드는 규칙

도구 진행은 한 assistant 메시지 아래의 접을 수 있는 활동 목록으로 표시한다. 예: Reading your request → Choosing a robot → Building the room → Connecting to Burger. 병렬 작업은 실제 병렬 상태로 보이고 가짜 순서·가짜 퍼센트를 만들지 않는다. 내부 ToolCatalog 이름은 Details에서 볼 수 있고 기본 화면에는 무엇을 하는지 이해할 수 있는 이름을 쓴다.

원문 5·7의 생성 중 3D는 실제 준비된 stage preview가 있을 때 표시한다. 부분 생성 장면은 Draft preview로 표시하고 현재 주행 지도·실물 기준으로 사용하지 않는다. 아직 stage가 없으면 Building your Twin placeholder와 진행 목록을 보여준다. 기존 완성 화면을 새 생성 결과처럼 표시하거나 모든 처리가 끝나기 전까지 아무 표시도 없는 구현은 불합격이다.

5초 상태 요약은 채팅의 Live mission card를 갱신하고 Last updated 시각을 보여준다. 도착·장애물 정지·연결 상실 등 중요한 변화는 별도 이력 메시지로 남긴다. 연결 상실 시 오래된 배터리/pose는 Last observed 또는 Unknown으로 바뀌고 이유가 표시된다. 연속 성공 카드 수백 개로 채팅을 채우지 않는다.

실패는 해당 채팅 카드에 계속 남고, 사용자가 보고 있지 않은 영역의 중요한 실패에는 오류 팝업/배너를 함께 표시한다. 같은 error ID의 반복 팝업은 만들지 않는다. 팝업을 닫는 것은 오류 해결·작업 재개가 아니다. 상태 바에는 원인, 막힌 기능, 가능한 다음 행동을 짧게 남기고 Details에는 단계/code/원본 기록을 제공한다. 정상 경로의 다음 버튼을 과거 오류 전문 아래로 밀어내지 않는다.

### 3H 원문을 화면에서 재현하는 예시

다음 문구는 UI 문체·전환의 구현 예시이며 실제 로봇·연결·배터리 결과를 미리 확정한 것이 아니다. 수치는 반드시 runtime 관측으로 채운다.

**SIM 예시**

1. User: 사진 첨부와 `Create a digital twin of this room.`
2. Assistant: `Do you have a physical robot?`와 Q1 버튼.
3. User가 Simulation only 선택 → 선택 답변 표시 → Assistant: `I'll use the closest supported wheeled robot and build a Twin from your photo. Dimensions are approximate.`
4. 실제 도구 활동과 우측 Draft preview → 생성 완료 → `Your Twin is ready. Run the preview route, or tell me where to go.`와 Run simulation.
5. Run 클릭 → 같은 카드가 Starting…→Running으로 전환, 우측 로봇 이동 → 이후 `Go to the desk` 입력으로 새로운 SIM 목표 실행. 숨겨진 별도 Run 탭으로 이동하지 않음.

**REAL 예시**

1. Q1 Use my robot → Q2 TurtleBot3 Burger → `I'm building your Twin and checking the robot connection.`
2. `Twin: Building · Robot: Ready`와 Q3 → 클릭 후 Preparing verification→Verifying drive→Stopping/Checking stop.
3. Q4 `Did it move and stop normally?` → 유효한 기계 결과와 사용자 정상 확인 뒤 `Drive verified`.
4. 두 준비 완료 → Q5 Start Twin inspection → Inspecting→Matching observations→Updating Twin→Inspection complete 또는 정확한 거절 사유.
5. User: `Show a route from here to the desk.` → 목표·계획·Twin 시연 → Q7 Drive this route → Running과 5초 Live mission card.
6. 도착 → Q8 Repeat between start and goal → 우측 `Loop active · Returning to start` → Stop → Stopping→Stopped. Stop을 누르기 전 task가 60초마다 끝나거나 새 연결을 요구하지 않음. 보호 조건 발생 시에는 이유와 함께 정지.

### 3I 사용자가 다시 지적하게 만들면 안 되는 구현

- 질문을 텍스트로만 써 놓고 답변은 별도 설정 화면에서 선택하게 만드는 것.
- 클릭 뒤 초기 버튼으로 돌아와 선택·진행 여부가 사라지는 것.
- 준비 전 버튼부터 활성화하거나, 이유 없이 회색으로 만드는 것.
- 정상 동작에서도 PC 점검·연결·Motor OFF·정지시험·연결을 사용자가 매번 순서대로 찾아 누르게 하는 것.
- 사용자가 매 명령마다 현장 체크박스를 재선택하도록 만드는 것.
- SIM preview·과거 raw 재생·실제 현재 센서·사진 추정치를 같은 Live 표현으로 표시하는 것.
- backend 작업 완료인데 Refresh 전에는 다음 버튼이 나오지 않는 것.
- ‘Stop response’, 일반 Stop, Force STOP의 의미를 혼합하는 것.
- 엔진·provider·로봇 오류에도 spinner만 무기한 보이거나, 이전 화면을 정상 상태처럼 유지하는 것.
- 기존 UI 폼을 그대로 두고 메시지 컴포넌트만 추가한 후 ‘ChatGPT형 UI 완료’라고 하는 것.

## 4 공통 세션과 서비스 계약

아래 이름은 새로 구현할 **제안 계약**이다. 기존 API인 것처럼 사용하거나 이름만 추가하고 완료로 기록하지 않는다. 기존 ProductWorkflow, broker, automatic mission, controller를 호출하는 얇은 orchestration 계층을 둔다.

### 대화 세션과 승인 카드

- `DemoSession`: project ID, input/scene/map revision, SIM/REAL, 선택 로봇, generation/job/task ID, event cursor, 진행 상태, 연결 세대, 사용자가 답한 질문을 관리한다.
- `ConversationEvent`: event ID/순서/시각/출처, message/tool progress/question/decision/error/telemetry summary. 재접속은 cursor 이후를 재수신하며 중복 메시지·중복 명령을 만들지 않는다.
- `ActionCard`: session·질문·명령의 ID, 현재 revision, expected state, 만료, 선택지, 처리 결과를 가진다. API에서 같은 버튼의 재전송을 멱등 처리하고 다른 탭·오래된 카드·이중 클릭은 실행하지 않는다. 3D절의 Q1–Q9와 3E절 상태표를 동일 contract로 구현한다.
- `RobotBinding`: 등록 장치, boot/release/profile, 마지막 관측, 기계적 qualification, 사용자 관측 확인을 서로 분리한다. 연결됨·검증됨·위치 확보·임무 가능은 다른 상태다.
- `MissionPlan`: 시작 위치와 그 유효 시각, 기준 frame/map/scene/footprint revision, 목표 ID, 경유점, 경로 비용·제약, 시연 결과, 계획 digest를 저장한다. 실행 Confirm은 이 계획을 가리킨다.
- `Task`: SIM run/survey/go-to/loop의 수명과 child mission, 예산, Stop 상태, 완료·실패 원인, 원본 로그 위치를 관리한다. 브라우저 컴포넌트가 작업 수명을 소유하지 않는다.

하나의 거대한 READY boolean을 피하고 engine/scene/robot/sensors/localization/task의 준비를 별도로 저장한다. 병렬 생성 중 로봇이 끊겨도 이미 완성된 장면을 지우지 않는다. 프로젝트 변경·장면 편집은 관련 카드와 계획을 무효화한다. 현재 주행 중이면 먼저 작업 종료 상태를 확인하고 전환한다.

재시작 시 대화·지도·보고서는 복원하지만 live pose, 구동 승인, 과거 heartbeat와 실행 중 물리 임무는 복원하지 않는다. UI 새로고침은 진행 상태 조회이지 재실행 요청이 아니다. 여러 창 중 물리 제어 소유자는 하나다. 창 전체 종료·제어 heartbeat 상실과 우측 패널 접기를 구분한다. 소유자 상실 시 기존 보호 정지가 적용되고 자동 재주행하지 않는다.

### 화면에 전달할 최소 데이터 계약

다음 필드는 구현 계약의 최소 요구이며, 기존 저장 schema를 무단 변경하는 것이 아니다. `schema_version`을 가진 새 DTO로 기존 service 결과를 감싼다.

- 메시지: `message_id`, `session_id`, `role`, `content`, `attachments`, `status`, `created_at`, `reply_to`, `operation_id`. 첨부는 검증된 식별자만 받고 임의 서버 경로를 받지 않는다.
- 질문/작업 카드: `card_id`, `kind`, `question`, `choices[{id,label,description,enabled,disabled_reason}]`, `state`, `selected_choice_id`, `expected_session_revision`, `related_plan_digest`, `expires_at`, `operation_id`. `expires_at`은 종류별 정책이며 실물 유무 질문에는 불필요한 시간제한을 걸지 않는다. 실행 카드는 현재 조건 변경에 따라 무효화한다.
- 선택 제출: `card_id`, `choice_id`, `expected_session_revision`, `client_request_id`. 사용자 인증·소유권과 유효 카드·실제 readiness는 서버에서 검사한다. frontend의 enabled 값은 권한 근거가 아니다.
- 작업 진행: `operation_id`, `phase`, `status`, `started_at`, `last_progress_at`, `summary`, `blockers`, `can_cancel`, `error_id`. 병렬 scene/robot은 별도 operation으로 연결하고 한쪽 결과를 다른 쪽 pending으로 덮어쓰지 않는다.
- 이벤트: `event_id`, `session_id`, `sequence`, `type`, `message_id 또는 operation_id`, `timestamp`, `payload`. 종류는 메시지 접수·text delta·최종 답변·카드 생성/갱신·작업 진행/종료·오류·telemetry summary를 구별한다. event gap은 snapshot 재동기화로 복구하고 재실행하지 않는다.
- 상태판: 관측 출처·SIM/REAL·sample 시각·age·연결 상태·배터리 값/추정 여부·현재 task·다음 task·stop 요청/확인 상태. current라는 상태에는 freshness 근거가 필요하다.

질문 문구·도구 설명은 LLM이 제안할 수 있지만 실행 카드 생성·선택지 ID·활성 조건·실물 승인 범위는 application policy가 결정한다. 임의 웹 문장·이미지 OCR·생성 텍스트가 실행 카드로 승격되지 않게 한다. API 거절은 채팅의 해당 카드에 반영하고 전체 대화를 지우지 않는다.

### LLM과 도구 실행의 경계

기존 provider와 ToolCatalog를 확장한다. LLM은 입력 해석, 후보 설명, 고수준 도구 선택을 담당하고 검증된 dispatcher만 실제 서비스를 호출한다. 장면·사진·이전 메시지의 문장을 실행 권한으로 해석하지 않는다. 임의 Python/shell, 임의 URL/파일 경로, LLM이 만든 모터·질량·안전 수치는 실행하지 않는다.

지원 의도는 최소 create/add/change environment, choose robot, simulate, inspect Twin, preview goal, execute confirmed plan, repeat, stop, explain status이다. 기존 New/Add/Change와 가구 추가·배치·회전·원본 보존을 유지한다. 불명확한 목표는 짧은 선택 카드로 해결하며, 정지 요청은 LLM 성공을 기다리지 않는 별도 경로도 제공한다.

도구 설명은 실제 시작/완료/실패 이벤트에서 생성한다. 내부 추론을 꾸며 보여주거나 실행하지 않은 검색·도구를 실행했다고 쓰지 않는다. 대화 생성 중 타임아웃·취소·인증 오류에도 이미 안전하게 끝난 단계는 재호출하지 않는다. 의존하지 않는 점검은 계속하고 이동만 필요한 조건에 따라 차단한다.

## 5 기능별 구현 기준

### 실행 준비와 자동 복구

기존 launcher/process manager를 확장해 Web부터 열고 Isaac은 소유한 백그라운드 프로세스로 시작한다. 체크 결과는 `ready / checking / repairing / needs_action / failed / not_required`와 근거·조치·시각을 갖는다.

필수 항목은 실행 파일·지원 버전, extension/asset manifest, Web build, 프로젝트 쓰기 공간·디스크, 엔진 heartbeat/capability, viewer, 선택된 provider 설정, REAL 분기의 장치 접속·release/profile·센서 준비다. SIM 분기에 SSH가 없는 것을 전체 실패로 표시하지 않는다. 키는 설정 여부만 검사하고 본문·헤더를 출력하지 않는다.

자동 복구는 검토된 allowlist로 제한한다. 소유 임시 경로 재생성, 패키지에 이미 있는 검증 자산의 재배치, 검토된 파생 캐시 재생성, 이 launcher가 소유한 실패 프로세스의 제한된 재시작을 대상으로 한다. 입력·원본 프로젝트·사용자 설정은 보존한다. 항목별 시도 수와 전체 예산을 정하고 같은 실패를 반복하지 않는다.

ROS/WSL/드라이버/Isaac 설치, 방화벽·호스트 키·인증 변경, 외부 자산 다운로드, 비용 발생은 자동 복구 대상이 아니다. 필요한 경우 정확한 누락·이유·실행 불가능한 기능을 체크리스트로 제시한다. ‘연결 실패’ 하나로 네트워크·SSH 인증·remote 프로그램 오류를 합치지 않는다.

### 우측 실시간 3D

현재 설치는 `C:\isaacsim\VERSION` 기준 `6.0.1-rc.7+release.42383.32955d8d.gl`이다. 로컬에 livestream app/core/webrtc extension과 streaming kit가 있지만, 이것이 웹 삽입 동작을 보증하지는 않는다. 현재 Web package에는 React 외 runtime viewer dependency가 없고, 기존 viewport capture는 지속 viewer가 아니다.

권장 첫 구현은 **현재 Windows에서 기존 Isaac 렌더를 서버가 전달하는 인증된 viewport**다. 고정 스크린샷을 반복 표시하는 것이 아니라 stage revision/frame ID/capture 시각을 가진 새 프레임을 제공하고, 승인된 camera orbit/pan/zoom 명령으로 실제 Isaac 카메라를 조작한다. 최초 구현 실험에서 headless 렌더·움직이는 로봇·카메라 반응·부하를 측정한다. 프레임은 bounded latest-only로 전달하며 매 프레임 디스크 저장을 강제하지 않는다. 사용자 원본 로깅·제어 채널과 분리한다.

이 방식의 제안 목표는 화면 표시 5 FPS 이상, 로컬 표시 지연 p95 500ms 이내다. 이는 **개발 목표이지 실측 결과나 로봇 제어 허용 지연이 아니다**. 못 맞추면 degraded를 표시하고 동일 PC의 WebRTC 직접 통합을 대안으로 비교한다. 느린 정지 사진을 완성된 실시간 3D로 인수하지 않는다. 새 SDK/설치가 필요하면 먼저 범위·권한을 확인한다.

NVIDIA 공식 문서는 native streaming과 browser viewer를 구분하며, Docker Compose browser viewer는 Ubuntu/DGX Spark 대상이고 Windows/WSL은 미지원이라고 명시한다. 따라서 Windows에서 해당 Docker 절차를 그대로 적용하는 계획을 세우지 않는다. streaming endpoint 보안과 GPU 인코딩 요구도 별도 점검한다. [Isaac Sim 6.0.1 Livestream Clients](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/manual_livestream_clients.html)

패널을 접었다 펴도 같은 stage/임무를 유지한다. viewer 손실은 viewer 오류로 표시하고 오래된 화면에 Live 표시를 제거한다. 로봇 current pose/scan이 무효화되면 화면도 즉시 그 사실을 반영한다. 3D 카메라 키보드와 채팅 키보드가 실물 주행으로 전파되지 않아야 한다. 투영된 경로 시연은 별도 ghost/SIM 로봇으로 표시해 실제 위치를 덮어쓰지 않는다. 프레임·카메라 API는 기존 인증·소유권 검사와 크기/빈도 제한을 적용하고 외부 인터페이스에 무인증으로 공개하지 않는다.

### 로봇 없는 시뮬레이션

현재 v1 기본 AGV profile은 약 0.60×0.40m의 별도 자산이다. 이를 Burger의 실측 차체라고 사용하면 안 된다. `RobotAssetCatalog`에 자산 ID, appearance tags, 검증된 구동 방식, wheel joint·footprint·지원 기능, 출처·라이선스를 둔다. LLM은 등록 ID만 고른다. 근접 자산이 없으면 ‘가장 가까운 검증된 차동 구동 모델을 사용한다’고 설명하고 무근거 자산을 다운로드하지 않는다.

v2 room scene과 executable simulation binding을 분리해 기존 직렬화/hash 계약을 깨지 않는다. static room compiler에 동적 로봇 articulation·충돌체·접지·controller·경로 추종기를 연결한다. 기존 `site_draft_review_only`를 무조건 삭제하지 말고 현재 scene/robot capability가 실제로 구동 가능한 경우에만 별도 run을 허용한다.

실제 Isaac physics step과 관측 pose가 진행해야 한다. USD pose 애니메이션만 한 것을 Physics 검증으로 표시하지 않는다. 공식 TurtleBot 예제도 drivable joints와 Differential/Articulation controller를 구분한다. 이 구조를 참고하되 예제 속도·치수를 현재 실물 안전 profile로 복사하지 않는다. [Isaac Sim TurtleBot 구동 예제](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/ros2_tutorials/tutorial_ros2_drive_turtlebot.html)

SIM 실행은 실제 로봇 endpoint와 분리한다. 사진 생성→현재 방 build→현재 robot Run→채팅 목표 변경→정지까지 실제 Web/API/Isaac으로 인수한다. 과거 warehouse Run 성공은 새 방의 Run 성공을 대신하지 않는다.

### 등록 로봇과 한 번의 주행 검증

RobotRegistry는 장치 식별·연결 설정 참조를 제공하고, 검증된 hardware profile은 실장 TF·footprint·driver timing·배포 binary/release와 분리 관리한다. registry 선택이나 파일 존재만으로 실물 임무를 허용하지 않는다.

선택 직후 읽기 전용 연결을 자동 검사한다. scene 생성과 병렬이며 어느 한쪽 오류가 다른 쪽 결과를 삭제하지 않는다. 장치 준비는 내부 state machine으로 진행하고 UI에 PC 점검→같은 연결 점검→다시 같은 점검을 각각 누르게 하지 않는다.

`Verify drive once`는 현장 시험 시 사용자가 누르는 물리 작업 승인이다. 카드에 배터리 전원·관찰·공간·예상 짧은 이동 및 필요한 배포 여부를 간결하게 표시한다. 별도 매명령 체크박스는 추가하지 않는다. reviewed release 준비, 정지 상태 확보, 제한 이동, 명령/관측 기록, 최종 stop 확인을 기존 field suite/controller를 통해 한 번 수행한다. 현재 boot/release/profile의 유효한 qualification은 재사용하되 새 부팅·관련 변경·실패 시 이유를 표시한다.

사용자의 ‘움직였다’ 확인은 관측 보강이다. 자동 정지시험 실패·센서 결손·배포 불일치를 무효화하지 않는다. 수동 구동 연동 준비와 자율 조사 준비를 각각 표시하여 “연결됨인데 조사 버튼이 안 되는” 이유를 명확히 한다. 실패하면 독립적으로 가능한 배터리·센서·raw export 등의 점검은 계속하고, 다음 이동만 중단한다.

### 자율 조사와 사진 Twin 보정

기존 cold-start worker를 조사 전용 task와 goal task가 공통으로 사용하게 한다. 조사 승인만 받았는데 임의 목표까지 주행하는 결합을 없앤다. 조사 task는 최신 odom/TF/scan→로컬 관측지도→사진 구조 정합→보정 후보 검증→새 revision→현재 pose 확보에서 완료한다.

처음 움직일 공간 판단은 미검증 사진 지도가 아닌 로봇의 최신 근거리 관측과 검증된 footprint로 한다. 모르는 영역은 빈 공간이 아니다. 2D LiDAR 높이 아래의 전선·천·낮은 물체와 낙차는 LiDAR만으로 보장할 수 없으므로, 현장 운용 범위와 제한을 상태에 남긴다. 충돌 감점은 방지 기능을 대신하지 않는다.

실제 저장자료의 사진 불일치를 먼저 재현한다. 오차를 scan timing/실장 좌표/부정확한 사진 치수/서로 다른 배치/관측 단면으로 분리하고, 측정 없는 임의 scale·축 반전·threshold 완화로 PASS를 만들지 않는다. 사진의 절대 치수가 부족하면 짧은 치수 질문을 생성 시점에 하거나 근사 visual layer와 sensor map을 분리한다. 모호한 사진 정합은 ‘지도는 생성했지만 사진 모델과 연결은 미확정’으로 보고하며 데모 9 완료로 표시하지 않는다.

기존 bounded wall correction, 독립 held-out, 원본 불변·derived revision·rollback을 재사용한다. LiDAR로 보이지 않는 가구 높이·재질·외형까지 수정하지 않는다. 사진 Twin 변경 또는 로봇 손이동 이후에는 현재 관측으로 다시 위치를 찾고 과거 odom 시작값을 재사용하지 않는다.

### 목표 해석과 경로 시연 및 실행

목표는 장면의 객체 ID와 접근 가능한 목표 영역에 연결한다. ‘책상 앞’의 물체 내부·침대 위·통행 불가 공간을 목표로 보내지 않는다. 같은 이름이 둘 이상이면 선택 카드를 사용한다. 특정 위치의 도달 방향·여유 폭·footprint를 동일 planner가 검사한다.

최적 경로는 **현재 지도와 비용 기준에서 선택된 최저비용 후보**라는 의미로 정의한다. 거리·회전·여유 공간 등의 비용을 명시하며 알 수 없는 환경 전체의 전역 최적을 보장하지 않는다. 시연은 계획 경로와 실제 SIM 관측 궤적을 구분한다.

실물 실행 전 Confirm에는 목표·예상 경로·시작 위치·최신 지도 revision을 담는다. 승인을 기다리는 동안 로봇 손이동·새 장애물·지도 변경이 발생하면 오래된 계획으로 움직이지 않는다. 새 preview가 필요한 변경과 승인된 임무 범위 안에서 가능한 작은 local replan을 계약으로 구분한다. 로봇은 녹화된 wheel command를 맹목 재생하는 것이 아니라 동일 목표/허용 경로 범위에 대해 최신 센서로 추종한다.

5초 보고는 서버 관측을 구조화한 요약으로 우선 구현한다. 매 5초 유료 LLM을 호출하지 않는다. 상태·진행 거리·다음 waypoint·배터리·장애물/정지 원인·관측 시각을 표시하고, 한 메시지의 live 카드 업데이트와 중요한 이력 메시지를 구분해 대화가 과도하게 쌓이지 않게 한다. 센서 손실·Force STOP·저전압 등의 경보는 다음 5초를 기다리지 않는다. LLM이 중단돼도 제어·정지·요약은 유지된다.

### 반복 임무와 종료

루프의 A는 최초 경로 실행 때 확정한 시작 위치, B는 목표 위치다. 사용자가 B 도착 후 반복을 선택하면 B→A→B를 반복한다. A/B는 단순 odom 좌표가 아니라 유효 지도 frame과 목표 영역에 결속한다. 편집·위치 상실·재부팅으로 무효화되면 자동 재개하지 않는다.

**45초 제한을 지우거나 만료 직전 몰래 갱신하는 것으로 구현하지 않는다.** 상위 지속 TaskLoop가 시작·도착·진행·보호 상태를 관리하고, 아래의 bounded mission이 예산 안에서 검증된 하위 목표를 수행하는 새 계약이 필요하다. 전환은 새 관측·lease·자원 상태와 task 승인을 검사한다. 계획한 하위 목표 완료는 이어갈 수 있지만, watchdog 만료·예산 초과·실패로 끝난 임무를 자동 새 세션으로 되살리지 않는다. 하위 명령의 freshness/segment/정지 기준은 그대로다.

현재 기준은 scan 200ms, input 250ms, segment 50ms, 자율 0.03m/s·0.20rad/s, bounded mission 45초다. 길어진 task의 정책 변경은 새 versioned 계약·회귀·현장 인수로 다루고 기존 수동 0.08 요청이나 예전 60초 세션을 자율 제한 변경 근거로 쓰지 않는다. 긴 왕복이 이 속도·예산으로 불가능하면 planner가 먼저 진단해야 한다.

배터리는 추정 20% 기준과 보드 보호를 유지하고 전압 부하 변동·히스테리시스·시각·unknown 정책을 명시한다. 한계를 넘은 후 새 다리를 시작하지 않으며, 귀환 에너지가 부족한데 무조건 A까지 돌아오게 하지 않는다. 저전압/보호 발생은 안전한 정지 우선이다.

‘모터 토크가 안 걸림’은 torque-enabled boolean으로 판정할 수 없다. 실제 전류/부하/진단값 제공 여부를 먼저 확인한다. 미지원이면 그 사실을 표시하고 명령 대비 encoder·odom·IMU 진행 정체, wheel slip, 장애물 가까움 등을 이용한 별도 stalled/progress 상태를 검증한다. 임계값은 실제 센서 주기·잡음·저속 회전 결과로 정하며 근거 없는 토크 실측값을 만들지 않는다. 실물 바퀴를 강제로 막는 시험은 별도 위험 검토 없이 하지 않는다.

일반 Stop은 다음 명령·다음 다리를 취소하고 현재 이미 발행된 제한 segment 후 정지한다. 현재 다리 전체나 목적지 도착까지 기다리지 않는다. Force STOP은 즉시 정지 요청·Motor OFF 경로를 사용하며 pending Stop 중에도 가능하다. 두 기능 모두 물리 응답·관측을 기록하고 ‘명령 보냄’과 ‘정지 확인’을 구분한다.

## 6 구현 작업 순서

작은 mock 패널을 하나 만들 때마다 사용자에게 다음 지시를 요구하지 않는다. 아래 여섯 묶음 각각을 기존 서비스와 연결한 사용자 흐름 단위로 끝낸다. 코드 단위 검사는 수시로 하되 무거운 전체 runtime 재실행은 묶음 종료와 통합 전후에 집중한다. 설치·유료·실물 권한이 없으면 그 부분만 분리하고 안전한 나머지 구현을 계속한다.

### C1 세션과 채팅 및 실행 준비

대상: `App.tsx`, `api.ts`, App `api.py`, `product_workflow_service.py`, `process_manager.py`, launcher, 기존 provider/ToolCatalog.

새 모듈 제안: `demo_session.py`, `conversation_service.py`, `startup_checks.py`, `ChatWorkspace.tsx`, `MessageList.tsx`, `ChatComposer.tsx`, `ActionCard.tsx`, `ToolProgressCard.tsx`, `RuntimeChecklist.tsx`. `ActionCard` 하나의 공통 상태 contract를 질문과 실행 승인에서 재사용한다. 새 서버나 별도 생성기를 만들지 않는다.

1. 0절 원문과 3절 전체 UI 계약을 읽고 상태·질문·이벤트를 typed contract로 구현한다. 3A의 실제 화면 배치와 Waiting/Submitting/Running/Failed/Completed 대표 상태를 먼저 렌더해 Sol이 직접 화면을 검사한다. 이 상태별 UI fixture는 개발 도구이며 제품 인수가 아니다.
2. DemoSession/ActionCard/event cursor 영속 저장·멱등 처리와 최소 DTO를 실제 API에 연결한다. 3E의 Accepted와 Delivery unknown을 빠뜨리지 않는다.
3. 입력·첨부·IME·응답 스트리밍/실제 진행 표시·취소·스크롤/포커스·실물 유무/로봇 선택을 기존 생성 서비스에 연결한다. 버튼은 3D의 Q1–Q9 contract를 사용하며 C1에 없는 후속 service는 이유 없이 READY로 표시하지 않는다.
4. 기존 launcher의 체크리스트·자가 복구 정책과 병렬 operation 표시를 연결한다. New/Add/Change, 기존 프로젝트 재열기, 오류 팝업·영문 UI를 유지한다.
5. UI-01–UI-09 및 UI-13–UI-17 중 C1에 해당하는 실제 Web/API 검사를 수행한다. 미연결 REAL 기능은 fixture 검사와 NOT_RUN을 구별한다. 사용자에게 스크린샷을 받고 나서야 기본 상태·입력 오류를 고치는 방식으로 넘기지 않는다.

완료 시험: 사진+글/글 단독 모두 실제 대화 질문까지 도달, 답변 전 후속 작업 0, 중복 클릭 1회 실행, reload 후 같은 질문·진행 복원, provider/engine 실패 구별, 소유 process 외 변경 0. 3A 화면과 3B–3G의 해당 상호작용을 실제 built Web/API에서 확인한다. 기능만 동작하고 UI 인수가 빠졌으면 C1은 PARTIAL이다. 이 단계에서 실행되지 않는 시뮬레이션·물리 버튼을 READY로 표시하지 않는다.

### C2 우측 viewer와 로봇 없는 데모 완결

대상: `twinpulse_engine_host.py`, Isaac `runtime.py` 및 compiler, engine/broker capability, robot profiles, C1 채팅.

새 모듈 제안: `viewport_service.py`, `robot_asset_catalog.py`, `simulation_mission.py`, `TwinViewport.tsx`. 기존 v1/v2 직렬화는 유지하고 실행 binding을 별도 version으로 둔다.

1. 현재 Windows Isaac에서 움직이는 실제 scene을 전달하는 viewport 기술 검증을 먼저 한다. 패널 외형을 먼저 완성하고 전송이 안 되는 상태로 넘기지 않는다.
2. 기존 자산의 관절·충돌·Physics 구동을 확인하고 v2 방에 실행 가능한 SIM robot을 결속한다.
3. LLM의 자산 선택·실제 생성 진행, 현재 방 Run, 자연어 목표·정지, viewer 접기/카메라 조작을 연결한다.
4. SIM 모드에서 robot transport를 만들 수 없게 테스트한다.

완료 시험: 새 프로젝트의 실제 UI로 단계 1→2→3→4→5를 끝까지 수행. 같은 장면의 Physics step, 관측 pose, 실제 프레임 변화, 목표 도착·Stop 증거를 저장한다. 실패/회복·viewer reconnect·다른 목표·비어 있지 않은 기존 프로젝트 보존도 검사한다. LLM 호출 미승인 시 fixture 검사는 별도이고 실제 provider 인수는 미검증으로 남긴다.

### C3 실물 준비 경로 통합과 배포 전 자격 검사

대상: `robot_readiness.py`, `robot_diagnostics.py`, `physical_controller.py`, `manual_controller.py`, `run_robot_field_suite.py`, `run_demo_preflight.py`, `packages/twinpulse_robot_safety/`, 기존 live adapter.

1. 등록 로봇→병렬 읽기 전용 검사→한 주행검증 작업→관측 확인→연동 상태를 C1 대화에 연결한다. 진단 버튼을 정상 경로에 다시 나열하지 않는다.
2. 기존 collector/원본 반출/오류 분석/전송 재개를 하나의 작업 결과에 연결한다. 항목 의존성을 DAG로 분리해 실패 후에도 안전한 독립 관측은 끝낸다.
3. 실제 목표 ROS/C++ 빌드 환경과 배포 binary/release·protocol·profile 일치를 **로봇을 켜 달라고 하기 전에** 확인한다. 현존 WSL 권한/컴파일러 blocker를 설치 없이 해결할 수 있는지 판단하고, 불가하면 필요한 환경과 미빌드 항목을 즉시 명시한다. 다른 언어의 mock PASS로 대체하지 않는다.
4. 배포 package, 로봇 profile 입력, 실측 mounting/footprint/timing 필요한 항목, 구동 qualification 무효화 규칙을 체크리스트로 묶는다. 이미 근거가 있는 값은 재요청하지 않는다.

오프라인 완료 시험: actual Web/API에서 정상 준비·SSH 실패·배포 불일치·정지 실패·사용자 문제 신고·boot 변경·결손 센서·전송 중단을 검사한다. 합성 robot 응답 시험은 실물 qualification이 아니다. 최종 field 실행 파일은 기존 `run_robot_field_suite.py`를 확장하며 새 진입 스크립트를 계속 늘리지 않는다. target 빌드가 외부 권한 때문에 막히면 그 항목은 BLOCKED로 남기고 독립적인 C4·C5 오프라인 구현은 계속한다. C3 전체 완료나 현장 준비 완료로 표시하지 않는다.

주의: target 빌드 가용성 조사는 C1 착수 시 병행해 외부 blocker를 늦게 발견하지 않는다. C3의 로봇 실제 실행은 아직 하지 않고 C4·C5까지 준비한 후 현장 묶음으로 수행한다.

### C4 조사와 경로 시연 및 실물 실행 연결

대상: `automatic_demo_service.py`, `automatic_mission_service.py`, `automatic_photo_store.py`, core `cold_start_mission.py`, `local_navigation.py`, `navigation_binding.py`, `active_mission_visual.py`, robot-local mission, Isaac.

1. `survey_only`와 `go_to_goal`을 같은 worker의 명시 모드로 나누고 조사 결과를 session의 준비 상태에 결속한다.
2. 현재 실사진 3 raw의 실패를 보존한 채 모델 불일치 진단과 부족 정보 질문·sensor map/visual model 분리 표시를 제품에 연결한다.
3. 자연어 목표→semantic ID/영역→경로→SIM 시연→digest/revision-bound Confirm→기존 로컬 mission 실행을 연결한다.
4. 최신 위치·scan·derived geometry를 viewer와 연결하고 5초 요약·즉시 오류·task 목록을 추가한다.

오프라인 완료 시험: 서로 다른 시작/방향·손이동·대칭 모호성·새 장애물·사진 변경·지연/끊김·저장 실패·cleanup 오류를 실제 App 경로에서 검사한다. 사전 시연 동안 physical command 0, old Confirm 실행 0, 위치 상실 시 current 표시 잔류 0, Stop/Force 지연이 LLM/렌더에 종속되지 않음을 입증한다. 올바른 합성 경로에서 같은 Confirm으로 끝까지 도착해야 한다. 실제 사진 정합 성공 여부는 별도 판정한다.

### C5 왕복 TaskLoop와 장기 운영

2026-10-06 v309 현재: 실제 1806.823초·21왕복(42완료구간)·120자원 표본·Stop/reload·88archive/정상종료 인수를 통과했다. native/App/task 복합 회귀245개와 최초 원인/cleanup/저장 분리는 검증했다. **C5 PARTIAL**: 모든 복합 실패가 actual built UI+Isaac에 전파되는 인수와 C6 최종 package/target/현장은 아직 남았다. 별도 legacy headless still capture의 viewport_missing FAIL을 viewer 성공으로 덮지 않는다. [최신 근거](../verification/goal-task-soak-faults-20261006.md). 아래 v307 현황과 완료 기준은 이력으로 보존한다.

2026-10-06 v307 현재: 상위 A↔B 작업·한 번 승인·새 하위 관측/actual Isaac preview·자원 admission·소유권/Stop·bounded 이력은 기존 제품에 연결했다. actual 합성 연속 두 반복구간과 Stop/reload 인수는 통과했지만 **C5 PARTIAL**이다. live 자원/다음 waypoint·progress-stall 정책, 아래의 3왕복·30분 지속·전체 fault matrix는 아직 완료하지 않았다. [최신 범위와 증거](../verification/goal-task-loop-20261006.md). 아래 완료 기준을 완화하지 않는다.

대상: C4 task/mission 계층, robot-local guard, battery/progress policy, raw journal/export, 오른쪽 task 목록.

새 모듈 제안: `task_loop.py`, `task_policy.py`, `telemetry_summary.py`. UI timer로 Start를 반복 호출하는 구현은 금지한다.

1. A/B·다리·횟수·예산·상태·중단 원인 계약을 구현하고 bounded child와 장기 task의 관계를 명시한다.
2. 양방향 경로·최신 관측·목표 도착·다음 다리 admission을 연결한다. 같은 루트 고정 재생이나 old pose 재사용을 하지 않는다.
3. 배터리 추정/unknown, 진행 정체·부하 센서 미지원, 센서/통신/저장 공간 한계, 취소 경쟁과 재시작을 처리한다.
4. 실제 명령/관측 raw를 보존하면서 메모리·로그·UI 이벤트를 bounded로 유지한다. 운영 중 디스크 부족은 최초 오류와 cleanup을 분리한다.

오프라인 완료 시험: SIM actual Physics 왕복 3회, 출력 반응형 robot fake 왕복·양방향 동적 장애물·하위 시간 만료·stale input/scan·배터리·stalled·full disk·Stop/Force fault matrix, 30분 PC 지속 실행의 메모리·로그 증거. 가속 가짜시계 검사는 실제 wall-time 지속 검사를 대체하지 않는다. 예상 가능한 보호 정지는 무한 재시도로 회피하지 않는다.

### C6 패키지 전체 인수와 한 번의 준비된 현장 세션

대상: 기존 release builder·`verify_packaged_automatic_demo.py`·field suite·Web E2E·검증 기록.

1. 현재 checkout이 아닌 최종 package만으로 새 사용자 데이터 경로에서 두 분기를 실행한다. 사용자 raw/사진/자격 증명은 배포 package에 포함하지 않는다.
2. 실제 Web→API→provider 또는 명시된 대체→Isaac→작업→보고서까지 12단계별 증거를 남긴다. UI 정상 조작 대신 내부 service 직접 호출로만 연결한 것은 제품 인수가 아니다.
3. C3의 target/release/profile 준비와 C4·C5 실패 회귀를 통과한 뒤 현장시험을 요청한다. 검토된 동일 package·단일 field suite·채팅 카드로 검사하며 즉흥 shell 탐색을 정상 절차로 삼지 않는다.
4. 현장에서 연결·scan/odom/TF·qualification·조사·경로 preview·짧은 실제 go-to·짧은 A↔B·Stop을 임무 범위 승인 안에서 수행한다. 안전상 일부가 실패하면 가능한 나머지 독립 진단·raw 반출을 끝내고 정확한 미수행 이유를 남긴다.
5. 해시가 바뀌면 영향 있는 qualification과 최종 경로를 재검사한다. 기존 실패는 보존하고 final release의 결과를 명확히 구분한다.

완료 시험: 아래 D01–D12 체크리스트와 실패 조건을 모두 판정한 최종 인수 보고서. 외부 blocker는 BLOCKED, 못 한 것은 NOT_RUN, 안전하게 거절한 시험은 EXPECTED_REJECTION으로 표시한다. 이 세 가지를 정상 경로 PASS에 합산하지 않는다.

## 7 현장시험 전 준비와 필요한 데이터

**지금 계획서를 작성하려고 로봇을 켤 필요는 없다.** 앞으로도 “일단 켜고 부족한 것을 찾기”보다 아래 준비물을 먼저 완성한다.

| 준비물 | 로봇 없이 가능한 작업 | 실제 현장에서 필요한 확인 |
| --- | --- | --- |
| 최종 프로그램 | reviewed binary/source manifest, dependency closure, protocol·profile 결속, package 인수 | 실제 배포본 hash·boot·실행 확인 |
| 센서 입력 | 기존 raw 재분석, 해석기·수명주기·실패 진단·전송 재개 | 새 release의 실제 scan/odom/TF·clock·rate·종료 결과 |
| 차체와 센서 | 기존 URDF/mesh/source 근거와 실측 항목 구분 | 명목과 다른 실장, footprint, 장착 TF, 취득 시각 보정의 근거 |
| 방 모델 | 기존 사진·raw의 불일치 분석, 치수/관측 높이 가설 분리 | 필요할 때만 특정 치수/현재 배치 보강. 막연히 새 한 바퀴를 요구하지 않음 |
| 제어 | 속도·정지·input stall·통신·배터리·원본 수집 코드 회귀 | 실제 정지 거리/시간, 최신 전송 지연, 현재 환경의 위치·장애물 대응 |
| 전체 UX | 질문·분기·오류·재접속·viewer·SIM·loop 검증 | 승인된 짧은 REAL 경로와 loop가 같은 UI에서 완료되는지 |

센서 실장/취득시각/목표 빌드가 준비되지 않으면 필요한 준비를 완료한 뒤 시험을 잡는다. 일부는 로봇이 켜져 있어도 측정 근거가 저절로 생기지 않는다. 새로운 데이터 요청에는 반드시 ‘어떤 미확정 값을 어느 테스트에서 판별하는지’를 붙인다.

현장에서는 시작 전 이번 임무 범위·전원·관찰·공간을 한 번 확인하고, 사용자가 요청한 7번 관측 확인 및 8/10/12번 작업 선택 외에 매 명령마다 확인을 요구하지 않는다. 문제가 없으면 로봇의 encoder/odom/scan/보드 관측을 우선 사용한다. 센서로 확인할 수 없는 물리 상태를 확인됐다고 꾸미지는 않는다.

## 8 최종 인수 체크리스트

| ID | 실행으로 입증할 완료 조건 | 주 증거 |
| --- | --- | --- |
| D01 | 바로가기 한 번으로 현재 package의 Web/API/Isaac 시작, 수동 터미널 불필요 | launch ID, 소유 PID, 실제 화면 |
| D02 | 준비 체크리스트, 허용 복구 성공·실패·수동 조치 구분, 무단 설치·원본 수정 0 | 항목별 attempt/원인/결과 |
| D03 | 사진+텍스트 및 글 단독으로 실제 채팅 생성, 취소·오류·재열기 | conversation/provider/tool 이벤트 |
| D04 | 실물 유무 답변까지 대기, 과거 카드·중복 응답이 재실행하지 않음 | decision/transition 기록 |
| D05 | SIM 선택→현재 방→구동 가능한 로봇→Run→채팅 목표, 실제 우측 3D | physics/pose/frame/도착·정지 |
| D06 | Burger 선택이 명확하고 장치·자산·profile를 혼동하지 않음 | registry/binding 기록 |
| D07 | 병렬 생성·연결→한 주행검증→사용자 관측→연동, 배터리·작업 표시 | current boot/release qualification+답변 |
| D08 | 두 준비 조건 전 조사 실행 불가, 현재 Confirm 한 번으로 시작 | join 상태·action ID |
| D09 | 다른 시작 위치에서 최신 센서로 조사·정합·관측 가능한 보정, 실패 시 사실대로 거절 | raw/pose residual/held-out/derived revision |
| D10 | 자연어 목표를 접근 가능 지점으로 해석, 현재 Twin 시연 후 exact plan Confirm | planner 비용·SIM 관측·plan digest |
| D11 | 승인 경로를 실센서로 주행, 5초 요약·즉시 경보·실측 Twin 갱신 | 명령/관측/시간/요약/도착 |
| D12 | A↔B 반복, 목록 표시, Stop/Force·저전압·정체·손실 때 종료하고 자동 재개 0 | task/child/stop/로그 용량·실제 짧은 왕복 |

공통 실패 회귀: LLM 인증/지연/취소, asset 누락·engine 시작/재시작, viewer 손실, ROS target 불일치, boot 변경, scan/odom/TF 결손·시각 이상, 위치 상실, 사진 불일치, 목표 차단, 오래된 확인 카드, 사용자 Stop·Force, low battery/unknown·진행 정체, transport stall, 저장 실패 및 cleanup 실패를 포함한다.

보고서에는 소스/package/input hash, 실제 사용한 런타임, 테스트 입력의 합성/저장/현재 실물 구분, 실행 명령, 시작·종료 시각, 결과, 최초 원인과 cleanup 결과, 원본 위치를 남긴다. 테스트 개수는 참고일 뿐 12개 사용자 흐름 완료를 대신하지 않는다.

### UI를 별도로 통과시켜야 하는 인수 조건

다음 UI 검사는 D01–D12에 추가되는 필수 조건이다. Playwright/컴포넌트 검사는 가능한 곳에 사용하고, 실제 built Web/API 화면과 backend operation/이벤트 기록을 연결해 검증한다. Screenshot 존재만으로 동작 PASS, API PASS만으로 UI PASS를 주지 않는다.

| 검사 | 시나리오와 기대 결과 | 주요 연결 |
| --- | --- | --- |
| UI-01 기본 배치 | 1920×1080·1280×800에서 메시지/질문/입력창/Twin이 겹치지 않고 정상 경로에 개발 패널 이동이 없음. 기본 화면에 장문 경고벽이 없음 | 3A, D03 |
| UI-02 첨부 | 파일 선택·붙여넣기·drop, 썸네일·제거·잘못된 파일·두 번째 사진 처리. 실패 후 초안 보존과 text-only 정상 생성 | 3C, D03 |
| UI-03 키보드 | Enter/Shift+Enter/한글 IME·Tab/포커스, 입력창 WASD 실물 전파 0. 입력과 선택의 접근 가능한 이름 확인 | 3B–3C |
| UI-04 답변 대기 | Q1/Q2를 누르기 전 장면 생성·로봇 접속을 앞서 시작하지 않음. 질문·버튼이 같은 assistant 메시지에 표시됨 | Q1/Q2, D04/D06 |
| UI-05 클릭 피드백 | local Submitting→server Accepted/Running→Completed를 화면과 이벤트에서 확인. accepted를 실패로 표시하지 않고 선택 결과가 사라지지 않음 | 3E |
| UI-06 응답 유실 | 중복 클릭·지연·서버 접수 후 응답 유실·다른 탭. 같은 ID 조회로 상태 복구, 물리 요청 재전송/이중 실행 0 | 3E, D04/D07/D10 |
| UI-07 진행과 오류 | engine/provider/robot 각각 실패·timeout·cleanup 실패. 짧은 이유·다음 조치·Details·팝업 중복 방지. 무응답/끝없는 spinner 없음 | 3G, D02 |
| UI-08 스트리밍 | delta 제공 provider는 점진 출력, 비제공 provider는 실제 진행/최종 응답. 취소 후 부분 답변·상태 보존. 부분 tool/card 실행 0 | 3C |
| UI-09 대화 도중 새 요청 | 기존 질문 설명 요청, 새 목표, Pending edit, old Confirm 만료. 초안·대화 보존, 불필요한 질문 반복과 무단 임무 교체 0 | 3F |
| UI-10 SIM 전체 화면 | 3H SIM 예시를 새 프로젝트에서 수행. Run simulation이 채팅에서 나타나고 실제 현재 방의 Physics 및 viewer가 진행. 실제 robot 연결 0 | D01–D05 |
| UI-11 REAL 선택 흐름 | Q1→Q2→병렬 생성/연결→Q3→Q4→Q5를 정상 UI로 수행. 준비 차단 이유·다음 카드 자동 표시·중복 점검 클릭 불필요. fake와 field 결과 구분 | D06–D09 |
| UI-12 목표와 반복 | preview에서 실제 명령 0, Q7 승인→5초 요약→도착→Q8 loop→Stop. 과거 승인 재사용 0, 다음 버튼을 위해 Refresh 0 | D10–D12 |
| UI-13 접기와 재열기 | Twin 접기/펼치기·뷰어 연결 끊김·페이지 새로고침. 새 임무 0, 진짜 engine/robot 손실은 그대로 보고, 우측을 닫아도 Stop 접근 가능 | 3A/3G |
| UI-14 대화 가독성 | 이전 메시지를 읽는 중 진행 업데이트·5초 요약이 와도 scroll/포커스 탈취 0. New updates와 Last updated 표시 | 3B/3G |
| UI-15 세 정지 구분 | Stop response는 생성만 취소. 일반 Stop·Force STOP은 별도 경로·확인 표시. LLM 지연·3D 미응답 중에도 로봇 정지 UI 사용 가능 | 3C/3I, D12 |
| UI-16 작은 화면 | 390×844 또는 동등한 좁은 viewport에서 가로 overflow·가려진 선택/정지 없음. Chat/Twin 전환에도 task 유지. 외부 접속 설정 변경은 이 검사에 필요 없음 | 3A |
| UI-17 영속성과 복구 | 새로고침 후 메시지·응답 대기·작업 결과 복원, 물리 권한/current pose 임의 복원 0. 새로운 operation은 실제 새 선택에서만 생성 | 4절 |
| UI-18 최종 증거 | 같은 최종 build의 SIM/REAL 흐름 녹화 또는 연속 캡처와 event/operation 대응. fixture/fake/actual engine/field를 명확히 구분하고 미수행은 NOT_RUN | C6 |

Sol은 최소 첫 화면, 선택 대기, 병렬 준비, READY, 실행 중, 실패, 정지 후 화면을 직접 열어 검사한다. 개발 중 state fixture에서 검사한 내용과 실제 서비스로 검사한 내용을 별도로 남긴다. UI-10의 SIM 인수와 UI-11/12의 실제 field 인수는 fake 화면으로 대체할 수 없다.

일반 사용자가 정상 분기를 끝내려면 콘솔/API/개발용 fixture 주입이 필요하거나, ‘언제 무엇을 누를지’ 설명을 채팅 외부에서 받아야 한다면 제품 완료가 아니다. 물리 안전을 위한 최초 현장 안내·정확한 사용자 선택까지 없애라는 뜻은 아니다.

## 9 Sol 작업 및 보고 규칙

1. C1→C2→C3→C4→C5→C6 순서로 구현한다. target 빌드 가용성 조사는 C1과 병행한다. 기존 기능을 조사 없이 다시 만들지 않는다.
2. 각 묶음에서 UI만/contract만/mock만 완료라고 끝내지 말고 기존 서비스와 실제 실행 흐름을 연결한다. 다음 묶음으로 넘어갈 조건과 실패한 조건을 함께 기록한다.
3. 기존 dirty 변경·원본 raw·과거 실패·v1/v2 hash와 안전 기준을 보존한다. 센서200ms/input250ms/segment50ms 등의 통과 기준을 맞추기 위해 완화하지 않는다.
4. 새 파일/API 이름은 제안이므로 코드 검토 후 조정할 수 있다. 승인 흐름·로그·완료 조건을 임의 축소하지 않는다. 설치/유료/실물/시스템 변경의 미승인 작업은 별도 범위로 남긴다.
5. 매 의미 있는 묶음 종료에 Baseline/Memory/관련 검증 기록을 동기화한다. ‘구현됨’, ‘오프라인 제품 인수’, ‘실제 Isaac Physics’, ‘실물 인수’를 별도로 보고한다.
6. 5초 상태 요약이나 자율 제어를 위해 무제한 LLM 호출을 만들지 않는다. 이번 계획 실행이 새 API 비용을 자동 승인하는 것은 아니다.
7. 토큰과 대기 시간을 줄이기 위해 최초 실패를 구조화해 원인별로 묶어 수정한다. 변경 없는 전체 회귀·동일 blocker 재점검·문서만 추가하는 작업을 반복하지 않는다.
8. 0절 사용자 원문을 축약된 기능 목록으로 대체하지 않는다. 3절 UI 계약과 UI-01–UI-18을 해당 C 묶음의 완료 조건으로 사용한다. 문구·기능 존재만 검사하지 말고 클릭 전후 실제 화면과 후속 동작을 확인한다.
9. 매 묶음의 제출 내용은 원문 해당 번호, 변경한 기존 경로, 실제 화면 증거, backend 작업 근거, 실패 회귀 결과, 아직 필요한 외부 근거다. 기본 UX·이중 실행·조용한 실패를 사용자에게 대신 찾아달라고 하지 않는다. 사용자의 주관적 선호나 현장 관측이 필요한 경우에만 한 번에 모아 질문한다.
10. 이 문서의 디자인 기준은 한 번에 구현 의도를 전달하기 위한 구체안이지 오류 없는 완성을 보증하지 않는다. 이를 핑계로 완료 조건을 줄이지 말고 개발자가 확인 가능한 오류를 제출 전에 해결한다. 제품 구현을 시작하는 승인은 이 문서 보완과 구별한다.

Sol 착수 지시문:

> AGENTS.md와 최신 Memory/Baseline를 읽고, 이 계획의 0절 사용자 원문과 3절 UI 명세를 먼저 읽어라. 사용자의 목표는 기존 관리 패널에 채팅을 붙이는 것이 아니라, 채팅에서 질문·선택·생성·시연·실물 승인·상태 확인·반복 임무가 이어지는 제품이다. C1부터 기존 코드에 연결하며 각 묶음에 해당하는 D01–D12와 UI-01–UI-18을 실제 화면 및 API/실행 기록으로 검사하라. Waiting/Blocked/Submitting/Accepted/Running/Completed/Failed/Delivery unknown/Expired 상태를 누락하지 말고, 준비 전 버튼 활성·클릭 후 상태 초기화·새로고침해야 다음 단계 표시·중복 물리 실행을 제출 전에 직접 찾아 고쳐라. 기존 raw·검증·안전 기준은 보존하라. 로봇 없는 C1–C5 구현과 target/release/profile/collector 준비를 먼저 하고, 준비되지 않은 상태에서 로봇을 켜 달라고 요청하지 말라. 미승인 실물·배포·설치·비용 발생은 하지 말고 의존하지 않는 오프라인 작업은 계속하라. 실제 provider/Isaac/로봇을 실행하지 못한 부분은 NOT_RUN으로 남겨라. 기본 UI QA를 사용자의 반복 지적으로 대신하지 말고, 완료 조건을 충족하는 묶음 단위로 진행·보고하라.

## 10 참조 근거

- 기존 구현과 실제 검증 범위: [Baseline](TWINPULSE_BASELINE.md), [Project Memory](TWINPULSE_PROJECT_MEMORY.md), [패키지 통합 검증](../verification/ad4-review-fixes-20261005.md#packaged-web-api-and-isaac-acceptance).
- 센서·정합·로컬 제어 계약: [기존 자동 데모 계획](TWINPULSE_AUTOMATIC_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-04.md), [AD1 이후 관측·target 경계](../verification/ad1-observation-transport-20261004.md).
- 코드 근거: `scripts/twinpulse_launcher.py`, `scripts/twinpulse_engine_host.py`, `apps/twinpulse-web/src/App.tsx`, `packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py`, `automatic_mission_service.py`, `physical_controller.py`, `robot_readiness.py`, `extensions/twinpulse.extension/twinpulse/extension/runtime.py`, `packages/twinpulse_core/src/twinpulse_core/robot_profiles.py`.
- 외부 기술 근거는 5절의 NVIDIA 공식 6.0.1 문서를 사용했다. 설치된 RC 빌드의 모든 API가 문서와 같다고 가정하지 않고 C2에서 실제 동작을 검증한다.

이 문서의 상태는 **PLAN_ONLY**다. 새 채팅·실시간 viewport·SIM v2 Run·실물 자동 demo·왕복 loop의 구현 또는 인수를 완료했다고 주장하지 않는다.
