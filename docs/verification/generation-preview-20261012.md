# 생성·검증·수정 미리보기 — 2026-10-12

Baseline **1.0.465**, 상태 **PARTIAL**. 구현과 로컬 사용자 흐름 검증은 진행했으나, 새로운 실제 Isaac/Flash·Super 전체 인수는 완료하지 않았다. 원 실패와 이전 비용 장부는 보존했다.

## 보고서와 확인 범위

화면 18장, 실행 ID, 수치와 정확한 잔여를 함께 담은 [단일 PDF 보고서](../../outputs/generation-preview-20261012/report.pdf)와 [같은 내용의 HTML](../../outputs/generation-preview-20261012/report.html)을 만들었다. 기계 판독 자료는 [report.json](../../outputs/generation-preview-20261012/report.json)이다. Chrome 1440px/390px에서 내장 이미지 18장 로드·가로 넘침 없음·외부 요청 0을 확인했다. PDF는 24페이지/내장 이미지18개·텍스트/Poppler 렌더·전체 페이지 배치를 확인했다. 화면 글자는 확대해서 확인할 수 있다. 공개 배포가 아니다.

**보고서의 단색 화면은 명시적인 합성 엔진 브리지다.** 실제 Chrome/App/API, 승인·체크포인트·컴파일러·broker·프레임 인증·저장 경로를 사용했지만 모델 응답은 고정 시험 자료이고 GPU 렌더가 아니다. 운영 Flash/Super 설정을 변경하지 않았으며 fixture의 다른 모델명은 실제 모델 호출을 뜻하지 않는다.

## 구현

1. 관측 메타데이터 `instance_count`의 null/양의 정수는 보존한다. 물체가 아닌 바닥/통로/표시 등을 가구로 확장하지 않는다. 0·음수·bool·분수는 계속 구체적인 경로 오류다. 원 관측 자료를 변경하지 않는다.
2. 수정 검증기의 typed report가 없는 경우에도 실제 오류 코드·경로·세부 내용을 feedback에 넣는다. 실패 기록만 저장한 경우, 관측만 저장한 경우, 유효한 미완성 초안을 저장한 경우를 구분한다.
3. `generation-preview-1.0`의 후보/장면 revision, 표시/대기/전체 수, building/ready/blocked, `preview_only=true`, `physical_authority=false`를 공통 API로 전달한다. UI에는 분석·상세 설계·검증·수정, 수량, 수정 횟수, 오류와 원 사진이 표시된다. 사진 없이 텍스트만 입력해도 동작한다.
4. 전체 inventory와 현재 묶음을 검사한 뒤 부모가 준비된 부분만 투영한다. 같은 `compile_scene`/기하 검사를 사용하고, 구조 직후·각 유효 묶음·유효 수정 결과를 기존 Build→receipt→현재 JPEG 경로로 전달한다. 부모/지지가 없는 자식과 아직 컴파일되지 않은 항목은 대기로 남는다. 전체 목록·원 관측·pending을 지워 통과시키지 않는다.
5. 마지막 유효 JPEG 한 장을 프로젝트-local 메모리에 유지하고 인증된 `/v1/product/viewport/preview/<sha>`로 제공한다. stale 화면은 정적 미리보기로 표시하고 카메라/현재 프레임 권한에 사용하지 않는다. API 프로세스 종료 이후에도 JPEG가 영구 복원된다는 뜻은 아니다. 이어하기는 이전 계획을 새 Build로 다시 확인한다.
6. 미리보기는 durable 확정 장면/Undo 기준/주행 승인과 분리된다. 기존 작업 취소·input/worker/revision·프로젝트 경계를 유지한다. 후보 SHA와 plan SHA가 모두 같은 현재 capture만 재사용한다. 최종 capture 소요 시간도 기존 실행 시간 예산에 포함한다.
7. `capture_viewport_to_buffer`의 delegate가 끝났지만 콜백이 오지 않은 경우 영구 busy가 되는 코드 경로를 재현했다. ticket/epoch로 늦은 콜백을 거절하고, 3초 이후 완료된 delegate만 제한적으로 회복한다. 미수신 native delivery 2개 이상은 새 캡처를 쌓지 않고 stalled로 표시한다. **사용자가 겪은 프레임 중단의 실제 원인이 이 경로라고 확정하지는 않았다.** 설치된 Isaac viewport 모듈은 읽기만 했고 수정하지 않았다.

주요 파일: Provider의 `nebius_pipeline.py`, `observation_instances.py`, `budgeted_pipeline.py`, 새 `generation_preview.py`; App의 `generation_render_port.py`, `viewport_service.py`, `api.py`, `product_workflow_service.py`; `scripts/twinpulse_live_viewport.py`, `twinpulse_engine_host.py`; Web의 `TwinViewport`, `ChatWorkspace`, 공통 API/타입/CSS와 검사. 확인 도구는 `scripts/verify_generation_preview.py`, Web `e2e/generation-preview.mjs`, 보고서 생성/QA 스크립트다.

## 실행 기록

최종 세 흐름 모두 생성 중 6/12 표시 → 의도적인 length 실패 → 원 목록 12개/대기 6개 유지 → 프레임 중단과 새로고침 → 명시 새 승인에서 남은 묶음만 재개 → 12개 표시·저장·정확한 ApplicationService 디스크 복원 PASS다. 실패 execution은 성공으로 고쳐 쓰지 않았다. 새 모델 추론·실제 GPU·완료 후 SIM 주행은 이 결과에 포함하지 않는다.

| 입력 | 결과 | 실패 execution ID | 재개 완료 execution ID | 고정 응답 dispatch |
|---|---|---|---|---:|
| 텍스트 | 로컬 흐름 PASS | `276d4c47e58f4581960b2a58dc3639ad` | `e2b953a609da4a03b44172929d5e0f69` | 4 |
| 이미지 | 로컬 흐름 PASS | `d6ac75bdc929483f9204d7a71b37a575` | `fd6d803a0ed64a10917e3c7983e1f339` | 5 |
| 텍스트+이미지 | 로컬 흐름 PASS | `87d3f26ed74042059e313de7cc35b292` | `a4ce243504614af79d9075057bf99eba` | 5 |

각 `outputs/generation-preview-20261012/browser-final-*/summary.json`에 operation→execution 원 manifest, 관측/묶음 원 응답, 체크포인트와 장부, 중요한 source/build SHA, 원 스크린샷을 보존했다. 검사 전후 해당 SHA 불변·외부 요청 0·page error 0·소유 API/Chrome 정리 PASS다. 사용자 실행 중 프로세스와 프로젝트는 수정하지 않았다.

초기 browser-image-text-01은 harness가 이미 사용한 bootstrap을 다시 전달한 driver 결함으로 FAIL, -02는 재개 질문 이름 변경에 대한 driver의 고정 문자열 때문에 FAIL이었다. 각 원 실패 결과는 남겼다. 단일 새 bootstrap과 현재 질문의 실제 label을 사용하도록 driver를 고친 뒤 새 디렉터리에서 재시험했다. 중간 PASS와 최종 PASS는 합산하지 않는다.

원 사진 실패 execution `9cfea134fcef4293ba815d5447cb87a4`, attempt `539af94963194de5836ba2dd95a3ce0d`의 이미 수신한 관측 JSON 재생만 수행했다. 19행, 바닥 표시 수량 2, 확장된 물체 30개를 보존해 새 검증기 PASS다. 사진을 다시 전송하거나 원 실패를 생성 성공으로 승격하지 않았다. 당시 잘못된 metadata 거절과 뒤따른 출력 중단을 서로 다른 원인으로 구분한다.

## 검사 결과

- 최종 전체 Web **511 PASS / 0 FAIL**, UI 집중 **121 PASS**, 타입·Vite 빌드 PASS. 기존 bundle-size와 jsdom canvas warning은 남았다.
- Core/Provider/API 확장 **865 PASS / 기존 4 FAIL / 469 subtests PASS**, `python-full.xml`. 마지막 변경 집중 **84 PASS / 27 subtests PASS**, `python-final-focused-02.xml`. 중복 검사와 subtest를 독립 시험으로 합산하지 않는다.
- 기존 실패 4개: `test_original_failed_real_packing_response_recompiles_without_source_or_model_change`, `test_last_slot_rolls_back_revalidates_and_stops_for_quality_not_unmapped`, `test_real_generation_service_recovers_bad_support_without_special_ids`, `test_unchanged_repair_still_stops_and_keeps_the_failed_parent_relation`. compiler 버전/미완성 subset/rollback 기대값 검토가 남아 있다. 기대값을 바꿔 전체 PASS로 처리하지 않았다.
- 메타데이터의 잘못된 수량, 구체적 수정 피드백, observation-only 저장 구분, 부모가 없는 자식 대기, 부분 장면의 전체 완료 거절, 실패 후 capture 유지, 프로젝트-local preview/auth/camera 경계, publisher 콜백 누락 복구와 예산 시간 계산을 집중 검사했다. 실제 UI에서 수정·Undo·취소·프로젝트 전환을 전부 인수했다는 뜻은 아니다.
- 초기 샌드박스 tempfile 거절과 두 중간 회귀 FAIL도 원 결과를 보존했다. preview를 지원하지 않는 기존 port에서 추가 checkpoint를 저장하던 결함은 코드를 고쳐 기존 기대값을 유지했다.

## 설정·비용·잔여

UI 보조는 **gpt-6.1-sol high**, 독립 원인/계약 검토 보조는 **gpt-6-astra high**로 명시 지정했다. 보조 최대 2명이며 파일 소유를 분리했다. 주 세션의 실제 모델·추론 수준은 확인/전환 도구가 없어 사용자가 요청한 Sol xhigh와 일치한다고 검증하지 못했다.

새 외부 API **0회 / USD 0**. 이전 사용·UNKNOWN·held와 원 상한은 초기화하지 않았다. 마지막 사진/외부 시험 기간은 만료됐으므로 새 Flash/Super 실호출은 NOT_RUN이다. 설치·Cloud·실물·공개 배포·commit/push는 하지 않았다.

남은 작업 순서:

1. 실행 중인 사용자 TwinPulse/Isaac를 **정상 종료하고 시험용으로 재시작하는 승인**을 받은 뒤, 이 최종 source로 실제 GPU에서 세 입력의 부분 Build/수정 갱신/프레임 중단·회복을 순차 시험한다. 사용자 Kit PID1708은 확인 시 약4.7GB 사용 중이어서 중복 GPU 엔진을 띄우지 않았다.
2. 실제 App/API/Isaac에서 취소·재개·Undo·저장 후 완전히 종료/재열기·프로젝트 전환/늦은 결과를 인수한다. 이번 저장 검사는 ApplicationService 재로드와 브라우저 reload이며 전체 프로세스 재시작이 아니다.
3. 유효한 사진·목적지·기간/잔여 예산 승인에서 운영 Flash/Super로 실제 사진 생성과 수정 품질을 시험한다. 원 사진별 하드코딩/기준 완화 없이 추정/미완성을 유지한다.
4. 기존 4개 회귀 기대값을 별도 검토하고, 사용자 실제 stale/lease 결함을 로그·현재 화면으로 재현해 원인을 확정한다. 저장 JPEG의 cold-session 재표시, 무한 관측/설계 pagination 등 이전 잔여를 새 PASS로 바꾸지 않는다.

따라서 현재 보고서는 **로컬 구현 검증 근거**이며 전체 제품·실제 모델 벤치마크·로봇 준비 완료 보고서가 아니다.
