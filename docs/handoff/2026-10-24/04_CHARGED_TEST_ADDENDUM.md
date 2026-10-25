# 충전 후 자동 명령 실물 시험 추가 결과

이 파일은 앞선 Claude 검토 ZIP을 만든 뒤 실행한 2026-10-24 후속 기록입니다. 기존 ZIP/원실패를 덮어쓰지 않습니다. 해당 ZIP 안의 최신 설치 finite 실물 NOT_RUN은 그 시점의 사실이며, 지금은 아래 **한정 제어 성공** 근거가 추가됐습니다.

제품/설치 변경 없이 `20261024T053958Z-9d2b297a8246`에서 새 현장승인 후 App operation `db929f4ad15e418e88ddd71a85ea55f6`를 실행했습니다. Connect11.62V→명시Prepare1200readback→LiDAR/정지78frame(불완전3 INCONCLUSIVE)→Arm수락→bootstrap durable Stop PASS→ordinary finite자동명령5건입니다.

| 명령 | 실제 발행 | admission부터 Stop까지 | 정착 후 encoder 기준 |
| --- | --- | --- | --- |
| 전진10cm |33 |4.843s |+10.593cm |
| 후진10cm |34 |4.409s |−10.709cm |
| 좌90도 |76 |9.321s |96.601도 |
| 우90도 |75 |8.989s |−94.154도 |
| 단일좌360도 |286 |33.331s |368.893도 |

다섯 건 모두 원문 `COMPLETED`, `TASK_WHEEL_ODOM_TARGET_REACHED`, `ROBOT_LOCAL_FINITE_SUPERVISED_V1`, Stop readback=true입니다. 정확 명령 window의 입력 만료/기타 실패 pause는0입니다. 위 정착 값은 마지막 RUNNING progress나 실제 몸체의 정밀 이동량과 다릅니다.

Astra 독립 원문 대조도 한정 제어성공을 확인했습니다. 단 전체 세션은 무오류가 아닙니다. 준비 `PREPARATION_PRESENCE_EXPIRED` fault12건, `OPERATOR_PRESENCE_EXPIRED` pause2건, watch `INPUT_CHALLENGE` 거절18건/generation 거절79건이 있습니다. 다섯 작업창 내 generation 거절10건은 첫 실제 발행 전 watch이며 진행 중 실패 pause와 구분합니다. 원문·최초 파생result01을 보존하고 `result02.json`/`report-complete.html`에서 세션 거절까지 명시했습니다.

독립 LiDAR 보조분석은 전진 약3mm/후진26mm로 wheel106/107mm와 차이가 있고, 회전은 scan 간격에 의해 거절됐습니다. duration-matched stationary baseline도 부족하여 **5건 모두 몸체 UNQUALIFIED_UNKNOWN**을 유지합니다. 자동 제어 수명/목표·정지 경로를 통과한 것과 실제 몸체 정확도·제동·RoomPlan 세계정합은 구분해야 합니다. 이번에는 사용자에게 반복 이동관찰 질문을 하지 않았습니다.

최종 Stop torqueOFF·LiDAROFF·Disconnect/cleanuptrue·recordingCOMPLETE, 원48,376행/30segments/124,077,855B SHA/크기/행수exact, robot journal45,441/native19,819 saved/queue0/writer 종료와 정상 App/root 종료·runtime/Kit 보존을 확인했습니다. 사용자에게 전원을 꺼도 된다고 안내했고 실제OFF는 관측하지 않았습니다. 수동/실물가구목표·제품수정·외부모델·업로드는0입니다.

원본·정확 수치와 355.840초 실제 앱 시험 녹화는 `outputs/robot-auto-charged-20261024-01/report-complete.html`, `result02.json`, `independent-motion01.json`에 있습니다. 이 영상은 실물 카메라/완성 제출 데모가 아닙니다.
