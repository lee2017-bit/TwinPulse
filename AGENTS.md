# TwinPulse project instructions

- Communicate with the user in Korean.
- Read `README.md`, `docs/progress.md`, and the relevant verification record before changing a milestone.
- TwinPulse is an Isaac Sim 3D Playground/Copilot Extension. Keep pure schemas, Isaac integration, and future long-running workers separated.
- Never execute arbitrary model-generated Python or shell commands.
- Do not store API keys, tokens, authorization headers, or company credentials in this repository or logs.
- Only modify `/World/TwinPulse` prims in a user's stage unless the user explicitly approves a broader operation.
- Do not install or change ROS2, Isaac Lab, drivers, WSL, Docker, firewall, paid cloud resources, or physical AGV controls without the corresponding user approval.
- Do not mark a runtime milestone PASS without actual Isaac Sim evidence.
