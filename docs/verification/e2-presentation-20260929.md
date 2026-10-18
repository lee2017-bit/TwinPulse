# E2g 화면 보기·조명 — 2026-09-29

범위: 저장된 방의 검토 화면에서 카메라 방향 6종(자동/앞/뒤/왼쪽/오른쪽/위)과 조명 3종(균형/부드럽게/밝게)을 선택한다. 설정은 원본 사진·recipe·scene revision과 분리된 프로젝트별 sidecar에 결속해 저장한다. **현재 열린 Isaac 장면이 아니라 다음 명시적 Build에 적용**되며, 다시 열어도 새 검토·장면 제어·승인은 별도로 필요하다. 방향은 장면 좌표 기준 표시 선택이고 사진 속 창문 방향/실측 TF 증거가 아니다. 로봇 권한·Run·Physics는 추가하지 않았다.

- 로컬 회귀: [전체 비-Isaac verifier](../../artifacts/runs/e2-presentation-verifier-20260929/manifest.json) PASS — core 178, 웹 154, production build PASS, Isaac suite NOT_RUN. 새 Python 테스트는 원본 프로젝트 바이트 불변·stale/invalid 거절·프로세스 재생성 후 설정 복원을 확인한다. 새 React 테스트는 명시 저장 전까지 버튼 잠금과 선택값 전달을 확인한다.
- 별도 실제 Isaac: [r5](../../artifacts/runs/e2-presentation-20260929-r5/result.json)에서 실제 Chrome→API→broker→bridge→Isaac Build로 `top:soft` 적용, 카메라 side `top`, Dome 550/Sun 250, Burger 시각 mesh 4, Run 없음. [r6](../../artifacts/runs/e2-presentation-20260929-r6/result.json)은 저장 상태를 새 Isaac 프로세스에 복사·재열기해 재저장 없이 같은 설정을 확인. [r7](../../artifacts/runs/e2-presentation-20260929-r7/result.json)은 이후 주입한 시각 Build 실패 시 이전 stage/설정 복구. [r8 화면](../../artifacts/runs/e2-presentation-20260929-r8/authored-camera-viewport.png)은 authored 카메라를 통한 합성 방 캡처. [기본값 회귀](../../artifacts/runs/e2-presentation-20260929-default-r1/result.json) PASS.
- 실패 보존: r1은 새로고침 후 검토 탭으로 돌아가지 않은 브라우저 harness 오류. r2–r4는 Burger 미리보기 조립이 설정 없이 `compile_site_scene()`을 다시 호출해 기본 view/light로 덮은 제품 오류였다. `presentation`을 조립 단계까지 전달한 뒤 r5–r8 PASS. 실패를 통과로 재분류하지 않는다.
- 미검증: 실제 사용자 사진의 기하/위치/창문 방향 정합, 회사 PC의 표시 품질·조명 선호, 자유 orbit 카메라·실시간 장면 변경, Physics/로봇/주행. 따라서 E2 전체는 PARTIAL. 기존 실물 정지 FAIL 및 실물 임무 잠금은 그대로다.
