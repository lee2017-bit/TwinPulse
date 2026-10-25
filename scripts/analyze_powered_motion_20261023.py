# SPDX-License-Identifier: Apache-2.0
"""Supplementary offline use of the shipped scan/noise analyser, not UI acceptance."""
import argparse
import json
from pathlib import Path
import sys
import time

root=Path(__file__).resolve().parents[1]
for package in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(root/'packages'/package/'src'))
sys.path.insert(0,str(root/'packages/twinpulse_robot_safety'))
from twinpulse_app.physical_motion_analysis import read_archive,analyse
from field_tests import register_pair

parser=argparse.ArgumentParser()
parser.add_argument('directory',type=Path)
parser.add_argument('--operation',required=True)
parser.add_argument('--project',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
began=time.monotonic()
archive=read_archive(args.directory,args.operation,args.project,began+60)
result=analyse(archive,register_pair,began+60)
result.update(invocation='SOURCE_OFFLINE_SUPPLEMENT_NOT_INSTALLED_UI_ACCEPTANCE',elapsed_s=time.monotonic()-began)
with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
print(json.dumps(dict(status=result['status'],elapsed_s=result['elapsed_s'],rejected_scans=result['rejected_scan_reasons'],
    windows=[{k:w.get(k) for k in ('request_id','direction','start','end','wheel','lidar','comparison','body_motion')} for w in result['windows']]),allow_nan=False))
