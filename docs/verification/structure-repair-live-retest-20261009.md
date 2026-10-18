# 실제 구조 수정 재시험과 전체 생성 실패 분석

2026-10-09 KST · Baseline v1.0.379 · 사용자 새 승인 최대 10회 · 기존 USD1 한도

새 backend에서 실제 GPT 사진 관측과 Nebius Nemotron 설계·수정을 시험했다. **새 구조 수정 계약과 크기 수정은 실제 응답으로 각각 통과했지만, 일반 사진 생성은 최종 기하 검사에서 실패했다.** 전체 성공이나 사진 정밀도 검증으로 합치지 않는다.

## 호출과 결과

| 시험 | 새 실제 호출 | 결과 |
| --- | ---: | --- |
| 일반 React 채팅의 사진 관측→구조→객체 2 batch→최종 수정 | 6 | FAIL · 관측/구조/파라미터는 통과했으나 블라인드 높이 오류가 유지되어 `REPAIR_STALLED` |
| 기존 정상 응답 복사본의 종류 오류→새 구조 수정 계약 | 1 | PASS · 종류와 파생 coverage를 한 대상에서 해결 · 정상 sibling 보존 · 전체 컴파일 |
| 기존 정상 응답 복사본의 음수 크기→typed patch | 1 | PASS · 오류 대상만 수정 · 정상 sibling 7개 보존 · 전체 컴파일 |

**총 8/10회, 미사용 2회, 추정 USD0.01161723.** UNKNOWN 0, pending lock 0이며 추정 비용은 실제 usage 기준이지 청구서 확인값은 아니다. 이미 같은 최종 오류에 대한 무변화 수정이 두 번 확인되어 같은 요청을 반복하지 않았다.

일반 생성은 기존 등록키와 실제 외부 HTTP를 사용했다. GPT 사진 관측 한도 4000, Nemotron 설계·수정 한도 20000, no-thinking, 호출 300초/전체 900초를 유지했다. 응답 8개 모두 `finish_reason=stop`이며 출력 소진·시간 초과는 없었다. 사진 전송은 첫 GPT 관측 1회뿐이다. 통제된 수정시험에는 이미 저장한 초기 context를 별도 `fixture=true, external_http=false`로 재생했고 **수정 응답만 실제 Nemotron**을 호출했다. 이를 새로운 자연 생성 성공으로 세지 않는다.

기존 프로그램을 강제 종료하지 않고 최신 source로 시험 소유 backend를 새로 시작했다. 일반 UI의 시도 6/6 표시, terminal 결과 표시, 새로고침 후 같은 operation·실패 상태 보존 및 자동 재호출 없음은 통과했다. page error 0, 엔진 명령 0이다. 이 UI 검사 PASS는 생성 결과 FAIL을 바꾸지 않는다. 시험 소유 backend는 종료됐고 사용자 설정·키·기존 유료 이력·원본을 변경하지 않았다.

## 전체 생성 실패의 정확한 원인

실제 새 관측은 10개 물체를 구성했으며, 블라인드와 천장등도 포함됐다. 방 치수와 배치는 모델 추정이며 실측 인수가 아니다. 최종 실패는 방 추정 크기 자체를 거절한 것이 아니라, 모델이 제안한 방 높이와 벽 부착물의 높이가 서로 모순된 경우다.

검사 시 방 높이는 2.4m, 블라인드 높이는 0.5m, 블라인드 중심 높이는 2.2m였다. 벽 부착물이 바닥·천장 사이에 들어가려면 중심 높이가 물체 높이의 절반 이상이면서 `방 높이 − 물체 높이/2` 이하여야 한다. 이 후보의 상한은 2.15m인데 중심이 2.2m라서 상단이 2.45m가 된다. `PHOTO_RELATION_WALL_HEIGHT_INVALID: window_blind_1` 검출은 이 후보의 기하 관계와 일치한다. 2.15m를 제품 정답이나 사진별 상수로 넣지 않았다.

제품의 최종 compiler 예외에는 `contract_report`가 없었다. 로그에는 대상 ID가 붙은 전체 오류 문자열이 남지만 `BudgetedPipeline`의 실제 수정 요청은 다음과 같았다.

```json
{"validation": {}, "error_code": ["PHOTO_RELATION_WALL_HEIGHT_INVALID"]}
```

물체 전체 후보는 전달했으나 **어느 물체·필드가 위반했고 실제 값과 허용 관계가 무엇인지** 구조화된 진단으로 전달하지 않았다. 로그의 `window_blind_1`도 오류 코드만 추출하면서 수정 피드백에서 빠졌다. 모델은 블라인드를 바꾸지 않고 침대·책상의 기존 값과 같은 update 두 개를 두 번 반환했다. 두 patch 적용 전후 revision은 모두 `46c8b909cf3715fd8a15df50b83e1355a49ddfaef8389ef9600b20083645543e`로 같았다.

최종 patch 경로는 형식이 맞으면 무변화 patch도 일단 수락한 뒤 전체 재검사·비진전 판정에서 중단했다. 따라서 이는 새 구조 keyed patch의 동일 ID 충돌 문제 재발이 아니다. **최종 기하 진단 전달의 누락과 무변화 patch 판정 지연이 확인된 제품 결함**이며, 실제 모델도 주어진 수정 과제를 해결하지 못했다. 모델 가중치와 constrained decoder 중 어느 쪽이 응답 선택에 영향을 줬는지는 분리하지 못했다.

## 새 구조 계약의 실제 통과

v377 정상 구조 복사본의 첫 관측 물체 kind만 다른 허용 종류로 바꾸는 범용 fault를 사용했다. validator가 종류 불일치와 관련 coverage 누락을 검출한 뒤, 제품의 `semantic-structure-repair-1.1` 요청을 실제 Nemotron으로 보냈다.

응답은 한 대상의 `changes.bed`에 `kind=bed, evidence_ref=seen:e6`를 함께 설정하고 `additions={}`를 반환했다. 1.766초/149 출력 tokens, 추가 호출 1회로 재검사와 전체 컴파일이 통과했다. 정상 물체와 원 관측 근거는 보존됐고, 과거 두 응답의 중복 set 실패는 원본에서 지우거나 PASS로 바꾸지 않았다. 이번 시험은 같은 물체를 여러 회차에 걸쳐 다시 수정해야 하는 상황까지 실제 모델로 만든 것은 아니다. 그 동작의 기존 오프라인 회귀와 구분한다.

크기 오류는 별도 정상 후보 복사본의 첫 dimensions 성분만 -1로 바꾸고 기존 제품 batch 수정 루프를 사용했다. 실제 Nemotron 응답 1회가 유효한 수정안을 반환했고 정상 sibling 7개의 전체 값이 보존되며 전체 컴파일까지 통과했다. 사진 재전송과 수동 정답 주입은 없다.

## 실행 ID와 원본 로그

| 범위 | Execution ID | 근거 위치 |
| --- | --- | --- |
| 새 일반 생성과 최종 수정 FAIL | `ef63a03d6bb243d39b0022a71426ca2f` | `outputs/structure-repair-live-20261009-ten/run-1/runtime/provider-evidence` |
| 종류 수정 PASS | `7d4a0e30e1aa4edb980386c06942dcbd` | `outputs/structure-repair-controlled-20261009/structure/evidence` |
| 크기 수정 PASS | `4b13edd8ff3f45dcaa0127e8cd443767` | `outputs/structure-repair-controlled-20261009/objects/evidence` |

각 실행에는 실제 request/schema, redacted raw response, 적용 후보·검사 실패, attempt/span ID 및 장부 usage가 남는다. `outputs/structure-repair-controlled-20261009/audit.json`은 **감사 PASS이지 전체 생성 PASS가 아니다.** 실제 8개 응답의 request/raw/validation SHA·usage·ID 결속, 총 한도, UNKNOWN/lock 및 원본·설정·과거 이력의 SHA 불변을 무호출로 대조했다.

## 시험 도구와 오프라인 회귀

현재 자연 생성이 실패했어도 별도 정상 역사 context를 재생해 새 구조 계약을 시험할 수 있도록 기존 시험도구에 `--accounting-prior`를 추가했다. **시험 context 원본과 현재 승인 장부는 구분**하며 이번 일반 생성 6회와 USD0.01125513을 먼저 차감해 잔여 4회/USD0.98874487만 허용했다. 두 수정시험은 같은 잔여 장부를 공유했다. 과거 context의 4회 장부로 현재 호출 수를 초기화하지 않았다.

승인 문구·사진 SHA·장부 SHA·정산 상태·원본 불변을 확인하며, 출력 소진/UNKNOWN/증거 실패의 전체 보호 중단은 다른 case로 우회하지 않는다. 새 계약 감사와 명시적 역사 array 감사도 구분했다. 제품 생성 source·기본 설정·guard를 이번 턴에 바꾸지는 않았다.

- 도구 회귀 14개 PASS / .128초: 신규 6개는 현재 6회 사용량 보존, 다른 승인 거절, 미완료/UNKNOWN·출력 소진/증거 실패 중단, 손상 증거와 원본 변경 거절을 검사했다.
- 일반 승인 및 도구 통합 28개 PASS / 11.154초. 위 14개와 중복되므로 합산하지 않는다. 외부 호출은 0이다.
- dry-run은 현재 6회 사용·잔여 4회 및 범용 종류 오류 검출을 확인했다. 새로운 paid call은 없다.
- 변경 파일 diff 검사는 PASS다. 전체 Web/Provider 회귀나 새로운 Isaac 인수 결과로 표시하지 않는다.

## 다음 수정과 미완료

다음 제품 수정 대상은 **최종 기하 오류의 구조화된 진단과 범위가 제한된 수정**이다. 대상 ID·필드 경로·실제 값·허용 관계/경계·관련 parent/room을 기존 실행 로그와 수정 요청 양쪽에 결속하고, 진단이 없을 때 원 오류 상세를 잃지 않아야 한다. 같은 revision의 무변화 patch는 정확한 실패 사유로 바로 구분해야 한다. 추정 방 치수의 재수정과 같은 물체의 차기 revision 수정은 유지하며, 사진별 높이나 특정 배치를 정답으로 하드코딩하지 않는다.

새 일반 생성→최종 수정→App 초안 저장과 현재 Isaac 3D/Run/Stop, 사진 정밀도·렌더 critic·여러 환경/warehouse/openings·가격/패키지/현장·규정 잔여는 유지한다. 새 backend 시험은 로봇·SSH·실센서·모터·배포·Isaac 실행 없이 종료했다. 전체는 **PARTIAL / whole=false**다.
