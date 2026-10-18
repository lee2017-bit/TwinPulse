# TwinPulse 회사 분리망 배포 검토 및 GPT 6.0 Sol 실행 지침

> **후속 정정 / 2026-09-25:** 이 문서의 O3 장면 교환, O4 일반 PC planner-only, A에서의 AI 생성, 두 PC 사이 결과 왕복, `simulation-offline` 기본 실행은 사용자 배치 결정으로 **실행 계획에서 철회**한다. 아래 내용은 당시 검토 이력이며 새 구현 지시로 사용하지 않는다. 현재 활성 경로는 [해커톤·워크스테이션 실행 방향](TWINPULSE_HACKATHON_EXECUTION_DIRECTION_2026-09-25.md)이다. GitHub 가능 일반 PC는 릴리스 파일만 다운로드·전달하고, RTX 3070 워크스테이션에서 웹 App·LLM 요청·Isaac을 모두 실행한다. 회사 네트워크의 Nebius 접근성과 실제 Isaac 실행은 미검증이다.

- 작성일: 2026-09-25 KST / 계획 버전 1.0
- 검토 기준: `main` / `5c42899a95a0bf2422550bd17df7556a92ab3232`, Baseline v1.0.52.
- 역할: Astra 계획·검토 → GPT 6.0 Sol 선택한 하위 단계 구현·검증. 모델 전환이나 다른 작업 생성은 이 문서가 수행하지 않는다.
- 최초 작성은 설계·작업계획이었다. 후속 작업에서 O1/O2의 로컬 시험용 설치·전송 경로와 명시적 `simulation_offline` 진단 모드를 일부 구현했다([검증 기록](../verification/O1-O2-local-offline-release.md)). O3 장면 교환 프로토타입은 현재 결정에 맞지 않아 미커밋 코드에서 제거했다. O4 planner-only는 구현하지 않는다. **회사 설치·LLM 연결·Isaac acceptance는 미완료**다.
- 기존 R/S/M 번호를 변경하지 않고 회사 오프라인 배포 트랙 **O0~O7**을 추가한다. 기존 사진 충실도, M2-D PARTIAL, R6 미완료 범위는 그대로 남는다.

## 1. 판단

**현재 온라인 설치기를 그대로 회사 환경에 적용할 수는 없다. 핵심 제품을 전면 재작성할 필요는 없고, 배포·기동 경계 및 장면 파일 교환을 보완하면 된다.**

React → Python ApplicationService → 로컬 인증 bridge → Isaac Extension/compiler/runtime 구조, 허용된 도구 계획, 2WD 프로필과 검증 로직을 재사용한다. MCP 서버를 두 PC 사이에 추가하는 것은 이번 문제의 해결 전제가 아니다. 필요한 것은 인터넷 없이 설치·실행할 배포물과, 연결되지 않은 PC 사이에서 검증 가능한 입력/장면 파일을 옮기는 계약이다.

회사 워크스테이션에서 가능한 목표를 구분한다.

| 목표 | 현재 판정 | 필요한 변경/조건 |
|---|---|---|
| GitHub clone 후 기존 원클릭 설치 | 그대로는 부적합 | 설치 중 Python/npm 패키지 다운로드, 웹 빌드가 필요 |
| 이미 생성된 장면을 가져와 실제 Isaac Build/Run | 구현 기반 있음, 회사 실행 미검증 | 오프라인 배포물, 장면 import, 로컬 의존성/RTX 시험 |
| 워크스테이션에서 사진을 넣어 즉시 새 AI 생성 | 조건부 | 허용된 외부 또는 사내 LLM endpoint 접속 필요 |
| 일반 PC에서 AI 생성 후 파일을 옮겨 3D 실행 | 권장 대안, 제품 기능 추가 필요 | 일반 PC의 승인된 API 접속, planner-only 기동, export/import |
| CPU VDI에서 현재 Isaac 3D 실행 | 기본안에서 제외 | 적합한 GPU 없음 |
| 향후 L40S 4GB VDI에서 현재 Isaac 실행 | 기본안에서 제외 | 실제 vGPU/RT 기능·driver·VRAM·runtime 검증 전 적합성 보장 불가 |

새 장면의 AI 생성과 저장 장면의 시뮬레이션은 별개다. 외부 API도 사내 API도 없고 로컬 추론도 준비되지 않았다면, 패키지만 옮겨서는 새 AI 생성이 생기지 않는다. 이때 저장 장면의 Build/Run은 지원해도 생성 기능을 mock으로 대체하면 안 된다.

## 2. 이번에 확정된 환경과 미확인 사항

사용자 보고를 현재 회사 배치의 기준으로 삼는다. 과거 설치 안내서의 RTX 3500 Ada, 특정 D: 경로, wheel 모음은 이번 워크스테이션의 확인 사실이 아니다.

| 구분 | 사용자 보고 사실 | 부여할 역할 |
|---|---|---|
| A: 사내 일반 PC Local | GPU 없음, 외부 GitHub 가능, VDI 접속 가능 | 릴리스 다운로드·준비, 필요 시 CPU 웹 빌드, 허용된 경우 AI planning |
| B: 워크스테이션 Local | RTX 3070, Isaac Sim 6.0.1 설치, GitHub 등 대부분 외부 접속 불가, VDI 접속 가능 | React/Python App와 별도 Isaac 창, 검증·물리·렌더링 |
| V: VDI | 현재 CPU만 있음, 외부 사이트 대부분 차단 | 승인된 파일 중계. 실행 서버·API 프록시로 가정하지 않음 |
| 전송 | VDI를 통해 두 Local 사이 이동, 한 번에 1GB 한도 | 단일 파일/회차 모두 한도 내로 분할·수동 전달 |
| 대체 수단 | 보안 USB 현재 없음 | USB를 필수 준비물로 요구하지 않음 |

미확인: A/B의 OS·아키텍처·RAM·디스크, B의 실제 VRAM·driver·Isaac build/Kit patch·설치 경로, 별도 Python 3.12와 브라우저, A의 npm/PyPI 접속 및 개발 도구 실행 가능 여부, 반입 파일 확장자/실행 정책, 두 PC 간 직접 네트워크 연결, A/B의 정확한 LLM endpoint 접근 가능 여부.

과거 사용자는 프로젝트 입력의 외부 전송을 허용했다. 이를 취소한 것으로 취급하지 않는다. 다만 앞으로 사용하는 특정 사내 이미지/도면의 반출 범위나 사내 정책이 그 승인에 포함되는지 불명확하면 그 입력만 보류하고 공개/합성 입력으로 검증한다. GitHub 접속 가능은 Nebius·PyPI·npm 접속 가능을 뜻하지 않는다.

현재 공식 Isaac 6.0.1 요구사항 페이지는 Windows 11, RAM 32GB, GPU RTX 4080, VRAM 16GB를 최소 표로 제시한다. RTX 3070의 실제 사양을 수집하고 미달을 명시해야 한다. 가정 개발 PC의 8GB 환경에서 작은 장면이 실행된 기록은 회사 3070에 대한 보장이 아니다. 작은 procedural scene으로 조건부 시험할 가치는 있지만 복잡 창고·다중 센서·학습의 성능을 약속하지 않는다. 4GB VDI를 이 워크스테이션의 대체로 계획하지 않는다. [공식 요구사항](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/requirements.html)

## 3. 코드에서 직접 확인한 제약

| 파일/구성 | 확인한 동작 | 설계에 주는 의미 |
|---|---|---|
| `scripts/install_twinpulse.ps1` | 시작부터 Isaac root 필수; CPython 3.12; pip install; pnpm install/build; 없으면 npm으로 pnpm 확보 | GPU/Isaac 없는 A에서 배포물 준비용으로 재사용하기 어려움. 준비와 설치 분리 |
| `scripts/launch_twinpulse_app.ps1` | 실행할 때 React build; pnpm 또는 npm 필요 | B의 일반 실행 경로에서 빌드 제거 필요 |
| `scripts/twinpulse_launcher.py`, `process_manager.py` | backend + Isaac의 동시 기동/ready, `dist/index.html` 필수 | planner-only를 명시적으로 추가. B는 기존 manager 유지 |
| `packages/twinpulse_app/.../api.py` | host는 `127.0.0.1`만 허용, remote/CORS 모드 없음 | 파일 중계를 네트워크 bridge로 오인하지 말 것. 원격 bind로 바꾸지 않음 |
| `config/python-runtime-requirements.lock` | Windows x64/CPython 3.12의 Pillow 12.3.0 hash lock | 정확한 wheel 반입으로 App 의존성 설치 가능. 다른 Python ABI에 재사용 금지 |
| `scripts/twinpulse_backend.py` | source-layout로 core/provider/app 로드, 기존 replay mode 있음 | 우선 동일 layout의 릴리스 묶음이 최소 변경. 패키지 설치 방식 혼합 금지 |
| `replay.py`, `verify_s2d_managed_replay.py` | M2-C report 형식 재검증, zero-provider replay, actual Isaac 기록 | 유용한 기반이나 임의 프로젝트의 export/import 제품 기능이 완성된 것은 아님 |
| `scene_compiler.py`, `runtime.py` | 현재 procedural geometry 중심; 조사한 파일에서 외부 asset URL/reference 호출 미발견 | 전체 Isaac asset pack 반입을 선행 조건으로 삼지 않음 |
| Extension manifest | simulation manager, wheeled robots, uiapp, filepicker, viewport utility, timeline, USD 의존 | Isaac 설치되어 있어도 이 의존성과 전이 의존성의 local availability 확인 필요 |
| Git ignore | `dist`, `.venv`, `node_modules`, `artifacts` 제외 | GitHub 소스 ZIP만 옮기는 것으로 실행 준비가 끝나지 않음 |

2026-09-25 clean clone 설치 PASS는 개발 PC의 네트워크/기존 패키지 cache를 사용한 결과다. **cold offline 설치 PASS가 아니다.** source-only replay의 JSON hash도 공식 생성자 신원을 인증하는 서명이 아니다.

## 4. 권장 배치

```text
개발/릴리스 환경(현재 개발 PC 또는 승인된 빌드 환경)
  소스 고정 → React build + Python wheel 확보 → 버전·hash manifest → 분할
                              ↓ GitHub 등 승인된 다운로드 경로
A: 일반 PC Local
  릴리스 수령/해시 확인 (GPU·Isaac 불필요)
  [선택] 이미지+설명 → 허용된 LLM → 검증된 scene 파일 export
                              ↓ 승인된 VDI 파일 전달, 회차당 1GB 이하
B: RTX 3070 워크스테이션 Local
  offline install → 로컬 브라우저+Python → 127.0.0.1 bridge → Isaac 6.0.1
  scene 파일 import → 현 버전 재검증 → 사용자 검토 → Build → Run/Pause/Reset
                              ↓ 결과 파일/허용한 캡처, 필요 시 VDI로 회신
A: 결과 확인 및 다음 입력/수정 준비
```

우선 B에서 UI/backend/Isaac를 모두 실행한다. A의 브라우저가 B를 직접 제어하는 설계는 채택하지 않는다. VDI 접속과 직접 A↔B routing은 별개이며, VPN·터널·개인 proxy·방화벽 해제는 이 계획에 포함하지 않는다.

현재 개발 root와 GitHub 저장소는 그대로 사용한다. B의 `TwinPulse/releases/<release-id>`는 배포 설치 위치로서 새로운 개발 기준 root가 아니다. 절대 사용자 경로를 릴리스에 하드코딩하지 않는다.

### 명시적 실행 모드

다음은 신규 설계 명칭이다. `mode` 하나에 generation/runtime 개념을 섞지 않도록 capability와 provider policy를 분리한다.

| 모드 | 실행 구성 | AI 생성 | 3D Build/Run |
|---|---|---|---|
| `simulation-offline` | B의 UI+backend+Isaac | 비활성, provider 생성 0회 | import된 유효 장면에 허용 |
| `planner-only` | A의 UI+backend | 설정·접속이 허용된 provider만 | engine 없음 표시, 서버에서도 명령 거부 |
| `full-local` | 현재 개발 PC 또는 승인 endpoint가 있는 B | 기존 provider 경로 | 기존 실제 엔진 경로 |

기존 S2d replay/fixture 테스트 모드와 혼동하지 않는다. `simulation-offline`에서 가져온 장면을 새 live 생성으로 표시하지 않는다. planner-only에서 engine이 없다는 이유로 생성·내보내기까지 막거나 engine ready를 가짜로 만들지 않는다.

### LLM 연결 선택 순서

1. B가 이미 승인된 사내 LLM에 접근할 수 있으면 별도 provider adapter로 연결을 검토한다. 실제 protocol/model/vision/schema/auth를 확인하기 전 a.biz와 OpenAI 호환성을 가정하지 않는다.
2. A에서 승인된 Nebius API에 접근 가능하면 기존 Gemma→Nemotron pipeline을 planner-only로 사용한다. A의 GPU는 필요 없다. 결과를 파일로 B에 반입한다.
3. 두 경로 모두 불가능하면 공개/승인 입력으로 미리 만든 장면을 B에서 시험한다. 새 회사 입력의 AI 생성은 미지원으로 표시한다.
4. CPU PC나 8GB GPU에서 새로운 로컬 VLM/LLM을 구축하는 것은 별도 성능·모델·라이선스 프로젝트다. 이번 오프라인 설치의 필수 조건으로 추가하지 않는다.

## 5. 배포물 설계

### 5.1 개발 도구와 실행 파일 분리

권장 첫 구현은 **현재 source layout + 미리 빌드한 React 정적 파일 + 정확한 Python wheel**이다. PyInstaller/새 데스크톱 프레임워크 도입보다 변경 범위가 작다. 이후 배포 최적화는 별도다.

제안 레이아웃(모두 O1 이후 구현):

```text
TwinPulse-release-<id>/
  release-manifest.json
  Install-Offline.cmd
  Start-TwinPulse.cmd
  Start-Planner.cmd                 # O4 완료 릴리스부터
  Verify-Offline.cmd
  packages/<core,provider,app>/src/  # allowlist, 동일 source commit
  extensions/twinpulse.extension/
  apps/twinpulse-web/dist/          # CPU에서 미리 빌드, same-origin 자산
  scripts/<필요한 launcher/backend/engine/capture/검증 파일>
  config/python-runtime-requirements.lock
  wheelhouse/<정확한 Windows x64 cp312 wheel>
  samples/<공개 또는 자체 생성, 최신 validator 통과 장면>
  licenses/
  docs/<오프라인 사용·실패 대응 안내>
```

배포물에서 `.git`, 기존 `.venv`, node_modules, 테스트 브라우저 download/cache, 사용자 runtime/credentials/logs, 사내 입력, NVIDIA 전체 설치 폴더를 제외한다. 개발 PC의 `.venv`는 PC별 경로가 들어갈 수 있어 복사하지 않는다. API key나 Credential Manager 저장 내용을 다른 PC에 이식하지 않는다.

Node/npm/pnpm은 릴리스 빌드 환경에서만 필요하도록 바꾼다. B는 브라우저, 승인된 CPython 3.12 x64, 기존 Isaac 설치를 사용한다. Pillow는 wheelhouse에서만 `--no-index --find-links ... --require-hashes`로 설치한다. source layout 방식이면 core/provider/app를 다시 pip로 sdist build하지 않는다. 기존 wheel 방식으로 바꾸려면 build backend까지 의존성 폐쇄를 증명해야 한다.

B에 CPython이 없으면 공식 CPython 오프라인 설치 파일을 별도 prerequisites 묶음으로 준비하고, 회사에서 허용된 절차로 사용자/관리자가 설치한다. 설치기는 누락 안내 후 중단하며 몰래 시스템 Python이나 Isaac Python을 바꾸지 않는다. 공식 embeddable Python에 pip/venv가 당연히 있다고 가정하지 않는다. 정확한 patch·출처·hash·라이선스는 O0/O1에서 고정한다.

A도 npm/PyPI가 차단될 수 있다. 이 경우 A에서 빌드하지 않고 현재 개발 PC 등 승인된 환경에서 완성된 release를 준비해 다운로드한다. 회사 PC에 Codex bundled runtime 경로를 요구하지 않는다. 릴리스 공개 업로드는 배포물 검수 및 사용자 공개 범위에 따라 수행하고, 회사 자료/비밀은 포함하지 않는다.

### 5.2 용량과 1GB 전달 제한

- 설치된 Isaac 6.0.1을 재사용한다. 약 10GB급 Isaac 설치본이나 전체 assets/Lab/wheels를 기본 bundle에 다시 넣지 않는다.
- TwinPulse core release, 필요 시 Python prerequisite, 확인된 경우에만 local Isaac dependency supplement를 별도 묶음으로 만든다. 첫 실제 빌드 전 총용량을 확약하지 않는다.
- core release는 가능하면 한 조각으로 만들되, 모든 조각의 기본 상한은 **900,000,000 bytes**로 한다. decimal 1GB/1GiB 혼동과 부가 여유를 고려한 값이다.
- 전체 archive를 생성하고 byte chunk로 `.part0001`, `.part0002`처럼 분할한다. 조각 각각은 독립 ZIP이 아니다. 작은 PowerShell 재조립 도구와 JSON manifest를 함께 제공한다. 첫 버전은 7-Zip 설치를 필수로 만들지 않는다.
- manifest는 release ID, 전체 bytes/hash, ordered part 이름/bytes/hash, part count를 갖는다. 입력 순서를 파일명 정렬에만 의존하지 않는다.
- 복원은 전체 목록/각 hash 검증 → 임시 archive에 순차 결합 → 전체 hash 검증 → 경로 안전성 확인 및 임시 폴더 추출 → 활성 버전 전환 순서다.
- 누락·중복·다른 release 혼입·변조·디스크 부족·중단 시 현재 설치는 보존한다. 손상 조각만 재전송할 수 있게 오류에 번호를 표시한다.
- VDI의 1GB가 회차 총합 제한일 수 있으므로 한 조각씩 전송하는 안내를 기본으로 한다. 확장자/분할 archive 반입 정책이 허용되는지는 현장에서 확인한다. 정책 검사를 피하려고 파일을 위장하지 않는다.
- 분할/재조립은 스트리밍으로 수행한다. 전체 대용량 archive를 메모리에 읽지 않는다. 조립 archive+추출 디렉터리+보존 버전을 합친 실제 필요 디스크를 계산한다.
- SHA-256은 무결성 검사다. 배포물과 함께 온 hash만으로 출처 인증을 주장하지 않는다. 신뢰할 수 있는 release 기록의 digest와 비교하거나 회사 배포 서명을 사용한다.

### 5.3 오프라인 설치·갱신

최종 사용자 동작은 **반입 폴더에서 `Install-Offline.cmd` 실행 → 필요하면 Isaac 경로 선택 → 이후 `Start-TwinPulse.cmd` 실행**이다. 현재 `Install-TwinPulse.cmd`는 온라인 개발 설치 경로로 보존하고 역할을 명확히 표시한다.

설치기는 사용자 쓰기 가능한 경로, 필요한 파일/hash/runtime, 남은 디스크, 기존 활성 launcher를 확인한다. 새 release를 별도 디렉터리에 설치·검증한 뒤 active pointer만 바꾼다. 실행 중인 사용자 Isaac을 종료하거나 이전 설치를 자동 삭제하지 않는다. 버전별 venv는 대상에서 생성한다. credentials는 기존 OS store에 두고 project/state 변경은 백업 후 적용한다. 구버전이 신버전 state를 읽지 못하면 snapshot 복원을 요구한다.

반복 실행·재부팅·경로 공백/한글·일반 사용자 권한을 검증한다. offline 모드에선 pip index 확인, npm/npx/pnpm/corepack, git fetch, 브라우저 자동 설치를 실행하지 않는다. `ExecutionPolicy Bypass`만으로 AppLocker/WDAC/회사 정책이 해결된다고 안내하지 않는다. 실행 차단은 승인된 서명/배포 경로로 처리한다.

## 6. 장면 교환 계약

### 6.1 형식과 경계

신규 `.twinpulse-scene`은 제한된 ZIP 컨테이너로 제안한다. 첫 schema `1.0`, 압축·전체 해제 크기 각각 최대 64MiB, 최대 파일 수 32개, 단일 입력은 기존 10MiB/40MP 한도를 유지한다. 필요 시 별도 변경으로 상한을 조정하며 설치 archive 제한과 혼합하지 않는다.

허용 내용:

- `manifest.json`: source release/commit, exchange schema, catalog/compiler/profile identity, 파일별 bytes/hash, bundle/plan/input identity.
- 이미지 1개, prompt, input kind, image에 결합된 optional measurement sidecar와 constraints.
- 검증된 SceneToolPlan, 기존 GeneratedDraftRecord/provenance의 허용 필드, canonical SpecBundle digest.
- LLM provider/model/request 식별과 관찰·route resolver provenance 중 기존 bounded schema가 허용한 항목. API key, credential reference, 인증 헤더, local 경로/username, raw HTTP response, data URI는 제외.

v1의 실행 가능한 교환물은 입력 bytes를 포함해 identity를 재계산할 수 있게 한다. 입력을 포함할 권한이 없으면 실행용 파일 export를 중단하거나 별도 비실행 보고서로만 제공한다. hash만 넣어 현재 input validation을 통과한 것처럼 만들지 않는다. 출처/라이선스 공개 가능 여부는 데이터별로 유지한다.

직접 USD/Python/셸, arbitrary asset path/URL, 객체 역직렬화(pickle), 실행 hook은 받지 않는다. schema 허용 필드와 파일 목록을 고정하고 ZIP path traversal, 절대경로, Windows drive/UNC/ADS, symlink/reparse, 중복·대소문자 충돌 경로, decompression bomb을 거부한다. import 시 URL을 따라가지 않는다.

### 6.2 import의 정확한 순서

1. 새 임시 작업 위치에서 size/schema/archive path 및 파일 hash를 검증한다. 현재 프로젝트나 stage는 아직 바꾸지 않는다.
2. 기존 bounded image decoder/sidecar/input revision 계약을 적용한다. 생산자 commit/catalog/compiler/profile 지원 범위를 확인한다. v1은 호환 릴리스 identity 일치를 기본으로 하고 임의 버전 자동 업그레이드는 하지 않는다.
3. SceneToolPlan을 현재 allowlist로 parse/re-execute하고 bundle digest, 치수, route, 랙 overlap을 재검증한다. 예전 파일의 `PASS` 문자열은 건너뛰기 권한이 아니다.
4. 생성 당시 input/settings identity는 출처로 보존한다. B의 활성 provider settings나 key를 바꾸지 않는다. B의 다른 LLM 설정에 맞추려고 imported revision을 조용히 덮어쓰지 않는다. 기존 restore/rebind와 새 import context를 명시적으로 구분하고 round-trip 테스트로 identity를 보장한다.
5. 유효 artifact를 ApplicationService/기존 broker 등록 경로로 승격하고 UI에 `imported`, 원래 생성 출처, 현지 재검증 상태를 표시한다. ack는 대상 PC에서 해당 input+draft에 대해 새로 받는다.
6. stage epoch, engine session, lease, command receipts, applied revision, 안전 latch, source PC ack는 이식하지 않는다. B의 실제 Build가 성공한 뒤에만 적용됨으로 표시한다. import만으로 Build/Run을 자동 실행하지 않는다.

파일 이관 중 수정된 sidecar/input, incompatible catalog, 중첩 랙, 모르는 profile은 typed error로 거부하고 기존 project/stage를 보존한다. 최신 guard에서 거부되는 과거 90-prim live plan을 demo fixture로 포장하지 않는다.

### 6.3 결과 회신

별도 result bundle은 release/plan/input/run 식별, 실제 Build/Run 상태, goal/cross-track/roll/pitch/collision/Pause/Reset 수치와 실패 단계만 기본 포함한다. viewport/browser capture는 로컬에 자동 저장하되 외부로 내보낼 때 데이터 공개 범위에 맞춰 사용자가 선택한다. 로그는 허용 필드의 진단 요약을 우선하고 전체 환경변수/credential store/raw HTTP/컴퓨터 이름을 덤프하지 않는다.

## 7. Isaac 오프라인 실행의 추가 조건

Kit은 필요한 Extension이 local cache에 없으면 registry 다운로드를 시도할 수 있다. NVIDIA도 air-gap 구성에서 local registry/dependency 준비를 설명한다. 따라서 `Isaac 설치됨` 또는 `provider 호출 0회`만으로 full offline readiness를 선언하지 않는다. 공식 문서는 원칙 참고이며 새 Kit 앱을 만들거나 전체 air-gap SDK를 반입하라는 지시가 아니다. [Kit Extensions](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/extensions_advanced.html), [Air Gap Guide](https://docs.omniverse.nvidia.com/air-gap/latest/build.html)

O0/O5에서 기존 standalone의 정확한 build와 로컬 Extension dependency closure를 기록한다. 필요한 항목이 없으면 정확한 id/version/platform과 라이선스·공식 취득 경로를 제시한다. 별도 supplement만 준비하며 개발자의 전체 cache를 무분별하게 복사하지 않는다. shader/driver cache는 다른 GPU에서 그대로 유효하다고 가정하지 않는다.

procedural floor/rack/AGV 및 local material/light만 쓰는 최소 scene으로 시작한다. 원격 HDRI/texture/USD/reference·브라우저 CDN/font가 새로 들어오지 않았는지 검사한다. renderer 품질·viewport 해상도·scene 규모는 측정 가능한 preset으로 제한하되 물리 안정성 허용치를 낮춰 PASS시키지 않는다.

offline 기동 설정은 설치된 Kit 버전의 지원 옵션으로만 적용하고 전역 사용자 설정/registry를 수정하지 않는다. 필수 의존성 부재는 missing ID와 복구 방법을 보고하고 유한 시간 안에 종료한다. 첫 shader 준비 시간이 길면 단계별 heartbeat를 기록한다. timeout 증가는 계측 근거로 결정하고 무한 대기로 바꾸지 않는다.

## 8. Sol 단계별 작업

공통: 기준 root의 AGENTS/메모리와 이 문서의 선택 단계만 읽고 진행한다. 회사에 직접 접근할 수 없으면 로컬 결과를 회사 PASS로 표시하지 않는다. 미래 O단계나 기존 R7~R10을 함께 구현하지 않는다. 시스템/driver/네트워크 정책 변경, 새 유료 API, 실물 조작은 이번 문서로 승인되지 않는다.

### O0 — 환경 진단 도구와 실행 분기 확정

- 제안 파일: `scripts/inspect_company_environment.ps1`, `docs/verification/O0-company-environment.md`.
- 일반 PC용 `prepare`, 워크스테이션용 `simulation` 역할을 명시한다. GPU/Isaac 없는 A에서도 성공적으로 보고서를 만들 수 있어야 한다.
- read-only inventory: OS/x64/RAM/free disk, 선택한 Isaac root의 VERSION/Kit/Python, GPU/VRAM/driver, 별도 Python3.12, 브라우저, 로컬 확장 metadata. 비밀값·전체 registry·환경변수·사내 파일 탐색 금지.
- 외부/사내 endpoint probe는 자동 스캔하지 않는다. 명시된 정확한 URL에 한해 선택적으로 DNS/TCP/TLS/HTTP 실패 단계를 구분하며 키·이미지 전송 없이 bounded timeout, retry 0으로 한다. 401/403/404는 응답 수신과 API 권한/기능 성공을 구분한다. read-only 탐색이 정책상 불가하면 `UNKNOWN` 기록.
- 결과는 sanitized JSON+읽기 쉬운 TXT. 코드/도구 준비와 회사 측 실측은 별개 상태다. 회사 보고서 반환 대기 중 O1의 CPU 빌드 준비는 독립 진행 가능하다.
- 완료 기준: A에 Isaac/GPU 없어도 진단 가능; missing dependencies가 명확함; local 테스트와 회사 NOT_RUN 구분; 비밀 canary 없음.

### O1a — 버전 고정 및 CPU-only release builder

- 제안 파일: `scripts/build_offline_release.ps1`, `config/offline-release.schema.json`, release allowlist.
- 기존 온라인 installer에서 Isaac 사전검사를 재사용하지 않는다. clean commit/출력 경로/Windows-x64-Python3.12를 입력받는다. commit/dirty 상태를 manifest에 기록하고 배포 release는 재현 가능한 clean source에서 만든다.
- exact pnpm 11.19.0 + frozen lock로 정적 웹 빌드. Pillow lock에 맞는 binary wheel을 다운로드하고 hash/tag 확인. sdist build 또는 GPU/Kit import를 요구하지 않는다.
- scripts가 import하는 내부 helper·extension assets·config를 모두 포함하는 dependency manifest 작성. dist의 asset hash와 source commit 결합. `0.1.0` package version만으로 같은 빌드라고 판정하지 않는다.
- 완료 기준: Isaac 없는 환경의 build 또는 Isaac 경로/Kit 접근을 차단한 CPU 전용 검증 PASS; unpacked release 순수 import/static assets 검증; 비밀/사내 데이터 없음; 실제 용량 보고. Isaac acceptance는 NOT_RUN.

### O1b — 전송 분할·복원 및 prerequisites 분리

- 제안 파일: `scripts/split_release.ps1`, 배포용 `Reassemble-TwinPulse.cmd`, 순수 PowerShell restore helper.
- 5.2 규격 구현. fresh B에 Python/7-Zip이 없어도 hash 확인과 재조립 안내가 가능해야 한다.
- 분할 테스트는 작은 임계치로 최소 3개 조각을 만들어 누락/손상/순서 교체/release 혼합/중단/재개를 검증한다. 큰 파일 할당이 꼭 필요하지 않으면 1GB dummy를 만들지 않는다.
- 완료 기준: byte-for-byte 복원, manifest 순서와 hash, 실패 시 기존 설치 보존, 모든 실제 조각 900,000,000 bytes 이하. Python prerequisite가 필요하면 core와 별도 목록으로 기록.

### O2a — offline installer와 prebuilt launcher

- 제안 파일: `Install-Offline.cmd`, `Start-TwinPulse.cmd`, `scripts/install_twinpulse_offline.ps1`; 변경 후보 `launch_twinpulse_app.ps1`, `twinpulse_launcher.py`.
- B의 Node/Git/npm/pnpm을 필수에서 제거한다. 새 venv에서 local wheel만 설치. 현재 source layout과 manager/engine host를 보존한다.
- 재시작 때 build/install을 반복하지 않고 manifest로 검증된 dist와 Python만 실행한다. default Isaac path를 발견하지 못하면 선택한 root를 비밀 없는 machine config에 저장한다.
- side-by-side release, update/rollback, 상태 snapshot, 일반 사용자·공백/한글·실행 중 설치 보호를 구현한다.
- 완료 기준: npm/PyPI/인터넷 없는 깨끗한 staging에 설치 및 순수 backend/static UI smoke; dependencies가 없을 때 자동 인터넷 fallback 없음; online 개발 launcher 회귀 보존.

### O2b — 명시적 simulation-offline 모드

- 변경 후보: `process_manager.py`, `twinpulse_backend.py`, `product_workflow_service.py`, provider composition, React 상태/설정 UI.
- 시작 시 provider 인스턴스/키를 요구하지 않음. offline mode에서 Generate는 API/UI 모두 `generation_unavailable_offline`로 거부. 기동 시 숨은 `/models` ping·외부 capability probe 없음.
- 첫 설치 smoke는 provenance가 `bundled_demo`인 작은 공개/합성 장면으로 가능하게 한다. 버튼과 화면에서 demo임을 표시하며 provider 생성 실패 fallback으로 쓰지 않는다. O3 뒤 사용자 import가 주 경로다.
- 완료 기준: key 없는 상태에서 launcher/UI/engine 사용 가능, provider 호출 0회, generation 거부, 기존 live/replay 모드 회귀. 아직 회사 성공 판정은 하지 않음.

### O3a — scene exchange 순수 계약

- 제안 위치: `packages/twinpulse_app/src/twinpulse_app/scene_exchange.py`와 schema/tests. 기존 `draft_store.py`, `input_revision`/artifact/measurement/registry 계약 재사용.
- 6절 export/import/제한 구현. 파일 조작과 순수 schema 검증을 분리한다. 임의 JSON PASS를 trusted draft로 만드는 우회 금지.
- 완료 기준: deterministic round-trip identity, 원본 input 교체/sidecar mismatch/손상/unknown schema/catalog/profile/악성 ZIP 모두 거부; imported receipts/ack 제거; 실패 원자성. 서로 다른 공개 장면 최소 2개로 다양성 유지.

### O3b — 제품 UI와 import state 연결

- 변경 후보: `api.py`, `application.py`, `project_store.py`, `product_workflow_service.py`, React App/API client.
- `장면 내보내기/장면 가져오기`를 구현. 기존 app의 request/upload bound와 새 ZIP binary bound를 구분하고 인증/Origin/CSRF 정책 유지. UI 표시만 바꾸고 서버 허용 검사를 생략하지 않는다.
- 승인된 input/draft revision과 Build allowed 상태를 실제 broker에 연결. 새 import로 stage를 자동 교체하지 않는다. import 뒤 기존 stage와 draft가 다르면 Run gate가 기존 정합성 규칙을 따른다.
- 완료 기준: A export를 독립 state인 B import에 적용, ack→Build gate 확인, stale old draft/late generation 차단, restart 복원, key 없는 B 사용. importer가 producer의 settings/secret binding을 활성화하지 않음.

### O4 — GPU 없는 planner-only (API 경로가 가능한 경우)

- 변경 후보: `twinpulse_launcher.py`, `process_manager.py`, backend/service/UI capabilities; 제안 `Start-Planner.cmd`.
- 기존 manager의 engine-required 경로와 명시적으로 분리. backend/브라우저만 own/start/stop한다. `isaac_python`·engine host·GPU 파일 검사를 planner-only에서 하지 않는다.
- ApplicationService와 기존 provider adapters를 그대로 사용하고 별도 생성 구현을 만들지 않는다. UI에는 엔진 미연결과 가져갈 draft 상태를 표시. Build/Run/Pause/Reset은 API에서 명확히 거부한다.
- fake transport로 이미지→검증된 plan→export와 cancel/stale/settings 변경을 먼저 시험한다. 실제 endpoint 호출은 승인된 키/입력/예산/횟수 조건에서만 한다.
- 완료 기준: Isaac 없는 일반 Python 환경에서 실행; provider 결과 검증/export; 불가능한 엔진 명령 거부; 자체 process만 종료; 기존 full-local 회귀. API 경로 미확인일 때 구현 PASS와 live NOT_RUN을 나눔.

### O5a — 설치된 Kit의 로컬 의존성 및 첫 기동

- 변경 후보: `twinpulse_engine_host.py`, `process_manager.py`, 배포 readiness/진단. 필요한 offline 옵션은 해당 설치본 API/설정 근거를 확인하고 적용한다.
- B와 같은 build의 로컬 Extension closure/asset/브라우저 정적 의존성을 확인한다. 테스트 전용 cache/data 경로를 써서 사용자 cache를 삭제하지 않는다. 기존 standalone에 포함된 필요한 exts cache는 inventory로 명시한다.
- 외부 egress가 차단되고 loopback은 허용된 승인 환경에서 cold 기동. 회사 방화벽을 임의 변경하지 않는다. 실제 egress 차단 검증 환경이 없으면 mock/no-provider 결과만 보고하고 `full_offline_network=NOT_RUN` 유지.
- 완료 기준: 외부 download 의존 없이 실제 engine ready 또는 정확한 missing-dependency FAIL. nonfatal 온라인 registry 경고와 필요한 다운로드 실패를 구분. 외부 연결 시도 잔존 시 기록하고 무시하지 않는다.

### O5b — 유한 자동 검증과 회신 bundle

- 제안 `Verify-Offline.cmd`, `scripts/verify_offline_release.py`, `docs/verification/O5-offline-release.md`.
- Node/Playwright 설치를 요구하지 않는 runtime verifier로 제품 endpoint와 기존 actual-Isaac harness를 재사용한다. 브라우저 capture가 필요하면 설치된 Chrome/Edge용 검증 수단을 release에 포함하고 외부 browser download는 금지한다.
- 테스트: clean install→key 없이 실행→두 scene import→ack→Build/revision 확인→Run/Pause/중간 Reset/완주/완료 Reset→viewport capture→종료→재시작 및 복원. 순차 1 engine만 사용한다.
- 기존 profile/acceptance 수치를 사용하고 goal, cross-track, pitch/roll, collision samples, pause drift, reset error, prim 수, elapsed, peak 자원과 renderer/preset을 남긴다. collision metric이 geometric sampling이면 정밀 contact 검증으로 과장하지 않는다.
- 짧은 결과 manifest/TXT, trajectory 요약, secret-filtered 오류, 공식 Isaac screenshot을 자동 생성한다. 캡처의 black/constant 검사와 실제 장면 판독은 별도이며 UI 성공만으로 physical PASS 금지.
- 최종 상태 `PASS/FAIL/BLOCKED/NOT_RUN`, 실패 phase, 다음 정확한 한 작업을 반드시 기록. CPU builder PASS, local offline PASS, company PASS를 나누고 full offline 또는 paid live NOT_RUN을 PASS에 포함하지 않는다.

### O6 — 실제 회사 PC 파일 이동 및 pilot

- O0 결과를 이용해 지원 범위와 prerequisites를 고정. A에서 릴리스 확인 → VDI로 조각별 반입 → B에서 복원/hash 확인 → 설치 → `Verify-Offline.cmd` 실행.
- B에서 자동 만든 결과 중 반출 가능한 bundle만 A로 반환한다. 여기에 모델 API/회사 데이터 접근이 없어도 public demo/import된 승인 장면으로 Isaac 재현을 확인할 수 있다.
- 직접 회사 세션/파일 시스템이 연결되지 않은 개발 에이전트가 VDI 조작·실행을 수행했다고 주장하지 않는다. 최초 반입/더블클릭/결과 반출은 사용자 또는 사내 담당자가 맡고 이후 재현·캡처·계측은 스크립트가 맡는다.
- O4 지원 경로가 확정되면 A 실제 생성→export→VDI→B import→실제 3D 실행을 추가 acceptance로 수행한다. 이것은 offline install 성공과 별도다.
- 완료 기준: 실제 B 환경 식별과 자동 evidence 수령. 설치·build·physics·화면·재기동 각각 PASS 또는 원인 명시. 실패 시 driver 무단 업데이트나 safety threshold 완화로 해결하지 않는다.

### O7 — 승인된 사내 provider 직접 연결 (선택)

- B에서 접근 가능한 endpoint가 있고 사용자가 이 경로를 선택할 때만 진행한다. 현 단계의 오프라인 실행 완료를 기다리게 만드는 선행 조건이 아니다.
- 실제 protocol, 인증, model ID, vision/structured-output/schema 범위와 사내 CA/proxy 요건을 기록하고 별도 명시 adapter로 구현한다. TLS 검증을 끄거나 Nebius origin에 사내 key를 재사용하지 않는다.
- fake transport→무비밀 연결 진단→허용 입력 유한 live→실제 Isaac의 순서. vision 불가이면 이미지 지원 가능 provider/별도 승인 관찰 경로가 필요하다고 표시한다.
- 2WD physics/실시간 제어는 계속 local. 네트워크 LLM에 wheel command를 맡기지 않는다.

## 9. 우선순위·종료점·토큰 한도 대응

권장 순서:

1. O0 진단 도구 준비 + O1a/O1b 배포물 준비.
2. O2a/O2b로 다운로드·Node·API key 없이 실제 실행 준비.
3. O3a/O3b로 회사 사용자가 장면을 가져올 수 있게 함.
4. API 경로가 있으면 O4, 없으면 그 live gate만 보류.
5. O5a/O5b 로컬 offline 검증 → O6 회사 pilot. O7은 선택.

첫 전달 가능 목표는 **B에 설치된 Isaac를 이용해 승인된 저장 장면을 자동으로 Build/Run하고 캡처·보고서를 생성하는 것**이다. O4 없이도 이 목표는 진행할 수 있다. 회사에서 새 이미지로 반복 AI 생성하는 목표는 O4 또는 O7의 연결 gate를 추가로 통과해야 한다.

한 turn에서 O1 전체+O2+O3를 몰아서 진행하지 않는다. 구현 요청을 받으면 선택한 하위 단계에 대해 파일 수정→필요 테스트→짧은 결과보고까지 닫는다. 일일 한도에 대비해 `docs/verification/O*-*.md`에 다음을 남긴다.

```text
step / source commit 또는 dirty files / 입력·출력 release id
완료한 변경 / PASS·FAIL·NOT_RUN / 증거 경로
남은 blocker / 실행 중인 owned process / 다음 정확한 명령·하위 단계
유료 요청 수행 여부(시도 수, 결과 불명 여부; 키·본문 없음)
```

각 milestone 종료 시 Baseline+메모리를 동기화한다. 결과 불명인 유료 요청을 자동 재실행하지 않는다. 공개 push는 사용자가 지정한 범위에 따라 소스·문서·공개용 manifest만 수행하고 사내 결과/이미지·binary runtime을 git에 섞지 않는다.

## 10. 6.0 Sol에 전달할 첫 지시문

> 기준 root `C:\Users\jaewo\Documents\TwinPulse`의 AGENTS.md, PROJECT_MEMORY, Baseline v1.0.52 및 `docs/planning/TWINPULSE_COMPANY_OFFLINE_DEPLOYMENT_PLAN_2026-09-25.md`를 읽고 **O0의 진단 도구 준비와 로컬 검증만** 수행하라. 일반 PC prepare 역할과 RTX 워크스테이션 simulation 역할을 분리하고 GPU/Isaac 없는 PC에서도 sanitized inventory를 만들 수 있게 한다. 외부 통신은 기본 off로 둔다. 회사 PC 정보는 사용자 보고와 직접 수집 결과를 구분한다. 회사 접근 권한이 없으면 결과를 조작하지 말고 회사 측 실행용 파일과 안내를 완성하라. O1 이후 설치·패키징·LLM 호출·Isaac 재기동·push는 이 첫 지시의 범위에 포함하지 않는다. 끝나면 변경 파일, 검증 결과, 회사에서 실행할 한 단계, 다음 O1a를 보고하라.

## 11. 남아 있는 사용자/현장 확인

- A 또는 B에서 허용되는 정확한 LLM API 경로. 미확인이어도 offline 배포 개발은 진행 가능하다.
- 기존 승인 범위 밖의 새 사내 자료라면 해당 데이터의 외부 LLM 전송 가능 여부.
- B의 OS/RAM/driver/VRAM/Isaac build/path/Python은 O0 보고서로 수집한다. 사용자가 긴 명령 목록을 수동 타이핑할 필요가 없게 도구를 만든다.
- 1GB 반입 정책의 파일·회차 단위 및 허용 확장자/실행 정책. 우선 한 조각당 900MB, 회차당 한 조각을 기본으로 한다.

현재 결론을 위해 L40S VDI 구매/할당, 새 저장소, 보안 USB 확보, remote MCP server 도입을 결정할 필요는 없다. 이번 문서는 위 설계를 제안하고 다음 구현 범위를 정리한 것이며 회사 배포 완료를 선언하지 않는다.
