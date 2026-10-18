# 단계별 생성 수정 루프와 호출 로그 검증

2026-10-09 KST · Baseline v1.0.373 · 제품 수정 및 오프라인 회귀 완료 · 실제 모델 회복 미검증

[v372 점검](ordinary-staged-request-audit-20261009.md)에서 확인한 오류 경로, 직전 후보 누락, 관측 목록 계약, 부분 개선 판정, 호출 목록 절단과 수정 표시를 기존 제품 경로에서 수정했다. 새 외부 LLM 요청, 사진 전송, 로봇 및 Isaac 실행은 0이다. 기존 실제 실패를 성공으로 바꾸거나 전체 데모 완료로 기록하지 않는다.

## 구현 결과

| 항목 | 현재 동작 | 범위와 제한 |
| --- | --- | --- |
| 오류 경로 | structure의 grounding 어댑터 오류를 실제 응답 필드 `$.inventory`로 변환 | 다른 계약의 `objects` 경로는 보존 |
| 수정 문맥 | 원 요청에 직전 파싱된 후보 JSON, 직전 호출 ID, 최신 검사 보고서와 남은 오류 대상을 전달 | 과거 오류를 계속 누적하지 않음. provider reasoning 및 깨진 JSON 원문은 전달하지 않음 |
| 관측 목록 | 매 요청의 object/unknown 관측 ID와 범주를 `required_inventory`로 전달 | 침실 전용 목록·사진 해시·고정 가구수·방 크기를 추가하지 않음 |
| 출처 우선순위 | 사진에 보이는 물체를 글에서도 언급했다면 동일 물체의 관측 ID를 사용하도록 명시 | 추가 텍스트 전용 물체는 같은 범주라도 user 출처로 허용. 개별 ID 누락은 host 의미검사로 거절 |
| 응답 형식 | 관측수와 한 source의 최대 참조수3에서 inventory 최소 길이를 계산 | 필요한 최소 조건일 뿐 전체 coverage를 보장하지 않음. 텍스트 빈방은 최소0으로 유효 |
| 개선 판정 | code/path에 더해 missing_ids와 invalid_ids의 정확한 대상을 비교 | 누락14→7→1은 개선. 순서·summary만 변경, 동일 실패, 오류 교환과 재등장은 개선이 아님 |
| 호출 이력 | 정책 최대32개까지 API와 접힌 Tool details에 호출 ID, 역할, 수신 상태, 검증 결과 표시 | total/truncated를 별도 표시. 요청·후보·사진·키는 공개 API에 넣지 않음 |
| 현재 오류 | 수정 및 최종 검사 성공 시 현재 오류를 제거 | 과거 실패는 개별 호출과 로컬 증거에 그대로 남음 |

사진 observer 수정은 원본 user 메시지의 이미지1개를 유지하고 최신 feedback 텍스트1개만 추가한다. system/user 순서도 유지한다. structure와 object batch, 최종 typed patch는 기존 Site2.2·라이브러리·compiler 경로를 그대로 사용한다. 단계별 수정이 공유 예산을 새로 얻거나 실패한 후보를 강제로 통과시키지 않는다.

## 실행 ID로 디버깅하는 방법

일반 staged generation의 기존 로컬 `provider-evidence` 경로에서 같은 attempt ID로 다음을 찾는다.

- `dispatches/<attempt_id>.json`: HTTP 전 저장한 요청 해시·스키마 해시·모델·역할·실행 ID와 span ID, 민감정보를 제거한 실제 송신 body. OpenAI 단계는 wire 변환 이후 body다.
- `<attempt_id>.json`: 기존 수신 원문 증거, 수신 및 비용 정산 정보. 원 파일은 덮어쓰지 않는다.
- `validations/<attempt_id>-<stage>.json`: 파싱된 후보, 검증 성공/실패, 코드·상세 원인·계약 보고서, 직전 수정 문맥.
- `validations/<attempt_id>-repair_decision.json`: 남은 대상·후보 해시와 개선 여부. 중단되는 수정도 판단을 먼저 저장한다.
- `validations/<attempt_id>-semantic_compile.json`: 최종 compiler 검사와 후보·patch 이력. HTTP200이나 patch 형식 통과와 최종 장면 통과를 구분한다.

직전 후보는 다음 요청의 `previous_candidate`에서, 수정 후 후보는 해당 validation에서 대조한다. `previous_attempt_id`로 앞뒤 호출을 연결하고 같은 execution ID로 기존 오류 그래프와 병목 측정을 확인한다. 인증 헤더는 저장하지 않으며 등록키·Bearer·data URL 이미지 바이트는 제거한다. 요청/검증 텍스트는 각각262144자 이내이며 초과 시 truncated 표시가 남는다. 사진과 프롬프트에서 추출된 비민감 내용은 로컬 개발 증거이므로 공용 DTO·export에는 포함하지 않는다.

필수 검증 기록 저장에 실패하면 `VALIDATION_EVIDENCE_FAILED`로 추가 모델 요청을 중단한다. 원래 의미검사 오류를 보존하고 별도 storage trace에 `validation_record_failed`를 남긴다. 저장 장애를 성공이나 자동 재시도로 처리하지 않는다. 기존 unknown 비용 예약과 output-limit 즉시 중단 정책도 유지한다.

## 직접 검증한 결과

- Provider 전체 **210 tests PASS**. 새 관련10 tests가 포함되며 별도 실행 수를 합산하지 않는다.
- App 승인·stage routing·기존 신뢰성·execution diagnostics 통합 **181 tests PASS**.
- 마지막 현재 오류 정리 후 승인·설정·provider trace·신뢰성 관련 **55 tests 재검증 PASS**. 위 통합 회귀와 중복이며 별도 합산하지 않는다.
- Web 전체 **47 files / 437 tests PASS**. ChatWorkspace 관련27 tests 포함. 타입 검사와 Vite build PASS.
- 저장된 v371 실제 실패 응답4개를 최신 코드에 무네트워크 재생했다. 같은 잘못된 답은 `REPAIR_STALLED`로 끝났으며 공개 이력4개, 수정 플래그 `[false,false,true,true]`, 직전 후보/ID·inventory 오류 경로를 확인했다. 보호한 입력·사진·원응답·장부·checkpoint·당시 결과 해시는 모두 불변이다.
- 감사 transport의 로컬 fake HTTP에서 요청·응답·validation·수정 판단·compiler 기록을 실제 파일로 생성하고 attempt ID, execution ID, span ID, body SHA의 결속과 민감정보 제거를 검사했다. 동일 파일 재저장은 거절됐다.
- 서로 다른 관측 ID/목록 길이1·4·14, 추가 텍스트 물체, 텍스트 빈방, 이미지 observer 수정, 비진전·재등장·저장 장애를 검사했다. 합성 coverage14→7→1은 공유수정3회 안에서 structure를 완료하고 다음 object 단계까지 도달했다. 다음 단계의 시험용 sentinel 실패를 3D 성공으로 표시하지 않는다.

최신 재생 근거는 [saved-response-regression-final.json](../../outputs/staged-repair-evidence-20261009/saved-response-regression-final.json)이다. `verify_staged_repair_saved_response.py`는 **수정된 코드의 회귀 도구**다. 요청 해시 변경은 예상된 결과이며 당시 송신 내용과 해시가 같다고 주장하지 않는다. 원래 `audit_budgeted_request_trace.py`와 v372의 정확한 재구성 결과는 보존했으며 그 도구는 source가 바뀌면 정확한 재생을 거절한다.

## 초기 실패와 정정

첫 테스트는 sandbox의 임시 파일 생성·정리 권한 거부로 실패했다. 권한 정책을 우회하거나 파일 권한을 바꾸지 않고 승인된 오프라인 테스트 실행으로 검증했다. 초기 새 테스트의 TestCase 직접 import가 기존 테스트까지 중복 수집해 모듈 import로 정정했다.

초기 통합181개 실행은6 assertion 실패를 기록했다. 하나는 새 attempts_total/truncated 필드가 빠진 옛 기대값, 하나는 사용자 요구와 달리 잘린 observer 출력을 재시도하던 옛 기대값, 나머지4개는 자식 테스트 프로세스의 소스 PYTHONPATH 누락이었다. 제품의 출력 재시도 동작을 되살리지 않고 현재 즉시 중단 계약으로 테스트를 정정했으며, 자식 테스트에 기존 소스 경로를 전달한 동일 통합 회귀가 통과했다. jsdom canvas 미구현 경고와 Vite500KB chunk 경고는 남지만 해당 테스트/빌드는 통과했다.

## 정확한 잔여

다음은 새 명시 승인으로 실제 GPT 사진 관측→Nebius Nemotron 설계/수정이 이번 문맥과 계약을 지키며 회복하는지 시험하고, 성공 후보를 일반 App 저장→현재 Isaac3D→Run/Stop까지 검증하는 것이다. 이번 수정으로 모델 성능이나 사진 정밀도가 검증된 것은 아니다. 렌더 critic·범용 계약 확장·신뢰 가격 갱신·최신 패키지와 현장 인수 등 기존 S5/S6 잔여도 유지한다. 전체 상태는 **PARTIAL, whole=false**다.

로봇 guard, 정지·sensor/input/segment 시간, 속도·실물 임무 잠금, 저장된 모델/키/정책·기존 승인·unknown 예약·raw·dirty 변경은 보존했다. 새 설치/설정, commit/push, 타 프로세스 종료, 새 에이전트 생성은 하지 않았다. 현재 앱을 강제 재시작하지 않았으며 새 코드와 빌드는 다음 TwinPulse 재실행부터 적용된다.
