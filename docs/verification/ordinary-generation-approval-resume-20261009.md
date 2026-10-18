# TwinPulse 일반 채팅 생성 승인·중간 재개 검증

2026-10-09 KST · Baseline v1.0.370 · [구현 계획](../planning/TWINPULSE_BUDGETED_GENERATION_REPAIR_SOL_PLAN_2026-10-09.md)

후속 v371: [실제 GPT→Nano 시험](ordinary-staged-live-ten-20261009.md)을 별도 승인으로 실시했으나 4/10요청에서 REPAIR_STALLED로 실패했다. 아래 실제모델 NOT_RUN은 v370 구현 인수 당시의 사실이며 후속 실패를 덮거나 실제 생성 PASS로 바꾸지 않는다.

일반 App/API에 생성 예산 승인과 실패한 draft의 명시적 재개를 연결했다. **제품 연결·고정 응답 회귀 및 실제 Isaac 인수는 PASS, 실제 GPT/Nemotron의 새 성공률 시험은 NOT_RUN**이다. 전체 계획은 PARTIAL / whole=false다. 로봇은 OFF로 취급했고 외부 HTTP·사진 전송·유료 호출·로봇 접속은 0이다.

## 사용 흐름

1. 다음 TwinPulse 재시작에서 새 빌드를 사용한다. API keys → Model routing의 단계별 생성 정책은 명시적 선택 사항이다. 설정 저장은 호출 승인이 아니며 기존 저장 조합과 기본 경로를 자동 전환하지 않았다.
2. 사진 또는 글을 보내고 기존 로봇 유무 질문에 답하면, 새 정책 경로는 실제 생성 전에 채팅에서 예산 승인 질문 하나를 표시한다. 모델·공급자·전송할 입력·시간/요청/수정 한도·가격 확인 시점과 추정 비용을 검토할 수 있다. 화면 열기·조회·설정 저장만으로 키를 읽거나 모델 요청을 보내지 않는다.
3. 이번 실행의 최대 USD 금액을 입력하고 Approve generation → Continue를 눌러야 새 승인 manifest가 생기고 생성한다. 기본 표시 USD1은 승인 자체가 아니다. 서버는 소수 둘째 자리까지 USD0.01..20.00을 검증하고 최초 단계에 필요한 보수적 예약보다 작은 금액을 거절한다. Not now는 모델을 호출하지 않는다.
4. 출력 한도 소진은 즉시 실패로 남기고 자동 수정·재호출하지 않는다. 기존 원응답·장부·checkpoint를 보존한다.
5. Review generation budget and resume options로 현재 입력과 checkpoint를 검토한 뒤 **새 예산을 명시적으로 승인**하면 미완료 단계부터 이어간다. 이전 요청·활성 시간·추정 비용은 누계로 남는다. 페이지 새로고침·재시작은 재호출/Build/Run 승인을 복원하지 않는다.

현재 승인 질문을 과거 실패 카드보다 뒤에 배치했다. 최종 실제 브라우저 시험에서 Continue가 화면 안에 보이는 것을 검증했고 저장 screenshot도 직접 확인했다. 이번 새 승인 질문의 모바일 상호작용 전체를 별도로 인수한 것은 아니다.

## 제품 연결과 오류 수정

- `generation_approval.py`는 승인 descriptor를 project/input revision·SHA/route/policy/가격/checkpoint SHA에 결속한다. 입력·조합 변경, 가격 만료, 동일 승인 재사용과 이중 승인 소비를 거절한다. 클라이언트가 임의 scope나 가격을 전달해 실행할 수 없다.
- Conversation API는 승인 선택을 실제 명시적 Continue와 분리한다. 승인 기록 후 새 작업 ID로 기존 ProductWorkflow/provider/compiler/store 경로를 호출한다. 일반 backend가 generation_policy를 credential 설정으로 오인하던 결함도 수정했다.
- 실패 응답의 raw evidence에 실제 수신 usage를 보존하도록 수정했다. 기존 코드에서 장부에는 usage가 있고 rejected raw에는 없어서 정당한 재개 검증이 실패하던 원인이다. 과거 원본을 고쳐 쓰지는 않는다.
- UNKNOWN·송신 중·미정산 요청은 예약을 유지하고 재개를 막는다. 이미 수신된 원응답과 장부가 일치하는 경우에만 명시적 read-only 대조로 파생 checkpoint를 만든다. 이전 UNKNOWN/실패 checkpoint는 불변이다. 원응답 불일치나 checksum 손상은 새 호출 전에 실패한다. 원격 결과가 정말 불명인 경우를 timeout/PID 종료만으로 해제하지 않는다.
- 현재/이전 실행의 추정 사용 비용과 미정산 예약을 구분한다. 누계 history_complete도 표시하며 실제 공급자 청구액으로 주장하지 않는다.
- 사진 mock 시험에서는 GPT 관측 요청에만 이미지가 들어가고 Nano 설계·수정은 텍스트만 받았다. 이는 전송 분리 회귀이지 실제 사진 해석 품질 증명이 아니다.

## 예산과 가격의 제한

선택 정책은 호출별300초/전체900초·최대12요청·공통 수정3·비진전2 및 초기540/수정300/마무리60초, 수정 시작 잔여90초다. Nano20000/no-thinking wire와 출력 소진 즉시 중단 규칙을 유지했다. 요청12회는 최대치이지 모든 호출/수정이 시간·USD 예산에 반드시 들어간다는 약속이 아니다.

이번 ordinary 승인 adapter는 기존 검토 가격 메타데이터를 사용한다. GPT mini snapshot은 2026-10-08, Nebius Nano는 2026-10-09 확인 기록이며 **유효기간은 2026-10-16 00:00 UTC**다. 새 웹/모델 목록 조회로 가격을 갱신한 것은 아니다. 미지원 모델·만료 가격은 키/HTTP 전에 차단하고 조용한 fallback은 없다. 신뢰 가능한 가격 갱신 UI/범용 공급자 가격 연결은 잔여다. 과거 승인·잔여 호출 장부에서 권한을 가져오지 않는다.

## 회귀 결과

| 검증 | 결과 | 범위 |
|---|---|---|
| Provider 전체 | 200 PASS / 4.440s | usage/예산/단계별 생성 |
| 최종 관련 Python 통합 | 244 PASS / 131.559s | 승인·라우팅·채팅·진단·제품 API |
| 승인/라우팅 집중 | 28 PASS / 9.766s | 위 통합과 중복, 합산하지 않음 |
| Web 전체 | 47 files / 436 PASS / 39.15s | 최종 카드 순서 수정 전 전체 회귀 |
| 최종 관련 Web | 4 files / 51 PASS / 5.45s | 최종 승인 카드 순서 포함, 중복 합산 금지 |
| 최종 TypeScript/Vite | PASS | 기존 500KB 초과 bundle 경고 유지 |
| 최종 실제 App→Isaac | PASS | 아래 r4, 외부 모델 없이 실제 엔진 |

승인 전 0호출, 금액 유효성, stale 조합, 저장/재시작, length 즉시 중단, 새 승인으로 미완료 batch만 재개, UNKNOWN 차단·late 정산 파생본, 가격 만료, photo wire 분리, 손상 checkpoint, 작업 메타데이터 유실 후 승인 소유 checkpoint 탐색을 회귀했다. 임의 사진 좌표를 제품 기본에 추가하지 않았다.

## 실제 App→Isaac 최종 인수

[r4 host 결과](../../outputs/ordinary-generation-isaac-20261009-r4/result.json)와 [브라우저 결과](../../outputs/ordinary-generation-isaac-20261009-r4/browser.json)는 PASS다. `inference_source_unchanged=true`, page_errors=[], launcher owned shutdown succeeded(6.765s), supervisor stopped다.

- 일반 승인/API/provider/audit/compiler 경로에 **격리된 시험 전용 HTTP opener**를 연결했다. 네트워크 요청0, scripted 요청4, 새 승인2/장부2다. 최초 구조 수신→batch 출력 length 실패(2요청), 새 승인→그 미완료 batch→방 크기 typed repair(2요청)다. 구조를 다시 관측/생성하지 않았다.
- received3/rejected1 원본과 원래 실패를 유지했다. 누계 USD0.0000216은 고정 usage로 계산한 **fixture 추정치**이며 실제 지출이 아니다. UNKNOWN 예약0/history_complete=true/청구 검증false다.
- 기존 채팅·저장→actual Build/current3D→명시 Run/PhysX 목표 도착→다음 채팅 목표/current pose→채팅 Stop/접힌 화면/paused pose 유지→reload 승인 미복원→reset/재열기와 진단 연계를 확인했다.
- 침대/책상은 기존 파라미터 모델이다. 고정 draft와 크기 수정 시험이며 실제 침실 사진 복원·실측·모델 성공률 인수는 아니다. 실제 엔진 이동 PASS를 실제 로봇 PASS로 바꾸지 않는다.
- r1 locator 중복 선택 FAIL, r2 테스트 observer가 이전 실패 응답을 새 작업 응답으로 읽은 경쟁 FAIL을 보존했다. driver를 정확한 카드/새 operation ID 조회로 수정했다. r3 PASS 뒤 저장 화면에서 현재 질문이 일부 밀리는 UI 문제를 발견·수정하고 r4를 다시 통과했다. 초기 callback 인자 회귀 실패도 수정 후 검증했다.

최종 화면: [재개 승인](../../outputs/ordinary-generation-isaac-20261009-r4/ordinary-resume-approval.png), [생성된 현재 Isaac 화면](../../outputs/ordinary-generation-isaac-20261009-r4/generated-ready.png).

재현은 기존 Python 환경에서 아래 명령을 사용한다. output은 새 디렉터리여야 한다. 이 시험 flag는 production 기본이나 실제 모델 성능 시험이 아니다.

```powershell
python scripts/verify_chat_sim_journey.py --case text --layout bedroom --site-transport-fixture --budgeted-fixture --ordinary-approval-fixture --diagnostics outputs/<fresh-directory>
```

## 정확한 잔여

1. 새 단계별 경로의 warehouse/벽 opening 및 전체 New/Add/Change 계약 확장·회귀. 현재는 home/common 중심이며 이전 편집 경로와 새 생성 계약 전체 인수를 혼동하지 않는다.
2. 현재 렌더를 기준으로 검사하고 수정하는 critic. external_final_review 요청은 아직 실행 전에 거절한다.
3. **별도 새 승인**으로 GPT 관측/Nemotron 설계·수정의 실제 새 성공률·사진 배치/지지 관계 검증(S5/S6). 이전 5회 잔여3이나 과거 USD 한도를 자동 재사용하지 않는다.
4. 신뢰 가능한 가격 갱신/추가 모델 가격 검토, 최신 배포 패키지와 현장 인수. 로봇이 없어도 앞의 제품·모델 검증은 할 수 있다.

원본·과거 실패·dirty 변경·v1/v2·물리 정지/scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s·실물 임무 잠금을 보존했다. 신규 설치·배포·commit/push·타 프로세스 강제 종료·agent 생성은 없다. 전원만 켜면 전체 데모가 완료된다고 보장하지 않는다.
