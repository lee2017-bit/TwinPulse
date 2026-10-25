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

## Progress log (newest last; Project Memory has the user's uncommitted v657 edit, so sprint lines live here)

- 2026-10-25 T1: body-progress window bound to output start, new window clears progress keys, bounded wait for an in-window sample; thresholds unchanged (`4eb49bf`, `20982d3`). The `scene()` freshness change was dropped: Path B does not use the common-task child path.
- 2026-10-25 T4: 'in place'/'in-place' no longer routes to scene edit (`204c571`).
- 2026-10-25 T2: no new code. The robot card's existing **Set position** (`set_twin_pose` → `display_pose`, operator estimate, never authority) is the declared start pose.
- 2026-10-25 T3: declared-route planner/runner plus a Run route card, every-Stop cancel and epoch continuity (`e764395`, `20982d3`, `ad1bf78` regex fix). Installed dev build `20261025T075618Z-aae9422ada4e`, Test/CDP, imported RoomPlan Twin, SIM robot at (1.4725, 1.0526, −0.8204): 4 stops / 3.52 m / 11 moves COMPLETED and returned to start (SIM kinematic; return error 0.000 m / 0.0002 rad). Evidence: `outputs/path-b-20261025/sim06/` (sim01–sim05 failures retained: trigger regex bug, scene not rebuilt after restart).
- 2026-10-25 Disk: 470 generated build copies and 6 old installed releases removed with user approval (C: 1.7 → 17.2 GiB free); inventory, script and receipt in `outputs/cleanup-20261025/`.
- Open: route overlay on the Twin, coverage is a local 4-stop loop (not whole room), physical T5 not run.
- 2026-10-25 Coverage + map: stops now spread to the farthest reachable points (6 m budget on the RoomPlan map: 2 stops up to 2.6 m from start; 8 m: 3 stops up to 3.2 m). The Run route card draws a floor minimap (start + heading, numbered stops, path). Installed build `20261025T081916Z-f9bfadbe58ce`: SIM 2 stops / 5.42 m / 13 moves COMPLETED, return error 0.0009 m (`outputs/path-b-20261025/sim07/`).
- 2026-10-25 Physical (T5, user-supervised, robot "Imported existing settings · unverified"): start declared from tape (1.00 m to sofa leather, 3.52 m to window wall; RoomPlan sofa 3.038 m vs measured 3.0 m). Run 1 halted after step 1 (runner read physical completion reason OPERATOR_STOP as Stop; fixed). Run 2 halted at 0.58 m by FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP (LiDAR tracker followed ~25% of odom); user chose explicitly_unverified_supervised for finite commands. Run 3 drove ~2.0 m and stopped 10 cm from the TV wall (pose/heading drift); added the window-corner obstacle and a 35 cm physical clearance. Run 4: 2.3 m straight OK, next step unacknowledged (sent instantly); added 1.5 s settle + 10 s ack stop. Run 5 (build `20261025T101242Z-b5c3f0314ffe`): 2.99 m of the 3.02 m first leg, then FIELD_PROXIMITY_10CM 4 cm short of stop 1 (object under the window). The remaining route was completed as 12 typed finite commands in the app (back 15 cm, then the planned turns/legs): all COMPLETED, odometry end 0.15 m from the start. Body motion unverified (odometry only); evidence `outputs/path-b-20261025/phys01..05/` and the operation journals.
- 2026-10-25 After the physical analysis (`docs/analysis/TWINPULSE_PATH_B_PHYSICAL_RUNS_2026-10-25.md`): runner now follows route vertices on measured odometry (re-aims every step; cancels the ~4 deg/m left curve in tests), recovers from FIELD_PROXIMITY_10CM by backing off 25 cm and re-planning around a point keepout (max 2), and survey stops keep >= 0.6 m from walls/obstacles. Plant mat re-added as a 0.95 x 0.85 m obstacle (+0.1 m). Installed build `20261025T104703Z-8a9c216cec5c`: SIM journey PASS (3 stops, 13 moves, return 0.5 mm) in `outputs/path-b-20261025/sim08/`. Physical retest pending a charged battery.
- 2026-10-25 Obstacles before the run (user-approved photo transmission): start-LiDAR keepouts installed (build `20261025T110224Z-25d151a1e4fc`); added from photos + the run-5 start scan: floor fan base (TV wall) and laundry basket + bags (window right). The app's photo observer (DeepSeek-V4.1-Flash) on IMG_7150/IMG_7158 proposed bag/basket (duplicates), a cable run along the TV wall (added as a 2.0 x 0.2 m keepout) and a "small wheeled device" that is the TurtleBot itself (rejected). Evidence `outputs/path-b-20261025/photo01..02`, `obstacle3..5`.
- 2026-10-25 Physical retest (T5, user-supervised, build `20261025T120155Z-cb02064b5674`, declared start 0.681/0.206/0.4887): "Survey the room and come back" → Run route **completed automatically**: 4 stops / 6.42 m plan, 33 finite commands (15 planned moves + odometry re-aims) all COMPLETED, 0 proximity stops, ALL_STOPS_AND_RETURN_COMPLETED in 6.5 min; odometry end 1.5 cm / −1.1° from start; 5 waypoint LiDAR scans hashed. Odometry only; user tape at the end: 14 cm left and 5 cm forward of the start mark (odometry said 1.5 cm). Not yet shown: route overlay on the USD Twin, live robot/LiDAR in Isaac, LiDAR-based object update. First launch lost its window to ENOSPC before Prepare (no motion; 9.19 GB of old build copies removed, `outputs/cleanup-20261025b/`). UI wording bug: card says "33 of 15 moves". Evidence `outputs/path-b-20261025/phys06b/`.
