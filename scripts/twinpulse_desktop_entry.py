# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen Windows entry point; only named, bundled child roles are supported."""
from pathlib import Path
import json
import os
import runpy
import sys
import traceback


def should_show_error_dialog(arguments):
    """Interactive launches may show errors; headless install must terminate."""
    return bool(getattr(sys,'frozen',False)) and '--internal-role' not in arguments and '--quiet' not in arguments


def apply_packaged_capabilities(package,role,environment):
    """Normalize every frozen role from its verified manifest, not parent flags."""
    capabilities=package.get('capabilities',{})
    physical=capabilities.get('physical_robot') is True
    if physical:environment.pop('TWINPULSE_SIM_ONLY',None)
    else:
        environment['TWINPULSE_SIM_ONLY']='1'
        if role not in {'launcher','backend','install','library-tool','motion-review'}:
            raise ValueError('PACKAGE_PHYSICAL_ROLE_DISABLED')
    if capabilities.get('robot_observation') is True:
        environment['TWINPULSE_ROBOT_OBSERVATION']='1'
    else:environment.pop('TWINPULSE_ROBOT_OBSERVATION',None)
    environment['TWINPULSE_RELEASE_ID']=str(package.get('build_id',''))
    environment['TWINPULSE_RELEASE_VERSION']=str(package.get('product_version',''))


def main():
    sys.dont_write_bytecode = True
    frozen = bool(getattr(sys, 'frozen', False))
    root = Path(sys._MEIPASS) / 'resources' if frozen else Path(__file__).resolve().parents[1]
    package=None
    if frozen:
        from twinpulse_bootstrap_integrity import verify_before_import
        package=verify_before_import(Path(sys.executable).parent)
    for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
        sys.path.insert(0, str(root / 'packages' / name / 'src'))
    sys.path.insert(0, str(root / 'scripts'))
    from twinpulse_app.desktop_settings import read_settings, save_settings
    from twinpulse_app.runtime_paths import SCRIPT_ROLES
    arguments = sys.argv[1:]
    role = 'launcher'
    if arguments[:1] == ['--install']:
        role, arguments = 'install', arguments[1:]
    if arguments[:1] == ['--internal-role']:
        if len(arguments) < 2 or arguments[1] not in SCRIPT_ROLES:
            raise ValueError('UNSUPPORTED_DESKTOP_ROLE')
        role, arguments = arguments[1], arguments[2:]
    if frozen:apply_packaged_capabilities(package,role,os.environ)
    state = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'TwinPulse' / 'runtime'
    state.mkdir(parents=True, exist_ok=True)
    from twinpulse_app.desktop_testing import configure_testing
    arguments=configure_testing(arguments,state,os.environ,role=role)
    # Windowed bootloaders have no Python stdout even when spawned with handles.
    inherited_output = False
    if frozen and role=='library-tool' and os.name=='nt':
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetStdHandle.argtypes=[wintypes.DWORD];kernel.GetStdHandle.restype=wintypes.HANDLE
        # MCP stdout must contain protocol messages only, not stderr logs.
        for attribute,handle_id,flags,mode in (('stdin',-10,os.O_RDONLY,'r'),
                ('stdout',-11,os.O_WRONLY,'w'),('stderr',-12,os.O_WRONLY,'w')):
            handle=kernel.GetStdHandle(wintypes.DWORD(handle_id))
            if not handle:raise ValueError('LIBRARY_STDIO_PIPE_REQUIRED')
            setattr(sys,attribute,os.fdopen(msvcrt.open_osfhandle(int(handle),flags),mode,encoding='utf-8',buffering=1))
        inherited_output=True
    if frozen and role not in {'launcher','library-tool'} and os.name == 'nt':
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetFileType.argtypes = [wintypes.HANDLE]
        handle = kernel.GetStdHandle(wintypes.DWORD(-11))
        if handle and kernel.GetFileType(handle) in {1, 3}:
            descriptor = msvcrt.open_osfhandle(int(handle), os.O_WRONLY)
            sys.stdout = sys.stderr = os.fdopen(descriptor, 'w', encoding='utf-8', buffering=1)
            inherited_output = True
    if frozen and not inherited_output:
        log = state / 'desktop-logs' / (role + '-' + str(os.getpid()) + '.log')
        log.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = log.open('a', encoding='utf-8', buffering=1)
    if arguments == ['--inspect-package']:
        from twinpulse_app.windows_package import verify_package
        result = verify_package(Path(sys.executable).parent if frozen else root)
        print(json.dumps(result, sort_keys=True))
        return 0
    if role == 'launcher' and frozen:
        configuration = read_settings(state)
        if '--isaac-root' not in arguments and not (Path(configuration.get('isaac_root', r'C:\isaacsim')) / 'python.bat').is_file():
            import tkinter as tk
            from tkinter import filedialog
            window = tk.Tk(); window.withdraw()
            selected = filedialog.askdirectory(parent=window, title='Select your installed Isaac Sim folder')
            window.destroy()
            if selected and not (Path(selected) / 'python.bat').is_file():
                raise ValueError('ISAAC_FOLDER_MISSING_PYTHON_BAT')
            if selected:
                save_settings(state, isaac_root=str(Path(selected).resolve()))
    if role == 'install':
        if not frozen or arguments not in ([], ['--quiet']):
            raise ValueError('INSTALL_REQUIRES_PACKAGED_EXE')
        from twinpulse_app.windows_install import install_package
        installation = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse' / 'installed'
        result = install_package(Path(sys.executable).parent, installation)
        import ctypes
        print(json.dumps(result))
        if arguments != ['--quiet']:
            ctypes.windll.user32.MessageBoxW(None,
                'TwinPulse installed for this Windows user.\nStart using:\n' + result['start']
                + '\nExisting projects and API-key references were preserved.', 'TwinPulse', 0)
        return 0
    script = 'twinpulse_launcher.py' if role == 'launcher' else SCRIPT_ROLES[role]
    sys.argv = [str(root / 'scripts' / script), *arguments]
    module = runpy.run_path(sys.argv[0], run_name='twinpulse_desktop_' + role.replace('-', '_'))
    result = module['main']()
    if result and frozen and role == 'launcher':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            'TwinPulse could not complete startup.\nOpen the diagnostics if the App is visible, '
            'or inspect %LOCALAPPDATA%\\TwinPulse\\runtime\\desktop-logs.\n'
            'No other application was stopped.', 'TwinPulse startup', 0x10)
    return result


if __name__ == '__main__':
    show_error_dialog = should_show_error_dialog(sys.argv[1:])
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as error:
        traceback.print_exc()
        if show_error_dialog:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                'TwinPulse could not start.\n' + type(error).__name__ + ': ' + str(error)[:600]
                + '\nSee %LOCALAPPDATA%\\TwinPulse\\runtime\\desktop-logs.',
                'TwinPulse startup', 0x10)
        raise SystemExit(1)
