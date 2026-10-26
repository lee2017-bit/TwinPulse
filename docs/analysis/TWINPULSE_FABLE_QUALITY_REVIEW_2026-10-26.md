# TwinPulse quality review (Fable, read-only pass) — 2026-10-26

Scope: web UI (`apps/twinpulse-web/src`), backend (`packages/twinpulse_app`), core `declared_route.py`, Isaac route overlay (`scripts/twinpulse_fleet_runtime.py`). Three parallel read-only reviews plus a direct read of the declared-route runner and chat route flow. No tests run, no app launched for this pass. Line numbers refer to the tree at `05017ce`. Items marked **fixed** were repaired in the follow-up commits on `claude/project-thread-l7md32` (see Project Memory lines dated 2026-10-26).

Priority for the 2026-10-26 morning physical demo: the replan story (box on leg 1 → LiDAR "not in model" → Add to Twin → ask again → different route) and anything that makes the route look hung or wrongly counted. General UI polish comes after.

## Critical / high

| # | Severity | Where | Defect | User impact | Fix | Effort |
|---|---|---|---|---|---|---|
| 1 | critical | `declared_route_runner.py:126-130,163-172,318-320`; `start():115-118` | `_save()` (route record) is not guarded. On ENOSPC: in `start()` the record is set RUNNING and then the save raises → thread never starts, `active()` stays True forever → every later route is refused with `declared_route_active`. In `_finish()` the save raises inside the outer `except`, thread dies, `on_result` never fires → no finish message, phantom RUNNING. `_stop()` only catches BrokerError. | After the disk fills once (happened twice on 10/25) the route feature is dead until App restart, with no message. | Guard all saves; on failure in `start` roll back `current`; in `_finish` keep memory state, note `save_error`, still notify; catch Exception in `_stop`. **fixed** | S |
| 2 | high | `declared_route_runner.py:301-309`, `conversation_service.py:1082` | After a proximity recovery skips a stop, leg indices restart at `reached+i`, so the return leg gets an index `< len(waypoints)` and is counted as a stop ("reached 3 of 3 stops" with one skipped); Isaac colours the wrong rings (`twinpulse_fleet_runtime.py:580-581` uses `i<reached`). | Wrong result on the exact demo (box on leg 1). | Carry the original waypoint index per queue entry; report `reached_stops`/`skipped_stops`; Isaac colours by the list. **fixed** | S |
| 3 | high | `robot_fleet.py:845-853` | Physical ghost/`twin_tracking` take `route['pose']` whenever revision+epoch match, without checking the route is RUNNING. After the route the ghost freezes at the last route pose while the UI says `ESTIMATED`. | Misleading position during manual driving after a route. | Use the route pose only while `state=='RUNNING'`. **fixed** | S |
| 4 | high | `ChatWorkspace.tsx:414-421`, `App.tsx:86` | If the first `bootstrap()` fails (slow backend at launch) the chat never connects and Exit stays disabled; no retry. | Permanent "disconnected" until reload. | Retry bootstrap inside the poll while not authenticated. **fixed** | S |
| 5 | high | `ChatWorkspace.tsx:537-542,1040` | Enter in the composer bypasses the Send button gates (pending card, active job, edit lock). | Server error or silently queued message. | Share one `sendDisabled` for Enter and the button. **fixed** | S |
| 6 | high (UX) | whole UI | A running declared route has no UI state: no component reads route state; Current step shows an idle message (`ChatWorkspace.tsx:655-685`), robot card says ACCEPTED forever (`RobotFleet.tsx:444,456`), details say "No active motion task". Progress is only chat text at finish. | Judge reads "nothing is happening / hung" during a 6-minute run. | Backend: route summary on the fleet snapshot + per-stop chat messages; UI: route progress card (state, stop n/N, moves, reason, Stop). **fixed** | M |
| 7 | high (UX) | `ChatWorkspace.tsx:719` | After a RoomPlan import the SIM card is one sentence; the real path (Robots → Manage → Add SIM robot → Connect → Prepare → chat) is not shown. | First-time user cannot find how to run anything. | Checklist text with the exact steps. **fixed (text)** | S |
| 8 | high | `RobotFleet.tsx:441-459` | Task text from the robot card ignores `accepted_request_ids`; a network error shows FAILED so the user resends → double route; a chat-routed task says ACCEPTED forever. | Second route attempt. | Receipt says "SENT TO CHAT" / "DELIVERY UNKNOWN · check chat before sending again". **fixed** | S |
| 9 | high | `fleet_recorder.py:151-152` + `robot_fleet.py:230-234,319-321` | Snapshot-writer error is sticky for the session (one ENOSPC or queue overflow). All SIM robots are re-paused on every drive; `_persist` raises on register/focus/set-pose. | SIM fleet unusable until restart even after freeing disk. | Per-write failure record; a later successful write clears the fault; the session receipt still reports the loss. **fixed** | M |

## Medium

| # | Where | Defect / gap | Fix | Effort |
|---|---|---|---|---|
| 10 | `conversation_service.py:1073` | "Route started: N finite moves" uses the nominal preview; re-aims make the real count larger (the 10/25 "33 of 15" confusion). | Word as "about N planned moves; re-aims may add more". **fixed** | S |
| 11 | `declared_route_runner.py:87-89` | Scan review runs outside the `try`; a malformed LiDAR row raises out of `plan()` as a 500. | Wrap in the same try. **fixed** | S |
| 12 | `declared_route_runner.py:258,265` | `_measured()` ValueError (pose lost) ends as `RUNNER_ERROR:ValueError`. | Report `ROUTE_POSE_UNAVAILABLE`. **fixed** | S |
| 13 | `robot_fleet.py:487,506-510` | `focus`/`set_twin_pose` persist after mutating state; OSError skips effects / anchor reset. | Catch OSError → BrokerError, pop anchors first. | S |
| 14 | `robot_fleet.py:916-939` | `close()` does not cancel a running declared route; a failing retire loop skips `snapshot_writer.close()` → project reopen blocked. | Cancel route first; `finally` close. **fixed (cancel + finally)** | S |
| 15 | `twinpulse_fleet_runtime.py:546-551` | `route_key` is set before drawing (a mid-draw exception freezes a partial overlay); trace redraw key uses `len(trace)` so it freezes at the 800 cap; `route_error` never reported. | Set key after draw; include a revision. **fixed (key after draw, revision)** | S |
| 16 | `ChatWorkspace.tsx:873,141,169` | Cards say "Submitting your choice…" while merely disconnected / stale. | Separate `busy` and `locked`. **fixed** | S |
| 17 | `SimulationRunCard.tsx:303-306` | Failed Stop keeps "waiting for the engine acknowledgement…". | Set phase in catch. **fixed** | S |
| 18 | `ChatWorkspace.tsx:270-281` | Fleet-stale banner flickers when a fleet GET takes >500 ms. | Show after two missed periods. | S |
| 19 | `EnvironmentImport.tsx:69,121-128` | One network error locks the import panel until reopen. | Clear `unknown` on a clean refresh. | S |
| 20 | `declared_route.py:203-212` | `cluster_candidates` can merge a wall arc into one candidate (radius clamped to .6, centroid in free space); one noisy stop satisfies `min_returns`. | Cap component extent; prefer support from 2 stops. | S/M |
| 21 | `RobotFleet.tsx:383-386` | "Add SIM robot" hidden behind Manage → details when no robots exist. | Show the form directly when the fleet is empty. **fixed** | S |
| 22 | `TwinViewport.tsx:579-580` | Empty viewport tells the user to "Build the scene in Isaac"; no such button. | "Select View current Twin in chat". **fixed** | S |
| 23 | `robot_fleet.py:879-881` | Whole overlay (trace 800 pts + all scans) resent at ~20 Hz. | Full overlay on revision change or every 2 s, stub otherwise; Kit ignores the stub. **fixed** | M |
| 25 | `EnvironmentImport.tsx:120,149`, `ChatWorkspace.tsx:719` | After an App restart the imported Twin is not rebuilt in Isaac when the project is reopened; the only path is Import space → Check saved import → Show Twin, which nothing in the chat points to (seen again in the 2026-10-26 installed SIM check). | "Rebuild Twin in Isaac" button in the imported-space checklist (same Build action). **fixed** | M |
| 26 | `declared_route_runner.py:plan()` vs `scripts/twinpulse_fleet_runtime.py:44-70` | SIM-only: the engine stops for other connected SIM robots standing on the floor, but the planner never knew about them. Installed checks 2026-10-26 (`outputs/path-b-20261026/sim14`, `sim15`): routes reached their stops and then hit `OBSTACLE_STOP` exactly where an earlier SIM robot (PathB SIM 01 at 0.60, −0.11) was parked. | Other connected SIM robots become 0.35 m keepout discs in a SIM plan (shown as red rings). **fixed**; the guard is untouched. | S |
| 27 | `bounded_grid_plan.py:142` + runner recovery | **Physical run 2 (phys08):** after a proximity stop the robot backs off 25 cm, so it sits inside keepout radius .25 + physical clearance .37 and the replan fails with `START_OR_GOAL_BLOCKED`. SIM never hit it (clearance .2). | Escape corridor: within one clearance of the start a keepout disc blocks only its own radius; walls/boxes/unknown cells keep the full berth. **fixed** | S |
| 28 | `declared_route.py next_move/heading_move`, `fleet_control.py:776` | **Physical run 3:** a 175.7° re-aim turn exceeded the robot-side deadline (amount/0.2 rad/s + 2 s) → `TASK_DEADLINE`. | Cap turns at 1.6 rad (preview and runner); the rest is re-aimed next step. **fixed** | S |
| 29 | runner `_run` heading tolerance | **Physical run 4:** ±2° turn overshoot against the 2° tolerance produced left/right ping-pong (14.07 → 2.15 → 2.59 → 2.55 → 2.18°) and burned battery. | Hysteresis: after a re-aim turn accept 0.07 rad before turning again. **fixed** | S |
| 30 | runner `plan()` / chat card | **Physical run 1:** Run route before Arm + Bootstrap stop → first step never acknowledged (`STEP_NOT_ACKNOWLEDGED`); nothing told the user the field session could not drive. | Refuse to plan while `capabilities.drive` is false, naming the blockers and the two steps. **fixed** | S |
| 31 | `declared_route.py cluster_candidates` | A ~30 cm box 1 m from a stop gave only 2 unexplained returns at the stop (190 points, agreement .976) → no candidate (min 3). | Start-scan returns (plan-time keepouts) seed the candidate clusters; the 3-return rule is unchanged. **fixed** | S |
| 24 | `robot_fleet.py:584-586,399-400` | Failed SIM connect leaves RECORDING badge while DISCONNECTED; `_begin` OSError → generic 500. | Reset recording_state; typed 507. | S |

## Low / ideas

- `ChatWorkspace.tsx:161-169`: every card needs radio + Continue; one-click buttons for 2-choice cards (S).
- `ChatWorkspace.tsx:1044-1051`: no reason shown when Send is disabled (S).
- `ChatWorkspace.tsx:799-808,1028`: same error shown up to three times (S).
- `SimulationRunCard.tsx:139` raw "Error:" prefix; `:126,270` say "Run simulation" while the button reads "Run" (S).
- `TwinViewport.tsx:474` 100 ms re-render of the whole component (S).
- `declared_route.py:230-234`: 4–10 cm overshoot produces a near-π turn + 4 cm step (S).
- `declared_route.py:167-169`: lateral sign reported as 1 even when `used=False` (S).
- `declared_route_runner.py:60-61`: full `fleet.snapshot()` (saved-profile disk reads) every 250 ms; a transient exception fails the route (S).
- `fleet_recorder.py:140-141`, runner `_save`: temp files leak on ENOSPC (S).
- `api.py:1649`: missing route record → generic 500 (S). **fixed**
- Not found: a product screen recorder. The 10/25 ENOSPC crash came from a demo recording script, not the shipped app; the morning checklist asks for a disk-space check before recording.

## Demo-flow verification added

`tests/integration/test_declared_route.py` gained: disk-full in `start()`/`_finish()` leaves no phantom RUNNING route and still notifies; recovery with a skipped stop reports the right stop numbers; a box on leg 1 seen by a fake LiDAR becomes one candidate, "Add to Twin" obstacles feed `plan_survey`, and the second plan avoids the box.
