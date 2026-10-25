# SPDX-License-Identifier: Apache-2.0
"""Streaming original UI observations; no product state or robot writes."""
import json,hashlib,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'outputs/robot-environment-field-20261025-01'
target=out/'admission-analysis01.json'
if target.exists():raise ValueError('NEW_RESULT_REQUIRED')
folder=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1/robot-tasks/9ab857c208416c83892dfa59bc09de2d'
task=json.loads((folder/'task.json').read_bytes())
samples=[]
with (out/'session03/fleet-observations.jsonl').open(encoding='utf-8') as f:
    for n,line in enumerate(f,1):
        value=json.loads(line)
        if not 1792898280000<=value['at']<=1792898285000:continue
        response=value['response'];row=next((r for r in (response.get('fleet') or response).get('robots',[]) if r['robot_id']==task['robot_id']),None)
        if not row:continue
        packet=row.get('task_local_observation') or {}
        samples.append(dict(line=n,at=value['at'],method=value['method'],request=value.get('request'),
            operation_id=row['operation_id'],connection_epoch=row['connection_epoch'],control_state=row['control_state'],
            motion_epoch=row['motion_epoch'],applied_motion_epoch=row['applied_motion_epoch'],
            pose=row.get('pose'),native_pose=row.get('native_pose'),task_local_state=row.get('task_local_state'),
            observation_sha256=packet.get('sha256'),observation_age_ms=row.get('task_observation_age_ms'),
            config=(row.get('field') or {}).get('config'),timing_values=row.get('timing_values'),
            boot=row.get('device_boot_id'),release=row.get('device_release_id'),stop_receipt=row.get('stop_receipt')))
navigation=next(folder.glob('navigation-*.json'))
value=dict(scope='ORIGINAL_SAVED_UI_BOUNDARY_OBSERVATIONS_NOT_EXACT_FAILED_GUARD_SNAPSHOT',
    task_id=task['task_id'],state=task['state'],reason=task['reason'],events=task['events'],samples=samples,
    task_sha256=hashlib.sha256((folder/'task.json').read_bytes()).hexdigest(),
    navigation=json.loads(navigation.read_bytes()))
with target.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps(dict(path=str(target),samples=len(samples),state=task['state'],reason=task['reason'],
    summaries=[{k:r[k] for k in ('at','control_state','observation_age_ms','observation_sha256','motion_epoch')} for r in samples])))
