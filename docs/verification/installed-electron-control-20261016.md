# Installed Electron control — 2026-10-16

## Verdict

**Installed renderer control route established; whole product acceptance PARTIAL.**

The same installed `Start-TwinPulse.cmd` was invoked by the execution tool with a per-launch loopback debugging option. Playwright attached to the supervisor-created, installed Electron BrowserWindow. No substitute Chrome window/context, bootstrap/cookie injection, mocked response, product mutation API or paid generation was used. Explorer double-click, Windows foreground/IME/clipboard/file picker/title-bar X and native Isaac interaction remain NOT_RUN.

[Single private offline report with six embedded actual screenshots](../../outputs/desktop-app-20261016/electron-control/report.html). [Reusable procedure and official sources](../DESKTOP_UI_TESTING.md).

## Actual attempts and finding

| Trial | Installed release | UI result | Strict whole result |
|---|---|---|---|
| smoke01 | build10 / c632dbe311a4 | Home/Isaac PASS; Robots 503 | FAIL, retained |
| smoke02 | build10 / c632dbe311a4 | 5/6; Robots 503 | FAIL, retained |
| smoke03 | build11 / a7160361d64d | 6/6 menu/input/Twin steps | FAIL: one GET runtime 409; retained |
| exit01 / exit02 | build10 / build11 | Visible Exit button, 2.829 / 2.651s | PASS within shutdown scope |

The packaged frozen entry sets `TWINPULSE_SIM_ONLY=1`; the former backend omitted all WorkspaceDevices, including the local registry. The earlier direct-manager web diagnostic did not follow that frozen entry and therefore missed `robot_registry_unavailable`. Fixed by exposing metadata-only WorkspaceDevices in SIM packages while creating no physical diagnostics/readiness/controller, physical store migration or device lease. Real installed11 Robots click loads the registry. No robot discovery/connect/movement was requested.

The final runtime409 response body and subsequent GET200 were not captured. Static review points to stale-project `project_context_changed` fencing; the client dedicated requery branch instead checks `context_changed`. This mismatch is a concrete next investigation, not proof of the exact observed response. Do not ignore all409s or revise the recorded FAIL.

## Build / lifecycle evidence

- build11 release `20261015T215053Z-a7160361d64d`.
- source SHA256 `a7160361d64d269fb938eacedfb48671f4de52712906217cc6579e8a60658d29`.
- ZIP SHA256 `ef370a5a22f384b78abe87f74d4a17c403383af5dcf6e4da60f7d9ce26c7b447`.
- Test launch `b2e1ee8e9b004d3e8908e752573f2c36`, execution `86fa32bdd76f464481de3aff91616f33`. Existing preload version response identifies actual Electron44.7.2/Chromium152.0.7977.149 and the installed release/launch.
- Repeated ordinary Start reused the same owner/backend/engine/DesktopPID. Visible Exit yielded matching `owned_processes_stopped:true` cleanup receipt; lock, owned processes and19222 listener disappeared.
- Normal restart without the test option: launch `7becaa39d82a4673b94c8447e26cf0c6`, execution `2e87e479ae564a729b103ed1115d4880`; authenticated actual Isaac ready. Owner14148/backend21284/engine19820/Desktop25364. No19222 listener. Left running normally for the user.
- `debug11.json`, `repeated11.json`, `normal11.json`, original trial JSON/screenshots and before/preservation evidence are under the report folder. Original trial10 remains separate; no other build's generation results are merged.

## Preservation / limits

1,503 original project/settings files have identical individual SHA values;83 provider ledgers unchanged. Two empty UI-created test chats remain (`chat_mva2mt7z_fccb76a9`, `chat_mva2rt69_ea542f35`). No original deletion or private-data publication. Added model HTTP0/USD0; past UNKNOWN-inclusive protected totalUSD6.8918946 against approvedUSD20 unchanged. This is not an invoice.

Python23PASS and Node/PowerShell syntax checks are supplementary. No new dependency, robot/Cloud/OpenAI call, commit/push or public deployment. Generation/repair/edit/Undo/save/reopen/photo quality and model-harness effectiveness remain NOT_RUN on final11. Historical v486 layout/critic failure, local read3s warning, native control problem and same-room sensor/physical readiness remain unresolved.

Next: instrument non-secret409 code/stage/recovery, fix contract mismatch if reproduced, then use this actual installed UI path for paid generation and recovery acceptance. Keep the debugger off in ordinary startup.
