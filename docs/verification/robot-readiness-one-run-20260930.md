# One-run no-motion readiness collector — 2026-09-30

## What is actually integrated

`Run-Robot-NoMotion-Check.cmd` asks once before starting SSH/deployment, then runs the four-gate PC-only preflight before the existing reviewed-source preparation/idle snapshot and bounded 20-second disarmed stationary observer. It saves one top-level HTML/JSON result under `artifacts/robot-readiness/`, links each underlying report, stops on any failed phase, and refuses to combine reports from different boot or release IDs. No per-phase user answer is needed. A separately explicit pair of CLI flags can authorize one torque-OFF-only preparation on a confirmed flat, clear floor; ordinary execution does not. There is no automatic retry.

`scripts/run_robot_readiness.py` without `--run` bundles source locally only. `--run` or the CMD explicitly allows SSH and project-source deployment; it is **not** a read-only action. The new code has not been run against the robot. The operator should initiate it only in a newly authorized robot session. An SSH timeout leaves the remote state UNKNOWN and blocks following phases.

## Evidence judgment

The observer report carries exact odom/scan receipt and fault codes, `/tf` and `/tf_static` receipt, publisher counts and bounded examples. A completed idle lifecycle is distinct from sensor evidence: rejected odom, absent scan, absent TF or capture errors cause `EVIDENCE_GAPS`, not a green readiness result. The top-level report keeps `demo_ready:false`, `motion_authorized:false`, room alignment `NOT_VERIFIED`, and autonomous motion `LOCKED` regardless of received messages. The COIN ROS LiDAR driver is never started automatically; when there is no scan publisher, the report preserves `NO_PUBLISHER`. Physical rotor shutdown and room-frame alignment are not inferred from topic receipt.

## Local verification and remaining stages

No-device fake orchestration plus existing preparation/stationary/preflight regression: 38 tests run, 35 PASS and 3 Linux-only skips. A separate local default invocation returned `OFFLINE_ONLY` and saved a report without SSH. No robot, motor, sensor, driver, or deployment was used for this verification. The first sandboxed test attempt failed on the Windows temp-directory permission; same tests passed with approved temp access. No prior physical FAIL was changed.

This is the **first integrated non-motion evidence pass**, not the full 1–4 demo chain. ROS COIN driver lifecycle and physical stop, validated chassis/sensor/room transforms, local collision protection and scoped autonomous mission require further implementation and separately approved physical acceptance. Do not auto-chain them from this result or ask for confirmation after each passive diagnostic step. A future supervised motion session should have one bounded initial authorization, automatic local safeguards and a full command/observation journal, with automatic halt on faults.
