# N1 — 실제 방·Burger App → Isaac 표시 경로

2026-09-28 00:34 KST. 로봇 OFF 야간 오프라인 승인 범위.

## 구현 및 실제 확인

- 기존 App에 `내 방 · Burger Digital Twin` 검토 패널 추가. 보존된 사진2장과
  기존 공식 Burger9파일을 로컬 해시로 다시 확인한다. 임의 경로/외부 다운로드 입력 없음.
- 준비는 장면 변경 없이 검토 정보를 반환한다. 사용자가 근사 장면을 확인한 뒤
  표시 버튼을 누르면 기존 제어권을 확보하고 bridge가 Build 가능 상태를 보고할 때까지
  제한된 상태 조회를 수행한다. 변이 명령 자동 재시도 없음.
- 인증/CSRF/정확한 요청 shape → BedroomReview → 기존 CommandBroker의
  `build_site_scene` → production BridgeClient → IsaacSimulationAdapter → 기존 compiler.
  manifest descriptor와 scene/asset를 Isaac에서도 재검증한다.
- 기존 프로젝트 파일/다른 stage prim 보존. 소유권 검증 및 runtime 정지 이후에만
  표시 prim을 작성한다. 일반 scene-only Build는 이전 표시용 Burger를 제거한다.
- UI가 결과 receipt와 snapshot을 확인하고, 상태 조회 실패 시 현재 표시 확인을 철회한다.
  새 검토/새 페이지에서 이전 성공만으로 자동 Build하지 않는다.

## 증거

- `artifacts/bedroom-app-20260928-r3/result.json`: PASS. 실제 Chrome/App/API/broker/
  production bridge/Isaac 경로, browser6체크, 명령1회, 외부 browser 요청0/page error0.
- source와 dist 해시, scene revision, manifest hash, 모델9파일 해시를 같은 결과에 기록.
  원본 project 불변, 외부prim 보존, robot4mesh, robot physics API 없음, Run 권한 없음.
- `bedroom-desktop.png`, `bedroom-mobile.png`, `actual-Isaac.png`,
  `bedroom-product-stage.usda` 저장. 데스크톱/모바일 캡처 직접 확인; 모바일 overflow 없음.
  actual Isaac 결과는 이전 r2와 같은 근사 방 배치이며 가구는 단순 box envelope다.
- `artifacts/bedroom-app-regression-20260928-r2/manifest.json`: 전체 기존 오프라인
  검사 스크립트 PASS, core138/bedroom15(신규8 포함)/Web87(신규5 포함)/production build PASS.
  각 수치는 부분집합이며 총합으로 중복 집계하지 않는다.

## 실패 보존 / 수정

- 첫 로컬 sandbox 실행은 임시 폴더 접근 및 Vite child spawn 권한 오류였다.
  허용 검토를 거친 동일 로컬 테스트 명령으로 재실행했다. 시스템 권한/설정 변경 없음.
- 실제 통합 r1: UI가 lease 이전 permitted Build를 요구해 버튼 잠김; browser builds0.
  runner의 UTF-8 JSON 읽기도 Windows 기본 인코딩 오류. 둘 다 수정했다.
- r2 실제 통합 PASS 후 화면 여백/구성 이름을 개선하고 r3로 전체 경로를 재검증.
  r1 FAIL과 r2 PASS 원본을 그대로 보존한다.

## 사용 범위와 남은 일

업데이트된 로컬 App/Isaac adapter에서 `저장한 방·모델 불러오기` → 근사 장면 확인 →
`Isaac에 방 + Burger 표시`. 기존 사용자 실행창/프로세스는 종료하거나 자동 교체하지 않았다.
현재 파일 기반 카탈로그는 이 개발 저장소의 보존 artifact에 의존한다.
새 PC 배포 패키지에 사진/모델을 포함하는 검증은 아직 하지 않았다.

**N1의 App 검토→시각 장면 연결만 완료**. 사진 치수·robot pose 추정, sensor/world TF 미검증.
표시용 Burger는 구동 RobotProfile이 아니고, 기존 프로젝트의 임무를 자동 선택/수정하지 않는다.
geometry Build fingerprint와 robot asset manifest는 별도 증거다. 현장 정합, dynamics,
자율 임무, 로컬 충돌 방지/명령-관측 로그/비교는 N2–N6 작업이다.
실물/SSH/센서/모터/배포/유료 provider0, timeline Run0; 전체 실물 데모 완료가 아니다.
