# TwinPulse project instructions

- Communicate with the user in Korean.
- This GitHub-connected clone is the canonical development root. Read `docs/planning/TWINPULSE_PROJECT_MEMORY.md` first; read the full `docs/planning/TWINPULSE_BASELINE.md` at handoff, then the relevant section on later turns. Read `README.md`, `docs/progress.md`, and the relevant verification record before changing a milestone.
- The latest approved product direction (2026-10-05) is a local React chat-first App with a collapsible real-time Isaac 3D pane and SIM/REAL demo branches. See `docs/planning/TWINPULSE_CHAT_DRIVEN_DEMO_SOL_IMPLEMENTATION_PLAN_2026-10-05.md`. This is a requested implementation target, not a completed milestone; the current separate Isaac window remains a diagnostic/legacy path until the embedded viewer is validated. The existing Isaac Sim 3D Playground/Copilot Extension remains the engine adapter. Keep pure schemas, application/backend, Isaac integration, and long-running workers separated.
- For stepwise work, follow the common rules and only the user-selected Step in `docs/planning/TWINPULSE_APP_MIGRATION_PLAYBOOK.md`. R0 is complete; R1 onward is not authorized by merely reading the plan. Preserve the M2-D partial status and known defects until actually fixed and verified.
- Update Baseline version/history and Project Memory together after important decisions or milestones. Do not present limited test PASS as full workflow acceptance.
- Never execute arbitrary model-generated Python or shell commands.
- Do not store API keys, tokens, authorization headers, or company credentials in this repository or logs.
- Only modify `/World/TwinPulse` prims in a user's stage unless the user explicitly approves a broader operation.
- Do not install or change ROS2, Isaac Lab, drivers, WSL, Docker, firewall, paid cloud resources, or physical AGV controls without the corresponding user approval.
- Do not mark a runtime milestone PASS without actual Isaac Sim evidence.
- User-facing acceptance must follow the user's actual start entry point and visible click/typing flow with Computer Use or the equivalent browser tools. Do not replace these steps with direct product API calls, preselected test-only projects, or fixed model replies and then claim ordinary-user acceptance. Unit/API/fault tests remain supplementary and must be labeled. Include repeated launch, closed-browser reopening, and normal shutdown/restart for launcher changes. If Computer Use prohibits CMD/terminal automation, run the identical entry file with the execution tool and verify the opened App through visible UI actions; state this limitation.

## Robot focused-test completion gate

- The active goal is preparing the ordinary installed App for one supervised powered-robot test session, not merely finishing the newest subfeature. Follow `docs/verification/ROBOT_FOCUSED_TEST_ACCEPTANCE_2026-10-18.md`; keep each required journey linked to evidence from the final installed release.
- A known blocking software failure or a missing required journey prevents a ready-for-powered-test verdict. Fix and rerun the original failing condition; a shorter movement, different goal, older release or split continuation is not its replacement. Preserve every failure.
- Distinguish software-path readiness from actual hardware outcomes. Robot OFF may leave physical acquisition/motion NOT_RUN, but it cannot excuse an unimplemented App action, circular prerequisites or a failed SIM journey. This rule never authorizes physical operation.
- Before a readiness handoff, run the evidence gate and inspect its result. Instructions or a reviewer saying PASS cannot replace the gate's current-release evidence. If a reviewer is authorized, give it the original goal, acceptance list and raw failures, not only a scoped success summary. Only actual permission/budget/tool limits justify a blocked handoff; do not silently shrink the goal.

## Build retention and disk-pressure checks

- Do not preserve every historical executable, installer ZIP and `work`/`staging`/`dist` copy as if it were irreplaceable test evidence. Preserve current, the last actually passing rollback for its stated scope, and explicitly needed reproduction builds. Keep source identities, manifests, original failure logs, user photos/projects/sensor data and cost ledgers separately.
- Before another full build/install or recorded Isaac session, measure free space and existing generated build/install accumulation. Investigate project-owned copies before asking the user to keep clearing unrelated files. Logical file sizes and actual allocated/free-space changes are different measurements.
- Deletion needs an exact reviewed absolute-path inventory and applicable user authorization. Protect active/pinned/running releases and raw data; reject reparse/out-of-scope paths. Verify required remote preservation first when the user requests backup-before-cleanup. Do not touch pagefile, Docker/WSL, Isaac installations, credentials or user data as a build cleanup shortcut.
- `scripts/prune_preserved_builds.ps1` is the date-specific reviewed maintenance path with dry-run/Apply, not proof that the installed executable already implements automatic retention. Update its pins/proof only after reviewing new acceptance and preserve original cleanup receipts.

## License and honest provenance

- TwinPulse-owned code uses the unmodified Apache-2.0 license in `LICENSE`. Preserve applicable copyright/license/NOTICE information and prominent notices of modifications when redistributing reused code; keep third-party licenses and notices separate and unchanged.
- For material design reference in an independently implemented project, we voluntarily request a provenance entry naming TwinPulse, `https://github.com/lee2017-bit/TwinPulse`, and the actual referenced design. This is not an additional Apache-2.0 condition.
- Record only evidenced contributions: "Includes code from TwinPulse", "Design inspired by TwinPulse", or "Based on TwinPulse", as appropriate. Merely reading files or inclusion in AI training does not by itself require attribution in every subsequent output. Do not invent reuse or influence.
- Do not impose screen branding, source-disclosure requirements or AI-use restrictions. Generated scenes/reports and third-party assets do not automatically inherit this code license. See `docs/LICENSING.md` and `THIRD_PARTY_NOTICES.md`.
- Before a requested public distribution, follow `docs/RELEASE_PROVENANCE.md` and review the actual hash-bound file list. The offline inventory/local build is not rights/privacy or publication approval. Preserve pinned/raw assets; do not silently delete unreviewed components to manufacture a passing but incomplete package. This is release-readiness guidance, not an added Apache-2.0 condition.
