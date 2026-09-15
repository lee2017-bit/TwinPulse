"""Finite, no-provider-call R1 legacy UI smoke against the local Isaac runtime."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STATE = tempfile.TemporaryDirectory(prefix="tmp-r1-kit-", dir=os.environ.get("TWINPULSE_TEST_TMP"))
os.environ["TWINPULSE_STATE_DIR"] = STATE.name

from isaacsim import SimulationApp  # noqa: E402

APP = SimulationApp({"headless": True, "renderer": "MinimalRendering",
                     "disable_viewport_updates": True, "width": 640, "height": 480})

try:
    import omni.kit.app
    import omni.usd

    omni.usd.get_context().new_stage()
    for _ in range(10):
        APP.update()
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(ROOT / "extensions"))
    if not manager.set_extension_enabled_immediate("twinpulse.extension", True):
        raise RuntimeError("TwinPulse extension did not enable")
    for _ in range(5):
        APP.update()
    import twinpulse.extension as module
    from twinpulse_core import GeneratedDraftRecord, demo_warehouse_tool_plan

    extension = module.get_extension()
    if extension is None:
        raise RuntimeError("TwinPulse extension instance is unavailable")
    extension._prompt_model.set_value("A warehouse aisle")
    a, _, _ = extension._current_input()
    record = GeneratedDraftRecord.create(request_id="r1-smoke", provider_name="fixture",
        model_id="fixture", image_count=0, plan=demo_warehouse_tool_plan(), input_revision=a)
    extension._set_generated_record(record, restored=False)
    if not extension._record_matches_current_input(record):
        raise AssertionError("matching draft was not accepted")
    epoch = extension._input_epoch
    extension._prompt_model.set_value("A different warehouse aisle")
    b, _, _ = extension._current_input()
    if extension._input_epoch <= epoch:
        raise AssertionError("prompt change did not supersede the active generation epoch")
    if a.digest == b.digest or extension._record_matches_current_input(record):
        raise AssertionError("changed prompt did not stale the draft")
    extension._request_build()
    if extension.runtime.compiler.bundle is not None:
        raise AssertionError("stale draft mutated the Isaac stage")
    extension._open_previous_draft()
    if extension._previous_draft_window is None:
        raise AssertionError("explicit prior-draft review did not open")
    print("R1 Extension smoke PASS: enable, prompt revision, stale Build gate, prior draft review")
    extension._previous_draft_window.visible = False
    extension = None
    module = None
    manager.set_extension_enabled_immediate("twinpulse.extension", False)
    for _ in range(5):
        APP.update()
finally:
    APP.close()
    STATE.cleanup()
