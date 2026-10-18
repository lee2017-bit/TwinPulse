# TwinPulse 실행 진단과 남은 데모 구현 계획

최신 구현 추적(2026-10-08 v346): 기존 실행 graph·편집 origin·화면 복구에 이어 observed_mission의 admission/PC 관측 조사·정합/보정 commit/검증된 remote ACK/cleanup/report span을 연결했다. 미수신 ACK unknown, Stop cancelled, bounded SHA256 metadata, sink degraded와 제어 격리 검증을 통과했다. 최종진단134/관련18/Web414/type/build, 단독 합성 native3 PASS·30artifact hash 일치(중복). 병렬 정상 입력 만료 FAIL·원인 미확정/당시raw 누락 한계는 보존하고 이후 assertion 전 반출로 보완했다. **이 완료 범위를 다시 미구현으로 세지 않는다.** 남은 다른 외부edit/정합·remote 경계/제한raw 조회/동적Loop·전체자원/P2 실제 품질/최신package/F0-F1 및 whole=false는 [현재 검증과 잔여](../verification/execution-graph-and-post-edit-render-20261008.md)를 따른다. 아래 ‘최신’ 표현과 PLAN_ONLY는 당시 이력이다.

최신 구현 추적(2026-10-07 v339): 1시간 작업으로 browser 표시 오류 exact ID/원 Build·Run 잠금/Stop 유지, 정상409 교체/실제 HTTP 분류·중복 억제, startup 입력 보존, shared writer quota/owned crash 복구·두 프로젝트 인증 API/저장 분리, launcher monitor/cleanup 및 exact runtime 링크를 연결했다. Python229/Web374/type/build, actual text HTTP503 진단→복구·PhysX/Stop/reload/reset·600초/588회/공백0/heap 비증가·정상 이미지/owned 종료 PASS. **병렬 API/quota와 대표 browser fault/10분 idle soak를 다시 미구현 목록으로 세지 않는다.** 전체 O1/O2/O4/O5 PARTIAL: 다른 commit/rollback/cleanup 경계·외부edit/정합/remote ACK 세부·raw 제한 조회/graph·동적Loop/GPU전체 profile. 이후 P1 사진 치수/library/support/attachment 의미 검사→P2 실제 LLM 성공/repair 품질 평가→패키지/F0/F1 순서다. 모델은 fixture/유료·로봇0, raw/과거 FAIL/hash/guard·whole=false·예약PAUSED 유지. [최신 검증·잔여](../verification/execution-diagnostics-20261007.md). 아래 ‘최신’과 PLAN_ONLY 표기는 당시 이력이다.

최신 구현 추적(2026-10-07 v338): apply 실패와 frame 관측을 분리해 exact 원인/진단, 필수 생성 저장 미완료의 메모리 안내·UI/API 차단, 입력 저장 오류 코드503/진단·이전 상태 보존을 연결했다. 선택적 sink 실패는 정상 SIM을 실패로 바꾸지 않는다. Python88/Web362/type/build, actual apply/필수 저장 차단 및 선택적 저장109frames/렌더/PhysX/Stop/reset/degraded PASS. 미적용 host FAIL·capture NOT_RUN 보존. O1/O2/O4/O5 전체 PARTIAL: 중간 USD rollback/다른 저장 경계·browser 이미지 HTTP·병렬/quota/correlation/raw/graph/최종soak 잔여; 이후 P1/P2·실물은 미완료. [최신 근거와 상태표](../verification/execution-diagnostics-20261007.md). 아래 추적은 당시 이력이다.

최신 구현 추적(2026-10-07 v337): 첫 current frame 대기를 bounded 실패/unknown 관측과 exact Build 참조로 연결하고 적용 성공·실제 대기 시간을 구분했다. Run 대기·exact 진단·모바일 수정, Python85/Web360/type/build, 실제 frame-loss r4 renderer capture PASS·frame0/Build1 succeeded/Run0·진단/export/reload/mobile와 정상88frames/목표·Stop/reset PASS. O1/O2/O4/O5 전체 PARTIAL: apply/storage/browser 이미지 HTTP·다른 복합 오류, 병렬/quota·상세 correlation·최종 soak 잔여. 이후 P1/P2 및 실물은 미완료다. [최신 근거와 상태표](../verification/execution-diagnostics-20261007.md).

이전 구현 추적(2026-10-07 v336): 인증된 후속 SIM 오류를 명령 receipt와 분리하고 exact popup/command 연결·최초/cleanup 보존·중복 억제·현재 단계 안내를 구현했다. 최종Python50/81(중복), Web355/type/build 및 실제 Chrome/API/Isaac 37frames 복합 pose/cleanup/Run HTTP 유실·reload/Run1·진단/export 인수 PASS. O1/O2/O4/O5 전체는 PARTIAL이며 당시 잔여는 apply/frame/storage 나머지 복합 UI·두 프로젝트/quota 및 최종 soak였다. [최신 상태표](../verification/execution-diagnostics-20261007.md)를 기준으로 한다.

작성일: 2026-10-07 KST. 구현 담당: 6.1 Sol. 코드·검증 기준: Baseline v1.0.330. 문서 및 우선순위 기준: v1.0.331. 상태: PLAN_ONLY. 이 문서 작성으로 제품 기능이나 현장 인수가 완료된 것은 아니다.

구현 추적(2026-10-07 v335): [실행 진단 제품 연결 및 실제 SIM 인수](../verification/execution-diagnostics-20261007.md). v332 기본 연결, v333 generation/event/edit/launcher 및 v334 검색/페이지/typed 관련 실행에 exact history 편집 origin 영속 복구·이전 edit 참조를 추가했다. 실제 복구 후 Build 인자 중복 결함을 재현·수정했다. 최종 집중46/관련87/Web353/build와 실제 Chrome/API/Isaac r3 114frames/편집·Undo·Build current frame/종료 후 동일ID·원본/이력 불변 PASS. 위 PLAN_ONLY는 계획 작성 당시 상태다. 현재 O1/O2/O4/O5 전체는 PARTIAL이며 정확한 잔여는 검증 기록 상태표를 따른다. P1 이후 및 실물 완료로 해석하지 않는다.

목표는 개발 중 성공과 실패를 한 실행 단위로 찾아보고, 최초 실패와 후속 오류를 구별하며, 기다린 구간과 느린 함수를 측정할 수 있게 만드는 것이다. 기존 로컬 기록을 연결하고 실제 App에서 조회할 수 있게 한다. 이어서 남아 있는 사진 생성·가구 라이브러리·제품 인수와 현장 검증을 순서대로 마무리한다. 새 로깅 서비스 구독이나 클라우드 배포는 필요하지 않다.

## 1 사용자 의도와 작업 범위

사용자 원문:

> 그래 맞는말이다. 지금 필요한것은 내가 개발하면서 실패나 성공 로그를 하나의 실행 ID로 통합해서 묶어서 분리해서 보여주고 병목함수를 측정해주는 기능이 필요한거지 특정한 프로그램 구독이 필요한게 아니다. 그럼 일단 그거 지금 반영하면 앞으로 오류개선할때 유리할까? 나한테 도움이 되어야지. 실제 반영하기전에 확인해보려는거니까 잘 고민해서 답변해봐

> 좋아 그럼 그거부터 해볼까? 근데 이전에 시켰던작업중에 먼저 우선순위로 해놓아야하는데 빼먹은 작업 있나? 있으면 그거부터 해도 되고, 아무튼 다포함한 작업계획서 6.1Sol에게 시키는 용도로 만들어줘라

이번 턴의 산출물은 계획서와 기준 문서의 포인터다. 실제 구현을 이어서 지시받으면 아래 O0부터 시작한다. 과거의 사진 전송·추론 예산 승인은 해당 범위에서 유지하되, 이 계획서 작성 중에는 외부 추론이나 로봇 명령을 실행하지 않는다.

사용자가 원하는 결과는 다음과 같다.

- 실패가 나면 사용자가 로그 파일을 찾아 모으거나 같은 실험을 반복하지 않아도 원인 조사에 필요한 기록을 찾을 수 있다.
- 한 실행 안의 성공한 단계, 실패한 단계, 수정 시도, 실행하지 못한 단계를 각각 볼 수 있다.
- 오래 걸리는 구간과 함수가 수치로 드러나며, 확인하지 못한 원인을 확정된 원인처럼 표시하지 않는다.
- 기존 채팅은 현재 질문 하나와 다음 행동 하나를 유지한다. 상세 개발 정보는 별도 Diagnostics 화면에 둔다. 제품 UI는 영어, 인수인계와 보고는 한국어다.
- 통합 진단을 만드는 동안 사진 기반 Twin과 실제 로봇 데모라는 기존 목표를 잊지 않는다. 아래 잔여 목록을 삭제하거나 새 로그 기능의 PASS로 대체하지 않는다.

## 2 선행 누락과 현재 완료 범위

최신 Memory와 검증 기록을 대조하면 통합 진단 전에 별도로 끝내야 하는 대규모 구현은 확인되지 않았다. 먼저 O0에서 현재 제품 경로와 기준 실패를 고정하고 O1부터 진단을 연결하는 것이 타당하다. 다만 아래 미완료를 방치한 채 로그 화면만 계속 확장하면 안 된다.

| 항목 | 현재 근거와 남은 부분 | 우선순위 |
|---|---|---|
| 재사용 모델 라이브러리 | home/common/warehouse 중복 제거 28종. 표준 Site2.2 생성·편집·저장·Isaac 연결 및 크기 변경 검증 통과. 새 옵션의 실제 LLM 선택·수정 품질은 미검증 | O 완료 후 P1과 P2 |
| 실제 사진 생성 경로 | compact-photo 1.0/1.1은 여전히 옛 고정 크기 가구 출력. 새 library 선택을 실제로 잘 쓰는 기본 사진 경로 인수는 미완료 | P1 최우선 |
| 기본 정책과 실험 정책 | 기본 thinking은 출력 10000에서도 length/timeout 실패 기록. 명시 compact/no-thinking 성공은 별도 실험 정책이며 기본 제품 채택 미완료 | P1 개선 후 P2 채택 판단 |
| 사진의 배치와 지지 | 옷장 위치·방향, 의복·침구 부착, 블라인드·케이블 등 오류 잔여. P01 검토 24항목·4위치·파생 지지3개 통과가 전체 사진 복원은 아님 | P1 |
| 실제 모델 평가 | 이전 특정 사진의 수정 후 성공은 확인. 새 library, 검토 제약 없는 사진, 기존 전체 평가 행렬은 미완료 | P2 |
| 채팅과 편집 흐름 | 한 질문·한 진행 버튼, 텍스트 생성, 수정/Undo 등 인수 기록 있음. 새 생활 물체 전체의 채팅 staging→drag/회전·현재 source 인수 등은 최신 근거로 재대조 필요 | P3에서 빈칸만 구현 |
| 장시간 실행과 최종 패키지 | 과거 actual 30분 합성 센서 반복 시험은 통과. 이후 current sensor 표시·library 변경을 포함한 최종 패키지 전체 인수는 아님 | O5 및 P4 |
| 로봇 준비 | corrected ARM64 driver 빌드와 실제 current 배포·의존성 검증은 완료. torque=true, 바퀴/명령0 관측은 과부하나 SSH 실패가 아님. 새 driver의 실제 scan/odom/TF·정지·정합은 미인수 | F0와 F1 |
| 실물 자율 임무와 Loop | 오프라인/합성 통합과 일부 actual Isaac 인수 있음. 새 release의 현장 자격·실측 정합·목표·왕복 인수는 없음 | F1 |

근거: [모델 library](../verification/parametric-model-library-20261007.md), [출력 10000 실제 평가](../verification/photo-output10000-20261007.md), [기존 H 평가와 미완료 행렬](../verification/agent-reliability-nemotron-20261007.md), [실제 driver 연결](../verification/robot-driver-path-integration-20261006.md), [current 표시와 복합 오류](../verification/goal-coupled-ui-native-display-20261006.md), [30분 자원 시험](../verification/goal-task-soak-faults-20261006.md).

이전 문서의 과거 NOT_RUN을 최신 PASS 이후에도 새 미구현으로 취급하지 않는다. 반대로 과거 소스의 PASS를 새 소스의 인수로 복사하지 않는다. C1~C6, H5/H6 전체 상태는 각 완료 조건과 최신 근거를 다시 대조할 때까지 PARTIAL이며 whole_demo_ready=false다.

## 3 전체 작업 순서와 중단 기준

1. O0에서 실행 경로·기록 위치·현재 실패·최신 source를 고정한다.
2. O1과 O2에서 실행 기록 저장과 실제 서비스 간 ID 연결을 완료한다.
3. O3과 O4에서 시간·함수 분석, Diagnostics 화면과 진단 묶음 내보내기를 연결한다.
4. O5에서 성공·실패·취소·병렬 작업을 실제 제품 경로로 인수한다. 여기까지를 첫 완료 묶음으로 보고한다.
5. P1에서 사진 생성과 새 library, 위치·지지·부착 계약을 연결한다. P2에서 실제 모델 품질을 측정하고 기본 정책을 결정한다.
6. P3의 기존 사용자 흐름 잔여와 P4의 최종 패키지 인수를 마무리한다. F0 현장 준비는 이 작업들과 병행할 수 있다.
7. F0가 통과하고 현장 승인·감독이 확보되면 F1을 한 세션으로 실행한다. 로봇을 켜야만 할 수 있는 부분을 이 시점에 구분해 요청한다.

O5를 넘어서 새 대시보드, 범용 APM, 외부 exporter, 로그 검색 언어, 여러 서비스 배포를 계속 추가하지 않는다. 후속 P 작업의 실제 실패를 조사하는 데 O 기능을 사용하고, 관측 결함이 재현될 때만 보강한다. 코드 단위마다 사용자에게 다음 진행 여부를 묻지 않는다. 유료·현장·설치 등 현재 권한 밖의 조건은 해당 부분만 명시하고 독립 오프라인 작업은 계속한다.

## 4 기존 코드와 기록 재사용

기존 로그를 새 형식으로 덮어쓰거나 별도 미니 생성기·로봇 제어기를 만들지 않는다.

| 기존 위치 | 현재 역할 | 이번 연결 |
|---|---|---|
| packages/twinpulse_app/src/twinpulse_app/provider_composition.py | 기본 Nebius도 AuditedChatTransport를 사용. campaign은 선택 사항 | 기본 제품 호출과 실험 호출 모두 execution 연결. 다른 provider 경로는 실제 지원 범위를 별도 표시 |
| packages/twinpulse_provider/src/twinpulse_provider/reliability.py | attempt ID, 제한·민감정보 제거 응답, request/schema hash, usage, 시간, 비용 ledger | 원본 evidence 참조와 operation/attempt 연결. 비용 기록 중복 생성 금지 |
| packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py 및 service.py | 관측·계획·검증·단일 repair·취소·deadline 진단 | 단계 span과 결과 전달. 기존 요청/실행 의미 보존 |
| App conversation_service.py, application.py, product_workflow_service.py | 채팅·생성·operation마다 식별자와 상태 | 명시 correlation 전달 및 영속 매핑. 한 전역 current ID 사용 금지 |
| App command_broker.py, process_manager.py, viewport_service.py | command/engine 상태, 소유 프로세스 로그, 프레임 FPS/신선도 | dispatch/ACK/apply/current frame을 구분하고 현재 실행에 연결 |
| scripts/twinpulse_engine_host.py 및 Extension bridge_client.py, runtime.py, isaac_adapter.py | 실제 Bridge·USD·PhysX·capture | 소유 command와 receipt를 기준으로 Build/Run/Stop 측정 |
| App session_history.py, physical_controller.py, remote_observed_adapter.py, goal_task_loop.py | session.jsonl, 전송/정합/정지 진단, robot worker와 TaskLoop | 기존 raw와 session/mission/leg를 실행 트리에 연결 |
| scripts/verify_goal_separated_journey.py | 선택적 cProfile·스택 샘플 진단 | 재사용 가능한 오프라인 함수 프로파일 진입점으로 정리 |
| scripts/owned_process_metrics.py | 시험 소유 프로세스의 메모리·handle·thread 관측 | 선택적 자원 표본을 실행 ID에 연결 |

경로 표에서 파일명만 쓴 App 항목은 packages/twinpulse_app/src/twinpulse_app 아래다. Extension 항목은 extensions/twinpulse.extension/twinpulse/extension 아래다. 새 파일은 예컨대 App execution_diagnostics.py와 진단용 공통 schema 정도로 시작한다. 순수 schema가 Isaac/ROS/GUI 의존성을 가져오지 않게 한다. 파일 개수 자체를 완료 지표로 삼지 않는다.

코드에서 확인된 선행 보강 항목은 다음 네 가지이며 O1/O2에 포함한다.

- 일반 Nebius 호출은 attempt ID를 메모리에서 만들고 HTTP 종료 후 finally에서 evidence를 저장한다. campaign reserve만 선행 영속 기록이 있다. 일반 제품에서도 호출 시작·dispatch 의도와 attempt ID를 전송 전에 선기록하여 crash 때 추적 가능한 unknown으로 복구한다. 기록 이전에 HTTP가 나가지 않게 하고, 그 admission 기록이 실패하면 새 호출을 시작하지 않는다. started만 있고 결과가 없으면 실제 서버 도달 여부를 단정하지 않는다.
- application.py의 SiteGenerationResult 전달과 strict SiteDraft 저장에는 provider provenance가 그대로 보존되지 않는다. 저장 sidecar/index에서 generation→provider request→attempt를 연결하고 옛 draft schema를 바꾸지 않는다.
- isaac_adapter.py의 기존 snapshot run_id는 site plan의 plan_id를 사용한다. 이를 새 execution_id로 간주하면 같은 plan의 반복 실행이 합쳐진다. broker command와 별도 실행 identity로 구분하며 기존 run_id 의미는 보존한다.
- Bridge에는 network thread, Kit update 실행, receipt 전달 대기가 따로 있다. 큐 포화로 receipt가 유실된 경우도 누락/unknown으로 기록하고 실제 실행 실패와 전달 실패를 구별한다.

## 5 실행 식별자와 결과 계약

### 실행의 단위

- execution_id는 서버가 사용자 의도를 수락할 때 한 번 만든다. 예: 방 생성, 명시 재시도, 경로 시연, 승인된 조사, 승인된 왕복 작업.
- workflow_id는 여러 사용자 결정으로 이어지는 전체 대화를 연결한다. 한 execution을 답변 대기 중 무한히 열린 상태로 두지 않는다. 사용자 대기와 실제 계산 시간을 구분한다.
- span_id와 parent_span_id는 한 실행의 내부 단계 및 병렬 분기를 표현한다. observer→planner→validation→repair→save→Build→frame을 같은 트리에서 본다.
- 기존 conversation_id, operation_id, generation_id, provider request_id/attempt_id, broker command_id, engine_session_id/run_id, robot_session_id/boot/release, mission_id/task_id/leg_id를 별도 refs로 보존한다. 이름이 같아도 의미가 다르면 덮어쓰지 않는다.
- 중복 제출·재전송은 기존 멱등 키에 해당하는 실행을 돌려준다. 사용자가 실패 후 명시 Retry하면 새 execution을 만들고 retry_of로 연결한다. 실제 HTTP 재호출은 새로운 attempt다.
- 한 Loop의 상위 task와 각 bounded leg를 구분한다. Stop은 해당 task를 종료하고 새 leg 발행을 막는다. UI 새로고침·진단 조회가 실행이나 센서 시작을 만들면 안 된다.
- 시작 전에 난 launcher 실패도 launch execution으로 남기고 backend가 생기면 연결한다. backend가 생성되지 않아도 로컬 진단 파일 경로를 알려준다.

### 이벤트와 상태

schema_version, execution_id, event_id, span 관계, component, event_name, component별 순번, wall timestamp, clock_domain과 clock_instance_id, 로컬 monotonic 기준 시간/기간, stage, outcome, 기존 refs, 안전한 error_code/요약, evidence_refs를 기본 계약으로 둔다. clock_instance_id는 host/boot/runtime과 브라우저의 page time-origin처럼 실제 기준점이 바뀌는 경계를 구별한다. 입력·plan·scene·library·source/build 식별은 hash/버전과 허용된 설정만 남긴다.

단계 outcome은 running/succeeded/failed/cancelled/skipped/unknown을 구분한다. 실행 요약에는 최초 오류, 후속 cleanup 오류, 기록 누락 여부, 성공한 단계, 실패한 attempt, 최종 결과를 별도 필드로 둔다. 정상 사용자 Stop을 시스템 오류로 표시하지 않되, Stop 결과나 정리가 확인되지 않으면 성공으로 만들지 않는다. 실패→수정 성공은 최종 성공과 failed attempt를 함께 보존한다.

HTTP timeout이나 프로세스 단절은 외부 결과 미확정일 수 있다. 제품은 실패 또는 취소됐더라도 늦게 도착한 응답·비용 정산을 같은 attempt에 append한다. 제품 실행 결과를 뒤늦게 성공으로 바꾸거나 장면 적용·재호출을 시작하지 않는다. 외부 처리 결과와 사용자 작업 결과를 분리한다. 깨진 JSONL 끝부분과 누락된 종료는 interrupted/unknown으로 표시하고 조용히 PASS 처리하지 않는다.

진단 ID는 추적용이다. 인증·owner·boot·release·scope·정지 자격·plan/scene hash를 대신하지 않는다. 기존 v1/v2 직렬화나 hash 대상에 새 필드를 끼워 넣지 않는다. 별도 metadata/sidecar나 명시적으로 버전이 확장된 전송 envelope에 붙이고, 엄격한 native protocol에는 미검증 필드를 즉흥 추가하지 않는다.

## 6 시간 측정과 함수 프로파일링 계약

항상 켜는 것은 가벼운 단계 시작/종료와 결과 기록이다. 함수 프로파일링·스택 샘플링은 대상·기간·출력 크기를 제한한 진단 모드다.

- CPU 계산, 대기열, 외부 HTTP 대기, validation/repair, 저장, Bridge dispatch→ACK→apply, 첫 current frame, 입력 발행/수신/처리, 센서 수신/정합, cleanup을 구분한다. 측정하지 못한 하위 항목은 unavailable로 남긴다.
- 같은 clock_domain과 같은 clock_instance_id의 monotonic 값으로 기간을 계산한다. PC와 로봇, 브라우저 reload 전후의 performance.now(), 재부팅 전후 기준점을 직접 빼지 않는다. wall time은 표시·대략 정렬용이며 시계 차이를 네트워크 지연으로 단정하지 않는다. sequence·상관 ID·왕복 상한과 기존 시각 불확실성을 사용한다.
- 병렬 단계의 소요 시간을 합쳐 전체 시간이라고 하지 않는다. parent inclusive time, 실제 child time, 대기/겹침을 구분한다. 증거가 없는 critical path나 CPU 비율은 계산하지 않는다.
- LLM은 observer/planner/repair별 모델·output policy·finish_reason·usage·호출 시간·검증 실패를 보여준다. 스트리밍이 없는 transport에서 TTFT나 서버 내부 계산 시간을 지어내지 않는다.
- cProfile 결과는 함수 경로·이름·호출 횟수·self/cumulative time을 execution에 연결한다. timer_basis=wall/thread_cpu/process_cpu와 thread/worker별 측정 범위를 기록한다. 기본 elapsed 결과에는 블로킹 대기도 포함될 수 있으므로 Profiled elapsed로 표시하고 실제 CPU timer를 쓴 결과만 CPU time으로 표시한다. 누적 시간의 중복을 주의하고 프레임 locals, 환경변수, 요청 전문을 수집하지 않는다.
- 진단 도구의 측정 비용을 기록한다. profiled 결과를 일반 실행 성능 인수로 사용하지 않는다. 실제 로봇의 watchdog/모터 제어 loop에 cProfile을 기본 장착하지 않는다.
- 상세 측정을 위해 유료 호출이나 실제 이동을 자동 재실행하지 않는다. 저장 자료·순수 계산·명시된 합성 worker부터 사용한다. 재생 결과는 원래 실행의 시간이나 새로운 모델 성공률로 합산하지 않는다.

## 7 저장과 진단 화면

### 저장 원칙

기존 사용자 데이터 root 아래 전용 diagnostics 디렉터리에 execution별 manifest, append-only events, 안전한 summary와 profiler artifact를 둔다. provider-evidence, session.jsonl, rosbag/센서 원본 등은 중복 복사 대신 검증된 참조로 연결한다. 원본 bytes와 hash를 보존한다. 과거 자료에는 근거 있는 ID만 매핑하고 historical/imported 상태를 붙인다.

이벤트 writer는 bounded queue와 단일 소유 writer를 사용한다. 제어/정지/센서 신선도 경로에서 디스크 flush·압축·큰 JSON 직렬화를 기다리지 않는다. sequence 중복 제거, 부분 쓰기, 종료 전 flush 한도, 재시작 시 복구, 파일 회전과 용량 상한을 명시한다. 자주 반복되는 telemetry는 요약할 수 있으나 종료·오류·attempt 결과의 누락은 명시적으로 계수한다.

새 진단 sink 실패가 Stop을 늦추거나 기존 최초 오류를 덮지 않게 한다. diagnostics_degraded와 누락 수를 표시하고 메모리도 bounded로 유지한다. 기존 비용 ledger·필수 임무 raw·release/정지 근거 저장 실패의 fail-closed 정책은 그대로다. 선택적 trace와 필수 실행 근거를 혼동하지 않는다.

로컬 응답 audit의 기존 제한·redaction을 재사용한다. 새 summary/export에는 API key, 인증 헤더, 쿠키, 전체 환경변수, 사진 base64, 개인 파일 전체 경로를 복사하지 않는다. 민감 응답을 포함하는 상세 원본은 로컬 제한 범위로 두고 export 기본값에서 제외한다. 로그 메시지·모델 출력은 데이터로 취급하며 HTML 또는 명령으로 실행하지 않는다.

기존 response_sha256는 전체 수신 bytes의 hash이고 저장 문자열은 크기 제한·UTF-8 변환·redaction을 거친다. 새 인덱스는 원응답 hash와 실제 보관 artifact hash를 별도 필드로 유지하고 byte count/truncation/redaction 상태를 함께 표시한다. 두 hash의 일치를 요구하거나 제한된 문자열을 무손실 원문으로 표시하지 않는다. 기존 evidence를 수정해서 새 hash를 끼워 넣지 않는다.

### 사용자가 보는 화면

기존 설정/진단 진입점에 Diagnostics를 둔다. 기본 채팅의 실패 메시지에는 짧은 원인과 View diagnostics 링크 하나를 제공한다. 정상 작업마다 로그 팝업을 띄우지 않는다.

- 목록: 시간, 사용자 작업 종류, 프로젝트, SIM/REAL/Replay, 실행 상태, 소요 시간, 실패 단계, execution ID. 성공/실패/취소/미확정 필터와 ID 검색, 페이지네이션.
- 상세: 현재/최종 결과, 최초 오류, 후속 cleanup, 단계 트리와 병렬 구간, 성공한 단계, 늦은 응답·유실·기록 미완료, 가장 긴 단계, 선택된 함수 프로파일.
- evidence: 소스·설정 버전, 이전/후속 실행, 관련 로그의 안전한 위치 또는 인증된 제한 조회. 임의 경로 읽기 endpoint는 만들지 않는다.
- 목록/상세/export 모두 기존 product session 인증과 접근 가능한 project/owner 범위를 적용한다. execution ID를 안다는 이유만으로 접근을 허용하지 않는다. 허용된 프로젝트 간 조회는 명시 선택으로 지원하되 다른 owner/project와 bootstrap/engine 역할이 product diagnostics에 접근하지 못하게 한다. 새 별도 로그인 체계를 만들 필요는 없다.
- Export diagnostics: manifest+안전한 summary+events+참조 목록+선택된 프로파일을 로컬 파일로 저장. 파일 누락·hash 불일치·잘림은 표시한다. 파일 읽기는 root/크기/형식/재분석 지점 경계를 검사한다.
- 상태가 오래됐으면 historical/stale로 표시한다. 화면을 열거나 Export를 눌러 robot/provider/Build/Run을 호출하지 않는다. 기존 Stop과 Force STOP은 진단 화면·렌더·LLM 대기와 독립적으로 동작한다.

원본 로그와 실패 기록은 자동 정리 대상에서 제외한다. 새 진단의 회전·상한 초과 시 동작을 O1에서 수치로 고정한다. 자동 삭제나 무한 축적 대신 bounded 기록과 명시적 용량 상태를 기본으로 하고, 삭제 정책 변경은 별도 범위로 둔다.

## 8 단계별 구현과 완료 조건

### O0 경로와 기준 실패 고정

최신 AGENTS/Memory/Baseline, 이 계획과 해당 verification만 읽고 dirty 소스를 보존한다. 실행 중인 사용자 App이나 다른 작업에 중복 기동·종료하지 않는다. 기본 제품 설정과 실험 설정, 각 로그 root와 ID를 표로 만든다. 비밀값은 읽어 출력하지 않는다.

저장된 provider length/timeout, packing 실패 후 repair, INPUT_DEADLINE_EXPIRED, 최초 오류+cleanup 오류, 엔진 apply/current frame 실패의 기존 근거를 찾는다. live 재현이 필요 없는 것은 저장 자료와 오프라인 failure injection으로 시작한다. 현재 로그에서 알 수 있는 사실과 기록이 없어 알 수 없는 구간을 명시한다. 과거 Wi-Fi 문제 같은 미확정 원인을 확정하지 않는다.

완료: 정상 생성과 실패 생성의 실제 코드 경로·ID 변환·evidence 위치, 재사용할 테스트, 미측정 구간이 정리돼 있고 O1 적용 위치가 확정된다. 문서만 장기간 확장하지 않고 다음 구현으로 진행한다.

### O1 실행 기록 기반과 한 제품 흐름

versioned contract와 store, 명시 context 전달, 안전한 요약, bounded writer와 조회 API를 만든다. 실제 채팅 text-only→generation→validation/save 경로에서 성공·실패 하나씩 기록한다. 글로벌 current execution 변수에 의존하지 않는다. 프로세스/스레드 경계를 넘을 때 context를 명시 전달한다.

완료: 사용자 요청 하나를 ID로 조회하면 성공·실패 단계와 provider attempt가 연결되고, 병렬 두 요청·두 프로젝트가 섞이지 않는다. 중복 제출은 새 호출을 만들지 않는다. 저장 후 프로세스 재시작에도 조회되며 진단 유실은 표시된다.

초기 기본 상한은 metadata event 8KiB, queue 1024개와 총8MiB, chunk 8MiB, execution 64MiB, 새 diagnostics 전체512MiB로 제안한다. 원본 evidence와 센서 raw는 이 새 quota에 합치지 않는다. 종료/실패 요약의 별도 제한 공간을 두고 상한 도달 시 일반 상세 이벤트를 중단하며 누락 수를 남긴다. O0 실측으로 부적합하면 구현 전에 조정 근거와 고정된 설정을 기록한다. 무제한 queue/파일이나 과거 실패의 자동 삭제로 해결하지 않는다.

### O2 실제 제품 전체 경로 연결

기본 Nebius observation/planning/repair·기존 raw audit, scene-edit, broker/Bridge/Isaac Build·Run·Stop·frame, launcher/readiness, robot preparation/saved collection, survey/localization/goal/Loop에 같은 계약을 연결한다. 실제 sensor raw와 고속 입력을 trace 이벤트에 통째로 중복 적재하지 않는다. 현재 지원 provider의 미연결 경로는 단순 성공 처리하지 말고 최소 공통 metadata부터 연결한다.

생성과 읽기 전용 로봇 검사의 병렬 분기, 취소 뒤 늦은 응답, worker 분리, leg 전환, 두 실행의 interleaving을 검사한다. 최초 오류·cleanup·storage 실패를 별개로 보존한다. 실제 robot protocol 변경이 필요하면 additive version과 기존 field 후보 무효화 범위를 기록한다.

완료: App→provider→save→실제 Isaac과 App→합성 native worker 경로에서 원래 ID/raw/hash를 보존하며 한 실행 트리로 탐색된다. robot 미연결의 오프라인 검증을 physical PASS로 표시하지 않는다.

### O3 시간과 함수 분석

6절 timing을 실제 단계에 적용하고 기존 cProfile/소유 process metrics를 재사용한다. 저장 데이터의 로컬 validation/packing/정합처럼 재현 가능한 계산을 먼저 프로파일한다. 외부 응답 대기와 CPU 계산을 구분한다. 함수 분석 결과를 execution에서 바로 열 수 있게 한다.

완료: 지연시킨 큐, HTTP 대기, 로컬 계산 중 어느 구간이 느린지 각각 올바르게 표시한다. 같은 호스트의 monotonic 기간과 다른 호스트의 불확실성을 구분한다. logger 켜짐/꺼짐 비교로 시간·메모리·이벤트량의 영향을 측정한다. 기존 input250ms/scan200ms/segment50ms 제한을 늘려 시험을 통과시키지 않는다.

### O4 화면과 진단 묶음

7절 목록/상세/내보내기를 기존 App에 연결한다. 오류에서 실행 상세로 바로 이동하고 성공 기록도 같은 방식으로 볼 수 있게 한다. 기본 화면은 현재 질문과 한 진행 동작을 유지한다. 개발자가 API/파일을 직접 뒤져야만 조회되는 상태로 끝내지 않는다.

완료: built browser에서 실제 저장 execution의 목록 필터→상세→최초/cleanup 오류→근거→export를 확인한다. 새로고침·프로젝트 변경·동일 시간 병렬 실행·누락 파일·진단 저장 실패·키보드/좁은 화면도 확인한다. 출력은 escaped text이고 민감정보 fixture가 UI/export에서 제거된다. 권한 없는 세션/프로젝트 조회·export와 bootstrap/engine 역할 접근은 거절한다.

### O5 통합 인수와 후속 구현 착수

기존 verify_chat_sim_journey.py, verify_goal_separated_journey.py, 복합 fault/field suite를 확장한다. 별도 비슷한 runner를 계속 만들지 않는다. 기존 파일을 실행할 때는 실제 --help/옵션과 소유 프로세스 정책부터 확인한다.

최소 인수 행렬:

| 사례 | 반드시 확인할 결과 |
|---|---|
| 텍스트 생성 성공과 photo observer→planner→repair 성공 | 같은 실행, attempt 실패 보존, 최종 저장/Build/frame 구분 |
| length/invalid JSON/packing 불가/90초 timeout | 정확한 실패 단계, raw 참조, 한 repair 상한, 무한 재시도 없음 |
| timeout 뒤 늦은 완료와 사용자 취소 | original operation 미부활, 비용/evidence는 같은 attempt에 정산 |
| 일반 제품의 dispatch 전후 소유 시험 worker 종료 | 선기록 보존, pending 결과는 unknown, 재기동 시 자동 HTTP 0 |
| 동시 두 프로젝트와 생성+로봇 검사 | ID/근거/오류 혼입 없음, 한 분기 실패가 다른 결과를 지우지 않음 |
| 같은 plan 두 번 Run, wall-clock 변경과 browser reload/boot 변경 | 실행·시계 인스턴스가 분리되고 duration 왜곡/다른 기준점 빼기 없음 |
| 실제 Isaac Build·Run·Stop 및 apply/frame 실패 | current revision/receipt와 연결, old frame을 성공 증거로 사용하지 않음 |
| native 합성 입력 만료+정리 실패 | 입력/전송/수신 순서, 최초 오류와 cleanup 보존, cause unknown 구간 표시 |
| 진단 queue 포화·disk 오류·부분 파일·재시작 | bounded 자원, 누락 명시, Stop 지연 없음, 필수 raw 정책 유지 |
| 중복 클릭·reload·export·과거 replay 조회 | provider/robot/Build 재실행 0, 기존 멱등과 원본 보존 |
| credential/CSRF/bootstrap/쿠키·사진 canary와 두 종류 hash | UI·기본 export 비밀 노출 0, 원응답/보관본 hash를 정확히 구분 |
| 프로파일 비용과 장시간 Loop | 일반 실행과 profiled 실행 분리, 기존 자원 budget/정지 조건 유지 |

오프라인 대표 오류는 선택한 실행의 Diagnostics와 export만으로 최초 실패·성공 단계·후속 오류·원본 위치를 찾을 수 있어야 한다. 결손 근거는 missing으로 보이며 다른 폴더를 수작업 검색하게 만들지 않는다. 데이터만으로 네트워크/센서 원인을 구분할 수 없으면 unknown이 정답이다.

O0에서 기존 자원 예산과 비교 조건을 읽어 시험 전에 정한다. telemetry 기록 변경이 있는 최종 소스에서는 실제 경과 30분 자원 시험을 한 번 수행하고 logger on/off의 짧은 동조건 비교를 붙인다. 기존 정책보다 느슨한 값으로 바꾸지 않는다. 표본이 적은 경우 평균/최대/표본수를 보여주고 p95 등으로 안정성을 과장하지 않는다. 회귀는 관련 범위→제품 묶음 순서로 진행하며 변경이 없으면 무거운 전체 시험을 반복하지 않는다.

crash 복구 시험은 명시적으로 시험이 만든 로컬 child와 offline transport에만 적용한다. 사용자가 실행 중인 App/Isaac, 다른 작업의 프로세스, 실제 로봇을 강제 종료하지 않는다. 기존 tests/integration/test_agent_reliability.py, test_r4_bridge_api.py와 packages/twinpulse_robot_safety/tests/test_robot_journal.py의 late/unknown/queue 회귀를 확장한다.

완료 보고는 O 기능, actual Isaac, 합성 robot, 실제 LLM, physical 결과를 분리한다. fixture 기반 연결 인수는 유료 호출 없이 가능하다. 새 모델 성공률은 P2에서 측정한다. 모든 O 완료 조건을 충족하면 아래 P1으로 넘어갈 준비가 된 것이며 전체 데모 완료는 아니다.

## 9 기존 사진 생성과 라이브러리 잔여

### P1 사진 생성과 크기 및 관계 통합

대상은 core model_library.py/furniture.py/room_visuals.py/photo_quality.py, provider photo_layout.py/nebius_pipeline.py/scene_edit_provider.py, App scene_changes.py/scene_edit_proposals.py와 기존 Isaac adapter다.

1. 표준 Site2.2와 compact-photo 두 경로의 model 선택/xyz/variant/finish/관계 표현을 대조한다. 버전이 명시된 compact 확장 또는 검증된 표준 경로 중 유지할 구조를 선택하고 이유를 기록한다. 옛 1.0/1.1 저장본을 소급 해석하지 않는다.
2. floor occupancy, 물체 위 지지, 벽/천장 부착, 가구에 걸친 의복·침구를 구분한다. 같은 물체를 별도 바닥 장애물로 중복 packing하지 않는다. relation parent 존재/순환/위치·높이·방향/합법적 겹침을 검증하고 collision은 보수적으로 유지한다.
3. 방을 임의 확대하거나 keepout/누락 물체를 삭제해 검사를 통과시키지 않는다. 지원하지 않는 형상이나 부착은 정확한 missing/unsupported 항목으로 보여준다. 사진 한 장의 치수는 estimated·실측 미검증을 유지한다.
4. 실제 선택된 library model과 dimensions가 prompt/schema→typed plan→validation→preview→save→Isaac→재열기/Undo까지 유지되게 한다. 새 제약에 따른 실패와 수정 결과를 O 실행 ID에 연결한다.

완료: 같은 검토 사진의 알려진 위치/방향/지지/부착 결함, 텍스트만 입력, 다른 크기의 방·가구, mixed home/warehouse와 좁은 방 거절을 검사한다. 실제 Isaac 외형을 확인하며 collider/탑뷰의 단순화와 우측 3D 식별성을 구분한다. 미지원 관계를 사진과 일치한다고 보고하지 않는다.

### P2 실제 모델 평가와 기본 정책 결정

이전 Nemotron/Gemma, 승인된 사진 범위·endpoint·동일 ledger를 재사용한다. v330 기록은 109/219, 남은110, pending0, 누적 추정+예약 USD0.14391436/총USD1이며 실행 직전에 실제 ledger와 승인 chain을 다시 확인한다. 이는 현재 잔액 조회나 청구액 보장이 아니다. 남은 한도를 소진 목표로 삼지 않는다. 가격/가용성은 실제 재개 시 공식 자료로 확인하고 근거 없이 기존 회계를 재작성하지 않는다.

기존 H5의 12조건×2 행렬을 현재 source/policy로 재정리한다. P01 검토 사진, P02 floor hazards, P03 창고, P04 비검토 사진과 텍스트/편집/복구 조건을 구분한다. 없는 원본은 MISSING_SOURCE로 기록하고 이미 승인된 자료로 동등 조건을 구성할 수 있는지 먼저 판단한다. 새 개인 사진이나 다른 외부 전송 범위가 필요할 때만 그 부분을 요청한다.

단일 묶음의 기존 host call cap과 shared repair1, 총90초, 출력 기본4000/8000 및 명시 실험10000 한도를 보존한다. 변경 필요 시 실제 trace의 단계 시간·비용·출력 근거로 제한된 정책 변경안을 제시한다. 첫 2~3개 독립 실행으로 새 library 출력·관계 전달이 되는지 확인하고, 구조적 동일 실패면 소스 원인을 수정한 뒤 남은 행렬을 진행한다.

첫 생성 성공률, 단일 수정 후 성공률, 관계/치수 계약 통과, 실제 사진 충실도, actual App→Isaac 전체 성공률을 따로 낸다. 사람 검토 제약·compiler 파생·cached response·fixture·fresh model을 분리한다. 근거 없는 정확한 방 크기나 일반화 성공률을 만들지 않는다. 실제 텍스트·사진 각각 최소 한 통과 후보는 새 실제 호출에서 저장된 동일 결과로 실제 chat/Isaac 생성·이동·Stop·재열기까지 이어진다.

기존 H5의 제안 기준인 첫 시도 제품 작업22/24 이상·허용 수정 후23/24 이상을 유지한다. 필수 T01/P01 생성·Isaac 표시, 적용 결과의 계약 준수, 원본 보존, 중복 실행 방지와 Stop은 모두 충족해야 한다. T08의 근거 있는 질문/거절은 해당 작업의 기대 성공이고, 실제 모델을 호출하지 않은 결정적 처리는 모델 성공률 분모에서 제외한다. 작은 데모 행렬의 목표이며 장기 신뢰도 보장이 아니다.

기본 thinking, compact/no-thinking 중 제품 기본으로 채택할 정책을 명시적으로 기록하고 기존 실행 설정과 UI가 그 정책을 사용하는지 확인한다. 실험 플래그를 켠 개발자 runner만 성공하고 원클릭 제품은 실패하는 상태로 완료 처리하지 않는다. 기존 H5 수치 목표 미달은 미달로 보고하며 후속 표본 때문에 기존 실패를 분모에서 빼지 않는다.

## 10 기존 제품 흐름과 최종 패키지 잔여

### P3 사용자 흐름의 빈칸 인수

상위 [채팅 데모 계획](TWINPULSE_CHAT_DRIVEN_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-05.md)의 사용자 원문·UI 계약·D01~D12를 그대로 유지한다. 이미 통과한 기능을 재개발하지 말고 최신 소스의 근거가 없는 항목을 채운다.

- 원클릭 launch의 진행·필수 항목·허용된 자가 복구·실패 후 재개, 텍스트 단독 SIM, 사진 선택 입력, 한 질문/한 진행 동작, 실제 진행 표시.
- New/Add/Change 원본 보존, 자연어 staging과 미배치 목록, 기존 위치·크기·높이·회전 편집. 새 생활 물체에서 drag/회전이 실제로 저장→Isaac→Undo/재열기에 반영되는지 확인. 숫자 입력 시험만으로 drag PASS를 기록하지 않는다.
- 다른 집·창고의 환경 선택, 현재 지원 robot catalog와 실제 구동 모델의 일치. Burger만 검증됐으면 임의 로봇 자동 호환을 주장하지 않는다.
- REAL 연결 검사와 생성의 병렬 상태, 필요할 때만 한 안전 초기화/주행검증 카드, 종료·취소·재시작·프로젝트 변경 시 옛 승인 비재사용.
- current pose/scan·5초 요약·다음 waypoint·battery 추정·Loop/Stop. stale/unknown을 정상 현재값으로 표시하지 않는다.

P3는 이 항목들의 체크리스트와 최신 근거를 채우는 단계다. H/C 전체를 다시 처음부터 만들지 않는다. 이미 구현된 torque-only 초기화와 single-step UI가 있으면 해당 실제 경로를 검증한다.

### P4 배포 가능한 동일 소스 인수

기존 release builder와 verify_packaged_automatic_demo.py를 사용해 checkout 밖 새 데이터 경로에서 최종 package만으로 검사한다. 원본 사진·raw·credential은 배포본에 포함하지 않는다. 진단 조회/export에 필요한 소스와 Web build가 포함됐는지 확인한다.

SIM 정상, REAL 합성 정상, timeout/cleanup/storage/stale/Stop 복합 실패를 built Web/API/실제 Isaac에서 연결한다. O5 이후 control/렌더/저장에 영향 주는 수정이 있으면 영향 범위 자원 시험과 필요한 인수를 갱신한다. 최종 source/웹/engine/package 해시를 묶고, 기존 30분 결과나 이전 package PASS를 새 release 증거로 복사하지 않는다.

완료: D01~D12 각 항목에 구현·오프라인·actual Isaac·actual provider·현장 상태와 근거가 있다. 현장 미실행 때문에 가능한 오프라인 인수를 중단하지 않는다. 여기까지 통과하면 F0/F1에 전달할 동일 후보를 고정한다.

## 11 로봇이 필요한 시점과 한 번의 현장 시험

### F0 로봇을 켜기 전에 끝낼 준비

O2로 source가 바뀌면 기존 후보의 source/runner/archive와 실제 배포 release가 달라질 수 있다. 기존 run_robot_field_suite.py의 prepare-field-candidate와 관련 preflight를 갱신하고 exact hash·driver binary/library·의존성·source import·원본 반출·전송 재개·오류 묶음 계약을 확인한다. 과거 stopped/qualified 결과를 새 release에 복사하지 않는다.

필요한 데이터 목록에는 현재 boot/release, corrected scan의 시각과 frame, 움직이는 odom/TF, sensor mounting/footprint·좌표축·타이밍 근거, 배터리/정지·cleanup, room reference/정합의 근거를 넣는다. 이미 유효한 근거는 재사용하고 없는 값만 missing으로 남긴다. motor load는 현재 UNSUPPORTED이므로 progress stall을 토크 측정이라고 표시하지 않는다.

현장 runner는 기존 한 파일 진입점을 유지한다. 의존 단계가 실패하면 이동은 막되 안전한 독립 상태 조회·원본 반출은 가능한 범위에서 끝낸다. 단계별 자동 진행·정확한 실패 원인·실행 ID·재실행 가능한 단계가 준비돼야 한다. 사용자가 프로그램 버튼을 누르는 경로와 runner가 같은 준비 서비스를 소비하는지 검사한다.

F0 완료와 현장 승인 전에는 로봇 전원이 필요하지 않다. 마지막 로봇 관측이나 오래된 감독 동의를 새 이동 승인으로 사용하지 않는다.

### F1 승인된 현장 세션

순서는 연결 및 현재 상태→필요한 안전 초기화/Motor OFF readback→현재 boot/release의 필요한 정지시험→corrected LiDAR의 stationary/moving scan·odom·TF와 정리→실측/방 기준 등록→조사·정합→같은 route의 Isaac 시연→짧은 목표·Stop→통과한 짧은 왕복이다. 실제 dependency gate에 따라 독립 수집과 이동 단계를 구분한다.

같은 세션에서 execution/attempt/session/boot/release를 연결하고 raw를 PC로 반출해 로봇 OFF 후 분석 가능하게 한다. 실패 시 가능한 독립 진단은 끝내며, 안전상 재시도가 불가능한 이동을 자동 반복하지 않는다. 새 근거가 필요한 최소 현장 확인만 묻는다. 변경된 시작 위치·수동 옮김·대칭 모호성은 현재 관측으로 재정합하고 저장 경로를 맹목 재생하지 않는다.

정지/scan200ms/input250ms/segment50ms/자율 .03m/s·.20rad/s/worker45s와 기존 실제 임무 잠금을 유지한다. 수동 .08m/s 설정을 자율 한도로 전이하지 않는다. 현장 검증 전에는 전원만 켜면 전체 데모 완료라고 보장하지 않는다.

## 12 이번 순서의 선행조건이 아닌 장기 항목

회사 PC cold 설치·환경 호환성 인수, 과거 M2-D 치수 도면의 높이 오독, 일반 임의 사진의 정밀 복원, 다기종 로봇 실제 구동, 음성 입력, GPU 서버 배포, RL/Nav2 최적화, 장기 연구는 기존 backlog로 보존한다. 개인 PC의 통합 진단·현재 방 데모를 시작하기 위해 모두 먼저 할 필요는 없다. 최종 제출 규정·Nebius 사용 요건은 제출 준비 때 공식 근거로 다시 확인하며 이번 계획으로 충족을 선언하지 않는다.

## 13 기록과 6.1 Sol에게 전달할 실행 지시

각 완료 묶음에는 변경 파일/기존 ID 연결표, 실행·입력·source·설정 식별, 실제 결과, 실패/미측정/원본 위치, profiler 적용 범위·측정 비용, 관련 회귀, UI/actual Isaac 증거, 정확한 다음 단계와 외부 blocker를 남긴다. Baseline/Memory를 함께 갱신하고 과거 원본과 실패는 보존한다. O에서는 로깅이 되는지, P에서는 생성·제품 품질이 되는지, F에서는 실제 로봇이 되는지를 각각 판정한다.

> 최신 AGENTS와 Memory/Baseline, 이 문서를 읽고 O0→O1→O2→O3→O4→O5 순서로 통합 진단을 실제 제품에 구현하라. 기존 기본 Nebius audit·session raw·broker/engine receipt를 재사용하고 사용자 실행 하나의 성공·실패·수정·취소를 연결하라. 단계 대기/처리 시간과 제한된 함수 프로파일을 실제로 측정하고, built App에서 실행 검색·오류/근거 확인·진단 내보내기가 되게 하라. 정상 채팅을 개발 패널로 바꾸지 말고 단일 질문/행동과 Stop을 보존하라. 저장소 mock/문서만 늘리거나 ID만 추가한 상태로 끝내지 마라. 각 묶음을 관련 회귀·제품 인수·기록까지 마친 뒤 연속 진행하라. 통합 진단 완료 후에는 이 계획의 P1 사진/library/관계 연결, P2 실제 LLM 평가·기본 정책, P3 제품 잔여, P4 최종 패키지, F0 현장 준비 순서로 남은 작업을 처리하라. 실제 추론은 보존된 승인 범위와 ledger 잔여를 확인해 사용하고 새 비용·전송 범위를 만들지 마라. 로봇 현장 승인 전 SSH·센서·모터·배포를 하지 말고 F1만 현장 대기로 남겨라. 독립 작업은 외부 blocker 때문에 중단하지 마라. v1/v2 원본/hash/dirty/실패·실물 guard를 보존하고 실제 runtime 없이 Isaac PASS, 실측 없이 physical PASS, 추정 치수로 정확한 복원을 선언하지 마라. 새 설치·구독·시스템 변경·commit/push·자동 예약 생성은 이 계획에 포함하지 않는다.

현재 계획 작성 중 신규 구현·테스트·외부 추론·로봇 실행은 없었다. 기존 소스와 기록을 읽어 우선순위와 완료 조건을 정했으며, 문서 검토용 읽기 전용 보조 검토를 사용했다.
