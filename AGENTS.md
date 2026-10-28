# TwinPulse project instructions

> **Sprint mode until the 2026-10-31 02:00 KST submission (user-approved 2026-10-25).** The active work definition is `docs/planning/SPRINT_PATH_B_SPEC.md`. Read it first; do not read the full Baseline/Project Memory/README/progress unless a task needs a specific fact (search, then read only that section). Record each finished task as one line at the top of Project Memory; defer Baseline version bumps and progress/README rewrites until after submission. Exception (user-approved 2026-10-25): the judge-facing README.md replaces the old one once for the submission; the previous README is kept verbatim as DEVLOG.md, and new dev-log entries go there. Detailed robot-evidence, build-retention and license rules were moved verbatim to `docs/planning/AGENTS_DETAIL_RULES.md`; read the relevant section before any physical robot test, readiness handoff, build cleanup or public release.

## Always

- Communicate with the user in Korean. Product UI text stays short English.
- Never execute arbitrary model-generated Python or shell commands.
- Do not store API keys, tokens, authorization headers, or company credentials in this repository or logs.
- Only modify `/World/TwinPulse` prims in a user's stage unless the user explicitly approves a broader operation.
- Do not install or change ROS2, Isaac Lab, drivers, WSL, Docker, firewall, paid cloud resources, or physical AGV controls without the corresponding user approval. Physical robot motion needs the user's approval for that session.
- Never weaken Stop, freshness, voltage, proximity, unknown-space or final-output guards, re-stamp timestamps, or delete failing evidence to manufacture a PASS. Changing *where* a check runs must keep an equal-or-stronger check before motion.
- Saved projects/plans/poses never restore connection, Arm or motion authority on reopen.
- Keep original geometry/units/provenance. Missing unit metadata is never measured scale. An operator-declared pose is labelled as declared, not measured.
- Do not mark a runtime milestone PASS without actual Isaac Sim (and, for physical claims, robot) evidence. Unit/API tests are supplementary and must be labelled as such.
- Preserve original failure records; a clean rerun does not prove an earlier root cause.

## Code layout

- React UI `apps/twinpulse-web/src/`, Electron `apps/twinpulse-desktop/`, backend `packages/twinpulse_app/`, pure core `packages/twinpulse_core/`, model provider `packages/twinpulse_provider/`, Isaac adapter `extensions/twinpulse.extension/`, robot-side runtime/guards `packages/twinpulse_robot_safety/`. Keep these layers separated.
- `Start-TwinPulse.cmd` runs the installed package; source edits do not change it. `Start-TwinPulse-Development.cmd` runs source.
- Match the surrounding code style. Prefer the smallest change that satisfies the task's stated acceptance check.

## Acceptance

- User-facing acceptance follows the real start entry point and visible click/typing flow in the real App, with actual provider/Isaac results. Direct API calls, injected state, intercepted requests or fixed model replies are not ordinary-user acceptance.
- Robot motion verification uses saved command/output, wheel odometry and LiDAR evidence; see `docs/planning/AGENTS_DETAIL_RULES.md` before physical tests.

## License

- TwinPulse-owned code is Apache-2.0 (`LICENSE`); keep third-party notices unchanged. See `docs/planning/AGENTS_DETAIL_RULES.md` and `docs/RELEASE_PROVENANCE.md` before public distribution.
