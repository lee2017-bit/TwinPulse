# Adaptive A2 — named project isolation, first offline increment

Date: 2026-09-29 KST. **A2 PARTIAL**. Robot reported OFF; no SSH, serial, sensor, motor, deployment, paid provider, or actual Isaac execution.

## Product path changed

- The existing R6 launcher accepts an explicit portable `--project-id`. `default` still uses the prior `active_project.json` and input directory. A named project stores its existing v2 `ProjectRecord`, input snapshots, and derived-review sidecar beneath `runtime/projects/<id>/`; no old state is moved or rewritten.
- The launcher carries one validated ID to the backend `ApplicationService` and `CommandBroker`, and to the managed Isaac adapter through the owned engine environment. The engine and broker therefore use the same project identity; a different project's command cannot pass the existing project check. No auto Build, Run, robot connection, or physical permission was added.
- `ProjectStore` rejects path-like IDs, mismatched stored identities, symlinked/out-of-root state paths, and overlapping writes for named projects. A corrupt named record fails startup rather than silently becoming a blank writable project. Existing default-project recovery behavior remains unchanged. Stale named `.lock`/`.tmp` files fail closed and require inspection; they are not automatically deleted.
- This is **process-start selection**, not a hot project switch or a completed UI. The existing hard-coded bedroom photo recipe/Burger fixture and shared physical history path have not been generalized or claimed to be project-isolated. Project-scoped image bytes are saved only through the existing `InputArtifactStore` path; no new executable reference or asset importer was added.

## Verification

- New isolation tests: two named projects with different photo bytes and input revisions, restart without implicit Build authority, default path unchanged, traversal/name rejection, corrupt identity, concurrent writer rejection, and stale temporary preservation: **4 PASS**.
- Existing R3 application and R6 process-manager regression together with new tests: **25 PASS**. R6 additionally checks `--project-id` propagation and rejects `../outside`.
- Entire local offline verifier `scripts/verify_twinpulse.ps1 -SkipIsaac`: **PASS**, final artifact [`20260929-032726`](../../artifacts/runs/20260929-032726/) (preceding pass [`032506`](../../artifacts/runs/20260929-032506/)); core 173, Web 125/125 and production build, existing integration groups. The final A2 test was also run separately after its last addition, 4/4 PASS. A2 is included in the verifier for subsequent runs.
- The first focused test attempt under the sandbox used the system Python (Pillow unavailable); a second attempt used the repository venv but Windows temp access was denied. Normal-permission venv rerun passed. These were environment/harness failures, not claims of passing tests.
- Actual Isaac managed startup with a named project and Web project-open UI: **NOT_RUN**. Robot/physical readiness/stop qualification: **NOT_RUN** in this increment; prior failure records remain.

## Remaining A2

Versioned room recipe and relative asset/evidence references with hashes, per-project sensor/mission history, explicit project-open/continue UI, copied-root/missing-asset tests, and an actual managed Isaac round trip. No photo guess is promoted to metric geometry or odom/TF calibration. Current default bedroom preview remains bound to its original photo hash.
