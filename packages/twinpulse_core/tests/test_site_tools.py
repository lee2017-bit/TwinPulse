# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H2b-1 v2 plan parser/expander fixtures; no App, provider, or Isaac execution."""

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from twinpulse_core import (SceneToolCall, SceneToolPlanError, SiteToolPlan,
                            demo_warehouse_tool_plan, evaluate_site_plan, execute_site_tool_plan,
                            site_tool_plan_from_json)
from twinpulse_core.site_tools import SiteCallEvidence
from twinpulse_core.furniture import FURNITURE_CATALOG_VERSION, expand_furniture, furniture_kinds


def plan_with(*, robot: bool = False, mission: bool = False) -> SiteToolPlan:
    calls = list(demo_warehouse_tool_plan().calls[:1])
    if robot:
        calls.append(demo_warehouse_tool_plan().calls[-2])
    if mission:
        calls.append(demo_warehouse_tool_plan().calls[-1])
    return SiteToolPlan("site_demo", "Bounded scene", "Fixture only", tuple(calls))


class SiteToolTests(unittest.TestCase):
    def test_local_furniture_v21_preserves_v20_plan_and_expands_height(self):
        old = plan_with()
        self.assertEqual(old.plan_version, "2.0")
        self.assertEqual(site_tool_plan_from_json(json.dumps(old.to_dict())).to_dict(), old.to_dict())
        self.assertEqual(set(furniture_kinds()), {"bed", "wardrobe", "desk", "chair", "sofa", "dining_table", "storage"})
        floor = old.calls[0]
        furniture = SceneToolCall("desk_call", "place_furniture", {
            "id": "desk_one", "kind": "desk", "catalog_version": FURNITURE_CATALOG_VERSION,
            "center_m": [0.5, 0.5], "yaw_deg": 90,
        })
        plan = SiteToolPlan("furnished_room", "User furniture", "No image inference", (floor, furniture),
                            plan_version="2.1", call_evidence=(
                                SiteCallEvidence(floor.call_id, (), "user", "User dimensions"),
                                SiteCallEvidence("desk_call", (), "user", "User selected desk"),
                            ))
        restored = site_tool_plan_from_json(json.dumps(plan.to_dict()))
        scene = execute_site_tool_plan(restored, source="photo", source_ref="e" * 64).scene
        self.assertEqual(len(scene.objects), 6)
        top = next(item for item in scene.objects if item.id == "desk_one_top")
        self.assertAlmostEqual(top.transform.position_m[2], .71)
        self.assertEqual(top.transform.rotation_rpy_deg[2], 90)
        self.assertTrue(all(item.collision for item in scene.objects[1:]))
        self.assertEqual(scene.from_dict(scene.to_dict()), scene)
        with self.assertRaisesRegex(SceneToolPlanError, "allowlisted"):
            site_tool_plan_from_json(json.dumps({**plan.to_dict(), "plan_version": "2.0"}))

    def test_furniture_catalog_rejects_unpinned_or_malformed_inputs(self):
        valid = {"id": "bed_one", "kind": "bed", "catalog_version": FURNITURE_CATALOG_VERSION,
                 "center_m": [0, 0], "yaw_deg": 0}
        self.assertEqual(len(expand_furniture(valid)), 3)
        for kind in furniture_kinds():
            with self.subTest(kind=kind):
                parts = expand_furniture({**valid, "kind": kind})
                self.assertGreaterEqual(len(parts), 3)
                self.assertEqual(len({part.id for part in parts}), len(parts))
                self.assertTrue(all(part.shape.type == "box" and part.transform.position_m[2] > 0
                                    and part.collision for part in parts))
        for invalid in ({**valid, "kind": "invented"}, {**valid, "catalog_version": "future"},
                        {**valid, "center_m": [True, 0]}, {**valid, "yaw_deg": float("nan")},
                        {**valid, "id": "x" * 49}, {**valid, "extra": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(SceneToolPlanError):
                expand_furniture(invalid)

    def test_generic_obstacle_has_traceable_observation_binding(self):
        floor = plan_with().calls[0]
        obstacle = SceneToolCall("barrier_call", "create_box_obstacle", {
            "id": "barrier", "center_m": [1.0, 0.0], "dimensions_m": [0.8, 0.4, 1.0],
            "yaw_deg": 0,
        })
        plan = SiteToolPlan("test_track", "Non-warehouse test track", "Observed barrier",
                            (floor, obstacle), call_evidence=(
                                SiteCallEvidence("floor", ("ground",), "visual", "Visible ground"),
                                SiteCallEvidence("barrier_call", ("barrier_seen",), "visual", "Visible barrier"),
                            ))
        restored = site_tool_plan_from_json(json.dumps(plan.to_dict()))
        site = execute_site_tool_plan(restored, source="photo", source_ref="c" * 64)
        self.assertEqual([item.kind for item in site.scene.objects], ["floor", "equipment"])
        self.assertEqual(site.scene.objects[1].shape.dimensions_m, (0.8, 0.4, 1.0))
        self.assertEqual(site.scene.observation_bindings[1].observation_id, "barrier_seen")
        self.assertEqual(site.scene.observation_bindings[1].scene_object_id, "barrier")
        self.assertEqual(site.scene.from_dict(site.scene.to_dict()), site.scene)

    def test_expanded_children_keep_same_observation_id(self):
        floor = plan_with().calls[0]
        pallet = SceneToolCall("pallet_call", "place_pallet_stack", {
            "id": "stack", "center_m": [1, 1], "footprint_m": [0.5, 0.5],
            "stack_height_m": 0.5, "stack_levels": 2,
        })
        plan = SiteToolPlan("mixed_site", "Mixed site", "Visible stack", (floor, pallet),
                            call_evidence=(
                                SiteCallEvidence("floor", (), "inferred", "Approximate ground"),
                                SiteCallEvidence("pallet_call", ("stack_seen",), "visual", "Visible stack"),
                            ))
        site = execute_site_tool_plan(plan, source="photo", source_ref="d" * 64)
        self.assertEqual(len(site.scene.observation_bindings), 3)
        self.assertEqual({item.observation_id for item in site.scene.observation_bindings}, {"stack_seen"})
        self.assertEqual(site.scene.from_dict(site.scene.to_dict()), site.scene)

    def test_evidence_rejects_missing_calls_and_visual_without_observation(self):
        plan = plan_with()
        with self.assertRaisesRegex(SceneToolPlanError, "cover every call"):
            SiteToolPlan.from_dict(replace(plan, call_evidence=()).to_dict())
        invalid = replace(plan, call_evidence=(SiteCallEvidence("floor", (), "visual", "Visible"),))
        with self.assertRaisesRegex(SceneToolPlanError, "requires an observation"):
            SiteToolPlan.from_dict(invalid.to_dict())

    def test_scene_only_roundtrip_and_no_dummy_entities(self):
        plan = plan_with()
        parsed = site_tool_plan_from_json(json.dumps(plan.to_dict()))
        self.assertEqual(parsed, plan)
        site = execute_site_tool_plan(parsed, source="photo", source_ref="a" * 64)
        self.assertEqual(len(site.scene.objects), 1)
        self.assertIsNone(site.robot)
        self.assertIsNone(site.mission)
        self.assertIsNone(site.navigation_map)
        self.assertTrue(site.review_required)
        self.assertFalse(evaluate_site_plan(site).run_allowed)

    def test_robot_only_and_explicit_goal_are_distinct(self):
        robot_only = execute_site_tool_plan(plan_with(robot=True), source="drawing", source_ref="a" * 64)
        self.assertIsNotNone(robot_only.robot)
        self.assertIsNone(robot_only.mission)
        plan = plan_with(robot=True, mission=True)
        reverse = replace(plan.calls[-1], arguments={"id": "reverse_task", "goal_position_m": [-2, 0, 0],
                                                   "position_tolerance_m": 0.1})
        site = execute_site_tool_plan(replace(plan, calls=(*plan.calls[:-1], reverse)),
                                      source="drawing", source_ref="b" * 64)
        self.assertEqual(site.mission.goal.position_m, (-2.0, 0.0, 0.0))
        self.assertFalse(evaluate_site_plan(site).mission_supported)
        self.assertFalse(evaluate_site_plan(site).run_allowed)

    def test_v1_and_corrupt_v2_cannot_be_silently_promoted(self):
        old = demo_warehouse_tool_plan().to_dict()
        with self.assertRaisesRegex(SceneToolPlanError, "version"):
            SiteToolPlan.from_dict(old)
        plan = plan_with()
        with self.assertRaisesRegex(SceneToolPlanError, "shape"):
            SiteToolPlan.from_dict({**plan.to_dict(), "unreviewed": True})
        with self.assertRaisesRegex(SceneToolPlanError, "source reference"):
            execute_site_tool_plan(plan, source="photo", source_ref="not-a-hash")
        bad_floor = SceneToolCall("floor", "create_floor", {"id": "floor", "center_m": [0, 0]})
        with self.assertRaisesRegex(SceneToolPlanError, "missing"):
            execute_site_tool_plan(replace(plan, calls=(bad_floor,)), source="photo", source_ref="a" * 64)
        malformed = plan.to_dict()
        malformed["calls"][0]["call_id"] = True
        with self.assertRaisesRegex(SceneToolPlanError, "shape"):
            SiteToolPlan.from_dict(malformed)

    def test_missing_floor_duplicate_id_and_ambiguous_agv_rejected(self):
        plan = plan_with(robot=True)
        with self.assertRaisesRegex(SceneToolPlanError, "one floor"):
            SiteToolPlan.from_dict(replace(plan, calls=(plan.calls[1],)).to_dict())
        with self.assertRaisesRegex(SceneToolPlanError, "duplicated"):
            SiteToolPlan.from_dict(replace(plan, calls=(*plan.calls, plan.calls[0])).to_dict())
        static = SceneToolCall("static_agv", "place_static_agv", {"id": "seen", "center_m": [0, 0], "yaw_deg": 0})
        with self.assertRaisesRegex(SceneToolPlanError, "observed AGV"):
            SiteToolPlan.from_dict(replace(plan, calls=(*plan.calls, static)).to_dict())
        with self.assertRaisesRegex(SceneToolPlanError, "requires an explicit robot"):
            SiteToolPlan.from_dict(replace(plan_with(), calls=(plan_with().calls[0],
                                demo_warehouse_tool_plan().calls[-1])).to_dict())


if __name__ == "__main__":
    unittest.main()
