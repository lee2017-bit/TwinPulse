# TwinPulse Windows EXE

This is an unsigned Windows x64 SIM-only alpha candidate with the browser interface. It includes the App's Python runtime, built web interface and the reviewed ROBOTIS Burger simulation assets. Install Isaac Sim separately on a compatible Windows/GPU system; Isaac, GPU drivers and API credentials are not bundled. Physical robot controls are not available in this alpha.

1. Extract the complete ZIP. Keep `TwinPulse.exe`, `_internal` and the manifest together.
2. Run `Install-TwinPulse.cmd` to install per user, then `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd`. The same start entry follows the active installed release. Portable use of `TwinPulse.exe` is also supported. If needed, select the installed Isaac folder containing `python.bat`.
3. The browser opens before Isaac finishes preparing. Wait for the authenticated connection indicator before using 3D commands.
4. Use New chat to create a separate conversation. Closing the browser only closes the view; run the same EXE to reopen the live App.
5. Use **Exit TwinPulse** to stop the App and its owned Isaac engine normally. Stop a simulation or response first if the menu asks you to.

The local address is remembered across restarts. If another program occupies that port, TwinPulse selects and remembers a bounded alternative. No public network listener or local DNS configuration is required. Provider API calls are made by the local backend over HTTPS.

Existing API-key references, conversations, scenes and incomplete work remain in `%LOCALAPPDATA%\TwinPulse\runtime`; key material remains in Windows Credential Manager. Moving the extracted package does not move or remove these user records. A different release cannot take control of a live launch from another installation: exit the old launch normally first.

## Manual updates and recovery

Exit TwinPulse normally, extract the entire next ZIP and run its `Install-TwinPulse.cmd`. Installation refuses a live launch; it does not force-stop another instance. It retains the previous executable pointer and leaves projects, original attachments, incomplete checkpoints, edits and Windows Credential Manager entries in their existing locations. Launch the same installed Start entry afterwards.

This alpha writes data epoch 1 without conversion. A release declaring an incompatible epoch is refused before switching. An interrupted same-epoch install can be rerun from the identical intact package. Do not manually reset data or edit active-release.json. Automatic rollback is limited to packages declaring the same supported epoch; arbitrary future-format downgrade is not provided. No automatic update download, forced update, telemetry upload or background paid inference is performed.

For a bug report, open Diagnostics and record App version/build ID, the affected execution ID and your actual click sequence. Export redacted diagnostics only if you want to share them, and review the file yourself. Original prompts, photos, responses and private paths are not required for a public issue. Do not upload keys or a whole runtime directory.

This unsigned candidate is not an assertion of final photo accuracy, clean-PC acceptance, physical robot readiness or public release clearance. Preserve the included Apache-2.0 LICENSE/NOTICE and component-original notices. SHA256 identifies bytes; it is not a publisher signature. Do not disable OS security to run a blocked package. See the release acceptance record for exact tests and remaining work.

A failed generation may preserve only a resume checkpoint and static preview, not an accepted saved scene. Object counts are not proof of image fidelity; dimensions without measurements remain estimated. The first alpha is for compatible-system testers, not a claim that any PC works with only an API key.
