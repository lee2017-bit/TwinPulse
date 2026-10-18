# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit, per-launch testing mode. No persisted setting or privilege change."""
import socket
import json


def configure_testing(arguments,state,environment,role='launcher'):
    arguments=list(arguments)
    environment.pop('TWINPULSE_UI_TEST_CDP_PORT',None)
    if any(value.startswith('--remote-debugging') for value in arguments):raise ValueError('USE_AUTOMATION_TEST_ENTRY')
    requested='--automation-test' in arguments
    if role!='launcher':
        if requested:raise ValueError('AUTOMATION_TEST_LAUNCH_ONLY')
        return arguments
    if requested and (arguments.count('--automation-test')!=1 or '--internal-role' in arguments or '--install' in arguments):
        raise ValueError('AUTOMATION_TEST_LAUNCH_ONLY')
    owner_path=state/'launcher.lock'
    if owner_path.exists():
        owner={}
        try:
            owner=json.loads(owner_path.read_text(encoding='utf-8'));launch=owner['launch_id']
            from .process_manager import _pid_alive
            pid=owner.get('owner_pid',owner.get('pid'))
            if type(pid) is int and pid>0 and not _pid_alive(pid):
                owner=None
                record={}
            else:
                if not isinstance(launch,str) or len(launch)!=32 or any(c not in '0123456789abcdef' for c in launch):raise ValueError()
                if type(owner.get('desktop_automation')) is bool:
                    record={'enabled':owner['desktop_automation'],'port':owner.get('automation_port')}
                else:record=json.loads((state/'launches'/launch/'desktop-automation.json').read_text(encoding='utf-8'))
        except (OSError,ValueError,KeyError,TypeError):
            # A newly O_EXCL-created lock may not be published yet. Do not
            # misclassify it; the manager retries its read and checks mode
            # again immediately before reusing an existing owner.
            owner=None;record={}
        if requested and owner is not None:
            if record.get('enabled') is not True:raise ValueError('EXIT_TWINPULSE_NORMALLY_BEFORE_TEST_MODE')
            port=record.get('port')
            if type(port) is not int or not 1024<=port<=65535:raise ValueError('AUTOMATION_TEST_MODE_UNKNOWN')
            environment['TWINPULSE_UI_TEST_CDP_PORT']=str(port);arguments.remove('--automation-test');return arguments
        if record.get('enabled') is True:raise ValueError('EXIT_TEST_MODE_NORMALLY_BEFORE_NORMAL_START')
    if not requested:return arguments
    for port in range(19222,19232):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
            try:listener.bind(('127.0.0.1',port))
            except OSError:continue
        environment['TWINPULSE_UI_TEST_CDP_PORT']=str(port)
        arguments.remove('--automation-test');return arguments
    raise ValueError('AUTOMATION_TEST_LOCAL_PORT_UNAVAILABLE')
