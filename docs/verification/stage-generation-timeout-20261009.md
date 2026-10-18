# 전체 생성 대기시간 설정 · 시험용 300초

2026-10-09 사용자 요청: 지금은 운영 배포가 아닌 시험이므로 대기시간을 5분으로 늘리고 직접 설정할 수 있게 한다. 이번 변경은 **설정·코드·오프라인 검증만** 수행했다. 추가 유료 추론/사진 전송/Isaac 실행/로봇 명령0, whole=false. 이전 실제5회 실패 기록·원응답·장부는 보존한다.

## 적용 및 사용

- TwinPulse 재실행 → **API keys → Model routing → Generation timeout (seconds)** → 숫자 변경 → **Save model routing**. 1~300초 정수이며 300초=5분. 빈칸·소수·범위 밖 입력은 저장 비활성화/API거절. 화면을 열거나 값을 편집하는 것만으로 저장·모델 호출하지 않는다.
- 기존 GPT 사진4000 / Nebius NVIDIA Nemotron 설계·수정20000 조합의 현재 저장 설정에 `generation_timeout_s=300`을 명시 적용했다. 네트워크 함수 차단 상태의 verify_stage_routing_settings.py 적용/별도 재읽기 모두 PASS; 실제 구성된 GenerationService 총timeout300.0, 기존 primary 설정·등록키 metadata 불변. 키 내용은 출력하지 않는다.
- **사진 관측+최초 설계+수정에 합산300초**를 허용한다. 각 단계마다300초를 새로 지급하는 것이 아니다. 일반 서비스의 기존 outer asyncio.wait_for와 pipeline deadline이 이 값을 사용하며 두 단계 HTTP 설정에도 연결한다. 기한 이후 도착한 응답의 취소·rejected/원문 보존 계약은 유지한다. 시간 만료 후 자동 재시도하지 않는다.
- credential-free 기존1.0 route에 optional 총시간 필드만 추가. 시간이 없는 구파일은 기존90초 유지하며 글로벌 운영 기본값을300초로 바꾸지 않았다. 다른 생성이나 실물의 정지·scan/input freshness·segment/motion/session 타이머는 변경하지 않는다.
- 명시 저장·busy guard·게이트웨이 재구성·atomic rollback 유지. 모델 변경/추천 조합 선택에서도 명시한 대기시간을 보존한다. 숫자 설정을 키 선택으로 오해하지 않도록 키 보호/삭제 잠금은 observer/planner만 조회한다. input revision의 안전한 metadata에 실제 총시간을 포함하여 시간 설정 변경이 revision에도 반영된다.
- host saved-stage 평가 scope도 저장 route/토큰한도와 **총시간**을 함께 결속한다. 구 scope의 시간이 없으면90초로 취급하며300초로 조용히 확대하지 않는다. 명시300초 scope+동일 저장 route만 허용한다. 이 변경은 이미 소진된5회/기존 승인 장부를 새로 만들거나 확장하는 승인이 아니다. verify_saved_stage_live.py는 scope와 일치하는 `--live-timeout-s 300` 전달을 지원한다. 역사적 고정경로 run_saved_stage_five.py는 종료된 배치 기록이며 재사용·재실행하지 않았다.
- `PROVIDER_OUTPUT_TRUNCATED`/출력 소진 시 **즉시 중단·추가 호출0** 정책은 유지한다. 정상 완료 JSON의 기존 bounded repair1은 시간 예산 안에서만 허용한다. 이번 변경으로 call_id↔근거ID 불일치가 해결되지는 않는다.

## 검증

- Python core/provider + stage routing/key registry/provider settings/split evaluation: **514 tests +279 subtests PASS**. 현재 관련 stage14(신규 총시간 저장/API/재시작/두 transport configs300/old90/입력revision/rollback/키잠금 포함), split12. scope300 일치 허용·90↔300불일치/boolean 거절·원 장부requests0 확인.
- Web 전체 **46 files/426 tests PASS**, 설정 UI11 포함: 기본90·명시300 저장/다시표시·빈값/0/301/소수 거절·모델/추천조합 변경 시300 보존·자동 저장0. API fixture 검증이며 실제 전체 브라우저 종단 인수는 아니다.
- TypeScript `tsc -b`, Vite build, Python 변경소스 py_compile, git diff --check PASS. 기존 jsdom canvas 미구현/큰chunk 경고 유지. 처음 존재하지 않는 test_split_evaluation.py를 지정한 시험은 실행 전 FAIL; 실제 test_split_provider_evaluation.py를 찾아 전체회귀로 검증했고 실패를 성공으로 바꾸지 않았다. 샌드박스 cache 권한 경고는 cache 비활성 및 승인된 동일 로컬 회귀로 처리, 새 설치/시스템 변경0.
- socket.create_connection/socket.socket.connect를 실패시키는 zero-call 설정 검사에서 저장300·서비스300·사진4000/설계20000·모델명 재읽기 PASS. 기존 백엔드 강제종료0; 코드·빌드는 앱 재실행 후 로드한다. 설정창에서 이후 저장하면 다음 생성부터 적용되며 진행 중인 생성에는 적용하지 않는다.

## 미검증 / 다음 작업

실제300초 LLM 재시험 **NOT_RUN**. 직전5/5 승인은 소진되어 새 유료 호출은 하지 않았다. 출력 한도와 시간 상한을 늘려도 성공 보장이 아니다. 실제 응답의 scene-1↔call-1 근거 참조 불일치, 생성 정확도, fresh actual Build/Run/Stop, 패키지/현장은 여전히 별도 검증 대상이다. 기존 dirty/raw/FAIL/UNKNOWN예약/로봇 guard/자동화 PAUSED를 보존했다.
