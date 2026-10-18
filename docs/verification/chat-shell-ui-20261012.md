# TwinPulse 대화 목록과 연결 표시 검증

2026-10-12 Baseline v1.0.461. 저장 대화를 시작 화면에 자동으로 펼치던 동작을 바꾸고, 왼쪽 대화·프로젝트 목록과 항상 보이는 Isaac 연결 표시, 작은 입력창을 적용했다. 기존 영어 기본 UI와 사용자 입력 언어를 유지한다. 이번 인수는 실제 Chrome와 일반 로컬 App/API의 UI 범위이며, 실제 Isaac 시작·주행이나 실물 LiDAR 전체 인수는 아니다.

## 적용 내용

- 저장된 대화가 있으면 홈에서 시작한다. 왼쪽 `Recent chats`와 `Projects`를 검색하고 클릭해 연다. 제목은 첫 사용자 메시지, 정렬은 마지막 메시지 시각을 사용한다. 원 대화·장면·첨부 파일은 삭제하지 않는다.
- `New chat`은 별도의 빈 프로젝트를 만든 뒤 기존 소유 launcher에 명시적으로 전환을 요청한다. 현재 대화 열기는 화면 선택만 바꾸며 재시작하지 않는다. 다른 프로젝트 전환은 기존 보안 세션 재시작 경로를 유지한다. 프로젝트 안의 여러 독립 대화나 Isaac hot-switch를 새로 구현한 것은 아니다.
- 이전 실패는 대화 기록에 남지만 시작 직후 현재 실패 배너로 재표시하지 않는다. 새 실행의 실패·연결 상실·현재 엔진 안전 오류는 계속 표시한다. 저장 질문·주행 승인은 복원하지 않는다.
- 상단 상태는 App 연결 확인, Isaac 시작 중과 경과 시간, 실제 broker 연결 관측, 시작 실패·중지를 구분한다. launcher ready만으로 연결이나 현재 3D 준비 완료를 주장하지 않는다.
- 입력창은 한 줄 높이에서 자동으로 커지고 textarea는 최대 140px까지다. 공통 label/footer 여백을 분리하고, 작업 선택은 작은 하단 도구로 옮겼다. 입력·이미지·IME·Enter/Shift+Enter와 기존 Send 잠금은 유지한다.
- 목록은 인증 완료 뒤에만 읽는다. 실제 브라우저에서 발견한 초기 목록 GET과 bootstrap의 순서 오류를 고쳤다. 새 대화 전환의 진행·미확정 상태도 표시하며 미확정 생성/전환은 자동으로 반복하지 않는다.

## 검증 결과

- 최종 프론트엔드 전체: **484 PASS**. [원 결과](../../outputs/chat-shell-ui-20261012/web-final-02.json).
- 프로젝트·대화 API/저장 회귀: **77 PASS, 1 SKIP, 14 subtests PASS**. [원 결과](../../outputs/chat-shell-ui-20261012/python-final.xml). SKIP을 PASS로 합산하지 않는다.
- TypeScript와 Vite 빌드 PASS. 최종 JS `index-DGA2wOHW.js` SHA256 `7d53162fefa9b0a98ad1fdf22bb55d1dd3638e3804aedd8d22d85a57abe57b30`, CSS `index-Bs1Id4W6.css` SHA256 `794385165e663ac8ffaf32d4b9ea05562e918439b3efa753183807ab5b98c706`.
- 실제 Chrome와 일반 인증 API의 `history`와 `empty` 두 흐름 PASS. [통합 원 결과](../../outputs/chat-shell-ui-20261012/browser-final/summary.json), [저장 대화](../../outputs/chat-shell-ui-20261012/browser-final/history/result.json), [새 입력](../../outputs/chat-shell-ui-20261012/browser-final/empty/result.json). 원 history bytes 불변, 외부/LLM/실물 요청 0, broker 명령 0, page error 0, 자체 API·Chrome 정상 종료.

| 화면 조건 | 빈 입력창 높이 | 메시지 읽기 영역 | 긴 입력 textarea |
|---|---:|---:|---:|
| 1920×1080 desktop | 102px | 약 820px | 최대 140px |
| 390×844 mobile | 102px | 약 486px | 최대 140px 정책 유지 |

Desktop의 긴 입력 때 composer 전체는 198px, 메시지 영역은 약 724px였다. Mobile의 긴 입력 높이를 별도 계측한 것은 아니다. 두 화면 모두 가로 넘침이 없었다. 측정 화면은 브라우저 콘텐츠 크기이며 첨부한 기존 화면과 동일 배율의 전후 비교 수치는 아니다.

## 실제 화면

아래는 실제 Chrome·App/API의 화면이다. 엔진 연결/시작 상태만 명시적으로 주입한 fixture이며 실제 Isaac 렌더나 실물 시험 결과로 해석하지 않는다.

![저장 대화를 접고 시작한 홈](../../outputs/chat-shell-ui-20261012/browser-final/history/02-clean-home.png)

![선택해서 연 대화와 작은 입력창](../../outputs/chat-shell-ui-20261012/browser-final/history/03b-desktop-reading.png)

![모바일 읽기 영역](../../outputs/chat-shell-ui-20261012/browser-final/empty/04-mobile.png)

## 실패 보존과 남은 범위

첫 로컬 회귀의 Windows sandbox 임시 폴더/자식 프로세스 오류는 제품 성공으로 계산하지 않았다. 정식 승인된 동일 로컬 시험으로 다시 실행했다. 첫 Web 44/50와 전체 480/483 실패 기록, browser-01/02의 초기 인증 순서 FAIL은 그대로 보존한다. 기존 영어 기본 UI 계약을 복구했고, 야간 변경으로 이미 구분된 `Transaction 3D frame`의 테스트 문구도 정확히 맞췄다. Canvas 없는 jsdom 경고와 Vite 큰 bundle 경고는 새 설치나 기준 완화로 숨기지 않았다.

사용자가 켜 둔 App·Isaac는 종료·재시작하지 않았다. 현재 창은 이전 JavaScript/Python 세션을 유지할 수 있으므로, 진행 중인 작업이 끝난 뒤 TwinPulse를 정상 재실행해야 변경된 시작 동작까지 적용된다. 실제 Isaac 연결·현재 3D·주행 재인수는 이번에 수행하지 않았으며 v460의 원 시험 결과를 새 UI source 전체 PASS로 승격하지 않는다. live LiDAR 자동 결과의 공통 commit/Undo 연결과 현장 안전·정합 인수는 여전히 남는다.
