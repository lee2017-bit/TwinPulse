# Actual model-combination integration benchmark — 2026-10-10

Status: COMPLETED_BOUNDED_PILOT_WITH_FAILURES. This is a private, single-image integration pilot, not a general model leaderboard.
No physical robot was connected. PASS means the bounded ordinary App → actual Isaac SIM workflow completed; it does not mean measured photo reconstruction or collision-safe physical deployment.

## Protocol

- Fresh ordinary chat approvals and actual HTTP; no substituted model outputs or shared observation cache.
- Same source photo and prompt for every fresh trial; one private bedroom, no measured dimensions or independent test set.
- Each role: 20,000 output tokens, 300 s request timeout. Total active budget 900 s: initial420/repair300/final-render180. At most3 repairs,2 stalled repairs,24 HTTP per trial.
- Reviewer is the observer model: source photo + candidate-bound actual Isaac frame. It is not an independent human judge.
- Luna uses structured reasoning=none; Nemotron Lightning thinking is disabled. Provider-native preprocessing differs, with equivalent host constraints.
- Geometric checks, candidate/plan/frame identity, final save, current rendered 3D, explicit PhysX arrival≤0.04 m, next-goal/chat Stop,1 s stationary hold, reload/reset and closed-backend saved-project reopen are required for full PASS.
- Output-length exhaustion/unknown result stops new inference. Recorded rejected HTTP keeps unverified billing reserved; five consecutive distinct configurations with the same failure also stop.
- Code cohorts are separate. Failed trials stay in the denominator; no-call harness preflight failures are reported separately.
- Conservative per-trial financial grants vary from USD0.79 to USD1.00 as the campaign reservation decreases; request/token/time/repair caps remain fixed. No local financial grant exhaustion occurred.
- p50/p95 use linear interpolation. With these small samples, p95 and Wilson95 intervals are descriptive, not evidence of production reliability.

## Results by role and code cohort

| Observer / critic | Planner / repair | Code SHA | Full PASS / trials | Wilson95 | Requests | Repairs / recovered trials | Saved objects | End-to-end p50 / p95 s | Usage estimate USD | Held billing USD |
|---|---|---|---:|---|---:|---:|---|---:|---:|---:|
| DeepSeek Flash | Nemotron Lightning | `a5ea92ba5557` | 0/1 | 0.0%–79.3% | 7 | 2/0 | 0 | — / — | 0.013207 | 0.000000 |
| GPT-6 Luna | GPT-6 Luna | `ca8fb4c380d3` | 1/1 | 20.7%–100.0% | 5 | 0/0 | 10 | 92.47 / 92.47 | 0.005136 | 0.000000 |
| DeepSeek Flash | Nemotron Lightning | `ca8fb4c380d3` | 0/1 | 0.0%–79.3% | 8 | 2/0 | 0 | 91.31 / 91.31 | 0.014576 | 0.000000 |
| Qwen 3.8 27B | Nemotron Lightning | `ca8fb4c380d3` | 1/1 | 20.7%–100.0% | 6 | 0/0 | 17 | 103.05 / 103.05 | 0.034986 | 0.000000 |
| GPT-6 Luna | Nemotron Lightning | `ca8fb4c380d3` | 1/1 | 20.7%–100.0% | 5 | 0/0 | 9 | 82.19 / 82.19 | 0.003512 | 0.000000 |
| DeepSeek Flash | GPT-6 Luna | `ca8fb4c380d3` | 0/1 | 0.0%–79.3% | 7 | 1/0 | 0 | — / — | 0.011258 | 0.115000 |
| DeepSeek Flash | GPT-6 Luna | `64289a04a616` | 1/2 | 9.5%–90.5% | 19 | 6/1 | 20, 0 | 117.19 / 145.00 | 0.071344 | 0.000000 |
| Qwen 3.8 27B | Nemotron Lightning | `64289a04a616` | 0/2 | 0.0%–65.8% | 14 | 3/0 | 0, 0 | 73.16 / 78.91 | 0.053089 | 0.067715 |
| GPT-6 Luna | Nemotron Lightning | `64289a04a616` | 2/2 | 34.2%–100.0% | 11 | 1/1 | 9, 10 | 86.66 / 88.58 | 0.008815 | 0.000000 |
| GPT-6 Luna | GPT-6 Luna | `64289a04a616` | 2/5 | 11.8%–76.9% | 30 | 4/0 | 0, 9, 10, 12, 0 | 90.09 / 103.25 | 0.036187 | 0.000000 |
| DeepSeek Flash | Nemotron Lightning | `64289a04a616` | 0/2 | 0.0%–65.8% | 17 | 5/0 | 0, 0 | 82.04 / 88.39 | 0.028648 | 0.000000 |

Saved-object count is the model-declared inventory, not recognition recall. More objects can make packing harder; fewer objects can omit real obstacles. Zero saved objects in a failed trial does not mean its observation was empty.

## Failure and current-render verdicts

Historical Nebius HTTP402 remains in the original failed trial. The user manually activated paid usage; a separate HTTP200 probe and an explicit later request authorized ONLY three deferred trials. Their new grant subtracts all old usage, retained billing reservations and the separate probe. Original deadlines/failures/raw ledgers were not rewritten. No automatic retry, top-up or key switch was performed.

- DeepSeek Flash / Nemotron Lightning · a5ea92ba5557: terminal failures ['REPAIR_STALLED']; local root codes [['PHOTO_LAYOUT_REGION_FULL']]; origins ['semantic_candidate_or_local_geometry']; render verdicts {'NOT_REACHED': 1}.
- GPT-6 Luna / GPT-6 Luna · ca8fb4c380d3: terminal failures []; local root codes []; origins []; render verdicts {'uncertain': 1}.
- DeepSeek Flash / Nemotron Lightning · ca8fb4c380d3: terminal failures ['REPAIR_STALLED']; local root codes [['PHOTO_LAYOUT_REGION_FULL']]; origins ['semantic_candidate_or_local_geometry']; render verdicts {'NOT_REACHED': 1}.
- Qwen 3.8 27B / Nemotron Lightning · ca8fb4c380d3: terminal failures []; local root codes []; origins []; render verdicts {'uncertain': 1}.
- GPT-6 Luna / Nemotron Lightning · ca8fb4c380d3: terminal failures []; local root codes []; origins []; render verdicts {'uncertain': 1}.
- DeepSeek Flash / GPT-6 Luna · ca8fb4c380d3: terminal failures ['ProviderRequestError']; local root codes [['PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE']]; origins ['app_provider_contract_or_transport']; render verdicts {'NOT_REACHED': 1}.
- DeepSeek Flash / GPT-6 Luna · 64289a04a616: terminal failures ['REPAIR_STALLED']; local root codes [['PHOTO_LAYOUT_REGION_FULL']]; origins ['semantic_candidate_or_local_geometry']; render verdicts {'NOT_REACHED': 1, 'uncertain': 1}.
- Qwen 3.8 27B / Nemotron Lightning · 64289a04a616: terminal failures ['REPAIR_STALLED', 'ProviderRequestError']; local root codes [['PHOTO_OBSERVED_REGION_CONTRADICTION'], ['RENDER_APPEARANCE_MISMATCH', 'RENDER_LAYOUT_MISMATCH', 'RENDER_SUPPORT_MISMATCH']]; origins ['semantic_candidate_or_local_geometry', 'provider_billing']; render verdicts {'NOT_REACHED': 1, 'needs_revision': 1}.
- GPT-6 Luna / Nemotron Lightning · 64289a04a616: terminal failures []; local root codes []; origins []; render verdicts {'uncertain': 2}.
- GPT-6 Luna / GPT-6 Luna · 64289a04a616: terminal failures ['REPAIR_STALLED', 'SIM_TARGET_NO_REACHABLE_APPROACH', 'REPAIR_STALLED']; local root codes [['ROOM_ITEM_OUTSIDE_FLOOR'], ['SIM_TARGET_NO_REACHABLE_APPROACH'], ['RENDER_APPEARANCE_MISMATCH']]; origins ['semantic_candidate_or_local_geometry', 'simulation_navigation', 'semantic_candidate_or_local_geometry']; render verdicts {'NOT_REACHED': 1, 'needs_revision': 1, 'uncertain': 3}.
- DeepSeek Flash / Nemotron Lightning · 64289a04a616: terminal failures ['REPAIR_STALLED', 'REPAIR_STALLED']; local root codes [['PHOTO_LAYOUT_REGION_FULL'], ['PHOTO_LAYOUT_REGION_FULL']]; origins ['semantic_candidate_or_local_geometry', 'semantic_candidate_or_local_geometry']; render verdicts {'NOT_REACHED': 2}.

An `uncertain` critique permits only the explicitly labelled approximate-Twin workflow. It is not photo-fidelity PASS. Any claimed natural repair recovery requires an actual repair request followed by the complete path; an injected offline regression is not counted.

## Timing boundaries

End-to-end wall time includes isolated launch/preflight, browser actions, inference, Isaac, diagnostics, cleanup and reopen. Active generation time is separately bounded. Request time is the recorded HTTP wall time, not GPU compute time. Thread-CPU function profiles do not include network waiting and their cumulative nested times must not be summed as total wall time.
CPU-profile consistency warning: 2 trials contain at least one retained top function row with self time greater than cumulative time. Those CPU snapshots are not used for bottleneck ranking; timer/profiler calibration remains unverified. HTTP and end-to-end wall timings are separate measurements.

- a5ea92ba5557 DeepSeek Flash/Nemotron Lightning: generation active p50/p95 43.11/43.11 s; request p50/p95 3.67/9.99 s.
- ca8fb4c380d3 GPT-6 Luna/GPT-6 Luna: generation active p50/p95 31.78/31.78 s; request p50/p95 4.11/9.95 s.
- ca8fb4c380d3 DeepSeek Flash/Nemotron Lightning: generation active p50/p95 55.39/55.39 s; request p50/p95 4.03/12.32 s.
- ca8fb4c380d3 Qwen 3.8 27B/Nemotron Lightning: generation active p50/p95 44.88/44.88 s; request p50/p95 6.09/13.08 s.
- ca8fb4c380d3 GPT-6 Luna/Nemotron Lightning: generation active p50/p95 24.34/24.34 s; request p50/p95 3.19/7.66 s.
- ca8fb4c380d3 DeepSeek Flash/GPT-6 Luna: generation active p50/p95 33.41/33.41 s; request p50/p95 4.20/9.29 s.
- 64289a04a616 DeepSeek Flash/GPT-6 Luna: generation active p50/p95 66.33/83.51 s; request p50/p95 4.61/13.94 s.
- 64289a04a616 Qwen 3.8 27B/Nemotron Lightning: generation active p50/p95 36.86/42.44 s; request p50/p95 3.60/11.11 s.
- 64289a04a616 GPT-6 Luna/Nemotron Lightning: generation active p50/p95 29.54/32.02 s; request p50/p95 3.22/10.01 s.
- 64289a04a616 GPT-6 Luna/GPT-6 Luna: generation active p50/p95 31.19/57.92 s; request p50/p95 3.90/11.35 s.
- 64289a04a616 DeepSeek Flash/Nemotron Lightning: generation active p50/p95 45.76/51.76 s; request p50/p95 3.69/9.33 s.

## Accounting and reproducibility

No-call preflight failures: 1. Conservative current exposure: Nebius USD0.25743807, OpenAI USD0.2060348; caps USD5/USD1. These are usage-rate estimates plus retained unverified billing reservations, not invoices or account balances.
Full model IDs, per-trial aliases, cohort SHA, stage timing distributions and failure categories are in the accompanying metrics JSON. Source-code SHA identifies the inference/compiler path, not a clean committed release; the working tree contains pre-existing changes.
Reproduction requires a separately approved dataset, registered credentials and actual Isaac runtime. The campaign runner uses frozen reviewed cases and separate cost ledgers; refresh/report commands send no inference.
Private raw dispatch/response/validation records, usage ledgers, checkpoint revisions and plan/frame hashes are retained locally. This report excludes the source image, private room geometry/coordinates, original user text, credentials and raw responses. Nothing was committed or pushed.

## Limits and remaining acceptance

One photograph repeated on one host cannot demonstrate other-room generalization, furniture-size accuracy, support realism, obstacle recall, independent visual quality, long autonomous loops or physical safety. Only the stated generated SIM routes are exercised. An earlier hardware snapshot was below recommended Isaac VRAM/RAM; a current hardware probe was permission-denied and not bypassed. These bounded successes are not a complex-scene capacity certification.

## Explicit payment-block resume

Historical Nebius HTTP402 remains in the original failed trial. The user manually activated paid usage; a separate HTTP200 probe and an explicit later request authorized ONLY three deferred trials. Their new grant subtracts all old usage, retained billing reservations and the separate probe. Original deadlines/failures/raw ledgers were not rewritten. No automatic retry, top-up or key switch was performed.

Including the separate non-benchmark probe, conservative combined exposure is Nebius USD0.25743975, OpenAI USD0.2060348; unchanged caps USD5/USD1. Probe excluded from performance denominators. Account deduction/invoices remain unverified.
