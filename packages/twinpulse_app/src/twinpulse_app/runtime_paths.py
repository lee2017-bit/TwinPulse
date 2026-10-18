# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""App resources and explicit child roles, independent of the working directory."""
from contextlib import contextmanager
from pathlib import Path
import os
import sys

SCRIPT_ROLES = {
    'backend': 'twinpulse_backend.py',
    'robot-readiness': 'run_robot_readiness.py',
    'robot-prepare': 'prepare_robot.py',
    'library-tool': 'twinpulse_library_worker.py',
}


def resource_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS).resolve() / 'resources'
    return Path(__file__).resolve().parents[4]


def script_command(root: Path, role: str, *, python: Path | None = None) -> list[str]:
    if role not in SCRIPT_ROLES:
        raise ValueError('UNSUPPORTED_DESKTOP_ROLE')
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--internal-role', role]
    return [str(python or sys.executable), '-B', str(root / 'scripts' / SCRIPT_ROLES[role])]


def child_environment(environment, *, external=False):
    result = dict(environment)
    if getattr(sys, 'frozen', False):
        # Every child is a new bootloader instance, not a continuation of ours.
        result['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        if external:
            for key in tuple(result):
                if key.startswith('_PYI_') or key in {'PYTHONHOME', 'PYTHONPATH'}:
                    result.pop(key, None)
    return result


@contextmanager
def external_dll_search():
    """Undo the bootloader's process-local DLL directory for external Isaac."""
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    size = kernel.GetDllDirectoryW(0, None)
    buffer = ctypes.create_unicode_buffer(size + 1)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    previous = buffer.value
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not kernel.SetDllDirectoryW(previous or None):
            raise ctypes.WinError(ctypes.get_last_error())
