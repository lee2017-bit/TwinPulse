# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A2 project inventory remains read-only and never switches a live engine."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
for name in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_app import CommandBroker, LocalApiServer  # noqa: E402
from twinpulse_app.project_catalog import ProjectCatalog  # noqa: E402
from twinpulse_app.project_store import ProjectStore  # noqa: E402
from tests.integration.test_a2_room_recipe import write_recipe  # noqa: E402
from twinpulse_app.room_recipe import import_project_room_recipe  # noqa: E402
from twinpulse_app.room_recipe import load_project_room_visual  # noqa: E402


class ProjectCatalogTests(unittest.TestCase):
    def test_unselected_listing_candidates_do_not_resolve_every_path(self):
        import os
        with TemporaryDirectory() as directory:
            root=Path(directory);catalog=ProjectCatalog(root,'default')
            for index in range(70):
                project=root/'projects'/('chat_'+str(index).zfill(3));project.mkdir(parents=True)
                os.utime(project,ns=(1_000_000_000+index,1_000_000_000+index))
            resolved=[];original=Path.resolve
            def checked(path,*args,**kwargs):
                if path.parent==root/'projects':resolved.append(path.name)
                return original(path,*args,**kwargs)
            with patch.object(Path,'resolve',checked):snapshot=catalog.snapshot()
            self.assertTrue(snapshot['truncated'])
            self.assertNotIn('chat_000',resolved)
            self.assertIn('chat_069',resolved)
            self.assertNotIn('chat_000',{row['project_id'] for row in snapshot['projects']})

    def test_listing_does_not_compile_scenes_but_selection_still_strictly_validates(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);catalog=ProjectCatalog(root,'default')
            catalog.create_empty('saved_chat')
            path=root/'projects/saved_chat/project.json'
            value=json.loads(path.read_text());value['site_draft']={'invalid_inner_scene':'not authority'}
            path.write_text(json.dumps(value),encoding='utf-8');before=path.read_bytes()
            with patch.object(ProjectStore,'load',side_effect=AssertionError('No full scene load in listing')):
                row=next(r for r in catalog.snapshot()['projects'] if r['project_id']=='saved_chat')
            self.assertEqual(row['status'],'review_required')
            self.assertEqual(catalog.selected_project('saved_chat')['status'],'source_invalid')
            self.assertEqual(path.read_bytes(),before)
            value['project_id']='wrong_identity';path.write_text(json.dumps(value),encoding='utf-8')
            row=next(r for r in catalog.snapshot()['projects'] if r['project_id']=='saved_chat')
            self.assertEqual(row['status'],'source_invalid')

    def test_recent_listing_cap_cannot_make_a_created_or_older_project_unopenable(self):
        import os
        with TemporaryDirectory() as directory:
            root=Path(directory);catalog=ProjectCatalog(root,'default')
            for index in range(70):
                identity='chat_'+str(index).zfill(3)
                catalog.create_empty(identity)
                os.utime(root/'projects'/identity,ns=(1_000_000_000+index,1_000_000_000+index))
            snapshot=catalog.snapshot();ids={r['project_id'] for r in snapshot['projects']}
            self.assertTrue(snapshot['truncated']);self.assertLessEqual(len(ids),65)
            self.assertIn('chat_069',ids);self.assertNotIn('chat_000',ids)
            self.assertEqual(catalog.selected_project('chat_000')['status'],'empty')
            self.assertEqual(catalog.selected_project('chat_069')['status'],'empty')
            self.assertIsNone(catalog.selected_project('absent'))
            (root/'projects/chat_000/project.json').write_bytes(b'preserved invalid record')
            self.assertEqual(catalog.selected_project('chat_000')['status'],'source_invalid')
            with self.assertRaises(ValueError):catalog.selected_project('../outside')

    def test_conversation_labels_are_read_only_and_never_include_attachment_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, 'default')
            catalog.create_empty('saved_chat')
            path = root / 'projects/saved_chat/project.conversation.json'
            value = {'schema_version': 'conversation-1.0', 'project_id': 'saved_chat',
                     'messages': [{'role': 'user', 'content': '  나의 침실  만들기 ', 'created_at': '2026-10-12T01:00:00Z'},
                                  {'role': 'assistant', 'content': 'Previous failure', 'created_at': '2026-10-12T01:01:00Z'}],
                     'thumbnails': {'private': 'not-for-catalog'}, 'physical_authority': False}
            path.write_text(json.dumps(value), encoding='utf-8')
            before = path.read_bytes()
            row = next(item for item in catalog.snapshot()['projects'] if item['project_id'] == 'saved_chat')
            self.assertEqual(row['display_name'], '나의 침실 만들기')
            self.assertEqual(row['message_count'], 2)
            self.assertEqual(row['conversation_status'], 'saved')
            self.assertNotIn('thumbnails', row)
            self.assertEqual(path.read_bytes(), before)
            value['messages'][0]['content'] = '다른 이름'
            path.write_text(json.dumps(value), encoding='utf-8')
            row = next(item for item in catalog.snapshot()['projects'] if item['project_id'] == 'saved_chat')
            self.assertEqual(row['display_name'], '다른 이름')

    def test_invalid_conversation_summary_preserves_original_and_does_not_break_inventory(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, 'default')
            catalog.create_empty('saved_chat')
            path = root / 'projects/saved_chat/project.conversation.json'
            path.write_bytes(b'{invalid original')
            row = next(item for item in catalog.snapshot()['projects'] if item['project_id'] == 'saved_chat')
            self.assertEqual(row['conversation_status'], 'unavailable')
            self.assertEqual(path.read_bytes(), b'{invalid original')

    def test_bedroom_creation_failure_never_publishes_partial_project_and_same_id_retries(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            request_id = str(uuid4())
            with patch("twinpulse_app.room_recipe.prepare_project_burger_visual",
                       side_effect=OSError("injected copy failure")):
                with self.assertRaises(OSError):
                    catalog.create_from_preserved_bedroom("retry_room", request_id)
            self.assertFalse((root / "projects" / "retry_room").exists())
            self.assertNotIn("retry_room", [item["project_id"] for item in catalog.snapshot()["projects"]])
            result = catalog.create_from_preserved_bedroom("retry_room", request_id)
            self.assertEqual(result["created_project_id"], "retry_room")
            project = root / "projects" / "retry_room"
            original = (project / "project.json").read_bytes()
            self.assertEqual(catalog.create_from_preserved_bedroom("retry_room", request_id)["created_project_id"],
                             "retry_room")
            self.assertEqual((project / "project.json").read_bytes(), original)
            with self.assertRaises(ValueError):
                catalog.create_from_preserved_bedroom("other_room", request_id)
            with self.assertRaises(FileExistsError):
                catalog.create_from_preserved_bedroom("retry_room", str(uuid4()))

    def test_legacy_partial_room_requires_explicit_fingerprint_and_preserves_original(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            catalog.create_empty("partial_room")
            original = root / "projects" / "partial_room"
            (original / "assets").mkdir()
            (original / "assets" / "room.jpg").write_bytes(b"incomplete original")
            status = next(item for item in catalog.snapshot()["projects"] if item["project_id"] == "partial_room")
            self.assertEqual(status["status"], "recovery_required")
            fingerprint = status["recovery_fingerprint"]
            self.assertIsNotNone(fingerprint)
            with self.assertRaises(FileExistsError):
                catalog.create_from_preserved_bedroom("partial_room", str(uuid4()), "0" * 64)
            request_id = str(uuid4())
            result = catalog.create_from_preserved_bedroom("partial_room", request_id, fingerprint)
            self.assertEqual(result["created_project_id"], "partial_room")
            archived = root / "project-transactions" / "recovered-originals" / f"partial_room-{request_id}"
            self.assertEqual((archived / "assets" / "room.jpg").read_bytes(), b"incomplete original")
            self.assertIsNotNone(ProjectStore.for_project(root, "partial_room").load().site_draft)
            self.assertEqual(catalog.create_from_preserved_bedroom("partial_room", request_id, fingerprint)
                             ["created_project_id"], "partial_room")

    def test_bedroom_import_and_publish_failures_leave_name_retryable(self):
        for target in ("twinpulse_app.room_recipe.import_project_room_recipe",
                       "twinpulse_app.project_catalog.os.rename"):
            with self.subTest(target=target), TemporaryDirectory() as directory:
                root = Path(directory)
                catalog = ProjectCatalog(root, "default")
                request_id = str(uuid4())
                with patch(target, side_effect=OSError("injected stage failure")):
                    with self.assertRaises(OSError):
                        catalog.create_from_preserved_bedroom("retry_room", request_id)
                self.assertFalse((root / "projects" / "retry_room").exists())
                self.assertEqual(catalog.create_from_preserved_bedroom("retry_room", request_id)
                                 ["created_project_id"], "retry_room")
                self.assertIsNotNone(ProjectStore.for_project(root, "retry_room").load().site_draft)

    def test_same_request_id_cannot_enter_two_project_creations_at_once(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            request_id = str(uuid4())
            locks = root / "project-transactions" / "locks"
            locks.mkdir(parents=True)
            held = locks / f"request-{request_id}.lock"
            held.write_bytes(b"")
            with self.assertRaises(FileExistsError):
                catalog.create_from_preserved_bedroom("other_room", request_id)
            self.assertTrue(held.exists())
            self.assertFalse((root / "projects" / "other_room").exists())
            held.unlink()
            self.assertEqual(catalog.create_from_preserved_bedroom("other_room", request_id)
                             ["created_project_id"], "other_room")

    def test_generic_release_does_not_advertise_private_bedroom_source(self):
        with TemporaryDirectory() as directory, patch("twinpulse_app.bedroom_review.ROOT", Path(directory)):
            snapshot = ProjectCatalog(Path(directory), "default").snapshot()
        self.assertFalse(snapshot["preserved_bedroom_available"])

    def test_explicit_saved_bedroom_project_is_reviewable_and_does_not_switch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            created = catalog.create_from_preserved_bedroom("my_room")
            self.assertEqual(created["created_project_id"], "my_room")
            self.assertEqual(created["source"], "preserved_bedroom_photo")
            self.assertFalse(created["build_allowed"])
            self.assertFalse(created["physical_authority"])
            self.assertEqual(created["catalog"]["active_project_id"], "default")
            self.assertIsNone(ProjectStore.for_project(root, "default").load())
            record = ProjectStore.for_project(root, "my_room").load()
            self.assertIsNotNone(record.site_draft)
            self.assertIsNotNone(load_project_room_visual(root, "my_room", record.site_draft))
            self.assertEqual(catalog.snapshot()["projects"][1]["status"], "review_required")
            with self.assertRaises(FileExistsError):
                catalog.create_from_preserved_bedroom("my_room")

    def test_explicit_create_is_empty_and_does_not_switch_active_project(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            result = catalog.create_empty("room_three")
            self.assertEqual(result["created_project_id"], "room_three")
            self.assertEqual(result["catalog"]["active_project_id"], "default")
            statuses = {row["project_id"]: row["status"] for row in result["catalog"]["projects"]}
            self.assertEqual(statuses["room_three"], "empty")
            self.assertIsNone(ProjectStore.for_project(root, "default").load())
            record = ProjectStore.for_project(root, "room_three").load()
            self.assertIsNotNone(record)
            self.assertIsNone(record.latest_input)
            self.assertIsNone(record.site_draft)
            self.assertIsNone(record.draft)
            with self.assertRaises(FileExistsError):
                catalog.create_empty("room_three")
            for invalid in ("default", "../escape", "Room Three", ""):
                with self.assertRaises(ValueError):
                    catalog.create_empty(invalid)

    def test_create_rejects_symlinked_projects_folder(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            try:
                (root / "projects").symlink_to(Path(outside), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are not available")
            with self.assertRaises(ValueError):
                ProjectCatalog(root, "default").create_empty("room_three")
            self.assertFalse((Path(outside) / "room_three").exists())

    def test_named_project_cannot_attach_unscoped_physical_history(self):
        with self.assertRaisesRegex(ValueError, "cannot share"):
            LocalApiServer(CommandBroker(project_id="room_one"),
                           product_bootstrap_secret="p" * 43,
                           engine_bootstrap_secret="e" * 43,
                           physical_controller=object())

    def test_inventory_is_bounded_and_keeps_selected_project_visible(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            projects = root / "projects"
            projects.mkdir()
            for index in range(70):
                (projects / f"room_{index:02d}").mkdir()
            result = ProjectCatalog(root, "room_69").snapshot()
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(result["projects"]), 66)
            self.assertIn("room_69", [item["project_id"] for item in result["projects"]])
            with self.assertRaises(ValueError):
                ProjectCatalog(root, "../escape")

    def test_two_projects_and_changed_source_are_reported_without_switch_or_writes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            photo_one, _ = write_recipe(root, "room_one", "red", 2.8)
            write_recipe(root, "room_two", "blue", 3.3)
            import_project_room_recipe(root, "room_one")
            catalog = ProjectCatalog(root, "room_one")
            result = catalog.snapshot()
            rows = {item["project_id"]: item for item in result["projects"]}
            self.assertEqual(result["active_project_id"], "room_one")
            self.assertEqual(rows["room_one"]["status"], "review_required")
            self.assertEqual(rows["room_two"]["status"], "import_required")
            self.assertFalse(result["saved_approval_restored"])
            self.assertTrue(result["switch_requires_restart"])
            original = (root / "projects" / "room_one" / "project.json").read_bytes()
            photo_one.write_bytes(b"changed")
            self.assertEqual({item["project_id"]: item["status"] for item in catalog.snapshot()["projects"]}["room_one"],
                             "source_invalid")
            self.assertEqual((root / "projects" / "room_one" / "project.json").read_bytes(), original)

    def test_authenticated_api_exposes_only_status_not_paths_or_secrets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            server = LocalApiServer(CommandBroker(), product_bootstrap_secret="p" * 43,
                                    engine_bootstrap_secret="e" * 43,
                                    project_catalog=ProjectCatalog(root, "default"))
            server.start()
            try:
                def get(cookie=""):
                    req = Request(server.base_url + "/v1/product/projects",
                                  headers={"Cookie": cookie} if cookie else {})
                    try:
                        with urlopen(req, timeout=3) as response:
                            return response.status, json.loads(response.read())
                    except HTTPError as error:
                        return error.code, json.loads(error.read())
                self.assertEqual(get()[0], 401)
                req = Request(server.base_url + "/v1/bootstrap",
                              data=json.dumps({"role": "product", "secret": "p" * 43}).encode(),
                              headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=3) as response:
                    cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                status, result = get(cookie)
                self.assertEqual(status, 200)
                self.assertEqual(result["projects"][1]["project_id"], "room_one")
                self.assertNotIn(str(root), json.dumps(result))
                self.assertNotIn("secret", json.dumps(result))
            finally:
                server.stop()

    def test_create_api_requires_session_csrf_and_exact_body(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broker = CommandBroker()
            server = LocalApiServer(broker, product_bootstrap_secret="p" * 43,
                                    engine_bootstrap_secret="e" * 43,
                                    project_catalog=ProjectCatalog(root, "default"))
            server.start()
            try:
                def create(body, cookie="", csrf="", endpoint="create"):
                    headers = {"Content-Type": "application/json"}
                    if cookie:
                        headers["Cookie"] = cookie
                    if csrf:
                        headers["X-TwinPulse-CSRF"] = csrf
                    request = Request(server.base_url + "/v1/product/projects/" + endpoint,
                                      data=json.dumps(body).encode(), headers=headers)
                    try:
                        with urlopen(request, timeout=3) as response:
                            return response.status, json.loads(response.read())
                    except HTTPError as error:
                        return error.code, json.loads(error.read())
                self.assertEqual(create({"project_id": "room_three"})[0], 401)
                request = Request(server.base_url + "/v1/bootstrap",
                                  data=json.dumps({"role": "product", "secret": "p" * 43}).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=3) as response:
                    cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                    csrf = json.loads(response.read())["csrf_token"]
                self.assertEqual(create({"project_id": "room_three"}, cookie)[0], 403)
                self.assertEqual(create({"project_id": "room_three", "switch": True}, cookie, csrf)[0], 400)
                self.assertEqual(create({"project_id": "../escape"}, cookie, csrf)[0], 400)
                status, payload = create({"project_id": "room_three"}, cookie, csrf)
                self.assertEqual(status, 201)
                self.assertEqual(payload["catalog"]["active_project_id"], "default")
                self.assertEqual(create({"project_id": "room_three"}, cookie, csrf)[0], 409)
                self.assertEqual(create({"project_id": "my_room"}, cookie, endpoint="create-bedroom")[0], 403)
                self.assertEqual(create({"project_id": "my_room", "overwrite": True}, cookie, csrf, "create-bedroom")[0], 400)
                status, bedroom = create({"project_id": "my_room"}, cookie, csrf, "create-bedroom")
                self.assertEqual(status, 201)
                self.assertEqual(bedroom["source"], "preserved_bedroom_photo")
                self.assertFalse(bedroom["physical_authority"])
                self.assertEqual(create({"project_id": "my_room"}, cookie, csrf, "create-bedroom")[0], 409)
                retry_id = str(uuid4())
                retry_body = {"project_id": "retry_room", "request_id": retry_id}
                with patch("twinpulse_app.room_recipe.prepare_project_burger_visual",
                           side_effect=OSError("injected copy failure")):
                    self.assertEqual(create(retry_body, cookie, csrf, "create-bedroom")[0], 409)
                self.assertFalse((root / "projects" / "retry_room").exists())
                self.assertEqual(create(retry_body, cookie, csrf, "create-bedroom")[0], 201)
                self.assertEqual(create(retry_body, cookie, csrf, "create-bedroom")[0], 201)
                self.assertIsNotNone(ProjectStore.for_project(root, "retry_room").load().site_draft)
                ProjectCatalog(root, "default").create_empty("partial_room")
                partial = root / "projects" / "partial_room"
                (partial / "assets").mkdir()
                (partial / "assets" / "room.jpg").write_bytes(b"preserve old partial")
                recovery = next(row for row in ProjectCatalog(root, "default").snapshot()["projects"]
                                if row["project_id"] == "partial_room")
                recovery_body = {"project_id": "partial_room", "request_id": str(uuid4()),
                                 "recovery_fingerprint": recovery["recovery_fingerprint"]}
                self.assertEqual(create({**recovery_body, "recovery_fingerprint": "0" * 64},
                                        cookie, csrf, "recover-bedroom")[0], 409)
                self.assertEqual(create(recovery_body, cookie, csrf, "recover-bedroom")[0], 201)
                preserved = root / "project-transactions" / "recovered-originals" / (
                    f"partial_room-{recovery_body['request_id']}")
                self.assertEqual((preserved / "assets" / "room.jpg").read_bytes(), b"preserve old partial")
                self.assertEqual(broker.project_id, "default")
                self.assertIsNone(ProjectStore.for_project(root, "default").load())
                self.assertNotIn(str(root), json.dumps(payload))
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
