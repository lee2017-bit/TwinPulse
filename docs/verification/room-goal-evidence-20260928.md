# 센서·차체 근거와 방 Twin → odom 목표 검토

2026-09-28. 사용자가 이 작업을 승인했다. 로봇 OFF 보고 유지, 로봇 접속·배포·센서
시작·모터·실물 시험 없음. 기존 실물 임무 잠금·정지 기준은 변경하지 않았다.

## 확인한 근거

로컬 공식 소스의 HEAD는 `90a68bd2e3c61c12966779da89d8eeaec82730e9`, git status는
clean이었다. 기존 `burger-prepared/source.json`과 원본 URDF/네 STL 해시를 대조한다.
실행 시 URDF와 메시의 고정 해시도 검사한다. 새 다운로드/설치는 하지 않았다.

| 항목 | 공식 명목 모델에서 확인한 값 | 실물 경계 |
|---|---|---|
| base_footprint → base_link | XYZ=(0,0,10)mm | 실제 TF 수신 아님 |
| base_link → base_scan | XYZ=(-32,0,172)mm, RPY=(0,0,0) | 현물 센서 장착 확인 아님 |
| 바퀴 간격 / 반지름 | 160mm / 33mm | 실제 조립·타이어 교정 아님 |
| 충돌 모델 X 범위 | -102~+38mm | base_link 기준, 중심 비대칭 |
| 충돌 모델 Y 범위 | 약 -89.026~+89.026mm | 원통 AABB 보수 변환 |
| 명목 외곽 원 반경 | 약123.709mm | 메시/충돌 형상·관절0 자세, 케이블/추가부품 미포함 |
| 기존 보호 반경 | 180mm 유지 | 모델을 이유로 기준 축소하지 않음 |

`robot_geometry_evidence.py`는 원본 URDF의 joint/origin을 합성하고 collision primitive
및 binary STL 정점을 base_link로 옮겨 범위를 계산한다. URDF wheel joint의 -1.57을
임의의 정확한 -π/2로 바꾸지 않는다. 명목 geometry이지 실제 차체 실측이 아니다.
기존 profile/binding/로봇 release 파일은 변경하지 않았다.

저장 실스캔은 `photo-scan-review-20260927/native-scan-bundle.json`의 74프레임.
원본 capture `raw.bin`, `nodes.ndjson`, report/bundle의 해시를 대조했다. 당시 boot는
`3394b6d9-5d94-402c-9e87-18204e04501e`다. 원시 scan은 host receipt 관측구간이며
각 빔의 ROS 시각·현재 boot가 아니다. 해당 자료에는 odom 자세/TF가 없다.
사진의 창문 방향 선언은 native 각도 부호/0도/로봇 전방/odom 변환 증거가 아니다.

## 기존 제품 경로에 연결한 부분

- 방 Twin 준비 후 `센서 좌표·차체 근거 확인`으로 위 값을 읽는다. 자동 로봇 접속 없음.
- 같은 방 패널의 근사 평면을 클릭하거나 Twin X/Y를 입력해 목표를 고른다.
- `목표 좌표 연결 검토 · 이동 없음`은 인증/CSRF API → 기존 BedroomReview에서
  현재 사진·scene·asset manifest 및 모델/실스캔 evidence revision을 다시 대조한다.
- 대응 근거가 없으면 `MISSING_METRIC_REFERENCE`, odom goal=null로 반환한다.
  현재 원본 데이터에 대해 이것이 올바른 결과다. 임의 원점/yaw/사진 축척을 만들지 않는다.
- 명시적인 3~16개 Twin/odom 미터 좌표 쌍은 core의 proper rigid SE(2) 후보로 변환한다.
  중복/일직선/퇴화, 비유한 값, scene/evidence 변경, 사진 추정 basis, 거리/축척 불일치,
  반사/과대 잔차, 임무 좌표 ±10m 초과를 거절한다. fit 한도50mm는 후보 검토 기준일 뿐
  실물 안전 허용오차가 아니다. 스케일/반사를 자동 맞추지 않는다.
- 요청에는 boot_id와 reference basis가 필요하나 현재 boot와 실측의 진위를 확인했다고
  주장하지 않는다. 성공 후보도 alignment_verified=false, motion_authorized=false,
  mission_request=null이다. PhysicalController로 넘기거나 Isaac Run을 실행하지 않는다.
- 목표/대응 근거 변경 또는 요청 실패 시 이전 후보 표시를 폐기한다. 원본/프로젝트
  및 이전 정지 실패는 보존한다. UI 후보는 저장/실물 자격을 자동 부여하지 않는다.

## 검증

관련 core7/기존 BedroomReview10/새 evidence4 =21개 PASS. UI 신규3/기존11=14개 PASS.
초기 단독 core 테스트 import 경로 오류는 기존 테스트와 같은 경로 bootstrap으로 수정했다.
실제 모델/저장 자료로 숫자·해시를 확인하고, 변환의 방향과 수치는 인공 대응점으로
검사했다. 예제 Twin(.2,.3) → odom(.7,2.2)는 회전90°·이동(1,2)의 **합성 검증**이며
사용자의 실제 방/로봇 변환이 아니다.

전체 `room-goal-regression-20260928-r1` core170/Web123/build PASS.
그 후 실제 App/Isaac r1은 반복 메시 계산으로 목표 응답5초 대기 FAIL이었다.
불변 원본 바이트·scale·transform을 key로 계산만 캐시하고 매번 파일 재읽기/해시
검사를 유지했다. 캐시 후에도 변경된 메시 해시를 거절하는 검사 포함21개 PASS.
r2는 새 근거/후보 경로와 실제 Isaac 표시·3시점 재생을 통과했으나 모바일 해시/
입력창 넘침으로 전체 FAIL. 두 실패 기록과 브라우저 종료 뒤 응답 중단 로그는 보존했다.
캐시 수정과 모바일 전용 wrapping/box-sizing 수정은 정지·실측 기준 변경이 아니다.
최종 빌드 후 통합 재검사를 별도 수행했다:

- `artifacts/room-goal-isaac-20260928-r3/result.json`: PASS. 실제 App/API/broker/bridge/
  Isaac 10항목. 새 근거/합성 후보 검증, 기존 3시점 재생/저장 USD/원본 보존, 모바일
  넘침 없음. desktop 근거 화면도 직접 확인. Physics Run/실물/접속/유료 호출0.
- `artifacts/room-goal-browser-20260928-r2/result.json`: PASS. 실제 App→가짜장치20단계,
  수동/임무 일반정지·강제STOP 포함5세션 수락 뒤 새 출력0·종료 확인. 13저장로그,
  1046 events. 합성 출력은 실제 바닥 주행 증거가 아니다.
- `artifacts/room-goal-evidence-audit-20260928-r1/result.json`: PASS. 최종 source/build
  53파일 일치. 전체회귀 manifest에는 소스 해시가 없고 캐시/CSS 전 기록이므로
  전체회귀를 최종 코드에 다시 수행했다고 주장하지 않는다. 후속 관련21 및 최종
  빌드/통합 검사로 해당 변경을 확인했다. audit6 재검사도 PASS(최초 sandbox 임시폴더
  권한 오류 후 승인된 로컬 재검사). 검증 프로세스 정상 종료, tracked diff-check PASS.

초기 r1/r2 FAIL 산출물은 덮어쓰지 않았다. baseline v1.0.153/BL-154와 메모리,
진행현황/야간계획/인수인계를 같은 상태로 갱신했다.

## 실제 정합 완료까지 필요한 것

1. 현재 조립 상태의 라이다 장착 방향/위치와 추가 돌출부를 명목 모델과 대조.
2. 같은 boot·같은 시점의 odom 자세/TF 및 ROS scan 방향·시각 자료 확보.
3. 방 Twin의 미터 축척과 실제 같은 지점의 대응 근거 확보. 기존 사진은 미터 실측이
   없어 현재 근사 scene의 치수도 보정 대상이다. 클릭 목표를 바로 운행 좌표로 쓸 수 없다.
4. 위 근거 검토/현재 boot·배포 결속 뒤 별도 실물 시험 승인. 이후 local scan 보호 및
   제한 임무로 확인한다. 로봇을 켜는 것만으로 위 조건들이 자동 충족되지는 않는다.

현재 구현은 **근거 검토·좌표 후보 연결**까지이며 실제 방↔odom 정합 완료가 아니다.
