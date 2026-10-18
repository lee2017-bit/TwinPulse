# TwinPulse 실제 GPT 관측 → Nemotron 단계별 생성·수정 시험

2026-10-09 KST · Baseline v1.0.371 · 사용자 승인: “그래 이제 총 10회까지 테스트해보자”

후속 v372 [요청·수정 계약 점검](ordinary-staged-request-audit-20261009.md): 세 Nano 요청본문/schema 해시를 당시 기록과 대조해 모두 일치했다. 관측 전달·수정 필드명 불일치·직전후보 누락을 확인했고 공개 attempts3 원인은 API의 고정 `[:3]` 절단으로 확정했다. 아래 내용은 당시 시험 결과이며 이 후속 점검으로 제품 수정이나 실제 생성 성공을 주장하지 않는다.

**결과는 FAIL이다. 최대 10회 중 실제 모델 요청 4회에서 `REPAIR_STALLED`로 중단했고 6회는 사용하지 않았다.** 자연 생성 작업은 1개이며 성공 0/1이다. 4개의 HTTP 응답이 정상이라는 사실은 장면 생성 성공이 아니다. 출력 잘림과 시간 만료는 이번 표본에서 발생하지 않았지만, 실제 모델이 누락을 수정하여 회복하는 기능은 통과하지 못했다. 전체 계획 PARTIAL / whole=false를 유지한다.

## 실행 범위와 실제 경로

- 기존 승인 침실 사진 SHA256 `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`, 원문 `Create a digital twin of my bedroom with a bed and desk.`를 사용했다. 이 SHA 검사는 시험 입력 결속이며 사진 전용 정답·배치 하드코딩이 아니다.
- 사진 관측은 기존 등록 OpenAI GPT-5.4 mini, 설계·수정은 기존 Nebius NVIDIA Nemotron-3-Nano-30B-A3B를 사용했다. 사진 관측 결과를 설계에 전달했다. 모델 응답을 고정 데이터나 수동 정답으로 대체하지 않았다.
- 일반 웹 채팅 → SIM 선택 → 서버 소유 예산 검토 → 명시 승인/Continue → 기존 App/API/gateway → 실제 HTTP 경로다. 새 일반 승인 1개, 최대 10요청/USD1이다. 과거 campaign 예산을 재사용하거나 자동으로 새 승인을 발급하지 않았다.
- 격리된 설정 복사에서 GPT 출력4000/Nano 출력20000·no-thinking·호출300초/전체900초·공통수정3/비진전2 정책을 사용했다. 원래 사용자 설정/키 metadata/이전 장부는 변경하지 않았다. 일반 기본 정책을 자동 전환하지 않았다.
- 기존 실제 local Isaac를 띄웠지만 생성이 structure 단계에서 실패했다. **새 장면 저장·Build·현재3D·SIM Run/Stop는 NOT_RUN**이다. Isaac 시작/연결을 생성·실행 PASS로 표시하지 않는다. 로봇 연결/SSH/배포/실물 동작은 0이다.

## 실제 원응답 결과

| 요청 | 단계 | 원응답 HTTP 소요 | 실제 출력 / 요청 한도 | 판정 |
| --- | --- | --- | --- | --- |
| 1 | GPT 사진 관측 | 10.453초 | 1455 / 4000 | 관측 스키마 통과: 18개 entity 중 물체·장애물 14개 |
| 2 | Nano 최초 structure | 2.781초 | 148 / 20000 | 침대 하나만 inventory에 반환, 관측 근거 연결 누락 |
| 3 | Nano structure 수정1 | 2.031초 | 146 / 20000 | inventory와 누락 오류 동일 |
| 4 | Nano structure 수정2 | 1.937초 | 148 / 20000 | 방 가로·세로 교환, inventory와 누락 오류 동일 → 비진전 중단 |

모든 응답 HTTP200 / finish_reason=stop이다. 표의 시간은 원응답 `elapsed_s`이며 공개 단계 시간은 주변 처리 때문에 조금 더 길다. 최종 공개 전체 active 시간 17.531초, 잔여882.469초, repairs2/3, stalled2다. 장부 추정 비용 **USD0.00948159**, UNKNOWN 예약0, 청구서 검증은 아니다. GPT 검토 가격은 [공식 모델 문서](https://developers.openai.com/api/docs/models/gpt-5.4-mini)의 input/output 백만 토큰당 USD0.75/4.50과 대조했고, Nebius 기존 모델 metadata GET의 USD0.06/0.24/context262144도 기존 검토 가격과 일치했다. 초기 무호출 시행과 본 시행에서 metadata GET 각1회는 모델 추론 횟수와 구분한다. 신뢰 가격 자동 갱신 기능 완료를 뜻하지 않는다.

## 원인: 시간·출력 한도가 아니라 관측 → 설계 연결과 수정 회복 실패

GPT는 침대, 책상, 의자, 옷장, 옷걸이, 블라인드, 조명, 선풍기, 케이블, 어댑터, 상자, 가방, 걸린 옷, 바닥 옷더미를 관측했다. 이는 모델이 반환한 14항목이며 사진 전체 누락 없음이나 실측 정확도를 독립 인증한 결과는 아니다.

Nano의 세 응답은 모두 inventory가 정확히 같은 침대 1개였다. 그 침대도 `basis=user / observation_ids=[] / user_quote=bed`여서 시각 관측 ID와 연결되지 않았다. 사용자 글에 명시된 책상도 실제 inventory에서 빠졌다. summary에 다른 가구를 언급하는 것은 구조화된 물체 생성의 대체가 아니다.

기존 `checked_structure`를 세 원응답에 그대로 재적용한 결과 모두 `PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING`, 누락된 관측 ID `e5..e18` 14개로 재현됐다. inventory SHA도 세 응답 모두 `61e83a03e335f1e6026dc4d499beb495a3e989c1ebe3c0267f3deeb32e8020c2`였다. 기존 수정 경로는 contract_report의 누락 ID와 오류 코드를 전달하지만 모델이 이를 반영하지 않았다. 방3.5×4 또는4×3.5m 추정이 실패 이유가 아니며 실측이 없으므로 추정으로 남긴다.

확인된 원인은 이 모델·프롬프트·중간 계약 조합이 관측 inventory를 충분히 출력하고 근거와 결속하지 못한 것이다. 모델의 모든 능력이 부족하다는 일반 결론은 아니다. **다음 개선 후보**는 실행마다 실제 관측에서 산출하는 물체 목록/ID를 중간 요청 계약에 결속하고, 누락 항목을 수정 대상으로 직접 전달·재검증하는 것이다. 임의 최소 가구수, 특정 침실 정답, 고정 방 크기, 검증을 건너뛰는 PASS로 해결하지 않는다. 이 후보 수정은 이번 시험에서 구현하지 않았다.

## 감사·시험 도구 및 한계

- 원응답4 ↔ 장부4 usage 일치와 저장 response SHA 통과. 과거 파일과 원응답을 덮어쓰지 않고 별도 `original-response-analysis.json`에 읽기 전용 재검사 결과를 저장했다. 추가 모델 호출0이다.
- inference source SHA 전후 불변, 원사용자 설정3개와 지정한 과거 campaign4개 SHA 불변, 소유 launcher/engine/backend 종료 succeeded, pending dispatch lock0/UNKNOWN0이다. 타 프로세스 강제 종료는 없었다.
- checkpoint 완료 단계는 observer뿐이다. structure가 유효하지 않아 draft가 없고 후속 물체 batch/최종 컴파일/저장/Build/실행으로 진행하지 않았다. 관측 캐시 존재는 완성된 Twin이 아니다.
- 처음 시험 도구가 일반 질문 상태를 `pending`으로 찾았으나 실제 값은 `waiting`이라 승인 이전에 실패했다. 시험 도구만 고쳤으며 이 시행은 승인0/유료 추론0으로 별도 보존했다. 본 실패와 구분한다.
- 실패 직후 저장 API 상태는 failed/REPAIR_STALLED이며 예산4회를 정확히 표시한다. 다만 공개 attempts 배열은3개, 원응답/장부는4개여서 마지막 attempt 상세의 최종 snapshot 누락은 추가 진단 대상이다. 원본 로그 소실로 단정하거나 수정 완료로 표시하지 않는다.
- 실패 캡처 이미지는 API terminal 판정 직후 React 갱신 전 화면이다. 그 이미지를 최종 UI 상태나 UI 고착의 증거로 사용하지 않는다.
- 마지막 오프라인 회귀는 Python Temp 쓰기 제한으로 첫 실행이 실패했다. 권한 검토를 거친 동일 로컬 승인·routing 회귀 **28 PASS / 9.855초**로 재확인했다. 초기 실패는 제품·모델 오류와 구분한다. AST3/Node syntax/변경 파일 diff check PASS; 전체 제품 테스트 재실행이나 새로운 모델 성공률 PASS로 확장하지 않는다.

## 근거와 다음 순서

- [본 시험·예산·종료 감사](../../outputs/ordinary-staged-live-20261009-ten-r2/summary.json), [원응답 재검사](../../outputs/ordinary-staged-live-20261009-ten-r2/run-1/original-response-analysis.json), [초기 무호출 시험 실패](../../outputs/ordinary-staged-live-20261009-ten/summary.json).
- operation `324445e9-ca10-4383-bcfd-4d51f009a7be`, request `ef245334-81d5-424e-be63-d0607bb5b09f`, diagnostic execution `55188c91a3ea4caf93faa56c739a3b05`, checkpoint `6d77cc260f8008f1d8593e98c94f28cd8dcf7804dc3432d802a53027aad749cf`.
- 순서: 관측 inventory/근거 결속 및 수정 피드백 개선 → 원응답 무호출 회귀 → 별도 명시 실행 승인으로 실제 회복 검증 → 성공 후보에만 actual Isaac Build/Run/Stop·렌더 검증. 지금 로봇 데이터가 이 실패의 병목은 아니다.
- warehouse/openings/전체편집 계약, 렌더 critic, 신뢰가격 갱신, S5/S6 실제 성공·실패/회복 전체 인수, 최신 패키지와 현장 인수는 계속 잔여다. 미사용6회를 동일 실패의 무목적 반복이나 승인 범위 밖 기능으로 소모하지 않는다.
