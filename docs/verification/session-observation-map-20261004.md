# Saved session observation map implementation and verification

October 4, 2026. The existing App now builds and replays a diagnostic observation map from verified saved ROS recordings without using the photo room as ground truth. It does not connect to a robot, edit the room, create free-space clearance, correct odometry, or unlock a physical mission. Timing and nominal sensor mounting remain explicitly unverified.

## Product path

The existing saved-session selector reaches an authenticated `room-localization/observation-map` API, original byte/hash/footer validation, the bounded CDR decoder, declared-header odom interpolation, and a new endpoint evidence builder. The result is exclusively saved under `artifacts/session-observation-map`; originals and previous failures are not overwritten. `scripts/review_room_localization.py --observation-map` uses the same service.

The new view is separate from the approximate photo-room outline. It shows whole-session endpoint bins, the odom trajectory, and a selected historical scan. Seek and Play use up to 64 uniformly selected original keyframes, not a full raw-message replay. Gray points include later scans and do not mean that an obstacle is currently visible. Playback sends neither robot nor engine commands.

The coordinate origin is this recording's initial odom pose, not the room, a surveyed map, or the previous session's final pose. The method applies no ICP/SLAM correction. Unknown rays never clear space. It samples at most 160 original-index rays per scan, limits display returns to 8 m, bins endpoints at 5 cm, and bounds scans, cells, extents, trace points and report size. Excluded returns and rejected frames are counted. Budget failures reject the operation explicitly rather than silently returning a partial successful map.

A new map request clears the previous photo-position binding. Session changes, hand-reposition invalidation, room/backend changes and late-response checks prevent old results from reappearing in the UI. Busy/error state is visible and the browser request has a 45-second deadline without automatic retry; a server diagnostic can still finish after the browser aborts. No motion authorization follows from a completed map.

The saved-room read-only preparation is no longer unnecessarily gated by Isaac connection. Existing 3D Build/preview capability checks remain unchanged. The saved room must still be loaded to expose its review panel; merely opening the App does not process scans automatically.

## Actual preserved recordings

| Session | Recorded scans | Declared-time paired | Rejected | Sampled returns used | Endpoint cells | Playback frames |
|---|---:|---:|---:|---:|---:|---:|
| `4493be87ef7643ababb661b4a12f0180` | 2318 | 2317 | 1 | 300392 | 3876 | 63 |
| `b6cf346718da44b99e7bffe6f7919bbf` | 1213 | 1212 | 1 | 156879 | 2853 | 63 |
| `1a7f033af112437699ca67aef3438ecb` | 30 | 25 | 5 | 3214 | 703 | 25 |

The long recordings reject their final scan as `ODOM_TIME_UNBRACKETED`; no pose is extrapolated. The failed recording retains four `ODOM_TIME_GAP` and one unbracketed rejection. Normal and failed datasets are kept separate. These are actual saved robot recordings, not fabricated test scans, but this offline processing is not a new physical acceptance test.

Derived CLI reports are `4493…-6074c68910d04cf4b7f1de3609b87784`, `b6cf…-f2b5806a29e3444a993d2f192cd0b274`, and `1a7f…-67ab4fd2daae4230ab3abc09d762dd1c` under the new artifact directory. The actual browser run also preserves its returned original-derived report in its evidence directory.

## Timing contract preparation

`acquisition_timing_candidate` is a device-free fixture helper for mapping scan-start clock time to a ROS first-ray timestamp under an explicit same-domain, stable-offset assumption. Tests verify that publication delay is not used as the first-ray time and reject reversed/nonuniform beam offsets, beams after publication, clock underflow/reset, excessive latency and invalid types. Every candidate still reports `acquisition_timing_verified=false` and `hardware_correction_applied=false`.

This is correction preparation, **not a COIN driver patch, compiled ROS-driver verification or hardware clock calibration**. The preserved source's `getTime()` also has clock-selection branches, so directly copying its numeric timestamp into ROS or subtracting a fixed 100 ms is not justified. Actual acquisition order/clock provenance still need verification before a corrected driver release is built or deployed. Existing recordings retain their original headers. The old localization view now says “declared-time paired,” not verified beam timing.

## Verification evidence

- Python related regression: 343 tests and 260 subtests passed in `artifacts/observation-map-regression-20261004-r2.xml`. Final focused map/localization tests: 19 tests and 13 subtests passed in `artifacts/observation-map-focused-20261004-r3.xml` after the keyframe fallback update.
- Final whole Web regression: 207 tests, zero failures, in `artifacts/observation-map-all-web-20261004-r4.json`. TypeScript/Vite production build and the generated engine contract check passed.
- Actual production Web → authenticated local API → verified real saved ROS → map → seek/play passed in `artifacts/observation-map-browser-20261004-r3/verification.json`. PC/mobile screenshots were checked for readable content and no horizontal overflow. Session change clears the previous map. The isolated workflow scaffolding is synthetic; the scan response and backend path are not mocked.
- Browser verification used no engine or physical controller adapter. It observed one local read-only robot-status GET, zero robot-operation POSTs, zero engine commands, zero external requests and zero page errors. No robot connection, deployment, sensor/motor start or paid provider call occurred. Isaac rendering was not rerun because this increment changes no engine geometry.

Earlier test failures remain preserved: missing Python package search paths, Windows sandbox temp-directory/child-process denials, a verification script incorrectly counting a local status GET as a robot action, and a wall-clock lease expiring in an existing offline routing fixture under CPU load. Permission-required checks were rerun with approval. That fixture now uses a deterministic fake clock; production lease/freshness/stop criteria were not changed or relaxed.

## Use without robot power

Restart the PC App to load the updated backend and production Web build. In the saved room panel, choose **Load saved room and model → Load saved sessions → a session → Build observation map · entire session**. Use the time slider or Play to inspect recorded scans. The buttons do not require robot power or Isaac connection. The existing photo-room position search remains separate and may correctly report ambiguity or poor fit.

Offline CLI:

```powershell
.venv/Scripts/python.exe -B scripts/review_room_localization.py 4493be87ef7643ababb661b4a12f0180 --observation-map
```

## Remaining work

The observation/3D separation and historical scan playback are implemented. Acquisition-time/beam-order correction is prepared only at fixture level. Evidence-bound sensor cross-section and room-geometry correction, multiframe/map-relative localization including changed physical starts, live room binding and accepted physical local collision protection remain unfinished. A timing-unverified odom endpoint map is not sufficient to approve those steps. This increment does not change the original photo recipe or claim to have recovered the room's true dimensions.

No new robot lap is needed for the next offline map/model comparison and correction preparation. As-built sensor geometry, true acquisition timing and current live position acceptance cannot be certified from these saved bytes alone. The earlier communication repair remains undeployed; requested 0.08 m/s remains unapplied.
