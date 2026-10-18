# Adaptive A2 — project-local photo room recipe and explicit App continue

Date: 2026-09-29 KST. **Offline A2 increment, not A2 completion or physical acceptance.** Robot reported OFF; no SSH/serial/sensor/motor/deployment/provider call or actual Isaac run.

## Connected behavior

- For a named project only, `projects/<id>/room_recipe.json` holds a versioned `room-recipe-1.0` envelope: exact project ID, bounded prompt, `assets/`-relative photo path and SHA-256, plus the existing v2 `SiteToolPlan` object. The loader validates JSON shape/duplicate keys, path/root/symlink, photo bytes/size/full decode and hash, plan allowlist, and rejects photo-only claims of trusted measurement, driven AGV, or mission. It creates the existing `InputRevision` and `SiteDraftRecord`, not a parallel scene compiler.
- Explicit `scripts/import_room_recipe.py --state-dir <local runtime> --project-id <name>` writes an immutable input snapshot and the existing named `ProjectRecord`; it does not overwrite a populated project, call a model, connect a robot, or issue Build. Two different photo/plan projects require only different project-local recipe data, not source edits. Copying the project folder to another allowed runtime root reopens because no absolute photo path is stored.
- Existing `ApplicationService`/`ProductWorkflow` validates the recipe again on reopen. The authenticated/CSRF-protected `/v1/product/project/continue-room` and the App's **Continue saved room review** button explicitly reselect the verified saved photo into the current workflow; they do not restore acknowledgement, lease, Build, Run, or real-device authority. Missing or changed source appears as `project_restore_invalid` in read-only state and cannot overwrite the saved record.
- A named project cannot call the old hard-coded default-bedroom prepare/build/replay endpoint. This prevents a named room from silently displaying the preserved default fixture. Named recipe geometry is currently a v2 **scene-only** review; its Burger visual asset placement is not yet connected. The default bedroom photo, plan, scene and Burger manifest are unchanged.

## Verified boundaries

- New room recipe tests cover two different 4×4 synthetic photos/plan geometries, product reopen and explicit continue, authenticated API/CSRF, no lease/Build, moved runtime root, missing/changed photo and plan rejection without record rewrite, traversal/false measurement rejection, and default bedroom golden. New room tests **6 PASS**; named-state isolation **4 PASS**; focused A2 + existing R5 API **29 PASS**. Web UI suite **126 PASS**, production TypeScript/Vite build PASS.
- Preserved default hashes: plan `4345d53d91133f05ea5d8960e808708362a21cc9882605a229f2242edfa198dd`, scene `c18410caf2fd41628b7487de1dabb0ee84b3161ac0a4ac0870f7a7cddf61b8b8`, visual manifest `176e0bdc569aeff37b5173a77afbc48f185678efd306dd0ac12e7a6d7a8fefe1`.
- Full `scripts/verify_twinpulse.ps1 -SkipIsaac`: **PASS**, artifact `artifacts/runs/20260929-040020` (the final A2 source, including App/API changes). This is offline verification; Isaac and real hardware are excluded.
- Actual managed Isaac visualization of a named recipe, actual user-photo geometry quality, Burger placement for named recipes, live robot/collision/TF/calibration: **NOT_RUN/NOT_IMPLEMENTED** as applicable. No stored/photo estimate becomes surveyed geometry or motion permission.

## Remaining A2

Data-driven version of the preserved default room recipe (without changing its golden), project-local pinned Burger asset manifest and actual Isaac visual placement, independent sensor/goal/calibration/mission history references, project selection UI rather than launcher-only selection, and full copied-root/missing-asset recovery UX. Current App continue acts within the selected named project; it does not hot-swap projects.
