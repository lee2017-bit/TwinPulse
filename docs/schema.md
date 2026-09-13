# TwinPulse M1 data contracts

All contracts use schema version `1.0`, SI meters, and a Z-up world. Inputs are immutable dataclasses and must pass `validate_bundle` before any USD stage mutation.

## SceneSpec

- Stable scene `id`, `schema_version`, `units`, and `up_axis`.
- Bounded collection of `SceneObject` values.
- Each object has a stable ID, supported kind, transform, primitive shape, collision flag, optional dynamics mass, and optional allowlisted asset ID.
- M1 supports `box` and `cylinder`; the fixed fixture uses primitives only.

## RobotProfile

- Stable profile ID and `differential` drive type.
- Chassis dimensions, mass, wheel radius/base/width, and linear/angular speed limits.
- Current profile: `agv_compact_2wd_caster_v2` (two driven wheels plus two passive support casters).
- Legacy generated plans that reference `agv_compact_diff_v1` are resolved to the v2 profile; hardware geometry is never authored by the LLM.

## TaskSpec

- Stable task ID, referenced robot profile, start/goal transforms, operation, and planar goal tolerance.
- M1 permits only the `navigate` operation.

## Validation boundary

The default limits reject:

- invalid/duplicate IDs and broken robot references;
- non-finite values, non-positive dimensions, invalid mass, or unsupported versions/axes/units;
- more than 64 objects, a dimension above 50m, or a position outside ±100m;
- unallowlisted assets, object kinds, shapes, drive types, and operations.

These are runtime-configurable guardrails, not final product capacity promises.
