# SPDX-License-Identifier: Apache-2.0
"""Read-only actual-history replay comparison; never rewrites project history."""
from dataclasses import replace
import hashlib,json,os,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.scene_changes import SceneChangeHistory,SceneChange
from twinpulse_app.project_store import ProjectRecord
folder=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1'
source=ProjectRecord.from_dict(json.loads((folder/'project.json').read_bytes())).site_draft
path=folder/'project.scene-changes.json';raw=path.read_bytes();value=json.loads(raw);counts={};timings={};original=SceneChangeHistory._apply_one
def measured(name,fn):
    count=[0]
    def apply(*a,**k):count[0]+=1;return original(*a,**k)
    start=time.monotonic()
    with patch.object(SceneChangeHistory,'_apply_one',staticmethod(apply)):result=fn()
    counts[name]=count[0];timings[name]=time.monotonic()-start;return result
def previous():
    h=replace(SceneChangeHistory.empty(value['project_id'],source),schema_version=value['schema_version'])
    for operation in value['operations']:h=h.append(source,SceneChange.from_dict(operation))
    if h.current_scene_revision!=value['current_scene_revision']:raise ValueError('result changed')
    return h
old=measured('previous_prefix_parser',previous)
new=measured('current_complete_chain_parser',lambda:SceneChangeHistory.from_dict(value,source,value['project_id']))
checks=dict(identical_checked_history=old==new,original_bytes_unchanged=path.read_bytes()==raw,
    one_apply_per_operation=counts['current_complete_chain_parser']==len(new.operations),
    fewer_apply_calls=counts['current_complete_chain_parser']<counts['previous_prefix_parser'])
result=dict(status='PASS' if all(checks.values()) else 'FAIL',scope='READ_ONLY_ORIGINAL_HISTORY_NOT_UI_LATENCY_ACCEPTANCE',checks=checks,
    source_path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),operations=len(new.operations),apply_one_calls=counts,elapsed_s=timings)
out=ROOT/'outputs/environment-task-loop-20261025-01/history-linear01.json'
with out.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(result));sys.exit(0 if result['status']=='PASS' else 1)
