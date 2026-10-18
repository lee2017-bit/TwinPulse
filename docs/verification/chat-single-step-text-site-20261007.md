# TwinPulse 채팅 단계와 텍스트 생성 수정 검증

2026-10-07 KST. 사용자가 보고한 동시 선택지 노출, 텍스트 입력 거절, 생성 실패 진단 부족을 기존 App과 provider 경로에서 수정했다. 오프라인 회귀와 독립 브라우저에서 변경을 확인했고, 실제 로컬 Isaac의 텍스트 생성 후 3D 표시 및 SIM 이동·정지도 통과했다. 외부 모델 응답의 안정성과 실물 준비 완료를 의미하지 않는다.

## 확인한 기존 실패 원인

- 설정된 Nebius profile은 기존 v1 사진 전용 조합이었다. 채팅 화면이 텍스트를 받더라도 `exactly one image`로 거절하고, 사진 생성이 성공해도 v1 warehouse를 반환하면 v2 방 실행으로 이어지지 않는 구성 불일치가 있었다.
- 저장된 REAL 생성은 90초 전체 제한을 초과했다. 이전 기록에는 어느 모델 단계에서 지연됐는지 남지 않았으므로 네트워크나 모델 내부 지연으로 단정하지 않는다.
- 저장된 SIM 사진 요청은 observer 응답이 출력 제한으로 잘려 거절됐다. 잘린 응답을 성공으로 취급하거나 부분 JSON을 복구해 적용하지 않는다.
- REAL 연결에서는 SSH 및 보드 관측이 성공했고 바퀴와 명령 값은 0이었다. `TORQUE_ENABLED`가 안전한 초기 상태 검사를 막았으며, 단순 연결 실패가 아니었다. 읽기 전용 재검사는 torque를 끄지 않는다.
- 질문 카드와 상시 준비·수집·검사 패널이 함께 진행 버튼을 노출했다. 서로 다른 단계의 요구사항을 사용자가 순서대로 해석해야 하는 화면이었다.

## 구현된 변경

### 현재 단계의 선택과 안전 정지

현재 질문 하나만 선택 가능하다. 여러 답은 라디오 선택 후 `Continue` 한 개로 제출한다. 답을 선택하는 것만으로 요청이나 주행을 시작하지 않는다. 과거 질문은 선택한 답을 보여주는 비활성 이력이며, 아직 차례가 아닌 질문은 비활성 요약이다. 선택지가 한 개이면 해당 버튼만 표시한다.

현재 단계 안내는 채팅 스크롤 밖에 고정해 질문 제목을 가리지 않는다. 로봇 선택 전 준비·수집·검사 버튼은 숨긴다. 저장된 REAL 장면은 명시적인 현재 방 표시부터 시작하며, 같은 revision이 Isaac에 적용되고 로봇이 LINKED일 때 검사 준비 버튼을 제공한다. SIM은 Burger를 추가한 파생 revision으로 실제 적용·주행 상태를 관측한다. 원본 draft revision과 달라 준비 대기로 잘못 표시하던 문제를 실제 Isaac 화면에서 확인해 수정했다. 이 관측은 Run 권한을 복원하지 않는다. 기존 고급 수집 기능은 삭제하지 않고 기본 채팅에서만 제외했다. 질문을 기다려도 Stop 경로는 유지하고, 정지·Force STOP은 단일 진행 버튼 정책의 안전 예외다.

### 텍스트와 사진 생성의 같은 방 경로

제품 chat backend의 Nebius 조합은 명시적으로 SiteToolPlan 2.2를 사용한다. 일반 조합의 기본 v1 동작, 저장된 provider 설정, 과거 input/release hash는 변경하지 않는다. 새 요청의 생성 설정에는 Site plan 버전이 포함된다.

텍스트 입력은 observer를 호출하지 않고 planner만 호출한다. 빈 visual observation을 사용하며 user/inferred 근거와 빈 observation ID를 검증한다. 사진 입력은 observer와 planner 두 단계를 유지한다. 텍스트가 사진 관측이나 실측을 만들어 낸 것처럼 기록하지 않는다. 추정 치수와 가구는 SIM 검토용이며 실제 이동 허가나 실측 지도는 아니다.

생성한 Site artifact와 기존 SIM route preparation을 연결했다. 사용자 응답에 결합된 새 생성만 실제 Build 준비를 시작할 수 있고, polling이나 새로고침은 Build·Run 권한을 복원하지 않는다. `Engine connected`, 장면 검증, revision 적용, 현재 3D frame, 실제 SIM 이동 상태를 구분한다.

### 생성 오류와 명시적 재시도

observer 출력은 중복 관계와 치수 및 설명 길이를 줄이도록 요청한다. 기존 4000/8000 출력 예산과 90초 전체 제한은 유지한다. timeout, truncation, 잘못된 JSON·관측 형식·모델·근거 검증에서 request, 단계, 모델, 출력 예산, 경과 시간 및 알 수 있는 finish reason을 기록한다. UI의 Tool details에서 이를 확인할 수 있다. 인증 정보, 요청 이미지, 응답 본문은 공개 진단에 넣지 않는다.

실패한 생성은 원래 입력으로 단 한 번 재요청하는 버튼을 제공한다. 현재 실패 operation과 원래 입력을 검증하고 request ID 중복을 거절·흡수한다. 실패 이력은 보존한다. 자동 유료 재시도, 잘린 결과의 강제 적용, 제한의 무조건 확대는 하지 않는다.

### REAL 초기 상태의 정확한 다음 동작

현재 boot 및 release, 120초 이내 관측, guard, 배터리·충전 조건이 맞고 실패 이유가 오직 `TORQUE_ENABLED`일 때만 초기 상태 준비 질문을 제공한다. 바퀴가 움직이거나 다른 이유가 함께 있으면 이 경로로 우회하지 않는다.

사용자가 현장 조건을 포함한 명시적 초기화 답을 제출하면 기존 prepare controller의 reviewed source transfer 및 Motor OFF를 한 번 실행하고, 완료 후 새로운 읽기 전용 관측을 수행하도록 연결했다. 승인 클릭 유효 시간은 2초이며 소유자·binding·작업 중 여부를 재검증한다. 정지 시험이나 이동은 자동 실행하지 않는다. 이번 검증에서는 이 controller를 오프라인 대체물로만 시험했다.

## 검증 결과

- 최종 Python 및 API 회귀: 167/167 PASS, 83.720초. provider, conversation, robot preparation, 새 text/photo/retry 및 초기 상태 검증 포함.
- 추가 응답 검증 단계 진단과 Site API 회귀: 34/34 PASS, 3.197초. 아래 전체 회귀와 중복되므로 합산하지 않는다.
- 최종 웹 전체 회귀: 340/340 PASS, 43 files, 24.15초. 파생 SIM revision 상태 관측과 비재실행 회귀 포함.
- TypeScript 및 Vite production build PASS. 500 kB 초과 chunk 경고는 남아 있으며 실패가 아니다.
- 독립 built Chrome 및 인증 API: 텍스트·사진·실패 후 명시적 재시도 3/3 PASS. 선택만으로 생성하지 않음, 질문 진행 버튼 하나, 과거 질문 비활성, Site artifact 저장, reload 및 모바일 가로 넘침을 확인했다. 모델 응답은 실제 Nebius provider/service에 주입한 scripted transport였다. 실제 Isaac을 사용한 검사는 아니다.
- 실제 built Chrome 및 로컬 Isaac 텍스트 SIM 경로 PASS. 질문→생성→자동 Build 1회→현재 3D frame→명시적 Run→목표 0.039663 m 이내 도착→채팅 다음 목표→접힌 화면의 Stop→정지 pose 불변→reload 비재실행→Reset preview를 확인했다. 이 실행의 생성 응답은 기존 v2 room fixture였다.
- 실제 로컬 Isaac 사진 및 Nebius 2.2 transport 경로 PASS. 실제 observer→planner→Site artifact→현재 3D→명시적 Run 및 0.039663 m 이내 도착→Stop·reload 비재실행을 확인했다. 외부 모델 대신 scripted transport를 사용한다. 최종 텍스트 2.2 r2 경로에서도 같은 과정과 현재 단계의 `Scene applied` 표시를 통과했다. 모든 테스트 소유 backend/engine은 정상 종료했다.

첫 회귀의 Windows 임시 디렉터리 ACL 및 Vite spawn 제한은 로컬 테스트에 한정된 승인 실행으로 해결했다. 기존 오류 문구 기대값 2개와 단계 정책이 바뀐 검사 버튼 기대값 1개, 기존 준비 완료 문구 기대값 1개는 수정 후 재검증했다. 실패 시 출력과 기존 실측·배포 원본은 삭제하지 않았다.

## 실행 근거

- `artifacts/chat-single-step-20261007-2a3fdf2a/result.json`: 세 built browser/API 시나리오와 스크린샷.
- `artifacts/chat-single-step-isaac-text-20261007/result.json`: 실제 Isaac 텍스트 경로, 현재 frame·PhysX telemetry, 소유 child 정상 종료.
- `artifacts/chat-single-step-isaac-v22-photo-20261007/result.json`: 실제 사진 및 2.2 transport 경로 PASS, 소유 backend/engine 종료.
- `artifacts/chat-single-step-isaac-v22-text-20261007/result.json`: 텍스트 및 2.2 transport 경로 PASS.
- `artifacts/chat-single-step-isaac-v22-text-r2-20261007/result.json`: 최종 웹 build의 실제 2.2 텍스트 경로, 파생 revision 적용 상태·3D·이동·정지·reload PASS.
- 재검증 entry: `scripts/verify_chat_single_step.py`, `scripts/verify_chat_sim_journey.py --case text|image --site-transport-fixture`. 두 entry 모두 fixture 검사임을 명시하며 외부 모델·로봇에 연결하지 않는다.

## 남은 검증과 사용자 실행 순서

1. 기존 TwinPulse를 정상 종료 후 다시 실행해 새 backend와 웹 build를 사용한다. 이전 프로세스나 탭은 자동 종료하지 않는다.
2. 로봇 없이 텍스트 입력→Simulation only 선택→Continue→생성 단계/진단→현재 3D→SIM Run·Stop을 먼저 확인한다. 외부 LLM을 사용하는 이 실행은 비용이 발생할 수 있으며 이번 오프라인 결과와 구분한다.
3. 사진 생성도 확인한다. 이번 수정은 실패 단계 분석과 출력 제한 예방을 보강했지만, 실제 provider의 90초 제한 내 성공이나 사진 해석 품질을 보장하지 않는다. 실패하면 새로운 단계 진단으로 원인을 확인한다.
4. REAL은 별도 현장 승인으로 현재 boot/release 초기 상태·정지 시험·corrected driver scan/odom/TF, 좌표 실측 및 정합을 검증한다. `1cede5493f5a4ade3c46c49049dc9752a8fef3476b76f5a0cc214e16e9ade1ba` 실제 배포 release는 이번 작업에서 변경하지 않았다.

C3–C6 전체 인수는 PARTIAL, whole readiness=false를 유지한다. 이번 결과는 corrected driver의 현장 인수, 실제 사진과 센서 자동 보정, 안전한 자율 경로·반복 임무, 외부 provider 안정성, 최종 패키지 D01–D12 전체 인수를 대체하지 않는다. 이번 턴 로봇 접속·배포·센서·모터·유료 호출·설치·시스템 설정·commit/push·새 agent 생성은 모두 0이다.
