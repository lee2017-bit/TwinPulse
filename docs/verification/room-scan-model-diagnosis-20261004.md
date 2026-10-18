# Saved room scan diagnosis — 2026-10-04

Analysis only: three preserved real ROS sessions, no robot connection, deployment, motor command or product source change. Originals and prior failures remain unchanged. Reproducible scripts and detailed Korean findings are in [the analysis report](C:/Users/jaewo/Documents/Codex/2026-09-12/dl/outputs/room-scan-analysis-20261004/analysis.md).

## Evidence and limits

- Original byte/hash/footer checks passed. Sessions `4493…`, `b6cf…`, `1a7f…` contain respectively 2318/1213/30 scans and 4678/2472/108 odom and dynamic TF messages. All have zero static TF messages.
- 2317/1212/25 scans can be interpolated using **declared message timestamps** (3554 of 3561). This is not independently verified acquisition-time alignment. Remaining frames retain unbracketed/time-gap rejection.
- Twelve uniformly spaced valid frames per session, 36 total, yielded 9 AMBIGUOUS and 27 POOR_FIT results; no unique room match. This is a selected-frame audit, not every possible frame.
- Forty-three approximately one-second scan pairs were compared; samples overlap. Odom-aligned capped nearest-neighbor means in the two long sessions were 51.1/36.9 mm; diagnostic local ICP gave 46.3/33.6 mm. These are point residuals, not robot position errors or SLAM acceptance.
- Normal-session scan intervals have median about 99.8 ms and maxima 103.6/104.3 ms. The failed input-deadline session has a 1.098 s maximum gap. That failure cannot explain all normal-session model mismatch.
- Same-stamp dynamic TF agrees with odom, but preserved ROBOTIS odometry source copies odom pose into TF. Agreement is not independent floor-position validation. Start/end odom distances of 3.85/3.92 m do not prove that much drift without a known physical return to the same place.

## Confirmed source and model issues

Preserved COIN source commit `8277b288902f28b37948b42e1bb80ba59afbba60` stores scan-start time in `outscan.stamp` at `coin_d4_base_handler.cpp:491`, but publication uses `get_node_time()` for the ROS header at line 322. Reviewed parser/lifecycle/stop-order patches do not change this handling. [The ROS LaserScan contract](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/LaserScan.msg) defines the header as the first ray's acquisition time. This source violates that timing contract; exact hardware timing and reversed array acquisition order remain unverified. No new remote binary inspection was performed.

The authored `bedroom_twin.py` recipe fixes estimated floor dimensions at 2.8 × 4.2 m and uses floor-filled furniture boxes. It is not a measured image reconstruction. Its original photo hash `a183bf7e…` differs from the later test-environment photo `456c9f3e…`; subsequent furniture/clutter placement is not automatically incorporated. Sensor-height outlines of solid boxes differ from legs, open undersides and hanging cloth. Their exact contributions to mismatch are not yet separated.

## Counterfactuals, not adopted corrections

- Y reflection worsens local residuals to 209.8/147.1 mm. Tested mounting yaw hypotheses favor the current 0° on moving pairs, but do not verify as-built extrinsics.
- Header shifts of -150/-100/-50/0/+50 ms improve the long sessions by at most about 2.5/0.6 mm, with different optima. No fixed timestamp shift is justified or applied.
- Three-frame XY scale sweeps favor 1.2 over 1.0 but still yield no unique match. This does not establish that the room is exactly 20% undersized. Removing desk/chair or retaining only walls worsens the fit; no furniture was removed to manufacture PASS.

## Decision and next order

The immediate blocker is not missing stored data. Separate a diagnostic multi-frame 2D observation map from approximate photo-based 3D appearance; prepare acquisition-clock/beam-order fixtures; then propose evidence-bound furniture cross-sections and geometry corrections. Only after multi-frame consistency checks should session-specific live localization be connected. Unknown space remains unknown, old starts cannot be reused after hand repositioning, and physical mission authorization remains locked until metric/current-session evidence is accepted.

Previous “timed/deskewed” counts mean computable under declared ROS timestamps, not verified beam acquisition timing. Previous software/visual checks remain valid in that narrower scope. No new physical PASS, calibration, autonomous mission acceptance, threshold relaxation or source correction is asserted. The communication fix remains undeployed and requested 0.08 m/s remains unapplied.

The detailed report preserves scripts, three session JSON results and `hypotheses.json` under the analysis directory. Outputs are exclusively created, not raw-data overwrites. Actual acquisition timing, as-built extrinsics and live acceptance cannot be finished from stored ROS bytes alone. No new robot run is needed for the next offline preparation.
