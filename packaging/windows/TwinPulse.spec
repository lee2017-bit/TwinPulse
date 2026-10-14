# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import os
import sys
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
data = [(str(resources), 'resources'), *copy_metadata('Pillow')]
a = Analysis([str(root / 'scripts/twinpulse_desktop_entry.py')], pathex=paths,
             binaries=[], datas=data, hiddenimports=hidden, hookspath=[],
             excludes=['pytest', 'PyInstaller'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TwinPulse',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TwinPulse')
