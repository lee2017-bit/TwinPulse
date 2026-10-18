# TwinPulse Windows EXE 전환과 배포 준비 작업계획

작성일: 2026-10-14. 대상 작업자: GPT-6.1 Sol 매우 높음(xhigh). 기준 저장소: `C:\Users\jaewo\Documents\TwinPulse`.

후속 실행 기록: [v477 최종08 실제 EXE·LLM 인수](../verification/windows-exe-live-acceptance-20261014.md), [이전 v476 EXE 인수](../verification/windows-exe-user-acceptance-20261014.md). 아래 ‘미실행’ 및 현재 코드 표는 계획 작성 당시 v475의 상태다. 로컬 EXE와 실제 텍스트/편집·복원은 통과 범위가 있지만 사진·혼합 repair 품질, 후보 동기화, 새 PC·전체 설치/공개는 미완료다.

현재 상태는 **계획 작성 완료, EXE 구현 및 인수 미실행**이다. 제품 기능의 기준은 Baseline v1.0.474의 PARTIAL 상태다. 이 계획의 문서 버전 갱신은 생성 품질이나 최종 배포의 완료를 뜻하지 않는다.

## 1. 목표와 첫 결과물

사용자가 `TwinPulse.exe`를 실행하면 기존 대화형 화면이 열리고, 설치된 Isaac Sim과 필요한 Extension이 연결되도록 한다. 재실행·새 대화·저장 복원 때문에 새 서버나 Isaac이 중복 실행되지 않고, 앱 주소와 사용자 자료가 안정적으로 유지되어야 한다.

첫 결과물은 **Windows x64용 one-folder 패키지**다. 폴더 안에 `TwinPulse.exe`, 앱 런타임, 미리 빌드한 React 화면, Isaac 연결용 소스와 필요한 자산을 넣고 ZIP으로 전달한다. 사용자는 압축을 풀어 EXE를 실행한다. 앱을 쓰기 위해 Git, Node, pnpm, 별도 App Python을 설치하거나 시작할 때 빌드할 필요가 없어야 한다. Isaac Sim과 호환 GPU/드라이버는 별도 전제다.

첫 EXE는 기존 Chrome/Edge 화면을 연다. **EXE 진입점과 전용 데스크톱 창은 서로 다른 작업**이다. 기존 CMD를 이름만 바꾸거나 EXE에서 개발 저장소의 CMD를 호출하는 것으로 독립 패키지 완료를 선언하지 않는다. WebView2 전용 창, 단일 파일 one-file, 자동 업데이트, 새 도메인·프록시 서버는 첫 인수 이후의 선택 단계다.

설치형 최종 배포까지의 순서는 `실행 구조 정리 → EXE 폴더 패키지 → 실제 사용자 인수 → 설치 및 업데이트 인수 → 공개 배포 검토`다. 제출 일정상 전용 창보다 이 순서를 우선한다.

## 2. 현재 코드에서 확인한 전제

| 확인 사실 | 수정에 주는 의미 |
|---|---|
| `Start-TwinPulse.cmd`는 개발/설치 경로를 나누고 개발 경로에서는 `launch_twinpulse_app.ps1 -SkipBuild`를 실행한다 | 개발용 시작도 유지하되 EXE와 공통 실행 서비스를 사용한다 |
| PowerShell `Port=0`, Python launcher `--port` 기본값도 0이다 | 완전 재시작 때 OS가 새 포트를 배정한다. 설치형 호출도 같은 기본값을 사용한다 |
| 현재 일반 New chat은 workspace 내부 전환이며 살아 있는 같은 런처 재열기는 기존 주소를 사용한다 | 이미 해결한 경로를 다시 만들지 않고 완전 재시작·충돌·다른 릴리스 경계를 보완한다 |
| `twinpulse_launcher.py`가 `sys.executable`을 Python으로 넘기고 `process_manager._backend_command()`가 `.py`를 실행한다 | frozen EXE에서는 재귀 실행 또는 잘못된 인자가 될 수 있다. 명시적인 자식 역할 실행이 필요하다 |
| `simulation_assets.py`와 Extension의 `core_bootstrap.py`가 파일의 부모 디렉터리로 저장소 위치를 계산한다 | 개발 저장소와 패키지 리소스 경로를 분리해야 한다 |
| Extension은 `packages/*/src`의 소스를 외부 Isaac Python에서 불러온다 | App EXE 안의 Python 아카이브만 배포해서는 Isaac import가 완성되지 않는다 |
| 기존 설치기는 CPython 3.12, venv와 Pillow wheel을 사용한다 | EXE 패키지용 설치 분기를 추가하면서 기존 설치를 파괴하지 않는다 |
| 기존 builder는 SHA manifest, 출처 감사, 명시 파일 복사와 개발용 dirty 표시를 갖고 있다 | 재사용한다. 현재 광범위한 scripts/tests 복사 목록은 실제 제품 의존성에 맞게 검토한다 |
| 현재 작업 트리는 많은 수정·미추적 파일을 포함하며 `.github/workflows`가 없다 | 현재 로컬 상태를 GitHub에 이미 보존된 릴리스로 간주하면 안 된다 |

검토 시 로컬 HEAD는 `5c42899a95a0bf2422550bd17df7556a92ab3232`였다. 이 값은 최신 dirty 파일의 내용이나 원격 최신 상태를 대표하지 않는다. 구현 시작 시 다시 확인한다.

기존 인수의 잔여는 별도 관리한다. 실제 사진의 상대 배치·자동 repair 정체, 최종 소스의 혼합/미사용 사진 시험, 취소·재개, 편집 후 완전 재열기, OS 붙여넣기 등이 남아 있다. EXE 빌드 성공으로 이 항목들을 PASS로 바꾸지 않는다. 정확한 원자료는 [v474 검증 기록](../verification/generation-ux-continued-user-20261014.md)을 따른다.

## 3. 공통 구조와 실행 계약

```text
TwinPulse.exe  기본 진입점과 소유 프로세스 관리자
  ├─ TwinPulse.exe  내부 backend 역할
  │    ├─ 같은 출처의 React 화면과 로컬 API
  │    ├─ 기존 대화·프로젝트·작업 저장
  │    └─ OS 보안 저장소의 키로 Nebius HTTPS 호출
  └─ 사용자가 설치한 Isaac의 python.bat
       └─ 패키지의 engine host와 TwinPulse Extension
```

### 실행 파일과 자식 역할

- 우선 구현안은 기존 Python 코드에 PyInstaller one-folder를 적용하는 것이다. 정확한 빌드 도구 버전은 구현 시 호환성을 확인한 뒤 build 전용 lock에 고정한다. 앱 런타임의 Python/Pillow/프런트엔드 버전을 패키징과 함께 무관하게 올리지 않는다.
- 진입점에서 허용한 `launcher`, `backend` 등 제한된 내부 역할을 명시적으로 분기한다. 임의 `.py`, `-c`, 모델 생성 코드를 실행하는 범용 인터프리터 역할은 만들지 않는다. 개발 모드는 기존 Python 경로를 사용한다.
- 내부 역할 인자 자체를 인증으로 취급하지 않는다. 기존 launch ID, 소유자, 세션 인증, 브리지 제어권과 초기화 증거를 검증한다.
- `physical_controller.py`, `robot_readiness.py` 등 `sys.executable` 자식 실행을 전부 목록화한다. 로컬 진단 역할은 같은 계약으로 이식한다. 실물 기능이 패키징되지 않았다면 명확하게 unavailable로 표시하고 실제 실물 동작으로 검증하지 않는다.
- windowed EXE에서 stdout/stderr가 없더라도 예외가 사라지지 않게 한다. 시작 전 실패는 작은 Windows 오류 안내와 사용자 데이터 폴더의 진단으로 보여주고, 백엔드 시작 후에는 앱에서 안내한다.

### 경로와 데이터

| 경로 | 내용과 규칙 |
|---|---|
| 실행 파일 위치 | EXE 및 릴리스 식별. 현재 작업 디렉터리에 의존하지 않는다 |
| `resource_root` | 빌드된 웹, manifest, 정적 자산, 고지. 읽기 전용으로 동작해야 한다 |
| `engine_payload_root` | 외부 Isaac Python이 읽는 host/Extension/필요한 순수 Python 소스. 같은 빌드의 코드여야 한다 |
| `state_root` | 기존 `%LOCALAPPDATA%\TwinPulse\runtime` 및 그 사용자 자료. 실행 파일의 이동·업데이트와 독립적이다 |
| 키 저장소 | 기존 Windows Credential Manager target과 참조를 유지한다. 키를 EXE·설정 평문·ZIP에 포함하지 않는다 |

공통 경로 해석기를 먼저 정하고 `__file__.parents[...]`, repository-relative 상수, 로그 쓰기 위치를 감사한다. frozen App 내부 코드와 Isaac용 외부 소스의 source hash를 manifest에 연결한다. 외부 Isaac을 실행할 때 frozen App의 DLL 검색 경로와 Python 환경이 Isaac 런타임을 오염시키지 않게 한다. 전역 환경 변경 대신 필요한 자식 실행 경계에서 처리하고 실제 Isaac으로 확인한다.

기존 source-root 아래 남은 자료는 읽기 목록으로 먼저 식별한다. 원본을 삭제하거나 사용자 프로젝트를 설치 폴더로 이동하지 않는다. 필요한 이전은 복사·검증·원자적 전환·재실행 가능 구조로 수행한다.

### 안정된 주소와 단일 실행

- 공통 설정에 `preferred_port`를 저장한다. 제안 기본값은 8765이며 최종 선택은 사용 가능성과 기존 설정을 확인해 정한다. 개발 PowerShell과 설치형/EXE가 같은 정책을 사용해야 한다.
- 일반 시작·완전 종료 후 재시작은 저장된 포트를 재사용한다. `--port 0`은 명시한 격리 개발/보조 시험에만 둔다.
- 이미 같은 사용자·같은 설치의 TwinPulse가 실행 중이면 검증된 기존 소유자에 열기 요청을 보내고 두 번째 런처는 종료한다. 단지 해당 포트가 응답한다는 이유로 소유 앱으로 채택하지 않는다.
- 외부 프로그램이 점유하면 종료시키지 않는다. 제한된 대체 후보를 실제 bind하여 성공한 주소를 저장하고 UI에 한 번 알린다. 매번 새 임의 주소를 선택하거나 무한 재시도하지 않는다. 사전 빈 포트 검사와 실제 bind 사이의 경합도 처리한다.
- 단일 실행 잠금은 PID뿐 아니라 시작 시각·실행 파일·사용자 데이터 위치·릴리스/프로토콜을 확인한다. PID 재사용을 고려한다. 오래된 기록을 무조건 현재 작업으로 취급하거나 불명 소유자를 강제 종료하지 않는다.
- 같은 주소에서도 새 실행의 세션과 인증은 새로 발급한다. 이전 탭의 요청·늦은 응답이 새 작업을 덮지 않아야 한다. Origin/Host/CSRF와 현재 프레임 검사를 유지한다.
- 로컬 UI/API는 loopback에 한정하고 키를 가진 백엔드가 공급자 HTTPS에 접속한다. 포트 포워딩·방화벽 예외·로컬 DNS·인증서 설치는 필요 조건으로 만들지 않는다.

### 시작과 종료의 사용자 경험

- 앱 화면은 Isaac 준비보다 먼저 열린다. 채팅 이력·설정은 엔진이 준비되는 동안에도 읽을 수 있어야 한다.
- `앱 시작 중`, `Isaac 시작 중`, `연결 중`, `연결됨`, `연결 끊김/실패`를 실제 상태로 표시한다. 초기 재료 없이 현재 장면이 있다고 표시하지 않는다.
- Isaac Extension은 유지하고 인증된 현재 연결에서만 초록점과 `TwinPulse Connected`, 펼침 작업 로그를 제공한다.
- 브라우저 창 닫기는 화면 닫기다. 백엔드와 Isaac이 계속 실행되는 동작을 앱에서 알리고 재실행하면 다시 열린다. 실제 종료를 위한 `TwinPulse 종료`를 앱 메뉴에 제공한다.
- 종료는 진행 중 작업의 취소/결과 정산과 저장을 처리하고 소유 Isaac의 정상 종료를 기다린 뒤 백엔드와 supervisor를 정리한다. 미확정 비용·작업은 기록을 남기며 자동 재전송하지 않는다.
- supervisor의 Job Object 수명과 정상 종료를 함께 설계한다. 창 없는 EXE가 보이지 않는 영구 프로세스로 남거나 종료 시작과 동시에 사용자 자료 저장 전에 자식이 잘려서는 안 된다.
- 엔진만 연결이 끊긴 경우 앱과 대화 화면은 유지한다. 재연결 자체가 미완성 LLM 작업이나 로봇 주행을 자동 재개하지 않는다.

## 4. 파일 소유와 재사용 범위

주 작업자가 먼저 경로/역할/주소/종료 상태 계약을 작성하고 파일 소유를 확정한다. 보조는 최대 2명이고 같은 파일을 동시에 수정하지 않는다.

| 담당 | 우선 확인 및 변경 후보 |
|---|---|
| 주 작업자 GPT-6.1 Sol xhigh | `scripts/twinpulse_launcher.py`, `twinpulse_backend.py`, `process_manager.py`, `startup_checks.py`, 공통 runtime path/command 해석기, exe 진입점, 패키지 빌드와 실제 통합 |
| UI 보조 GPT-6.1 Sol high 1명 | 합의된 API를 사용하는 시작/연결/종료·설정 UI와 해당 회귀. launcher/manifest/실제 엔진·외부 호출은 맡기지 않는다 |
| 필요 시 Astra xhigh 1명 | frozen 자식 역할, 상태 이전, 단일 소유자·충돌·복원 설계를 읽기 전용 검토 |

새 파일명 예시는 `scripts/twinpulse_desktop_entry.py`, `scripts/build_windows_exe.ps1`, `packaging/windows/TwinPulse.spec`, `config/python-build-requirements.lock`, `docs/WINDOWS_EXE_QUICKSTART.md`다. 기존 동등 기능이 있으면 재사용한다. 전용 폴더/서비스를 무의미하게 늘리지 않는다.

기존 `build_offline_release.ps1`, `install_twinpulse_offline.ps1`, `start_twinpulse_installed.ps1`, `audit_release_provenance.py`의 manifest 검증·버전별 설치·이전 active pointer·출처 고지를 활용한다. 실제 helper 의존성을 확인하기 전에 scripts/tests를 일괄 제거하지 않는다. EXE용 새 manifest schema를 도입하면 구형 설치와 명시 분기하고 검증을 생략하는 호환 분기를 만들지 않는다.

## 5. 순서별 구현과 종료 기준

### E0 현재 실행과 패키지 의존성 조사

1. AGENTS, 최신 Memory/Baseline, v474 검증 기록, 기존 배포/출처 문서를 읽는다.
2. 현재 프로세스·포트·작업 상태는 읽기 전용으로 확인한다. 실행 중인 사용자 작업이 있으면 패키지 제작 등 독립 작업을 먼저 진행한다.
3. 전체 자식 실행, 동적 import, JSON/schema/catalog/USD/Extension 데이터, repository-relative 경로를 목록화한다. 빌드 도구와 실제 지원 Windows/Isaac 버전을 확인한다.
4. 기존 키·프로젝트·원사진을 읽어 출력하지 않고 경로/참조/필요한 비민감 hash로 보존 기준을 만든다. local source manifest에는 선택된 dirty/미추적 파일도 명시한다.

종료 기준: 단일 실행과 경로/역할 계약, 패키지 포함 목록, 빌드 환경 부족분이 구체적인 파일 단위로 정리되어 있다.

### E1 기존 실행 경로 안정화

공통 preferred port, 같은 소유자 재열기, 중복 실행, 정상 종료, 엔진 시작 상태를 먼저 구현한다. 기존 CMD에서 주소 유지·브라우저 재열기·새 대화·저장 장면 표시를 실제로 확인한다. 포장 전에 발생한 기존 제품 결함과 이후 frozen 특유 결함을 구별할 수 있게 한다.

종료 기준: 일반 재시작에서 같은 저장 주소를 사용하고 동일 세션의 반복 실행이 백엔드/Isaac을 늘리지 않는다. 외부 점유와 다른 릴리스의 소유자를 잘못 연결하지 않는다.

### E2 EXE 실행과 경로 전환

공통 경로 해석과 제한된 내부 역할 dispatch를 구현한다. 현재 App Python 코드와 외부 Isaac Python 경계를 유지한다. windowed의 로그/오류/종료 경로, 동적 import와 실제 리소스 검사도 포함한다. `sys.executable`에 `.py`를 붙여 실행하는 지점은 전부 분류하여 남은 누락을 보고한다.

종료 기준: EXE launcher→EXE backend→별도 Isaac host가 정확한 순서로 한 번씩 실행되며 development Python이나 checkout 경로에 몰래 의존하지 않는다.

### E3 one-folder 패키지 제작

프로젝트 전용 빌드 환경에서 도구 버전과 해시를 고정하고 Windows x64 패키지를 만든다. spec/hook/resource 목록을 소스로 남긴다. 앱 시작 시 네트워크 설치나 웹 빌드를 수행하지 않는다. 빌드 산출물에 제품 버전, build ID, 원본 소스 commit 및 dirty source manifest SHA, UI/resource/engine payload SHA, 지원 환경과 서명 상태를 기록한다. 문서 Baseline 번호를 제품 버전으로 사용하지 않는다.

실제 ZIP의 모든 파일과 추가 파일까지 감사한다. Python/Pillow/프런트엔드/패키징 도구에 필요한 고지와 TwinPulse LICENSE/NOTICE를 포함한다. Isaac/Kit 실행 파일·모델 가중치·개인 사진·사용자 프로젝트·raw·API 키는 묶지 않는다. 기존 Burger 자산은 검토된 로컬 인수와 공개 배포 권리 검토를 구분한다.

종료 기준: 저장소 밖 새 경로에서 EXE가 앱을 열고 Isaac과 연결된다. 같은 패키지의 임의 파일 누락/변조는 구체 오류로 진단되며 개발 checkout으로 자동 fallback하지 않는다.

### E4 동결 패키지의 실제 사용자 인수

패키지 SHA를 고정하고 아래 시험표를 수행한다. 결함 수정으로 패키지가 바뀌면 새 build ID로 영향 시험을 다시 수행한다. 이전 성공 화면을 새 패키지의 성공으로 합치지 않는다.

실제 외부 호출은 실행 시 유효한 데이터·제공자·횟수·기한·누적 예산 안에서만 진행한다. v474의 4시간 승인은 2026-10-14 09:30:02 KST에 끝났으며 이 문서는 새 승인이 아니다. 당시 보호 장부는 USD3.7011867/10이고 최신 장부를 다시 읽어야 한다. 재승인이 실제 필요한 호출만 남기고 나머지 구현·로컬 인수를 계속한다. 이미 유효한 승인은 반복 질문하지 않는다. 앱의 USD1/가격 승인창을 다시 넣지 않는다.

종료 기준: 패키지 기능 결과와 사진 품질 결과를 별도 판정한 보고서가 있고, 실행하지 못한 표 항목은 NOT_RUN으로 남아 있다.

### E5 설치 업데이트와 복원

폴더형 EXE의 실제 인수가 끝나면 기존 per-user `installed/releases`·active pointer 방식을 EXE로 확장한다. 설치/업데이트에 App Python의 별도 설치나 venv 생성을 요구하지 않게 한다. 기존 구형 설치 포맷은 별도 경로로 계속 해석한다. 시작 메뉴/바탕화면 진입점은 활성 릴리스를 열어야 한다.

설치는 별도 staging에 파일과 manifest를 검증한 뒤 전환한다. 실행 중인 릴리스나 데이터에 덮어쓰지 않는다. 불완전 업데이트는 이전 정상 릴리스를 유지한다. rollback은 실행 파일뿐 아니라 데이터 schema 호환성을 검사한다. 새 버전이 변환한 데이터를 구버전이 잘못 읽게 하지 않는다. 제거는 앱 파일과 사용자 데이터 삭제를 구분하며 기본으로 사용자 데이터/키를 보존한다.

`Setup.exe`는 이 단계에서 필요한 경우 선택한다. ZIP 안 `TwinPulse.exe` 인수를 건너뛰려고 새 설치 프레임워크를 먼저 도입하지 않는다. 서명 인증서 구매·시스템 설치·공개 업로드는 현재 승인 범위를 확인한다. 서명하지 않은 후보를 서명 완료로 표현하거나 SmartScreen 우회를 사용자 기본 절차로 만들지 않는다.

종료 기준: 설치 A→업데이트 B→실패 복구/지원되는 rollback에서 키 참조·대화·첨부·미완성 초안이 보존되고 일반 아이콘으로 정상 실행된다.

### E6 GitHub와 공개 배포 준비

기존 저장소에서 소스·문서·빌드 레시피·잠금 파일을 관리한다. EXE/ZIP은 추후 GitHub Releases의 배포 파일로 제공한다. 설치 사용자에게 clone이나 개발 도구 설치를 요구하지 않는다. 이 단계의 로컬 준비만으로 push·tag·Release 업로드를 실행하지 않는다.

현재 미추적 파일 중 필수 제품 파일을 선별하고 명시 파일 목록을 만든다. `git add .`로 사진·outputs·진단을 섞지 않는다. ignore 추가는 이미 추적된 파일을 제거하지 않으므로 추적 상태를 별도로 검토한다. 원본 파일을 삭제하거나 이력을 임의로 다시 쓰지 않는다.

빌드 자동화가 필요하면 Windows 빌드/기본 패키지 검사를 하는 workflow 소스를 준비한다. 공개/Release 게시 단계는 분리한다. 일반 GitHub runner의 CPU 빌드 통과는 Isaac GPU·개인 키를 사용한 실제 LLM 인수를 대신하지 않는다. CI에는 개인 사진·실제 키·원 사용자 보고서를 올리지 않는다.

종료 기준: 검토 가능한 소스 목록, ZIP/hash/manifest/릴리스 노트/설치 가이드가 준비되어 있고, 실제 공개에 남은 권리·개인자료·서명·환경 미검증을 구체적으로 표시한다.

## 6. 실제 사용자 시험표

일반 EXE→실제 화면→클릭/입력/Attach 또는 OS 붙여넣기→생성/수정→저장/재열기를 사용한다. 제품 API 직접 호출, fixture, 내부 상태 주입은 보조 검사로만 기록한다. UI 도구가 Explorer나 OS paste를 지원하지 않으면 같은 EXE를 실행 도구로 시작한 차이를 기록하고 해당 native 항목을 NOT_RUN으로 남긴다. 도구의 URL 검사 실패를 앱 실패 또는 사용자 승인 부족으로 혼동하지 않으며 정책 제한을 다른 제어 도구로 우회하지 않는다.

| ID | 시험 | 필요한 증거와 통과 조건 |
|---|---|---|
| X01 | 일반 사용자 EXE 첫 실행 | 시작 화면, app/engine 단계, 인증 Connected, 현재 3D. checkout·개발 Python·Node에 의존하지 않음 |
| X02 | 동일 EXE 연속 2회 및 동시 실행 | launch ID/PID/실제 주소 확인. 동일 owner/backend/Isaac 1개, 기존 창 재열기 |
| X03 | New chat 3개와 프로젝트 왕복 | URL·engine 유지, 대화·사진·현재 장면이 올바른 프로젝트에 연결됨 |
| X04 | 브라우저 모든 앱 창 닫기 후 EXE 재실행 | 같은 실행 주소로 다시 열리고 기존 작업·저장 상태 유지 |
| X05 | 메뉴 정상 종료 후 EXE 재시작 3회 | 저장 포트 유지, 소유 자식 정상 종료, 새 세션 인증, 키 재입력 불필요 |
| X06 | 포트 충돌·stale lock·다른 릴리스 | 소유한 보조 시험으로 재현. 외부 서비스에 키 전송/강제 종료 없음, 제한된 복구·명확한 진단 |
| X07 | 한글/공백 경로·읽기 전용 리소스·다른 cwd | 리소스 읽기와 사용자 경로 쓰기 정상. 원 설치/사용자 자료의 권한을 임의 변경하지 않고 소유 시험 사본 사용 |
| X08 | Isaac 없음·지연·연결 실패와 복구 | 앱/설정 먼저 사용 가능, 설치 경로 선택·재연결 안내, 중복 엔진/자동 LLM 재전송 없음 |
| X09 | 기존 키·프로젝트·첨부·실패 기록 | 원자료/참조 보존, 실제 저장 대화와 마지막 미리보기 복원, static/live 표시 정확 |
| X10 | 실제 텍스트 생성 | 최종 EXE에서 새 입력→현재 Isaac→저장/재열기. 모델·실행 ID·HTTP·시간·비용 기록 |
| X11 | 실제 원사진 및 텍스트+사진 생성 | 원 입력 SHA, 초기 구조/묶음/repair 전 표시, 표시/대기 수, 원사진과 주요 배치·지지 비교 |
| X12 | 실제 자연어 수정·Apply·Undo·닫힌 재열기 | 의도한 물체/종속 물체만 변경, 저장된 새 revision/ACK, Undo 기하 복원, 재시작 후 일치 |
| X13 | 생성 취소·미완성 재개·늦은 응답 | 마지막 유효 장면과 pending 보존, 취소 결과가 새 대화에 적용되지 않음, 재개에 중복 물체/불명 재전송 없음 |
| X14 | 창 없는 supervisor/자식 실패 | 소유 시험에서 오류/잔여 작업을 남기고 재실행 가능. 개발용 crash 주입 결과는 보조로 표시 |
| X15 | 설치·업데이트·중단 복구·rollback | versioned 설치와 자료 schema 호환, active pointer/shortcut 정합, 사용자 자료 보존 |
| X16 | 다운로드한 동일 ZIP의 새 PC 인수 | Python/Node 없는 지원 Windows/GPU/Isaac 환경에서 실행. 현재 PC에서 PATH만 가린 시험은 대체하지 않음 |
| X17 | OS Ctrl+V와 Attach | 실제 전송 입력과 UI 첨부 확인. 도구 file chooser 지연은 모델 시간과 분리. clipboard 변환 SHA는 원파일 동일 바이트 시험과 구분 |

X10–X13에 필요한 기존 생성 UX 잔여를 먼저 해결한다. 기하 기준 완화·물체 삭제·사진별 배치 상수로 패키지 인수를 통과시키지 않는다. 유효한 부분 초안과 품질 미완성은 그대로 표현한다. 자동 repair가 발생하지 않은 fresh 시험은 그 분기의 회복 증거가 아니다.

응답성은 EXE 클릭→첫 앱 화면, 앱 화면→Isaac 연결, Send→초기 구조, 첫 물체 묶음, 최종 저장을 따로 측정한다. Cold/warm, 실제 엔진 준비, LLM 응답, UI 도구 지연을 구분한다. 파일 없는 즉시 실패를 성공으로 세지 않는다. 초기 UI 반응은 3초 이내를 설계 목표로 삼되 실제 장비 측정 전 보장값으로 발표하지 않는다.

같은 입력 3회/새 사진 2장 등의 이전 생성 품질 인수는 원 계획에서 이어간다. EXE 포장 시험 때문에 횟수와 비용을 초기화하거나 불필요하게 모든 모델 벤치마크를 다시 하지 않는다.

## 7. GitHub 관리와 배포물

| Git 저장소에 관리 | 생성 후 배포 파일로 관리 | 사용자 PC에만 유지 |
|---|---|---|
| Python/React/Extension 소스, spec/hook, build lock, 설치·빌드 스크립트, 시험, 문서, LICENSE/NOTICE | `TwinPulse-Windows-x64-<version>-<build-id>.zip`, 필요 시 Setup.exe, SHA256 목록, manifest, 릴리스 노트, 검토된 공개용 결과 | API 키, 개인 사진, 프로젝트, raw/실패/UNKNOWN 장부, 개인 경로가 든 보고서, 사용량 기록 |

소스 저장소가 원본이고 EXE는 특정 소스를 빌드한 결과다. 다른 개발자나 AI 도구는 소스와 빌드 방법을 읽고 수정할 수 있다. Apache-2.0과 자발적 출처 요청 정책을 유지하며 패키징으로 소스를 숨기거나 재사용을 제한하지 않는다.

`dist/`, `build/`, `artifacts/`는 기존처럼 산출물이다. `.env`와 개인 출력의 공개 제외는 정확한 경로·tracked 상태까지 점검한다. 이미 공유 가능한 문서를 일괄 지우지 않는다. public candidate는 검토된 allowlist로 조립하고 실제 포함 파일 전체를 감사한다. 로컬 private 보고서와 GitHub용 요약을 분리한다.

## 8. 권한과 작업 지속

현재 요청은 계획서와 프롬프트 작성이다. 실제 구현은 사용자가 실행 프롬프트를 전달하거나 구현을 지시한 뒤 시작한다. 문서만으로 새 설치·외부 전송·유료 호출·공개 배포 권한을 만들지 않는다.

구현 지시 후에는 승인된 구현·검증을 단계마다 다시 묻지 않고 이어간다. 새 빌드 도구가 필요하면 기존 설치를 먼저 확인하고 누락 도구·고정 버전·프로젝트 전용 설치 경로를 한 번에 정리한다. 설치 권한이 아직 없다면 그 설치만 남기고 필요한 소스·spec·문서 작업을 계속한다. 사용자 전역 Python, Isaac Python, 시스템 PATH/보안 설정은 변경하지 않는다.

기존 Flash/Nemotron 조합을 유지한다. 실물 로봇·유료 Cloud·새 시스템 설치·공개 업로드·commit/push는 본 계획의 실행 기본 범위에 포함하지 않는다. 원 dirty 변경·원사진·사용자 stage·실패 이력·미확정 비용을 보존한다.

## 9. 최종 납품과 판정

납품물은 EXE 폴더 ZIP, 정확한 source/build manifest와 SHA256, 빌드/실행/설치 가이드, 미해결 목록, **실제 화면을 포함한 하나의 로컬 HTML 보고서**다. 보고서에는 모든 시도와 source/package/input SHA, launch/generation/edit ID, 기능·사진 품질·복원·응답성 판정, 실패/NOT_RUN, 실제 사용 추정과 미확정 비용을 넣는다.

판정은 `EXE 패키지 실행`, `실제 생성 및 수정`, `설치 및 업데이트`, `새 PC`, `공개 배포 준비`로 나눈다. 사진 생성이나 새 PC가 미검증이면 전체 최종 배포 완료로 표시하지 않는다. 요구된 권한·도구·장비 안에서 할 수 있는 작업은 끝까지 수행하고, 남은 작업은 파일/실패 원인/다음 시험으로 구체화한다.

## 10. 후속 전용 창

폴더형 EXE가 안정화되고 사용자가 전용 창을 원하면 WebView2 등으로 기존 React 화면을 표시하는 얇은 shell을 검토한다. 백엔드·Isaac·저장 형식은 재작성하지 않는다. 파일 첨부/붙여넣기/다운로드, 외부 링크, 창 닫기/종료, 런타임 배포, 실제 Computer Use 지원을 추가 인수한다. 전용 창으로 바꾸면 현재 자동화의 URL 검증 문제가 자동 해결된다고 가정하지 않는다.

## 11. 공식 자료와 기존 근거

- [PyInstaller one-folder와 one-file 동작](https://pyinstaller.org/en/stable/operating-mode.html): Python 포함 배포, OS별 빌드, 먼저 one-folder 검증을 권장한다.
- [PyInstaller runtime 정보](https://pyinstaller.org/en/stable/runtime-information.html): frozen 환경의 `sys.executable`과 리소스 경로 의미를 확인한다.
- [PyInstaller 외부 프로그램 실행 주의점](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html): 자식 실행 환경과 DLL 검색 경계를 확인한다.
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases): 소스와 연결된 바이너리 배포 파일/릴리스 노트를 제공한다.
- [WebView2 배포](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution): 후속 전용 창에서 필요한 런타임 배포 조건이다.
- [기존 공개 배포 출처 정책](../RELEASE_PROVENANCE.md), [기존 App 전환 지침](TWINPULSE_APP_MIGRATION_PLAYBOOK.md), [생성 UX 원 인수 계획](TWINPULSE_GENERATION_UX_REPAIR_USER_ACCEPTANCE_SOL_PLAN_2026-10-13.md).

공식 문서는 패키징 기능에 대한 근거이고 TwinPulse의 실제 성공을 증명하는 자료는 아니다. 계획의 one-folder 우선순위와 단계 구분은 현재 코드·일정·실패 이력을 바탕으로 한 설계 판단이다.
