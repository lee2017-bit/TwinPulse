# 상대배치 초안과 센서 연결 준비 — 2026-10-15

상태: **PARTIAL**. 수정 가능한 부분 Twin과 실제 수정/Undo는 확인했다. 사진 배치와 센서 정합 완료가 아니다. 이전 v484의 기능 성공도 사진 품질로 승격하지 않는다.

## 범위와 사전 판정

목표는 사진의 실측 없는 방을 정밀 복제하는 것이 아니라 주요 가구의 상대 위치·방향·부모 지지가 대응 가능한 수정 초안이다. 정확한 거리/치수/재질/소품 완벽도와 구분한다. 사진 추정은 로봇의 free-space 또는 실행 권한이 아니다.

기존 Flash/Super, 원사진 `ITM0018.jpg` SHA `4fea13acb1152a742db047a0fd2797ea3850e4c42c016d6fbe8a5050b79933c2`, 기존 Nebius 누적 USD10 지속 승인 사용. 직전 보호 누적 USD5.9306919, UNKNOWN 보류를 환급/초기화하지 않는다. 새 설치/물리 로봇/Cloud/OpenAI/commit/push/공개 없음.

시험은 일반 per-user Start를 실행 도구로 호출하고 실제 Chrome New chat→Attach/입력→Send/Create→현재 Isaac→수정/저장/재열기를 클릭한다. OS Explorer double-click/OS 이미지 clipboard/native Isaac 패널은 별도 NOT_RUN이다. API 호출·고정 응답·이전 장면 재사용을 fresh 생성 성적으로 세지 않는다.

사전 사람 평가(평가용일 뿐 runtime 제약 아님): 원사진의 침대는 왼쪽, 책상은 오른쪽 벽을 따라 길게, 책장/수납은 오른쪽 책상 뒤쪽과 연결, 의자는 책상 앞, 문은 뒤쪽에 있다. 지지 물체는 해당 부모와 함께 남아야 한다. 가림은 불확실, 실측 없는 거리/면적은 추정이다. 수량 충족만으로 PASS하지 않는다.

1. 새 원사진 생성: support pending이 있어도 현재 사진/렌더 비교가 먼저 실행되는지, 구체 배치 진단→동일 예산 수정→새 frame 검토를 확인.
2. 실제 결과의 주요 상대배치/방향/부모/누락/중복을 원사진과 사람이 비교. 기능·배치 품질·측정·센서 판정을 분리.
3. 실제 자연어 피드백→검증 preview→Apply/Undo/저장·닫힌 재열기. 같은 source의 실제 시도로 기록.
4. 저장 센서 UI와 현재 scene binding/미보유 상태를 확인. 같은 방의 적합한 저장 원자료가 없으면 센서 정합은 NOT_RUN. 다른 방 자료를 현재 방 성공 증거로 대체하지 않는다.

## 구현 경계

- strict materialized subset의 원 pending 위험을 유지하면서 critic을 지원 수정 전으로 연결한다.
- layout 문제는 semantic 배치를 먼저 고치고, 지원 능력 부족은 원 수치 진단을 별도 capability 선택에 전달한다. 원 quality 진단을 삭제하지 않는다.
- settled invalid repair의 정체만 정확한 current candidate/plan/원 pending witness/visual 진단으로 strict refinement1.1 저장 가능. UNKNOWN/잘림/취소/저장오류를 허용하지 않는다.
- 상대배치 요약은 dependency roots 기준이며 photo별 대상/좌표가 없다. 수정/Undo/복원 revision이 달라지면 이전 검토는 재검토 필요다.
- 기존 saved LiDAR 기능은 overlay/정합 진단과 제한된 벽 보정이다. 가구 자동 보정/실물 준비 완료가 아니다.

## 실제 실패에서 추가된 계약

P01은 미보정 image region을 world centroid 구간으로 오인한 검사를 발견했다. region 원문과 종전 가정 잔차는 증거에 남기되 `UNVERIFIED_REGION_PROJECTION`으로 분리한다. 그것은 미터 정확도 측정이 아니며 명시 치수·충돌·지원·신뢰할 수 있는 관계/visual 모순 검사는 유지한다. 관계 검토2.0/quality repair1.2로 분리했고 과거 소진 CP를 자동 승격하지 않았다.

P02는 실제 current critic2회 뒤 shared final-review180초 잔여 약42초에서 마지막 검토를 중단했다. 응답은 늦게51.156초에 원 HTTP로 정산됐으며 usage31909tokens/추정.0159618도 비용에 포함한다. 새 호출로 재요청하거나 원 결과를 채택하지 않았다. P03 전에 실제 설정 UI에서 final reserve300초/total1020초로 조정했다. percall300/HTTP24/repair3/기하 기준/Flash·Super는 유지하며 P02와 통제 비교로 합산하지 않는다.

P03은 원사진32개 중30개를 표시했으나 이불→인형의 pending-parent 관계를 구형 저장 계약이 거절해 실패했다. 이를 삭제/평탄화하지 않고 새 source `progressive-twin-1.2`/policy1.1을 구현했다. 최초 pending root는 기존 capacity/clearance eligible native surface prop만 가능하다. 그 아래의 원 surface 의존성만 closure로 보존하며 floor 가구·구조 실패/없는 부모/잘못된 part·model/cycle은 계속 거절한다. host가 materialized anchor/최초 issue/조상경로를 역산·검증하고 원 parent/source/evidence를 유지한다. 배치되지 않은 자식은 가짜 world pose 없이 native hazard와 전체 미확정 높이 `[0,8]`을 보존한다. 이 새 closure가 있으면 높이 예외 없이 SIM/REAL motion 모두 차단한다. 구 source1.0 reader와 기존 effective1.1 저장 형식은 유지하고 새 policy를 effective 편집에도 이월한다.

원 P03 immutable checkpoint의 읽기전용 재컴파일은30표시/2pending/원 bytes 불변을 확인했다. 이는 `PASS_OFFLINE_SUBSET_ONLY`이며 원 실제FAIL을 바꾸지 않는다. 신규 nested current-critic→strict refinement1.1, 3단계 entanglement·cycle/경로/높이조작·부모 pending인데 자식 materialized 거절, 저장 재열기/부모 이동 gate 회귀를 포함한 선택 provider61 PASS/Web72 PASS/빌드 PASS는 보조 증거다. 기존 확장 suite의 legacy asset/API 실패는 전체 green으로 바꾸지 않는다.

동결07 build `20261015T090517Z-aed9c7b50aaa` / source `aed9c7b50aaae0d2e1e47dd4fa705f263f78ad5262e89564fa28101241a8bd96` / ZIP `5ece9f3cfff45859a90a390ac8be0cb8b7a8aea438800aa41f84bd1b0fe78141`에서 P04 실제 New chat/동일 Attach/Create를 실행했다.17HTTP/current-render critic4/repair3 뒤21/28표시·7pending을 strict1.1로 저장했다. request `c19cd76e-ee20-45ef-a308-94b337e1fa1d`/execution `606ceb972dcb479b8fcaa8a35fe0840f`. 원 다단계 지원은 남고 모든 task 잠금이다. 사진 품질은 `QUALITY_REPAIR_LIMIT_REACHED`, uncertain·누락/지원/방향 문제를 보존했다. 준비된 수량만으로 PASS하지 않는다.

사람 비교에서는 침대 왼쪽·문 뒤쪽은 대응하지만 책상 길이/방향, 수납·소품/지원 대응이 충분하지 않았다. 현재 검토의 다수 anchor는 uncertain이다. 실측/위치 정합 합격이 아니며 LiDAR가 잘못 분류된 물체·보이지 않는 지지·상부 소품을 자동 복구한다고 가정할 수 없다.

## 실제 사용자 수정과 최종 표시 계약

E01 실제 자연어10cm 이동1HTTP/9.469초는 책상+자식6부품Y−.1m, engine ACK/disk/transaction frame 확인까지 갔지만 viewport가 옛 generation revision에 고정됐다. 원 실패는 보존했다. source08의 exact-saved binding을 Astra xhigh가 읽기 검토해 workflow null/늦은 decoder의 fail-open을 추가로 지적했고, 최종09는 같은 api/project/input에서 seen/available/revision을 유지해 null 동안 static만 남기고 새 프레임·live·camera를 차단한다. 다른 입력/프로젝트 픽셀 격리와 camera freshness는 그대로다.74Web PASS와 마지막 읽기 검토에서 범위 내P1/P2 없음은 보조 증거다.

최종09 build `20261015T093227Z-6b2282d081a7` / source `6b2282d081a719fef1b61188be8ed33301ed82edfc8aeaeb202a326d3731cc29` / ZIP `6662fb3e80a7ef0a261de039354dcfb1c1ad7a21dc1aff43083986bc79bc4ed6`. 일반 설치 Start→실제 저장 대화Open/Reopen/View에서 edited revision199503… current6.9FPS·카메라와 실제 Undo Apply/ACK/disk/current를 확인했다. 원 objects/inventory/placements·source파일 exact,7pending 유지.

최종09 E02는 “책상 긴 방향을 오른쪽 벽을 따라90도” 실제 자연어→Super1HTTP/19.156초→8부품 방향/좌표 proposal→Apply/ACK/disk/current PASS 범위다. request `f66cd026-3a31-4cbe-abd4-58ddc14459ae`/exec `014519783e564e539b2d1675ef65f71f`/Apply `edit_89ca244c6e8b4c2698464e8b1cdc98d4`. Undo `edit_5a3d876ec5e04325b00f17f2ee79a52b` 뒤 objects SHA `fb74e763f575c7e14bfa650f9614489ac72e65a42b5ef146bc3fe3ffc31af219`,inventory/placements도 원값 exact/current 확인. 이 작은 수동 피드백 회복이 자동 원사진 전체품질 합격은 아니다.

## 센서 다음 단계와 현실적인 경계

최종09 정상Exit/supervisor stopped→동일Start→실제Open/Reopen/View/newstage `6d8f6415-277b-41ce-970f-6e028f38c8cd`/current frame171을 확인했다. `audit-before-restart.json`과 `audit.json`의 source/project/history/scene revision/state/objects/inventory/placements 8필드 exact, 편집4개·pending7 유지. 원 source b0773fb8…/projected024204…/history4bd8e17e…/effective revision3b3c3726… . 새HTTP0/자동motion0. 원transactionreceipt와 재Viewcurrent는 구별했다.

Saved sensor feedback UI의 같은 방 survey/map은 placeholder만 있어 실제 정합은 **NOT_RUN**이다. 다음은 동일 방의 좌표계·시간·센서 외부파라미터·로봇pose/scan 메타데이터가 있는 저장자료를 넣어 overlay→잔차/불확실성→사람 확인→동일 revision patch→Apply/Undo를 검증하는 순서다. 먼저 벽·바닥 점유/주요 가구 대응을 대상으로 하며 가구 의미/상부 지지/전소품 자동보정은 별도 기능이다. 물리 scan은 정지 수집/전원·통신·초기화/신선pose·TF·Stop/별도허가를 통과한 다음 단계다. 이번에 물리 연결/구동은 하지 않았다.

새67HTTP/usage기반 추정USD0.6899982/새UNKNOWN·held·중복0, 원carry5.9306919 포함 보호USD6.6206901/10. 이전 보류 환급0, invoice 미대조. P02의 늦은 응답도 known usage로 포함했고 채택 결과로 바꾸지 않았다. 새 호출을 예산이 남는다는 이유로 반복하지 않는다.

정확한 잔여: 최종09 fresh3반복·text/mixed/unseen2/cancelresume/native Extension/OSimagepaste/Explorer double-click/독립PC/A04복구/공개gate 미인수. 사진 배치·7pending·자동전체 회복·동일방 센서정합 미완료. project read3초 경고와 frame stale 전환 재현. 역사적 PREVIEW_REBUILD_REQUIRED+새saved revision 및 geometry-regression rollback의 progressive mode/원진단 보존도 별도 잔여다. 선택 provider61/Web74/typebuild/sensor29 PASS를 전체suite green으로 바꾸지 않는다. legacy catalog asset/API와 progressive App fixture 실패도 원 기록 유지.

실제 시도·실행 ID·비용·화면은 `outputs/layout-sensor-readiness-20261015/`의 단일 로컬 보고서에 누적한다. 전체 인수 전 완료로 기록하지 않는다.

최종 `report.html`은 실제화면20개 JPEG를 내장한 단일파일이다. JSON/내장수/외부이미지0/diffcheck를 확인했고 파일URL 브라우저 시각QA는 도구정책 차단으로 NOT_RUN·우회0이다. 일반 App 실제화면은 직접 관찰했다. 원사진/좌표/raw/보고서는 로컬 비공개이며 GitHub에 올리지 않았다.
