# TwinPulse 회사 PC 설치 및 확인

이 문서는 TwinPulse Isaac Sim Extension의 현재 검증 스냅샷을 다른 Windows PC에서 실행하는 절차다. ROS2, Isaac Lab, Docker는 이 단계에 필요하지 않다.

## 1. 준비 사항

- Git
- NVIDIA Isaac Sim 6.0.1 standalone
- PowerShell
- LLM 생성을 시험할 경우에만 OpenAI Responses API를 사용할 수 있는 별도 API key

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

## 3. 자동 검증

PowerShell 실행 정책이 스크립트를 막는 경우 현재 창에만 임시 허용한다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

회사 PC의 실제 Isaac 경로로 전체 검증을 실행한다.

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

마지막에 `TWINPULSE_VERIFY_RESULT=PASS`가 출력되어야 한다. 결과는 `artifacts\runs\<run-id>` 아래에 저장되며 Git에는 올라가지 않는다. `FAIL`이면 해당 폴더의 `manifest.json`, `verification-console.txt`, `isaac-result.json`을 확인한다.

순수 Python 계약만 빠르게 확인하려면 다음을 사용한다.

```powershell
.\scripts\verify_twinpulse.ps1 -SkipIsaac
```

## 4. Isaac Sim에서 실행

실행 중인 Isaac Sim을 모두 정상 종료한 다음 아래 명령을 실행한다.

```powershell
.\scripts\launch_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

첫 시작은 Extension 의존성 확인 때문에 수 분 걸릴 수 있다. Full 앱이 뜨면 **TwinPulse Copilot** 창이 자동으로 열려야 한다. 창이 없으면 Isaac Sim을 완전히 종료하고 위 launcher로 다시 시작한다. 수동으로 등록할 때는 이 저장소의 `extensions` 폴더를 Extension search path에 추가하고 `twinpulse.extension` 버전 `0.1.0`을 활성화한다.

## 5. LLM 설정과 사용

LLM 요청은 선택 사항이며 비용이 발생할 수 있다. 자동 검증은 유료 요청을 보내지 않는다.

1. **Settings**를 연다.
2. Base URL은 OpenAI 사용 시 `https://api.openai.com/v1/`로 둔다.
3. Model ID는 현재 기준 `gpt-5.6-luna`, Reasoning effort는 `low`다.
4. 회사 PC에서 만든 API key를 API Key 칸에 붙여 넣고 **Save Settings**를 누른다.
5. 이미지와 선택적 자연어 제약을 입력하고 **Generate with LLM**을 누른다.
6. `DRAFT VALID`와 tool/object 수를 검토한 뒤 **Build Generated Scene**을 누른다.
7. **Run / Resume**, **Pause**, **Reset**으로 시험한다.

키는 프로젝트 파일이 아니라 해당 Windows 사용자의 Credential Manager에 저장된다. `KEY SAVED`는 저장 상태이고 실제 요청 성공 뒤에만 `LLM CONNECTED`가 표시된다. 키, 인증 헤더, 이미지 바이트는 draft 기록이나 Git에 저장하지 않는다.

## 6. 현재 검증 범위와 제한

2026-09-13 개발 PC에서 다음 안정 기준이 PASS했다.

- core 23/23, provider 8/8
- Extension enable/disable 3/3
- short Run/Reset 3/3
- generated/fallback/rollback 계약
- `agv_compact_2wd_caster_v2`: 좌우 2개 구동륜 + 앞뒤 passive caster 2개
- 고정 6.9 m 경로: goal error 0.049306 m, 최대 cross-track 0.000825 m, pitch 0.0306°, roll 0.0433°, 충돌 sample 0

하지만 임의 LLM 장면 전체의 물리 안정성을 보장하지 않는다. 실제 이미지에서 생성·저장된 한 플랜은 구조 검증과 3D Build에는 성공했으나 이후 deterministic replay에서 roll 9.0393°로 안전 정지했다. 서로 다른 이미지 3개 M2-C 평가는 아직 수행하지 않았다. 따라서 현재 버전은 Playground prototype이며 실물 AGV 제어·배포에 사용하면 안 된다.

회사 PC는 개발 PC와 별도 환경이므로 위 자동 검증 PASS와 Full 앱 화면에서 Build/Run/Reset을 직접 확인해야 회사 PC 재현 성공으로 기록할 수 있다.

## 7. 흔한 문제

- `Isaac Sim launcher not found`: `-IsaacRoot`가 `isaac-sim.bat`과 `python.bat`이 있는 폴더를 가리키는지 확인한다.
- Copilot 창이 없음: 모든 Isaac/Kit 프로세스를 종료한 뒤 제공된 launcher로 다시 실행한다.
- `KEY SAVED`에서 진행되지 않음: 이미지 또는 설명을 넣고 **Generate with LLM**을 눌렀는지, 계정 API 사용량/권한, Base URL과 Model ID를 확인한다.
- strict plan 오류: 버튼 아래의 정확한 validation 원인과 PowerShell 로그를 보관한다. 실패를 sample scene으로 자동 대체하지 않는다.
- 화면이 검게 보임: 초기 렌더링을 기다린 뒤 **Focus Scene**을 누른다. 이 PC에서는 최초 부팅이 오래 걸린 적이 있다.

문제 보고 시 API key를 가리고 `artifacts\runs\<run-id>`의 비밀값 없는 결과 파일과 화면 캡처만 공유한다.
