# 생성 미리보기와 실제 Isaac 재시작 검증

Baseline **1.0.466**. 실제 App/API/Chrome/Isaac 경로의 아래 인수 범위는 **PASS**다. 외부 모델의 새 생성 품질과 실물 로봇은 이번에 시험하지 않았으므로 전체 제품 판정은 **PARTIAL**로 유지한다.

## 화면과 원 기록

[화면 18장과 실행 ID를 담은 PDF](../../outputs/generation-preview-20261012/report-isaac-final.pdf), [같은 내용의 HTML](../../outputs/generation-preview-20261012/report-isaac-final.html), [기계 판독 결과](../../outputs/generation-preview-20261012/report-isaac-final.json)를 함께 보존한다. 이전 v465의 합성 브리지 보고서는 덮어쓰지 않았다.

최종 HTML은 실제 Chrome의1440px/390px에서 내장 화면18개 로드·가로 넘침0·외부 요청0·page error0을 확인했다. PDF는22페이지/내장 이미지18개이며 모든 페이지를 Poppler로 렌더해 표·한글·캡션·화면 배치를 확인했다. PDF 생성 자체가 제품 PASS 근거는 아니며 위의 원 실행 기록에 연결된 결과를 담는다.

이번 장면과 ACK는 설치된 실제 Isaac가 생성했다. 모델 응답만 명시 고정 시험 자료다. 따라서 입력·검사·수정·저장·뷰어 경로를 확인한 것이지, 사진을 실제 모델이 잘 해석했거나 Flash/Super 성능을 다시 측정한 것이 아니다. 운영 모델 조합과 사용자 키 설정은 변경하지 않았다.

## 정상 종료와 데이터 보존

사용자가 기존 프로그램 정상 종료와 시험용 재시작을 승인했다. 실행 소유권을 확인한 뒤 기존 런처의 정상 종료 요청 파일을 사용했다. 다른 프로세스를 강제로 종료하거나 사용자 프로젝트를 시험 데이터로 바꾸지 않았다. 시험은 별도 runtime 폴더에서 실제 Isaac를 하나씩 띄워 순차 실행했다.

기존 런처 `44f039a25f684a1592050109416c28b4`의 owner PID20576과 Kit PID1708 및 해당 자식들은 종료됐다. 기존 raw supervisor의 `engine_exited`와 raw engine의 FAIL은 그대로 남겼다. 당시 엔진은 idle, prim0, capture NOT_RUN, viewport sent0/error null이었다. 생성된 장면이 없던 실행을 정상 렌더 PASS로 바꾸지 않았으며 이 기록만으로 과거 모든 프레임 중단 원인을 확정하지 않는다.

사용자 원본 두 파일의 종료 전·후 SHA256은 동일하다.

| 파일 | SHA256 |
|---|---|
| active_project.json | `2a87c4892164cc91d27c1e875b29f6c298783c705b476c7b5e3887e97247cb9b` |
| active_project.conversation.json | `96612f9f4618f2f6fdaf6201dee5a293c76f5800112f3d3e4ede04c34bbd4efa` |

시험 종료 뒤 시험용 엔진/API도 정상 정리했다. 실행 중인 테스트 프로그램을 운영 프로그램으로 넘겨주지 않는다. 다음 사용자 실행은 원 저장소의 기존 정상 실행 방법을 사용하면 된다.

## 실제 인수 결과

모든 아래 자료는 `outputs/generation-preview-20261012/`의 해당 폴더에 있다. summary/result, 원 diagnostics manifest·trace·checkpoint·ledger·engine capture와 스크린샷을 보존한다. 각 실행 안에서 해당 source/build SHA는 불변이다. 원 실패와 중간 PASS를 독립 표본처럼 합산하지 않는다.

| 흐름 | 최종 시험 폴더 | 실제 확인 내용 | 주 execution ID |
|---|---|---|---|
| 텍스트 | isaac-text-03 | 6/12 표시→출력 중단→프레임 전달 중단/reload→남은 6개 재개→12개 저장/복원 | `5b99e22d354a4611ab46090dea8431c4` |
| 이미지 | isaac-image-02 | 같은 흐름, 사진만 입력하는 API 경로 | `0a75f98252244367815486da384c8ca0` |
| 텍스트+이미지 | isaac-image-text-02 | 같은 흐름, 혼합 입력 경로 | `eb5d2d18b37b4e008a4462eb01a6acb5` |
| 취소·늦은 응답 | isaac-cancel-02 | 첫 부분 장면→취소→늦은 유효 응답의 추가 Build/변경0→명시 잔여 재개 | `c21c1e1e4dfe4eedab1a6383809c366c` |
| 현재 렌더 검사·수정 | isaac-repair-02 | 실제 후보 프레임→검사→수정 중 이전 후보 유지→새 배치 Build/현재 화면→저장/reload | `cd8f7294814943288b60c59134668b1c` |
| 제어권 만료 재현 | isaac-feedback-03 | 준비 단계4초 지연/TTL3초 그대로→Undo→완전 종료/새 엔진 복원 | Undo `3870c7f9077b42c9a9215c7d29aa5c03` |
| 자연어 수정·Undo | isaac-feedback-04 | 모호함 확인·Cancel·유효 이동·잘못된 제안 거절·일반 Undo·닫힌 재열기 | Apply `dd228955275f43f2b3d34c438162fbf4`, Undo `a5850d94babc436abb289742192092ba` |
| 저장 실패 복구 | isaac-rollback-01 | 실제 Build 뒤 저장 직전 오류→보상 Build/ACK/현재 이전 장면→닫힌 복원 | `0487171beeb84dc98b610d6faefe3f8d` |
| 프로젝트 격리 | isaac-project-switch-03 | default 표시→빈 room_two에서 frame/last_frame null·옛 cache409→default 새 세션/같은 revision | 세 launch ID는 JSON에 보존 |

세 입력의 원 중단 execution은 각각 `75892665a2c849f7a45002cde3ab0c9d`, `36e85258048b4bf7974960b2818fbdde`, `b6595d77679b42b185afb3c0408aaf70`이다. 의도한 length 중단을 성공으로 수정하지 않고, 명시 재개의 새 실행과 구분한다. 텍스트는 고정 응답4개, 이미지·혼합은5개, 검사·수정 흐름은6개를 사용했다. 자연어 피드백은 고정 제안4개이며 외부 호출이 아니다.

세 최종 입력의 실제 viewport 전송은 71/82/73 프레임, capture timeout0/error null이다. 프레임 전달 중단은 실제 퍼블리셔·heartbeat를 유지한 채 격리 API 입구에서만 14/13/13 프레임을 누락시켰다. 픽셀이나 엔진 ACK는 대체하지 않았다. 이 시험은 끊겼을 때 정적 화면 보존과 회복을 확인하며, 사용자 현장의 모든 GPU/네트워크 중단 원인을 재현한 것은 아니다.

검사·수정은 서로 다른 세 Build revision과 두 실제 frame_key를 확인하고 침대의 중간 배치에서 뒤쪽 배치로 갱신했다. 사진 품질 판정 응답은 고정이므로 실제 사진 정확성 PASS는 아니다. 자연어 편집에서 유효하지 않은 위치 제안은 원 장면을 변경하지 않았다. 미완성 자료와 추정은 그대로 남았으며 Run/실물 명령은0이다.

transaction의 `current_frame`은 응답 순간의 값이다. 지연 시험에서는 COMMITTED 응답 직후 false였으나 뒤이어 같은 ACK의 더 신선한 현재 프레임을 기다리고 캔버스·디스크·완전 재열기 일치를 따로 확인했다. 보고서 JSON의 `subsequent_current_frames`와 원 browser 결과가 이를 구분한다. 프로젝트 보고서의 두 저장 장면 스크린샷은 촬영 순간 정적 미리보기로 표시됐고, 새 세션의 현재 프레임은 별도 API/캔버스 검사로 확인했다. 정적 화면을 영구 live라고 설명하지 않는다.

## 재현된 제품 오류와 최소 수정

`isaac-feedback-02`의 Undo가 실제로 실패했다. 실행 `d47437467f804f30b9286fd17fdca367`, operation `edit_3fae622bf849430caaebfe040c2d3075`는 command_id/receipt가 없고 `SCENE_EDIT_ENGINE_IDENTITY_CHANGED`로 UNKNOWN이 됐다. 따라서 명령을 보낸 뒤 ACK가 느렸던 문제가 아니라 제출 전 준비 경계 문제다. 같은 엔진/epoch와 이전 Apply 장면이 유지됐고 native capture timeout0/error null이었다.

기존 흐름은3초짜리 제어권을 얻은 뒤 archive/fsync·진단·journal·history 준비를 했다. 이 동안 제어권을 갱신하지 않았고, 마지막 확인은 연결·세션·제어권 문제를 하나의 오류로 표시했다. 실제 실패 시 journal manifest→BUILDING만2.941초였으며 그 앞의 준비 시간도 있다. 기존 로그에서 각 boolean을 기록하지 않아 원 실패의 만료 순간을 직접 입증하지는 못하지만, 같은 실제 경로의4초 지연 재현과 수정 후 갱신 직전 lease=false 로그가 원인 분석을 뒷받침한다.

`scene_edit_transaction.py`를 다음과 같이 최소 수정했다.

- 같은 기록된 엔진/epoch·idle·안전 상태를 먼저 확인한 뒤 자신의 제어권만 제출 직전과 permit 대기 중 다시 확보한다. 다른 소유자의 유효 제어권은 빼앗지 않는다.
- 엔진 단절·identity 교체·제어권 소실을 서로 다른 오류로 기록한다. TTL3초, permit6초, ACK125초, 기하/저장/REAL 기준은 그대로다.
- `execution_diagnostics.py`의 positive whitelist에 갱신 단계와 두 boolean만 추가한다. 제어권 토큰이나 키는 기록하지 않는다.
- 교체 엔진·다른 소유자 takeover·permit 대기 중 만료·진단 allowlist를 회귀 검사한다. 원 UNKNOWN journal은 자동 복구/삭제하지 않는다.

Astra high의 읽기 전용 원인 분석과 좁은 패치 검토를 사용했고 새 P1/P2는 없었다. 보조 에이전트를 추가로 생성하거나 실제 Isaac 실행을 위임하지 않았다. 주 세션의 모델/추론 설정은 독립 확인 도구가 없어 요청된 Sol 매우높음이라고 단정하지 않는다.

## 실패 보존과 회귀

`isaac-feedback-01`은 첫 편집/Undo를 확인한 뒤 완전 재시작에서 홈의 저장 대화를 선택하지 않은 시험 스크립트 오류로 FAIL이었다. `isaac-project-switch-01/02`도 인증된 홈 전환보다 먼저 초기 입력창을 준비 완료로 간주한 재열기 driver 오류였다. 실제 사용자와 같은 명시 열기와 저장 상태 대기를 추가한 뒤 새 폴더에서 재시험했다. 생산 UI를 변경하거나 원 FAIL을 덮어쓰지 않았다.

최종 제어권/진단/실물 admission/피드백/저장 센서 영향 검사 `lease-regression-02.xml`은 **176 PASS + 35 subtests PASS**, 오류0이다. 두 의도한 중단 테스트의 SystemExit thread warning은 남았다. 초기 fixture typo/시계 race와 진단 allowlist 누락을 드러낸 `lease-regression-01.xml` 실패도 보존했다.

전체 `python-runtime-full.xml`은 **866 PASS / 기존4 FAIL + 469 subtests PASS**, 오류0이다. 이전 `python-full.xml`과 실패 이름 네 개가 같고 새 실패0이다. 기존 실패는 compiler 경계1.7/1.8 기대값, quality rollback의 미완성 초안 반환, 요청3/2 기대값, unchanged repair의 pending 반환 계약이다. 기대값을 고쳐 PASS로 만드는 작업은 하지 않았다. 전체 Web511/type/build는 기존 동결 검증이며 이번 production Web/source/dist는 변경하지 않았다. 중복 검사와 subtest는 모델 성공률처럼 합산하지 않는다.

## 비용과 정확한 잔여

신규 외부 API **0회 / USD0**. 시험 ledger의 양수 비용은 가상 값이다. 과거 비용·UNKNOWN·held·사용 상한은 그대로 보존한다. 로봇·센서·모터·전원·Cloud·설치·공개 배포·commit/push는0이다.

1. 새 유효 기간·전송 데이터·목적지/잔여 예산 범위에서 실제 Flash/Super 텍스트·사진·혼합 생성과 수정 품질을 시험한다. 이전 외부 승인 기간은 만료됐다.
2. 실제 사진의 물체 위치·지지·규격과 새 모델 응답의 오류 회복 능력을 검증한다. 이번 고정 응답 인수로 사진 정밀도를 보증하지 않는다.
3. 기존 네 회귀의 기대값과 현재 계약을 원 근거에 따라 별도 검토한다.
4. live LiDAR 자동 보정을 공통 저장/Undo로 연결하고, 사용자와 현장에서 안전 초기화·정지·정합을 인수한다. 이번 정상 재시작 승인은 실물 구동 승인이 아니다.

이 범위는 실제 생성·검증·수정 화면과 복원 경로를 사용할 준비가 됐다는 근거이며, 실물 전체 데모나 모델 벤치마크 완료는 아니다.
