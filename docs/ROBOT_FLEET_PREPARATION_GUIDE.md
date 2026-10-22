# 앱에서 실물 로봇을 준비하는 순서

이 문서는 소프트웨어 사용 순서이며 실물 인수 PASS 증명서가 아닙니다. 로봇이 꺼져 있을 때는 등록·측정 프로필 검토·저장·이전 로그 열기까지 가능합니다. 충전 중에는 바퀴 시험을 하지 않습니다.

## ROS 빌드와 앱 준비

PC의 TwinPulse 실행에는 별도의 ROS SDK 설치가 필수는 아닙니다. 이전 전체 ARM64/ROS 빌드는 Pi의 기존 ROS Humble 도구로 수행했고, PC의 순수 C++ 보호 로직 시험과는 다른 검증입니다. PC에 SDK가 없다는 사실을 Pi의 ROS가 삭제됐다는 의미로 해석하지 않습니다.

명시적인 `Prepare`는 앱이 보낸 고정 source-SHA의 제어 노드를 Pi 사용자 영역에 빌드·검사하고, 실제 출력 설정 readback을 확인한 뒤 준비 상태를 갱신합니다. 빌드 단계는 장치 lease와 모터 준비보다 먼저이며, 소스와 실행파일 SHA가 일치하는 검증 캐시는 재사용합니다. 캐시가 있다는 사실이 현재 SDK·실물 인수를 뜻하지는 않습니다. 실패 시 옛 고정 설정 바이너리로 자동 우회하지 않습니다. 시스템 ROS·드라이버·기본 launch를 교체하거나 임의의 모델 작성 shell을 실행하지 않습니다. 창에는 `Building output guard…` → `Checking output guard…` → `Verifying applied settings…`가 표시됩니다.

새 로봇/새 제어 소스의 최초 실제 타깃 컴파일과 readback은 로봇 전원 후 확인할 사항입니다. PC 재생·단위시험이나 빌드 버튼의 존재를 실제 타깃 성공으로 표시하지 않습니다. 현장 화면은 현재 세션의 입력 만료값과 확인된 출력 timeout을 구분하며, 적용 readback이 없으면 `not confirmed`로 남깁니다. 등록값·추천값의 재계산/적용은 `Robots → Timing settings`에서 별도로 수행합니다. 아래 v546의 250ms/400ms 등 수치는 당시 경로 설명이며 현재 세션의 등록/적용값을 대체하지 않습니다.

## 일반 시작

저장소의 `Start-TwinPulse.cmd`도 설치본이 있으면 `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd`와 같은 활성 Electron 설치본을 실행합니다. 개발 소스를 직접 실행하려면 별도의 `Start-TwinPulse-Development.cmd`를 사용합니다. Test 시작은 같은 설치본의 명시적인 디버그 창이며 일반 시작과 성적을 구분합니다.

## 이번 집중시험: 감독하 저속 현장 모드

아래의 엄격한 실측 프로필 경로와 별도로, 현재 App에는 `Physical setup → Supervised field-test setup`이 있습니다. 로봇이 꺼져 있어도 App 폼에서 검토된 Burger 명목값의 출처와 미검증 한계를 확인하고 설정을 저장할 수 있습니다. 외부 JSON 작성이나 완성된 제동 실측값은 이 감독 시험을 시작하는 선행조건이 아닙니다. 명목값을 실측 인증으로 승격하지 않습니다.

전원 후에는 같은 네트워크·충전선 분리·둘레30cm·현장 감독/즉시전원차단을 확인한 뒤 저장 로봇을 선택합니다. `PC preparation → Check connection → Twin의 Connect → Prepare(정지/zero·OFF) → LiDAR On → 정지 수집8초/기록 확인 → 감독 확인·Arm → Bootstrap stop → 짧은 패드4방향/키보드 → 채팅90도/한 바퀴·연속 스캔 → Stop → 기록 반출 → Disconnect` 순서로 진행합니다. Bootstrap stop은 최대0.03m/s·0.6초의 첫 바퀴시험이며 사전Stop영수증이 없어도 그 시험을 시작할 수 있습니다. 이후 이동만 현재boot/설정/ACK에결속된Stop영수증을 요구합니다. 연결이나 토크 ON 자체를 안전 점검 통과로 부르지 않습니다.

### v546: 시작 조건과 측정 결과를 분리

- Pi부하·실제저장지연·제동·주행은 이번실물세션에서 측정할 결과입니다. 전원OFF/SIM만으로 PASS하지않으며, 시험하기전 그시험의성공을요구하지않습니다. 전체TF/정밀정합/5분soak/엄격실측프로필은 첫감독시험의선행조건이아닙니다.
- 정지8초수집은 기록 경로가 정상인 동안 ring 품질 경고를 누적하며 관측창을 끝까지 기록합니다. writer/저장 fault가 발생하면 즉시 INCONCLUSIVE로 종료하고 이동 권한을 폐기합니다. `collection_complete`는구간종료, `strict_ring_quality`는완전회전품질, 원문저장무결성은최종native manifest·writer ACK와별개입니다. INCONCLUSIVE를미실행이나이동허가로해석하지않습니다.
- 미해석bytes는원문그대로UNKNOWN/불완전으로남깁니다. 감독모드만같은stream의마지막strict-complete회전을**그원수신시각350ms안에서만**사용하고, 최신불완전회전의근접/관측공백은우선거절합니다. CRC·malformedheader·시작불완전·각도fallback·새stream·Stop/수집fault는캐시로우회하지않습니다. 원시각갱신/재생0, strict프로필과ICP는여전히완전회전만사용합니다.
- 0/no-return은빈공간이나유효샘플이아닙니다. 하나의0로전체회전을무조건거절하던규칙을**양수·유효거리샘플만의방향coverage/최대5도공백**검사로바꿉니다. 기존5도·10cm·속도·입력기한은높이지않습니다. 작은/흡수성/투명장애물과미관측각의위험이없다는보장이아니며감독용관측등급입니다. 넓은미관측구간·실제Stop실패면추가이동을막고독립진단/반출은계속합니다.
- 같은연결operation안에서수신나이·ICP자식처리시간·writer단계/ACK·pause이유·명령/trial/scanSHA를기록합니다. 기록/추적/Isaac전체부하에서정지수집→짧은Stop시험으로단계적으로측정합니다. 장시간soak·고의충돌·차체구속·실제Wi-Fi단절은기본세션의필수조건이아닙니다. `stall`은strict tracker의불확실성때문에INCONCLUSIVE일수있으며그결과를삭제/완료위장하지않습니다.
- 엔진 heartbeat의 일시 지연과 프로세스 사망은 구분합니다. 실물 소유/정리 불확실성이 없다고 로컬에서 확인된 idle/SIM에만 서로 다른 두 stale 발행을 확인하고 종료합니다(발행 정체는 최대3초). 그동안 새 실물 연결·주행은 차단하고 이전 제어 lease는 폐기합니다. 현재 실물 세션·정리 미확인·상태 불명은 기존 즉시 종료 경계이며 센서350ms·입력250ms·로봇 watchdog을 늘리지 않습니다. 회복돼도 이전 명령/권한은 재개하지 않습니다.

현장 시험 목록 11개와 원문 내보내기는 같은 로봇 조종기 안에 있습니다. Stop/입력 해제는 지난 명령을 폐기하되 인증 연결을 유지합니다. LiDAR Off·Disconnect·boot/config 변경·감독 기한 만료는 새 준비가 필요합니다. 독립 차체 정체·미끄럼·실제 외곽 10cm 보장·Twin world 정합 정확도는 미검증이며 고의 충돌이나 차체 구속 시험을 요구하지 않습니다. 다음 절의 strict measured 보호 주행은 별도 경로이며 감독 시험의 필수 선행조건이 아닙니다.

## 연결과 센서

1. Robots에서 이름·검토된 어댑터·현재 SSH 주소를 등록/선택하고 PC 준비를 확인합니다. 저장된 이름이나 검색 결과는 현재 인증된 연결이 아닙니다.
2. Twin의 로봇 목록에서 로봇을 선택하고 Connect를 누릅니다. 호스트키 검증을 유지하는 SSH 세션과 검토된 로봇 사용자 영역 helper가 실행됩니다. 시스템 ROS/드라이버를 설치하거나 기존 `robot/current`를 바꾸지 않습니다. Connect만으로 모터나 LiDAR를 켜지 않습니다.
3. 초록점은 현재 인증된 왕복 응답이 있을 때만 표시합니다. SSH, 센서, 제어 준비, 전압, 기록 상태는 서로 다릅니다. 전압을 못 읽으면 unknown이며 백분율을 추정하지 않습니다.
4. LiDAR On은 native 원시 각도/거리 스트림을 시작합니다. 균일 LaserScan으로 위장하거나 사진의 방 좌표로 자동 정합하지 않습니다. LiDAR Off는 이동도 멈추되 SSH 세션은 유지합니다.

## 엄격한 실측 프로필 경로와 공통 명령

- Prepare는 현장 감독과 zero-command 준비 확인 후 명시적으로 실행합니다. 기본 부팅의 torque ON을 안전/위험 판정 하나로 대신하지 않습니다. 준비 경로는 실제 zero/OFF 읽기 확인과 소유한 기존 guarded base를 사용합니다.
- 보호 주행에는 이 로봇/바인딩에 결속한 측정 프로필이 필요합니다. 센서-차체 변환, footprint, 센서 시간 지연의 보수적 상한, 제동/오차/정체 기준은 실측 근거 없이 자동 생성하지 않습니다. JSON은 직접 측정한 값의 가져오기 인터페이스이며 앱이 채워 주는 측정치가 아닙니다. 단순 SHA 문자열이 실측 품질을 인증하지 않습니다.
- `independent_required`는 현재 독립 차체 관측 source의 제품 연결이 **개발 미구현**이므로 `INDEPENDENT_BODY_PROGRESS_SOURCE_NOT_IMPLEMENTED`로 막힙니다. 이는 실측 자료만 추가하면 해소되는 조건이나 단순 실물 미시험이 아닙니다. `explicitly_unverified_supervised`는 독립 차체 진행을 UNKNOWN으로 표시하면서 측정된 바퀴 정체 감시와 native 근접 보호를 사용하는 별도의 명시 범위입니다. 사용자가 이 제한을 검토해 선택해야 하며 자동 전환하지 않습니다. 바퀴 odom을 실제 차체 이동/미끄럼 검증으로 부르지 않습니다.
- `progress.body_progress_policy`를 정확히 `explicitly_unverified_supervised`로 선택했을 때만 독립 차체 전용 네 항목(`minimum_body_translation_m`, `minimum_body_rotation_rad`, `maximum_body_speed_m_s`, `maximum_body_rotation_rad_s`)의 미측정을 null 그대로 둘 수 있습니다. 임의 양수나 0을 채우지 않으며, 이미 제공한 양수 값도 자동 변경하지 않습니다. `independent_required` 또는 미선택에서는 네 항목 모두 독립 측정이 필요합니다. 감독 경로에서도 geometry·sampling·timing·stop·바퀴 진행/속도·거리 환산·바퀴 간격·근거 SHA는 계속 필수이며 서버가 schema·수치 범위를 검증합니다. 차체 진행은 UNKNOWN이고 body 정체/slip은 검증되지 않습니다.
- 같은 boot/release의 유효한 기존 정지 검증은 재사용합니다. 없으면 별도 `Run same-boot stop qualification`의 현장 조건을 확인하고 실행해야 합니다. 이 검사는 실제로 움직일 수 있습니다. 새 native 통합의 실물 검증을 과거 검증으로 대신하지 않습니다.
- 수동/유한 명령 속도는 기존 정책 상한(0.05m/s·0.30rad/s)과 프로필의 실측 상한 중 낮은 값입니다. 단 기존 정지 qualification은 고정 0.05m/s 시험입니다. 유효한 같은 boot/release receipt가 없고 프로필 선속도 상한이 0.05m/s 미만이면 시험을 시작/소비하지 않고 `LEGACY_QUALIFICATION_REQUIRES_0_05_PROFILE_CAP`로 거절합니다. 더 낮은 속도에 결속된 별도 qualification/receipt 경로는 아직 미구현이며, 실행을 위해 실측 상한을 임의로 높여서는 안 됩니다.
- 방향 패드를 누르거나 WASD/화살표를 누르는 동안만 수동 입력을 보냅니다. 해제·창 이탈·입력 만료·장애물/정체는 정지/일시정지이며 연결 종료가 아닙니다. 전송이 회복돼도 지난 이동을 재생하지 않습니다. 다시 조작해야 합니다.
- 채팅은 `로봇이름 앞으로 10cm`, `로봇이름 왼쪽 90도`, `로봇이름 라이다 켜`, `모든 로봇 정지`처럼 대상을 명시합니다. 무기한 주행 지시는 받지 않습니다. 단일 회전/이동은 유한 거리·각도와 로컬 제한 안에서 실행되며 완료는 실제 ACK/관측으로 판단합니다.
- Stop은 프로젝트 전환·종료 대기에도 owned session에 전달합니다. 요청 수락과 로봇의 실제 정지 확인을 구분합니다. 센서가 보지 못하는 끈·전선·투명체·높낮이 장애물까지 보호한다고 보장하지 않습니다.

## 기록과 종료

## 측정 안내와 Twin 표시의 한계

Physical setup의 `측정 프로필 작성 안내`에서 항목별 측정 방법·단위·정책 상한과 실측값의 차이를 확인하고, 로봇/binding ID만 고정된 빈 JSON을 다운로드하거나 앱 안에서 작성할 수 있습니다. 모든 측정치는 null로 시작하며 선택 모드의 필수 측정에 실제 근거가 없으면 적용할 수 없습니다. 명시적인 `explicitly_unverified_supervised`에서만 위 독립 차체 전용 네 항목의 null을 허용하며, 이 허용이 차체 진행/slip 검증을 뜻하지 않습니다. 이것은 수동 측정 준비 지원이지 자동 측정 수집 wizard가 아닙니다.

`Estimated Twin marker`는 사용자가 현재 확정 장면에 명시한 정적인 시각화 추정입니다. 실제 로봇 위치·센서/월드 정합·실시간 이동 추적이 아니며 연결/주행권한을 부여하지 않습니다. 이 기능을 실제 위치 보정 완료로 해석하지 않습니다.

## 기록과 종료 상세

하나의 operation ID에 원래 명령, 로봇 ACK, 현재 boot/release/helper SHA, native bytes와 chunk별 시간창, 분할 기록 SHA, cleanup 결과를 연결합니다. Operation logs에서 요약/JSON과 원문 세그먼트를 내려받습니다. 센서 수신 시간은 정확한 빔 취득 시각과 다릅니다. 실패·미완성 파일과 과거 실패는 지우지 않습니다.

Disconnect는 명시적으로 정지·센서 마무리·기록 종료를 요청합니다. 프로세스가 사라졌다는 이유만으로 cleanup 성공으로 표시하지 않습니다. 앱 재시작은 이름·이력만 복원하고 연결/운전 권한을 자동 복원하지 않습니다. 주소나 프로젝트가 달라지면 이전 요청이 새 장면을 제어할 수 없습니다.

실물 재개 시 별도 인수: 새 부팅 인증/전압, native On→Off→재시작, 준비/정지 검증, 실제 10cm 외곽 정지와 탈출, 바퀴 정체, 한 세션 360도·60초·약5분, 통신 상실과 cleanup/원문 반출. 로봇 OFF에서 이 항목을 PASS로 판정할 수 없습니다.
