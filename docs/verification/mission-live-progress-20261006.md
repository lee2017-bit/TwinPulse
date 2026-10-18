# Mission resource display and observed progress

The repeating goal task now carries source-bound battery and next-waypoint diagnostics from the native worker through the saved session, App, chat and right-hand Twin summary. An observed-progress guard stops a native mission when successful nonzero output continues without sufficient odometry and scan-localized progress. These are offline implementations and tests, not physical acceptance. The robot remains off and this source is not deployed.

## Current resource display

The additive `mission-telemetry-1.0` packet binds the owned worker ID, complete source context and current scope digest. It preserves original battery and position sample times, checks source ages below 200ms, rejects malformed data, changed sources, replay and non-increasing emission clocks, and never grants motion authority. The strict visual v1 schema and existing v1/v2 preview contracts remain unchanged. The reviewed source bundle includes both new pure modules.

Battery percentage is the existing voltage-based estimate, not measured capacity. Missing or expired facts remain unavailable. A waypoint is derived from the current accepted coordinate transform and route index; localization loss cannot substitute a previous waypoint. Motor torque/load measurement is unsupported.

The chat summary, goal card and right-hand Twin summary use the same validated stream. Display receipts expire after one second or when the worker ends/Stop begins. The browser has its own expiration timer even if the next HTTP response never arrives. This display interval accommodates the existing 750ms UI polling; it does not change the robot's 200ms sensor or 250ms input guards. Transport delay remains unmeasured, so a recent worker receipt is not continuously verified physical status. Per-leg resource checks remain separately labeled historical.

## Observed progress policy

`OBSERVED_PROGRESS_3S_V1` starts only after a successful native nonzero publication, not merely planning or motor arming. During a continuous command category, each three-second window requires at least 10mm translation or 0.05rad rotation in both odometry and current scan-localized pose. Zero output, a servicing gap of 250ms or a translation/rotation/direction change resets the observation window. Ordinary source/alignment checks retain their diagnoses before the progress check.

Failure returns `OBSERVED_PROGRESS_STALLED` before another movement output, invalidates the current visual, follows existing independent cleanup/report handling and blocks subsequent task legs. No automatic return home or retry follows. The same successful-publication hook reaches cold-start mission parts. This conservative software policy is not a calibrated physical blockage detector: sensor uncertainty, periodic pauses, slip and actual motor load need field qualification.

The stop, scan200ms, input250ms, segment50ms, 0.03m/s, 0.20rad/s and 45-second active-leg limits, exact-plan review, first-output gate and physical release lock remain unchanged.

## Verification

- [Final frozen-source regression](../../artifacts/verification/mission-live-progress-20261006-final-regression.json): PASS, 184 selected Python tests in 313.125 seconds, zero errors/failures/skips; 64 source hashes unchanged before and after. The final verifier also checks that both actual runs below match the current source and built UI.
- Web: 327 tests across 42 files PASS; TypeScript and production build PASS. The existing large-bundle warning remains, not a functional acceptance failure.
- [Final normal runtime](../../artifacts/verification/mission-live-progress-20261006-03/verification.json): PASS. Built Chrome/App, authenticated Bridge, actual Isaac/PhysX and native synthetic sensor workers completed six repeat legs (three round trips) after one Repeat approval, then Stop and reload without re-execution. Fifteen peer session archives reopened; independent cleanup and normal owned-child exit passed.
- [Final expected-stall runtime](../../artifacts/verification/mission-live-progress-20261006-stall-03/verification.json): PASS for the failure-handling test, not goal arrival. A synthetic stationary world after native output caused OBSERVED_PROGRESS_STALLED; the App error banner/chat retained the cause, the report was saved, current telemetry expired, two archives reopened, both cleanup facts passed and owned children exited normally.

Both actual runtime records have 38 unchanged source hashes and four unchanged built-file hashes, with no forced cleanup. Live and failed screenshots were inspected. The actual runtime is Isaac, but the sensor data and qualification are test-only: robot connections and physical tests are zero. No source was deployed. Neither the three round trips nor the expected-stall test qualifies physical blockage detection or the complete demo.

## Preserved intermediate results

- [Normal attempt01](../../artifacts/verification/mission-live-progress-20261006-01/verification.json) failed because the verifier expected battery data even in an expired terminal packet. Native arrival, original-time active packets, saved session review and cleanup passed; the packet correctly reported unavailable facts. The verifier now checks valid active packets and requires terminal display removal.
- [Normal attempt02](../../artifacts/verification/mission-live-progress-20261006-02/verification.json) passed six repeat legs, Stop and reload before the final sidebar/source refinements. Fifteen peer sessions reopened and all owned children exited normally.
- [Stall attempt01](../../artifacts/verification/mission-live-progress-20261006-stall-01/verification.json) failed on a verifier assumption that an absent optional `cleanup_error` must serialize as null. Native `OBSERVED_PROGRESS_STALLED`, saved report, chat cause and both cleanup facts were observed. The assertion now accepts absent or null, without weakening cleanup evidence checks.
- [Stall attempt02](../../artifacts/verification/mission-live-progress-20261006-stall-02/verification.json) passed before the final cause-priority refinement. No real wheel was blocked.
- [Intermediate test metadata](../../artifacts/verification/mission-live-progress-20261006-intermediate-tests.json) preserves sandbox temporary-file/build-worker errors and a mistyped Python test-module selection. Those runs are not final frozen-source PASS results.

## Exact remaining work

C4 and C5 remain partial; whole-demo readiness stays false. Three round trips and an observed-stall test do not replace the required thirty-minute actual wall-time resource/log run or the combined dynamic-obstacle, low/unknown battery, lost input/scan, storage, Force STOP and ownership-loss matrix. C6/package/target admission and separately authorized physical qualification remain. No robot is needed to implement and test the remaining offline cases; a new field scope is required before physical execution.
