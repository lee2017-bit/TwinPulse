# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic receipts test the gate only, never count as App acceptance."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import runpy
import tempfile
import unittest

module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/verify_robot_focus_gate.py'))
validate=module['validate_records'];required=module['REQUIRED']


class BodyEscapeGateTests(unittest.TestCase):
    def observation(self):
        def row(x,y,reason=None):
            return dict(robot_id='beta',operation_id='op',connection_epoch='connection',
                pose=dict(position_m=[x,y,-.5015999997298083],frame_id='isaac_world',source='isaac_usd_kinematic',aligned=True),
                reason=reason,command=dict(state='COMPLETED' if reason=='TASK_COMPLETED' else 'FAILED'))
        yaw=-.5015999997298083
        a=row(0,0);b=row(.11*math.cos(yaw),.11*math.sin(yaw),'OBSTACLE_STOP')
        c=row(.01*math.cos(yaw),.01*math.sin(yaw),'TASK_COMPLETED')
        return dict(steps=[dict(name='Actual obstacle approach stops Beta and fresh reverse escapes',evidence=dict(before=a,stopped=b,escaped=c))])
    def test_original_rotated_body_criteria_not_world_axis(self):
        self.assertTrue(module['body_escape_verified'](self.observation()))
    def test_missing_wrong_direction_lateral_and_identity_rejected(self):
        for alteration in ('missing','direction','lateral','identity','nonfinite','huge','incomplete','before_list','pose_list','command_list','command_null'):
            value=self.observation();evidence=value['steps'][0]['evidence'];row=evidence['escaped']
            if alteration=='missing':evidence.pop('before')
            elif alteration=='direction':row['pose']['position_m'][:2]=[.2*math.cos(-.5016),.2*math.sin(-.5016)]
            elif alteration=='lateral':row['pose']['position_m'][1]+=.02
            elif alteration=='identity':row['operation_id']='other'
            elif alteration=='nonfinite':row['pose']['position_m'][0]=math.nan
            elif alteration=='huge':row['pose']['position_m'][0]=10**1000
            elif alteration=='before_list':evidence['before']=[]
            elif alteration=='pose_list':row['pose']=[]
            elif alteration=='command_list':row['command']=[]
            elif alteration=='command_null':row['command']=None
            else:row['command']['state']='RUNNING'
            with self.subTest(alteration=alteration):self.assertFalse(module['body_escape_verified'](value))

def fixture():
    rows={role:dict(status='PASS',project='p',phase={'fresh':'fresh','cold':'reopen','lineage':'run','lineage_cold':'cold'}[role],
        desktop=dict(engine=dict(release_id='release')),steps=[dict(name=n,status='PASS',evidence={}) for n in names]) for role,names in required.items()}
    normal=[n for n in required['fresh'] if not n.startswith('FAULT') and n!='Visible Exit TwinPulse normal shutdown']
    rows['fresh'].update(normal_steps_before_fault_window=normal,fault_window_held_until_exit=True)
    rows['fresh']['registration_history']=dict(project_id='p',session_id='session',entries=[dict(robot_id=n) for n in ('Alpha','Beta')])
    scan=dict(present=True,visible=True,frame_live=True,preview_only=False,requested_at_ms=1600,received_at_ms=1700,captured_at_ms=1000.25,observed_at_ms=1699,age_ms=698.75,frame_id=2,
        frame_captured_at_ms=1650,robot_id='a',stage_epoch='stage',scene_revision='scene',connection_epoch='connection',motion_epoch='motion',rays_count=1,points_count=2)
    next(s for s in rows['fresh']['steps'] if s['name'].startswith('Frame-bound selected LiDAR'))['evidence']['scan_display']=scan
    rows['fresh']['scan_display_observations']=[deepcopy(scan)]
    window=dict(started_at_ms=1600,deadline_ms=6600,timeout_ms=5000,expected={k:scan[k] for k in ('robot_id','connection_epoch','motion_epoch')})
    rows['fresh']['scan_display_window']=window
    next(s for s in rows['fresh']['steps'] if s['name'].startswith('Frame-bound selected LiDAR'))['evidence']['scan_display_window']=deepcopy(window)
    next(s for s in rows['fresh']['steps'] if s['name']=='Physical setup shown while robot remains off; no Connect or movement')['evidence'].update(
        destination_policy_visible=True,off_destination_send_disabled=True,physical_destination_commands_sent=0)
    rows['cold']['registration_history']=deepcopy(rows['fresh']['registration_history'])
    rows['fresh']['steps'].sort(key=lambda s:0 if s['name'] in normal else 2 if s['name']=='Visible Exit TwinPulse normal shutdown' else 1)
    for s in rows['fresh']['steps']:
        if s['name']=='Main chat bounded 90 degree command, measured completion':s['evidence']['delta']=math.pi/2
        if s['name']=='One session full turn with actual simulated scan':s['evidence']['delta']=2*math.pi
    rows['lineage']['requested_command']='left 90 degrees'
    motion=dict(operation_id='saved-physical',job_id='job',input_receipt_sha256='receipt',review_sha256='review',input_segments_sha256='segments',input_rows=10,
        physical_activation=0,physical_motion_verified=False,raw_receipt_sha256_checked=True)
    next(s for s in rows['lineage']['steps'] if s['name']=='Original physical recording motion review runs offline with exact IDs and no restored authority')['evidence']=dict(motion,analysis_post_count=1)
    next(s for s in rows['lineage_cold']['steps'] if s['name']=='Saved physical motion review cold reopens without Analyze or restored authority')['evidence']=dict(motion,analysis_post_count=0)
    display=dict(at=1,frame_id=1,frame_age_ms=20,live=True,scene_revision='scene',stage_epoch='stage',canvas_visible=True,canvas=dict(height=300),intersection_px2=0,
        stop_visible=True,pad_visible=True,robot_badge_visible=True,robot_bounds=[.1,.2,.15,.3],origin_marker_count=0,label_under_body_error_px=0,label_horizontal_error_px=0)
    cold_prefix=[]
    for n in required['cold']:
        if n.startswith('FAULT'):break
        cold_prefix.append(n)
    rows['cold'].update(normal_steps_before_fault_window=cold_prefix,fault_window_held_until_exit=True)
    robots=[dict(robot_id=n,operation_id='op-'+n,connection_epoch='c-'+n,motion_epoch='new-'+n,applied_motion_epoch='new-'+n,control_state='PAUSED',connection_state='CONNECTED',lidar_state='STREAMING') for n in ('a','b')]
    rows['fresh']['final_fault_recovery']=dict(before=deepcopy(display),after=dict(display,frame_id=2),stopped_robots=robots,
        before_stop_robots=[dict(r,motion_epoch='old-'+r['robot_id']) for r in robots],stop_request_id='stop-id')
    rows['fresh']['fleet_requests']=[dict(action='stop_all',request_id='stop-id',status=200,result_robots=deepcopy(robots))]
    rows['fresh']['display_samples']=[dict(display,frame_id=i+1,at=1+i*500) for i in range(120)]
    next(s for s in rows['fresh']['steps'] if s['name'].startswith('Non-overlapping dock'))['evidence']['rows']=[dict(deepcopy(display),window=dict(width=w,height=h)) for w,h in [(1920,1080),(1366,768),(1093,614),(911,512),(1600,900)]]
    next(s for s in rows['fresh']['steps'] if s['name'].startswith('Non-overlapping dock'))['evidence']['bodySelections']=[dict(name=n,bodyHit=True,origin_marker_count=0,label_under_body_error_px=.01,label_horizontal_error_px=.01) for n in ('Alpha','Beta')]
    next(s for s in rows['fresh']['steps'] if s['name']=='LiDAR Off pauses but retains connection; On restarts sensor')['evidence']['off']=dict(overlay_count=0,sensor_state='OFF',observed_ms=900)
    def robot_pose(x,reason=None):
        return dict(robot_id='beta',operation_id='beta-op',connection_epoch='beta-connection',
            pose=dict(position_m=[x,0,0],frame_id='isaac_world',source='isaac_usd_kinematic',aligned=True),
            reason=reason,command=dict(state='COMPLETED' if reason=='TASK_COMPLETED' else 'FAILED'))
    next(s for s in rows['fresh']['steps'] if s['name']=='Actual obstacle approach stops Beta and fresh reverse escapes')['evidence'].update(
        before=robot_pose(0),stopped=robot_pose(.11,'OBSTACLE_STOP'),escaped=robot_pose(.01,'TASK_COMPLETED'))
    rows['fresh']['sustained_hold_observations']=[dict(at=r['at']) for r in rows['fresh']['display_samples']]
    next(s for s in rows['fresh']['steps'] if s['name'].startswith('Continuous 60-second'))['elapsed_ms']=61000
    rows.update(normal=dict(status='PASS_NORMAL_START_REUSE_DEBUG_OFF',release_id='release',source_sha256='source',launch_id='first',ready_wait_ms=40000,
        debug_listener_count=0,app_listener_count=1,repeated_start_same_owner=True),
        installation=dict(status='PASS',release_id='release',source_manifest_sha256='source',mismatches=[],capabilities=dict(physical_robot=True)),
        lifecycle=dict(status='PASS',release_id='release',source_sha256='source',normal_start_launch_id='first',shutdown_clean=True,
            restart_ready=True,restart_shutdown_clean=True,restart_launch_id='second',restart_debug_listener_count=0,restart_app_listener_count=1,
            restart_authenticated_ready=True,restart_ready_wait_ms=45000),
        supplementary=dict(status='PASS',release_id='release',source_sha256='source',source_unchanged=True,
            groups=[dict(name=n,status='PASS') for n in ['lineage-and-pc','native-worker','field','ui','web-build']]),
        budget=dict(within_approved_total=True))
    return rows

def reproduction_fixture():
    row=fixture()['fresh'];row['phase']='reproduction'
    row['steps']=[s for s in row['steps'] if s['name'] not in module['REPRODUCTION_EXCLUDED']]
    row['steps'].insert(1,dict(name=module['REPRODUCTION_OPEN'],status='PASS',evidence=dict(project='p',expected_revision='scene')))
    next(s for s in row['steps'] if s['name']=='Two simultaneous real Isaac SIM connections and independent scan')['evidence']=[
        dict(kind='sim',connection_state='CONNECTED',source_twin_context=dict(scene_revision='scene')) for _ in range(2)]
    row['normal_steps_before_fault_window']=[s['name'] for s in row['steps'] if not s['name'].startswith('FAULT') and s['name']!='Visible Exit TwinPulse normal shutdown']
    return row

class GateTests(unittest.TestCase):
    def test_reproduction_requires_original_full_journey_and_same_geometry(self):
        check=module['reproduction_issues'];expected=dict(project='p',scene_revision='scene')
        self.assertEqual(check(reproduction_fixture(),'release',expected),[])
        for name in module['REPRODUCTION_REQUIRED']:
            row=reproduction_fixture();row['steps']=[s for s in row['steps'] if s['name']!=name]
            with self.subTest(missing=name):self.assertIn('REPRODUCTION_MISSING_OR_FAILED_STEP:'+name,check(row,'release',expected))
        for field,value,issue in (('phase','fresh','REPRODUCTION_NOT_WHOLE_PASS'),('project','other','REPRODUCTION_ORIGINAL_GEOMETRY_NOT_BOUND'),
                                 ('request_failures',[dict(path='/v1/product/projects')],'REPRODUCTION_UNCLASSIFIED_REQUEST_FAILURE')):
            row=reproduction_fixture();row[field]=value
            self.assertIn(issue,check(row,'release',expected))
        row=reproduction_fixture();row.pop('final_fault_recovery');row['fleet_requests']=[]
        self.assertIn('REPRODUCTION_FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN',check(row,'release',expected))
    def test_only_explicit_absence_may_precede_current_scan_within_shared_deadline(self):
        rows=fixture();last=rows['fresh']['scan_display_observations'][0]
        absent=dict(last,present=False,visible=False,captured_at_ms=None,age_ms=None)
        rows['fresh']['scan_display_observations']=[absent,last]
        self.assertNotIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
        for earlier in (dict(last,captured_at_ms=900,age_ms=799),dict(last,preview_only=True),dict(last,motion_epoch='wrong')):
            rows['fresh']['scan_display_observations']=[earlier,last]
            self.assertIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
        rows['fresh']['scan_display_observations']=[absent]
        self.assertIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
        rows=fixture();sample=rows['fresh']['scan_display_observations'][0];sample['received_at_ms']=6601
        next(s for s in rows['fresh']['steps'] if s['name'].startswith('Frame-bound selected LiDAR'))['evidence']['scan_display']=deepcopy(sample)
        self.assertIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
        rows=fixture();sample=rows['fresh']['scan_display_observations'][0]
        sample.update(observed_at_ms=6601,captured_at_ms=6590,frame_captured_at_ms=6590,age_ms=11)
        next(s for s in rows['fresh']['steps'] if s['name'].startswith('Frame-bound selected LiDAR'))['evidence']['scan_display']=deepcopy(sample)
        self.assertIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
    def test_atomic_scan_proof_cannot_be_missing_expired_hidden_or_unbound(self):
        for delta in ({'present':False},{'visible':False},{'frame_live':False},{'preview_only':True},{'preview_only':None},
                      {'age_ms':700,'observed_at_ms':1700.25},{'captured_at_ms':10**1000},
                      {'captured_at_ms':float('nan')},{'motion_epoch':None},{'frame_id':True}):
            rows=fixture()
            scan=next(s for s in rows['fresh']['steps'] if s['name'].startswith('Frame-bound selected LiDAR'))['evidence']['scan_display']
            scan.update(delta);rows['fresh']['scan_display_observations']=[deepcopy(scan)]
            self.assertIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
        rows=fixture();rows['fresh']['scan_display_observations']=[]
        self.assertIn('CURRENT_SCAN_DISPLAY_UNVERIFIED',validate(rows,'release','source'))
    def test_preview_cache_classification_rechecks_original_native_context_and_decode(self):
        digest='a'*64
        error=dict(path='/v1/product/viewport/preview/'+digest,method='GET',status=409,code='viewport_preview_expired',response_body_available=True,
            response_body=dict(code='viewport_preview_expired'),request_step='FAULT MATRIX: dispatch',request_fault_window=True,request_at=100,response_at=120,request_wall_time_ms=1000,
            context='ctx',response_context='ctx',current_context='ctx')
        frame=dict(frame_id=1,sha256=digest,preview_only=True,physical_authority=False,engine_session_id='engine',stage_epoch='stage',applied_revision='scene')
        proof=dict(classification='TYPED_PREVIEW_CACHE_REPLACEMENT_WITH_SAME_CONTEXT_DECODE',browser_request_id='native',sha256=digest,context='ctx',metadata_at=90,decoded_frame_id=3)
        row=dict(original_http_errors=[deepcopy(error)],http_errors=[],expected_preview_cache_miss=[dict(error=deepcopy(error),proof=proof)],final_fault_context='ctx',
            fault_window_held_until_exit=True,fetch_boundaries=[dict(action='after_enable',node_at=50,cdp_monotonic_s=.5)],
            viewport_network_timings=[dict(path=error['path'],method='GET',status=409,context_id='ctx',cdp_wall_time=1,cdp_timestamp=1,browser_request_id='native')],
            viewport_receipt_trace=dict(receipts=[dict(path='/v1/product/viewport',status=200,context='ctx',at=90,last_frame=frame,frame=dict(frame,frame_id=2)),
                dict(status=200,context='ctx',at=190,frame=dict(frame,frame_id=3))]),
            final_fault_recovery=dict(after=dict(at=200,live=True,frame_age_ms=10,frame_id=3,stage_epoch='stage',scene_revision='scene')))
        check=module['preview_cache_issues'];self.assertEqual(check(row),[])
        changes=[lambda r:r.update(original_http_errors=[]),lambda r:r['original_http_errors'].append(deepcopy(error)),
            lambda r:r['original_http_errors'].append(dict(error,request_wall_time_ms=1000.5)),
            lambda r:r['expected_preview_cache_miss'].append(deepcopy(r['expected_preview_cache_miss'][0])),
            lambda r:r.update(expected_preview_cache_miss=[]),lambda r:r['http_errors'].append(deepcopy(error)),
            lambda r:r.update(final_fault_context='other'),lambda r:r['viewport_network_timings'][0].update(status=403),
            lambda r:r['viewport_network_timings'].append(deepcopy(r['viewport_network_timings'][0])),
            lambda r:r['viewport_receipt_trace']['receipts'][0]['last_frame'].update(sha256='b'*64),
            lambda r:r['viewport_receipt_trace']['receipts'][0]['last_frame'].update(preview_only=False),
            lambda r:r['viewport_receipt_trace']['receipts'][0]['last_frame'].update(physical_authority=True),
            lambda r:r['viewport_receipt_trace']['receipts'][1].update(context='other'),
            lambda r:r['final_fault_recovery']['after'].update(live=False),lambda r:r['final_fault_recovery']['after'].update(frame_age_ms=1000),
            lambda r:r['final_fault_recovery']['after'].update(stage_epoch='wrong'),lambda r:r.update(fault_window_held_until_exit=False)]
        for change in changes:
            r=deepcopy(row);change(r);self.assertTrue(check(r))
        r=deepcopy(row)
        duplicate=dict(error,request_wall_time_ms=1000.5)
        r['original_http_errors'].append(duplicate)
        r['expected_preview_cache_miss'].append(dict(error=deepcopy(duplicate),proof=deepcopy(proof)))
        self.assertTrue(check(r)) # Equal counts cannot reuse the one native response.
        for key,value in [('method','POST'),('status',401),('status',403),('code','other'),('response_body_available',False),
                ('request_fault_window',False),('response_context','other'),('path','/v1/product/viewport/current')]:
            r=deepcopy(row);r['original_http_errors'][0][key]=value;r['expected_preview_cache_miss'][0]['error'][key]=value
            self.assertTrue(check(r))

    def test_candidate_offline_checks_cannot_replace_installed_supplementary_role(self):
        records=fixture();records['supplementary']['inspection_target']='FROZEN_CANDIDATE_NOT_INSTALLED'
        self.assertIn('SUPPLEMENTARY_MISSING_OR_FAILED',validate(records,'release','source'))

    def test_motion_review_cold_rejects_reanalysis_changed_identity_or_authority(self):
        name='Saved physical motion review cold reopens without Analyze or restored authority'
        for key,value in (('job_id','different'),('input_receipt_sha256','different'),('review_sha256','different'),('input_segments_sha256','different'),
                ('input_rows',11),('analysis_post_count',1),('physical_activation',1),('physical_motion_verified',True),('raw_receipt_sha256_checked',False)):
            with self.subTest(key=key):
                records=fixture();e=next(s for s in records['lineage_cold']['steps'] if s['name']==name)['evidence'];e[key]=value
                self.assertIn('MOTION_REVIEW_COLD_BINDING_OR_AUTHORITY_INVALID',validate(records,'release','source'))

    def test_shutdown_requires_exact_handoff_owner_roles_and_unforced_roots(self):
        # Synthetic contract tests only. No result is App/hardware evidence.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records=fixture()
            names=('fresh','cold','lineage','lineage_cold','normal','restart','reproduction')
            starts={name:dict(launch_id='launch-'+name,owner_pid=100+i) for i,name in enumerate(names)}
            for name in names[:4]:records[name]['desktop']['engine']['launch_id']=starts[name]['launch_id']
            records['normal']['launch_id']=starts['normal']['launch_id'];records['lifecycle']['restart_launch_id']=starts['restart']['launch_id']
            joins=dict(viewport_alive=False,fleet_alive=False,diagnostic_alive=False,scan_worker=dict(worker_alive=False,cleanup_errors=[]))
            engine=dict(cleanup_status='PRE_CLOSE_COMPLETE',cleanup_errors=[],app_close=dict(state='PREPARED_FOR_ISAAC_CLOSE',external_confirmation_required=True),viewport_phase_diagnostics=dict(join_status=joins))
            roles={name:dict(role=name,pid=200+i,ownership='HELD_POPEN_PROCESS_HANDLE',evidence_complete=True,errors=[],
                root_disposition='EXITED_DURING_GRACE',return_code=0,job_close_requested=True,job_observation='OBSERVED',job_active_before_close=1)
                for i,name in enumerate(('engine','backend'))}
            def write(name,value):
                path=root/name;raw=json.dumps(value).encode();path.write_bytes(raw)
                return dict(path=name,sha256=hashlib.sha256(raw).hexdigest())
            def check(change=None,changed_branch='fresh'):
                contract=dict(schema='owned-shutdown-contract-1.0',release_id='release',source_sha256='source',branches={})
                for name in names:
                    start=deepcopy(starts[name]);inner=dict(deepcopy(engine),launch_id=start['launch_id'])
                    owner=dict(schema='owned-exit-observations-1.0',**start,execution_id='shutdown-'+name,evidence_complete=True,roles=deepcopy(roles))
                    cleanup=dict(**start,owned_processes_stopped=True,exit_evidence_complete=True,process_exit_observations=deepcopy(roles))
                    if name==changed_branch and change:change(start,inner,owner,cleanup)
                    contract['branches'][name]={key:write(name+'-'+key+'.json',value) for key,value in dict(start=start,engine_result=inner,owner_exit=owner,cleanup=cleanup).items()}
                reproduction=reproduction_fixture();reproduction['desktop']['engine']['launch_id']=starts['reproduction']['launch_id']
                manifest=dict(physical_readiness_review=dict(schema='physical-readiness-review-1.2',shutdown_contract=write('contract.json',contract),reproduction=write('reproduction.json',reproduction),reproduction_expected=dict(project='p',scene_revision='scene')))
                return module['shutdown_review_issues'](manifest,root,records,'release','source')
            self.assertEqual(check(),[]) # A Job descendant count is not root graceful-exit proof or a hidden veto.
            for value in (True,None):
                self.assertIn('SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:reproduction',check(
                    lambda s,e,o,c:e['viewport_phase_diagnostics']['join_status'].update(diagnostic_alive=value),'reproduction'))
            self.assertIn('SHUTDOWN_LAUNCH_BINDING_INVALID:reproduction',check(lambda s,e,o,c:e.update(launch_id='other'),'reproduction'))
            for change,expected in (
                (lambda s,e,o,c:e.update(cleanup_status='PRE_CLOSE_FAILED'),'SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:fresh'),
                (lambda s,e,o,c:e['viewport_phase_diagnostics']['join_status'].update(fleet_alive=True),'SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:fresh'),
                (lambda s,e,o,c:e['viewport_phase_diagnostics']['join_status'].update(cleanup_errors=[dict(owner='viewport_http',error='OSError')]),'SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:fresh'),
                (lambda s,e,o,c:e['app_close'].update(state='RAISED'),'SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:fresh'),
                (lambda s,e,o,c:e.update(error='ORIGINAL_HOST_ERROR'),'SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:fresh'),
                (lambda s,e,o,c:e.update(launch_id='other-good-sha-launch'),'SHUTDOWN_LAUNCH_BINDING_INVALID:fresh'),
                (lambda s,e,o,c:o.update(evidence_complete=False),'SHUTDOWN_OWNER_EVIDENCE_INCOMPLETE:fresh'),
                (lambda s,e,o,c:c.update(exit_evidence_complete=False),'SHUTDOWN_OWNER_EVIDENCE_INCOMPLETE:fresh'),
                (lambda s,e,o,c:s.update(launch_id='other'),'SHUTDOWN_LAUNCH_BINDING_INVALID:fresh'),
                (lambda s,e,o,c:o['roles']['engine'].update(root_disposition='TERMINATE_AFTER_TIMEOUT'),'SHUTDOWN_ROOT_FORCED_UNKNOWN_OR_JOB_UNOBSERVED:fresh:engine'),
                (lambda s,e,o,c:o['roles']['engine'].update(root_disposition='UNKNOWN'),'SHUTDOWN_ROOT_FORCED_UNKNOWN_OR_JOB_UNOBSERVED:fresh:engine'),
                (lambda s,e,o,c:o['roles']['engine'].update(job_observation='UNKNOWN'),'SHUTDOWN_ROOT_FORCED_UNKNOWN_OR_JOB_UNOBSERVED:fresh:engine'),
                (lambda s,e,o,c:o['roles']['engine'].update(evidence_complete=False,errors=[dict(stage='evidence_store')]),'SHUTDOWN_ROOT_FORCED_UNKNOWN_OR_JOB_UNOBSERVED:fresh:engine'),
            ):
                with self.subTest(expected=expected):self.assertIn(expected,check(change))
            self.assertEqual(module['shutdown_review_issues'](dict(physical_readiness_review=dict(schema='physical-readiness-review-1.2')),root,records,'release','source'),['SHUTDOWN_CONTRACT_UNREADABLE_OR_SHA_MISMATCH'])
            for schema in ('physical-readiness-review-1.0','physical-readiness-review-1.1',None):
                self.assertEqual(module['shutdown_review_issues'](dict(physical_readiness_review=dict(schema=schema)),root,records,'release','source'),['CURRENT_SHUTDOWN_CONTRACT_REQUIRED'])

    def test_registration_restore_proof_missing_or_changed_is_rejected(self):
        for role in ('fresh','cold'):
            rows=fixture();rows[role].pop('registration_history')
            self.assertIn('REGISTRATION_CHAT_RESTORE_NOT_PROVEN',validate(rows,'release','source'))
        rows=fixture();rows['cold']['registration_history']['entries'].append(dict(robot_id='duplicate'))
        self.assertIn('REGISTRATION_CHAT_RESTORE_NOT_PROVEN',validate(rows,'release','source'))
    def test_sensor_off_leftover_hits_and_detached_names_are_rejected(self):
        for overlay in (1,None):
            r=fixture();next(s for s in r['fresh']['steps'] if s['name']=='LiDAR Off pauses but retains connection; On restarts sensor')['evidence']['off']['overlay_count']=overlay
            self.assertIn('SENSOR_OFF_OVERLAY_REMOVAL_NOT_PROVEN',validate(r,'release','source'))
        for change in (dict(origin_marker_count=1),dict(label_under_body_error_px=20),dict(label_horizontal_error_px=20)):
            r=fixture();r['fresh']['display_samples'][0].update(change)
            self.assertIn('ROBOT_LABEL_NOT_ATTACHED_TO_BODY',validate(r,'release','source'))
    def test_missing_physical_goal_entry_or_unauthorized_off_send_is_not_ready(self):
        for change in ({'destination_policy_visible':False},{'off_destination_send_disabled':False},{'physical_destination_commands_sent':1}):
            r=fixture();next(s for s in r['fresh']['steps'] if s['name']=='Physical setup shown while robot remains off; no Connect or movement')['evidence'].update(change)
            self.assertIn('PHYSICAL_DESTINATION_OFF_ENTRY_NOT_PROVEN',validate(r,'release','source'))
    def test_actual_shared_sensor_import_is_required_not_an_unclassified_normal_step(self):
        r=fixture();name='Actual saved native scan imported via UI and shown by the shared renderer without world alignment'
        r['fresh']['steps']=[s for s in r['fresh']['steps'] if s['name']!=name]
        self.assertIn('MISSING_OR_FAILED_STEP:fresh:'+name,validate(r,'release','source'))
    def test_missing_body_click_or_detached_marker_is_not_full_acceptance(self):
        for value in ([],[dict(name='Alpha',bodyHit=True,marker_error_px=0)],
                      [dict(name=n,bodyHit=True,marker_error_px=20) for n in ('Alpha','Beta')]):
            rows=fixture();next(s for s in rows['fresh']['steps'] if s['name'].startswith('Non-overlapping dock'))['evidence']['bodySelections']=value
            self.assertIn('CURRENT_MODEL_BODY_SELECTION_NOT_PROVEN',validate(rows,'release','source'))
    def test_final_stop_rejects_missing_or_duplicate_ids_and_old_epochs(self):
        mutations=(lambda r:r['fresh']['final_fault_recovery'].pop('stop_request_id'),
            lambda r:r['fresh']['final_fault_recovery'].update(stop_request_id=''),
            lambda r:r['fresh']['fleet_requests'].append(deepcopy(r['fresh']['fleet_requests'][0])),
            lambda r:r['fresh']['final_fault_recovery']['before_stop_robots'][0].pop('motion_epoch'),
            lambda r:r['fresh']['final_fault_recovery']['before_stop_robots'][0].update(motion_epoch=''),
            lambda r:r['fresh']['final_fault_recovery']['before_stop_robots'].append(deepcopy(r['fresh']['final_fault_recovery']['before_stop_robots'][0])))
        for mutate in mutations:
            rows=fixture();mutate(rows)
            self.assertIn('FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN',validate(rows,'release','source'))

    def test_final_recovery_requires_visible_controls_connection_and_stream(self):
        for point in ('before','after'):
            for flag in ('canvas_visible','stop_visible','pad_visible','robot_badge_visible'):
                rows=fixture();rows['fresh']['final_fault_recovery'][point][flag]=False
                self.assertIn('FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN',validate(rows,'release','source'))
        for field,value in [('connection_state','DISCONNECTED'),('lidar_state','OFF')]:
            rows=fixture();rows['fresh']['final_fault_recovery']['stopped_robots'][0][field]=value
            self.assertIn('FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN',validate(rows,'release','source'))

    def test_complete_synthetic_fixture_only_tests_gate_logic(self):self.assertEqual(validate(fixture(),'release','source'),[])
    def test_normal_controls_after_or_inside_fault_window_cannot_claim_unintercepted_path(self):
        for mutate in (lambda r:r['fresh'].pop('normal_steps_before_fault_window'),
                lambda r:r['fresh'].update(fault_window_held_until_exit=False),
                lambda r:r['fresh']['steps'].reverse()):
            r=fixture();mutate(r)
            self.assertIn('ORDINARY_PATH_NOT_SEPARATE_FROM_FINAL_FAULT_WINDOW',validate(r,'release','source'))
    def test_cold_motion_after_fault_cannot_claim_normal_path(self):
        r=fixture();r['cold']['steps'].reverse()
        self.assertIn('COLD_NORMAL_MOTION_NOT_BEFORE_FAULT_WINDOW',validate(r,'release','source'))
    def test_final_fault_requires_exact_stop_new_applied_epochs_and_advancing_same_scene_frame(self):
        for mutate in (lambda r:r['fresh'].pop('final_fault_recovery'),
                lambda r:r['fresh']['final_fault_recovery']['after'].update(frame_id=1),
                lambda r:r['fresh']['final_fault_recovery']['after'].update(stage_epoch='other'),
                lambda r:r['fresh']['final_fault_recovery']['stopped_robots'][0].update(applied_motion_epoch='old'),
                lambda r:r['fresh']['final_fault_recovery'].update(stop_request_id='missing'),
                lambda r:r['fresh']['fleet_requests'][0]['result_robots'][0].update(operation_id='other')):
            r=fixture();mutate(r)
            self.assertIn('FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN',validate(r,'release','source'))
    def test_pose_only_success_and_nonfinite_or_clipped_display_are_rejected(self):
        r=fixture();r['fresh']['display_samples']=[]
        self.assertIn('CONTINUOUS_DISPLAY_SAMPLES_MISSING',validate(r,'release','source'))
        for change in (dict(frame_age_ms=math.nan),dict(frame_age_ms=-1),dict(robot_bounds=[]),dict(pad_visible=False),dict(canvas=dict(height=149)),dict(canvas=dict(height=math.nan))):
            r=fixture();r['fresh']['display_samples'][0].update(change)
            self.assertIn('INVALID_OR_OBSCURED_CURRENT_DISPLAY',validate(r,'release','source'))
    def test_known_physical_blockers_cannot_be_overridden_by_sim_pass(self):
        check=module['physical_review_issues']
        self.assertEqual(check({}),['MISSING_CURRENT_PHYSICAL_READINESS_REVIEW'])
        self.assertEqual(check(dict(physical_readiness_review=dict(status='SOFTWARE_NO_KNOWN_BLOCKER'))),['INVALID_PHYSICAL_READINESS_REVIEW'])
        self.assertEqual(check(dict(physical_readiness_review=dict(schema='physical-readiness-review-1.0',status='SOFTWARE_NO_KNOWN_BLOCKER',unresolved=['PROTOCOL_UNKNOWN'],evidence=['original-raw-sha']))),['KNOWN_PHYSICAL_BLOCKER:PROTOCOL_UNKNOWN'])
    def test_supervised_entry_is_not_physical_completion_or_unknown_software_bypass(self):
        check=module['physical_review_issues']
        review=dict(schema='physical-readiness-review-1.1',status='SOFTWARE_NO_KNOWN_BLOCKER',unresolved=[],evidence=['current-source-replay'],
            scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
            observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
            not_run=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT'],
            protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',replay=dict(path='replay.json',sha256='a'*64))
        self.assertEqual(check(dict(physical_readiness_review=review)),[])
        self.assertIn('CONTROL_REPLAY_UNREADABLE',module['replay_review_issues'](dict(physical_readiness_review=review),Path('.').resolve()))
        bad=deepcopy(review);bad['unresolved']=['LIVE_STOP_BROKEN']
        self.assertEqual(check(dict(physical_readiness_review=bad)),['KNOWN_PHYSICAL_BLOCKER:LIVE_STOP_BROKEN'])
        bad=deepcopy(review);bad['not_run'].append('UNIMPLEMENTED_CONNECT_BUTTON')
        self.assertEqual(check(dict(physical_readiness_review=bad)),['INVALID_SUPERVISED_TEST_ENTRY_REVIEW'])
    def test_replay_gate_rejects_directional_blockage_corruption_and_other_input(self):
        # Synthetic gate receipt only; never App, sensor or hardware evidence.
        root=Path(__file__).resolve().parents[2]
        sources={'packages/twinpulse_robot_safety/'+n+'.py':hashlib.sha256((root/'packages/twinpulse_robot_safety'/f'{n}.py').read_bytes()).hexdigest()
                 for n in ('native_stream','field_tests','fleet_control')}
        value=dict(status='PASS',classification='OFFLINE_SAVED_INPUT_NOT_PI_OR_PHYSICAL_ACCEPTANCE',
            raw_sha256='7a50ff3fec3cb24e500faead1e5b5d0caeea8b0654ad2db615aa491ebaa21522',raw_bytes=8336993,chunks=51791,
            checksum_errors=0,pending_bytes=0,frames=6081,strict_incomplete=202,retained_complete_observations=201,unknown_bytes=2259,
            held_age_max_ms=164.,source_sha256=sources,directions={name:{'OBSERVATION_ACCEPTED':6080,'FIELD_COMPLETE_NATIVE_RING_REQUIRED':1}
                for name in ('forward','backward','left','right')})
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);target=folder/'replay.json'
            def check(row):
                raw=json.dumps(row).encode();target.write_bytes(raw)
                manifest=dict(physical_readiness_review=dict(schema='physical-readiness-review-1.1',replay=dict(path=target.name,sha256=hashlib.sha256(raw).hexdigest())))
                return module['replay_review_issues'](manifest,folder)
            self.assertEqual(check(value),[])
            for key,new in [('raw_sha256','a'*64),('raw_bytes',8336992),('checksum_errors',1),('pending_bytes',1),('held_age_max_ms',351.)]:
                bad=deepcopy(value);bad[key]=new;self.assertEqual(check(bad),['CONTROL_REPLAY_NOT_QUALIFIED'])
            bad=deepcopy(value);bad['directions']['backward']={'FIELD_DIRECTION_COVERAGE_UNKNOWN':6080}
            self.assertEqual(check(bad),['CONTROL_REPLAY_DIRECTIONS_NOT_QUALIFIED'])
            bad=deepcopy(value);bad['source_sha256']={'unrelated.py':'b'*64}
            self.assertEqual(check(bad),['CONTROL_REPLAY_SOURCE_MISSING'])
    def test_duplicate_sizes_broken_lineage_and_short_display_interval_rejected(self):
        r=fixture();layout=next(s for s in r['fresh']['steps'] if s['name'].startswith('Non-overlapping dock'))['evidence']['rows'];layout[0]=deepcopy(layout[1])
        self.assertIn('DISPLAY_LAYOUT_SIZES_NOT_PROVEN',validate(r,'release','source'))
        for change in (dict(at=1),dict(frame_id=0),dict(stage_epoch='other')):
            r=fixture();r['fresh']['display_samples'][5].update(change)
            self.assertIn('DISPLAY_TIME_FRAME_OR_LINEAGE_INVALID',validate(r,'release','source'))
        r=fixture();r['fresh']['sustained_hold_observations']=[dict(at=i) for i in range(120)]
        self.assertIn('CONTINUOUS_60S_DISPLAY_INTERVAL_MISSING',validate(r,'release','source'))
        r=fixture()
        for row in r['fresh']['display_samples']:row['frame_id']=1
        r['fresh']['display_samples'].append(dict(r['fresh']['display_samples'][-1],at=62001,frame_id=2))
        self.assertIn('CONTINUOUS_HOLD_DECODED_FRAME_NOT_ADVANCING',validate(r,'release','source'))
    def test_missing_role_and_failed_whole_flow_rejected(self):
        r=fixture();r.pop('cold');r['fresh']['status']='FAIL'
        issues=validate(r,'release','source');self.assertIn('MISSING_ROLE:cold',issues);self.assertIn('RUN_NOT_PASS:fresh',issues)
    def test_old_release_and_split_resume_rejected(self):
        r=fixture();r['lineage']['phase']='resume-completed-motion';r['fresh']['desktop']['engine']['release_id']='old'
        issues=validate(r,'release','source');self.assertIn('WRONG_RELEASE:fresh',issues);self.assertIn('SPLIT_OR_WRONG_PHASE:lineage',issues)
    def test_observation_only_package_cannot_claim_powered_control_readiness(self):
        r=fixture();r['installation']['capabilities']['physical_robot']=False
        self.assertIn('INSTALLATION_NOT_EXACT',validate(r,'release','source'))
    def test_each_required_step_missing_is_rejected_even_when_overall_pass(self):
        for role,names in required.items():
            for name in names:
                with self.subTest(role=role,name=name):
                    r=fixture();r[role]['steps']=[s for s in r[role]['steps'] if s['name']!=name]
                    self.assertIn('MISSING_OR_FAILED_STEP:'+role+':'+name,validate(r,'release','source'))
    def test_old_source_supplementary_and_unclean_lifecycle_rejected(self):
        r=fixture();r['supplementary']['source_sha256']='old';r['lifecycle']['shutdown_clean']=False
        issues=validate(r,'release','source');self.assertIn('SUPPLEMENTARY_MISSING_OR_FAILED',issues)
        self.assertIn('NORMAL_LIFECYCLE_NOT_QUALIFIED',issues)
    def test_slow_restart_does_not_resolve_original_startup_failure(self):
        r=fixture();r['lifecycle']['restart_ready_wait_ms']=120210
        self.assertIn('NORMAL_LIFECYCLE_NOT_QUALIFIED',validate(r,'release','source'))
    def test_restart_without_clean_shutdown_cannot_claim_ready(self):
        for value in (False,None):
            r=fixture();r['lifecycle']['restart_shutdown_clean']=value
            self.assertIn('NORMAL_LIFECYCLE_NOT_QUALIFIED',validate(r,'release','source'))
    def test_unexplained_get_failure_is_not_hidden_by_overall_pass(self):
        r=fixture();r['fresh']['request_failures']=[dict(method='GET',path='/v1/product/runtime',error='net::ERR_FAILED',exiting=False)]
        self.assertIn('UNCLASSIFIED_REQUEST_FAILURE:fresh',validate(r,'release','source'))
    def test_short_rotation_cannot_resolve_original_failure(self):
        r=fixture();r['lineage']['requested_command']='left 10 degrees'
        step=next(s for s in r['fresh']['steps'] if '90 degree command' in s['name']);step['evidence']['delta']=math.radians(10)
        self.assertTrue(any('ANGLE_NOT_PROVEN' in i for i in validate(r,'release','source')))
        self.assertIn('ORIGINAL_LINEAGE_90_NOT_RUN',validate(r,'release','source'))
    def test_timeout_and_budget_and_changed_input_rejected(self):
        r=fixture();r['normal']['ready_wait_ms']=120210;r['budget']['within_approved_total']=False;r['cold']['project']='other'
        issues=validate(r,'release','source');self.assertIn('NORMAL_START_NOT_QUALIFIED',issues);self.assertIn('BUDGET_UNCONFIRMED_OR_EXCEEDED',issues)
        self.assertIn('PROJECT_MISMATCH:fresh:cold',issues)
    def test_file_hash_and_duplicate_role_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'evidence.json';p.write_text(json.dumps(dict(status='PASS')))
            m=dict(evidence=[dict(role='fresh',path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()),
                             dict(role='fresh',path=p.name,sha256='wrong'),dict(role='cold',path=p.name,sha256='wrong')])
            _,_,issues=module['load_evidence'](m,root)
            self.assertIn('INVALID_OR_DUPLICATE_REFERENCE:fresh',issues);self.assertIn('EVIDENCE_HASH_MISMATCH:cold',issues)
