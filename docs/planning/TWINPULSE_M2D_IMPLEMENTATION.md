# TwinPulse M2-D 치수 도면 시험

- 일자: 2026-09-14 KST
- 상태: **PARTIAL**
- 상세 증거: `C:\Users\jaewo\Documents\Codex\TwinPulse\docs\verification\M2-D-dimensioned-floorplan-e2e.md`

## 완료한 것

- 12×8m 창고 평면, 2개 rack row, 외벽 높이, 중앙 통로, AGV Start/Goal을 명시한 deterministic PNG 생성기
- 이미지 binary 없이 재생성할 수 있는 SHA-256 manifest
- provider가 반환한 allowlisted plan을 29개 치수/좌표 항목으로 비교하는 scorer
- fixture 수를 3개로 고정하지 않고 PNG/JPG/WEBP를 처리하는 provider/Isaac runner
- provider와 혼동되지 않는 `deterministic_reference_not_provider` 3D compiler 검증 경로

## 실제 결과

- reference score: 29/29 PASS
- reference tool plan: 9 calls, 35 expanded objects
- Isaac scene: 90 prims
- 8m route: `completed`, simulated 32.583s, travel 7.903m
- goal error 0.09887m, cross-track 0.00390m
- max roll/pitch 0.10101°/0.06674°
- collision samples 0, Pause drift 0m, Reset error 0m
- 실제 build stage를 `work\m2d-usd\dimensioned_warehouse_floorplan_v1.usda`로 export(35,948 bytes, SHA-256 `0284520340250ea1ce103fe4e83944757ae928e267eaeb21e935613f700cb618`)
- 새 key 저장 뒤 실제 Luna multimodal 요청 exactly one attempt 성공
- provider plan: `dimensioned_warehouse_floor_plan`, 10 calls, 32 expanded objects
- provider score: **27/29 FAIL**. 바닥 12x8m, 외벽 2.5m, 랙 길이/깊이/베이, 중앙 통로, AGV start/goal/route는 통과했으나 이미지의 랙 높이 3.0m를 두 행 모두 2.0m로 오독
- 같은 provider bundle의 실제 Isaac scene: 84 prims, 32.583s/7.903m 주행, `completed`, goal error 0.09887m, cross-track 0.00390m, max roll/pitch 0.10101°/0.06674°, collision/Pause drift/Reset error 0
- provider build stage를 `work\m2d-live\usd\dimensioned_warehouse_floorplan_v1.usda`로 export(33,823 bytes, SHA-256 `1ea2e44c5d1732a2ce35d8a71e5be7322bb7fa3e51d97f498a1404b5b81ddc0a`)

## 미완료 이유

새로 저장한 Windows Credential Manager 값으로 OpenAI Responses API 요청은 성공했고 자동 retry하지 않았다. 그러나 모델이 도면의 `RACKS: 8.0 x 1.5 x 3.0 m HIGH`를 `2.0 HIGH`로 잘못 관찰해 두 랙 높이 검사를 실패했다. 따라서 실제 이미지 판독과 3D/physics는 검증됐지만 정확 좌표 acceptance 29/29는 미달이다.

## 실패 후 적용한 구조 교정

- 기존 OpenAI adapter가 모든 이미지를 `detail=low`로 보내던 것을 수정해 도면·floor plan·technical drawing cue는 `high`, 일반 사진은 `low`로 선택한다.
- generator가 PNG와 함께 동일 stem의 `*.measurements.json`을 만들며, 현재 fixture는 바닥·랙·벽·start/goal을 포함한 8개 독립 constraint를 가진다.
- Extension은 image attach 시 sidecar를 strict loading하고 실제 이미지 파일명과 binding한다. 일치하는 constraint가 있으면 provider plan을 registry 실행 전에 검증하며, 없으면 `exact dimensions unverified`를 명시한다.
- 기존 27/29 provider plan을 새 gate에 재입력한 결과 `rack_height expected 3 +/- 0.25, got 2`, `build_allowed=false`로 차단됐다.
- Provider 13/13, Core 24/24, compileall, generator/sidecar 8개 로딩 PASS. clean Full-app 재기동에서 TwinPulse Extension startup과 `app ready`를 확인했다. 수정 뒤 외부 API는 재호출하지 않았다.

## 재개 조건

M2-D는 27/29 실패 결과를 보존하며 상태는 PARTIAL이다. 다음에는 재기동한 Extension의 sidecar 인식부터 확인하고, 별도 승인 아래 동일 도면을 한 번만 다시 호출해 29/29와 measurement-validation PASS를 동시에 확인한다. 사용자의 수동 Isaac 실행이나 스크린샷 전달은 필요 없다.
