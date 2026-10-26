# SIM demo recording review — 2026-10-26

Published recording: `outputs/path-b-20261026/demo-sim/twinpulse-sim-demo-2026-10-26.mp4` (29:37, 1920x1080, 10 fps, cursor drawn; H.264, decodes end to end). It is five segments joined in order, each recorded with ffmpeg gdigrab from the installed App on this PC, virtual robot only (Isaac kinematic SIM, "Demo SIM 4"); no physical robot:

| Segment | Source file | Build | Starts at | Content |
|---|---|---|---|---|
| A | `rec-take5.mp4` (take 5) | `20261026T012847Z-568386e8598e` | 0:00 | Twin rebuild, robot drop, Prepare, Nemotron survey, clicked stops, run, box, re-survey, run, photo analysis |
| B | `rec-sim-demo-partB.mp4` | build 30 `20261026T014315Z-6acdfebc88c7` | 10:49 | Photo candidate placed as a new Twin object; the box replace was blocked (one object per edit) |
| C | `rec-sim-demo-partC.mp4` | build 31 `20261026T020338Z-65015a5d365d` | 19:08 | Box replaced by a photo object in two edits (remove, then add with the photo colour) |
| C2 | `rec-sim-demo-partC2.mp4` | build 31 | 26:46 | The duplicate box (added twice in earlier takes) removed |
| C3 | `rec-sim-demo-partC3.mp4` | build 31 | 29:08 | Final obstacle list and Twin |

Each raw segment is a fragmented MP4 whose last fragment was cut by the forced recorder stop, so each was re-encoded minus its last 1.5 s before joining; the only action lost that way is the Apply click of segment C2 (its committed result is what C3 shows). Frames were extracted at every UI action and every 45–60 s (`frames-take5*/`) and inspected one by one; `frames-final/sheet.jpg` samples the joined file at the moments cited below.

Takes 1–4 were rejected by this review and are kept as evidence, not published: take 1 recorded the Isaac window on top of the App and the cursor never moved (CDP clicks), take 2 reused a robot label, take 3 lost the App behind Isaac mid-run, take 4 stopped at a clicked stop that had no room for the robot.

| # | User ask | Where in the published file | Result | Note |
|---|---|---|---|---|
| 1 | Recording from the first action with the cursor visible | 0:00–0:50 | PASS | App on top from the first click; the OS cursor is moved to every target before the click. |
| 2 | USD Twin + photo-derived objects | 0:08–0:40 (Reopen saved scene → Rebuild Twin in Isaac); 11:55–14:15 (photo → candidates → object placed, Edit COMMITTED) | PASS | The RoomPlan USD Twin with earlier photo-added objects (plant mat, fan base, basket, cable run) is rebuilt in Isaac with one button; segment B shows a photo analysed (DeepSeek-V4.1-Flash, 3 candidates) and one candidate placed as a Twin object. The USD file itself is private and is not re-imported on screen. |
| 3 | Robot placed by drag-and-drop | 0:49 (floor map click + heading drag → X 1.472, Y 1.053, yaw −1.201 → Add SIM robot) | PASS | Click places, drag sets heading; the values land in the numeric fields (still editable). Labelled operator estimate. |
| 4 | Prepare | 0:56–1:30 | PASS | Connect → Prepare → READY, LiDAR on. |
| 5 | NL survey with a clear purpose; route sensible, no zigzag | 1:34 chat "Survey the room and come back" → 1:34 card | PASS | Card says "Planned by nvidia/nemotron-3-super-120b-a12b via Nebius Token Factory · 4.7 s"; 2 stops, 4.65 m; polyline start→1→2→start without back-and-forth. |
| 6 | Create/edit the route by clicking stops | 1:38 two clicks on the preview map → "Re-plan via 2 stops" → 1:50 card "Route planned through your 2 chosen stops … Operator stops · no model call" | PASS | Clicked stops snap to free floor with room for the robot (take 4 failed here; fixed in build 29). |
| 7 | LiDAR shown in the Digital Twin view | 1:30 onward (cyan hit points around the SIM robot in the Isaac render; Route card shows the trace) | PASS | Live Isaac render in the Twin pane; the route card no longer squeezes it (build 27 fix). |
| 8 | Chat auto-scrolls to the latest message | 3:00 (Stop 1/2 of 2 reached messages visible, no "New updates" banner) | PASS | Follow mode until the reader scrolls up. |
| 9 | Robots list not clipped | 0:49, 3:00 (Robots rows readable) | PASS | Condensed rows keep their text. |
| 10 | Route run + return to origin | 1:52 run → 3:43 "Route completed · 2 of 2 stops" | PASS | 10 moves; "Route running · stop 2 of 2" in Current step and on the Twin-pane card. |
| 11 | Object position correction from LiDAR results | — | NOT SHOWN | Implemented (finish card offers "Move <object> to the LiDAR estimate" when a LiDAR candidate sits within 0.6 m of an existing object), but a SIM LiDAR never disagrees with the Twin, so no candidate appeared. Needs the physical run. |
| 12 | Add an obstacle, re-survey avoiding it | 3:50 Import space → Added obstacles → box "Box on leg 1" at (1.19, −0.22) → 6:13 Apply (Edit COMMITTED, Engine ACK) → 6:40 re-survey → 6:41 Nemotron card (5.2 s) → 8:49 completed | PASS | Second route goes around the box (stops moved to the left side). |
| 13 | Obstacle outline becomes a box | 6:13 | PASS (SIM limitation) | In SIM the box is added by hand; LiDAR outline boxes (oriented extent) are implemented for physical candidates. |
| 14 | Photo-based shape/colour upgrade of the box | 20:16 photo analysed → 20:26 "Replace an added estimate box" = Box on leg 1 (removal preview) → 22:45 Apply (COMMITTED) → 22:57 Candidate_2 at the box position (1.19, −0.22) → 25:06 Apply (COMMITTED) → 27:05 duplicate box removed → 29:24 list shows only photo objects | PASS (SIM limitation) | The box is replaced by the photo-recognized "Small white/red object on floor by wardrobe" (catalog shape for its kind, same 0.3 m footprint) carrying the photo crop's dominant colour (display only, saved as `display_color` [0.357, 0.361, 0.325]; Isaac displayColor). Take 5 (9:13) and segment B (14:26) show the two earlier blockers: the oversize reference-photo check (fixed build 30) and the one-object-per-edit rule (two-edit replace, build 31). The earlier takes had added the box twice, so C2 removes the second copy. |
| 15 | Nemotron / Token Factory label | 1:34, 6:41 | PASS | Model id and latency on the card and in chat; call logs under the project's `robot-tasks/<task_id>` (no keys). |

Live model calls during the whole demo work: planner 9, photo observer 4 (limit 100).
