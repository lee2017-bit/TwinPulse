# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One-command R6 launcher for the local TwinPulse App and Isaac window."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ProcessManagerError, TwinPulseProcessManager  # noqa: E402
from twinpulse_app.process_manager import PROJECT_SWITCH_REQUESTED, RESTART_REQUESTED  # noqa: E402


def _browser(configured: str | None) -> Path | None:
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    return next((item for item in candidates if item is not None and item.is_file()), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isaac-root", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--browser", type=str)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Disable provider generation; run local Isaac only")
    parser.add_argument("--project-id", default="default", help="Portable local project name; default keeps legacy project")
    parser.add_argument("--ready-timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime"))
    state_dir = args.state_dir or local_app_data / "TwinPulse" / "runtime"
    from twinpulse_app.desktop_settings import read_settings
    configuration = read_settings(state_dir)
    saved_path = ROOT / '.runtime' / 'isaac-root.txt'
    isaac_root = args.isaac_root or Path(configuration.get('isaac_root') or
        (saved_path.read_text(encoding='utf-8').strip() if saved_path.is_file() else r'C:\isaacsim'))
    # Each explicit UI retry uses a fresh launch identity, backend session and
    # engine child. The prior manager is fully stopped in finally first.
    retry_count = 0
    selected_project = args.project_id
    while True:
        manager = TwinPulseProcessManager(
            repo_root=ROOT,
            state_dir=state_dir,
            python_executable=Path(sys.executable),
            isaac_python=isaac_root / "python.bat",
            browser_executable=_browser(args.browser),
            port=args.port,
            headless=args.headless,
            ready_timeout_s=args.ready_timeout_s,
            offline_mode=args.offline,
            project_id=selected_project,
            retry_remaining=3 - retry_count,
            defer_engine_validation=bool(getattr(sys, 'frozen', False)),
        )
        try:
            result = manager.start(open_browser=not args.no_browser)
            if getattr(result, 'reused', False):
                print(f"TWINPULSE_APP_REOPENED launch_id={result.launch_id} ui={result.ui_url} "
                      f"phase={result.phase}; existing App and Isaac kept running", flush=True)
                return 0
            print(
                f"TWINPULSE_APP_READY launch_id={result.launch_id} ui={result.ui_url} "
                f"backend_pid={result.backend_pid} "
                f"engine_pid={result.engine_pid} stage={result.stage_epoch}",
                flush=True,
            )
            print("TwinPulse is running. Press Ctrl+C to stop only the processes owned by this launcher.", flush=True)
            outcome = manager.monitor()
            if outcome == PROJECT_SWITCH_REQUESTED and manager.requested_project_id is not None:
                selected_project = manager.requested_project_id
                retry_count = 0
                print(f"Closing the current project before opening {selected_project} in a new session.", flush=True)
                continue
            return outcome
        except KeyboardInterrupt:
            return 0
        except ProcessManagerError as error:
            if error.code == "startup_cancelled":
                print("TwinPulse startup cancelled. Only this launch was stopped.", flush=True)
                return 0
            print(f"TWINPULSE_LAUNCH_ERROR code={error.code} message={error}", file=sys.stderr, flush=True)
            if getattr(error,'execution_id',None):
                print(f"TWINPULSE_EXECUTION_ID={error.execution_id} diagnostics={error.diagnostics_path}",
                      file=sys.stderr,flush=True)
            if manager.diagnostics_active:
                if retry_count < 3:
                    print("Diagnostics remain in the browser. Press Ctrl+C to close or request an explicit retry there.", flush=True)
                else:
                    print("Retry limit reached. Save diagnostics, then close this launch before a new start.", flush=True)
                try:
                    diagnostic_outcome = manager.monitor_diagnostics()
                    if diagnostic_outcome == 0:
                        # An explicit Exit from the diagnostic UI is not a
                        # failed startup attempt needing another native alert.
                        return 0
                    if diagnostic_outcome == RESTART_REQUESTED and retry_count < 3:
                        retry_count += 1
                        print("Stopping the failed launch before a fresh retry window opens.", flush=True)
                        continue
                except KeyboardInterrupt:
                    return 0
            return 1
        finally:
            manager.stop()


if __name__ == "__main__":
    raise SystemExit(main())
