# TwinPulse Quick Start

TwinPulse runs a local app and a separate Isaac Sim window on the **same Windows PC**. In the current build you import a RoomPlan USD scan, add missing objects from a photo, place a robot, ask for a mission in one sentence (Nemotron plans it via Nebius Token Factory), and run the route on a SIM TurtleBot3 or, in a supervised session, on a physical TurtleBot3 Burger. LiDAR returns the twin cannot explain are added to the twin as "not in model" objects (Review or Auto-apply, always with Undo). Measured results and known limits are in the [README](../README.md#what-is-proven-and-what-is-not).

## Choose an install path

| Where you will run TwinPulse | What to use | What that PC needs |
|---|---|---|
| Company PC, or any PC without developer tools | The **Windows EXE ZIP**: extract it, run `TwinPulse\Install-TwinPulse.cmd`, start `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd` ([steps](WINDOWS_EXE_QUICKSTART.md)) | Isaac Sim 6.0.1 standalone only; Python, the web UI, the desktop window and the robot assets are inside the ZIP |
| Personal or developer PC with package-network access | Clone the repository and run its `Install-TwinPulse.cmd` | Isaac Sim 6.0.1 standalone, 64-bit CPython 3.12, Node.js 22.12+, Git |

Get the ZIP and its `SHA256SUMS.txt` from the release page or file you were given. Every file is checked automatically at install; there is no manual hash step ([what is checked, and when](WINDOWS_EXE_QUICKSTART.md#what-is-checked-and-when)). The `Install-TwinPulse.cmd` in a source checkout (or a "Source code" archive) is the developer install, not the company-PC one. Follow your company's transfer and execution policy; do not bypass AppLocker, WDAC, or other company controls. Company-PC install, Nebius network access and actual Isaac Build/Run on a company PC have **not** been verified with the EXE ZIP yet.

## Online source install and restart

1. Install the prerequisites above yourself. The TwinPulse installer does not install Isaac Sim, Python, or Node.js.
2. Clone this repository on the PC that will run TwinPulse. In File Explorer, double-click `Install-TwinPulse.cmd` in the repository root. If asked, enter the Isaac Sim folder containing both `python.bat` and `isaac-sim.bat`.
3. The installer creates a repository-local `.venv`, installs locked dependencies, builds the web UI, and starts the local app and its owned Isaac window. `TWINPULSE_INSTALL_RESULT=PASS` means installation finished; it does not mean an AI request or Isaac scene build has passed.
4. On later starts, double-click `Start-TwinPulse.cmd` in the repository root. It does not rebuild. After pulling source changes, rerun `Install-TwinPulse.cmd` to rebuild. If an installed release exists under `%LOCALAPPDATA%\TwinPulse\installed`, this file starts that release instead; `Start-TwinPulse-Development.cmd` always runs the source.

Save any open Isaac stage before starting a new managed session. Stop TwinPulse with Ctrl+C in its launcher window; the launcher stops only the processes it started. Never paste an API key into a command line, screenshot, or repository file.

## Offline venv release (deprecated)

The prepared offline release (`Install-Offline.cmd`, `Reassemble-TwinPulse.cmd`, `tp-<git12>` bundles) is deprecated: it ships no desktop window, needs a separate CPython 3.12 and no longer fits its own 1,000-file limit. Use the [Windows EXE ZIP](WINDOWS_EXE_QUICKSTART.md) instead; earlier EXE ZIPs were about 190 MB, so one file normally fits the 1 GB VDI transfer limit. To move a PC from an old offline install, see [Moving from an old offline install](WINDOWS_EXE_QUICKSTART.md#moving-from-an-old-offline-install). The historical steps remain in [Company PC install](COMPANY_PC_INSTALL.md) section 6.

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

- **API key saved, but no plan or photo result:** Check the model routing, the key, and that the PC can reach `api.tokenfactory.nebius.com`. A saved key is not a successful AI request. Do not repeat an uncertain paid request without checking its outcome. If the error shows a web page title, a company filter answered the `TwinPulse/<version>` User-Agent; see [Network](WINDOWS_EXE_QUICKSTART.md#network).
- **Session expired:** Reopen TwinPulse from the secure link provided by its launcher. Failed state-changing actions are not automatically retried.
- **Isaac disconnected or unresponsive:** Check the owned launcher and Isaac window. Do not force-close an unrelated user Isaac session.
- **Route refused or safety stop:** Keep the reported error code and trace ID. Do not bypass validation or the robot-side guards; re-arm and run a bootstrap stop before the next physical route.
- **No desktop window:** a current source checkout without the desktop window opens Chrome or Edge instead and prints `TWINPULSE_UI_HOST=browser reason=desktop_host_not_built`; with neither browser it stops with `ui_host_unavailable` before starting anything. Rerun `Install-TwinPulse.cmd` to install the desktop window. An old offline release keeps its old code and still stops with `DESKTOP_HOST_NOT_BUILT`; move that PC to the EXE ZIP.
- **Company PC install or start blocked:** See [If something fails](WINDOWS_EXE_QUICKSTART.md#if-something-fails) for the EXE ZIP. Do not disable security controls to make the installer run.

For company networks, the PC check script and older Korean install notes see [Company PC install](COMPANY_PC_INSTALL.md). For verified and unverified milestones see [Progress](progress.md). Local checks and actual Isaac acceptance are different; only report an actual Isaac pass with the corresponding run/capture evidence.
