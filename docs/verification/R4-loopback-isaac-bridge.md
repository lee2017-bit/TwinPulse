# R4 loopback API and actual Isaac bridge verification

- Date: 2026-09-16 KST
- Scope: local loopback transport, authenticated product/engine sessions, command broker, managed Isaac adapter, disconnect watchdog, and regressions
- Result: **PASS for the tested local scope**
- Full-run artifact: `artifacts/runs/20260916-212014` (git-ignored)

## Implemented boundary

- The backend binds only to `127.0.0.1` and exposes separate single-use product and engine bootstrap roles.
- Product mutations require an authenticated HttpOnly/SameSite session plus CSRF token. Engine endpoints require the engine bearer session. Host, Origin, query/fragment, role, schema version, payload size, lease, session, stage epoch, revision, and command TTL are checked.
- One bounded `CommandBroker` owns a single writer/engine, deduplicates commands, distinguishes queued cancellation from in-flight unknown outcomes, and accepts Build payloads only from a registered trusted artifact.
- The Extension bridge performs network I/O on its worker thread, transfers work through bounded queues, and executes USD/PhysX/compiler/runtime operations only from the Kit update thread.
- Managed mode disables the legacy Extension's competing product controls. A three-second lease and engine-local watchdog pause the runtime when the owned backend disappears; reconnect never resumes motion automatically.

This is the R4 bridge slice only. It does not add the React product UI, provider upload/generation endpoints, ROS2, MCP transport, WebRTC, remote binding, cloud deployment, or physical robot control.

## Pure contract and security tests

`tests/integration/test_r4_bridge_api.py` passed **6/6**. The suite covers:

- single-use bootstrap, product/engine role separation, cookie/CSRF, Host and Origin rejection;
- Build command delivery, exact retry idempotence, conflicting duplicate rejection, receipt/snapshot reconciliation, and product state projection;
- lease conflict/expiry, stale engine session and stage-epoch rejection;
- queued cancellation versus an in-flight command whose outcome becomes `unknown` after engine loss;
- wrong revision/version/extra fields and payloads larger than 256 KiB;
- engine crash timeout and safe reconciliation without silently retrying a mutation.

The same full runner also passed Core **24/24**, Provider **13/13**, R1 integration **9/9**, R3 application **9/9**, and the preserved actual-Isaac regressions.

## Actual Isaac acceptance

The owned backend and Isaac Sim 6.0.1 headless process were connected through the real HTTP bridge. The test used the registered `fixed_warehouse_v1` bundle and did not issue a paid provider request.

| Check | Result |
|---|---:|
| HTTP Build and authored TwinPulse prims | PASS, 32 prims |
| Run actual wheeled AGV motion | PASS, 0.670145454 m |
| Pause drift | PASS, 0.0 m |
| Reset position error | PASS, 0.0 m |
| GetState / Focus | PASS / PASS |
| Owned-backend termination watchdog | PASS |
| Runtime after backend loss | `paused` |
| Safety state / reason | `bridge_disconnected` / `Backend connection lost` |
| Post-stop drift | 0.0 m |
| Extension enable/disable and reconnect | PASS, 3/3 cycles |

The measured stop distance after intentionally killing the backend was 0.328420714 m before the stopped pose stabilized. This is a local prototype watchdog measurement, not a physical-robot stopping-distance guarantee.

## Integrated result

`scripts/verify_twinpulse.ps1` completed with:

```text
TWINPULSE_VERIFY_RESULT=PASS artifact_dir=C:\Users\jaewo\Documents\TwinPulse\artifacts\runs\20260916-212014
```

The manifest records `PASS_R3_R4_CONTRACTS` for the application side and `PASS_M1_M2_R2_R3_LEGACY_R4_BRIDGE` for Isaac. R5 remains a separate user-approved step.
