# A2 named room — actual browser/API/bridge/Isaac rehearsal

Date: 2026-09-29 KST. An isolated **synthetic** 4×4-pixel room photo and
project-local pinned Burger asset were used. No provider, robot connection,
deployment, timeline Run or physical test.

## Result

`C:\isaacsim\python.bat scripts\rehearse_named_room_isaac.py artifacts\runs\20260929-named-room-product-isaac-r3`
ended `NAMED_ROOM_PRODUCT_ISAAC=PASS`. Evidence:
[machine result](../../artifacts/runs/20260929-named-room-product-isaac-r3/result.json),
[browser result](../../artifacts/runs/20260929-named-room-product-isaac-r3/browser-result.json),
[React screenshot](../../artifacts/runs/20260929-named-room-product-isaac-r3/named-room-browser.png),
[reopened USD](../../artifacts/runs/20260929-named-room-product-isaac-r3/named-room-browser-stage.usda).
Reusable isolated harnesses:
[Python](../../scripts/rehearse_named_room_isaac.py),
[Playwright](../../apps/twinpulse-web/e2e/named-room-isaac-real.mjs).

- React restored the named project without approval/Build authority. A user
  click continued saved-room review; scene control acquisition and current
  revision acknowledgement were separate. Exactly one `build_site_scene`
  command reached the authenticated local API, production bridge and actual
  Isaac adapter; the broker operation succeeded. There was no Run permission.
- Isaac contained four Burger visual meshes, matching project manifest,
  `Physics=none`, no rigid/collision/articulation control APIs, no driven
  Robot/Task, no playback, and an untouched non-TwinPulse prim. The USD export
  reopened. Original room recipe bytes and imported draft/input were preserved.
  The explicit acknowledgement correctly updated the separate project state.
- The browser blocked external requests and its robot endpoint request was
  intercepted before the server; `robot_connections=0`. The model location is
  illustrative. The separate [viewport capture](adaptive-named-room-isaac-a2-20260929.md)
  shows a synthetic room only, not the user's measured space.

## Preserved failures and limits

`r1` and `r2` had successful browser Build checks but the harness incorrectly
asserted that the entire project record bytes must not change. That is false
for an explicit acknowledgement; `r2` located this at assertion line 115.
`r3` tests preservation of the source recipe and imported draft while allowing
the intended state change. This did not relax a product safety criterion.

Still **NOT_RUN**: actual user's room recipe and placement, model occlusion or
physical clearance validation for arbitrary poses, measured room↔robot TF,
real sensors, physical navigation and collision prevention. A2 remains partial.
The earlier stop failures and live mission locks remain intact.
