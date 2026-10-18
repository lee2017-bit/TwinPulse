# Browser transport failure / lease expiry — 2026-09-27 16:38 KST

## Reproduced defects and correction

Two React regressions failed before correction (`connection-loss-before-20260927.log`,
56PASS/2FAIL): a rejected product-state read left cached engine authority and an
enabled Build button; a response with `lease_owned=false` but an old lease ID
restarted renewal of that expired ID.

App refresh now invalidates snapshot/engine-connected/control authority on a
failed current state-read batch, retaining the draft and historical operations.
The existing request-order counter also orders failures so an older failed read
cannot clear a newer applied state. Lease renewal follows `lease_owned`, not the
mere presence of an ID. Recovery does not acknowledge or submit any command.
Backend and engine acceptance/watchdog/lease criteria were not changed.

This correction handles **rejected/failed reads**, not a fetch that never settles.
Indefinitely pending transport and independent state-freshness deadlines remain
a useful next offline check. The test does not crash/kill Isaac or demonstrate
physical stopping. A browser-side transport fault is not an engine crash.

## Actual local verification

`artifacts/connection-loss-isaac-20260927-r1` PASS, actual isolated Isaac exit0:

- Existing real browser→API→broker→production bridge→Isaac→receipt/snapshot six
  synthetic scene stages rerun against changed App/build.
- Browser intercepts only its product-state requests as connection failures:
  Build becomes disabled and cached engine status clears. The real local backend
  and engine continue running. Restoring reads sends no automatic command.
- Browser then rejects lease-renew requests. The real backend lease expires on
  its normal3s clock and the actual bridge observes it. Build disables, explicit
  control request is available, no automatic acquisition or additional command.
- Exactly two scene builds total; no Run, timeline play, robot, provider or external
  browser request. Original project and foreign prim preserved. `expired-control.png`
  inspected; historical completed build remains history, not permission to rebuild.
- `browser-result.json`/`result.json` preserve six normal stages plus three
  `failure_checks`. These are now explicitly checked in handoff aggregation.

Full `connection-loss-regression-20260927-r1` manifest and sibling log:
**351 Python /58 Web /TypeScript /build PASS**. The updated handoff verifier was
then checked separately after adding the fault-evidence requirement: eight tests
PASS in `connection-loss-summary-tests-20260927.log` (not eight additional unique
tests). Final saved-native App9 and no-engine App5 PASS in
`connection-loss-native-20260927-final` / `connection-loss-noengine-20260927-final`.

[Updated result page](../../artifacts/connection-loss-handoff-20260927-final/index.html)
binds ten checks to those exact current runs, source/build hashes and historical
native Isaac frame exports. Static desktop/mobile/link/image QA PASS; expiry and
mobile handoff screenshots inspected. The16:10 page remains an immutable earlier
snapshot; do not call its old code hashes current. `git diff --check` PASS.

## Remaining boundary

No robot connection, live battery reading, motor/sensor/power action or deployment.
Real native/base/world alignment, physical stop FAIL and physical mission/demo
integration remain unresolved. Current robot power is only the user's OFF report.
Next inspect bounded handling of non-settling reads and stale/reordered responses
before the17:45 deadline, then refresh handoff evidence and pause the heartbeat.
