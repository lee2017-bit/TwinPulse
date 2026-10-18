# Saved sensor map and photo room coordinate link

October 4, 2026. The existing App can now connect a recorded sensor-map position candidate to the approximate photo-room frame using explicit point correspondences. It separates fitted points from held-out checks and previews a room goal in the historical query odom frame. This is a connected offline visual review, not measured calibration, a current robot position or physical demo acceptance.

## Connected product flow

Build a saved observation map and use **Find scan position in the sensor map**. A unique historical sensor-map candidate reveals **Link sensor map to photo room**. Load the current photo wall anchors, select a recorded endpoint and an authored wall corner in the side-by-side views, and add each correspondence. Endpoint indices and corner IDs are also available as form inputs. At least three noncollinear fit pairs and one distinct validation pair are required; the maximum is sixteen pairs.

**Check coordinate link · no movement** shows individual errors, fit RMS and the held-out maximum, with three historical scan overlays. A consistent visual candidate enables **Preview linked goal coordinates**, which converts photo-room XY to the historical query odom frame. It does not submit a mission or position the current robot. Mismatch hides usable pose and goal controls; outside-room returns remain visible rather than being clipped into apparent agreement. Progress, exact failures, changed-source rejection and a 45-second request/body deadline are explicit. There is no automatic retry.

The three authenticated strict-shape API paths are `photo-link-context`, `photo-link` and `photo-link-goal` under `/v1/product/room-localization/`. This increment connects the Web and App service; it does not add a CLI command or extend the Isaac renderer.

## Coordinates and evidence boundaries

Targets are server-derived corners of the current authored walls intersecting the nominal sensor plane. Furniture is displayed only as unmeasured appearance and is never an anchor or clearance certificate. The current room supplies twelve wall corners. No client-supplied target XY, scale or transform is accepted.

The fit estimates a proper rigid planar translation and rotation from fit pairs only. Validation points do not influence that transform. Scale is fixed to one and the rotation determinant to one; neither reflection nor room resizing can repair a mismatch. Both fit and held-out maximum residuals must satisfy the existing 50 mm draft correspondence threshold. This is a visual consistency rule, not a stopping criterion or physical accuracy guarantee. Even a candidate retains `correspondences_verified=false`, `alignment_verified=false`, `motion_authorized=false` and `physical_demo_ready=false`.

The service binds room and scene revisions, current observation and sensor-match revisions, reference/query raw hashes, nominal model revision, project and invalidation epoch. It reloads originals before and after computing the link and at goal use. Changed raw data, room, sensor model or epoch, an ambiguous sensor position, stale context and concurrent work are rejected. Source indices and original endpoint frame provenance are preserved. Derived reports are exclusive, bounded, canonical-hashed files in `artifacts/sensor-photo-link`; original recordings and earlier failures are unchanged.

The goal preview remains `HISTORICAL_QUERY_ONLY_NOT_CURRENT_ROBOT`, with `collision_clearance_verified=false` and `mission_request=null`. A source/epoch-bound coordinate conversion is not live localization or authorization.

## Verification

- Python selected core and App regression: **368 tests and 303 subtests passed**, `artifacts/sensor-photo-regression-20261004-r1.xml`. This is a selected regression suite, not every repository test or physical acceptance.
- New core/App focused checks: **10 tests and 18 subtests passed**, `artifacts/sensor-photo-focused-20261004-r3.xml`. Earlier focused runs accidentally collected eighteen imported fixture tests; the import was corrected and this final count excludes duplicates.
- Whole Web regression: **221 tests passed**, `artifacts/sensor-photo-web-20261004-r2.json`. TypeScript and production Vite build passed.
- Real production Web → authenticated API → preserved actual ROS decoding: `artifacts/sensor-photo-browser-20261004-r2/verification.json` passed after correcting clipped wall-corner markers seen in the first run. Desktop/mobile screenshots were inspected, with no horizontal overflow, external requests, robot connections, engine commands or page errors. The isolated project was unchanged. The final build hash is recorded with the evidence; the earlier run is preserved separately.
- Positive rigid-link and goal conversions use explicit synthetic geometry in core tests and mocked contract data in App/Web positive tests. They establish implementation behavior, not a physically correct room transform. Scale/reflection mismatch, collinear/duplicate/unknown/nonfinite pairs, absent validation, stale sources/model/epoch, authentication, strict API shape and delayed UI results are covered.

For actual preserved session `4493be87ef7643ababb661b4a12f0180`, the browser loaded the held-out reference and three-frame sensor-map candidate. It deliberately selected unverified endpoint indices 0, 1200, 2500 and 3500 against `wall_left:0`, `wall_right:1`, `wall_window:2` and `wall_window:3`; the last was validation only. These are test selections, not asserted physical correspondences. The real API returned `ANCHOR_MISMATCH`: fit RMS 3.119 m, fit maximum 4.153 m and held-out maximum 2.982 m. Usable photo-room pose was null and no goal control or movement permission appeared. Those numbers describe intentionally wrong selected pairs, not the true room alignment error.

## Remaining integration and physical gaps

Correct observed wall correspondences have not been independently identified or surveyed. The photo room still uses estimated dimensions and unmeasured furniture boxes; nominal sensor mounting, declared acquisition timing and odom drift remain unverified. The earlier automatic photo comparison disagreement is not overwritten by this new optional visual link.

This increment displays a Web XY overlay and supplies the candidate transforms. It does not render this new link into the Isaac 3D Burger scene, edit room geometry, export a measured TF, accept a live changed-start pose, enable collision avoidance or run an autonomous mission. Existing historical Isaac previews remain separate; no Isaac runtime acceptance is claimed here.

Next offline integration is an explicitly visual-only 3D preview of the source-bound link and correspondence review. A physical demo still requires current-start localization and calibrated geometry plus guarded live control acceptance. No additional robot lap was requested or executed. The earlier communication repair remains undeployed and the requested 0.08 m/s is unapplied. All original failed sessions, stopping thresholds and physical mission locks remain intact.
