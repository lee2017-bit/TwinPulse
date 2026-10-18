# TwinPulse model combination pilot results and selection rationale

## Interrupted public role screening and reporting fix

The fresh40k role screen stopped after74 started cases and102 HTTP attempts.73 case reports were written:49 role-contract passes,11 inference failures and13 admission-not-run cases; the74th case has a timeout/UNKNOWN and no original result report.136 scheduled cases remain undispatched. The model-cost holdUSD.0764288 is preserved; total historical exposureNebius2.31278064/OpenAI1.81365030 remains within the originalUSD5/provider ceiling. This is not a completed all-model benchmark. [Complete35 role/model metrics-only table](../../outputs/benchmark-public-roles-20261011-v410-audit/metrics-only.md), [pre-change independent audit](../../outputs/benchmark-public-roles-20261011-v410-audit/audit.json), [cause/fix/remaining work](../verification/comparative-benchmark-overnight-20261011.md#타임아웃-후-집계-중단-수정과-부분-비교-v410).

Flash and Luna each passed6/6 observer contracts across3 public rooms/two repeats. They remain candidates, not photo-fidelity winners. Super/Ultra each passed only one planner case; comparative planner repetitions and current-code ordinary App/Isaac acceptance remain outstanding. Timeout/raw settlement ordering is now covered by offline regressions, but no paid replay was performed. The native automation isPAUSED under the UNKNOWN-cost stop rule; the lower running description is historical.

## Fresh output-cap diagnostic (separate source and consent)

The unchanged public-dining photo/render critic request returned valid final JSON twice at a40k cap, using7980 and3639 output tokens, in24.687 and12.265 seconds. New estimated Nebius costUSD.0216390; originals/settings unchanged, settled ledger and no pending lock. Both used fewer than20k, so this is **not proof that increasing the cap alone caused success**; the20k failure is a historical rather than concurrent randomized control. Critic uncertainty remained17/16 assessments. This is response-contract evidence, not photo fidelity or new App/Isaac/robot acceptance. [Raw-derived local probe metrics](../../outputs/benchmark-public-roles-20261011-v409/flash-cap-probe-report.json).

A new public-only role screen is running under fresh explicit consent until18:00KST and totalUSD5/provider including historical holds. It plans210 role/input/repeat jobs across3 independent public photos,24 Nebius generation models and Luna, at40k/300s. Some model contexts cannot admit40k and some conservative cost reservations cannot fit the remaining total: these are explicit untested limitations, not poor-model scores. Planner models share each room's first Luna observation (not human truth); role-only successes are not full ordinary App/Isaac journey passes. Luna preprocessing runs first, so no pure randomized latency winner is asserted. [Scope/evidence/precise remaining work](../verification/comparative-benchmark-overnight-20261011.md#출력-진단과-새-공개-입력-재시험-v409).

## Preserved source407 partial pilot

The October 11 development pilot exercised actual model calls through the ordinary TwinPulse chat App, scene generation, Isaac rendering, goal navigation, moving Stop and project reopening. It stopped after 20 of 60 scheduled trials: 8 functional passes, 12 failures and 40 not run. This is a reproducible task-specific partial pilot, not evidence of a global model winner or independently verified photo reconstruction quality.

The stop was required by an output-limit failure. A controller defect delayed that stop by five trials. All five remain visible in the results and cost accounting; they are not silently dropped, refunded or counted as compliant pre-stop execution. No new paid trial was started after the defect was detected.

## Model roles and common conditions

| Short name | Observer and photo critic | Planner and repair |
| --- | --- | --- |
| Flash Lightning | Nebius `deepseek-ai/DeepSeek-V4.1-Flash` | Nebius `nvidia/Nemotron-3_5-Lightning` |
| Qwen Lightning | Nebius `Qwen/Qwen3.8-27B` | Nebius `nvidia/Nemotron-3_5-Lightning` |
| Luna Lightning | OpenAI `gpt-6-luna` | Nebius `nvidia/Nemotron-3_5-Lightning` |
| Flash Luna | Nebius `deepseek-ai/DeepSeek-V4.1-Flash` | OpenAI `gpt-6-luna` |
| Luna Luna | OpenAI `gpt-6-luna` | OpenAI `gpt-6-luna` |

Repair inherits the planner and photo critic inherits the observer. Independent repair or critic combinations are not implemented. Text-only inputs do not call the observer or photo critic; the three Lightning text rows are repetitions of the same planner configuration, not three different image-model comparisons.

The schedule fixed three licensed public room photos, three independently authored text designs, five combinations and two repetitions per input. Input bytes, prompt and goal hashes, role settings, source inventory, runtime entrypoints, reviewed Burger assets, evaluator rubric and pre-output auxiliary references were frozen before execution. Paired input-by-repeat blocks used seed 61146, balanced execution positions and serial runtime operation. Every configuration received the same per-call 20,000-token output limit, 300-second HTTP timeout, 900-second generation budget, 24-request cap, three-repair cap and USD0.75 trial ceiling. Diagnostics were enabled for all trials.

The planned photos are [Afifa Afrin's bedroom](https://commons.wikimedia.org/wiki/File:Bedroom_with_a_almirah,_a_chair_and_TV_on.jpg), [Tim Collins's living room](https://commons.wikimedia.org/wiki/File:Living_Room.jpg) and [Stilfehler's dining room](https://commons.wikimedia.org/wiki/File:Orange_Dining_Room.jpg), under CC BY-SA 3.0. The bedroom uses a Commons JPEG thumbnail instead of the original MPO container; provenance and both input hashes are retained locally. The user's private bedroom is not an input to this pilot. Text designs cover a bedroom, office and warehouse, with the warehouse treated as a domain stress case rather than household generalization evidence.

Only the dining photo twice, bedroom photo once and warehouse text once were executed for each combination. Thus the observed coverage is two independent photo rooms and one text design, not the planned three rooms per modality. Living-room trials, all bedroom/office text trials, bedroom-photo repeat 1 and warehouse-text repeat 1 remain not run.

## Functional comparison

Each photo row had six planned trials and three executed trials. Each text row had six planned trials and one executed trial. A failure remains a failure; not-run trials are disclosed but are not called model failures.

| Input | Combination | PASS | FAIL | NOT RUN | HTTP wall p50 / p95 seconds | Estimated Nebius / OpenAI USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Photo | Flash Lightning | 0 | 3 | 3 | 39.531 / 48.671 | 0.046913 / 0 |
| Photo | Qwen Lightning | 1 | 2 | 3 | 38.468 / 48.790 | 0.089937 / 0 |
| Photo | Luna Lightning | 1 | 2 | 3 | 28.204 / 36.822 | 0.009866 / 0.004354 |
| Photo | Flash Luna | 1 | 2 | 3 | 56.313 / 71.303 | 0.063217 / 0.024195 |
| Photo | Luna Luna | 2 | 1 | 3 | 24.313 / 36.211 | 0 / 0.016647 |
| Text | Flash Lightning | 1 | 0 | 5 | 6.360 / 6.360 | 0.000911 / 0 |
| Text | Qwen Lightning | 1 | 0 | 5 | 10.719 / 10.719 | 0.002064 / 0 |
| Text | Luna Lightning | 1 | 0 | 5 | 9.297 / 9.297 | 0.002064 / 0 |
| Text | Flash Luna | 0 | 1 | 5 | 9.593 / 9.593 | 0 / 0.003169 |
| Text | Luna Luna | 0 | 1 | 5 | 13.093 / 13.093 | 0 / 0.004894 |

HTTP wall is the sum of recorded HTTP durations per trial, including failed trials, not individual-request latency or total App latency. These p95 values use only three or one observations and are descriptive, not reliable production tail-latency estimates. Generation active-time distributions are in the local metrics JSON. Instrumented CPU rankings are not used, and diagnostic-mode runtime must not be presented as uninstrumented product performance.

Actual requests total 113. Current-cohort usage estimates total **Nebius USD0.21497166 and OpenAI USD0.05325900**, with no unsettled current request or current retained billing reservation. Including all preceding carry-in costs and historical unknown reservations, exposure is **Nebius USD1.34577603 and OpenAI USD1.80602030**, within the original USD5-per-provider ceilings. These are accounting estimates, not independently verified invoices or account-balance deductions.

## Failure stages and correction recovery

| Failure stage | Trials | Evidence |
| --- | ---: | --- |
| Candidate compilation or photo revision | 10 | Below-floor placement, unsupported support, above-ceiling placement, observed-region contradictions or appearance/layout/support review failures persisted through bounded repair |
| Provider output contract | 1 | Flash photo critic returned `length` with 20,000 completion tokens, all recorded as reasoning tokens; generation terminated with `PROVIDER_OUTPUT_TRUNCATED` |
| Semantic navigation | 1 | A saved warehouse Twin could not provide a reachable approach to the requested target, `SIM_TARGET_NO_REACHABLE_APPROACH` |
| Moving Stop or reopen | 0 observed failures | Eight successful journeys reached these stages; earlier failures did not reach them and do not receive Stop/reopen credit |

All five combinations failed the executed bedroom-photo repeat. This is not proof that five distinct models failed consecutively in the same role: the shortlist contains only three observer models and two planner models. It also does not isolate model weakness from the common compiler, parametric library, support-placement or review policy.

Four of the eight passing journeys included at least one actual repair request before completion. Flash Luna recovered from a photo quality correction; Lightning text trials recovered from geometry corrections, and Qwen Lightning passed a dining-photo repeat after a repair request. These were fresh model responses, not replayed or injected successes. They show bounded correction can recover some natural failures, not that all failed layouts are repairable.

The eight passes bind the current semantic request, route plan and Isaac run/epoch/sequence to actual arrival evidence. Goal distances range from 0.039515 to 0.039822 metres, within the common 0.04-metre arrival gate. Each also passed a separate return movement stopped while running, one-second stable-pose verification, reload/reset and closed-backend reopening. This is simulated functional evidence, not measured robot accuracy, collision-safety acceptance or a mathematically optimal-path proof.

## Output limit and delayed stop

The original model response preserved `choices[0].finish_reason = length`, but the rejected-response record did not copy that field to its top-level metadata. The audit used only that metadata, producing a null finish reason. The terminal product code correctly said `PROVIDER_OUTPUT_TRUNCATED`, yet both campaign entrypoints checked only the null wire-summary field. Five more trials and 37 HTTP requests ran before detection; their estimated costs were Nebius USD0.06404805 and OpenAI USD0.02039960 and are included above.

On detection, a next-dispatch stop request allowed the already-running trial to settle and complete owned cleanup. No process was forcibly terminated. The frozen source was then used to regenerate the report and audit all 20 original trials before code edits. Both campaign entrypoints now stop on either an audited `length` field or the typed `PROVIDER_OUTPUT_TRUNCATED` terminal code. A normal completed response with 20,000 tokens is not guessed to be truncated. The original raw record, usage, failures and report remain unchanged. Offline guard regression and the existing saved campaign confirm `OUTPUT_LIMIT_STOP`; no paid retest or automatic replacement grant was issued.

## Conditional selection rationale

For an **all-Nebius Apps and Agents candidate**, use **Qwen observation and critic with Nemotron Lightning planning and repair** for the next independently reviewed cohort. It has a functional photo pass where Flash Lightning has none on the same three executed photo trials, plus a passing Lightning text run. The photo pass rate is only 1/3 and observed costs are higher than Flash Lightning, so this is a provisional candidate, not a production-quality endorsement. NVIDIA documents Lightning as an open Nemotron model, and the official Apps and Agents rules require Nemotron runtime use on Nebius Token Factory. [NVIDIA Lightning documentation](https://docs.nvidia.com/nemotron/nightly/nemotron/lightning35/README.html), [official hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules).

For a **hybrid retaining NVIDIA runtime**, **Luna observation and critic with Nemotron Lightning planning and repair** is a provisional option. It matches Qwen Lightning's observed 1/3 photo and 1/1 text functional outcomes, with lower recorded photo HTTP time and combined usage cost in this small pilot. OpenAI assistance is not an eligibility guarantee; the final submission must still satisfy the rules and should be confirmed with the organizers when mixed providers matter. [Official hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules).

Without hackathon provider constraints, **Luna Luna is the leading photo-generation candidate in this executed subset**, with two photo functional passes out of three and the lowest observed photo HTTP median. However, its warehouse-text run failed, all combinations failed the bedroom repeat and none has independently accepted photo quality. A **photo Luna Luna / text Nemotron Lightning split** is therefore a hypothesis for the next cohort, not a single demonstrated winning configuration. Flash Luna has a demonstrated natural photo-repair recovery but also the output-limit failure and higher observed photo cost and latency.

Physical AI is a separate track with Serverless Jobs and demo/submission requirements. Local Isaac runs alone do not establish complete track eligibility; neither does this pilot establish a ready physical robot demo. [Official hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules).

## Quality and statistical limits

Qualified full-quality passes remain **zero**. Passing photo reviews end as `uncertain`; there is no independent human blind review of positions, support relations, dimensions or visual fidelity. Pre-output required-kind recall is only an auxiliary lower-bound coverage measure. The fixed report aliases do not cover every tool or synonym, and failed scenes receive zero saved coverage; that number is not precision, F1, obstacle safety or room reconstruction accuracy. Explicit text dimensions are design contracts, not measured physical geometry.

All 20 family-adjusted room-paired comparisons are inconclusive. Only one photo room has both completed repeats for each pair; no text room has both repeats. Repeated trials are not additional independent rooms. The early output stop and five post-stop-rule dispatches further limit any claim. This is five shortlisted combinations, not all 25 catalog models, a held-out study or a global benchmark ranking.

Runtime entrypoints and reviewed assets were fingerprinted; the entire installed DLL, wheel, extension and driver closure was not frozen. GPU and driver were observed separately. Any future hardware, installation, policy, source, model or prompt change requires a separately identified cohort rather than pooling scores into this one.

## Reusing the benchmark

For another room photo or model, create a new dataset specification with lawful input provenance, transmission permission, prompt and goal hashes, independent room groups and evaluator-only labels established before model outputs. Never encode one bedroom's expected geometry into the model packet. Human-reviewed spatial, support and hazard labels plus blinded output review are needed before claiming reconstruction quality or generalization.

Use the existing preparation path, a fresh source/environment freeze and an explicit authorization bound to the new manifest. The preparation itself performs no inference:

```powershell
python scripts/prepare_benchmark_pilot.py <dataset-spec.json> <new-cohort-dir> `
  --catalog <reviewed-model-catalog.json> --version <new-source-cohort>
```

After valid current approval, the owner uses `scripts/run_benchmark_pilot.py` with that manifest and authorization. Only one owner may run; never remove foreign locks, repeat a started job, reset exposure or extend approval implicitly. Repair and final review remain bounded. Output-length, billing, unknown-cost, deadline and same-role distinct-model stop gates terminate admission rather than turning failures into passes.

Before editing any frozen source, generate the read-only report in a new directory:

```powershell
python scripts/benchmark_pilot_report.py <campaign-dir> `
  --manifest <cohort-dir>/manifest.json `
  --authorization <cohort-dir>/authorization.json --output <new-report-dir>
```

The preparation and authorization must not be changed to retroactively validate old trials. The existing source 407 campaign is closed to new execution because an output stop occurred and its source has since changed for the guard fix. A future cohort needs current authorization and all applicable carry-in exposure; old 403–406 scores remain separate.

The locally generated metrics are at `outputs/benchmark-overnight-20261011/report-407-final/public-pilot.json` and `.md`. The JSON intentionally retains the historical campaign state `RUNNING`, which does not describe a currently running owner; terminal owner stop is recorded separately without rewriting the original campaign. Manifest SHA256 is `d419c730ac154e5cc20ac2f55fe3ed4408fdd896441cf0b0078e329deab5b3b4`. Metrics JSON SHA256 is `8205fb05929805dd6b03d60f0b81da417678a6ad43ce2ab08a9b06fca7ceccc8`.

Publish only reviewed aggregate metrics and methodology. Do not publish private photos/prompts, raw responses, geometry, account metadata, credentials or the frozen local source archive. No GitHub push or external publication was performed. The follow-up automation is paused; unfinished benchmark coverage, independent quality acceptance and physical demo work remain explicit.
