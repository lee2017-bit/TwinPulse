# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A saved v2 room is edited without rewriting its original plan or photo."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for package in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))

from twinpulse_core import SceneToolCall, SiteToolPlan  # noqa: E402
from twinpulse_app.application import ApplicationService  # noqa: E402
from twinpulse_app.scene_changes import SceneChange, SceneChangeHistory, SceneChangeStore  # noqa: E402
from twinpulse_app.site_draft import SiteDraftRecord  # noqa: E402
from twinpulse_app.manual_room import manual_room_plan  # noqa: E402
from twinpulse_core.furniture import FURNITURE_CATALOG_VERSION  # noqa: E402


def room_source() -> SiteDraftRecord:
    prepared = ApplicationService.prepare_input(
        prompt="Synthetic room, not measured", images=(), measurement_constraints=(),
        generation_settings={"model_id": "offline"},
    )
    floor = SceneToolCall("floor", "create_floor", {"id": "floor", "center_m": [0, 0], "size_m": [5, 5]})
    bed = SceneToolCall("bed", "create_box_obstacle", {
        "id": "bed", "center_m": [-1, 0], "dimensions_m": [1.2, 1.8, 0.5], "yaw_deg": 0,
    })
    desk = SceneToolCall("desk", "create_box_obstacle", {
        "id": "desk", "center_m": [1, 0], "dimensions_m": [0.8, 0.5, 0.7], "yaw_deg": 0,
    })
    plan = SiteToolPlan("room_one", "Synthetic room", "No photo", (floor, bed, desk))
    return SiteDraftRecord.create(
        request_id="fixture", provider_name="fixture", model_id="fixture", image_count=0,
        input_revision=prepared.revision, plan=plan,
    )


def sofa() -> dict:
    return {"call_id": "sofa", "tool": "create_box_obstacle", "arguments": {
        "id": "sofa", "center_m": [0, 1], "dimensions_m": [1, 0.7, 0.7], "yaw_deg": 0,
    }}


def furnished_source() -> SiteDraftRecord:
    prepared = ApplicationService.prepare_input(
        prompt="User-selected room furniture; no image inference", images=(),
        measurement_constraints=(), generation_settings={"model_id": "offline"},
    )
    plan = manual_room_plan("room_one", 3.6, 5.2, 2.6, [
        {"kind": "bed", "center_m": [-.9, .8], "yaw_deg": 0},
        {"kind": "desk", "center_m": [.9, .8], "yaw_deg": 0},
    ])
    return SiteDraftRecord.create(
        request_id="furnished-fixture", provider_name="fixture", model_id="fixture", image_count=0,
        input_revision=prepared.revision, plan=plan,
    )


def furniture(call_id: str, object_id: str, kind: str, x: float, y: float, yaw: float = 0) -> dict:
    return {"call_id": call_id, "tool": "place_furniture", "arguments": {
        "id": object_id, "kind": kind, "catalog_version": FURNITURE_CATALOG_VERSION,
        "center_m": [x, y], "yaw_deg": yaw,
    }}


def rack(call_id: str, x: float, *, bays: int = 1, levels: int = 1) -> dict:
    return {"call_id": call_id, "tool": "create_rack_row", "arguments": {
        "id": call_id, "center_m": [x, 0], "length_m": 2,
        "depth_m": 0.5, "height_m": 1.5, "bay_count": bays, "level_count": levels,
    }}


class SceneChangeTests(unittest.TestCase):
    def test_batch_furniture_add_is_one_atomic_revision_and_undo_reopens(self):
        source = furnished_source()
        original = source.to_dict()
        additions = [furniture("new_bed", "furn_new_bed", "bed", -.9, -1.4),
                     furniture("new_chair", "furn_new_chair", "chair", .9, -1.4)]
        with TemporaryDirectory() as folder:
            store = SceneChangeStore(Path(folder) / "edits.json", project_id="room_one", source=source)
            preview = store.load().preview(source, operation_id="add_both", mode="add_many",
                                           tool_call={"calls": additions})
            self.assertEqual(preview["operation"]["tool_call"], None)
            self.assertEqual(len(preview["operation"]["tool_calls"]), 2)
            self.assertEqual(len(preview["affected_after"]), 9)
            self.assertEqual(preview["affected_before"], {})
            self.assertFalse(store.path.exists())
            saved = store.apply(preview["operation"], preview["preview_digest"])
            self.assertEqual(len(saved.operations), 1)
            plan, site = saved.replay(source)
            self.assertEqual(plan.plan_version, "2.1")
            self.assertEqual(len([call for call in plan.calls if call.tool == "place_furniture"]), 4)
            self.assertEqual(site.scene.revision, preview["result_revision"])
            reopened = SceneChangeStore(store.path, project_id="room_one", source=source).load()
            self.assertEqual(reopened, saved)
            undo = reopened.preview(source, operation_id="undo_both", mode="undo")
            restored = store.apply(undo["operation"], undo["preview_digest"])
            self.assertEqual(restored.replay(source)[0], source.plan)
            self.assertEqual(source.to_dict(), original)

    def test_batch_rejects_overlap_duplicate_and_forged_operation_without_publishing(self):
        source = furnished_source()
        history = SceneChangeHistory.empty("room_one", source)
        bed = furniture("new_bed", "furn_new_bed", "bed", -.9, -1.4)
        chair = furniture("new_chair", "furn_new_chair", "chair", .9, -1.4)
        with self.assertRaisesRegex(ValueError, "overlap"):
            history.preview(source, operation_id="overlap", mode="add_many", tool_call={"calls": [
                bed, furniture("bad_chair", "furn_bad_chair", "chair", -.9, -1.4)]})
        with self.assertRaisesRegex(ValueError, "distinct"):
            history.preview(source, operation_id="duplicate", mode="add_many", tool_call={"calls": [bed, bed]})
        with self.assertRaises(ValueError):
            history.preview(source, operation_id="wrong_tool", mode="add_many", tool_call={"calls": [bed, sofa()]})
        preview = history.preview(source, operation_id="valid", mode="add_many", tool_call={"calls": [bed, chair]})
        forged = json.loads(json.dumps(preview["operation"]))
        forged["tool_calls"][1]["arguments"]["center_m"] = [-.9, -1.4]
        with TemporaryDirectory() as folder:
            store = SceneChangeStore(Path(folder) / "edits.json", project_id="room_one", source=source)
            with self.assertRaises(ValueError):
                store.apply(forged, preview["preview_digest"])
            self.assertFalse(store.path.exists())

    def test_furniture_add_change_undo_reopen_keeps_v21_and_original(self):
        source = furnished_source()
        original = source.to_dict()
        with TemporaryDirectory() as folder:
            store = SceneChangeStore(Path(folder) / "edits.json", project_id="room_one", source=source)
            initial = store.load()
            added = initial.preview(source, operation_id="add_sofa", mode="add",
                                    tool_call=furniture("sofa_call", "furn_3_sofa", "sofa", 0, -1.5))
            first = store.apply(added["operation"], added["preview_digest"])
            self.assertEqual(len(added["affected_after"]), 5)
            self.assertEqual(first.replay(source)[0].plan_version, "2.1")
            changed = first.preview(source, operation_id="move_bed", mode="change",
                                    target_call_id="furniture_1",
                                    tool_call=furniture("furniture_1", "furn_1_bed", "bed", -.9, 1.0))
            self.assertEqual(set(changed["affected_before"]), set(changed["affected_after"]))
            self.assertEqual(len(changed["affected_before"]), 3)
            second = store.apply(changed["operation"], changed["preview_digest"])
            undone = second.preview(source, operation_id="undo_move", mode="undo")
            third = store.apply(undone["operation"], undone["preview_digest"])
            reopened = SceneChangeStore(store.path, project_id="room_one", source=source).load()
            self.assertEqual(reopened, third)
            plan, site = reopened.replay(source)
            self.assertEqual(plan.plan_version, "2.1")
            self.assertEqual({call.arguments["kind"] for call in plan.calls if call.tool == "place_furniture"},
                             {"bed", "desk", "sofa"})
            self.assertEqual(len(site.scene.objects), 17)
            self.assertEqual(source.to_dict(), original)

    def test_add_furniture_upgrades_v20_only_in_change_set_and_rejects_overlap(self):
        source = room_source()
        initial = SceneChangeHistory.empty("room_one", source)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            initial.preview(source, operation_id="overlap", mode="add",
                            tool_call=furniture("new_bed", "furn_new_bed", "bed", -1, 0))
        add = initial.preview(source, operation_id="valid", mode="add",
                              tool_call=furniture("new_sofa", "furn_new_sofa", "sofa", 0, 1.5))
        after = initial.append(source, SceneChange.from_dict(add["operation"]))
        self.assertEqual(source.plan.plan_version, "2.0")
        self.assertEqual(after.replay(source)[0].plan_version, "2.1")
        undo = after.preview(source, operation_id="undo", mode="undo")
        restored = after.append(source, SceneChange.from_dict(undo["operation"]))
        self.assertEqual(restored.replay(source)[0].plan_version, "2.0")

    def test_add_change_undo_reopen_preserves_source_and_unrelated_objects(self):
        source = room_source()
        original = source.to_dict()
        with TemporaryDirectory() as folder:
            path = Path(folder) / "project.scene-changes.json"
            store = SceneChangeStore(path, project_id="room_one", source=source)
            initial = store.load()
            add = initial.preview(source, operation_id="add_sofa", mode="add", tool_call=sofa())
            first = store.apply(add["operation"], add["preview_digest"])
            self.assertEqual(len(first.replay(source)[1].scene.objects), len(source.site.scene.objects) + 1)
            moved = {"call_id": "bed", "tool": "create_box_obstacle", "arguments": {
                "id": "bed", "center_m": [-0.5, 0], "dimensions_m": [1.2, 1.8, 0.5], "yaw_deg": 0,
            }}
            change = first.preview(source, operation_id="move_bed", mode="change",
                                   target_call_id="bed", tool_call=moved)
            second = store.apply(change["operation"], change["preview_digest"])
            self.assertEqual(list(change["affected_before"]), ["bed"])
            self.assertEqual(list(change["affected_after"]), ["bed"])
            self.assertEqual(change["preserved_object_count"], 3)
            undo = second.preview(source, operation_id="undo_bed", mode="undo")
            third = store.apply(undo["operation"], undo["preview_digest"])
            reopened = SceneChangeStore(path, project_id="room_one", source=source).load()
            self.assertEqual(third, reopened)
            _, site = reopened.replay(source)
            self.assertEqual(site.scene.revision, third.current_scene_revision)
            self.assertEqual(site.scene.parent_revision, second.current_scene_revision)
            self.assertEqual({item.id for item in site.scene.objects}, {"floor", "bed", "desk", "sofa"})
            self.assertEqual(next(item for item in site.scene.objects if item.id == "bed").transform.position_m[0], -1)
            self.assertEqual(source.to_dict(), original)

    def test_stale_parent_duplicate_operation_and_changed_source_fail(self):
        source = room_source()
        with TemporaryDirectory() as folder:
            store = SceneChangeStore(Path(folder) / "edits.json", project_id="room_one", source=source)
            empty = store.load()
            add = empty.preview(source, operation_id="add_sofa", mode="add", tool_call=sofa())
            first = store.apply(add["operation"], add["preview_digest"])
            self.assertEqual(store.apply(add["operation"], add["preview_digest"]), first)
            with self.assertRaisesRegex(ValueError, "stale"):
                store.apply(empty.preview(source, operation_id="stale", mode="add", tool_call={
                    **sofa(), "call_id": "other", "arguments": {**sofa()["arguments"], "id": "other"},
                })["operation"], empty.preview(source, operation_id="stale", mode="add", tool_call={
                    **sofa(), "call_id": "other", "arguments": {**sofa()["arguments"], "id": "other"},
                })["preview_digest"])
            with self.assertRaises(ValueError):
                first.preview(source, operation_id="collision", mode="add", tool_call=sofa())
            changed_source = replace(source, request_id="another")
            with self.assertRaisesRegex(ValueError, "source"):
                SceneChangeStore(store.path, project_id="room_one", source=changed_source).load()

    def test_tamper_and_failed_replace_preserve_previous_revision(self):
        source = room_source()
        with TemporaryDirectory() as folder:
            store = SceneChangeStore(Path(folder) / "edits.json", project_id="room_one", source=source)
            add = store.load().preview(source, operation_id="add_sofa", mode="add", tool_call=sofa())
            store.apply(add["operation"], add["preview_digest"])
            saved = store.path.read_bytes()
            history = store.load()
            undo = history.preview(source, operation_id="undo_sofa", mode="undo")
            with patch.object(Path, "replace", side_effect=OSError("injected write failure")):
                with self.assertRaises(OSError):
                    store.apply(undo["operation"], undo["preview_digest"])
            self.assertEqual(store.path.read_bytes(), saved)
            self.assertEqual(store.load(), history)
            forged = json.loads(saved)
            forged["operations"][0]["tool_call"]["arguments"]["center_m"][0] = 1.5
            store.path.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load()

    def test_cannot_edit_floor_or_use_new_call_to_change_other_object(self):
        source = room_source()
        history = SceneChangeHistory.empty("room_one", source)
        with self.assertRaises(ValueError):
            history.preview(source, operation_id="badfloor", mode="change", target_call_id="floor",
                            tool_call={"call_id": "floor", "tool": "create_floor",
                                       "arguments": {"id": "floor", "center_m": [1, 0], "size_m": [5, 5]}})
        with self.assertRaises(ValueError):
            history.preview(source, operation_id="duplicate_id", mode="add", tool_call={
                **sofa(), "arguments": {**sofa()["arguments"], "id": "desk"},
            })

    def test_multi_object_call_reports_every_effect_and_preserves_other_objects(self):
        source = room_source()
        empty = SceneChangeHistory.empty("room_one", source)
        added = empty.preview(source, operation_id="add_rack", mode="add", tool_call=rack("rack", 3))
        self.assertEqual(len(added["affected_after"]), 5)
        self.assertEqual(added["preserved_object_count"], 3)
        first = empty.append(source, SceneChange.from_dict(added["operation"]))
        moved = rack("rack", 4)
        changed = first.preview(source, operation_id="move_rack", mode="change",
                                target_call_id="rack", tool_call=moved)
        self.assertEqual(set(changed["affected_before"]), set(added["affected_after"]))
        self.assertEqual(set(changed["affected_after"]), set(added["affected_after"]))
        self.assertEqual(changed["preserved_object_count"], 3)

    def test_existing_call_and_object_caps_remain_in_force(self):
        source = room_source()
        extra = tuple(SceneToolCall(f"box_{index}", "create_box_obstacle", {
            "id": f"box_{index}", "center_m": [index * 0.3, 3],
            "dimensions_m": [0.2, 0.2, 0.2], "yaw_deg": 0,
        }) for index in range(21))
        plan = SiteToolPlan(source.plan.scene_id, source.plan.summary,
                            source.plan.image_observations, source.plan.calls + extra)
        call_limit = SiteDraftRecord.create(
            request_id="fixture", provider_name="fixture", model_id="fixture", image_count=0,
            input_revision=source.input_revision, plan=plan)
        with self.assertRaises(ValueError):
            SceneChangeHistory.empty("room_one", call_limit).preview(
                call_limit, operation_id="too_many_calls", mode="add", tool_call=sofa())

        many_objects = SiteToolPlan(source.plan.scene_id, source.plan.summary,
                                    source.plan.image_observations,
                                    source.plan.calls + tuple(SceneToolCall.from_dict(rack(
                                        f"rack_{index}", index * 5, bays=8, levels=5))
                                        for index in range(2)))
        object_limit = SiteDraftRecord.create(
            request_id="fixture", provider_name="fixture", model_id="fixture", image_count=0,
            input_revision=source.input_revision, plan=many_objects)
        with self.assertRaises(ValueError):
            SceneChangeHistory.empty("room_one", object_limit).preview(
                object_limit, operation_id="too_many_objects", mode="add",
                tool_call=rack("rack_2", 10, bays=8, levels=5))


if __name__ == "__main__":
    unittest.main()
