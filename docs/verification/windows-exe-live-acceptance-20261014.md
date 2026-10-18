# Windows EXE 실제 모델·사용자 인수 — v477

2026-10-14 · 전체 **PARTIAL**. [원사진과 실제 화면18장 단일 비공개 로컬 보고서](../../outputs/windows-exe-llm-20261014/report.html), [감사 수치/ID/원인 JSON](../../outputs/windows-exe-llm-20261014/report.json).

## 승인·동결·방법

사용자는 기존 Nebius USD10 승인을 계속 사용 가능하다고 명시했다. 기존 ITM0018/파생 렌더/시험 텍스트→Flash V4.1/Super120B 범위와 과거 UNKNOWN·중복 포함 원총상한을 유지한다. 이전09:30 기한을 다시 적용하거나 승인창을 되살리지 않는다. 추가USD10·OpenAI·다른 개인자료·실물·Cloud·공개 권한으로 확장하지 않았다.

첫07 시험에서 일반 한국어 “추정 크기6×5m의 서재를”의 조사를 host parser가 못 읽어 전송 전 실패했다. 범용 noun/particle·bounded qualifier·소유 대상/모호성 처리를 수정하고 동일 텍스트로08을 새 시험했다. 사진 좌표/침실 특례가 아니다. requested_size11/photo_layout22/semantic_binding42 보조PASS, semantic_review9PASS/기존 mock termination_code 누락1ERROR와 과거4FAIL은 보존했다. 잘못된 시험 파일명2건의 실행0은 PASS로 세지 않았다.

- Build `20261014T041314Z-dfcbd0c629cb`, 제품0.1.0, Windows x64 one-folder.
- Source SHA `dfcbd0c629cb74e6b28f0197cb7325e912e50084ce33df522a1ff65fb2eea0c3`.
- ZIP SHA `3ecf0b81ef8de2db14aac2cf8135fb29ad610e851df409561bbd220997ccffb7`.
- 원사진 SHA `4fea13acb1152a742db047a0fd2797ea3850e4c42c016d6fbe8a5050b79933c2`, 원파일6000×4000/6,607,240bytes.
- 일반 per-user 설치07→08 후 같은EXE·Chrome·현재Isaac·키 재입력0.1469설치파일 post-runtime SHA/size 일치.
- ordinary New chat→실제 입력/Attach→Send→SIM→Create, 실제 model feedback/Apply/Undo, Stop response/Continue, 메뉴Exit→동일EXE→sidebar/Reopen/View를 사용했다. 직접 제품API·고정 응답·상태 주입·저장 재사용을 fresh시험으로 대체하지 않았다.
- 실행 도구로 동일EXE를 호출했으므로 Explorer 더블클릭/nativeIsaac 패널/OS Ctrl+V는 NOT_RUN. 주 모델·effort를 도구로 확인할 수 없으며 기존 Astra xhigh 보조는 원인 읽기 전용 검토만 수행했다. 실제 Isaac/외부 호출은 주 작업자가 순서대로 실행했다.

## 결과

| 시험 | 실제 HTTP / 추정 USD | 기능 | 품질·미완성 |
| --- | --- | --- | --- |
| 07 최초 텍스트 | 0 / 0 | 전송 전 FAIL 보존 | 미시험 |
| 08 텍스트 | 3 / 0.0058785 | 5/5 준비·현재화면·저장/복원 PASS 범위 | 추정6×5m·개략 위치, 자동repair 미발생 |
| 08 자연어 수정 | 1 / 0.0058281 | 책상0.2m Apply/ACK/disk/current·Undo exact·cold reopen PASS | 다른 물체 기하 불변 |
| 08 사진 | 11 / 0.0688923 | 24/25 유효 부분 저장·현재/재열기 PASS | 1지원 대기·2repair stalled·사진품질 FAIL |
| 08 사진+텍스트 | 12 / 0.0970860 | 취소12/29→명시재개29준비 PASS 범위 | 3repair stalled·최종24표시5대기 FAIL; checkpoint-only 정적 복원 |

원사진25/29라는 모델 목록 수는 전체 사진 recall·위치/방향/지지·실측 품질 PASS가 아니다. 사진의2.8×7m 추정 치수만으로 실패를 판정하지 않았다. 실제 방/긴 책상/문/벽 지지의 배치가 아직 불완전하며 물체 삭제/방 축소/기하 기준 완화는 하지 않았다.

텍스트 active21.11초, 사진189.875초, 혼합 누적253.5초(취소 전96.89+재개156.61). 클릭→첫pixel 측정이나 평균/p95 사용자 벤치마크는 아니다. coarse observation/room HTTP는 사진14.422/3.109초, 혼합11.578/2.703초였다. 초기 구조가 상세 목록 전에 표시되는 실제 화면은 있으나 정확한 first-pixel 목표는 미인수다.

## 실행 ID와 복원

- 원07 실패: project `chat_mv7l6p0q_2d79a1c3`, generation `6235db3a-3b90-4b95-bda0-f4a43f9fee2c`.
- 08 text: `chat_mv7lm0q1_555ba371`, generation `eac02d05-d50a-48b5-8e54-c90307f3237a`.
- Apply transaction `a80701389f514d939d1a356e819a620d`, Undo `8f363bda2b51472696c4e6787c4f0596`. Undo 후 objects SHA `a4e57e83761de0cdcaa28346571d6c21789a2dc29342074112afb52912e9338b`가 cold reopen에도 동일하고 changed IDs는0. Overlay 편집이므로 원planSHA 불변만으로 판정하지 않는다.
- 08 photo: `chat_mv7m2alp_6629d301`, generation `b3736b2b-c146-42b8-9ae5-3724af441730`.
- 08 mixed: `chat_mv7ojciq_410416c2`, 원취소 `bb9d31ab-1457-44e1-8a2c-36ed9a28fb9b`, 명시재개 `62b33049-8430-449c-b461-be1571653f75`. 새로운 독립 사진 반복으로 세지 않는다.
- ordinary launch `6de47cb7040342138023c85711232127`→실제Exit/owner종료→`dd4b0c8d4afa468bb8590f8adde0273e`, 같은8765. 텍스트 새stage `8b48a58d…` 현재7FPS와 사진 새stage `24b4d3b5…` 현재6.9FPS를 확인했다. 사진부분 objects/sceneSHA도 cold reopen 그대로다. 혼합은 failed24/29 정적 복원이며 current/full-draft PASS가 아니다.

## 확인된 원인과 아직 수정하지 않은 문제

1. 사진 `toy_headboard_1` footprint0.15×0.15m에 선택된 `bed_1.headboard` 면은1.4×0.025m다. `SURFACE_CAPACITY_EXCEEDED/EMPTY_VALID_DOMAIN/nodes0`으로 탐색한도 부족이 아니다. 지원면 의미/부모 선택과 사진 위치 모순2개를 해결해야 한다.
2. 혼합의 품질 patch 이후 clock/chair/headboard shelf가 바닥 배치 실패했고 shelf 자식2개도 대기했다. 같은-region 검색29/512nodes·0.0698/2초에서 후보 소진, global 불가능성 증명은 아니다. 마지막 repair는 update3개+실제 변경 없는 scope8개라 `SEMANTIC_SCOPE_REQUIRES_CHANGED_UPDATE`로 거절됐다. 토큰/HTTP 한도 원인이 아니다.
3. `budgeted_pipeline.py:1187` 종료 복귀는 draft/scene_contract를 best362161…로 돌리지만 preview_plan/capture/수량은 실패ff20f5…에 남긴다. 원자 복구 또는 명시적인 이전 후보 표시가 필요한 실제 host 결함이다. 이번에는 원감사/기록만 했고 수정 완료로 표시하지 않았다.

Mixed `project.json.site_draft=null`, checkpoint compiled_plan없음/preview_plan있음이다. UI의 “Incomplete draft saved”는 재개 checkpoint 보존이지 확정 초안 저장이 아니다. sidebar empty와 사진의 “scene not accepted” 문구도 이를 더 정확히 구분해야 한다. 감사 스크립트가 initially site_draft를 가정해 오류난 것은 collector를 보완했고 제품 성공으로 승격하지 않았다.

## 비용·도구 한계·다음 순서

27실제응답 전부 HTTP200/finish stop/usage있음, 최대52.407초. 출력40k 부족이나300초 timeout은 없었다. 이번 추정USD0.1776849/새held0, 과거 원UNKNOWN·중복 포함 보호누적USD3.8788716/10. 기록 가격 기반 추정이지 공급자 invoice/실시간 잔액을 확인한 것이 아니다. 앱 금액/만료가격 gate는 부활하지 않았다.

첫 사진 첨부 도구가3468.5644초 뒤 반환했으나 다음 동일 원사진 Attach는3.3475초로 정상 완료했다. 모델·제품 생성시간에 합산하지 않았다. 큰 clipboard 쓰기는 timeout/kernel reset 후 첨부없음을 확인했고 불명 clipboard를 붙이지 않았다. long DOM20초 probe는3초 제어 타이머에서 실패; 유효한15표본1.525초에 원사진 decode loss0/21px 위치 이동만 측정했다. 전체 생성·repair flicker 해결은 NOT_RUN/UNQUALIFIED다. 도구 기본804px 화면에서는 Twin을 보이면 chat이 숨겨져 일반 Show/Hide로 조작했다. root launch PNG는 다른 context의 그림일 수 있어 최종사진 증거로 쓰지 않았고 실제 UI canvas를 확인했다.

단일 HTML18PNG+원사진은 오프라인 decode/참조 검사했다. 이전 report fileURL의 정책 차단은 우회하지 않았으며 브라우저 렌더 QA는 NOT_RUN이다. private 원사진/보고서/raw를 GitHub에 올리지 않았다.

다음 순서는 후보 원자 복구/저장 상태 표현 → 지원면 의미/부모·scope 계약 → 새 동결본의 동일 원사진3독립 반복·미사용2·전체repair/연속화면 및 live-model 늦은 결과/프로젝트 전환 race → native/새PC/서명/설치rollback/권리공개검토 → 별도 현장 승인 후 로봇/LiDAR다. 취소·재개의 이번 관찰을 모든 늦은 결과 경계 PASS로 일반화하지 않는다. 기존 source08 성적을 이후 source에 합치지 않는다. 현재 Nebius 승인은 잔여 내에서 계속 유효하다. 실물/Cloud/새설치/공개/commit/push0이며 전체 제품·해커톤 제출 완료가 아니다.
