# TwinPulse 종합 검토 — 제품 결함, 해커톤 적합성, 다음 투자 순서

- 작성: 2026-09-22 KST / 검토 기준 HEAD `500f19992350d5b96877a9001d429656dfc7f748` **및 당시 미커밋 R6 작업 트리**.
- 독자: 사용자, 후속 개발자 GPT 5.6 Sol.
- 성격: 소스/기존 실행 증거/격리 재현/공식 문서에 근거한 **검토 및 권고**. 제품 수정·ROS 설치·클라우드 과금·실물 구동·push 승인이 아니다.
- 연결: [Sol 실행 계획](TWINPULSE_SOL_EXECUTION_PLAN_2026-09-22.md), [TurtleBot3 실험 계획](TWINPULSE_TURTLEBOT3_EXPERIMENT_PLAN.md).

## 1. 결론

**아키텍처의 큰 방향은 맞다. 다만 지금은 제품의 핵심 경로보다 플랫폼 분리와 검증 장치가 앞서 있다.**

React App → Python application/backend → typed command broker → Isaac Extension이라는 경계, 허용된 도구만 실행하는 compiler, 입력/draft/stage revision, 2WD+passive support, 실제 물리 검증은 유지할 가치가 있다. 지금 전부 다시 만들거나 4WD로 바꿀 이유는 없다.

가장 큰 공백은 새 웹 App의 Generate가 실제 provider를 사용하지 않는다는 점이다. 과거 Extension에서 성공한 이미지→LLM→도구→Isaac 흐름과, 새 App에서 성공한 fixture→bridge→Isaac 흐름은 **서로 다른 증거**다. 두 흐름을 연결해야 한다. Settings에 키가 저장돼 있어도 현재 웹 생성 경로는 바뀌지 않는다.

해커톤 Physical AI 주제 적합성은 높지만, 현재 증거만으로 출품 요건 충족이나 수상권 완성도를 주장할 수 없다. Nebius 런타임 사용과 NVIDIA 공개 모델의 실질적 역할을 입증하고, 이미지/도면→검증된 3D→실물 관측 비교라는 짧고 완결된 고객 흐름이 필요하다. 권장 포지셔닝은 **소규모 로봇 도입팀의 현장 주행 사전검증 도구**다. 일반 창고 이미지 생성기, 범용 디지털 트윈 플랫폼, 자율 AGI를 동시에 만들지 않는다.

TurtleBot3는 이 연결을 검증하는 실험 플랫폼이다. 구매한 Burger의 2개 구동륜 구성을 유지하되, 현재 generic AGV를 실물 디지털 트윈으로 부르지 않는다. 먼저 공식 bringup/teleop/Nav2 기준선을 확보하고 TwinPulse를 연결한다.

## 2. 이번 검토의 증거 수준

| 구분 | 이번 확인 | 의미/한계 |
|---|---|---|
| 직접 코드 확인 | core/provider/application/workflow/API/credentials/process manager/launcher/engine host/React 계약 및 기존 지침 | 특정 작업 트리 기준. 미래 버전에는 재확인 필요 |
| 신규 격리 재현 | 서로 다른 입력의 동일 draft, 비소유 manager의 stop 파일 생성, 픽셀 없는 PNG 수락 | 일반 Python만 사용. 실제 Isaac/API/로봇을 실행하지 않음 |
| 기존 실제 실행 자료 | `artifacts/runs/20260922-100347`, `20260922-102341` 및 M2-C/D 기록 | 이 검토에서 전체 suite를 재실행한 것은 아님 |
| 공식 자료 | 해커톤 rules/judging, Nebius API/시뮬레이션, ROBOTIS, Nav2 | 2026-09-22 조회. 계정별 quota/model availability는 미조회 |
| 미확인 | 실제 TurtleBot 부품/OS/펌웨어, 새 웹 App live 생성, Nebius GPU, 회사 fresh clone | 완료 또는 PASS로 기록하지 않음 |

재현 스크립트(로컬 진단용): `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\work\astra_review_probe_20260922.py`. 저장소 외 임시 진단 자료이며 회사 설치 의존성이 아니다. Sol은 아래 재현을 저장소의 회귀 테스트로 옮긴다. 첫 임시 디렉터리 시도는 Windows sandbox 권한으로 실패했고, 명시적으로 만든 격리 scratch에서 재실행했다. 기존 런타임 state나 사용자 키를 읽지 않았다.

신규 출력 요약:

```text
distinct_inputs: different_input_revisions=true, identical_draft=true,
                 mode=deterministic_fixture
unowned_cleanup: rejection=launcher_already_running, owns_lock=false,
                 owned_processes=0, stop_signal_created=true,
                 existing_lock_preserved=true
png_without_pixel_data: bytes=45, accepted=[image/png, 1, 1]
real_image_decoder: NOT_RUN (일반 Python에 Pillow 없음; 설치하지 않음)
```

검토한 핵심 소스의 SHA256(후속 작업 전 변경 여부 확인용):

| 저장소 상대 경로 | SHA256 |
|---|---|
| `packages/twinpulse_app/src/twinpulse_app/product_workflow.py` | `DC3C0B0529F929B9D46C9E09D6F6101A4AAD7F146BE475D3A6D06D1E9A7B1018` |
| `packages/twinpulse_app/src/twinpulse_app/process_manager.py` | `9CE2B7F62626E67DF8473DD20EB11F43BCD229C7F37CFE5A3518909A30E38852` |
| `scripts/twinpulse_engine_host.py` | `14DFA59AE839E481C0754F06D25438D10036D572D190B28CA50B2C2599A9F982` |
| `packages/twinpulse_app/src/twinpulse_app/api.py` | `7DD5F2DEB2813A87A421D44C58F391749D1F91FAA67A02B3E68BC831010FAD52` |

## 3. 우선순위별 발견사항

P1은 다음 기능/실물 연결보다 먼저 닫을 항목, P2는 같은 제품화 구간에서 해결할 항목이다. 아래 번호는 이전 지침의 F1~F10과 혼동하지 않도록 **A-** 접두어를 쓴다.

### A-01 · P1 · 웹 생성 경로가 fixture에 고정됨 — 직접 재현

- 위치: `scripts/twinpulse_backend.py`의 `fixed_warehouse_bundle()`/`ProductWorkflow(artifact)`, `packages/twinpulse_app/src/twinpulse_app/api.py:156`, `product_workflow.py`의 `start_fixture_generation`, `_complete_generation`, `_draft_summary`.
- 요청의 이미지/문구를 받아도 생성은 잠시 기다린 뒤 고정 artifact를 `draft_ready`로 노출한다. 상반된 두 문구에서 입력 hash는 달랐지만 draft 전체가 같았다.
- UI/API는 `deterministic_fixture`라고 명시한다. 숨긴 live 호출로 단정하지 않는다. 문제는 **이 경로가 아직 최종 제품 생성 경로가 아니라는 것**이다.
- R3 `ApplicationService`의 실제 generation gateway, immutable revision, persistence를 웹 backend가 사용하지 않는다. 새 workflow가 독립 상태기계를 재구현해 후속 정합성 유지 비용이 커진다.
- sidecar는 파싱되지만 workflow에는 제약 자체 대신 개수만 남는다. profile/settings revision도 현재 웹 입력 hash에 없다. live 연결 시 그대로 두면 R1의 보호를 우회한다.
- 조치: 웹 adapter가 R3 service를 호출하도록 통합. fixture는 명시적인 테스트 모드로만 유지. 실제 job/request/input/plan/build receipt를 한 provenance chain으로 연결.
- gate: 실제 이미지 A/B의 차이, sidecar 위반 차단, 생성 중 입력/설정 변경, restart 복원, 정확한 applied revision. 유료 시험 전 fake gateway/저장 응답 replay로 먼저 검증.

### A-02 · P1 · 중복 실행 실패의 정리가 기존 엔진을 멈출 수 있음 — 직접 재현

- 위치: `process_manager.py`의 `_acquire_lock`, `stop`(약 184행 이후); `scripts/twinpulse_launcher.py`의 무조건 `finally: manager.stop()`; `twinpulse_engine_host.py`의 stop-file loop.
- live PID lock이 있으면 두 번째 manager는 소유권을 얻지 못한다. 하지만 `stop()`이 소유권과 무관하게 공유 `engine-stop.request`를 만든다. 기존 engine은 이 파일을 종료 신호로 읽는다.
- 격리 재현은 기존 프로세스를 실제로 종료하지 않았지만, 비소유 manager가 정확히 이 신호를 생성하는 것까지 확인했다. “no process was terminated” 메시지와 실제 부작용이 어긋난다.
- 조치: 비소유 cleanup은 완전 no-op. session/launch ID가 있는 소유 stop 신호. 획득·spawn·ready·종료 상태별 rollback을 구분.
- 회귀: lock rejection 후 launcher의 finally까지 실행; 첫 owner의 stop/status/ready 파일 불변; 첫 engine 계속 살아 있음. lock 함수만 단독 호출하는 테스트로 끝내지 않음.

### A-03 · P1 · R6 캡처 성공 판정이 비동기 파일 생성과 어긋남 — 실제 실패 + 소스 근거

- 기존 isolated `20260922-100347/r6-app`: PASS, 32 prim, 약 0.329136m 이동, 960×640 PNG.
- 더 늦은 full run `20260922-102341`: manifest FAIL. browser PASS, engine 연결/32 prim/약 0.262762m 이동은 확인됐지만 `capture_missing`으로 최종 FAIL.
- 이후 같은 run의 `runtime/isaac-viewport.png`는 486,730 bytes이며 SHA256 `E00C4BC1E981AD184F97722023243960FF39942463643407CE7747584024D774`다. **나중에 파일이 존재한다고 당시 FAIL을 PASS로 바꾸지 않는다.**
- `twinpulse_engine_host.py:50–61,172–189`: capture 완료 후 즉시 파일 검사, 함수의 bool 결과 미사용, 한 번의 missing이 terminal FAIL, 이후 재검사 없음.
- 설치된 Kit capture 구현은 renderer에 저장 요청 후 future를 완료하고 지정된 update frame을 기다린다. 이는 TwinPulse가 확인해야 하는 디스크 파일의 안정적 decode 완료와 동일한 계약이 아니다. I/O 완료 타이밍이 유력하나 실제 원인 확정에는 task/frame/file timestamp 계측이 필요하다.
- 조치: 유한 상태 `requested → render_returned → file_pending → decoded → verified`와 monotonic deadline. 파일 크기 안정/완전 decode/해당 run·stage·revision·camera 연결 검증. 이미지를 다른 run에서 재사용하지 않음.
- 단지 sleep을 크게 늘리거나 capture를 optional로 바꿔 PASS시키지 않는다. 구조 검증+브라우저+3D 증거를 별도 상태로 보존하고 전체 verdict는 필수 gate의 conjunction으로 계산.

### A-04 · P1 · 이미지 검사가 완전한 decoder가 아님 — 일부 직접 재현

- `product_workflow.py::_inspect_image`: PNG IHDR/IEND/checksum만 확인해 IDAT 없는 45-byte 파일도 수락한다.
- JPEG는 SOF에서 크기를 얻으면 성공 처리하므로 전체 손상 여부를 확인하지 않는다. WebP 분기는 VP8X/VP8L만 있고 일반 lossy VP8 분기가 없다. JPEG/VP8은 정적 결함 후보이며 이번 실데이터 재현은 NOT RUN.
- 조치: 지원 decoder의 verify와 실제 decode, bounded bytes/pixels, MIME 일치 및 unsupported 유형의 정확한 오류. dependency는 별도 격리 설치 계획 후 추가.
- 회귀: 정상 PNG/JPEG/VP8/VP8L, truncated payload, 거짓 MIME, oversized dimensions, 빈 파일, decode 실패, 정상 이미지+sidecar.

### A-05 · P1 · provider 전환 시 credential의 endpoint 귀속이 없음 — 잠재 보안 위험

- `credentials.py:11`: 기본 target `TwinPulse/OpenAIResponsesAPI` 하나. `api.py::_save_provider_settings`는 base URL을 바꿔도 키 필드가 비면 이전 키 유지.
- 새 App에서 live 경로가 아직 없으므로 **현재 이 경로에서 유출됐다는 증거는 없다**. 하지만 이 설정을 그대로 live 호출에 연결하면 다른 endpoint로 이전 provider의 credential을 보내는 위험이 생긴다.
- 조치: provider/profile + 정규화 origin/protocol에 credential reference를 귀속. endpoint 변경 시 기본 unconfigured, 명시적인 migration/rebind만 허용. redirect로 다른 origin에 Authorization 전달 금지. key 원문/해시를 input revision·로그·browser에 넣지 않음.
- settings와 credential의 부분 저장 실패도 다룬다. “Windows 저장소 영속 구현”과 “실제 재부팅 후 해당 경로로 정상 사용” 증거를 구분.

### A-06 · P2 · 장시간 사용/새 탭의 인증 복구 경로 부족 — 정적 확인

- `api.py::_bootstrap_session/_session`: cookie Max-Age는 발급 시 1800초, 서버 session expiry는 요청마다 연장. cookie는 갱신되지 않아 활성 사용 중에도 브라우저 인증이 먼저 끝날 수 있다.
- `apps/twinpulse-web/src/api.ts`: CSRF는 sessionStorage, fragment bootstrap은 일회성. 새 탭·세션 만료 때 기존 launcher 링크를 그대로 다시 쓰는 것으로는 복구를 보장하지 않는다.
- 조치: 유한 idle/absolute TTL과 정상 renewal/reopen 계약, owner만 새 bootstrap 발급, 새 탭 정책, 만료 후 안전 정지·명확한 UI 안내. 인증을 없애거나 secret을 localStorage에 장기 저장하지 않음.
- fake clock으로 30분 경계·재발급·잘못된 origin/CSRF/role 시험, actual browser 새 탭/refresh 시험.

### A-07 · P2 · 설정/프로세스 수명주기의 실패 경계 — 추가 검증 필요

- `settings.py::save`는 고정 `.tmp` 사용. threaded API의 동시 저장 충돌 가능. 저장소 손상/접근 거부는 정상 오류 응답으로 정규화해야 한다.
- manager의 사용자 지정 state dir는 engine에만 환경 전달된다. backend 설정/credential은 기본 사용자 저장소를 사용할 수 있으므로 E2E 격리 시험에서 실제 사용자 설정을 만질 위험을 차단해야 한다.
- `python.bat`의 Popen PID와 실제 Isaac 후손 프로세스 소유권은 다르다. graceful 실패 후 terminate/kill이 후손까지 정리하는지 fake process 테스트로는 증명되지 않는다. Windows Job Object 또는 동등한 검증된 tree ownership을 검토한다. 사용자 전체 kit.exe 일괄 종료 금지.
- lock의 작성 중/불완전 JSON, PID 재사용, 접근 불가 PID를 dead로 오판하는 경로도 failure injection 대상이다.
- monitor의 PID 생존과 앱/engine heartbeat 정상은 다르다. loop hang·stale telemetry를 명시적으로 관찰해야 한다.

### A-08 · P1(실물 이전) · 장면 유효성과 제한된 주행 capability가 결합됨

- `core/validation.py:179` 등은 +X 직선/같은 y/거리 제한을 현재 controller 조건으로 강제한다. 이 한계는 이전 crash를 막은 guard이므로 무조건 삭제하면 안 된다.
- 장면이 올바른데 경로가 굽어 있다는 이유로 전체 생성 실패가 될 수 있고, LLM이 생성 장면을 단순한 통로로 왜곡하도록 유도할 수 있다.
- R7 취지대로 `scene_valid`, `robot_compatible`, `mission_supported`, `run_allowed`를 분리. 장면 Build 성공과 Nav2 운행 가능을 별도로 표시한다.
- 물리 안정성 PASS는 일반 장애물 회피·현장 안전·실물 동역학 일치를 뜻하지 않는다. generic 2WD profile은 회귀 기준으로 남기고 TurtleBot 전용 profile/adapter를 추가한다.

### A-09 · P2 · 측정 출처/성공 조건/계수의 제품 의미가 불명확

- 도면 M2-D 27/29 실패는 사라지지 않았다. sidecar 차단 성공은 OCR/치수 판독 성공이 아니다.
- `_draft_summary`의 `tool_count=len(objects)+2`는 실제 tool receipt 개수가 아니다. mock summary라도 도구 호출 수로 오해할 수 있다.
- non-black 화면은 목적 장면임을 증명하지 않는다. prim 개수도 형상/동선 정확도를 증명하지 않는다. 0 collision samples는 detector가 관찰한 범위의 결과이지 안전 인증이 아니다.
- 출처는 observed / measured / user_override / inferred / template로 나누고 unknown은 unknown으로 유지한다. 입력→계획→실제 USD→runtime 관측의 provenance를 연결한다.

### A-10 · P1(제출 이전) · 제출/배포 증거 부족 및 문서 상태 불일치

- 미커밋 R6 파일이 많고 일부 untracked다. HEAD만 clone하면 이번 검토 대상 R6와 같지 않다.
- 루트 `LICENSE*` 파일은 이번 조회에서 발견하지 못했다. 공개 repo 주소만으로 open-source 제출 요건을 충족했다고 보지 않는다. 라이선스 선택은 사용자의 권리/의도 확인 후 수행한다.
- Baseline/Memory/README/progress에는 earlier R6 PASS가 전면에 있고 later full-run FAIL 및 App live integration 미구현이 충분히 드러나지 않는다.
- 조치: 과거 PASS를 삭제하지 않고 최신 verdict를 우선 표시. Gitignored 대형 artifact의 재현 절차·sanitized 요약/hash를 tracked report로 보존. fresh clone은 선택된 commit+dependency lock+asset manifest로 검증.

## 4. 해커톤 Fit: 좋은 주제지만 현재 형태로는 수상 준비가 안 됨

### 공식 조건과 일정

공식 규정은 Nebius Token Factory 런타임 호출 또는 Nebius AI Cloud 실행, 그리고 NVIDIA 공개 모델 사용을 요구한다. **Isaac Sim만 쓴 것은 모델 사용 증명이 아니다.** 제출 마감은 2026-10-30 10:00 PDT, 한국 시간 **10월 31일 02:00**이다. 공개 소스·라이선스·실행 설명과 3분 미만 공개 영상이 필요하며, Physical AI의 영상에는 실제 로봇 작동(하드웨어가 없으면 핵심 모듈 작동) 최소 1분을 포함하도록 안내한다. 계정/지역/팀 자격은 제출 전 사용자가 확인한다. [공식 규정](https://nebiusglobalaihackathon.devpost.com/rules)

심사는 구현·디자인·영향·아이디어를 동등 비중으로 평가하며, Physical AI에서는 미리 정한 동작만 하는 데모보다 실제 입력에 반응하는 하드웨어를 강조한다. [공식 심사 안내](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works)

| 평가 관점 | 현재 증거 기반 판단 | 수상 경쟁력에 필요한 변화 |
|---|---|---|
| Physical AI 주제 | 높음: Isaac/로봇/현장 입력이 직접 연결되는 문제 | 실물 또는 실제 모듈 end-to-end 동작 |
| 필수 플랫폼/모델 | 미입증: 주된 provider 증거는 OpenAI, 실행은 로컬 Isaac | Nebius+NVIDIA model의 실제 핵심 경로와 사용 증거 |
| 구현 완성도 | 하부 계약/검증 강점, 웹 live 생성/launcher 안정성 공백 | 한 App에서 생성→검토→실행→증거 저장 |
| 제품 디자인 | React 전환 타당, 상태/복구/결과 설명 미완 | 단계 구분, 실패 원인, 원클릭 재개, evidence 확인 |
| 고객 영향 | 도입 비용 절감 가능성은 있으나 실측 부족 | 수동 준비 대비 시간, 보정 전후 오차, 실제 mission 결과 |
| 아이디어 차별성 | 이미지→3D/LLM tool call 자체만으로는 약함 | 잘못 추정한 환경을 scan으로 고치고 재검증하는 증거 흐름 |

수상 확률이나 순위는 경쟁작/심사위원 판단을 모르므로 수치화하지 않는다. **현재 상태는 기반 기술 PoC로는 의미 있지만 수상권 제품으로 평가하기에는 이르다. 아래 좁은 데모를 끝내면 경쟁력 있는 출품 후보로 발전할 수 있다**는 것이 본 검토의 판단이다.

### 권장 변경: 범위 확장보다 가치의 연결

권장 한 문장: **“사진·도면에서 만든 개략 현장을 실제 스캔으로 보정하고, 로봇 임무를 가상 검증한 뒤 제한된 실물 시험으로 비교하는 AI 사전검증 도구.”**

최소 데모는 한 로봇, 한 소형 트랙, 두 장면 상태로 고정한다.

1. 사용자가 공개 가능한 트랙 사진 또는 치수 도면과 목적지를 입력한다.
2. Nebius에서 실행되는 NVIDIA model이 관측/제약을 바탕으로 allowlisted plan을 만든다. 불확실 치수는 표시한다.
3. Isaac에서 TurtleBot-compatible scene/mission을 확인하고 사전검증 결과를 보여준다.
4. 실제 TurtleBot의 scan/odom으로 위치·장애물 차이를 확인하고 승인된 작은 보정을 적용한다.
5. 운영자가 로봇 정지 상태에서 장애물을 옮긴다. 새 scan에 따라 현장 로봇은 정지/재계획하고, twin은 revision을 바꾸어 재검증한다.
6. 동일 과제의 보정 전후 준비 시간·형상 오차·성공/실패·주행 시간을 하나의 보고서로 보여준다.

안전 정지/로컬 회피는 deterministic controller/Nav2/supervisor의 책임이다. 매 제어 주기를 cloud LLM이 결정하는 것이 아니다. LLM의 가치도 단순 결과 요약으로 축소하지 말고 장면/mission proposal과 허용 도구 선택에 실질적으로 둔다.

### Nebius/NVIDIA 활용 설계

- 1차: 계정에서 사용 가능한 NVIDIA model의 modality/구조화 출력/tool use/가격을 확인한다. 정확한 model ID를 추정해서 하드코딩하지 않는다. 모델 목록은 공식 [List models](https://docs.tokenfactory.nebius.com/api-reference/models/list-models)로 확인할 수 있다.
- vision model을 쓸 수 있으면 관측+계획을 담당시킨다. text-only NVIDIA model만 가능하면 별도 VLM의 관측 JSON을 입력으로 받아 **제약/도구 계획 결정**을 담당시킨다. 서로의 역할·출처·실제 호출을 기록한다.
- 기존 Responses adapter의 Base URL만 바꾸면 프로토콜 호환이 보장되지 않는다. Nebius의 [inference service](https://nebius.com/services/token-factory/inference-service) 사용 예시와 실제 endpoint를 확인해 별도 adapter/capability 계약으로 연결한다.
- 2차: full Isaac GPU 서버 목표는 유지한다. Nebius는 RT-capable L40S/RTX PRO 계열 시뮬레이션 경로를 안내한다. 실제 SKU/region/quota/Isaac 호환성은 작은 smoke로 확인한다. [Nebius simulations](https://nebius.com/solutions/simulations)
- 전체 Isaac의 클라우드 실행은 **사용자의 프로젝트 목표**이고, 해커톤 일반 조건 자체가 반드시 모든 Isaac을 cloud에서 실행하라는 뜻은 아니다. quota가 막히면 Token Factory+local Isaac 출품으로 축소할지 사용자에게 결정받는다. cloud 완료라고 표기하지 않는다.
- 비용은 모델 token, GPU 실행 시간, disk/storage, 전송을 나누어 기록. credit 존재와 GPU 할당 가능은 별개다.

### 제외/후순위

- 범용 외부 MCP 서버, Tauri 패키징, 멀티 로봇, 고품질 photoreal asset library.
- RL/Isaac Lab 학습부터 도입하는 접근. 먼저 Nav2 기준선과 소수 parameter 후보의 통제 비교.
- 초파리 connectome controller는 사용자의 장기 연구 아이디어로 유지하되 이번 hackathon main demo에는 넣지 않음. 계산 모델 연구이며 살아 있는 뇌 연결이 아니다.
- 장애물을 모든 조건에서 회피한다거나 산업 현장에 안전하게 배포 가능하다는 주장.

## 5. 권장 일정과 중단 기준

아래는 9월 22일 기준 **제안 일정**이다. 단계별 gate가 날짜보다 우선한다.

| 구간 | 우선 산출물 | 일정 위험 시 줄일 것 |
|---|---|---|
| 9/22–9/26 | A-02/A-03 복구, App live service 연결, provider protocol 조사, TB inventory | 새로운 UI 꾸미기/전체 재설계 |
| 9/27–10/3 | Nebius NVIDIA 핵심 생성 1회+replay, App 3-image 연결, TB 기본 bringup | 모델 종류 늘리기/반복 유료 재시도 |
| 10/4–10/10 | R7 분리, TurtleBot 전용 sim profile, Nav2 기준선, cloud 작은 smoke | 범용 편집기/일반 도면 OCR |
| 10/11–10/20 | 제한 실물 mission 및 한 번의 layout change, paired metrics | RL/신경망 연구/자동 parameter Deploy |
| 10/21–10/26 | 재현성·fresh clone·권리/라이선스·데모 반복 | 기능 추가 |
| 10/27–10/30 | code freeze, 3분 미만 영상·README·제출 점검 | 마감 당일 구조 변경 |

cloud quota와 robot host OS는 앞에서 확인하되, 승인 없는 설치/과금은 하지 않는다. 실물 gate가 실패하면 수동 screenshot으로 성공처럼 보이게 하지 말고 검증된 sim/모듈 데모 범위로 축소 여부를 결정한다.

## 6. 지금 사용자에게 필요한 결정 / 나중에 필요한 결정

문서 작성은 아래 답변 없이 완료할 수 있다. 구현 직전에 필요한 항목만 묻는다.

1. **범위:** 위 사전검증+실물 비교 데모를 이번 hackathon 핵심으로 좁힐지. 기존 목표를 폐기하는 것이 아니라 제출 우선순위 조정이다.
2. **Nebius:** API 시험 횟수/비용 상한, GPU smoke 최대 시간/총예산, 계정 region/quota. 키 자체는 채팅에 받지 않음.
3. **하드웨어:** 기존 Pi OS 유지 여부, 별도 Ubuntu 원격 PC 유무, 실제 LiDAR 모델, 실물 시험 장소/운영자/전원 차단 수단.
4. **공개:** 자체 촬영/합성 입력의 공개 가능 여부와 repo 라이선스. iStock 미리보기 등은 공개 재배포 권리를 자동 가정하지 않음.

다음 기본 개발 권고는 **Sol 계획 S0 → S1**이다. S0은 snapshot/재현/체크포인트, S1은 launcher 소유권과 capture 자동 관찰 복구다. 그 뒤 S2로 실제 생성 경로를 연결한다. 사용자가 선택한 한 단계만 실행한다.
