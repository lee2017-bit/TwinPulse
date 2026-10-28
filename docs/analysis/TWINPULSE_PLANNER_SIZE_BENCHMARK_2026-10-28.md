<!-- SPDX-FileCopyrightText: 2026 Jaewon Lee -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
# Planner size benchmark on the robot-plan request (2026-10-28)

**Question.** TwinPulse's robot mission planner is `nvidia/nemotron-3-super-120b-a12b`. The choice was made after the Oct 9–11 scene-design trials, where Nano produced cut-off JSON and runaway whitespace and Super matched Ultra at about a quarter of the cost (one trial each). Those trials were on the long scene-design request, not on the short robot-plan request. Does the size matter for the robot-plan request itself?

**Method.** `scripts/benchmark_planner_sizes.py` sends the installed app's planning request for a robot mission: the planner instruction from `robot_task_planner.py`, the capability-restricted schema from `twinpulse_core.robot_task_plan.plan_schema`, `response_format: json_schema` (strict), temperature 0, the app's planner output cap (40,000). Not reproduced (found on review after the run): two lines the app's transport appends to the system prompt, the guidance text of the harness profile bound to the planner stage when the route was saved (`harness_profiles.apply_profile`; on the PC that ran the demo it is a locally edited profile, `acceptance-nemotron-final15` revision 5: the built-in planning text plus one appended Korean sentence asking the model to mark unmeasured dimensions as estimates and not to invent unknown information) and a compact copy of the schema (`explicit_json_contract`), and the saved routing's thinking-mode flag, if set. Every answer is validated with `checked_plan()`, the function the app uses, so "valid" means the app would have executed the plan. Three prompts (`demo_survey` = "Survey the room and come back", `explicit_moves`, `inspect`), 5 trials each, 4 sizes, sequential: 60 live calls to Nebius Token Factory on 2026-10-28 about 22:30–22:45 UTC from the PC (`outputs\bench-planner-20261029\calls.jsonl`). All 60 returned HTTP 200; no 402 or 504.

Models present on the account (`--discover`): `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3_5-Lightning`, `nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3-Ultra-550b-a55b` (and `nvidia/Nemotron-3.5-Super-VL`, vision, not a planner candidate).

## Results

| Model | Prompt | Valid | Latency s min / median / max | Completion tokens median | Reasoning tokens median | Failure codes |
| --- | --- | --- | --- | --- | --- | --- |
| Nemotron-3-Nano-30B-A3B | demo_survey | 5/5 | 4.2 / 5.8 / 7.0 | 519 | - | - |
| Nemotron-3-Nano-30B-A3B | explicit_moves | 5/5 | 4.1 / 6.1 / 9.4 | 491 | - | - |
| Nemotron-3-Nano-30B-A3B | inspect | 5/5 | 2.6 / 4.7 / 6.7 | 341 | - | - |
| Nemotron-3-Ultra-550b-a55b | demo_survey | 5/5 | 2.6 / 4.4 / 9.4 | 1008 | 853 | - |
| Nemotron-3-Ultra-550b-a55b | explicit_moves | 5/5 | 2.3 / 2.8 / 2.9 | 613 | 416 | - |
| Nemotron-3-Ultra-550b-a55b | inspect | 5/5 | 3.2 / 4.1 / 4.7 | 1024 | 908 | - |
| Nemotron-3_5-Lightning | demo_survey | 4/5 | 10.8 / 11.7 / 30.1 | 2956 | 2858 | ROBOT_TASK_CLARIFY_HAS_ACTIONS |
| Nemotron-3_5-Lightning | explicit_moves | 5/5 | 7.5 / 9.4 / 14.5 | 2659 | 2449 | - |
| Nemotron-3_5-Lightning | inspect | 4/5 | 6.8 / 9.6 / 32.0 | 2593 | 2495 | ROBOT_TASK_CLARIFY_HAS_ACTIONS |
| nemotron-3-super-120b-a12b | demo_survey | 5/5 | 2.5 / 5.0 / 5.9 | 305 | 205 | - |
| nemotron-3-super-120b-a12b | explicit_moves | 5/5 | 2.9 / 5.3 / 6.8 | 448 | 295 | - |
| nemotron-3-super-120b-a12b | inspect | 5/5 | 3.2 / 3.8 / 5.6 | 330 | 237 | - |

Per size over 15 calls:

| Size | Valid | Latency s min / median / max | Completion tokens median | of which reasoning |
| --- | --- | --- | --- | --- |
| Nano 30B-A3B | 15/15 | 2.6 / 5.1 / 9.4 | 491 | none reported |
| Super 120B-A12B | 15/15 | 2.5 / 4.8 / 6.8 | 385 | 237 |
| Ultra 550B-A55B | 15/15 | 2.3 / 3.7 / 9.4 | 905 | 753 |
| 3.5 Lightning | 13/15 | 6.8 / 11.6 / 32.0 | 2956 | 2789 |

Lightning's two failures were `ROBOT_TASK_CLARIFY_HAS_ACTIONS`: the answer set `mode: clarify` but still listed steps, which the validator rejects.

List prices on Token Factory (third-party listing, read 2026-10-20, USD per million input / output tokens): Nano 0.06 / 0.24, Lightning 0.06 / 0.24, Super 0.30 / 0.90, Ultra 1.00 / 3.00.

## Reading

- For this narrow, schema-bound request, size barely matters: three of four sizes returned 15 of 15 valid plans. The schema and the capability list carry the result.
- Nano would do for the robot planner alone. Super is kept because the same model is the scene-design planner (one model to validate across roles) and its latency and token use are close to Nano's.
- Ultra is the fastest by median but writes 2.3x Super's output tokens at over 3x the list price.
- Lightning spends about 2,800 hidden reasoning tokens per call, is 2–3x slower, and twice answered "clarify" with steps.
- This is 15 calls per size on three prompts, not a general benchmark.

Reproduce: `python scripts/benchmark_planner_sizes.py --repo . --discover`, then `--trials 5 --out outputs\bench-planner-<date> --models <ids>` (needs the Token Factory key; see the script docstring).
