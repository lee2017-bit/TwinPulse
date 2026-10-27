# 2026-10-27 저녁 실물 주행 — 한 장 절차 (PHYS09 이후, 새 빌드 기준)

전제(모두 완료/자동): SD 카드 정리(여유 5.9 GB), 링크 소크 PASS(22:22Z, 5분 LiDAR 10 Hz, FAULT 0, 정리 영수증 OK), 수정 빌드(세션 게이트 UI·로봇 디스크 점검·errno)가 게이트 PASS 후 자동 설치됨. 설치 여부는 상단 바 Diagnostics의 build id가 `20261026T125513Z`가 **아닌지**로 확인.

## 사용자가 하는 것 (총 4번의 손길)
1. 로봇 전원 ON → 시작 테이프 마크(x 0.681 / y 0.206 / yaw 0.489)에 놓기 → "켰다".
2. 로봇 카드 **Supervised session gate**(버튼 바로 아래, 항상 보임)에서 체크 ① "I am present…" → "체크했다" (제가 Prepare).
3. 같은 자리에서 체크 ② "I am supervising, charging is unplugged…" → "체크했다" (제가 Arm) → 체크 ③ "I reviewed the Bootstrap stop trial scope…" → "체크했다" (제가 Run Bootstrap stop: 0.03 m/s 최대 0.6 s 전진 후 정지).
4. 경로 카드가 뜨면 제가 알림 → 상자(40–50 cm)를 1구간 위, 시작점 약 1.1 m 앞에 놓고 "놓았다". (의자 이동은 선택.)

## 제가 하는 것 (클릭·녹화·판정) — 단계 사이에 기다리지 않고 연속 진행, 사용자 손길 4번 외엔 멈추지 않음
녹화 시작 → New chat → 집 USD import → Show Twin → Twin edits Auto-apply → 사진 분석(축소본) → 실물 로봇 선택 → Connect(배터리 읽어 보고만 함 — 시작 전압 기준 없음: 코드 가드(저전압 11.1 V, goal_task_loop의 재무장 여유 11.2 V/20 %)가 받아들이면 바로 시작, 전압으로 기다리지 않음) → LiDAR on → Prepare → Arm → Bootstrap stop → Set position(선언 좌표) → "Survey the room and come back"(Nemotron 1회) → 상자 확인 후 Run route → 근접 정지·25 cm 후진·재계획 → 완주·복귀 → LiDAR 후보 자동 반영 → 재계획 카드 → Run route → 복귀 → Exit(정상 cleanup). 각 단계의 거부 사유는 게이트 블록에 한 줄로 표시됩니다.

## 중단 기준(제가 즉시 멈추고 보고)
코드 가드가 거부(저전압 11.1 V / 재무장 여유 11.2 V·20 %) · 링크 DEGRADED/REJECTED 문구 · 근접 정지 후 RECOVERY 실패 2회 · 사용자가 "멈춰".
Stop을 누른 뒤에는 경로를 다시 요청합니다("Survey the room and come back"). 예전 경로 카드의 Run route가 거부되는 것은 의도된 동작입니다(PR #9).

## 증거/산출물
`%LOCALAPPDATA%\TwinPulse\runtime\devices\local\physical-live\<operation_id>\`(receipt.json complete 확인), 화면 녹화 `outputs/path-b-20261027/rec-physical-*.mp4`, 소크 `outputs/soak/soak-20261026T222210Z.json`.
