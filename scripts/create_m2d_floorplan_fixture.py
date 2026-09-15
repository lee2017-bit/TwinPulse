"""Create a deterministic dimensioned warehouse floor-plan PNG for M2-D."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS = (1400, 1100)
ORIGIN = (700, 610)
PIXELS_PER_METER = 90


def _measurement_sidecar(source_image: str) -> dict[str, object]:
    source = "dimensioned_drawing_sidecar"
    return {
        "schema_version": "1.0",
        "source_image": source_image,
        "measurement_constraints": [
            {"constraint_id": "floor_size", "tool": "create_floor", "argument_path": "size_m", "expected": [12.0, 8.0], "tolerance": 0.1, "occurrence": 0, "source": source},
            {"constraint_id": "rack_length", "tool": "create_rack_row", "argument_path": "length_m", "expected": 8.0, "tolerance": 0.1, "occurrence": None, "source": source},
            {"constraint_id": "rack_depth", "tool": "create_rack_row", "argument_path": "depth_m", "expected": 1.5, "tolerance": 0.1, "occurrence": None, "source": source},
            {"constraint_id": "rack_height", "tool": "create_rack_row", "argument_path": "height_m", "expected": 3.0, "tolerance": 0.25, "occurrence": None, "source": source},
            {"constraint_id": "rack_bays", "tool": "create_rack_row", "argument_path": "bay_count", "expected": 5.0, "tolerance": 0.0, "occurrence": None, "source": source},
            {"constraint_id": "wall_height", "tool": "create_wall", "argument_path": "dimensions_m.2", "expected": 2.5, "tolerance": 0.1, "occurrence": None, "source": source},
            {"constraint_id": "agv_start", "tool": "place_predefined_agv", "argument_path": "position_m", "expected": [-4.0, 0.0], "tolerance": 0.1, "occurrence": 0, "source": source},
            {"constraint_id": "agv_goal", "tool": "create_navigation_task", "argument_path": "goal_m", "expected": [4.0, 0.0], "tolerance": 0.1, "occurrence": 0, "source": source},
        ],
    }


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
    except OSError:
        return ImageFont.load_default()


def _xy(x_m: float, y_m: float) -> tuple[int, int]:
    return (
        int(ORIGIN[0] + x_m * PIXELS_PER_METER),
        int(ORIGIN[1] - y_m * PIXELS_PER_METER),
    )


def _rect(draw: ImageDraw.ImageDraw, center: tuple[float, float], size: tuple[float, float], **kwargs: object) -> None:
    half_x, half_y = size[0] / 2.0, size[1] / 2.0
    left, top = _xy(center[0] - half_x, center[1] + half_y)
    right, bottom = _xy(center[0] + half_x, center[1] - half_y)
    draw.rectangle((left, top, right, bottom), **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    image = Image.new("RGB", CANVAS, "white")
    draw = ImageDraw.Draw(image)
    title = _font(36, bold=True)
    label = _font(25, bold=True)
    body = _font(21)
    small = _font(18)

    draw.text((70, 35), "TWINPULSE DIMENSIONED WAREHOUSE FLOOR PLAN", fill="#111827", font=title)
    draw.text((70, 82), "TOP VIEW  |  ALL DIMENSIONS IN METERS  |  NORTH UP", fill="#374151", font=body)

    # Authoritative 12 m x 8 m floor boundary.
    _rect(draw, (0.0, 0.0), (12.0, 8.0), fill="#f8fafc", outline="#111827", width=7)

    # Two rack rows: exact 8.0 m length, 1.5 m depth, 3.0 m height.
    for name, y_m in (("RACK A", 2.6), ("RACK B", -2.6)):
        _rect(draw, (0.0, y_m), (8.0, 1.5), fill="#bfdbfe", outline="#1d4ed8", width=5)
        left, top = _xy(-4.0, y_m + 0.75)
        right, bottom = _xy(4.0, y_m - 0.75)
        for bay in range(1, 5):
            x = int(left + (right - left) * bay / 5)
            draw.line((x, top, x, bottom), fill="#1d4ed8", width=3)
        text_box = draw.textbbox((0, 0), name, font=label)
        center_px = _xy(0.0, y_m)
        draw.text(
            (center_px[0] - (text_box[2] - text_box[0]) / 2, center_px[1] - 14),
            name,
            fill="#1e3a8a",
            font=label,
        )

    # Central clear aisle and its exact width annotation.
    _rect(draw, (0.0, 0.0), (10.5, 2.0), fill="#f3f4f6", outline="#9ca3af", width=2)
    draw.text((575, 520), "CLEAR CENTER AISLE", fill="#4b5563", font=body)
    draw.text((620, 553), "WIDTH 2.0 m", fill="#4b5563", font=small)

    # Route is deliberately positive X to match the currently validated controller.
    start = _xy(-4.0, 0.0)
    goal = _xy(4.0, 0.0)
    draw.line((start, goal), fill="#16a34a", width=10)
    draw.polygon(((goal[0], goal[1]), (goal[0] - 25, goal[1] - 16), (goal[0] - 25, goal[1] + 16)), fill="#16a34a")
    draw.ellipse((start[0] - 17, start[1] - 17, start[0] + 17, start[1] + 17), fill="#22c55e", outline="#14532d", width=3)
    draw.ellipse((goal[0] - 17, goal[1] - 17, goal[0] + 17, goal[1] + 17), fill="#ef4444", outline="#7f1d1d", width=3)
    draw.text((start[0] - 68, start[1] + 24), "START (-4, 0)", fill="#14532d", font=small)
    draw.text((goal[0] - 34, goal[1] + 24), "GOAL (4, 0)", fill="#7f1d1d", font=small)
    draw.text((620, 665), "8.0 m AGV ROUTE", fill="#166534", font=small)

    # Dimension callouts and wall height define how the 2D plan should become 3D.
    draw.line((_xy(-6, -4.35), _xy(6, -4.35)), fill="#111827", width=3)
    draw.text((625, 1015), "12.0 m", fill="#111827", font=label)
    draw.line((_xy(-6.35, -4), _xy(-6.35, 4)), fill="#111827", width=3)
    draw.text((70, 595), "8.0 m", fill="#111827", font=label)
    draw.text((865, 120), "FLOOR: 12.0 m x 8.0 m", fill="#111827", font=body)
    draw.text((865, 151), "RACKS: 8.0 x 1.5 x 3.0 m HIGH", fill="#1e3a8a", font=body)
    draw.text((865, 182), "PERIMETER WALLS: 2.5 m HIGH", fill="#111827", font=body)
    draw.text((865, 213), "KEEP CENTER AISLE CLEAR", fill="#166534", font=body)

    draw.polygon(((1320, 125), (1300, 170), (1340, 170)), fill="#111827")
    draw.text((1300, 177), "N", fill="#111827", font=label)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="PNG", optimize=True)
    sidecar_path = args.output.with_suffix(".measurements.json")
    sidecar_path.write_text(
        json.dumps(_measurement_sidecar(args.output.name), indent=2) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f"output={args.output}")
    print(f"bytes={args.output.stat().st_size}")
    print(f"sha256={digest}")
    print(f"measurement_sidecar={sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
