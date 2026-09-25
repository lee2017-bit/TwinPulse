# S2b generation ownership verification

- Date: 2026-09-24 KST
- Scope: local product backend, application service, broker, React UI, and deterministic/fake transports
- Result: **PASS for S2b local acceptance**
- Paid provider requests: **0**
- Isaac application launch: **NOT RUN**
- Physical robot commands: **0**

## Implemented boundary

- `ApplicationService` is the single owner of immutable input selection, generation epoch, validated draft promotion, and project persistence.
- `ProductWorkflow` is a presentation/acknowledgement adapter. It freezes a `GenerationContext` before the worker starts so an input changed during thread startup cannot be mistaken for the requested input.
- The normal launcher uses `live_provider`. The deterministic provider is available only through the explicit `--fixture-mode` test flag. Provider/configuration failures do not fall back to a sample scene.
- One daemon worker performs provider I/O outside the HTTP/Kit threads. Cancel, input change, settings change, shutdown, timeout, and late response paths retain a finite terminal state and never promote a superseded result.
- Only a locally validated `GeneratedDraftRecord` is registered as a broker artifact. The product snapshot exposes input revision, plan hash, request/provider/model identity, tool count, object count, and source.
- Review acknowledgement is bound to both input revision and broker draft revision. Changing input or provider settings invalidates the acknowledgement and Build gate.
- Restart never silently enables Build. A saved draft requires current-input reselection/review; an invalid project file is preserved and shown as `project_restore_invalid` when the production backend opts into safe restore handling.

## Acceptance evidence

`tests/integration/test_s2b_generation_ownership.py` passed 7/7:

1. Different A/B inputs produce different plan hashes and broker artifacts.
2. Input replacement and cancel discard late success.
3. Invalid provider output returns a structured error and retains the previous record.
4. Acknowledgement is invalidated by an input change.
5. Restart requires reselection/review before Build.
6. Corrupt state is preserved and exposed as an explicit restore review error.
7. Live mode without a credential returns `provider_not_configured`; it creates no fixture draft or broker artifact.

Additional results:

- Full general-Python integration discovery: 73/73 before the final no-fallback case; the final S2b suite independently passed 7/7.
- Core: 24/24.
- Provider: 13/13.
- React/Vitest: 10/10.
- React production build: PASS.
- Official non-Isaac verification `artifacts/runs/20260924-140336`: PASS with 92 Python checks, React 10/10, and production build, including the final no-fallback and single-worker regressions.

The attempted direct `python scripts/verify_r5_web.py` was not an S2b failure: that script imports `isaacsim` and must run under Isaac Python. Actual Isaac was intentionally not launched in this step.

## Test-isolation correction

During development, an early test helper instantiated the default `%LOCALAPPDATA%\TwinPulse\runtime` project store. It wrote an explicit fake/audit draft to that default project file without using a credential or network request. All affected tests now use unique temporary project and input stores, and the official runner uses isolated paths. The current default local project file is therefore review-only test data; it must not be treated as a provider result or silently built. It is not automatically deleted because an earlier user project may have occupied the same path.

## Remaining boundary

- S2b does not claim a fresh multimodal provider call or actual-Isaac build.
- S2c remains the next implementation step: provider profile/capability identity, credential binding, atomic settings writes, and secret-canary tests.
- S2d remains replay/live evidence. S3 model list, Base URL, and API key configuration wait for the user-provided Nebius/NVIDIA details.
