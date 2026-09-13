# Decision 0001 — M1 process and ownership boundaries

- Status: accepted for M1
- Date: 2026-09-12

The pure `twinpulse_core` package has no Isaac dependency. The `twinpulse.extension` package bootstraps the local core source and owns USD prims only below `/World/TwinPulse`.

The M1 AGV is a deterministic procedural differential-drive fixture. This avoids remote asset availability as a prerequisite while still exercising real wheel joints and PhysX. It is a predefined test profile, not a purchased AGV model and not a visual teleport animation.

Repeated compilation of the same fixed fixture is a no-op once the validated owned root exists. Reset uses the timeline so it does not delete a Robot prim while Isaac tensor views are active. A future scene revision must use an explicit, lifecycle-safe reconciliation design rather than silently replacing unknown content.

The local Extension inserts `packages/twinpulse_core/src` into `sys.path` based on repository layout. Server packaging will replace this development bootstrap with an explicit package/lock step.

