# S1d — process boundary and state isolation

Date: 2026-09-23 KST
Status: **PASS for S1d tested scope; full R6 remains PARTIAL**

## Scope

S1d closes three launcher gaps without making a paid provider request:

1. an owned Windows process tree must be reclaimed even when a wrapper leaves a descendant behind;
2. persistent non-secret provider settings, Windows credential identity, per-launch operational files, and engine mutable state must have explicit separate roots;
3. a live engine PID with a stale authenticated heartbeat must be reported as `engine_unresponsive`, expose only a secret-filtered log tail, and disable Run.

## Contract implemented

- Every real backend and engine root is assigned immediately after spawn to its own Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
- Shutdown first preserves the existing graceful path. If the root does not exit, it is terminated; a remaining process tree is terminated/closed through the owned Job Object. Production code uses no global `taskkill`, process-name kill, or unrelated PID traversal.
- `%LOCALAPPDATA%\TwinPulse\runtime\provider_settings.json` remains the persistent non-secret backend settings file. The credential target remains `TwinPulse/OpenAIResponsesAPI` and is passed explicitly to the backend. Tests use a unique target name and never read or write the user's saved credential.
- Operational status, logs, capture/result files, stop request, and engine state now live under `runtime\launches\<launch-id>\...`. A new run cannot consume another run's readiness, log, or capture file.
- The broker already rejects commands after heartbeat expiry. S1d additionally makes the launcher report `engine_unresponsive`; the React Run control also requires `engine_connected`, so a stale snapshot cannot leave Run enabled.
- Traceback/log tails pass through the credential marker filter before entering supervisor status.

## RED and GREEN evidence

The initial S1d tests failed because the manager had no credential target injection, used shared runtime files, did not inspect stale heartbeat, and terminated only the wrapper PID. After implementation:

```text
python -m unittest tests.integration.test_s1d_process_boundary -v
3 tests, PASS
```

The Windows fake-wrapper test confirms at least two active Job members (wrapper and child), then confirms the child no longer exists after owned shutdown. Python bridge/product/manager/S1d regression is 28/28 PASS. React/API tests are 10/10 PASS, including a disconnected engine with a retained `run` permission in the last snapshot. Production web build passes.

## Actual Isaac boundary

```powershell
python scripts\verify_s1d_process_boundary.py --isaac-python C:\isaacsim\python.bat --case both
```

Result: `artifacts/runs/20260922-235219-s1d-boundary/result.json`

| Case | Engine Job active members before stop | Engine exit | Shutdown | Result |
|---|---:|---:|---:|---|
| graceful stop-file path | 26 | 0 | 7.047 s | PASS |
| forced fallback (`graceful_s=0`) | 26 | 1 | 5.015 s | PASS |

Both backend roots also exited and a post-run process inventory found no remaining Isaac/Kit/Python process. The verifier records `paid_provider_requests: 0` and does not open a browser or access the provider credential.

## Limits and next gate

S1d verifies local Windows ownership, path isolation, stale-heartbeat reporting, and actual Isaac graceful/forced shutdown. It does not prove deliberately breakaway external processes, remote orchestration, company-PC reproduction, or physical robot safety. Full R6 remains PARTIAL until the stored M2-C managed replays, fresh-clone/company-PC reproduction, and approved live-provider App gate are closed. The next planned implementation step is S2a input decoding and immutable measurement binding.
