# T3 plan — declared-pose route runner (self-approved under the sprint decision rights, 2026-10-25)

## Findings that change the spec

- **T2 already exists.** The robot card's "Set position" / "Estimated Twin marker" (`robot_fleet.py` action `set_twin_pose`) stores an operator X/Y/yaw as `display_pose` (`source=operator_estimate_not_localized`, `frame_id=isaac_world`, bound to the current scene revision). It persists, is labelled as not localized, and grants no motion authority. T2 is reduced to verifying it in the real UI. Click-to-place is optional polish.
- Imported RoomPlan scenes reach the fleet as `navigation_scene` (`scene-navigation-2.0`: bounds, obstacles, targets, floor-mask grid → `observed_cells`) in the same `isaac_world` XY frame.
- The common task child path (`robot_task_service` with `task_token`) re-checks a pinned LiDAR ring at every child admission (`PINNED_RING_EXPIRED`, `_geometry` age check). That is the path that failed on 2026-10-25, so the runner does **not** use it. The `scene()` freshness change from T1 is dropped because Path B does not use that path either.

## Design

1. `twinpulse_core/declared_route.py` (pure):
   - `plan_survey(start, geometry, observed_cells, kind, budget_m)`: repeats `robot_survey.next_observation` from a simulated pose (with return reserved), then appends `route_to(start)`. Returns waypoints, polyline and `scope=DECLARED_START_MODEL_PLAN_NOT_LOCALIZED`.
   - `compile_moves(start, polyline, final_yaw)`: produces `left/right θ` and `forward d` steps, with legs of at most 1.0 m (1 m forward was proven on 2026-10-25), turns under 0.02 rad skipped, and a final heading restore.
   - `move_text(step)` produces the exact text the existing parser accepts.
2. `twinpulse_app/declared_route_runner.py`: a background thread per run.
   - **Start pose:** SIM uses the engine pose. Physical uses `display_pose`, which must match the current scene revision, and the robot must be stopped.
   - **Execution:** sends each step as an ordinary `action='command'` with text through `RobotFleet.action` (the same path as the UI finite command, with no task token). It waits for that `request_id`'s `command.state` and halts on anything other than `COMPLETED`, on an epoch change (Stop) or on a timeout.
   - **At each waypoint:** records the latest scan identity if LiDAR is streaming.
   - **Record:** writes the plan and the result JSON under the project folder.
3. **Chat:** for "survey/explore … return" requests with a focused robot and an imported scene available, conversation routes to the runner, replies with the plan summary, and posts the result. The existing common-task path stays for other phrasings.
4. **UI:** the existing plan/route display is reused if cheap. Otherwise the result is listed as chat text (waypoints and the step list).

## Acceptance

- Unit: planner returns a closed route on a synthetic room with an obstacle; compiled moves reproduce the polyline within 1 mm/0.001 rad when integrated; texts parse back to the same steps with `parse_robot_command`.
- Unit: the runner halts on FAILED, on an epoch change and on a timeout, and never sends the next step after a Stop.
- SIM in the real App: import the RoomPlan USD, register a SIM robot at the declared pose, chat "survey the room and come back", and the robot visits the waypoints and returns. The plan and result files are saved.

## Not done here

Re-planning, obstacle-aware detours, LiDAR scan-matching correction, and the physical run (T5 needs the user's go-ahead).
