# DP1 App no-motion collection path — 2026-09-30

Scope: PC-only source and fake-transport verification. The robot was OFF; no SSH, serial, sensor, motor, power, deployment, installation, cloud call, or real drive was performed.

## Product connection

- The authenticated default-project App now has an explicit, one-shot no-motion collection entry. Opening/refreshing it reads only local saved state. Start requires a fresh confirmation and runs the existing `run_robot_readiness.py --run` collector. That action can transfer reviewed source; it never grants motion authority or starts the ROS LiDAR driver.
- A durable single-flight job and physical-controller/read-only-check interlocks reject concurrent starts. Server restart or ambiguous remote completion becomes `REMOTE_STATE_UNKNOWN`; further robot operations stay locked until the operator confirms the robot is physically OFF. Saved results remain reviewable after restart.
- The App shows stage results, report path and odom/scan/TF status. Missing/rejected data remain evidence gaps. Status/exit-code contradictions and missing/invalid reports fail closed. UI status-read failure disables Start and displays an error; no automatic retry occurs.
- The operation manifest points stationary raw odom/scan/TF collection at the existing product route and fake HTTP test. This is a PC transport/product mapping, not a physical acceptance.

## Installability correction

The first App connection exposed a clean-release defect: `build_offline_release.ps1` copied the web panel but omitted its CLI, safety source/profile and local preflight tests. The release source list now includes those fixed code dependencies. The collection preflight was separated from the five-group *full demo* rehearsal: it runs only the connection/idle and LiDAR-recording contract groups, requires the locked safety profile and returns `COLLECTION_CONTRACTS_PASS_DEMO_LOCKED`. The full rehearsal still requires all five groups; an incomplete group map no longer reports its full offline status. Neither path grants demo/motion authority. Generic releases do **not** bundle the user's room photo or saved scan to make a check pass.

## Observed verification

- Python fake/contract tests: 21/21 PASS (`test_robot_readiness`, `test_robot_readiness_app`, `test_robot_demo_offline_rehearsal`).
- Web: 23 files / 178 tests PASS; TypeScript/Vite production build PASS. The new UI test covers status-read failure keeping Start disabled.
- A source-only isolated directory, with existing local `.venv` for Pillow, ran collection preflight without the personal room/model/scan artifacts: connection/idle 55 tests (3 platform skips) and LiDAR-recording 11 tests `PASS_OFFLINE`, final `COLLECTION_CONTRACTS_PASS_DEMO_LOCKED`. The isolated CLI's default offline source-bundle path returned `OFFLINE_ONLY`/exit 0. Its full demo rehearsal remained `OFFLINE_REVIEW_REQUIRED` because geometry evidence was absent. Earlier raw isolated attempts exposed missing packaged core tests and an unrelated Python/Pillow environment difference; those were corrected/controlled rather than counted as product PASS.
- `git diff --check`: no whitespace errors (existing CRLF warnings). No complete frozen clean-release build, installer, company PC, real ROS, or physical test was run in this increment.

## Remaining gates

This does **not** close DP1 or DP2–DP5. The next field opportunity, only after a new scoped operator approval, should collect and export actual same-boot/release raw odom/scan/TF, then inspect the report and original bytes. ROS COIN driver target build/lifecycle/rotor stop, as-built frame/room calibration, local collision protection, physical stop and autonomous mission remain separate locked gates. The current operation audit still reports `pc_demo_ready=false` and `manifest_mapped=false`; a successful collection cannot turn either true.
