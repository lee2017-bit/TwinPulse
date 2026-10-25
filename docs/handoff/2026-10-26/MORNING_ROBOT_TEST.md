# 아침 로봇 테스트 체크리스트 — 2026-10-26

밤사이 Fable이 코드 리뷰·수정·SIM/단위 테스트·개발 채널 빌드까지 끝냈습니다. 실물 로봇은 켜지도 움직이지도 않았습니다. 이 문서 하나로 바로 시작할 수 있게 적었습니다.

## 0. 설치된 빌드

| 항목 | 값 |
| --- | --- |
| 설치된 빌드 ID | `20261025T223555Z-ee9267cf8927` (channel **development**, physical_robot=true; 06:50 세션의 결함 4개 수정 포함) |
| 소스 | 브랜치 `claude/project-thread-l7md32`, commit `d24c506` (+ 사용자 미커밋 문서 2개) |
| 이전 빌드(롤백용, 보존) | `20261025T182006Z-e390aa4478c3`(밤 빌드, 06:50 세션에 사용), `20261025T162952Z-62f7a3f1e698`, `20261025T120155Z-cb02064b5674` |
| 설치 로그 | `outputs/path-b-20261026/install21.log`, 빌드 로그 `outputs/path-b-20261026/build21.log` (이전: install20/build20); 설치본 SIM 여정 PASS 증거 `outputs/path-b-20261026/sim16/` (3 stops, 12 moves, 복귀 오차 0.4 mm) |

최종 설치본 검증: Test 모드 기동 → Isaac 연결 30 s → 설치 UI 스모크 6/6 PASS(`outputs/path-b-20261026/smoke20b/`) → Exit 정상 종료. 이 검사가 프로젝트 목록에 빈 "New chat" 항목 하나를 남겼을 수 있습니다(무시 가능). 중간 빌드 `20261025T172753Z-6ad052bdf3f6`은 정리했고 이전 두 빌드는 보존.

시작: 바탕화면/저장소의 `Start-TwinPulse.cmd` (설치본 실행). 화면 녹화·CDP 검증이 필요하면 `Start-TwinPulse-Test.cmd`.
롤백이 필요하면 `%LOCALAPPDATA%\TwinPulse\installed\active-release.json`의 `release_id`를 이전 빌드로 바꾸지 말고, 이전 빌드 폴더의 `TwinPulse.exe --install`을 다시 실행하세요(같은 epoch).

## 1. 켜기 전 (5분)

1. **디스크**: 탐색기에서 C: 여유 **10 GB 이상** 확인 (어젯밤 18.2 GB). 10 GB 아래면 녹화 전에 `outputs/path-b-20261025/build18` 삭제(882 MB, 설치 완료된 중간 빌드) 등으로 확보. 설치본·raw 기록·프로젝트는 건드리지 않음.
2. **배터리**: TurtleBot3 **12.3 V 이상** 충전 확인(11.1 V 아래면 Arm 불가). PC 전원 연결.
3. **바닥 정리**: 경로 위 옷·전선·선풍기 밑판 등 LiDAR가 못 보는 낮은 물체 제거. 데모용 상자 1개 준비(30 cm 내외, 바닥에 바로 놓는 단색 상자).
4. **시작 위치 표시**: 어젯밤과 같은 테이프 마크. 선언 좌표 **x 0.681 / y 0.206 / yaw 0.489 rad(≈28°)** (소파 가죽까지 1.00 m, 창문 벽까지 3.52 m).
5. 로봇 전원 → PC와 연결 확인(`Check-Robot-Connection.cmd`).

## 2. 앱에서 (순서대로)

1. `Start-TwinPulse.cmd` → 왼쪽 Recent chats에서 어젯밤 프로젝트(`Menu action: Import space for SIM · Project-2610222326.usd`, 106 messages, 프로젝트 ID `chat_mvmbjpcn_d8ef3086`) 열기. **앱을 새로 켠 뒤에는 Isaac에 Twin이 자동으로 다시 세워지지 않습니다**: 채팅 안의 **Reopen saved scene** 버튼(없으면 생략) → 상단 **Import space → Check saved import → Show Twin**(패널 안의 버튼; "Import status: failed · Reopen the saved space"가 보이면 Reopen saved scene을 먼저) → Twin 패널에 3D 프레임이 뜨고 Robots 카드의 내비게이션 맵이 `AVAILABLE`이 될 때까지 기다린 뒤 **Close import space**. (어젯밤 SIM 검증도 이 순서로 통과.)
2. Twin 패널 **Robots**에서 실물 로봇 선택 → **Connect** → LiDAR on → 로봇 카드 **Details → Physical setup**에서 (a) "I am present…" 체크 후 **Prepare**, (b) "I am supervising…" 체크 후 **Arm supervised field session**, (c) "I reviewed the selected trial…" 체크 후 **Run Bootstrap stop**(이동 0). 카드의 차단 사유가 비고 drive 가능이어야 합니다. (06:50 세션: 이 두 단계 없이 Run route를 누르면 첫 명령이 ACK되지 않음 → 이제 경로 요청 자체가 사유를 알려 주며 거절합니다.)
3. 로봇 카드 **Set position**으로 선언 좌표 입력(위 값). 라벨은 "operator-declared"로 남습니다.
4. 채팅에 **`Survey the room and come back`** 입력 → 경로 카드(미니맵, "4 stops, 6.42 m, about N finite moves") 확인. **아직 Run route를 누르지 마세요.**
5. **상자 놓기** — 두 가지 중 하나:
   - **A(권장, 안전)**: 1구간(시작→정지 1, 로봇 진행 방향으로 2.13 m 직진) **옆** 30–40 cm, 시작점에서 약 1.0–1.3 m 앞. 로봇은 그대로 지나가고, 각 정지점의 LiDAR가 상자를 "Twin에 없는 물체"로 잡습니다.
   - **B(코디네이터 요청 시나리오, 재계획 라이브)**: 1구간 **위**, 시작점에서 약 1.1 m 앞(좌표 약 x 1.65 / y 0.73). 로봇이 10 cm 근접 정지 → 25 cm 후진 → 경로 자동 재계획(채팅에 "Proximity stop … re-planning" 메시지, Isaac에 빨간 keepout 링). 실물에서는 어젯밤 처음 코드로 검증된 경로이므로 **첫 실행은 A**로, 여유가 있으면 B.
   - 둘 다 **경로 카드가 뜬 뒤**에 놓아야 합니다(카드 전에 놓으면 시작 LiDAR가 이미 keepout으로 넣어 "달라지는 경로"가 안 보임).
6. **Run route** 클릭. 이제 보이는 것:
   - 채팅: `Route started: 4 stops, about N planned moves…` → 정지마다 `Stop k of 4 reached · n moves so far · LiDAR: m returns not in the Twin` → `Back at the start…` → 완료 메시지.
   - Twin 패널 아래 **Route 카드**: `Route running · stop k of 4`, 이동 수, 현재 명령, 바닥 지도(도달 정지=녹색, 건너뜀=회색, 궤적, 현재 위치), **Stop route** 버튼.
   - Isaac: 경로·번호·궤적·정지별 LiDAR 점·후보 원.
7. 완료 카드 `LiDAR at the stops saw N objects the Twin does not have…` → **Add to Twin**(한 번에 1개, 가장 강한 후보부터). Twin 갱신(Undo 가능) 확인. 상자가 아닌 후보(로봇 자신, 벽 근처 잡음)는 **Skip**.
8. 로봇을 시작 마크로 되돌려 놓고(또는 종료 위치를 다시 **Set position**), 다시 **`Survey the room and come back`** → 새 경로 카드가 상자를 피해 가는지(미니맵·Isaac) 확인. SIM으로도 같은 문장을 보내 비교 가능.

## 3. 녹화 (Physical AI 트랙: 실물 로봇 1분 이상)

- 카메라: 로봇과 상자가 같이 보이게 고정, 전체 1회 주행 연속 촬영(6–7분).
- 화면: ffmpeg 데스크톱 캡처는 `-movflags +frag_keyframe+empty_moov`를 꼭 넣어 강제 종료에도 파일이 살아남게(06:50 세션 녹화는 이 옵션이 없어 인덱스 손실). `Start-TwinPulse-Test.cmd`로 시작하면 CDP 검증·스크린샷 도구 사용 가능. OS 녹화(Win+Alt+R) 사용 시 **커서 표시**, 클릭마다 **1–2초 멈춤**, 채팅 메시지가 뜰 때 2초 대기. 녹화 전 디스크 10 GB 재확인(어젯밤 ENOSPC 충돌은 데모 녹화 스크립트의 프레임 파일 때문).
- 라벨은 UI 그대로: declared start + wheel odometry, not localized. 자율 SLAM/방 전체 커버리지라고 말하지 않기.

## 4. 기대 결과

- A: 4/4 정지 도달, 복귀, 완주 메시지, 후보 1개 이상(상자). Add to Twin 후 재계획 경로가 상자 주변 0.35 m 이상 떨어짐.
- B: 1구간에서 `FIELD_PROXIMITY_10CM` → 후진 → 재계획 메시지 → 나머지 정지 도달(keepout 안의 정지는 "skipped"로 표시, 번호는 그대로) → 복귀.
- 오도메트리 종료 오차 수 cm, 테이프 실측과 10–15 cm 차이는 정상(어젯밤 14 cm). 이건 "not localized" 라벨의 이유.

## 5. 실패 시

| 증상 | 조치 |
| --- | --- |
| `Set the robot position and heading on this Twin first` | Twin이 다시 표시된 뒤 Set position을 다시(씬 revision이 바뀌면 재선언 필요). |
| `Stop and prepare the robot before a route` | Prepare 다시, READY 확인. |
| 첫 이동 전 `STEP_NOT_ACKNOWLEDGED` | 연결 지연. Stop → Prepare → 다시 요청. 자동 재전송은 없음. |
| `FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP` | 바퀴 미끄러짐/트래커. 바닥 확인 후 재시도. 가드 완화 금지. |
| 근접 정지 후 `RECOVERY_…` 로 멈춤 | 상자를 치우고 로봇을 시작으로 되돌려 다시 요청(재계획은 최대 2회). |
| `ROUTE_RECORD_WRITE_FAILED` / `declared_route_record_failed` | 디스크 꽉 찼음. 공간 확보 후 다시 요청(이제 앱 재시작 없이 가능). |
| Route 카드가 안 보임 | Twin 패널 하단, 씬이 바뀌면 숨겨짐. 채팅 메시지는 그대로 남음. |
| 앱이 멈춘 것처럼 보임 | 상단 Current step 줄에 `Route running · stop k of 4`가 보이면 정상 진행 중. Stop route / Stop all은 항상 동작. |
| 전압 경고 | 충전. 보호 해제 금지. |

종료는 항상 **Exit** 버튼(정상 cleanup → 토크 OFF·LiDAR OFF·disconnect 영수증).

## 5b. 06:45–07:25 실물 세션 결과 (`outputs/path-b-20261026/phys08/SESSION.md`)

- 경로 1: Arm/Bootstrap 전 Run → 미ACK(이동 0). 경로 2: 상자 앞 근접 정지 → 25 cm 후진 → 재계획 실패(시작점 막힘). 경로 3: 시작 LiDAR keepout으로 상자 우회, 정지 1 도달 후 175.7° 회전 시간 초과. 경로 4: ±2° 재조준 진동 → 운영자 Stop. 충돌 0, 가드 변경 0, Disconnect 확인, 배터리 12.37 → 11.78 V.
- 위 네 결함은 세션 직후 코드로 수정(리뷰 문서 #27–#30)하고 새 빌드에 포함했습니다. 충전 후 같은 체크리스트로 재시도하면 됩니다.

## 6. 어젯밤 바뀐 것 요약 (자세한 목록: `docs/analysis/TWINPULSE_FABLE_QUALITY_REVIEW_2026-10-26.md`)

- 디스크 풀 시 경로 러너가 영원히 RUNNING으로 남아 다음 경로가 409로 막히던 결함 수정(507 응답, 자동 복구).
- 근접 정지 재계획 후 정지 번호가 어긋나 "3 of 3 stops"로 잘못 세던 결함 수정(건너뜀 정지는 별도 표시).
- 정지마다 채팅 진행 메시지, Twin 패널 Route 카드(진행/결과/Stop), 상단 Current step 표시.
- "N finite moves" 문구를 "about N planned moves, re-aims can add more"로 정직하게.
- 경로 끝난 뒤 실물 고스트가 마지막 위치에 얼어붙던 문제, Isaac 오버레이가 궤적 800점에서 갱신을 멈추던 문제 수정.
- Enter 키가 Send 버튼 게이트를 우회하던 문제, 첫 연결 실패 시 영구 disconnected 문제, "Submitting…" 오표시, 빈 플릿에서 Add SIM robot 숨김, 빈 뷰포트 안내 문구, 임포트 후 다음 단계 안내.
