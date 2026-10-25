# SPDX-License-Identifier: Apache-2.0
"""Isolated actual Win32 publication diagnostic; no App or hardware access."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / f'packages/{package}/src'))
from twinpulse_app.process_manager import _engine_status_win_api


def main():
    parent = ROOT / 'outputs/status-file-fixtures'
    parent.mkdir(parents=True, exist_ok=True)
    kernel = _engine_status_win_api()
    kernel.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    kernel.MoveFileExW.restype = wintypes.BOOL
    kernel.ReplaceFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    kernel.ReplaceFileW.restype = wintypes.BOOL
    results = []
    with TemporaryDirectory(dir=parent) as folder:
        folder = Path(folder).resolve()
        assert folder.is_relative_to(parent.resolve())
        for method in ('replace', 'move_native', 'replace_native', 'rename_to_absent', 'open_delete'):
            for sharing in (3, 7):
                current = folder / f'{method}-{sharing}.json'
                source = folder / f'{method}-{sharing}.tmp'
                absent = folder / f'{method}-{sharing}.moved'
                current.write_bytes(b'old publication')
                source.write_bytes(b'new publication')
                handle = kernel.CreateFileW(str(current), 0x80000000, sharing, None, 3, 128, None)
                assert handle != ctypes.c_void_p(-1).value
                row = dict(method=method, sharing=sharing)
                try:
                    if method == 'replace':
                        try:
                            os.replace(source, current)
                            row['ok'] = True
                        except OSError as error:
                            row.update(ok=False, winerror=error.winerror)
                    elif method == 'move_native':
                        row['ok'] = bool(kernel.MoveFileExW(str(source), str(current), 1))
                        if not row['ok']:
                            row['winerror'] = ctypes.get_last_error()
                    elif method == 'replace_native':
                        row['ok'] = bool(kernel.ReplaceFileW(str(current), str(source), None, 0, None, None))
                        if not row['ok']:
                            row['winerror'] = ctypes.get_last_error()
                    elif method == 'rename_to_absent':
                        row['ok'] = bool(kernel.MoveFileExW(str(current), str(absent), 0))
                        if not row['ok']:
                            row['winerror'] = ctypes.get_last_error()
                    else:
                        other = kernel.CreateFileW(str(current), 0x10000, 7, None, 3, 128, None)
                        row['ok'] = other != ctypes.c_void_p(-1).value
                        if row['ok']:
                            assert kernel.CloseHandle(other)
                        else:
                            row['winerror'] = ctypes.get_last_error()
                    buffer = ctypes.create_string_buffer(128)
                    count = wintypes.DWORD()
                    assert kernel.ReadFile(handle, buffer, 128, ctypes.byref(count), None)
                    row['pinned_original'] = buffer.raw[:count.value].decode()
                    if current.exists():
                        row['current_name_bytes'] = current.read_text()
                finally:
                    assert kernel.CloseHandle(handle)
                results.append(row)
    print(json.dumps(dict(schema='win32-publication-probe/1.0', results=results), indent=2))


if __name__ == '__main__':
    main()
