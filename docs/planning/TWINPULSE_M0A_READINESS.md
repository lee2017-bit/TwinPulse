# TwinPulse M0-A — 실행 대상 및 작업 경로 Readiness

- 조사일: **2026-09-12 (KST)**
- 연결 기준: **Baseline v1.0.3**
- 수행 범위: 비파괴 로컬 조회 및 이 결과 문서 작성
- 단계 / 상태: **PASS**
- 의미: M0-A의 로컬 조사와 사용자 결정이 완료됐다. 개발 root는 승인됐고, 현재 PC는 순수 Extension 코드 개발에 사용하며 목표 6.0.1 runtime 검증은 회사 PC에서 수행한다. M0-B 자체는 아직 NOT RUN이다.

## 1. 결론

현재 Codex가 접근하는 host는 회사 설치 안내서의 RTX 3500 Ada PC가 아니라, RTX 2070 Max-Q가 장착된 Windows 10 PC다. 이 host에는 `C:\isaacsim`의 Isaac Sim 5.1.0이 있으나 목표인 Isaac Sim 6.0.1은 확인한 예상 경로에 없다.

권장 분리는 다음과 같다.

| 역할 | 권장 대상 | 현재 판정 |
|---|---|---|
| 문서·순수 Python/schema 개발 | 현재 PC의 신규 독립 프로젝트 root | 사용자 승인 완료. M1-A에서 생성 |
| 첫 Isaac 6.0.1 M0-B smoke test | 회사 PC의 보고된 6.0.1 환경을 우선 직접 재검증 | 이 세션에서 접근 불가 |
| 최종 full Isaac Sim 실행 | 승인된 RT 지원 GPU 서버, 우선 L40S 계열 검토 | 계정·quota·비용·접근 미확인 |

현재 PC에서 5.1을 사용해 M0-B를 통과시키거나, 회사 문서의 결과를 현재 실행 증거로 대체하지 않는다.

## 2. 개발 root

### 현재 문서 작업 폴더

`C:\Users\jaewo\Documents\Codex\2026-09-12\dl`

- Codex의 날짜별 projectless 문서 작업 폴더다.
- `AGENTS.md`, `outputs`, 빈 `work`만 있으며 제품 소스는 없다.
- 현재 폴더와 상위에서 Git repository를 찾지 못했다.
- Baseline, 프로젝트 메모리, Sol 지시서의 authoritative 원본은 현재 `outputs`에 있다.

### 확정된 신규 제품 root

`C:\Users\jaewo\Documents\Codex\TwinPulse`

- 사용자가 이 경로의 사용을 승인했다. **M0-A에서는 생성하지 않았으며 M1-A 시작 시 생성한다.**
- 날짜별 문서 산출물 폴더와 제품 소스를 분리하면서 이 작업 환경의 쓰기 가능한 범위에 둔다.
- `C:\isaacsim` vendor runtime 및 무관한 기존 PoC와 분리한다.
- M1-A에서 신규 Git repository와 최소 프로젝트 구조를 생성한다.
- 승인 시 현재 Baseline·메모리·playbook과 프로젝트 지침을 신규 root의 `docs`/`AGENTS.md`로 이전 또는 연결하고 authoritative 위치를 하나로 정한다.

경로는 확정됐지만 M0-A의 read-only 범위를 지켜 신규 디렉터리나 Git repository는 아직 만들지 않았다.

## 3. 현재 접근 host — 직접 확인

| 항목 | 확인값 | 근거/비고 |
|---|---|---|
| host | `DESKTOP-511RPFE` | 현재 프로세스의 machine name |
| OS | Windows 10 Pro 22H2, build 19045.6466 | Windows registry read |
| CPU | Intel Core i7-10750H | processor registry read |
| GPU | NVIDIA GeForce RTX 2070 Max-Q | `nvidia-smi` 읽기 조회 |
| VRAM | 총 8192 MiB, 당시 여유 8006 MiB | 변동 가능한 조사 시점 값 |
| GPU driver | 592.82 | `nvidia-smi` |
| RAM | 총 15.77 GiB, 당시 가용 6.45 GiB | OS memory counter |
| C: | 사용 393.6 GiB, 당시 여유 76.8 GiB | filesystem 조회 |
| D: | 당시 여유 약 0.5 GiB | 회사 안내서의 D: 경로를 이 host에 적용할 수 없음 |
| 일반 Python | `C:\Users\jaewo\AppData\Local\Programs\Python\Python312\python.exe`, 3.12.10 | `python --version`; Isaac 내장 Python과 별개 |
| Git / rg | Git 2.53.0.windows.2, ripgrep 15.2.0 | 순수 코드 작업 도구 사용 가능 |

VRAM·RAM·디스크의 여유량은 실행 중 변하므로 M0-B 직전에 실행 host에서 다시 측정한다.

## 4. Isaac root 및 목표 runtime

### 현재 host에서 확인됨

| 항목 | 값 |
|---|---|
| Isaac root | `C:\isaacsim` |
| VERSION | `5.1.0-rc.19+release.26219.9c81211b.gl` |
| Kit | `107.3.3+production.229672.69cbf6ad.gl` (`kit-core.json`), launcher `107.3.3` |
| 내장 Python | `C:\isaacsim\kit\python\python.exe`, 파일 product version 3.11.13 |

`C:\isaacsim\VERSION`, Kit 설정 파일과 실행 파일 metadata를 읽었다. Isaac/Kit application과 내장 Python은 실행하지 않았다.

### 현재 host에서 확인한 예상 경로 — 모두 없음

- `C:\isaacsim-6.0.1`
- `C:\IsaacLab`
- `D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64`
- `D:\IsaacLab`
- `D:\isaacsim_assets`

이는 위 예상 경로의 결과이며 디스크 전체에 대한 부재 증명은 아니다. 그러나 현재 알려진 정보로는 이 host에 목표 6.0.1 Isaac root를 지정할 수 없다. 또한 이 PC는 Baseline에 기록된 공식 6.0.1 최소 OS/RAM/GPU 기준에 미달하므로 full runtime의 권장 실행 host로 삼지 않는다.

## 5. 회사 PC와 GPU 서버 — 현재 세션에서 미확인

### 회사 PC

회사 재설치 안내서에는 다음이 보고되어 있다.

- `D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64`
- `D:\IsaacLab`
- RTX 3500 Ada 약 12GB, driver 580.92
- 일부 import/CUDA/화면/USD 로딩 성공과 PhysX CUDA error 700 등 오류가 함께 기록됨

현재 host의 D:에는 이 경로가 없고 하드웨어도 다르므로 회사 PC를 직접 조회한 것으로 볼 수 없다. 회사 PC의 실제 OS/RAM/여유 디스크, 파일 존재, VERSION/Kit/Python, 현재 driver, PhysX 동작은 모두 M0-B 전에 재확인해야 한다.

### GPU 서버

이 세션에서는 Nebius 계정, AI Cloud project, quota/credit, region, RT GPU 재고 또는 서버 SSH/WebRTC 접근을 조회하지 않았다. 서버를 생성하거나 비용을 발생시키지 않았다. Token Factory API 접근 여부도 이번 단계 대상이 아니다.

## 6. 지금 가능한 일과 실제 runtime 시험의 분리

### 현재 PC에서 가능한 범위

- 신규 root가 승인되면 Python 3.12.10과 표준 도구로 M1-A의 순수 schema/core를 개발한다.
- SceneSpec, RobotProfile, TaskSpec, serialization, validation 및 fixture 단위시험을 Isaac import 없이 작성한다.
- Extension manifest와 adapter interface를 정적으로 준비할 수 있으나, 6.0.1 API 동작을 확인하기 전 runtime PASS로 기록하지 않는다.
- dependency가 없는 표준 라이브러리부터 시작할 수 있다. 새 package가 필요하면 실제 필요성과 격리 방식을 먼저 제시한다.

### 현재 PC에서 완료할 수 없는 범위

- Isaac Sim 6.0.1/Kit 110.1.2의 실제 import 및 API 검증.
- 6.0.1에서의 extension enable/disable/reload.
- physics 기반 AGV 직진·회전, collider, pause/reset, PhysX/CUDA 안정성 시험.
- 회사 PC의 오류 재현·해결 확인.
- GPU 서버 E2E와 과금/네트워크 검증.

## 7. 최소 접근·설치 계획

### 권장 경로 A — 회사 PC 우선

1. 회사 PC에서 이 작업의 기준 문서와 M0-B 지시를 열거나, 이 Codex 세션이 해당 PC를 직접 조회할 수 있게 한다.
2. 설치를 건드리기 전에 OS/GPU/driver/RAM/disk, 실제 Isaac/Lab 경로, VERSION/Kit/Python과 Git 상태를 읽기 조회한다.
3. 기존 6.0.1이 정확히 확인되면 M0-B의 최소 physics/AGV smoke test를 승인된 새 테스트 폴더에서 수행한다.
4. 설치가 없거나 손상됐으면 기존 5.x 또는 자료를 삭제하지 않고, 대상 경로·필요 용량·버전·보존 계획을 적은 별도 설치 승인안을 먼저 제출한다.
5. 회사 GPU에서 최소 scene이 실패하거나 요구 성능을 충족하지 못하면 RT GPU 서버로 전환한다.

### 대안 경로 B — RT GPU 서버

M4-A의 read-only 배포/비용 승인안을 먼저 수행한 뒤, 사용자에게 승인받은 region·RT GPU·시간·비용 상한으로 M0-B/M4-B를 결합하지 않고 각각의 acceptance를 실행한다. H100/H200을 full Isaac Sim GPU로 자동 선택하지 않는다.

### 현재 PC 재설치안

권장하지 않는다. 목표 6.0.1이 없다는 이유만으로 `C:\isaacsim`의 5.1을 삭제하거나 D:에 설치하지 않는다. D: 여유 0.5 GiB는 회사 안내서 경로를 수용할 수 없다.

## 8. 사용자 결정과 다음 단계 권한

### 2026-09-12 확정된 결정

1. 개발 root는 `C:\Users\jaewo\Documents\Codex\TwinPulse`를 사용한다.
2. 초기 목표는 Isaac Sim Extension이다. 이에 직접 필요한 단계만 먼저 수행한다.
3. M0-B는 Extension의 대상 runtime 검증에 필요하므로 생략하지 않는다. 다만 현재 PC의 Isaac 5.1에서 수행해 목표 6.0.1 검증으로 간주하지 않는다.
4. 현재 PC에서는 M1-A 순수 core/schema를 먼저 진행한다. M0-B와 M1-B의 실제 Extension/physics 검증은 회사의 6.0.1 PC에서 수행한다. 회사 PC가 실패하거나 사용할 수 없을 때 RT GPU 서버를 fallback으로 검토한다.

### M0-B를 회사 PC에서 수행할 경우

- 회사 PC에서 이 작업을 실행하거나 해당 host의 파일·명령에 접근할 방법.
- 우선 비파괴 환경 조회 권한.
- 조회 후 별도로: 기존 Isaac Sim 6.0.1 실행과 지정된 신규 테스트 폴더 쓰기 승인.
- 설치가 필요할 때만: 정확한 설치 대상과 예상 용량을 제시한 후 설치 승인.

### 현재 PC에서 M1-A를 수행할 경우

- 위 신규 개발 root 사용은 승인됐다. M1-A 요청 시 그 안의 Git/code/test 문서 쓰기를 수행한다.
- 표준 라이브러리만으로 시작하면 추가 시스템 권한은 필요하지 않다.
- 새 dependency 설치가 필요하면 M1-A에서 구체적인 package/version/격리 범위를 제시한다.

## 9. 이번 단계에서 수행하지 않은 작업

- Isaac Sim/Kit 실행: **NOT RUN**
- Isaac Lab/ROS2/Pixi/WSL/Docker 실행 또는 설치: **NOT RUN**
- package 설치, 기존 파일 삭제, driver/OS/방화벽 변경: **NOT RUN**
- API key 요청/출력, 외부 API 호출: **NOT RUN**
- Nebius 자원 생성·과금·포트 공개: **NOT RUN**
- 실물 AGV 연결·구동: **NOT RUN**
- 신규 TwinPulse 제품 root/Git repository 생성: **NOT RUN — M1-A에서 수행**

## 10. 검증 기록

비파괴로 사용한 조회 범주:

- Windows registry와 runtime property를 통한 host/OS/CPU/RAM 조회.
- `nvidia-smi` query를 통한 GPU/VRAM/driver 조회.
- filesystem/known-path 존재 여부와 VERSION/Kit/Python metadata 읽기.
- `git rev-parse`, `git status`, tool version을 통한 현재 workspace 상태 확인.
- Baseline·메모리·Sol playbook 전체/관련 절 확인.

### 상태 요약

| 하위 항목 | 상태 | 근거 |
|---|---|---|
| 기준 문서 인수 | PASS | Baseline v1.0.1, 메모리, 공통 규칙과 M0-A 읽음 |
| 현재 host inventory | PASS | 위 직접 조회값 기록 |
| 현재 workspace/Git 확인 | PASS | 제품 소스/Git 없음 확인 |
| 개발 root 확정 | PASS | 사용자가 권장 경로 사용 승인. 실제 생성은 M1-A 범위 |
| Isaac 6.0.1 실행 정책 | PASS | 회사 PC 우선 검증, 실패/불가 시 RT GPU 서버 fallback |
| 회사 6.0.1 host 접근 | BLOCKED | M0-B 수행 시 회사 PC에서 작업을 열거나 접근 방법 필요 |
| 목표 runtime 실행 검증 | NOT RUN | M0-B 범위이며 이번 단계에서 금지 |

## 11. 변경 결정

제품 요구사항은 변경하지 않았다. Baseline을 v1.0.3으로 갱신해 사용자가 승인한 개발 root와 초기 Extension 작업의 실행 순서를 기록했다. 현재 PC의 volatile 여유 RAM/디스크 값은 본 문서에 조사 시점 값으로 기록했으며, 최초 Baseline snapshot을 과거 사실로 보존했다.

## 12. 다음

다음 작업은 현재 PC에서 **M1-A** 순수 core/schema를 수행하는 것이다. M1-A 시작 시 승인된 root를 생성한다. 그 뒤 회사 PC가 준비되면 **M0-B**를 수행하고, 통과 후 **M1-B**에서 실제 Extension을 로드·검증한다. M0-B가 끝날 때까지 runtime PASS는 계속 미통과 상태다.

다음 단계는 자동으로 시작하지 않는다.
