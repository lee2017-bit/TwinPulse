# TwinPulse separated goal execution and latency verification

Follow-up Baseline 1.0.306 connects goal chat progress and terminal messages; see [current progress verification](goal-progress-chat-20261006.md). Evidence and remaining work below describe Baseline 1.0.305.

The existing built chat App, authenticated Bridge, actual Isaac PhysX preview and native synthetic control worker now pass two distinct goal journeys. Each journey uses the UI goal request, exact route simulation, one Confirm, a new current observation, guarded native execution and arrival. Reload does not replay execution; delayed observations reject without movement. This is an offline integration acceptance, not physical robot qualification or whole-demo completion.

**Baseline 1.0.305: selected Python regression PASS and final actual separated journey PASS. C4 remains PARTIAL; whole readiness=false.** Physical connections, SSH, serial, real sensors/motors, deployment, paid calls, installs, system changes, commit/push and new agents are zero. Robot source is NOT_DEPLOYED. Heartbeat remains PAUSED. Existing dirty edits, original survey bytes and every failed attempt remain preserved.

## Implementation changes

1. Exact builtin JSON normalization avoids repeated Mapping checks in large grids. A frozen legacy algorithm verifies byte-identical hashes for 132 cases, including custom/subclass mappings, negative zero and Unicode. Nonfinite numbers and unsupported values remain rejected; no rounding, downsampling or cached evidence is introduced.
2. The goal receipt guard captures the same owner, live lease, engine/stage/run, revision, safety and telemetry fields atomically without rebuilding UI reports. The independent room/asset/ledger fingerprint remains checked. Busy inspection rejects before unused room/model re-admission; idle readiness is not cached.
3. Handoff reserves its exact owner/job/scope, writes and fsyncs exclusive raw evidence outside the input/Stop lock, then rechecks ownership, source, worker and Stop before sending. Only the owned pending transfer may continue scoped watches. Directions cannot use this transition to gain authority; Force STOP can still send its explicit terminal packet. Stop or changed source during saving cannot send a late begin.
4. Adaptive visual validation runs outside that lock and rechecks job/source/Stop before publication. A late visual cannot restore current pose after Stop. New cycle timers separate receipt checking, source checking, controller-lock wait and sender time; they do not alter control clocks or freshness bounds.
5. A lease can rotate between periodic Bridge heartbeats. When a claimed command names a different lease, the Bridge invalidates its cached grant and obtains a new authenticated backend heartbeat before queuing. The envelope itself never grants authority. Invalid/mismatched/failed refreshes preserve the claimed command for strict adapter rejection and receipt; watchdog and TTL are unchanged.
6. A bound observation already on stdout can arrive after query timeout/Stop. Its bounded bytes remain historical raw evidence, not a current pose. The receiver continues to the final cleanup receipt. Stopped partial transfers send no further ACK. Foreign queries remain rejected.
7. Strict archive validation now recognizes exact additive diagnostic shapes, including late-data, validation, handoff, visual timing and watch-cycle records. Extra authorization fields, unknown shapes, nonfinite values and wrong numeric types reject. Legacy records remain valid; diagnostic fields never authorize motion.

The native scan/pose 200ms, input 250ms, command segment 50ms, .03m/s, .20rad/s, original active 45s budget, existing qualification/first-output/source/Stop gates and v1/v2 hashes are unchanged. A synthetic spin interval measures actual elapsed servicing time, including scheduling; it is not the requested command segment. The final first moving peer recorded a maximum spin interval of about 63ms. This is not a physical timing or braking qualification.

## Diagnosis and preserved failures

Attempts 14 through 25 remain in `artifacts/verification/goal-separated-20261006-*`; attempts 01 through 13 remain described in [the previous verification](goal-separated-journey-20261006.md). Intermediate source versions are not final-source acceptance.

- 14–15: query profiling and normal execution exposed repeated hash/model work and pending-handoff renewal gaps. The profiler is opt-in and saves only bounded function/frame metadata, never locals, arguments or secrets. Profiled timings are diagnostic only.
- 16–18: native handoff reached acceptance/arming but expired before movement. Source-guard cycles showed roughly 200ms stalls; isolated metadata checks were much shorter. This did not establish a Wi-Fi cause.
- 19–20: scoped profiling found repeated Burger geometry loading through inspection polling. In the isolated verifier, navigation/API used the replacement mission service but inspection still held the retired service and incorrectly reported idle. The verifier now composes all consumers with the same mission. This was a harness defect, not proof of a production physical fault.
- 21: first complete UI/Isaac/native arrival passed; second preview failed with an invalid/expired command lease. The Bridge rotation correction addresses this reproduced product race.
- 22: both arrivals and reload passed. The negative-case predicate expected the wrong rejection label. Delayed data correctly caused query timeout, but a late packet aborted final cleanup reading. Both the predicate and receiver were corrected.
- The first late-packet regression exposed the new diagnostic event missing from strict archive validation. Exact diagnostic contracts were added; the corrected 17-test selection passed in 22.359s.
- 23: actual browser and Isaac checks passed; all five archives reopened. A new verifier counter incorrectly treated native publication lists as dictionaries, so overall verification remained FAIL. The counter was corrected and tested.
- 24: intentionally ended through its owned normal stop files after a saved-data check found the counter also conflated measured spin elapsed time with command duration. It is not acceptance. No unrelated process was terminated. The corrected counter validates native list shape, finite nonnegative elapsed time and the unchanged velocity limits, while reporting elapsed servicing separately.
- Intermediate selections (19 tests, 55 tests, 24 tests and focused diagnostics) are retained as incremental evidence, not added together or substituted for the final regression.

## Final acceptance evidence

**Python:** 165 selected tests PASS in 113.903s; 41 source hashes match before and after testing and after the actual journey. Coverage includes protocol/Stop, exact reviewed-route admission and native handoff, delayed raw/cleanup, reference transport, lease rotation and denial, strict diagnostic archives, R1 provenance/hash workflows and core/site contracts. Inherited tests are included; this is not the entire repository suite. [Frozen-source regression](../../artifacts/verification/goal-separated-latency-20261006-final-regression.json).

**Actual separated journey 25:** PASS. Existing App backend, authenticated production Bridge, existing Isaac host and existing headless Chrome ran in isolated owned roots. The native worker used causal reactive synthetic scan/odometry and the real matcher; qualification was explicitly test-only. Both distinct reviews completed actual Isaac Build/Run/arrival/Pause; both UI Confirms reached native `MISSION_ARRIVED`, with 48 and 114 nonzero synthetic publications. Each Confirm uses a fresh owned worker and the configured synthetic starting position; this does not validate a continuous physical loop.

Reload added no worker or Build/Run and restored no current physical pose. An injected 210ms output delay produced a visible `IDLE_LOCALIZATION_QUERY_TIMEOUT`; the native negative peer failed on `INPUT_DEADLINE_EXPIRED`, published no movement and confirmed wheel/sensor cleanup. These are separately recorded PC and native causes, not a claim of Wi-Fi diagnosis. Every saved session reopened; all five peers confirmed cleanup. Original survey bytes, 27 runtime/fixture sources and four built Web files matched; all owned children exited normally without forced cleanup. [Full actual result](../../artifacts/verification/goal-separated-20261006-25/verification.json).

The production Web source/build did not change. The earlier 319-test Web/build result is historical; the new actual built-UI Chrome journey is the current UI evidence. Screenshots remain in the same actual-result directory: both preview/arrival pairs, delayed-data rejection and actual engine capture.

## Remaining work

1. Connect goal progress summaries at five-second intervals and immediate terminal/fault messages to the established chat execution path.
2. Implement C5 persistent round-trip loop policy with current observations for each leg, explicit Stop/Force STOP, battery/obstacle/torque/freshness/source failures and no automatic restart after a fault. Two distinct synthetic goals do not replace loop acceptance.
3. Complete C6 normal/failure product acceptance, including changed starting positions, dynamic obstacles, session restoration and target packaging/profile checks.
4. Separately validate the reviewed target release, real frames/timing/localization, current room alignment and bounded physical execution under fresh on-site authorization. Offline PASS does not unlock those gates or guarantee that power-on alone completes the demo.

The next three software stages can proceed without powering the robot. All processes from this verification have finished; no automatic robot retry or background mission remains.
