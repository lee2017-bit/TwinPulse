# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Existing broker product-state path exposes fail-closed simulation readiness."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for source in (ROOT / "packages" / "twinpulse_core" / "src",
               ROOT / "packages" / "twinpulse_provider" / "src",
               ROOT / "packages" / "twinpulse_app" / "src"):
    sys.path.insert(0, str(source))

from twinpulse_app.command_broker import CommandBroker  # noqa: E402
from twinpulse_core import SimulationSnapshot  # noqa: E402


class BrokerReadinessTests(unittest.TestCase):
    def test_product_state_distinguishes_capability_session_and_connection(self) -> None:
        now = [100.0]
        broker = CommandBroker(clock=lambda: now[0])
        self.assertEqual(broker.public_state("viewer")["engine_readiness"]["bedroom_visual_v1"]["code"],
                         "runtime_disconnected")
        broker.register_engine("engine", "stage")
        self.assertEqual(broker.public_state("viewer")["engine_readiness"]["bedroom_visual_v1"]["code"],
                         "runtime_snapshot_missing")
        broker.record_snapshot(SimulationSnapshot(
            "engine", "stage", "default", None, None, 1, "idle", None, None,
            ("build_site_scene", "get_state"),
            ("simulation", "site_scene_build_v2", "bedroom_visual_v1"),
        ))
        self.assertTrue(broker.site_scene_capable())
        self.assertTrue(broker.public_state("viewer")["engine_readiness"]["bedroom_visual_v1"]["ready"])
        self.assertFalse(broker.public_state("viewer")["engine_readiness"]["bedroom_replay_v1"]["ready"])
        now[0] += 4.0
        self.assertFalse(broker.site_scene_capable())
        self.assertEqual(broker.public_state("viewer")["engine_readiness"]["bedroom_visual_v1"]["code"],
                         "runtime_disconnected")
        broker.register_engine("replacement", "new_stage")
        self.assertEqual(broker.public_state("viewer")["engine_readiness"]["bedroom_visual_v1"]["code"],
                         "runtime_snapshot_missing")


if __name__ == "__main__":
    unittest.main()
