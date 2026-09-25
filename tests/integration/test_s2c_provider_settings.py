from __future__ import annotations

import json
from pathlib import Path
import sys
import types
from tempfile import TemporaryDirectory
from threading import Thread
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = Path(__import__("os").environ.get("TWINPULSE_TEST_TMP", ROOT / "artifacts" / "test-tmp"))
TEST_TMP.mkdir(parents=True, exist_ok=True)
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

# This suite exercises provider settings only. Keep it runnable in the minimal
# general-Python lane where the image decoder dependency is intentionally not
# imported or executed.
try:
    import PIL  # noqa: F401
except ImportError:
    pil_stub = types.ModuleType("PIL")
    pil_stub.Image = object()
    pil_stub.UnidentifiedImageError = ValueError
    sys.modules["PIL"] = pil_stub

from twinpulse_app import CommandBroker, JsonProviderSettingsStore, LocalApiServer, ProviderSettings
from twinpulse_app.command_broker import BrokerError


class _Credential:
    def __init__(
        self, secret: str | None = None, *, fail_save: bool = False, fail_status: bool = False,
    ) -> None:
        self.secret = secret
        self.fail_save = fail_save
        self.fail_status = fail_status

    @property
    def target_name(self) -> str:
        return "TwinPulse/OpenAIResponsesAPI"

    def save(self, secret: str) -> None:
        if self.fail_save:
            raise OSError("credential backend unavailable")
        self.secret = secret.strip()

    def load(self) -> str | None:
        return self.secret

    def is_configured(self) -> bool:
        if self.fail_status:
            raise OSError("credential status unavailable")
        return bool(self.secret)

    def delete(self) -> None:
        self.secret = None


class _FailingSettingsStore(JsonProviderSettingsStore):
    def save(self, value: ProviderSettings) -> None:
        raise OSError("settings disk unavailable")


class _WorkflowStatus:
    def __init__(self, mode: str, connected: bool) -> None:
        self.mode = mode
        self.connected = connected

    def snapshot(self) -> dict[str, object]:
        return {"mode": self.mode, "provider": {"connected": self.connected}}


class S2cProviderSettingsTests(unittest.TestCase):
    def make_server(
        self, store: JsonProviderSettingsStore, credential: _Credential,
        workflow: _WorkflowStatus | None = None,
    ) -> LocalApiServer:
        return LocalApiServer(
            CommandBroker(),
            product_bootstrap_secret="p" * 40,
            engine_bootstrap_secret="e" * 40,
            provider_settings_store=store,
            credential_store=credential,
            product_workflow=workflow,  # type: ignore[arg-type]
        )

    @staticmethod
    def body(
        *, base_url: str = "https://api.openai.com/v1/", api_key: str = "",
        reapprove: bool = False,
    ) -> dict[str, object]:
        return {
            "base_url": base_url,
            "model_id": "gpt-test",
            "reasoning_effort": "low",
            "api_key": api_key,
            "credential_reapproval": reapprove,
        }

    def test_v2_profile_and_openai_only_legacy_migration(self) -> None:
        current = ProviderSettings().to_dict()
        self.assertEqual(current["schema_version"], "3.0")
        self.assertEqual(current["adapter_kind"], "openai_responses")
        self.assertEqual(current["credential_ref"], "TwinPulse/OpenAIResponsesAPI")
        migrated = ProviderSettings.from_dict({
            "schema_version": "1.0", "base_url": "https://api.openai.com/v1/",
            "model_id": "gpt-old", "reasoning_effort": "medium",
        })
        self.assertEqual(migrated.provider_profile, "openai")
        with self.assertRaisesRegex(ValueError, "explicit profile migration"):
            ProviderSettings.from_dict({
                "schema_version": "1.0", "base_url": "https://custom.example/v1/",
                "model_id": "custom", "reasoning_effort": "low",
            })
        with self.assertRaisesRegex(ValueError, "endpoint path"):
            ProviderSettings(endpoint_path="https://redirect.example/responses").validated()

    def test_concurrent_saves_are_atomic_and_leave_no_shared_tmp(self) -> None:
        with TemporaryDirectory(prefix="s2c-", dir=TEST_TMP) as directory:
            path = Path(directory) / "provider.json"
            stores = [JsonProviderSettingsStore(path) for _ in range(4)]
            workers = [
                Thread(target=store.save, args=(ProviderSettings(model_id=f"model-{index}"),))
                for index, store in enumerate(stores)
            ]
            for worker in workers:
                worker.daemon = True
                worker.start()
            for worker in workers:
                worker.join(timeout=10.0)
            self.assertFalse(any(worker.is_alive() for worker in workers), "atomic settings save deadlocked")
            result = JsonProviderSettingsStore(path).load()
            self.assertTrue(result.model_id.startswith("model-"))
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_origin_change_requires_new_key_or_explicit_reapproval(self) -> None:
        with TemporaryDirectory(prefix="s2c-", dir=TEST_TMP) as directory:
            store = JsonProviderSettingsStore(Path(directory) / "provider.json")
            store.save(ProviderSettings())
            credential = _Credential("existing-secret")
            server = self.make_server(store, credential)
            try:
                with self.assertRaises(BrokerError) as caught:
                    server._save_provider_settings(self.body(base_url="https://gateway.example/v1/"))
                self.assertEqual(caught.exception.code, "credential_rebind_required")
                saved = server._save_provider_settings(self.body(
                    base_url="https://gateway.example/v1/", reapprove=True,
                ))
                self.assertEqual(saved["base_url"], "https://gateway.example/v1/")
                self.assertTrue(saved["credential_configured"])
            finally:
                server._httpd.server_close()

    def test_credential_failure_does_not_change_settings(self) -> None:
        with TemporaryDirectory(prefix="s2c-", dir=TEST_TMP) as directory:
            store = JsonProviderSettingsStore(Path(directory) / "provider.json")
            store.save(ProviderSettings(model_id="before"))
            server = self.make_server(store, _Credential("old", fail_save=True))
            try:
                with self.assertRaises(BrokerError) as caught:
                    server._save_provider_settings(self.body(api_key="secret-canary"))
                self.assertEqual(caught.exception.code, "credential_save_failed")
                self.assertEqual(store.load().model_id, "before")
                self.assertNotIn("secret-canary", str(caught.exception))
            finally:
                server._httpd.server_close()
            status_server = self.make_server(store, _Credential("old", fail_status=True))
            try:
                with self.assertRaises(BrokerError) as caught:
                    status_server._provider_settings()
                self.assertEqual(caught.exception.code, "credential_status_failed")
            finally:
                status_server._httpd.server_close()

    def test_settings_failure_rolls_back_secret_and_never_serializes_canary(self) -> None:
        with TemporaryDirectory(prefix="s2c-", dir=TEST_TMP) as directory:
            path = Path(directory) / "provider.json"
            good = JsonProviderSettingsStore(path)
            good.save(ProviderSettings(model_id="before"))
            store = _FailingSettingsStore(path)
            credential = _Credential("old-secret")
            server = self.make_server(store, credential)
            canary = "S2C-SECRET-CANARY-never-leak"
            try:
                with self.assertRaises(BrokerError) as caught:
                    server._save_provider_settings(self.body(api_key=canary))
                self.assertEqual(caught.exception.code, "provider_settings_save_failed")
                self.assertEqual(credential.secret, "old-secret")
                self.assertEqual(good.load().model_id, "before")
                self.assertNotIn(canary, path.read_text(encoding="utf-8"))
                self.assertNotIn(canary, str(caught.exception))
            finally:
                server._httpd.server_close()

    def test_corrupt_json_is_preserved_and_reported_structurally(self) -> None:
        with TemporaryDirectory(prefix="s2c-", dir=TEST_TMP) as directory:
            path = Path(directory) / "provider.json"
            original = b'{"schema_version":"2.0","truncated":'
            path.write_bytes(original)
            server = self.make_server(JsonProviderSettingsStore(path), _Credential())
            try:
                with self.assertRaises(BrokerError) as caught:
                    server._provider_settings()
                self.assertEqual(caught.exception.code, "provider_settings_corrupt")
                self.assertEqual(path.read_bytes(), original)
            finally:
                server._httpd.server_close()

    def test_status_separates_saved_capability_key_and_live_success(self) -> None:
        with TemporaryDirectory(prefix="s2c-", dir=TEST_TMP) as directory:
            store = JsonProviderSettingsStore(Path(directory) / "provider.json")
            server = self.make_server(store, _Credential())
            try:
                state = server._provider_settings()
                self.assertFalse(state["settings_saved"])
                self.assertTrue(state["capability_checked"])
                self.assertFalse(state["credential_configured"])
                self.assertFalse(state["live_request_succeeded"])
                self.assertNotIn("api_key", json.dumps(state))
            finally:
                server._httpd.server_close()
            fixture_server = self.make_server(store, _Credential("saved"), _WorkflowStatus("explicit_fixture", True))
            live_server = self.make_server(store, _Credential("saved"), _WorkflowStatus("live_provider", True))
            try:
                self.assertFalse(fixture_server._provider_settings()["live_request_succeeded"])
                self.assertTrue(live_server._provider_settings()["live_request_succeeded"])
            finally:
                fixture_server._httpd.server_close()
                live_server._httpd.server_close()


if __name__ == "__main__":
    unittest.main()
