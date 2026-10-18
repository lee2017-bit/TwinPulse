# TwinPulse 아침 인수인계 — 2026-09-28 06:49 KST 마감 전 검수

**최신 09:10:** 공식모델 센서/차체 근거와 저장74프레임을 App에서 검토하고, 방 목표를
명시 미터 대응점으로 odom 후보에 연결할 수 있다. 최종 가짜App20/actualIsaac10/
현재53파일audit PASS. [결과·사용경로](../verification/room-goal-evidence-20260928.md).
**실제 방↔odom 정합 완료 아님.** 다음은 별도 승인 뒤 로봇을 정지한 상태에서 동일
boot odom/TF/ROS scan 방향·시각과 현물 장착/외곽, 방 미터 대응 근거를 확보하는 것.
기존 사진/저장native만으로 변환을 확정할 수 없다. 반복 주행/재부팅은 이 작업의
선행 조건이 아니다. live 임무 잠금·정지 기준 유지, 새실물/배포0·예약PAUSED.

**최신 08:43:** 요청한 일반 정지/강제 STOP·Esc 구현 및 오프라인 검증 완료.
마지막 발행 구간 잔여만 대기/즉시 대기취소를 구분하며 양쪽 모두 기존 최종OFF와
저장기록으로 연결된다. [결과·미검증](../verification/two-stop-controls-20260928.md).
새 코드 실물 미배포, 물리 비상정지나 부하감소 검증 아님. 로봇은 계속 OFF여도 된다.
기본 자율 임무 잠금 및 아래 보정/배포 등록·Twin목표 결속 잔여는 그대로다.

**최신 08:21:** App의 한 번 승인 임무 시작/범위 고정/robot-clock 전달/상태/취소/
저장이력 경로를 로컬 가짜 장치와 생산 loop로 연결·검증했다. core163/Web118/build,
actualAppfake16/actualIsaac8/audit50 PASS. [정확한 증거와 다음 순서](../verification/mission-app-20260928.md).
**실제 transport 잠금은 개발 잔여:** 실제 보정·검토 배포 등록/readiness가 없다.
사용자가 전원을 켜거나 정지 시험을 반복해서 풀 문제가 아니다. 아직 로봇을 켤 필요
없으며 다음은 기존모델/저장센서 frame·footprint 근거 검토와 보정/등록 경계다.
방Twin목표↔odom변환·실측재생/우회재계획도 잔여. 접속·배포0,예약PAUSED,검사프로세스종료.

**최신 07:58:** 기존 worker에 조건부 자율 mission 수명과 1회 request/calibration
검사, 단절/취소/종료처리·판단/관측로그를 연결했다. 기존 App 이력에서 최신판단10개와
JSON을 읽는다. 관련77/전체core163·Web112/build·actualAppfake14/Isaac8/audit49 PASS.
[구현과 다음 순서](../verification/mission-runtime-20260928.md). 실제 calibration 미제공,
현재 profile 자율 policy 없음, App의 실물 mission 시작 미허용이므로 **아직 실물
자율 주행은 할 수 없다.** 우회/재계획과 실제기록→방Twin 정합도 남았다.
접속/배포/실물0·로봇OFF사용자보고·예약PAUSED,검증프로세스종료. 아래는이전시점기록.

**07:20 후속 인수인계:** 야간 예약은 PAUSED 처리 완료. 새 사용자 승인으로
센서 좌표·시간검사와 기존 ROS 출력 접점을 구현하고 오프라인 검증했다.
core163/Web111/build·가짜App13/actualIsaac8/audit43 PASS. [상세 및 다음 순서](../verification/navigation-binding-20260928.md).
실제 로봇 보정/근거 loader와 자율 worker loop·watchdog·재계획은 아직 남았다.
새 메서드는 CLI/UI 자율 실행에 연결되지 않았으며 기존 수동 경로의 충돌보호를
추가 완료한 것도 아니다. 로봇은 미접속/미배포, 예약PAUSED, 검사 프로세스 종료.
아래 06:49 이전 기록의 `마감/중지 대기`와39파일 대조는 당시 이력이다.

**06:49 최종 검수:** 콘솔의 별도 PC 점검 요구 문구를 실제 연결 내 통합 흐름에
맞게 교정했다. `overnight-final-regression-20260928-r1` 전체회귀(core156/Web111/
build 포함), `overnight-evidence-audit-20260928-r3`39파일 대조·audit6 PASS.
아래06:24 actual browser13/Isaac8의 Web 빌드와 동일하며 새 실물 작업은 없다.
현재 실행 중인 검증 프로세스 없음. 07:00 마감 후 최종 보고와 예약 중지는 남아 있다.

**06:24 추가 수정:** 준비 응답 전에 창을 떠났는데 늦은 READY가 조작을 다시 켜는
경합을 수정했다. 신규5 FAIL 재현→컨트롤러14/전체Web111 PASS, actual App→가짜
13단계에서 취소된 시작은 close만·이동0, 같은빌드 actualIsaac8도 PASS.
[수정/검증 상세](../verification/start-context-20260928.md).
현재 증거는 `start-context-regression-20260928-r1`, `start-context-browser-20260928-r1`,
`start-context-isaac-20260928-r1`, `overnight-evidence-audit-20260928-r2`이며39파일일치다.
아래05:55 증거 목록은 이전 빌드의 이력으로 보존한다. 새 코드도 로봇에 미배포다.

**로봇을 켜기만 하면 실물 자율 데모가 되는 상태는 아니다.** 사진 방/Burger 표시와
합성 임무·비교·선택 시점 3D 표시까지는 기존 App 경로에서 확인했다. 실물 자율
실행과 라이다 기반 충돌 방지는 아직 연결되지 않았다. 이 부족분은 사용자 준비가
아니라 구현·검증의 잔여 작업이다. 로봇을 켜 두고 개발 완료를 기다릴 필요가 없다.

07:00 마감 전 중간 인수인계이며 야간 예약 종료 보고가 아니다. 현재 로봇 OFF는
사용자 보고이고 이번 야간에는 접속/배포/센서/모터/전원 명령을 하지 않았다.

## 지금 되는 것과 아직 안 되는 것

| 구간 | 확인한 범위 | 남은 부분 |
|---|---|---|
| 방 사진 → 3D Twin | 사진 기반 12개 상자형 방/가구와 기존 공식 Burger, 실제 App→Isaac 표시 | 사진 그대로의 정밀 재구성 아님. 치수·로봇 pose 추정, 실측 TF 없음 |
| 연결 준비 | 읽기 연결 내부 PC 준비 통합. 읽기 버튼에 숨은 이동 없음 | 배포/현재 boot·release 정지검증/센서 준비를 하나의 readiness로 묶는 흐름 미완료 |
| 수동 입력 | WASD code/IME/CapsLock, 일반 해제 후 같은 세션 재입력, 명시 종료/통신 실패 구분을 가짜 장치에서 확인 | 새 코드는 미배포. 실제 반복 조작·종료 인수 필요. 2초 입력/60초 수동 세션 제한 유지 |
| 명령/관측 기록 | 입력·전송·발행·encoder·배터리·종료 기록, 종료 전 저장, App 이력/JSON. 이미 발행되는 odom/scan의 수동 수신 기록 | 실 ROS 수신 검증, 시간/좌표 정합, 바닥 pose 증명 없음. 없는 관측은 null |
| 임무/충돌 방지 | PC 합성 방에서 공통 검사·waypoint 판단, 장애물/센서 지연 이동 차단 | 실제 센서/TF→로봇 로컬 guard→자율 worker/watchdog·임무 수명 연결, 자동 우회/재계획 미완료. 현재 실물 수동은 scan 보호 없음 |
| 비교/재생 | 같은 합성 scene/start/XY goal/profile의 A/B, 선택한 3시점 actual Isaac pose/yaw 확인 | 실측 경로/연속 애니메이션/PhysX 주행 아님. 충돌 점수는 미측정(null), 실물 성능 비교 불가 |

합성 A는 21.8초/0.4215m, B는 13.95초/0.306m로 도착했다. 이는 고정된 두 경로의
결과이며 실물 최적화나 실제 이동 성능이 아니다. 사진 위쪽=창문은 사용자의 방향
근거지만 센서/base/world 변환이나 실측 배치를 증명하지 않는다.

## 로봇 없이 먼저 볼 수 있는 제품 경로

1. 최신 소스 저장소의 `Start-TwinPulse.cmd`로 App/Isaac 경로를 연다. 이미 열린
   구버전 콘솔을 새 빌드라고 간주하지 않는다. 사용자 프로세스를 자동 종료하지 않는다.
2. **내 방 · Burger Digital Twin**에서 사진/모델 검토 후 근사·시각 전용 조건을
   확인하고 명시적으로 3D 표시한다. 실제 로봇을 연결하는 작업이 아니다.
3. PC 합성 임무, 장애물·센서 지연 경우, 같은 조건 A/B 비교를 확인한다.
4. A/B 기록 선택 → 시점 선택 → 명시 3D 표시. Isaac timeline Run은 필요 없다.
5. **저장된 조작 이력**은 로봇 접속 없이 볼 수 있다. 이전 journal 없는 실물 세션은
   새 목록에 자동 생성되지 않는다. 가짜 회귀 세션을 실제 조작 이력에 섞지 않았다.

로봇 점검/수동 콘솔은 별도 `Open-Robot-Console.cmd`이며 Isaac/provider 자동 호출은
없다. PC 확인은 연결 버튼 내부에 포함되어 따로 매번 누를 필요가 없다. **읽기
점검 완료가 이동 승인·정지검증 통과·라이다 준비를 뜻하지는 않는다.**

## 실물 재개 의존 순서 — 지금 실행 지시 아님

1. 먼저 개발 측에서 최신 패키지/PC 빌드와 잔여 작업 범위를 확정한다. 로봇이
   꺼진 동안 가능한 회귀·실패 주입을 먼저 끝내고 사용자 대기 시간을 만들지 않는다.
2. 사용자가 복귀해 연결 점검 범위를 승인하면 전원·현재 boot/release·배터리·
   프로세스·기존 센서 발행을 한 번 읽어 확인한다. 전압 추정은 용량 실측이 아니다.
3. 새 제어 패키지는 아직 미배포다. 별도 승인 후 배포하고, 현재 boot/release의
   유효한 qualification을 검사한다. 같은 유효 조건이면 불필요한 반복시험을 하지
   않되, 구 release의 성공을 새 코드에 복사하지 않는다. 필요한 새 시험은 현장
   주시·범위 승인 후 한 번 실행하고 실패를 자동 재시도/완화하지 않는다.
4. 제한된 수동 반복 입력/해제/종료를 확인하면서 실 odom/scan 형식·발행 namespace·
   주기/시간축을 확보한다. 센서 드라이버 시작은 수동 수신 로깅과 별개 작업이다.
5. 실 TF/차체 footprint·정지거리와 독립 watchdog을 포함한 로컬 충돌 방지 및
   자율 worker가 구현·검증되기 전에는 실물 자율 임무 버튼을 풀지 않는다.
6. 준비되면 **임무 전체 범위 1회 승인**으로 목표·시간·속도·영역을 제한하여 실행한다.
   임무 안의 명령마다 승인을 받는 구조가 최종 목표가 아니다. 센서/시간/연결 실패
   때 로봇이 독립적으로 멈추어야 하며, 충돌을 실제로 허용해 감점을 수집하지 않는다.
7. 명령과 실제 관측을 분리 저장하고 같은 조건으로 Twin 비교한다. encoder 회전량을
   바닥 이동 거리나 world pose로 단정하지 않는다.

## 05:55 당시 증거 — 현재 검수는 상단 06:49 기록 참조

- 전체 오프라인 회귀: `artifacts/explicit-close-regression-20260928-r1/manifest.json`
  PASS(core156/Web106/build 포함). 이는 05:20 실행 기록이며 이 결산에서 재실행하지 않았다.
- 실제 App→가짜 worker: `artifacts/explicit-close-browser-20260928-r1/result.json`
  12단계 PASS. 5개 journal/500events, 정상 OPERATOR_STOP와 입력 손실 FAILED 구분.
- 실제 App→broker/production bridge→Isaac:
  `artifacts/overnight-integration-isaac-20260928-r1/result.json` 8체크 PASS.
  B 0/140/280 pose/yaw, 저장 USD 재열기, 변조 거절, 단절/복구, 원본 보존 포함.
- 읽기 전용 증거 대조: `artifacts/overnight-evidence-audit-20260928-r1/result.json`
  현재 기록된 source/build **39파일 일치**, 두 리허설 공통 해시와 dist 전체 목록 일치.
  `scripts/audit_overnight_evidence.py`로 재검사할 수 있다. 이는 저장 증거 정합성이지
  새 runtime 시험/실물 권한이 아니다. 전체 repo hash coverage/증거 서명은 없고,
  전체 회귀 manifest 자체에는 source 해시 바인딩이 없다.
- 검증기 신규 단위테스트 6개 PASS. 최초 sandbox 실행은 임시폴더 권한 오류로
  실행되지 못했고 승인된 로컬 테스트 실행으로 재검사했다. 제품 코드/빌드는 이번
  결산에서 변경하지 않았다.

최신 과거 실물 qualification은 `ddaf23aed5964089a1480bb9b3b151ef`의 QUALIFIED
(release `7a1a4f9a…`, cleanup true)다. 이후 수동 오류5건과 예전 정지 FAIL도 모두
보존한다. 현재 전원 OFF/새 코드 미배포이므로 그 성공을 현재 이동 권한으로 쓰지 않는다.
