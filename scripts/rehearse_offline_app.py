# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real local React/HTTP rehearsal with synthetic or saved native evidence.

Starts a fresh server on an OS-assigned loopback port. Credentials are ephemeral
and passed to the owned browser process only, never written to results or logs.
An existing application/project/runtime is never reused or stopped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for source in ("packages/twinpulse_core/src", "packages/twinpulse_app/src", "packages/twinpulse_provider/src"):
    sys.path.insert(0, str(ROOT / source))
from tests.integration.test_scan_review import route_bundle
from tests.integration.test_robot_reports import report
from twinpulse_app import ApplicationService, CommandBroker, JsonProviderSettingsStore, LocalApiServer, ProductWorkflow, ProjectStore
from twinpulse_core import InputArtifactStore
from twinpulse_provider import GenerationService, MockProvider, ProviderCapabilities, ProviderConfig


class NoCredentials:
    target_name = "offline-rehearsal-memory-only"

    def is_configured(self):
        return False

    def load(self):
        raise RuntimeError("Credential loading is not part of offline rehearsal")

    def save(self, _value):
        raise RuntimeError("Credential changes are not part of offline rehearsal")

    def delete(self):
        raise RuntimeError("Credential changes are not part of offline rehearsal")


def native_source_hashes():
    """Curated code/build bytes only; never read credentials or arbitrary metadata paths."""
    paths = [ROOT / relative for relative in (
        "packages/twinpulse_core/src/twinpulse_core/native_scan.py",
        "packages/twinpulse_core/src/twinpulse_core/native_scan_quality.py",
        "packages/twinpulse_core/src/twinpulse_core/native_scan_3d.py",
        "packages/twinpulse_core/src/twinpulse_core/native_registration.py",
        "packages/twinpulse_app/src/twinpulse_app/native_scan_review.py",
        "packages/twinpulse_app/src/twinpulse_app/scan_review.py",
        "packages/twinpulse_app/src/twinpulse_app/api.py",
        "packages/twinpulse_app/src/twinpulse_app/application.py",
        "packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py",
        "apps/twinpulse-web/src/NativeScanReview.tsx", "apps/twinpulse-web/src/App.tsx",
        "apps/twinpulse-web/src/ScanReview.tsx", "apps/twinpulse-web/e2e/offline-app-real.mjs",
        "apps/twinpulse-web/src/api.ts", "apps/twinpulse-web/src/styles.css",
        "scripts/rehearse_offline_app.py", "apps/twinpulse-web/e2e/native-scan-real.mjs",
        "apps/twinpulse-web/e2e/native-registration-real.mjs",
        "packages/twinpulse_core/tests/test_native_registration.py",
        "apps/twinpulse-web/dist/index.html")]
    assets = ROOT / "apps/twinpulse-web/dist/assets"
    paths += sorted(p for p in assets.iterdir() if p.suffix in (".css", ".js"))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="New result directory only")
    parser.add_argument("--native-bundle", type=Path, help="Use an actual saved native bundle, not the synthetic scratch rehearsal")
    parser.add_argument("--photo-dir", type=Path, help="Directory with the two original bound JPEG files")
    parser.add_argument("--registration-fixture", action="store_true", help="Run explicitly synthetic reference-fit browser checks")
    parser.add_argument("--archive-fixture", action="store_true", help="Add synthetic archive save/restore checks; no active project")
    args = parser.parse_args()
    if bool(args.native_bundle) != bool(args.photo_dir):
        parser.error("native-bundle and photo-dir are required together")
    if sum(bool(option) for option in (args.registration_fixture, args.native_bundle, args.archive_fixture)) > 1:
        parser.error("synthetic reference rehearsal must not be mixed with actual saved recording")
    output = args.output_dir.resolve()
    web = ROOT / "apps/twinpulse-web"
    node = shutil.which("node")
    chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    if not node or not chrome.is_file() or not (web / "dist/index.html").is_file():
        parser.error("Existing Node, Chrome and production web build required; nothing will be installed")
    output.mkdir(parents=True, exist_ok=False)
    if args.native_bundle:
        from twinpulse_core.native_scan import NativeScanBundle
        native = NativeScanBundle.from_text(args.native_bundle.read_text(encoding="utf-8"))
        value = native.to_dict()
        if value["source"]["kind"] != "saved_sensor_recording":
            parser.error("native rehearsal requires explicitly saved sensor evidence")
        for role, name in (("room", "room.jpg"), ("top_view", "top-view-window-up.jpg")):
            original = args.photo_dir / name
            matching = [p for p in value["photos"] if p["role"] == role]
            if len(matching) != 1 or hashlib.sha256(original.read_bytes()).hexdigest() != matching[0]["sha256"]:
                parser.error("original photo differs from bundle binding")
            shutil.copy2(original, output / name)
        fixtures = {"native-scan-bundle.json": value}
    elif args.registration_fixture:
        sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/tests'))
        from test_native_registration import registration_fixture
        native, reference = registration_fixture(-1)
        fixtures = {'native-scan-bundle.json': native.to_dict(), 'reference.json': reference}
    else:
        text, baseline, candidate, pairs = route_bundle()
        fixtures = {"bundle.json": json.loads(text), "baseline.json": baseline["points_xy_m"],
                    "candidate.json": candidate["points_xy_m"], "pairs.json": pairs,
                    "synthetic-health-report.json": report()}
    for name, value in fixtures.items():
        with (output / name).open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
    broker = CommandBroker()
    gateway = GenerationService(MockProvider(), ProviderConfig(
        base_url="https://fixture.invalid/v1/", endpoint_path="responses", model_id="unused-offline-fixture",
        api_key_env="TWINPULSE_UNUSED_FIXTURE_KEY", capabilities=ProviderCapabilities(True, True, 1, ("image/png",)),
        timeout_s=2., max_attempts=1))
    app = ApplicationService(gateway, project_store=ProjectStore(output / "isolated-state/project.json"),
                             artifact_store=InputArtifactStore(output / "isolated-state/inputs"))
    # Application startup creates an empty project record; review must not change it.
    project_before = (output / "isolated-state/project.json").read_bytes()
    workflow = ProductWorkflow(app, broker, mode="explicit_fixture",
                               generation_settings_getter=lambda: {
                                   "base_url": "https://fixture.invalid/v1/", "model_id": "unused-offline-fixture",
                                   "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0"},
                               provider_state_getter=lambda: {"configured": False, "label": "Offline rehearsal"})
    bootstrap = secrets.token_urlsafe(32)
    server = LocalApiServer(broker, product_bootstrap_secret=bootstrap, engine_bootstrap_secret=secrets.token_urlsafe(32),
                            product_workflow=workflow, static_root=web / "dist",
                            provider_settings_store=JsonProviderSettingsStore(output / "isolated-state/settings.json"),
                            credential_store=NoCredentials(), bootstrap_ttl_s=120.)
    summary = {"schema_version": "offline-app-rehearsal-1.0", "status": "FAIL", "data": "saved_sensor_recording" if args.native_bundle else "synthetic",
               "http": "actual_local_backend", "robot": "NOT_RUN", "isaac": "NOT_RUN", "provider_calls": "NOT_RUN"}
    source_hashes = native_source_hashes() if args.native_bundle or args.registration_fixture or args.archive_fixture else None
    try:
        server.start()
        env = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url, TWINPULSE_REHEARSAL_BOOTSTRAP=bootstrap,
                   TWINPULSE_REHEARSAL_OUTPUT=str(output), TWINPULSE_REHEARSAL_CHROME=str(chrome),
                   TWINPULSE_REHEARSAL_ARCHIVE="1" if args.archive_fixture else "0")
        entry = "native-scan-real.mjs" if args.native_bundle else "native-registration-real.mjs" if args.registration_fixture else "offline-app-real.mjs"
        child = subprocess.run([node, str(web / "e2e" / entry)], cwd=web, env=env,
                               capture_output=True, text=True, timeout=120.,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if child.returncode:
            # Browser error details may contain navigation URLs: do not persist them.
            raise RuntimeError("Browser rehearsal failed; inspect browser-result.json stage")
        result = json.loads((output / "browser-result.json").read_text(encoding="utf-8"))
        if result["status"] != "PASS" or app.site_draft is not None:
            raise RuntimeError("Offline rehearsal state validation failed")
        if (output / "isolated-state/project.json").read_bytes() != project_before:
            raise RuntimeError("Offline review unexpectedly changed the initialized project")
        if source_hashes is not None:
            if native_source_hashes() != source_hashes:
                raise RuntimeError("Native source/build changed while rehearsal was running")
            summary["source_and_build_sha256"] = source_hashes
        summary.update(status="PASS", active_project_changed=False, browser_stages=result["stages"])
    except Exception as exc:
        summary["error_type"] = type(exc).__name__
        print("Offline rehearsal FAIL; see the result stage. No robot or engine was started.")
    finally:
        server.stop()
        with (output / "result.json").open("x", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, allow_nan=False)
    print(f"OFFLINE_APP_REHEARSAL={summary['status']} result={output / 'result.json'}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
