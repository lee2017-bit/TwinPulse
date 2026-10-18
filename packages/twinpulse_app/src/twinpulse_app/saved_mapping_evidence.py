# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Verified exported ROS bytes -> declared-time offline diagnostic data."""
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import re

from twinpulse_core.ros_cdr import decode_mapping_message
from twinpulse_core.observation_stream import RecordedObservationSource
from twinpulse_core.room_localization import PoseTimeline, planar_pose, angle
from .offline_evidence_review import review_saved_evidence
from .session_history import review_project_session
from .command_broker import BrokerError

from .runtime_paths import resource_root
SOURCE_ROOT=resource_root()


def load_saved_mapping(root, project_id, job_id):
    if type(job_id) is not str or not re.fullmatch('[a-f0-9]{32}',job_id):
        raise ValueError('EXACT_SESSION_ID_REQUIRED')
    root=Path(root).resolve()
    # The immutable project index and PC journal bind ownership before reading.
    review_project_session(root,project_id,job_id)
    verified=review_saved_evidence(root,job_id)
    if verified['status']!='COMPLETE':raise ValueError('SAVED_ORIGINALS_NOT_COMPLETE')
    evidence=root/'artifacts/manual-control'/job_id/'robot-evidence'
    report=json.loads((evidence/'report.json').read_text(encoding='utf-8'))
    module_path=SOURCE_ROOT/'packages/twinpulse_robot_safety/raw_ros_record.py'
    spec=importlib.util.spec_from_file_location('tp_mapping_raw_inspector',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frames=module.inspect_recording(evidence/'ros-messages.raw')
    common_source = RecordedObservationSource(frames,decode_mapping_message,
        {'project_id':project_id,'session_id':job_id,'boot_id':report['boot_id'],
         'release_id':report['release_id'],'source_revision':report['raw_ros']['sha256'],'origin':'recorded_ros'})
    scans=[];odom=[];transforms=[];counts=Counter();errors=[]
    for metadata,payload in frames:
        kind=metadata['type']
        if kind not in {'sensor_msgs/msg/LaserScan','nav_msgs/msg/Odometry','tf2_msgs/msg/TFMessage'}:continue
        try:
            value=decode_mapping_message(kind,payload)
            common_source.window.receive(metadata['topic'],value,metadata['sequence'],metadata['receipt_monotonic_ns'])
            value['raw_sequence']=metadata['sequence'];value['receipt_monotonic_ns']=metadata['receipt_monotonic_ns']
            counts[metadata['topic']]+=1
            if kind=='sensor_msgs/msg/LaserScan':scans.append(value)
            elif kind=='nav_msgs/msg/Odometry':odom.append(value)
            else:transforms.extend(value['transforms'])
        except (ValueError,KeyError,TypeError) as exc:
            errors.append({'raw_sequence':metadata['sequence'],'topic':metadata['topic'],'reason':str(exc)[:100]})
    if errors:
        raise BrokerError('mapping_cdr_decode_failed',json.dumps({'count':len(errors),'first_errors':errors[:4]}),status=409)
    if not scans or not odom:raise ValueError('SCAN_AND_ODOM_REQUIRED')
    if len(scans)>8192:raise ValueError('SCAN_REPLAY_FRAME_BUDGET')
    if any(a['stamp_ns']>=b['stamp_ns'] for a,b in zip(scans,scans[1:])):
        raise ValueError('SCAN_SOURCE_CLOCK_RESET_OR_DUPLICATE')
    if len({s['frame_id'] for s in scans})!=1:raise ValueError('SCAN_FRAME_CHANGED')
    timeline=PoseTimeline(odom)
    # A dynamic TF agreeing with odom does not establish sensor extrinsics.
    by_stamp={r['stamp_ns']:r for r in odom};tf_compared=0;tf_conflicts=0
    for tf in transforms:
        if tf['frame_id']!='odom' or tf['child_frame_id']!=odom[0]['child_frame_id']:continue
        other=by_stamp.get(tf['stamp_ns'])
        if other is None:continue
        a=planar_pose(other);b=planar_pose({'position_m':tf['translation_m'],'quaternion_xyzw':tf['quaternion_xyzw']})
        tf_compared+=1
        if math.dist(a[:2],b[:2])>.001 or abs(angle(a[2]-b[2]))>.001:tf_conflicts+=1
    if tf_conflicts:raise ValueError('ODOM_DYNAMIC_TF_CONFLICT')
    return {'job_id':job_id,'boot_id':report['boot_id'],'release_id':report['release_id'],
            'source_revision':report['raw_ros']['sha256'],'source_status':report['status'],
            'scans':scans,'odom':odom,'timeline':timeline,
            'diagnostics':{'decoded_counts':dict(counts),'dynamic_tf_odom_compared':tf_compared,
                'dynamic_tf_conflicts':tf_conflicts,'mapping_cdr_decode':'COMPLETE',
                'other_message_types':'PRESERVED_RAW_NOT_DECODED_BY_MAPPING_ADAPTER',
                'tf_static_count':counts['/tf_static'],'sensor_extrinsic':'NOMINAL_MODEL_NOT_AS_BUILT',
                'scan_timing':'DECLARED_HEADER_NOT_VERIFIED_FIRST_RAY',
                'beam_order':'DECLARED_INDEX_NOT_VERIFIED_ACQUISITION_ORDER',
                'raw_bytes_verified':True,'physical_validation':'NOT_RUN_BY_THIS_REVIEW',
                'common_observation_health':common_source.window.summary()}}


def saved_observation_source(root, project_id, job_id):
    """Project-bound causal source for the automatic runner; no localization I/O.

    Verify all exact bytes before yielding the first decoded message. Unlike
    load_saved_mapping this does not build a full pose timeline or require scan
    and odom both to be present, so independent diagnostics continue on gaps.
    """
    if type(job_id) is not str or not re.fullmatch('[a-f0-9]{32}',job_id):
        raise ValueError('EXACT_SESSION_ID_REQUIRED')
    root = Path(root).resolve()
    review_project_session(root,project_id,job_id)
    verified = review_saved_evidence(root,job_id)
    if verified['status'] != 'COMPLETE': raise ValueError('SAVED_ORIGINALS_NOT_COMPLETE')
    folder = root/'artifacts/manual-control'/job_id/'robot-evidence'
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('tp_causal_raw_inspector',
        SOURCE_ROOT/'packages/twinpulse_robot_safety/raw_ros_record.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    source = RecordedObservationSource(module.inspect_recording(folder/'ros-messages.raw'),
        decode_mapping_message,{'project_id':project_id,'session_id':job_id,'boot_id':report['boot_id'],
        'release_id':report['release_id'],'source_revision':report['raw_ros']['sha256'],'origin':'recorded_ros'})
    source.original_status=report['status']
    source.original_reason=report.get('reason')
    return source
