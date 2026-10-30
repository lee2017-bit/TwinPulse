# TwinPulse Quick Start

TwinPulse runs a local app and a separate Isaac Sim window on the **same Windows PC**. The current build (the one in the demo video) imports an iPhone RoomPlan USD as the twin, places a SIM or physical TurtleBot3 Burger on it at a declared start pose, turns "Survey the room and come back" into a Nemotron plan and a route on the twin, drives it, and offers LiDAR returns the twin cannot explain as reviewable twin edits. A physical run is a supervised session (see [Run the current demo](#run-the-current-demo) below). The start pose is declared, not measured, and the robot drives on wheel odometry; there is no SLAM or twin-based relocalization yet. The sections after the install steps also describe the earlier photo-to-draft workflow; some labels there may differ in the current build.

## Run the current demo

1. Start TwinPulse (`Start-TwinPulse.cmd`). Open **API keys**, add your Nebius Token Factory key, and under **Model routing** set the planner to `nvidia/nemotron-3-super-120b-a12b` and the photo observer to `nvidia/Nemotron-3.5-Super-VL`.
2. In a new chat open **Import space**, choose your RoomPlan USD, check it, import it and **Show Twin**. After every app restart use **Rebuild Twin in Isaac**.
3. Optional: in Import space open **Added obstacles**, choose an **Obstacle reference photo**, tick **Allow photo analysis** and analyze it. Add the candidates you agree with one by one.
4. In the Digital Twin pane open **Robots → Manage → Add SIM robot**, or select your registered physical robot, and set its position and heading on the Twin.
5. Select the robot, then **Connect** and **Prepare**. For a physical robot run `Prepare-Robot.cmd` once beforehand, and in the session gate confirm supervision → **Arm** → **Bootstrap stop** (a fixed 0.03 m/s forward for at most 0.6 s) before the first route. Arm expires; after a reconnect, Prepare comes first again.
6. Type **Survey the room and come back**. Check the route card (model, latency, stops, length), then **Run route**. **Stop** is always one click, and robot-side guards (proximity stop, battery cutoff, output timeout) act on their own.
7. After the route, the LiDAR card lists objects that are not in the twin. Apply or Skip each one. **Twin edits** can be set to Review (default) or Auto-apply; **Undo last edit** reverts the latest change.

Measured runs, including the failed ones, are in [the repeatability record](analysis/TWINPULSE_REPEATABILITY_2026-10-28.md).

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

## Create and inspect a draft (earlier photo-to-draft workflow)

1. In the local web app, open **AI settings**. Select the provider preset and enter that PC's API key. The key is stored in Windows Credential Manager and is not copied from another PC. A saved key does not prove the provider is reachable or that a paid AI request succeeded. Check the provider's cost and permissions before creating a draft.
2. In **Add Photo**, choose a PNG/JPG/WEBP site photo or drawing (up to 10 MiB). Add **Instructions (optional)** if needed. Photo observation (`nvidia/Nemotron-3.5-Super-VL` on Nebius Token Factory, selected under **API keys → Model routing** as in the demo build) requires exactly one image. A supported provider may accept instructions alone. No input means **Create Draft** stays disabled.
3. Select **Create Draft**. Review the generated tool/object list and the approximate-model warning. A photo does not establish exact scale, hidden geometry, or equipment locations. For accuracy, supply verified dimensions or scans when supported.
4. In **Review Twin**, confirm the current draft version and select the enabled Build action. A validated draft is not yet a built scene. The optional **Nebius · site scene proposal (v2)** profile requires a matching v2-capable Isaac adapter and builds site geometry only; it does not install a robot or task. Switching provider profiles requires re-entering the API key under the current credential-binding policy. Wait for the engine result and check the separate Isaac 3D window. An isolated deterministic v2 fixture passed a headless Isaac Build/Reset, but the full browser path, interactive view, and paid/live v2 request have not yet been verified.
5. In **Simulate**, use **Run**, **Pause**, **Reset**, and **Show 3D View** only for a matching built v1 robot-task scene when the app permits the action. Run is blocked for v2 site scenes. The web status illustration is not the live 3D view. A safety stop may require Reset.

The current simulator's supported robot task is constrained; it is not general obstacle-avoiding navigation. The scene may differ materially from the photo. Do not claim a successful build, safe route, or better path from draft validation alone.

## If something fails

- **API key saved, but no draft:** Check that an image/instructions were selected, the provider profile is correct, and the workstation can reach the provider. A saved key is not a successful AI request. Do not repeat an uncertain paid request without checking its outcome.
- **Session expired:** Reopen TwinPulse from the secure link provided by its launcher. Failed state-changing actions are not automatically retried.
- **Isaac disconnected or unresponsive:** Check the owned launcher and Isaac window. Do not force-close an unrelated user Isaac session.
- **Build blocked or safety stop:** Keep the reported error code and non-secret diagnostics. Do not substitute a sample scene or bypass validation; use Reset when the app requires it.
- **Company offline install blocked:** Verify every transfer part, the Python/Isaac prerequisites, and company execution policy. Do not disable security controls to make the installer run.

For detailed Korean company-install notes see [Company PC install](COMPANY_PC_INSTALL.md). For verified and unverified milestones see [Progress](progress.md). Local checks and actual Isaac acceptance are different; only report an actual Isaac pass with the corresponding run/capture evidence.
