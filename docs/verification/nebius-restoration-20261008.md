# v360 — Nebius 기본 선택 복원

> 이 문서는 당시 실제 변경 이력이다. 사용자가 v361에서 **사진 GPT / 설계·수정 Nebius Nemotron**으로 정정했으며, 모든 단계를 Nebius로 바꾼 해석은 잘못이었다. [정정 및 혼합 실제 시험](mixed-provider-correction-live-20261009.md)을 현재 기준으로 따른다. 아래 과거 사실은 보존한다.

사용자 요청: “다시 Nebius로 가능한부분은 돌려줘라. 그게 규정이니까”. 새 유료 시험 승인이 아니라 공급자 선택 복원으로 처리했다.

## 변경과 직접 확인

- 기존 보안 저장소의 등록된 Nebius 키를 `KeyRegistry.select`로 선택했다. 키 재입력·등록·삭제 없이 OpenAI 등록도 보존했다. 키 값은 출력하지 않았다.
- 사진 관측은 `google/gemma-3-27b-it`, 설계·내용 수정은 `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, 모두 기존 Nebius Token Factory endpoint다. GPT 자동 우회는 없다. 기존 명시적 비교 구현과 raw 결과는 삭제하지 않았다.
- 등록된 legacy profile 이름은 `nebius_token_factory`다. 일반 채팅 backend는 해당 adapter에 **Site2.2를 명시**하므로 legacy1.0으로 퇴행하지 않는다. backend와 동일하게 구성하여 Site2.2 / 내용 수정 최대1을 확인했다. compact 실험·추론 설정·출력 상한을 새로 변경하지 않았다.
- 활성 설정을 새 객체로 다시 읽어 복원을 확인했다. 등록2개와 보안 키 존재 상태, registry metadata SHA, 기존 Nebius/mixed/all-GPT 장부4개의 SHA가 모두 보존됐다. 키 존재는 새 인증 성공을 의미하지 않는다.
- 구성 검증 중 socket connect를 금지해 외부 요청0을 확인했다. 실제 생성·Isaac·로봇 명령0. 실행 중인 다른 backend는 재시작하거나 종료하지 않았으며 **다음 일반 TwinPulse backend 시작부터 적용**된다. 명시적인 과거 평가 scope는 역사 기록이며 이번 요청으로 재실행하지 않았다.

## 회귀와 한계

공급자 키 목록/설정 회귀 **19 PASS** (`nebius-restoration-regression-r2.json`). 첫 sandbox 실행은 Temp 파일 쓰기/정리 권한 오류로 18FAIL/1PASS/12teardown ERROR였으며 제품 결함으로 단정하지 않았다. 허가된 오프라인 재실행에서 통과했다. 실패한 임시 자료를 임의로 삭제하지 않았다.

근거: `artifacts/pre-demo-20261008/nebius-restoration-r1.json` (구성/재읽기/보존 PASS), `nebius-restoration-regression-r1.json` (초기 권한 실패 요약), `nebius-restoration-regression-r2.json` (19 PASS).

사진 관측 품질, 일반 배치·추정·수정 회복 병목은 미해결이다. 공급자 복원을 전체 데모 성공으로 표시하지 않는다. 새 유료 호출 없이 과거 승인 한도를 초기화하거나 늘리지 않았다. 로봇 안전 잠금·dirty·raw·과거 실패·예약 PAUSED는 그대로 유지한다.
