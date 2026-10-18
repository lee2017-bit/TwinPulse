# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual standalone Isaac test of a synthetic derived review, never physical.

Existing runtime only, new output directory, new stage, no timeline play. Tests
the typed adapter/compiler boundary, not yet the App promotion workflow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/integration"))
from test_derived_site_review import derived_fixture
from twinpulse_app.derived_site_review import DerivedSiteReview, DerivedReviewStore
from twinpulse_core import CommandEnvelope

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--workflow", action="store_true", help="Also validate App selection/ack/broker with actual Isaac")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
# Isolate fallback settings paths and ignore any inherited managed bridge config.
# Never load or print their former values.
os.environ["TWINPULSE_STATE_DIR"] = str((args.output / "isolated-app-state").resolve())
for name in ("TWINPULSE_BRIDGE_URL", "TWINPULSE_ENGINE_BOOTSTRAP", "TWINPULSE_API_KEY"):
    os.environ.pop(name, None)
result = {"status": "FAIL", "data": "synthetic_test_fixture", "boundary": "typed_adapter_not_product_workflow",
          "physical_validation": "NOT_RUN", "robot_connections": 0, "provider_calls": 0,
          "physics_run": "NOT_RUN", "motion_authorized": False, "checks": []}
app = None
try:
    source, text = derived_fixture()
    record = DerivedSiteReview.create(source, text)
    store = DerivedReviewStore(args.output / "derived-review.json")
    store.save(record)
    checked = store.load()
    assert checked == record
    result["checks"].append("original_expansion_and_archive_replayed_after_disk_reload")
    workflow_fixture = None
    if args.workflow:
        from tests.integration.test_derived_review_selection import selection_fixture
        workflow_fixture = selection_fixture(args.output / "isolated-workflow")
        result["boundary"] = "application_workflow_broker_to_actual_isaac_not_combined_browser"
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": 960, "height": 720})
    import omni.kit.app
    import omni.timeline
    import omni.usd
    from pxr import UsdGeom
    context = omni.usd.get_context()
    context.new_stage()
    for _ in range(10): app.update()
    # Import the adapter classes without running the Extension UI startup,
    # credential/settings lookup, draft restore, or a bridge client.
    sys.path.insert(0, str(ROOT / "extensions/twinpulse.extension"))
    from twinpulse.extension import get_extension
    assert get_extension() is None, "Unexpected existing Extension UI instance"
    from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
    from twinpulse.extension.runtime import TwinPulseRuntime
    runtime = TwinPulseRuntime()
    adapter = IsaacSimulationAdapter(runtime)
    adapter.update_control_lease("synthetic-derived-fixture", True)
    stage = context.get_stage()
    marker = UsdGeom.Xform.Define(stage, "/ExternalKeep").GetPrim()
    marker.SetCustomDataByKey("fixture", "preserve-this")
    def envelope(scene, number):
        return CommandEnvelope(command_id=f"derived-{number}", command_type="build_site_scene",
            project_id="default", engine_session_id=adapter.engine_session_id, stage_epoch=adapter.stage_epoch,
            control_lease_id="synthetic-derived-fixture", expected_applied_revision=scene.revision,
            payload={"artifact_id": f"derived-{number}", "scene_revision": scene.revision, "scene": scene.to_dict()})
    receipts = []
    for number, scene in enumerate((record.source.site.scene, record.site.scene)):
        if workflow_fixture:
            application, workflow, broker, _, adoption_args, _ = workflow_fixture
            broker.register_engine(adapter.engine_session_id, adapter.stage_epoch)
            lease = broker.acquire_lease("synthetic-product")
            adapter.update_control_lease(lease["control_lease_id"], True)
            broker.record_snapshot(adapter.snapshot())
            if number:
                workflow.adopt_derived_review(*adoption_args)
            draft = workflow.snapshot()["site_draft"]
            assert draft["revision"] == scene.revision
            from twinpulse_app.command_broker import BrokerError
            try:
                workflow.assert_site_build_allowed(draft["artifact_id"], draft["revision"])
            except BrokerError:
                pass
            else:
                raise AssertionError("Build passed without new acknowledgement")
            workflow.acknowledge(draft["revision"])
            workflow.assert_site_build_allowed(draft["artifact_id"], draft["revision"])
            broker.submit("synthetic-product", {"client_request_id": f"workflow-{number}",
                "command_type": "build_site_scene", "artifact_id": draft["artifact_id"],
                "expected_applied_revision": draft["revision"]})
            command = broker.claim(adapter.engine_session_id, adapter.stage_epoch)
            assert command is not None
            receipt = adapter.execute(command)
            broker.record_receipt(receipt)
            broker.record_snapshot(adapter.snapshot())
            assert broker.public_state("synthetic-product")["operations"][-1]["status"] == "succeeded"
        else:
            receipt = adapter.execute(envelope(scene, number))
        assert receipt.status == "succeeded", receipt.error_code
        assert receipt.applied_revision == scene.revision
        assert runtime.compiler.matches_site_scene(scene)
        for obj in scene.objects:
            prim = stage.GetPrimAtPath(f"/World/TwinPulse/Environment/{obj.id}")
            actual = tuple(prim.GetAttribute("xformOp:translate").Get())
            assert all(abs(a-b) < 1e-6 for a,b in zip(actual, obj.transform.position_m))
        assert stage.GetPrimAtPath("/ExternalKeep").GetCustomDataByKey("fixture") == "preserve-this"
        assert not stage.GetPrimAtPath("/World/TwinPulse/Robot").IsValid()
        assert not stage.GetPrimAtPath("/World/TwinPulse/Task").IsValid()
        assert "run" not in adapter.snapshot().permitted_commands
        assert not omni.timeline.get_timeline_interface().is_playing()
        receipts.append({"revision": receipt.applied_revision, "fingerprint": receipt.build_fingerprint})
    result["checks"].append("source_then_derived_typed_build_exact_geometry_foreign_prim_preserved_no_robot_task_or_run")
    # Remaining negative/idempotence adapter tests use their own explicit lease.
    adapter.update_control_lease("synthetic-derived-fixture", True)
    if workflow_fixture:
        try:
            workflow.assert_run_not_site_draft()
        except BrokerError:
            pass
        else:
            raise AssertionError("Derived workflow permitted Run")
        result["checks"].append("application_selection_new_ack_broker_receipt_actual_isaac_no_run")
    # Stale identity must fail before replacing the already-tested derived scene.
    bad = envelope(record.source.site.scene, 2)
    from dataclasses import replace
    denied = adapter.execute(replace(bad, expected_applied_revision="0"*64))
    assert denied.status == "failed"
    assert runtime.compiler.matches_site_scene(record.site.scene)
    result["checks"].append("stale_typed_build_rejected_prior_derived_geometry_retained")
    again = adapter.execute(envelope(record.site.scene, 3))
    assert again.status == "succeeded" and again.build_fingerprint == receipts[-1]["fingerprint"]
    result["checks"].append("same_derived_build_is_idempotent")
    assert get_extension() is None
    result["checks"].append("no_extension_ui_startup_or_user_project_restore")
    result.update(status="PASS", derivation_revision=record.revision, receipts=receipts,
                  record_sha256=hashlib.sha256(store.path.read_bytes()).hexdigest())
except Exception as exc:
    result["error_type"] = type(exc).__name__
    result["error"] = str(exc)
finally:
    result["source_hashes"] = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__).resolve(), ROOT/"packages/twinpulse_app/src/twinpulse_app/derived_site_review.py",
                  ROOT/"packages/twinpulse_app/src/twinpulse_app/scan_review.py",
                  ROOT/"tests/integration/test_derived_site_review.py")}
    if args.workflow:
        for name in ("packages/twinpulse_app/src/twinpulse_app/application.py",
                     "packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py",
                     "packages/twinpulse_app/src/twinpulse_app/command_broker.py",
                     "tests/integration/test_derived_review_selection.py"):
            result["source_hashes"][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    (args.output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("DERIVED_REVIEW_RESULT=" + json.dumps(result), flush=True)
    if app: app.close()
sys.exit(0 if result["status"] == "PASS" else 1)
