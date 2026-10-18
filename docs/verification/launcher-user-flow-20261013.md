# TwinPulse 실행 파일과 실제 클릭 검증

2026-10-13 / Baseline 1.0.470. [화면 7개를 포함한 단일 보고서](../../outputs/launcher-user-flow-20261013/report.html), [실행 ID와 정확한 범위](../../outputs/launcher-user-flow-20261013/acceptance.json), [동결 소스와 실제 배포 번들 SHA](../../outputs/launcher-user-flow-20261013/source-manifest.json).

## 원인과 수정

사용자 실패 `e71b5aad84e94ced9125d598dc60a13c`는 제가 남겨 둔 소유 PID320이 살아 있는 상태에서 `Start-TwinPulse.cmd`가 기존 실행으로 연결하지 않고 `launcher_already_running`으로 종료한 결과다. v469의 앱 내부 시험은 이 실제 시작 경로를 검증하지 않았으므로, 사용자 실행까지 완료했다는 앞선 표현은 과도했다. 원 실패와 당시 제한된 통과를 모두 보존한다.

같은 저장소·runtime의 살아 있는 소유자에게 재열기 요청을 보내고, 소유자가 메모리의 인증 정보를 이용해 일회용 창 열기 토큰을 발급한다. 요청/응답 파일에는 키·토큰·인증 헤더를 저장하지 않는다. 두 번째 실행은 기존 포트·backend·Isaac을 유지하고 정상 코드0으로 끝난다. 다른/구형 소유자·손상 잠금은 채택하거나 강제 종료하지 않는다. 시작 잠금이 상태 파일보다 먼저 생기는 구간은 같은 소유자를 최대5초 기다린다.

동시 창 열기는 아직 교환하지 않은 토큰을 덮어쓰지 않도록 메모리에서 최대8개·원 유효기간·각1회 교환으로 관리한다. 프로젝트 전환에서도 같은 인증 저장소를 공유한다. 유효한 기존 cookie/CSRF와 절대 만료를 보존한다. 동시 초기 교환으로 cookie가 바뀐 오래된 탭은 서버가 **실행 전** 명확히 반환한 `csrf_rejected`에만 현재 세션을 관측하고 **같은 프로젝트에서1회** 복구한다. 불명 응답·다른403·오래된 프로젝트 쓰기는 재전송하지 않는다. 준비 완료 뒤 엔진 종료 코드0은 정상 종료로 기록한다.

## 실제 사용자 경로

Computer Use 스킬은 CMD/터미널 및 Explorer에서의 간접 CMD 실행을 금지한다. 따라서 사용자의 **동일한 Start-TwinPulse.cmd를 수정 없이 실행 도구로 실행**했고, 이후 Chrome의 실제 입력·Enter·선택·클릭·파일 선택으로 진행했다. 직접 product API 생성·사전 선택 fixture 프로젝트·고정 모델 응답으로 사용자 인수를 대체하지 않았다. Windows Computer Use의 Isaac 창 캡처는 최소화 복구 후에도 타임아웃되어 native X 종료는 NOT_RUN이다. 소유자 정상 종료 요청을 사용했다.

| 실제 경로 | 결과 |
| --- | --- |
| 동일 Start 파일 두 번 즉시 실행 | 최종 두 창 연결 및 첫 창 New chat PASS |
| New chat → 직접 입력 → Enter → Simulation only → Create Twin | 실제 Super3 HTTP, 현재4/4 표시·Orbit PASS |
| Run simulation 버튼 클릭 | PhysX 목표 도착/정상 정지, 표시 goal distance 약0.04m PASS |
| 연결 완료 후 Start 재실행 | 같은 실행 ID/포트/프로세스, 종료0 PASS |
| 새 대화 → Attach/file chooser → 사진만 Send → SIM only/Create | 실제 Flash/Super7 HTTP, 현재 모델 inventory18/18 PASS; 정밀 사진 품질 미검증 |
| 시험 앱 창 모두 닫고 Start로 재열기 | 같은 실행 ID/URL·사진 대화 복원, 추가 추론/자동 Run0 PASS |
| 실제 시험 소유자 정상 종료 → 계측 env 제거 → Start | 일반 환경의 default New chat PASS |
| 일반 재시작 → 사이드바 사진 선택 → Reopen saved scene → View current Twin | 같은 저장 SHA/scene revision·새 세션 현재7fps PASS |
| 일반 환경에서 Start 재실행 | 종료0/같은 일반 launch PASS |

`Reopen saved scene`은 입력/이력 복원만 하고 Build/Run을 자동으로 시작하지 않는다. 완전히 새 엔진에서는 `View current Twin`을 눌러 현재3D를 표시했다. 이것을 누르기 전의 오래된18개 표시 수를 현재 렌더로 세지 않았다.

최종 시험 launch `b06288c17d8941518ca86fc46dc5e2eb` / `127.0.0.1:53681`, owner17236/backend19724/engine wrapper8508. 일반 사용자 재시작 launch `4fd7d4bd28614c80914eab7cc8a300b5` / `127.0.0.1:58517`, owner2776/backend15796/engine wrapper19852. 일반 앱은 사용자 확인을 위해 켜두었다. 기본 장면과 대화 SHA는 각각 `2A87C489…CB9B`, `96612F9F…4EFA`로 이전 실제 복사본과 동일했다.

텍스트 operation `3284b12f-6a0b-4b3a-80d9-bfa4d0451a01`, generation execution `b1584eda5ab344ef8aae4c741e21edeb`, Run execution `ff64b945038a4af4abdde225a25182f3`. 사진 operation `e83d2973-26b5-4ced-a04a-bea50e772d7e`, execution `9c27e80e5d2749f786bafecb73ec420c`, 저장 SHA `89FF0C270BC621B4ACA26F91232EB3CC9A846308CD7F82DE4FCEF5622A9514A0`, scene revision `4c7c7be45de34b1230a8ad18284adede50139d5b3059ac665735603733b05a4b`.

## 실패와 비용

첫 실제 재시험은 상태 파일 초기 경합으로 FAIL(`5464648f410040dbb00f232b4dbd1d15`). 두 번째는 CLI0이어도 첫 창 토큰 덮어쓰기로 FAIL. 세 번째는 두 홈이 연결됐어도 실제 첫 New chat 클릭의 CSRF 불일치로 FAIL. 마지막 source/번들에서 같은 실제 경로를 다시 실행해 통과했다. 원 logs·실패 화면·진단 ID를 남겼다. 보조 검사 중 비동기 진단 flush/임시 폴더 정리2ERROR, 불완전한 테스트 session metadata2FAIL도 별도로 남겼으며 이후 Python75/Web534/TypeScript/production build PASS다. 단위 수치를 실제 클릭 통과 수로 합산하지 않는다.

사진 파일 선택 도구가1433초 걸렸다. 이는 LLM/앱 생성 지연이 아니다. 앞선 첨부 시도에서는 좁은 창의 열린 사이드바와 겹친 입력을 누르는 동안 다른 대화가 선택되어 chooser event가 오지 않았다. 사진 전송0을 확인하고 올바른 대화를 선택·사이드바 닫기 뒤 실제 파일 선택을 완료했다. 도구 지연을 모델 벤치마크 시간으로 사용하지 않는다.

추가 실제 추론10HTTP/추정 USD0.0450567. 동일 승인 장부 누적42HTTP/USD0.2361993, 새 held0, 과거 미확정 USD3 보존. 원 USD10 한도를 초기화하지 않았다. 공급자 청구서 대조는 하지 않았다. 일반 재시작에는 `TWINPULSE_AGENT_TEST_SCOPE`를 전달하지 않았다. 앱의 삭제된 금액/가격 gate를 다시 추가하지 않았다.

## 남은 범위

- 다른 창에서 대화를 바꾸면 이전 창은 stale 요청을 거절하며 새로고침해야 한다. 실제 reload 회복은 PASS지만 자동 다중 창 동기화와 `Refreshing` 안내 개선은 남는다.
- 사진18/18은 모델 목록의 현재 표시 수다. 실측·모든 사진 물체·외형/위치/지지 관계의 인간 검증은 아니다. 추정과 시각적 불확실성을 보존했다.
- 이번 시작 파일 milestone에서 새 텍스트+사진·새 실제 feedback/Undo·설치 배포 분기·실물/Cloud는 재시험하지 않았다. 이전 scoped 인수와 섞지 않는다. Provider4 계약, live LiDAR/common Undo, 현장·새 설치는 이전 잔여다.
- 앞으로 사용자 인수는 동일 진입 파일과 실제 클릭/입력으로 수행하도록 AGENTS.md에 기록했다. 원 자료·dirty 변경·키·불명 비용을 보존하며 공개/commit/push/설치0이다.

사진은 Chris Olszewski (Kgbo)의 [Brisbane bedroom 2025](https://commons.wikimedia.org/wiki/File:Bedroom,_Interior_of_apartment_in_Brisbane,_2025,_02.jpg), CC BY-SA4.0이다. 원 SHA `3888e47ad6c73ed4360aca67f278b19a4d2c31fb163a266adde23f74f8bed401`를 보존했고 모델 전송 표현에만 MPO 첫 사진 JPEG를 사용했다. 개인 사진·키·raw는 공개 업로드하지 않았다.
