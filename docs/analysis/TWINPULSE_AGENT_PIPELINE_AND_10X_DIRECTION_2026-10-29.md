# TwinPulse: the agent pipeline today, and what a 10× more capable model changes

Written 2026-10-29 from the Oct 26 source review (branch `claude/project-thread-l7md32`) and the master narrative §6 and §12 ("Design for an Agent 10× More Capable"). The first half is what runs in the demo today; the second half is a post-hackathon direction, not a shipped feature.

## 1. The pipeline that runs today

Models propose; the host validates, the user approves, the robot's own guards execute. Stage by stage:

| Stage | What happens | Where |
| --- | --- | --- |
| Intent | The user's sentence is classified by host rules (route request, robot task, scene edit). The stop words are always handled deterministically (`immediate_stop`). | `conversation_service.py` |
| Observe | NVIDIA Nemotron 3.5 Super VL on Nebius Token Factory reads a room photo together with the twin's object list and returns candidate objects as strict-schema JSON; the host re-validates every candidate (`checked_photo_candidates`). | `twinpulse_provider/environment_photo.py` |
| Plan | NVIDIA Nemotron 3 Super turns the instruction plus the robot's declared capability list (`observe, move_relative, navigate, survey, return_to_start, stop`) into a short JSON plan. The transport binds a versioned harness profile and an explicit JSON contract to each stage, so a stage can change model without code changes. | `twinpulse_core/robot_task_plan.py`, `twinpulse_provider/harness_profiles.py` |
| Validate | The host checks the plan against the capability list and the step, distance and time limits; at most one repair pass (`max_repairs=1`). Nothing invalid reaches the robot. | `provider_composition.py`, `robot_task_plan.checked_plan` |
| Route | The route is computed on the twin's RoomPlan geometry with keepouts, deterministically: the same twin gives the same route. The route card names the model and shows the measured latency, and waits for the user's Run route. | `declared_route_runner.py` |
| Execute | Finite moves with host re-aim rules (25 cm recovery keepout, re-aim after each leg). Robot-side guards (proximity stop, battery cutoff, output timeout, wheel read-back, Stop) run independently of the app and the model, behind the Arm gate. | `twinpulse_robot_safety/` |
| Sense and update | LiDAR returns the twin cannot explain are reported at every stop; the user (or Auto-apply) adds them as rough boxes with Undo. Each request, operation and move carries a trace ID and a recorded outcome; if the session record cannot be written, the robot refuses to move. | `product_workflow_service.py` |

Built and tested with AI agents: Codex and Claude Code drive the installed app through its visible controls in a develop → operate → observe → diagnose → revise → retest loop, and read the recorded evidence; physical sessions are supervised and separately authorized.

## 2. Three kinds of harness

Today's harness mixes three kinds of parts, and the first task for a stronger model is to separate them:

- **(A) Scaffolding around 2026-model weaknesses.** Regex intent routing; the observer/planner split with a repair pass; flags tied to model names (reasoning effort only for Nano, no-thinking template only for Nano/Lightning); long rule sentences in the planner prompt ("left/right are rotations in radians, never lateral metres").
- **(B) Fixed host rules where the model was not yet trusted.** The host picks survey observation positions (the model only says `survey`); a fixed set of six capabilities; LiDAR clusters become boxes only on the user's Apply, with a fixed 0.3 uncertainty; a declared, tape-measured start pose; host-only re-planning rules.
- **(C) Safety, approval and evidence contracts.** Explicit Run route; model output stops at the JSON plan, finite drive commands only; robot-side guards; distance, time and segment limits and the execution budget; trace IDs, raw responses kept, sensor originals separated from estimates, scene revisions with Undo; data stays local unless approved.

## 3. What a 10× more capable model changes

Delete (A), turn (B) into "the model proposes, the host verifies", keep (C) unchanged.

| # | Today | With a 10× model | Allowed to change when |
| --- | --- | --- | --- |
| 1 | Regex intent routing | The model classifies intent and required capabilities; the host only confirms "robot motion or scene edit". `immediate_stop` stays deterministic. | Equal or better accuracy on the same evaluation set |
| 2 | Six fixed capabilities, plan limits | Limits stay (C). The model may propose new composite capabilities; the host verifies them in sandbox SIM and the user registers them. | The proposed capability passes the SIM set and the user approves |
| 3 | Host picks survey positions | The model proposes observation positions and order from the USD geometry, keepouts and LiDAR blind spots; the host checks reachability, distance and collisions. | Equal or better coverage and safety in SIM |
| 4 | Observer / planner split, repair pass, 17 schemas | One multimodal call reads photo + LiDAR + scene context and returns a verifiable plan; repairs default to zero. | A single-call path matches the two-stage path on the held-out photo set (geometry validity, collisions, user corrections) |
| 5 | Flags keyed on model names | Routing by a measured capability profile (JSON compliance, length stability, image input), not by model ID. | A ModelProfile store and probes exist |
| 6 | Nemotron plan → host-computed route and host re-planning | At re-plan time the model proposes the next move from live LiDAR, odometry and scene; host validation and robot guards stay. | Equal or better completion and safety in SIM; physical use only in a supervised session |
| 7 | "Not in model" → user Apply, box shape, fixed uncertainty | The model proposes what the cluster is, its shape and a confidence from cluster + photo + context; the user still approves. | Proposal accuracy is measured and the user-correction rate is below a threshold |
| 8 | Declared start pose | The model estimates the start pose from the first LiDAR scan against the USD geometry, with uncertainty; the user confirms. | Estimation error at tape-measure level (a few cm, a few degrees) |
| 9 | Long rule sentences in prompts | Schema and capability definitions only. | Contract pass rate unchanged without the sentences |
| 10 | Agent-driven UI tests with human-chosen scenarios | The model runs the evaluation set itself and classifies failure causes; robot motion stays in supervised sessions. | Not a deletion: an extension |

## 4. The deletion procedure (the same every time)

1. Write down the scaffold and the failure it prevented.
2. Keep the existing path; add the simpler candidate path as opt-in.
3. Compare both on the same held-out scenarios, including past failures and ambiguous inputs: geometry validity, collisions, task completion, safety stops, cost, latency, recoverability, on-premises feasibility.
4. If the simpler path wins, make it the default and keep the old path one version for rollback.
5. Unit tests, the model's self-report and an agent's "100% pass" are not evidence. Real UI plus Isaac Sim readings plus, where relevant, physical evidence are.

## 5. Preparation that can start before a stronger model exists

1. Separate (A), (B) and (C) into different modules in `robot_task_plan.py`, `nebius_pipeline.py` and `conversation_service.py`.
2. A held-out evaluation set: about 50 robot instructions (Korean and English, ambiguous ones included), 20 photo-to-scene cases, 10 LiDAR clusters, with a scoring script. The Oct 10-11 and Oct 28 benchmarks are the starting point.
3. A ModelProfile store with measured values per model ID (JSON compliance, length-failure rate, image input, thinking toggle), read by routing instead of names.
4. A minimal capability-registration path: model proposal → SIM verification → user approval, scene authoring first.
5. A re-plan hook in `declared_route_runner.py` with a "host rules / model proposal" switch, host rules by default.

## 6. What we will not do

- Relax user approval, robot guards or budget limits because a model is smarter.
- Auto-deploy model-written code. Proposal → sandbox → review → approval stays.
- Start deleting scaffolds before the hackathon ends. This is a post-hackathon list.

References: master narrative `docs/reference/creator-20261022/TWINPULSE_MASTER_NARRATIVE_CODEX_v0_3_2026-10-22.md` §6, §12; `docs/planning/TWINPULSE_ADAPTIVE_ARCHITECTURE_REVIEW_SOL_PLAN_2026-09-29.md` (A0-A9); `docs/analysis/TWINPULSE_FABLE_DIRECTION_REVIEW_2026-10-25.md`.
