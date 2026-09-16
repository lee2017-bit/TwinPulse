# R3 Application service and common-contract verification

- Date: 2026-09-16 KST
- Result: **PASS for the tested local R3 scope**
- Canonical root: `C:\Users\jaewo\Documents\TwinPulse`
- Full-run artifact: `artifacts/runs/20260916-152550` (local and intentionally git-ignored)
- Paid provider calls: none
- React/loopback bridge/physical control: not implemented or run

## Delivered boundary

R3 extracts generation, immutable input selection, validated-draft promotion, active-project persistence and Build eligibility into `twinpulse_app.ApplicationService`. The service returns typed records/events and imports no UI or Isaac modules. The existing Isaac Extension uses that service, while USD/PhysX compilation and runtime callbacks remain inside the Extension.

`twinpulse_core.engine_contracts` defines schema `1.0` records for `CommandEnvelope`, `CommandReceipt` and `SimulationSnapshot`, plus the pure `SimulationPort` protocol. The records bind commands to a project, engine session, stage epoch, control lease and expected applied revision. A successful Build receipt must report the requested applied revision.

Project and provider-settings JSON stores are atomic and contain no credential. The Windows Credential Manager target remains `TwinPulse/OpenAIResponsesAPI`. Legacy non-secret carb provider settings are imported only when the app settings file does not yet exist; later writes are app-owned and are not synchronized back to carb.

The architecture and local bootstrap/session policy are recorded in `docs/decisions/0003-application-engine-and-local-auth-contract.md`. That ADR constrains R4 but does not claim that transport exists.

## Acceptance evidence

The finite R3 suite passed **9/9**:

- general Python imports `twinpulse_core`, `twinpulse_provider` and `twinpulse_app` without loading `omni`, `pxr` or `carb`;
- package metadata declares the pure core → provider → app dependency direction;
- generation, input-artifact snapshot, project persistence, restore and Build-candidate checks;
- late superseded response rejection;
- error/cancel preservation of the previous validated draft while blocking Build for a changed input;
- fake simulation-port dispatch and mismatched Build-receipt rejection;
- one-time non-secret settings migration and absence of serialized API-key fields;
- corrupt project rejection without overwriting the source;
- strict contract round-trip and unknown-field rejection.

The combined pure run passed Core **24/24**, Provider **13/13**, R1 integration **9/9** and R3 **9/9**. The full actual-Isaac runner then passed the same suites plus M1/M2/R2 runtime checks and the R1 legacy Extension smoke. Its manifest records:

```text
status=PASS
app=PASS_R3
isaac=PASS_M1_M2_R2_R3_LEGACY
run_id=20260916-152550
```

The actual-Isaac R3 claim is deliberately limited: the existing Extension enabled, preserved the prompt/input-revision and stale-Build rules, restored prior draft behavior and shut down cleanly while using the application service. No visible React UI, loopback transport, new paid generation or manual screenshot acceptance was part of R3.

## Commands

```powershell
python scripts\verify_r3_application.py
.\scripts\verify_twinpulse.ps1 -SkipIsaac
.\scripts\verify_twinpulse.ps1 -IsaacRoot C:\isaacsim

python -m venv tmp-r3-wheel-env
.\tmp-r3-wheel-env\Scripts\python.exe -m pip install setuptools==84.0.0 wheel==0.48.0
.\tmp-r3-wheel-env\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation . -w tmp-r3-wheels
.\tmp-r3-wheel-env\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation packages\twinpulse_provider -w tmp-r3-wheels
.\tmp-r3-wheel-env\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation packages\twinpulse_app -w tmp-r3-wheels
python -m venv tmp-r3-install-env
.\tmp-r3-install-env\Scripts\python.exe -m pip install --no-index --find-links tmp-r3-wheels twinpulse-app==0.1.0
.\tmp-r3-install-env\Scripts\python.exe -m pip check
```

## Wheel and clean-install verification

The first wheel attempt exposed that the available Python environments did not contain `setuptools`. With user approval, packaging tools were installed only in the git-ignored `tmp-r3-wheel-env` virtual environment (`setuptools 84.0.0`, `wheel 0.48.0`). No system or Isaac Python package was changed.

All three wheels then built successfully without build isolation and were installed from the local wheel directory into a second clean, git-ignored virtual environment. Installing only `twinpulse-app==0.1.0` resolved and installed the exact `twinpulse-provider==0.1.0` and `twinpulse-core==0.1.0` wheels. `pip check` reported `No broken requirements found`; all three packages imported and no `omni`, `pxr` or `carb` module was loaded.

```text
twinpulse_app-0.1.0-py3-none-any.whl      sha256 4e49c01f5a3f078febeeca9c57f5c82ea3832181617b934288e197a02bd31d86
twinpulse_core-0.1.0-py3-none-any.whl     sha256 8d8a1a5e792df17551b0274a4d790954b2cf504d972ebca8c83bd8027455b88b
twinpulse_provider-0.1.0-py3-none-any.whl sha256 441be05c688c6f90427f69b26796e1d915238ad4264b3623a5ad974eaab5c44c
```

This closes the local R3 package-build and clean-install check. Publishing the wheels, installing them on the company PC, and producing a locked release artifact remain separate future actions.

## Scope boundary and next gate

R3 does not create an HTTP server, bridge worker, browser session, React UI, multi-project format, Replay, ROS2/Nav2, cloud deployment or physical-robot command path. The next selectable step is **R4: loopback API plus actual Isaac bridge**, and it requires a separate user instruction.
