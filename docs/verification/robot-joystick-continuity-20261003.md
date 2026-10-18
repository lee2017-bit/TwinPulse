# Joystick readiness, continuous intent and actual scan metadata — 2026-10-03

## User scope / boundary

Fix the dedicated robot console after user testing: make readiness explicit, remove its repeated watching checkbox, retain control between gestures, remove periodic braking during a fresh held intent, and display ROS LiDAR data beside the joystick. English product strings. This turn performs local implementation and offline checks only: SSH, deployment, sensor and motor commands **0**. New physical behaviour **NOT_RUN**, not full demo acceptance.

## Evidence inspected and causes

- Existing real session `artifacts/manual-control/3858c408cb0149ac9ec5a88226cec131`: deployed source `2763660e9e653a9fc5911573821761a7113cd764175701de63779d9f45740763`, boot `a420706c-2b68-4bb0-943d-cbd8b2bf9611`, mode `control_scan`, ended `SESSION_EXPIRED`; independent wheel and sensor cleanup confirmed. Journal contains 21 arm/release/idle cycles, 258 published intents, **zero scan_preview events**. Worker raw summary: scan608, odom1261, tf1261, 4,085,914 bytes, complete/no drops. These are historical observations, not current power/readiness.
- Periodic stop was deliberately introduced by the UI at 1.4s under the old 2s total-hold rule. This explains the stop/resume pattern; it was not evidence of wheel overload. The final 60s session expiry explains that session's final lock.
- This page's new qualification was tied to the current operation's job ID. Starting control replaced that ID. An older read-only release snapshot then could not match the just-deployed qualified release, so setup visibly reverted despite the owned drive being READY. Now the page keeps the actual owned qualification bound to boot/release across operation IDs; reload still requires independent observed boot/release matching. Robot authorization remains authoritative.
- The exporter omitted `control_scan` and `scan` from its fixed mode map, causing `ValueError` / incomplete evidence export. Both exporter and OFF re-inspector now share the complete scan-mode contract, including driver log, exact-byte ROS raw and footer. Latest session's raw is **not fetched this turn**; a future explicit transfer-only recovery is needed, not another driving test.
- Older available real raw `artifacts/ros-scan-20260930T143239Z-c4b681f5/ros-messages.raw`, SHA256 `33efb640cb759c7deeb63b089c786d38b35d7d8cdd9aa2f9680d24fd242d253b`, contains 105 actual COIN D4 LaserScans. It declares range_max=100m and angle_max=2π; its angle increment/count can omit a terminal bin (first sample 394 rays / increment .0159067977). Previous display validation rejected both the range metadata and endpoint/full-circle convention. This is an experimentally reproduced display-contract defect on saved real data; latest session's exact rejected metadata remains unavailable, so its complete live failure chain is not claimed proven.
- Latest navigation records also show scan `ENDPOINT_COUNT`. **Navigation/TF/calibration are not repaired or promoted to PASS by a display fix.** Manual control already checks driver/scan freshness independently; the new view is not collision avoidance.

## Implemented product flow

1. Automatic read-only status observation remains unchanged.
2. Only missing package/stop preparation is shown. Its existing source-bound physical criteria remain required; no automatic movement test or deployment.
3. Dedicated-console watching checkbox removed. Clicking the named operation is the explicit request; guidance says keep the robot in view. Legacy full product/mission panel's existing consent remains unchanged.
4. One `Driving mode` selector (Drive + LiDAR / Drive only), one Connect button. It becomes Connecting while preparing, Connected once ready. Selected mode, elapsed preparation and **READY TO DRIVE** are beside the controls. READY shows the 60s session limit. Connection does not silently fall back to another mode.
5. Releasing a gesture stops wheels but keeps the owned connection; another gesture requires no checkbox/reconnect. Terminal Stop/Force STOP, missing input, focus loss and session expiry remain terminal, with no automatic resume.

## Deliberate continuous-control policy change

- New manual/control_scan workers advertise `fresh-intent-1.0`. Fresh direction frames renew a short intent lease; the UI no longer sends the artificial 1.4s periodic stop for that advertised policy. The old **total 2s gesture cap is replaced**, not falsely described as unchanged. Qualification modes remain bounded and physical stop policy unchanged.
- Independent checks retained: robot-issued single-use nonce, strict monotonic sequence, conservative source age <250ms, existing robot/PC watchdogs, fixed low speeds, release/close/Force STOP, sensor liveness/freshness, qualification bound to boot/source, 60s total session and independent final cleanup. `check()` runs before accepting renewal: expired frames cannot revive the lease. A watch packet alone cannot sustain moving output.
- Old robot workers do not advertise the policy, so the UI retains bounded stop/resume instead of accidentally running them past their hard guard. Current local source must be explicitly prepared and qualified once before the new behaviour is available. No robot reboot is required for this source update.
- Continuous real-floor motion/braking/latency and simultaneous live display **remain unverified**. No autonomous release or collision guarantee.

## Display and diagnostics

- Display-only validation accepts bounded sensor-declared range metadata (≤1000m) and known full-circle endpoint/one-terminal-bin-gap conventions. Original supplied angle increment/frame/ranges are preserved; missing/invalid returns become null, and unseen angular space is not filled. The SVG displays only returns within the selected 2/4/8m radius.
- Strict navigation `valid_snapshot` remains unchanged (including its range/geometry/freshness limits). The preview cannot authorize motion, fabricate TF or create a calibrated room map.
- Robot emits bounded `scan_display_fault` reason changes; authenticated owner-only PC snapshot/UI show rejection codes beside the scan, rather than silently showing an empty graph. Codes: NOT_RECEIVED, STAMP_FORMAT, SOURCE_TIME, RAY_COUNT, ANGLE_ENDPOINT, DISPLAY_METADATA, MESSAGE_SHAPE, NONE. Raw capture remains unchanged.
- Official [ROS LaserScan contract](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/LaserScan.msg) documents message angles/ranges; [ROBOTIS COIN D4 driver](https://github.com/ROBOTIS-GIT/coin_d4_driver) is the upstream sensor implementation. No manufacturer stopping guarantee is inferred from either. The compatibility decision above is based on saved raw measurements, not a guessed driver specification.

## Verification / preserved failures

- Whole Web **197/197 PASS**, final `artifacts/joystick-continuity-20261003-web-r3.json` (r2 also PASS); includes readiness across new job/old release snapshot, no compact checkbox, one mode selector, 3.1s continuous WASD, release without connection close, legacy bounded hold and terminal-stop regressions.
- Related Python **155/155 PASS + 113 subtests**, `artifacts/joystick-continuity-20261003-python-r2.xml`: production manual worker keeps publishing beyond 3s without periodic release; expired nonce/input/session cannot renew; combined scan export→OFF inspection→verified resume works; all 105 saved real scan samples accepted by the display contract with original frame/spacing. Test-only decoder supports only this saved CDR1 little-endian LaserScan shape, not arbitrary ROS/TF replay. If private raw is absent, that particular audit is explicitly skipped.
- TypeScript and Vite build PASS. Actual built React/owned loopback App/headless Chrome with intercepted **synthetic physical responses**: final `artifacts/joystick-continuity-20261003-browser-r3/result.json` (r1/r2 also PASS). Tests scan-only never drives, >3s held joystick without periodic stop, turn/release without reconnect, active scan beside drive, combined sensor stop locks driving, mobile no overflow, connection failure hides controls. No physical process/requests or external requests. Automatic read-only status/attention/failure/retry regression also PASS: `artifacts/joystick-continuity-20261003-readonly/result.json`. Final desktop/mobile screenshot inspection confirms mode selection/connected state and visible scan/joystick without overlap.
- Initial sandbox Python run failed on Windows temporary-directory permissions: XML retained as `joystick-continuity-20261003-python-sandbox-failed.xml`. Authorized local no-device rerun found one genuine new display test failure (151 pass/1 fail), retained `joystick-continuity-20261003-python.xml`: count394 × angle_increment did not span 2π; the actual missing-terminal-bin convention was then bounded explicitly and all 105 raw samples audited. No old stop criterion relaxed.
- Local robot source ID: `eb47a7935eef71658e884ef1c2c3764a93d97add229720f63321383b7f32a85d`, **NOT_DEPLOYED this turn**. Previous source qualification is not reused for this changed robot release.

## Applying / remaining

- When no operation is active, close the old console's launcher normally with Ctrl+C and reopen `Open-Robot-Console.cmd`. Old Python backends retain old code even if the browser reloads the rebuilt static UI. Keep only the newly opened console for control; no PC/robot reboot needed.
- Explicit Prepare package → new release's required stop test → choose Drive + LiDAR → Connect. READY alone enables joystick. New qualification is once per boot/release, not per gesture. No automatic trial/retry.
- Next live acceptance needs an authorized on-site session for new release/continuous input/display timing. Latest failed raw export can be recovered separately through transfer-only recovery. Room calibration/TF, collision envelope and physical autonomous mission remain separate unfinished gates.
