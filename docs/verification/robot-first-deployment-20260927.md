# D1 첫 실물 배포·보드 읽기 — 2026-09-27 11:20~11:21 KST

사용자가 프로그램 배포와 무주행 배터리/보드 점검을 승인했다. `prepare_robot.py
--mode prepare` 1회 실행. OS/ROS/system package 설치, firmware, 기본 launch,
자동시작, 센서/모터/주행 제어는 하지 않았다. 기존 guard binary를 hash 확인 후
새 영구 release로 복사했고 READ helper만 기존 ARM64 g++/SDK로 빌드했다.

## 배포 결과

- 로컬 기록: `artifacts/robot-preparation/20260927T021953Z-6703380d/`.
  `result/report.json`, `transport.log`, 직접 회수한 `remote-operation.log`.
- 로봇 release: `/home/twinpulse/.local/share/twinpulse/robot/releases/9ff4bf2a3b1133a41836b7be3d17f1fe7b0128f263b84ec06a0e82a1a102672b`.
  `current`가 이 release를 가리킴. manifest SHA256
  `decf17f3ba8e11d91e7d12706f9f9cf1cdbbfc5417af0d2c4d888feab5d284a2`.
- 새 ARM64 READ helper build, CMake/CTest3개(deployment_runtime,
  stationary_lifecycle fake, command_guard) PASS, battery policy615 순수 검사 PASS.
  stationary_lifecycle **fake 시험**이지 실제 driver 시작/관측이 아니다.
- manifest와 qualified guard digest는 실제 배포 및 이후 checker에서 VERIFIED.
- 결과는 **PREPARED_NEEDS_ATTENTION**, 전체 idle qualification PASS 아님.
  software 배포/build 성공과 실제 보드의 torque-on 상태를 구분한다.

## 실제 보드 읽기

| 관측 | 11:20:10 KST prepare | 11:21:02 KST 독립 checker |
|---|---|---|
| 배터리 | 12.35V / 전압식 추정100% | 동일 |
| 양 바퀴 속도(raw) | 0 / 0 | 0 / 0 |
| 명령 바이트 | 모두0 | 모두0 |
| encoder | 2321 / 1626 | 2321 / 1626 |
| 보드 torque flag | true | true |
| port 복구 | 확인 | 확인 |

독립 보고서: `artifacts/robot-checks/20260927T022114Z-7b6bfd/report.json`.
감시대상 제어프로세스0/ROS command publisher0, scan/odom 메시지0(driver미실행),
CPU39.92°C/root9.04GiB. 두 시점 encoder 동일은 사이의 연속 정지 전체를 증명하지
않으며 기존 timeout/settling qualification을 대체하지 않는다.

12.35V의100%는 기존 공개 전압식 결과를0~100으로 제한한 추정 표시다. 정밀
용량/사용가능 시간/충전기 판정이 아니다. 이번에는 과거 값이나 합성 값이 아닌
실제 OpenCR PING/READ 결과다.

## 주의 항목과 다음 단계

모터 torque flag가 true여서 `NEEDS_ATTENTION`을 유지했다. READ helper에는
write-register 호출이 없고 이번 실행은 `prepare`/읽기만 사용했다. 따라서 이
작업에서 torque-enable/이동 명령을 전송하지 않았다. 부팅 기본값인지 다른
원인인지는 이 읽기 결과만으로 확정할 수 없다.

별도 stationary 절차는 사전 torque=false를 요구하므로 실행하지 않았다.
다음은 torque-on 원인/비활성화 경로 확인과 무주행 비활성화에 대한 별도 승인이다.
토크 해제 전 장치가 평평한 바닥에서 지지되는지 확인해야 하며 임의 레지스터
변경·기존표식재사용·새 주행으로 해결하지 않는다. D2 physical adapter·실제
stationary/ROS observer·재부팅 지속성·기존122ms정지FAIL·scan/TF 등은 남는다.
