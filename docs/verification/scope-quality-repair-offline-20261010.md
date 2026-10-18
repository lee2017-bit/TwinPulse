# Host 검증 수정 범위·관측 품질 수정 루프

2026-10-10 KST · Baseline v1.0.385 · 실행 ID `scope-quality-offline-20261010` · 전체 PARTIAL / whole=false.

## 결과

기존 BudgetedPipeline의 최종 수정 경로에 `request_scope`와 관측 배치 품질 수정 루프를 연결했다. 새 에이전트/우회 생성기/제품 fixture fallback은 없다. 실제 LLM, 현재 Isaac 렌더 critic, 실물 인수는 이번 검증 대상이 아니다. 로봇·SSH·serial·센서·모터·배포·외부 LLM 호출·사진 전송·설치·commit/push 모두 0이다.

## 제품 흐름과 보호 조건

1. compiler 실패의 실제 ID·의존 closure를 모델에 전달한다. 다른 물체가 필요하면 host가 제시한 `packing_neighbor` 또는 라이브러리 호환 `support_alternative`만 `request_scope`로 제안할 수 있다. 현재 실패 후보의 revision/anchor/reason을 검증하고 관련 parent/child closure를 넓힌다. 자유 문장으로 방 전체를 해제하지 않는다.
2. 범위 제안과 실제 patch는 **한 응답에서 원자적으로 검증**한다. 별도 모델 승인 요청을 추가하지 않으므로 동일 request/repair/time/financial owner 예산을 쓴다. 범위 metadata만 보내면 NO_CHANGE, 중복 제안·임의 anchor·stale revision·범위 밖 실제 수정은 거절한다.
3. 원본 후보를 바꾸지 않는 복사본에 patch를 적용하고 기존 전체 compiler의 8개 phase를 다시 실행한다. 범위 확대도 명시 치수·관측 source·이미 저장된 장면의 편집 권한을 해제하지 않는다. 지원하지 않는 범위는 보수적으로 거절하며 전체 packing 해의 존재를 보장하지 않는다.
4. 기하가 통과했어도 현재 관측의 높은 신뢰도 좌우/전후/region 모순이 있으면 수정 대상으로 넘긴다. 이 루프도 같은 repair 예산을 쓰고 수정 뒤 전체 기하/관측 관계를 다시 검사한다. 상대 순서 침범량은 **추정 좌표의 진전 지표**이지 실측 정확도 증거가 아니다. 낮은 신뢰도는 불확실로 남기며 억지 정답을 만들지 않는다.
5. geometry/quality high-water·seen/history·quality best/review·scope decision과 protocol revision을 checkpoint에 저장한다. 정체/악화 후보는 성공으로 게시하지 않고 best를 보존/복원한다. 품질 best 복원 뒤 geometry ledger를 해당 revision으로 다시 결속한다. 실패 branch/patch/counters도 남긴다.
6. 명시 재개는 이전 호출·수정·비진전·active time·관측·검사 이력을 이어받는다. 출력 잘림은 즉시 중단하며 geometry 실패로 재분류하거나 추가 수정 호출을 하지 않는다. 성공 후보가 있더라도 current-render 비교/지지 사진 검증/실측이 없으면 `photo_quality=uncertain`이다.
7. 일반 App DTO는 안전한 ID·정해진 범위 사유만 공개한다. 채팅은 현재 품질 수정과 중단 상태를 구별하고 상세에 host 승인 관련 물체를 표시한다. 새 사용자 선택/반복 승인 UI를 추가하지 않았다.

## 회귀 근거

| 검사 | 결과 | 해석 |
| --- | --- | --- |
| 신규 `test_scope_quality_loop.py` | 14 PASS | 실제 GenerationService/BudgetedPipeline + 명시 고정 transport, 외부 모델 0 |
| Provider 전체 | 292 PASS / 6.332초 | 기존 계약·budget·resume 포함; 신규 14개와 겹침 |
| Core 전체 | 302 PASS / 26.396초 | 기존 library/placement/명시 치수 guard |
| 관련 App 통합 9 modules | 270 PASS / 162.413초 | conversation/approval/diagnostics/ownership/photo/site generation |
| Web 전체 | 47 files / 441 PASS / 24.08초 | jsdom 회귀; 현재 3D 렌더 검증 아님 |
| 마지막 UI 문구 회귀 | ChatWorkspace 31 PASS | 위 441개와 겹침; 진행/중단 구분 변경 뒤 재확인 |
| TypeScript / Vite build | PASS | canvas 미구현 test 경고와 500kB bundle 경고는 남음 |
| 기존 v382 원본 감사 | AUDIT_PASS_NOT_GENERATION_PASS | 실제 과거 생성 FAIL / 6 of10 / 미사용4 / USD.01188129 / UNKNOWN0 / pending0 / originals unchanged |

App 명령: `python -m unittest tests.integration.test_chat_conversation tests.integration.test_generation_approval tests.integration.test_execution_diagnostics tests.integration.test_s2b_generation_ownership tests.integration.test_photo_nominal_product tests.integration.test_photo_conflict_product tests.integration.test_chat_site_text_generation tests.integration.test_site_furniture_generation tests.integration.test_live_photo_product_audit`.

핵심 양성/음성: 현재 support packing 실패→다른 desk 지지면 scope 확대→동일 응답 patch→전체 PASS(고정3 요청/repair1), 좌우 모순→patch→전체 재검사(고정4/repair1), room 추정 변경의 수치 진전→다음 수정(고정5/repair2), 무관 치수 변경 정체→2회 보호중단/best복원, 품질 patch가 기하 악화→compiler 실패/미공개/복원, length에서 1회 즉시중단, 신규 승인 재개 시 observer/structure 재송신0·추가수정1·cumulative requests5/repairs2·원checkpoint불변, 임의/중복 범위·source rewrite·명시 치수 변경 거절, 안전한 공개 DTO/UI.

## 최초 실패와 수정 이력

- test에 TestCase 자체를 import해 기존 18개가 중복 수집됐다. module alias로 정정했다. 최종 신규 수는 14개이며 초기 24개를 신규 검증으로 합산하지 않는다.
- checkpoint state만 DRAFT→READY로 바뀌는 정상 차이를 후보 차이로 세던 기대를 geometry revision 비교로 정정했다.
- support fixture의 desk depth1.6m가 기존 library 최대1.5m를 위반해 의도한 support 검사에 도달하지 못했다. fixture를1.4m로 정정했으며 제품 library 제한을 풀지 않았다.
- continuation fixture가 검증된 모델 가격/context를 누락해 송신 전에 차단됐다. 명시 `fixture-not-live` 가격을 시험에 제공했다. 제품은 가격을 자동 추정/보완하지 않는다. 명시 치수 위반의 실제 ValueError를 기대하도록 test도 정정했다.
- 제품 검토 중 품질 patch의 provider/evidence 실패가 compiler except에 잡힐 경계를 발견해 `compiling` 경계로 분리했다. 실제 품질 repair의 length 회귀는 원인 유지/즉시중단을 확인했다. best 복원에 따른 ledger revision도 로컬 재검사로 일치시켰다.

## G0–G6 / 정확한 잔여

- G0/G1/G4: 기존 기록 범위 통과 유지 + 이번 관련 회귀 통과. 모든 미지 결함 또는 제품 전체 인수 완료는 아니다.
- G2: graph 밖 host-검증 scope wire와 listed 반복/진전/복원/재개 인수 완료. 현재 eligible 범위는 packing 인접 물체·library 지지 대안이다. 복합 packing/domain의 실제 모델 장기 탐색은 미검증이므로 넓은 G2 범위는 PARTIAL.
- G3: **현재 observer 관계→품질 patch→전체 기하 재검사→단계 DTO/UI**는 구현/고정 응답 회귀 통과. **현재 3D render→사진 critic→품질 patch→실제 Build/재렌더 재검사**는 미구현/NOT_RUN. 지지 사진 충실도·가림·형상 식별성·실측도 PASS가 아니다.
- G5: 이번 revision의 실제 저장 실패 회복/새 자연 생성 NOT_RUN. 기존 v3826/10·별도v3819/10 장부·수정/terminal·시간을 초기화하거나 합치지 않았다. fixture 승인/소비는 새 실제 호출 권한이 아니다.
- G6: v384 텍스트 fixture의 실제 Isaac/PhysX/Stop/재열기 근거 유지. 이번 사진 관측 수정 후보의 실제 Isaac 품질 인수는 NOT_RUN이며 기존 PASS로 대체하지 않는다.

다음 순서: current-render critic의 입력 identity/품질 항목을 기존 Viewport/Build에 연결하고 동일 budget의 수정 뒤 저장/Build/재렌더를 재결속 → 해당 루프 오프라인 양성/음성/실제 Isaac 인수 → 유효한 별도 승인·공통 예산의 actual LLM 회복 및 새 자연 생성. 이 잔여는 로봇을 켜야 시작할 작업이 아니다. 원 12단계 데모·도메인·패키지·규정·실물 잔여는 유지한다.
