# TwinPulse Quick Start

TwinPulse runs a local app and a separate Isaac Sim window on the **same Windows PC**. In the current build you import a RoomPlan USD scan, add missing objects from a photo, place a robot, ask for a mission in one sentence (Nemotron plans it via Nebius Token Factory), and run the route on a SIM TurtleBot3 or, in a supervised session, on a physical TurtleBot3 Burger. LiDAR returns the twin cannot explain are added to the twin as "not in model" objects (Review or Auto-apply, always with Undo). Measured results and known limits are in the [README](../README.md#what-is-proven-and-what-is-not).

## Choose an install path

| Where you will run TwinPulse | What to use | What that PC needs |
|---|---|---|
| Personal PC with package-network access | Clone the repository and run `Install-TwinPulse.cmd` | Isaac Sim 6.0.1 standalone, 64-bit CPython 3.12, Node.js 20.19+/22.12+/24+, Git, browser |
| Company RTX workstation without package-network access | Transfer a **prepared offline release**, then run `Reassemble-TwinPulse.cmd` and `Install-Offline.cmd` | Isaac Sim 6.0.1 standalone, 64-bit CPython 3.12, browser; no Node/Git/npm/pnpm needed on the workstation |

The company PC that can access GitHub only downloads and transfers the prepared release. The RTX workstation runs the web app, AI requests, and Isaac Sim together. VDI transfer is limited to 1 GB per operation, so release parts are at most 900,000,000 bytes each. A prepared release is **not currently published on GitHub**; cloning source alone onto the offline workstation is not an offline install.

## Online source install and restart

1. Install the prerequisites above yourself. The TwinPulse installer does not install Isaac Sim, Python, or Node.js.
2. Clone this repository on the PC that will run TwinPulse. In File Explorer, double-click `Install-TwinPulse.cmd` in the repository root. If asked, enter the Isaac Sim folder containing both `python.bat` and `isaac-sim.bat`.
3. The installer creates a repository-local `.venv`, installs locked dependencies, builds the web UI, and starts the local app and its owned Isaac window. `TWINPULSE_INSTALL_RESULT=PASS` means installation finished; it does not mean an AI request or Isaac scene build has passed.
4. On later starts, double-click `Start-TwinPulse.cmd` in the repository root. It does not rebuild. After pulling source changes, rerun `Install-TwinPulse.cmd` to rebuild.

Save any open Isaac stage before starting a new managed session. Stop TwinPulse with Ctrl+C in its launcher window; the launcher stops only the processes it started. Never paste an API key into a command line, screenshot, or repository file.

## Offline release transfer and install

A release preparer must first build from **reviewed, committed, clean source** on an approved Windows x64 PC with internet/package access, Python 3.12, Node.js, and pnpm 11.19.0. This build PC does not need a GPU or Isaac Sim. If the GitHub-connected company PC cannot access npm/PyPI, build the release in another approved environment and use that PC only to download and transfer it. Do not use `-AllowDirty` for a distributable release.

From the repository root on the approved build PC:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_offline_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\split_offline_release.ps1 -ReleaseRoot ".\artifacts\offline-release\<release-id>" -OutputRoot ".\artifacts\offline-transfer\<release-id>"
```

Replace `<release-id>` with the directory created by the first command. Transfer `transfer-manifest.json`, `Reassemble-TwinPulse.cmd`, `scripts/reassemble_offline_release.ps1`, and **every** `.partNNNN` file through the approved VDI route, one part per transfer if needed. On the RTX workstation:

1. Run `Reassemble-TwinPulse.cmd` in the transferred folder. Missing or damaged parts are rejected.
2. Run `unpacked\<release-id>\Install-Offline.cmd`. Enter the Isaac Sim root when prompted. The installer verifies file hashes and installs its local Python wheel without contacting a package index.
3. Start later from `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd`, not the copy inside the release bundle. The installed launcher defaults to **live AI mode**. The `-Offline` PowerShell option is a diagnostic mode that blocks new AI generation; it does not make new photos work without a provider.

An archive hash proves transfer integrity, not publisher identity. Compare the release digest through a trusted channel and follow your company's transfer/execution policy. Do not bypass AppLocker, WDAC, or other company controls. No API key, user input, or Isaac Sim installation is included in the release. Company-workstation install, Nebius network access, and actual Isaac Build/Run have **not** been verified yet.

## Run the loop

1. **Model keys and routing.** Open **API keys**, add your Nebius Token Factory key (stored in Windows Credential Manager, never in the repository), and under **Model routing** set the planner to `nvidia/nemotron-3-super-120b-a12b` and the photo observer to `nvidia/Nemotron-3.5-Super-VL`. A saved key does not prove a request has succeeded.
2. **Build the twin.** Start a new chat and import a RoomPlan USD scan; the scene opens in the Isaac Sim window. Add a room photo: Nemotron VL proposes objects the scan is missing, and accepted ones are placed next to the furniture they belong to. Photo-added objects are catalogue boxes sized by kind, not exact shapes.
3. **Choose how twin edits apply.** **Review** (default for a new chat) waits for Apply on each LiDAR or photo candidate; **Auto-apply** applies them as they arrive. **Undo last edit** reverts the latest change in both modes.
4. **Place the robot.** Under **Manage**, add a SIM TurtleBot3 (no hardware) or your registered physical robot, then place it on the twin where it stands, with its heading.
5. **Ask for a mission.** Type for example "Survey the room and come back". Nemotron returns a short task plan from the robot's declared capabilities; TwinPulse validates it, computes the route on the twin and shows it on a card with the model name and latency. Nothing moves until you click **Run route**. If the planner call fails, the app shows the error and offers the deterministic route as an explicit card instead of substituting it silently.
6. **Watch the twin update.** During and after the route, LiDAR returns that the twin cannot explain appear as "not in model" candidates; in Review mode click Apply or Skip. You can then ask for the next route, which is planned on the updated twin.

### Physical TurtleBot3 (supervised only)

Run `Prepare-Robot.cmd` once, start `Start-TwinPulse.cmd` (development channel), then **Connect → Prepare → Arm → Bootstrap stop** before the first route, and confirm the supervised-session checks. Stop is always one click. A proximity stop, battery cutoff at 11.1 V, output timeout and wheel-readback check run on the robot side, independent of the app and the model. The robot refuses motion when the session record cannot be written; keep a physical session under about an hour or reconnect between runs. The start pose is declared, not localized, so check the robot's real position against the twin before each run.

## If something fails

- **API key saved, but no plan or photo result:** Check the model routing, the key, and that the PC can reach `api.tokenfactory.nebius.com`. A saved key is not a successful AI request. Do not repeat an uncertain paid request without checking its outcome.
- **Session expired:** Reopen TwinPulse from the secure link provided by its launcher. Failed state-changing actions are not automatically retried.
- **Isaac disconnected or unresponsive:** Check the owned launcher and Isaac window. Do not force-close an unrelated user Isaac session.
- **Route refused or safety stop:** Keep the reported error code and trace ID. Do not bypass validation or the robot-side guards; re-arm and run a bootstrap stop before the next physical route.
- **Company offline install blocked:** Verify every transfer part, the Python/Isaac prerequisites, and company execution policy. Do not disable security controls to make the installer run.

For detailed Korean company-install notes see [Company PC install](COMPANY_PC_INSTALL.md). For verified and unverified milestones see [Progress](progress.md). Local checks and actual Isaac acceptance are different; only report an actual Isaac pass with the corresponding run/capture evidence.
