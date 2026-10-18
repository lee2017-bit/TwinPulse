# 로봇 기록이 어느 채팅·Twin에서 나왔는지 확인하기

조종 ID를 채팅 ID와 같은 값으로 쓰지는 않는다. 한 채팅에서 여러 로봇·여러 연결·여러 Twin 버전을 사용할 수 있기 때문에 다음 참조를 함께 저장한다.

| 구분 | 기록 값 |
|---|---|
| 채팅/프로젝트 | `project_id`, `conversation_session_id` |
| 장면 | `scene_revision`, `engine_session_id`, `stage_epoch` |
| 로봇 작업 | `operation_id`, `robot_id`, `connection_epoch` |
| 개별 동작/시험 | `request_id`, `command_id`, `trial_id` |
| 센서 자료 | `stream_id`, `frame_sequence` 또는 원 native 이벤트 순서, 원문 SHA |

이는 서로 다른 수명과 목적의 ID다. 인증용 owner/session token은 대화 ID가 아니며 기록용으로 복사하지 않는다.

## 앱에서 보기

1. 원하는 저장 채팅을 열고 Twin 화면을 표시한다. 기록 복원과 현재 Isaac에 장면 표시는 별개다.
2. 로봇을 선택한다. 실물 연결은 기존 PC 준비/명시 Check Connection을 사용하며 이 메뉴를 열었다고 자동 연결하거나 움직이지 않는다.
3. 조종기의 **기록 연결 · 채팅 / Twin 버전**을 펼친다. 채팅 프로젝트, 대화 ID, 연결 시작 Twin, 현재 Twin, 연결 관계, 좌표 정합 상태를 확인한다.
4. **Operation logs**를 누른다. 현재 작업과 마지막 저장 작업을 구분한다. 과거 로그 조회는 연결·운전 권한을 복원하지 않는다.
5. **Download operation JSON**으로 manifest와 이벤트를 보관한다. 실물 원 센서 bytes가 필요하면 별도 **Physical runtime evidence**의 원문 파일도 함께 내려받는다. JSON 요약만으로 모든 원 센서 자료를 확보했다고 생각하지 않는다.

명시적인 과거 작업 기록 읽기는 최대20초까지 기다린다. 실시간 fleet/viewport/state의3초 조회 제한과 센서/입력 최신성 검사는 그대로다. 기록 읽기 실패가 로봇 명령을 재전송하지 않는다.

## 연결 기준과 관측 버전은 다르다

- 실물 `source_twin_context`는 **연결 시작 시의 불변 Twin 참고 기준**이다. 모든 새 v2 command/event는 그 SHA를 참조한다. 개별 사용자 명령에는 요청 시점의 `request_twin_context`도 따로 남는다.
- 실물 LiDAR의 연결 기준은 취득시각 장면 동기화나 world 정합 완료의 증거가 아니다. raw는 native/unaligned다. 사용자가 놓은 로봇 marker도 실측 위치로 승격하지 않는다.
- SIM은 각 실제 engine observation에 당시 수락된 engine/stage/Twin 버전을 남긴다. 마지막 manifest의 장면을 모든 과거 frame에 붙이지 않는다.
- 수정·Undo·엔진 재시작·프로젝트 전환으로 과거 기록을 다시 분류하지 않는다. Undo로 같은 형상을 복원해도 새 revision이 만들어질 수 있다.
- 실물 수집의 참고 Twin을 바꾸고 싶으면 명시 Disconnect 후 Check Connection으로 새 작업을 시작한다. 자동 센서 재시작이나 추가 운전 제한을 만들지는 않는다.

## 표시의 의미

`NO_CURRENT_TWIN`은 연결할 때 적용된 Twin이 없었다는 뜻이다. `LEGACY_UNKNOWN`은 예전 기록에 연결 정보가 없다는 뜻이며 현재 장면으로 채우지 않는다. `CURRENT_TWIN_UNAVAILABLE`, `DIFFERENT_TWIN_REVISION`, `SAME_REVISION_DIFFERENT_ENGINE`은 원본을 보존한 채 현재와의 차이를 알린다. 같은 Twin 참조라는 표시도 실제 공간 좌표 정합 성공을 뜻하지 않는다.

이번 설치의 실제 SIM·저장 재열기 인수와 실물 OFF 미검증 항목은 [단일 로컬 보고서](../outputs/robot-twin-lineage-20261018/report.html)를 따른다. 이 문서는 실물 주행 성공·사진 품질·산업 안전 인증을 주장하지 않는다.
