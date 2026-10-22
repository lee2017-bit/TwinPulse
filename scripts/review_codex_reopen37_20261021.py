# SPDX-License-Identifier: Apache-2.0
"""Compare immutable before/after counters and PID+creation identities only."""
from hashlib import sha256
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'outputs/robot-continuous-repair-20261021'
TOOL_ROLES = {'COMPUTER_USE_OR_NODE_TOOL_RUNTIME', 'REA_TOOL_TRANSPORT'}


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    return dict(path=name, sha256=sha256((OUT / name).read_bytes()).hexdigest())


def summary(audit, roles):
    groups = [g for g in audit['groups'] if g['role'] in roles]
    return dict(process_count=sum(g['process_count'] for g in groups),
                working_set_sum_bytes=sum(g['observed_working_set_sum_bytes'] for g in groups),
                private_commit_sum_bytes=sum(g['observed_private_commit_sum_bytes'] for g in groups))


def main():
    before = read('background-process-audit36-after.json')
    after = read('background-process-audit37-after-codex-reopen.json')
    b = read('dwm-after-authorized-reset36.json')
    a = read('dwm-after-codex-reopen37.json')
    idle = read('dwm-after-codex-reopen37-idle.json')
    current = {(p['pid'], p['created_unix_ms']) for p in after['relevant_processes']}
    old_tools = [p for p in before['relevant_processes'] if p['role'] in TOOL_ROLES]
    old_codex = [p for p in before['relevant_processes'] if p['role'] == 'CODEX_APP_OR_ENGINE']
    remaining_tools = [p for p in old_tools if (p['pid'], p['created_unix_ms']) in current]
    remaining_codex = [p for p in old_codex if (p['pid'], p['created_unix_ms']) in current]
    old, new = summary(before, TOOL_ROLES), summary(after, TOOL_ROLES)
    assert b['boot_at'] == a['boot_at'] == idle['boot_at']
    assert not b['twinpulse_or_kit'] and not a['twinpulse_or_kit'] and not idle['twinpulse_or_kit']
    assert before['dwm'][0]['pid'] == after['dwm'][0]['pid'] == a['dwm'][0]['Id']
    value = dict(
        schema='codex-normal-close-reopen-comparison-1.0',
        status='OLD_TOOL_PROCESSES_CLOSED_DWM_NOT_RECOVERED_NOT_READY' if not remaining_tools else 'OLD_TOOL_PROCESSES_REMAIN_NOT_READY',
        before_at=before['sampled_at'], after_at=after['sampled_at'], idle_at=idle['sampled_at'],
        same_os_boot=True, original_tool_identity_count=len(old_tools), original_tool_identities_remaining=remaining_tools,
        original_codex_identity_count=len(old_codex), original_codex_identities_remaining=remaining_codex,
        tools_before=old, tools_after=new,
        tool_working_set_sum_change_bytes=new['working_set_sum_bytes']-old['working_set_sum_bytes'],
        tool_private_commit_sum_change_bytes=new['private_commit_sum_bytes']-old['private_commit_sum_bytes'],
        codex_before=summary(before, {'CODEX_APP_OR_ENGINE'}), codex_after=summary(after, {'CODEX_APP_OR_ENGINE'}),
        dwm_before=b['dwm'][0], dwm_after=a['dwm'][0], dwm_idle=idle['dwm'][0],
        dwm_working_set_change_bytes=a['dwm'][0]['WorkingSet64']-b['dwm'][0]['WorkingSet64'],
        dwm_private_change_bytes=a['dwm'][0]['PrivateMemorySize64']-b['dwm'][0]['PrivateMemorySize64'],
        physical_available_before_bytes=b['physical_available_bytes'], physical_available_after_bytes=a['physical_available_bytes'],
        physical_available_idle_bytes=idle['physical_available_bytes'],
        interpretation=[
            'The user normal close/reopen removed the observed old tool process identities, not merely their windows. New tool processes are counted separately.',
            'Tool-private commit and observed working-set sums fell, but DWM did not release its prior private commit. Its resident working set increased much more than its private commit. Do not call that difference an equally large new private allocation.',
            'Working-set sums share pages and cannot be added as disjoint physical RAM. No page-level causality or total-memory accounting is established.',
            'The old tool residency contributed counter load; it is not proven to be the cause of the original31 native network failure or all DWM allocation.',
            'No new TwinPulse/Isaac start, robot request, driver/OS change, forced process stop or installation occurred in this comparison. The current full UI gate remains NOT_READY.'],
        next='Do not ask for robot power or another Codex restart. Isolate the remaining Windows graphics allocation/capture/close path using bounded diagnostics before further memory-heavy Isaac acceptance; do not treat a driver update or PC reboot as an established permanent fix.',
        references=[ref(n) for n in ('background-process-audit36-after.json', 'background-process-audit37-after-codex-reopen.json',
            'dwm-after-authorized-reset36.json', 'dwm-after-codex-reopen37.json', 'dwm-after-codex-reopen37-idle.json')])
    with (OUT / 'codex-reopen-comparison37.json').open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=value['status'], old_tool_remaining=len(remaining_tools),
                         old_codex_remaining=len(remaining_codex), tools_before=old, tools_after=new,
                         dwm_ws_change=value['dwm_working_set_change_bytes'], dwm_private_change=value['dwm_private_change_bytes'],
                         available_idle=value['physical_available_idle_bytes'])))


if __name__ == '__main__':
    main()
