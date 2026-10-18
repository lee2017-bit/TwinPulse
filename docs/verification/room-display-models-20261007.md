# 오른쪽 3D 표시 모델 분리 — 2026-10-07

## 요청과 범위

사용자는 왼쪽 경로용 bird's-eye의 단순화는 허용하지만 오른쪽 3D의 침대·옷장·옷걸이 등까지 네모 상자로 표현하는 것을 거부했다. 충돌 catalog를 다시 만드는 것이 아니라 **실제 Isaac 표시 경로에 식별 가능한 모델을 연결**하는 작업이다. 사진과 같은 특정 제품, 정확한 사진 복원, 실측 치수 또는 실물 자율주행 완료를 뜻하지 않는다.

## 구현

- `room-display-meshes-1.0`: 외부 다운로드·모델 생성 코드 실행 없이 제한된 로컬 mesh recipe를 사용한다. 기존 가구 7종/생활 물체 19종 모두 표시 recipe가 있다.
- 침대: 프레임·헤드보드·둥근 매트리스·베개·주름 mesh 이불/봉제선. 옷장: 분리된 벽판/선반·한쪽 문·손잡이·내부 봉/행거/옷. 행거: 목재 기둥/다리·원형 봉·행거·옷의 실루엣. 의자: 좌판·등판·팔걸이·중앙 지지대·5갈래 바퀴. 선풍기: 원형 그릴·방사형 와이어·날개·기둥/원형 받침. 바구니·가방/손잡이·케이블·모니터·블라인드·전원장치 등도 구별되는 형태와 재질이다.
- 표시 mesh는 `/World/TwinPulse/Presentation/RoomModels` 안에만 작성한다. Physics/Collision/Rigid/Articulation schema가 없고 `motionAuthorized=false`, `ILLUSTRATIVE_CATALOG_NOT_PHOTO_EXACT`로 기록한다.
- 원래 Environment 형상·좌표·collision API·keepout·catalog 버전·plan/scene serialization/hash·2D 경로는 그대로다. 대체된 proxy만 `purpose=guide`로 일반 렌더에서 숨긴다. 작은/얇은 물체의 장식 반경도 현재 표시 envelope 안으로 제한한다.
- 현재 저장 프로젝트와 검증된 scene-change sidecar의 **typed call**로 종류를 선택하고 현재 SceneRevision의 모든 member를 다시 검사한다. 원본 좌표를 무조건 다시 그리지 않는다. 그룹 이동/회전/상하 이동은 현재 pose를 따른다. 부분 누락·비균일 직접 수정·dynamic 변경은 detailed overlay를 버리고 현재 proxy를 남긴다. 정식 typed 크기/종류 변경·Add/Undo는 유효한 sidecar plan을 사용한다.
- 일반 Build와 SIM/REAL visual Build의 기존 adapter 경로에 연결했다. 표시 실패는 이전 owned scene/receipt를 복원하며 과거 실행 권한은 복원하지 않는다. engine host는 실제 room-display marker/group/kind/mesh/physics-schema 수를 기록한다.

## 검증 근거

1. Python **43 tests PASS**: 새 표시 6개(26종, 제한/유효성, 작은/얇은 envelope, hash 보존, 현재 이동/회전/상하 pose, 누락/부분변경 fallback) + 기존 room items/scene edits/manual-room generation/site SIM/site furniture 회귀. 겹치는 작은 실행을 합산하지 않았다.
2. 실제 이전 LLM 생성의 저장 결과를 **새 호출 없이** 읽어 현재 adapter Build를 실행했다. `artifacts/room-visuals-20261007/isaac-r7/result.json`: **PASS, 24 groups / 445 meshes**, plan `437c176871c1edef5e121e566a40ba589ddfd798e04f87a38c6ab36259312f19`, scene `5e54ff6a7c735f15f641fd4c4d14b614e250260d46eeb3c878c3249a7ab742de`. 원래 저장 프로젝트 hash 불변.
3. 실제 PhysX 공 낙하 비교: 원래 proxy/default 렌더와 detailed 모델/guide proxy 모두 매트리스 접촉 후 z=**0.5m**. 원래 충돌/속성 graph, external prim, scene identity 불변; overlay에 physics schema0.
4. 동일 Build/표시 idempotence, 표시 작성 중 오류 복원, 새로운 geometry Build 후 표시 실패의 이전 전체 graph/receipt 복원, USD export/reopen, 직접 단일 크기 변경 시 stale detailed 모델 제거, 기존 sidecar typed Add→Undo의 현재 표시 생성/제거를 actual Isaac에서 확인했다.
5. 실제 사진-plan 3D screenshots는 `isaac-r7/room-overview.png`, `furniture-detail.png`, `wardrobe-rack-detail.png`다. **가구를 보기 위한 진단 cutaway에서 벽을 숨겼으며 사진 배치나 collision을 수정한 결과가 아니다.** 이미지 합성 또는 AI 생성 그림이 아니다.
6. 실제 Chrome/chat→App/API/Bridge→Isaac bed/desk 생성·Run·Stop·reload/reset 인수 `chat-bedroom-r1/result.json` PASS, 실제 display2 groups/19 meshes/physics-schema0, viewport103 frames, owned supervisor stopped. 모델 답변은 명시 fixture이므로 새 LLM 품질 평가가 아니다.
7. `chat-clutter-r1`의 실제3D19 groups/369 meshes/physics-schema0·viewport221 frames는 확인됐으나 전체 browser 인수는 접힌 inventory를 열지 않고 클릭해 timeout이었다. 기존 제품 UI를 바꾸지 않고 검증기가 사용자처럼 바깥 details부터 여는 것으로 수정했다. 최종 `chat-clutter-r2/result.json`의 실제 Chrome/chat/App/API/Isaac 생성·Run·Stop·reload/reset 전체 인수 **PASS**:19 groups/369 meshes/physics-schema0, viewport104 frames/dropped0/error없음, owned supervisor stopped. 명시 fixture 답변/새 photo inference NOT_RUN, provider·로봇0. r1 FAIL은 보존한다.

실행 명령:

```powershell
python -m unittest tests.integration.test_room_visuals tests.integration.test_room_items tests.integration.test_scene_changes tests.integration.test_manual_room_creation tests.integration.test_site_simulation tests.integration.test_site_furniture_generation -q
C:\isaacsim\python.bat scripts\verify_room_visuals_isaac.py artifacts\agent-reliability-20261007\photo-output10000-chat-isaac-r1 artifacts\room-visuals-20261007\isaac-r7
python scripts\verify_chat_sim_journey.py artifacts\room-visuals-20261007\chat-clutter-r2 --case text --layout cluttered_room
```

위 output은 이미 생성된 기록이다. 재실행에는 새로운 격리 output 경로를 사용한다. ISAAC bat의 프로세스 exit code만으로 PASS를 판정하지 않고 result/checks를 확인한다.

## 이전 실패와 제한

- 초기 구문/인자 오류는 unit 단계에서 수정했다. sandbox의 임시 잠금파일 권한 실패는 승인된 로컬 테스트 실행으로 재검사했다. 시스템 설치/ACL 변경이나 거부 우회는 없다.
- `isaac-r1`은 실패 복원 시 원래 없던 `purpose` opinion을 남기는 결함을 발견했고 authored-property 여부까지 보존하도록 수정했다. r2/r3 표시/접촉 통과 기록과 실패 기록 모두 보존한다.
- 확장 검증 r4/r5의 byte-string 비교는 기존 safe PhysicsScene 보존으로 바뀌는 **형제 출력 순서**를 실패로 판정했다. r5 diff를 보존하고, r7에서는 모든 prim/속성/schema/custom data/관계/children의 graph 동일성으로 검사했다. 물리 Scene을 제거하여 출력 순서를 맞추지 않는다.
- r6은 긴 렌더 검사 후 예전 CommandEnvelope를 복사해 Add 검사 명령 TTL30s가 만료됐다. 테스트 명령마다 새 issued time을 사용하도록 고쳤고 **제품 TTL은 그대로**다. r7 Add/Undo까지 PASS.
- 모델/catalog 외형은 이제 구별되지만 **기존 사진 후보의 옷장 위치·방향, 떨어진 옷/침구의 부착, 블라인드/케이블 배치 오류는 남아 있다**. 이번 작업은 원래 후보를 보기 좋게 표현했을 뿐 해당 오류를 숨겨서 정합 PASS로 만들지 않았다. 사진 척도/실측/일반 사진 생성 안정성/실물 연결도 미검증이다.
- 새 provider/로봇/SSH/센서/모터/배포/설치/commit/push/agent0. 승인 ledger109/219·남은110·pending0은 그대로이고 비용 추가0. 원본/과거FAIL/raw/dirty/v1-v2/hash/안전guard/예약PAUSED 보존. **Whole demo readiness=false**.

## 다음

1. 사용자 외형 리뷰 후 필요하면 catalog의 세부 형태/재질 개선. 특정 제품 수준의 asset이나 photoreal reconstruction은 별도 범위다.
2. 사진의 방향·붙어 있는 물체·벽/천장/가구 지지 의미를 먼저 바로잡고, 그 뒤 별도 제한된 실제 LLM 평가. 시각적 mesh 품질과 배치 정밀도를 다른 acceptance로 유지한다.
3. 기존 App/Isaac 재실행 후 저장된 방을 다시 Build하면 새 표시 renderer를 쓴다. 이미 실행 중인 옛 Isaac Python 모듈은 웹 새로고침만으로 교체되지 않는다.
