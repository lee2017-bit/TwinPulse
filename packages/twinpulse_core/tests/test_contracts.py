from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import unittest


CORE_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(CORE_SRC))

from twinpulse_core import (  # noqa: E402
    GeneratedDraftRecord,
    EpisodeSample,
    SceneObject,
    SceneToolCall,
    SceneToolPlanError,
    SceneToolRegistry,
    ShapeSpec,
    SpecValidationError,
    ValidationLimits,
    bundle_from_json,
    bundle_to_json,
    demo_warehouse_tool_plan,
    fixed_warehouse_bundle,
    assess_episode,
    compact_2wd_caster_profile,
    resolve_robot_profile,
    straight_route_command,
    validate_bundle,
    validate_current_controller_route,
)


class ContractTests(unittest.TestCase):
    def test_compact_profile_separates_drive_and_support_contacts(self) -> None:
        profile = compact_2wd_caster_profile()
        self.assertEqual(profile.drive_wheel_count, 2)
        self.assertEqual(len(profile.support_wheels), 2)
        self.assertEqual(profile.contact_count, 4)
        self.assertEqual(resolve_robot_profile("agv_compact_diff_v1"), profile)

    def test_episode_assessment_rejects_nose_dive(self) -> None:
        bundle = fixed_warehouse_bundle()
        samples = [
            EpisodeSample(0.0, bundle.task.start.position_m, (0.0, 0.0, 0.0)),
            EpisodeSample(1.0, bundle.task.goal.position_m, (0.0, math.radians(30.0), 0.0)),
        ]
        result = assess_episode(
            bundle,
            samples,
            final_state="completed",
            observed_support_wheels=2,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("pitch" in violation for violation in result.violations))

    def test_episode_assessment_accepts_stable_supported_drive(self) -> None:
        bundle = fixed_warehouse_bundle()
        samples = [
            EpisodeSample(0.0, bundle.task.start.position_m, (0.0, 0.0, 0.0)),
            EpisodeSample(1.0, bundle.task.goal.position_m, (0.0, math.radians(1.0), 0.0)),
        ]
        result = assess_episode(
            bundle,
            samples,
            final_state="completed",
            observed_support_wheels=2,
        )
        self.assertTrue(result.passed, result.violations)

    def test_episode_assessment_counts_intentional_geometric_collision(self) -> None:
        bundle = fixed_warehouse_bundle()
        obstacle = SceneObject(
            id="intentional_collision_box",
            kind="box",
            transform=replace(bundle.task.goal, position_m=(*bundle.task.goal.position_m[:2], 0.25)),
            shape=ShapeSpec("box", (0.5, 0.5, 0.5)),
        )
        collision_bundle = replace(
            bundle,
            scene=replace(bundle.scene, objects=(*bundle.scene.objects, obstacle)),
        )
        result = assess_episode(
            collision_bundle,
            [EpisodeSample(1.0, bundle.task.goal.position_m, (0.0, 0.0, 0.0))],
            final_state="completed",
            observed_support_wheels=2,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.geometric_collision_samples, 1)
        self.assertTrue(any("overlapped colliders" in violation for violation in result.violations))

    def test_closed_loop_route_command_recovers_heading_and_lateral_error(self) -> None:
        position = [0.0, 0.06]
        yaw = math.radians(4.0)
        maximum_lateral_error = abs(position[1])
        for _ in range(2400):
            command = straight_route_command(
                position_xy_m=(position[0], position[1]),
                yaw_rad=yaw,
                start_xy_m=(0.0, 0.0),
                goal_xy_m=(6.9, 0.0),
                position_tolerance_m=0.05,
                max_linear_speed_mps=0.25,
                max_angular_speed_rps=math.radians(45.0),
            )
            if command.completed:
                break
            self.assertFalse(command.off_route)
            step_s = 1.0 / 60.0
            yaw += command.angular_rps * step_s
            position[0] += command.linear_mps * math.cos(yaw) * step_s
            position[1] += command.linear_mps * math.sin(yaw) * step_s
            maximum_lateral_error = max(maximum_lateral_error, abs(position[1]))

        self.assertTrue(command.completed)
        self.assertLess(math.hypot(6.9 - position[0], position[1]), 0.05)
        self.assertLess(maximum_lateral_error, 0.08)

    def test_closed_loop_route_command_stops_outside_protected_aisle(self) -> None:
        command = straight_route_command(
            position_xy_m=(2.0, 0.21),
            yaw_rad=0.0,
            start_xy_m=(0.0, 0.0),
            goal_xy_m=(6.9, 0.0),
            position_tolerance_m=0.05,
            max_linear_speed_mps=0.25,
            max_angular_speed_rps=math.radians(45.0),
        )
        self.assertTrue(command.off_route)
        self.assertEqual((command.linear_mps, command.angular_rps), (0.0, 0.0))

    def test_fixed_fixture_is_valid(self) -> None:
        bundle = fixed_warehouse_bundle()
        self.assertIs(validate_bundle(bundle), bundle)

    def test_json_round_trip_is_stable(self) -> None:
        first = fixed_warehouse_bundle()
        payload = bundle_to_json(first)
        second = bundle_from_json(payload)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(payload), json.loads(bundle_to_json(second)))

    def test_negative_dimension_is_rejected(self) -> None:
        bundle = fixed_warehouse_bundle()
        broken_object = replace(bundle.scene.objects[0], shape=ShapeSpec("box", (8.0, -1.0, 0.1)))
        broken_scene = replace(bundle.scene, objects=(broken_object, *bundle.scene.objects[1:]))
        with self.assertRaisesRegex(SpecValidationError, "dimensions_m"):
            validate_bundle(replace(bundle, scene=broken_scene))

    def test_non_finite_position_is_rejected(self) -> None:
        bundle = fixed_warehouse_bundle()
        broken_task = replace(bundle.task, goal=replace(bundle.task.goal, position_m=(math.nan, 0.0, 0.0)))
        with self.assertRaisesRegex(SpecValidationError, "finite"):
            validate_bundle(replace(bundle, task=broken_task))

    def test_duplicate_ids_are_rejected(self) -> None:
        bundle = fixed_warehouse_bundle()
        duplicate = replace(bundle.scene.objects[1], id=bundle.scene.objects[0].id)
        broken_scene = replace(bundle.scene, objects=(bundle.scene.objects[0], duplicate))
        with self.assertRaisesRegex(SpecValidationError, "unique"):
            validate_bundle(replace(bundle, scene=broken_scene))

    def test_unknown_robot_reference_is_rejected(self) -> None:
        bundle = fixed_warehouse_bundle()
        with self.assertRaisesRegex(SpecValidationError, "unknown robot"):
            validate_bundle(replace(bundle, scene=replace(bundle.scene, robot_profile_id="missing_robot")))

    def test_asset_must_be_allowlisted(self) -> None:
        bundle = fixed_warehouse_bundle()
        asset_object = replace(bundle.scene.objects[0], asset_id="vendor/private_asset")
        broken_scene = replace(bundle.scene, objects=(asset_object, *bundle.scene.objects[1:]))
        with self.assertRaisesRegex(SpecValidationError, "allowlisted"):
            validate_bundle(replace(bundle, scene=broken_scene))

    def test_operation_must_be_allowlisted(self) -> None:
        bundle = fixed_warehouse_bundle()
        broken = replace(bundle, task=replace(bundle.task, operation="run_shell"), allowed_operations=("run_shell",))
        with self.assertRaisesRegex(SpecValidationError, "operation"):
            validate_bundle(broken)

    def test_object_limit_is_configurable(self) -> None:
        bundle = fixed_warehouse_bundle()
        with self.assertRaisesRegex(SpecValidationError, "object count"):
            validate_bundle(bundle, ValidationLimits(max_objects=2))

    def test_dynamic_object_requires_mass(self) -> None:
        bundle = fixed_warehouse_bundle()
        dynamic = SceneObject(
            id="dynamic_box",
            kind="box",
            transform=bundle.scene.objects[0].transform,
            shape=ShapeSpec("box", (0.2, 0.2, 0.2)),
            dynamic=True,
        )
        with self.assertRaisesRegex(SpecValidationError, "mass_kg"):
            validate_bundle(replace(bundle, scene=replace(bundle.scene, objects=(dynamic,))))

    def test_current_controller_accepts_fixed_clear_route(self) -> None:
        bundle = fixed_warehouse_bundle()
        self.assertIs(validate_current_controller_route(bundle), bundle)

    def test_current_controller_rejects_sideways_goal(self) -> None:
        bundle = fixed_warehouse_bundle()
        sideways = replace(bundle.task, goal=replace(bundle.task.goal, position_m=(1.5, 0.5, 0.0)))
        with self.assertRaisesRegex(SpecValidationError, "positive-X straight route"):
            validate_current_controller_route(replace(bundle, task=sideways))

    def test_current_controller_rejects_blocked_route(self) -> None:
        bundle = fixed_warehouse_bundle()
        obstacle = SceneObject(
            id="blocked_route_box",
            kind="box",
            transform=replace(bundle.task.start, position_m=(0.75, 0.0, 0.25)),
            shape=ShapeSpec("box", (0.5, 0.5, 0.5)),
        )
        blocked_scene = replace(bundle.scene, objects=(*bundle.scene.objects, obstacle))
        with self.assertRaisesRegex(SpecValidationError, "blocked"):
            validate_current_controller_route(replace(bundle, scene=blocked_scene))

    def test_allowlisted_scene_tool_plan_expands_rack_rows(self) -> None:
        plan = demo_warehouse_tool_plan()
        receipt = SceneToolRegistry().execute_with_receipt(plan)
        bundle = receipt.bundle
        self.assertEqual(bundle.scene.id, plan.scene_id)
        self.assertGreater(len(bundle.scene.objects), len(plan.calls))
        self.assertEqual(sum(item.kind == "rack" for item in bundle.scene.objects), 16)
        self.assertEqual(receipt.domains, ("scene", "robot", "task"))
        self.assertEqual(receipt.robot_profile_id, "agv_compact_2wd_caster_v2")

    def test_unknown_scene_tool_is_rejected(self) -> None:
        plan = demo_warehouse_tool_plan()
        malicious = SceneToolCall("unsafe", "run_shell", {"command": "whoami"})
        with self.assertRaisesRegex(SceneToolPlanError, "not allowlisted"):
            SceneToolRegistry().execute(replace(plan, calls=(*plan.calls, malicious)))

    def test_scene_tool_extra_argument_is_rejected(self) -> None:
        plan = demo_warehouse_tool_plan()
        first = plan.calls[0]
        tampered = replace(first, arguments={**first.arguments, "url": "https://example.invalid"})
        with self.assertRaisesRegex(SceneToolPlanError, "extra"):
            SceneToolRegistry().execute(replace(plan, calls=(tampered, *plan.calls[1:])))

    def test_generated_draft_record_round_trip_reexecutes_plan(self) -> None:
        plan = demo_warehouse_tool_plan()
        record = GeneratedDraftRecord.create(
            request_id="request-1",
            provider_name="test",
            model_id="test-model",
            image_count=1,
            plan=plan,
        )
        loaded = GeneratedDraftRecord.from_dict(record.to_dict())
        self.assertEqual(loaded.plan, plan)
        self.assertEqual(loaded.bundle, SceneToolRegistry().execute(plan))

    def test_generated_draft_hash_tamper_is_rejected(self) -> None:
        plan = demo_warehouse_tool_plan()
        record = GeneratedDraftRecord.create(
            request_id="request-1",
            provider_name="test",
            model_id="test-model",
            image_count=0,
            plan=plan,
        )
        value = record.to_dict()
        value["plan_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            GeneratedDraftRecord.from_dict(value)


if __name__ == "__main__":
    unittest.main()
