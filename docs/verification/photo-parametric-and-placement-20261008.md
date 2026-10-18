# 사진 라이브러리·관계·실제 편집 연결 — 2026-10-08

## 범위와 현재 판정

사용자의 2시간 연속 요청으로 07:17:49 KST부터 기존 계획의 P1→P3→P4와 영향 범위 회귀를 진행한다. 로봇 OFF, 새 외부 모델/유료 호출 0, SSH/serial/배포/설치/시스템 설정/commit/push/새 에이전트 0이다. 실제 모델 품질이나 실물 인수를 가짜 PASS로 바꾸지 않는다. `whole_demo_ready=false`, H5–H6/C3–C6 PARTIAL, 기존 예약 PAUSED를 유지한다.

07:17:49–09:17 KST 약 2시간의 구현·검증을 마무리했다. 아래 P1/P3/P4의 각 실제 결과를 개별 판정하며 전체 Full Process 완료를 의미하지 않는다. 마지막 r18 화면 유지/편집/재열기와 owned 종료도 PASS다.

## 기존 제품에 연결한 변경

- **사진 intent 1.2:** 기존 opt-in compact 경로의 planner strict schema/프롬프트에 실제 환경 모델 라이브러리, 선택한 model ID·XYZ 치수·variant·finish, 바닥/상면/드레이프/벽/천장 관계와 parent/part/anchor/elevation을 전달한다. compiler 1.3은 치수를 임의 clamp하거나 방을 늘리거나 물체를 삭제하지 않는다. seven furniture kinds는 기존 `furniture-parametric-1.0`으로 생성한다. 구 1.0/1.1 reader/compiler·직렬화/hash는 그대로다.
- **배치 관계:** `photo-placement-contract-1.0`은 추정 관계의 sidecar다. 실제 sensor observation이나 좌표 정합이 아니다. 부모가 없거나 자기/순환/중첩인 관계, 미지원 kind/part/anchor, 너무 작은 상면, 상면 형제의 겹침, 천장/바닥 이탈을 거절한다. 침구/옷의 선택된 drape만 지원하며 케이블/천/unknown의 synthetic keepout은 보존한다.
- **저장/편집:** 새 sidecar가 있을 때만 source record 2.1로 저장하고 구 2.0 shape는 변경하지 않는다. 공개 dict는 deep copy다. 기존 App→scene preview/apply→history→Undo/reopen에서 부모 translation/yaw/XYZ resize와 자식을 하나의 검증된 수정으로 처리한다. 독립 자식 이동은 attachment 위반으로 거절한다. 부모가 너무 작아지면 source/history를 변경하지 않는다. 새 edit context는 1.1, 이전 context 1.0과 proposal wire 1.0은 보존한다.
- **기존 편집 UI의 floor map:** 물체 footprint 드래그, 90° 회전, 5cm 키보드 이동을 기존 편집기에 연결했다. 드래그는 입력 미리보기일 뿐 Preview→Save 전에는 저장/Isaac/로봇을 변경하지 않는다. grab offset을 보존해 모서리 선택 시 centre가 튀지 않으며, outside/cancel/busy/attached child를 제한한다. legacy 가구 footprint도 저장 geometry에서 계산한다. 선택창의 접근성 이름은 option 내용과 분리한다.
- **실제 병목 수정:** Undo의 before object마다 이전 history를 반복 컴파일하던 코드를 operation당 1회로 바꿨다. 검증/hash를 제거하거나 lease TTL을 늘리지 않았다. 기존 네 수정/24항목 기록의 동일 CLI cProfile에서 compile 198→4회, status wall 약 3.158→0.171초였다. 이는 작은 고정 사례이며 p95/GPU/로봇 전송 성능이 아니다.
- **연속 Undo:** actual r13에서 이동→회전→Undo 두 번의 두 번째 Undo가 첫 Undo를 취소하는 기존 toggle semantics를 재현했다. explicit placement source의 새 이력만 `scene-changes-1.1` active edit stack으로 생성하며 연속 취소/새 분기/빈 stack 거절을 검증한다. 기존 `scene-changes-1.0` 이력은 reader/replay/직렬화/hash/toggle 의미를 소급 변경하지 않는다. 새 source라도 저장된 구 이력은 1.0 그대로 재열린다. operation wire는 바꾸지 않는다.
- **실제 마우스 입력:** generic button hover transform이 작은 footprint를 cursor 밖으로 옮겨 pointerdown이 사라지는 결함을 선택 marker 전용 hover/active transform으로 수정했다. r12/r13에서 real pointerdown/capture/move/up, .32m 이동, Preview/Save 및 exact Isaac JPG hash를 확인했다. r12의 async controlled acknowledgement 시험 동기화 실패와 r13의 실제 연속 Undo 결함은 원 FAIL로 보존하며 최종 전체 인수는 별도 결과를 따른다.
- **실제 실패 복구:** owned USD rollback에서 CopySpec이 기존 child order를 보존해 재생성 Environment가 뒤로 이동했다. backup과 정확히 같은 child set/order만 recursive 복원하고 PhysicsScene을 제거하지 않는다. 사용자 root 밖이나 실행 권한을 복원하지 않는다. 실패 시 raw 이전/이후 USD와 diff/hash를 synthetic 시험 artifact로 남기며 coded assertion으로 보고한다.
- **배포 검사:** 기존 builder가 필요한 provider test fixture 모듈을 포함하도록 했고 기존 package verifier에 placement/scene/library/text-generation/diagnostics 시험을 추가했다. 정상/저장 실패 시험은 현재 채팅→Projects→Advanced tools 진입으로 맞췄다. 이 legacy 진단 경로의 성공은 채팅 D01–D12 전체 인수가 아니다.

## 현재 검증 근거

| 검증 | 결과와 제한 |
|---|---|
| Provider | 117 PASS / 3.060s. 새 schema/치수/styles/지지/벽·천장/거절/single repair, 이전 layout 회귀. 모델 응답은 고정 transport |
| Core | 302 PASS / 26.920s. 실제 LLM/Isaac/실물 증거 아님 |
| App 관련 여섯 모듈 | 227 PASS / 105.244s. placement·scene changes·model library·text generation·R5 API·diagnostics; import 중복 포함, 다른 집계와 합산 금지 |
| 최종 stack Undo·저장·진단 | 145 PASS / 65.296s. 빈 stack 거절·새 분기·legacy toggle/직렬화 보존, parent-child atomic/원본 보존 포함. 위 집계와 중복 |
| Web | 최종 45 files / 383 PASS / 25.92s, TypeScript/Vite build PASS. `index-CtQD8DZ5.js` / `index-sXaisMAz.css`, JS 596.14kB/gzip174.20kB, 기존 500kB chunk 경고 유지 |
| Profiling 제품 저장 | 실행 `7dfc9fa263544065bebb5f01fd631e5a`, `offline_scene_replay` succeeded, 30 profile rows, thread CPU .21875s, raw 제외/원본 불변. [저장 기록](../../artifacts/verification/photo-parametric-replay-profile-20261008/diagnostics) |
| 실제 Isaac rollback r2 | **PASS**. 실제 USD 변경 이후 visual compose fault→정확한 이전 stage/identity/Burger 복원·실패 receipt 원인/type·성공 receipt 없음, 만료 permit/중복/engine-room 변경 거절, external prim/프로젝트 원본/paused timeline 보존. Physics/실물/사진 정합 NOT_RUN. [결과](../../artifacts/verification/geometry-rollback-20261008-r2/verification.json) |
| 실제 P1/P3 브라우저 연결 r16 | **PASS**. 사진 업로드→고정 intent→실제 Isaac Build/PhysX 목표 도착·두 번째 채팅 목표/Stop/reload/reset→desk/monitor·bed/bedding의 atomic 이동/회전/XYZ resize→실제 cable pointer drag·회전/Preview/Save→연속 Undo 두 번→종료 후 동일 원본/8 operation 이력 재열기. 실제 219 frames/13 commands(9 Build, 2 Run, pause, reset), page errors 0, 네 current JPG hash 일치, 추가 자동 Run 없음. 진단 desktop/mobile/search/profile/export(raw 제외), owned 종료 PASS. [결과](../../artifacts/verification/photo-parametric-20261008-r16/result.json). 사진 복원 품질/실물 증거 아님 |
| 최종 개발 package r5 | **PACKAGED_WEB_API_ISAAC_OFFLINE_PASS**. 550 files / 23,326,694 bytes, dirty=true, 기존 최종 Web 재사용/고정 local wheel. checkout 밖 274 App/core 및 actual normal/storage/geometry/startup PASS, driver/input 해시 불변·격리 복사본 정상 제거. clean install/physical NOT_RUN |
| 최종 실제 화면·편집 r18 | **PASS**. reset 후 편집 전 idle 600.122초/588 samples, current frame 공백0/canvas1/추가 Build·Run0(기존 Build1/Run2), JS heap28,508,464→6,796,968bytes/peak29,609,828bytes. 그 뒤 동일 실행의 실제 grouped edit·pointer drag·회전·연속 Undo·8 operation disk reopen/원본·이력 불변 PASS. 전체 current frames4792, page errors0, inference source unchanged=true, owned backend/engine 정상 종료. [결과](../../artifacts/verification/photo-parametric-20261008-r18-soak/result.json). 30분/편집 후 soak/동적 Loop/logger on-off/GPU 전체 인수 아님 |

## 실패 원본은 보존한다

- photo r1 route readiness evaluator wait, r2 compact fixture의 불필요한 repair 요구, r3–r6 실제 history/lease 병목, r7 mobile layout, r8 선택창 exact 접근성 이름, r9/r10 hover로 pointerdown 누락, r11 초기 Build readiness 미확인, r12 async acknowledgement 시험 동기화, r13 실제 연속 Undo를 모두 보존했다. r11은 초기 준비에서 Build/Run 0으로 차단됐고 바로 이어진 격리 r12/r13에서는 초기 자동 Build가 통과했으나 정확한 r11 원인은 미확정이다. 동시에 두 actual Isaac을 시작한 당시 부하 가능성을 원인으로 단정하지 않는다. 성공한 앞부분 때문에 전체 FAIL을 PASS로 바꾸지 않는다.
- geometry r1은 장면 형상 상실이 아니라 USD child order 차이였지만 exact rollback 기준 FAIL이었다. [이전/이후 diff](../../artifacts/verification/geometry-rollback-20261008-r1/rollback.diff)를 보존하고 product order 복원 후 r2로 통과했다.
- package r1은 checkout 밖 272 App/core PASS였지만 normal/storage browser의 옛 화면 selector 및 actual USD exact rollback에서 FAIL, startup case만 PASS였다. [원 결과](../../artifacts/verification/photo-parametric-package-20261008-r1/verification.json)는 덮어쓰지 않는다.
- package r2는 actual 네 경우 PASS이나 자식 subprocess가 isolated source import 경로를 받지 못한 4회귀 실패 및 검사 중 driver 변경으로 전체 FAIL이다. r3 core도 같은 원 FAIL이다. verifier는 caller의 PYTHONPATH를 가져오지 않고 자체 격리 복사본의 package root만 descendant에 전달한다. parent는 계속 `-I`로 실행한다. package gate/geometry/placement 23 PASS / 3.866s; 새 Undo 최종 placement+legacy scene changes 23 PASS / 1.868s. 초기 두 stack test의 방 경계 이탈 fixture는 실제 규칙대로 거절됐으며 시험 위치만 합법적 centre로 교정했다; 방/검증 조건은 완화하지 않았다.
- package r4는 수정된 isolate 경로로 272 App/core 및 actual normal/storage/geometry/startup 모두 `PACKAGED_WEB_API_ISAAC_OFFLINE_PASS`, driver unchanged=true다. 이 후보는 stack Undo 수정 직전이며 **최종 소스의 인수를 대신하지 않는다**. 최종 [r5](../../artifacts/verification/photo-parametric-package-20261008-r5/verification.json)는 550files / 23,326,694bytes, stack Undo 포함 274 App/core 및 actual 네 경우 PASS. manifest `ad82389b09b52b3a5a300afa7eebfae8fa48c6149f711865e07d480969472453`, driver/input unchanged=true, isolated_copy_removed=true. 검증에 별도 제공한 저장 scan raw는 배포 member가 아니며 전후 hash 불변이다.
- photo r14는 새 stack Undo Build receipt가 모두 succeeded였으나 현재 JPG URL이 다음 frame으로 교체된 정상409를 시험이 HTTP 실패로 취급해 전체 FAIL이었다. 수정된 runner는 15초 한도 안에서 그 409만 최신 동일 revision 재조회하며 frame SHA를 검증한다. Build/Run 재전송이나 다른 HTTP 오류 묵살은 하지 않는다. 실패 DTO에 product readiness/lease와 viewport를 추가해 초기 준비 결손을 더 직접 확인할 수 있게 했다. r15는 다른 owned package Isaac 시험과 시기가 겹친 상태에서 180초 authenticated handshake timeout으로 UI 시작 전 FAIL이며 supervisor와 최초/종료 진단을 보존했다. GPU 시험 종료 후 단독 r16으로 재검증한다. timeout의 정확한 원인을 동시 부하로 단정하거나 정책을 느슨하게 바꾸지 않았다.
- 단독 r16은 위 전체 bounded journey PASS, inference source unchanged=true, backend/engine owned 종료 PASS다. r17 추가 soak는 시험 runner의 `placementEdits` 선언 누락으로 reset 다음에 FAIL(제품 명령은 성공)이며 원본을 보존했다. 선언 수정 후 r18은 600초 idle와 뒤의 전체 편집 연결/종료 PASS다. r18의 soak 순서는 환경 변수 이름 불일치로 편집 **전**이었다(`after_placement_edits=false`). 종료 뒤 runner를 실제 `TWINPULSE_PLACEMENT_EDITS` 이름에 맞췄고 Node syntax PASS지만, 수정된 **편집 후** soak 순서는 actual NOT_RUN이다. r18 원본/해시는 수정하지 않았다. 이 시험 오류를 제품 PASS나 30분 자원 인수로 바꾸지 않는다.

## 로봇 OFF 현장 수집 후보

기존 `run_robot_field_suite.py --prepare-field-candidate`를 실행해 최종 `6fd252d643c64f088594d44eb5161907/manifest.json`과 source archive 92 members를 고정했다. source ID `634e56cec63be2eee5ccf5ed0325f7bccb1fd96488bfb816aae3be039dfbd071`, syntax/import/contracts/unchanged PASS_LOCAL_ONLY, 기존 corrected driver compile 증거는 PASS_NOT_ACTIVATED다. collection 79 tests/3skip + LiDAR11 + field212/25.284s PASS(중복). SSH/scp 및 기존 key/host는 존재만 확인하고 내용을 읽지 않았다. **로봇 접촉/배포/이동 승인 0**, autonomous readiness=false다. 최종 `checked()` 재조회도 PASS. 직전 `178dc05862c6425dbb4e67beab9d8941`은 Undo 코드 변경 후 PC fingerprint changed로 정상 거절됐고 원본은 보존했다; 수집 robot source ID는 동일하지만 PC 코드 fingerprint는 다르다.

이것은 collection 준비 후보이며 F0 전체 자율 임무 등록 완료가 아니다. current boot/release·corrected scan/odom/TF·실측 mounting/footprint·timing·방 reference/정합·Stop/목표/Loop 인수는 없다. 현장 전 `checked()`는 소스/runner/archive/compiled proof/유효기간을 다시 확인한다. 오래된 통과 관측이나 승인 복사 및 배포 hash 우회는 하지 않는다.

마지막 candidate 회귀 18 tests / 1.854s PASS(SSH/실물 함수는 injected). 최초 제한 shell에서는 Windows Temp 하위 디렉터리 접근 WinError5로 18 tests/33 errors였다. 기존 승인 절차로 해당 오프라인 임시 파일 시험만 다시 실행해 통과했다; 거부를 우회하거나 원 실패를 지우지 않았다. 원 fixture patch의 기존 whitespace 경고는 이 작업에서 unrelated 수정하지 않았다.

## 사진·모델·물리 근거를 구분한다

현재 실제 Isaac 시험은 원본 사진의 업로드를 통과하지만 **모델 출력은 explicit 8×8m/24항목 fixture**다. 실제 렌더를 확인할 수 있어도 사진의 좁은 방 크기/좌우/문 hinge/가림의 정확한 복원 증거가 아니다. 세 상면 관계와 두 drape, wall/ceiling 관계는 고정 intent/compiler 연결을 검사했다. 실제 모델이 새 계약을 지키거나 잘못된 사진 배치를 스스로 수정하는 성공률은 P2 잔여다. opt-in 실험은 기본 OFF이며 실제 모델 평가 없이 기본 정책으로 승격하지 않는다.

원본 사진 SHA256 `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`을 마지막 정리에서 다시 확인했다. 패키지 r5는 고정된 개발 배포본이며 검증 뒤 문서 상태 갱신으로 그 원본 manifest를 다시 쓰지 않았다. 실제 제품/Web 코드는 package 인수와 r16에 대응하고, 후속 soak test runner 수정은 별도로 남긴다.

### 실제 화면 근거

아래는 AI 생성 이미지가 아닌 actual Isaac/current JPG와 브라우저 캡처다. **시험용 넓은 8×8m 배치이며 사용자의 실제 방 복원이 아니다.**

![드래그 저장 후 실제 Isaac 장면](../../artifacts/verification/photo-parametric-20261008-r16/placement-drag-isaac.jpg)

[회전 반영 current JPG](../../artifacts/verification/photo-parametric-20261008-r16/placement-rotate-isaac.jpg) · [연속 Undo 후 current JPG](../../artifacts/verification/photo-parametric-20261008-r16/placement-undo-8-isaac.jpg) · [편집 완료 채팅 화면](../../artifacts/verification/photo-parametric-20261008-r16/placement-restored-chat.png)

## 정확한 잔여와 다음 순서

이번에 닫힌 범위는 고정 intent의 실제 drag/rotation→Preview/Save→exact Isaac frame→연속 Undo→disk reopen 및 동일 개발 package의 checkout 밖 네 경계 인수다. 다음은 아직 닫히지 않았다.

1. P2: 새 사진/텍스트 계약의 실제 모델 성공률·사진 배치/지지 품질·single repair를 기존 승인/ledger/privacy 범위 재확인 후 평가한다. 이번 2시간에는 새 호출을 하지 않았다. compact 기본 정책 승격도 하지 않는다.
2. P3/P4: 다른 사진/집/혼합 창고, 나머지 D01–D12 및 timeout/cleanup/stale/Loop의 전체 조합 인수. r11 초기 readiness/r15 cold handshake의 정확한 원인은 여전히 미확정이며 단독 성공이 원인 해결을 증명하지 않는다. clean install/다른 PC 배포도 NOT_RUN이다.
3. O2/O4/O5: remote ACK/정합 계산 세부·제한된 raw 조회/일반 graph 및 30분 자원 기준, logger on/off·동적 Loop·GPU/프로세스 전체 측정. 현재 마지막 10분 화면 시험은 이 전체 항목의 대체가 아니다.
4. F0/F1: 오프라인 source/archive/driver collection 후보는 준비·재검사 PASS지만 전체 자율 임무 등록은 미완료다. 검토 release/profile·navigation calibration·adaptive qualification/sensor 근거를 닫은 다음, 별도 현장 승인으로 corrected scan·odom/TF·실측 mounting/footprint·timing·정합·짧은 목표/Stop/왕복을 검증한다. 과거 boot/release 승인과 Stop 결과를 새 후보에 복사하지 않는다.

원본 사진/raw·과거 실패·dirty·v1/v2 hash·실물 scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s를 보존한다. 전원만 켜면 전체 실물 데모가 완료된다는 보장은 없다.
