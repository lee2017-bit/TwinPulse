#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
r"""Read-only TwinPulse company-PC check: one file, standard library only, Python 3.10+.

Run it on the company PC with any Python 3.10+ (system CPython 3.12 or Isaac's python.bat):
    py -3.12 twinpulse_company_pc_check.py
    py -3.12 twinpulse_company_pc_check.py --no-network

It reads Windows, Isaac Sim and TwinPulse state and writes ONE UTF-8 text report to the Desktop
(else the current folder), then prints that path. Nothing else is changed: no installs, settings,
deletes or moves, and Windows Credential Manager is never read. API keys, tokens, Authorization
values and long secrets are redacted, saved prompts (request_redacted) are never read out, and
nothing is uploaded. The network check is an unauthenticated GET of two public model lists, once
with Python's default User-Agent and once with TwinPulse's own (never a browser User-Agent).
Isaac's python.bat runs twice with -B (no files written) only to import numpy and PIL, once as
a plain start and once as TwinPulse starts the engine (without the user site-packages folder).
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import html
import http.client
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CHECK_VERSION = '1.0'
MAX_JSON_BYTES = 8 * 1024 * 1024
REVIEWED_ISAAC_VERSION = '6.0.1-rc.7+release.42383.32955d8d.gl'
ISAAC_CANDIDATES = (r'C:\isaacsim', r'D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64',
                    r'C:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64', r'D:\isaacsim')
NETWORK_TARGETS = (('Nebius', 'https://api.tokenfactory.nebius.com/v1/models'),
                   ('OpenAI', 'https://api.openai.com/v1/models'))
OS_JUNK = frozenset({'thumbs.db', 'desktop.ini', '.ds_store'})
# Runtime order of packages/twinpulse_app/src/twinpulse_app/simulation_assets.py asset_root().
BURGER_FOLDERS = ('assets/simulation/turtlebot3_burger/usd',
                  'artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1')
# Copies of the reviewed pin sets in simulation_assets.py (a test keeps them equal).
BURGER_MANIFEST = {
    'turtlebot3_burger.usda':'58af6e5f75f5cf96362f4abb175971dd555870add77c50a0baaa8028d2293b37',
    'payloads/base.usda':'750889ff799fbe55efe50af7a47e32c38d664ce50fb360aa1802d2daacfcb4f7',
    'payloads/robot.usda':'f384b6a2b53094a18e10b02b18f254f10c2c972a8b9cf8fcccbf2f0159f5ed36',
    'payloads/materials.usda':'2be307ad3d46d77b19c0bea7f229c66af8b35e3dcf7d00455f9ef44927b1328b',
    'payloads/instances.usda':'06798e126ee49d958c4201abdd8ef578eb9a6fc48eed7951c3171e005162aa55',
    'payloads/geometries.usd':'0bda8f94edce82b534d2d58013ecaf8b33d6854a99827fe6fccfbd84a47cf43d',
    'payloads/Physics/physx.usda':'218b0c0f2b82c3859d184c59b8fd36b2b8c28b633609df7325906e370307408a',
    'payloads/Physics/physics.usda':'8c1e6353f364638bd6e8d823351811a353ab5235588d395cf3f56f71c3482195',
    'payloads/Physics/mujoco.usda':'a613ea9405af764aac0b31758b7703e18f74708d238fd8ad158d81a86b65cd98',
}
PUBLIC_BURGER_MANIFEST = {
    'turtlebot3_burger.usda':'3b657533bd802d137c066728e4df1e7b225cd9d5c5738c34c178ed84b4cb1f69',
    'payloads/base.usda':'17767908c3bac46f453b00fe2c566f45f06e57e818b83315fc5e281b92888cf1',
    'payloads/robot.usda':'7de52ca7ad6471aed9fde8c6ef130436e7395dea1c2c3949aed7c952bbfdbbef',
    'payloads/materials.usda':'6d75e07acabbab8f417564dfe8713a62d8d87d2ae47a32bd41c82be70657bd12',
    'payloads/instances.usda':'c194290f05f7dfd9a9b90a8c0dacf2b436e3d4bd032106268d61a9497a20416b',
    'payloads/geometries.usd':'f9ccb9c2716a19289d6ef05e15e57e5c8dbcd1425049317ff462b29bed96d2c0',
    'payloads/Physics/physx.usda':'078530d6b2799caf6bdcb40deaff34092e6b5686b26f21a9bcbd9448eb4eace2',
    'payloads/Physics/physics.usda':'b4c6d8013f5fd7fcdddc4ff39ac769d5b13f976bee0813d8242aa28eb58f0acd',
    'payloads/Physics/mujoco.usda':'63c2a9a8834c470d1424cb4c0e406ccbb293584ee20d392a00bd3f2dded4d659',
}
IDENT = r'[A-Za-z0-9._+-]{1,80}'
MODEL = r'[A-Za-z0-9._:/@+-]{1,128}'
KIT_PATTERN = re.compile(r'error|failed to solve|registry|twinpulse', re.I)
REGISTRY_PATTERN = re.compile(r'failed to solve|syncing with extension registry', re.I)
BACKUP_PATTERN = re.compile(r'(?i)(\.bak|\.orig|\.old|~)$|backup')
EVIDENCE_FIELDS = ('saved_at', 'model_id', 'schema_stage', 'role', 'status', 'http_status', 'error_type', 'elapsed_s')


# ---- text safety ---------------------------------------------------------------------------

_SECRETS = (
    (re.compile(r'(?i)\bbearer\s+[^\s"\'<>,;]+'), 'Bearer [REDACTED]'),
    (re.compile(r'(?i)\b((?:proxy-)?authorization["\']?\s*[:=]\s*["\']?)(?:(?:basic|digest|bearer|token)\s+)?[^\s"\'<>,;]+'),
     r'\1[REDACTED]'),
    (re.compile(r'\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]+)?'), '[REDACTED]'),
    (re.compile(r'\bsk-[A-Za-z0-9_-]{8,}'), '[REDACTED]'),
    (re.compile(r'(?i)((?:api[_-]?key|x-api-key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret|password|passwd|token)'
                r'["\']?\s*[:=]\s*["\']?)[^\s"\'<>,;&]+'), r'\1[REDACTED]'),
    # A URL's user name and password, up to its LAST '@': a password may hold '@' itself.
    (re.compile(r'(?i)\b([a-z][a-z0-9+.-]{1,20}://)[^/\s]+@'), r'\1[REDACTED]@'),
)
# Long base64/hex runs (session ids, bootstrap secrets, keys); paths and versions stay readable.
_STANDARD_BASE64 = re.compile(r'(?<![A-Za-z0-9+/])(?:[A-Za-z0-9+/]{30,}={1,2}|(?=[A-Za-z0-9/]*\+)[A-Za-z0-9+/]{32,})')
_URLSAFE_RUN = re.compile(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])')


def _long_secret(match):
    value = match.group(0)
    return '[REDACTED]' if re.search(r'[0-9]', value) and re.search(r'[A-Za-z]', value) else value


def redact(text, *, long_tokens=True):
    text = str(text)
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    if long_tokens:
        text = _URLSAFE_RUN.sub(_long_secret, _STANDARD_BASE64.sub(_long_secret, text))
    return text


def short(value, limit=300):
    """One redacted line of at most `limit` characters (redacted before it is cut)."""
    flat = ' '.join(re.sub(r'[\x00-\x1f\x7f]', ' ', str(value)).split())
    text = flat[:limit * 16]
    if len(text) < len(flat):  # drop the word this bound split: half a key may no longer match a pattern
        text = text[:max(text.rfind(mark) for mark in ' "\'<>,;&') + 1]
    text = redact(text)
    return text if len(text) <= limit else text[:limit - 3] + '...'


def ident(value, pattern=IDENT):
    """A fixed-shape identifier (release id, phase, model id) or a placeholder."""
    if isinstance(value, bool) or value is None:
        return '-' if value is None else str(value)
    if isinstance(value, (int, float)):
        return str(value)
    return redact(value, long_tokens=False) if isinstance(value, str) and re.fullmatch(pattern, value) else '(unusual value)'


def html_title(body, content_type=''):
    """Title of an HTML page (a filter's block page), decoded with its declared charset."""
    head = bytes(body or b'')[:262144]
    found = (re.search(r'charset=["\']?([A-Za-z0-9_.:-]{1,40})', content_type or '', re.I)
             or re.search(r'<meta[^>]{0,512}charset=["\']?([A-Za-z0-9_.:-]{1,40})', head[:8192].decode('ascii', 'replace'), re.I))
    try:
        text = head.decode(found.group(1) if found else 'utf-8', 'replace')
    except LookupError:
        text = head.decode('utf-8', 'replace')
    match = re.search(r'<title[^>]{0,200}>(.{0,4096}?)</title\s{0,8}>', text, re.I | re.S)
    if not match:
        return None
    return short(html.unescape(re.sub(r'<[^>]{0,200}>', ' ', match.group(1))), 120) or None


def describe_body(body, content_type=''):
    """Typed facts of a response body: a JSON error's type/code/param/message, an HTML title, or a size."""
    body = bytes(body or b'')
    if not body.strip():
        return {'kind': 'none'}
    text = body[:262144].decode('utf-8', 'replace')
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        value = None
    if isinstance(value, (dict, list)):
        facts = {'kind': 'json'}
        error = value.get('error') if isinstance(value, dict) else None
        if isinstance(value, dict) and not isinstance(error, dict):
            detail = value.get('detail')
            if isinstance(detail, list) and detail and isinstance(detail[0], dict):
                detail = detail[0].get('msg')  # a validation item's input could echo the request
            error = {'message': next((v for v in (error, detail, value.get('message')) if isinstance(v, str)), None)}
        if isinstance(error, dict):
            for key in ('type', 'code', 'param'):
                item = error.get(key)
                item = str(item) if type(item) is int else item
                if isinstance(item, str) and re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{1,80}', item):
                    facts[key] = item
            if isinstance(error.get('message'), str) and error['message'].strip():
                facts['message'] = short(error['message'], 300)
        return facts
    if 'html' in (content_type or '').lower() or re.search(r'<(?:!doctype\s+html|html|head|title|body)\b', text[:4096], re.I):
        return {'kind': 'html', 'title': html_title(body, content_type)}
    return {'kind': 'text', 'bytes': len(body)}


def body_text(facts):
    if facts.get('kind') == 'html':
        return 'HTML page' + (f" '{facts['title']}'" if facts.get('title') else ' (no title)')
    if facts.get('kind') == 'json':
        label = '/'.join(facts[key] for key in ('type', 'code', 'param') if facts.get(key))
        return 'JSON' + (f' {label}' if label else '') + (f": {facts['message']}" if facts.get('message') else '')
    if facts.get('kind') == 'text':
        return f"text ({facts.get('bytes', 0)} bytes)"
    return 'no body'


# ---- files ---------------------------------------------------------------------------------

def read_json(path, limit=MAX_JSON_BYTES):
    """(value, info). Reads utf-8-sig, so a PowerShell 5.1 BOM never breaks it; never raises."""
    info = {'exists': False, 'bom': False, 'bytes': 0, 'error': None}
    path = Path(path)
    try:
        if not path.is_file():
            return None, info
        info['exists'], info['bytes'] = True, path.stat().st_size
        if info['bytes'] > limit:
            info['error'] = f'larger than {limit} bytes; not read'
            return None, info
        raw = path.read_bytes()
        info['bom'] = raw.startswith(b'\xef\xbb\xbf')
        return json.loads(raw.decode('utf-8-sig')), info
    except (OSError, ValueError, RecursionError) as error:
        info['error'] = f'{type(error).__name__}: {short(error, 160)}'
        return None, info


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def newest(paths, count):
    return sorted(paths, key=_mtime, reverse=True)[:count]


def local_time(timestamp):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)) if timestamp else '?'


def parse_utc(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def show_utc(value):
    moment = parse_utc(value)
    return moment.astimezone().strftime('%Y-%m-%d %H:%M:%S') if moment else None


def names(items, limit=40):
    items = list(items)
    return ', '.join(items[:limit]) + (f' (+{len(items) - limit} more)' if len(items) > limit else '')


def section(lines, findings, facts=None):
    return {'lines': lines, 'findings': findings, 'facts': facts or {}}


# ---- Windows (guarded: every call is read-only and optional) ------------------------------

def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def reg_value(hive, key, name, winreg=None):
    winreg = winreg or _winreg()
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(getattr(winreg, hive), key, 0, winreg.KEY_READ) as handle:
            return winreg.QueryValueEx(handle, name)[0]
    except (OSError, AttributeError):
        return None


def _kernel32():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    return ctypes, wintypes, kernel


# OpenProcess ERROR_ACCESS_DENIED: the PID belongs to a program this user may not inspect (a service, another
# user). TwinPulse runs as this user, so it is never our TwinPulse; the App archives such a launcher.lock.
ACCESS_DENIED = 'access_denied'


def pid_alive(pid):
    """True/False, ACCESS_DENIED, or None when unknown. It only queries; it never signals the process."""
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == 'nt':  # os.kill on Windows would terminate the process; never use it here
        try:
            ctypes, wintypes, kernel = _kernel32()
            handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                error = ctypes.get_last_error()
                return False if error == 87 else ACCESS_DENIED if error == 5 else None
            try:
                code = wintypes.DWORD()
                return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
            finally:
                kernel.CloseHandle(handle)
        except (OSError, AttributeError, ValueError):
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # another user's process
        return ACCESS_DENIED
    except OSError:
        return None
    return True


def process_identity(pid):
    """{executable, creation_filetime} as TwinPulse records it in launcher.lock (Windows only)."""
    if os.name != 'nt' or type(pid) is not int or pid <= 0:
        return None
    try:
        ctypes, wintypes, kernel = _kernel32()
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            times = [wintypes.FILETIME() for _ in range(4)]
            if (not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
                    or not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times))):
                return None
            return {'executable': buffer.value,
                    'creation_filetime': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime}
        finally:
            kernel.CloseHandle(handle)
    except (OSError, AttributeError, ValueError):
        return None


def expand(value, env):
    upper = {key.upper(): item for key, item in env.items()}
    return re.sub(r'%([^%]+)%', lambda match: upper.get(match.group(1).upper(), match.group(0)), value)


def desktop_folder(env, winreg=None):
    shell = reg_value('HKEY_CURRENT_USER', r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders',
                      'Desktop', winreg)
    candidates = [Path(expand(shell, env))] if isinstance(shell, str) and shell else []
    if env.get('USERPROFILE'):
        candidates.append(Path(env['USERPROFILE']) / 'Desktop')
    return next((path for path in candidates if path.is_dir()), None)


# ---- 1. system -----------------------------------------------------------------------------

CREDENTIALS_REMOVED = '[credentials removed]'
# Where a proxy entry's address starts: after a WinINET 'https=' and a 'scheme://', both optional.
_PROXY_ENTRY_START = re.compile(r'(?i)(?:(?:https?|ftp|socks|gopher)=)?(?:[a-z][a-z0-9+.-]{0,20}://)?')
# A host[:port][/path] address with no user name or password in it.
_PROXY_HOST = re.compile(r'(?:\[[0-9A-Fa-f:.]*\]|[^\s:@/]*)(?::[0-9]*)?(?:/[^\s@]*)?')


def _without_userinfo(entry):
    """One proxy entry without its user name and password: everything from the address start to its LAST '@'
    goes, with or without a scheme (urllib accepts 'user:password@host:port'; a password may hold '@')."""
    if '@' not in entry:
        return entry
    return entry[:_PROXY_ENTRY_START.match(entry).end()] + CREDENTIALS_REMOVED + entry[entry.rindex('@'):]


def _proxy_text(value, limit=200, *, listed=False):
    """A proxy setting for the report, never its credentials.

    A listed setting (WinINET ProxyServer or ProxyOverride, NO_PROXY) is cleaned entry by entry (';', ',' and
    spaces separate entries); any other setting is one address, so a separator inside a password cannot split
    it. If a listed entry before an '@' is no plain host[:port], a password held a separator: then the whole
    setting is cleaned as one address."""
    if not value:
        return '(not set)'
    text = str(value)
    if listed:
        parts = re.split(r'([;,\s]+)', text)
        entries = parts[0::2]
        last = max((index for index, entry in enumerate(entries) if '@' in entry), default=-1)
        if not any('@' not in entry and not _PROXY_HOST.fullmatch(entry[_PROXY_ENTRY_START.match(entry).end():])
                   for entry in entries[:last]):
            return short(''.join(_without_userinfo(part) if index % 2 == 0 else part for index, part in enumerate(parts)), limit)
    return short(_without_userinfo(text), limit)


def system_section(env, *, winreg=None, run=None, getproxies=None, which=None):
    run, getproxies, which = run or subprocess.run, getproxies or urllib.request.getproxies, which or shutil.which
    lines, findings = [], []
    lines.append(f'Python: {platform.python_version()} {struct.calcsize("P") * 8}-bit ({sys.executable})')
    lines.append(f'Platform: {platform.platform()}')
    winreg = winreg or _winreg()
    if winreg is not None:
        current = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion'
        product, display, build, ubr = (reg_value('HKEY_LOCAL_MACHINE', current, name, winreg)
                                        for name in ('ProductName', 'DisplayVersion', 'CurrentBuild', 'UBR'))
        eleven = str(build).isdigit() and int(build) >= 22000
        version = ' '.join(str(part) for part in (product or '?', display) if part)
        lines.append(f'Windows: {version} build {build or "?"}.{ubr if ubr is not None else "?"}'
                     + (' (Windows 11 build)' if eleven else ''))
    for name in ('USERPROFILE', 'LOCALAPPDATA'):
        value = env.get(name) or ''
        lines.append(f'{name}: {value or "(not set)"} - ASCII only: {"yes" if value.isascii() else "NO"}')
        if value and not value.isascii() and not any(f['key'] == 'profile_non_ascii' for f in findings):
            findings.append({'key': 'profile_non_ascii'})
    # The App quotes the Isaac engine command for & | < > ^ ( ) and refuses % and " (engine_path_unsupported).
    profile = (env.get('USERPROFILE') or '') + (env.get('LOCALAPPDATA') or '')
    unsupported, special = [c for c in '%"' if c in profile], [c for c in '&|<>^()' if c in profile]
    if unsupported:
        findings.append({'key': 'profile_unsupported_chars', 'chars': unsupported})
    elif special:
        findings.append({'key': 'profile_special_chars', 'chars': special})
    if winreg is not None:
        long_paths = reg_value('HKEY_LOCAL_MACHINE', r'SYSTEM\CurrentControlSet\Control\FileSystem', 'LongPathsEnabled', winreg)
        lines.append(f'LongPathsEnabled: {long_paths if long_paths is not None else "(not set)"}')
        if long_paths != 1:
            findings.append({'key': 'long_paths_disabled'})
    upper = {key.upper(): value for key, value in env.items()}
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'):
        lines.append(f'env {name}: {_proxy_text(upper.get(name), listed=name == "NO_PROXY")}')
    pac = None
    if winreg is not None:
        internet = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        enable, server, override, pac = (reg_value('HKEY_CURRENT_USER', internet, name, winreg)
                                         for name in ('ProxyEnable', 'ProxyServer', 'ProxyOverride', 'AutoConfigURL'))
        lines.append(f'WinINET ProxyEnable: {enable if enable is not None else "(not set)"}; '
                     f'ProxyServer: {_proxy_text(server, listed=True)}; ProxyOverride: {_proxy_text(override, listed=True)}; '
                     f'AutoConfigURL: {_proxy_text(pac)}')
    try:
        used = getproxies()
        lines.append('Python urllib uses: ' + (', '.join(f'{k}={_proxy_text(v, 120, listed=k == "no")}'
                                                         for k, v in sorted(used.items())) or 'no proxy'))
    except Exception as error:
        used = None
        lines.append(f'Python urllib proxies: unknown ({type(error).__name__})')
    if used is not None:
        # Only what urllib really uses counts: Python (so TwinPulse too) reads no PAC file (AutoConfigURL)
        # and no WPAD, and sends an https request through a proxy only for an 'https' entry.
        routed = [scheme for scheme in ('http', 'https') if used.get(scheme)]
        if routed:
            findings.append({'key': 'proxy_configured', 'schemes': routed})
        elif pac:
            findings.append({'key': 'proxy_pac_only'})
    powershell = which('powershell') or which('powershell.exe')
    if not powershell:
        lines.append('PowerShell execution policy: powershell not found')
    else:
        try:
            done = run([powershell, '-NoProfile', '-NonInteractive', '-Command', 'Get-ExecutionPolicy -List'],
                       capture_output=True, text=True, errors='replace', timeout=30)
            output = [line.rstrip() for line in (done.stdout or '').splitlines() if line.strip()]
            lines.append('PowerShell execution policy (Get-ExecutionPolicy -List):')
            lines += ['  ' + short(line, 120) for line in output[:12]]
            policy = dict(re.findall(r'^\s*(MachinePolicy|UserPolicy)\s+(\w+)\s*$', '\n'.join(output), re.M))
            if any(value in ('Restricted', 'AllSigned') for value in policy.values()):
                findings.append({'key': 'ps_policy_restricted', 'policy': policy})
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            lines.append(f'PowerShell execution policy: not read ({type(error).__name__})')
    return section(lines, findings)


# ---- 2. Isaac Sim --------------------------------------------------------------------------

def _version_text(path):
    try:
        if not path.is_file() or path.stat().st_size > 1024:
            return None
        text = path.read_bytes().decode('utf-8-sig', 'replace').strip().splitlines()
        return short(text[0], 120) if text else ''
    except OSError:
        return None


def kit_matches(path, limit=80):
    """First and last limit/2 matching lines (redacted), the match count and registry-sync hits."""
    head, tail, total, registry = [], deque(maxlen=limit // 2), 0, 0
    with open(path, 'rb') as stream:
        for raw in iter(lambda: stream.readline(65536), b''):
            try:
                line = raw.decode('utf-8')
            except UnicodeDecodeError:
                line = raw.decode('cp949', 'replace')
            if not KIT_PATTERN.search(line):
                continue
            total += 1
            registry += bool(REGISTRY_PATTERN.search(line))
            if len(head) < limit - limit // 2:
                head.append(short(line, 300))
            else:
                tail.append(short(line, 300))
    return {'head': head, 'tail': list(tail), 'total': total, 'registry': registry}


def _kit_logs(folder):
    try:
        return [path for path in folder.rglob('kit_*.log') if path.is_file()] if folder.is_dir() else []
    except OSError:
        return []


# Run inside Isaac's python.bat; the code travels in an environment variable so
# no quote or newline has to pass through cmd.exe.
ISAAC_PYTHON_PROBE = (
    "import json, site, sys\n"
    "out = {'python': sys.version.split()[0], 'user_site': site.ENABLE_USER_SITE,\n"
    "       'user_site_path': site.getusersitepackages(), 'modules': {}}\n"
    "for name in ('numpy', 'PIL'):\n"
    "    try:\n"
    "        module = __import__(name)\n"
    "        out['modules'][name] = {'version': str(getattr(module, '__version__', '')), 'file': str(module.__file__)}\n"
    "    except Exception as error:\n"
    "        out['modules'][name] = {'error': type(error).__name__}\n"
    "print('TWINPULSE_PROBE=' + json.dumps(out))\n")


PROBE_KILL_WAIT = 10  # seconds to collect a probe's output after its process tree was ended


def kill_tree(process, *, windows=None, run=None):
    """End a timed-out probe and every process it started. python.bat is cmd.exe, and its child python.exe holds
    the output pipes, so ending cmd.exe alone would leave the probe running and its pipes open."""
    windows = os.name == 'nt' if windows is None else windows
    if windows:
        taskkill = Path(os.environ.get('SystemRoot') or r'C:\Windows') / 'System32' / 'taskkill.exe'
        try:
            (run or subprocess.run)([str(taskkill), '/T', '/F', '/PID', str(process.pid)], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        process.kill()  # elsewhere the only step; on Windows the fallback when taskkill could not run
    except OSError:
        pass


def _run_bounded(command, *, popen, kill, timeout, **options):
    """(exit code, stdout) of one run, which never waits longer than timeout plus PROBE_KILL_WAIT:
    on timeout the whole process tree is ended and TimeoutExpired is raised."""
    process = popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, errors='replace', **options)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill(process)
        try:
            process.communicate(timeout=PROBE_KILL_WAIT)
        except subprocess.TimeoutExpired:
            pass  # something still holds the pipe: give up on it, the report comes first
        raise subprocess.TimeoutExpired(command, timeout) from None
    return process.returncode, stdout


def isaac_python_probe(root, env, *, popen=None, kill=None, timeout=90):
    """Import numpy and PIL in Isaac's own Python twice: as a plain python.bat start and as
    TwinPulse starts the engine (PYTHONNOUSERSITE=1, no PYTHONHOME/PYTHONPATH). Read-only (-B).
    stdin is empty, and a run that hangs is ended with all its children after timeout seconds."""
    popen, kill = popen or subprocess.Popen, kill or kill_tree
    results = {}
    for mode, extra in (('default', {}), ('twinpulse', {'PYTHONNOUSERSITE': '1'})):
        child = {key: value for key, value in env.items() if key.upper() not in {'PYTHONHOME', 'PYTHONPATH', 'PYTHONNOUSERSITE'}}
        child.update(extra, TWINPULSE_PROBE_CODE=ISAAC_PYTHON_PROBE)
        try:
            code, stdout = _run_bounded([str(Path(root) / 'python.bat'), '-B', '-c', "import os; exec(os.environ['TWINPULSE_PROBE_CODE'])"],
                                        popen=popen, kill=kill, timeout=timeout, env=child, cwd=str(root))
            found = [line[len('TWINPULSE_PROBE='):] for line in (stdout or '').splitlines() if line.startswith('TWINPULSE_PROBE=')]
            value = json.loads(found[-1]) if found else None
            results[mode] = value if isinstance(value, dict) else {'failed': f'exit {code}, no probe line'}
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            results[mode] = {'failed': type(error).__name__}
    return results


def _under(path, folder):
    """True when path is inside folder; Windows spelling, so case and slashes do not matter."""
    def norm(value):
        return str(value).replace('\\', '/').rstrip('/').casefold()
    return bool(path and folder) and norm(path).startswith(norm(folder) + '/')


def _probe_part(results):
    """Report lines and findings for isaac_python_probe."""
    lines, findings = [], []
    default, engine = results.get('default') or {}, results.get('twinpulse') or {}
    for mode, label in (('default', 'plain python.bat'), ('twinpulse', 'as TwinPulse starts it (PYTHONNOUSERSITE=1)')):
        value = results.get(mode) or {}
        if 'failed' in value:
            lines.append(f'Isaac Python probe, {label}: not run ({short(value["failed"], 120)})')
            continue
        modules = value.get('modules') if isinstance(value.get('modules'), dict) else {}
        shown = '; '.join(f'{name} ' + (f'{short(item.get("version"), 40)} at {short(item.get("file"), 200)}' if 'file' in item
                          else f'not importable ({short(item.get("error"), 60)})') for name, item in modules.items() if isinstance(item, dict))
        lines.append(f'Isaac Python probe, {label}: Python {short(value.get("python"), 20)}, user site {value.get("user_site")}: {shown}')
    if 'failed' in default or 'failed' in engine:
        return lines, findings
    user_site = default.get('user_site_path')
    shadowed, needs = [], []
    for name, item in (default.get('modules') or {}).items():
        other = (engine.get('modules') or {}).get(name) or {}
        if 'file' in item and _under(item['file'], user_site):
            (shadowed if 'file' in other else needs).append(name)
        elif 'file' not in item and 'file' in other:
            shadowed.append(name)  # the user folder breaks the import; TwinPulse starts without it
    if shadowed:
        findings.append({'key': 'isaac_user_site_shadow', 'modules': shadowed})
    if needs:
        findings.append({'key': 'isaac_needs_user_site', 'modules': needs})
    return lines, findings


def isaac_section(env, roots=(), *, candidates=ISAAC_CANDIDATES, max_logs=3, max_lines=80, popen=None):
    lines, findings, seen, valid = [], [], set(), []
    for label, root in [*roots, *(('default list', item) for item in candidates)]:
        key = os.path.normcase(os.path.normpath(str(root))).rstrip('\\/')
        if key in seen:
            continue
        seen.add(key)
        path = Path(root)
        if not path.is_dir():
            lines.append(f'{root} ({label}): not found')
            continue
        python_bat, sim_bat, version = (path / 'python.bat').is_file(), (path / 'isaac-sim.bat').is_file(), _version_text(path / 'VERSION')
        lines.append(f'{root} ({label}): python.bat {"yes" if python_bat else "NO"}, isaac-sim.bat {"yes" if sim_bat else "NO"}, '
                     f'VERSION {version or "(none)"}' + (' (reviewed build)' if version == REVIEWED_ISAAC_VERSION else ''))
        if python_bat:
            valid.append((path, version))
    if not valid:
        findings.append({'key': 'isaac_missing'})
    else:
        findings.append({'key': 'isaac_found', 'root': str(valid[0][0]), 'version': valid[0][1]})
        for root, version in valid:
            if version and not re.match(r'6\.0\.1(?![0-9])', version):
                findings.append({'key': 'isaac_version_other', 'root': str(root), 'version': version})
        for name in ('PYTHONHOME', 'PYTHONPATH'):
            if env.get(name):
                lines.append(f'env {name} is set ({short(env[name], 120)}); TwinPulse removes it for Isaac')
        probe_lines, probe_findings = _probe_part(isaac_python_probe(valid[0][0], env, popen=popen))
        lines += probe_lines
        findings += probe_findings
    logs = [log for root, _ in valid for log in _kit_logs(root / 'kit' / 'logs' / 'Kit')]
    if env.get('USERPROFILE'):
        logs += _kit_logs(Path(env['USERPROFILE']) / '.nvidia-omniverse' / 'logs' / 'Kit')
    logs = list({os.path.normcase(str(log)): log for log in logs}.values())
    if not logs:
        lines.append('Kit logs: none found')
    registry_log = None
    for log in newest(logs, max_logs):
        try:
            found = kit_matches(log, max_lines)
        except OSError as error:
            lines.append(f'Kit log {log}: not read ({type(error).__name__})')
            continue
        shown = len(found['head']) + len(found['tail'])
        lines.append(f'Kit log {log} ({_size(log)} bytes, modified {local_time(_mtime(log))}): {found["total"]} matching lines'
                     + (f', showing first {len(found["head"])} and last {len(found["tail"])}' if found['total'] > shown else ''))
        lines += ['  ' + line for line in found['head']] + (['  ...'] if found['tail'] else []) + ['  ' + line for line in found['tail']]
        if found['registry'] and registry_log is None:
            registry_log = log
    if registry_log is not None:
        findings.append({'key': 'kit_registry_sync', 'when': local_time(_mtime(registry_log))})
    return section(lines, findings)


def _size(path):
    try:
        return path.stat().st_size
    except OSError:
        return None


# ---- 3. TwinPulse install ------------------------------------------------------------------

def classify_burger(inventory):
    """Compare {relative name: sha256} with both reviewed pin sets, file by file (file set and digests only)."""
    files = {}
    for name in PUBLIC_BURGER_MANIFEST:
        digest = inventory.get(name)
        files[name] = ('missing' if digest is None else 'public' if digest == PUBLIC_BURGER_MANIFEST[name]
                       else 'original' if digest == BURGER_MANIFEST[name] else 'neither')
    extra, states = sorted(set(inventory) - set(PUBLIC_BURGER_MANIFEST)), set(files.values())
    overall = ('missing' if states == {'missing'} else 'closure_changed' if extra or 'missing' in states
               else 'public' if states == {'public'} else 'original' if states == {'original'}
               else 'mismatch' if 'neither' in states else 'mixed')
    return {'overall': overall, 'files': files, 'extra': extra}


BURGER_SIZE_LIMIT = 32 * 1024 * 1024  # simulation_assets._inventory refuses a larger file


def _linked(path, inside):
    try:
        return path.is_symlink() or not path.resolve().is_relative_to(inside)
    except (OSError, RuntimeError):  # a link loop or an unreadable reparse point
        return True


def burger_folder(folder):
    """One usd folder through the steps of simulation_assets._inventory, in its order and with its codes:
    main file, links (symlinks, junctions), file set, size, digests. Explorer/Finder metadata (OS_JUNK
    names) is ignored at every step, as the App ignores it. A link is never followed and a file over
    the size limit is never hashed; neither is ever read by the App."""
    folder = Path(folder)
    every = sorted(folder.rglob('*'))
    ignored = [path.relative_to(folder).as_posix() for path in every if path.name.casefold() in OS_JUNK]
    paths = [path for path in every if path.name.casefold() not in OS_JUNK]
    inside, folder_linked = folder.resolve(), folder.is_symlink()
    linked = (['(this folder)'] if folder_linked else []) + [
        path.relative_to(folder).as_posix() for path in paths if _linked(path, inside)]
    files = {path.relative_to(folder).as_posix(): path for path in paths if path.is_file()}
    behind_link = set(files) if folder_linked else set(linked)
    oversized = [name for name, path in files.items() if name not in behind_link and path.stat().st_size > BURGER_SIZE_LIMIT]
    inventory = {name: sha256_file(path) for name, path in files.items() if name not in behind_link and name not in oversized}
    entry = {'inventory': inventory, **classify_burger(inventory), 'linked': linked, 'oversized': oversized, 'ignored': ignored}
    entry['extra'] = sorted(set(files) - set(PUBLIC_BURGER_MANIFEST))
    entry['files'].update({name: 'linked' for name in behind_link if name in entry['files']})
    entry['files'].update({name: 'oversized' for name in oversized if name in entry['files']})
    if not (folder / 'turtlebot3_burger.usda').is_file():
        code = 'SIM_BURGER_ASSET_MISSING'
    elif linked:
        code = 'SIM_ASSET_DEPENDENCY_UNSAFE'
    elif set(files) != set(PUBLIC_BURGER_MANIFEST):
        code = 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'
    elif oversized:
        code = 'SIM_BURGER_ASSET_SIZE_LIMIT'
    elif inventory not in (BURGER_MANIFEST, PUBLIC_BURGER_MANIFEST):
        code = 'SIM_BURGER_ASSET_DIGEST_MISMATCH'
    else:
        code = None
    states = set(entry['files'].values())
    entry['overall'] = {'SIM_BURGER_ASSET_MISSING': 'missing' if states == {'missing'} else 'closure_changed',
                        'SIM_ASSET_DEPENDENCY_UNSAFE': 'linked', 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED': 'closure_changed',
                        'SIM_BURGER_ASSET_SIZE_LIMIT': 'oversized',
                        'SIM_BURGER_ASSET_DIGEST_MISMATCH': 'mismatch' if 'neither' in states else 'mixed'}.get(code, entry['overall'])
    entry['code'] = code
    return entry


def burger_check(resource_root, manifest_hashes=None, prefix=''):
    """The Burger folders of one release, in the order TwinPulse picks them at run time."""
    result = {'used': None, 'folders': []}
    for relative in BURGER_FOLDERS:
        folder = Path(resource_root) / relative
        if not folder.is_dir():
            continue
        entry = {'folder': relative, **burger_folder(folder)}
        if manifest_hashes is not None:
            recorded = {}
            for name in PUBLIC_BURGER_MANIFEST:
                key = (prefix + relative + '/' + name).casefold()
                if key in manifest_hashes:
                    recorded[name] = manifest_hashes[key]
            entry['recorded'] = classify_burger(recorded)['overall'] if recorded else None
        result['used'] = result['used'] or relative
        result['folders'].append(entry)
    return result


def _extra_kind(relative):
    name, parts = relative.rsplit('/', 1)[-1].casefold(), relative.casefold().split('/')
    if name in OS_JUNK:
        return 'os_junk'
    if '__pycache__' in parts or name.endswith(('.pyc', '.pyo')):
        return 'bytecode'
    return 'backup' if BACKUP_PATTERN.search(name) else 'other'


def compare_manifest(root, entries, *, manifest_name, kind, hash_files=True, max_path=None):
    """Missing, changed (size or SHA-256), unreadable and extra files of a release folder against its manifest.

    A file that cannot be read is never called changed: a path over MAX_PATH without long path support, access
    denied or an antivirus lock is not a hand patch.
    """
    root, listed, invalid = Path(root), {}, 0
    max_path = max_path or (259 if os.name == 'nt' else None)
    for entry in entries if isinstance(entries, list) else []:
        name = entry.get('path') if isinstance(entry, dict) else None
        if (not isinstance(name, str) or not name or '\\' in name or ':' in name or name.startswith('/')
                or any(part in ('', '.', '..') for part in name.split('/'))):
            invalid += 1
            continue
        listed[name.casefold()] = entry
    missing, changed, unreadable = [], [], []
    for entry in listed.values():
        path = root / entry['path']
        try:
            if not path.is_file():
                too_long = max_path is not None and len(os.path.abspath(path)) > max_path
                (unreadable if too_long else missing).append(entry['path'])
            elif path.stat().st_size != entry.get('bytes') or (
                    hash_files and sha256_file(path) != str(entry.get('sha256', '')).lower()):
                changed.append(entry['path'])
        except OSError:
            unreadable.append(entry['path'])
    extra, venv = {'other': [], 'backup': [], 'bytecode': [], 'os_junk': []}, False
    for directory, folders, files in os.walk(root):
        relative = Path(directory).relative_to(root).as_posix()
        if relative == '.' and kind == 'offline' and '.venv' in folders:
            folders.remove('.venv')  # created by the offline installer, not part of the release
            venv = True
        for name in files:
            path = name if relative == '.' else relative + '/' + name
            if path != manifest_name and path.casefold() not in listed:
                group = _extra_kind(path)
                # The EXE start check refuses every unlisted file but Explorer metadata, bytecode included.
                extra['other' if kind == 'exe' and group == 'bytecode' else group].append(path)
    return {'listed': len(listed), 'invalid_entries': invalid, 'missing': sorted(missing), 'changed': sorted(changed),
            'unreadable': sorted(unreadable), 'extra': {key: sorted(value) for key, value in extra.items()}, 'venv': venv}


def release_report(folder, *, verify=True):
    folder = Path(folder)
    exe, exe_info = read_json(folder / 'windows-release-manifest.json')
    offline, offline_info = read_json(folder / 'release-manifest.json')
    if exe_info['exists']:
        kind, manifest, info, name, resources, prefix = ('exe', exe, exe_info, 'windows-release-manifest.json',
                                                         folder / '_internal' / 'resources', '_internal/resources/')
    elif offline_info['exists']:
        kind, manifest, info, name, resources, prefix = 'offline', offline, offline_info, 'release-manifest.json', folder, ''
    else:
        return {'name': folder.name, 'kind': 'unknown', 'burger': burger_check(folder)}
    report = {'name': folder.name, 'kind': kind, 'manifest': name, 'manifest_bom': info['bom'], 'manifest_error': info['error']}
    hashes = None
    if isinstance(manifest, dict):
        for key in ('schema', 'release_id', 'build_id', 'product_version', 'release_version', 'git_revision', 'dirty', 'channel'):
            if isinstance(manifest.get(key), (str, int, float, bool)):
                report[key] = ident(manifest[key])
        entries = manifest.get('files')
        report['listed'] = len(entries) if isinstance(entries, list) else None
        if isinstance(entries, list):
            hashes = {entry['path'].casefold(): str(entry.get('sha256', '')).lower() for entry in entries
                      if isinstance(entry, dict) and isinstance(entry.get('path'), str)}
            if verify:
                report['compare'] = compare_manifest(folder, entries, manifest_name=name, kind=kind)
    report['burger'] = burger_check(resources, hashes, prefix)
    return report


def _release_lines(report, active):
    head = f"Release {report['name']}" + (' [ACTIVE]' if active else '') + f": {report['kind']}"
    if report['kind'] == 'unknown':
        return [head + ' (no release manifest)']
    details = [f"{key}={report[key]}" for key in ('schema', 'release_id', 'build_id', 'product_version', 'git_revision', 'dirty', 'channel')
               if key in report]
    lines = [head + f", {report['manifest']} BOM {'YES' if report['manifest_bom'] else 'no'}"
             + (f", unreadable ({report['manifest_error']})" if report['manifest_error'] else '')
             + (', files listed ' + str(report['listed']) if report.get('listed') is not None else ''), '  ' + ' '.join(details)]
    compare = report.get('compare')
    if compare is None:
        lines.append('  Files vs manifest: not checked (' + ('the manifest has no readable file list)' if report.get('listed') is None
                                                         else 'only the active and newest releases are hashed)'))
    else:
        extra = compare['extra']
        lines.append(f"  Files vs manifest: {len(compare['changed'])} changed, {len(compare['missing'])} missing, "
                     + (f"{len(compare['unreadable'])} unreadable, " if compare['unreadable'] else '')
                     + f"{len(extra['other']) + len(extra['backup'])} extra; ignored: {len(extra['bytecode'])} bytecode cache, "
                     f"{len(extra['os_junk'])} Windows metadata" + (', .venv (made by the offline installer)' if compare['venv'] else ''))
        for label, items in (('changed', compare['changed']), ('missing', compare['missing']),
                             ('unreadable (path over 259 chars, access denied or locked)', compare['unreadable']),
                             ('extra', extra['other']), ('backup copies', extra['backup'])):
            if items:
                lines.append(f'    {label}: {names(items)}')
    burger = report['burger']
    if burger['used'] is None:
        lines.append('  Burger asset: no Burger folder in this release')
    for entry in burger['folders']:
        used = ' (used at run time)' if entry['folder'] == burger['used'] else ' (not used: the folder above wins)'
        lines.append(f"  Burger asset {entry['folder']}{used}: {entry['overall']}"
                     + (f" (all {len(entry['files'])} files)" if entry['overall'] in ('public', 'original') else '')
                     + (f" -> {entry['code']}" if entry['code'] and entry['folder'] == burger['used'] else '')
                     + (f"; manifest-recorded hashes: {entry['recorded']}" if entry.get('recorded') else ''))
        for name, state in entry['files'].items() if entry['overall'] not in ('public', 'original') else ():
            digest = entry['inventory'].get(name)
            lines.append(f'    {name}: {state}' + (f' sha256={digest}' if state == 'neither' else ''))
        for label, items in (('extra files', entry['extra']), ('links (never followed)', entry['linked']),
                             (f'over {BURGER_SIZE_LIMIT // (1024 * 1024)} MB (not hashed)', entry['oversized']),
                             ('ignored Explorer/Finder metadata', entry['ignored'])):
            if items:
                lines.append(f'    {label}: {names(items)}')
    return lines


def install_section(local_app_data, *, max_verify=3):
    installed = Path(local_app_data) / 'TwinPulse' / 'installed'
    lines, findings, facts = [f'Install folder: {installed}'], [], {}
    if not installed.is_dir():
        lines.append('  not found')
        findings.append({'key': 'not_installed'})
        return section(lines, findings, facts)
    pointer, info = read_json(installed / 'active-release.json')
    active = None
    if not info['exists']:
        lines.append('active-release.json: missing')
    else:
        lines.append(f"active-release.json: {info['bytes']} bytes, BOM {'YES' if info['bom'] else 'no'}, "
                     + ('parsed (read as utf-8-sig)' if info['error'] is None else 'not parsed: ' + info['error']))
        if info['bom']:
            findings.append({'key': 'pointer_bom'})
        if info['error']:
            findings.append({'key': 'pointer_unreadable', 'error': info['error']})
    if isinstance(pointer, dict):
        active = pointer.get('release_id') if isinstance(pointer.get('release_id'), str) else None
        pointer_kind = 'exe' if pointer.get('schema') == 'twinpulse-windows-install-1.0' else 'offline'
        lines.append(f'  release_id {ident(active)}, pointer type {pointer_kind}'
                     + (f", isaac_root {pointer['isaac_root']}" if isinstance(pointer.get('isaac_root'), str) else ''))
        if isinstance(pointer.get('isaac_root'), str):
            facts['pointer_isaac_root'] = pointer['isaac_root']
    previous = sorted(path.name for path in installed.glob('active-release.previous*.json'))
    if previous:
        lines.append('Older pointers kept: ' + names(previous, 10))
    entries = [name for name in ('Start-TwinPulse.cmd', 'Start-TwinPulse-Test.cmd', 'start-installed.ps1',
                                 'scripts/start_twinpulse_installed.ps1') if (installed / name).is_file()]
    lines.append('Start entries: ' + (', '.join(entries) or 'none'))
    journals = installed / 'update-journals'
    if journals.is_dir():
        lines.append(f'Update journals: {len(list(journals.glob("*.json")))}')
    store = installed / 'releases'
    folders = [path for path in store.iterdir() if path.is_dir()] if store.is_dir() else []
    leftovers = [path for path in folders if path.name.startswith(('.stage-', '.install-'))]
    releases = newest([path for path in folders if path not in leftovers], 100)
    lines.append(f'Releases ({len(releases)}): ' + (names(f'{path.name} ({local_time(_mtime(path))})' for path in releases) or 'none'))
    if leftovers:
        lines.append('Interrupted install folders: ' + names(path.name for path in leftovers))
        findings.append({'key': 'staging_leftovers', 'count': len(leftovers)})
    if active and not (store / active).is_dir():
        findings.append({'key': 'active_release_missing', 'release': active})
    ordered = [path for path in releases if path.name == active] + [path for path in releases if path.name != active]
    for index, folder in enumerate(ordered):
        try:
            _release_findings(folder, folder.name == active, index < max_verify, lines, findings, facts)
        except Exception as error:  # one unreadable release must not hide the others
            lines.append(f'Release {folder.name}: check failed ({type(error).__name__}: {short(error, 160)})')
    return section(lines, findings, facts)


def _release_findings(folder, active, verify, lines, findings, facts):
    report = release_report(folder, verify=verify)
    lines += _release_lines(report, active)
    if active and report['kind'] == 'exe' and report.get('product_version'):
        facts['product_version'] = report['product_version']
    if active and report['kind'] == 'offline':
        findings.append({'key': 'offline_active', 'release': folder.name})
    if verify and report['kind'] != 'unknown' and report.get('listed') is None:
        findings.append({'key': 'release_manifest_unreadable', 'release': folder.name})
    compare = report.get('compare')
    if compare:
        other, backup = compare['extra']['other'], compare['extra']['backup']
        refused = other + backup if report['kind'] == 'exe' else other  # the EXE start check refuses a backup copy too
        if compare['changed'] or compare['missing'] or refused:
            findings.append({'key': 'release_modified', 'release': folder.name, 'kind': report['kind'], 'changed': compare['changed'],
                             'missing': compare['missing'], 'extra': refused})
        if compare['unreadable']:
            findings.append({'key': 'release_unreadable', 'release': folder.name, 'files': compare['unreadable']})
        if backup:
            findings.append({'key': 'release_backups', 'release': folder.name, 'files': backup})
        if not (compare['changed'] or compare['missing'] or compare['unreadable'] or other or backup):
            findings.append({'key': 'release_clean', 'release': folder.name})
    if verify and report['kind'] != 'unknown':
        state, code, files = burger_verdict(report['burger'])
        if code:
            findings.append({'key': 'burger_' + state, 'release': folder.name, 'files': files, 'code': code})


def burger_verdict(burger):
    """(state, the App's refusal code or None, files to name) for the Burger folder TwinPulse uses at run time.
    With no folder at all, simulation_assets._inventory finds no main file either."""
    used = next((entry for entry in burger['folders'] if entry['folder'] == burger['used']), None)
    if used is None:
        return 'missing', 'SIM_BURGER_ASSET_MISSING', []
    state = used['overall']
    files = {'linked': used['linked'], 'oversized': used['oversized']}.get(
        state, [name for name, value in used['files'].items() if value not in ('public', 'original')])
    return state, used['code'], files


# ---- 4. runtime state ----------------------------------------------------------------------

def _host(url):
    if not isinstance(url, str):
        return '?'
    try:
        return urllib.parse.urlsplit(url).hostname or '?'
    except ValueError:
        return '?'


def _models(settings):
    models = [settings.get(key) for key in ('model_id', 'observer_model_id', 'fallback_observer_model_id')]
    return ', '.join(ident(model, MODEL) for model in models if isinstance(model, str) and model) or '-'


def provider_lines(runtime):
    """Provider names, base URL hosts and model ids only: never keys or credential targets."""
    lines, labels = [], {'legacy': 'legacy key (provider_settings.json)'}
    value, info = read_json(runtime / 'provider_settings.json', 1024 * 1024)
    if isinstance(value, dict):
        lines.append(f"provider_settings.json: profile {ident(value.get('provider_profile'))}, host {_host(value.get('base_url'))}, "
                     f"models {_models(value)}")
    elif info['exists']:
        lines.append(f"provider_settings.json: not parsed ({info['error']})")
    keys, info = read_json(runtime / 'provider_keys.json', 1024 * 1024)
    if isinstance(keys, dict) and isinstance(keys.get('entries'), list):
        for entry in keys['entries'][:32]:
            if not isinstance(entry, dict):
                continue
            settings = entry.get('settings') if isinstance(entry.get('settings'), dict) else {}
            label = short(entry.get('name', '?'), 80)
            labels[str(entry.get('id'))] = f"{label} ({ident(settings.get('provider_profile'))})"
            lines.append(f"provider key entry: {label}, profile {ident(settings.get('provider_profile'))}, "
                         f"host {_host(settings.get('base_url'))}, models {_models(settings)}")
    elif info['exists']:
        lines.append(f"provider_keys.json: not parsed ({info['error'] or 'unexpected shape'})")
    routing, info = read_json(runtime / 'provider_stage_routing.json', 1024 * 1024)
    route = routing.get('route') if isinstance(routing, dict) else None
    if isinstance(route, dict):
        for stage in ('observer', 'planner'):
            choice = route.get(stage)
            if isinstance(choice, dict):
                cap = choice.get('max_output_tokens')
                lines.append(f"stage {stage}: {labels.get(str(choice.get('key_id')), 'unknown key entry')}, model {ident(choice.get('model_id'), MODEL)}"
                             + (f', max_output_tokens {cap}' if type(cap) is int else ''))
    elif info['exists']:
        lines.append(f"provider_stage_routing.json: not parsed ({info['error'] or 'unexpected shape'})")
    return lines or ['Provider settings: none saved']


def _scalars(value, keys):
    """Numbers, booleans and identifier-shaped strings only."""
    value = value if isinstance(value, dict) else {}
    result = {}
    for key in keys:
        item = value.get(key)
        if isinstance(item, float):
            result[key] = round(item, 1)
        elif isinstance(item, (bool, int)) or (isinstance(item, str) and re.fullmatch(IDENT, item)):
            result[key] = item
    return result


def launch_report(folder):
    status, _ = read_json(folder / 'supervisor-status.json', 4 * 1024 * 1024)
    result, _ = read_json(folder / 'engine-result.json', 16 * 1024 * 1024)
    exits, _ = read_json(folder / 'owned-exit-observations.json', 1024 * 1024)
    progress, _ = read_json(folder / 'engine-progress.json', 1024 * 1024)
    report = {'name': folder.name, 'modified': _mtime(folder), 'engine_log': _size(folder / 'engine.log'),
              'backend_log': _size(folder / 'backend.log'), 'stop_request': (folder / 'engine-stop.request').exists()}
    if isinstance(status, dict):
        engine = status.get('engine') if isinstance(status.get('engine'), dict) else {}
        browser = status.get('browser') if isinstance(status.get('browser'), dict) else {}
        started, updated = parse_utc(status.get('started_at_utc')), parse_utc(status.get('updated_at_utc'))
        report['status'] = {'status': ident(status.get('status')), 'phase': ident(status.get('phase')),
                            'message': short(status.get('message') or '', 240), 'engine': ident(engine.get('state')),
                            'browser_launched': browser.get('launched') is True, 'started': show_utc(status.get('started_at_utc')),
                            'seconds': round((updated - started).total_seconds()) if started and updated else None,
                            'timeout': status.get('ready_timeout_s') if isinstance(status.get('ready_timeout_s'), (int, float)) else None}
    if isinstance(result, dict):
        error = result.get('error') if isinstance(result.get('error'), str) else ''
        report['result'] = {'status': ident(result.get('status')), 'phase': ident(result.get('startup_phase')),
                            'code': ident(result.get('error_type')), 'message': short(error.splitlines()[0] if error else '', 200),
                            'bridge': _scalars(result.get('bridge_diagnostic'), ('error_type', 'http_status', 'error_code'))}
    roles = exits.get('roles') if isinstance(exits, dict) and isinstance(exits.get('roles'), dict) else {}
    if isinstance(roles.get('engine'), dict):
        report['engine_exit'] = _scalars(roles['engine'], ('pid', 'root_disposition', 'return_code', 'elapsed_s'))
    if isinstance(progress, dict):
        report['progress'] = _scalars(progress, ('phase', 'elapsed_s'))
    return report


def _launch_lines(report):
    lines = [f"- {ident(report['name'])} (folder modified {local_time(report['modified'])})"]
    status = report.get('status')
    if status:
        lines.append(f"  supervisor-status: {status['status']} / {status['phase']}: \"{status['message']}\"; engine {status['engine']}, "
                     f"window/browser opened {'yes' if status['browser_launched'] else 'no'}, started {status['started'] or '?'}"
                     + (f", last update after {status['seconds']} s" if status['seconds'] is not None else '')
                     + (f", ready timeout {status['timeout']:g} s" if status['timeout'] is not None else ''))
    else:
        lines.append('  supervisor-status: none')
    logs = [f'{name} ' + (f'{size} bytes' if size is not None else 'missing')
            for name, size in (('engine.log', report['engine_log']), ('backend.log', report['backend_log']))]
    lines.append('  ' + ', '.join(logs) + (', engine-stop.request present' if report['stop_request'] else ''))
    result = report.get('result')
    if result:
        lines.append(f"  engine-result: {result['status']}, phase {result['phase']}, type {result['code']}"
                     + (f", \"{result['message']}\"" if result['message'] else '')
                     + (f", bridge {result['bridge']}" if result['bridge'] else ''))
    if report.get('engine_exit'):
        exit_ = report['engine_exit']
        lines.append(f"  owned engine exit: pid {exit_.get('pid', '?')}, {exit_.get('root_disposition', '?')}, return code "
                     f"{exit_.get('return_code', '?')}, stop wait {exit_.get('elapsed_s', '?')} s (time spent stopping, not run time)")
    if report.get('progress'):
        lines.append(f"  engine-progress: phase {report['progress'].get('phase', '?')} at {report['progress'].get('elapsed_s', '?')} s")
    return lines


def _launch_findings(reports):
    found = {}
    for report in reports:  # newest first: keep the newest of each kind, count the rest
        status = report.get('status') or {}
        when = status.get('started') or local_time(report['modified'])
        keys = []
        message = (status.get('message') or '').lower()
        if 'desktop_host_not_built' in message:
            keys.append(('launch_desktop_host', {}))
        elif status.get('phase') == 'engine_ready_timeout':
            keys.append(('launch_ready_timeout', {'seconds': status.get('seconds'), 'timeout': status.get('timeout')}))
        elif status.get('phase') == 'engine_unresponsive':
            keys.append(('launch_unresponsive', {}))
        elif status.get('status') == 'error':
            keys.append(('launch_error', {'phase': status.get('phase'), 'message': status.get('message')}))
        exit_ = report.get('engine_exit') or {}
        if status.get('engine') == 'not_started' and exit_.get('pid'):
            keys.append(('launch_engine_ran', {'pid': exit_.get('pid')}))
        if report.get('engine_log') == 0 and exit_.get('pid'):
            keys.append(('launch_engine_log_empty', {}))
        for key, data in keys:
            if key in found:
                found[key]['count'] += 1
            else:
                found[key] = {'key': key, 'when': when, 'launch': report['name'], 'count': 1, **data}
    latest = (reports[0].get('status') or {}) if reports else {}
    if reports and latest.get('status') != 'error':  # an error is already named by the lines above
        found['launch_latest'] = {'key': 'launch_latest', 'when': latest.get('started') or local_time(reports[0]['modified']),
                                  'status': latest.get('status', 'no supervisor-status'), 'phase': latest.get('phase', '-')}
    return list(found.values())


def evidence_report(folder, count=10):
    """The newest final provider-evidence records: whitelisted facts only, never request_redacted."""
    folder = Path(folder)
    files = newest([path for path in folder.glob('*.json') if path.is_file()], count) if folder.is_dir() else []
    reports = []
    for path in files:
        record, info = read_json(path, 16 * 1024 * 1024)
        item = {'file': path.name if re.fullmatch(r'[A-Za-z0-9._-]{1,80}', path.name) else '(file)', 'modified': _mtime(path)}
        if not isinstance(record, dict):
            item['error'] = info['error'] or 'not a JSON object'
            reports.append(item)
            continue
        for key in EVIDENCE_FIELDS:
            value = record.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                item[key] = value
            elif isinstance(value, str) and key == 'model_id':
                item[key] = ident(value, MODEL)
            elif isinstance(value, str) and key == 'saved_at':
                item[key] = show_utc(value) or '?'
            elif isinstance(value, str):
                item[key] = short(value, 80)
        typed = record.get('provider_error')
        if isinstance(typed, dict) and typed.get('kind') in ('json_error', 'html_page', 'unparsed'):
            body = {'kind': {'json_error': 'json', 'html_page': 'html', 'unparsed': 'text'}[typed['kind']]}
            for key in ('type', 'code', 'param'):
                if isinstance(typed.get(key), str) and re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{1,80}', typed[key]):
                    body[key] = typed[key]
            if isinstance(typed.get('message'), str):
                body['message'] = short(typed['message'], 300)
            if isinstance(typed.get('title'), str):
                body['title'] = short(typed['title'], 120)
            if type(typed.get('bytes')) is int:
                body['bytes'] = typed['bytes']
        else:
            text = record.get('response_redacted')
            content_type = record.get('content_type') if isinstance(record.get('content_type'), str) else ''
            body = describe_body(text.encode('utf-8', 'replace') if isinstance(text, str) else b'', content_type)
        item['body'] = body
        item['content_type'] = (short(record['content_type'], 80) if isinstance(record.get('content_type'), str)
                                else body['kind'] + ' (from the saved body)')
        reports.append(item)
    return reports


def _evidence_findings(reports):
    findings, seen = [], set()
    for item in reports:
        body, status = item.get('body') or {}, item.get('http_status')
        if body.get('kind') not in ('json', 'html'):
            continue
        # A rejected 2xx JSON answer without error facts is the model's own output, not a provider error body.
        if not (type(status) is int and status >= 400 or item.get('status') == 'rejected' and (body['kind'] == 'html' or len(body) > 1)):
            continue
        signature = (status, body.get('kind'), body.get('type'), body.get('code'), body.get('param'), body.get('title'))
        if signature in seen:
            continue
        seen.add(signature)
        findings.append({'key': 'evidence_' + body['kind'], 'model': item.get('model_id', '?'), 'status': status,
                         'when': item.get('saved_at') or local_time(item['modified']), 'body': body})
    return findings[:3]


def _lock_part(runtime, alive, identity):
    lock, info = read_json(runtime / 'launcher.lock', 1024 * 1024)
    if not info['exists']:
        return ['launcher.lock: none'], []
    if not isinstance(lock, dict):
        return [f"launcher.lock: not parsed ({info['error'] or 'unexpected shape'})"], [{'key': 'lock_unknown'}]
    pid = lock.get('owner_pid', lock.get('pid'))
    state = alive(pid) if type(pid) is int else None
    denied = state == ACCESS_DENIED  # another program this user cannot inspect: never our TwinPulse
    same = None
    if state is True and isinstance(lock.get('process_identity'), dict):
        current = identity(pid)
        same = None if current is None else current == lock['process_identity']
    running = ('yes' if state is True else 'no' if state is False
               else 'another program this user cannot inspect (access denied)' if denied else 'unknown')
    line = (f"launcher.lock: pid {ident(pid)}, running {running}"
            + (f", same process {'yes' if same else 'NO (PID reused)'}" if same is not None else '')
            + f", launch {ident(lock.get('launch_id'))}, started {show_utc(lock.get('started_at_utc')) or '?'}")
    key = ('lock_stale' if state is False else 'lock_reused' if denied or (state is True and same is False)
           else 'lock_alive' if state is True else 'lock_unknown')
    return [line], [{'key': key, 'pid': pid, **({'access_denied': True} if denied else {})}]


SETTINGS_MAX_BYTES = 8192  # desktop_settings.read_settings refuses a larger desktop-settings.json


def _settings_part(runtime, facts):
    """desktop-settings.json, flagged exactly when desktop_settings.read_settings refuses it (the EXE then does not start)."""
    path = runtime / 'desktop-settings.json'
    if not path.exists():  # a link to nothing is no file to read_settings either: it uses the defaults
        return ['desktop-settings.json: none (defaults: port 8765, Isaac C:\\isaacsim)'], []
    if path.is_symlink() or not path.is_file():
        return [f"desktop-settings.json: {'a link' if path.is_symlink() else 'not a file'}, refused"], [{'key': 'desktop_settings_invalid'}]
    settings, info = read_json(path, SETTINGS_MAX_BYTES)
    if not isinstance(settings, dict):
        return [f"desktop-settings.json: not parsed ({info['error'] or 'unexpected shape'})"], [{'key': 'desktop_settings_invalid'}]
    findings = []
    unknown = sorted(str(key) for key in settings if key not in ('schema_version', 'preferred_port', 'isaac_root'))
    root = settings.get('isaac_root')
    line = (f"desktop-settings.json: port {ident(settings.get('preferred_port'))}, "
            f"isaac_root {(root or '-') if isinstance(root, str) else '(not text)' if 'isaac_root' in settings else '-'}, "
            f"BOM {'YES' if info['bom'] else 'no'}" + (f", unknown keys: {names(unknown)}" if unknown else ''))
    if isinstance(root, str) and root:
        facts['settings_isaac_root'] = root
    port = settings.get('preferred_port')
    if (unknown or settings.get('schema_version') != '1.0' or type(port) is not int or not 1024 <= port <= 65535
            or ('isaac_root' in settings and not isinstance(root, str))):
        findings.append({'key': 'desktop_settings_invalid'})  # the same rules as desktop_settings.read_settings
    if info['bom']:
        findings.append({'key': 'desktop_settings_bom'})
    return [line], findings


def _launches_part(runtime, count):
    launches = runtime / 'launches'
    folders = [path for path in launches.iterdir() if path.is_dir()] if launches.is_dir() else []
    reports = [launch_report(folder) for folder in newest(folders, count)]
    lines = [f'Launch folders: {len(folders)} (newest {len(reports)} below; check the dates, do not mix old and new runs)']
    for report in reports:
        lines += _launch_lines(report)
    return lines, _launch_findings(reports)


def _evidence_part(runtime, count):
    folder = runtime / 'provider-evidence'
    evidence = evidence_report(folder, count)
    lines = [f'provider-evidence: newest {len(evidence)} final records (saved prompts are never shown)']
    for item in evidence:
        if item.get('error'):
            lines.append(f"- {item['file']}: not parsed ({item['error']})")
            continue
        lines.append(f"- {item['file']}: saved {item.get('saved_at', '?')}, model {item.get('model_id', '?')}, "
                     f"stage {item.get('schema_stage', '-')}, status {item.get('status', '-')}, HTTP {item.get('http_status', '-')}, "
                     f"error {item.get('error_type', '-')}, content {item['content_type']}; body: {body_text(item['body'])}")
    return lines, _evidence_findings(evidence) + ([{'key': 'evidence_present'}] if folder.is_dir() else [])


def _folders_part(runtime):
    lines = []
    logs = runtime / 'desktop-logs'
    if logs.is_dir():
        files = newest([path for path in logs.iterdir() if path.is_file()], 5)
        lines.append('desktop-logs (newest 5, contents not shown): '
                     + (names(f'{path.name} {_size(path)} bytes {local_time(_mtime(path))}' for path in files) or 'empty'))
    stale = runtime / 'stale-launch-records'
    if stale.is_dir():
        lines.append(f'stale-launch-records: {len(list(stale.glob("*.json")))} archived locks')
    return lines, []


def runtime_section(local_app_data, *, alive=pid_alive, identity=process_identity, launch_count=8, evidence_count=10):
    runtime = Path(local_app_data) / 'TwinPulse' / 'runtime'
    lines, findings, facts = [f'Runtime folder: {runtime}'], [], {}
    if not runtime.is_dir():
        lines.append('  not found')
        return section(lines, findings, facts)
    parts = (('launcher.lock', lambda: _lock_part(runtime, alive, identity)), ('desktop-settings', lambda: _settings_part(runtime, facts)),
             ('provider settings', lambda: (provider_lines(runtime), [])), ('launches', lambda: _launches_part(runtime, launch_count)),
             ('provider-evidence', lambda: _evidence_part(runtime, evidence_count)), ('folders', lambda: _folders_part(runtime)))
    for title, part in parts:
        try:  # one unreadable piece must not hide the others
            more_lines, more_findings = part()
        except Exception as error:
            more_lines, more_findings = [f'{title}: check failed ({type(error).__name__}: {short(error, 160)})'], []
        lines += more_lines
        findings += more_findings
    return section(lines, findings, facts)


# ---- 5. network ----------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # report a redirect (often a filter) instead of following it


def product_user_agent(version):
    return 'TwinPulse/' + (version if isinstance(version, str) and re.fullmatch(r'[0-9A-Za-z.+-]{1,40}', version) else 'dev')


def _facts(status, headers, body, agent):
    content_type = (headers.get('Content-Type') or '') if headers is not None else ''
    location = (headers.get('Location') or '') if headers is not None else ''
    facts = {'agent': agent, 'status': status, 'content_type': short(content_type, 80) or '-',
             'server': short((headers.get('Server') or '') if headers is not None else '', 60), 'body': describe_body(body, content_type)}
    if location:
        facts['redirect_host'] = _host(location)
    return facts


def probe(url, user_agent=None, *, timeout=10.0, opener=None):
    """One GET without Authorization. user_agent None keeps urllib's own default User-Agent."""
    opener = opener or urllib.request.build_opener(_NoRedirect)
    headers = {} if user_agent is None else {'User-Agent': user_agent, 'Accept': 'application/json'}
    agent = user_agent or dict(getattr(opener, 'addheaders', [])).get('User-agent', 'Python-urllib (default)')
    request = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with opener.open(request, timeout=timeout) as response:
            return _facts(response.status, response.headers, response.read(65536), agent)
    except urllib.error.HTTPError as error:
        try:
            body = error.read(65536)
        except Exception:
            body = b''
        return _facts(error.code, error.headers, body, agent)
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as error:
        reason = getattr(error, 'reason', error)
        name = type(reason).__name__ if isinstance(reason, BaseException) else type(error).__name__
        return {'agent': agent, 'error': name, 'detail': short(reason, 160)}


def _probe_kind(facts):
    if 'error' in facts:
        text = (facts['error'] + ' ' + facts.get('detail', '')).lower()
        return 'tls' if 'certificate' in text else 'error'  # an SSL EOF or reset is a dropped connection, not a certificate
    if facts['body']['kind'] == 'html' or 300 <= facts['status'] < 400:
        return 'page'
    # Without a key the API answers 401 JSON; a JSON 403 or 5xx is not proof that the product can use it.
    return 'api' if facts['body']['kind'] == 'json' and facts['status'] == 401 else 'other'


def classify_pair(default, product):
    kinds = (_probe_kind(default), _probe_kind(product))
    if 'tls' in kinds:
        return 'tls'
    if kinds == ('error', 'error'):  # one answered request means the host is reachable: 'unclear' below
        return 'unreachable'
    return {('page', 'api'): 'python_ua_blocked', ('api', 'api'): 'reachable', ('page', 'page'): 'both_blocked',
            ('api', 'page'): 'product_ua_blocked'}.get(kinds, 'unclear')


def _probe_line(name, facts):
    if 'error' in facts:
        return f"{name} [{facts['agent']}]: no HTTP response ({facts['error']}: {facts['detail']})"
    return (f"{name} [{facts['agent']}]: HTTP {facts['status']}, {facts['content_type']}, {body_text(facts['body'])}"
            + (f", server {facts['server']}" if facts['server'] else '')
            + (f", redirect to {facts['redirect_host']}" if facts.get('redirect_host') else ''))


def network_section(version, *, targets=NETWORK_TARGETS, opener=None, timeout=10.0):
    agent = product_user_agent(version)
    lines = [f'Unauthenticated GET, no Authorization header, {timeout:g} s timeout, redirects not followed.',
             f'Compared: urllib default User-Agent vs "{agent}" (TwinPulse\'s own, honest User-Agent; no browser User-Agent).',
             'Reading: 401 JSON = the API answered (expected without a key); a 503/403 HTML page = a filter answered.']
    findings = []
    for name, url in targets:
        default = probe(url, None, timeout=timeout, opener=opener)
        product = probe(url, agent, timeout=timeout, opener=opener)
        lines += [_probe_line(name, default), _probe_line(name, product)]
        findings.append({'key': 'net_' + classify_pair(default, product), 'name': name, 'host': _host(url),
                         'default': default, 'product': product})
    return section(lines, findings, {'user_agent': agent})


# ---- summary and report --------------------------------------------------------------------

def _status_of(facts):
    return facts.get('error') or f"HTTP {facts.get('status')}"


def summary_lines(findings):
    """Short Korean lines: what each finding means and the next step."""
    out = []
    for item in findings:
        key, release = item['key'], item.get('release', '')
        text = {
            'profile_non_ascii': '사용자 폴더 경로에 한글 등 비ASCII 문자 있음 -> Isaac/Kit에서 문제될 수 있음(미검증), 문제가 나면 이 줄을 전달',
            'long_paths_disabled': '긴 경로(LongPathsEnabled) 꺼짐 -> 설치 경로가 259자를 넘는 파일은 설치/시작에 실패할 수 있음, 그때 IT에 긴 경로 허용 요청',
            'proxy_pac_only': ('프록시 자동 구성(PAC, AutoConfigURL)만 설정됨 -> Python과 TwinPulse는 PAC 파일을 읽지 않으므로 '
                               '아래 네트워크 요청은 프록시 없이 직접 연결한 결과'),
            'ps_policy_restricted': '그룹 정책이 PowerShell 스크립트를 제한함 -> 새 EXE 설치본의 Start-TwinPulse.cmd는 PowerShell 없이 실행',
            'isaac_missing': 'Isaac Sim 폴더(python.bat)를 찾지 못함 -> 설치 후 첫 실행에서 Isaac 폴더를 직접 선택',
            'not_installed': 'TwinPulse 설치 폴더 없음 -> 새 EXE ZIP을 풀고 Install-TwinPulse.cmd 실행',
            'pointer_bom': 'active-release.json에 BOM 있음 -> 새 설치 프로그램이 자동 처리 (구버전 EXE 설치는 여기서 멈출 수 있음)',
            'desktop_settings_invalid': 'desktop-settings.json 형식이 예상과 다름 -> 현재/새 버전 모두 시작하지 않음(DESKTOP_SETTINGS_INVALID 등), 지우지 말고 이름을 바꿔 보관',
            'desktop_settings_bom': 'desktop-settings.json에 BOM 있음 -> 새 버전은 자동 처리',
            'lock_unknown': 'launcher.lock 상태를 확인하지 못함 -> TwinPulse 창과 콘솔을 모두 닫은 뒤 설치',
            'launch_unresponsive': f"{item.get('when')} 실행: 엔진 응답 없음(heartbeat stale) -> 장시간 실행 중 절전/잠금 여부 확인",
            'evidence_present': 'provider-evidence 폴더에는 프롬프트가 저장될 수 있음 -> 이 보고서에는 넣지 않음, 원본 파일은 공유 전에 확인',
            'net_skipped': '네트워크 검사 생략(--no-network)',
        }.get(key)
        if text is None:
            if key == 'profile_special_chars':
                text = (f"사용자 경로에 {' '.join(item['chars'])} 문자 있음 -> 새 버전은 Isaac 엔진 명령을 따옴표로 감싸 시작하므로 지원됨"
                        "(이전 버전은 엔진 시작 실패 가능), 문제가 나면 이 줄을 전달")
            elif key == 'profile_unsupported_chars':
                text = (f"사용자 경로에 {' '.join(item['chars'])} 문자 있음 -> TwinPulse가 Isaac 엔진을 시작하지 않음"
                        "(engine_path_unsupported), 이 문자가 없는 Windows 계정(사용자 폴더)에서 실행")
            elif key == 'proxy_configured':
                text = ('프록시 설정 있음 -> 아래 네트워크 결과는 이 프록시를 거친 결과' if 'https' in item['schemes'] else
                        'http 프록시만 설정됨 -> 아래 HTTPS 네트워크 요청(TwinPulse 공급자 요청도)은 프록시 없이 직접 연결한 결과')
            elif key == 'isaac_found':
                text = f"Isaac 폴더 확인: {item['root']} (VERSION {item.get('version') or '없음'})"
            elif key == 'isaac_version_other':
                text = f"Isaac 버전이 6.0.1이 아님 ({item['version']}) -> 경고만 표시되지만 검증되지 않은 버전"
            elif key == 'isaac_user_site_shadow':
                text = (f"사용자 폴더(AppData\\Roaming\\Python)의 {', '.join(item['modules'])}가 Isaac 기본 패키지를 가림 "
                        "-> TwinPulse는 Isaac을 사용자 폴더 없이 시작하므로 영향 없음, 다른 Isaac 작업에서는 버전 충돌 가능")
            elif key == 'isaac_needs_user_site':
                text = (f"Isaac Python이 {', '.join(item['modules'])}를 사용자 폴더에서만 찾음 "
                        "-> TwinPulse 엔진이 시작하지 못할 수 있음, 이 줄을 전달")
            elif key == 'kit_registry_sync':
                text = f"Kit 로그({item['when']})에 확장 레지스트리 동기화 메시지 -> 인터넷이 막힌 PC에서는 시작이 늦거나 실패할 수 있음"
            elif key == 'pointer_unreadable':
                text = 'active-release.json을 읽지 못함 -> 지우지 말고 보관, 새 설치 프로그램이 원본을 그대로 백업'
            elif key == 'active_release_missing':
                text = f'active-release.json이 가리키는 release {release} 폴더 없음 -> 새 EXE ZIP으로 다시 설치'
            elif key == 'staging_leftovers':
                text = f"중단된 설치 폴더 {item['count']}개(.stage-/.install-) -> 지우지 말고 두어도 새 설치에는 영향 없음"
            elif key == 'offline_active':
                text = f'오프라인(venv) 설치본 {release} 사용 중 -> 이 방식은 지원 중단, 새 EXE ZIP 설치 권장(데스크톱 창, 600초 대기 포함)'
            elif key == 'release_modified':
                count = len(item['changed']) + len(item['missing']) + len(item['extra'])
                sample = names([path.rsplit('/', 1)[-1] for path in item['changed'] + item['missing'] + item['extra']], 3)
                text = f'release {release} 파일 {count}개가 manifest와 다름 ({sample}) -> ' + (
                    'EXE 시작 검사에서 멈출 수 있음(WINDOWS_PACKAGE_FILE_MISMATCH/UNMANIFESTED_FILE), 파일은 그대로 두고 이 줄을 개발자에게 전달'
                    if item.get('kind') == 'exe' else '수동 패치 흔적, 새 설치본에는 반영되지 않음')
            elif key == 'release_unreadable':
                sample = names([path.rsplit('/', 1)[-1] for path in item['files']], 3)
                text = (f"release {release} 파일 {len(item['files'])}개를 읽지 못함 ({sample}) "
                        f"-> 경로 259자 초과(긴 경로 꺼짐), 권한 또는 백신 잠금 가능, 수동 패치로 단정하지 말 것")
            elif key == 'release_backups':
                text = f"release {release}에 백업 파일 {len(item['files'])}개 -> 설치 파일을 직접 고친 흔적 (상세 목록 참고)"
            elif key == 'release_clean':
                text = f'release {release} 파일이 manifest와 일치'
            elif key == 'release_manifest_unreadable':
                text = f'release {release}의 manifest 파일 목록을 읽지 못함 -> 파일 비교 불가, manifest는 지우지 말고 보관'
            elif key in ('burger_mismatch', 'burger_mixed', 'burger_closure_changed', 'burger_linked', 'burger_oversized'):
                sample = names([path.rsplit('/', 1)[-1] for path in item['files']], 3)
                reason = {'burger_mismatch': '공개/원본 기준 모두와 다른 파일 ' + str(len(item['files'])) + '개',
                          'burger_mixed': '공개/원본 파일이 섞임', 'burger_closure_changed': '파일 구성이 다름',
                          'burger_linked': f"링크(심볼릭 링크/정션) {len(item['files'])}개 ({sample})",
                          'burger_oversized': f"{BURGER_SIZE_LIMIT // (1024 * 1024)}MB를 넘는 파일 {len(item['files'])}개 ({sample})"}[key]
                text = f"release {release}의 Burger 에셋: {reason} -> {item['code']} 원인, 새 EXE 설치본은 검증된 공개 에셋 포함"
            elif key == 'burger_missing':
                text = f'release {release}에 Burger 에셋 파일 없음 -> SIM_BURGER_ASSET_MISSING, SIM Burger 기능 불가, 새 EXE 설치본 사용'
            elif key == 'lock_alive':
                text = f"TwinPulse 실행 중 (launcher.lock PID {item['pid']}) -> 설치 전에 TwinPulse를 정상 종료"
            elif key == 'lock_stale':
                text = f"남은 launcher.lock (PID {item['pid']} 종료됨) -> 새 EXE 설치 프로그램이 자동 보관, 오프라인 설치 프로그램은 거부"
            elif key == 'lock_reused':
                other = '이 사용자가 확인할 수 없는 다른 프로그램' if item.get('access_denied') else '다른 프로그램'
                text = f"launcher.lock의 PID {item['pid']}를 {other}이 사용 중 -> 새 EXE 설치 프로그램이 자동 보관"
            elif key == 'launch_desktop_host':
                text = f"{item['when']} 실행: DESKTOP_HOST_NOT_BUILT -> 오프라인 설치본에는 데스크톱 창이 없음, EXE 설치본에는 포함"
            elif key == 'launch_ready_timeout':
                waited = f", {item['seconds']}초 후" if item.get('seconds') is not None else ''
                repeated = f" (최근 기록 중 {item['count']}회)" if item['count'] > 1 else ''
                text = (f"{item['when']} 실행: Isaac 준비 시간 초과{waited}{repeated} "
                        f"-> Isaac 첫 실행은 5분 이상 걸릴 수 있음, 새 버전은 600초 대기")
            elif key == 'launch_engine_log_empty':
                text = f"{item['when']} 실행: engine.log 0바이트 -> Isaac이 실행되지 않았다는 증거가 아님(출력 버퍼링), 새 버전은 즉시 기록"
            elif key == 'launch_engine_ran':
                text = f"{item['when']} 실행: engine not_started는 정리 후 표시 -> owned-exit 기록상 엔진(PID {item['pid']})은 실행되었다가 종료됨"
            elif key == 'launch_error':
                text = f"{item['when']} 실행 오류: {item.get('phase')} \"{item.get('message')}\" -> 상세 섹션 참고"
            elif key == 'launch_latest':
                text = f"가장 최근 실행({item['when']}): {item['status']} / {item['phase']}"
            elif key == 'evidence_json':
                body = item['body']
                label = '/'.join(body[name] for name in ('type', 'code', 'param') if body.get(name)) or 'JSON'
                text = (f"공급자 오류 본문 저장됨 ({item['when']}, {item['model']}, HTTP {item['status']}): {label}"
                        + (f" \"{short(body['message'], 160)}\"" if body.get('message') else '') + ' -> 이 줄을 개발자에게 전달')
            elif key == 'evidence_html':
                text = (f"공급자 응답이 HTML 페이지 '{item['body'].get('title') or '-'}' ({item['when']}, HTTP {item['status']}) "
                        f"-> 네트워크 필터 차단 페이지로 보임")
            elif key == 'net_python_ua_blocked':
                text = f"{item['name']}: Python-urllib만 차단됨 -> 새 버전(TwinPulse UA)에서 해결 예상"
            elif key == 'net_both_blocked':
                title = item['product']['body'].get('title') if 'body' in item['product'] else None
                text = f"{item['name']}: TwinPulse UA도 차단 페이지" + (f" '{title}'" if title else '') + f" -> IT에 {item['host']} 허용 요청 필요"
            elif key == 'net_product_ua_blocked':
                text = f"{item['name']}: TwinPulse UA만 차단됨 -> IT에 {item['host']} 허용 요청 필요"
            elif key == 'net_reachable':
                text = f"{item['name']}: 접속 정상 (키 없이 {_status_of(item['product'])} JSON = 정상)"
            elif key == 'net_tls':
                text = f"{item['name']}: TLS 인증서 검증 실패 -> 회사 보안 장비 인증서 문제 가능, IT 확인 (검증을 끄지 말 것)"
            elif key == 'net_unreachable':
                text = (f"{item['name']}: 연결 실패 ({_status_of(item['default'])} / {_status_of(item['product'])}) "
                        f"-> 네트워크/방화벽/프록시 확인")
            elif key == 'net_unclear':
                text = (f"{item['name']}: 판정 어려움 (기본 {_status_of(item['default'])}, TwinPulse {_status_of(item['product'])}) "
                        f"-> 상세 섹션 참고")
        if text:
            out.append(text)
    out.append('원본 기록 보존: runtime\\launches, provider-evidence, Kit 로그, desktop-logs는 지우거나 옮기지 말고 그대로 보관')
    return out


def render_report(started, summary, sections, *, network):
    lines = [f'TwinPulse company PC check {CHECK_VERSION} (read-only)',
             f"Created {started.astimezone().strftime('%Y-%m-%d %H:%M:%S %z')} ({started.strftime('%Y-%m-%dT%H:%M:%SZ')})",
             f"Network check: {'on' if network else 'off (--no-network)'}",
             'Nothing was changed. Keys, tokens, Authorization values and saved prompts are not included.',
             '', '== Summary (요약) ==', *('- ' + line for line in summary), '']
    for title, part in sections:
        lines += [f'== {title} ==', *part['lines'], '']
    return '\n'.join(lines) + '\n'


def write_report(text, env, cwd, output_dir=None, *, now=None, winreg=None):
    """The only file this check writes: Desktop if it exists, else the current folder."""
    folder = Path(output_dir) if output_dir else (desktop_folder(env, winreg) or Path(cwd))
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(now))
    for attempt in range(100):
        path = folder / (f'TwinPulse-PC-Check-{stamp}' + (f'-{attempt}' if attempt else '') + '.txt')
        try:
            with open(path, 'x', encoding='utf-8-sig', newline='\r\n') as stream:
                stream.write(text)
            return path
        except FileExistsError:
            continue
    raise FileExistsError(str(folder))


def _guard(title, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as error:  # one broken piece must not hide the other sections
        return section([f'{title} check failed: {type(error).__name__}: {short(error, 200)}'], [])


def main(argv=None, *, env=None, cwd=None, out=None):
    parser = argparse.ArgumentParser(description='Read-only TwinPulse company-PC check. Writes one report file only.')
    parser.add_argument('--no-network', action='store_true', help='skip the unauthenticated HTTPS checks')
    parser.add_argument('--output-dir', type=Path, help='folder for the report (default: Desktop, else the current folder)')
    parser.add_argument('--no-pause', action='store_true', help='do not wait for Enter at the end')
    args = parser.parse_args(argv)
    env = dict(os.environ if env is None else env)
    out = out or sys.stdout
    if out is sys.stdout and hasattr(out, 'reconfigure'):
        try:
            out.reconfigure(errors='replace')
        except (OSError, ValueError):
            pass

    def say(text):
        out.write(text + '\n')
        out.flush()

    started = datetime.now(timezone.utc)
    local = Path(env.get('LOCALAPPDATA') or Path(env.get('USERPROFILE') or Path.home()) / 'AppData' / 'Local')
    say('TwinPulse company PC check (read-only). Hashing release files can take a minute.')
    say('[1/5] TwinPulse install')
    install = _guard('Install', install_section, local)
    say('[2/5] Runtime state')
    runtime = _guard('Runtime', runtime_section, local)
    say('[3/5] System')
    system = _guard('System', system_section, env)
    say('[4/5] Isaac Sim (imports numpy/PIL in Isaac Python twice, read-only)')
    roots = [('desktop-settings', runtime['facts'].get('settings_isaac_root')),
             ('active-release.json', install['facts'].get('pointer_isaac_root'))]
    isaac = _guard('Isaac', isaac_section, env, [(label, root) for label, root in roots if root])
    if args.no_network:
        say('[5/5] Network: skipped')
        network = section(['Skipped (--no-network).'], [{'key': 'net_skipped'}])
    else:
        say('[5/5] Network (4 requests, up to 10 s each)')
        network = _guard('Network', network_section, install['facts'].get('product_version'))
    sections = [('1. System', system), ('2. Isaac Sim', isaac), ('3. TwinPulse install', install),
                ('4. Runtime state', runtime), ('5. Network', network)]
    summary = summary_lines([item for _, part in sections for item in part['findings']])
    text = render_report(started, summary, sections, network=not args.no_network)
    try:
        path = write_report(text, env, cwd or os.getcwd(), args.output_dir)
    except OSError as error:
        say(f'Report could not be written ({type(error).__name__}); the summary follows.')
        path = None
    say('')
    say('== 요약 ==')
    for line in summary:
        say('- ' + line)
    say('')
    say(f'Report: {path}' if path else 'Report: not written')
    if os.name == 'nt' and not args.no_pause and sys.stdin is not None and sys.stdin.isatty():
        try:
            input('Press Enter to close.')
        except (EOFError, KeyboardInterrupt):
            pass
    return 0 if path else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
