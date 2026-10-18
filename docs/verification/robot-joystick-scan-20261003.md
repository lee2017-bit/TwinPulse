# Joystick and sensor-local scan console — 2026-10-03

## Delivered scope

- User selected a joystick-centered console with LiDAR buttons and live scan display. The existing product path was extended, not replaced by a disconnected mock UI. English product strings, Korean handoff.
- Connection setup is above scan/drive. The display is left, joystick right; mobile stacks them. The joystick maps only to the already reviewed fixed-speed forward/backward/in-place-turn intents. Release/cancel stops movement; direction change preserves the current segment's hold time. Existing keyboard and optional directional buttons remain.
- Scan-only viewing uses new owned `scan` mode, with wheels disabled and no motion receipt required. Combined driving and scan uses existing `control_scan`, requiring its source-bound physical stop receipt. One owner controls the base/serial/driver; no competing sensor process is started. **Stopping the combined scan closes driving too**; fully independent sensor termination inside a moving session is not implemented.
- Scan session remains bounded to 60 seconds, preparation to 8 seconds. No repeat/resume on failure. Cancellation is read during driver warmup. Owned driver shutdown, independent sensor STOP/quiet/port restoration and final board idle checks remain required.

## Data path and safety boundary

`ROS /scan → RosLink display preview → robot scan_preview journal event (at most 5 Hz) → validated owner-only PC snapshot → React distance-point SVG`.

- Separate `lidar-display-1.0` display contract accepts 72–720 full-circle samples with valid frame/stamp/range/angles. Invalid or missing individual distance returns become null/unknown; no filled free-space polygon. The original strict navigation contract is unchanged and continues rejecting missing ranges for navigation.
- Original raw serialized capture is not replaced by the display projection. Preview events join existing command/observation records. Robot source timestamps gate duplicate display emission; owner boundary and finite/shape validation apply at PC ingress.
- The view is **sensor-local +X up/+Y left**, not calibrated robot/room coordinates. It does not claim a room map, SLAM accumulation, photo alignment or collision avoidance. No room TF is guessed or inserted.
- PC receipt age plus robot sample age at emission are shown as freshness indicators; transport delay/clock alignment are unmeasured. Stale/interrupted reception and stopped cached scans are visibly distinguished. Return count/range radius are display options only.
- Scan-only rejects all direction input before torque enable. Moving input 250ms freshness, 2-second hard hold, 60-second session, physical qualification, independent halt cleanup and autonomous mission locks remain unchanged.
- Driver cleanup evidence is STOP write/data quiet/port restoration, not a measurement of the rotor's physical stopping.

## Verification

- Whole Web **196/196 PASS**: `artifacts/robot-joystick-scan-20261003-web.json`.
- Python controller/diagnostics/source identity/robot lifecycle/ROS observation **129/129 PASS + 5 subtests**: `artifacts/robot-joystick-scan-20261003-python.xml`. Includes real worker control-loop preview emission, scan-only no motion receipt/lifecycle, direction rejection, warmup cancellation, malformed scan/missing-return boundaries and owner-only preview projection.
- TypeScript and Vite production build PASS. Relevant tracked-file diff whitespace check PASS.
- Actual built React in headless Chrome with owned loopback App and **intercepted synthetic physical responses**: `artifacts/robot-joystick-scan-20261003-browser-r5/result.json`, `browser-result.json`. Scan-only never enables joystick; preview is rendered; combined joystick forward/turn/release maintains connection; combined Stop disables driving; mobile has no horizontal overflow; failed connection hides controls. No real controller process or physical server command in this fixture.
- Original automatic read-only/attention/failure/retry browser regression PASS: `artifacts/robot-joystick-scan-20261003-readonly-regression/result.json`.
- Desktop/mobile screenshots were visually inspected. Control-area screenshot: `artifacts/robot-joystick-scan-20261003-browser-r5/joystick-scan-controls.png`. Its scan is **synthetic**, not a scan of the user's room.

## Preserved failed checks / correction

- Browser r1–r3 failed on joystick drag. r3 hit-testing identified the sticky Stop bar covering the joystick, not a transport/motor issue. Removed its overlapping sticky positioning and placed compact Stop controls beside the joystick. r4 passed; final r5 passed after button placement and redundant completed-test button removal. All failed browser records retained.
- A newly added Python preview test initially observed the UI output callback instead of the worker's separate journal callback (128 pass, 1 failure). Fixed the test hook, no product threshold change. Failed XML retained as `artifacts/robot-joystick-scan-20261003-python-failed-test-hook.xml`; final 129 pass.

## Deployment / remaining acceptance

- Local source ID: `2763660e9e653a9fc5911573821761a7113cd764175701de63779d9f45740763`.
- Last user-observed robot release: `e07a328081de6bbc03128ed0745b78ae151b7392b9b4e47c54848486ea9c2a74`. New source **NOT deployed**. Browser refresh alone cannot apply robot-side display/idle fixes. Source mismatch keeps new scan paths locked and offers explicit preparation. New deployment requires that release's stop qualification before combined driving, not before stationary scan-only viewing.
- This turn: SSH/deployment/real sensor/motor commands **0**, Isaac **NOT_RUN**. Physical joystick/combined scan acceptance, real stream timing/rotor stop, room calibration/collision envelope and autonomous demo remain unverified/locked. No full demo readiness claim.
- Open the existing `Open-Robot-Console.cmd` to load the rebuilt UI. Do not infer authorization to deploy, spin a sensor or move from this verification record.
