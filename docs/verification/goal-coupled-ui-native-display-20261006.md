# Coupled goal failures and actual native-sensor display

2026-10-06 / Baseline1.0.310. Selected offline increment accepted; C4/C5/C6 remain PARTIAL and whole readiness=false. Robot connections, physical trials, deployment, paid calls, installation and new agents: zero. Heartbeat remains PAUSED.

## Product changes

1. Native cleanup diagnoses now remain distinct from the first failure, adapter cleanup and report-storage failure in the existing goal card, terminal chat and a nonmodal failure popup. Only bounded machine-code/stage/type fields are displayed; raw exception strings are not exposed. A late native diagnosis updates the existing terminal message once, without replaying the operation. Dismissing the popup does not resume a mission or block independent Stop controls.
2. Actual native worker identity differs from the App job identity. The previous strict frame contract correctly rejected that mismatch; successful native travel and Isaac route simulation did not prove live native-pose display. The App now checks the native identity, preserves the original visual and its hash, records `native_visual_binding`, and produces a separately hashed display frame bound to the App job. Engine/stage/project/geometry/source/age checks and the existing frame contract are unchanged.
3. Current saved chat/imported rooms can use the pinned fixed Burger without a separately copied legacy Burger manifest. Existing recipes and authored assets are still validated; malformed existing files never trigger a default-room fallback. The current draft, edit history and correction ledger must match the compiled scene. Default projects with a saved draft use that draft, not the historical bedroom. Default/no-draft legacy behavior is retained separately.
4. Formerly active sensor Burger/cloud prims become `LAST_OBSERVATION_NOT_CURRENT` and invisible after evidence, lease or mission ends; a new verified frame makes them visible again. Raw history remains intact. Illustrative SIM and explicitly historical displays remain separate; hiding sensor prims is not a claim that every simulation prim is removed.
5. Actual renderer failures retain bounded local machine-code/type diagnostics in the engine receipt. The ordinary Web test configuration now selects Web source tests, excluding the separate Node-only ownership driver.

No localization tolerance, stop qualification, input/scan/segment/speed/time guard or physical permission was relaxed. Test fault timing was changed only in the explicit synthetic fixture so current rendering could be observed before the injected scan loss. The fixed task guards remain scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s per active leg; legacy v1/v2 and raw hashes remain preserved.

## Final evidence

| Scope | Final result | Boundary |
|---|---|---|
| Frozen native/App/task/current-room regression | [257 tests PASS](../../artifacts/verification/goal-coupled-ui-20261006-final-regression-r2/verification.json),369.541s test runner /370.078s total;93 source hashes unchanged;17 new combined-case artifacts | Device-free fixtures, not every actual browser/Isaac fault combination |
| Web regression | [335 tests PASS](../../artifacts/verification/goal-coupled-ui-20261006-web-final.json),42 source test files; TypeScript and production build exit0 | Existing local dependencies; no install |
| Node ownership boundary | `node --test e2e/owned-chrome-observer.test.mjs`:1 test PASS | Only explicitly generated temporary profile leaf; user profile untouched |
| Actual normal journey | [09 PASS](../../artifacts/verification/goal-coupled-ui-20261006-09/verification.json): two distinct exact Isaac PhysX demonstrations, single Confirm/native synthetic arrival,5s chat, current display binding, reload non-replay, delayed raw rejection | Actual built Chrome/App/authenticated Bridge/Isaac; synthetic ROS-shaped source and test-only qualification; physical0 |
| Actual scan combination | [10 PASS](../../artifacts/verification/goal-coupled-ui-20261006-10/verification.json) | First cause NAVIGATION_TIME_SKEW; native halt, adapter cleanup and storage failure remain independent |
| Actual progress combination | [11 PASS](../../artifacts/verification/goal-coupled-ui-20261006-11/verification.json) | First cause OBSERVED_PROGRESS_STALLED; same independent cleanup/storage checks |
| Development package | [r2 PASS](../../artifacts/verification/goal-coupled-ui-20261006-package-r2/verification.json):71 tests from502 declared members,22,444,139 bytes, outside-checkout imports, independent saved-input hashes unchanged, temporary copy removed | PACKAGED_APP_CORE_OFFLINE_PASS only; package-specific Web/Isaac, clean install, target and whole acceptance NOT_RUN |

Each final actual journey binds49 runtime source hashes and four built files, confirms source/build unchanged and normally exits all owned children with no forced cleanup. Each renderer receipt reports `current_visible=true`, `ended_hidden=true`, no renderer error. Actual USD transitions show ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED/inherited followed by LAST_OBSERVATION_NOT_CURRENT/invisible. This proves the selected current sensor presentation path, not physical calibration or accuracy.

Both combined cases retain:

- first navigation failure;
- native `navigation_halt: STOP_READBACK_UNCONFIRMED (ValueError)`;
- adapter `OWNED_SENSOR_STOP_UNCONFIRMED`;
- `MISSION_REPORT_STORAGE_FULL` / report FAILED.

The actual nonmodal popup and saved chat contain all four causes. The raw injected storage canary is absent from the exposed job. Ended pose is null, scan is empty, telemetry is unavailable, stale Confirm/Repeat is disabled or absent; waiting/reload creates no operation or worker. The synthetic outer cleanup is independently checked and must not be described as physical wheel/sensor-stop proof.

Screenshots: [current display](../../artifacts/verification/goal-coupled-ui-20261006-09/goal-1-live-telemetry.png), [scan failure popup](../../artifacts/verification/goal-coupled-ui-20261006-10/combined-scan-failed.png), [progress failure after reload](../../artifacts/verification/goal-coupled-ui-20261006-11/combined-stall-reloaded.png). Screenshot inspection supports UI layout; behavior acceptance comes from the linked checks and receipts.

Final build: index-DMdY3W9E.js571.19kB, index-CDxJwhen.css40.54kB; unchanged >500kB bundle warning remains. [Build manifest](../../apps/twinpulse-web/dist/twinpulse-build-manifest.json) hashes JS `f7287df730ce5f9c6f1c83be5ce2059fcf135431cb7280c94ee1a1ae5b12578f`, CSS `c47d3f8befdf3f3430cb9148ae734ed3db40b62916dc039cb32dc098b6883e58`, index `7da8f318926aed3958ad7360f9e9dcb6a109cd0aa3b7fb270ae5af687de7fcaf`.

Final local package: `artifacts/offline-release/tp-local-coupled-ui-v310-r2-20261006`. Manifest SHA256 `083f06a14c39ce6e89ac8ee00ee3a7a959800f724419809d02dc3717a47183f0`. Dirty development package, not a committed production release. Existing pinned wheel plus reviewed built dist were copied; no dependency installation/download. Private photos, raw observations, runtime state and identity/host records are absent. Saved raw test input was copied independently, not added to the package. The earlier v310 package remains an intermediate artifact, not the final package.

## Failed and intermediate attempts preserved

- Sandbox temporary-folder access and Node spawn failures were not code PASS; relevant local tests ran after scoped permission review.
- Initial Web assertion matched both banner and inline text; the selector was corrected. Bare Vitest accidentally selected a Node-only test before the final include configuration; its335 Web passes did not make the overall exit1 a PASS.
- [01](../../artifacts/verification/goal-coupled-ui-20261006-01/verification.json) passed the stall combination before the real nonmodal popup and current native display fix; it does not prove final popup/current rendering.
- [02](../../artifacts/verification/goal-coupled-ui-20261006-02/verification.json) failed the scan expected-code assertion: the time-skew guard correctly fired before missing-data. No guard was changed to force the desired result.
- [03](../../artifacts/verification/goal-coupled-ui-20261006-03/verification.json) and [04](../../artifacts/verification/goal-coupled-ui-20261006-04/verification.json) passed popup/failure behavior but had no actual active sensor marker. Those reports do not prove live native rendering.
- [05](../../artifacts/verification/goal-coupled-ui-20261006-05/verification.json) FAILED the strengthened actual current-display check; bounded engine diagnosis ACTIVE_VISUAL_BURGER_REQUIRED identified the legacy-recipe/no-visual branch. [06](../../artifacts/verification/goal-coupled-ui-20261006-06/verification.json) passed both normal goals after correction. [07](../../artifacts/verification/goal-coupled-ui-20261006-07/verification.json) and [08](../../artifacts/verification/goal-coupled-ui-20261006-08/verification.json) added actual current→hidden fault assertions. Final-source acceptance is09–11.
- [First final regression](../../artifacts/verification/goal-coupled-ui-20261006-final-regression/verification.json) FAILED one new test setup: importing a named legacy recipe into preserved default is intentionally forbidden. The test now saves a valid active draft instead. Product import restrictions were not relaxed; final257-test result is r2.

The earlier30-minute/42-leg native and viewer-resource result remains valid for its recorded v309 source. It did not check current native USD presentation, which was rejected by the identity mismatch. Its timing/resource result must not be promoted to a final30-minute result with the newly active current-sensor rendering path.

## Exact next work

1. Complete remaining actual combined-fault UI/Isaac combinations and rerun the resource/log-duration acceptance with the final active current-sensor renderer. The selected normal and two compound cases above are complete; all17 Python combinations are not thereby actual UI/Isaac PASS. Do not reuse the old30-minute result as final-source current-render resource proof.
2. C6 final-package, fresh-userdata SIM/REAL D01–D12/UI acceptance and one-click startup/checklist/recovery. The r2 package is prepared and its isolated App/core tests pass, but package-specific full UI/Isaac branches and clean-install acceptance remain NOT_RUN. Resolve or explicitly gate the separate legacy headless still-capture `viewport_missing` limitation; current live viewer/selected engine captures do not erase it.
3. Reviewed target/release/profile preparation and corresponding qualification remain; source NOT_DEPLOYED. Preserve previous target/permission blockers without changing the source/stop/scan/input criteria or installing a workaround.
4. Only after offline requirements are met, a separately approved bounded physical session for real scan/odom/TF/clock/source, coordinate fit, go-to/loop and actual Stop. Robot power alone is not acceptance. No physical Wi-Fi/input-deadline or positional accuracy fix is claimed here.

No robot is required for the next offline work. All owned tests in this increment have ended; originals, dirty work and earlier FAIL evidence remain.
