# SPDX-License-Identifier: Apache-2.0
"""Compare local cleanup observations; no process, App, or remote invocation."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'outputs/robot-continuous-repair-20261021'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    p = OUT / name
    return dict(path=name, sha256=sha256(p.read_bytes()).hexdigest())


def tools(audit):
    rows = [g for g in audit['groups'] if g['role'] in (
        'COMPUTER_USE_OR_NODE_TOOL_RUNTIME', 'REA_TOOL_TRANSPORT')]
    return dict(process_count=sum(g['process_count'] for g in rows),
                observed_working_set_sum_bytes=sum(g['observed_working_set_sum_bytes'] for g in rows),
                observed_private_commit_sum_bytes=sum(g['observed_private_commit_sum_bytes'] for g in rows),
                groups=rows)


def main():
    original = read('background-process-audit35.json')
    before = read('background-process-audit36-before.json')
    after = read('background-process-audit36-after.json')
    b = read('dwm-before-authorized-reset36.json')
    a = read('dwm-after-authorized-reset36.json')
    assert not before['historical_owned_still_alive'] and not after['historical_owned_still_alive']
    assert not b['twinpulse_or_kit'] and not a['twinpulse_or_kit']
    assert b['boot_at'] == a['boot_at']
    value = dict(
        schema='authorized-tool-cleanup-observation-1.0',
        status='PARTIAL_OWN_KERNEL_RESET_SHARED_TRANSPORTS_NOT_CLOSED',
        authorization_scope='Only confirmed finished sessions owned by this work. Current conversation, other work and unproven/shared ownership excluded.',
        actual_actions=dict(supported_node_repl_kernel_reset=1, force_process_stop=0,
                            mcp_transport_close=0, plugin_or_config_change=0,
                            app_or_robot_start=0, driver_or_os_change=0),
        earlier_at=original['sampled_at'], before_at=before['sampled_at'], after_at=after['sampled_at'],
        earlier_tools=tools(original), before_tools=tools(before), after_tools=tools(after),
        dwm_before=b['dwm'], dwm_after=a['dwm'],
        reset_observation_elapsed_s=(datetime.fromisoformat(a['sampled_at'])-datetime.fromisoformat(b['sampled_at'])).total_seconds(),
        dwm_private_change_bytes=a['dwm'][0]['PrivateMemorySize64']-b['dwm'][0]['PrivateMemorySize64'],
        dwm_working_set_change_bytes=a['dwm'][0]['WorkingSet64']-b['dwm'][0]['WorkingSet64'],
        physical_available_before_bytes=b['physical_available_bytes'],
        physical_available_after_bytes=a['physical_available_bytes'],
        actual_twinpulse_owned_still_alive_count=0,
        limitation='MCP transport parent/creation metadata does not map each client to a definitely finished session. No safe individual-client close is exposed in this tool environment. The kernel reset did not terminate those transport processes; no claim that cleanup is complete.',
        robotics='NOT_READY remains: current whole SIM31 failed with native ERR_NETWORK_CHANGED coincident with an OS Wi-Fi reconnect. Remaining tools occupy memory, but no intervention has established they caused that failure. Physical robot is OFF/NOT_RUN.',
        next='Save work and normally exit/reopen Codex itself, without a PC reboot or driver change, then compare process/RAM/DWM against these immutable baselines. This step was not performed automatically because it closes the current conversation and potentially other work. It is a discriminating next check, not a guaranteed fix.',
        semantics='Working-set sums can double-count shared pages. Private commit is not physical RAM or actual pagefile bytes. More processes alone do not prove a leak or causal attribution.',
        official_reference='https://learn.chatgpt.com/docs/app-server',
        references=[ref(n) for n in ('background-process-audit35.json', 'background-process-audit36-before.json',
            'background-process-audit36-after.json', 'dwm-before-authorized-reset36.json', 'dwm-after-authorized-reset36.json')])
    with (OUT / 'authorized-tool-cleanup36.json').open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=value['status'], before=value['before_tools']['process_count'],
                         after=value['after_tools']['process_count'], forced_stops=0,
                         dwm_private_change_bytes=value['dwm_private_change_bytes'])))


if __name__ == '__main__':
    main()
