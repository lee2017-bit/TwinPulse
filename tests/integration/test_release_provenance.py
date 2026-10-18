# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline release-provenance regressions; no devices/providers/installations."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import audit_release_provenance as audit


class ReleaseProvenanceTests(unittest.TestCase):
    def fixture(self, root):
        release = root / "release"
        release.mkdir()
        for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "docs/LICENSING.md",
                     "apps/twinpulse-web/dist/THIRD_PARTY_LICENSES.txt", "artifacts/robot-models/turtlebot3-source/LICENSE"):
            for folder in (root, release):
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"original notice\n")
        wheel = release / "wheelhouse/pillow.whl"
        wheel.parent.mkdir()
        wheel.write_bytes(b"not executed wheel fixture")
        inventory = {"python": {"wheel_sha256": audit.digest(wheel.read_bytes())}}
        return release, inventory

    def manifest(self, release):
        rows = [{"path": p.relative_to(release).as_posix(), "sha256": audit.digest(p.read_bytes()), "bytes": p.stat().st_size}
                for p in audit.plain_files(release) if p.name != "release-manifest.json"]
        (release / "release-manifest.json").write_text(json.dumps({"files": rows}))
        return rows

    def test_own_code_is_only_a_candidate_not_public_approval(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            release, inventory = self.fixture(root)
            with patch.object(audit, "ROOT", root):
                result = audit.audit_release(release, inventory)
            self.assertFalse(result["public_ready"])
            self.assertEqual(result["human_content_review"], "REQUIRED")
            self.assertEqual(result["findings"], [])

    def test_private_inputs_credentials_and_runtime_are_denied_by_path(self):
        for name in ("outputs/report.json", "fixtures/photo.jpg", ".env.local", "nested/id_ed25519",
                     "scripts/secret.pem", "isaacsim/LICENSE.txt", "packages/node_modules/lib.js"):
            self.assertEqual(audit.classify(name), "EXCLUDED_PRIVATE_OR_RUNTIME", name)
        self.assertEqual(audit.classify("newphoto.jpg"), "UNCLASSIFIED_CONTENT_REVIEW")

    def test_private_key_is_not_read_or_echoed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            release, inventory = self.fixture(root)
            key = release / "id_rsa"
            key.write_bytes(b"never read")
            original = Path.read_bytes
            def read_bytes(path):
                if path == key:
                    raise AssertionError("excluded credential was read")
                return original(path)
            with patch.object(audit, "ROOT", root), patch.object(Path, "read_bytes", read_bytes):
                result = audit.audit_release(release, inventory)
            self.assertIn({"path": "id_rsa", "reason": "EXCLUDED_PRIVATE_OR_RUNTIME"}, result["findings"])
            self.assertNotIn("never read", json.dumps(result))

    def test_converted_asset_and_embedded_personal_path_are_not_auto_cleared(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            release, inventory = self.fixture(root)
            asset = release / "artifacts/robot-models/burger-isaac/usd/test.usda"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b'#usda 1.0\n# C:\\Users\\private-person\\Temp\\conversion.usd\n')
            with patch.object(audit, "ROOT", root):
                result = audit.audit_release(release, inventory)
            reasons = result["finding_counts"]
            self.assertIn("CONVERTED_ASSET_RIGHTS_AND_PATH_REVIEW", reasons)
            self.assertIn("PERSONAL_ABSOLUTE_PATH_REVIEW", reasons)
            self.assertNotIn("private-person", json.dumps(result))

    def test_unknown_assets_are_not_inherited_apache(self):
        self.assertEqual(audit.classify("artifacts/new/model.usd"), "UNCLASSIFIED_CONTENT_REVIEW")
        self.assertEqual(audit.classify("apps/twinpulse-web/dist/assets/private-photo.png"), "UNCLASSIFIED_CONTENT_REVIEW")
        self.assertEqual(audit.classify("tests/fixtures/generic_room_layout.py"), "OWNED_CODE_CANDIDATE")
        self.assertEqual(audit.classify("tests/fixtures/private-photo.jpg"), "EXCLUDED_PRIVATE_OR_RUNTIME")

    def test_content_findings_never_include_matched_value(self):
        secret = b"sk-" + b"X" * 40
        result = audit.content_findings("scripts/example.py", secret)
        self.assertEqual(result, ["POTENTIAL_CREDENTIAL_MATERIAL"])
        self.assertNotIn(secret.decode(), json.dumps(result))

    def test_notice_drift_is_reported(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            release, inventory = self.fixture(root)
            (release / "NOTICE").write_bytes(b"different")
            with patch.object(audit, "ROOT", root):
                result = audit.audit_release(release, inventory)
            self.assertIn({"path": "NOTICE", "reason": "REQUIRED_NOTICE_DRIFT"}, result["findings"])

    def test_manifest_tampering_and_extra_files_are_rejected(self):
        for tamper in ("changed", "extra"):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                release, inventory = self.fixture(root)
                self.manifest(release)
                (release / ("LICENSE" if tamper == "changed" else "extra.txt")).write_bytes(b"changed")
                with patch.object(audit, "ROOT", root), self.assertRaisesRegex(ValueError, "MANIFEST_HASH_MISMATCH|UNMANIFESTED_RELEASE_FILE"):
                    audit.audit_release(release, inventory)

    def test_manifest_duplicate_and_traversal_are_rejected(self):
        for unsafe in ("../outside.py", "C:/outside.py", "\\outside.py", "LICENSE"):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                release, inventory = self.fixture(root)
                rows = self.manifest(release)
                rows.append({"path": unsafe, "sha256": "0" * 64, "bytes": 0})
                (release / "release-manifest.json").write_text(json.dumps({"files": rows}))
                with patch.object(audit, "ROOT", root), self.assertRaisesRegex(ValueError, "MANIFEST_UNSAFE_OR_DUPLICATE_PATH"):
                    audit.audit_release(release, inventory)

    def test_node_lock_drift_fails_without_fetching_dependencies(self):
        with TemporaryDirectory() as directory:
            web = Path(directory)
            (web / "node_modules/.pnpm").mkdir(parents=True)
            (web / "pnpm-lock.yaml").write_text("frozen")
            (web / "node_modules/.pnpm/lock.yaml").write_text("different")
            with self.assertRaisesRegex(ValueError, "INSTALLED_LOCK_DRIFT"):
                audit.node_inventory(web)

    def test_pnpm_parser_does_not_count_peer_dependency_fields_as_packages(self):
        lock = b"lockfileVersion: '9.0'\r\n\r\npackages:\r\n\r\n  react@19.3.0:\r\n    peerDependencies:\r\n      typescript:\r\n        optional: true\r\n  '@types/react@19.3.0': {}\r\n\r\nsnapshots:\r\n  invented@1.0.0: {}\r\n"
        self.assertEqual(set(audit.locked_node_packages(lock)), {("react", "19.3.0"), ("@types/react", "19.3.0")})

    def test_wheel_hash_notice_and_non_extra_dependency_are_verified(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, lock = root / "pillow.whl", root / "requirements.lock"
            def make(requirement):
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr("pillow-12.3.0.dist-info/METADATA", "Name: pillow\nVersion: 12.3.0\nLicense-Expression: MIT-CMU\n" + requirement)
                    archive.writestr("pillow-12.3.0.dist-info/licenses/LICENSE", "original bundled notices")
                lock.write_text("Pillow==12.3.0 --hash=sha256:" + audit.digest(wheel.read_bytes()) + "\n")
            make('Requires-Dist: docs-only; extra == "docs"\n')
            result = audit.wheel_inventory(wheel, lock)
            self.assertEqual(len(result["original_notices"]), 1)
            wheel.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "PYTHON_WHEEL_LOCK_MISMATCH"):
                audit.wheel_inventory(wheel, lock)
            make("Requires-Dist: uninventoried-runtime\n")
            with self.assertRaisesRegex(ValueError, "UNINVENTORIED_PYTHON_RUNTIME_DEPENDENCY"):
                audit.wheel_inventory(wheel, lock)

    def test_existing_builder_gate_is_before_success_and_keeps_local_mode(self):
        builder = (audit.ROOT / "scripts/build_offline_release.ps1").read_text()
        self.assertIn("[switch]$RequirePublicReview", builder)
        self.assertLess(builder.index("scripts\\audit_release_provenance.py"), builder.index("TWINPULSE_OFFLINE_RELEASE=PASS"))
        self.assertIn('throw "Public release requires', builder)


if __name__ == "__main__":
    unittest.main()
