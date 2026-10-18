# 실행 ID 통합 진단 제품 연결 — 2026-10-07

## v339 1시간 연속 작업: 표시 장애·저장 경합·launcher 수명주기

작업 범위는 2026-10-07 22:23–23:23 KST의 로봇 OFF 개발·검증이다. 새 유료 모델·로봇·SSH/serial·센서/모터·배포·설치·commit/push·새 에이전트 호출은 없다. 기존 App/API/core/실제 Isaac 경로에 연결했고, 범용 로깅 서비스나 새 runner를 만들지 않았다.

### 수정한 제품 경로

- **브라우저 표시 실패:** 이미지 HTTP/content/decode/draw 오류를 인증·CSRF를 통과한 `browser_view_observation` 실행으로 기록한다. 현재 engine/epoch/revision과 최근 관측 frame에 결속하고, 원 Build 실행과 typed 참조로 연결한다. 원 Build/receipt 성공을 실패로 다시 쓰지 않는다. UI 배너·현재 단계·exact 진단·export를 연결했고 표시 오류 중 SIM Run만 차단하며 Stop은 유지한다. 브라우저 보고는 신뢰된 엔진·로봇 안전 판정이 아니다. 같은 owner/scene/cause는 서버 64개 bounded cache와 브라우저 64개 cache로 반복 보고를 제한한다. 재열기·복구 이후에도 저장된 실패는 남는다.
- **정상 frame 교체와 장애 구분:** 실제 10분 시험에서 화면이 11회 비던 원인은 metadata/image GET 사이 frame 교체를 장애로 처리한 것이었다. 409 교체 응답에는 마지막 **아직 1초 이내인** frame만 유지하고 다음 read poll을 기다린다. 401/404/5xx는 `viewport_http_error`로 표시·기록한다. 모든 실패 HTTP를 만료로 뭉뚱그리던 API도 수정했다. 오래된 이미지의 1초 만료는 그대로이고 Build/Run/카메라 mutation을 자동 재실행하지 않는다.
- **시작 입력 보존:** 첫 conversation/saved draft 복원 전에 사용자가 입력한 텍스트를 뒤늦은 빈 저장본이 덮어쓰던 실제 브라우저 결함을 수정했다. draft 복원만 제한하며 과거 승인이나 Run 권한을 복원하지 않는다.
- **다중 프로세스 기록 용량:** 독립 store의 캐시 때문에 12,000-byte 제한에서 22,147 bytes를 기록하던 결함을 재현했다. 디스크 writer만 nonblocking OS reservation과 8-byte generation marker를 사용해 예산 확인과 쓰기를 묶는다. marker까지 전체 용량에 포함한다. 다른 writer/중간 종료를 발견하면 캐시를 폐기하고 다시 계산한다. 경합·손상 marker·hardlink는 optional diagnostics degraded이며 원 기록을 삭제하거나 자동 복구하지 않는다. 입력·정지 admission은 디스크 lock을 잡지 않는다. 이 검증은 저장 root별 quota이며 컴퓨터 전체 디스크/GPU 자원 상한 보장이 아니다.
- **launcher 감시·정리:** 성공한 `launcher_start`는 보존하고 후속 `launcher_monitor` 및 `launcher_shutdown`에 원 launch execution ID를 연결한다. 엔진 exit/stale 실패와 명시적 restart/project switch cancellation을 구분한다. cooperative engine stop-file 저장·owned process 정리·log close 실패는 cleanup role/typed code로 기록하고 최초 감시 원인을 덮지 않는다. 오류 메시지·경로·secret은 진단 metadata에 넣지 않는다. supervisor→인증 API→오류 배너의 exact runtime 실행 링크를 연결했다. 기존 owned-only 종료 순서·대기·강제 종료 조건은 바꾸지 않았다.

### 이번 검증과 보존한 실패

| 검증 | 결과·범위 |
|---|---|
| 최종 Python 통합 | 229 PASS / 96.016s. diagnostics·viewport·process manager·text scene generation·bridge·lease. import된 기존 API/chat 클래스 중복 포함, 다른 집계와 합산하지 않음 |
| 추가 마지막 회귀 | launcher sink 실패/명시적 project switch 및 marker 포함 quota까지 26 PASS / 2.120s. 위 227과 중복 포함 |
| 최종 Web | 44 files / 374 PASS / 32.48s. startup 입력·HTTP 분류·표시 ID 반복/복구·runtime exact ID·Stop 유지 포함 |
| type/build | PASS, 67 modules, JS 590.97kB / gzip172.60kB. 기존 500kB chunk 경고는 유지 |
| 두 프로젝트 병렬 제품/API | 실제 두 로컬 인증 API와 named ProjectStore에서 동일 request ID의 독립 생성·저장·exact 진단/export·재열기 PASS. 다른 프로젝트 ID는404, 다른 cookie는401. LLM 응답은 명시 fixture이고 엔진 명령0; 두 GPU 동시 실행 인수가 아님 |
| 공유 root writer | 독립 캐시·동시 owned subprocess/24,000-byte cap·owned writer 비정상 종료/lock 해제/캐시 복구·marker 손상/hardlink 보존·optional admission 부담 회귀 PASS. 실제 OS power loss나 모든 filesystem 공격을 인수한 것은 아님 |
| 실제 Chrome/API/Isaac 최종 r6 | **PASS**. HTTP503 표시 실패의 exact 실행→원 Build succeeded→export→복구, 실제 PhysX 목표 도착/거리오차3.97cm·Stop·접은 화면 Stop·reload 비재실행·reset·진단/profile/모바일·owned 종료. 600.286초/588회 soak 관측의 current frame 공백0·canvas1·추가 Build/Run0·heap19,273,272→6,753,716 bytes/peak20,048,944 bytes. 실제 engine sent4,407 frames/metadata 관측4,693회(최근2,000개만 보존). page error0·추론소스 SHA 불변·supervisor stopped·launcher_shutdown succeeded |
| 동일 최종 코드 이미지 업로드 | [v339 image r1](../../artifacts/verification/execution-diagnostics-v339-image-20261007-r1/result.json) **PASS**. 업로드/질문/저장/실제 렌더/PhysX/Stop/reload/reset·진단/profile/export/모바일·owned 종료. engine sent121 frames/metadata 관측101회/drop2, capture PASS, page error0·추론소스 SHA 불변·launcher_shutdown succeeded. 사진 인식은 명시 fixture이며 실제 방 정밀도/실물 증거가 아님 |

[실제 r6 결과와 소스 SHA](../../artifacts/verification/execution-diagnostics-browser-soak-20261007-r6/result.json), [표시 실패 진단](../../artifacts/verification/execution-diagnostics-browser-soak-20261007-r6/browser-display-diagnosis.png), [복구 후 reset 렌더](../../artifacts/verification/execution-diagnostics-browser-soak-20261007-r6/generated-reset-preview.png)를 확인했다. browser 보고 POST는 최초/새로고침 각1회로 총2회지만 같은 저장 실행 ID로 결속된다. 엔진 frame6회 drop은 bounded publisher 관측이며 soak 화면 공백0과 구분한다. launcher monitor의 엔진 실패·cleanup 실패 주입은 위 Python 회귀이고 실제 Isaac 고장 주입 인수라고 확대하지 않는다. 실제 정상 종료 root/child는 r6 결과에 보존했다.

실제 제품 검증은 기존 `verify_chat_sim_journey.py`/`chat-sim-journey.mjs`에 opt-in 표시 fault·bounded 60–900초 soak만 확장했다. 프레임·snapshot 관측 기록은 최근 2,000개와 전체 counter를 구분하고 soak 샘플도 초당 1개/최대900개다. JS heap은 Chrome Performance `JSHeapUsedSize`이며 GPU/RSS 전체 메모리나 무한 장시간 leak 검증으로 표현하지 않는다. 실제 모델 응답은 fixed fixture이므로 사진/LLM 품질 증거가 아니다.

이전 r1 selector, r2 startup 입력 덮임, r3 새로고침 후 옛 Run 승인 재활성 기대 오류, r4 600초/11회 화면 공백, r5 모든 HTTP를409 만료로 뭉뚱그린 분류 결함 결과를 보존했다. r4는 heap 18,832,924→5,726,884 bytes/peak19,960,196 bytes였지만 화면 연속성 실패이므로 전체 FAIL이다. r5는 실제 Build succeeded와 launcher cleanup succeeded여도 표시 오류 인수 실패이므로 전체 FAIL이다. 존재하지 않는 unittest 모듈을 지정한 두 실행과 마지막 메서드명 선택 오류도 loader ERROR로 보존했다. 확인한 모듈로 최종229 PASS, 마지막 store 클래스30 PASS/6.944s를 얻었으며 중복 집계를 합산하지 않는다. 어떤 실패도 PASS로 덮어쓰거나 원본을 삭제하지 않았다.

### 정확한 다음 잔여

최종 점검에서 text r6/image r1의 소스 SHA 65개씩을 현재 파일과 대조해 불일치0을 확인했다. 두 결과 모두 browser/capture PASS·page error0·paid0·robot0·supervisor stopped·owned backend/engine false·launcher cleanup succeeded다. 위 six-doc 현재 항목과 로컬 결과/화면 링크를 확인했고 새 원본 이동·삭제는 없다.

| 단계 | 이번에 해결한 범위 | 아직 남은 범위 |
|---|---|---|
| O1 | 공유 root quota/캐시 경합·owned crash 복구, 두 프로젝트 인증 API/저장 분리 대표 인수 | 다른 commit/sidecar 경계와 OS power-loss 복구 등 미검증 조합; 전체 PARTIAL |
| O2 | launcher admission 이후 monitor/stop/cleanup 기록과 원 시작 참조 | 외부 편집 LLM transport·survey/localization 계산·remote input/ACK 및 나머지 분기 correlation; 전체 PARTIAL |
| O3 | 기존 pure compile/validation profile 보존 | 실제 센서/정합/전송 세부 병목 미계측; 모터 loop 성능 인수 아님 |
| O4 | browser 표시 및 runtime 오류 exact 링크/검색/관련 실행/export | 다른 임무 오류 exact 링크, 안전한 raw 제한 조회, 일반 이전/후속 graph; 전체 PARTIAL |
| O5 | browser HTTP 실패·회복·대표 launcher 종료·두 프로젝트 API 및 실제 10분 idle/render 인수 | 중간 USD rollback/다른 저장·cleanup 조합과 실제 decode 정체/장시간 지연, 동적 장시간 Loop/GPU 전체 메모리 비교; 전체 PARTIAL |
| P1 → P2 | 이번에는 유료/사진 평가를 시작하지 않음 | compact-photo의 실제 치수/library·floor/support/attachment와 사진 의미 검사 → 기존 승인/ledger 재확인 후 실제 모델 성공/repair 품질 평가 |
| 패키지·현장 | 기존 준비/임무 guard 보존 | 현재 코드 패키지·F0 후 승인된 F1 실물 인수. 로봇 전원만 켜면 전체 데모 완료라는 보장 없음 |

H5-H6/C3-C6 PARTIAL, `whole_demo_ready=false`, 예약 PAUSED, raw/dirty/과거 실패/v1-v2/hash와 scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s 실물 임무 기준은 유지한다. 아래 v338 이하의 ‘현재’와 잔여 표현은 당시 이력이며 위 표가 최신 기준이다.

## v338 적용 오류와 필수 및 선택적 저장 오류

3D 적용 실패를 첫 화면 수신 실패와 구분하고, 배너의 원인·현재 단계·진단 버튼을 실패한 Build 실행 ID로 연결했다. 필수 프로젝트 저장 실패는 유효한 메모리 초안으로 남지만 저장 완료로 표시하지 않는다. UI와 API에서 해당 초안의 Build 및 SIM 준비를 차단한다. 선택적 진단 저장 실패는 정상 제품 실행을 실패로 바꾸지 않고 `Diagnostics degraded`와 누락 경고로 표시한다.

- `build_view.phase=apply`는 실패/미확정 receipt의 원 코드·메시지·명령 실행 ID를 사용한다. 이 DTO의 revision은 요청 대상이며 적용 성공의 증거가 아니다. 성공 뒤 화면 대기는 `phase=frame`이다. native command/receipt와 v1/v2 직렬화는 변경하지 않았다.
- 생성 저장 실패의 `project_save` 최초 오류와 `persisted=false`를 원 생성 실행에 보존한다. 초안은 메모리에만 있으며 재열기 시 유실될 수 있다고 안내한다. 실패 상태에서 acknowledge, Build 및 SIM plan/preview를 API로 우회할 수 없다. 모델 재호출·자동 저장 재시도는 추가하지 않았다.
- 입력 선택의 첫 저장 실패도 HTTP 연결이 끊기지 않도록 `input_persistence_failed`/503과 `input_selection → input_project_save` 실패 기록으로 처리한다. 이전 파일/선택 입력은 보존하고 오래된 생성은 취소한다. epoch를 과거 값으로 되돌리지 않는다. 이 추가 경로는 최종 HTTP 회귀로 검증했으며 아래 브라우저 주입은 생성 완료 시점의 저장 실패다.
- 기존 journey/fault-host에 opt-in 격리 옵션만 확장했다. 제품 launcher는 fault-host를 선택하지 않는다. 적용 오류는 실제 adapter/runtime 경계에서 **변경 전** 주입했으므로 중간 USD 수정의 rollback 인수를 뜻하지 않는다. 저장 주입도 해당 단계의 알려진 OSError이며 모든 디스크 고장 형태의 재현은 아니다.

### v338 검증

| 검증 | 결과와 범위 |
|---|---|
| 최종 Python | 진단 5개 클래스 + bridge/lease/viewport, **88 PASS / 28.840s**. 적용 실패 ID, 실패 후 frame 무효, 필수 저장 API 차단, 입력 저장 HTTP/이전 상태 보존 포함 |
| 기존 채팅 및 제품 API 회귀 | `test_r5_product_api`, `test_chat_conversation`, `test_chat_site_text_generation`, **134 PASS / 79.037s**. import된 테스트 중복 포함; 위 88과 합산하지 않음. 최종 입력 저장 취소 순서 변경 뒤 검증 |
| 최종 Web | **44 files / 362 PASS / 25.92s**, unhandled error 0. type/build PASS, 67 modules, JS 588.68kB/gzip171.91kB. 기존 500kB 경고 유지 |
| 실제 적용 오류 | `artifacts/verification/execution-diagnostics-apply-20261007-r2/result.json` **PASS**. 실제 Isaac command failed/RuntimeError/SIM_TEST_APPLY_FAILED, Build1/Run0, exact 진단/export/reload/재시도0/page error0/owned 정리. ID `e062164774ac4a5785b99c46d03e9871`. 적용되지 않았으므로 host 요약 FAIL·capture NOT_RUN을 그대로 보존; 렌더 성공으로 기록하지 않음 |
| 실제 필수 생성 저장 오류 | `artifacts/verification/execution-diagnostics-storage-project-20261007-r1/result.json` **PASS**. 메모리 초안/failed save/정확한 진단/export/reload/Build0/Run0, 종료 후 ProjectStore 재열기 site_draft 없음. ID `0d4e3196f7e546fd9e4fbe30c13c23fa`. host FAIL·capture NOT_RUN은 미적용 상태이며 렌더 인수 아님 |
| 실제 선택적 진단 저장 오류 | `artifacts/verification/execution-diagnostics-storage-optional-20261007-r1/result.json` **PASS**. 실제 렌더/PhysX 목표 도착·Stop·접힌 화면 Stop·reload/reset, 109frames, 진단 UI degraded/storage_errors118/누락 경고, page error0/owned 정리. 저장된 launcher 기록은 보존; backend 진단 manifest 실패로 누락된 generation을 성공 기록으로 조작하지 않음 |

모든 journey는 고정 외부 모델 응답이며 새 유료/로봇 호출0, 추론 소스 SHA 불변이다. 마지막 입력 저장 취소 순서 보완은 위 최종 Python 회귀로 검증했다. 브라우저 근거는 각 result의 source SHA와 해당 실행 시점 코드 범위에 결속한다. 적용 r1은 원인 문구 추가 전 근거이며 r2가 최종 Web 표시 근거다. 초기 Python 22개 중 넓게 주입한 fixture 오류1, sandbox Vite spawn EPERM, Web362 통과+잘못된 mock 응답으로 unhandled1은 실패로 보존하고 교정 후 결과만 PASS로 사용한다.

이 증분은 적용 경계 실패·필수 생성 저장·선택적 진단 저장의 **대표 제품 인수**를 마쳤다. browser 이미지 HTTP 실패, 다른 cleanup/저장 경계 조합, 두 프로젝트 병렬·다중 프로세스 quota/복구, 남은 correlation/raw 제한 조회/graph 및 최종 soak는 잔여다. 사진/library/관계와 실제 모델 품질, 현장 자율 데모도 미완료다. O1/O2/O4/O5·H5/H6/C3-C6 PARTIAL, `whole_demo_ready=false`, 예약 PAUSED, raw/dirty/과거 실패/hash/실물 guard를 유지한다. 아래 v337 이하의 잔여 표현은 당시 이력이다.

## v337 적용 성공 뒤 첫 화면 수신 누락

Build receipt가 성공한 뒤 첫 current frame이 오지 않으면 진단 span이 끝나지 않던 누락을 수정했다. 엔진의 적용 성공은 보존하고, 15초 동안 backend가 current frame을 확인하지 못한 관측을 별도 실패 실행으로 연결한다. 이 결과는 GPU나 Wi-Fi 고장의 확정 진단이 아니다.

- 기존 인증·revision·epoch·JPEG 검사를 통과한 frame만 인정한다. 같은 Build가 claim된 뒤 frame이 receipt보다 먼저 들어온 순서도 처리하며, 이전 Build의 frame을 새 대기에 재사용하지 않는다.
- `first_current_frame_timeout`은 failed, 연결 상실·엔진 교체·새 Build·기록 eviction으로 대기가 끝난 경우는 unknown이다. 명령 receipt와 원 실행의 성공은 다시 쓰지 않는다. 같은 대기를 반복 관측해도 실패 실행은 한 개다. 늦게 들어온 유효 current frame은 화면을 복구할 수 있지만 과거 실패 기록은 보존한다.
- 제품의 `build_view`는 표시 관측이며 native v1/v2 command·receipt·sensor 계약이나 실물 권한이 아니다. 현재 단계·오류 배너→정확한 진단→원 Build 실행을 연결했다. 같은 revision의 화면이 확인되지 않은 동안 SIM Run은 활성화하지 않는다. 18초의 UI 준비 대기는 backend 15초 관측 결과를 받기 위한 상한이며, 재시도나 안전 watchdog 완화가 아니다.
- 실제 대기 시간과 실패 기록을 만드는 짧은 시간을 분리해 표시한다. 다른 호스트의 timestamp를 빼지 않는다. 선택적 진단 저장 실패는 degraded이고 정상 receipt/frame 수신을 거절하지 않는다. 긴 오류 배너의 모바일 버튼 넘침도 수정했다.

### v337 검증

| 검증 | 결과 |
|---|---|
| Python 진단·Bridge·lease·viewport 85개 | PASS, 27.449s. 신규 4개: timeout/정확한 연결·반복 억제·늦은 frame, disconnect/교체, frame/receipt 순서, 선택적 sink 실패 |
| 최종 Web 44 files / 360개 | PASS, 24.14s. 화면 대기/실패 Run 잠금·exact 진단 링크·실제 대기 시간 분리 포함 |
| TypeScript / production build | PASS, 67 modules, JS 587.92 kB. 기존 500 kB 초과 경고 유지 |
| 최종 실제 첫 frame 전송 누락 r4 | PASS. 실제 Isaac 렌더 캡처 PASS, 의도적으로 전송을 막아 App frame 0, Build 1 succeeded / Run 0, 정확한 failed 관측·export·관련 실행·reload·모바일 인수 |
| 정상 실제 제품 경로 r1 | PASS, 88 frames. 목표 도착·Stop·접은 화면 채팅 Stop·reload 비재실행·reset·기존 진단 탐색/export |

[최종 누락 시험](../../artifacts/verification/execution-diagnostics-first-frame-20261007-r4/result.json)은 기존 opt-in fault host에서 live frame 전송만 억제했다. GPU scheduling·capture·JPEG 생성은 그대로이며 별도 actual render 캡처도 PASS다. 관측 execution `395e409de5554bee83fa9076e3909fa9`는 failed, 연결한 Build execution `b40852bc412d489a95fe5c6f8e028779`는 succeeded다. 기다린 시간 약 15초, page error 0, 추론 source SHA 불변, 소유 supervisor stopped를 확인했다. [최종 진단 화면](../../artifacts/verification/execution-diagnostics-first-frame-20261007-r4/first-frame-diagnosis.png)과 [모바일 현재 단계](../../artifacts/verification/execution-diagnostics-first-frame-20261007-r4/first-frame-mobile-step.png)를 직접 검토했다.

[정상 경로](../../artifacts/verification/execution-diagnostics-first-frame-normal-20261007-r1/result.json)는 88 frames/page error 0/actual capture PASS/추론 source 불변/owned stopped다. 이후 바뀐 것은 실패 관측 화면의 시간 설명이며, 그 최종 화면은 위 r4에서 별도 인수했다. 모델 응답은 명시 fixture이고 App/API/Isaac/PhysX는 실제다. 사진 복원 품질이나 실물 정지 인수로 해석하지 않는다.

초기 sandbox Python 시험은 Windows Temp ACL 때문에 10개에 19 ERROR가 났다. 승인된 동일 로컬 회귀 실행에서 10개 PASS 후 최종 85개를 실행했으며 최초 실행을 제품 실패나 PASS로 바꾸지 않았다. [누락 r1](../../artifacts/verification/execution-diagnostics-first-frame-20261007-r1/result.json)은 주요 오류 연결 뒤 모바일 넘침 검사에서 FAIL했다. r2는 UI PASS지만 주입이 publisher update를 막아 별도 capture가 `viewport_missing`으로 FAIL하므로 GPU 정상 근거가 아니다. 전송 구간만 막도록 시험을 좁힌 r3는 capture도 PASS, 최종 대기 시간 설명을 포함한 r4가 최종 근거다. 이전 결과를 삭제·덮어쓰지 않았다.

이번에는 **backend 첫 current frame 미수신의 대표 제품 인수**를 완료했다. apply 실패·필수/선택적 storage와 다른 cleanup 조합, browser 이미지 HTTP 실패, 병렬/quota/최종 soak 및 사진/library/실제 LLM/실물 인수는 남아 있다. 새 유료·로봇·SSH/serial/센서/모터/배포/설치/commit/push/에이전트 0, 원본·dirty·과거 실패·hash·guard·예약 PAUSED·`whole_demo_ready=false`를 유지한다.

## v336 Isaac 주행 오류와 정리 실패 연결

Run 명령의 수신 성공과 이후 주행 실패를 구분해 기록한다. 인증된 engine snapshot의 오류 전환을 `engine_runtime_observation` 실행으로 저장하고, 근거가 일치하는 원 Run 명령의 실행 ID로 연결했다. 오류 팝업의 `View diagnostics`는 이 관측 실행을 직접 연다. 실패 화면의 현재 단계도 경로 요청 대신 오류 원인 확인을 안내한다.

- 명령 receipt와 진단의 기존 succeeded 결과는 바꾸지 않는다. 후속 관측은 failed이며 최초 `engine_runtime_fault`와 별도 `engine_runtime_cleanup`을 보존한다. 예외 객체 없이 error code만 전달한 `TraceContext.finish(role='cleanup')`에서 role이 사라지던 공통 결함을 수정했다. 정리 실패를 확인된 정지로 표시하지 않는다.
- 실제로 claim한 Run의 engine/epoch/revision과 비교하며, Site SIM은 snapshot의 reusable run_id가 해당 명령의 plan_id와 맞아야 한다. stage invalidation으로 revision이 지워지면 같은 engine/epoch의 직전 인증 snapshot만 사용할 수 있다. 일치하지 않거나 명령 근거가 없으면 오류는 남기되 command 참조를 만들지 않는다. 새 engine/epoch는 이전 연결을 초기화한다.
- `snapshot_execution_id`는 인증된 product state에만 추가했다. native snapshot/envelope/receipt와 v1/v2/hash·제어권·정지 자격은 변경하지 않았다. 끊어진 engine의 옛 snapshot 링크는 제공하지 않으며 정상 snapshot이 오면 현재 오류 링크를 지운다. 실행 ID는 승인 자격이 아니다.
- 같은 오류 상태와 같은 소유 명령의 반복 snapshot은 새 진단을 만들지 않는다. sequence나 예외 문구가 변해도 최초 원인을 덮지 않는다. 이 경로는 bounded 비동기 writer에만 넣으며 flush/파일 저장을 snapshot 경로에서 기다리지 않는다. 선택적 sink 실패는 degraded이고 수락한 snapshot을 취소하거나 매 표본 자동 재시도하지 않는다.
- 진단에는 고정된 SIM 오류 토큰과 허용한 예외 타입만 남긴다. 임의 safety_reason 문장·파일 경로·credential은 복사하지 않고 generic 오류 코드로 남긴다. 시간은 backend에서 이 관측을 기록한 시간이지 전체 주행 시간이나 전송 지연이 아니다. 화면에도 이를 명시했다.

### v336 검증

| 검증 | 결과 |
|---|---|
| 최종 진단 집중 50개 | PASS, 19.313s. 최초/cleanup 구분·명령 성공 보존·반복 억제·다른 revision/epoch·stage invalid·sink 실패·민감정보 제외 포함 |
| 진단과 Bridge/lease/viewport 관련 81개 | PASS, 30.673s. 집중 회귀와 중복 |
| Web 44 files / 355개 | PASS, 23.67s. exact 오류 링크·현재 단계·관측 시간 설명 포함 |
| TypeScript / production build | PASS, 67 modules, JS 586.54 kB. 기존 500 kB 초과 경고 유지 |
| 최종 실제 Chrome/API/Isaac 복합 오류 | PASS, 37 frames, page error 0, 추론 소스 SHA 고정, 시험 소유 supervisor stopped |

[최종 실제 결과](../../artifacts/verification/execution-diagnostics-compound-runtime-20261007-r3/result.json)는 원 Run 응답만 browser에서 유실시키고 실제 owned PhysX 주행 중 pose 조회와 SIM zero-drive 정리를 각각 실패시켰다. 최초 `SIM_TEST_POSE_LOST`와 후속 `SIM_TEST_CLEANUP_FAILED`가 별도 span으로 남고, Run command execution `6f2334cd685d4c65b7d48b30ce157f8f`는 receipt succeeded를 유지한다. 관측 execution `29dfa5a802dd435b9ae2cb43de211a6f`는 failed다. 위치 null/telemetry false/Run 잠금, browser reload와 diagnostics refresh 뒤 동일 관측 ID·오류 실행 1개·Run 1개, popup→정확한 실패 상세→관련 명령→Back 및 인증 export를 확인했다. [최종 화면](../../artifacts/verification/execution-diagnostics-compound-runtime-20261007-r3/compound-runtime-diagnosis.png)을 직접 검토했다. provider 응답만 fixture이고 App/API/Isaac/PhysX는 실제 로컬 실행이다. 이는 실물 zero-drive 실패나 물리 정지 인수가 아니다.

초기 Broker 회귀에서 cleanup role 누락을 재현한 ERROR 1을 수정했다. 관련 시험 첫 실행은 존재하지 않는 `test_bridge_lease` 이름으로 import ERROR가 났으며 57개 묶음을 PASS로 세지 않는다. 실제 `test_bridge_lease_rotation`으로 위 최종 81개를 실행했다. [실제 r1](../../artifacts/verification/execution-diagnostics-compound-runtime-20261007-r1/result.json)은 진단 값 확인을 통과한 뒤 같은 텍스트 두 곳을 선택한 Playwright strict selector 오류로 FAIL했다. 선택 범위를 stage의 strong으로 좁혔다. [r2](../../artifacts/verification/execution-diagnostics-compound-runtime-20261007-r2/result.json)는 36 frames로 PASS지만 이후 현재 단계 안내와 관측 시간 설명을 개선했으므로 r3가 최종 화면 근거다. 중간 Python109/Web354 결과는 당시 소스로 보존하며 최종 수치와 합산하지 않는다. 실제 실패 디렉터리를 지우거나 PASS로 덮지 않았다.

이번에는 후속 SIM 오류의 원인·cleanup·명령 연결과 대표 복합 오류 화면 인수를 완료했다. apply/첫 frame/필수·선택적 storage의 전체 복합 UI 행렬, 두 프로젝트 병렬·quota 경합, launcher monitor/cleanup와 외부 edit/정합 세부, 최종 장시간 비교는 남아 있다. 새 유료·로봇/SSH/serial/센서/모터/배포/설치/commit/push/에이전트는 0이며 원본·dirty·과거 실패·guard·예약 PAUSED·`whole_demo_ready=false`를 유지한다.

## v335 편집 실행 재열기와 Build 오류 수정

저장한 편집과 Undo의 실행 ID를 앱 종료 후에도 복구하도록 연결했다. 실제 인수 중 복구된 생성 참조가 새 Build의 인자와 충돌하는 결함도 재현하고 수정했다. 기존 진단 화면에서 Undo→이전 편집→생성 기록을 탐색할 수 있으며, 저장 후 3D 등록이 실패한 편집도 최초 실패 상태 그대로 찾는다.

- 편집 commit 뒤 프로젝트·원 request/input/source revision·마지막 operation ID·전체 검증 이력 digest·현재 결과 revision에 결속한 불변 sidecar를 저장한다. 원 generation 연결과 별도 identity이며 기존 원본, scene-changes-1.0, v1/v2/native payload와 hash를 다시 쓰지 않는다. 읽기 전에 기존 SceneChangeHistory 전체 replay 검증을 통과해야 한다.
- 편집 trace에는 원 generation과 이전 편집 참조를 남긴다. 새 Build는 자신의 request/command ID와 현재 revision을 우선하고 evidence ID로 원 생성·편집을 보존한다. 복구 참조를 `**refs`와 새 인자로 이중 전달해 발생하던 `TypeError: multiple values for request_id`를 제거했다. 제품 제어권·기능·revision gate는 바꾸지 않았다.
- 필수 history 저장 실패에는 편집 연결을 만들지 않는다. 저장 후 3D 등록 실패에는 commit 근거를 먼저 남겨 재열기 후에도 실패한 registration trace로 연결한다. 선택적 진단 저장 실패는 degraded이며 이미 저장한 편집을 취소하거나 성공으로 덮지 않는다. 같은 프로젝트라도 다른 operation/history/revision, 변조·누락 evidence는 연결하지 않는다.
- 새 sidecar도 기존 4,096개/각 8KiB 및 전체 quota·link/hardlink 검사 범위 안에 둔다. 정상 편집 경로의 bounded flush만 사용하며 모터/watchdog에 flush를 추가하지 않는다. history commit과 진단 sidecar는 단일 트랜잭션이 아니므로 그 사이 프로세스 종료나 quota 실패에는 연결이 없을 수 있다. 과거 sidecar 없는 편집을 소급 추정하거나 실행 자격으로 사용하지 않는다.

### v335 검증

| 검증 | 결과 |
|---|---|
| 최종 실행 진단 집중 46개 | PASS, 15.378s. edit/Undo 재열기, exact history/다른 프로젝트·변조 거절, 저장 후 등록 실패 원인 유지, 선택적 저장 실패, 복구 참조와 새 command 충돌 포함 |
| 최종 진단·scene changes·Bridge·lease·viewport 87개 | PASS, 26.775s. 집중 회귀와 중복 |
| 기존 API/chat/가짜 robot preparation/readiness 205개 | PASS, 118.837s. 마지막 broker 인자 충돌 수정 전 실행. 수정본은 위 46/87 및 아래 실제 인수로 검증 |
| Web 44 files / 353개 | PASS, 30.33s. 제품 Web 소스 변경 없음 |
| TypeScript / production build | PASS, 67 modules, JS 586.17 kB. 기존 500 kB 초과 경고 유지 |
| 실제 Chrome/API/Isaac text r3 | PASS, 114 frames, page error 0, 편집/Undo Build current frame·진단 탐색·종료 후 원본/이력 재열기 및 소유 supervisor 정리 |

[최종 실제 r3 결과](../../artifacts/verification/execution-diagnostics-edit-reopen-20261007-r3/result.json): generation `485a3fdb4f1844d58e55fe2b6b17c497`, 편집 `0492d6fb4be148b5ae3d6aa8ee0c98dd`, Undo `64b7ce1b4f244e88aae2f6ada841f92b`, 편집 후 Build `822bce4bf111417dad05dc3b02b505db`다. Build terminal은 succeeded이며 metadata가 Undo ID·현재 revision과 새 command/request를 함께 갖는 것을 확인했다. 기존 생성/검색/페이지 7개/profile 30행/export/목표 도착·Stop/reload/reset 경로 뒤에 explicit `--diagnostics-edits` 시험을 추가했다. 편집 뒤 새 Run은 없고, 종료한 backend의 실제 저장 파일을 새 ApplicationService/ProductWorkflow로 읽어 동일 Undo ID를 복구했다. 원본과 history bytes 불변, 재열기 acknowledgement 없음, 자동 command/provider dispatch 없음. [편집 원인 진단 화면](../../artifacts/verification/execution-diagnostics-edit-reopen-20261007-r3/execution-edit-origin.png)을 직접 검토했다. 추론 소스 SHA는 전후 동일하다. 외부 LLM 응답만 fixture이며 사진 품질·실물 인수가 아니다.

첫 sandbox 회귀는 Windows 임시 파일 접근/정리 제한으로 실패했다. 권한 검토를 거친 재실행과 위 최종 회귀로 검증했으며 거부된 경로를 우회하거나 시스템 권한을 변경하지 않았다. 중간 집중44/45 및 관련86 PASS는 당시 코드 근거로 보존하며 최종46/87과 합산하지 않는다.

[실제 r1](../../artifacts/verification/execution-diagnostics-edit-reopen-20261007-r1/result.json)은 편집·Undo 저장 후 Build HTTP409에서 실패했다. 저장 snapshot에는 Build permission/준비가 없었고 첫 runner는 구체 error code를 보관하지 않았으므로 세부 원인을 확정하지 않는다. 기존 제어권 heartbeat와 `build_allowed`를 기다리도록 시험을 강화했다. [실제 r2](../../artifacts/verification/execution-diagnostics-edit-reopen-20261007-r2/result.json)는 준비를 통과했지만 HTTP400/request_invalid에서 실패했다. 별도 단일 회귀에서 복구된 `request_id` 중복 TypeError를 재현하고 위 broker merge로 수정했다. 두 실행의 page error는 0, supervisor는 stopped이며 실패 자료를 삭제하거나 PASS로 덮지 않았다.

이번 완료는 편집 origin 영속 복구와 저장/등록/진단 실패의 회귀, 복구 후 Build 결함 수정이다. 모든 복합 실패의 실제 제품 UI 행렬, 다중 프로세스 quota/두 프로젝트 병렬, launcher monitor/cleanup·외부 edit/정합 세부·모든 오류 exact 링크/raw 제한 조회·최종 soak는 남아 있다. 새 유료·로봇/SSH/serial/실센서/모터/배포/설치/commit/push/에이전트 0, 기존 raw/dirty/guard·예약 PAUSED 및 `whole_demo_ready=false` 유지. 정확한 최신 잔여는 하단 상태표를 따른다.

## v334 진단 검색과 이전 실행 탐색

기존 최근 50개 안에서만 상태를 필터하던 목록을 서버 검색과 페이지 조회로 바꿨다. 현재 프로젝트의 execution·request·mission 등 ID, 단계명·오류 코드와 안전한 metadata를 대소문자 구분 없이 부분 검색한다. 입력 중에는 요청하지 않고 `Search executions` 또는 Enter로 제출한다. 상세에서는 근거가 있는 생성·편집·시작 실행 ID로 이동하고 이전 상세로 돌아올 수 있다.

- 기본 50행/최대 100행, 요청당 최대 100개 실행 본문을 검사한다. 일치가 없는 페이지에도 오래된 기록이 남아 있으면 `Older executions`를 활성화한다. 상태 필터는 서버에서 적용한다. 정렬은 UTC 인과관계나 호스트 간 경과 시간이 아니라 manifest 파일 기록 시각과 execution ID의 안정적인 순서다.
- 커서는 첫 페이지 상한과 마지막 검사 위치를 프로젝트·검색어·상태에 묶는다. 동률 시각, 추가 이벤트, 새 기록, 프로세스 재시작과 커서 범위 변경을 회귀로 확인했다. 커서는 조회 위치이지 인증 토큰이 아니며 product session과 현재 프로젝트 권한을 그대로 적용한다. 진행 중인 결과는 조회 사이에 바뀔 수 있고 외부에서 manifest를 변경한 경우까지 불변 snapshot이라고 보장하지 않는다.
- 검색은 manifest·최초 오류·유지된 span metadata만 읽는다. private raw 응답·사진·prompt 전문을 검색하거나 export에 넣지 않는다. bounded timeline에서 이미 제외된 오래된 span의 모든 참조까지 검색한다는 보장은 없다. 임의 파일 경로 조회는 추가하지 않았다.
- 중복·잘못된 query와 다른 프로젝트/검색조건의 cursor는 400, 진단 저장 위치 접근 실패는 503으로 구별한다. 손상·읽을 수 없는 개별 기록은 `unavailable executions`와 degraded로 표시한다. 실패한 조회의 옛 결과를 현재 결과처럼 남기지 않는다. 다른 API와 POST의 기존 URL query 금지 정책은 유지한다.
- 영문 검색창·상태·이전/다음 페이지·관련 실행 버튼을 기존 Diagnostics에 연결했다. 전역 dark input/낮은 대비와 표 최소폭 760px 상속을 진단 화면에 한해 제거하고, 좁은 화면의 결과를 항목별 grid로 표시한다. 정상 채팅 흐름·실물 Stop/guard·원본/v1-v2/hash를 바꾸지 않았다.

### v334 검증

| 검증 | 결과 |
|---|---|
| 최종 실행 진단 집중 41개 | PASS, 13.483s. 검색/커서·동률/재시작·105개 중 첫 100개에 일치가 없는 경우·손상·권한·저장 실패 분류 포함 |
| 관련 Bridge/viewport/launcher 등 91개 | PASS, 25.130s. 집중 회귀와 중복, 후속 저장 실패 분류 추가 전 결과 |
| 기존 API/채팅/로봇 준비/readiness 205개 | PASS, 118.018s. 실제 로봇·유료 모델 호출 0 |
| 최종 Web 44 files / 353 tests | PASS, 23.17s |
| TypeScript / production build | PASS, 67 modules, JS 586.17 kB. 기존 500 kB 초과 경고 유지 |

[최종 실제 r4](../../artifacts/verification/execution-diagnostics-search-20261007-r4/result.json)는 PASS: 실제 Chrome/API/Isaac 106 frames, page error 0, source SHA 고정, 서로 다른 실행 7개 페이지, profile 30행, 목표 도착·Stop/reload/reset·export·종료 후 저장 재열기·소유 supervisor 정리까지 확인했다. generation execution은 `d69489e923e04a4a9d0354f0ef8b2166`, launch execution은 `c394a9983bb44d83acf8a43ca0dbe40a`다. 제출 버튼 enabled 대기 후 Enter 검색으로 실제 일치 행 1개를 확인하고, typed 관련 launch 이동→Back 및 모바일 panel 내부 가로 넘침 검사를 통과했다. [모바일 검색](../../artifacts/verification/execution-diagnostics-search-20261007-r4/execution-search-mobile.png)과 [모바일 결과](../../artifacts/verification/execution-diagnostics-search-20261007-r4/execution-search-mobile-results.png)를 직접 검토했다. 외부 LLM 응답만 fixture이며 실제 생성 품질·사진 복원·실물 인수 근거가 아니다. 새 유료 호출과 로봇 연결은 0이다.

[이전 실제 r2](../../artifacts/verification/execution-diagnostics-search-20261007-r2/result.json)는 93 frames/7개 실행 페이지/버튼 검색·관련 실행 왕복/저장 재열기 PASS다. r3도 91 frames/소스 고정/저장 재열기 PASS지만 keyboard 검색을 초기 loading 전에 보내도 통과하던 시험 조건이 약했다. r4의 강화한 조건으로 최종 검색 인수를 대체했다. 중간 결과는 삭제하거나 최종 소스 근거로 덮어쓰지 않는다.

첫 집중 회귀에서는 기존 API 전체 query 차단, Windows 파일 시각 정밀도를 무시한 시험 fixture 및 잘못된 테스트 helper 인자가 드러났다. Web에서는 기존 same-origin 인증에 대한 잘못된 기대와 테스트 mock의 TypeScript 인자를 고쳤다. 지원하지 않는 image+library runner 조합은 시작 전 거절됐으며 실행 범위를 확대하지 않고 지원하는 text 경로로 확인했다. 이 실패들을 제품 정상/실물 실패나 실제 LLM 성공률로 세지 않는다. 모든 테스트 숫자는 중복이 있어 합산하지 않는다.

검색/페이지와 명시적인 관련 실행 탐색은 이번 증분의 완료 범위다. 모든 임무 오류의 exact 링크, 안전한 원본 evidence 제한 조회, 일반적인 이전·후속 실행 graph, 전체 fault/장시간·두 프로젝트 제품 인수는 계속 잔여다. P1 사진/library/지지·부착, P2 실제 모델 평가, 최종 패키지와 현장 작업을 진단 PASS로 대체하지 않는다. 새 유료/로봇/SSH/serial/배포/설치/commit/push/에이전트 0이며 예약 PAUSED와 `whole_demo_ready=false`를 유지한다.

## v333 재시작·편집·시작 실패 연결

저장 장면을 다시 열어도 원래 생성 실행을 찾고, 편집과 Undo의 실패 단계 및 백엔드 시작 전 실패를 같은 진단 계약으로 조회하도록 연결했다. 새 로깅 서비스·유료 모델 호출·로봇 접속 없이 기존 App/API/core/provider/launcher 경로를 수정했다. 아래 v332 기록은 당시 근거로 보존하며, 최신 잔여는 하단 상태표를 따른다.

### 구현과 실패 구분

- 생성 저장 후 프로젝트·request ID·입력 revision·원본 scene revision에 결속한 작은 불변 `diagnostics/links` sidecar를 기록한다. 재열기 때 원 generation manifest와 revision 근거가 모두 일치해야 Broker에 연결한다. 다른 프로젝트/요청·변조·누락 근거로 임의 연결하지 않는다. 새 sidecar는 원본 프로젝트·v1/v2·plan/scene hash·실물 승인 자격을 바꾸지 않는다. 과거 연결 파일이 없는 기록에 ID를 꾸며 넣지 않는다.
- 새 이벤트는 schema 1.1의 event ID와 component를 갖는다. 기존 1.0 manifest/event 읽기를 유지한다. 최근 8,192개 ID 범위에서 중복을 무시하고 `duplicate_events`와 degraded를 표시한다. 최초 오류의 단계/span을 별도로 보존하며 중복 성공 이벤트로 실패를 덮지 않는다. 이는 무한 기간의 중복 제거 보장은 아니다.
- scene-edit proposal 검증·preview·apply·Undo를 기록한다. `scene_edit_validate_and_save` 실패는 저장 전 실패이며, `scene_edit_register_review` 실패는 편집은 저장됐지만 3D 검토 등록이 안 된 상태다. 후자는 이전 review 자격을 무효화하고 재열기를 요구한다. 최초 원인과 원본 저장 파일을 보존한다. 외부 편집 LLM 호출 전체를 이번에 새로 계측한 것은 아니다.
- launcher의 backend/engine 준비 대기를 기록하고 launch execution을 이후 backend 실행에 전달한다. 검증 실패로 backend가 생성되지 않으면 `artifacts/launcher-diagnostics`의 별도 파일과 실행 ID를 CLI 오류에 제공한다. 잘못된 시작 설정에서는 runtime state·child process를 만들지 않는 기존 규칙을 유지한다. launcher 성공은 시작 준비 완료이지 앱 종료·임무·실물 성공이 아니다.
- sidecar 연결도 기존 전체 저장 상한에 포함하며 최대 4,096개/각 8 KiB로 제한한다. link/junction/다중 hardlink·형식/identity 검사를 적용한다. 선택적 진단 저장 실패는 degraded이고 기존 필수 비용 audit·안전 journal의 fail-closed 정책은 그대로다. launcher와 backend의 다중 프로세스 동시 quota 경합을 검증한 결과는 아니다.

편집 후 실행은 살아 있는 Broker에서 `scene_edit_execution_id`까지 연결한다. 프로세스 재시작 후에는 원 generation과 현재 편집 revision이 복구되지만 이전 편집 실행 ID의 영속 복구는 잔여다. backend 이전 fallback 파일은 경로를 제공하며 App 목록에 자동 import하지 않는다.

### 검증

| 검증 | 결과 |
|---|---|
| 최종 실행 진단 집중 36개 | PASS, 10.173s. 1.0 재열기·새 event 계약·중복 실패 보존·exact generation 복구·quota·edit/Undo·저장/등록 실패 구분 포함 |
| 관련 core/provider/Bridge/viewport/startup/process manager 등 163개 | PASS, 54.182s. 집중 회귀와 중복 포함 |
| 채팅·텍스트 생성·로봇 준비/readiness·모델 library 187개 | PASS, 104.846s. 외부 adapter는 가짜이고 새 유료·로봇 접속 0 |
| 최종 Web 44 files / 348 tests | PASS, 23.35s |
| TypeScript / Vite production build | PASS, 67 modules, JS 583.59 kB. 기존 500 kB 초과 bundle 경고 유지 |
| 실제 Chrome/API/Isaac 최종 text r9 | PASS, 100 frames, page error 0, source SHA 고정, profile 30행, 저장 재열기 PASS, owned supervisor stopped |

[최종 r9 결과](../../artifacts/verification/execution-diagnostics-restart-20261007-r9/result.json)의 generation execution은 `3f7f3a3a2ad340278ffee75d537842a0`, launch execution은 `c25d3f73a6a94ae8aadadbc366bc73eb`다. 실제 browser 검증에서 launch root→generation metadata 연결과 schema 1.1 event ID/component를 확인했다. 목표 도착·Stop/reload/reset·진단 조회/export·모바일·종료 후 원본 저장 재열기를 검사했다. [모바일 화면](../../artifacts/verification/execution-diagnostics-restart-20261007-r9/execution-diagnostics-mobile.png)을 직접 확인했다. 외부 LLM 응답만 fixture이고 App/API/Isaac/PhysX는 실제 로컬 runtime이다. 새 유료·로봇 접속은 각각 0이다. r8의 앞선 실제 PASS도 별도 디렉터리에 보존했다.

검증 중 존재하지 않는 테스트 모듈 두 개(`test_chat_reliability`, `test_parametric_model_library`)를 지정해 import ERROR가 났다. 해당 132개 실행 묶음을 PASS로 표시하지 않는다. 실제 `test_agent_reliability`는 위 163개, `test_model_library`와 채팅 관련 파일은 위 187개 묶음에서 통과했다. 후자의 첫 실행은 Windows sandbox 임시 파일 쓰기/정리 거절로 실패했으며 권한 검토를 거친 오프라인 재실행에서 통과했다. 접근 거절된 무관한 pytest cache는 읽거나 변경하지 않았다. 중간 실패 원본·기존 dirty 변경·과거 raw 및 실물 잠금은 보존했다. 숫자는 중복이 있어 고유 테스트 총수로 합산하지 않는다.

## v332 완료 범위

성공·실패 기록을 실행 ID로 묶고, 최초 실패·재수정·후속 cleanup을 분리하며, 단계 시간과 제한적 함수 프로파일을 기존 App에서 읽는 기능을 구현했다. 외부 로깅 서비스나 구독은 추가하지 않았다. [승인된 전체 계획](../planning/TWINPULSE_EXECUTION_DIAGNOSTICS_AND_DEMO_SOL_PLAN_2026-10-07.md)의 첫 구현 증분이며 O0~O5 전체 또는 사진·실물 데모 완료를 뜻하지 않는다.

이번 검증은 새 유료 추론 0, 로봇/SSH/serial/배포/실센서/모터 0이다. 설치·시스템 설정·commit/push·새 에이전트도 없다. 기존 dirty 변경과 원본·과거 실패·strict v1/v2·hash·정지/센서 신선도/실물 승인 제한을 유지했다. 자동 예약은 재개하지 않았다.

## 실제 연결한 경로

| 경로 | 구현과 확인 | 의미의 한계 |
|---|---|---|
| 채팅 → ProductWorkflow → application → provider → 검증 → 저장 | workflow/operation/chat request/generation과 execution 연결, 명시 context를 worker에 전달 | 생성 결과 품질은 별도 평가이며 fixture 성공을 실제 LLM 성공률로 쓰지 않음 |
| Nebius observer/planner/validation/repair 및 OpenAI Responses | attempt 선기록, 단계 span, raw evidence/usage/원응답·저장응답 hash 참조, timeout 이후 late evidence 보존 | 실제 HTTP 전 기록은 admitted_not_proven_sent. timeout·프로세스 단절은 외부 결과 unknown일 수 있음 |
| Broker → Bridge → Isaac adapter → receipt → current frame | 중복 요청은 같은 실행, 같은 plan의 새 Run은 별도 실행. queue/engine-local execute/receipt queue/첫 검증된 current frame 구분 | receipt 성공은 명령 수신·처리 근거이지 임무 완료나 실물 정지 PASS가 아님 |
| 읽기 전용 로봇 준비 및 stationary 수집 | 대화 workflow를 보존한 별도 실행, 실패·센서 gap·unknown 원인 연결 | 이번에는 가짜 adapter로만 검증. 수집 성공은 좌표 정합·이동 허용이 아님 |
| physical controller / automatic mission / GoalTaskLoop | 기존 boot/release/session/mission/task/leg 참조, leg 분리, 최초 실패와 cleanup/storage 실패 구분 | 기존 raw 프로토콜·journal은 그대로. 새 실물 인수 없음 |
| App Diagnostics / 인증 API / export | 서버 metadata/상태 검색·페이지·명시 관련 실행 왕복·상세·프로파일·안전한 JSON 다운로드. 생성 오류는 해당 실행으로 직접 이동 | 모든 mission 오류의 직접 ID 링크·원본 참조 제한 조회·전체 이전/후속 graph는 아직 없음 |

로봇·제어 admission의 선택적 진단 manifest는 비동기 큐로 전달하고 제어 경로에서 fsync를 기다리지 않는다. 기존 필수 임무 기록·비용 ledger·안전 근거의 fail-closed 정책은 약화하지 않았다. provider dispatch의 필수 audit 저장 실패는 실제 HTTP 전에 차단한다.

## 사용 방법

기존 App/Isaac을 다음 정상 실행 때 다시 시작하면 새 Python 코드와 빌드가 로드된다. 사용자 실행 중인 App을 임의 종료하지 않았다.

1. App 상단 `Diagnostics`를 연다. ID·단계·오류 코드를 검색하거나 상태를 고른다. `Older executions`/`Newer executions`로 이동하고 execution ID를 선택한다. Refresh는 첫 페이지로 돌아간다.
2. `Stage timeline`에서 최초 오류·실패 단계·관련 attempt/command/mission/task ID를 본다. 재수정 성공이어도 최초 실패 기록은 남는다.
3. `Function profile`이 있을 때만 함수 호출 수·self/cumulative time을 확인한다. 기본은 OFF이며 backend의 명시 `--profile-generation`으로 기존 순수 compile/validation 호출만 측정한다. launcher에 프로파일 선택 UI를 추가한 것은 아니다.
4. `Export redacted diagnostics`로 해당 실행의 제한·민감정보 제거 JSON과 export hash를 저장한다. 사진과 private raw 응답은 포함하지 않는다.

조회·Refresh·Export는 모델 호출/Build/Run/로봇 접속을 시작하지 않는다. 생성 오류의 `View diagnostics`는 해당 실패 execution을 연다. 상세 새로고침 실패 시 이전 상세를 숨긴다. 저장 오류·유실·깨진 이벤트·누락 chunk와 조회 상한에 의한 timeline 잘림을 영문으로 알린다.

## 저장·보안·시간 계약

- 프로젝트 데이터 root의 `diagnostics/<execution_id>/manifest.json` 및 `events*.jsonl`에 sidecar를 둔다. generation manifest와 provider dispatch intent는 dispatch 전에 flush/fsync한다. 새 sidecar 필드는 canonical plan/scene/native payload의 hash에 삽입하지 않는다.
- 명시 `TraceContext`를 thread/worker에 전달한다. 전역 current execution을 두지 않는다. 진단 ID는 추적용이고 product 인증·프로젝트 접근·boot/release/정지 자격을 대신하지 않는다.
- bounded queue 1,024개와 terminal 예비 16개, 이벤트 최대 8 KiB, 기본 chunk 8 MiB/실행 64 MiB/전체 512 MiB다. 상한에 도달하면 자동으로 raw나 과거 기록을 삭제하지 않고 유실·degraded를 표시한다. 단일 writer와 bounded read를 사용한다.
- 실행 재시작 후 종료 근거가 없는 기록은 unknown이다. 최종 결과를 late 응답으로 성공으로 바꾸거나 장면 적용·재호출하지 않는다. writer 오류는 terminal health에도 보존한다. 최초 primary 실패와 cleanup 실패를 따로 남긴다.
- credential·사진 bytes·prompt 전문·환경변수·자유로운 exception 전문·개인 경로를 새 event/export에 복사하지 않는다. scalar allowlist와 크기 제한, root/ID/link/형식 검사를 적용한다. 기존 제한/redaction 원본 audit와 별개로 원응답 hash와 실제 저장 문자열 hash를 구별한다.
- UTC는 표시/정렬, monotonic 기간은 같은 process clock에서만 계산한다. engine의 queue/execute/receipt elapsed는 engine-local 측정값임을 표시한다. PC↔engine↔robot 시각을 빼서 네트워크 지연이나 CPU 비율로 표시하지 않는다. 각 병렬 span을 합산하여 전체 시간이라고 하지 않는다.
- cProfile은 명시 opt-in, 최대 30개 함수 행, 경로 제거, timer_basis 표시다. locals/args/binary profile은 수집하지 않는다. 로봇 watchdog/고주파 제어 loop에는 장착하지 않았다.

## 회귀와 실제 제품 인수

아래 실행들은 겹치는 테스트가 있으므로 숫자를 합쳐 고유 테스트 총수라고 하지 않는다.

| 검증 | 결과 |
|---|---|
| 새 실행 진단 집중 회귀 30개 | PASS. 실제 소유 테스트 child가 dispatch/read 중 자체 종료한 뒤 manifest/audit가 남고 unknown으로 재열림. 실제 네트워크 0·자동 재호출 0 |
| 관련 core/provider/Bridge/viewport/Loop/chat 회귀 99개 | PASS |
| robot 준비/readiness/mission/physical 관련 회귀 187개 | PASS. 가짜 adapter, 실물 아님 |
| 최종 correlation 변경 후 mission/preparation/readiness/chat 회귀 146개 | PASS |
| 최종 Web 44 files / 348 tests | PASS. 같은 execution refresh 실패·잘린 timeline 회귀 포함 |
| TypeScript / Vite production build | PASS. 67 modules, JS 583.53 kB. 기존 500 kB 초과 bundle 경고는 남음 |

집중 회귀는 `tests/integration/test_execution_diagnostics.py`의 ExecutionStoreTests, ProviderTraceTests, DiagnosticsProductTests, BrokerTraceTests, MissionTraceTests로 실행했다. provider transport/pipeline은 가짜 HTTP/응답이지만 실제 production class 경로를 사용했다. 인증 부재·engine/bootstrap 역할·다른 프로젝트 실행 접근 거절, raw/hash 보존, optional 저장 실패·quota·malformed·chunk 회전, late 정산·terminal 불변을 확인했다.

실제 Chrome/API/Isaac 인수는 기존 `scripts/verify_chat_sim_journey.py`의 `--site-transport-fixture --library-models --diagnostics`를 사용했다. 외부 모델 응답만 명시 fixture이며, 저장·App·API·Isaac render·PhysX 이동·Stop은 실제 로컬 runtime이다.

- [text r2 결과](../../artifacts/verification/execution-diagnostics-text-20261007-r2/result.json): 생성·저장·Build·목표 도착·Stop/reload/reset·진단/profile/export·저장 재열기 PASS. 중간 소스의 근거이며 최종 소스 인수를 대신하지 않는다.
- [image r5 결과](../../artifacts/verification/execution-diagnostics-image-20261007-r5/result.json): observer→초기 invalid plan→기존 단일 repair→저장→실제 Isaac 88 frames·목표 도착·Stop/reload/reset·진단/profile/export·모바일·종료 후 재열기 PASS. 최초 validation 실패가 최종 성공 이후에도 보존됨. fixture는 사진 인식/방 복원 품질의 근거가 아니다.
- [text r6 결과](../../artifacts/verification/execution-diagnostics-text-20261007-r6/result.json): 최종 Python 연결 코드·직전 UI의 actual Chrome/API/Isaac 110 frames, source 고정, profile 30 thread_cpu rows, export raw=false/physical_authority=false, 저장 재열기 및 소유 프로세스 정리 PASS.
- [최종 text r7 결과](../../artifacts/verification/execution-diagnostics-text-20261007-r7/result.json): 새로고침/잘림 표시까지 포함한 최종 빌드로 실제 Chrome/API/Isaac 81 frames·목표 도착·Stop/reload/reset·진단/profile/export·모바일·저장 재열기 PASS. 개별 run의 소스 SHA와 Web fingerprint는 각 result.json에 보존한다.

측정 예시(text r6)는 Build root 0.906s, backend queue 0.031s, claim→receipt 대기 0.875s, engine-local Kit queue 0.016s/adapter execute 0.859s/receipt queue 0s, receipt 이후 첫 current frame 0.375s다. frame 대기는 root receipt 완료 이후의 별도 span이며 Build root 시간에 포함된다고 하지 않는다. 이것은 한 샘플이고 일반 성능 보장이나 실물/무선 지연 측정이 아니다.

[실제 데스크톱 진단 화면](../../artifacts/verification/execution-diagnostics-text-20261007-r6/execution-diagnostics.png), [모바일 진단 화면](../../artifacts/verification/execution-diagnostics-image-20261007-r5/execution-diagnostics-mobile.png), [실제 JSON export](../../artifacts/verification/execution-diagnostics-text-20261007-r6/execution-export.json). 모바일 화면은 직접 이미지로 확인했으며 bounded panel 스크롤·영문 표시를 확인했다. 이 파일 링크가 Codex 모바일에서 항상 열린다는 보장은 하지 않는다.

### 측정 자체의 부담

같은 순수 계산 `sum(i*i for i in range(20000))`을 조건별 16회 비교했다. tracemalloc을 켠 작은 probe이며 Isaac이 동시에 실행되어 일반 제품 벤치마크로 쓰지 않는다. 평균: logger OFF 0.01332s, logger ON 0.01433s, opt-in profiler ON 0.03058s. 출력 동일, trace 307 events/128,005 bytes, tracemalloc peak 413,688 bytes, degraded/storage/drop 0. 이 조건에서는 trace 약 1ms, profiler 약 2.3배 부담이 있었다. 프로파일을 기본으로 켜지 않는 이유이며 모터 loop overhead나 장시간 전체 App 자원 상한을 검증한 결과가 아니다.

### 보존한 실패와 수정

text r1은 검증 runner가 backend 시작 후 diagnostics 환경을 지정해 profile이 없었다. 환경을 시작 전에 지정했다. image r3/r4는 통제 invalid plan을 넣었는데 fixture repair=0 또는 짧은 fixture deadline 때문에 기존 repair가 실행되지 않았다. 시험 fixture만 repair1/20s로 명시했다. 제품의 기존 repair/timeout/안전 제한은 바꾸지 않았다. 결과 디렉터리를 삭제하거나 PASS로 덮어쓰지 않았다.

초기 `.revision` 접근 오류는 실제 SiteDraft 구조 경로로 수정했고, Bridge timing 시험 fixture의 command_id 누락 및 테스트 import/PYTHONPATH 선택 오류도 수정했다. sandbox의 임시 디렉터리/Vite 실행 거절은 승인된 오프라인 검증으로 수행했으며 거부를 우회하지 않았다. 새로운 trace가 최초 실패를 덮어쓰지 않는 회귀를 포함했다.

## 전체 계획 상태와 남은 우선순위

| 단계 | 현재 상태 | 정확한 잔여 |
|---|---|---|
| O0 현재 경로·기록 기준 | 이번 증분 기준 확인 | 다음 변경의 source/기록 기준도 계속 갱신 |
| O1 실행 store·audit | event 1.1·legacy 읽기·generation 및 exact history 편집 origin 영속 복구 PASS, 전체 PARTIAL | 다중 프로세스 quota/복구 경합 및 두 프로젝트 병렬 제품 인수. commit/선택적 sidecar 사이 단절은 근거 없음으로 보존 |
| O2 모든 제품 경로 correlation | launcher admission·edit/Undo·후속 SIM primary/cleanup·첫 current frame·apply 및 저장 최초 오류 연결 PASS, 전체 PARTIAL | launcher 이후 monitor/stop/cleanup, 외부 편집 LLM transport, survey/localization 세부 계산·remote input/ACK 및 모든 분기 연결 |
| O3 단계·함수 측정 | 제한적 순수 compile/validation 프로파일 PASS | 전체 센서/정합/전송 병목이 측정됐다는 뜻 아님. 미계측 세부 단계는 unavailable |
| O4 Diagnostics·export | 검색/상태/페이지·관련 실행·SIM/첫 frame/apply/생성 저장 exact 링크·조회/export와 선택적 sink 누락 경고 PASS, 전체 PARTIAL | 나머지 임무 오류 exact ID 링크, 안전한 raw evidence 제한 조회, 일반 이전/후속 실행 graph |
| O5 통합 인수 | 실제 text/image SIM·edit/Undo/Build/frame/재열기·위치 상실+cleanup 실패+Run 응답 유실·첫 frame/apply 경계/필수 생성 및 선택적 진단 저장 대표 UI PASS, 전체 PARTIAL | 중간 USD rollback 및 나머지 cleanup/저장 경계 조합·browser 이미지 HTTP 실패, 두 프로젝트 병렬 인수, 최종 소스 장시간 resource/Loop 비교 |
| P1 사진·library·관계 | 아직 이번 증분에서 시작하지 않음 | compact-photo 옛 fixed-size 출력→새 치수/library, floor/support/attachment 및 사진 의미 검사 연결 |
| P2 실제 모델 평가·기본 정책 | 이번 새 호출 0 | 진단 의존성 통과 후 기존 승인/ledger 재확인, 실제 품질·repair 성공률 평가. fixture 결과 제외 |
| P3/P4·F0/F1 | 기존 PARTIAL 유지 | 채팅/편집 잔여·현재 코드 패키지/F0 준비 후 현장 승인된 F1. 지금 전원만 켜면 전체 데모 완료라는 보장 없음 |

다음 작업은 위 O1/O2의 정확한 잔여와 O4/O5 제품 인수다. 이번에 검증한 원 generation 복구·launcher admission·기본 edit/Undo를 다시 미구현 목록에 넣지 않는다. 범용 APM/새 구독을 더하지 않는다. 그 이후 사진/library/관계와 실제 LLM 평가를 진행한다. H5-H6/C3-C6 PARTIAL 및 `whole_demo_ready=false`를 유지한다. 과거 ledger109/219·남은110은 이번 재조회 값이 아니며 새 유료 실행 전에 다시 확인한다.

## v332 최종 확인

최종 집중 Python 30개(9.415s), Web 348개(23.36s), TypeScript/build, 실제 text r7 제품 인수 PASS. r7 생성 execution `9194aed68b0542e392a322b1d289dfa5`, profile 30행/thread_cpu, page error 0, 추론 소스 start/end 동일, 실제 81 frames, 종료 후 저장 재열기 PASS, supervisor stopped. 유료/로봇 연결 모두 0이다. [최종 실제 화면](../../artifacts/verification/execution-diagnostics-text-20261007-r7/execution-diagnostics.png)을 직접 확인했다. O1/O2/O4/O5의 위 잔여 및 사진/실물 미검증은 그대로이며 전체 완료로 승격하지 않는다.
