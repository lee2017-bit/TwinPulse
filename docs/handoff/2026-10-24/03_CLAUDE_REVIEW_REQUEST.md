# Claude 독립 검토 요청

아래 내용을 ZIP과 함께 전달하세요. 이 요청은 검토이며 구현/접속/구동 승인이 아닙니다.

```text
첨부한 TwinPulse 인계 ZIP을 독립적으로 검토해 주세요. 현재 개발자의 결론을 정당화하지 말고 실제 코드·시험·원문 근거와 대조해 주세요. 사용자와는 한국어로 답하고 제품 UI는 영어라는 결정을 유지해 주세요.

목표: 제출이 임박한 상태에서 불필요한 확장/반복시험을 줄이고, 실제 스캔 환경+로봇 SIM 데모와 별도 감독 실물 자동명령을 성립시키는 가장 짧은 신뢰 가능한 경로를 찾는 것입니다. 현재 로봇은 충전 중이고 이번 검토에서 연결/Prepare/LiDAR/모터를 실행하지 않습니다.

먼저 00_START_HERE.md, 01_HANDOFF.md, 02_TEST_RUNBOOK.md를 읽고 PACKAGE_INFO.json/MANIFEST.json의 포함 범위와 버전을 확인해 주세요. 긴 Baseline/PROJECT_MEMORY는 필요한 부분만 참고하고 과거 READY를 최신 실물 PASS로 읽지 마세요. Git HEAD와 현재 미커밋 소스·설치 source ID는 다릅니다.

핵심 검토:
1. 현 구조에 상태/권한/시각/동기I/O가 불필요하게 겹쳐 같은 종류의 실패가 반복되는지, 정확한 파일/함수와 경로로 설명해 주세요.
2. fleet_control.py/teleop_contract.py의 새 ROBOT_LOCAL_FINITE_SUPERVISED_V1을 기존 teleop_ros.py/C++ guard와 함께 검토해 주세요. 원격 초기 admission, finite 권한, local 계산시작시각, 원source5초supervision, task총deadline, Stop/세대·epoch·context fencing과 최종발행 veto가 일관적인가요? 늦은 watch/Stop/worker부하가 권한을 연장·복원하거나 위험출력을 만들 반례가 있나요?
3. fake clock/device의10개+로봇회귀252개가 실제 위험경계를 어느 정도 다루고 무엇을 놓치는지 확인해 주세요. 테스트가 구현을 그대로 따라가며 결함을 숨기거나, 이전 명령 실패를 다른 여정으로 대체한 곳이 있는지도 봐 주세요.
4. 최신 실제 실패의 원문배터리<=11.1V→generation철회→Arm거절→bootstrap감독미성립을 독립 대조해 주세요. 이 결과로 새 finite 실행의 실물효과를 주장할 수 없다는 판단이 맞나요? 정확히11.1V도 거절하므로 float 버그나 심한방전으로 단정하지 마세요.
5. 수동조종은 추가수정 중단한 사용자 결정을 유지하며, 자동명령 데모에 지금 꼭 필요한 수정만 우선순위화해 주세요. 단순 TTL추가확대·guard제거·unknown 정상화·전면재작성·새iOS/SLAM/VDA5050/Cloud를 기본 결론으로 삼지 마세요. 대안은 장단점·범위·새 검증비용과 함께 제시할 수 있습니다.
6. RoomPlan Import의 시각/triangle collision/floor mask/편집·저장·Undo/SIM 경로와 실제 pose 정합·몸체 제동·사진충실도를 섞어 주장한 곳이 있는지 봐 주세요.

제한: 비밀값 읽기/출력/외부전송, 설치/삭제/시스템변경, Git reset/clean/push·공개, 유료 API/Cloud, 실물 접속/구동, 제품 수정은 하지 마세요. ZIP의 포함 원문·소스만으로 불가능한 검증은 UNKNOWN/추가자료필요로 표시하세요. generic fixture/추정 수치로 개인 원USD나 실제 ROS/HW를 대체해 통과 처리하지 마세요.

응답 형식:
A. 핵심 결론 5줄: 현재 무엇이 되고 무엇이 안 되는지.
B. 확정 결함/유력 가설/설계 trade-off를 분리한 표: 심각도, 파일·함수/라인, 근거, 반례, 최소 수정, 필요한 검증.
C. 지금 필수 수정 / 이후로 미룰 작업 / 유지할 결정.
D. 충전 후 1회 현장세션의 최소 명령·성공/중단 기준.
E. 이 ZIP만으로 판단할 수 없는 자료와 꼭 필요한 추가 요청.

가능하면 먼저 읽기 전용 검토 결과를 보고하고, 승인 전에 코드를 수정하지 마세요. Astra 기존검토는 참고 증거일 뿐 동의해야 할 결론이 아닙니다. 확정 blocker가 없으면 '추가 확정 blocker를 찾지 못함'이라고 쓰고 하드웨어 성공 보장으로 바꾸지 마세요.
```
