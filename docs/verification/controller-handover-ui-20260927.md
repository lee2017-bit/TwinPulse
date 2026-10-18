# 수동 연결 실패 원인과 컨트롤러 개편

2026-09-27 KST. 사용자 반복 실패/조작 UI 개선 요청. **PC 수정 완료; 이번 로봇 작업은 기존 보고서/로그 읽기만. 새 배포·센서·모터·주행 실행 없음.**

## 실제 원인 — 감속 성능 실패가 아님

- PC 원본 `artifacts/manual-control/26c4f8b91ed04904bbb985b9dae78ec6/robot-report.json`, SHA256 `6b018cb931966c93d0f474ab54e40c9600b0894783f02d19bf54fd526c0a48af` 보존.
- 같은 boot `bb3844da-1fd6-42a9-b2c5-2f37be22ed30`, release `ee066bf6c2a158c0dc3b7202aab405ca077eacd716a80b42e37465190d65cfef`.
- 정지 정책 v2 **PASS**, 각 바퀴 누적3.189/3.290mm, 잔류0/0.169mm/s 상당. `ros_stop_confirmed=true`, base exit0/interrupt.
- 최종 상태는 `FINAL_IDLE_UNCONFIRMED`, cleanup false, `after` 없음. 기존 worker가 종료 예외를 버려 화면에서는 이유가 사라짐.
- 고정 SSH로 이미 저장된 두 report 디렉터리의 파일 목록/`final-off.log`만 읽음. 실패 디렉터리 `manual-3b8146fa113441adbac37f08c0b70bb8`에 `READ addr=14 len=5 rc=0 error=0 bytes=0001000000`, 곧바로 FAILED, RESTORE verified=1. 두 번째 바이트 host connection=1 때문에 기존 즉시 gate가 거절한 사실 확인.
- 이후 수동 연결 시도 디렉터리 `manual-8847ec583b754b0eb7e9d05496863eb8`은 같은 필드0000000000 및 OFF readback PASS. 하지만 앞 시험에서 qualification receipt가 만들어지지 않아 연결은 `PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE`로 거절됨.
- ROS 프로세스 종료와 보드 연결표시 해제 사이 순서 문제. 정확한 펌웨어 만료시간을 새로 측정한 것은 아님. 과부하/바닥 마찰/사용자操作 오류로 판정하지 않음. 과거90ms/122ms FAIL은 별도 원본으로 유지.

## 수정

1. OFF helper는 host connection=1인 경우 READ만 하며200ms 간격 최대10회 해제를 기다림. 매 표본 debug/device/전압/모터/버튼/명령0/속도0 조건 유지. IO 오류·다른 상태 이상은 즉시 실패, 마지막도1이면 HOST_DISCONNECT_TIMEOUT. 연결이0이 된 뒤 기존 OFF/최종 readback 절차 수행. 재활성화/heartbeat/속도 명령/실패한 쓰기 재시도 없음. 부모 실행8초 상한 유지. 이것은 **호스트 인계 대기 예산**이며 정지 시험 시간/거리 기준 완화가 아님.
2. worker는 `operation_status`, `cleanup_stage`, `cleanup_error`를 저장. 정지 평가 PASS라도 종료 확인 실패면 receipt0/잠금 유지. base 종료 실패면 독립 포트 작업 안 함.
3. PC는 최신 저장 시험을 별도 historical 요약으로 유지. 다음 연결 실패나 콘솔 재시작이 이전 시험의 원인을 덮지 않음. 과거 결과로 권한을 발급하지 않으며 현재 boot/release 검증은 로봇에서만 수행.
4. UI: 상단 상태/다음 행동, 세 관측 카드, 한 줄 현장 확인, 좌측 방향패드/항상 보이는 정지, 우측 연결 단계/라이다/OFF. 길던 정책 설명은 접기. 모바일 한 열, checkbox 줄바꿈 수정, 키보드/포인터 눌림 표시. 인증 완료 후 PC 저장 상태만 읽고 자동 로봇 연결/재개 없음. 완료 보고 후 늦은 입력 실패가 새 통신 장애로 남지 않도록 표시 수정.

## 검증과 발견한 결함

- 기존 WSL g++17/경고오류화: fake OFF **95 cases PASS** (`artifacts/controller-handover-cpp-r1/checks.log`). 해제1/3/10회,10회 초과, 영구 연결, 속도 비영/읽기 실패/쓰기 실패/해제 readback 실패 포함. 장치 접근 없음.
- Linux Python worker8/runtime8/stationary17 PASS. 별도 정책10/PC transport16 PASS.
- 전체 회귀 `artifacts/controller-handover-regression-r2/manifest.json` PASS, Web82/build PASS, Isaac NOT_RUN. 마지막 완료-response UI 문구/가드 보완은 추가 Web82/build 재검사.
- 실제 격리 Chrome→로컬 App/API→가짜 process/production control loop: `controller-handover-browser-r3` 및 **최종 r4**8단계 PASS. r4 네 방향19개 가짜 출력·놓기·종료·센서 중단·입력 상실, 별도 synthetic PASS+cleanupFAIL 표시/잠금, 모바일 외부요청0/오류0. **실제 로봇 검증이 아님.** 최종 빌드 `index-CZ3TcByX.js` / `index-CrAbcMjF.css`. [새 화면](../../artifacts/controller-handover-browser-r4/physical-desktop.png).
- 초기 브라우저 r2 실패: 인증 전에 initial READ를 보내 가짜장치 표시를 못 받음. 인증 준비 후 조회로 수정. 한국어 실패 기록을 Windows 기본 인코딩으로 읽던 검증 스크립트도 UTF-8로 명시. 실패 산출물 보존. 부분 API mock이 동기 예외를 던진 Web29실패도 비동기 catch 경계로 보완 후 전체 통과.
- WSL에 CMake 없음. 설치하지 않고 기존 g++/Python으로 직접 검사. 로봇 ARM64 helper 재빌드 및 실물 최종 인계는 미검증.
- PC-only bundle `artifacts/robot-preparation/20260927T135432Z-2271c1f1/source.tar`, SHA256 `e0ac4f4b4c56aaa8627944186bceadb94f7664b25fa8cdae597a201d31fab45e`; robot preparation이 사용하는 실제 패키지 기준. 아직 전송하지 않음.

## 다음 실행

로봇 재부팅 불필요. 작업 없는 기존 PC 콘솔 창을 종료하고 `Open-Robot-Console.cmd` 다시 열어 새 Python/UI를 사용한다. 새 화면의 현장 확인 후1번으로 수정된 helper/package를 반영한다. 새 release의2번 준비→별도 정지 시험 실행이 모두 통과해야3번 수동 연결 가능. 이전 실패를 PASS로 바꾸거나 marker를 지워 재사용하지 않는다. 로봇 적용/새 실제 이동은 사용자 명시 실행으로만 한다. 이번 수정의 실제 성공 및 전체 데모 완성은 아직 주장할 수 없다.
