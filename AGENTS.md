# TwinPulse project instructions

- Communicate with the user in Korean.
- This GitHub-connected clone is the canonical development root. Read `docs/planning/TWINPULSE_PROJECT_MEMORY.md` first; read the full `docs/planning/TWINPULSE_BASELINE.md` at handoff, then the relevant section on later turns. Read `README.md`, `docs/progress.md`, and the relevant verification record before changing a milestone.
- The approved product direction is a local React web App with a separate Isaac 3D window. The existing Isaac Sim 3D Playground/Copilot Extension remains the engine adapter and legacy UI until replacement is validated. Keep pure schemas, application/backend, Isaac integration, and future long-running workers separated.
- For stepwise work, follow the common rules and only the user-selected Step in `docs/planning/TWINPULSE_APP_MIGRATION_PLAYBOOK.md`. R0 is complete; R1 onward is not authorized by merely reading the plan. Preserve the M2-D partial status and known defects until actually fixed and verified.
- Update Baseline version/history and Project Memory together after important decisions or milestones. Do not present limited test PASS as full workflow acceptance.
- Never execute arbitrary model-generated Python or shell commands.
- Do not store API keys, tokens, authorization headers, or company credentials in this repository or logs.
- Only modify `/World/TwinPulse` prims in a user's stage unless the user explicitly approves a broader operation.
- Do not install or change ROS2, Isaac Lab, drivers, WSL, Docker, firewall, paid cloud resources, or physical AGV controls without the corresponding user approval.
- Do not mark a runtime milestone PASS without actual Isaac Sim evidence.
