# TwinPulse 생성 UX·수정 회복·일반 사용자 경로 — 부분 인수

Baseline v1.0.472 · 캠페인 시작 2026-10-13 · **전체 PARTIAL**.

## 실제 경로와 분모

일반 `Start-TwinPulse.cmd`를 실행 도구로 호출하고, 실제 Chrome의 New chat→Attach/file chooser→Send→Simulation only/Create Twin→Show Twin을 눌렀다. 테스트 전용 환경·제품 API 직접 호출·상태 주입·저장 후보를 새 생성으로 사용하는 대체는 하지 않았다. Explorer/CMD UI 실행은 Computer Use 지침상 금지돼 동일 진입 파일 실행 도구로 대체했으며, native Isaac panel/OS Ctrl+V는 미인수다.

- 원사진: `C:\Projects\TwinPulse\ITM0018.jpg`, 6,607,240bytes, SHA `4fea13acb1152a742db047a0fd2797ea3850e4c42c016d6fbe8a5050b79933c2`. 공개 Brisbane 사진과 합산하지 않는다.
- 기존 원실패 project `chat_mv6jng6j_e508a535`, execution `134b972cea9449f09da0279161753aae`, immutable checkpoint SHA `e95f3d8f63ae4df9de85637c78e8e03418caca6d9cae0d7adc37d8deaa80dd83` 불변. 로컬 replay는20표시/8대기·전체 packing 실패를 유지한다. 실제 모델 성적이 아니다.
- 새 생성 U1-a: project `chat_mv6m9577_fe5219af`, operation `685406ab-16a1-4a8c-9c56-89d7b76edd01`, generation `643f163c-a4f0-43ff-938b-0bd4dbfc9177`, root execution `42a0274a51ed42eebe5c6d5a8a88c9f3`. 5HTTP 뒤 objects500으로 FAIL. 초기 구조/바닥·원사진 화면은 실제로 표시했다.
- 잔여 재개 U1-b: 같은 project, operation `e2f00ec0-ef9d-4f2c-8832-14a6ab3ecda1`, generation `5915b579-415e-4c53-ba4c-dac5573a7c89`, root execution `effd09423a0c4e03a452a43a316ab466`. 3objects HTTP 수신 뒤 다음 HTTP 전 `NEEDS_REQUEST_BUDGET`. 18/25 파라미터,17표시,8대기. 동일 입력의 이어가기이며 독립 새 생성이 아니다.
- 개발 Extension source hot reload로 launch `c700d6c5dad0408d8ab16791e36d80aa`가 old runtime reference 오류로 종료한 시도도 보존한다. 이 시도 외부 추론0. 이후 source 수정 중 Kit Extension hot reload를 하지 않고 정상 종료·Start했다.
- normal cold reopen launch `1ab29bdce2bd4b7c9419222be4928a95`에서는 메타데이터만 복원되고 JPEG가 사라지는 FAIL을 추가 재현했다. 기존 render/checkpoint 연결 수정 뒤 최종 normal launch `3876e6d42a094b1683585ea7ace2a4b2`의 sidebar→Show Twin에서21:52:25 원 capture/revision의 정적 장면 복원을 확인했다. current frame/카메라 권한은 없으며 재생 이미지를 live로 표시하지 않았다.

## 구현한 범위

1. Extension의 bridge/필수 enable은 유지했다. 관리형 작은 연결 패널과 인증된 연결 상태·유한 작업 로그·실행 ID/마지막 오류를 추가했다. native panel 표시/펼침은 capture failure로 NOT_RUN이다.
2. generation_activity의 실제 단계/묶음/대상/원인과 prepared/rendered/pending을 분리했다. 원첨부 origin을 저장·복원하고, 실패/취소가 waiting 문구로 남는 것을 보완했다.
3. 마지막 decode canvas와 사진·설명·카메라 영역을 안정화했다. 새 원입력/초기 reload는 confirmed revision 전 옛 프레임을 채택하지 않고, 같은 입력의 재개는 마지막 이미지 유지. 카메라 current 검사 불변.
4. 작은 초기 구조 관측→추정 room seed→상세 관측→부모/중요도 우선6개 묶음. 상세 구조가 달라질 때 full 목록·ID를 보존한 새 revision recompile을 보조 회귀로 확인했다.
5. 반복 schema의 prompt copy를 정확한 refs로 축약하고 공급자 grammar는 기존 평면 형식을 유지했다. 직전 중복 진단을 줄이고 scope 요청과 실제 diff를 구분했다. 근거 있는 지지 후손/packing 이웃 재배치, 후보 분산과 한 번의 유한 재검색, exploratory/repeated/regressed/progress 분리를 추가했다. 물체 삭제·사진 좌표 하드코딩·기하 기준 완화는 하지 않았다.
6. optional repair3개 전체를 미리 예약해 상세 묶음이 일찍 멈추던 host 결함을 다음 repair1개+최종 review 예약으로 고쳤다. 실제 총12HTTP 상한/수정3회/공유 시간/이전 누적은 유지했다. 최종 수정본의 paid 재개 확인은 아직 없다.
7. cold JPEG 소실은 별도 sidecar가 아니라 기존 immutable GenerationStore.render/checkpoint를 재사용했다. request(outer/provider 구분), 후보·장면·계획/JPEG SHA·project 결속, bounded read·symlink/손상 거절, 지연 저장 negative cache 재검사, static-only 복원. 독립 검토 P2 세 건을 고쳤다.

## 시간·비용·승인 불일치

초기 구조21.984s, room3.485s, 상세 관측40.704s, inventory14.063s. 엔진 준비/브라우저 첫 paint는 이 합과 같다고 주장하지 않는다. 원115.7s 전체 관측과 동일조건 반복 비교도 아니다. Attach chooser tool2879.7515s 지연 및 native helper 승인 timeout은 모델 지연에서 제외했다.

이번 실제8HTTP reported usage 추정 **USD0.0294411**, HTTP500 사용량 없는1건 보수적 hold **USD0.1146432**. 이전 agent42HTTP/.2361993, 추가 사용자 원사진 노출과 원 UNKNOWN3까지 중복 없이 포함한 보호 합계 **USD3.4700964 / 총USD10**. 청구서 확인이 아니다. 보류를 환급/0으로 바꾸지 않는다.

원 파일 기한은21:50:38KST인데 U1-b3HTTP는21:51:43 이후 시작했다. 최신 사용자 요청이 작업을 지시했지만 새 기간을 기록하지 않았으므로 옛 기간 내 호출로 소급하지 않는다. 이 불일치를 원자료에 남기고 추가 유료 호출은 중단했다.24HTTP 확대는 auto-review가 거절해 UI 설정을12로 복구했으며, 원사진/공개사진2/파생렌더/텍스트→동일 Nebius, 총USD10 무초기화·최대24HTTP/수정3회·확인 후2시간 범위의 사용자 답변을 대기 중이다. 제품 USD1/가격 승인창을 다시 넣은 것이 아니다.

## 판정과 정확한 잔여

새 생성의 최종본 필수 분모는 **0/7 실행**이다. 개발 U1-a1개와 잔여 재개 U1-b를 최종본 독립 반복3회나 전체 생성 성공으로 합치지 않는다. 부분 화면에서 주요 책상이 미완성이므로 사진 품질 PASS가 아니다. 실측 없는 치수는 추정이다.

- 최종본 원사진 독립3회, text/mixed/미사용 사진2: NOT_RUN.
- fresh 자연 발생 자동 repair 회복: NOT_EXERCISED. 원실패 비파괴 UI 재개 보조도 아직 미실행.
- 생성 중 깜빡임 연속 관찰/첫 paint/UX 목표 시간: NOT_RUN 또는 NOT_MEASURED. 최종 still로 no-flicker를 주장하지 않는다.
- 최종본 실제 자연어 수정/Apply/Undo/Save·취소/late/재개 전체: NOT_RUN. 관련 로컬 회귀 및 이전 버전 성적과 구분.
- 마지막 정적 장면 cold restore: 실제 FAIL→수정→해당 제한 범위 PASS. 원사진 썸네일 직접 URL의 컨텍스트 헤더 누락도 실제 발견해 인증 Blob 경로로 고쳤다. 최신 bundle의 일반 저장 대화/Open/ShowTwin에서 채팅 첨부와 Twin 참고사진 모두 실제512×341 디코드, 마지막21:52:25 정적 capture·8대기·카메라비활성 확인. 새 생성 품질 인수가 아니다.
- native Isaac 연결 패널/log expansion, OS Ctrl+V/Explorer doubleclick: NOT_RUN. 설치/실물/Cloud/공개/commit/push0.

보조 검사: budget38,scope15,preview12,inventory5,schema6,chat+product67,UI119,imageAPI+session61,static restore+viewport+render50,type/build PASS. 서로 겹친 회귀를 합산하지 않는다. Python interpreter/PIL 경로 및 fixture 단계/예약 기대값 오류도 실제 사용자 모델 실패와 분리해 기록했다. 전 provider4FAIL을 전체 PASS로 승격하지 않는다. 최종 번들 `index-iWMQUE0m.js`/CSS`index-DrdqjbNM.css`를 실제 재열기에서 사용했다.

보고서 HTML은7개 내장 이미지 decode/검증·외부 이미지0·단일파일 약9.46MiB로 오프라인 검사했다. Browser Use가 `file:` URL을 정책상 차단해 보고서 자체의 브라우저 시각 렌더는 NOT_RUN이며 우회하지 않았다. App의 실제 화면 시험과 보고서 시각 QA를 구분한다.

실제 화면·모든8HTTP/실행 ID·SHA·비용·실패/미검증은 [단일 로컬 HTML](../../outputs/generation-ux-user-20261013/report.html), [기계 감사 JSON](../../outputs/generation-ux-user-20261013/audit.json)에 있다. 원사진/개인 prompt/raw는 공개하지 않는다.
