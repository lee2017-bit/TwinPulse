# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned offline test child exits without finally after a synced journal prefix."""
import os
from pathlib import Path
import sys
import time

for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages'/name/'src'))
from twinpulse_app.session_journal import SessionJournal

sink=SessionJournal(Path(sys.argv[1])/'session.jsonl')
sink.start()
for n in range(12):sink.append({'n':n})
until=time.monotonic()+2
while sink.status()['saved']<12 and time.monotonic()<until:time.sleep(.005)
os._exit(0 if sink.status()['saved']==12 else 1)
