# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Isolated Chrome/App/API manual-photo room creation; no Isaac or robot."""

from __future__ import annotations

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
    if len(sys.argv) != 2:
        raise SystemExit("usage: rehearse_manual_room_create.py OUTPUT")
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "FAIL", "source": "synthetic_photo_user_dimensions",
              "isaac": "NOT_RUN", "robot": "NOT_RUN", "provider_calls": 0}
    server = None
    try:
        from tests.integration.test_manual_room_creation import photo
        from tests.integration.test_a2_room_recipe import NoGateway
        from rehearse_offline_app import NoCredentials
        from twinpulse_app import (ApplicationService, CommandBroker, JsonProviderSettingsStore,
                                   LocalApiServer, ProductWorkflow, ProjectStore)
        from twinpulse_app.project_catalog import ProjectCatalog
        from twinpulse_app.room_recipe import load_project_room_visual
        node = shutil.which("node")
        chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
        if not node or not chrome.is_file():
            raise RuntimeError("Existing Node/Chrome required")
        (output / "synthetic-room.png").write_bytes(photo("green"))
        state_root = output / "isolated-state"
        broker = CommandBroker()
        application = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(state_root, "default"))
        default_path = ProjectStore.for_project(state_root, "default").path
        default_before = default_path.read_bytes() if default_path.exists() else None
        workflow = ProductWorkflow(application, broker, mode="simulation_offline",
                                   generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
        status_file = output / "launcher-status.json"
        status_file.write_text(json.dumps({
            "schema_version": "1.0", "status": "ready", "phase": "fixture_only",
            "message": "Local UI fixture; engine not started",
            "backend": {"owned": False, "state": "ready"},
            "engine": {"owned": False, "state": "not_started"},
            "browser": {"launched": False},
        }), encoding="utf-8")
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(
            broker, product_bootstrap_secret=product_secret, engine_bootstrap_secret=engine_secret,
            product_workflow=workflow, project_catalog=ProjectCatalog(state_root, "default"),
            static_root=ROOT / "apps/twinpulse-web/dist", supervisor_status_file=status_file,
            provider_settings_store=JsonProviderSettingsStore(state_root / "settings.json"),
            credential_store=NoCredentials(),
        )
        server.start()
        environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url,
                           TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                           TWINPULSE_REHEARSAL_OUTPUT=str(output), TWINPULSE_REHEARSAL_CHROME=str(chrome))
        child = subprocess.run([node, str(ROOT / "apps/twinpulse-web/e2e/manual-room-create-real.mjs")],
                               cwd=ROOT / "apps/twinpulse-web", env=environment,
                               capture_output=True, text=True, timeout=120,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        browser = json.loads((output / "browser-result.json").read_text(encoding="utf-8"))
        if child.returncode or browser["status"] != "PASS":
            raise RuntimeError("Local browser manual room creation failed")
        named = ProjectStore.for_project(state_root, "photo_room_two").load()
        assert named.site_draft is not None and named.site_draft.site.robot is None
        assert named.site_draft.site.mission is None
        furnished = os.environ.get("TWINPULSE_REHEARSAL_FURNITURE") == "1"
        assert named.site_draft.plan.plan_version == ("2.1" if furnished else "2.0")
        if furnished:
            assert [call.arguments["kind"] for call in named.site_draft.plan.calls[4:]] == ["bed", "desk"]
            assert len(named.site_draft.site.scene.objects) == 12
        assert load_project_room_visual(state_root, "photo_room_two", named.site_draft) is not None
        assert (default_path.read_bytes() if default_path.exists() else None) == default_before
        result.update(status="PASS", browser=browser,
                      scene_revision=named.site_draft.site.scene.revision,
                      input_revision=named.site_draft.input_revision.digest,
                      original_photo_preserved=True, burger_visual_pinned=True,
                      active_project_unchanged=True, furniture_scenario=furnished)
    except Exception as error:
        traceback.print_exc()
        result.update(error_type=type(error).__name__, error=str(error)[:500])
    finally:
        if server:
            server.stop()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("MANUAL_ROOM_CREATE_BROWSER=" + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
