# D1 — 영구 로봇 패키지 준비 구현 / 실제 배포 대기

후속: [충전 중 사전 준비](robot-charging-offline-prep-20260927.md)에서 base
lifecycle 구현/오프라인 검증을 추가했다. 아래는 이전 checkpoint이며
실제 Pi 배포/하드웨어 검증은 여전히 대기다.

2026-09-27 KST. 사용자 승인: 첫 번째(D1)부터 진행. 실제 이동 승인 아님.

## 결과

**D1 PARTIAL.** PC 소스 통합·준비 명령·실패 보고·Linux 소유권 테스트는
완료했다. Pi 영구 배포/ARM64 새 helper 빌드/새 경로의 실제 READ/재부팅
후 점검은 하지 못했다. 배포 시작 시 SSH가 응답하지 않았고, 사용자가
“내가 껐어 계속 소리가나서”라고 확인했다. 지금은 전원 OFF를 유지한다.
지속음 원인과 현재 배터리는 미확인. 과거11.21V를 현재 값으로 표시하지 않는다.

## 반영한 코드

- `packages/twinpulse_robot_safety/`: 기존 guard에 `profile.json`, `runtime.py`,
  PING/READ helper 원본 및 중단 시 복원 처리,20% 정책 시험기 원본을 통합.
  이전 cwd 원본과 소비된1회표식은 삭제·변경하지 않았다.
- `trial/`은 소스 보존용. D1은 실제 trial을 빌드/실행하지 않으며 CMake
  기본값도 OFF다. 실제 시험 승인·표식 재발급 기능은 만들지 않았다.
- `stationary-recipe.json`: 검증됐던 guard/환경/namespace/45초 제한과
  필요한 소유권을 명시한 **비실행 recipe**. base lifecycle 자체를 새
  lease에 묶는 부분은 아직 미구현이며, 전체 제어 단일소유권 완료가 아니다.
- `Prepare-Robot.cmd` → `scripts/prepare_robot.py`: 한 번에 소스 묶음/전송/
  검증·조건부 빌드/장치 없는 검사/idle READ/JSON·HTML 저장. 기존 SSH 키만
  사용하고 패키지·ROS·펌웨어·서비스를 설치하거나 드라이버를 시작하지 않는다.
- 목표 경로: Pi `~/.local/share/twinpulse/robot/releases/<source-id>/`와
  원자적으로 교체하는 `current` 링크. 새 실패는 기존 current를 덮어쓰지
  않는다. 동일 소스는 해시 검증 뒤 빌드를 생략하고 상태는 새로 읽는다.
- runtime 매 실행 UUID run ID/현재 boot ID/manifest ID/로그를 저장한다.
  점검값·과거 Ready를 캐시하지 않는다. 어떤 결과도 이동 권한은 아니다.
- `scripts/robot_health.py`: 이제 영구 manifest 경로만 사용. 미설치/변경 시
  UNKNOWN이며 임시 `/tmp` helper로 자동 fallback하지 않는다. 따라서 Pi
  배포가 끝나기 전에는 새 checker의 board가 UNKNOWN인 것이 의도된 상태다.

## 소유권과 제한

준비/READ는 동일 `state/opencr.lock`의 비대기 flock을 유지한다. 장치 열기
전 fuser로 기존 소유자를 거부한다. timeout/중단 시 자식 process group을
종료·회수한 뒤 lease를 놓는다. helper의 SIGTERM/SIGINT는 현재 읽기를 끝내고
termios/modem 복원을 시도한다. 실패/강제 종료의 복원 성공을 가정하지 않는다.

이 잠금은 **새 managed 작업 사이**의 충돌 방지다. 구 기본 launch나 직접
SDK 실행은 따르지 않으며 fuser 뒤의 unmanaged open 경쟁도 남는다.
guard executable 자체는 이전 검증 해시의 binary를 영구 경로로 이관하는
방식이며 이번에 재빌드한 guard가 아니다. 기존 ROS/SDK 및 최초 이관 파일이
필요하다. clean OS 설치기나 완전히 독립된 배포 이미지로 설명하지 않는다.

## 검증

- Windows robot Python 회귀26/26 PASS. 첫 sandbox 실행은 Windows Temp
  권한 오류1건으로 실패했고 정상 실행 권한 재검사에서 통과했다.
- 기존 WSL Ubuntu22.04에서 장치 없는 runtime6/6 PASS:
  manifest 누락/변경/경로 이탈, busy/조회 실패, 동시 lease 거부/예외 해제,
  timeout child 종료·회수, 첫 배포/cache/변경 거부/실패 시 current 보존.
- CMake 통합 호출은 WSL에 cmake가 없어 미실행. 새 도구 설치는 하지 않았다.
- 새 helper ARM64 compile 및 실제 장치 복원은 **NOT_RUN**. 기존 helper의
  과거 성공을 새 build의 성공으로 전용하지 않는다.
- 첫 읽기 SSH에서는 기존 guard hash
  `403b148b2bdbf0e4c6fc0540888768f9a5eddd38649b1d20883e61fb7fcdc042`,
  포트 미사용, boot `76d5f5c5-0a06-4720-aa6a-7b328d6d6265`를 확인했다.
- 01:19:56KST 배포 시 SSH ConnectTimeout,한 번 재확인도 동일. 첫 mkdir
  요청이 접속 단계에서 실패해서 소스 전송/빌드/배포/새 READ는 시작하지 못함.
  로컬 오류 보고:
  `artifacts/robot-preparation/20260926T161956Z-c056eae1/result/report.json`.
- 모터 활성화/이동/라이다/재부팅/기존 설치 수정은 **없음**.

## 재개 순서 — D1을 완료로 넘기지 말 것

1. 전원·지속음 상황을 사용자와 확인. 계속 켜 두거나 반복 재시동하지 않는다.
2. 전원 재개가 적절한 때 기존 주소/SSH·현재 전압부터 확인. `Prepare-Robot.cmd`
   한 번으로 이관/실제 무구동검사를 실행하고 저장된 결과를 읽는다.
3. 동일 명령 재실행 시 build_cached와 신규 boot/run/배터리 확인. 실제
   재부팅 뒤 영구 경로 점검은 별도로 수행·기록해야 한다.
4. 고정 base recipe를 단일 lease lifecycle에 연결하고 무구동 중복/중단/
   종료 후 포트 반환을 검증. 이것까지 전에는 D1 전체 완료가 아니다.
5. 그다음 D2의 계측·유한 trial runner. 실제 주행은 준비가 다 끝난 뒤
   사용자의 새 현장 주시 확인을 받고 수행한다.
