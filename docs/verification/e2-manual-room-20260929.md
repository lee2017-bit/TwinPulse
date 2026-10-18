# E2a 사용자 사진 + 입력 치수로 새 방 만들기 — 2026-09-29

**E2a 제한된 로컬 경로 PASS, E2 전체 PARTIAL.** 실제 Chrome/App에서 합성 PNG와 사용자 입력 치수(폭 3.6m·길이 5.2m·벽 2.6m)를 별도 `photo_room_two` 프로젝트에 만들고, 원 사진·허용목록 plan·선택한 고정 Burger 시각 자산을 저장했다. 새 Isaac 프로세스에서 **같은 저장본**을 검토→새 승인→production API/bridge→3D Build했다. 원래 `default` 프로젝트 바이트는 바뀌지 않았고 이전 승인은 승계되지 않았다. 물리 Run/실물/유료 provider는 실행하지 않았다.

## 구현 경계

- App `My photo + dimensions I enter` 모드는 JPEG/PNG/WebP 완전 디코딩, 크기·치수·요청 형태 검사를 거쳐 새 project ID에만 게시한다. 원본사진 해시와 사용자 치수·plan을 project-local recipe/InputRevision에 결속한다. **사진 해석은 하지 않는다.** 3벽(정면 열림)+바닥은 입력 치수의 결정적 저작 형상이다.
- staged project를 다시 읽어 검증한 뒤 같은 파일시스템 rename으로 게시한다. 기존 project/ID를 덮어쓰지 않으며 동일 request ID·동일 입력 재시도만 같은 결과를 반환한다. 실패 중간본은 활성 프로젝트 목록에 승격되지 않는다.
- 사용자가 선택하고 고정 로컬 자산이 실제 존재할 때만 visual-only Burger 사본을 project에 넣는다. 자산 부재 시 방 생성은 모델 없이 가능하다. Burger 위치는 시각용 가설이지 사진 판독/실물 TF가 아니다.
- 기존 E1 수치 box Add/Change/Undo와 저장방 재검토 흐름은 그대로 사용한다. 이번 증분은 침대/소파/의자 등의 의미·시각적 차이를 만드는 가구 카탈로그, 자연어 추가/변경, 사용자 보기/조명 조절을 구현하지 않았다.

## 증거

| 시험 | 결과 |
|---|---|
| [실제 Chrome 새 방 생성 r5](../../artifacts/runs/20260929-e2-manual-room-browser-r5/result.json) | PASS. 인증 UI→API→독립 프로젝트 저장, 원본·Burger 고정, 외부/로봇 변경/장면 명령 0. 준비 상태는 **격리 가짜 launcher**이며 Isaac/실물 아님. |
| [r5 저장본의 새 실제 Isaac 프로세스 Build](../../artifacts/runs/20260929-e2-browser-created-isaac-r1/result.json) | PASS. 동일 `photo_room_two` 저장본 검토/새 승인·실제 Chrome/API/bridge/Isaac, Burger visual 4 mesh, USD 저장, 물리 Run 0. [시점 이미지](../../artifacts/runs/20260929-e2-browser-created-isaac-r1/authored-camera-viewport.png)는 방·로봇의 시각 QA이지 사진 정확도 검증이 아니다. |
| [별도 programmatic 수동방 Isaac](../../artifacts/runs/20260929-e2-manual-room-isaac-r1/result.json) | PASS. 독립 입력으로 동일 room recipe 경로 확인. 주요 완료 근거는 위 browser-created 저장본이다. |
| `.venv/Scripts/python.exe -m unittest tests.integration.test_manual_room_creation tests.integration.test_a2_project_catalog tests.integration.test_a2_room_recipe tests.integration.test_scene_changes` | 38 실행, 37 PASS·Windows symlink 1 SKIP. 입력 위조/중복 ID·원본 보존·실패 후 미게시·Burger 선택/해시 경계 포함. |
| Web `pnpm test` / `pnpm run build` | 144 PASS / production build PASS. |

초기 브라우저 리허설 r1은 읽기 전용 로봇 상태 폴링을 로봇 변경 요청으로 잘못 센 harness 판정으로 FAIL, r2는 원래 `default` 빈 레코드 존재를 `None`으로 잘못 가정해 FAIL이었다. 판정만 수정하고 실제 로봇 호출 없이 r3→Burger 포함 r5 PASS를 얻었다. 이전 실패를 삭제하거나 성공으로 바꾸지 않았다.

## E2 잔여

가구 타입별 카탈로그/지오메트리·근거·충돌 및 시각 구별, 기존 장면 자연어 추가/변경(가짜/저장 provider로 오프라인 검증), 사용자 조작 시점·밝기 모드, 서로 다른 실제 방/주거·창고 동일 경로 인수. 새 사진의 해석 품질·실측 기하/TF·회사PC·실물은 별도다. E1–E7 전체 완료가 아니다.
