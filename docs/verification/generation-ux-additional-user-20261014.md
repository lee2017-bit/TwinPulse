# TwinPulse 추가 실제 사용자 인수 — PARTIAL

Baseline v1.0.473 · 2026-10-14. 기존 v472의 실패/UNKNOWN/원사진/체크포인트는 보존했다.

## 실제 성과와 분모

- 일반 Start 동일파일 재실행은 기존 launch `3876e6d42a094b1683585ea7ace2a4b2`·포트61097·Isaac을 재사용했다. 소유 엔진 정상 종료 후 같은 Start의 최종 launch `c24ed6d3d3e840d8b307eff023eac898`·포트54497을 시작했다. Explorer 더블클릭/네이티브 Isaac 패널/OS Ctrl+V는 NOT_RUN.
- 개발 코호트A 실제 텍스트 생성은 Nemotron3 HTTP/4개 물체·현재 Isaac 표시 PASS. project `chat_mv6u95uu_dfef0b5e`, generation `dbe58445-d65e-4636-ab31-56ae4bc6628d`, operation `ed672690-7691-43f9-898c-01b2207d3714`, execution `2699bde572964190bec43c448b3b7f67`. room3.282s/structure4.359s/batch5.516s는 외부 HTTP 시간이며 첫 paint/전체 앱 시간과 같다고 주장하지 않는다.
- 실제 자연어 의자0.2m 이동은 Nemotron feedback7.015s/1HTTP→Apply→엔진ACK·디스크저장·현재프레임 PASS. feedback execution `648f0f3ebfed412f88a99fe6542943ec`, Apply execution `c27172d572174057a533dfd1bb2365e0`, operation `edit_1345ac6ea877470aac4c01e8830f1709`.
- 일반 Undo Apply execution `9fae973eb3654f7aa14138c917454733`, operation `edit_1c527efb6c1042d292c67ae43e4e9813`, COMMITTED/현재 프레임 확인. 이는 자연어 편집 회복이지 자동 Repair 회복이 아니다.
- 최종 코호트B 일반 재시작→실제 저장 대화→Reopen saved scene→View current Twin→새 stage `dd3cf1a4-889b-4acf-8c31-f123b7cef85f`·현재7FPS 표시 PASS. 일부 버튼은 실제 키보드Enter로 실행했다. 저장 재열기는 새 모델 추론이 아니다.
- **최종본 독립 새 생성0/7**. A 텍스트1개와 편집1개를 B의 사진 반복3개·자동 Repair 성적으로 합치지 않는다. 원사진/혼합/다른사진2의 실제 외부생성0, 취소/잔여재개·연속flicker·첫paint·사진품질·native패널 미실행이다.

## 실제 발견·수정

완료 job에 stale validating stage와 미완성 체크포인트/Continue unfinished 안내가 남았다. UI completed 상태를 우선하고, parameters_complete/draft_saved/pending0에만 실제 저장 완료 문구를 표시했다. 부분/blocked/pending·사진품질 미검증은 유지한다. 최종본 저장 재열기에서 완료문구를 실제 확인했다.

모델 제안 대기·엔진 갱신 대기 행이 결과 후에도 pending으로 남았다. conversation_service는 해당 operation의 assistant pending 행만 terminal 상태로 정리하고 edit 시작 안내에 operation ID를 결속했다. 다른 작업/프로젝트·ID 없는 옛 행은 임의 변경하지 않는다. Python71/UI115/typebuild PASS는 보조이며 이 상태정리의 새 실제 모델 재시험은 아직 없다. 최초 임시파일 권한 오류/Vite spawn EPERM은 허용된 로컬 escalation 재실행과 구분한다.

좁은 실제 창791×683에서 Twin은 반응형 전체 영역이며 대화/입력이 접힌다. 자동화 마우스 동작과 가려진 버튼을 동일 성공으로 주장하지 않고 키보드Enter의 실제 결과를 확인했다. 좌우 동시관찰·연속 화면 인수는 남는다. 단위시험 결과로 이를 PASS로 바꾸지 않는다.

## 승인·도구 지연·비용

사용자는 원사진 ITM0018·공개사진2·파생렌더·텍스트→같은 Nebius Flash/Super, 새생성최대7·재개/수정·작업당24HTTP/수정3, 기존 총USD10·02:26KST까지를 명시 재승인했다. 제품 금액/가격 승인창은 되살리지 않았다.

처음 private Send는 보안검토가 포괄 답변을 기간·데이터 승인과 연결하지 못해 전송 전 차단했다. 이후 명시 승인을 받았지만 실제 Attach/filechooser 도구가 **14,666.4395초(약4시간4분)** 동안 반환되지 않았다. timeout_ms30000/chooser10000을 지정해도 막지 못했다. 앞선 도구 지연1,210.9351초도 있다. 이는 모델 생성시간이 아니다. 반환 시05:15KST였으므로 원02:26기한 후 사진 Send/Create를 하지 않았다. 외부 전송 우회/소급 승인/기한후추론0.

추가 실제4HTTP reported usage 추정USD0.0109635/새held0. 원 보호3.4700964 포함 **USD3.4810599/10**. 이전 HTTP500 보수hold·UNKNOWN3을 환급/초기화하지 않았다. 청구서·잔액 확인은 아니다. 원사진 SHA `4fea13acb1152a742db047a0fd2797ea3850e4c42c016d6fbe8a5050b79933c2` 및 원실패cp SHA `e95f3d8f63ae4df9de85637c78e8e03418caca6d9cae0d7adc37d8deaa80dd83` 불변.

## 정확한 잔여

1. 파일선택 도구 장시간 대기 해결/실제 브라우저 이미지 키보드 붙여넣기 기능 별도 검증. 제품 API 직접 호출·상태주입·합성 paste로 대체하지 않는다.
2. 유효한 새 기간에서 최종 동결본 같은 원사진3회·글+사진·미사용사진2·텍스트 새 생성. 입력/전송 SHA, 주요 위치·방향·지지·누락·중복과 추정치수를 별도 평가.
3. 실제 자동 Repair 회복, 생성 중 연속 화면, 취소·잔여 재개·늦은 결과 격리, 새 pending 상태정리 fresh 회귀.
4. native Isaac Connected/로그 펼침, OS Ctrl+V/Explorer 시작 별도 인수.

[단일 로컬 실제 화면 보고서](../../outputs/generation-ux-user-20261014/report.html) · [모든HTTP·비용·소스SHA](../../outputs/generation-ux-user-20261014/audit.json) · [거래·분모·도구지연](../../outputs/generation-ux-user-20261014/evidence.json). HTML3내장이미지 오프라인decode 검사, file URL 시각QA는 정책상NOT_RUN/우회0. 로봇/Cloud/설치/공개/commit/push0. 일반54497 앱의 저장 텍스트 Twin 현재화면을 켜두었다.
