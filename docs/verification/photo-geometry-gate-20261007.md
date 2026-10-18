# 사진 geometry 검사·수정 연결 — 2026-10-07 / v323

## 결과

사용자의 “다시 검사로직을 짜보자” 요청에 따라 **실제 생성 geometry 검사와 기존 bounded repair를 제품에 연결**했다. 검토된 P01 사진의 4개 위치 조건·3개 지지 조건을 검사하며, compact 변환기는 부모 지지면 위 배치도 생성한다. 모델의 `accept_estimated`나 객체 존재 개수로 통과시키지 않는다.

**로컬 구현/회귀 통과이며 새 실제 LLM 수정 성공·전체 사진 복원·새 Isaac·실물 인수는 아니다.** 일반 사진 자동 관계 추출, 가림/부착 복원과 실제 치수는 여전히 미검증이다. 기본 compact OFF, H5/H6/C3–C6 PARTIAL, whole demo ready=false 유지.

## 제품 흐름과 실패 처리

`기존 JSON·evidence 검증 → 실제 pure executor → geometry 검사 → 수정 가능한 오류만 shared repair1 → 같은 검사 재실행 → GenerationResult → 기존 저장/Build`

- 기존 기본 Site2.2 사진 경로와 실험 compact 경로 모두, 검토 근거가 있는 사진은 generation 성공 전에 검사한다. 실패 후보는 새 GenerationResult/장면으로 수용하지 않는다.
- `photo-geometry-quality-1.0`은 실제 catalogue 부품/회전/좌표를 사용한다. `PHOTO_POSITION_MISMATCH`, `PHOTO_SUPPORT_MISMATCH`, 누락/종류 변경, 지지면의 자식 겹침, 천장 관통을 구분한다. 부모 yaw 좌표에서 자식 mesh 전체의 XY 포함과 bottom→surface-top Z 간격을 모두 검사한다. 로컬 관계 허용 XY .015m/Z .02m는 실물 정합 허용값 변경이 아니다.
- P01에서 침대 우측, 책상 좌측·후방, 옷장 후방만 확실한 위치 조건으로 사용한다. 침대 깊이를 만들어내지 않는다. 방 크기는 추정·실측 없음; 큰 추정 면적은 경고이지 실측 FAIL/PASS 판정이 아니다.
- 검사 기준은 별도 host-reviewed 계약이며 **원본 사진 SHA에 결속**된다. 기존 inventory1.0 직렬화는 바꾸지 않았다. 다른 사진에는 P01 기준을 빌려 쓰지 않고 `UNVERIFIED`로 남긴다. host 근거/사진/재고 불일치는 transport 호출 전 실패한다.
- 모든 오류의 object/parent/part, expected/actual 좌표, XY 포함, Z 간격, 재수정 가능 여부를 bounded 구조로 남긴다. repair 요청에 전체 geometry 진단이 들어가며, 400자 요약 때문에 뒤의 지지 오류가 사라지지 않는다.
- 한 작업의 기존 shared repair 최대1/전체 deadline/observer 재사용/identity·취소·unknown 처리 유지. compact가 표현할 수 없는 지지 오류나 compiler 의존 실패는 **추가 호출 없이** 원인을 반환한다. 직접 Site2.2 tool plan은 위치/높이/종류 표현이 가능하므로 같은 한도 안에서 해당 수정이 가능하다.
- quality repair는 첫 실패 후보의 floor size/centre를 결속한다. 실측 없는 추정 방도 수정을 위해 확대/좌표계 변경하면 `PHOTO_REPAIR_ROOM_FRAME_CHANGED`로 거절한다. 명시 사용자 치수 보존도 기존대로 유지된다.
- 다음 시도가 JSON 단계에서 실패하면 이전 quality report를 현재 결과로 남기지 않는다. 시도별 이전 진단은 보존된다. 제품의 기존 generation 진단/API·실패 journal에는 whitelist된 모든 오류가 남으며 임의 응답/프롬프트/인증 정보를 내보내지 않는다. 새 전용 UI 품질 카드/새 Browser 인수는 이번 범위가 아니다.

## 변환기에서 수정 가능한 관계

`photo-layout-1.1` wire JSON 필드는 그대로다. 별도 `photo-layout-compiler-1.2`는 SHA-bound 검토 계약을 받은 경우에만 아래 지지를 파생한다. 직접 legacy 호출에는 기존 독립 proxy 동작이 유지된다.

| 자식 | 부모/실제 catalogue 부품 | 구현 |
|---|---|---|
| top_storage | wardrobe/body | 상면 위 XY·높이 배치 |
| monitor | desk/top | 책상 위 별도 footprint |
| tabletop_items | desk/top | monitor와 겹치지 않는 footprint |

부모를 먼저 floor에 배치하고 자식은 지지면 내부에 배치한다. 자식의 모델 region은 advisory이며 요청 region/파생 region/parent/part를 모두 provenance에 남긴다. 자식을 독립 floor 물체로 강제해 공간을 낭비하지 않는다. 지지면에 실제로 맞지 않으면 `PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE`; 확대·누락·강제 축소로 통과시키지 않는다. 전체24 inventory와 fabric/cable/unknown의 기존 synthetic keepout은 유지한다. catalog 치수는 원래 실물의 측정값이 아니다.

검사된 조건이 모두 맞아도 `checked_relation_status=PASS`, 전체는 `status=PARTIAL`, `full_photo_reconstruction=UNVERIFIED`, `metric_scale_validation=UNVERIFIED_NO_MEASUREMENTS`, `physical_validation=NOT_RUN`이다. 알려진 조건 통과와 사진 전체 복원을 구분한다.

## 저장된 실제 모델 출력에 대한 새 검사

최종 결과: `artifacts/agent-reliability-20261007/photo-geometry-gate-offline-r3/result.json`.

`scripts/verify_photo_geometry_gate.py`는 네트워크/credential/모터 코드 없이 원래 실제 응답의 UTF-8 SHA·byte 수를 대조하고 현재 compiler/gate에 넣는다. 원래 request가 변경된 새 실행을 exact 원래 request의 모델 성공으로 부르지 않는다. fresh output 디렉터리만 허용하고 overwrite하지 않는다. r1/r2는 같은 증분의 중간 로컬 산출물이며 최종 source hash는 r3에 있다.

- 과거 실제 후보3개: 새 검사에서 전부 FAIL로 거절, 지지3FAIL 각각 재현. 원본은 변경하지 않았다.
- 저장 Nano 응답 `a946…` 그대로 새 compiler 적용: 지지3은 해결됐지만 위치3 오류 → FAIL.
- 저장 Nano 응답 `810d…` 그대로 적용: 지지3은 해결됐지만 책상 후방1 오류 → FAIL.
- 위 각 intent의 검토된 위치만 로컬 검증용으로 수정한 파생2개: 검사 조건 PASS, 전체 PARTIAL. **모델이 스스로 수정한 성공2개가 아니다.** 두 방의10×12m 추정/120㎡ 경고·실측 미검증은 유지됐다.
- 이전 campaign, 실제 result/post-run analysis/plan/raw, 이전 실제 project/run 포함 **원본16파일 전후 SHA 동일**. r3에는 제품/검증기6 source hash와 검사 중 불변도 기록했다.

## 회귀와 중간 실패

- 신규 검사29개 포함 provider 전체 **94 PASS / 2.641s**. 지지 XY/Z·회전4방향·sibling·누락·NaN·사진 hash·frame 변경·한 번 repair·불가능 repair 무호출·현재/시도별 진단·기본 Site2.2 경로·과거 실제 후보를 검사했다.
- 최종 core 전체 **302 PASS / 25.659s**.
- 관련 생성/신뢰성/채팅/재사용 전체 **166 PASS / 87.271s**. 마지막 floor-frame 보존 변경 후 관련 repair/채팅 생성 **59 PASS / 24.295s** 재확인. 겹치는 회귀를 합산하지 않는다.
- Python7파일 compile, tracked diff-check 및 신규 파일 whitespace 검사. 새로운 실제 Browser/Isaac 실행은 NOT_RUN이다.
- 초기 sandbox 기본 Temp와 저장소 내부 Temp 모두 Python TemporaryDirectory 접근/정리 `PermissionError/WinError5`를 재현했다. 접근권한/ACL/시스템 설정은 바꾸지 않았다. 승인 심사를 거친 정상 사용자 권한의 동일 로컬 회귀로 최종 확인했다. 첫 관련 명령에 실제로 없는 테스트 모듈2개를 넣어 loader ERROR2가 났으며, `rg --files`로 존재 모듈을 골라 수정 후166 PASS. 이를 제품 assertion 실패나 묵살한 PASS로 만들지 않는다.
- 이번 작업이 만든 저장소 내부 테스트 Temp는 exact absolute path/reparse 여부·파일0개를 읽기 확인한 뒤 빈 하위 디렉터리50개만 정리했다. 원본·검증 산출물·다른 사용자 Temp는 삭제하지 않았다. 최종6 source/원본16파일 해시 불일치0.

새 외부 호출0/추가 비용0. 공유 campaign **59/60, pending0, 전체 추정+예약 USD.10468336/청구 미확인** 그대로다. 원본/과거 실패/dirty/기존 v1/v2/hash·정지·freshness·실물 잠금 보존. SSH/센서/모터/배포/설치/commit/push/새 agent0.

## 정확한 다음 작업

1. 현재 새 prompt/변환기/gate를 실제 모델로 다시 검사한다. 기존 전체 요청 한도가1회만 남아 있어 observer+planner+repair 묶음 재평가는 별도 예산 판단이 선행되어야 한다. 자동 reset/새 campaign/무한 재시도는 하지 않는다.
2. 실제로 조건을 통과한 같은 새 결과를 기존 chat→저장/재열기→actual Isaac Build/화면/Run·Stop에 연결 인수한다. 이전 source의 Isaac PASS를 이번 source에 전용하지 않는다.
3. 사람 검토가 없는 다른 사진의 relation 추출·확신/불확실성·근거 결속, 부착/hinge/침구/가림 관계를 확장하고 재평가한다. 현재 P01 보조 기준의 성능을 일반 사진 정확도로 주장하지 않는다.
4. 실측 또는 승인된 robot scan/odom/TF 정합과 현장 인수는 별도다. 방 크기/위치의 실물 정확도·전체 Demo 완료는 아직 보장할 수 없다.
