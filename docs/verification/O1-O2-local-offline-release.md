# O1/O2 로컬 오프라인 릴리스 검증 — 2026-09-25

> 후속 범위 정정: 아래는 시험 당시의 증거 기록이다. 이후 사용자 결정으로 O3 PC 간 장면 교환과 O4 planner-only는 철회되었으므로 아래의 O3/O4 선행조건은 더 이상 유효하지 않다. 현재 목표는 다운로드 PC에서 릴리스를 전달한 뒤 GPU 워크스테이션 하나에서 App·LLM 요청·Isaac을 실행하는 것이다. offline 설치와 실행 중 LLM 네트워크 요구는 별개이며 `-Offline`은 진단 옵션이다. 최신 단계는 [통합계획 H0~H8](../planning/TWINPULSE_HACKATHON_DEMO_MASTER_PLAN_2026-09-25.md)을 따른다. 과거 시험 결과를 새 회사 환경 PASS로 승격하지 않는다.

범위: 개인 PC 빠른 재실행, Windows x64/CPython 3.12용 prebuilt UI+hash-locked Pillow 릴리스, 900MB 이하 조각 분할/해시 확인/재조립, GPU PC의 Node·PyPI 없는 설치, 명시적 `simulation_offline`에서 provider 생성 금지. **회사 PC·cold Kit/Isaac 실제 기동·장면 이관 acceptance가 아니다.**

## 실행한 검증

- 개발 PC의 dirty 소스에서 `-AllowDirty`로 **로컬 테스트 전용** 릴리스 `tp-local-smoke3-20260925` 생성: 59개 allowlisted 파일, 8,032,748 bytes, Pillow 12.3.0 Windows cp312 wheel 포함, React frozen pnpm 11.19.0 build PASS. dirty 릴리스는 일반 `Install-Offline.cmd`가 거부한다.
- `-PartBytes 3000000` 축소 시험: 7,443,807-byte ZIP을 3개 조각으로 분할, 각 SHA-256/전체 SHA-256 재검증 후 byte-identical 재조립 PASS. manifest만 있고 조각이 없는 경우 `Missing transfer part: ...part0001`로 추출 전 거부 PASS.
- 재조립본을 별도 `artifacts/offline-install-smoke4`에 설치: `pip --no-index --find-links ... --require-hashes`로 Pillow wheel만 설치하고 `TWINPULSE_OFFLINE_INSTALL=PASS`; 설치된 `.venv`에서 launcher `--offline` 옵션을 로드. 기존 설치/개인 credential을 건드리지 않음.
- 테스트용 이전 릴리스 `tp-local-smoke2-20260925`에서도 이동한 `.venv`의 Python/Pillow 12.3.0 import 확인. 최종 smoke4에 대해서는 actual Isaac window, browser E2E, Kit extension dependency closure를 실행하지 않았다.
- `scripts/verify_twinpulse.ps1 -SkipIsaac` 공식 회귀 `artifacts/runs/20260925-185146`: Core 30, Provider 27, R1 9, R3 9, R4 6, R5/S2/S3 35, R6 11, React 10 및 production build PASS. 신규 offline workflow 테스트에서 `generation_unavailable_offline`, gateway 호출 0회를 확인했다.
- 설치 경로 보완 뒤 최종 로컬 테스트 묶음 `tp-local-smoke4-20260925`(59 files, 8,036,750 bytes)을 다시 생성하고 manifest/Python 3.12/Isaac prerequisite `-CheckOnly` PASS. 현재 사용자 launcher lock이 존재하여 실행 중 앱을 건드리지 않도록 이 최종 묶음의 실제 재설치·Isaac 기동은 보류했다. 위 no-index 설치 PASS는 직전 smoke3 묶음에 대한 결과다.

## 알려진 경계와 다음 단계

- 회사 A/B 두 PC와 VDI의 실제 실행 정책, Python 설치, Isaac build, RTX 3070/VRAM 및 Kit local dependency는 미실측. 회사 설치 PASS는 `NOT_RUN`.
- source-only GitHub checkout은 B에서 실행 준비가 완료된 bundle이 아니다. 이 소스를 검토·커밋하고 clean release를 빌드한 후, 승인된 경로로 release + transfer manifest를 게시/반입해야 한다. 이번에는 commit/push/release 업로드 없음.
- `simulation_offline`은 LLM/키 없이 앱과 Isaac 실행을 목표로 하지만 fresh B에서 임의 생성 장면을 가져올 제품 `.twinpulse-scene` export/import는 아직 없다. O3/O4가 완료되기 전 회사 전체 사용 흐름 PASS로 표시하지 않는다.
- 업데이트는 버전별 폴더에 설치하고 active release pointer를 교체한다. 기존 버전은 자동 삭제하지 않는다. 롤백 UI, 실행 중 갱신 보호, 회사 정책 차단 진단, O0 inventory와 O5 cold offline Kit 검증은 추가 구현·현장 확인이 필요하다.
