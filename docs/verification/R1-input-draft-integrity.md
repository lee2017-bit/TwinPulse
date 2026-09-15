# R1 — 입력·치수·생성 기록 정합성 검증

- 기준일: 2026-09-16 KST
- 기준 root: `C:\Users\jaewo\Documents\TwinPulse`
- 범위: App migration playbook Step 1만. R2 stage identity와 React/backend는 미착수.
- 판정: **R1 로컬 자동 acceptance PASS**. 실제 유료 multimodal provider 재호출과 visible UI 시각 검수는 NOT RUN.

## 변경과 판단

- M2-D `ground_truth`에서 sidecar 치수를 파생한다. 실제 `start_position_m`/`goal_position_m`의 3D 좌표를 사용한다. 도면 PNG는 manifest에 고정된 원본 sha256과 일치하며, sidecar는 provider 입력에 독립 제약으로 전달한다. 이 값이 LLM의 이미지 추론 성공을 뜻하지는 않는다.
- `InputRevision`은 이미지 bytes, prompt, 입력 종류, 측정 제약, profile, 비밀정보를 제외한 생성 설정을 해시한다. 요청 전 이미지 bytes와 revision을 로컬에 snapshot한다. 같은 파일명에서 내용만 바뀌어도 다른 revision이다.
- 새 입력은 진행 중 생성을 supersede한다. 결과는 ticket와 현재 입력 digest를 모두 비교한 뒤에만 current draft가 된다. 이전 record/stage는 남지만 최신 입력 Build는 차단한다. 이전 draft 검토는 별도 명시 버튼이다.
- v2 record에는 input/plan/expanded-bundle/measurement digest, validator version, 검증/미검증 치수 상태, 검증 값 수와 오류 목록을 담는 receipt가 있다. 성공 record의 오류 목록은 비어 있어야 한다. 저장·복원·Build 직전에 plan을 재실행하고 제약/receipt를 재검증한다. 해시는 서명이나 원본 인증이 아니다.
- v1 record는 읽되 `legacy-unverified`로 Build 차단한다. 명시적 rebind는 현재 선택 입력에 plan을 다시 검증하지만, 과거 이미지 bytes의 일치를 입증하지 못함을 UI에 알린다. 저장 후에도 `origin_status=legacy_rebound`가 남아 새 생성 draft와 구별된다.

## 실행 증거

`C:\isaacsim\python.bat -B`로 실행했다. R1 통합 테스트의 임시 파일은 승인된 작업 폴더를 사용했다.

- `python -m unittest discover -s tests/integration -p test_r1_workflow.py`: **9/9 PASS**. 실제 generator PNG hash/sidecar loader, 정답 plan PASS, 랙 높이·goal 좌표 오답 FAIL, core/provider 측정 parity, 입력 변형, receipt 변조·unknown version, late result ticket/digest, v1 gate, immutable snapshot, plan/bundle alias normalization 확인.
- `python -m unittest discover -s packages/twinpulse_core/tests -p test_*.py`: **24/24 PASS**.
- `python -m unittest discover -s packages/twinpulse_provider/tests -p test_*.py`: **13/13 PASS**.
- `python scripts/verify_r1_extension.py`: **PASS**. 로컬 Isaac Sim 6.0.1 headless에서 Extension enable, prompt 변경 시 generation epoch supersede, stale Build 거부 및 stage mutation 없음, previous draft review 창 열기 확인. API 요청 없음. 첫 실행의 smoke script 참조로 lifetime warning이 있었으나 참조 해제 후 재실행에는 없었고 종료 코드는 0이다.

## 남은 경계

- 실제 multimodal provider 응답, 취소 경쟁, 전체 visible UI 렌더링은 재시험하지 않았다. 핵심 ticket/digest 함수와 headless legacy UI gate는 검증했지만 모든 UI interaction을 보장하지 않는다.
- 사진의 실제 치수 추론 정확도와 M2-D 29/29, 임의 장면 품질은 여전히 미검증이다.
- R2는 **새 scene hash와 현재 실제 stage의 일치, Run 안전 latch**를 별도로 검증해야 한다. R1 receipt는 그 기능을 대신하지 않는다.
- 이 단계에서 새 시스템 dependency 설치, API 과금, GitHub push, 실물 구동을 하지 않았다.
