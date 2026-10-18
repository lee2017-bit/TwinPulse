# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen A0/A1a contracts: moving definitions must not change public schemas."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_core" / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_provider" / "src"))

from twinpulse_core import (SCENE_TOOL_NAMES, SITE_TOOL_NAMES, TOOL_DOMAINS,  # noqa: E402
                            SceneToolCall, SceneToolPlanError, SceneToolRegistry, SiteToolPlan,
                            demo_warehouse_tool_plan, execute_site_tool_plan)
from twinpulse_core.revisions import canonical_sha256  # noqa: E402
from twinpulse_core.scene_tools import SCENE_TOOL_CATALOG_REVISION  # noqa: E402
from twinpulse_core.site_tools import SITE_TOOL_CATALOG_REVISION, SiteCallEvidence  # noqa: E402
from twinpulse_core.tool_catalog import static_tool_definitions, tool_call_schemas, tool_domains, tool_names  # noqa: E402
from twinpulse_provider.schema import scene_tool_plan_json_schema, site_tool_plan_json_schema  # noqa: E402


def schema_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class ToolCatalogCompatibilityTests(unittest.TestCase):
    def test_public_schema_golden_hashes(self) -> None:
        self.assertEqual(schema_digest(scene_tool_plan_json_schema()),
                         "b481aec2ac009d2a61e20cedde69e19b53bf494c209ef00d1eb2eccd4896a131")
        self.assertEqual(schema_digest(scene_tool_plan_json_schema(required_call_slots=True)),
                         "bf2c5a37ef18679ba001924fc7b99b757832acef78133d0ae8b6d2f750538213")
        self.assertEqual(schema_digest(site_tool_plan_json_schema()),
                         "b1599ff2b94900ce624e9560d432032c8a7f6d7d76bb8a31da23aa49bb243160")

    def test_catalog_views_match_public_allowlists_and_local_handlers(self) -> None:
        self.assertEqual(SCENE_TOOL_NAMES, tool_names("1.0"))
        self.assertEqual(SITE_TOOL_NAMES, tool_names("2.0"))
        self.assertEqual(TOOL_DOMAINS, tool_domains("1.0"))
        self.assertEqual(SCENE_TOOL_CATALOG_REVISION, "scene-tools-1.0")
        self.assertEqual(SITE_TOOL_CATALOG_REVISION, "site-tools-2.1")
        self.assertEqual([item["properties"]["tool"]["const"] for item in tool_call_schemas("1.0")],
                         ["create_floor", "create_wall", "create_rack_row", "place_pallet_stack",
                          "create_aisle_marking", "place_static_agv", "place_predefined_agv",
                          "create_navigation_task"])
        self.assertEqual([item["properties"]["tool"]["const"] for item in tool_call_schemas("2.0")][-1],
                         "create_box_obstacle")
        self.assertEqual(set(static_tool_definitions("1.0")), SCENE_TOOL_NAMES - {
            "place_predefined_agv", "create_navigation_task"})
        for definition in static_tool_definitions("1.0").values():
            self.assertTrue(callable(getattr(SceneToolRegistry, definition.handler_name or "", None)))

    def test_demo_plan_and_compiled_bundle_golden(self) -> None:
        plan = demo_warehouse_tool_plan()
        receipt = SceneToolRegistry().execute_with_receipt(plan)
        self.assertEqual([item.tool for item in plan.calls], [
            "create_floor", "create_rack_row", "create_rack_row",
            "place_predefined_agv", "create_navigation_task"])
        self.assertEqual(receipt.expanded_object_count, 17)
        self.assertEqual(canonical_sha256(plan.to_dict()),
                         "c8fc953804d944e5f50679ea52cb5a95fbd4767b5208a7e351904fa57b52515e")
        self.assertEqual(canonical_sha256(receipt.bundle.to_dict()),
                         "756e710786bb6a1e71ddb7f7147c91fb2bc939538ff54d63dfe8a9204d6bbfc8")

    def test_v2_scene_only_and_evidenced_box_golden(self) -> None:
        floor = demo_warehouse_tool_plan().calls[0]
        scene_only = SiteToolPlan("site_demo", "Bounded scene", "Fixture only", (floor,))
        built_scene_only = execute_site_tool_plan(scene_only, source="photo", source_ref="c" * 64)
        self.assertEqual(canonical_sha256(scene_only.to_dict()),
                         "d558aa716a5f740a0251a7a8e2e41c51c5cac4e9c9d6fbf30af3ca08ea62e14d")
        self.assertEqual(canonical_sha256(built_scene_only.to_dict()),
                         "1cd31fc4133c18b3da47d1616d2db4bb41cfda7f95c6f96e222f6e9e93d3838e")
        box = SceneToolCall("barrier_call", "create_box_obstacle", {
            "id": "barrier", "center_m": [1.0, 0.0],
            "dimensions_m": [0.8, 0.4, 1.0], "yaw_deg": 0,
        })
        evidenced = SiteToolPlan("test_track", "Non-warehouse test track", "Observed barrier",
                                 (floor, box), call_evidence=(
                                     SiteCallEvidence("floor", ("ground",), "visual", "Visible ground"),
                                     SiteCallEvidence("barrier_call", ("barrier_seen",), "visual", "Visible barrier"),
                                 ))
        built_evidenced = execute_site_tool_plan(evidenced, source="photo", source_ref="c" * 64)
        self.assertEqual(canonical_sha256(evidenced.to_dict()),
                         "dafebfb5cf95dc67114e7daf83002699f766116ebc7175bb65c3bee40f021867")
        self.assertEqual(canonical_sha256(built_evidenced.to_dict()),
                         "a65a36972454f21fbd91bc43103d6e0d4f4cc72461255024b043e8a8c1753140")

    def test_invalid_values_remain_rejected_by_local_semantics(self) -> None:
        plan = demo_warehouse_tool_plan()
        floor = plan.calls[0]
        for bad_size in ([True, 2.0], [math.nan, 2.0]):
            altered = replace(floor, arguments={**floor.arguments, "size_m": bad_size})
            with self.subTest(bad_size=bad_size), self.assertRaises(SceneToolPlanError):
                SceneToolRegistry().execute(replace(plan, calls=(altered, *plan.calls[1:])))
        with self.assertRaises(SceneToolPlanError):
            SceneToolRegistry().execute(replace(plan, calls=plan.calls * 5))
        unknown = replace(floor, tool="run_external_command")
        with self.assertRaises(SceneToolPlanError):
            SceneToolRegistry().execute(replace(plan, calls=(unknown, *plan.calls[1:])))


if __name__ == "__main__":
    unittest.main()
