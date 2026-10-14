# TwinPulse

TwinPulse is a local chat-first application for creating and editing approximate 3D twins in Isaac Sim from text, photographs or both. Allowlisted LLM plans are compiled locally; arbitrary model-written Python/shell commands are not executed.

This branch prepares **0.1.0-alpha.1, SIM only**. It does not promise complete photo reconstruction, independent clean-PC qualification or physical robot readiness. Exact actual acceptance and known limits accompany each candidate; unit-test counts are not user-flow evidence.

## Windows app

Use the complete executable ZIP attached to a release, not GitHub's automatic Source code ZIP. Extract the whole folder, run `Install-TwinPulse.cmd`, then the stable `%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd`. Portable `TwinPulse.exe` is supported. A compatible Windows x64 GPU/Isaac installation is required separately; Python/Node development tools are not required to run the EXE.

Select the installed Isaac folder if prompted, add your Nebius API key in settings and wait for the authenticated connection indicator. New chat creates a separate project. Attach a photo or describe a room, then Create Twin. Partial results and unresolved work remain explicit. Natural-language edits use review/apply, Undo and saved reopening. Run simulation starts only a reviewed finite SIM route; Stop and Reset are separate. Closing the browser does not stop the owned App/Isaac; use Exit TwinPulse.

Default roles are Nebius DeepSeek V4.1 Flash observation and NVIDIA Nemotron 3 Super design/repair. Configured finite token/request/time/repair limits are separate from provider billing. Normal use has no per-action dollar approval or expired-price gate.

[Quickstart and manual updates](docs/WINDOWS_EXE_QUICKSTART.md) · [Alpha scope](docs/SIM_ALPHA.md) · [Build source](docs/WINDOWS_EXE_BUILD.md).

## Feedback and updates

Report build ID, execution ID and actual click sequence using the issue template. Redacted diagnostics are optional; review before sharing. Never publish keys, private originals or the runtime directory. Existing conversations, attachments, edits and checkpoints stay outside versioned executable folders. Same-epoch updates preserve formats; incompatible epochs are refused. Automatic updating and arbitrary future-schema downgrade are not included.

Known limits include coarse furniture proxies, uncertain dimensions and photo-relative placement/refinement failures. Object counts are not image-fidelity scores. Unresolved items are not silently deleted to manufacture success. Physical commands, paid Cloud and telemetry upload are outside this SIM release.

## Development and provenance

Source remains one codebase; tags identify immutable source/ZIP versions. Web dist, EXEs and ZIPs are generated artifacts. Reviewed ROBOTIS USD, source hashes and original notices are in `assets/simulation/turtlebot3_burger`. Isaac/Kit runtime/importers, drivers, keys and weights are not bundled. This selected source tree omits private development history, but ancestor history still requires review before a private repository is made public.

TwinPulse-owned code uses the unmodified [Apache License 2.0](LICENSE). Preserve applicable copyright/LICENSE/NOTICE when redistributing reused code; third parties retain original notices. Generated scenes/reports do not automatically inherit the code license.

For material design inspiration in independent work, voluntarily record TwinPulse, https://github.com/lee2017-bit/TwinPulse and the actual influence. This adds no license condition. Use truthful wording: “Includes code from TwinPulse”, “Design inspired by TwinPulse”, or “Based on TwinPulse”. Merely reading files or AI-training inclusion is not itself a contribution or attribution duty. [Licensing](docs/LICENSING.md) · [Third-party notices](THIRD_PARTY_NOTICES.md).
