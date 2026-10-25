# Sprint spec — Path B: declared start pose → planned route → proven finite moves

Status: DRAFT for user approval (2026-10-25). Deadline: Devpost 2026-10-31 02:00 KST (checked on the official page 2026-10-25).

## Goal (one demo, one installed build)

In the living room scanned as `Project-2610222326.usd` (SHA-256 `844366fc…4d69b`), the user:

1. imports the RoomPlan environment,
2. places the robot on the Twin at its real start position and heading,
3. asks in chat "survey the room and come back" (or "go to the sofa"),
4. sees the planned route on the Twin,
5. watches SIM and the real TurtleBot3 execute the same move list, with a LiDAR snapshot recorded at each waypoint, and the robot returns to start.

The video must include **at least 1 minute of camera footage of the real robot operating** (Physical AI track rule).

## Honest labels (shown in UI and README)

Start pose is **operator-declared**, not measured. The route is **odometry-based finite moves**, not SLAM/autonomous coverage. LiDAR snapshots are **recorded observations**, not world registration. Scale is from the user's tape measurement once provided.

## Design

```text
declare pose (USD x, y, yaw)  →  plan once (core robot_survey.route_to on RoomPlan geometry + keepouts)
  →  compile to [rotate θ | forward d] list  →  execute one by one through the EXISTING finite 'task' path
  →  stationary LiDAR snapshot at each waypoint  →  reverse list to return, restore start heading
```

- **Reuse what physically worked:** each step is the same finite `task` (`direction` + `amount`) that completed 4/4 on 2026-10-25 (`robot_fleet.py` finite branch → `physical.drive`). No new robot-side executor. Do **not** use `estimated_object_route` (it needs the LiDAR tracker, the fragile part) or the common-task child path (it failed on its admission).
- **No live-map gate in planning.** Planning is not authority. Every step keeps the existing pre-motion admission plus robot-side proximity stop, voltage, output timeout and Stop.
- **No replanning mid-run.** On any stop or rejection, halt and report the completed steps and the remaining steps.
- **Low obstacles the LiDAR cannot see** (clothes, foam board, fan base, cables) are not in RoomPlan. Clear the floor before filming, or draw keepouts on the Twin.

## Tasks (one session each; acceptance must pass before the next task)

| # | Change | Where to start | Accept when |
| --- | --- | --- | --- |
| T1 | Remove the freshness raise from planning `scene()`. Drop tracker samples older than output start in body-progress. Clear `progress` on `reset()`. Thresholds unchanged. | `physical_task_map.py:85-95`, `field_tests.py:425-540` | New unit tests for each change; existing `packages/twinpulse_robot_safety` tests pass |
| T4 | "in-place"/"in place" with room words must route to the robot, not to scene edit | `robot_fleet.py:44-46` | Unit test with the original failing sentence |
| T2 | Declare start pose on the Twin (click + heading), stored with an "operator-declared" label. Reopen shows the pose, never Arm. | environment workspace + Twin view in web UI | Real UI: set, save, reopen; pose visible, robot not armed |
| T3 | Route → move list compiler + sequential runner over the finite path; show route; halt/report on failure; same list in SIM | `twinpulse_core/robot_survey.py`, `robot_task_service.py`, `robot_fleet.py` | SIM in the real App completes waypoints and returns; move list and results saved |
| T5 | Physical: short route, then full route; camera footage of at least 1 min | — | Robot-side completion and Stop receipts for each step; video file |

T1 and T4 are independent and small. T2, T3 and T5 run in that order. Scale check uses the user's tape measurement before T5.

## Token plan (how each task is run)

Reviewed 2026-10-25: a planner-model/executor-model split is **not** the default here. Opus 5.5 is only 2× Sonnet 5.5 per token ($4/$20 vs $2/$10; cache reads $0.20 on both), caches are model-scoped, and every hand-off makes the new agent re-read files. For small, well-located edits, the hand-off costs more than the edit. One model with effort set per task is the baseline; split only where it buys something specific.

| Task type | How | Why |
| --- | --- | --- |
| Small, located edits (T1, T4) | Same session, Opus at **medium**, no plan mode | Diff fits in one sentence per change. A hand-off would re-read the same files |
| Design-heavy (T2, T3) | Plan mode at **high** → user approves a short written plan → fresh session executes at **high** with only the plan | Planning really is separable here. The fresh session drops exploration noise (the useful part of Astra→Sol) |
| Wide search ("where is X used") | Explore subagent returns file:line only | Keeps the main context clean (total tokens are not lower) |
| Review before commit | Fresh subagent with the diff + task row, correctness only | Unanchored second read. This is for quality, not to save tokens |
| Long build/test/Isaac output | Background run, report exit code + tail | Logs are the largest avoidable context cost |

Escalate effort (medium → high → xhigh) only after a real failure, not up front. Judge cost per **completed** task: a cheaper turn that needs a retry is not cheaper.

Rules that save the most tokens here:

1. **Never read the large records.** Baseline, Project Memory, README and progress (~2.6 MB) stay closed. If a fact is needed, `rg` for it and read only the matching lines.
2. **Ranged reads only.** Every brief names `file:start-end`. No whole-file reads of `api.py` (185 KB) or similar.
3. **Quiet commands.** Use `pytest -q path::test` for the touched tests only, and pipe long output through `tail -40`. Run builds, Isaac and installs in the background and report only the exit code and the summary.
4. **One task per executor and a fresh context.** After two failed fixes, stop and re-brief instead of continuing to patch.
5. **UI checks:** read the page as text and take screenshots only at the acceptance moment; batch the clicks.
6. **Records:** one line at the top of Project Memory per finished task; no Baseline bump.
7. **Physical sessions (T5):** the planner prepares a checklist before power-on, and the run reports only receipts and summaries; raw logs stay on disk.

## Decision rights (user-approved 2026-10-25)

Claude decides and proceeds without asking, then reports in the thread:
- implementation plans and design details inside a task row above, including T2/T3 plans (Claude self-reviews the plan before executing);
- code, test and doc edits within these tasks; refactors needed to make them work;
- commits and pushes to `claude/project-thread-l7md32`;
- running unit tests, SIM, the development App and Isaac locally;
- choosing defaults where a task is ambiguous (stated in the report).

Claude asks first (one question, with a recommended option):
- **any physical robot power-on/motion session**, and each new physical route;
- changing a task's goal or acceptance, dropping a task, or switching to the fallback;
- weakening or relaxing any safety guard or threshold;
- installs/system changes (ROS, drivers, WSL, packages beyond the repo), deleting non-generated files, paid cloud use;
- merging to `main`, opening a PR, public release, YouTube/Devpost upload, or anything sent outside the project;
- model/API calls that send the user's photos or USD to an external service.

## Out of scope before submission

Nav2/SLAM, new reconstruction models, the photo-fidelity rework, capability routing, on-prem LLM, automatic GC, and Baseline/README/progress rewrites (one line per task in Project Memory only).

## Fallback (decide on 10/28)

If the physical return is not achieved by the end of 10/28, film at least 1 minute of the already-working finite moves with LiDAR recording, show the full survey/return in SIM, and state the limitation.
