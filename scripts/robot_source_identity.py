# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Deterministic identity of the reviewed robot source sent by prepare_robot.

Purely local: never opens an SSH connection or reads credentials.
"""
import hashlib
import json
import ast
from pathlib import Path

# The robot imports the same pure contracts as the App, not a fork of the
# navigation algorithm. Keep the namespace initializer deliberately inert:
# the desktop initializer eagerly imports unrelated authoring subsystems.
ROBOT_CORE_ENTRYPOINTS = ('observed_mission', 'current_mission_evidence',
                         'automatic_mapping', 'automatic_photo_alignment', 'adaptive_mission_contract','cold_start_mission',
                         'mission_correction_contract', 'mission_evidence_contract', 'mission_telemetry', 'cleanup_diagnostics',
                         'manual_motion_guard','field_persistence')


def core_members(core, entrypoints=()):
    core = Path(core)
    pending = list(ROBOT_CORE_ENTRYPOINTS) + list(entrypoints)
    seen = set()
    result = {'twinpulse_core/__init__.py': (
        b'# SPDX-FileCopyrightText: 2026 Jaewon Lee\n'
        b'# SPDX-License-Identifier: Apache-2.0\n'
        b'# Source: https://github.com/lee2017-bit/TwinPulse\n'
        b'"""Reviewed pure robot contracts; no device initialization."""\n')}
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        if not name.isidentifier():
            raise ValueError('ROBOT_CORE_MODULE_NAME')
        seen.add(name)
        path = core / (name + '.py')
        if path.is_symlink() or not path.is_file():
            raise ValueError('ROBOT_CORE_DEPENDENCY_MISSING:' + name)
        data = path.read_bytes()
        tree = ast.parse(data, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                if node.level != 1 or not node.module:
                    raise ValueError('ROBOT_CORE_RELATIVE_IMPORT:' + name)
                pending.append(node.module.split('.')[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('twinpulse_core.'):
                pending.append(node.module.split('.')[1])
        result['twinpulse_core/' + name + '.py'] = data
    return result


def bundle_files(root):
    root = Path(root)
    package = root / 'packages/twinpulse_robot_safety'
    files = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob('*')
             if p.is_file() and (p.suffix in {'.py', '.json', '.cpp', '.hpp', '.txt', '.patch', '.md', '.sh','.xml'}
                                or p.name in {'LICENSE', 'NOTICE'})
             and not {'__pycache__', 'checks', 'build'}.intersection(p.relative_to(package).parts)}
    files['robot_health.py'] = (root / 'scripts/robot_health.py').read_bytes()
    core = root / 'packages/twinpulse_core/src/twinpulse_core'
    for name in ('local_navigation.py', 'ros_observations.py', 'navigation_binding.py', 'mission_contract.py',
                 'observation_stream.py'):
        files[name] = (core / name).read_bytes()
    # Resolve the robot sources' absolute contract imports too. A fixed list
    # alone missed robot_timing_profile when teleop_contract began importing it.
    # This scans reviewed source, never client/model-provided module names.
    required = set()
    for name, data in files.items():
        if not name.endswith('.py') or 'tests' in Path(name).parts:
            continue
        for node in ast.walk(ast.parse(data, filename=name)):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('twinpulse_core.'):
                required.add(node.module.split('.')[1])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('twinpulse_core.'):
                        required.add(alias.name.split('.')[1])
    files.update(core_members(core, required))
    return {name: data.replace(b'\r\n', b'\n') if name.endswith('.sh') else data
            for name, data in files.items()}


def source_id(root):
    """Match runtime.prepare's source_files JSON hash without creating an archive."""
    members = bundle_files(root)
    digests = {name: hashlib.sha256(content).hexdigest() for name, content in members.items()}
    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()
