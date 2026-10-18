# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Credential-free, versioned input and validation identities for R1.

Hashes identify bytes/contracts, not authorship. Every load/build must revalidate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from .models import SpecBundle
from .scene_tools import SceneToolPlan, validate_scene_tool_plan


INPUT_REVISION_VERSION = "1.0"
VALIDATOR_VERSION = "r1.1"
_NON_SECRET_SETTING_KEYS = frozenset({
    "base_url", "model_id", "reasoning_effort", "image_detail", "request_schema",
    "tool_catalog_revision", "adapter_kind", "provider_profile", "endpoint_path",
    "observer_model_id", "observer_base_url", "fallback_observer_model_id", "site_plan_version",
    "planner_reasoning_effort",
    "observer_max_output_tokens", "planner_max_output_tokens",
    "generation_timeout_s",
    "observer_thinking_mode", "planner_thinking_mode", "generation_policy_sha256", "model_catalog_sha256",
    "harness_composer_revision", "observer_harness_sha256", "planner_harness_sha256",
})


def canonical_sha256(value: Any) -> str:
    """Digest strict JSON, sorted object keys and ordered arrays, without rounding."""

    def normalize(item: Any) -> Any:
        # Exact JSON builtins dominate sensor grids. Avoid thousands of ABC
        # checks, retaining the same bytes and the Mapping-first fallback for
        # custom/subclass objects. No rounding or cached digest is introduced.
        kind=type(item)
        if kind in (str,int,bool) or item is None:return item
        if kind is float:
            if not math.isfinite(item):raise ValueError("canonical numbers must be finite")
            return 0.0 if item == 0 else item
        if kind in (list,tuple):return [normalize(part) for part in item]
        if kind is dict:
            if not all(isinstance(key,str) for key in item):raise ValueError("canonical object keys must be strings")
            return {key:normalize(item[key]) for key in sorted(item)}
        if isinstance(item, Mapping):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("canonical object keys must be strings")
            return {key: normalize(item[key]) for key in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [normalize(part) for part in item]
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("canonical numbers must be finite")
            return 0.0 if item == 0 else item
        if isinstance(item, (str, int, bool)) or item is None:
            return item
        raise ValueError(f"unsupported canonical value: {type(item).__name__}")

    payload = json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def plan_digest(plan: SceneToolPlan) -> str:
    validate_scene_tool_plan(plan)
    # Call order is meaningful, even though argument/object key order is not.
    return canonical_sha256(plan.to_dict())


def bundle_digest(bundle: SpecBundle) -> str:
    # Registry execution has already resolved defaults and RobotProfile aliases.
    return canonical_sha256(bundle.to_dict())


def generation_result_is_current(*, ticket: int, current_ticket: int,
                                 requested_input_digest: str, current_input_digest: str) -> bool:
    """A late result cannot be promoted across an input-change boundary."""
    return ticket == current_ticket and requested_input_digest == current_input_digest


@dataclass(frozen=True, slots=True)
class InputRevision:
    prompt: str
    images: tuple[dict[str, str], ...]
    input_kind: str
    measurement_constraints: tuple[dict[str, Any], ...]
    profile_id: str
    generation_settings: dict[str, str]
    digest: str
    schema_version: str = INPUT_REVISION_VERSION

    @classmethod
    def create(
        cls, *, prompt: str, images: Sequence[tuple[str, bytes] | tuple[str, str, bytes]],
        measurement_constraints: Sequence[Any], profile_id: str,
        generation_settings: Mapping[str, str], input_kind: str | None = None,
    ) -> "InputRevision":
        if not isinstance(prompt, str) or len(prompt) > 10000:
            raise ValueError("input prompt is invalid")
        if len(images) > 1:
            raise ValueError("input revision permits at most one image")
        image_refs_list: list[dict[str, str]] = []
        for image in images:
            if len(image) == 2:
                name, content = image
                mime_type = None
            else:
                name, mime_type, content = image
            reference = {"name": name, "sha256": hashlib.sha256(content).hexdigest()}
            if mime_type is not None:
                if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
                    raise ValueError("input image MIME type is unsupported")
                reference["mime_type"] = mime_type
            image_refs_list.append(reference)
        image_refs = tuple(image_refs_list)
        if any(not ref["name"] or Path(ref["name"]).name != ref["name"] for ref in image_refs):
            raise ValueError("input image name must be a file name")
        constraints = tuple(dict(value.to_dict() if hasattr(value, "to_dict") else value)
                            for value in measurement_constraints)
        kind = input_kind or ("drawing" if constraints else ("photo" if images else "text"))
        if kind not in {"drawing", "photo", "text"}:
            raise ValueError("input_kind is unsupported")
        if kind == "text" and images:
            raise ValueError("text input cannot contain an image")
        if not profile_id.strip():
            raise ValueError("input profile_id is required")
        settings = dict(generation_settings)
        if not settings or any(key not in _NON_SECRET_SETTING_KEYS or not isinstance(value, str)
                               for key, value in settings.items()):
            raise ValueError("generation settings must be non-secret strings")
        if 'model_catalog_sha256' in settings:_hex_digest(settings['model_catalog_sha256'],'model catalog')
        for address in ('base_url','observer_base_url'):
            if address in settings:
                url = urlsplit(settings[address])
                if url.username or url.password or url.query or url.fragment:
                    raise ValueError("generation Base URL must not contain credentials or query data")
        identity = {
            "schema_version": INPUT_REVISION_VERSION,
            "prompt": prompt,
            "images": image_refs,
            "input_kind": kind,
            "measurement_constraints": constraints,
            "profile_id": profile_id,
            "generation_settings": settings,
        }
        return cls(prompt, image_refs, kind, constraints, profile_id, settings,
                   canonical_sha256(identity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "prompt": self.prompt,
            "images": list(self.images), "input_kind": self.input_kind,
            "measurement_constraints": list(self.measurement_constraints),
            "profile_id": self.profile_id, "generation_settings": self.generation_settings,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InputRevision":
        expected = {"schema_version", "prompt", "images", "input_kind",
                    "measurement_constraints", "profile_id", "generation_settings", "digest"}
        if set(value) != expected or value.get("schema_version") != INPUT_REVISION_VERSION:
            raise ValueError("input revision has an unsupported shape or version")
        images = value["images"]
        constraints = value["measurement_constraints"]
        settings = value["generation_settings"]
        if not isinstance(images, list) or len(images) > 1 or not isinstance(constraints, list):
            raise ValueError("input revision images or measurements are invalid")
        if not isinstance(settings, Mapping):
            raise ValueError("input revision settings are invalid")
        if any(key not in _NON_SECRET_SETTING_KEYS or not isinstance(item, str)
               for key, item in settings.items()):
            raise ValueError("input revision settings contain unsupported or secret data")
        if 'model_catalog_sha256' in settings:_hex_digest(settings['model_catalog_sha256'],'model catalog')
        for image in images:
            if not isinstance(image, Mapping) or set(image) not in (
                {"name", "sha256"}, {"name", "sha256", "mime_type"},
            ):
                raise ValueError("input revision image reference is invalid")
            if not isinstance(image["name"], str) or Path(image["name"]).name != image["name"]:
                raise ValueError("input revision image name is invalid")
            _hex_digest(image["sha256"], "image")
            if "mime_type" in image and image["mime_type"] not in {"image/png", "image/jpeg", "image/webp"}:
                raise ValueError("input revision image MIME type is invalid")
        if not all(isinstance(item, Mapping) for item in constraints):
            raise ValueError("input revision measurement is invalid")
        if not all(isinstance(value[field], str) for field in ("prompt", "input_kind", "profile_id")):
            raise ValueError("input revision string fields are invalid")
        record = cls(value["prompt"], tuple(dict(item) for item in images),
                     value["input_kind"], tuple(dict(item) for item in constraints),
                     value["profile_id"], dict(settings),
                     _hex_digest(value["digest"], "input revision"))
        if record.input_kind not in {"drawing", "photo", "text"} or len(record.prompt) > 10000 or not record.profile_id.strip():
            raise ValueError("input revision content is invalid")
        if record.input_kind == "text" and record.images:
            raise ValueError("input revision text kind cannot contain an image")
        if "base_url" in record.generation_settings:
            url = urlsplit(record.generation_settings["base_url"])
            if url.username or url.password or url.query or url.fragment:
                raise ValueError("input revision URL contains credentials or query data")
        identity = record.to_dict()
        identity.pop("digest")
        if canonical_sha256(identity) != record.digest:
            raise ValueError("input revision hash does not match")
        return record


def _hex_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} hash is invalid")
    return value


class InputArtifactStore:
    """Immutable local snapshot of input bytes before a provider request."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, revision: InputRevision, images: Sequence[tuple[str, bytes]]) -> Path:
        if tuple((name, hashlib.sha256(content).hexdigest()) for name, content in images) != tuple(
            (ref["name"], ref["sha256"]) for ref in revision.images
        ):
            raise ValueError("input artifact bytes do not match revision")
        folder = self.root / revision.digest
        if self.root.is_symlink() or folder.is_symlink():
            raise ValueError("input artifact link is forbidden")
        folder.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or folder.is_symlink():
            raise ValueError("input artifact link is forbidden")
        manifest = folder / "revision.json"
        if manifest.is_symlink():
            raise ValueError("input artifact link is forbidden")
        data = json.dumps(revision.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
        if manifest.exists():
            if InputRevision.from_dict(json.loads(manifest.read_text(encoding="utf-8"))) != revision:
                raise ValueError("immutable input artifact revision changed")
        for ref in revision.images:
            image = folder / f"{ref['sha256']}.bin"
            if image.is_symlink() or (image.exists() and hashlib.sha256(image.read_bytes()).hexdigest() != ref["sha256"]):
                raise ValueError("immutable input artifact image changed")
        for ref, (_, content) in zip(revision.images, images, strict=True):
            image = folder / f"{ref['sha256']}.bin"
            if image.exists():
                continue
            else:
                image.write_bytes(content)
        if not manifest.exists():
            manifest.write_text(data, encoding="utf-8")
        return folder

    def load(self, expected: InputRevision) -> tuple[InputRevision, tuple[tuple[str, str, bytes], ...]]:
        """Read only the immutable archive named by a validated saved revision.

        No caller-supplied path is accepted. A missing or altered archive cannot
        silently become a newly selected input or inherit review approval.
        """
        checked = InputRevision.from_dict(expected.to_dict())
        folder = self.root / checked.digest
        manifest = folder / "revision.json"
        if self.root.is_symlink() or folder.is_symlink() or manifest.is_symlink():
            raise ValueError("input artifact link is forbidden")
        if manifest.stat().st_size > 256 * 1024:
            raise ValueError("input artifact manifest is too large")
        stored = InputRevision.from_dict(json.loads(manifest.read_text(encoding="utf-8")))
        if stored != checked:
            raise ValueError("input artifact revision changed")
        images: list[tuple[str, str, bytes]] = []
        for ref in stored.images:
            image = folder / f"{ref['sha256']}.bin"
            if image.is_symlink() or image.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("input artifact image is linked or too large")
            content = image.read_bytes()
            if not content or len(content) > 10 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != ref["sha256"]:
                raise ValueError("input artifact image changed")
            mime = ref.get("mime_type")
            if mime is None:
                raise ValueError("input artifact image MIME is unavailable")
            images.append((ref["name"], mime, content))
        return stored, tuple(images)
