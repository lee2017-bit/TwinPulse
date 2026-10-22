# SPDX-License-Identifier: Apache-2.0
"""Preserve exact historical launcher traces; not a new shutdown trial."""
from hashlib import sha256
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/robot-continuous-repair-20261021'
runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
out=BASE/'normal12-shutdown-original-context';out.mkdir(exist_ok=False)
rows=[]
for identity in ('13811a9c03c34b4498e0da68559fbce9','2c8bfc676ab24f7cbff6351c6f36d8ea',
                 'b9bdf6906b504f98b152c2ee62bdc07e','ffe5fec9976f4e1da6d24672c32e0196'):
    folder=out/identity;folder.mkdir()
    for name in ('manifest.json','events.jsonl'):
        source=runtime/'diagnostics'/identity/name
        if not source.is_file():rows.append(dict(source=str(source),status='ORIGINAL_UNAVAILABLE'));continue
        raw=source.read_bytes();target=folder/name;target.write_bytes(raw)
        rows.append(dict(source=str(source),path=target.relative_to(BASE).as_posix(),bytes=len(raw),sha256=sha256(raw).hexdigest()))
source=runtime/'launches/2d40d70d03164f06bf46b33064625f17/engine-stop.request'
raw=source.read_bytes();target=out/'engine-stop.request';target.write_bytes(raw)
rows.append(dict(source=str(source),path=target.relative_to(BASE).as_posix(),bytes=len(raw),sha256=sha256(raw).hexdigest()))
(out/'receipt.json').write_text(json.dumps(dict(classification='ORIGINAL_NORMAL12_FORCED_VS_NATURAL_EXIT_UNKNOWN',files=rows),indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(rows),receipt=str(out/'receipt.json'))))
