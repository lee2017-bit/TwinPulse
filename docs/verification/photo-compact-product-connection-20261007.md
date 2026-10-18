# 사진 compact 계약의 실제 제품 연결 — 2026-10-07 / v319

## 결론과 경계

`photo-layout-1.1`의 선택 경로를 기존 App composition/host backend에 연결했고, **명시적인 고정 모델 응답으로 실제 Chrome→chat/API→Site2.2 저장/등록→Isaac 3D→Physics Run/도착→자연어 목표/Stop→접기/새로고침/reset→프로세스 종료 후 저장 재열기 PASS**다. 모델/Isaac 모두 가짜인 시험이 아니다: **모델 응답만 고정이며 Isaac/PhysX는 실제 로컬 runtime**이다.

실제 P01 원본 사진을 로컬 업로드하여 기존 검토24개를 적용했지만, 시험 배치는 명시적인 **8×8m 임의 regional fixture**다. 실제 방 치수/사진 배치·지지/부착을 복원한 결과가 아니다. `photo_inference=NOT_RUN`, `production_default=false`, `physical_validation=NOT_RUN`, whole_demo_ready=false. H5/H6/C3–C6 PARTIAL 유지.

이전 최대3회 모델 호출 승인은 모두 사용된 상태다. 다음 최대3회 실제 Gemma/Nemotron 검사에 대한 별도 답변을 요청했으며 **이번 증분에는 외부 호출0**이다. 기존 사진 실패/원본/dirty/guard/직렬화 보존, 로봇 접속/배포/센서/모터/설치/commit/push0. 기존 예약 PAUSED 유지.

## 실제 연결에서 발견·수정한 결함

1. 첫 `compact-chat-isaac-contract-r1`은 **FAIL**: `scene revision digest mismatch`. 소품 geometry가 정수 yaw `0`을 그대로 보유하고, 저장/등록 reader는 float `0.0`으로 복원하여 revision이 달라졌다. 기존 순수 compiler 시험의 성공만으로 실제 등록 성공을 주장할 수 없었던 결함이다.
2. `expand_room_item`이 검증된 numeric vector/yaw를 geometry 생성 전에 float로 일관되게 받게 수정했다. **입력/tool-plan bytes, canonical_sha256 알고리즘, SceneRevision digest 대조, SiteDraftRecord schema2.0은 변경하지 않았다.** 기존 정상 float geometry는 같고 정수 geometry도 새 생성부터 안정적으로 roundtrip한다. 옛 실패 기록을 다시 쓰거나 해시 검사를 생략하는 migration은 없다.
3. 첫 실패의 미생성 stage에서 종료 보고가 `NoneType.GetPrimAtPath`로 추가 실패했다. 실제 host의 `_mission_visual_marker`가 stage/prim 부재를 처리하게 하고 로컬 회귀로 None/없는 prim/정상 marker를 확인했다. 이를 생성 성공이나 준비 완료로 바꾸지 않는다.
4. `build_live_generation_service(..., compact_photo_layout=True)`와 backend `--experimental-compact-photo`를 추가했다. 기본 False, Nebius Site2.2에만 허용. backend는 명시 live campaign이 필수이며 fixture/offline/replay 혼합을 실행 전 거절한다. 브라우저가 이 정책이나 campaign을 바꿀 수 없다. 허용된 기존 generation_settings의 `request_schema=photo-layout-1.1`에 opt-in을 결속하고, 일반 설정은 유지한다.
5. 기존 journey runner에 `--compact-photo`를 연결했다. 실제 생성 검사에서는 **동일 backend 옵션을 전달**하고, 고정 응답 시험에서는 별도 `--site-transport-fixture`를 명시한다. 모델 응답 임의 교체를 일반 런처 기본값으로 넣지 않았다. 사진 compiler/core/composition source hash를 실행 전후 대조한다.

## 최종 검증

- provider 전체 **57 / 1.158s PASS**, 로컬 transport.
- core 전체 **300 / 32.249s PASS**, 기존 hash/serialization/geometry/mission 포함.
- 관련 통합 **97 / 28.742s PASS**: 채팅, 소품 정수 roundtrip19종/변조 해시 거절, 파생 scene/저장, host opt-in 경계, unbuilt host 종료, reliability/observer reuse. imported suite 중복이 있으므로 고유 시험 수 합계로 주장하지 않는다.
- 별도 host 경계4 /2.997s는 위 통합에도 포함된다.
- 최초 sandbox 로컬 API 회귀는 Windows Temp 파일 권한으로 실패했다. 일반 로컬 테스트 실행 권한을 정식 요청·허용받아 같은 suite48/23.218s 및 최종 통합97을 실행했다. 이는 제품/API 또는 모델 실패가 아니며 권한 거부 우회/시스템 설정 변경은 없다.
- 최종 실제 runtime **`artifacts/agent-reliability-20261007/compact-chat-isaac-contract-r3/result.json` PASS**. r1 FAIL/r2 PASS는 보존한다.
  - 사진 업로드 후 Q1 하나에서 기다림; 답변 전 생성/Build/Run0.
  - 고정1.1 관측/intent→기존 compiler/executor→24개 검토 항목 모두 저장·표시, missing0. geometry UNMEASURED/실물 NOT_RUN.
  - 실제 Isaac Build1, 현재 render109 frame/125 prim, viewport error 없음.
  - 명시 Run1의 실제 PhysX 도착 거리 **0.0396904184m ≤0.04m**, sim4.1s. 다음 채팅 목표 Run 후 접힌 화면에서 채팅 Stop→pause, 위치 유지.
  - 새로고침 후 Build/Run 재실행0·승인 자동복원0. 명시 reset은 비물리 preview와 telemetry unavailable 상태로 복구.
  - 실제 backend 종료 후 **ProjectStore.load()**로 파일을 재열어 같은 plan/input/scene 해시와24개 전부 재검증. 브라우저 reload의 서버 메모리만 확인한 것이 아니다.
  - 최종 operation: build_site_scene/run/run/pause/reset 모두 succeeded; page errors0; inference source unchanged=true; 테스트 소유 backend/engine owned=false로 정리.
- Web 제품 source/build는 변경하지 않았다. 기존 built UI를 실제 브라우저로 사용했으며 이번에 Web unit/build 전체를 새로 실행했다고 주장하지 않는다.
- git diff --check PASS.

저장 plan SHA256 `365531a6537485253a6349013767daee8da778f22590b0656482a2743fe31d5d`, scene revision `ad77bce1e13bacf5a03f2efb8fec137e41612e637808afc30abed9367951dc8b`. 실행 결과에는 전체 현재 source/build hashes가 있다. 사진 계약 원본은 변경하지 않았고 `photo_layout.py` SHA는 v318과 동일하다.

## 재현 경로와 다음 작업

비용 없는 실제 제품 연결 시험:

```text
python scripts/verify_chat_sim_journey.py <새 output> --case image --site-transport-fixture --compact-photo --live-photo <P01 원본 사진>
```

후속 실제 모델 검사는 별도 승인된 제한 안에서 `--site-transport-fixture` 대신 `--live-campaign <기존 campaign.json>`을 사용한다. 새 ledger 생성/초기화나 자동 API retry는 하지 않는다. 한 번의 사진 생성은 관측1·계획1·공유 semantic repair 최대1이며, timeout/identity/auth/transport 실패를 자동 재요청하지 않는다. 구동 전에 이 작업의 추가 호출 승인과 기존 가격/예산을 확인한다.

1. 아직 미검증인 **1.1 실제 API schema 수용·24개 모델 출력·배치 검증→같은 actual chat/Isaac 인수**가 다음이다. 실패 원본/원인을 그대로 남기며 고정 응답 인수로 대체하지 않는다.
2. 실제 방처럼 보이게 하는 **지지/부착·크기/방 배치 충실도**는 별도 미완료다. 8×8 fixture 통과가 원본 방 복원/주행 가능성의 근거가 아니다.
3. 검증 뒤 일반 런처 정책 채택을 판단한다. 현재 **기본 제품 사진 경로가 자동으로 compact로 바뀐 것은 아니다**. 광범위 matrix·실측/정합·현장 driver/정지·실물 임무는 독립 잔여다.

공유 campaign은 **51/60**, 알려진 usage+unknown 전체 예약 **USD0.09513896** 그대로이며 실제 청구는 미확인이다. 새 모델 호출/dispatch/잠금0, 이전 unknown2 및 실패 유지. 남은 총9회는 후속 묶음의 사용자 승인과 동일한 의미가 아니다.
