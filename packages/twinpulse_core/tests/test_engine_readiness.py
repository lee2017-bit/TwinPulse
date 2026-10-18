# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A1b snapshot capability versus momentary runtime readiness; no device I/O."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from twinpulse_core.engine_contracts import SimulationSnapshot, evaluate_engine_feature


def snapshot() -> SimulationSnapshot:
    return SimulationSnapshot(
        "engine", "stage", "default", None, None, 1, "idle", None, None,
        ("build_scene", "build_site_scene", "get_state"),
        ("simulation", "build", "site_scene_build_v2", "bedroom_visual_v1", "bedroom_replay_v1"),
    )


def status(feature: str, value: SimulationSnapshot | None, *, connected: bool = True,
           session: str = "engine", stage: str = "stage"):
    return evaluate_engine_feature(feature, snapshot=value, connected=connected,
                                   engine_session_id=session, stage_epoch=stage)


class EngineReadinessTests(unittest.TestCase):
    def test_valid_scene_build_never_implies_physical_authority(self) -> None:
        value = snapshot()
        for feature in ("legacy_scene_build", "site_scene_build_v2", "bedroom_visual_v1",
                        "bedroom_replay_v1"):
            self.assertEqual(status(feature, value).to_dict(),
                             {"feature": feature, "ready": True, "code": "ready"})
        with self.assertRaises(ValueError):
            status("physical_mission", value)

    def test_failure_categories_are_distinct_and_fail_closed(self) -> None:
        value = snapshot()
        self.assertEqual(status("bedroom_visual_v1", value, connected=False).code, "runtime_disconnected")
        self.assertEqual(status("bedroom_visual_v1", None).code, "runtime_snapshot_missing")
        self.assertEqual(status("bedroom_visual_v1", value, session="new_engine").code,
                         "runtime_identity_stale")
        self.assertEqual(status("bedroom_visual_v1", value, stage="new_stage").code,
                         "runtime_identity_stale")
        self.assertEqual(status("bedroom_replay_v1", replace(value, capabilities=("simulation",))).code,
                         "capability_unavailable")
        self.assertEqual(status("bedroom_visual_v1", replace(value, safety_state="latched")).code,
                         "runtime_safety_latched")
        self.assertEqual(status("bedroom_visual_v1", replace(value, permitted_commands=("get_state",))).code,
                         "runtime_command_unavailable")

    def test_legacy_snapshot_build_compatibility(self) -> None:
        old = replace(snapshot(), capabilities=("simulation",),
                      permitted_commands=("build_scene", "get_state"))
        self.assertTrue(status("legacy_scene_build", old).ready)
        self.assertFalse(status("site_scene_build_v2", old).ready)


if __name__ == "__main__":
    unittest.main()
