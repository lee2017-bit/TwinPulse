# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicitly import a project-local photo room recipe into the existing App store."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_app.room_recipe import (  # noqa: E402
    import_project_room_recipe, load_project_room_visual, prepare_project_burger_visual,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a reviewed local photo recipe; never run a simulation or robot")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--include-local-burger-visual", action="store_true",
                        help="Explicitly copy the reviewed visual-only Burger bytes into this new project")
    parser.add_argument("--visual-x-m", type=float)
    parser.add_argument("--visual-y-m", type=float)
    parser.add_argument("--visual-yaw-deg", type=float)
    args = parser.parse_args()
    if args.include_local_burger_visual and args.state_dir is None:
        parser.error("Burger visual preparation requires an explicit --state-dir")
    state_dir = args.state_dir or Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime")) / "TwinPulse" / "runtime"
    pose = (args.visual_x_m, args.visual_y_m, args.visual_yaw_deg)
    if args.include_local_burger_visual:
        if any(value is None for value in pose):
            parser.error("Burger visual requires --visual-x-m, --visual-y-m, and --visual-yaw-deg")
        prepare_project_burger_visual(
            state_dir, args.project_id,
            (args.visual_x_m, args.visual_y_m, 0.002), args.visual_yaw_deg)
    elif any(value is not None for value in pose):
        parser.error("visual placement requires --include-local-burger-visual")
    draft = import_project_room_recipe(state_dir, args.project_id)
    print(json.dumps({"project_id": args.project_id, "scene_revision": draft.site.scene.revision,
                      "review_required": True, "build_started": False, "physical_validation": "NOT_RUN",
                      "burger_visual_prepared": load_project_room_visual(
                          state_dir, args.project_id, draft) is not None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
