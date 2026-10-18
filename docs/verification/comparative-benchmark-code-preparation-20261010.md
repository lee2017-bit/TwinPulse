# 비교 벤치마크 선행 코드 검증

2026-10-11 · 최신 Baseline v1.0.402 · 범위: 오프라인 코드·회귀·저장 원본 재분석

## 실행 환경과 독립 평가 결속 v402

동일 조건 비교시험에서 실행 파일·3D 자산 또는 평가표가 달라지는 경우를 기존 manifest→campaign→ordinary runner→원본 감사→collector 경로에 연결했다. **이 경로의 오프라인 계약 검증은 통과했다. 실제 LLM/Isaac 시험과 독립 데이터·사람 정답 확보는 완료하지 않았다.**

### 구현한 조건 고정

`comparative-benchmark-1.2`는 카탈로그에 더해 실행 환경 파일, 선택한 평가표 파일, 선택적인 사람 검토 provenance 파일을 SHA로 묶는다. 평가표는 CLI에서 동결 여부를 확인하는 기존 기능이 이미 있었다. 이번 변경은 여러 동결 평가표 중 선택을 manifest에 명시하고, 프로그램에서 직접 collector를 호출할 때도 다른 평가표로 바꿀 수 없게 한다. 파일 SHA와 canonical 평가표 SHA를 구분하며 답안 파일도 freeze에 포함한다. 기존1.0/1.1 읽기는 유지하고 환경·평가 선택이 없는 결과는 `LEGACY_PARTIAL_FREEZE`로 공개한다.

`benchmark_environment.py`는 실제 ordinary 경로의 PC Python, PATH Node, 고정 Chrome, Isaac VERSION/launcher/setup/Kit/Python 진입 파일 9개의 SHA·크기, PC Python package 버전 metadata, OS/아키텍처/논리 CPU 수를 읽는다. Burger의 기존 reviewed manifest로 검증한 USD dependency closure 9개를 source freeze에 포함한다. 파라메트릭 가구는 기존 코드 SHA로 동결한다. 실행·서비스·GPU 조회·인증 읽기·네트워크·설치·시스템 변경은 하지 않는다.

전체 Isaac/browser/Python 설치의 DLL·extension·wheel 내용은 재귀 동결하지 않았다. GPU·드라이버는 `NOT_OBSERVED`, actual Isaac readiness는 `NOT_RUN`이다. 버전 metadata만으로 package bytes가 같다고 보장하지 않는다. 따라서 **진입 파일과 reviewed 자산이 일치한 결과를 전체 설치 재현성 또는 Isaac PASS로 표시하지 않는다.** `PYTHONEXE` override, missing Node, runtime/host/package metadata 변경 또는 unreviewed 자산은 해당 경로에서 차단한다.

campaign은 변경을 비용 예약과 child 실행 전에 확인하고, child도 키 registry/credential 경계 전에 재확인한다. 실행 전후 환경 증거의 동일 SHA는 승인 기록과 outer summary에 연결되며 원본 감사와 collector가 검사한다. 후속 환경 증거가 없거나 바뀌면 generation/engine 결과가 PASS여도 정상 정산으로 승격하지 않고 UNKNOWN/held를 유지한다. 입력·소스·가격·UTC 만료·paired budget·5모델/length/402 중단 기준은 그대로다.

### 독립 답안을 준비하는 상태

`prepare_benchmark_evaluation.py`는 manifest의 입력 SHA와 선택 평가표 SHA를 넣은 빈 annotation worksheet와 `label-review-draft.json`을 만든다. 물체·관계·크기·검토자·실측은 채워 넣지 않는다. draft schema는 완성된 답안으로 받아들이지 않으며 `PENDING_HUMAN_LABEL_REVIEW`이다.

1.2에서 품질 채점에 사용할 답안은 기존 엄격 annotation 계약, coverage, 입력/평가표/답안 SHA, 검토자 일치와 별도 provenance를 통과해야 한다. provenance는 source=`human`, blinded, 출력 열람 전 검토 여부와 검토시각을 **사람이 선언한 자료**다. 사람 신원을 자동 검증했다는 뜻은 아니며 공개 결과도 `human_identity_verified=false`로 남긴다. 한 명 검토는 두 명 독립 평가로 표시하지 않는다. 실제 2인 일치도/adjudication은 아직 없다.

최종 holdout은 답안·사전 검토가 준비되지 않거나 검토시각이 미래이면 예약 전에 차단한다. collector도 실행 시작 후 검토한 답안으로 해당 결과를 품질 PASS로 만들지 않는다. 개발 smoke는 답안이 없어도 별도 승인 범위에서 실행할 수 있지만 품질은 NOT_EVALUATED다. 같은 text 입력은1.2에서 같은 room group이어야 하며, 개발/holdout 사이 동일 group 누출을 막는다. 의미가 비슷한 paraphrase/crop의 그룹 지정은 사람 검토가 필요하다. 평가표·답안·환경 정보는 모델에 보내는 journey packet에 들어가지 않는다.

### 검증 근거

| 확인 | 결과와 범위 |
| --- | --- |
| 새 환경·평가 계약 회귀 | 16개. 환경/host/package/asset 변조, alternative frozen rubric, secret field/relative path, pre-reservation/pre-credential 차단, 실행 후 증거 누락, draft·provenance·coverage·text group·legacy 호환·공개 정보 제한 |
| 관련 벤치마크 통합 회귀 | 105 PASS / 3.227초. 위16개 포함; 중복 합산 금지 |
| Core 전체 | 302 PASS / 26.459초 |
| Provider 전체 | 332 PASS / 7.541초 |
| 실제 로컬 파일 동결·준비 경로 | `environment-v402.json`, `package-v402-r2/result.json`에서 source/asset520개, runtime9개, reviewed Burger9개, 기존 원본39개 SHA 불변 |
| 데이터와 외부 실행 | 자가 작성 text 계약 입력2개·독립 데이터0개·평가표는 PROVISIONAL_CONTRACT_ONLY. HTTP0/credential0/Isaac NOT_RUN/robot0 |

새 source는 `benchmark_environment.py`, `benchmark_evaluation.py`, `prepare_benchmark_environment.py`, `prepare_benchmark_evaluation.py`, `verify_benchmark_package_offline.py`다. 기존 `benchmark_protocol.py`, `benchmark_campaign.py`, `run_ordinary_staged_live_ten.py`, `collect_comparative_benchmark.py`를 함께 수정했다. Web 소스/빌드는 변경하지 않았고 이번 Web/Node/type 전체 재시험은 하지 않았다. v401 결과를 이번 새 실행으로 세지 않는다.

최종 동결 파일은 `outputs/benchmark-code-preparation-20261011/package-v402-r2/manifest.json`·`prepared.json`·`pending-worksheets.json`이다. 환경 identity는 `9bb700b130d6fb3889d5729661f73e5d6831a1bccdb91b29d8f7619663a9cce1`. 이는 timestamp를 제외한 환경 identity이며 manifest의 원파일 SHA와 다르다. synthetic 입력은 전송 권한 false, 금융 승인 없음이다. 이 패키지는 실제 모델 비교 실행이나 최종 평가표 승인이 아니다. 앞 `package-v402/`는 후속 legacy/draft 보완 전 동결본으로 보존하며 현재 비교군과 합치지 않는다.

문서 동기화 후 최종 점검에서도 Python AST10개, 저장 prepared와 재계산의 동일성, source/asset520개와 현재 runtime identity, 원본39개 SHA, 기준 문서6개의402 연결을 확인했다. scoped `git diff --check`는 오류 없이 끝났고 기존 LF→CRLF 경고만 있었다. 검사 대상 중 새 untracked 파일은 Git diff 검사와 별개로 AST/동결 SHA로 확인했다.

### 최초 실패와 처리

- 첫 회귀의 임시 파일 생성·cleanup PermissionError는 제품 FAIL과 분리한다. 이 시도는54개/80 ERROR였고, imported TestCase의 중복 발견도 포함됐다. 후속 중복 import를 제거했다.
- 승인된 새 outputs 생성도 sandbox에서 두 차례 거부됐다. 정확한 폴더만 만드는 별도 승인 명령으로 저장했으며 ACL·시스템 권한은 변경하지 않았다.
- 정상 로컬 집중38개에서 잘못 지정한 credential mock 메서드 `read` 때문에1 ERROR였다. 실제 `load` 경계로 수정하여38 PASS를 확인했다.
- 확대104개에서 legacy job에 `split`이 없는7 ERROR를 재현했다. 새 evaluation 계약이 있을 때만 holdout guard를 적용하도록 수정하여104 PASS, 추가 legacy 회귀 후105 PASS였다.

### 남은 순서

1. 독립 사진/text와 라이선스·전송/공개 가능 범위를 확보하고, 사람 답안·blind 검토·최종 rubric을 동결한다. 기존 침실은 개발군으로 유지한다. worksheet 생성은 이 작업의 완료가 아니다.
2. GPU·driver·설치 의존성의 비교 범위를 명시하고 새 cohort의 실제 runtime 관측을 보완한다. 전체 설치 byte closure는 NOT_FROZEN이다.
3. 새 유효한 공급자별 비용·사진/파생 렌더 전송 승인을 받은 후 actual photo/text와 질문/거절 Isaac smoke를 실행한다. 종료된 옛 USD5/USD1 grant는 재사용하지 않는다.
4. 개발군 선별과 holdout의 동일 조건 반복·독립 품질/불일치·비용/시간·방 단위 통계를 수집한 뒤 제약별 조합을 추천한다. 독립 repair/critic 역할 라우팅도 별도 미구현으로 남는다.

전체 제품과 벤치마크는 PARTIAL / whole=false이며 예약은 PAUSED다. 기존13개/5PASS·전체19개/129HTTP, 원 실패·전역 설정·장부/held·실물 guard는 보존했다. 로봇은 이 오프라인 잔여의 선행조건이 아니다.

아래 v401 이하는 당시 이력이다.

## 모델 카탈로그와 진단 과제 연결 v401

소수 모델의 고정 허용 목록 때문에 새 모델이 일반 App에서 실행되지 못하던 경로를 시험별 동결 카탈로그로 확장했다. 목표의 정상 거절과 선택 질문도 기존 채팅/API/브라우저 시험 경로에 연결했다. **카탈로그·입력·승인·진단 판정의 오프라인 인수는 통과했다. 새 실제 모델 호출과 Isaac 브라우저 인수는 NOT_RUN이며 전체 벤치마크는 PARTIAL이다.**

### 같은 설정으로 모델 시험하기

`stage-model-catalog-1.0`은 모델 ID, 공개 여부, text/image 역할, 문맥 한도, 입력·출력 가격과 출처 SHA·UTC 유효기간만 저장한다. 저장된 2026-10-10 Nebius inventory에서 25개 모델을 정규화했으며 계정·인증 정보는 옮기지 않았다. 결과는 다음과 같다.

| 범위 | 오프라인 확인 | 실제 성능·현재 계정 가용성 |
| --- | --- | --- |
| 관측 | 이미지+텍스트 역할 9개, 일반 gateway/InputRevision 계약 통과 | NOT_RUN / NOT_CHECKED |
| 설계 | 텍스트 역할 24개, 일반 gateway/InputRevision 계약 통과 | NOT_RUN / NOT_CHECKED |
| 비생성·역할 미지원 | 전체 25개 목록에 제외 사유 유지 | 열등한 모델이라고 판정하지 않음 |
| 수정·생산 critic | 수정은 planner, critic은 observer와 같은 모델을 사용 | 독립 역할 조합은 NOT_IMPLEMENTED |

근거는 `outputs/benchmark-code-preparation-20261010/catalog-v401.json`, `catalog-v401-report.json`, `catalog-adapter-v401-r2/result.json`이다. 마지막 검증은 socket 연결과 credential 읽기를 차단한 생성자/입력 계약 시험이다. 33개 역할 계약을 실제 모델 성공 33건으로 세지 않는다. 카탈로그 유효기간은 **2026-10-16 00:00 UTC 미만**이며 새 실제 시험 직전에 공급자 metadata와 계정 `/v1/models`를 조회해 가격·문맥·역할·가용성을 다시 대조한다. 엄격 JSON 출력 지원은 저장 목록만으로 보장하지 않는다.

manifest 1.1은 카탈로그 파일과 SHA를 동결하고 최대256개 구성을 선언할 수 있다. 기존1.0 형식과 이전 hash는 유지한다. 카탈로그 식별값은 격리된 App 라우팅, 비밀을 포함하지 않는 InputRevision, 승인 미리보기, 승인 scope의 가격표·장부, 실행 감사까지 같은 값으로 연결된다. 전역 키·모델 설정에는 자동 적용하지 않는다. 카탈로그 변조·만료·미래 시각·가격 누락·잘못된 역할은 호출 전에 차단한다. 카탈로그를 제거해도 임시 가격이 기본 설정에 남지 않는다.

전체 manifest에 미지원 구성이 섞이면 admission을 막는 정책은 유지했다. 역할이 지원되는 구성을 시험 전에 선언하고, 제외 모델·사유는 별도 지원표에 남긴다. 결과를 본 뒤 실패 모델을 삭제하거나 다른 모델로 대체하지 않는다. 문맥 전체의 보수적 비용 예약·공급자별 한도·paired block·held·length/402/역할별5모델 연속 중단은 그대로다. 비싼 모델의 예약이 현재 trial USD cap을 넘으면 NOT_RUN이다. 공통 상한을 늘리려면 다음 cohort의 명세와 승인에 먼저 반영해야 한다.

### 질문과 거절의 판정

App은 `simulation_goal_clarification`과 typed `simulation_goal_rejected`에 request ID·현재 scene revision을 기록한다. 브라우저 시험은 선언된 목표를 일반 채팅에 입력하고, 입력 전후의 실제 workflow/operation/idle pose 및 새 API 이벤트를 비교한다. 선택 질문에 자동 답하거나 Run을 누르지 않는다. 질문은 같은 revision의 대기 카드와 활성 대상2개 이상, 거절은 알려진 의미적 거절 원인을 요구한다. 내부 오류·stale·시작점 누락·host 예산 소진을 정상 거절로 인정하지 않는다.

`benchmark_diagnostic.py`는 case/goal SHA, request ID, 이벤트 순서, scene/plan/input, operation 목록, 현재 pose·telemetry, 실행 권한 부재를 확인한다. 이전 이벤트, 새 Run, 위치 상실, 입력 혼입, 잘못된 카드와 손상된 저장 자료는 typed 실패다. raw 감사 후 collector가 판정 근거 SHA를 기록한다. accounting/public schema1.2는 `qualified_diagnostic_pass`를 별도 집계한다. 진단 과제의 의미 목표 도착과 움직이는 중 Stop은 NOT_EVALUATED이며 full PASS·양성 완료율·arrival paired 통계로 승격하지 않는다. 새 실제 Isaac에서 이 브라우저 분기를 실행한 인수는 아직 필요하다.

### 회귀와 오류 기록

| 확인 | 최종 결과 |
| --- | --- |
| Core 전체 | 302 PASS / 26.341초 |
| Provider 전체 | 332 PASS / 7.560초 |
| 웹 전체 | 445 PASS / 26.21초, 47파일 |
| 명세/campaign/진단/집계/App 라우팅·승인·채팅 API | 144 PASS / 54.103초 |
| 독립 품질/프로파일 집계/공개 collector/기존 모델 보고서/카탈로그 장부 | 30 PASS / 0.794초; 위144와 일부 겹침 |
| Node 정지·진단 정책 / 브라우저 구문 | 4 PASS / syntax PASS |
| App/Node TypeScript noEmit | PASS; 웹 source/dist는 새로 변경하지 않음 |
| 변경 Python 구문 / scoped diff check | 28파일 AST PASS / PASS; 기존 LF/CRLF 안내 유지 |
| 카탈로그 ordinary gateway/InputRevision | 관측9·설계24 PASS, HTTP0, credential0, 원본39 SHA 불변 |
| 새 실제 모델·사진 전송·Isaac·로봇 | NOT_RUN / 0회 |

겹치는 suite를 합산하지 않는다. 웹의 jsdom canvas 경고는 기존 가상 UI 한계이며 실제 렌더 확인이 아니다. 개발 중 처음143개 회귀에서 modality 목록 순서와 가격 누락 보호 실패가 나왔다. 가격표를 재설정하던 병합을 임시 effective 가격으로 수정해 누락 보호를 유지했다. 다음145개 회귀에서 InputRevision의 카탈로그 식별값 거절을 발견해 비밀 없는64hex 계약을 추가했다. 이후57개 회귀의 optional 진단 verdict shape 오류를 수정했다. 공개 collector29개 회귀의 이전 INELIGIBLE 기대는 새 adapter 지원 상태로 갱신하고, 증거 없는 diagnostic PASS가 생기지 않는 반례를 추가했다. 최종 결과는 위 표와 같으며 초기 실패를 모델 성적으로 세지 않는다.

새 preparation CLI의 core import 누락도 수정했다. sandbox temp write/cleanup PermissionError와 Node subprocess EPERM은 별도 개발 환경 실패로 남겼다. 첫 `catalog-adapter-v401` 실패 디렉터리를 보존하고 승인된 좁은 로컬 실행의 새 `catalog-adapter-v401-r2`에서 검증했다. Node 정책은 단일 프로세스로 실행했다. ACL·시스템 설정 변경이나 권한 거부 우회는 하지 않았다.

### 남은 작업 순서

1. 독립 photo/text 개발·holdout 입력, 인간 annotations·blind frame review·평가자 일치도와 rubric 동결. 기존 침실은 개발군이며 실측 없는 크기는 추정/미검증이다.
2. UI/engine/assets/prompt/schema/evaluator와 실제 runtime·hardware 환경을 포함한 freeze, 다음 시험의 공통 trial 비용/기간·원본/파생 렌더 전송 승인 확정. 종료된 과거 USD5/USD1 grant는 재사용하지 않는다.
3. 새 유효 승인에서 actual 모델 photo/text 생성→현재 render→save→의미 목표 이동·moving Stop/reload/reopen smoke와 별도 진단 거절/질문 smoke. 실패하면 정확한 단계로 기록하고 수정 후 새 cohort로 재검증한다.
4. 개발 선별·최종 표본수/비용 확정→holdout→제약별 추천과 공개. 독립 repair/critic 조합까지 비교하려면 그 역할 라우팅을 추가 구현해야 한다.

이번 paid/사진 전송/Isaac/로봇/배포/설치/commit/push0. 원 최신13시험/5PASS·전체19시험/129HTTP, 전역 설정·원 실패·과거 장부와 held, 실물 guard·whole=false·예약 PAUSED는 변경하지 않았다. 원본39파일과 입력 카탈로그 SHA 불변을 재확인했다. 저장된 catalog의 역할 표는 현재 모델의 품질이나 전체 실물 준비 상태를 증명하지 않는다.

아래 v400 이하는 당시 이력이다.

## 프로파일 교정과 결과 분모 보호 v400

기존 실행ID의 함수 계측 오류를 재현·수정하고, 계측 비용과 결과 분모를 검증했다. **계측·집계의 오프라인 인수는 통과했다. all-model/진단 실제 adapter·독립 데이터 품질·새 실제 LLM/Isaac 인수는 PARTIAL이다.** 과거 모델 성적을 새 코드 성적으로 옮기지 않는다.

### 함수 계측: 원인과 제품 경로 수정

원 `luna-luna-2` 실행ID `f4fd8928414b4f4495128b08f2045e52`의 deepcopy는 self 0.359375초/cumulative 0초, `luna-luna-4` 실행ID `4f600468b2f44ff782cab6268f699f0a`의 validate_placement_plan은 self 1.015625초/cumulative 0.296875초였다. 원 이벤트·실패·summary는 변경하지 않았다.

로컬 재현에서 기존 custom thread CPU timer가 서로 다른 두 스레드에서 호출되고 음수 시간이 발생했다. [CPython 3.12.14 `_lsprof.c` 구현](https://raw.githubusercontent.com/python/cpython/v3.12.14/Modules/_lsprof.c)은 interpreter-wide monitoring callback과 하나의 profiler stack을 사용한다. 다른 스레드의 CPU clock이 같은 stack에 섞이는 것이 원인이다. Wi-Fi·LLM·로봇 문제가 아니다.

`execution_diagnostics.py::profile_call`은 owner-thread callback만 C profiler에 전달하고 ns timer를 사용한다. nonblocking guard로 계측 충돌을 SKIPPED/FAILED로 기록하되 **제품 함수는 한 번만 실행**하며 원 예외를 보존한다. 기존 외부 profiler를 바꾸거나 종료하지 않는다. 지원되지 않는 runtime도 계측만 실패한다. 모든 함수 행을 검사한 뒤 최대30행을 저장하므로 낮게 순위된 비정상 값도 전체 profile을 무효화한다. 같은 이름의 서로 다른 generator는 source line으로 구분한다.

`profile_snapshot`은 검증된 owner-thread/profile/span 결속 및 완전한 이벤트만 진단용 순위에 넣는다. legacy·비정상·잘린 이벤트·degraded는 제외 상태로 남고 소급 교정하지 않는다. App의 실행ID 화면도 원 수치를 유지한 채 Validated/Uncalibrated/Invalid/Incomplete와 계측 한계를 표시한다. wall/HTTP 시간과 제품 승인 기준은 바꾸지 않았다.

### 교정과 오버헤드

최종 근거 `outputs/benchmark-code-preparation-20261010/profile-calibration-v400-r3/result.json` PASS (`r1/r2`도 보존). CPython3.12.14/Windows AMD64/논리CPU12, socket 전송 차단 상태에서 중첩·재귀·CPU/wall 대기·다른 busy thread·동시 profiler와 저장 후보2개 각4반복을 검사했다. 원 campaign/project/diagnostic **39파일 SHA 불변**, 계측 코드3파일 SHA 불변, 두 원 저장 후보의 재컴파일 계약 일치. 이3개 SHA는 full product/runtime/asset freeze가 아니다.

| 저장 후보 | OFF 평균 wall | ON 평균 wall | OFF CPU 0초 표본 / 4 |
| --- | ---: | ---: | ---: |
| Luna/Luna2 | 0.0027733초 | 0.025233875초 | 3 |
| Luna/Luna4 | 0.00264875초 | 0.023490425초 | 4 |

45ms 대기는 thread CPU 0초/wall 약45–47ms로 분리됐다. 짧은 CPU는 Windows에서 0으로 양자화될 수 있고 callback 계측 오버헤드가 크다. 이는 **thread 혼입/수치 무결성과 오버헤드 검사**이지 정밀 CPU 인증이나 모델 속도 순위가 아니다. 모델 속도는 계측 OFF wall/HTTP를 주 지표로, ON은 별도 진단 lane으로 사용한다. 누적 시간은 호출 관계가 겹치므로 합산하지 않는다.

### 성공률과 adapter 지원표

accounting/public exporter schema1.1은 `expected_outcome`별 분모와 주 도달 모집단을 구분한다. diagnostic rejection/clarification은 full arrival PASS·양성 완료율·arrival paired 통계에 들어가지 않는다. actual 진단 adapter는 아직 `NOT_IMPLEMENTED`다. 원 단계 수치는 보존하고 공개 파생 trial의 arrival만 NOT_EVALUATED로 명시한다.

`eligibility_matrix`는 예정 job을 모두 유지하면서 REVIEWED_ADAPTER_SUPPORTED/INELIGIBLE/NOT_EVALUATED와 typed 사유를 공개한다. 이것은 로컬 계약 검사이지 현재 계정 가용성·승인·품질 확인이 아니다. account availability는 NOT_CHECKED_NO_NETWORK다. 미지원 모델이 섞인 전체 manifest의 admission을 막는 기존 정책은 유지했고 대체 모델로 실행하지 않았다.

### 최종 회귀와 개발 중 오류

| 확인 | 결과 |
| --- | --- |
| Core 전체 | 302 PASS / 25.653초 |
| Provider 전체 | 327 PASS / 13.469초 |
| 웹 전체 | 445 PASS / 25.21초; source-line 표시 보완 후 관련18개 PASS |
| 명세/campaign/collector 실제 CLI/품질/집계/legacy 보고서/계측 | 76 PASS / 1.145초 |
| 실행ID 저장·조회·export/기존 진단·교정/집계 | 145 PASS / 69.163초; 위76과 겹침 |
| App/Node TypeScript noEmit, Vite build | PASS; 기존 chunk>500kB 경고 유지 |
| 변경 Python AST11개·브라우저 시험 syntax·scoped diff check | PASS; 기존 LF/CRLF 안내 유지 |
| 새 actual LLM/브라우저/Isaac·로봇 | NOT_RUN / HTTP0 |

겹치는 suite는 합산하지 않는다. jsdom canvas 경고는 기존 가상 UI 한계이며 actual 렌더 PASS가 아니다. 최초 Vite/Vitest spawn EPERM은 승인된 좁은 로컬 실행으로 재검증했고 설치/ACL 변경0이다. 초기 stdlib profile.Profile 대안은 동시 Bad return으로 실패해 폐기했다. 원 cProfile 재현의 teardown timer 오류 때 소유 시험 프로세스만 중단했다. sleep 이름 assertion은 sanitize된 함수명에 맞춰 수정했다. 교정 명령1개는 web cwd에서 script를 찾지 못해 실패했으며 root에서 별도 재실행했다. 이 개발 오류는 모델 성적 분모에 넣지 않는다.

### 정확한 잔여와 다음 순서

1. B1: 모델별 실제 역할 가용성/계약 검토와 fresh all-model·expected rejection/clarification adapter 확장. 지원표만으로 완료 처리하지 않는다.
2. B2: 독립 photo/text 개발·holdout 자료, 인간 labels·blind frame review, 평가자 일치도와 rubric 동결. 기존 침실은 개발군·실측 없는 크기는 추정/미검증이다.
3. B3: UI/engine/assets/prompt/schema/evaluator 전체 source/runtime/hardware 동결 후 새 유효 비용/원본·파생 렌더 승인에서 photo와 text actual LLM→현재 render→save→의미목표 이동→moving Stop/reload/reopen smoke. CPU 교정은 이번 완료, 새 runtime/asset/browser smoke는 미완료다.
4. B4–B6: 개발 선별·표본 수/비용 확정→holdout→제약별 추천·공개. 미실행/미평가/실패·불명 청구 예약을 유지하고 결과를 본 뒤 변경하면 새 cohort로 구분한다.

이번 paid/사진전송/Isaac/로봇/배포/설치/commit/push0. 원 최신13시험/5PASS·전체19시험/129HTTP와 설정·장부·실물 보호·whole=false·예약 PAUSED 불변. 로봇은 이 잔여 오프라인 작업의 선행조건이 아니다.

아래 v399 이하는 당시 이력이다.

## 후속 구현 결과 v399

부착물 경계의 확인된 결함을 수정하고, 동결된 명세를 기존 일반 App 시험기에 연결하는 캠페인 제어기와 독립 품질 평가·결과 수집기를 구현했다. **확인된 B0 결함과 이 범위의 오프라인 인수는 통과했다. B1/B2의 검토된 조합 경로는 오프라인 검증됐지만, 모든 모델·기대 거절 경로·실제 새 명세 시험은 아직 PARTIAL이다.** 새 모델 성능 결과나 전체 데모 완료가 아니다.

### 부착물 경계와 원본 수정 이력

기존 배치 계산은 침대 등 부모 물체만 바닥에 맞추고, 걸친 이불과 확장된 entanglement keepout은 고려하지 않았다. 이제 같은 파라메트릭 라이브러리의 anchor·회전·확장된 시각 부품·안전 영역을 계산하여 부모와 drape 부착물의 합성 범위를 예약한다. 사진별 ID·좌표·정답 치수를 추가하지 않았고, 입력 방 크기·물체 치수·관계·다른 물체를 바꾸거나 삭제하지 않는다. 실제 자식 높이 및 바닥침범 검사는 여전히 core에서 수행한다.

범위는 부모 중심의 보수적 대칭 envelope이다. 비대칭 모양의 실제 여유 공간보다 크게 잡아 가능한 배치를 거절할 수 있고, surface 부착물 전체를 다루는 임의 형상 solver는 아니다. 10cm 격자·512노드·2초·분기32·기존 여유폭은 그대로다. 이 제한 탐색의 거절을 연속 공간 전체의 불가능 증명으로 쓰지 않는다. 네 anchor×네 회전, 다른 물체 보존, 큰 부착물을 축소하지 않는 반례와 기존 작은 완전탐색·되돌림 회귀가 통과했다.

최종 파생 근거는 `outputs/benchmark-code-preparation-20261010/saved-geometry-attachment-patch-r3.json`이다. 원본 JSON·사진192개와 진단 코드6개 SHA가 실행 전후 동일하며 HTTP0이다. 원 patch의 요청·응답 SHA, 적용 전후 revision·changed IDs·보존 sibling·원 ProgressTracker의 summary 제외/순서 정규화 identity를 대조했다.

| 원 시험 | 실제 원 patch 대조와 현재 무료 재분석 |
| --- | --- |
| Flash/Luna3 | 원 적용 patch3개 모두 revision·changed IDs·진전 기록 결속. 원 결정은 `advanced_checks`→`exploring`→`rollback`; best 복원 revision 일치. 현재 저장 snapshot4개는 EMPTY_DOMAIN/BRANCH_BUDGET_EXHAUSTED/EMPTY_DOMAIN/EMPTY_DOMAIN으로 거절 |
| Flash/Lightning4 | 적용 patch2개는 원 기록과 결속, `advanced_checks`→`exploring`. 나머지 원 수정 응답1개는 `SEMANTIC_SCOPE_REQUEST_REJECTED`로 적용되지 않음. best 복원 revision 일치. 현재 저장 실패 후보2개는 NODE_BUDGET_EXHAUSTED |
| Luna/Luna5 | 원 scene와 원 마지막 pose의16후보 중14 START_OR_GOAL_BLOCKED·2 NO_PATH. 원 FAIL 유지 |

일부 바닥경계 실패가 더 이른 typed packing 거절로 바뀐 것은 검사가 진전된 결과이지 실제 생성 회복 성공이 아니다. 이전 파생 JSON도 삭제·덮어쓰지 않았다.

### 캠페인 제어와 같은 조건 실행

`scripts/benchmark_campaign.py`를 기존 `run_model_combination_benchmark.py`의 별도 manifest lane에 연결했다. 기존 단일사진 캠페인 형식·장부를 이관하거나 수정하지 않는다.

- 승인 파일은 명세 SHA·승인 ID·현재 인간 승인 문구·UTC 시작/만료·공급자별 상한/기존 노출·원본과 파생 렌더 전송 범위를 별도로 요구한다. 데이터 전송 허용 표시는 금융 승인으로 바뀌지 않는다.
- 검토된 프로필은 HTTP24와 고정 trial USD cap을 모든 조합에 동일 적용한다. mixed trial의 최대 가능 금액을 각 공급자에 보수적으로 예약하고, 미정산·불명·청구 usage 없는 held 금액을 유지한다. 부족하면 다음 조합의 조건을 줄이지 않고 paired block을 미실행으로 남긴다.
- 순서와 원 실행을 보존해 재개하며 실패를 다시 실행하지 않는다. 명시 `--reconcile`은 남은 원 하위 실행을 감사할 뿐 새 HTTP를 만들지 않는다. 승인 변경·소스/입력 변경·미정산·다른 소유자의 lock은 진행을 차단한다. 기존 lock을 자동 삭제하거나 PID를 강제 종료하지 않는다.
- 출력 `length`, 공급자402, 역할별 서로 다른 모델5개의 연속 동일 원인 실패는 새 실행을 중단한다. 성공·원인 귀속 불명 결과를 history에 남겨 비연속 실패를 연속으로 세지 않는다. 조합5개나 같은 모델5반복을 모델5개로 세지 않는다.
- 새 시험 시작에 최소30분의 승인 잔여시간을 요구하고, 하위 App에 만료시간을 전달하여 `AuditedChatTransport`가 worker admission 이후와 실제 HTTP 직전에도 검사한다. 이미 보낸 요청의 늦은 결과·비용 정산은 막거나 환불하지 않는다. 환경 변수는 권한을 제한할 뿐 승인하지 않는다.
- full source inventory와 추가 rubric/평가 파일을 함께 동결할 수 있다. 기존 ordinary App/브라우저 경로에 입력과 목표만 전달하며 annotation을 생성·수정 feedback에 넣지 않는다. OpenAI-only 조합은 사용하지 않는 Nebius 키/metadata를 요구하지 않는다.

검토된 actual adapter 범위는 observer Flash/Qwen/Luna, planner Lightning/Luna, repair=planner·critic=observer이다. all-model 및 독립 repair/critic 역할, diagnostic 기대 거절 lane은 **명시 ineligible**이며 지원 성공으로 계산하지 않는다. 이번에는 `--run-next`를 실행하지 않았다.

새 lane의 실행 위치는 다음과 같다. `MANIFEST`, `AUTHORIZATION`, `CAMPAIGN`, `REPORT`는 실제 동결 파일/새 폴더를 지정할 자리이며, 아래는 이번 유료 실행 승인이 아니다.

```text
python scripts/run_model_combination_benchmark.py CAMPAIGN --manifest MANIFEST --authorization AUTHORIZATION --initialize
python scripts/run_model_combination_benchmark.py CAMPAIGN --manifest MANIFEST --authorization AUTHORIZATION
python scripts/run_model_combination_benchmark.py CAMPAIGN --manifest MANIFEST --authorization AUTHORIZATION --reconcile
python scripts/collect_comparative_benchmark.py CAMPAIGN --manifest MANIFEST --authorization AUTHORIZATION --rubric RUBRIC --visual-reviews REVIEWS --output REPORT
```

initialize/report/reconcile/collector는 inference를 보내지 않는다. 실제 dispatch는 별도 유효한 승인에서 제어기 명령에 `--run-next`를 명시한 경우에만 한 job을 실행한다. 승인 JSON1.0은 `authorization_id`, `manifest_sha256`, `approved_at`, `expires_at`, `human_approval`, 공급자별 `limit_usd/existing_exposure_usd/original_input/derived_render`, `request_cap=24`, 두 자리 소수 `trial_usd`, `admission_reserve_s>=1800`을 요구한다. 예시 파일이나 시험용 승인 문자열은 인간의 실제 승인에 해당하지 않는다.

### 독립 품질 평가와 결과 수집

`scripts/benchmark_quality.py`는 생성 모델의 critic과 별도로 evaluator-only annotation/rubric을 사용한다. 입력·case·rubric·후보 plan·실제 관측 frame SHA를 결속하며, semantic tool 물체와 확장된 렌더 부품을 구분한다. 생성 ID나 순서가 아닌 종류·정규화 위치로 최대 일대일 matching을 계산한다. precision/recall/F1, 장애물 recall, 좌우·전후 등 배치 관계, 지지 parent/part, 명시·실측·알려진 합성 치수를 평가한다.

실측 없는 추정 방 크기는 실패로 보지 않는다. occluded/unknown 물체는 관측 가능한 정답이나 false positive로 억지 계산하지 않고, 판별 불명 관계·부분 annotation·중복종류의 모호한 matching은 비평가로 남긴다. 이미지 pixel 좌표나 3D 실측 정밀도와 이 room XY 평가를 혼동하지 않는다. 독립적으로 blind 검토한 실제 frame의 가구 식별성 확인이 없으면 품질 NOT_EVALUATED이며, production critic의 `uncertain`을 PASS로 바꾸지 않는다. 박스로만 보인다는 독립 판정은 시각 품질 FAIL이다. 이번 합성 labels는 판정기 회귀용이며 실제 방의 인간 정답 annotation이 아니다.

`scripts/collect_comparative_benchmark.py`는 원 raw/dispatch/ledger를 기존 ordinary 감사기로 다시 읽어 실제 입력·역할별 wire 모델/출력 한도·승인 시간·저장 라우팅·명세 정책을 확인한다. 캠페인의 저장 summary와 재감사 정산이 다르면 예약을 유지하고 감사 실패로 남긴다. 원 자료가 없거나 프로세스만 종료됐다는 이유로 비용을0으로 만들지 않는다. 원 generation/현재 revision 렌더/사전 선언한 의미목표 도착/이동 중 Stop/승인 없는 reload/종료 후 reopen을 단계별 수집하며, 독립품질 비평가 결과는 전체 PASS가 아니다.

공개 JSON/Markdown은 집계 지표·익명 job ID·모델 역할만 내보낸다. 사진·원문·전체 좌표·annotation·원 응답·키는 제외한다. development/holdout과 photo/text 분모를 나누고, 실패/NOT_RUN/audit/held를 유지한다. holdout 비교는 방 단위 paired 집계와 조합×입력 modality에 대한 가족별 alpha 분할을 사용하며 자동 우승을 선언하지 않는다. 공개 결과는 원 실행 tree 밖의 새 폴더에만 저장한다.

### 최종 회귀와 보존한 초기 오류

| 검사 | 최종 결과 |
| --- | --- |
| Provider 전체 | 327 PASS / 7.819s |
| Core 전체 | 302 PASS / 26.439s |
| benchmark 파일·명세·제어·품질·수집·기존 보고서·dispatch deadline + 기존 App 라우팅·승인 | 95 PASS / 12.799s, import 중복 포함 |
| Stop 정책 Node | 2 PASS, 단일 프로세스 |
| Python 변경 코드 AST15개·브라우저 시험 syntax·diff check | PASS; diff에는 기존 LF/CRLF 안내 |
| 현재 새 명세 actual LLM/브라우저/Isaac smoke | NOT_RUN |

각 suite는 겹침을 합산하지 않는다. 최종95개에는 캠페인 initialize/report/reconcile 파일 경로, 실제 collector CLI의 JSON/Markdown 생성 및 원 tree 덮어쓰기 거절, 사진2/text2의 네비우스·OpenAI-only metadata 직전 중단, wire 출력8k로 변경·만료 뒤 dispatch·누락 frame/annotation·장부 불일치 반례가 포함된다. 실제 네트워크와 하위 actual journey는 fixture에서 차단했다.

초기 부착물 회귀의 시험 입력/source/ref 오류·Transform 필드명 오류는 수정 전 기록으로 보존한다. Provider sandbox temp 정리30건과 Core sandbox temp 정리1건 PermissionError는 환경 실패였다. 정상 검토된 오프라인 실행으로 각각 최종 통과했으며 ACL 변경·권한 우회·타 프로세스 종료는 없었다. collector CLI 시험의 Windows cp949 읽기 UnicodeDecodeError1건은 시험이 UTF-8을 명시하도록 고쳐 재검증했다. 이 오류를 실제 모델 실패나 제품 성공률에 더하지 않는다.

### 정확한 다음 작업

1. B1 나머지: 검토된 제품 역할 외 모델의 별도 eligible 검사/기대 거절 adapter, 실제 fresh 명세에서 제어기 재개·중단 조건 인수. 미지원 모델을 기존 모델로 대체해 시험하지 않는다.
2. B2 나머지: 독립 개발/holdout 데이터와 인간 annotation·blind frame review, 평가자 일치도·rubric 임계값 동결. synthetic 회귀를 실제 품질 성적으로 쓰지 않는다.
3. B3: 소스·runtime/asset/hardware 기록 동결 및 CPU profiler 불일치 교정 후, **유효한 새 금융/원본·파생 렌더 전송 승인**으로 photo와 text 각각 실제 LLM→현재렌더→저장→의미목표 이동→Stop/reload/reopen smoke. 새 reload evidence 코드는 syntax만 통과했고 실제 새 browser 실행은 아직 안 했다.
4. B4~B6: 개발군 선별·독립 표본 수/검정력/비용 확정→holdout 비교→규정별·규정 없는 추천과 공개 지표. 지금 “최적 조합”을 확정하지 않는다.

이번 실제 모델 HTTP/사진 외부 전송/Isaac/로봇/배포/설치/commit/push는0이다. 원 최신13시험/5PASS 및 전체19시험/129HTTP, 기존 사용량·held·종료된 승인·설정·실물 보호·예약 PAUSED·whole=false는 그대로다. 로봇은 위 오프라인 잔여의 선행조건이 아니다.

아래 v398은 당시 기록이다.

## 판정과 실행 범위

목표 계획의 내부 오류가 경로 없음으로 소실되는 결함을 수정했다. 배치 탐색은 종료 원인을 구분하며, 다중 사진·텍스트 시험 명세와 실패 분모·방 단위 비교 통계의 기반 코드를 추가했다. **B0의 확인된 오류 분류 수정은 검증됐지만 B0 전체 인수 및 B1/B2는 PARTIAL이다.** 새 manifest 경로의 실제 LLM·Isaac smoke와 독립 품질 평가기는 아직 완료되지 않았다. 본시험 실행 준비 완료나 모델 성능 우위로 표시하지 않는다.

최신 사용자 요청은 코드 작업이다. 이번 실제 LLM HTTP, 사진 외부 전송, Isaac 실행, 로봇 연결·모터·센서·배포, 설치·시스템 설정, commit/push는 모두 0이다. 기존 자동화 PAUSED와 실물 임무 잠금을 유지했다. 종료된 기존 USD5/1 캠페인을 새 실행 승인으로 재사용하지 않았다.

## 제품 경로 변경

| 경로 | 변경과 검증 범위 |
| --- | --- |
| `simulation_goal.py`, `current_goal_preview.py` | 알려진 후보·경로 거절만 다음 후보로 넘긴다. 잘못된 로봇 asset 설정과 예상 밖 planner 오류는 원인을 유지해 즉시 전달한다. 최대16후보·좌표·scene revision·시작 pose·clearance·후보별 원인·종료 사유를 기록한다. REAL 후보 planner는 자체 context를 명시하며 기존 실물 한도를 바꾸지 않는다. |
| `product_workflow_service.py`, `conversation_service.py`, `execution_diagnostics.py` | 목표 성공·실패 진단을 기존 채팅 이벤트와 실행 ID에 연결한다. 원 생성 근거와 관련 실행을 연결하고 개발자 로그에는 진단 SHA·종료 코드·후보 수·원인별 수만 허용한다. 사진·원문·전체 좌표를 개발자 메타데이터에 추가하지 않는다. |
| `photo_layout.py` | greedy 후보 수와 fallback의 domain 생성/되돌림 단계, 노드·시간·분기 제한, 빈 domain, 유한 격자 소진을 구분한다. 10cm/512노드/2초/분기32와 기존 여유폭·물체 보존은 그대로다. `global_infeasibility_proved=false`로 연속 공간 전체의 불가능 증명을 금지한다. |

수정 전에는 `SIM_ASSET_INVENTORY_INVALID`와 `PLANNER_CONFIGURATION_INVALID`를 기대한 두 회귀가 모두 `SIM_TARGET_NO_REACHABLE_APPROACH` 때문에 실패했다. 수정 후 원인이 보존된다. 경로가 실제로 막힌 후보를 성공시킨 것이 아니다.

새 packing 회귀는 작은 독립 유한격자 완전탐색, 분기·노드·두 단계의 시간 제한, 성공·빈 domain, 격자 사이에만 가능한 연속 배치를 대조한다. 기존 generic/repair/rollback 회귀도 함께 실행했다. 첫 회귀의 시험 치수 기대값 두 건은 교정했고, Provider 전체 회귀에서 발견한 **0노드·0초 시험 계약의 호환성 변경은 제품에서 복원**했다. 음수·NaN 예산은 여전히 거절한다.

## 저장된 실제 실패의 원인 재분석

파생 근거: `outputs/benchmark-code-preparation-20261010/saved-geometry-final-diagnosis.json`. 원 JSON과 사진 **192개 SHA 불변**, 현재 진단 코드5파일 SHA 불변, 네트워크 연결은 진단 도구 내부에서 차단했다. checkpoint history의 서로 다른 원 후보도 검사했으며 원 후보를 수정하지 않았다.

| 원 시험 | 현재 재분석 결과 | 해석 |
| --- | --- | --- |
| `flash-luna-3` | 두 저장 배치 실패 후보 모두 `BRANCH_BUDGET_EXHAUSTED` | 허용 분기만 탐색했다. 연속 공간 전체의 불가능이나 모델 단독 실패를 증명하지 않는다. |
| `flash-lightning-4` | 두 저장 배치 실패 후보 모두 `NODE_BUDGET_EXHAUSTED` | 512노드 한도가 끝났다. 물체를 삭제하거나 방을 특정 사진 치수로 고쳐 PASS로 만들지 않았다. |
| `luna-luna-5` | `NO_ACCEPTED_EXTERIOR_CANDIDATE`:16후보 중 `START_OR_GOAL_BLOCKED`14, `NO_PATH`2 | 원 scene와 원 마지막 SIM pose 기준의 제한 접근 후보가 모두 거절됐다. 원 FAIL을 유지한다. |

동일 원 후보의 다른 복원 snapshot은 파생 bedding keepout이 바닥 경계를 벗어나 `ROOM_ITEM_OUTSIDE_FLOOR`로 거절된다. 이를 확인된 solver 결함이나 해결 완료로 단정하지 않았다. attachment envelope의 일반 반례와 수정 범위·진전·rollback의 원 patch 대조는 B0 전체 인수 전에 더 확인해야 한다. 첫 두 진단 JSON도 삭제·덮어쓰기 없이 보존했다.

## 시험 명세와 실제 경로의 기반

`scripts/benchmark_protocol.py`와 `prepare_comparative_benchmark.py`는 입력·목표·출처·전송 범위·room group·개발/holdout·정확한 역할별 모델·정책 해시·반복·순서 seed·소스 해시를 검증한다. 사진2개와 텍스트2개의 서로 다른 입력으로 격리 시험을 했다. 텍스트는 사진을 요구하지 않으며 평가 답안 파일은 SHA만 확인하고 제품 입력 packet에 포함하지 않는다. 같은 방의 split 유출, 같은 사진을 다른 독립 방으로 세는 경우, 변경된 사진/원문/목표/소스, UI trim에 따른 입력 변경, 이미지 아닌 파일을 거절한다. 실행 위치는 조합별 ±1 이내로 균형화하며 같은 seed는 같은 순서를 만든다. 준비 명령은 HTTP0이며 금융·로봇 승인도 생성하지 않는다.

기존 `run_ordinary_staged_live_ten.py` → `verify_chat_sim_journey.py` → 실제 일반 App의 브라우저 경로에 manifest case/config를 연결했다. 새 actual lane은 고정 응답이나 저장 후보를 주입하지 못하며, 명세의 텍스트·사진·목표를 사용한다. 레거시 침실 SHA 승인은 레거시 시험에만 유지되고 새 명세는 승인 입력의 SHA를 사용한다. 소스 동결에는 core/provider/App/safety, scripts, web source·e2e·build, **실제 Isaac extension adapter·설정**을 포함한다. 외부 runtime/asset/hardware snapshot까지 동결하는 B3는 별도 잔여다.

사전검증의 config dict와 설정 폴더가 같은 변수에 덮여 쓰이던 새 adapter 결함도 수정했다. 사진2/text2에서 가짜 등록 metadata만 사용해 manifest→격리 설정→승인 저장까지 실행하고, metadata GET 직전에 중단하는 회귀가 통과했다. 키 저장소·네트워크·하위 프로그램은 실제 실행하지 않았다.

목표 도착은 짧은 초기 시연 이동과 분리하며, 실제 의미 목표의 `completed` telemetry와 오차≤4cm를 요구한다. 도착 후 Stop 버튼은 정상적으로 비활성화되므로, 같은 scene의 관측된 이전 preview endpoint로 돌아가는 별도 경로가 **움직이는 동안** Stop을 검사하도록 시험을 수정했다. 이전/현재 pose가 불명·다른 revision·4cm 허용오차 두 개가 겹칠 정도로 가까우면 정지 인수를 만들지 않고 거절한다. 이 절차의 순수 정책2건과 구문은 통과했지만 새 브라우저·Isaac 실제 경로는 NOT_RUN이다.

현재 실제 adapter는 검토된 observer Flash/Qwen/Luna와 planner Lightning/Luna, repair=planner·critic=observer 조합만 지원한다. 모든 Token Factory 모델·독립 역할 설정·diagnostic 기대 거절 경로를 지원 완료로 표시하지 않는다.

## 실패 분모와 통계의 기반

`scripts/benchmark_results.py`는 예정·실행·미실행·감사 실패·평가 미완료·fixture/replay를 모두 보존한다. provider응답/생성/독립품질/현재렌더/실제 의미목표 도착/Stop/reload/reopen의 단계별 분모를 기록하며, 독립품질 미평가나 감사 미통과를 전체 PASS로 바꾸지 않는다. 실패 비용도 포함하고 비용 불명·미정산 예약이 있으면 성공당 비용이나 비용 우승을 산출하지 않는다.

비교는 같은 case/repeat를 짝지은 후 같은 방의 반복을 먼저 평균한다. 방 단위 seeded bootstrap, 작은 표본 또는 동일 관측의 보수적 구간, 미완료 비교의 INCONCLUSIVE를 구현했다. 2/2나 모든 값 동일에서 폭0의 확신을 만들지 않는다. 통계 함수는 자동 승자를 선언하지 않으며 최종 표본 수·검정력·다중 비교·실용적 차이는 시험 전에 확정해야 한다. 동일 원인 중단 함수는 조합5개가 아니라 역할별 서로 다른 모델5개를 센다. 아직 실제 dispatch controller에 연결한 완료 인수는 아니다.

## 회귀 결과

각 행은 별도 suite이며 겹치는 테스트가 있어 합산하지 않는다.

| 검사 | 최종 결과 |
| --- | --- |
| Provider 전체 | 322 PASS / 7.610s |
| Core 전체 | 302 PASS / 25.497s |
| 채팅 conversation·R5 API | 86 PASS / 54.243s; import된 관련 테스트 포함 |
| protocol/result/기존 benchmark/goal/packing/generic 집중 | 63 PASS / 1.908s |
| 실행 진단 관련 | 133 PASS / 약68.7s; import 중복 포함 |
| Stop 정책 Node | 2 PASS, 단일 프로세스 실행 |
| 브라우저 시험 코드 | `node --check` PASS; 실제 browser journey NOT_RUN |

첫 sandbox 실행의 임시 파일 `PermissionError`와 Node test runner의 `spawn EPERM`은 환경 실패로 보존한다. Python은 검토된 로컬 회귀 권한 안에서 재실행했고, Node 정책 시험은 하위 프로세스를 만들지 않는 직접 실행으로 검증했다. ACL·시스템 설정·타 프로세스 종료로 우회하지 않았다. `git diff --check`의 기존 LF/CRLF 안내는 제품 실패가 아니다. 이번 web 제품 코드는 바꾸지 않았으며 전체 web suite/type/build는 새로 실행하지 않았다.

## 정확한 잔여와 다음 순서

1. B0 잔여: attachment 바닥 경계의 범용 반례와 원 patch의 적용 전후·진전·rollback 대조. 제한 탐색 예산을 변경하려면 개발군 자원 곡선을 먼저 비교하고 모든 후보에 동일하게 동결한다.
2. B1 잔여: 기존 역할별·조합별 controller를 manifest schedule에 연결, 별도 campaign 승인·공급자별 예산/held·만료·재개와 모델5개 중단의 전체 인수. 역할 모델 확대와 기대 거절 adapter도 필요하다.
3. B2 잔여: visibility/unknown을 가진 독립 annotation 계약, 물체 matching·누락/배치/지지 관계 evaluator, 실제 감사 근거→정규화 collector→공개 exporter 연결. 현재 집계기는 자체 품질 판정기가 아니다.
4. B3: 위 코드·데이터/목표·정책 동결 후 유효한 새 승인에서 photo/text 실제 LLM→현재렌더 critic→저장→실제 의미목표 도착→Stop/reload/reopen smoke. CPU profiler 교정과 runtime/asset/hardware 기록을 분리한다.
5. 그다음에만 B4 선별·표본/예산 확정, B5 독립 holdout, B6 규정별 추천/공개 지표를 실행한다. 기존 침실은 개발군으로 남긴다. 로봇 실측·LiDAR 정합·실물 목표/Loop 인수는 별도다.

기존 v396의 최신13시험/5PASS와 전체19시험/129HTTP는 변경하지 않았다. 이번 0call 재분석이나 합성 회귀를 새 모델 성공률·실물 준비 완료로 더하지 않는다.
