# N3 증분 — 일반 해제 / 연결 유지 / 명령-관측 기록

2026-09-28 야간 승인 범위. 로봇 OFF, SSH/serial/배포/실물 구동 없음.

## 변경과 경계

- 일반 방향키 해제를 최종 `halt()`와 분리했다. `RosLink.release()`는 즉시
  guard stop과 torque OFF를 요청하고, 기존 2틱 anchor/200ms 안정 조건과
  fresh sensor·explicit_stop·torque=false를 관측한다. 이동 중 해제의 관측 예산은
  기존 stop policy의 800ms+경계표본 100ms 이내다. 누적 절대 바퀴 회전량도
  기존 10mm 한도로 검사한다. 이는 제조사 정지 보증이 아니다.
- 과거 고정 250ms 수면 안에 안정 200ms를 충족해야 하던 일반 release의
  관측 부족을 분리한 것이다. 최종 halt/독립 OFF, qualification 정책·해시,
  기존 FAIL/소비 표식, 속도/입력 신선도/2초 hold/60초 세션은 변경하지 않았다.
  새로운 release는 qualification receipt를 만들거나 과거 실패를 통과로 바꾸지 않는다.
- PC는 해제 명령 후 `RELEASING`으로 표시하고 방향 버튼만 잠근다. 로봇 READY의
  input_sequence가 해제 sequence 이상일 때만 같은 연결에서 다시 활성화한다.
  이전 READY가 지연 도착해도 해제 완료로 취급하지 않는다. 반복 확인란/재연결 없음.
  명령은 해제 대기 중 발행하지 않으며 이후 새 post-arm 입력이 있어야 발행한다.
- 입력 지연, hold 제한, 세션 만료를 별도 원인으로 기록하고 한국어로 표시한다.
  모든 제한은 그대로이며 해당 만료는 계속 세션을 종료한다.

## 세션 로그

기존 제품 제어 경로의 PC `artifacts/manual-control/<job_id>/session.jsonl`에
입력 수신 / pipe 전송 완료 / 로봇 수락·arm·ROS publish / 해제·idle / encoder·
torque·전압·source age·guard 관측 / 종료 결과를 구분해 저장한다.
로봇에도 해당 실행의 `session.jsonl`과 기존 전체 telemetry 파일을 남긴다.

- PC job_id와 로봇 session id를 한 로그에서 연결하며 각각 PC/robot monotonic
  clock domain을 보존한다. 두 clock의 offset이나 전송 지연을 임의 추정하지 않는다.
- input 수신 ≠ 전송 ≠ ROS publish ≠ 실제 바닥 이동. 최초 arm 이전 입력은
  수락 기록이 있어도 publish 기록은 없으며, source age를 새로 부여하지 않는다.
- 스트림 schema/필드/유한수/순서/세션 변경을 검사한다. challenge·인증정보는 저장하지 않는다.
  로봇4096/PC8192 event 상한 초과 시 조작을 종료하고 완전한 로그로 표시하지 않는다.
- 관측은 주기별 최신 sample이며 모든 ROS 표본이 아니다. OFF 대기 중 표본의
  PC 스트림 공백을 보간하지 않는다. 전체 원본은 로봇 telemetry에 남는다.
- **odom/scan/차체 pose는 아직 수집하지 않는다.** 실측 이동거리/충돌 여부/세계 TF를
  이 로그만으로 확정하지 않는다. qualification 상세는 기존 별도 시험 보고서다.
- PC 로그는 작업 종료 시 저장하므로 PC 서버 자체의 비정상 종료 시 내구성은 미완료다.
  UI 재생/분석, 자율 adapter 공용화, 실센서와의 완전한 시간축 통합도 남아 있다.

## 검증

- 직접 관련 Python45 PASS: 프로토콜/PC transport21, worker lifecycle8 + release6,
  stop policy10. 350ms 감속 후 안정, 계속 이동/torque ON/센서 지연/서비스 실패/
  왕복 회전량, 반복 release 같은 세션, stale READY, 기존 FAIL 보존, 로그 schema/budget.
- `artifacts/session-release-regression-20260928-r3/manifest.json`: 전체 오프라인 회귀 PASS,
  core138 / Web95 / TypeScript·production build PASS. 정규 검증 명령에도
  robot worker·stop policy 단위검사를 추가했고 최종 r3에도 포함되어 PASS.
- `artifacts/session-release-browser-20260928-r2/result.json`: 실제 Chrome→App/API→
  **가짜 장치**9단계 PASS. 550ms fake 해제 지연에서도 키4방향/마우스4방향
  같은 연결 유지, 새 승인 불필요, 해제 중 잠금 및 이후 활성화 확인.
  가짜 출력26개, 로그5개/전체462 events/robot221 events. source/dist SHA256 고정,
  외부요청0·원본 project 불변·실물0. 이는 실물 반복 주행 성공이 아니다.

초기 sandbox 실행은 Windows 임시폴더 권한 오류13개로 실패했다. 승인된 로컬
검증 권한으로 같은 검사42→추가검사45 PASS. 브라우저 r1은 9단계 동작 자체는
PASS지만 병행한 빌드가 dist 파일을 교체해 마지막 해시 검사 FileNotFoundError로
전체 FAIL이다. 기록을 보존하고 빌드 완료 후 고정된 r2로 재검증했다.

## 다음

N3는 부분 완료다. 자율 임무 수명/공통 adapter 및 N4 로컬 fresh scan·footprint
충돌방지는 아직 구현·통합 검증이 필요하다. N2 qualification-readiness 통합과
N5 Twin 재생·동일조건 비교도 남아 있다. 이번 수정은 PC에만 있으며 새 실물 배포/
실제 네 방향 해제/통신손실 인수검증은 사용자 복귀 후 별도 승인 전 실행하지 않는다.
