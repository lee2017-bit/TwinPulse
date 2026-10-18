# G0–G6: 기하 진단·자동 회복·동일 결과의 App/Isaac 인수

2026-10-09–10 KST · Baseline v1.0.381 근거 · 전체 제품 PARTIAL / whole=false 유지.

## 결과 구분

- 원 v379 자연 생성 FAIL은 변경하지 않았다. 당시 10물체 후보의 벽 높이 오류를 현재 코드에서 다시 검사했다.
- 새 실제 Nano 요청 **1회**가 같은 후보의 블라인드 중심 높이를 **2.2→2.0m**로 수정했다. 방 치수·블라인드 크기·나머지 9물체·관측 출처는 그대로다. 전체 compiler PASS.
- 초기 관측/설계/객체 4개 응답은 저장 자료 재생이다. 새 사진 분석이나 새 자연 생성의 성공 표본으로 세지 않는다. 인위적으로 오류를 넣은 시험도 아니다.
- 기존 8회와 새 1회를 합해 **9/10**, 미사용 1, 추정 비용 USD0.01247277. 추가 요청 비용 USD0.00085554, 3.89초, 입력 13315/출력 236 tokens, finish=stop. 청구서 검증 아님. UNKNOWN/lock 0, 새 사진 전송/로봇 명령 0.
- 같은 실제 수락 결과를 명시적 zero-network replay로 일반 App/API/저장/실제 Isaac에 전달한다. 엔진 시험에서 다른 샘플 장면으로 바꾸거나 JSON을 수동 수정하지 않는다. 새 자연 생성 인수와 구분한다.

## 수정한 실제 제품 경로

1. `core/geometry_diagnostics.py`: provider를 import하지 않는 typed 진단. 안정적인 issue ID, code/path/target/related IDs, 실제 값, 동적으로 계산한 조건/단위, 수치 위반량, blocked 검사, repairable을 전달한다. 여러 독립 관계 오류를 함께 수집한다.
2. `photo_layout.py`/`photo_placement.py`: 모델·바닥·벽·천장·부모/part/anchor·순환·지지·배치 오류 연결. 지지 실패는 부모 없음/지지면 없음/용량 초과/파생 형상 실패로 구분한다. 형제 충돌과 종속 검사도 기록한다. 원 인간-readable 오류의 호환성을 유지한다.
3. `semantic_scene.py`: compiler 1.2. 문자열-only 알려진 오류를 semantic ID에 결속하고 미매핑 내부 오류는 UNMAPPED_COMPILER_ERROR/repairable=false로 분리한다. 같은 ID의 차기 revision 수정은 허용한다. summary/목록 순서/동일 값만 바뀌면 SEMANTIC_PATCH_NO_CHANGE. helper도 request/evidence_ref 계약을 사용한다.
4. `budgeted_pipeline.py`/`generation_policy.py`: 진단→수정 요청→원응답/적용 후보→전체 검사→실행 증거를 연결한다. patch 형식/실제 변화/최종 검사 상태를 분리한다. 수치 부분 개선, 악화 rollback, A→B→A 비진전, 이전 blocked 검사에서 새로 드러난 오류의 구분을 회귀로 확인했다. best candidate와 진단을 checkpoint에 저장한다. 전체 수락 전 App 장면을 게시하지 않는다.
5. App/React: 기존 접힌 Tool details에서 각 시도의 patch 형식/변화/전체 검사 상태와 대상·실제 값·경계를 읽을 수 있다. 공개 API는 allowlist/유한 숫자만 노출한다. 자동 수정별 버튼·추가 승인 카드를 만들지 않았다. 기존 단일 질문·Cancel/Stop·실물 잠금은 유지한다. 실제 엔진 인수 중 발견한 flat semantic compiler provenance의 관계 sidecar 누락도 일반 Application 경로에서 수정했다. 기존 nested `photo_layout_compiler`와 새 flat trace를 같은 core 계약으로 검사·2.1 저장하고 재열기한다.

직접 진단의 wall 상한 2.15는 `room.height_m − object.height_m/2`에서 계산했다. 다른 이름/치수/방 높이의 회귀를 포함하며 제품에 window_blind_1/침실 사진 hash/2.15 정답 분기를 추가하지 않았다. 원본의 고정 데이터는 명시 재현 테스트에서만 사용한다.

### 구현 경계 / 계획의 아직 미완료 부분

- 의존 범위는 매 revision의 target/parent/child/같은 지지면 sibling으로 계산해 요청한다. **New 장면의 최종 typed patch는 정상 물체를 영구 잠그지 않으며 전체 재검사로 수락한다.** graph 밖 변경을 별도 typed 제안→host 승인→후속 context 확대하는 wire 프로토콜은 아직 별도로 구현하지 않았다. Add/Change의 기존 사용자 변경 승인·preview/commit 경계는 유지하지만 이번 시험으로 모든 범위 확대 사례를 인수했다고 주장하지 않는다.
- 수치 진전은 `violation_m`이 제공되는 검사에 적용한다. 복잡한 다물체 packing 전체의 연속 위반 점수, 비교 불가능한 여러 후보의 장기 탐색, 재개 간 tracker 전체 상태 복원은 이번 완료 범위가 아니다. 유효한 부분 개선·회귀/무변화는 현재 루프에서 검사했다.
- 원 관측/품질/명시 치수/독립적으로 가능한 검사만 PASS. 파싱·부모 실패로 실행 불가한 종속 검사와 아직 없는 렌더 critic을 검사 성공처럼 표시하지 않는다.

## 오프라인 검증

| 실행 | 결과 | 범위 / 비고 |
| --- | --- | --- |
| Core 전체 unittest | 302 PASS | 명시 PYTHONPATH, 실제 Isaac 시험과 분리 |
| Provider 전체 unittest | 266 PASS | 기존 252 + 신규 기하 14; 최종 전체 재실행 |
| 관련 App 통합 4 modules | 최종 256 PASS | generation_approval/chat_conversation/execution_diagnostics/chat_site_text_generation; flat 저장 회귀 1 포함, 142.434초 |
| 최종 관계 저장 집중 통합 | 52 PASS | nested/flat provenance, 2.1 저장·재열기; 위 통합과 겹침 |
| 신규 기하 + 장부 harness 집중 | 32 PASS | Provider 14 + harness 18; 위 suite와 겹침, 합산 금지 |
| Web 전체 Vitest | 47 files / 438 PASS | jsdom canvas 미지원 경고는 실제 캔버스 품질 검증이 아님 |
| tsc -b / Vite build | PASS | 기존 로컬 도구; >500KB chunk 경고는 남김 |
| 원 실패 dry-run | PASS, external 0 | 현재 typed 대상/placement/실제 2.2/범위 .25..2.15, prior8/remaining2 대조 |
| 실제 회복의 read-only audit | PASS, 새 호출 0 | raw/dispatch/validation/patch/전체 compile/장부/hash/원본 설정 재대조 |

추가 회귀: 동일 ID의 2.2→2.18→2.1 부분 개선·성공, 악화 2.3 후보의 rollback 후 원 base 수정, 무변화 침대 patch 뒤 올바른 대상 수정, 순서-only NO_CHANGE, 추정 방 높이 변경, 부모 순환/독립 다중 오류, 미매핑 예외, 관련 부모/자식 context, blocked packing의 첫 오류와 새 필수 제약 회귀 구분, 현재 6회만 차감하지 않고 이전 controlled2도 공제, 훼손된 장부 count의 dispatch 전 거절.

오프라인 합성 응답/테스트는 실제 LLM 성공률·사진 정밀도·실물 성능의 증거가 아니다.

## 실제 회복의 원본과 실행 ID

- 원 자연 생성 실행: `ef63a03d6bb243d39b0022a71426ca2f`, 원 실패 operation `d653c892-57c0-46f1-9dca-a929bc61a371`.
- 새 실제 기하 회복 실행: `76ed2cb64f094e779fc93696152388db`, attempt `0b2bc1f84036461798364f12dbd16581`.
- 원본: `outputs/structure-repair-live-20261009-ten/`, 앞선 controlled 구조/크기와 합계8 근거 `outputs/structure-repair-controlled-20261009/`.
- 새 결과: `outputs/geometry-repair-live-20261009/geometry/result.json`, `compiled-plan.json`, `final-candidate.json`.
- 실제 송신/수신/검사: 같은 폴더 `evidence/dispatches`, `evidence/*.json`, `evidence/validations`; 실행/span `diagnostics`.
- 공유 잔여 장부 `outputs/geometry-repair-live-20261009/campaign.json`, 독립 감사 `audit.json`. 전 승인/사진·장부 hash와 실제8회 공제 결속. 재생 초기 요청은 external_http=false로 분리했다.
- 전후 semantic revision: `a0913b4964ba1698396db9fb41bf4fe422c749b9fc74fa8c6ab1c170a8856171` → `5e0253f4e83bfcce0f55f7f1a10bb69f4e24f6a8158a52380b2bcdfbe38b4afe`.
- 최종 전체 plan SHA256: `3486853c1b77a1549409d8b4d256e12b901d06088052e906191f46122109bc9a`.

## 동일 결과의 실제 App/Isaac 인수

최종 전체 결과는 아래 후속 절에 기록한다. 최초 세 시도도 `outputs/geometry-repair-isaac-20261009`, `...20261009-r2`, `...20261010-r3`에 보존했다.

세 시도 모두 같은 plan SHA, 관측 10물체, 실제 current 3D, PhysX 0.4m 목표의 약0.36m 이동·도착, Stop·reload·reset까지 진행했다. 첫 failure는 마지막 진단 검사에서 재생에도 새 observer span을 기대한 test-only 단정이었다. 두 번째는 새 metadata 이름이 기존 안전 allowlist에서 제외됐고, 세 번째는 bind의 references event를 immutable manifest 필드에서 찾은 harness 오류였다. 원 기록/FAIL을 지우지 않고 기존 allowlist의 evidence_id/requests와 실제 references event 계약으로 수정했다. 모델·제품 형상·모터/안전 정책을 바꿔 해결하지 않았다. 새 유료 호출 0.

현재 화면에서 침대·열린 옷장·책상·의자·옷걸이·선풍기·블라인드의 파라메트릭 외형을 시각적으로 확인했다. 단순 collision box를 외형이라고 통과시키지 않았다. 장면은 추정 3.5×4.2×2.4m, 실측/사진의 모든 세부 위치·가림·크기 정확도는 미검증이다. 자동 렌더 critic은 호출하지 않았다.

### 최종 인수 PASS

`outputs/geometry-repair-isaac-20261010-r5/result.json`의 전체 상태와 browser 상태 모두 PASS. 실제 일반 채팅 입력/SIM 선택 → 동일 accepted plan의 저장 → Build/current frame → 명시 Run/PhysX 이동·도착 → 새로운 자연어 목표 → Stop/접힌 Twin/reload → reset → 진단 조회·실행 graph·모바일 layout/export → 소유 backend/engine 종료 → 디스크 ProjectStore 재열기/placement 재검사가 통과했다. 새 요청 0, 로봇 연결 0, pageerror/driver_error 0, original accepted model evidence/settings/hash 불변.

저장 schema **2.1**, inventory **10**, placement relation **10**. plan SHA는 실제 수락 결과와 그대로 일치한다. SIM 추가/preview의 scene revision `c374f1eb1a3815db7dd51f5e14eaa782d35a4f50fbfa8826646f1d3dac3f2cb6`는 semantic revision과 같은 hash가 아니다. 관계/모델 plan을 보존하고 App/scene compiler의 원 입력을 통해 파생된 revision임을 각각 기록한다. 실측/실물 이동 권한은 생기지 않는다.

네 번째 실행 `...20261010-r4`에서는 browser 전체 PASS 뒤 closed-backend reopen에서 schema2.0으로 sidecar가 누락된 실제 제품 결함을 발견했다. 일반 Application이 기존 nested provenance 키만 읽어 단계별 compiler의 flat `model_parameters`를 버린 것이 원인이었다. 모델 재호출·response 수정 없이 두 형식을 동일 core validator에 전달하는 수정과 새 회귀를 적용했다. r4의 FAIL/schema2.0 원본은 그대로 보존했다. 최종 r5의 schema2.1/10관계 원본은 별개다.

화면 근거: 최종 폴더 `generated-ready.png`, `generated-physics-arrived.png`, `generated-reset-preview.png`, `execution-diagnostics.png`, `execution-diagnostics-mobile.png`. 실제 stream 123 current frames, dropped 2/error null, PhysX 최대 이동 0.3603334179108209m를 기록했다. 소유 backend/engine 종료 뒤 supervisor phase=stopped를 확인했다. legacy viewport native capture의 `viewport_missing` 별도 FAIL은 headless live frame 전달 PASS와 혼동하지 않는다. 이번 현재 3D 인수는 새 Isaac frame의 실제 browser 표시·revision·Build receipt와 연속 stream으로 확인했다.

## G단계 상태와 잔여

| 단계 | 상태 | 정확한 경계 |
| --- | --- | --- |
| G0 | DONE | 원 후보 재생/원본불변/동적 진단, external0 |
| G1 | DONE for tested geometry paths | typed 모델/관계/배치→요청/원본 기록 연결; 미매핑/blocked 별도 |
| G2 | PARTIAL | 동일 ID 반복·NO_CHANGE·부분 개선·rollback 연결; 별도 scope 제안/확대 프로토콜 및 장기 후보 탐색은 위 경계 참조 |
| G3 | PASS for listed App paths | 현재 채팅·저장·진단·동일 실제 결과 연결; 새 실제 자연 생성은 아님 |
| G4 | DONE for listed matrix | suite/type/build/dry/accounting/hash; 전체 제품 인수 아님 |
| G5 | PARTIAL | 실제 저장 실패 회복1PASS; 새로운 자연 생성은 NOT_RUN |
| G6 | PASS for same accepted result | 실제 같은 결과의 App/Isaac/Run/Stop/저장재열기; 새 자연 생성·render critic·실물은 별도 |

미사용 1회로 사진 GPT 관측+Nano 구조+객체 batch 전체의 새 자연 생성을 끝낼 수 없다. 이번 후보는 초기4회를 필요로 했고 추가 repair가 생길 수 있다. 무의미한 1회를 소진하거나 새 승인으로 초기화하지 않는다. 다음 실제 자연 생성의 목적/사진/목적지/최대 호출·USD를 별도 승인한 뒤 일반 App에서 인수해야 한다.

로봇은 이 수정/생성/Isaac 검증에 필요하지 않다. 이후 현재 boot/release·안전 초기화/정지 검증, scan/odom/TF 원본·신선도, 다른 시작위치 정합, 승인된 Twin 검사·derived revision·목표 재검증, 실제 이동/Stop/5초 요약·loop 종료 조건의 현장 인수가 남는다. 기존 품질·domain/warehouse/openings·렌더 critic·가격 snapshot 갱신·패키지·Physical AI Jobs 조건의 별도 잔여도 유지한다.

## 검증 중 발견·정정한 실패

- 기본 Windows sandbox의 임시 폴더 ACL 실패를 실제 로직 실패와 분리했다. 검토 승인된 기존 로컬 테스트만 escalated로 재실행했다. ACL/WSL/설치 우회·삭제는 하지 않았다.
- 부모가 있는 단일 관계 재검사에서 전체 parent contract를 다시 singleton으로 검사해 생긴 오류는 전체 contract 검사 후 내부 row 검사로 분리했다.
- 과거 add fixture의 `source`를 현재 `evidence_ref` 계약으로 정정했다. bound helper의 request 전달과 production 계약은 유지한다.
- legacy human message 회귀, 중복 unittest import, 테스트 결과의 provider_provenance 이름 오류를 정정했다. 최초 FAIL을 runtime/model 실패처럼 해석하지 않는다.
- 새 read-only audit에서 모델 후보와 host-owned APPROXIMATE_TWIN_READY flag 차이를 기하 hash 차이와 혼동한 검사 오류를 정정했다. flag는 전체 compile 후 설정하고 형상·계획 hash를 독립 대조한다.
- read-only diagnostics 단언 뒤 존재하지 않는 close() 호출을 붙여 생긴 진단 명령 exit1은 단언 PASS와 구분한다. 제품 실행·새 모델 호출은 없었다.

기존 dirty 변경·raw·이전 FAIL·사용자 설정·키·로봇 guard 보존. commit/push/설치/시스템설정/새 에이전트/자동화 변경/실물 연결 0. 시험은 소유 backend/engine/browser만 정리한다.
