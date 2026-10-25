# TwinPulse — RoomPlan·사진·실물 LiDAR와 최종 데모 검토

2026-10-24. 사용자 외출/로봇 OFF 범위. 저장 원본만 분석했고 새로운 장치 접속·이동·SDK/모델 설치·유료 호출·외부 업로드는 없다. 이전 현장 성공·실패를 덮어쓰지 않는다.

## 결론

현재 방 위에 LiDAR가 붙지 않는 주된 이유는 **자동 정합 단계의 제품 연결이 없기 때문**이다. 센서를 한 바퀴 돌리는 것만으로 그 기능이 생기지 않는다. 새 iPhone 앱이나 치수 JSON만으로 이 연결 누락은 해결되지 않는다.

별도 문제가 실제로 확인됐다. 이전 오프라인 point-to-point ICP의 표본 누락·국소해 때문에 이동을 크게 작게 추정했다. 이를 몸체 미끄러짐으로 단정할 수 없다. 독립 point-to-segment **오프라인 진단**에서는 같은 저장 전후 스캔이 바퀴와 가까운 이동을 추정한다. 실시간 추적기/제어/안전 기준은 이번에 바꾸지 않았다.

현재 USD를 버리거나 전용 Scanner를 먼저 만들기보다, **원 구조 보존 → 정확한 센서 높이 단면 → 검토용 정합/불일치 → 보정 한 곳 → 재시뮬레이션·Undo**가 최초의 “변화하는 Twin을 유지·검증한다”는 목적에 맞는다. 다만 정합·사진 기반 누락 장애물 추가·센서 보정의 RoomPlan transaction 연결은 아직 완성되지 않았다.

## 1. 왜 오른쪽 별도 LiDAR인가

| 단계 | 현재 확인한 상태 |
|---|---|
| 실물 스캔 취득·원문 저장 | 최신 실제 자동 명령 시험에서 확인됨 |
| sensor-local 화면 | 연결·소유 epoch·신선도에 결속된 표시. 세계 좌표가 아님 |
| 로봇 모델 표시 | 추정 anchor + 같은 epoch 상대 추적. `visual_only`, 실제 world localization 아님 |
| scan → RoomPlan 절대 정합 | 현장 취득 경로에 연결되지 않음 |
| 기존 센서 후보 → imported mesh 보정 | procedural `create_wall`/가구 경로와 `import_environment` 사이 adapter 없음 |
| 새 오프라인 단면/정합 검토 | 이번 구현. 표시·통계 가설만, Apply/TF/이동 권한 없음 |

근거: `PhysicalLidarPanel.tsx`, `TwinViewport.tsx`, `robot_fleet.py:live_viewport`, `field_tests.py`, `scene_sensor_review.py`, `scene_obstacle_feedback.py`, `environment_workspace.py`. `physical desired.lidar=False`이며 현재 SIM scan overlay에 실물 점을 몰래 넣지 않는다.

회전은 상대 방향 추정과 겹치는 관측에 도움을 준다. 하지만 원점·방향·스케일·센서 장착 변환·시간 결속·대응 구조가 없으면 방의 어디인지 유일하게 결정되지 않는다. 제자리 360°는 같은 높이·같은 위치의 반복 관측이며 가려진 뒤쪽이나 높이를 새로 복원하지 않는다. 이동은 시점 다양성을 늘리지만 잘못된 추적을 누적하면 오히려 틀어질 수 있다.

기존 RoomMatcher/명시 대응점 proposal/센서 보정 모듈이 저장소에 있다는 사실과 **현재 RoomPlan 실물 경로에 통합됐다**는 주장은 다르다. 기존 photo 벽 fitter는 3–12개 box 벽을 전제로 한다. 원 USD 15개 회전 벽의 AABB/yaw0 proxy를 그대로 넣으면 안 된다.

## 2. 저장 로그: 바퀴와 LiDAR 불일치

원 operation `db929f4ad15e418e88ddd71a85ea55f6`, project `chat_mvki3gm9_e212190a`, connection `e53172d8bc4540af94c646fa82ef4487`.
원 48,376행·30 segment·124,077,855 bytes, receipt SHA `85efb7b5fd539578496de732a484c9119590a4f3b494bd86390ff111c4c6a194`. 매 segment SHA·bytes·행·context를 재검증했다. archive JSONL 검증과 센서 원패킷 재디코딩은 별도이며 Astra가 원 812,436노드를 재디코딩한 결과 positive-valid-quality0은 0개였다.

| 값 | 전진 | 후진 | 해석 |
|---|---:|---:|---|
| 정착 wheel centre | +105.925mm | −107.089mm | encoder 기반, 차체 정밀 측정 아님 |
| 이전 순차 ICP x | −2.965mm | −25.040mm | 원 결과 불변. 추정기 문제를 물리 원인으로 오인하면 안 됨 |
| 전체 링 균등표본, 기존 순차 ICP x | +41.450mm | −33.333mm | 표본만 바꿔도 큰 차이 |
| 새 독립 endpoint segment fit x | +105.776mm | −106.718mm | wheel seed/기대 거리 입력 없이 계산한 지역 가설 |
| 표본 phase 변경에 따른 XY 차 | 0.053mm | 0.268mm | 이 두 진단의 민감도만, 측정 정확도 아님 |
| endpoint–chain XY 차 | 64.888mm | 73.670mm | 여전히 보존·공개 |

확정된 문제:

- 기존 stride+앞 120개 cap은 실제 394–398점 링의 끝부분을 누락했다.
- 기존 ICP는 고정 각도 ray 재측정 합성 방에서 실제 +100mm를 +37.35mm로 추정했다. 같은 점 집합을 이동시키는 단순 합성시험은 이 결함을 잡지 못한다.
- 기존 live ICP residual은 마지막 transform 갱신 전 대응점 오차다. 이번에 실시간 공통 함수를 성급히 교체하지 않았고, 새 **offline 진단만** 최종 transform에서 residual을 계산한다.
- 단순 7→30회 증가는 ray 재측정 국소해를 해결하지 못했다. wheel에 가까운 값을 고르는 방식도 사용하지 않는다.

새 분석은 전체 링 표본/원 point 수, 끝점 frame·raw SHA·원시각, 수렴/퇴화/경쟁 local fit, endpoint/phase/chain 차를 남긴다. 만료는 시작·반복·최종 계산·반환에서 검사한다. Astra가 최종 계산 중 만료 경계 누락을 찾아 음성 시험으로 먼저 재현한 뒤 수정했다.

**정지 baseline 유효 표본은 각각 1개뿐**이며 기존 요구 3개에 부족하다. 회전은 원 incomplete interval 거절을 유지한다. 360° endpoint가 시작과 비슷하다는 것만으로 한 바퀴 회전을 증명하지 않는다. 전체 몸체 판정은 `UNQUALIFIED_UNKNOWN`, 센서 보정/제동/실측 정확도·세계 정합은 미검증이다.

원 `independent-motion01.json`/Astra probe와 이번 `outputs/roomplan-lidar-review-20261024-01`, 최종 `…-02`를 각각 보존한다. 새 추정치로 원 결과를 덮거나 전체 시험을 PASS로 승격하지 않는다.

## 3. USD에 치수와 가구가 없는가

원 파일 38,339 bytes, USDC, SHA `844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b`를 다시 확인했다. 원본은 수정하지 않았다.

- 30 mesh, 1,212 vertices, 620 triangles. Wall15, Door4, Window2, Floor1.
- 주요 가구 **8개**: Chair2, Refrigerator1, Sofa1, Storage3, Table1. “소파만 들어 있다”는 파일 분석 결과는 아니다. 넓은 방을 작게 보는 카메라·단순 흰 형상도 식별을 어렵게 한다.
- Y-up 명시. **metersPerUnit만 미작성**이며 기본 fallback .01은 실측값이 아니다. 현재 Meters 선택은 `selected_for_sim`, 실측 scale 미확인이다.
- 좌표에서 외접 크기를 계산할 수 있다. native 전체 약 10.2632 × 2.4636(높이) × 9.0173. 이는 메타데이터 치수/실측 인증과 다르다.
- 객체 bounds는 **장면 축 AABB**다. 회전한 소파의 X/Y bounds를 실제 길이/너비라고 부르면 안 된다. 이번 Import UI에 `Objects and size`로 정확한 의미를 표시한다.
- 원 mesh는 디테일한 현장 재구성이 아니라 단순화된 가구다. 사진 속 선풍기·바구니·가방·옷·케이블 등의 작은 장애물을 이 입력이 전부 표현하지 않는다. 사진을 첨부했다고 imported USD에 자동 융합되는 경로도 없다.
- nominal 센서 평면 0.182m에서 상부 Storage1/2는 교차선이 없다. “가구가 있는데 LiDAR에 안 보임”과 “누락”을 구분해야 한다. Table0 등의 간단 solid mesh는 실제 다리·탁자 아래 열린 공간을 온전히 나타내지 않는다.

로봇의 2D LiDAR는 그 높이를 가로지르는 표면을 관측한다. 바닥 옷·전선, 유리, 가려짐·반사 특성, 높이가 다른 가구를 일반적인 3D 측정기로 모두 복원하지 못한다. 누락된 작은 물체가 있어도 안정적인 벽만으로 위치 정합이 가능한 경우는 있지만, 모든 미지점을 기존 가구로 강제 대응하면 안 된다.

## 4. 실제 단면으로 한 번 정합해 본 결과

새 `environment_section.py`는 원 triangle에 translation/축변환이 반영된 기하를 높이에서 직접 자른다. AABB 직사각형을 대신 쓰지 않는다. 점/공선·coplanar·통로 공백을 구분하고 원 ID/source path를 남긴다.

nominal URDF 기준 0.182m에서 310개 교차 segment를 얻었다. windows는 유리 return을 가정하지 않기 위해 정합의 양성 면에서 제외한다. 같은 저장소의 기존 bounded `RoomMatcher`를 첫 전진 이전 frame715(396점→전체 링120점)에 적용했다. wheel·추정 anchor를 seed로 쓰지 않았다.

결과: **POOR_FIT**, capped mean error 0.130341m, inlier fraction .716667, rival margin .032876m. 기존 mean 기준 .12m를 넘으므로 불합격 그대로다. 이는 최고 후보의 capped scoring 값이며 센서 계측 정확도가 아니다. 검사 기준을 .14m로 올리거나 유리한 frame을 찾으며 PASS를 만들지 않았다.

`overlay-hypothesis.svg`는 실패 후보를 눈으로 조사하는 자료이지 실제 앱 world overlay가 아니다. 단일 프레임이며 360° 누적/독립 held-out/first-hit 검증이 없다. floor bounds는 검색 상자일 뿐 free-space/footprint 검증이 아니다. 원 USD를 사용자가 지정했음을 기록하지만 archive 내부 scene revision과 새 기하의 대응을 자동 증명했다고 쓰지 않는다. 원 프로젝트 context·receipt·segment·검토 코드 SHA를 함께 남겼다.

최소 후속은 사전 고정한 다른 프레임/독립 대응점과 실제 mesh first-hit를 비교하여 좌표·scale·단순 solid 가구·현장 clutter를 분리하는 것이다. 특정 물체나 벽을 임의 삭제하거나 원본에 없는 치수를 만들어 맞추지 않는다.

## 5. iPhone 앱을 새로 만들어야 하는가

**치수가 안 보인다는 이유만으로는 불필요하다.** 현재 USD만으로 기하·객체 크기와 단면을 구할 수 있다. JSON은 현재 import의 필수조건이 아니다. USDZ도 packaging이며 치수·정확도를 새로 만들지 않는다.

Apple RoomPlan의 object `dimensions`는 bounding box, `transform`은 위치/방향이며 `confidence`는 분류 확신이다. 치수의 계측 오차 보증이 아니다. RoomPlan만 다시 감싼 자체 앱은 같은 단순화·미지원 clutter 문제를 그대로 가질 수 있다. [Apple RoomPlan](https://developer.apple.com/augmented-reality/roomplan/), [Object dimensions](https://developer.apple.com/documentation/roomplan/capturedroom/object/dimensions), [Confidence](https://developer.apple.com/documentation/roomplan/capturedroom/confidence).

추가 세부 형상에는 별도 **ARKit scene reconstruction mesh/depth**가 더 적절한 데이터 후보다. 이것도 근사치이며 작은/얇은/반사 물체 완전 복원을 보장하지 않는다. 카메라 사진 자체나 `.mesh` export 명칭이 dense scene mesh 취득을 증명하지 않는다. [Apple SceneReconstruction](https://developer.apple.com/documentation/arkit/arconfiguration/scenereconstruction), [Apple reconstructed-scene sample](https://developer.apple.com/documentation/arkit/visualizing-and-interacting-with-a-reconstructed-scene).

| 선택 | 지금의 판단 |
|---|---|
| 기존 RoomPlan USD | 작은 실내의 기본 구조 경로로 유지 |
| 치수 숫자 표시 | 신규 앱 없이 이번 소스/UI에 반영 |
| 기존 앱이 dense mesh/depth/좌표를 추가로 export | 지원 여부·실제 산출물을 먼저 확인. 앱 기능을 미확인 상태에서 단정하지 않음 |
| 자체 Scanner | 결정적 데이터가 없고 기존 앱 대안도 부족할 때 후속 선택. 이번에 시작하지 않음 |
| RoomPlan+ARKit 자체 앱의 최소 데이터 | 명시 units/upAxis/origin, 객체 UUID/category/transform/dimensions, confidence 의미, dense mesh/depth, 카메라 intrinsic/pose·센서시각·공유 coordinate frame, 원본/해시·온디바이스 저장/유선 반출 |

현재 Windows 환경이고 Mac/Xcode·서명·실기기 개발 접근성은 확인되지 않았다. 이전 Swift 소스 ZIP은 구동 검증된 앱이 아니다. 새 앱 개발·배포·동일 공간 재스캔·TwinPulse 통합을 남은 제출기간의 선행조건으로 놓지 않는다.

## 6. 최초 최종데모 방향과 우선순위

창업 동기는 단순히 “방을 생성”하는 것이 아니라 **현실이 바뀔 때 Twin과 AGV 운영 시나리오를 계속 업데이트하고 검증**하는 것이다. 집은 접근 가능한 테스트베드이며 공장 활용 목표를 버린 것이 아니다. 현재 LLM·Nebius는 사용자 의도/기존 typed scene edit에 활용하고, 확보한 scan 기하를 LLM이 임의로 다시 그리도록 하지 않는다.

제출의 짧은 성공 경로:

1. 원 USD 출처·명시 SIM 단위 → 실제 Isaac의 벽/주요 가구·치수 검토.
2. 사진에서 누락된 물체 **한 곳**을 식별. 사진은 의미 증거, 치수/좌표는 독립 기준 또는 센서 관측으로 별도 확보. 미확인 물체는 추정/unknown 레이어로 표시.
3. 원 mesh 단면과 저장 실제 scan의 **검토 가능한** 겹침·불일치. 좌표 후보·실측·미검증을 구분하고 360° 자동 보정 완료처럼 편집하지 않음.
4. 기존 가구 한 개의 제한 이동 또는 별도 장애물 레이어 후보 → 명시 Review/Apply → Isaac ACK/현재 frame → 재계획/SIM 이동·Stop → Undo/저장/다시 열기.
5. 실물 finite 제어/Stop의 실제 성공 기록은 별도 보조 근거. 몸체·정합을 증명하지 못한 부분을 SIM 성공으로 치환하지 않음.

현재 이미 import/기존 가구 이동·Undo/SIM 경로는 과거 한정 인수가 있지만 **2의 사진→추가 장애물, 3의 제품 overlay/검증, 4의 센서→import mesh transaction 결속은 남아 있다**. 이는 단순 시간 파라미터 조절로 해결되는 일이 아니다.

다음 구현은 RoomPlan 공통 정합 review adapter/프레임·source SHA·scene revision 결속과 검토 화면이 먼저다. 실패 후보를 원본과 분리해 보여주고, 독립 대응/held-out/first-hit를 통과한 경우에만 transform을 활성화한다. 그 뒤 가구 XY 보정 한 개를 기존 scene transaction에 연결한다. 누락 장애물은 별도 provenance layer로 추가해 원 스캔을 보존한다. live geometry 자동변경·재주행은 별도 단계다.

중단 조건: 정합을 독립 관측으로 검증하지 못하면 제출에는 실패 후보/한계만 짧게 공개하고, **명시 기준점 정합 + 검토된 수동 보정 + 실제 SIM 재계획**으로 좁힌다. 사진만으로 정밀 치수를 만들어 넣거나 새 모델/클라우드를 무작정 추가하지 않는다.

## 7. 이번 변경·실행 방법·잔여

제품 소스:

- `scan_fit_diagnostics.py`, `physical_motion_analysis.py`: offline 분석만. live field_tests/모터·시간·센서/배터리/10° 공백 기준 불변.
- `environment_section.py`: 검토용 원 triangle 단면과 기존 matcher 입력 adapter.
- `environment_workspace.py`, `environment-types.ts`, `EnvironmentImport.tsx`: 기존 bounds에서 계산한 크기 표시. source·geometry·transaction 권한 불변.
- `PhysicalLidarPanel.tsx`: 접힌 Alignment 안내. 자동 정합 미연결을 명시하며 기본 화면의 긴 문구/버튼 확대를 피함.

집중 Python 40개, UI unit 37개 및 TypeScript/build 확인. 최종 증거는 `focused-tests03/result.json`과 세 로그다. 설치 EXE의 실제 frozen `motion-review` 역할도 별도 격리 state에서 원 archive를 읽어 `COMPLETED_WITH_LIMITS`/분석 revision2026-10-24.2/권한false로 종료0을 확인했다. 이는 App의 저장 job/cold GET UI 인수와 다르며 후자는 이번에 실행하지 않았다. 실제 metadata UI는 `ui01/result.json`: 같은 설치·원 프로젝트·객체30·두 해상도 overflow0·명시 종료, 원 runtime/Kit 9개 exact·optional liveness부재1·두 root 자연0을 확인했다. 전체 SIM/실물 회귀를 반복하지 않았다.

합성 검증은 실측 인수가 아니다. Astra가 분석기와 RoomPlan 경로를 독립 검토했고 최종 계산 만료/원 USD 대응 표기 두 경계를 보완했다. `focused-tests01/02`는 단일 벽 2개 교차선으로 adapter의 최소4선 조건을 통과한다고 잘못 기대한 시험 오류가 있으며, 거절을 기대하도록 fixture 계약만 바로잡았다. 01의 frozen검증 도구는 `--role` 오인자로 실패, 02/03은 실제 `--internal-role motion-review`로 종료0이다. 제품 기준을 완화하거나 원 실패를 지우지 않았다. 과거 실패·개발 음성 실패·첫 잘못 선택한 빌드 venv 실패도 성공으로 바꾸지 않는다.

원본 보존 재현(항상 새 출력 폴더):

```powershell
.venv\Scripts\python.exe -B -m unittest tests.integration.test_saved_scan_geometry tests.integration.test_physical_motion_review tests.integration.test_environment_import
.venv\Scripts\python.exe -B scripts/review_saved_roomplan_scan_20261024.py --usd "C:\Users\jaewo\OneDrive\문서\카카오톡 받은 파일\Project-2610222326.usd" --archive outputs/robot-auto-charged-20261024-01/raw/db929f4ad15e418e88ddd71a85ea55f6 --project chat_mvki3gm9_e212190a --output outputs/new-offline-review
```

최종 파생 결과: `outputs/roomplan-lidar-review-20261024-02/review.json`, `motion-review.json`, `height-section.json`, `overlay-hypothesis.svg`. 현재 source/import UI 검증 상태는 같은 폴더의 설치 receipt와 `ui01/result.json`을 따른다. **현장 자동정합/사진보완/전체 제출 데모 완료나 실물 재인수를 뜻하지 않는다.**

## 8. 사용자 보완: RoomPlan + 기존 이미지 장애물 + COLMAP/점 추적 기술 검토

### 8.1 요구의 정확한 해석

2026-10-24 후속 요청은 RoomPlan으로 사진 기능을 대체하라는 뜻이 아니다. **RoomPlan의 구조/주요 가구와 기존 이미지→Twin의 작은 장애물 생성을 합치고, LiDAR 등으로 위치를 보완**하자는 것이다. 원 USD의 가구8개 존재를 확인한 것만으로 이 요구에 답했다고 보면 안 된다.

RoomPlan 출력에 없는 물체는 `not represented`이지 실제 현장의 `absent/free` 판정이 아니다. 사진에서 확인되는 가방·옷·전선 같은 위험을 LiDAR에 안 잡힌다는 이유로 지워서는 안 된다. 반대로 이미지 모델이 추정한 좌표·카탈로그 크기를 실측 장애물로 승격해서도 안 된다.

이번은 기술 검토와 읽기 전용 probe만이다. 제품 코드/등록 설정/설치74db…d2fa/로봇/모델 호출/외부 자료 업로드를 변경하지 않았다. Tavily Research 지침을 읽었으나 CLI와 참조 설치 지침이 없어 신규 설치 없이 아래 공식 자료를 직접 확인했다. 사용자 자료를 검색 서비스에 보내지 않았다.

### 8.2 현재 코드에서 실제 재사용 가능한 것과 막힌 경계

- `photo_layout.py`는 `floor_fan`, `basket`, `bag`, `clothing_pile`, `cable_bundle` 등을 이미 인식할 수 있는 요청/카탈로그 종류로 포함한다. 지원 종류가 있다는 것은 모든 사진에서 정확히 검출한다는 증명은 아니다.
- `room_items.py`는 해당 물체 형상을 결정적으로 만들고 옷·케이블에 별도 합성 keepout을 만든다. keepout은 센서 반사면이나 실제 물체 부피가 아니다.
- 읽기 전용 실제 함수 probe에서 선풍기3형상/바구니1/가방1, 옷더미·케이블은 각 visual+keepout이 생성됐다. 입력 치수/좌표는 명시한 합성값이며 실제 사진 inference 시험이 아니다.
- 현재 `SiteToolPlan 2.4`는 `import_environment` 한 호출만 허용한다. 기존 `place_room_item`을 덧붙이는 순수 재현은 실제로 `ENVIRONMENT_PLAN_INVALID`로 거절된다.
- `SiteRevision`도 `objects == environment_objects(environment)`를 요구하고 compiler는 환경 메시와 procedural object 생성을 양자택일한다. 검증기 한 줄을 제거한다고 혼합 장면이 완성되는 구조가 아니다.
- imported navigation은 원 메시에서 만든 바닥/장애물 셀을 사용한다. 새 물체를 화면에만 추가하고 이 경로를 갱신하지 않으면 로봇은 그 물체를 없는 것처럼 계획할 위험이 있다.

근거 probe: `outputs/roomplan-hybrid-method-review-20261024-01/probe.json`, 실행기 `scripts/probe_roomplan_photo_hybrid_20261024.py`. 원 JSON·USD SHA 보존/기하 적용0/제품 수정0이다.

### 8.3 COLMAP·Google 점 추적·2D SLAM의 역할 비교

| 기술 | 실제로 제공하는 정보 | LiDAR↔USD에서 맡길 수 있는 역할 | 직접 해결하지 못하는 것 |
|---|---|---|---|
| COLMAP SfM/MVS | 겹치는 다중 사진의 카메라 pose·3D 점, 조건에 따라 dense mesh | 사진 물체의 공간적 근거/관측 위치 보완. 복원 좌표를 USD/metric 기준에 별도 정합 | USD를 읽으면 바로 LiDAR가 붙는 기능, 단안 절대 scale, 물체 의미·위험 판단 |
| Google DeepMind TAPIR/TAPNext 계열 | 영상에서 지정한 점의 좌표·가림/재출현 추적 | 처음 확인한 물체/기준점 대응을 여러 frame에 유지. 알려진3D 대응·intrinsics와 pose 계산을 결합 | 2D 궤적만으로 metric XYZ·USD 원점·LiDAR extrinsic/시각 변환 자동 확보 |
| TAPIP3D 등 3D tracking | depth·camera motion을 이용한 3D 궤적 | 영상/depth가 갖춰졌을 때 moving-object layer 보조 | depth/pose/scale의 불확실성을 저절로 제거하지 않음. TAPIP3D는 Google TAPIR와 같은 프로젝트가 아님 |
| AMCL/SLAM Toolbox 계열 | 2D laser map 안 위치 추정/지도 작성 | 현재 센서에 더 직접적인 localization 기준. `map↔USD`를 정합한 뒤 같은 transform으로 로봇·점 표시 | 원 USD/사진의 의미 복원, 작은/낮은 물체 전체 감지, 현재 앱의 자동 통합 |

COLMAP은 정적인 여러 시점에서 같은 부분이 보이는 입력이 유리하다. 공식 튜토리얼은 물체가 최소3장 이상에 보이는 높은 overlap과 카메라의 **이동**을 권장한다. 흰 벽·광택·가림, 단순 제자리 회전은 불리하다. 현재 제공된 거실/주방 사진2장만으로 안정적 전체 복원 성공을 전제하지 않는다. 기존 다른 프로젝트의145frame 성공도 이 입력의 성공 증거가 아니다. [COLMAP tutorial](https://colmap.github.io/tutorial).

COLMAP 결과는 자체 좌표계다. 공식 `model_aligner`는 대응되는 카메라 중심 위치를 이용해 similarity transform을 구한다. 표면 landmark 정합은 별도 대응/추정 절차다. 텍스처 없는 RoomPlan USD를 COLMAP sparse model 대신 넣어 image registration을 바로 수행하는 것은 아니다. [COLMAP FAQ—geo-registration](https://colmap.github.io/faq.html#geo-registration).

사용자가 말한 Google 기술의 정확한 이름은 불명이다. TAPIR/TAPNext로 추정해 비교했으며 특정 제품을 지칭했다고 단정하지 않는다. TAPIR는 query point의 영상 궤적을 추정한다. 이를3D로 쓰려면 depth/triangulation, 카메라 intrinsic/pose, 기준 scale 등 추가 정보가 필요하다. 손에 든 iPhone 영상의 카메라 pose를 로봇 pose로 바로 쓸 수 없다. 두 기기의 동시각/공유좌표나 측정된 rigid transform이 별도로 필요하다. [TAPIR 저자 페이지](https://deepmind-tapir.github.io/), [Google 공식 TAP 저장소](https://github.com/google-deepmind/tapnet).

TAPIP3D는 CMU/PKU/Stanford 저자의 별도 연구다. monocular 경로에서 depth·camera motion 추정을 결합한다. 이 계열을 추가해도 측정되지 않은 metric scale이 자동 검증되는 것은 아니다. [TAPIP3D 저자 페이지](https://tapip3d.github.io/).

카메라 pose가 필요할 경우 known 3D landmark↔image 2D와 camera intrinsics를 이용하는 PnP도 더 작은 대안이다. 처음 대응을 잡은 뒤 점 추적으로 전파할 수 있다. 바닥 접점의 영상 ray를 알려진 바닥과 교차시켜 XY를 추정하는 방법도 있지만, 접점 가림·바닥 비평면·크기/높이·카메라 calibration의 불확실성을 기록해야 한다. [OpenCV PnP](https://docs.opencv.org/4.12.0/d5/d1f/calib3d_solvePnP.html).

### 8.4 정합 실패와 장애물 누락을 분리해야 한다

현재 `RoomMatcher.score`는 모든 표본 return의 거리 오차를 cap 후 평균낸다. 따라서 **로봇 pose 불량**과 **올바른 pose에서 원 모델에 없는 물체를 본 경우**가 같은 점수에 섞인다. 이 코드 특성은 확인했지만, 원 실패의 모든 미일치점이 clutter라는 뜻은 아니다.

원 frame715/원 candidate pose를 고정하고 새 탐색 없이 재계산했을 때 기존 score .13034111359613115/inlier .7166667이 정확히 재현됐다. 연속 triangle 선분까지의 직접 거리(기존 grid 근사와 별개)는120점 중61개≤5cm,26개 5–15cm,33개>15cm다. 마지막33개의 정체는 **UNKNOWN**이며 pose·scale·가림·유리·단순 가구·실제 clutter 중 어느 원인인지 아직 분리되지 않았다.

후속 설계는 기존 불합격을 덮지 않고 **별도 두 평가**를 둔다.

1. 안정된 벽/구조의 다중 관측으로 `room_from_lidar/map` 후보를 추정하고, 독립 frame/기준점·방향·scale/오차를 검증한다. 경쟁해·퇴화·추적 손실은 HELD다.
2. 같은 좌표에서 남는 점·사진 물체를 환경 불일치/장애물 증거로 보관한다. 모두 벽으로 끌어붙이거나 벽 좌표를 변형하지 않는다. 사진 이름만으로 scan cluster의 정체를 확정하지 않는다.

사전 정의한 robust structural estimator로 localization과 model completeness를 분리할 수는 있지만, 사후 유리한 점만 선택하고 기존 .12m 기준을 느슨하게 해서 원 `POOR_FIT`를 PASS로 바꾸지는 않는다.

AMCL은 static map 내 localization, SLAM Toolbox는2D laser mapping/localization에 직접 맞는 후보다. `map→odom→base_link→sensor`와 USD↔map transform을 명시한다. 기존 센서 시각/원문·quality를 지키면서 실제 호환성·부하·재현이 필요하므로 이번 검토를 ROS/SDK 설치나 실제 주행 승인으로 해석하지 않는다. [Nav2 state estimation](https://docs.nav2.org/rolling/getting_started/navigation_concepts/state_estimation/), [SLAM Toolbox 공식 저장소](https://github.com/SteveMacenski/slam_toolbox).

### 8.5 권장 혼합 구조

원 RoomPlan은 불변 기초 레이어로 둔다. 사진 물체는 별도 ID/출처/관측시각/관계·추정 pose/size/불확실 범위로 추가한다. 센서 레이어는 metric return/원시각/등록 transform과 정체 미상 cluster를 보존한다. 시각적 primitive, 충돌체, synthetic keepout, localization에 사용할 구조를 구분한다.

| 상황 | 표시/결합 원칙 |
|---|---|
| RoomPlan에도 있고 사진에도 있는 소파 | 같은 대상 대응 검토, 새 소파를 중복 생성하지 않음 |
| 사진에만 있는 바구니 | 기존 카탈로그 형상 후보 생성, 위치 추정/불확실 영역 표시. 스캔이나 기준점으로 보완 |
| LiDAR에만 보이는 cluster | `unknown obstacle`로 차단·관측 보존. 사진 class를 자동 할당하지 않음 |
| 사진의 옷/전선이 LiDAR 평면 아래에 있음 | 위험/keepout 유지. 미검출은 부재·free 증거 아님 |
| 관측 시점이 다른 물체/사라짐 | 과거 사진과 현재 센서를 구분, 별도 검토 없이 삭제/현재 확정으로 덮지 않음 |
| 위치가 정확하지 않은 객체 | 보기용 추정과 주행용 차단을 분리. 임의 한 좌표가 정확한 obstacle인 것처럼 사용하지 않음 |

주행 범위는 “점이 모델에 맞았다”만으로 정하지 않는다. 등록이 검증된 구역 안에서 현재 로봇 footprint/여유, 높이별 충돌·얽힘 위험, 최신 관측·unknown과 중단 조건을 함께 반영해야 한다. 감지 가능한 평면에서의 free ray가 전 높이 부피의 통과 가능성을 증명하지 않는다.

Nav2의 static/obstacle/inflation 분리는 이 구조의 좋은 참고다. 그 자체가3D Twin 편집을 수행하는 것은 아니므로 semantic/geometry layer는 TwinPulse가 별도 관리해야 한다. [Nav2 obstacle layer](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/obstacle/).

### 8.6 구현 우선순위 제안 — 이번에는 아직 실행하지 않음

1. **Hybrid composition:** 원 environment + 기존 prop/keepout의 추가 레이어 계약. 원SHA/메시를 보존하고 안정 ID·출처/추정 상태·장면 revision을 결속한다. `site_tools/site_contracts/scene_changes`와 compiler/matches_environment를 함께 확장, collision·SIM/REAL navigation·저장/Undo/cold reopen까지 연결한다.
2. **정합 review:** 안정 구조의 후보와 clutter residual을 별도 표시. 기존 원검사 기준·실패 불변, 미검증 가구/keepout을 실측 scan surface로 넣지 않음. 명시 metric 대응점으로 시작한 좁은 데모를 대안으로 유지한다.
3. **기존 사진 경로 재사용:** 방을 새로 생성하지 않고 현재 USD를 고정한 채 누락 물체1–3개만 후보화. region을 예전 추정 방 좌표에 packing한 값을 그대로 RoomPlan에 이식하지 않는다. 사진→현재 장면 관계/좌표와 중복 객체 확인이 필요하다.
4. **COLMAP 조건부 파일럿:** 겹치며 이동한 원 영상/사진이 확보되면 sparse camera pose/metric alignment만 먼저 확인. dense 재구성을 선행하지 않고, 특정 데이터의 재투영/held-out 실패가 지속되면 주 데모를 종속시키지 않는다.
5. **TAP 계열 조건부:** 영상에서 정체/대응 유지가 실제 병목일 때 추가. 정적 방의 기본 정합 문제에 COLMAP과 점 추적을 모두 필수로 쌓지 않는다. 신규 weights/라이선스/자원 검증·사용자 설치/비용 경계는 별도다.

즉 이번 권장 순서는 **RoomPlan 골격 + 기존 사진 작은 물체 + LiDAR localization/obstacle layer**다. COLMAP/점 추적은 이 구조의 시각 위치 추정·대응 유지 부품으로 넣을 수 있으며, 기존 기능을 버리고 새 스캐너 하나로 해결하려는 접근이 아니다. 실제 제품 혼합/자동정합 성공으로 보고하지 않는다.

## 9. 영상 없이 진행한 혼합 장면 1차 구현 — v636

사용자가 현재 영상이 없으며 개발을 진행하라고 승인했다. 이번 구현은 위8.6의 **혼합 계약·제품 연결 기반**이다. 원USD를 고정한 사진 물체 자동 검출·세계 좌표 추정·실물 LiDAR 정합은 아직 완료하지 않았다. 수동으로 확인한 위치를 자동 복원 결과로 주장하지 않는다.

### 9.1 실제 구현

- `environment_source.py`/새 `environment_overlays.py`: 기존 static1.0을 그대로 읽고, static1.1은 원 필드+별도 `overlays`만 허용한다. 원source SHA/30mesh·축·selected_for_sim scale는 불변이다. 한 번에 원가구 한 개의 이동 또는 추가 물체 한 개의 add/move/remove만 허용하며 기존 추정의 class·크기·출처를 move로 덮지 못한다.
- 기존 `room_items`/버전고정 카탈로그의 floor_fan, basket, bag, box, clothing_pile, cable_bundle, power_adapter, power_strip, small_equipment, unknown을 재사용한다. 원 사진에서 이10개를 자동 검출했다는 뜻은 아니다. primitive 형태의 세부 한계도 유지한다.
- `EnvironmentImport`/새 `EnvironmentObstacles`: **Import space → Added obstacles**에서 선택적 로컬 사진, 이름/type, scene XY(지도 클릭 가능), 크기·yaw·uncertainty를 입력한다. `Preview obstacle` 뒤 기존 `Apply space edit`가 별도이며 자동 적용되지 않는다. 객체 목록으로 이동하고, `Remove … · preview`/`Undo last edit · preview`로 검토한다. UI는 영어다.
- 사진은 JPEG/PNG/WebP5MiB/24MP 이내 원바이트를 프로젝트의 environment-imports/overlay-photos/SHA에 보존하며 Preview/Apply/Build에서 무결성을 확인한다. **로컬 참조 + 사용자 placement**이므로 evidence=`photo_estimate`, alignment_verified=false, 관측시각 미제공은null이다. EXIF/색상/파일명으로 camera pose나 real-time 관측시각을 만들지 않는다. 이번 외부 모델 호출·사진 전송0이다.
- `environment_geometry.py`는 원mesh와 추가 catalog mesh를 함께 만든다. 가시 형상은 추정임을 색으로 구분하고, 별도 synthetic uncertainty/entanglement envelope는 숨겨진 physics collider다. `matches_environment`가 geometry/visibility/flag/evidence를 확인한다. 원mesh source path를 추가물체 source로 바꾸지 않는다.
- `twinpulse_fleet_runtime.py`/`environment_navigation.py`는 실제 stage의 추가형상과 **채워진** synthetic footprint를 경로/수동 guard에 포함한다. side surface만 막고 box내부를free로 두지 않는다. `lidar_scene_geometry.py`는 synthetic을 제외하고 가시 mesh를 실제 센서 높이로 slice한다. 높이 아래 케이블 미검출은 통과 가능 증거가 아니다. 물리 제어에 대한 새 권한은 없다.
- `scene_changes`/기존 `scene_edit_transaction`의 stable ID·비대상 digest·원revision·ACK·disk commit·current frame·Undo 재생을 재사용한다. 이번에 원 SitePlan2.4 single import call을 임의 procedural calls와 섞어 validator만 완화한 것이 아니다.

### 9.2 Astra 검토 및 데이터 호환성

Astra는 원본 source로 다음 두 경계를 검토했다(코드 수정·제품 인수 대신 읽기 전용 검토).

1. **구버전 호환성:** epoch1이 같아도 새 nested schema를 읽는다는 뜻은 아니다. 첫 새형식 transaction **STAGED 전** runtime-data marker1.1 + required capability를 원자 저장하고 실패하면 dispatch하지 않는다. 새 launcher/installer는 target capability를 검사하며 구 reader는 모르는 marker schema를 거절한다. journal이 남으므로 Undo 후도 sticky다. 원 project 변환/epoch2 migration은 하지 않는다. 기존 reader 함수를 원 release에서 실행한 거절 및 target contract 없는/구 contract install의 pointer 보존 거절을 확인했으며, **구 EXE 전체를 실제 기동한 시험과는 구분한다**.
2. **실제 발견·수정한 P2:** footprint/cell의 단순 바닥 면적합은 ‘왼쪽 절반 중복+오른쪽 공백’이 상쇄될 수 있었다. 양의 convex 교집합을 검사해 overlay는거절, navigation의 모호한 셀은occupied로 유지한다. 공유 triangle edge는 중복면적으로 처리하지 않는다. 원mesh를 변형하지 않았고 두 반례를 회귀에 넣었다. Astra 재검토에서 해당P2가 닫혔고 새P1/P2를 찾지 못했다는 한정 결론을 받았다.

### 9.3 실제 검증과 원문

설치: `20261024T082715Z-8d141e053179`, source manifest SHA `8d141e0531793699320a874d198eb0596e47239257cfd09f3c6abb6e13df06a7`, 1686exact.

|검증|확인 범위|
|---|---|
|집중 검사|Python66개(1조건부skip), React40개, 실제`tsc -b` 종료0. 기존 Import/제안/transaction/installer·저장scan 회귀 포함. 실제제품인수의 대체가 아님.|
|실제 OpenUSD Stage|원RoomPlan에서 가시바구니firsthit .824999952m≈.825m, synthetic 앞면.625m는반사점에안섞임. 낮은케이블은.182m평면에서원래벽반사그대로/경로occupied, synthetic flag변조거절.|
|일반 설치 UI fresh03|New chat→원USD/명시meters→검사/Import/Build→원사진참조바구니추정위치→add/move/Undo/remove/Undo5commit·ACK/durable/currentframe→SIM Burger등록/Connect/Prepare/라이다/단일90도완료·Stop/OFF/Disconnect.|
|실제 composed 센서|base_scan높이.182m, 로봇원점대비X−.032m 포함 전방반사점.857m=예상.857m. 축척/실제방측정정합 성공은아님.|
|Cold01|동일 project `chat_mvm5di1d_80ccf02a`의원source/사진SHA·overlay/현재revision/Undo이력재생, 명시Build·SIM재연결전Connect필요·확대현재모델/라이다 관측. 원Stop요청/ACK·새epoch engine관측, OFF scan=null, Disconnect.|
|화면·종료|1280×720/1024×768 가져오기패널 가로넘침0. 최종fresh/cold모두정상Exit·backend/engine roots자연0, Kit포함9개원문exact/optional liveness원문부재1·launcherlock0.|

UI01/02의 Manage 접근성 이름/접힌 registration란 선택자 오류는 원FAIL로 보존했다. 이를 잘라 이어붙여 성공으로 만들지 않고 fresh03 전체여정을 다시 실행했다. 초반 Python 모듈경로·코드구문, 테스트의 TypeScript옵션, USD SDK로드 초기화 오류도 도구출력/집중검사 원문에 보존했다. `tsc --noEmit`만으로 root references의 전체 type build를 확인하지 못했던 검수도 최종`tsc -b`로 보완했다. 이들을 실물 장치/엔진 실패로 집계하지 않는다.

최종 근거 gate: [acceptance01.json](../../outputs/environment-hybrid-20261024-01/acceptance01.json). [화면·정확수치·검수녹화](../../outputs/environment-hybrid-20261024-01/report.html)는 실제renderer 기록이며 native OS/실물 카메라·완성 제출 영상은 아니다. test 좌표의 사진참조 바구니를 실제 사진 위치 정합으로 홍보하지 않는다. 기존 실물 project와 원센서/사진/USD를 변경하지 않았다.

### 9.4 재현 및 다음 단계

현재 설치의 일반 시작을 사용해 저장 project를 열고 `Reopen saved scene` → `Import space` → `Show Twin`을 명시한다. `Added obstacles`에서 사진참조·추정 입력을 검토/적용한다. cold open이 센서/로봇권한을 복원해서는 안 되며 SIM을 선택 후 별도 Connect/Prepare한다. runtime marker1.1이 생긴 이후 **구버전으로 임의 rollback하지 않는다**. 원본/이력이 변환된 것은 아니지만 해당 capability를 읽는 release가 필요하다.

무구동 보조 재현: `.venv\Scripts\python.exe -B scripts/verify_environment_hybrid_20261024.py outputs/<새 폴더>`.
실제 설치 UI verifier: `node scripts/verify_environment_hybrid_ui_20261024.mjs fresh outputs/<새 폴더>`; 실제 Test entry/CDP window가 있어야 하며 새로운 테스트 project를 만든다. cold mode는 같은 fresh project ID를 전달한다. 검수용script이지 일반 제품 시작/직접 API우회가 아니다.

남은 우선순위는 **USD고정 사진누락물체1–3개 후보 자동제안 → 중복/관계/metric위치 검토 → 안정구조 LiDAR정합 후보와 독립held-out 검증 → 명시적Apply/재계획**이다. 이번 수동참조 연결을 자동융합 완료로 승격하지 않는다. 원POOR_FIT·실물몸체UNQUALIFIED·정합검증실패는그대로다. 영상이 확보되면 camera pose/대응 유지가 실제 병목인지 확인해 COLMAP/TAP 파일럿을 별도 판단한다. 이번 새 iOS/weights·SDK·유료GPU·실물연결·외부업로드·GitHub 작업은0이다.

## 10. 사진 누락후보 제안 구현 — v637, 실제 검출 인수 대기

새 `environment_photo.py` core/provider 모듈은 최대3개 `{id,kind,label,confidence,bbox,description}`와 설명만 허용한다. bbox는 normalized image 좌표이고 confidence는 인식신뢰도이지 metric정확도가 아니다. 모델의 치수/세계pose/tool명령은 거절한다. 원RoomPlan source/30mesh와 existing overlay1.1 계약은 그대로다. 카탈로그크기·위치는 추정으로 별도 검토한다.

`EnvironmentPhotoReview`는 원사진 SHA·source/input revision·job/response를 보존하고 `SinglePhotoScope`로 reserve-before-dispatch 1회를 강제한다. JPEG/PNG1장+추가prop이름/종류만 기존observer로 보낼 수 있다. planner/repair/자동retry/자동Apply/원USD·좌표·실물로그 전송은 없다. 같은 request의 중복 전송/GET/cold는 새 요청을 만들지 않는다. 결과가ready여도 Review→빈XY/중복확인→명시좌표/size→Preview→Apply가 별도다. Adoption receipt는 후보/모델/사진·response SHA/검토revision/operation·preview digest·overlay ID를 연결한다.

Astra의 세 경계는 실제 반례로 보완했다. 먼저 Cancel이면 Apply거절/먼저 Apply admission이면 Cancel거절, diagnostics finish/flush가 성공한 뒤 ready를 마지막 원자저장, Cancel 저장실패라도 현재 프로세스에서는 revoked로 기존preview/새reference를차단한다. **취소 저장 실패의 cold 지속성까지 보장한다고 말하지 않는다.** 원 실패와 비용/unknown 요청은 지우지 않는다.

첫 설치 UI01은 새chat→원USD Inspect/Import30→Build까지 통과했으나 사진 전송 전에 `Configured harness composition failed`로 실패했다. 새schema를 `ConfiguredStageTransport`에 연결했지만 `harness_profiles.SCHEMAS`에서 누락한 제품오류였다. 원project `chat_mvmbjpcn_d8ef3086`, job `8af6c78e3693861a64b25db6b8059b91`, usage requests0/response없음/외부사진전송0을 보존했다. observer/observation mapping과 실제configuredtransport+frozenbinding 회귀를추가, Astra 읽기검토를받았다. 최초실패를잘라PASS로만들지않고 추가1회승인답전호출0을유지한다.

수정설치 `20261024T113318Z-875966ed7575`/source `875966ed757526f0b8fbd64ccc558bc9bb8569131b52edcc82ae4bddc55a4c7a`/1690exact. Python109(1조건부skip)/UI42/tsc-b0은fakes포함보조검증이다. cold01은동일실패job을실패로복원하고사진POST없이명시Build했다. 성공후보의실제모델검출·Apply/currentframe/Undo·cold재열기는아직미인수다. 현재 UI/검수녹화는동일설치Electron renderer이며nativeOS/실물카메라·완성제출영상이아니다. [원실패·현재보고서](../../outputs/environment-photo-20261024-01/report.html).

이 기능만으로 자동 metric사진배치·LiDAR 정합/실물준비가완성되는것은아니다. 원POOR_FIT/.12기준·몸체UNQUALIFIED·센서/제어시간정책은그대로이며 실물연결/이동0이다. 다음은 실제후보1회검출/명시적용인수 후 안정구조 정합review·독립held-out 증거/사용자확정좌표를 연결하는 일이다.

## 11. 실제 모델 후보와 명시 적용·SIM 검증 — v638

추가10회 승인 중 실제 configured observer 1HTTP(2607tokens)를 사용했다. 동일 거실사진에서 선풍기/바구니/바닥가방 후보3개를 받았고, 바구니만 사용자 검토 경로의 빈XY·중복확인·카탈로그 추정치·Preview/Apply로 추가했다. 나머지9회는 사용하지 않았다. 자동 retry/repair/Apply는 없다. 원USD/30mesh, 사진/응답 SHA와 adoption receipt가 연결되며 4번 적용·3Undo의 exact engine ACK/저장/currentframe, 같은 job/response의 cold 복원을 확인했다. 위치[2.35,1.15]는 SIM 시험을 위해 고른 값이지 사진에서 metric 추론한 값이 아니다. 선풍기와 가방은 제안만 남겼다. 실제 자동 후보 검출 경로가 작동했다는 것과 인식률/전물체검출/정확위치 검증은 다르다.

### 11.1 발견한 실패와 최소 보완

- 원본 Storage2의 높이1.834–2.292m 구간 아래 옛 시험pose가 있어 위 카메라에 로봇이 가리거나 카메라가 형상 안에 들어간 경우를 남겼다. 원기하를 삭제/숨기지 않고 별도 가려지지 않는 시험pose[1.35,1.15,0]를 선택했다. `viewport_service.py`, `TwinViewport.tsx`, `twinpulse_live_viewport.py`에 Top view와 수직시점→Orbit의 finite oblique 방향 복귀를 연결했다. 기존 frame/stage freshness·로봇/센서 권한은 유지한다.
- 실제 cold05는 `site_scene_capability_missing`409로 Build 실패했다. 이 코드는 capability뿐 아니라 lease-dependent permitted command도 검사한다. `environment_workspace.py`에서 full 저장/input/history/photo 검증과 acknowledge를 같은 workflow lock 안의 lease획득 전으로 옮겼다. 원 단독 원인이 정확히 lease 만료였는지는 당시 timing binding이 없어 미확정이다. 3초lease·6초permit대기·currentidentity/assert/submit검사·REAL 보호는 바꾸지 않았다. 느린 검증 중 acquire0·변조시 acquire/submit0·identity변경/timeout submit0 반례를 확인했다.
- Astra가 sim04에서 이미 PAUSED였던 옛 snapshot을 새 Stop 완료로 저장한 검수누락을 찾았다. 원 sim04의 body/scan/90도/OFF 증거는 유지하되 새 Stop 적용은 미인수로 남겼다. 검수기에서 원Stop request/ACK가 준 새epoch와 같은robot/connection의 후행 appliedepoch를 기다린 뒤 OFF하도록 보완했다. 새 sim05 전체여정에서 `ddd8e9…→47f0ac…→applied47f0ac…`를 확인했다. 원 aggregate01 FAIL도 보존했다.
- 제 별도 SDK probe가 설치 resource imports에 bytecode를 써114개 pyc를 만들었고 다음 startup이 strict manifest로 정확히 차단됐다. 해당 오류 프로세스의 정상 dialog종료/소멸 확인 후, 원manifest에 없는 정확114개/2,390,858B만 SHA검증해 격리 이동했다(삭제0). 원source/manifest/사용자 프로젝트는 변경하지 않았다. probe의 `dont_write_bytecode`와 `-B`를 보완, 원a57/현재5ca 각1690exact 재검사했다. prelaunch 오류는 backend/engine 시작이나 실물 고장이 아니며 cold04의 준비 전 ECONNREFUSED도 검수 오류로 보존했다.

### 11.2 최종 확인 범위

현재 설치 `20261024T124901Z-5ca438e5d224`, sourceSHA `5ca438e5d2243673118c164bcd44298e480fdb5672bb6bc37d4fad71b72f7510`,1690exact, dataepoch1/static1.1불변. 최종 cold06/SIM05는 launch `74ee4076de7c4b87985bb7184c09c885`, 독립 cold07은 `84102675b70b41a29020cdbc994ede7b`이며 각 릴리스·종료archive를 정확히 결속했다. 이전 반복 횟수만으로 현재 설치를 PASS하지 않는다.

실제 화면에서 Burger body/wheel·이름 아래표시·호박색 바구니·cyan sensor ray/hit가 보이며 OFF 후 점/광선/active표시가 사라진다. 별도 Stage의 **같은 저자화/레이 알고리즘** 비교에서 height.182m/sensor[1.318,1.15,0]/전방 hit.857m/179반환점/최대차.0003994m를 확인했다. 독립 알고리즘·모든 missedray·광학/실물정밀도 증명은 아니다. synthetic keepout은 반사점으로 만들지 않는다.

최종 [gate02](../../outputs/environment-photo-live-20261024-01/acceptance02.json)는65/65 한정PASS. Python159(조건부skip1)/Web155/tsc0은 보조다. 원ui01/adopt04/sim05의 영상 전체decode·원PTS/DTS·시간길이·실제첫/중간/끝 픽셀을 확인했다. sim05는44.52초renderer검수 녹화이지 완성1분제출/OS커서/실물카메라 영상이 아니다. 초기 null출력의 sim02 DTS경고는 원timebase/passthrough재검수와 구분한다. 모든7개 ownedlaunch는 innercleanup완료/backend·engine root자연0 및 Kit포함 원문9개 exact동결이다. 선택적 engine-liveness 원본 부재1개는 copy-receipt에 별도로 유지한다. 원 cold05가 정상종료였어도 Build 실패는 실패 그대로다.

[실제 보고서·화면·영상·원 실패](../../outputs/environment-photo-live-20261024-01/report.html). 일반 App→같은project `chat_mvmcf9wa_18f1e6d1`→Reopen saved scene→Import space→Show Twin으로 검토하며 SIM 연결/Prepare는 별도 명시한다. 검수script는 `verify_environment_photo_ui_20261024.mjs`/`verify_environment_photo_sim_20261024.mjs`, gate는 `verify_environment_photo_live_20261024.py`다. 원 결과는 덮어쓰지 않고 새 output경로/판정명을 사용한다. SDK probe는 반드시 `python.bat -B`로 실행한다. 현재 source 문서/QA마감 수정과 설치manifest의 동결 payload SHA를 혼동하지 않는다.

다음 핵심은 안정구조 LiDAR정합 후보/독립held-out 검증과 사진후보의 실제위치 확인이다. 현재 구조에 실제 후보제안이 연결됐으므로 새 iPhone 앱/JSON을 먼저 개발해야 한다는 근거가 새로 생긴 것은 아니다. 원 authored단위 부재/POOR_FIT/.12기준·실물몸체UNQUALIFIED는 불변이다. 이번 실물접속/이동·새SDK/모델/iOS/유료/GitHub는0이며, 로봇만 켜면 최종 데모가 완성된다고 말하지 않는다.

## 12. 초기 pose 기반 구조벽 정합 review — v639

사용자가 승인한 최소 경로를 구현했다. `Import space → Scan alignment`에서 대략의 몸체 X/Y/yaw, 화면에 표시된 같은 벽 양끝 span의 기준 길이, 센서 높이를 명시한다. `SIM scale check only`는 원 선택 단위의 일관성 확인이지 실측이 아니다. 실물은 operator-reported reference가 필요하며, 길이 mismatch는 HELD로 두고 원 USD를 재조정하지 않는다. 한 span으로 모든 방 치수나 센서 extrinsic을 검증했다고 하지 않는다.

`environment_alignment.py`는 초기 pose·TF·원 ray 방향과 지도 가림 구조만으로 fit 이전 ROI/원 인덱스를 고정한다. train-only first-visible-wall range로 pose를 선택하고 별도 heldout과 후행 두 acquisition을 검사한다. missing/foreground occlusion은 분모에서 버리지 않는다. 최소12 validation returns·두 방향 normal 다양성·기존 .12m/.15m/.70 기준과 전체 원반환 잔차를 유지한다. 이후 소이동 추적은 초기 탐색보다 계산을 줄이되 원1초 freshness를 늘리지 않는다. 국소 경쟁해가 발견되면 AMBIGUOUS이고, 검색 창 밖의 정답이나 유일한 전역해를 보장하지 않는다.

`environment_alignment_review.py`/새 readonly `alignment-archive` 역할은 request/job/project/scene/source/원 acquisition·TF·입력 묶음 SHA를 보존한다. Cancel을 publish와 같은 lock에서 철회하고 초기 TF/sign/basis 변화를 거절한다. Hide→Show는 최신의 일치하는 packet을 유지하고 cold는 초기 immutable scan–pose 쌍을 Saved로 명시 표시한다. `twinpulse_alignment_view.py`의 별도 Physics=none ghost와 보라색 scan은 `/World/TwinPulse/AlignmentReview` 안에서만 존재한다. 기존 fleet의 `set_twin_pose`, navigation anchor, 모터/실물 제어를 호출하지 않는다. CURRENT OFF/단절/stale/owner·scene 변경이면 숨긴다. 명시적으로 연 Saved scan은 OFF 상태에서도 역사 자료로 표시할 수 있으며 current sensor와 구분한다.

초기 개발 probe에서 endpoint 최근접 비용은 정답과 약16cm 오답 모두 약.0474m였다. 같은 고정 원 ROI의 첫-hit 대조는 정답 .047390m/inlier.9053, 오답 .166537m/inlier.3263이었다. 원 저장 SIM/새 actual UI의 알려진 배치와 대조했으나 **동일 단면/ray 알고리즘·SIM ground truth이지 실물 정밀도나 독립 dataset 증명이 아니다**. 원 실물 frame715의 역사적 추정 seed[2.25,.95,0]·기록TF[0,0,0]·명시 기준 실측 없음은 새 방법으로도 HELD였다. 원 whole-scan POOR_FIT 및 몸체UNQUALIFIED는 그대로다.

최종 설치 `20261024T142218Z-24b97024f20a`/source `24b97024f20a428416b49673be78a8de73eea872eceb63228a5ea883052fc9d3`/1694exact·epoch1/static1.1 불변. 실제 `ui06`은 명시 메뉴 등록 `Aligned SIM 06`→Connect/Prepare/ON→초기[1.35,1.15,0] 정합→실제 몸체/점·광선→단일 Forward10cm 후[1.45,1.15,0] 추적→새StopACK epoch와 후행 engine 적용→OFF/Disconnect다. 이동 후 first-hit heldout .045482m/inlier.90909였다. `cold05`는 같은 job hidden/SAVED·실시간/연결 권한 미복구→명시 historical Show/Hide를 새 실행에서 확인했다. DOM current frame ID/시각과 같은 header·모델 envelope·실제 PNG를 결속했다. fast/360도 tracking은 이번 범위 밖이다.

원 ui01 snapshot 호출400, ui02 metadata-only recorder의 PASS를 PNG에서 거절한 aggregate01FAIL, ui03 표시 공백, ui04 카메라 과확대, ui05 옛job을 새 결과로 오인한 검수 race, cold04 Control view 선택 누락과 QA import 경로 오류는 모두 보존했다. 표시 UV만 반올림/최대32점·전체8000 budget내 optional 감축해 기존8192 원수신 제한을 유지한다. raw/fit/clock은 바꾸지 않았다. Astra가 네 lifecycle/TF/coverage P2와 Unicode header·검수기 frame 결속을 검토했고 보완했다.

[최종 gate02](../../outputs/environment-alignment-20261024-01/acceptance02.json) 45/45 한정PASS, 집중 Python123(조건부skip1)/Web158/tsc0 보조. 실제 최종 packaged readonly worker의 원receipt/segment 검증·첫3frame 추출도 확인했다. 모든7 ownedlaunch 정상Exit·root둘 자연0·innercleanup 및 Kit 포함 원문 exact동결. SIM 검수영상34.397초는 완성1분제출/OS커서/실물카메라 영상이 아니다. [보고서·실제 영상·원 실패](../../outputs/environment-alignment-20261024-01/report.html).

재현: 동일 일반 App에서 위 project를 열고 Reopen saved scene→Import space→Show Twin을 명시한다. SIM은 별도 명시 재연결/Prepare/ON, 새 Check에는 초기pose/기준 길이가 필요하다. 검수기는 `verify_environment_alignment_ui_20261024.mjs`, `verify_alignment_focused_20261024.py`, `verify_alignment_archive_frozen_20261024.py`, gate는 `verify_environment_alignment_acceptance_20261024.py`다. 기존 output을 덮지 않고 새 증거 경로를 사용한다. 이번 로봇접속/구동·LLM·새SDK/모델/iOS/유료/외부업로드/GitHub/삭제0. 다음 실물 단계는 기준 벽 길이/초기 위치·방향 확인과 정지3scan review이며, 사진 후보 metric 위치·센서 장애물 추가·몸체/제동/목표 주행은 남는다.
