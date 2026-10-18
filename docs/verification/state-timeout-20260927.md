# Bounded status reads and stale replies — 2026-09-27 17:13 KST

## Correction and reproduced failure

Three API tests reproduced indefinitely pending fetch/body reads and duplicate
concurrent polling before correction: `artifacts/state-timeout-before-20260927.log`
records 58 PASS / 3 FAIL. The original failure log is retained.

Only workflow, product-state and runtime-state GETs now share one in-flight
request per path and have a three-second deadline covering fetch and JSON parsing.
Expiry rejects with `state_read_timeout`, aborts the transport, and releases the
slot for a later ordinary poll. Late completion cannot settle the expired promise.
The existing ordered App refresh failure path clears cached engine/snapshot/lease
authority. No mutation is implicitly retried, timed out or reacquired by this change.

Two additional React tests deliver an older success after a newer failure and an
older failure after a newer success. Neither older result overwrites the newer
applied control state. This does not claim all stale error-banner UX is solved.
Browser timers may be throttled in background tabs; this is not a hard-real-time
watchdog or evidence of physical stopping. Bootstrap and other requests are outside
this bounded status-read scope. Backend/engine/physical stopping gates are unchanged.

## Actual verification

- `state-timeout-regression-20260927-r1/manifest.json` and sibling full log:
  **351 Python / 63 Web / TypeScript / production build PASS**.
- `state-timeout-isaac-20260927-r1`: actual isolated browser → API → broker →
  production bridge → Isaac → receipt/snapshot → UI. Six synthetic normal stages
  and five failure/recovery checks PASS, exactly two scene builds, no Run.
- Browser transport deliberately holds a real product-state response. Build
  becomes disabled after **3376 ms** in this run and the timeout message appears.
  Releasing the held response and restoring fresh reads does not submit another
  build. Actual backend and Isaac stay alive; this is not an engine crash test.
- Prior rejected-read/recovery and real lease-expiry checks also pass. No automatic
  scene acknowledgement, command retry or control acquisition is asserted as success.
- `state-timeout-native-20260927-final`: actual saved-native App nine stages PASS.
  `state-timeout-noengine-20260927-final`: synthetic no-engine App five stages PASS.
- Original project and foreign prim preserved; zero robot/provider connections,
  external browser requests and page errors. No physical validation or timeline play.

[Current evidence page](../../artifacts/state-timeout-handoff-20260927-final/index.html)
binds ten checks to the explicit runs and current source/build hashes, source
photos/raw/nodes and byte-identical native USD exports. Historical actual native
Isaac frames 0/37/73 are reused, not claimed as a fresh engine run. Static local
desktop/mobile/link/image QA passes; mobile handoff and actual expired-control
screenshots were inspected. Previous pages remain immutable historical snapshots.

## Reproduction and next boundary

With existing runtimes and appropriate local permissions, use
`scripts/verify_twinpulse.ps1 -SkipIsaac -ArtifactDirectory <new-regression-dir>`,
then `C:\isaacsim\python.bat scripts/rehearse_derived_isaac.py --output <new-dir>`.
The runner creates and cleans up only its own isolated backend/browser/Isaac state.
Use `scripts/summarize_four_hour_prep.py` with explicit combined/native/historical
Isaac/regression directories, followed by the static page QA. Do not overwrite
existing evidence or treat aggregation as a physical test.

Robot OFF remains user-reported, current battery UNKNOWN. Real native/base/world
alignment, the original physical stop FAIL, D2 physical mission integration and
the full physical demo remain unresolved. Next perform final offline handoff
freshness/audit before the 17:45 deadline, then pause the existing heartbeat.
