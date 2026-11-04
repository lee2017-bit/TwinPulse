# TwinPulse Windows EXE

This one-folder package is how company PCs install TwinPulse. It already contains Python, the web UI, the desktop window, the Isaac extension and the robot assets. Only **NVIDIA Isaac Sim 6.0.1** (standalone) is installed separately, on a compatible Windows x64/GPU system; Isaac, GPU drivers and API keys are not included. The package is unsigned. Physical robot controls exist only in a development-channel build; the default sim-alpha package is simulation only, and a separately declared read-only robot build can offer explicit connection observations. Check the capability message in Robots.

## Install

1. Get `TwinPulse-Windows-x64-<version>-<build>.zip` and `SHA256SUMS.txt` from the release page or file you were given. Nothing else needs to be downloaded.
2. Optional: compare the ZIP's SHA-256 with the line in `SHA256SUMS.txt` (case does not matter): `Get-FileHash <zip> -Algorithm SHA256` in PowerShell, or `certutil -hashfile <zip> SHA256` in Command Prompt.
3. Right-click the ZIP → **Properties** → tick **Unblock** if it is shown → **OK**.
4. Right-click the ZIP → **Extract All** to a short, empty folder such as `C:\TP`. The default folder under Downloads makes every path about 13 characters longer than the installed one, and Windows limits paths to 259 characters.
5. Double-click `C:\TP\TwinPulse\Install-TwinPulse.cmd` and wait for the confirmation message. It checks every file and installs for this Windows user under `%LOCALAPPDATA%\TwinPulse\installed`. No network is used.
6. Start with `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd` (paste it into Win+R, or make your own shortcut; none is created). It starts the installed `TwinPulse.exe` directly; no PowerShell is needed.

Use the `Install-TwinPulse.cmd` inside the extracted `TwinPulse` folder. A source checkout has a file with the same name: that one is the developer install and needs Python, Node.js and package downloads. If Windows or company security still blocks the package, ask IT; do not disable security controls.

**Isaac Sim** is found automatically in `C:\isaacsim`, `D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64`, `C:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64` or `D:\isaacsim`. Otherwise a folder picker asks once: choose the folder that contains `python.bat`. The folder is saved for later starts.

**The first start can take up to 10 minutes** while Isaac initializes. The App window opens first and shows the current Isaac phase with elapsed seconds; later starts are usually faster. If Isaac is not ready after 600 s, the message names the last phase.

## Use

1. Wait for the authenticated connection indicator before using 3D commands.
2. Use New chat to create a separate conversation in the same app/address. Run the same installed Start entry to focus/reopen the existing app without another backend or Isaac instance. Portable use of `TwinPulse.exe` from the extracted folder is also supported.
3. Use **Exit TwinPulse** to stop the App and its owned Isaac engine normally. The independent window's close button requests the same normal shutdown; it is not a hide-to-tray action. Stop a simulation or response first if the app asks you to. If only the renderer crashes, the manager does not silently abandon ongoing work: use the same Start entry to reopen it. The explicit diagnostic browser mode is different; closing that browser only closes its view.

## What is checked, and when

| When | What is checked | Your part |
|---|---|---|
| Build PC | Locked build tools and versions, the Burger robot files against their reviewed digests, and that no installed path passes 259 characters | None. Strict, on the builder only: the build stops |
| Download | The ZIP's SHA-256 against `SHA256SUMS.txt` | Optional (step 2) |
| Install | Size and SHA-256 of every file against `windows-release-manifest.json` inside the ZIP, for the extracted folder before any install code runs and again for the installed copy | None. Automatic |
| Each start | Every listed file is present with its recorded size. Child processes (backend, workers) only read the manifest | None. Quick |
| On demand | The full SHA-256 check of every file | Run `Start-TwinPulse.cmd --inspect-package` (or `TwinPulse.exe --inspect-package` in a package folder), or reinstall |
| Isaac Sim | Its version: any 6.0.1 build is accepted; another version gets a warning, not a block | None |
| SIM robot | The Burger robot files against the digests the build checked; a mismatch names the file | None |

At install and start, `desktop.ini`, `Thumbs.db` and `.DS_Store` are ignored unless the manifest lists them; any other unexpected file stops the check and is named. `--inspect-package` does not start the App. A problem opens a message naming the file; a pass writes `"status": "verified"` to a new log in `%LOCALAPPDATA%\TwinPulse\runtime\desktop-logs`. SHA-256 identifies bytes; it is not a publisher signature.

## Network

Install uses no network, but AI generation does; `Start-TwinPulse.cmd --offline` is a diagnostic mode that runs local Isaac only and blocks new AI generation. Apart from a robot you connect on the local network, the App contacts only the AI providers you set up, over HTTPS: `api.tokenfactory.nebius.com` (Nebius Token Factory) and, if you route a model to OpenAI, `api.openai.com`. Every request carries the User-Agent `TwinPulse/<version>`; TwinPulse never disguises itself as a browser. If a company filter answers instead of the provider, the App shows the HTTP status and the block page's title, not a key error. During key setup, `provider_blocked_page`, `provider_http_error` and `provider_unreachable` tell a filter page, another HTTP error and no connection apart. Ask IT to allow those hosts for that User-Agent. TwinPulse listens on 127.0.0.1 only, and calls between its own processes ignore proxy settings. Isaac Sim itself may also try NVIDIA's online extension registry; the extensions TwinPulse needs must already be in the local Isaac install.

## If something fails

- **Install stops with `WINDOWS_PACKAGE_FILE_MISMATCH` or `WINDOWS_PACKAGE_UNMANIFESTED_FILE`:** the message names the file. Extract the ZIP again into a new, empty short folder and add nothing to it. If it repeats, check the ZIP's SHA-256 (step 2).
- **`EXIT_TWINPULSE_BEFORE_INSTALL`:** TwinPulse is still running; exit it first.
- **Isaac is not ready after 600 s:** the message names the last phase. Keep `engine.log` from `%LOCALAPPDATA%\TwinPulse\runtime\launches\<launch>`; it keeps its output even when the engine is stopped. If the TwinPulse extension does not start, the error lists the declared Isaac extensions that are not enabled. TwinPulse starts Isaac without the Windows user-site Python folder; do not copy NumPy or SciPy folders into Isaac.
- **A provider error shows a web page title:** a company filter answered; see Network. Provider errors show the HTTP status and a short reason. OpenAI planner requests are checked against OpenAI's strict schema rules before they are sent.
- **Check this PC:** copy `scripts/twinpulse_company_pc_check.py` from the TwinPulse source (or ask whoever gave you the ZIP) and run `py -3 twinpulse_company_pc_check.py` with any Python 3.10+, or `<Isaac folder>\python.bat twinpulse_company_pc_check.py`. It is read-only, writes a report to your Desktop and never prints keys or prompts. By default it sends unauthenticated test requests to `api.tokenfactory.nebius.com` and `api.openai.com` with the Python default and the TwinPulse User-Agent; `--no-network` skips them. Review the report before sharing it.
- **Anything else:** open Diagnostics in the App, or read `%LOCALAPPDATA%\TwinPulse\runtime\desktop-logs`.

## Moving from an old offline install

For a PC that used the old offline release (`Install-Offline.cmd`, a `releases\tp-<git12>` folder):

1. Exit TwinPulse.
2. Install this ZIP as above. The installer reads the old `active-release.json` with or without a BOM (the offline installer wrote one), keeps a byte-for-byte copy and does not stop on an unreadable old pointer, so nothing needs to be renamed. A leftover `launcher.lock` whose process ID now belongs to another program is moved to `runtime\stale-launch-records`.
3. Start from `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd`. No `--ready-timeout-s` argument is needed.
4. Keep the old launch folders in `%LOCALAPPDATA%\TwinPulse\runtime\launches`: they are the original failure records. Archive them if you clean up; do not delete them. The old `releases\tp-...` folder can stay; it does not conflict.

Projects, settings and API-key references stay in `%LOCALAPPDATA%\TwinPulse\runtime` and Windows Credential Manager.

## Optional automation checks in the same app

Normal Start discards inherited testing-port settings and opens no automation port. For a test session, exit normally and use **Start-TwinPulse-Test.cmd** beside the installed Start (or the portable EXE). It starts the same package with `--automation-test`, a loopback-only port and a visible TEST MODE badge. A running session is never silently changed between normal and test modes; close it normally first. The next normal launch is debug-off.

Open **Tests → Run basic checks** while Isaac is connected and the app is idle. A bundled, version-pinned Playwright worker clicks the actual installed window: Robots, Library typing/results and Twin pane. No extra Node/Chrome installation, paid generation, network discovery or SSH is needed. Do not use the app controls during this short check. **Tests → Open check report** opens the local report and screenshots; these may contain conversation/device information, so review before sharing. Nothing is uploaded automatically. A basic PASS is not full generation, native OS input or physical robot qualification. The debugging port grants local programs broad control of this app; keep testing mode limited to the test session and never expose/forward the port. Robot preparation and motion gates remain unchanged.

API keys holds provider/model routing and editable model-specific harness instructions. Existing saved Legacy routes are not silently rewritten. Save routing explicitly to select a profile; custom/new-model instructions remain compatibility-unverified until tested. Schema, geometry checks and robot authority are not editable through a prompt profile.

Robots starts empty on a fresh installation. Search shows network service advertisements observed during that search, with a last-search time and a maximum 30-second validity (shorter advertisement TTLs expire sooner). It is not a continuous power/reachability or identity check. Saved robots remain registered even when off; no response means not observed, not proven offline. Remembered Bluetooth devices/local ports are separate OS inventory, never current network search results. A robot must advertise a supported service and network discovery must be allowed; simply enabling SSH is not sufficient to appear. Register/select the intended robot explicitly and run Check PC preparation. Search does not automatically connect or change the saved endpoint. Plain SIM builds stop at local preparation. Read-only robot builds additionally offer Check connection: this explicit action runs bounded SSH health reads, existing ROS topic observations and a reviewed board-read check. It does not deploy software, start a sensor driver, collect a survey or enable a motor. Unknown hardware requires an adapter review and calibration; TwinPulse does not infer a safe motor protocol from a Bluetooth or USB name. A successful read-only result is not motion readiness.

The local address is remembered across restarts. If another program occupies that port, TwinPulse selects and remembers a bounded alternative. No public network listener or local DNS configuration is required. Provider API calls are made by the local backend over HTTPS.

Existing API-key references, conversations, scenes and incomplete work remain in `%LOCALAPPDATA%\TwinPulse\runtime`; key material remains in Windows Credential Manager. Moving the extracted package does not move or remove these user records. A different release cannot take control of a live launch from another installation: exit the old launch normally first.

## Manual updates and recovery

Exit TwinPulse normally, extract the entire next ZIP and run its `Install-TwinPulse.cmd`. Installation refuses a live launch; it does not force-stop another instance. It retains the previous executable pointer, rewrites the installed Start entries for the new release and leaves projects, original attachments, incomplete checkpoints, edits and Windows Credential Manager entries in their existing locations. Launch the same installed Start entry afterwards.

Reinstalling the same ZIP checks the installed copy again. If that copy is damaged, the install stops and names the file: exit TwinPulse, rename that build's folder under `%LOCALAPPDATA%\TwinPulse\installed\releases` (keep it as a record) and run `Install-TwinPulse.cmd` again.

This alpha writes data epoch 1 without conversion. A release declaring an incompatible epoch is refused before switching. An interrupted same-epoch install can be rerun from the identical intact package. Do not manually reset data or edit active-release.json. Automatic rollback is limited to packages declaring the same supported epoch; arbitrary future-format downgrade is not provided. No automatic update download, forced update, telemetry upload or background paid inference is performed.

For a bug report, open Diagnostics and record App version/build ID, the affected execution ID and your actual click sequence. Export redacted diagnostics only if you want to share them, and review the file yourself. Original prompts, photos, responses and private paths are not required for a public issue. Do not upload keys or a whole runtime directory.

This unsigned package is not an assertion of final photo accuracy, clean-PC acceptance, physical robot readiness or public release clearance. Preserve the included Apache-2.0 LICENSE/NOTICE and component-original notices. Do not disable OS security to run a blocked package. See the release acceptance record for exact tests and remaining work.

A failed generation may preserve only a resume checkpoint and static preview, not an accepted saved scene. Object counts are not proof of image fidelity; dimensions without measurements remain estimated. The first alpha is for compatible-system testers, not a claim that any PC works with only an API key.
