# TwinPulse 4시간 갱신 — 실제 원사진·저장계약·자연어 수정 인수

Baseline v1.0.474 · 2026-10-14 · 전체 **PARTIAL**. [실제 화면8장 단일 로컬 보고서](../../outputs/generation-ux-continued-20261014/report.html), [원 장부 감사](../../outputs/generation-ux-continued-20261014/audit-final-ui-routing.json), [판정·스트림·실행 ID](../../outputs/generation-ux-continued-20261014/evidence.json).

## 범위와 중단

사용자의 “이전에 승인한 내용은4시간 계속 승인, 반복 질문하지 말라”는 최신 답변을 현재 생성 UX의 명시 전송 범위 갱신으로 적용했다.05:30:02–09:30:02 KST, 원 ITM0018·공개2사진·파생 Isaac 렌더·시험 텍스트→기존 Nebius Flash V4.1/Super120B, 원누적USD10·작업24 HTTP/수정3회·새 UNKNOWN 보호 유지. 이전 fresh1개 후 잔여6개 중 이번 원사진3개를 시작해 잔여3개다. 다른 과거 실물/Cloud/설치/공개/Git 작업을 포괄 승인으로 재개하지 않았다.

일반 Start→Chrome New chat→실제 Attach→Send→SIM/Create로 시험했다. 일부 버튼은Enter로 실행했으며 API 직접 호출·고정 모델·상태 주입·시험 전용 서버0. 동일 Start를 실행 도구로 호출했으므로 Explorer 더블클릭은NOT_RUN이다. `setFiles`는 지정10초/tool20초와 달리565.5405초와1134.7943초 뒤 반환됐다. 이 자동화 계층 시간을 모델 지연으로 세지 않았다. OSCtrlV는NOT_RUN/browserClipboard CtrlV도timeout이다.

마지막 fresh 생성 시작 후 native Windows Chrome URL 검증이 신뢰 가능한 현재주소를 확정하지 못해 **Computer Use가 이번 턴 UI 조작을 중단**했다. 이후 CUA/Windows 입력·새 paid시험을 전부 중단했고 다른 제어 방식으로 우회하지 않았다. 이미 시작한 U3는기존 worker에서 종료/usage 수집했고 이후는읽기 감사·보고만 수행했다. 사용자 승인 부족으로 다시 기다리는 상황이 아니다. NativeIsaac 캡처도FrameArrived timeout으로패널 초록점/로그의 실제 시각인수는NOT_RUN이다.

## 실제 발견과 수정

1. **저장 계약 불일치:** A 원사진11응답은전부received/settled였으나 정책max_requests24를 core의옛≤12 검사로 거절해 `DRAFT_REFINEMENT_OUTCOME_UNKNOWN`이 됐다. 토큰 소진/remote UNKNOWN이아니었다. shared `generation_limits.py`의request1–32/repair0–8/stall1–4를provider/core가같이사용하고snapshot의carried_requests/carried_repairs·configuredstall을검증한다. prior.requests는합계, prior.repairs는최신누적값이며 current+carry 상한과 received/settled/unknown은엄격히검증한다. Legacy stall2, 원quality needs_revision/기하·물체보존 유지. 설정24/3/2/40k/300초/900초는변경하지않았다.
2. **명시 편집 오분류:** 실제 Change current의한국어“책상을이동해줘”를navigation으로먼저분기해 `SIM_START_REQUIRED`이발생했다(HTTP0). Stop/Status 우선은유지하되명시Add/Change는edit로처리한다. new mode navigation은기존별도경로검사/자동motion0이다.
3. **거짓 진행 안내:** 진행중draft없는checkpoint의Failure record문구와approximate saved뒤‘장면저장안함’문구를상태에맞게중립/저장미완성안내로변경했다. pending/current/authority/기하품질검사미변경.

UI6.1Sol high 보조는TwinViewport/ChatWorkspace+각tests4파일만소유했다. Astra xhigh는공통상한/누적카운터/UNKNOWN 차단좁은읽기검토에서새P1/P2없음을전달했다. 외부/Isaac/통합은main만순서대로수행했다. main 실제모델/effort는도구로확인·변경할수없었으므로요청설정을사용했다고주장하지않는다.

## 실제 원사진 세 번 — 서로 다른 소스

| 시도 | project / generation | 결과 |
|---|---|---|
| A/U1 | chat_mv751v7a_7ebeda7f /249afc5b-654d-4c5d-8673-64b0814a3d47 |11HTTP/26준비·표시/repair2 뒤OUTCOME_UNKNOWN FAIL·원마지막화면/원cp보존|
| B/U2 | chat_mv7628e2_bf5b3efb /1a9a784c-ee01-42d1-ba51-0d54ffd1d744 |11HTTP/207–208초/26준비·표시/repair2→geometry-valid approximate저장·현재화면기능PASS, photo needs_revision/REPAIR_STALLED|
| C/U3 | chat_mv77ecdg_6555e2e1 /4b73bc2e-cd56-4572-8f2f-8e42f796c4be |10HTTP/186.196초/repair0·파일상completed.27파라미터·마지막preview24/3대기·qualityuncertain/approximatepartial. UI제어중단뒤끝화면·시각품질NOT_RUN|

전체원사진3회는A/B/C다. 같은최종본3회성공/통계적벤치마크로합치지않는다. 최종C fresh1건의UI전체인수0. 이전v473텍스트1건도최종C텍스트PASS로합치지않는다. U3 마지막요약에대기3개의개별ID/사유가없고원inventory는저장되어있다. 최종표시/대기목록상세의사용자UI 정합을추후먼저확인해야한다.

원사진SHA `4fea13acb1152a742db047a0fd2797ea3850e4c42c016d6fbe8a5050b79933c2`,6,607,240bytes 불변. 원실패cp `e95f3d8f63ae4df9de85637c78e8e03418caca6d9cae0d7adc37d8deaa80dd83` 불변. A SHA80970c57…299e8, B55021fb2…07120, C339040d5…bfd4c는이름이명시된런타임소스closure이지전체설치SHA가아니다. disthash는각freeze에별도기록.

## 화면·응답성·품질

B 최초Flash 구조18.485초→room seed3.204초→첫연속브라우저표본43.471초이내decoded바닥확인(정확한firstpaint아님). 상세Flash43.344초동안바닥이이미나타났고최대6묶음/Repair전실제18표시24준비를캡처했다.

B 관측대기20초277표본은사진decode/DOM위치만확인(사진은화면밖). 묶음1→2 생성의실제사진보이는20초250표본은decode누락0·사진/버튼위치span약0.1px. `u2-repair`198표본20초는실제로완료뒤라Repair도중영상으로세지않는다. A388표본도FAILED뒤정적유지이며잘못된관찰selector의null은사진FAIL이아니다. 전생성/전체Repair의no-flicker는미검증.

원사진평가는production이아닌evaluator-only다. B의침대왼쪽·후면문은대략반영되지만긴오른쪽벽책상과선반·벽부착asset표현이원사진과크게다르다. PHOTO_RELATIVE_ORDER_CONTRADICTION(bookshelf약0.19m)/REPAIR_STALLED 보존.26/26은모델목록이므로정답물체수/사진품질PASS아니다. 치수는실측없으므로추정·미검증이며큰추정방만으로실패시키지않았다.

## 실제 자연어·Undo·복원

최종C에서같은한국어right0.2m요청이실제모델1HTTP로연결됐으나floor경계를넘어구체기하오류로적절히거절됐다. 원장면유지·기준완화0. 새left0.05m요청은모델1HTTP→proposal→실제Apply→ACK/디스크/current COMMITTED. 책상+종속노트북외침대와비대상기하불변. Apply execution `c100accfe1a14d2f991e6d92521d06cb`, revision480470a6…3e26. 일반UndoApply execution `2b63155db4d6480d8801d932b92023b3`, operation `edit_7e1a81cab04a4c46b387613ca14bb486`, revisionad53b02a…cf809.55compiler geometry components원기하exact/새revision/sourceDraft불변을기존allowlisted순수history replay로읽기검증했다. 이를26inventory물체와섞지않는다.

중간읽기감사가원sourceDraft만봐서currentedit를빠뜨렸고JSON문자열순서비교가거짓차이를냈다. 원감사는보존하고effectivehistory/geometry데이터비교및최종COMMITTED재감사로교정했다. 제품상태주입0. 일반재시작→실제sidebarU2→Reopen/View→새stage28cb…/current7FPS도확인. 편집/Undo뒤완전닫힌복원·Cancel/Resume·늦은결과확대시험은NOT_RUN.

## 비용·보조 회귀·남은 순서

새34HTTP 추정USD0.2201268/새held0. 과거보호3.4810599/UNKNOWN·held를포함한누적보호USD3.7011867/10, 원기간뒤신규0. 공급자청구서/잔액실측은아니다. 실물/OpenAI/Cloud/설치/공개/commit/push0. 소유런처정상종료2번후최종launch `41fc09fe6e134374b903c65a58782c17`/URL52089/owner4460/backend6296/enginewrapper21744 ready를읽기확인했으며강제종료0.

공통계약17/예산38/inventory5/scopequality15/Conversation64/UI2suite123/typebuild PASS는보조·중복합산0. 최초test method-tail 작성실수1ERROR/npm명령없음/감사import오기와중간비교오류는교정후재검사했다. 기존Provider4회귀FAIL은이번전체해결로승격하지않는다. largechunk경고유지. 보고서8image전체decode·offlineintegrity확인; HTML브라우저QA는fileURL정책/이번UI중단으로NOT_RUN·HTTP서버우회0.

다음순서:①WindowsURL신뢰확인/chooser지연정상지원복구→②최종C/U3 실제끝화면·27준비/24preview/3대기 상세확인·저장재열기→③남은fresh3건(혼합/새공개2)→④실제autoRepair완전회복·전구간flicker·Cancel/Resume/late→⑤편집뒤닫힌복원/프로젝트전환/nativeConnected로그/OSCtrlV/Explorer. 추가같은최종본3반복·final텍스트는원횟수를초기화하지않고별도잔여계획을확정한다. 현재4시간승인범위가유효하면같은데이터/목적지/잔여/원09:30:02기한으로승인반복질문하지않되기한후새호출은하지않는다.
