# E2e 다중 가구 배치 대기·드래그 검증 — 2026-09-29

## 결과

사용자 요청 `침대와 의자 추가`를 종류가 모호한 요청으로 거절하던 로컬 해석을 수정했다. **두 종류는 확정**, 좌표만 미정으로 배치 대기 공간에 놓는다. 사용자가 방 평면에 끌어놓거나 항목→평면 클릭/수치 입력으로 좌표를 결정한다. 모두 놓은 뒤 한 번의 preview와 한 번의 apply로 동일 sidecar revision에 저장한다. 기존 사진·recipe·초안은 그대로 두며, 서버의 벽 여유/겹침 검증은 통과해야 한다. 사진에서 위치를 추론하지 않는다.

| 확인 | 결과 |
|---|---|
| Python scene change 통합 | 10 PASS. 침대+의자 원자 추가/Undo/재열기 및 겹침·중복·조작된 입력 거부. |
| Web | 153 PASS, production build PASS. 다중 의도, 배치 미완료 잠금, preview 이후 단일 apply. |
| 실제 Chrome→로컬 API→Isaac | [r3 PASS](../../artifacts/runs/20260929-e2e-multi-furniture-isaac-r3/result.json). 드래그 2개→preview→sidecar 1 revision→재승인→Build, 최종 bed/desk/bed/chair 4종 호출·가구 prim/Collision API·Burger 시각, 외부/로봇 요청 0. [카메라 캡처](../../artifacts/runs/20260929-e2e-multi-furniture-isaac-r3/authored-camera-viewport.png). |

검증 입력은 **합성 사진으로 만든 저장 방**이다. 첨부된 실제 사용자 방 사진에서 침대/의자 위치를 추론하거나 실제 치수를 확인한 것이 아니다. 카메라 캡처의 모바일 채팅 지속 표시도 확인되지 않았다. 원본 파일의 로컬 경로 링크는 모바일에서 열리지 않을 수 있어 전달 문제는 미해결이다. Physics Run/회사 PC/실물 로봇 시험은 하지 않았다. E2 전체는 PARTIAL.

초기 r1은 Windows 샌드박스가 Chrome spawn을 EPERM으로 차단해 FAIL, r2는 리허설 브라우저가 화면 밖 배치 보드로 마우스를 이동해 미배치 FAIL이었다. 화면 안으로 스크롤하는 리허설 수정 후 r3 PASS. 두 실패 기록은 보존한다.
