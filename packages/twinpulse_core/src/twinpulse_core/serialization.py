"""JSON round-trip helpers for TwinPulse specifications."""

from __future__ import annotations

import json

from .models import SpecBundle
from .validation import ValidationLimits, validate_bundle


def bundle_to_json(bundle: SpecBundle, *, indent: int = 2) -> str:
    validate_bundle(bundle)
    return json.dumps(bundle.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)


def bundle_from_json(payload: str, *, limits: ValidationLimits | None = None) -> SpecBundle:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("bundle JSON must be an object")
    return validate_bundle(SpecBundle.from_dict(value), limits)

