# TwinPulse M2-C 구현·검증 결과

- 날짜: 2026-09-14 KST
- 판정: **PASS — 서로 다른 실제 이미지 3개에 대해 provider 3/3, Isaac physics 3/3**
- 상세 저장소 문서: `C:\Users\jaewo\Documents\Codex\TwinPulse\docs\verification\M2-C-three-image-e2e.md`

## 수행 범위

Wikimedia Commons의 권리 조건이 명시된 창고 사진 3개를 직접 내려받고 SHA-256을 고정했다. 바이너리는 저장소에 넣지 않고 출처·저자·라이선스·URL·hash만 fixture manifest에 남겼다. 기존 Windows Credential Manager의 key를 출력하거나 파일에 저장하지 않은 채 이미지마다 OpenAI Responses 요청을 정확히 1회 실행했다. 자동 유료 재시도는 없었다.

세 응답은 각각 10/9/18개의 allowlisted tool call과 58/58/46개의 확장 객체를 만들었다. LLM 관찰은 좁은 양측 pallet rack 통로, 비대칭 parts storage와 지원하지 않는 산업차량 제외, 넓은 pallet staging과 사람 제외로 달랐다. 따라서 하나의 mock scene을 반복한 결과가 아니다.

각 bundle을 Isaac Sim 6.0.1 headless MinimalRendering에 순서대로 Build하고 실제 articulation을 Run/Pause/Reset했다. 세 episode 모두 `completed`, collision sample 0, Pause drift 0m, Reset error 0m였다. 목표 오차는 0.2464m, 0.2444m, 0.2153m(각 허용 0.25m), 최대 횡이탈은 0.00515m 이하, 최대 roll/pitch는 각각 0.1029°/0.0667° 이하였다.

계측 자체의 false negative를 막기 위해 collider와 의도적으로 겹치는 sample이 collision 1건으로 실패하는 core regression을 추가했다. blocked route, off-route stop, invalid response, timeout/no-retry, rate limit, unsupported image, cancelled late response 시험을 포함해 core 24/24와 provider 8/8이 통과했다.

## 판정 경계

M2-C는 선택한 세 fixture에 대해 완료다. 일반 사진의 치수·가림은 계속 개략적이며, 현재 controller는 검증된 positive-X 직선 경로만 수행한다. 이 결과는 임의 미래 scene이나 장애물 회피, ROS2/Nav2, 실물 AGV를 보장하지 않는다. 다음 단계는 회사 PC 재현 후 M3 구조적 수정·저장·Replay다.
