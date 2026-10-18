# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only reopening of a historical saved project, never a photo generator.

The authored draft is preserved as project data. New photographs use the
configured provider; neither image hashes nor room dimensions select a recipe.
"""
from hashlib import sha256
import json
from pathlib import Path

from twinpulse_core.revisions import canonical_sha256
from .site_draft import SiteDraftRecord

from .runtime_paths import resource_root
ROOT = resource_root()
SAVED_PROJECT = "artifacts/bedroom-twin-20260928-r2"


def saved_bedroom_manifest(root=ROOT):
    value = json.loads((Path(root) / SAVED_PROJECT / "manifest.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in value.items() if k != "manifest_sha256"}
    if value.get("manifest_sha256") != canonical_sha256(body):
        raise ValueError("Historical manifest changed")
    return value


def bedroom_draft(photo: bytes, root=ROOT) -> SiteDraftRecord:
    manifest = saved_bedroom_manifest(root)
    value = json.loads((Path(root) / SAVED_PROJECT / "site-draft.json").read_text(encoding="utf-8"))
    checked = SiteDraftRecord.from_dict(value)
    if (sha256(photo).hexdigest() != manifest["photo_sha256"]
            or checked.input_revision.images[0]["sha256"] != manifest["photo_sha256"]
            or canonical_sha256(checked.to_dict()) != manifest["draft_sha256"]
            or checked.site.scene.revision != manifest["scene_revision"]):
        raise ValueError("Historical project source changed")
    return checked


def bedroom_manifest(draft: SiteDraftRecord, asset_files: dict[str, str], root=ROOT) -> dict:
    checked = SiteDraftRecord.from_dict(draft.to_dict())
    previous = saved_bedroom_manifest(root)
    if (canonical_sha256(checked.to_dict()) != previous["draft_sha256"]
            or checked.site.scene.revision != previous["scene_revision"]):
        raise ValueError("Historical project draft mismatch")
    body = {k: v for k, v in previous.items() if k != "manifest_sha256"}
    body["asset_files_sha256"] = dict(asset_files)
    return {**body, "manifest_sha256": canonical_sha256(body)}
