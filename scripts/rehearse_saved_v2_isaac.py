# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reopen a saved generic v2 scene in real Chrome/API/bridge/Isaac; no Run."""

import argparse
import asyncio
from hashlib import sha256
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
sys.path.insert(0, str(ROOT / "extensions/twinpulse.extension"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--photo", action="store_true", help="Use a deterministic local PNG as original input")
    parser.add_argument("--missing-archive", action="store_true", help="Require identical source reattachment in Chrome")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    node = shutil.which("node")
    chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    if not node or not chrome.is_file():
        parser.error("Existing Node/Chrome required")
    result = {"status": "FAIL", "source": "synthetic_saved_provider_v2_photo" if args.photo else "synthetic_saved_provider_v2_text", "project_id": "default",
              "physical_validation": "NOT_RUN", "physics_run": "NOT_RUN",
              "robot_connections": 0, "provider_external_calls": 0, "checks": []}
    sim = server = bridge = child = None
    try:
        from tests.integration.test_h2b2_site_review import SiteGateway
        from tests.integration.test_r5_product_api import png
        from rehearse_offline_app import NoCredentials
        from twinpulse_app import (ApplicationService, CommandBroker, JsonProviderSettingsStore,
                                   LocalApiServer, ProductWorkflow, ProjectStore)
        from twinpulse_core import InputArtifactStore
        from twinpulse_provider import ImageInput
        from isaacsim import SimulationApp

        state_root = output / "isolated-state"
        project_store = ProjectStore.for_project(state_root, "default")
        archive = InputArtifactStore(state_root / "inputs")
        first = ApplicationService(SiteGateway(), project_store=project_store, artifact_store=archive)
        images = (ImageInput("room.png", "image/png", png()),) if args.photo else ()
        prepared = first.prepare_input(prompt="Saved generic v2 room fixture", images=images,
                                       measurement_constraints=(), generation_settings={"model_id": "original-fixture"})
        first.select_input(prepared)
        outcome = asyncio.run(first.generate())
        draft = outcome.record
        original_record_hash = sha256(project_store.path.read_bytes()).hexdigest()
        original_archive_hash = sha256((archive.root / prepared.revision.digest / "revision.json").read_bytes()).hexdigest()
        if args.missing_archive:
            missing = (archive.root / prepared.revision.digest /
                       (f"{prepared.revision.images[0]['sha256']}.bin" if args.photo else "revision.json"))
            missing.unlink()
            if args.photo:
                (output / "room.png").write_bytes(png())
                wrong = output / "wrong"
                wrong.mkdir()
                (wrong / "room.png").write_bytes(png(width=3))
        # New backend objects simulate restarting the application; the prior
        # in-memory input and approval cannot carry over.
        app = ApplicationService(SiteGateway(), project_store=project_store, artifact_store=archive)
        broker = CommandBroker()
        workflow = ProductWorkflow(app, broker, mode="live_provider",
                                   generation_settings_getter=lambda: {"model_id": "changed-fixture"},
                                   provider_state_getter=lambda: {"configured": False, "label": "No-call saved review"})
        assert workflow.snapshot()["phase"] == "restore_review_required"
        sim = SimulationApp({"headless": True, "width": 960, "height": 720})
        import omni.timeline
        import omni.usd
        from pxr import Usd
        from twinpulse.extension.bridge_client import BridgeClient
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.runtime import TwinPulseRuntime
        omni.usd.get_context().new_stage()
        for _ in range(10):
            sim.update()
        stage = omni.usd.get_context().get_stage()
        runtime = TwinPulseRuntime()
        adapter = IsaacSimulationAdapter(runtime, project_id="default", project_state_root=state_root)
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(broker, product_bootstrap_secret=product_secret,
                                engine_bootstrap_secret=engine_secret, product_workflow=workflow,
                                static_root=ROOT / "apps/twinpulse-web/dist",
                                provider_settings_store=JsonProviderSettingsStore(state_root / "settings.json"),
                                credential_store=NoCredentials())
        server.start()
        bridge = BridgeClient(adapter, base_url=server.base_url, bootstrap_secret=engine_secret)
        bridge.start()
        environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url,
                           TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                           TWINPULSE_REHEARSAL_OUTPUT=str(output),
                           TWINPULSE_REHEARSAL_CHROME=str(chrome),
                           TWINPULSE_REHEARSAL_PROJECT="default",
                           TWINPULSE_REHEARSAL_REATTACH="1" if args.missing_archive else "0")
        if args.missing_archive and args.photo:
            environment["TWINPULSE_REHEARSAL_PHOTO_FILE"] = str(output / "room.png")
            environment["TWINPULSE_REHEARSAL_WRONG_PHOTO_FILE"] = str(output / "wrong" / "room.png")
        child = subprocess.Popen([node, str(ROOT / "apps/twinpulse-web/e2e/named-room-isaac-real.mjs")],
                                 cwd=ROOT / "apps/twinpulse-web", env=environment,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + 150
        while child.poll() is None and time.monotonic() < deadline:
            sim.update()
            bridge.update()
            assert not omni.timeline.get_timeline_interface().is_playing()
            time.sleep(.005)
        if child.poll() is None:
            raise TimeoutError("Owned browser deadline exceeded")
        browser = json.loads((output / "browser-result.json").read_text(encoding="utf-8"))
        result["browser"] = browser
        assert child.returncode == 0 and browser["status"] == "PASS", "Browser checks failed"
        assert len(broker._operations) == 1
        operation = next(iter(broker._operations.values()))
        assert operation.status == "succeeded"
        assert runtime.compiler.matches_site_scene(draft.site.scene)
        assert workflow.snapshot()["input"]["revision"] == prepared.revision.digest
        assert workflow.snapshot()["phase"] == "draft_ready"
        assert app.site_draft == draft
        assert sha256(project_store.path.read_bytes()).hexdigest() == original_record_hash
        assert sha256((archive.root / prepared.revision.digest / "revision.json").read_bytes()).hexdigest() == original_archive_hash
        assert not omni.timeline.get_timeline_interface().is_playing()
        assert "run" not in adapter.snapshot().permitted_commands
        stage.GetRootLayer().Export(str(output / "saved-v2-browser-stage.usda"))
        saved = Usd.Stage.Open(str(output / "saved-v2-browser-stage.usda"))
        assert saved.GetPrimAtPath("/World/TwinPulse").IsValid()
        result.update(status="PASS", scene_revision=draft.site.scene.revision,
                      input_revision=prepared.revision.digest,
                      original_record_sha256=original_record_hash,
                      original_archive_sha256=original_archive_hash,
                      checks=["real browser/API/bridge/Isaac reopened saved generic v2 with one explicit review",
                              "one scene-only Build, no Run or robot request",
                              "saved project and input archive bytes preserved after restart"])
    except Exception as error:
        traceback.print_exc()
        result.update(error_type=type(error).__name__, error=str(error)[:500],
                      failure_line=traceback.extract_tb(error.__traceback__)[-1].lineno)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        if bridge:
            bridge.stop()
        if server:
            server.stop()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("GENERIC_SAVED_V2_ISAAC=" + result["status"], flush=True)
        if sim:
            sim.close()
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
