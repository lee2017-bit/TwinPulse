# 추정 Twin에서 로봇 관측 확인하기

> **Historical (mid-October 2026 builds).** This page describes an earlier build. For the current app, including physical TurtleBot3 runs, see [QUICKSTART.md](QUICKSTART.md) and the [README](../README.md).

현재 `robot-observation` 설치판은 SIM과 명시적인 읽기 전용 연결만 지원한다. 모터·주행·배포·연속 survey 시작은 지원하거나 승인하지 않는다. 초기 Twin은 센서 없이 만들 수 있는 수정 가능한 추정 장면이다.

1. 일반 설치 Start로 TwinPulse를 열고 Isaac 연결 표시를 기다린다.
2. `Robots`에서 등록된 로봇을 선택한다. 저장된 이름은 현재 전원·통신 성공을 뜻하지 않는다. 로봇 전원과 같은 네트워크, 현재 주소를 먼저 확인한다.
3. `Check PC preparation`으로 로컬 준비를 확인한 다음 `Check connection (read-only)`을 누른다. PC 준비 통과는 SSH 인증이나 센서 수신 성공이 아니다.
4. 완료 후 실행 ID, 실패 코드 또는 건강·센서 상태, scan snapshot 수, `Observation logs saved locally`를 확인한다. 저장 전에는 로그 조회가 비활성이다.
5. `View connection log` → `Download observation JSON`으로 로그를 저장한다. 재시작 뒤에는 `Saved connection observations`에서 같은 job을 선택할 수 있다. 조회·다운로드는 재접속하지 않는다.

실패해도 job ID·execution ID·시각·안전한 실패 분류를 남긴다. SSH 시간초과는 전원, 현재 IP와 공유 네트워크를 확인해야 한다는 뜻이지 단독으로 전원 꺼짐을 증명하지 않는다. 인증 키를 앱이나 보고서에 붙여 넣지 않는다. 기존 SSH 키와 host-key 검증을 재사용하며 자동 수락·드라이버 시작·설치는 하지 않는다.

## 관측을 추정 Twin 수정에 사용하기

Torque ON은 모터가 활성이라는 뜻이지 현재 이동 증명은 아니다. 바퀴속도·명령·전후 엔코더의 관측과, 정지 자격·주행 허가는 분리한다. 2026-10-17 별도 sensor-only 수집은 실제 raw 수신/종료까지 확인했지만 설치16의 읽기 연결 버튼이 센서를 시작하는 것은 아니다. ROS candidate는 비균일 native 각도 때문에 scan을 거절했으며, 원시 offline preview의 센서축/TF/방 정합은 미검증이다. 이 파일을 임의 균일 LaserScan으로 변환하거나 추측 pose를 넣어 주행 PASS로 취급하지 않는다.

1. 저장 대화를 열고 `Reopen saved scene`을 누른다. 이는 기록 복원이며 Isaac Build가 아니다. `Current Twin and SIM controls`에서 `View current Twin`(부분 초안은 `View draft in Isaac`)으로 장면을 표시하고 준비·idle 상태를 기다린다.
2. `Refine an estimated Twin with obstacle observations`에서 관측 JSON을 선택한다. 로봇 다운로드 파일이나 명시적으로 구분한 모의 관측 파일을 사용할 수 있다. 사진 분석용 첨부와 별도이며 모델에 전송하지 않는다.
3. 마지막 스냅샷의 센서 X/Y/yaw(rad), scan 높이를 입력한다. 이는 사용자가 지정한 추정값이며 보정 완료값이 아니다. 앞선 스냅샷을 같은 pose에 억지로 합치지 않는다.
4. `Obstacle observation`에서 이번에 사용할 관측 ID·시각을 직접 선택한 다음 기존 대상 물체를 선택한다. 이전 선택은 보존되므로 새 파일을 가져와도 자동으로 최신 자료로 바뀌었다고 가정하지 않는다. 자동 표면 후보가 불분명하면 `HELD`로 남긴다. 수동 추정 이동도 선택할 수 있지만 센서로 확인된 물체 식별이라고 표현하지 않는다.
5. `Preview obstacle correction`의 XY 이동을 검토한 뒤 명시적으로 Apply한다. Isaac ACK, disk COMMITTED, 현재 프레임은 별도 확인한다. 결과 미확정이면 다시 Apply하지 말고 저장 결과 조회를 사용한다.
6. `Preview Undo last scene edit` → `Apply reviewed Undo`로 최신 장면 변경을 되돌릴 수 있다. 관측 로그는 삭제하지 않는다.

관측되지 않은 공간과 무효 ray는 unknown이다. 단일 2D scan은 상부 형상·가구 이름·전체 방 정합·로봇 위치·전신 통과 가능성이나 주행 안전을 증명하지 않는다. 자동 대응과 동일 공간 실측 검증, 실제 주행 자격은 별도 단계다.

관측·후보는 `%LOCALAPPDATA%\TwinPulse\runtime\artifacts\obstacle-feedback`에, 로봇 연결 로그는 `runtime\devices\local\artifacts\robot-console`과 `robot-diagnostics`에 저장된다. 실행 파일 폴더와 분리되어 있고 원본 입력 SHA·장면 revision·보정 operation/execution ID를 연결한다. 공유 전 개인 공간·주소·센서 자료를 검토한다.
