# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual Chrome/local API error-stop check using only an owned fake subprocess."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--explicit-stop", choices=("finish_stop", "force_stop", "escape"),
                        help="Exercise the visible stop control after backend error with stale UI status")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "FAIL", "http": "actual_local_backend", "browser": "actual_chrome",
              "process": "LOCAL_FAKE_ONLY", "robot": "NOT_RUN", "isaac": "NOT_RUN"}
    server = child = None
    try:
        from rehearse_offline_app import NoCredentials
        from tests.integration.test_derived_review_selection import selection_fixture
        from twinpulse_app import JsonProviderSettingsStore, LocalApiServer
        from twinpulse_app.physical_controller import PhysicalController
        node = shutil.which("node")
        chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
        if not node or not chrome.is_file():
            raise RuntimeError("Existing Node/Chrome required")
        app, workflow, broker, _, _, _ = selection_fixture(output / "isolated-state")
        status_file = output / "launcher-status.json"
        status = {"schema_version": "1.0", "status": "ready", "phase": "fake_process_only",
                  "message": "Local fake controller; no owned engine or robot",
                  "backend": {"owned": False, "state": "ready"},
                  "engine": {"owned": False, "state": "not_started"},
                  "browser": {"launched": False}}
        status_file.write_text(json.dumps(status), encoding="utf-8")
        controller = PhysicalController(output, command=lambda _root, mode: [
            sys.executable, "-B", str(ROOT / "tests/fixtures/manual_robot_process.py"),
            mode, str(output / "fake-robot")])
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(broker, product_bootstrap_secret=product_secret,
                                engine_bootstrap_secret=engine_secret, product_workflow=workflow,
                                physical_controller=controller,
                                supervisor_status_file=status_file,
                                static_root=ROOT / "apps/twinpulse-web/dist",
                                provider_settings_store=JsonProviderSettingsStore(output / "isolated-state/settings.json"),
                                credential_store=NoCredentials())
        server.start()
        environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url,
                           TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                           TWINPULSE_REHEARSAL_OUTPUT=str(output),
                           TWINPULSE_REHEARSAL_CHROME=str(chrome),
                           TWINPULSE_STOP_EXPLICIT_ACTION=args.explicit_stop or "")
        child = subprocess.Popen([node, str(ROOT / "apps/twinpulse-web/e2e/review-fix-stop-error-browser.mjs")],
                                 cwd=ROOT / "apps/twinpulse-web", env=environment,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        marker = output / "inject-runtime-error-now"
        deadline = time.monotonic() + 90
        injected = False
        while child.poll() is None and time.monotonic() < deadline:
            if marker.exists() and not injected:
                status.update(status="error", phase="engine_exited",
                              message="Injected local engine failure")
                status_file.write_text(json.dumps(status), encoding="utf-8")
                injected = True
            time.sleep(.05)
        if child.poll() is None:
            raise TimeoutError("Owned browser deadline exceeded")
        browser = json.loads((output / "browser-result.json").read_text(encoding="utf-8"))
        result["browser_result"] = browser
        assert child.returncode == 0 and browser["status"] == "PASS", "Browser stop flow failed"
        assert injected and controller.snapshot(None)["busy"] is False
        assert app._project_store.path.is_file()
        result.update(status="PASS", checks=[
            (f"visible {args.explicit_stop} reached fake owner after backend error"
             if args.explicit_stop else "active fake controller auto-closed after engine error"),
            "new directions disabled; owned fake process finished",
            "no robot connection or provider request"])
    except Exception as error:
        traceback.print_exc()
        result.update(error_type=type(error).__name__, error=str(error)[:500])
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        if server:
            server.stop()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("REVIEW_FIX_STOP_ERROR_BROWSER=" + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
