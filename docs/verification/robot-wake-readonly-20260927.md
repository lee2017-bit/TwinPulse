# 충전 후 부팅·읽기 전용 재확인 — 2026-09-27 11:11 KST

사용자 보고: 충전 완료, 로봇 전원 다시 켬. 충전 완료는 사용자 보고이며 현재
용량/전압을 실제 측정해 검증한 것은 아니다. 야간 자동작업은 PAUSED 유지.

기존 `check_robot_connection.py --profile twinpulse-burger --ros-distro humble
--identity-file <기존 키 경로> --batch --board-snapshot` 1회 실행. SSH 키 내용은
출력/기록하지 않았고 기존 host-key 확인을 유지했다. 새 배포·설치·driver 시작·
센서/모터 제어·주행·전원 변경 없음. 기존 과거 임시 helper로 우회하지 않았다.

## 직접 읽은 상태

- 보고서: `artifacts/robot-checks/20260927T021112Z-73bad6/report.json` 및 report.html.
- 측정11:10:59KST, 주소192.168.35.139 연결 성공. uptime150.36초(당시 약2분30초).
- Ubuntu22.04.5/aarch64, ROS Humble/domain86, ttyACM0/ttyUSB0 확인.
- CPU40.407°C, root여유9.1GiB.
- 감시 대상 base/시험기/LiDAR 프로세스 없음, ROS graph에서 command publisher없음.
  이는 보드 torque/바퀴속도0을 읽은 증거와 같지 않다.
- 영구 release `MISSING_OR_CHANGED`, board `UNKNOWN`/FileNotFoundError.
  배포 검증에서 중단되어 현재 전압·잔량·torque·encoder를 얻지 못했다.
- scan/odom 메시지0, TF없음. driver를 시작하지 않았으므로 이 결과만으로
  센서 고장이라고 판단하지 않는다. `NEEDS_ATTENTION`/`NO_SENSOR_DATA` 유지.

## 다음 단계와 승인 경계

다음은 준비된 D1 영구 패키지의 첫 Pi 배포·ARM64 helper build·독립 READ 확인이다.
사용자의 이번 발언은 전원 상태 알림이므로 이 턴에는 배포하지 않았다. 해당
무주행 배포/진단 범위를 확인한 뒤 진행하며 별도 stationary driver 시작·이동은
자동으로 하지 않는다. D2 physical adapter 미연결·기존정지122ms FAIL·실제scan/TF/
activeTwin 등은 그대로 남는다. 현재 배터리는 과거11.21V나 합성100%로 대체하지 않는다.
