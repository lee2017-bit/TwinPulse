# 전체 관측 목록과 묶음 처리 검증

2026-10-12 Baseline v1.0.464. 현재 staged semantic 생성 경로에서 방 전체의 물체 개수를 24개나32개로 제한하던 정책을 제거했다. 관측 목록을 보존하고 상세 매개변수는6개씩 처리하며, 중단 시 완료된 작업과 미처리 목록을 체크포인트에 저장한다. 합성60개가 기존 컴파일러를 통과했고 일반 인증 App/API의 중단·명시 재개·저장 복원도 통과했다. 새 실제 모델·Isaac 인수는 별도로 남는다.

## 처리 구조와 보호 경계

- 관측의 entities·관계·치수·불확실성 배열과 positive instance_count에 전역 물체 개수 quota를 부여하지 않는다. 정상 객체와 unknown 장애물을 지우거나 실제 수량을 줄여 통과시키지 않는다. null 수량·개별 위치·지지 미검증과 원 관측을 유지한다. 원본과 host 파생 inventory는 구분하고 expansion trace는1.3으로 기록한다.
- 전체 inventory를 먼저 설계하고 개별 상세 매개변수는 기존6개 묶음 경로를 사용한다. 전체 inventory·완료 objects·정확한 pending_parameter_ids·원본·예산·이전 실행 이력을 저장한다. 재개 시 원본 결속과 완료 매개변수를 재검사하고 이미 완료한 묶음은 다시 호출하지 않는다.
- 모델 응답·관측/semantic 데이터·현대 Site2.2 plan/geometry/sidecar에2MiB 직렬화 자원 보호를 유지한다. 최신 plan의40개 호출·64개 오브젝트 거절도 이 자원 보호로 분리했다. legacy Site2.0/2.1 호출 수와 SpecBundle의 기존 정책은 유지한다. 임의 코드 실행은 허용하지 않는다.
- 충돌·좌표·치수·유한 수치·지지·관측 coverage·중복 ID·출처·주행 안전 기준은 변경하지 않는다. 시간·요청·repair·출력·비용·UNKNOWN 보호와 실물 권한도 유지한다. 큰 목록을 수용하는 것이 사진 품질이나 실물 정확성의 PASS를 뜻하지 않는다.
- 예산 중단은 실행 실패 상태를 보존하되 UI는 ‘미완성 초안 저장’, 완료/보류 수량, 재개 선택을 함께 표시한다. 검증되지 않은 초안을 완성된3D로 표현하거나 자동 Build/Run/재승인을 하지 않는다. 목록에 기록된 provisional 개수와 실제 렌더된 물체 개수를 구분한다.

달러 승인만으로 누적 요청·시간 상한이 자동 늘어나지는 않는다. 이번 재개 시험은 새 명시 승인에 더해 호출 상한을12→24로 설정한 범위다. 이전9개 요청·repair·시간·비용 기록은 이월되며, 미확정 원격 결과가 있으면 재개하지 않는다. 제품 기본 정책은 자동 상향하지 않았다.

## 통과한 검증

| 검증 | 결과 | 근거 |
|---|---|---|
| 합성 전체 생성 |60 inventory/60 매개변수,60 furniture calls,40 calls와64 scene objects 초과인 정상 Site2.2 compile 통과 | [inventory 검사](../../outputs/inventory-work-20261012/inventory-final.xml) |
| 예산 중단과 명시 재개 | 기본9 HTTP 뒤60 전체 목록/42 완료/18 보류 저장, 새 승인·상한24에서 남은3 묶음만 처리, 누적12 HTTP·원 체크포인트 불변 | 같은 검사와 [일반 API 복원](../../outputs/inventory-work-20261012/api-restored-final.xml) |
| 일반 저장 복원 |60개 저장본을 ApplicationService로 다시 열어 동일 draft/원 저장 bytes 유지 | 위 API 검사 |
| 과도한 그룹 자원 중단 | count10억 합성 입력은 대량 확장 전 메모리 보호 중단, 원 압축 관측/count 그대로 저장·repair0·1 fixture 응답·Build/Run0 | 위 inventory 검사 |
| 기존 검사 의미 | NaN·치수·중복·출처·geometry memory·UNKNOWN/승인 guard 유지, 영향72 PASS+28 subtests | [영향 검사](../../outputs/inventory-work-20261012/python-focused-final.xml) |
| 전체 Web |495 PASS, TypeScript/Vite build PASS | [최종 Web JSON](../../outputs/inventory-work-20261012/web-final.json) |

각 묶음의 반복 실행과 서로 겹치는 시험은 독립 표본으로 합산하지 않는다. 모델 응답은 모두 명시된 합성 fixture이며 성능 벤치마크·새 사진 인식 성공률이 아니다. 기본 production 모델 조합이나 사용자 key/settings를 바꾸지 않았다. 시험 화면의 모델명은 fixture 설정이며 새로운 실제 모델 비교가 아니다.

## 실제 Chrome과 인증 API 화면

최종 Web build manifest3개 SHA 검증·외부 browser 요청0·page error0·broker 명령0·자체 API/Chrome 정상 종료를 확인했다. 합성PNG를 사용하고 OS 클립보드·사용자 사진·실물은 조작하지 않았다. 다음 ID는 일반 App/API generation operation이며 Isaac 실행 ID가 아니다.

- 36개 완료: operation `28bdb0ed-cc00-41f9-8acd-b1d799b25517`, request `fed3c817-b4b1-45bd-a56a-cdf103ac481f`,8 audited fixture dispatches. [원 결과](../../outputs/inventory-work-20261012/browser-complete-final-02/summary.json).
- 60개 보류 저장: operation `99254a54-2a00-4a91-afa8-5175c2ceefd9`, request `23275c4c-52ef-4832-a470-3649b33588d1`,9 audited fixture dispatches. [원 결과](../../outputs/inventory-work-20261012/browser-stopped-final-02/summary.json).

![전체36개 매개변수 처리와 저장된 결과](../../outputs/inventory-work-20261012/browser-complete-final-02/02-generated.png)

![60개 전체 inventory 중42개 완료와18개 보류 저장](../../outputs/inventory-work-20261012/browser-stopped-final-02/02-saved-incomplete.png)

## 남아 있는 회귀 실패

최종 Core/Provider·일반 승인/채팅 회귀는 **822 PASS/4 FAIL/+445 subtests PASS**다. XML의1271은 subtests를 포함한 값이며 추가 독립 표본이 아니다. [최종 전체 XML](../../outputs/inventory-work-20261012/python-full-final-02.xml). 아래4개는 v463에서도 실패했으며 수정하거나 숨기지 않았다.

1. photo_semantic_review의 원 재컴파일 검사는 현재 compiler1.8에 대해1.7을 기대한다.
2. rollback_revalidation은 현재 미완성 초안 결과에 대해 None을 기대한다.
3. warehouse_semantics의 support recovery는3 요청을 기대하지만2 요청 후 결과가 반환된다.
4. 같은 warehouse 모듈의 unchanged repair는 REPAIR_STALLED를 기대하지만 발생하지 않는다.

현재 정책과 기존 기대값의 추가 검토가 필요하다. 이번 검증을 전체 제품 PASS로 승격하지 않는다. 첫 전체7FAIL에는 새 byte 검사로 NaN 오류의 의미가 바뀐2건과 구형 count schema 기대1건이 포함됐다. resource 측정과 수치 판정을 분리하고 새 quota 정책의 schema 검사를 갱신한 뒤 위 기존4개만 남았다. 이후 fixture의 필수 source_ref 누락1건도 독립5검사 및 최종 전체로 재확인했다. 첫 FAIL/XML과 임시폴더 권한 거절·잘못된 테스트 경로·fixture 오류는 보존한다.

## 비용과 정확한 잔여

추가 실제 외부 API 호출/비용0, 실물·유료 Cloud·설치·공개 배포0이다. fixture 장부의 가상 토큰/가격은 실제 청구로 계산하지 않는다. 기존 개인 사진·실패·UNKNOWN/held·금융 자료는 초기화하지 않았다. 사용자의 기존 App/Isaac는 종료하거나 재시작하지 않았다. **Python 변경은 정상 종료 후 재실행해야 적용된다.**

아직 모든 크기의 방을 무한 처리하는 구조는 아니다. 방 전체 inventory 설계는 한 응답이며, 관측/설계의 페이지 수집·2MiB 초과 자료의 chunk 저장·별도 승인 episode를 무한히 이어가는 정책은 미구현이다. 아주 큰 compressed group은 삭제 대신 원 evidence와 미완성 상태를 보존하고 자원 중단한다. 현재 요청/시간의 구성 가능한 상한도 유지한다.

다음 인수는 새 승인 범위에서 같은 사진의 실제 Flash V4.1/Super120B 생성·재개와 현재 Isaac 렌더·편집·저장 복원이다. 사용자 Kit가 실행 중인 상태에서 추가 GPU 인스턴스를 시작하지 않아 이번 actual Isaac는 NOT_RUN이다. stale3D·도착 뒤 lease 경고·위4개 회귀·live LiDAR 공통 commit/Undo·현장 인수는 별도 잔여다.

## 변경 파일

Provider의 scene_capacity/observation_instances/nebius_pipeline/semantic_scene/photo_layout/budgeted_pipeline, Core의 scene_resources/validation/site_contracts/site_tools/photo_placement/progressive_twin/photo_quality, App의 product_workflow_service, Web의 conversation-types/ChatWorkspace 및 관련 검사·일반 UI verification helper를 수정했다. 최초 untracked/dirty 상태와 unrelated 변경을 보존했다. 최종 browser summary의 source_sha256 및 build manifest가 실제 검증 파일을 결속한다.
