# 상대배치 탐색·정지 센서 준비와 실제 인수 — 2026-10-15

상태: **PARTIAL**. 사진을 로봇 대응용 공간 초안으로 만드는 기능을 계속 보강했지만, 사진 배치·동일 방 센서 정합·실물 시험은 완료하지 않았다. 단위시험과 실제 사용자 시험을 구분한다.

## 승인·방법

사용자가 Nebius 누적 한도를 USD20으로 늘렸다. 원 carry USD6.6206901에는 과거 UNKNOWN 예약이 포함된다. 초기화·환급하지 않는다. 기존 ITM0018 원사진/기존 공개 사진·파생 Isaac 렌더·시험 텍스트를 기존 Flash/Super로 전송하는 범위다. OpenAI, 실물 로봇/SSH/serial/모터/전원, 유료 Cloud, 새 의존성, commit/push/공개 배포는 이번에 하지 않았다.

일반 설치 `Start-TwinPulse.cmd`를 실행 도구로 호출하고 실제 Chrome New chat→Attach→Send/Create→생성/수정 중 현재 Isaac 화면을 관찰했다. 제품 API 직접 호출·고정 응답·이전 결과를 fresh 생성으로 대체하지 않았다. Explorer 더블클릭/OS 이미지 Ctrl+V/native Isaac 패널은 NOT_RUN. 화면의 두 패널을 검증하기 위해 1920×920 viewport override를 사용했으며 최종에는 해제한다. Astra xhigh 한 명은 읽기 전용 검토만 했다. 주 작업자 자체의 모델 설정은 도구로 변경하지 않았다.

원사진 `C:\Projects\TwinPulse\ITM0018.jpg` SHA256 `4fea13acb1152a742db047a0fd2797ea3850e4c42c016d6fbe8a5050b79933c2`. 사전 사람 비교 기준은 침대 왼쪽/문 뒤/책상 오른쪽 벽에 평행한 장축/책장·의자·부모 지지다. runtime 사진별 제약으로 넣지 않았다. 치수와 거리는 실측 미검증이다.

## 확인한 원인과 변경

1. v485 원사진 P04의 검토는 책상 장축·책장 위치 모순을 발견했지만 확신 .55/.6은 hard issue .8 미만이라 지원 소품 문제만 수리했다. .8을 낮추지 않고 `current-render-review-1.1`에 실제 compiled footprint/장축/plan SHA와 별도 미확정 `layout_hypotheses`를 추가했다. 이 정보는 합성 기하이며 source pose나 LiDAR 센서 높이의 실측값이 아니다. 구 검토1.0 reader도 유지한다.
2. 현재 frame/candidate/plan/capture SHA가 일치하고 이미 hard repair가 필요한 경우에만 가설 대상의 의존 assembly를 위치·yaw·placement 범위로 탐색할 수 있다. 미확정 가설로 model/recipe/규격/무관 packing neighbor를 열지 않는다. 부모·지원 위험·pending을 보존하며 기하/PASS 기준을 완화하지 않았다.
3. 실제 P01에서도 가설은 전달됐지만 수정 모델이 작은 지지 문제만 줄였다. 후속 `observed-quality-repair-1.5`는 기존 quality repair 한 슬롯에 미시도 materialized floor root 하나를 실제 footprint 면적으로 선정한다. 큰 hard geometry/고신뢰 모순이 있으면 이 탐색보다 먼저 처리한다. root 3필드 trial 또는 typed abstain을 요구한다. root 모델/크기와 room은 이 실험에서 고정한다. 소품 reparent만으로 root 실험을 수행했다고 할 수 없다. 변경/compiled 효과/새 critic 품질은 다른 기록이다.
4. no-change abstain도 별도 `layout_experiments` checkpoint 이력에 남겨 재개 때 다시 “미시도”로 선택하지 않는다. 추가 coax 호출·stall 초기화·품질 승격을 하지 않는다. 새 탐색 정책은 아래 P01 뒤의 변경이므로 실제 모델 효과는 NOT_RUN이다.
5. rollback 재컴파일은 progressive 모드와 원 pending 진단을 유지한다. 기존 stall latch가 fresh critic 전에 종료시키는 경계까지 해결했다고 하지 않는다.
6. 정지 수집 시작 시 source/input/effective scene/state SHA를 job별 immutable `stationary-twin-collection-1.0` sidecar로 남긴다. 종료 시 원 CLI 보고서 경로/bytes SHA와 시작 참조 SHA를 별도 `stationary-twin-receipt-1.0`에 연결한다. 원 CLI/raw는 수정하지 않는다. 현재 pose/정합/이동 권한의 증거가 아니다. 실제 수집은 이번에 실행하지 않았다.
7. 센서 review의 bounded diagnostics DTO에는 fit/heldout 잔차, 다른 가능한 변환, 벽 후보, 관측 수·odom 분산과 제한을 담는다. 가구 semantic 대응은 `not_implemented`, pose truth/physical authority는 false다. 실제 화면의 빈 목록에는 정지 스캔과 다시점 정합의 차이를 안내한다. 기존 공통 Apply/Undo를 유지한다.

## 실제 P01 — 최종 사진 합격 아님

- 동결03 build `20261015T110040Z-2e0359809a40`, source `2e0359809a40ec786737c380f88adcfeb5608b7bfd8d547c6a7b17cc1d98ccd5`, ZIP `4678c0441c102e36fb4bb62019ccfb7e6962778a924c59f8d59d38e70f06f860`.
- project `chat_mv9fkjv9_a332af06`, request `e2a24aef-c8eb-42d3-b13f-f6298db76766`, execution `b562df0c8cf042d5823e65703745eda1`, checkpoint `60d396c1cadf2b74685260eda2142fbe46344c64cef8fca2ba66d7c063ff908e`.
- 첫 구조 관측43.766s+설계3.375s 뒤 실제 바닥/벽이 상세 관측보다 먼저 나타났다. 이후 최대6개 묶음, 30개 파라미터, 첫23→수정 후27개 표시/3개 대기를 관찰했다. 이 수량은 사진 품질 판정이 아니다.
- 세 성공 critic의 책상 모순 확신 .6→.7→.7, compiled 장축 X 유지. source는 오른쪽 벽을 따르는 앞뒤 장축이다. 세 patch는 머리맡 소품4개/같은 소품4개/duvet만 바꾸고 책상 yaw0을 유지했다. 소품을 책상에 옮겨 pending 수가 줄어도 사진 지지·배치가 개선됐다고 판단할 수 없다.
- 마지막 네 번째 critic은108.468s 뒤 `finish_reason=length`, completion40,000 모두 reasoning, visible chars0. `hidden_reasoning_without_final_at_limit`, `PROVIDER_OUTPUT_TRUNCATED`. 원 요청/schema/응답 SHA는 audit/evidence에 보존한다. 토큰 한도를 올리거나 응답을 추측 복구하지 않았다.
- 전체550.64s/17HTTP/repair3, `DRAFT_INCOMPLETE`, accepted saved scene0. 마지막27개 미리보기와 `duvet_cover/pillow_1/plush_fish` pending3은 보존한다. 실패 후 실제 브라우저 reload에서 정적 미리보기/대기3/카메라 disabled가 남는 것을 확인했다.
- 사전 계획의 P02 같은 사진 반복/P03 텍스트·실제 자연어 수정은 출력 소진 중단 원칙 때문에 NOT_RUN. 옛 source의 편집/Undo 성공을 이번 새 source의 성공으로 합치지 않는다. 모델 비교 벤치마크나 성능 우위 근거가 아니다.

## 실제 저장 보기·Exit 실패와 보강

03에서 이전 v485 저장 프로젝트 `chat_mv9bglwq_c6ce983d`를 실제 Open/Reopen/View했다. 현재 stage `3e96ecd4-b38b-4d86-8d4b-d68f6ed76e4c`/약7FPS/원21표시+7pending을 확인했다. 이는 이전 저장 장면 복원 시험이며 새 사진 성공이 아니다. 저장 센서/map 선택지는 없고 정합은 NOT_RUN이다.

이후 Exit는 `shutdown_busy`로 반복 거절됐고, 다른 프로젝트 Open도 `Wait for the current change to finish.`로 막혔다. 화면/engine은 built, run_id null, Reset ACK였지만 이는 HTTP handler가 끝났다는 증거가 아니다. Reset/Hide Twin/중복 탭 정리만으로 해결되지 않았다. 입력 없는 중복 TwinPulse 탭51개(44개 종료 화면, 7개 Connecting)를 확인 후 닫았으며 다른 사이트와 원 프로젝트/대화/실패/파일은 보존했다. 중복 탭을 원인으로 확정하지 않는다.

현재 브라우저까지 완전히 닫고 같은 Start로 재연결한 홈의 일반 Exit는 정상 supervisor stopped로 끝났다. 원 busy는 실패로 유지한다. 강제 종료/카운터 초기화/안전 기록 삭제/파일 프로토콜 우회는 하지 않았다.

후속 source는 요청별 route allowlist/context/thread/phase/elapsed를 payload·인증 없이 기록한다. **등록된 변경 POST만** 대상이며 GET·부분 헤더·conversation 사전 본문 읽기까지 포함하는 전 연결 추적이 아니다. `_json` 진입 전 이미 업무 결과가 구성된 요청은 business fence를 한 번 해제하고 응답 전송 상태는 별도 유지한다. 실행 worker/transaction/engine pending/UNKNOWN/실물 gate는 그대로다. 늦은 응답의 원 context도 유지한다. 30s socket inactivity와 총 본문 read1/chunk-write deadline은 LLM/엔진 시간 제한과 별개다. 업무 잠금 대기 자체의 원인 해결이라고 주장하지 않는다.

05 실제 Open/Reopen/View는 stage `2aecbdaf-e499-4495-9395-60534dcac868`의 current/활성 카메라까지 확인했다. 첫 Exit는 `other_product_post / dispatch / 0.187s`와 겹쳐 거절됐으며 FAIL로 남긴다. 명시 재시도는 정상 stopped였다. 후속06은 새 변경을 closing fence로 막고 기존 동기 POST를 최대2초 drain한 뒤 **진단용32개 목록이 아닌 전체 business count**와 worker/engine/UNKNOWN을 재검사한다. workspace 잠금 안에서는 robot/worker 잠금을 기다리지 않는다. 완성·fsync된 sibling만 atomic no-overwrite link로 게시하고, 미발행 write/fsync/link 실패는 자신이 소유한 closing만 복구한다. 기존 부분 파일을 덮거나 성공으로 응답하지 않는다. Stop/카운터/원 안전 이력은 유지한다. Astra가 발견한 세 지적을 수정하고 읽기 재검토에서 잔여 P1/P2 없음(이 범위)을 확인받았다.

06 build `20261015T121205Z-9dfbaab39fce`, source `9dfbaab39fce66e4d3448fa3947e793fb11f2d1fbb07112cbff94dd8cbfc86f3`, ZIP `9756922b3965c6cda43ee3481f6d105efd76184ddcf1a54c5266a5ed66db9678`를 일반 설치했다. 임시 viewport는 해제하고 기본 브라우저 크기로 Open/Reopen/View→stage `e15f2158-882f-4420-8636-e4786e831229` frame301/21:19:23 current/카메라활성→Twin 열린 채 Exit **한 번**→supervisor stopped를 확인했다. launch `825680806224428cb0a305d0e763cc89`, execution `008cb1a53e5549379d7e439700071023`. 이 부분 흐름의 PASS이며 새 사진/수정정책 인수가 아니다.

첫06 전환에서는 read3초 경고와 old 프로젝트 선택 뒤 P01 헤더가 보이는 불일치를 한 번 관찰했다. 원인 확정 없이 보존한다. 명시 재선택 뒤 current/Exit는 정상이다. Astra 읽기 분석은 일반 late GET의 project/epoch guard가 존재하며 헤더 복귀 경로는 확정하지 못했다. 늦은 bootstrap 응답의 context 갱신, `project_context_changed`/client `context_changed` 복구 이름 불일치는 후속 재현 후보이지 이번 원인 증거가 아니다. 이를 최종 전체 무결점으로 숨기지 않는다.

정상종료 전후 원 v485 저장 source/history/scene/state/objects/inventory/placements의7해시와 편집4개·pending7이 exact였다. history SHA `4bd8e17eb7992a23cca25db4bb4b07c75de3a319222a429f71a965c6e8ef95f8`. Reopen의 새 대화 메시지는 정상 추가됐으므로 대화 파일 전체 bytes 불변이라고 쓰지 않는다.

최종06 normalExit/브라우저 닫기→같은 installedStart/8765→실제Open/Reopen/View를 다시 수행했다. 새 launch `3a30a211c52f481389932c41fbe81b5c`/execution `f258cb2bd5cd4e1abbd164edcd16d65c`, stage `46056e61-3568-4880-b1cc-727fd3c14628` frame58/21:25:18 current·원사진decode·카메라활성을 확인했다. domain 재감사7해시·편집4·pending7 exact는 `restoration.json`에 보존한다. 전환 중 read3초경고는 다시 관찰돼 응답성 PASS는 아니다. 앱은 이 이전 저장 부분장면으로 열어두며 paid/robot 작업은 없다. 단일보고서는 실제16화면을 포함한다.

## 검증·잔여

Provider 집중66 PASS, 센서/readiness DTO Web12와 viewport74 PASS, TypeScript/Vite build PASS. 정지 참조·보고서 sidecar와 센서 diagnostics 집중2 PASS, 앞선 readiness/chat83 및 sensor review/import24 검사는 서로 중복되며 단순 합산하지 않는다. HTTP lifecycle/기존 workspace/Windows contract 최종24 PASS에는 실제 로컬 반쪽 헤더·인증된 반쪽 본문408/무명령, 느린 업무 fence 유지/응답 쓰기 fence 해제/연결 종료/총 deadline·32+1 uncapped 판정·robot/workspace barrier·쓰기/fsync/link 실패 후 정상 재시도·기존 invalid 파일 보존이 포함된다. 이들은 zero-network 또는 local fault 보조 시험이며 새 실제 LLM/Isaac 인수를 대체하지 않는다. 과거 legacy catalog asset/API와 progressive App fixture 실패는 해결됐다고 쓰지 않는다.

03 원사진 실패와05/06의 기능 결과는 서로 다른 source cohort다. 새 focus 탐색의 실제 모델 효과, critic reasoning-only 출력 소진의 구조적 해결, 원사진 배치/소품 지지, 동일 방 유효 raw/다시점 정합·가구 대응·실물 정지 수집, fresh 반복/text/mixed/unseen/cancelresume/native/독립PC·공개 gate, 위 선택불일치/read3초 경고가 남는다. 실물 이동은 준비 완료가 아니다.

현재 새 추정USD0.2712045(Flash .1624512/Super .1087533), 새 held/UNKNOWN/중복0. 원 carry 포함 보호USD6.8918946/20. usage×보존 단가의 추정이며 공급자 청구 확정이나 계정 잔액이 아니다. P01 중단 후 새 유료 추론0.

실제 화면/모든 시도/식별자/입력·source SHA/비용은 `outputs/robot-sensor-preparation-20261015/report.html` 단일 로컬 비공개 보고서에 모은다. 원사진·좌표·raw·보고서를 GitHub에 올리지 않았다. 파일 URL 시각 QA는 이전 도구 정책 차단을 우회하지 않으며, 실제 App 화면 직접 관찰과 HTML 구조 검사를 구분한다.

최종 로컬 배포물 manifest1367파일 hash 검증 PASS/public_ready=false. 단일HTML1,848,790bytes의 내장JPEG16개를 전부 디코드 검증했고 외부 active asset0/script·iframe0, 수정 문서·API diff whitespace 검사 PASS다. 이는 HTML 브라우저 시각 QA나 독립PC/공개배포 자격을 뜻하지 않는다. 검사 도구 첫 PYTHONPATH 누락과 shell quoting 오류는 도구 호출만 수정해 재검사했으며 제품/실제 생성 시험 실패로 합산하지 않는다.
