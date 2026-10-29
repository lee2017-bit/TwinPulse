# Repeatability runs — analysis (2026-10-28)

Scope: the same mission, "Survey the room and come back", repeated on the physical TurtleBot3 Burger in the living room with build 61 (`20261027T233111Z-059aab92576d`) and twin edits set to **Review**. The sources are the app's own run records on the operator PC (`outputs/repeat-20261028/`, local only, like the other physical outputs), the plan and route cards shown in the app, and the operator's tape measurements and photos. Distances driven are wheel odometry unless stated; return errors and object positions are tape-measured.

## 1. Result in one line

4 mission attempts plus 1 guard-stop retry: 3 completed, 1 reached all 4 stops and the start but had its final heading turn refused by the fail-closed recording-budget guard (the 74-minute session hit its 768 MiB recording budget), and 1 was stopped by a robot-side guard at the third move with no contact. Nemotron returned a valid plan 5 times out of 5, the route on the twin was identical every time, LiDAR found the box and the stool in every run and missed a soft bag in every run, and the robot came back 4.5–29 cm to the left of its mark while the app's own estimate said it was within 2 cm.

## 2. Setup

- Robot: TurtleBot3 Burger, living room, declared start pose X 0.681 Y 0.206 yaw 0.489 (tape mark on the floor). Before every attempt the operator put the robot back on the mark, and afterwards measured the return error against the mark with a tape.
- App: build 61, new chat, twin edits = **Review**. Every LiDAR candidate was shown to the operator and skipped, so the twin was the same in every run. Control view.
- Command: "Survey the room and come back", typed in the chat each time → Nemotron (`nvidia/nemotron-3-super-120b-a12b` via Nebius Token Factory) picks the task steps → the deterministic planner (`declared_route.plan_survey`) places 4 stops and the return leg on the twin's free floor → **Run route**.
- Placed objects (tape, from the start pose; the objects have volume, so about ±5–10 cm): A cardboard box 1.0 m ahead, 0.7 m right ≈ twin (1.89, 0.06); B stool 2.1 m ahead, 0.2 m right ≈ (2.63, 1.02); C soft bag 1.2 m ahead, 0.9 m left ≈ (1.32, 1.56). Objects that were already in the room and not in the twin (robot vacuum and its dock, plant pot and basket by the window, cables by the sofa) are counted as reference objects, not false positives.
- Photo step (before run 2): one photo of the initial room → Nemotron VL (`nvidia/Nemotron-3.5-Super-VL`), one call → 5 candidates. 2 floor obstacles accepted (cable beside the sofa at (1.16, −1.28), bag behind the sofa at (4.12, 0.30)), 3 skipped (box under the sofa, wall cable, wall adapter). Both accepted objects are more than 1.5 m from the first leg and did not change the route.

## 3. Runs

| Attempt | UTC | Plan latency | Plan steps | Stops | Route planned / driven | Moves | Return error (tape: along / across / heading) | A box | B stool | C bag | Other candidates | Battery | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 15:52–15:59 | 5.1 s | observe → survey → return_to_start → stop | 4/4 | 6.22 / 6.3 m | 23 | 3.5 cm forward / 4.5 cm left / not recorded | 12 cm | 26 cm | missed | 4 (reference objects) | 12.30 → 12.13 V | Before the photo step |
| 2 | 16:16–16:23 | 5.6 s | observe → survey → return_to_start → stop | 4/4 | 6.22 / 6.3 m | 23 | 0 / 23.5 cm left / about 5° CW | 16 cm | 38 cm | missed | 4 | 12.13 → 11.69 V | Twin with the 2 photo objects |
| 3 | 16:26–16:32 | 4.5 s | survey → return_to_start → stop | 4/4 | 6.22 / 6.3 m | 21 | 1 cm back / 29 cm left / about 15° CW | 17 cm | 41 cm | missed | 4 | 11.67 → 11.62 V | |
| 4-1 | 16:41–16:42 | 4.5 s | survey → return_to_start → stop | 0/4 | 6.22 / — | 3 | — (guard stop) | — | — | — | 2 (partial card) | 11.51 → 11.49 V | Robot-side guard `ENABLE_READBACK_OR_UNEXPECTED_MOVEMENT` at the third move (encoder moved more than 2 ticks within 60 ms of enabling torque, or the readback failed). No collision or contact (operator). The app does not retry on its own. |
| 4-2 | 16:54–17:01 | 8.9 s | survey → return_to_start → stop | 4/4 | 6.22 / about 6.3 m | 21 | 7 cm forward / 23 cm left / about 150° (alignment turn refused) | 7 cm | 24 cm | missed | 4 | 11.40 → 11.30 V | All 4 stops and the return to the start position completed; the final heading-alignment turn was refused with `physical_recording_incomplete` → Route failed. Cause: the 74-minute session hit its 768 MiB recording budget (`EVENT_ARCHIVE_BYTES` in `robot_control_timing.py`, enforced on both sides). The PC-side evidence log reached the budget first at about 17:00:52Z (413,955 events since the 15:47Z connection, with LiDAR streaming) and errored `STREAM_RECORDING_CAPACITY`; the robot journal then reported `SESSION_LOG_BYTE_BUDGET` and the robot exited the session, so it stopped accepting motion (fail-closed, as designed). The PC's C: drive was also nearly full at the same time (screen-recording frames), a separate and coincident problem. |

Object columns: distance between the centre of the LiDAR candidate in the twin and the tape position (the tape position itself is about ±5–10 cm).

## 4. Aggregates

- **Mission completion:** 3 completed (1, 2, 3), 1 partial (4-2: 4/4 stops and back at the start position, only the final heading alignment refused), 1 guard stop (4-1). Stops reached 16/20 (16/16 excluding the guard stop). Proximity stops and replans: 0 (nothing was on the route).
- **Nemotron plan latency:** 5.1 / 5.6 / 4.5 / 4.5 / 8.9 s (median 5.1 s, mean 5.7 s). 5/5 plans schema-valid and shown as normal plan cards. Two step orders came back for the same prompt (with a leading `observe` twice, without it three times); the deterministic planner absorbs this, so the route was the same.
- **Route determinism:** the coordinate planner produced the same route 5/5 (4 stops, 6.22 m, first leg 1.32 m straight ahead). Driven about 6.3 m in 21–23 moves.
- **LiDAR object recovery:** A box 12 / 16 / 17 / 7 cm (mean 13 cm, found 4/4); B stool 26 / 38 / 41 / 24 cm (mean 32 cm, found 4/4); **C soft bag found 0/4** (1.2 m ahead, 0.9 m left; the stops face the space ahead, so the bag probably had too little view and return). The four reference objects recurred within about ±10 cm of the same position every run, so they are real unmodelled objects rather than noise.
- **Return error (tape):** across 4.5 / 23.5 / 29 / 23 cm (all to the left); along 3.5 cm forward / 0 / 1 cm back / 7 cm forward; heading not recorded / about 5° / about 15° / not aligned. The app's own estimate put the robot within 2 cm of the start every time. **The app cannot see this drift**: the start pose is declared and there is no twin-based relocalization. This is the main limitation found.
- **Battery:** 12.30 → 11.30 V over about 75 minutes (5 attempts); the 11.1 V guard was not reached.
- **Model calls:** 5 planner + 1 VL = 6, all via Nebius Token Factory.

## 5. Incidents (kept separate from the numbers)

1. **4-1 guard stop.** The robot-side guard caught a mismatch between the torque-enable command and the wheel readback and stopped the robot. The retry passed the same segment.
2. **4-2 final turn refused.** The 74-minute session hit its 768 MiB recording budget (PC-side evidence log first, then the robot journal) → the robot stopped accepting motion and closed the session, as designed (fail-closed). Lesson: keep a physical session under about 60 minutes of connection, or reconnect between runs so the recording starts fresh. The PC disk was also nearly full at the same moment (screen-recording frames take several GB per hour): check free disk before a physical recording session.
3. **What a "stop" is.** The deterministic planner, not the LLM, picks observation points on the twin's free floor grid that satisfy ahead-of-robot, clearance and round-trip budget constraints. Stop 1 is the farthest free point straight ahead; stops 2–4 are the farthest from the points already visited. Stops are not chosen to look at objects, which is one reason the bag off to the left was never seen.

## 6. What this does and does not show

- **Shown:** the planning path (Nemotron → deterministic route) is repeatable; LiDAR recovers solid objects of box and stool size in every run, with rough positions; the guards fail closed and no run ended in contact.
- **Not shown:** an accurate return (odometry drift is real and invisible to the app); detection of soft or low objects outside the stops' view; obstacle replanning (nothing was on the route this time; see the Oct 27 filmed run and the Oct 25–27 box tests for that).
