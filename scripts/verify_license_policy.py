# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline legal-file, metadata, reversible-header and existing-package checks.

No installations, API calls, device imports, deployment or publishing. CFF is
stored in JSON (a YAML 1.2 subset). The optional frozen official schema is checked
for the schema keywords reached by this document, not via a new dependency.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/lee2017-bit/TwinPulse"
OFFICIAL_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
COPIES = ("", "packages/twinpulse_app", "packages/twinpulse_provider",
          "packages/twinpulse_robot_safety", "extensions/twinpulse.extension",
          "apps/twinpulse-web", "apps/twinpulse-web/public")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_cff_subset(value, schema, document):
    """Check all reached validation keywords; fail rather than ignore new ones."""
    if "$ref" in schema:
        reference = schema["$ref"]
        require(reference.startswith("#/"), "CFF_EXTERNAL_REF")
        target = document
        for part in reference[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        validate_cff_subset(value, target, document)
        return
    allowed = {"$id", "$schema", "$comment", "definitions", "description", "title", "default", "examples",
               "type", "enum", "pattern", "minLength", "format", "required", "properties",
               "additionalProperties", "items", "minItems", "uniqueItems", "anyOf", "oneOf"}
    require(not set(schema) - allowed, "CFF_UNSUPPORTED_SCHEMA_KEYWORD:" + str(set(schema) - allowed))
    for keyword in ("anyOf", "oneOf"):
        if keyword in schema:
            successes = 0
            for choice in schema[keyword]:
                try:
                    validate_cff_subset(value, choice, document)
                except ValueError:
                    continue
                successes += 1
            require(successes == 1 if keyword == "oneOf" else successes >= 1, "CFF_" + keyword)
    if "type" in schema:
        classes = {"object": dict, "array": list, "string": str}
        require(schema["type"] in classes and isinstance(value, classes[schema["type"]]), "CFF_TYPE")
    if "enum" in schema:
        require(value in schema["enum"], "CFF_ENUM")
    if "pattern" in schema:
        require(isinstance(value, str) and re.search(schema["pattern"], value) is not None, "CFF_PATTERN")
    if "minLength" in schema:
        require(isinstance(value, str) and len(value) >= schema["minLength"], "CFF_LENGTH")
    if "format" in schema:
        require(schema["format"] == "uri" and bool(re.match(r"https?://[^/\s]+(?:/\S*)?$", value)), "CFF_URI")
    if isinstance(value, dict):
        require(set(schema.get("required", [])) <= set(value), "CFF_REQUIRED")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            require(set(value) <= set(properties), "CFF_EXTRA_PROPERTY")
        for name, member in value.items():
            if name in properties:
                validate_cff_subset(member, properties[name], document)
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), "CFF_MIN_ITEMS")
        if schema.get("uniqueItems"):
            require(len({json.dumps(item, sort_keys=True) for item in value}) == len(value), "CFF_DUPLICATE")
        if "items" in schema:
            for item in value:
                validate_cff_subset(item, schema["items"], document)


def check_files(header_report=None, cff_schema=None):
    license_data = (ROOT / "LICENSE").read_bytes()
    notice_data = (ROOT / "NOTICE").read_bytes()
    require(sha(license_data) == OFFICIAL_SHA256, "OFFICIAL_LICENSE_BYTES_CHANGED")
    for relative in COPIES:
        for name, expected in (("LICENSE", license_data), ("NOTICE", notice_data)):
            require((ROOT / relative / name).read_bytes() == expected, "LEGAL_COPY_MISMATCH:" + relative + "/" + name)
    notice = notice_data.decode("utf-8")
    require("Copyright 2026 Jaewon Lee / 이재원" in notice and ORIGIN in notice, "NOTICE_PROVENANCE")
    cff = json.loads((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    require(cff["cff-version"] == "1.2.0" and cff["title"] == "TwinPulse", "CFF_IDENTITY")
    require(cff["authors"] == [{"family-names": "Lee", "given-names": "Jaewon"}], "CFF_AUTHOR")
    require(cff["repository-code"] == ORIGIN and cff["url"] == ORIGIN and cff["license"] == "Apache-2.0", "CFF_PROVENANCE")
    require(not {"version", "date-released", "doi", "identifiers"}.intersection(cff), "CFF_UNVERIFIED_RELEASE")
    if cff_schema:
        schema = json.loads(cff_schema.read_text(encoding="utf-8"))
        validate_cff_subset(cff, schema, schema)
    for relative in ("pyproject.toml", "packages/twinpulse_app/pyproject.toml", "packages/twinpulse_provider/pyproject.toml"):
        meta = tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))
        require(meta["project"]["license"] == {"file": "LICENSE"}, "PYTHON_LICENSE:" + relative)
        require(meta["project"]["urls"]["Repository"] == ORIGIN, "PYTHON_REPOSITORY")
        require(meta["project"]["authors"] == [{"name": "Jaewon Lee / 이재원"}], "PYTHON_AUTHOR")
        require(meta["build-system"]["requires"] == ["setuptools>=68"], "BUILD_SYSTEM_CHANGED")
        require(meta["tool"]["setuptools"]["license-files"] == ["LICENSE", "NOTICE"], "PYTHON_LEGAL_FILES")
    web = json.loads((ROOT / "apps/twinpulse-web/package.json").read_text(encoding="utf-8"))
    require(web["private"] is True and web["license"] == "Apache-2.0" and web["repository"]["url"] == ORIGIN + ".git", "WEB_METADATA")
    kit = tomllib.loads((ROOT / "extensions/twinpulse.extension/config/extension.toml").read_text(encoding="utf-8"))["package"]
    require(kit["license"] == "Apache-2.0" and kit["repository"] == ORIGIN, "KIT_METADATA")
    browser_legal = (ROOT / "apps/twinpulse-web/THIRD_PARTY_LICENSES.txt").read_bytes()
    require((ROOT / "apps/twinpulse-web/public/THIRD_PARTY_LICENSES.txt").read_bytes() == browser_legal, "BROWSER_THIRD_PARTY_COPY_MISMATCH")
    node_root = ROOT / "apps/twinpulse-web/node_modules"
    if node_root.is_dir():
        for package in (node_root / "react", node_root / "react-dom", node_root / "vite",
                        node_root / "react-dom/node_modules/scheduler"):
            # pnpm's dependency symlink lives beside react-dom, not under it.
            if not package.is_dir() and package.name == "scheduler":
                package = (node_root / "react-dom").resolve().parent / "scheduler"
            meta = json.loads((package / "package.json").read_text(encoding="utf-8"))
            upstream_license_data = next(package.glob("LICENSE*")).read_bytes()
            require(upstream_license_data in browser_legal and (meta["name"] + " " + meta["version"]).encode() in browser_legal,
                    "UPSTREAM_BROWSER_LICENSE_CHANGED:" + meta["name"])
    from apply_license_headers import candidates, insert_header
    counts = Counter()
    for path in candidates():
        data = path.read_bytes()
        updated, reason = insert_header(path, data)
        require(updated == data, "MISSING_SOURCE_HEADER:" + path.relative_to(ROOT).as_posix())
        counts[path.suffix] += 1
        if path.suffix == ".py":
            compile(data, str(path), "exec", dont_inherit=True)
    changed = 0
    if header_report:
        reports = header_report if isinstance(header_report, (list, tuple)) else [header_report]
        inserted_rows = []
        for path in reports:
            original = json.loads(path.read_text(encoding="utf-8"))
            require(original["applied"] is True, "HEADERS_NOT_APPLIED")
            inserted_rows.extend(row for row in original["files"] if row["changed"])
        require(len({row["path"] for row in inserted_rows}) == len(inserted_rows), "DUPLICATE_HEADER_EVIDENCE")
        for row in inserted_rows:
            data = (ROOT / row["path"]).read_bytes()
            require(sha(data) == row["after_sha256"], "HEADER_REWRITE_CHANGED_LATER:" + row["path"])
            if row["changed"]:
                detail = row["detail"]
                offset, length = detail["offset"], detail["inserted_bytes"]
                require(data[offset:offset + length] == detail["inserted_text"].encode("ascii"), "HEADER_INSERTION_CHANGED")
                restored = data[:offset] + data[offset + length:]
                require(sha(restored) == row["before_sha256"], "NON_COMMENT_BYTES_CHANGED")
                if row["path"].endswith(".py"):
                    require(ast.dump(ast.parse(restored), include_attributes=False) == ast.dump(ast.parse(data), include_attributes=False), "PYTHON_AST_CHANGED")
                changed += 1
    return {"status": "PASS", "official_license_sha256": sha(license_data), "identical_license_notice_copy_pairs": len(COPIES),
            "cff": "CFF_1.2.0_POPULATED_FIELDS_OFFICIAL_SCHEMA_PASS" if cff_schema else "JSON_YAML12_SUBSET_PASS",
            "source_headers_by_suffix": dict(counts), "exact_reversible_insertions": changed,
            "runtime_workflow_acceptance": "NOT_RUN_NOT_CLAIMED"}


def build_python_packages(output):
    require(not output.exists(), "NEW_PACKAGE_OUTPUT_REQUIRED")
    output.mkdir(parents=True)
    builds = []
    for name, folder, relative_source in (("core", ROOT, "packages/twinpulse_core/src"),
                                          ("app", ROOT / "packages/twinpulse_app", "src"),
                                          ("provider", ROOT / "packages/twinpulse_provider", "src")):
        stage = output / name
        stage.mkdir()
        for file in ("pyproject.toml", "LICENSE", "NOTICE"):
            shutil.copyfile(folder / file, stage / file)
        shutil.copytree(folder / relative_source, stage / relative_source,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
        # Invoke the already installed, declared backend directly; no build
        # frontend installation or isolated dependency download is necessary.
        build_code = ("from setuptools.build_meta import build_sdist, build_wheel; "
                      "build_sdist('dist'); build_wheel('dist')")
        result = subprocess.run([sys.executable, "-c", build_code],
                                cwd=stage, capture_output=True, text=True, timeout=120,
                                env={**os.environ, "PIP_NO_INDEX": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        (stage / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        require(result.returncode == 0, "PACKAGE_BUILD_FAILED:" + name)
        for archive in sorted((stage / "dist").iterdir()):
            if archive.suffix == ".whl":
                with zipfile.ZipFile(archive) as handle:
                    members = {entry: handle.read(entry) for entry in handle.namelist() if not entry.endswith("/")}
                metadata = [data.decode("utf-8") for entry, data in members.items() if entry.endswith(".dist-info/METADATA")]
                require(len(metadata) == 1 and ORIGIN in metadata[0], "WHEEL_REPOSITORY_MISSING")
                require("License-File: LICENSE" in metadata[0] and "License-File: NOTICE" in metadata[0], "WHEEL_LICENSE_METADATA")
            else:
                require(archive.name.endswith(".tar.gz"), "UNEXPECTED_BUILD_FILE")
                with tarfile.open(archive) as handle:
                    members = {entry.name: handle.extractfile(entry).read() for entry in handle.getmembers() if entry.isfile()}
            for legal in ("LICENSE", "NOTICE"):
                payloads = [data for entry, data in members.items() if entry.split("/")[-1] == legal]
                require(bool(payloads) and all(data == (ROOT / legal).read_bytes() for data in payloads), "PACKAGE_LEGAL_MISSING:" + name + ":" + legal)
            builds.append({"package": name, "archive": str(archive.relative_to(ROOT)), "sha256": sha(archive.read_bytes()), "license_notice": "PASS"})
    return builds


def check_distributions(release, web):
    release, web = release.resolve(), web.resolve()
    require(release.resolve().is_relative_to(ROOT / "outputs/licensing-20261011"), "OWNED_RELEASE_REQUIRED")
    manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8-sig"))
    rows = {row["path"]: row for row in manifest["files"]}
    legal = ("LICENSE", "NOTICE", "CITATION.cff", "THIRD_PARTY_NOTICES.md", "docs/LICENSING.md",
             "extensions/twinpulse.extension/LICENSE", "extensions/twinpulse.extension/NOTICE",
             "packages/twinpulse_robot_safety/LICENSE", "packages/twinpulse_robot_safety/NOTICE",
             "apps/twinpulse-web/dist/LICENSE", "apps/twinpulse-web/dist/NOTICE",
             "apps/twinpulse-web/dist/THIRD_PARTY_LICENSES.txt",
             "artifacts/robot-models/turtlebot3-source/LICENSE", "artifacts/robot-models/burger-prepared/source.json")
    require(set(legal) <= set(rows), "OFFLINE_LEGAL_FILES_MISSING")
    for name, row in rows.items():
        path = (release / name).resolve()
        require(path.is_relative_to(release.resolve()), "RELEASE_MEMBER_PATH")
        data = path.read_bytes()
        require(sha(data) == row["sha256"] and len(data) == row["bytes"], "RELEASE_MEMBER_MISMATCH:" + name)
    for name in legal:
        source = ROOT / name
        if name.startswith("apps/twinpulse-web/dist/"):
            source = ROOT / name.split("/")[-1]
            if name.endswith("THIRD_PARTY_LICENSES.txt"):
                source = ROOT / "apps/twinpulse-web/THIRD_PARTY_LICENSES.txt"
        require((release / name).read_bytes() == source.read_bytes(), "RELEASE_LEGAL_MISMATCH:" + name)
    wheel = next((release / "wheelhouse").glob("pillow-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        upstream_pillow_notices = [name for name in archive.namelist() if "license" in name.lower() or "notice" in name.lower()]
    require(bool(upstream_pillow_notices), "PILLOW_UPSTREAM_NOTICES_MISSING")
    require(web.resolve().is_relative_to(ROOT / "outputs/licensing-20261011"), "OWNED_WEB_BUILD_REQUIRED")
    for name in ("LICENSE", "NOTICE"):
        require((web / name).read_bytes() == (ROOT / name).read_bytes(), "WEB_LEGAL_COPY_MISMATCH")
    require((web / "THIRD_PARTY_LICENSES.txt").read_bytes() == (ROOT / "apps/twinpulse-web/THIRD_PARTY_LICENSES.txt").read_bytes(),
            "WEB_UPSTREAM_LICENSE_MISSING")
    return {"status": "PASS", "offline_release": str(release.relative_to(ROOT)),
            "manifest_hashes_verified": len(rows), "legal_paths_verified": list(legal),
            "web_build_mode": manifest.get("web_build_mode"), "standalone_web_build": "PASS",
            "upstream_pillow_notice_paths": upstream_pillow_notices, "browser_upstream_notices": "PRESERVED_IN_SEPARATE_FILE",
            "public_release_or_runtime_acceptance": "NOT_RUN_NOT_CLAIMED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header-report", type=Path, action="append")
    parser.add_argument("--cff-schema", type=Path)
    parser.add_argument("--build-packages", action="store_true")
    parser.add_argument("--offline-release", type=Path)
    parser.add_argument("--web-build", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "outputs/licensing-20261011") and not output.exists(), "NEW_OWNED_OUTPUT_REQUIRED")
    report = check_files(args.header_report, args.cff_schema)
    if args.build_packages:
        report["python_archives"] = build_python_packages(output.parent / (output.stem + "-packages"))
    if args.offline_release:
        require(args.web_build is not None, "WEB_BUILD_REQUIRED")
        report["distributions"] = check_distributions(args.offline_release, args.web_build)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
