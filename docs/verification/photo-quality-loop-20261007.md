# 사진 품질·수정 루프 검사 — 2026-10-07

## v322 — 명시 동의 후 실제 6회 검사 완료

사용자가 원본 침실 사진을 외부 Nebius Gemma/Nemotron에 전송하는 구체적 질문에 **“응 동의해”**라고 답한 후 같은 계획의 실제 검사를 실행했다. 이전 거절을 우회한 것이 아니라 새 동의에 근거한 실행이다. **검사 절차 완료, 제품 사진 fidelity 루프는 여전히 FAIL**이며 원래 결과를 성공으로 바꾸지 않았다.

실제 결과: `artifacts/agent-reliability-20261007/photo-quality-loop-r1/result.json`; 원본 SHA `0d3fbb699b740ce5818db0d301181932d5bf08707cba2b46bbb6461ebee06029`. 추가 관계 분석은 같은 폴더 `post-run-analysis.json`에 별도로 저장했다. Live 원본/result/실패 응답은 수정하지 않았다.

| 시험 | 신규 실제 호출 | 결과 |
|---|---:|---|
| 새 Nano 계획 + 기존 자동 repair1 | 2 | 최초8000토큰/length로 잘림. 재수정은 완전JSON/stop이나4×5m에서 `bedding_overhang/front_left` REGION_FULL. 생성 FAIL/50.485s |
| 통제 region 오류 → 기존 자동 repair1 | 1 | 실제 Nano가 형식 오류를 수정하고 계약 검증 PASS/14.812s. 사진 위치·지지 FAIL; 의도적 fault이며 자연발생 모델 성공률에 섞지 않음 |
| 원본 사진 + 기존 geometry의 Gemma 재판정 | 1 | `accept_estimated`이나 local geometry에는 좌우·지지 오류가 있음. 잘못된 수용/12.735s |
| 구체 geometry 오류 + 후보 + 판정 → Nano 수정 | 1 | 계약 검증 PASS/14.328s, 침대·책상 좌우는 수정. 지지3FAIL/10×12m 추정 유지. **외부 평가 피드백**이지 제품 자동 품질 루프가 아님 |
| 수정된 geometry + 원본 사진 Gemma 재판정 | 1 | 지지 문제를 일부 언급하지만 다시 `accept_estimated`/54.063s. 수학적 관계 FAIL이므로 제품 PASS로 인정하지 않음 |

공유 **53→59/60** 요청, 신규 추정USD**.00730658**, 기존 불명예약 포함 전체USD**.10468336**/청구 미확인, pending0. 사용자 최대10 및 이 묶음 최대7 이하. 4 Nano +2 Gemma 호출이다. 기존 원본의 실제 Gemma observer 응답은 동일 사진/prompt/schema/raw를 검증해 재사용했으며 새 관측 호출/재시도라고 세지 않는다. 독립 Gemma 판정2회에는 승인한 원본 사진을 실제 전송했다. 1회 예산이 남았어도 같은 지지 불가능 요청을 반복하지 않고 종료했다.

### 수정 전후와 후방 landmark 추가 감사

- 침대 XY `[-3.3,4] → [3.3,4]`: 좌우 오류 수정.
- 책상 XY `[3.3,-4] → [-3.3,-4]`: 좌우는 수정됐으나 사진의 좌후방과 달리 **앞쪽**이다.
- 옷장상자 바닥0/옷장상면1.9m, monitor·소품 XY는 책상 밖: 지지3개는 모두 FAIL 유지.
- 방10×12m/120㎡ 유지. 실제 치수는 실측 없음으로 계속 UNVERIFIED; 수치 정답을 단정하지 않는다.
- 최초 oracle는 좌우/지지만 검사했다. ‘좌우를 고쳤다’가 ‘가구 위치를 완성했다’로 오인되지 않도록 **완료 뒤 책상/옷장의 확실한 후방 y>0 landmark 검사를 추가**해 저장 geometry를 재분석했다. 이 새 규칙은 당시 모델 피드백에 포함됐다고 주장하지 않는다. 6→4개 위치·지지 이슈; 침대 깊이/가림 구조의 정답은 만들지 않는다. 실제 원본 report의 당시5→3 이슈는 변경하지 않았다.

### 최종 근거·한계

제품 provider/core 소스6개/과거 project/raw SHA 전후 동일. 새 raw6개를 **UTF-8 명시**로 재읽어 원본 responseSHA/byte count와 모두 대조했고 ledger status/finished6개 일치. 임시 분석 명령의 기본CP949 읽기에서 발생한 가짜 해시 불일치는 UTF-8 재검사로 배제했으며 audit 원본을 수정하지 않았다. 새 provider 전체**65개 PASS/.915s**, 신규 평가 회귀8개 포함; 새 Python compile 및 별도 whitespace 검사. 이번 제품 변경0이므로 이전 core302 PASS는 보존 근거이며 이번 재실행으로 주장하지 않는다.

Gemma 수용2/2는 **이 두 P01 후보의 false positive**이며 일반 모델 정확도 추정이 아니다. JSON/24슬롯 검증과 ‘사진과 닮았는지’ 판정은 별개다. 관계/높이 없는 현 compiler는 지지 오류를 수정할 수 없고, 모델만의 accept는 수학적 FAIL을 덮을 수 없다. 형식 repair는 실제로 작동하지만 작은 방의 배치 실패를 해결하지 못한 표본도 확인됐다.

품질까지 통과한 새 후보가 없어 이번 Isaac/Browser/실물 인수는 실행하지 않았다. 제품 auto fidelity gate/관계 compiler/기본채택/넓은 반복 인수는 미완료이며 whole ready=false. 로봇/SSH/배포/센서/모터/설치/commit/push/새 agent0. 기존 v1/v2/원본/실패/정지·freshness·실물 잠금/dirty 보존.

다음 구현 우선순위는 **부모·지지면·부착 및 상대 위치를 표현하는 additive 계약 → 결정적 관계 배치/정확한 floor 추정 표시 → 실제 geometry·사진 품질 gate → 기존 bounded repair/재검증 → 같은 결과 제품·Isaac 인수**다. P01 보조 oracle를 모든 사진의 하드코딩 정답으로 일반화하지 않으며 uncertainty를 유지한다. 모델 호출 반복이나 방 확대·물체 누락·위험 keepout 제거로 통과시키면 안 된다. 이번은 테스트 요청이므로 새 제품 관계 구현까지 임의 확장하지 않았다.

## v321 — 최초 로컬 검사와 실행 전 거절 이력

**사진 위치·지지 오류를 스스로 발견해 수정하는 제품 루프는 불합격이다.** 형식 repair 절차와 사진 품질 판정을 구분했다. 이번 새 외부 모델 테스트는 원본 침실 사진의 Nebius 전송에 대한 명시 동의 부족으로 실행 전에 거절되어 **NOT_RUN/새 호출0**이다. 거절을 우회하지 않았고 구체적인 원본 전송 동의를 질문했다. 로컬 저장 응답 검사는 실제 모델의 새 수정 성공률이 아니다.

사용자가 실측 없이 추정을 선택했으므로 실제 방 가로×세로 정확도는 `UNVERIFIED_NO_MEASUREMENTS`로 남긴다. 사진만으로 metre 단위 정답을 만들지 않는다.

- [먼저 저장한 테스트 계획](../planning/TWINPULSE_PHOTO_QUALITY_LOOP_TEST_PLAN_2026-10-07.md)
- 검증기: `scripts/verify_photo_quality_loop.py` — `--offline`/`--live` 명시 분리. Live 최대7회/기존USD1·60회 공유 한도, unknown/timeout 중단·재시도 없음.
- 결과: `artifacts/agent-reliability-20261007/photo-quality-loop-offline-r1/result.json`
- 원래 실제 응답: `artifacts/agent-reliability-20261007/compact-chat-isaac-live-r1/runtime/provider-evidence/`의 기존 Gemma/Nano2회. 원래 request/schema/raw hash를 대조하여 그대로 재사용.
- 기존 실제 Isaac/PhysX 연결 인수는 [v320 기록](photo-compact-live-connection-20261007.md)을 유지한다. **이번 새 Isaac/Browser/실물 실행0**.

## 사진과 실제 생성 geometry의 차이

P01을 사람이 검토한 보조 oracle이며 일반 사진 인식 정확도 평가가 아니다. 원본 사진에는 침대가 우측, 책상이 좌후방, 상자가 옷장 위, 모니터와 소품이 책상 위에 있다.

| 대상 | 기존 실제 모델 출력 geometry | 판정 |
|---|---|---|
| 침대 | x=-3.3, 입구 기준 좌측 | 사진의 우측과 반대 |
| 책상 | x=+3.3, 우측 | 사진의 좌측과 반대 |
| 옷장 위 상자 | 바닥높이0, 옷장 상면1.9m; XY도 분리 | 지지 FAIL |
| 모니터 | 바닥높이.75m, 책상 상면.74m이나 XY가 책상 밖 | 지지 FAIL; 높이만 비슷하다고 PASS 아님 |
| 책상 소품 | 바닥높이.75m이나 XY가 책상 밖 | 지지 FAIL |
| 방 | 10×12m/120㎡ 추정 | 규모 경고; 실제 치수 정답 미검증 |

지지 검사는 부모의 실제 catalog 부품을 확장한 후 부모 yaw 좌표에서 자식의 회전 footprint 전체 포함과 bottom/top 간격을 검사한다. XY 허용.015m/Z 허용.02m는 **로컬 관계 oracle 허용값**이지 로봇 정합·실물 정확도 기준 변경이 아니다. 의복 부착/열린 문 hinge/침구/불확실한 작은 물체·가림 구조는 별도 미완료다.

## 수정 루프와 병목 분리

1. **기존 실제 실패 후보 재사용:** 기존 `GenerationService → NebiusChatCompletionsPipelineProvider → compact compiler → executor`로 동일 plan을 얻었다. 위 사진 오류5개가 있어도 계약 유효·repair0으로 끝났다. 사진 품질의 false negative가 재현됐다.
2. **통제 형식 오류:** 기존 실제 Nano 응답의 침대 region 하나를 `controlled_invalid_region`으로 바꿨다. 기존 pipeline이 정확한 region 오류/이전 후보/같은 schema를 담아 repair1을 요청했다. 로컬에서는 이전 유효 응답을 저장 자료로 반환해 절차·재검증을 확인했다. **실제 새 모델 correction NOT_RUN**, 자연발생 모델 오류나 성공률 분모에 섞지 않는다. 수정 후에도 사진 품질 오류는 그대로다.
3. **실행기와 변환기 분리:** 별도 로컬 파생 계획에서 상자를 옷장 상면 XY/Z로 옮기자 지지 oracle PASS와 기존 executor ACCEPTED를 얻었다. 원본 불변이다. 초기 ‘실행기의2D 겹침 거절일 수 있다’ 가설은 검사로 반증됐으며 확정 원인으로 기록하지 않는다. 실행기는 room item을 별도로 처리하여 이 지지를 허용한다.
4. **실제 병목:** `photo-layout-1.1`의 각 필수 슬롯은 `region/yaw_deg/observation_ids`만 받는다. 부모/지지면/높이/부착 필드가 없다. compiler는 모든 항목을 독립 XY영역에 서로 겹치지 않게 배치하고 box는 바닥, 모니터/소품은 부모 위치와 무관하게+.75m에 배치한다. `placement_relationships=NOT_RECONSTRUCTED`. 이 경로로는 모델에 관계 오류를 반복 전달해도 실제 옷장 위 상자를 출력할 수 없다.
5. **독립 실제 사진 판정→수정→재판정:** 원본 사진과 geometry JSON을 Gemma에 보내고 Nemotron에 진단을 반환하는 bounded 시험 경로를 준비했다. 렌더를 보지 않은 검사를 렌더 품질 평가라고 부르지 않는다. 실행 승인 검토에서 차단되어 모든 신규 모델 단계는 NOT_RUN이며, 외부 평가기를 제품에 이미 연결된 자동 품질 gate로 주장하지 않는다.

## 회귀·보존

- Provider 전체63개 PASS/0.875s; 새 평가 oracle6개 포함. 별도 focused18개 PASS/0.157s는 중복이므로 합산하지 않는다.
- Core 첫 전체302개 실행에서 제품 assertion 실패가 아니라 한 테스트의 Windows Temp cleanup `WinError5`1건 발생(25.489s). 정상 Temp 접근으로 같은 전체302개 **PASS/25.679s**. 제품 소스 수정 없이 재확인했다.
- 새 Python2개 compile PASS, `git diff --check` PASS. Untracked 새 파일은 별도 검사 대상이다.
- 이전 실제 project/result/raw, 공유 campaign, provider/core 제품 소스6개 SHA 전후 동일. 계획/검증기/테스트/기록만 추가, 제품 기본 정책·LLM prompt·compiler·API/UI·저장 형식 변경0.
- 초기 평가 fixture의 잘못된 region/kind 표기를 바로잡고, executor REJECTED라는 미확인 예상은 실제 ACCEPTED 결과에 맞춰 교정했다. 이 중간 검증기 오류를 제품 오류로 계산하지 않는다.
- Campaign **53/60**, 미완료 dispatch0, 기존 추정+불명예약USD.09737678 유지/청구 미확인. 새 모델 비용0, 키/헤더 출력·보관0. 로봇/배포/센서/모터/설치/commit/push/새 agent0.
- 기존 dirty/원본/과거FAIL/v1-v2/hash/정지·freshness·실물 잠금 보존. Whole demo ready=false, 기본 compact OFF, H5/H6 및 C3–C6 PARTIAL 유지.

## 다음에 실제로 필요한 것

추가 호출을 채우기 전에 **관계 표현→결정적 지지 배치→geometry·사진 품질 gate→정확한 오류를 기존 bounded repair로 반환→재검증**을 제품 경로에 연결해야 한다. 관계를 표현할 수 있는 계약이 선행되어야 하며, LLM self-accept 또는 존재 개수로 품질 통과를 대체하면 안 된다. 방 크기는 추정과 실측을 계속 분리한다. 이후 같은 원본 실제 모델 평가와 통과한 결과의 Isaac Build/표시/Run·Stop/저장 재열기를 검사한다. 이 개선 구현은 이번 ‘테스트’ 범위를 넘어 자동으로 착수하지 않았다.

원본 사진 전송을 승인하면 현재 검증기로 실제 형식 repair와 독립 품질 진단·수정 가능 범위를 제한해서 확인할 수 있다. 다만 현재 compiler에서 지지 복원까지 성공한다고 보장하지 않으며 동일 불가능 요청을 반복하지 않는다.
