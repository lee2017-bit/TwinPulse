"""Deterministic M1 fixtures shared by tests and the Extension."""

from __future__ import annotations

from .models import SceneObject, SceneSpec, ShapeSpec, SpecBundle, TaskSpec, Transform
from .robot_profiles import compact_2wd_caster_profile


def fixed_warehouse_bundle() -> SpecBundle:
    robot = compact_2wd_caster_profile()
    scene = SceneSpec(
        id="warehouse_fixed_v1",
        robot_profile_id=robot.id,
        objects=(
            SceneObject(
                id="floor_main",
                kind="floor",
                transform=Transform((0.0, 0.0, -0.05)),
                shape=ShapeSpec("box", (8.0, 6.0, 0.10)),
            ),
            SceneObject(
                id="wall_left",
                kind="wall",
                transform=Transform((0.0, 3.0, 0.50)),
                shape=ShapeSpec("box", (8.0, 0.10, 1.0)),
            ),
            SceneObject(
                id="wall_right",
                kind="wall",
                transform=Transform((0.0, -3.0, 0.50)),
                shape=ShapeSpec("box", (8.0, 0.10, 1.0)),
            ),
            SceneObject(
                id="rack_north",
                kind="rack",
                transform=Transform((1.5, 1.6, 0.75)),
                shape=ShapeSpec("box", (2.0, 0.60, 1.50)),
            ),
            SceneObject(
                id="rack_south",
                kind="rack",
                transform=Transform((1.5, -1.6, 0.75)),
                shape=ShapeSpec("box", (2.0, 0.60, 1.50)),
            ),
            SceneObject(
                id="box_demo",
                kind="box",
                transform=Transform((-1.0, 1.2, 0.25)),
                shape=ShapeSpec("box", (0.50, 0.50, 0.50)),
            ),
        ),
    )
    task = TaskSpec(
        id="smoke_route_v1",
        robot_profile_id=robot.id,
        start=Transform((0.0, 0.0, 0.0)),
        # Long enough to be clearly visible in the interactive Playground while
        # remaining inside the unobstructed center aisle.
        goal=Transform((1.50, 0.0, 0.0)),
        position_tolerance_m=0.05,
    )
    return SpecBundle(scene=scene, robot=robot, task=task)
