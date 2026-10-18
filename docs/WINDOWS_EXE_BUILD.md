# Build the TwinPulse Windows EXE

Source stays in the existing GitHub repository. The executable ZIP is a generated release artifact. This Windows x64 one-folder package uses the existing React interface in a separate Electron host, the Python application manager, and a separately installed Isaac runtime. The Python manager remains the backend/Isaac lifecycle authority.

Use Windows x64 CPython 3.12 and a project-local build environment. Do not install build dependencies into Isaac or the application's environment. The exact build wheels are pinned by SHA256 in `config/python-build-requirements.lock`.

```powershell
py -3.12 -m venv .build-venv
.build-venv\Scripts\python.exe -m pip install --require-hashes -r config\python-build-requirements.lock
```

Build the web distribution with the repository's locked Node/pnpm toolchain first. Install desktop build dependencies from `apps/twinpulse-desktop/package-lock.json` using `npm ci` in that directory. If lifecycle scripts were disabled, run its pinned `node node_modules/electron/install.js` there before packaging; do not rely on an empty Electron package being executable. This stays project-local. The EXE builder verifies/copies the resulting web files and packages Electron from the frozen desktop source snapshot; it does not run npm or download anything at application startup. A local development build may reuse the already-qualified `apps/twinpulse-web/dist`, but its hash must match the recorded build manifest.

```powershell
.build-venv\Scripts\python.exe scripts\build_windows_exe.py --channel sim-alpha --output-dir artifacts\windows-exe\NEW_BUILD_ID
```

The output directory must be new. It contains the immutable staging source snapshot, PyInstaller diagnostics, `dist/TwinPulse/TwinPulse.exe`, the `desktop/TwinPulseDesktop.exe` host inside that package, the complete one-folder ZIP and SHA256SUMS. Python source, Electron host source/lock, desktop entry, spec, version metadata, resources and original Python/Electron/Chromium notices are hash-bound; analysis uses the staging snapshot rather than live source files. Build failures remain in their original output directories. App version, package build/source SHA, Electron runtime and external Isaac version are separate identities.

Use the entire extracted folder outside the source checkout for acceptance. Confirm repeated startup, same address, current Isaac image, UI shutdown and saved data. `--inspect-package` performs a package-only check; `--internal-role backend --help` can check child stdout without provider or robot actions. These are supplementary checks, not full user acceptance.

`Install-TwinPulse.cmd` invokes `TwinPulse.exe --install`, copies the verified package into versioned per-user releases and retains the previous active pointer. Exit TwinPulse normally first. `--install --quiet` is the unattended equivalent. Installation writes the stable per-user Start wrapper but no desktop shortcut. The shared kernel maintenance lock serializes install/start; same-epoch data is not converted, while incompatible epochs are refused. Dedicated Setup.exe, generic format migrations and uninstall remain future work.

The clean-clone asset input is `assets/simulation/turtlebot3_burger`: nine hash-pinned USD layers, original ROBOTIS license and machine-readable conversion/provenance record. Missing assets or built web files fail the build. Historical `artifacts/robot-models` are not required in a clean clone and must not be silently substituted into a public package. No Isaac runtime/importer binaries or model weights are bundled.

The existing installed CMD supports both its original Python release pointer and the new EXE pointer. An active release from another folder must be closed before switching packages. User data and key references remain in their existing OS locations.

GitHub should track reviewed source, tests, docs, spec and hash locks. Generated EXE/ZIP belong in Releases after public-content review. Local dirty builds identify the exact source snapshot and are not equivalent to an approved public release. Do not publish private outputs, user projects, photos, raw captures, key material or converted assets without the required content-specific review.
