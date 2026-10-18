# 실제 혼합 모델 생성 및 자동 부분 수정 시험

2026-10-09 KST · Baseline v1.0.377 · 사용자 새 승인 최대10회 / 기존 USD1 유지

## 결론

새 v376 계약으로 **실제 GPT 사진 관측→Nebius Nemotron 설계→host 검증·컴파일→App 초안 저장** 1회가 통과했다. 활성 생성시간21.938초, 유료 호출4회, 수정0회다. 단일 시험이므로 일반적인 성공률·사진 복원 정밀도·실물 준비 완료로 해석하지 않는다.

정상 생성에 오류가 없었으므로 별도로 정상 원응답의 **복사본에 일반 오류 한 개씩** 넣어 기존 `BudgetedPipeline.content_stage`의 자동 부분 수정 루프를 시험했다. 초기 context는 저장 원응답 재생이며 새로운 모델 생성·성공 횟수로 세지 않는다. 실제 수정 응답만 Nemotron을 호출했다.

| 시험 | 실제 추가 호출 | 결과 |
| --- | ---: | --- |
| 일반 App 사진→관측→구조→파라미터2 batch→검증·저장 | 4 | PASS / 8개 관측 물체 개별 결속 / 정상 생성1회 |
| 종류·근거 오류 복사본의 자동 부분 수정 | 2 | FAIL / 같은 물체 중복 set 반복 / `REPAIR_STALLED` 보호 중단 |
| 음수 크기 오류 복사본의 자동 부분 수정 | 1 | PASS / 실제 typed patch1회 / 정상 sibling7개 보존 / 전체 재컴파일 |

**총7/10회, 추정 USD0.00940497, 미사용3회, UNKNOWN0, pending lock0.** 이는 usage 기반 추정이지 청구서 확인값이 아니다. 반복 실패가 이미 재현되어 남은3회를 같은 요청 반복에 소비하지 않았다. 새 사진 전송은 일반 생성의 GPT 관측1회뿐이다. 수정시험 사진 재전송0, 로봇·Isaac·Build/Run/Stop0, 원 설정·키·기존 유료 이력 변경0이다. 예약을 재개하지 않았다.

## 실제 일반 App 결과

- 일반 App의 Simulation only→현재 한도 승인→실제 등록키→현재 제품 worker 경로다. 모델 응답을 고정 데이터로 대체하지 않았다.
- GPT 관측8.265초/1113 출력 tokens; Nemotron 구조4.171초/358, 객체 batch6.078초/718와3.063초/245. 모두 HTTP200/finish_reason=stop. 실제 관측 한도4000, 설계·수정 한도20000, per-call300초/total900초, no-thinking 설정이다.
- 방3.5×4.2×2.4m와 배치는 모델 추정이다. 실측·도면을 정답으로 코드에 넣지 않았다. 침대·책상·사무용 의자·옷장·옷걸이·선풍기·케이블 묶음·옷더미8개를 관측별 source로 결속하고 기존 `home.*` 라이브러리 파라미터로 컴파일했다. 사진 속 모든 작은 물체를 빠짐없이 인식했다는 인수는 아니다.
- `runtime/active_project.json`의 Site 초안과 generation-store의 `APPROXIMATE_TWIN_READY` checkpoint를 저장했다. 새로고침 후 같은 operation/초안 revision이 유지되고 모델 재호출·엔진 명령이 없었다. 브라우저 page error0, 화면의 시도4/4 및 최종 검증 상태 표시를 확인했다.
- Engine 미등록인 generation-only 시험이다. 컴파일된 3D 데이터와 저장 성공이지 새 Isaac 렌더·PhysX·이동/정지 성공이 아니다. 우측 실제 3D 화면의 사진 유사도는 이번에 검사하지 않았다.

최초 sandbox 실행은 Chrome `spawn EPERM`으로 모델 호출·승인 장부 모두0에서 끝났다. 해당 출력 폴더를 보존하고 승인된 generation-only 실행으로 진행했다. 다른 프로세스 강제 종료·ACL 수정·새 설치는 하지 않았다.

## 수정 실패의 정확한 내용

실험은 특정 사진 정답을 모델에게 넣는 방식이 아니다. 성공한 구조 복사본의 첫 `seen:` 항목에서 kind 하나를 다른 허용 kind로 바꾸는 범용 fault다. 실제 validator가 종류 불일치와 해당 관측 coverage 누락을 진단했다.

Nemotron 첫 수정은 같은 ID에 두 개의 `set`을 반환했다. 하나는 올바른 원 관측 참조로 종류를 고쳤지만, 다른 하나는 같은 ID를 텍스트 참조로 다시 수정했다. 동일 ID의 두 연산은 의미가 모호하고 관측 근거를 잃을 수 있으므로 host가 **둘 중 하나를 임의로 선택하지 않고 전체 patch를 거절**했다. `BINDING_REPAIR_DUPLICATE_TARGET`이 원 후보·원 진단과 함께 다음 수정 요청에 전달됐는데 두 번째 모델 응답도 같은 중복 연산이었다. 적용 후보는 원 실패 후보 그대로 보존되고 `REPAIR_STALLED`로 끝났다. 원 실측이나 운영 중 자연 발생한 종류 오류가 아니라 **통제된 오류에 대한 실제 모델 회복 실패**다.

현재 구조 patch의 array schema는 개별 set을 허용하지만 같은 ID 반복은 host 사후 검사에 맡긴다. 이 시험에서 모델은 그 전체 불변조건을 지키지 않았다. 따라서 일반 응답 계약·host 결속 개선으로 정상 생성이 성공했어도, 구조 수정 계약의 신뢰성까지 완료됐다고 주장할 수 없다. 모델 가중치와 Nebius constrained decoder 중 어느 쪽이 원인인지는 이 시험만으로 분리하지 못했다.

다음 개선 후보는 사진별 정답이나 오류 무시가 아니다. **오류 대상별 keyed patch처럼 동일 ID가 두 번 존재할 수 없는 계약**, 이미 검증된 관측 참조의 유지와 kind/ref 수정 대상 분리, 종류 불일치에 딸린 coverage 진단을 같은 대상에 묶는 방식이다. 신규·실제 누락 관측 추가는 별도로 유지해야 한다. 실제 검증 실패를 조용히 수정·통과시키거나 정상 물체를 삭제하는 fallback은 넣지 않았다. 이 개선은 아직 구현하지 않았다.

## 실제로 회복한 수정

다른 복사본에서는 첫 파라미터 batch의 한 물체 크기 첫 성분만 -1로 바꿨다. `SEMANTIC_NUMBER_RANGE_INVALID`가 검출되자 제품 루프가 해당 slot만 허용한 `base_revision + operations`를 요청했다. Nemotron 실제 응답1회가 유효한 set을 반환했고 host가 적용 후보→batch 검사→후속 저장 context→최종 전체 compiler 검사까지 진행했다.

일곱 정상 물체의 전체 parameter 값이 원 성공 후보와 동일했다. 파라미터 수정1회 및 전체 재컴파일은 실제 모델 경로에서 확인했지만, 초기 관측·구조·정상 batch들은 재생한 context다. 이를 두 번째 자연 생성 성공이나 실물 정합 성공으로 세지 않는다.

## 실행 ID와 보존 자료

| 범위 | Execution ID | 근거 위치 |
| --- | --- | --- |
| 일반 생성4회 / App 저장 | `719a94932b394233889a44127c95088d` | `outputs/semantic-binding-live-20261009-ten-r2/run-1/runtime/provider-evidence` |
| 종류 오류 수정2회 / FAIL | `132fa021486e464ba003792a6e6d3528` | `outputs/semantic-scoped-recovery-20261009/structure/evidence` |
| 크기 오류 수정1회 / PASS | `3ae7300ff8f944fb8245e2aace561722` | `outputs/semantic-scoped-recovery-20261009/objects/evidence` |

각 실제 시도의 dispatch request·raw response·validation/applied candidate·repair decision·execution/span/attempt ID를 대조했다. raw/request/validation SHA256와 raw↔장부 usage, 모델·한도, 실행 ID 일치가 모두 통과했다. 실패한 patch 두 개는 현재 host 검사로 다시 거절됐으며 성공 patch는 실제 저장한 적용 후보와 동일하게 재생됐다. 원 응답·기존 설정·과거 승인 장부 SHA도 불변이다.

`outputs/semantic-scoped-recovery-20261009/scope.json`은 앞선4회와 USD0.00886899를 포함하고 잔여6회/USD0.99113101만 허용한다. 같은 승인 안의 독립 두 수정시험은 동일 잔여 장부를 사용했다. 독립 실행 ID는 각 시험을 분리하고 부모 장부/hash 및 `audit.json`으로 이번 총7회를 연결한다. 재생 context에는 `fixture=true, external_http=false`를 별도 폴더에 남겨 실제 유료 응답과 혼동하지 않는다.

검사 도구 `scripts/verify_semantic_scoped_live_recovery.py`는 기존 제품 자동 수정 루프/설정 transport를 사용한다. 초기 재생과 실제 수정 호출을 분리하고, 네트워크는 승인된 Nemotron/한도20000/image-free repair에서만 가능하다. 같은 case를 자동 반복하거나 새로운 예산을 생성하지 않는다. 출력 소진/UNKNOWN/증거 저장 실패는 중단한다.

## 검증과 남은 범위

- 실제 화면 검사2개 PASS: 전체 시도 이력, 새로고침 후 동일 결과·무재실행. 이는 일반 생성1회의 UI 검사다.
- 통제 fault 사전 dry-run2개 PASS / 외부0: 실제 validator가 종류·크기 오류를 검출했다.
- 새 시험도구 회귀8개 PASS / 외부0 / .114초: 초기 재생 무HTTP·원본 불변·fixture 표시, 실제 수정 위임, 모델/한도/사진/schema/role 허용 범위, fixture validation 분리. 최초 실행은 테스트 fixture의 response ID 누락1 error였으며 fixture만 정정해 같은8개 통과했다. 유료 시험 결과에는 영향이 없다.
- `--audit-only` PASS / 추가 모델0: 7개 실제 호출의 request/raw/validation/accounting 및 보존·전체 한도를 독립 대조했다. **감사 PASS와 구조 모델 수정 FAIL을 분리했다.**
- 제품 App/core/provider 생성 source 및 저장 기본설정은 이번에 수정하지 않았다. 추가한 것은 통제 시험 도구와 회귀·기록이다. 기존 Provider238/App194 오프라인 결과를 이번 실제 모델 성공률로 합산하지 않았다.

실제 일반 생성 한 번은 통과했지만 종류 수정의 중복 실패가 남는다. 다음은 그 범용 수정 계약 개선 후 새 승인 범위에서 구조 회복 재확인, 성공 후보의 일반 App→현재 Isaac 3D→Run/Stop 인수다. 사진 정밀도·여러 환경/warehouse/openings·렌더 critic·신뢰 가격 갱신·최신 패키지·현장/실물 및 Physical AI Jobs 규정 확인 등 잔여를 완료로 바꾸지 않는다. 전체는 여전히 **PARTIAL / whole=false**이며 전원만 켜면 전체 데모 완료라고 보장하지 않는다.
