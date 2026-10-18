# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fetch a pinned official nominal Burger asset; prepare URDF without installing ROS."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "90a68bd2e3c61c12966779da89d8eeaec82730e9"
URL = "https://github.com/ROBOTIS-GIT/turtlebot3.git"
BASE = ROOT / "artifacts/robot-models"


def prepare(fetch=False):
    source = BASE / "turtlebot3-source"
    if not source.exists():
        if not fetch:
            raise ValueError("Source missing. Run with --fetch to download the official model.")
        subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none", URL, str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", COMMIT], check=True)
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != COMMIT:
        raise ValueError("Source revision mismatch; existing source was not modified")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise ValueError("Source has local edits; refusing to treat it as the pinned official model")
    package = source / "turtlebot3_description"
    original = package / "urdf/turtlebot3_burger.urdf"
    tree = ET.parse(original)
    robot = tree.getroot()
    ns = "{http://ros.org/wiki/xacro}"
    expected = {ns + "arg": {"name": "namespace", "default": ""},
                ns + "property": {"name": "namespace", "value": "$(arg namespace)"}}
    for child in list(robot):
        if child.tag in expected and child.attrib == expected[child.tag]:
            robot.remove(child)
    meshes = {}
    for element in robot.iter():
        if element.tag.startswith(ns):
            raise ValueError("Unsupported xacro: use the official xacro processor")
        for key, value in list(element.attrib.items()):
            element.set(key, value.replace("${namespace}", ""))
            if "$" in element.get(key):
                raise ValueError("Unresolved URDF expression")
        if element.tag == "mesh":
            prefix = "package://turtlebot3_description/"
            filename = element.get("filename", "")
            if not filename.startswith(prefix):
                raise ValueError("Unexpected mesh reference")
            mesh = (package / filename[len(prefix):]).resolve()
            if not mesh.is_relative_to(package.resolve()) or not mesh.is_file():
                raise ValueError("Mesh is missing or outside source package")
            meshes[str(mesh.relative_to(package))] = hashlib.sha256(mesh.read_bytes()).hexdigest()
            element.set("filename", mesh.as_posix())
    output = BASE / "burger-prepared"
    output.mkdir(parents=True, exist_ok=True)
    urdf = output / "turtlebot3_burger.urdf"
    tree.write(urdf, encoding="utf-8", xml_declaration=True)
    metadata = {"source": URL, "commit": COMMIT, "license": "Apache-2.0",
                "source_urdf_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                "mesh_sha256": meshes, "namespace": "", "physical_robot_match": "UNVERIFIED",
                "note": "Nominal official model. Not registered as a validated TwinPulse robot profile."}
    (output / "source.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (output / "LICENSE").write_bytes((source / "LICENSE").read_bytes())
    print(urdf)
    return urdf


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    prepare(parser.parse_args().fetch)
