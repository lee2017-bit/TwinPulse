# TwinPulse 생성 시작과 SIM 도착 안내 검증

2026-10-12 Baseline v1.0.462. 새 장면 생성의 별도 Approve 질문을 모드·로봇 선택과 합쳤다. 비용 한도와 전송 대상은 같은 질문에 표시하며, 현재 입력·모델·가격을 다시 검사한 일회성 범위로만 생성한다. 사용자 Run의 정상 도착과 우측 화면 표시 문제는 구분한다.

## 사용자 Run에서 확인한 사실

프로젝트 `chat_mv4tkhzo_69b66279`의 생성 operation은 `b1c3e0ed-c62e-424b-ac1a-82202925a91c`, 생성 실행 ID는 `13e0f5f8b131428e948a481bf726d9b0`다. Run 실행 ID `5c4574a9b7534abd93e4932dac474e6b`와 command `5c8f5889-ebc1-4415-8f90-3032400b87cd`의 엔진 ACK는 성공했다.

자동으로 준비한 최초 시험 경로 길이는 0.40m다. 같은 plan ID `0583b8f2d8dee40bfd5b857cee8ea09e814b5813d2b26bcf30c43a9544161ddb`에 대해 실제 엔진 상태 파일은 `completed`, 목표 거리 `0.039532067404143174m`, safety state/reason 없음이었다. 4cm 도착 기준 안에 들어와 정지한 것이며 연속 배회 작업이 아니다. Run ACK만으로 도착을 주장한 것이 아니라 엔진의 완료 상태도 확인했다. 원 로그에는 이번 주행의 도착 시각/총 경과 시간이 없으므로 정확한 실행 시간을 만들지 않는다.

기존 Preview는 현재 SIM 위치에서 입력창의 같은 목표로 다시 계획한다. 이 상태에서 목표까지 10cm 미만이면 core의 `SIM_GOAL_TOO_CLOSE`가 발생한다. 현재 위치와 목표 사이가 3.95cm이므로 동일 목표를 다시 계획하면 그 조건에 해당한다. 새로운 목표를 지정해야 한다.

읽기 전용 브라우저 관측에서도 `Physics completed`, `SIM navigation · completed`를 확인했다. 동시에 우측은 `Viewer waiting / stale`, 별도로 `Control lease is invalid or expired` 경고가 있었다. **현재 3D 송출 중단 원인과 도착 이후 lease 경고는 해결되지 않았다.** 완료된 주행의 실패로 바꾸거나 전체 제품 정상으로 기록하지 않는다. 설치된 Kit 캡처 구현도 읽었으나 현재 publisher 내부 관측 없이 캡처 객체 소실 등을 확정 원인으로 쓰지 않는다.

## 적용한 변경

- 새 입력의 모드/지원 로봇 질문에 비용 한도와 모델·전송 범위 disclosure를 함께 표시한다. SIM 선택 후 `Create Twin`, 또는 지원 로봇 선택 후 같은 버튼으로 생성하며 별도 Approve 질문을 추가하지 않는다. 사진·파생 렌더는 실제 정책에서 허용된 범위만 표시한다.
- 기존 `GenerationApprovals`의 fresh descriptor 비교, 가격 만료, 최소 예약, 일회성 scope, 입력·route·정책 SHA, UNKNOWN 비용 예약과 출력 소진 중단을 유지한다. UI가 미리 자동 클릭하거나 저장된 질문만으로 유료 호출하지 않는다. 가격 정보가 없거나 오래된 클라이언트는 기존 명시 검토 경로를 유지한다.
- 완료 상태는 상단 Current step과 SIM 카드에서 정상 도착으로 안내한다. 최초 시험 경로의 길이와 유한 경로임을 표시한다. 같은 목표의 10cm 미만 재계획은 안내만 하고 새 계획/Run을 보내지 않는다. core 도착·경로·충돌 기준과 실제 Run 확인은 변경하지 않는다.
- 실패 후 추가 예산으로 재개하는 확인, 실제 로봇의 초기화·주행·검사 확인은 이번에 없애지 않았다. 모델 설정과 사용자 실행 중 프로세스도 변경하지 않았다.

## 검증 결과

- 전체 Web **486 PASS**: [최종 JSON](../../outputs/sim-generation-ux-20261012/web-final.json). 관련 Python **141 PASS + 14 subtests PASS**: [XML](../../outputs/sim-generation-ux-20261012/python-after-02.xml). 서로 다른 집계를 합쳐 제품 전체 검사 개수로 만들지 않는다.
- TypeScript/Vite 빌드 PASS. build manifest의 3개 파일 SHA가 실제 파일과 일치한다. JS `index-B9Fd9_Ce.js` SHA `a637f3255f48531536ecc0b66bc6e405c4b8f7ef0379da36bc88bcc4625cb3d8`.
- 실제 Chrome와 일반 인증 App/API에서 새 입력→한 질문/한도→Create Twin→생성 완료를 통과했다. 답변 POST 1회, 별도 Approve 질문 0, page error 0, broker 명령 0, 자체 API/Chrome 정상 종료: [결과](../../outputs/sim-generation-ux-20261012/browser-final/summary.json). **LLM 응답은 audited fixture 2회, 실제 외부 API 비용/요청 0, 새 Isaac/실물 시험 0**이다. 새 실제 모델·GPU 전체 인수로 승격하지 않는다.
- 잘못된/부족한 한도, 바뀐 모델 설정, 기존 REAL 확인 경계, 동일 request 중복, 저장 이력 재열기에서 유료 요청·권한이 생기지 않는 회귀를 포함한다.
- 최초 Python-before의 잘못된 테스트 method, before-02의 제품 실패, Web-before 34 PASS/2 FAIL, Python-after-01의 에러 문구 matcher 79 PASS/1 FAIL/12 subtests를 그대로 보존했다. matcher는 문자열 추측 대신 정확한 `generation_approval_stale` 코드로 검사한다. canvas 미설치 경고/큰 bundle 경고를 새 설치나 기준 완화로 숨기지 않았다.

## 실제 Chrome 화면

이번 화면은 일반 App/API와 명시 provider fixture의 UI 결과이며 엔진/렌더는 연결하지 않았다.

![별도 Approve 없이 모드 선택과 생성 시작](../../outputs/sim-generation-ux-20261012/browser-final/01-single-choice.png)

![같은 일반 API에서 생성 완료](../../outputs/sim-generation-ux-20261012/browser-final/02-generated.png)

## 남은 확인 순서

1. 사용자가 정상 종료·재실행한 뒤 새 대화에서 실제 설정 조합의 한 단계 생성 흐름을 확인한다. 현재 실행 중인 Python 세션이나 기존 저장 질문을 자동 갱신·실행하지 않았다.
2. 실제 publisher/GPU 캡처 및 화면 수신의 신선도와 오류를 관측해 우측 stale 원인을 재현한다. 원인 확인 후 수정하고 현재 3D 표시를 재인수해야 한다.
3. 정상 도착 이후의 lease 만료 경고를 active Run의 lease 상실과 구분해 검사한다. watchdog을 끄거나 임의 재획득/자동 재시작으로 숨기지 않는다.

사용자 원 `project.conversation.json` SHA `2da9901f608b5740fb1542d2e189fb80cedbb26c70260165592fd61682b4e946`, `project.json` SHA `63646257e8357d72544e566704f0f8b35661c3783e901be6c42cdba2b228ed3c`는 두 번 읽기 비교에서 동일했다. 기존 센서/실패/예산 자료는 보존했다. 이 변경으로 실물 LiDAR 자동 보정의 공통 commit/Undo 또는 현장 인수가 완료된 것은 아니다.
