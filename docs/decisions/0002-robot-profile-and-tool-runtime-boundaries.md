# Decision 0002: robot profile and tool/runtime boundaries

- Date: 2026-09-13
- Status: accepted for the local M2 repair

## Problem

The first procedural AGV treated "2W" as two total ground contacts. Its axle was near the chassis center and it had no passive support, so XY route metrics could pass while the chassis pitched forward. Scene authoring, robot physics, navigation intent, and runtime acceptance were also described too loosely as "MCP calls".

## Decision

1. `2W` means two **driven** wheels, not two total contacts. The default local profile is `agv_compact_2wd_caster_v2`: differential drive, two driven wheels, two passive ball casters, fixed mass/center-of-mass/inertia, and an 8 degree runtime attitude limit.
2. The LLM may select only a versioned profile ID. It cannot author wheel geometry, support placement, mass, inertia, controller gains, or safety limits.
3. Allowlisted operations are separated into scene, robot-selection, and task-intent domains. The in-process typed registry validates and compiles them deterministically and can return an execution receipt.
4. MCP is an optional adapter for external process/service boundaries. It is not the physics safety layer and must not carry the real-time motor loop.
5. Fast simulation/real control stays in deterministic runtime/ROS2 components with a local safety supervisor and watchdog. Future optimization emits a versioned parameter artifact rather than direct motor commands.
6. Acceptance includes 3D attitude and support structure in addition to planar navigation metrics. Headless runs write structured artifacts automatically.

## Compatibility

Persisted plans using `agv_compact_diff_v1` resolve to the v2 profile. New provider plans request the canonical v2 ID. Scene/task schema 1.0 remains unchanged; RobotProfile is upgraded to schema 2.0.

## Remaining limits

The current collision metric is deterministic footprint-vs-collider overlap, not a PhysX contact impulse trace. MinimalRendering produces no screenshot; interactive or server rendering evidence remains a separate visual acceptance item. Hardware-specific caster/footprint/inertia values must replace the prototype profile after an actual AGV is selected.
