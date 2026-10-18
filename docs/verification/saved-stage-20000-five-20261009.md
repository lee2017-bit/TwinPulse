# 저장 Nemotron20000 · 승인5회 실제 재시험

2026-10-09 사용자 요청 ‘다시 실행해서5회까지 테스트’에 따라 **모든 단계 합산5/5** 종료. GPT 관측2/최초 Nano설계2/Nano수정1. 출력잘림0/5(설계·수정0/3), 새장면생성0/2, Build/Run/Stop **NOT_RUN**, whole=false. 이번 응답은 20000 한도에 걸리지 않았으나 90초 총 generation deadline으로 두 세션 모두 FAIL. 추정USD**0.02421966**, pending0/dispatch lock 없음/6번째0/로봇0. 실제 청구 확정이 아니다.

## 실행 경계

- 기존 저장모델 GPT mini snapshot→Nebius NVIDIA Nemotron Nano, 사진4000/설계·수정20000, compactOFF/90초/max_repairs1 유지. 기존 원사진·동일 prompt 사용, 도면외부전송0. 저장 route/key/primary 변경0.
- 이전10회 장부를 확장·재활용하지 않고 새 `configured-stage-evaluation-1.0` 명시 host scope에서 max_requests5와 저장 route/단계한도/기존 등록settings/origin·가격을 함께 검증한다. 이전 mixed/gpt scope의 max_requests10 계약은 유지한다. generic legacy builder는 새 scope를 거절하여10000으로 조용히 내려 시험하는 것을 방지한다.
- `verify_saved_stage_live.py`는 ordinary **build_configured_stage_service**와 actual stage cap을 사용하고 두 audit transport에 공통5회 장부만 결속한다. 실제 원응답/evidence에 Nano max_tokens20000 확인. 상태 UI metadata는 기존 host split harness이므로 일반 설정 UI 전체 종단 인수는 아니다.
- 기존 로컬 Isaac/백엔드/browser를 시험 소유 프로세스로 재실행하고 각 세션 종료. 다른 user process 강제 종료/새 설치/실물 구동 없음. 모델추론 소스/웹빌드 각 세션 내부불변, historical FAIL/RAW/장부2개 SHA불변.

## 결과

| 세션/단계 | 응답 시간 | 출력 토큰 | 결과 |
|---|---:|---:|---|
| 1 GPT관측 | 5.953초 | 981 | stop·관측검증 PASS |
| 1 Nano최초 | 64.687초 | 17172 | stop·5798자 설계 JSON, 검증 FAIL |
| 1 Nano수정 | 28.765초 | 6311 | stop·5814자 응답이지만 deadline 후 도착/취소·rejected |
| 2 GPT관측 | 7.563초 | 1191 | stop·관측검증 PASS |
| 2 Nano최초 | 90.234초 | 16989 | stop·8854자 응답이지만 deadline 후 도착/취소·rejected |

세션1 첫설계의 scene_calls는 `scene-1`~`scene-9`인데 call_evidence는 `call-1`~`call-9`를 참조한다. 따라서 `EVIDENCE_CALL_MISSING`9개, `CALL_EVIDENCE_MISSING`, `PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING`을 받은 것이다. 사진의 실측 방크기 때문에 거절한 것이 아니다. 이 join 오류는 실제 응답에서 확인됐으며, 다른 의미의 호출 ID를 수동으로 바꾸거나 rejected응답을 정상데이터로 대체하지 않았다.

관측+최초설계에서 약71초가 지나 수정에 남은 약19초가 부족했다. 세션2도 관측 후 남은 약82초보다 설계 응답90.234초가 길었다. **90초는 관측·설계·수정을 모두 포함하는 총시간 제한**이므로 개별 호출마다90초를 준 결과가 아니다. 출력 상한과 시간 상한은 별개다.

공개 generation은 timeout/outcome_unknown으로 먼저 종료하고 늦은 HTTP응답은 원문과 ledger에 usage·rejected로 정산했다. 이는 late response를 장면으로 적용하지 않았다는 뜻이다. 첫 세션 진단상 ‘unknown’ 상태를 보고 보낸 ‘3회 사용/추가중단’ commentary는 늦은 정산·두 번째 시험 시작을 반영하지 못했고 바로 정정했다. 실제 최종은 승인5회 이내이며, raw length가 없었으므로 출력초과 즉시중단 조건이 발생하지 않았다. 무한재시도/추가6번째 없고 raw/장부상 pending0을 확인했다.

## 검증과 정확한 다음 일

- 호출 전/후 **25회귀 PASS**: 기존 stage/split 설정, 새로운5회 scope/20000 결속/구scope한도불변/변경route 거절/legacy builder 거절. 저장 재읽기 PASS, diff/compile 검사 PASS. 이번 새로운 Web회귀/빌드0(웹소스 변경없음).
- audit_saved_stage_five.py PASS: 장부5↔원응답5 attempt IDs·response SHA/usage/모든 browser_closed·owned shutdown succeeded/supervisor stopped/시험중 inference source불변/이전 ledger SHA불변. 늦게 취소된2응답도 버리지 않고 포함했다.
- 필요 수정은 **도구 호출ID↔근거ID 생성 계약 일관성**, **단계별 시간/전체시간 예산 정합화와 설정 가능성**이다. 20000 증가로 이번 출력 잘림은 재현되지 않았지만 생성 성공은 아니다. 시간만 늘리면 근거 참조 오류가 해결되는 것도 아니다. 이번 턴은 진단·시험이며 이 두 제품 수정은 미실시.
- 공개 종료 진단과 늦은 audit 정산의 상태 차이도 사용자가 이해할 수 있도록 구분해야 한다. 실측·사진 전체 장애물/지지 정밀도·actual fresh 장면·package·현장은 여전히 미검증.

근거: [요약](../../artifacts/pre-demo-20261009/saved-stage-20000-five/summary.json), [감사·실행ID/시간/usage](../../artifacts/pre-demo-20261009/saved-stage-20000-five/audit.json), [장부](../../artifacts/pre-demo-20261009/saved-stage-20000-five/campaign.json). run-1/2 result.json/browser.json/runtime/provider-evidence에 실패·원문·진단 보존. secret/header/사진 bytes를 로그에 저장하지 않는다. 기존 dirty/raw/guard/과거 UNKNOWN예약/자동화PAUSED 유지.
