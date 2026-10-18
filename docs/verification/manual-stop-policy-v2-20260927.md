# 수동 저속 정지 판정 v2 — 시간·바퀴 회전량·잔류 변화 분리

2026-09-27 KST. 사용자 지적(마찰/정상 감속을 고려하지 않은 자체 기준) 후 재설계 승인. **PC 구현/검사 완료, 로봇 배포·새 실물시험은 NOT_RUN.** 로봇을 켜둔 상태라는 사용자 보고가 있었지만 이번 작업에서 접속하거나 움직이지 않았다.

## 근거와 정정

기존 `500ms 창 안에 고정 2틱 anchor로 200ms 안정`은 제조사 요구가 아닌 자체 시험 조건이었다. 사실상 약300ms 내 안정화를 요구했고, 2틱은 명목상 바퀴 둘레 이동 약0.101mm다. 이를 검증된 보편 안전 기준처럼 설명한 것은 잘못이다. 구 판정/구 FAIL을 삭제하지 않되 새로운 기준과 분리한다.

- [ROBOTIS XL430 공식 설명](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#profile-acceleration108): 속도 제어는 가속도 프로파일과 PI 제어를 사용하며 위치 분해능은 4096counts/rev. 이는 고정 정지 시간/차체 제동거리 보증이 아니다.
- [Burger 모터 공식 구성](https://emanual.robotis.com/docs/en/platform/turtlebot3/appendix_dynamixel/): XL430/12bit 엔코더.
- 저장된 공식 소스 `artifacts/robot-models/turtlebot3-source/turtlebot3_bringup/param/humble/burger.yaml`: radius0.033m, separation0.160m, profile_acceleration0.0. **현재 모터 레지스터를 읽은 것이 아니며**, 0이 물리적 순간정지를 뜻하지 않는다.
- 바닥 마찰/미끄러짐/타이어 변형/하중/제어 응답 영향은 가능한 가설이다. 어느 항목이 이번 원인인지 단정하지 않는다.

## 새 설계 범위 — 제조사 스펙 아님

`stop_policy.py`의 `supervised-stop-2.0`. 명시적으로 직접 보는 사용자, 배터리 전원, 평평한 바닥, 로봇 둘레 최소30cm 빈 공간, 고정 선속도0.03m/s/제자리각속도0.20rad/s, 기존2초 hold/60초 연결/250ms 입력 수명에서만 사용하는 **제한된 수동 commissioning 설계값**이다. 무인/자율주행이나 기능안전 인증 기준이 아니다. UI에 범위·조건 표시.

| 분리 항목 | 구현 조건 | 근거/한계 |
|---|---|---|
| 명령 차단 상태 | 마지막 시험 명령 후700ms 내 guard command_timeout 관측, 이후 latch 유지 | 기존400ms guard+관측 여유는 유지. 상태 관측은 MCU 출력 전기 계측 아님 |
| 감속 대기 | timeout 관측 이후500ms | 더 이상 이 시간 안에 안정 확인 시간까지 소모하지 않음. 제조사 보증 대신 저속 설계 목표 |
| 별도 확인 | 그 뒤300ms 이상 실제 센서 표본 | 500ms+300ms의 고정 창. 표본 누락/지연/토크 OFF로 채운 창은 통과하지 않음 |
| 바퀴 회전량 | 좌우 각각 절대 증가량 누적10mm 이하 | 반대방향으로 돌아와도 거리 취소 불가. 30mm/s에서500ms 선형 감속 가정이면7.5mm; 나머지는 계측/응답 여유. 이 감속 가정 자체는 실물로 아직 검증 안 됨 |
| 잔류 위치 변화 | 마지막 확인창 각 바퀴 max-min /0.3s ≤1mm/s 상당 | 300ms 동안0.3mm 범위, 명목 명령속도의약3.3%. 5틱≈0.253mm는 허용,6틱≈0.304mm는 거절. 끝점 차이만 보지 않아 왕복 흔들림 취소 불가. 실제 순간속도/차체 이동률 아님 |
| 센서 품질 | 각 경계 전후 표본, 최대 간격100ms, source age<200ms, 순서/유한수/정확한 엔코더 형태, 관측 중 torque=true | 외삽/중복/오래된 표본/종료 후 OFF 정지를 주행 정지로 대체하지 않음 |
| 최종 종료 | ROS stop/OFF와 base 종료 후 독립 OFF/속도0 관측 모두 성공 | 정지 성능 평가와 종료 처리 결과는 별개 |

10mm 기준은 이번 3mm 기록에 맞춰 정한 제조사 스펙이 아니다. 무감속30mm/s가800ms 지속하면24mm로 실패하며, 천천히 계속 움직이는 경우 잔류 변화 항목으로 실패한다. guard 관측 최대700ms 동안 명목상21mm+추가 회전량10mm라는 저속 예산을 두었지만 **바닥 미끄러짐·경사·센서 고장·회전체/사람 접근을 보호하는 보증은 아니다**. 30cm 공간과 현장 주시는 별도 필요하다.

## 구현 및 권한 경계

- worker의 고정 시험 명령0.03m/s·600ms는 그대로. 관측만800ms+최대100ms 실제 경계표본 대기까지 확장, 총 시험 루프3초 상한. 기다리는 중 순회마다 travel/기존 총 encoder/asymmetry/torque/신선도/입력 watchdog 검사. 별도 중간 이동 명령 없음.
- 새 평가가 PASS이며 실제 전진 관측/ROS 종료/독립 OFF가 모두 성공해야 새 receipt 발급. `manual-stop-2.0` 및 policy SHA256·boot·전체 release identity 결합. 구 receipt/가짜 장치/PC 저장 재분석으로 해제 불가.
- 새 policy hash: `c64ea5483e79023c2c87bcc201f7e60ddb116b0cfce42134c52eefb6468b1c53`.
- 기존 strict settling 계산은 `stop_diagnostics` 비교값으로만 보존; 새 평가와 UI 명확히 분리. 일반 초기 idle/enable readback/최종 halt 조건은 유지.
- guard 코드, 드라이버·모터 설정, 통신 만료 기준은 변경하지 않았다. 기존 시험 표식도 삭제하지 않는다. 새 설계 버전의 별도 명시 시험을 해야 하며, 반복 실행으로 통과를 찾지 않는다.
- 네 방향의 실제 버튼 해제·통신실패·회전·후진 인수 검사는 새 정지시험 통과 뒤 별도로 남는다. 짧은 전진 시험 하나가 전체 동작/물리 비상정지를 증명하지 않는다.

## 실제 저장 자료 재평가

`scripts/review_manual_stop.py`는 순수 PC 분석이다. `artifacts/stop-policy-v2-saved-review/review.json`:

- 구 실제 기록 `347a645563264e3091165027e79c77e9`의 원본 SHA256 `2aae52a860843534050bd00263030f7fa85d0077eef7c5c4ca0ee1c41867225b` 불변.
- 구 판정90.767942ms FAIL 그대로. command_timeout 관측 지연410.25ms.
- timeout 직후 첫 표본→500ms 이내 마지막 표본의 명목 순회전량 좌3.04mm/우2.68mm. 이것은 새 policy의 전체 누적 회전량과 다른 **부분 관측**이다.
- 새 결과 **INCOMPLETE / OBSERVATION_WINDOW_INCOMPLETE**. 800ms 관측이 없고 종료 도중 torque OFF가 수행됐으므로 부족한 구 기록을 PASS로 재작성하지 않았다. 새 qualification 파일0, 로봇 접속0.

## 오프라인 검증

- policy10, worker lifecycle7, physical integration15 PASS. 410ms까지 감속 후 안정되는 합성자료 PASS, 지속 미세 drift/왕복 회전량/왕복 잔류 변화/한쪽 바퀴/지연 cutoff FAIL, 구 짧은 기록·누락·중복·NaN·bool 엔코더·OFF 혼입 INCOMPLETE, 구 receipt 거절/ROS 종료 실패 시 새 receipt0 검증.
- 전체 회귀 `artifacts/stop-policy-v2-regression-r1/manifest.json` PASS, Web80 및 TypeScript/build PASS. Isaac NOT_RUN.
- `artifacts/stop-policy-v2-browser-r1/result.json`: 실제 격리 Chrome→App/API→로컬 가짜 장치 subprocess→production trial/control 7단계 PASS. 네 방향19출력/해제/연결실패 종료·라이다중단·새 평가표시·모바일 확인. 외부요청0·원본프로젝트불변·실물0.
- 오프라인 준비 bundle `artifacts/robot-preparation/20260927T133241Z-c69197aa/source.tar`; OFFLINE_BUNDLE_READY. 실제 설치/ARM64 검사/현장 정지 성능은 미검증.

## 다음 사용자 실행 순서

**로봇 재부팅 불필요.** 작업 없는 PC 점검 콘솔만 종료 후 `Open-Robot-Console.cmd` 다시 실행(Python 교체), 현장 조건 확인 후1번 패키지 준비→2번 시험 준비→별도 실행 버튼. 이 배포와 실제 짧은 전진은 아직 수행하지 않았다. 새 시험 PASS 때만3번 수동 연결. 실패/관측부족이면 저장된 항목별 원인부터 검토하고 자동 반복하지 않는다. 현재 사용자 콘솔은 임의 종료하지 않았다. 전체 데모 완성/안전 인증을 주장하지 않는다.
