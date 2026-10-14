# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Project-local display preferences; never part of the source scene revision."""

from __future__ import annotations

import json
import os
from pathlib import Path

from twinpulse_core.presentation import checked_presentation
from .project_store import ProjectStore


class PresentationStore:
    def __init__(self, project_store: ProjectStore):
        self._project_store = project_store
        self.path = project_store.path.with_suffix(".presentation.json")

    def _check_path(self) -> None:
        self._project_store._check_location()
        if self.path.is_symlink() or self.path.parent.resolve() != self._project_store.path.parent.resolve():
            raise ValueError("presentation path leaves the project")

    def load(self, source_scene_revision: str) -> dict[str, object] | None:
        self._check_path()
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 4096:
            raise ValueError("presentation file exceeds limit")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"source_scene_revision", "presentation"}:
            raise ValueError("presentation file shape is invalid")
        if value["source_scene_revision"] != source_scene_revision:
            return None
        return checked_presentation(value["presentation"])

    def save(self, source_scene_revision: str, presentation: object) -> dict[str, object]:
        if (type(source_scene_revision) is not str or len(source_scene_revision) != 64
                or any(character not in "0123456789abcdef" for character in source_scene_revision)):
            raise ValueError("source scene revision is invalid")
        checked = checked_presentation(presentation)
        self._check_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            self._check_path()
            if temporary.exists() or temporary.is_symlink():
                raise ValueError("stale presentation temporary file blocks saving")
            temporary.write_text(json.dumps({"source_scene_revision": source_scene_revision,
                                             "presentation": checked}, sort_keys=True), encoding="utf-8")
            temporary.replace(self.path)
        finally:
            lock.unlink(missing_ok=True)
        return checked
