# SPDX-License-Identifier: Apache-2.0
"""Exact saved15/17 failure attribution. No App/network/device or result edits."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha256(p.read_bytes()).hexdigest())
def main():
    old=OUT/'failed-ui15-original-logs';repro=OUT/'failed-ui-reproduction17-original-logs'
    for folder in (old,repro):
        for row in read(folder/'receipt.json')['files']:
            if row.get('status')=='COPIED_EXACT':
                actual=ref(folder/row['path'])
                if any(actual[k]!=row[k] for k in ('bytes','sha256')):raise ValueError('ORIGINAL_CHANGED')
    op=old/'10-a479fcaae56c4655adc47c2980b8f87f.json'
    event=next(e for e in read(op)['events'] if e.get('kind')=='motion_result' and e.get('reason')=='ISAAC_UPDATE_STALLED')
    host=read(old/'04-engine-result.json')['host_phase_diagnostics']
    tail=next(e for e in host['recent_stalls'] if e['phase']=='host_tail' and abs(e['entered_monotonic_s']-event['runtime_fault']['observed_monotonic_s'])<2)
    ui=read(OUT/'ui-reproduction-17/result.json');at=1792529287440
    receipts=[dict(relative_ms=e['at']-at,path=e['path'],state=e['state'],frame_id=(e.get('frame')or{}).get('frame_id'),
        frame_age_ms=e['at']-(e.get('frame')or{}).get('captured_at_ms',e['at']))
        for e in ui['viewport_receipt_trace']['receipts'] if abs(e.get('at',0)-at)<1600]
    network=[dict(relative_ms=e['at']-at,path=e['path'],browser_request_id=e['browser_request_id'],
        native_response_ms=1000*(e['response_cdp_timestamp']-e['cdp_timestamp']),callback_relative_ms=e['response_node_received_at']-at)
        for e in ui['viewport_network_timings'] if abs(e.get('at',0)-at)<1600]
    value=dict(classification='READ_ONLY_ORIGINAL_FAILURES_NOT_NEW_ACCEPTANCE',
        original15=dict(launch_id=read(old/'receipt.json')['launch_id'],operation=ref(op),
            original_event=event,original_same_time_tail=tail,
            confirmed='Original dt .796s includes preceding host tail .703s; Kit render gap811ms. Worker47ms/cache hit. Movement .51485m stopped early, not obstacle result.',
            unknown='Original tail substage/CPU/GC unavailable. APP-only GC0 does not exclude tail or other-thread GC. Early APP3.25s/GC1.703s is another time.'),
        original17=dict(launch_id=ui['desktop']['engine']['launch_id'],ui=ref(OUT/'ui-reproduction-17/result.json'),
            engine=ref(repro/'04-engine-result.json'),failure_at_ms=at,failure=ui['error'],receipts=receipts,network=network,
            confirmed='90-degree engine task later completed, but displayed frame674 exceeded original1s at1043.9565ms. Sequential metadata311ms then a later JPEG request delayed display. Tail worst88ms, not original15 tail703ms recurrence.',
            unknown='Multiple transport/render/scheduling stages contributed; removing one sequential request is not proof of sole-cause repair.'),
        source_change='Live atomic metadata+JPEG single request; explicit rebuild static path and JPEG-less cold-history fallback preserve original identities and1s expiry. Tail diagnostic exceptions cannot mask body.',
        not_claimed=['No timeout relaxation','No new original fault backfill','No physical/SIM PASS from these failed runs','No proof that historical15 tail sole cause was repaired'])
    with (OUT/'followup15-17-analysis.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(dict(path=str(OUT/'followup15-17-analysis.json'),receipt_count=len(receipts),network_count=len(network))))
if __name__=='__main__':main()
