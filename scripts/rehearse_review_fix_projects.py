# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual Chrome/local API exercise for bedroom create retry and legacy recovery.

The launcher ready state is a UI fixture. No engine, provider, or robot runs.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "FAIL", "http": "actual_local_backend", "browser": "actual_chrome",
              "launcher_ready": "fixture_only", "engine": "NOT_RUN", "robot": "NOT_RUN",
              "provider_external_calls": 0}
    server = None
    try:
        from rehearse_offline_app import NoCredentials
        from tests.integration.test_a2_room_recipe import NoGateway
        from twinpulse_app import (ApplicationService, CommandBroker, JsonProviderSettingsStore,
                                   LocalApiServer, ProductWorkflow, ProjectStore)
        from twinpulse_app.project_catalog import ProjectCatalog
        node = shutil.which("node")
        chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
        if not node or not chrome.is_file():
            raise RuntimeError("Existing Node/Chrome required")
        state_root = output / "isolated-state"
        catalog_base = ProjectCatalog(state_root, "default")
        catalog_base.create_empty("partial_room")
        partial = state_root / "projects" / "partial_room"
        (partial / "assets").mkdir()
        (partial / "assets" / "room.jpg").write_bytes(b"preserve incomplete original")

        class FailingOnceCatalog(ProjectCatalog):
            attempts = 0

            def create_from_preserved_bedroom(self, project_id, request_id=None, recovery_fingerprint=None):
                if project_id == "retry_room" and self.attempts == 0:
                    self.attempts += 1
                    raise OSError("injected preparation failure")
                self.attempts += 1
                return super().create_from_preserved_bedroom(project_id, request_id, recovery_fingerprint)

        catalog = FailingOnceCatalog(state_root, "default")
        broker = CommandBroker()
        app = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(state_root, "default"))
        workflow = ProductWorkflow(app, broker, mode="simulation_offline",
                                   generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
        status_file = output / "launcher-status.json"
        status_file.write_text(json.dumps({
            "schema_version": "1.0", "status": "ready", "phase": "fixture_only",
            "message": "Local project UI fixture; engine not started",
            "backend": {"owned": False, "state": "ready"},
            "engine": {"owned": False, "state": "not_started"},
            "browser": {"launched": False},
        }), encoding="utf-8")
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(broker, product_bootstrap_secret=product_secret,
                                engine_bootstrap_secret=engine_secret, product_workflow=workflow,
                                project_catalog=catalog,
                                static_root=ROOT / "apps/twinpulse-web/dist",
                                supervisor_status_file=status_file,
                                provider_settings_store=JsonProviderSettingsStore(state_root / "settings.json"),
                                credential_store=NoCredentials())
        server.start()
        environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url,
                           TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                           TWINPULSE_REHEARSAL_OUTPUT=str(output),
                           TWINPULSE_REHEARSAL_CHROME=str(chrome))
        child = subprocess.run([node, str(ROOT / "apps/twinpulse-web/e2e/review-fix-project-browser.mjs")],
                               cwd=ROOT / "apps/twinpulse-web", env=environment,
                               capture_output=True, text=True, timeout=120,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        browser = json.loads((output / "browser-result.json").read_text(encoding="utf-8"))
        result["browser_result"] = browser
        assert child.returncode == 0 and browser["status"] == "PASS", "Browser project flow failed"
        retry = ProjectStore.for_project(state_root, "retry_room").load()
        recovered = ProjectStore.for_project(state_root, "partial_room").load()
        assert retry.site_draft is not None and recovered.site_draft is not None
        originals = list((state_root / "project-transactions" / "recovered-originals").glob("partial_room-*"))
        assert len(originals) == 1
        assert (originals[0] / "assets" / "room.jpg").read_bytes() == b"preserve incomplete original"
        assert ProjectStore.for_project(state_root, "default").load().site_draft is None
        result.update(status="PASS", attempts=catalog.attempts,
                      checks=["UI/API first create failure then same request ID retry succeeds",
                              "legacy partial project explicitly archived and recreated",
                              "active project unchanged; no engine or robot request"])
    except Exception as error:
        traceback.print_exc()
        result.update(error_type=type(error).__name__, error=str(error)[:500])
    finally:
        if server:
            server.stop()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("REVIEW_FIX_PROJECT_BROWSER=" + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
