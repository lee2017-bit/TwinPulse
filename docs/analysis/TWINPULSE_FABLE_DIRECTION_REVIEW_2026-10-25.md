# Independent direction review (Fable, read-only) — 2026-10-25

Input: original goal/context docs, SPRINT_PATH_B_SPEC, physical runs 1–5, phys06b result, and the user's critique after phys06b (stop order not visible, route only on a chat minimap, robot/LiDAR not shown in Isaac, no LiDAR-based object update). File:line citations are the reviewer's and were not re-checked.

## (a) Path B kept half of the original goal and explicitly dropped the half the user pointed at

**Original goal**
- `docs/handoff/2026-10-25/TWINPULSE_CLAUDE_PROJECT_CONTEXT_2026-10-25.md:9` — a Twin matching the real environment, "verified by simulation and field observation"; `:86-90` room loop = sensor collection from several positions; appendix `:396` "LiDAR-assisted physical alignment: use sensor observations to improve or check … obstacle position and real/sim consistency".
- `TWINPULSE_ROOMPLAN_LIDAR_DEMO_REVIEW_2026-10-24.md:103-111` — shortest submission path: missing object from photo → reviewable overlap/mismatch of real scan vs mesh section → obstacle layer candidate → explicit Review/Apply → Isaac ACK → replan.
- `TWINPULSE_ENVIRONMENT_TASK_LOOP_2026-10-25.md:28` already records the same complaint: no world registration, so no body/points on the USD, only the sensor-local panel.

**What Path B dropped**
- `SPRINT_PATH_B_SPEC.md:13,19,32`: LiDAR reduced to "recorded snapshots, not world registration"; low obstacles handled by hand-drawn keepouts. `:12` "sees the planned route on the Twin" was implemented only as a chat-card SVG (`conversation_service.py:1025-1035`, `ChatWorkspace.tsx:113-127`).
- The runner stores only scan SHA + odometry pose per stop (`declared_route_runner.py:218-222`). The only LiDAR→Twin link is the one-off start scan turned into planning keepout discs (`:76-85`, core `declared_route.py:143-180`), drawn only on the minimap.
- Isaac does show a physical Burger ghost (`robot_fleet.py:843-869` → `twinpulse_fleet_runtime.py:390,433-437`), but its pose source is the LiDAR relative tracker, judged unusable on 10/25 (`TWINPULSE_PATH_B_PHYSICAL_RUNS_2026-10-25.md:35`). The odometry pose the runner actually uses (`plan_pose`) is not wired to the Twin display — the direct reason the Twin looked unused (inferred).
- Web viewport hardcodes "room projection unavailable" for physical robots (`TwinViewport.tsx:589`); Isaac runtime excludes scans of `visual_only` rows (`twinpulse_fleet_runtime.py:115,139`).

**Conclusion:** Path B was right for reliability and phys06b achieved that (33/33 COMPLETED, 0 proximity stops). The demo's core message (real LiDAR → Twin update, robot/route on the Twin) was deliberately excluded and is where the remaining 5 days should go. Not a direction change: add a "display + reflect" layer on top of Path B. More autonomy/accuracy work (SLAM, the 14 cm return error) has low value now.

## (b) Minimal demo story feasible in 5 days

RoomPlan Twin with declared start → "Survey the room and come back" → numbered route drawn in Isaac → during the real run the Isaac Burger ghost follows odometry and leaves a trace, and real LiDAR points at each stop are projected onto the Twin floor (label: declared pose + odometry, not localized) → the finish card lists "stops 1–4 reached + N return clusters not in the model" → user clicks "Add to Twin" → unknown obstacle created through the existing Added-obstacles transaction (Isaac ACK, Undo) → same sentence again → replanned route around it drawn on the Twin (SIM run is enough).

Reusable code: `_scan_world` / `plan_pose` (`declared_route.py:136-141,183-188`), `unexplained_scan_discs` (`:143-180`), stop poses already in `waypoint_scans`; USD curve/point patterns in `extensions/.../bedroom_preview.py:32-41,277-298`; physical ghost via `robot_fleet.py:843-869`; obstacle insertion via `environment_overlays.py:115 add_overlay` + `checked_overlay` (kind `unknown` allowed). Blocker: evidence basis only allows `manual_estimate`/`photo_estimate` (`:35`) → add `lidar_estimate` bound to the scan sha256; `checked_overlay_floor` may reject wall-adjacent clusters as `OUTSIDE_FLOOR`.

## (c) Ranked tasks

| # | Task | Effort | Main risk |
|---|---|---|---|
| 1 | Drive the physical ghost from runner odometry (`odometry_in_declared_frame`) + trace | 0.5 d | lock/epoch race between runner and fleet snapshot |
| 2 | Draw the route in Isaac (BasisCurves + stop points, colour on reach) | 0.5–1 d | Kit-thread exception stopping the fleet; isolate and clean prims |
| 3 | Project per-stop LiDAR points into the Twin (`/World/TwinPulse/Fleet/Route_<id>/Scan_k`) | 1 d | odometry drift makes wall points float 10–30 cm; label honestly, cap ~400 pts/stop |
| 4 | "Not in model" cluster card + Add to Twin (`lidar_estimate`, uncertainty 0.3, user Apply only) | 1.5 d | evidence enum change ripples; false positives from pose error |
| 5 | SIM replan around the new obstacle | 0.5 d | navigation scene rebuild timing |
| 6 | Fix "33 of 15 moves" wording + per-stop reached messages | 0.25 d | none |
| 7 | One final physical filming run (≥12.3 V, camera + screen recording) | 0.5 d | no battery/time for a retake; validate 3–4 in SIM first |

Suggested schedule: 10/26 #1 #2 #6; 10/27 #3 #4 core; 10/28 #4 UI + #5 + dry run; 10/29 physical filming; 10/30 edit/labels/submit. If #4 is not done by 10/28 evening, freeze at #3 and use the already-accepted photo obstacle path for "add obstacle".

## (d) Cut

Return-accuracy work, left-curve correction, LiDAR relative tracker repair, world registration retries, SLAM/Nav2; whole-room coverage, more stops, more physical runs; Baseline/README rewrites, new gate scripts, new photo-model calls; reusing the AlignmentView packet under a "geometric review" label.

Labels (unchanged): every new display is `declared start + wheel odometry, not localized`; obstacles `lidar_estimate, alignment_verified=false`; Apply is a user click. No guard or motion authority is touched.
