# Reviewed route admission and idle review lifecycle

Baseline v1.0.303 connects conservative current-route revalidation and a parked review lifecycle to the existing App, native worker and actual Isaac route preview. Small candidate pose changes no longer require bitwise equality, and a user or Isaac review does not keep a robot worker or its 45-second budget running.

**C4 remains PARTIAL; whole readiness=false.** Python and lower actual Isaac checks passed, but the attempted combined Kit-process/native journey failed safely on input expiry before driving. Physical qualification and measured localization accuracy are not established. Robot, SSH, serial, real sensor/motor commands, deployment, paid calls, installs, settings, commit/push, unrelated termination and new agents were zero. Existing raw, dirty edits and failures are preserved; heartbeat remains PAUSED.

## Connected implementation

1. The registered factory opts into additive `current-goal-preview-2.0`. V1 defaults and strict checks remain unchanged. V2 retains the immutable review, route and goal digest. It checks current observations, the complete original route from both reviewed and newly observed starts, nominal obstacles and every intersecting grid cell. It does not silently substitute a different route.
2. Candidate admission is bounded to translation at most 0.010m and wrapped yaw change at most 0.020rad. These are design bounds, **not measured sensor accuracy or physical acceptance**. An additional 0.010m is added to the existing circular clearance. Missing, conflicting or occupied cells along the route still block; unrelated far cells need not invalidate the review.
3. Boot, release, source, origin, project, epoch, alignment, room transform, room revision, bounds and footprint remain exact. Only a fresh explicitly owned session may have a different session ID. This comparison alone grants no ownership, qualification or movement permission.
4. Before Isaac/user review, the owned idle worker is normally closed. Both motor and sensor cleanup must be confirmed before the server keeps a memory-only review reservation. There is no active sensor, keeper, current pose or input gate during this wait.
5. Single explicit Confirm consumes that reservation, rereads the accepted original reference and opens a new wheel-disabled observation worker. The full reviewed route is rechecked against its fresh observations. The reviewed handoff then adopts that same new worker and its original gate; there is no active budget reset or independent scope7 bootstrap. Its total active 45s, scan/pose200ms, input250ms, segment50ms, .03m/s/.20rad/s and current qualification guards remain unchanged.
6. Rejected fresh pose or failed preparation closes the owned idle worker without restoring approval. Cancel, expired confirmation, changed reference and new goal discard the reservation. Refresh/history do not create workers or resume execution.
7. Completing Isaac does not make its receipt irrevocable. Stop or shutdown now immediately invalidates even a completed receipt while keeping historical completion data. The continuous execution guard prevents that cancelled receipt from authorizing a handoff.
8. English Web status says the robot is idle during review and Confirm requires a fresh position/full-route check. The reviewed start remains explicitly historical; no automatic motion or current physical position is advertised.

## Final regression

- Frozen-source Python: **75 tests /169.716s PASS**; all19 code/test hashes match before and after. The selection covers reviewed-route/v1 contracts, full reference wire/idle/native handoff, chat API, exact demonstration, mission, source identity, admission and cleanup. It is selected-suite acceptance, not a whole-product run.
- Added cases include small jitter, full-route unknown/occupied/missing/conflicting cells, changed context/transform/footprint/freshness, rehashed weaker-policy rejection, added clearance, nonidentity transforms, first nonzero rejection after Motor Enable, lost SIM receipt, parked owner/reference/cleanup, expired confirmation and no polling retry.
- Actual local stdin/controller/native-loop positives use the **existing matcher with reactive synthetic rays and no frozen pose**. The parked case opens a distinct job/session and then uses that same new worker to arrive. A virtual PC clock advance of90s during the parked interval produces no new journal activity; it is not a physical 90s observation. The separate stable-estimator fixture is retained only for isolating the post-enable negative test.
- Web: **319 tests /42 files /23.50s PASS**. TypeScript/Vite production build PASS. All3 manifest hashes match. The pre-existing >500kB chunk warning remains.
- JS `assets/index-DR94lH27.js`: `a9d6b4de7f9477fefdb6b9f7418d38e29c31cd24ff884cfba4553b458a2ea2fa`.
- CSS `assets/index-DjLK5Ycj.css`: `dd4b3989e3daf39c46a597024fb391bf8019bd573920d13b1f302b9e7f072041`.
- HTML: `f422b54656df23985de27d5211678ff0043a82e7f4855580449c750bcfb46384`.

## Actual Isaac result

The [final result](../../artifacts/verification/goal-revalidation-isaac-20261006-final/verification.json) and [owned stage](../../artifacts/verification/goal-revalidation-isaac-20261006-final/goal-demonstration-stage.usda) use the existing headless Isaac runtime with explicit synthetic room/sensor input. Both preserve the exact v2 review and route, use Build/Run/Pause, observe Burger PhysX arrival, preserve the foreign prim and invalidate receipts after stage replacement. All9 runtime hashes match.

| Goal XY m | Terminal XY m | Observed poses | Physics steps | Service elapsed s |
| --- | --- | --- | --- | --- |
| 0.30 and minus1.8 | 0.2605343 and minus1.8000127 | 211 | 207 | 3.718 |
| 0 and minus1.35 | 0.0021051 and minus1.3895704 | 491 | 485 | 7.906 |

Arrival uses the unchanged SIM tolerance0.04m. This lower check does not qualify physical movement, Chrome, the embedded-viewer journey or the full native handoff under rendering load.

## Preserved failures and corrections

- First two new matcher/park tests failed with `REVIEWED_ROUTE_INVALID`. Inverse-transform round trips differed at floating-point precision. The checked-route endpoint now accepts only a numerical gap up to1e-12m, checks that gap too and never modifies waypoints. A geometrically different endpoint still fails.
- The next two-test run passed fresh matcher admission but parked handoff failed `GOAL_HANDOFF_SOURCE_CHANGED`. The PC still compared the terminated review session ID exactly. Its v2 check now matches all other source fields exactly; the native fresh-pose/full-route check and ownership gates remain.
- Initial new test-module run had3 fixture errors: missing optional close argument and excessive default grid budget in two tests. Fixtures were corrected; product limits were not increased. Focused23 tests then passed10.082s. Final75 is the acceptance result.
- Nonidentity-transform review endpoint canonicalization is v2-only, so SIM preserves the exact requested room goal while native inverse-path validation still checks its geometry.
- The [combined attempt](../../artifacts/verification/chat-goal-native-isaac-20261006/verification.json) remains **FAIL**. Its [native report](../../artifacts/verification/chat-goal-native-isaac-20261006/synthetic-peer-0/idle-report.json) records `INPUT_DEADLINE_EXPIRED`, empty published commands and confirmed cleanup. Its full PC journal and synthetic reference remain below that run's runtime directory.
- In that attempt, PC watch31 at881873.359s,32 at881873.453s and33 at881873.703s show a250ms generation gap; the worker failed before the first localization query completed. This is local synthetic transport, not Wi-Fi evidence. The harness placed App/controller/watch code in the Kit interpreter, unlike the separated production backend/Bridge architecture. This topology and CPU/GIL scheduling are hypotheses to isolate, not a confirmed root cause or a fixed production latency claim. The later final source has not passed that combined mode.
- A read-only manifest-check PowerShell expression initially had a parser error and performed no check; the corrected expression verified all3 files.

## Remaining sequence

1. Validate the combined goal path through **separate real App/backend and Bridge/Isaac processes**, profile keeper generation, pipe writes, robot acceptance, observation processing and receipt checks, and resolve the reproduced deadline gap without loosening250ms/200ms. Include current scene/receipt loss, Stop during preparation, stale transport and reload. Chrome/embedded-viewer acceptance is still required.
2. Connect goal5s summaries, bounded persistent return/target legs and C5/C6 normal/fault/reload acceptance.
3. Separately qualify the reviewed target binary/profile and freshly approved on-site geometry, scan/odom/TF, stop, latency, autonomous travel and loop. Source is **NOT_DEPLOYED**. Robot power alone does not finish the demo.

Next implementation and latency isolation need no robot power. No whole-demo or physical success is claimed.

## Frozen source SHA256

The following19 code/test files match after final Python and Web verification. Documentation is excluded. Tracked whitespace checking does not audit pre-existing untracked files; those remain preserved.

| File | SHA256 |
| --- | --- |
| `packages/twinpulse_core/src/twinpulse_core/current_goal_preview.py` | `67c5224b3a8ea775210fb5069a1937abd76823dbe7e087964d1533107f2698dd` |
| `scripts/verify_goal_demonstration_isaac.py` | `2d06842d1bbd4b2ddff91e5f55e138e90d4f824eaea9bd04c1d426a09f2cd83b` |
| `packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py` | `3b2ac818458378f590ac14e864e46a02a4bfab6b218b4fbc7e45ddf6e24fdd04` |
| `apps/twinpulse-web/src/conversation-types.ts` | `cc8c44453ad9757932ab2e0fdeae2f1f39821dddccb3350065e182372763d08f` |
| `packages/twinpulse_core/src/twinpulse_core/observed_mission.py` | `669a6d2cf8ca15acf24825e0cb06d5a4910ed69c33a38aa0d3656ade97cb02eb` |
| `tests/integration/test_goal_demonstration.py` | `c985ba87aebfb97187f75e64ae1ac165f1eabdb36e335e9d733c24f2bc1f5d55` |
| `packages/twinpulse_app/src/twinpulse_app/goal_demonstration.py` | `f7543e90ac3e38044735542950092cb5fe5d84a3a8dc1dbb271d9519adf7a9fe` |
| `tests/integration/test_goal_handoff.py` | `a7d80bda361379dd88f6fc9bfa7cbdae61b35e09cf6508e7d37270c058e03362` |
| `packages/twinpulse_core/src/twinpulse_core/reference_transport.py` | `f33ff5b363ebfb197c700dd2a651ef4e83b10f5dc955867fb6350482e98c2264` |
| `tests/integration/test_reviewed_route_revalidation.py` | `2b3d5b10e370ef9c80edd9b85ef3ba01d5380b31a1473b0d0f177a3ff8adff64` |
| `packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py` | `f00d389c49107e0c0a87eb0737a238cb3b4447af3840f495b66015bba6751d62` |
| `packages/twinpulse_app/src/twinpulse_app/conversation_service.py` | `e5435dc3843ecb109a21f26e5d1e96faf777a44a760ef8478ea58b4b92cdf997` |
| `packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py` | `415c4f8535d5b91d9d742a4e6bf0838b11611bf61d9690a00ebda6c65e79f8e7` |
| `apps/twinpulse-web/src/CurrentGoalReview.test.tsx` | `29dc255c0617f8526b86397a165aa3bc5f32d34de40b7dab57ed51b36ff9bff8` |
| `packages/twinpulse_core/src/twinpulse_core/goal_simulation.py` | `30949c7d0490336fe4d7410097e86a9f8ed13fa9599fa3ba1025e6158e035435` |
| `tests/fixtures/idle_reference_robot_process.py` | `d486ecc0589492659df36497b054c2b2d0e4f189af760e60dc0a725d3d9f594e` |
| `packages/twinpulse_app/src/twinpulse_app/physical_controller.py` | `25d4d6f107767bfb61b114c1b3d7f8e91d5bd48596aa1bd92ec2d03a85f21f30` |
| `apps/twinpulse-web/src/CurrentGoalReview.tsx` | `fb17fc746f7d9b1fa5dde8b1f079fc17f6acbb790191713a852127d98666312c` |
| `packages/twinpulse_app/src/twinpulse_app/chat_goal_navigation.py` | `83f0635fdab79472dfd5a5a99986de9493be4fcd9081b336cded946036b4edd5` |

