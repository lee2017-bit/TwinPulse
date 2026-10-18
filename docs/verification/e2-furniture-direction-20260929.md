# E2f 가구 재배치·방향 선택 — 2026-09-29

배치 대기 가구는 처음 평면으로 드래그한 뒤 **배치 마커를 다시 드래그해 이동**할 수 있다. 선택 가구마다 위(+Y, yaw 0°)·오른쪽(+X, -90°)·아래(-Y, 180°)·왼쪽(-X, 90°) 방향을 지정한다. 2D 발자국 모양/화살표는 선택 회전을 표시하고, 저장 tool call의 `yaw_deg`에 같은 값을 전달한다. 방향·위치 변경은 기존 preview를 무효화하며 서버가 회전된 부품의 벽 여유/겹침을 다시 판정한다.

이 4방향은 **저장 방 평면 좌표계 기준**이다. 사용자가 사진에서 알려준 창문 방향과 검증된 좌표/TF로 자동 일치시킨 것은 아니다.

- Web 153 PASS 및 production build PASS. 침대 180°, 의자 -90° 전달과 방향 변경 후 재검토 요구를 단위 테스트로 확인.
- [실제 Chrome→API→Isaac r2 PASS](../../artifacts/runs/20260929-e2f-furniture-direction-isaac-r2/result.json): 두 가구를 드래그, 침대 마커 재드래그(-0.85m), 침대 180°·의자 -90° 선택, 일괄 preview/sidecar 1 revision/새 승인/Build. 저장 계획의 회전값과 prim 유효성 검증. [3D 캡처](../../artifacts/runs/20260929-e2f-furniture-direction-isaac-r2/authored-camera-viewport.png).
- 외부/로봇 요청 0, 물리 Run/실물/회사 PC 시험 없음. 합성 사진 기반 저장 방에서만 검증했으며 사용자 실사진의 가구 위치·치수/좌표 정합은 증명하지 않는다. E2 전체 PARTIAL.

이전 E2e r3는 방향 0°로 저장한 성공 이력이며 수정하지 않는다. 이 검증의 r1은 마커 재드래그를 추가하기 전의 방향 검증 PASS, r2가 위치 재드래그까지 검증한 최종 증거다.
