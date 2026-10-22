# SPDX-License-Identifier: Apache-2.0
"""Read-only bounded native-capture experiment; never an App acceptance result."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-continuous-repair-20261021'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    return dict(path=name, sha256=sha256((OUT / name).read_bytes()).hexdigest())


def at(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000


def main():
    probe = read('capture-probe38/result.json')
    receipt = read('memory-capture-probe38/receipt.json')
    samples = OUT / 'memory-capture-probe38/samples.jsonl'
    assert sha256(samples.read_bytes()).hexdigest() == receipt['samples_sha256']
    assert probe['status'] == 'CLOSED' and not receipt['errors']
    rows = [json.loads(line) for line in samples.open(encoding='utf-8')]
    protected = []
    seen = set()
    for row in rows:
        value = row.get('protected_process_projection') or {}
        if value.get('at_ms') in seen:
            continue
        seen.add(value.get('at_ms'))
        for process in value.get('rows', []):
            if process['name'].lower() in ('dwm', 'dwm.exe'):
                protected.append(dict(at_ms=value['at_ms'], **process))
    begin = at(probe['events'][0]['utc'])
    end = at(next(e['utc'] for e in probe['events'] if e['kind'] == 'MAINLOOP_RETURNED'))
    p = [row for row in protected if begin <= row['at_ms'] <= end]
    assert len(p) >= 20 and len({r['pid'] for r in p}) == 1
    private = [r['private_committed_bytes'] for r in p]
    ws = [r['working_set_bytes'] for r in p]
    value = dict(
        schema='owned-native-capture-probe-review-1.0', generated_at=datetime.now(timezone.utc).isoformat(),
        status='AX_AVAILABLE_NATIVE_SCREENSHOT_TIMEOUT_NOT_APP_ACCEPTANCE',
        user_screen_state='User explicitly confirmed screen ON and Windows unlocked; supplied chat screenshot corroborates display availability. Not independently sampled power state.',
        actual_actions=dict(project_owned_tk_window=True, native_accessibility_observed=True,
                            native_screenshots_received=0, native_input=0,
                            bounded_auto_close=True, native_alt_f4=False,
                            robot=0, isaac=0, system_changes=0),
        native_capture_attempts=[
            dict(started_utc='2026-10-21T13:48:12.517Z',
                 ended_before_utc='2026-10-21T13:48:15.213Z', exact_end_not_recorded=True,
                 error='FrameArrived timed out: timed out waiting on channel'),
            dict(started_utc='2026-10-21T13:48:46.204Z', ended_utc='2026-10-21T13:48:51.237Z',
                 recovery='Fresh returned window selection, one retry only',
                 error='Error: window capture timed out: timed out waiting on channel')],
        capture_record_provenance='Main-agent transcription of actual tool results; not a native capture trace file or screenshot.',
        dwm_during_owned_window=dict(samples=len(p), pid=p[0]['pid'],
            private_first_bytes=private[0], private_last_bytes=private[-1],
            private_min_bytes=min(private), private_max_bytes=max(private),
            working_set_first_bytes=ws[0], working_set_last_bytes=ws[-1],
            working_set_min_bytes=min(ws), working_set_max_bytes=max(ws)),
        memory_collection=dict(rows=receipt['rows'], elapsed_s=receipt['elapsed_s'],
            recorder_cpu_s=receipt['recorder_cpu_s'], errors=receipt['errors']),
        interpretation=[
            'Native AX worked, but capture failed twice even without TwinPulse/Isaac. Do not blame the user screen lock or treat the screenshot as received.',
            'This bounded probe did not reproduce the earlier sustained DWM private-commit growth. Capture/driver leak causality remains UNKNOWN.',
            'Tk auto-close does not reproduce an Electron native Alt+F4 path. This is supplementary, not ordinary App or physical acceptance.',
            'Private commit is not resident RAM; working sets contain shared pages. Sampled counters cannot prove page-level causality.'],
        references=[ref(n) for n in ('capture-probe38/result.json', 'memory-capture-probe38/receipt.json',
            'memory-capture-probe38/samples.jsonl', 'codex-reopen-comparison37.json')])
    with (OUT / 'capture-probe-review38.json').open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=value['status'], dwm=value['dwm_during_owned_window'])))


if __name__ == '__main__':
    main()
