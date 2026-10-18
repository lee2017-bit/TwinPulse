# 검사 실행 근거 기반 기하 수정·재개 제품 구현

2026-10-10 KST · Baseline v1.0.384 · 계획 1.1 구현 증분 · 전체 PARTIAL / whole=false.

## 결과와 범위

v382의 두 제품 결함을 기존 경로에서 수정했다. 선행 오류를 해결하고 이전 blocked 종속 검사가 실제 실행된 경우 `advanced_checks`로 판정한다. 새 오류 이름만 생기거나 검사 기록을 생략한 경우는 진전이 아니다. 생성 중 및 최종 검사의 drape 오류는 child ID·parent/part·현재/허용 높이·침범량을 잃지 않는다. 특정 사진 ID·가구 좌표·정답 치수 분기를 추가하지 않았다.

새 유료 LLM 호출·사진 외부 전송·로봇/SSH/serial/센서/모터/배포는 모두 0. 설치·시스템 설정·commit/push·새 에이전트 생성도 0. 시험용 HTTP 응답은 명시적으로 격리되며 제품 fallback으로 사용하지 않는다. 실제 Isaac 인수는 아래 텍스트 fixture 경로에 한정된다. 실제 사진 생성의 성공률이나 전체 데모 완료를 뜻하지 않는다.

## 제품 변경

- core `geometry_checks.py`: 후보 revision·compiler/library 버전·대상/의존 필드·검사 ID·실행 상태·blocked 원인·issue 참조를 8개 등록된 compiler phase에 결속한다. 모든 후보를 다시 검사하며 이전 PASS 캐시를 재사용하지 않는다. 현재는 phase 단위 기록이고, 물체별 세분 검사 캐시는 없다.
- `photo_placement.py`/`photo_layout.py`/`semantic_scene.py`: 파생 drape와 최종 배치 검사 모두 typed 오류를 보존한다. 독립 모델 관계/지지면 실패를 모으고, 대상 없는 PHOTO 예외를 room 오류로 추정하지 않는다. 매핑 불가능한 내부 오류는 모델 재요청 대신 중단한다. compiler revision은 1.3이다.
- `generation_policy.py`: best 후보의 검사·수치 high-water와 비교하고 seen/history를 checkpoint에 보존한다. 단계 개방과 기존 제약 악화가 함께 있으면 best 승격/비진전 초기화를 하지 않는다. 검사 버전 변경·잘림·누락·중복 ID·손상된 의존 기록도 성공이 아니다.
- `budgeted_pipeline.py`: 미공개 추정 기하만 남은 예산 안에서 제한 탐색한다. 탐색은 진전이 아니며 실패/취소/소진 시 best를 복원한다. 재개 시 소비된 요청·수정·연속 비진전·시간과 tracker를 보존하고 송신 전에 로컬 재검사한다. 검사 이력이 없는 옛 geometry checkpoint나 이미 소진된 정책은 임의 초기화하지 않는다. 로컬 재검사는 가짜 외부 attempt ID를 만들지 않는다.
- App/API/React: 진전했지만 미완료, 탐색/best 보존, 단계 완료를 구분하고 실제 검사 상태·drape 수치를 기술 상세에 표시한다. 근사 초안/사진 품질/Isaac/SIM/실측/실물은 별도 판정이다. 사진 상대 배치 검사 결과를 현재 후보/plan SHA에 결속하지만 지지 관계·실측·현재 렌더 비교가 없으면 품질은 uncertain이다.
- workflow 종료: 생성 worker 완료 후에도 남은 비동기 진단 쓰기를 해당 로컬 sink에서 bounded flush한다. 물리 STOP/watchdog 경로는 변경하지 않았다.

## 회귀와 실제 실행

겹치는 suite의 건수를 합산한 총계로 표시하지 않는다.

| 검증 | 최종 결과 | 범위 |
| --- | --- | --- |
| Core 전체 | 302 PASS | 로컬 pure/core 회귀 |
| Provider 전체 | 278 PASS / 9.225초 | 기하 loop 24개·재개/예산 포함 |
| 관련 App 통합 9 modules | 225 PASS / 149.584초 | approval/conversation/diagnostics/ownership/photo/workflow |
| chat_site_text_generation | 52 PASS / 26.267초 | 저장·단일 채팅·생성 관계 회귀; 위와 별도 실행 |
| Web 전체 | 440 PASS / 47 files | 기존 UI 회귀 및 단계/품질 표시 |
| TypeScript typecheck / Vite build | PASS | 기존 canvas jsdom 경고·큰 bundle 경고는 남음 |
| 일반 채팅→실제 Isaac | PASS | 고정 HTTP 응답, 실제 승인·재개·compiler·저장·App·Isaac/PhysX |
| 종료 후 디스크 재열기 | PASS | schema2.1·2개 관계·placement 재검사·원 저장 bytes 불변·자동 dispatch 없음 |
| 이전 실제 paid/raw 감사 | AUDIT_PASS_NOT_GENERATION_PASS | 6/10·미사용4·USD.01188129 추정·UNKNOWN/lock0·원 설정/입력/역사 불변 |

v382 원 세 후보를 원 기록 그대로 재컴파일한 양성 회귀에서 `initial → advanced_checks → advanced_checks`, 최종 후보는 계속 미완성으로 남는다. 원 drape는 hanging_clothes→bed/base, 높이0.9m/지지상단0.28m/침범0.62m가 typed 진단에 보존된다. 이 수치는 재현 자료이며 제품 상수가 아니다. 다른 ID/치수의 drape, 수치 개선/진동, 오류 교환, 단계 개방+회귀, 악화 탐색 후 회복, 예산 소진 best 복원, 손상 기록 거절도 통과했다. 원 raw bytes 보존을 테스트에서 대조했다.

실행 명령은 bundled Python의 unittest discover(Core/Provider), 관련 unittest modules, 기존 Web test/typecheck/build 및 다음 고립된 도구다.

`scripts/verify_chat_sim_journey.py outputs/geometry-progress-offline-20261010/ordinary-sim-r3 --case text --budgeted-fixture --ordinary-approval-fixture --site-transport-fixture --diagnostics`

최종 근거: `outputs/geometry-progress-offline-20261010/ordinary-sim-r3/result.json`, `browser.json`, `generated-ready.png`, `generated-physics-arrived.png`, `runtime/provider-evidence/`, `runtime/diagnostics/`.

- 일반 inline 승인2건, 기록된 scripted 요청4건(실제 네트워크0): 출력 length 보호중단→refresh/reload 무재호출→새 명시 승인으로 미완료 단계만 재개→수정1→기하 통과.
- actual engine host PASS, 현재 3D capture PASS, 최대 실제 SIM 변위0.360709936m, arrival completed, Stop paused. Build/Run2/Pause/Reset receipt 모두 succeeded. page_errors/driver_errors0.
- 첫 viewport capture는 `viewport_missing`으로 실패했고 기존 bounded 두 번째 capture가 디코드 PASS였다. 실패를 숨기거나 사진 품질 성공으로 세지 않는다.
- 소유 shutdown succeeded / supervisor stopped, inference source SHA unchanged. 시험 소유 프로세스만 종료했다.
- 종료 후 실제 ProjectStore로 재열기: plan SHA `e212d93ff03c55d0b291f8944368265154c608ed08a09b296ee01f90bf91ed9e`, schema2.1, relation2, source unchanged, 자동 Build/Run0. 텍스트 fixture이며 침실 사진 결과가 아니다.

## 최초 실패와 정정 이력

1. 초기 temp/subprocess 권한 또는 PYTHONPATH 누락은 허용된 로컬 실행과 올바른 import 경로로 재검증했다. 권한 거부를 시스템 설정으로 우회하지 않았다.
2. 이전 '새 단계도 비진전' 회귀 기대는 실제 검사 실행 근거를 가진 양성 사례와 이름 교환/검사 생략 음성 사례로 교체했다.
3. 관련 App 최초 224 실행 중 S2b teardown 3건의 WinError145/32를 보존한다. 생성은 끝났지만 diagnostic writer가 남은 경쟁 상태를 bounded flush로 수정; S2b7 및 최종 관련225 PASS.
4. 일반 Isaac 최초 `ordinary-sim`은 시험 응답의 standalone base_revision이 실제 입력/근거에 결속된 후보와 달라 `SEMANTIC_CONSTANT_MISMATCH` 후 scripted 응답 소진으로 FAIL했다. r2는 wire의 const→singleton enum 정규화를 시험 fixture가 반영하지 못해 `'const'` FAIL. fixture가 현재 wire 계약의 revision만 사용하도록 정정하고 r3 PASS. 제품의 stale revision 보호를 풀거나 응답 수를 늘려 모면하지 않았다. 앞 두 결과/이미지는 보존한다.
5. 재열기 수동 진단 최초는 취소 gateway를 None으로 만든 도구 오류로 종료 시 AttributeError. 외부 통신 없는 cancel interface를 제공하여 재검증 PASS; 제품의 gateway 계약을 완화하지 않았다.

## G0–G6 현재 판정과 남은 일

| 단계 | 판정 | 정확한 범위 / 잔여 |
| --- | --- | --- |
| G0 | DONE | v382 세 후보·진전 오판·drape 근거 회귀 |
| G1 | DONE for listed matrix | 실행 phase 기록·typed 파생/최종 진단·매핑 실패 중단; 전체 라이브러리의 모든 미지 예외 보장은 아님 |
| G2 | PARTIAL | best/high-water/탐색/복원/소비 예산·tracker 재개 PASS. graph 밖 scope 제안→host 확인→범위 확대 wire protocol은 아직 없음 |
| G3 | PARTIAL | 단계/품질 DTO·UI·현재 관측 상대 관계 검사 연결. 현재 렌더 critic→품질 patch→기하·Build·렌더 재검증 자동 loop 미구현 |
| G4 | DONE for listed offline matrix | suite·일반 approval/resume·actual Isaac fixture·저장·로그 감사. actual LLM 품질 인수 대체 아님 |
| G5 | NOT_RUN for this revision | 새 actual LLM 회복/새 자연 생성 미실행. 예전6/10(잔여4), 별도9/10(잔여1), terminal·수정/시간을 초기화하지 않았음 |
| G6 | PARTIAL | 텍스트 fixture의 실제 engine/current3D/PhysX/Stop/재열기 PASS. actual 사진 품질 수정 결과의 동일 revision 렌더 인수 NOT_RUN |

다음 순서: (1) graph 밖 범위 제안 계약과 host 검증 (2) 현재 렌더·관측 관계에 근거한 품질 수정/기하 재검사/Build 재결속 (3) 유효한 명시 재개·예산에서 actual LLM 저장 실패 회복 및 별도 새 자연 생성 (4) 같은 수락 결과의 실제 Isaac 품질 인수. 이는 로봇 없이 가능한 잔여다.

기존 v382 checkpoint에는 새 검사 tracker가 없고 compiler 버전도 다르다. 자동으로 새 이력을 넣거나 stalled/repair 예산을 0으로 만들지 않는다. 옛 원 후보/원 로그로 로컬 이력을 재구성한 파생 자료와 명시 재개 범위를 먼저 검증해야 한다. 남은 HTTP4를 수정4회나 새 전체 생성 충분 조건으로 해석하지 않는다. 기존 별도 scope·사진 정밀도·도메인/warehouse/openings·가격/패키지·규정·실물 인수 잔여도 유지한다. 로봇은 현재 생성 결함 수정의 병목이 아니다.
