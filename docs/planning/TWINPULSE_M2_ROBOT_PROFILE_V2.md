# TwinPulse M2 RobotProfile v2 교정 결과

- 날짜: 2026-09-13 KST
- 상태: **코드·local headless Isaac PASS / Full 앱 시각 확인 및 M2-C 3-image 평가는 미완료**
- 개발 저장소: `C:\Users\jaewo\Documents\Codex\TwinPulse`
- 자동 증거: `artifacts\runs\20260913-205327`

## 변경

- `2W`를 총 바퀴 2개가 아닌 좌·우 **2 driven wheels**로 정의했다.
- canonical `agv_compact_2wd_caster_v2`에 전·후 passive ball caster, 고정 center of mass/diagonal inertia와 8° roll/pitch 안전한계를 추가했다.
- 이전 저장 plan의 `agv_compact_diff_v1`은 local profile catalog가 v2로 승격한다. USD root의 RobotProfile metadata가 다르면 같은 scene ID라도 다시 Build한다.
- LLM plan의 도구를 scene/robot/task domain으로 분류하고 deterministic execution receipt를 추가했다. MCP는 외부 process/service adapter이며 실시간 wheel/motor loop가 아니다.
- runtime은 full roll/pitch/yaw를 읽고 자세 한계 초과 시 `unstable` safety stop으로 전환한다.
- `scripts\verify_twinpulse.ps1`이 compile/core/provider/Isaac 시험과 실행별 manifest/result/transcript를 자동 생성한다.

## 검증

- compileall: PASS
- core: 23/23 PASS
- provider: 8/8 PASS
- Isaac lifecycle: 3/3 PASS
- short run/pause/reset: 3/3 PASS
- generated/fallback/rollback: PASS
- 6.9m route: completed, goal error 0.049306m, max cross-track 0.000825m, max pitch 0.030598°, max roll 0.043333°, vertical range 0.000286m, geometric collision samples 0/1720.

## 미검증

- MinimalRendering에서는 렌더 screenshot을 생성하지 않았다.
- collision metric은 deterministic footprint overlap이며 PhysX contact impulse 계측은 아니다.
- Full 앱에서 재시작 후 v2 차체 방향을 1회 시각 확인해야 한다.
- 서로 다른 실제 이미지 3개 M2-C는 아직 실행하지 않았다.
