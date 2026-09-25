# GPT 5.6 Sol 실행 지침 — 검증 복구부터 해커톤 vertical slice까지

- 작성일: 2026-09-22 / 상태: **계획, 아직 구현 안 함**.
- 기준 root: `C:\Users\jaewo\Documents\TwinPulse`.
- 읽을 문서: [종합 검토 A-01~A-10](TWINPULSE_ASTRA_REVIEW_2026-09-22.md), [TurtleBot 실험 B0~B9](TWINPULSE_TURTLEBOT3_EXPERIMENT_PLAN.md).
- 기존 R0~R10 번호는 유지한다. 아래 S0~S9는 이번 검토의 작업 묶음이며 R 단계를 완료로 바꾸는 우회 경로가 아니다.
- 사용자에게 선택받은 **한 하위 단계**만 진행한다. 이 문서의 존재는 설치·과금·실물·push 승인이 아니다.

## 0. Sol의 필수 작업 규칙

### 시작 / 중단 / 재개

1. AGENTS.md, PROJECT_MEMORY 최신 우선 블록, 이 문서의 선택된 단계, 해당 checkpoint를 읽는다. 인수인계 첫 회에는 Baseline 전체를 읽는다. 이후 매번 모든 과거 문서/대화/거대한 로그를 재독하지 않는다.
2. `git status --short`, HEAD, 현재 diff 파일 목록과 checkpoint의 소스 hash를 비교한다. 미커밋 사용자 변경을 rollback/덮어쓰기하지 않는다.
3. 한 하위 단계마다 **재현 시험 → 최소 수정 → 대상 시험 → 증거 저장 → checkpoint → 사용자 보고** 순서를 지킨다.
4. 실행 전 명령·예상 상한·산출물 경로를 정한다. 출력 없이 무기한 대기하지 않는다. launcher/engine/test 각각 timeout과 소유 프로세스 정리 정책을 가진다.
5. 실패한 동일 expensive job을 원인 분석 없이 다시 시작하지 않는다. 최초 실패 artifact를 보존하고 좁은 재현 시험으로 줄인다.
6. 끝에는 반드시 “완료한 범위 / PASS·FAIL·NOT_RUN / 남은 blocker / 다음 명령 또는 결정”을 보고한다. 테스트가 끝났는데 보고 없이 계속 새 기능에 진입하지 않는다.

### 토큰 한도 대응

- 남은 한도를 정확히 알 수 있다고 가정하지 않는다. **편집 또는 유한 테스트 한 묶음이 끝날 때마다** checkpoint를 갱신한다.
- 한 대화에서 S1a~S9를 통째로 실행하지 않는다. 승인된 하위 단계에 집중한다. 실패 분석과 문서 갱신 공간을 남긴다.
- 거대한 stdout 대신 요약 JSON/exit code/error tail을 사용한다. 원본은 artifacts에 보존한다.
- Isaac 전체 suite는 매 작은 Python 수정마다 실행하지 않는다. 관련 pure regression → 대상 actual test → milestone full suite 순서로 올린다.
- 유료 generation은 request/input hash/job ID/started 상태를 **호출 전에** durable 저장한다. 중단 후 응답 여부 불명인 job은 `outcome_unknown`으로 취급하고 자동 재호출 금지. 제공자가 idempotency를 지원하는지 확인한 경우에만 그 계약을 따른다.
- 중단됐다고 기존 owned engine을 무조건 죽이지 않는다. PID+시작시각+launch ID+현재 health를 확인하고 자신의 세션만 처리한다. 실물 motion은 작업/연결 상실 시 로봇 현장의 watchdog으로 독립 정지해야 한다.

### 체크포인트 계약

단계 시작 시 `docs/planning/TWINPULSE_EXECUTION_CHECKPOINT.md`를 생성하거나 기존 내용을 이어 쓴다. 요약은 Git 관리, 큰 증거는 `artifacts/runs/<unique-run-id>/`에 둔다. 비밀값·회사 원본은 기록하지 않는다.

```yaml
schema_version: '1.0'
step: S1a
status: IN_PROGRESS # PASS / FAIL / BLOCKED / NOT_RUN도 허용
root: C:/Users/jaewo/Documents/TwinPulse
head_commit: <actual HEAD>
dirty_source_manifest: <path + sha256; secret files excluded>
last_completed_action: <구체적인 한 작업>
modified_files: []
evidence:
  - run_id: <unique id>
    command: <secret-free exact command>
    exit_code: <number or not_finished>
    result: <PASS/FAIL/NOT_RUN>
    report: <relative artifact path>
owned_processes: [] # PID/start_time/launch_id/state_dir; secrets 없음
paid_requests: [] # provider/model/job/request_id/status/cost, API key 없음
blocker: null
next_action: <한 문장으로 실행 가능한 바로 다음 작업>
do_not_repeat: [] # 이미 끝낸 시험/과금/설치
required_approval: null
```

전체 상태는 단계별 sub-gate의 conjunction이다. `PASS 8개 + NOT_RUN 1개`는 해당 milestone 완료가 아니다. 문서에는 마지막 성공뿐 아니라 최신 실패도 기록한다.

### 현재 저장소에 존재하는 검증 진입점

아래는 향후 선택한 단계의 테스트 명령 예시이며, 문서 작성 중 실행했다는 뜻이 아니다. 먼저 interpreter/dependency 및 `--help`를 확인하고 실제 사용 경로를 checkpoint에 남긴다. `python`은 승인된 일반 Python/격리 venv여야 하며 Isaac bundled Python과 임의로 교체하지 않는다.

```powershell
Set-Location C:\Users\jaewo\Documents\TwinPulse
python -m unittest discover -s tests/integration -p test_r6_process_manager.py -v
python -m unittest discover -s tests/integration -p test_r5_product_api.py -v
```

React는 `apps/twinpulse-web`에서 설치된 runner로 `npm run test`와 `npm run build`를 사용한다. npm이 PATH에 없으면 승인된 기존 runtime 경로를 찾아 기록하며, 시스템 재설치부터 하지 않는다.

```powershell
# 실제 Isaac 실행이 승인된 단계에 한함. 고유 artifact-dir를 지정할 것.
python scripts/verify_app_e2e.py --help
# milestone 최종 회귀; 작은 수정마다 반복하지 않음
.\scripts\verify_twinpulse.ps1 -IsaacRoot C:\isaacsim -RunR6
```

명령 실패가 권한/환경 때문이면 코드 회귀 실패와 구분한다. Python 임시 폴더 ACL로 테스트 fixture 생성이 차단되면 승인된 scratch root와 적절한 권한을 확인하고, 실패를 숨기거나 사용자 runtime 폴더를 대체 scratch로 사용하지 않는다.

## 1. 유지할 아키텍처와 금지할 단축

```text
React UI
  └─ Local API adapter
      └─ ApplicationService (입력/생성/저장/검토의 단일 주체)
          ├─ Provider adapter → NVIDIA model on Nebius (고수준 제안)
          ├─ Typed plan validator + allowlisted registry
          ├─ Project/artifact store (비밀 제외)
          └─ Command broker (revision/session/lease/idempotency)
              ├─ Isaac adapter → compiler/runtime/센서
              └─ 향후 ROS mission adapter → 현장 Nav2 → safety supervisor → driver
```

- LLM 출력은 데이터와 allowlisted intent다. Python/shell/URDF/질량/관성/임의 속도 안전한계를 생성해 실행하지 않는다.
- 외부 MCP는 필요할 때 같은 계약을 노출하는 transport adapter다. 이번 핵심 문제를 해결하기 위해 외부 MCP 서버가 필수인 것은 아니다.
- snapshot의 `generated`, `validated`, `applied`, `running`, `completed`를 구분한다. evidence capture 실패도 generation 실패와 별도다.
- SceneSpec/RobotProfile/Mission/RunResult의 책임을 분리한다. 실물은 typed mission goal과 승인된 parameter artifact만 받는다.
- 인증 제거, mock으로 fallback, 이전 scene screenshot 재사용, runtime 안전 gate 삭제로 테스트를 녹색으로 만들지 않는다.

## 2. 단계 지도

| 새 묶음 | 연결되는 기존 단계 | 목표 | 선행 |
|---|---|---|---|
| S0 | R6 audit | snapshot/증거/재현 기준선 | 없음 |
| S1a~d | R6 잔여 | launcher·capture·session 복구 | S0 |
| S2a~d | R3→R5 실제 통합 | live application 경로와 입력/secret 보강 | S1a; S1b는 E2E 전 필요 |
| S3a~c | provider/M4 준비 | Nebius NVIDIA 실질 호출 | S2b/c, 비용 승인 |
| S4a~b | R7 | scene/mission 분리 | S2 |
| S5a~c | R8/R9 최소 범위 | 명시 치수·scan correction·재현 | S4; live는 S3 |
| S6a~b | M4 | RT GPU cloud smoke/작은 반복 eval | S1/S3, 별도 승인 |
| S7 | M5/M7 | TurtleBot B0~B8 | B 단계별 gate |
| S8 | R10 최소+M7 평가 | sim/real 비교 보고서 | S5/S7 |
| S9 | 제출 | reproducible 공개 release/영상 | 제출 필수 gate |

S3a의 공식 capability 조사와 B0 inventory는 초기에 할 수 있다. cloud/물리/LLM을 한 번에 디버깅하지 않는다. 이 의존성은 동시 sub-agent 실행 지시가 아니다.

## S0 — 현재 상태를 잃지 않는 검토 기준선

**수정 대상:** checkpoint와 검증 요약만. 제품 소스 수정 없음.

1. HEAD/dirty 파일 목록, Python/Node/Isaac 버전, 마지막 두 run ID를 기록한다. R6 untracked 소스 누락을 확인한다.
2. `20260922-100347`와 `20260922-102341`의 result/manifest를 읽어 earlier PASS/latest FAIL을 보존한다. full suite를 다시 돌릴 필요 없음.
3. 종합 검토의 격리 probe를 repository integration regression으로 옮길 계획을 정한다. 이 단계에서는 red test 작성/실행까지 가능하되 fix와 혼합하지 않는다.
4. actual process/state-dir 사용 없이 가짜 artifact/temp storage로 A-01/A-02/A-04를 재현한다.

**완료:** 세 재현의 actual output, 미실행 항목, 파일 목록이 checkpoint에 있음. 사용자 dirty 작업을 전부 commit하거나 push하지 않음.

## S1 — 자동 실행/관찰 신뢰성 복구

### S1a: 소유권 있는 종료

**대상:** `packages/twinpulse_app/src/twinpulse_app/process_manager.py`, `scripts/twinpulse_launcher.py`, `tests/integration/test_r6_process_manager.py`.

- launcher lock를 얻지 못한 manager의 stop은 어떤 shared runtime 파일도 변경하지 않아야 한다.
- launch instance ID/owner PID/start time을 runtime 상태에 넣는다. engine stop 요청은 같은 instance를 대상으로 해야 한다.
- 중복 실행 거절, validation 실패, backend spawn 실패, engine spawn 실패, readiness timeout, 정상 종료, 중복 stop을 구분한다.
- lock read 오류/작성 중/접근 거부는 “stale”로 즉시 삭제하지 않는다. 작은 bounded retry 후 진단을 반환한다.
- 후손 프로세스 종료 문제는 별도 S1d로 분리하되 global taskkill 금지.

**필수 red→green 테스트:** 첫 lock를 살아 있는 test PID로 구성 → 두 번째 launcher 실패 → finally stop → 첫 stop-file 미생성, ready/status byte 불변, lock 보존. 두 번 stop idempotent. 소유 실패 세션의 자식만 cleanup.

**종료점:** pure manager 회귀 PASS, 아직 실제 duplicate Isaac 시험을 하지 않았다면 명시. 다음 S1b 또는 사용자가 고른 단계로 인계.

### S1b: 캡처 완료 계약

**대상:** `scripts/twinpulse_engine_host.py`, `scripts/verify_app_e2e.py`, capture 전용 test helper(신규 가능), R6 검증 문서.

1. capture request 시각/frame/stage epoch/applied revision/camera를 기록한다. task return/파일 첫 관측/크기 안정/decode 완료 timestamp를 별도로 기록한다.
2. Kit update loop를 막지 않는 finite polling을 사용한다. 초기 제안 deadline 15초, 재캡처 최대 1회; 실제 현장 지연을 측정해 명시 설정으로 조정한다. 무한 frame count 금지.
3. pending → success/timeout/decoder error를 구분하고, 실패 파일을 다른 run의 정상 PNG로 대체하지 않는다.
4. 결과 저장은 atomic. shutdown 시 동일 deadline 내에서 pending만 마무리하고, 이미 실패한 원인을 삭제하지 않는다.
5. unit fake capture: 늦은 파일/부분 파일/빈 파일/black frame/없는 viewport/예외/영원히 안 끝나는 future/중간 stage revision 변경.

**actual gate:** 승인된 로컬 Isaac에서 새 run 3회. 각 회 `Build → capture → Run → Pause → Reset → Focus → 종료`, browser/실제 scene revision/완전 decode 모두 PASS. 과거 실패 run은 수정하지 않는다. 실패하면 동일 경로 instrumentation을 보고 다음 회를 결정.

### S1c: 인증 수명과 안전 재열기

**대상:** `api.py`, `apps/twinpulse-web/src/api.ts`, React 상태, API/browser tests.

- active renewal과 absolute lifetime을 정하고 cookie/server expiry를 일치시킨다. 만료/새 탭/reload UX를 정의한다.
- 기존 owner에게서 한 번만 쓸 수 있는 새 bootstrap을 받는 경로 또는 안전한 재열기를 구현한다. URL/로그/스크린샷에 bootstrap secret을 남기지 않는다.
- 부정 origin/CSRF/role/replayed bootstrap 차단 유지. stale session의 command 재전송 금지.
- 테스트는 fake clock으로 TTL 전후, 새 탭과 refresh는 browser로 확인한다. 30분 실시간 sleep은 필요 없다.

### S1d: 실제 프로세스 경계/상태 격리

- fake wrapper child로 Windows Job Object/동등한 tree ownership을 먼저 검증. 이후 실제 owned Isaac을 대상으로 graceful와 강제 fallback을 확인한다.
- 기본 사용자 credential/settings 대신 테스트 주입 store와 고유 state dir를 사용한다. API/backend/engine별 settings root 계약을 명확히 한다.
- 엔진 heartbeat가 stale이면 PID가 살아 있어도 `unresponsive` 상태를 보고하고 Run을 막는다. 실패 시 traceback/log tail은 secret filter 후 제공.
- R6 전체 종료는 저장된 M2-C 세 결과 replay, fresh clone, 실제 live App 등 전체 gate가 닫혔을 때만. S1 통과 자체는 R6 전체 PASS 아님.

## S2 — 웹 App의 실제 생성 연결

### S2a: 입력 검사와 정확한 측정 유지

**대상:** `product_workflow.py`, `application.py::prepare_input`, provider measurement parser, `test_r5_product_api.py`.

- image header 추정 함수를 완전한 bounded decoder로 교체. 추가 라이브러리는 isolated dependency/lock/license 계획과 승인 후 설치한다.
- sidecar의 실제 typed constraints/원본 hash를 immutable input에 포함한다. 개수만 유지하지 않는다.
- 입력 bytes/hash/prompt/kind/measurement/profile/settings/도구 catalog revision이 동일한 generation snapshot을 가리키도록 R1 계약을 재사용한다.
- 이미지 file name/path를 실행/임의 filesystem 접근 지시로 취급하지 않는다. 공개 artifact에 원본 이미지 보관 여부는 입력 권리에 따라 결정.
- **gate:** A-04의 정상/비정상 입력 corpus, sidecar wrong-image/잘못된 dimensions, oversized request, 한국어 prompt 통과/오류 설명.

### S2b: ApplicationService 단일 소유자

**대상:** `scripts/twinpulse_backend.py`, `api.py`, `product_workflow.py`, `application.py`, `project_store.py`, `command_broker.py`, React types/API.

1. `ProductWorkflow`를 presentation adapter로 줄이거나 제거하고 R3 service를 composition root에서 생성한다. 기존 service를 통째로 재작성하지 않는다.
2. `POST /v1/product/generation`은 현재 immutable input으로 실제 gateway job을 만든다. fixture mode는 테스트용 명시 flag로만 생성한다. live 오류 시 fixture fallback 금지.
3. HTTP/Kit thread와 generation I/O 분리. 하나의 generation job, finite timeout/cancel, 늦은 응답 폐기, shutdown cancellation을 계약으로 둔다.
4. provider 결과를 semantic/measurement 검증 후 등록된 artifact로 승격. 실제 tool receipt 개수/plan hash를 UI에 반환한다.
5. Review acknowledgment는 input+draft revision에 귀속. 입력/설정/profile 변경 후 이전 acknowledgment로 Build 금지. 엔진의 applied revision은 backend draft와 별도로 유지.
6. 재시작 시 마지막 **완전 저장된** project/receipt만 복원한다. partial/corrupt/legacy 파일은 명확한 검토 상태로 표시. OS credential은 project export에 넣지 않는다.

**회귀 표:**

| 시험 | 예상 결과 |
|---|---|
| fake gateway가 입력 A/B에 서로 다른 plan 반환 | A/B의 draft 및 broker artifact 다름 |
| 생성 도중 이미지/문구/settings/profile 변경 | 이전 result가 현재 draft가 되지 않음 |
| invalid JSON/schema/measurement/unsupported tool | 정확한 structured error, Build 불가 |
| cancel 후 지연 success | 취소 유지, provider 비용 사실은 숨기지 않음 |
| restart 뒤 receipt 입력 hash 불일치 | explicit restore review, 자동 Build 불가 |
| Generate 실패 뒤 기존 applied scene 있음 | 기존 scene 보존, 새 성공처럼 표시하지 않음 |
| draft ack 후 stage reload | 이전 stage receipt로 Run 불가 |

**금지:** pure fake 시험을 multimodal inference PASS로 보고, 선택한 이미지를 gateway에 전달하지 않고 UI 이름만 표시.

### S2c: provider별 secret/settings

**대상:** `settings.py`, `credentials.py`, API Settings, provider transport, tests.

- ProviderSettings version을 올려 adapter kind/provider profile/endpoint/capabilities/credential reference를 구분한다.
- 기존 default target migration은 OpenAI profile에만 귀속시킨다. origin/protocol 변경 시 새 키 연결 또는 명시 재승인이 필요하다. `empty key = keep`는 같은 profile에서만 유지한다.
- 키 사용 없이 `configured` 확인이 가능하도록 한다. Settings saved / capability checked / live request succeeded는 별개 표시.
- unique temp + atomic replace + serialization으로 concurrent settings save 처리. credential 저장 실패/설정 저장 실패/손상 JSON의 복구와 오류 code 시험.
- mock secret canary로 API response/log/project export/traceback에 포함되지 않는지 테스트한다. 사용자 실제 키 열람/출력 금지.

### S2d: 과거 결과 replay와 실제 App smoke 분리

- 먼저 M2-C 저장 결과 세 개를 새 service→broker→manager→Isaac 경로로 재생한다. API 호출 0회, source=`replay` 명시.
- 각 결과 input/plan hash, object/tool 수, receipt, 실제 scene 차이, Run/Pause/중간Reset/완료Reset을 기록한다.
- live gate는 비용 승인 뒤 하나의 자체 촬영 또는 권리 확보 이미지부터 시작한다. image bytes 전달, provider/model/request ID, schema 검증, plan hash, build revision, capture를 연결.
- 서로 다른 이미지에 대해 hash만 다른 것이 아니라 관측/배치 차이를 설명한다. 첫 호출이 실패하면 원인별 진단 후 멈춘다. 3-image live gate의 추가 호출은 승인된 총 횟수 안에서만.
- 여기까지 통과해야 “새 App이 기존 실제 이미지 생성 경로를 대체했다”는 주장이 가능하다.

## S3 — Nebius/NVIDIA 핵심 경로

### S3a: 호출 없는 capability/배포 선택

상태: **2026-09-24 PASS — 호출 없는 선택 범위만 완료.** 계정의 public `/v1/models`에는 Vision `google/gemma-3-27b-it`, text planner `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, Vision fallback `openbmb/MiniCPM-V-4_5`가 확인됐다. `nvidia/Cosmos3-Super-Reasoner`는 관찰된 계정 UI에서 Dedicated H100 배포 대상이므로 기본 경로에서 제외했다. `Gemma observation → Nemotron constrained plan → local validation`과 `nebius_chat_completions_pipeline`을 ADR로 확정했으며 live/유료 요청과 endpoint 생성은 0회다. 상세 근거는 `docs/verification/S3a-nebius-provider-selection.md`.

- 공식 catalog와 계정 quota를 구분해 기록. exact model ID/revision/license/modality/context/output schema/tool calling/가격/region을 표로 만든다.
- NVIDIA model이 무엇을 결정하는지 ADR 작성. vision 불가면 VLM observations→NVIDIA constrained planner로 분리하되 NVIDIA 역할을 장식적 요약에 한정하지 않음.
- Responses, Chat Completions, custom endpoint 중 실제 protocol에 맞는 adapter 선택. 예상 schema/features 미지원이면 local validator+structured rejection을 유지한다.

### S3b: fake transport 먼저

상태: **2026-09-25 PASS — fake transport/local validation 범위만 완료.** Gemma observation → Nemotron full constrained plan의 2단계 Chat Completions adapter, typed failure/cancel/late-result/no-retry, bounded provenance와 secret/data-URI 차단을 검증했다. official non-Isaac `20260925-000253` PASS. live 요청·Isaac·endpoint 생성은 0회이며 product settings/backend 연결과 finite live gate는 S3c에 남는다. 상세 근거는 `docs/verification/S3b-nebius-fake-transport.md`.

- 새 provider adapter는 GenerationGateway/result 계약을 유지한다. text/image encoding, strict schema 또는 typed tool calls, refusal/truncation/timeout/429/5xx/cancel/late response/redirect/cost receipt 시험.
- model `reasoning` 옵션 이름·지원값을 OpenAI와 같다고 가정하지 않음. request/response에서 안전한 trace만 남긴다.
- API key/생성 이미지 data URI/Authorization을 로그에 넣지 않는다. image SHA와 bytes count로 증명한다.

### S3c: 승인된 유한 live 시험

상태: **2026-09-25 PARTIAL — product wiring PASS, live gate NOT RUN.** settings schema 3.0, exact Nebius preset, backend composition과 React 선택 UI를 무호출로 연결했다. official non-Isaac `20260925-002818` PASS. live 단계는 아래 예산/요청 한도의 사용자 명시 승인 후에만 진행한다. 상세 근거는 `docs/verification/S3c-product-wiring.md`.

- 사전 합의: provider/model, 최대 요청 수, token/output 상한, 총금액, timeout, 자동 retry 0.
- 한 작은 계획을 end-to-end 생성/검증/build하고 Nebius 호출 증거와 NVIDIA model 사용 증거를 남긴다.
- acceptance: NVIDIA가 산출한 실제 plan/결정을 validator가 검사했고 UI/Isaac 결과와 연결됨. model 없는 replay는 별도 결과.
- 후속 변경은 saved response replay로 검증하고, 모델 변경/품질 확인 필요 시에만 새 유료 run.

## S4 — scene와 navigation 분리 (기존 R7)

### S4a: 계약과 unit test

- core SceneSpec validation에서 +X 직선 제약을 scene validity와 분리하되 controller capability gate로 이동한다.
- `scene_valid`, `robot_compatible`, `mission_supported`, `run_allowed`, reason code를 snapshot에 분리.
- 정상 L형 장면/역방향 goal/막힌 route에서도 scene 검토·Build는 가능할 수 있지만 현재 controller Run은 거절해야 한다. collider/단위/소유권/범위 검사 유지.
- scene-only 계약 변경이 기존 schema/fixture/receipt를 깨는 경우 version migration을 먼저 정의. task를 dummy +X로 조용히 만들어 넣지 않음.

### S4b: 실제 Isaac capability gate

- L형 배치를 Build해 올바른 geometry를 확인하고 generic +X controller Run이 명확한 unsupported로 끝나는지 시험.
- 기존 직선 회귀는 그대로 PASS해야 한다. 이 단계만으로 Nav2 회피를 구현했다고 하지 않음.

## S5 — 최소 보정/도면 검증 (기존 R8/R9의 선택 범위)

### S5a: provenance와 검토

- object stable ID에 dimension/position의 source와 units를 붙인다. photo 추정, drawing 관측, 사용자 명시, scan 측정을 구분한다.
- 누락 높이는 2D LiDAR로 측정됐다고 하지 않는다. 저해상도 치수는 unknown/needs review.
- observation extractor와 tool planner의 출력 책임을 분리. 두 LLM 응답의 일치를 독립 ground truth로 부르지 않음.

### S5b: 하나의 안전한 편집

- 최소 기능: 선택한 장애물 위치/랙 치수 수정, diff preview, explicit apply, revision 증가, 이전 run invalidation, undo.
- expected revision/stable ID/허용 필드/typed units 필요. model-generated JSON patch를 임의 path에 적용하지 않음.
- 실제 USD 변경된 대상만/외부 prim 보존/undo/동시 stale edit regression.

### S5c: held-out 평가

- 기존 27/29 도면과 새 단위/방향/랙 높이/통로 폭이 다른 held-out 2~3개. test ground truth는 provider input과 분리해 blind extraction 점수와 constrained generation 점수를 따로 계산한다.
- 치수, object association, 통로 clear width, orientation, collider/route viability를 별도 점수로 낸다. 잘못 읽은 입력이 Build 차단된 것은 안전 gate PASS, 판독 정확도 PASS 아님.
- live 평가 비용 상한 없이 반복하지 않음. “범용 도면 정확한 3D 복원”이라고 확대하지 않음.

## S6 — Nebius full Isaac 서버 검증

### S6a: 유료 실행 이전

- 계정 quota/region/GPU RT 지원/driver/Isaac 버전/container 또는 standalone/license/storage/총비용을 확인한다. H100 등의 VRAM 크기만으로 renderer 호환을 결정하지 않음.
- 승인 받을 내용: 최대 GPU 시간/금액, volume 크기와 보존 기간, 실패 시 자동 종료, 공개 포트 유무. 기본은 inbound 비공개 job+artifact 반환.
- 버전/asset/dependency lock을 만들고 로컬 fingerprint와 서버 환경 차이를 기록한다. Windows API/credential dependency는 platform adapter로 격리.

### S6b: 작은 smoke → 같은 세 결과 replay

- 먼저 renderer 1frame+physics 짧은 run 하나. PASS 후 저장된 세 plan batch를 실행한다. 첫 smoke와 반복 eval의 예산을 분리.
- cloud run은 job timeout/finalizer가 있고 비용/시작/종료/삭제 resource 목록을 기록한다. 토큰 중단 후에도 비용이 무기한 발생하지 않도록 platform TTL을 검증.
- local/cloud scene/profile/units와 동일 metric definition. 동일 timestep/seed/config를 기록하되 bitwise physics 일치를 요구하지 않음.
- 결과 다운로드/검증 뒤 승인한 scratch만 정리한다. 공유 volume/다른 VM 삭제 금지.

## S7 — TurtleBot 통합

[별도 B0~B9 계획](TWINPULSE_TURTLEBOT3_EXPERIMENT_PLAN.md)이 실행 기준이다. 로봇 실험마다 local operator 승인이 필요하다.

- B0~B4는 TwinPulse와 독립된 기준선 확보.
- B5~B6은 실제 profile/센서/ROS/Nav2 simulation 연결.
- B7은 read-only 실물 관측과 shadow/replay; B8이 최초 제한 real mission.
- 2WD는 유지하되 mass/inertia/support/footprint/scan frame은 실제 모델로 교정.
- Sim/Replay/LiveObserve/LiveControl은 enum뿐 아니라 command sink 권한이 다르다. Replay가 real `/cmd_vel`을 publish할 수 없게 구성/테스트한다.

## S8 — 차이를 보여주는 비교 보고서

- 데이터 계약: run ID, software/profile/model/map/scene/mission revision, modes, timestep, sensor timestamps, initial pose, input/calibration source, config, operator interventions, terminal reason.
- A(보정 전)/B(scan 보정 후)를 같은 mission과 고정된 Nav2 설정으로 각 5회 제안. tuning train set과 평가 scene를 구분한다. 표본이 작은 데모 실험임을 명시한다.
- 기록: 준비 시간, geometry/registration error, 성공률(분모 포함), 충돌/접촉·개입, goal error, 이동거리/시간, 최소 clearance, 정지/통신 timeout 반응, sim-to-real 차이.
- 개선이 없거나 실패가 늘면 그대로 보고한다. false precision/최고 한 번만 골라 개선율 발표 금지.
- 최소 report/replay viewer만 만들고 범용 timeline editor는 후순위. 시뮬레이션 성공은 실제 Deploy 허가와 분리.

## S9 — 재현 가능한 제출

1. 사용자가 선택한 라이선스와 입력/asset/model attribution 정리. Windows credential/API key/company 이미지 제외.
2. 실제 검증한 clean clone에서 packages/frontend build, saved-response replay, engine 연결, 한 scene 실행. 시스템/Isaac 설치 여부에 따라 명확한 prerequisites.
3. README 첫 화면에 문제/대상 사용자/검증된 범위/Nebius+NVIDIA 역할/실행 순서/제한사항. 미래 계획은 별도.
4. 3분 미만 영상 구성 제안: 문제 15초 → 입력/계획/검증 35초 → 실제 로봇과 장애물 변화 65초 → 비교 결과 35초 → 플랫폼/제한/재현 15초. 영상이 실측을 왜곡하지 않게 source clip 보존.
5. Git push/공개 영상/제출은 사용자 승인 후. 변경을 검토해 이 단계 소유 파일만 stage하고 secret scan 후 commit/tag한다. dirty 전체를 무조건 `git add .` 하지 않음.
6. 최신 공식 마감/요건 재확인. freeze 이후 치명 결함 외 변경은 다음 버전으로 미룬다.

## 바로 다음 Sol 시작 프롬프트

> 기준 root는 C:\Users\jaewo\Documents\TwinPulse다. AGENTS.md와 최신 PROJECT_MEMORY, TWINPULSE_SOL_EXECUTION_PLAN_2026-09-22.md의 공통 규칙 및 S0을 읽고 S0만 수행해라. 기존 미커밋 변경은 보존하고, 새 유료 API/Isaac 기동/설치/실물 명령/push는 하지 마라. 검토 A-01/A-02/A-04의 재현과 현재 source/evidence snapshot을 checkpoint에 남겨라. 끝에 실행 결과와 S1a의 정확한 다음 작업을 보고하고 멈춰라.

S0가 이미 PASS라면 전부 반복하지 말고 source hash와 checkpoint를 확인한 후 사용자가 지정한 다음 하위 단계로 이어간다.
