# v362 — 설정에서 바꾸는 단계별 LLM 조합

요청: “나중에 이렇게 조합해서 바꿀 수 있으니까 그건 설정에서 쉽게 바꿀 수 있게 해줘”. 일반 App 설정/실제 생성 경로 구현으로 처리했으며 새 paid 시험·로봇 구동 승인은 아니다.

## 사용법

1. 기존 TwinPulse가 실행중이면 안전하게 종료 후 다시 실행한다. 이번 작업은 기존 사용자 프로세스를 강제 종료/재시작하지 않았다.
2. 채팅 상단 **API keys → Model routing**을 연다.
3. **Photo analysis**와 **Planning and repair**에서 각각 사용할 등록된 키·모델 조합을 고른다.
4. **Save model routing**을 누른다. 선택만 한 경우 Unsaved, 저장·gateway 재구성이 끝난 경우 Applied로 구분한다. 다음 생성부터 사용하며 진행중인 생성에는 변경할 수 없다.
5. 기존 단일 공급자 설정으로 돌아가려면 **Switch to single-provider mode**를 누른 뒤 Use this key를 선택한다.

**GPT 사진 + Nemotron 설계 조합은 실제 runtime에 저장하고 재읽기까지 확인했다.** 기본 키 파일과 등록키 metadata는 바꾸지 않고 별도 `provider_stage_routing.json`에 키 ID·모델 ID만 저장했다. 키 값은 OS 보안 저장소에 그대로 있고 UI/파일/로그에 출력하지 않았다. 영어 기본 UI 정책은 유지하고 사용자 설명은 한국어로 제공한다.

현재 지원 선택지는 사진 OpenAI GPT-5.4 mini/Nebius Gemma3/MiniCPM-V, 설계·수정 OpenAI GPT-5.4 mini/Nebius NVIDIA Nemotron Nano다. OpenAI 실제 wire 모델은 기존 검증 snapshot `gpt-5.4-mini-2026-03-17`. 공급자에 등록된 여러 키도 선택 가능하다. API 키가 등록되었다고 해당 모델의 인증·성능 검증이 완료된 것은 아니다. 임의 origin/미지원 모델을 자유 입력해 호출하는 구조는 아니며, 새 모델 프로토콜 지원은 별도 추가해야 한다.

## 제품 연결과 안전 경계

- ordinary `scripts/twinpulse_backend.py` gateway/settings metadata/provider status가 저장 조합을 사용한다. host-only 평가 scope를 normal default로 넣지 않았다. fixture/offline/replay/host campaign 경로는 기존대로 분리했다.
- Site2.2 기존 프롬프트/도구계약/검증/공유 repair1을 재사용, 사진 본문은 observer에게만 전송한다. planner와 repair에는 분석 결과·설명만 들어간다. 텍스트 입력은 observer 호출 없이 선택 planner로 진행한다.
- 단계별 origin·registered secure store를 결속, 한 공급자의 키를 다른 origin으로 보내지 않는다. OpenAI wire 정규화와 Nebius body를 단계별로 구분한다.
- gateway 재구성/설정 재시작 재읽기는 zero-call이다. 실패 시 다른 공급자로 자동 전환/자동 재시도하지 않는다. host evaluation campaign의 승인·예산을 ordinary routing으로 빌려오지 않는다.
- atomic 파일 저장/재구성 실패 rollback, missing key/corrupt file fail-closed, 생성·장면 pending 중 변경409, 단계에서 사용중인 키 삭제 차단. 단일 키 선택과 단계별 조합이 충돌하지 않도록 먼저 mode를 전환한다.
- 설정 적용은 기존 `provider_settings_changed()`에 연결해 현재 input/ack를 무효화하고 재선택·검토를 요구한다. 새로운 키/모델로 과거 승인된 Build/Run을 자동 재사용하지 않는다. 입력 revision에 실제 단계 모델/origin/추론 설정을 넣되 credential ref/secret은 넣지 않는다.
- 설정창 초기 목록과 선택값을 함께 갱신해 빈 선택/늦은 effect 경쟁을 제거했다. Refresh와 Save를 함께 잠가 과거 읽기 결과가 새 저장 결과를 덮지 않으며 unmount 후 응답은 UI에 반영하지 않는다.
- 90초 전체 deadline·기존 출력상한(관측4000/설계 기존정책)·bounded repair1은 그대로다. 이전 compact/300초/10000토큰 평가를 일반 기본정책으로 몰래 승격하지 않았다.

## 검증

- 새 stage routing integration **10 PASS**: 추천은 저장 전 미적용, persistence/독립 키·모델 조합/unsupported 거부/secret 비노출/rollback/busy/pinned key/corrupt/missing credential/campaign 분리, 실제 pipeline photo+repair/text/reverse dispatch, origin/이미지누출 거부.
- 같은 HTTP endpoint의 cookie/CSRF401/403/200, 저장 후 generation gateway 재구성 확인. ordinary backend main 진입에서 saved routing을 읽고 ProductWorkflow의 실제 입력 선택→설정 변경→입력 무효화→재선택 revision 변경을 확인했다. startup server/robot adapters는 테스트 격리용 대체이며 actual Isaac이나 실물 인수가 아니다.
- 기존 key registry12/split evaluation12/provider settings7 = 관련 **41 PASS**(새10 포함), Provider 전체167/Core 전체302 PASS. 중복 인수를 합산한 제품 성공률로 주장하지 않는다.
- Web 최종 **46파일/424테스트 PASS**(설정9/영어기본2 포함), 타입검사/프로덕션 build PASS. 기존 jsdom canvas 미구현 및 500kB chunk 경고는 남아 있다.
- actual registered Windows 설정: `scripts/verify_stage_routing_settings.py --apply-recommended`, 이후 옵션 없는 readback 둘 다 PASS. socket connect를 금지한 상태에서 설정·키 metadata SHA 불변/저장route true/gateway composed true/network0/robot0 확인. 청구·생성 품질 인증은 아니다.
- compile 및 변경 범위 diff whitespace 확인 PASS. 이번에 새 외부 LLM 호출0, 로봇/SSH/serial/배포/모터/설치/commit/push/새agent0, 과거 raw·paid ledger9/10·UNKNOWN 예약·dirty·guard·예약PAUSED 보존.

초기 실패도 보존한다: Windows sandbox 임시 파일/cleanup PermissionError와 Vite spawn EPERM 후 정상 승인 범위의 동일 offline 실행으로 재검증; 테스트 fixture user_quote/좌표계 누락, shutdown stub/입력 API shape·auto-kind 불일치, source PYTHONPATH 누락을 바로잡았다. UI 첫 선택 effect 경쟁과 기존 영어 기본 정책 FAIL은 실제 구현을 수정했다. refresh 중 Save 버튼이 Applying으로 바뀌는 정상 라벨을 테스트가 잘못 기대한 실패도 기록하며 최종 assertion을 수정했다. 최초 실패를 성공으로 덮어쓴 것이 아니다.

## 잔여

이번에 **normal 혼합 설정 코드·저장 연결은 해결**했다. 새 ordinary 경로의 실제 외부 응답→Isaac 인수/사진 전체 장애물·정밀도/일반성/initial camera 및 stale progress code/최신package·현장 검증은 하지 않았다. v361의 실제 mixed SIM 성공은 그때의 명시 평가 경로 근거로 보존하고 이번 normal default의 새 성공으로 재표시하지 않는다. 전원만 켜면 전체 실물 데모 완료라는 보장은 없다.
