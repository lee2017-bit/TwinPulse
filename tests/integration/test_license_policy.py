# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""License-only regressions; no provider, device, Isaac or deployment activity."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from apply_license_headers import insert_header
from robot_source_identity import bundle_files
from verify_license_policy import OFFICIAL_SHA256, check_files, validate_cff_subset


class LicensePolicyTests(unittest.TestCase):
    def test_files_metadata_and_applied_headers(self):
        # Public checkout regressions must not depend on private/local evidence.
        result = check_files()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["official_license_sha256"], OFFICIAL_SHA256)
        self.assertEqual(result["identical_license_notice_copy_pairs"], 7)

    def test_python_shebang_encoding_and_syntax_preserved(self):
        original = b'#!/usr/bin/env python3\r\n# coding: utf-8\r\n"""Original docstring."""\r\nfrom __future__ import annotations\r\nx = 1\r\n'
        updated, detail = insert_header(Path("owned.py"), original)
        self.assertTrue(updated.startswith(b'#!/usr/bin/env python3\r\n# coding: utf-8\r\n# SPDX'))
        self.assertTrue(detail["python_ast_equal"])
        self.assertEqual(insert_header(Path("owned.py"), updated)[0], updated)

    def test_existing_third_party_notice_is_never_replaced(self):
        original = b'# Copyright 2020 Another Contributor\n# SPDX-License-Identifier: BSD-3-Clause\nvalue = 7\n'
        updated, reason = insert_header(Path("external.py"), original)
        self.assertEqual(updated, original)
        self.assertEqual(reason, "existing_notice_preserved")

    def test_spdx_inside_generated_string_is_not_a_file_header(self):
        original = b'rendered = """// SPDX-License-Identifier: MIT\n"""\n'
        updated, _ = insert_header(Path("generator.py"), original)
        self.assertTrue(updated.startswith(b'# SPDX-FileCopyrightText:'))
        self.assertIn(original, updated)

    def test_html_doctype_and_ts_reference_stay_first(self):
        for name, original in (("index.html", b'<!doctype html>\n<html></html>\n'),
                               ("vite-env.d.ts", b'/// <reference types="vite/client" />\n')):
            updated, _ = insert_header(Path(name), original)
            self.assertEqual(updated.splitlines()[0], original.splitlines()[0])

    def test_bom_and_crlf_are_not_reencoded(self):
        original = b'\xef\xbb\xbf@echo off\r\necho TwinPulse\r\n'
        updated, detail = insert_header(Path("Launch.cmd"), original)
        self.assertTrue(updated.startswith(b'\xef\xbb\xbf@echo off\r\nrem SPDX'))
        offset, length = detail["offset"], detail["inserted_bytes"]
        self.assertEqual(updated[:offset] + updated[offset + length:], original)

    def test_cff_rejects_unknown_fields_and_bad_spdx(self):
        cff = json.loads((ROOT / "CITATION.cff").read_text())
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {name: {} for name in cff}, "required": list(cff)}
        schema["properties"]["license"] = {"type": "string", "enum": ["Apache-2.0"]}
        for key, value in (("mandatory-screen-credit", True), ("license", "Imaginary-License")):
            invalid = copy.deepcopy(cff)
            invalid[key] = value
            with self.assertRaises(ValueError):
                validate_cff_subset(invalid, schema, schema)

    def test_robot_source_archive_includes_notices_and_inert_initializer(self):
        members = bundle_files(ROOT)
        for name in ("LICENSE", "NOTICE"):
            self.assertEqual(members[name], (ROOT / name).read_bytes())
        initializer = members["twinpulse_core/__init__.py"]
        self.assertIn(b'SPDX-License-Identifier: Apache-2.0', initializer)
        self.assertNotIn(b'import ', initializer)

    def test_existing_offline_builder_requires_legal_files(self):
        builder = (ROOT / "scripts/build_offline_release.ps1").read_text()
        self.assertIn('"LICENSE", "NOTICE", "CITATION.cff", "THIRD_PARTY_NOTICES.md"', builder)
        self.assertIn('artifacts\\robot-models\\turtlebot3-source\\LICENSE', builder)
        self.assertIn('Copy-Item -LiteralPath (Join-Path $repoRoot $name) -Destination $target', builder)


if __name__ == "__main__":
    unittest.main()
