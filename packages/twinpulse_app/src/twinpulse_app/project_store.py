"""Atomic, credential-free state for the single active R3 project."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Mapping

from twinpulse_core import GeneratedDraftRecord, GeneratedDraftStore, InputRevision


PROJECT_RECORD_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: str
    latest_input: InputRevision | None = None
    draft: GeneratedDraftRecord | None = None
    updated_at_utc: str = ""
    schema_version: str = PROJECT_RECORD_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_RECORD_VERSION:
            raise ValueError("project state version is unsupported")
        if not isinstance(self.project_id, str) or not self.project_id.strip() or len(self.project_id) > 128:
            raise ValueError("project_id is invalid")
        if self.draft is not None:
            GeneratedDraftRecord.from_dict(self.draft.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "project_id": self.project_id,
            "latest_input": self.latest_input.to_dict() if self.latest_input is not None else None,
            "draft": self.draft.to_dict() if self.draft is not None else None,
            "updated_at_utc": self.updated_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ProjectRecord":
        if set(value) != {"schema_version", "project_id", "latest_input", "draft", "updated_at_utc"}:
            raise ValueError("project state shape is unsupported")
        latest = value["latest_input"]
        draft = value["draft"]
        if latest is not None and not isinstance(latest, Mapping):
            raise ValueError("project input revision is invalid")
        if draft is not None and not isinstance(draft, Mapping):
            raise ValueError("project draft is invalid")
        if not isinstance(value["updated_at_utc"], str) or len(value["updated_at_utc"]) > 64:
            raise ValueError("project update timestamp is invalid")
        return cls(
            project_id=value["project_id"],  # type: ignore[arg-type]
            latest_input=InputRevision.from_dict(latest) if latest is not None else None,
            draft=GeneratedDraftRecord.from_dict(draft) if draft is not None else None,
            updated_at_utc=value["updated_at_utc"],
            schema_version=value["schema_version"],  # type: ignore[arg-type]
        )


def default_project_state_path() -> Path:
    override = os.environ.get("TWINPULSE_STATE_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TwinPulse" / "runtime"
    return root / "active_project.json"


class ProjectStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_project_state_path()

    def load(self) -> ProjectRecord | None:
        if not self.path.is_file():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("project state must be a JSON object")
        return ProjectRecord.from_dict(value)

    def save(self, record: ProjectRecord) -> None:
        checked = ProjectRecord.from_dict(record.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(checked.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def load_or_import_legacy(
        self, legacy: GeneratedDraftStore | None, *, project_id: str = "default",
    ) -> tuple[ProjectRecord, bool]:
        current = self.load()
        if current is not None:
            return current, False
        draft = legacy.load() if legacy is not None else None
        record = ProjectRecord(
            project_id=project_id,
            latest_input=draft.input_revision if draft is not None else None,
            draft=draft,
        )
        self.save(record)
        return record, draft is not None
