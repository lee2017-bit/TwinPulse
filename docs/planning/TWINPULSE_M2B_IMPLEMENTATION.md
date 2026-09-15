# TwinPulse M2-B — image-first tool orchestration 및 generated scene 연결

- 날짜: 2026-09-13 KST
- 결과: **PASS — 단일 real image tool-plan 생성·Build·reload 복원 및 장거리 주행 교정 검증**
- 제품 저장소: `C:\Users\jaewo\Documents\Codex\TwinPulse`

## 구현

- Copilot형 Settings 창: Base URL, Model ID, reasoning effort, masked API Key.
- Base URL/model/reasoning은 Kit persistent settings에 저장하고 key는 Windows Credential Manager에 별도 저장. key는 프로젝트·로그·Baseline에 기록하지 않음.
- PNG/JPG/JPEG/WEBP 한 장, 최대 10MB의 picker와 preview. Generate 클릭 때만 파일을 읽고 전송.
- modern `POST /responses` adapter: text+data URL image, strict JSON Schema, `store: false`, 단일 시도, timeout/cancel/stale response와 authentication/rate-limit error.
- 이미지를 primary evidence, 자연어를 optional constraint로 전달. 고정 기본 prompt 제거.
- provider는 floor/wall/rack row/pallet/aisle/static AGV/predefined AGV/navigation task의 8개 allowlisted tool로만 strict plan을 반환.
- local registry가 tool plan을 deterministic geometry와 기존 `SpecBundle`로 확장하고 core/route validation 뒤에만 scene에 적용. 임의 Python/shell/USD/asset/web 호출은 불가.
- generated draft는 plan hash와 함께 `%LOCALAPPDATA%\\TwinPulse\\runtime\\last_generated_draft.json`에 저장·reload 복원. key/prompt/image/path는 저장하지 않음.
- generated Build는 draft 없이는 비활성화되며 M1 sample fixture로 silent fallback하지 않음. UI/log/USD metadata에 image/tool/object/source를 명시.
- PhysicsScene prim을 유지하면서 TwinPulse 소유 environment/robot/presentation/task를 교체. 실패 시 이전 bundle 복구.
- Extension session당 첫 Build 또는 Run에 개략 모델 경고 한 번 표시.

## 검증

- Python compile: PASS.
- core: 20/20 PASS. allowlist/argument contract, rack expansion, record serialization/hash tamper, route gate와 6.9m 폐루프 복귀/통로 이탈 안전정지 포함.
- provider: 8/8 PASS. image request/schema body 및 Responses structured JSON parsing 포함.
- Isaac 6.0.1 MinimalRendering/CPU: PASS.
  - Settings/warning window 생성.
  - allowlisted generated tool plan scene 적용, owned prim 50.
  - 의도적 mid-replacement 실패 시 이전 scene ID/prim/bundle과 live PhysicsScene 보존 PASS.
  - implicit sample fallback rejection PASS.
  - lifecycle 3회, run/pause/reset 3회 PASS.
  - 6.9m long-route: 목표 오차 0.049724m, 최대 횡이탈 0.005134m, `completed` PASS.

## 실제 이미지 E2E 및 주행 교정

- 사용자 Full 앱에서 `gpt-5.6-luna`, 이미지 1장으로 `warehouse_aisle_scene_01` 생성 성공.
- audit: `images=1`, 14 allowlisted tool calls, 59 expanded objects, plan hash prefix `a135a31a65d7`.
- generated tool plan으로 134 prim Build 성공. rack row, pallet stack, static AGV와 predefined moving AGV가 이미지 구성에 맞춰 달라졌고 sample fixture가 아님을 source log로 확인.
- 앱 재시작 뒤 같은 plan hash/draft가 복원돼 persistence 경로를 확인.
- 최초 Run은 현재 pose/yaw를 보지 않고 양쪽 바퀴에 같은 속도를 주는 open-loop였으므로 긴 경로에서 오차가 누적되어 오른쪽 rack 쪽으로 이탈했다.
- 매 physics step 목표 heading을 재계산하는 차동 조향으로 교체하고, 0.20m 초과 횡이탈 시 정지/Reset 요구, 상태줄 aisle error 표시, 실제 2D 목표 거리 완료 조건을 적용했다.

## 남은 gate

- Codex는 API key를 생성·요청·출력하지 않았고 유료 API 호출을 직접 보내지 않았다.
- 이전 semantic reject는 상세 오류/schema 정렬 교정 뒤 실제 tool-plan 재시도로 해소됐다. 추가 비용을 발생시키는 자동 retry는 넣지 않았다.
- 사용자 Full 앱을 완전히 재시작한 뒤 저장된 draft를 **Build Generated Scene**하고 **Run / Resume**해 교정된 장거리 중앙선 유지와 목표 정지를 시각 확인한다. 이 확인에는 Generate/API 재호출이 필요 없다.
- 기본 후보는 `gpt-5.6-luna` reasoning `low`. 동일 fixture 품질이 부족하면 `gpt-5.6-terra`와 비교한다.
- 서로 다른 이미지 3개와 실제 Build/Run/충돌·시간·거리·최대 횡이탈 계측 전에는 M2 전체 PASS가 아니다.
