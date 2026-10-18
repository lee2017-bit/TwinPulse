# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Build source-bound product draft using local photo and existing Burger assets."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
from twinpulse_app.bedroom_twin import bedroom_draft, bedroom_manifest, saved_bedroom_manifest

ASSET_ROOT = ROOT / "artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1"
ASSET_ENTRY = ASSET_ROOT / "turtlebot3_burger.usda"
PHOTO_ROOT = ROOT / "artifacts/photo-scan-review-20260927"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset_hashes():
    if not ASSET_ENTRY.is_file():
        raise ValueError("Existing imported Burger asset is missing; no automatic download")
    files = sorted(path for path in ASSET_ROOT.rglob("*") if path.is_file())
    if not files or any(not path.resolve().is_relative_to(ASSET_ROOT.resolve()) for path in files):
        raise ValueError("Asset dependencies must remain in the existing local asset directory")
    return {path.relative_to(ASSET_ROOT).as_posix(): digest(path) for path in files}


def prepare(output):
    draft = bedroom_draft((PHOTO_ROOT / "room.jpg").read_bytes())
    if digest(PHOTO_ROOT / "top-view-window-up.jpg") != saved_bedroom_manifest()["direction_photo_sha256"]:
        raise ValueError("Window-direction photograph differs from preserved source")
    manifest = bedroom_manifest(draft, asset_hashes())
    # Never overwrite a prior run or modify the existing active product project.
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("site-draft.json", draft.to_dict()), ("manifest.json", manifest)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    record, manifest = prepare(args.output.resolve())
    print(json.dumps({"status": "DRAFT_PREPARED", "scene_revision": record.site.scene.revision,
                      "physical_validation": "NOT_RUN", "output": str(args.output)}, indent=2))
