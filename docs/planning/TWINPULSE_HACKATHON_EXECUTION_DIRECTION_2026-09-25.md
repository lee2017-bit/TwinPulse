# TwinPulse 해커톤·단일 워크스테이션 실행 방향

- 결정일: 2026-09-25 KST
- 성격: 제품 방향/우선순위 검토. 이 문서만으로 유료 API, 회사 설치, 실물 모터 구동 또는 GitHub push를 승인하지 않는다.
- 최신 상세 계획: [영어 UX·최종 데모 통합계획 H0~H8](TWINPULSE_HACKATHON_DEMO_MASTER_PLAN_2026-09-25.md). Astra 검토/후속 구현은 이 상세계획의 범위·완료 기준을 따른다.

## 확정 배치

```text
GitHub 가능 일반 PC: 릴리스 다운로드·무결성 확인·1GB 미만 조각 전달만
    → 승인된 VDI 파일 전송 →
RTX 3070 + Isaac Sim 6.0.1 워크스테이션:
    로컬 브라우저 + TwinPulse backend + LLM 요청 + Isaac 3D Build/Run
```

두 PC 사이 장면·초안·시뮬레이션 결과 교환은 요구사항이 아니다. O3 장면 교환은 미커밋 프로토타입에서 제거했고 O4 CPU planner-only는 계획에서 철회했다. VDI의 사내 LLM 접속 가능성은 워크스테이션에서의 접속 가능성을 증명하지 않는다. 승인된 Nebius 경로가 워크스테이션에 없다면 회사 설치만으로 새 이미지 생성은 불가능하다. 방화벽 우회/임의 proxy를 전제하지 않는다.

설치 패키지는 네트워크 없는 의존성 설치가 가능해야 하지만 실행의 기본값은 live provider다. `-Offline`은 LLM을 호출하지 않는 진단 모드일 뿐 제품 주 경로가 아니다. 개인 PC의 기존 온라인 원클릭 경로는 유지한다.

## 대회 기준과 제품 주장

[공식 규칙](https://nebiusglobalaihackathon.devpost.com/rules)은 실행 중 Nebius Token Factory 추론 API 호출 **또는** Nebius AI Cloud compute 실행과 NVIDIA 오픈 모델 1개 이상 사용을 요구한다. 따라서 로컬 Isaac과 Token Factory의 실제 Nemotron runtime 호출은 규정상 성립할 수 있다. 클라우드 GPU의 Isaac 실행은 필수 조건이 아니다. 완전 오프라인 데모만으로는 Nebius 사용 증거를 만족시키지 못한다. Physical AI 트랙은 하드웨어가 없으면 주요 모듈 동작을 보여주는 영상도 허용한다. 다만 [심사 안내](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works)는 현실 입력에 반응하는 실물 하드웨어 데모의 차별성을 강조한다. 이는 공식 요건과 수상 경쟁력의 차이다.

**제품 비전 정정:** 창고는 첫 시험 사례일 뿐 대상의 한계가 아니다. 사용자가 **AGV가 포함된 실제 현장 사진·설명**을 제공하면 로봇 후보와 주변 정적 환경으로 개략적인 3D Digital Twin 초안을 만든다. AGV가 추가로 주변을 스캔하면 로봇 좌표계와 장면을 정합하고 관측된 벽·장애물 위치를 보정해 Twin의 새 revision을 만든다. 그 갱신된 동일 환경에서 기존 주행경로/제어 설정과 새 최적화 결과를 공정하게 비교하고, 검증·승인된 주행 로직만 실물에 제한적으로 투입해 실측 차이를 보여준다. 사진에서 AGV의 모델·치수·센서를 확정하거나 단일 2D LiDAR scan으로 가려진 3D 높이를 측정했다고 주장하지 않는다.

**실물 데모 역할 확정:** 사용자가 보유한 TurtleBot3 Burger는 사진 속 산업용 AGV를 그대로 복제한 로봇이 아니라, AGV의 현장 scan·주행·비교 흐름을 축소해 실제로 수행하는 **데모 대역**이다. 사진 기반 장면과 실제 실험장 사이의 치수·축척 관계를 명시하고, 실물 동역학·센서·안전성은 TurtleBot 전용으로 검증한다. 사진 속 AGV의 예상 성능을 TurtleBot 실측으로 주장하지 않는다.

데모의 핵심 흐름은 **사진 속 AGV·현장 → 초기 3D Twin → AGV의 현장 스캔 → Twin 보정 전/후 차이 → 같은 보정 Twin에서 기존 경로와 최적 경로 비교 → 안전 gate를 통과한 실물 적용 및 시간·거리·안전성 비교**다. 여기서 ‘Twin 보정 효과’(장애물 위치·정합 잔차 등)와 ‘경로 최적화 효과’(같은 지도·시작/목표·로봇·속도 상한에서 시간·거리·성공률 등)는 서로 다른 실험으로 측정한다. 초기 지도에서 돌린 기존 경로와 보정 지도의 새 경로를 직접 비교해 최적화 개선율이라고 부르지 않는다.

현재 강점은 Gemma 관찰 → Nemotron 허용 도구 계획 → 로컬 의미/충돌 검증 → 실제 Isaac Build/2WD 완주라는 **초기 Twin 생성 구간**이다. 그러나 사진 속 특정 AGV의 profile 식별·확인, 실물 scan 수집, 좌표 정합·Twin revision 갱신, 동일 조건 경로 최적화 비교, 승인된 로직의 실물 적용은 **아직 구현·검증되지 않았다**. 사진 충실도와 객체 배치 일관성, 치수 도면 부분 실패, 회사 워크스테이션 연결/기동도 남아 있다. 한 장면의 route completion을 최종 폐루프 성립이나 범용 로봇 안정성으로 확대하지 않는다.

## 다음 구현·검증 순서 — H 통합계획으로 정정

1. **H0 Astra 검토:** 현재 소스와 오래된 checkpoint를 대조하고 [통합계획](TWINPULSE_HACKATHON_DEMO_MASTER_PLAN_2026-09-25.md)의 계약·의존성·완료 기준을 검토한다.
2. **H1 영어 UX:** 기존 입력/검토/시뮬레이션·오류·안전·설치 안내부터 쉬운 영어로 정리한다.
3. **H2 scene/mission 분리:** +X 주행 제약을 scene 생성에서 분리하고, 사용자가 정한 출발/목표의 자동 이동을 새 demo mission에서 막는다.
4. **H3 사진 충실도·실물 대역:** 일반 현장 입력과 사진-실험장 관계를 명시하고 TurtleBot 전용 profile을 준비한다. 다른 장소의 scan을 산업 사진 속 실제 현장 관측으로 취급하지 않는다.
5. **H4 Scan→Twin:** virtual/recorded scan으로 계약·좌표 정합·diff/검토/갱신/undo를 먼저 검증하고 실제 관측으로 이어간다.
6. **H5 navigation·후보 평가:** 동일한 보정 환경에서 기존/새 route·configuration의 시간·거리·성공률·안전성을 비교한다.
7. **H6~H7 실물·증거:** B0~B8의 준비/정지 gate를 통과한 TurtleBot으로 실행하고 지도 보정 효과·동일 지도 경로 개선·실물 재현을 각각 측정한다.
8. **H8 영어 제출/릴리스:** 공개 라이선스·영어 README/설치·테스트 안내·영상과 실제 모델/실행 증거를 점검한다.

회사 워크스테이션 inventory/API 도달성/cold offline 설치/Isaac actual gate는 배포 검증으로 유지한다. 회사 네트워크나 추가 VDI를 기다리는 것을 개인 PC 해커톤 제품 개발의 선행조건으로 삼지 않는다. cloud full Isaac/S6는 선택적 후속 확장이다. 기존 O1/O2 tested scope는 재사용하며 매 하위 작업마다 전체 배포 회귀를 반복하지 않는다.

## 영어 우선 제품·제출 UX gate

[공식 언어 요건](https://nebiusglobalaihackathon.devpost.com/rules)은 제출 자료가 영어이거나 영어 번역을 제공할 것을 요구한다. 제품 전체 소스코드나 내부 개발 이력의 영어화 의무와는 다르다. 다만 심사위원이 별도 설명 없이 데모를 이해하도록 공개 화면은 쉬운 영어 기본값으로 만든다.

1. React 제품 화면의 메뉴·단계·버튼·도움말·입력 검증·오류·안전 경고·대체 텍스트·문서 언어를 하나의 영어 사전으로 정리한다. `html lang=en`을 기본값과 연동한다. 필요하면 한국어 선택지를 같은 사전에 추가하되 혼용하지 않는다.
2. 창고 전용 영웅 문구와 고정 랙 삽화는 일반 AGV 현장으로 넓힌다. 단계명은 평이한 행동 언어를 쓴다. 예: `Add a site photo` → `Review the 3D scene` → `Run in Isaac Sim`; 실제 구현 전인 `Update from robot scan`·`Compare routes`·`Run the demo robot`은 동작하는 단계처럼 표시하지 않는다.
3. 전문 내부 용어(`revision`, `provenance`, `fixture`, `sidecar`, raw error code)는 1차 화면에서 풀어 쓰거나 상세 펼치기로 옮긴다. 예: `Scene version`, `Why this object is here`, `Sample scene`. 안전 정지 시 원인과 다음 행동을 쉬운 영어로 보여주되 진단 원문은 보존한다.
4. 공개 README의 첫 단락을 창고 한정이 아닌 AGV 사진→3D Twin→TurtleBot scan→경로 비교 비전과 **현재 구현 범위**로 정정한다. 영어 설치/테스트 절차, Nemotron/Token Factory의 실제 역할, 재현 제약, 실물 대역 관계를 명시한다. 한국어 내부 문서는 남겨도 제출하는 자료에는 영어 원본 또는 번역을 제공한다.
5. 영어 기본 화면 전체와 안전/오류 분기를 UI 테스트 및 데스크톱·축소 창 캡처로 확인한다. 영상은 영어 자막/설명과 실제 하드웨어 장면을 포함하고 제출 직전 문구·테스트 지침을 최종 검사한다.

2026-09-25 점검 현재 이 gate는 **미완료**다. `apps/twinpulse-web/src`에는 한글 포함 63줄(테스트 제외), `index.html`은 `lang=ko`, README는 영어 중심이나 창고 전용 소개, `docs/COMPANY_PC_INSTALL.md`는 한국어다. 이 기록은 제품 번역 완료를 뜻하지 않는다.

2026-09-25 정정 후 `scripts/verify_twinpulse.ps1 -SkipIsaac`는 Core 30, Provider 27, R1 9, R3 9, R4 6, R5/S2/S3 35, R6 11, React 10 및 production build PASS (`artifacts/runs/20260925-202829`). 샌드박스 내 임시 폴더 쓰기 거부로 두 차례 R1이 실패했으나 권한 경계 밖에서 같은 회귀가 PASS했다. 실제 Isaac, 새 Nebius 유료 호출, 회사 PC는 실행하지 않았다. 설치용 wrapper의 기본 live 옵션은 소스에서 확인했으나 **새 릴리스 설치 후 실제 기동은 미검증**이다.

장면 공유·내보내기는 다인 협업이나 외부 감사가 실제 사용자 시나리오로 확인될 때 재검토한다. 지금은 단일 PC 작업과 해커톤 품질에 집중한다. 초파리 connectome 기반 제어 등 장기 아이디어는 이 제출의 critical path가 아니다.
