# Operating TwinPulse with Codex, Claude Code or another local agent

An agent with local desktop-control tools or a Playwright/CDP client can operate TwinPulse's **actual installed Electron window**. This is a tool-agnostic UI path, not a dedicated Codex/Claude integration, TwinPulse MCP server or general-purpose robot CLI. A chat model without access to your PC cannot operate the app merely by reading this guide. A separate Claude Code installation/tool configuration has not been independently qualified.

Use the same visible controls as a person. Do not substitute another Chrome tab, injected state/cookies, saved model replies or direct product mutation requests for a UI test.

## Choose the interaction path

| Path | Entry | Scope |
| --- | --- | --- |
| Normal desktop use | `Start-TwinPulse.cmd` | Debugging off. A suitable native computer-use tool can target the actual TwinPulse window. |
| Built-in basic checks | `Start-TwinPulse-Test.cmd` → **Tests** | Bundled Playwright checks: Home/Isaac, Robots metadata, Library search and Twin visibility. No external Node installation is needed for these checks. |
| Agent-driven UI work | `Start-TwinPulse-Test.cmd` + local CDP client | Click, type, inspect and capture the same installed BrowserWindow. External scripts need an available Node/Playwright environment. |

Test mode uses the same installed EXE, Python supervisor, authenticated backend and Isaac connection. **It is not a sandbox, separate user profile or automatic SIM-only mode.** Saved data is real; submitting generation can call the configured paid provider. Physical capabilities depend on the installed package and need separate authorization and live checks.

Normal startup does not expose the debugger. Test mode is per launch, not a persistent user setting. Never expose/forward its loopback port, disable authentication/sandboxing, or make it an always-on production control service.

## Start and identify the correct window

1. Save work and close TwinPulse using **Exit** or normal window close. Wait for shutdown; do not kill unrelated processes or delete a launcher lock.
2. Open `Start-TwinPulse-Test.cmd` from the checkout or installed folder. An agent can invoke the identical entry with its execution tool, but must not label that an Explorer double-click.
3. Confirm the visible **TEST MODE** indication and actual app/Isaac readiness. A process or debugger port alone is not readiness.
4. Attach to this launch's installed Electron window. Do not create a new browser/context or navigate to a copied bootstrap URL. Never print bootstrap fragments, credentials, cookies or authorization headers.

From a source checkout with the existing repository dependencies, this helper invokes the same Test Start and checks the current launch record, loopback listener, executable and launcher-child ownership:

```powershell
# Run from the TwinPulse repository root, with no running TwinPulse owner.
$tpLaunchJson = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_installed_electron_ui_test.ps1
if ($LASTEXITCODE -ne 0) { throw 'Test Start failed; inspect its retained launch diagnostics.' }
$tpLaunch = $tpLaunchJson | ConvertFrom-Json
$tpEndpoint = $tpLaunch.cdp_endpoint
```

Use the returned endpoint. Test startup chooses an available loopback port in **19222–19231**; `19222` is not guaranteed. Revalidate after every launch. The debugger endpoint is neither the app HTTP URL nor the robot address. Do not guess ports or attach to another Electron app.

The helper refusing an existing owner is intentional: close that session normally instead of starting a duplicate. If startup fails or candidate ports are occupied, preserve the launch ID and failure; do not widen the listener to the network.

## Existing small UI smoke test

Using the endpoint above and the repository's existing Node/Playwright dependencies:

```powershell
$tpEvidence = Join-Path 'outputs' ('agent-ui-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
node scripts\verify_installed_electron_ui.mjs --cdp $tpEndpoint --output $tpEvidence
```

The script opens menus, searches Library, opens model settings without changing routes, creates an empty chat, types/clears an **unsent** input sample, and toggles Twin. It saves screenshots and `result.json` in a new evidence directory. It is not a read-only dry run: the empty chat remains. It does not submit generation, discover/connect hardware or prove photo quality. Failed attempts must be retained.

If source dependencies are unavailable, do not install tooling or download browsers automatically. Use the bundled **Tests** menu, an already available compatible client, or arrange development dependencies separately. The ordinary installed app does not require external Node/Playwright.

Finish using the visible **Exit** control; the driver can click it too:

```powershell
node scripts\verify_installed_electron_ui.mjs --cdp $tpEndpoint --output ($tpEvidence + '-exit') --exit
```

Wait for the matching launch's cleanup receipt, owned-process exit and listener removal before another Start. Closing a CDP client alone does not shut down TwinPulse. A Windows parent PID alone is not process ownership because PIDs can be reused.

The built-in **Tests** menu runs four basic checks, not this external smoke script or a full acceptance campaign. Its reports are under `%LOCALAPPDATA%\TwinPulse\runtime\desktop-window\self-tests\<run_id>\report.html`; open them through **Tests**. Screenshots/reports may contain private project text or device details and are not uploaded automatically.

## Copyable instruction for a local coding agent

Provide the repository path, allowed task/data, any provider budget and whether hardware is in scope. This default excludes paid generation and physical robots:

```text
Operate TwinPulse through its actual installed Electron window.
Read AGENTS.md, current Project Memory and docs/DESKTOP_UI_TESTING.md.
Preserve existing projects, settings and failed attempts.

Scope: basic UI smoke only. Do not submit paid generation, discover/connect
a physical robot, run hardware Prepare, enable physical LiDAR or send motion.
Do not read/print/transmit credentials, install software or publish data.

Close any running TwinPulse normally, then use Start-TwinPulse-Test.cmd.
Use the repository helper's returned CDP endpoint and launch ID; do not assume
port 19222. Attach only to the existing installed BrowserWindow and verify
its desktop/launch identity and actual readiness.

Use visible controls with semantic locators or a supported native tool.
Do not launch another Chrome/context, inject state/cookies, call product
mutation APIs, mock replies or intercept normal UI requests.

Run the basic checks and save failures/screenshots to a fresh output folder.
Exit through the visible control and confirm cleanup before restarting.
Report exactly what ran; mark unsupported native/OS steps NOT_RUN.
Basic checks and request acceptance are not full generation or robot PASS.
```

For a larger authorized task, replace the scope explicitly. “Automate TwinPulse” is not approval for every upload, provider expense, installation or hardware action.

## Extending the task to an actual SIM journey

After input transmission and any provider expense are authorized:

1. **New chat** → real scene brief/Attach → **Send/Create**. Observe actual generation events and rendering; record original input/SHA. A restored scene is not a fresh generation.
2. **Robots/Manage** → **Add SIM robot**. Read model, name and starting pose before Add; verify the matching chat entry. Registration alone is not connection or displayed placement.
3. Explicitly **Connect** and **Prepare** the selected SIM robot. Inspect model/status in Twin. A saved physical robot in the list is not permission to connect it.
4. Test hold/release, **Stop**, and LiDAR on/off. For chat/panel commands distinguish accepted, running and measured terminal outcome. “Go to the nearest bed” is a scene-derived **SIM** destination, not qualified physical navigation.
5. Save, exit normally and reopen. Check settings/history, edited/Undo revisions and that movement authority did not resume automatically.

Prefer accessible names to coordinates. The compact visible **Exit** currently has accessible name `Exit TwinPulse`; inspect the current window rather than guessing renamed controls. Use one controlling client during a recorded journey: another client can change session-wide download handling and confound the test.

Normal acceptance must run without `page.route`/Fetch interception, fixed replies or hidden state changes. Deliberate delay/disconnection tests belong in separately labeled fault windows after releasing controls and confirming Stop. Do not lengthen freshness, input, output or geometry limits to turn a failure green.

A continuous recording should show Home **before** New chat, then actual input/generation/registration. Renderer recording does not cover Windows startup, Explorer, native Isaac or the real robot. Preserve original times and failures; distinguish a private fault-test video from a shareable demo.

The repository's renderer recorders now include a recording-only arrow, faint amber halo and short recent-press ring from actual trusted mouse events. The transparent annotation does not intercept clicks or change product state and is removed when recording stops. It is not the captured OS cursor or a proof that a button is still held. Recorder metadata labels the annotation explicitly. Existing videos without original pointer positions cannot be given a trustworthy reconstructed cursor path; record a new demonstration instead.

## Evidence and troubleshooting

Record installed release/source SHA, `launch_id`, project/chat/conversation identity and scene revision; also `robot_id`, `operation_id` and tested request IDs. These are linked identities, **not one interchangeable ID**. Keep actual input/actions, requested versus applied/terminal results, screenshots, errors, elapsed time and provider usage/unknown cost.

Use **Diagnostics** for execution records and **Operation logs** for robot detail/export. Startup evidence is under `%LOCALAPPDATA%\TwinPulse\runtime\launches\<launch_id>`. Operation journals are under `%LOCALAPPDATA%\TwinPulse\runtime\projects\<project_id>\robot-operations\`. Prefer app export; never edit journals to manufacture success. If an outcome is unknown, inspect IDs before retrying: replay can duplicate work.

Label the exact path: normal/native versus Test/CDP, execution-tool Start versus Explorer, DOM attachment versus OS clipboard/file picker. If native capture/input cannot be performed, report that limitation instead of replacing the UI action with a product API call.

## Native limits and physical hardware

CDP covers the renderer, not Windows foreground behavior, title-bar X, Explorer, OS paste/file pickers or native Isaac. Use an appropriate native tool and retain separate results. Native capture/control can fail even when renderer automation works. This project's installed-Electron route has been exercised; compatibility with another agent depends on its actual tools, not its model name.

Opening Robots or passing basic checks is not physical readiness/authorization. A SIM-only package can omit physical controllers; inspect installed capabilities. Hardware-capable packages still require explicit selection, connection and live validation. App **Prepare** owns source-bound robot build/check/readback: do not bypass it with ad-hoc SSH commands or install a PC ROS SDK merely to drive the UI.

Physical motion needs a separately authorized supervised session and live safeguards. SIM destinations, saved-sensor replay, a green connection light or a software gate do not prove live sensors, braking, navigation or world alignment.

## Implementation references

The current path uses Playwright `chromium.connectOverCDP` on the supervisor-created BrowserWindow, not `_electron.launch()` or a substitute Chrome. See `apps/twinpulse-desktop/main.mjs`, `automation.cjs`, `self-test-runner.cjs`, and the two helper scripts above. Current acceptance is recorded in Project Memory; older release notes are historical, not guarantees for another package or PC.
