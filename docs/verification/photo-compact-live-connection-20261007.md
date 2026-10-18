# 실제 사진 모델 결과의 제품·Isaac 연결 — 2026-10-07 / v320

## 결론

후속 “그래 해봐” 승인으로 원래 침실 사진을 기존 Gemma/Nemotron에 전송했다. 외부 요청2회, 관측/사진1.1 계획 first-valid·repair0·검토24개 필수 슬롯/actual 관측ID 계약 PASS. 사람 검토 inventory를 사용하는 assisted 검사이며 독립 사진 인식률24/24가 아니다.

최초 live 전체 연결은 **FAIL/Build·Run0**. 모델의 추정10×12m 격자 한도 오류를 수정한 뒤 정확한 실제 두 응답을 원본 request/schema/model/raw와 대조하여 재사용, 실제 Chrome/chat/API/save/Isaac/PhysX Build·도착·목표·Stop·reload·reset·종료후파일 재열기 PASS. **이전 실제 모델 결과의 오프라인 재검증**이지 수정 후 새 live 추론은 아니다. 수작업 scene/가짜 응답으로 대체하지 않았다.

**사진 fidelity 미완료:** 10×12m는 실측이 아니고 사진 우측 침대가 좌측 후방 proxy로 배치되며 지지/부착 미복원. 24항목 보존과 사진 충실도는 별도 인수. production_default=false·whole_demo_ready=false·H5/H6/C3–C6 PARTIAL·physical NOT_RUN. 로봇/배포/센서/모터/설치/시스템설정/commit/push/새 에이전트0·예약PAUSED 유지.

## 실제 호출과 비용

P01 SHA `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`. 이 침실 사진만 전송, UI/중국어 화면 사진 전송0.

| 단계 | 실제 요청 ID | 결과/시간 | 사용량 / 추정 USD |
|---|---|---|---|
| Gemma | `9f6887d8ef074e768859a5b7a6406a59` | HTTP200/stop/유효·34.406s | prompt435+completion933 / .0003234 |
| Nemotron | `419e911eb31b4ec9a25f469f22b77ce4` | HTTP200/stop/유효·38.562s | prompt2307+completion7400 / .00191442 |

job약73.831s, plan28 calls=바닥1+벽3+inventory24. completion7400은 reasoning 포함8000cap에 가까워 반복 안정성을 증명하지 않는다. 최신1.1 actual sample1개. 추가 추정USD .00223782; campaign53/60·unknown예약 포함USD .09737678·pending0·이전unknown2 예약 보존/청구미확인. 이번 최대3회 중2사용, 남은1회는 불필요하게 사용하지 않았다. replay추가호출0.

## 원인·수정

- 10×12m/.10m=101×121=12221셀>10000. planner가 직선 검사 전 `GRID_BUDGET_EXCEEDED`, preview가 모든ValueError를 삼켜512후보 `SIM_PREVIEW_SEARCH_BUDGET_EXCEEDED`로 가렸다. 원본live-r1 FAIL 보존.
- SIM make_plan만 명시적 allow_direct_over_grid_budget: 동일 .10m/.22m footprint/full floor·box·disc·unknown 검사된 직선만 grid 없이 허용. segment 검사≤10000. 우회는 여전히 grid budget 거절. 물리planner 기본/grid/확장/waypoint cap 유지, floor축소/장애물삭제/무검사경로/실물권한0. preview는 NoBoundedPath 후보만 흡수하고 계약 오류/large-grid 원인을 전달. 직렬화/canonical/hash/정지guard 유지.
- 평가전용 ExactAuditedResponses는 완료ledger/HTTP200/stop/model/raw SHA·길이와 정확한request/schema SHA 대조. 취소·변조·다른입력·추가요청 거절, network fallback 없음. 제품/browser 기본에 replay를 추가한 것이 아니다.

## 최종 검증

- core302/29.449s·provider57/1.000s·관련통합93/29.623s PASS(imported중복 포함). 기존 SIM/chat/소품해시/host와 기본grid거절·SIMdirect·막힘/바닥/box/disc/unknown/segmentcap·변조/다른요청/재사용소진 검사.
- 최종 `artifacts/agent-reliability-20261007/compact-chat-isaac-exact-r2/result.json` PASS. Q1전generation/Build/Run0→동일actual응답/plan→Build1/current3D92frames→PhysX도착 .0397109794m≤.04m/sim4.4167s→침대목표Run→접힌화면 채팅Stop/pause위치유지→reload재실행/승인복원0→reset비물리preview/telemetry unavailable. Build/run/run/pause/reset succeeded·pageerrors0.
- backend 종료후 ProjectStore.load 동일24항목/plan/input/scene 재열기 PASS. source/원본live result/raw/input archive/ledger SHA 불변, owned backend/engine=false.
- 원본과최종 plan `f80fc30e6032519d3b33c3014ec1b21709dfe38a65ef2f2690620e238da8f816`, InputRevision `2b2393c11597f89589f77ae9d1c1f66bb97d5e451c1275f74298cd068387f656`, scene `7cf44fba944a3c84b8402af0b48f86bfbf2ad04353ba3b429e053a5bedc6e384`.
- 중간 exact-r1은 동일plan/geometry PASS이나 fixture metadata 때문에 input/scene이 달랐다. 원래 generation_settings/hash 조건으로r2 최종 인수; r1을전체identity 근거로 쓰지 않는다. 모든실패/중간/raw 보존.
- Web제품source/build 변경0·기존built UI actual검사. 이번Web전체unit/build 실행주장 없음. git diff --check와주요dirty/untracked whitespace/compile 검사PASS.

## 정확한 잔여

1. actual관측side/region·지지/부착/바닥hazard 관계·미실측크기가정의검토. floor독립proxy/과도한room확대를 최종사진복원으로 채택하지 않는다.
2. 품질계약 개선/오프라인검증 후 승인범위 actual반복 성공률/시간/품질. sample1은안정성증명아님.
3. 실험기본채택·최종package/전체SIM·REAL. large-floor 막힌경로는현재budget거절.
4. 실물초기화/odom·scan·TF/방정합/주행·정지/배터리·특이상태는별도현장승인 인수. 전원만켜면전체데모완료를보장하지 않는다.

비용없는 exact replay(표시를제거하지않음):

```text
python scripts/verify_chat_sim_journey.py <새 output> --case image --compact-photo --replay-live-run artifacts/agent-reliability-20261007/compact-chat-isaac-live-r1 --replay-campaign artifacts/agent-reliability-20261007/campaign.json --live-photo <P01 원본 사진>
```
