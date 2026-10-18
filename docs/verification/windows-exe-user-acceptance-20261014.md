# Windows EXE 실제 사용자 인수 — v476

후속 최신 기록: [v477 실제 Flash/Super·텍스트/사진/혼합·수정/Undo/취소재개 인수](windows-exe-live-acceptance-20261014.md). 최종 설치 후보는08이며 기존 Nebius USD10 승인은 지속 유효하다. 이 파일의07·추론0·승인대기 문구는 당시 이력이다.

2026-10-14 · **로컬 EXE 실행/복원 PASS 범위, 전체 PARTIAL**.
[실제 화면을 포함한 단일 로컬 HTML](../../outputs/windows-exe-20261014/report.html),
[시험/빌드/실행 원자료](../../outputs/windows-exe-20261014/report.json).

## 납품물과 범위

- 최종 `artifacts/windows-exe/candidate-07/dist/TwinPulse/TwinPulse.exe` 및 전체 one-folder ZIP. EXE만 분리하면 안 된다.
- ZIP: `TwinPulse-Windows-x64-0.1.0-20261014T025305Z-39ffe005d47c.zip`.
- ZIP SHA256 `8dc31e9b5ff48cbdee0183511547fad4dac574c489fab49f870e6b489ae3fcfe`.
- source manifest SHA256 `39ffe005d47c345a7ae346ee5395d25783533493f8562271ee0de14382b0e923`, 파일1,469. 기존 HEAD5c42899… + dirty snapshot이며 GitHub에 올린 Release가 아니다.
- 실제 설치: `%LOCALAPPDATA%\TwinPulse\installed\releases\20261014T025305Z-39ffe005d47c\TwinPulse.exe`.
- Python3.12.10·Pillow12.3.0·빌드 PyInstaller6.22.3, Windows10 x64/현장 Isaac6.0.1-rc.7. 사용자 전용 `.build-venv` 설치만 명시 승인했고 기존 App/Isaac Python과 전역 PATH는 변경하지 않았다. wheel8개 버전/SHA 잠금, 공식 PyPI wheelhouse 보존.

## 구현

기존 Python/React/Extension을 유지한 실제 frozen launcher/backend와 명시 helper 역할, 외부 Isaac용 같은 소스 payload, resource/state/key 분리를 구현했다. backend/robot-readiness/robot-prepare만 allowlist이며 임의 모델 Python/shell 실행은 없다. 실제 실물 helper 실행은 하지 않았다.

기본 preferred8765를 저장하며 New chat/재열기로 서버를 늘리지 않는다. lock의 executable/Windows creationFILETIME와 기존 소유자 재열기를 검증한다. 외부 DLL 검색/Python 환경을 자식 Isaac 경계에서 분리한다. 파일/해시 무결성을 **외부 payload import 전 compiled bootstrap**에서 검사하며 현재 개발 checkout으로 fallback하지 않는다.

인증된 runtime shutdown API와 UI 메뉴를 기존 Origin/CSRF/context/현재 작업 검사에 연결했다. 정상 종료는 소유 Isaac 정지 요청→backend stop→lock 정리이며 늦은 작업과 불명 상태의 잠금은 풀지 않는다. 앱 화면은 실제 엔진 준비 전에 나타나며 연결/실패 경과를 표시한다. Isaac 부재도 backend와 대화/설정/진단을 유지한다.

버전별 staging 검증/immutable 설치/active pointer 원자 전환과 이전 포인터 보존을 구현했다. actual06→07 갱신·기존 사용자 자료 사용 확인. 시작 메뉴·바탕화면 아이콘, schema 호환 rollback, 제거 및 설치 중단 복구 전체는 미완료다.

## 실제 시험과 실패

Computer Use **브라우저 실제 클릭/키**로 일반 EXE→New chat3→기존 사진 대화→Reopen→View draft→current Isaac→앱 탭 전체 닫기→EXE 재열기→메뉴Exit/완전재시작3회를 수행했다. 제품 API 직접 호출/fixture/상태 주입으로 인수를 대체하지 않았다. 실행 도구로 같은 EXE를 호출했으므로 Explorer 더블클릭/nativeIsaac 패널/OS붙여넣기는NOT_RUN이다.

최종07 launch `9ba5e146de0341869ac3001ebb288584`의 중복 EXE2회와 모든 task 탭 닫힌 뒤 재열기는 backend18648/engine11796/owner18964/8765를 그대로 사용했다. 실제 새 대화는 chat_mv7iqsga_2ad798d7, chat_mv7irv35_ea52b213, chat_mv7isin5_80ed1662이다. 원사진 U3를 실제 current6.8–6.9FPS/stage4488f5f6…으로 복원했고24/27·3pending·추정 치수·motion미검증을 보존했다. 원사진SHA4fea13ac…93c2 불변. Reopen으로 대화 메시지가 추가되므로 전체 사용자 파일 byte불변이라고 주장하지 않는다.

실제 메뉴 종료/재시작 `9ba5→5b4b805c…→08f098f7…→1695ed2a2860426f8936d777a7c95fc9`는 같은8765/새owner·인증/키재입력0, 이전3실행의소유자식/lock 정리 확인. 마지막 owner6700/backend20128/engine20344에서도 일반 Reopen/View→current6.8–6.9FPS/stagedf0162e7… 및 실제3D장면을확인해사용자에게남겼다. 마지막 실행의 탭 생성은 시작후4.520초, 실제 engine ready는30.870초였다. 이는 첫 pixel/p50/p95/clean-cold benchmark가 아니며 최초 화면3초목표는 미인수다.

원 빌드01 Path문자열식/02 cp949 metadata/04 nonexistent corepyproject 실패를 보존·수정했다. 후보03/05의 성공은 최종07에 합산하지 않는다. 후보06 엔진부재 종료에서 자식 cleanup 뒤 failure-return1/nativeerror owner4604가 남는 결함을 확인했다. 명시 diagnostics Exit0 분기로 수정했고 최종07 부정시험 owner6492의 실제 종료를 확인했다. 이전06 owner는 강제종료하지 않았으며 native 오류창의 직접 닫기 인수는 불가했다.

실제 브라우저에서 엔진 준비 전 disabledNewchat press와804px 좁은 레이아웃의 Twin표시후숨겨진View버튼 선택은 driver실패로 남겼다. 최신 화면을 읽고 연결 완료/Hide→View→Show 정상 액션으로 해결했으며 제품 gate/geometry검사를 완화하지 않았다. 실제 UI 선택 흐름에 필요한 상태 관찰을 생략하지 않는다.

보조 최종 회귀: process31, windows contract5, install3, startup48, initialstate30 PASS. UI보조 App/api/ChatWorkspace160/type/Vite PASS는 단위·형식 검증이다. 패키지 현재1,469개 post-runtime hash검사 PASS; 첫 보조감사PYTHONPATH부족 실패는수정하고 재실행했다. 이전 unrelated provider4FAIL은 없애지 않았다.

## 비용·미검증·다음 순서

단일 HTML은 실제 화면12장을 내장하며 외부 이미지 의존성이 없다. HTML/그림 decode는 오프라인검사했고 첫검사 shell quoting실패는교정했다. 보고서fileURL의브라우저시각QA는허용protocol정책에서차단되어NOT_RUN이다. 이를HTTP서버나다른browser로우회하지않았다. 실제App8765 인수와보고서fileURL 제한을구분한다.

이번 신규 추론HTTP0/추정USD0, 이전 보호 USD3.7011867/10 및 UNKNOWN 보존. 이전 시험 기간09:30:02KST가 끝났으며 EXE fresh3개/원사진/렌더/텍스트→Nebius/원누적10/승인후2시간의 명시 갱신 질문은 한 번만 보냈고 답변 미수신이다. 승인된 프로젝트 빌드 도구 설치와 새 inference 권한을 혼동하지 않았다. 앱 금액 승인창을 되살리지 않았다.

1. 유효한 외부 기간이 확인되면 **최종 EXE** 실제 text/image/mixed→자연어Apply/Undo/닫힌재열기→취소/재개를 인수한다. 저장 재사용으로 새 생성 성적을 대신하지 않는다.
2. 원사진의 긴 오른쪽 책상/선반·벽부착 관계·3pending·전체Repair 회복과 미사용 사진2장을 검증한다. 사진 품질/전체 생성 중 깜빡임 검증은 미완료다.
3. native Extension 초록점/로그·Explorer/OSCtrlV·새 Windows/GPU/Isaac 환경 인수.
4. 활성 포인터 아이콘/데이터호환rollback/설치중단복구/제거, cleancheckout 빌드·권리/개인경로 검토·서명/공개 준비.

실물/Cloud/시스템설치/공개/commit/push0. 주 모델·effort는 도구로 확인할 수 없으며 UI6.1Solhigh와독립Astraxhigh 보조 두 명의 지정만 확인했다. localcandidate 실행가능과 최종제품/해커톤 제출 완료는 다르다.
