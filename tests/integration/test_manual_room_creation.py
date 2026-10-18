# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""E2 user-photo/manual-dimension creation without any provider or robot."""

from __future__ import annotations

from io import BytesIO
import base64
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
for name in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_app.manual_room import manual_room_plan  # noqa: E402
from twinpulse_app import CommandBroker, LocalApiServer  # noqa: E402
from twinpulse_app.project_catalog import ProjectCatalog  # noqa: E402
from twinpulse_app.project_store import ProjectStore  # noqa: E402
from twinpulse_app.room_recipe import load_project_room_recipe, load_project_room_visual  # noqa: E402


def photo(color: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


class ManualRoomCreationTests(unittest.TestCase):
    def create(self, catalog: ProjectCatalog, project_id: str, image: bytes,
               request_id: str, *, burger: bool = False):
        return catalog.create_from_manual_room(
            project_id, prompt="My room; dimensions entered by user", photo=image,
            media_type="image/png", width_m=3.2, length_m=4.4, wall_height_m=2.4,
            include_burger_visual=burger, request_id=request_id,
        )

    def test_two_independent_rooms_and_idempotent_exact_retry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            first_id = str(uuid4())
            result = self.create(catalog, "bedroom_a", photo("red"), first_id)
            self.assertFalse(result["photo_interpreted"])
            self.assertFalse(result["physical_authority"])
            first_store = ProjectStore.for_project(root, "bedroom_a")
            first_bytes = first_store.path.read_bytes()
            second = self.create(catalog, "bedroom_b", photo("blue"), str(uuid4()))
            self.assertEqual(second["created_project_id"], "bedroom_b")
            self.assertEqual(first_store.path.read_bytes(), first_bytes)
            source, saved_photo = load_project_room_recipe(root, "bedroom_a")
            self.assertEqual(saved_photo, photo("red"))
            self.assertIsNone(source.site.robot)
            self.assertIsNone(source.site.mission)
            self.assertEqual(len(source.site.scene.objects), 4)
            self.assertEqual(self.create(catalog, "bedroom_a", photo("red"), first_id)
                             ["created_project_id"], "bedroom_a")
            self.assertEqual(first_store.path.read_bytes(), first_bytes)
            with self.assertRaises(FileExistsError):
                self.create(catalog, "bedroom_a", photo("green"), first_id)
            self.assertEqual(first_store.path.read_bytes(), first_bytes)

    def test_user_dimensions_not_measured_and_invalid_input_does_not_publish(self):
        for bad in (True, float("nan"), 0.2, 12.1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                manual_room_plan("room", bad, 3.0, 2.4)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            with self.assertRaises(ValueError):
                self.create(catalog, "bad_room", b"not an image", str(uuid4()))
            self.assertFalse((root / "projects" / "bad_room").exists())

    def test_user_selected_furniture_persists_and_invalid_placement_does_not_publish(self):
        selected = [{"kind": "bed", "center_m": [-0.8, 0.7], "yaw_deg": 0},
                    {"kind": "desk", "center_m": [0.8, 0.7], "yaw_deg": 0}]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            result = catalog.create_from_manual_room(
                "furnished", prompt="Two pieces explicitly selected", photo=photo("blue"),
                media_type="image/png", width_m=3.6, length_m=5.2, wall_height_m=2.6,
                include_burger_visual=False, request_id=str(uuid4()), furniture=selected)
            self.assertFalse(result["photo_interpreted"])
            record, image = load_project_room_recipe(root, "furnished")
            self.assertEqual(image, photo("blue"))
            self.assertEqual(record.plan.plan_version, "2.1")
            self.assertEqual([call.arguments["kind"] for call in record.plan.calls[4:]], ["bed", "desk"])
            self.assertEqual(len(record.site.scene.objects), 4 + 3 + 5)
            self.assertTrue(all(item.kind == "equipment" for item in record.site.scene.objects[4:]))
            for name, furniture in (("outside", [{"kind": "bed", "center_m": [1.8, 0], "yaw_deg": 0}]),
                                    ("overlap", [selected[0], selected[0]]),
                                    ("unknown", [{"kind": "rack_from_photo", "center_m": [0, 0], "yaw_deg": 0}])):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    catalog.create_from_manual_room(
                        name, prompt="bad", photo=photo("blue"), media_type="image/png",
                        width_m=3.6, length_m=5.2, wall_height_m=2.6,
                        include_burger_visual=False, request_id=str(uuid4()), furniture=furniture)
                self.assertFalse((root / "projects" / name).exists())
            with self.assertRaises(ValueError):
                catalog.create_from_manual_room(
                    "bad_room", prompt="room", photo=photo("red"), media_type="image/jpeg",
                    width_m=3.0, length_m=4.0, wall_height_m=2.4,
                    include_burger_visual=False, request_id=str(uuid4()),
                )
            self.assertFalse((root / "projects" / "bad_room").exists())

    def test_failure_is_not_published_and_burger_visual_is_optional_and_pinned(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = ProjectCatalog(root, "default")
            request_id = str(uuid4())
            with patch("twinpulse_app.room_recipe.import_project_room_recipe",
                       side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    self.create(catalog, "retry_room", photo("red"), request_id)
            self.assertFalse((root / "projects" / "retry_room").exists())
            self.create(catalog, "retry_room", photo("red"), request_id)
            draft = ProjectStore.for_project(root, "retry_room").load().site_draft
            self.assertIsNone(load_project_room_visual(root, "retry_room", draft))
            result = self.create(catalog, "with_burger", photo("blue"), str(uuid4()), burger=True)
            self.assertTrue(result["burger_visual_included"])
            draft = ProjectStore.for_project(root, "with_burger").load().site_draft
            self.assertIsNotNone(load_project_room_visual(root, "with_burger", draft))

    def test_authenticated_manual_room_api_rejects_extra_shape_and_bad_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            server = LocalApiServer(CommandBroker(), product_bootstrap_secret="p" * 43,
                                    engine_bootstrap_secret="e" * 43,
                                    project_catalog=ProjectCatalog(root, "default"))
            server.start()
            try:
                body = {"project_id": "new_room", "request_id": str(uuid4()),
                        "prompt": "User entered 3.2 by 4.4 metre room", "media_type": "image/png",
                        "photo_base64": base64.b64encode(photo("red")).decode("ascii"),
                        "width_m": 3.2, "length_m": 4.4, "wall_height_m": 2.4,
                        "include_burger_visual": False}

                def post(endpoint: str, value: dict, cookie: str = "", csrf: str = ""):
                    headers = {"Content-Type": "application/json"}
                    if cookie:
                        headers["Cookie"] = cookie
                    if csrf:
                        headers["X-TwinPulse-CSRF"] = csrf
                    request = Request(server.base_url + endpoint, data=json.dumps(value).encode(), headers=headers)
                    try:
                        with urlopen(request, timeout=5) as response:
                            return response.status, json.loads(response.read())
                    except HTTPError as error:
                        return error.code, json.loads(error.read())

                endpoint = "/v1/product/projects/create-manual-room"
                self.assertEqual(post(endpoint, body)[0], 401)
                request = Request(server.base_url + "/v1/bootstrap",
                                  data=json.dumps({"role": "product", "secret": "p" * 43}).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=5) as response:
                    cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                    csrf = json.loads(response.read())["csrf_token"]
                self.assertEqual(post(endpoint, body, cookie)[0], 403)
                self.assertEqual(post(endpoint, {**body, "overwrite": True}, cookie, csrf)[0], 400)
                self.assertEqual(post(endpoint, {**body, "photo_base64": "bad!"}, cookie, csrf)[0], 400)
                self.assertEqual(post(endpoint, {**body, "width_m": True}, cookie, csrf)[0], 400)
                self.assertEqual(post(endpoint, {**body, "project_id": "bad_furniture",
                                                 "furniture": [{"kind": "bed", "center_m": [True, 0],
                                                                "yaw_deg": 0}]}, cookie, csrf)[0], 400)
                self.assertFalse((root / "projects" / "new_room").exists())
                self.assertFalse((root / "projects" / "bad_furniture").exists())
                status, created = post(endpoint, body, cookie, csrf)
                self.assertEqual(status, 201)
                self.assertFalse(created["photo_interpreted"])
                self.assertFalse(created["physical_authority"])
                self.assertEqual(post(endpoint, body, cookie, csrf)[0], 201)
                self.assertEqual(post(endpoint, {**body, "request_id": str(uuid4())}, cookie, csrf)[0], 409)
                furnished = {**body, "project_id": "furnished_http", "request_id": str(uuid4()),
                             "furniture": [{"kind": "chair", "center_m": [0.5, 0.5], "yaw_deg": 90}]}
                self.assertEqual(post(endpoint, furnished, cookie, csrf)[0], 201)
                self.assertEqual(ProjectStore.for_project(root, "furnished_http").load().site_draft.plan.plan_version,
                                 "2.1")
                self.assertIsNone(ProjectStore.for_project(root, "default").load())
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
