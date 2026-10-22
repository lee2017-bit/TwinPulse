# SPDX-License-Identifier: Apache-2.0
"""Bounded, project-owned native capture target. No TwinPulse/robot/API actions."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time
import tkinter as tk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root_path = Path(__file__).resolve().parents[1]
    target = args.output.resolve()
    if not target.is_relative_to((root_path / 'outputs/robot-continuous-repair-20261021').resolve()):
        raise ValueError('PROJECT_OWNED_DIAGNOSTIC_ONLY')
    target.mkdir(exist_ok=False)
    events = []
    began = time.monotonic()
    root = tk.Tk()
    root.title('TwinPulse Capture Probe 38 - no robot')
    root.geometry('640x240+100+120')
    label = tk.Label(root, text='Local capture/close diagnostic\nNo Isaac, robot, network or project changes', font=('Segoe UI', 15))
    label.pack(padx=16, pady=22)
    counter = tk.Label(root, text='Owned temporary window', font=('Segoe UI', 12))
    counter.pack(pady=8)
    closed = False

    def record(kind):
        events.append(dict(kind=kind, utc=datetime.now(timezone.utc).isoformat(), elapsed_s=time.monotonic()-began))

    def close(kind='WINDOW_CLOSE_REQUEST'):
        nonlocal closed
        if closed:
            return
        closed = True
        record(kind)
        root.destroy()

    def tick():
        if not closed:
            counter.configure(text=f'Owned temporary window - {time.monotonic()-began:.1f}s')
            root.after(500, tick)

    tk.Button(root, text='Close probe', command=lambda: close('CLOSE_BUTTON'), font=('Segoe UI', 12)).pack(pady=8)
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(120000, lambda: close('BOUNDED_AUTO_CLOSE'))
    record('WINDOW_CREATED')
    tick()
    try:
        root.mainloop()
    finally:
        record('MAINLOOP_RETURNED')
        value = dict(schema='owned-native-capture-probe-1.0', status='CLOSED' if closed else 'UNCONFIRMED',
                     pid=os.getpid(), events=events, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                     maximum_window_lifetime_s=120, classification='SUPPLEMENTARY_CAPTURE_DIAGNOSTIC_NOT_TWINPULSE_OR_ROBOT_ACCEPTANCE')
        with (target / 'result.json').open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)


if __name__ == '__main__':
    main()
