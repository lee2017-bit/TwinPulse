# 반복 오류·원자료 색인 — 2026-10-25

현재 확정 결과와 역사적 실패를 분리한다. **최신 v655는 실제 이동 자료 부분 확보/자율 순회·복귀 FAILED**다. 아래 항목의 수정/한정 성공은 전체 실물 방 순회의 성공이 아니다. 상세 원 ID·시간·기준과 모든 중간 실패는 PROJECT_MEMORY/Baseline 버전과 각 보고서에 보존한다.

| 계층 / 이력 | 확인한 실패 / 원인 범위 | 조치·현 상태 | 원근거 |
|---|---|---|---|
| 최초 연결·Stop 전달 / v614 | 미발행 -inf 진단 JSON, blocking queue 중 Stop 자기 명령 거절 경합 | 두 경계 보완, 이후 실제 연결 가능. 과거 실패 유지 | [실물 재시험](../../outputs/robot-powered-roomplan-20261023-01/report.html) |
| 수동 입력 / v615–620 | 350ms 입력 유효기간 소모, 갱신 위상, PC 배터리 표시 I/O/registry 경합. 개별 관측을 전체 지연의 단독 원인으로 확정하지 않음 | 표시와 제어 경로 분리·원입력 나이 중복 교정·UI 갱신 보강. 사용자 승인 custom 입력1000/output1200/odom500. 수동 연속 완주 아님/수동 추가개발 동결 | [기록/확대 정책](../../outputs/robot-powered-roomplan-20261023-01/report.html) |
| LiDAR 방향 공백 / v620–624 | 우회전 중5.375° 공백으로 조기 중단, 시간만료와 별개 | 사용자 승인10° 정책, 원5° 실패 보존. 새로운 raw 품질 실패를 자동 PASS로 만들지 않음 | [원결과](../../outputs/robot-powered-roomplan-20261023-01/expanded-timing-status.json) |
| 실물 표시 / v621 이후 | display_pose 없음/몸체 표시 경로 분리, rawscan은 sensor-local. 단순 센서 미수신 문제가 아님 | 현재 registration/명시 anchor와 모델 표시 연결. 미정합 데이터를 USD에 강제 투영하지 않음 | [종합 검토](TWINPULSE_POWERED_FAILURE_VISUAL_REVIEW_2026-10-24.md) |
| 전압 / v631 | 11.1V 기존 경계 아래로 pause/Arm 불가 | 충전 후 별도 재시험, 보호 해제 안 함 | [당시 결과](../../outputs/robot-auto-demo-20261024-01/report.html) |
| 단일 자동명령 / v633 | 준비/idle 원거절 존재, wheel 이동과 독립 LiDAR 차체 추정 불일치 | 전후10cm·좌우90°·360° finite5개 Stop까지 한정 완료. 차체/제동/정합 UNQUALIFIED 유지 | [전 세션 결과](../../outputs/robot-auto-charged-20261024-01/report-complete.html) |
| USD·센서 정합 / v634 이후 | RoomPlan 누락 소물체, 미기록 단위, 전체링/높이별 구조 POOR_FIT, wheel-seeded 추정 독립성 문제 | 원USD 보존·구조 정합/센서 잔차 XY/사진 종류의 명시 결합. 자동 metric 사진 배치/실물세계 정합 미인수 | [분석](TWINPULSE_ROOMPLAN_LIDAR_DEMO_REVIEW_2026-10-24.md) |
| 공통 자연어 task / v642–646 | capability 누락/발명 waypoint, return 경로접경, SIM/공통 envelope 불일치 | strict schema+Run 재검증·같은 충돌정책/귀환 예산·관측 재계획. 이전 FAIL 및 scoped SIM PARTIAL 유지 | [공통 task](TWINPULSE_COMMON_ROBOT_TASKS_2026-10-25.md) |
| 저장·복구·실행 환경 / v648–652 | deepcopy import누락, history prefix 반복, ENOSPC, heartbeat UNKNOWN 뒤 late ACK 큐정체, 새SIM geometry 저장674.5ms로 .5s 자기만료 | 각각 좁은 보완/새 actual UI 인수. source13 ABORT와 원UNKNOWN/실패를 성공으로 변경 안 함 | [환경 전체 연결](TWINPULSE_ENVIRONMENT_TASK_LOOP_2026-10-25.md) |
| 현재 physical common task / v653–654 | 첫 child 전 `Physical task pose or observed map changed before admission.` /0segment. 원실패 guard 세부분기 미기록 | 500ms pinned ring이 반복검사 중 소모되는 경로가 우선 후보/정확 원인 미확정. typed 최초거절/전송 전 새ring1회·snapshot시작시각으로원age보존/Stop후진단·원예외분리를새설치에반영.584무구동PASS/새실물 재시험 없음 | [현재 원FAIL](../../outputs/robot-environment-field-20261025-01/result01.json) · [한정PC보완gate](../../outputs/robot-data-priority-20261025-01/acceptance01.json) |
| 데이터 우선 세션 / 2026-10-25 | 모터 UNPREPARED에서 Stop readback 미확인. 초기 offline verifier가 disconnected operation_id로 조회해 StopIteration | 이동0/Prepare·Arm0, OFF/Disconnect·정상 Exit. 검수기는 원robot_id로 수정, 오류 별도 보존. 신규 wheel pose 없음 | [원자료16,311건](../../outputs/robot-data-priority-20261025-01/data-result01.json) |

## v655 추가 현장 실패

| 계층 | 확인 결과 | 현재 상태 / 원근거 |
|---|---|---|
| 자율 survey 계획 | TASK_LOCAL_FRESH_RING_REQUIRED_BEFORE_MOTION /0child. 계획용 `_geometry→Map.scene` 원500ms gate가 child 전 새ring 취득보다 앞선다. 정확 PC 단계 소요는 미기록 | 계획 전용 누적지도와 strict child freshness 분리가 다음 최소 보완/미구현. [원FAIL](../../outputs/robot-moving-survey-20261025-01/failed-common-task01.json) |
| 운영자 보조 복귀 | 4finite 완료 후 병진 .01817m에서 FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP. 1.766mm<2mm 추적 window에 PUBLISHED 전501ms 표본 포함/후685ms. reset 잔존 진단은 동일구간 비교 아님 | 입력 만료가 이번 거절 근거는 아님. 물리 정체·슬립 원인 미확정/귀환false/정지 확인. [Astra 원행·시각 결속](../../outputs/robot-moving-survey-20261025-01/astra-body-window-review01.json) |
| 자연어 라우팅 | in-place의 place가 편집으로 분류되어 chat400 두 건·Robot command409 한 건. 같은 의미의 짧은 문장만 task 경로 진입 | 미해결/원응답 유지. [앱 요청·응답](../../outputs/robot-moving-survey-20261025-01/ui-actions01.json) |
| 저장공간 / 검수 도구 | Isaac 실행 중 C여유 약250MB. NTFS 압축02 영수증의 scope 문자열은 staging/work로 잘못 남음 | 과거 생성 build 복사본만 압축/원byte 동일·삭제0, 정확 경로와 별도 정정 보존. [결과·정정 영수증](../../outputs/robot-moving-survey-20261025-01/report.html) |

원166471행/383520936bytes·3807scan/5359pose heartbeat는 준비·정지·이동을 포함한다. 전SHA/행수/COMPLETE 확인은 원자료 보존 인수이지 자율 방순회/복귀·차체/제동·정합 PASS가 아니다. 최종 Stop/OFF/Disconnect·정상 종료, 제품변경/새설치0·추가 이동0.

## 보존 원칙

- 원 명령·packet·source clock·Stop/readback·거절 분기와 후행 cleanup을 별도 저장한다.
- 실패 뒤의 fresh snapshot 또는 정상 종료를 실패 당시 guard의 대체 증거로 쓰지 않는다.
- 원107,157건과 추가 정지16,311건은 서로 다른 operation이다. 새 정지 데이터를 이동/전체방 coverage로 부풀리지 않는다.
- 원본 사진/USD·프로젝트·native/odom 로그는 삭제하거나 외부 전송하지 않는다. 분석물은 원경로와 SHA를 참조한다.
- 최초 문제를 고쳤다는 주장은 같은 조건의 검증 범위를 명시한다. 오프라인 fixture 성공은 실제 installed UI/하드웨어 결과가 아니다.
