# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic application/workflow selection; no engine, provider or robot calls."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from tests.integration.test_derived_site_review import derived_fixture
from twinpulse_app import ApplicationService, ProjectStore, ProductWorkflow, CommandBroker, LocalApiServer
from twinpulse_app.application import PreparedInput
from twinpulse_app.project_store import ProjectRecord
from twinpulse_app.command_broker import BrokerError


class NoGateway:
    def cancel_active(self): pass
    async def generate(self, request): raise RuntimeError("explicit offline generation failure")


def selection_fixture(folder):
    source, text = derived_fixture()
    store = ProjectStore(Path(folder)/"active_project.json")
    store.save(ProjectRecord("selection-fixture", source.input_revision, site_draft=source))
    app = ApplicationService(NoGateway(), project_store=store)
    broker = CommandBroker()
    workflow = ProductWorkflow(app, broker, mode="explicit_fixture",
        generation_settings_getter=lambda: {"model_id": "offline-fixture"}, gateway_factory=NoGateway)
    body = dict(name=None, input_kind="auto", prompt=source.input_revision.prompt, media_type=None,
                content_base64=None, sidecar_name=None, sidecar_content_base64=None)
    workflow.select_input(body)
    state = app.scan_review.import_archive(app.scan_review.snapshot()["workspace_revision"], text)
    args = (source.input_revision.digest, source.site.scene.revision, state["workspace_revision"])
    return app, workflow, broker, source, args, body


class DerivedSelectionTests(unittest.TestCase):
    def test_actual_http_adopt_restore_auth_csrf_shape_and_stale(self):
        with TemporaryDirectory() as folder:
            app, workflow, broker, _, args, _ = selection_fixture(folder)
            server = LocalApiServer(broker, product_workflow=workflow,
                product_bootstrap_secret="p"*43, engine_bootstrap_secret="e"*43)
            server.start()
            def request(path, body, headers=None):
                req = Request(server.base_url + path, data=json.dumps(body).encode(),
                              headers={"Content-Type": "application/json", **(headers or {})})
                try:
                    with urlopen(req, timeout=3) as response:
                        return response.status, json.loads(response.read()), response.headers
                except HTTPError as error:
                    return error.code, json.loads(error.read()), error.headers
            try:
                _, bootstrap, headers = request("/v1/bootstrap", {"role": "product", "secret": "p"*43})
                auth = {"Cookie": headers["Set-Cookie"].split(";", 1)[0], "X-TwinPulse-CSRF": bootstrap["csrf_token"]}
                body = dict(input_revision=args[0], source_revision=args[1], workspace_revision=args[2])
                path = "/v1/product/derived-review/adopt"
                self.assertEqual(request(path, body)[0], 401)
                self.assertEqual(request(path, body, {"Cookie": auth["Cookie"]})[0], 403)
                self.assertIsNone(app.derived_review)
                self.assertEqual(request(path, {**body, "automatic": True}, auth)[0], 400)
                status, state, _ = request(path, body, auth)
                self.assertEqual(status, 200)
                revision = state["site_draft"]["revision"]
                self.assertIsNone(state["acknowledged_revision"])
                self.assertFalse(state["build_allowed"])
                self.assertEqual(request(path, {**body, "workspace_revision": "stale"}, auth)[0], 409)
                self.assertIsNone(app.derived_review)
                status, state, _ = request("/v1/product/derived-review/restore", dict(input_revision=args[0], source_revision=args[1]), auth)
                self.assertEqual(status, 200)
                self.assertEqual(state["site_draft"]["revision"], revision)
                self.assertIsNone(state["acknowledged_revision"])
            finally:
                server.stop()

    def test_workflow_adopt_new_ack_and_original_unchanged(self):
        with TemporaryDirectory() as folder:
            app, workflow, broker, source, args, _ = selection_fixture(folder)
            before = app._project_store.path.read_bytes()
            workflow.acknowledge(source.site.scene.revision)
            state = workflow.adopt_derived_review(*args)
            draft = state["site_draft"]
            self.assertIsNone(state["acknowledged_revision"])
            self.assertFalse(state["build_allowed"])
            self.assertFalse(draft["run_allowed"])
            self.assertEqual(app._project_store.path.read_bytes(), before)
            self.assertEqual(app.site_draft, source)
            self.assertNotEqual(draft["revision"], source.site.scene.revision)
            self.assertEqual(draft["geometry_provenance"], "offline_review_unverified")
            with self.assertRaises(BrokerError): workflow.acknowledge(source.site.scene.revision)
            with self.assertRaises(BrokerError): workflow.assert_site_build_allowed(draft["artifact_id"], draft["revision"])
            workflow.acknowledge(draft["revision"])
            with self.assertRaisesRegex(BrokerError, "Connected Isaac"):
                workflow.assert_site_build_allowed(draft["artifact_id"], draft["revision"])
            # Contract capability stub only, NOT actual Isaac evidence.
            with patch.object(broker, "site_scene_capable", return_value=True):
                workflow.assert_site_build_allowed(draft["artifact_id"], draft["revision"])
                self.assertTrue(workflow.snapshot()["build_allowed"])
            with self.assertRaises(BrokerError): workflow.assert_run_not_site_draft()

    def test_explicit_restore_revalidates_and_never_restores_ack(self):
        with TemporaryDirectory() as folder:
            app, workflow, _, source, args, body = selection_fixture(folder)
            state = workflow.adopt_derived_review(*args)
            revision = state["site_draft"]["revision"]
            workflow.acknowledge(revision)
            restored = ApplicationService(NoGateway(), project_store=app._project_store)
            self.assertIsNone(restored.derived_review)
            restored.select_input(PreparedInput(source.input_revision, (), ()))
            record = restored.adopt_derived_review(args[0], args[1], None, restore=True)
            self.assertEqual(record.site.scene.revision, revision)
            workflow.select_input(body)
            self.assertIsNone(app.derived_review)
            state = workflow.adopt_derived_review(args[0], args[1], None, restore=True)
            self.assertEqual(state["site_draft"]["revision"], revision)
            self.assertIsNone(state["acknowledged_revision"])
            self.assertFalse(state["build_allowed"])

    def test_bad_input_source_workspace_and_store_failure_clear_previous_eligibility(self):
        with TemporaryDirectory() as folder:
            app, workflow, _, _, args, _ = selection_fixture(folder)
            for index in range(3):
                workflow.adopt_derived_review(*args)
                bad = list(args); bad[index] = "stale"
                with self.assertRaises(BrokerError): workflow.adopt_derived_review(*bad)
                self.assertIsNone(app.derived_review)
                self.assertFalse(workflow.snapshot()["build_allowed"])
            workflow.adopt_derived_review(*args)
            before = app._derived_store.path.read_bytes()
            with patch.object(app._derived_store, "save", side_effect=OSError("synthetic disk failure")):
                with self.assertRaises(BrokerError): workflow.adopt_derived_review(*args)
            self.assertIsNone(app.derived_review)
            self.assertEqual(app._derived_store.path.read_bytes(), before)
            self.assertIsNone(workflow.snapshot()["site_draft"]["artifact_id"])

    def test_input_cancel_provider_and_failed_generation_invalidate(self):
        with TemporaryDirectory() as folder:
            app, workflow, _, _, args, body = selection_fixture(folder)
            for mutation in (lambda: workflow.select_input(body), workflow.cancel,
                             workflow.provider_settings_changed):
                workflow.select_input(body)
                workflow.adopt_derived_review(*args)
                mutation()
                self.assertIsNone(app.derived_review)
                self.assertFalse(workflow.snapshot()["build_allowed"])
            workflow.select_input(body)
            workflow.adopt_derived_review(*args)
            with self.assertRaisesRegex(RuntimeError, "offline generation failure"):
                asyncio.run(app.generate())
            self.assertIsNone(app.derived_review)
            self.assertFalse(workflow.snapshot()["build_allowed"])
            with self.assertRaises(BrokerError): workflow.assert_run_not_site_draft()
            self.assertTrue(app.diagnostics.flush()) # Drain owned writer before Windows temp cleanup.

    def test_same_input_reselection_during_save_cannot_activate(self):
        with TemporaryDirectory() as folder:
            app, workflow, _, source, args, _ = selection_fixture(folder)
            save = app._derived_store.save
            def changing_save(record):
                save(record)
                app.select_input(PreparedInput(source.input_revision, (), ()))
            with patch.object(app._derived_store, "save", side_effect=changing_save):
                with self.assertRaises(BrokerError): workflow.adopt_derived_review(*args)
            self.assertIsNone(app.derived_review)
            self.assertFalse(workflow.snapshot()["build_allowed"])
            # Retained file is evidence, not automatic selection authority.
            self.assertIsNotNone(app._derived_store.load())

    def test_workspace_edit_during_save_cannot_activate(self):
        with TemporaryDirectory() as folder:
            app, workflow, _, _, args, _ = selection_fixture(folder)
            save = app._derived_store.save
            def changing_save(record):
                save(record)
                app.scan_review.import_archive(args[2], record.archive_text)
            with patch.object(app._derived_store, "save", side_effect=changing_save):
                with self.assertRaises(BrokerError): workflow.adopt_derived_review(*args)
            self.assertIsNone(app.derived_review)
            self.assertFalse(workflow.snapshot()["build_allowed"])

    def test_corrupt_saved_review_never_changes_original(self):
        with TemporaryDirectory() as folder:
            app, workflow, _, _, args, _ = selection_fixture(folder)
            workflow.adopt_derived_review(*args)
            before = app._project_store.path.read_bytes()
            app._derived_store.path.write_text('{"invalid": true}', encoding="utf-8")
            with self.assertRaises(BrokerError): workflow.adopt_derived_review(args[0], args[1], None, restore=True)
            self.assertIsNone(app.derived_review)
            self.assertEqual(app._project_store.path.read_bytes(), before)
            self.assertFalse(workflow.snapshot()["build_allowed"])


if __name__ == "__main__": unittest.main()
