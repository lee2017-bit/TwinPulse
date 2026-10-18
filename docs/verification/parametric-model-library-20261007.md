# 재사용 가정집·창고 모델 라이브러리 — 2026-10-07

## 요청과 완료 범위

한 방 전용 고정 mesh가 아니라 다른 집/방/창고에서도 LLM이 모델을 선택하고 폭·깊이·높이를 조정하는 라이브러리를 구현했다. 외부 asset 다운로드, 임의 생성 코드 실행, 실측 또는 사진과 동일한 제품 복원을 의미하지 않는다.

| 그룹 | 현재 지원 | 조절 방식 |
|---|---|---|
| home | 침대·옷장·소파·식탁 및 가정용 생활 물체 | 가구는 새 parametric catalog, 생활 물체는 기존 dimensions recipe |
| common | 책상·의자·수납장 및 공용 물체 | 같은 model_id를 가정집/창고가 공유 |
| warehouse | 랙·팔레트 적재물 | 기존 create_rack_row/place_pallet_stack의 크기·bay·level 조절 |

중복 제거한 등록 항목은 **28종 = 가구7 + 생활 물체19 + 창고2**다. 가구7만 3가지 형태 선택과 natural/white/dark 마감을 지원한다. 생활 물체19의 여러 형태/마감을 새로 구현했다고 하지 않는다.

## 실제 제품 연결

- Core `model_library.py`: 안정적인 model_id, family/environment tags, 기본 xyz·종류별 범위·형태·마감·기존 도구 metadata. 명시 혼합 환경/비전형 물체는 배제하지 않는다. 환경 검색은 bounded 키워드 기반 선택지 검색이며 사진 이해 자체가 아니다.
- `furniture-parametric-1.0`: dimensions_m=[width_x,depth_y,height_z], variant, finish가 필수. XY footprint 중심·바닥 z0·local front=-Y/+Z yaw. 전체 모델을 치수에 맞춰 재조립한다. 판 두께25mm/탁상60mm/탁자 다리55mm 등은 절대 단위로 유지하여 단순 mesh 전체 비등방 scaling을 피했다. 형태에 따라 베개 수/옷장 문/소파 쿠션/의자 형태가 실제 바뀐다.
- 표시와 충돌은 분리하되 새 크기를 둘 다 반영한다. 열린 옷장의 내부 통과를 허용하지 않는 보수적 collision, 바닥 경계/다른 물체 겹침/유한값/종류별 치수/allowlist 검사를 유지한다. 잘못된 치수를 조용히 clamp하지 않는다.
- 표준 Site2.2 생성의 기존 Nemotron planner prompt에 환경별 manifest·치수/형태 규칙과 strict schema를 연결했다. 기존 provider/service/단일 repair/검증 도구 경로를 쓰며 임의 Python/새 coding agent는 없다. JSON의 model_id는 검색용이고 실제 호출은 각 항목의 기존 typed tool을 사용한다.
- 기존 저장 장면 수정 provider의 context/schema/preview/apply에도 동일 옵션을 연결했다. 가구 id/kind를 보존하며 옛 고정 catalog에서 새 catalog로 **명시 업그레이드**, 전체 가구 크기 변경과 Undo를 지원한다. 기존 저장 원본은 수정 sidecar와 분리되어 보존된다.
- 인증된 read-only `/v1/product/model-library` 및 기존 영문 편집 상세의 `Adjustable library model`, Width/Depth/Height, Variant/Finish를 연결했다. 새로운 주 화면 질문/승인 버튼을 우르르 추가하지 않았다.
- 현재 project+검증된 sidecar+현재 geometry가 Isaac display를 결정한다. 가구/공용/창고 model_id·dimensions·variant/finish를 USD에 기록하며 표시 mesh에는 physics API/이동 권한이 없다. 낡은 geometry에 새 외형을 덮어쓰지 않는다.

## 호환성과 별도 미완료

`furniture-blocks-1.0`의 옛 치수·arguments·직렬화·hash 의미는 변경하지 않았다. v1/v2.0 golden과 v2.1 고정 가구 schema가 통과했다. 새 catalog는 Site2.2에서 명시 선택한다. 옛 저장본을 다시 열었다고 새 치수로 자동 변환하지 않는다.

**실험용 compact-photo 1.0/1.1 compiler는 계속 옛 고정 가구 catalog를 생성한다.** 이번에 기존 real-photo 원본/승인 후보를 소급 재해석하지 않았다. 표준 Site2.2 생성·수정은 새 옵션을 받지만, compact-photo 자체의 치수 선택 형식 변경/실제 모델 평가/기본 정책 채택은 별도 남는다. 현재 사진의 잘못된 옷장 위치/방향, 의복·침구 부착, 블라인드/케이블, 실측 치수 문제를 이 변경의 완료로 표시하지 않는다.

## 검증 결과

1. 최종 관련 Python **62 PASS / 6.878s**. 새 라이브러리8 tests: 인증/read-only, family/shared identity, 가구 모든 형태·마감×4 치수 조합의 collision/mesh bounds, 절대 두께, office 마감 변화, 불법치수 거절, planner manifest/schema/service, legacy→resize→serialize/reopen→Undo, 기존 랙/팔레트 factory 바인딩. 기존 관련 편집/room/fixture/golden 포함.
2. 전체 Core **302 PASS / 26.772s**, Provider **104 PASS / 2.948s**. 위 62와 중복 포함; 별도 LLM 성공률 분모가 아니다.
3. TypeScript 검사, 전체 Web **342 PASS / 43 files / 30.56s**, production build/manifest PASS. 편집 UI12에는 메타데이터 읽기·명시 업그레이드·치수/형태/마감 preview 호출 검사가 있다. bundle>500kB 경고는 보존했다.
4. `artifacts/model-library-20261007/isaac-r7/result.json` **실제 Isaac PASS**: 가정집7 groups/61 meshes, 창고2 groups/22 meshes, current source-bound adapter Build, physics0, USD export/reopen. 침대1.6×2.2×1.0/double/natural→0.9×1.9×0.75/single/white를 실제 저장 sidecar와 동일 adapter로 재빌드; 베개1개/치수·마감 metadata/원본 bytes 보존. 최종 캡처 평균 RGB153.50→153.35, 창고151.48; 어둡거나 과노출인 frame을 새 최종 gate에서 거절한다. 카메라 exposure API 보존 검사 포함.
5. `chat-library-r2/result.json` **실제 Chrome→chat→API→표준 Site2.2 provider→저장→Isaac Build→PhysX Run/도착→chat Stop/fold/reload/reset→backend 종료 후 ProjectStore 재열기 PASS**. 실제90 viewport frames, 목표 거리0.0396627657m, 표시2 groups/12 meshes/physics0, page errors0, 소유 backend/engine 종료. 새 parametric 침대1.5×2.0×0.9/double/white·책상1.1×0.6×0.74/metal/white 저장 계약 확인. **전송 응답은 명시 fixture, 외부 모델 품질/신뢰성 평가 아님.**
6. 최종 `legacy-room-r1/result.json` **실제 과거 LLM 저장방24 groups/445 meshes 회귀 PASS**. 같은 원본/scene/plan hash 보존, collision attrs 불변, 원래/guide proxy PhysX 접촉 z=.5/.5, post-authoring 실패 overlay복원·새 geometry/display 실패 전체 owned graph/receipt복원, 외부 prim 보존, stale 부분수정 collider fallback, typed Add→Undo, USD 재열기 모두 확인했다. 과거 사진 정합 결함을 고쳤다는 결과가 아니다.

### 실제 화면

합성 치수로 구성한 재사용 모델 모음이며 사용자 방을 복원한 사진이 아니다. 모두 actual Isaac viewport 캡처다.

![Home library](C:/Users/jaewo/Documents/TwinPulse/artifacts/model-library-20261007/isaac-r7/home-models.png)

![Resized single bed](C:/Users/jaewo/Documents/TwinPulse/artifacts/model-library-20261007/isaac-r7/home-resized-single-bed.png)

![Warehouse library](C:/Users/jaewo/Documents/TwinPulse/artifacts/model-library-20261007/isaac-r7/warehouse-models.png)

![Actual chat and Isaac](C:/Users/jaewo/Documents/TwinPulse/artifacts/model-library-20261007/chat-library-r2/generated-ready.png)

### 보존된 실패와 수정

- 초기 sandbox temp cleanup/웹 child-spawn 차단은 기존 허용 도구를 승인된 권한으로 재실행했으며 ACL 변경·권한 우회·설치가 없다.
- 테스트의 존재하지 않는 server.close/두 잘못된 unittest 모듈 이름을 수정했다. 최종 존재하는 모듈로62 PASS; 이전 잘못된 실행을 PASS로 합산하지 않는다.
- Isaac r1은 app.close가 프로세스를 끝내 결과를 못 남겼다. 결과를 종료 전에 저장하는 것으로 수정했다. r2 FAIL은 검증 입력의 잘못된 generation setting key로, 기존 non-secret allowlist를 완화하지 않았다.
- r3/r4는 USD/치수 검사는 통과했으나 **재빌드 캡처 과노출**이 발견되어 최종 표시 인수로 사용하지 않는다. 추가 렌더 대기로도 해결되지 않았다. r5 조명0/복원 진단과 r6 변경 후 비교를 보존했다.
- 원인은 이 경로에서 활성 presentation camera/light를 같은 path로 삭제·재생성하는 동작과 연결됐다. 기존 physics-preserving 교체 중 카메라/조명 prim은 유지하고 이전 scene overlay만 제거·카메라 pose/조명을 갱신했다. 원본 collision/PhysicsScene/시스템 renderer 설정은 바꾸지 않았다. 최종 r7 실제 재빌드 렌더와 r2 제품 생성/Run/Stop/reset 화면으로 확인했다.

## 다시 실행 및 현재 경계

```powershell
C:\isaacsim\python.bat scripts\verify_model_library_isaac.py artifacts\model-library-20261007\new-owned-run
python scripts\verify_chat_sim_journey.py artifacts\model-library-20261007\new-owned-chat --case text --layout bedroom --site-transport-fixture --library-models
```

출력은 존재하지 않는 새 디렉터리여야 한다. fixture는 실행 옵션에 명시되며 제품의 live provider를 몰래 대체하지 않는다. 기존 App/Isaac을 재실행하고 저장 장면을 다시 Build해야 새 Python renderer가 적용된다.

이번 새 외부 LLM/유료 호출·로봇/SSH·설치/배포·commit/push·새 agent는0. 이전109/219·남은110·pending0 이력과 과거 실패/dirty/raw/정지 기준은 보존한다. **전체 사진 복원/실측/실물 자율 임무/전체 데모 준비 완료는 아니며 whole=false.** 다음 평가는 새 library 출력의 실제 LLM 선택·수정 성공과 사진 부착/배치 정합을 별도로 구분한다.
