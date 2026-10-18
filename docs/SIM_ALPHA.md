# TwinPulse SIM alpha

TwinPulse turns text, photographs and combined input into an editable, approximate Isaac scene. It shows generation progress, supported partial previews and unresolved work, then accepts natural-language edits, Undo and saved reopening. It is not a photogrammetry tool or a guarantee of complete image reconstruction.

## Supported release shape

- Windows x64 one-folder ZIP with an unsigned `TwinPulse.exe` and per-user manual installer/start wrapper.
- Separately installed compatible Isaac Sim and GPU environment. The release does not bundle Isaac, drivers, credentials or model weights.
- Nebius DeepSeek V4.1 Flash observation and Nemotron 3 Super design/repair. Provider API keys stay in Windows Credential Manager.
- SIM-only: no physical robot commands or paid Cloud deployment. Normal runtime does not create per-action dollar approval or stale-price gates; provider/account controls and configured token/request/repair limits remain separate.

See [EXE quickstart](WINDOWS_EXE_QUICKSTART.md) and [build instructions](WINDOWS_EXE_BUILD.md). General-use acceptance requires the downloaded executable and ordinary visible New chat/Attach/Send/Create workflow, not just unit tests or API calls. A clean source build and an independent clean-PC run are different checks.

## Updates and feedback

Use the same installed Start entry after updating. Epoch 1 currently retains existing project, attachment, conversation, edit and checkpoint formats without conversion. Incompatible format epochs are refused rather than silently opened by an old executable. See the quickstart for interrupted-install and rollback limits.

Report the build ID, affected execution ID, input mode and exact click sequence with the GitHub bug template. Redacted diagnostics are optional and local until you review and submit them yourself. Never attach keys, private original photos or the entire runtime directory to a public issue. Feature requests should explain the desired user task.

Known limits must accompany each prerelease. Missing/uncertain objects and estimates remain explicit; prepared/rendered object counts are not photo-quality scores. Finite SIM routes stop at their destination and are not continuous autonomous exploration. Unsupported furniture may use coarse proxies. Native OS clipboard, installer interaction and independent hardware coverage must be stated from actual acceptance, not inferred.

TwinPulse-owned code is Apache-2.0. The ROBOTIS simulation assets and bundled dependencies retain their original notices. Private test inputs and local reports are not included in the release. No public release is implied by this document; final reviewed source/ZIP hashes and the acceptance summary identify what was actually published.
