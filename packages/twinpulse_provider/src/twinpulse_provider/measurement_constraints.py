"""Independent numeric constraints applied to an untrusted scene-tool plan.

The constraints are intentionally supplied outside the LLM response.  They can
come from a drawing/CAD parser, OCR adapter, trusted sidecar metadata, or an
explicit user measurement.  A plan that disagrees is rejected before the local
scene-tool registry is executed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class MeasurementConstraintError(ValueError):
    """Raised when a plan conflicts with independently supplied measurements."""


@dataclass(frozen=True, slots=True)
class MeasurementConstraint:
    constraint_id: str
    tool: str
    argument_path: str
    expected: float | tuple[float, ...]
    tolerance: float
    occurrence: int | None = None
    source: str = "external_measurement"

    def __post_init__(self) -> None:
        if not _ID_RE.fullmatch(self.constraint_id):
            raise MeasurementConstraintError("constraint_id must be a stable ASCII identifier")
        if not _ID_RE.fullmatch(self.tool):
            raise MeasurementConstraintError("constraint tool must be a stable ASCII identifier")
        if not self.argument_path or len(self.argument_path) > 96:
            raise MeasurementConstraintError("argument_path must contain 1 to 96 characters")
        if not math.isfinite(self.tolerance) or self.tolerance < 0:
            raise MeasurementConstraintError("constraint tolerance must be finite and non-negative")
        if self.occurrence is not None and self.occurrence < 0:
            raise MeasurementConstraintError("constraint occurrence must be non-negative or null for all")
        if not self.source.strip() or len(self.source) > 200:
            raise MeasurementConstraintError("constraint source must contain 1 to 200 characters")
        values = self.expected if isinstance(self.expected, tuple) else (self.expected,)
        if not values or any(isinstance(value, bool) or not math.isfinite(float(value)) for value in values):
            raise MeasurementConstraintError("constraint expected value must contain finite numbers")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MeasurementConstraint":
        expected_keys = {
            "constraint_id",
            "tool",
            "argument_path",
            "expected",
            "tolerance",
            "occurrence",
            "source",
        }
        if set(value) - expected_keys:
            raise MeasurementConstraintError("measurement constraint contains unexpected fields")
        required = {"constraint_id", "tool", "argument_path", "expected", "tolerance"}
        if not required.issubset(value):
            raise MeasurementConstraintError("measurement constraint is missing required fields")
        raw_expected = value["expected"]
        if isinstance(raw_expected, list):
            expected: float | tuple[float, ...] = tuple(float(item) for item in raw_expected)
        else:
            expected = float(raw_expected)
        occurrence = value.get("occurrence")
        return cls(
            constraint_id=str(value["constraint_id"]),
            tool=str(value["tool"]),
            argument_path=str(value["argument_path"]),
            expected=expected,
            tolerance=float(value["tolerance"]),
            occurrence=None if occurrence is None else int(occurrence),
            source=str(value.get("source", "external_measurement")),
        )

    def to_dict(self) -> dict[str, Any]:
        expected: float | list[float]
        expected = list(self.expected) if isinstance(self.expected, tuple) else self.expected
        return {
            "constraint_id": self.constraint_id,
            "tool": self.tool,
            "argument_path": self.argument_path,
            "expected": expected,
            "tolerance": self.tolerance,
            "occurrence": self.occurrence,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class MeasurementValidationResult:
    constraint_count: int
    checked_value_count: int


def measurement_sidecar_path(image_path: Path) -> Path:
    """Return the documented sidecar path for an attached drawing image."""

    return image_path.with_suffix(".measurements.json")


def load_measurement_constraints(
    sidecar_path: Path,
    *,
    image_path: Path | None = None,
) -> tuple[MeasurementConstraint, ...]:
    """Load strict, trusted measurements stored next to a drawing image."""

    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MeasurementConstraintError(f"cannot read measurement sidecar: {error}") from error
    if not isinstance(payload, Mapping):
        raise MeasurementConstraintError("measurement sidecar root must be an object")
    allowed = {"schema_version", "source_image", "measurement_constraints"}
    if set(payload) - allowed:
        raise MeasurementConstraintError("measurement sidecar contains unexpected fields")
    if payload.get("schema_version") != "1.0":
        raise MeasurementConstraintError("measurement sidecar schema_version must be 1.0")
    source_image = payload.get("source_image")
    if source_image is not None:
        if not isinstance(source_image, str) or Path(source_image).name != source_image:
            raise MeasurementConstraintError("measurement sidecar source_image must be a file name")
        if image_path is not None and source_image != image_path.name:
            raise MeasurementConstraintError(
                f"measurement sidecar is for {source_image}, not {image_path.name}"
            )
    raw_constraints = payload.get("measurement_constraints")
    if not isinstance(raw_constraints, list) or not raw_constraints:
        raise MeasurementConstraintError("measurement sidecar must contain at least one constraint")
    if len(raw_constraints) > 64:
        raise MeasurementConstraintError("measurement sidecar exceeds the 64-constraint limit")
    constraints: list[MeasurementConstraint] = []
    for index, value in enumerate(raw_constraints):
        if not isinstance(value, Mapping):
            raise MeasurementConstraintError(f"measurement constraint {index} must be an object")
        try:
            constraints.append(MeasurementConstraint.from_dict(value))
        except (TypeError, ValueError) as error:
            raise MeasurementConstraintError(f"measurement constraint {index} is invalid: {error}") from error
    ids = [constraint.constraint_id for constraint in constraints]
    if len(ids) != len(set(ids)):
        raise MeasurementConstraintError("measurement sidecar constraint_id values must be unique")
    return tuple(constraints)


def validate_measurement_constraints(
    plan: Any,
    constraints: Sequence[MeasurementConstraint],
) -> MeasurementValidationResult:
    """Reject a plan when any external measurement differs beyond tolerance."""

    checked = 0
    for constraint in constraints:
        matches = [call for call in plan.calls if call.tool == constraint.tool]
        if not matches:
            raise MeasurementConstraintError(
                f"{constraint.constraint_id}: required tool {constraint.tool} is missing"
            )
        if constraint.occurrence is None:
            targets = matches
        elif constraint.occurrence >= len(matches):
            raise MeasurementConstraintError(
                f"{constraint.constraint_id}: occurrence {constraint.occurrence} is missing"
            )
        else:
            targets = [matches[constraint.occurrence]]
        for call in targets:
            actual = _resolve_argument(call.arguments, constraint.argument_path, constraint.constraint_id)
            if not _matches(actual, constraint.expected, constraint.tolerance):
                raise MeasurementConstraintError(
                    f"{constraint.constraint_id}: {call.call_id}.{constraint.argument_path} "
                    f"expected {_compact(constraint.expected)} +/- {constraint.tolerance:g}, "
                    f"got {_compact(actual)} (source={constraint.source})"
                )
            checked += len(actual) if isinstance(actual, tuple) else 1
    return MeasurementValidationResult(len(constraints), checked)


def _resolve_argument(arguments: Mapping[str, Any], path: str, constraint_id: str) -> float | tuple[float, ...]:
    current: Any = arguments
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                raise MeasurementConstraintError(f"{constraint_id}: argument path {path} is missing")
            current = current[part]
        elif isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise MeasurementConstraintError(f"{constraint_id}: argument path {path} is missing")
            current = current[index]
        else:
            raise MeasurementConstraintError(f"{constraint_id}: argument path {path} is not numeric")
    if isinstance(current, (list, tuple)):
        if not current or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in current):
            raise MeasurementConstraintError(f"{constraint_id}: argument path {path} is not numeric")
        return tuple(float(item) for item in current)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise MeasurementConstraintError(f"{constraint_id}: argument path {path} is not numeric")
    return float(current)


def _matches(actual: float | tuple[float, ...], expected: float | tuple[float, ...], tolerance: float) -> bool:
    actual_values = actual if isinstance(actual, tuple) else (actual,)
    expected_values = expected if isinstance(expected, tuple) else (expected,)
    return len(actual_values) == len(expected_values) and all(
        abs(left - right) <= tolerance for left, right in zip(actual_values, expected_values, strict=True)
    )


def _compact(value: Any) -> str:
    if isinstance(value, tuple):
        return "[" + ", ".join(f"{item:g}" for item in value) + "]"
    if isinstance(value, (int, float)):
        return f"{float(value):g}"
    return str(value)
