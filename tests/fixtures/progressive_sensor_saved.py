# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""TEST ONLY: authored raycasts -> typed CDR -> normal saved readers/mapping.

No backend injection, alignment result, ACK or success receipt is authored.
Selected real bundles are copied byte-for-byte with their original attribution.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
from uuid import uuid4
from types import SimpleNamespace

from twinpulse_app.application import ApplicationService
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.project_store import AutomaticMapStore
from twinpulse_app.robot_geometry_evidence import load_geometry_evidence
from twinpulse_app.robot_evidence_export import expected_files
from twinpulse_app.saved_mapping_evidence import saved_observation_source
from twinpulse_app.session_history import index_project_session,review_project_session
from twinpulse_core import SiteToolPlan,canonical_sha256
from twinpulse_core.automatic_mapping import AutomaticMapping
from twinpulse_core.room_localization import compose,inverse
from packages.twinpulse_core.tests.test_automatic_mapping import observations
from packages.twinpulse_core.tests.test_automatic_photo_alignment import room
from packages.twinpulse_core.tests.test_ros_cdr import Writer

ROOT=Path(__file__).resolve().parents[2]


def _json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,sort_keys=True,allow_nan=False)


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _header(writer,data):
    writer.put('iI',4,*divmod(data['stamp_ns'],1_000_000_000));writer.string(data['frame_id'])


def _cdr(topic,data):
    w=Writer()
    if topic=='scan':
        _header(w,data)
        w.put('7f',4,*(data[k] for k in ('angle_min','angle_max','angle_increment','time_increment','scan_time','range_min','range_max')))
        ranges=[float('inf') if value is None else value for value in data['ranges_m']]
        w.put('I',4,len(ranges));w.put(str(len(ranges))+'f',4,*ranges);w.put('I',4,0)
    elif topic=='odom':
        _header(w,data);w.string(data['child_frame_id']);w.put('3d',8,*data['position_m'])
        w.put('4d',8,*data['quaternion_xyzw']);w.put('36d',8,*([0]*36));w.put('6d',8,*([0]*6));w.put('36d',8,*([0]*36))
    else:raise ValueError('TEST_CDR_TOPIC_UNSUPPORTED')
    return bytes(w.data)


def _save_map(root,project_id,job,map_id,geometry):
    source=saved_observation_source(root,project_id,job)
    base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
    processor=AutomaticMapping(source.window.context,[base[0]+mount[0],base[1]+mount[1],0.])
    for event in source:processor.consume(event)
    processor.finish()
    body=processor.saved_map();body.update(source_job_id=job,nominal_geometry_revision=geometry['revision'],
        source_status=source.original_status,source_reason=source.original_reason,processing_summary=processor.snapshot())
    body.pop('revision');body['revision']=canonical_sha256(body)
    AutomaticMapStore(root,project_id).save(map_id,body)
    return dict(source_job_id=job,map_id=map_id,map_revision=body['revision'],keyframes=len(body['keyframes']),
        status=processor.state,reason=processor.failed)


def _synthetic_raw(root,project_id,outline,geometry,*,completed_survey=False,survey_scope=None):
    job=uuid4().hex;session='manual-'+job;boot='synthetic-'+job;release='b'*64
    folder=root/'artifacts/manual-control'/job;bundle=folder/'robot-evidence';bundle.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('tp_test_sensor_raw',ROOT/'packages/twinpulse_robot_safety/raw_ros_record.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    recorder=module.RawRosRecorder(bundle/'ros-messages.raw',serializer=lambda v:v)
    positions=[[.35*math.sin(i*.045),-.7+i*.006,.35+i*.004] for i in range(180)]
    base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
    offset=[base[0]+mount[0],base[1]+mount[1],0.]
    odom=[compose(position,inverse(offset)) for position in positions]
    context=dict(project_id=project_id,session_id=session,boot_id=boot,release_id=release,source_revision='a'*64,origin='recorded_ros')
    for event in observations(positions,odom_positions=odom,outline=outline,context=context):
        if not recorder.record(event['topic'],_cdr(event['topic'],event['data']),receipt_monotonic_ns=event['receipt_monotonic_ns']):
            raise ValueError('TEST_RAW_RECORD_REJECTED')
    footer=recorder.close()
    if json.loads((bundle/'ros-messages.raw.footer.json').read_text(encoding='utf-8'))!=footer:
        raise ValueError('TEST_RAW_FOOTER_CHANGED')
    mode='mission' if completed_survey else 'control_scan'
    status='MISSION_ARRIVED' if completed_survey else 'FAILED'
    report=dict(robot_session_id=session,mode=mode,boot_id=boot,release_id=release,
        raw_ros=footer,status=status,reason='SYNTHETIC_TEST_ONLY',synthetic=True)
    if completed_survey:report.update(cleanup_confirmed=True,sensor_cleanup_confirmed=True,
        physical_validation='NOT_RUN',physical_authority=False)
    _json(bundle/'report.json',report)
    for name in expected_files(report):
        if not (bundle/name).exists():
            if name.endswith('.json'):_json(bundle/name,{'synthetic':True})
            else:
                with (bundle/name).open('x',encoding='utf-8') as stream:stream.write('SYNTHETIC_TEST_ONLY\n')
    receipt=dict(schema_version='robot-session-export-1',robot_session_id=session,mode=report['mode'],
        robot_originals_retained=True,binding='VERIFIED',status='COMPLETE',
        files={name:dict(status='COPIED',bytes=(bundle/name).stat().st_size,sha256=_sha(bundle/name)) for name in expected_files(report)})
    _json(bundle/'export.json',receipt)
    rows=[dict(schema='control-session-1.0',job_id=job,event_index=1,clock_domain='pc_monotonic',t=1.,
        kind='pc_session_started',real_transport=False,data=dict(mode=mode,project_id=project_id)),
        dict(schema='control-session-1.0',job_id=job,event_index=2,clock_domain='pc_monotonic',t=2.,
        kind='robot_event',real_transport=False,data={'event':dict(schema='robot-session-1.0',robot_session_id=session,
            event_index=1,clock_domain='robot_monotonic',t=1.,kind='session_started',
            data=dict(mode=mode,boot_id=boot,release_id=release))}),
        dict(schema='control-session-1.0',job_id=job,event_index=3,clock_domain='pc_monotonic',t=3.,
        kind='robot_finished',real_transport=False,data=dict(status=status,reason='SYNTHETIC_TEST_ONLY',robot_session_id=session,cleanup_confirmed=True))]
    if completed_survey:
        for n,kind,data in ((3,'mission_started',dict(mission_id=job,request_sha256='c'*64)),
                (4,'mission_finished',dict(mission_id=job,status=status))):
            rows.insert(n-1,dict(schema='control-session-1.0',job_id=job,event_index=n,clock_domain='pc_monotonic',t=float(n),
                kind='robot_event',real_transport=False,data={'event':dict(schema='robot-session-1.0',robot_session_id=session,
                    event_index=n-1,clock_domain='robot_monotonic',t=float(n-1),kind=kind,data=data)}))
        rows[-1].update(event_index=5,t=5.)
        if survey_scope is None:raise ValueError('TEST_SURVEY_SCOPE_REQUIRED')
        rows.insert(1,dict(schema='control-session-1.0',job_id=job,event_index=2,clock_domain='pc_monotonic',t=2.,
            kind='mission_scope',real_transport=False,data=dict(scope=survey_scope,scope_sha256=canonical_sha256(survey_scope))))
        for index,row in enumerate(rows,1):row.update(event_index=index,t=float(index))
    with (folder/'session.jsonl').open('x',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,sort_keys=True)+'\n')
    pc_result=dict(session_log_complete=True,session_event_count=len(rows),real_transport=False)
    if completed_survey:pc_result.update(state='FINISHED',result=status,cleanup_confirmed=True,sensor_cleanup_confirmed=True,
        evidence_export='COMPLETE',physical_verified=False)
    _json(folder/'result.json',pc_result)
    index_project_session(root,project_id,job)
    return job


def _unregistered_survey(root,project_id,record,outline,geometry):
    """Authored terminal lifecycle only; mapping/fit/engine/physical success NOT injected."""
    scene=record.site.scene.to_dict()
    room_body=dict(project_id=project_id,input_revision=record.input_revision.digest,scene_revision=scene['revision'],
        objects=scene['objects'],adapter='current-chat-room-1.0',photo_revision=None)
    source=dict(room={**room_body,'revision':canonical_sha256(room_body)},scene=scene)
    from twinpulse_core.adaptive_mission_contract import adaptive_scope,nominal_room
    goal=dict(mode='SURVEY_ONLY',xy=[0.,0.],duration_s=45.,room_revision=source['room']['revision'])
    base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
    scope=adaptive_scope(dict(schema='observed-mission-scope-4.0',project_id=project_id,goal=goal,reference=None,alignment=None,
        nominal=nominal_room(scene['objects'],base[2]+mount[2],goal['room_revision'])))
    job=_synthetic_raw(root,project_id,outline,geometry,completed_survey=True,survey_scope=scope)
    report=dict(schema='automatic-mission-report-1.0',project_id=project_id,job_id=job,
        goal=goal,state='MISSION_ARRIVED',cold_start={'stage':'SURVEY_COMPLETE'},room_source=source,
        room_base_revision=source['room']['revision'],
        result=dict(status='MISSION_ARRIVED',mission_id=job,robot_job_id=job,sensor_cleanup_confirmed=True,evidence_export='COMPLETE'),
        provenance='SYNTHETIC_TRANSPORT',physical_validation='NOT_RUN',physical_authority=False,
        synthetic_purpose='Explicit typed terminal lifecycle fixture; no physical mission or alignment result')
    report['revision']=canonical_sha256(report)
    _json(root/'artifacts/automatic-mission'/project_id/(job+'.json'),report)
    from twinpulse_app.scene_sensor_import import SceneSensorImport,survey_map_id
    importer=SceneSensorImport(SimpleNamespace(root=root,maps=AutomaticMapStore(root,project_id)))
    witness,_,_=importer.witness(job)
    return dict(mission_id=job,report_revision=report['revision'],source_job_id=job,
        expected_map_id=survey_map_id(witness),provenance='SYNTHETIC_TRANSPORT')


def build_test_sensor_history(history_root,project_id='default',*,real_history_root=None,real_job_ids=()):
    root=Path(history_root).resolve();root.mkdir(parents=True,exist_ok=True)
    outline,objects=room()
    plan=dict(plan_version='2.0',scene_id='synthetic_sensor_current',summary='Explicit synthetic approximate Twin',
        image_observations='Test-only authored scene; not a real photo or measured room',calls=[
            dict(call_id='floor',tool='create_floor',arguments=dict(id='floor',center_m=[0,0],size_m=[3,4]))])
    for obj in objects[1:-1]:
        position=deepcopy(obj['transform']['position_m'])
        if obj['id']=='wall_4':position[1]+=.12
        plan['calls'].append(dict(call_id=obj['id'],tool='create_wall',arguments=dict(id=obj['id'],position_m=position,
            dimensions_m=obj['shape']['dimensions_m'],yaw_deg=obj['transform']['rotation_rpy_deg'][2])))
    # Keep an unrelated materialized object to check the nonwall scope.
    plan['calls'].append(dict(call_id='chair',tool='create_box_obstacle',arguments=dict(id='chair',center_m=[.8,-.7],dimensions_m=[.2,.2,.5],yaw_deg=0)))
    plan['call_evidence']=[dict(call_id=c['call_id'],observation_ids=[],basis='inferred',note='Explicit synthetic regression; not measured') for c in plan['calls']]
    input_body=dict(name=None,media_type=None,content_base64=None,input_kind='auto',prompt='Explicit synthetic approximate sensor Twin',sidecar_name=None,sidecar_content_base64=None)
    prepared=ApplicationService.prepare_input(prompt=input_body['prompt'],images=(),measurement_constraints=(),generation_settings={'model_id':'offline-sensor-fixture'})
    record=SiteDraftRecord.create(request_id='synthetic-sensor-fixture',provider_name='explicit_fixture',model_id='offline-sensor-fixture',
        image_count=0,input_revision=prepared.revision,plan=SiteToolPlan.from_dict(plan))
    geometry=load_geometry_evidence()
    job=_synthetic_raw(root,project_id,outline,geometry)
    positive=_save_map(root,project_id,job,uuid4().hex,geometry);positive['wall_id']='wall_4'
    survey=_unregistered_survey(root,project_id,record,outline,geometry)
    real=[]
    for job_id in real_job_ids:
        if real_history_root is None:raise ValueError('REAL_HISTORY_ROOT_REQUIRED')
        original=Path(real_history_root).resolve()
        # Only original project-bound bundles may be selected; no reattribution.
        review_project_session(original,project_id,job_id)
        old=original/'artifacts/manual-control'/job_id;report=json.loads((old/'robot-evidence/report.json').read_text(encoding='utf-8'))
        paths=[old/'session.jsonl',old/'result.json',original/'artifacts/project-session-index'/project_id/(job_id+'.json')]
        paths.extend(old/'robot-evidence'/name for name in (*expected_files(report),'export.json'))
        for path in paths:
            target=root/path.relative_to(original)
            if path.is_symlink() or not path.resolve().is_relative_to(original):raise ValueError('TEST_SOURCE_PATH_UNSAFE')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise ValueError('TEST_SOURCE_COPY_EXISTS')
            shutil.copyfile(path,target)
            if _sha(path)!=_sha(target):raise ValueError('TEST_SOURCE_COPY_CHANGED')
        real.append(_save_map(root,project_id,job_id,uuid4().hex,geometry))
    return dict(source_record=record,input_body=input_body,positive=positive,pose_only=deepcopy(positive),real_maps=real,survey=survey,
        fingerprints={str(p):_sha(p) for p in root.rglob('*') if p.is_file()},provenance='SYNTHETIC_TRANSPORT')
