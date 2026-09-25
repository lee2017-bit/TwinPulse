# S3c Nebius product wiring — no-call checkpoint

- Date: 2026-09-25 KST
- Scope: product Settings/API/React/composition-root wiring only
- Result: **PASS for product wiring and local live→Isaac Build/Run gate; photo fidelity remains unverified**

## Local live→Isaac result — 2026-09-25

- An intermediate live response returned an AGV start with nonzero z. Local validation correctly rejected it. The route resolver now projects start/goal z to the floor before checking the XY corridor; targeted Core+Provider tests 42/42 PASS.
- The same 80,073-byte warehouse photo and unchanged user prompt were submitted again. Gemma observer → Nemotron planner returned a validated draft `f658ca7d…c0dc`, plan `8caa89e4…5405`, 7 allowlisted tools and 35 objects for a 2WD+caster robot (no real robot was driven).
- After the approximate-model acknowledgment, the app applied that revision to actual Isaac stage `cfbb8e64…63c8`. The UI showed `Revision matched`, `build_scene · succeeded`, and `Built 90 TwinPulse prims`.
- The `Run` command completed; backend engine snapshot showed distance to goal ~0.0013 m, cross-track error ~0.00002 m, and near-zero roll/pitch. This is a local simulated completion, not a physical-robot result.
- The generated rack-row centers are x=-4/+4, y=0 with 12 m extents along x. Thus an identical route/scene may not visually match the source photo's left/right aisle. An Isaac viewport image was not independently inspected in this run. Do not treat scene fidelity as accepted. Fresh clone/company-PC reproduction remains open.

## Finite live addendum — 2026-09-25

- The user approved one run with the same image and prompt, at most two Nebius requests (Gemma observer then Nemotron planner), zero automatic retries, and an additional-cost ceiling of USD 0.50.
- Both model stages returned and the strict response reached local scene execution. The safety validator rejected the candidate route because it intersected `rack_row_left_shelf_1`. No further API request was made.
- Route ownership was corrected: the LLM still proposes observed geometry and a candidate AGV task, while local revision `straight-x-aabb-v1` preserves a safe route or deterministically selects a free positive-X floor corridor. The resolved coordinates replace the candidate in the persisted plan and are recorded in bounded provider provenance.
- Trusted measurement constraints are evaluated against the resolved final plan, so route synthesis cannot silently bypass a dimensioned-plan constraint.
- Core + Provider 53/53, S3c integration 4/4, and compileall PASS. The revised launcher reached backend-ready/Isaac-idle/key-saved state.
- This describes the earlier intermediate checkpoint. The later local live/Build/Run result above supersedes that pending status, but does not close photo fidelity or deployment acceptance.

## Implemented boundary

- Provider settings schema 3.0 migrates schema 2.0 OpenAI settings and adds explicit observer/fallback identities.
- The reviewed Nebius preset is locked to `https://api.tokenfactory.nebius.com/v1/`, `chat/completions`, observer `google/gemma-3-27b-it`, planner `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, and manual fallback `openbmb/MiniCPM-V-4_5`.
- The backend composition root selects `NebiusChatCompletionsPipelineProvider` only for that exact preset. Construction performs no key read and no request; runtime retry remains one attempt/zero automatic retries.
- The React Settings panel exposes an explicit OpenAI/Nebius preset choice and shows the observer/planner/fallback identities. Nebius endpoint/model controls are locked to the reviewed preset.
- Switching provider identity requires a newly entered key. Existing OpenAI credentials cannot be rebound to Nebius by checkbox alone.
- `settings_saved`, `credential_configured`, `capability_checked`, and `live_request_succeeded` remain separate. Nebius capability stays unverified until a validated live response.
- Input revision identity now includes adapter/profile/endpoint/observer/planner/fallback values.

## Verification

- Targeted S2c + S3c + Product API: 20/20 PASS.
- React: 10/10 PASS; TypeScript/Vite production build PASS.
- Official non-Isaac run `20260925-002818`: 116 Python tests, React 10/10, production build PASS.
- Manifest: `artifacts/runs/20260925-002818/manifest.json`.
- `git diff --check`: no whitespace errors; only existing line-ending warnings.

## Initial no-call checkpoint (historical; superseded by live result above)

- Nebius/API requests: 0.
- Credential read/write: 0 with user credentials.
- Isaac Sim, endpoint deployment, physical robot, commit, and push: not run.
- Before one live gate, explicitly approve exact models, maximum request count, observer/planner output-token caps, timeout, maximum spend, and automatic retry 0. A successful response must then pass local validation and be linked to the UI draft, Isaac build revision, and evidence receipt.
