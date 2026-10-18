# TwinPulse 단계별 미리보기 검증

2026-10-13 / Baseline 1.0.467. 사용자가 승인한 바닥 선행 표시, 주요 물체의 묶음 생성, Repair 이전 유효 부분 표시, 실패 후 화면 보존과 원본 사진 깜빡임 개선을 구현했다. 실제 App/API/Chrome/Isaac에서 아래 기능을 검증했다. **모델 응답은 명시 고정 데이터이며 새 Flash/Super의 사진 품질·속도나 전체 실물 흐름을 검증한 것이 아니다.**

[화면 17장과 수치·실행 ID를 포함한 단일 PDF](../../outputs/progressive-preview-20261013/report-final.pdf), [HTML](../../outputs/progressive-preview-20261013/report-final.html), [감사 JSON](../../outputs/progressive-preview-20261013/report-final.json).

이 기록과 내부 보고서는 로컬 개발 자료이며 공개 배포물이 아니다. GitHub 공개 자료는 원사진·개인 prompt·좌표·raw를 제외한 metrics-only 형태로 별도 검토해야 한다. 이번 요청으로 공개 권한을 추가하지 않았다.

## 원 실패와 수정

사용자 프로젝트 `chat_mv5d5hwj_a7d5d5f5`, 원 생성 실행 `89d9006ddcc14ffcb8fc74767e90a6db`는 10개 HTTP 응답을 모두 받았고 finish=stop이었다. 관측 20.719초, 전체 구조 144.547초, 물체 다섯 묶음 80.702초, Repair 세 번 77.531초, 전체 약 326.75초다. 출력 소진·timeout이 아니라 `REPAIR_STALLED`였고 바닥만 보였다. 원 실패·raw·장부는 보존했다.

storage depth .20m가 catalog 최소 .25m를 위반했다. Repair1에서 교정했지만 기존 drape의 전체 이불 길이를 침대 모서리에 중심 배치해 assembly가 1.7×3.11m가 됐다. 바닥 덮개·벽시계·천장 환기구·벽 수납장의 generic 표현도 부족했고, 10cm 격자가 desk의 좁은 유효 구간 x=[.88,.89]를 놓쳤다. 모델의 region 수정만으로는 최종 배치가 회복되지 않았다. blocker의 atomic scope 확장은 허용되어 있었지만 원 세 Repair는 요청하지 않았다.

구현은 다음과 같다.

- 작은 room-seed 단계로 floor와 세 벽을 먼저 표시한다. 전체 관측은 checkpoint에 보존하고 seed를 물체 coverage나 실측 완료로 취급하지 않는다. 초기 승인 예산에는 이 planner 요청도 포함한다.
- 주요 가구와 관측된 부모를 우선해 최대6개 상세 묶음을 요청한다. 원 inventory의 순서·이름·source는 바꾸지 않는다. 형식이 잘못된 묶음에서도 따로 검사한 유효 슬롯을 먼저 표시하고 원 불량 응답은 대기 자료로 보존한다.
- 각 물체 검사와 dependency closure 뒤 기존 compiler로 부분 장면을 검사한다. repairable 대상만 **표시 투영**에서 대기로 옮기며 전체 후보를 삭제하거나 전체 PASS로 승격하지 않는다. 내부·unmapped·비수정 오류는 통과시키지 않는다.
- 유효 묶음과 Repair 직후 결과를 기존 broker/Build/현재 JPEG 경로로 갱신한다. 실패하거나 새 결과가 비어도 마지막 유효 장면을 유지한다.
- `floor_covering`, `wall_fixture`, `ceiling_fixture`, `wall_storage`를 versioned catalog에 추가했다. 기존 kind는 기존 catalog1.0, 새 kind는1.1을 사용한다. 새 model library는1.2/33종이다. unknown의 위험 keepout은 유지한다. drape의 기존 geometry는 변경하지 않았고 매달린 부분 envelope라는 의미를 프롬프트에서 명확히 했다.
- 같은 여유 .11m와 간격 .03m를 유지하며 기존 격자 다음에 경계·접촉 후보를 검사한다. bounded 후보 예산 소진은 별도 실패다. compiler trace는 photo1.9/semantic1.7로 구분한다.
- 원 사진 요소를 polling이나 fresh/stale 전환에서 다시 mount하지 않는다. 매개변수 준비 수량과 마지막 실제 표시 수량, 대기 물체·이유, 미완성/마지막 정적 화면을 구분한다. 상세 hash는 기본 접힌 영역에 둔다.

## 카탈로그 외형 연결과 새 프레임 경계

실제 화면 검사에서 부분 후보가 아직 ProjectStore에 저장되지 않았기 때문에 Isaac이 typed catalog plan을 얻지 못하고 collision proxy만 표시하는 연결 누락을 발견했다. `generation_room_visual_v1`은 임의 code나 파일 경로 대신 checked tool plan을 운반한다. 양쪽에서 프로젝트·계획 SHA·정확한 SceneRevision 재생성과 motion 금지를 검사한다. 새 capability가 없는 엔진에서는 박스로 조용히 fallback하지 않고 갱신 필요 오류를 낸다. 기존 owned `/World/TwinPulse` backup/rollback과 `compose_room_visuals`를 재사용한다.

새 물체 종류를 포함한 이미지 시험의 실제 Build receipt는 groups0/meshes0 → groups5/meshes30 → groups11/meshes77 → groups12/meshes83이었다. root가 실제 가구 외형을 화면에서 확인했다. 외형은 illustrative catalog이며 photorealism이나 사진 정밀 복원이 아니다.

Astra `gpt-6-astra` **xhigh** 읽기 검토에서 같은 collision revision의 재Build가 이전 JPEG를 새 plan/command 증거로 채택할 수 있는 P2를 발견했다. 성공 Build의 local display ID로 publisher GPU epoch와5 update warmup을 갱신하고 old callback/raw를 무효화한다. port는 receipt 관측 이후 frame ID와 capture time, exact broker Build 관측을 함께 요구한다. 음성·양성 회귀와 재검토에서 closure를 확인했다. root가 실제 Isaac을 직렬 실행했고 보조에게 실행이나 외부 호출을 위임하지 않았다. 기존 UI Sol high 보조1명과 이 Astra 보조만 사용했다. 주 세션의 실제 모델 설정은 별도 확인 도구가 없으므로 요청 설정과 같다고 단정하지 않는다.

## 실제 사용자 흐름 결과

모든 최종 사례는 같은 production package/extension/Web dist hash로 실행했다. 시험 helper의 중단/복원 시나리오는 서로 다르며 이를 모델 벤치마크의 동일 조건 성공률로 합산하지 않는다. 각 원 summary에 helper 포함 SHA와 API/engine/native log를 보존했다.

| 사례 | 실행 ID | 확인한 범위 | 판정 |
|---|---|---|---|
| `isaac-settled-text-01` | `f914401d177d43e7aececb6e5ab214f7` | room 먼저, 5→11→Repair12, 모든 준비 Build 정산, 저장/reload | PASS |
| `isaac-settled-image-01` | `bb8b488336444a1bab4421c47ed49719` | 원 사진 DOM 유지, 새4kind, 같은 부분 갱신·저장/reload | PASS |
| `isaac-settled-mixed-01` | `6710a4a0ed0c49608a5ac1da3a4f7e68` | 글+사진, 같은 부분 갱신과 모든 준비 정산·저장/reload | PASS |
| `isaac-repair-failure-03` | `4410ffb44e4449d7b1ea9fa26bc1c71e` | 정체 실패 후11/대기1, 전체12 원cp 보존, 같은 소진 정책 재개 차단/추가 Build0 | 보존·차단 기능 PASS, 생성 자체 FAIL |
| `isaac-cancel-01` | `a9d084fc6c564f87982a25578b98a69a` |6개 표시→취소→늦은 유효 응답 Build0→프레임 전달 중단/reload→잔여만 명시 재개12→저장 | PASS |
| `isaac-current-repair-01` | `686a0cce335b438289bb8956564d8a8e` | 실제 현재 프레임→고정 응답 critic→typed patch→새 배치·새 프레임·저장/reload | PASS |

마지막 장면만 보이고 자동으로 완료라고 표시하는 시험이 아니다. room-stage·부분 장면·Repair 대기·실패·새로고침 화면을 각각 캡처했다. 프레임 전달 중단은 실제 publisher를 유지한 채 격리된 ingress에서만 frame을 누락시켰으며 가짜 pixels/engine receipt는 사용하지 않았다. 과거 사용자 flicker/모든 frame 단절 원인을 완전히 확정했다는 주장은 하지 않는다.

동일 정체 정책이 소진된 뒤에는 승인 버튼을 다시 눌러도 `CONTINUATION_STALLED_POLICY_EXHAUSTED`로 차단된다. 이 guard를 완화하지 않았다. 취소·출력 중단의 정상 재개는 별도 사례에서 PASS다. Undo·완전 재열기·프로젝트 전환의 실제 v466 근거는 보존하며 이번에 같은 기능 전체를 새 외부 모델로 재인수했다고 주장하지 않는다.

## 원 후보 재생과 회귀

`original-replay-01`은 immutable 원 checkpoint와 원 후보를 로컬 재컴파일한 결과이며 Isaac/새 LLM 시험이 아니다.

| 매개변수 준비 | 전체 목록 | 표시 가능 | 대기 |
|---|---|---|---|
|0|29|0|29|
|6|29|3|26|
|12|29|5|24|
|18|29|11|18|
|24|29|16|13|
|29|29|20|9|

원 후보·파일 SHA가 그대로이고 전체29 배치는 여전히 `PHOTO_LAYOUT_REGION_FULL`이다. 원 실패를 새 모델 성공이나 전체 기하 PASS로 승격하지 않았다.

- API/표시/저장 `api-checks-05`:123 PASS.
- Core `core-final`:305 PASS.
- Web `web-final.json`:517 PASS, 최종 TypeScript/Vite build PASS.
- Provider `provider-checks-02`:451개 중447 PASS/기존4 FAIL, errors0. 이전 실패 집합과 같으며 전체 회귀 PASS라고 하지 않는다. 원 full log를 보존했다. compiler version 기대값, 품질 미완성 초안 반환, support 보류 요청 수와 unchanged Repair 반환 계약을 별도 검토해야 한다.
- 새 exact visual binding, malformed slot 보존, invalid parent dependency, floor/contact 후보, generic relation/keepout, same revision old JPEG 및 GPU warmup 음성·양성 검사를 포함했다.

`isaac-image-text-01`은 room stage의 transport routing 누락으로 FAIL이었다. 누락을 수정하고 새 폴더에서 재시험했다. `isaac-repair-failure-01`은 고정 응답 함수가 두 번째 repair feedback의 JSON+설명을 단일 JSON으로 잘못 읽어 실패했고 원 UNKNOWN 예약이 남았다. helper만 교정했다. `isaac-repair-failure-02`는 동일 소진 정책 재개를 완료로 잘못 기대한 시험 FAIL이다. 원 로그·장부를 덮어쓰지 않고03에서 guard를 유지한 보존·차단 시험으로 분리했다. 개별 원 생성 FAIL 자체를 PASS로 바꾼 것이 아니다.

## 비용과 보존

이번 신규 외부 요청0/USD0, 실물0, 유료 Cloud0이다. 기존 외부 승인 기간이 만료되어 key를 불러 새 추론하지 않았다. Flash V4.1/Nemotron3 Super120B 운영 조합·출력/시간/요청/금융 설정은 유지했다. 과거 실제 실패 추정 USD.1139037/held0은 별도 이력이며 verified invoice가 아니다. 기존 UNKNOWN를 삭제·환급·초기화하지 않는다. 이번 로컬 고정 응답 장부의 reservation은 실제 외부 청구가 아니며 원01의 mock UNKNOWN도 보존했다.

기존 launch `140d470ab052487aa4d9d73550a17a68`의 소유 런처19968/Kit17844를 정상 종료 요청으로 닫고 모든 시험 엔진도 정상 종료했다. 마지막 Kit 활성 수0이며 사용자 다른 프로세스를 강제 종료하지 않았다. 사용자 원 파일 SHA는 전후 동일하다.

- `project.json`: `cb1374a02cccd5d7eaee0a884670abaab14270c966962ff7ec011b6087e648cf`
- `project.conversation.json`: `72e052ef3c2d0e56a4fce3195d88deb6c8e09c44d2ceaabcfbcf6c51226ce651`

새 설치·시스템 설정·commit/push·공개 배포는 없다. PDF는19페이지/실제 화면17장, desktop/mobile 내장 이미지 decode·가로 넘침0·외부0·pageerror0 및 전체 Poppler 렌더 시각 검토를 통과했다. SHA `354b3525317ffebc4db06e072c3e6054442b021264a95b7deac377974fd7d5af`.

## 다음 작업

1. 새 외부 기간과 데이터 범위에서 Flash/Super의 세 입력을 실제 재시험한다. 새 room seed의 첫 화면 시간과 실제 model Repair 회복·generic kind 사용 여부를 기록한다.
2. 원29 전체 후보의 blocker/drape/지지 문제를 모델이 실제 고치는지 확인한다. 전체 이불의 surface와 매달린 부분을 연속 패브릭으로 만드는 모델, 벽 수납장 위/안의 자식 지지 계약은 이번에 구현하지 않았다.
3. 기존 Provider4개 기대 계약을 원 근거로 검토한다. 무조건 기대값을 변경하거나 성공 기준을 완화하지 않는다.
4. live LiDAR 공통 저장/Undo 연결과 현장 안전·정합 인수는 별도 승인과 실제 로봇 자료에서 마무리한다. 전체 실물 준비 완료를 주장하지 않는다.
