# TwinPulse M2-A 구현 결과

- 날짜: 2026-09-13 KST
- 결과: **LOCAL PASS / REAL PROVIDER NOT RUN**
- 제품 root: `C:\Users\jaewo\Documents\Codex\TwinPulse`

## 구현

- text+image 입력, capability, structured response, provider config 계약
- timeout, cancel, late/stale response 거부, rate-limit/capability/invalid-response typed error
- 검증된 `SpecBundle`만 반환하는 generation service
- deterministic local mock provider
- 실제 endpoint 계약 확인 전에는 사용하지 않는 gated HTTPS JSON adapter
- API key 값이 없는 example config
- VS Code Copilot 분위기의 prompt-first Isaac Extension UI
  - Describe → Generate → Simulate 단계 표시
  - 자연어 multiline 입력
  - local/mock 상태 표시와 구조화 결과 요약
  - 기존 Build/Focus/Run/Pause/Reset 유지
  - image 입력은 M2-B까지 명시적으로 disabled

## 검증 근거

- core unit tests: **10/10 PASS**
- provider unit tests: **6/6 PASS**
  - 정상 구조
  - 잘못된 구조
  - timeout/no retry
  - rate limit
  - image unsupported
  - cancel 후 late response 거부
- Isaac headless regression: **PASS**
  - Extension enable/disable 3회
  - run/pause/reset 3회
  - prim 28→28, camera/dome/sun/goal true
  - 목표 오차 0.049747m, pause drift 0m, reset error 0m
- 새 UI widget tree가 실제 Isaac Extension startup에서 예외 없이 생성됨
- 최초 Full 앱 화면은 한글/특수문자 glyph가 `?`로 깨지고 Stack 자동 높이가 과도하게 늘어나 시각 검수 FAIL
- 즉시 ASCII-only label과 명시적 `ui.Pixel` 크기의 compact layout으로 교체했으며 Isaac lifecycle/physics 회귀 재시험 PASS

## 아직 완료가 아닌 것

- 수정된 compact UI의 Full 앱 최종 시각 품질 확인
- image picker와 preview
- 사진+자연어를 실제 provider로 전송
- provider별 endpoint/model/vision/schema capability 확인
- 생성된 bundle을 `/World/TwinPulse` scene으로 적용

따라서 local mock 성공을 multimodal 또는 real-provider 성공으로 해석하지 않는다.

## M2-B gate

실제 API 호출 전 non-secret endpoint/protocol 문서, exact model ID, vision/structured-output 지원, 인증 위치, provider·비용·호출 횟수 승인이 필요하다. API key 값은 채팅이나 프로젝트 문서에 기록하지 않는다.
