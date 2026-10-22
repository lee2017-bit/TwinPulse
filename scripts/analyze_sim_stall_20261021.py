# SPDX-License-Identifier: Apache-2.0
"""Read-only attribution from preserved original08; no new App or sensor work."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
folder=OUT/'failed-ui08-original-logs'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def main():
    rows=[]
    for p in sorted(folder.glob('*-*.json')):
        if len(p.name.split('-',1)[-1].split('.')[0])!=32:continue
        value=read(p)
        for index,e in enumerate(value.get('events',[])):
            work=e.get('runtime_work') or {}
            if work.get('scan_s',0)>.1:
                rows.append(dict(file=ref(p),zero_based_event_index=index,
                    original={k:e.get(k) for k in ('event_sequence','utc','monotonic_s','kind','operation_id','project_id',
                        'robot_id','connection_epoch','motion_epoch','telemetry_sequence','position_m','runtime_work','runtime_timing')},
                    original_scan={k:(e.get('scan') or {}).get(k) for k in ('captured_at_ms','height_m','geometry','sensor_xy_yaw_world','position_m')}))
    result=read(folder/'04-engine-result.json')
    value=dict(classification='READ_ONLY_ORIGINAL08_DIAGNOSTIC_NOT_NEW_ACCEPTANCE',
        original_launch_id=read(folder/'receipt.json')['launch_id'],engine_result=ref(folder/'04-engine-result.json'),
        host_worst=result.get('host_phase_diagnostics',{}).get('worst_phase'),
        viewport_worst=result.get('viewport_phase_diagnostics',{}).get('worst_phase'),slow_original_scans=rows,
        confirmed='Beta synchronous scan block671ms within fleet_update685ms followed APP.update438ms; combined about1.127s matches the original frame-age failure.',
        unknown=['671ms sensor_pose vs section build vs pure raycast was not subdivided in original08.',
            'Process soft/hard combined page-fault count is not proof of disk paging as sole cause.',
            'Original03 6.53s stall and original05 physical producer/executor latency remain separately UNKNOWN.'],
        unchanged='No timeout/speed/geometry policy changed. Frozen original event/receipt bytes are not edited.')
    target=OUT/'original08-stall-analysis.json'
    with target.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(path=str(target),slow_scan_events=len(rows))))
if __name__=='__main__':main()
