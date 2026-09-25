"""Strict import of stored provider results for zero-network managed replay."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePath
from typing import Mapping

from twinpulse_core import (
    COMPACT_2WD_PROFILE_ID,
    GeneratedDraftRecord,
    InputRevision,
    SCENE_TOOL_CATALOG_REVISION,
    SceneToolPlan,
    SceneToolRegistry,
    SpecBundle,
    bundle_digest,
    canonical_sha256,
    plan_digest,
)
from twinpulse_provider import ProviderConfigurationError


MAX_REPLAY_REPORT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ReplayFixture:
    source: str
    report_sha256: str
    fixture_id: str
    image_name: str
    image_sha256: str
    input_revision: InputRevision
    record: GeneratedDraftRecord
    plan_sha256: str
    bundle_sha256: str
    tool_count: int
    object_count: int


class ReplayOnlyGateway:
    """A generation gateway that proves a replay cannot contact a provider."""

    def __init__(self) -> None:
        self.generate_calls = 0
        self.cancel_calls = 0

    def cancel_active(self) -> None:
        self.cancel_calls += 1

    async def generate(self, _request: object) -> object:
        self.generate_calls += 1
        raise ProviderConfigurationError("Stored replay mode cannot perform provider generation")


def load_replay_fixture(path: Path, fixture_id: str) -> ReplayFixture:
    """Revalidate one stored result without executing paths, code, or network I/O."""

    report_path = path.resolve()
    if not fixture_id or len(fixture_id) > 128:
        raise ValueError("replay fixture id is invalid")
    size = report_path.stat().st_size
    if size <= 0 or size > MAX_REPLAY_REPORT_BYTES:
        raise ValueError("replay report size is invalid")
    raw = report_path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, Mapping) or value.get("status") != "PASS":
        raise ValueError("replay report must be a successful object")
    provider = _text(value.get("provider"), "provider")
    model_id = _text(value.get("model_id"), "model_id")
    reasoning = value.get("reasoning_effort", "low")
    if reasoning not in {"low", "medium", "high"}:
        raise ValueError("replay reasoning effort is invalid")
    fixtures = value.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("replay fixtures must be an array")
    matches = [item for item in fixtures if isinstance(item, Mapping) and item.get("fixture_id") == fixture_id]
    if len(matches) != 1:
        raise ValueError("replay fixture must exist exactly once")
    fixture = matches[0]
    if fixture.get("status") != "PASS":
        raise ValueError("replay fixture was not successful")

    image_name = _safe_file_name(fixture.get("image_filename"))
    image_sha256 = _digest(fixture.get("image_sha256"), "image")
    request_id = _text(fixture.get("request_id"), "request_id")
    prompt = fixture.get("prompt")
    if not isinstance(prompt, str) or len(prompt) > 10_000:
        raise ValueError("replay prompt is invalid")
    raw_plan = fixture.get("plan")
    raw_bundle = fixture.get("bundle")
    if not isinstance(raw_plan, Mapping) or not isinstance(raw_bundle, Mapping):
        raise ValueError("replay plan and bundle must be objects")
    plan = SceneToolPlan.from_dict(raw_plan)
    rebuilt_bundle = SceneToolRegistry().execute(plan)
    stored_bundle = SpecBundle.from_dict(raw_bundle)
    rebuilt_digest = bundle_digest(rebuilt_bundle)
    if bundle_digest(stored_bundle) != rebuilt_digest:
        raise ValueError("stored replay bundle does not match re-executed allowlisted plan")
    tool_count = _count(fixture.get("tool_call_count"), "tool")
    object_count = _count(fixture.get("expanded_object_count"), "object")
    if tool_count != len(plan.calls):
        raise ValueError("stored replay tool count does not match the plan")
    if object_count != len(rebuilt_bundle.scene.objects):
        raise ValueError("stored replay object count does not match the bundle")

    suffix = PurePath(image_name).suffix.lower()
    mime_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if mime_type is None:
        raise ValueError("replay image filename has an unsupported suffix")
    settings = {
        "model_id": model_id,
        "reasoning_effort": str(reasoning),
        "image_detail": "auto",
        "request_schema": "1.0",
        "tool_catalog_revision": SCENE_TOOL_CATALOG_REVISION,
    }
    revision_value = {
        "schema_version": "1.0",
        "prompt": prompt,
        "images": [{"name": image_name, "sha256": image_sha256, "mime_type": mime_type}],
        "input_kind": "photo",
        "measurement_constraints": [],
        "profile_id": COMPACT_2WD_PROFILE_ID,
        "generation_settings": settings,
    }
    revision_value["digest"] = canonical_sha256(revision_value)
    input_revision = InputRevision.from_dict(revision_value)
    record = GeneratedDraftRecord.create(
        request_id=request_id,
        provider_name=provider,
        model_id=model_id,
        image_count=1,
        plan=plan,
        input_revision=input_revision,
    )
    # A second load validates every receipt and re-executes the tool plan.
    record = GeneratedDraftRecord.from_dict(record.to_dict())
    return ReplayFixture(
        source="replay",
        report_sha256=hashlib.sha256(raw).hexdigest(),
        fixture_id=fixture_id,
        image_name=image_name,
        image_sha256=image_sha256,
        input_revision=input_revision,
        record=record,
        plan_sha256=plan_digest(plan),
        bundle_sha256=rebuilt_digest,
        tool_count=tool_count,
        object_count=object_count,
    )


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"replay {name} is invalid")
    return value


def _safe_file_name(value: object) -> str:
    name = _text(value, "image filename")
    if PurePath(name).name != name or "/" in name or "\\" in name:
        raise ValueError("replay image filename is unsafe")
    return name


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"replay {name} hash is invalid")
    return value


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"replay {name} count is invalid")
    return value
