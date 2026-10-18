# Actual disarmed base lifecycle — 2026-09-27 12:02 KST

User approved the prepared no-motion communication test, not LiDAR or movement.
Ran `scripts/prepare_robot.py --mode stationary` once with the existing release.
No new build/deployment, firmware, OS changes, torque enable, arm service, velocity
publisher, LiDAR or power command. Guarded base startup does perform its existing
gyro calibration, zero-output and heartbeat processing; this is not a read-only
serial operation. Motor torque remained disabled in all observed samples.

## Evidence

- Local: `artifacts/robot-preparation/20260927T030159Z-12272ca4/`:
  `result/report.json`, `result/report.html`, `transport.log`, copied `base.log`.
- Remote: `/home/twinpulse/.local/share/twinpulse/robot/reports/20260927T030201Z-ed269470/`.
- Release `1f444e2e03e4d16c7e4a62eaaa62bd11df000a6ca46c11f54b32fae6b227d603`,
  same boot `3394b6d9-5d94-402c-9e87-18204e04501e`.
- Run12:02:01–12:02:25KST; result **STATIONARY_CHECK_PASS**.
  Lifecycle events: idle_precheck → base_started_disarmed → base_reaped →
  independent_idle_read. Existing lease covered base/observer lifetime and final READ.
- Observer20.012s including startup discovery/calibration;318 SensorState samples,
  final guard `explicit_stop`. Observer enforces disarmed state, released buttons,
  sensor age<0.2s, fresh guard/sensor stream after startup allowance, one telemetry
  source, zero velocity publishers and existing2-tick anchor bound. No criterion changed.
- Observed message age1.93–13.64ms (mean6.47ms). This is message timestamp age,
  not measured actuator delay, network-loss latency or physical stopping time.
  Sensor voltage11.78–11.84V.318 samples over the startup-inclusive interval is
  not a claimed fixed sample rate or an IMU/odom/TF quality qualification.
- Base log shows serial open,5s gyro calibration, startup, then SIGINT/SIGTERM
  handler. Owned child exit0 via requested interrupt, no terminate/kill escalation.
- Independent board readings at12:02:02 and12:02:25:11.82V/voltage-estimated73.3%,
  torque=false, wheel raw velocities0/0, command bytes0, encoders2321/1626 identical.
  Both reads restored the serial settings they found. Final idle_port check passed.

## Scope of PASS / next

The deployed managed disarmed base/observer/cleanup path passed once on the real Pi.
This closes the previously untested ordinary stationary lifecycle, not every
failure-injection scenario, reboot persistence or all of D1/D2.
There is no new physical travel/stop test, lidar scan, obstacle-clearance finding,
full TF validation, live Twin integration or full demo acceptance. Previous physical
settling122ms<200ms FAIL remains unchanged.

Next: prepare the bounded LiDAR receive/stop/recording path before runtime;
then a separately scoped stationary sensor test and actual scan review in TwinPulse.
Do not repeat the unchanged base test or builds just to fill preparation time.
No further physical action follows this result automatically.
