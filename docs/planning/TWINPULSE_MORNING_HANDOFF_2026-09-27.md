# 아침 재개 안내 — 2026-09-27

야간 작업은 10:13 KST에 종료 확인했고 후속 예약은 PAUSED다. 마감 후 새 구현이나
로봇 접속은 하지 않았다. 아래 검증 결과는09:16 오프라인 실행의 기록이다.

## 먼저 결론

**지금 전원을 켜고 연결만 하면 최종 실물 데모가 된다는 상태는 아니다.**
밤사이 오프라인 기능과 검증을 진행했지만, 전원이 꺼진 실물에서만 확인할 수 있는
배포·정지·센서·좌표 및 제품 통합 단계가 남아 있다. 이것을 사용자에게 숨기거나
합성 시험의 성공으로 대신하지 않는다.

최종 목표는 그대로다: 현장 사진→초기 Twin→실제 scan 보정→같은 보정 환경에서
두 경로 비교→승인된 실물 실행/실측 결과. 아래 오프라인 리허설은 그중 일부다.

| 구간 | 준비된 것 | 아직 필요한 것 |
|---|---|---|
| 전체 점검 | 진단 코드/JSON·HTML, Prepare/Stationary 명령, saved-report App | 새 패키지 Pi 배포·ARM64/ROS·현재 상태 읽기 |
| 저장 scan | stationary 기록 계약, 좌표 투영, App overlay | 실제 COIN-D4 ROS scan·TF·물리 회전 정지 |
| 보정 | 수동 대응점 XY proposal/review/apply/undo, 검토기록 export | 자동정합, active Twin/Isaac promotion·영구 derived draft |
| 경로 비교 | 동일조건 수동 경로 길이·격자 검사, 보정 후 보수적 장애물 overlay/명시적 임무재검토 | 전체 지도 재생성/관측 free-space·자동최적화·Isaac 추종·실측 성능 |
| 실제 이동 | 과거 짧은 전진·정지 육안 확인, timeout421ms 기록 | 정지 안정122ms<200ms **FAIL** 해결·재검증, 제품 one-shot runner |

## 로봇 없이 바로 확인할 수 있는 한 명령

**재실행 없이 먼저 볼 결과:** [09:16 오프라인 검증 요약/화면](../../artifacts/offline-rehearsal-20260927-091542-a8c40893/summary.html).
Python271/Web37/build/실제 로컬 앱9단계 PASS. 이 파일은 정적 기록이며 로봇·앱을
시작하지 않는다. 화면 속 배터리/scan/경로는 합성 자료다. [검증과 보존된 실패](../verification/overnight-handoff-audit-20260927.md).
기상 후 이 회귀 전체를 다시 돌리느라 기다릴 필요는 없다.

기준 저장소 `C:\Users\jaewo\Documents\TwinPulse`에서 **Rehearse-Offline.cmd** 실행.
기존 개발 의존성이 있는 이 PC용이다. 설치/업데이트는 하지 않는다.

- 전체 오프라인 Python/Web 검사와 웹 build.
- 새 격리 프로젝트·빈 상태, 임시 인증 세션, OS 할당 loopback port의 실제 App 서버.
- 전용 headless Chrome으로 저장 진단→scan 가져오기→같은 조건 경로 비교→막힌
  경로 거부→보정 검토/적용→별도 지도/임무 검토→새 조건 경로비교→실제 파일
  export→undo→새로고침/모바일 확인.
- 결과는 `artifacts/offline-rehearsal-<시각>-<id>/`의 **summary.html/summary.json**,
  `regression/manifest.json`, regression.log와 `browser/result.json`,
  `browser/browser-result.json`, 스크린샷, export에 저장. 같은 실행만 묶고 누락/실패는
  FAIL로 남긴다. HTML에는 제어 기능·외부 통신이 없다.
- 기존 활성 프로젝트/열려 있는 앱을 사용하지 않는다. 생성한 서버와 브라우저만 종료.
  **화면을 계속 보고 있을 필요 없고, 로봇 전원을 켤 필요도 없다.**
- 실패하면 그 단계에서 중단한다. FAIL/UNKNOWN을 무시하고 다음 실물 단계로 넘어가는
  명령이 아니다. 로그·폴더를 남긴 채 원인 확인, 무한 재시도나 기준 완화 금지.

PowerShell에서 창을 닫지 않고 실행하려면:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\rehearse_offline_app.ps1
```

리허설의 health/scan/경로 입력은 **모두 합성 테스트 자료**다. 11.21V/39.4%도 이
리허설에서는 fixture 값으로 현재 배터리가 아니다. 브라우저→서버 통신은 실제지만
로봇·Isaac·유료 모델은 실행하지 않는다. 내보낸 기록은 실행 가능한 프로젝트가 아니다.

## 오프라인 화면을 직접 설명할 때

[D5 보정](../verification/scan-review-app-20260927.md)과
[D6 비교](../verification/route-comparison-offline-20260927.md)의 합성 파일을 사용한다.

1. `Scan review · Offline scratch draft`에 D6 bundle 가져오기.
2. baseline/candidate 점 파일을 입력해 비교. 예제8.000m/4.828m,39.64%는 **수동
   합성 경로의 길이 차이**이며 자동 최적화나 실제 로봇 속도 향상이 아니다.
3. 직선 `[[-2,0],[2,0]]`은4m로 더 짧지만 장애물에 걸려 winner를 표시하지 않는다.
4. 대응점 pairs로 XY 보정 preview→직접 검토 체크→scratch 적용.
   보정 직후 map/mission이 없어서 비교가 비활성화되는 것이 정상. 08:19 추가된
   **Preview conservative map overlay**로 old/new 장애물만 추가하는 지도와 동일
   endpoints를 제안받고 별도 검토 checkbox→**Use reviewed map in scratch draft**를
   누르면 새 조건으로 재비교할 수 있다. 기존 occupied/unknown을 free로 바꾸지 않으며
   원본free는 미검증 inherited 값이다. full map rebuild/SLAM/실물 증거가 아니다.
   새 비교와 export를 본 다음 undo한다. undo 후에는 다시 map/mission이 없어진다.
   [상세한계](../verification/map-overlay-offline-20260927.md).
5. `Robot status`에 저장된 과거 보고서를 보여줄 때 측정 시각·unverified·not-live
   표시를 유지한다. 현재 잔량·현재 안전 상태라고 설명하지 않는다.

## 기상 후 사용자가 먼저 알려줄 것

“일어났고 충전 상태는 ○○, 로봇 전원은 ○○” 정도면 된다.
아직 전원을 켜지 않았다면 데모가 준비됐다는 가정으로 급히 켤 필요 없다.
현재 전원·충전·소리 상태부터 확인하며, 밤사이 전압/충전 완료는 읽지 않았다.
새 배터리 잔량은 전압 기반 추정이고 정확한 용량/남은 분 단위 시간 보장은 아니다.

## 그 뒤 담당 에이전트의 실행 순서

1. [현재 로봇 상태](TWINPULSE_ROBOT_CURRENT_STATE.md)와 새 사용자 답변 확인.
   이번 밤의 로봇 접근 금지는 기상 메시지만으로 임의 확장하지 말고 점검 범위를 확인.
2. 전원 재개·배포/무구동 점검 승인 후 `Prepare-Robot.cmd`의 실제 Pi 배포,
   ARM64 helper/manifest/최종 독립 READ 결과 확인. 주소 변경·실패는 정확히 보고.
3. 실제 stationary/ROS observer 검사. UNKNOWN이면 원인을 해결하기 전 주행 불가.
   [D1/D2 준비와 한계](../verification/robot-charging-offline-prep-20260927.md)를 따른다.
4. D2 dry-run 계약과 실제 C++ trial adapter·영구1회 receipt 연결을 완성/검증.
   현재 이 연결이 이미 준비됐다고 말하지 않는다. 기존 소비된 표식 재사용 금지.
5. 긴 준비가 끝난 후에만 “지금 보고 있다”는 새 답변과 해당 시험의 명시 승인을 받는다.
   승인 직후 제한된 시험을 실행하고 즉시 결과를 알린다. 오래 지연되면 재확인.
   사용자가 준비 시간 내내 로봇을 지켜보게 하지 않는다.
6. 정지 기준을 충족한 뒤 LiDAR 정지/scan/TF와 실제 Burger profile, active Twin/
   map/mission 및 동일조건 실측 비교 통합 검증. 각 단계 실패는 다음 주행을 막는다.

기존122ms FAIL은 관찰된 사실이다. 이것이 곧 하드웨어 고장이라고 단정하지도,
기준을 낮춰 성공이라고 고치지도 않는다. 지금 가능한 것은 검증된 오프라인 부분의
시연이고, 전체 실물 데모 완료 시간은 아직 보장할 수 없다.
