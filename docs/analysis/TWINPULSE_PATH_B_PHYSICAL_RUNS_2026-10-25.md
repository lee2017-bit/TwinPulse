# Path B physical runs — analysis (2026-10-25)

Scope: five supervised runs of the declared-start route on TurtleBot3 Burger ("Imported existing settings · unverified") in the living room scanned as `Project-2610222326.usd`. The sources are the app's own recorded fleet observations (`outputs/path-b-20261025/phys01..05/observations.jsonl`), the robot operation journals, and the user's tape measurements and photos. Body motion is **not** independently verified. Distances are wheel odometry unless stated.

## 1. Result in one line

The robot surveyed the window side of the living room and came back to its taped start **2.5 cm forward and 2 cm to the right, with heading visually unchanged** (user measurement, after about 6.4 m of travel and 17 moves). The run did not finish automatically, though. The route runner stopped at a real obstacle 4 cm before stop 1, and the remaining 12 moves were typed in the app by hand.

## 2. What each run taught us

| Run | Outcome | Cause | Fix (commit) |
| --- | --- | --- | --- |
| 1 | Halted after the first 7.8° turn | Runner read the physical completion reason `OPERATOR_STOP` as an external Stop | Epoch continuity instead of reason for physical rows (`Do not treat a physical finite completion…`) |
| 2 | `FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP` at 0.58 m | LiDAR relative tracker followed ~25% of the odometry move | User decision: low tracker progress is *unverified*, not a stop, for supervised finite commands (`Record low tracker progress…`) |
| 3 | `FIELD_PROXIMITY_10CM` beside the TV wall after ~2.0 m | Start pose was an odometry estimate after runs 1–2, plus heading drift; plan kept only 17 cm | Re-taped start, window-corner obstacle in the Twin, 35 cm physical clearance (`Give physical declared routes a 35 cm berth…`) |
| 4 | 2.29 m straight OK, next step never acknowledged | Step sent the instant the previous one completed; robot ignored it; runner waited 50 s and mislabelled its own Stop | 1.5 s settle, 10 s ack timeout without resend, correct reason (`Settle between physical route steps…`) |
| 5 | 2.99 m of the 3.02 m first leg, then `FIELD_PROXIMITY_10CM` | Sansevieria leaves sticking out of the plant mat at LiDAR height (user photo) | Remaining 12 moves typed manually: all COMPLETED |

Every fix moved the failure further along the route. Runs 4 and 5 failed on **real-world** issues (protocol timing, an actual plant), not on safety timing gates.

## 3. Measurements

**Odometry heading drift (forward legs).** The executor targets distance only, and the robot curves left.

| Leg | Commanded heading | Odometry heading during leg |
| --- | --- | --- |
| Run 3, legs 1–3 | 36.1° | 39.0° → 40.3° → 41.1° |
| Run 4, legs 1–3 | 3.8° | 6.4° → 6.9° → 7.7° |
| Run 5, legs 1–4 | 3.8° | 5.9° → 6.2° → 6.4° → 6.6° |

This is roughly +2.5° at the first leg and about +0.3° more per 0.75 m leg. Over the 3 m first leg the odometry lateral offset reached 0.33 m, consistent with the run-3 wall approach and the run-5 drift toward the plants.

**Odometry vs reality at the end.** Odometry closed 0.154 m from the start. The tape showed 0.025 m forward and 0.02 m right. The real return was better than odometry predicted. The left curve and its odometry error partly cancelled on the return legs, so neither odometry nor the final closure alone qualifies the path in between.

**LiDAR relative tracker.** On forward legs it reported 5–47% of odometry distance (run 5: 0.25/0.756, 0.25/0.762, 0.17/0.759; run 3: 0.41/0.82). It also moved during in-place turns (0.57–0.65 m on the 135° and 110° turns) and drifted while stationary in run 2. It cannot serve as body evidence in this room.

**Declared start from tape.** Two measurements (1.00 m to the sofa leather front, 3.52 m to the window wall) plus the RoomPlan sofa length (3.038 m in the scan vs 3.0 m taped) gave a start that kept a 3 m straight leg clear of both the sofa and the TV wall. Tape plus the scan was good enough. The error came from drift during motion, not from the declared start.

**Battery.** 12.15 V → 11.23 V over the ~90-minute session (5 connects/Prepares). The cutoff is 11.1 V, so one more full run would have been marginal.

## 4. Root causes to address before the next physical test

1. **Open-loop heading.** Each forward leg ends where odometry says, but the next turn assumes the planned heading. *Change:* after every forward leg, compute the actual odometry heading and position, then re-aim the next turn/leg at the next planned vertex (odometry-closed waypoint following). This uses data the runner already reads; there is no new sensor and no guard change.
2. **Obstacles thinner than their footprint.** The plant mat with protruding leaves was larger than the 0.80 × 0.65 m box. *Change:* add the obstacle from the user photo with a ≥0.25 m uncertainty, or add the LiDAR cluster seen at the stop as a sensor obstacle and keep stops ≥0.8 m from walls.
3. **No resume after a correct safety stop.** *Change:* on `FIELD_PROXIMITY_10CM`, back off 15 cm (rear check), re-plan the rest of the route from the odometry pose avoiding the new obstacle, and ask for one confirmation. Today's manual recovery shows this works.
4. **Battery budget.** Charge to ≥12.3 V. Each restart costs Prepare plus Bootstrap, so do the code changes first and run a single physical session.

## 5. What this means for the demo

- **Ready to show:** RoomPlan Twin, declared start from a tape measure, chat "Survey the room and come back", Run route card with minimap, the real robot driving 3 m and turning, the safety stop at a real plant, the Twin updated with the missing obstacle, and the return to start within ~3 cm. It is an honest "Twin ↔ reality" story.
- **Not yet shown:** an uninterrupted automatic survey and return. The fixes in §4 (1 and 3 especially) are needed for that.
- **Physical footage rule:** at least 1 minute of real-robot footage. Record the next charged session from the start.
- **Labels:** odometry-based, start pose declared, body motion unverified, obstacle added by the operator.
