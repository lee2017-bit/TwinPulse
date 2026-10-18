# 실제 수동 컨트롤러 연결 — 구현/오프라인 검증, 실물 인수시험 대기

2026-09-27 KST. 사용자 “완성시켜. 로봇은 껐다.” 승인에 따른 구현. 이번 로봇 SSH/배포/센서/모터/전원 제어는 **0회**다. 로봇 OFF 보고를 유지했다. 기존 모의 UI에 머물지 않고 실제 전송·로봇 측 실행 경로를 추가했다. **새 패키지의 ARM64/ROS/실제 정지·주행 성공은 아직 확인하지 못했다.**

## 사용 순서

1. 현재 작업이 없는 기존 점검 실행 콘솔을 Ctrl+C로 닫고 루트 `Open-Robot-Console.cmd`를 다시 연다. Python 서버가 바뀌므로 브라우저 새로고침만으로는 부족하다. 로봇이 꺼져 있어도 화면 열람 가능, 자동 접속 없음.
2. 로봇을 켠 뒤 현장을 보고 있을 때 **가상 컨트롤러 → 실물 조작**의 배터리 전원/평평하고 빈 바닥/현장 주시 확인을 선택한다.
3. **1. 제어 패키지 준비 · 설치/모터 OFF**: 기존 준비 도구로 현재 프로젝트 소스만 전송·기존 guard 검증/캐시·검사·OFF/독립 읽기를 수행한다. 시스템 패키지 설치나 부팅 자동 서비스 등록은 없다. 첫 준비는 빌드 때문에 시간이 걸릴 수 있다. 결과가 PREPARED가 아니면 다음 단계로 넘어가지 않는다.
4. 확인을 다시 선택하고 **2. 정지 시험 준비**. 준비가 끝나면 **지금 정지 시험 실행 · 실제 짧은 전진**을 눌러야 실제 시험이 시작된다. 고정0.03m/s·600ms 전진 입력 후 입력 만료/정지를 관측한다. 기존200ms 안정/2틱/500ms 창 기준 유지. 준비 중 오류는 움직이지 않은 상태로 종료하며, 실제 시험 직전에만 새 일회 표식을 소비한다. 실패를 버튼 재클릭으로 자동 반복하지 않는다.
5. **이번 부팅·버전의 정지 검증 통과** 뒤 확인을 다시 선택하고 **3. 수동 조작 연결**. 누르는 동안 전후진/제자리 좌우 회전, W/S/A/D·방향키, 버튼 해제 정지. 한 연속 입력 최대2초, 연결 최대60초. 입력 만료·창 이탈/숨김·연결 종료 후 자동 재시작하지 않는다. 새 연결은 다시 명시 승인한다.
6. 라이다는 별도 **라이다 시작 · 최대8초 / 라이다 중단**. 바퀴 제어와 동시 실행하지 않는다. 데이터 수신 종료는 물리 회전체 정지 증거가 아니다.

각 작업 결과는 PC `artifacts/manual-control/<request_id>/result.json`, 가능하면 `robot-report.json`에 자동 저장한다. 로봇에는 `~/.local/share/twinpulse/robot/reports/manual-<id>/` 아래 상세 telemetry/raw/최종 읽기가 남는다. 결과 새로고침은 읽기만 하며 이전 제어를 재개하지 않는다. 사용자가 매번 결과를 채팅에 붙이지 않아도 프로젝트 파일에서 확인할 수 있지만, 저장했다고 대화가 자동으로 시작되는 것은 아니다.

## 실제 경로와 경계

- React `PhysicalRobotController` → 기존 인증/CSRF API → PC `PhysicalController` → 고정 사용자/주소/StrictHostKeyChecking SSH → 고정 `teleop.sh` 역할 → 로봇 `teleop_worker`/`teleop_ros` → 검증된 guard의 stamped command/arm/stop, 명시 motor_power. 임의 호스트/속도/셸 입력 API는 없다.
- 생성자/GET에는 접속 없음. 시작 요청은 짧은 유효기간·명시 확인·일회 request ID를 요구한다. 동일 ID는 중복 실행하지 않고 기존 작업 상태만 반환한다. 준비/센서/수동 작업 중 다른 작업은 거절한다.
- 로봇의 기존 OpenCR lease·manifest·guard digest·독립 READ/OFF helper 재사용. 기존 `motion_enabled:false`는 legacy trial/mission 비활성 상태로 유지하며, 별도 `manual_control_policy`가 명시 수동 세션에 한해 같은 부팅/전체 release의 정지 검증 기록을 요구한다. 단순 PC PASS/보고서 import/가짜 데이터로 이를 해제하지 않는다.
- PC 시간과 로봇 시간을 동기화했다고 가정하지 않는다. 로봇 발급250ms challenge, PC에 이미 머문 입력 age의 보수적 합, 증가 sequence, 원래 요청 만료를 적용한다. 대기 큐의 입력에 새 수명을 주지 않는다. arm 이전 입력은 이후 도착해도 출력하지 않는다.
- 정지/OFF 확인 대기 중 이미 만료된 입력은 **출력이 비활성일 때만** 버리고 새 입력을 기다린다. 이동 중 입력 만료는 계속 실패·종료한다. 센서/guard freshness·전압/보드 버튼·엔드포인트 수와 프레임을 검사한다.
- PC 파이프 쓰기는 별도 bounded queue로 HTTP/감시기를 막지 않는다. PC 입력이 끊기면 EOF 정리를 요청하고 소유한 로컬 프로세스만 제한시간 후 종료한다. 로봇은 입력 만료·EOF·예외 후 stop/OFF→소유 base 종료 확인→독립 OFF/READ 순서로 정리한다. 확인 실패를 정지 성공으로 표시하지 않는다.
- 정지 검증은 새 고정 시험이며 구 시험 표식을 삭제하거나 기존122ms FAIL을 덮어쓰지 않는다. 같은 부팅/release에 유효한 새 기록이 있어야 수동 이동 연결이 가능하다. 로봇 재부팅/패키지 변경 뒤에는 이전 기록으로 활성화하지 않는다.

## 검증

- `physical-controller-regression-r3/manifest.json`: Python397/Web78/TypeScript·production build PASS. 마지막 일회 표식 위치 정리 후 관련14+로봇 lifecycle4 추가 재검사 PASS.
- 로봇 패키지 no-device lifecycle4 / LiDAR7 PASS. 새 CMake 패키지 검사에 두 그룹 포함. 로봇에서의 실제 CMake/ARM64 실행은 NOT_RUN.
- 최종 `artifacts/physical-controller-browser-r7/result.json`: 격리 Chrome→실제 App/API→실제 자식 프로세스→production 입력/시험 루프→**가짜 장치** 7단계 PASS. OFF 관측 대기250ms도 가짜 장치에 반영. 19개 가짜 출력 표본에서 네 방향 도달과 원래 입력 수명 확인, 외부요청/페이지오류/합성수집기호출0, 프로젝트 원본 불변. r3/r5/r6도 각7단계 PASS. 가짜 QUALIFIED라도 `physical_verified:false`, 실제 자격 파일을 만들지 않는다. 최종 모바일 화면 육안 확인, 가로 넘침 없음.
- 최종 오프라인 bundle: `artifacts/robot-preparation/20260927T125143Z-5a8e4c8c/source.tar`, SHA256 `a92db83d9fc5ca249b9bbb420a636697888aa988eca45d9073d3cfa06cdda6e9`, OFFLINE_BUNDLE_READY/actual_robot_validation NOT_RUN. 실제 설치 버튼은 그때의 현재 source를 동일 절차로 다시 묶는다. 앞선 bundle은 이전 버전 이력으로 보존한다.
- 기존 실제 보고서 SHA256 `4cdf7ab2c6ecc4c82475c6f34fe5581f5969a2c226e227b3a0218a2821a07b49` 재확인, 변경 없음. 로봇이 꺼져 있다는 사용자 보고 이후 새 실물 관측을 만들지 않았다.
- 발견한 실패를 보존: 최초 Windows sandbox 임시폴더 거부 후 허용된 테스트 실행; browser r1 입력 BufferedReader 종료 잠금/가짜 시각 중복, r2 challenge 소비 경합, r4 재활성화 때 이전 challenge를 지워 유효한 후속 입력까지 거절. 무버퍼 입력, 최종 receipt 뒤 stdin 종료, 원래 age를 보존하는 중계 큐, arm 이전 입력 무출력 소비로 수정. 실패 폴더 삭제/기준 완화 없음.

## 아직 실물에서 확인할 것

새 소스의 배포/ARM64 패키지 검사, ROS Python 서비스/telemetry 실제 지연, 기존 정지FAIL 재현·원인, 실제 정지 시험, 실제 입력 해제·연결 끊김·OFF 최종 읽기, LiDAR 시작/중단을 확인해야 한다. 오프라인 PASS는 실물 합격이 아니다. 실패하면 저장된 상세 센서 표본으로 원인을 판단하며 반복 시험으로 통과를 찾지 않는다.

하드웨어 비상정지, kernel/MCU/통신 전체 고장, 기존 직접 SDK/다른 프로세스의 동시 제어까지 보장하지 않는다. firmware heartbeat fallback 실물 검증도 남아 있다. 지도/TF/장애물 자율판단·실물 임무 데모와 별개인 제한된 현장 수동 제어다. 기존 예약은 PAUSED 유지한다.
