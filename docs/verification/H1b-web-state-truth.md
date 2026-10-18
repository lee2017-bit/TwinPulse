# H1b web state truth — local verification

- Date: 2026-09-25 KST.
- Source boundary: local `main` HEAD `5c42899a95a0bf2422550bd17df7556a92ab3232` plus pre-existing uncommitted work. No reset, commit, or push.
- Result: **H1b WEB_UNIT_BUILD_MOCK_BROWSER_PASS / ACTUAL_ISAAC_NOT_RUN**. Mock responses prove UI state transitions, not a live engine acceptance.

## Change and contract

- The HTTP 202 `build_scene` response is **accepted**, not completed. The Review screen remains open while the operation is accepted or running. It moves to Simulate only after a successful engine receipt with the requested revision, current engine session/stage, and a matching current stage snapshot. A receipt alone cannot make an old scene look newly built.
- Input revision, draft revision, Isaac scene revision, and simulation runtime each have a separate status card. An input newer than its draft is marked outdated. A previous scene remains visible as **previous**, even when a new Build fails. A disconnected or replaced stage is unconfirmed, not treated as live. Build is disabled while pending; stale Run/Pause/Reset/Focus are disabled. Unknown and failed operations remain visible without implicit retry.
- The fixed CSS warehouse sketch is visibly labeled `Status illustration · not the live 3D view`; its AGV no longer animates with runtime state. Live telemetry numbers are hidden when the stage identity or telemetry flag is stale. The separate Isaac 3D window remains the actual 3D view.
- The frontend command response type now matches the broker's full `Operation.public()` payload. No broker, engine, protocol schema, provider, credential, physics, or installer behavior changed. Raw receipt message is not rendered in the command status; Details contains only status, short command ID, and error code.

## Verification

| Check | Result |
|---|---|
| `pnpm --dir apps\twinpulse-web test` | PASS, 18/18; accepted→running→receipt→matching snapshot, failed/unknown, previous scene, replaced stage, stale telemetry/input gate |
| `pnpm --dir apps\twinpulse-web build` | PASS, TypeScript and production Vite build |
| `node apps\twinpulse-web\e2e\h1a-browser.mjs` | PASS, existing no-call English/responsive smoke; generation requests 0 |
| `node apps\twinpulse-web\e2e\h1b-browser.mjs` | PASS, no-call browser accepted/running/receipt/snapshot/replaced-stage sequence |
| Browser screenshots | `artifacts/runs/h1b-browser-smoke/accepted.png`, `confirmed.png`; ignored local artifacts, not live Isaac images |
| `git diff --check` | PASS (Windows LF→CRLF advisories only) |

The first Vitest run failed before loading tests because the sandbox denied a Windows child process (`spawn EPERM`). The same suite passed under the approved test process; no test was skipped. This is not an application failure.

## Limits and next boundary

- Actual Isaac Build/Run, live provider call, paid request, ROS/physical robot, installer, company PC, commit, and push were **not run**. The existing verified engine behavior remains historical evidence, not new H1b proof.
- H1b does not implement H2 scene/robot/mission/map contracts or H3+ scanning and route comparison. Start H2 only on a separate request.
