# TwinPulse 라이선스·출처 기록 적용 검증 — v422

## 결론과 승인 범위

2026-10-11 사용자가 표준 Apache-2.0을 확정했다. TwinPulse 자체 코드의 라이선스/출처/헤더와 기존 패키지·배포 메타데이터를 실제 반영하고 로컬 검증했다. **라이선스 선택 보류는 해소했다.** 전체 데모나 공개 패키지의 모든 권리/개인정보 점검이 완료된 것은 아니다. 새 LLM 호출, Cloud, 설치, SSH/serial/모터, 배포, 공개 전환, commit/push는 실행하지 않았다.

작성자/권리자: **Jaewon Lee / 이재원**. 원본: https://github.com/lee2017-bit/TwinPulse. 저작권 연도 2026은 최초 commit `57b0ec0`(2026-09-13)과 사용자 선언에 근거한다. 조회한 Git 이력의 작성자는 Jaewon Lee(14개 commit)였으며 다른 작성자 고지를 삭제하지 않았다. 이력만으로 모든 외부 권리를 소유한다고 판단하지 않는다.

## 적용 파일

- 루트 `LICENSE`: [Apache 공식 원문](https://www.apache.org/licenses/LICENSE-2.0.txt) 그대로. Appendix의 예시 placeholder도 바꾸지 않았다. SHA256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.
- 루트 `NOTICE`: 프로젝트명, 2026 저작권자, 원본 URL의 짧은 사실 고지. 별도 광고/열람/AI/소스공개 의무 없음.
- `CITATION.cff`: CFF 1.2.0, 프로젝트/작성자/원본/Apache 식별자. JSON은 YAML 1.2의 유효한 부분집합이다. 공개 출시 version/date/DOI는 넣지 않았다.
- `README.md`, `AGENTS.md`, `docs/LICENSING.md`, `THIRD_PARTY_NOTICES.md`: 실제 코드 재사용의 라이선스 조건과 독립 구현의 **자발적** 설계 참고 크레딧을 구분. 세 가지 실제 기여 표현을 유지하고 가짜 참고/단순 열람 기여 주장을 요구하지 않는다.
- 루트/`packages/twinpulse_app`/`packages/twinpulse_provider`의 `pyproject.toml`, 웹 `package.json`, extension `config/extension.toml`: 저작권자/원본/라이선스 일치. Python은 기존 `setuptools>=68` 호환 `license={file="LICENSE"}` 및 명시 `license-files` 사용, 새 빌드 시스템/설치 없음. `private:true`와 기존 버전/의존성/런타임 설정 유지.
- LICENSE/NOTICE 사본: 루트, App, Provider, robot-safety, extension, 웹 소스, 웹 `public/`의 **7쌍**. 모든 LICENSE/NOTICE 사본은 각각 루트와 동일하다. `.gitattributes`는 이 자체 고지 파일에만 LF를 고정하여 Windows 재체크아웃에서 원문 바이트가 바뀌지 않게 한다.
- 기존 자체 소스 **831개**(첫 829개 + 최종 확장자 점검에서 찾은 CMakeLists.txt 2개)에 형식에 맞는 SPDX 저작권/Apache-2.0/원본 URL 주석을 삽입. shebang/인코딩/BOM/CRLF/DOCTYPE/TS reference, 기존 docstring/future import를 보존했다. [첫 829개 전후 SHA](../../outputs/licensing-20261011/header-applied.json), [CMake 2개 가역 삽입](../../outputs/licensing-20261011/header-cmake-applied.json). 신규 자체 라이선스 도구/테스트도 같은 고지를 갖는다.
- `scripts/generate_engine_ts.py`의 생성 헤더에도 같은 고지를 넣어 재생성 시 사라지지 않게 함. `scripts/robot_source_identity.py`의 기존 아카이브에 LICENSE/NOTICE 및 inert 생성 initializer의 주석 포함. 실행 제어/모터/안전 알고리즘 변경 없음.
- `scripts/build_offline_release.ps1`: 기존 패키지에 루트 법적 문서, extension/robot 고지, 웹 dist 고지를 포함. 기존 upstream ROBOTIS LICENSE/source.json 복사 유지.
- `apps/twinpulse-web/THIRD_PARTY_LICENSES.txt`, `public/` 사본 및 현재 `dist/` 법적 파일: 설치된 React 19.3.0/React DOM 19.3.0/Scheduler 0.28.0 MIT 원문, Vite 8.3.0의 전체 upstream LICENSE(삽입 build helper에 관한 출처)를 보존. Vite 문서에 포함된 다른 고지를 전부 실제 앱 구성요소라고 주장하지 않는다. 화면 광고/워터마크 없음.
- `scripts/apply_license_headers.py`, `scripts/verify_license_policy.py`, `tests/integration/test_license_policy.py`: 라이선스 작업만의 가역 변경/메타데이터/기존 배포 검증. 제품 런타임과 분리. 공개 checkout용 테스트는 로컬 outputs/개인 증거에 의존하지 않는다.
- Baseline/Memory/progress/Physical AI 계획의 현황을 v422로 동기화. 기존 보류/실패 기록은 삭제하지 않고 선택 이전 이력으로 구분했다.

## 검증 결과

| 확인 | 실제 결과 / 범위 |
| --- | --- |
| 원문·사본·NOTICE | 공식 원문 SHA와 LICENSE 7곳 바이트 일치; NOTICE 7곳 일치 |
| CFF | 동결한 [공식 CFF 1.2.0 schema](https://raw.githubusercontent.com/citation-file-format/citation-file-format/1.2.0/schema.json)의 실제 채운 필드/참조/형식/enum 검증 PASS. 새 YAML/JSON-schema 라이브러리 설치 없이 JSON/YAML 부분집합 파싱 및 해당 keyword 검사. 모든 가능한 CFF 기능을 구현한 범용 validator라고 주장하지 않음 |
| 메타데이터 | Python TOML 3개/웹 JSON/Kit TOML의 라이선스·작성자·원본 일치 PASS; 기존 빌드 backend 및 private 플래그 보존 |
| 기계적 헤더 | 831개 삽입을 제거하면 기존 바이트 SHA로 정확히 복원; Python AST 동일. 최종 검사 대상 834개(신규 도구/테스트 포함)에 고지 누락 없음. CMake 명령 본문 바이트 그대로, 새 CMake/ROS 빌드는 하지 않음 |
| 문법/생성 | Python 631개 compile, PowerShell 11개 parser, TS typecheck PASS. 생성 engine contract `--check` PASS |
| 로컬 회귀 | 라이선스9 + 기존 source identity2 + 기존 packaged gate9 = **20개 PASS**. 최종 보고 SHA의 변수 오염 수정 후 라이선스9 재확인 PASS(겹치는 반복, 29개 독립 시험이 아님) |
| 기존 웹 회귀 | **47 files / 449 tests PASS**, jsdom Canvas 미구현 경고 유지; 새 라이브러리 설치로 감추지 않음. 실제 GPU/실물 인수 아님 |
| Python 배포 | 기존 설치된 setuptools84 backend 직접 사용, 격리 사본에서 Core/App/Provider 각각 wheel+sdist = **6개 PASS**. 각 LICENSE/NOTICE 원문 포함·wheel License-File/Repository 확인. [아카이브별 SHA](../../outputs/licensing-20261011/verification-accepted.json) |
| 웹 빌드 | `web-dist-final` 새 로컬 Vite 빌드 PASS, LICENSE/NOTICE/외부 고지 포함. 외부 고지 파일 추가 전후 JS/CSS 해시 동일, 큰 chunk 경고 유지 |
| 기존 offline 배포 | `tp-licensing-v422-complete` **696 files / 25,323,636 bytes**, 모든 manifest SHA/bytes 및 법적 경로14 확인 PASS. `REUSED_EXISTING_DIST_NOT_REBUILT`인 기존 dist 패키지 검증과 별도 새 웹 빌드는 구분. Pillow wheel의 `pillow-12.3.0.dist-info/licenses/LICENSE` 보존. 설치/배포/전체 제품 acceptance 아님 |

최종 배포 근거는 [complete-final.json](../../outputs/licensing-20261011/complete-final.json)이다. `verification-accepted.json`은 Python 6개 아카이브 검사 근거다. `accepted-final.json`은 CMake 2개를 추가하기 전의 유효한 증분 기록이다. 새 법적 안내/헤더 때문에 소스 및 향후 로봇 배포 hash가 달라진다. **기존 raw/동결 benchmark/stop 기록의 해시를 새 코드로 바꾸거나 통과를 소급 적용하지 않았다.** 다음 실제 배포에서는 기존 fresh identity/boot/stop 검증을 따른다.

## 검증 중 발견한 문제와 처리

1. 최초 패키지 시험의 `python -m build`는 repo의 `build/` namespace 때문에 탐색에서 발견된 것처럼 보였지만 실행 가능한 frontend가 없었다. 설치하지 않고 이미 선언/설치된 setuptools backend를 직접 사용했다. 원 실패 로그 `outputs/licensing-20261011/package-builds/core/build.log` 보존.
2. Windows sandbox Temp 권한 오류로 setuptools 임시 sdist와 Vite spawn이 실패했다. 별도 승인된 로컬 테스트 권한으로 새 격리 출력에서 확인; ACL/시스템 설정 변경 없음. `verification-packages/core/build.log`와 도구 실패 기록 보존.
3. 최초 Vite 상대 출력 경로를 잘못 계산했다. 이번 작업이 만든 정확히 6개 파일임을 확인 후 canonical licensing output으로 이동; 다른 파일 삭제/이동 없음. 최종은 올바른 `../../outputs/licensing-20261011/web-dist-final`을 사용했다.
4. JS 원문 검사 도구의 기본 cp949 decode, 상대/절대 경로 보고 오류를 UTF-8/resolve로 수정했다. 오류를 제품/모델 실패로 분류하지 않았다.
5. 압축 웹 번들에서 React 라이선스 comment가 제거되는 실제 누락 확인. 댓글이 남았다고 테스트를 완화하지 않고 upstream 원문을 별도 배포 파일로 포함하고 일치 검증했다.
6. 추가 browser-license 검사에서 지역 변수 재사용 때문에 중간 `final-distribution-verification.json`의 **official_license_sha256 필드에 Vite SHA가 잘못 기록**됐다. 원 LICENSE의 SHA/내용은 변경되지 않았다. 해당 중간 보고서는 최종 근거로 사용하지 않는다. 변수 분리·SHA assertion 회귀 후 `accepted-final.json`에 공식 Apache SHA를 정확히 기록했다. 중간 파일을 덮어쓰지 않고 보존했다.
7. setuptools의 legacy license table/classifier deprecation 및 sdist README 미동봉 경고가 있었다. 실제 6개 법적 고지는 통과했다. 이번 범위를 넘는 새 backend/배포 시스템 전환은 하지 않았다.

## 충돌·미확인 및 공개 전 잔여

루트에 기존 LICENSE/NOTICE/COPYING/CITATION은 없었으며 확인한 자체 코드에 상충하는 고지나 다른 작성자 고지를 발견하지 않았다. 기존 `turtlebot3-90a68bd.patch`의 upstream context, 외부 라이브러리/자산/사진·fixture manifests 및 saved outputs는 자체 저작권 헤더 대상에서 제외했다.

- 원 ROBOTIS LICENSE/source.json/patch의 현재 SHA는 각각 `ac8793d277f1a08231d10e1b2ebaabb0598bd5561cfc21f97648656b416d901e`, `b933a1743954410acfe3e685fa1843610404fc1fe24a331e1020a50bcb7ca359`, `fa8fa60231daf3d90f691c1e4fc88016657e56b635cddf347d6d03fe1d5446c2`. 원본 고지를 변경하지 않았다.
- `artifacts/robot-models/burger-isaac/usd/` 변환물과 **Isaac runtime/asset 재배포** 조건을 본 작업만으로 전부 법률 검토했다고 보증하지 않는다. 현재 기록된 nominal source/라이선스와 원문은 유지; 공개 바이너리 번들 결정 전 확인한다.
- Python/Node의 **전체 전이 의존성**에 대한 공개 배포 권리 점검은 아직 전수 완료가 아니다. 현재 browser 4개 original notice와 offline Pillow wheel은 직접 확인했다. 설치된 개발/test 도구까지 전부 앱에 포함됐다고 주장하지 않는다.
- `fixtures/m2c/warehouse_images.json` 등 기록된 CC BY-SA/공개 사진과 적합한 파생물은 각 원 조건을 유지해야 한다. 개인 침실/도면/raw/모든 생성 장면·리포트에 Apache가 자동 적용되거나 공개 허락이 생기지 않는다. 실제 공개 목록별 권리/개인정보 검토는 잔여다.
- 인용 파일·AI 안내가 모든 AI의 준수나 영구적인 출처 보존을 보장하지 않는다. 단순 열람/아이디어/학습 포함만으로 모든 후속 산출물에 새 의무를 만들지 않는다.

정책적 구분: Apache가 적용되는 코드 재사용에서는 원 라이선스의 조건을 따른다. 독립 구현의 실질적 설계 참고는 **자발적 출처 요청**이며 추가 라이선스 조건이 아니다. [정책 전문](../LICENSING.md), [외부 고지](../../THIRD_PARTY_NOTICES.md).
