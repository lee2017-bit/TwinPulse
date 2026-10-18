# TwinPulse 새 대화와 로봇 세션 분리 — 실제 인수

2026-10-13 / Baseline 1.0.469. [단일 12페이지 PDF](../../outputs/product-flow-20261013/device-final-report/TwinPulse-device-flow-report.pdf), [화면 내장 HTML](../../outputs/product-flow-20261013/device-final-report/report.html), [실행·소스·비용 JSON](../../outputs/product-flow-20261013/device-final-report/summary.json).

## 원인과 변경

기본 프로젝트의 2026-10-06 준비 실패는 센서 수집 전에 끝났지만 `REMOTE_STATE_UNKNOWN`을 보존했다. 기존 New chat은 `_scene_edit_admission`의 저장된 SIM 문서 예외까지 통과해야 했으므로 빈 대화 전환이 막혔다. 대화 복귀마다 기본 프로젝트의 로봇 관리 객체와 시작 잠금도 새로 생성했다.

`WorkspaceDevices`를 한 번 생성·공유하고 대화 서비스의 소유권과 장치 서비스의 소유권을 구분했다. 관리형 App의 문서 변경은 현재 살아 있는 작업·수집·전송·정지 작업을 검사한다. 과거 수집 실패나 읽을 수 없는 기록이 SIM 작업을 잠그지 않으며, 실물 동작은 기존 신선한 연결·준비·실행 조건을 계속 검사한다. 읽기 전용 연결 관측은 독립적으로 허용하지만 과거 기록을 정지 ACK로 바꾸지 않는다.

사용자 runtime의 `devices/local`에 수집 current·manual-control·프로젝트 실행 인덱스·연결 진단을 복사/해시검증/원자적 전환으로 이전한다. 이전 marker가 있으면 다시 원본으로 덮어쓰지 않는다. 원본 파일은 삭제하지 않았다. 프로세스 간 OS 장치 소유 잠금은 종료 시 자동 해제된다. 공유 서비스는 대화 종료마다 닫지 않고 App 소유자가 한 번 정리한다. 설치 코드·모델 자산 경로는 사용자 기록 경로와 구분한다.

Readiness의 연결 로그 정리는 완료된 연결 진단만 기간(1–365일)·512MiB 기준으로 `retired-diagnostics`에 보관한다. 프로젝트·사진·센서·current와 실제 활성 작업은 정리 대상이 아니다. 영구 삭제나 무기한 기록 보존 의무를 추가하지 않았다. 새 대화 전환의 확인된 실패 뒤 재시도는 생성한 같은 프로젝트를 재사용한다. 불명 응답은 자동 재전송하지 않는다.

새 공개 원본 JPG가 실제로 MPO 2장(일반 사진+보조 사진)임을 확인했다. 전체 구성 이미지와 총 픽셀 한계를 검사하고, 관측·현재 렌더 검사·OpenAI 어댑터의 전송 표현에는 첫 사진 JPEG를 사용한다. 원 업로드 bytes/hash는 유지한다. 일반 서재·복도·회의실 등의 공간 치수 명칭도 보완했다. 사진별 물체·방 치수·위치 예외나 성공 기준 완화는 없다.

## 실제 시험

| 시험 | 결과 | 시간/물체 | 근거 |
| --- | --- | --- | --- |
| 실제 default/history → New chat, 복귀·reload 3회, stale context POST | PASS | 추론0 | device-default-smoke-02, 최종 device-default-final-01 |
| 복사본 연결 로그 25개 보관, current/대화 유지 | PASS | 추론0, 복구 가능 | device-default-final-01, 원 연결진단 22,311bytes |
| 실제 텍스트 서재 생성·현재 화면·저장reload | PASS | 17.973초, 4/4 | afab09f9-1cb2-44d3-901e-ca2f74983763 / 5a24a49c8b174762b56118b29b3424e9 |
| 새 공개 사진 생성·현재 화면·저장reload | 부분 초안 기능 PASS | 147.560초, 22/23·보류1 | ef092085-7d7e-416d-a7d8-d2735ed389e6 / fddfbb24ab534ae180c61fc4ea037eff |
| 텍스트+같은 사진 생성·현재 화면·저장reload | 부분 초안 기능 PASS | 126.390초, 16/19·보류3 | f7701263-8894-4aaa-8680-9f88fdfc9900 / 1da4d05f163c4f7faebfb54d78f835b4 |
| 공통 MPO 렌더 전송과 최종 로그 UI에서 사진 재시험 | 초안 기능 PASS | 125.796초, 모델 inventory20/20 | 8fdd15d7-bae7-45de-b31e-36214c0b2d1a / 4100793a49c240879894f2b42ff19f1e |
| 실제 Super 제안 Cancel/Apply/현재 화면/Undo/reload | PASS | 추론2 | feedback_2453db28fb5e47c08b4ab901a5e54328 / 01dc71e48ab547d3a05f5f16c44c25f3 |
| 닫힌 새 App/Isaac의 Undo 저장본·전환/재Build 3회 | PASS | 추론0, 정확한 상태 복원 | device-closed-reopen-01 |

최종 복원 revision `bfdc8bb4d1e0a975bc3eccb7e9bc4a8d83992c72cfbd76e986e61937a8497e03`, state SHA `18bf01b232a3da5998534a0a717e469725ee7365f9572c8b5004b2a573bde465`. 최종 default/cold-reopen 소스 동결과 정상 종료를 확인했다. 같은 URL/Kit 내 대화 전환이며 App 전체 재시작 때의 새 OS 포트 배정과 구분한다.

inventory 수는 모델의 근사 목록이다. 20/20이라고 실제 사진의 모든 물체를 사람이 검증한 것은 아니다. 위 결과는 모델 비교 벤치마크·실측·정밀 사진 복원·실물 인수가 아니다.

### 사용자 앱 재시작 후 인수

격리 시험 소유자가 모두 정상 종료된 뒤 실제 사용자 runtime으로 다시 실행했다. launch `50eee2fdf322438189942f5bb68995ee`, `http://127.0.0.1:55144/`에서 Isaac 연결 완료를 확인하고 Chrome의 Start a new chat을 직접 눌렀다. 같은 주소에서 `chat_mv6eizsv_411f76da`가 열리고 `New chat ready`, 입력창, 활성 Attach 버튼을 확인했다. 기본 장면·대화의 SHA는 첫 시험 전 복사본과 동일했다. 새 추론·실물 명령0, 앱은 사용자 시험을 위해 켜두었다. [실제 화면](../../outputs/product-flow-20261013/device-final-report/user-restart.jpg), [해시·재시작 기록](../../outputs/product-flow-20261013/device-final-report/user-restart.json). PDF의 기존 시험 결과를 변경하거나 재시작을 새 모델 시험으로 합산하지 않는다.

## 원 실패·회귀·비용

- default-smoke-01: 시험 도구의 `＋` 버튼명 누락, 모델0. 원 FAIL 보존.
- live-01: 서재 치수 명칭과 MPO 업로드 검사에서 전송 전에 실패, 모델0. 입력을 바꿔 통과시키지 않고 동일 입력으로 수정/재시험했다.
- live-final-01: 시험 도구 `read` 초기화 순서 오류, 모델0. 제품 source·모델·입력을 바꾸지 않은 final-02 PASS와 분리했다.
- 최종 Web 52파일/530 tests PASS, TypeScript/production build PASS. Python 영향 검사215, 후속133, 이미지/치수16, provider 경계36, 렌더/소유26, 최종 source-path/실물 보호46 PASS는 중복이 있어 합산하지 않는다. 중간 CLI tail 기대2FAIL와 잘못된 검사 모듈명1ERROR도 시험 로그에 보존했다.
- 실제 Nebius 추론32HTTP, usage 기반 추정 USD0.1911426, 새 미확정/예약0. 과거 미확정 USD3을 보수적으로 포함해 이번 승인 USD10 내에서 보호했다. 이번 장부는 USD7 신규 예약 한도로 운용했고 제품에 금액 승인/가격 만료 gate를 되살리지 않았다. Metadata GET2는 추론과 별도이며 공급자 청구서 대조는 미실시다.

새 사진: Chris Olszewski (Kgbo), [Bedroom, Interior of apartment in Brisbane, 2025, 02](https://commons.wikimedia.org/wiki/File:Bedroom,_Interior_of_apartment_in_Brisbane,_2025,_02.jpg), [CC BY-SA4.0](https://creativecommons.org/licenses/by-sa/4.0/), 원 SHA256 `3888e47ad6c73ed4360aca67f278b19a4d2c31fb163a266adde23f74f8bed401`. 원본은 보존했고 모델 전송 표현만 MPO 첫 사진을 JPEG로 변환했다. 로컬 보고서의 UI 삽입/축소 화면에 출처를 남겼다. 원 사진·개인 프로젝트·raw·키를 공개 업로드하지 않았다.

## 남은 범위

1. Isaac 연결 전에 독립 대화를 활성화하는 UX는 별도 후속이다. 현재 실제 장면 전환은 엔진 연결/ACK를 요구한다.
2. 사진 외형·누락·물체 배치·규격은 인간 피드백과 추가 자료로 검증해야 한다. 첫 초안의 보류1/3과 품질 미완성 상태는 보존했다.
3. 실물 실행 승인·자동 정합 자료 자동 이전은 자동 검토가 민감 상태 범위 확장으로 차단해 제외했다. 설치 소스와 사용자 상태를 읽는 코드 경로만 분리했고 어떤 실물 실행 권한도 생성하지 않았다. 필요 시 실제 등록 자료를 별도 검토해야 한다.
4. 기존 Provider4 계약 실패, live LiDAR 공통 commit/Undo/저장 연결과 실제 센서·정지·좌표 정합 인수는 이전 잔여다. 새 설치 전체 인수·실물·Cloud·공개 배포는 이번 NOT_RUN이다. whole project PARTIAL.
