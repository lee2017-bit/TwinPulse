# M2-B multimodal provider integration

## Result

The image-first tool-orchestration path passes a user-run single-image provider E2E, generated-scene Build, reload restore, and local Isaac physics verification. The separate three-image M2-C evaluation remains pending.

## Implemented

- Copilot-style Settings window for Base URL, Model ID, reasoning effort, and masked API-key entry.
- Persistent non-secret Kit settings and Windows Credential Manager secret storage. A blank key field preserves the existing credential.
- One-image local picker and preview for PNG, JPG/JPEG, and WEBP up to 10 MB. An attached image is placed before optional text constraints in the provider request.
- Modern `POST /responses` adapter with `input_image`, optional `input_text`, strict scene-tool-plan JSON Schema, `store: false`, one attempt, timeout/cancel, and typed authentication/rate-limit errors.
- Numeric bounds in the provider schema mirror the local tool registry. Semantic rejection now includes a bounded, secret-free cause such as a blocked route or expanded-object limit instead of a generic invalid-plan message.
- An allowlisted typed tool registry for floor, walls, rack rows, pallet stacks, aisle markings, static AGVs, one predefined driven AGV, and one navigation task. The LLM cannot supply Python, shell, arbitrary USD, assets, or web fetches.
- Deterministic local tool expansion followed by existing bundle and positive-X controller-route validation. Rack rows expand into posts and shelves rather than one solid box.
- Generated draft persistence with a plan hash and reload restore. Persisted data excludes the API key, prompt, image bytes, and image path.
- **Build Generated Scene** has no implicit sample fallback. Preview, UI status, console log, and `/World/TwinPulse` metadata distinguish generated-tool-plan content from explicit test/demo fixtures.
- The live PhysicsScene prim remains stable while only TwinPulse-owned scene content is replaced.
- One approximation warning per Extension session before the first Build or Run.

## Verification

- Python compile check: PASS.
- Core tests: 20/20 PASS, including allowlist validation, rack expansion, record serialization/hash tamper detection, route gates, long-route recovery, and off-route safety stop.
- Provider tests: 8/8 PASS, including request-body image/schema shape and structured response parsing.
- Isaac 6.0.1 MinimalRendering/CPU regression: PASS.
  - Settings window and approximation warning constructed.
  - Allowlisted tool plan expanded and replaced the current scene with 50 owned prims.
  - An intentional mid-replacement failure restored the previous scene without replacing the live PhysicsScene.
  - `build_scene(None)` rejected the former implicit sample fallback.
  - Three run/pause/reset cycles and three Extension lifecycle cycles passed.

## User-run real image result

- `gpt-5.6-luna` received one attached warehouse image and returned `warehouse_aisle_scene_01`.
- Audit: `images=1`, 14 allowlisted tool calls, 59 expanded objects, plan hash prefix `a135a31a65d7`.
- **Build Generated Scene** authored 134 prims with `generated_tool_plan` source; it was not the M1 sample fixture.
- The same persisted draft/plan hash was restored after restart.
- The first long Run exposed an open-loop drive defect: equal wheel speeds accumulated yaw error and the AGV drifted toward a rack. Runtime now derives yaw from the live WXYZ pose, recomputes goal heading every physics step, and stops with a Reset-required status if cross-track error exceeds 0.20 m.
- Local Isaac long-route regression completed 6.9 m within 0.049724 m of the goal with 0.005134 m maximum cross-track error.

## Not run

- No API key was created, read, or supplied by Codex.
- No paid external request was sent by Codex. Real requests were initiated by the user in the Extension.
- The closed-loop fix is locally verified in Isaac headless physics; one user-visible restart and saved-draft Build/Run should confirm corrected motion in the same generated scene. This does not require another provider call.
- The three-image M2-C fixture evaluation remains pending.

## Recommended first evaluation

Start with `gpt-5.6-luna` and reasoning `low`. If scene structure or image interpretation is materially unreliable across the fixed evaluation set, retry the same fixtures with `gpt-5.6-terra` rather than silently raising reasoning or changing prompts between runs. Use Sol only as an upper-bound comparison if Terra is still insufficient.
