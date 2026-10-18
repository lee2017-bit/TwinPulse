# TwinPulse — 실행환경 호환성과 비파괴 장면 저작 개선 계획

> 후속 통합: 로봇 없는 준비 5항목과 합친 구현 순서·인수 기준은 [Sol 통합 상세계획](TWINPULSE_INTEGRATED_OFFLINE_SOL_WORKPLAN_2026-09-29.md)을 따른다. 본 문서는 회사 사례 분석과 UX 기술 상세의 참조로 유지한다.

- 작성: 2026-09-29 KST. 상태: **현재 코드 대조·계획 작성 / 신규 기능 구현·재현시험 미실행**.
- 기준 root: `C:\Users\jaewo\Documents\TwinPulse`. 기존 미커밋 변경을 포함한 현재 작업 트리를 검토했다. 회사 PC의 GitHub 배포본으로 원복하거나 그 배포본을 수정하는 계획이 아니다.
- 입력: 사용자 회사-PC 오류 보고서 `TwinPulse_범용_환경호환성_및_Engine_Startup_오류_분석_개선요청.md`, SHA-256 `53702b9baed0cfcdbbcfb694892bba6f4e2c96ca2fb24aab739665941bb469ed`; 생성/추가/변경 모드, 조명, 주거 공간 다양성, 대화형 안내 요청.
- 첨부의 복구 명령은 사례 자료로만 읽었다. 환경 수정·패키지 복사·설치·유료 호출·로봇 접속·배포·commit/push를 하지 않았다. 이번 문서 검토를 기능 PASS로 기록하지 않는다.
- 기존 적응형 아키텍처 계획의 A1b/A2/A3/A4와 연결하는 보완 실행계획이다. 이전 계획의 최초 ‘미착수’ 문구보다 최신 PROJECT_MEMORY의 부분 구현 기록이 현재 상태의 기준이다. 새 야간 일정이나 자동 실행 승인을 만들지 않는다.

## 1. 판단과 우선순위

사용자 제안은 타당하다. 단, 세 모드를 프롬프트 문구만으로 구현하거나 특정 NumPy 버전을 모든 PC에 강제하는 방식은 채택하지 않는다.

1. **어디서 시작에 실패했는지 앱에서 보이게 한다.** 실행환경 진단은 별도 필수 클릭이 아니라 시작 흐름 내부에 넣는다.
2. **장면을 덮어쓰지 않고 이어서 작업하게 한다.** 프로젝트·장면 revision·객체 ID와 생성/추가/변경 계약을 먼저 연결한다.
3. **항상 읽을 수 있는 기본 화면을 제공한다.** 보기용 조명·카메라와 실제 장면 조명을 분리한다.
4. **공간에 맞는 객체를 선택하고 판단 근거를 설명한다.** 창고 도구를 주택에 억지로 적용하지 않는다.
5. 이 경로를 기존 방+Burger+저장 센서/임무 로그와 통합한다. 수동조작이나 새 자산 플랫폼 자체를 최종 목표로 삼지 않는다.

범용 호환성은 ‘모든 PC에서 무조건 실행’이 아니라 **검증된 조합에서는 실행하고, 미검증/불일치 환경에서는 정확한 상태와 복구 선택지를 제시하는 것**으로 정의한다.

## 2. 회사 사례와 현재 코드의 근거 수준

| 항목 | 확인한 사실 | 아직 확정하지 못한 것 / 계획 판단 |
|---|---|---|
| 회사 PC 복구 | 사용자 최신 설명은 복구 후 정상 작동. 첨부는 Isaac 6.0.1/Python 3.12.13에서 NumPy 2.5.3과 prebundle 2.3.1의 import 경로 및 DLL A/B를 기록 | 회사 배포 Git revision·전체 실행 로그를 현재 코드와 대조하지 못함. 현재 PC에 동일 오류가 있다는 뜻은 아님 |
| native 오류 | 첨부에서 일반 Python import는 성공하나 SimulationApp 초기화 중 SciPy→NumPy FFT DLL 오류. NumPy 폴더/metadata만 복사한 경우 실패, 대응 `numpy.libs` 포함 복구 사례 | 공존하는 버전 수만으로 충돌 확정 불가. 2.3.1 전역 고정이나 폴더 덮어쓰기를 제품 정책으로 채택하지 않음 |
| launcher | `process_manager.py:246` 파일/구성 확인, `:536` backend/engine 조기 종료 감지와 handshake 검증 존재 | ‘종료 감지가 없다’는 진단은 현재 코드에는 부정확. 살아 있는 프로세스의 초기화 지연/정체/원인 전달을 보강해야 함 |
| 실패 화면 | `process_manager.py:297–311`에서 engine ready 뒤에 브라우저를 열며 시작 예외에서 프로세스를 정리 | 엔진 시작 실패를 웹에서 안내하려면 startup 상태와 UI 수명을 분리해야 함 |
| 초기 예외 | `scripts/twinpulse_engine_host.py:34–37`의 import/SimulationApp 생성이 main의 예외 처리보다 먼저 실행 | 초기 DLL 오류의 구조화된 단계/원인 기록이 빠질 수 있음. 가장 바깥 stdlib reporter부터 필요 |
| 로그 | `process_manager.py:801`은 전체 파일을 읽은 뒤 마지막 2048바이트를 취함. 일부 tail/문자열만 오류에 반영 | 큰 로그 처리와 최초 원인 보존·민감정보 제거가 충분한지 별도 검증 필요 |
| 설치 | 기존 installer는 App venv와 명시 Isaac 실행 경로를 사용하고, hash 기반 offline release 도구도 존재 | 새 설치기를 다시 만들거나 현재 installer가 Isaac NumPy를 손상했다고 단정하면 안 됨 |
| 장면 작성 | `SceneCompiler.compile_site_scene`는 fingerprint가 다르면 소유 root 교체. 실패 복구·PhysicsScene 보존 경로 존재 | rollback은 있지만 사용자가 기대하는 append/targeted edit 계약은 아님 |
| 화면 | `_ensure_presentation`은 고정 camera pose와 Dome 650/Distant 2500 등 값을 다시 설정 | 회사 화면의 과노출 원인으로 확정한 것은 아님. viewport light rig·exposure·material·camera 조합 재현 필요 |
| 다양성 | `tool_catalog.py`는 rack/pallet 중심 도구와 v2 `create_box_obstacle` 지원. provider v2에는 non-rack을 상자로 처리하라는 지침 존재 | ‘모든 버전이 무조건 rack 강제’는 아님. 그러나 의미 있는 가구 카탈로그와 가구별 시각 모델은 부족 |
| 표현 | compiler는 일반 객체를 주로 cube/cylinder로 작성. App의 상태 일러스트도 창고 rack 표현 | 실제 장면 모델과 UI 일러스트를 각각 공간 맥락에 맞춰야 함 |
| 지속 프로젝트 | 빈 프로젝트 생성/목록은 있음. 현재 선택 변경은 종료 후 재시작. `prepare_project_burger_visual`은 빈 레코드라도 기존 프로젝트면 거절 | 새 프로젝트→방 작성→Burger 준비의 자연스러운 연결이 미완성. A2 작업에 포함 |

현재 회귀의 마지막 기록은 `docs/verification/adaptive-project-create-a2-20260929.md`의 core176/Web131/build PASS, Isaac NOT_RUN이다. 이는 **이 문서의 변경안을 시험한 결과가 아니다**. 기존 실제 Isaac 시각 검증도 회사 PC 호환성·새 편집 기능·실물 임무 성공으로 확장하지 않는다.

## 3. 실행환경: 빠른 정상 시작, 실패해도 남는 진단 화면

### 3.1 시작 흐름

`App 시작 → 빠른 구성 확인 → 로컬 상태 화면 → Isaac 초기화 진행 → extension/bridge 확인 → 작업 가능`

- UI에는 ‘PC 점검을 먼저 누르세요’를 추가하지 않는다. 현재 명시 연결/시작에 통합한다.
- backend가 준비되면 UI를 열고 engine 상태를 구독한다. 엔진 실패 때 조작은 비활성화하되 오류 설명·저장 프로젝트 열람·진단 내보내기는 유지한다.
- backend 자체도 못 뜨면 launcher가 로컬 요약/로그 위치를 제공한다. 브라우저가 항상 열릴 것이라고 가정하지 않는다.
- engine 실패 시 owned engine만 정리하고 진단 UI를 유지하는 degraded lifecycle을 설계한다. App 종료/명시 취소에서는 기존 소유 프로세스 정리·단일 인스턴스 잠금을 유지한다. 재시도 중 중복 엔진 금지.
- 단계 제안: `CONFIG_CHECK`, `ENGINE_SPAWN`, `KIT_INITIALIZING`, `SIM_APP_READY`, `EXTENSION_READY`, `BRIDGE_READY`, `READY`, `FAILED`, `CANCELLED`. 진행률 백분율을 지어내지 않는다.
- engine_host의 Isaac import 이전에 stdlib 전용 reporter를 둔다. init 예외, exit code, 마지막 단계, 시간, 최초 관련 예외와 제한된 연쇄 원인을 기록한다. native hard crash는 부모 프로세스가 exit/log로 보완한다.
- 단계별 시간과 전체 상한을 구분하고, 최초 shader/cache 지연은 실패 원인과 구별한다. timeout 무제한 연장이나 키워드만으로 ‘NumPy 충돌 확정’은 금지한다.

### 3.2 진단 계층과 호환성 프로필

- 매 시작: 선택한 Isaac root/실행기 존재, App release·설정 fingerprint, 필요한 asset/cache manifest 같은 저비용 검사.
- 최초 사용·환경 변경·실패·사용자 상세진단 요청: 별도 프로세스에서 Python/패키지 출처, native import, 필요한 경우 SimulationApp smoke를 수행. **매번 실제 시작 전에 SimulationApp을 두 번 부팅하지 않는다.**
- 정상 시작에서도 실제 SimulationApp 문맥의 import 출처를 기록한다. standalone 검사 통과만으로 준비 완료 처리하지 않는다.
- 프로필에는 OS/아키텍처, Isaac 정확한 build·Kit/Python, GPU/driver, App/adapter 버전, 검사 범위/시각을 둔다. NumPy/SciPy 버전·`__file__`·native 모듈 및 관련 DLL 출처를 필요한 범위에서 조사한다. 전체 환경변수/자격증명 덤프 금지.
- App venv 의존성과 Isaac vendor runtime을 분리 유지. Isaac Lab/torch/torchvision/RSL-RL은 해당 학습 기능을 쓸 때만 별도 프로필로 확인한다. 기본 방 작성에 Lab 스택을 요구하지 않는다.
- `validated / untested / incompatible`는 **기능·실제 검사별** 상태다. 회사 사용자 보고를 vendor 공식 지원 matrix로 승격하지 않는다. 비슷한 버전도 검사 없이 verified로 표시하지 않는다.
- 설치가 오프라인이라는 것, Kit asset/cache가 준비된 것, 모델 추론이 오프라인이라는 것을 각각 표시한다.

### 3.3 복구와 지원 자료

- 우선 ‘무엇이 선택되었고 무엇이 로드되었는가’를 비교한다. 잘못된 root 선택은 앱 설정에서 바로잡고 재검사한다.
- vendor 환경 충돌은 진단과 **미실행 복구 제안**까지. 자동 pip downgrade/패키지 복사/PYTHONPATH 전역 변경은 하지 않는다. 사용자 선택 시 변경 대상·백업·검증·복구 범위를 사전에 표시한다.
- App 소유 버전별 venv 교체와 Isaac 설치 폴더 복구를 구분한다. vendor 복구 rollback을 증거 없이 보장하지 않는다.
- 내보내기는 allowlist 기반 JSON+제한 로그. 프로젝트 사진/회사 데이터/키/토큰/전체 경로는 기본 제외 또는 마스킹, 공유 전 미리보기. 원본 로그는 변경하지 않는다. bounded seek/ring buffer로 읽는다.

공식 Python 환경 문서는 SimulationApp 이후 Omniverse API를 import해야 하는 runtime 순서를 설명한다. 이는 초기화 전후 문맥을 나눠 확인하는 근거이지, 회사의 특정 NumPy 버전 조합을 인증하는 자료는 아니다. [NVIDIA Python Environment](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/python_scripting/manual_standalone_python.html)

## 4. 세 가지 저작 모드: UI와 실제 데이터 처리 모두 분리

기존 live/offline/replay 실행 모드와 별개의 **장면 작업 의도**다. 상단에 현재 프로젝트·장면 revision과 함께 상시 표시한다.

| 사용자 모드 | 실제 동작 | 보존 규칙 |
|---|---|---|
| 새로운 환경 만들기 | 첫 빈 화면의 기본값. 새 장면 revision/분기에서 초안 생성 후 선택하여 표시 | 기존 장면/사진/로그를 지우지 않음. 기존 프로젝트가 있으면 새 장면임을 명시 |
| 현재에 추가하기 | 현재 revision을 기준으로 새 ID의 객체만 추가 | 기존 객체 형상·위치·재질·ID·외부 prim 불변. 자동 재배치가 필요하면 변경 모드 제안 |
| 현재에 변경하기 | 선택 ID의 허용 속성 변경·교체·명시 삭제 | 대상 밖 객체 불변. 삭제 목록·이동 대상·변경 전후를 보여주고 되돌리기 지원 |

- 기존 장면을 열었을 때는 ‘추가’를 기본 제안하고 명시 변경 요청은 ‘변경’으로 안내한다. 명령 의미와 선택 모드가 충돌하면 자동 삭제하지 않고 필요한 한 가지 질문/전환 제안을 한다.
- ‘침대를 창가로 옮겨’는 새 방 생성을 뜻하지 않는다. 대상 침대/창문이 하나로 특정되면 그 ID만 변경한다. 사진의 창문 방향만으로 미터 좌표가 검증되었다고 보지 않는다.
- typed `SceneChangeSet` 제안: schema version, project/scene ID, base revision, operation ID, intent, add/update/delete, 근거/가정, 예측 결과 fingerprint. **기존 v1/v2 plan 필드를 몰래 추가하지 말고 새 versioned envelope로 감싼다.**
- provider는 현재 scene 요약·허용 ID·모드·가용 catalog를 받는다. 서버 validator/compiler가 모드 규칙을 강제하며 LLM의 ‘보존했습니다’ 답변을 신뢰 근거로 삼지 않는다.
- 미리보기→한 번 적용→적용 receipt/revision. stale revision/중복 요청은 conflict 또는 동일 receipt로 처리하고 두 번 생성하지 않는다. 변경 도중 취소/실패는 원본 보존. rollback 자체 실패는 불명 상태로 남겨 재조회 전 다음 쓰기를 막는다.
- 자동 전체 root 교체 대신 선택 prim 변경을 우선한다. 성능상 재컴파일이 필요한 경우에도 영향받지 않은 객체·자산·view 상태 보존을 검증하고 그 전략을 기록한다. 기존 PhysicsScene singleton/외부 root 보존을 회귀에 넣는다.
- geometry 변경은 기존 보정/경로·평가의 revision을 낡은 것으로 표시한다. 임무 실행 중 편집은 중단/일시정지의 실제 완료 상태와 조정하며 현재 실행에 몰래 적용하지 않는다.
- Undo는 장면 revision 복원이다. 과거 실제 로봇 이동을 되돌렸다는 뜻이 아니다.
- A2 빈 프로젝트·recipe import·Burger 준비를 한 흐름으로 연결한다. 빈 ProjectRecord를 기존 완성 자산과 구별하되 실제 기존 자산/원본은 덮어쓰지 않는다. 프로젝트 전환은 사용자가 셸 재시작을 알 필요 없도록 owned 프로세스의 정상 종료/재시작을 앱에서 조율한다.

## 5. 보기: ‘Light Off / Stage Light’를 사용자의 해결 과제로 남기지 않기

- 기본은 **기본 보기**: 중립적 보조 조명, 과한 반사/노출을 피한 재질, 장면 범위에 맞는 자동 프레이밍. 추가/편집 때 사용자 카메라를 강제로 초기 위치로 돌리지 않는다.
- 간단한 선택: `기본 보기 / 실내 보기 / 장면 조명`, 밝기 조절, `화면 맞춤`, `보기 초기화`, 위/사선 시점. robot 시점은 실제 정의된 카메라가 있을 때만 제공한다.
- 보기용 light rig/exposure는 장면 데이터·센서 렌더링 조건과 분리한다. 사용자가 실제 조명으로 저장할 때만 scene revision에 반영한다. 비교 실험에서는 조명/노출 설정을 고정해 기록한다.
- 방 크기/중심 AABB로 camera/clip 범위를 계산하고 벽/천장 때문에 내부가 가려지는 문제는 단면 보기나 보기 전용 숨김으로 해결한다. 충돌체 삭제와 혼동하지 않는다.
- 현재 고정 Dome/Distant 숫자를 무작정 낮추는 것만으로 완료하지 않는다. 실제 viewport rig·tone mapping·재질·노출의 조합을 기록하여 재현한다.
- 렌더 수용 기준: 작은 방/큰 창고/밝은 재질/어두운 재질에서 바닥·객체 경계·Burger가 구분되고, 극단적 검정/백색 clipping과 카메라 가림이 없는 캡처. 통계 검사와 실제 이미지 검토를 함께 한다. 검정 화면 검사 하나로 합격시키지 않는다.

Kit의 조명 메뉴에는 stage lighting과 camera/light rig 구분이 있으며, RTX post-processing에는 exposure/tone mapping 제어가 있다. 제안 UI는 이 원리를 사용하되 **설치된 Kit adapter에서 실제 지원 API를 확인한 뒤 구현**한다. [Kit lighting 변경기록](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.viewport.menubar.lighting/latest/CHANGELOG.html), [NVIDIA Post-Processing](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx_post-processing.html)

## 6. 공간 이해·가구 다양성·대화형 안내

### 6.1 ‘랙 종류 늘리기’보다 의미 기반 객체 선택

`요청/사진 → 공간과 객체 후보 → 가정·확인사항 → 로컬 catalog 검색 → 크기/배치 검증 → 기존 도구의 선언형 조합 → 미리보기`

- 공간은 주거/창고/사무실/혼합/불명으로 분류하되 사용자 명시 정보가 우선한다. 한국어 입력만으로 한국형 아파트를 확정하지 않는다. 불명확하면 편집 가능한 가정으로 제시한다.
- 1차 범위: 침대·옷장·책상·의자·소파·식탁·수납장과 기존 창고 rack/pallet. 기존 사용자 방+Burger를 첫 인수 사례로 삼는다. 처음부터 인터넷 전체 자산 검색기를 만들지 않는다.
- catalog: semantic category, 스타일/색/용도, 치수 범위·단위·축·pivot, 로컬 asset ID/revision/hash, 출처·라이선스, 시각 상세도, collision envelope와 검증 상태. 외부 USD reference/texture 의존성도 검증한다.
- 먼저 기존 로컬 자산과 결정적 parametric 가구 조합을 사용한다. 형상 없는 단순 box fallback은 ‘단순 대체 모델’이라고 표시한다. 외부 다운로드는 별도 허용·출처 확인·캐시 경로로 후속 도입한다.
- 미관용 mesh와 계획/충돌용 형상을 분리한다. 자산을 예쁘게 바꾼 것만으로 실측 치수·물리 접촉·로봇 주행을 검증했다고 표시하지 않는다.
- Asset 선택은 가용성→범주→치수 적합→스타일 순. 다양성을 위해 매번 랜덤 교체하지 않고 선택한 asset/seed/revision을 저장한다. 사용자가 가구 하나만 다른 스타일로 바꿀 수 있게 한다.
- 기존 ToolCatalog와 유한 composite를 재사용한다. 모델이 작성한 Python/셸을 실행하거나 임의 URL 자산을 즉석 로드하는 방식은 사용하지 않는다.

### 6.2 대화는 실제 작업 상태를 설명

진행 메시지는 ‘요청 이해 / 적용할 가정 / 사용한 자료 / 변경 요약 / 결과·제약’으로 구성한다. 내부 추론 전문을 노출하거나 기다리는 동안 허구의 작업 단계를 출력하지 않는다.

예시(실제로 로컬 catalog만 쓰는 경우):

> 주거 공간으로 해석했습니다. 한국형 아파트 스타일은 가정이며 변경할 수 있습니다. 사진에서 확인되는 침대·책상·옷장은 유지하고, 로컬 가구 목록에서 소파 후보를 고르겠습니다. 사진만으로 확인되지 않는 치수는 추정값으로 표시합니다.

> 소파 1개를 추가했습니다. 기존 12개 객체의 위치와 재질은 바뀌지 않았습니다. 온라인 자료 조회는 하지 않았고, 사용한 모델은 로컬 기본 소파입니다.

마지막 문장은 실제 변경 receipt가 확인된 뒤에만 표시한다. 실제 조회/다운로드가 없으면 ‘관련 데이터를 가져왔습니다’라고 말하지 않는다. 저장 provider 재생도 새 LLM 판단처럼 보이지 않도록 표시한다. Chat UI의 답변과 3D 선택 대상/변경 내역을 연결한다.

## 7. 실행 단위와 완료 기준

| 단계 | 실제 제품에 연결할 변경 | 의존성 | 완료 기준 |
|---|---|---|---|
| U0 기준 고정 | 기존 release/dirty source fingerprint·회사 보고서·저장 scene 골든·새/추가/변경 기대 사례 | 없음 | 원본 불변, 회사 관측/현재 확인/가설 분리. 기존 v1/v2 hash와 실패 이력 고정 |
| U1 시작 상태/진단 | process manager + engine_host + backend startup API + React 실패/진행 화면 | U0 | DLL형 init 예외·hard exit·살아있는 hang·backend 실패·취소·재시도 테스트; 정상 actual Isaac 한 번 부팅으로 ready; 실패 UI와 최초 원인 보존 |
| U2 비파괴 작성/A2 | project/recipe/Burger 연결, intent/change-set, compiler 적용, UI 모드/preview/undo/전환 | U0, U1 상태 계약 | 새 방 작성→추가→한 객체 변경→취소/실패 복구→저장/재열기. 비대상 객체·외부 prim 불변, stale/중복 요청 검증; actual Isaac stage/USD 확인 |
| U3 기본 보기 | compiler presentation + typed view command + App 밝기/프레이밍 | U2의 scene/view 분리 | 방/창고·밝고어두운 재질 캡처 검토, 편집 후 사용자 camera 보존, 보기 변경으로 geometry/hash 불변 |
| U4 공간별 가구/설명 | ToolCatalog/composite/로컬 catalog + provider 문맥 + 결과 receipt 기반 대화 | U2, U3 | 주거에 강제 rack 없음, 창고 기능 보존, 단순 대체 명시, 가구 ID/출처/치수/충돌형상 추적, 추가·변경 보존 테스트 |
| U5 통합 리허설/배포 검증 | 기존 방/Burger·프로젝트별 관측/임무 이력·평가와 전체 App 흐름 연결 | U1–U4 | App→Isaac→저장→재시작→계속 편집 end-to-end; 기존 세션/정지/임무 fake 회귀, 환경별 증거와 미검증 목록; 회사 조합은 해당 PC 재검사 전 미검증 |

첫 구현 묶음은 **U0+U1**, 다음은 **U2**다. U3의 API 조사는 함께 준비할 수 있으나 실제 merge/완료는 scene/view 경계를 맞춘 뒤 한다. 가구 수를 늘리느라 시작 실패·덮어쓰기 문제를 뒤로 미루지 않는다. 정확한 공수는 U0 기준 측정 후 산정하며 ‘로봇을 켜면 전부 완료’ 같은 시각 약속을 하지 않는다.

### 반드시 포함할 회귀/인수 사례

1. 환경: standalone 성공/SimulationApp 실패, warning만 있는 정상 시작, 잘못된 root, native exit, progress 정체, cache cold start, 취소 후 재시도·중복 시작. fake 통과와 실제 runtime 통과를 별도 보고.
2. 편집: 소파 추가 후 기존 침대 좌표/재질 불변; 침대 이동 때 책상 불변; 기존 floor 중복 금지; delete는 명시 목록만; 외부 prim·PhysicsScene 보존; Undo/재열기; revision 충돌·쓰기 실패·rollback 실패·late reply.
3. 맥락: 사용자 방, 일반 아파트, 창고, 혼합 작업실, 불명확 사진을 고정 입력으로 비교. 단순 fixture 통과를 실제 모델 의미 이해의 품질 검증으로 부르지 않음. 새 유료 품질 실험은 별도 허용 범위에서만 시행.
4. 자료: 자산 누락/라이선스·출처 미확인/단위·축 불일치/외부 reference/경로이탈은 대체 안내 또는 거절. 미터 추정·사진 가정·저장 scan·검증 TF를 혼합하지 않음.
5. 운영: 엔진 실패 화면에서 저장 자료가 남음, 로그 내보내기에 secret/회사 사진 없음, 프로젝트 전환에서 다른 프로젝트 세션·승인·view가 섞이지 않음.
6. 최종 흐름: ‘방 만들기→기존 Burger 표시→소파만 추가→침대만 변경→저장→종료→이어보기→저장 임무 재생’에서 변화/원본을 추적. 실물 transport 잠금과 기존 정지 기준은 그대로.

## 8. 기존 계획과의 통합 / 남겨 둘 경계

- **A1b**: EngineCapabilities는 기능 계약이다. 설치 호환성/시작 상태를 새 기능 플래그 하나로 뭉치지 말고 RuntimeProfile/StartupStatus로 참조한다.
- **A2**: 위 U2를 최우선 지속 프로젝트 수직 흐름으로 포함한다. 목록·빈 record만으로 A2 완료가 아니다. 사진/자산/센서/임무 이력의 project-local 참조도 U5에서 확인한다.
- **A3/A4**: 변경 receipt와 관측 근거·자산 provenance, 시각 품질/편집 보존/시작 신뢰성을 평가 축으로 추가한다. 기능 PASS와 회사 호환성/실물 성공을 합산해 하나의 PASS로 만들지 않는다.
- **A5 이후**: 모델 자동 탐색·라우팅·자기 개선은 이 작업의 선행조건이 아니다. 가구 composite는 기존 허용 도구의 유한 조합부터 연결한다.
- 기존 로봇 연결준비 통합·로그·방 좌표 결속·로컬 충돌 방지 계획은 없어지지 않는다. U2의 revision과 U5의 project-local 기록을 공통으로 쓴다. 임무 내 이동마다 승인을 묻는 구조로 되돌리지 않는다.
- 로봇 OFF에서도 U0–U5의 코드/가짜 경로/로컬 Isaac 시각·저장 검증은 가능하다. **회사 PC 재현, 현재 실제 TF·odom/scan 정합, 변경된 로봇 코드 배포·실제 정지·주행은 별도 현장 검증**이다. 사진 기반 3D의 치수는 계속 추정으로 남는다.

## 9. 구현자 인수 지침

현재 AGENTS/Memory/Baseline와 본 문서를 읽고 첫 묶음 U0→U1부터 구현한다. 이 문서를 구현 승인의 대용으로 사용하지 말고 다음 사용자 구현 요청 범위를 따른다. 기존 코드 경로를 연결하고, 단계마다 diff·관련 회귀·actual runtime 증거/NOT_RUN·잔여를 남긴다. 예전 GitHub 복원, 새 저장소, 설치환경 일괄 정리, NumPy 강제 교체, 새 provider 유료 호출은 포함하지 않는다. 원본 실패를 지우거나 기준을 완화하여 완료 처리하지 않는다.
