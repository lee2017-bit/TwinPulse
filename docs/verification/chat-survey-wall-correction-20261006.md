# 채팅 조사 전용 벽 보정 검증

현재 채팅방의 조사 승인에 bounded wall correction을 연결한다. 목표 좌표로 이동하는 승인과 분리하며, 보정은 원본을 바꾸지 않는 새 ledger revision으로 저장한다. 이 증분은 C4 전체 완료나 실물 데모 인수가 아니다.

## 구현 범위

- 조사 전용 SURVEY_ONLY에 additive v5 correction 계약을 적용한다. v1–v4 계약과 기존 목표 주행 계약은 유지한다.
- 현재 adapter가 보정을 지원할 때만 채팅 readiness에 correct_walls를 선택하고 승인 digest에 policy를 결속한다. 지원 여부 변경은 이전 승인을 무효화한다. 영문 질문에 원본 보존과 derived revision 저장 범위를 명시한다.
- 보정 proposal 검증과 소유 ledger append, robot idle ACK, 현재 source와 새 room revision을 가진 신선한 센서 위치 재검증을 재사용한다. 조사 placeholder는 목적지가 아니며, 목적지에 대한 기존 바닥·벽 검사는 실제 목표 주행에서 유지한다.
- 완료 상태는 SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL이다. 경로와 목적지는 비어 있고 최종 pose는 역사 자료다. 다음 주행 권한으로 재사용하지 않는다.
- PC controller와 saved history에서 v4/v5를 adaptive 계약으로 분류한다. 새 조사 완료 stage와 zero-output reason을 허용하되 비zero 이동, freshness, 속도, Stop 및 기존 예산 검사는 유지한다.
- 채팅 결과에 correction 상태·새 revision·원본 보존과 3D 재구성 필요를 표시한다. saved correction은 3D 적용 완료가 아니다.

## 검증 경계

로컬 합성 raycast의 실제 공유 mission loop에서 조사→fit→ledger append→새 revision의 fresh sensor 확인→SURVEY_COMPLETE와 최종 속도0을 검사했다. 별도 PC/robot-local 합성 subprocess의 proposal→append→ACK→조사 완료도 검사했다. 원격 계약의 초기 실패는 scope 분류와 stage/reason 허용 목록 누락에 의한 INVALID_SESSION_EVENT였으며 실제 Wi-Fi나 로봇 결함으로 해석하지 않는다.

기존 조사·주행·보정·채팅·원격 보호 회귀의 최종 결과는 아래 실행 기록에 동기화한다. 새 Web 표시와 TypeScript build도 검사한다. 로봇 접속·배포·실물 시험·유료 호출·새 설치·commit/push는 0이다. 이전 v294 browser receipt는 이전 source snapshot의 증거이며 이번 변경의 browser 인수로 전용하지 않는다.

## 실행 기록

- Local SURVEY_ONLY correction runtime 1개 PASS, 21.192s. 조사·채팅·v5 ACK 계약 9개 PASS, 65.435s. 최종 승인 policy 변경·remote guard·geometry·ACK 계약 집중15개 PASS, 2.376s.
- 새 PC/robot-local 원격 조사 subprocess와 등록 잠금2개 PASS, 26.381s. 초기 INVALID_SESSION_EVENT 실패는 새 zero-output reason 누락으로 재현하고 수정했으며 stage/scope 분류 누락도 수정했다.
- 전체 관련 Python77개는 212.566s에 76 PASS/1 FAIL이었다. 기존 SURVEY_THEN_NAVIGATE 원격 주행이 ALIGN 진입 시 INPUT_DEADLINE_EXPIRED로 보호 정지했다. Web 시험과 병행 실행 중이었으나 자원 경합 원인은 확정하지 않는다. 전체 PASS로 기록하지 않고 해당 case의 단독 재검사를 별도로 기록한다.
- 실패했던 기존 원격 goal case와 등록 잠금의 단독 재검사2개는28.081s PASS였다. 코드의 안전 deadline이나 fixture를 완화하지 않았다. 단독 통과가 이전77개 통합 실패를 지우거나 부하 조건의 안정성을 증명하지는 않는다.
- Web40파일306개 PASS. 새 표시 테스트의 필수 advanced prop 누락으로 TypeScript 최초 실패 후 prop 수정, 최종 build PASS. 500kB bundle 경고는 잔여 성능 이슈이며 build 실패는 아니다. 이번 source의 actual Chrome/Isaac/실물 인수는 NOT_RUN이다.

## 잔여 작업

1. 현재 채팅방의 보정 revision과 저장·원격 fit/map replay를 우측 3D에 연결하고 기존 legacy room fallback을 현재방 근거로 사용하지 않도록 검증한다.
2. 현재 센서 기반 semantic goal→실제 SIM preview→정확한 digest/revision Confirm→robot-local mission을 연결한다. terminal 조사 pose를 현재 위치로 사용하지 않는다.
3. C5 persistent bounded-leg TaskLoop와 C6 전체 제품 인수를 진행한다. C3 target binary/profile 및 별도 승인된 실물 인수는 별도 잔여다.

Whole readiness=false, C4 PARTIAL. scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s와 기존 실물 잠금을 유지한다. 다음 오프라인 코드 작업에 로봇 전원은 필요하지 않다.
