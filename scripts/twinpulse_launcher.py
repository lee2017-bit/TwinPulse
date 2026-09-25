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
    parser.add_argument("--isaac-root", type=Path, default=Path(r"C:\isaacsim"))
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--browser", type=str)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--ready-timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime"))
    state_dir = args.state_dir or local_app_data / "TwinPulse" / "runtime"
    manager = TwinPulseProcessManager(
        repo_root=ROOT,
        state_dir=state_dir,
        python_executable=Path(sys.executable),
        isaac_python=args.isaac_root / "python.bat",
        browser_executable=_browser(args.browser),
        port=args.port,
        headless=args.headless,
        ready_timeout_s=args.ready_timeout_s,
    )
    try:
        result = manager.start(open_browser=not args.no_browser)
        print(
            f"TWINPULSE_APP_READY launch_id={result.launch_id} ui={result.ui_url} "
            f"backend_pid={result.backend_pid} "
            f"engine_pid={result.engine_pid} stage={result.stage_epoch}",
            flush=True,
        )
        print("TwinPulse is running. Press Ctrl+C to stop only the processes owned by this launcher.", flush=True)
        return manager.monitor()
    except KeyboardInterrupt:
        return 0
    except ProcessManagerError as error:
        print(f"TWINPULSE_LAUNCH_ERROR code={error.code} message={error}", file=sys.stderr, flush=True)
        return 1
    finally:
        manager.stop()


if __name__ == "__main__":
    raise SystemExit(main())
