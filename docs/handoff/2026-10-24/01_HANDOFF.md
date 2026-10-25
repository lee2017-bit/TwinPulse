# TwinPulse 현재 구조와 구현 상태 인계

기준일은 2026-10-24 KST입니다. 제출이 임박한 시점의 우선순위는 기능 확대가 아니라 **실제 스캔 공간을 가져와 편집·SIM·저장·재열기까지 이어지는 데모와, 별도로 검증한 실물 자동 명령**입니다. 사용자 요청은 독립 검토용 인계 자료 작성이며 현재 로봇은 충전 중입니다.

## 1. 지금의 결론

텍스트/사진 기반 초안과 로컬 Isaac 화면, RoomPlan 환경 Import·객체 이동/Undo·SIM 목적지 기능은 구현되어 있고 과거 같은 설치 여정의 성공 근거가 있습니다. 그러나 사진→3D 충실도, 실물 연속 조종, RoomPlan과 실물 좌표정합, 실제 몸체 이동/제동, 최종 제출 영상까지 모두 끝난 제품은 아닙니다.

가장 최근 수정은 수동조종이 아니라 **유한 거리·각도 자동 명령의 실행 수명 분리**입니다. 소프트웨어 보조검사는 통과했지만 새 설치의 실물 시험은 배터리 보호 경계에서 Arm이 거절되어 자동 이동에 진입하지 못했습니다. 충전 후 이 변경의 실물 효과를 확인해야 합니다. 이번 실패를 입력 지연 재발로 분류하거나, 이전 설치의 네 명령 성공으로 새 변경을 통과 처리하면 안 됩니다.

## 2. 정확한 버전과 작업 위치

| 대상 | 기준 |
| --- | --- |
| 개발 root | `C:\Users\jaewo\Documents\TwinPulse` |
| Git 로컬 HEAD | `249be107dec38ddafcd52828559d2fcfd66a591c` |
| 작업 트리 | 미커밋 수정·신규 파일 다수. HEAD는 현재 설치의 전체 소스가 아님 |
| 현재 설치 | `20261024T053958Z-9d2b297a8246`, 1,682 exact files |
| 설치 source manifest ID | `9d2b297a8246b902d08b4bfe773af1195e6f6b313673e934fc37fa02e675612c` |
| 최신 실제 launch | `c33072ddfbaa490db3b28ece7f763079` |
| 최신 실제 operation | `abfc5082aec74ec1a79205783c59375a` |
| project / physical robot | `chat_mvki3gm9_e212190a` / `2bf518f09a234dd5b65c312febda8841` |
| 직전 부분 성공 설치 | `20261024T044855Z-597678ea2fcb` |
| 직전 부분 성공 operation | `8dda7811b4c640f7a077a685bbc67bed` |

설치 source ID는 build script가 정렬한 파일→SHA 맵을 직렬화해 계산한 식별자입니다. `source-manifest.json` 파일 자체의 바이트 SHA와 혼동하지 않습니다. 이번 인계 문서는 설치 이후 추가된 문서이며 제품 재빌드/설치를 하지 않습니다. GitHub의 현재 상태를 새로 조회하거나 push하지 않았습니다.

## 3. 제품 방향과 범위

TwinPulse는 현장 사진·설명·스캔으로 초기 Twin을 만들고, 변경을 검토·시뮬레이션하며 로봇 관측을 이용해 개선하는 Physical AI Copilot을 지향합니다. 거실/TurtleBot3는 접근 가능한 시험장이지 산업용 AGV 인증이나 공장 전체 자동화의 증명이 아닙니다.

현재의 가장 짧은 공간 입력 경로는 이미 확보한 RoomPlan USD입니다. 사진 생성 경로는 남기되 충실도 문제를 별도 관리합니다. USDZ 전환, 전용 iPhone Scanner, 새 SLAM·재구성 모델·GPU Cloud·VDA5050 구현을 이번 데모의 선행조건으로 추가하지 않습니다. 향후 기능을 포기한다는 뜻은 아닙니다.

## 4. 현재 실행 구조

```text
설치 Launcher / Python supervisor
├─ Electron BrowserWindow → React chat/Twin UI
├─ Python App backend (loopback, 인증)
│  ├─ 프로젝트·대화·revision·편집 transaction·Library/Environment 저장
│  ├─ Provider worker → typed 결과 검증 → Build/Apply 승인
│  ├─ Isaac typed bridge → Extension/compiler → /World/TwinPulse
│  └─ PhysicalFleetAdapter → 한 authenticated SSH session
│     └─ Pi worker
│        ├─ InputGate / finite executor / field supervision
│        ├─ ROS sensor·odom·guard receipt / 실제 출력 admission
│        ├─ source-bound C++ output guard → OpenCR/모터
│        ├─ native LiDAR reader → bounded 원문 writer
│        └─ 별도 scan tracker / journal / durable field evidence
└─ 소유 Isaac process → 렌더 frame·SIM fleet·scan·엔진 ACK
```

LLM은 지원된 typed scene/task intent를 생성합니다. 임의 Python/셸을 실행하거나 실시간 모터 루프를 책임지지 않습니다. UI의 연결·명령 접수, robot-local 실행, Stop readback, 디스크 기록완료, 실제 몸체 이동은 서로 다른 사건입니다.

### 주요 파일과 책임

| 소스 | 책임과 우선 검토 지점 |
| --- | --- |
| `apps/twinpulse-desktop/main.mjs`, `automation.cjs` | 같은 설치 Electron 창, 명시 Test/debug 진입, 종료 |
| `apps/twinpulse-web/src/ChatWorkspace.tsx`, `TwinViewport.tsx`, `RobotFleet.tsx` | 채팅·Twin 표시, 실제 버튼/입력·명령 상태 |
| `PhysicalLidarPanel.tsx`, `RobotTimingSettings.tsx` | 실물 sensor-local scan, 등록값/추천값 UI |
| `packages/twinpulse_app/src/twinpulse_app/api.py`, `product_workflow_service.py`, `application.py` | 제품 API와 입력/생성/Build 상태 |
| 같은 App의 `scene_edit_transaction.py`, `scene_changes.py` | preview→Apply→engine ACK→저장/Undo/revision |
| 같은 App의 `environment_workspace.py`, `scripts/twinpulse_environment_worker.py` | 명시 단위·원본 보존·mesh별 환경 Import |
| `packages/twinpulse_core/src/twinpulse_core/environment_source.py`, `environment_navigation.py`, `navigation_grid.py` | 원기하·object ID/상대이동, floor mask·경로 |
| `extensions/twinpulse.extension/.../scene_compiler.py`, `environment_geometry.py`, `isaac_adapter.py` | 실제 USD/정적 충돌·엔진 작업 |
| `scripts/twinpulse_fleet_runtime.py`, core `sim_fleet_navigation.py` | Isaac SIM fleet·기하 기반 이동·목적지·scan |
| App의 `robot_fleet.py`, `physical_fleet_adapter.py`, `physical_live_session.py` | SIM/REAL 분기, source/context/epoch, SSH transport·원본 수집 |
| App의 `robot_registry.py`, core `robot_timing_profile.py` | 등록·상세 파라미터·측정·수동 추천/적용 |
| `packages/twinpulse_robot_safety/fleet_control.py`, `teleop_contract.py`, `teleop_ros.py` | Pi 명령/권한/계산·freshness·발행/Stop |
| 같은 safety의 `field_tests.py`, `native_stream.py`, `robot_journal.py`, `include/` | native scan·보조추적·기록·실제 출력 guard |

ZIP 경로는 위 상대 경로 앞에 `source/`를 붙입니다. `...`로 줄인 Extension 경로의 중간은 `twinpulse/extension/`입니다.

## 5. 구현 완료와 미완료

| 기능 | 현재 구현/근거 | 아직 미완료 또는 주장할 수 없는 것 |
| --- | --- | --- |
| 채팅·텍스트/사진 입력→초안→Isaac | 실제 provider/Isaac 여정의 과거 성공. 검증/승인 분리, 취소/저장 이력 구현 | 모든 사진의 충실한 복원 아님. 과거 사진 코호트 완전 품질 PASS 0/6 |
| RoomPlan 환경 Import | 원 USD/SHA, 명시 단위, 객체별 mesh/ID·static triangle collider·floor mask; 실제 Import/수정/Undo/cold/SIM 근거 | 완전 무손실 USD 편집기·실측 scale·사진 외관·모든 통로 연결 보장 아님 |
| 가구 편집 | 제한된 한 객체 XY 상대이동, 자연어 제안/preview/명시 Apply/ACK·저장/Undo | 일반 CAD·벽 구조/회전/크기 편집 전체 아님 |
| TurtleBot SIM | 등록 이력·모델·거리/각도·scene 목적지·scan/OFF·Stop·저장/재열기 | fleet 경로는 kinematic/기하 검사. 실물 wheel dynamics·PhysX 제동 증명 아님 |
| 실물 App 연결/Prepare | 실제 App SSH·source-bound guard 확인·1200ms readback 확인. ad-hoc SSH는 인수 대체로 사용하지 않음 | 임의 신규 PC/로봇 설치 성공 보장 아님 |
| 실물 모델/scan 표시 | 추정 anchor의 모델과 별도 sensor-local 실제 점 표시, OFF/stale/owner 정리 | 방 위 실측 pose/scan projection 아님. 방 전체 view에서는 모델이 작음 |
| 실물 짧은 명령 | 직전 설치에서 전후10cm·좌우90도 4개 COMPLETED/Stop readback, wheel 기준 | 몸체 거리/제동/미끄러짐·현재 finite 정책 통과 아님 |
| 수동 연속 제어 | 구현되어 있으나 원 입력만료·버전/도전값 경합 이력 있음 | 사용자 결정으로 추가 수정·시험 중단. 해결/센서 대역폭 한계로 확정하지 않음 |
| 새 유한 자동 executor | 집중10/회귀252 PASS·설치·Astra 설계/소스 검토 | 최신 실제 run은 이동 전 배터리 admission 실패. 자동4개/360 NOT_RUN |
| 기록/정리 | 최신21,414행 exact/COMPLETE·Stop torqueOFF·journal/native 종료·App root 정상0 | 늦은 정상정리로 앞선 주행 실패를 PASS로 바꾸지 않음 |
| 실물 객체 목적지 | estimated anchor·relative tracking을 이용하는 별도 경로가 있음 | 현 RoomPlan과 실물 정합/가구 도착 미검증. 새 finite 정책에 포함하지 않음 |
| 최적화/RL·산업 연동 | 장기 방향과 설계 일부 | 배포된 Nav2/RL 최적화·VDA5050 호환·산업 안전 인증 미완료 |
| 제출물 | 과거 SIM 데모와 시험 녹화 존재 | 현재 전체 사이클 완료·최종 실물 영상/공개 제출 완료 아님 |

실행 증거의 release가 다르면 같은 결과로 합치지 않습니다. 과거 PC/SIM 전체 gate PASS는 당시 범위의 사실이고 최신 실물 전체 PASS가 아닙니다.

## 6. RoomPlan 원본과 Import의 경계

원본 `Project-2610222326.usd`는 38,339 bytes, PXR-USDC, SHA-256 `844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b`입니다. 이 ZIP에는 개인 주거지 geometry/사진을 넣지 않았습니다.

기존 분석의 OpenUSD 결과는 Y-up authored, **metersPerUnit 미작성**, Mesh30/정점1212/삼각형620/외부의존0입니다. Wall15/Door4/Window2/Floor1, Chair2/Refrigerator1/Sofa1/Storage3/Table1입니다. API fallback0.01을 실측 단위로 쓰지 않습니다. 현재 Meters 선택은 `selected_for_sim`이며 실측 검증과 다릅니다.

Environment Import는 composed transform을 world vertices에 bake하고 객체별 wrapper/mesh로 author합니다. 원 parenting/transform stack/복잡 shader/RoomPlan confidence 전체를 보존하는 reference editor가 아닙니다. Library의 단일 MeshAsset/enclosing-box 경로에 방 전체를 넣으면 안 됩니다. 문 mesh를 임의 삭제하거나 clearance를 낮춰 통로를 만들어 통과시키지 않습니다.

## 7. 반복 오류와 지금까지 바꾼 것

문제가 모두 같은 timeout 하나는 아닙니다. **첫 원거절 → 후속 generation/HTTP409 → 정리**를 분리해야 원인이 보입니다.

| 분류 | 확인된 사례 | 이미 수정한 범위 | 남은 불확실성 |
| --- | --- | --- | --- |
| 최초 연결/정지 제어 | 미발행 `-inf` JSON, blocking queue 중 Stop 경합 | JSON 진단 null·Stop 자기 명령 guard 경계 보완 | 이 수정이 모든 지연을 해결했다는 뜻 아님 |
| PC 표시 I/O가 입력 경로 차단 | battery 설정 read/registry lock, workflow snapshot·GC | 표시 read/cache를 control critical path에서 분리, Stop 우회, 중복 empty-history compile 감소 | 모든 과거332/711ms의 전 시간을 한 I/O 원인으로 확정 불가 |
| 수동 입력의 수명/갱신 | timer+inflight 위상, 원age 중복공제, nonce/generation 거절 | sentAt 기반 갱신·원clock 보존·중복구간만 공제·비밀 없는 window 결속 | 정확 선행 hop UNKNOWN인 과거 실패 존재. 수동 추가수정 중단 |
| native 센서/디스크 정체 | read 후 decode 전4.664s, journal queue full/maxwrite10.224s | native bounded writer4096항목/4MiB·main16384항목/16MiB, sticky 실패·실종료 확인 | 부하 전체 성능 보장 아님; overflow를 버리고 PASS 금지 |
| durable 저장/종료 대기 | ACK fsync 약9.864s 대2s, final writer_alive | 저장 commit2→30s, 장치 Stop/OFF 뒤 journal drain2→15s | 제어/센서 timeout을 늘린 것 아님. 실제쓰기오류는 계속 FAIL |
| LiDAR 원문/coverage | 주기적 unknown bytes·불완전 ring, 방향5.375도 gap | unknown 보존; 한정 supervised last complete ring+새 위험 veto. 사용자 승인 valid-return gap10도 | strict/ICP는 불완전 ring을 정상으로 바꾸지 않음; UI 설명 일부5도 잔존 |
| 원입력 만료 중 자동회전 | 직전360 약226도에서 `SOURCE_EXPIRED_DURING_ENABLE` | 새 finite executor에서 원격 입력 수명과 새 local 결정 시각 분리 | 최신 정책 실물 효과 NOT_RUN. manual 그대로 |
| 최신 배터리 admission |11.0999994278V/<=11.1V, Arm 전 gen48→49 | **기준 변경 없음**. 중단·원문보존·정상정리 | 충전 후 부하 전압여유와 실제 자동 명령 확인 필요 |
| 시험도구/녹화 | aria 이름 mismatch·kernel reset·부분 녹화 | 현재 DOM의 accessible name 확인, 복구를 별도 기록 | 도구 오류를 엔진/로봇 실패로 혼합하지 않음 |

RAM/DWM·native 화면 캡처의 과거 문제도 있습니다. renderer CDP 동작 성공은 OS/native 캡처 경로 해결 증명이 아니고, 재부팅/프로세스 종료를 유일 원인으로 단정하지 않습니다. 현재 인계 작업에서는 새 App/Isaac/로봇을 시작하지 않습니다.

## 8. 최신 자동 명령 변경의 의미

정책명은 `ROBOT_LOCAL_FINITE_SUPERVISED_V1`입니다. `fleet_control.py::_activate_finite_execution`, `_check_finite_execution`, `_accept`, `_tick`과 `teleop_contract.py::InputGate.accept/check`를 우선 검토하세요.

1. 최초 task와 필요한 post-arm watch는 기존 원격 원시각/nonce/sequence/generation/1초 수명을 통과해야 합니다.
2. 승인된 finite job만 operation/robot/project/connection/boot/release/Twin context/request/motion epoch/generation/목표/origin/고정deadline에 결속합니다.
3. 각 local 제어 결정의 시각은 센서/진행 계산 **시작 전**에 잡습니다. 원 remote request clock과 decision sequence를 별도로 보존합니다. 발행 직전 오래된 원격 입력 시각을 새로 꾸미는 것이 아닙니다.
4. 수락된 새 supervision watch는 자신의 원시각/nonce/seq/gen을 검증한 뒤 원source 기준5초만 갱신합니다. 거절된 watch는 권한을 갱신하지 않습니다.
5. task deadline/감독/바인딩/Stop/센서/native guard를 검사하고 실제 `RosLink.publish`의 preflight·최종발행 경계에서도 veto를 유지합니다. 완료·취소·Stop 후 늦은 응답이 task를 되살릴 수 없어야 합니다.
6. 수동 drive·estimated object route·bootstrap/presence-gap 등 진단 field trial은 기존 정책을 유지합니다.

이것은 **실행권한 의미의 변경**입니다. 수동 입력1초가 만료되어도 승인된 finite job은 살아 있는 별도 감독권한 내에서 계속할 수 있습니다. 모든 정지시간 의미가 완전히 같다고 말하면 안 됩니다. source age/로봇측1200ms출력차단·task총시간과5초감독은 서로 다른 보호입니다.

## 9. 현재 등록된 시간·동작 정책

아래는 최신 operation의 실제 등록값입니다. 코드 전역 기본값이나 모든 로봇의 안전 표준이 아닙니다.

| 값 | 현재 값 | 목적 |
| --- | --- | --- |
| input renewal / input window |100 / 50ms | PC 갱신과 짧은 window 발급 주기 |
| original input TTL |1000ms | 새 원격 입력/로컬 결정의 최대 나이, manual 수명 |
| actual output timeout |1200ms | 로봇 C++ 최종 출력 만료·readback 필요 |
| original-source operator presence |5000ms | finite 별도 감독, 네트워크 무제한 지속 아님 |
| sensor source / receipt / guard receipt |500 / 500 / 500ms | 원 timestamp와 ROS 수신 신선도 각각 |
| odom sample interval / wheel interval |500 / 500ms | 연속 표본 간격 |
| odom source / scan source |750 / 750ms | source age |
| native receipt |500ms | native ring 원 수신 age·구간 |
| odom–scan skew |50ms | 별도 정합용 timestamp 차이 |
| tracking result / delivery / ICP compute |1000 / 750 / 150ms | 추적 결과·worker전달·계산 예산 |
| ROS service |1000ms | 서비스 응답 대기 |
| field speed / angular cap |0.03m/s / 0.20rad/s | 감독시험 engineering cap, 실측 보장 아님 |
| valid directional return gap / clearance |10도 / 0.10m | 한정 field 유효점/여유 검사, unknown은 free 아님 |
| battery / field session |<=11.1V 차단 / 최대900s | 이번 그대로 유지 |

사용자 결정: 신규 등록 시 초기 측정으로 계산한 뒤 **등록값을 자동 변경하지 않습니다.** 새 측정 저장→명시 `Recalculate`→추천 확인→명시 `Apply recommended`로 다음 연결의 등록값을 바꿉니다. 활성 세션은 불변이며 reconnect가 권한을 복구하지 않습니다. 이 UX와 CAS/해시 검증을 유지하세요.

## 10. 가장 최근 실제 실패의 정확한 연결

`evidence/latest/original-excerpts.jsonl`과 index에서 원문을 볼 수 있습니다.

- 최초 seq9068/events04:184: `BATTERY_LOW`,11.09999942779541V(표시11.10), button0, source22.658ms/sensor receipt8.560ms. `teleop_ros.py::fresh`는 `battery <=11.1`에서 거절하므로 float 오류/심한방전으로 단정하지 않습니다.
- Arm 직전 seq15359/events07:43: 같은 배터리 fault가 generation48→49로 철회. PC Arm 원요청은 generation48입니다.
- 약50.510ms 뒤 seq15372/events07:57: `field_arm` 요청 `74d3c0e9-afd2-452f-afc8-694dd556e6d7`가 `MOTION_GENERATION_CHANGED`로 거절.
- seq15596/events07:296: bootstrap 요청 `28f7f4f6-7e53-4f16-b04f-3ea429a25548`가 `FIELD_SUPERVISION_CONFIRMATION_REQUIRED`로 거절.
- 유한 Send 명령/수동/360은 요청하지 않았고 nonzero PUBLISHED command0입니다. stationary79frame/invalid3의 INCONCLUSIVE는 별도 품질 판정입니다.
- 최종 ROS Stop/torqueOFF/encoder[0,0]/cleanuptrue·LiDAROFF·recordingCOMPLETE, PC21,414행/9segments37,454,551B exact; robot journal19,470/native5,114 모두saved/queue0/writer 종료. App backend/engine root 정상0·Job정리·runtime/Kit보존.

Astra 독립검토도 같은 연결을 확인했습니다. 그 검토는 반례 후보이지 Claude가 그대로 따라야 하는 결론이 아닙니다. 현재 finite 실물 미검증, 이전 manual/360 실패, 몸체/세계정합 미완료를 유지해야 합니다.

## 11. 임의로 바꾸면 안 되는 결정

- **현재 사용자 범위:** 수동조종 추가수정 중단, 먼저 유한 자동 명령. 충전 중 실물 재접속/구동 금지; 다음 현장 준비와 명시 승인을 별도로 확인합니다.
- **사실/권한:** SIM PASS·HTTP200·수락·wheel 도달·scan byte 변화·후기 정상정리는 몸체/안전/전체 성공이 아닙니다. 원 실패를 삭제·합성·스킵해 PASS로 만들지 않습니다.
- **시간/안전:** 원시각·unknown bytes·Stop fencing·출력 guard·속도/전압/clearance를 단지 통과시키려고 풀지 않습니다. 새로운 engineering 정책은 이유·범위·반례·승인·실물 결과를 별도 기록합니다.
- **제품:** 영어 UI, 간결한 버튼; 대화는 한국어. 등록→Connect→Prepare→이동은 별도 사건. 자동 명령 제출 후 입력창을 비우고 영상에서는 입력 후 Enter 전3초를 둡니다.
- **표시:** 로봇 바로 아래 이름, 가리는 초록 원 없음. 실물 추정 anchor/sensor-local scan은 world alignment로 표시하지 않습니다. LiDAR OFF에는 hit/beam/활성상태가 남으면 안 됩니다.
- **데이터/환경:** 원USD·사진·프로젝트·원로그·Undo·해시·버전 보존. `/World/TwinPulse` 밖 Stage 변경, 무관 데이터 삭제, credential 읽기/출력, 임의모델 코드실행 금지.
- **확장/배포:** 새 SDK/ROS/Isaac/driver/WSL/Docker·유료Cloud·외부업로드·공개전환·Git push는 별도 범위. VDA5050·전용iPhone앱·범용SLAM/RL 전면도입을 막판에 강제하지 않습니다.
- **시험:** 일반 인수는 실제 같은 설치 UI/실제 provider·Isaac 경로. mock/API/fault시험은 보조로 표시. 긴 SIM 전체행렬을 매 수정마다 반복하지 말고 변경 영향·원실패에 맞춰 검사합니다. 최종 주장 범위의 종단시험을 생략한다는 뜻은 아닙니다.

## 12. 다음 가장 작은 실행 단위

현재는 문서/코드 독립검토만 합니다. 충전 후 감독 승인된 별도 세션에서 실제 App 연결→무구동 Prepare/readback→LiDAR 부하의 전압여유→stationary기록→감독 Arm→한정 bootstrap Stop→유한 전후10cm/좌우90→단일360을 확인합니다. 첫 실제 실패를 원문과 함께 보존하고 해당 경계를 진단합니다. 충전/입력 수명/센서/저장/세계정합을 한 원인으로 섞지 않습니다.

성공하면 같은 설치의 Stop/OFF/Disconnect·원본 반출·정상종료까지 마감합니다. 실물 가구목표는 좌표정합이 검증된 뒤의 별도 범위입니다. 최종 데모는 Home부터 원입력/Import·로봇추가·SIM/변경/Undo/재열기가 보이도록 촬영하고 실물 footage와 구분합니다.

## 13. 독립 검토에서 특히 의심할 지점

새 finite executor가 정말 fresh command admission과 지속 supervision을 분리했는지, 오래된 원격 의도를 무심코 재발행하는 경로가 없는지 확인해야 합니다. local decision 시작→native검사/record→최종publish 사이의 나이와 Stop/epoch fencing이 핵심입니다. 현재 tests는 fake clock/device 및 실제 Python publisher 경계이지 실제 ROS 네트워크·MCU·바닥 검증이 아닙니다.

현재 구조에 불필요하게 겹친 동기 I/O/복제/상태기계가 있는지, 무엇을 지우면 위험 없이 간단해지는지도 검토 요청합니다. 기존 코드를 정당화할 필요는 없습니다. 다만 전면 재작성이나 새 기술 도입을 결론부터 정하지 말고, 코드 위치·재현 조건·최소 수정·반례와 함께 제시해 주세요.
