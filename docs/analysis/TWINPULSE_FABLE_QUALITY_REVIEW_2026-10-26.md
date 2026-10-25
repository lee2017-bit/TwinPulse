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
| 8 | high | `RobotFleet.tsx:441-459` | Task text from the robot card ignores `accepted_request_ids`; a network error shows FAILED so the user resends → double route. | Second route attempt. | Show "Delivery unknown · check chat". | S |
| 9 | high | `fleet_recorder.py:151-152` + `robot_fleet.py:230-234,319-321` | Snapshot-writer error is sticky for the session (one ENOSPC or queue overflow). All SIM robots are re-paused on every drive; `_persist` raises on register/focus/set-pose. | SIM fleet unusable until restart even after freeing disk. | Per-write failure + explicit retry. | M (not done; restart is the documented workaround) |

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
| 23 | `robot_fleet.py:879-881` | Whole overlay (trace 800 pts + all scans) resent at ~20 Hz. | Revision + send on change. | M |
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
