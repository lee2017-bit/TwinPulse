"""Reload-safe, credential-free persistence for the last validated tool plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .models import SpecBundle
from .scene_tools import SceneToolPlan, SceneToolRegistry, scene_tool_plan_to_json


_RECORD_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class GeneratedDraftRecord:
    request_id: str
    provider_name: str
    model_id: str
    image_count: int
    created_at_utc: str
    plan_sha256: str
    plan: SceneToolPlan

    @property
    def bundle(self) -> SpecBundle:
        return SceneToolRegistry().execute(self.plan)

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        provider_name: str,
        model_id: str,
        image_count: int,
        plan: SceneToolPlan,
    ) -> "GeneratedDraftRecord":
        return cls(
            request_id=request_id,
            provider_name=provider_name,
            model_id=model_id,
            image_count=image_count,
            created_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            plan_sha256=_plan_hash(plan),
            plan=plan,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_version": _RECORD_VERSION,
            "request_id": self.request_id,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "image_count": self.image_count,
            "created_at_utc": self.created_at_utc,
            "plan_sha256": self.plan_sha256,
            "plan": self.plan.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GeneratedDraftRecord":
        expected = {
            "record_version",
            "request_id",
            "provider_name",
            "model_id",
            "image_count",
            "created_at_utc",
            "plan_sha256",
            "plan",
        }
        if set(value) != expected or value.get("record_version") != _RECORD_VERSION:
            raise ValueError("generated draft record has an unsupported shape or version")
        raw_plan = value["plan"]
        if not isinstance(raw_plan, Mapping):
            raise ValueError("generated draft plan must be an object")
        plan = SceneToolPlan.from_dict(raw_plan)
        image_count = value["image_count"]
        if isinstance(image_count, bool) or not isinstance(image_count, int) or image_count not in (0, 1):
            raise ValueError("generated draft image_count must be 0 or 1")
        record = cls(
            request_id=_metadata(value["request_id"], "request_id"),
            provider_name=_metadata(value["provider_name"], "provider_name"),
            model_id=_metadata(value["model_id"], "model_id"),
            image_count=image_count,
            created_at_utc=_metadata(value["created_at_utc"], "created_at_utc"),
            plan_sha256=_metadata(value["plan_sha256"], "plan_sha256"),
            plan=plan,
        )
        if record.plan_sha256 != _plan_hash(plan):
            raise ValueError("generated draft plan hash does not match")
        # Re-execute the allowlisted plan during load so stale or invalid plans
        # never become eligible for an Isaac stage mutation.
        record.bundle
        return record


class GeneratedDraftStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_generated_draft_path()

    def load(self) -> GeneratedDraftRecord | None:
        if not self.path.is_file():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("generated draft state must be a JSON object")
        return GeneratedDraftRecord.from_dict(value)

    def save(self, record: GeneratedDraftRecord) -> None:
        # Validate immediately before the atomic replace.
        GeneratedDraftRecord.from_dict(record.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def default_generated_draft_path() -> Path:
    override = os.environ.get("TWINPULSE_STATE_DIR")
    if override:
        root = Path(override)
    else:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TwinPulse" / "runtime"
    return root / "last_generated_draft.json"


def _plan_hash(plan: SceneToolPlan) -> str:
    canonical = scene_tool_plan_to_json(plan, indent=None)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metadata(value: object, name: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 256:
        raise ValueError(f"generated draft {name} is invalid")
    return text
