# ADR 0003: Application/engine boundary and local session ownership

- Status: Accepted and implemented through R4
- Date: 2026-09-16

## Context

TwinPulse is moving its product UI out of Isaac Sim while the Extension remains the only owner of USD, PhysX and runtime callbacks. Splitting the processes introduces stale revisions, duplicate commands, role confusion and disconnect safety risks. R3 must fix the application and engine vocabulary before HTTP or React code exists.

## Decision

### Ownership and process topology

- The Python application owns one active local project, input revision, provider job and validated draft. The Isaac adapter owns actual stage state, the applied revision, telemetry and simulation safety state.
- The first release has one backend process, one worker, one active project and one connected Isaac engine. A second writer is rejected; there is no automatic fallback to the legacy writer.
- `ApplicationService` returns typed snapshots/events. UI labels are presentation only and are never parsed to make state decisions.
- USD/PhysX code remains in the Extension. The application package imports neither `omni`, `pxr` nor `carb`.

### Versioned engine contract

- `CommandEnvelope`, `CommandReceipt` and `SimulationSnapshot` schema version `1.1` are defined in `twinpulse_core.engine_contracts`. R4 adds the command issue timestamp needed for expiry checks while retaining strict version rejection.
- Commands are `build_scene`, `run`, `pause`, `reset`, `focus_scene` and `get_state`. Every command carries project, engine session, stage epoch, control lease, expected applied revision and a bounded TTL.
- Accepted/running is not success. The application recognizes a Build only after a succeeded receipt has the same command/session/project identity and applied revision.
- A timeout is an unknown outcome until state reconciliation; it is not proof that a command did not execute.

### Local authentication and bootstrap for R4/R5

- The R4 server binds only to `127.0.0.1` and still requires authentication. Product and engine roles use different random 256-bit bootstrap secrets and cannot call each other's endpoints.
- Bootstrap secrets are single-use with a 30-second TTL. They are never placed in query strings, logs, project files, diagnostics, provider settings or browser local storage.
- The owned launcher passes the engine bootstrap through the child process environment. Attaching a user-owned Isaac process requires an explicit, user-scoped handoff file under the private TwinPulse runtime directory; it is deleted after one successful exchange.
- The product browser bootstrap may use a URL fragment (not a query or request header) only during the first same-origin page load. JavaScript posts it once in the request body, immediately clears the fragment with `history.replaceState`, and receives a `Secure`-when-available, `HttpOnly`, `SameSite=Strict` session cookie. This residual local address-bar/process-list exposure is accepted for the loopback prototype and must be re-evaluated for a packaged wrapper.
- Product sessions have a 30-minute idle TTL. Engine sessions end on process/session change. A mutating control lease has a 3-second TTL and must be renewed every second. Expiry causes engine-local zero-drive and pause; reconnect never auto-runs.
- Default operation limits are 90 seconds for provider generation, 120 seconds for Build and 10 seconds for Run/Pause/Reset/Focus submission. The command envelope TTL remains at most 300 seconds. R4 must test reconciliation rather than silently retrying timed-out mutations.

### Persistence and credentials

- R3 `active_project.json` stores only the active input identity and validated draft. It is not the full portable project format planned for R10.
- Existing non-secret carb provider settings are imported once into the app JSON settings store. Later writes go only to the app store; there is no two-way synchronization.
- Both app and Extension use the existing Windows Credential Manager target `TwinPulse/OpenAIResponsesAPI`. Read APIs expose only configured/not-configured status; secret values are never returned in application events or engine payloads.

## Consequences

- R4 added loopback transport and an Isaac adapter without changing generation or Build eligibility rules. The server, broker, bridge and actual-Isaac watchdog are verified in `docs/verification/R4-loopback-isaac-bridge.md`.
- R5 can render typed state without inferring truth from labels.
- Multi-user, multi-worker, remote/WAN access, Tauri packaging, Replay and physical-robot commands remain out of scope.
- The browser-fragment bootstrap is constrained to the local prototype and is not an endorsement for internet-facing deployment.
