# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A2 named-project isolation without engine, provider, or device access."""

from __future__ import annotations

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ApplicationService, ProjectRecord, ProjectStore, checked_project_id  # noqa: E402
from twinpulse_app.project_store import named_project_state_path  # noqa: E402
from twinpulse_provider import ImageInput  # noqa: E402
from twinpulse_core import InputArtifactStore  # noqa: E402


class UnusedGateway:
    def cancel_active(self):
        pass

    async def generate(self, request):
        raise AssertionError("no provider call expected")


class NamedProjectTests(unittest.TestCase):
    def test_names_and_default_path(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(named_project_state_path(root, "default"), root / "active_project.json")
            for value in ("../other", "..", ".hidden", "a/b", "a\\b", "UPPER", "", "x" * 65):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    checked_project_id(value)

    def test_two_projects_restart_without_cross_restore(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = ProjectStore.for_project(root, "room_one")
            second = ProjectStore.for_project(root, "room_two")
            app_a = ApplicationService(UnusedGateway(), project_store=first, project_id="room_one")
            app_b = ApplicationService(UnusedGateway(), project_store=second, project_id="room_two")
            self.assertNotEqual(first.path.parent, second.path.parent)
            self.assertEqual(app_a.project_id, "room_one")
            self.assertEqual(app_b.project_id, "room_two")
            self.assertIsNone(app_a.record)
            self.assertIsNone(app_b.record)
            prepared = app_a.prepare_input(
                prompt="first room", images=(ImageInput("room.jpg", "image/jpeg", b"photo"),),
                measurement_constraints=(), generation_settings={"request_schema": "1.0"})
            app_a.select_input(prepared)
            other = app_b.prepare_input(
                prompt="second room", images=(ImageInput("room.jpg", "image/jpeg", b"other"),),
                measurement_constraints=(), generation_settings={"request_schema": "1.0"})
            app_b.select_input(other)
            InputArtifactStore(first.path.parent / "inputs").save(prepared.revision, (("room.jpg", b"photo"),))
            InputArtifactStore(second.path.parent / "inputs").save(other.revision, (("room.jpg", b"other"),))
            self.assertFalse((first.path.parent / "inputs" / other.revision.digest).exists())
            self.assertFalse((second.path.parent / "inputs" / prepared.revision.digest).exists())
            reopened_a = ApplicationService(UnusedGateway(), project_store=first, project_id="room_one")
            reopened_b = ApplicationService(UnusedGateway(), project_store=second, project_id="room_two")
            self.assertEqual(reopened_a.snapshot().persisted_input_revision, prepared.revision.digest)
            self.assertEqual(reopened_b.snapshot().persisted_input_revision, other.revision.digest)
            self.assertFalse(reopened_a.snapshot().build_allowed)
            self.assertFalse(reopened_b.snapshot().build_allowed)
            self.assertFalse((root / "active_project.json").exists())

    def test_identity_corruption_and_concurrent_writer_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore.for_project(root, "room_one")
            with self.assertRaises(ValueError):
                store.save(ProjectRecord("room_two"))
            store.save(ProjectRecord("room_one"))
            self.assertEqual(store.load().project_id, "room_one")
            store.path.write_text(json.dumps(ProjectRecord("room_two").to_dict()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity"):
                store.load()
            store.save(ProjectRecord("room_one"))
            lock = store.path.with_suffix(".json.lock")
            lock.write_text("other writer", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "concurrent"):
                store.save(ProjectRecord("room_one"))
            self.assertTrue(lock.exists())

    def test_stale_temporary_file_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            store = ProjectStore.for_project(Path(directory), "room_one")
            store.save(ProjectRecord("room_one"))
            temporary = store.path.with_suffix(".json.tmp")
            temporary.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale temporary"):
                store.save(ProjectRecord("room_one"))
            self.assertEqual(temporary.read_text(encoding="utf-8"), "preserve")
            self.assertFalse(store.path.with_suffix(".json.lock").exists())


if __name__ == "__main__":
    unittest.main()
