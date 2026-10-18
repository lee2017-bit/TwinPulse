# v361 — 공급자 해석 정정 및 실제 혼합 시험

## 사용자 의도와 범위

“아니 사진은 GPT로 하고 설계랑 수정은 Nemotron으로 하라고. 아까 그렇게 한거아니야?”를 기준으로 사진 관측은 등록된 OpenAI GPT-5.4 mini, 설계·수정은 기존 Nebius Token Factory의 NVIDIA Nemotron Nano로 분리했다. v360에서 모든 단계를 Nebius로 복원한 것은 에이전트의 잘못된 해석이다. 기존 현재 승인 **최대10회**에 잘못 보낸 Gemma 호출도 포함하며, 정정이 새10회 승인은 아니다.

로봇/SSH/serial/센서/배포/모터/전원/설치/commit/push/새agent0. 원사진·제품 소스·dirty 변경·원실패·정지 기준·실물 잠금·예약PAUSED 유지. 사진 SHA는 전송 승인 식별용이며 배치 정답표가 아니다. 생성 응답을 사람이 편집하거나 사진별 좌표를 주입하지 않았다.

## 호출과 실패 보존

| 경로 | 실제 호출 | 결과 |
| --- | ---: | --- |
| 잘못된 all-Nebius r1 | Gemma1 | observer timeout, 원격/청구 UNKNOWN |
| 잘못된 all-Nebius r2 | Gemma2 | 최초 응답 수신 후 observer 수정 중 사용자 정정으로 중단; 마지막 원격/청구 UNKNOWN |
| 정정 mixed r1 | GPT1 + Nano최초1 + Nano수정1 | 최초 OBSERVED_ITEMS_MISSING, 수정 REGION_FULL(e8/rear_right), 최종 FAIL |
| 정정 mixed r2 | GPT1 + Nano최초1 + Nano수정1 | 최초 PARENT_MISSING_OR_SELF, 수정 검증 통과; actual SIM journey PASS |
| 합계 | **9/10** | 성공 후 추가 호출0, 미사용1 |

정정된6응답 모두 HTTP 수신/finish_reason=stop, raw manifest6↔장부6/고유attempt ID/usage 대응 확인. r1 GPT8.407초/Nano12.172초/수정37.656초, r2 GPT8.719초/Nano26.063초/수정28.765초. 두 세션 모두 모델의 원응답을 기존 Site2.2 검증·bounded repair 경로에 전달했다. 회복1/2는 이 소수 표본 결과이며 일반 성공률 보장은 아니다.

정정6회 usage 기반 추정USD0.01995654, 오송신 수신1회USD0.0004489. 오송신 UNKNOWN2 예약USD0.028은 제거하지 않았다. 합산 추정usageUSD0.02040544 + UNKNOWN 예약USD0.028 = 계산·예약USD0.04840544이며 공급자 청구 확인/환불 확정이 아니다.

중단은 정확한 시험 root/descendant 명령을 확인한 뒤 그 시험의 소유 프로세스만 정리했다. 사용자 기존 App/launcher는 종료하지 않았다. 첫 abandoned-lock acknowledgement는 wrapper PID16036을 넣어 **ownership mismatch로 거부**되었다. 이를 우회하지 않고 실제 lock owner PID11132/attempt를 확인, 기존 안전 API의 owner 종료 검증 후 UNKNOWN/예약 보존으로 정리했다. 초기 `correction-stop.json`의 wrapper PID 기록도 덮어쓰지 않았다. 기존 Nebius155requests prefix는 보존, 오송신3으로158/219가 됐으며 pending0/lock없음이다. 정정 평가 중 이 장부는 불변이다.

## 실제 통과한 범위

둘째 혼합 세션에서 실제 생성→검증→저장→Isaac Build→PhysX 이동·도착→Stop→reload→저장 프로젝트 재열기를 실행했다. synthetic LLM 응답이나 Isaac startup만을 장면 성공으로 표시하지 않았다.

- actual frames187, Stop 후 pose 불변/paused, reload/reset 자동 Build·Run 없음.
- 저장 재열기 schema2.1, 물체8/placement 관계8, scene/input/plan identity 보존.
- 물체: bed, wardrobe, desk, office_chair, cable_bundle, floor_fan, window_blind, hanging_clothes. 전부 실제 모델 응답에서 생성됐다.
- floor4×3.5m는 **추정**이다. 실측 기준/사진 정밀도 인수는 없다. 8개는 방 전체 장애물 목록이 아니다.
- 실행ID·프로파일·그래프·진단/export/desktop/mobile 경로 확인, source 시작/종료 SHA 동일, 테스트 소유 browser/backend/Isaac 종료 확인.
- scene plan SHA `1e282330288e39390e74ccd24d12fa74ffc342f12184d7e3f75b5c40e707c85a`.

원본 결과: `artifacts/pre-demo-20261009/mixed-corrected-live-r1/result.json`, `mixed-corrected-live-r2/result.json`, `mixed-correction-summary.json`, `mixed-corrected-audit.json`. 실제 화면: `mixed-corrected-live-r2/generated-physics-arrived.png`. 잘못된 r1/result와 r2의 중단 raw·장부·브라우저 이력은 삭제하지 않았다. 이번에 제품 코드 변경/새 오프라인 회귀 suite 실행은 없으며 과거 회귀 숫자를 새 실행으로 재표시하지 않는다.

## 아직 완료되지 않은 것

1. **일반 원클릭 앱의 영구 혼합 공급자 설정은 미연결이다.** 기존 혼합 구현은 명시적인 host 평가 scope에서 사용했다. 시험 준비 중 저장 primary key를 OpenAI로 선택했지만 단일 키 선택만으로 Nemotron 설계·수정 라우팅되지는 않는다. 기존 실행중 App의 cached gateway도 이 시험 성공으로 바뀌었다고 주장하지 않는다. 소진/유한 승인 scope를 일반 기본설정으로 끼워넣지 않는다.
2. 사진 전체 장애물/가구 세부 위치·지지/일반 사진 품질/실측 척도는 UNVERIFIED. 원본 입력/모델 판단에 기반해 검증해야 하며 사진별 고정 목록을 재도입하지 않는다.
3. 최종 validated progress에 이전 validation_code가 잔존한다. 최종 attempt는 통과/scene issues=[]이나 표시 진단 잔여를 수정해야 한다. 초기 generated-ready 카메라는 벽으로 가려지고 후속 정상 카메라 화면에는 방이 보인다; 초기 framing 인수도 잔여다.
4. 현재 설정/UI 연결 이후 최신 package·일반 사용자 경로 인수 및 로봇 현장 검증이 필요하다. 이번 SIM PASS는 whole demo/실물 안전/라이다 정합 PASS가 아니다.

현재 확정 방향: **사진 GPT → 설계·수정 Nebius NVIDIA Nemotron**, 단계별 secure key/origin·예산·응답 provenance를 유지한다. 남은 일반 설정/UI 연결과 품질 개선에 별도 paid 시험이 필요하면 새 한도를 확인하며, 이번 성공 뒤 추가 호출은 하지 않았다.
