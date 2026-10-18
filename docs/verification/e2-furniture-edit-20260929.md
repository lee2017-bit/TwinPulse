# E2c 가구 의미 편집 — 2026-09-29

**검증한 로컬 경로 PASS; E2 전체 PARTIAL.** 기존 방의 E1 변경 이력을 재사용해 `place_furniture` 가구를 개별 호출 단위로 추가·종류/위치/각도 변경·마지막 변경 되돌리기 할 수 있다. 원본 사진·recipe·초안은 덮어쓰지 않고 프로젝트별 sidecar를 재생한다. 적용 뒤 장면 revision이 바뀌므로 검토·승인을 새로 해야 한다. 로봇 명령은 없다.

## 범위와 수정

- `SceneEditReview`에서 7종 고정 로컬 프리셋과 기존 가구 호출을 고른다. 다중 부품의 전후 차이를 미리 본 뒤 적용한다. 변경된 입력은 미리보기를 무효화한다.
- v2.1 가구 계획의 Add/Change/Undo·재열기에서 계획 버전을 보존한다. 기존 v2.0 방에 가구를 새로 넣는 경우 별도 변경 계획만 v2.1로 올리고 원본 v2.0은 그대로 둔다.
- 가구 그룹의 보수적 XY footprint가 바닥 여유 밖이거나 다른 가구/충돌 고체와 겹치면 게시 전에 거절한다. 이는 실측 통과 여유나 물리 충돌 검증이 아니다.

## 실행 검증

| 범위 | 결과 |
|---|---|
| Core | 178 PASS, 가구 계획/배치 검증 포함. |
| 방 생성 + 변경 이력 통합 | 13 PASS. v2.0→2.1 별도 변경, 가구 Add/Change/Undo/재열기, 겹침 거절. |
| Web | 147 PASS, production build PASS. 가구 선택/미리보기 무효화/적용/되돌리기. |
| [실제 Chrome→API→bridge→Isaac](../../artifacts/runs/20260929-e2c-furniture-edit-isaac-r1/result.json) | PASS. 저장된 테스트 방에서 의자 추가→수납장 변경→Undo→새 승인→Build. 원본 recipe/초안 불변, bed·desk·chair prim/충돌 API, Burger visual, USD 보존. [화면 캡처](../../artifacts/runs/20260929-e2c-furniture-edit-isaac-r1/authored-camera-viewport.png). |
| [별도 새 Isaac 프로세스 재열기](../../artifacts/runs/20260929-e2c-furniture-edit-reopen-r1/result.json) | PASS. 저장 revision `4cc8d1200db218ac24fe3e6ccba88a70522306cd9f6351383db740215cb87891`, 가구 3종, 의자 유지/수납장 없음. 승인/실행권한 복원 없이 다시 검토→Build. |

처음 전체 Python 명령은 `twinpulse_core.tests`라는 존재하지 않는 import 경로를 함께 지정해 13개 통과 뒤 loader ERROR였으며, 종료코드 0인 harness여서 성공으로 세지 않았다. 올바른 경로로 core 178과 통합 13을 별도 재실행해 PASS했다. 첫 Web build는 새 시험 fixture의 optional `editable_calls` 타입 오류로 FAIL, 한 줄 수정 후 build PASS. 실패 기록을 지우지 않는다.

## 남은 경계

검증 방의 사진은 합성 입력이며 실제 방 사진의 가구/치수 인식은 하지 않았다. 현재는 수치/종류 선택 UI이며 자연어 대상 해석·모호성 질문·출처 설명, 사용자 카메라/조명 모드, 다른 방/창고 동등 경로는 E2 잔여다. Physics Run, 회사 PC, 실물 로봇/센서/좌표·주행·정지는 미실행. 기존 실물 정지 FAIL과 실행 잠금은 유지한다.
