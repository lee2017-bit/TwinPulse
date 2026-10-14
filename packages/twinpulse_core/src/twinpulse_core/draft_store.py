# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reload-safe, credential-free persistence for the last validated tool plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .models import SpecBundle
from .measurements import validate_plan_measurements
from .revisions import InputRevision, VALIDATOR_VERSION, bundle_digest, canonical_sha256, plan_digest
from .scene_tools import SceneToolPlan, SceneToolRegistry, scene_tool_plan_to_json


_LEGACY_RECORD_VERSION = "1.0"
_PREVIOUS_RECORD_VERSION = "2.0"
_RECORD_VERSION = "3.0"


@dataclass(frozen=True, slots=True)
class ValidationReceipt:
    input_sha256: str
    plan_sha256: str
    bundle_sha256: str
    measurement_sha256: str
    validator_version: str
    dimensional_status: str
    checked_value_count: int
    validation_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_sha256": self.input_sha256, "plan_sha256": self.plan_sha256,
            "bundle_sha256": self.bundle_sha256, "measurement_sha256": self.measurement_sha256,
            "validator_version": self.validator_version, "dimensional_status": self.dimensional_status,
            "checked_value_count": self.checked_value_count,
            "validation_errors": list(self.validation_errors),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ValidationReceipt":
        expected = {"input_sha256", "plan_sha256", "bundle_sha256", "measurement_sha256",
                    "validator_version", "dimensional_status", "checked_value_count", "validation_errors"}
        if set(value) != expected:
            raise ValueError("validation receipt shape is unsupported")
        errors = value["validation_errors"]
        if not isinstance(errors, list) or not all(isinstance(error, str) for error in errors):
            raise ValueError("validation receipt errors are invalid")
        receipt = cls(**{**value, "validation_errors": tuple(errors)})
        if receipt.validator_version != VALIDATOR_VERSION:
            raise ValueError("validation receipt validator version is unsupported")
        if receipt.dimensional_status not in {"verified", "unverified"}:
            raise ValueError("validation receipt dimensional status is invalid")
        if isinstance(receipt.checked_value_count, bool) or not isinstance(receipt.checked_value_count, int) or receipt.checked_value_count < 0:
            raise ValueError("validation receipt checked count is invalid")
        if receipt.validation_errors:
            raise ValueError("a buildable draft cannot contain validation errors")
        return receipt


@dataclass(frozen=True, slots=True)
class GeneratedDraftRecord:
    request_id: str
    provider_name: str
    model_id: str
    image_count: int
    created_at_utc: str
    plan_sha256: str
    plan: SceneToolPlan
    input_revision: InputRevision | None = None
    validation_receipt: ValidationReceipt | None = None
    origin_status: str = "generated"
    provider_provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_provenance", _provider_provenance(self.provider_provenance))

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
        input_revision: InputRevision | None = None,
        origin_status: str = "generated",
        provider_provenance: Mapping[str, Any] | None = None,
    ) -> "GeneratedDraftRecord":
        if origin_status not in {"generated", "legacy_rebound"}:
            raise ValueError("draft origin status is unsupported")
        receipt = None
        if input_revision is not None:
            if image_count != len(input_revision.images):
                raise ValueError("generated draft image_count differs from input revision")
            bundle = SceneToolRegistry().execute(plan)
            checked = validate_plan_measurements(plan, input_revision.measurement_constraints)
            receipt = ValidationReceipt(
                input_sha256=input_revision.digest,
                plan_sha256=plan_digest(plan),
                bundle_sha256=bundle_digest(bundle),
                measurement_sha256=canonical_sha256(input_revision.measurement_constraints),
                validator_version=VALIDATOR_VERSION,
                dimensional_status="verified" if input_revision.measurement_constraints else "unverified",
                checked_value_count=checked,
            )
        return cls(
            request_id=request_id,
            provider_name=provider_name,
            model_id=model_id,
            image_count=image_count,
            created_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            plan_sha256=_plan_hash(plan),
            plan=plan,
            input_revision=input_revision,
            validation_receipt=receipt,
            origin_status=origin_status,
            provider_provenance=_provider_provenance(provider_provenance or {}),
        )

    @property
    def legacy_unverified(self) -> bool:
        return self.input_revision is None or self.validation_receipt is None

    def build_allowed_for(self, revision: InputRevision) -> bool:
        if self.legacy_unverified or self.input_revision.digest != revision.digest:
            return False
        try:
            # Build is a new trust boundary, even when the record stayed in memory.
            GeneratedDraftRecord.from_dict(self.to_dict())
        except (TypeError, ValueError, KeyError):
            return False
        return True

    def adopt_legacy_for(self, revision: InputRevision) -> "GeneratedDraftRecord":
        """Explicit old-version rebinding, not proof of its original input bytes."""
        if not self.legacy_unverified:
            raise ValueError("only legacy-unverified drafts require adoption")
        if self.image_count != len(revision.images):
            raise ValueError("legacy draft image count differs from selected current input")
        return GeneratedDraftRecord.create(
            request_id=self.request_id, provider_name=self.provider_name, model_id=self.model_id,
            image_count=len(revision.images), plan=self.plan, input_revision=revision,
            origin_status="legacy_rebound",
            provider_provenance=self.provider_provenance,
        )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "record_version": _LEGACY_RECORD_VERSION if self.legacy_unverified else _RECORD_VERSION,
            "request_id": self.request_id,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "image_count": self.image_count,
            "created_at_utc": self.created_at_utc,
            "plan_sha256": self.plan_sha256,
            "plan": self.plan.to_dict(),
        }
        if not self.legacy_unverified:
            value["input_revision"] = self.input_revision.to_dict()
            value["validation_receipt"] = self.validation_receipt.to_dict()
            value["origin_status"] = self.origin_status
            value["provider_provenance"] = dict(self.provider_provenance)
        return value

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
        version = value.get("record_version")
        if version == _RECORD_VERSION:
            expected.update({"input_revision", "validation_receipt", "origin_status", "provider_provenance"})
        elif version == _PREVIOUS_RECORD_VERSION:
            expected.update({"input_revision", "validation_receipt", "origin_status"})
        elif version != _LEGACY_RECORD_VERSION:
            raise ValueError("generated draft record version is unsupported")
        if set(value) != expected:
            raise ValueError("generated draft record has an unsupported shape or version")
        raw_plan = value["plan"]
        if not isinstance(raw_plan, Mapping):
            raise ValueError("generated draft plan must be an object")
        plan = SceneToolPlan.from_dict(raw_plan)
        image_count = value["image_count"]
        if isinstance(image_count, bool) or not isinstance(image_count, int) or image_count not in (0, 1):
            raise ValueError("generated draft image_count must be 0 or 1")
        input_revision = None
        validation_receipt = None
        if version in {_RECORD_VERSION, _PREVIOUS_RECORD_VERSION}:
            if not isinstance(value["input_revision"], Mapping) or not isinstance(value["validation_receipt"], Mapping):
                raise ValueError("generated draft provenance must be objects")
            input_revision = InputRevision.from_dict(value["input_revision"])
            validation_receipt = ValidationReceipt.from_dict(value["validation_receipt"])
            if value["origin_status"] not in {"generated", "legacy_rebound"}:
                raise ValueError("generated draft origin status is unsupported")
        record = cls(
            request_id=_metadata(value["request_id"], "request_id"),
            provider_name=_metadata(value["provider_name"], "provider_name"),
            model_id=_metadata(value["model_id"], "model_id"),
            image_count=image_count,
            created_at_utc=_metadata(value["created_at_utc"], "created_at_utc"),
            plan_sha256=_metadata(value["plan_sha256"], "plan_sha256"),
            plan=plan,
            input_revision=input_revision,
            validation_receipt=validation_receipt,
            origin_status=(
                value["origin_status"]
                if version in {_RECORD_VERSION, _PREVIOUS_RECORD_VERSION} else "generated"
            ),
            provider_provenance=(
                _provider_provenance(value["provider_provenance"])
                if version == _RECORD_VERSION else {}
            ),
        )
        if record.plan_sha256 != _plan_hash(plan):
            raise ValueError("generated draft plan hash does not match")
        # Re-execute the allowlisted plan during load so stale or invalid plans
        # never become eligible for an Isaac stage mutation.
        bundle = record.bundle
        if version in {_RECORD_VERSION, _PREVIOUS_RECORD_VERSION}:
            if record.image_count != len(input_revision.images):
                raise ValueError("generated draft image_count differs from input")
            checked = validate_plan_measurements(plan, input_revision.measurement_constraints)
            expected_receipt = ValidationReceipt(
                input_revision.digest, plan_digest(plan), bundle_digest(bundle),
                canonical_sha256(input_revision.measurement_constraints), VALIDATOR_VERSION,
                "verified" if input_revision.measurement_constraints else "unverified", checked,
            )
            if validation_receipt != expected_receipt:
                raise ValueError("generated draft validation receipt hash or status does not match")
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


def _provider_provenance(value: object) -> dict[str, Any]:
    """Accept bounded JSON metadata while rejecting secret or image-bearing fields."""
    forbidden = {"authorization", "api_key", "secret", "image_url", "data_uri", "image_base64"}

    def check(item: object, depth: int = 0) -> Any:
        if depth > 6:
            raise ValueError("provider provenance exceeds nesting limit")
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str) or not key or len(key) > 64 or key.lower() in forbidden:
                    raise ValueError("provider provenance key is invalid or secret-bearing")
                result[key] = check(child, depth + 1)
            return result
        if isinstance(item, (list, tuple)):
            if len(item) > 32:
                raise ValueError("provider provenance list exceeds limit")
            return [check(child, depth + 1) for child in item]
        if isinstance(item, str):
            if len(item) > 1024 or "base64," in item.lower() or "bearer " in item.lower():
                raise ValueError("provider provenance string is invalid or secret-bearing")
            return item
        if isinstance(item, bool) or item is None:
            return item
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            return item
        raise ValueError("provider provenance contains an unsupported value")

    checked = check(value)
    if not isinstance(checked, dict):
        raise ValueError("provider provenance must be an object")
    if len(json.dumps(checked, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 32 * 1024:
        raise ValueError("provider provenance exceeds size limit")
    return checked
