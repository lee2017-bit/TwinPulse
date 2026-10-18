# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""R1 regression: independent drawing measurements and draft/input provenance."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = os.environ.get("TWINPULSE_TEST_TMP")
sys.path.insert(0, str(ROOT / "packages" / "twinpulse_core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "twinpulse_provider" / "src"))

from twinpulse_core import (GeneratedDraftRecord, GeneratedDraftStore, InputArtifactStore, InputRevision,
                            generation_result_is_current,
                            SceneToolRegistry, bundle_digest, plan_digest,
                            validate_plan_measurements,
                            canonical_sha256, demo_warehouse_tool_plan)  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    MeasurementConstraintError,
    load_measurement_constraints,
    validate_measurement_constraints,
)


class R1WorkflowTests(unittest.TestCase):
    def test_generated_sidecar_accepts_actual_reference_plan_and_rejects_wrong_height(self) -> None:
        with TemporaryDirectory(prefix="tmp-r1-", dir=TEST_TMP) as directory:
            root = Path(directory)
            image = root / "warehouse-floorplan.png"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "create_m2d_floorplan_fixture.py"), "--output", str(image)],
                check=True, stdout=subprocess.DEVNULL,
            )
            manifest = json.loads((ROOT / "fixtures" / "m2d" / "dimensioned_floorplan.json").read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), manifest["fixtures"][0]["sha256"])
            reference = root / "reference.json"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "create_m2d_reference_report.py"),
                 "--manifest", str(ROOT / "fixtures" / "m2d" / "dimensioned_floorplan.json"),
                 "--output", str(reference)],
                check=True, stdout=subprocess.DEVNULL,
            )
            payload = json.loads(reference.read_text(encoding="utf-8"))
            from twinpulse_core import SceneToolPlan, SceneToolCall  # noqa: E402
            plan = SceneToolPlan.from_dict(payload["fixtures"][0]["plan"])
            constraints = load_measurement_constraints(image.with_suffix(".measurements.json"), image_path=image)
            self.assertGreaterEqual(validate_measurement_constraints(plan, constraints).checked_value_count, 8)
            self.assertEqual(validate_plan_measurements(plan, tuple(value.to_dict() for value in constraints)),
                             validate_measurement_constraints(plan, constraints).checked_value_count)
            calls = list(plan.calls)
            index = next(i for i, call in enumerate(calls) if call.tool == "create_rack_row")
            call = calls[index]
            calls[index] = SceneToolCall(call.call_id, call.tool, {**call.arguments, "height_m": 2.0})
            with self.assertRaises(MeasurementConstraintError):
                validate_measurement_constraints(
                    SceneToolPlan(plan.scene_id, plan.summary, plan.image_observations, tuple(calls)), constraints
                )
            with self.assertRaises(ValueError):
                validate_plan_measurements(
                    SceneToolPlan(plan.scene_id, plan.summary, plan.image_observations, tuple(calls)),
                    tuple(value.to_dict() for value in constraints),
                )
            goal_index = next(i for i, call in enumerate(plan.calls) if call.tool == "create_navigation_task")
            goal_call = plan.calls[goal_index]
            wrong_goal = list(plan.calls)
            wrong_goal[goal_index] = SceneToolCall(goal_call.call_id, goal_call.tool,
                                                    {**goal_call.arguments, "goal_position_m": [3.0, 0.0, 0.0]})
            with self.assertRaises(MeasurementConstraintError):
                validate_measurement_constraints(
                    SceneToolPlan(plan.scene_id, plan.summary, plan.image_observations, tuple(wrong_goal)), constraints
                )
            with self.assertRaises(ValueError):
                validate_plan_measurements(
                    SceneToolPlan(plan.scene_id, plan.summary, plan.image_observations, tuple(wrong_goal)),
                    tuple(value.to_dict() for value in constraints),
                )

    def test_legacy_record_is_loaded_but_not_buildable_for_new_input(self) -> None:
        from twinpulse_core import InputRevision  # noqa: E402
        record = GeneratedDraftRecord.create(
            request_id="a", provider_name="mock", model_id="mock", image_count=1,
            plan=demo_warehouse_tool_plan(),
        )
        revision = InputRevision.create(prompt="A", images=(("same.png", b"a"),),
                                        measurement_constraints=(), profile_id="agv_compact_2wd_caster_v2",
                                        generation_settings={"model_id": "mock"})
        self.assertFalse(record.build_allowed_for(revision))
        rebound = record.adopt_legacy_for(revision)
        self.assertEqual(rebound.origin_status, "legacy_rebound")
        self.assertEqual(GeneratedDraftRecord.from_dict(rebound.to_dict()).origin_status, "legacy_rebound")
        with self.assertRaises(ValueError):
            record.adopt_legacy_for(InputRevision.create(prompt="A", images=(),
                measurement_constraints=(), profile_id="agv_compact_2wd_caster_v2",
                generation_settings={"model_id": "mock"}))

    def test_new_input_supersedes_a_even_if_b_fails_then_save_load(self) -> None:
        from twinpulse_core import InputRevision  # noqa: E402
        a = InputRevision.create(prompt="A", images=(("same.png", b"a"),),
                                 measurement_constraints=(), profile_id="agv_compact_2wd_caster_v2",
                                 generation_settings={"model_id": "mock"})
        b = InputRevision.create(prompt="A", images=(("same.png", b"b"),),
                                 measurement_constraints=(), profile_id="agv_compact_2wd_caster_v2",
                                 generation_settings={"model_id": "mock"})
        self.assertNotEqual(a.digest, b.digest)
        record = GeneratedDraftRecord.create(
            request_id="a", provider_name="mock", model_id="mock", image_count=1,
            plan=demo_warehouse_tool_plan(), input_revision=a,
        )
        self.assertTrue(record.build_allowed_for(a))
        self.assertFalse(record.build_allowed_for(b))
        with TemporaryDirectory(prefix="tmp-r1-", dir=TEST_TMP) as directory:
            store = GeneratedDraftStore(Path(directory) / "draft.json")
            store.save(record)
            loaded = store.load()
            self.assertIsNotNone(loaded)
            self.assertFalse(loaded.build_allowed_for(b))

    def test_input_revision_tracks_prompt_image_removal_measurement_and_settings(self) -> None:
        base = dict(prompt="A", images=(("same.png", b"bytes"),),
                    measurement_constraints=(), profile_id="agv_compact_2wd_caster_v2",
                    generation_settings={"model_id": "mock"})
        a = InputRevision.create(**base)
        changes = (
            {**base, "prompt": "B"},
            {**base, "images": ()},
            {**base, "measurement_constraints": ({"kind": "distance", "expected_m": 3.0},)},
            {**base, "generation_settings": {"model_id": "other"}},
            {**base, "profile_id": "other_profile"},
        )
        for variant in changes:
            self.assertNotEqual(a.digest, InputRevision.create(**variant).digest)
        self.assertEqual(InputRevision.from_dict(a.to_dict()), a)

    def test_corrupt_receipt_or_validator_version_never_builds(self) -> None:
        revision = InputRevision.create(prompt="A", images=(), measurement_constraints=(),
                                        profile_id="agv_compact_2wd_caster_v2",
                                        generation_settings={"model_id": "mock"})
        record = GeneratedDraftRecord.create(request_id="a", provider_name="mock", model_id="mock",
                                             image_count=0, plan=demo_warehouse_tool_plan(), input_revision=revision)
        self.assertTrue(record.build_allowed_for(revision))
        for field, value in (("bundle_sha256", "0" * 64), ("validator_version", "obsolete"),
                             ("dimensional_status", "verified")):
            altered = record.to_dict()
            altered["validation_receipt"][field] = value
            with self.assertRaises(ValueError):
                GeneratedDraftRecord.from_dict(altered)
        from dataclasses import replace
        from twinpulse_core import ValidationReceipt
        tampered = replace(record, validation_receipt=replace(record.validation_receipt, bundle_sha256="0" * 64))
        self.assertFalse(tampered.build_allowed_for(revision))
        unknown = record.to_dict()
        unknown["record_version"] = "9.0"
        with self.assertRaises(ValueError):
            GeneratedDraftRecord.from_dict(unknown)

    def test_late_result_fails_after_epoch_or_input_digest_change(self) -> None:
        a = InputRevision.create(prompt="A", images=(), measurement_constraints=(),
                                 profile_id="agv_compact_2wd_caster_v2", generation_settings={"model_id": "mock"})
        b = InputRevision.create(prompt="B", images=(), measurement_constraints=(),
                                 profile_id="agv_compact_2wd_caster_v2", generation_settings={"model_id": "mock"})
        self.assertTrue(generation_result_is_current(ticket=1, current_ticket=1,
                        requested_input_digest=a.digest, current_input_digest=a.digest))
        self.assertFalse(generation_result_is_current(ticket=1, current_ticket=2,
                         requested_input_digest=a.digest, current_input_digest=a.digest))
        self.assertFalse(generation_result_is_current(ticket=1, current_ticket=1,
                         requested_input_digest=a.digest, current_input_digest=b.digest))

    def test_canonical_hash_is_ordered_precise_and_rejects_nonfinite(self) -> None:
        self.assertEqual(canonical_sha256({"b": 1, "a": -0.0}), canonical_sha256({"a": 0.0, "b": 1}))
        self.assertNotEqual(canonical_sha256([1, 2]), canonical_sha256([2, 1]))
        self.assertNotEqual(canonical_sha256(1.0000001), canonical_sha256(1.0000002))
        with self.assertRaises(ValueError):
            canonical_sha256(float("nan"))

    def test_plan_hash_retains_alias_but_expanded_bundle_hash_normalizes_it(self) -> None:
        from twinpulse_core import SceneToolPlan, SceneToolCall
        plan = demo_warehouse_tool_plan()
        calls = list(plan.calls)
        index = next(i for i, call in enumerate(calls) if call.tool == "place_predefined_agv")
        robot = calls[index]
        calls[index] = SceneToolCall(robot.call_id, robot.tool,
                                    {**robot.arguments, "profile_id": "agv_compact_diff_v1"})
        alias = SceneToolPlan(plan.scene_id, plan.summary, plan.image_observations, tuple(calls))
        self.assertNotEqual(plan_digest(plan), plan_digest(alias))
        self.assertEqual(bundle_digest(SceneToolRegistry().execute(plan)),
                         bundle_digest(SceneToolRegistry().execute(alias)))

    def test_input_snapshot_immutable_and_secret_setting_rejected(self) -> None:
        revision = InputRevision.create(prompt="A", images=(("same.png", b"original"),),
                                        measurement_constraints=(), profile_id="agv_compact_2wd_caster_v2",
                                        generation_settings={"model_id": "mock"})
        with TemporaryDirectory(prefix="tmp-r1-", dir=TEST_TMP) as directory:
            store = InputArtifactStore(Path(directory) / "inputs")
            folder = store.save(revision, (("same.png", b"original"),))
            self.assertTrue((folder / "revision.json").is_file())
            self.assertEqual(len(list(folder.glob("*.bin"))), 1)
            with self.assertRaises(ValueError):
                store.save(revision, (("same.png", b"changed"),))
        with self.assertRaises(ValueError):
            InputRevision.create(prompt="A", images=(), measurement_constraints=(),
                                 profile_id="agv_compact_2wd_caster_v2",
                                 generation_settings={"api_key": "secret"})


if __name__ == "__main__":
    unittest.main()
