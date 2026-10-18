# TwinPulse 로봇 통합 재검토와 실행 계획

검토일:2026-09-27. 현재 코드·실물 기록을 근거로 한 재계획.
이번 범위: 저장된 정지 시험 분석, 통합 읽기 전용 점검1차 구현·실행,
프로젝트 통합 순서 확정. 실물 추가 주행은 실행하지 않았다.

후속 D1(동일 날짜): [부분 구현·검증](../verification/robot-package-d1-20260927.md).
소스 통합/준비 명령/manifest/managed READ lease 구현,26+6검사 PASS.
사용자가 지속음 때문에 로봇 전원을 꺼 실제 배포 전 연결 실패. Pi 배포와
재부팅 확인 및 base lifecycle 소유권은 남아 있으므로 D1 전체 PARTIAL.

이후 사용자 충전 중 승인으로 [D1 lifecycle와 D2 dry-run 선행 준비](../verification/robot-charging-offline-prep-20260927.md)를 추가.
base 소유권은 코드/offline검증 완료, 실제 Pi gate미실행. D2는 승인만료/binding
계약만 준비했고 physical adapter미연결. 로봇접속/구동 없이 배포묶음을 저장했다.

## 1. 판단

최종 목표는 유지한다: 같은 실제 장소의 사진→개략3D→TurtleBot 스캔으로
보정→동일 조건 경로 비교→승인된 실물 실행 결과를 TwinPulse에서 확인.
로봇의 짧은 이동 시험은 이 과정의 기반 검증이며 최종 데모 완성을 뜻하지 않는다.

현재 가장 큰 문제는 점검 개수 자체보다 **작업 단위와 실행 도구의 부재**다.
점검·준비·구동·분석이 한 대화에서 섞이고, 도구 경로/인자/버전을 매번
다시 찾아 여러 SSH 호출로 실행했다. 설치 때 한 번 확인할 사실과 방금
확인해야 할 상태를 구분하지 않아 사용자가 준비 시간 내내 기다리게 됐다.
그 책임을 사용자에게 명령 입력이나 지속적인 화면 감시로 넘기면 안 된다.

따라서 당장 개별 주행을 늘리기보다, 기존 코드를 재사용해
`Check → Prepare → Ready → Run once → Stopped → Report`를 고정된 실행
단위로 만든다. 모든 준비는 Ready 이전에 끝낸다. 준비/진단 성공이
구동 승인을 자동 생성하지 않으며, 구동 후에는 명확한 결과를 즉시 알린다.

## 2. 현재 사실과 남은 구간

| 구간 | 직접 확인된 사실 | 남은 것 |
|---|---|---|
| OS/연결 | Ubuntu22.04.5arm64, Humble, SSH, OpenCR/CP2102 | 부팅·버전별 재현 가능한 배포 묶음 |
| 기본 구동 | 공식 Burger FW5, 짧은 전진/정지, 사용자 육안 확인 | 회전/후진/연속 주행 qualification |
| 명령 만료 | 별도 guarded base에서 실제 timeout421ms 수신 | 실제 감속·정지거리 기준, 프로세스 중단/통신 장애 실물 시험 |
| 정지 후 상태 | 독립 READ에서 속도0/토크0/명령0 | 모든 고장 조합의 최종 정지 증명 |
| 배터리 | 전압 측정·제조사 공개식에 따른 추정 표시 | 측정된 용량%/사용가능 시간, 셀별 상태 |
| LiDAR | COIN-D4 응답/패킷 검사 기록 | ROS scan 품질·TF, 시작/물리 회전 정지, 필요 수정본 통합 |
| TwinPulse | 사진→3D 및 제한된 Isaac 시험, H2/H3 일부 | 실제 로봇 profile·관측/scan·mission·UI 연결 |
| 경로 비교 | 제품 방향/계약 계획 | 일반 navigation, 공정 baseline/candidate 비교, 실물 재현 |

기존 기본 ROS launch는 여전히 guarded 경로가 아니다. 별도 guarded 실행
파일을 만들었다는 사실만으로 기본 제품 제어 경로가 보완됐다고 할 수 없다.
임시 디렉터리의 시험기·명령행·하드코딩된1회표식을 제품의 최종 구조로
유지하지 않는다. 전체 H6/B3가 완료됐다는 주장은 하지 않는다.

## 3. 이번 정지 판정의 해석

소스: `guard_stop_probe/probe.cpp`, `CommandGuard`/`RosGuard`,
[실제 시험 기록](../verification/robot-policy20-motion-20260927.md).
오프라인 재계산 명령:

```powershell
.\.venv\Scripts\python.exe scripts/analyze_robot_stop.py docs/verification/robot-policy20-motion-20260927.md
```

- 입력 마지막 기록t562ms, timeout 수신은421ms 후로 재구성t983ms.
- 시험은 timeout 후500ms 이내에 고정2틱 범위에서200ms 안정할 것을 요구.
- 발췌된 센서 기록에 같은 규칙을 적용하면 마지막 기준점 재설정t1361ms,
  관찰 끝을t1483ms로 재구성할 때 안정 시간122ms다. 따라서 FAIL은 코드와 일치한다.
- Burger 명목 반지름33mm/4096틱으로1틱≈0.0506mm,2틱≈0.101mm.
- 마지막 timeout 이전 샘플부터 관찰 끝까지 명목 바퀴 변화는 약3.59/3.70mm.
  이는 timeout 직후의 정확한 바닥 제동거리가 아니다. 샘플 간 지연·slip·
  발췌 로그 한계를 포함한다. 정확한 정지 명령 write 시각도 별도 계측이 필요하다.
- 사용자는 전진 후 정지를 봤고, cleanup 후 독립 READ 속도/토크/명령0도 확인됐다.

**결론:** 자동 만료 신호는 실제로 관찰됐다. 시험의 안정 시간 조건은
실패했다. 이를 곧바로 제어기 고장으로 해석하거나 단순 센서 잡음이라고
면제할 근거는 부족하다. 이전 실패를 PASS로 고치지 않는다.

다음 측정 설계는①입력 종료②guard의0 write/응답③wheel 속도 감소
④정해진 거리·속도 범위의 정지⑤미세 encoder 안정⑥토크 해제를 각각
기록한다. 불필요한 긴 지연/진동/크리프가 있는지 판별한 뒤 원인에 맞춰
제어·측정법을 수정한다. 허용 정지 시간/거리는 속도·실제 공간 여유와
측정 오차를 근거로 시험 전에 정한다. 이번 자료 한 건에 맞춘 threshold
완화로 성공을 만들지 않는다. 영상/바닥 표식 등 독립 측정도 함께 사용한다.

## 4. 사전 점검을 언제 할 것인가

| 실행 시점 | 자동 점검 내용 | 무효화 조건 / 사용자 대기 |
|---|---|---|
| 설치/프로그램 변경 | OS/패키지, firmware/profile, 실행 파일 hash, build/test | 변경한 항목만 재검사. 사용자가 지켜볼 필요 없음 |
| 부팅/연결 세션 시작 | boot ID, 연결, USB, 자원, 배터리, 프로세스/포트 소유, 정지 상태 | 재부팅/연결 대상 변경/세션 종료 시 만료. 사용자가 지켜볼 필요 없음 |
| 실행 준비 | 검증된 고정 launch, 센서/guard 준비, 명령 source, 실행 한도와 로그 위치 | executable/config/profile/boot/session 변경·통신 손실 시 만료 |
| 실행 직전 | 최신 배터리/상태·정지/guard·유일 명령 소유자 + 현장 관찰 확인 | 오래된 상태는 재사용하지 않음. 소프트웨어 확인은 수초 목표, 실측 필요 |
| 실행 중/종료 | 로봇 내부 watchdog·명령/센서 나이·경계, 종료 후0/토크해제/로그 | 인간이 수치나 터미널을 계속 감시하도록 설계하지 않음 |

읽기 전용 전체 점검은“고장을 전부 자동 진단한다”는 뜻이 아니다.
점검 가능한 모든 계층을 보고서에 열거하고, 센서 미실행/장치 사용중/
미지원/실패/확인된 상태를 구분한다. 프로그램 종료 상태에서 scan 없음은
고장 확정이 아니다. 카메라 없는 원격 점검이 주변 사람·전선이나 실제
LiDAR 회전 정지를 확인했다고 주장할 수 없다.

## 5. 이번에 구현한 통합 진단 V1

기존 `check_robot_connection.py`/`turtlebot_probe.py`를 유지·확장하고
`robot_health.py`를 추가했다. 기존 명령에서 profile을 선택하면 단일 SSH
요청으로 조사하고 JSON/HTML 보고서를 저장한다.

```powershell
.\.venv\Scripts\python.exe scripts/check_robot_connection.py --profile twinpulse-burger --ros-distro humble --identity-file C:\Users\jaewo\.ssh\twinpulse-burger\id_ed25519_automation --batch --board-snapshot
```

현재 프로필의 주소/계정은 편의 기본값이며 DHCP 변경 시 `--host`로 지정한다.
키는 SSH가 사용하며 내용은 읽어 출력하지 않는다. 다른 로봇에는 generic
프로필을 사용한다. board backend는 검토한 PING/READ 전용 실행 파일의 hash를
검사하고 포트 사용 중에는 실행하지 않는다. ROS 드라이버는 기동하지 않는다.

수집: OS/ROS/domain/USB, boot ID/uptime/CPU온도/디스크, 실행 중인 base와
guard hash, 가능한 경우 voltage/추정%/토크/속도/encoder/0명령,
scan/odom 수신·시간·frame·속도, cmd_vel/guarded_cmd_vel publisher,
guard status, TF publisher 수. TF 연결/정지 qualification/navigation 등
미완료 항목은 보고서에 남는다. root topic이 있어도 여러 동일형 센서가
보이면 임의로 하나를 선택하지 않는다.

검증: 기존9+health10+저장된 정지 분석4=23개 검사 PASS.
실물 읽기 전용 통합 실행1회:00:24:32KST,11.21V/추정39.4%,
토크false·속도0·명령0·encoder1800/5530, CPU38.946°C, 여유9.13GiB,
USB2개, base/probe없음, guard artifact hash일치. ROS sensor미수신은
드라이버 미실행 상태와 함께 표시. 보고서 생성까지약12초(기록 timestamp 기준).

**V1 제한:** backend가 `/tmp`의 이전 검토 실행 파일에 의존하므로 재부팅
후 없어질 수 있다. 이때 UNKNOWN을 반환하며 임의로 새 helper를 빌드하지
않는다. fuser 조회와 helper open 사이의 경쟁을 완전히 막는 단일 소유권
구조는 아직 없다. 진행 중 제어기에서의 ROS battery/전체 TF 분석과 제품
UI/API 연결도 다음 단계다. 이것을 production health agent완료로 표기하지 않는다.

## 6. 확정할 구현 순서와 완료 조건

| 순서 | 작업 / 프로젝트 반영 위치 | 완료 증거 |
|---|---|---|
| D0 이번 | 사실/실패 원인 한계 정리, 통합 읽기 점검V1, 오래된 계획 포인터 정리 |23검사·실물보고서·이 문서. 완료 |
| D1 바로 다음 | canonical robot package에 profile/manifest/진단 backend/실행 recipe·시험기 이관. stable deployment, boot/session ID, 프로세스·serial단일 소유자 | 재부팅 뒤 한 명령 점검, busy/미설치/변경 hash/중단 보고, 로그자동저장. 모터를 켜지 않는 검증 우선 |
| D2 | 고정 유한 trial runner와 정지 계측. Prepare/Ready/Run/Stop/Report, manifest·run ID·승인범위·expiry를 연결 | 준비완료 후 실행 지연 측정, fake/replay 실패 경로, 별도 현장 시험에서 시간/거리/cleanup 증거 |
| D3 | COIN-D4 driver/ROS scan·IMU/odom/TF·센서시간 qualification | 제자리 scan부터 시작/정지·rate/range/frame·기록파일 확인. 회전 센서는 현장 관찰 필요 |
| D4 | ApplicationService RobotSession/HealthReport/Observation API와 영어 Robot Status UI | CLI와 UI가 같은 계약 사용. 상태/Ready/차단이유/Cancel/결과 표시, stale session시험 |
| D5 | TurtleBot profile/H3c 및 scan→Twin/H4 | 실제 장치 profile, 기록 scan 정합/undo/좌표/단위 검증; 실제 공간과 같은 사진 |
| D6 | H5 navigation·동일 조건 비교→H6제한mission→H7증거 | 같은 map/profile/start/goal/제한의 baseline/candidate; 실제 성공·실패·시간/거리·개입 기록 |

D번호는 이번 복구·통합 작업 순서이며 H/B milestone을 대체하거나 완료로
재표기하는 번호가 아니다. D1/D2는 H6의 기반을 먼저 정리하는 범위다.
H4의 기록·합성 스캔 작업은 D3의 물리 준비와 독립적으로 진척 가능하다.
현재 단순 주행 시험을 반복하며 H4/H5를 무기한 미루지 않는다.

코드의 책임은 분리한다:
`robot package(C++ 상태/제어 소유) → RobotSession worker → ApplicationService
→ typed API → React Robot Status`, Isaac은 관측을 표현하고 승인된 장면을
검증한다. LLM은 설명·목표 제안을 맡으며 상태 보고·제어 루프·정지 판단은
고정 코드가 소유한다. 기존 `/tmp`·개인 cwd 파일이 유일한 소스가 되지 않게 한다.

## 7. 배터리와 운영 편의

사용자 충전 기준은 전압으로 추정한20%로 유지. 독립 보드 보호가 먼저
작동할 수 있다는 제한을 같은 화면에서 짧게 표시한다. 표시에는 측정
시각·전압·추정임을 포함하고, 데이터가 오래되면 마지막 값을 현재 값처럼
보여주지 않는다. 현재 식의20%를 실제 잔여에너지20%로 보장하지 않는다.
전원이 켜진 채 준비하면 Pi도 배터리를 소비한다. 긴 준비를 위해 운영자에게
계속 주시를 요구하지 않고 Prepare완료 후 현장 실행을 요청한다.

장기적으로 충전 완료→정해진 부하 운전의 기록으로 사용시간 추정을
보완할 수 있지만, 방전을 강제하거나 경고/보호를 해제해서 측정하지 않는다.

## 8. 다음 작업의 구체적 시작점

**D1부터:** 현재 검토된 helper/probe/guard를 canonical package의 소스·
manifest·배포물로 묶고 한 번의 준비 명령을 만든다. clean 설치/부팅과
실행 소유권·로그 생성까지 무구동으로 검증한 후 D2의 계측을 준비한다.
그다음 실제 시험이 필요해졌을 때 실행 범위·예상시간이 정해진 상태로
현장 확인을 받는다. 이미 끝난 동일 소스의615/1314검사를 매번 반복하지
않고 변경 영향과 manifest무효화에 따라 필요한 검사만 실행한다.

기록: [현재 상태](TWINPULSE_ROBOT_CURRENT_STATE.md),
[검증 범위](../verification/robot-health-review-20260927.md),
[기존 최종 데모계획](TWINPULSE_HACKATHON_DEMO_MASTER_PLAN_2026-09-25.md).
