# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Strict, geometry-independent site presentation presets."""

from __future__ import annotations

from typing import Mapping

PRESENTATION_VIEWS = frozenset({"auto", "front", "back", "left", "right", "top"})
PRESENTATION_LIGHTS = frozenset({"balanced", "soft", "bright"})


def checked_presentation(value: object) -> dict[str, object]:
    if (not isinstance(value, Mapping) or set(value) != {"schema_version", "view", "lighting"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["view"]) is not str or value["view"] not in PRESENTATION_VIEWS
            or type(value["lighting"]) is not str or value["lighting"] not in PRESENTATION_LIGHTS):
        raise ValueError("site presentation preset is invalid")
    return {"schema_version": 1, "view": value["view"], "lighting": value["lighting"]}


DEFAULT_PRESENTATION = checked_presentation({"schema_version": 1, "view": "auto", "lighting": "balanced"})
