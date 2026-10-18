# H2a core contract and migration boundary

- Date: 2026-09-25 KST. Canonical root: `C:\Users\jaewo\Documents\TwinPulse`.
- Scope/result: **H2a CORE_CONTRACT_UNIT_PASS / H2b-H2c_NOT_RUN / ACTUAL_ISAAC_NOT_RUN**. Existing dirty work was preserved; no commit/push, provider call, installation, or robot command.
- Visual summary: [H2a contract map](H2a-contract-map.png) ([editable SVG](H2a-contract-map.svg)). It is a design diagram, not a live Isaac screenshot.

## Implemented only in pure core

`site_contracts.py` adds additive schema `2.0` for an independent `SceneRevision`, optional `NavigationMapRevision`, optional `RobotInstance`, optional explicit `MissionSpecV2`, proposed `RunIntent`, and `SitePlan`. A scene can exist without a fabricated robot/mission. The scene stores source and parent lineage, the map stores a scene digest, frame, resolution, and explicit unknown/free/occupied cells, the robot stores a confirmed profile digest and initial pose, and the mission stores its unchanged requested start/goal/waypoints. The same observed entity cannot be both a static scene object and the mobile robot.

The pure gate reports scene geometry, robot/profile compatibility, mission support, and Run readiness separately. The existing +X-only controller remains a named capability; reverse, turns/waypoints, off-floor, stale map/profile, unknown/occupied cells, and stale engine evidence do not become drivable. Map checks conservatively cover every grid cell touched by the old +X robot corridor (chassis footprint plus 5 cm margin). This remains a preliminary gate, **not** a claim of general navigation or a replacement for the current runtime safety validator.

Run readiness additionally needs a non-legacy reviewed plan, exact scene/map/robot/mission identity, known demo safety policy, explicit controller capability, successful matching Build receipt, current engine/session/stage/snapshot, connected engine, no snapshot safety stop, and `run` permitted. The pure core cannot authenticate a caller-supplied receipt or clear `review_required`; H2b must own those trust decisions. The legacy v1 bundle imports only as review-required derived data without a map or carried approval/receipt.

## Version and migration matrix

| Payload / present writer and reader | Identity / added or removed fields | H2a legacy handling and H2b obligation |
|---|---|---|
| `InputRevision` 1.0; `revisions.py` | Existing canonical digest binds prompt, image hashes/MIME, constraints, profile, settings and catalog; no scene/map/mission fields changed | Preserve exact input/digest and old reader. H2b derives new records with lineage, never silently rewrites input. |
| `SceneToolPlan` 1.0; `scene_tools.py` + provider schema | Existing tool calls and required robot/task slots; existing plan digest | No writer change. H2b must version planner schema/parser/expander together before promising scene-only generation; old responses remain legacy. |
| `SpecBundle` scene/task 1.0 + robot 2.0; `models.py`/`validation.py` | Existing `bundle_digest` and controller gate remain unchanged | Explicit `import_legacy_bundle` validates then creates a review-required v2 scene/robot/mission; no map, approval, or Build receipt is inherited. Original persists. |
| `GeneratedDraftRecord` writer 3.0, readers 1.0/2.0/3.0; `draft_store.py` | Input/plan/bundle/validator hashes and receipt retained; no new site plan persisted | H2b adds a separate versioned derived record/reader and regression fixture; no re-labeling old validation as v2 approval. |
| `ProjectRecord` 1.0; `project_store.py` | `latest_input`, `draft`, timestamp; no scene/map/run revisions | H2b changes store/writer/reader atomically and retains original legacy project. |
| Engine 1.1 `CommandReceipt`/`SimulationSnapshot`; `engine_contracts.py` + TS generator | Existing applied revision is a **v1 bundle digest**, not a v2 scene digest | H2a synthetic receipt fixture is contract-only. H2b/c require negotiated version/capability and a real scene-revision receipt/snapshot; a v1 receipt cannot authorize v2 Run. |
| Workflow 1.1 and provider settings 3.0; app/extension readers | Existing workflow lease and non-secret provider binding remain | No H2a changes. H2b updates app/broker/API/TS and replay adapters without auto-carrying acknowledgement or key authorization across changed bindings. |
| New `SitePlan`/Scene/Map/Robot/Mission/Run 2.0; `site_contracts.py` | Strict schemas; canonical SHA-256 of scene/map/mission bodies; robot profile digest; Run references all identities | Pure writer/reader and fixtures only. No app/store/provider/Isaac consumer yet. Unsupported version, shape, digest, unknown map, and mismatched lineage fail closed. |

Only world-aligned maps are supported. A later scan with a different coordinate frame needs an explicit verified transform/version; it cannot be treated as free space. The initial pose is not live odometry. Scene geometry or scan changes must invalidate map/Run eligibility while preserving older artifacts and history. Start/goal changes create a new mission identity; they must not be quietly shifted to make a route pass.

## Verification and next boundary

` .\.venv\Scripts\python.exe -m unittest discover -s packages\twinpulse_core\tests -p test_*.py `: **38/38 PASS** (including 8 H2a tests). Fixtures cover scene-only, strict round-trip/digest/version, valid synthetic straight route, unknown/blocked/stale map, reverse/waypoint/off-floor/profile mismatch, legacy import, malformed maps, duplicated observed AGV, stale receipt/snapshot/capability/connection/safety policy. The positive Run fixture is synthetic: it does not establish runtime wiring or actual Isaac acceptance.

Next separately authorized stage is **H2b only**: versioned store/app/broker/API/provider/TS integration plus safe legacy replay. H2c then proves scene-only actual Isaac Build/receipt/Reset and capability-aware Run. No general route, scan apply, TurtleBot, or physical test is claimed here.
