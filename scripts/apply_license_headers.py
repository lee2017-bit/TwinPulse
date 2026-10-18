# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded, mechanical licensing-only rewrite; never touches saved evidence.

Default is a read-only inventory. --apply inserts reversible native comments,
preserves existing bytes/newlines/directives/notices and records every digest.
No imports from the App, robot, provider or Isaac are needed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tokenize

ROOT = Path(__file__).resolve().parents[1]
ROOTS = (
    "packages/twinpulse_core/src", "packages/twinpulse_core/tests",
    "packages/twinpulse_provider/src", "packages/twinpulse_provider/tests",
    "packages/twinpulse_app/src", "packages/twinpulse_app/tests",
    "packages/twinpulse_robot_safety", "extensions/twinpulse.extension",
    "apps/twinpulse-web/src", "apps/twinpulse-web/e2e", "scripts", "tests",
)
EXTRA = (
    "pyproject.toml", "packages/twinpulse_app/pyproject.toml",
    "packages/twinpulse_provider/pyproject.toml", "apps/twinpulse-web/vite.config.ts",
    "apps/twinpulse-web/index.html",
)
SUFFIXES = {".py", ".ts", ".tsx", ".mjs", ".css", ".cpp", ".hpp", ".sh", ".ps1", ".cmd", ".toml", ".html"}
EXCLUDED_DIRS = {"build", "checks", "dist", "node_modules", "__pycache__", ".pytest_cache", ".git", "outputs", "artifacts"}
FIELDS = (
    "SPDX-FileCopyrightText: 2026 Jaewon Lee",
    "SPDX-License-Identifier: Apache-2.0",
    "Source: https://github.com/lee2017-bit/TwinPulse",
)
NOTICE = re.compile(r"(?im)^\s*(?:#|//|/\*|\*|<!--|rem\s+)\s*(?:Copyright\b|SPDX-(?:FileCopyrightText|License-Identifier):)")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def candidates():
    paths = {ROOT / p for p in EXTRA}
    paths.update(ROOT.glob("*.cmd"))
    for relative in ROOTS:
        base = ROOT / relative
        if not base.is_dir():
            continue
        for folder, directories, files in os.walk(base, followlinks=False):
            directories[:] = sorted(d for d in directories if d not in EXCLUDED_DIRS
                                    and not d.endswith(".egg-info")
                                    and not (Path(folder) / d).is_symlink())
            paths.update(Path(folder) / n for n in files if Path(n).suffix in SUFFIXES or n == "CMakeLists.txt")
    return sorted(p for p in paths if p.is_file() and not p.is_symlink())


def insert_header(path, data):
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    raw = data[len(bom):]
    text = raw.decode("utf-8")
    notice_text = text[:4096]
    if path.suffix == ".py":
        notice_text = "\n".join(token.string for token in tokenize.tokenize(io.BytesIO(data).readline)
                                if token.type == tokenize.COMMENT)
    if NOTICE.search(notice_text):
        return data, "existing_notice_preserved"
    lines = raw.splitlines(keepends=True)
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    position = 0
    if lines and lines[0].startswith(b"#!"):
        position = 1
    if path.suffix == ".py":
        for i, line in enumerate(lines[:2]):
            if re.match(rb"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+", line):
                position = max(position, i + 1)
    if path.suffix == ".cmd" and lines and lines[0].strip().lower() == b"@echo off":
        position = 1
    if path.suffix == ".html" and lines and lines[0].strip().lower() == b"<!doctype html>":
        position = 1
    if path.suffix == ".css" and lines and lines[0].lstrip().startswith(b"@charset"):
        position = 1
    if path.suffix in {".ts", ".tsx", ".mjs"}:
        while position < len(lines) and (lines[position].startswith(b"///")
                                       or lines[position].startswith(b"// GENERATED")
                                       or lines[position].startswith(b"// @")):
            position += 1
    if position and not lines[position - 1].endswith(b"\n"):
        raise ValueError("DIRECTIVE_WITHOUT_NEWLINE:" + str(path))
    if path.suffix in {".py", ".sh", ".ps1", ".toml"} or path.name == "CMakeLists.txt":
        header = ["# " + field for field in FIELDS]
    elif path.suffix == ".cmd":
        header = ["rem " + field for field in FIELDS]
    elif path.suffix == ".html":
        header = ["<!--"] + list(FIELDS) + ["-->"]
    elif path.suffix == ".css":
        header = ["/*"] + [" * " + field for field in FIELDS] + [" */"]
    else:
        header = ["// " + field for field in FIELDS]
    insertion = newline.join(line.encode("ascii") for line in header) + newline
    offset = sum(len(line) for line in lines[:position]) + len(bom)
    updated = data[:offset] + insertion + data[offset:]
    # Exact reversibility protects non-comment bytes, including file endings.
    assert updated[:offset] + updated[offset + len(insertion):] == data
    if path.suffix == ".py":
        assert ast.dump(ast.parse(data), include_attributes=False) == ast.dump(ast.parse(updated), include_attributes=False)
    return updated, {"offset": offset, "inserted_bytes": len(insertion),
                     "inserted_text": insertion.decode("ascii"), "python_ast_equal": path.suffix == ".py"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.apply and args.report is None:
        parser.error("--apply requires a new owned --report")
    if args.report:
        report = args.report.resolve()
        if not report.is_relative_to(ROOT / "outputs" / "licensing-20261011") or report.exists():
            parser.error("new licensing-only output path required")
    rows = []
    # Precompute all proposed changes before writing any source file.
    changes = []
    for path in candidates():
        before = path.read_bytes()
        after, detail = insert_header(path, before)
        row = {"path": path.relative_to(ROOT).as_posix(), "before_sha256": digest(before),
               "after_sha256": digest(after), "changed": before != after, "detail": detail}
        rows.append(row)
        if before != after:
            changes.append((path, before, after))
    if args.apply:
        for path, before, after in changes:
            if path.read_bytes() != before:
                raise RuntimeError("SOURCE_CHANGED_DURING_LICENSING:" + str(path))
            path.write_bytes(after)
    result = {"schema": "twinpulse-license-headers-1.0", "applied": args.apply,
              "candidate_count": len(rows), "changed_count": len(changes),
              "excluded": "upstream patch/context, dependencies, assets, binary/data/JSON, outputs, frozen evidence",
              "files": rows}
    if args.report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}))


if __name__ == "__main__":
    main()
