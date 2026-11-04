# Build the TwinPulse Windows EXE

Source stays in the existing GitHub repository. The executable ZIP is a generated release artifact and the company-PC package: everything except Isaac Sim is inside it. This Windows x64 one-folder package uses the existing React interface in a separate Electron host, the Python application manager, and a separately installed Isaac runtime. The Python manager remains the backend/Isaac lifecycle authority.

The strict locks and checks on this page run only on the build PC. A company PC never repeats them; its installer checks every file against the manifest inside the ZIP (see "What is checked, and when" in `WINDOWS_EXE_QUICKSTART.md`).

Use Windows x64 CPython 3.12 and a project-local build environment. Do not install build dependencies into Isaac or the application's environment. The exact build wheels are pinned by SHA256 in `config/python-build-requirements.lock`.

```powershell
py -3.12 -m venv .build-venv
.build-venv\Scripts\python.exe -m pip install --require-hashes -r config\python-build-requirements.lock
```

Building needs **Node.js 22.12+**: electron 44.7.2 and @electron/packager 20.3.0 require it, so Node 20.19 is not enough. Install the web dependencies from the repository's lock with pnpm 11.19.0 (the web package's `packageManager`); the builder always rebuilds `apps/twinpulse-web/dist` with those locked tools (`tsc -b`, `vite build`). Install desktop build dependencies from `apps/twinpulse-desktop/package-lock.json` using `npm ci` in that directory. If lifecycle scripts were disabled, run its pinned `node node_modules/electron/install.js` there before packaging; do not rely on an empty Electron package being executable. This stays project-local. The EXE builder copies the resulting web files and packages Electron from the frozen desktop source snapshot; it does not run npm or download anything at application startup.

```powershell
.build-venv\Scripts\python.exe scripts\build_windows_exe.py --channel sim-alpha --output-dir artifacts\windows-exe\NEW_BUILD_ID
```

Both executables and the Electron window carry `apps/twinpulse-desktop/icon.ico` (wire cube + pulse, chosen 2026-10-27; vector source `icon.svg`). The `.ico` is packed by `scripts/make_app_icon.py <square PNG render of icon.svg, >=256 px> apps/twinpulse-desktop/icon.ico` (Pillow only: 16-128 px as 32-bit BMP entries, 256 px as PNG); `package.mjs` passes it to `@electron/packager`, which stamps `TwinPulseDesktop.exe` with its pure-JS resource editor, and `packaging/windows/TwinPulse.spec` stamps `TwinPulse.exe`. Changing any desktop source, the icon included, makes `--reuse-desktop-from` refuse with `DESKTOP_REUSE_SOURCE_CHANGED`; the first build after such a change must package the desktop host again.

## What the build checks

The build stops on the build PC when any of these fails:

- A Verify-Sprint PASS receipt for the exact HEAD on a clean tree, less than 24 hours old (`--skip-sprint-gate` is for emergencies only).
- Exact PyInstaller 6.22.3, Pillow 12.3.0, Electron 44.7.2 and Playwright core 1.63.0.
- The built web UI, the Burger assets and their ROBOTIS notice must exist.
- The nine Burger USD files must equal the reviewed public digests; `BUILD_BURGER_ASSET_NOT_PUBLIC` names the files that differ. A wrong asset byte fails here instead of on a company PC.
- No package path may pass the Windows 259-character limit once installed under `%LOCALAPPDATA%\TwinPulse\installed\releases\<build>` for a 20-character user name; `BUILD_INSTALL_PATH_TOO_LONG` names the longest path.

The output directory must be new. It contains the immutable staging source snapshot, PyInstaller diagnostics, `dist/TwinPulse/TwinPulse.exe`, the `desktop/TwinPulseDesktop.exe` host inside that package, the complete one-folder ZIP `TwinPulse-Windows-x64-<release_version>-<build_id>.zip` (top folder `TwinPulse/`) and `SHA256SUMS.txt`; `--package-only` skips the ZIP. Python source, Electron host source/lock, desktop entry, spec, version metadata, resources and original Python/Electron/Chromium notices are hash-bound in `windows-release-manifest.json`; analysis uses the staging snapshot rather than live source files. Build failures remain in their original output directories. App version, package build/source SHA, Electron runtime and external Isaac version are separate identities.

Use the entire extracted folder outside the source checkout for acceptance. Confirm repeated startup, same address, current Isaac image, UI shutdown and saved data. `--inspect-package` hashes every file against the manifest (a normal start only checks presence and size, and child processes only read the manifest); `--internal-role backend --help` can check child stdout without provider or robot actions. These are supplementary checks, not full user acceptance.

`Install-TwinPulse.cmd` invokes `TwinPulse.exe --install`, hashes every file of the extracted package and again of the staged copy, copies the verified package into versioned per-user releases and retains the previous active pointer. Exit TwinPulse normally first. `--install --quiet` is the unattended equivalent. Installation writes `Start-TwinPulse.cmd` and `Start-TwinPulse-Test.cmd`, which start the active release's `TwinPulse.exe` directly (no PowerShell) and pass arguments through; `start-installed.ps1` stays as a fallback. No desktop shortcut is created. The shared kernel maintenance lock serializes install/start; same-epoch data is not converted, while incompatible epochs are refused. Dedicated Setup.exe, generic format migrations and uninstall remain future work.

The clean-clone asset input is `assets/simulation/turtlebot3_burger`: nine hash-pinned USD layers, original ROBOTIS license and machine-readable conversion/provenance record. Historical `artifacts/robot-models` are not required in a clean clone and must not be silently substituted into a public package. No Isaac runtime/importer binaries or model weights are bundled.

Installing over an old offline (Python venv) install reads its `active-release.json` with or without a BOM, keeps a byte-for-byte copy and replaces the installed Start entries; an unparseable old pointer does not stop the install. A leftover `launcher.lock` whose PID now belongs to another process is moved to `runtime\stale-launch-records`. An active release from another folder must be closed before switching packages. User data and key references remain in their existing OS locations.

## Distribute

Hand over the ZIP and its `SHA256SUMS.txt` together, as one release or one file transfer; a company PC needs nothing else except Isaac Sim 6.0.1. Pick the channel deliberately: `sim-alpha` (the default) is simulation only, `development` keeps the physical robot controls, and `robot-observation` adds read-only robot observation. GitHub should track reviewed source, tests, docs, spec and hash locks. Generated EXE/ZIP files go to a release; a public one only after the content review in `RELEASE_PROVENANCE.md`. Local dirty builds identify the exact source snapshot and are not equivalent to an approved public release. Do not publish private outputs, user projects, photos, raw captures, key material or converted assets without the required content-specific review.
