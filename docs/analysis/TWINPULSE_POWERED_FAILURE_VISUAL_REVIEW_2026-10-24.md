# TwinPulse 실물 시험 실패·TurtleBot/LiDAR 표시 종합검토

작성: 2026-10-24 KST. 최신 대상: 설치 `20261023T140854Z-119dbace2d7b`, source manifest `119dbace2d7bf2437f3cbade795b57d263208ea74cccab3168a560835ce3a206`.

이번 요청은 **종합검토 우선**이다. 제품 코드/설정/설치본 변경, App 재실행, 로봇 연결·구동, 외부 업로드는 하지 않았다. 원본 영상과 실패 자료를 그대로 읽고, Astra가 독립 대조했다. 아래 계획은 아직 실행한 수정이 아니다.

## 1. 결론

사용자 지적이 맞다. 최신 영상의 주요 주행 구간에 RoomPlan 공간만 있고 TurtleBot 모델과 실물 LiDAR 점이 보이지 않는다. 이것은 녹화 파일 손상이나 단순 확대 문제만으로 설명되지 않는다.

1. 실제 실물 로봇은 App에서 연결·준비되고 센서도 수신됐다. 그러나 해당 로봇의 Twin 표시 위치를 설정하지 않아 Isaac에 그릴 모델 목록에 들어가지 않았다.
2. 실물 raw scan은 수신되지만, Twin 위 LiDAR overlay는 현재 Isaac SIM 결과를 소비한다. 실물 수신→현재 pose/센서 변환→Twin 투사 경로가 연결되어 있지 않다. 추정 모델만 배치해도 이 연결이 생기는 것은 아니다.
3. 별도의 센서 좌표계 LiDAR 보기 기능은 존재하지만 접힌 상세 항목 안에 있다. 이번 녹화의 주요 조작 구간에서는 표시하지 않았다.
4. 따라서 시간정책·Stop·기록 개선과 별개로 **모델+센서가 보이는 사용자 여정 검증을 빠뜨렸다.** 218개 회귀 PASS나 실제 바퀴/Stop 기록은 이 표시 누락을 통과시킬 근거가 아니다.

현재는 **실물 제어 일부 개선 / 표시 통합 미완료 / 전체사이클 미완료**다.

## 2. 영상·원문·코드 대조

최신 원본 영상은 [retry09/app-screen.mp4](../../outputs/robot-powered-roomplan-20261023-01/ui-retry09/app-screen.mp4), 281.240초이다. 다음은 편집하거나 로봇을 덧그리지 않은 원본 녹화 JPEG다.

| 확인 구간 | 원본 프레임 | 관측 |
|---|---|---|
| 약2:18 정지수집 | [000202.jpg](../../outputs/robot-powered-roomplan-20261023-01/ui-retry09/frames/000202.jpg) | CONNECTED/LiDAR STREAMING, Twin에는 공간만, `awaiting current scan` |
| 약3:00 전진 유지 | [000264.jpg](../../outputs/robot-powered-roomplan-20261023-01/ui-retry09/frames/000264.jpg) | DRIVING/전진키 활성인데 Twin에는 모델과 scan이 없음 |
| 약3:55 마지막 우회전 | [000346.jpg](../../outputs/robot-powered-roomplan-20261023-01/ui-retry09/frames/000346.jpg) | RoomPlan만 표시, 원 센서 공백으로 조기정지한 구간 |

프레임의 원 시각/단계는 `ui-retry09/frame-times.json`과 `session.json`에 있다. 앱 영상은 renderer 녹화이지 실물 카메라 영상이 아니다. 다만 사용자가 지적한 것은 실물 촬영 부재가 아니라 **Twin의 3D 로봇·센서 부재**이므로 이를 혼동해 해명하면 안 된다.

### 2.1 TurtleBot 모델이 없는 직접 경로

- Astra가 `ui-retry09/fleet-observations.jsonl`을 집계했다. **CONNECTED+STREAMING 490개 관측 모두 `display_pose=null`**이었다. 메인의 bootstrap/여섯 HOLD 전후 snapshot 대조도 같은 결과다. 그 시점 raw scan은 대략392~397개 점을 가진다.
- `packages/twinpulse_app/src/twinpulse_app/robot_fleet.py:778`은 실물 row의 `display_pose`가 있을 때만 Isaac desired robot 목록에 넣는다. 현재 Twin revision도 일치해야 한다.
- 같은 파일 `:802`는 추정 모델을 `visual_only=True`, `lidar=False`, `intent=None`, `task=None`으로 보낸다.
- `scripts/twinpulse_fleet_runtime.py:391`은 실제 `turtlebot3_burger.usda`를 참조한다. **모델 자산이나 추정 표시 기능 자체가 없는 것은 아니다.** 이번 흐름에서 설정·인수하지 않은 것이다.
- 등록된 SIM 로봇도 이번에는 연결하지 않았으므로 SIM row가 있다는 사실만으로 모델이 나타나지 않는다.

해법은 자동으로 원점에 로봇을 만들어 실제 위치인 것처럼 보여주는 것이 아니다. 기존 `Estimated Twin marker` 배치 기능을 주 흐름에서 찾을 수 있게 하고, 사용자 추정 위치/방향임을 명시해 모델 표시를 확인해야 한다. 원점·사진상 위치를 임의로 실제 좌표로 확정하지 않는다.

### 2.2 LiDAR 데이터는 있는데 Twin에 안 보이는 경로

- `apps/twinpulse-web/src/TwinViewport.tsx:493–509`는 현재 Isaac frame의 `lidar_overlay`와 robot/connection/motion epoch, 표시 신선도를 확인한다. `robot.scan.points`를 직접 Twin에 그리는 경로가 아니다.
- `scripts/twinpulse_live_viewport.py:208`의 overlay 생산자는 `fleet_runtime.frame_scan`이다.
- `scripts/twinpulse_fleet_runtime.py:114,138`은 `visual_only`를 SIM scan 계산에서 제외한다. `:431–436`은 추정 모델의 scan을 `None`으로 유지한다. 실제 센서인 것처럼 가상 ray를 제조하지 않으려는 분리다.
- `RobotFleet.tsx:546–549`에는 실물 점을 그리는 `LidarPointView`가 이미 있다. 그러나 컨트롤 Details 내부의 별도 접힌 `LiDAR points` 항목이다. 소스 설명도 동기화된 pose·sensor transform 없이는 Twin에 투사하지 않는다고 명시한다.
- 따라서 `Hit points`를 선택하거나 추정 로봇을 배치하는 것만으로 실물 world overlay가 생기지 않는다.

정확한 표현은 **“센서 수신은 있으나 Twin 투사 경로·기본 표시 UX가 미완료”**다. `UNALIGNED`라는 값 하나를 UI가 검사해 모든 것을 숨긴다는 설명은 소스와 맞지 않는다. 또한 세계정합을 모른다는 이유로 센서 좌표계의 실시간 점 보기까지 숨길 필요는 없다.

현재 `STREAMING · awaiting current scan`은 센서 미수신과 Twin overlay 미준비를 구분하지 못한다. 수신 중/원점 미설정/변환 미준비/실제 데이터 지연/표시 OFF를 구별해야 한다. 이미 받은 점 개수·원 시각을 즉시 볼 수 있어야 한다.

## 3. 반복 실패의 통합 이력

다음은 서로 다른 시도를 합쳐 PASS로 만들지 않은 요약이다. 원본 목록은 [expanded-timing-status.json](../../outputs/robot-powered-roomplan-20261023-01/expanded-timing-status.json), [powered-retest-status.json](../../outputs/robot-powered-roomplan-20261023-01/powered-retest-status.json), [final-status.json](../../outputs/robot-powered-roomplan-20261023-01/final-status.json), [최초 연결 검토](../../outputs/robot-powered-roomplan-20261023-01/connection-repair-review.json)에 보존돼 있다.

| 시도/층위 | 실제 실패 | 반영 및 현재 한계 |
|---|---|---|
| 최초 연결 | 미발행 `-inf`가 진단 JSON에 들어가 control worker 종료. Stop 큐 경합도 재현 | 진단 null 처리/Stop 경합 보완 후 이후 App Connect·Prepare 성공. 모든 과거 실패를 네트워크 탓으로 설명할 수 없음 |
| retry01 | 1.2초 수동 유지 중 원 입력 deadline 초과, 발행1회 | UI 응답 후 갱신 보완. 유한 전후진·90도 wheel 목표 일부 성공과 연속조종 실패는 별개 |
| retry02 | 다음 검사에서 deadline24.071ms 초과 | UI/nonce 나이의 같은 구간 중복을 교정. 과거 전체 지연의 유일 원인 입증은 아님 |
| retry03 | 서버 dispatch711.558ms, pending stack에서 배터리 표시 파일 I/O 관측 | 표시용 파일 읽기/잠금을 제어에서 분리. 711ms 전부가 한 read 때문이라는 단정은 불가 |
| retry04 | SSH timeout | 사용자가 로봇 OFF 확인. 구동 실패/수정 효과 시험으로 계산하지 않음 |
| retry05 | 3초 유지 중 deadline9.018ms 초과, wheel 중심2.941cm | UI 갱신 위상 누락 반례 보완. 당시 지연 전체의 단독 원인은 UNKNOWN |
| retry06 | 첫 입력이 PC에서332.281ms 경과, 원350ms 기한 거의 소진. 로봇 INPUT_EXPIRED/발행0 | UI 보완만으로 해결되지 않았음을 보존. 동시 GC·표시지연을 원인으로 단정하지 않음 |
| retry07 | input500/output600ms. 네방향3초·좌10초 뒤 우10초 wheel 관측 간격 오류 | 일부 유지 효과는 확인. wheel 관측 기준은 입력 기한과 별도. 당시 실제 실패 간격값 미기록 |
| retry08 | input1000/output1200ms. bootstrap 뒤 첫 수동 DEGRADED·동작증거 없음. 나중에 기록 queue512 포화 | 버퍼/기록실패 종단처리·연결감시 보완. **후행** 저장포화를 **앞선** 첫 Stop의 확정 원인으로 바꾸지 않음 |
| retry09 | 네방향3초·좌10초 뒤 우10초가 약4.9초에서 LiDAR coverage gap으로 종료 | gesture 중 입력/출력만료 pause0, 각 Stopreadback 확보. 우10초 원 실패가 있으므로 전체연속 FAIL |
| 화면/데모 | 움직임·scan 기록이 있어도 영상에는 모델·점 표시 없음 | 기존 marker/점 보기 기능을 실제 여정에 통합·검증하지 않은 별도 누락. 이번에 미수정 |

### 3.1 현재 개선된 것과 아직 아닌 것

- 최신 제어 요청258건의 native browser→App 응답: 평균20.530ms, 표본표준편차7.789ms, p99 54.202ms, 최대69.839ms. 이것은 Pi까지의 전체 제동 응답시간이 아니다.
- PC 입력 나이248건: 평균18.617ms, 최대115.911ms. 위 왕복시간과 다른 값이다.
- 여섯 gesture 중 입력/출력 만료 pause는 없었다. 다만 arming 후 갱신6건의 generation 거절과 이동 전 presence 만료2건은 남아 있다. 오류가 하나도 없었다는 뜻이 아니다.
- 마지막 세션 기록은 최대 단일 write4.538829초를 겪고도 버퍼가 회복됐다. 최종29,363건/18segments/71,533,477B, accepted=saved/complete true/해시·행수 문제0이다. 저장장치 지연의 근본 원인까지 최적화한 것은 아니다.
- 최신 Stop·LiDAR OFF·Disconnect cleanup 및 App/Isaac 정상 종료는 확인됐다. 실제 로봇 전원 OFF는 관측하지 않았다. 이번 검토에서는 연결 자체를 시도하지 않았다.
- 바퀴 이동량은 독립 몸체/미끄러짐/물리 제동 검증이 아니다. 후진 LiDAR 추정이 정지 baseline 밖이라는 보조 결과도 RoomPlan scale·외부변환·세계정합을 모두 증명하지 않는다.

### 3.2 아직 고정된 기준도 있다

현재 로봇별 Custom은 input1000/output1200/odom·wheel500/presence5000ms다. 그러나 전체 제약이 모두 UI 파라미터화된 상태는 아니다.

- watch ACK 왕복 인정 한도500ms: `physical_live_session.py:595`.
- session 감시의 하한2500ms: 같은 파일 `:635,740`. 현재 profile에서는5000ms가 적용된다.
- dense Stop 증거 표본의225ms 상한: `stop_policy.py:28,42`. 수동 wheel 간격500ms와 역할이 다르다.
- 유효 반사점 최대 공백5°: `field_tests.py:471–477`. 시간 파라미터가 아니다.

이는 모두 이번 마지막 실패의 원인이라는 뜻이 아니다. **입력만 늘리면 다른 정지 조건까지 없어지는 구조는 아니다.** 고정 기준의 목적·근거·조정 가능 범위를 한 번에 문서화할 필요가 있으나, 제출 전에 모든 항목을 새 설정 화면으로 확대하는 것을 필수 선행작업으로 삼지는 않는다.

## 4. 마지막 LiDAR 공백의 판단

원 실패는 `ui-retry09/live-final/events-00014.jsonl:546`, `FIELD_DIRECTION_COVERAGE_GAP`이다. 원 입력 deadline4721.566165537s에 비해 pause 요청4720.704308003s로 약862ms 여유가 있었다. 이번 중단은 입력 timeout 추가 확대의 직접 대상이 아니다.

같은 파일477행 scan977은 complete=true/unknown bytes0이며 공개점의306.46875°→311.84375° 사이5.375° 공백이 있다. 좌우 회전은 전체360°의 유효 반환 간격≤5°를 요구하므로 시간·조건이 강하게 대응한다. 정지 baseline의 complete 공개 scan36개에서는5° 초과 공백이 없었다.

그러나 실패 예외에는 사용한 frame/hash/각도 구간이 직접 붙지 않았다. `guard.last_result`는 이전 성공 frame976이다. 공개 점 대조는 전체 원 링·quality 필터의 정확 재현도 아니다. 그러므로 **977은 강한 후보이지 직접 결속된 확정 실패 frame은 아니다.** [Astra 원문 대조](../../outputs/robot-powered-roomplan-20261023-01/expanded-timing-astra-review.json).

필수 최소 보완은 다음 둘이다.

1. 저장된 원 링을 같은 필터/complete·partial 선택 경로에 재생하고, 실제 실패 예외에 최초 검사 시각·frame/hash·유효점 간격을 결속한다. 후행 성공 프레임을 원 실패로 사용하지 않는다.
2. 한 번의 반사 누락과 지속 관측 불가를 어떻게 다룰지, 필요한 회전 공간/최신 위험 우선/원 시각을 유지한 상태에서 검토한다. 결과를 본 뒤 기준을 정한다. **5.375를 통과시키려고 곧바로6°로 바꾸거나 missing return을 빈 공간으로 치환하는 수정은 하지 않는다.** 허용할 근거가 없으면 정지는 유지하고 사용자에게 실제 누락 방향을 보여준다.

`FIELD_DIRECTION_COVERAGE_GAP`과 기존5° 검사는 현재 Git HEAD에도 있으므로 이번 버퍼 보완에서 새로 추가한 조건은 아니다. 주기적 미해석11바이트/불완전 링 문제와 이번 complete ring 후보의 유효점 공백을 동일 원인으로 합치지 않는다.

## 5. 왜 계속 다른 문제처럼 발견됐는가

한 가지 문제를 고칠 때마다 로봇이 새로운 결함을 만드는 것이 아니다. 기존 층위가 **연결→입력 전달→관측 간격→기록→센서 커버리지→화면 표시** 순서로 드러났고, 각 수정의 보조시험 결과를 사용자 전체 여정과 연결하는 검증이 부족했다.

특히 이번에는 원문/Stop/기록 검증에 집중한 반면, `모델이 실제 프레임에 있음`, `수신 scan이 눈에 보임`을 같은 필수 여정의 결과로 검사하지 않았다. 모델·LiDAR가 없는 영상은 진단 기록으로는 유효해도 사용자 목표의 완성 데모가 아니다. 이 누락은 사용자가 캡처로 지적하기 전에 발견했어야 한다.

원 보고서에는 최신09 영상 외에 과거06·03 영상도 같은 페이지에 들어 있다. 과거 구역의 “최신 retry06”은 그 시점 표현이지만 현재도 최신인 것처럼 읽힐 수 있다. 증거는 보존하되 제출 영상과 시도별 진단 아카이브를 분리할 필요가 있다. 영상 삭제나 새 녹화·업로드는 이번 검토에서 하지 않았다.

영어 UI 통일도 완전히 끝난 상태는 아니다. 실제 프레임의 배터리 표시는 `약 …% (전압 추정)`이고 `robot-fleet-types.ts:109,118`에도 한국어 문구가 남아 있다. 기능 정지 원인은 아니지만 기존 요청의 미완료 항목으로 보존한다. 이는 새 기능 개발이 아니라 표시 통합 때 함께 정리할 문구다.

도구의 오래된 성공 문구 selector timeout, 개발용 fixture 오류, 촬영 위치 문제는 제품/로봇 실패와 구분한다. 과거 DWM/RAM·화면 캡처 문제는 별도 이력이며 최신 coverage 공백이나 미설정 marker의 확정 원인으로 끌어오지 않는다.

## 6. 제출까지의 최소 수정 순서 — 이번에는 계획만

### A. 로봇 없이 먼저 닫을 두 작업

- **제어:** 마지막 실패 원 링 재생·정확한 최초 실패 근거와 유한 공백 처리 정책 검토. 기존 실패와 안전 조건은 보존한다.
- **표시:** 기존 추정 Burger 배치와 sensor-local `LidarPointView`를 기본 조작 화면에 연결한다. 연결/센서 수신/위치 미설정/변환 미준비를 별도 표시하고, 선택 로봇이 보이는 카메라 구도로 확인한다. 새 로봇 모델이나 Scanner 앱을 만들 작업은 아니다.

세계정합 전에도 센서 좌표계 점을 보여줄 수 있다. RoomPlan 위 투사까지 요구한다면 acquisition pose·센서 외부변환·같은 epoch의 원 scan을 결속하는 별도 표시 연결이 필요하다. 사용자 추정 anchor를 쓴 투사는 **estimated / not localized**로 구분하며, 측정된 실제 좌표나 이동 허가로 승격하지 않는다. 실제 센서 대신 SIM ray를 켜서 물리 scan처럼 보여주는 대체는 하지 않는다.

### B. 같은 최종 설치로 한 번의 통합 여정

실제 USD 열기 → 공간 Build → 대상 로봇 선택/추정 표시 위치 확인 → Connect/Prepare → 실제 LiDAR 수신과 점 표시 → bootstrap Stop → 전후좌우3초·좌우10초 → 키보드/명령/회전 → Stop·반출·Disconnect를 같은 상태에서 확인한다. 현재 미완료인 목적지 주행은 필요한 위치 근거를 갖춘 뒤 별도 범위를 명시한다.

필수 결과는 새 시험 종류를 계속 늘리는 것이 아니라 원래 목표 세 가지다: **명령대로 움직이고, 움직임·센서가 화면에 보이고, 안전하게 멈추며 원문이 남는 것.** 여정 중 한 항목이 실패하면 그 여정은 FAIL이고, 다른 실행의 성공 부분을 이어 붙이지 않는다.

### C. 제출 영상

진단 로그 영상과 분리된 한 개의 사용자용 영상을 만든다. 시작 화면/실제 입력 또는 USD Import/선택한 단위 → 로봇 선택·추가 또는 배치 → 충분히 읽을 시간 → 모델 움직임 → 실제/가상 출처가 구분된 LiDAR → Stop을 보여준다. 기존 요청의 텍스트/사진 SIM 데모와 이번 RoomPlan 실물 검증을 섞어 한쪽의 성공으로 다른 쪽을 증명하지 않는다. 마우스 위치 표시와 최종 인코딩 프레임을 확인한다.

새 iPhone 앱·USDZ 강제전환·새 SDK/외부 모델·클라우드·GPU 사용·일반 CAD 확장은 현재 확인된 실패를 닫는 선행조건이 아니다. 일정은 A를 우선한 뒤 B 결과가 나온 같은 설치로 C를 촬영하는 순서이며, 날짜를 맞추기 위해 성공 판정을 낮추지 않는다.

## 7. 독립 검토와 이번 산출물

Astra(`/root/astra_failure_visual_review24`, gpt-6-astra)의 읽기 전용 검토는 모델/센서 경로·490관측·실패01~09·마지막 원 deadline과 coverage를 독립 대조했다. 위 확정/미확정 구분과 최소 순서에 동의했다. 별도 App 실행/로봇 조작이나 제품 수정은 하지 않았다.

이번에 생성한 것은 이 검토 기록과 프로젝트 메모리 갱신이다. **제품 수정·재설치·추가 실물시험·새 동영상 제작·GitHub 업로드는 아직 하지 않았다.**
