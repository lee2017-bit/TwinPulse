# 현재 채팅방 조사 결과의 3D 표시 검증

현재 채팅방에서 조사한 보정 revision을 기존 App과 Isaac 우측 화면에 연결했다. 저장 보고서의 원본 방, 보정 ledger, 현재 프로젝트가 일치할 때만 표시하며 과거 위치와 스캔은 주행 권한이 아니다. C4 전체 및 실물 데모 인수는 미완료다.

## 구현 범위

- 임무 승인 전에 현재 방의 정확한 SceneRevision과 input digest를 캡처해 보고서에 저장한다. JSON 배열로 정규화하되 기존 canonical hash와 v1/v2 계약은 바꾸지 않는다.
- additive `current_inspection_visual_v1` descriptor는 보고서 SHA와 임무 ID만 받는다. 브라우저 경로·pose·변환·실행 코드를 받지 않는다. 성공한 SURVEY_ONLY, cleanup 성공, 원본 scene/input/objects, 최신 보정 ledger 및 fresh revalidation 기록을 검사한다. 변경·손상·실패 시 역사 방으로 fallback하지 않는다.
- 센서 기록 root와 프로젝트 root를 별도로 전달한다. 기본 raw 저장 위치는 유지하고 런처가 신뢰된 host 설정을 backend와 engine에 동일하게 전달한다. engine은 실행 직전 현재 저장 프로젝트를 독립 재검사한다.
- 조사 완료를 이번 채팅에서 승인한 경우 표시용 Build를 한 번 요청한다. 저장 이력 복원과 새로고침은 Build/Run/주행을 실행하지 않으며 명시적 표시 버튼을 제공한다. 응답 유실은 자동 재전송하지 않는다. 엔진 identity 변경·실패 receipt·snapshot 미확인은 오류로 표시한다.
- 기존 고정 Burger 자산을 Physics=none으로 표시한다. 조사 결과는 top 시점으로 열고 벽에 가려지는 스캔 주석만 표시 높이를 조정한다. 원본 XY/scan/방 형상과 pose는 변경하지 않는다. `annotationHeightIsPresentationOnly=true`, `currentPoseAvailable=false`와 역사 후보 표식을 USD에도 남긴다.
- 기존 owned-root transaction을 재사용한다. 시각 조합 오류 시 정확한 이전 USD와 적용 revision을 복구하고 외부 prim은 보존한다. 저장 USD 재열기에서도 현재 위치나 실행 승인으로 승격하지 않는다.

## 실행 결과

- Python 관련 회귀133개, 322.405s PASS. 실행 시작 시 시험 모듈이 가져온 TestCase까지 unittest가 발견해 기존 채팅/ColdStart/API 시험 일부가 중복 포함됐다. 이후 모듈 import로 바꾸어 새 파일은 고유4개 시험만 발견한다. 133을 고유 신규 시험 수로 사용하지 않는다.
- 후속 저장/API/엔진 계약3개 1.340s, split-root/기존 런처/SIM 계약41개 2.757s, 표시 top preset1개 1.171s PASS. 앞 시험과 일부 중복이다. 공유 합성 조사 loop의 current-room 보고서·derived scene 재열기 단독 시험도21.023s PASS였다.
- 최종 Web41파일313개 24.01s PASS, TypeScript/build PASS. 산출물은 `index-w3Xm7RyM.js`와 `index-DjLK5Ycj.css`; 500kB bundle 경고는 보존된 성능 잔여다.
- 실제 Chrome/App/API/Isaac 저장 표시 최종 [결과](../../artifacts/runs/chat-inspection-saved-browser-20261006-r5/verification.json): 한 Build의 정확한 derived revision과 연속 viewport, reload 비재실행, 모바일 Twin 접기/저장 버튼/가로 overflow 없음 PASS. source22개와 Web4개 해시는 전후 및 최종 소스와 일치한다. 캡처를 직접 확인해 벽에 가려지던 시점과 스캔 주석 가림을 수정했다.
- 같은 실행의 **별도 host 1회 파일 캡처 진단은 FAIL / viewport_missing**이다. 실제 latest-only 연속 viewport와 브라우저 캡처는 통과했지만 이 host 판정을 전체 PASS로 바꾸지 않는다. [원본 host 관측](../../artifacts/runs/chat-inspection-saved-browser-20261006-r5/verification.json)의 capture/host.status를 보존한다.
- 최종 실제 Isaac lower 검사 [결과](../../artifacts/runs/chat-inspection-current-isaac-20261006-r4/verification.json): 공유 합성 조사→fit→보정→fresh revalidation→저장, 현재 보정 방/Burger4 meshes/Physics schema0/스캔 점 개수·표시높이, 오류 주입 뒤 정확한 USD rollback, 저장 재열기·외부 prim·원본 JSON 불변 PASS. source18개 전후/최종 해시 일치. Physics Run은 실행하지 않았다.
- 모든 시험 소유 프로세스를 종료했다. 실제 로봇 접속·배포·센서/모터·유료 호출·새 설치·commit/push·새 agent는 0이다.

## 실패와 수정 이력

1. 최초 단위 시험에서 tuple/list 저장 경계와 시험 owner 참조 오류를 수정했다. Scene의 JSON 정규화는 실제 보고서 재열기 결속에도 필요했다. 최초 Web 시험의 matcher 및 질문 메시지 fixture 누락도 수정했다.
2. 브라우저 첫 실행은 표시 버튼이 잠겼다. 보고서와 프로젝트가 같은 root라고 가정한 결함을 실제 host의 분리 root로 재현·수정하고 split-root 회귀를 추가했다. 해당 [실패 기록](../../artifacts/runs/chat-inspection-saved-browser-20261006-r1/verification.json)은 보존한다.
3. 두 번째 실행은 데스크톱 표시/reload 통과 후 모바일에서 열린 Twin overlay를 접지 않아 시험이 실패했다. 명시적 Hide Twin을 수행하도록 인수 절차를 수정했다. [기록](../../artifacts/runs/chat-inspection-saved-browser-20261006-r2/verification.json)의 초기 isaac=NOT_RUN 값은 당시 시험 도구의 초기값이며 실제 host/Build가 실행되지 않았다는 뜻이 아니다. 이후 도구는 runtime 시작 상태를 별도 기록한다.
4. 중간 r3/r4 브라우저 통과 뒤 직접 캡처 검토에서 벽 가림을 발견해 표시만 개선했다. r1–r4 browser 및 r1–r3 lower 자료는 당시 소스 이력이며 최종 인수 자료는 browser r5/lower r4다. 기존 v295의 Python77 중 원격 goal deadline 실패도 지우지 않는다.

## 검증 경계와 다음 순서

입력 센서/방은 output-reactive 합성 자료이며 새 사진 해석이나 실측 정합을 증명하지 않는다. 실제 런타임 인수는 저장 표시·복구·재열기 범위다. fresh 채팅 완료의 자동 표시 arming은 React/API 회귀로 확인했으며 실물 조사부터 끝까지의 인수는 아니다.

1. 원격 full-fit/map 원본의 반출·재열기와 현재방 연결을 마무리한다. 로봇 없이 계약/저장 경로를 구현할 수 있다.
2. 현재 센서 위치 기반 semantic goal → 실제 SIM 경로 시연 → 정확한 revision/digest Confirm → robot-local 임무 연결을 진행한다. 저장 조사 terminal pose를 현재 위치로 사용하지 않는다.
3. C5 persistent bounded-leg TaskLoop와 C6 통합 인수를 진행한다. 별도 host 파일 캡처의 초기 viewport 실패도 독립 재현 대상으로 남긴다.
4. C3 target binary/profile/full moving field-suite와 별도 승인된 실제 현장 인수는 잔여다. 회사 PC·최종 배포 패키지·실물 데모 전체 성공을 보장하지 않는다.

Whole readiness=false, C4 PARTIAL. 기존 scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s·실물 임무 잠금·원본/dirty/과거 실패를 보존하고 heartbeat는 PAUSED다.
