# 추천 모델 조합 실제 생성 재시험

DeepSeek V4.1 Flash 사진 관측과 Nemotron 3.5 Lightning 설계·수정을 일반 채팅 App의 기존 승인·실행 로그 경로에 연결해 실제 호출했다. 모델 응답 6개는 정상 수신했지만, host가 블라인드 위치를 바닥 경계 밖으로 생성하여 전체 시험은 실패했다. 범용 벽면 배치 수정 후 같은 원본 응답의 전체 기하 재검사는 통과했다. 실제 모델의 현재 렌더 평가와 최종 저장·SIM 인수는 아직 통과하지 않았다.

## 승인과 실행 범위

- 이번 사용자 승인: “추천 조합 실제 생성 및 재시험 승인한다 횟수는 그대로”. 더 보수적으로 두 반복의 새 요청을 합계 10 HTTP/USD1 이내로 제한한다고 실행 전에 알렸다. 기존 전체 모델 비교의 두 역할별 PASS를 조합 전체 PASS로 쓰지 않았다.
- 원본 사진 SHA256 `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`, 동일 bedroom/bed/desk 프롬프트. 사진별 정답·좌표·크기·inventory 하드코딩 없음. 시험 입력의 SHA 승인 결속은 제품 정답 조건이 아니다.
- 관측 `deepseek-ai/DeepSeek-V4.1-Flash`, 설계/수정 `nvidia/Nemotron-3_5-Lightning`. observer/planner 출력 각각20,000, 요청300초, 전체900초, 최대수정3, current-render review 명시ON. length/UNKNOWN 즉시중단을 유지했다.
- 기존 키는 Windows 보안 저장소에서 메모리에만 읽고 새 출력/문서에 저장하지 않았다. 별도 reviewed-settings만 선택 조합으로 저장; 전역 설정3개·과거 장부 불변. OpenAI 모델 호출0.
- 현재 Nebius metadata GET으로 선택 모델의 가격/context를 재확인. metadata SHA256 `c9c56152c844c5984f7340604248713b8582aa7dcfaebc39634ea5465507e604`; Flash 입력0.30/출력1.20 USD per1M/context1048000, Lightning0.06/0.24/context1048576. 청구금액·잔액을 직접 확인한 것은 아니다.
- 일반 설정/API의 단계 모델 허용목록과 가격표에 두 모델을 추가했다. 설정 UI는 기존 서버 options를 사용하며 정확한 Flash/Lightning 이름과 Lightning 추론 설정을 표시한다. 알 수 없는 모델은 다른 모델 이름으로 표시하지 않는다. 자동 전역 전환/fallback 없음. Lightning의 이미 실제 비교에서 사용한 no-thinking wire를 정확한 모델에만 허용했다.

## 실제 첫 시험 결과

`outputs/recommended-combination-live-20261010/sample-1/summary.json`과 `run-1/result.json`에 최초 FAIL을 보존했다. ordinary 승인ID `ordinary-generation:64abcf79-2cf5-499f-95a7-d64fa109b9cc`, operation `f65e81c2-3a24-48ce-9019-46fd4512ea98`, 실행ID `ff5ef11be4e644cba15eece2083286ad`. 원본·dispatch·검증·장부가 같은 attempt/execution에 결속되어 있다.

| 단계 | 실제 요청 | 결과 |
| --- | ---: | --- |
| 사진 분석 | 1 | stop/계약통과, 약10.9초. 물체/unknown21개를 후속 설계가 보존 |
| 방 구조 | 1 | stop/계약통과, 약3.5초. 추정4.2×4.8×2.4m; 실측 아님 |
| 물체 파라미터 배치 | 4 | 모두 stop/계약통과, 요청별 약2.8–3.9초 |
| 전체 host 기하 검사 | HTTP0 | tool_executor의 ROOM_ITEM_OUTSIDE_FLOOR가 미결속 UNMAPPED로 변환되어 CHECK_EVIDENCE_INSUFFICIENT 중단 |
| 실제 모델 자동 수정/현재 렌더 critic | 0 | 해당 단계 미도달 |
| 최종 저장/Build/Run/Stop | 0 | 해당 단계 미도달. Isaac 프로세스 기동은 성공 인수를 뜻하지 않음 |

6/10 HTTP, 수정0, 추정 USD0.00841584, UNKNOWN0/dispatch-lock0. 원래 승인 입력·설정·장부 그대로이고 owned 종료 diagnostics는 succeeded이다. 원본/파생 렌더 critic은 전송되지 않았으며 원본 사진 관측1회만 전송되었다. 실패 화면 `run-1/failed-journey.png`도 저장했다.

전체 새 생성에 첫 시험은 관측+구조+물체 batches로 이미6회가 필요했다. 남은4회로 동일한 새 전체 시험을 충분히 반복하기 어려워 두 번째 새 샘플을 시작하지 않았다. 2/2 인수라는 주장은 하지 않는다. 남은4회를 임의로 초기화하거나 새 자동 승인으로 확장하지 않았다.

## 재현한 근본 원인과 제품 수정

`scripts/audit_recommended_combination.py`는 실제 raw/dispatch/validation/장부의 해시·usage·attempt·execution·finish_reason을 감사하고, immutable checkpoint 후보를 현재 제품 compiler에 재생한다. 외부 dispatch0이며 원본JSON55개의 SHA를 보존했다.

원 `audit.json`에서 실패 source A16/window_blind를 결속했다. 모델은 rear_left/rear_wall과 폭1.5m를 제안했고 세계좌표를 생성하지 않았다. host는 방폭4.2m에서 지역 중심 x=-4.2/3=-1.4m를 그대로 썼다. half-width0.75m를 더하면2.15m로 바닥 half-width2.10m를5cm 넘는다. 이것은 모델 JSON 오류나 Wi-Fi 문제, 방 추정 크기의 실패가 아니라, 유효한 폭을 고려하지 않은 host의 벽면 pose 생성 결함이다.

`photo_layout._place_attachments`는 이제 rear/side 벽의 실제 접선 방향 길이와 물체 폭으로 유효 중심 범위를 계산하고 지역 중심을 그 범위 안에 놓는다. 모델 크기·방크기·관측·물체를 수정/삭제하지 않는다. 물체 자체가 벽보다 크면 `PHOTO_WALL_SPAN_EXCEEDED` typed 대상/동적 max/침범량을 내보낸다. 특정 사진/ID/고정 치수 분기 없음.

`room_items.validate_room_item_bounds`는 기존 SceneToolPlanError와 guard를 유지하면서 대상 owner/generated part/실제 pose/회전 footprint/바닥범위/침범량을 typed 진단에 보존한다. `site_tools`가 실제 expansion에서 owner map을 전달하므로 문자열 prefix 추측으로 semantic 대상을 바꾸지 않는다. 이로써 다른 경계 위반도 빈진단으로 숨기지 않는다.

`replay-final.json`: 같은21개 후보, semantic revision 불변, 바닥밖 물체0, 전체 compiler checks complete. 관측 기반 품질검사는 uncertain/수정issue0이지만 낮은 신뢰 관계·지지·실측·현재렌더는 미검증이다. **최초 실패가 실제 모델 전체 성공으로 바뀐 것은 아니다.**

## 회귀와 최초 시험 오류

- 라우팅18 PASS, 생성 승인14 PASS, room-items9 PASS. 새 라우팅 gateway 구성1, 범용 wall pose/oversize2, generated owner 진단1 회귀를 포함한다.
- provider 전체310/core 전체302/Web 전체443 PASS. Web 설정14/타입/빌드 PASS. 관련 수는 서로 겹치므로 합산 성공률로 쓰지 않는다. jsdom의 Canvas getContext 미구현 경고와 번들500kB 경고는 남아 있으며 이를 실제 화면/성능 PASS로 해석하지 않는다.
- 변경한 E2E Node 문법/추적 diff whitespace PASS. 기존 LF/CRLF 경고는 보존했다.
- 첫 라우팅 시험18개는 Windows sandbox 임시폴더 PermissionError로 ERROR였다. 설치/ACL 변경 없이 명시된 scoped execution 승인 후 같은 테스트18 PASS. 그 ERROR를 제품 PASS로 세지 않는다.
- 첫 core discovery는3 module import 경로 ERROR. 현재 프로세스 PYTHONPATH만 보완하여 재실행했다. 시스템 설정이나 테스트 본문을 우회 변경하지 않았다.
- 실제 모델 최초 실패/모든 응답/장부/승인/사진/화면을 삭제하거나 덮어쓰지 않았다. 수정 후 비교 증거는 새 파일에 보존했다.

## 정확한 잔여

1. 현재 수정된 host로 실제 후보를 일반 App에서 명시 재검사/재개하여 새 current Isaac 렌더→Flash critic→Lightning 수정→새 렌더→최종저장/SIM 인수를 끝내야 한다. 기존 실패 응답을 읽는 것은 무료지만 새 critic/patch HTTP는 현재 소비된 수를 포함하는 명시 범위에 결속해야 한다.
2. 새 두 번째 전체 조합 샘플은 미실행이다. 관측/설계 역할별2/2는 현재 조합 성공률의 근거로 대체하지 않는다.
3. 실제 사진의 지지·형상/규모·다른 방 일반화, Ultra model/decoder 대조와 미실행21개 비교, 도메인/편집/패키지/해커톤 세부요건과 실물 정합·자율·Loop/안전 인수는 이전대로 남는다.

로봇 연결·SSH·serial·실물 배포·모터·센서0, `whole_demo_pass=false`. 전원을 켜면 실물 데모 전체가 끝난다는 의미가 아니다.
