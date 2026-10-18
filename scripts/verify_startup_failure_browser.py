# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exercise the real local product UI after an intentionally failed Isaac import.

The existing project Python lacks Isaac. The manager owns only its isolated
backend/engine children; a headless Playwright browser is opened afterwards.
No robot, provider, installation or live scene command is involved.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))

from twinpulse_app import TwinPulseProcessManager  # noqa: E402
from twinpulse_app.process_manager import ProcessManagerError, RESTART_REQUESTED  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--recovery-isaac", type=Path,
                        help="Existing Isaac Python for an optional isolated fresh-session recovery check")
    parser.add_argument('--playwright-module',type=Path,help='Existing external test runtime for an isolated package')
    args = parser.parse_args()
    artifact = args.artifact_dir.resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    result: dict[str, object] = {"status": "FAIL", "source": "intentional_missing_isaac_import",
                                 "robot": "NOT_RUN", "provider": "NOT_RUN", "scene_commands": 0}
    manager = None
    try:
        node = shutil.which("node")
        chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
        if node is None or not chrome.is_file():
            raise RuntimeError("Existing Node and Chrome are required")
        if subprocess.run([sys.executable, "-c", "import isaacsim"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0:
            raise RuntimeError("Selected Python unexpectedly has Isaac; refusal to run failure fixture")
        manager = TwinPulseProcessManager(
            repo_root=ROOT, state_dir=artifact / "runtime", python_executable=Path(sys.executable),
            isaac_python=Path(sys.executable), browser_executable=None,
            headless=True, fixture_mode=True, ready_timeout_s=30.0,
        )

        def mark_browser_ready(url: str) -> None:
            if not url.startswith("http://127.0.0.1:"):
                raise RuntimeError("Non-loopback UI URL")
            manager._write_status("starting", "backend_ready", "Backend ready; starting Isaac 3D engine",
                                  browser_launched=True)

        manager.open_browser = mark_browser_ready  # type: ignore[method-assign]
        try:
            manager.start(open_browser=True)
        except ProcessManagerError as error:
            if error.code != "engine_start_failed" or not manager.diagnostics_active:
                raise RuntimeError("Unexpected startup failure handling") from error
        else:
            raise RuntimeError("The intentionally unavailable Isaac import unexpectedly succeeded")

        engine_result = json.loads(manager.engine_result_file.read_text(encoding="utf-8"))
        if engine_result.get("startup_phase") != "isaac_import":
            raise RuntimeError("Early failure was not attributed to Isaac import")
        base, ticket = manager.product_bootstrap()
        environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=base,
                           TWINPULSE_REHEARSAL_BOOTSTRAP=ticket,
                           TWINPULSE_REHEARSAL_OUTPUT=str(artifact),
                           TWINPULSE_REHEARSAL_CHROME=str(chrome))
        if args.playwright_module:
            if not args.playwright_module.is_file():raise ValueError('EXISTING_PLAYWRIGHT_REQUIRED')
            environment['TWINPULSE_PLAYWRIGHT_MODULE']=str(args.playwright_module.resolve())
        completed = subprocess.run(
            [node, str(ROOT / "apps/twinpulse-web/e2e/startup-failure-real.mjs")],
            cwd=ROOT / "apps/twinpulse-web", env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=50,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        browser = json.loads((artifact / "browser-result.json").read_text(encoding="utf-8"))
        result["browser"] = browser
        if completed.returncode != 0 or browser.get("status") != "PASS":
            raise RuntimeError(f"browser failure: {browser.get('error', 'unknown')}")
        if manager.monitor_diagnostics(poll_s=0) != RESTART_REQUESTED:
            raise RuntimeError("Browser retry request did not reach the owned launcher")
        failed_launch_id = manager._launch_id
        failed_lock_file = manager.lock_file
        manager.stop()
        if failed_lock_file.exists():
            raise RuntimeError("Failed launch retained its owner lock after retry cleanup")
        recovery_isaac = args.recovery_isaac.resolve() if args.recovery_isaac else Path(sys.executable)
        if not recovery_isaac.is_file():
            raise RuntimeError("Selected recovery Isaac Python is unavailable")
        manager = TwinPulseProcessManager(
            repo_root=ROOT, state_dir=artifact / "runtime", python_executable=Path(sys.executable),
            isaac_python=recovery_isaac, browser_executable=None,
            headless=True, fixture_mode=True, ready_timeout_s=120.0, retry_remaining=2,
        )
        if manager._launch_id == failed_launch_id:
            raise RuntimeError("Explicit retry reused the failed launch identity")
        manager.open_browser = mark_browser_ready  # type: ignore[method-assign]
        if args.recovery_isaac:
            recovered = manager.start(open_browser=True)
            if recovered.launch_id == failed_launch_id or not manager.lock_file.exists():
                raise RuntimeError("Fresh recovery did not own a distinct live session")
            new_status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
            if new_status.get("status") != "ready":
                raise RuntimeError("Fresh recovery was not marked ready")
            retry_outcome = "NEW_OWNED_SESSION_READY_WITH_EXISTING_ISAAC"
            successful_recovery = "ISOLATED_LOCAL_ISAAC_PASS"
        else:
            try:
                manager.start(open_browser=True)
            except ProcessManagerError as error:
                if error.code != "engine_start_failed" or not manager.diagnostics_active:
                    raise RuntimeError("Fresh retry had an unexpected startup outcome") from error
            else:
                raise RuntimeError("Fresh retry unexpectedly found Isaac in the fixture Python")
            retry_result = json.loads(manager.engine_result_file.read_text(encoding="utf-8"))
            if retry_result.get("startup_phase") != "isaac_import" or not manager.lock_file.exists():
                raise RuntimeError("Fresh retry did not own a new diagnostic backend")
            retry_outcome = "NEW_OWNED_SESSION_ATTEMPTED_STILL_MISSING_ISAAC"
            successful_recovery = "NOT_RUN"
        new_base, new_ticket = manager.product_bootstrap()
        if not new_base.startswith("http://127.0.0.1:") or new_ticket == ticket:
            raise RuntimeError("Fresh retry did not rotate the local browser bootstrap ticket")
        result.update(status="PASS", diagnostic_backend_survived=True,
                      engine_failure_phase="isaac_import", retry_request_observed=True,
                      actual_retry=retry_outcome,
                      retry_launch_identity_changed=True, retry_remaining=2,
                      new_bootstrap_ticket=True, successful_isaac_recovery=successful_recovery)
        result['process_manager_origin']=str(Path(sys.modules['twinpulse_app.process_manager'].__file__).resolve())
        if not Path(result['process_manager_origin']).is_relative_to(ROOT):raise ValueError('PACKAGE_IMPORT_ORIGIN')
    except Exception as error:
        result.update(failure_type=type(error).__name__, failure=str(error)[:450])
    finally:
        if manager is not None:
            manager.stop()
        (artifact / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"STARTUP_FAILURE_BROWSER={result['status']} artifact={artifact}", flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
