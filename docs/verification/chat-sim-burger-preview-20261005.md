# Burger preview before simulation Run

2026-10-05 · Baseline v1.0.288. The selected pre-Run placement and explicit Reset path pass in actual local Isaac. Whole C1/C2 and physical demo acceptance remain incomplete.

## Product behavior

Fresh accepted SIM generation now Builds the current room with the existing Burger's `Physics=none` visual at the checked plan's illustrative start. Run explicitly creates the driven PhysX Burger and hides the visual, avoiding two displayed robots. Explicit Reset removes the driven robot, clears its plan/telemetry and restores the non-physical visual without Run. This is simulated placement, not physical localization or measured photo geometry.

The existing Build command accepts an optional registered `simulation_id`. The broker binds that plan to the exact scene revision, rejects unknown plans or incompatible saved visuals, requires the new `site_simulation_preview_v1` engine capability, and preserves request-ID idempotence. Existing Build without this field and ordinary v2 Run restrictions remain unchanged. Scene v1/v2 serialization and hashes do not change.

The adapter checks the plan and current fixed local asset inventory, then uses its existing owned-root transactional visual Build path. The composer references only the established local Burger asset, selects `Physics=none`, removes collision APIs in the stronger owned preview layer and requires meshes but no rigid-body, articulation or collision schemas. Source asset files are not edited. Only `/World/TwinPulse` is authored.

Fresh generation rebuilds its preview even if a previous scene shares the same geometry revision. Polling/restored chat history still grants no Build or Run approval. Unsupported engine or other preparation failures show the original reason and clear the Run plan; a preparation failure cannot leave Run enabled. Following chat goals continue to use current idle PhysX pose when available.

## Final evidence

| Check | Evidence | Result |
| --- | --- | --- |
| Fresh text journey | `artifacts/chat-sim-preview-20261005-text-final/result.json` | PASS; actual goal residual 0.03966270604 m, simulation time 4.25 s |
| Fresh photo-upload journey | `artifacts/chat-sim-preview-20261005-image-final/result.json` | PASS; actual goal residual 0.03966252591 m, simulation time 4.55 s |
| Final source and built Web | Each journey: 27 source + 3 build SHA256 entries | All match final files |
| Actual owned USD observations | Six preview transitions per final host receipt | Four visual meshes, zero physical schemas, illustrative position `[0.3600000000000001, 0, 0.002]`, motion authority false |
| Before Run and after explicit Reset | Visible preview, no site plan or driven Burger, timeline stopped | PASS; product telemetry false, run ID null, sim time zero |
| Explicit Run handoff | Hidden preview alongside one driven Burger/current plan | PASS; actual PhysX arrival, subsequent chat goal and Stop |
| Browser boundaries | Both browser receipts | Q1 waits; one automatic Build, zero automatic Run; Stop while folded; unchanged paused pose; reload no repeat/approval; explicit Reset no Run; mobile overflow/page errors absent |
| Selected Python regressions | simulation_goal/site_simulation/chat_conversation/h2b2_site_review | 83 PASS |
| Web regressions and build | 37 files/TypeScript/Vite | 289 PASS, build PASS; existing >500 kB warning remains |
| Existing browser/API cases | `artifacts/c1-chat-20261005-v288/verification.json` | Six cases PASS; source/build hashes match |
| Cleanup | Both final supervisors | Stopped; owned backend/engine cleared, host PASS |

The generation provider alone is an explicit local v2 fixture. Photo transport, validation, product commands, built React/Chrome and installed Isaac/PhysX/rendering are actual execution; no new LLM photo interpretation is claimed. Screenshots before Run and after Reset were inspected, with the static Burger visibly present. Earlier text-01 is preserved as evidence before the final failure-lock UI correction, not final-build acceptance. Frame counts 84/90 and screenshot FPS are observations, not a sustained performance guarantee.

## Reproduction and failures

```powershell
python -m unittest tests.integration.test_simulation_goal tests.integration.test_site_simulation tests.integration.test_chat_conversation tests.integration.test_h2b2_site_review
pnpm test
pnpm build
python scripts/verify_chat_sim_journey.py artifacts/<fresh-output> --case text
python scripts/verify_chat_sim_journey.py artifacts/<another-fresh-output> --case image
python scripts/verify_chat_c1.py --output artifacts/<fresh-regression-output>
```

New broker regression tests first reproduced the missing Build-preview contract (`command_shape_invalid`), then passed after implementation. Initial Web regressions exposed old fixture capability/Build-receipt expectations; those fixtures now model the stronger preparation contract, and the complete final suite passed. A further test requires unsupported-engine preparation to retain the exact reason, send no Build/Run, and leave Run disabled. Finite local tests used reviewed scoped execution permissions; no rejection or WSL failure was bypassed.

Base HEAD is `5c42899a95a0bf2422550bd17df7556a92ab3232` with pre-existing dirty changes preserved. Final receipts identify the exact reviewed source/build bytes. No commit was made. The increment is in broker, adapter, visual composer, Web API/Run card and related test/host evidence paths. Existing physical guards, raw evidence and historical failures remain unchanged.

## Remaining sequence

1. Complete startup dependency/asset manifest and prerequisite distinctions. Existing `startup_checks` still mostly checks file presence/version, disk and owned write access; it does not prove the complete package or capability/viewer/provider readiness matrix.
2. Implement and accept only reviewed bounded repair actions, and verify actual owned engine project-switch success. Installation, permissions/credentials changes, external downloads and original-project replacement remain excluded.
3. Broaden actual runtime fault/rollback tests beyond this accepted explicit Reset; broaden scene/robot selection and configured v2 live-provider photo/text acceptance separately.
4. C3–C6 REAL chat qualification, survey/correction, exact-route confirmation, five-second summaries and task loop still require implementation/acceptance. No robot power is needed for the immediate offline code work.

C1/C2 PARTIAL; whole-demo readiness=false. Robot/SSH/serial/sensors/motors/power/deployment/paid calls/install/system settings/commit/push/new agents: zero. Existing heartbeat remains PAUSED. This document deliberately distinguishes static preview, actual SIM Physics and unverified physical/live-provider results.
