# E1 저장 방 비파괴 편집 — 2026-09-29

## 로컬 판정

**검증한 사용자 방 저장 v2 경로: LOCAL_ACCEPTED.** 실제 Chrome에서 보존 사진방을 열어 `Add box → Change bed → Undo → Change bed again`을 수행하고 별도 변경 이력을 저장했다. 새 승인 뒤 production API/bridge→로컬 Isaac Build 영수증과 3D 장면을 확인했다. 별도 Isaac 프로세스에서 같은 변경 이력을 다시 열어 승인 없이 검토 상태부터 시작하고 동일 revision을 Build했다. 이 판정은 가구의 실측 정확도, 자연어 변경, Isaac 물리주행, 실물 로봇 또는 회사 PC 검증이 아니다.

## 구현된 경계

- 원 `project.json`의 `SiteDraftRecord`, 사진 archive, `room_recipe.json`, Burger 자산/manifest는 변경하지 않는다. 프로젝트 로컬 `project.scene-changes.json`에 source/input/parent/result revision, operation ID, typed tool call과 비대상 객체 digest를 기록한다. 원자 게시·동시 잠금·재생 검증·동일 ID 멱등성, 저장 직전 원 프로젝트 재검사를 사용한다.
- App 검토 화면에서 새 환경은 별도 프로젝트 생성 화면으로 연결되고, 기존 방은 Add/Change/Undo를 제공한다. 현재 수치 입력 UI는 **박스 형상** 한정이다. 미리보기는 영향받는 모든 객체의 전후 위치·크기와 보존 수를 보여주며 저장 후 새 승인을 요구한다. 새 객체는 `user_local_edit`로 표시한다.
- 저장 revision은 Isaac 적용 revision과 다르다. Build 성공/현재 엔진 영수증 뒤에만 3D 적용을 표시한다. 시각 합성 후반 오류 주입 시 `/World/TwinPulse` 마지막 정상 장면과 적용 revision을 복원한다. 실패 시 저장된 편집 자체는 지우지 않는다.
- 방 사진 방향·가구 치수·Burger 시각 pose는 근사/미검증이다. 편집이 기존 지도/임무 근거를 자동 재승인하지 않고 실물 Run을 열지 않는다.

## 실제 실행 근거

| 근거 | 결과 |
|---|---|
| [Chrome→Isaac 편집·Build r6](../../artifacts/runs/20260929-e1-scene-edit-complete-isaac-r6/result.json) 및 [브라우저](../../artifacts/runs/20260929-e1-scene-edit-complete-isaac-r6/browser-result.json) | PASS. Add/Change/Undo/재변경 4회, 새 review/Build 1회, sofa 추가·bed X=-0.4 m·desk 불변, Burger visual 4 mesh, Run 없음, 외부/로봇 요청 0. 합성 후반 실패 주입의 마지막 정상 stage/적용 revision 복원 PASS. [Isaac 카메라](../../artifacts/runs/20260929-e1-scene-edit-complete-isaac-r6/authored-camera-viewport.png)는 보기 QA이며 방 실측 증거가 아님. |
| [새 Isaac 프로세스 재열기 r7](../../artifacts/runs/20260929-e1-scene-edit-reopen-final-r7/result.json) | PASS. r6의 격리 저장 상태 복사본을 새 프로세스에서 검증; 동일 `7be7359c…7289f8f` 편집 revision을 승인 없이 다시 검토→명시 승인→Build. |
| `.venv/Scripts/python.exe -m unittest tests.integration.test_scene_changes tests.integration.test_a2_room_recipe` | 21 PASS. 원본 불변/다중 객체 영향/24 call·64 object 경계, stale·동일 ID·저장 실패/변조, 실제 API/CSRF·원 프로젝트 변경/재열기/시각 descriptor 검증. |
| `.venv/Scripts/python.exe -m unittest discover -s packages/twinpulse_core/tests` | 176 PASS. |
| Python R4/R5/A2/편집 집중 묶음 | 68 실행, 67 PASS·Windows symlink 1 SKIP. 편집 source 표기 뒤 해당 21건을 재실행 PASS. |
| Web `pnpm test`, `pnpm run build` | 143 PASS 및 production build PASS. 편집 preview/apply·미리보기 무효화 검사 포함. |

초기 24-call 음성 시험은 fixture를 허용된 ±20m 밖에 놓아 1회 FAIL했고 좌표만 고쳐 동일 6개 테스트 PASS. [앞선 새 프로세스 r3](../../artifacts/runs/20260929-e1-scene-edit-reopen-isaac-r3/result.json)는 결과 JSON의 편집 revision 표기 누락이 있었고, 이를 고친 r4 및 최종 r7을 판정 근거로 사용한다. 이전 결과를 수정하거나 삭제하지 않았다.

## 다음 사용자 기능

E2는 임의 방 입력/가져오기, 의미가 다른 가구·기본 보기, 일반 프로젝트 Burger 배치, 자연어의 기존 장면 **추가/변경** 문맥을 App에 붙이는 작업이다. 현재 박스 편집만으로 “한국형 아파트 가구 다양성” 또는 “새 사진의 정확한 3D 해석”을 완료했다고 표시하지 않는다. E3 이후 기록/모의 임무/통합 연결과 실제 로봇 검증도 남아 있다.
