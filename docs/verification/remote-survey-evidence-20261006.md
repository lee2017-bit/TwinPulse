# 원격 조사 지도 보존과 저장 정합 재검사

원격 조사에서 만든 전체 파생 지도와 정합 결과를 로봇 작업 종료 후 PC로 보존하고, 기존 저장 자료 검사 경로에서 정합을 다시 계산하도록 연결했다. 기존 실시간 제어 채널에는 대용량 지도를 보내지 않는다. 이번 결과는 오프라인 코드·프로세스 통합 검증이며 현재 위치, 주행 승인 또는 실물 데모 성공을 뜻하지 않는다.

## 연결한 제품 경로

1. 기존 robot-local observed worker가 모터 OFF/정지 관측, 센서 종료 및 raw/journal 정리를 먼저 수행한다. 이후 `mission-evidence.json`을 배타적으로 만들고 flush/fsync한다. 제어 stdout과 최종 로봇 보고서에는 고정 파일명·크기·SHA256·revision의 작은 descriptor만 넣는다. 저장 오류는 별도 코드와 예외 종류로 남기며 원래 임무의 실패 사유를 덮어쓰지 않는다.
2. 기존 `robot_evidence_export`가 해당 descriptor를 가진 보고서에만 파일을 추가한다. 이전 보고서의 파일 목록은 그대로다. 보고서·전송 receipt·크기·파일 SHA·내부 revision·원래 scope/request·session/boot/release를 검사하고, 누락·손상·다른 세션이면 완료로 표시하지 않는다. 전송 재개도 같은 고정 파일과 원본 보고서에 결속한다.
3. `PhysicalController`는 종료 후 검증된 자료만 private 역사 자료로 로드한다. 기존 원격 어댑터는 전송 완료까지 기다린 뒤 전체 지도와 fit을 `AutomaticMissionService`의 저장 보고서에 연결한다. 조사 성공인데 전체 지도/fit이 없으면 `REMOTE_SURVEY_EVIDENCE_MISSING` 등 정확한 원인으로 거절한다. 실패·Stop에서도 확보된 자료는 보존하되 결과를 성공으로 바꾸지 않는다.
4. 기존 `inspect_robot_evidence.py`와 이를 사용하는 오프라인 review 경로는 자료를 검증한 후 같은 원본 keyframe·nominal geometry·policy로 정합을 다시 계산한다. `MATCH`는 저장 계산의 재현성이고 `MISMATCH`는 별도 오류다. 거절된 fit을 재현한 `MATCH`는 정합 통과가 아니다. 보정 적용, 로봇 연결 또는 재주행은 하지 않는다.

`mission-evidence-1.0`은 추가 저장 계약이다. 기존 observed scope v1–v5, 직렬화/hash, 정지·scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s 기준 및 실물 임무 잠금은 변경하지 않았다. 임의 경로, 중복 JSON key, 비유한 수, 예산 초과, 다른 scope/boot/release/request, 변경된 keyframe·tracking cloud와 authority=true는 거절한다. 새 core 모듈은 기존 reviewed source archive에 포함하되 실제 배포는 수행하지 않았다.

## 무엇을 전체로 보존하는가

전체 **파생 조사 지도**는 기존 알고리즘이 채택한 keyframe, 해당 선택/deskew 반환점과 origins, odometry-projected tracking endpoints, endpoint cells 및 전체 fit이다. 이미 선택된 지도를 UI용 소수 점으로 다시 축소하지 않는다. 모든 시간의 모든 원시 LiDAR beam이나 전역 SLAM 지도를 뜻하지 않는다. 전체 원시 ROS 메시지는 기존 별도 raw 기록 경로이며 이번 계약으로 대체하지 않는다.

저장 계약과 재검사 출력의 `current_pose_valid`, `motion_authorized`, `physical_demo_ready`는 모두 false다. 역사 자료 재열기는 fresh odom/scan/TF, 현재 위치 또는 입력 lease를 복구하지 않는다.

## 최종 검증

- 소스를 고정한 최종 Python 관련 모듈 회귀 **145개 / 221.324s / PASS**. 신규 시험만의 수가 아니라 기존 controller·수집·복구·채팅 표시 시험을 포함한 묶음이다. 이번 신규 저장 계약 시험은 6개다.
- 정상 원격 목표 완료, ledger 거절, 조사 전용 완료, 보정 시점 Force Stop의 PC/robot subprocess 통합 4개가 통과했다. 센서는 출력에 반응하는 합성 ROS fixture, 전송은 명시 test-only exporter다. 실제 SSH/SCP/센서/바퀴 검증이 아니다. 실제 제품 exporter 함수의 파일/receipt/hash/전송재개는 별도 파일 기반 fake-SCP 시험으로 검증했다. production worker와 test-only exporter 혼용은 거절한다.
- 최종 4개 case마다 source 16개와 artifact 8개 SHA256이 현재 파일과 일치한다. 정상 목표·조사 전용 case는 저장 지도/fit이 App 보고서와 일치하고 동일 fit 재계산 `MATCH`도 검사했다. ledger 거절은 `PHOTO_LEDGER_HEAD_CHANGED`와 로봇 `COLD_START_FIT_FAILED`, Stop은 `FORCE_STOPPED`를 보존한다.

| 최종 case | 저장 keyframe | tracking points | endpoint cells | 지도 파일 bytes | 원래 결과 |
|---|---:|---:|---:|---:|---|
| [목표 완료](../../artifacts/remote-full-map-20261006-r3/arrived/verification.json) | 17 | 2040 | 180 | 220670 | 합성 MISSION_ARRIVED |
| [ledger 거절](../../artifacts/remote-full-map-20261006-r3/rejected/verification.json) | 17 | 2040 | 178 | 222882 | FAILED / COLD_START_FIT_FAILED |
| [조사 전용](../../artifacts/remote-full-map-20261006-r3/survey/verification.json) | 16 | 1920 | 187 | 208367 | 합성 MISSION_ARRIVED, goal route 없음 |
| [Stop](../../artifacts/remote-full-map-20261006-r3/stop/verification.json) | 17 | 2040 | 185 | 224531 | FORCE_STOPPED |

최종 묶음은 `test_mission_evidence`, `test_robot_evidence_export`, `test_robot_source_identity`, `test_remote_mission_correction`, `test_adaptive_robot_preparation`, `test_remote_correction_guard`, `test_robot_evidence_recovery`, `test_physical_controller`, `test_chat_inspection_visual`이다. `git diff --check`는 통과했다. 시험 소유 자식은 각 cleanup으로 종료했다. 로봇 접속·센서·모터·배포·유료 호출·설치·commit/push·새 agent는 0이다.

## 실패 이력과 검증 경계

- 최초 제한 실행은 생성된 임시 폴더의 child write가 `WinError 5`로 실패했다. 권한 우회나 시스템 변경 없이 범위가 명시된 시험 실행 승인을 받아 재검사했다.
- 최초 계약 시험 fixture가 nominal structural objects 대신 전체 가구 objects를 넣어 `MISSION_EVIDENCE_FIT_CONTEXT`로 거절됐다. fixture를 실제 scope 계약에 맞췄고 제품 기준을 완화하지 않았다.
- 중간 원격/준비 회귀 15개 중 14 PASS/1 ERROR가 있었다. 실행 중 계약 소스를 변경하여 부모의 이전 import와 새 자식의 schema가 달랐던 `MISSION_EVIDENCE_CONTEXT` 오류다. 이 중간 결과는 최종 PASS에 합치지 않았다. 최종 회귀는 소스를 고정한 뒤 전체 145개를 다시 실행했다. r1/r2 산출물은 이전 시점의 기록이며 최종 근거는 r3다.
- 이번 증분의 실제 Chrome/Isaac runtime, 회사 PC, target binary/profile 및 실물 실행은 **NOT_RUN**이다. Web 소스/build는 변경하지 않았으며 이전 v296의 별도 host capture `viewport_missing` FAIL도 해결했다고 표시하지 않는다.

## 정확한 잔여와 다음 작업

C4는 **PARTIAL**, whole-demo readiness는 false다. 다음 오프라인 구현은 현재 보정 방의 semantic goal을 **fresh** 로봇 위치와 연결하고, 정확한 방/시작/목표의 실제 SIM 경로 시연 후 digest-bound Confirm을 기존 robot-local 임무에 연결하는 묶음이다. 저장 전체 지도를 다음 로봇 임무의 reference로 반입하는 경로는 아직 연결하지 않았으며 현행 bounded reference/packet 계약을 임의로 늘리지 않는다. 지도 재생 성공만으로 새 임무를 시작할 수 없다.

이후 C5 persistent TaskLoop/안전한 bounded leg 전환과 C6 제품 통합 인수, 별도 C3 target/profile·moving field-suite 및 실물 확인이 남는다. 다음 코드 구현에는 로봇 전원이 필요 없다. 실제 로봇을 켜면 전체 데모가 보장된다는 상태가 아니다. 원본·dirty 변경·과거 실패·guard·실물 잠금을 보존했고 heartbeat는 PAUSED다.
