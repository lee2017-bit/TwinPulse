# SPDX-License-Identifier: Apache-2.0
"""Device-free review tests; synthetic fits are not physical acceptance."""
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.physical_motion_analysis import read_archive,analyse,windows,digest
from twinpulse_app.physical_motion_review import PhysicalMotionReview
from twinpulse_app.command_broker import BrokerError

OP='1'*32;PROJECT='saved-project';ROBOT='2'*32;EPOCH='3'*32
def archive():
    config=dict(angle_sign=1,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.)
    first=dict(operation_id=OP,project_id=PROJECT,robot_id=ROBOT,connection_epoch=EPOCH,source_twin_context=None)
    return dict(first=first,receipt=dict(segments=[],complete=False,error='ORIGINAL_FAILURE'),receipt_sha256='a'*64,
        rows=0,scans=[],poses=[],terminal=[],pubs=[],pauses=[],fields=[],sources={'field-config.json':{'config':config},
        'field-trials.json':{'trials':[dict(case='stationary',started_s=0.,ended_s=9.,config_sha256=digest(config))]}})

def write_archive(root,events):
    p=Path(root)/OP;p.mkdir(exist_ok=True)
    header=dict(schema='physical-live-pc-start-2.0',operation_id=OP,project_id=PROJECT,robot_id=ROBOT,connection_epoch=EPOCH,source_twin_context=None)
    rows=[header]+[dict(schema='physical-live-event-2.0',operation_id=OP,project_id=PROJECT,robot_id=ROBOT,connection_epoch=EPOCH,
        sequence=i+1,robot_monotonic_s=float(i+1),**event) for i,event in enumerate(events)]
    raw=b''.join((json.dumps(row)+'\n').encode() for row in rows);(p/'events-00000.jsonl').write_bytes(raw)
    (p/'receipt.json').write_text(json.dumps(dict(schema='physical-live-recording-1.0',segments=[dict(path='events-00000.jsonl',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())],event_count=len(rows),bytes=len(raw),complete=False)))
    return p

class AnalysisTests(unittest.TestCase):
    def test_scan_sampling_keeps_last_sector_and_original_point_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            points=[[float(i),0.] for i in range(398)]
            p=write_archive(tmp,[dict(kind='scan',data=dict(complete=True,quality=dict(interval_fallback_packets=0),
                timing=dict(receipt_start_s=1.,receipt_end_s=1.1),points=points,stream_id='s',frame_sequence=1,raw_sha256='b'*64))])
            a=read_archive(p,OP,PROJECT,time.monotonic()+5);scan=a['scans'][0]
            self.assertGreater(scan['points'][-1][0],393.)
            self.assertEqual(scan['input_point_count'],398);self.assertEqual(scan['points_full'],points)

    def test_legacy_repeated_same_direction_is_not_joined(self):
        a=archive();a['pubs']=[dict(sequence=1,at=10.,direction='forward',request_id='one'),dict(sequence=3,at=12.,direction='forward',request_id='two')]
        a['pauses']=[dict(sequence=2,at=10.2,reason='EXPIRED'),dict(sequence=4,at=12.2,reason='STOP')]
        rows,truncated=windows(a)
        self.assertFalse(truncated);self.assertEqual([r['request_id'] for r in rows],['one','two'])
        self.assertTrue(all(r['motion_epoch'] is None for r in rows));self.assertTrue(all('LEGACY' in r['linkage'] for r in rows))

    def test_full_revolution_is_adjacent_unwrapped_not_zero(self):
        a=archive()
        for i in range(86):
            t=i*.2
            a['scans'].append(dict(start=t,end=t,stream_id='scan',frame_sequence=i,raw_sha256='b'*64,points=[[t,0.]]*50))
        a['terminal']=[dict(request_id='turn',latest_request_id='turn',motion_epoch=EPOCH,direction='left',first_sample_s=10.,sample_s=16.4,ended_s=16.5,
            reason='TASK_COMPLETED',centre_m=0.,yaw_rad=math.tau,wheel_data_quality='RAW_DELTA_UNQUALIFIED')]
        calls=[]
        def fit(p,q,**kw):
            calls.append((p[0][0],q[0][0]));return dict(delta=(0.,0.,.2 if p[0][0]>=9.8 else 0.),residual_m=.001)
        v=analyse(a,fit,time.monotonic()+5)
        row=v['windows'][0]
        self.assertGreater(row['lidar']['yaw_rad'],6.)
        self.assertFalse(v['physical_motion_verified']);self.assertFalse(v['authority_restored'])
        self.assertEqual(row['body_motion'],'UNQUALIFIED_UNKNOWN');self.assertTrue(calls)
        self.assertFalse(v['original_complete']);self.assertEqual(v['original_error'],'ORIGINAL_FAILURE')

    def test_gap_does_not_fabricate_rotation_or_comparison(self):
        a=archive();a['terminal']=[dict(request_id='x',motion_epoch=EPOCH,direction='left',first_sample_s=10.,sample_s=12.,ended_s=12.1)]
        a['scans']=[dict(start=t,end=t,points=[[0.,0.]]*50,stream_id='s',frame_sequence=i,raw_sha256='b'*64) for i,t in enumerate((10.,12.))]
        v=analyse(a,lambda *a,**kw: (_ for _ in ()).throw(AssertionError('No fit across missing coverage')),time.monotonic()+5)
        self.assertEqual(v['windows'][0]['lidar']['status'],'SCAN_STREAM_OR_COVERAGE_GAP')
        self.assertNotIn('yaw_rad',v['windows'][0]['lidar']);self.assertFalse(v['physical_motion_verified'])

    def test_missing_extrinsics_never_claims_quantitative_agreement(self):
        a=archive();a['sources']={};v=analyse(a,lambda *a,**kw:None,time.monotonic()+5)
        self.assertEqual(v['comparison_frame'],'SENSOR_LOCAL_UNCONFIRMED')

    def test_short_window_requires_actual_before_and_after_frames(self):
        a=archive();a['terminal']=[dict(request_id='short',motion_epoch=EPOCH,direction='forward',first_sample_s=10.,sample_s=10.1,ended_s=10.2)]
        a['scans']=[dict(start=t,end=t,points=[[0.,0.]]*50,stream_id='s',frame_sequence=i,raw_sha256='b'*64) for i,t in enumerate((9.75,9.95))]
        v=analyse(a,lambda *a,**kw:self.fail('Both frames precede the command'),time.monotonic()+5)
        self.assertEqual(v['windows'][0]['lidar']['status'],'INSUFFICIENT_WINDOW_EDGE_COVERAGE')

    def test_short_legacy_window_rejects_two_odometry_samples_before_command(self):
        a=archive();a['pubs']=[dict(sequence=1,at=10.,direction='forward',request_id='short')]
        a['pauses']=[dict(sequence=2,at=10.1,reason='STOP')]
        a['poses']=[dict(sample_s=t,x=t,y=0.,yaw=0.,frame_id='odom') for t in (9.75,9.95)]
        v=analyse(a,lambda *a,**kw:None,time.monotonic()+5)
        self.assertIsNone(v['windows'][0]['wheel'])

    def test_applied_epoch_is_read_from_actual_producer_and_splits_gestures(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=write_archive(tmp,[dict(kind='command',data=dict(status='PUBLISHED',direction='forward',request_id='one',applied_motion_epoch='first')),
                dict(kind='command',data=dict(status='PUBLISHED',direction='forward',request_id='two',applied_motion_epoch='second')),
                dict(kind='control_pause',data=dict(reason='STOP'))])
            a=read_archive(p,OP,PROJECT,time.monotonic()+5)
            # Adjacent publications: the epoch, not a timing gap, splits them.
            a['pubs'][1]['at']=a['pubs'][0]['at']+.1
            rows,_=windows(a);self.assertEqual([r['motion_epoch'] for r in rows],['first','second'])
            p=write_archive(tmp,[dict(kind='command',data=dict(status='PUBLISHED',direction='forward',applied_motion_epoch='first',motion_epoch='second'))])
            with self.assertRaisesRegex(ValueError,'EPOCH_CONFLICT'):read_archive(p,OP,PROJECT,time.monotonic()+5)

    def test_rejected_fallback_and_incomplete_scans_block_interpolated_coverage(self):
        for complete,quality,reason in ((True,{'interval_fallback_packets':1},'FALLBACK_OR_QUALITY_NOT_RECORDED'),(False,{'interval_fallback_packets':0},'INCOMPLETE_SCAN')):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as tmp:
                p=write_archive(tmp,[dict(kind='scan',data=dict(complete=complete,quality=quality,timing=dict(receipt_end_s=10.1)))])
                a=read_archive(p,OP,PROJECT,time.monotonic()+5);self.assertEqual(a['rejected_scans'][reason],1)
                a['terminal']=[dict(request_id='x',motion_epoch='e',direction='forward',first_sample_s=10.,sample_s=10.2,ended_s=10.2)]
                a['scans']=[dict(start=t,end=t,points=[[0.,0.]]*50,stream_id='s',frame_sequence=i,raw_sha256='b'*64) for i,t in enumerate((9.9,10.3))]
                v=analyse(a,lambda *a,**kw:self.fail('Rejected ring cannot be bridged'),time.monotonic()+5)
                self.assertEqual(v['windows'][0]['lidar']['status'],'REJECTED_SCAN_INTERVAL_UNQUALIFIED')

    def test_later_configuration_is_not_applied_to_earlier_points(self):
        a=archive();config=dict(a['sources']['field-config.json']['config'],axes_reviewed=True,robot_id=ROBOT,binding_sha256='b'*64,sensor_x_m=100.)
        a['first']['binding_sha256']='b'*64;a['sources']['field-config.json']['config']=config;a['fields']=[(11.,{'config':config})]
        a['terminal']=[dict(request_id='early',motion_epoch='e',direction='forward',first_sample_s=10.,sample_s=10.2,ended_s=10.3)]
        a['scans']=[dict(start=t,end=t,points=[[0.,0.]]*50,stream_id='s',frame_sequence=i,raw_sha256='b'*64) for i,t in enumerate((9.9,10.1,10.3))]
        def fit(p,q,**kw):
            self.assertEqual(p[0][0],0.);return dict(delta=(0.,0.,0.),residual_m=0.)
        row=analyse(a,fit,time.monotonic()+5)['windows'][0]
        self.assertEqual(row['lidar']['comparison_frame'],'SENSOR_LOCAL_UNCONFIRMED')

    def test_terminal_does_not_hide_later_missing_terminal(self):
        a=archive();a['terminal']=[dict(request_id='done',motion_epoch=EPOCH,direction='forward',first_sample_s=10.,sample_s=10.2,ended_s=10.3)]
        a['pubs']=[dict(sequence=1,at=10.1,direction='forward',request_id='done'),dict(sequence=2,at=12.,direction='forward',request_id='missing')]
        v=analyse(a,lambda *a,**kw:None,time.monotonic()+5)
        self.assertEqual(len(v['windows']),2)
        self.assertIsNone(v['windows'][1]['end']);self.assertEqual(v['windows'][1]['comparison'],'TERMINAL_RECORD_MISSING')

    def test_unclosed_publications_keep_their_own_direction_and_epoch(self):
        a=archive();a['pubs']=[dict(sequence=1,at=10.,direction='forward',request_id='a',motion_epoch='first'),dict(sequence=2,at=10.1,direction='left',request_id='b',motion_epoch='second')]
        rows,_=windows(a)
        self.assertEqual([(r['direction'],r['motion_epoch']) for r in rows],[('forward','first'),('left','second')]);self.assertTrue(all(r['end'] is None for r in rows))

    def test_configuration_change_prevents_borrowing_final_extrinsics(self):
        a=archive();a['fields']=[(1.,{'config':dict(a['sources']['field-config.json']['config'])}),(9.,{'config':dict(angle_sign=-1,sensor_x_m=.1,sensor_y_m=0.,sensor_yaw_rad=0.)})]
        v=analyse(a,lambda *a,**kw:None,time.monotonic()+5)
        self.assertEqual(v['comparison_frame'],'SENSOR_LOCAL_UNCONFIRMED')

    def test_full_archive_hash_and_project_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/OP;p.mkdir()
            header=dict(schema='physical-live-pc-start-2.0',operation_id=OP,project_id=PROJECT,robot_id=ROBOT,connection_epoch=EPOCH,source_twin_context=None)
            event=dict(schema='physical-live-event-2.0',operation_id=OP,project_id=PROJECT,robot_id=ROBOT,connection_epoch=EPOCH,
                sequence=1,robot_monotonic_s=1.,kind='control_pause',data={'reason':'FAILED'})
            raw=b''.join((json.dumps(v)+'\n').encode() for v in (header,event));member=p/'events-00000.jsonl';member.write_bytes(raw)
            receipt=dict(schema='physical-live-recording-1.0',segments=[dict(path=member.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())],event_count=2,bytes=len(raw),complete=False)
            (p/'receipt.json').write_text(json.dumps(receipt))
            self.assertFalse(read_archive(p,OP,PROJECT,time.monotonic()+5)['receipt']['complete'])
            with self.assertRaisesRegex(ValueError,'START_BINDING'):read_archive(p,OP,'other',time.monotonic()+5)
            member.write_bytes(raw.replace(b'FAILED',b'FIXED!'))
            with self.assertRaisesRegex(ValueError,'SEGMENT_SHA'):read_archive(p,OP,PROJECT,time.monotonic()+5)

class Devices:
    def __init__(self):self.lock=threading.RLock();self.active=False
    def physical_runtime_active(self):return self.active

class Job:
    def assign(self,p):pass
    def close(self):pass
    def terminate(self):pass

class ReviewTests(unittest.TestCase):
    def test_cancel_during_spawn_does_not_join_or_publish_late_result(self):
        devices=Devices();entered=threading.Event();release=threading.Event()
        class Process:
            returncode=None
            def terminate(self):self.returncode=1
            def wait(self,timeout=None):return self.returncode or 0
            def poll(self):return self.returncode
        process=Process()
        def spawn(*args,**kwargs):entered.set();release.wait(3);return process
        with tempfile.TemporaryDirectory() as tmp:
            service=PhysicalMotionReview(devices,ROOT,tmp,popen=spawn,job_factory=Job)
            state=service.start(OP,PROJECT,'r')
            self.assertTrue(entered.wait(2));start=time.monotonic()
            service.cancel(OP,PROJECT,state['job']['job_id'])
            self.assertLess(time.monotonic()-start,.2)
            self.assertEqual(service.snapshot(OP,PROJECT)['job']['status'],'CANCEL_REQUESTED')
            with self.assertRaises(BrokerError):service.start(OP,PROJECT,'second')
            release.set();service.thread.join(3)
            self.assertFalse(service.thread.is_alive());self.assertEqual(process.returncode,1)
            self.assertIsNone(service.snapshot(OP,PROJECT)['review']);self.assertFalse((Path(tmp)/'motion-reviews'/('saved-'+OP+'.json')).exists())
            self.assertTrue(service.close()['closed'])

    def test_active_physical_owner_rejects_analysis_without_spawning(self):
        devices=Devices();devices.active=True
        with tempfile.TemporaryDirectory() as tmp:
            service=PhysicalMotionReview(devices,ROOT,tmp,popen=lambda *a,**kw: self.fail('No process permitted'))
            with self.assertRaises(BrokerError):service.start(OP,PROJECT,'r')
            self.assertIsNone(service.thread)

    def test_job_close_exception_stays_incomplete_even_after_root_exits(self):
        class BadJob(Job):
            def close(self):raise OSError('injected Job close failure')
        class Process:
            def wait(self,timeout=None):return 0
            def poll(self):return 0
            def terminate(self):pass
        with tempfile.TemporaryDirectory() as tmp:
            service=PhysicalMotionReview(Devices(),ROOT,tmp,popen=lambda *a,**kw:Process(),job_factory=BadJob)
            service.start(OP,PROJECT,'r');service.thread.join(3);receipt=service.close()
            self.assertTrue(receipt['root_reaped']);self.assertFalse(receipt['closed']);self.assertFalse(receipt['evidence_complete'])
            self.assertIn('REVIEW_JOB_CLOSE_UNCONFIRMED',receipt['errors'])

    def test_corrupt_cold_index_is_unavailable_not_an_attribute_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'motion-reviews').mkdir();path=root/'motion-reviews'/('saved-'+OP+'.json')
            for v in ('[]','null'):
                path.write_text(v);self.assertIsNone(PhysicalMotionReview(Devices(),ROOT,root).snapshot(OP,PROJECT)['review'])

    def test_cold_review_is_explicitly_historical_and_project_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'motion-reviews').mkdir()
            path=root/'motion-reviews'/('saved-'+OP+'.json')
            value=dict(schema='physical-motion-review-1.0',operation_id=OP,project_id=PROJECT,status='COMPLETED_WITH_LIMITS',input_receipt_sha256='a'*64,physical_motion_verified=False,authority_restored=False)
            path.write_text(json.dumps(value))
            service=PhysicalMotionReview(Devices(),ROOT,root)
            self.assertEqual(service.snapshot(OP,PROJECT)['review'],value)
            self.assertIsNone(service.snapshot(OP,'other')['review'])
            self.assertIsNone(service.thread);self.assertFalse(service.snapshot(OP,PROJECT)['authority_restored'])

class ApiTests(unittest.TestCase):
    def setUp(self):
        import tests.integration.test_r5_product_api as fixtures
        self.fixture=fixtures.R5ProductApiTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)

    def test_auth_csrf_and_offline_runtime_boundary(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        f=self.fixture;value=dict(job=None,review=None,authority_restored=False)
        physical=SimpleNamespace(motion_review=Mock(return_value=value));f.server.robot_fleet.physical=physical
        path='/v1/product/robot-fleet/operations/'+OP+'/motion-review';body=dict(action='start',request_id='4'*32)
        self.assertEqual(f.request(path)[0],401)
        self.assertEqual(f.request(path,body,headers={'Cookie':f.cookie})[0],403)
        physical.motion_review.assert_not_called()
        f.supervisor_status.write_text(json.dumps({'schema_version':'1.0','status':'error','phase':'failed'}))
        self.assertEqual(f.request(path,headers=f.product_headers)[0],200)
        self.assertEqual(f.request(path,body,headers=f.product_headers)[0],202)
        self.assertEqual(len(physical.motion_review.call_args_list),2)
        self.assertEqual(physical.motion_review.call_args.args[0],OP)
        self.assertEqual(f.request('/v1/product/state',headers=f.product_headers)[1]['operations'],[])

    def test_adapter_small_descriptor_blocks_cross_project_without_reading_segments(self):
        from unittest.mock import Mock
        from twinpulse_app.physical_fleet_adapter import PhysicalFleetAdapter
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'physical-live'/OP;folder.mkdir(parents=True)
            (folder/'events-00000.jsonl').write_text(json.dumps(dict(operation_id=OP,project_id=PROJECT))+'\n')
            (folder/'receipt.json').write_text('{}')
            adapter=PhysicalFleetAdapter.__new__(PhysicalFleetAdapter);adapter.state_root=root
            adapter._history_owner=Mock();adapter.motion_reviews=Mock()
            with self.assertRaises(BrokerError):adapter.motion_review(OP,'authenticated','other')
            adapter.motion_reviews.snapshot.assert_not_called();adapter.motion_reviews.start.assert_not_called()
            adapter.motion_review(OP,'authenticated',PROJECT)
            adapter.motion_reviews.snapshot.assert_called_once_with(OP,PROJECT)
            with self.assertRaises(BrokerError):adapter.motion_review(OP,'authenticated',PROJECT,{'action':'start','request_id':'4'*32,'path':'C:/other'})
            adapter.motion_reviews.start.assert_not_called()

if __name__=='__main__':unittest.main()
