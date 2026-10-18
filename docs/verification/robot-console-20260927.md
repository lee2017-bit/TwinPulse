# PC 준비 / 원클릭 읽기 전용 로봇 점검

2026-09-27 KST · 사용자 “그래 해보자” 승인에 따른 구현. 실물 접속/배포/주행은 이번에 실행하지 않았다.

## 사용법

1. 저장소의 `Open-Robot-Console.cmd`를 더블클릭한다. 기존 Python/빌드만 사용하며 Isaac, 유료 API, 로봇을 자동 시작하지 않는다. 브라우저와 실행 콘솔을 유지한다.
2. **1. PC 사전준비**: 점검 코드, SSH 실행파일, 기존 인증 키와 known_hosts 파일의 존재/메타데이터를 검사한다. 키 내용은 읽지 않는다. 이 단계에는 로봇 전원이 필요 없다.
3. 충전 완료 후 로봇이 준비되면 PC 준비를 다시 확인하고, 이번 읽기 점검 확인란을 선택한 뒤 **2. 로봇 연결·묶음 점검**을 누른다. 토큰 유효기간은 2분이다. 대상은 기존 `twinpulse@192.168.35.139`, ROS domain86으로 고정된다.
4. 진행 시간과 결과/저장 여부, 관측 시각, 보드/기존 센서 상태, 전압 기반 배터리 추정값을 확인한다. 원격 수집 상한120초, 자동 재시도 없음. 결과는 `artifacts/robot-console/<job-id>/report.json`에 정규화해 저장한다.
5. 창 새로고침 후에는 **결과 새로고침**으로 기존 작업 결과를 읽는다. 실행 콘솔의 Ctrl+C로 이 서버만 종료할 수 있다. 수집 중 종료는 최대120초 수집 종료를 기다릴 수 있다.

일반 TwinPulse App에도 같은 패널이 들어간다. 전용 실행파일은 별도 `.runtime/robot-console` 상태를 사용하므로 기존 활성 프로젝트를 바꾸지 않는다. AI 생성과 Isaac 연결은 전용 창에서 제공하지 않는다. HTTP 서버는 loopback만 바인딩하며 세션/CSRF 검사를 유지한다. 단순히 화면을 열거나 PC 준비를 눌러도 SSH는 실행하지 않는다.

## 구현 경계

- 기존 `check_robot_connection.py`의 전송을 `collect_readonly`로 공유한다. 사용자 입력 임의 호스트/명령/옵션을 API로 받지 않는다. 기존 키와 엄격한 호스트 신원 검사, 비대화형 1회 SSH, PING/READ 및 기존 센서 구독만 사용한다.
- PC 준비 토큰은 세션/파일 fingerprint/시간에 묶이고, 소비된 토큰의 재전송은 같은 결과만 반환한다. 동시 점검은 차단한다. 다른 App 인스턴스를 함께 실행하지 않는 것이 좋으며 원격 포트 사용은 기존 lease에 따른다.
- 새 수집 시작 시 이전 관측값을 지운다. 실패 시 과거 배터리가 현재 값으로 남지 않는다. 보고서는 지속적인 실시간 연결/현재 상태/이동승인을 뜻하지 않는다.
- 배터리 %는 전압 기반 추정이며 용량 실측이 아니다. 사용자20% 충전 정책과 보드 전압 보호 조건을 분리한다.
- 준비 버튼은 설치/배포/업데이트/토크OFF/드라이버 시작/좌표 변경/이동을 하지 않는다. 파일 존재 PASS는 원격 인증 성공을 보장하지 않는다.
- **좌표 동기화, 새 정지 진단 runner, 실물 mission adapter는 미구현/미검증이다. 기존 안정정지122ms FAIL과200ms 기준을 변경하지 않았다. 전체 실물 데모 준비 완료가 아니다.**

## 실제 검증

- `artifacts/robot-console-regression-r3/manifest.json`: 전체 기존 회귀 + 새 console/기존 connection18검사, 총 Python369 / Web65, TypeScript/production build PASS. Isaac NOT_RUN.
- `artifacts/robot-console-browser-r1/result.json`: 실제 Chrome→React→인증 LocalApiServer, **합성 collector** 주입으로5단계 PASS. PC 준비 무통신, 명시 확인/단일 작업/진행/저장, reload 조회, 실패 후 이전 전압 제거/재시도 없음, mobile overflow없음. 외부요청/engine명령0. collector2회, 실제 SSH0.
- desktop/mobile 스크린샷을 직접 확인했다. 화면 속11.21V/39.4%는 **합성 fixture**이고 현재 배터리가 아니다.
- 새 경량 launcher의 실제 local server 생성/정상종료와 PC-only 무통신을 모의 브라우저로 검증했다. 실제 PC의 `launch_robot_console.py --pc-only`는19:16 KST에4항목 모두 ready=true였다. 키 내용/로그인 정보 출력 없음.
- 초기 Web r1에서 기존 테스트의 무명 checkbox 선택이 새 확인란과 충돌한1FAIL을 보존하고, 기존 draft의 명시 label로 선택하도록 수정했다. r2/r3 Web65 PASS. 샌드박스 Vite spawn EPERM은 승인된 기존 로컬 빌드 실행으로 검증했으며 설치/시스템 변경은 없다.

## 다음

충전 후 사용자가 점검 버튼으로 실제 읽기1회를 승인·실행하면 결과부터 판단한다. 연결 성공을 미리 보장하지 않는다. 센서가 꺼져 있으면 NO_SENSOR_DATA는 예상 가능하며 임의로 켜거나 이동하지 않는다. 과거17:36/18:04 인수인계 페이지는 당시 snapshot으로 보존하고 현재 코드 해시와 동일하다고 주장하지 않는다. 기존 예약은 PAUSED 유지.
