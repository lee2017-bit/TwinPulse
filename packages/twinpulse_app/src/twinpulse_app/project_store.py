# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Atomic, credential-free state for the active or explicitly named project."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Mapping

from twinpulse_core import GeneratedDraftRecord, GeneratedDraftStore, InputRevision
from .site_draft import SiteDraftRecord


PROJECT_RECORD_VERSION = "2.0"
PROJECT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def checked_project_id(project_id: str) -> str:
    """A project identifier is a name, never a filesystem path."""
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("project_id must be a lowercase portable name")
    return project_id


def named_project_state_path(root: Path, project_id: str) -> Path:
    project_id = checked_project_id(project_id)
    if project_id == "default":
        return root / "active_project.json"
    return root / "projects" / project_id / "project.json"


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: str
    latest_input: InputRevision | None = None
    draft: GeneratedDraftRecord | None = None
    site_draft: SiteDraftRecord | None = None
    updated_at_utc: str = ""
    schema_version: str = PROJECT_RECORD_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_RECORD_VERSION:
            raise ValueError("project state version is unsupported")
        if not isinstance(self.project_id, str) or not self.project_id.strip() or len(self.project_id) > 128:
            raise ValueError("project_id is invalid")
        if self.draft is not None:
            GeneratedDraftRecord.from_dict(self.draft.to_dict())
        if self.site_draft is not None:
            SiteDraftRecord.from_dict(self.site_draft.to_dict())
        if self.draft is not None and self.site_draft is not None:
            raise ValueError("a project cannot have active v1 and v2 drafts together")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "project_id": self.project_id,
            "latest_input": self.latest_input.to_dict() if self.latest_input is not None else None,
            "draft": self.draft.to_dict() if self.draft is not None else None,
            "site_draft": self.site_draft.to_dict() if self.site_draft is not None else None,
            "updated_at_utc": self.updated_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ProjectRecord":
        version = value.get("schema_version")
        fields = {"schema_version", "project_id", "latest_input", "draft", "updated_at_utc"}
        if version not in {"1.0", PROJECT_RECORD_VERSION} or set(value) != (fields if version == "1.0" else fields | {"site_draft"}):
            raise ValueError("project state shape is unsupported")
        latest = value["latest_input"]
        draft = value["draft"]
        site_draft = value.get("site_draft")
        if latest is not None and not isinstance(latest, Mapping):
            raise ValueError("project input revision is invalid")
        if draft is not None and not isinstance(draft, Mapping):
            raise ValueError("project draft is invalid")
        if site_draft is not None and not isinstance(site_draft, Mapping):
            raise ValueError("project site draft is invalid")
        if not isinstance(value["updated_at_utc"], str) or len(value["updated_at_utc"]) > 64:
            raise ValueError("project update timestamp is invalid")
        return cls(
            project_id=value["project_id"],  # type: ignore[arg-type]
            latest_input=InputRevision.from_dict(latest) if latest is not None else None,
            draft=GeneratedDraftRecord.from_dict(draft) if draft is not None else None,
            site_draft=SiteDraftRecord.from_dict(site_draft) if site_draft is not None else None,
            updated_at_utc=value["updated_at_utc"],
            schema_version=PROJECT_RECORD_VERSION,
        )


def default_project_state_path() -> Path:
    override = os.environ.get("TWINPULSE_STATE_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TwinPulse" / "runtime"
    return root / "active_project.json"


class AutomaticMapStore:
    """Immutable derived maps, isolated from the existing v1/v2 project record."""
    def __init__(self, root: Path, project_id: str):
        self.root=Path(root).resolve();self.project_id=checked_project_id(project_id)
        self.folder=self.root/'artifacts/automatic-mapping'/self.project_id

    def _path(self, map_id):
        if not isinstance(map_id,str) or re.fullmatch('[a-f0-9]{32}',map_id) is None:
            raise ValueError('EXACT_AUTOMATIC_MAP_ID_REQUIRED')
        path=self.folder/(map_id+'.json')
        if any(p.is_symlink() for p in (path,self.folder,self.folder.parent,self.folder.parent.parent)) or not path.resolve().is_relative_to(self.root):
            raise ValueError('AUTOMATIC_MAP_PATH_UNSAFE')
        return path

    def save(self, map_id, value):
        from twinpulse_core.automatic_mapping import checked_saved_map
        checked_saved_map(value,self.project_id)
        encoded=json.dumps(value,sort_keys=True,allow_nan=False)
        if len(encoded.encode())>4*1024*1024:raise ValueError('AUTOMATIC_MAP_FILE_BUDGET')
        path=self._path(map_id);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as stream:stream.write(encoded)
        return self.load(map_id)

    def load(self, map_id):
        from twinpulse_core.automatic_mapping import checked_saved_map
        path=self._path(map_id)
        if path.stat().st_size>4*1024*1024:raise ValueError('AUTOMATIC_MAP_FILE_BUDGET')
        return checked_saved_map(json.loads(path.read_text(encoding='utf-8')),self.project_id)

    def list_maps(self):
        self._path('0'*32)
        if not self.folder.exists():return []
        files=list(self.folder.glob('*.json'))
        if len(files)>256:raise ValueError('AUTOMATIC_MAP_CATALOG_BUDGET')
        result=[]
        for path in sorted(files):
            value=self.load(path.stem)
            result.append({'map_id':path.stem,'revision':value['revision'],'source_revision':value['source_revision'],
                           'reference_eligible':value['reference_eligible'],'keyframes':len(value['keyframes'])})
        return result

    def save_failure(self, job_id, value):
        base=self._path(job_id);folder=base.parent/'failures';path=folder/base.name
        if folder.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('AUTOMATIC_FAILURE_PATH_UNSAFE')
        folder.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,sort_keys=True,allow_nan=False)


class ProjectStore:
    def __init__(self, path: Path | None = None, *, expected_project_id: str | None = None,
                 expected_parent: Path | None = None) -> None:
        self.path = path or default_project_state_path()
        self.expected_project_id = checked_project_id(expected_project_id) if expected_project_id is not None else None
        self.expected_parent = expected_parent

    @classmethod
    def for_project(cls, root: Path, project_id: str) -> "ProjectStore":
        path = named_project_state_path(root, project_id)
        return cls(path, expected_project_id=project_id,
                   expected_parent=root.resolve() if project_id == "default"
                   else root.resolve() / "projects" / project_id)

    def _check_location(self) -> None:
        if self.expected_parent is not None and (
            self.path.parent.resolve() != self.expected_parent or self.path.is_symlink()
        ):
            raise ValueError("project state path leaves the selected project")

    def input_root(self) -> Path:
        self._check_location()
        path = self.path.parent / "inputs"
        if self.expected_parent is not None and (
            path.is_symlink() or path.resolve() != self.expected_parent / "inputs"
        ):
            raise ValueError("project input directory leaves the selected project")
        return path

    def _check_identity(self, record: ProjectRecord) -> ProjectRecord:
        if self.expected_project_id is not None and record.project_id != self.expected_project_id:
            raise ValueError("stored project identity does not match selected project")
        return record

    def load(self) -> ProjectRecord | None:
        self._check_location()
        if not self.path.is_file():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("project state must be a JSON object")
        checked = self._check_identity(ProjectRecord.from_dict(value))
        self._check_recipe(checked)
        return checked

    def _check_recipe(self, record: ProjectRecord) -> None:
        if self.expected_project_id not in {None, "default"}:
            from .room_recipe import verify_project_room_record
            verify_project_room_record(record, self.path.parent.parent.parent)

    def save(self, record: ProjectRecord) -> None:
        self._check_location()
        checked = self._check_identity(ProjectRecord.from_dict(record.to_dict()))
        self._check_recipe(checked)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._check_location()
        lock_path = (self.path.with_suffix(self.path.suffix + ".lock")
                     if self.expected_project_id not in {None, "default"} else None)
        if lock_path is not None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as error:
                raise ValueError("concurrent project write is blocked") from error
            os.close(descriptor)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            if lock_path is not None and (temporary.exists() or temporary.is_symlink()):
                raise ValueError("stale temporary project state blocks saving")
            temporary.write_text(
                json.dumps(checked.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        finally:
            if lock_path is not None:
                lock_path.unlink()

    def load_or_import_legacy(
        self, legacy: GeneratedDraftStore | None, *, project_id: str = "default",
    ) -> tuple[ProjectRecord, bool]:
        if self.expected_project_id is not None and project_id != self.expected_project_id:
            raise ValueError("selected project identity changed")
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
