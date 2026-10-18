# TwinPulse 사진 물체 용량과 이미지 붙여넣기 검증

2026-10-12 Baseline v1.0.463. 사진 분석 응답을 받자마자 실패하던 원인은 관측 확장 24개와 기존 장면 설계 32개의 용량 불일치, 그리고 확장 오류가 관측 수정 루프 밖에서 발생한 것이다. 두 경계를 수정하고 클립보드 이미지 입력을 보강했다. 현재 사진의 새 실제 모델·Isaac 전체 생성 성공은 아직 확인하지 않았다.

## 실제 실패 원인

프로젝트 `chat_mv4v170d_f88a6222`, 실행 ID `c27fa192e71b4df9829f93c55685e009`, operation `1c1ec876-660a-40a4-a6e1-36bf48623f60`의 관측은 Flash V4.1에서 18.672초 후 정상 `finish=stop`으로 도착했다. 출력 상한은 40,000이며 토큰 소진·timeout이 아니다. 원 실행은 observer 1회, repair 0회, 추정 USD0.005613/미확정 예약0으로 남는다. 원 실패를 새 성공으로 덮어쓰지 않았다.

원 응답은 24행, object/unknown 20행과 별도 구조·공간 metadata 4행이었다. 한 조명 그룹의 count6을 펼치면 장면 입력 항목은25개가 된다. 책 수량은 null이므로25가 실물 개수의 확정값은 아니다. 구형 확장은24에서 거절했고, 뒤쪽 설계기는 이미32를 지원했다. 또한 JSON 관측 검사에서는 passed로 기록한 뒤 루프 밖에서 확장 오류가 발생해 수정 기회를 쓰지 못했다.

## 수정한 경계

- 기존 설계 최대32를 공통 `scene_capacity.py`로 묶었다. raw observation의24행 제한은 유지하고 expanded object32, 별도 metadata24, host-only derived 최대56으로 분리했다. 개별 group count의 스키마·파서·프롬프트도 같은32 한도를 사용한다. 사진 SHA나 특정 가구 이름으로 분기하지 않는다.
- 원 관측과 그룹 개수는 보존한다. 그룹의 개별 위치·지지는 추정/미검증, null 개수와 관계·치수 불확실성은 그대로 남는다. 개수를 맞추려고 물체를 삭제하거나 외부 응답을 조용히 잘라내지 않는다. 확장 trace는1.2로 구분하며 기존 저장 증거는 변경하지 않는다.
- 새 Budgeted/legacy observer 검사는 JSON과 instance expansion을 같은 오류 경계에서 검사한다. 원 candidate와 실제 count/maximum을 기록해 기존 공유 repair·시간·요청·비용 상한 안에서 재검사한다. genuine visible object를 지우라는 지시는 없으며32 초과는 여전히 명시 한계다. 출력 소진/UNKNOWN/가격/물리/기하·사진 품질 기준은 유지한다.
- UI 오류에 안전한 정수 count/capacity/metadata 개수를 추가했다. 임의 문자열·비밀 값·bool·잘못된 수치·4096 초과 값은 고지에 내보내지 않는다.

## Ctrl V 입력

기존 구현은 textarea의 `clipboardData.files`만 보았다. 새 구현은 파일, items-only, MIME 없는 지원 이미지 파일명과 bytes가 포함된 HTML을 읽고, 입력창 밖의 page paste도 처리한다. 텍스트/기존 첨부를 보존하며 붙여넣기만으로 API를 호출하지 않는다. 다른 입력창·API 설정/진단 창·저장 대화 홈에서는 이미지 붙여넣기를 가로채지 않는다.

PNG/JPEG/WebP·한 메시지 한 이미지·10MiB 제한과 backend의 실제 파일 검사도 유지했다. HTML을 문서에 삽입하거나 실행하지 않는다. 원격/사설/blob image URL은 자동 다운로드하지 않고 `Copy image`, 주소가 아닌 이미지 복사 또는 파일 Attach를 안내한다. 문자열 URL을 사진 bytes로 간주하지 않는다. 다중 이미지·큰/잘못된 bytes는 거절하며 기존 입력을 보존한다.

## 검증 결과

- 영향 범위 Python **190 PASS +42 subtests PASS**: [최종 XML](../../outputs/photo-paste-capacity-20261012/python-focused-final-02.xml). 관측·공유 repair·legacy·semantic binding·한도·일반 승인/채팅 API를 포함한다.25/32개 수용·33개 초과 거절·원 candidate/count를 보존하는 observer repair1회→정상 compiler까지의 합성 흐름을 검사했다.
- 전체 Web **494 PASS**, TypeScript와 Vite 빌드 PASS: [최종 JSON](../../outputs/photo-paste-capacity-20261012/web-final-02.json). JS `index-D4s57UZR.js` SHA `915f594340982af84c7e6701c9c9953c5963c41309b5541555890d11794ce8ed`.
- 실패 때 받은 실제 관측의 읽기 전용 재생 PASS: [원 응답 재생](../../outputs/photo-paste-capacity-20261012/original-observer-replay-01.json).25개와 metadata4를 원 bytes 그대로 확장하고, 기존 설계의 one-seen-ref 계약에서도25개를 통과시켰다.12×12는 이 수량 검사의 명시 합성 설계 입력이며 사진 실측이나 제품 기본값이 아니다. **장면 geometry compile/새 외부 LLM/Isaac는 수행하지 않은 검사**다. 책 count null과 개별 위치·지지 미검증을 유지한다.
- 실제 Chrome/ordinary 인증 App/API의 page items-only paste→원 텍스트 보존→PNG 첨부→Send→한 질문/Create Twin→생성 완료 PASS: [결과](../../outputs/photo-paste-capacity-20261012/browser-final/summary.json). 전송 bytes가 원 시험 PNG와 동일·답변POST1·broker명령0·pageerror0·3개 audited provider fixture·외부/실물/새Isaac0·build manifest3개 SHA 검증·자체 API/Chrome 종료다. **OS 클립보드와 네이티브 키보드 Ctrl V를 직접 조작한 시험은 아니다.** 사용자의 실제 복사 표현을 특정 원인으로 단정하지 않는다.

## 확장 회귀의 남은 실패

전체 공급자/승인 확장 회귀는 **448 PASS/4 FAIL/+206 subtests PASS**로 PARTIAL이다: [전체 원 결과](../../outputs/photo-paste-capacity-20261012/python-full-final.xml). 아래4개는 이전24/48 용량·trace1.1·raw-only 관측 검사로 바꾼 독립 프로세스에서도 동일하게 실패했다: [이전 규칙 비교](../../outputs/photo-paste-capacity-20261012/capacity-prechange-differential.xml). 이는 이번 경계 변경과의 비교이며 전체 과거 source checkout/bisect는 아니다.

- `test_photo_semantic_review`: 원본 재컴파일 결과는 현재 compiler1.8인데 테스트는1.7을 요구한다.
- `test_rollback_revalidation`: None을 기대하지만 현재 미완성 초안 결과가 반환된다.
- `test_warehouse_semantics`의2개: 지원 관계 실패로 repair/중단을 기대하지만 현재 입력은2요청 후 결과가 반환된다.

해당 기존 기대값과 현재 compiler/미완성 초안 정책의 정합성은 추가 검토 대상이다. 이번에 테스트를 삭제하거나 판정·fixture를 바꾸어4개를 통과시키지 않았다. 기능 범위 PASS를 전체 제품 PASS로 승격하지 않는다.

## 실제 화면과 기록

아래는 시험 PNG·명시 모델 응답을 사용한 실제 Chrome/App/API 화면이다. 사용자 사진의 새 생성·현재 Isaac 프레임을 증명하지 않는다.

![입력창 밖 paste로 첨부되고 텍스트가 유지된 화면](../../outputs/photo-paste-capacity-20261012/browser-final/00-pasted-image.png)

![한 질문으로 사진 생성 시작](../../outputs/photo-paste-capacity-20261012/browser-final/01-single-choice.png)

최초 용량/루프2FAIL와 Web40PASS/1FAIL을 보존했다. 새 검사 fixture의 단일 물체 region 유지·추가 품질 응답 부족·multimodal feedback 리스트 파싱 문제, 전체 수집의 PYTHONPATH 오류·테스트 파일명 오타·필수 진단 필드 빠진 TypeScript fixture 실패도 따로 남겼다. 최종190/494에 실패를 합산하거나 감추지 않는다. canvas/bundle 경고는 설치나 기준 완화로 숨기지 않았다.

원 관측 파일 SHA `e88056c3291351d6d3c6ad7370387c6887c38536f58bd822e7493a8de4accffa`는 재생 전후와 마지막 읽기에서 동일했다. 원 실패·프로젝트/사진/금융 자료를 보존했고, 이번 새 실제 외부 API 비용은0이다. 실행 중 사용자 App/Isaac는 변경·종료하지 않았다. **정상 종료 후 TwinPulse를 다시 켜야 Python 변경까지 적용된다. 웹 새로고침만으로 용량 변경은 적용되지 않는다.**

다음은 실제 OS 복사→붙여넣기와 같은 사진의 명시 생성/재개를 실제 모델·현재 Isaac에서 인수하는 것이다. 우측3D stale·도착 뒤 lease 경고·위4개 정책 검사·live LiDAR 공통 commit/Undo와 현장 인수는 별도 잔여다.
