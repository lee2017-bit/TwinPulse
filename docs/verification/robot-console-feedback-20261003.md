# Robot console feedback and idle lease — 2026-10-03

## Saved evidence / cause

- User-run `artifacts/manual-control/128db85c5696492789da1c8bce98cd80`: `INPUT_DEADLINE_EXPIRED`, no direction accepted/published. PC watch packets continued, robot accepted only two near failure. Idle watch incorrectly started a 250ms motion lease while outputs were disabled; nonce round-trip age reduced the remaining lease. Fixing this does not justify relaxing the moving deadline.
- `c75451cc12bc49829a34743187409f8f`: `LIDAR_DATA_QUIET`, `operator_cancelled=true`, STOP write complete, data quiet and port restoration. PC close delivery to final report took approximately 4.55s. UI lacked adjacent progress. Physical rotor stop remains UNCONFIRMED.
- `e3d24336ccfa42f59807549d3f6a305a` rejected an already-consumed trial, but its report hid the actual qualified trial `c91cb08282e0429b89984d654897a3bc`. No failed report is rewritten.
- Previous 14:51–14:52 read-only failures discarded SSH diagnostics; saved SSH-service observation placed availability after those attempts. Network failure alone does not prove boot state.

## Implementation

- Manual/control_scan validates idle watch then discards only its motion lease with outputs disabled. Fresh nonce, fresh post-arm direction, active 250ms deadline, 2s hold, 60s session, PC heartbeat, qualification and stop cleanup remain unchanged.
- Consumed-trial rejection with confirmed cleanup and no measurements remains a failed operation but does not substitute for the actual trial. Actual failed measurements/cleanup are not skipped. Robot still checks same boot/release qualification independently.
- SSH jobs save/display allowlisted cause and exit code, not arbitrary private stderr/key paths. Refused/timeout/no-route differ from authentication/host-identity failures. The console shows this robot's usual 2–3 minute boot estimate, not guaranteed/live readiness. Retry explicit; automatic check remains read-only.
- Setup shows elapsed time, ready/blocked state and next action beside controls. LiDAR shows sending→pipe-write delivery→robot STOP write/data quiet/port restoration. The latter is not physical rotor measurement. Repeated Stop disabled while pending; Force STOP remains available separately.
- English product text maintained. Major visual redesign awaits user benchmark selection; this patch is functional feedback, not completed redesign.

## Benchmarks

- [Foxglove Teleop](https://docs.foxglove.dev/docs/visualization/panels/teleop): directional pad, central Stop, stop-on-release, publish rate.
- [Transitive Remote Teleop](https://transitiverobotics.com/caps/transitive-robotics/remote-teleop/): video with joystick/overlay, explicit activation, demo video. Reference only; no new provider or copied safety thresholds.

## Verification / limits

- Python controller/diagnostics/source-identity/robot lifecycle **113/113 PASS**: `artifacts/robot-console-feedback-20261003/python.xml`. Tests include delayed idle watch in both modes, unchanged direction/active/session deadlines, rejected vs actual trial, safe SSH cause persistence and LiDAR final evidence projection without rotor claims.
- Complete Web **190/190 PASS**: `artifacts/robot-console-feedback-20261003/web.json`; TypeScript and Vite production build PASS. No new screenshot/visual acceptance claimed.
- Initial sandbox runs: Python temporary-folder PermissionError (78 failed/34 passed), Vite child spawn EPERM. Authorized normal-permission no-device runs passed. These are environment failures, not robot failures.
- New local robot source ID `3cd1a06d84a2d006148ec883aea121fc81bb65cfecc878d6de61c88c47367c8b`; user-observed release `e07a328081de6bbc03128ed0745b78ae151b7392b9b4e47c54848486ea9c2a74`.
- This turn: **SSH/deployment/sensor/motor commands 0**. Robot-side fix **NOT deployed/physically tested**; browser reload alone cannot apply it. Explicit deployment changes release and requires the new release's qualification; old receipt must not carry across.
- Remaining: benchmark choice/full visual redesign, corrected idle/combined-control physical acceptance, measured rotor stop, room calibration/collision envelope/autonomous demo. No physical or demo-readiness promotion.
