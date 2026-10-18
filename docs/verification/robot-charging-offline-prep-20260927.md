# 충전 중 D1 잔여·D2 준비 — 2026-09-27

사용자가 충전 중 다음 단계를 미리 준비하도록 승인했다. 이번 턴은
PC/기존 WSL 작업만 수행했으며 **로봇 SSH/장치 접근/전원 조작/라이다/
모터 활성화·이동 모두0회**다. 충전 완료와 현재 전압은 미확인이다.

## 준비된 실행 단위

- `Prepare-Robot.cmd`: 영구 release 배포·조건부 build·idle READ. 기본
  동작은 여전히 드라이버를 시작하지 않는다. 실제 Pi 배포는 대기 중.
- `Check-Robot-Stationary.cmd`: 명시적으로 선택할 때만 guarded base를
  disarmed로 시작→20초 passive 관측→종료·회수→독립 READ. 코드와 가짜
  프로세스 검증 완료, 실제 ROS/ARM64 실행은 NOT_RUN.
- `Prepare-Robot.cmd --mode offline`: SSH 없이 소스 묶음·해시·보고서.
  실제 실행했고 결과는 `OFFLINE_BUNDLE_READY`, 이동 권한은 false다.
- `scripts/verify_robot_offline.sh`: 기존 Python/g++만 사용해 회귀·가짜
  프로세스·순수 C++ 검사와 오프라인 묶음을 한 번에 생성. 설치/장치 접근 없음.

## D1 소유권·중단 처리

같은 flock을 사전 READ부터 base/observer 회수와 최종 READ까지 유지한다.
자식이 lock FD를 상속하므로 부모가 사라져도 생존 중인 자식과 다른 managed
작업이 겹치지 않는다. Linux parent-death signal과 fork-race 확인으로 관리자가
사라지면 고정 역할 자식도 종료된다. 임의 명령/속도 인자를 받지 않는다.

observer는 application publisher/service client 없이 sensor/status를 관측한다.
시작8초 유예 후 나이<200ms, 각각 publisher1개, command publisher0개,
torqueoff/button0/고정2틱 encoder band를 요구한다.11.1V 이하 보호 근처
상태도 정상 qualification으로 승격하지 않는다. 사용자20% 충전 정책 변경 아님.

예외/timeout/Ctrl+C에도 자식을 먼저 회수한 뒤 포트를 읽는다. 정리 중
두 번째 종료 신호를 무시하고 handler를 복원한다. 강제 종료·조기 종료는
review, 최종 idle 미확인은 cutoff필요로 표시. 모터off 명령을 추가하거나
읽지 못한 상태를 성공으로 추정하지 않는다.

**제한:** legacy launch/direct SDK는 lease를 따르지 않는다. fuser 뒤의
unmanaged open경쟁을 막는 장치 접근권한 정책은 아니다. 기존 launch,
자동 시작, firmware는 미변경. 기존 qualified guard binary를 이관하는
방식이지 새 guard 재빌드/clean OS 설치기가 아니다.

## D2 사전 준비

`trial_session.py`는 실제 출력에 연결되지 않은 **dry-run 상태 계약**이다.
준비와 현장승인 분리, boot/release/session/trial binding, Ready5분 만료,
현장확인15초 만료, 즉시 점검1초 이내, 취소/1회소비/재시도금지를 검사한다.
통과해도 `motion_authorized:false`. 실제 C++ trial adapter·영구 승인/소비
receipt 연결과 ROS/실물 qualification은 남았다. 기존 소비 표식/주행 조건은 보존.

저장된 정지 분석은500ms 구간의 시작/끝/중간 sample공백을 검사한다.
200ms 이상 공백이나 끝부분 누락이면 reconstructed pass=null(UNKNOWN).
데이터 없음=정지로 판정하지 않는다. 과거122ms<200ms FAIL은 그대로 유지.

## 검증

- Windows robot Python28/28 PASS.
- WSL Python28+deployment6+stationary/session17 = **51 PASS**.
  가짜 base 성공/사전거부/telemetry오류/중단/회수실패/종료 후 이동 검출,
  실제 fake child 회수·중복 lease거부·부모강제종료 후 child종료 포함.
- WSL g++ command_guard1314 및 이관한 battery_policy615 checks PASS.
  둘 다 순수/fake output 검사이며 ROS/serial 없음.
- 첫 통합 실행에서 테스트의 보고서 root가 소스 조회에도 쓰이는 문제가
  나와 모듈 기준 소스 경로로 수정, 재실행 PASS. shell bundle은 CRLF→LF 정규화.
- CMake 통합·새 helper ARM64 compile·실제 ROS observer import/graph/rate,
  Pi 배포/재부팅 검증 **NOT_RUN**. WSL cmake/ROS SDK 미설치 상태 유지.
- 로그: `artifacts/robot-offline/run-*/checks.log`. 묶음과 JSON/HTML:
  `artifacts/robot-preparation/<run-id>/`. Linux fake PASS는 하드웨어 PASS가 아니다.
- 최종 전체 PASS 로그: `artifacts/robot-offline/run-BHZ6OUjf/checks.log`.
  최종 묶음: `artifacts/robot-preparation/20260926T164958Z-55347f24/source.tar`,
  같은 run의 `result/report.json`에 SHA256과 NOT_RUN 범위를 기록했다.

## 충전 후 순서

1. 사용자가 충전 완료와 전원 재개를 알리면 주소/SSH·현재 전압 확인.
2. `Prepare-Robot.cmd`로 Pi 첫 배포/ARM64 helper build/실제 READ 검증.
3. 준비 완료 후 주변 상태를 확인할 수 있을 때 무구동 stationary check를
   실제 검증. 자동으로 주행 단계로 넘어가지 않는다.
4. D1 actual gate 뒤 D2 physical adapter/계측 연결·ROS fake검증.
   실제 주행은 새 현장 주시 확인 직후 별도로 승인받아 수행.

**D1 lifecycle/offline 준비 완료·실제 배포 gate대기; D2 dry-run 준비 완료/
실제 runner미연결.** 충전만 끝나면 전체 주행이 검증된다는 의미가 아니다.
TwinPulse UI/scan/공정 경로 비교의 최종 목표는 유지한다.
