# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Project-local, photo-derived site recipe; never a metric map or motion authority."""

from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Mapping

from twinpulse_core import InputArtifactStore, InputRevision, SiteToolPlan, canonical_sha256

from .image_validation import decode_image
from .project_store import ProjectRecord, ProjectStore, checked_project_id
from .site_draft import SiteDraftRecord


ROOM_RECIPE_VERSION = "room-recipe-1.0"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
# These are the already-reviewed local visual-only Burger bytes. A project may
# carry a portable copy, but may not turn arbitrary USD references into a Build.
_BURGER_HASHES = {
    "turtlebot3_burger.usda": "58af6e5f75f5cf96362f4abb175971dd555870add77c50a0baaa8028d2293b37",
    "payloads/base.usda": "750889ff799fbe55efe50af7a47e32c38d664ce50fb360aa1802d2daacfcb4f7",
    "payloads/geometries.usd": "0bda8f94edce82b534d2d58013ecaf8b33d6854a99827fe6fccfbd84a47cf43d",
    "payloads/instances.usda": "06798e126ee49d958c4201abdd8ef578eb9a6fc48eed7951c3171e005162aa55",
    "payloads/materials.usda": "2be307ad3d46d77b19c0bea7f229c66af8b35e3dcf7d00455f9ef44927b1328b",
    "payloads/robot.usda": "f384b6a2b53094a18e10b02b18f254f10c2c972a8b9cf8fcccbf2f0159f5ed36",
    "payloads/Physics/mujoco.usda": "a613ea9405af764aac0b31758b7703e18f74708d238fd8ad158d81a86b65cd98",
    "payloads/Physics/physics.usda": "8c1e6353f364638bd6e8d823351811a353ab5235588d395cf3f56f71c3482195",
    "payloads/Physics/physx.usda": "218b0c0f2b82c3859d184c59b8fd36b2b8c28b633609df7325906e370307408a",
}
_BURGER_FILES = frozenset(_BURGER_HASHES)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate room recipe key")
        value[key] = item
    return value


def _project_root(state_root: Path, project_id: str) -> Path:
    if checked_project_id(project_id) == "default":
        raise ValueError("the preserved default room uses its existing fixture adapter")
    expected = state_root.resolve() / "projects" / project_id
    if expected.exists() and expected.resolve() != expected:
        raise ValueError("project directory leaves the allowed root")
    return expected


def _asset_path(project_root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or len(relative) > 256 or "\\" in relative:
        raise ValueError("room asset path is invalid")
    parts = PurePosixPath(relative).parts
    if (len(parts) < 2 or len(parts) > 4 or parts[0] != "assets"
            or not all(_NAME.fullmatch(part) and part not in {".", ".."} for part in parts)):
        raise ValueError("room asset must be a project-relative assets path")
    path = project_root.joinpath(*parts)
    if path.is_symlink() or path.resolve() != project_root.resolve().joinpath(*parts):
        raise ValueError("room asset leaves the selected project")
    return path


def _checked_burger_files(asset_root: Path) -> dict[str, str]:
    if not asset_root.is_dir() or asset_root.is_symlink():
        raise ValueError("project Burger asset directory is missing or linked")
    contents = tuple(asset_root.rglob("*"))
    if (any(path.is_symlink() for path in contents)
            or {path.relative_to(asset_root).as_posix() for path in contents if path.is_file()} != _BURGER_FILES):
        raise ValueError("project Burger asset files are missing, extra or linked")
    hashes = {}
    for name in sorted(_BURGER_FILES):
        path = asset_root.joinpath(*PurePosixPath(name).parts)
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("project Burger asset file is invalid")
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != _BURGER_HASHES[name]:
            raise ValueError("project Burger asset hash changed")
        hashes[name] = actual
    return hashes


def load_project_room_recipe(state_root: Path, project_id: str) -> tuple[SiteDraftRecord, bytes]:
    """Rebuild the draft from a bounded photo and allowlisted existing site plan."""
    project_root = _project_root(state_root, project_id)
    recipe_path = project_root / "room_recipe.json"
    if recipe_path.is_symlink() or not recipe_path.is_file() or recipe_path.stat().st_size > 128 * 1024:
        raise ValueError("project room recipe is missing or invalid")
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if (not isinstance(recipe, Mapping)
            or set(recipe) not in ({"schema_version", "project_id", "prompt", "photo", "plan"},
                                   {"schema_version", "project_id", "prompt", "photo", "plan", "burger_visual"})
            or recipe["schema_version"] != ROOM_RECIPE_VERSION or recipe["project_id"] != project_id
            or not isinstance(recipe["prompt"], str) or not 1 <= len(recipe["prompt"].strip()) <= 500
            or not isinstance(recipe["photo"], Mapping)
            or set(recipe["photo"]) != {"relative_path", "sha256"}
            or not isinstance(recipe["photo"]["sha256"], str)
            or not _HEX.fullmatch(recipe["photo"]["sha256"])):
        raise ValueError("project room recipe shape or version is unsupported")
    photo_path = _asset_path(project_root, recipe["photo"]["relative_path"])
    if not photo_path.is_file() or photo_path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("project room photo is missing or too large")
    photo = photo_path.read_bytes()
    if sha256(photo).hexdigest() != recipe["photo"]["sha256"]:
        raise ValueError("project room photo hash changed")
    media_type = decode_image(photo, max_pixels=40_000_000).media_type
    plan = SiteToolPlan.from_dict(recipe["plan"])
    if (plan.call_evidence is None
            or any(call.tool in {"place_predefined_agv", "create_navigation_task"} for call in plan.calls)
            or any(item.basis == "trusted_measurement" for item in plan.call_evidence)):
        raise ValueError("photo recipe cannot assert measured geometry or a driven mission")
    revision = InputRevision.create(
        prompt=recipe["prompt"], images=((photo_path.name, media_type, photo),),
        measurement_constraints=(), profile_id="visual-room-unqualified",
        generation_settings={"adapter_kind": f"{ROOM_RECIPE_VERSION}:{canonical_sha256(recipe)}"},
        input_kind="photo",
    )
    draft = SiteDraftRecord.create(
        request_id=f"room-{canonical_sha256(recipe)[:20]}", provider_name="local-room-recipe",
        model_id="no-provider-call", image_count=1, input_revision=revision, plan=plan,
    )
    if "burger_visual" in recipe:
        _checked_visual(project_root, project_id, draft, recipe["burger_visual"])
    return draft, photo


def _checked_visual(project_root: Path, project_id: str, draft: SiteDraftRecord,
                    visual: object) -> tuple[dict, Path]:
    if (not isinstance(visual, Mapping)
            or set(visual) != {"asset_dir", "files_sha256", "position_m", "yaw_deg"}
            or visual["asset_dir"] != "assets/burger"
            or not isinstance(visual["files_sha256"], Mapping)
            or set(visual["files_sha256"]) != _BURGER_FILES):
        raise ValueError("project Burger visual manifest is invalid")
    position = visual["position_m"]
    yaw = visual["yaw_deg"]
    if (not isinstance(position, list) or len(position) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 20 for value in position)
            or position[2] < 0 or position[2] > 1
            or type(yaw) not in (int, float) or not math.isfinite(yaw) or abs(yaw) > 180):
        raise ValueError("project Burger placement is invalid")
    asset_root = _asset_path(project_root, visual["asset_dir"])
    hashes = _checked_burger_files(asset_root)
    if dict(visual["files_sha256"]) != hashes:
        raise ValueError("project Burger asset hash changed")
    body = {
        "schema_version": "project-room-visual-1.0", "project_id": project_id,
        "draft_sha256": canonical_sha256(draft.to_dict()),
        "scene_revision": draft.site.scene.revision,
        "photo_sha256": draft.input_revision.images[0]["sha256"],
        "geometry_status": "PHOTO_APPROXIMATION_NOT_SURVEYED",
        "sensor_to_world_transform": None, "alignment_verified": False,
        "robot_placement": {
            "asset_id": "project-local-turtlebot3-burger-visual",
            "position_m": list(position), "yaw_deg": yaw,
            "pose_status": "ILLUSTRATIVE_NOT_MEASURED", "physics_variant": "none",
        },
        "asset_files_sha256": hashes,
        "physical_robot_match": "UNVERIFIED", "execution_authority": False,
        "physical_validation": "NOT_RUN",
    }
    return {**body, "manifest_sha256": canonical_sha256(body)}, asset_root


def load_project_room_visual(state_root: Path, project_id: str,
                             draft: SiteDraftRecord) -> tuple[dict, Path] | None:
    """Optional pinned visual asset; absence means scene-only, never a fallback fixture."""
    project_root = _project_root(state_root, project_id)
    recipe_path = project_root / "room_recipe.json"
    if recipe_path.is_symlink() or not recipe_path.is_file() or recipe_path.stat().st_size > 128 * 1024:
        raise ValueError("project room recipe is missing or invalid")
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if "burger_visual" not in recipe:
        return None
    expected_draft, _ = load_project_room_recipe(state_root, project_id)
    if expected_draft != draft:
        raise ValueError("project Burger visual belongs to a different room draft")
    return _checked_visual(project_root, project_id, draft, recipe["burger_visual"])


def checked_project_room_descriptor(descriptor: object, scene, state_root: Path,
                                    project_id: str) -> tuple[SiteDraftRecord, dict, Path]:
    if (not isinstance(descriptor, Mapping)
            or set(descriptor) not in ({"kind", "manifest_sha256"},
                                       {"kind", "manifest_sha256", "scene_change_revision"})
            or descriptor["kind"] != "project_room_visual_v1"):
        raise ValueError("project room visual descriptor is invalid")
    draft, _ = load_project_room_recipe(state_root, project_id)
    result = load_project_room_visual(state_root, project_id, draft)
    if result is None:
        raise ValueError("project room has no pinned Burger visual")
    manifest, asset_root = result
    expected_scene = draft.site.scene
    if "scene_change_revision" in descriptor:
        from .scene_changes import SceneChangeStore
        from .project_store import ProjectStore
        project_path = ProjectStore.for_project(state_root, project_id).path
        history = SceneChangeStore(project_path.with_suffix(".scene-changes.json"),
                                   project_id=project_id, source=draft).load()
        if not history.operations:
            raise ValueError("project room has no saved scene edits")
        expected_scene = history.replay(draft)[1].scene
        if descriptor["scene_change_revision"] != expected_scene.revision:
            raise ValueError("project room edit revision changed")
    if (descriptor["manifest_sha256"] != manifest["manifest_sha256"]
            or canonical_sha256(scene.to_dict()) != canonical_sha256(expected_scene.to_dict())):
        raise ValueError("project room visual does not match current scene and assets")
    return draft, manifest, asset_root


def prepare_project_burger_visual(state_root: Path, project_id: str,
                                  position_m: tuple[float, float, float], yaw_deg: float) -> dict:
    """Explicitly copy the pinned local visual into an unimported room project.

    A backup of the authored recipe is kept. This never imports the project,
    creates a simulation, starts a provider or grants motion authority.
    """
    project_root = _project_root(state_root, project_id)
    recipe_path = project_root / "room_recipe.json"
    backup_path = project_root / "room_recipe.before-burger.json"
    temporary_path = project_root / "room_recipe.burger.tmp"
    asset_root = project_root / "assets" / "burger"
    current = ProjectStore.for_project(state_root, project_id).load()
    if ((current is not None and (current.latest_input or current.draft or current.site_draft))
            or backup_path.exists() or temporary_path.exists() or asset_root.exists()):
        raise ValueError("project is already imported or Burger preparation exists")
    draft, _ = load_project_room_recipe(state_root, project_id)
    from .bedroom_review import ASSET_RELATIVE, ROOT
    source = (ROOT / ASSET_RELATIVE).resolve()
    if not source.is_relative_to(ROOT.resolve()):
        raise ValueError("pinned Burger source leaves the repository")
    hashes = _checked_burger_files(source)
    visual = {
        "asset_dir": "assets/burger", "files_sha256": hashes,
        "position_m": list(position_m), "yaw_deg": yaw_deg,
    }
    original = recipe_path.read_bytes()
    recipe = json.loads(original.decode("utf-8"), object_pairs_hook=_unique_object)
    if "burger_visual" in recipe:
        raise ValueError("project recipe already declares a Burger visual")
    # Reject invalid pose before creating a directory or modifying the recipe.
    if (len(position_m) != 3 or any(type(value) not in (int, float) or not math.isfinite(value)
                                    or abs(value) > 20 for value in position_m)
            or position_m[2] < 0 or position_m[2] > 1
            or type(yaw_deg) not in (int, float) or not math.isfinite(yaw_deg) or abs(yaw_deg) > 180):
        raise ValueError("project Burger placement is invalid")
    # A fixed list, never a user-supplied source path or recursive arbitrary tree.
    asset_root.mkdir(parents=True, exist_ok=False)
    for name in sorted(_BURGER_FILES):
        destination = asset_root.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.joinpath(*PurePosixPath(name).parts), destination)
    _checked_visual(project_root, project_id, draft, visual)
    recipe["burger_visual"] = visual
    encoded = (json.dumps(recipe, ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    # Never overwrite pre-existing backup/temp paths; interrupted work remains visible.
    with backup_path.open("xb") as stream:
        stream.write(original)
    with temporary_path.open("xb") as stream:
        stream.write(encoded)
    os.replace(temporary_path, recipe_path)
    checked_draft, _ = load_project_room_recipe(state_root, project_id)
    result = load_project_room_visual(state_root, project_id, checked_draft)
    if result is None:
        raise ValueError("project Burger visual preparation did not validate")
    return result[0]


def verify_project_room_record(record: ProjectRecord, state_root: Path) -> None:
    if record.site_draft is None:
        return
    kind = record.site_draft.input_revision.generation_settings.get("adapter_kind", "")
    named_provider = record.site_draft.provider_name == "local-room-recipe"
    named_kind = kind.startswith(ROOM_RECIPE_VERSION + ":")
    if named_provider != named_kind:
        raise ValueError("stored room recipe provenance is inconsistent")
    if not named_kind:
        return
    draft, _ = load_project_room_recipe(state_root, record.project_id)
    if draft != record.site_draft or record.latest_input != draft.input_revision:
        raise ValueError("stored room draft does not match current recipe and photo")


def import_project_room_recipe(state_root: Path, project_id: str) -> SiteDraftRecord:
    """Explicit offline import; never overwrites an existing draft or runs Build."""
    draft, photo = load_project_room_recipe(state_root, project_id)
    store = ProjectStore.for_project(state_root, project_id)
    current = store.load()
    if current is not None and (current.latest_input or current.draft or current.site_draft):
        raise ValueError("project already contains input or a draft")
    InputArtifactStore(store.input_root()).save(
        draft.input_revision, ((draft.input_revision.images[0]["name"], photo),))
    store.save(ProjectRecord(project_id, latest_input=draft.input_revision, site_draft=draft))
    return draft
