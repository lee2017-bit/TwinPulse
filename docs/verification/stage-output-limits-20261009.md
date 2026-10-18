# 단계별 출력 한도·한도 초과 즉시 중단

2026-10-09 사용자가 Nemotron 8000→20000과 설정 UI의 직접 변경, 출력 제한 확인 시 즉시 중단을 요청했다. 출력 소진을 자동 수정으로 회복시키자는 v363 다음 제안은 이 요청으로 **취소**한다. 정상 완성 JSON의 계약/배치 오류에 대한 bounded repair1은 유지한다.

## 반영

- **API keys → Model routing**에 Photo output token limit / Planning and repair output token limit 숫자 입력 추가. 사진 기본4000, 설계·수정 기본20000; 지원 범위1~20000 정수, 빈칸/소수/상한초과는 저장 비활성화/API거절. 기존 모델/등록키 선택과 함께 명시 Save model routing, 적용·미저장 상태, busy lock/atomic rollback 유지.
- stage choice의 optional `max_output_tokens`를 기존 credential-free 1.0 저장파일에 보존. 구 파일은 수정하지 않아도 새 기본값 적용; 저장 키/모델은 변경하지 않는다. 현재 실제 저장 조합 GPTmini observer/Nebius Nano planner의 **planner cap20000 명시저장·두 번 재읽기 PASS**, primary/key registry metadata 불변.
- ordinary configured pipeline `stage_output_token_caps`를 observer/최초 planner/수정 planner 실제 요청·trace·attempt에 적용. OpenAI observer는 기존 adapter의 `max_completion_tokens`로 변환, Nebius planner는 `max_tokens=20000`. 두 단계 값은 input revision에도 문자열로 포함되어 한도 변경이 이전 입력·생성물 재사용을 무효화한다.
- parser는 유효 envelope identity/usage를 검증한 뒤 `finish_reason=length`를 빈본문보다 우선 분류한다. 본문 없음/일부 JSON/정상모양 JSON이어도 length면 rejected `PROVIDER_OUTPUT_TRUNCATED`; partial content/usage/원문 유지, reasoning에서 설계 추출/실행하지 않는다.
- 출력 초과는 `stop_reason=output_limit_reached`, repair_count0(최초 잘림 기준), 모델/단계/한도/finish/usage/실행ID 진단을 남기고 **자동 수정·후속단계·자동 공급자 우회 없음**. 정상 stop의 스키마 오류는 기존 한도내 수정 허용. observer 잘림이면 planner 송신0, planner 잘림이면 추가repair0. 수정 중 잘림이어도 그 자리에서 추가0.
- future `run_saved_stage_batch.py`도 원문 length를 확인하면 전체 batch 종료. 이미 종료된 v363의10회/과거 scope·장부·승인·상한은 소급변경하지 않는다. 기존 host 전용 output override1~10000 및 승인 장부의10000 경계는 별개로 유지하여 사용자 설정 변경을 유료 시험 승인 확대로 해석하지 않는다. 새20000 paid test는 이번0.

## 검증

- Python **500 passed +279 subtests**: Provider167/Core302/단계설정12/키등록12/기존설정7. 초기 잘못된 test 파일경로로 no tests 오류, 그 뒤166/167에서 예전 length 자동repair 기대값1 FAIL; 사용자 새 중단정책으로 그 회귀를 명시 변경·usage/content 보존 및 송신1/repair0 검사 후 전체 통과. 실패기록을 성공으로 덮어쓰지 않는다.
- 새 단계설정 회귀: 구파일 기본20000/영속저장/잘못된 cap 무변경/입력digest 변경/사진5000·최초/수정planner20000 실body 전달/observer·planner의 None·partial length 추가송신0 통과.
- v363 실제 Nemotron 원응답5개 zero-call 재검사: 모두 `PROVIDER_OUTPUT_TRUNCATED`, repairable=false, usage8000 보존 PASS. 첫 실행 import PYTHONPATH 누락 FAIL은 core/provider 경로 지정 후 통과. 원문은 수정하지 않음.
- Web 전체46 files/**425 tests PASS**, 타입검사·production build PASS(최종 빌드 결과는 아래 기록). UI10회귀 포함 숫자표시/빈값·20001 차단/명시저장·다시 표시. 기존 jsdom canvas 경고·큰 chunk 경고 유지, 새 설치0.
- 실제20000 LLM 성공률/생성사진정밀도/새actual Isaac/현장 **NOT_RUN**. 키·로봇·유료 요청0, 90초 deadline·일반 JSON/compactOFF·guard/whole=false/dirty/raw/예약PAUSED 보존. 앱 다음 재시작부터 코드·빌드·저장값 적용; 다른 실행 앱 강제종료0.

사용: TwinPulse 재실행 → API keys → Model routing → 단계별 한도 수정 → Save model routing. **20000이면 반드시 성공한다는 뜻은 아니다.** 추론도 출력 토큰을 소비하고90초 제한은 별도이다. 한도 초과 후에는 원인 확인/사용자 명시 재요청 없이 추가 추론하지 않는다.
