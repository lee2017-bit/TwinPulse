# Adaptive A2 — explicit empty project creation

Date: 2026-09-29 KST. **Offline A2 increment, not A2 completion.** Robot was reported OFF. No robot connection, sensor/motor action, deployment, paid API, cloud call, or Isaac run was performed.

## Product behavior

- The existing authenticated App project panel now accepts a lowercase portable name and calls `POST /v1/product/projects/create` with the product session and CSRF token. The API requires exactly `project_id`; `default`, path-like, malformed and duplicate names are refused.
- Creation writes an empty `ProjectRecord` only in `projects/<id>/project.json`, using the existing project store's bounded identity/path and atomic state-file write. The response shows `created_project_id` and the refreshed catalog. A saved draft, image, recipe, approval, lease, scene, runtime selection, robot session or physical permission is **not** created.
- The active backend/Isaac project remains unchanged. To use the new ID, stop the current launcher normally and explicitly start again with `-ProjectId`. No hot-switch is implied. If a filesystem write fails, creation reports failure; a newly made empty directory may remain for inspection rather than being silently deleted.

## Verification

- Focused Python project catalog/API: 6 PASS, 1 SKIP (Windows directory symlink creation unavailable). Cases cover empty record, no default mutation, duplicate/invalid IDs, authentication, CSRF, exact request shape, active ID and root-path non-disclosure.
- Focused React `App.test.tsx`: 27 PASS, including click-to-create without engine command or saved-review continuation. Production TypeScript/Vite build PASS.
- Full `scripts/verify_twinpulse.ps1 -SkipIsaac`: **PASS**, core 176, React 131 and production build PASS. Evidence: `artifacts/runs/20260929-project-create-r1/manifest.json` (08:30 KST); Isaac `NOT_RUN`.
- Initial local tests hit Windows sandbox Temp ACL and Vite child-process EPERM; the same local-only tests passed under authorized execution. No failure criterion was relaxed.

## Still open

Project editing/import UI, coordinated owned backend/Isaac project switch, project-local sensor and robot/mission history, real user-room geometry and real physical/TF/calibration validation. Named physical control remains locked. Historical stop FAIL, M2-D 27/29 FAIL, and live mission lock remain unchanged.
