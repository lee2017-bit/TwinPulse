# M2 generated-floor stability verification

- Date: 2026-09-13 KST
- Host: local Windows 10, Isaac Sim 6.0.1-rc.7, CPU physics, MinimalRendering
- Full verification artifact: `artifacts/runs/20260913-234455`
- Persisted-plan diagnostic artifact: `artifacts/runs/generated-stability-diagnostic/result.json`

## Root cause

The real-image plan generated an 18 x 12 x 0.1 m floor. The scene compiler represented every box as a unit `UsdGeom.Cube` plus a non-uniform scale operation. PhysX contact on this large, thin scaled collider was asymmetric enough to destabilize the two driven wheels and passive casters. Removing racks, markings, and static AGVs did not change the failure. Replacing only the floor geometry with an actual-size closed `UsdGeom.Mesh` removed it.

This was a deterministic scene-compilation/physics primitive defect. It was not caused by the LLM tool plan, MCP transport, route coordinates, or nearby generated objects.

## Persisted real-image plan

- Request: `643747bb-09b6-4571-a688-eca6059e8ada`
- Scene: `warehouse_aisle_scene_01`
- Input images: 1
- Plan: 14 allowlisted calls, 59 expanded objects
- Route: start (-5, 0) to goal (3, 0)
- Result: completed in 1,889 frames
- Final position: (2.753533, 0.000478, 0.220000) m
- Goal error: 0.246468 m; task tolerance 0.25 m
- Maximum absolute roll: 0.086213 degrees
- Maximum absolute pitch: 0.073829 degrees
- Maximum absolute yaw error observed: 0.127121 degrees

Before the repair, the same plan stopped as `unstable` at frame 187 with 9.0393 degrees roll.

## Permanent regression

The standard verifier now builds an 18 x 12 m floor and asserts that `/World/TwinPulse/Environment/floor_main/geometry` is a Mesh with no `xformOp:scale`. Its 6.9 m episode result was:

- Runtime state: completed
- Goal error: 0.049289 m
- Maximum cross-track error: 0.004352 m
- Maximum absolute pitch: 0.066773 degrees
- Maximum absolute roll: 0.076246 degrees
- Vertical range: 0.000379 m
- Geometric collision samples: 0/1723

The full verifier passed core 23/23, provider 8/8, Extension lifecycle 3/3, short Run/Reset 3/3, generated/fallback/rollback, robot support, visual-contract, and long-route checks.

## Limits

MinimalRendering did not capture a screenshot. The result validates the saved one-image plan and the permanent large-floor fixture, not all possible generated scenes. A Full-app visual check and the three-image M2-C gate remain open. Physical deployment is out of scope.
