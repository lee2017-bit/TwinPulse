# 창고 semantic·지지 관계 연결 검증 — v424–v431

현재 기준은 **Baseline v1.0.431**이다. 승인된 새3건은 모두 종료했고 창고/거실 기능2/3PASS·식당FAIL이다. [10이미지 단일 보고서](../../outputs/physical-ai-p2-20261011-v431/final-evidence/report.html)와 [최종 감사·잔여](#수정본-3건-종료와-실제-기능-재인수--v431)를 현재 결과로 사용한다. 사진 품질/전체데모/P2는계속PARTIAL이며 직전 source427/428 실제전체0/3과source429의범용수정/정적검증은 [이전 보고서](../../outputs/physical-ai-p2-20261011-v429/final-evidence/report.html)에 별도 보존한다. 아래 RUNNING은 종료 전 이력이다.

2026-10-11. 기준은 Baseline v1.0.424다. 창고 라이브러리가 발견되지만 실제 장면 문법과 지지 검사에는 연결되지 않던 결함을 범용 제품 경로에서 수정했다. 이 절의 결과는 **오프라인 회귀 통과**이며 실제 모델·Isaac·실물 인수와 구분한다.

## 구현한 연결

기존 `create_rack_row`와 `place_pallet_stack`을 typed semantic `rack`·`pallet_stack`에서 호출한다. 새 wire tool이나 임의 코드 실행은 없다. 빈 팔레트는 별도 `warehouse.pallet` 모델로 기존 `place_room_item`에 연결하고, 슬랫·러너 표시 모델과 보수적 충돌 형상을 사용한다. 라이브러리는 29종, room prop은 20종이다.

- rack의 bay/level, loaded pallet의 stack level을 정수·유한 범위로 검증한다. 실제 확장 형상을 packing과 천장 검사에 사용한다.
- 빈 팔레트 `deck`, rack의 선택한 층에 실제 존재하는 `shelf_N`, loaded pallet의 `stack_top`만 지지면으로 허용한다. 이미 화물이 있는 base를 빈 면처럼 사용하지 않는다.
- 지지면 크기뿐 아니라 기둥·다른 선반·기존 화물의 3D 침투를 검사한다. 실패 시 실제 footprint·surface 크기·부모·거절 부품을 수정 피드백으로 남긴다.
- 기존 rack/loaded pallet factory는 회전을 지원하지 않으므로 yaw=0만 명시 허용한다. 지원되지 않는 회전을 조용히 버리지 않는다. 빈 팔레트의 기존 room-item 회전은 유지한다.
- 종류별 정확한 schema 분기로 가정집 행에 불필요한 warehouse 필드를 요구하지 않는다. 모든 typed repair add 분기의 source 참조를 host에서 제한한다.
- 저장 sidecar의 지지 관계, 부모 이동 시 자식 재배치, App preview/cancel/apply, 닫힌 재열기·Undo와 현재 장면의 명명 목표 접근 경로를 연결해 검사했다. 실제 이동은 하지 않았다.
- 보조 보고서의 kind 집계는 rack factory를 한 객체로 세며 생성된 부품 수를 객체 수로 부풀리지 않는다. loaded pallet을 빈 pallet으로 세지 않는다. 이 지표는 지지·위치 정확도나 사진 품질 PASS가 아니다.

핵심 파일은 core의 `warehouse_models.py`, `geometry_diagnostics.py`, `photo_quality.py`, `photo_placement.py`, `model_library.py`, room catalog/inventory/visuals와 provider의 `photo_layout.py`, `semantic_scene.py`, `budgeted_pipeline.py`다. 기존 v1/v2 도구·정지/실물 잠금·출력/비용/수정 보호는 유지했다. 모델 조합과 일반 설정은 바꾸지 않았다.

## 실제 오프라인 결과

원 XML은 [시험 디렉터리](../../outputs/warehouse-semantics-20261011-v424/)에 보존한다. 아래 행의 중복 테스트·subtest를 합산하지 않는다.

| 시험 | 결과 | 원 기록 |
|---|---:|---|
| Provider/Core 전체와 model library·placement·visual·live geometry 관련 | 703 PASS, 620 subtests PASS | `regressions-complete2.xml` |
| 창고·parametric schema·목표 계산·채팅 목표·편집 proposal | 86 PASS, 20 subtests PASS | `app-final.xml` |
| 라이선스·기존 출처 배포 gate | 22 PASS | `licensing.xml` |
| pilot 보조지표·comparative collector | 11 PASS | `reporting.xml` |

최초 실패도 지우지 않았다. 기본 Temp 권한 오류, 중복 fixture class 수집, PYTHONPATH 누락은 시험 환경/구성 문제로 분리했다. 새 add 분기에 source 참조 제한이 일부만 적용되던 실제 결함은 전체 분기로 수정했다. 옛 모델/prop 고정 개수와 `items.properties`를 직접 읽던 테스트는 새 registry와 정확한 종류별 `anyOf` 계약에 맞춰 갱신했다. fixture 인자·얕은 복사·예외 클래스 기대값과 한 테스트 들여쓰기 오류도 수정하고 실패 XML을 보존했다. 마지막 전체 재실행은 703 PASS다. `git diff --check` 오류는 없고 기존 CRLF 경고만 있었다.

원 창고 실패의 .5×.5m 상자는 .8×.42m storage 면에 여전히 맞지 않는다. 원 결과·raw는 FAIL 그대로다. 테스트에서 복사한 후보를 명시적으로 빈 팔레트와 그 deck에 연결했을 때 컴파일 가능함을 확인했으며, 이를 실제 모델의 수정 회복으로 세지 않는다. 특정 사진·ID·좌표의 production hardcode, 바닥으로 자동 이동, 임의 물체 삭제·크기 강제 변경은 없다.

## 새 실제 시험 범위와 남은 순서

사용자가 공개 CC BY-SA 식당·거실 사진 2장, 파생 Isaac 렌더와 창고 텍스트에 대해 **Flash V4.1/Super120B 최대 3개 새 생성**, 각 12 HTTP/수정 3회, 과거 사용·UNKNOWN/held 포함 **Nebius 누적 USD6**, 승인 후 **2시간**을 새로 승인했다. OpenAI·개인 사진·Cloud·로봇은 제외한다. 원 P2의 8개는 이미 사용했으며 이번 승인으로 초기화하지 않는다. 시작 전 새 catalog/입력·소스·설정·회계 동결, 종료 후 원본 재감사를 수행한다. 실제 결과는 이후 절에 별도 기록하며 이 시점에는 NOT_RUN이다.

1. 해당 3건으로 개수/warehouse 수정의 실제 영향 범위 인수. 모델의 parent 선택·수정 진전과 실제 현재 렌더/목표 이동/이동 중 Stop/저장·재열기를 확인한다.
2. 별도 유효 범위에서 C 새세션 반복, 일반 채팅의 실제 LLM scene edit→preview/apply/cancel→재계획.
3. SIM 연속 왕복/loop·이상 주입 통합 인수와 독립 사진 품질 검토.
4. P2 LOCAL_FULL_PASS 이후 승인된 bounded Cloud, 현장 실물·영상, 외부 자산 권리·개인정보 공개 검토, 제출.

`whole_demo_pass=false`, P2 전체 PARTIAL, native 예약 PAUSED를 유지한다. 오프라인 통과만으로 로봇 전원 연결 후 전체 데모 성공을 보장하지 않는다.

## 실제 착수와 catalog 격리 준비 결함 — v425

v424 manifest SHA `1d945232bb9d217237319403d928c8fdc7ecdf73f556e6c16bc7ef909dc72ec7`의 첫 창고 착수는 LLM/Isaac 시작 전에 `stage_routing_corrupt`로 끝났다. 새 catalog를 격리 폴더에 복사한 뒤 원래 다른 catalog SHA에 고정된 global route를 `save()`의 이전 설정으로 읽으면서 거절됐다. 모델 출력이나 창고 geometry 실패가 아니다. `approval.json`·generation ledger가 만들어지기 전의 예외이며 확인된 inference dispatch는 0개다. 기존 controller는 완전한 정산 자료가 없으므로 UNKNOWN/미정산으로 보수적으로 보존했고 **USD1 전액 예약**을 유지했다. 이를 비용0으로 바꾸거나 원 실패를 성공으로 승격하지 않았다.

소스 수정 전에 [기존 감사기 부분 보고서](../../outputs/physical-ai-p2-20261011-v424/pre-change-audit/public-pilot.json)를 저장했다. 실제 소스 수정은 `run_ordinary_staged_live_ten.py`의 manifest-bound 준비 경로에 한정한다. 새 manifest가 전체 route/catalog를 제공하므로 격리 복사본은 provider identity metadata만 복사하고 route는 처음부터 검증해서 저장한다. global 설정은 그대로이며 legacy 복사 경로와 route 검증·복구 보호를 완화하지 않는다. 이전 catalog route+새 catalog 충돌을 재현하고 fresh manifest route의 save/readback·원 파일 SHA/키 미조회·기존 설정창 회귀를 검사해 **38 PASS** (`catalog-preflight-fix.xml`)를 확인했다.

원 창고 job 재호출 없이 아직 착수하지 않은 **식당·거실 사진 2건**만 source425로 새 동결했다. manifest SHA `370d05ddbca586e906507d074749b77a6f4118099b2ed4591941b7a09831cd05`, 원 승인3슬롯 중1착수+2잔여, 원 기한 **2026-10-11 21:04 KST**(답변보다 이른 시점을 사용한 보수적 2시간), 원 누적N6를 유지한다. carry-in은 USD4.66708357+새 미정산1=**5.66708357**이며 원 hold는 포함된다. 각 잔여 시험은 추가로 엄격한 USD0.30 cap를 사용한다. 40k/300s/900s/12HTTP/3repair와 입력·목표는 유지했지만 cost cap가 다르므로 과거 USD1 시험과 동일 재정 조건의 모델 비교시험으로 주장하지 않는다. 이것은 수정 영향 기능 인수다.

v425 작성 시 [새 campaign](../../outputs/physical-ai-p2-20261011-v425/campaign/manifest-campaign.json)은 실행 중이었다. 현재는 아래 v426처럼 정상 종료된 상태다. 소스/웹/build/입력·평가기준은 실행 중 변경하지 않았고, 종료 후 원 감사와 다음 소스 수정으로 분리했다.

## 비용 사전 점검 수정과 실제 Isaac 정적 검증 — v426

### 두 번째 실제 착수 결과

source425의 식당 사진은 ordinary App/Isaac 연결까지 시작했으나, 제가 더 엄격하게 정한 **USD0.30 cap**가 제품의 초기 보수적 예약 최소액 **USD0.5916864**보다 작았다. 화면은 그 금액을 명시하고 Continue를 정상적으로 잠갔으며, harness가 클릭 가능 상태를 기다리다 30초 Timeout으로 끝났다. UI 또는 모델 성능 실패가 아니라 **시험 cap를 정할 때 제품의 예약 규칙을 먼저 확인하지 않은 host 준비 판단 오류**다. 모델 출력40k를 줄이거나 보호를 완화해서 통과시키지 않았다.

일반 제품은 각 요청의 전체 context 상한과 출력 상한으로 보수적 비용을 예약한다. 이번 reviewed rate/context의 사진 최초 예약은 Flash 관측 USD0.3624 + Super 구조 USD0.1146432 + Super 최초 parameter 요청 USD0.1146432 = **0.5916864**다. 텍스트 최초 예약은 관측을 건너뛰므로 **0.2292864**다. 이는 실제 한 요청의 청구액을 예측한 숫자가 아니며, usage가 돌아오면 기존 정산 경로에서 실제 추정액으로 대체한다.

원 [수정 전 감사](../../outputs/physical-ai-p2-20261011-v425/pre-change-audit/public-pilot.json)는 먼저 저장했다. 확인된 승인/LLM dispatch는 0이나 ordinary ledger가 완성되기 전 종료되어 기존 strict auditor의 정산은 UNKNOWN이다. controller 원 기록의 **추가 USD0.30 full hold**를 보존하고 거실은 NOT_RUN으로 남겼다. 창고 UNKNOWN USD1도 그대로다. 과거 exposure 4.66708357 + 새 미정산1.30 = **Nebius USD5.96708357/누적6**, 보호 잔여 **0.03291643**다. 이것을 실제 USD1.30 청구로 설명하거나, 반대로 기록을 지워 비용0/환급으로 바꾸지 않는다. 이번 확인된 새 모델 추론은0회, invoice는 미검증이다.

### 실행 전에 같은 계산을 적용

`generation_approval.py`의 기존 계산을 `full_context_reserve`와 `minimum_initial_reserve`로 공유했고 제품의 계산 결과와 보호는 그대로다. `benchmark_campaign.admission`이 frozen catalog/단계별 cap/입력 modality로 같은 최소액을 검사하여 **child 실행·UI 시작·campaign 금융예약 전에** `INITIAL_RESERVATION_EXCEEDS_TRIAL_CAP`과 실제 최소액을 반환한다. 이미 미정산된 run에 대한 차단이 더 우선이며, 원 hold를 해제하는 기능을 추가하지 않았다.

새 회귀는 사진0.30 거절·state/runs 불변·reserve_next 차단과, 같은 조건의 텍스트가 observer 없이0.30 안에 들어감을 확인한다. 첫 관련61개와 reporting/live-budget까지 포함한 **83개**가 통과했다. 중복 suite를 합산하지 않는다. 마지막83개 실행은 기본 sandbox에서 Temp fixture 권한으로56 FAIL/27 ERROR/27 PASS였고 원 XML을 보존했다. 권한 검토를 거친 동일 오프라인 범위의 재실행은83 PASS,14.79초다. 시스템 ACL 변경·설치·외부 호출은 하지 않았다.

### 실제 Isaac에서 확인한 범위

새 합성 fixture만으로 semantic compiler → core → App의 saved placement contract → 실제 Isaac adapter Build → 현재 USD/표시 위치 → 캡처 → 저장 프로젝트 및 export 재열기를 실행했다. 사용자 방 원본·기존 project·전역 설정은 건드리지 않았다.

| 대상 | 실제 선택한 지지면 | 표시 mesh | 지지 XY/높이차 | 프로젝트·USD 재열기 |
|---|---|---:|---|---|
| 빈 `warehouse.pallet` | `deck` | 11 | contained PASS / 0m | PASS |
| `warehouse.rack` | `shelf_1` | 12 | contained PASS / 0m | PASS |
| `warehouse.pallet_stack` | `stack_top` | 14 | contained PASS / 0m | PASS |

각 경우의 실제 current-render1280×960, scene revision, Build receipt, PNG SHA, 원 project SHA와 compile trace는 [원 결과](../../outputs/warehouse-semantics-20261011-v426/isaac-static-2/result.json)에 있다. 세 이미지를 직접 검토했다. display physics schema는0, 충돌 형상 current-match를 확인했고 각 source SHA도 불변이다. 결과는 **PASS_STATIC_SUPPORT_ONLY**이며 모델의 부모 선택/수정 회복, 실제 물리 이동, 사진 재현 정확도 또는 Full Process PASS가 아니다.

첫 정적 시험은 room-item prop에도 optional `libraryModelId`가 반드시 있다고 시험 코드가 잘못 가정해 FAIL했다. 기존 계약은 room-item의 `catalogKind`와 선택적 parametric/factory library ID다. 제품 메타데이터를 임의로 추가하거나 실패를 숨기지 않고 시험 기대값을 실제 계약으로 수정했다. [첫 실패](../../outputs/warehouse-semantics-20261011-v426/isaac-static-1/result.json)와 두 번째 통과를 모두 남겼다. 두 headless 앱은 소유 프로세스의 정상 close로 종료했다.

### 원본 감사와 다음 순서

원 P2 JSON seal421개와 첫 preflight seal7개는 SHA 변경0이며, ordinary 설정 metadata3파일도 불변이다. 두 paid owner/dispatch lock는 정상 종료됐고, 과거 FAIL/UNKNOWN/장부/원 입력은 유지된다. 아래 단계는 새 실행 승인과 필요한 예산·기한·횟수 없이 자동으로 시작하지 않는다.

1. 두 UNKNOWN/full hold의 독립 정산 확인. 향후 전송 전 실패도 완전한 terminal audit evidence를 남기는 경계는 별도 잔여이며, 단순히 파일이 없다는 이유로 비용0을 만들지 않는다.
2. 유효 재시험 범위에서 새 동결 cohort로 warehouse 및 공개 사진2의 실제 Flash/Super 생성·수정·현재 렌더/명명 목표/이동 중Stop/닫힌 재열기 영향 인수. 실패 원 job을 재호출하지 않는다.
3. C 새세션 반복, ordinary 자연어의 실제 LLM 편집→preview/apply/cancel→재계획, SIM loop/이상주입 통합, 독립 사진 품질 검토.
4. P2 LOCAL_FULL_PASS 이후 bounded Cloud·현장 로봇·측정·영상·외부 자산 권리/개인정보·공개 재현·제출.

라이선스 자체 코드 적용과 고지·메타데이터는 이미 반영됐다. 외부 자산 권리와 공개 검토는 별도 잔여다. native 예약 PAUSED, `whole_demo_pass=false`, Cloud/OpenAI/실물0를 유지한다. 비용 부족을 우회하거나 불필요하게 대기하며 시간을 채우지 않았다.

## 추가 사용 승인과 새 동결 재시험 — v427

사용자는 계정 사용/잔액 화면과 함께 “아직 넉넉하다 둘다. 충분히 더써도 돼.”라고 추가 사용을 승인했다. 이를 기존 실패/held를 삭제하는 지시로 해석하지 않았다. 이번 범위는 명시적으로 **Nebius 누적USD8, 공개사진2/파생렌더/창고text의 최대3개 fresh 생성, 기존 Flash/Super, 각USD1/12HTTP/3repair/40k/300s/900s, 원21:04KST**로 제한했다. OpenAI·개인사진·Cloud·로봇은 제외한다. 스크린샷의 OpenAI월사용 .52는 잔액이 아니고 Nebius의 USD2.61 사용표는 Oct10까지만 필터된 값이며, 보호노출/미정산과 실제invoice는 구분한다.

carry는 **5.96708357**이며 이전 UNKNOWN fullhold1.30과 과거 원미정산을 모두 포함한다. 원424/425 campaign/raw를 SHA로봉인했고 globalmetadata도불변이다. 새 config label `flash-super-v427`은 cohort별job식별만 구분하며 정확한모델/입력/가격/정책을 변경하지 않는다. 첫 준비는 jobID가source별로달라진다는 잘못된가정으로 `OLD_JOB_REDISPATCH_FORBIDDEN`에0HTTP거절됐고 부분준비파일을 보존했다. 승인된실행은 새 `outputs/physical-ai-p2-20261011-v427/approved-scope`이고 manifestSHA는 `ff30fee4714eebc5447eab9dd42c490597ad3862bcbd9c0cd262930cbc693b36`다.

`RunnerPhaseTrace`는 phase/time/case/config/sourceSHA·typedexception만 남기는 비밀없는 diagnostic이다. childdispatch의intent이후에는UNKNOWN_AUDIT_REQUIRED이며, terminal의financial/physicalauthority는항상false다. folder생성전에는 sibling preflight기록을 만들고 원기록을덮어쓰지 않는다. 이를 금융정산receipt로 간주하거나 oldhold를 해제하지 않는다. 새4회귀를포함한 runner/예산·보고87PASS(14.77초), 독립literal최소예약14PASS(.41초)를확인했고 suite중복을합산하지않는다. 실제모델결과는 아직NOT_RUN이다.

## 요청 로그 잘림과 미착수 1건 — v428

source427 owner는2건후정상종료했다. 창고2HTTP/usage추정USD.0060885는 생성·현재렌더·첫PhysXpreview 도착(.039798m)이 실제통과했지만 동결lexicographic 선택 `box_on_pallet`에 접근점을찾지못해 전체FAIL이었다. 원 입력을 다시 대조한 결과 사전목표는 **`Go to pallet`**이며, 앞선 `Go to box` 설명은 오기였다. ID접미사를kind처럼취급해 상자까지pallet후보로잡는 host결함과 parent keepout 접근결함을v429에서구분했다. 원16개후보의failure진단/실패성적은보존하며 이는전역경로불가능의증명이아니다. 수정 후 원 목표 checked plan과 별도 명시 상자 접근은 아래에서 확인하며 원 결과를 승격하지 않는다.

식당은 **8실제응답 모두stop**, 관측1/구조1/객체4/수정2, `REPAIR_STALLED`/no_progress로생성실패했다. 동시에2repair dispatch로그가 **273841bytes** 등으로기존262144문자prefix를넘어잘렸다. response/usage/finished/validation/hash join은확인됐지만 full-request감사를완료할수없어controller가UNKNOWN/fullUSD1을보존하고거실을NOT_RUN으로중단했다. 이는새토큰소진·300초timeout·잔액부족과별개다. [원wire identity boolean진단](../../outputs/physical-ai-p2-20261011-v427/wire-identity-diagnosis.json), [수정전기존감사](../../outputs/physical-ai-p2-20261011-v427/approved-scope/final-audit/public-pilot.json), [실제4이미지/수치 단일보고서](../../outputs/physical-ai-p2-20261011-v427/final-evidence/report.html)를먼저보존했다. 기존reporter의3방/2반복일반서두는이번3입력/1반복범위와다르므로단일HTML에서정확히구분하며, 식당8을완전감사2HTTP에더하지않는다.

범용 `InferenceEvidence.started/validation`은이미지/secret을먼저삭제하고structured본문을 **2MiB UTF-8 byte-bound**까지저장한다. 초과는여전히truncated=true이며엄격감사를완화하지않는다. requestwire/모델schema/출력40k/300s/수정·금융·실물guard와기존raw는무변경이다. 새5회귀는273KB tail/hash·validation tail·Unicode byte-bound·secret/image제거·덮어쓰기거절을검사한다. 관련226PASS/36subtests(72.46초), 첫실행225PASS/1FAIL은시험fixture가UTF8파일을Windows기본cp949로읽던문제이며원XML을보존한후encoding만교정했다.

최신승인3개중2개만착수했으므로 **원미착수 거실1개만**source428로동결한다. 누적N8/각1·40k/300s/900s/12HTTP/3repair·원21:04KST/같은입력·목표를유지하고carry는 **6.97317207**(과거5.96708357+창고추정.0060885+식당fullhold1)이다. 새장부는미정산을환급하거나원job를재호출하지않는다. 실제결과는종료뒤별도감사한다. P2전체PARTIAL/nativePAUSED·OpenAI/Cloud/개인사진/로봇0 유지.

## 실제 3건 종료와 범용 host 수정 — v429

두 소유 runner는 정상 종료했으며 원 manifest/authorization/장부/수신 응답의 재감사를 **소스 변경 전에** 저장했다. source427 manifest SHA `ff30fee4714eebc5447eab9dd42c490597ad3862bcbd9c0cd262930cbc693b36`, source428 SHA `886ca07583c03e917a014eb4cce8c30e3fe66e7ef54ac11a5f4346ef4d2c8393`를 각각 유지한다. 공개 사진2/텍스트1·각1회·동일 Flash/Super·40k/300s/900s/12HTTP/3repair의 기능 인수다. 별도 source를 합쳐 모델 순위나 모든 모델 동일조건 벤치마크 완료로 주장하지 않는다.

| 입력·원 job ID | 실제 수신 | 생성 | 전체 경로 | 원 중단·금융 상태 |
|---|---:|---|---|---|
| 창고 텍스트 `dd171071b5dc58192d4fb88f7e8f73ac` / source427 | 2 | PASS | FAIL | 첫 PhysX 도착 .0397984399m, 후속 명명 목표 `SIM_TARGET_NO_REACHABLE_APPROACH`; strict 요청감사 PASS/추정USD.0060885 |
| 식당 사진 `9fcbf1125a81ddea7464b737072e96f6` / source427 | 8 | FAIL | FAIL | repair2/no_progress/`REPAIR_STALLED`·지지 배치; 두 수정 요청 로그 잘림으로 strict UNKNOWN/USD1 최대예약 유지 |
| 거실 사진 `5237f4d0b2eff1843648d913f86d1d65` / source428 | 8 | FAIL | FAIL | repair2/no_progress/`REPAIR_STALLED`·지지 배치; 완전 요청감사 PASS/추정USD.0544776 |

총18개 **수신 응답은 모두 stop**이고 빈 final·length·요청300초timeout은 없었다. 이번 실패를 모델 출력 상한이나 계정 잔액 문제로 설명하지 않는다. 완전 요청/응답/장부 감사는10개이며 식당8개를 그 분모에 포함하지 않는다. 최신 완전감사 추정 합계는 **Nebius USD0.0605661**이고 식당의 미확정 USD1 hold는 별도다. 과거 보호노출5.96708357을 포함한 누적은 **7.02764967/8**이다. 이는 보호 예산 계산이지 청구액이 아니며 invoice 미검증이다. 원 최대3새생성은 모두 소진했고 새로운 OpenAI/Cloud/실물 호출은0회다.

### 같은 모델 응답을 host가 잘못 거절한 원인

1. **탐욕 지지면 packing의 되돌리기 부재.** 식당 초기/첫 수정의 동일1.8×1.0m 테이블 위0.45×0.30m 매트4개는 배치 가능한데 기존 center-first 배치가 앞선 물체를 확정해 마지막 물체를 거절했다. `support_packing.py`의 bounded 탐색으로 같은 부모·부품의 형제들을 임시 컴파일에서 되돌려 재배치한다. 크기·회전·종류·개수·부모를 자동 변경하거나 입력 원본을 수정하지 않는다. 모든 결과는 실제 support geometry와 .01m inset/.025m 형제 여유를 다시 통과해야 한다. 512노드/2초/분기32/geometry검사65,536 한도는 자원 보호이며 한도 실패를 전역 불가능의 증명으로 쓰지 않는다.
2. **exact-fit의 격자 반올림.** 거실 수정에서0.42m면 위0.40m물체+양쪽0.01m여유는 정확히 맞지만 float ceil/floor가 중앙 후보를 없앴다. grid index의1e-9 허용은 실제 좌표5e-11m 이하 계산오차이며 충돌·여유 기준 완화가 아니다. 초기0.06m 의자 등받이 배치와 식당 마지막0.46m좌판/.45m매트+.02m여유는 여전히 실패한다. 유효한 parent 수정까지 host가 거절하던 문제이므로 Nemotron 성능만으로 원인을 단정하지 않는다.
3. **명명 목표의 ID 접미사 오분류.** 원 동결 입력 `benchmark-case.json`의 목표는 `Go to pallet`이다. 현재kind를 사용하지 않고 ID의 `box_on_pallet` 끝까지 후보로 잡아 `pallet_right`와 두 선택지가 생겼으며 원 lexicographic 정책이 상자를 선택했다. 현재kind 우선, 완전 ID/`id=` 명시 선택 보존, 종류가 없을 때만 기존 ID fallback을 사용한다. 별도로 상자를 명시 선택하는 경우에도 selected target ID는 그대로 두고 checked placement contract의 부모 keepout을 포함한 외곽에서 접근점을 찾는다. 부모 삭제나 충돌 제외로 통과시키지 않는다.
4. **수정 요청 로그 손실.** v428의 finite2MiB redacted UTF-8 기록 수정은 실제 거실8개 요청감사로 검증됐다. 식당 과거 잘린 요청은 복원했다고 주장하거나 hold를 해제하지 않는다. 로그가 한도를 넘으면 여전히 truncated·UNKNOWN으로 보호한다.

photo-layout compiler1.7/semantic compiler1.5로 현재 파생 출처를 갱신했다. 새 helper도 journey inference 소스 해시에 포함한다. 현재 App의 goal 경로는 **같은 현재 장면의 checked placement contract**를 core에 전달한다. 과거wire1.0/1.1/1.2는 보존하며 host-only1.3을 외부 observer 응답으로 허용하지 않는다. 실제수신1.2를 거절하던 오프라인 exact-observer-reuse 도구의 호환 검사만 수정했고 원 body/SHA 결속을 유지했다. 특정 사진명/SHA·방 규격/물체 위치를 production 분기로 넣지 않았고 정지/실물guard를 변경하지 않았다.

### 추가 HTTP 없는 재현과 실제 Isaac 범위

[동일 원 후보 재검사](../../outputs/physical-ai-p2-20261011-v429/stored-replay-4/result.json)는 실제 보존된 관측/semantic 후보를 읽고 원 instance expansion trace를 그대로 대조했다. 원 후보·입력 bytes는 변경하지 않는다. 식당 초기와 첫 수정, 거실 두 수정은 실제 compiler→core까지 통과했다. 진짜 좁은 지지면인 나머지2후보는 계속 거절했다. 원 `Go to pallet`은 `pallet_right`를 선택해 checked plan을 통과했고, 별도 explicit `box_on_pallet` 접근 checked plan도 통과했다. 이것은 원 실패 점수 승격이나 실제 새 모델 회복 횟수가 아니다.

[실제 정적 Isaac 결과](../../outputs/physical-ai-p2-20261011-v429/stored-isaac-4/result.json)는 식당 초기/거실 첫 수정의 **변경하지 않은 모델 후보**를 사용한다. 저장 App 프로젝트/동일 사진 archive→실제 Isaac adapter Build→collision-current-match·표시 group 종류/원점·display physics schema0→현재 PNG→export USD와 프로젝트 닫힌 재열기를 확인했다. headless 앱은 정상 close했다. 실내 높은 진단 카메라로 캡처2장을 직접 검토했고, 벽이나 원 장면을 삭제하지 않았다. 현재 parametric 가구가 보이지만 사진 충실도/위치·실측 규격/눈가림 품질 PASS가 아니다. **Run0/HTTP0/로봇0, PASS_STORED_STATIC_BUILD_ONLY**다. 수정 후 actual 명명 목표 이동·이동 중Stop/안정 상태·최신 모델 전체 생성은 아직 NOT_RUN이다.

최초 정적 시도1의 archive tuple fixture 오류는 console 관측 별도 JSON, 시도2의 임시 `Usd.Stage` 수명 오류는 원 FAIL로 보존했다. 시도3은 두 정적 Build/저장·재열기 PASS, 시도4는 읽기 쉬운 진단 카메라의 동일 장면 캡처다. 초기 오프라인 fixture shape/신뢰 source digest·예전 compiler revision 기대값과 지원 wire1.2 도구 오류도 실패 XML/폴더를 지우지 않았다.

최종 **810 tests PASS, 359 subtests PASS /81.67초**는 [현재 소스 XML](../../outputs/physical-ai-p2-20261011-v429/current-source-full.xml)에 있다. provider/core 전체와 App 채팅·목표·편집·reporting/combination/exact reuse 관련을 포함하며 반복 suite를 합산하지 않는다. JUnit1169 cases는810+359 표현이며810독립사진/모델 시험을 뜻하지 않는다. 원 실제 시험 자료254파일의 SHA는 수정/재현/보고서 생성 후 모두 불변이다. regression 통과와 실제3건 전체FAIL은 서로 다른 근거다.

기존 라이선스·로컬 공개 출처 gate의 추가 확인도 [22 PASS /3.53초](../../outputs/physical-ai-p2-20261011-v429/licensing-final.xml)다. 새 helper/시험 소스는 기존 Apache/SPDX/원 URL 관례를 따른다. 이는 외부 자산의 모든 권리나 공개 배포 인수를 승인하지 않는다.

### 보고서와 정확한 다음 작업

[단일 HTML](../../outputs/physical-ai-p2-20261011-v429/final-evidence/report.html)은 실제 paid 화면5개,0HTTP 수정 후 실제 정적화면2개, 공개 원본사진2개를 각각 구분해 **9이미지를 파일 안에 포함**한다. [metrics JSON](../../outputs/physical-ai-p2-20261011-v429/final-evidence/metrics.json)에 input/model/manifest/auth/result/browser/XML SHA·원응답metadata·p50/p95·출처/비용/미정산을 기록했다. 생성기에서9이미지 decode/Pillow 검증과254원파일 불변을 확인했다. 외부 이미지 호스팅·새 유료 호출·GitHub 업로드는 하지 않았다.

로컬 headless Chrome에서도 desktop1400×1000/mobile390×844 두 크기로9이미지의 decode/자체 포함·문서 가로 넘침 없음·현재 실패/회귀 표시를 확인했다. HTTP/HTTPS는 전부 차단했고 실제 외부 요청/page error는0이다. [렌더 검사](../../outputs/physical-ai-p2-20261011-v429/report-qa/result.json)의 보고서 SHA와4캡처를 보존하고 상단/정적 결과를 직접 시각 검토했다. 첫 QA의 상대 module 경로 오류는 browser 실행 전 오류로 별도 보존했으며 모듈 경로만 교정했다. 이것은 모바일 Codex 다운로드 서비스가 된다는 검증은 아니고 로컬 HTML 레이아웃 검증이다.

1. 새 횟수·기한·누적 보호노출 범위 확인 후 **새 cohort**로 수정본 실제 Flash/Super 새 생성→현재 render/critic→명명 목표 이동→별도 moving Stop/stable→reload/reset/닫힌 reopen을 한 번에 재인수한다. 최신 최대3개는 소진했고 원 job 재호출/원 실패 승격을 하지 않는다.
2. 새세션 반복, ordinary 실제 LLM scene edit→preview/apply/cancel/재계획, SIM loop·배터리/장애물/에러 주입, 독립 사진 배치/지지/품질 검토를 수행한다.
3. source429 실제 모델 전체 PASS 전Cloud를 시작하지 않는다. 이후 bounded Cloud·현장 로봇/실측/안전 초기화·영상·외부 권리/개인정보·공개 재현·제출은 각각 승인과 acceptance가 필요하다.

전체 P2 PARTIAL/`whole_demo_pass=false`, nativePAUSED, 원실패/UNKNOWN/실물잠금 유지다. 설치/시스템설정/새agent/타프로세스 강제종료/commit/push0. 사용자가 승인한 계정 잔액을 무시해서 종료한 것이 아니라 원 새생성3개를 실행했고, 이후 범용 수정과 안전한0HTTP 검증을 진행했다.

## 수정본 공개 3건 새 승인 재인수 — v430

사용자는 직전의 “같은 공개 사진·텍스트로 수정본 3회 추가 시험, Nebius 누적상한USD10·승인후2시간, OpenAI·Cloud·로봇 제외” 제안에 **“그래 진행하자”**로 승인했다. 이전 최대3개를 초기화한 것이 아니라 새3fresh generation을 승인한 것이다. 같은 공개 CC BY-SA 식당/거실 사진2개·그 파생Isaacrender·창고text, 같은FlashV4.1/Super120B·각1회·원goal을 사용한다. 특정물체/좌표/정합기준으로수정하지않는다.

새 `outputs/physical-ai-p2-20261011-v430`의 manifest SHA는 `56022b1c1d01f79ff01fd8f2a997aac3be66a26117895017a4c981d74830846d`다. 준비시carry는 **7.02764967**,누적Nebius상한10/각trial1·40k/300s/900s/12HTTP·3repair·보수적20:59–22:59KST다. 이전UNKNOWN·USD1식당hold/원장부/254seal·ordinary설정은그대로이며새OpenAIauthority는없다. 금액추정은invoice가아니다. 새jobID를cohort config label로분리해원job재호출을막고현재support helper/typedgoal 소스를동결했다. 준비는HTTP0·현재runtime/asset/env해시확인PASS다.

2026-10-11T12:03:14.823460Z에owner19844/session33583가첫 `text-warehouse` job `c25383575af3b37c1a95e5c6589bca01`을착수했다. 고정순서는warehouse→dining→living이며최대3만실행한다. 실행중source/Web/build/input/model/policy/evaluation을변경하지않으며소유process를강제종료하거나중복실행하지않는다. native예약은PAUSED인채현재턴소유runner로실행한다. 실제결과는아직미확정이고새UNKNOWN/length/402/원기한·동일원인gate는유지한다.

종료후먼저기존 `benchmark_pilot_report.py`로원본재감사JSON/Markdown을새폴더에저장한다. 원FAIL·source427/428·source429의stored/static회복은이번점수와분리하고현재3입력/1반복범위를명시한다. 실제fresh생성·currentrender/critic·정확한명명목표 이동/거리·별도movingStop/stable·reload/reset·닫힌reopen을통과했는지확인한뒤수치와실제이미지단일결과를작성한다. 후보종류recall은보조지표이며독립사진정밀도·실물·전체모델순위PASS가아니다.

## 수정본 3건 종료와 실제 기능 재인수 — v431

### 승인과 실행 종료

사용자가 승인한 새3개 생성은 전부 실행했고 **기능2/3PASS, 식당1FAIL**로 종료했다. 더 큰 잔액은 횟수 초기화나 무제한 추가시험으로 해석하지 않는다. 원 승인20:59–22:59KST, 누적Nebius USD10/과거 포함carry7.02764967, 공개사진2/파생렌더/창고text, 각USD1/40k/300s/900s/12HTTP·3repair를 유지했다. OpenAI/Cloud/로봇은0이다.

source430 owner19844/session33583는 창고1건을 실제 종료한 뒤 catalog 유효기간 만료로 다음 dispatch 전에 정상 종료했다. 사진2건은 그 scope에서 미호출이며, 첫 결과를 [수정 전 원감사](../../outputs/physical-ai-p2-20261011-v430/pre-catalog-refresh-audit/public-pilot.json)로 먼저 저장했다. catalog 기한은 사람의 새 승인 기한과 별개다.

기존 보안저장소 등록키로 기존 bounded metadata GET2(`models_info`, `models`)만 실행해 FlashV4.1/Super120B의 동일 모델ID·가시성·image/text 기능·context·가격을 확인했다. 키/헤더는 출력하거나 저장하지 않았다. 현재 catalog 유효기간은 원 승인13:59UTC까지만 설정했다. 이후 준비의 dataset label이 기존64자 ID 경계를 넘어 `BENCHMARK_ID_INVALID`가 발생했지만 inference0/campaign생성전 실패였으며 부분폴더와 [오류](../../outputs/physical-ai-p2-20261011-v431/preparation-failure.json)를 보존했다. 짧은 새 label과 같은 재확인 cache로 준비해 metadata GET을 반복하지 않았다.

남은2사진만 새 manifest `cff2e74a12034752088db5ad33d58af1be50d414f65fe8649de98942ed761e08`로 이어갔다. carry7.03326567에는 먼저 통과한 창고의 추정비용.0056160도 포함된다. source431 owner17912/session20423는12:09:50UTC에 식당을 착수하고, 한 모델 실패만으로 중단하지 않고 거실까지 실행해 `LOCAL_JOB_BOUND_REACHED_NO_EXTRA_JOBS`/exit0로 정상 종료했다. 통과한 창고/시작된 사진 재호출은0이며 승인3슬롯을 넘기지 않았다.

source430/431의 **product/harness/Web/build freeze는 동일**하다. 각 scope의 dataset-spec/auxiliary-reference는 창고를 제외하는 case subset이라 경로/SHA가 다르지만, 각 사진의 원 입력·prompt·goal과 사전 보조평가기준은 정확히 대조해 동일함을 확인했다. 이를 소스 변경이나 서로 다른 모델을 섞은 최적 순위표로 표현하지 않는다. 원source427/428의0/3 실패와429 저장후보 정적 회복은 이번 새 성적과 별개다.

### 실제 결과와 감사

| 입력 | 새 job ID | 기능 | HTTP / 수정 | 생성 active s | 모델 HTTP 합계 s | 원 명명 목표 오차 m | 신규 추정 USD |
|---|---|---|---|---|---|---|---|
| 창고 텍스트 | c25383575af3b37c1a95e5c6589bca01 | PASS | 2 / 0 | 14.859 | 14.626 | 0.0397815604 | 0.0056160 |
| 식당 공개 사진 | e4d1c6c645320a1eb8e392815713b976 | FAIL / REPAIR_STALLED | 9 / 3 | 94.156 | 91.361 | 미도달 | 0.0881505 |
| 거실 공개 사진 | 2ccd10b357dc9a712c3a5157dc8d1d75 | PASS | 6 / 0 | 80.844 | 78.374 | 0.0394581981 | 0.0334680 |

기존 reporter의 [source431 원감사](../../outputs/physical-ai-p2-20261011-v431/final-audit/public-pilot.json)를 owner 종료 후 제품 수정 전에 저장했다. 최신17HTTP는 모두 stop/nonempty, 요청·응답·SHA·usage·장부 audit PASS다. 새UNKNOWN/held0·신규추정합계 **USD0.1272345**, 과거 사용·UNKNOWN·식당USD1 fullhold를 포함한 보호노출 **USD7.15488417 / 누적10**이다. 보호노출은 청구액/잔액이 아니며 invoice 대조는 미검증이다. 오래된 hold를 해제하거나 budget을 초기화하지 않았다. 요청별 실제 metadata p50=9.484초/p95=17.1594초다. 생성 active·HTTP 합계·Isaac 부팅/전체wall time은 구분한다.

기능PASS인 창고/거실은 fresh ordinary App/API의 채팅 질문/명시 생성 승인→현재 Site2.2 inventory→실제 Isaac Build·현재 PNG→첫 preview 이동→**원 Go to pallet/Go to chair 명명목표 실제 PhysX 도착**을 확인했다. 반환 경로가 실제 움직이는 중 별도 Stop, paused pose 안정성, 접힌 Twin의 chat Stop, reload 시 Build/Run/승인 복원없음, explicit reset/telemetry 해제, backend를 닫은 뒤 saved project/현재 render-review 결속 재열기가 통과했다. 단순 도착 후 cleanup 정지를 moving Stop으로 세지 않았다. 거실의 복수 chair 선택은 동결 saved-ID 정책으로 해결했으며 새로운 쉬운 목표로 바꾸지 않았다.

실행 ID가 generation·순수CPU profile·engine receipts에 연결되는 desktop/mobile Diagnostics 검색·paging·one-hop incoming/outgoing 그래프·export도 actual 경로에서 확인했다. export는 raw 제외이며 로봇 권한을 만들지 않는다. 소유 launcher backend/engine/browser는 `stopped`로 정상 종료했고 타프로세스 강제종료0이다.

### 식당 배치 실패의 원인과 제한된 진단

식당 초기안은 추정4×5m방/1.4×0.8m테이블에 매트4·접시4·잔4를 **같은 상판의 비중첩 sibling12개**로 배치했다. 초안의 `PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE`5개는 bounded repacking512노드 종료이며 `global_infeasibility_proved=false`다. 기존 범용 되돌리기 수정은 실행됐지만 제한된 탐색에서 유효 witness를 못 찾았다. 방 규격 추정 자체는 실패 조건이 아니다.

1. 초기 `6587cabf…`의5개 오류는 `NODE_BUDGET_EXHAUSTED`다.
2. 수정1 `6096fdec…`은 매트3개를 의자 seat와 접시를 chair back으로 옮겨4개 오류가 남았다. 매트0.45m+양쪽0.01m여유는 의자0.46m면에 들어가지 않아 `EMPTY_VALID_DOMAIN`이다.
3. 수정2 `da07c74f…`은 매트를 다시 테이블로 옮기며4개 오류와512노드 종료가 남았다.
4. 수정3 `b06a8ed9…`은 의자부모로 다시 옮겼고 같은 chair seat의 접시2개도 `GRID_SEARCH_EXHAUSTED`였다.4개 오류가 남아REPAIR_STALLED로 종료했다.

세 patch는 실제 적용·SHA/변경ID가 기록됐으며 동일응답을 무조건 중복 거절해서 실패한 것이 아니다. room/table dimensions는 변경하지 않았다. 요청/검증 로그는2MiB 이하 structured redacted 원문/SHA를 보존해 이번 완전감사에 성공했다. 따라서 이전 로그 잘림 문제와 이번 geometry/수정 미회복을 구분한다. 이번 실패는40k소진·빈final·300초timeout이 아니다.

[추가0HTTP sensitivity](../../outputs/physical-ai-p2-20261011-v431/support-sensitivity.json)는 동일 저장 후보와 생산 함수를 사용하되 **오프라인 호출 인자만**512노드/2초/분기32와16,384노드/5초/분기256으로 비교했다. 초기상판12개와 수정2상판11개 모두 생산 한도는512노드, 확대는각7838/8350노드 부근5초 만료였고 witness는없었다. 시간변동은 가능하며 전역불가능의증명/새모델회복이아니다. 원후보/production함수·상수·충돌/여유기준/SHA 변경0·Run/로봇0이다. 한도 확대만을 해결책으로 채택하지 않았다.

다음은 **매트 위 접시처럼 층별 지지와 독립 sibling의 구분**, 그리고 치수·부모 dependency를 바꾸는 모델 patch 범위 진단이다. 같은 상판에 모든 물체의 XY 비중첩을 강제하는 표현이 사진의 실제 포개짐을 제한할 수 있다는 **가설**이지, 이 후보가 반드시 정상 배치 가능하다는 결론은 아니다. 실제 지지 geometry witness·합성 일반 회귀로 분리 검증해야 한다. 특정 사진/규격 강제화·물체 삭제·충돌 제외·실물guard 완화로 통과시키지 않는다.

### 기능과 사진 품질의 구분

거실은23관측엔티티/15저장물체로 fresh 생성과 actual 이동·정지는 통과했으나 현재 렌더critic은 **uncertain**이다. 사전 evaluator-only 최소 종류 대응은 거실3/7=42.9%(관측/저장), 식당 관측6/8=75%/저장0이다. 종류 대응 한계·관측 누락과 library 표현 차이가 있으므로 총 인스턴스recall·배치/지지 정밀도/실측/사람눈가림 품질 점수로 사용하지 않는다. `qualified_full_quality_pass=0`, human_reviewers0, metric scaleUNMEASURED이다. 텍스트는observer/critic미호출이라 사진 관측 모델을 비교한 표본으로 세지 않는다.

이번 결과는 **고정 조합의 개발 기능 재인수**이며 전체 모델 순위·holdout·통계적 최적조합 증명이 아니다. 원0/3을2/3으로 덮어쓰거나 소스가 다른 과거 모든 PASS를 합산하지 않는다. 창고/거실 기능 성공을 ‘사진 재현 완성’, `whole_demo_pass=true` 또는 PhysicalAI제출 전요건 충족으로 표현하지 않는다.

### 보고서·불변성·현재 잔여

[단일 HTML](../../outputs/physical-ai-p2-20261011-v431/final-evidence/report.html)에 실제 새 화면8장과 원본 공개입력2장, 수치/실행ID/소스·model·manifest·auth·원응답 SHA/비용/실패 히스토리를 넣었다. [기계 판독 metrics](../../outputs/physical-ai-p2-20261011-v431/final-evidence/metrics.json)도 별도 로컬 보존한다. 사진/원prompt/좌표/raw는GitHub에올리지않았다. 원사진 CC BY-SA출처를 유지하고 생성보고서에Apache를자동적용하지않는다.

보고서 최초 생성의freeze비교는scope별dataset/auxiliary파일경로까지비교해 `PRODUCT_OR_HARNESS_FREEZE_DIFFERS`로0HTTP중단했다. 이파일4개만scope차이로분리하고각case 입력/goal/evaluator를정확히대조한뒤전체 product/harness/current SHA를확인했다. 원자료를고치거나감사를생략하지않았다. 로컬 headless Chrome QA 최초 sandbox spawnEPERM은browser전실패로 [기록](../../outputs/physical-ai-p2-20261011-v431/report-qa/spawn-failure.json)보존, 정식권한검토후같은로컬검사를실행했다. [desktop/mobile QA](../../outputs/physical-ai-p2-20261011-v431/report-qa-reviewed/result.json)는10이미지decode/자체포함·가로넘침없음·기능/품질/비용구분·외부request/pageerror0PASS다.4캡처를보존하고상단/실제화면을직접시각검토했다. 모바일Codex다운로드서비스PASS를뜻하지않는다.

원429봉인254파일과430종료자료84파일은전부SHA불변, 두scope의current제품/harness/Web/build과ordinary전역설정불변이다. 기존frozen source회귀810tests+359subtestsPASS는직전429의같은소스근거이며이번에재실행한신규검사라고쓰지않는다. overlap suite/paid실험수를합산하지않는다. 준비/보고서오류·원FAIL/UNKNOWN/held·dirty를보존했고 commit/push/install/system/새agent/타process강제종료0이다. native예약파일의PAUSED상태를다시확인했다.

정확한 다음 순서는 **식당층별지지/repair dependency0HTTP진단·범용수정과회귀 → 새승인·새동결실제재시험 → 독립사진품질/세션반복·ordinaryLLM편집/SIMloop·이상주입 → 승인된Cloud/현장로봇/실측·안전초기화/영상·공개권리·PhysicalAI제출**이다. 현재새3cap소진, P2PARTIAL/wholefalse·Cloud/실물미인수다. 현재유료시험과소유runner는끝났으며더이상RUNNING이아니다.
