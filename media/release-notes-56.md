Pre-robot demo check on installed build 56 (`20261027T055422Z-328f88e98444`, commit 01864fe; tree = main 21e2729 with the photo-library recognition of PR #8, the reduced sprint gate and the regression-module writer drain). One recorded pass, 2026-10-27 05:56-06:00Z, robot powered off: no Connect, no motion. Real click flow over the installed App, one real model call (photo analysis); the survey request is refused before any planner call.

| Step | Result | On screen |
|---|---|---|
| 1 New chat | PASS | chat_mvq9vkzo_d5f40d1a |
| 2 Home USD attach, units m, Import space | PASS | 30 objects, message "Import space - Project-2610222326.usd" |
| 3 Show Twin | PASS | Isaac live render 6.9 FPS |
| 4 Twin edits set to Auto-apply | PASS | |
| 5 Photo analysis, home-fan-basket.jpg (DeepSeek V4.1 Flash, 1 call) | PASS | 5 candidates: bag 62 %, basket 72 %, pedestal fan 85 %, small floor fan 80 %, clothing pile 78 %; scanned object names/types sent for duplicate hints (schema 1.1) |
| 6 Select the physical robot, Control view | PASS | Session gate, Link DISCONNECTED |
| 7 Start pose 0.681 / 0.206 / 0.489 by number | PASS | Declared pose saved (operator estimate, not localized) |
| 7b Drag placement on the floor map, Place robot | PASS | Marker (0.1, -0.4, 0) saved from the click-drag; numbers restored afterwards |
| 8 "Survey the room and come back" | Refused at once | "Stop and prepare the robot before a route." with no planner call (readiness guard runs before the model) |
| 5b Review candidate 1 (bag), place at (0.74, 1.14), Preview | PASS, auto-applied once | "Twin updated, saved and its current 3D frame confirmed." No model call. Recorded as segment 2 |

Header caption now reads "chat id - Twin"; the current-step text reads "request or preview a route". Step 9 (click-edit a route point) needs a route card, which needs a prepared robot; it is covered by the supervised physical run. Assets: 720p mobile recording (3:51) and key frames.
