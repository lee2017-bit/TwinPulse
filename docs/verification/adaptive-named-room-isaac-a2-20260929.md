# A2 named room — actual isolated Isaac visual check

Date: 2026-09-29 KST. Scope: synthetic 4×4-pixel room photo, project-local
recipe and pinned Burger model only. No robot connection, provider call,
timeline Run, deployment, or physical validation.

## Execution and result

`C:\isaacsim\python.bat scripts\verify_named_room_isaac.py artifacts\runs\20260929-named-room-isaac-r4`
ran in an isolated output root and exited with `NAMED_ROOM_ISAAC=PASS`.
The [machine result](../../artifacts/runs/20260929-named-room-isaac-r4/result.json),
[viewport capture](../../artifacts/runs/20260929-named-room-isaac-r4/named-room-actual-Isaac.png),
and [saved USD](../../artifacts/runs/20260929-named-room-isaac-r4/named-room-stage.usda)
are retained. The harness is [verify_named_room_isaac.py](../../scripts/verify_named_room_isaac.py).
After this addition, the full offline `scripts/verify_twinpulse.ps1 -SkipIsaac`
also passed at `artifacts/runs/20260929-052555` (core 173, Web 126, production
build). That offline suite does not substitute for the separate actual-Isaac
check above.

- An unimported named room copied the reviewed nine Burger asset bytes, retained
  `room_recipe.before-burger.json`, imported its draft, and remained without
  Build authority until the explicit test lease/command.
- `ProductWorkflow` registered the named descriptor; `CommandBroker` issued
  `build_site_scene`; `IsaacSimulationAdapter` rechecked the project root and
  rendered the scene in actual Isaac. The receipt succeeded. Four Burger mesh
  prims, the matching manifest hash, `Physics=none`, no physics control APIs,
  no driven Robot/Task, no permitted Run, no timeline playback, and an untouched
  external prim were checked. Exported USD reopened with matching provenance.
- The viewport capture was inspected: at the test pose `(0, -0.65, .002)` the
  small Burger is visible beside the bed. It is only an illustrative pose in
  synthetic geometry, **not** a verified user-room placement or collision-free
  physical path.

## Earlier test iterations and boundary

- `r1` failed because the isolated harness had not passed the broker's control
  lease to the adapter. The harness was fixed; production code was unchanged.
- `r2` proved the stage and saved USD but did not capture pixels.
- `r3` passed structural checks at illustrative `(0.25, -0.5, .002)`, yet visual
  inspection showed the Burger was hidden by the bed. This reveals a limitation:
  the current preparation CLI bounds the pose but does not check visual occlusion
  or physical clearance. `r4` changed only the synthetic fixture pose, not the
  underlying acceptance thresholds. These failed/limited results are retained.

**Not tested:** authenticated React browser → API → live bridge for a named
project, a user's actual room recipe, measured scale/TF, a safe placement
validator, autonomous/physical motion, real sensor data, or collision avoidance.
The existing default-room browser/bridge/Isaac test is separate. A2 remains
partial; A1b/physical mission gates and historical stop criteria are unchanged.
