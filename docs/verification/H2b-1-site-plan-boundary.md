# H2b-1 — versioned site tool-plan boundary

- Date: 2026-09-25 KST. Scope: **H2b-1 CORE_AND_PROVIDER_SCHEMA_UNIT_PASS / H2b_INCOMPLETE / ACTUAL_ISAAC_NOT_RUN**.
- Visual summary: [PNG](H2b-1-site-plan-boundary.png) ([editable SVG](H2b-1-site-plan-boundary.svg)); this is a structure diagram, not a product or Isaac screenshot.

## What changed

An additive `SiteToolPlan` version 2.0 and `site-tools-2.0` catalog identity now have a strict parser and deterministic, allowlisted `execute_site_tool_plan` path. Existing `SceneToolPlan` 1.0, `GeneratedDraftRecord` 3.0, and the live Nebius v1 generation path were not changed. A v1 plan is not silently parsed as v2.

The v2 path requires exactly one floor, permits zero or one predefined robot, and permits zero or one navigation mission **only if a robot is explicit**. It rejects duplicate call IDs, non-allowlisted tools, duplicate robot/static-AGV portrayal without observation binding, malformed arguments, and excess object expansion. It reuses existing bounded geometry builders and rack-overlap validation. Resulting `SitePlan` is always `review_required=True`; the source reference is a trusted caller-supplied SHA-256 digest, not an LLM claim. Navigation map and current Build receipt are absent. A proposed goal is preserved verbatim, including reverse or unsupported goals; no local route relocation occurs in this v2 path. Unsupported mission is not Run authorization.

A separate provider `site_tool_plan_json_schema()` describes the v2 shape, with robot and mission slots optional. It is **not selected by the live Nebius adapter yet**. Local core validation remains authoritative over schema hints.

## Checks and remaining work

- Core `unittest discover`: **42/42 PASS**, including 4 new H2b-1 fixtures for scene-only, robot-only, explicit reverse goal, v1 rejection, malformed plans, and ambiguous robot portrayal.
- Provider `unittest discover`: **28/28 PASS**, including distinct v2 schema check.
- `compileall` and `git diff --check`: PASS; Windows LF→CRLF warnings only.
- No live provider request, App/store/broker/API/TypeScript migration, Isaac Build/Run, ROS/physical command, installer, commit, or push.

**Next H2b-2** must connect versioned v2 output through the single generation owner and a new persisted derived record, then expose an honest review-only UI/API state. Legacy replay remains on its v1 path, with any v2 derivation requiring fresh review; old approval, receipt, stage identity, and Run authority must never transfer. H2b-3 must negotiate broker/engine/TS capabilities before H2c actual Isaac validation. Do not turn on the v2 provider schema alone, because the current app still expects a v1 `SpecBundle` and old required call slots.
