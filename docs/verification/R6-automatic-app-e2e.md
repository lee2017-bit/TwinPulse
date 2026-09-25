# R6 automatic App/Isaac verification

- Date: 2026-09-23 KST
- Status: **PARTIAL — local deterministic managed-launcher E2E and S1b three-run capture gate PASS**
- Evidence: `artifacts/runs/20260922-100347/r6-app` (local, Git-ignored)

## Implemented scope

R6 now has a single process manager and launcher for the local backend, the approved Isaac executable, and the browser product UI. The manager uses fixed executable/config paths, owns only the processes it starts, records a lock and finite readiness/failure state, and does not terminate unrelated user Isaac processes. Readiness requires an authenticated engine session, advertised capabilities, stage readiness, and an initial state snapshot rather than merely observing a PID.

The React header exposes backend/Isaac state and a provider settings panel. Non-secret provider settings are stored under `%LOCALAPPDATA%\TwinPulse\runtime\provider_settings.json`; the API key is stored separately in Windows Credential Manager as `TwinPulse/OpenAIResponsesAPI`. The GET API returns only whether a credential exists and never returns the key. Saving an empty key retains an existing credential.

`scripts/verify_app_e2e.py` starts the managed backend and a headless actual Isaac process, drives the browser workflow, captures both browser screenshots and the official Isaac viewport, records revision/state/trajectory metrics, then shuts down only its owned processes. `scripts/verify_twinpulse.ps1 -RunR6` is the optional full-suite entry point.

## Verified result

The finite run `20260922-100347` reported `TWINPULSE_R6_RESULT=PASS`:

- authenticated backend/engine readiness and capabilities: PASS
- browser upload → deterministic draft → review acknowledgement → actual applied revision: PASS
- actual Isaac Build/Run/Pause/Reset/Focus: PASS
- desktop, mobile, 125% zoom, Korean text, scroll and keyboard focus: PASS
- actual scene: 32 prims; observed `idle`, `ready`, `running`, `paused`
- maximum measured movement before Pause: 0.329136 m
- applied revision remained `67c662fa927c9b818ace344fc1ac7975f7049850254dec09767eb121a5eb9806`
- official Isaac viewport capture: 960×640, 484,381 bytes, non-black dynamic range 215, PASS
- process-manager unit tests: 5/5 PASS
- product API including credential redaction/retention: 9/9 PASS
- React tests: 5/5 PASS; production build PASS
- new paid/live provider request: **NOT RUN**

## Defects caught during R6

1. Windows PID probing used `os.kill(pid, 0)`, which terminates rather than probes a process on Windows. It was replaced with `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and `GetExitCodeProcess`.
2. Concurrent Windows JSON replacement could briefly fail with `PermissionError`. Runtime status writers now use unique temporary names and finite retry/cleanup.
3. The engine host queried robot position before a scene existed. The initial empty-stage state is now represented without treating it as an engine failure.
4. Readiness incorrectly depended on Build even though Build is draft-gated. Readiness now verifies authenticated stage/capability/state contracts only.
5. Capture scheduling was reset on every sample, preventing the viewport capture. The deadline is now stable.

## Remaining R6 acceptance

This result does **not** mark all of Phase 1 complete yet:

- replay of all three stored M2-C real-provider outputs through the new R6 manager, including mid-run and post-completion Reset, is still pending;
- fresh-clone/isolated backend install, frontend build and engine link are still pending for this uncommitted R6 revision;
- no newly approved live-provider App smoke was run.

Therefore the accurate status is **local deterministic automatic E2E PASS; R6/Phase 1 acceptance PARTIAL**. Existing legacy Extension UI remains intact.

## 2026-09-23 S1b capture-contract repair

The former capture race is now represented as a finite state machine rather than a single task-completion check. Request identity and timestamps distinguish task return, first file visibility, size stability, successful decode, and final promotion. Attempt files are run-local, retries are capped at one, stage/revision changes abort, and result JSON writes are atomic.

Pure failure-corpus tests passed 8/8. Three new actual managed runs passed end to end:

- `artifacts/runs/20260923-s1b-01/r6-app`
- `artifacts/runs/20260923-s1b-02/r6-app`
- `artifacts/runs/20260923-s1b-03/r6-app`

Each run completed Build, capture, Run/Pause, Reset/Focus and shutdown; produced a decoded non-black 960×640 current-revision viewport; applied 32 prims; and moved 0.337496 m, 0.374946 m, and 0.362503 m respectively. No retry or paid provider request was needed. Full details are in [`S1b-capture-completion.md`](S1b-capture-completion.md).

This closes the S1b capture gate, not the remaining stored M2-C replay, fresh-clone/company-PC, or live-provider R6 gates.
