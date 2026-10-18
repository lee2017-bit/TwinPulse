# Adaptive A2 — project-local Burger visual binding

Date: 2026-09-29 KST. **Offline product-path increment, not actual Isaac or physical acceptance.** Robot was reported OFF. No SSH, sensor, motor, deployment, provider, paid call, or physical test.

## Implemented boundary

- A named project's `room_recipe.json` may optionally carry `burger_visual` with `asset_dir: assets/burger`, all nine SHA-256 file digests, and an illustrative position/yaw. The project holds the actual local asset bytes; it cannot name an outside path or arbitrary USD file. The nine allowed files must match the already reviewed local Burger visual bytes. Missing, changed, extra, symlinked, or foreign-but-rehashed files fail closed on import/reopen. This is a display asset, **not** a verified robot profile or calibrated pose.
- The stored `SiteDraftRecord` stays the existing v2 scene-only draft. `ApplicationService` rechecks the recipe and optional visual source; the existing `ProductWorkflow` attaches a `project_room_visual_v1` descriptor only to that exact local draft. The existing broker passes it on `build_site_scene` only when the matching Isaac feature is currently ready. The managed launcher supplies the selected state root to the Isaac adapter; the adapter rechecks project ID, scene revision, recipe and every asset byte before entering the existing visual-only composer. No Build is automatic, acknowledgement and lease are not restored, and Run remains forbidden for site scenes.
- The preserved default bedroom descriptor and compositor output are unchanged. A named project cannot render the default-room fixture. The new descriptor has no replay, mission, world transform, or physical authority.
- Project data can be copied with relative paths to another permitted state root. `burger_visual` is optional; a project without it remains scene-only. The current CLI imports a prepared recipe; a user-facing asset-copy/recipe authoring flow and project chooser are still pending. No actual user project was imported in this run.

## Verification

- Focused A2 + default bedroom + process manager + engine readiness: **32 PASS** before the final fixed-file pin; final A2 + bedroom focused run **19 PASS** after that pin. A2's nine cases include two different projects/placements, copied-root reopen, broker command payload, no restored Build authority, changed/missing/extra-path/model bytes, false pose/measurement claim, and default plan/scene/manifest golden. The changed USD with its own updated claimed hash is rejected against the fixed reviewed bytes.
- Final full `scripts/verify_twinpulse.ps1 -SkipIsaac`: **PASS** at `artifacts/runs/20260929-043006`, including core173, A2 room9, Web126 and production build. Earlier full PASS `artifacts/runs/20260929-042628` preceded the final fixed-file pin and is not the final-source result.
- Default golden values remain: plan `4345d53d91133f05ea5d8960e808708362a21cc9882605a229f2242edfa198dd`, scene `c18410caf2fd41628b7487de1dabb0ee84b3161ac0a4ac0870f7a7cddf61b8b8`, default visual manifest `176e0bdc569aeff37b5173a77afbc48f185678efd306dd0ac12e7a6d7a8fefe1`.
- Managed Isaac execution of the **named** descriptor, visual screenshot, actual room-photo quality/scale, TF/odom, and all robot behavior: **NOT_RUN**. Static adapter wiring and fake/broker tests do not constitute actual Isaac acceptance.

## Remaining

Provide an explicit safe UI/CLI flow to copy the pinned model into a project and author `burger_visual` without hand-editing JSON; execute the named preview in actual isolated Isaac and visually inspect the stage; data-drive the preserved default room without changing its golden; isolate sensor/goal/calibration/mission references and provide project selection UI. A2 remains **PARTIAL**. Real navigation remains locked pending separately verified physical evidence.
