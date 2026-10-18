# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only AD1 actual-recording regression. Never contacts a robot."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from twinpulse_app.saved_mapping_evidence import saved_observation_source,load_saved_mapping
from twinpulse_app.robot_geometry_evidence import load_geometry_evidence
from twinpulse_app.session_history import review_session
from twinpulse_core.scan_observation import build_observation_map
from robot_source_identity import source_id
SESSIONS={'4493be87ef7643ababb661b4a12f0180':(2318,4678,2317,1),
          'b6cf346718da44b99e7bffe6f7919bbf':(1213,2472,1212,1),
          '1a7f033af112437699ca67aef3438ecb':(30,108,25,5)}

def verify(root):
    root=Path(root).resolve();geometry=load_geometry_evidence(root);results=[]
    for job,(scans,odom,paired,rejected) in SESSIONS.items():
        folder=root/'artifacts/manual-control'/job/'robot-evidence'
        paths=list(folder.glob('*'))+[folder.parent/'session.jsonl',folder.parent/'result.json']
        paths=[p for p in paths if p.is_file()]
        hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        source=saved_observation_source(root,'default',job);counts=Counter();faults=Counter();last=-1
        for event in source:
            assert event['sequence']>last;last=event['sequence'];counts[event['topic']]+=1
            if event.get('status')=='REJECTED':faults[event['reason']]+=1
        assert counts=={'scan':scans,'odom':odom,'/tf':odom}
        assert not faults and not source.window.clock_fault
        health=source.window.summary();assert not health['motion_authorized'] and not health['alignment_verified']
        assert health['faults']['/tf_static']=='NOT_RECEIVED'
        evidence=load_saved_mapping(root,'default',job)
        base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
        child=evidence['odom'][0]['child_frame_id'];assert child in ('base_footprint','base_link')
        offset=[mount[0]+(base[0] if child=='base_footprint' else 0),
                mount[1]+(base[1] if child=='base_footprint' else 0),0.]
        observed=build_observation_map(evidence['scans'],evidence['timeline'],offset)
        assert (observed['paired_frames'],observed['rejected_frames'])==(paired,rejected)
        if job.startswith('1a7'):assert report['status']=='FAILED' and report['reason']=='INPUT_DEADLINE_EXPIRED'
        for p in paths:assert hashes[str(p.relative_to(root))]==hashlib.sha256(p.read_bytes()).hexdigest()
        review=review_session(root,job)
        results.append({'job_id':job,'counts':dict(counts),'rejected_common_messages':dict(faults),
            'paired_scans':paired,'rejected_scans':rejected,'pairing_failures':dict(Counter(v['reason'] for v in observed['failures'])),
            'source_status':report['status'],'source_reason':report.get('reason'),
            'deployed_release':report['release_id'],'originals_unchanged':True,
            'raw_sha256':report['raw_ros']['sha256'],'common_health':health,
            'transport_diagnostics':review['transport_diagnostics']})
    return {'schema':'ad1-offline-verification-1.0','status':'PASS','sessions':results,
            'nominal_geometry':{'revision':geometry['revision'],
                'base_link_to_scan_xyz_m':geometry['base_link_to_scan_xyz_m'],
                'nominal_envelope_radius_m':geometry['nominal_envelope_radius_m'],
                'retained_guard_radius_m':geometry['retained_guard_radius_m'],
                'physical_robot_match':geometry['physical_robot_match'],
                'alignment_verified':False},
            'local_source_id':source_id(root),'local_source_deployed':False,
            'target_build':'TARGET_BUILD_NOT_RUN','robot_contacts':0,'physical_validation':'NOT_RUN',
            'timing_verified':False,'calibration_verified':False,'motion_authorized':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();result=verify(ROOT);path=Path(args.output)
    with path.open('x',encoding='utf-8') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sessions'},indent=2))
    for row in result['sessions']:print(row['job_id'],row['counts'],row['paired_scans'],row['rejected_scans'])
