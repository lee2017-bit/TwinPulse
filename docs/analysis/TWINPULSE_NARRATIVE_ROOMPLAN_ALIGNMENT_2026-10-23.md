# TwinPulse 방향성·사진 충실도·RoomPlan 실파일 종합 분석

## 2026-10-23 추가 검토 · v612: Scanner 앱보다 현 USD/설치12 재사용

**현재 결론:** 추가 iPhone 앱·JSON·USDZ 변환 없이 현 원본 USD로 공간 표시/편집 및 기하 기반 TurtleBot3 SIM 데모가 가능하다. 단지 구현 가능성만의 판단이 아니라 설치 `20261023T045245Z-9d9e533cef09`/source `9d9e533cef0949b6792a0078a50790fb54997dc570a9ca2079d4bb6d6f2fd9cf`의 기존 실제 여정(Import6/실모델 편집Undo3/SIM13/cold3)이 있다. 아래 최초 분석의 “환경 Import 미구현/이 입력 SIM NOT_RUN”은 당시 이력이며 현재 상태가 아니다. 원사진 충실도/실물 정합의 미검증은 그대로다. 이번 사용자 요청에 따라 **검토만** 수행했으며 새 제품 수정·App/Isaac GUI/모델 호출·로봇 접속·업로드는 하지 않았다.

### (1) 실제 USD 재검사

현재 접근한 원본은 `C:\Users\jaewo\OneDrive\문서\카카오톡 받은 파일\Project-2610222326.usd`이다. 이름에 `(1)`이 붙은 별도 사본은 확인되지 않았으므로 그 사본과의 바이트 동일성을 단정하지 않는다. 이 파일은 사용자가 이전에 제공한 38,339bytes/PXR-USDC이며 SHA256 `844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b`가 이전 인수와 같다. 원본은 불변이다.

기존 OpenUSD0.25.11 API로 `/Project_2610222326` Stage와 각 Prim/변환/재질 바인딩을 다시 읽었다. Xform29/Scope2/Mesh30/Material30/Shader30, 정점1212/삼각형620/사각형0. Wall15/Door4/Window2/Floor1, Chair2/Refrigerator1/Sofa1/Storage3/Table1. 외부 layer/reference/asset 의존성0, 원 authored physics0이다. **Stage.HasAuthoredMetadata('upAxis')=true/Y, metersPerUnit=false**이며 API fallback0.01은 실측 단위가 아니다. 원 수치 외접범위10.2632×2.4636×9.0173과 최대 wall 높이2.3036은 native값이다. Meters 선택 시에만 그 숫자를 m로 해석하며 실제 방 치수/면적/정확도로 확정하지 않는다.

명시 단위 없이 현재 환경 inspector를 호출하면 `ENVIRONMENT_SELECT_UNITS`, Library inspector는 `USD_EXPLICIT_UNITS_AND_AXIS_REQUIRED`로 각각 거절한다. 명시 Meters의 환경 경로는30mesh 유지, source path별 composed transform→Y/Z 변환·바닥 원점 보정을 다시 계산한 정점 오차0(오프라인 double 수치 비교), 실제 `author_environment`의 메모리 USD Stage와 `matches_environment` 대조 PASS다. 이 테스트는 Kit 독립 시각 렌더/PhysX contact 시험이 아니다. 원 Prim property/metadata 이름에서 RoomPlan confidence/dimensions/identifier/category 필드는 찾지 못했으며 별도 CapturedRoom UUID/신뢰도 데이터의 존재를 추정하지 않는다.

새 분석 원문: [USD 검사](../../outputs/roomplan-scanner-review-20261023/usd-inspection.json), [Stage/Prim·좌표·현재 author/nav 대조](../../outputs/roomplan-scanner-review-20261023/source-geometry-review.json), [Library 원본 거절](../../outputs/roomplan-scanner-review-20261023/library-source-probe.json). 원 메시 투영과 기존 실제 설치 화면도 직접 보았지만 서로 카메라/렌더 방식이 달라 동일시점 영상 비교라고 하지 않는다.

### (2) 기존 Library와 현재 공간 Import는 다르다

Library는 여전히 `.usd/.usda/.usdc` 정적 메시·명시 단위/축을 요구한다. 여러 Prim의 world vertices를 단일 MeshAsset으로 합치고 bounds-centre로 정규화하며 배치 충돌은 enclosing box다. 방 전체를 이 경로에 넣거나 단위 검증을 풀 이유가 없다.

최신 `EnvironmentImport.tsx`→`environment_workspace.py`→`twinpulse_environment_worker.py`는 New chat/Attach/Import space/명시 단위/Inspect/Import/Show Twin 경로다. 원 bytes/SHA를 별도 archive에 보존하고 각 mesh의 source path와 안정ID를 유지해 별도 USD mesh로 author한다. **원 USD를 통째로 reference하는 완전 무손실 scene editor는 아니다.** 계층 transform을 world-space vertices에 bake하고 새 객체 wrapper로 재구성, 재질은 display/diffuse 색상, 범주는 Prim 이름에서 유도한다. 복잡 shader/texture·원 parenting/변환 스택·RoomPlan API의 semantic confidence 보존까지 약속하지 않는다. 편집은 현재 가구1개의 XY translation/preview/명시 Apply/ACK/저장/Undo이며 회전·크기·벽 구조 CAD편집은 아니다.

같은 설치12의 실제 Import/AI편집/Undo/저장/cold·LiDAR/4방향/60초/목표도착·Stop/반출 원문은 [최종 인수 보고서](../../outputs/robot-roomplan-ready-20261023/report.html)와 [saved cycle](../../outputs/robot-roomplan-ready-20261023/roomplan-saved-cycle12.json)이다. 이번에는 이를 hash-bound 원문과 재대조했지 새 일반 GUI 시험을 했다고 하지 않는다. focused 환경/nav 보조16개도 새로 PASS했다. 첫 unittest 직접실행은 프로젝트 PYTHONPATH 누락으로 loader2ERROR였으며, 시험환경 경로만 process-local로 명시해 재실행했다. 제품 수정은 없고 별도 최초 raw 파일은 없으며 원 도구출력/이 기술 이력으로 남긴다.

### (3) JSON/Scanner 결정

이번 목적의 geometry·객체별 위치/형상·대상 이름은 현 USD에서 얻으므로 JSON을 필수입력으로 추가하지 않는다. Apple은 CapturedRoom을 JSON/Plist로 encode하고 node-name↔UUID metadata로 연결하는 별도 경로를 설명한다. 그 자료는 confidence/고유ID/객체 속성·재스캔 추적 등이 실제 요구일 때 유용하며 geometry로 이를 임의 복원해서는 안 된다. 현재 서드파티 앱의 숨은 JSON 메뉴/실제 권한은 확인하지 않았고 필요성도 없어 추가 조사하지 않았다. [Apple RoomPlan](https://developer.apple.com/augmented-reality/roomplan/), [Apple WWDC23 export/metadata](https://developer.apple.com/videos/play/wwdc2023/10192/).

USDZ는 의존성을 묶는 전달 package이지 정확도 개선기가 아니다. 이번 원본은 외부 의존성이 없고 직접 USD 지원으로 통과했으므로 전환 이익이 입증되지 않았다. [OpenUSD USDZ specification](https://openusd.org/release/spec_usdz.html). Xcode의 macOS 요구는 공식 확인했으나 사용자의 Mac/Xcode/서명·실기기 접근성은 미확인이다. 그러므로 일주일 안에 별도 앱을 완성한다고 약속하지 않고 데모 이후 검토한다. [Apple Xcode requirements](https://developer.apple.com/xcode/system-requirements).

### (4) 최소 변경 대상·회귀 위험

현재 증거상 **이 입력의 데모를 위해 반드시 고쳐야 할 추가 제품 코드 결함은 확인하지 못했다.** 신규 importer/Scanner 개발이 아니라 검증과 촬영 시나리오를 우선한다. 데이터 손실/통로 오류가 재현될 때에만 해당 경계를 수정한다: `twinpulse_environment_worker.py`(축·단위·mesh/material 추출), `environment_source.py`(source ID·불변 geometry/translation), `environment_geometry.py`(실제 static triangle mesh), `environment_navigation.py`(floor/장애물 projection), `EnvironmentImport.tsx`(입력·상태 표시). 기존 Library/asset store는 변경하지 않는다. core normalization 변경은 렌더/충돌/LiDAR/nav/Undo/cold 전부에 영향을 주므로 별도 importer 완화보다 회귀 위험이 크다. 변경하면 새 같은 설치본 필수 여정을 다시 검사해야 한다.

### (5) 시뮬레이션의 정확한 경계와 남은 데모 검증

현재 환경은 개별 triangle collider/approximation none을 author하며 방 전체 convex/AABB로 채우지 않는다. nav는 실제 floor triangle와 높이0.005–0.30m 장애물의 보수적0.10m cell, goal planner는 기존0.25m clearance/경로5m한도를 사용한다. 이번 오프라인8000cell 중2760free/4-neighbor57 component라는 결과는 입력의 모든 문이 열려 있거나 모든 방을 왕복 가능하다는 근거가 아니다. 연결성은 footprint inflation 전 cell 수준이고 문 mesh도 장애물로 남는다. 보이지 않는 통로를 만들기 위해 Door를 임의 삭제하거나 clearance를 줄이지 않는다.

**Fleet SIM은 kinematic motion/실제 geometry 기반 검사이며 wheel/PhysX 동역학 시험이 아니다.** robot model의 Physics variant none과 pose transform 갱신 경로가 명시되어 있다. collision API가 있다는 것과 실제 마찰·접촉·제동 검증은 구분한다. 기존 RoomPlan12의60초는 held-left 회전이고 Sofa0 도착 path_length는 **0.3784585m**다. 따라서 전 공간 횡단/긴 연속 직진 성공으로 과장하지 않는다. 실제 소파 목표도착은 확인했지만 제출 영상에는 UI로 선언한 시작점에서 원 장애물 옆 **가능하면1–2m의 눈에 보이는 경로**를 기존 안전기준에서 확인해 보여주는 것이 유리하다. 이는 새 필수 런타임 gate가 아니라 데모 장면 선정/명시 시험이며, 불가하면 검증한 거실 구역만 솔직하게 보여준다.

원파일 독립 Kit Stage와 TwinPulse Import를 같은 카메라·명시 scale로 나란히 보는 비교는 아직 별도 NOT_RUN이다. 원 구조/색상/개구부 보존을 설명하려면 이 비교와 실제 dimension 한두 개의 교차확인을 추가하는 편이 좋다. SIM을 위해 실측을 순환 선행조건으로 만들지는 않으며, 실제 목적지 주행에는 현장 좌표정합이 별도로 필요하다. 새 캡처 실패 시 현재 원수치/정점 대조와 기존 실제 Twin 화면을 근거로 쓰되 독립 render 비교라고 표시하지 않는다.

### (6) 남은 약1주 실행안 — 제안, 이번 구현 승인 아님

1. 첫날: 원 USD/현재 Import 숫자·구조 비교를 묶고 독립 Stage/현재 Twin 동일 camera를 확인. 실측 근거가 없으면 selected_for_sim을 그대로 노출.
2. 다음1일: 같은 RoomPlan 거실의 명시 시작점·눈에 보이는 경로/원소파·Stop·scan·가구 이동/Undo/cold를 데모 시나리오로 고정. 거절 시 원인 보존/검증된 구역으로 범위를 명시, 기하·한도를 숨겨 바꾸지 않음.
3. 다음1–2일: 기존 준비가 끝난 실제 App의 한 현장 세션(Check Connection→Prepare→정지센서/부하→저속주행/Stop→scan/반출). 물리 소파 목표이동은 좌표정합 후 별도 범위, SIM 성공을 실물로 바꾸지 않음.
4. 중반 이후: 필요한 최소 수정이 발생했을 때만 같은 설치 회귀·동결. 마지막1–2일은 Home부터 Import/등록/조종/변경·복원까지 고정 크기 영상·실물 별도 footage·제출 설명. 정확한 공식 마감/영상 규칙은 별도 확인 대상.
5. 실패 대안: 실물 미통과면 SIM과 실제 실패/부분근거를 구분 제출. 원 스캔 자체가 중요한 부분을 누락했다면 기존 앱의 해당 구역 재스캔/재export가 자체 Scanner 개발보다 작은 대안이다. 다른 scan을 기존 원본으로 위장하거나 이름/충돌을 임의 재작성하지 않는다.

### (7) 이번에는 하지 않을 것

불필요한 USDZ 전환/JSON 의무화, 별도 iOS 앱·서명/TestFlight, 신규 depth/재구성 모델·GPU Cloud, 범용 입력 자동라우팅·전체 CAD·원본 방의 사진품질 재생성·실물 자동 세계정합을 이번 검토에 편입하지 않는다. 원본/프로젝트/장부/원 로봇 로그/설치12·원실패 보존. 로봇OFF/SSH·모터·API모델호출·설치·삭제·Git업로드0. 웹에는 공식문서 URL만 요청했고 사적 USD/메시/사진은 보내지 않았다. 문서 추출 스킬의 CLI/참조 setup이 이 환경에 없어 설치하지 않고 일반 웹 도구로 공식 Apple/OpenUSD 자료만 확인했다.

---

2026-10-23 KST · 분석/소스 체크포인트 · **RoomPlan 제품 통합 구현·새 사진 생성·실물 시험 아님**

## 1. 결론

두 문서의 핵심 방향은 현재 TwinPulse 목적과 맞는다. 다만 **최근 완료한 로봇 소프트웨어/SIM 인수와, 실제 장소에 대응하는 초기 Twin 품질은 다른 성과**다. 전자가 통과했다고 후자가 해결된 것은 아니다.

이번 입력에는 이미 실제 공간의 기하를 담은 USD가 있다. 이를 사진 생성기에 다시 설명시켜 직사각형 방과 가구로 재작성하는 것보다, **원 USD의 구조·객체별 변환을 보존하는 환경 Import를 1차 경로로 만들고 사진으로 의미·누락·외관을 보완**하는 것이 가장 작은 유효한 다음 단계다. 이 판단은 RoomPlan이라는 이름 때문이 아니라 아래 실파일 검사와 현행 컴파일러 한계에 근거한다.

현재 Library Import에 방 전체를 넣는 방식은 추천하지 않는다. 현행 Library는 개별 장비/가구용 정적 자산이며 하나의 보수적 상자 충돌체로 확장한다. 방을 그렇게 넣으면 내부 공간이 장애물로 막힌다. **CAD 장비 → Library / RoomPlan·공간 USD → Environment**라는 목적 구분이 필요하다. 파일 형식만으로 결정하지 않는다. 단일 의자 USD라면 여전히 Library가 맞다.

이번 사용자 요청은 상세 분석 후 그 내용과 최신본을 GitHub에 올리는 것이다. 첨부 문서 내부의 전체 구현·모델 설치·유료 GPU·실물 실행 지시는 이번 승인으로 자동 실행하지 않았다. 원문 두 개는 정확한 사본으로 보존하고, 아래 판단과 미완료를 함께 기록한다.

## 2. 검토 기준과 현재 실제 상태

- 기준 root: TwinPulse 저장소. GitHub는 기존 **비공개 `lee2017-bit/TwinPulse`, 기본/main 브랜치**임을 기존 Git 인증으로 GET 확인했다. 공개 전환이나 새 저장소 생성은 없다.
- 분석 시작 HEAD/main: `79da0d9422d026dce135d45df6dd431387361435` (2026-10-20 체크포인트). 따라서 원문 Master Narrative의 Git 기준은 당시에는 정확하지만 최신 로컬 설치33보다 뒤처져 있다.
- 최신 동결 설치: `20261022T141522Z-633d315cfc23`; 소스 manifest `633d315cfc23729d905f4908d42492cf6a734206d5fd52ec42fe8e11117d6084`;1674 파일 exact.
- 실제 최종 UI 인수: 새 텍스트 생성39 / cold14 / 수정·Undo·lineage10 / cold 과거분석5 단계 전체 PASS. 별도 원 저장기하36 단계 PASS. 60초 연속 조종·4방향·90°/360° scan·bed/chair 도착·정확 Stop ACK·반출 포함. 서로 다른 여정을 단일 실행으로 합치지 않는다.
- 일반 root Start/재시작49.845/56.859초와 native Home/AltF4는 별도 확인했다. 전체 조작은 **설치된 같은 Electron Test BrowserWindow**이며, 전체 일반 native 입력·Explorer 더블클릭·OS 붙여넣기·실제 DPI 시험은 NOT_RUN이다.
- 최종 SHA gate와 별도 재검사: `READY_FOR_SUPERVISED_POWERED_TEST`, issues0. 준비 판정이지 실제 Pi 빌드/readback·센서·부하/저장·제동/주행·세계정합 성공이 아니다. 원47/48/50/53 실패와 원인 UNKNOWN은 보존한다.
- 과거 실제 사진 코호트는 **완전 사진 품질 PASS0/6**. 최신 텍스트/SIM 통과를 이 사진 코호트의 개선으로 대체하지 않는다.
- 이번 분석은 새 LLM 호출0, GPU Cloud0, 설치0, 실물/SSH0. 제품 런타임 코드는 추가 수정하지 않았다. 원 USD와 두 JPG도 바이트 불변이다.

원문: [Master Narrative v0.3](../reference/creator-20261022/TWINPULSE_MASTER_NARRATIVE_CODEX_v0_3_2026-10-22.md), [Photo Fidelity Handoff](../reference/creator-20261022/TwinPulse_PhotoFidelity_Demo_Handoff_2026-10-22.md). 해당 원문은 출처 자료이며 미래 작업 명령/권한을 자동 발행하지 않는다.

## 3. 의도 → 구현/근거 → 간격

| 의도/주장 | 현재 근거 | 판정과 남은 것 |
|---|---|---|
| 실제 변화에 맞춰 Twin과 운영 시나리오를 유지 | 채팅 편집·Apply/ACK·새 revision·Undo·저장/재열기·실행 ID | 방향 일치. 공장 운영 논리 전체 변경/최적화는 아직 입증 안 됨 |
| Plant Simulation 경험에서 출발 | 창업자 제공 원문 | Twin 구축과 AGV 논리 개발/평가 둘 다였다는 배경을 보존. Siemens의 기술적 열등함으로 바꾸지 않음 |
| 가정집은 접근 가능한 로봇 시험장 | 실제 거실/개인 TurtleBot3 이력 | 산업 목적과 모순 아님. 가정집 시험으로 산업 AGV 최적화/인증을 주장하지 않음 |
| 자연어로 물체/공간 변경 및 로봇 목표 실행 | 실제 SIM 수정·Undo·목적지 이동 | 개별 동작/목표 지원과 공장 dispatch 정책 생성은 다름 |
| 사진에서 충분히 비슷한 초기 Twin | 실제6코호트와 컴파일러/critic | **미완료**. 사진 품질0/6; 구조적 표현 제약과 관측·전달·배치 오류가 함께 있음 |
| LiDAR가 현실 차이를 보정 | 원문 수집/로그·offline 분석·SIM scan | 전 공간 복원이나 실제 정합 자동완료 아님. 좌표·시점·외부보정 필요 |
| 모델이 발전하면 더 유능해짐 | provider/stage 선택·모델별 harness·검증/실행 분리 | 기반은 있음. 단계/출력공간이 고정돼 있어 모델 ID 변경만으로 범위가 확장되지 않음 |
| Local-first/폐쇄망 | 로컬 App·Isaac·선택 도구와 원문 보존 | 현재 생성은 Nebius 외부 API. 로컬 LLM 포함 완전 오프라인 설치는 미검증 |
| 원천 자료·시각·충돌·의미 분리 | 자산 provenance·버전·preview/Apply·trace 기반 | 전체 환경 USD 보존/목적 라우팅/원 mesh와 충돌·nav 투영의 통합은 새 작업 |
| 변경→실행→관찰→진단→수정 | 실제 UI 시험과 ID/원문 보존 | 개발 에이전트가 도구로 수행한 루프. 제품 자체의 자율 자기개선 완료는 아님 |

## 4. 이번 USD를 직접 검사한 결과

새 모델이나 Isaac GUI 없이, **기존 OpenUSD0.25.11 정적 라이브러리**로 읽었다. Python wrapper만으로는 pxr가 활성화되지 않아 첫 조회가 실패했고, 기존 Library worker가 쓰는 동일한 process-local USD 라이브러리 경로를 이용해 검사했다. 새 설치나 전역 PATH 변경은 없다.

| 항목 | 실제 결과 |
|---|---|
| 원본 파일 | `Project-2610222326.usd`,38,339 bytes, binary USDC |
| SHA256 | `844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b` |
| metadata creator | `Model IO export preview 1.10` |
| upAxis | **Y**, 명시됨 |
| metersPerUnit | **명시되지 않음**; OpenUSD 조회 fallback은0.01 |
| 계층 | Xform29/Scope2/Mesh30/Material30/Shader30 |
| 구조 mesh | Wall15,Door4,Window2,Floor1 |
| 물체 mesh | Chair2,Refrigerator1,Sofa1,Storage3,Table1 |
| geometry | vertices1212,faces620, 모두 삼각형 |
| 외부 의존성 | sublayer/reference/asset dependency0 |
| authored physics | **0**; collision/rigid-body 설정 없음 |
| 원본 변경 | 전후 SHA 동일 |

사용자가 RoomPlan으로 만들었다고 알려준 출처와 내부 이름은 일치하는 단서다. 하지만 metadata만으로 원 수집 앱/iOS·ARKit 버전, 센서 보정/신뢰도나 Apple 원 JSON의 보존 여부를 인증할 수는 없다. 원 촬영 카메라 pose/내부파라미터·측정 신뢰도·원 스캔 시간은 이번 USD만으로 확보되지 않았다.

### 4.1 즉시 드러난 단위 문제

벽 높이는 변환이 합성된 **native 좌표에서 약2.30357158 units**다. 이를 fallback0.01m/unit로 읽으면 약0.0230m,1m/unit로 해석하면 약2.3036m가 된다. 후자가 주거 공간 크기로는 그럴듯하지만 **그럴듯함은 단위 측정/확정이 아니다**.

전체 world AABB는 native 약10.2632×2.4636×9.0173이며 Y가 높이다. 이는 회전된 전체 스캔의 축 정렬 외접 범위일 뿐, 실제 거실 가로×세로나 바닥 면적이 아니다. 원점도 바닥이0이 아니므로 좌표를 그대로 Z-up/1m 장면에 넣으면 높이·스케일 오류가 생길 수 있다.

향후 Import는 `units missing`을 보여주고 원 export 설정/RoomPlan JSON/확인한 기준 길이 중 가능한 근거로 **명시적인 단위 선택**을 받아야 한다. 미터를 추천 후보로 표시할 수는 있어도 자동 확정/계측 PASS를 만들면 안 된다. 원본은 고치지 않고 별도 wrapper에 축/스케일/바닥 기준 변환을 기록한다.

OpenUSD는 미지정 단위에0.01을 사용하며, 다른 metric 자산을 조합할 때 필요한 변환은 조합자가 책임진다. 이 때문에 `stage meters=1`만 지정하거나 파일을 참조하는 것으로 모든 변환이 해결된다고 가정하면 안 된다. [OpenUSD linear units](https://openusd.org/release/api/group___usd_geom_linear_units__group.html)

### 4.2 원형상과 목적을 보존해야 한다

실제 mesh 투영에서는 **연결된 주방/식탁 구역·거실·출입 쪽 꺾인 구조**가 보인다. 원본30mesh를 하나의 상자로 바꾸거나 새 직사각형 방으로 다시 만들 필요가 없다. `Floor0` 역시 전체 외접 사각형으로 대체하면 안 된다.

Apple이 설명하는 RoomPlan은 카메라/LiDAR 기반의 치수·범주를 포함한 parametric 공간 표현이다. 모든 실제 물체의 정밀 스캔 메시를 뜻하지 않는다. 이번 파일도 색상 위주의 단순 형상이며 사진 텍스처나 모든 소품이 포함된 photogrammetry 결과는 아니다. [Apple RoomPlan](https://developer.apple.com/augmented-reality/roomplan/)

### 4.3 현재 제품에 그대로 넣으면 어디서 막히는가

원본을 **현행 소스의 실제 `inspect_usd()` 함수**에 넣은 비용 없는 probe 결과는 `USD_EXPLICIT_UNITS_AND_AXIS_REQUIRED`였다. 축은 있으므로 이 경우 단위 누락이 직접 원인이다. 이 probe는 App UI나 설치 worker의 실제 Import 인수로 세지 않는다.

단위를 정상적으로 해결하더라도 다음 간격이 있다.

1. 채팅 Attach의 `isLibrarySource()`는 USD를 모두 Library로 보낸다. 공간/개별 자산 목적 구분이 없다.
2. Library worker는 여러 mesh를 단일 points/triangles로 합친다. normalize 단계는 bounds 중심으로 재정렬한다. 원 객체 계층/이름·원점 관계를 환경 편집과 목표 선택에 그대로 재사용할 수 없다.
3. `expand_library_asset()`는 이를 `equipment` 하나와 `ShapeSpec('box', dimensions)`로 확장한다. 장비용 보수적 충돌 상자이지, 방의 벽·문·통로 충돌 표현이 아니다.
4. UI accept에는 `.usdz`가 있지만 실제 `_import()`는 `.usd/.usda/.usdc`와 일부 자산만 구현했다. 보이는 확장자 목록이 지원 완료 증거는 아니다.
5. 원 USD에는 collision이 없으므로 가져오기 성공만으로 주행 가능해지지 않는다. 원형상을 읽는 경로와 별도의 충돌/이동영역 검사·Isaac readback이 필요하다. [Isaac physics fundamentals](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/physics/simulation_fundamentals.html)

관련 소스: [Library worker](../../scripts/twinpulse_library_worker.py), [Library Import](../../packages/twinpulse_app/src/twinpulse_app/library_workspace.py), [mesh contract/box collider](../../packages/twinpulse_core/src/twinpulse_core/library_assets.py), [Attach routing](../../apps/twinpulse-web/src/library-workspace-types.ts).

## 5. 두 사진과 USD의 대응: 확인한 것과 모르는 것

사진1은 식탁·의자·냉장고 및 연결 통로 쪽, 사진2는 소파·창·TV/선풍기 쪽을 보여준다. **서로 다른 방이라는 뜻이 아니라 같은 큰 공간의 부분 관측**이라는 사용자 설명을 따른다. 화면 밖이 보이지 않는다는 이유로 USD의 벽/가구를 삭제하거나 사진별 방을 독립 생성하면 안 된다.

| 비교 대상 | 현재 대응 | 아직 확정 못 하는 것 |
|---|---|---|
| 식탁/냉장고 | USD에 Table1/Refrigerator1, 인접 구역 구조 있음 | 사진 카메라 pose·정확 치수·식탁 주변 의자별 대응 |
| 소파/창 쪽 | USD에 Sofa1/Window2, 주방과 연결된 거실 구조 있음 | 사진 픽셀과 USD면의 정확 대응/출입문 경계 |
| 의자 | USD Chair2; 사진에는 여러 의자가 보임 | 실제 수·가림·스캔 누락/시점 차이를 구분해야 함 |
| TV/선풍기/화분/바구니/의류·가방 | 사진에는 보이지만 해당 독립 mesh 범주는 USD에 없음 | 다른 Storage에 흡수됐는지, 미검출인지, 촬영 간 이동인지 |
| 통로·임시 장애물 | 사진의 열린 중앙 바닥과 일부 바닥 물건 관측 | 가려진 바닥의 free-space, 전선/얇은 물건의 센서 검출 |

**소파를 침대로 바꾸거나 `nearest bed` 데모를 이 거실의 정답으로 쓰면 안 된다.** 여기서는 실제 대응이 확인된 소파/식탁 등을 목표로 삼는 것이 맞다. 사진은 누락 후보와 의미를 보완하되, 대응 근거 없이 원 스캔 가구를 자동 이동시키지 않는다.

두 JPEG는 각각960×720이고 부분 범위/서로 다른 시점을 담고 있다. 현재 UI와 staged pipeline은 **0장 또는1장** 경로이며, 두 장 동시 fusion은 구현되지 않았다. COLMAP은 겹치는 시점과 대응점이 필요하다고 설명한다. 이번 두 장만으로 중첩·pose·전체 커버리지가 검증됐다고 말할 수 없다. 영상/추가 사진을 받으면 겹침과 재투영 오차를 검사할 수 있지만, 현재 USD가 이미 있는 상황에서는 그 수집을 첫 Import의 필수 조건으로 만들 필요가 없다. [COLMAP capture guidance](https://colmap.github.io/tutorial.html)

원 사진 SHA:

- `KakaoTalk_20261023_001641404.jpg`: `79328b5b50cff0ee0f69e3ba2feb2afa20bbe9204cbeea7285d03fe8f17e0f9b`
- `KakaoTalk_20261023_001642352.jpg`: `4bae813cf9ec1b0dff9b1ba6caf9af09155b274c5b99da313b4060ad14636b7f`

## 6. 사진 정확도 실패는 LLM 하나의 문제인가

**아니다. 관측·정보 전달·표현 공간·배치·자산·검토가 함께 관여한다.** 단계별로 분리해야 한다.

### 6.1 표현 공간의 손실은 최신 소스에도 있다

- `semantic_scene.batch_schema()`는 region9종류와 yaw0/90/−90/180을 사용한다. 강한 모델도 이 wire 계약 안에서는 임의 각도·실측 pose를 출력할 수 없다.
- `compile_scene()`는 `compile_layout()`로 연결된다. 기본 공간은 width/length/height와 **열린 정면의 직사각형3벽**이다. 이번 꺾인 공간을 보존하는 임의 wall/floor polygon 경로가 아니다.
- 주 배치는0.1m grid와 경계/접촉 후보이며, 큰 물체 우선으로 분리 가능한 지점을 찾는다. 최종 좌표는 연속 수치일 수 있고 경계 보완도 있으므로 “전부 딱9칸 중심에만 배치”는 틀린 설명이다. 그러나 실제 사진 카메라/측정 pose에 구속된 최적화도 아니다.
- 충돌하지 않게 배치됐다는 것은 그럴듯한 공간을 만들었다는 뜻일 수 있지만, 원래 사진에 충실하다는 뜻이 아니다.

근거: [semantic schema/compile](../../packages/twinpulse_provider/src/twinpulse_provider/semantic_scene.py), [photo compiler](../../packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py), [packing candidates](../../packages/twinpulse_provider/src/twinpulse_provider/packing_candidates.py).

### 6.2 원문 trace가 보여주는 전달/배치 오류

2026-10-17 보존 audit의 dining 실행 `d59794ba3f2d4d4f870f8c47f8413d65`는 원 관측에서 의자5개가 식탁 여러 면에 있다고 기술했다. group→individual 변환 후 각 의자의 region/long-axis는 unknown이 되고 derived relations가 비었다. 최종5개는 전부 yaw0,두 줄로 한쪽에 모였다. 따라서 이 사례를 **“Vision이 의자 자체를 못 봄”으로만 설명할 수 없다.** 개별 근거/식탁 상대 배치 제약의 전파와 compiler가 함께 문제다. unknown을 임의 정답으로 채우라는 뜻도 아니다.

ITM 실행 `e7f0ae2a2e134dcfa4072a7970f18a4a`는 `REPAIR_STALLED/needs_revision`이고 bedding의 실제 support domain이 비어 pending으로 남았다. 그 기록에서 desk yaw가0이라는 사실만으로 “90도 틀렸다”고 하면 안 된다. 당시 desk long-axis가 오른쪽 벽을 따라간다는 정정도 유지한다. 지지·구성요소 표현과 unresolved가 별도 실패다.

이후의 모델별 프롬프트/지원면/DAG 보완이 일부 경계를 개선했지만, 최신 installed33의 텍스트/SIM 결과가 이 옛 사진6코호트의 재인수는 아니다. 이번에는 원 감사 자료를 재검토했을 뿐 새 사진 trial을 실행하지 않았다. [당시 실제 사진 인수·정정](../verification/core-library-extensions-20261016.md)

### 6.3 critic과 repair는 측정 기하를 대신하지 못한다

현재 `render_review.py`는 실제 고정 렌더/원본 사진·plan/frame SHA를 비교하고 모순/불확실을 분리한다. 좋은 기반이다. 하지만 사진과 render의 카메라 등록은 미검증이며, 프롬프트도 시점 차이·가림·unknown을 인정한다. 반복 critic이 모두 consistent를 줘도 원 공간의 metric pose를 입증하지 않는다. 관측이 틀렸으면 repair도 잘못된 근거를 일관되게 따를 수 있다.

따라서 **모델 교체나 retry 확대만으로 해결된다고 약속하지 않는다.** 측정/복원 기하가 있을 때는 그 기하를 먼저 보존하고, LLM은 목적·이름·분류·미확인 항목 제안에 한정하는 것이 유리하다.

## 7. 추천 구조: 공통 입력 UX, 서로 다른 실행 목적

```text
채팅 / Attach / 진행·결과 카드 / 동일 project·operation ID
  ├─ 텍스트·사진만: 근사 환경 생성 (추정·unknown 유지)
  ├─ 공간 USD·RoomPlan: 환경 Import → 원 구조 보존 → 물리·nav 검사
  ├─ CAD·개별 가구 USD: Library 자산 가져오기 → 등록 → 장면에 참조 배치
  └─ 외부 도구 분석: 작업 실행 → 결과/변경 제안 → 검사 후 적용
```

이것은 새 라우터/마이크로서비스를 모두 만들라는 뜻이 아니다. 현행 Library/작업 큐·별도 worker·asset store·ProjectStore·Apply/ACK를 재사용하되, **환경 source와 개별 asset을 같은 collider/정규화 계약으로 뭉개지 않는 것**이 핵심이다.

### 최소 환경 Import 계약 제안 — 미구현

1. 입력 원본 SHA·원 layer/prim path·원 축/단위·시점/출처를 불변 기록. 단위 미지정은 user-confirmed 근거와 따로 저장.
2. 원 geometry/material 계층을 별도 source artifact로 보존. 각 source prim에 안정 ID를 부여하고 semantic category/사용자 이름은 별도 매핑.
3. wrapper에 Y→Z 회전,명시 스케일·바닥 기준 transform을 기록. 범용 계산으로 파생하고 사진/방별 좌표 하드코딩은 하지 않음. 원점이 같다는 것과 실물 world 정합은 구분.
4. 시각 geometry,static collision geometry,2D nav/keepout,semantic targets를 구분하고 각 정책 버전/불확실·source lineage를 기록.
5. 방 전체 convex hull/AABB 금지. 실제 floor 경계·문 개구부·객체별 충돌체를 사용해 통로가 열려 있는지 독립 확인. RoomPlan 의자/소파 자체가 단순화됐다면 그 한계도 유지.
6. 현행 compile의 사각 room 재생성/자동 재배치를 Import 경로에 적용하지 않음. 기하 변경은 별도 preview·사용자 명시 Apply·새 revision·ACK 후 저장.
7. Undo는 수정 layer/transform·대상 ID·파생 collision/nav를 함께 복원. cold reopen에서 원 source/변환·동일 scene·원문 링크는 돌아오되 연결/주행 권한은 자동 복원하지 않음.
8. `/World/TwinPulse` 경계와 기존 SIM/REAL 제어/Stop·취소·늦은 결과 차단을 재사용. 외부 도구/LLM이 live stage나 모터를 직접 변경하지 않음.

## 8. LiDAR로 나중에 보정하면 되는 범위

원래 제품 생각인 “대략 맞는 초기 구조→센서로 차이 보정”은 유효하다. 그러나 **세계 프레임/스케일/주요 벽·통로가 무너진 상태를2D scan 하나로 자동 해결하는 단계**와 같지 않다.

- 먼저 원 스캔 geometry와 robot/scan의 transform·센서 높이/방향·시각·단위가 연결돼야 한다.
- scan은 해당 높이에서 맞은 표면이다. 상판 아래가 비어 있는 실제 식탁/의자와 RoomPlan의 단순 박스가 다르면 위치 이동만으로 불일치가 해결되지 않는다.
- 반사/유리/가림/낮은 전선·물건 미검출은 free-space 증거가 아니다. 사진에 나온 임시 물건을 USD에 없다고 삭제/무시하면 안 된다.
- 센서 제안은 source CAD/RoomPlan을 덮는 것이 아니라 장면 revision 또는 uncertain obstacle layer 변경으로 남겨야 한다.
- 오도메트리와 scan 정합·정지 노이즈를 함께 평가한다. 바이트 변화만으로 chassis 이동/정확 정합을 PASS 처리하지 않는다.

이번 제공 자료에는 **동일 시점·같은 좌표로 등록된 실제 로봇 scan**이 없으므로 실제 정합 성능은 NOT_RUN이다. 기존 다른 시점의 로봇 데이터를 이번 USD의 ground truth로 붙이지 않는다.

## 9. 외부 모델·클라우드 선택

| 후보 | 이번 입력/1차 데모 판단 | 조건과 이유 |
|---|---|---|
| RoomPlan 직접 환경 Import | **1순위** | 이미 작고 닫힌 의존성의 삼각 mesh가 있음. 단위 확인·구조/충돌 계약 추가 필요 |
| 기존 사진 파이프라인 개선 | 병행해야 할 별도 품질 트랙 | group/개별 관계·연속 pose·구조 표현/critic 개선을 같은 원사진으로 비교해야 함 |
| DA3 Small/Base | 사진-only/다시점용 **후속 백업 후보** | relative depth/pose는 의미 요약을 보완하지만 자동 실측이 아님. 이번 USD 해석에는 불필요 |
| COLMAP/Open3D | 중첩 영상/다수 사진 확보 시 후보 | 지금2사진만으로 전체 성공 보장 못 함. 확보된 RoomPlan을 두고 선행조건화하지 않음 |
| 검출/분할 | 일부 누락 물체 자동 대응에만 조건부 | 픽셀 mask만으로3D pose·숨은 면·통로가 완성되지 않음 |
| VGGT 계열 | 비교 후보로 유지, 첫 통합은 보류 | checkpoint별 권리·메모리·Windows 지원 검증 후 선택 |
| Nebius GPU Job/VM | **현재 분석·소형 Import에는 불필요** | 무거운 복원이 실제 병목일 때만 선택적 worker로 사용. Isaac은 우선 로컬 유지 |

DA3 공식 모델 표는 Small/Base의 Apache2.0,Large/Giant/Nested 계열의 다른 조건,metric 전용 모델을 구분한다. Small을 “metric 측정 모델”이라고 부르면 안 된다. 원 가중치/revision·의존성·라이선스를 고정하고 VRAM/실측 오차·실패를 시험한 다음 채택한다. 현재는 다운로드/설치/추론하지 않았다. [DA3 공식 표](https://github.com/ByteDance-Seed/Depth-Anything-3#-model-cards), [Small model card](https://huggingface.co/depth-anything/DA3-SMALL)

VGGT도 원 checkpoint와 commercial checkpoint를 구분해야 하므로 일괄 “모두 비상업” 또는 “전부 Apache”라고 쓰지 않는다. [VGGT 공식 저장소](https://github.com/facebookresearch/vggt)

Nebius 공식 quickstart는 Job의 컨테이너 실행/로그 경로를 제공한다. 하지만 계정 GPU 재고·quota·해당리전 가격·콜드스타트·모델 다운로드/스토리지·출력 회수/취소를 이번에는 계정에서 시험하지 않았다. 따라서 서버리스가 VM보다 싸다거나 USD100으로 완료된다고 확정하지 않는다. 필요해질 때 한 작은 Job의 실제 비용/결과 회수 후 다음 단계를 결정한다. [Nebius Job quickstart](https://docs.nebius.com/serverless/quickstart/jobs)

현장 로컬 조회: RTX2070 Max-Q8192MiB/driver592.82, GPU 사용0MiB(Isaac OFF), OS RAM약15.77GiB/당시가용6.73GiB,C:약47.8GiB. 이는 idle 순간 관측이지 신규 모델+Isaac 동시 피크 여유 증명은 아니다. 우선 순차 복원→모델 해제→Isaac 표시를 비교해야 한다.

API 장부의 추가USD50 누적4.6899930/잔여45.3100070과, 사용자 문서의 GPU Compute약USD100은 **다른 예산/서비스**다. 후자는 제공된 진술이며 잔액을 계정에서 확인하거나 사용하지 않았다.

## 10. 10× Agent 방향을 현재 구조에 적용하는 방법

맞는 원칙은 “모델을 더 믿기”가 아니라 **고정 실행 계약과 교체 가능한 추론 단계를 분리**하는 것이다.

| 유지할 안정 계약 | 교체/간소화 가능한 scaffolding |
|---|---|
| source/권한·revision·Apply/ACK·Stop·Undo·원문·비용·독립 품질 검사 | 모델별 prompt·observer/planner 분할·고정 호출 순서·JSON repair·근거 없는 배치 휴리스틱 |
| 외부 도구 결과 검사와 실제 executor | 어떤 모델/도구가 후보 계획을 작성하는지 |
| 일반 UI/Isaac/원 실패 회귀 | 더 유능한 모델이 중간 설명/변환을 줄이는 전략 |

지금은 stage 선택/harness profile은 있으나 task별 benchmark로 자동 route를 검증/승격하는 제품은 아니다. 특히 현9region·직각·직사각형 출력공간은 **프롬프트를 교체하는 것보다 큰 제약**이다. 장기적으로 이를 source geometry를 보존하는 표현과 task capability로 열어두되, 이번 데모 직전 범용 router/자기코드배포를 새로 만들 필요는 없다.

강한 모델을 시험할 때는 같은 held-out 입력의 품질/비용/지연/실패복구와 known-good rollback을 비교한다. 간소화는 가능해도 모델 self-report로 안전/측정·허가를 생략하지 않는다.

## 11. 다음 구현 순서와 중단 조건 — 제안, 이번 실행 아님

1. **현재33 보존**: 이번 Git source checkpoint와 scope별 인수 요약을 저장. 새 기능과 무관한 원 실패를 삭제하거나 최신 사진 성공으로 소급하지 않음.
2. **환경 Import 최소 계약**: 공간/자산 목적 선택·단위 확인·원 source/prim ID·wrapper transform·별도 collision/nav 투영. 먼저 이30mesh 입력으로 정적 검사/표시.
3. **같은 거실의 의미/누락 비교**: 원 structure를 유지하고 사진2장으로 대상 이름·누락/임시 장애물 후보를 검토. 서로 다른 coverage와 unknown을 보존.
4. **제품 전체 여정**: 일반 Start→New chat→공간 USD Attach/Import→검토/Apply→Isaac→SIM 로봇 선택/배치→소파/식탁 접근·Stop/scan→편집/Undo→저장/종료/cold재열기. 직접 제품 변경 API나 저장 결과 재사용으로 새 여정을 대체하지 않음.
5. **사진-only 별도 회귀**: 원6입력 중 재현성 있는 실패를 먼저 고정, group/개별 상대 관계 등 작은 변경 전후를 같은 입력에서 비교. RoomPlan 성공을 사진-only 품질 수치에 합치지 않음.
6. **제출용 이야기/영상**: 실제 변화 대응의 문제→원 공간/Import 결과→의미 있는 변경/재시뮬레이션·Stop→저장/증거. 공장 사진은 산업 적용 예시, 집은 접근 가능한 로봇 시험장. 실제 사용한 Nebius/NVIDIA 기여만 표시.

예상 작업 묶음은 초기1–2일 Import/단위·첫 표시,다음2–3일 collision/nav/편집복원·회귀,남은 기간 데모 동결/촬영이다. **공식 마감 확인/착수 전의 계획 범위이며 납기 보장이 아니다.** 첫 작은 Import가 진전하지 않으면 이유를 기록하고, 동일 source의 외부 USD 표시와 제품 통합 미완료를 구분한다. 별도 사진/영상 geometry 모델 후보는 입력 중첩·단위/신뢰 근거가 확보된 때만 작은 시간/비용 한도에서 시험한다. RoomPlan이 실패했다고 대형 모델 여러 개를 즉시 설치하지 않는다.

공식 Devpost 마감·영상 상한·hardware footage 규정과 원문 webinar 타임코드는 이번 파일/소스 분석에서 독립 확인하지 않았다. 제출 전에 공식 규정 확인이 필요하며, 이번 Git push는 대회 제출이나 새 배포 릴리스가 아니다. 영상은 필요한 증거를 가장 짧게 보여주되 길이를 맞추기 위한 padding은 하지 않는다.

## 12. 성공 기준 — 한 개의 PASS로 합치지 않는다

| 트랙 | 최소 통과 근거 | 이번 상태 |
|---|---|---|
| A 사진-only 충실도 | 같은 원사진·주요 구조/배치·방향/지지·누락/중복을 검토; 새 장면/수정복원 | **미개선/새 시험 NOT_RUN**; 과거0/6 유지 |
| B RoomPlan Import 보존 | source/명시 단위·축·객체별 변환/식별자·원형상과 파생물·불변 bytes | 정적 검사와 typed거절 원인 확인만; **통합 NOT_RUN** |
| C Import SIM 동작 | 실제 floor/개구부·객체별 충돌/센서높이·유효 목표와 실제 도착/Stop·원상복원 | 이 입력에는 **NOT_RUN**; 기존 텍스트/SIM 인수와 분리 |
| D 실제 정합/주행 | 같은 장소/시점 source와 로봇 frame·원scan/odom·독립 이동·제동/Stop/readback | **NOT_RUN**, 로봇 OFF |
| E 미래 모델/route 개선 | 같은 held-out 입력 A/B·실패/지연/비용·recoverability/권리 검증 | 장기 제안, 미구현 |

Import 전후 변환의 수치 동일성은 소프트웨어 보존 검사이고 실제 집의 cm 정확도 보장은 아니다. 상대 배치·통로에 관한 외부 기준이 없으면 “RoomPlan 형상 보존”과 “실물 정확”을 구분한다. 옆방/가림 부분 unknown을 삭제로 해결하지 않으며, 객체 수·성공HTTP·critic consistent만으로 품질 PASS를 만들지 않는다.

## 13. 변경 영향과 회귀 위험

- **Provider**: 기존 사진 경로는 유지. 새 source geometry를 region 요약으로 downcast하지 않는 분기 필요. 단순 모델 ID 교체와 계약 확장은 다른 작업.
- **App/ProjectStore**: environment source/불변 버전·instance transform·semantic map·파생 collision/nav·scene revision 결속. 원 asset store와 Undo ledger를 최대 재사용하되 migration/cold 복원 시험 필수.
- **UI Attach**: `Environment / Library asset / Reference photo` 목적과 단위 확인을 공통 진행 카드에 표시. 명확한 요청은 재확인 남발하지 않고 모호할 때만 목적 선택.
- **Isaac/센서/목표**: `/World/TwinPulse` 소유권·current frame/scene/stage/operation을 유지. 원 geometry를 display·collision·ray·navigation이 서로 다르게 해석하지 않게 독립 first-hit/개구부 시험.
- **회귀**: current33의 시작종료·2SIM·60초/4방향/90/360·Stop·수정Undo/프로젝트 전환·원 실패 로그/cold복원과 새 Import 여정을 **변경된 같은 최종 설치본**에서 다시 시험해야 한다.

## 14. 산출물·공개 경계

GitHub 반영 범위는 최신 소스/시험·두 원문 문서·이 분석·scope별 검증 요약이다. 원 거실 JPG/USD·투영된 사적 평면도·원 로봇 로그/credentials·runtime/projects·전체 outputs/설치 의존성은 포함하지 않는다. 원본은 삭제/수정하지 않는다. 저장소는 비공개 그대로 유지한다.

로컬 상세 근거는 `outputs/roomplan-alignment-analysis-20261023/`의 `usd-inspection.json`, `library-source-probe.json`, 실제 mesh의 top/oblique 투영 및 Git target receipt다. 이 폴더는 Git에 포함하지 않는다. 공유 가능한 수치/SHA 요약은 [정적 검사 요약](../verification/checkpoint-20261023/roomplan-facts.json), 설치33 판정 요약은 [소프트웨어 인수](../verification/checkpoint-20261023/software-evidence.json)를 따른다.

검사 도구: [USD 정적 검사/투영](../../scripts/inspect_roomplan_input_20261023.py), [원본 Library 계약 probe](../../scripts/probe_roomplan_library_contract_20261023.py). 둘 다 분석용이며 새 제품 Import 기능이 아니다.

**최종 판정:** 새로운 방향은 기존 목적의 변경이 아니라, 그 목적을 달성하기 위해 부족했던 **신뢰 가능한 초기 공간 데이터 경로**를 보완하는 것이다. 현재33은 조작/복원 baseline으로 보존하고, 다음 제품 작업은 **환경 Import의 단위·기하 보존·물리/의미 경계부터** 시작하는 것이 적절하다.
