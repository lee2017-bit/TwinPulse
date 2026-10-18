# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import os
import sys
import ast
import importlib.util
sys.dont_write_bytecode = True
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parents[1]
resources = Path(os.environ['TWINPULSE_BUILD_RESOURCES']).resolve()
paths = [str(root / 'packages' / name / 'src') for name in
         ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app')]
sys.path[:0] = paths
hidden = sum((collect_submodules(name) for name in
              ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app')), [])

# Child roles are executed from verified source through runpy. Analysis of the
# entry alone cannot see their stdlib imports. Collect their static imports
# without executing/importing robot scripts or shipping Isaac/ROS libraries.
stdlib = set()
for script in (resources / 'scripts').glob('*.py'):
    for node in ast.walk(ast.parse(script.read_text(encoding='utf-8-sig'))):
        names = [item.name for item in node.names] if isinstance(node, ast.Import) else (
            [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else [])
        for name in names:
            top = name.split('.')[0]
            if top in sys.stdlib_module_names and importlib.util.find_spec(name) is not None:
                stdlib.add(name)
hidden = sorted(set(hidden) | stdlib)
data = [(str(resources), 'resources'), *copy_metadata('Pillow')]
a = Analysis([str(root / 'scripts/twinpulse_desktop_entry.py')], pathex=paths,
             binaries=[], datas=data, hiddenimports=hidden, hookspath=[],
             excludes=['pytest', 'PyInstaller'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TwinPulse',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TwinPulse')
