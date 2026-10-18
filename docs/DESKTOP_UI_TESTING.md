# Installed Electron UI testing

TwinPulse supports a per-launch, loopback-only renderer debugging option. It is off during ordinary startup and is not a saved user setting. Normal frozen startup discards inherited port settings; use the explicit `Start-TwinPulse-Test.cmd` / `--automation-test` entry instead. The same installed `desktop/TwinPulseDesktop.exe` and Python supervisor are used with the existing authenticated App/Isaac connection. The app's Tests menu runs the bundled basic Playwright checks or opens its local report; full SIM generation and physical qualification remain separate.

Electron documents [Playwright automation](https://www.electronjs.org/docs/latest/tutorial/automated-testing) and its [remote-debugging-port switch](https://www.electronjs.org/docs/latest/api/command-line-switches#--remote-debugging-portport). This project attaches to the supervisor-created window with [Playwright connectOverCDP](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp). Direct `_electron.launch()` would replace the existing supervisor launch chain, so it is not used for this acceptance path. CDP supports fewer features than Playwright's native protocol; each required interaction needs actual verification.

## Run locally

Use the existing repository dependencies. First close any running TwinPulse using its visible **Exit TwinPulse** button and wait for normal shutdown. Then, from the canonical repository:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_installed_electron_ui_test.ps1
node scripts\verify_installed_electron_ui.mjs --cdp http://127.0.0.1:19222 --output outputs\electron-ui-new-run
node scripts\verify_installed_electron_ui.mjs --cdp http://127.0.0.1:19222 --output outputs\electron-ui-new-run-exit --exit
```

Each output directory must be new; failed attempts are preserved. The helper invokes the same user-facing installed Test Start entry. The explicit mode selects a free loopback port in19222–19231 for this launch only; use the returned endpoint in the Node commands. The helper checks the launch mode record, actual127.0.0.1 listener and installed Electron child/launcher ownership. A running launcher is not taken over. Never copy a previous endpoint into a new session without these checks.

The first Node command attaches to the existing renderer, reads desktop version/launch identity, clicks menus, types into Library search and a new chat, and captures the rendered results. It creates an empty chat and clears its unsent draft. It does not submit a generation or change model routes. The second command clicks the visible **Exit TwinPulse** control and waits for the window to close. Check the matching `cleanup-receipt.json` and disappearance of the listener; then use the ordinary installed Start again without the test environment variable.

The debugger has control of this local app session. Keep it enabled only for testing and do not expose/forward its port. No Node inspector, relaxed renderer sandbox, altered product authentication, persistent debug setting, cookie injection or mocked API response is required. Test clients must not print bootstrap fragments, credentials or headers.

## What this proves

Clicks, keyboard events and screenshots come from the installed Electron BrowserWindow and its actual backend. The driver does not open a Chrome tab, create a substitute browser context, navigate to a manually authenticated URL, or call product mutation APIs.

This is renderer-level interaction through CDP. It does not qualify Windows foreground handling, native title-bar X, OS clipboard/file-picker behavior, installer double-click, or native Isaac UI. Invoking the identical Start file through an execution tool is recorded separately from an Explorer double-click. A rendered Isaac connection indicator and an actual engine receipt do not establish generation or photo quality. Paid generation, repair, Undo and save/reopen need their own actual UI journeys.

## SIM package boundary

SIM alpha exposes local robot metadata and the registration guide. Its physical diagnostics, readiness and movement controllers remain absent. Merely opening Robots performs no robot transport or discovery. Discovery requires its explicit UI action, and connection/movement qualification is separate. This avoids the former packaged-only `503 robot_registry_unavailable` caused by omitting the entire metadata service.
