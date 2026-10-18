# Actual bounded LiDAR recording — 2026-09-27 12:13–12:14 KST

## Result / scope

**Real raw capture + offline sensor-native scan decoding PASS in this limited scope.**
This is not a ROS LaserScan, world TF, free-floor, autonomous navigation or whole-demo PASS.
User approved proceeding with sensor reception/shutdown/recording after the stationary base check.
No wheel enable/write, velocity publisher, base/ROS driver startup, firmware or system installation.

One fixed sensor START, 8.0002 seconds of reception, one fixed STOP. After 2 seconds
of settling/draining, a further 1-second observation received zero bytes.
Both modem-control lines and termios were restored, serial closed; subsequent `fuser`
reported neither ttyUSB0 nor ttyACM0 owned. **Physical rotor stop remains UNCONFIRMED**;
an asynchronous operator-observation question was sent. Silence is not rotor feedback.

- Raw data: **103,448 bytes**, 1,200 host receipt chunks.
- Valid checksummed packets **1,303**, bad checksum **0**, invalid packet header **0**.
- Non-scan prefix bytes 70; incomplete trailing bytes 0.
- Vendor parser decoded **30,116 samples**, independently matching packet sample counts.
- **74 complete ring-to-ring scans**, 356–415 samples each (initial/final partial rings excluded).
- Last complete scan: 403 samples, 389 usable returns / 14 invalid by the recorded
  vendor zero/low-quality rule. Nominal returned ranges 0.509–4.009 m.
- Selected scan angle increments 0.703–1.1094 degrees, median 0.891. **Not uniformly
  spaced**: do not assign an invented constant increment to these native points.
- Before/after board READ: **11.69 V / voltage-estimated66.1%**, torque flag false,
  wheel speed0/0, command bytes0, encoders2321/1626 unchanged. Battery figure is not
  calibrated remaining capacity and is historical as of12:14:05KST.

## Evidence

Local root: `artifacts/lidar-capture-20260927-1214/`.

- `lidar-20260927T031354Z-323c99a6/report.json`, `raw.bin`, `chunks.json`, before/after-board logs.
- `nodes.ndjson`: actual patched vendor parser output; `nodes-asan.ndjson` identical by `cmp`.
- `review/summary.json`, `native-points.json`, `preview.svg`: offline integrity summary
  and scientific sensor-native scatter plot. Missing points are unknown, not free space.
- Raw SHA256: `4b6d732b717e2cc6242366e3a6040d5212b59b3271be76d525466b45a6e39e07`;
  transferred raw file matched the robot receipt.
- Remote report: `/home/twinpulse/.local/share/twinpulse/robot/reports/lidar-20260927T031354Z-323c99a6/`.
- Capture script SHA256: `a9adb276c5fa803697f22d715459f7b92f8e4ff44cc2c36d3dda8c70cd57e815`,
  local and transferred file matched before execution. Uploaded only into a separate
  hash-named incoming directory. **Permanent current release and installed vendor driver unchanged.**
- Existing qualified READ release `1f444e2e03e4d16c7e4a62eaaa62bd11df000a6ca46c11f54b32fae6b227d603`;
  boot ID `3394b6d9-5d94-402c-9e87-18204e04501e`.

## Implementation / why not start the ROS node yet

`packages/twinpulse_robot_safety/lidar_capture.py` reuses the current verified release's
OpenCR flock, READ helper and disarmed pre/post conditions. Sensor by-id is fixed to
the known CP2102, fuser idle check + TIOCEXCL, 230400 8N1/DTR low. The script sends only
the vendor fixed START/STOP bytes already used in the prior authorized probe.
There is no runtime command/device override, no motor-write path, no automatic restart.
Memory is bounded to512KiB; capture8s with12s acquisition alarm; cleanup sends STOP even
if START is partial, drains2s then observes1s, at most one extra STOP if not quiet.
Repeated interrupt signals cannot interrupt cleanup; saved settings are restored and
descriptor closed. SIGKILL, power loss, USB failure or a stuck kernel cannot guarantee
physical stop. Existing unmanaged processes do not honor the OpenCR flock; fuser is
not a perfect protection against a racing unmanaged opener. No such owner was observed.

Source review of pinned `coin_d4_driver`8277b288 found that the ROS node's stop path
joins its grab thread **before** writing STOP. Rather than claim the previous parser
patch fixes lifecycle behavior, this test used the bounded raw recorder and decoded
after stopping. The old installed ROS driver was not started or replaced.

`docs/verification/coin-d4-offline-tests/decode_recording.cpp` compiles the **actual
patched vendor parser** against in-memory serial substitutes. No serial implementation,
ROS node, sockets or device access is linked; any attempted write aborts. It retains
vendor native angles/ranges, not the ROS publisher's uniformized representation.
`scripts/review_lidar_recording.py` independently validates packet checksums/counts,
binds raw hash, rejects decoder diagnostics, selects a complete ring and creates the
preview. It never assigns a world transform or claims obstacle clearance.

## Tests

- New capture lifecycle tests: **6 PASS**, including partial/failed START, read failure,
  interruption, size budget, configuration failure, STOP retry without START retry,
  unconfirmed stop and restoration failure/close.
- New offline recording integrity/preview boundary tests: **4 PASS**, including every
  packet truncation point, checksum/count rejection, provenance hash and no invented TF.
- Existing actual-parser synthetic regression: **222,738 assertions PASS** on PC WSL.
- Real recording decoded using warning-clean C++14/O2/Werror build and ASan/UBSan build;
  both exit0, output byte-identical, no sanitizer report (leak detection disabled).
  Parser reports one non-OK result at EOF, no malformed-packet diagnostics.
- Existing device-free runtime8 + stationary17 + preparation-client5: **PASS in WSL**.
  Initial Windows run had temporary-directory WinError5 failures; that failed attempt
  is not counted as PASS. WSL launch initially required permission; authorized existing
  WSL was then used without installing/changing any system component.
- `git diff --check` on touched paths PASS. No commit/push.

## Next / unchanged blockers

The useful new artifact is a real stationary sensor-native scan, available for offline
development without keeping the robot scanning. Next: preserve nonuniform beam angles
in the adapter, establish sensor-to-base/world orientation/TF and connect truthful real
scan review to TwinPulse. Do not fabricate a scene/profile binding merely to import it.
ROS runtime remains untested here; physical rotor stop awaits observation.
Existing command-stop122ms vs required200ms FAIL, D2 physical runner, navigation and
integrated demo remain unresolved. No further physical execution is implicit in this report.
