# TwinPulse 회사 PC 설치 및 확인

For the short English setup path, see [Quick Start](QUICKSTART.md). This longer Korean guide retains the detailed local/company verification history.

> **2026-09-25 환경 정정:** GitHub 가능 일반 PC는 배포물 다운로드·전달만 하고, RTX 3070 워크스테이션에서 웹 App·LLM 요청·Isaac 3D를 모두 실행한다. 로컬에서 릴리스 빌드·분할·재조립·wheel 설치를 시험했지만 **회사 워크스테이션에서 설치/LLM 연결/Isaac Build·Run은 검증하지 않았다.** PC 간 장면 파일 교환 및 일반 PC planner-only는 현재 범위가 아니다. [회사 배포 계획의 정정](planning/TWINPULSE_COMPANY_OFFLINE_DEPLOYMENT_PLAN_2026-09-25.md)을 참조한다.

이 문서는 TwinPulse 로컬 React App과 별도 Isaac Sim 3D 엔진의 현재 검증 스냅샷을 다른 Windows PC에서 실행하는 절차다. legacy Extension UI도 보존된다. ROS2, Isaac Lab, Docker는 이 단계에 필요하지 않다.

## 1. 개인 PC: 온라인 원클릭 경로

- Git
- NVIDIA Isaac Sim 6.0.1 standalone
- PowerShell
- CPython 3.12 (`py -3.12 --version`으로 확인)
- Node.js 20.19+ 또는 22.12+와 npm (`node --version`, `npm --version`으로 확인). pnpm이 없어도 설치기가 고정 버전을 사용자 npm cache에 내려받는다.
- LLM 생성을 시험할 경우에만 선택한 provider의 별도 API key

현재 개발 PC에서 검증한 런타임은 Isaac Sim `6.0.1-rc.7`, Kit `110.1.2`, bundled Python `3.12.13`이다. 회사 PC에 보고된 설치 경로는 아래와 같지만 실제 build/patch는 회사 PC에서 다시 확인해야 한다.

```text
D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64
```

## 2. 받기

처음 받는 경우:

```powershell
Set-Location C:\Users\<user>\Documents
git clone https://github.com/lee2017-bit/TwinPulse.git
Set-Location .\TwinPulse
```

이미 clone한 경우에는 로컬 변경이 없는지 먼저 확인한 뒤 가져온다.

```powershell
git status
git pull --ff-only origin main
```

API key는 저장소에 들어 있지 않으며 다른 PC에서 복사하지 않는다.

## 3. 원클릭 설치·실행

clone 후 탐색기에서 저장소의 **`Install-TwinPulse.cmd`를 더블클릭**한다. Isaac Sim이 표준 경로에 없으면 설치 root(`python.bat`, `isaac-sim.bat`이 있는 폴더)를 한 번 입력한다. 설치기는 `.venv` 생성, hash-locked Pillow 및 frozen `pnpm-lock.yaml` 의존성 설치, React 빌드, local App과 별도 Isaac 창 기동을 순서대로 수행한다. 앱을 닫을 때는 launcher 창에서 Ctrl+C를 누른다. 시스템 Python/Isaac Python을 수정하거나 API key를 복사하지 않는다. 첫 설치는 패키지 다운로드를 위한 네트워크가 필요하다. Isaac/Node/Python 자체의 설치는 자동화하지 않으므로 사전 준비해야 한다.

첫 설치 뒤 재실행은 저장소의 **`Start-TwinPulse.cmd`를 더블클릭**한다. 설치 때 지정한 Isaac 경로는 Git에서 제외된 `.runtime/isaac-root.txt`에 저장된다. 재실행은 Node 의존성 설치나 웹 빌드를 반복하지 않는다. 소스를 바꾸거나 업데이트한 뒤에는 `Install-TwinPulse.cmd`를 다시 실행해 웹을 재빌드한다.

경로를 명시하거나 설치와 실행을 분리하려면 다음을 사용한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

마지막에 `TWINPULSE_INSTALL_RESULT=PASS`가 나와야 한다. 실행까지 하려면 `-Launch`를 덧붙인다. 설치기는 재실행 가능하며 기존 `.venv`를 무조건 지우지 않는다. 개발 PC의 깨끗한 로컬 clone에서 설치/빌드와 비-Isaac 회귀를 통과했다. 그 clone의 실제 Isaac 기동과 회사 PC는 아직 직접 검증하지 않았다.

수동 설치가 필요하면 repository-local virtual environment에 Python 이미지 decoder를 설치한다. 이 명령은 고정된 Pillow wheel hash가 맞지 않으면 실패하며 시스템/Isaac Python을 수정하지 않는다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r config\python-runtime-requirements.lock
```

Pillow는 MIT-CMU 라이선스이며 product App은 `>=12.2,<13`, Windows lock은 `12.3.0`을 사용한다. launcher와 verifier는 `.venv\Scripts\python.exe`를 자동 선택한다. 인터넷이 차단된 회사 PC는 승인된 동일 wheel을 반입해 hash를 확인한 뒤 `.venv`에 설치해야 하며, wheel 자체를 Git에 커밋하지 않는다.

## 4. 자동 검증

PowerShell 실행 정책이 스크립트를 막는 경우 현재 창에만 임시 허용한다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

회사 PC의 실제 Isaac 경로로 전체 검증을 실행한다.

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

R6의 자동 App→실제 Isaac 검증까지 포함하려면 다음을 실행한다.

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64" -RunR6
```

마지막에 `TWINPULSE_VERIFY_RESULT=PASS`가 출력되어야 한다. 결과는 `artifacts\runs\<run-id>` 아래에 저장되며 Git에는 올라가지 않는다. `FAIL`이면 해당 폴더의 `manifest.json`, `verification-console.txt`, `isaac-result.json`을 확인한다.

순수 Python 계약만 빠르게 확인하려면 다음을 사용한다.

```powershell
.\scripts\verify_twinpulse.ps1 -SkipIsaac
```

## 5. 제품 App 다시 실행

실행 중인 TwinPulse launcher가 없고 필요한 작업을 저장했는지 확인한 뒤 다음 한 명령을 실행한다.

```powershell
.\scripts\launch_twinpulse_app.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

React production build 후 local backend와 launcher 소유 Isaac 엔진이 시작되고 기본 브라우저에 TwinPulse가 열린다. launcher를 종료하면 자신이 시작한 backend/Isaac만 정리하며 사용자가 별도로 실행한 Isaac을 종료하지 않는다.

빠른 재실행에는 위 스크립트 대신 `Start-TwinPulse.cmd`를 사용한다.

## 6. 회사 분리망: 준비된 릴리스 반입 경로

이 경로의 준비자는 인터넷/패키지 저장소가 허용된 Windows x64 + Python 3.12 + Node/pnpm 11.19.0 개발 환경에서 **검토·커밋된 깨끗한 소스**로 릴리스를 만든다. GPU/Isaac은 릴리스 빌드에 필요 없다. 회사의 GitHub 가능 일반 PC에서 npm/PyPI가 차단된다면 그 PC에서 빌드하지 말고 승인된 외부 빌드 환경에서 완성된 릴리스를 받아야 한다. 아직 GitHub에 배포용 릴리스 파일은 게시하지 않았다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_offline_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\split_offline_release.ps1 -ReleaseRoot ".\artifacts\offline-release\tp-REPLACE_WITH_COMMIT" -OutputRoot ".\artifacts\offline-transfer\tp-REPLACE_WITH_COMMIT"
```

`transfer-manifest.json`, `Reassemble-TwinPulse.cmd`, `scripts/reassemble_offline_release.ps1`과 모든 `.partNNNN`을 승인된 VDI 경로로 B에 옮긴다. 기본 조각 상한은 900,000,000 bytes이며 한 번에 한 조각씩 옮긴다. 각 조각은 단독 ZIP이 아니다. B에는 이미 Isaac Sim 6.0.1 standalone과 별도 **64-bit CPython 3.12**, 브라우저가 필요하다. B에서 Node/Git/npm/pnpm 또는 패키지 인터넷 접속은 설치·재실행에 필요하지 않다.

1. 받은 폴더의 `Reassemble-TwinPulse.cmd`를 실행한다. 누락/손상 조각은 번호와 함께 거부된다.
2. 생성된 `unpacked\<release-id>\Install-Offline.cmd`를 실행한다. Isaac 경로를 찾지 못하면 설치 root를 입력한다. 설치기는 파일 SHA-256을 확인하고 로컬 wheelhouse만 사용해 버전별 `.venv`를 만든다.
3. 설치 완료 메시지에 표시된 `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd`로 다시 실행한다. 설치는 패키지 다운로드 없이 가능하지만 **기본 실행은 live LLM 모드**다. 워크스테이션에서 승인된 Nebius endpoint와 API key를 설정해야 새 이미지를 생성할 수 있다. `scripts\start_twinpulse_installed.ps1 -Offline`은 새 LLM 생성을 서버에서 차단하는 별도 진단 모드다.

API key/사용자 입력/Isaac 전체 설치본은 릴리스에 들어가지 않는다. 반입 조각과 함께 온 SHA-256은 무결성 확인이지 배포자 신원 증명이 아니므로, 신뢰하는 경로의 릴리스 digest도 대조해야 한다. PowerShell 실행 정책 우회가 회사의 AppLocker/WDAC 또는 반입 정책을 우회하는 수단은 아니다. 차단되면 승인된 사내 절차를 따른다.

로봇의 App **No-motion evidence collection** 버튼은 설치/시작과 별개의 명시적 현장 동작이다. 버튼은 기존 소스 전송과 정지 상태 raw odom/scan/TF 수집을 시도하지만 모터 이동·라이다 드라이버 기동·전체 데모 승인을 하지 않는다. 릴리스에는 이 동작에 필요한 로컬 코드·수집 계약시험을 포함하고 개인 방 사진/과거 스캔은 자동 포함하지 않는다. 새 릴리스의 전체 빌드·회사 PC 실행·실제 로봇 접속은 아직 검증되지 않았다. [PC-only 근거](verification/demo-dp1-app-no-motion-collection-20260930.md).

여기서 **오프라인은 설치 의존성 반입 방식**을 뜻하며, 기본 실행의 LLM 추론까지 오프라인이라는 뜻은 아니다. 워크스테이션의 Nebius API 연결 가능 여부는 미확인이다. 사내 LLM이 VDI에서만 가능하다는 사실만으로 워크스테이션에서 접근 가능하다고 가정하지 않는다. 연결이 없다면 현장에서는 새 이미지의 live 생성이 불가능하며, 별도로 승인된 네트워크 경로 또는 개인 PC 데모 경로를 결정해야 한다. Isaac의 Kit extension 의존성과 RTX 3070의 작은 실제 장면 안정성도 현장 확인이 필요하다.

## 7. Legacy Extension UI에서 실행

실행 중인 Isaac Sim을 모두 정상 종료한 다음 아래 명령을 실행한다.

```powershell
.\scripts\launch_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

첫 시작은 Extension 의존성 확인 때문에 수 분 걸릴 수 있다. Full 앱이 뜨면 **TwinPulse Copilot** 창이 자동으로 열려야 한다. 창이 없으면 Isaac Sim을 완전히 종료하고 위 launcher로 다시 시작한다. 수동으로 등록할 때는 이 저장소의 `extensions` 폴더를 Extension search path에 추가하고 `twinpulse.extension` 버전 `0.1.0`을 활성화한다.

## 8. LLM 설정과 사용

LLM 요청은 선택 사항이며 비용이 발생할 수 있다. 자동 검증은 유료 요청을 보내지 않는다.

1. 웹 App 상단의 **AI settings**를 연다.
2. Nebius 실험은 앱의 고정 `Nebius Token Factory` preset(Gemma observer→NVIDIA Nemotron planner)을 선택한다. OpenAI를 사용할 경우에만 OpenAI preset과 `https://api.openai.com/v1/`를 사용한다.
3. 해당 PC에서 만든 provider API key를 입력하고 설정을 저장한다. 키는 PC 간 복사되지 않는다.
4. 이미지와 선택적 자연어 제약을 입력하고 **Create Draft**를 누른다.
5. 초안의 tool/object 수와 개략성 경고를 검토·확인한 뒤 **Build in Isaac Sim**을 누른다.
6. **Run**, **Pause**, **Reset**으로 시험한다.

키는 프로젝트 파일이 아니라 해당 Windows 사용자의 Credential Manager에 provider/profile binding별로 저장되므로 PC 재시작 뒤에도 유지된다. 비밀이 아닌 Base URL/model/reasoning과 adapter/profile/endpoint/capability/credential reference만 `%LOCALAPPDATA%\TwinPulse\runtime\provider_settings.json`에 저장된다. 웹 API는 키 자체를 반환하지 않고 저장 여부만 표시한다. 동일한 provider binding에서는 키 입력칸을 비워 저장하면 기존 키를 유지한다. Base URL의 origin 또는 protocol을 바꾸면 새 키를 입력하거나 체크박스로 기존 키 사용을 명시적으로 재승인해야 한다. 설정 저장, capability 확인, key 저장, 실제 live 요청 성공은 서로 다른 상태다. 키, 인증 헤더, 이미지 바이트는 draft 기록이나 Git에 저장하지 않는다.

## 8. 현재 검증 범위와 제한

기존 M2-C와 R0~R5 회귀에 더해 2026-09-22 개발 PC에서 R6 local deterministic managed-launcher E2E가 PASS했다. R6 artifact는 `artifacts/runs/20260922-100347/r6-app`이며 로컬 전용이라 Git에는 포함되지 않는다.

- R6 process manager 5/5, product API 9/9, React 5/5, production build PASS
- S1d 추가 검증: Windows Job Object 후손 정리, 실행별 state 격리, stale heartbeat Run 차단; Python 28/28, React 10/10/build, actual Isaac graceful/forced 종료 PASS
- S2a 추가 검증: PNG/JPEG/VP8/VP8L bounded full decode, image hash/dimension-bound sidecar 1.1, immutable MIME/measurement/profile/settings/catalog identity; Python 100/100과 official non-Isaac run `20260924-091108` PASS
- authenticated backend/actual-Isaac readiness, 32 prim scene, applied revision 일치
- Run/Pause/Reset/Focus와 최대 0.329136 m 이동
- browser desktop/mobile/125% 및 official Isaac viewport 960×640 capture PASS
- Extension enable/disable 3/3
- short Run/Reset 3/3
- generated/fallback/rollback 계약
- `agv_compact_2wd_caster_v2`: 좌우 2개 구동륜 + 앞뒤 passive caster 2개
- 18 x 12 m 대형 바닥 Mesh 계약과 6.9 m 경로: goal error 0.049289 m, 최대 cross-track 0.004352 m, pitch 0.0668°, roll 0.0762°, 충돌 sample 0
- 실제 이미지에서 저장된 8 m 플랜 재생: 1,889 frames에 완료, goal error 0.2465 m(허용 0.25 m), pitch 0.0738°, roll 0.0862°

이전 persisted-plan의 roll 9.0393° 안전 정지는 대형 바닥을 non-uniform scale Cube collider로 만든 컴파일 결함이 원인이었고, 실제 치수의 closed Mesh로 교체해 위 재생과 대형 바닥 회귀가 통과했다. S2d에서는 저장된 M2-C 세 장면을 새 managed Isaac 경로로 재생해 통과했다. 2026-09-25에는 Nebius live 1장면을 90 prim으로 Build하고 2WD AGV를 목표까지 주행시켰다. 다만 랙 배열이 사진과 불일치했고 overlap guard를 추가한 뒤 새 live 재시험은 하지 않았다. 이 결과가 임의 LLM 장면 전체의 시각·물리 안정성을 보장하지 않는다. fresh clone/회사 PC 재현은 별도 확인이 필요하다. 현재 버전은 Playground prototype이며 실물 AGV 제어·배포에 사용하면 안 된다.

회사 PC는 개발 PC와 별도 환경이므로 `-RunR6` 자동 검증 결과와 생성된 브라우저/Isaac capture를 확인해야 회사 PC 재현 성공으로 기록할 수 있다. 사용자가 화면을 수동 촬영해 전달할 필요는 없다.

## 9. 흔한 문제

- `Isaac Sim launcher not found`: `-IsaacRoot`가 `isaac-sim.bat`과 `python.bat`이 있는 폴더를 가리키는지 확인한다.
- Node/npm을 찾을 수 없음: 지원 Node.js를 설치하고 새 PowerShell에서 `node --version`, `npm --version`을 확인한다. `pnpm`이 없으면 원클릭 설치기가 npm으로 고정 pnpm을 가져온다. Codex 전용 bundled 경로를 영구 PATH로 복사하지 않는다.
- `TwinPulse Python image decoder is missing`: 위 `.venv` 생성 및 hash-locked Pillow 설치를 실행한다. 전역 `pip install`이나 Isaac bundled Python 변경으로 우회하지 않는다.
- Copilot 창이 없음: 모든 Isaac/Kit 프로세스를 종료한 뒤 제공된 launcher로 다시 실행한다.
- `API key saved`에서 진행되지 않음: 이미지 또는 설명을 넣고 **Create Draft**를 눌렀는지, 계정 API 사용량/권한, Base URL과 Model ID를 확인한다. 키 저장은 실제 생성 성공을 뜻하지 않는다.
- strict plan 오류: 버튼 아래의 정확한 validation 원인과 PowerShell 로그를 보관한다. 실패를 sample scene으로 자동 대체하지 않는다.
- 화면이 검게 보임: 초기 렌더링을 기다린 뒤 **Show 3D View**를 누른다. 이 PC에서는 최초 부팅이 오래 걸린 적이 있다.

### 현재 개발 소스의 시작 진단(아직 회사 PC 재검증 전)

2026-09-29 개발 소스에서는 인증된 App 화면이 backend 준비 후 열려 Isaac 시작 단계를 보여준다. Isaac import와 `SimulationApp` 초기화 실패는 서로 구분하며, 오류 화면의 **Save safe diagnostic summary**는 관측된 Python/NumPy/SciPy 버전·출처 분류와 제한된 상태만 저장한다. 이 파일에는 원시 exception/traceback, 경로, 회사 사진, API key 또는 전체 로그를 넣지 않는다. 해당 파일의 `origin_class`만으로 충돌 원인을 단정하거나 Isaac Python의 NumPy/SciPy 폴더를 복사·교체하지 않는다. 로컬 소유 엔진 로그는 회사 승인 절차에 따라 별도로 검토하고 공유 전 민감정보를 제거한다.

오류 때 **Retry startup**은 기존 런처가 소유한 backend/engine을 종료한 후 새 인증 세션으로 한 번 재시작한다. 자동 반복은 없다. 오래 걸리는 시작은 **Cancel this startup**으로 해당 런처 자식만 정리할 수 있다. 두 버튼은 설치 수정이나 원인 복구가 아니며, 성공 표시가 나오기 전 Build/Run은 잠겨야 한다. 회사 PC의 실제 설치 조합과 GPU/Kit 시작·시각 품질은 여기서 검증하지 않았고, 개발 PC의 오프라인 시험으로 대체할 수 없다.

문제 보고 시 API key를 가리고 `artifacts\runs\<run-id>`의 비밀값 없는 결과 파일과 화면 캡처만 공유한다.
