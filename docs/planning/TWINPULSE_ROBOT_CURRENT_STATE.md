# Robot current state — 2026-10-16

**최신 v494 / 검색·기억 목록 분리:** 저장이름은전원과무관하게유지, 이번mDNS응답만시각/TTL(최대30초)표시. OS기억Bluetooth/포트는별도목록이며전원·거리·신원을증명하지않는다. 자동접속없음/명시Check connection유지. 실제설치검색·만료·재검색·PC준비·선택·Exit7/cold5PASS, mDNS로봇응답0·기억BT2분리. 실제TurtleBot3 전원cycle/광고명발견/SSH·센서는미검증. 추가유료0/원기록·선택보존. 아래v493은이전연결준비이력이다. [화면·정확한잔여](../../outputs/robot-discovery-presence-20261016/report.html).

**최신 v493 / 최종17:** 별도 관측전용 연결 모드를 설치했다. 원래 Burger 선택 시 읽기전용 Connect 버튼이 활성화되며, 실제 GUI 등록/선택/PC6ready/정상종료/cold복원9+4단계 PASS다. manifest는 simulation/robot_observation=true, physical_robot=false이며 diagnostics+lease만 제공한다. 배포·정지수집·driver시작·모터/주행은 사용할 수 없다. Connect는 누르지 않았으므로 현재 로봇 상태는 여전히 UNKNOWN이다. 로봇 준비 후 현재주소 확인→Robots→PC준비→명시read-only관측이 다음이다. 원선택 복원·추가유료0·일반실행debugoff/Isaacready. 아래 PC-only13과 Sep28 기록은 해당 source/당시 이력으로 구분한다.

이번 확인은 실물 접속 준비의 로컬 PC 단계다. 설치13 실제 Electron에서 검색·수동등록·선택·PC점검·정상종료·cold재열기/원선택복원을 검증했다. 기존 Burger의 로컬6항목은 ready였고 선택 주소의 known_hosts entry가 존재했다. 현재 로봇 전원·실제 DHCP 주소·SSH 인증·배터리·센서·idle 상태는 새로 관측하지 않아 UNKNOWN이다. 이전 전원OFF 보고/과거 실물 qualification을 오늘의 실측으로 쓰지 않는다.

현재 SIM alpha는 metadata/discovery/PC준비만 지원하고 live 진단/물리services는 비활성이다. 다음은 별도 검토된 연결가능 빌드→신선한 읽기관측→정지데이터 확인→동일방 완료/정리된 다지점 survey 정합 검토 순서다. 이번에는 SSH·센서·모터·배포0,추가APIUSD0. 원로봇등록/선택과과거실패이력은 보존했다. [실제화면보고서](../../outputs/robot-connection-preparation-20261016/report.html), [연결준비가이드](../ROBOT_CONNECTION_PREPARATION.md).

## 아래는 2026-09-28 06:49 KST 당시 기록

06:49 최종 전체회귀 core156/Web111/build PASS, audit r3 현재39파일일치.
콘솔 별도PC점검 요구 문구 교정·자동접속없음 시험 포함. 새 브라우저/Isaac/실물
실행은 없으며06:24 actual검증의Web빌드와동일. 로봇OFF·미배포·자율미완료 유지.

06:24 오프라인 추가: 늦은 start 응답 뒤 창 이탈/취소 승인이 복원되던 UI 경합 수정.
컨트롤러14/전체Web111/가짜browser13·actualIsaac8 PASS, 실물/배포0.
[증거/제한](../verification/start-context-20260928.md). 로봇 OFF 및 아래 미완료 유지.

## 현재 요약 — 아래 Sep27 낮 기록보다 우선

- 사용자 마지막 보고: **로봇 OFF**. 야간 새 로봇 접속/배포/실물시험 없음.
  현재 배터리/프로세스/센서 상태는 UNKNOWN이며 어제 전압을 현재값으로 쓰지 않는다.
- 최신 과거 실물 정지시험 `ddaf23aed5964089a1480bb9b3b151ef`는 **QUALIFIED**,
  release `7a1a4f9a…`, cleanup true. 이후 수동 오류5건과 과거 정지FAIL은 별도다.
  "정지시험이 한 번도 성공하지 않았다"는 현재 사실이 아니다.
- 야간 코드: PC 연결 준비 통합, WASD/일반해제·같은세션 재입력, 명시종료,
  명령/관측 journal·이력, passive odom/scan 기록. 가짜 장치 회귀 PASS이나 **미배포**.
  이전 boot/release의 qualification을 새 패키지 권한으로 재사용하지 않는다.
- 사진 근사 방+공식 Burger, PC 합성 임무·A/B 비교·선택시점 actual Isaac 표시 PASS.
  실 TF/바닥pose·실물 자율worker·라이다 충돌 보호·우회/재계획은 미완료다.
  현재 수동 출력은 live scan 보호가 없다. 켜기만 하면 자율 데모가 되는 상태가 아니다.
- [아침 인수인계/제품에서 볼 순서](TWINPULSE_MORNING_HANDOFF_2026-09-28.md).
  사용자 복귀 후 새 범위 승인까지 실물 대기. 개발 중 전원을 켜 둘 필요 없다.

## 과거 기록 — 2026-09-27 낮 시점, 현재 실행 지시 아님

아래의 '최신/현재/다음'은 당시 기록이다. 원본 이력을 보존했으며 상단 현재 요약과
새 인수인계가 우선한다. 특히 아래 정지FAIL/배포미완료·배터리값은 최신 상태가 아니다.

이 파일은 빠른 재개용 현재 상태다. 과거 로그는 verification에 보존한다.
실제 배터리·프로세스 상태는 시간에 따라 바뀌므로 아래 측정시각을 확인한다.

**현재 사용자보고: 로봇 전원 OFF.** 12:54 이후의 이번 오프라인 작업에서
새 로봇접속·센서·모터·전원 명령이나 배터리 측정은 하지 않았다.
이 사용자보고를 과거12:14 센서 자체정지/OS종료의 실측증거로 바꾸지 않는다.

**최신13:35 오프라인 완료:** 실제74frame/29538샘플·원본사진2장 → App native
검토패널/방향가설/프레임선택/원형export/기술통계. Python305/Web44/build,
실저장자료App8단계·기존합성9단계 PASS. [결과페이지](../../artifacts/native-scan-hour-handoff-20260927-final/index.html).
새스캔을 얻지 않아도 이 결과는 로봇OFF에서 열 수 있다. 통계의 clearance는
UNKNOWN; 실제sensor/base/world축/handedness·정지FAIL·activeTwin/실물데모는
미완료다. [다음실물세션](TWINPULSE_NEXT_PHYSICAL_SESSION_2026-09-27.md): 복귀 후
새 읽기점검 승인→기존단일진입점 보고→필요한좌표/정지확인만, 자동재배포·이동없음.

**최신 오프라인 사진연결:** 실제현장사진과 같은스캔위치 사용자확인 확보.
원본사진+점군 검토본 `artifacts/photo-scan-review-20260927/index.html`, 8방향후보.
우선가설은 반사포함이라TF/제어적용금지. 실제사진대기는해소됐으나방향/좌표미검증.
[검증](../verification/photo-scan-review-20260927.md). 새실물접속/구동/배터리측정 없음.

**최신12:14:05 KST:** 실라이다8초수신/STOP후데이터quiet·포트복원/해제.
103448bytes→정상1303패킷/30116샘플/완전74scan,실제센서좌표점군 저장.
전후torque0/속도명령0·encoder2321/1626동일,11.69V/전압추정66.1%.
**물리회전정지 사용자관찰대기**(무수신만으로판정금지),ROS driver/current미변경.
[검증](../verification/robot-lidar-recording-20260927.md). 다음은 저장데이터로
불균등각도보존/센서좌표·TF/TwinPulse연결 준비. 주행정지FAIL·전체데모미완료.

**최신12:02:25 KST:** 실제무주행통신/자동종료 **STATIONARY_CHECK_PASS**.
20.012초관측318상태·guard비활성 유지,종료exit0·독립READ torque0/속도명령0.
전후encoder2321/1626동일,11.82V/전압추정73.3%.
[검증](../verification/robot-stationary-live-20260927.md). 다음은라이다수신/종료/기록준비.
주행/라이다미실행·기존정지FAIL·전체데모미완료. 같은base시험반복불필요.

**이전11:56:06 KST:** OFF문제해결. 실OFF명령1회·독립torque0/속도명령0,
명시OFF준비옵션 영구배포/캐시실행확인 **SOFTWARE_PREPARED_IDLE**.
11.87V/전압추정76.1%,encoder2321/1626. [검증·한명령준비](../verification/robot-torque-off-correction-20260927.md).
encoder변화를 OFF거부조건 아닌 기록으로분리했으나 기존주행정지122msFAIL은 유지.
다음은 미리준비한 묶음무구동점검/실stationary·라이다gate. 전체데모완료 아님.

**이전11:38 KST:** OFF 전용기1회는 사전 위치값 왼쪽2321→2320 1틱변화로
쓰기 전 중단. 토크는 여전히ON, 속도/명령0,12.15V(독립READ). 공개소스 부팅ON
경로와 기존관측 일치. 실제OFF/주행/driver 없음. [증거](../verification/robot-torque-off-20260927.md).
이번표식은 소비됨. 자동재시도/기준완화 없이 1틱 관측·OFF 절차 검토가 다음이다.

**이전11:20~11:21 KST:** 사용자승인 D1 첫 영구배포/build/manifest 확인 완료.
실제READ12.35V·전압추정100%,속도0/0·명령0·encoder2321/1626이나torque=true.
독립checker동일로 **PREPARED_NEEDS_ATTENTION**, idle PASS 아님. driver/모터/센서
시작·이동명령 없음. [증거](../verification/robot-first-deployment-20260927.md).
다음은 torque원인/무주행비활성화 경로 확인 및 제어승인. stationary 미실행.

09:19 KST 오프라인 업데이트: D4 saved-report App, D3/D5 저장scan/검토보정/undo,
D6 수동 경로 비교·보정후 보수적 지도/임무 검토·실제localHTTP9단계 및 정적 요약이
준비됐다(Python271/Web37/build PASS). 실제 로봇 연결이나
전체 미션 완료가 아니다. [아침 재개 순서](TWINPULSE_MORNING_HANDOFF_2026-09-27.md),
`Rehearse-Offline.cmd`로 로봇 없이 전체 오프라인 회귀/합성리허설 가능.
[기존 결과페이지](../../artifacts/offline-rehearsal-20260927-091542-a8c40893/summary.html)는
재실행 없이 읽을 수 있다. 현재 로봇 상태/배터리를 나타내는 페이지가 아니다.

- 최종 데모: 같은 장소의 사진→Twin→robot scan 보정→공정 경로 비교→실물 결과.
- Pi: Ubuntu22.04.5arm64/Humble, 사용자 twinpulse, 마지막 주소192.168.35.139(DHCP).
- **현재 사용자 충전완료·전원ON 보고(11:11 KST):** 읽기전용 재접속 성공.
  당시 uptime150초·Humble·USB2·CPU40.407°C, 감시대상 제어프로세스 없음.
  영구release 미확인·board UNKNOWN(FileNotFoundError)으로 현재 전압/torque/속도는
  못읽음. scan/odom0, driver미시작. [최신 보고서](../verification/robot-wake-readonly-20260927.md).
  소리 원인은 미확정. 앞선01:19:56KST SSH timeout은 당시 전원OFF 기록이다.
- Burger OpenCR FW5, COIN-D4 식별 기록. 실제 LiDAR scan/정지·TF는 미완료.
- 실제 전진/정지 및 사용자 관찰 확인. 00:11시험에서 command_timeout421ms
  수신, encoder안정시간기준FAIL. 실패를 PASS로 바꾸지 않았고 추가구동 없음.
- 00:24:32KST 통합 점검:11.21V/추정39.4%, 속도0/0·torque0·명령0,
  encoder1800/5530, base종료, USB2, CPU38.946°C, root여유9.13GiB.
- 기존 기본launch는 guarded경로가 아님. 검증된 guard는 별도 staging.
- 새/구 one-shot표식 모두 이미 소비됨. 삭제/재사용/자동재시도 금지.
- D1 준비 코드: canonical package/manifest/release/current/READ·base lifecycle
  lease/부모종료 처리/독립 최종 READ와 `Prepare-Robot.cmd`, 별도
  `Check-Robot-Stationary.cmd`. Windows28/WSL Python51·C++1314+615 PASS.
  **Pi 배포·ARM64 helper 빌드완료. 실제 ROS observer/정상종료는12:02 PASS, 재부팅·고장주입 검증 미완료.**
  새 checker는 영구 manifest 없는 경우 UNKNOWN이며 `/tmp` fallback 없음.
- D2 현장확인 만료/1회소비/binding은 dry-run만 준비, physical adapter미연결.
  [최종 준비묶음·상세](../verification/robot-charging-offline-prep-20260927.md).
- 다음: D1배포/토크OFF/실제무주행통신·정상종료 확인완료.
  라이다수신·종료·기록을선행준비하고 별도정지센서시험으로실scan확보.
  D2 physical adapter/정지계측, D3TF, D4liveApp, D5scan→Twin,
  D6실물mission은여전히남음.
- 운영자는 긴 준비 중 대기하지 않는다. 준비 완료 후 즉시 실행 직전만
  현장확인, 수초 점검 목표는 구현/측정할 요구사항이며 아직 성능보장 아님.

## 한 번에 현재 상태 확인

**영구배포/토크OFF/실무주행통신·종료 PASS. 아래는 필요할 때만 새 읽기점검.**
배포를 반복해 해결하려 하지 않는다. 아래 checker는 읽기만 하며 torque를 바꾸지 않는다.
그 뒤 저장소 root에서 다음 명령을 실행한다. 읽기 전용이며 필요한 항목을
JSON/HTML로 기록한다. 키 내용은 SSH만 사용한다.

```powershell
.\.venv\Scripts\python.exe scripts/check_robot_connection.py --profile twinpulse-burger --ros-distro humble --identity-file C:\Users\jaewo\.ssh\twinpulse-burger\id_ed25519_automation --batch --board-snapshot
```

최신 무주행 보고서: `artifacts/robot-preparation/20260927T030159Z-12272ca4/result/report.json`.
과거 배터리실측 보고서: `artifacts/robot-checks/20260926T152444Z-80d890/report.json`.
UTC 디렉터리 날짜와 한국 측정 날짜가 다르다. report의출처/시각/UNKNOWN을
유지하고 전체 READY나실물안전인증으로 승격하지 않는다.
