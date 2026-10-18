# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned loopback App rehearsal, synthetic fixture, no engine or devices."""
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
from tests.integration.test_derived_review_selection import selection_fixture
from twinpulse_app import LocalApiServer, JsonProviderSettingsStore
from rehearse_offline_app import NoCredentials, native_source_hashes


def hashes():
    result = native_source_hashes()
    for name in ("packages/twinpulse_app/src/twinpulse_app/derived_site_review.py",
                 "tests/integration/test_derived_review_selection.py", "tests/integration/test_derived_site_review.py",
                 "apps/twinpulse-web/src/DerivedReview.tsx", "apps/twinpulse-web/e2e/derived-review-real.mjs",
                 "scripts/rehearse_derived_review.py"):
        result[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    node = shutil.which("node")
    chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))/"Google/Chrome/Application/chrome.exe"
    if not node or not chrome.is_file(): parser.error("Existing Node/Chrome required; no installs")
    output.mkdir(parents=True, exist_ok=False)
    app, workflow, broker, source, _, _ = selection_fixture(output / "isolated-state")
    archive = app.scan_review.download_archive(app.scan_review.snapshot()["workspace_revision"])["archive_text"]
    (output/"synthetic-archive.json").write_text(archive, encoding="utf-8")
    before = app._project_store.path.read_bytes()
    baseline = hashes()
    secret = secrets.token_urlsafe(32)
    server = LocalApiServer(broker, product_bootstrap_secret=secret, engine_bootstrap_secret=secrets.token_urlsafe(32),
        product_workflow=workflow, static_root=ROOT/"apps/twinpulse-web/dist",
        provider_settings_store=JsonProviderSettingsStore(output/"isolated-state/settings.json"),
        credential_store=NoCredentials())
    result = dict(status="FAIL", data="synthetic", robot="NOT_RUN", isaac="NOT_RUN", provider_calls=0)
    try:
        server.start()
        env = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url, TWINPULSE_REHEARSAL_BOOTSTRAP=secret,
            TWINPULSE_REHEARSAL_OUTPUT=str(output), TWINPULSE_REHEARSAL_CHROME=str(chrome))
        child = subprocess.run([node, str(ROOT/"apps/twinpulse-web/e2e/derived-review-real.mjs")],
            cwd=ROOT/"apps/twinpulse-web", env=env, capture_output=True, timeout=100,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        browser = json.loads((output/"browser-result.json").read_text())
        if child.returncode or browser["status"] != "PASS": raise RuntimeError("Browser stages failed")
        if app.site_draft != source or app._project_store.path.read_bytes() != before:
            raise RuntimeError("Original project changed")
        if hashes() != baseline: raise RuntimeError("Code changed during rehearsal")
        result.update(status="PASS", stages=browser["stages"], source_and_build_sha256=baseline,
            original_project_changed=False, derived_sidecar_exists=app._derived_store.path.is_file())
    except Exception as error:
        result["error_type"] = type(error).__name__
    finally:
        server.stop()
        (output/"result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("DERIVED_APP_REHEARSAL=" + result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__": raise SystemExit(main())
