# Adaptive A2 — explicit local Burger visual preparation

Date: 2026-09-29 KST. This is an **offline project preparation** increment, not actual Isaac/robot validation.

## Product path

Given an unimported named project with a valid `room_recipe.json` and `assets/` photo, one explicit command can copy the already reviewed nine Burger visual files to that project's `assets/burger`, add their fixed digests and an **illustrative** position/yaw to the recipe, preserve the original bytes in `room_recipe.before-burger.json`, then import the existing App `ProjectRecord` and immutable input snapshot. The command does not call a provider, launch Isaac, start Build/Run, connect to a robot, or grant an execution lease. An existing/imported project or pre-existing preparation output is never overwritten.

Example syntax (values are project-specific visual guesses, **not** a physical pose):

```powershell
.venv\Scripts\python.exe scripts\import_room_recipe.py --state-dir C:\path\to\TwinPulse\runtime --project-id sample-room --include-local-burger-visual --visual-x-m 0.25 --visual-y-m -0.5 --visual-yaw-deg 90
```

The potentially modifying visual option requires `--state-dir` explicitly. Nonfinite/out-of-range pose is rejected before copying. If copying or final validation is interrupted, the current files remain visible; there is no silent reuse or overwrite. This is a **CLI increment**, not yet the desired in-App authoring/project chooser.

## Verification and limits

- New integration cases exercise the actual CLI on an isolated temporary project, original-recipe backup, fixed copied bytes, import without Build authority, repeat refusal, invalid pose with no write, and missing explicit state root refusal. A2 room suite **13 PASS**; full `scripts/verify_twinpulse.ps1 -SkipIsaac` **PASS** at `artifacts/runs/20260929-045419` (core173, Web126, production build). Earlier `artifacts/runs/20260929-045158` preceded the final explicit-root guard.
- Existing default bedroom golden and previous failed physical stop criterion are unchanged. Tests use synthetic 4×4 room photos and the known local Burger asset; this is not a demonstration of actual user-room scale, Isaac rendering, TF registration, or navigation.
- **Remaining A2:** App UI to choose a project and author/copy a model; actual isolated Isaac display of a named project; durable independent sensor/goal/calibration/mission references; default bedroom data recipe migration without golden changes. Physical readiness still requires separate evidence and user approval.
