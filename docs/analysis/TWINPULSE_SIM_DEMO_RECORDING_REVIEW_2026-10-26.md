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

## Follow-up after the user's viewing (2026-10-26 afternoon)

The user watched the published file and reported three problems. Causes found from frames of that file (`frames-cause/`) and fixes verified on a new SIM take (`rec-verify35.mp4`, 254.6 s, build 35 `20261026T065802Z-5ec1fe766c8d`, frames in `frames-verify35/`). A first verification take on build 34 (`rec-verify34.mp4`, `frames-verify34/`) exposed the remaining cause of point 1 and is kept as evidence.

| # | Reported | Cause | Fix | Verification frame | Result |
|---|---|---|---|---|---|
| 1 | Digital Twin on the right looks cut off / small | The window did fit the physical 1920×1080 screen (125 % scaling), nothing was cropped. The chat column had 55 % plus a 240 px sidebar, so the Isaac render was ~700 px wide; and while the Import space panel was open (the whole photo segment) it spanned both columns at 45 vh, leaving the Twin pane too short and the render cut at the bottom. | Wide windows default to chat 40 / Twin 60; the Import space panel now lives inside the chat column, so the Twin keeps its full height; the recording script folds the sidebar. | `frames-verify35/009-0046.9s-shot_W1_twin_with_import_ope.jpg` (import panel open, whole room visible), `020-0203.6s-shot_W3_object_added.jpg`, `024-0213.0s-shot_W4_final.jpg` | PASS |
| 2 | Chat should open already at the latest message, not scroll down | The jump to the bottom ran in an effect after paint and the 400 ms follow tick caught later re-flows one by one, which looked like scrolling. | `useLayoutEffect` jump before paint on open; a ResizeObserver/MutationObserver pins the bottom synchronously on every transcript re-flow while in follow mode; smooth scrolling is not used. | `frames-verify35/dense/open-sheet.jpg` (16 frames at 4 fps around reopening the 290-message chat: the first rendered frame is already at the last route card; no top-to-bottom motion), probe `ui-actions-verify35.jsonl` scroll gap 0 | PASS |
| 3 | Demo must start from a new chat with USD and photos, not an existing chat | The published take reopened the saved project. | Runbook §2a and the driver start with New chat → attach USD → Meters → Inspect → Import → Show Twin → photo analysis → candidates placed → Twin edits set to Auto-apply on screen. | `frames-verify35/002-0011.5s-new_chat.jpg` … `008-0045.3s-show_twin.jpg`, `013-0067.9s-shot_W2_photo_candidates.jpg`, `023-0211.6s-set_twin_edits_auto.jpg` | PASS |

The published `twinpulse-sim-demo-2026-10-26.mp4` still shows the old layout and the saved-chat start; the next full take (physical session, runbook §2a/§2b) replaces it. Live model calls after this follow-up: planner 9, photo observer 6 (limit 100).


## Factory SIM demo take (2026-10-26 evening) — pre-release `sim-factory-demo-2026-10-26`

User decisions after the afternoon take: SIM-only demo = a **factory** photo (public-domain NIST AGV photo, `outputs/path-b-20261026/factory-photo/SOURCE.md`), never the home USD; start from New chat; show robot placement and driving; no still screen longer than 5 s; fix root causes instead of re-recording. Recording `twinpulse-sim-factory-demo-2026-10-26.mp4` (8:56, 1920×1080; mobile 1280×720 copy), two parts joined with an on-screen title card.

| # | Checked | Evidence (frames / driver log) | Result |
|---|---|---|---|
| A | Factory photo → Twin from New chat, live generation | part 1 0:00–~3:40: ＋ New chat, photo attached, "Simulation only", 24-object generation (planner + observer, 12 calls) | PASS |
| B | Digital Twin not clipped / not tiny | window 0,0,1920,1080 (DPI-aware arrange), Control-view render ≥40vh (`0b8b1f4`); contact sheets show the full render | PASS (letterboxed 3:2 render inside the wide panel remains) |
| C | Robot placed, Connect/Prepare/LiDAR, Nemotron route, SIM box, proximity stop → 40 cm back-off → keepout re-plan → return | route 1: 19 moves, 1 recovery, reached 1/3 (stops 2–3 skipped after the stop), 2 LiDAR candidates | PASS |
| C2 | LiDAR candidates auto-added as Twin boxes (Auto-apply) | two "Auto-applied … LiDAR outline box" + "Twin updated … frame confirmed" | PASS |
| C3 | Automatic re-plan after the auto edits | part 1 ended here: `declared_route_scene_required` because the grid was still rebuilding → fixed in `410de82`; part 2 shows the route requested again on the updated Twin (planner call), 3/3 stops + return | PASS with honest cut (auto re-plan itself not on video) |
| C4 | Photo upgrade of a LiDAR box | part 2: Replace → removal auto-committed → candidate placed at the box centre → second commit | PASS |
| D | No still segment > 5 s | pixel-count detector (`still_segments.py`): 20 + 12 segments played at 8× with a banner; final scan 2 segments of 5.0 s and 5.5 s | PASS (5.5 s remains) |
| E | Robot stops before touching the box | OBSTACLE_STOP at 10 cm skin, back-off 40 cm (`SimObstacleStopRecoveryTest`) | PASS |

Root causes fixed today (all with tests): grid budget 10000→40000 cells (12×8 m factory), SIM obstacle re-authoring every tick, SIM box never authored (NameError), OBSTACLE_STOP not treated as proximity stop, SIM keepout/back-off .45/.40, LiDAR section cache ignoring SIM obstacles, auto re-plan skipped after the last queued edit, **repair patch schema required a `recipe_parameters` key that stored objects drop → every geometry repair of builtin/warehouse objects failed and the first factory take stalled (`7bf92bd`, replay test on the saved patches)**, auto re-plan before the rebuilt grid (`410de82`). One-pass stage contract test: `SimLoopStageContractTest`.

Live model calls today (planner + observer): generation 12 + 12 (one stalled take), routes 6, photo observer 4; cumulative ≈ 87 of the 200 approved.
