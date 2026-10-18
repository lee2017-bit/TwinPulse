# N4 부분 — App의 한 번 승인 임무 시작·상태·취소

2026-09-28 08:21 KST. 사용자 `그래 다음으로 가자`의 오프라인 구현 승인.
로봇 접속/배포/실센서/모터/전원 조작은 하지 않았다. 예약은 PAUSED다.

## 연결한 제품 경로

- 기존 실물 컨트롤러 패널에 임무 범위 입력/시작/취소/최신 판단을 연결했다.
  범위는 odom **절대** XY 1~16개(각 ±10m), 시간 0초 초과·45초 이하다.
  사진·방 Twin 좌표를 자동 변환하거나 정합 완료로 취급하지 않는다.
  범위를 바꾸면 시작 전 확인을 해제하며, 시작 후에는 서버의 deep copy를 고정한다.
- 기존 인증/CSRF/정확한 body 검사를 사용하는 `/robot/physical/mission`으로
  한 번만 시작한다. 같은 ID에 다른 범위를 붙이면 거절하며 자동 재시도하지 않는다.
  실행 중 UI는 방향 명령이 아닌 watch만 보내고 같은 기존 상태 조회를 사용한다.
  별도 방향 입력은 거절하고 취소한다. Esc/창 이탈/백엔드 상실/unmount 및
  늦은 start 응답은 기존 epoch/job 소유권 경계로 close만 보낼 수 있다.
- 로봇 worker의 새 stdin bootstrap은 calibration 무결성 확인 후 현재
  boot/release/calibration hash·로봇 monotonic 시각·1회 nonce를 발급한다.
  PC는 승인한 경로를 이 문맥에 결속해 보낸다. 로봇에서 2초 안에 정확한 문맥과
  범위만 수락하며, PC 시계를 로봇 시계로 사용하지 않는다. 공유 mission-request
  파일을 덮어쓰거나 별도 shell/scp 경로를 추가하지 않았다. 기존 파일 loader는
  회귀/검토용으로 남고 실제 worker 분기는 새 수신 경로를 사용한다.
- 그 후 기존 qualification/소유권/1회 소비 marker/센서 검사/로컬 판단/최종 독립
  OFF 경로를 사용한다. 정지 정책·입력 기한·과거 실패는 변경하지 않았다.
  준비 과정에서 패키지 설치나 정지 시험을 자동 실행하는 기능은 추가하지 않았다.
- 승인 범위와 해시, 실제 전송 request 해시를 기존 session journal에 저장한다.
  기존 이력 JSON에 범위/전송 해시를 포함하고 robot mission_started의 해시와
  대조했다. nonce/challenge는 journal에 저장하지 않는다. 명령·관측·실물 성공은 별개다.
- 공통 범위/문맥 계약은 core에 두고 robot bundle에 동일 파일을 포함한다.
  새 API는 shell 문자열/실행 코드/사용자 지정 장치 주소를 받지 않는다.

## 현재의 중요한 제한

**실제 로봇 자율 실행은 여전히 잠겨 있다.** 검토된 실제 배포·보정 등록 경로가
없으므로 기본 fixed SSH transport의 mission start를 서버에서 거절한다. HTTP 필드,
좋은 과거 보고서, factory 교체만으로 잠금을 풀 수 없다. 현재 출하 profile에도
autonomous policy가 없고 실제 calibration을 만들지 않았다.

`mission_readiness.start_available`은 이 증분에서 **주입된 로컬 시험 transport**에만
true다. 로봇 readiness/동작 허가 판정이 아니며 physical_ready는 항상 false다.
UI는 이 사유가 개발 준비 미완료이며 재부팅·정지시험 반복으로 해결되지 않음을 표시한다.
가짜 장치로 검증한 전달 경로를 실배포가 된 것으로 표시하지 않는다.

현재 임무 UI의 JSON 좌표는 개발용 odom 범위 입력이다. 최종 목표인 방 Twin의
목표 선택→검증된 실제 좌표 변환과 연결된 최종 데모 UI는 아니다. 장애물은 종료
정지하며 우회/재계획이 없고, 실측 기록의 방 Twin 정합 재생도 아직 남았다.

## 실제 수행한 검사

- 관련 Python 79개(새8 포함)는 전체 회귀에서 PASS. 범위 복사/경계,
  robot-clock bootstrap/취소/잘못된 nonce·문맥/만료, 기본 실물 transport 잠금,
  production PC→가짜 subprocess→production request/mission/RosLink→저장이력,
  취소/방향 주입/heartbeat 단절을 검사했다. 별도 audit6 PASS.
- UI 단독20개 PASS(새6 포함): 1회 승인·자동 watch·취소, 기본 live 잠금,
  blur/Esc/backend/unmount 뒤 늦은 mission start의 재활성화 금지.
- `artifacts/mission-app-regression-20260928-r1/manifest.json` 전체 PASS:
  core163/Web118/build 및 기존 App/bridge/process-manager 검사.
  출력의 fake SSH/password 오류 문자열은 실패-path fixture이며 실제 접속이 아니다.
- 초기 단독 시험에서는 완료/마지막 heartbeat의 시험 harness 경합과 가짜 센서가
  Windows 같은 monotonic tick을 중복 발행하는 문제가 드러났다. harness의 종료
  상태 처리, fixture의 새 timestamp일 때만 표본 생성 및 production static helper
  연결을 수정했다. 센서 중복/신선도 검사나 동작/정지 기준은 완화하지 않았다.
  npm은 현재 PATH에 없었으므로 이미 설치된 프로젝트 pnpm으로 검증했다.
- `artifacts/mission-app-browser-20260928-r1/result.json` 실제 App/Chrome +
  로컬 가짜 장치 **16단계 PASS**. 새 임무는 1회 시작, 자체 출력15회/16판단으로
  도착(odom x≈0.025m, 목표0.04m, 기존 도착 허용거리0.015m), 별도 임무 취소 확인.
  원격 입력은 watch/close뿐이며 범위1개/전송 request1개/시작 해시 일치를 export로
  확인했다. 전체9로그827events(robot512), 가짜 출력53. 실물 이동/정확도 증거 아님.
  새 패널 desktop 캡처를 직접 확인했고 모바일 가로 넘침/외부 요청/페이지 오류0.
- `artifacts/mission-app-isaac-20260928-r1/result.json` 같은 build의 실제
  App/bridge/Isaac **8체크 PASS**: 기존 근사 방/Burger4mesh·합성 B의3시점·USD
  재열기/원본 보존. 새 mission을 Isaac physics로 실행한 것이 아니다.
  Physics Run/로봇/provider0. 기존 종료 VtValue 경고는 보존했다.
- `artifacts/mission-app-evidence-audit-20260928-r1/result.json` PASS:
  현재50개 선택 source/build 파일·공통 해시/dist 목록 일치.
  전체 저장소 인증이나 독립 실물 acceptance가 아니며 regression manifest 자체에는
  source hash가 없다. 검증 프로세스 모두 정상 종료했다.

## 다음 순서

1. 기존 실제 모델/센서 자료와 저장 관측으로 frame/footprint/보정 근거를 검토하고,
   live mission 배포 등록 및 readiness 경계를 구현한다. 알 수 없는 값은 만들지 않는다.
2. 방 Twin 목표와 검증된 odom 변환 결속, 명령·실제 관측의 정합 재생을 연결한다.
3. 장애물 우회/재계획을 같은 로컬 보호 경계 안에서 검증한다.
4. 사용자와 새 실물 시험 범위를 합의한 후 배포/센서·정지·단절/제한 임무를 확인한다.

전원 ON만으로 실물 자율 데모가 완료된다는 뜻이 아니다. 지금은 로봇을 켜둘 필요 없다.
