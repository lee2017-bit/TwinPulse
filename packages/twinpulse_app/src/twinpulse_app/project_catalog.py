# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local project inventory and explicit empty creation; never grants runtime authority."""

from __future__ import annotations

from hashlib import sha256
from heapq import nlargest
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from twinpulse_core import canonical_sha256

from .image_validation import decode_image
from .manual_room import manual_room_plan
from .project_store import PROJECT_ID_PATTERN, ProjectRecord, ProjectStore, checked_project_id, named_project_state_path


class ProjectCatalog:
    def __init__(self, state_root: Path, active_project_id: str) -> None:
        self.root = state_root.resolve()
        self.active_project_id = checked_project_id(active_project_id)
        self._conversation_summaries: dict[str, tuple[tuple[int, int, int], dict]] = {}
        self._listing_records = {}

    def create_empty(self, project_id: str) -> dict[str, object]:
        project_id = checked_project_id(project_id)
        if project_id == "default":
            raise ValueError("default project already exists")
        folder = self.root / "projects"
        if folder.is_symlink() or (folder.exists() and (not folder.is_dir() or folder.resolve() != self.root / "projects")):
            raise ValueError("project directory is invalid")
        folder.mkdir(parents=True, exist_ok=True)
        if folder.is_symlink() or folder.resolve() != self.root / "projects":
            raise ValueError("project directory is invalid")
        project_dir = folder / project_id
        project_dir.mkdir(exist_ok=False)
        ProjectStore.for_project(self.root, project_id).save(ProjectRecord(project_id=project_id))
        return {"created_project_id": project_id, "catalog": self.snapshot()}

    def create_from_manual_room(self, project_id: str, *, prompt: str, photo: bytes,
                                media_type: str, width_m: object, length_m: object,
                                wall_height_m: object, include_burger_visual: bool,
                                request_id: str, furniture: object = ()) -> dict[str, object]:
        """Publish a complete, photo-bound room under a new project ID only.

        Dimensions come from the user, never from an image inference. A failed
        staging attempt is not listed as a project and cannot overwrite one.
        """
        from .room_recipe import (ROOM_RECIPE_VERSION, import_project_room_recipe,
                                  load_project_room_visual, prepare_project_burger_visual)

        project_id = checked_project_id(project_id)
        if project_id == "default" or not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 500:
            raise ValueError("manual room project or prompt is invalid")
        try:
            if str(UUID(request_id)) != request_id:
                raise ValueError("invalid request ID")
        except (TypeError, ValueError) as error:
            raise ValueError("request_id must be a canonical UUID") from error
        if (not isinstance(photo, bytes) or not photo or len(photo) > 10 * 1024 * 1024
                or type(include_burger_visual) is not bool):
            raise ValueError("manual room image or visual choice is invalid")
        decoded = decode_image(photo, max_pixels=40_000_000)
        if decoded.media_type != media_type:
            raise ValueError("manual room image MIME does not match bytes")
        plan = manual_room_plan(project_id, width_m, length_m, wall_height_m, furniture)
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[media_type]
        photo_hash = sha256(photo).hexdigest()
        source_digest = canonical_sha256({"photo_sha256": photo_hash, "prompt": prompt,
                                          "plan": plan.to_dict(), "burger": include_burger_visual})
        transactions = self._checked_child(self.root, "project-transactions")
        locks = self._checked_child(transactions, "locks")
        workspaces = self._checked_child(transactions, "workspaces")
        projects = self._checked_child(self.root, "projects")
        destination = projects / project_id
        lock_path = locks / f"{project_id}.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            if destination.exists() or destination.is_symlink():
                receipt = destination / "creation_receipt.json"
                if receipt.is_file() and not receipt.is_symlink():
                    expected = {"schema_version": "manual-room-creation-1.0", "project_id": project_id,
                                "request_id": request_id, "source_digest": source_digest}
                    if json.loads(receipt.read_text(encoding="utf-8")) == expected:
                        record = ProjectStore.for_project(self.root, project_id).load()
                        if record is None or record.site_draft is None:
                            raise ValueError("published manual room is invalid")
                        load_project_room_visual(self.root, project_id, record.site_draft)
                        return self._manual_room_created(project_id, include_burger_visual)
                raise FileExistsError("project name already exists")
            stage = workspaces / str(uuid4())
            staged_root = stage / "staged-state"
            staged_root.mkdir(parents=True, exist_ok=False)
            ProjectCatalog(staged_root, "default").create_empty(project_id)
            project_dir = staged_root / "projects" / project_id
            assets = project_dir / "assets"
            assets.mkdir(exist_ok=False)
            with (assets / f"room.{extension}").open("xb") as stream:
                stream.write(photo)
            recipe = {"schema_version": ROOM_RECIPE_VERSION, "project_id": project_id,
                      "prompt": prompt, "photo": {"relative_path": f"assets/room.{extension}",
                                                  "sha256": photo_hash}, "plan": plan.to_dict()}
            with (project_dir / "room_recipe.json").open("x", encoding="utf-8") as stream:
                json.dump(recipe, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
            if include_burger_visual:
                prepare_project_burger_visual(staged_root, project_id,
                                              (0.0, -min(float(length_m) / 4.0, 0.65), 0.002), 0.0)
            import_project_room_recipe(staged_root, project_id)
            checked = ProjectStore.for_project(staged_root, project_id).load()
            if checked is None or checked.site_draft is None:
                raise ValueError("staged manual room has no validated draft")
            load_project_room_visual(staged_root, project_id, checked.site_draft)
            (project_dir / "creation_receipt.json").write_text(json.dumps({
                "schema_version": "manual-room-creation-1.0", "project_id": project_id,
                "request_id": request_id, "source_digest": source_digest,
            }, sort_keys=True), encoding="utf-8")
            if destination.exists() or destination.is_symlink():
                raise FileExistsError("project name already exists")
            os.rename(project_dir, destination)
            published = ProjectStore.for_project(self.root, project_id).load()
            if published is None or published.site_draft != checked.site_draft:
                raise ValueError("published manual room failed validation")
            return self._manual_room_created(project_id, include_burger_visual)
        finally:
            lock_path.unlink()

    def _manual_room_created(self, project_id: str, burger: bool) -> dict[str, object]:
        return {"created_project_id": project_id, "catalog": self.snapshot(),
                "source": "user_photo_manual_dimensions", "burger_visual_included": burger,
                "photo_interpreted": False, "build_allowed": False, "physical_authority": False}

    def create_from_preserved_bedroom(self, project_id: str, request_id: str | None = None,
                                      recovery_fingerprint: str | None = None) -> dict[str, object]:
        """Explicitly copy the reviewed photo-room into a new named project.

        The photo-derived geometry and Burger placement remain illustrative;
        this creates a saved draft for review, never a Build or motion grant.
        """
        from .bedroom_review import ROOT, load_bedroom_source
        from .room_recipe import (ROOM_RECIPE_VERSION, import_project_room_recipe,
                                  load_project_room_visual, prepare_project_burger_visual)

        project_id = checked_project_id(project_id)
        if project_id == "default":
            raise ValueError("default project already exists")
        operation = str(uuid4()) if request_id is None else request_id
        try:
            if str(UUID(operation)) != operation:
                raise ValueError("invalid operation ID")
        except (TypeError, ValueError) as error:
            raise ValueError("request_id must be a canonical UUID") from error
        draft, _, _ = load_bedroom_source(ROOT)
        photo = (ROOT / "artifacts" / "photo-scan-review-20260927" / "room.jpg").read_bytes()
        source_digest = canonical_sha256({"photo_sha256": sha256(photo).hexdigest(),
                                          "prompt": draft.input_revision.prompt, "plan": draft.plan.to_dict()})
        transactions = self._checked_child(self.root, "project-transactions")
        locks = self._checked_child(transactions, "locks")
        requests = self._checked_child(transactions, "requests")
        workspaces = self._checked_child(transactions, "workspaces")
        projects = self._checked_child(self.root, "projects")
        destination = projects / project_id
        request_lock_path = locks / f"request-{operation}.lock"
        lock_path = locks / f"{project_id}.lock"
        descriptor = os.open(request_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except Exception:
            request_lock_path.unlink()
            raise
        os.close(descriptor)
        journal = requests / f"{operation}.json"
        try:
            if journal.exists():
                existing = json.loads(journal.read_text(encoding="utf-8"))
                if (existing.get("project_id"), existing.get("source_digest"),
                        existing.get("recovery_fingerprint")) != (project_id, source_digest, recovery_fingerprint):
                    raise ValueError("request_id already belongs to another creation")
            recover_existing = False
            if destination.exists() or destination.is_symlink():
                receipt = destination / "creation_receipt.json"
                if receipt.is_file() and not receipt.is_symlink():
                    value = json.loads(receipt.read_text(encoding="utf-8"))
                    if value == {"schema_version": "bedroom-creation-1.0", "project_id": project_id,
                                 "request_id": operation, "source_digest": source_digest}:
                        record = ProjectStore.for_project(self.root, project_id).load()
                        if record is None or record.site_draft is None:
                            raise ValueError("published project is invalid")
                        load_project_room_visual(self.root, project_id, record.site_draft)
                        return self._bedroom_created(project_id)
                if (recovery_fingerprint is not None and project_id != self.active_project_id
                        and self._recovery_fingerprint(project_id) == recovery_fingerprint):
                    recover_existing = True
                else:
                    raise FileExistsError("project name already exists")
            stage = workspaces / str(uuid4())
            staged_root = stage / "staged-state"
            staged_root.mkdir(parents=True, exist_ok=False)
            self._write_journal(journal, operation, project_id, source_digest, "preparing", recovery_fingerprint)
            try:
                ProjectCatalog(staged_root, "default").create_empty(project_id)
                project_dir = staged_root / "projects" / project_id
                assets_dir = project_dir / "assets"
                assets_dir.mkdir(exist_ok=False)
                with (assets_dir / "room.jpg").open("xb") as stream:
                    stream.write(photo)
                recipe = {
                    "schema_version": ROOM_RECIPE_VERSION, "project_id": project_id,
                    "prompt": draft.input_revision.prompt,
                    "photo": {"relative_path": "assets/room.jpg", "sha256": sha256(photo).hexdigest()},
                    "plan": draft.plan.to_dict(),
                }
                with (project_dir / "room_recipe.json").open("x", encoding="utf-8") as stream:
                    json.dump(recipe, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                    stream.write("\n")
                prepare_project_burger_visual(staged_root, project_id, (0.0, -0.65, 0.002), 90.0)
                import_project_room_recipe(staged_root, project_id)
                checked = ProjectStore.for_project(staged_root, project_id).load()
                if checked is None or checked.site_draft is None:
                    raise ValueError("staged project has no validated draft")
                load_project_room_visual(staged_root, project_id, checked.site_draft)
                (project_dir / "creation_receipt.json").write_text(json.dumps({
                    "schema_version": "bedroom-creation-1.0", "project_id": project_id,
                    "request_id": operation, "source_digest": source_digest,
                }, sort_keys=True), encoding="utf-8")
                self._write_journal(journal, operation, project_id, source_digest, "validated", recovery_fingerprint)
                if recover_existing:
                    if self._recovery_fingerprint(project_id) != recovery_fingerprint:
                        raise ValueError("incomplete project changed during recovery")
                    recovery_root = self._checked_child(transactions, "recovered-originals")
                    os.rename(destination, recovery_root / f"{project_id}-{operation}")
                # Same-filesystem rename publishes only a complete, reloaded project.
                os.rename(project_dir, destination)
                published = ProjectStore.for_project(self.root, project_id).load()
                if published is None or published.site_draft != checked.site_draft:
                    raise ValueError("published project failed final validation")
                load_project_room_visual(self.root, project_id, published.site_draft)
            except Exception:
                if not destination.exists():
                    self._write_journal(journal, operation, project_id, source_digest, "failed", recovery_fingerprint)
                raise
            self._write_journal(journal, operation, project_id, source_digest, "published", recovery_fingerprint)
            return self._bedroom_created(project_id)
        finally:
            lock_path.unlink()
            request_lock_path.unlink()

    @staticmethod
    def _checked_child(parent: Path, name: str) -> Path:
        path = parent / name
        if path.is_symlink() or (path.exists() and (not path.is_dir() or path.resolve() != path)):
            raise ValueError("project transaction directory is invalid")
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("project transaction directory is invalid")
        return path

    @staticmethod
    def _write_journal(path: Path, operation: str, project_id: str, source_digest: str,
                       state: str, recovery_fingerprint: str | None) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"schema_version": "bedroom-transaction-1.0",
            "request_id": operation, "project_id": project_id,
            "source_digest": source_digest, "recovery_fingerprint": recovery_fingerprint,
            "state": state}, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _bedroom_created(self, project_id: str) -> dict[str, object]:
        return {"created_project_id": project_id, "catalog": self.snapshot(),
                "source": "preserved_bedroom_photo", "build_allowed": False,
                "physical_authority": False}

    def _recovery_fingerprint(self, project_id: str) -> str | None:
        """Fingerprint only a nonactive, undrafted legacy folder within this root."""
        if project_id == self.active_project_id:
            return None
        folder = self.root / "projects" / checked_project_id(project_id)
        if not folder.is_dir() or folder.is_symlink() or folder.resolve() != folder:
            return None
        try:
            record_path = folder / "project.json"
            if not record_path.is_file() or record_path.is_symlink() or record_path.stat().st_size > 5 * 1024 * 1024:
                return None
            record = ProjectRecord.from_dict(json.loads(record_path.read_text(encoding="utf-8")))
            if record.project_id != project_id or record.latest_input or record.draft or record.site_draft:
                return None
            entries = sorted(folder.rglob("*"), key=lambda item: item.as_posix())
            if len(entries) > 64 or any(item.is_symlink() for item in entries):
                return None
            from .room_recipe import _BURGER_FILES
            for item in entries:
                parts = item.relative_to(folder).parts
                if parts[0] in {"project.json", "room_recipe.json", "room_recipe.before-burger.json",
                                "room_recipe.burger.tmp"}:
                    if len(parts) != 1 or not item.is_file():
                        return None
                elif parts[0] == "assets":
                    if len(parts) == 2 and parts[1] == "room.jpg" and item.is_file():
                        continue
                    if len(parts) > 1 and parts[1] == "burger":
                        relative = Path(*parts[2:]).as_posix()
                        if item.is_dir() or relative in _BURGER_FILES:
                            continue
                    if len(parts) == 1 and item.is_dir():
                        continue
                    return None
                elif parts[0] == "inputs":
                    # A failed import may have written an immutable input archive.
                    if len(parts) == 1 and item.is_dir():
                        continue
                    if len(parts) == 2 and len(parts[1]) == 64 and item.is_dir():
                        continue
                    if (len(parts) == 3 and len(parts[1]) == 64 and item.is_file()
                            and (parts[2] == "revision.json" or
                                 (parts[2].endswith(".bin") and len(parts[2]) == 68))):
                        continue
                    return None
                else:
                    return None
            files = [item for item in entries if item.is_file()]
            if not files or any(item.stat().st_size > 20 * 1024 * 1024 for item in files):
                return None
            return canonical_sha256({"project_id": project_id, "files": [
                [item.relative_to(folder).as_posix(), sha256(item.read_bytes()).hexdigest()]
                for item in files]})
        except (OSError, ValueError, TypeError):
            return None

    def snapshot(self) -> dict[str, object]:
        projects = [self._describe("default", validate_scene=False)]
        folder = self.root / "projects"
        truncated = False
        if folder.is_dir() and not folder.is_symlink() and folder.resolve() == self.root / "projects":
            # Bound the response, not which existing project may be opened.
            # Keep recent chats visible after the old 64-row listing fills up.
            # No project records are parsed during this metadata selection.
            def candidates():
                nonlocal truncated
                count=0
                for entry in folder.iterdir():
                    if (entry.is_dir() and not entry.is_symlink() and
                            PROJECT_ID_PATTERN.fullmatch(entry.name) and entry.name!='default'
                            and entry.resolve()==folder/entry.name):
                        count+=1
                        if count>64:truncated=True
                        try:yield (entry.stat().st_mtime_ns,entry.name,entry)
                        except OSError:continue
            entries=nlargest(64,candidates(),key=lambda row:(row[0],row[1]))
            for _,_,entry in entries:
                if len(projects) >= 65:
                    truncated = True
                    break
                if (entry.is_dir() and not entry.is_symlink()
                        and PROJECT_ID_PATTERN.fullmatch(entry.name)
                        and entry.name != "default"
                        and entry.resolve() == folder / entry.name):
                    projects.append(self._describe(entry.name, validate_scene=False))
            if self.active_project_id != "default" and not any(
                item["project_id"] == self.active_project_id for item in projects
            ):
                active_dir = folder / self.active_project_id
                if active_dir.is_dir() and not active_dir.is_symlink() and active_dir.resolve() == active_dir:
                    projects.append(self._describe(self.active_project_id, validate_scene=False))
        return {
            "schema_version": "project-catalog-1.0",
            "active_project_id": self.active_project_id,
            "preserved_bedroom_available": self._preserved_bedroom_available(),
            "burger_visual_available": self._burger_visual_available(),
            "switch_requires_restart": True,
            "saved_approval_restored": False,
            "truncated": truncated,
            "projects": projects,
        }

    @staticmethod
    def _preserved_bedroom_available() -> bool:
        # The generic offline installer deliberately omits this user's private
        # photo and large pinned USD. Never imply that the copy option works
        # merely because its UI code is present in a release.
        from .bedroom_review import ROOT, ASSET_RELATIVE
        return all(path.is_file() for path in (
            ROOT / "artifacts/photo-scan-review-20260927/room.jpg",
            ROOT / "artifacts/photo-scan-review-20260927/top-view-window-up.jpg",
            ROOT / ASSET_RELATIVE / "turtlebot3_burger.usda",
        ))

    @staticmethod
    def _burger_visual_available() -> bool:
        from .bedroom_review import ROOT, ASSET_RELATIVE
        from .room_recipe import _checked_burger_files
        try:
            _checked_burger_files(ROOT / ASSET_RELATIVE)
            return True
        except (OSError, ValueError):
            return False

    def _listing_record(self, store, project_id):
        """Bounded metadata only, never scene validation or execution authority.

        Opening the selected project still uses ProjectStore.load in _describe's
        default strict path. Listing 65 chats must not compile 65 saved scenes.
        """
        store._check_location()
        if not store.path.is_file():return None
        stat=store.path.stat();stamp=(stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size)
        cached=self._listing_records.get(project_id)
        if cached and cached[0]==stamp:return dict(cached[1])
        value=json.loads(store.path.read_text(encoding='utf-8'))
        fields={'schema_version','project_id','latest_input','draft','updated_at_utc'}
        if (not isinstance(value,dict) or value.get('schema_version') not in {'1.0','2.0'}
                or set(value)!=(fields if value['schema_version']=='1.0' else fields|{'site_draft'})
                or value.get('project_id')!=project_id
                or not isinstance(value.get('updated_at_utc'),str) or len(value['updated_at_utc'])>64
                or any(value.get(key) is not None and not isinstance(value[key],dict)
                    for key in ('latest_input','draft','site_draft'))
                or value.get('draft') is not None and value.get('site_draft') is not None):
            raise ValueError('project listing metadata is invalid')
        summary={key:({} if value.get(key) is not None else None) for key in ('draft','site_draft')}
        if len(self._listing_records)>=128:self._listing_records.pop(next(iter(self._listing_records)),None)
        self._listing_records[project_id]=(stamp,summary)
        return dict(summary)

    def _describe(self, project_id: str, *, validate_scene=True) -> dict[str, object]:
        status = "empty"
        kind = "default" if project_id == "default" else "named_room"
        try:
            store = ProjectStore.for_project(self.root, project_id)
            if store.path.is_file() and store.path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("project record is too large for inventory")
            record = store.load() if validate_scene else self._listing_record(store,project_id)
            if record is not None:
                has_draft=bool(record.site_draft or record.draft) if validate_scene else (
                    record.get('site_draft') is not None or record.get('draft') is not None)
                if has_draft:
                    status = "review_required"
                elif project_id != "default" and (store.path.parent / "room_recipe.json").exists():
                    from .room_recipe import load_project_room_recipe
                    load_project_room_recipe(self.root, project_id)
                    status = "import_required"
                else:
                    status = "empty"
            elif project_id != "default":
                from .room_recipe import load_project_room_recipe
                load_project_room_recipe(self.root, project_id)
                status = "import_required"
        except (OSError, ValueError, TypeError):
            status = "source_invalid"
        recovery = self._recovery_fingerprint(project_id) if project_id != "default" and status in {'empty','import_required'} else None
        if status == "empty" and recovery is not None:
            files = [entry.name for entry in (self.root / "projects" / project_id).iterdir()]
            if any(name not in {"project.json"} for name in files):
                status = "recovery_required"
        return {"project_id": project_id, "kind": kind, "status": status,
                "active": project_id == self.active_project_id,
                "recovery_fingerprint": recovery if status in {"recovery_required", "import_required"} else None,
                **self._conversation_summary(project_id, named_project_state_path(self.root, project_id))}

    def selected_project(self,project_id):
        """Fresh validation of a requested local ID, independent of list paging.

        A catalog page is presentation, not project existence or edit authority.
        Paths, records and normal switch/mission guards still apply.
        """
        project_id=checked_project_id(project_id)
        folder=self.root/'projects'/project_id
        if project_id!='default' and (not folder.is_dir() or folder.is_symlink() or folder.resolve()!=folder):
            return None
        return self._describe(project_id)

    def _conversation_summary(self, project_id: str, project_path: Path) -> dict:
        """Bounded read-only labels, not restored work or raw attachment data."""
        fallback = {'display_name': project_id, 'message_count': 0,
                    'last_message_at': None, 'conversation_status': 'empty'}
        path = project_path.with_suffix('.conversation.json')
        try:
            if not path.exists():
                return fallback
            if (project_path.parent.is_symlink() or project_path.parent.resolve() != project_path.parent
                    or path.is_symlink() or path.resolve().parent != project_path.parent):
                raise ValueError('unsafe conversation path')
            stat = path.stat()
            if stat.st_size > 20 * 1024 * 1024:
                raise ValueError('conversation summary budget')
            stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
            cached = self._conversation_summaries.get(project_id)
            if cached and cached[0] == stamp:
                return dict(cached[1])
            value = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or value.get('schema_version') != 'conversation-1.0'
                    or value.get('project_id') != project_id or not isinstance(value.get('messages'), list)
                    or len(value['messages']) > 5000):
                raise ValueError('invalid conversation summary')
            messages = value['messages']
            if any(not isinstance(row, dict) or row.get('role') not in {'user', 'assistant'}
                   or not isinstance(row.get('content'), str) or not isinstance(row.get('created_at'), str)
                   or len(row['created_at']) > 64 for row in messages):
                raise ValueError('invalid message summary')
            first = next((row for row in messages if row['role'] == 'user'), None)
            title = ' '.join(first['content'].split())[:80] if first else ''
            if first and not title and first.get('attachments'):
                title = 'Photo Twin'
            summary = dict(display_name=title or project_id, message_count=len(messages),
                           last_message_at=messages[-1]['created_at'] if messages else None,
                           conversation_status='saved' if messages else 'empty')
            if len(self._conversation_summaries) >= 128:
                self._conversation_summaries.pop(next(iter(self._conversation_summaries)),None)
            self._conversation_summaries[project_id] = (stamp, summary)
            return dict(summary)
        except (OSError, ValueError, TypeError, UnicodeError):
            return {**fallback, 'conversation_status': 'unavailable'}
