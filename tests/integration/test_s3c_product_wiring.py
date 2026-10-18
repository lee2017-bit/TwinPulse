# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
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

from twinpulse_app import (  # noqa: E402
    CommandBroker,
    JsonProviderSettingsStore,
    LocalApiServer,
    ProviderSettings,
    build_live_generation_service,
    provider_settings_preset,
)
from twinpulse_app.command_broker import BrokerError  # noqa: E402
from twinpulse_app.settings import (  # noqa: E402
    NEBIUS_ADAPTER_KIND,
    NEBIUS_BASE_URL,
    NEBIUS_FALLBACK_OBSERVER_MODEL_ID,
    NEBIUS_OBSERVER_MODEL_ID,
    NEBIUS_PLANNER_MODEL_ID,
    NEBIUS_PROVIDER_PROFILE,
)
from twinpulse_provider import NebiusChatCompletionsPipelineProvider, OpenAIResponsesProvider  # noqa: E402


class _Credential:
    target_name = "TwinPulse/OpenAIResponsesAPI"

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret

    def save(self, secret: str) -> None:
        self.secret = secret.strip()

    def load(self) -> str | None:
        return self.secret

    def is_configured(self) -> bool:
        return bool(self.secret)

    def delete(self) -> None:
        self.secret = None


class S3cProductWiringTests(unittest.TestCase):
    def test_v2_settings_migrate_without_changing_openai_binding(self) -> None:
        legacy = ProviderSettings().to_dict()
        legacy["schema_version"] = "2.0"
        legacy.pop("observer_model_id")
        legacy.pop("fallback_observer_model_id")
        value = ProviderSettings.from_dict(legacy)
        self.assertEqual(value.adapter_kind, "openai_responses")
        self.assertEqual(value.observer_model_id, "")
        self.assertEqual(value.to_dict()["schema_version"], "3.0")

    def test_reviewed_nebius_preset_is_exact_and_locked(self) -> None:
        value = provider_settings_preset(NEBIUS_PROVIDER_PROFILE)
        self.assertEqual(value.base_url, NEBIUS_BASE_URL)
        self.assertEqual(value.adapter_kind, NEBIUS_ADAPTER_KIND)
        self.assertEqual(value.endpoint_path, "chat/completions")
        self.assertEqual(value.model_id, NEBIUS_PLANNER_MODEL_ID)
        self.assertEqual(value.observer_model_id, NEBIUS_OBSERVER_MODEL_ID)
        self.assertEqual(value.fallback_observer_model_id, NEBIUS_FALLBACK_OBSERVER_MODEL_ID)
        with self.assertRaisesRegex(ValueError, "reviewed S3a"):
            replace(value, model_id="substitute").validated()

    def test_composition_selects_adapter_without_network_or_key_read(self) -> None:
        reads = 0

        def key_getter() -> str | None:
            nonlocal reads
            reads += 1
            return "unused"

        openai = build_live_generation_service(ProviderSettings(), key_getter)
        nebius = build_live_generation_service(provider_settings_preset(NEBIUS_PROVIDER_PROFILE), key_getter)
        self.assertIsInstance(openai._provider, OpenAIResponsesProvider)  # noqa: SLF001
        self.assertIsInstance(nebius._provider, NebiusChatCompletionsPipelineProvider)  # noqa: SLF001
        self.assertEqual(nebius._config.endpoint_path, "chat/completions")  # noqa: SLF001
        self.assertEqual(nebius._config.max_attempts, 1)  # noqa: SLF001
        self.assertEqual(reads, 0)

    def test_site_v2_profile_is_explicit_and_keeps_legacy_profile(self) -> None:
        site = provider_settings_preset("nebius_site_v2")
        self.assertEqual(site.provider_profile, "nebius_site_v2")
        self.assertEqual(site.base_url, NEBIUS_BASE_URL)
        legacy = build_live_generation_service(provider_settings_preset(NEBIUS_PROVIDER_PROFILE), lambda: None)
        selected = build_live_generation_service(site, lambda: None)
        self.assertEqual(legacy._plan_version, "1.0")  # noqa: SLF001
        self.assertEqual(selected._plan_version, "2.2")  # noqa: SLF001
        self.assertEqual(selected._provider.site_plan_version, "2.2")  # noqa: SLF001

    def test_api_switch_requires_new_key_and_reports_unverified_capability(self) -> None:
        with TemporaryDirectory(prefix="s3c-", dir=TEST_TMP) as directory:
            path = Path(directory) / "provider.json"
            store = JsonProviderSettingsStore(path)
            store.save(ProviderSettings())
            credential = _Credential("old-openai-key")
            server = LocalApiServer(
                CommandBroker(), product_bootstrap_secret="p" * 40, engine_bootstrap_secret="e" * 40,
                provider_settings_store=store, credential_store=credential,
            )
            body = {
                "base_url": NEBIUS_BASE_URL,
                "model_id": NEBIUS_PLANNER_MODEL_ID,
                "reasoning_effort": "low",
                "api_key": "",
                "credential_reapproval": True,
                "provider_profile": NEBIUS_PROVIDER_PROFILE,
            }
            try:
                with self.assertRaises(BrokerError) as caught:
                    server._save_provider_settings(body)
                self.assertEqual(caught.exception.code, "credential_rebind_required")
                body["api_key"] = "S3C-SECRET-CANARY"
                state = server._save_provider_settings(body)
                self.assertEqual(state["schema_version"], "3.0")
                self.assertEqual(state["observer_model_id"], NEBIUS_OBSERVER_MODEL_ID)
                self.assertFalse(state["capability_checked"])
                self.assertFalse(state["live_request_succeeded"])
                self.assertNotIn("S3C-SECRET-CANARY", json.dumps(state))
                self.assertNotIn("S3C-SECRET-CANARY", path.read_text(encoding="utf-8"))
            finally:
                server._httpd.server_close()


if __name__ == "__main__":
    unittest.main()
