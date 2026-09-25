# S1a ownership-safe shutdown verification

- Recorded: 2026-09-22 13:38 KST
- Status: **PASS for pure manager/launcher scope**
- Canonical root: `C:\Users\jaewo\Documents\TwinPulse`
- HEAD: `500f19992350d5b96877a9001d429656dfc7f748`
- Actual Isaac duplicate-launch test: **NOT RUN**
- Paid request / installation / physical command / commit / push: **NOT RUN**

## Contract implemented

- Every manager receives a random launch instance ID and records it with owner PID and start time in `launcher.lock` and `supervisor-status.json`.
- The engine stop request now lives at `runtime/launches/<launch-id>/engine-stop.request` and contains the same launch ID and owner PID. The engine process receives only that instance-specific path.
- A manager that failed validation or did not acquire the lock returns from `stop()` without creating directories or changing shared runtime files.
- A second `stop()` is idempotent. It does not recreate the stop request or rewrite terminal status.
- A duplicate launcher preserves the existing lock, backend-ready, engine-status, and supervisor-status bytes.
- A partial, malformed, temporarily unreadable, or access-denied lock is not assumed stale. Reads use a small bounded retry and return a diagnostic while preserving the file.
- A valid lock is deleted only if its launch ID and owner PID still match the releasing manager.
- Backend and engine spawn exceptions are classified independently as `backend_spawn_failed` and `engine_spawn_failed`. Cleanup stops only processes registered by that manager.
- The launcher ready line includes the non-secret launch ID for diagnosis.

This step does not add process-tree ownership; that remains S1d. It also does not claim that a second real Isaac launch has been exercised.

## RED baseline

Command:

```powershell
$env:TWINPULSE_TEST_TMP='C:\Users\jaewo\Documents\Codex\2026-09-12\dl\work\s1a-red-tests'
python -m unittest discover -s tests\integration -p 'test_r6_process_manager.py' -v
```

Before the implementation the suite exited `1`: 9 tests ran with 3 failures and 2 errors. The failures were confined to the new S1a expectations: non-owner stop mutation, missing instance metadata, malformed-lock deletion, unclassified spawn failure, and validation-finally mutation.

## GREEN evidence

Commands:

```powershell
$env:TWINPULSE_TEST_TMP='C:\Users\jaewo\Documents\Codex\2026-09-12\dl\work\s1a-final-tests'
python -m unittest discover -s tests\integration -p 'test_r6_process_manager.py' -v
python tests\integration\test_s0_audit_regressions.py S0AuditRegressionTests.test_a02_non_owner_stop_does_not_signal_the_owner_runtime -v
python -m py_compile packages\twinpulse_app\src\twinpulse_app\process_manager.py scripts\twinpulse_launcher.py
python scripts\twinpulse_launcher.py --help
```

Results:

- manager/launcher regression: **10/10 PASS**, exit `0`, 0.183 s
- S0 A-02 regression: **1/1 PASS**, exit `0`, 0.004 s
- Python compilation: PASS
- launcher argument/import smoke: PASS
- `git diff --check`: PASS; existing Windows LF→CRLF notices only

The remaining S0 A-01 and A-04 tests intentionally stay RED until S2b and S2a respectively; they were not hidden or weakened to close S1a.

## Source hashes

| SHA-256 | Path |
|---|---|
| `BDED81DBF02F90625A44DA3BFD2A6D246D9A50723DB96B0FADFC2F2D768E0765` | `packages/twinpulse_app/src/twinpulse_app/process_manager.py` |
| `CB5FC8676C44B44192CFCC99E31463C76E72BDC2C631AAF6C15E0E282C41A7A8` | `scripts/twinpulse_launcher.py` |
| `C01419001030C9A36418E35010B0F6EA62C71B85A11E6A48A9C9684585D40E3A` | `tests/integration/test_r6_process_manager.py` |
| `078051CC5EBF9502F46EEECF7D8571B3FC34561FAE26175B1470472AEABAE849` | `tests/integration/test_s0_audit_regressions.py` |

The broader pre-existing dirty-source inventory remains in [`S0-audit-baseline.md`](S0-audit-baseline.md). No unrelated user change was reverted or committed.

## Next gate

Proceed to **S1b: capture completion contract**. Start with fake capture tests for late/partial/empty/black output, missing viewport, exceptions, never-completing futures, and stage-revision changes. Do not launch Isaac until the finite unit contract is green and the actual three-run gate is explicitly approved.
