# 추가100회·출력10000 검증 계획 / v328

사용자 원문: “아니 현재까지 0.07$밖에 안썼네 100회 추가 써도되고 출력제한 4000토큰이었으면 10000토큰까지 늘려도 된다”.

## 승인과 보존

- 기존97 요청·실패·unknown 비용예약·가격·USD1 상한·raw는 보존한다. 이전119 상한의 미사용22에 새100을 더해 누적219, 현재부터122 사용 가능하다. 단일 실행1..5와 sharedrepair1은 유지한다. 사용 한도는 소진 목표가 아니다.
- 사용자의 화면USD.07은 사용자 관측이며 청구 API를 조회하지 않았다. 로컬 USD.13446040은 사용량 추정과 unknown 예약의 합으로 청구액과 다르다. 차액을 환불/초기화하지 않는다.
- 기본 observer4000/planner8000은 유지하며 명시 host 실험에서 둘 다10000으로 요청한다. browser/model은 설정을 변경하지 못한다. 실제 사용량/finish_reason을 함께 기록한다.
- 기존90초·사진 동의·정확한 관측 재사용 hash·same floor/geometry/plan/version·실물잠금은 유지한다. 로봇/설치/배포/commit/push/새agent 없음.

## 실행 순서와 판정

1. 한도 전파·repair 동일상한·잘못된10001/bool·승인chain/잔여이월·host-only 회귀를 통과시킨다.
2. P01 fresh Gemma→기본thinking Nano10000→최대repair1, cap3. 답변 잘림과 완성된JSON의 배치 실패를 구분한다.
3. 같은10000 정책의 정확히 hash가 일치하는 관측만 재사용해 no-thinking planner와 비교한다. 4000 관측을10000 응답인 것처럼 재사용하지 않는다. fresh 전체 표본과 cached 관측 표본은 분리한다.
4. 확인된 정책으로 독립 fresh 소규모 반복 후 실제 기존 App/chat→저장→Isaac 현재frame/Run/Stop/reload를 재검증한다. 실패·timeout·비용 unknown이면 원인을 검토한 뒤 다음 독립 실행 여부를 판단하며 자동 무한재시도하지 않는다.
5. 원본/source/hash/raw/usage/ledger·완성 JSON·첫시도/수정 성공률을 감사하고 Baseline/Memory를 함께 기록한다.

출력확대는 응답 잘림을 해결할 후보이지 semantic packing/관계 누락/실측 정확도의 해결 보장이 아니다. 현재24항목/4위치/3파생지지 검증을 전체 사진 fidelity·물리 준비완료로 표시하지 않는다. 기본정책 채택, 일반사진/attachment/실측/REAL은 별도 잔여다.
