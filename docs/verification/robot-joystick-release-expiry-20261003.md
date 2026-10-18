# Joystick release vs session expiry — 2026-10-03

## Saved physical evidence, not a new device run

User reported that releasing the joystick locked control after successful scanning. Saved session `artifacts/manual-control/e9dfefa0d8354954bb19b78bbe3e4011` ended with `SESSION_EXPIRED`, not a release/idle failure. Boot `21e8a7e0-8e16-47c8-8a04-b12192373272`, deployed release `eb47a7935eef71658e884ef1c2c3764a93d97add229720f63321383b7f32a85d`, mode `control_scan`.

- Journal contains 575 published wheel commands over about 57.41 seconds (robot monotonic 360.909195360–418.321880691), 292 scan previews and 600 accepted input events. This measures publication duration, not floor distance.
- PC release input sequence 729 arrived at the expiry boundary; no robot release-request/idle-confirmation event follows it. Therefore this record does not prove that a normal release closed the session, or that this release was accepted.
- Original verdict remains FAILED/SESSION_EXPIRED. Final board observation reports torque disabled, raw wheel velocities `[0,0]`, zero command bytes and restored port. Robot cleanup and sensor cleanup are confirmed; `ros_stop_confirmed=false` remains preserved, not relabelled as true. Owned LiDAR driver exited 0 after SIGINT, independent sensor STOP/data-quiet checks completed. These are software/board observations, not measurement of physical rotor stopping.
- Complete exported raw: 607 scan, 1263 odom, 1263 dynamic TF, zero static TF messages; 4,128,438 bytes, SHA-256 `165ec6bd31b129d4844070c339916c96c8d23615b9072445b5cded66d0a2d69f`. Evidence export and session log are COMPLETE (4032/4032 events saved). Missing static TF, room alignment and physical autonomous acceptance remain gaps.

## PC-only correction

Show an approximate countdown from the first READY observation beside the joystick and connection status, plus a final ten-second expiry notice. The PC clock is explicitly approximate; the robot-local 60-second deadline remains authoritative. Temporary RELEASING now says that wheels are stopping and the connection remains open pending idle confirmation. Terminal SESSION_EXPIRED explicitly identifies the 60-second limit and offers Connect again; no automatic reconnect/resume.

Robot source, limits, physical stop qualification and navigation gates are unchanged. The saved physical evidence now confirms that the previous source was deployed/used; historical prior-turn NOT_DEPLOYED statements are historical. Loading this PC-only change does not require new deployment or a new stop test when the existing qualification still matches the current boot/release.

## Verification

- Web: 198/198 PASS, `artifacts/joystick-release-expiry-20261003-web.json`.
- TypeScript and Vite production build PASS.
- Synthetic Chrome rehearsal PASS, `artifacts/joystick-release-expiry-20261003-browser-r3/result.json` and `browser-result.json`: focused joystick, >3-second gesture, delayed 450 ms idle readback, release and second gesture in the same session with scan retained; mobile layout, stop and failed-connection branches. External requests 0, physical server requests 0, page errors 0. Connection setup also remains labelled Connected during wheel-stop confirmation instead of reverting to Connecting/Preparing.
- New unit regression covers approximate countdown, last-ten-second warning, transient stopping and expiry reason/no automatic restart.

No SSH, deployment, sensor/motor command or new physical test was performed for this correction. Synthetic release success is not physical release acceptance. Restart the PC console to load the new UI; reuse matching boot/release qualification and Connect explicitly for another bounded session. No power cycle is needed merely to reload this UI.
