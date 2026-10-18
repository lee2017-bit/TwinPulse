# 로봇 집중시험 준비 · 필수 인수

> 전원 ON 후 정정(2026-10-18): 아래 READY는06의 당시 PC/SIM 준비 인수 이력이다. 이후 실제 Connect 화면 crash, native stationary/ROS freshness 및 ENOSPC가 재현됐으므로 현재 실제 로봇 전체 준비는 **NOT_READY**다. 바퀴 명령0. 최신 진행/실패는 PROJECT_MEMORY v536과 SIM archive 설명을 따른다. 과거 gate를 현재 실물 PASS로 사용하지 않는다.

현재 상태: **READY_FOR_SUPERVISED_POWERED_TEST / 이 PC의 최종 설치 App 소프트웨어 경로 인수 완료**. [최종 단일 보고서](../../outputs/robot-focused-test-20261018/report.html), [해시 결속 gate](../../outputs/robot-focused-test-20261018/gate-result.json). 실물은 OFF/충전 유지했으며 센서·주행·제동·정합 성공은 NOT_RUN이다. 규칙만 적어 완료한 판정이 아니다.

목표는 사용자 감독하에 전원을 켰을 때 설치 App만으로 연결·센서·조종·정지·기록 반출을 시험할 수 있는 소프트웨어 상태다. 실제 로봇은 OFF/충전 유지, SSH/센서/모터 동작은 이번 준비 인수에 포함하지 않는다. CAD/BRep·산업 인증·사진 정밀복제·다기종 실제 하드웨어 보장은 이 목표의 선행조건이 아니다. 기존 미완료를 완료로 바꾸지도 않는다.

## 소유·계약

Main이 Python/Isaac/UI/시험/패키징·설치·통합을 순서대로 소유한다. 같은 파일 동시 편집 없음. 기존 fleet API·연결/동작 epoch·expiry·Stop 우선·기록 context 계약을 재사용한다. 무단 자동 재접속·명령 재전송·기준 완화 없음. 별도 하위 기능의 완료로 이 상위 목표를 종료하지 않는다.

## 최종 설치본 필수 증거

| ID | 사용자 여정 / 통과 조건 |
|---|---|
| F01 | 일반 root Start → 120초 이내 인증 Isaac ready; 중복 Start는 같은 owner/8765, 일반 debug listener 없음. 정상 종료·재시작도 확인. |
| F02 | 같은 설치 Electron 실제 UI에서 저장 Twin 열기·현재 Isaac 표시. stale 장면을 live로 표시하지 않고 카메라/연결 상태 정상. |
| F03 | SIM 2대 등록·명시 선택/연결, 이름·연결 표시·배터리 출처와 unavailable 구분. 한 로봇 정지가 다른 연결을 끊지 않음. |
| F04 | 패드/키보드 4방향, 입력 해제·focus loss·Stop와 새로운 명시 입력. 60초 연속 hold 중 예기치 않은 연결 중단 없음. |
| F05 | 실제 채팅 90도 및 한 세션 360도+LiDAR, 실제 engine pose와 완료 결과 확인. 원래90도 실패를10도로 대체 금지. 저FPS 시간적분/동일목표 회귀 포함. |
| F06 | 실제 LiDAR On/Off·현재 frame/stream·기록. 준비/센서 버튼이 최신성 경합으로 반복 실패하지 않음; 의도적 fault 거절과 정상 경로 오류 구분. |
| F07 | 근접 SIM 정지·후진 탈출, 지연/입력 만료·Stop all. 원래 안전 기준·원 expiry 유지. SIM은 물리 성능 증거 아님. |
| F08 | 설치 manifest의 physical_robot=true인 현장용 개발 구성. Robots 실제 UI에서 저장 장비·PC 준비·명시 연결/현장 설정·전체 시험 목록·원문 export 진입 확인. OFF에서 연결/이동 시작하지 않으며 외부 JSON 작성이나 숨은 스크립트가 필수 아님. |
| F09 | 실제 작업 로그의 채팅/conversation/Twin revision/engine/stage → operation/command/trial/scan/raw SHA 연결, 펼친 화면 가독성·다운로드 확인. |
| F10 | 실제 장면 편집·Undo·저장/프로젝트 전환·cold reopen에서 과거 기록 보존·늦은 결과 차단·권한 자동복원0. 한 릴리스 증거에 결속. |
| F11 | 기존 실제 native 자료의 no-device replay로 worker/decoder·설정/field test·Stop/cleanup·원문 반출 계약 보조검증. fixture나 replay를 실물 PASS로 합산하지 않음. |
| F12 | 하나의 보고서에 모든 시도/현재 릴리스·입력·실행 ID/SHA·오류·시간·비용·물리 NOT_RUN과 현장 순서. machine gate가 누락/다른 빌드/원 실패 미해결을 차단함을 별도 negative test. |

모든 F항목은 최종 설치 릴리스와 시험 모드를 명시한다. 관련 제품 변경 후 영향 여정을 재시험한다. 분할 조회/복원 증거는 허용하되 한 번의 fresh 전체 실행인 것처럼 합치지 않는다. 정상 핵심 SIM 여정은 중간의 실패 후 수동 이어하기 없이 end-to-end 통과해야 한다. 실제 UI의 의도적 fault 주입은 구분하고 예상한 거절 여부로 판정한다.

## 원 차단 결함과 최종 후속 판정 (원 FAIL 보존)

- B01: lineage ui-11 operation `8f1ed1ef821f40d7af9f3f624e8e0d3b`, 90도85.94도/TASK_TIMEOUT. 저FPS dt clipping/벽시계 deadline 충돌은 가설이며 계측·동일목표 실제 재인수 필요.
- B02: lineage normal-01 entry120.210초 ready 미관찰. supervisor 자체118.319초와 다른 측정 구간. 원 실패 보존, 원인·시작 경로 실제 재시험.
- B03: 최종 lineage ui-16 센서 stale409/preview_expired409·status/image abort. expected guard와 정상 경로 경합 구분 후 실제 UI 재시험.

최종06 `20261018T044930Z-d0d4e62d6701` / source `d0d4e62d67010295e5b30e6350a352fbe0dd6344b4ad964e7919997c11a33a93` /1609파일 SHA exact. 아래 경로는 `outputs/robot-focused-test-20261018/` 기준이며 원문과 SHA는 evidence-manifest/gate에 결속했다.

| 항목 | 최종 설치 실제 증거 / 판정 |
|---|---|
| F01 | normal-06/result.json 43.817s, normal-06-restart/result.json 43.244s·동일owner/8765하나/debug0. normal-06/shutdown.json owned16→0/lock·리스너0. 동일 Start는 실행도구 호출, 일반종료는 지원 owned graceful request. Explorer/native전체 NOT_RUN. |
| F02–F07 | ui-03/result.json fresh27단계 전체PASS. 원90° 실제1.5707963267948983rad/5.984s,360°/141scan·61초hold·4방향/키/focus·2SIM·LiDAR On/Off·currentframe·근접Stop/후진·fault/Stopall. 일반HTTP/page/미분류GET0, 명시drive지연 취소4는 별도. 실제 모델 새생성41.882s. |
| F08 | 같은 ui-03 + ui-cold-03/result.json PC준비/read-only연결진입/감독설정 저장·11case/strict거절·권한복원0. physical_robot=true 구성. OFF에서 실제 연결버튼/센서/모터 실행0. |
| F09–F10 | lineage-03/result.json 8PASS, lineage-cold-03/result.json 3PASS: 실제 원90°/scan·ID로그/수정·저장·Undo새revision·전환종료·원history bytes/SHA보존. ui-cold-03은12단계 별도전체PASS. 분할 이어하기나 한 번의50단계로 합산하지 않음. |
| F11 | offline-07/result.json source 전후동일/5집합PASS: PC168중native-symlink1skip/native31(실제저장원자료 replay)/field13/UI216/tsc. no-device 보조이며 실물증거 아님. |
| F12 | evidence-manifest.json 9역할/6도구SHA·gate READY issues0. 실제 ui02 미귀속GET 원문 negative gate NOT_READY/UNCLASSIFIED_REQUEST_FAILURE:fresh, 누락·구릴리스·각도축소·120s초과 negative11시험. 원시도 전부/추가도구실패/비용/화면/현장순서 단일report. |
| B01 후속 | 원 ui11 FAIL 보존. 저FPS elapsed/입력경계 수정 후 같은90°를 fresh03 및 lineage03에서 완료. 기존 속도/deadline/watchdog 유지,10°대체0. |
| B02 후속 | 이전 lineage normal-01 원FAIL 보존. 최종 일반/재시작 위43.817/43.244s; 조상경로검사 최적화가 과거 전체지연의 유일원인이라는 주장은 안 함. |
| B03 후속 | 최종 fresh/cold/lineage의 실제 센서·현재프레임 정상경로 통과. 별도cold PC준비 ready경합은 재현/수정. 원abort 및 중간ui02 GET5개 단일원인은 미확정이고 최종클린실행으로 원FAIL을 지우지 않음. |

Astra xhigh 독립 읽기 감사1명은 원목표·필수표·원FAIL·최종raw/해시/negative를 검토해 새P1/P2차단 없음으로 확인했다. 이번15HTTP/추정USD0.1345758/미확정0·추가50누적USD0.9892311. 이전20장부 별도유지. 사용자 거실 저장Twin 복원/표시2PASS는 기존 사진품질PARTIAL/uncertain을 유지한다. App/Isaac는 정상종료했다. 전원 후 실제 조건에 따른 현장 시험 성공은 앞으로 별도 판정한다.

## 전원 후 한 번의 집중 세션

같은 LAN/충전선 분리/현장 감독 → App 로봇 선택·PC 준비·Check Connection → 배터리/현재 연결/boot → 정지 원 native 수집·저장 → 명시 현장 설정/감독확인·저속 정지 관측 → 짧은 전후진/좌우 회전·해제/Stop → 90도·한 바퀴+scan·연속 수신 → 안전한 범위의 장애물 정지 관찰 → operation/trial/raw 반출·정상 연결 종료. 실제 측정/안전조건이 부족한 가지는 정확한 이유로 멈추고 나머지 독립 수집을 계속한다. 접촉/고의 차체 구속은 요구하지 않는다.

실물 차체정체/제동·외곽10cm·실제 Wi-Fi 단절·world 정합 정확도는 전원 후 별도 판정이며 로봇OFF 준비 PASS에 포함하지 않는다. 사용자 촬영과 App 영상은 같은 operation/Twin ID로 맞춘다.
