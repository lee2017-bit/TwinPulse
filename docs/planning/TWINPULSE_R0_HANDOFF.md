# TwinPulse R0 — 기준 소스 인수인계

- 날짜: 2026-09-15 KST
- 범위: App 전환 지침의 Step 0(R0)만. 새 React UI/API/물리 기능 구현 없음.
- 기준 root: `C:\Users\jaewo\Documents\TwinPulse` (기존 `main`, `origin=https://github.com/lee2017-bit/TwinPulse.git`, 통합 전 clean local HEAD `c35e9fcefdc632345ced482b789da385845b4e14`). 새 폴더/브랜치 없음.
- 보존 개발본: `C:\Users\jaewo\Documents\Codex\TwinPulse` (`main`, commit/remote 없음, 모든 소스 untracked). 삭제·이동·수정하지 않음.
- 사용자 D1: 로컬 React 웹 App + 별도 Isaac 3D 창. Isaac Extension은 엔진 adapter/검증 전 legacy UI로 유지.
- 사용자 D2: 새 개발 폴더가 특별히 필요하지 않으므로 기존 GitHub 연결 clone을 단일 기준으로 채택.

## 소스 inventory와 통합

두 root의 `rg --files` 소스 경로 집합과 SHA-256을 비교했다. 공통 중 동일 파일은 62개, 다른 파일은 아래 11개, 개발본 전용 신규 파일은 6개, clone 전용 보존 파일은 1개였다. `.git`, cache, artifacts, secrets, image binary는 비교·출력·복사 대상에서 제외했다. 통합 직전 clone은 clean이었고 이름 충돌은 없었다. M2-D 관련 17개 파일만 `Copy-Item -LiteralPath`로 복사한 후 각 원본/대상의 SHA-256 일치를 확인했다. 기존 개발본은 그대로 둔다.

| 분류 | 파일 |
|---|---|
| M2-D 신규 6 | `docs/verification/M2-D-dimensioned-floorplan-e2e.md`; `fixtures/m2d/dimensioned_floorplan.json`; `packages/twinpulse_provider/src/twinpulse_provider/measurement_constraints.py`; `scripts/create_m2d_floorplan_fixture.py`; `scripts/create_m2d_reference_report.py`; `scripts/evaluate_m2d_floorplan_result.py` |
| M2-D 관련 수정 11 | `README.md`; `docs/progress.md`; `extensions/twinpulse.extension/docs/CHANGELOG.md`; `extensions/twinpulse.extension/twinpulse/extension/extension.py`; `packages/twinpulse_provider/src/twinpulse_provider/__init__.py`; `contracts.py`; `providers.py`; `service.py`; `tests/test_provider.py`; `scripts/run_m2c_isaac_fixtures.py`; `scripts/run_m2c_provider_fixtures.py` (provider의 상대경로는 `packages/twinpulse_provider/` 아래) |
| clone 전용 보존 1 | `TWINPULSE_PRODUCT_SPEC_v1_2.md`; 최신 사용자 결정/기준선보다 앞선 이력으로 보존 |
| 동일 공통 62 | M2-C core/compiler/runtime/robot profiles/fixtures, scripts/config/기타 문서. 변경하지 않음 |

기준 문서 12개 `.md`를 이전 `outputs/`에서 이 저장소 `docs/planning/`으로 정확한 해시로 추가했다. 이후 이 저장소의 `docs/planning/TWINPULSE_PROJECT_MEMORY.md`, `TWINPULSE_BASELINE.md`, `TWINPULSE_APP_MIGRATION_PLAYBOOK.md`가 authoritative 문서다. 이전 폴더 `outputs/`는 R0 시점 이력/보존본이며 앞으로 양쪽을 병렬 편집하지 않는다. 이 저장소 `AGENTS.md`, `README.md`, `docs/progress.md` 및 이전 작업 폴더 `AGENTS.md`를 새 참조 위치로 맞췄다.

## 검증 및 제한

- `python -B packages/twinpulse_core/tests/test_contracts.py`: 24/24 PASS (Windows Python 3.12.10).
- `python -B packages/twinpulse_provider/tests/test_provider.py`: 13/13 PASS.
- `git diff --check`: whitespace 오류 없음. 통합 파일들은 나중에 commit 대상만 따로 검토한다.
- 실제 Isaac/Full viewport 및 현재 활성 Extension 경로: **NOT RUN/미확인**. Windows process command-line 조회가 OS access denied였고 기존 프로세스/unsaved stage는 건드리지 않았다. `scripts/launch_twinpulse.ps1`은 실행된 저장소 root의 `extensions`를 참조하므로, 다음 실제 실행에서 기준 clone 경로를 명시해야 한다.
- M2-D: 실제 과거 계획은 27/29; 새 이관은 그 정확도/도면→3D/sidecar 연결/복원 acceptance를 개선하지 않는다. sidecar generator의 2D `position_m`/`goal_m`와 실제 3D 도구의 `start_position_m`/`goal_position_m` 불일치, 새 입력과 이전 draft Build의 분리 실패는 R1 대상이다.
- GitHub 원격은 설정만 확인했다. fetch/push 없음. 이 문서의 `c35e9fc`는 **통합 전 로컬 HEAD**이며 원격의 최신 여부를 단정하지 않는다.

## 의존성/도구 확보안 (설치 없음)

현재 PATH에서 Node `v24.19.0`은 Codex bundled runtime에 있고 Windows Python `3.12.10`이 있다. `npm`, `cargo`, `rustc`, MSVC `cl`은 PATH에서 확인되지 않았다. 일반 Python의 FastAPI/Uvicorn/Pydantic import 위치는 발견됐으나 app 설치/구동 acceptance가 아니다. `pyproject.toml`은 **twinpulse-core만** 패키징하며 provider/Isaac Extension/app과 프런트엔드를 고정 설치하는 manifest/lock은 아직 없다. R3/R5 전에 app 전용 Python dependency lock/clean import, 프런트엔드 `package.json` 및 lock과 로컬 Node/npm 확보를 별도 제안·검증한다. 첫 웹+별도 Isaac 방식은 Tauri용 Rust/MSVC를 선행 필수로 만들지 않는다. 시스템 설치를 R0에서 수행하지 않았다.

## 체크포인트와 복구

이 R0 파일 묶음은 통합 전 clean commit `c35e9fc`에서 분리한 **31개 파일의 로컬 R0 commit**으로 기록했다. `git diff --cached --check` 통과 후 대상 파일만 commit했고 `main`은 `origin/main`보다 로컬로 1개 commit 앞서 있다. GitHub push는 하지 않았다. 현재 commit ID는 `git log -1 --format=%H`로 확인한다. rollback은 그 commit을 별도 `git revert`로 취소하는 방식을 우선한다; 이전 개발본은 원형 보존되어 재비교할 수 있다. `git reset --hard`나 기존 개발본 삭제는 하지 않는다.

다음 단계는 사용자에게 선택된 R1만이다. 이 checkpoint가 R1 또는 Phase 1 전체의 완료를 뜻하지 않는다.
