# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline inventory and release-content gate, not legal/publication approval.

Reads manifests and original notices, never imports dependency/device code.
Reports only fingerprints and finding categories; never prints matched secrets.
Local packages can retain unresolved assets. --require-public fails closed and
does not silently remove files or make an incomplete demo look deployable.
"""
from __future__ import annotations

import argparse
from collections import Counter
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "twinpulse-release-provenance-1.0"
LEGAL_NAME = re.compile(r"^(?:licen[cs]e|copying|notice|copyright)(?:[._-].*)?$", re.I)
PRIVATE_PATH = re.compile(rb"(?:[A-Za-z]:[\\/]+Users[\\/]+[^\s\"<>]+|/home/[^\s\"<>]+)", re.I)
SECRET = re.compile(rb"(?:\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
FORBIDDEN_PARTS = {"outputs", "captures", "saved-projects", "projects", "datasets", "fixtures",
                   "node_modules", ".git", ".codex", ".aws", "__pycache__", "isaacsim"}
OWNED_ROOTS = ("packages/", "scripts/", "tests/", "extensions/twinpulse.extension/")
OWNED_TYPES = {".py", ".ps1", ".sh", ".cpp", ".hpp", ".txt", ".md", ".toml", ".patch", ".json"}
ROOT_DOCUMENTS = {"LICENSE", "NOTICE", "CITATION.cff", "THIRD_PARTY_NOTICES.md",
                  "docs/LICENSING.md", "docs/COMPANY_PC_INSTALL.md", "docs/QUICKSTART.md",
                  "docs/RELEASE_PROVENANCE.md", "Install-Offline.cmd", "Start-TwinPulse.cmd",
                  "config/python-runtime-requirements.lock", "provenance-audit.json"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def relative(path, root):
    resolved = path.resolve()
    require(resolved.is_relative_to(root.resolve()), "PATH_OUTSIDE_SCOPE")
    return resolved.relative_to(root.resolve()).as_posix()


def plain_files(root):
    """Do not traverse reparse points or silently ignore enumeration errors."""
    def failed(error):
        raise error
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        for name in dirs + files:
            item = Path(folder) / name
            require(not item.is_symlink() and not item.is_junction(), "REPARSE_POINT")
        dirs.sort()
        for name in sorted(files):
            yield Path(folder) / name


def notice_files(package):
    # Original notices nested in a package are included; dependency directories
    # are separate entries, not recursively attributed to the parent package.
    result = []
    def failed(error):
        raise error
    for folder, dirs, files in os.walk(package, followlinks=False, onerror=failed):
        dirs[:] = sorted(d for d in dirs if d not in {"node_modules", ".git"}
                         and not (Path(folder) / d).is_symlink() and not (Path(folder) / d).is_junction())
        for name in sorted(files):
            path = Path(folder) / name
            if LEGAL_NAME.match(name) and not path.is_symlink():
                data = path.read_bytes()
                result.append({"path": path.relative_to(package).as_posix(), "bytes": len(data), "sha256": digest(data)})
    return result


def node_resolve(name, parent, boundary):
    require(re.fullmatch(r"(?:@[\w.-]+/)?[\w.-]+", name), "NODE_PACKAGE_NAME")
    current = parent.resolve()
    while current.is_relative_to(boundary.resolve()):
        candidate = current / "node_modules" / name
        if (candidate / "package.json").is_file():
            resolved = candidate.resolve()
            require(resolved.is_relative_to(boundary.resolve()), "NODE_PACKAGE_OUTSIDE_INSTALL")
            return resolved
        current = current.parent
    return None


def locked_node_packages(lock_bytes):
    text = lock_bytes.decode("utf-8").replace("\r\n", "\n")
    require("lockfileVersion: '9.0'" in text and "\npackages:\n" in text, "UNSUPPORTED_PNPM_LOCK_FORMAT")
    section = text.split("\npackages:\n", 1)[1].split("\nsnapshots:\n", 1)[0]
    locked = {}
    for line in section.splitlines():
        match = re.fullmatch(r"  (?:'([^']+)'|(\S[^:]*)):\s*(?:\{\})?", line)
        if match:
            key = match.group(1) or match.group(2)
            name, _, version = key.rpartition("@")
            require(re.fullmatch(r"(?:@[\w.-]+/)?[\w.-]+", name) and re.fullmatch(r"[0-9][^\s:]*", version), "UNSUPPORTED_PNPM_PACKAGE_KEY")
            locked[(name, version)] = key
    require(bool(locked), "PNPM_PACKAGE_SECTION_EMPTY")
    return locked


def node_inventory(web):
    lock_bytes = (web / "pnpm-lock.yaml").read_bytes()
    installed_lock = web / "node_modules/.pnpm/lock.yaml"
    require(installed_lock.is_file() and installed_lock.read_bytes() == lock_bytes, "INSTALLED_LOCK_DRIFT")
    locked = locked_node_packages(lock_bytes)
    package_roots = set()
    store = web / "node_modules/.pnpm"
    # pnpm intentionally uses junctions inside node_modules. Resolve these only
    # within the install boundary; the release gate itself forbids junctions.
    for slot in store.iterdir():
        modules = slot / "node_modules"
        if not modules.is_dir():
            continue
        for entry in modules.iterdir():
            candidates = entry.iterdir() if entry.name.startswith("@") and entry.is_dir() else [entry]
            for candidate in candidates:
                if (candidate / "package.json").is_file():
                    resolved = candidate.resolve()
                    require(resolved.is_relative_to((web / "node_modules").resolve()), "NODE_PACKAGE_OUTSIDE_INSTALL")
                    package_roots.add(resolved)
    manifest = json.loads((web / "package.json").read_bytes())
    production, pending, graph = set(), [], []
    queue = [(web, name, False) for name in manifest["dependencies"]]
    while queue:
        parent, name, optional = queue.pop()
        target = node_resolve(name, parent, web)
        if target is None:
            pending.append({"name": name, "optional": optional, "status": "NOT_INSTALLED"})
            continue
        if target in production:
            continue
        production.add(target)
        meta = json.loads((target / "package.json").read_bytes())
        for dep in meta.get("dependencies", {}):
            queue.append((target, dep, dep in meta.get("optionalDependencies", {})))
            graph.append({"parent": meta["name"] + "@" + meta["version"], "dependency": dep})
        for dep in set(meta.get("optionalDependencies", {})) - set(meta.get("dependencies", {})):
            queue.append((target, dep, True))
    vite = node_resolve("vite", web, web)
    rows, installed = [], set()
    notice_bundle = (web / "THIRD_PARTY_LICENSES.txt").read_bytes()
    for folder in sorted(package_roots):
        metadata_bytes = (folder / "package.json").read_bytes()
        meta = json.loads(metadata_bytes)
        key = (meta["name"], meta["version"])
        installed.add(key)
        notices = notice_files(folder)
        scope = "BROWSER_RUNTIME" if folder in production else "VITE_BROWSER_HELPER" if folder == vite else "DEVELOPMENT_NOT_SHIPPED_AS_PACKAGE"
        row = {"name": key[0], "version": key[1], "declared_license": meta.get("license", "UNDECLARED"),
               "repository": meta.get("repository"), "scope": scope,
               "package_json_sha256": digest(metadata_bytes), "locked": key in locked,
               "original_notices": notices}
        if scope != "DEVELOPMENT_NOT_SHIPPED_AS_PACKAGE":
            # Preserve exact byte texts (not just an SPDX/name/URL summary).
            require(bool(notices), "BROWSER_ORIGINAL_NOTICE_MISSING:" + key[0])
            row["notice_bundle_preserved"] = all((folder / item["path"]).read_bytes() in notice_bundle for item in notices)
            require(row["notice_bundle_preserved"], "BROWSER_NOTICE_BUNDLE_DRIFT:" + key[0])
        rows.append(row)
    require(all(item["optional"] for item in pending), "PRODUCTION_DEPENDENCY_MISSING")
    require(all(row["locked"] for row in rows), "INSTALLED_PACKAGE_NOT_LOCKED")
    require((web / "public/THIRD_PARTY_LICENSES.txt").read_bytes() == notice_bundle, "PUBLIC_NOTICE_COPY_DRIFT")
    return {"lock_sha256": digest(lock_bytes), "installed_lock_matches": True, "installed_packages": rows,
            "locked_packages_not_installed": [{"name": name, "version": version, "status": "NOT_INSTALLED_NOT_SHIPPED"}
                                             for name, version in sorted(set(locked) - installed)],
            "production_edges": graph, "production_missing": pending,
            "scope_counts": dict(Counter(row["scope"] for row in rows)),
            "legal_clearance": "INVENTORY_NOT_LEGAL_CERTIFICATION"}


def wheel_inventory(wheel, lock):
    data = wheel.read_bytes()
    match = re.search(r"(?m)^Pillow==([^ ]+) --hash=sha256:([a-f0-9]{64})\s*$", lock.read_text())
    require(match and digest(data) == match[2], "PYTHON_WHEEL_LOCK_MISMATCH")
    with zipfile.ZipFile(wheel) as archive:
        metadata_files = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        require(len(metadata_files) == 1, "WHEEL_METADATA_COUNT")
        meta = BytesParser().parsebytes(archive.read(metadata_files[0]))
        require(meta["Name"].lower() == "pillow" and meta["Version"] == match[1], "WHEEL_METADATA_IDENTITY")
        notices = [{"path": name, "sha256": digest(archive.read(name)), "bytes": len(archive.read(name))}
                   for name in sorted(archive.namelist()) if not name.endswith("/") and LEGAL_NAME.match(name.rsplit("/", 1)[-1])]
        require(bool(notices), "WHEEL_NOTICES_MISSING")
        dependencies = meta.get_all("Requires-Dist", [])
        # Optional extra requirements are recorded but not silently shipped.
        require(all("extra ==" in dep for dep in dependencies), "UNINVENTORIED_PYTHON_RUNTIME_DEPENDENCY")
    return {"name": meta["Name"], "version": meta["Version"], "wheel_sha256": digest(data),
            "declared_license": meta["License-Expression"] or meta["License"],
            "requires_dist": dependencies, "original_notices": notices,
            "scope": "SHIPPED_WHEEL_WITH_BUNDLED_LIBRARY_NOTICES"}


def source_inventory(root):
    packages = []
    for name in ("pyproject.toml", "packages/twinpulse_app/pyproject.toml", "packages/twinpulse_provider/pyproject.toml"):
        data = (root / name).read_bytes()
        meta = tomllib.loads(data.decode("utf-8"))["project"]
        packages.append({"name": meta["name"], "version": meta["version"], "path": name,
                         "metadata_sha256": digest(data), "requires_dist": meta["dependencies"], "scope": "TWINPULSE_OWNED_SOURCE"})
    lineage_path = root / "artifacts/robot-models/burger-prepared/source.json"
    data = lineage_path.read_bytes()
    lineage = json.loads(data)
    source_root = root / "artifacts/robot-models/turtlebot3-source/turtlebot3_description"
    checks = [("urdf/turtlebot3_burger.urdf", lineage["source_urdf_sha256"])]
    checks.extend((name.replace("\\", "/"), sha) for name, sha in lineage["mesh_sha256"].items())
    sources = []
    for name, expected in checks:
        path = source_root / name
        relative(path, source_root)
        actual = digest(path.read_bytes())
        require(actual == expected, "ROBOTIS_SOURCE_LINEAGE_DRIFT")
        sources.append({"path": relative(path, root), "sha256": actual})
    converted_root = root / "artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1"
    converted = [{"path": relative(path, root), "sha256": digest(path.read_bytes()),
                  "redistribution": "CONTENT_SPECIFIC_REVIEW_REQUIRED"} for path in plain_files(converted_root)]
    require(len(converted) == 9, "PINNED_BURGER_FILE_COUNT_DRIFT")
    return {"python_packages": packages, "robotis_origin": lineage["source"], "robotis_commit": lineage["commit"],
            "robotis_declared_license": lineage["license"], "lineage_sha256": digest(data),
            "original_source_hashes_verified": sources, "converted_assets": converted,
            "rights_scope": "ORIGIN_AND_INTEGRITY_NOT_BLANKET_OUTPUT_LICENSE"}


def installed_isaac_inventory(root):
    # Optional read-only evidence; never launch/import the installed engine.
    names = ("VERSION", "LICENSE.txt", "exts/isaacsim.asset.importer.urdf/config/extension.toml",
             "exts/isaacsim.asset.importer.urdf/pip_prebundle/urdf_usd_converter-0.1.3.dist-info/METADATA",
             "exts/isaacsim.asset.importer.urdf/pip_prebundle/urdf_usd_converter-0.1.3.dist-info/licenses/LICENSE.md")
    rows = [{"installed_relative_path": name, "sha256": digest((root / name).read_bytes())} for name in names]
    converter = BytesParser().parsebytes((root / names[3]).read_bytes())
    return {"version": (root / "VERSION").read_text().strip(), "files": rows,
            "converter": {"name": converter["Name"], "version": converter["Version"], "license": converter["License"]},
            "shipped_in_release": False, "runtime_redistribution": "NOT_AUTHORIZED_BY_TWINPULSE_APACHE_DECLARATION"}


def content_findings(name, data):
    # File-name deny rules run before content is read by the release auditor.
    result = []
    if PRIVATE_PATH.search(data):
        result.append("PERSONAL_ABSOLUTE_PATH_REVIEW")
    if SECRET.search(data):
        result.append("POTENTIAL_CREDENTIAL_MATERIAL")
    return result


def classify(name):
    parts = PurePosixPath(name).parts
    low = [part.lower() for part in parts]
    # Python test fixtures are own test code, not the external fixture datasets.
    # Photos/JSON/raw additions under the same folder still follow deny rules.
    if name.startswith("tests/fixtures/") and name.endswith(".py"):
        return "OWNED_CODE_CANDIDATE"
    if any(part in FORBIDDEN_PARTS or part.startswith(".env") for part in low) or low[-1] in {"id_rsa", "id_ed25519"} or PurePosixPath(name).suffix.lower() in {".pem", ".key", ".p12"}:
        return "EXCLUDED_PRIVATE_OR_RUNTIME"
    if name.startswith("artifacts/robot-models/burger-isaac/usd/"):
        return "CONVERTED_ASSET_RIGHTS_AND_PATH_REVIEW"
    if name in {"artifacts/robot-models/turtlebot3-source/LICENSE", "artifacts/robot-models/burger-prepared/source.json"} or name.startswith("artifacts/robot-models/turtlebot3-source/turtlebot3_description/"):
        return "ROBOTIS_UPSTREAM_NOTICE_REQUIRED"
    if name.startswith("wheelhouse/") and name.endswith(".whl"):
        return "PINNED_PYTHON_WHEEL"
    if name.startswith("apps/twinpulse-web/dist/") and (PurePosixPath(name).suffix in {".js", ".css", ".html", ".txt"} or parts[-1] in {"LICENSE", "NOTICE", "twinpulse-build-manifest.json"}):
        return "BROWSER_BUILD_NOTICE_REQUIRED"
    if name.startswith("apps/twinpulse-web/e2e/") and name.endswith(".mjs"):
        return "OWNED_CODE_CANDIDATE"
    if name in ROOT_DOCUMENTS or name.startswith(OWNED_ROOTS) and PurePosixPath(name).suffix in OWNED_TYPES:
        return "OWNED_CODE_OR_DOCUMENT_CANDIDATE"
    if name.endswith("/LICENSE") or name.endswith("/NOTICE"):
        return "NOTICE"
    return "UNCLASSIFIED_CONTENT_REVIEW"


def audit_release(release, inventory):
    findings, rows = [], []
    files = list(plain_files(release))
    require(len(files) <= 2000, "RELEASE_FILE_COUNT_BOUND")
    file_names = {relative(path, release) for path in files}
    for path in files:
        name = relative(path, release)
        if name in {"release-manifest.json", "provenance-audit.json"}:
            continue
        classification = classify(name)
        if classification == "EXCLUDED_PRIVATE_OR_RUNTIME":
            # Do not read a private key or excluded photo/log just to flag it.
            issues = [classification]
            rows.append({"path": name, "classification": classification, "content_read": False})
        else:
            data = path.read_bytes()
            issues = content_findings(name, data) if path.suffix.lower() != ".whl" else []
            if classification in {"CONVERTED_ASSET_RIGHTS_AND_PATH_REVIEW", "UNCLASSIFIED_CONTENT_REVIEW"}:
                issues.append(classification)
            rows.append({"path": name, "classification": classification, "sha256": digest(data), "bytes": len(data)})
        findings.extend({"path": name, "reason": issue} for issue in issues)
    names = {row["path"] for row in rows}
    for required in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "docs/LICENSING.md",
                     "apps/twinpulse-web/dist/THIRD_PARTY_LICENSES.txt", "artifacts/robot-models/turtlebot3-source/LICENSE"):
        if required not in names:
            findings.append({"path": required, "reason": "REQUIRED_NOTICE_MISSING"})
        elif (release / required).read_bytes() != (ROOT / required).read_bytes():
            findings.append({"path": required, "reason": "REQUIRED_NOTICE_DRIFT"})
    wheel_rows = [row for row in rows if row["classification"] == "PINNED_PYTHON_WHEEL"]
    if len(wheel_rows) != 1 or wheel_rows[0].get("sha256") != inventory["python"]["wheel_sha256"]:
        findings.append({"path": "wheelhouse", "reason": "SHIPPED_WHEEL_IDENTITY_MISMATCH"})
    manifest_path = release / "release-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        entries = manifest.get("files", [])
        seen = set()
        for item in entries:
            name = item["path"]
            require(name not in seen and not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts and "\\" not in name and ":" not in name, "MANIFEST_UNSAFE_OR_DUPLICATE_PATH")
            seen.add(name)
            require(name in file_names, "MANIFEST_FILE_MISSING")
            path = release / name
            if classify(name) == "EXCLUDED_PRIVATE_OR_RUNTIME":
                continue
            data = path.read_bytes()
            require(item["sha256"] == digest(data) and item["bytes"] == len(data), "MANIFEST_HASH_MISMATCH")
        require(seen == file_names - {"release-manifest.json"}, "UNMANIFESTED_RELEASE_FILE")
    return {"status": "PUBLIC_REVIEW_REQUIRED" if findings else "AUTOMATED_CONTENT_CHECK_PASS_NOT_PUBLICATION_APPROVAL",
            "public_ready": False, "human_content_review": "REQUIRED", "files": rows,
            "findings": findings, "finding_counts": dict(Counter(row["reason"] for row in findings)),
            "manifest_checked": manifest_path.exists(),
            "notes": "Own-code classification is a candidate, not a guarantee of ownership/privacy. No files removed or permissions granted."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--release-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isaac-root", type=Path)
    parser.add_argument("--require-public", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT) and not output.exists(), "NEW_REPOSITORY_OUTPUT_REQUIRED")
    inventory = {"schema": SCHEMA, "status": "OFFLINE_INVENTORY_PASS",
                 "node": node_inventory(ROOT / "apps/twinpulse-web"),
                 "python": wheel_inventory(args.wheel, ROOT / "config/python-runtime-requirements.lock"),
                 "sources": source_inventory(ROOT),
                 "publication_or_runtime_approval": False}
    if args.isaac_root:
        inventory["installed_isaac"] = installed_isaac_inventory(args.isaac_root)
    if args.release_root:
        release = args.release_root.resolve()
        require(release.is_relative_to(ROOT / "outputs") or release.is_relative_to(ROOT / "artifacts/offline-release"), "LOCAL_RELEASE_SCOPE_REQUIRED")
        inventory["release"] = audit_release(release, inventory)
    require(not args.require_public or args.release_root, "PUBLIC_GATE_REQUIRES_RELEASE")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": inventory["status"], "node_scope_counts": inventory["node"]["scope_counts"],
                      "python": inventory["python"]["name"], "release": inventory.get("release", {}).get("status"),
                      "finding_counts": inventory.get("release", {}).get("finding_counts", {}), "report": relative(output, ROOT)}))
    # Never grant publication on scanner results alone; content-specific human
    # rights/privacy review is intentionally distinct from technical integrity.
    return 2 if args.require_public else 0


if __name__ == "__main__":
    raise SystemExit(main())
