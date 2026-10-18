# 저장300초·20000토큰 실제 재시험 — 출력 소진으로2회 중단

2026-10-09 사용자 ‘재실행하고 테스트5회까지만’ 승인에 따라 기존 원사진/GPT 사진관측→Nebius NVIDIA Nemotron 설계·수정/ordinary configured service를 새 host 장부에서 시험했다. **합산2/5 호출 후 출력 소진으로 즉시 중단**, 나머지3회 미사용. 생성 **FAIL**, 새장면 Build/Run/Stop **NOT_RUN**, whole=false. 로봇 연결·명령0.

## 경계와 실행

- 저장 설정 그대로: 사진4000 / 최초·수정 설계20000 / 전체 generation300초 / compactOFF / max_repairs1. 기존 등록키·모델·primary/stage 설정은 변경하지 않았다. 시간만 늘리면 이전 근거ID 오류가 해결된다고 가정하지 않는다.
- `run_saved_stage_timeout_five.py`는 이번 명시 승인용 `configured-stage-evaluation-1.0` scope/최대5 공통장부/기존 USD0.15 상한을 별도 경로에 생성한다. current 저장 route/출력/총시간/등록settings/사진SHA·기존prompt 결속 후 기존 `verify_saved_stage_live.py`→실제 App/API generation 경로를 실행했다. Nano 가격 metadata GET은 추론횟수0; 실제 inference POST2. 기존 소진된5회 장부를 확대/재설정하지 않았다.
- 시험 소유의 TwinPulse 백엔드·로컬 Isaac·브라우저를 새로 실행/종료한다. 다른 사용자 프로세스 강제종료/설치/실물접속0. 시작 전 read-only 프로세스 열거는 sandbox 권한거부였고 이를 우회하지 않았다; 기존 소유권 관리 launcher로만 진행했다.
- HTTP 전송/원응답/장부에서 실제 GPT cap4000/Nano cap20000, App 결과와 saved service에서 총300 확인. 일반 service를 사용하되 metadata는 기존 host split harness이므로 일반 설정 UI 전체 종단 인수로 표시하지 않는다.

## 결과

| 단계 | 응답 시간 | 출력 토큰 | finish / 결과 |
|---|---:|---:|---|
| GPT 사진 관측 | 7.968초 | 1334 | stop / 관측 schema검증 PASS |
| Nano 최초 설계 | 89.453초 | 20000 | length / content0·rejected |

Nano 원응답은 추론 필드만 존재하고 최종 설계 JSON 본문은 비어 있다(추론 내용은 사용자 보고/문서에 옮기지 않음). 즉 **300초 만료 전에 출력 한도가 먼저 소진**된 것이다. 추론 토큰도 출력 한도를 소비한다. 20,000으로 늘린 이전5회에서는 모두stop이었으나 이번에는length가 재현돼 출력 성공이 안정적이라는 근거가 아니다.

- 제품 진단 `validation_code=PROVIDER_OUTPUT_TRUNCATED`, finish_reason=length, planner/model/max_tokens20000, `repair_count=0`, App `phase=generation_failed`, `build_allowed=false`. 출력 한도 문제를 정상JSON 계약 repair로 넘기지 않았다. batch `stop_reason=output_limit_reached`, 후속 수정·추가 사진 호출0, 3~5번째0.
- 이번에는 설계 JSON이 없으므로 이전 scene-1↔call-1 근거 참조 오류의 수정 여부/정합 품질은 **평가 불가**이며 해결됐다고 표시하지 않는다. 이 결과만으로 모든 Nemotron 작업이 불가능하다고 일반화하지도 않는다.
- 공통 진단 실행ID **316a374ca04141cc8b6be524b4978e0b** 아래 GPT/Nano 요청·응답 span과 제품 오류가 결속된다. raw2/attemptID2↔ledger2/SHA/usage/저장설정SHA·이전장부3개SHA불변 감사 PASS. 추정USD **0.01293429**(실제 청구 확정 아님), pending0/outcome_unknown0/dispatch lock 없음.
- browser_closed=true, owned launcher shutdown=succeeded, supervisor=stopped 감사 PASS. 새장면 생성 실패로 host의 장면 캡처도 PASS가 아니며 actual scene 인수로 승격하지 않는다. 원사진/원응답/과거 FAIL·UNKNOWN예약/dirty/물리 guard/wholefalse/예약PAUSED 보존.

## 검증과 다음 판단

- 호출 전·후 stage/split 설정 **26회귀 PASS**, 새 runner py_compile/diff 검사 PASS. inference source는 이번 세션 시작/종료 SHA 동일, 모델 생성 계약/프롬프트/제품 source 변경0. 웹소스 변경0/새웹빌드0. 저장300·사진4000/설계20000 별도 zero-call 재읽기 PASS.
- 추가 호출은 하지 않았다. 다음 분석 대상은 **Nemotron의 추론 소진·최종 structured JSON 생성 설정/요청 구조**이며 대기시간 추가 확대가 아니다. 추론 제어가 실제 공급자·모델에서 지원되는지와 기존 body에 적용되는지 먼저 확인해야 한다. 자동 fallback/compact 전환/사진 맞춤 하드코딩/한도 조용한 증액으로 이번 FAIL을 모면하지 않는다. 수정은 이 시험 요청에 포함하지 않아 미실시.

근거: [요약](../../artifacts/pre-demo-20261009/saved-stage-300s-five/summary.json), [원응답·장부·종료 감사](../../artifacts/pre-demo-20261009/saved-stage-300s-five/audit.json), [공통 장부](../../artifacts/pre-demo-20261009/saved-stage-300s-five/campaign.json), [App/실행 결과](../../artifacts/pre-demo-20261009/saved-stage-300s-five/run-1/result.json). run-1/runtime/provider-evidence와 diagnostics/해당실행ID에 원본·세부로그 보존; secrets/header를 보고하지 않는다.
