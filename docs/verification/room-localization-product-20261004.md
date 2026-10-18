# Saved scan localization and room goal review

2026-10-04 KST. Saved ROS data now reaches the existing photo-room product path: verified raw bytes → timed scan and wheel odometry → route-independent position candidates → historical goal conversion → visual-only Burger, scan and trajectory overlay. This is an implemented offline review path, not acceptance of current robot localization or autonomous driving.

Subsequent [multi-frame diagnosis](room-scan-model-diagnosis-20261004.md) found that the preserved COIN source publishes node/publication time rather than its available scan-start timestamp. All “timed/deskewed” counts below mean computable under declared message timestamps, **not independently verified beam-acquisition timing**. Previous byte, software and visual results remain valid within that narrower scope; no physical timing/calibration acceptance is added. Thirty-six selected real frames yield no unique room match, and the authored room still uses the earlier photo and estimated geometry.

## Implemented product path

- The bounded CDR1 reader decodes the original LaserScan, Odometry and TFMessage payloads. Unknown rays remain unknown; unsupported encodings, malformed lengths, clock resets, nonplanar poses and timing gaps have explicit errors. Other message types remain preserved raw, not silently declared decoded.
- LaserScan first-ray ROS timestamps and each original ray's time increment are paired with interpolated wheel odometry. The complete rolling scan must be bracketed; no extrapolation fills a missing final pose. Same-stamp dynamic TF is checked against odometry. The COIN declared end-angle discrepancy is recorded without fabricating rays or relaxing live navigation rules.
- Global XY and heading search against the approximate room outline does not prescribe a route or reuse the previous lap's final pose. It returns competing candidates, capped all-ray error and inlier coverage. Poor, ambiguous or unpaired frames cannot convert goals.
- Session, source, scene, sensor-model revision and reposition epoch bind every result. A new physical start/mission request invalidates historical localization. An explicit manual-reposition action clears the binding; late results cannot resurrect it. Source/room/model changes at goal conversion return a precise rejection and invalidate old results.
- The room panel selects a saved session and original scan frame, shows acquisition elapsed time, point cloud, wheel-odometry trace, rejected-frame causes and position quality. It can convert a unique candidate's Twin XY goal to the historical odom frame. This returns `mission_request=null` and `motion_authorized=false`.
- An authenticated preview request uses the existing bedroom Build broker and a separately advertised `room_scan_replay_v1` engine capability. The engine checks the fixed report descriptor, source identity and reprojection before changing only the owned presentation. Burger uses Physics none; no timeline Run or physical mission is started.
- Derived reports are new exclusive files under `artifacts/room-localization-review`; originals and past failures are not replaced. The CLI `scripts/review_room_localization.py` reaches the same service without SSH or device access.

## Actual saved data inspected

The following are actual source-release `582714f7…` recordings, not injected fixtures. All original raw byte integrity checks passed. The timing audit covered every decoded scan; global room matching below covers only the explicitly selected original frame.

| Saved job | Scan / odom / dynamic TF | Timed frames / rejected | Selected frame | Room match |
|---|---|---|---|---|
| `4493be87ef7643ababb661b4a12f0180` | 2318 / 4678 / 4678 | 2317 / 1 | 10 | AMBIGUOUS |
| `b6cf346718da44b99e7bffe6f7919bbf` | 1213 / 2472 / 2472 | 1212 / 1 | 10 | POOR_FIT |
| `1a7f033af112437699ca67aef3438ecb` | 30 / 108 / 108 | 25 / 5 | 2 | POOR_FIT |

Every dynamic TF sample compared with its same-stamp odom sample agrees within the checked tolerance. All three have zero static TF samples: the sensor mount remains a pinned nominal model, not an as-built measurement. The first two recordings each end with one `ODOM_TIME_UNBRACKETED` rolling scan. The failed input-deadline session also has four `ODOM_TIME_GAP` frames. Those gaps are retained, not interpolated across the limit.

The long recording spans 231.374850 seconds of first-ray scan timestamps. Selected frame 10 has a 105 mm capped mean outline error, 80% inliers and only about 10 mm advantage over a separated alternative: it is **ambiguous**, not a verified position. The other selected recordings have about 253 mm mean error and about 49–51% inliers. These results suggest insufficient compatibility between the photograph-derived geometry and sensor observations; they do not identify one proven physical cause. Occlusion, changed furniture, unknown metric geometry and nominal sensor mounting remain possible contributors. No success threshold was changed to force a match.

Derived report IDs:

- `4493be87ef7643ababb661b4a12f0180-0611309e855b4cbb92310d45f15a0588`
- `b6cf346718da44b99e7bffe6f7919bbf-8466f8978e9044bebf960b7aca1dafe6`
- `1a7f033af112437699ca67aef3438ecb-117816f7dd5b49879e9bebcee38da128`

## Verification

- `artifacts/room-localization-regression-20261004-r2.xml`: Python 375 tests and 158 subtests passed. Includes core, room/geometry, physical-controller fake paths and existing authenticated product/bridge APIs.
- `artifacts/room-localization-product-20261004-r3.xml`: nine focused product tests passed, including the subsequently added unique-candidate goal routing test. Synthetic matcher/raycast cases check wiring, changed starts and rejection behavior, not physical accuracy.
- Whole Web regression: 203 tests passed, zero failures. Generated engine contract check, Python compilation, TypeScript and production Vite build passed. Final Web evidence: `artifacts/room-localization-all-web-20261004-r3.json`.
- Actual isolated Isaac run: `artifacts/room-localization-isaac-20261004-r1/verification.json`, status `ROOM_BURGER_VISUAL_PASS`. The ambiguous long-session candidate's 135 reprojected scan points and trajectory compose with the existing four-mesh Burger. Captures and reopened USD verify presentation persistence, idempotence, untouched external prim, unchanged asset bytes and Physics none. Alignment and physical validation remain false/NOT_RUN. This was the real compiler/rendering path, not a browser→engine end-to-end run; `product_app_integration=PENDING` is retained.
- Initial floating-point test assertion, unsupported Web matcher and sandbox temp-directory failures are preserved in the earlier reports. They were corrected or rerun with approved local filesystem/process permissions; no ROS/physical guard was weakened.

Reproduce offline:

```powershell
.venv/Scripts/python.exe scripts/review_room_localization.py 4493be87ef7643ababb661b4a12f0180 --frame 10 --goal 0 0
```

This records a new derived report and rejects goal conversion for the ambiguous frame. To review in the App, use the existing saved room/model panel, then **Scan → room position → goal**. The 3D action requires an updated connected Isaac adapter and its advertised capability; merely accepting a queued Build is not proof that rendering completed.

## Remaining boundary and next work

The software no longer lacks a saved CDR/time-pairing/global-candidate/goal/3D review path. However it does **not** yet continuously relocalize the live robot, infer every hand relocation from wheel odometry, survey the room, construct a metrically accepted SLAM map, or unlock physical autonomy. The new-session invalidation is implemented; live automatic acceptance after invalidation is not. Historic goal conversion is deliberately not advertised as a current robot goal.

Next use the preserved multi-frame evidence to assess a consistent odometry-frame scan map and room-model mismatch, then establish the required metric room/sensor reference and live localization acceptance. Do not obtain an arbitrary new lap simply to hide this mismatch. A live demo still needs current pose confidence, calibrated frame binding, accepted local collision protection and an authorized mission-level field trial.

No robot connection, deployment, sensor or motor action was made here. The previous `f6e00875…` communication repair remains not deployed/physically tested, the 0.08 m/s request remains unapplied, and the previous final accepted-stop evidence remains unchanged. The current offline work does not claim either issue resolved on hardware.

## ROS schema references

The decoder and rolling acquisition-time interpretation were checked against the primary Humble message definitions: [LaserScan](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/LaserScan.msg), [Odometry](https://github.com/ros2/common_interfaces/blob/humble/nav_msgs/msg/Odometry.msg), and [TFMessage](https://github.com/ros2/geometry2/blob/humble/tf2_msgs/msg/TFMessage.msg). These describe the message contract, not the physical accuracy of this particular sensor or room model.
