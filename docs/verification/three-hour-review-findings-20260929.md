# 3시간 통합 구현 후 코드 검토 — 2026-09-29

상태: **F1/F2/F3 재현, 모두 미수정(OPEN)**. 이 문서는 점검 당시 관측을 정리한 기록이며 수정 검증 결과가 아니다.

## 범위와 재현 방법

- 현재 canonical dirty 트리의 API, App, workflow, project catalog와 기존 시험을 대조했다.
- `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\review_twinpulse_20260929.py`를 기존 `.venv\Scripts\python.exe -B`로 실행했다.
- 상태는 별도 scratch 디렉터리에 생성했다. API는 loopback, physical controller는 action 수신만 기록하는 fake, provider는 기존 `SiteGateway` 가짜 구현이다. 사용자 프로젝트·로봇 transport·Isaac·유료 provider는 사용하지 않았다.
- 첫 실행은 Windows 임시 폴더 접근 권한 때문에 진행하지 못했다. 허용된 작업 폴더의 독립 scratch로 바꿨다. 이후 첫 API probe의 CSRF 헤더 오기를 기존 `X-TwinPulse-CSRF`로 바로잡은 최종 실행 결과를 아래에 기록한다. 앞선 403은 제품 결함 근거가 아니다.

## F1 — 엔진 오류 중 정지 입력까지 공통 게이트에서 거절

`packages/twinpulse_app/src/twinpulse_app/api.py`의 runtime starting/error POST 차단이 physical input handler보다 먼저 실행된다.

| supervisor | action | HTTP | fake 제어기 도달 | 결과 |
|---|---|---|---|---|
| ready | force_stop | 200 | true | STOPPING |
| ready | finish_stop | 200 | true | STOPPING |
| error | force_stop | 409 | false | runtime_start_failed |
| error | finish_stop | 409 | false | runtime_start_failed |
| starting | force_stop | 409 | false | runtime_not_ready |
| starting | finish_stop | 409 | false | runtime_not_ready |

동일 인증 세션/CSRF와 동일 endpoint/body 형태에서 supervisor만 달리했다. 실제 모터 정지 실패를 재현한 것은 아니며, **정지 요청이 제어기까지 도달하지 않는 API 결함**을 확인한 것이다. 기존 로봇 로컬 timeout/watchdog과 구별한다.

## F2 — 일반 저장 v2 장면의 UI 재개 경로 누락

가짜 provider로 정상 v2 장면을 생성·저장한 뒤 ApplicationService와 ProductWorkflow를 다시 만들었다.

```json
{
  "phase": "restore_review_required",
  "protected": true,
  "provider_name": "fake",
  "artifact_id": null,
  "continue_saved_room": "room_recipe_restore_unavailable",
  "generate": "existing_scene_protected"
}
```

App의 저장 이어보기는 `local-room-recipe`에서만 나타나며, 일반 입력 선택은 잠긴 Create Draft 동작 안에 있다. 검토의 acknowledge도 artifact가 없으면 비활성이다. 따라서 이 일반 장면을 사용자가 화면에서 재개할 경로가 없다. 백엔드 `select_input`을 동일 원본으로 직접 호출하면 복원 가능하다는 기존 테스트와 **사용자 UI의 복원 가능 여부는 별개**다. 이 점검은 상태/API 재현과 UI 소스 경로 대조이며, 별도 실제 브라우저 재현은 이 턴에 수행하지 않았다.

## F3 — 복사 실패가 최종 프로젝트 ID를 점유

별도 임시 state root에서 `prepare_project_burger_visual`에 OSError를 주입했다. 오류를 잡은 후 catalog와 동일 ID 재시도를 확인했다.

```json
{
  "failed_project": {"project_id": "audit_room", "status": "import_required", "active": false},
  "same_id_retry": "FileExistsError"
}
```

최종 폴더·빈 project.json·사진·recipe를 먼저 게시하기 때문에 실패 이후에도 미완성 프로젝트가 남는다. 이 결과는 원래 사용자 자료 손실을 뜻하지 않으며, **정상 목록에 반제품이 남고 같은 이름 재시도가 막히는 복구 결함**이다.

## 검증 공백과 후속

- 이전 core176/Web140/build PASS는 당시 검사 범위 안에서 유지한다. 위 결함은 기존 수용 검사가 빠뜨린 경로다.
- H2b2 복원 검사는 내부 `select_input()`으로 복원하여 UI 재개 누락을 드러내지 않았다. 새 검사는 사용자 버튼→API를 통과해야 한다.
- 기존 시작 실패→Isaac-ready harness는 새 manager를 테스트에서 직접 만들고 recovery 실행 파일을 교체한다. 이 결과를 회사 PC 환경 자동 수리나 운영 런처 전체 복구의 증거로 확대하지 않는다.
- [상세 수정계획](../planning/TWINPULSE_REVIEW_FIX_SOL_PLAN_2026-09-29.md)의 R0→R4가 기존 통합계획 P3 기능 추가보다 우선한다. 문서 작성 시점에는 제품 코드 수정·실물 시험이 없다.
