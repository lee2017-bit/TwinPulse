# Repeat session 2 — protocol, written before the runs (2026-10-29)

**Status: pre-registered, not run.** This file is committed before any robot session so that the plan, the metrics and the stop rules are fixed in advance. Results, including failures and runs that did not happen, will be appended under "Results" without editing the sections above it. If no session takes place before the hackathon deadline (2026-10-31 02:00 KST), "Results" stays "not run".

## 1. Why a second session

The [Oct 28 repeat runs](TWINPULSE_REPEATABILITY_2026-10-28.md) kept twin edits on **Review** and skipped every LiDAR candidate, so they measured planning repeatability, LiDAR recovery and return drift, not the twin-update loop itself. The loop that the demo video shows — LiDAR finds an object the twin does not have, it is **auto-applied** to the twin, and the next route is planned around it — has one recorded instance (the filmed run, Oct 27). This session repeats that loop three times with Auto-apply on, and lets one person who has never used the app type the command once.

## 2. Setup (same build, same room, same start)

- Robot: TurtleBot3 Burger, living room. Declared start pose X 0.681 Y 0.206 yaw 0.489 on the tape mark; the robot is put back on the mark before every attempt and its return is measured against the mark with a tape (along / across / heading).
- App: build 61 (`20261027T233111Z-059aab92576d`, unchanged since Oct 28), a new chat, Control view, twin edits = **Auto-apply** (with Undo available, as in the filmed run).
- Placed objects, from the Oct 28 positions: A cardboard box 1.0 m ahead, 0.7 m right (twin ≈ (1.89, 0.06)); B stool 2.1 m ahead, 0.2 m right (≈ (2.63, 1.02)). The soft bag C is placed again (1.2 m ahead, 0.9 m left) only to confirm the Oct 28 miss; its result is reported but not counted as a failure of the loop.
- Base twin: the room scan plus the two photo objects accepted on Oct 28 (cable beside the sofa, bag behind the sofa). Between runs every auto-applied object is removed with Undo, so each run starts from the same twin; the Undo is recorded.
- Before the first run: battery voltage recorded (no extra start threshold; the code guards decide: 11.1 V low-voltage stop, 11.2 V re-arm), at least 10 GB free on the PC disk, screen recording on.
- Connection: reconnect the robot before every run so each physical session stays well under 60 minutes and the 768 MiB recording budget that ended attempt 4-2 on Oct 28 cannot recur.

## 3. One run, step by step

1. Type "Survey the room and come back" in the chat. Record: plan latency, plan steps as returned by Nemotron, planned route length and stop count on the route card.
2. Run route. Record: stops reached, moves, return error by tape, battery before and after.
3. Record what Auto-apply added to the twin during the run: each object's label and twin position, and the tape distance for A and B. Reference objects already in the room (robot vacuum and dock, plant pot and basket, cables) are listed separately, as on Oct 28.
4. On the updated twin, click one point about 0.5 m past the box (the same spot each run, marked on the floor) and plan the route through it. Record: whether the planned route goes around the box as it now stands in the twin (yes / no), route length, and the card's own text.
5. Run that route. Record: completed or not, any proximity stop or replan, return error by tape, objects added on this route.
6. Undo the auto-applied objects, put the robot back on the mark, reconnect.

Three runs are planned (N = 3). A guard stop is retried once, counted as a separate attempt, exactly as on Oct 28.

## 4. First-time user (during run 2 or 3)

A household member who has not used TwinPulse sits at the PC after the robot is armed and bootstrapped by the operator. They are told one sentence: "Type what you want the robot to do, then press Run route." Recorded: the time from their first keypress to the wheels turning; what they typed; one quoted sentence of confusion, if any; what they asked. Nothing else is explained until the route has started. No video of the person is required; the app recording runs as usual.

## 5. Stop rules

- Any contact with an object or a person: stop, record, end the run.
- Battery: no threshold beyond the code guards. If the robot-side 11.1 V guard stops a run, record it as a guard stop and charge before the next run (motion re-arms at 11.2 V).
- A second guard stop in the same run: end the run, no second retry.
- More than 45 minutes of connection: reconnect before the next run.
- Any run that cannot start or finish is reported with its reason; nothing is excluded from the table.

## 6. What the numbers will be called

| Metric | Definition |
| --- | --- |
| Attempt | one Run route of the survey mission; a guard-stop retry is a new attempt |
| Completed | all planned stops reached and the robot back at the start with the final heading aligned |
| Auto-added | an object the app added to the twin without a click during the run; A and B count as found when an auto-added object is within 50 cm of the tape position |
| Re-planned around | the second route's planned path leaves at least the box's clearance on every side of the auto-added box, as drawn on the route card |
| Return error | tape measurement against the start mark, along / across / heading |
| First-time user time | first keypress to wheels turning |

## 7. What this can and cannot show

- Can show: whether the auto-apply loop (LiDAR → twin → re-plan around the new object) repeats, with positions; whether a first-time user reaches the aha moment without instructions.
- Cannot show: an accurate return (the start pose is declared and there is no relocalization), soft or low objects outside the stops' view, or anything about factory AGVs.

## Results

Not run yet.
