# TwinPulse Claude 독립 검토 안내

이 ZIP은 2026-10-24의 로컬 개발 상태를 검토하기 위한 **소스·인계 문서·선별 증거**입니다. 설치 프로그램이나 완성 제품, 전체 실물 성공 증명이 아닙니다. 현재 사용자는 로봇을 충전 중이며 충전 후 다시 알리기로 했습니다. 이 검토는 실물 연결·모터 구동을 승인하지 않습니다.

## 읽는 순서

1. `01_HANDOFF.md`: 구조, 완료/미완료, 원인과 수정 이력, 유지할 결정.
2. `02_TEST_RUNBOOK.md`: 무구동 검토와 실제 App/실물 시험 절차의 구분.
3. `03_CLAUDE_REVIEW_REQUEST.md`: Claude에 그대로 입력할 검토 요청과 응답 형식.
4. `evidence/latest/result01.json`, `evidence/latest/original-excerpts.jsonl`: 이번 이동 전 배터리 차단의 계산 결과와 원문 발췌.
5. `source/packages/twinpulse_robot_safety/fleet_control.py`, `teleop_contract.py`, `teleop_ros.py`, `tests/test_finite_execution.py`: 최근 자동 명령 변경의 실제 구현.
6. 필요한 범위만 `source/docs/`의 설계·창업자 원문·현재 UI 조작 지침으로 확장합니다. 거대한 Baseline/PROJECT_MEMORY 전체를 첫 프롬프트에 붙일 필요는 없습니다.

## ZIP의 기준

- 현재 개발 소스를 `source/`에 보존합니다. Git HEAD만 묶는 `git archive`가 아닙니다. 미커밋·신규 소스가 많습니다.
- 현재 설치 release/source manifest와 ZIP 내 소스의 대응은 `PACKAGE_INFO.json` 및 `source-vs-installed.json`을 확인합니다. 변경 문서와 미포함 vendor/build 파일을 제품 코드 차이와 구분합니다.
- `MANIFEST.json`은 ZIP 항목별 SHA-256/크기/출처입니다. 원문 발췌의 원 segment/행/전체 파일 해시는 `evidence/latest/excerpt-index.json`에 있습니다.
- 인증정보, 개인 사진/RoomPlan 원 USD, 실제 등록 설정/개인 프로젝트, 전체 원본 센서 로그/영상, EXE·가상환경·node_modules·Isaac/ROS 설치본은 포함하지 않습니다. 실제 기하/전체 원문에 의존하는 재현은 이 ZIP만으로 불가능합니다.
- 선별된 과거 보고서는 역사적 근거입니다. 거기에 적힌 READY/PASS를 최신 설치의 실물 전체 통과로 읽지 마세요. 상대 링크 중 ZIP 밖 대용량 근거는 원 PC 전용입니다.

독립 검토자가 실행 환경에 접근하지 못하면 코드/첨부 증거 검토까지만 보고하고, 하드웨어 결과를 추정하지 않아야 합니다. ZIP을 Claude에 제공하는 행위는 사용자가 수행하며, 이번 작업에서는 외부 업로드를 하지 않았습니다.
