# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Optional isolated evidence capture for fault tests, never physical evidence."""
import json
import os
from pathlib import Path
import re


def save(case,data):
    name=os.environ.get('TWINPULSE_COMBINED_EVIDENCE')
    if not name:return
    if not re.fullmatch('[a-z0-9-]{1,100}',name) or not re.fullmatch('[a-z0-9-]{1,100}',case):
        raise ValueError('COMBINED_EVIDENCE_NAME')
    root=Path(__file__).resolve().parents[2]/'artifacts/verification'/name/'cases'
    root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):raise ValueError('COMBINED_EVIDENCE_PATH')
    with (root/(case+'.json')).open('x',encoding='utf-8') as stream:
        json.dump({'robot_connections':0,'physical_validation':'NOT_RUN',
                   'sensor_basis':'SYNTHETIC_ONLY','case':case,**data},stream,allow_nan=False,indent=2)
