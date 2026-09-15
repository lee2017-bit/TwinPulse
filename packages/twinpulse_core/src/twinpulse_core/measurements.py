"""Pure revalidation of independently supplied numeric plan constraints."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .scene_tools import SceneToolPlan


def validate_plan_measurements(plan: SceneToolPlan, constraints: Sequence[Mapping[str, Any]]) -> int:
    checked = 0
    for constraint in constraints:
        tool = constraint["tool"]
        path = constraint["argument_path"]
        occurrence = constraint.get("occurrence")
        matches = [call for call in plan.calls if call.tool == tool]
        if not matches:
            raise ValueError(f"measurement {constraint['constraint_id']}: required tool is missing")
        if occurrence is not None:
            if isinstance(occurrence, bool) or not isinstance(occurrence, int) or not 0 <= occurrence < len(matches):
                raise ValueError(f"measurement {constraint['constraint_id']}: occurrence is missing")
            matches = [matches[occurrence]]
        expected = constraint["expected"]
        values = expected if isinstance(expected, list) else [expected]
        tolerance = constraint["tolerance"]
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("measurement tolerance is invalid")
        if not values or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                             for value in values):
            raise ValueError("measurement expected value is invalid")
        for call in matches:
            actual: Any = call.arguments
            for part in str(path).split("."):
                if isinstance(actual, Mapping) and part in actual:
                    actual = actual[part]
                elif isinstance(actual, (list, tuple)) and part.isdigit() and int(part) < len(actual):
                    actual = actual[int(part)]
                else:
                    raise ValueError(f"measurement {constraint['constraint_id']}: argument path is missing")
            actual_values = actual if isinstance(actual, (list, tuple)) else [actual]
            if len(actual_values) != len(values) or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in actual_values
            ):
                raise ValueError(f"measurement {constraint['constraint_id']}: numeric shape differs")
            if any(abs(float(a) - float(e)) > tolerance for a, e in zip(actual_values, values, strict=True)):
                raise ValueError(f"measurement {constraint['constraint_id']}: plan value differs")
            checked += len(actual_values)
    return checked
