# 저장된 단계별 조합 실제 10회 시험

## 결론

2026-10-09 사용자 추가10회 승인으로 실제 호출 **10/10** 종료. GPT 사진관측5회 정상 응답/계약 통과, Nebius NVIDIA Nemotron 최초 설계5회 모두 본문 생성 전 출력 잘림. 최종 생성0/5, 자동수정 호출0, 새 장면 Build/Run/Stop **NOT_RUN**. 장부·원문·종료 감사 PASS는 생성 성공을 뜻하지 않는다. whole=false.

추정 비용 **USD0.04462059**(usage 기반, 실제 청구 미확인). pending0/dispatch lock 없음. 추가11번째 호출 없음, 이전 장부 재사용·초기화 없음. 로봇/SSH/센서/모터/배포0.

## 범위와 방법

- 재부팅 뒤 secure 등록·저장 route 재읽기: GPT `gpt-5.4-mini-2026-03-17` observer → Nebius `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` planner 확인. 기존 key/primary metadata 보존.
- `verify_saved_stage_live.py`는 시험 전용 host wrapper. 기존 명시승인 scope/공통10회 장부를 활용하되 서비스는 실제 **build_configured_stage_service**에서 구성하고 두 단계의 audit transport에만 동일 장부를 부착한다. 사진SHA/prompt/등록키/모델이 승인과 다르면 송신전 차단.
- ordinary pipeline의 **90초/max_attempts1/compact OFF/observer4000/planner8000/max_repairs1**을 유지했다. 이전 성공의 compact ON/300초/10000 출력 시험으로 바꾸지 않았다. 임의 fallback/응답 수정/가짜 데이터 없음.
- backend 상태 메타데이터와 평가 entrypoint는 기존 explicit split harness를 이용하므로 **일반 설정창부터 모든 메타데이터까지 종단 인수는 아니다**. 실제 저장 route가 사용하는 동일 생성 서비스·정책의 live 시험이다. 결과의 production_default=false/split_provider_evaluation=true는 보존한다.
- 각 세션에서 기존 로컬 Isaac/백엔드/브라우저를 시험 소유 프로세스로 시작했다. 장면 생성 이전에 실패하여 Isaac 실행 준비 자체를 장면·PhysX 성공으로 표시하지 않는다.
- 새 설치·시스템설정·타 프로세스 종료0. 초기 Win32_Process 인벤토리 권한 거부는 우회하지 않았고, 기존 manager의 시험소유 상태/종료기록만 사용했다.

## 실제 결과

| 세션 | GPT 초 | Nemotron 초 | 설계 결과 |
|---|---:|---:|---|
| 1 | 6.672 | 32.172 | finish=length, content=0, completion8000 |
| 2 | 7.593 | 28.500 | 동일 |
| 3 | 6.797 | 37.968 | 동일 |
| 4 | 9.484 | 38.547 | 동일 |
| 5 | 4.969 | 38.015 | 동일 |

Nemotron 원응답의 `message.reasoning`은 26,364~30,434자이며 `message.content`는 모두 비어 있다. 90초 timeout이나 Wi-Fi/로봇 문제로 볼 근거가 아니라 **8000 completion 한도 안에서 추론만 생성하고 JSON 본문에 도달하지 못한 실패**가 직접 확인됐다. 5장 사진 분석 모두 HTTP 정상 응답/stop이지만 사진의 실제 크기·모든 소물체 정확도를 검증한 결과는 아니다.

제품 parser `nebius_pipeline.py:parse_completion`은 length 확인 전에 비어 있는 content를 검사하여 `Chat Completions content is missing`으로 예외를 낸다. 이 오류가 `_complete` 단계에서 밖으로 전파돼 pipeline의 구조/geometry 수정 루프까지 도달하지 않았다. `max_repairs=1`이라는 설정만으로 모든 wire/잘림 실패가 수정되는 것은 아니다. 원문 reasoning을 정상 설계 JSON으로 간주하거나 추론에서 임의 JSON을 뽑아 PASS시키지 않았다.

## 다음 수정 대상 (이번 시험에서 미구현)

1. `finish_reason=length`와 usage/본문 상태를 우선 보존하여 잘림 원인·단계·출력한도를 정확히 분류. 빈 content 잘림과 정상 stop 빈 content/거절/HTTP 실패를 구분하고 회귀 추가.
2. 일반 Nemotron의 추론·출력 정책을 이전 성공의 compact 경로와 비교해 설정·입력 revision·UI에서 명시적으로 선택/기록 가능하게 정합화. 단순 timeout 증가만으로 이번 토큰 소진은 해결되지 않는다. 더 긴 출력만으로 성공한다고 보장할 수 없다.
3. 잘림에도 공유 호출한도 안에서 안전하게 모델에 피드백하는 bounded 재시도/수정 설계. 중단/unknown/예산/원본 보존, 자동 공급자 변경 금지. 근거 없는 입력 토큰 재송신 반복 방지.
4. 수정 후 별도 승인 fresh generation→actual Build/PhysX/Stop/reopen→일반 설정 UI 포함 종단 인수. 기존 successful compact 기록은 이 기본 경로의 성공률로 대체하지 않는다.

## 검증·근거

- 기존 단계별 설정 integration 10 PASS; wrapper 실제 composition 확인 zero-call PASS(두 transport 같은 ledger, exact models/90초).
- `audit_saved_stage_batch.py`: 장부10↔원문10의 attempt identity 일치/저장 response SHA 검증/모든 browser_closed/owned shutdown succeeded/supervisor stopped/source unchanged PASS. 추론 제품 코드와 Web 빌드 시험중 변경0.
- [총 결과](../../artifacts/pre-demo-20261009/saved-stage-batch/summary.json), [감사·호출별 실행ID/시간/usage](../../artifacts/pre-demo-20261009/saved-stage-batch/audit.json), [호출 장부](../../artifacts/pre-demo-20261009/saved-stage-batch/campaign.json).
- run-1~5의 result.json/browser-worker.log/runtime/provider-evidence에 FAIL·원응답·실행별 진단 보존. 승인사진/키 원문은 진단에 저장하지 않았다. 비용·일반성·실물·최신 package 인수는 확대 주장하지 않는다.
