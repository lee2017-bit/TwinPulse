# DP1 PC-only collection preflight cache — 2026-09-30

## Scope and result

The robot remained OFF. No SSH, serial, LiDAR, motor, power, deployment, Isaac Run, paid API, or field test was performed. This increment reduces work at the next explicitly approved no-motion collection; it does not complete the demo.

`scripts/rehearse_robot_demo_offline.py --collection-only` runs only the two collection contract groups and writes a passing local receipt. The receipt is bound to the collector, App/backend/safety source and tests, local Python path/version/platform, locked profile and calibration-file presence. The live collector checks the receipt before any SSH; if it matches and is at most 12 hours old, it reuses it. A missing, stale, mismatched, malformed or failed receipt causes local tests to run again. A failed local result or source change immediately after the check stops before robot contact. The five-group full-demo rehearsal remains separate and unchanged in meaning.

## Verification

- Focused no-device regression: 27/27 PASS, including cache reuse, expiry, source change, failure not cached, collector fallback, post-check source-change abort and saved App job contracts. It was run with the existing `.venv` and an authorized local temporary directory; the first restricted-shell attempt failed on temporary-directory permissions, not an assertion, and is not counted as PASS.
- Real PC-only `--collection-only` command: `COLLECTION_CONTRACTS_PASS_DEMO_LOCKED`, exit 0. Group 1: 65 tests (3 Linux-only skips); group 2: 11 tests, both `PASS_OFFLINE`. The actual `run_robot_readiness._offline_preflight()` read the receipt as `MATCHED`, with `motion_authorized=false` and `demo_ready=false`. No `--run` collector was invoked.
- The cached result verifies only the local source/Python-bound collection contract at the observed time. It does not prove installed third-party packages cannot change, actual robot reachability, ROS messages, original CDR, correct frames, physical stop, driver lifecycle, battery, clearance or autonomous safety. A different Python executable invalidates the receipt and forces recheck.

## Remaining

DP1 still requires an approved same-boot/release physical collection and original odom/scan/TF export/review. DP2 ROS LiDAR driver target build and lifecycle, as-built frame/room alignment, physical stop/collision checks, DP3 one-session mission handoff and DP4/DP5 product acceptance remain open. The App's explicit collection click may deploy reviewed source; this cache alone never initiates it. `pc_demo_ready=false`, `manifest_mapped=false`, and live motion stay locked.
